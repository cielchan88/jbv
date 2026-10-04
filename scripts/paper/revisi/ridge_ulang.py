"""Hitung ulang HANYA Ridge di folder hasil v2, dengan penjaga ekstrapolasi.

    JBV_HASIL=hasil_v2 JBV_LEAF=A.2.b python scripts/paper/revisi/ridge_ulang.py

Jalan v2 pertama memakai Ridge tanpa penjaga dan satu origin meledak (lihat
ramal_ridge di rerun_v2.py). Model lain tidak tersentuh. Baris Ridge baru
ditulis ke v2_ridge.csv (per leaf, bisa diparalelkan dengan JBV_LEAF); ganti
baris lama dengan `--terapkan`, yang menyimpan salinan v2_ramalan.csv lama.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('JBV_HASIL', 'hasil_v2')
import rerun_v2 as V
import pandas as pd

if '--terapkan' in sys.argv:
    R = pd.read_csv(V.HASIL + 'v2_ramalan.csv', float_precision='round_trip')
    B = V.baca(V.HASIL + 'v2_ridge.csv')
    assert len(B) == 15 * (V.NROLL + V.NVAL), f'v2_ridge belum lengkap: {len(B)}'
    R.to_csv(V.HASIL + 'v2_ramalan_ridge_lama.csv', index=False)
    R = pd.concat([R[R.metode != 'Ridge'], B[V.KOLOM_OUT]], ignore_index=True)
    R.to_csv(V.HASIL + 'v2_ramalan.csv', index=False)
    print('diterapkan:', len(B), 'baris Ridge diganti')
    sys.exit(0)

panel, dcols, dall = V.load_panel()
lv = V.leaves(panel)
pl, pu, tp = V.pasar()
OUT = V.jalur('v2_ridge.csv')
for _, r in lv.iterrows():
    S = V.Seri(r, dcols, dall, pl, pu, tp)
    rows = []
    for blok in ('val', 'uji'):
        for t in S.rentang(blok):
            rows.append(S.baris(blok, t, 'Ridge', 'utama', 0, V.ramal_ridge(S, t)))
    pd.DataFrame(rows)[V.KOLOM_OUT].to_csv(OUT, mode='a', header=not os.path.exists(OUT), index=False)
    print('selesai', S.leaf, flush=True)
