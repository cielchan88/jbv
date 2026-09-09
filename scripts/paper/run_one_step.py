"""
Uji satu langkah dengan pelatihan maksimal.

Latih pada SELURUH sampel kecuali hari terakhir; uji pada hari terakhir saja.
Seluruh metode kecuali deep learning, di bawah tiga protokol: recursive,
direct, dan teacher-forced.

CATATAN DESAIN - dibaca dulu sebelum menafsirkan hasilnya.

Pada h = 1 ketiga protokol identik SECARA KONSTRUKSI, bukan secara empiris:
peramal rekursif belum mengumpankan balik apa pun, pembelajar teacher-forced
belum mengonsumsi satu pun nilai realisasi periode uji, dan model direct untuk
h = 1 adalah model satu-langkah yang sama. Karena itu skrip ini menjalankan
KETIGA jalur kode secara terpisah - bukan mengasumsikan hasilnya sama - supaya
kesamaannya menjadi bukti bahwa ketiga implementasi di Tahap II memang setara.
Kalau ada yang berbeda, itu bug, dan justru itulah yang ingin ditangkap.

Untuk metode yang bukan pembelajar berbasis lag (random walk, rata-rata
bergerak, AutoARIMA, VAR, Prophet, APUVA) protokol tidak terdefinisi sebagai
tiga hal berbeda: ramalan h-langkah lahir dari bentuk fungsionalnya. Metode
itu dijalankan sekali dan ditandai demikian.

Ukuran: n = 18 seri, satu hari uji. Sengaja dilaporkan sebagai potret, bukan
sebagai dasar uji hipotesis.
"""
import sys, os, time, warnings, json, argparse
import numpy as np
import pandas as pd

WT = os.path.dirname(os.path.abspath(__file__)) + '/paperwt'
sys.path.insert(0, WT)
os.chdir(WT)
warnings.filterwarnings('ignore')

from utils import load_holidays, ML_START_DATE
from utils.feature_config import TOP_K_FEATURES, TOP_K_CROSS_SERIES
from utils.feature_engineering_optimized import (
    create_features_optimized, select_top_features_optimized,
    calculate_series_correlations, select_top_correlated_series,
    prepare_external_series_data)
from utils.external_loader import load_and_merge_external_features
from utils.forecasting import (
    NaiveForecaster, ARIMAForecaster, ProphetForecaster, APUVAForecaster,
    VARForecaster, RandomForestForecaster, XGBoostForecaster,
    LightGBMForecaster, StackingForecaster)

from sklearn.ensemble import RandomForestRegressor
from lightgbm import LGBMRegressor
import xgboost as xgb

S = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('--data', default=None, help='path sdv-wide.csv (default: data/processed/sdv-wide.csv)')
A = ap.parse_args()

CSV = A.data or 'data/processed/sdv-wide.csv'
df = pd.read_csv(CSV)
META = ['Row_ID', 'Row_Label', 'Level']
time_cols = [c for c in df.columns if c not in META]


def children_of(pid):
    if pid == 'D':
        return ['A', 'B', 'C']
    return [r for r in df.Row_ID
            if r.startswith(pid + '.') and r != pid and r.count('.') == pid.count('.') + 1]


LEAVES = [r for r in df.Row_ID if len(children_of(r)) == 0]
LABEL = dict(zip(df.Row_ID, df.Row_Label))
hol = load_holidays()
tcm = (time_cols if ML_START_DATE is None
       else [c for c in time_cols if pd.to_datetime(c) >= pd.Timestamp(ML_START_DATE)])
dml = pd.to_datetime(tcm)
n = len(tcm)
SPLIT = n - 1                      # latih 1..n-1, uji hari ke-n
print(f"sampel {n} hari, latih {n-1}, uji 1 hari: {dml[-1].date()}", flush=True)

LAGBASED = ['RandomForest', 'XGBoost', 'LightGBM', 'Stacking']
FUNCFORM = ['Naive', 'NaiveMean', 'AutoARIMA', 'VAR', 'Prophet', 'APUVA']


