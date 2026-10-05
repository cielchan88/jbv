"""Susun tables.json - seluruh angka naskah, dihitung dari berkas hasil mentah.

Setiap angka di naskah berasal dari sini, dan sini membacanya dari CSV/JSON
hasil komputasi - tidak ada yang disalin dengan tangan. Itulah yang membuat
cek_draft.py bisa membandingkan naskah terhadap sumbernya.

    venv/bin/python scripts/paper/naskah/buat_tables.py

Jalan berkas diatur jalan.py; lihat docstring-nya untuk env yang tersedia.
"""
import json, os, sys, warnings
import pandas as pd, numpy as np
from scipy.stats import spearmanr, skew, kurtosis, wilcoxon

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jalan                                  # lewat modul, JANGAN from-import
from jalan import SLOT, LAMA, BANDING, TABLES, siapkan, periksa_hasil, REPO

# HASIL sengaja diambil lewat jalan.HASIL, bukan di-from-import. h1_common
# JUGA mendefinisikan HASIL, dan `from h1_common import *` di bawah akan
# menimpanya - bug yang tidak terlihat selama kedua folder kebetulan sama,
# lalu diam-diam membaca folder yang salah begitu keduanya berbeda.
HASIL = jalan.HASIL

sys.path.insert(0, os.path.join(REPO, 'scripts', 'paper', 'revisi'))
os.environ.setdefault('JBV_PANEL', 'data/processed/sdv-wide-gabung.csv')
# Samakan folder dan panjang blok validasi h1_common dengan folder yang
# benar-benar dibaca, supaya pemeriksa sidik jarinya tidak menolak folder
# lain yang sah.
os.environ['JBV_HASIL'] = os.path.basename(HASIL.rstrip(os.sep))
import json as _json
_cfg = HASIL + 'konfigurasi.json'
if os.path.exists(_cfg):
    os.environ['JBV_NVAL'] = str(_json.load(open(_cfg)).get('nval', 10))
os.environ['JBV_DIAM'] = '1'
# Penyusun naskah hanya MEMBACA folder hasil. Tanpa ini, mengganti jendela di
# feature_config.py membuat naskah yang sedang beredar tidak bisa dibangun lagi
# dari foldernya sendiri - sidik jari folder itu menyebut jendela lama.
os.environ['JBV_BACA_SAJA'] = '1'
from h1_common import *                      # ber-chdir ke akar repo; menimpa HASIL
HASIL = jalan.HASIL                          # kembalikan milik jalan.py
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
    # Berkas ini SUDAH DI-COMMIT sejak ia hanya berisi tujuh hitungan bulat per
    # leaf - 2,4 KB, tanpa nilai arus - jadi biasanya ia sudah ada. Kalau hilang,
    # berarti folder hasil dialihkan lewat JBV_NASKAH_SLOT, atau checkout-nya
    # tidak lengkap. Petunjuk lamanya menyebut `python`, yang di banyak VPS tidak
    # ada sama sekali, dan tidak menyebut venv - jadi menjalankannya apa adanya
    # gagal dengan ModuleNotFoundError, bukan dengan hasil.
    raise SystemExit(
        f'BERHENTI: slot_pasar.json tidak ada di\n  {SLOT}\n'
        'Berkas ini ikut di-commit, jadi biasanya cukup:\n'
        '  git checkout -- scripts/paper/revisi/hasil_slot/slot_pasar.json\n'
        'Kalau memang perlu dihitung ulang (butuh sklearn, puluhan menit):\n'
        '  JBV_HASIL=hasil_slot venv/bin/python scripts/paper/revisi/cek_slot_pasar.py')
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
    # Dari laporan pertama (review ketujuh): nol struktural sebelum kategori
    # masuk kerangka pelaporan tidak ikut statistik deskriptif, sama dengan
    # desain v2 yang melatih sejak laporan pertama. Aturan >= 250 hari nol.
    _nz = np.nonzero(y)[0]
    _s0 = int(_nz[0]) if len(_nz) and _nz[0] >= 250 else 0
    y = y[_s0:]
    T['desc'].append(dict(leaf=r['Row_ID'], label=str(lab[r['Row_ID']]), s0=_s0,
        mean=float(y.mean()), sd=float(y.std()), med=float(np.median(y)),
        zero=float(100*(y == 0).mean()), skew=float(skew(y)),
        kurt=float(kurtosis(y)), acf1=float(pd.Series(y).autocorr(1))))
T['n_leaf'] = len(lv)
T['n_hari'] = len(dcols)
T['tgl_awal'], T['tgl_akhir'] = dcols[0], dcols[-1]
T['tgl_uji_awal'] = dcols[-30]
T['tgl_latih_akhir'] = dcols[-2]           # desain headline: training berakhir sehari sebelum uji

