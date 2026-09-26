"""Susun tables.json - seluruh angka naskah, dihitung dari berkas hasil mentah.

Setiap angka di naskah berasal dari sini, dan sini membacanya dari CSV/JSON
hasil komputasi - tidak ada yang disalin dengan tangan. Itulah yang membuat
cek_draft.py bisa membandingkan naskah terhadap sumbernya.

    python scripts/paper/naskah/buat_tables.py

Jalan berkas diatur jalan.py; lihat docstring-nya untuk env yang tersedia.
"""
import json, os, sys, warnings
import pandas as pd, numpy as np
from scipy.stats import spearmanr, skew, kurtosis, wilcoxon

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jalan import HASIL, SLOT, LAMA, TABLES, siapkan, periksa_hasil, REPO

sys.path.insert(0, os.path.join(REPO, 'scripts', 'paper', 'revisi'))
os.environ.setdefault('JBV_PANEL', 'data/processed/sdv-wide-gabung.csv')
os.environ.setdefault('JBV_HASIL', 'hasil_sdv-wide-gabung')
os.environ['JBV_DIAM'] = '1'
from h1_common import *                      # ber-chdir ke akar repo
warnings.filterwarnings('ignore')

siapkan()
periksa_hasil('opt_rolling.csv', 'headline.csv', 'sisa_kablasi.csv',
              'sisa_eksternal.csv', 'sisa_pasar_benar.csv', 'opt_tuned.csv',
              'shap_ringkas.json', 'uji_statistik.json')

H = HASIL
BACA = lambda n, d=None: pd.read_csv((d or H) + n, float_precision='round_trip')

S = json.load(open(H + 'shap_ringkas.json'))
U = json.load(open(H + 'uji_statistik.json'))
# versi.json ditulis h1_common sejak commit 74e2dad; hasil lama belum punya.
V = (json.load(open(H + 'versi.json')) if os.path.exists(H + 'versi.json')
     else {k: None for k in ('python', 'numpy', 'pandas', 'scipy', 'sklearn',
                             'lightgbm', 'xgboost', 'statsmodels')})
if not os.path.exists(SLOT + 'slot_pasar.json'):
    raise SystemExit(f'BERHENTI: {SLOT}slot_pasar.json tidak ada. Jalankan dulu:\n'
                     f'  JBV_HASIL=hasil_slot python scripts/paper/revisi/cek_slot_pasar.py')
slot = json.load(open(SLOT + 'slot_pasar.json'))

roll, head = BACA('opt_rolling.csv'), BACA('headline.csv')
kab, ext = BACA('sisa_kablasi.csv'), BACA('sisa_eksternal.csv')
pben = BACA('sisa_pasar_benar.csv')
T = {}

# ------------------------------------------------------------------ deskriptif
panel, dcols, dall = load_panel(); lv = leaves(panel)
lab = dict(zip(panel.Row_ID, panel.Row_Label))
T['desc'] = []
for _, r in lv.iterrows():
    d, y = series_of(r, dcols, dall)
    T['desc'].append(dict(leaf=r['Row_ID'], label=str(lab[r['Row_ID']]),
        mean=float(y.mean()), sd=float(y.std()), med=float(np.median(y)),
        zero=float(100*(y == 0).mean()), skew=float(skew(y)),
        kurt=float(kurtosis(y)), acf1=float(pd.Series(y).autocorr(1))))
T['n_leaf'] = len(lv)
T['n_hari'] = len(dcols)
T['tgl_awal'], T['tgl_akhir'] = dcols[0], dcols[-1]

# ------------------------------------------------------------- Tabel 5 dan 6
T['e1'] = [dict(leaf=r.leaf, model=r.model, actual=float(r.actual),
                pred=float(r.pred), mase=float(r.mase)) for r in head.itertuples()]
g1 = head.groupby('model')['mase'].agg(['mean', 'median', 'count'])
T['e1_summary'] = [dict(model=m, mase=float(v['mean']), med=float(v['median']),
                        n=int(v['count'])) for m, v in g1.iterrows()]
