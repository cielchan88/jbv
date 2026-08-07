"""
External Features Loader Helper
Helper function to load and merge external features with cross-series features
"""

import streamlit as st
from etl.load_external import load_external_features


@st.cache_data(ttl=600)  # Cache 10 menit (balance antara performance vs freshness)
def load_and_merge_external_features(cross_series_dict):
    """
    Load external features dan merge dengan cross-series features

    Cache TTL: 10 menit
    - Cukup fresh untuk workflow harian
    - Hemat resource (avoid repeated Excel read)
    - Bisa clear manual via sidebar button (jika ditambahkan di pages)

    Parameters:
    -----------
    cross_series_dict : dict
        Dictionary dari cross-series features (dari prepare_external_series_data)

    Returns:
    --------
    combined_dict : dict
        Combined dictionary dengan cross-series + external features
    """
    try:
        # Load external features (use default sheet)
        _, external_features_dict = load_external_features(sheet_name=None)

        # Merge
        from utils.feature_engineering import merge_external_features_with_cross_series
        combined = merge_external_features_with_cross_series(
            external_features_dict,
            cross_series_dict
        )

        return combined

    except Exception as e:
        # Silent fallback - error message will be shown at higher level if needed
        return cross_series_dict