# ------------------------------------------------- nilai hilang di data pasar
# Naskah menyebut rentang nilai hilang di 3.3 dan menyatakan tidak ada nilai
# yang dibawa MUNDUR lebih dari satu tanggal. Keduanya diturunkan di sini,
# bukan diketik: versi ketik tangan menulis "between 0.1 and 0.7 per cent"
# padahal EMPAT dari delapan variabel tidak punya nilai hilang sama sekali,
# jadi batas bawahnya menyesatkan.
#
# load_external() memakai ffill lalu bfill, jadi hanya deretan NaN di AWAL
# yang terisi mundur - itulah yang dihitung sebagai bfill_maks.
T['pasar'] = None
if os.path.exists(EXT):
    _e = pd.read_excel(EXT)
    _kol = [c for c in _e.columns if c != 'Tanggal']
    _n = len(_e)
    _hil = {c: float(100 * pd.to_numeric(_e[c], errors='coerce').isna().sum() / _n)
            for c in _kol}
    def _nan_awal(s):
        v = pd.to_numeric(s, errors='coerce').isna().values
        i = 0
        while i < len(v) and v[i]:
            i += 1
        return i
    T['pasar'] = {
        'n_var': len(_kol),
        'n_tanggal': _n,
        'hilang_maks': max(_hil.values()),
        'n_tanpa_hilang': sum(1 for v in _hil.values() if v == 0),
        'bfill_maks': max(_nan_awal(_e[c]) for c in _kol),
    }
    print(f"  data pasar: {T['pasar']['n_var']} variabel, hilang maks "
          f"{T['pasar']['hilang_maks']:.3f}%, {T['pasar']['n_tanpa_hilang']} tanpa "
          f"hilang, bawa mundur maks {T['pasar']['bfill_maks']} tanggal")
else:
    print(f'  data pasar: {EXT} tidak ada - klaim nilai hilang dilewati')

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
T['n_leaf_tanpa_slot'] = int((per.slot == 0).sum())
T['n_leaf_membaik'] = int(((per.rusak_benar < 0) & (per.slot > 0)).sum())
T['n_leaf_memburuk'] = int(((per.rusak_benar > 0) & (per.slot > 0)).sum())
assert T['n_leaf_membaik'] + T['n_leaf_memburuk'] + T['n_leaf_tanpa_slot'] == len(per), 'rincian seri pasar tidak berjumlah penuh'

# ------------------- per seri, lengan DISUPLAI (hasil utama 4.5, beta=1)
# Tabel per seri di 4.5 kini melaporkan hasil yang sudah dikoreksi: data pasar
# ikut diberikan saat meramal. Lengan dinolkan hanya muncul di Diskusi.
_sup = gg[gg.beta == 1.0].groupby(['leaf', 'top_k']).agg(
    mati=('mati', 'mean'), benar=('benar', 'mean')).reset_index()
_sup['delta'] = 100 * (_sup.benar / _sup.mati - 1)
T['per_leaf_supplied'] = [dict(leaf=r.leaf, k=int(r.top_k), off=float(r.mati), on=float(r.benar),
                               delta=float(r.delta), n_ext=int(slot[r.leaf][f'k{int(r.top_k)}_mrmr']))
                          for r in _sup.itertuples()]
_s25 = _sup[_sup.top_k == 25]
_rs, _ps = spearmanr([slot[l]['k25_mrmr'] for l in _s25.leaf], _s25.delta)
T['supplied_slot_rho'] = {'rho': float(_rs), 'p': float(_ps)}

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
    n=r['n'], p_holm=r.get('p_holm'),
    # Putusan tabel memakai Holm atas tiga komponen, bukan p mentah: ketiganya
    # diuji pada data yang sama. Dengan p mentah, mRMR (p 0,038) tercetak
    # "significant" padahal Holm-nya 0,113.
    sig=(r.get('p_holm') if r.get('p_holm') is not None else r['p']) < 0.05)
    for r in sorted(U['tabel9'], key=lambda r: NM[r['komponen']])]
T['reverse_by_model'] = {r['komponen']: [round(r['per_model_pct'][m], 2)
    for m in ('LightGBM', 'RandomForest', 'XGBoost')] for r in U['tabel9']}
T['reverse_leaf_worse'] = {r['komponen']: r['leaf_lebih_baik_tanpa']
                           for r in U['tabel9']}

# --------------------------------------- Tabel 7: kekokohan lengan ablasi k
# Uji per titik (n = 1.350) memperlakukan origin dalam satu leaf sebagai
# saling bebas, padahal tidak. Tiga pemeriksaan tambahan, semuanya dari
# berkas mentah yang sama:
#   - Holm atas seluruh lengan melawan k=25 (satu keluarga uji),
#   - Wilcoxon per LEAF (rata-rata 3 model x 30 origin, n = 15), satuan yang
#     lebih jujur untuk ketergantungan antar-origin,
#   - selisih per model dan per paruh blok uji.
_kb = BACA('sisa_kablasi.csv')
_kp = _kb.pivot_table(index=['leaf', 'model', 'origin'], columns='top_k', values='mase')
_acuan = 25
_lengan = [k for k in _kp.columns if k != _acuan]
_praw = {k: float(wilcoxon(_kp[k], _kp[_acuan]).pvalue) for k in _lengan}
_urut = sorted(_lengan, key=_praw.get)
_holm, _jalan = {}, 0.0
for _i, _k in enumerate(_urut):
    _jalan = max(_jalan, min(1.0, (len(_urut) - _i) * _praw[_k]))
    _holm[_k] = _jalan
