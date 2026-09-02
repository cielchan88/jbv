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
from plotly.subplots import make_subplots
from sklearn.metrics import mean_absolute_error, mean_squared_error, mean_absolute_percentage_error, r2_score
from lightgbm import LGBMRegressor
from sklearn.ensemble import RandomForestRegressor
import xgboost as xgb
from prophet import Prophet
import warnings
import json
import os
warnings.filterwarnings('ignore')

# Page config
st.set_page_config(page_title="Prediksi - JBV Dashboard", layout="wide")

# Import utils
from utils import load_holidays, generate_business_dates, ML_START_DATE
from utils.data_loader import load_etl_output, parse_children
from utils.forecasting import forecast_single_series

# Title
st.title("🔮 Prediksi")
st.markdown("Prediksi single series dengan berbagai model machine learning.")

st.divider()

# Load ETL output data (NOT raw processed data!)
df, metadata_cols, time_cols = load_etl_output()

# Get leaf nodes (parse Children JSON strings)
leaf_nodes = df[df['Children'].apply(lambda x: len(parse_children(x))) == 0].copy()

# Sidebar: Series Selection
st.sidebar.header("⚙️ Pengaturan Test")

# Clean labels for display
def get_clean_label(row_id):
    row_data = df[df['Row_ID'] == row_id]
    if len(row_data) > 0:
        label = row_data.iloc[0]['Row_Label']
        return label.split('. ', 1)[-1] if '. ' in label else label
    return row_id

# Step 1: Select main category
main_categories = {
    'A': 'KORPORASI',
    'B': 'INDIVIDU',
    'C': 'NON RESIDEN'
}

selected_category = st.sidebar.selectbox(
    "1️⃣ Pilih Kategori",
    options=list(main_categories.keys()),
    format_func=lambda x: main_categories[x]
)

# Step 2: For KORPORASI, select sub-category
if selected_category == 'A':
    korporasi_sub = {
        'A.1': 'PTMN',
        'A.2': 'Korporasi Lainnya'
    }

    selected_sub = st.sidebar.selectbox(
        "2️⃣ Pilih Sub-Kategori",
        options=list(korporasi_sub.keys()),
        format_func=lambda x: korporasi_sub[x]
    )

    category_leaf_nodes = leaf_nodes[leaf_nodes['Row_ID'].str.startswith(selected_sub + '.')].copy()

    selected_series = st.sidebar.selectbox(
        "3️⃣ Pilih Komponen",
        options=category_leaf_nodes['Row_ID'].tolist(),
        format_func=get_clean_label
    )
else:
    category_leaf_nodes = leaf_nodes[leaf_nodes['Row_ID'].str.startswith(selected_category + '.')].copy()

    selected_series = st.sidebar.selectbox(
        "2️⃣ Pilih Komponen",
        options=category_leaf_nodes['Row_ID'].tolist(),
        format_func=get_clean_label
    )

# Forecast horizon
forecast_days = st.sidebar.number_input(
    "Horizon Prediksi (hari)",
    min_value=1,
    max_value=365,
    value=30,
    step=1
)

# Train/test split
test_size = st.sidebar.slider(
    "Ukuran Data Test (%)",
    min_value=10,
    max_value=40,
    value=20,
    step=5
)


# Run prediction button
run_test = st.sidebar.button("🚀 Jalankan Test", type="primary")

