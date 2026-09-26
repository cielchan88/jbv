"""Jalan berkas untuk penyusunan naskah - satu tempat, supaya skrip lain portabel.

Tiga folder yang dipakai:

    HASIL   berkas mentah hasil komputasi (CSV + JSON)
    SLOT    slot_pasar.json dari cek_slot_pasar.py
    KERJA   keluaran penyusunan: tables.json, gambar, .docx

Semuanya bisa dialihkan lewat env, dan bawaannya menunjuk ke tempat yang
sebenarnya dipakai di repo ini:

    JBV_NASKAH_HASIL   bawaan scripts/paper/revisi/hasil_sdv-wide-gabung
    JBV_NASKAH_SLOT    bawaan scripts/paper/revisi/hasil_slot
    JBV_NASKAH_KERJA   bawaan scripts/paper/naskah/keluaran
    JBV_NASKAH_LAMA    opsional; folder hasil run SEBELUMNYA, hanya untuk
                       menghitung catatan reprodusibilitas ARIMA. Kalau tidak
                       ada, bagian itu dilewati dan naskah kehilangan satu
                       butir batasan - bukan galat.

KENAPA KERJA TERPISAH DARI HASIL. Folder hasil adalah belasan jam komputasi
dan tidak boleh tercampur keluaran penyusunan; keluaran penyusunan boleh
dihapus dan dibangun ulang kapan saja.

KENAPA KELUARAN TIDAK MASUK GIT. tables.json memuat kolom actual dan pred per
leaf - arus valas dalam juta USD - dan repo ini publik.
"""
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(_DIR)))


def _ambil(env, *bawaan):
    v = os.environ.get(env)
    return os.path.abspath(v) if v else os.path.join(REPO, *bawaan)


HASIL = _ambil('JBV_NASKAH_HASIL', 'scripts', 'paper', 'revisi',
               'hasil_sdv-wide-gabung') + os.sep
SLOT = _ambil('JBV_NASKAH_SLOT', 'scripts', 'paper', 'revisi',
              'hasil_slot') + os.sep
KERJA = _ambil('JBV_NASKAH_KERJA', 'scripts', 'paper', 'naskah',
               'keluaran') + os.sep
LAMA = os.environ.get('JBV_NASKAH_LAMA')
LAMA = (os.path.abspath(LAMA) + os.sep) if LAMA else None

TABLES = KERJA + 'tables.json'
GAMBAR = KERJA + 'gambar' + os.sep
DOCX = KERJA + 'FX_15seri.docx'


def siapkan():
    os.makedirs(KERJA, exist_ok=True)
    os.makedirs(GAMBAR, exist_ok=True)


def periksa_hasil(*wajib):
    """Berhenti dengan pesan yang menyebut berkasnya, bukan KeyError di tengah."""
    kurang = [n for n in wajib if not os.path.exists(HASIL + n)]
    if kurang:
        raise SystemExit(
            f'BERHENTI: berkas hasil berikut tidak ada di\n  {HASIL}\n'
            + ''.join(f'  - {n}\n' for n in kurang)
            + 'Setel JBV_NASKAH_HASIL ke folder hasil yang benar, atau '
              'jalankan komputasinya dulu.')