_L = _kp.groupby(level='leaf').mean()
_o = _kp.index.get_level_values('origin')
for a in T['ablation']:
    k = a['k']
    if k == _acuan:
        continue
    a['p_holm'] = _holm[k]
    a['p_leaf'] = float(wilcoxon(_L[k], _L[_acuan]).pvalue)
    a['leaf_lebih_baik'] = int((_L[k] < _L[_acuan]).sum())
    a['per_model'] = {m: float(100 * (_kp[k].xs(m, level='model').mean()
                                      / _kp[_acuan].xs(m, level='model').mean() - 1))
                      for m in ('LightGBM', 'RandomForest', 'XGBoost')}
    a['paruh'] = [float(100 * (_kp[k][_o < 15].mean() / _kp[_acuan][_o < 15].mean() - 1)),
                  float(100 * (_kp[k][_o >= 15].mean() / _kp[_acuan][_o >= 15].mean() - 1))]
T['ablation_acuan'] = _acuan

# ------------------------------------ kombinasi ramalan berbobot sama (4.2)
# Lima kombinasi sederhana, SEMUANYA dilaporkan dan dikoreksi Holm bersama,
# supaya tidak ada yang dipilih sesudah melihat blok uji. Bobot sama tidak
# butuh data untuk ditaksir, jadi tidak ada kebocoran dari blok uji.
_r = BACA('opt_rolling.csv')
_r['skala'] = _r.ae / _r.mase
_P = _r.pivot_table(index=['leaf', 'origin'], columns='model', values='pred')
_A = _r.groupby(['leaf', 'origin']).actual.first()
_S = _r.groupby(['leaf', 'origin']).skala.median()
_mase = lambda pr: (pr - _A).abs() / _S
_juara = T['champion_juara']
_ref = _mase(_P[_juara])
_ML = ['LightGBM', 'RandomForest', 'XGBoost']
_KOMB = [('Mean of the three learners', _P[_ML].mean(axis=1)),
         ('Mean of the three learners, ARIMA and Croston', _P[_ML + ['ARIMA', 'Croston']].mean(axis=1)),
         ('Mean of LightGBM and ARIMA', _P[['LightGBM', 'ARIMA']].mean(axis=1)),
         ('Median of all ten methods', _P.median(axis=1)),
         ('Mean of all ten methods', _P.mean(axis=1))]
_ens, _pr = [], {}
for nama, pr in _KOMB:
    m = _mase(pr)
    L = pd.DataFrame({'c': m, 'j': _ref}).groupby(level='leaf').mean()
    _pr[nama] = float(wilcoxon(m, _ref).pvalue)
    _ens.append(dict(nama=nama, mase=float(m.mean()), med=float(m.median()), max=float(m.max()),
                     delta=float(100 * (m.mean() / _ref.mean() - 1)), wins=int((m < _ref).sum()),
                     n=int(len(m)), p=_pr[nama], leaf_lebih_baik=int((L.c < L.j).sum())))
_urut, _jalan = sorted(_ens, key=lambda e: e['p']), 0.0
for i, e in enumerate(_urut):
    _jalan = max(_jalan, min(1.0, (len(_urut) - i) * e['p']))
    e['p_holm'] = _jalan
T['ensemble'] = _ens

# ============================================================ review kedua (B)
# Semua dari berkas hasil yang sudah ada; lihat inferensi.py untuk alasannya.
import inferensi as INF
_opt = roll.set_index(['leaf', 'model', 'origin']).mase
_ML3 = ['LightGBM', 'RandomForest', 'XGBoost']
_ab = BACA('opt_ablasi.csv')
_R = {}

# 1. metode: juara melawan kesembilan lainnya (450 unit, sudah per seri-tanggal)
_jr = T['champion_juara']
_m = roll.pivot_table(index=['leaf', 'origin'], columns='model', values='mase')
_R['metode'] = [INF.banding(_m[_jr], _m[m], m) for m in _m.columns if m != _jr]

# 2. ablasi terbalik: rata-rata tiga learner per (seri, tanggal)
_full = _opt[_opt.index.get_level_values('model').isin(_ML3)]
_KOMP = {'tanpa_mrmr': 'Redundancy-aware selection', 'tanpa_refit': 'Daily re-fitting',
         'tanpa_setelan': 'Tuned hyperparameters'}
_R['komponen'] = [INF.banding(_full, _ab[_ab.arm == arm].set_index(['leaf', 'model', 'origin']).mase, lab_)
                  for arm, lab_ in _KOMP.items()]
# menang tanpa ties: 'tanpa_setelan' identik di sel yang memilih konfigurasi 1
T['reverse_ties'] = {}
for arm, lab_ in _KOMP.items():
    x = _ab[_ab.arm == arm].set_index(['leaf', 'model', 'origin']).mase
    j = pd.concat([_full, x], axis=1, keys=['o', 'x']).dropna()
    seri_ = int(np.isclose(j.o, j.x, rtol=0, atol=1e-12).sum())
    T['reverse_ties'][lab_] = dict(ties=seri_, wins=int((j.o < j.x).sum()), n=int(len(j)))