# Main content
if run_test and selected_series:
    st.subheader(f"📊 Test Results: {get_clean_label(selected_series)}")

    # ========================================================================
    # PREPARE DATA WITH DIFFERENT STRATEGIES FOR ML vs APUVA
    # ========================================================================

    # Get FULL time series data (for APUVA - needs 2006-2025 for 6-year history)
    series_data = df[df['Row_ID'] == selected_series]
    values_full = series_data[time_cols].values.flatten()
    # Clean None/NaN values
    values_full = np.array(values_full, dtype=float)
    values_full = np.nan_to_num(values_full, nan=0.0, posinf=0.0, neginf=0.0)
    dates_full = pd.to_datetime(time_cols)

    # Get FILTERED time series data (for ML models - 2019+ with external features)
    if ML_START_DATE is not None:
        time_cols_ml = [col for col in time_cols if pd.to_datetime(col) >= pd.Timestamp(ML_START_DATE)]
    else:
        time_cols_ml = time_cols  # ML pakai histori penuh yang sama dengan ETL/APUVA
    values_ml = series_data[time_cols_ml].values.flatten()
    # Clean None/NaN values
    values_ml = np.array(values_ml, dtype=float)
    values_ml = np.nan_to_num(values_ml, nan=0.0, posinf=0.0, neginf=0.0)
    dates_ml = pd.to_datetime(time_cols_ml)

    # Create time series dataframe for ML models (2019+)
    ts_df_ml = pd.DataFrame({
        'date': dates_ml,
        'value': values_ml
    })

    # Create time series dataframe for APUVA (full 2006-2025)
    ts_df_apuva = pd.DataFrame({
        'date': dates_full,
        'value': values_full
    })

    # Train/test split for ML models (based on 2019+ data)
    split_idx_ml = int(len(ts_df_ml) * (1 - test_size/100))
    train_ml = ts_df_ml.iloc[:split_idx_ml]
    test_ml = ts_df_ml.iloc[split_idx_ml:]

    # Train/test split for APUVA (based on full data)
    split_idx_apuva = int(len(ts_df_apuva) * (1 - test_size/100))
    train_apuva = ts_df_apuva.iloc[:split_idx_apuva]
    test_apuva = ts_df_apuva.iloc[split_idx_apuva:]

    # Display data info
    ml_start_label = dates_ml[0].strftime('%Y') + "+" if len(dates_ml) > 0 else "N/A"
    apuva_start_label = dates_full[0].strftime('%Y') + "+" if len(dates_full) > 0 else "N/A"
    st.write(f"📊 **ML Models ({ml_start_label})**: Training {len(train_ml)} hari | Testing {len(test_ml)} hari")
    st.write(f"📊 **APUVA ({apuva_start_label})**: Training {len(train_apuva)} hari | Testing {len(test_apuva)} hari | **Forecast**: {forecast_days} hari")
    st.info("ℹ️ External features (Oil Price, USD/IDR, Sentiment, dll) sedang dimatikan sementara - "
            "ML models dan APUVA sekarang sama-sama pakai seluruh histori data yang tersedia.")

    # Load holidays
    holidays_list = load_holidays()

    # ========================================================================
    # PREPARE CROSS-SERIES FEATURES (from ALL leaf nodes)
    # ========================================================================

    with st.spinner("🔍 Finding correlated series from all leaf nodes..."):
        from utils.feature_engineering_optimized import (
            calculate_series_correlations,
            select_top_correlated_series,
            prepare_external_series_data
        )

        # 1. Get all leaf nodes (exclude the target series itself)
        all_leaf_ids = leaf_nodes['Row_ID'].tolist()
        candidate_series = [lid for lid in all_leaf_ids if lid != selected_series]

        # 2. Calculate correlations with ALL leaf nodes (using 2019+ data for ML)
        correlations = calculate_series_correlations(df, selected_series, candidate_series, time_cols_ml)

        # 3. Select top 30 correlated series
        top_30_series = select_top_correlated_series(correlations, top_k=30)

        # 4. Prepare external series data (cross-series only) - using 2019+ data
        cross_series_only = prepare_external_series_data(df, top_30_series, time_cols_ml)

        # 5. Merge with external features from Excel
        from utils.external_loader import load_and_merge_external_features
        external_series_data = load_and_merge_external_features(cross_series_only, time_cols_ml)

    # ========================================================================
    # FEATURE ENGINEERING (SHARED ACROSS ALL ML MODELS)
    # ========================================================================

    with st.spinner("🔧 Creating features for ML models (OPTIMIZED: ~92 features)..."):
        from utils.feature_engineering_optimized import create_features_optimized, select_top_features_optimized

        # Prepare data for feature engineering (use ML data 2019+)
        train_fe = train_ml.rename(columns={'date': 'ds', 'value': 'y'})
        test_fe = test_ml.rename(columns={'date': 'ds', 'value': 'y'})

        # Create optimized features (60-70% fewer features, preserves volatility capture)
        #
        # TANPA cross-series, sengaja. Fitur di sini dipakai untuk metrik uji
        # dan tabel "fitur terpilih" yang DITAMPILKAN sebagai penjelas forecast
        # di bawah. Peramal rekursif (RandomForest/XGBoost/LightGBM) tidak lagi
        # memakai ext_* - lihat ENABLE_CROSS_SERIES_FOR_RECURSIVE di
        # utils/feature_config.py - jadi kalau di sini masih dipakai, angka dan
        # daftar fitur yang ditampilkan menggambarkan model yang berbeda dari
        # model yang menghasilkan forecast. VAR di bawah tetap memakai
        # external_series_data lewat jalurnya sendiri.
        train_features = create_features_optimized(train_fe, lag_steps=90, holidays_list=holidays_list, external_series_dates=dates_ml)
        test_features = create_features_optimized(test_fe, lag_steps=90, holidays_list=holidays_list, external_series_dates=dates_ml)

        # Check if test_features is empty or too small
        if len(test_features) == 0:
            st.warning("⚠️ Test features kosong setelah feature engineering. Menggunakan test data original.")
            # Fallback: use test_ml directly without feature engineering
            test_features = test_fe.copy()
            test_features['date'] = test_features['ds']
            test_features['value'] = test_features['y']

        # Get all available features
        train_available = [col for col in train_features.columns if col not in ['ds', 'date', 'value']]
        test_available = [col for col in test_features.columns if col not in ['ds', 'date', 'value']]
        common_features = list(set(train_available) & set(test_available))

        total_features_created = len(common_features)

        # Calculate scores for ALL features (not just top 25)
        from scipy.stats import spearmanr
        feature_scores = {}
        X_all = train_features[common_features].fillna(0).replace([np.inf, -np.inf], 0)
        y_all = train_features['value'].fillna(0)

        for col in common_features:
            try:
                corr, _ = spearmanr(X_all[col], y_all)
                feature_scores[col] = abs(corr) if not np.isnan(corr) else 0
            except:
                feature_scores[col] = 0

        # Select top 25 features based on correlation (with volatility priority)
        top_features, _ = select_top_features_optimized(train_features, top_k=25)

        # Final feature columns to use
        if len(top_features) > 0:
            feature_cols = [f for f in top_features if f in common_features]
        else:
            feature_cols = common_features

        if len(feature_cols) == 0:
            st.error("❌ No common features between train and test")
            st.stop()

    # Display feature engineering results
    st.success(f"✅ Mengambil {len(top_30_series)} series lainnya untuk dijadikan feature")
    st.success(f"✅ Terbentuk {total_features_created} fitur (dari series ini + {len(top_30_series)} series lainnya)")
    st.success(f"✅ Dipilih {len(feature_cols)} fitur dengan korelasi tertinggi")

    # Prepare X, y for ML models
    X_train = train_features[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
    y_train = train_features['value']

    # Safety check: ensure y_train has no None/NaN values
    if y_train.isna().any() or y_train.isnull().any():
        y_train = y_train.ffill().bfill().fillna(0)
        train_features['value'] = y_train

    # Handle case where test_features might not have all feature_cols
    available_test_cols = [col for col in feature_cols if col in test_features.columns]
    if len(available_test_cols) < len(feature_cols):
        # Add missing columns with 0
        for col in feature_cols:
            if col not in test_features.columns:
                test_features[col] = 0.0

    X_test = test_features[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
    y_test = test_features['value']

    # Safety check: ensure y_test is not empty
    if len(y_test) == 0:
        st.error("❌ Test data kosong setelah feature engineering. Coba kurangi ukuran test atau pilih series lain.")
        st.stop()

    # Safety check: ensure y_test has no None/NaN values
    # This can happen if test data has missing values or feature engineering introduced NaN
    if y_test.isna().any() or y_test.isnull().any():
        st.warning("⚠️ Test target (y_test) memiliki nilai NaN. Mengisi dengan nilai dari test_ml.")
        # Fill NaN values from original test data
        y_test = y_test.fillna(test_ml['value'].values[:len(y_test)])
        # If still NaN, use forward/backward fill
        y_test = y_test.ffill().bfill()
        # Update test_features to keep consistency
        test_features['value'] = y_test

    # Convert to numpy array with proper None handling
    y_test_values = y_test.values
    if any(v is None for v in y_test_values):
        st.warning("⚠️ Detected None values in y_test. Converting to numeric.")
        y_test_values = pd.to_numeric(y_test, errors='coerce').fillna(0).values

    # Store for display later
    shared_features_info = {
        'features': feature_cols,
        'scores': {f: feature_scores.get(f, 0) for f in feature_cols}
    }

    # ========================================================================
    # SHOW SELECTED FEATURES WITH SCORES
    # ========================================================================

    # Display ALL features table (selected features highlighted in red)
    with st.expander("🔍 Daftar Semua Fitur & Skor Korelasi", expanded=False):
        # Feature type and description mapping
        feature_info = {
            # Lag features
            'lag_': ('Historis', 'Nilai aktual {n} hari kerja yang lalu, menangkap pola jangka pendek'),
            # Rolling statistics
            'rolling_mean_': ('Statistik', 'Rata-rata bergerak {n} hari terakhir, menghaluskan fluktuasi harian'),
            'rolling_std_': ('Statistik', 'Standar deviasi {n} hari terakhir, mengukur tingkat volatilitas'),
            'rolling_max_': ('Statistik', 'Nilai tertinggi dalam {n} hari terakhir, mendeteksi puncak lokal'),
            'rolling_min_': ('Statistik', 'Nilai terendah dalam {n} hari terakhir, mendeteksi lembah lokal'),
            # EWM (Exponential Weighted)
            'ewm_std_': ('Statistik', 'Volatilitas eksponensial {n} hari, lebih responsif terhadap perubahan terkini'),
            'ewm_': ('Statistik', 'Rata-rata eksponensial {n} hari, memberi bobot lebih pada data terbaru'),
            # Bollinger Bands
            'bb_middle_': ('Teknikal', 'Garis tengah Bollinger Band (SMA {n} hari), basis untuk mengukur deviasi'),
            'bb_upper_': ('Teknikal', 'Batas atas Bollinger Band, sinyal potensi overbought'),
            'bb_lower_': ('Teknikal', 'Batas bawah Bollinger Band, sinyal potensi oversold'),
            'bb_width_': ('Teknikal', 'Lebar Bollinger Band, indikator ekspansi/kontraksi volatilitas'),
            # Technical indicators
            'macd': ('Teknikal', 'Moving Average Convergence Divergence, mengukur momentum dan arah tren'),
            'macd_signal': ('Teknikal', 'Signal line MACD, digunakan untuk sinyal buy/sell crossover'),
            'rsi_': ('Teknikal', 'Relative Strength Index {n} hari, mengukur kekuatan pergerakan (0-100)'),
            # Calendar features
            'day_of_week': ('Kalender', 'Hari dalam minggu (0=Senin s.d. 4=Jumat), menangkap pola mingguan'),
            'day_of_month': ('Kalender', 'Tanggal dalam bulan (1-31), menangkap pola awal/akhir bulan'),
            'month': ('Kalender', 'Bulan dalam tahun (1-12), menangkap pola musiman'),
            'quarter': ('Kalender', 'Kuartal dalam tahun (1-4), menangkap pola kuartalan'),
            'week_of_year': ('Kalender', 'Minggu ke-N dalam tahun (1-52), menangkap siklus tahunan'),
            'is_month_start': ('Kalender', 'Indikator awal bulan (1/0), menangkap efek turn-of-month'),
            'is_month_end': ('Kalender', 'Indikator akhir bulan (1/0), menangkap efek window dressing'),
            'is_quarter_start': ('Kalender', 'Indikator awal kuartal (1/0), menangkap efek rebalancing'),
            'is_quarter_end': ('Kalender', 'Indikator akhir kuartal (1/0), menangkap efek reporting'),
            'is_holiday': ('Kalender', 'Indikator hari libur (1/0), menangkap dampak libur terhadap transaksi'),
            'days_to_holiday': ('Kalender', 'Jumlah hari menuju libur terdekat, antisipasi pra-libur'),
            'days_from_holiday': ('Kalender', 'Jumlah hari sejak libur terakhir, efek pasca-libur'),
            # Trend features
            'trend': ('Teknikal', 'Komponen tren linear dari dekomposisi time series'),
            'trend_slope_': ('Teknikal', 'Kemiringan tren {n} hari, mengukur percepatan/perlambatan'),
            # Momentum
            'momentum_': ('Teknikal', 'Selisih nilai dengan {n} hari lalu, mengukur kecepatan perubahan'),
            'rate_of_change_': ('Teknikal', 'Persentase perubahan dari {n} hari lalu, momentum relatif'),
        }

        # External features from Excel with detailed descriptions
        external_feature_desc = {
            'news_count': ('Eksternal', 'Jumlah berita ekonomi/keuangan harian dari Trading Economics'),
            'sentiment_finbert': ('Eksternal', 'Skor sentimen berita dari model FinBERT (0-1)'),
            'sentiment_bertmulti': ('Eksternal', 'Skor sentimen dari BERT Multilingual untuk berita Indonesia'),
            'sentiment_finbert_weighted': ('Eksternal', 'Sentimen FinBERT tertimbang confidence score'),
            'sentiment': ('Eksternal', 'Skor sentimen agregat dari berbagai sumber berita'),
            'oil_price': ('Eksternal', 'Harga minyak mentah global (USD/barrel)'),
            'usd_idr': ('Eksternal', 'Kurs USD/IDR dari pasar valuta asing'),
            'gold': ('Eksternal', 'Harga emas global (USD/oz)'),
            'us_treasury': ('Eksternal', 'Yield US Treasury 10Y, indikator suku bunga global'),
        }

        def get_feature_type_and_desc(feat_name):
            """Get feature type and description"""
            # Check exact match first
            if feat_name in feature_info:
                return feature_info[feat_name]

            # Check prefix matches with number extraction
            for prefix, (ftype, desc_template) in feature_info.items():
                if prefix.endswith('_') and feat_name.startswith(prefix):
                    suffix = feat_name[len(prefix):]
                    if suffix.isdigit():
                        return (ftype, desc_template.format(n=suffix))
                    else:
                        return (ftype, desc_template.format(n=suffix))

            # Check if it's an external feature from Excel
            feat_lower = feat_name.lower()
            for ext_key, (ext_type, ext_desc) in external_feature_desc.items():
                if ext_key in feat_lower:
                    return (ext_type, ext_desc)

            # Check if it's a cross-series feature (ext_ prefix or series ID pattern)
            if feat_name.startswith('ext_'):
                series_id = feat_name[4:]
                return ('Series Lain', f'Data dari series {series_id} yang berkorelasi tinggi dengan target')

            # Check for series ID pattern (A.1.1.1, B.1.2, etc.)
            if any(feat_name.startswith(p) for p in ['A.', 'B.', 'C.']):
                return ('Series Lain', f'Data dari series {feat_name} yang berkorelasi tinggi dengan target')

            # Default
            return ('Lainnya', 'Fitur tambahan dari feature engineering')

        # Get selected features
        selected_features = set(shared_features_info['features'])

        # Create DataFrame for ALL features
        all_features_data = []
        for feat in common_features:
            is_selected = feat in selected_features
            feat_type, feat_desc = get_feature_type_and_desc(feat)
            all_features_data.append({
                'Feature': feat,
                'Tipe': feat_type,
                'Penjelasan': feat_desc,
                'Korelasi': feature_scores.get(feat, 0),
                'Status': '✅' if is_selected else ''
            })

        # Sort by correlation score
        feature_df_all = pd.DataFrame(all_features_data).sort_values('Korelasi', ascending=False)

        # Add ranking
        feature_df_all['#'] = range(1, len(feature_df_all) + 1)
        feature_df_all = feature_df_all[['#', 'Feature', 'Tipe', 'Penjelasan', 'Korelasi', 'Status']]

        # Apply styling to highlight selected features
        def highlight_selected(row):
            if row['Status'] == '✅':
                return ['background-color: #ffcccc'] * len(row)
            else:
                return [''] * len(row)

        styled_df = feature_df_all.style.apply(highlight_selected, axis=1).format({'Korelasi': '{:.3f}'})

        st.dataframe(
            styled_df,
            use_container_width=True,
            height=min(500, len(feature_df_all) * 35 + 38),
            hide_index=True
        )

        # Summary by type
        type_counts = feature_df_all['Tipe'].value_counts()
        selected_by_type = feature_df_all[feature_df_all['Status'] == '✅']['Tipe'].value_counts()

        st.markdown(f"**Total:** {len(common_features)} fitur | **Dipakai:** {len(selected_features)} fitur")

        # Type breakdown
        type_summary = []
        for t in type_counts.index:
            total = type_counts.get(t, 0)
            used = selected_by_type.get(t, 0)
            type_summary.append(f"{t}: {used}/{total}")
        st.caption(" | ".join(type_summary))

    # ========================================================================
    # TRAIN ALL MODELS
    # ========================================================================

    progress_bar = st.progress(0)
    status_text = st.empty()

    results = {}
    selected_features_info = {}  # Store selected features for each model
    trained_models = {}  # Store trained model objects for SHAP

    # ==================== MODEL 1: Prophet ====================
    status_text.text("Training Prophet...")

    try:
        train_prophet = train_ml.rename(columns={'date': 'ds', 'value': 'y'})
        test_prophet = test_ml.rename(columns={'date': 'ds', 'value': 'y'})

        model_prophet = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            changepoint_prior_scale=0.05
        )
        model_prophet.fit(train_prophet)

        # Predict on test
        test_forecast = model_prophet.predict(test_prophet[['ds']])
        predictions_test_prophet = test_forecast['yhat'].values

        # Forecast future using BUSINESS DAYS ONLY
        future_business_dates = generate_business_dates(dates_ml[-1], forecast_days, holidays_list)
        future_dates_df = pd.DataFrame({'ds': future_business_dates})
        forecast_future = model_prophet.predict(future_dates_df)

        forecast_prophet = forecast_future['yhat'].values
        forecast_lower_prophet = forecast_future['yhat_lower'].values
        forecast_upper_prophet = forecast_future['yhat_upper'].values

        results['Prophet'] = {
            'predictions_test': predictions_test_prophet,
            'forecast': forecast_prophet,
            'forecast_lower': forecast_lower_prophet,
            'forecast_upper': forecast_upper_prophet,
            'success': True
        }

    except Exception as e:
        results['Prophet'] = {'success': False, 'error': str(e)}

    progress_bar.progress(0.17)

    # ==================== MODEL 2: XGBoost ====================
    status_text.text("Training XGBoost...")

    try:
        # USING CENTRALIZED FORECASTING - 100% consistent with lembar_kerja.py
        # Use 2019+ data with external features
        forecast_xgb, future_business_dates_xgb = forecast_single_series(
            dates=dates_ml,
            values=values_ml,
            model_name='XGBoost',
            n_days=forecast_days,
            holidays=holidays_list,
            external_series=external_series_data
        )
        forecast_xgb = np.array(forecast_xgb)

        # Use shared features for test predictions
        selected_features_info['XGBoost'] = shared_features_info

        model_xgb = xgb.XGBRegressor(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, verbosity=0)
        model_xgb.fit(X_train, y_train, verbose=False)
        predictions_test_xgb = model_xgb.predict(X_test)

        # Calculate confidence intervals based on residuals
        residuals_xgb = y_test_values - predictions_test_xgb
        residual_std = np.std(residuals_xgb)
        forecast_lower_xgb = forecast_xgb - 1.96 * residual_std
        forecast_upper_xgb = forecast_xgb + 1.96 * residual_std

        results['XGBoost'] = {
            'predictions_test': predictions_test_xgb,
            'forecast': forecast_xgb,
            'forecast_lower': forecast_lower_xgb,
            'forecast_upper': forecast_upper_xgb,
            'success': True,
            'test_dates': test_features['date'].values
        }
        trained_models['XGBoost'] = model_xgb

    except Exception as e:
        results['XGBoost'] = {'success': False, 'error': str(e)}

    progress_bar.progress(0.34)

    # ==================== MODEL 3: Random Forest ====================
    status_text.text("Training Random Forest...")

    try:
        # USING CENTRALIZED FORECASTING - 100% consistent with lembar_kerja.py
        # Use 2019+ data with external features
        forecast_rf, future_business_dates_rf = forecast_single_series(
            dates=dates_ml,
            values=values_ml,
            model_name='RandomForest',
            n_days=forecast_days,
            holidays=holidays_list,
            external_series=external_series_data
        )
        forecast_rf = np.array(forecast_rf)

        # Use shared features for test predictions
        selected_features_info['RandomForest'] = shared_features_info

        model_rf = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
        model_rf.fit(X_train, y_train)
        predictions_test_rf = model_rf.predict(X_test)

        # Calculate confidence intervals
        residuals_rf = y_test_values - predictions_test_rf
        residual_std_rf = np.std(residuals_rf)
        forecast_lower_rf = forecast_rf - 1.96 * residual_std_rf
        forecast_upper_rf = forecast_rf + 1.96 * residual_std_rf

        results['RandomForest'] = {
            'predictions_test': predictions_test_rf,
            'forecast': forecast_rf,
            'forecast_lower': forecast_lower_rf,
            'forecast_upper': forecast_upper_rf,
            'success': True,
            'test_dates': test_features['date'].values
        }
        trained_models['RandomForest'] = model_rf

    except Exception as e:
        results['RandomForest'] = {'success': False, 'error': str(e)}

    progress_bar.progress(0.51)

    # ==================== MODEL 4: LightGBM ====================
    status_text.text("Training LightGBM...")

    try:
        # USING CENTRALIZED FORECASTING - 100% consistent with lembar_kerja.py
        # Use 2019+ data with external features
        forecast_lgb, future_business_dates = forecast_single_series(
            dates=dates_ml,
            values=values_ml,
            model_name='LightGBM',
            n_days=forecast_days,
            holidays=holidays_list,
            external_series=external_series_data
        )
        forecast_lgb = np.array(forecast_lgb)

        # Use shared features for test predictions
        selected_features_info['LightGBM'] = shared_features_info

        from lightgbm import LGBMRegressor
        model_lightgbm = LGBMRegressor(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, verbose=-1)
        model_lightgbm.fit(X_train, y_train)
        predictions_test_lgb = model_lightgbm.predict(X_test)

        # Calculate confidence intervals
        residuals_lgb = y_test_values - predictions_test_lgb
        residual_std_lgb = np.std(residuals_lgb)
        forecast_lower_lgb = forecast_lgb - 1.96 * residual_std_lgb
        forecast_upper_lgb = forecast_lgb + 1.96 * residual_std_lgb

        results['LightGBM'] = {
            'predictions_test': predictions_test_lgb,
            'forecast': forecast_lgb,
            'forecast_lower': forecast_lower_lgb,
            'forecast_upper': forecast_upper_lgb,
            'success': True,
            'test_dates': test_features['date'].values
        }
        trained_models['LightGBM'] = model_lightgbm

    except Exception as e:
        results['LightGBM'] = {'success': False, 'error': str(e)}

    progress_bar.progress(0.50)

    # ==================== MODEL 5: AutoARIMA ====================
    status_text.text("Training AutoARIMA...")

    try:
        # USING CENTRALIZED FORECASTING
        forecast_arima, future_business_dates_arima = forecast_single_series(
            dates=dates_ml,
            values=values_ml,
            model_name='autoarima',
            n_days=forecast_days,
            holidays=holidays_list
        )
        forecast_arima = np.array(forecast_arima)

        # For test predictions, use ARIMA on train data
        from utils.forecasting import ARIMAForecaster
        arima_model = ARIMAForecaster(holidays=holidays_list)
        arima_model.fit(train_ml['date'].dt.strftime('%Y-%m-%d').tolist(), train_ml['value'].values)
        predictions_test_arima, _ = arima_model.predict(
            train_ml['date'].dt.strftime('%Y-%m-%d').tolist(),
            train_ml['value'].values,
            len(test_ml)
        )
        predictions_test_arima = np.array(predictions_test_arima)

        # Calculate confidence intervals
        residuals_arima = test_ml['value'].values - predictions_test_arima
        residual_std_arima = np.std(residuals_arima)
        forecast_lower_arima = forecast_arima - 1.96 * residual_std_arima
        forecast_upper_arima = forecast_arima + 1.96 * residual_std_arima

        results['AutoARIMA'] = {
            'predictions_test': predictions_test_arima,
            'forecast': forecast_arima,
            'forecast_lower': forecast_lower_arima,
            'forecast_upper': forecast_upper_arima,
            'success': True,
            'test_dates': test_ml['date'].values
        }

    except Exception as e:
        results['AutoARIMA'] = {'success': False, 'error': str(e)}

    progress_bar.progress(0.58)

    # ==================== MODEL 6: VAR ====================
    status_text.text("Training VAR...")

    try:
        # Prepare external series as dict for VAR
        # external_series_data is always a dict from load_and_merge_external_features
        external_dict = {}
        if external_series_data is not None:
            if isinstance(external_series_data, dict):
                # Dict format: {series_id: values_array}
                external_dict = external_series_data.copy()
            elif hasattr(external_series_data, 'columns'):
                # DataFrame format (fallback)
                for col in external_series_data.columns:
                    if col != 'date':
                        external_dict[col] = external_series_data[col].values

        # VAR uses external series for multivariate forecasting
        forecast_var, future_business_dates_var = forecast_single_series(
            dates=dates_ml,
            values=values_ml,
            model_name='var',
            n_days=forecast_days,
            holidays=holidays_list,
            external_series=external_dict
        )
        forecast_var = np.array(forecast_var)

        # For test predictions, use VAR on train data
        from utils.forecasting import VARForecaster
        var_model = VARForecaster(holidays=holidays_list)

        # Prepare external series for training period (truncate to train length)
        external_train = {}
        if external_series_data is not None:
            if isinstance(external_series_data, dict):
                # Dict format: {series_id: values_array}
                for col, vals in external_series_data.items():
                    if col != 'date':
                        # Convert to array if needed and truncate to train length
                        arr = np.array(vals) if not isinstance(vals, np.ndarray) else vals
                        external_train[col] = arr[:len(train_ml)]
            elif hasattr(external_series_data, 'columns'):
                # DataFrame format (fallback)
                for col in external_series_data.columns:
                    if col != 'date':
                        external_train[col] = external_series_data[col].iloc[:len(train_ml)].values

        var_model.fit(train_ml['date'].dt.strftime('%Y-%m-%d').tolist(), train_ml['value'].values, external_series=external_train)
        predictions_test_var, _ = var_model.predict(
            train_ml['date'].dt.strftime('%Y-%m-%d').tolist(),
            train_ml['value'].values,
            len(test_ml)
        )
        predictions_test_var = np.array(predictions_test_var)

        # Calculate confidence intervals
        residuals_var = test_ml['value'].values - predictions_test_var
        residual_std_var = np.std(residuals_var)
        forecast_lower_var = forecast_var - 1.96 * residual_std_var
        forecast_upper_var = forecast_var + 1.96 * residual_std_var

        results['VAR'] = {
            'predictions_test': predictions_test_var,
            'forecast': forecast_var,
            'forecast_lower': forecast_lower_var,
            'forecast_upper': forecast_upper_var,
            'success': True,
            'test_dates': test_ml['date'].values
        }

    except Exception as e:
        results['VAR'] = {'success': False, 'error': str(e)}

    progress_bar.progress(0.66)

    # ==================== MODEL 7: APUVA ====================
    status_text.text("Training APUVA...")

    try:
        # APUVA uses FULL historical data (2006-2025) - needs 6 years for year-6 to year-1 calculations
        # NO external features - pure historical proportions
        forecast_apuva, future_business_dates = forecast_single_series(
            dates=dates_full,
            values=values_full,
            model_name='apuva',
            n_days=forecast_days,
            holidays=holidays_list,
            row_id=selected_series  # Pass row_id for sentiment factor
        )
        forecast_apuva = np.array(forecast_apuva)

        # For test predictions, use APUVA on train data to predict test period
        from utils.forecasting import APUVAForecaster
        apuva_model = APUVAForecaster(holidays=holidays_list, row_id=selected_series)
        apuva_model.fit(train_apuva['date'].dt.strftime('%Y-%m-%d').tolist(), train_apuva['value'].values)
        predictions_test_apuva, _ = apuva_model.predict(
            train_apuva['date'].dt.strftime('%Y-%m-%d').tolist(),
            train_apuva['value'].values,
            len(test_apuva)
        )
        predictions_test_apuva = np.array(predictions_test_apuva)

        # Calculate confidence intervals (use historical volatility)
        residuals_apuva = test_apuva['value'].values - predictions_test_apuva
        residual_std_apuva = np.std(residuals_apuva) if len(residuals_apuva) > 0 else np.std(values_full) * 0.5
        forecast_lower_apuva = forecast_apuva - 1.96 * residual_std_apuva
        forecast_upper_apuva = forecast_apuva + 1.96 * residual_std_apuva

        results['APUVA'] = {
            'predictions_test': predictions_test_apuva,
            'forecast': forecast_apuva,
            'forecast_lower': forecast_lower_apuva,
            'forecast_upper': forecast_upper_apuva,
            'success': True,
            'test_dates': test_apuva['date'].values
        }

    except Exception as e:
        results['APUVA'] = {'success': False, 'error': str(e)}

    progress_bar.progress(0.80)

    # ==================== MODEL 8: Stacking Ensemble ====================
    status_text.text("Training Stacking Ensemble (All Models with GBM Meta-Learner)...")

    try:
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.model_selection import KFold

        # Collect all successful base models (ML models only - exclude AutoARIMA and VAR)
        # AutoARIMA/VAR are statistical models that don't use ML features, better to exclude from stacking
        base_models = ['APUVA', 'RandomForest', 'LightGBM', 'XGBoost']
        successful_models = [m for m in base_models if results.get(m, {}).get('success')]

        if len(successful_models) >= 2:
            # Find the shortest test prediction length among ML models
            ml_models = [m for m in successful_models if m not in ['APUVA', 'AutoARIMA', 'VAR']]
            if ml_models:
                min_len = min(len(results[m]['predictions_test']) for m in ml_models)
            else:
                min_len = len(results['APUVA']['predictions_test'])

            # Align all predictions to the same length
            aligned_preds = {}
            for model in successful_models:
                pred = results[model]['predictions_test']
                if model in ['APUVA', 'AutoARIMA', 'VAR']:
                    # These models have different test period, take last min_len
                    aligned_preds[model] = np.array(pred[-min_len:])
                else:
                    aligned_preds[model] = np.array(pred[-min_len:])

            # Get actual values (use test_ml for alignment)
            y_actual_stack = test_ml['value'].values[-min_len:]

            # Stack predictions as features
            X_stack = np.column_stack([aligned_preds[m] for m in successful_models])

            # ============ CROSS-VALIDATION FOR OUT-OF-FOLD PREDICTIONS ============
            # This prevents overfitting and creates better meta-learner training data
            n_splits = 5
            kf = KFold(n_splits=n_splits, shuffle=False)  # Time series: no shuffle

            oof_predictions = np.zeros(len(y_actual_stack))

            for train_idx, val_idx in kf.split(X_stack):
                X_fold_train, X_fold_val = X_stack[train_idx], X_stack[val_idx]
                y_fold_train = y_actual_stack[train_idx]

                # Train meta-learner on fold
                fold_meta = GradientBoostingRegressor(
                    n_estimators=50,
                    max_depth=3,
                    learning_rate=0.1,
                    random_state=42
                )
                fold_meta.fit(X_fold_train, y_fold_train)

                # Predict on validation fold
                oof_predictions[val_idx] = fold_meta.predict(X_fold_val)

            # Train final meta-learner on ALL data
            meta_model = GradientBoostingRegressor(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                random_state=42
            )
            meta_model.fit(X_stack, y_actual_stack)

            # Use OOF predictions as test predictions (more realistic)
            predictions_test_stack = oof_predictions

            # ============ FORECAST ============
            # Stack forecasts from all base models
            min_forecast_len = min(len(results[m]['forecast']) for m in successful_models)

            forecast_stack_features = np.column_stack([
                results[m]['forecast'][:min_forecast_len] for m in successful_models
            ])

            # Generate stacked forecast
            forecast_stack = meta_model.predict(forecast_stack_features)

            # ============ CONFIDENCE INTERVALS ============
            # Use residuals from OOF predictions for realistic uncertainty
            residuals_stack = y_actual_stack - oof_predictions
            residual_std = np.std(residuals_stack)

            # Add trend-based uncertainty (increases with forecast horizon)
            horizon_factor = np.linspace(1.0, 1.5, len(forecast_stack))
            forecast_lower_stack = forecast_stack - 1.96 * residual_std * horizon_factor
            forecast_upper_stack = forecast_stack + 1.96 * residual_std * horizon_factor

            # Feature importance from meta-learner
            feature_importance = dict(zip(successful_models, meta_model.feature_importances_))

            results['Stacking'] = {
                'predictions_test': predictions_test_stack,
                'forecast': forecast_stack,
                'forecast_lower': forecast_lower_stack,
                'forecast_upper': forecast_upper_stack,
                'success': True,
                'test_dates': test_features['date'].values[-len(predictions_test_stack):],
                'feature_importance': feature_importance,
                'base_models': successful_models
            }

            # Display feature importance
            imp_str = ", ".join([f"{m}={v:.1%}" for m, v in feature_importance.items()])
            st.info(f"🔗 Stacking Base Models: {', '.join(successful_models)} | Importance: {imp_str}")

        else:
            results['Stacking'] = {'success': False, 'error': f'Need at least 2 base models, got {len(successful_models)}'}

    except Exception as e:
        results['Stacking'] = {'success': False, 'error': str(e)}

    progress_bar.progress(1.0)
    status_text.empty()

    # Display training completion message
    st.success("✅ Berhasil melatih 8 model forecasting")

    # ========================================================================
    # SECTION 1: METRICS COMPARISON
    # ========================================================================

    metrics_data = []
    for model_name, result in results.items():
        if result['success']:
            # APUVA uses full test data, ML models use ML test data
            if model_name == 'APUVA':
                actual = test_apuva['value'].values
            else:
                actual = test_ml['value'].values

            predictions = result['predictions_test']

            # Handle models which might have different length
            if model_name in ['XGBoost', 'LightGBM', 'RandomForest', 'Stacking', 'AutoARIMA', 'VAR'] and 'test_dates' in result:
                actual = actual[-len(predictions):]

            # Ensure same length and convert to numpy arrays
            min_len = min(len(actual), len(predictions))
            actual = np.array(actual[:min_len])
            predictions = np.array(predictions[:min_len])

            mae = mean_absolute_error(actual, predictions)
            rmse = np.sqrt(mean_squared_error(actual, predictions))

            # MAPE - only for non-zero values
            non_zero_mask = actual != 0
            if non_zero_mask.sum() > 0:
                mape = np.mean(np.abs((actual[non_zero_mask] - predictions[non_zero_mask]) / actual[non_zero_mask])) * 100
            else:
                mape = np.nan

            # R² (Coefficient of Determination)
            r2 = r2_score(actual, predictions)

            # SMAPE (Symmetric Mean Absolute Percentage Error) - correct formula
            smape = np.mean(np.abs(predictions - actual) / ((np.abs(actual) + np.abs(predictions)) / 2 + 1e-8)) * 100

            # Directional Accuracy - correct formula
            if len(actual) > 1:
                # Compare direction of change between consecutive points
                actual_change = actual[1:] - actual[:-1]
                pred_change = predictions[1:] - predictions[:-1]

                # Count how many times directions match
                correct_direction = np.sign(actual_change) == np.sign(pred_change)
                da = np.mean(correct_direction) * 100
            else:
                da = np.nan

            # Forecast Bias (Mean Error)
            bias = np.mean(predictions - actual)

            metrics_data.append({
                'Model': model_name,
                'MAE': mae,
                'RMSE': rmse,
                'MAPE': mape,
                'SMAPE': smape,
                'R²': r2,
                'DA': da,
                'Bias': bias
            })

    metrics_df = pd.DataFrame(metrics_data)

    # Sort metrics_df by model order
    model_display_order = ['Stacking', 'APUVA', 'AutoARIMA', 'VAR', 'Prophet', 'RandomForest', 'LightGBM', 'XGBoost']
    metrics_df['sort_key'] = metrics_df['Model'].map({model: i for i, model in enumerate(model_display_order)})
    metrics_df = metrics_df.sort_values('sort_key').drop('sort_key', axis=1).reset_index(drop=True)

    # Display summary table only
    st.markdown("### 📋 Metrics Comparison")
    st.dataframe(metrics_df.round(2), use_container_width=True)

    # ========================================================================
    # SECTION 2: VISUAL COMPARISON (3 PLOTS SIDE BY SIDE)
    # ========================================================================

    st.subheader("📈 Visual Comparison: Test + Forecast")

    # Generate business dates (skip weekends and holidays) - same as lembar_kerja.py
    holidays = load_holidays()
    forecast_dates = generate_business_dates(dates_ml[-1], forecast_days, holidays)

    # Create tabs for visual comparison
    model_order = ['Stacking', 'APUVA', 'AutoARIMA', 'VAR', 'Prophet', 'RandomForest', 'LightGBM', 'XGBoost']
    tabs = st.tabs(model_order)

    colors = {
        'Stacking': 'rgba(220, 20, 60, 1)',  # Crimson for Stacking
        'APUVA': 'rgba(139, 69, 19, 1)',
        'AutoARIMA': 'rgba(0, 100, 200, 1)',  # Blue for AutoARIMA
        'VAR': 'rgba(50, 150, 100, 1)',  # Teal for VAR
        'RandomForest': 'rgba(255, 165, 0, 1)',
        'Prophet': 'rgba(0, 128, 0, 1)',
        'XGBoost': 'rgba(128, 0, 128, 1)',
        'LightGBM': 'rgba(255, 0, 0, 1)'
    }
    colors_fill = {
        'Stacking': 'rgba(220, 20, 60, 0.2)',  # Crimson for Stacking
        'APUVA': 'rgba(139, 69, 19, 0.2)',
        'AutoARIMA': 'rgba(0, 100, 200, 0.2)',  # Blue for AutoARIMA
        'VAR': 'rgba(50, 150, 100, 0.2)',  # Teal for VAR
        'RandomForest': 'rgba(255, 165, 0, 0.2)',
        'Prophet': 'rgba(0, 128, 0, 0.2)',
        'XGBoost': 'rgba(128, 0, 128, 0.2)',
        'LightGBM': 'rgba(255, 0, 0, 0.2)'
    }

    for idx, model_name in enumerate(model_order):
        with tabs[idx]:
            result = results.get(model_name, {})
            if result.get('success'):
                fig = go.Figure()

                # APUVA uses full data, ML models use 2019+ data
                if model_name == 'APUVA':
                    train_plot = train_apuva
                    test_plot = test_apuva
                else:
                    train_plot = train_ml
                    test_plot = test_ml

                # Training data
                fig.add_trace(go.Scatter(
                    x=train_plot['date'],
                    y=train_plot['value'],
                    mode='lines',
                    name='Train',
                    line=dict(color='gray', width=1)
                ))

                # Test data (actual)
                fig.add_trace(go.Scatter(
                    x=test_plot['date'],
                    y=test_plot['value'],
                    mode='lines',
                    name='Test (Actual)',
                    line=dict(color='black', width=2)
                ))

                # Test predictions
                if model_name in ['XGBoost', 'LightGBM', 'RandomForest', 'Stacking', 'AutoARIMA', 'VAR'] and 'test_dates' in result:
                    test_dates_plot = result['test_dates']
                else:
                    test_dates_plot = test_plot['date']

                fig.add_trace(go.Scatter(
                    x=test_dates_plot,
                    y=result['predictions_test'],
                    mode='lines',
                    name='Test (Pred)',
                    line=dict(color=colors[model_name], dash='dash', width=2)
                ))

                # Prepend last actual point to forecast so line is continuous (no gap)
                if model_name == 'APUVA':
                    last_actual_date = test_apuva['date'].iloc[-1]
                    last_actual_value = test_apuva['value'].iloc[-1]
                else:
                    last_actual_date = test_ml['date'].iloc[-1]
                    last_actual_value = test_ml['value'].iloc[-1]

                # Create extended forecast arrays that start from last actual point
                extended_dates = [last_actual_date] + list(forecast_dates)
                extended_forecast = [last_actual_value] + list(result['forecast'])
                extended_upper = [last_actual_value] + list(result['forecast_upper'])
                extended_lower = [last_actual_value] + list(result['forecast_lower'])

                # Forecast with confidence intervals (starting from last actual)
                fig.add_trace(go.Scatter(
                    x=extended_dates,
                    y=extended_upper,
                    mode='lines',
                    line=dict(width=0),
                    showlegend=False
                ))

                fig.add_trace(go.Scatter(
                    x=extended_dates,
                    y=extended_lower,
                    mode='lines',
                    fill='tonexty',
                    fillcolor=colors_fill[model_name],
                    line=dict(width=0),
                    name='Confidence Interval'
                ))

                fig.add_trace(go.Scatter(
                    x=extended_dates,
                    y=extended_forecast,
                    mode='lines',
                    name='Forecast',
                    line=dict(color='red', dash='dot', width=2)
                ))

                fig.update_layout(
                    height=600,
                    title_text=f"{model_name} - {get_clean_label(selected_series)}",
                    hovermode='x unified',
                    xaxis_title="Date",
                    yaxis_title="Value (USD Juta)",
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )

                st.plotly_chart(fig, use_container_width=True)
            else:
                st.error(f"❌ Model {model_name} gagal: {result.get('error', 'Unknown error')}")

    # ========================================================================
    # SECTION 3: FORECAST TABLES
    # ========================================================================

    st.subheader(f"📋 Forecast Tables ({forecast_days} Hari Kedepan)")

    # Ordered tabs
    model_order = ['Stacking', 'APUVA', 'AutoARIMA', 'VAR', 'Prophet', 'RandomForest', 'LightGBM', 'XGBoost']
    tabs = st.tabs(model_order)

    for idx, model_name in enumerate(model_order):
        with tabs[idx]:
            result = results.get(model_name, {})
            if result.get('success', False):
                # Ensure all arrays have same length
                forecast_len = min(len(forecast_dates), len(result['forecast']),
                                   len(result['forecast_lower']), len(result['forecast_upper']))

                # Convert forecast_dates to list of strings if it's a list of Timestamps
                if isinstance(forecast_dates, list):
                    forecast_dates_str = [d.strftime('%Y-%m-%d') for d in forecast_dates[:forecast_len]]
                else:
                    forecast_dates_str = forecast_dates[:forecast_len].strftime('%Y-%m-%d')

                forecast_df = pd.DataFrame({
                    'Tanggal': forecast_dates_str,
                    'Prediksi': result['forecast'][:forecast_len].round(0),
                    'Lower Bound': result['forecast_lower'][:forecast_len].round(0),
                    'Upper Bound': result['forecast_upper'][:forecast_len].round(0)
                })
                st.dataframe(forecast_df, use_container_width=True, height=400)
            else:
                st.error(f"❌ Model {model_name} gagal: {result.get('error', 'Unknown error')}")

    # ========================================================================
    # SECTION 4: RESIDUAL ANALYSIS
    # ========================================================================

    st.subheader("🔍 Analisis Residual (Test Set)")

    # Create residuals for each model
    residuals_data = {}
    for model_name, result in results.items():
        if result['success']:
            # APUVA uses full test data, ML models use ML test data
            if model_name == 'APUVA':
                actual = test_apuva['value'].values
                test_dates_default = test_apuva['date'].values
            else:
                actual = test_ml['value'].values
                test_dates_default = test_ml['date'].values

            predictions = result['predictions_test']

            # Handle models which might have different test dates
            if model_name in ['XGBoost', 'LightGBM', 'RandomForest', 'Stacking', 'AutoARIMA', 'VAR'] and 'test_dates' in result:
                actual = actual[-len(predictions):]

            residuals_data[model_name] = {
                'residuals': actual - predictions,
                'predictions': predictions,
                'test_dates': result.get('test_dates', test_dates_default)
            }

    # Create tabs for residual analysis
    model_order = ['Stacking', 'APUVA', 'AutoARIMA', 'VAR', 'Prophet', 'RandomForest', 'LightGBM', 'XGBoost']
    tabs = st.tabs(model_order)

    colors_residual = {'Stacking': 'crimson', 'APUVA': 'brown', 'AutoARIMA': 'blue', 'VAR': 'teal', 'LightGBM': 'red', 'RandomForest': 'orange', 'Prophet': 'green', 'XGBoost': 'purple'}

    for idx, model_name in enumerate(model_order):
        with tabs[idx]:
            if model_name in residuals_data:
                data = residuals_data[model_name]
                residuals = data['residuals']
                predictions = data['predictions']
                test_dates = data['test_dates']

                # Create 3-row subplot for this model
                fig_residuals = make_subplots(
                    rows=3, cols=1,
                    subplot_titles=(
                        'Residuals vs Fitted Values',
                        'Residuals Distribution',
                        'Residuals Over Time'
                    ),
                    vertical_spacing=0.12
                )

                # Row 1: Residuals vs Fitted
                fig_residuals.add_trace(go.Scatter(
                    x=predictions,
                    y=residuals,
                    mode='markers',
                    marker=dict(color=colors_residual[model_name], size=6),
                    name='Residuals',
                    showlegend=False
                ), row=1, col=1)
                fig_residuals.add_hline(y=0, line_dash="dash", line_color="red", row=1, col=1)

                # Row 2: Distribution (Histogram)
                fig_residuals.add_trace(go.Histogram(
                    x=residuals,
                    nbinsx=30,
                    marker=dict(color=colors_residual[model_name], line=dict(color='black', width=1)),
                    name='Distribution',
                    showlegend=False
                ), row=2, col=1)

                # Row 3: Residuals Over Time
                fig_residuals.add_trace(go.Scatter(
                    x=test_dates,
                    y=residuals,
                    mode='lines+markers',
                    marker=dict(color=colors_residual[model_name], size=4),
                    line=dict(color=colors_residual[model_name]),
                    name='Residuals',
                    showlegend=False
                ), row=3, col=1)
                fig_residuals.add_hline(y=0, line_dash="dash", line_color="red", row=3, col=1)

                # Update axes labels
                fig_residuals.update_xaxes(title_text="Fitted Values", row=1, col=1)
                fig_residuals.update_yaxes(title_text="Residuals", row=1, col=1)

                fig_residuals.update_xaxes(title_text="Residuals", row=2, col=1)
                fig_residuals.update_yaxes(title_text="Frequency", row=2, col=1)

                fig_residuals.update_xaxes(title_text="Date", row=3, col=1)
                fig_residuals.update_yaxes(title_text="Residuals", row=3, col=1)

                fig_residuals.update_layout(
                    height=900,
                    title_text=f"{model_name} - Residual Analysis",
                    showlegend=False
                )

                st.plotly_chart(fig_residuals, use_container_width=True)

                # Statistics for this model
                st.markdown("### 📊 Residual Statistics")
                residual_stats = {
                    'Metric': ['Mean', 'Std Dev', 'Min', 'Max', 'Skewness', 'Kurtosis'],
                    'Value': [
                        residuals.mean(),
                        residuals.std(),
                        residuals.min(),
                        residuals.max(),
                        pd.Series(residuals).skew(),
                        pd.Series(residuals).kurtosis()
                    ]
                }
                residual_stats_df = pd.DataFrame(residual_stats)
                st.dataframe(residual_stats_df.round(4), use_container_width=True, hide_index=True)
            else:
                st.warning(f"No residual data available for {model_name}")

    # ========================================================================
    # SECTION 5: SHAP EXPLAINABILITY (XAI)
    # ========================================================================

    st.subheader("🔬 SHAP Explainability (XAI)")
    st.markdown("""
    **SHAP (SHapley Additive exPlanations)** menjelaskan kontribusi setiap fitur terhadap prediksi model.
    - **Merah**: Nilai fitur tinggi mendorong prediksi naik
    - **Biru**: Nilai fitur rendah mendorong prediksi turun
    """)

    # Only for tree-based models
    shap_models = ['XGBoost', 'LightGBM', 'RandomForest']
    available_shap_models = [m for m in shap_models if m in trained_models and results.get(m, {}).get('success')]

    if len(available_shap_models) > 0:
        import shap

        # Create tabs for each model
        shap_tabs = st.tabs(available_shap_models)

        for idx, model_name in enumerate(available_shap_models):
            with shap_tabs[idx]:
                with st.spinner(f"Computing SHAP values for {model_name}..."):
                    try:
                        model = trained_models[model_name]

                        # Use TreeExplainer for tree-based models (faster)
                        explainer = shap.TreeExplainer(model)

                        # Compute SHAP values on test data (use sample if too large)
                        X_shap = X_test.copy()
                        if len(X_shap) > 200:
                            X_shap = X_shap.sample(n=200, random_state=42)

                        shap_values = explainer.shap_values(X_shap)

                        # ========== 1. SHAP Summary Plot (Feature Importance) ==========
                        st.markdown(f"#### 📊 Feature Importance - {model_name}")

                        # Calculate mean absolute SHAP values for each feature
                        shap_importance = np.abs(shap_values).mean(axis=0)
                        importance_df = pd.DataFrame({
                            'Feature': feature_cols,
                            'Mean |SHAP|': shap_importance
                        }).sort_values('Mean |SHAP|', ascending=False).head(10)

                        # Create horizontal bar chart
                        fig_importance = go.Figure(go.Bar(
                            x=importance_df['Mean |SHAP|'].values[::-1],
                            y=importance_df['Feature'].values[::-1],
                            orientation='h',
                            marker=dict(
                                color=importance_df['Mean |SHAP|'].values[::-1],
                                colorscale='RdBu_r'
                            )
                        ))
                        fig_importance.update_layout(
                            title=f"Top 10 Features by SHAP Importance",
                            xaxis_title="Mean |SHAP Value|",
                            yaxis_title="Feature",
                            height=500
                        )
                        st.plotly_chart(fig_importance, use_container_width=True)

                        # ========== 2. SHAP Beeswarm/Summary Plot ==========
                        st.markdown(f"#### 🐝 SHAP Summary (Beeswarm)")

                        # Create beeswarm-like plot using plotly
                        # Get top 10 features in order of importance (highest first)
                        top_features = importance_df['Feature'].head(10).tolist()
                        top_feature_indices = [feature_cols.index(f) for f in top_features if f in feature_cols]

                        # Reverse the order so highest importance appears at top of plot
                        # In plotly, higher y-values appear at top, so we reverse the list
                        top_features_reversed = top_features[::-1]
                        top_feature_indices_reversed = top_feature_indices[::-1]

                        beeswarm_data = []
                        for i, feat_idx in enumerate(top_feature_indices_reversed):
                            feat_name = feature_cols[feat_idx]
                            feat_shap = shap_values[:, feat_idx]
                            feat_values = X_shap[feat_name].values

                            # Normalize feature values for color
                            feat_min, feat_max = feat_values.min(), feat_values.max()
                            if feat_max > feat_min:
                                feat_normalized = (feat_values - feat_min) / (feat_max - feat_min)
                            else:
                                feat_normalized = np.zeros_like(feat_values)

                            # Add jitter for y-axis
                            y_jitter = np.random.normal(i, 0.15, len(feat_shap))

                            beeswarm_data.append({
                                'x': feat_shap,
                                'y': y_jitter,
                                'color': feat_normalized,
                                'name': feat_name
                            })

                        fig_beeswarm = go.Figure()
                        for i, data in enumerate(beeswarm_data):
                            fig_beeswarm.add_trace(go.Scatter(
                                x=data['x'],
                                y=data['y'],
                                mode='markers',
                                marker=dict(
                                    size=6,
                                    color=data['color'],
                                    colorscale='RdBu_r',
                                    showscale=(i == 0),
                                    colorbar=dict(title="Feature Value<br>(normalized)")
                                ),
                                name=data['name'],
                                showlegend=False,
                                hovertemplate=f"{data['name']}<br>SHAP: %{{x:.2f}}<extra></extra>"
                            ))

                        # Add feature names on y-axis (reversed so highest importance at top)
                        fig_beeswarm.update_layout(
                            title="SHAP Summary Plot (Top 10 Features)",
                            xaxis_title="SHAP Value (impact on prediction)",
                            yaxis=dict(
                                tickmode='array',
                                tickvals=list(range(len(top_features_reversed))),
                                ticktext=top_features_reversed
                            ),
                            height=500,
                            showlegend=False
                        )
                        fig_beeswarm.add_vline(x=0, line_dash="dash", line_color="gray")
                        st.plotly_chart(fig_beeswarm, use_container_width=True)

                    except Exception as e:
                        st.error(f"Error computing SHAP for {model_name}: {str(e)}")
    else:
        st.warning("Tidak ada model tree-based yang berhasil dilatih untuk SHAP analysis.")

else:
    st.info("👈 Pilih series dan klik **Jalankan Test** untuk memulai")
