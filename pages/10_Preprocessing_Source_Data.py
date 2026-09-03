import streamlit as st
import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime
from io import BytesIO

from etl.pipeline import SHEET_NAMES as TARGET_SHEETS

st.set_page_config(page_title="Preprocessing Source Data - JBV Dashboard", layout="wide")

st.title("🧩 Preprocessing Source Data")
st.markdown("""
Gabungkan file mentah (hasil export laporan Cognos BI) menjadi satu file `source-data.xlsx`
yang siap dipakai dashboard. Halaman ini otomatis membuang baris/kolom metadata laporan dan
mengekstrak data sesuai format yang dibutuhkan pipeline ETL.
""")

st.divider()

BASE_DIR = Path(__file__).parent.parent
SOURCE_FILE = BASE_DIR / "data" / "raw" / "source-data.xlsx"
BACKUP_DIR = BASE_DIR / "data" / "raw" / "backup"


def excel_col_to_index(col_str: str) -> int:
    """Convert Excel column letter (e.g. 'AV') to 0-indexed column position."""
    col_str = col_str.strip().upper()
    result = 0
    for ch in col_str:
        if not ch.isalpha():
            raise ValueError(f"'{col_str}' bukan huruf kolom Excel yang valid")
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def index_to_excel_col(idx: int) -> str:
    """Convert 0-indexed column position back to Excel column letter."""
    idx += 1
    letters = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def extract_sheet(file, sheet_name: str, data_start_row: int, date_col_idx: int, end_col_idx: int) -> pd.DataFrame:
    """
    Ekstrak satu sheet mentah menjadi format target (kolom 1=tanggal, 2..N=data).

    - Kolom sebelum date_col_idx (mis. kolom A) diabaikan.
    - Baris sebelum data_start_row (metadata/header laporan) diabaikan.
    """
    raw = pd.read_excel(file, sheet_name=sheet_name, header=None)

    extracted = raw.iloc[data_start_row:, date_col_idx:end_col_idx + 1].copy()
    n_cols = end_col_idx - date_col_idx + 1
    extracted.columns = range(1, n_cols + 1)
    extracted = extracted.dropna(how="all").reset_index(drop=True)

    extracted[1] = pd.to_datetime(extracted[1], errors="coerce")
    bad_dates = extracted[1].isna().sum()

    for col in extracted.columns[1:]:
        extracted[col] = pd.to_numeric(extracted[col], errors="coerce")

    return extracted, bad_dates