# 3. jumlah fitur melawan k acuan
_R['k'] = [INF.banding(_kp[_acuan], _kp[k], f'k = {k}') for k in _kp.columns if k != _acuan]

# 4. data pasar disuplai melawan dimatikan, dirata-rata atas learner dan kondisi
_gi = gg.set_index(['leaf', 'model', 'origin', 'beta', 'top_k'])
_R['pasar'] = [INF.banding(_gi.mati, _gi.benar, 'pooled')] + [
    INF.banding(g_.mati, g_.benar, f"{'mRMR' if b_ == 1 else 'univariate'}, k = {int(k_)}")
    for (b_, k_), g_ in _gi.groupby(level=['beta', 'top_k'])]

# 5. kombinasi melawan juara
_R['kombinasi'] = [INF.banding(_ref, _mase(pr), nama) for nama, pr in _KOMB]

# 5b. (review ketiga) keluarga tambahan, semuanya pada unit (seri, tanggal)
#     dan SESUDAH panggilan di atas, supaya urutan RNG CI utama tidak berubah.
_ex = ext[~ext.ext.astype(bool)].set_index(['leaf', 'model', 'origin', 'beta', 'top_k']).mase
_R['selektor'] = [INF.banding(_ex.xs((0.0, k_), level=['beta', 'top_k']),
                              _ex.xs((1.0, k_), level=['beta', 'top_k']), f'k = {k_}')
                  for k_ in sorted(ext.top_k.unique())]
_R['nolkan'] = [INF.banding(_gi.mati, _gi.nol, 'zero-filled'), INF.banding(_gi.mati, _gi.benar, 'supplied')]
_R['nolkan_kondisi'] = [INF.banding(g_.mati, g_.nol, f"{'mRMR' if b_ == 1 else 'univariate'}, k = {int(k_)}")
                        for (b_, k_), g_ in _gi.groupby(level=['beta', 'top_k'])]
# efek tuning bersyarat: hanya pasangan seri-learner yang setelannya berubah
_tn = _ab[_ab.arm == 'tanpa_setelan'].set_index(['leaf', 'model', 'origin']).mase
_jt = pd.concat([_full, _tn], axis=1, keys=['o', 'x']).dropna()
_beda = pd.Series(~np.isclose(_jt.o, _jt.x, rtol=0, atol=1e-12), index=_jt.index).groupby(level=['leaf', 'model']).any()
_pakai = np.array([bool(_beda[(l_, m_)]) for l_, m_, _o_ in _jt.index])
_R['tuning_bersyarat'] = INF.banding(_jt.o[_pakai], _jt.x[_pakai], 'Tuned hyperparameters, changed pairs')
_R['tuning_bersyarat']['n_pasangan'] = int(_beda.sum())
# per learner (n = 450 per learner): ekuivalensi pooled belum tentu berlaku per learner
_R['komponen_per_model'] = {
    lab_: {m: INF.banding(_full.xs(m, level='model'),
                          _ab[(_ab.arm == arm) & (_ab.model == m)].set_index(['leaf', 'origin']).mase,
                          f'{lab_}, {m}') for m in _ML3}
    for arm, lab_ in _KOMP.items()}
for fam_ in ('metode', 'komponen', 'k', 'pasar', 'kombinasi', 'selektor', 'nolkan_kondisi'):
    INF.holm(_R[fam_])
T['robust'] = _R

# 6. Diebold-Mariano (HLN) per seri: juara melawan metode lain
_dm = []
for m in _m.columns:
    if m == _jr:
        continue
    lebih, kalah = 0, 0
    for lf, g_ in _m.groupby(level='leaf'):
        stat, pp = INF.dm_hln(g_[_jr].values, g_[m].values)
        if pp < 0.05:
            lebih += stat > 0
            kalah += stat < 0
    _dm.append(dict(model=m, juara_lebih_baik=int(lebih), juara_lebih_buruk=int(kalah)))
T['dm_per_seri'] = _dm

# 7. Model Confidence Set 90 persen pada rata-rata harian MASE
_L = roll.pivot_table(index='origin', columns='model', values='mase', aggfunc='mean')
_mcs, _mcs_p = INF.mcs(_L, alpha=0.10)
T['mcs'] = dict(tersisa=_mcs, p=_mcs_p, alpha=0.10, n_tanggal=int(len(_L)))

# 8. skala MASE untuk seri yang baru dilaporkan setelah awal panel
#    Penyebut asli dihitung atas y[:cut] termasuk periode nol struktural.
_kor, _fak = [], {}
for _, rr in lv.iterrows():
    dd_, yy_ = series_of(rr, dcols, dall)
    cut_ = len(yy_) - 30
    nz = np.nonzero(yy_)[0]
    if len(nz) and nz[0] >= 250:
        lama_ = scale_denom(yy_[:cut_]); baru_ = scale_denom(yy_[nz[0]:cut_])
        _fak[rr.Row_ID] = lama_ / baru_
        _kor.append(dict(leaf=rr.Row_ID, mulai=str(dd_[nz[0]])[:10], nol_sebelum=int(nz[0]),
                         faktor=float(lama_ / baru_)))
