"""Hitung ulang SHAP pada konfigurasi BARU.

Gambar 7 dan 8 di draf masih berasal dari 10 September: kolam 4 lag, seleksi
Spearman murni, parameter bawaan. Ketiganya sudah tidak dipakai naskah, jadi
kedua gambar itu menjelaskan model yang tidak ada lagi di dalamnya.

Di sini: kolam 18 lag (dari feature_config), seleksi mRMR (beta=1), dan
setelan hyperparameter terpilih per leaf dari blok validasi.

Checkpoint per leaf ke shap_baru.json supaya restart tidak menghapus kemajuan.
"""
import json
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h1_common import *          # noqa: F403
warnings.filterwarnings('ignore')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import shap
from sklearn.ensemble import RandomForestRegressor

from utils.feature_engineering_optimized import (create_features_optimized,
                                                 select_top_features_optimized)

S = HASIL                      # ikut JBV_PANEL / JBV_HASIL, lihat h1_common
CKPT = S + 'shap_baru.json'
TUNE = S + 'opt_tuned.csv'
RF_CFG = {}                    # diisi muat_setelan() saat main() berjalan
NROLL, TOP_K, BETA = 30, 25, 1.0
BLUE, ACC, GRID = '#3b6ea5', '#c4713d', '#d8d8d8'

RF_GRID = [dict(n_estimators=100, max_depth=10), dict(n_estimators=300, max_depth=10),
           dict(n_estimators=300, max_depth=None), dict(n_estimators=100, max_depth=4)]


def muat_setelan():
    """Baca setelan RandomForest terpilih per leaf dari opt_tuned.csv.

    Dulu daftar ini di-hardcode di berkas ini. Itu diam-diam salah begitu
    panelnya berganti: nilai yang tertulis berasal dari penyetelan panel lain,
    dan leaf yang namanya kebetulan sama akan memakai setelan milik panel itu.
    Pada panel 15 leaf satu seri (A.2.f) memang tersetel berbeda, sehingga
    gambar SHAP-nya dibuat dari model yang bukan model yang dievaluasi.

    Sekarang dibaca dari berkas, jadi ia selalu cocok dengan blok uji.
    """
    if not os.path.exists(TUNE):
        print(f'PERINGATAN: {TUNE} tidak ada; memakai setelan pertama grid '
              f'untuk semua leaf. Gambar SHAP tidak akan mencerminkan blok uji.',
              flush=True)
        return {}
    t = pd.read_csv(TUNE)
    t = t[t['model'] == 'RandomForest']
    return {r.leaf: int(r.cfg) for r in t.itertuples()}

FAMILY = [
    ('ext_', 'External'), ('lag_', 'Lag'), ('rolling_mean', 'Moving average'),
    ('ewm', 'Moving average'), ('rolling_std', 'Volatility / range'),
    ('volatility', 'Volatility / range'), ('range', 'Volatility / range'),
    ('rsi', 'Technical'), ('bb_', 'Technical'), ('macd', 'Technical'),
    ('z_score', 'Extreme value'), ('is_extreme', 'Extreme value'),
    ('diff', 'Change / trend'), ('pct_change', 'Change / trend'),
    ('fourier', 'Calendar'), ('day_of', 'Calendar'), ('month', 'Calendar'),
    ('is_weekend', 'Calendar'), ('quarter', 'Calendar'),
]


def family(fn):
    for pre, fam in FAMILY:
        if fn.startswith(pre) or pre in fn:
            return fam
    return 'Other'


def pretty(fn):
    if '_x_' in fn:
        a, b = fn.split('_x_', 1)
        return f'{pretty(a)} x {b.replace("_", " ")}'
    if fn.startswith('ext_'):
        p = fn[4:].split('_lag_')
        nm = p[0].replace('_', ' ')
        return f'{nm}, lag {p[1]}' if len(p) > 1 else f'{nm}, 7d mean'
    if fn.startswith('lag_'):
        return f'Own lag {fn[4:]}'
    if fn.startswith('rolling_mean_'):
        return f'Own mean, {fn.split("_")[-1]}d'
    if fn.startswith('ewm_'):
        return f'Own EWM, span {fn.split("_")[-1]}'
    return fn.replace('_', ' ')