T['e2_summary'] = [dict(model=m, mase=v['mean'], med=v['median'], max=v['max'],
                        n=int(v['count'])) for m, v in U['tabel6'].items()]
e1r = g1['mean'].sort_values()
e2r = pd.Series({m: v['mean'] for m, v in U['tabel6'].items()}).sort_values()
rho, p = spearmanr(e1r.rank(), e2r.reindex(e1r.index).rank())
T['rank_corr'] = {'rho': float(rho), 'p': float(p)}
T['champion_tests'] = [dict(model=m, wins=v['menang'], n=v['n'], p=v['p'],
                            p_holm=v.get('p_holm'), p_bh=v.get('p_bh'),
                            sig=v['p'] < 0.05,
                            sig_holm=(v.get('p_holm') is not None
                                      and v['p_holm'] < 0.05))
                       for m, v in U['tabel6_uji'].items()]
T['champion_koreksi'] = U.get('tabel6_koreksi')
T['champion_juara'] = U['tabel6_juara']

# ---------------------------------------------------------- pemenang per seri
g = roll.groupby(['leaf', 'model'])['mase'].mean().reset_index()
best = g.loc[g.groupby('leaf')['mase'].idxmin()]
T['best_per_leaf'] = dict(zip(best.leaf, best.model))
desc = {d['leaf']: d for d in T['desc']}
fam = lambda m: 'ML' if m in ('RandomForest', 'LightGBM', 'XGBoost') else 'lain'
T['winners'] = [dict(leaf=r.leaf, best=r.model, mase=float(r.mase),
                     zero=desc[r.leaf]['zero'], fam=fam(r.model))
                for r in best.itertuples()]
rw = g[g.model == 'Naive'].set_index('leaf')['mase']
T['n_beat_rw'] = int((best.set_index('leaf').mase < rw - 1e-12).sum())
rr, pp = spearmanr([w['zero'] for w in T['winners']], [w['mase'] for w in T['winners']])
T['winner_rho'], T['winner_p'] = float(rr), float(pp)
cro = [w for w in T['winners'] if w['best'] == 'Croston']
T['croston_leaves'] = [dict(leaf=w['leaf'], zero=w['zero']) for w in cro]
sp_ = max(T['winners'], key=lambda w: w['zero'])
T['sparsest'] = dict(leaf=sp_['leaf'], zero=sp_['zero'], best=sp_['best'])
T['n_metode_menang'] = int(best.model.nunique())
T['menang_terbanyak'] = int(best.model.value_counts().iloc[0])

# ---------------------------------------------------------------- Tabel 7
T['ablation'] = [dict(k=int(k), mase=v['mean'], median=v['median'], max=v['max'],
                      delta=v['delta_pct'], wins=v.get('menang_25', 0),
                      n=v.get('n', 1350), p=v.get('p'))
                 for k, v in sorted(U['tabel7'].items(), key=lambda kv: int(kv[0]))]
T['ablation_best'] = int(min(U['tabel7'].items(), key=lambda kv: kv[1]['mean'])[0])

# ------------------------------------------------- Tabel 8 (sadar hari seri)
T['external_full'] = [dict(beta=r['beta'], k=r['top_k'], off=r['mean_off'],
    on=r['mean_on'], delta=r['delta_pct'], wins_off=r['menang_off'],
    losses_off=r['kalah_off'], ties=r['seri'], pct_off=r['persen_menang_off'],
    n=r['n'], p=r['p'], rank_favours=r['rank_favours']) for r in U['tabel8']]
T['external'] = [dict(k=r['k'], delta=r['delta'], p=r['p'], wins_off=r['wins_off'],
                      pct_off=r['pct_off'], rank_favours=r['rank_favours'])
                 for r in T['external_full'] if r['beta'] == 1.0]
