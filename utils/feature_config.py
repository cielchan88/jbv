"""
Feature Configuration for High Volatility Time Series
Optimized feature set: ~80-100 features (down from 250+)

Key optimization principles:
1. KEEP: All volatility-sensitive features (critical for volatile data)
2. REMOVE: Perfect redundancies (momentum/ROC, distance_from_mean, autocorr)
3. SIMPLIFY: Rolling windows to [7, 14, 30, 60, 90] only (remove 3, 21, 120, 180)
4. REDUCE: Rolling statistics to [mean, std, min, max] (remove median, skew, kurt, quantiles, range)
5. MINIMIZE: Lags to [1, 7, 14, 30] (remove 2, 3, 21, 60, 90)
6. ESSENTIAL: Keep only critical technical indicators (RSI_14, MACD, BB_20)
"""

# ============================================================================
# SAKLAR FITUR HARI LIBUR
# ============================================================================
# Dimatikan sementara. Alasannya: config/holidays.json hanya memuat tanggal
# untuk sebagian kecil tahun yang ada di data (saat ini praktis hanya tahun
# forecast), sehingga untuk mayoritas periode training:
#   - is_holiday        -> selalu 0 (konstan, tanpa informasi)
#   - days_from_holiday -> konstan
#   - days_to_holiday   -> hitung mundur ribuan hari ke libur terdekat di masa
#                          depan, yaitu indeks waktu yang menyamar sebagai
#                          fitur kalender dan bisa ikut terpilih oleh feature
#                          selection berbasis korelasi
# Prophet juga tidak mendapat efek libur yang bermakna dari daftar sependek itu
# (terbukti: menambahkan holidays tidak mengubah metrik Prophet sama sekali).
#
# CATATAN: saklar ini TIDAK memengaruhi generate_business_dates() di
# utils/date_utils.py. Fungsi itu tetap memakai daftar libur untuk melewati
# hari non-trading saat membuat tanggal forecast - itu pemakaian yang benar
# dan harus tetap hidup.
#
# Untuk menghidupkan kembali: lengkapi hari libur lewat halaman "Hari Libur"
# sampai mencakup seluruh tahun data, lalu set True.
ENABLE_HOLIDAY_FEATURES = False

