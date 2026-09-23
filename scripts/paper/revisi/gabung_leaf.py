"""Bangun panel 15 leaf: gabungkan tiga leaf PTMN ke pasangannya di Korporasi Lainnya.

    A.1.a  Impor       ->  A.2.d  Impor
    A.1.b  Repatriasi  ->  A.2.e  Repatriasi
    A.1.c  Lainnya     ->  A.2.f  Lainnya

Hasilnya data/processed/sdv-wide-gabung.csv dengan 15 leaf, bukan 18.

KENAPA PENJUMLAHAN SAJA SUDAH BENAR. Setiap sel panel ini adalah arus valas
neto dalam juta USD, dan panelnya aditif sempurna di semua tingkat - skrip ini
memeriksanya sebelum menulis apa pun, bukan mengasumsikannya. Menggabungkan
dua sel yang tujuannya sama berarti berhenti membedakan PTMN dari korporasi
lain untuk tujuan itu; arus gabungannya adalah jumlah keduanya.

APA YANG HILANG DAN APA YANG DIDAPAT. A.1 tidak lagi punya anak, jadi simpul
A.1 ikut dibuang - kalau dibiarkan, leaves() akan menganggapnya leaf karena
definisinya 'simpul tanpa anak', dan ia akan terhitung dua kali bersama A.2.
Yang didapat: A.1.b adalah sel degenerat di panel lama - nol pada 95,9% hari
dan nol di SELURUH blok uji, sehingga setiap metode yang meramal nol mencetak
MASE sempurna di situ dan naskah harus mengecualikannya dari setiap
pembacaan. Setelah digabung ke A.2.e pangsa nolnya turun ke 18,6% dan
kekecualian itu tidak diperlukan lagi.

A.2 tetap bernama A.2 supaya kode leaf-nya sebanding dengan naskah lama untuk
15 seri yang tersisa; hanya labelnya yang berubah, karena ia kini mencakup
seluruh korporasi, bukan hanya yang bukan PTMN.

Jalankan:  python scripts/paper/revisi/gabung_leaf.py
Lalu:      export JBV_PANEL=data/processed/sdv-wide-gabung.csv
"""
import os
import sys

import pandas as pd

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
os.chdir(_REPO)

ASAL = 'data/processed/sdv-wide.csv'
TUJUAN = 'data/processed/sdv-wide-gabung.csv'

# (sumber, penerima) - sumber dijumlahkan ke penerima lalu dibuang
PASANGAN = [('A.1.a', 'A.2.d'), ('A.1.b', 'A.2.e'), ('A.1.c', 'A.2.f')]
INDUK_KOSONG = 'A.1'
LABEL_BARU = {'A.2': '2. Korporasi (PTMN dan lainnya)'}

# Hierarki yang harus tetap aditif sesudah penggabungan.
RANTAI = [('A.2', ['A.2.a', 'A.2.b', 'A.2.c', 'A.2.d', 'A.2.e', 'A.2.f']),
          ('A', ['A.2']),
          ('B', ['B.a', 'B.b', 'B.c', 'B.d']),
          ('C', ['C.a', 'C.b', 'C.c', 'C.d', 'C.e']),
          ('D', ['A', 'B', 'C'])]


def periksa(V, judul, rantai):
    print(f'  {judul}')
    buruk = 0
    for induk, anak in rantai:
        d = (V.loc[induk] - V.loc[anak].sum(axis=0)).abs().max()
        tanda = 'OK' if d < 1e-6 else 'GAGAL'
        if d >= 1e-6:
            buruk += 1
        print(f'    {tanda:5s} {induk:3s} = {" + ".join(anak)}   maks selisih {d:.2e}')
    return buruk


