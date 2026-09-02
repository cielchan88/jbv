"""
📊 Fitur Eksternal - unggah dan pantau file fitur eksternal

Halaman ini HANYA menerima file fitur eksternal dari user. Scraper Trading
Economics + FinBERT yang sebelumnya ada di sini sudah dilepas: sumber datanya
sekarang sepenuhnya berada di tangan user, bukan hasil scraping otomatis.

File yang diunggah menggantikan data/external_features.xlsx, yang dibaca oleh
etl/load_external.py dan diteruskan ke pipeline fitur. File lama selalu
dibackup lebih dulu.

Author: APUVA Team
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
import shutil
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etl.load_external import load_external_features, get_external_features_info

st.set_page_config(page_title="Fitur Eksternal", page_icon="📊", layout="wide")

# Kontrak file, harus sama dengan etl/load_external.py
TARGET_PATH = Path("data/external_features.xlsx")
BACKUP_DIR = Path("data/backup")
DATE_COL = "Tanggal"

st.title("📊 Fitur Eksternal")
st.markdown(
    "Unggah file fitur eksternal Anda sendiri. File yang diunggah menggantikan "
    f"`{TARGET_PATH}` yang dibaca pipeline fitur."
)
st.divider()

# ============================================================================
# UNGGAH FILE
# ============================================================================
st.subheader("📤 Unggah File Fitur Eksternal")

with st.expander("📌 Format yang diharapkan", expanded=not TARGET_PATH.exists()):
    st.markdown(f"""
    - Format **.xlsx**, **.xls**, atau **.csv**. Data dibaca dari **sheet pertama**.
    - Wajib ada kolom **`{DATE_COL}`** berisi tanggal. Sisanya dianggap kolom fitur.
    - Satu baris per tanggal - **tanggal tidak boleh terduplikasi**.
    - Kolom fitur sebaiknya numerik. Kolom non-numerik tetap diterima tapi
      tidak akan berguna untuk model.

    Contoh:

    | {DATE_COL} | usdidr | flows_sbn | flows_saham |
    |---|---|---|---|
    | 2024-01-02 | 15485 | -1250.4 | 320.1 |
    | 2024-01-03 | 15510 | 880.0 | -145.7 |
    """)

uploaded = st.file_uploader(
    "Pilih file fitur eksternal",
    type=["xlsx", "xls", "csv"],
    help="Menggantikan file yang sekarang dipakai. File lama dibackup otomatis.",
)


def read_upload(f):
    """Baca file unggahan; kembalikan (df, error)."""
    try:
        if f.name.lower().endswith(".csv"):
            return pd.read_csv(f), None
        return pd.read_excel(f, sheet_name=0), None
    except Exception as e:
        return None, f"File tidak bisa dibaca: {e}"


def validate(df):
    """
    Periksa file terhadap kontrak yang dipakai etl/load_external.py.

    Mengembalikan (errors, warnings). Errors memblokir penyimpanan; warnings
    hanya diberitahukan. Pemisahan ini disengaja: file yang tanggalnya bolong
    atau tidak mencakup periode terbaru tetap SAH untuk disimpan - user mungkin
    memang punya data separuh - tapi file tanpa kolom Tanggal atau dengan
    tanggal ganda akan merusak pipeline di hilir tanpa pesan yang jelas.
    """
    errors, warns = [], []

    if df is None or len(df) == 0:
        return ["File kosong."], []

    if DATE_COL not in df.columns:
        mirip = [c for c in df.columns if str(c).strip().lower() == DATE_COL.lower()]
        if mirip:
            errors.append(
                f"Kolom tanggal bernama `{mirip[0]}` - harus persis `{DATE_COL}` "
                f"(perhatikan spasi dan huruf besar/kecil)."
            )
        else:
            errors.append(
                f"Tidak ada kolom `{DATE_COL}`. Kolom yang ditemukan: "
                f"{', '.join(str(c) for c in df.columns[:10])}"
            )
        return errors, warns

    dt = pd.to_datetime(df[DATE_COL], errors="coerce")
    n_bad = int(dt.isna().sum())
    if n_bad == len(df):
        errors.append(f"Tidak satu pun nilai di kolom `{DATE_COL}` bisa dibaca sebagai tanggal.")
        return errors, warns
    if n_bad > 0:
        errors.append(f"{n_bad} baris punya tanggal yang tidak bisa dibaca.")

    dup = int(dt.duplicated().sum())
    if dup > 0:
        errors.append(
            f"{dup} tanggal terduplikasi. Pipeline mengasumsikan satu baris per "
            f"tanggal; duplikat membuat penyelarasan ke deret SDV tidak menentu."
        )

    feat_cols = [c for c in df.columns if c != DATE_COL]
    if not feat_cols:
        errors.append("Tidak ada kolom fitur - file hanya berisi kolom tanggal.")

    non_num = [c for c in feat_cols
               if not pd.api.types.is_numeric_dtype(pd.to_numeric(df[c], errors="coerce"))]
    all_nan = [c for c in feat_cols if pd.to_numeric(df[c], errors="coerce").notna().sum() == 0]
    if all_nan:
        warns.append(f"{len(all_nan)} kolom tidak punya satu pun nilai numerik: "
                     f"{', '.join(str(c) for c in all_nan[:5])}")

    if not dt.is_monotonic_increasing:
        warns.append("Tanggal tidak terurut menaik - akan diurutkan otomatis saat disimpan.")

    valid_dt = dt.dropna()
    if len(valid_dt) > 1:
        full = pd.date_range(valid_dt.min(), valid_dt.max(), freq="D")
        miss = len(full.difference(valid_dt))
        if miss > 0:
            warns.append(f"{miss} tanggal kalender tidak ada di antara "
                         f"{valid_dt.min().date()} dan {valid_dt.max().date()}.")

    return errors, warns


if uploaded is not None:
    df_new, read_err = read_upload(uploaded)

    if read_err:
        st.error(f"❌ {read_err}")
    else:
        errors, warns = validate(df_new)

        c1, c2, c3, c4 = st.columns(4)
        _dt = pd.to_datetime(df_new[DATE_COL], errors="coerce") if DATE_COL in df_new.columns else pd.Series(dtype="datetime64[ns]")
        with c1:
            st.metric("Baris", f"{len(df_new):,}")
        with c2:
            st.metric("Kolom fitur", max(len(df_new.columns) - 1, 0))
        with c3:
            st.metric("Tanggal awal", str(_dt.min().date()) if _dt.notna().any() else "—")
        with c4:
            st.metric("Tanggal akhir", str(_dt.max().date()) if _dt.notna().any() else "—")

        for e in errors:
            st.error(f"❌ {e}")
        for w in warns:
            st.warning(f"⚠️ {w}")

        # ---- Bandingkan dengan file yang sedang dipakai ----
        if TARGET_PATH.exists() and not errors:
            try:
                cur = pd.read_excel(TARGET_PATH, sheet_name=0)
                cur_cols = set(cur.columns) - {DATE_COL}
                new_cols = set(df_new.columns) - {DATE_COL}
                hilang, tambah = sorted(cur_cols - new_cols), sorted(new_cols - cur_cols)

                st.markdown("**Perbandingan dengan file yang sedang dipakai**")
                d1, d2 = st.columns(2)
                with d1:
                    st.write(f"Sekarang: **{len(cur):,}** baris, **{len(cur_cols)}** fitur")
                with d2:
                    st.write(f"Setelah diganti: **{len(df_new):,}** baris, **{len(new_cols)}** fitur")

                if hilang:
                    st.error(
                        f"🚨 **{len(hilang)} kolom akan HILANG**: {', '.join(str(c) for c in hilang)}. "
                        f"Kalau kolom ini dipakai model, fiturnya ikut hilang."
                    )
                if tambah:
                    st.info(f"➕ {len(tambah)} kolom baru: {', '.join(str(c) for c in tambah)}")
                if not hilang and not tambah:
                    st.success("✅ Susunan kolom sama persis dengan file sekarang.")
            except Exception as e:
                st.warning(f"⚠️ Tidak bisa membandingkan dengan file lama: {e}")

        # ---- Cakupan terhadap data SDV ----
        if not errors and _dt.notna().any():
            try:
                from utils.data_loader import load_etl_output
                _sdv, _meta, _tcols = load_etl_output()
                sdv_end = pd.to_datetime(_tcols[-1])
                lag = (sdv_end - _dt.max()).days
                if lag > 30:
                    st.warning(
                        f"⚠️ Fitur eksternal berakhir {_dt.max().date()}, sedangkan data SDV "
                        f"sampai {sdv_end.date()} - tertinggal **{lag} hari**. Periode itu "
                        f"tidak akan punya nilai fitur eksternal."
                    )
            except Exception:
                pass

        st.markdown("**Pratinjau (10 baris pertama)**")
        st.dataframe(df_new.head(10), use_container_width=True)

        if errors:
            st.info("Perbaiki kesalahan di atas, lalu unggah ulang.")
        else:
            st.divider()
            konfirm = st.checkbox(
                f"Saya paham file ini akan menggantikan `{TARGET_PATH}`"
                + (" dan menghilangkan kolom yang disebut di atas" if TARGET_PATH.exists() else "")
            )
            if st.button("💾 Simpan sebagai fitur eksternal", type="primary", disabled=not konfirm):
                try:
                    TARGET_PATH.parent.mkdir(parents=True, exist_ok=True)

                    backup_msg = ""
                    if TARGET_PATH.exists():
                        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        bak = BACKUP_DIR / f"external_features_{stamp}.xlsx"
                        shutil.copy2(TARGET_PATH, bak)
                        backup_msg = f" File lama dibackup ke `{bak}`."

                    out = df_new.copy()
                    out[DATE_COL] = pd.to_datetime(out[DATE_COL], errors="coerce")
                    out = out.dropna(subset=[DATE_COL]).sort_values(DATE_COL).reset_index(drop=True)
                    out.to_excel(TARGET_PATH, index=False)

                    st.cache_data.clear()
                    st.success(f"✅ Tersimpan: {len(out):,} baris, "
                               f"{len(out.columns) - 1} fitur.{backup_msg}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Gagal menyimpan: {e}")

st.divider()

# ============================================================================
# STATUS FILE YANG SEDANG DIPAKAI
# ============================================================================


@st.cache_data
def load_external_data():
    try:
        df, external_dict = load_external_features(sheet_name=None)
        return df, external_dict, None
    except FileNotFoundError:
        return None, None, "File tidak ditemukan"
    except Exception as e:
        return None, None, f"Error: {str(e)}"


df_ext, ext_dict, error = load_external_data()

if error:
    st.info(f"ℹ️ Belum ada fitur eksternal yang aktif ({error}). Unggah file di atas untuk memulai.")
    st.stop()

info = get_external_features_info()

st.subheader("📦 File yang Sedang Dipakai")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("📁 File", "✅ Tersedia")
with col2:
    st.metric("📊 Jumlah Features", info.get("num_features", 0))
with col3:
    st.metric("📅 Total Rows", info.get("num_rows", 0))
with col4:
    st.metric("💾 Size", f"{info.get('file_size_kb', 0):.1f} KB")

# Fitur eksternal bisa saja dimatikan di pipeline. Kalau ya, itu harus terlihat
# di sini - kalau tidak, user bisa mengunggah file berkali-kali dan bingung
# kenapa tidak ada pengaruhnya pada hasil model.
try:
    from utils.external_loader import ENABLE_EXTERNAL_FEATURES
    if not ENABLE_EXTERNAL_FEATURES:
        st.warning(
            "⚠️ **Fitur eksternal sedang DIMATIKAN di pipeline** "
            "(`ENABLE_EXTERNAL_FEATURES = False` di `utils/external_loader.py`). "
            "File di halaman ini tetap tersimpan dan terpantau, tapi **tidak diteruskan "
            "ke model mana pun** sampai saklar itu dinyalakan."
        )
except Exception:
    pass

st.divider()

st.subheader("📅 Informasi Data")
if "date_range" in info:
    st.write(f"**Tanggal Awal:** `{info['date_range']['start']}`")
    st.write(f"**Tanggal Akhir:** `{info['date_range']['end']}`")
    _s = pd.to_datetime(info["date_range"]["start"])
    _e = pd.to_datetime(info["date_range"]["end"])
    st.write(f"**Durasi:** {(_e - _s).days} hari")

dates = pd.to_datetime(df_ext[DATE_COL])
missing_dates = pd.date_range(dates.min(), dates.max(), freq="D").difference(dates)

if len(missing_dates) == 0:
    st.success("✅ **Status:** Data lengkap, tidak ada gap")
else:
    st.warning(f"⚠️ **Status:** Ada **{len(missing_dates)} tanggal** yang hilang")
    with st.expander("📋 Lihat tanggal yang hilang"):
        st.dataframe(
            pd.DataFrame({
                "Missing Date": missing_dates.strftime("%Y-%m-%d"),
                "Day": missing_dates.strftime("%A"),
            }),
            use_container_width=True, hide_index=True,
        )

st.divider()

st.subheader("📋 Daftar Features")
if info.get("features"):
    _feats = info["features"]
    _cov = []
    for f in _feats:
        s = pd.to_numeric(df_ext[f], errors="coerce") if f in df_ext.columns else pd.Series(dtype=float)
        _cov.append({
            "No": len(_cov) + 1,
            "Feature Name": f,
            "Terisi": f"{s.notna().sum():,} / {len(df_ext):,}",
            "Min": round(float(s.min()), 3) if s.notna().any() else None,
            "Maks": round(float(s.max()), 3) if s.notna().any() else None,
        })
    st.dataframe(pd.DataFrame(_cov), use_container_width=True, hide_index=True)

st.divider()

st.subheader("📈 Data")
st.dataframe(df_ext, use_container_width=True, height=600)
