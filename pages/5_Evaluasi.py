import streamlit as st
import warnings
import logging

# Suppress deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*keyword arguments have been deprecated.*')

# Suppress Prophet and CmdStan verbose logging
logging.getLogger('prophet').setLevel(logging.WARNING)
logging.getLogger('cmdstanpy').setLevel(logging.WARNING)

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from lightgbm import LGBMRegressor
from sklearn.ensemble import RandomForestRegressor
import xgboost as xgb
from prophet import Prophet
import json
import os
import warnings
warnings.filterwarnings('ignore')

# Page config
st.set_page_config(page_title="Evaluasi - JBV Dashboard", layout="wide")

# Import utils
from utils import load_holidays, generate_business_dates, ML_START_DATE
from utils.data_loader import load_etl_output, parse_children

# Title
st.title("📊 Evaluasi Model")
st.markdown("Bandingkan performa 8 model untuk semua leaf nodes.")

st.divider()

# Load ETL output data (NOT raw processed data!)
@st.cache_data
def load_evaluation_data():
    df, metadata_cols, time_cols = load_etl_output()

    # Get leaf nodes (nodes without children)
    leaf_nodes_df = df[df['Children'].apply(lambda x: len(parse_children(x))) == 0].copy()
    leaf_nodes = leaf_nodes_df['Row_ID'].tolist()

    # Add category info
    def get_category(row_id):
        if row_id.startswith('A'):
            return 'KORPORASI'
        elif row_id.startswith('B'):
            return 'INDIVIDU'
        elif row_id.startswith('C'):
            return 'NON RESIDEN'
        return 'LAINNYA'

    # Add sub-category info (same as Prediksi.py)
    def get_subcategory(row_id):
        if row_id.startswith('A.1'):
            return 'PTMN'
        elif row_id.startswith('A.2'):
            return 'Korporasi Lainnya'
        return '-'

    leaf_nodes_df['Category'] = leaf_nodes_df['Row_ID'].apply(get_category)
    leaf_nodes_df['Sub_Category'] = leaf_nodes_df['Row_ID'].apply(get_subcategory)

    return df, metadata_cols, time_cols, leaf_nodes, leaf_nodes_df

df, metadata_cols, time_cols, leaf_nodes, leaf_nodes_df = load_evaluation_data()

st.info(f"📊 Total **{len(leaf_nodes)}** leaf nodes tersedia untuk evaluasi")

# Sidebar configuration
st.sidebar.header("⚙️ Pengaturan Evaluasi")

# Test size
test_size = st.sidebar.slider(
    "Ukuran Data Test (%)",
    min_value=10,
    max_value=40,
    value=20,
    step=5
)

# Batas horizon evaluasi.
# Dengan histori penuh (~5000 hari), test 20% = ~1000 hari. Mengevaluasi forecast
# 1000 hari ke depan itu (a) sangat lambat, dan (b) tidak mencerminkan cara model
# dipakai - Lembar Kerja defaultnya forecast 30 hari. Membatasi horizon membuat
# metrik evaluasi selaras dengan horizon pemakaian nyata sekaligus jauh lebih cepat.
limit_horizon = st.sidebar.checkbox(
    "Batasi horizon evaluasi", value=True,
    help="Evaluasi hanya N hari pertama dari periode test, bukan seluruhnya"
)
eval_horizon = None
if limit_horizon:
    eval_horizon = st.sidebar.number_input(
        "Horizon evaluasi (hari)", min_value=7, max_value=365, value=60, step=7,
        help="Samakan dengan horizon forecast yang biasa dipakai di Lembar Kerja"
    )

# Model selection
st.sidebar.markdown("---")
st.sidebar.subheader("🤖 Pilih Model")

# Available models with checkboxes in sidebar
all_models = ["APUVA", "Prophet", "RandomForest", "LightGBM", "XGBoost", "AutoARIMA", "VAR", "Stacking"]

selected_models = []
if st.sidebar.checkbox("APUVA", value=True, key="model_apuva"):
    selected_models.append("APUVA")
if st.sidebar.checkbox("Prophet", value=True, key="model_prophet"):
    selected_models.append("Prophet")
if st.sidebar.checkbox("RandomForest", value=True, key="model_rf"):
    selected_models.append("RandomForest")
if st.sidebar.checkbox("LightGBM", value=True, key="model_lgbm"):
    selected_models.append("LightGBM")
if st.sidebar.checkbox("XGBoost", value=True, key="model_xgb"):
    selected_models.append("XGBoost")
if st.sidebar.checkbox("AutoARIMA", value=True, key="model_arima"):
    selected_models.append("AutoARIMA")
if st.sidebar.checkbox("VAR", value=True, key="model_var"):
    selected_models.append("VAR")
if st.sidebar.checkbox("Stacking", value=True, key="model_stack"):
    selected_models.append("Stacking")

# Warning if no model selected
if len(selected_models) == 0:
    st.sidebar.warning("⚠️ Pilih minimal 1 model")

# Pilihan subset leaf node - supaya evaluasi bisa dijalankan bertahap
# (sekali jalan untuk semua leaf node bisa makan puluhan menit dan berisiko
# putus koneksi sebelum selesai).
st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Cakupan Leaf Node")
evaluate_all = st.sidebar.checkbox("Evaluasi semua leaf node", value=True)
if evaluate_all:
    leaf_nodes_to_run = leaf_nodes
else:
    leaf_nodes_to_run = st.sidebar.multiselect(
        "Pilih leaf node:",
        options=leaf_nodes,
        default=leaf_nodes[:5],
        help="Jalankan sebagian dulu supaya prosesnya lebih pendek, lalu lanjutkan sisanya"
    )
    if len(leaf_nodes_to_run) == 0:
        st.sidebar.warning("⚠️ Pilih minimal 1 leaf node")

# Metric selection for best model
st.sidebar.markdown("---")
st.sidebar.subheader("📊 Metric Acuan")
selection_metric = st.sidebar.selectbox(
    "Pilih metric untuk best model",
    options=['SMAPE', 'MAE', 'RMSE', 'MAPE', 'DA'],
    index=0,
    help="Metric yang digunakan untuk memilih model terbaik per leaf node"
)

# Explain metric direction
metric_info = {
    'SMAPE': "Symmetric MAPE (0-200%). Lebih robust terhadap nilai kecil. Lower is better.",
    'MAE': "Mean Absolute Error. Satuan sama dengan data asli. Lower is better.",
    'RMSE': "Root Mean Squared Error. Sensitif terhadap outlier. Lower is better.",
    'MAPE': "Mean Absolute Percentage Error. Bisa inf jika actual=0. Lower is better.",
    'DA': "Directional Accuracy (%). Seberapa akurat prediksi arah. Higher is better."
}
st.sidebar.caption(f"ℹ️ {metric_info[selection_metric]}")

