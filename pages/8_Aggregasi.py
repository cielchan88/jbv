"""
Aggregasi - Period Aggregation View

Aggregates daily forecast data into different timeframes:
- Harian (Daily) - original data
- Mingguan (Weekly) - sum of each week
- Bulanan (Monthly) - sum of each month
- Per RDG (Board of Governors Meeting) - sum per RDG period
"""

import streamlit as st
import pandas as pd
import numpy as np
import json
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from io import BytesIO

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Aggregasi - JBV Dashboard", layout="wide")

# Import utils
from utils.forecast_version import list_forecast_versions, load_forecast_version, format_timestamp

st.title("📊 Aggregasi Periode")
st.markdown("Agregasi data forecast harian ke berbagai timeframe: Harian, Mingguan, Bulanan, dan Per RDG.")

st.divider()

# ========================================================================
# HELPER FUNCTIONS
# ========================================================================

def load_rdg_schedule():
    """Load RDG schedule from config file"""
    config_path = Path(__file__).parent.parent / "config" / "rdg_schedule.json"
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
            return data.get('schedule', [])
    except FileNotFoundError:
        st.warning("⚠️ File config/rdg_schedule.json tidak ditemukan. Fitur RDG tidak tersedia.")
        return []
    except Exception as e:
        st.error(f"❌ Error loading RDG schedule: {str(e)}")
        return []


def aggregate_weekly(df, date_cols):
    """Aggregate daily data to weekly sum"""
    df_result = df.copy()

    # Convert date columns to datetime for grouping
    dates = pd.to_datetime(date_cols)

    # Create week mapping (ISO week)
    week_map = {}
    for date_str in date_cols:
        dt = pd.to_datetime(date_str)
        # Get Monday of that week as the week identifier
        week_start = dt - timedelta(days=dt.weekday())
        week_key = week_start.strftime('%Y-%m-%d')
        if week_key not in week_map:
            week_map[week_key] = []
        week_map[week_key].append(date_str)

    # Create aggregated columns
    agg_data = {}
    for week_key in sorted(week_map.keys()):
        week_dates = week_map[week_key]
        week_end = pd.to_datetime(week_key) + timedelta(days=6)
        col_name = f"W {week_key} - {week_end.strftime('%Y-%m-%d')}"

        # Sum values for this week
        df_result[col_name] = df[week_dates].sum(axis=1)
        agg_data[col_name] = week_dates

    # Return only aggregated columns
    meta_cols = ['Row_ID', 'Row_Label', 'Level']
    agg_cols = [col for col in df_result.columns if col.startswith('W ')]

    return df_result[meta_cols + agg_cols], agg_data


def aggregate_monthly(df, date_cols):
    """Aggregate daily data to monthly sum"""
    df_result = df.copy()

    # Create month mapping
    month_map = {}
    for date_str in date_cols:
        dt = pd.to_datetime(date_str)
        month_key = dt.strftime('%Y-%m')
        if month_key not in month_map:
            month_map[month_key] = []
        month_map[month_key].append(date_str)

    # Create aggregated columns
    agg_data = {}
    for month_key in sorted(month_map.keys()):
        month_dates = month_map[month_key]
        dt = pd.to_datetime(month_key + '-01')
        col_name = dt.strftime('%B %Y')  # e.g., "January 2025"

        # Sum values for this month
        df_result[col_name] = df[month_dates].sum(axis=1)
        agg_data[col_name] = month_dates

    # Return only aggregated columns
    meta_cols = ['Row_ID', 'Row_Label', 'Level']
    agg_cols = list(agg_data.keys())

    return df_result[meta_cols + agg_cols], agg_data


