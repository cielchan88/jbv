import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import os

st.set_page_config(page_title="Sumber Data - JBV Dashboard", layout="wide")

st.title("📁 Sumber Data")
st.markdown("Lihat dan verifikasi data dari Sumber Data.")

st.divider()

# Paths
BASE_DIR = Path(__file__).parent.parent
SOURCE_FILE = BASE_DIR / "data" / "raw" / "source-data.xlsx"
PROCESSED_FILE = BASE_DIR / "data" / "processed" / "sdv-wide.csv"

# Check if source file exists
if not SOURCE_FILE.exists():
    st.error(f"❌ File sumber tidak ditemukan: {SOURCE_FILE}")
    st.info("💡 Pastikan file `source-data.xlsx` ada di folder `data/raw/`")
    st.stop()

# File info
source_mtime = datetime.fromtimestamp(os.path.getmtime(SOURCE_FILE))
file_size = os.path.getsize(SOURCE_FILE) / 1024  # KB

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("📁 File Sumber", "source-data.xlsx")
with col2:
    st.metric("📅 Terakhir Diubah", source_mtime.strftime('%Y-%m-%d %H:%M'))
with col3:
    st.metric("💾 Ukuran File", f"{file_size:.1f} KB")

st.divider()

# ===== API SYNC SECTION =====
st.subheader("🔄 Sinkronisasi Data API")
st.markdown("""
API akan otomatis mengambil data hari ini dari CDS.
Jika data hari ini belum ada di Excel, klik **Sync dari API** untuk mengambil data terbaru.
""")

# Initialize session state for sync status
if 'api_sync_status' not in st.session_state:
    st.session_state.api_sync_status = None

# Display sync status
if st.session_state.api_sync_status:
    status_results = st.session_state.api_sync_status

    # Count status types
    success_count = sum(1 for v in status_results.values() if v.get('status') == 'success')
    skipped_count = sum(1 for v in status_results.values() if v.get('status') == 'skipped')
    error_count = sum(1 for v in status_results.values() if v.get('status') == 'error')

    # Overall status
    if error_count > 0 and success_count == 0:
        st.error(f"❌ Sync gagal untuk {error_count} sheet")
    elif success_count > 0:
        st.success(f"✅ Berhasil sync {success_count} sheet")
    elif skipped_count > 0:
        st.info(f"ℹ️ {skipped_count} sheet sudah up-to-date")

    # Show details in expander
    with st.expander("📋 Detail Status Sync", expanded=(success_count > 0 or error_count > 0)):
        for endpoint_key, result in status_results.items():
            status = result.get('status', 'unknown')
            message = result.get('message', 'No message')
            last_date = result.get('last_date', 'N/A')
            sync_time = result.get('sync_time', 'N/A')
            gap_warning = result.get('gap_warning', None)

            sheet_name = {
                'korporasi': 'Korporasi',
                'ptmn': 'PTMN',
                'asing': 'Asing',
                'individu': 'Individu'
            }.get(endpoint_key, endpoint_key.upper())

            if status == 'success':
                st.success(f"**{sheet_name}**: {message} (sync: {sync_time})")

                # Show gap warning if exists
                if gap_warning:
                    gap_days = gap_warning.get('gap_days', 0)
                    missing_start = gap_warning.get('missing_start', 'N/A')
                    missing_end = gap_warning.get('missing_end', 'N/A')
                    st.warning(f"⚠️ **Gap terdeteksi**: {gap_days} hari data tidak tersedia ({missing_start} s/d {missing_end}). API hanya menyediakan data hari ini. Silakan update manual untuk data historis yang hilang.")

            elif status == 'skipped':
                st.info(f"**{sheet_name}**: {message} (tanggal terakhir: {last_date})")
            elif status == 'error':
                st.error(f"**{sheet_name}**: {message}")

# Load and display all sheets
@st.cache_data
def load_all_sheets():
    """Load all sheets from Excel file"""
    xl_file = pd.ExcelFile(SOURCE_FILE)
    sheets_data = {}
    for sheet_name in xl_file.sheet_names:
        df = pd.read_excel(xl_file, sheet_name=sheet_name)
        sheets_data[sheet_name] = df
    return sheets_data

