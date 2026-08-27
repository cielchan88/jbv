"""
📊 Fitur Eksternal - External Features Monitoring

Halaman sederhana untuk:
- Melihat external features yang tersedia
- Check apakah data up-to-date (ada gap atau tidak)

Author: APUVA Team
Date: 2025-11-11
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etl.load_external import (
    load_external_features,
    get_external_features_info
)

# Page config
st.set_page_config(
    page_title="Fitur Eksternal",
    page_icon="📊",
    layout="wide"
)

# Header
st.title("📊 Fitur Eksternal")
st.markdown("Monitoring fitur eksternal untuk prediksi.")
st.divider()

# ===== UPDATE SENTIMENT BERITA (SCRAPER + FINBERT) =====
st.subheader("🔄 Update Sentiment Berita")
st.markdown("""
Scrape berita terbaru dari Trading Economics (khusus US & Indonesia), analisis sentimen
pakai FinBERT, lalu otomatis di-*merge* ke `data/external_features.xlsx` berdasarkan
tanggal (kolom `News_Count` & `Sentiment_TradingEconomics`) - kolom fitur lain
(Oil Price, USD/IDR, dll) tidak tersentuh. File lama dibackup otomatis sebelum ditimpa.
""")
st.warning(
    "⚠️ Proses ini **berat dan bisa memakan waktu beberapa menit**: download model "
    "FinBERT (~400MB) saat pertama kali jalan, scraping via internet, lalu analisis "
    "sentimen per berita. Butuh akses internet dari server ke `tradingeconomics.com` "
    "dan `huggingface.co`."
)

if st.button("🔄 Scrape & Update Sentiment", type="primary"):
    try:
        from helper.tradingeconomics_scraper import run_scrape_and_update
    except ImportError as e:
        st.error(f"❌ Dependency belum terinstall: {e}")
        st.info("💡 Install dulu: `pip install transformers torch sentencepiece tqdm`")
    else:
        with st.spinner("⏳ Scraping berita & menjalankan analisis sentimen... (bisa beberapa menit)"):
            try:
                result = run_scrape_and_update()
                st.cache_data.clear()
                st.success(
                    f"✅ Selesai! {result['daily_rows']} hari data sentiment "
                    f"({result['date_start'].strftime('%Y-%m-%d')} s/d {result['date_end'].strftime('%Y-%m-%d')}) "
                    f"berhasil di-merge ke external_features.xlsx ({result['merged_rows']} baris total)."
                )
                st.rerun()
            except Exception as e:
                st.error(f"❌ Gagal scrape/update: {str(e)}")
                st.info("💡 Pastikan server punya akses internet ke tradingeconomics.com")

st.divider()

# Load external features
@st.cache_data
def load_external_data():
    """Load external features with caching"""
    try:
        df, external_dict = load_external_features(sheet_name=None)
        return df, external_dict, None
    except FileNotFoundError as e:
        return None, None, "File tidak ditemukan"
    except Exception as e:
        return None, None, f"Error: {str(e)}"

df_ext, ext_dict, error = load_external_data()

if error:
    st.error(f"❌ {error}")
    st.info("💡 Pastikan file `data/external_features.xlsx` tersedia dengan sheet `External_Features`")
    st.stop()

# File info
info = get_external_features_info()

# Metrics
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("📁 File", "✅ Tersedia")

with col2:
    st.metric("📊 Jumlah Features", info.get('num_features', 0))

with col3:
    st.metric("📅 Total Rows", info.get('num_rows', 0))

with col4:
    file_kb = info.get('file_size_kb', 0)
    st.metric("💾 Size", f"{file_kb:.1f} KB")

st.divider()

# Date info
st.subheader("📅 Informasi Data")

if 'date_range' in info:
    st.write(f"**Tanggal Awal:** `{info['date_range']['start']}`")
    st.write(f"**Tanggal Akhir:** `{info['date_range']['end']}`")

    start_date = pd.to_datetime(info['date_range']['start'])
    end_date = pd.to_datetime(info['date_range']['end'])
    days = (end_date - start_date).days
    st.write(f"**Durasi:** {days} hari")

# Check gaps
dates = pd.to_datetime(df_ext['Tanggal'])
date_range = pd.date_range(start=dates.min(), end=dates.max(), freq='D')
missing_dates = date_range.difference(dates)

if len(missing_dates) == 0:
    st.success("✅ **Status:** Data lengkap, tidak ada gap")
else:
    st.warning(f"⚠️ **Status:** Ada **{len(missing_dates)} tanggal** yang hilang")

    with st.expander("📋 Lihat tanggal yang hilang"):
        missing_df = pd.DataFrame({
            'Missing Date': missing_dates.strftime('%Y-%m-%d'),
            'Day': missing_dates.strftime('%A')
        })
        st.dataframe(missing_df, use_container_width=True, hide_index=True)

st.divider()

# Features list
st.subheader("📋 Daftar Features")

if 'features' in info and len(info['features']) > 0:
    features_df = pd.DataFrame({
        'No': range(1, len(info['features']) + 1),
        'Feature Name': info['features']
    })

    st.dataframe(features_df, use_container_width=True, hide_index=True)

st.divider()

# Data preview
st.subheader("📈 Data")
st.dataframe(df_ext, use_container_width=True, height=600)