def aggregate_rdg(df, date_cols, rdg_schedule):
    """Aggregate daily data to RDG period sum"""
    df_result = df.copy()

    if not rdg_schedule:
        st.warning("⚠️ RDG schedule tidak tersedia")
        return df_result, {}

    # Create RDG period mapping
    rdg_map = {}
    for rdg in rdg_schedule:
        rdg_id = rdg['id']
        start_date = pd.to_datetime(rdg['start_date'])
        end_date = pd.to_datetime(rdg['end_date'])

        # Find dates within this RDG period
        period_dates = []
        for date_str in date_cols:
            dt = pd.to_datetime(date_str)
            if start_date <= dt <= end_date:
                period_dates.append(date_str)

        if period_dates:
            rdg_map[rdg_id] = {
                'dates': period_dates,
                'period': rdg['period'],
                'rdg_date': rdg['rdg_date']
            }

    # Create aggregated columns
    agg_data = {}
    for rdg_id, rdg_info in rdg_map.items():
        col_name = f"{rdg_info['period']} (RDG: {rdg_info['rdg_date']})"
        period_dates = rdg_info['dates']

        # Sum values for this RDG period
        df_result[col_name] = df[period_dates].sum(axis=1)
        agg_data[col_name] = period_dates

    # Return only aggregated columns
    meta_cols = ['Row_ID', 'Row_Label', 'Level']
    agg_cols = list(agg_data.keys())

    return df_result[meta_cols + agg_cols], agg_data


# ========================================================================
# SIDEBAR - VERSION SELECTION & TIMEFRAME
# ========================================================================

st.sidebar.header("⚙️ Pengaturan")

# Load available forecast versions
versions = list_forecast_versions()

if not versions:
    st.warning("⚠️ Belum ada versi forecast yang tersimpan.")
    st.info("💡 Silakan generate forecast terlebih dahulu di halaman **📋 Lembar Kerja**")
    st.stop()

# Version selection
version_options = {f"{v['version_id']} ({format_timestamp(v['timestamp'])})" : v['version_id'] for v in versions}
selected_version_label = st.sidebar.selectbox(
    "Pilih Versi Forecast:",
    options=list(version_options.keys()),
    help="Pilih versi forecast yang ingin diagregasi"
)
selected_version_id = version_options[selected_version_label]

# Load selected version
df_forecast, metadata = load_forecast_version(selected_version_id)

if df_forecast is None:
    st.error(f"❌ Gagal memuat versi {selected_version_id}")
    st.stop()

# Get date columns
future_date_cols = metadata.get('future_date_cols', [])
time_cols = metadata.get('time_cols', [])

# All date columns (historical + forecast)
all_date_cols = time_cols + future_date_cols

st.sidebar.success(f"✅ Versi **{selected_version_id}** dimuat")
st.sidebar.caption(f"Forecast: {len(future_date_cols)} hari | Historical: {len(time_cols)} hari")

st.sidebar.divider()

# Timeframe selection
timeframe = st.sidebar.selectbox(
    "Pilih Timeframe:",
    options=['Harian', 'Mingguan', 'Bulanan', 'Per RDG'],
    help="Agregasi data forecast ke timeframe yang dipilih"
)

# Date range filter
st.sidebar.subheader("📅 Filter Tanggal")

use_date_filter = st.sidebar.checkbox("Filter rentang tanggal", value=False)

