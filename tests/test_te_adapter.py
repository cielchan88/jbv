"""Uji adapter Trading Economics dengan respons tiruan.

Situsnya diblokir dari lingkungan pengembangan, jadi yang diuji di sini adalah
logika adapternya: penyaringan tanggal dan negara, penggabungan judul dengan
ringkasan, penetapan hari bisnis lintas zona, penghentian ketika sudah
melewati tanggal awal, dan - yang paling penting - aduan keras ketika
penelusuran mentok sebelum mencapai rentang yang diminta.

Jalankan: python tests/test_te_adapter.py
"""
import sys
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import etl.news.sources as src
from etl.news.store import business_date

GAGAL = []


def cek(nama, syarat, detail=''):
    if syarat:
        print(f'  OK   {nama}')
    else:
        print(f'  GAGAL {nama} {detail}')
        GAGAL.append(nama)


class RespTiruan:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p

    def raise_for_status(self):
        pass


def pasang_umpan(halaman):
    """Ganti _get() dengan umpan tiruan. halaman = list of list-of-item."""
    kotak = {'panggilan': 0}

    def _get(s, url, **kw):
        i = kotak['panggilan']
        kotak['panggilan'] += 1
        return RespTiruan(halaman[i] if i < len(halaman) else [])

    src._get = _get
    return kotak


def item(tgl, judul, negara='Indonesia', desc='', url=None):
    return {'ID': abs(hash(judul)) % 10**8, 'date': tgl, 'title': judul,
            'description': desc, 'country': negara,
            'url': url or f'https://te/{abs(hash(judul)) % 10**6}'}


ASLI = src._get


def t_saring():
    print('\npenyaringan tanggal dan negara')
    halaman = [[
        item('2026-03-05T04:00:00Z', 'Rupiah Steady', 'Indonesia'),
        item('2026-03-05T04:00:00Z', 'Fed Holds Rates', 'United States'),
        item('2026-03-05T04:00:00Z', 'Brazil CPI Rises', 'Brazil'),
        item('2026-02-01T04:00:00Z', 'Terlalu Lama', 'Indonesia'),
    ], []]
    pasang_umpan(halaman)
    out = list(src.fetch_trading_economics(date(2026, 3, 1), date(2026, 3, 31),
                                           rate_delay=0))
    judul = [r['title'] for r in out]
    cek('negara di luar daftar dibuang', 'Brazil CPI Rises' not in judul, judul)
    cek('tanggal di luar rentang dibuang', 'Terlalu Lama' not in judul, judul)
    cek('dua negara target lolos', len(out) == 2, judul)
    cek('sumber ditandai benar', all(r['source'] == 'trading_economics' for r in out))


def t_judul_plus_ringkasan():
    print('\npenggabungan judul dan ringkasan')
    halaman = [[
        item('2026-03-05T04:00:00Z', 'Rupiah Weakens',
             desc='The currency slid as foreign investors pulled out of bonds.'),
        item('2026-03-05T04:00:00Z', 'Tanpa Ringkasan', desc=''),
    ], []]
    pasang_umpan(halaman)
    out = list(src.fetch_trading_economics(date(2026, 3, 1), date(2026, 3, 31),
                                           rate_delay=0))
    gabung = next(r for r in out if r['title'].startswith('Rupiah Weakens'))
    cek('ringkasan ikut masuk teks yang dinilai',
        'foreign investors' in gabung['title'], gabung['title'])
    cek('ringkasan asli tetap disimpan terpisah',
        gabung['body'] and 'foreign investors' in gabung['body'])
    polos = next(r for r in out if r['title'] == 'Tanpa Ringkasan')
    cek('tanpa ringkasan tidak meninggalkan titik menggantung',
        polos['title'] == 'Tanpa Ringkasan', repr(polos['title']))
    cek('body kosong jadi None', polos['body'] is None)


def t_zona_waktu():
    print('\npenetapan hari bisnis lintas zona')
    # 10.00 UTC = 17.00 WIB, lewat batas 16.00 -> harus jadi hari BERIKUTNYA
    halaman = [[item('2026-03-05T10:00:00Z', 'Sore Hari WIB')], []]
    pasang_umpan(halaman)
    out = list(src.fetch_trading_economics(date(2026, 3, 1), date(2026, 3, 31),
                                           rate_delay=0))
    bd = business_date(out[0]['published_utc'])
    cek('berita 17.00 WIB masuk hari berikutnya', bd == '2026-03-06', bd)

    # 02.00 UTC = 09.00 WIB, masih pagi -> hari yang sama
    halaman = [[item('2026-03-05T02:00:00Z', 'Pagi Hari WIB')], []]
    pasang_umpan(halaman)
    out = list(src.fetch_trading_economics(date(2026, 3, 1), date(2026, 3, 31),
                                           rate_delay=0))
    bd = business_date(out[0]['published_utc'])
    cek('berita 09.00 WIB tetap di harinya', bd == '2026-03-05', bd)


def t_berhenti_setelah_lewat():
    print('\npenghentian setelah melewati tanggal awal')
    halaman = [
        [item('2026-03-10T04:00:00Z', 'Baru')],
        [item('2026-02-20T04:00:00Z', 'Sudah Lewat')],   # < start, harus berhenti
        [item('2026-02-10T04:00:00Z', 'Tidak Boleh Terbaca')],
    ]
    kotak = pasang_umpan(halaman)
    out = list(src.fetch_trading_economics(date(2026, 3, 1), date(2026, 3, 31),
                                           rate_delay=0))
    cek('berhenti begitu melewati tanggal awal', kotak['panggilan'] == 2,
        f"halaman diambil={kotak['panggilan']}")
    cek('hanya yang dalam rentang dikembalikan',
        [r['title'] for r in out] == ['Baru'], [r['title'] for r in out])


def t_mentok_mengadu():
    print('\naduan ketika mentok sebelum mencapai rentang')
    # Umpan tak berujung yang tanggalnya tidak pernah mundur sampai 2006.
    halaman = [[item(f'2026-03-0{(i % 9) + 1}T04:00:00Z', f'Berita {i}')]
               for i in range(10)]
    pasang_umpan(halaman)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        list(src.fetch_trading_economics(date(2006, 1, 1), date(2026, 3, 31),
                                         rate_delay=0, max_pages=5))
        pesan = ' '.join(str(x.message) for x in w)
    cek('mentok memicu peringatan, bukan diam', len(w) >= 1, len(w))
    cek('peringatan menyebut rentang tidak terpenuhi',
        'TIDAK terpenuhi' in pesan, pesan[:90])
    cek('peringatan mengarahkan ke GDELT', 'GDELT' in pesan, pesan[:90])


def main():
    try:
        t_saring()
        t_judul_plus_ringkasan()
        t_zona_waktu()
        t_berhenti_setelah_lewat()
        t_mentok_mengadu()
    finally:
        src._get = ASLI
    print('\n' + ('SEMUA LULUS' if not GAGAL else f'{len(GAGAL)} GAGAL: {GAGAL}'))
    return 1 if GAGAL else 0


if __name__ == '__main__':
    sys.exit(main())