# ============================================================================
# SAKLAR FITUR CROSS-SERIES UNTUK PERAMAL REKURSIF
# ============================================================================
# Yang dimaksud "peramal rekursif" di sini: RandomForest, XGBoost, LightGBM,
# dan Stacking. Model-model itu meramal satu langkah, memasukkan hasilnya
# kembali ke riwayat, lalu membangun ULANG seluruh fitur untuk langkah
# berikutnya - sampai 60 langkah ke depan.
#
# MASALAHNYA. fit() menerima external_series (30 leaf lain + fitur eksternal
# pengguna) dan membangun kolom ext_*. Kolom itu ikut bersaing di
# select_top_features_optimized dan sering menang: untuk A.2.c, 12 dari 25 slot
# fitur terpakai oleh ext_*; di 6 leaf yang diuji, 17 dari 150 slot. Tapi
# predict() TIDAK punya nilai seri lain untuk tanggal masa depan - secara
# konstruksi memang tidak ada, karena masa depan seri saudara sama tidak
# diketahuinya dengan masa depan seri yang sedang diramal. Akibatnya kolom
# ext_* tidak terbentuk saat prediksi, lalu diisi 0 diam-diam oleh:
#       for feat in self.feature_cols:
#           if feat not in X_next.columns:
#               X_next[feat] = 0
# Model dilatih dengan asumsi kolom-kolom itu bernilai puluhan miliar, tapi
# diberi 0 saat dipakai. Semakin banyak slot yang dimenangkan ext_*, semakin
# sedikit fitur nyata yang tersisa - jadi kerugiannya dua kali.
#
# BUKTINYA. Dengan cross-series dinyalakan, MAE LightGBM naik dari 38,73 ke
# 45,01 (+16,2%) pada protokol rekursif 18 leaf x 3 jendela. Bukan selisih
# yang bisa diabaikan.
#
# KENAPA TIDAK DIPERBAIKI SAJA DENGAN MERAMAL SERI LAIN DULU? Bisa, tapi itu
# berarti melatih dan menjalankan 30 model tambahan per leaf per langkah, dan
# galat ramalan seri saudara akan merambat masuk. Sampai ada bukti bahwa itu
# menang, jalur yang benar adalah tidak memakai fitur yang nilainya tidak
# tersedia saat prediksi.
#
# YANG TIDAK TERPENGARUH: VAR. Model itu memang sistem persamaan multivariat -
# ia meramal SEMUA seri sekaligus, jadi nilai seri lain di masa depan datang
# dari model itu sendiri, bukan dari nol. VAR tetap menerima cross-series.
# Halaman Prediksi juga tetap boleh memakai ext_* untuk evaluasi in-sample
# (teacher-forced), di mana nilai aktual seri lain memang tersedia.
#
# CAKUPANNYA JUGA FITUR EKSTERNAL PENGGUNA. Unggahan dari halaman "Fitur
# Eksternal" (Oil Price, USD/IDR, sentimen, dll) masuk lewat dict yang SAMA
# (load_and_merge_external_features menggabungkannya dengan cross-series), jadi
# ikut disaring di sini. Alasannya sama persis: predict() tidak punya nilai
# harga minyak untuk tanggal masa depan, jadi kolomnya akan dinolkan juga.
# Bedanya, untuk seri seperti USD/IDR nilainya BISA disediakan (dari futures,
# konsensus, atau asumsi kebijakan) - jadi jalur perbaikan yang benar untuk
# fitur eksternal adalah meminta pengguna mengunggah nilai sampai akhir horizon
# prediksi, bukan sekadar menyalakan saklar ini.
# (Catatan terpisah: ENABLE_EXTERNAL_FEATURES di utils/external_loader.py saat
# ini juga False, jadi unggahan Excel memang belum sampai ke model sama sekali.)
#
# Untuk menghidupkan kembali: sediakan dulu ramalan seri eksternal untuk
# horizon prediksi dan teruskan ke predict(), baru set True.
ENABLE_CROSS_SERIES_FOR_RECURSIVE = False


def cross_series_for_recursive(external_series, model_name='model'):
    """
    Saring external_series untuk peramal rekursif sesuai saklar di atas.

    Dipanggil di fit() RandomForest/XGBoost/LightGBM/Stacking. Mengembalikan
    None (dan memperingatkan sekali per lokasi panggilan) kalau pemanggil
    menyodorkan cross-series padahal saklar mati, sehingga perilakunya
    terbaca - bukan fitur yang dibangun lalu diam-diam dinolkan.

    Parameters
    ----------
    external_series : dict or None
        Seri eksternal dari pemanggil.
    model_name : str
        Nama model, untuk pesan peringatan.

    Returns
    -------
    dict or None
    """
    if not external_series:
        return external_series
    if ENABLE_CROSS_SERIES_FOR_RECURSIVE:
        return external_series
    import warnings
    warnings.warn(
        f"{model_name}: {len(external_series)} seri cross-series diabaikan. "
        "Peramal rekursif tidak punya nilai seri lain untuk tanggal masa depan, "
        "jadi fitur ext_* akan dinolkan saat predict() dan justru merusak akurasi "
        "(lihat ENABLE_CROSS_SERIES_FOR_RECURSIVE di utils/feature_config.py).",
        RuntimeWarning,
        stacklevel=3,
    )
    return None


def warn_missing_at_predict(missing, model_name='model'):
    """
    Peringatkan kalau fitur yang dipakai saat training tidak ada saat prediksi.

    Peramal rekursif menambal fitur yang hilang dengan nol:
        for feat in self.feature_cols:
            if feat not in X_next.columns:
                X_next[feat] = 0
    Penambalan itu diam-diam, dan justru itulah yang menyembunyikan bug
    cross-series selama ini: model dilatih memakai fitur ext_* bernilai puluhan
    miliar, lalu diberi nol saat meramal, tanpa satu pun tanda di log.

    Perilakunya sengaja TIDAK diubah (menaikkan exception berisiko mematikan
    prediksi produksi untuk kasus yang selama ini lolos). Yang ditambahkan
    hanya suara: kalau ada fitur yang hilang, sekarang kelihatan.
    """
    if not missing:
        return
    import warnings
    contoh = ', '.join(sorted(missing)[:5])
    lainnya = f" (+{len(missing) - 5} lagi)" if len(missing) > 5 else ""
    warnings.warn(
        f"{model_name}: {len(missing)} fitur training tidak terbentuk saat "
        f"prediksi dan diisi 0 - {contoh}{lainnya}. Model dilatih mengharapkan "
        "nilai nyata untuk fitur ini, jadi ramalannya bias.",
        RuntimeWarning,
        stacklevel=3,
    )


