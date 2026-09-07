"""
External Features Loader Helper
Helper function to load and merge external features with cross-series features
"""

import streamlit as st
import pandas as pd
from etl.load_external import load_external_features, align_external_features_to_dates

# Kill switch sementara: external_features.xlsx (Oil Price, USD/IDR, Sentiment
# TradingEconomics, dll) dimatikan dulu sampai kualitas datanya bisa dipastikan
# stabil (scraper sentiment masih dalam perbaikan). Selama False, model tetap
# jalan pakai cross-series features saja (korelasi antar leaf node) - itu tidak
# tersentuh, cuma sumber data Excel eksternalnya yang dilewati. Set True lagi
# kapan saja untuk mengaktifkan tanpa perlu ubah kode di tempat lain.
ENABLE_EXTERNAL_FEATURES = False


@st.cache_data(ttl=600)  # Cache 10 menit (balance antara performance vs freshness)
def load_and_merge_external_features(cross_series_dict, target_dates):
    """
    Load external features dan merge dengan cross-series features

    External features (dari Excel, tanggal kalender - termasuk weekend) di-align
    ke target_dates (tanggal target series, hari kerja saja) berdasarkan tanggal
    asli masing-masing via forward-fill, bukan berdasarkan posisi index seperti
    sebelumnya. Tanpa ini, Oil_Price/USD_IDR/Sentiment dkk. akan tergeser dari
    tanggal aslinya karena kedua sumber data punya kalender yang berbeda.

    Kalau ENABLE_EXTERNAL_FEATURES = False, langsung return cross_series_dict
    tanpa load/merge Excel sama sekali (lihat kill switch di atas).

    Cache TTL: 10 menit
    - Cukup fresh untuk workflow harian
    - Hemat resource (avoid repeated Excel read)
    - Bisa clear manual via sidebar button (jika ditambahkan di pages)

    Parameters:
    -----------
    cross_series_dict : dict
        Dictionary dari cross-series features (dari prepare_external_series_data),
        sudah berurutan sesuai target_dates.
    target_dates : list/array tanggal (mis. time_cols_ml)
        Tanggal series target yang jadi acuan alignment.

    Returns:
    --------
    combined_dict : dict
        Combined dictionary dengan cross-series + external features (atau cuma
        cross-series saja kalau external features dimatikan), berurutan
        mengikuti target_dates.
    """
    if not ENABLE_EXTERNAL_FEATURES:
        return cross_series_dict

    try:
        target_dates_idx = pd.DatetimeIndex(pd.to_datetime(list(target_dates)))

        # Load external features (use default sheet)
        external_df, external_features_dict = load_external_features(sheet_name=None)
        external_dates_idx = pd.DatetimeIndex(pd.to_datetime(external_df['Tanggal']))

        aligned_external = align_external_features_to_dates(
            external_features_dict, external_dates_idx, target_dates_idx
        )

        # Merge
        from utils.feature_engineering import merge_external_features_with_cross_series
        combined = merge_external_features_with_cross_series(
            aligned_external,
            cross_series_dict
        )

        return combined

    except Exception as e:
        # Silent fallback - error message will be shown at higher level if needed
        return cross_series_dict
