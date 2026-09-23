"""Berapa slot fitur yang benar-benar dimenangkan variabel pasar?

Hanya menjalankan penyeleksi - tidak ada model yang dilatih - jadi murah dan
bisa dijalankan di mana saja, termasuk di luar VPS. Mengisi kolom "Market
slots" di Tabel 8 dan memeriksa dua klaim di naskah.

KENAPA SKRIP INI ADA. Naskah sempat membandingkan 1,9 slot (aturan mRMR)
dengan 4,5 slot (aturan univariat). Kedua angka itu benar, tapi datang dari
KOLAM LAG YANG BERBEDA - 4,5 diukur pada kolam 4 lag yang lama - sehingga
selisihnya mencampur dua perubahan sekaligus dan menyalahkan penyeleksi atas
sebagian efek pelebaran kolam. Pada kolam yang sama pembandingnya 3,72.
Skrip ini menghitung keempat angka itu dalam satu jalan supaya tidak
tercampur lagi.

SATU HASIL YANG PERLU DIINGAT. Slot nol TIDAK berarti tanpa efek. Kriteria
mRMR hanya dijalankan atas 3k kandidat teratas menurut relevansi mentah
(lihat select_top_features_optimized di feature_engineering_optimized.py),
jadi variabel pasar yang mengalahkan satu fitur internal pada korelasi saja
bisa menendangnya keluar dari daftar pendek tanpa pernah terpilih sendiri.
B.d adalah contohnya: nol slot di kedua nilai k, tapi tetap 4,3% lebih buruk
pada k=25. Kolom "Market slots" adalah batas bawah paparan.

Checkpoint per leaf ke hasil/slot_pasar.json, jadi aman dijalankan ulang.
"""
import json
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h1_common import *            # noqa: F403
warnings.filterwarnings('ignore')

import pandas as pd

from utils.feature_engineering_optimized import (create_features_optimized,
                                                 select_top_features_optimized)

H = HASIL                      # ikut JBV_PANEL / JBV_HASIL, lihat h1_common
CKPT = H + 'slot_pasar.json'
NROLL = 30
KS = (12, 25)
ATURAN = ((1.0, 'mrmr'), (0.0, 'univ'))

# Kolom bantu yang bukan kandidat fitur. create_features_optimized
# mengembalikannya bersama fitur, dan penyeleksi membuangnya - jadi jumlah
# kandidat yang dilaporkan naskah adalah jumlah kolom dikurangi ketiganya.
BUKAN_FITUR = {'date', 'ds', 'value'}


def main():
    os.makedirs(H, exist_ok=True)
    st = json.load(open(CKPT)) if os.path.exists(CKPT) else {}

    panel, dcols, dall = load_panel()
    lv = leaves(panel)
    esd, edt = load_external()
    print(f'{len(lv)} leaf, {len(esd)} variabel pasar, blok uji {NROLL} hari\n', flush=True)

    for _, r in lv.iterrows():
        rid = r['Row_ID']
        if rid in st:
            continue
        d, y = series_of(r, dcols, dall)
        cut = len(y) - NROLL
        s = pd.DataFrame({'ds': d[:cut], 'y': y[:cut]})

        # Persis seperti yang dilihat model: fit sekali di awal blok uji,
        # jadi kandidatnya dibangun dari data latih saja.
        f_ext = create_features_optimized(s, external_series=esd,
                                          external_series_dates=edt)
        f_int = create_features_optimized(s)
        rec = {
            'kandidat_internal': len([c for c in f_int.columns if c not in BUKAN_FITUR]),
            'kandidat_total': len([c for c in f_ext.columns if c not in BUKAN_FITUR]),
            'kandidat_pasar': sum(1 for c in f_ext.columns if c.startswith('ext_')),
        }
        for k in KS:
            for beta, tag in ATURAN:
                top, _ = select_top_features_optimized(f_ext, top_k=k, mrmr_beta=beta)
                rec[f'k{k}_{tag}'] = sum(1 for c in top if c.startswith('ext_'))
        st[rid] = rec
        json.dump(st, open(CKPT, 'w'), indent=1)
        print(f"  {rid:6s} kandidat pasar {rec['kandidat_pasar']:3d}  " +
              '  '.join(f"k{k} {tag} {rec[f'k{k}_{tag}']:2d}"
                        for k in KS for _, tag in ATURAN), flush=True)

    D = pd.DataFrame(st).T
    print('\n' + '=' * 62)
    print('KANDIDAT (jumlah kolom dikurangi date/ds/value)')
    print(f"  internal saja : {int(D.kandidat_internal.mode()[0])}")
    print(f"  dengan pasar  : {int(D.kandidat_total.mode()[0])}"
          f"  (pasar {int(D.kandidat_pasar.mode()[0])})")

    print(f'\nRATA SLOT PASAR YANG TERPILIH, {len(D)} leaf')
    print('  Kedua aturan diukur pada kolam lag yang SAMA. Selisihnya murni')
    print('  efek penyeleksi - itulah gunanya menghitung keduanya di sini.')
    for k in KS:
        print(f"  k={k:2d}   mRMR {D[f'k{k}_mrmr'].mean():.2f}"
              f"   univariat {D[f'k{k}_univ'].mean():.2f}")

    print('\nLEAF YANG MEMILIH MINIMAL SATU FITUR PASAR')
    for k in KS:
        print(f"  k={k:2d}   mRMR {int((D[f'k{k}_mrmr'] > 0).sum())}/{len(D)}"
              f"   univariat {int((D[f'k{k}_univ'] > 0).sum())}/{len(D)}")

    print(f'\nditulis: {CKPT}')
    print('Kolom "Market slots" Tabel 8 memakai kolom k25_mrmr.')


if __name__ == '__main__':
    main()
