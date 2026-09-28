"""Bangun ulang Gambar 1 dan Gambar 4 naskah pendamping, dengan label ARIMA.

    python3 scripts/paper/figs_pendamping.py [-o dir-keluaran]

KENAPA HANYA DUA. Enam gambar naskah pendamping diperiksa satu per satu dari
DOCX-nya; hanya Gambar 1 dan Gambar 4 yang memuat nama metode sebagai label.
Gambar 2 berkategori keluarga fitur, Gambar 3 protokol dan tiga model pohon,
Gambar 5 distribusi, Gambar A1 tiga model pohon - semuanya tidak menyebut
AutoARIMA, jadi tidak perlu diusik.

KENAPA PERLU DIBANGUN ULANG. Teks di dalam PNG sudah ter-raster. Naskah menulis
ARIMA di prosa dan tabel sejak nama metodenya disamakan, jadi dua gambar yang
masih menulis AutoARIMA justru membuat naskah tampak menyebut dua metode
berbeda - persis yang ingin dihilangkan.

DARI MANA ANGKANYA. gambar_pendamping.json, disalin dari TABEL di dalam DOCX
naskah pendamping, bukan ditaksir dari piksel gambar lama. Skrip yang membuat
gambar aslinya tidak ikut di-commit, dan h1_facts2.json maupun hasil h=60 tidak
ada di repo, jadi tanpa rekaman itu gambar ini tidak bisa dibangun sama sekali.

PENJAGA. Klaim yang tercetak di judul Gambar 1(b) - rho = -1,000 dan p = 1/6! -
DIHITUNG ULANG dari datanya, tidak diketik. Kalau angkanya diperbarui dan
pembalikannya tidak lagi sempurna, skrip ini berhenti alih-alih mencetak judul
yang dibantah datanya sendiri.
"""
import argparse
import json
import math
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from scipy.stats import spearmanr

DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(DIR, 'gambar_pendamping.json')

# Nama metode untuk DITAMPILKAN - satu tempat, sama seperti build_paper.js.
# Kunci di gambar_pendamping.json sengaja tetap memakai nama internal.
NAMA_METODE = {'AutoARIMA': 'ARIMA'}
nama = lambda m: NAMA_METODE.get(m, m)


def muat():
    if not os.path.exists(DATA):
        raise SystemExit(f'BERHENTI: {DATA} tidak ada.')
    return json.load(open(DATA, encoding='utf-8'))


def gaya(ax, P):
    ax.set_axisbelow(True)
    ax.grid(True, color=P['kisi'], linewidth=0.8)
    for sisi in ('top', 'right'):
        ax.spines[sisi].set_visible(False)


