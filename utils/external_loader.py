"""
External Features Loader Helper
Helper function to load and merge external features with cross-series features
"""

import streamlit as st
import pandas as pd
from etl.load_external import load_external_features, align_external_features_to_dates

# Saklar sumber data eksternal (data/external_features.xlsx).
#
# DINYALAKAN setelah berkasnya diganti dengan panel makro harian yang tanggalnya
# cocok persis dengan data/processed/sdv-wide.csv - 5032 baris, 2006-01-02 s/d
# 2026-08-26, isi: bid/ask USD/IDR, bid/ask NDF 1M, yield SBN 10 tahun, DXY,
# arus asing di pasar saham, dan IHSG.
#
# Berkas SEBELUMNYA (sentimen berita + flows, 2019-02-20 s/d 2025-11-21) dimatikan
# karena dua cacat yang keduanya hilang di berkas baru:
#   - nol dipakai sebagai penanda hilang (831 nol di closing_usdidr_mid, 1.962 di
#     flows_srbi), sehingga model membaca kurs nol sebagai angka sungguhan;
#   - mulai 2019, jadi bfill mengisi 3.219 tanggal training (2006-2019) dengan
#     nilai 2019 - kebocoran look-ahead. Berkas baru hanya terisi mundur 1 tanggal
#     (dxy, 2006-01-02).
# Salinannya ada di data/external_features_LAMA_2019-2025.xlsx.bak.
#
# YANG MASIH HARUS DIPERHATIKAN. Menyalakan saklar ini TIDAK membuat fitur makro
# aman dipakai di semua horizon. Pada seleksi fitur, kolom ext_* memenangkan
# rata-rata 3,2 dari 25 slot (terbanyak ext_jci_index_*, lalu ext_dxy_* dan
# ext_bid_usdidr_*). Untuk peramal REKURSIF multi-langkah, predict() tidak punya
# nilai IHSG/DXY untuk tanggal masa depan sehingga kolom itu dinolkan diam-diam -
# persis kegagalan yang didokumentasikan di ENABLE_CROSS_SERIES_FOR_RECURSIVE
# (utils/feature_config.py), yang pernah menaikkan MAE LightGBM 16,2%.
# Beban 3,2/25 jauh lebih ringan dari kasus 12/25 di sana, tapi arah risikonya sama.
#
# Karena itu ENABLE_CROSS_SERIES_FOR_RECURSIVE sengaja DIBIARKAN False: saklar itu
# yang menyaring ext_* keluar dari fit() peramal rekursif. Jadi saat ini fitur makro
# sampai ke model hanya di jalur yang nilainya memang tersedia - horizon 1 (nilai
# tanggal test sudah diketahui), evaluasi teacher-forced, dan VAR.
# Untuk memakainya pada horizon panjang, sediakan dulu ramalan nilai eksternal
# sampai akhir horizon, baru nyalakan saklar di feature_config.py.
ENABLE_EXTERNAL_FEATURES = True


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