T['selector_tests'] = [dict(k=r['top_k'], wins=r['menang_mrmr'], n=r['n'],
                            p=r['p'], delta=r['delta_pct']) for r in U['gambar10']]

# ------------------------------------------- Tabel 8b: pasar saat meramal
K = ['leaf', 'model', 'origin', 'beta', 'top_k']
mati = ext[~ext.ext.astype(bool)][K + ['mase']].rename(columns={'mase': 'mati'})
nol = ext[ext.ext.astype(bool)][K + ['mase']].rename(columns={'mase': 'nol'})
ben = pben[K + ['mase']].rename(columns={'mase': 'benar'})
gg = mati.merge(nol, on=K).merge(ben, on=K).dropna()
assert len(gg) == 5400, f'harus 5400 pasangan, dapat {len(gg)}'


def menang_kalah(a, b):
    """a lebih baik = menang. Hari seri dikeluarkan dari penyebut."""
    seri = np.isclose(a, b, rtol=1e-12, atol=0)
    w = int((a < b)[~seri].sum()); l = int((a > b)[~seri].sum())
    return w, l, int(seri.sum()), (100.0 * w / (w + l) if w + l else float('nan'))


T['tabel8b'] = []
for (b, k), d in gg.groupby(['beta', 'top_k']):
    m, n_, bn = d.mati.mean(), d.nol.mean(), d.benar.mean()
    w, l, s_, pct = menang_kalah(d.benar.values, d.mati.values)
    T['tabel8b'].append(dict(
        beta=float(b), k=int(k), mati=float(m), benar=float(bn), nol=float(n_),
        delta_benar=100*(bn/m - 1), delta_nol=100*(n_/m - 1),
        rusak_hilang_pct=100*(1 - (bn - m)/(n_ - m)),
        p_vs_mati=float(wilcoxon(d.benar, d.mati).pvalue),
        p_vs_nol=float(wilcoxon(d.benar, d.nol).pvalue),
        menang_benar=w, kalah_benar=l, seri=s_, pct_benar=pct, n=int(len(d))))
m, n_, bn = gg.mati.mean(), gg.nol.mean(), gg.benar.mean()
w, l, s_, pct = menang_kalah(gg.benar.values, gg.mati.values)
T['tabel8b_gabungan'] = dict(
    mati=float(m), nol=float(n_), benar=float(bn),
    delta_nol=100*(n_/m - 1), delta_benar=100*(bn/m - 1),
    rusak_hilang_pct=100*(1 - (bn - m)/(n_ - m)),
    p_vs_mati=float(wilcoxon(gg.benar, gg.mati).pvalue),
    p_vs_nol=float(wilcoxon(gg.benar, gg.nol).pvalue),
    menang_benar=w, kalah_benar=l, seri=s_, pct_benar=pct, n=int(len(gg)))

# ------------------------- slot pasar lawan kerusakan, sebelum dan sesudah
sl25 = {lf: slot[lf]['k25_mrmr'] for lf in slot}
s25 = gg[(gg.beta == 1.0) & (gg.top_k == 25)]
per = s25.groupby('leaf').agg(mati=('mati', 'mean'), nol=('nol', 'mean'),
                              benar=('benar', 'mean'))
per['rusak_nol'] = 100*(per.nol/per.mati - 1)
per['rusak_benar'] = 100*(per.benar/per.mati - 1)
per['slot'] = pd.Series(sl25)
r1, p1_ = spearmanr(per.slot, per.rusak_nol)
r2, p2_ = spearmanr(per.slot, per.rusak_benar)
T['slot_damage'] = {'nol': {'rho': float(r1), 'p': float(p1_)},
                    'benar': {'rho': float(r2), 'p': float(p2_)}, 'n': int(len(per))}
T['per_leaf_benar'] = [dict(leaf=i, slot=int(r.slot), mati=float(r.mati),
    nol=float(r.nol), benar=float(r.benar), rusak_nol=float(r.rusak_nol),
    rusak_benar=float(r.rusak_benar)) for i, r in per.sort_values('rusak_benar').iterrows()]
