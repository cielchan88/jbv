"""Lengan tambahan untuk review ketujuh, di atas hasil v2 (blok uji saja).

    JBV_HASIL=hasil_v2 JBV_LEAF=A.2.a,A.2.b python scripts/paper/revisi/tambahan_v2.py

Dihitung di lingkungan lokal dengan fungsi dan bingkai fitur rerun_v2.py:

  Ridge  ridge_lag     hanya 18 lag seri sendiri (praktis model AR linear)
         ridge_kal     25 fitur terpilih yang sama dengan Ridge utama, tetapi
                       kalender berkode bilangan bulat (hari, bulan, minggu)
                       dan interaksinya diganti dummy hari dan bulan
         ridge_semua   seluruh 116 kandidat, dengan perlakuan kalender yang sama
  LightGBM loss_l1     objective L1 (sesuai metrik MASE)
           loss_huber  objective Huber, delta = 1,345 x skala MASE seri

Penjaga Ridge (kolom hampir konstan dibuang, baris ramalan dipotong ke rentang
latih) dipakai di semua varian, sama dengan Ridge utama. Keluaran:
v2_tambahan.csv (skema sama dengan v2_ramalan.csv).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('JBV_HASIL', 'hasil_v2')
import rerun_v2 as V                         # noqa: E402
import numpy as np                           # noqa: E402
import pandas as pd                          # noqa: E402
from sklearn.linear_model import RidgeCV     # noqa: E402
from lightgbm import LGBMRegressor           # noqa: E402

OUT = V.jalur('v2_tambahan.csv')
KAL_INT = ('day_of_week', 'month', 'week_of_year')
ALFA = np.logspace(-3, 3, 13)


def kal_aman(kol):
    """Buang kalender bilangan bulat dan interaksinya; dummy ditambah terpisah."""
    return [c for c in kol if c not in KAL_INT and not any(c.endswith('_x_' + k) for k in KAL_INT)]


def dummy(S):
    tg = pd.DatetimeIndex(S.d)
    d = pd.get_dummies(pd.DataFrame({'dow': tg.dayofweek, 'bln': tg.month}).astype(str), drop_first=True)
    return d.values.astype(float)


def ridge(S, t, kol, tambah=None):
    X = S.F['int'][kol].values
    if tambah is not None:
        X = np.hstack([X, tambah])
    Xl, xt = X[:t], X[t:t + 1]
    sd = Xl.std(0)
    pakai = sd > 1e-8 * (np.abs(Xl).max(0) + 1)
    Xl, xt, sd = Xl[:, pakai], xt[:, pakai], sd[pakai]
    xt = np.clip(xt, Xl.min(0), Xl.max(0))
    mu = Xl.mean(0)
    rm = RidgeCV(alphas=ALFA).fit((Xl - mu) / sd, S.y[:t])
    return float(rm.predict((xt - mu) / sd)[0])


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
        D = dummy(S)
        lag = [c for c in S.kand_int if c.startswith('lag_') and '_x_' not in c]
        semua = kal_aman(S.kand_int)
        g = V.GRID['LightGBM'][cfg[(S.leaf, 'LightGBM')]]
        rows, n_kal = [], 0
        for t in S.rentang('uji'):
            kol = S.pilih('int', t, V.K_UTAMA, 1.0)
            n_kal += any(c in KAL_INT or any(c.endswith('_x_' + k) for k in KAL_INT) for c in kol)
            X, yv = S.F['int'][kol].values, S.F['int']['value'].values
            pr = {
                ('Ridge', 'ridge_lag'): ridge(S, t, lag),
                ('Ridge', 'ridge_kal'): ridge(S, t, kal_aman(kol), D),
                ('Ridge', 'ridge_semua'): ridge(S, t, semua, D),
            }
            for nama, obj in (('loss_l1', dict(objective='l1')),
                              ('loss_huber', dict(objective='huber', alpha=1.345 * S.den))):
                m = LGBMRegressor(random_state=42, verbose=-1, n_jobs=1, **g, **obj).fit(X[:t], yv[:t])
                pr[('LightGBM', nama)] = float(m.predict(X[t:t + 1])[0])
            for (met, lg), p in pr.items():
                rows.append(S.baris('uji', t, met, lg, 0, p))
        pd.DataFrame(rows)[V.KOLOM_OUT].to_csv(OUT, mode='a', header=not os.path.exists(OUT), index=False)
        print(f'selesai {S.leaf}: kalender bilangan bulat terpilih di {n_kal} dari {V.NROLL} origin', flush=True)


if __name__ == '__main__':
    main()
