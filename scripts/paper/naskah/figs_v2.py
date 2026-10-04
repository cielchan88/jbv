"""Gambar badan naskah untuk desain v2, dari keluaran/tables_v2.json.

    python scripts/paper/naskah/figs_v2.py

Gambar desain lama (30 origin) tetap dibuat figs.py untuk lampiran. Nama
berkas di sini berakhiran _v2. Penjaga kode leaf lama sama dengan figs.py.
"""
import json
import os
import re
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt              # noqa: E402
import matplotlib.text                       # noqa: E402
import numpy as np                           # noqa: E402
import pandas as pd                          # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

NASKAH = os.path.dirname(os.path.abspath(__file__))
KEL = os.path.join(NASKAH, 'keluaran')
F = os.path.join(KEL, 'gambar') + os.sep
T2 = json.load(open(os.path.join(KEL, 'tables_v2.json')))
T = json.load(open(os.path.join(KEL, 'tables.json')))       # deskriptif dan label
BLUE, ACC, GRID, MUTED, GREEN, INK = '#3b6ea5', '#c4713d', '#d8d8d8', '#5e6b76', '#4f7d5a', '#1B2530'
NICE = {'Naive': 'Random walk', 'NaiveMean': 'Rolling mean', 'NaiveDrift': 'RW w/ drift',
        'SeasonalNaive': 'Seasonal naive', 'Croston': 'Croston', 'SeasonalDecomp': 'Seasonal decomp',
        'ARIMA': 'ARIMA', 'ETS': 'ETS', 'Theta': 'Theta', 'Prophet': 'Prophet', 'Ridge': 'Ridge',
        'RandomForest': 'Random forest', 'LightGBM': 'LightGBM', 'XGBoost': 'XGBoost'}
nice = lambda m: NICE.get(m, m)
PUR = {'Ekspor': 'Export', 'Impor': 'Import', 'Investasi': 'Investment', 'Repatriasi': 'Repatriation',
       'Transaksi tanpa underlying': 'No underlying', 'Remittance': 'Remittance', 'Trading': 'Trading',
       'Lainnya': 'Other'}
LAB = {d['leaf']: PUR.get(str(d['label']).split('. ', 1)[-1], str(d['label']).split('. ', 1)[-1]) for d in T['desc']}
NAMA_LEAF = json.load(open(os.path.join(os.path.dirname(NASKAH), 'nama_leaf.json')))['peta']
nama = lambda l: NAMA_LEAF.get(l, l)
KODE_LAMA = re.compile(r'(?<![\w.])(?:' + '|'.join(re.escape(k) for k in NAMA_LEAF) + r')(?!\w|\.\w)')
LEARNER = ['RandomForest', 'LightGBM', 'XGBoost']


def simpan(fig, nm, tata=True):
    for t in fig.findobj(matplotlib.text.Text):
        if KODE_LAMA.search(t.get_text()):
            raise SystemExit(f'BERHENTI: {nm} memuat kode leaf lama: {t.get_text()!r}')
    if tata:
        fig.tight_layout()
    fig.savefig(F + nm, dpi=200)
    plt.close(fig)
    print('  ', nm)


urut_m = [r['model'] for r in T2['peringkat']]
urut_l = sorted(T2['per_leaf_model'])
NR, NV = T2['nroll'], T2['nval']

# ------------------------------------------------------------ desain
fig, ax = plt.subplots(figsize=(7.4, 1.5))
ax.add_patch(plt.Rectangle((0, .25), 7.2, .4, fc='#E8EFF4', ec=BLUE, lw=.8))
ax.text(3.6, .45, 'training sample, from each series’ first report (also fixes the MASE scale)',
        ha='center', va='center', fontsize=7.4, color=INK)
ax.add_patch(plt.Rectangle((7.2, .25), 1.1, .4, fc='#EEF3E8', ec=GREEN, lw=.8))
ax.text(7.75, .45, f'validation\n{NV} origins', ha='center', va='center', fontsize=7, color=INK)
ax.add_patch(plt.Rectangle((8.3, .25), 2.9, .4, fc='#F6E9E7', ec=ACC, lw=.8))
ax.text(9.75, .45, f'test, {NR} one-day origins\n{T2["tgl_uji_awal"]} to {T2["tgl_uji_akhir"]}',
        ha='center', va='center', fontsize=7, color=INK)
