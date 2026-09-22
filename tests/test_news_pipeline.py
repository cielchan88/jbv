"""Uji pipeline berita tanpa jaringan.

Seluruh sumber berita diblokir dari lingkungan pengembangan, jadi yang diuji
di sini adalah logika yang TIDAK butuh jaringan - dan itu justru bagian yang
paling menentukan kredibilitas: penetapan hari bisnis, deduplikasi, dan
larangan pengisian mundur.

Jalankan: python tests/test_news_pipeline.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from etl.news.store import (WIB, business_date, connect, make_uid, to_utc,
                            unscored, upsert, write_scores)
from etl.news.daily import align_to_calendar, coverage_report, daily_from_corpus

GAGAL = []


def cek(nama, syarat, detail=''):
    if syarat:
        print(f'  OK   {nama}')
    else:
        print(f'  GAGAL {nama} {detail}')
        GAGAL.append(nama)


def t_batas_hari_bisnis():
    print('\nbatas penetapan hari bisnis (16.00 WIB)')
    # 15.00 WIB -> hari yang sama
    cek('sebelum batas tetap di hari sendiri',
        business_date(datetime(2024, 3, 5, 15, 0, tzinfo=WIB)) == '2024-03-05')
    # 16.00 WIB tepat -> hari berikutnya
    cek('tepat di batas pindah ke besok',
        business_date(datetime(2024, 3, 5, 16, 0, tzinfo=WIB)) == '2024-03-06')
    # 23.00 WIB -> besok
    cek('malam pindah ke besok',
        business_date(datetime(2024, 3, 5, 23, 0, tzinfo=WIB)) == '2024-03-06')
    # 10.00 UTC = 17.00 WIB -> besok. Ini inti pertahanan look-ahead:
    # berita asing sore hari tidak boleh masuk ke hari yang sudah diramal.
    cek('cap waktu UTC dikonversi dulu, bukan dipakai mentah',
        business_date(datetime(2024, 3, 5, 10, 0, tzinfo=timezone.utc)) == '2024-03-06')
    # tanggal polos harus ditolak
    try:
        business_date(datetime(2024, 3, 5, 15, 0))
        cek('tanggal tanpa zona ditolak', False, '(tidak melempar)')
    except ValueError:
        cek('tanggal tanpa zona ditolak', True)


def t_dedup():
    print('\ndeduplikasi')
    a = make_uid('http://x/1', 'Rupiah Menguat', '2024-03-05T05:00:00+00:00')
    b = make_uid('http://x/1', 'rupiah   menguat', '2024-03-05T09:00:00+00:00')
    cek('judul beda spasi/kapital di hari sama dianggap sama', a == b)
    c = make_uid('http://y/9', 'Rupiah Menguat', '2024-03-05T05:00:00+00:00')
    cek('media berbeda tetap dua sinyal', a != c)
    d = make_uid('http://x/1', 'Rupiah Menguat', '2024-03-06T05:00:00+00:00')
    cek('judul sama di hari berbeda tetap dua', a != d)


def t_upsert(db):
    print('\npenyimpanan')
    recs = [
        {'source': 'uji', 'url': 'u1', 'title': 'Rupiah Menguat',
         'published_utc': datetime(2024, 3, 5, 3, tzinfo=timezone.utc)},
        {'source': 'uji', 'url': 'u1', 'title': 'Rupiah Menguat',
         'published_utc': datetime(2024, 3, 5, 3, tzinfo=timezone.utc)},
        {'source': 'uji', 'url': 'u2', 'title': '', 'polarity': None,
         'published_utc': datetime(2024, 3, 5, 3, tzinfo=timezone.utc)},
        {'source': 'gdelt', 'url': 'g1', 'title': None, 'polarity': 0.3,
         'scorer': 'gdelt-tone',
         'published_utc': datetime(2024, 3, 5, 12, tzinfo=timezone.utc)},
    ]
    with connect(db) as con:
        s = upsert(con, recs)
        cek('duplikat dalam satu batch dibuang', s['diterima'] == 2, s)
        cek('baris tanpa judul DAN tanpa skor ditolak', s['diterima'] == 2, s)
        s2 = upsert(con, recs)
        cek('penarikan ulang tidak menambah baris', s2['baru'] == 0, s2)
        n = con.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
        cek('total dua baris', n == 2, n)
        # baris tanpa judul tidak boleh muncul sebagai pekerjaan FinBERT
        u = unscored(con, 'finbert-v3')
        cek('baris nada agregat tidak masuk antrean FinBERT',
            set(u['title'].dropna()) == {'Rupiah Menguat'}, list(u['title']))


def t_skor_lanjutan(db):
    print('\npenilaian yang bisa dilanjutkan')
    with connect(db) as con:
        u = unscored(con, 'finbert-v3')
        uid = u.iloc[0]['uid']
        write_scores(con, 'finbert-v3', [(uid, 0.42, 0.6, 0.18, 0.22)])
        sisa = unscored(con, 'finbert-v3')
        cek('yang sudah dinilai tidak diantre lagi', len(sisa) == 0, len(sisa))
        sisa_lain = unscored(con, 'finbert-v4')
        cek('ganti scorer memicu penilaian ulang', len(sisa_lain) == 1)


def t_agregasi(db):
    print('\nagregasi ke kalender panel')
    daily = daily_from_corpus(db)
    cek('polaritas per scorer dipisah',
        any(c.endswith('_polaritas') for c in daily.columns), list(daily.columns))

    # Sabtu 2024-03-09 dan Minggu 2024-03-10 harus jatuh ke Senin 2024-03-11.
    d = pd.DataFrame({'Tanggal': pd.to_datetime(['2024-03-08', '2024-03-09',
                                                 '2024-03-10', '2024-03-11']),
                      'sent_finbert_v3_polaritas': [0.1, 0.5, 0.7, 0.3],
                      'sent_finbert_v3_n_berita': [10, 2, 2, 8]})
    cal = pd.to_datetime(['2024-03-07', '2024-03-08', '2024-03-11', '2024-03-12'])
    out = align_to_calendar(d, cal)
    senin = out[out['Tanggal'] == '2024-03-11'].iloc[0]
    cek('akhir pekan digabung ke Senin, bukan diisi nol',
        abs(senin['sent_finbert_v3_polaritas'] - (0.5 + 0.7 + 0.3) / 3) < 1e-9,
        senin['sent_finbert_v3_polaritas'])
    cek('jumlah berita akhir pekan ikut pindah',
        senin['sent_finbert_v3_n_berita'] == 12, senin['sent_finbert_v3_n_berita'])

    # Larangan pengisian mundur: hari kerja SEBELUM berita pertama harus NaN.
    kosong = out[out['Tanggal'] == '2024-03-07'].iloc[0]
    cek('hari sebelum data pertama TETAP kosong (tidak diisi mundur)',
        pd.isna(kosong['sent_finbert_v3_polaritas']), kosong['sent_finbert_v3_polaritas'])
    cek('jumlah berita hari kosong = 0', kosong['sent_finbert_v3_n_berita'] == 0)

    # Isi maju dibatasi
    d2 = pd.DataFrame({'Tanggal': pd.to_datetime(['2024-01-02']),
                       'sent_finbert_v3_polaritas': [0.9],
                       'sent_finbert_v3_n_berita': [5]})
    cal2 = pd.bdate_range('2024-01-02', periods=20)
    out2 = align_to_calendar(d2, cal2, max_gap_days=4)
    terisi = int(out2['sent_finbert_v3_polaritas'].notna().sum())
    cek('isi maju dibatasi, kekosongan panjang tidak disulap jadi data',
        terisi == 5, f'terisi={terisi}')

    rep = coverage_report(out2)
    cek('laporan cakupan menandai kolom tidak layak',
        (rep['layak'] == 'TIDAK').any(), rep.to_dict('records'))


def main():
    db = Path('/tmp/uji_news.sqlite')
    if db.exists():
        db.unlink()
    t_batas_hari_bisnis()
    t_dedup()
    t_upsert(db)
    t_skor_lanjutan(db)
    t_agregasi(db)
    print('\n' + ('SEMUA LULUS' if not GAGAL else f'{len(GAGAL)} GAGAL: {GAGAL}'))
    return 1 if GAGAL else 0


if __name__ == '__main__':
    sys.exit(main())
