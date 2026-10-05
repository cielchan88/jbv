"""Semua angka naskah dari jalan ulang v2 -> keluaran/tables_v2.json.

    python scripts/paper/naskah/buat_tables_v2.py

Membaca scripts/paper/revisi/hasil_v2 (atau JBV_NASKAH_V2). Satuan inferensi
sama dengan naskah sebelumnya: rata-rata per (seri, tanggal), kini 15 x 250 =
3.750 unit, bootstrap blok lima hari atas 250 tanggal, ekuivalensi +-2 persen,
Holm per keluarga. Ramalan random forest dirata-rata atas tiga seed sebelum
galatnya dihitung; sebaran antar-seed dilaporkan sendiri.

Keluaran mengandung ringkasan saja (rata-rata, persentase, statistik uji),
bukan nilai arus per hari, tetapi tetap disimpan di keluaran/ yang di-ignore.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

NASKAH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, NASKAH)
import inferensi as INF                                   # noqa: E402

REVISI = os.path.join(os.path.dirname(NASKAH), 'revisi')
H = os.environ.get('JBV_NASKAH_V2', os.path.join(REVISI, 'hasil_v2')).rstrip('/') + '/'
KEL = os.path.join(NASKAH, 'keluaran')
LEARNER = ['RandomForest', 'LightGBM', 'XGBoost']
T = {}

kf = json.load(open(H + 'v2_konfigurasi.json'))
R = pd.read_csv(H + 'v2_ramalan.csv', float_precision='round_trip')
sk = pd.read_csv(H + 'v2_skala.csv').drop_duplicates('leaf').set_index('leaf')
st = pd.read_csv(H + 'v2_setelan.csv').drop_duplicates(['leaf', 'model'], keep='last')
assert not R.duplicated(['leaf', 'blok', 'metode', 'lengan', 'seed', 'origin']).any(), 'baris ganda'
assert R.pred.notna().all(), 'ada ramalan kosong'
assert len(sk) == 15 and len(st) == 45
T['konfigurasi'] = kf
T['n_leaf'] = int(len(sk))
T['nroll'], T['nval'] = int(kf['nroll']), int(kf['nval'])

# ------------------------------------------------------------------ MASE
U = R[R.blok == 'uji']
rata = (U.groupby(['leaf', 'origin', 'metode', 'lengan'], as_index=False)
         .agg(pred=('pred', 'mean'), actual=('actual', 'first'), tanggal=('tanggal', 'first')))
for nm, kol in (('mase', 'den'), ('mase_penuh', 'den_penuh'), ('mase_2022', 'den_2022')):
    rata[nm] = (rata.actual - rata.pred).abs() / rata.leaf.map(sk[kol])
rata['ae'] = (rata.actual - rata.pred).abs()
M = rata.set_index(['leaf', 'origin', 'metode', 'lengan'])
tgl = rata.groupby('origin').tanggal.first()
T['tgl_uji_awal'], T['tgl_uji_akhir'] = str(tgl.iloc[0]), str(tgl.iloc[-1])
V0 = R[R.blok == 'val']
T['tgl_val_awal'] = str(V0.tanggal.min())
T['seri'] = {l: dict(mulai=r.mulai, s0=int(r.s0), n_latih=int(r.n_latih)) for l, r in sk.iterrows()}

utama = M.xs('utama', level='lengan')
mase_u = utama.mase.unstack('metode')
metode = list(mase_u.columns)
T['n_metode'] = len(metode)

# ------------------------------------------------------------------ 1. peringkat
peringkat = mase_u.mean().sort_values()
juara = str(peringkat.index[0])
T['juara'] = juara
T['peringkat'] = [dict(model=m, mase=float(v), med=float(mase_u[m].median()),
                       mase_penuh=float(utama.mase_penuh.unstack('metode')[m].mean()),
                       mase_2022=float(utama.mase_2022.unstack('metode')[m].mean()))
                  for m, v in peringkat.items()]
T['banding_juara'] = INF.holm([INF.banding(mase_u[juara], mase_u[m], m) for m in peringkat.index[1:]])
# Benjamini-Hochberg pada keluarga yang sama
_b = sorted(T['banding_juara'], key=lambda r: r['p'])
_m, _min = len(_b), 1.0
for i in range(_m - 1, -1, -1):
    _min = min(_min, _b[i]['p'] * _m / (i + 1))
    _b[i]['p_bh'] = _min
harian = mase_u.groupby(level='origin').mean()
_t, _p = INF.mcs(harian, alpha=0.10)
T['mcs'] = dict(tersisa=_t, p=_p)
for alt in ('mase_penuh', 'mase_2022'):
    T[f'urutan_{alt}'] = list(utama[alt].unstack('metode').mean().sort_values().index)

# Diebold-Mariano per seri: juara lawan setiap metode
T['dm_per_seri'] = []
for m in peringkat.index[1:]:
    lebih = kalah = 0
    for lf, g in mase_u.groupby(level='leaf'):
        s_, p_ = INF.dm_hln(g[juara].values, g[m].values)
        if p_ < 0.05:
            lebih += s_ > 0
            kalah += s_ < 0
    T['dm_per_seri'].append(dict(model=m, juara_lebih_baik=int(lebih), juara_lebih_buruk=int(kalah)))

# ------------------------------------------------------------------ 2. per seri
plm = mase_u.groupby(level='leaf').mean()
T['per_leaf_model'] = {l: {m: float(v) for m, v in r.items()} for l, r in plm.iterrows()}
T['winners'] = [dict(leaf=l, best=str(r.idxmin()), mase=float(r.min()),
                     fam='ML' if r.idxmin() in LEARNER else ('Linear' if r.idxmin() == 'Ridge' else 'lain'))
                for l, r in plm.iterrows()]
T['n_beat_rw'] = int(sum(plm.loc[l].min() < plm.loc[l]['Naive'] - 1e-12 for l in plm.index))
nol_uji = U[U.metode == 'Naive'].groupby('leaf').actual.apply(lambda a: float(100 * (a == 0).mean()))
T['nol_uji'] = nol_uji.to_dict()

# ------------------------------------------------------------------ 3. kombinasi dan pemilihan
P = rata[rata.lengan == 'utama'].pivot_table(index=['leaf', 'origin'], columns='metode', values='pred')
A = rata[rata.lengan == 'utama'].groupby(['leaf', 'origin']).actual.first()
den = P.index.get_level_values('leaf').map(sk['den']).values
ms = lambda pr: (pr - A).abs() / den

# validasi: learner memakai konfigurasi terpilih (seed pertama RF), benchmark 'utama'
V = V0.copy()
pil = st.set_index(['leaf', 'model']).cfg
V['pakai'] = (V.lengan == 'utama') | (V.lengan == [f"cfg{pil.get((l, m), -1) + 1}" for l, m in zip(V.leaf, V.metode)])
V = V[V.pakai]
V['mase'] = (V.actual - V.pred).abs() / V.leaf.map(sk['den_val'])
vm = V.groupby(['leaf', 'metode']).mase.mean().unstack()
assert set(vm.columns) == set(metode), 'validasi tidak memuat semua metode'
lima = {l: list(r.sort_values().index[:5]) for l, r in vm.iterrows()}
pilih = vm.idxmin(axis=1)
top5 = pd.concat([P.xs(l, level='leaf', drop_level=False)[lima[l]].mean(1) for l in P.index.levels[0]])
satu = pd.concat([P.xs(l, level='leaf', drop_level=False)[pilih[l]] for l in P.index.levels[0]])
KOMB = [('Mean of the three learners', P[LEARNER].mean(1)),
        (f'Mean of all {len(metode)} methods', P.mean(1)),
        (f'Median of all {len(metode)} methods', P.median(1)),
        ('Mean of the five best on validation, per series', top5.reindex(P.index))]
T['kombinasi'] = INF.holm([dict(INF.banding(ms(P[juara]), ms(pr), nama), mase=float(ms(pr).mean()),
                                med=float(ms(pr).median()),
                                seri_lebih_baik=int((ms(pr).groupby(level='leaf').mean()
                                                     < ms(P[juara]).groupby(level='leaf').mean()).sum()))
                           for nama, pr in KOMB])
T['pilih_per_seri'] = dict(pilihan=pilih.to_dict(), banding=INF.banding(ms(P[juara]), ms(satu.reindex(P.index)), 'selection'),
                           mase=float(ms(satu.reindex(P.index)).mean()),
                           n_learner=int(pilih.isin(LEARNER).sum()))

# ------------------------------------------------------------------ 4. lengan learner
def seri_lengan(nama, model=None):
    s = M.xs(nama, level='lengan').mase
    s = s[s.index.get_level_values('metode').isin([model] if model else LEARNER)]
    return s


def banding_lengan(nama, acuan, label=None, model=None):
    a, b = seri_lengan(acuan, model), seri_lengan(nama, model)
    return INF.banding(a, b, label or nama)


KOMP = {'tanpa_mrmr': 'Redundancy-aware selection', 'tanpa_refit': 'Daily re-fitting',
        'tanpa_setelan': 'Tuned hyperparameters'}
T['komponen'] = INF.holm([banding_lengan(k, 'utama', v) for k, v in KOMP.items()])
T['komponen_per_model'] = {v: {m: banding_lengan(k, 'utama', f'{v}, {m}', m) for m in LEARNER}
                           for k, v in KOMP.items()}
_ts = U[(U.lengan == 'tanpa_setelan') & (U.seed.astype(str).isin(['42', '0']))]
_salin = _ts.groupby(['leaf', 'metode']).salinan.max()
T['tuning_pasangan_berubah'] = int((_salin == 0).sum())
_berubah = set(_salin[_salin == 0].index)
_sel = lambda s: s[[(l, m) in _berubah for l, m in zip(s.index.get_level_values('leaf'), s.index.get_level_values('metode'))]]
T['tuning_bersyarat'] = INF.banding(_sel(seri_lengan('utama')), _sel(seri_lengan('tanpa_setelan')),
                                    'Tuned hyperparameters, changed pairs only')
T['cfg_terpilih'] = {m: [int((st[st.model == m].cfg == i).sum()) for i in range(4)] for m in LEARNER}

LK = {'k12': 'k = 12', 'k40': 'k = 40', 'k_semua': 'All candidates (no selection)'}
T['k'] = INF.holm([banding_lengan(k, 'k25', v) for k, v in LK.items()])
T['k_mase'] = {k: float(seri_lengan(k).mean()) for k in ('k12', 'k25', 'k40', 'k_semua')}
LP = {'pasar_ubah': 'Market data as daily changes', 'pasar_level': 'Market data as levels'}
T['pasar'] = INF.holm([banding_lengan(k, 'k25', v) for k, v in LP.items()])
T['pasar_per_model'] = {v: {m: banding_lengan(k, 'k25', f'{v}, {m}', m) for m in LEARNER} for k, v in LP.items()}
T['jendela'] = banding_lengan('jendela_2022', 'k25', 'Training from 2022 only')
_sel_pasar = M.xs('pasar_ubah', level='lengan').mase.groupby(level='leaf').mean() / \
    M.xs('k25', level='lengan').mase.groupby(level='leaf').mean() - 1
T['pasar_ubah_per_seri'] = {l: float(100 * v) for l, v in _sel_pasar.items()}

# ------------------------------------------------------------------ 5. seed RF
rf = U[(U.metode == 'RandomForest')].copy()
rf['mase'] = (rf.actual - rf.pred).abs() / rf.leaf.map(sk['den'])
per_seed = rf[rf.lengan == 'utama'].groupby('seed').mase.mean()
T['seed_rf'] = dict(mase=per_seed.to_dict(), rentang_persen=float(100 * (per_seed.max() / per_seed.min() - 1)))
eff = {}
for k, v in KOMP.items():
    a = rf[rf.lengan == 'utama'].groupby('seed').mase.mean()
    b = rf[rf.lengan == k].groupby('seed').mase.mean()
    eff[v] = {str(s): float(100 * (b[s] / a[s] - 1)) for s in a.index}
T['seed_rf']['efek_komponen'] = eff

# ------------------------------------------------------------------ 6. per kuartal
kw = pd.PeriodIndex(pd.to_datetime(tgl), freq='Q').astype(str)
kmap = dict(zip(tgl.index, kw))
q = mase_u.copy()
q['kuartal'] = [kmap[o] for o in q.index.get_level_values('origin')]
T['per_kuartal'] = {k: {m: float(v) for m, v in g.drop(columns='kuartal').mean().items()}
                    for k, g in q.groupby('kuartal')}
T['kuartal_n'] = {k: int(g.index.get_level_values('origin').nunique()) for k, g in q.groupby('kuartal')}
T['kuartal_juara'] = {k: min(v, key=v.get) for k, v in T['per_kuartal'].items()}
ref = seri_lengan('tanpa_refit').groupby(level='origin').mean() / seri_lengan('utama').groupby(level='origin').mean()
T['refit_per_kuartal'] = {k: float(100 * (seri_lengan('tanpa_refit')[[kmap[o] == k for o in seri_lengan('tanpa_refit').index.get_level_values('origin')]].mean()
                                          / seri_lengan('utama')[[kmap[o] == k for o in seri_lengan('utama').index.get_level_values('origin')]].mean() - 1))
                          for k in sorted(set(kw))}

# ------------------------------------------------------------------ 7. metrik operasional
rw = rata[(rata.lengan == 'utama') & (rata.metode == 'Naive')].set_index(['leaf', 'origin'])
jarang = str(max(T['nol_uji'], key=T['nol_uji'].get))


def desk(buang=()):
    out = []
    for m, g in rata[(rata.lengan == 'utama') & ~rata.leaf.isin(buang)].groupby('metode'):
        g = g.set_index(['leaf', 'origin'])
        prev = rw.pred.reindex(g.index)
        mae_s = g.ae.groupby(level='leaf').mean()
        rel = (mae_s / rw.ae.groupby(level='leaf').mean().reindex(mae_s.index)).replace([np.inf], np.nan).dropna()
        aa, ap = np.sign(g.actual - prev), np.sign(g.pred - prev)
        ok = (aa != 0) & (ap != 0)
        pt, ptp = INF.pesaran_timmermann(aa[ok], ap[ok]) if ok.sum() > 10 else (None, None)
        tot = g.groupby(level='origin')[['actual', 'pred']].sum()
        out.append(dict(model=m, rel_mae_geo=float(np.exp(np.log(rel[rel > 0]).mean())), mae=float(g.ae.mean()),
                        bias=float((g.actual - g.pred).mean()),
                        arah=float(100 * (aa[ok] == ap[ok]).mean()) if ok.sum() else None, pt=pt, pt_p=ptp,
                        mae_total=float((tot.actual - tot.pred).abs().mean())))
    out = sorted(out, key=lambda r: r['rel_mae_geo'])
    for i, r in enumerate(out):
        r['peringkat'] = i + 1
    return out


T['desk'] = desk()
T['desk_tanpa'] = dict(leaf=jarang, rows=desk((jarang,)))
_td = os.path.join(KEL, f"topdown_{T['nroll']}.json")
if os.path.exists(_td):
    td = pd.DataFrame(json.load(open(_td)))
    tot = rw.groupby(level='origin').actual.sum()
    assert np.allclose(tot.values, td.sort_values('origin').actual.values), 'total top-down tidak cocok'
    T['topdown'] = dict(arima=float((td.actual - td.arima).abs().mean()), rw=float((td.actual - td.rw).abs().mean()))
else:
    print(f'  {_td} belum ada - top-down dilewati')

# ------------------------------------------------------------------ 8. SHAP
_sv = os.path.join(KEL, 'shap_v2.json')
if os.path.exists(_sv):
    SV = json.load(open(_sv))
    fam = {}
    for fk in ('int', 'ubah'):
        for nm in ('RandomForest', 'LightGBM'):
            df = pd.DataFrame({l: v[fk][nm] for l, v in SV.items()}).fillna(0.0)
            fam[f'{fk}|{nm}'] = df.mean(axis=1).sort_values(ascending=False).to_dict()
    pasar = pd.DataFrame({l: {nm: v['ubah'][nm].get('Market', 0.0) for nm in ('RandomForest', 'LightGBM')}
                          for l, v in SV.items()}).T
    r_, p_ = spearmanr(pasar.RandomForest, pasar.LightGBM)
    T['shap'] = dict(famili=fam, pasar=pasar.to_dict(orient='index'), rho=float(r_), p=float(p_),
                     n_ext={l: v['ubah']['n_ext'] for l, v in SV.items()},
                     n_lag={l: v['int']['n_lag'] for l, v in SV.items()},
                     kelompok={nm: {g: float(pasar[nm][pasar.index.str[0] == g].mean()) for g in 'ABC'}
                               for nm in ('RandomForest', 'LightGBM')})
    if all('level' in v for v in SV.values()):
        lv_ = pd.DataFrame({l: {nm: v['level'][nm].get('Market', 0.0) for nm in ('RandomForest', 'LightGBM')}
                            for l, v in SV.items()}).T
        T['shap']['level'] = dict(pasar=lv_.to_dict(orient='index'), n_ext={l: v['level']['n_ext'] for l, v in SV.items()},
                                  kelompok={nm: {g: float(lv_[nm][lv_.index.str[0] == g].mean()) for g in 'ABC'}
                                            for nm in ('RandomForest', 'LightGBM')},
                                  rata={nm: float(lv_[nm].mean()) for nm in ('RandomForest', 'LightGBM')})
    rr, pp = spearmanr([T['shap']['pasar'][l]['RandomForest'] for l in _sel_pasar.index], _sel_pasar.values)
    T['shap']['vs_efek'] = dict(rho=float(rr), p=float(pp))
else:
    print(f'  {_sv} belum ada - SHAP dilewati')

# ================================================================ review ketujuh
UNIV = ['Naive', 'NaiveDrift', 'NaiveMean', 'SeasonalNaive', 'Croston', 'SeasonalDecomp', 'ARIMA', 'ETS', 'Theta', 'Prophet']
BEDA = [m for m in metode if m not in ('Theta', 'NaiveDrift')]      # buang duplikat praktis
_ref = ms(P[juara])
_med_all = ms(P.median(1))
T['median_varian'] = INF.holm([
    dict(INF.banding(_ref, ms(P[UNIV].median(1)), 'Median of the ten univariate methods'), mase=float(ms(P[UNIV].median(1)).mean())),
    dict(INF.banding(_ref, ms(P[BEDA].median(1)), f'Median of {len(BEDA)} distinct methods'), mase=float(ms(P[BEDA].median(1)).mean()))])
T['median_univ_vs_semua'] = INF.banding(_med_all, ms(P[UNIV].median(1)), 'univariate median vs all-method median')
_ed = P[['ETS', 'Theta']]
T['duplikat'] = dict(ets_theta_maks=float((_ed.ETS - _ed.Theta).abs().max()),
                     ets_theta_kor=float(_ed.corr().iloc[0, 1]),
                     rw_rwd_maks=float((P.Naive - P.NaiveDrift).abs().max()))

# Ridge tanpa penjaga: ramalan VPS asli, sebelum ridge_ulang.py
_lama = os.path.join(H, 'v2_ramalan_ridge_lama.csv')
if os.path.exists(_lama):
    RL = pd.read_csv(_lama, float_precision='round_trip')
    RL = RL[(RL.blok == 'uji') & (RL.metode == 'Ridge')].set_index(['leaf', 'origin'])
    baru = U[(U.metode == 'Ridge')].set_index(['leaf', 'origin'])
    ml = (RL.actual - RL.pred).abs() / RL.index.get_level_values('leaf').map(sk['den']).values
    mb = (baru.actual - baru.pred).abs() / baru.index.get_level_values('leaf').map(sk['den']).values
    beda_ = (RL.pred - baru.pred.reindex(RL.index)).abs() > 1e-9
    terburuk = ml.idxmax()
    T['ridge_tanpa_penjaga'] = dict(mase=float(ml.mean()), mase_tanpa_satu=float(ml.drop(terburuk).mean()),
                                    mase_baru=float(mb.mean()), n_berubah=int(beda_.sum()), n=int(len(ml)),
                                    leaf_terburuk=str(terburuk[0]), mase_terburuk=float(ml.max()),
                                    banding_lgbm_tanpa_satu=float(100 * (ml.drop(terburuk).mean() / mase_u['LightGBM'].drop(terburuk).mean() - 1)))

# per kuartal untuk semua perbandingan utama
def _perk(a, b):
    o = a.index.get_level_values('origin')
    out = {}
    for q in sorted(set(kw)):
        msk = np.array([kmap[x] == q for x in o])
        out[q] = float(100 * (b[msk].mean() / a[msk].mean() - 1))
    return out


T['kuartal_banding'] = {
    'Median of all methods vs leader': _perk(_ref, _med_all),
    'ARIMA vs leader': _perk(mase_u[juara], mase_u['ARIMA']),
    'LightGBM vs leader': _perk(mase_u[juara], mase_u['LightGBM']),
    **{f'Without {v.lower()}': _perk(seri_lengan('utama'), seri_lengan(k)) for k, v in KOMP.items()},
    'k = 12': _perk(seri_lengan('k25'), seri_lengan('k12')),
    'All candidates': _perk(seri_lengan('k25'), seri_lengan('k_semua')),
    'Market data as changes': _perk(seri_lengan('k25'), seri_lengan('pasar_ubah')),
    'Market data as levels': _perk(seri_lengan('k25'), seri_lengan('pasar_level')),
    'Training from 2022 only': _perk(seri_lengan('k25'), seri_lengan('jendela_2022')),
}

# jendela 30 hari (panjang blok desain lama): siapa unggul, efek refit, median
_o = mase_u.index.get_level_values('origin')
_jw = []
for a0 in range(0, T['nroll'] - 29, 30):
    msk = (_o >= a0) & (_o < a0 + 30)
    m = mase_u[msk].mean()
    fo = seri_lengan('utama'); no = seri_lengan('tanpa_refit')
    mo = (fo.index.get_level_values('origin') >= a0) & (fo.index.get_level_values('origin') < a0 + 30)
    _jw.append(dict(awal=str(tgl.iloc[a0]), akhir=str(tgl.iloc[a0 + 29]), juara=str(m.idxmin()),
                    arima_vs_lgbm=float(100 * (m['ARIMA'] / m['LightGBM'] - 1)),
                    refit=float(100 * (no[mo].mean() / fo[mo].mean() - 1)),
                    median_vs_terbaik=float(100 * (_med_all[msk].mean() / m.min() - 1))))
# 30 origin terakhir: tanggal yang sama dengan blok uji desain lama
msk = _o >= T['nroll'] - 30
m = mase_u[msk].mean()
T['tiga_puluh_terakhir'] = dict(urutan=list(m.sort_values().index[:5]),
                                arima_vs_lgbm=float(100 * (m['ARIMA'] / m['LightGBM'] - 1)),
                                awal=str(tgl.iloc[-30]))
T['jendela30'] = _jw

# per seri: pasar level, jendela 2022, dan DM pasar perubahan
def _per_seri(k, acuan='k25'):
    a = seri_lengan(acuan).groupby(level='leaf').mean(); b = seri_lengan(k).groupby(level='leaf').mean()
    return {l: float(100 * (b[l] / a[l] - 1)) for l in a.index}


T['pasar_level_per_seri'] = _per_seri('pasar_level')
T['jendela_per_seri'] = _per_seri('jendela_2022')
_dmp = {}
for l in sorted(T['per_leaf_model']):
    a = seri_lengan('k25').xs(l, level='leaf').groupby(level='origin').mean()
    b = seri_lengan('pasar_ubah').xs(l, level='leaf').groupby(level='origin').mean()
    st_, p_ = INF.dm_hln(b.values, a.values)          # positif = tanpa pasar lebih buruk
    _dmp[l] = dict(stat=float(st_), p=float(p_), delta=T['pasar_ubah_per_seri'][l])
T['dm_pasar_ubah'] = _dmp
T['hl_pasar_level'] = next(r for r in T['pasar'] if r['label'] == 'Market data as levels')['hl']

# lengan tambahan (tambahan_v2.py, dihitung lokal)
_tb = [p_ for p_ in [H + 'v2_tambahan.csv'] + sorted(__import__('glob').glob(H + 'v2_tambahan.shard-*.csv')) if os.path.exists(p_)]
if _tb:
    TB = pd.concat([pd.read_csv(p_, float_precision='round_trip') for p_ in _tb]).drop_duplicates(['leaf', 'metode', 'lengan', 'origin'])
    TB['mase'] = (TB.actual - TB.pred).abs() / TB.leaf.map(sk['den'])
    tb = TB.set_index(['leaf', 'origin', 'metode', 'lengan']).mase
    lengkap = TB.groupby('lengan').leaf.nunique().to_dict()
    T['tambahan_lengkap'] = lengkap
    if all(v == T['n_leaf'] for v in lengkap.values()):
        rid = mase_u['Ridge']
        T['ridge_varian'] = INF.holm([
            dict(INF.banding(rid, tb.xs(('Ridge', k), level=['metode', 'lengan']), lab), mase=float(tb.xs(('Ridge', k), level=['metode', 'lengan']).mean()))
            for k, lab in (('ridge_lag', 'Own lags only (18 lags)'), ('ridge_kal', 'Calendar as dummies, same 25 features'),
                           ('ridge_semua', 'All 116 candidates, calendar as dummies'))])
        lg = mase_u['LightGBM']
        T['loss_varian'] = INF.holm([
            dict(INF.banding(lg, tb.xs(('LightGBM', k), level=['metode', 'lengan']), lab), mase=float(tb.xs(('LightGBM', k), level=['metode', 'lengan']).mean()))
            for k, lab in (('loss_l1', 'LightGBM, absolute loss'), ('loss_huber', 'LightGBM, Huber loss'))])

# versi pustaka: jalan v2 di VPS, dan lingkungan lokal tempat Ridge dan SHAP v2 dihitung ulang
T['versi'] = json.load(open(H + 'versi.json')) if os.path.exists(H + 'versi.json') else {}
import platform, sklearn, lightgbm, shap as _shap                     # noqa: E402
import numpy as _np, pandas as _pd                                    # noqa: E402
T['versi_lokal'] = dict(python=platform.python_version(), numpy=_np.__version__, pandas=_pd.__version__, sklearn=sklearn.__version__,
                        lightgbm=lightgbm.__version__, shap=_shap.__version__)
json.dump(T, open(os.path.join(KEL, 'tables_v2.json'), 'w'), indent=1, default=float)
print(f"ditulis tables_v2.json  juara {juara}  ({T['n_leaf']} seri x {T['nroll']} origin)")
for r in T['peringkat'][:8]:
    print(f"  {r['model']:15s} {r['mase']:.3f}")
