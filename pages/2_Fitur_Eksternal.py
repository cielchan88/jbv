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

with st.expander("⚙️ Opsi lanjutan: isi histori dari tanggal tertentu (backfill)"):
    st.markdown("""
    Secara default tombol di bawah cuma mengisi **selisih dari data terakhir sampai kemarin**
    (atau 30 hari terakhir kalau belum pernah scrape sama sekali). Model ML butuh data dari
    **2019** ke atas - kalau mau isi histori sejauh itu, gunakan opsi ini.
    """)
    st.error(
        "🚨 **Backfill rentang panjang (mis. sampai 2019) bisa makan waktu berjam-jam** "
        "(ribuan artikel x scraping + inferensi FinBERT per artikel). Kalau dijalankan lewat "
        "tombol di web ini, koneksinya berisiko putus di tengah jalan (timeout nginx/browser) "
        "meskipun prosesnya sendiri tetap lanjut di server. Untuk backfill panjang, lebih aman "
        "dijalankan langsung di server lewat SSH (bukan lewat tombol), atau isi bertahap "
        "beberapa minggu/bulan per klik."
    )
    use_backfill = st.checkbox("Aktifkan backfill dari tanggal tertentu")
    backfill_date = None
    if use_backfill:
        backfill_date = st.date_input(
            "Scrape dari tanggal", value=datetime(2019, 1, 1).date(),
            max_value=datetime.now().date()
        )

if "scrape_result" not in st.session_state:
    st.session_state.scrape_result = None
if "scrape_error" not in st.session_state:
    st.session_state.scrape_error = None

# Tampilkan hasil run terakhir (persist lewat session_state supaya tidak hilang setelah rerun)
if st.session_state.scrape_error:
    st.error(f"❌ Gagal scrape/update: {st.session_state.scrape_error}")
    st.info("💡 Pastikan server punya akses internet ke tradingeconomics.com")

if st.session_state.scrape_result:
    result = st.session_state.scrape_result
    st.success(
        f"✅ Proses selesai - {result['daily_rows']} hari data sentiment "
        f"({result['date_start'].strftime('%Y-%m-%d')} s/d {result['date_end'].strftime('%Y-%m-%d')}) "
        f"di-merge ke external_features.xlsx ({result['merged_rows']} baris total)."
    )

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("📰 Berita di-scrape", result['scraped_count'])
    with col_b:
        st.metric("🌏 Lolos filter US/ID", f"{result['filtered_count']}/{result['total_before_filter']}")
    with col_c:
        st.metric("🤖 Sentiment sukses", result['sentiment_stats']['success'])
    with col_d:
        st.metric("❌ Sentiment gagal", result['sentiment_stats']['failed'])

    st.caption(result['scrape_note'])

    if result['sentiment_stats']['failed'] > 0:
        st.warning(
            f"⚠️ {result['sentiment_stats']['failed']} artikel gagal dianalisis sentimennya "
            f"(fallback ke neutral/skor 0.0). Contoh error: `{result['sentiment_stats']['last_error']}`"
        )
    if result['sentiment_stats']['empty_title'] > 0:
        st.warning(f"⚠️ {result['sentiment_stats']['empty_title']} artikel tidak punya judul, dianggap neutral otomatis.")

    if result['flat_fallback_days'] > 0:
        st.error(
            f"🚩 **{result['flat_fallback_days']} hari** punya berita tapi `Sentiment_TradingEconomics` "
            f"jatuh persis di **0.5** - tanda semua artikel di hari itu gagal dianalisis (bukan sentimen netral "
            f"yang wajar). Ini kemungkinan besar penyebab nilai sentimen terlihat flat."
        )

if st.button("🔄 Scrape & Update Sentiment", type="primary"):
    st.session_state.scrape_result = None
    st.session_state.scrape_error = None
    try:
        from helper.tradingeconomics_scraper import run_scrape_and_update
    except ImportError as e:
        st.error(f"❌ Dependency belum terinstall: {e}")
        st.info("💡 Install dulu: `pip install transformers torch sentencepiece tqdm`")
    else:
        with st.spinner("⏳ Scraping berita & menjalankan analisis sentimen... (bisa beberapa menit)"):
            try:
                st.session_state.scrape_result = run_scrape_and_update(
                    backfill_start_date=backfill_date if use_backfill else None
                )
                st.cache_data.clear()
            except Exception as e:
                st.session_state.scrape_error = str(e)
        st.rerun()

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