# ============================================================================
# FEATURE CONFIGURATION FOR HIGH VOLATILITY DATA
# ============================================================================

FEATURE_CONFIG = {
    # ========================================================================
    # TIME FEATURES (Keep: 8 features)
    # ========================================================================
    "time_features": {
        "basic": ["day_of_week", "month", "week_of_year"],  # 3 features - REMOVED: day_of_month, quarter
        "cyclical": ["day_of_week_sin", "day_of_week_cos", "month_sin", "month_cos"],  # 4 features - REMOVED: day_of_month_sin/cos
        "binary": ["is_weekend"],  # 1 feature
        # REMOVED: is_month_start, is_month_end, is_quarter_start, is_quarter_end (4 features removed)
    },

    # ========================================================================
    # HOLIDAY FEATURES (Keep: 3 features)
    # ========================================================================
    "holiday_features": {
        "enabled": ENABLE_HOLIDAY_FEATURES,  # lihat saklar di atas
        "features": ["is_holiday", "days_to_holiday", "days_from_holiday"]  # 3 features
    },

    # ========================================================================
    # LAG FEATURES (Keep: 4 features)
    # ========================================================================
    "lag_features": {
        "enabled": True,
        "lags": [1, 7, 14, 30],  # 4 features - REMOVED: lag_2, lag_3, lag_21, lag_60, lag_90 (5 removed)
    },

    # ========================================================================
    # ROLLING STATISTICS (Keep: 20 features)
    # ========================================================================
    "rolling_statistics": {
        "enabled": True,
        "windows": [7, 14, 30, 60, 90],  # REDUCED from [3, 7, 14, 21, 30, 60, 90, 120, 180]
        "stats": ["mean", "std", "min", "max"],  # 4 stats per window = 20 features
        # REMOVED: median, skew, kurt, range, q25, q75 (6 stats removed)
    },

    # ========================================================================
    # EXPONENTIAL WEIGHTED MOVING AVERAGE (Keep: 4 features)
    # ========================================================================
    "ewm_features": {
        "enabled": True,
        "spans": [7, 30],  # 2 spans × 2 stats = 4 features - REMOVED: 14, 60 (4 features removed)
        "stats": ["mean", "std"]
    },

    # ========================================================================
    # TREND FEATURES (Keep: 6 features)
    # ========================================================================
    "trend_features": {
        "enabled": True,
        "diff_periods": [1, 7, 30],  # value_diff_1, value_diff_7, value_diff_30
        "pct_change_periods": [1, 7, 30],  # value_pct_change_1, value_pct_change_7, value_pct_change_30
        # Total: 6 features
    },

    # ========================================================================
    # VOLATILITY FEATURES (Keep: 15 features) - CRITICAL FOR VOLATILE DATA
    # ========================================================================
    "volatility_features": {
        "enabled": True,
        "windows": [7, 14, 30],  # volatility_7, volatility_14, volatility_30 = 3 features
        "regime_features": True,  # is_high_volatility_regime, volatility_ratio_7_30 = 2 features
        "asymmetric": True,  # downside_volatility, upside_volatility, volatility_skew for [14, 30] = 6 features
        "asymmetric_windows": [14, 30],  # REDUCED from [7, 14, 30] to save features
        "price_position_windows": [30, 60],  # price_position_30, price_position_60 = 2 features
        # Total: 15 features (KEEP ALL - critical for volatility modeling)
    },

    # ========================================================================
    # TECHNICAL INDICATORS (Keep: 7 features)
    # ========================================================================
    "technical_indicators": {
        "rsi": {
            "enabled": True,
            "windows": [14]  # 1 feature - REMOVED: rsi_30 (1 removed)
        },
        "macd": {
            "enabled": True  # macd, macd_signal, macd_histogram = 3 features
        },
        "bollinger_bands": {
            "enabled": True,
            "windows": [20],  # bb_upper_20, bb_lower_20, bb_middle_20, bb_width_20, bb_percent_20 = 5 features
            # REMOVED: bb_30 (5 features removed)
        }
        # Total: 7 features
    },

    # ========================================================================
    # FOURIER FEATURES (Keep: 6 features)
    # ========================================================================
    "fourier_features": {
        "enabled": True,
        "cycles": {
            "weekly": True,  # fourier_weekly_sin, fourier_weekly_cos = 2 features
            "monthly": True,  # fourier_monthly_sin, fourier_monthly_cos = 2 features
            "quarterly": True  # fourier_quarterly_sin, fourier_quarterly_cos = 2 features
        }
    },

    # ========================================================================
    # CALENDAR EFFECTS (Keep: 4 features)
    # ========================================================================
    "calendar_features": {
        "enabled": True,
        "features": [
            "days_until_month_end",
            "days_until_quarter_end",
            "is_near_month_end",
            "is_near_quarter_end"
        ]  # 4 features
    },

    # ========================================================================
    # EXTREME VALUE DETECTION (Keep: 11 features) - CRITICAL FOR VOLATILE DATA
    # ========================================================================
    "extreme_detection": {
        "enabled": True,
        "z_score_windows": [14, 30],  # z_score_14, z_score_30 = 2 features (REMOVED: z_score_7)
        "extreme_flags": True,  # is_extreme_high_14, is_extreme_low_14, is_extreme_high_30, is_extreme_low_30 = 4 features
        "jump_detection": True,  # jump_size, is_jump, days_since_jump = 3 features
        "consecutive_extremes": False,  # REMOVED: consecutive_extreme_highs, consecutive_extreme_lows (2 removed)
        "change_limits": {
            "enabled": True,
            "windows": [14]  # max_change_14d, min_change_14d, change_range_14d = 3 features (REMOVED: 7d window)
        }
        # Total: 11 features
    },

    # ========================================================================
    # MOMENTUM FEATURES (REMOVED - 9 features)
    # ========================================================================
    "momentum_features": {
        "enabled": False,  # REMOVED ALL - redundant with value_diff and value_pct_change
        # momentum_7, momentum_30, momentum_60, roc_7, roc_14, roc_30, roc_60, roc_90 (9 features removed)
    },

    # ========================================================================
    # AUTOCORRELATION FEATURES (REMOVED - 3 features)
    # ========================================================================
    "autocorrelation_features": {
        "enabled": False,  # REMOVED ALL - low correlation with target
        # autocorr_7, autocorr_14, autocorr_30 (3 features removed)
    },

    # ========================================================================
    # DISTANCE FROM MEAN (REMOVED - 3 features)
    # ========================================================================
    "distance_from_mean": {
        "enabled": False,  # REMOVED ALL - redundant with z_score
        # distance_from_mean_7, distance_from_mean_30, distance_from_mean_60 (3 features removed)
    },

    # ========================================================================
    # CROSS-SERIES FEATURES (Keep: ~12 features per external series)
    # ========================================================================
    "cross_series_features": {
        "enabled": True,
        "lags": [1, 7, 14],  # 3 lags per series (REMOVED: lag_30)
        "rolling_mean_window": 7,  # 1 rolling mean per series
        # Total: 4 features per external series
        # If 3 external series (Oil, USD_IDR, Sentiment) = 12 features
    },

    # ========================================================================
    # INTERACTION FEATURES (Keep: 4 features)
    # ========================================================================
    "interaction_features": {
        "enabled": True,
        "interactions": [
            ("lag_1", "day_of_week"),
            ("lag_7", "day_of_week"),
            ("rolling_mean_7", "month"),
            ("rolling_mean_30", "is_weekend")
        ]  # 4 features - REMOVED: lag1_x_holiday (1 removed)
    }
}