_f = lambda s: s * s.index.get_level_values('leaf').map(lambda l: _fak.get(l, 1.0)).values
_rk = roll.set_index(['leaf', 'model', 'origin']).mase
_rk2 = _f(_rk)
_rank2 = _rk2.groupby(level='model').mean().sort_values()
_m2 = _rk2.unstack('model')
_kab2 = _f(_kb.set_index(['leaf', 'model', 'origin', 'top_k']).mase).unstack('top_k')
_ab2 = _f(_ab.set_index(['leaf', 'model', 'origin', 'arm']).mase).unstack('arm')
_full2 = _f(_full)
_g2 = _gi.copy()
for c_ in ('mati', 'benar'):
    _g2[c_] = _f(_gi[c_])
T['skala_koreksi'] = dict(
    seri=_kor,
    peringkat=[dict(model=m, lama=float(_rk.groupby(level='model').mean()[m]), baru=float(v))
               for m, v in _rank2.items()],
    juara_baru=str(_rank2.index[0]),
    uji_juara={m: float(wilcoxon(_m2[_jr], _m2[m]).pvalue) for m in ('ARIMA', 'Croston', 'RandomForest', 'XGBoost')},
    komponen={lab_: float(100 * (_ab2[arm].mean() / _full2.reindex(_ab2.index).mean() - 1))
              for arm, lab_ in _KOMP.items()},
    k={int(k): float(100 * (_kab2[k].mean() / _kab2[_acuan].mean() - 1)) for k in _kab2.columns if k != _acuan},
    pasar=float(100 * (_g2.benar.mean() / _g2.mati.mean() - 1)))

# 9. metrik untuk desk (juta USD dan relatif terhadap random walk)
#    Review ketiga: B.1 (93 persen nol di blok uji) mendominasi rata-rata
#    geometrik, jadi semuanya dihitung dengan dan tanpa B.1; akurasi arah
#    diuji dengan Pesaran-Timmermann (pooled, mengabaikan ketergantungan).
_rw = roll[roll.model == 'Naive'].set_index(['leaf', 'origin'])


def _metrik_desk(buang=()):
    hasil = []
    for m, g_ in roll[~roll.leaf.isin(buang)].groupby('model'):
        g_ = g_.set_index(['leaf', 'origin'])
        prev = _rw.pred.reindex(g_.index)                  # ramalan RW = nilai kemarin
        mae_s = g_.ae.groupby(level='leaf').mean()
        rw_s = _rw.ae.groupby(level='leaf').mean().reindex(mae_s.index)
        rel = (mae_s / rw_s).replace([np.inf], np.nan).dropna()
        arah_a, arah_p = np.sign(g_.actual - prev), np.sign(g_.pred - prev)
        ok = (arah_a != 0) & (arah_p != 0)
        pt_, ptp_ = INF.pesaran_timmermann(arah_a[ok], arah_p[ok]) if ok.sum() > 10 else (None, None)
        tot = g_.groupby(level='origin')[['actual', 'pred']].sum()
        hasil.append(dict(model=m, rel_mae_geo=float(np.exp(np.log(rel[rel > 0]).mean())),
                          mae=float(g_.ae.mean()), bias=float((g_.actual - g_.pred).mean()),
                          arah=(float((arah_a[ok] == arah_p[ok]).mean() * 100) if ok.sum() else None),
                          n_arah=int(ok.sum()), pt=pt_, pt_p=ptp_,
                          mae_total=float((tot.actual - tot.pred).abs().mean())))
    hasil = sorted(hasil, key=lambda r: r['rel_mae_geo'])
    for i, r in enumerate(hasil):
        r['peringkat'] = i + 1
    return hasil


T['desk'] = _metrik_desk()
_jarang = str((_rw.actual == 0).groupby(level='leaf').mean().idxmax())   # seri paling jarang di blok uji
T['desk_tanpa'] = dict(leaf=_jarang, rows=_metrik_desk((_jarang,)))
_td = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keluaran', 'topdown.json')
assert os.path.exists(_td), 'jalankan dulu: python scripts/paper/naskah/topdown.py'
_td = pd.DataFrame(json.load(open(_td)))
_tot = roll[roll.model == 'Naive'].groupby('origin').actual.sum()
assert np.allclose(_tot.values, _td.sort_values('origin').actual.values), 'total top-down tidak cocok dengan jumlah seri'
T['topdown'] = dict(arima=float((_td.actual - _td.arima).abs().mean()),
                    rw=float((_td.actual - _td.rw).abs().mean()))

# 9b. patahan 2022 dan penyebut MASE: skala dihitung hanya dari 2022 ke
#     depan untuk semua seri (sensitivitas, bukan hasil utama).
_fak22 = {}
for _, rr in lv.iterrows():
    dd_, yy_ = series_of(rr, dcols, dall)
    cut_ = len(yy_) - 30
    m22 = np.asarray(pd.DatetimeIndex(dd_[:cut_]).year >= 2022)
    _fak22[rr.Row_ID] = scale_denom(yy_[:cut_]) / scale_denom(yy_[:cut_][m22])
