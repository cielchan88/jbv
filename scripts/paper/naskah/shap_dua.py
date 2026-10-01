"""SHAP untuk RandomForest DAN LightGBM, dengan taksonomi Lampiran D.

Review ketiga: (1) SHAP di naskah hanya dari random forest padahal
pemimpinnya LightGBM; (2) keluarga di Gambar 10 tidak sama dengan Lampiran D
(Interaction dan Calendar/Fourier hilang). Di sini kedua learner dihitung pada
fitur dan setelan yang sama dengan shap_baru.py (k = 25, mRMR, setelan
terpilih per leaf), dan pangsa dikelompokkan dengan taksonomi Lampiran D
ditambah 'Market'. Hasil: keluaran/shap_dua.json (tanpa nilai arus).
"""
import json, os, sys, warnings
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jalan
HASIL = jalan.HASIL
sys.path.insert(0, os.path.join(jalan.REPO, 'scripts', 'paper', 'revisi'))
os.environ.setdefault('JBV_PANEL', 'data/processed/sdv-wide-gabung.csv')
os.environ['JBV_HASIL'] = os.path.basename(HASIL.rstrip(os.sep))
os.environ['JBV_NVAL'] = str(json.load(open(HASIL + 'konfigurasi.json')).get('nval', 10))
os.environ['JBV_DIAM'] = '1'
os.environ['JBV_BACA_SAJA'] = '1'
from h1_common import *          # noqa: F403,E402
warnings.filterwarnings('ignore')
import shap                      # noqa: E402
from sklearn.ensemble import RandomForestRegressor   # noqa: E402
from lightgbm import LGBMRegressor                   # noqa: E402
import shap_baru as SB            # noqa: E402  (feats, RF_GRID; tidak menjalankan main)
from rerun_optimal import GRID    # noqa: E402

KEL = [('Market', lambda c: c.startswith('ext_')),
       ('Interaction', lambda c: '_x_' in c),
       ('Lag', lambda c: c.startswith('lag_')),
       ('Rolling statistics', lambda c: c.startswith('rolling_')),
       ('Exponentially weighted mean', lambda c: c.startswith('ewm_')),
       ('Difference and percentage change', lambda c: c.startswith('value_')),
       ('Volatility and range', lambda c: any(k in c for k in ('volatil', 'price_position', 'max_change', 'min_change', 'change_range'))),
       ('Extreme value and jump', lambda c: any(k in c for k in ('z_score', 'is_extreme', 'jump'))),
       ('Technical indicator', lambda c: any(c.startswith(k) for k in ('rsi', 'bb_', 'macd'))),
       ('Calendar and Fourier', lambda c: True)]


def kelompok(c):
    return next(n for n, f in KEL if f(c))


tun = pd.read_csv(HASIL + 'opt_tuned.csv')
cfg = {(r.leaf, r.model): int(r.cfg) for r in tun.itertuples()}
panel, dcols, dall = load_panel()
lv = leaves(panel)
esd, edt = load_external()
out = {}
for _, r in lv.iterrows():
    rid = r['Row_ID']
    top, X, yv = SB.feats(r, dcols, dall, esd, edt)
    Xs = X.iloc[-300:]
    hasil = {'n_ext': int(sum(c.startswith('ext_') for c in top))}
    for nm, mk in (('RandomForest', lambda c: RandomForestRegressor(random_state=0, n_jobs=-1, **c)),
                   ('LightGBM', lambda c: LGBMRegressor(random_state=42, verbose=-1, **c))):
        m = mk(GRID[nm][cfg.get((rid, nm), 0)]).fit(X, yv)
        sv = shap.TreeExplainer(m).shap_values(Xs, check_additivity=False)
        imp = np.abs(sv).mean(0)
        tot = imp.sum() + 1e-12
        fam = {}
        for i, c in enumerate(top):
            fam[kelompok(c)] = fam.get(kelompok(c), 0.0) + float(100 * imp[i] / tot)
        hasil[nm] = fam
    out[rid] = hasil
    print(f"  {rid}  pasar RF {hasil['RandomForest'].get('Market', 0):5.1f}%  "
          f"LGBM {hasil['LightGBM'].get('Market', 0):5.1f}%", flush=True)
tujuan = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keluaran', 'shap_dua.json')
json.dump(out, open(tujuan, 'w'), indent=1)
print('ditulis', tujuan)