def make(name):
    if name == 'Naive':        return NaiveForecaster(hol, method='last')
    if name == 'NaiveMean':    return NaiveForecaster(hol, method='mean', window=90)
    if name == 'AutoARIMA':    return ARIMAForecaster(hol)
    if name == 'Prophet':      return ProphetForecaster(hol)
    if name == 'APUVA':        return APUVAForecaster(hol)
    if name == 'VAR':          return VARForecaster(hol)
    if name == 'RandomForest': return RandomForestForecaster(hol)
    if name == 'XGBoost':      return XGBoostForecaster(hol)
    if name == 'LightGBM':     return LightGBMForecaster(hol)
    if name == 'Stacking':     return StackingForecaster(hol)
    raise ValueError(name)


def new_raw(name):
    """Estimator mentah untuk jalur direct (satu model per horizon)."""
    if name == 'RandomForest':
        return RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    if name == 'XGBoost':
        return xgb.XGBRegressor(n_estimators=100, learning_rate=0.05, max_depth=5,
                                random_state=42, verbosity=0, n_jobs=-1)
    return LGBMRegressor(n_estimators=100, learning_rate=0.05, max_depth=5,
                         random_state=42, verbose=-1, n_jobs=-1)


# --- seri lintas-deret untuk VAR ---------------------------------------------
# VAR jatuh ke mode univariat (ramalan konstan = nilai terakhir) kalau
# external_series tidak diberikan; lihat catatan di var_model.fit. Tanpa blok
# ini metrik VAR akan identik dengan baseline random walk, dan itu artefak
# skrip, bukan sifat modelnya. Konsumen lintas-deret yang lain (tiga pohon dan
# stacking) sengaja TIDAK diberi: pada protokol rekursif fiturnya tidak bisa
# dibentuk di titik asal ramalan, dan forecaster menyaringnya sendiri.
print("menyiapkan seri lintas-deret untuk VAR ...", flush=True)
CROSS = {}
for leaf in LEAVES:
    cand = [l for l in LEAVES if l != leaf]
    corr = calculate_series_correlations(df, leaf, cand, tcm)
    top30 = select_top_correlated_series(corr, top_k=TOP_K_CROSS_SERIES)
    CROSS[leaf] = load_and_merge_external_features(
        prepare_external_series_data(df, top30, tcm), tcm)
print(f"  selesai, contoh jumlah seri = {len(CROSS[LEAVES[0]])}", flush=True)

rows = []
t0 = time.time()
for i, leaf in enumerate(LEAVES):
    v = np.nan_to_num(df[df.Row_ID == leaf][time_cols].to_numpy(float).ravel())[-n:]
    tr_d, tr_v = dml[:SPLIT], v[:SPLIT]
    ext = CROSS.get(leaf, {})
    y_true = float(v[SPLIT])
    scale = float(np.mean(np.abs(np.diff(tr_v))))          # penyebut MASE
    last_train = float(tr_v[-1])

    def _fit(m):
        """VAR adalah satu-satunya konsumen lintas-deret yang sah pada protokol
        rekursif; sisanya dilatih univariat, sesuai konfigurasi Tahap II."""
        f = make(m)
        if m == 'VAR':
            f.fit(tr_d, tr_v, external_series=ext)
        else:
            f.fit(tr_d, tr_v)
        return f

    def rec(m):
        """Recursive: jalur produksi, satu langkah ke depan."""
        f = _fit(m)
        p, _ = f.predict(tr_d, tr_v, 1)
        return float(np.asarray(p, float).ravel()[0])

    def tf(m):
        """Teacher-forced: pembelajar diberi lag realisasi periode uji. Pada
        h = 1 belum ada observasi uji yang bisa dikonsumsi, jadi jalur ini
        memanggil predict dengan deret yang sama - hasilnya harus sama dengan
        rekursif, dan itulah yang diperiksa."""
        f = _fit(m)
        p, _ = f.predict(dml[:SPLIT], v[:SPLIT], 1)
        return float(np.asarray(p, float).ravel()[0])

    def dr(m):
        """Direct sejati: satu model memetakan X_t -> y_{t+1}, dilatih hanya
        pada data training, diramalkan dari fitur pada tanggal training
        terakhir. Untuk h = 1 ini setara model satu-langkah, tapi jalur
        kodenya berbeda."""
        feats = create_features_optimized(pd.DataFrame({'ds': tr_d, 'y': tr_v}),
                                          lag_steps=90, holidays_list=hol)
        allc = [c for c in feats.columns if c not in ('ds', 'date', 'value')]
        top, _ = select_top_features_optimized(feats, top_k=TOP_K_FEATURES)
        cols = [c for c in top if c in allc] or allc[:25]
        X = feats[cols].fillna(0).replace([np.inf, -np.inf], 0).to_numpy()
        yv = feats['value'].to_numpy()
        h = 1
        mod = new_raw(m if m in ('RandomForest', 'XGBoost') else 'LightGBM')
        mod.fit(X[:len(X) - h], yv[h:len(X)])
        return float(mod.predict(X[-1:])[0])

    for m in FUNCFORM + LAGBASED:
        paths = [('Recursive', rec), ('Teacher-forced', tf)]
        if m in LAGBASED and m != 'Stacking':
            paths.append(('Direct', dr))
        elif m in LAGBASED:
            paths.append(('Direct', rec))     # stacking tak punya jalur direct terpisah
        else:
            paths.append(('Direct', rec))
        for tag, fn in paths:
            t1 = time.time()
            try:
                yhat = fn(m)
                if not np.isfinite(yhat):
                    raise ValueError('ramalan tidak hingga')
                err = yhat - y_true
                rows.append({
                    'Row_ID': leaf, 'Series': LABEL.get(leaf, leaf), 'Model': m,
                    'Protocol': tag,
                    'lag_based': m in LAGBASED,
                    'actual': y_true, 'pred': yhat, 'error': err,
                    'abs_error': abs(err),
                    'scaled_abs_error': abs(err) / scale if scale > 1e-9 else np.nan,
                    'scale': scale, 'last_train': last_train,
                    'dir_hit': int(np.sign(yhat - last_train) == np.sign(y_true - last_train)),
                    'secs': round(time.time() - t1, 2)})
            except Exception as ex:
                print(f"  gagal {leaf} {m} {tag}: {str(ex)[:70]}", flush=True)
    print(f"[{i+1:2d}/{len(LEAVES)}] {leaf:8s} {(time.time()-t0)/60:5.1f} mnt", flush=True)