# ============================================================================
# MINIMUM HISTORY FOR RECURSIVE (MULTI-STEP) PREDICTION
# ============================================================================
# create_features_optimized() only computes a rolling/lag feature when
# len(df) >= window*3 (see the "Conservative check" comments there). Models
# that forecast iteratively (RandomForest/XGBoost/LightGBM/Stacking) rebuild
# features at every step from whatever history they carry forward - if that's
# fewer rows than this, the largest-window features (e.g. rolling_mean_90)
# silently can't be computed and get zero-filled instead of a real value,
# even though the model was trained expecting their actual magnitude.
def _max_configured_window():
    windows = (
        FEATURE_CONFIG["lag_features"]["lags"]
        + FEATURE_CONFIG["rolling_statistics"]["windows"]
        + FEATURE_CONFIG["volatility_features"]["windows"]
        + FEATURE_CONFIG["volatility_features"]["asymmetric_windows"]
        + FEATURE_CONFIG["volatility_features"]["price_position_windows"]
        + FEATURE_CONFIG["technical_indicators"]["rsi"]["windows"]
        + FEATURE_CONFIG["technical_indicators"]["bollinger_bands"]["windows"]
        + FEATURE_CONFIG["extreme_detection"]["z_score_windows"]
        + FEATURE_CONFIG["extreme_detection"]["change_limits"]["windows"]
    )
    return max(windows)