ax.text(0, .9, 'Each origin: re-fit on the actual history up to the day before, forecast one day ahead',
        fontsize=7.8, color=INK, weight='bold')
ax.text(0, .08, 'time  →', fontsize=6.6, color=MUTED)
ax.set_xlim(-.1, 11.3); ax.set_ylim(0, 1.05); ax.axis('off')
simpan(fig, 'fig2_design_v2.png')

# ------------------------------------------------------------ alur evaluasi
fig, ax = plt.subplots(figsize=(7.4, 4.6))
ax.set_xlim(0, 10); ax.set_ylim(0, 7.8); ax.axis('off')


def kotak(x, y, w, h, judul, isi, fc='#F3F6F9', ec=BLUE, fs=6.9, jfs=7.6):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.12', fc=fc, ec=ec, lw=.9))
    ax.text(x + .12, y + h - .12, judul, ha='left', va='top', fontsize=jfs, weight='bold', color=INK)
    ax.text(x + .12, y + h - .14 - .30 * (judul.count('\n') + 1), isi, ha='left', va='top',
            fontsize=fs, color=INK, linespacing=1.35)


def panah(x1, y1, x2, y2):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='-|>', color=MUTED, lw=1.0, shrinkA=0, shrinkB=0))


kotak(0.1, 6.75, 9.8, 0.95, '1  Data',
      f'{T2["n_leaf"]} daily flow series, each from its first report. Market data (six variables as daily '
      'changes, eight as levels)\nenter only the market-data arms.')
panah(5, 6.75, 5, 6.3)
kotak(0.1, 4.5, 4.85, 1.8, '2  Validation block',
      f'{NV} origins before the test block, re-fit daily.\n'
      'Learners: 4 configurations each, keep the best.\n'
      'All 14 methods: forecasts kept for choosing a\nmethod or a set of methods per series.',
      fc='#F4F8F1', ec=GREEN)
kotak(5.05, 4.5, 4.85, 1.8, '3  Test block',
      f'{NR} origins. At each origin re-fit on the history\nup to the day before and forecast one day ahead.\n'
      'Random forest with three seeds, averaged.\nScaled error with the training-sample scale.',
      fc='#FBF1EE', ec=ACC)
panah(2.5, 4.5, 2.5, 4.05)
panah(7.5, 4.5, 7.5, 4.05)
E = [('Methods', '14 methods,\neach against\nthe leader'),
     ('Components', 'daily arms: no mRMR,\nno daily re-fit,\nno tuning'),
     ('Features', 'weekly arms: k = 12,\n40 and all 116\nagainst k = 25'),
     ('Market data', 'weekly arms: changes,\nlevels, training\nfrom 2022 only')]
for i, (j, t) in enumerate(E):
    x = 0.1 + i * 2.475
    kotak(x, 2.55, 2.3, 1.5, '4  ' + j, t, fc='#F7F7F7', ec=MUTED, fs=6.6, jfs=7.2)
    panah(x + 1.15, 2.55, x + 1.15, 2.15)
kotak(0.1, 0.05, 9.8, 2.1, '5  Inference',
      f'Units averaged to one value per series and date ({T2["n_leaf"]} x {NR} = {T2["n_leaf"] * NR:,} per comparison).\n'
      'Wilcoxon signed-rank test with Holm correction within each family of comparisons.\n'
      'Circular block bootstrap over dates (blocks of five days) for confidence intervals.\n'
      'Equivalence within ±2 per cent (90 per cent interval), Hodges-Lehmann shifts.\n'
      'Diebold-Mariano tests per series and a 90 per cent Model Confidence Set.\n'
      'Results by quarter, operational metrics in US dollars, SHAP on the final models.')
fig.subplots_adjust(left=.005, right=.995, top=.995, bottom=.005)
simpan(fig, 'fig3_evaluasi_v2.png', tata=False)

