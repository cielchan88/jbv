"""Satukan berkas hasil per shard jadi berkas kanonik yang dibaca tahap lanjutan.

KENAPA ADA TAHAP TERSENDIRI. Saat dijalankan paralel, tiap proses menulis ke
berkasnya sendiri - `opt_rolling.shard-2-of-4.csv` dan seterusnya. Itu bukan
kehati-hatian berlebih: dua proses yang meng-append ke satu CSV persis yang
melahirkan baris ganda 125,9% dan 163,3% di folder hasil panel 18 seri.
Sesudah semua shard selesai, berkasnya harus disatukan karena ringkas.py,
uji_statistik.py, shap_baru.py dan penyusun tabel membaca nama kanonik.

AMAN DIJALANKAN BERULANG. Penyatuan membaca berkas kanonik yang sudah ada
ikut serta, lalu membuang baris kembar berdasarkan kunci selnya - jadi
menjalankannya dua kali tidak melipatgandakan apa pun. Berkas shard TIDAK
dihapus kecuali diminta, supaya masih ada kalau penyatuannya perlu diulang.

YANG DIPERIKSA SEBELUM MENULIS. Setiap berkas punya kunci sel yang sudah
diketahui. Kalau satu kunci muncul lebih dari sekali dengan ISI yang berbeda,
itu tanda dua shard mengerjakan leaf yang sama - pembagian kerjanya salah, dan
skrip berhenti alih-alih diam-diam memilih salah satu.

    python scripts/paper/revisi/gabung_shard.py            # lihat saja
    python scripts/paper/revisi/gabung_shard.py --ya       # tulis berkas kanonik
    python scripts/paper/revisi/gabung_shard.py --ya --bersihkan   # lalu hapus shard
"""
import glob
import os
import re
import sys

import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
_P = os.environ.get('JBV_PANEL')
_BAWAAN = 'hasil' if not _P else 'hasil_' + os.path.splitext(os.path.basename(_P))[0]
H = os.path.join(_DIR, os.environ.get('JBV_HASIL', _BAWAAN))

# Kunci sel tiap berkas. Baris dengan kunci sama adalah pekerjaan yang sama,
# jadi yang belakangan menimpa yang terdahulu.
KUNCI = {
    'opt_tuned.csv':      ['leaf', 'model'],
    'opt_rolling.csv':    ['leaf', 'model', 'origin'],
    'headline.csv':       ['leaf', 'model'],
    'opt_ablasi.csv':     ['leaf', 'model', 'arm', 'origin'],
    'sisa_kablasi.csv':   ['leaf', 'model', 'top_k', 'origin'],
    'sisa_eksternal.csv': ['leaf', 'model', 'top_k', 'ext', 'beta', 'origin'],
}
# Dua bentuk penanda: JBV_SHARD=2/4 -> ".shard-2-of-4", JBV_LEAF -> ".shard-leaf-A-2-d"
POLA = re.compile(r'^(.*)\.shard-(?:\d+-of-\d+|leaf-[A-Za-z0-9-]*)(\.csv)$')


def baca_tepat(path):
    """Baca CSV tanpa kehilangan bit terakhir.

    Pembaca CSV pandas TIDAK bolak-balik persis secara bawaan: 2,0406320647409077
    terbaca kembali sebagai 2,040632064740908. Akibatnya berkas kanonik - yang
    ditulis dari angka hasil parsing - berbeda satu bit dari berkas shard yang
    jadi sumbernya, dan penyatuan kedua kali melaporkannya sebagai bentrokan.
    float_precision='round_trip' mematikan jalan pintas itu.
    """
    return pd.read_csv(path, float_precision='round_trip')


def hitung_bentrok(gab, kunci, rtol=1e-9):
    """Berapa kunci sel yang muncul dengan isi BERBEDA NYATA.

    Kolom angka dibandingkan dengan toleransi, bukan persamaan persis. Dua
    perhitungan yang sah bisa berbeda di bit terakhir - RandomForest saja
    bergeser 1e-13 hanya karena tata letak memori berubah - dan menolak
    menyatukan karena itu akan menjadi alarm palsu. Yang dicari di sini adalah
    dua shard yang benar-benar mengerjakan leaf yang sama, yang selisihnya
    besar, bukan derau titik mengambang.
    """
    bukan_kunci = [c for c in gab.columns if c not in kunci]
    kembar = gab.duplicated(kunci, keep=False)
    if not kembar.any() or not bukan_kunci:
        return 0
    g = gab[kembar].groupby(kunci, dropna=False)
    beda = None
    for c in bukan_kunci:
        s = gab[kembar][c]
        if pd.api.types.is_numeric_dtype(s):
            # astype(float) sebelum clip: agg() bisa mengembalikan dtype
            # object untuk kolom campuran, dan clip di atas object memicu
            # FutureWarning penurunan dtype dari pandas. Perbandingannya
            # memang perbandingan pecahan, jadi tegaskan saja tipenya.
            rentang = (g[c].max() - g[c].min()).astype(float)
            besar = g[c].agg(lambda v: v.abs().max()).astype(float)
            buruk = rentang > rtol * besar.clip(lower=1e-300)
        else:
            buruk = g[c].nunique(dropna=False) > 1
        beda = buruk if beda is None else (beda | buruk)
    return int(beda.sum()) if beda is not None else 0