_rk22 = _rk * _rk.index.get_level_values('leaf').map(_fak22).values
_r22 = _rk22.groupby(level='model').mean().sort_values()
T['skala_2022'] = dict(faktor={k: float(v) for k, v in _fak22.items()},
                       peringkat=[dict(model=m, mase=float(v)) for m, v in _r22.items()],
                       rw=float(_r22['Naive']), rw_lama=float(_rk.groupby(level='model').mean()['Naive']))

# 10. RQ4: pangsa SHAP pasar per kelompok pihak transaksi
_sh = pd.Series({r['leaf']: r['share'] for r in S['shap_ext_share']})
T['shap_per_kelompok'] = {g: float(_sh[_sh.index.str[0] == g].mean()) for g in 'ABC'}

# 11. penalti pasar per seri, dengan dan tanpa dua sel "Other" terbesar
_ps = pd.DataFrame(T['per_leaf_supplied'])
# 11b. MASE per seri x metode, untuk heatmap (Gambar 5)
T['per_leaf_model'] = {lf: {m: float(v) for m, v in g_.groupby('model').mase.mean().items()}
                       for lf, g_ in roll.groupby('leaf')}

# 12. pangsa SHAP pasar tidak memprediksi apakah data pasar membantu
_chg = pd.Series({r['leaf']: r['delta'] for r in T['per_leaf_supplied'] if r['k'] == 25})
_rr, _pp = spearmanr(_sh.reindex(_chg.index), _chg)
T['shap_vs_change'] = dict(rho=float(_rr), p=float(_pp))

# 13. nol sejak mulai pelaporan, dan analisis sparsity yang dihitung ulang
_z = {}
for _, rr in lv.iterrows():
    dd_, yy_ = series_of(rr, dcols, dall)
    nz = np.nonzero(yy_)[0]
    _z[rr.Row_ID] = dict(mulai=str(dd_[nz[0]])[:10], nol_total=float(100 * np.mean(yy_ == 0)),
                         nol_sejak=float(100 * np.mean(yy_[nz[0]:] == 0)),
                         nol_uji=float(100 * np.mean(yy_[-30:] == 0)))
T['nol_sejak'] = _z

# 13b. patahan Januari 2022 di sel ekspor (fakta data, tanpa tafsiran sebab)
_pt = {}
for _, rr in lv.iterrows():
    if rr.Row_ID not in ('B.a', 'A.2.a', 'A.2.b'):
        continue
    dd_, yy_ = series_of(rr, dcols, dall)
    th = pd.DatetimeIndex(dd_).year
    _pt[rr.Row_ID] = dict(nol_14_21=float(100 * np.mean(yy_[(th >= 2014) & (th <= 2021)] == 0)),
                          nol_22=float(100 * np.mean(yy_[th >= 2022] == 0)),
                          abs_21=float(np.mean(np.abs(yy_[th == 2021]))),
                          abs_22=float(np.mean(np.abs(yy_[th == 2022]))))
assert _pt['B.a']['nol_14_21'] < 10 and _pt['B.a']['nol_22'] > 75, _pt['B.a']
assert _pt['A.2.a']['abs_22'] < 0.2 * _pt['A.2.a']['abs_21'] and _pt['A.2.b']['abs_22'] > _pt['A.2.b']['abs_21']
_a1 = _a2 = None
for _, rr in lv.iterrows():
    if rr.Row_ID in ('A.2.a', 'A.2.b'):
        dd_, yy_ = series_of(rr, dcols, dall)
        ss_ = pd.Series(yy_, index=pd.DatetimeIndex(dd_))
        if rr.Row_ID == 'A.2.a':
            _a1 = ss_
        else:
            _a2 = ss_
_jm = (_a1 + _a2)
_pt['jumlah_a'] = dict(des21=float(_jm['2021-12'].mean()), jan22=float(_jm['2022-01'].mean()),
                       a1_des21=float(_a1['2021-12'].mean()), a1_jan22=float(_a1['2022-01'].mean()))
_sd = _a1.groupby(_a1.index.year).std()
_pt['a1_sd'] = dict(min_19_24=float(_sd.loc[2019:2024].min()), max_19_24=float(_sd.loc[2019:2024].max()),
                    th2025=float(_sd.loc[2025]), th2026=float(_sd.loc[2026]))
assert abs(_pt['jumlah_a']['jan22'] / _pt['jumlah_a']['des21'] - 1) < 0.25, _pt['jumlah_a']
assert _pt['a1_sd']['th2026'] > _pt['a1_sd']['max_19_24'], _pt['a1_sd']
T['patahan_2022'] = _pt

# 13c. SHAP dua learner, taksonomi Lampiran D (shap_dua.py, dihitung lokal)
_sdj = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keluaran', 'shap_dua.json')
assert os.path.exists(_sdj), 'jalankan dulu: python scripts/paper/naskah/shap_dua.py'
_SD = json.load(open(_sdj))
assert set(_SD) == set(lv.Row_ID), 'shap_dua.json tidak lengkap'
_famd = {}
for nm_ in ('RandomForest', 'LightGBM'):
    df_ = pd.DataFrame({l: v[nm_] for l, v in _SD.items()}).fillna(0.0)
    _famd[nm_] = df_.mean(axis=1).sort_values(ascending=False).to_dict()
