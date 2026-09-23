"""Uji berpasangan dan median gabungan untuk seluruh tabel naskah.

Yang dihitung di sini TIDAK bisa dihitung dari berkas ringkasan. Rata-rata
per leaf sudah cukup untuk kolom mean, tapi median gabungan atas 540 atau
1.620 titik bukan rata-rata dari median per leaf - estimatornya berbeda - dan
uji Wilcoxon butuh setiap pasangan ramalan, bukan agregatnya.

Membaca lima berkas mentah di hasil/ dan menulis satu uji_statistik.json yang
bisa langsung dipakai menyusun tabel.

    Tabel 6   median gabungan per metode + uji terhadap metode terbaik
    Tabel 7   ablasi jumlah fitur, uji terhadap k = 25
    Tabel 8   data pasar hidup/mati, per (beta, k)
    Tabel 9   ablasi balik, per lengan + rincian per model dan per leaf
    Gambar 10 mRMR lawan univariat pada kondisi tanpa data pasar

Jalankan:  /opt/jbv/venv/bin/python scripts/paper/revisi/uji_statistik.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

_P = os.environ.get('JBV_PANEL')
_BAWAAN = 'hasil' if not _P else 'hasil_' + os.path.splitext(os.path.basename(_P))[0]
H = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 os.environ.get('JBV_HASIL', _BAWAAN)) + os.sep
OUT = H + 'uji_statistik.json'
ML = ['RandomForest', 'LightGBM', 'XGBoost']
KUNCI = ['leaf', 'model', 'origin']


def baca(nama):
    p = H + nama
    if not os.path.exists(p):
        print(f'  LEWAT: {nama} belum ada')
        return None
    d = pd.read_csv(p)
    print(f'  {nama}: {len(d)} baris')
    return d


def uji(a, b):
    """Bandingkan dua deret galat yang sudah berpasangan.

    'menang' dihitung untuk a, dan lebih kecil berarti lebih baik. p dari
    Wilcoxon signed-rank. Selisih nol dibuang oleh scipy, jadi n yang
    dilaporkan di sini adalah jumlah pasangan yang ada - bukan jumlah yang
    masuk ke statistik uji. Keduanya memang beda, dan naskah melaporkan n
    pasangan.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    n = int(len(a))
    menang = int((a < b).sum())
    p = float('nan')
    if n and np.any(a != b):
        try:
            p = float(wilcoxon(a, b).pvalue)
        except Exception as e:
            print(f'    (wilcoxon gagal: {type(e).__name__})')
    return {'menang': menang, 'n': n, 'p': p,
            'mean_a': float(a.mean()) if n else float('nan'),
            'mean_b': float(b.mean()) if n else float('nan')}


def bagian(judul):
    print('\n' + '=' * 66)
    print(judul)
    print('=' * 66)


hasil = {}

# ---------------------------------------------------------------- Tabel 6
bagian('TABEL 6  peringkat rolling: median gabungan + uji terhadap juara')
roll = baca('opt_rolling.csv')
if roll is not None:
    g = roll.groupby('model')['mase'].agg(['mean', 'median', 'max', 'count'])
    g = g.sort_values('mean')
    print(g.round(4).to_string())
    hasil['tabel6'] = {m: {k: float(v) for k, v in row.items()}
                       for m, row in g.iterrows()}

    juara = g.index[0]
    piv = roll.pivot_table(index=['leaf', 'origin'], columns='model', values='mase')
    print(f'\n  uji berpasangan terhadap {juara} (menang = {juara} lebih baik):')
    hasil['tabel6_uji'] = {}
    for m in g.index:
        if m == juara:
            continue
        d = piv[[juara, m]].dropna()
        r = uji(d[juara], d[m])
        hasil['tabel6_uji'][m] = r
        tanda = 'signifikan' if r['p'] < 0.05 else '-'
        print(f"    vs {m:15s} menang {r['menang']:4d}/{r['n']:4d}  "
              f"p={r['p']:.4g}  {tanda}")
    hasil['tabel6_juara'] = juara

    # median gabungan TANPA leaf uji-nol, untuk catatan ketahanan di naskah
    tanpa = roll[roll.leaf != 'A.1.b']
    g2 = tanpa.groupby('model')['mase'].agg(['mean', 'median']).sort_values('mean')
    hasil['tabel6_tanpa_A1b'] = {m: {k: float(v) for k, v in row.items()}
                                 for m, row in g2.iterrows()}
    print(f'\n  urutan tanpa A.1.b: {" < ".join(g2.index)}')

# ---------------------------------------------------------------- Tabel 7
bagian('TABEL 7  ablasi jumlah fitur, uji terhadap k = 25')
kab = baca('sisa_kablasi.csv')
if kab is not None:
    pk = kab.pivot_table(index=KUNCI, columns='top_k', values='mase')
    stat = kab.groupby('top_k')['mase'].agg(['mean', 'median', 'max'])
    hasil['tabel7'] = {}
    for k in sorted(pk.columns):
        d = pk[[k, 25]].dropna()
        r = uji(d[25], d[k]) if k != 25 else None      # menang = k=25 lebih baik
        s = stat.loc[k]
        rec = {'mean': float(s['mean']), 'median': float(s['median']),
               'max': float(s['max']),
               'delta_pct': 100 * (s['mean'] - stat.loc[25, 'mean']) / stat.loc[25, 'mean']}
        if r:
            rec.update(menang_25=r['menang'], n=r['n'], p=r['p'])
        hasil['tabel7'][int(k)] = rec
        print(f"  k={int(k):2d}  mean {rec['mean']:.4f}  median {rec['median']:.4f}  "
              f"max {rec['max']:8.4f}  delta {rec['delta_pct']:+6.2f}%  " +
              (f"menang(25) {r['menang']:4d}/{r['n']}  p={r['p']:.4g}" if r else 'acuan'))

