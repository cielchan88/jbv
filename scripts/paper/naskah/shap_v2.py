"""SHAP untuk desain v2: random forest dan LightGBM pada model akhir tiap seri.

    JBV_HASIL=hasil_v2 python scripts/paper/naskah/shap_v2.py

Model akhir = dilatih pada seluruh data sejak laporan pertama sampai origin uji
terakhir, dengan setelan terpilih v2 dan seleksi mRMR k = 25. Dua kolam:

    int   fitur rekayasa saja (pipeline utama v2)
    ubah  ditambah data pasar sebagai perubahan harian (lengan pasar_ubah)

Pangsa dikelompokkan dengan taksonomi Lampiran D ditambah 'Market'. Beeswarm
random forest pada kolam 'ubah' digambar untuk Lampiran B. Keluaran tanpa nilai
arus: keluaran/shap_v2.json dan keluaran/gambar/beeswarm_v2/<leaf>.png.
"""
import json
import os
import sys

NASKAH = os.path.dirname(os.path.abspath(__file__))
REVISI = os.path.join(os.path.dirname(NASKAH), 'revisi')
sys.path.insert(0, REVISI)
os.environ.setdefault('JBV_HASIL', 'hasil_v2')
import rerun_v2 as V                     # noqa: E402  (chdir ke akar repo)
import numpy as np                       # noqa: E402
import pandas as pd                      # noqa: E402
import shap                              # noqa: E402
from shap_baru import beeswarm           # noqa: E402

NAMA = json.load(open(os.path.join(os.path.dirname(NASKAH), 'nama_leaf.json')))['peta']
KEL = [('Market', lambda c: c.startswith('ext_')),
       ('Interaction', lambda c: '_x_' in c),
       ('Lag', lambda c: c.startswith('lag_')),
       ('Rolling statistics', lambda c: c.startswith('rolling_')),
       ('Exponentially weighted mean', lambda c: c.startswith('ewm_')),
       ('Difference and percentage change', lambda c: c.startswith('value_')),
       ('Volatility and range', lambda c: any(k in c for k in ('volatil', 'price_position', 'max_change',
                                                                 'min_change', 'change_range'))),
       ('Extreme value and jump', lambda c: any(k in c for k in ('z_score', 'is_extreme', 'jump'))),
       ('Technical indicator', lambda c: any(c.startswith(k) for k in ('rsi', 'bb_', 'macd'))),
       ('Calendar and Fourier', lambda c: True)]


def kelompok(c):
    return next(n for n, f in KEL if f(c))


tun = V.baca(V.HASIL + 'v2_setelan.csv').drop_duplicates(['leaf', 'model'], keep='last')
cfg = {(r.leaf, r.model): int(r.cfg) for r in tun.itertuples()}
panel, dcols, dall = V.load_panel()
lv = V.leaves(panel)
pl, pu, tp = V.pasar()
GBR = os.path.join(NASKAH, 'keluaran', 'gambar', 'beeswarm_v2')
os.makedirs(GBR, exist_ok=True)
out = {}
for _, r in lv.iterrows():
    S = V.Seri(r, dcols, dall, pl, pu, tp)
    N = len(S.y)
    hasil = {}
    for fk in ('int', 'ubah', 'level'):
        kol = S.pilih(fk, N, V.K_UTAMA, 1.0)
        X = S.F[fk][kol]
        yv = S.F[fk]['value'].values
        Xs = X.iloc[-300:]
        per = {'n_ext': int(sum(c.startswith('ext_') for c in kol)),
               'n_lag': int(sum(c.startswith('lag_') and '_x_' not in c for c in kol))}
        for nm in ('RandomForest', 'LightGBM'):
            sd = V.SEED_RF[0] if nm == 'RandomForest' else 0
            m = V.model(nm, V.GRID[nm][cfg[(S.leaf, nm)]], sd).fit(X.values, yv)
            sv = shap.TreeExplainer(m).shap_values(Xs, check_additivity=False)
            imp = np.abs(sv).mean(0)
            tot = imp.sum() + 1e-12
            fam = {}
            for i, c in enumerate(kol):
                fam[kelompok(c)] = fam.get(kelompok(c), 0.0) + float(100 * imp[i] / tot)
            per[nm] = fam
            if nm == 'RandomForest' and fk == 'ubah':
                beeswarm(kol, Xs, sv, NAMA.get(S.leaf, S.leaf), os.path.join(GBR, f'{S.leaf}.png'))
        hasil[fk] = per
    out[S.leaf] = hasil
    print(f"  {S.leaf}: pasar terpilih {hasil['ubah']['n_ext']}, pangsa pasar RF "
          f"{hasil['ubah']['RandomForest'].get('Market', 0):.1f}% LGBM "
          f"{hasil['ubah']['LightGBM'].get('Market', 0):.1f}%", flush=True)
json.dump(out, open(os.path.join(NASKAH, 'keluaran', 'shap_v2.json'), 'w'), indent=1)
print('ditulis keluaran/shap_v2.json')