_mk = pd.DataFrame({l: {nm_: v[nm_].get('Market', 0.0) for nm_ in ('RandomForest', 'LightGBM')}
                    for l, v in _SD.items()}).T
# pangsa pasar RF lokal harus sama dengan SHAP VPS (shap_ringkas.json)
_vps = pd.Series({r['leaf']: r['share'] for r in S['shap_ext_share']})
# Dihitung di lingkungan lain (versi pustaka berbeda, lihat Lampiran F), jadi
# tidak harus identik dengan SHAP VPS di setiap seri. Jumlah seri yang identik
# dilaporkan di naskah; penjaga ini hanya menolak kalau sebagian besar meleset.
_meleset = (np.abs(_mk.RandomForest.reindex(_vps.index) - _vps) > 0.15)
assert (~_meleset).sum() >= 12, f'SHAP RF lokal terlalu jauh dari VPS: {list(_vps.index[_meleset])}'
_rf_vps_cocok = int((~_meleset).sum())
_rr, _pp = spearmanr(_mk.RandomForest, _mk.LightGBM)
T['shap_dua'] = dict(famili=_famd, rf_cocok_vps=_rf_vps_cocok, pasar=_mk.to_dict(orient='index'),
                     rho_pasar=float(_rr), p_pasar=float(_pp),
                     kelompok={nm_: {g: float(_mk[nm_][_mk.index.str[0] == g].mean()) for g in 'ABC'}
                               for nm_ in ('RandomForest', 'LightGBM')})
_w = pd.DataFrame(T['winners']).set_index('leaf')
_w['nol_sejak'] = [_z[l]['nol_sejak'] for l in _w.index]
_rr, _pp = spearmanr(_w.nol_sejak, _w.mase)
T['winner_rho_sejak'], T['winner_p_sejak'] = float(_rr), float(_pp)

# 14. daftar lengkap kolam fitur internal, per keluarga (Lampiran)
from utils.feature_engineering_optimized import create_features_optimized as _cfo
_d0, _y0 = series_of(lv.iloc[0], dcols, dall)
_f0 = _cfo(pd.DataFrame({'ds': _d0[:-30], 'y': _y0[:-30]}))
_fit = [c for c in _f0.columns if c not in ('date', 'ds', 'value')]
_KEL = [('Lag', lambda c: c.startswith('lag_') and '_x_' not in c),
        ('Rolling statistics', lambda c: c.startswith('rolling_') and '_x_' not in c),
        ('Exponentially weighted mean', lambda c: c.startswith('ewm_')),
        ('Difference and percentage change', lambda c: c.startswith('value_')),
        ('Volatility and range', lambda c: any(k in c for k in ('volatil', 'price_position', 'max_change', 'min_change', 'change_range'))),
        ('Extreme value and jump', lambda c: any(k in c for k in ('z_score', 'is_extreme', 'jump'))),
        ('Technical indicator', lambda c: any(c.startswith(k) for k in ('rsi', 'bb_', 'macd'))),
        ('Interaction', lambda c: '_x_' in c),
        ('Calendar and Fourier', lambda c: True)]
_daftar, _sisa = [], list(_fit)
for nama_, f_ in _KEL:
    anggota = [c for c in _sisa if f_(c)]
    _sisa = [c for c in _sisa if c not in anggota]
    _daftar.append(dict(kelompok=nama_, fitur=anggota))
assert sum(len(x['fitur']) for x in _daftar) == next(iter(slot.values()))['kandidat_internal'], 'daftar fitur tidak sama dengan kolam internal'
T['daftar_fitur'] = _daftar

T['pasar_kualifikasi'] = {int(k): dict(
    semua=float(g_.delta.mean()),
    tanpa=float(g_[~g_.leaf.isin(['A.2.f', 'C.e'])].delta.mean()))
    for k, g_ in _ps.groupby('k')}
# Setelan terpilih per learner (indeks ke grid di rerun_optimal.py; 0 =
# setelan bawaan pustaka). Menunjukkan apakah penyetelan benar-benar bergerak.
_tn = BACA('opt_tuned.csv')
T['cfg_terpilih'] = {m: [int((g.cfg == i).sum()) for i in range(4)]
                     for m, g in _tn.groupby('model')}
T['nval'] = int(json.load(open(H + 'konfigurasi.json')).get('nval', 10))

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
# Lag dan jendela DARI FOLDER HASIL, bukan dari feature_config.py: angka yang
# dilaporkan naskah harus menggambarkan komputasi yang menghasilkan folder ini.
# Dulu diketik tetap range(1, 15), jadi mengganti lag pasar ke 1-15 akan
# membuat naskah tetap menulis 1-14.
_kf = konfigurasi_folder()
T['lag_pasar'] = list(_kf['lag_pasar'])
T['jendela'] = _kf['jendela']
T['rata_pasar'] = _kf['rata_pasar']