# Sync button
if st.button("🔄 Sync dari API", type="primary", help="Ambil data hari ini dari API"):
    with st.spinner("⏳ Mengambil data dari API..."):
        try:
            from etl.api_client import sync_today_data

            # Run sync
            sync_results = sync_today_data(str(SOURCE_FILE), force_refresh=False)

            # Store results in session state
            st.session_state.api_sync_status = sync_results

            # Clear cache to reload data
            load_all_sheets.clear()

            st.rerun()

        except Exception as e:
            st.error(f"❌ Error saat sync API: {str(e)}")
            st.info("💡 Pastikan Anda terhubung ke jaringan BI (VPN)")

st.divider()

try:
    sheets_data = load_all_sheets()

    st.subheader("📑 Data Per Sheet")

    if st.button("🔄 Reload Data", type="primary", help="Muat ulang data dari file Excel"):
        load_all_sheets.clear()
        st.rerun()

    # Create tabs for each sheet
    tabs = st.tabs(list(sheets_data.keys()))

    for idx, (sheet_name, df) in enumerate(sheets_data.items()):
        with tabs[idx]:
            st.markdown(f"### Sheet: **{sheet_name}**")

            # Summary metrics
            metadata_cols = ['Row_ID', 'Row_Label', 'Level']
            date_cols = [col for col in df.columns if col not in metadata_cols]

            # Get date range from column 1 (contains dates in each row)
            first_date = "N/A"
            last_date = "N/A"
            if 1 in df.columns and len(df) > 0:
                try:
                    # Get first and last date from column 1
                    first_val = pd.to_datetime(df[1].iloc[0])
                    last_val = pd.to_datetime(df[1].iloc[-1])
                    first_date = first_val.strftime('%Y-%m-%d')
                    last_date = last_val.strftime('%Y-%m-%d')
                except:
                    pass

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📋 Jumlah Kolom", f"{len(df.columns):,}")
            with col2:
                st.metric("📊 Jumlah Baris", f"{len(df):,}")
            with col3:
                st.metric("📅 Tanggal Awal", first_date)
            with col4:
                st.metric("📅 Tanggal Akhir", last_date)

            # Show full data directly
            st.dataframe(df, use_container_width=True, height=600)

except Exception as e:
    st.error(f"❌ Error saat membaca file Excel: {str(e)}")
    st.info("💡 Pastikan file source-data.xlsx dalam format yang benar")

st.divider()

# ===== ETL SYNC SECTION =====
st.subheader("⚙️ Sinkronisasi ETL Pipeline")
st.markdown("Proses data dari Excel menjadi format siap analisis dan prediksi.")

# Status sinkronisasi ETL
if PROCESSED_FILE.exists():
    processed_mtime = datetime.fromtimestamp(os.path.getmtime(PROCESSED_FILE))

    # Get last date from processed data (with actual non-null data)
    try:
        processed_df = pd.read_csv(PROCESSED_FILE)
        metadata_cols = ['Row_ID', 'Row_Label', 'Level', 'Children', 'Parent_ID', 'Jenis_Pemilik']
        date_cols = [col for col in processed_df.columns if col not in metadata_cols]

        if len(date_cols) > 0:
            # Find the last column with actual data (non-null values)
            last_data_date = None
            for col in reversed(date_cols):
                if processed_df[col].notna().any():
                    last_data_date = col
                    break

            if last_data_date:
                date_info = f" | Data terakhir: {last_data_date}"
            else:
                date_info = ""
        else:
            date_info = ""
    except:
        date_info = ""

    if os.path.getmtime(SOURCE_FILE) > os.path.getmtime(PROCESSED_FILE):
        st.warning(f"⚠️ Data sumber lebih baru dari data yang diproses. Klik **Sync Data** untuk update.")
    else:
        st.success(f"✅ Data sudah tersinkronisasi (terakhir diproses: {processed_mtime.strftime('%Y-%m-%d %H:%M')}{date_info})")
else:
    st.warning("⚠️ Belum ada data yang diproses. Klik **Sync Data** untuk memproses data pertama kali.")

# Sync button
if st.button("🔄 Sync Data", type="primary", help="Jalankan ETL pipeline untuk memproses ulang data dari sumber"):
    with st.spinner("⏳ Menjalankan ETL pipeline..."):
        try:
            from etl import run_pipeline
            run_pipeline()
            st.success("✅ Data berhasil di-sync!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error saat sync data: {str(e)}")
