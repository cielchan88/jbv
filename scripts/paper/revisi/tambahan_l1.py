"""Loss absolut untuk metode lain, sesudah LightGBM-L1 memimpin (review ketujuh).

    JBV_HASIL=hasil_v2 JBV_LEAF=A.2.a,A.2.b python scripts/paper/revisi/tambahan_l1.py

  XGBoost  loss_l1     objective reg:absoluteerror, setelan terpilih v2 yang sama
  Ridge    median_lin  regresi median linear (quantile 0,5, tanpa penalti) pada
                       25 fitur terpilih yang sama dengan Ridge utama, dengan
                       penjaga yang sama

Random forest dengan kriteria absolute_error tidak dihitung karena terlalu lambat.
Keluaran: v2_tambahan_l1.csv (skema sama dengan v2_ramalan.csv).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('JBV_HASIL', 'hasil_v2')
import rerun_v2 as V                         # noqa: E402
import numpy as np                           # noqa: E402
import pandas as pd                          # noqa: E402
from sklearn.linear_model import QuantileRegressor   # noqa: E402

OUT = V.jalur('v2_tambahan_l1.csv')
CADANGAN = []


def median_lin(S, t, kol):
    X = S.F['int'][kol].values
    Xl, xt = X[:t], X[t:t + 1]
    sd = Xl.std(0)
    pakai = sd > 1e-8 * (np.abs(Xl).max(0) + 1)
    Xl, xt, sd = Xl[:, pakai], xt[:, pakai], sd[pakai]
    xt = np.clip(xt, Xl.min(0), Xl.max(0))
    mu = Xl.mean(0)
    # Target diskalakan demi kestabilan numerik (regresi median ekuivarian
    # terhadap skala). Bila LP tanpa penalti gagal, pakai penalti L1 sangat kecil.
    sy = float(np.std(S.y[:t])) or 1.0
    for alfa in (0.0, 1e-6, 1e-4):
        try:
            qr = QuantileRegressor(quantile=0.5, alpha=alfa, solver='highs').fit((Xl - mu) / sd, S.y[:t] / sy)
            if alfa:
                CADANGAN.append((S.leaf, t, alfa))
            return float(qr.predict((xt - mu) / sd)[0]) * sy
        except TypeError:
            continue
    raise RuntimeError(f'regresi median gagal {S.leaf} t={t}')


def main():
    tun = V.baca(V.HASIL + 'v2_setelan.csv').drop_duplicates(['leaf', 'model'], keep='last')
    cfg = {(r.leaf, r.model): int(r.cfg) for r in tun.itertuples()}
    sudah = V.baca(OUT)
    sudah = set(sudah.leaf) if len(sudah) else set()
    panel, dcols, dall = V.load_panel()
    lv = V.leaves(panel)
    pl, pu, tp = V.pasar()
    for _, r in lv.iterrows():
        if r['Row_ID'] in sudah:
            continue
        S = V.Seri(r, dcols, dall, pl, pu, tp)
        g = V.GRID['XGBoost'][cfg[(S.leaf, 'XGBoost')]]
        rows = []
        for t in S.rentang('uji'):
            kol = S.pilih('int', t, V.K_UTAMA, 1.0)
            X, yv = S.F['int'][kol].values, S.F['int']['value'].values
            m = V.model('XGBoost', g, 0).set_params(objective='reg:absoluteerror').fit(X[:t], yv[:t])
            rows.append(S.baris('uji', t, 'XGBoost', 'loss_l1', 0, float(m.predict(X[t:t + 1])[0])))
            rows.append(S.baris('uji', t, 'Ridge', 'median_lin', 0, median_lin(S, t, kol)))
        pd.DataFrame(rows)[V.KOLOM_OUT].to_csv(OUT, mode='a', header=not os.path.exists(OUT), index=False)
        print(f'selesai {S.leaf}  penalti cadangan di {sum(c[0] == S.leaf for c in CADANGAN)} origin', flush=True)


if __name__ == '__main__':
    main()