# Cocokkan slot yang dihitung di sini dengan n_ext dari SHAP milik VPS.
# Keduanya mengukur hal yang sama pada konfigurasi utama (k=25, mRMR), hanya
# dihitung di mesin berbeda - kalau berbeda jauh, angka slot tidak layak
# dipakai di naskah.
beda = {lf: (sl25[lf], T['shap_per_leaf'][lf]['n_ext'])
        for lf in sl25 if sl25[lf] != T['shap_per_leaf'][lf]['n_ext']}
T['slot_vs_shap_beda'] = beda

# ------------------------------------------------- catatan reprodusibilitas
T['versi'] = V
# Percobaan reprodusibilitas yang membandingkan beberapa RUN, jadi tidak bisa
# diturunkan dari berkas hasil mana pun. Disimpan tercatat di repro.json.
_repro = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'repro.json')
T['repro'] = json.load(open(_repro)) if os.path.exists(_repro) else None

# Ablasi jumlah fitur pada horizon 60 hari - PEMBANDING, bukan hasil naskah ini.
# Dipakai di 5.2 untuk mendukung klaim bahwa titik balik bias-ragam terlihat di
# horizon panjang. Angkanya datang dari ablation_topk.py dan tercatat di komentar
# TOP_K_FEATURES pada utils/feature_config.py; tidak bisa diturunkan dari berkas
# hasil naskah ini, jadi disimpan tercatat seperti repro.json. Tanpa berkasnya
# naskah memakai kalimat yang tidak menyebut angka - bukan galat.
_ab60 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ablasi_h60.json')
T['ablasi_h60'] = json.load(open(_ab60)) if os.path.exists(_ab60) else None
if T['ablasi_h60']:
    _a = T['ablasi_h60']
    # Penjaga: kalau tabel arm-nya diperbarui tapi ringkasannya tidak, naskah
    # akan mencetak angka yang tidak ada di tabelnya sendiri.
    _terbaik = min(_a['arm'], key=lambda r: r['delta_pct'])
    if _terbaik['k'] != _a['terbaik_k'] or abs(_terbaik['delta_pct'] - _a['terbaik_delta_pct']) > 1e-9:
        raise SystemExit(
            f"BERHENTI: ablasi_h60.json tidak konsisten - arm terbaik adalah "
            f"k={_terbaik['k']} ({_terbaik['delta_pct']}%) tapi terbaik_k={_a['terbaik_k']} "
            f"({_a['terbaik_delta_pct']}%). Perbarui ringkasannya.")
    if _a['n_leaf'] * _a['n_jendela'] * _a['n_model'] != _a['n_unit']:
        raise SystemExit(
            f"BERHENTI: ablasi_h60.json tidak konsisten - {_a['n_leaf']} x "
            f"{_a['n_jendela']} x {_a['n_model']} != {_a['n_unit']} unit.")
    print(f"  ablasi h={_a['horizon']}: k={_a['terbaik_k']} mengalahkan k={_a['acuan_k']} "
          f"sebesar {abs(_a['terbaik_delta_pct'])}% pada {_a['n_unit']} unit "
          f"({_a['n_leaf']} sel pra-penggabungan)")
else:
    print('  ablasi h=60: ablasi_h60.json tidak ada - klaim horizon dilewati')
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

# ------------------------- perbandingan panjang blok validasi
# Menjawab langsung kritik pengulas: apakah tanda negatif penyetelan bertahan
# kalau bloknya dilebarkan? Hanya bisa dihitung kalau kedua folder hasil ada.
T['blok_validasi'] = None
if BANDING and os.path.exists(BANDING + 'uji_statistik.json'):
    Ub = json.load(open(BANDING + 'uji_statistik.json'))
    tb = pd.read_csv(BANDING + 'opt_tuned.csv').set_index(['leaf', 'model'])
    tk = pd.read_csv(HASIL + 'opt_tuned.csv').set_index(['leaf', 'model'])
    gab = tb.join(tk, lsuffix='_pendek', rsuffix='_panjang')
    lama_arm = {r['komponen']: r for r in Ub['tabel9']}
    T['blok_validasi'] = {
        'nval_pendek': int(json.load(open(BANDING + 'konfigurasi.json'))
                           .get('nval', 10)),
        'nval_panjang': int(json.load(open(HASIL + 'konfigurasi.json'))
                            .get('nval', 60)),
        'n_cfg_berubah': int((gab.cfg_pendek != gab.cfg_panjang).sum()),
        'n_cfg': int(len(gab)),
        'lengan': [dict(komponen=r['komponen'],
                        delta_pendek=lama_arm[r['komponen']]['delta_pct'],
                        p_pendek=lama_arm[r['komponen']]['p'],
                        delta_panjang=r['delta_pct'], p_panjang=r['p'],
                        holm_panjang=r.get('p_holm'))
                   for r in U['tabel9']],
        'mean_pendek': {m: v['mean'] for m, v in Ub['tabel6'].items()},
        'mean_panjang': {m: v['mean'] for m, v in U['tabel6'].items()},
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
