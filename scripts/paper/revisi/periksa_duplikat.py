"""Cari baris ganda di berkas hasil, dan tawarkan perapiannya.

KENAPA INI BISA TERJADI. Tiap skrip tahap memakai sudah() untuk melewati sel
yang sudah tercatat, lalu tulis() menambahkan baris di ujung berkas. Selama
kunci sel dibaca dengan benar, tidak ada yang berulang. Tapi kalau berkasnya
pernah disunting di tengah jalan - misalnya baris rusak dibuang lalu diisi
ulang sementara proses lain masih menulis ke berkas yang sama - satu sel bisa
tercatat dua kali, dan rata-ratanya jadi campuran dua konfigurasi berbeda
tanpa satu pun pesan galat.

Gejalanya terlihat di ringkas.py sebagai persentase di atas 100%.

Skrip ini hanya MELAPORKAN secara bawaan. Dengan --rapikan ia menyimpan
cadangan lalu menulis ulang berkas dengan satu baris per sel, mempertahankan
baris TERAKHIR untuk tiap kunci - yang terakhir ditulis adalah yang berasal
dari kode terbaru.

    python scripts/paper/revisi/periksa_duplikat.py
    python scripts/paper/revisi/periksa_duplikat.py --rapikan
"""
import os
import shutil
import sys

import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
_P = os.environ.get('JBV_PANEL')
_BAWAAN = 'hasil' if not _P else 'hasil_' + os.path.splitext(os.path.basename(_P))[0]
H = os.path.join(_DIR, os.environ.get('JBV_HASIL', _BAWAAN)) + os.sep

# (berkas, kunci satu sel, jumlah origin per sel)
BERKAS = [
    ('opt_rolling.csv', ['leaf', 'model', 'origin'], 1),
    ('headline.csv', ['leaf', 'model'], 1),
    ('opt_ablasi.csv', ['leaf', 'model', 'arm', 'origin'], 1),
    ('sisa_kablasi.csv', ['leaf', 'model', 'top_k', 'origin'], 1),
    ('sisa_eksternal.csv', ['leaf', 'model', 'top_k', 'ext', 'beta', 'origin'], 1),
    ('opt_tuned.csv', ['leaf', 'model'], 1),
]


def main():
    rapikan = '--rapikan' in sys.argv
    if not os.path.isdir(H):
        print(f'Folder hasil tidak ada: {H}')
        return 1
    print(f'folder: {H}')
    print('mode  : ' + ('RAPIKAN (menulis ulang berkas)' if rapikan else
                        'LAPOR saja - tambahkan --rapikan untuk membereskan') + '\n')

    total_ganda = 0
    for berkas, kunci, _ in BERKAS:
        jalan = H + berkas
        if not os.path.exists(jalan):
            print(f'  LEWAT   {berkas:22s} belum ada')
            continue
        d = pd.read_csv(jalan)
        hilang = [k for k in kunci if k not in d.columns]
        if hilang:
            print(f'  LEWAT   {berkas:22s} kolom kunci tidak ada: {hilang}')
            continue

        ganda = int(d.duplicated(subset=kunci, keep='last').sum())
        unik = len(d) - ganda
        if ganda == 0:
            print(f'  BERSIH  {berkas:22s} {len(d):6d} baris, semuanya unik')
            continue

        total_ganda += ganda
        print(f'  GANDA   {berkas:22s} {len(d):6d} baris, {unik:6d} sel unik, '
              f'{ganda:6d} baris berlebih')

        # Perlihatkan di mana ganda itu menumpuk - biasanya satu lengan atau
        # satu nilai beta, yaitu bagian yang pernah dibuang lalu diisi ulang.
        dd = d[d.duplicated(subset=kunci, keep=False)]
        for kol in ('arm', 'beta', 'top_k', 'ext'):
            if kol in dd.columns and len(dd):
                sebaran = dd[kol].value_counts().to_dict()
                print(f'          menumpuk di {kol}: {sebaran}')

        if rapikan:
            shutil.copy2(jalan, jalan + '.ganda.bak')
            d.drop_duplicates(subset=kunci, keep='last').to_csv(jalan, index=False)
            print(f'          -> ditulis ulang {unik} baris, '
                  f'cadangan di {berkas}.ganda.bak')

    print()
    if not total_ganda:
        print('Tidak ada baris ganda.')
    elif rapikan:
        print(f'{total_ganda} baris berlebih dibuang. Periksa lagi dengan ringkas.py -')
        print('persentasenya harus kembali ke 100% atau di bawahnya.')
    else:
        print(f'{total_ganda} baris berlebih ditemukan. Jalankan lagi dengan --rapikan')
        print('untuk membereskannya (cadangan otomatis dibuat).')
        print('\nPERHATIAN: hentikan dulu proses komputasi sebelum merapikan,')
        print('supaya tidak ada yang menulis ke berkas yang sedang disunting.')
    verifikasi_tanpa_mrmr()
    return 0