T['n_leaf_membaik'] = int((per.rusak_benar < -0.5).sum())
T['n_leaf_memburuk'] = int((per.rusak_benar > 0.5).sum())
T['n_leaf_tanpa_slot'] = int((per.slot == 0).sum())

# ------------------------------- Tabel 8 per seri (lengan dinolkan, beta=1)
xm = ext[ext.beta == 1.0]
pv = (xm.pivot_table(index=['leaf', 'top_k'], columns='ext', values='mase')
      .rename(columns={False: 'fe', True: 'fe_ext'}).reset_index())
pv['delta'] = 100*(pv.fe_ext - pv.fe)/pv.fe
pv['n_ext'] = [slot[l][f'k{k}_mrmr'] for l, k in zip(pv.leaf, pv.top_k)]
T['per_leaf_ext'] = [dict(leaf=r.leaf, k=int(r.top_k), fe=float(r.fe),
    fe_ext=float(r.fe_ext), delta=float(r.delta), n_ext=int(r.n_ext))
    for r in pv.itertuples()]
aa = pv[(pv.top_k == 25) & (pv.n_ext > 0)]
r3, p3 = spearmanr(aa.n_ext, aa.delta)
T['per_leaf_spearman_informative'] = {'rho': float(r3), 'p': float(p3),
                                      'n': int(len(aa))}
T['per_leaf_ext_summary'] = {
    'n_better_25': int((pv[pv.top_k == 25].delta < -0.5).sum()),
    'n_better_12': int((pv[pv.top_k == 12].delta < -0.5).sum()), 'n': 15}

# ---------------------------------------------------------------- Tabel 9
NM = {'Redundancy-aware selection': 0, 'Daily re-fitting': 1,
      'Tuned hyperparameters': 2}
T['reverse_ablation'] = [dict(component=r['komponen'], opt=r['mean_opt'],
    off=r['mean_off'], delta=r['delta_pct'], p=r['p'], wins=r['menang_opt'],
    n=r['n'], sig=r['p'] < 0.05)
    for r in sorted(U['tabel9'], key=lambda r: NM[r['komponen']])]
T['reverse_by_model'] = {r['komponen']: [round(r['per_model_pct'][m], 2)
    for m in ('LightGBM', 'RandomForest', 'XGBoost')] for r in U['tabel9']}
T['reverse_leaf_worse'] = {r['komponen']: r['leaf_lebih_baik_tanpa']
                           for r in U['tabel9']}

# -------------------------------------------------------------- SHAP dan slot
T.update(shap_family=S['shap_family'], shap_ext_share=S['shap_ext_share'],
         beeswarm_leaf=S['beeswarm_leaf'], beeswarm_n_ext=S['beeswarm_n_ext'],
         beeswarm_top=S['beeswarm_top'], mean_lag_slots=S['mean_lag_slots'],
         mean_ext_slots=S['mean_ext_slots'])
T['shap_per_leaf'] = {lf: {'n_ext': v['n_ext'], 'n_lag': v['n_lag']}
                      for lf, v in S['per_leaf'].items()}
D = pd.DataFrame(slot).T
T['slot_uptake_new'] = {f'k{k}_{t}': float(D[f'k{k}_{t}'].mean())
                        for k in (12, 25) for t in ('mrmr', 'univ')}
T['slot_max_k25_mrmr'] = int(D['k25_mrmr'].max())
T['pool_internal'] = int(D.kandidat_internal.mode()[0])
T['pool_total'] = int(D.kandidat_total.mode()[0])
T['pool_pasar'] = int(D.kandidat_pasar.mode()[0])
T['n_lags'] = 18
T['lag_pasar'] = list(range(1, 15))