# ------------------------------------------------------------ Tabel 8 / Gbr 6
bagian('TABEL 8 / GAMBAR 6  data pasar hidup-mati, per (beta, k)')
ext = baca('sisa_eksternal.csv')
if ext is not None:
    px = ext.pivot_table(index=KUNCI + ['beta', 'top_k'], columns='ext', values='mase')
    px = px.rename(columns={False: 'off', True: 'on'}).dropna().reset_index()
    hasil['tabel8'] = []
    for (b, k), d in px.groupby(['beta', 'top_k']):
        r = uji(d['off'], d['on'])                      # menang = mati lebih baik
        rec = {'beta': float(b), 'top_k': int(k),
               'mean_off': r['mean_a'], 'mean_on': r['mean_b'],
               'delta_pct': 100 * (r['mean_b'] - r['mean_a']) / r['mean_a'],
               'menang_off': r['menang'], 'n': r['n'], 'p': r['p'],
               'rank_favours': 'off' if r['menang'] * 2 > r['n'] else 'on'}
        hasil['tabel8'].append(rec)
        print(f"  beta={b:.1f} k={int(k):2d}  mati {rec['mean_off']:.4f}  "
              f"hidup {rec['mean_on']:.4f}  delta {rec['delta_pct']:+6.2f}%  "
              f"menang(mati) {rec['menang_off']:4d}/{rec['n']}  p={rec['p']:.4g}  "
              f"-> hitungan memihak {rec['rank_favours']}")

    # ------------------------------------------------------------ Gambar 10
    bagian('GAMBAR 10  mRMR lawan univariat, pada kondisi tanpa data pasar')
    mati = ext[~ext.ext.astype(bool)]
    ps = mati.pivot_table(index=KUNCI + ['top_k'], columns='beta', values='mase')
    ps = ps.dropna().reset_index()
    hasil['gambar10'] = []
    if 1.0 in ps.columns and 0.0 in ps.columns:
        for k, d in ps.groupby('top_k'):
            r = uji(d[1.0], d[0.0])                     # menang = mRMR lebih baik
            rec = {'top_k': int(k), 'mean_mrmr': r['mean_a'], 'mean_univ': r['mean_b'],
                   'delta_pct': 100 * (r['mean_a'] - r['mean_b']) / r['mean_b'],
                   'menang_mrmr': r['menang'], 'n': r['n'], 'p': r['p']}
            hasil['gambar10'].append(rec)
            print(f"  k={int(k):2d}  mRMR {rec['mean_mrmr']:.4f}  univ {rec['mean_univ']:.4f}  "
                  f"delta {rec['delta_pct']:+6.2f}%  menang {rec['menang_mrmr']:4d}/{rec['n']}  "
                  f"p={rec['p']:.4g}")

# ---------------------------------------------------------------- Tabel 9
bagian('TABEL 9  ablasi balik: tiap lengan terhadap konfigurasi optimal')
abl = baca('opt_ablasi.csv')
if abl is not None and roll is not None:
    opt = (roll[roll.model.isin(ML)][KUNCI + ['mase']]
           .rename(columns={'mase': 'opt'}))
    NAMA = {'tanpa_mrmr': 'Redundancy-aware selection',
            'tanpa_refit': 'Daily re-fitting',
            'tanpa_setelan': 'Tuned hyperparameters'}
    hasil['tabel9'] = []
    for arm, d0 in abl.groupby('arm'):
        d = (d0[KUNCI + ['mase']].rename(columns={'mase': 'off'})
             .merge(opt, on=KUNCI))
        r = uji(d['opt'], d['off'])                     # menang = optimal lebih baik
        per_model = {m: 100 * (z.off.mean() - z.opt.mean()) / z.opt.mean()
                     for m, z in d.groupby('model')}
        lebih_baik_tanpa = int(sum(z.off.mean() < z.opt.mean()
                                   for _, z in d.groupby('leaf')))
        rec = {'arm': arm, 'komponen': NAMA.get(arm, arm),
               'mean_opt': r['mean_a'], 'mean_off': r['mean_b'],
               'delta_pct': 100 * (r['mean_b'] - r['mean_a']) / r['mean_a'],
               'menang_opt': r['menang'], 'n': r['n'], 'p': r['p'],
               'per_model_pct': {k: float(v) for k, v in per_model.items()},
               'leaf_lebih_baik_tanpa': lebih_baik_tanpa,
               'n_leaf': int(d.leaf.nunique())}
        hasil['tabel9'].append(rec)
        print(f"  {rec['komponen']:28s} opt {rec['mean_opt']:.4f}  tanpa {rec['mean_off']:.4f}  "
              f"delta {rec['delta_pct']:+6.2f}%  menang(opt) {rec['menang_opt']:4d}/{rec['n']}  "
              f"p={rec['p']:.4g}")
        print(f"      per model: " + '  '.join(f'{m} {v:+.2f}%' for m, v in per_model.items()))
        print(f"      leaf yang lebih baik TANPA komponen ini: "
              f"{lebih_baik_tanpa}/{rec['n_leaf']}")

# ------------------------------------------------------------------ simpan
if hasil:
    with open(OUT, 'w') as f:
        json.dump(hasil, f, indent=1, default=float)
    print(f'\nditulis: {OUT}')
    print('Kirim berkas itu untuk dipasang ke naskah.')
else:
    print('\nTidak ada berkas hasil yang terbaca. Cek isi folder hasil/.')
    sys.exit(1)