# Run evaluation button
st.sidebar.markdown("---")
run_comparison = st.sidebar.button("🚀 Jalankan Evaluasi", type="primary")

# Check if we have previous results in session state
has_results = 'evaluation_results' in st.session_state and st.session_state['evaluation_results'] is not None

# Main evaluation logic
if run_comparison and len(selected_models) > 0 and len(leaf_nodes_to_run) > 0:

    # Load holidays
    holidays_list = load_holidays()

    # ========================================================================
    # PREPARE CROSS-SERIES DATA FOR ALL LEAF NODES (SAME AS Lembar_Kerja.py)
    # ========================================================================

    with st.spinner("🔍 Calculating cross-series correlations for all leaf nodes..."):
        from utils.feature_engineering_optimized import (
            calculate_series_correlations,
            select_top_correlated_series,
            prepare_external_series_data
        )

        @st.cache_data
        def prepare_cross_series_data(df, leaf_nodes, time_cols, target_leaves=None):
            """
            Prepare cross-series correlation data - SAME AS Lembar_Kerja.py

            target_leaves: leaf node yang benar-benar akan dievaluasi. Kandidat
            korelasinya tetap SELURUH leaf_nodes (supaya fiturnya identik dengan
            evaluasi penuh), tapi peta hanya dihitung untuk leaf yang dipakai -
            menghindari komputasi sia-sia saat user hanya menjalankan sebagian.
            """
            cross_series_map = {}
            if target_leaves is None:
                target_leaves = leaf_nodes

            # Filter to 2019+ for ML models with external features (SAME AS Prediksi.py & Lembar_Kerja.py)
            if ML_START_DATE is not None:
                time_cols_ml = [col for col in time_cols if pd.to_datetime(col) >= pd.Timestamp(ML_START_DATE)]
            else:
                time_cols_ml = time_cols  # ML pakai histori penuh yang sama dengan ETL/APUVA

            for leaf_id in target_leaves:
                # 1. Get all other leaf nodes (exclude current series)
                candidate_series = [lid for lid in leaf_nodes if lid != leaf_id]

                # 2. Calculate correlations with ALL other leaf nodes (using 2019+ data)
                correlations = calculate_series_correlations(df, leaf_id, candidate_series, time_cols_ml)

                # 3. Select top 30 correlated series
                top_30_series = select_top_correlated_series(correlations, top_k=30)

                # 4. Prepare external series data (cross-series only) - using 2019+ data
                cross_series_only = prepare_external_series_data(df, top_30_series, time_cols_ml)

                # 5. Merge with external features from Excel
                from utils.external_loader import load_and_merge_external_features
                external_series_data = load_and_merge_external_features(cross_series_only, time_cols_ml)

                cross_series_map[leaf_id] = external_series_data

            return cross_series_map

        cross_series_map = prepare_cross_series_data(df, leaf_nodes, time_cols, tuple(leaf_nodes_to_run))
        st.success(f"✅ Cross-series correlations calculated for {len(cross_series_map)} leaf nodes")

    # Display data range information (SAME AS Prediksi.py)
    if ML_START_DATE is not None:
        time_cols_ml = [col for col in time_cols if pd.to_datetime(col) >= pd.Timestamp(ML_START_DATE)]
    else:
        time_cols_ml = time_cols  # ML pakai histori penuh yang sama dengan ETL/APUVA
    st.info(f"📊 **ML Models (XGBoost, RF, LightGBM, Prophet)**: {time_cols_ml[0]} to {time_cols_ml[-1]} ({len(time_cols_ml)} days)")
    st.info(f"📊 **APUVA**: {time_cols[0]} to {time_cols[-1]} ({len(time_cols)} days) - Full historical data for year-over-year calculations")

    # Progress tracking
    st.subheader("⚙️ Running Model Evaluation...")
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Evaluate all leaf nodes for SELECTED models
    # IMPORTANT: Evaluate base models first, then Stacking uses their predictions
    all_results = []
    base_models = ["APUVA", "Prophet", "RandomForest", "LightGBM", "XGBoost", "AutoARIMA", "VAR"]
    # Filter base models to only selected ones
    active_base_models = [m for m in base_models if m in selected_models]
    total_steps = len(leaf_nodes_to_run) * len(selected_models)
    current_step = 0

    for leaf_id in leaf_nodes_to_run:
        # Get historical values
        leaf_row = df[df['Row_ID'] == leaf_id]
        if len(leaf_row) == 0:
            continue

        values = leaf_row[time_cols].values.flatten()

        # Get metadata
        row_label = leaf_row['Row_Label'].values[0]
        category = 'KORPORASI' if leaf_id.startswith('A') else ('INDIVIDU' if leaf_id.startswith('B') else 'NON RESIDEN')
        # Get sub-category (same logic as Prediksi.py)
        if leaf_id.startswith('A.1'):
            sub_category = 'PTMN'
        elif leaf_id.startswith('A.2'):
            sub_category = 'Korporasi Lainnya'
        else:
            sub_category = '-'

        # Get external series for this leaf node
        external_series_data = cross_series_map.get(leaf_id, {})

        # ========================================================================
        # DATA PREPARATION - EXACTLY SAME AS Prediksi.py lines 130-166
        # Do this ONCE per leaf node, then use for all models
        # ========================================================================

        # Clean values (SAME AS Prediksi.py line 134-135)
        values_clean = np.array(values, dtype=float)
        values_clean = np.nan_to_num(values_clean, nan=0.0, posinf=0.0, neginf=0.0)

        # Get FULL data for APUVA (SAME AS Prediksi.py line 130-136)
        values_full = values_clean
        dates_full = pd.to_datetime(time_cols)

        # Get FILTERED data for ML models (SAME AS Prediksi.py line 138-144)
        values_ml = values_clean[-len(time_cols_ml):]
        dates_ml = pd.to_datetime(time_cols_ml)

        # Create time series dataframe for ML models (SAME AS Prediksi.py line 146-150)
        ts_df_ml = pd.DataFrame({'date': dates_ml, 'value': values_ml})

        # Create time series dataframe for APUVA (SAME AS Prediksi.py line 152-156)
        ts_df_apuva = pd.DataFrame({'date': dates_full, 'value': values_full})

        # Train/test split for ML models (SAME AS Prediksi.py line 158-161)
        split_idx_ml = int(len(ts_df_ml) * (1 - test_size/100))
        train_ml = ts_df_ml.iloc[:split_idx_ml]
        test_ml = ts_df_ml.iloc[split_idx_ml:]

        # Train/test split for APUVA (SAME AS Prediksi.py line 163-166)
        split_idx_apuva = int(len(ts_df_apuva) * (1 - test_size/100))
        train_apuva = ts_df_apuva.iloc[:split_idx_apuva]
        test_apuva = ts_df_apuva.iloc[split_idx_apuva:]

        # Potong horizon test kalau dibatasi - training tetap utuh, hanya periode
        # yang dievaluasi yang dipotong (lihat catatan di sidebar).
        if eval_horizon is not None:
            test_ml = test_ml.iloc[:int(eval_horizon)]
            test_apuva = test_apuva.iloc[:int(eval_horizon)]

        # Skip if test data too small
        if len(test_ml) < 5 or len(test_apuva) < 5:
            current_step += len(selected_models)
            progress_bar.progress(min(current_step / total_steps, 1.0))
            continue

        # ========================================================================
        # FEATURE ENGINEERING - EXACTLY SAME AS Prediksi.py lines 208-253
        # Do this ONCE per leaf node, then use for all ML models
        # ========================================================================

        from utils.feature_engineering_optimized import create_features_optimized, select_top_features_optimized

        # Hitung fitur SEKALI pada deret utuh (train + test menyambung), baru
        # di-split berdasarkan tanggal.
        #
        # Sebelumnya fitur dihitung terpisah untuk train dan test. Itu salah
        # karena create_features_optimized() membangun lag/rolling DARI DALAM
        # dataframe yang diberikan: potongan test tidak punya histori sebelum
        # titik awalnya, sehingga fitur window panjang (rolling_mean_90 dst.)
        # tidak bisa dihitung sama sekali (butuh window*3 baris) atau dihitung
        # dari sampel yang "restart" - tidak sama dengan yang dilihat model saat
        # training. Makin pendek horizon evaluasi, makin parah efeknya.
        full_fe = pd.concat([train_ml, test_ml], ignore_index=True).rename(
            columns={'date': 'ds', 'value': 'y'}
        )
        full_features = create_features_optimized(
            full_fe, lag_steps=90, holidays_list=holidays_list,
            external_series=external_series_data, external_series_dates=dates_ml
        )

        split_date = test_ml['date'].iloc[0]
        train_features = full_features[full_features['date'] < split_date].copy()
        test_features = full_features[full_features['date'] >= split_date].copy()

        # Get common features (SAME AS Prediksi.py line 220-222)
        train_available = [col for col in train_features.columns if col not in ['ds', 'date', 'value']]
        test_available = [col for col in test_features.columns if col not in ['ds', 'date', 'value']]
        common_features = list(set(train_available) & set(test_available))

        # Select top 25 features ONCE (SAME AS Prediksi.py line 225-232)
        if len(common_features) > 0:
            top_features, _ = select_top_features_optimized(train_features, top_k=25)
            feature_cols = [f for f in top_features if f in common_features]
            if len(feature_cols) == 0:
                feature_cols = common_features[:25]

            # Prepare X, y ONCE (SAME AS Prediksi.py line 235-238)
            X_train = train_features[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
            y_train = train_features['value']
            X_test = test_features[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
            y_test = test_features['value']
        else:
            feature_cols = []
            X_train = X_test = y_train = y_test = None

        # ========================================================================
        # EVALUATE ALL MODELS - Using prepared data
        # ========================================================================

        # Store predictions for Stacking (same as Prediksi.py approach)
        leaf_predictions = {}
        leaf_actual_ml = test_ml['value'].values  # For ML models
        leaf_actual_apuva = test_apuva['value'].values  # For APUVA

        # Dictionary to store results like Prediksi.py
        results = {}

        # --- MODEL 1: APUVA (uses full data) ---
        if "APUVA" in selected_models:
            status_text.text(f"Evaluating {leaf_id} with APUVA... ({current_step+1}/{total_steps})")
            try:
                from utils.forecasting import APUVAForecaster
                apuva_model = APUVAForecaster(holidays=holidays_list, row_id=leaf_id)
                apuva_model.fit(train_apuva['date'].dt.strftime('%Y-%m-%d').tolist(), train_apuva['value'].values)
                predictions_apuva, _ = apuva_model.predict(
                    train_apuva['date'].dt.strftime('%Y-%m-%d').tolist(),
                    train_apuva['value'].values,
                    len(test_apuva)
                )
                predictions_apuva = np.array(predictions_apuva)
                results['APUVA'] = {'success': True, 'predictions_test': predictions_apuva}
                leaf_predictions['APUVA'] = predictions_apuva
            except:
                results['APUVA'] = {'success': False}
            current_step += 1
            progress_bar.progress(min(current_step / total_steps, 1.0))

        # --- MODEL 2: Prophet (uses ML data) ---
        if "Prophet" in selected_models:
            status_text.text(f"Evaluating {leaf_id} with Prophet... ({current_step+1}/{total_steps})")
            try:
                train_prophet = train_ml.rename(columns={'date': 'ds', 'value': 'y'})
                test_prophet = test_ml.rename(columns={'date': 'ds', 'value': 'y'})
                model_prophet = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False, changepoint_prior_scale=0.05)
                model_prophet.fit(train_prophet)
                test_forecast = model_prophet.predict(test_prophet[['ds']])
                predictions_prophet = test_forecast['yhat'].values
                results['Prophet'] = {'success': True, 'predictions_test': predictions_prophet}
                leaf_predictions['Prophet'] = predictions_prophet
            except:
                results['Prophet'] = {'success': False}
            current_step += 1
            progress_bar.progress(min(current_step / total_steps, 1.0))

        # --- MODEL 3-5: ML Models (use shared features) ---
        if X_train is not None and len(feature_cols) > 0:
            # RandomForest
            if "RandomForest" in selected_models:
                status_text.text(f"Evaluating {leaf_id} with RandomForest... ({current_step+1}/{total_steps})")
                try:
                    rf_model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
                    rf_model.fit(X_train, y_train)
                    predictions_rf = rf_model.predict(X_test)
                    results['RandomForest'] = {'success': True, 'predictions_test': predictions_rf, 'test_dates': test_features['ds'].values}
                    leaf_predictions['RandomForest'] = predictions_rf
                except:
                    results['RandomForest'] = {'success': False}
                current_step += 1
                progress_bar.progress(min(current_step / total_steps, 1.0))

            # LightGBM
            if "LightGBM" in selected_models:
                status_text.text(f"Evaluating {leaf_id} with LightGBM... ({current_step+1}/{total_steps})")
                try:
                    lgb_model = LGBMRegressor(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, verbose=-1)
                    lgb_model.fit(X_train, y_train)
                    predictions_lgb = lgb_model.predict(X_test)
                    results['LightGBM'] = {'success': True, 'predictions_test': predictions_lgb, 'test_dates': test_features['ds'].values}
                    leaf_predictions['LightGBM'] = predictions_lgb
                except:
                    results['LightGBM'] = {'success': False}
                current_step += 1
                progress_bar.progress(min(current_step / total_steps, 1.0))

            # XGBoost
            if "XGBoost" in selected_models:
                status_text.text(f"Evaluating {leaf_id} with XGBoost... ({current_step+1}/{total_steps})")
                try:
                    xgb_model = xgb.XGBRegressor(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, verbosity=0)
                    xgb_model.fit(X_train, y_train, verbose=False)
                    predictions_xgb = xgb_model.predict(X_test)
                    results['XGBoost'] = {'success': True, 'predictions_test': predictions_xgb, 'test_dates': test_features['ds'].values}
                    leaf_predictions['XGBoost'] = predictions_xgb
                except:
                    results['XGBoost'] = {'success': False}
                current_step += 1
                progress_bar.progress(min(current_step / total_steps, 1.0))

        # --- MODEL 6: AutoARIMA (uses ML data) ---
        if "AutoARIMA" in selected_models:
            status_text.text(f"Evaluating {leaf_id} with AutoARIMA... ({current_step+1}/{total_steps})")
            try:
                from utils.forecasting import ARIMAForecaster
                arima_model = ARIMAForecaster()
                arima_model.fit(train_ml['date'].dt.strftime('%Y-%m-%d').tolist(), train_ml['value'].values)
                predictions_arima, _ = arima_model.predict(
                    train_ml['date'].dt.strftime('%Y-%m-%d').tolist(),
                    train_ml['value'].values,
                    len(test_ml)
                )
                predictions_arima = np.array(predictions_arima)
                results['AutoARIMA'] = {'success': True, 'predictions_test': predictions_arima}
                leaf_predictions['AutoARIMA'] = predictions_arima
            except:
                results['AutoARIMA'] = {'success': False}
            current_step += 1
            progress_bar.progress(min(current_step / total_steps, 1.0))

        # --- MODEL 7: VAR (uses ML data with external series) ---
        if "VAR" in selected_models:
            status_text.text(f"Evaluating {leaf_id} with VAR... ({current_step+1}/{total_steps})")
            try:
                from utils.forecasting import VARForecaster
                var_model = VARForecaster()
                var_model.fit(
                    train_ml['date'].dt.strftime('%Y-%m-%d').tolist(),
                    train_ml['value'].values,
                    external_series=external_series_data
                )
                predictions_var, _ = var_model.predict(
                    train_ml['date'].dt.strftime('%Y-%m-%d').tolist(),
                    train_ml['value'].values,
                    len(test_ml)
                )
                predictions_var = np.array(predictions_var)
                results['VAR'] = {'success': True, 'predictions_test': predictions_var}
                leaf_predictions['VAR'] = predictions_var
            except Exception as e:
                # print(f"VAR failed for {leaf_id}: {str(e)}")  # Debug only
                results['VAR'] = {'success': False}
            current_step += 1
            progress_bar.progress(min(current_step / total_steps, 1.0))

        # ========================================================================
        # CALCULATE METRICS - EXACTLY SAME AS Prediksi.py lines 711-779
        # ========================================================================

        def calculate_metrics(actual, predictions):
            """Calculate all metrics - same formula as Prediksi.py"""
            min_len = min(len(actual), len(predictions))
            actual = np.array(actual[:min_len])
            predictions = np.array(predictions[:min_len])

            mae = mean_absolute_error(actual, predictions)
            rmse = np.sqrt(mean_squared_error(actual, predictions))

            non_zero_mask = actual != 0
            if non_zero_mask.sum() > 0:
                mape = np.mean(np.abs((actual[non_zero_mask] - predictions[non_zero_mask]) / actual[non_zero_mask])) * 100
            else:
                mape = np.nan

            r2 = r2_score(actual, predictions)
            smape = np.mean(np.abs(predictions - actual) / ((np.abs(actual) + np.abs(predictions)) / 2 + 1e-8)) * 100

            if len(actual) > 1:
                actual_change = actual[1:] - actual[:-1]
                pred_change = predictions[1:] - predictions[:-1]
                correct_direction = np.sign(actual_change) == np.sign(pred_change)
                da = np.mean(correct_direction) * 100
            else:
                da = np.nan

            bias = np.mean(predictions - actual)

            return {'MAE': mae, 'RMSE': rmse, 'MAPE': mape, 'SMAPE': smape, 'R²': r2, 'DA': da, 'Bias': bias}

        # Calculate metrics for each model (SAME AS Prediksi.py lines 711-779)
        for model_name, result in results.items():
            if result.get('success'):
                # APUVA uses full test data, ML models use ML test data (SAME AS Prediksi.py line 714-718)
                if model_name == 'APUVA':
                    actual = leaf_actual_apuva
                else:
                    actual = leaf_actual_ml

                predictions = result['predictions_test']

                # Handle models which might have different length (SAME AS Prediksi.py line 722-724)
                if model_name in ['XGBoost', 'LightGBM', 'RandomForest'] and 'test_dates' in result:
                    actual = actual[-len(predictions):]

                metrics = calculate_metrics(actual, predictions)
                metrics['Row_ID'] = leaf_id
                metrics['Row_Label'] = row_label
                metrics['Category'] = category
                metrics['Sub_Category'] = sub_category
                metrics['Model'] = model_name
                metrics['predictions'] = predictions
                metrics['actual'] = actual
                all_results.append(metrics)

        # ========================================================================
        # STACKING - EXACTLY SAME AS Prediksi.py lines 586-699
        # ========================================================================
        if "Stacking" in selected_models:
            status_text.text(f"Evaluating {leaf_id} with Stacking... ({current_step+1}/{total_steps})")

            # Stacking requires at least 2 successful base models (excluding Prophet)
            stacking_base_models = ['APUVA', 'RandomForest', 'LightGBM', 'XGBoost', 'AutoARIMA', 'VAR']
            successful_models_stack = [m for m in stacking_base_models if results.get(m, {}).get('success')]

            if len(successful_models_stack) >= 2:
                try:
                    from sklearn.ensemble import GradientBoostingRegressor
                    from sklearn.model_selection import KFold

                    # Find shortest prediction length (align like Prediksi.py line 598-603)
                    ml_models_stack = [m for m in successful_models_stack if m != 'APUVA']
                    if ml_models_stack:
                        min_len = min(len(results[m]['predictions_test']) for m in ml_models_stack)
                    else:
                        min_len = len(results['APUVA']['predictions_test'])

                    # Align all predictions to same length (SAME AS Prediksi.py line 605-613)
                    aligned_preds = {}
                    for model in successful_models_stack:
                        pred = results[model]['predictions_test']
                        if model == 'APUVA':
                            aligned_preds[model] = np.array(pred[-min_len:])
                        else:
                            aligned_preds[model] = np.array(pred[-min_len:])

                    # Get actual values aligned (SAME AS Prediksi.py line 616)
                    y_actual_stack = leaf_actual_ml[-min_len:]

                    # Stack predictions as features (SAME AS Prediksi.py line 619)
                    X_stack = np.column_stack([aligned_preds[m] for m in successful_models_stack])

                    # KFold cross-validation for OOF predictions (same as Prediksi.py)
                    n_splits = min(5, len(y_actual_stack) // 2)  # Ensure enough samples per fold
                    if n_splits >= 2:
                        kf = KFold(n_splits=n_splits, shuffle=False)
                        oof_predictions = np.zeros(len(y_actual_stack))

                        for train_idx, val_idx in kf.split(X_stack):
                            X_fold_train, X_fold_val = X_stack[train_idx], X_stack[val_idx]
                            y_fold_train = y_actual_stack[train_idx]

                            fold_meta = GradientBoostingRegressor(
                                n_estimators=50, max_depth=3, learning_rate=0.1, random_state=42
                            )
                            fold_meta.fit(X_fold_train, y_fold_train)
                            oof_predictions[val_idx] = fold_meta.predict(X_fold_val)

                        # Use OOF predictions as test predictions (same as Prediksi.py line 654)
                        predictions_stack = oof_predictions
                        actual_stack = y_actual_stack

                        # Calculate metrics for Stacking
                        mae = mean_absolute_error(actual_stack, predictions_stack)
                        rmse = np.sqrt(mean_squared_error(actual_stack, predictions_stack))

                        non_zero_mask = actual_stack != 0
                        if non_zero_mask.sum() > 0:
                            mape = np.mean(np.abs((actual_stack[non_zero_mask] - predictions_stack[non_zero_mask]) / actual_stack[non_zero_mask])) * 100
                        else:
                            mape = np.nan

                        r2 = r2_score(actual_stack, predictions_stack)
                        smape = np.mean(np.abs(predictions_stack - actual_stack) / ((np.abs(actual_stack) + np.abs(predictions_stack)) / 2 + 1e-8)) * 100

                        if len(actual_stack) > 1:
                            actual_change = actual_stack[1:] - actual_stack[:-1]
                            pred_change = predictions_stack[1:] - predictions_stack[:-1]
                            correct_direction = np.sign(actual_change) == np.sign(pred_change)
                            da = np.mean(correct_direction) * 100
                        else:
                            da = np.nan

                        bias = np.mean(predictions_stack - actual_stack)

                        stacking_result = {
                            'Row_ID': leaf_id,
                            'Row_Label': row_label,
                            'Category': category,
                            'Sub_Category': sub_category,
                            'Model': 'Stacking',
                            'MAE': mae,
                            'RMSE': rmse,
                            'MAPE': mape,
                            'SMAPE': smape,
                            'R²': r2,
                            'DA': da,
                            'Bias': bias,
                            'predictions': predictions_stack,
                            'actual': actual_stack
                        }
                        all_results.append(stacking_result)

                except Exception as e:
                    pass  # Stacking failed for this leaf node

            current_step += 1
            progress_bar.progress(current_step / total_steps)

    progress_bar.progress(1.0)
    status_text.text("✅ Evaluation completed!")

    if len(all_results) == 0:
        st.error("❌ No results generated. Please try different settings.")
        st.stop()

    # Convert to DataFrame
    results_df = pd.DataFrame(all_results)

    # Store results in session state
    st.session_state['evaluation_results'] = results_df
    st.session_state['evaluation_test_size'] = test_size
    st.session_state['evaluation_metric'] = selection_metric

    st.success(f"✅ Successfully evaluated {len(selected_models)} models on {len(leaf_nodes_to_run)} leaf nodes!")

    # ========================================================================
    # SECTION 1: OVERALL MODEL PERFORMANCE (same format as Prediksi.py)
    # ========================================================================
    st.subheader("🏆 Overall Model Performance")

    # Aggregate by model - same metrics as Prediksi.py
    model_summary = results_df.groupby('Model').agg({
        'MAE': 'mean',
        'RMSE': 'mean',
        'MAPE': 'mean',
        'SMAPE': 'mean',
        'R²': 'mean',
        'DA': 'mean',
        'Bias': 'mean',
        'Row_ID': 'count'
    }).rename(columns={'Row_ID': 'Count'})

    # Sort by model order (filter to only selected models)
    model_order = [m for m in ['Stacking', 'APUVA', 'Prophet', 'RandomForest', 'LightGBM', 'XGBoost', 'AutoARIMA', 'VAR'] if m in selected_models]
    model_summary = model_summary.reindex([m for m in model_order if m in model_summary.index]).reset_index()
    model_summary = model_summary.round(2)

    # Calculate "Best Combination" - metrics if each leaf uses its best model (by selected metric)
    # DA uses idxmax (higher is better), others use idxmin (lower is better)
    if selection_metric == 'DA':
        best_per_leaf = results_df.loc[results_df.groupby('Row_ID')[selection_metric].idxmax()]
    else:
        best_per_leaf = results_df.loc[results_df.groupby('Row_ID')[selection_metric].idxmin()]
    best_combination = {
        'Model': '⭐ Best Combination',
        'MAE': best_per_leaf['MAE'].mean(),
        'RMSE': best_per_leaf['RMSE'].mean(),
        'MAPE': best_per_leaf['MAPE'].mean(),
        'SMAPE': best_per_leaf['SMAPE'].mean(),
        'R²': best_per_leaf['R²'].mean(),
        'DA': best_per_leaf['DA'].mean(),
        'Bias': best_per_leaf['Bias'].mean(),
        'Count': len(best_per_leaf)
    }

    # Add Best Combination as first row
    best_combination_df = pd.DataFrame([best_combination])
    model_summary = pd.concat([best_combination_df, model_summary], ignore_index=True)
    model_summary = model_summary.round(2)

    # Display as simple table (same as Prediksi.py)
    st.markdown("### 📋 Metrics Comparison (Average across all leaf nodes)")
    st.markdown(f"*⭐ Best Combination = setiap leaf node menggunakan model terbaik (by {selection_metric})*")
    st.dataframe(model_summary, use_container_width=True, hide_index=True)

    # ========================================================================
    # SECTION 2: BEST MODEL PER LEAF NODE
    # ========================================================================
    st.subheader(f"🎯 Best Model per Leaf Node (by {selection_metric})")

    # Find best model for each leaf node
    # DA uses idxmax (higher is better), others use idxmin (lower is better)
    results_clean = results_df.dropna(subset=[selection_metric]).copy()

    if len(results_clean) > 0:
        if selection_metric == 'DA':
            best_models = results_clean.loc[results_clean.groupby('Row_ID')[selection_metric].idxmax()]
        else:
            best_models = results_clean.loc[results_clean.groupby('Row_ID')[selection_metric].idxmin()]
        best_models = best_models[['Row_ID', 'Row_Label', 'Category', 'Sub_Category', 'Model', selection_metric, 'R²']].sort_values('Row_ID')
        best_model_counts = best_models['Model'].value_counts()
    else:
        st.warning(f"⚠️ No valid {selection_metric} values to determine best models")
        best_models = pd.DataFrame()
        best_model_counts = pd.Series()

    if len(best_models) > 0:
        st.markdown("### 🏅 Best Model Frequency")
        cols = st.columns(min(8, len(model_order)))
        for idx, model in enumerate(model_order):
            if model in best_model_counts.index:
                count = best_model_counts[model]
                percentage = (count / len(best_models)) * 100
                with cols[idx % len(cols)]:
                    st.metric(model, f"{count} nodes", f"{percentage:.1f}%")

    # Store best_models in session state for later use
    if len(best_models) > 0:
        st.session_state['best_models_df'] = best_models

    # ========================================================================
    # SECTION 3: DETAILED COMPARISON TABLE
    # ========================================================================
    st.subheader("📋 Detailed Results (All Models)")

    # Add filter
    col1, col2 = st.columns(2)
    with col1:
        filter_category = st.multiselect(
            "Filter by Category",
            options=results_df['Category'].unique().tolist(),
            default=results_df['Category'].unique().tolist(),
            key="filter_cat_detailed"
        )

    with col2:
        available_models = results_df['Model'].unique().tolist()
        filter_model = st.multiselect(
            "Filter by Model",
            options=available_models,
            default=available_models,
            key="filter_model_detailed"
        )

    # Filter data
    filtered_results = results_df[
        (results_df['Category'].isin(filter_category)) &
        (results_df['Model'].isin(filter_model))
    ].copy()

    # Sort by Row_ID and Model
    filtered_results = filtered_results.sort_values(['Row_ID', 'Model'])

    # Display table
    display_cols = ['Row_ID', 'Row_Label', 'Category', 'Sub_Category', 'Model', 'MAE', 'RMSE', 'MAPE', 'SMAPE', 'R²', 'DA', 'Bias']
    st.dataframe(
        filtered_results[display_cols].round(2),
        use_container_width=True,
        height=600
    )

    # ========================================================================
    # SECTION 5: DOWNLOAD RESULTS
    # ========================================================================
    st.subheader("📥 Download Evaluation Results")

    # Feature description helper (same as Prediksi.py)
    def get_feature_descriptions():
        """Generate feature description reference table"""
        descriptions = [
            # Historis
            {'Tipe': 'Historis', 'Pattern': 'lag_N', 'Penjelasan': 'Nilai aktual N hari kerja yang lalu, menangkap pola jangka pendek'},
            # Statistik
            {'Tipe': 'Statistik', 'Pattern': 'rolling_mean_N', 'Penjelasan': 'Rata-rata bergerak N hari terakhir, menghaluskan fluktuasi harian'},
            {'Tipe': 'Statistik', 'Pattern': 'rolling_std_N', 'Penjelasan': 'Standar deviasi N hari terakhir, mengukur tingkat volatilitas'},
            {'Tipe': 'Statistik', 'Pattern': 'rolling_max_N', 'Penjelasan': 'Nilai tertinggi dalam N hari terakhir, mendeteksi puncak lokal'},
            {'Tipe': 'Statistik', 'Pattern': 'rolling_min_N', 'Penjelasan': 'Nilai terendah dalam N hari terakhir, mendeteksi lembah lokal'},
            {'Tipe': 'Statistik', 'Pattern': 'ewm_N', 'Penjelasan': 'Rata-rata eksponensial N hari, memberi bobot lebih pada data terbaru'},
            {'Tipe': 'Statistik', 'Pattern': 'ewm_std_N', 'Penjelasan': 'Volatilitas eksponensial N hari, lebih responsif terhadap perubahan terkini'},
            # Teknikal
            {'Tipe': 'Teknikal', 'Pattern': 'bb_middle_N', 'Penjelasan': 'Garis tengah Bollinger Band (SMA N hari), basis untuk mengukur deviasi'},
            {'Tipe': 'Teknikal', 'Pattern': 'bb_upper_N', 'Penjelasan': 'Batas atas Bollinger Band, sinyal potensi overbought'},
            {'Tipe': 'Teknikal', 'Pattern': 'bb_lower_N', 'Penjelasan': 'Batas bawah Bollinger Band, sinyal potensi oversold'},
            {'Tipe': 'Teknikal', 'Pattern': 'bb_width_N', 'Penjelasan': 'Lebar Bollinger Band, indikator ekspansi/kontraksi volatilitas'},
            {'Tipe': 'Teknikal', 'Pattern': 'macd', 'Penjelasan': 'Moving Average Convergence Divergence, mengukur momentum dan arah tren'},
            {'Tipe': 'Teknikal', 'Pattern': 'macd_signal', 'Penjelasan': 'Signal line MACD, digunakan untuk sinyal buy/sell crossover'},
            {'Tipe': 'Teknikal', 'Pattern': 'rsi_N', 'Penjelasan': 'Relative Strength Index N hari, mengukur kekuatan pergerakan (0-100)'},
            {'Tipe': 'Teknikal', 'Pattern': 'momentum_N', 'Penjelasan': 'Selisih nilai dengan N hari lalu, mengukur kecepatan perubahan'},
            {'Tipe': 'Teknikal', 'Pattern': 'rate_of_change_N', 'Penjelasan': 'Persentase perubahan dari N hari lalu, momentum relatif'},
            # Kalender
            {'Tipe': 'Kalender', 'Pattern': 'day_of_week', 'Penjelasan': 'Hari dalam minggu (0=Senin s.d. 4=Jumat), menangkap pola mingguan'},
            {'Tipe': 'Kalender', 'Pattern': 'day_of_month', 'Penjelasan': 'Tanggal dalam bulan (1-31), menangkap pola awal/akhir bulan'},
            {'Tipe': 'Kalender', 'Pattern': 'month', 'Penjelasan': 'Bulan dalam tahun (1-12), menangkap pola musiman'},
            {'Tipe': 'Kalender', 'Pattern': 'quarter', 'Penjelasan': 'Kuartal dalam tahun (1-4), menangkap pola kuartalan'},
            {'Tipe': 'Kalender', 'Pattern': 'week_of_year', 'Penjelasan': 'Minggu ke-N dalam tahun (1-52), menangkap siklus tahunan'},
            {'Tipe': 'Kalender', 'Pattern': 'is_month_start', 'Penjelasan': 'Indikator awal bulan (1/0), menangkap efek turn-of-month'},
            {'Tipe': 'Kalender', 'Pattern': 'is_month_end', 'Penjelasan': 'Indikator akhir bulan (1/0), menangkap efek window dressing'},
            {'Tipe': 'Kalender', 'Pattern': 'is_quarter_start', 'Penjelasan': 'Indikator awal kuartal (1/0), menangkap efek rebalancing'},
            {'Tipe': 'Kalender', 'Pattern': 'is_quarter_end', 'Penjelasan': 'Indikator akhir kuartal (1/0), menangkap efek reporting'},
            {'Tipe': 'Kalender', 'Pattern': 'is_holiday', 'Penjelasan': 'Indikator hari libur (1/0), menangkap dampak libur terhadap transaksi'},
            {'Tipe': 'Kalender', 'Pattern': 'days_to_holiday', 'Penjelasan': 'Jumlah hari menuju libur terdekat, antisipasi pra-libur'},
            {'Tipe': 'Kalender', 'Pattern': 'days_from_holiday', 'Penjelasan': 'Jumlah hari sejak libur terakhir, efek pasca-libur'},
            # Eksternal
            {'Tipe': 'Eksternal', 'Pattern': 'news_count', 'Penjelasan': 'Jumlah berita ekonomi/keuangan harian dari Trading Economics'},
            {'Tipe': 'Eksternal', 'Pattern': 'sentiment_finbert', 'Penjelasan': 'Skor sentimen berita dari model FinBERT (0-1)'},
            {'Tipe': 'Eksternal', 'Pattern': 'sentiment_bertmulti', 'Penjelasan': 'Skor sentimen dari BERT Multilingual untuk berita Indonesia'},
            {'Tipe': 'Eksternal', 'Pattern': 'sentiment_finbert_weighted', 'Penjelasan': 'Sentimen FinBERT tertimbang confidence score'},
            {'Tipe': 'Eksternal', 'Pattern': 'oil_price', 'Penjelasan': 'Harga minyak mentah global (USD/barrel)'},
            {'Tipe': 'Eksternal', 'Pattern': 'usd_idr', 'Penjelasan': 'Kurs USD/IDR dari pasar valuta asing'},
            {'Tipe': 'Eksternal', 'Pattern': 'gold', 'Penjelasan': 'Harga emas global (USD/oz)'},
            {'Tipe': 'Eksternal', 'Pattern': 'us_treasury', 'Penjelasan': 'Yield US Treasury 10Y, indikator suku bunga global'},
            # Series Lain
            {'Tipe': 'Series Lain', 'Pattern': 'A.x.x.x / B.x.x / C.x.x', 'Penjelasan': 'Data dari series lain yang berkorelasi tinggi dengan target (cross-series features)'},
            {'Tipe': 'Series Lain', 'Pattern': 'ext_[Series_ID]', 'Penjelasan': 'Lag/rolling dari series lain yang berkorelasi tinggi'},
        ]
        return pd.DataFrame(descriptions)

    from io import BytesIO
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # All results
        results_df.to_excel(writer, index=False, sheet_name='All Results')

        # Model summary
        model_summary.to_excel(writer, sheet_name='Model Summary')

        # Best models per leaf node
        if len(best_models) > 0:
            best_models.to_excel(writer, index=False, sheet_name='Best Models')

        # Feature Description Reference
        feature_desc_df = get_feature_descriptions()
        feature_desc_df.to_excel(writer, index=False, sheet_name='Feature Descriptions')

        # Model configuration - export all saved configs
        config_dir = 'model_configs'
        if os.path.exists(config_dir):
            all_configs = []
            for filename in os.listdir(config_dir):
                if filename.endswith('.json'):
                    try:
                        filepath = os.path.join(config_dir, filename)
                        with open(filepath, 'r') as f:
                            config_data = json.load(f)
                            if 'metadata' in config_data and 'models' in config_data:
                                for row_id, model in config_data['models'].items():
                                    all_configs.append({
                                        'Config_Name': config_data['metadata']['name'],
                                        'Row_ID': row_id,
                                        'Model': model
                                    })
                    except:
                        pass

            if len(all_configs) > 0:
                config_export_df = pd.DataFrame(all_configs)
                config_export_df.to_excel(writer, index=False, sheet_name='Model Configurations')

    buffer.seek(0)

    st.download_button(
        label="📥 Download Model Evaluation Report (Excel)",
        data=buffer,
        file_name=f"model_evaluation_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        use_container_width=True
    )

else:
    st.info("👈 Atur ukuran test set di sidebar dan klik **Jalankan Evaluasi** untuk memulai")

# ========================================================================
# SECTION: SAVE CONFIGURATION (Always available if has evaluation results)
# ========================================================================
st.markdown("---")

# Check if there's evaluation results in session state
if 'best_models_df' in st.session_state and st.session_state['best_models_df'] is not None:
    best_models_saved = st.session_state['best_models_df']

    st.subheader("⚙️ Simpan Konfigurasi Model")
    st.markdown("""
    Pilih model yang akan digunakan untuk forecast setiap leaf node.
    Konfigurasi akan disimpan dengan nama dan bisa dipilih di **Lembar Kerja > Forecast**.
    """)

    # Create config directory if not exists
    config_dir = 'model_configs'
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    # Get list of saved configurations
    saved_configs = []
    if os.path.exists(config_dir):
        for filename in os.listdir(config_dir):
            if filename.endswith('.json'):
                try:
                    filepath = os.path.join(config_dir, filename)
                    with open(filepath, 'r') as f:
                        config_data = json.load(f)
                        if 'metadata' in config_data:
                            saved_configs.append({
                                'filename': filename,
                                'name': config_data['metadata']['name'],
                                'date': config_data['metadata']['date'],
                                'test_size': config_data['metadata'].get('test_size', 'N/A'),
                                'metric': config_data['metadata'].get('metric', 'WAPE')
                            })
                except:
                    pass

    # Show existing configurations
    if len(saved_configs) > 0:
        with st.expander("📁 Konfigurasi Tersimpan", expanded=False):
            configs_df = pd.DataFrame(saved_configs)
            st.dataframe(configs_df[['name', 'date', 'test_size', 'metric']], use_container_width=True)
            st.caption(f"Total: {len(saved_configs)} konfigurasi tersimpan")

    # Initialize with best models
    initial_config = {}
    if len(best_models_saved) > 0:
        for _, row in best_models_saved.iterrows():
            initial_config[row['Row_ID']] = row['Model']

    # Display configuration table
    st.markdown("### 📋 Pilih Model untuk Setiap Leaf Node")

    # Filter by category
    selected_category_filter = st.multiselect(
        "Filter by Category",
        options=['KORPORASI', 'INDIVIDU', 'NON RESIDEN'],
        default=['KORPORASI', 'INDIVIDU', 'NON RESIDEN'],
        key="category_filter_config_save"
    )

    # Prepare data for display - sort by Row_ID (A.1.a → A.1.b → A.2.a → ...)
    config_data = []
    best_models_sorted = best_models_saved.sort_values('Row_ID', ascending=True)
    for _, row in best_models_sorted.iterrows():
        if row['Category'] in selected_category_filter:
            # Get metric value based on selected metric
            metric_value = row[selection_metric] if selection_metric in row else row.get('SMAPE', row.get('MAPE', 0))

            config_data.append({
                'Row_ID': row['Row_ID'],
                'Row_Label': row['Row_Label'],
                'Category': row['Category'],
                'Best_Model': row['Model'],
                'Metric_Value': metric_value
            })

    config_df = pd.DataFrame(config_data)

    if len(config_df) > 0:
        st.markdown(f"**Total: {len(config_df)} leaf nodes**")
        st.markdown("**💡 Tips:** Pilih model untuk setiap node, lalu klik tombol Simpan di paling bawah.")

        # Use form to collect all changes before saving
        with st.form(key='model_config_form_save'):
            # Group by category
            for category in selected_category_filter:
                category_df = config_df[config_df['Category'] == category].sort_values('Row_ID', ascending=True)

                if len(category_df) > 0:
                    st.markdown(f"### 📊 {category} ({len(category_df)} nodes)")

                    for idx, row in category_df.iterrows():
                        col1, col2, col3, col4 = st.columns([2, 3, 2, 2])

                        with col1:
                            st.text(row['Row_ID'])

                        with col2:
                            label = row['Row_Label'].split('. ', 1)[-1] if '. ' in row['Row_Label'] else row['Row_Label']
                            st.text(label[:40] + '...' if len(label) > 40 else label)

                        with col3:
                            st.text(f"Best: {row['Best_Model']}")
                            st.caption(f"{selection_metric}: {row['Metric_Value']:.2f}")

                        with col4:
                            # Use Best_Model from current row (from best_models dataframe)
                            best_model = row['Best_Model']
                            model_options = ['Stacking', 'APUVA', 'Prophet', 'RandomForest', 'LightGBM', 'XGBoost', 'AutoARIMA', 'VAR']

                            # Get index of best model, default to 0 if not found
                            try:
                                default_index = model_options.index(best_model)
                            except ValueError:
                                default_index = 0

                            st.selectbox(
                                "Model",
                                options=model_options,
                                index=default_index,
                                key=f"model_select_save_{row['Row_ID']}",
                                label_visibility="collapsed"
                            )

                    st.markdown("---")

            st.markdown("---")
            st.markdown("### 💾 Simpan Konfigurasi")

            # Configuration name input
            config_name = st.text_input(
                "Nama Konfigurasi",
                value=f"Config_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}",
                help="Berikan nama untuk konfigurasi ini (contoh: Config_WAPE_Best, Config_Test20pct)",
                key="config_name_input_save"
            )

            # Submit button inside form
            submitted_save = st.form_submit_button("💾 Simpan Konfigurasi", type="primary", use_container_width=True)

        # Handle form submission OUTSIDE the form
        if submitted_save:
            # Get config name from session state
            config_name_value = st.session_state.get('config_name_input_save', '')

            if not config_name_value or config_name_value.strip() == "":
                st.error("❌ Nama konfigurasi tidak boleh kosong!")
            else:
                # Collect all model selections from form
                final_config = {}
                for _, row in config_df.iterrows():
                    final_config[row['Row_ID']] = st.session_state.get(f"model_select_save_{row['Row_ID']}", row['Best_Model'])

                # Get test_size from session state if available
                test_size_value = st.session_state.get('evaluation_test_size', 20)

                # Prepare configuration with metadata
                config_with_metadata = {
                    'metadata': {
                        'name': config_name_value.strip(),
                        'date': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'test_size': test_size_value,
                        'metric': 'SMAPE',
                        'total_nodes': len(final_config)
                    },
                    'models': final_config
                }

                # Save configuration with safe filename
                safe_filename = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in config_name_value.strip())
                safe_filename = safe_filename.replace(' ', '_')
                config_filepath = os.path.join(config_dir, f"{safe_filename}.json")

                try:
                    with open(config_filepath, 'w') as f:
                        json.dump(config_with_metadata, f, indent=2)
                    st.success(f"✅ Konfigurasi '{config_name_value}' berhasil disimpan untuk {len(final_config)} leaf nodes!")
                    st.info(f"📁 Disimpan di: {config_filepath}")
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ Gagal menyimpan: {str(e)}")

else:
    # No evaluation results yet - show saved configs only
    config_dir = 'model_configs'
    if os.path.exists(config_dir):
        saved_configs = []
        for filename in os.listdir(config_dir):
            if filename.endswith('.json'):
                try:
                    filepath = os.path.join(config_dir, filename)
                    with open(filepath, 'r') as f:
                        config_data = json.load(f)
                        if 'metadata' in config_data:
                            saved_configs.append({
                                'name': config_data['metadata']['name'],
                                'date': config_data['metadata']['date'],
                                'test_size': config_data['metadata'].get('test_size', 'N/A'),
                                'total_nodes': config_data['metadata'].get('total_nodes', len(config_data.get('models', {})))
                            })
                except:
                    pass

        if len(saved_configs) > 0:
            st.subheader("📁 Konfigurasi Model Tersimpan")
            configs_df = pd.DataFrame(saved_configs)
            st.dataframe(configs_df, use_container_width=True)
            st.caption(f"Total: {len(saved_configs)} konfigurasi tersimpan")