def main():
    p = pd.read_csv(ASAL)
    dc = [c for c in p.columns if c[:2] == '20']
    p = p.set_index('Row_ID')
    V = p[dc].apply(pd.to_numeric, errors='coerce')
    if V.isna().any().any():
        print('BERHENTI: panel asal mengandung NaN.')
        sys.exit(1)

    print(f'panel asal: {ASAL}  {len(p)} baris, {len(dc)} tanggal\n')
    print('SEBELUM')
    rantai_lama = [('A.1', ['A.1.a', 'A.1.b', 'A.1.c']),
                   ('A.2', ['A.2.a', 'A.2.b', 'A.2.c', 'A.2.d', 'A.2.e', 'A.2.f']),
                   ('A', ['A.1', 'A.2'])] + RANTAI[2:]
    if periksa(V, 'aditivitas panel asal', rantai_lama):
        print('BERHENTI: panel asal tidak aditif, penggabungan tidak aman.')
        sys.exit(1)

    # ---------------------------------------------------------------- gabung
    print('\nPENGGABUNGAN')
    for sumber, penerima in PASANGAN:
        a, b = V.loc[sumber], V.loc[penerima]
        V.loc[penerima] = (a + b).values
        print(f'  {sumber} -> {penerima}   rata {a.mean():8.1f} + {b.mean():8.1f} '
              f'= {V.loc[penerima].mean():8.1f} juta USD   '
              f'nol {100*(a==0).mean():5.1f}% & {100*(b==0).mean():5.1f}% '
              f'-> {100*(V.loc[penerima]==0).mean():5.1f}%')

    buang = [s for s, _ in PASANGAN] + [INDUK_KOSONG]
    V = V.drop(index=buang)

    # Induk harus ikut disegarkan. A.2 kini menampung seluruh arus korporasi,
    # jadi nilainya bertambah sebesar A.1, dan A tinggal menyalin A.2 karena
    # cabang PTMN sudah tidak ada. Menjumlahkan ke anak tanpa langkah ini
    # meninggalkan panel yang tidak aditif - dan pemeriksaan di bawah menolak
    # menulisnya.
    V.loc['A.2'] = V.loc[[a for a in RANTAI[0][1]]].sum(axis=0).values
    V.loc['A'] = V.loc['A.2'].values
    print('  induk disegarkan: A.2 = jumlah enam anaknya, A = A.2')
    meta = p.drop(index=buang)[['Row_Label', 'Level']].copy()
    for rid, lab in LABEL_BARU.items():
        meta.loc[rid, 'Row_Label'] = lab
    print(f'  dibuang: {", ".join(buang)}  ({INDUK_KOSONG} ikut, karena kini tanpa anak)')

    print('\nSESUDAH')
    if periksa(V, 'aditivitas panel gabungan', RANTAI):
        print('BERHENTI: panel gabungan tidak aditif. Tidak ada yang ditulis.')
        sys.exit(1)

    # D harus persis sama dengan sebelumnya - penggabungan memindahkan arus
    # antar sel, bukan menambah atau menghilangkannya.
    d_lama = pd.read_csv(ASAL).set_index('Row_ID').loc['D', dc].astype(float)
    d_baru = V.loc['D']
    selisih = (d_lama.values - d_baru.values).__abs__().max()
    print(f'  {"OK" if selisih < 1e-6 else "GAGAL"}    total D tidak berubah   '
          f'maks selisih {selisih:.2e}')
    if selisih >= 1e-6:
        sys.exit(1)

    # ----------------------------------------------------------------- tulis
    keluar = meta.join(V).reset_index()
    keluar = keluar[['Row_ID', 'Row_Label', 'Level'] + dc]
    keluar.to_csv(TUJUAN, index=False)

    def daun(ids):
        return [i for i in ids
                if i != 'D' and not any(j != i and j.startswith(i + '.') for j in ids)]

    lv = daun(list(keluar['Row_ID']))
    print(f'\nditulis: {TUJUAN}  {len(keluar)} baris')
    print(f'leaf: {len(lv)}  ->  {", ".join(lv)}')
    print('\nPakai dengan:')
    print(f'  export JBV_PANEL={TUJUAN}')
    print('  (folder hasil ikut bergeser sendiri ke hasil_sdv-wide-gabung/)')


if __name__ == '__main__':
    main()
