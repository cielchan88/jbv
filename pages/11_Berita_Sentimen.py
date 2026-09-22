"""
📰 Berita & Sentimen - pantau korpus berita dan jalankan tahapan pipeline

Laman ini PEMANTAU dan PELUNCUR, bukan pelaksana. Penarikan dan penilaian
berlangsung puluhan menit sampai berjam-jam, jadi dilepas sebagai proses
terpisah (lihat etl/news/jobs.py) dan laman ini hanya membaca log serta
basis datanya. Kalau dijalankan langsung di dalam permintaan halaman, nginx
dan browser akan memutus sambungan jauh sebelum selesai, dan setiap
interaksi Streamlit berisiko memulai penarikan kedua di atas yang pertama.

Author: APUVA Team
"""

import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etl.news import jobs
from etl.news.daily import DEFAULT_OUT, coverage_report
from etl.news.store import ASSIGN_CUTOFF_HOUR_WIB, DEFAULT_DB, connect, coverage

st.set_page_config(page_title="Berita & Sentimen", page_icon="📰", layout="wide")

st.title("📰 Berita & Sentimen")
st.markdown(
    "Pantau korpus berita dan jalankan tahapan pipeline sentimen. "
    "Hasil akhirnya kolom fitur harian yang digabungkan ke fitur eksternal "
    "saat pemuatan."
)

st.info(
    f"**Penetapan hari bisnis memakai batas {ASSIGN_CUTOFF_HOUR_WIB}.00 WIB.** "
    "Berita yang terbit setelah jam itu masuk ke hari bisnis berikutnya, karena "
    "saat prakiraan disusun berita tersebut belum ada. Mengubah batas ini "
    "mengubah sah atau tidaknya seluruh hasil - ada di `etl/news/store.py`.",
    icon="🕒")

st.divider()

# ============================================================================
# STATUS PEKERJAAN
# ============================================================================
st.subheader("⚙️ Status Pekerjaan")

c1, c2 = st.columns([3, 1])
with c2:
    if st.button("🔄 Muat ulang status", width='stretch'):
        st.rerun()

status = jobs.all_status()
df_status = pd.DataFrame(status)
berjalan = [s for s in status if s['status'] == 'BERJALAN']

with c1:
    if berjalan:
        st.warning(
            f"{len(berjalan)} pekerjaan sedang berjalan: "
            + ", ".join(f"`{s['pekerjaan']}` (pid {s['pid']})" for s in berjalan),
            icon="⏳")
    else:
        st.success("Tidak ada pekerjaan yang sedang berjalan.", icon="✅")

st.dataframe(df_status, width='stretch', hide_index=True)

# ============================================================================
# PELUNCUR
# ============================================================================
st.subheader("🚀 Jalankan Tahapan")

st.caption(
    "Setiap tahap dilepas sebagai proses terpisah dan tetap hidup meskipun "
    "dashboard di-restart. Tombol tidak akan memulai pekerjaan kedua kalau "
    "yang sebelumnya masih berjalan."
)

tab_te, tab_gdelt, tab_situs, tab_olah = st.tabs(
    ["Trading Economics", "GDELT (sejarah panjang)", "Arsip situs", "Nilai & agregasi"])

with tab_te:
    st.markdown(
        "Umpan JSON terstruktur, **lapisan terbaru saja**. Endpoint-nya "
        "berpaginasi dengan offset dari berita terbaru, bukan dengan tanggal, "
        "jadi tahun yang jauh ke belakang tidak akan tercapai. Adapter akan "
        "mengadu di log kalau mentok sebelum sampai."
    )
    a, b = st.columns(2)
    y0 = a.number_input("Tahun awal", 2006, 2030, 2025, key='te_y0')
    y1 = b.number_input("Tahun akhir", 2006, 2030, 2026, key='te_y1')
    if st.button("Tarik Trading Economics", type="primary", key='te_go'):
        st.write(jobs.launch('tarik-te', [y0, y1]))

with tab_gdelt:
    st.markdown(
        "Nada agregat per peristiwa, tersedia **sejak 2006**. Ini satu-satunya "
        "sumber gratis yang menjangkau awal panel. Nadanya dihitung dengan "
        "leksikon umum, bukan model keuangan - jadi lapisan ini **tidak "
        "sepadan** dengan FinBERT dan disimpan terpisah lewat kolom `scorer`."
    )
    st.warning(
        "Jalankan **Validasi skema** dulu. Daftar kolom GDELT tidak bisa "
        "diverifikasi saat pengembangan, jadi validator akan berhenti keras "
        "kalau buku kodenya berubah - itu lebih baik daripada diam-diam "
        "membaca kolom yang salah sebagai nada.", icon="⚠️")
    if st.button("Validasi skema GDELT", key='gd_cek'):
        st.write(jobs.launch('cek', []))
    a, b = st.columns(2)
    g0 = a.number_input("Tahun awal", 2006, 2030, 2006, key='gd_y0')
    g1 = b.number_input("Tahun akhir", 2006, 2030, 2026, key='gd_y1')
    if st.button("Tarik GDELT (berjam-jam)", key='gd_go'):
        st.write(jobs.launch('tarik-gdelt', [g0, g1]))

