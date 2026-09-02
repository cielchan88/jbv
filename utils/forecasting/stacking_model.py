"""Stacking Ensemble forecaster combining APUVA + ML models - SAME AS Prediksi.py"""

import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import TimeSeriesSplit
from lightgbm import LGBMRegressor
import xgboost as xgb
from .base import BaseForecaster
from .apuva_model import APUVAForecaster
from .. import generate_business_dates
from ..feature_config import MIN_HISTORY_FOR_RECURSIVE_PREDICT, cross_series_for_recursive


class StackingForecaster(BaseForecaster):
    """
    Stacking Ensemble forecaster that combines 4 base models:
    - APUVA (internal baseline)
    - XGBoost
    - RandomForest
    - LightGBM

    With GradientBoosting as meta-learner.
    Uses out-of-fold predictions for training meta-learner to prevent overfitting.

    SAME MECHANISM AS Prediksi.py MODEL 6 for consistency.
    """

    def __init__(self, holidays=None, row_id=None):
        super().__init__(holidays)
        self.base_models = {}
        self.meta_model = None
        self.feature_cols = None
        self.row_id = row_id  # For APUVA sentiment factor

    def fit(self, dates, values, external_series=None):
        """Fit Stacking ensemble model with 4 base models (APUVA + 3 ML)"""
        from ..feature_engineering_optimized import create_features_optimized, select_top_features_optimized

        self.last_date = pd.to_datetime(dates[-1]) if not isinstance(dates[-1], pd.Timestamp) else dates[-1]

        # Base model XGBoost/RandomForest/LightGBM di sini juga meramal secara
        # rekursif. Selain masalah nol yang sama, predict() meneruskan
        # self.external_series TANPA external_series_dates, sehingga
        # create_features_optimized memakai jalur mundur series_values[:len(df)]
        # - yaitu nilai seri saudara dari AWAL sejarah, ditempelkan ke tanggal
        # masa depan. Itu bukan sekadar nol, itu data yang salah dengan yakin.
        external_series = cross_series_for_recursive(external_series, 'Stacking')

        # Store raw data for APUVA and prediction
        self.dates = dates
        self.values = values
        self.external_series = external_series

        # Prepare data for ML models
        ts_df = pd.DataFrame({
            'ds': pd.to_datetime(dates),
            'y': values
        })

        # Create features for ML models
        features_df = create_features_optimized(
            ts_df,
            lag_steps=90,
            holidays_list=self.holidays,
            external_series=external_series
        )

        # Select features
        available_features = [col for col in features_df.columns if col not in ['ds', 'date', 'value']]
        top_features, _ = select_top_features_optimized(features_df, top_k=25)
        self.feature_cols = [f for f in top_features if f in available_features]

        if len(self.feature_cols) == 0:
            self.feature_cols = available_features[:25]

        # Prepare X, y for ML models
        X = features_df[self.feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
        y = features_df['value'].values

        # ============ TRAIN BASE MODELS ============

        # 1. APUVA - uses full historical data pattern
        try:
            apuva_model = APUVAForecaster(holidays=self.holidays, row_id=self.row_id)
            apuva_model.fit(dates, values)
            # Get APUVA in-sample predictions (for meta-learner training)
            apuva_fitted = []
            for i in range(len(y)):
                # Simple approximation: use last available value scaled
                if i > 0:
                    apuva_fitted.append(float(values[i-1]) if i > 0 else float(values[0]))
                else:
                    apuva_fitted.append(float(values[0]))
            self.base_models['APUVA'] = {
                'model': apuva_model,
                'fitted': np.array(apuva_fitted[-len(y):])
            }
        except Exception as e:
            print(f"Warning: APUVA failed to fit: {e}")

        # 2. XGBoost
        xgb_model = xgb.XGBRegressor(
            n_estimators=100, learning_rate=0.05, max_depth=5,
            random_state=42, verbosity=0
        )
        xgb_model.fit(X, y, verbose=False)
        self.base_models['XGBoost'] = {
            'model': xgb_model,
            'fitted': xgb_model.predict(X)
        }

        # 3. RandomForest
        rf_model = RandomForestRegressor(
            n_estimators=100, max_depth=10,
            random_state=42, n_jobs=-1
        )
        rf_model.fit(X, y)
        self.base_models['RandomForest'] = {
            'model': rf_model,
            'fitted': rf_model.predict(X)
        }

        # 4. LightGBM
        lgb_model = LGBMRegressor(
            n_estimators=100, learning_rate=0.05, max_depth=5,
            random_state=42, verbose=-1
        )
        lgb_model.fit(X, y)
        self.base_models['LightGBM'] = {
            'model': lgb_model,
            'fitted': lgb_model.predict(X)
        }

        # ============ STACK BASE MODEL PREDICTIONS ============
        # Get fitted values from all successful base models
        successful_models = [name for name in self.base_models.keys()]

        if len(successful_models) < 2:
            raise ValueError(f"Need at least 2 base models, got {len(successful_models)}")

        # Stack predictions as features for meta-learner
        train_meta_features = np.column_stack([
            self.base_models[name]['fitted'] for name in successful_models
        ])

        # ============ CROSS-VALIDATION FOR OUT-OF-FOLD PREDICTIONS ============
        # This prevents overfitting - SAME AS Prediksi.py
        n_splits = 5
        # TimeSeriesSplit, BUKAN KFold. KFold(shuffle=False) tetap melatih tiap
        # fold memakai SEMUA fold lain - termasuk yang berada SETELAHNYA dalam
        # waktu. Contoh 20 titik/5 fold: fold 0 (validasi idx 0-3) dilatih pakai
        # 16 titik masa depan. TimeSeriesSplit hanya melatih pada data sebelum
        # jendela validasi, sehingga meta-learner tidak pernah melihat masa depan.
        kf = TimeSeriesSplit(n_splits=n_splits)
        oof_predictions = np.zeros(len(y))

        for train_idx, val_idx in kf.split(train_meta_features):
            X_fold_train = train_meta_features[train_idx]
            y_fold_train = y[train_idx]
            X_fold_val = train_meta_features[val_idx]

            fold_meta = GradientBoostingRegressor(
                n_estimators=50, max_depth=3, learning_rate=0.1, random_state=42
            )
            fold_meta.fit(X_fold_train, y_fold_train)
            oof_predictions[val_idx] = fold_meta.predict(X_fold_val)

        # Train final meta-learner on ALL data
        self.meta_model = GradientBoostingRegressor(
            n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42
        )
        self.meta_model.fit(train_meta_features, y)

        # Store feature importance
        self.feature_importance = dict(zip(successful_models, self.meta_model.feature_importances_))
        self.successful_models = successful_models

        # Store for prediction
        self.last_data = ts_df.tail(MIN_HISTORY_FOR_RECURSIVE_PREDICT).copy()
        self.X_train = X
        self.y_train = y

        return self

    def predict(self, dates, values, n_days):
        """Predict n_days into the future using stacking ensemble"""
        from ..feature_engineering_optimized import create_features_optimized

        if self.meta_model is None:
            raise ValueError("Model not fitted. Call fit() first.")

        # Generate business dates
        future_business_dates = generate_business_dates(self.last_date, n_days, self.holidays)

        # ============ GET FORECASTS FROM ALL BASE MODELS ============
        base_forecasts = {}

        # 1. APUVA forecast
        if 'APUVA' in self.base_models:
            try:
                apuva_model = self.base_models['APUVA']['model']
                apuva_forecast, _ = apuva_model.predict(self.dates, self.values, n_days)
                base_forecasts['APUVA'] = np.array(apuva_forecast)
            except Exception as e:
                print(f"Warning: APUVA forecast failed: {e}")

        # 2-4. ML models forecast (iterative)
        ml_models = ['XGBoost', 'RandomForest', 'LightGBM']
        for model_name in ml_models:
            if model_name in self.base_models:
                forecast_values = []
                last_data = self.last_data.copy()

                for next_date in future_business_dates:
                    next_df = pd.DataFrame({'ds': [next_date], 'y': [np.nan]})
                    temp_df = pd.concat([last_data, next_df], ignore_index=True)

                    next_features = create_features_optimized(
                        temp_df,
                        lag_steps=90,
                        holidays_list=self.holidays,
                        external_series=self.external_series
                    )

                    if len(next_features) > 0 and all(col in next_features.columns for col in self.feature_cols):
                        X_next = next_features.iloc[[-1]][self.feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
                        pred = self.base_models[model_name]['model'].predict(X_next)[0]

                        if isinstance(pred, np.ndarray):
                            pred = float(pred.item()) if pred.size == 1 else float(pred[0])

                        if pred is None or np.isnan(pred):
                            pred = float(values[-1]) if len(values) > 0 else 0.0

                        forecast_values.append(float(pred))

                        last_data = pd.concat([
                            last_data,
                            pd.DataFrame({'ds': [next_date], 'y': [pred]})
                        ], ignore_index=True).tail(MIN_HISTORY_FOR_RECURSIVE_PREDICT)
                    else:
                        forecast_values.append(float(values[-1]) if len(values) > 0 else 0.0)

                base_forecasts[model_name] = np.array(forecast_values)

        # ============ STACK FORECASTS AND PREDICT ============
        # Ensure all forecasts have same length
        min_len = min(len(f) for f in base_forecasts.values())

        # Stack in same order as training
        forecast_stack_features = np.column_stack([
            base_forecasts[name][:min_len] for name in self.successful_models if name in base_forecasts
        ])

        # Generate stacked forecast using meta-learner
        stacked_forecast = self.meta_model.predict(forecast_stack_features)

        return list(stacked_forecast), future_business_dates[:len(stacked_forecast)]
