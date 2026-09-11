"""Agregasi korpus berita jadi kolom fitur harian.

Keluarannya berkas terpisah, BUKAN tulisan langsung ke
data/external_features.xlsx. Alasannya: berkas itu milik pengguna. Kalau
scraping menimpanya, unggahan berikutnya menghapus sentimen dan scraping
berikutnya menghapus unggahan. Dua sumber yang saling menimpa di satu berkas
adalah cara paling cepat kehilangan keduanya.

Penggabungan dilakukan saat PEMUATAN (lihat merge_for_loader), sehingga
kedua sisi tetap utuh di sumbernya masing-masing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .store import connect

DEFAULT_OUT = Path('data/news/sentiment_daily.parquet')

# Akhiran penanda jenis kolom, dipakai bersama oleh daily_from_corpus(),
# align_to_calendar(), dan coverage_report(). Ketiganya harus sepakat: kalau
# hanya satu yang diubah, kolom polaritas berhenti dikenali dan diam-diam
# hilang dari hasil agregasi.
POL_SUFFIX = '_polaritas'
CNT_SUFFIX = '_n_berita'

# Berapa hari kerja minimum yang harus punya berita sebelum sebuah lapisan
# scorer dianggap layak pakai. Di bawah ini kolomnya lebih banyak lubang
# daripada isi, dan pengisian apa pun akan mendominasi sinyalnya.
MIN_COVERAGE_PCT = 60.0


def daily_from_corpus(db_path, scorers: Optional[list] = None) -> pd.DataFrame:
    """Rata-rata polaritas dan jumlah berita per hari bisnis, per scorer.

    Dipecah per scorer dengan sengaja. Merata-ratakan nada GDELT bersama
    polaritas FinBERT dalam satu angka akan menyembunyikan patahan metode di
    titik sambung - lihat catatan di sources.py.
    """
    q = """
        SELECT business_date, scorer,
               COUNT(*)      AS n_berita,
               AVG(polarity) AS polaritas
        FROM articles
        WHERE polarity IS NOT NULL
        GROUP BY business_date, scorer
    """
    with connect(db_path) as con:
        df = pd.read_sql_query(q, con)
    if scorers:
        df = df[df['scorer'].isin(scorers)]
    if df.empty:
        return pd.DataFrame(columns=['Tanggal'])

    df['Tanggal'] = pd.to_datetime(df['business_date'])
    wide = df.pivot_table(index='Tanggal', columns='scorer',
                          values=['polaritas', 'n_berita'])
    # Pola nama: sent_<scorer>_<besaran>. Akhiran dipakai untuk mengenali
    # jenis kolom di align_to_calendar(), jadi jangan diubah di satu tempat
    # saja - lihat POL_SUFFIX / CNT_SUFFIX.
    wide.columns = [f'sent_{b}_{a}'.replace('-', '_') for a, b in wide.columns]
    return wide.reset_index().sort_values('Tanggal').reset_index(drop=True)


def align_to_calendar(daily: pd.DataFrame, calendar: pd.DatetimeIndex,
                      max_gap_days: int = 4) -> pd.DataFrame:
    """Petakan sentimen harian ke kalender hari kerja panel.

    Akhir pekan dan hari libur DIGABUNGKAN ke hari kerja berikutnya, bukan
    dibuang dan bukan diisi nol. Berita Sabtu memang belum bisa ditindaklanjuti
    sampai Senin, jadi Senin-lah tempatnya. Ini juga yang menghapus gigi
    gergaji mingguan pada versi lama, yang menulis 0.0 di akhir pekan -
    nilai yang di skala lama justru berarti senegatif mungkin.

    Hari kerja yang tetap tidak punya berita dibiarkan NaN. TIDAK diisi maju
    lebih dari `max_gap_days`, dan TIDAK PERNAH diisi mundur: pengisian mundur
    memasukkan nilai masa depan ke masa lalu.
    """
    if daily.empty:
        return pd.DataFrame({'Tanggal': calendar})
    cal = pd.DatetimeIndex(sorted(calendar))
    d = daily.sort_values('Tanggal').copy()

    # Setiap tanggal berita dipetakan ke hari kerja pertama yang >= tanggal itu.
    pos = cal.searchsorted(d['Tanggal'].values, side='left')
    inside = pos < len(cal)
    d = d[inside].copy()
    d['Tanggal'] = cal[pos[inside]]

    val_cols = [c for c in d.columns if c != 'Tanggal']
    pol_cols = [c for c in val_cols if c.endswith(POL_SUFFIX)]
    cnt_cols = [c for c in val_cols if c.endswith(CNT_SUFFIX)]
    lain = set(val_cols) - set(pol_cols) - set(cnt_cols)
    if lain:
        raise ValueError(
            f'kolom tidak dikenali: {sorted(lain)}. Penamaan harus berakhir '
            f'{POL_SUFFIX} atau {CNT_SUFFIX}; kolom lain akan hilang diam-diam '
            f'saat agregasi.')

    agg = {c: 'mean' for c in pol_cols}
    agg.update({c: 'sum' for c in cnt_cols})
    d = d.groupby('Tanggal').agg(agg).reset_index()

    out = pd.DataFrame({'Tanggal': cal}).merge(d, on='Tanggal', how='left')
    for c in cnt_cols:
        out[c] = out[c].fillna(0)
    for c in pol_cols:
        # Isi maju terbatas: hari libur panjang boleh memakai sentimen terakhir,
        # tapi kekosongan berbulan-bulan tidak boleh disulap jadi data.
        out[c] = out[c].ffill(limit=max_gap_days)
    return out


def coverage_report(aligned: pd.DataFrame) -> pd.DataFrame:
    """Berapa persen hari kerja yang benar-benar punya sentimen, per kolom.

    Wajib dibaca sebelum memakai kolom mana pun sebagai fitur. Kolom dengan
    cakupan rendah bukan fitur lemah - ia fitur yang isinya sebagian besar
    keputusan pengisian kita sendiri, bukan data.
    """
    rows = []
    for c in aligned.columns:
        if c == 'Tanggal' or not c.endswith(POL_SUFFIX):
            continue
        ada = int(aligned[c].notna().sum())
        pct = 100.0 * ada / len(aligned)
        rows.append({'kolom': c, 'hari_terisi': ada, 'dari': len(aligned),
                     'cakupan_pct': round(pct, 1),
                     'layak': 'ya' if pct >= MIN_COVERAGE_PCT else 'TIDAK',
                     'mulai': aligned.loc[aligned[c].notna(), 'Tanggal'].min(),
                     'sampai': aligned.loc[aligned[c].notna(), 'Tanggal'].max()})
    return pd.DataFrame(rows)


def merge_for_loader(external_path, sentiment_path) -> pd.DataFrame:
    """Gabungkan berkas unggahan pengguna dengan sentimen, saat pemuatan.

    Keduanya tetap utuh di berkasnya masing-masing; hasil gabungan ini
    sementara. Unggahan baru dari pengguna tidak menghapus sentimen, dan
    penarikan berita baru tidak menyentuh unggahan pengguna.
    """
    ext = pd.read_excel(external_path)
    ext['Tanggal'] = pd.to_datetime(ext['Tanggal'])
    sp = Path(sentiment_path)
    if not sp.exists():
        return ext
    sen = pd.read_parquet(sp) if sp.suffix == '.parquet' else pd.read_excel(sp)
    sen['Tanggal'] = pd.to_datetime(sen['Tanggal'])
    dup = [c for c in sen.columns if c != 'Tanggal' and c in ext.columns]
    if dup:
        ext = ext.drop(columns=dup)
    return ext.merge(sen, on='Tanggal', how='left').sort_values('Tanggal')