if use_date_filter:
    min_date = pd.to_datetime(all_date_cols[0])
    max_date = pd.to_datetime(all_date_cols[-1])

    date_range = st.sidebar.date_input(
        "Rentang tanggal:",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    if len(date_range) == 2:
        start_date, end_date = date_range
        # Filter date columns
        filtered_date_cols = [
            col for col in all_date_cols
            if start_date <= pd.to_datetime(col).date() <= end_date
        ]
    else:
        filtered_date_cols = all_date_cols
else:
    filtered_date_cols = all_date_cols

# Data type selection
st.sidebar.subheader("📊 Tipe Data")
data_type = st.sidebar.radio(
    "Tampilkan data:",
    options=['Forecast Only', 'Historical + Forecast', 'Historical Only'],
    help="Pilih data yang ingin ditampilkan"
)

if data_type == 'Forecast Only':
    display_date_cols = [col for col in filtered_date_cols if col in future_date_cols]
elif data_type == 'Historical Only':
    display_date_cols = [col for col in filtered_date_cols if col in time_cols]
else:
    display_date_cols = filtered_date_cols

if not display_date_cols:
    st.warning("⚠️ Tidak ada data untuk rentang tanggal yang dipilih")
    st.stop()

# ========================================================================
# MAIN CONTENT - AGGREGATED VIEW
# ========================================================================

# Version info
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Versi Forecast", selected_version_id)
with col2:
    st.metric("Timeframe", timeframe)
with col3:
    st.metric("Total Tanggal", len(display_date_cols))
with col4:
    st.metric("Model Mode", metadata.get('model_mode', '-'))

st.divider()

# Load RDG schedule for RDG timeframe
rdg_schedule = load_rdg_schedule()

# Perform aggregation based on selected timeframe
if timeframe == 'Harian':
    # No aggregation - show original data
    meta_cols = ['Row_ID', 'Row_Label', 'Level']
    df_display = df_forecast[meta_cols + display_date_cols].copy()
    agg_data = {col: [col] for col in display_date_cols}
    st.subheader(f"📅 Data Harian ({len(display_date_cols)} hari)")

elif timeframe == 'Mingguan':
    df_display, agg_data = aggregate_weekly(df_forecast, display_date_cols)
    st.subheader(f"📅 Data Mingguan ({len(agg_data)} minggu)")

elif timeframe == 'Bulanan':
    df_display, agg_data = aggregate_monthly(df_forecast, display_date_cols)
    st.subheader(f"📅 Data Bulanan ({len(agg_data)} bulan)")

else:  # Per RDG
    if not rdg_schedule:
        st.error("❌ RDG schedule tidak tersedia. Silakan buat file config/rdg_schedule.json")
        st.stop()

    df_display, agg_data = aggregate_rdg(df_forecast, display_date_cols, rdg_schedule)
    st.subheader(f"📅 Data Per RDG ({len(agg_data)} periode)")

# Show aggregation summary
if timeframe != 'Harian':
    with st.expander("📋 Detail Agregasi"):
        st.markdown(f"**{timeframe}** mengagregasi {len(display_date_cols)} hari menjadi {len(agg_data)} periode:")

        agg_summary = []
        for period_name, dates in agg_data.items():
            agg_summary.append({
                'Periode': period_name,
                'Jumlah Hari': len(dates),
                'Tanggal Awal': dates[0] if dates else '-',
                'Tanggal Akhir': dates[-1] if dates else '-'
            })

        st.dataframe(pd.DataFrame(agg_summary), width='stretch')

# Display data table
st.dataframe(df_display, width='stretch', height=500)

# ========================================================================
# VISUALIZATION - NET SUPPLY DEMAND VALAS (D)
# ========================================================================

st.divider()
st.subheader("📈 Visualisasi Net Supply Demand Valas (D)")

# Get row D values
d_row = df_display[df_display['Row_ID'] == 'D']

if len(d_row) > 0:
    import plotly.graph_objects as go

    # Get aggregated columns (exclude metadata)
    meta_cols = ['Row_ID', 'Row_Label', 'Level']
    value_cols = [col for col in df_display.columns if col not in meta_cols]

    # Extract values
    d_values = d_row[value_cols].values.flatten()

    # Create figure
    fig = go.Figure()

    # Determine colors based on data type
    if data_type == 'Forecast Only':
        line_color = 'red'
        line_dash = 'dot'
        name = 'Forecast'
    elif data_type == 'Historical Only':
        line_color = 'gray'
        line_dash = 'solid'
        name = 'Historical'
    else:
        # Mixed - need to identify which are historical vs forecast
        line_color = 'blue'
        line_dash = 'solid'
        name = 'Historical + Forecast'

    # Add bar chart for aggregated view
    if timeframe != 'Harian':
        fig.add_trace(go.Bar(
            x=value_cols,
            y=d_values,
            name=timeframe,
            marker_color='steelblue',
            hovertemplate='%{x}: %{y:,.0f}<extra></extra>'
        ))
    else:
        # Line chart for daily view
        fig.add_trace(go.Scatter(
            x=value_cols,
            y=d_values,
            mode='lines',
            line=dict(color=line_color, dash=line_dash, width=2),
            name=name,
            hovertemplate='%{x}: %{y:,.0f}<extra></extra>'
        ))

    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    # Determine max ticks based on timeframe (fewer ticks to prevent overlap with horizontal labels)
    if timeframe == 'Harian':
        max_ticks = 10
    elif timeframe == 'Mingguan':
        max_ticks = 6
    else:
        max_ticks = 8

    # Update layout
    fig.update_layout(
        title=f"Net Supply Demand Valas (D) - {timeframe}",
        xaxis_title="Periode",
        yaxis_title="Value (USD Juta)",
        hovermode='x unified',
        height=500,
        xaxis_tickangle=0,
        xaxis_nticks=max_ticks
    )

    st.plotly_chart(fig, width='stretch')

    # Statistics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total", f"{np.sum(d_values):,.0f}")
    with col2:
        st.metric("Rata-rata", f"{np.mean(d_values):,.0f}")
    with col3:
        st.metric("Min", f"{np.min(d_values):,.0f}")
    with col4:
        st.metric("Max", f"{np.max(d_values):,.0f}")

else:
    st.warning("⚠️ Row D tidak ditemukan dalam data")

# ========================================================================
# RDG SCHEDULE MANAGEMENT
# ========================================================================

st.divider()
st.subheader("🗓️ Jadwal RDG (Rapat Dewan Gubernur)")

if rdg_schedule:
    # Show current RDG schedule
    rdg_df = pd.DataFrame(rdg_schedule)
    rdg_df = rdg_df[['id', 'period', 'start_date', 'end_date', 'rdg_date', 'notes']]
    rdg_df.columns = ['ID', 'Periode', 'Tanggal Mulai', 'Tanggal Selesai', 'Tanggal RDG', 'Catatan']

    st.dataframe(rdg_df, width='stretch')

    st.caption("""
    💡 **Cara update jadwal RDG:**
    1. Edit file `config/rdg_schedule.json`
    2. Sesuaikan `start_date`, `end_date`, dan `rdg_date` untuk setiap periode
    3. Refresh halaman ini untuk melihat perubahan
    """)
else:
    st.info("ℹ️ Jadwal RDG belum dikonfigurasi. Buat file `config/rdg_schedule.json`")

# ========================================================================
# DOWNLOAD SECTION
# ========================================================================

st.divider()
st.subheader("📥 Download Data Agregasi")

# Prepare download buffer
buffer = BytesIO()

with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    # Sheet 1: Aggregated Data
    sheet_name = f'SDV_{timeframe.replace(" ", "_")}'
    df_display.to_excel(writer, index=False, sheet_name=sheet_name)

    # Sheet 2: Metadata
    metadata_rows = [
        ['Version ID', selected_version_id],
        ['Timestamp', format_timestamp(metadata.get('timestamp', ''))],
        ['Timeframe', timeframe],
        ['Data Type', data_type],
        ['Total Periods', len(agg_data)],
        ['Original Days', len(display_date_cols)],
        ['Model Mode', metadata.get('model_mode', '-')],
        ['Forecast Days', metadata.get('forecast_days', 0)],
    ]

    df_metadata = pd.DataFrame(metadata_rows, columns=['Parameter', 'Value'])
    df_metadata.to_excel(writer, index=False, sheet_name='Metadata')

    # Sheet 3: Aggregation Details (if not daily)
    if timeframe != 'Harian' and agg_data:
        agg_details = []
        for period_name, dates in agg_data.items():
            agg_details.append({
                'Period': period_name,
                'Days_Count': len(dates),
                'Start_Date': dates[0] if dates else '',
                'End_Date': dates[-1] if dates else '',
                'Dates': ', '.join(dates[:5]) + ('...' if len(dates) > 5 else '')
            })

        df_agg_details = pd.DataFrame(agg_details)
        df_agg_details.to_excel(writer, index=False, sheet_name='Aggregation Details')

buffer.seek(0)

# Download button
filename = f"sdv_{timeframe.lower().replace(' ', '_')}_{selected_version_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

st.download_button(
    label=f"📥 Download Data {timeframe}",
    data=buffer,
    file_name=filename,
    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    type="primary",
    width='stretch'
)

st.caption(f"""
💡 File berisi:
- **{sheet_name}**: Data agregasi {timeframe}
- **Metadata**: Informasi versi dan parameter
{f'- **Aggregation Details**: Detail periode agregasi' if timeframe != 'Harian' else ''}
""")

# Footer
st.divider()
st.caption("📊 Aggregasi - Agregasi periode untuk analisis dan presentasi RDG.")