# Cocokkan slot yang dihitung di sini dengan n_ext dari SHAP milik VPS.
# Keduanya mengukur hal yang sama pada konfigurasi utama (k=25, mRMR), hanya
# dihitung di mesin berbeda - kalau berbeda jauh, angka slot tidak layak
# dipakai di naskah.
beda = {lf: (sl25[lf], T['shap_per_leaf'][lf]['n_ext'])
        for lf in sl25 if sl25[lf] != T['shap_per_leaf'][lf]['n_ext']}
T['slot_vs_shap_beda'] = beda

# ------------------------------------------------- catatan reprodusibilitas
T['versi'] = V
# Catatan reprodusibilitas ARIMA hanya bisa dihitung kalau ada run PEMBANDING.
# Tanpa itu naskah kehilangan satu butir batasan - bukan galat.
T['arima_repro'] = None
if LAMA and os.path.exists(LAMA + 'opt_rolling.csv'):
    lama_roll = BACA('opt_rolling.csv', LAMA)
    kk = ['leaf', 'model', 'origin']
    cmp = (lama_roll[kk + ['mase']].rename(columns={'mase': 'lama'})
           .merge(roll[kk + ['mase']].rename(columns={'mase': 'baru'}), on=kk))
    cmp['rel'] = (cmp.lama - cmp.baru).abs() / cmp.lama.abs().clip(lower=1e-300)
    per_model = cmp.groupby('model').apply(lambda d: int((d.rel > 1e-9).sum()))
    p_lama = None
    if os.path.exists(LAMA + 'uji_statistik.json'):
        p_lama = json.load(open(LAMA + 'uji_statistik.json'))['tabel6_uji']['ARIMA']['p']
    T['arima_repro'] = {
        'sel_berbeda': {m: int(v) for m, v in per_model.items() if v > 0},
        'n_per_model': 450,
        'mean_lama': float(lama_roll[lama_roll.model == 'ARIMA'].mase.mean()),
        'mean_baru': float(roll[roll.model == 'ARIMA'].mase.mean()),
        'p_lama': float(p_lama) if p_lama is not None else None,
        'p_baru': float(U['tabel6_uji']['ARIMA']['p']),
    }

out = TABLES
json.dump(T, open(out, 'w'))
print(f'{out} ditulis, {len(T)} kunci\n')
print(f"  leaf {T['n_leaf']} | hari {T['n_hari']} | kandidat "
      f"{T['pool_internal']} internal / {T['pool_total']} total "
      f"(pasar {T['pool_pasar']})")
print(f"  slot pasar k25 mRMR: rata {T['slot_uptake_new']['k25_mrmr']:.2f} "
      f"maks {T['slot_max_k25_mrmr']}")
print(f"  slot vs SHAP n_ext berbeda di {len(beda)} leaf: {beda or 'tidak ada'}")
gb = T['tabel8b_gabungan']
print(f"\n  TABEL 8b gabungan: tanpa {gb['mati']:.4f} | nol {gb['nol']:.4f} "
      f"({gb['delta_nol']:+.1f}%) | benar {gb['benar']:.4f} ({gb['delta_benar']:+.1f}%)")
print(f"    kerusakan hilang {gb['rusak_hilang_pct']:.0f}%  "
      f"p vs mati {gb['p_vs_mati']:.3g}  p vs nol {gb['p_vs_nol']:.3g}")
print(f"    leaf membaik {T['n_leaf_membaik']}, memburuk {T['n_leaf_memburuk']}, "
      f"tanpa slot {T['n_leaf_tanpa_slot']}")
print(f"  Spearman slot-kerusakan: nol rho={T['slot_damage']['nol']['rho']:.3f} "
      f"(p={T['slot_damage']['nol']['p']:.4f}) -> "
      f"benar rho={T['slot_damage']['benar']['rho']:.3f} "
      f"(p={T['slot_damage']['benar']['p']:.4f})")
print('  ARIMA sel berbeda antar-run: '
      + (str(T['arima_repro']['sel_berbeda']) if T['arima_repro']
         else '(dilewati - JBV_NASKAH_LAMA tidak disetel)'))
