"""Buang baris yang dihasilkan lengan 'tanpa mRMR' yang rusak.

LATAR. Sampai perbaikan hari ini, pasang_selektor(0) di rerun_ablasi.py dan
pasang(k, 0) di rerun_sisa.py menyerahkan select_top_features_optimized apa
adanya tanpa menyebut mrmr_beta. Nilai bawaan fungsi itu adalah 1.0 sejak
commit 7006b01, jadi lengan yang seharusnya MEMATIKAN mRMR justru tetap
memakainya. Gejalanya kentara sekali begitu dilihat: ablasi balik melaporkan
selisih persis 0,0000 dengan p=NaN, karena kedua lengan menghasilkan ramalan
yang identik.

YANG TERKENA:
    opt_ablasi.csv       baris dengan arm == 'tanpa_mrmr'
    sisa_eksternal.csv   baris dengan beta == 0.0

YANG TIDAK TERKENA. Tahap 1 dan 2 tidak pernah memakai beta=0. Ablasi jumlah
fitur (sisa_kablasi.csv) selalu dipanggil dengan MRMR_BETA, bukan 0. SHAP
juga tidak lewat jalur ini. Hasil panel 18 leaf selesai 21 September 01:38,
sebelum commit itu, dan angkanya memang berbeda antara beta 0 dan 1 - jadi
naskah yang sudah ada tidak terpengaruh.

Skrip ini menyalin berkas aslinya ke *.rusak.bak lalu menulis ulang tanpa
baris yang terkena. Checkpoint per sel akan mengisi kembali persis bagian itu
saat rerun_ablasi.py dan rerun_sisa.py dijalankan lagi.

Jalankan:  python scripts/paper/revisi/buang_baris_rusak.py
"""
import os
import shutil
import sys

import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
_P = os.environ.get('JBV_PANEL')
_BAWAAN = 'hasil' if not _P else 'hasil_' + os.path.splitext(os.path.basename(_P))[0]
H = os.path.join(_DIR, os.environ.get('JBV_HASIL', _BAWAAN)) + os.sep

# (berkas, kolom, nilai yang dibuang, keterangan)
TARGET = [
    ('opt_ablasi.csv', 'arm', 'tanpa_mrmr', "lengan 'tanpa mRMR'"),
    ('sisa_eksternal.csv', 'beta', 0.0, 'seluruh sel beta = 0 (univariat)'),
]


def main():
    if not os.path.isdir(H):
        print(f'Folder hasil tidak ada: {H}')
        return 1

    print(f'folder: {H}\n')
    total = 0
    for berkas, kolom, nilai, ket in TARGET:
        jalan = H + berkas
        if not os.path.exists(jalan):
            print(f'  LEWAT  {berkas:22s} belum ada')
            continue
        d = pd.read_csv(jalan)
        if kolom not in d.columns:
            print(f'  LEWAT  {berkas:22s} tidak punya kolom {kolom}')
            continue
        buruk = d[kolom] == nilai
        n = int(buruk.sum())
        if n == 0:
            print(f'  BERSIH {berkas:22s} tidak ada baris {kolom}={nilai}')
            continue
        shutil.copy2(jalan, jalan + '.rusak.bak')
        d[~buruk].to_csv(jalan, index=False)
        total += n
        print(f'  BUANG  {berkas:22s} {n:6d} baris  ({ket})')
        print(f'         sisa {len(d) - n} baris, cadangan di {berkas}.rusak.bak')

    if not total:
        print('\nTidak ada yang perlu dibuang.')
        return 0

    print(f'\n{total} baris dibuang. Jalankan lagi untuk mengisinya kembali:')
    print(f'  {sys.executable} scripts/paper/revisi/jalankan_semua.py gabung')
    print('\nTahap 1, 2 dan ablasi jumlah fitur tidak tersentuh, jadi yang')
    print('dihitung ulang hanya bagian yang memang rusak.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
