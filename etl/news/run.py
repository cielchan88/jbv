"""Penggerak pipeline berita. Dijalankan di VPS, bukan dari dashboard.

Empat tahap terpisah, sengaja bisa dijalankan sendiri-sendiri. Penarikan
2006-2026 berlangsung berjam-jam sampai berhari-hari; menyatukannya jadi satu
tombol berarti satu kegagalan di tengah membuang seluruh pekerjaan.

    python -m etl.news.run cek                      # validasi skema GDELT
    python -m etl.news.run tarik-gdelt 2006 2026    # nada agregat, sejarah panjang
    python -m etl.news.run tarik-situs detik 2019 2026
    python -m etl.news.run nilai                    # FinBERT, bisa dilanjutkan
    python -m etl.news.run agregasi                 # -> data/news/sentiment_daily.parquet
    python -m etl.news.run cakupan                  # laporan, baca SEBELUM memakai

Jalankan di tmux/screen. Tahap 'nilai' dan 'tarik-*' tidak boleh dijalankan
lewat HTTP: nginx dan browser akan timeout jauh sebelum selesai.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

from .daily import (DEFAULT_OUT, align_to_calendar, coverage_report,
                    daily_from_corpus)
from .store import DEFAULT_DB, connect, coverage, upsert

PANEL = Path('data/processed/sdv-wide.csv')
CHUNK = 5000        # simpan tiap sekian baris supaya kemajuan tidak hilang


def panel_calendar() -> pd.DatetimeIndex:
    p = pd.read_csv(PANEL, nrows=1)
    return pd.to_datetime([c for c in p.columns if c[:2] == '20'])


def _drain(it, db, label):
    """Alirkan hasil adapter ke basis data per potongan.

    Tidak menumpuk seluruh hasil di memori lebih dulu: rentang 20 tahun bisa
    ratusan ribu baris, dan proses yang mati di jam kelima tidak boleh
    kehilangan empat jam pertama.
    """
    buf, total = [], {'diterima': 0, 'baru': 0, 'duplikat': 0}
    with connect(db) as con:
        for rec in it:
            buf.append(rec)
            if len(buf) >= CHUNK:
                s = upsert(con, buf)
                for k in total:
                    total[k] += s[k]
                con.commit()
                print(f'  [{label}] {total["baru"]:,} baru / '
                      f'{total["diterima"]:,} diterima', flush=True)
                buf = []
        if buf:
            s = upsert(con, buf)
            for k in total:
                total[k] += s[k]
    print(f'[{label}] SELESAI {total}')
    return total


def cmd_cek():
    """Validasi skema GDELT sekali sebelum penarikan panjang."""
    import requests
    from .sources import GDELT_EVENT_BASE, gdelt_validate
    url = f'{GDELT_EVENT_BASE}200601.zip'
    print(f'mengunduh contoh: {url}')
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    print('hasil validasi:', gdelt_validate(r.content))
    print('Skema cocok. Penarikan panjang aman dilanjutkan.')


def cmd_tarik_gdelt(y0: int, y1: int):
    from .sources import fetch_gdelt
    _drain(fetch_gdelt(date(y0, 1, 1), min(date(y1, 12, 31), date.today())),
           DEFAULT_DB, 'gdelt')


def cmd_tarik_situs(site: str, y0: int, y1: int):
    from .sources import fetch_site_archive
    _drain(fetch_site_archive(site, date(y0, 1, 1),
                              min(date(y1, 12, 31), date.today())),
           DEFAULT_DB, site)


def cmd_nilai(limit=None):
    from .sentiment import score_corpus
    print(score_corpus(DEFAULT_DB, limit=int(limit) if limit else None))


def cmd_agregasi():
    daily = daily_from_corpus(DEFAULT_DB)
    if daily.empty:
        print('Korpus belum punya baris berpolaritas. Jalankan nilai dulu.')
        return
    out = align_to_calendar(daily, panel_calendar())
    DEFAULT_OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(DEFAULT_OUT, index=False)
    print(f'ditulis {DEFAULT_OUT} ({len(out):,} hari kerja)')
    print(coverage_report(out).to_string(index=False))


def cmd_cakupan():
    with connect(DEFAULT_DB) as con:
        print('--- korpus mentah per tahun ---')
        print(coverage(con).to_string(index=False))
    if DEFAULT_OUT.exists():
        print('\n--- setelah disejajarkan ke kalender panel ---')
        print(coverage_report(pd.read_parquet(DEFAULT_OUT)).to_string(index=False))


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd, args = argv[0], argv[1:]
    fn = {'cek': cmd_cek, 'tarik-gdelt': cmd_tarik_gdelt,
          'tarik-situs': cmd_tarik_situs, 'nilai': cmd_nilai,
          'agregasi': cmd_agregasi, 'cakupan': cmd_cakupan}.get(cmd)
    if fn is None:
        print(f'perintah tidak dikenal: {cmd}\n{__doc__}')
        return 1
    fn(*args)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