# ------------------------------------------------------------ heatmap
PLM = T2['per_leaf_model']
M_ = np.array([[PLM[l][m] / PLM[l]['Naive'] for m in urut_m] for l in urut_l])
fig, ax = plt.subplots(figsize=(7.4, 4.8))
L2 = np.clip(np.log2(M_), -1.5, 1.5)
im = ax.imshow(L2, cmap='RdBu_r', vmin=-1.5, vmax=1.5, aspect='auto')
for i in range(M_.shape[0]):
    jb = int(np.argmin(M_[i]))
    for j in range(M_.shape[1]):
        ax.text(j, i, f'{M_[i, j]:.2f}', ha='center', va='center', fontsize=5.6,
                weight='bold' if j == jb else 'normal', color='white' if abs(L2[i, j]) > 1.0 else INK)
    ax.add_patch(plt.Rectangle((jb - .5, i - .5), 1, 1, fill=False, ec=INK, lw=1.2))
ax.set_xticks(range(len(urut_m))); ax.set_xticklabels([nice(m) for m in urut_m], fontsize=6.6, rotation=35, ha='right')
ax.set_yticks(range(len(urut_l))); ax.set_yticklabels([f'{nama(l)}  {LAB[l]}' for l in urut_l], fontsize=6.8)
cb = fig.colorbar(im, ax=ax, fraction=.03, pad=.02, ticks=np.log2([.4, .5, .7, 1, 1.4, 2, 2.8]))
cb.ax.set_yticklabels(['0.4', '0.5', '0.7', '1', '1.4', '2', '2.8+'], fontsize=6.5)
cb.set_label('MASE relative to random walk (log scale)', fontsize=7)
simpan(fig, 'fig_heatmap_v2.png')

# ------------------------------------------------------------ per kuartal
PK = T2['per_kuartal']
qs = sorted(PK)
tampil = urut_m[:6] + ['Naive']
fig, ax = plt.subplots(figsize=(7.4, 2.8))
gaya = {m: dict(color=c, lw=1.6 if m in LEARNER or m == 'Ridge' else 1.1,
                ls='-' if m in LEARNER or m == 'Ridge' else '--')
        for m, c in zip(tampil, ['#1B2530', BLUE, ACC, GREEN, '#8a5ea8', '#b8a04a', MUTED])}
for m in tampil:
    ax.plot(range(len(qs)), [PK[q][m] for q in qs], marker='o', ms=3, label=nice(m), **gaya[m])
ax.set_xticks(range(len(qs)))
ax.set_xticklabels([f'{q}\n({T2["kuartal_n"][q]} days)' for q in qs], fontsize=7)
ax.set_ylabel('mean MASE', fontsize=8)
ax.legend(fontsize=6.6, frameon=False, ncol=4, loc='upper left')
ax.grid(axis='y', color=GRID, lw=.6); ax.set_axisbelow(True)
simpan(fig, 'fig_kuartal_v2.png')

# ------------------------------------------------------------ komponen per learner
KP = T2['komponen_per_model']
komp = list(KP)
fig, ax = plt.subplots(figsize=(7.4, 2.7))
x = np.arange(len(komp)); w = .25
for i, (m, c) in enumerate(zip(LEARNER, [BLUE, ACC, MUTED])):
    v = [KP[k][m]['delta'] for k in komp]
    lo = [KP[k][m]['delta'] - KP[k][m]['lo95'] for k in komp]
    hi = [KP[k][m]['hi95'] - KP[k][m]['delta'] for k in komp]
    ax.bar(x + (i - 1) * w, v, w, color=c, zorder=3, label=nice(m), yerr=[lo, hi],
           error_kw=dict(lw=.7, capsize=2, ecolor=INK))
pool = {r['label']: r['delta'] for r in T2['komponen']}
for i, k in enumerate(komp):
    ax.hlines(pool[k], i - .42, i + .42, colors=INK, linestyles='--', lw=.9, zorder=4)
ax.axhspan(-2, 2, color='#eeeeee', zorder=0)
ax.axhline(0, color=INK, lw=.8)
ax.set_xticks(x); ax.set_xticklabels([f'without {k.lower()}' for k in komp], fontsize=7.6)
ax.set_ylabel('% change in mean MASE', fontsize=8)
ax.legend(fontsize=7, frameon=False, loc='upper right')
ax.grid(axis='y', color=GRID, lw=.6); ax.set_axisbelow(True)
simpan(fig, 'fig_komponen_v2.png')