def verifikasi_tanpa_mrmr():
    """Pastikan baris tanpa_mrmr benar-benar dari kode yang sudah diperbaiki.

    Lengan yang rusak menghasilkan ramalan IDENTIK dengan lengan optimal,
    karena mRMR tidak pernah benar-benar dimatikan. Sisa kerusakan bisa
    dikenali tanpa menghitung ulang apa pun: cocokkan tiap (leaf, model,
    origin) di arm tanpa_mrmr dengan baris yang sama di opt_rolling.csv.

    DIHITUNG PER SEL, BUKAN PER BARIS. Seleksi fitur diputuskan sekali per
    sel (leaf, model), jadi kalau dua aturan kebetulan memilih himpunan yang
    sama, ketiga puluh origin-nya akan cocok sekaligus. Menghitung baris
    membuat satu kebetulan tampak seperti tiga puluh kerusakan.

    Satu atau dua sel yang cocok memang mungkin. Belasan sel tidak.
    """
    a_j, r_j = H + 'opt_ablasi.csv', H + 'opt_rolling.csv'
    if not (os.path.exists(a_j) and os.path.exists(r_j)):
        return
    a = pd.read_csv(a_j)
    if 'arm' not in a.columns or 'tanpa_mrmr' not in set(a['arm']):
        return
    a = a[a['arm'] == 'tanpa_mrmr'][['leaf', 'model', 'origin', 'mase']]
    r = pd.read_csv(r_j)[['leaf', 'model', 'origin', 'mase']]
    g = a.merge(r, on=['leaf', 'model', 'origin'], suffixes=('_abl', '_opt'))
    if not len(g):
        return
    g['sama'] = (g['mase_abl'] - g['mase_opt']).abs() < 1e-12
    per_sel = g.groupby(['leaf', 'model'])['sama'].all()
    n, tot = int(per_sel.sum()), len(per_sel)

    print('\n' + '=' * 62)
    print('VERIFIKASI LENGAN tanpa_mrmr')
    print('=' * 62)
    print(f'  {n} dari {tot} sel identik dengan lengan optimal '
          f'({100*n/tot:.1f}%)')
    if n == 0:
        print('  BERSIH - lengan ini benar-benar mematikan mRMR.')
    elif n <= 2:
        print('  Wajar. Sel sesedikit ini memang bisa memilih himpunan fitur')
        print('  yang sama di kedua aturan, jadi hasilnya kebetulan sama.')
    else:
        print('  TERKONTAMINASI. Sel sebanyak ini tidak mungkin kebetulan;')
        print('  sebagian masih berasal dari jalan sebelum perbaikan.')
        print('  Buang seluruh lengan ini lalu hitung ulang:')
        print('    python scripts/paper/revisi/buang_baris_rusak.py')
        print('    python scripts/paper/revisi/jalankan_semua.py gabung')
        print(f'  Sel yang terkena: {", ".join(f"{l}/{m}" for l, m in per_sel[per_sel].index[:8])}'
              + (' ...' if n > 8 else ''))


if __name__ == '__main__':
    sys.exit(main())