def find_duplicate_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Return all rows (not just the extras) involved in a duplicated date, sorted by date."""
    dup_mask = df[1].duplicated(keep=False)
    return df[dup_mask].sort_values(1)


def resolve_duplicates(df: pd.DataFrame, strategy: str) -> pd.DataFrame:
    """strategy: 'Baris terakhir' | 'Baris pertama' | 'Jangan diubah otomatis'"""
    if strategy == "Baris terakhir (revisi terbaru)":
        return df.drop_duplicates(subset=[1], keep="last").reset_index(drop=True)
    elif strategy == "Baris pertama":
        return df.drop_duplicates(subset=[1], keep="first").reset_index(drop=True)
    return df


def compare_date_sets(sheets_dict: dict) -> pd.DataFrame:
    """For each sheet, find dates missing relative to the union of dates across all sheets."""
    date_sets = {name: set(df[1].dropna()) for name, df in sheets_dict.items()}
    union = set().union(*date_sets.values())

    rows = []
    for name, dset in date_sets.items():
        missing = union - dset
        if missing:
            missing_sorted = sorted(d.strftime("%Y-%m-%d") for d in missing)
            rows.append({
                "Sheet": name,
                "Jumlah Tanggal Hilang": len(missing),
                "Contoh Tanggal Hilang": ", ".join(missing_sorted[:5]) + (" ..." if len(missing_sorted) > 5 else ""),
            })
    return pd.DataFrame(rows)


# ===== KONFIGURASI EKSTRAKSI =====
with st.expander("⚙️ Konfigurasi Ekstraksi", expanded=False):
    st.markdown("Default di bawah ini sudah sesuai format laporan Korporasi/PTMN/Asing/Individu standar.")
    col1, col2, col3 = st.columns(3)
    with col1:
        data_start_row_1indexed = st.number_input(
            "Baris pertama data (Excel)", min_value=2, value=6, step=1,
            help="Baris ke berapa data pertama dimulai, mis. baris 6 = data mulai dari cell B6/C6"
        )
    with col2:
        date_col_letter = st.text_input("Kolom tanggal (Excel)", value="B")
    with col3:
        end_col_letter = st.text_input("Kolom terakhir data (Excel)", value="AV")

    try:
        date_col_idx = excel_col_to_index(date_col_letter)
        end_col_idx = excel_col_to_index(end_col_letter)
        data_start_row_idx = int(data_start_row_1indexed) - 1
        n_target_cols = end_col_idx - date_col_idx + 1
        st.info(f"ℹ️ Kolom {date_col_letter.upper()} s.d. {end_col_letter.upper()} = **{n_target_cols} kolom** "
                f"(1 tanggal + {n_target_cols - 1} data). Data diambil mulai baris Excel ke-{data_start_row_1indexed}.")
        config_valid = True
    except ValueError as e:
        st.error(f"❌ {e}")
        config_valid = False

st.divider()

# ===== UPLOAD FILE =====
st.subheader("📤 Upload File Sumber")

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.markdown("**File Korporasi & PTMN**")
    st.caption("mis. Korporasi-2021 backup.xlsx")
    file_korp = st.file_uploader("Upload", type=["xlsx"], key="upload_korp", label_visibility="collapsed")
    sheet_korp, sheet_ptmn = None, None
    if file_korp is not None:
        sheets = pd.ExcelFile(file_korp).sheet_names
        default_korp = next((s for s in sheets if s.lower() == "korporasi"), sheets[0])
        default_ptmn = next((s for s in sheets if s.lower() in ("pertamina", "ptmn")), sheets[0])
        sheet_korp = st.selectbox("Sheet untuk Korporasi", sheets, index=sheets.index(default_korp), key="sheet_korp")
        sheet_ptmn = st.selectbox("Sheet untuk PTMN", sheets, index=sheets.index(default_ptmn), key="sheet_ptmn")

with col_b:
    st.markdown("**File Asing**")
    st.caption("mis. Asing-2021.xlsx")
    file_asing = st.file_uploader("Upload", type=["xlsx"], key="upload_asing", label_visibility="collapsed")
    sheet_asing = None
    if file_asing is not None:
        sheets = pd.ExcelFile(file_asing).sheet_names
        default_asing = next((s for s in sheets if s.lower() == "asing"), sheets[0])
        sheet_asing = st.selectbox("Sheet untuk Asing", sheets, index=sheets.index(default_asing), key="sheet_asing")

with col_c:
    st.markdown("**File Individu**")
    st.caption("mis. Individu-2021.xlsx")
    file_individu = st.file_uploader("Upload", type=["xlsx"], key="upload_individu", label_visibility="collapsed")
    sheet_individu = None
    if file_individu is not None:
        sheets = pd.ExcelFile(file_individu).sheet_names
        default_individu = next((s for s in sheets if s.lower() == "individu"), sheets[0])
        sheet_individu = st.selectbox("Sheet untuk Individu", sheets, index=sheets.index(default_individu), key="sheet_individu")

st.divider()

all_uploaded = file_korp is not None and file_asing is not None and file_individu is not None

if not all_uploaded:
    st.info("💡 Upload ketiga file di atas untuk mulai proses ekstraksi.")
    st.stop()

if not config_valid:
    st.error("❌ Perbaiki konfigurasi ekstraksi di atas terlebih dahulu.")
    st.stop()

# ===== PROSES & PREVIEW =====
if st.button("🔍 Proses & Preview", type="primary"):
    jobs = [
        ("Korporasi", file_korp, sheet_korp),
        ("PTMN", file_korp, sheet_ptmn),
        ("Asing", file_asing, sheet_asing),
        ("Individu", file_individu, sheet_individu),
    ]

    results = {}
    has_error = False

    for target_name, src_file, src_sheet in jobs:
        try:
            df, bad_dates = extract_sheet(src_file, src_sheet, data_start_row_idx, date_col_idx, end_col_idx)
            results[target_name] = df

            if bad_dates > 0:
                st.warning(f"⚠️ **{target_name}** (dari sheet '{src_sheet}'): {bad_dates} baris dengan tanggal tidak valid ditemukan.")
        except Exception as e:
            st.error(f"❌ Gagal ekstrak **{target_name}** dari sheet '{src_sheet}': {str(e)}")
            has_error = True

    if not has_error:
        st.session_state["preprocessed_raw"] = results
        st.session_state.pop("preprocessed_sheets", None)
        st.success("✅ Ekstraksi selesai untuk 4 sheet.")

st.divider()

# ===== DETEKSI KUALITAS DATA =====
if "preprocessed_raw" in st.session_state:
    st.subheader("🔎 Deteksi Kualitas Data")

    raw_results = st.session_state["preprocessed_raw"]

    # --- Cek jumlah baris & kolom antar sheet ---
    summary_rows = []
    for name in TARGET_SHEETS:
        df = raw_results[name]
        summary_rows.append({
            "Sheet": name,
            "Baris": len(df),
            "Kolom": len(df.columns),
            "Tanggal Duplikat": int(df[1].duplicated().sum()),
            "Tanggal Awal": df[1].min().strftime("%Y-%m-%d") if df[1].notna().any() else "N/A",
            "Tanggal Akhir": df[1].max().strftime("%Y-%m-%d") if df[1].notna().any() else "N/A",
        })
    summary_df = pd.DataFrame(summary_rows)
    st.dataframe(summary_df, width='stretch', hide_index=True)

    col_counts = summary_df["Kolom"].unique()
    if len(col_counts) > 1:
        st.warning(f"⚠️ Jumlah kolom tidak seragam antar sheet: {dict(zip(summary_df['Sheet'], summary_df['Kolom']))}. "
                   f"Ini bisa menyebabkan masalah saat diproses ETL.")
    elif col_counts[0] != 47:
        st.warning(f"⚠️ Jumlah kolom ({col_counts[0]}) berbeda dari skema standar (47 kolom: 1 tanggal + 46 data). "
                   f"Cek kembali konfigurasi kolom terakhir data.")

    row_counts = summary_df["Baris"].tolist()
    if len(set(row_counts)) > 1:
        st.warning(f"⚠️ Jumlah baris **tidak sama** antar sheet: "
                   f"{dict(zip(summary_df['Sheet'], summary_df['Baris']))}. Lihat detail di bawah untuk cari penyebabnya.")
    else:
        st.success(f"✅ Jumlah baris seragam di keempat sheet ({row_counts[0]} baris).")

    # --- Cek tanggal duplikat per sheet ---
    any_dup = False
    for name in TARGET_SHEETS:
        dup_df = find_duplicate_dates(raw_results[name])
        if len(dup_df) > 0:
            any_dup = True
            n_dates = dup_df[1].nunique()
            with st.expander(f"⚠️ {name}: {n_dates} tanggal terduplikasi ({len(dup_df)} baris terlibat)", expanded=True):
                st.dataframe(dup_df, width='stretch')
    if not any_dup:
        st.success("✅ Tidak ada tanggal terduplikasi di sheet manapun.")

    # --- Cek kesesuaian set tanggal antar sheet ---
    diff_df = compare_date_sets(raw_results)
    if len(diff_df) > 0:
        st.warning("⚠️ Ada tanggal yang muncul di sebagian sheet tapi tidak di sheet lain:")
        st.dataframe(diff_df, width='stretch', hide_index=True)
    else:
        st.success("✅ Set tanggal konsisten — semua sheet punya tanggal yang persis sama.")

    # --- Resolusi duplikat ---
    st.markdown("**Jika ada tanggal duplikat, gunakan:**")
    dedup_strategy = st.selectbox(
        "Strategi resolusi duplikat", label_visibility="collapsed",
        options=["Baris terakhir (revisi terbaru)", "Baris pertama", "Jangan diubah otomatis"],
    )

    final_results = {name: resolve_duplicates(df, dedup_strategy) for name, df in raw_results.items()}
    st.session_state["preprocessed_sheets"] = final_results

    tabs = st.tabs(TARGET_SHEETS)
    for tab, name in zip(tabs, TARGET_SHEETS):
        with tab:
            n_before, n_after = len(raw_results[name]), len(final_results[name])
            if n_before != n_after:
                st.caption(f"{n_before} baris → {n_after} baris setelah resolusi duplikat")
            st.dataframe(final_results[name].head(10), width='stretch')

st.divider()

# ===== SIMPAN / DOWNLOAD =====
if "preprocessed_sheets" in st.session_state:
    st.subheader("💾 Simpan Hasil")

    results = st.session_state["preprocessed_sheets"]

    def build_workbook(sheets_dict) -> bytes:
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            for name in TARGET_SHEETS:
                sheets_dict[name].to_excel(writer, sheet_name=name, index=False)
        buffer.seek(0)
        return buffer.getvalue()

    workbook_bytes = build_workbook(results)

    col_dl, col_save = st.columns(2)

    with col_dl:
        st.download_button(
            "⬇️ Download source-data.xlsx",
            data=workbook_bytes,
            file_name="source-data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch',
        )

    with col_save:
        st.warning("⚠️ Menyimpan akan menimpa `source-data.xlsx` yang sedang dipakai dashboard (file lama dibackup otomatis).")
        if st.button("✅ Simpan sebagai source-data.xlsx di Server", type="primary", width='stretch'):
            try:
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)

                if SOURCE_FILE.exists():
                    backup_file = BACKUP_DIR / f"source-data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    shutil.copy2(SOURCE_FILE, backup_file)

                SOURCE_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(SOURCE_FILE, "wb") as f:
                    f.write(workbook_bytes)

                st.cache_data.clear()
                st.success("✅ source-data.xlsx berhasil disimpan. Jalankan ETL Sync Data di halaman Sumber Data untuk memproses data ini.")
            except Exception as e:
                st.error(f"❌ Gagal menyimpan file: {str(e)}")
