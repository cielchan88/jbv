"""Komputasi ulang hasil utama pada konfigurasi OPTIMAL.

Pengulas menolak tiga hal, dan ketiganya menuntut konfigurasi yang sama:

  1. Peringkat Tabel 6 memakai parameter bawaan, padahal RandomForest
     tersetel membaik 9,5% dan semestinya naik ke peringkat satu.
  2. Seleksi fitur memakai Spearman univariat, padahal mRMR lebih baik 7%.
  3. Parameter di-fit sekali di awal blok, padahal refit harian lebih baik
     4,5% dan biayanya hanya hitungan detik.

Jadi seluruh hasil utama dijalankan ulang dengan: mRMR (beta=1) + setelan
terpilih dari blok validasi + refit SETIAP HARI.

CHECKPOINT. Lingkungan ini pernah membunuh proses latar tanpa jejak, dan
pekerjaan ini berjam-jam. Setiap sel (leaf x model) ditulis ke CSV begitu
selesai, dan sel yang sudah ada di CSV dilewati saat dijalankan ulang. Mati
di tengah berarti kehilangan satu sel, bukan seluruh pekerjaan.
"""
import os
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h1_common import *          # noqa: F403

warnings.filterwarnings('ignore')

import utils.forecasting.randomforest_model as rfm
import utils.forecasting.lightgbm_model as lgm
import utils.forecasting.xgboost_model as xgm
from utils.forecasting import (ARIMAForecaster, APUVAForecaster,
                               CrostonForecaster, LightGBMForecaster,
                               NaiveForecaster, ProphetForecaster,
                               RandomForestForecaster, XGBoostForecaster)
from utils.feature_engineering_optimized import select_top_features_optimized

S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hasil') + os.sep
os.makedirs(S, exist_ok=True)
OUT = S + 'opt_rolling.csv'
TUNE = S + 'opt_tuned.csv'
NROLL = 30
# Origin validasi untuk memilih setelan. Lebih pendek dari blok uji dengan
# sengaja: ini tahap PEMILIHAN, bukan hasil yang dilaporkan, dan menyetel
# dengan refit harian pada 30 origin makan 10 menit per model per leaf -
# 9 jam hanya untuk menyetel. Sepuluh origin menahan biayanya di sepertiga
# tanpa mengubah hal yang dipersoalkan pengulas: setelan tetap dipilih pada
# blok yang MENDAHULUI blok uji, jadi tidak ada kebocoran.
NVAL = 10
TOP_K = 25              # sama dengan naskah, supaya hanya SATU hal berubah
MRMR_BETA = 1.0
SEASONAL = 'SeasonalDecomp'

ML = {'RandomForest': (RandomForestForecaster, rfm),
      'LightGBM': (LightGBMForecaster, lgm),
      'XGBoost': (XGBoostForecaster, xgm)}

GRID = {
    'RandomForest': [dict(n_estimators=100, max_depth=10),
                     dict(n_estimators=300, max_depth=10),
                     dict(n_estimators=300, max_depth=None),
                     dict(n_estimators=100, max_depth=4)],
    'LightGBM': [dict(n_estimators=100, learning_rate=0.05, max_depth=5),
                 dict(n_estimators=400, learning_rate=0.02, max_depth=5),
                 dict(n_estimators=100, learning_rate=0.10, max_depth=3),
                 dict(n_estimators=400, learning_rate=0.05, max_depth=8)],
    'XGBoost': [dict(n_estimators=100, max_depth=5, learning_rate=0.05),
                dict(n_estimators=400, max_depth=5, learning_rate=0.02),
                dict(n_estimators=100, max_depth=3, learning_rate=0.10),
                dict(n_estimators=400, max_depth=8, learning_rate=0.05)],
}

ALL_MODELS = ['Naive', 'NaiveMean', 'NaiveDrift', 'Croston', SEASONAL,
              'ARIMA', 'Prophet', 'RandomForest', 'LightGBM', 'XGBoost']


def build(name, row_id, cfg=None):
    if name == 'Naive':        return NaiveForecaster(method='last')
    if name == 'NaiveMean':    return NaiveForecaster(method='mean')
    if name == 'NaiveDrift':   return NaiveForecaster(method='drift')
    if name == 'Croston':      return CrostonForecaster()
    if name == SEASONAL:       return APUVAForecaster(row_id=row_id)
    if name == 'ARIMA':        return ARIMAForecaster()
    if name == 'Prophet':      return ProphetForecaster()
    return ML[name][0](**(cfg or {}))


def p1(m, d, y):
    v, _ = m.predict(d, y, 1)
    return float(np.asarray(v).ravel()[0])