def feats(r, dcols, dall, esd, edt):
    d, y = series_of(r, dcols, dall)
    cut = len(y) - NROLL
    s = pd.DataFrame({'ds': d[:cut], 'y': y[:cut]})
    f = create_features_optimized(s, external_series=esd, external_series_dates=edt)
    top, _ = select_top_features_optimized(f, top_k=TOP_K, mrmr_beta=BETA)
    X = f[top].fillna(0).replace([np.inf, -np.inf], 0)
    return top, X, f['value'].values


def beeswarm(top, Xs, sv, judul, keluar, n_fitur=14):
    """Gambar beeswarm satu leaf dari nilai SHAP yang sudah dihitung.

    Dipisah jadi fungsi supaya bisa dipanggil untuk SETIAP leaf tanpa
    menghitung ulang SHAP-nya - nilai sv yang sama yang dipakai menyusun
    pangsa per keluarga dipakai lagi di sini.
    """
    order = np.argsort(-np.abs(sv).mean(0))[:n_fitur]
    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    for row, i in enumerate(order):
        v = sv[:, i]
        xv = Xs.iloc[:, i].values.astype(float)
        rk = (np.argsort(np.argsort(xv)) / max(1, len(xv) - 1))
        jit = (np.random.RandomState(row).rand(len(v)) - .5) * .34
        ax.scatter(v, len(order) - row + jit, c=rk, cmap='coolwarm', s=5,
                   alpha=.7, linewidths=0)
    ax.set_yticks([len(order) - k for k in range(len(order))])
    ax.set_yticklabels([pretty(top[i]) for i in order], fontsize=7.4)
    for k, i in enumerate(order):
        if top[i].startswith('ext_'):
            ax.get_yticklabels()[k].set_color(ACC)
    ax.axvline(0, color='#888', lw=.7)
    ax.set_xlabel('SHAP value (effect on the forecast, millions of USD)')
    if judul:
        ax.set_title(judul, fontsize=9, loc='left', pad=6)
    ax.grid(axis='x', color=GRID, lw=.6); ax.set_axisbelow(True)
    os.makedirs(os.path.dirname(keluar), exist_ok=True)
    fig.tight_layout(); fig.savefig(keluar, dpi=200); plt.close(fig)