with tab_situs:
    st.markdown(
        "Arsip indeks harian media Indonesia. Selector HTML **belum teruji** "
        "terhadap halaman sungguhan, dan situs berita berganti tata letak "
        "beberapa kali dalam 20 tahun. Periksa log: hari yang menghasilkan "
        "nol tautan dilaporkan, bukan dianggap hari sepi."
    )
    from etl.news.sources import SITE_CONFIGS
    a, b, c = st.columns(3)
    site = a.selectbox("Situs", sorted(SITE_CONFIGS), key='st_site')
    s0 = b.number_input("Tahun awal", 2006, 2030, 2019, key='st_y0')
    s1 = c.number_input("Tahun akhir", 2006, 2030, 2026, key='st_y1')
    if st.button("Tarik arsip situs", key='st_go'):
        st.write(jobs.launch('tarik-situs', [site, s0, s1]))

with tab_olah:
    st.markdown(
        "**Nilai** menjalankan FinBERT pada artikel yang belum punya skor. "
        "Bisa dilanjutkan: proses yang mati di tengah tinggal dijalankan lagi. "
        "Di CPU kecepatannya puluhan judul per detik, jadi korpus ratusan ribu "
        "artikel berarti hitungan jam.\n\n"
        "**Agregasi** menyusun polaritas harian ke kalender hari kerja panel "
        "dan menulis berkas fiturnya."
    )
    a, b = st.columns(2)
    if a.button("Nilai sentimen (FinBERT)", type="primary", key='nl_go'):
        st.write(jobs.launch('nilai', []))
    if b.button("Agregasi ke fitur harian", key='ag_go'):
        st.write(jobs.launch('agregasi', []))

# penghenti, dipisah supaya tidak tertekan sambil lalu
with st.expander("⏹️ Hentikan pekerjaan"):
    if berjalan:
        pilih = st.selectbox("Pekerjaan", [s['pekerjaan'] for s in berjalan])
        if st.button("Hentikan", key='stop_go'):
            st.write(jobs.stop(pilih))
    else:
        st.caption("Tidak ada yang bisa dihentikan.")

st.divider()

# ============================================================================
# ISI KORPUS
# ============================================================================
st.subheader("📚 Isi Korpus")

if not Path(DEFAULT_DB).exists():
    st.info("Korpus belum ada. Jalankan salah satu tahap penarikan di atas.",
            icon="📭")
else:
    with connect(DEFAULT_DB) as con:
        cov = coverage(con)
    if cov.empty:
        st.info("Korpus masih kosong.", icon="📭")
    else:
        a, b, c = st.columns(3)
        a.metric("Total artikel", f"{int(cov['artikel'].sum()):,}")
        b.metric("Sudah dinilai", f"{int(cov['dinilai'].sum()):,}")
        c.metric("Sumber", cov['source'].nunique())

        st.dataframe(cov, width='stretch', hide_index=True)

        fig = px.bar(cov, x='tahun', y='artikel', color='source',
                     title='Artikel per tahun per sumber',
                     labels={'artikel': 'jumlah artikel', 'tahun': ''})
        st.plotly_chart(fig, width='stretch')

        belum = int(cov['artikel'].sum() - cov['dinilai'].sum())
        if belum > 0:
            st.warning(f"{belum:,} artikel belum dinilai. Jalankan tahap "
                       f"**Nilai sentimen**.", icon="🤖")

st.divider()

# ============================================================================
# HASIL AGREGASI
# ============================================================================
st.subheader("📈 Fitur Harian")

if not DEFAULT_OUT.exists():
    st.info("Belum ada hasil agregasi. Jalankan tahap **Agregasi**.", icon="📭")
else:
    daily = pd.read_parquet(DEFAULT_OUT)
    rep = coverage_report(daily)

    st.markdown("**Laporan cakupan** - baca ini sebelum memakai kolom mana pun.")
    st.dataframe(rep, width='stretch', hide_index=True)

    tidak_layak = rep[rep['layak'] == 'TIDAK']
    if len(tidak_layak):
        st.error(
            "Kolom bertanda TIDAK punya cakupan di bawah ambang. Kolom seperti "
            "itu bukan fitur lemah - isinya sebagian besar keputusan pengisian "
            "kita sendiri, bukan data. Jangan dipakai sebelum cakupannya naik.",
            icon="🚫")

    pol = [c for c in daily.columns if c.endswith('_polaritas')]
    if pol:
        pilih = st.multiselect("Kolom polaritas", pol, default=pol)
        if pilih:
            plot = daily[['Tanggal'] + pilih].melt(
                'Tanggal', var_name='kolom', value_name='polaritas').dropna()
            fig = px.line(plot, x='Tanggal', y='polaritas', color='kolom',
                          title='Polaritas harian per lapisan metode')
            fig.add_hline(y=0, line_dash='dot', line_color='gray')
            st.plotly_chart(fig, width='stretch')

            st.caption(
                "Kalau ada dua lapisan, periksa titik sambungnya. Lompatan "
                "rata-rata atau ragam di situ berarti deret ini membawa "
                "artefak metode, bukan hanya sentimen - dan pohon keputusan "
                "akan mempelajari tanggal sambungannya sebagai pola.")

st.divider()

# ============================================================================
# LOG
# ============================================================================
st.subheader("📜 Log Pekerjaan")
nama = st.selectbox("Pekerjaan", sorted(jobs.ALLOWED), key='log_pilih')
baris = st.slider("Baris terakhir", 20, 400, 80, step=20)
st.code(jobs.tail(nama, baris), language='text')
