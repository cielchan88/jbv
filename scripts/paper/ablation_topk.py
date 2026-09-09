"""Ablation jumlah fitur (top_k) pada seleksi fitur.

Skrip yang menghasilkan angka di komentar TOP_K_FEATURES
(utils/feature_config.py) dan bagian ablation jumlah fitur di naskah.
Keluarannya CSV per unit; ubah tujuannya lewat env ABLATION_OUT.

Menjawab satu pertanyaan yang belum pernah diuji: apakah menaikkan jumlah fitur
yang diteruskan ke model memperbaiki akurasi. Satu-satunya arm yang pernah
dicoba sebelumnya justru ke bawah (top-10), jadi arah ke atas masih kosong.

Protokolnya menyalin dua eksperimen yang sudah tercatat di
select_top_features_optimized supaya angkanya sebanding: 18 leaf x 3 jendela
rolling-origin x 3 model pohon, horizon 60 hari, dibandingkan dengan Wilcoxon
signed-rank berpasangan terhadap arm baseline top_k=25.

Yang diukur MASE, bukan MAE, supaya unit dengan skala berbeda bisa digabung.

Catatan penting soal apa yang TIDAK diuji di sini: seleksi fitur menentukan
model yang TERLATIH, dan model terlatihnya sama untuk semua protokol prediksi.
Jadi hasilnya informatif untuk ketiganya, tapi tetap diukur lewat satu jalur
prediksi saja.
"""
import os, sys, warnings, json, time
os.chdir('/home/user/jbv'); sys.path.insert(0, '/home/user/jbv')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

import utils.forecasting.randomforest_model as rf_mod
import utils.forecasting.lightgbm_model as lgb_mod
import utils.forecasting.xgboost_model as xgb_mod
from utils.forecasting import (RandomForestForecaster, LightGBMForecaster,
                               XGBoostForecaster)

HORIZON = 60
WINDOWS = 3
MIN_TRAIN = 300
ARMS = [10, 12, 15, 18, 20, 25, 40, 60]
BASELINE = 25   # nilai lama; TOP_K_FEATURES kini 12

MODELS = {
    'RandomForest': (RandomForestForecaster, rf_mod),
    'LightGBM':     (LightGBMForecaster,     lgb_mod),
    'XGBoost':      (XGBoostForecaster,      xgb_mod),
}


def mase(actual, pred, train):
    """MASE dengan penyebut naive musiman-1 dari periode training."""
    actual = np.asarray(actual, float)
    pred = np.asarray(pred, float)
    d = np.mean(np.abs(np.diff(np.asarray(train, float))))
    if not np.isfinite(d) or d == 0:
        return np.nan
    return np.mean(np.abs(actual - pred)) / d


def main():
    panel = pd.read_csv('data/processed/sdv-wide.csv')
    dcols = [c for c in panel.columns if c[:2] == '20']
    dates_all = pd.to_datetime(dcols)

    # leaf = simpul tanpa anak. sdv-wide.csv tidak memuat kolom Children, jadi
    # hierarkinya diturunkan dari Row_ID: sebuah simpul punya anak kalau ada
    # Row_ID lain yang diawali "<id>.".
    #
    # Dua hal yang mudah salah di sini:
    #   - "Level terdalam" BUKAN definisi leaf. Level 3 hanya memberi 9 baris,
    #     karena cabang B dan C sudah berhenti di level 2.
    #   - D adalah total A+B+C dan memang tidak punya anak, jadi aturan prefiks
    #     akan menandainya leaf. Ia dikeluarkan secara eksplisit - kalau ikut,
    #     agregat teratas akan dihitung sebagai unit tersendiri.
    ids = list(panel['Row_ID'])
    def _punya_anak(i):
        return any(j != i and j.startswith(i + '.') for j in ids)
    leaves = panel[panel['Row_ID'].apply(lambda i: not _punya_anak(i))
                   & (panel['Row_ID'] != 'D')]
    assert len(leaves) == 18, f'harusnya 18 leaf, dapat {len(leaves)}'
    print(f'leaf: {len(leaves)} | horizon {HORIZON} | jendela {WINDOWS} | arm {ARMS}',
          flush=True)

    rows = []
    t0 = time.time()
    for li, (_, r) in enumerate(leaves.iterrows()):
        y = pd.to_numeric(r[dcols].values, errors='coerce')
        ok = ~pd.isna(y)
        d_i, y_i = dates_all[ok], y[ok].astype(float)
        if len(y_i) < MIN_TRAIN + HORIZON * WINDOWS:
            continue

        for w in range(WINDOWS):
            te = len(y_i) - w * HORIZON
            ts = te - HORIZON
            if ts < MIN_TRAIN:
                continue
            dtr, ytr = d_i[:ts], y_i[:ts]
            yte = y_i[ts:te]

            for mname, (cls, mod) in MODELS.items():
                for k in ARMS:
                    old = mod.TOP_K_FEATURES
                    mod.TOP_K_FEATURES = k
                    try:
                        m = cls()
                        m.fit(dtr, ytr)
                        # predict() mengembalikan (nilai, tanggal), bukan array.
                        # Tanpa unpack, len()-nya 2 dan MASE-nya omong kosong.
                        vals, _dates = m.predict(dtr, ytr, HORIZON)
                        p = np.asarray(vals, float)[:len(yte)]
                        v = mase(yte, p, ytr)
                    except Exception as e:
                        v = np.nan
                    finally:
                        mod.TOP_K_FEATURES = old
                    rows.append({'leaf': r['Row_ID'], 'window': w,
                                 'model': mname, 'top_k': k, 'mase': v})
        print(f'  leaf {li+1}/{len(leaves)} selesai ({time.time()-t0:.0f}s)', flush=True)

    df = pd.DataFrame(rows)
    out = os.environ.get('ABLATION_OUT', 'ablation_topk.csv')
    df.to_csv(out, index=False)
    print(f'\ndisimpan: {out}  ({len(df)} baris)', flush=True)

    # ---- ringkasan berpasangan terhadap baseline ----
    piv = df.pivot_table(index=['leaf', 'window', 'model'], columns='top_k',
                         values='mase')
    piv = piv.dropna()
    print(f'\nunit lengkap terpakai: {len(piv)}\n')
    print(f'{"arm":>5s} {"MASE rata":>10s} {"vs k=25":>9s} {"menang":>12s} {"Wilcoxon p":>11s}')
    base = piv[BASELINE]
    for k in ARMS:
        col = piv[k]
        delta = 100 * (col.mean() - base.mean()) / base.mean()
        win = int((col < base).sum())
        if k == BASELINE:
            print(f'{k:5d} {col.mean():10.3f} {"(acuan)":>9s} {"-":>12s} {"-":>11s}')
            continue
        try:
            _, p = wilcoxon(col, base)
        except Exception:
            p = np.nan
        print(f'{k:5d} {col.mean():10.3f} {delta:+8.2f}% {win:6d}/{len(col):<5d} {p:11.4f}')

    print('\nper model (delta MASE terhadap k=25, negatif = lebih baik):')
    pm = piv.reset_index()
    print(f'{"model":14s}' + ''.join(f'{k:>10d}' for k in ARMS))
    for mname in MODELS:
        sub = pm[pm['model'] == mname]
        b = sub[BASELINE].mean()
        line = f'{mname:14s}'
        for k in ARMS:
            line += f'{100*(sub[k].mean()-b)/b:+9.2f}%'
        print(line)


if __name__ == '__main__':
    main()
