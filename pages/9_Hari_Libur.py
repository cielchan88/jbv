import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="Hari Libur - JBV Dashboard", layout="wide")

st.title("📅 Hari Libur")
st.markdown("Kelola data hari libur untuk forecasting model.")

st.divider()

# Path to holidays JSON file
BASE_DIR = Path(__file__).parent.parent
HOLIDAYS_FILE = BASE_DIR / "config" / "holidays.json"

# Initialize holidays data
def load_holidays():
    """Load holidays from JSON file"""
    if os.path.exists(HOLIDAYS_FILE):
        try:
            with open(HOLIDAYS_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_holidays(holidays):
    """Save holidays to JSON file"""
    with open(HOLIDAYS_FILE, 'w') as f:
        json.dump(holidays, f, indent=2)

# Load existing holidays
if 'holidays' not in st.session_state:
    st.session_state.holidays = load_holidays()

# Add new holiday section
st.subheader("➕ Tambah Hari Libur")

col1, col2, col3 = st.columns([2, 3, 2])

with col1:
    new_date = st.date_input("Tanggal", datetime.now(), key='new_date')

with col2:
    new_name = st.text_input("Nama Hari Libur", placeholder="Contoh: Tahun Baru", key='new_name')

with col3:
    category = st.selectbox(
        "Kategori",
        ["Nasional Indonesia", "Federal Reserve", "Cuti Bersama Indonesia"],
        key='new_category'
    )

if st.button("➕ Tambah Hari Libur", width='stretch'):
    if new_name.strip():
        # Check if date already exists
        date_str = new_date.strftime('%Y-%m-%d')
        existing = [h for h in st.session_state.holidays if h['tanggal'] == date_str]

        if existing:
            st.warning(f"⚠️ Tanggal {date_str} sudah ada dalam daftar!")
        else:
            holiday_entry = {
                'tanggal': date_str,
                'nama': new_name.strip(),
                'kategori': category
            }
            st.session_state.holidays.append(holiday_entry)
            # Sort by date
            st.session_state.holidays.sort(key=lambda x: x['tanggal'])
            save_holidays(st.session_state.holidays)
            st.success(f"✅ Hari libur berhasil ditambahkan!")
            st.rerun()
    else:
        st.warning("⚠️ Nama hari libur tidak boleh kosong")

st.divider()

# Display and manage holidays
st.subheader("📋 Daftar Hari Libur")

if st.session_state.holidays:
    # Create DataFrame for display
    df_holidays = pd.DataFrame(st.session_state.holidays)
    df_holidays['tanggal'] = pd.to_datetime(df_holidays['tanggal'])

    # Filter options
    col1, col2, col3 = st.columns([2, 2, 2])

    with col1:
        year_filter = st.selectbox(
            "Filter Tahun",
            ["Semua"] + sorted(df_holidays['tanggal'].dt.year.unique().tolist(), reverse=True),
            key='year_filter'
        )

    with col2:
        category_filter = st.selectbox(
            "Filter Kategori",
            ["Semua", "Nasional Indonesia", "Federal Reserve", "Cuti Bersama Indonesia"],
            key='category_filter'
        )

    # Apply filters
    df_filtered = df_holidays.copy()
    if year_filter != "Semua":
        df_filtered = df_filtered[df_filtered['tanggal'].dt.year == year_filter]
    if category_filter != "Semua":
        df_filtered = df_filtered[df_filtered['kategori'] == category_filter]

    # Format date for display
    df_display = df_filtered.copy()
    df_display['tanggal'] = df_display['tanggal'].dt.strftime('%Y-%m-%d')
    df_display = df_display.rename(columns={
        'tanggal': 'Tanggal',
        'nama': 'Nama Hari Libur',
        'kategori': 'Kategori'
    })

    st.dataframe(df_display, width='stretch', hide_index=True)

    st.markdown(f"**Total: {len(df_filtered)} hari libur**")

    st.divider()

    # Edit/Delete section
    st.subheader("✏️ Edit / Hapus Hari Libur")

    # Select holiday to edit/delete
    holiday_options = [f"{h['tanggal']} - {h['nama']}" for h in st.session_state.holidays]
    selected_holiday = st.selectbox("Pilih Hari Libur", holiday_options, key='select_holiday')

    if selected_holiday:
        selected_index = holiday_options.index(selected_holiday)
        selected_data = st.session_state.holidays[selected_index]

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Edit Hari Libur")
            edit_date = st.date_input(
                "Tanggal",
                datetime.strptime(selected_data['tanggal'], '%Y-%m-%d'),
                key='edit_date'
            )
            edit_name = st.text_input(
                "Nama Hari Libur",
                value=selected_data['nama'],
                key='edit_name'
            )
            categories = ["Nasional Indonesia", "Federal Reserve", "Cuti Bersama Indonesia"]
            edit_category = st.selectbox(
                "Kategori",
                categories,
                index=categories.index(selected_data['kategori']) if selected_data['kategori'] in categories else 0,
                key='edit_category'
            )

            if st.button("💾 Simpan Perubahan", width='stretch'):
                if edit_name.strip():
                    st.session_state.holidays[selected_index] = {
                        'tanggal': edit_date.strftime('%Y-%m-%d'),
                        'nama': edit_name.strip(),
                        'kategori': edit_category
                    }
                    # Sort by date
                    st.session_state.holidays.sort(key=lambda x: x['tanggal'])
                    save_holidays(st.session_state.holidays)
                    st.success("✅ Perubahan berhasil disimpan!")
                    st.rerun()
                else:
                    st.warning("⚠️ Nama tidak boleh kosong")

        with col2:
            st.markdown("### Hapus Hari Libur")
            st.warning(f"Anda akan menghapus: **{selected_data['nama']}** ({selected_data['tanggal']})")

            if st.button("🗑️ Hapus Hari Libur", type="primary", width='stretch'):
                st.session_state.holidays.pop(selected_index)
                save_holidays(st.session_state.holidays)
                st.success("✅ Hari libur berhasil dihapus!")
                st.rerun()

    st.divider()

    # Bulk actions
    col1, col2 = st.columns(2)

    with col1:
        if st.button("🗑️ Hapus Semua Hari Libur", width='stretch'):
            st.session_state.holidays = []
            save_holidays(st.session_state.holidays)
            st.success("✅ Semua hari libur berhasil dihapus!")
            st.rerun()

    with col2:
        # Export to Excel
        from io import BytesIO
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_display.to_excel(writer, index=False, sheet_name='Hari Libur')
        buffer.seek(0)

        st.download_button(
            label="📥 Download Excel",
            data=buffer,
            file_name=f"hari_libur_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            width='stretch'
        )

else:
    st.info("📝 Belum ada hari libur yang ditambahkan.")
    st.markdown("""
    **Tips:**
    - Tambahkan hari libur nasional untuk meningkatkan akurasi forecasting
    - Data hari libur akan digunakan sebagai fitur dalam model prediksi
    - Pastikan tanggal yang dimasukkan akurat
    """)
