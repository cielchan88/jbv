"""Pembanding TOP-DOWN untuk galat total harian (review ketiga).

Tabel metrik operasional menjumlahkan ramalan 15 seri (bottom-up). Pembanding
yang wajar adalah meramal total itu langsung. Di sini ARIMA (kelas yang sama
dengan benchmark naskah) dan random walk dijalankan pada jumlah 15 seri,
dengan 30 origin dan refit harian yang sama. Hasil: keluaran/topdown.json,
dibaca buat_tables.py. Berisi nilai aktual, jadi TIDAK di-commit.
"""
import json, os, sys, time
import numpy as np
import pandas as pd

AKAR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, AKAR)
os.chdir(AKAR)
from utils.forecasting import ARIMAForecaster  # noqa: E402

# Panel dibaca langsung (tanpa h1_common, yang memeriksa folder hasil). Leaf =
# baris tanpa anak, selain total D - definisi yang sama dengan h1_common.leaves.
p = pd.read_csv('data/processed/sdv-wide-gabung.csv')
dcols = [c for c in p.columns if c[:2] == '20']
ids = list(p.Row_ID)
lv = p[[not any(j != i and j.startswith(i + '.') for j in ids) and i != 'D' for i in ids]]
assert len(lv) == 15, len(lv)
NROLL = 30
d = pd.to_datetime(dcols)
Y = lv[dcols].apply(pd.to_numeric, errors='coerce')
assert not Y.isna().any().any()
y = Y.sum().values.astype(float)
cut = len(y) - NROLL
out, t0 = [], time.time()
for t in range(cut, len(y)):
    m = ARIMAForecaster().fit(d[:t], y[:t])
    pr = float(m.predict(d[:t], y[:t], 1)[0][0])
    out.append(dict(origin=t - cut, actual=float(y[t]), arima=pr, rw=float(y[t - 1]), orde=list(m.order)))
    print(f'  origin {t-cut+1}/{NROLL} orde {m.order} ({time.time()-t0:.0f}s)', flush=True)
tujuan = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keluaran', 'topdown.json')
json.dump(out, open(tujuan, 'w'), indent=1)
print('ditulis', tujuan)
