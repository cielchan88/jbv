"""Random Forest forecaster with advanced feature engineering"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from .base import BaseForecaster
from ..feature_engineering_optimized import create_features_optimized as create_features_advanced, select_top_features_optimized as select_top_features, transform_target, inverse_transform_target
from .. import generate_business_dates
from ..feature_config import MIN_HISTORY_FOR_RECURSIVE_PREDICT


class RandomForestForecaster(BaseForecaster):
    """Random Forest forecaster with advanced feature engineering and target transformation"""

    def __init__(self, holidays=None, n_estimators=100, max_depth=10, use_transform=False):
        super().__init__(holidays)
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.use_transform = use_transform
        self.transform_method = 'signed_log' if use_transform else 'none'

    def fit(self, dates, values, external_series=None):
        """Fit Random Forest model with target transformation"""
        # Prepare data - ensure no None/NaN values
        values = np.array(values, dtype=float)
        values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
        ts_df = pd.DataFrame({'ds': pd.to_datetime(dates), 'y': values})

        # Create features with optional cross-series data
        train_features = create_features_advanced(ts_df, lag_steps=90, holidays_list=self.holidays, external_series=external_series)

        if len(train_features) == 0:
            raise ValueError("Not enough data for feature engineering")

        # Select top features
        top_features, _ = select_top_features(train_features, top_k=25)

        # IMPORTANT: Only use features that actually exist in train_features
        available_features = [col for col in train_features.columns if col not in ['ds', 'date', 'value']]

        if len(top_features) > 0:
            # Filter top_features to only include features that exist
            feature_cols = [f for f in top_features if f in available_features]
        else:
            feature_cols = available_features

        # Safety check
        if len(feature_cols) == 0:
            raise ValueError("No features available for training")

        # Train model with TRANSFORMED target
        X_train = train_features[feature_cols]
        y_train_original = train_features['value']
        y_train_transformed = transform_target(y_train_original, method=self.transform_method)

        self.model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            random_state=42,
            n_jobs=-1
        )
        self.model.fit(X_train, y_train_transformed)
        self.feature_cols = feature_cols

        return self

    def predict(self, dates, values, n_days):
        """Predict n_days into the future using business dates with inverse transformation"""
        if self.model is None:
            raise ValueError("Model not fitted. Call fit() first.")

        # Prepare data - ensure no None/NaN values
        values = np.array(values, dtype=float)
        values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
        ts_df = pd.DataFrame({'ds': pd.to_datetime(dates), 'y': values})
        last_data = ts_df.tail(MIN_HISTORY_FOR_RECURSIVE_PREDICT).copy()

        # Generate business dates for forecasting
        future_business_dates = generate_business_dates(last_data['ds'].iloc[-1], n_days, self.holidays)

        forecast_values = []

        for next_date in future_business_dates:
            temp_df = pd.DataFrame({'ds': [next_date], 'y': [0]})
            temp_df = pd.concat([last_data, temp_df], ignore_index=True)
            temp_features = create_features_advanced(temp_df, lag_steps=90, holidays_list=self.holidays)

            if len(temp_features) > 0:
                X_next = temp_features[[col for col in temp_features.columns if col in self.feature_cols]].iloc[-1:]

                for feat in self.feature_cols:
                    if feat not in X_next.columns:
                        X_next[feat] = 0

                X_next = X_next[self.feature_cols]

                # Predict in TRANSFORMED space
                pred_transformed = self.model.predict(X_next)[0]

                # INVERSE transform back to original scale
                pred = inverse_transform_target(pred_transformed, method=self.transform_method)

                # Convert numpy array to scalar float
                if isinstance(pred, np.ndarray):
                    pred = float(pred.item()) if pred.size == 1 else float(pred[0])

                # Safety check: ensure pred is not None or NaN
                if pred is None or np.isnan(pred):
                    pred = float(values[-1]) if len(values) > 0 else 0.0

                forecast_values.append(float(pred))

                last_data = pd.concat([
                    last_data,
                    pd.DataFrame({'ds': [next_date], 'y': [pred]})
                ], ignore_index=True).tail(MIN_HISTORY_FOR_RECURSIVE_PREDICT)
            else:
                forecast_values.append(values[-1])

        return forecast_values, future_business_dates
