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
    T['desc'].append(dict(leaf=r['Row_ID'], label=str(lab[r['Row_ID']]),
        mean=float(y.mean()), sd=float(y.std()), med=float(np.median(y)),
        zero=float(100*(y == 0).mean()), skew=float(skew(y)),
        kurt=float(kurtosis(y)), acf1=float(pd.Series(y).autocorr(1))))
T['n_leaf'] = len(lv)
T['n_hari'] = len(dcols)
T['tgl_awal'], T['tgl_akhir'] = dcols[0], dcols[-1]

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