def main():
    global RF_CFG
    # shap_ringkas.json ditulis utuh di akhir, bukan ditambah per sel, jadi
    # menjalankannya per shard hanya menyisakan potongan shard terakhir.
    tolak_shard('shap_baru.py')
    RF_CFG = muat_setelan()
    panel, dcols, dall = load_panel()
    lv = leaves(panel)
    esd, edt = load_external()
    st = json.load(open(CKPT)) if os.path.exists(CKPT) else {'leaf': {}}

    for _, r in lv.iterrows():
        rid = r['Row_ID']
        if rid in st['leaf']:
            continue
        top, X, yv = feats(r, dcols, dall, esd, edt)
        cfg = RF_GRID[RF_CFG.get(rid, 0)]
        m = RandomForestRegressor(random_state=0, n_jobs=-1, **cfg).fit(X, yv)
        sv = shap.TreeExplainer(m).shap_values(X.iloc[-300:], check_additivity=False)
        imp = np.abs(sv).mean(0)
        tot = imp.sum() + 1e-12
        fam = {}
        for i, fn in enumerate(top):
            fam[family(fn)] = fam.get(family(fn), 0.0) + float(imp[i] / tot)
        st['leaf'][rid] = {
            'family': fam,
            'ext_share': float(100 * sum(imp[i] for i, fn in enumerate(top)
                                         if fn.startswith('ext_')) / tot),
            'n_ext': int(sum(1 for fn in top if fn.startswith('ext_'))),
            'n_lag': int(sum(1 for fn in top if fn.startswith('lag_'))),
            'top': [{'name': pretty(top[i]), 'ext': bool(top[i].startswith('ext_'))}
                    for i in np.argsort(-imp)[:14]],
        }
        # Beeswarm per leaf. Memakai sv yang baru saja dihitung, jadi
        # ongkosnya hanya menggambar - bukan menghitung SHAP dua kali.
        beeswarm(top, X.iloc[-300:], sv, f'{rid}',
                 S + f'fig/beeswarm/{rid}.png')
        json.dump(st, open(CKPT, 'w'))
        print(f'  shap {rid}  ext={st["leaf"][rid]["n_ext"]}  '
              f'lag={st["leaf"][rid]["n_lag"]}  -> fig/beeswarm/{rid}.png', flush=True)

    # ---- agregasi ----
    L = st['leaf']
    fam_tot = {}
    for v in L.values():
        for k, x in v['family'].items():
            fam_tot[k] = fam_tot.get(k, 0) + x
    fam = {k: 100 * v / len(L) for k, v in
           sorted(fam_tot.items(), key=lambda kv: -kv[1])}
    shares = sorted([{'leaf': k, 'share': v['ext_share']} for k, v in L.items()],
                    key=lambda r: -r['share'])

    # Gambar 8: pangsa per keluarga + per seri
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 2.8),
                             gridspec_kw={'width_ratios': [1.1, 1]})
    ax = axes[0]
    ks = list(fam)
    ax.barh(range(len(ks))[::-1], [fam[k] for k in ks],
            color=[ACC if k == 'External' else BLUE for k in ks], zorder=3)
    ax.set_yticks(range(len(ks))[::-1]); ax.set_yticklabels(ks, fontsize=7.6)
    ax.set_xlabel('share of total feature importance (%)')
    ax.grid(axis='x', color=GRID, lw=.6); ax.set_axisbelow(True)
    ax.set_title('Where the model gets its signal', fontsize=8.4, loc='left', pad=6)
    ax = axes[1]
    ax.barh(range(len(shares))[::-1], [r['share'] for r in shares], color=ACC, zorder=3)
    ax.set_yticks(range(len(shares))[::-1])
    ax.set_yticklabels([r['leaf'] for r in shares], fontsize=6.6)
    ax.set_xlabel('external share of importance (%)')
    ax.grid(axis='x', color=GRID, lw=.6); ax.set_axisbelow(True)
    ax.set_title('By series', fontsize=8.4, loc='left', pad=6)
    # Folder gambar dibuat di sini, bukan diasumsikan ada. Di hasil/ ia
    # kebetulan sudah ada dari jalan sebelumnya; di folder hasil yang baru
    # tidak, dan savefig akan gagal SESUDAH seluruh SHAP dihitung.
    os.makedirs(S + 'fig', exist_ok=True)
    fig.tight_layout(); fig.savefig(S + 'fig/fig7_shapfamily.png', dpi=200)
    plt.close(fig)

    # Gambar 7: beeswarm satu leaf yang memang memilih fitur eksternal
    target = max(L, key=lambda k: L[k]['n_ext'])
    r = lv[lv['Row_ID'] == target].iloc[0]
    top, X, yv = feats(r, dcols, dall, esd, edt)
    m = RandomForestRegressor(random_state=0, n_jobs=-1,
                              **RF_GRID[RF_CFG.get(target, 0)]).fit(X, yv)
    Xs = X.iloc[-700:]
    sv = shap.TreeExplainer(m).shap_values(Xs, check_additivity=False)
    beeswarm(top, Xs, sv, '', S + 'fig/fig6_beeswarm.png')

    out = {'shap_family': fam, 'shap_ext_share': shares,
           'beeswarm_leaf': target, 'beeswarm_n_ext': L[target]['n_ext'],
           'beeswarm_top': L[target]['top'],
           # Rincian per leaf: pangsa tiap keluarga fitur, jumlah slot, dan
           # 14 fitur terpenting. Inilah isi tabel SHAP per seri di naskah.
           'per_leaf': {k: {'family': {f: 100 * x for f, x in v['family'].items()},
                            'ext_share': v['ext_share'], 'n_ext': v['n_ext'],
                            'n_lag': v['n_lag'], 'top': v['top']}
                        for k, v in L.items()},
           'mean_lag_slots': float(np.mean([v['n_lag'] for v in L.values()])),
           'mean_ext_slots': float(np.mean([v['n_ext'] for v in L.values()]))}
    json.dump(out, open(S + 'shap_ringkas.json', 'w'), indent=1)
    print('\nkeluarga:', {k: round(v, 1) for k, v in fam.items()})
    print('rata slot lag:', round(out['mean_lag_slots'], 2),
          '| rata slot eksternal:', round(out['mean_ext_slots'], 2))
    print('beeswarm leaf utama:', target)
    print(f'beeswarm per leaf : {len(L)} berkas di {S}fig/beeswarm/')


if __name__ == '__main__':
    main()