# ------------------------------------------------------------ SHAP keluarga
if 'shap' in T2:
    SF = T2['shap']['famili']
    a, b = SF['ubah|RandomForest'], SF['ubah|LightGBM']
    nm = [k for k in a if max(a[k], b.get(k, 0)) >= 0.05]
    fig, ax = plt.subplots(figsize=(7.4, 2.9))
    yy = np.arange(len(nm))[::-1]; h = .38
    for j, (src, wr, lab) in enumerate(((a, BLUE, 'Random forest'), (b, ACC, 'LightGBM'))):
        vv = [src.get(k, 0.0) for k in nm]
        ax.barh(yy + (h / 2 if j == 0 else -h / 2), vv, h, color=wr, zorder=3, label=lab)
        for y_, v in zip(yy, vv):
            ax.text(v + .5, y_ + (h / 2 if j == 0 else -h / 2), f'{v:.1f}', va='center', fontsize=6.4, color=MUTED)
    ax.set_yticks(yy); ax.set_yticklabels(nm, fontsize=7.4)
    ax.set_xlabel('share of total |SHAP|, mean across the 15 series (%)', fontsize=8)
    ax.set_xlim(0, max(max(a.values()), max(b.values())) * 1.15)
    ax.legend(fontsize=7, frameon=False, loc='lower right')
    ax.grid(axis='x', color=GRID, lw=.6); ax.set_axisbelow(True)
    simpan(fig, 'fig_shap_v2.png')

    # pasar per seri: slot terpilih dan efek lengan perubahan
    ne, ef = T2['shap']['n_ext'], T2['pasar_ubah_per_seri']
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.0), sharey=True)
    yy = np.arange(len(urut_l))[::-1]
    axes[0].barh(yy, [ne[l] for l in urut_l], color=ACC, zorder=3)
    axes[0].set_xlabel('market features kept at k = 25', fontsize=7.6)
    axes[0].set_yticks(yy); axes[0].set_yticklabels([f'{nama(l)}  {LAB[l]}' for l in urut_l], fontsize=6.8)
    axes[1].barh(yy, [ef[l] for l in urut_l], color=[ACC if ef[l] > 0 else BLUE for l in urut_l], zorder=3)
    axes[1].axvline(0, color=INK, lw=.8)
    axes[1].set_xlabel('% change in MASE with market changes', fontsize=7.6)
    for a_ in axes:
        a_.grid(axis='x', color=GRID, lw=.6); a_.set_axisbelow(True)
    simpan(fig, 'fig_pasar_v2.png')

# ------------------------------------------------------------ deret dengan blok uji v2
_pn = pd.read_csv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(NASKAH))),
                               'data', 'processed', 'sdv-wide-gabung.csv'))
_tg = [c for c in _pn.columns if c[:2] == '20']
_tt = pd.to_datetime(_tg)
fig, axes = plt.subplots(5, 3, figsize=(7.4, 6.6), sharex=True)
for ax, l in zip(axes.T.ravel(), urut_l):
    v = pd.to_numeric(_pn.loc[_pn.Row_ID == l, _tg].iloc[0], errors='coerce').values.astype(float)
    ax.plot(_tt, v, lw=.35, color=BLUE)
    ax.axvspan(_tt[-NR - NV], _tt[-NR], color=GREEN, alpha=.25, lw=0)
    ax.axvspan(_tt[-NR], _tt[-1], color=ACC, alpha=.3, lw=0)
    s0 = T2['seri'][l]['s0']
    if s0:
        ax.axvline(_tt[s0], color=MUTED, lw=.6, ls=':')
    ax.set_title(f'{nama(l)}  {LAB[l]}', fontsize=7, loc='left', pad=2)
    ax.tick_params(axis='both', labelsize=5.5)
    ax.yaxis.set_major_locator(plt.MaxNLocator(3))
    for sp in ('top', 'right'):
        ax.spines[sp].set_visible(False)
simpan(fig, 'fig_seri_v2.png')

# ------------------------------------------------------------ beeswarm v2 disalin oleh shap_v2.py
print('selesai ->', F)