def gambar1(G, keluar):
    """Hasil Tahap I: fit dalam-sampel lawan akurasi luar-sampel."""
    P, S = G['palet'], G['stage1']
    baris = S['baris']
    kecuali = S['dikecualikan']

    # Panel (b) mengecualikan random walk. rho dan p DIHITUNG di sini.
    pakai = [r for r in baris if r['metode'] != kecuali]
    rho, _ = spearmanr([r['in_mase'] for r in pakai], [r['out_mase'] for r in pakai])
    n = len(pakai)
    p = 1.0 / math.factorial(n)          # uji permutasi eksak untuk rho = -1
    if abs(rho - S['rho']) > 5e-4:
        raise SystemExit(f'BERHENTI: rho dari data {rho:.4f} tidak cocok dengan '
                         f'{S["rho"]} yang tercatat - jangan cetak judul yang '
                         'dibantah datanya sendiri.')
    if abs(p - S['p']) > 5e-6:
        raise SystemExit(f'BERHENTI: 1/{n}! = {p:.6f} tidak cocok dengan p = '
                         f'{S["p"]} yang tercatat.')

    # Panel kanan dibuat lebih lebar: judulnya memuat rho, p dan apa yang
    # dikecualikan, dan pada lebar yang sama ujungnya terpotong di luar bidang.
    fig, (a, b) = plt.subplots(1, 2, figsize=(11.2, 3.2), dpi=200,
                               gridspec_kw={'width_ratios': [1, 1.28]})

    # ---- (a) batang berpasangan, diurutkan menurut fit dalam-sampel
    urut = sorted(baris, key=lambda r: r['rank_in'])
    x = range(len(urut))
    lb = 0.38
    a.bar([i - lb / 2 for i in x], [r['in_mase'] for r in urut], lb,
          color=P['dalam_sampel'], label='In-sample (training)')
    a.bar([i + lb / 2 for i in x], [r['out_mase'] for r in urut], lb,
          color=P['ml'], label='Out-of-sample (test)')
    a.axhline(1.0, color='0.2', linestyle='--', linewidth=1.1)
    a.set_xticks(list(x))
    a.set_xticklabels([nama(r['metode']) for r in urut], rotation=30, ha='right')
    a.set_ylabel('MASE')
    a.set_title(S['judul_a'], loc='left', fontsize=11)
    a.legend(frameon=False, fontsize=8.5)
    gaya(a, P)

    # ---- (b) sebaran, random walk ditandai tapi dikecualikan dari uji
    # Batas sumbu disetel LEBIH DULU supaya label bisa tahu titik mana yang
    # dekat tepi kanan. Tanpa itu label Prophet - titik paling kanan - tertulis
    # menimpa tepi bidang.
    xi = [r['in_mase'] for r in baris]
    yi = [r['out_mase'] for r in baris]
    jx, jy = max(xi) - min(xi), max(yi) - min(yi)
    b.set_xlim(min(xi) - 0.10 * jx, max(xi) + 0.16 * jx)
    b.set_ylim(min(yi) - 0.16 * jy, max(yi) + 0.16 * jy)
    # HANYA titik paling kanan yang labelnya dibalik ke kiri. Ambang berbasis
    # proporsi membalik NaiveMean juga, dan labelnya lalu bertumpuk dengan
    # label ARIMA yang menjulur ke kanan.
    x_maks = max(xi)
    for r in baris:
        ml = r['keluarga'] == 'ML'
        ada = r['metode'] == kecuali
        b.scatter(r['in_mase'], r['out_mase'],
                  s=110 if ada else 70,
                  marker='D' if ada else 'o',
                  color=P['ml'] if ml else P['tradisional'],
                  edgecolor='0.25' if ada else 'none', linewidth=0.8, zorder=3)
        kanan = r['in_mase'] == x_maks
        b.annotate(nama(r['metode']), (r['in_mase'], r['out_mase']),
                   textcoords='offset points',
                   # Yang paling kanan diturunkan, bukan sekadar dibalik:
                   # di atas ia berdempetan dengan label tetangganya.
                   xytext=(-10, -15) if kanan else (10, 7),
                   ha='right' if kanan else 'left', fontsize=8.5)
    # Garis tren hanya atas titik yang dipakai, supaya konsisten dengan ujinya.
    xs = [r['in_mase'] for r in pakai]
    ys = [r['out_mase'] for r in pakai]
    n_ = len(xs)
    mx, my = sum(xs) / n_, sum(ys) / n_
    sxy = sum((u - mx) * (v - my) for u, v in zip(xs, ys))
    sxx = sum((u - mx) ** 2 for u in xs)
    m_, c_ = sxy / sxx, my - (sxy / sxx) * mx
    lo, hi = min(xs) - 0.04, max(xs) + 0.04
    b.plot([lo, hi], [m_ * lo + c_, m_ * hi + c_], '--', color='0.55', linewidth=1.1)

    b.set_xlabel('In-sample MASE (lower = better training fit)')
    b.set_ylabel('Out-of-sample MASE')
    # Judul panel ini panjang; pada fontsize 11 ujungnya terpotong di luar
    # bidang. Dikecilkan supaya seluruh klaimnya - rho, p, dan apa yang
    # dikecualikan - benar-benar terbaca.
    b.set_title(f'(b) Better training fit, worse forecasts  '
                f'(rho={rho:.3f}, p={p:.5f}, excl. {kecuali})',
                loc='left', fontsize=9.5)
    b.legend(handles=[Patch(color=P['tradisional'], label='Traditional'),
                      Patch(color=P['ml'], label='Machine learning')],
             frameon=False, fontsize=8.5, loc='lower left')
    gaya(b, P)

    fig.tight_layout()
    out = os.path.join(keluar, 'fig1_stage1.png')
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out, rho, p, n


def gambar4(G, keluar):
    """MASE rata-rata per metode di bawah protokol rekursif."""
    P, S = G['palet'], G['sepuluh']
    baris = sorted(S['baris'], key=lambda r: r['mase'])

    fig, ax = plt.subplots(figsize=(6.22, 3.065), dpi=200)
    y = range(len(baris))
    ax.barh(list(y), [r['mase'] for r in baris],
            color=[P['ml'] if r['keluarga'] == 'ML' else P['tradisional']
                   for r in baris], height=0.72)
    for i, r in zip(y, baris):
        ax.text(r['mase'] + 0.045, i, f'{r["mase"]:.2f}',
                va='center', fontsize=8.5)
    ax.set_yticks(list(y))
    ax.set_yticklabels([nama(r['metode']) for r in baris])
    ax.invert_yaxis()                      # terbaik di atas
    ax.axvline(1.0, color='0.2', linestyle='--', linewidth=1.1)
    ax.text(1.04, -0.62, S['anotasi_acuan'], fontsize=8.5, color='0.3')
    ax.set_xlim(0, max(r['mase'] for r in baris) * 1.16)
    ax.set_xlabel(S['sumbu_x'])
    ax.legend(handles=[Patch(color=P['tradisional'], label='Traditional'),
                       Patch(color=P['ml'], label='Machine learning')],
              frameon=False, fontsize=8.5, loc='center right')
    gaya(ax, P)
    for sisi in ('left',):
        ax.spines[sisi].set_visible(True)

    fig.tight_layout()
    out = os.path.join(keluar, 'fig4_bymethod.png')
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-o', '--out', default=os.path.join(DIR, 'fig_baru'),
                    help='direktori keluaran (bawaan scripts/paper/fig_baru)')
    A = ap.parse_args()
    os.makedirs(A.out, exist_ok=True)
    G = muat()

    f1, rho, p, n = gambar1(G, A.out)
    f4 = gambar4(G, A.out)
    print(f'  Gambar 1: rho={rho:.3f} dihitung dari data, p=1/{n}!={p:.6f}')
    print(f'  ditulis {f1}')
    print(f'  ditulis {f4}')
    print('\nKeduanya memakai label ARIMA. Empat gambar lain naskah pendamping '
          'tidak\nmenyebut nama metode, jadi tidak perlu dibangun ulang.')


if __name__ == '__main__':
    main()