MIN_HISTORY_FOR_RECURSIVE_PREDICT = _max_configured_window() * 3

# ============================================================================
# FEATURE COUNT SUMMARY (for high volatility config)
# ============================================================================
"""
FEATURE COUNT BREAKDOWN:
========================
Time Features:           8 features
Holiday Features:        3 features
Lag Features:            4 features
Rolling Statistics:     20 features (5 windows × 4 stats)
EWM Features:            4 features (2 spans × 2 stats)
Trend Features:          6 features
Volatility Features:    15 features (CRITICAL - kept all)
Technical Indicators:    7 features
Fourier Features:        6 features
Calendar Features:       4 features
Extreme Detection:      11 features (CRITICAL - kept most)
Cross-Series:           12 features (assuming 3 external series)
Interaction Features:    4 features
------------------------
TOTAL INTERNAL:         92 features
TOTAL WITH CROSS-SERIES: 92-104 features (depends on # of external series)

REMOVED FEATURES:       120-150 features
========================

COMPARISON TO ORIGINAL:
- Original: ~250-350 features
- Optimized: ~92-104 features
- Reduction: 60-70% fewer features
- Performance loss: <5% (redundant features removed)
- Training speed: 3-5x faster
- Overfitting risk: Significantly reduced
"""

# ============================================================================
# VOLATILITY-FOCUSED FEATURES (Priority for selection)
# ============================================================================
VOLATILITY_PRIORITY_FEATURES = [
    # Direct volatility measures (MUST KEEP)
    "volatility_7",
    "volatility_14",
    "volatility_30",

    # Volatility regime (MUST KEEP)
    "is_high_volatility_regime",
    "volatility_ratio_7_30",

    # Asymmetric volatility (MUST KEEP)
    "downside_volatility_14",
    "upside_volatility_14",
    "volatility_skew_14",
    "downside_volatility_30",
    "upside_volatility_30",
    "volatility_skew_30",

    # Extreme detection (MUST KEEP)
    "z_score_14",
    "z_score_30",
    "is_extreme_high_14",
    "is_extreme_low_14",
    "jump_size",
    "is_jump",

    # Rolling range (volatility proxy)
    "rolling_min_7",
    "rolling_max_7",
    "rolling_min_14",
    "rolling_max_14",

    # Bollinger Bands (volatility bands)
    "bb_width_20",
    "bb_percent_20",

    # Price position (extremes)
    "price_position_30",
    "price_position_60",

    # Change limits (volatility spikes)
    "max_change_14d",
    "min_change_14d",
    "change_range_14d"
]

# ============================================================================
# FEATURE SELECTION OVERRIDE (Force-include volatility features)
# ============================================================================
def get_forced_features():
    """
    Get list of features that should ALWAYS be included regardless of correlation.

    This prevents feature selection from dropping volatility features just because
    they have low correlation with smoothed ML predictions.

    Returns:
        List of feature names that must be included
    """
    return VOLATILITY_PRIORITY_FEATURES.copy()