def kelompok():
    """Kumpulkan berkas shard per nama kanonik."""
    out = {}
    for p in sorted(glob.glob(os.path.join(H, '*.shard-*.csv'))):
        m = POLA.match(os.path.basename(p))
        if not m:
            continue
        out.setdefault(m.group(1) + m.group(2), []).append(p)
    return out


def satukan(nama, shard_paths, tulis):
    kunci = KUNCI.get(nama)
    if kunci is None:
        print(f'  {nama:22s} DILEWATI - kuncinya belum terdaftar di KUNCI')
        return False

    kanonik = os.path.join(H, nama)
    bagian, asal = [], []
    for p in [kanonik] + list(shard_paths):
        if not os.path.exists(p):
            continue
        d = baca_tepat(p)
        if len(d):
            bagian.append(d); asal.append((os.path.basename(p), len(d)))
    if not bagian:
        print(f'  {nama:22s} kosong')
        return False

    gab = pd.concat(bagian, ignore_index=True)
    hilang = [k for k in kunci if k not in gab.columns]
    if hilang:
        print(f'  {nama:22s} BERHENTI - kolom kunci hilang: {hilang}')
        return False

    bentrok = hitung_bentrok(gab, kunci)

    rapi = gab.drop_duplicates(kunci, keep='last').sort_values(kunci)
    n_leaf = rapi['leaf'].nunique() if 'leaf' in rapi.columns else 0
    print(f'  {nama:22s} {len(gab):7,} baris -> {len(rapi):7,} '
          f'({n_leaf} leaf, {len(asal)} berkas)'
          + (f'  BENTROK {bentrok} sel' if bentrok else ''))
    for a, n in asal:
        print(f'      {n:7,}  {a}')
    if bentrok:
        print(f'      ^ {bentrok} kunci muncul dengan isi berbeda. Dua shard '
              f'mengerjakan leaf yang sama?')
        return None                    # None = ada masalah, bukan sekadar gagal

    if tulis:
        rapi.to_csv(kanonik, index=False)
    return True


def rerun_berjalan():
    """Proses tahap yang masih menulis ke folder hasil.

    Membaca /proc alih-alih mencocokkan teks 'rerun_' dengan pgrep. pgrep juga
    menangkap shell yang KEBETULAN menyebut rerun_ di baris perintahnya -
    termasuk baris perintah yang memanggil skrip ini - lalu menolak menyatukan
    padahal tidak ada yang berjalan. Di sini yang dihitung hanya proses yang
    argumennya benar-benar sebuah skrip rerun_*.py.
    """
    out = []
    milik_sendiri = os.getpid()
    for d in glob.glob('/proc/[0-9]*'):
        pid = int(os.path.basename(d))
        if pid == milik_sendiri:
            continue
        try:
            with open(os.path.join(d, 'cmdline'), 'rb') as f:
                arg = [a for a in f.read().split(b'\0') if a]
        except OSError:
            continue                    # proses sudah hilang, atau tidak terbaca
        if not arg or b'python' not in os.path.basename(arg[0]):
            continue
        if any(os.path.basename(a).startswith(b'rerun_')
               and a.endswith(b'.py') for a in arg[1:]):
            out.append((pid, b' '.join(arg).decode('utf-8', 'replace')))
    return out


def main():
    lanjut = '--ya' in sys.argv
    bersihkan = '--bersihkan' in sys.argv
    if not os.path.isdir(H):
        print(f'Folder hasil belum ada:\n  {H}')
        return 1

    kel = kelompok()
    print(f'folder : {H}')
    if not kel:
        print('\nTidak ada berkas shard. Tidak ada yang perlu disatukan.')
        return 0
    print(f'shard  : {sum(len(v) for v in kel.values())} berkas, '
          f'{len(kel)} keluaran\n')

    # Proses yang masih menulis akan membuat hasil penyatuan tidak lengkap.
    sisa = rerun_berjalan()
    if sisa:
        print('BERHENTI: masih ada proses tahap yang berjalan:\n')
        for pid, baris in sisa:
            print(f'  pid {pid}  {baris[:100]}')
        print('\nTunggu sampai selesai, baru satukan.')
        return 1

    masalah = False
    berhasil = []
    for nama, paths in sorted(kel.items()):
        hasil = satukan(nama, paths, lanjut)
        if hasil is None:
            masalah = True
        elif hasil:
            berhasil.append((nama, paths))

    if masalah:
        print('\nBERHENTI: ada bentrokan di atas. Tidak ada berkas kanonik '
              'yang ditulis ulang untuk keluaran itu.')
        return 1
    if not lanjut:
        print('\nBELUM ADA YANG DITULIS. Tambahkan --ya untuk menulis berkas kanonik.')
        return 0

    print(f'\n{len(berhasil)} berkas kanonik ditulis di {H}')
    if bersihkan:
        n = 0
        for _, paths in berhasil:
            for p in paths:
                os.remove(p); n += 1
        print(f'{n} berkas shard dihapus')
    else:
        print('Berkas shard dibiarkan. Tambahkan --bersihkan untuk menghapusnya.')
    print(f'\nLanjutkan:  {sys.executable} scripts/paper/revisi/ringkas.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())