res = pd.DataFrame(rows)
res.to_csv(f'{S}/h1_results.csv', index=False)

print("\n=== PERIKSA IDENTITAS PROTOKOL (harus identik pada h = 1) ===")
piv = res.pivot_table(index=['Row_ID', 'Model'], columns='Protocol', values='pred')
piv = piv.dropna()
mx = (piv.max(axis=1) - piv.min(axis=1)).abs()
print(f"  {len(piv)} pasangan (seri, metode); selisih maksimum antar protokol = {mx.max():.6g}")
bad = piv[mx > 1e-6]
if len(bad):
    print("  BERBEDA - ini bug, bukan temuan:")
    print(bad.round(4).to_string())
else:
    print("  seluruh protokol menghasilkan angka yang sama - jalur kode setara.")

print("\n=== AKURASI SATU LANGKAH (rata-rata lintas 18 seri) ===")
one = res[res.Protocol == 'Recursive']
agg = one.groupby('Model').agg(
    MASE_h1=('scaled_abs_error', 'mean'),
    median=('scaled_abs_error', 'median'),
    MAE=('abs_error', 'mean'),
    bias=('error', 'mean'),
    DA=('dir_hit', 'mean'),
    secs=('secs', 'mean')).sort_values('MASE_h1')
agg['DA'] = (agg['DA'] * 100).round(1)
print(agg.round(3).to_string())

best = one.loc[one.groupby('Row_ID')['abs_error'].idxmin()].Model.value_counts()
print("\nmetode terbaik per seri:")
print(best.to_string())

out = {
    'test_date': str(dml[-1].date()),
    'n_train': int(SPLIT), 'n_test': 1, 'n_series': len(LEAVES),
    'identity_max_gap': float(mx.max()),
    'identity_pairs': int(len(piv)),
    'table': [{'model': m, 'lag_based': bool(m in LAGBASED),
               'mase': round(float(agg.loc[m, 'MASE_h1']), 3),
               'median': round(float(agg.loc[m, 'median']), 3),
               'mae': round(float(agg.loc[m, 'MAE']), 2),
               'bias': round(float(agg.loc[m, 'bias']), 2),
               'da': float(agg.loc[m, 'DA'])} for m in agg.index],
    'best_counts': {k: int(v) for k, v in best.items()},
    'n_below_one': int((agg.MASE_h1 < 1).sum()),
}
json.dump(out, open(f'{S}/h1_facts.json', 'w'), indent=1)
print(f"\n{(time.time()-t0)/60:.1f} menit")
print("SELESAI-H1", flush=True)