def pasang_mrmr():
    """mRMR untuk ketiga model berbasis fitur."""
    for _, mod in ML.values():
        mod.TOP_K_FEATURES = TOP_K
        mod.select_top_features = (
            lambda df, top_k=TOP_K, _b=MRMR_BETA:
            select_top_features_optimized(df, top_k=top_k, mrmr_beta=_b))


def sudah(path, kunci):
    """Sel yang sudah tercatat, untuk melewati saat dijalankan ulang."""
    if not os.path.exists(path):
        return set()
    try:
        d = pd.read_csv(path)
        return set(map(tuple, d[list(kunci)].drop_duplicates().values))
    except Exception:
        return set()


def tulis(path, rows):
    df = pd.DataFrame(rows)
    df.to_csv(path, mode='a', header=not os.path.exists(path), index=False)


def pilih_setelan(r, d, y, t0):
    """Pilih setelan per (leaf, model) di blok validasi yang MENDAHULUI uji.

    Tanpa pemisahan ini, setelan terpilih sudah melihat blok uji dan
    angkanya bocor.
    """
    done = sudah(TUNE, ('leaf', 'model'))
    te_cut = len(y) - NROLL
    va_cut = te_cut - NVAL
    den_va = scale_denom(y[:va_cut])
    rows = []
    for nm in ML:
        if (r['Row_ID'], nm) in done:
            continue
        skor = []
        for ci, cfg in enumerate(GRID[nm]):
            ae = []
            try:
                # Blok validasi juga memakai refit harian, supaya setelan
                # dipilih pada rezim yang sama dengan yang nanti dipakai.
                for t in range(va_cut, te_cut):
                    m = build(nm, r['Row_ID'], cfg)
                    m.fit(d[:t], y[:t])
                    ae.append(one_step_metrics(y[t], p1(m, d[:t], y[:t]), den_va)['mase'])
                skor.append((float(np.nanmean(ae)), ci))
            except Exception:
                skor.append((float('inf'), ci))
        best = min(skor)[1]
        # Tulis SETIAP SEL, jangan ditumpuk sampai leaf selesai. Kontainer ini
        # restart tiap belasan menit dan membunuh proses lepas; menumpuk berarti
        # kehilangan seluruh leaf padahal selnya sudah dihitung.
        tulis(TUNE, [{'leaf': r['Row_ID'], 'model': nm, 'cfg': best,
                      'mase_val': min(skor)[0]}])
        print(f'  setel {r["Row_ID"]}/{nm} -> cfg{best} ({time.time()-t0:.0f}s)',
              flush=True)


def main():
    panel, dcols, dall = load_panel()
    lv = leaves(panel)
    t0 = time.time()
    pasang_mrmr()

    # ---- tahap 1: setelan per leaf/model dari blok validasi ----
    for _, r in lv.iterrows():
        d, y = series_of(r, dcols, dall)
        pilih_setelan(r, d, y, t0)
    print(f'SETELAN SELESAI ({time.time()-t0:.0f}s)', flush=True)

    tuned = pd.read_csv(TUNE).set_index(['leaf', 'model'])['cfg'].to_dict()

    # ---- tahap 2: blok uji, refit harian, seluruh model ----
    done = sudah(OUT, ('leaf', 'model'))
    for _, r in lv.iterrows():
        d, y = series_of(r, dcols, dall)
        cut = len(y) - NROLL
        den = scale_denom(y[:cut])
        for nm in ALL_MODELS:
            if (r['Row_ID'], nm) in done:
                continue
            cfg = None
            if nm in ML:
                ci = tuned.get((r['Row_ID'], nm))
                cfg = GRID[nm][int(ci)] if ci is not None else None
            rows = []
            try:
                for t in range(cut, len(y)):
                    m = build(nm, r['Row_ID'], cfg)
                    m.fit(d[:t], y[:t])          # REFIT HARIAN
                    rec = one_step_metrics(y[t], p1(m, d[:t], y[:t]), den)
                    rec.update(leaf=r['Row_ID'], model=nm, origin=t - cut)
                    rows.append(rec)
            except Exception as e:
                print(f'  GAGAL {r["Row_ID"]}/{nm}: {type(e).__name__}: {e}',
                      flush=True)
                continue
            tulis(OUT, rows)
            print(f'  {r["Row_ID"]}/{nm} selesai ({time.time()-t0:.0f}s)',
                  flush=True)
    print(f'SELESAI TOTAL ({time.time()-t0:.0f}s)', flush=True)


if __name__ == '__main__':
    main()
