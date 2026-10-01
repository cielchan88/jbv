"""Ringkasan dan pemeriksaan hasil jalan ulang v2 - v2_ringkas.json.

    JBV_HASIL=hasil_v2 python scripts/paper/revisi/ringkas_v2.py

Memeriksa kelengkapan (setiap sel punya jumlah origin penuh, tidak ada baris
ganda, tidak ada ramalan kosong yang tak dilaporkan), lalu menghitung angka
yang akan dipakai naskah. Semua inferensi memakai satuan yang sama dengan
naskah sekarang: rata-rata per (seri, tanggal), bootstrap blok atas tanggal,
ekuivalensi +-2 persen (lihat scripts/paper/naskah/inferensi.py).

MASE memakai penyebut dari laporan pertama sampai awal blok uji (kolom den di
v2_skala.csv). Ramalan random forest dirata-rata atas tiga seed untuk
perbandingan antar-lengan; sebaran antar-seed dilaporkan terpisah.
"""
import json
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
sys.path.insert(0, os.path.join(os.path.dirname(DIR), 'naskah'))
os.environ.setdefault('JBV_PANEL', 'data/processed/sdv-wide-gabung.csv')
os.environ.setdefault('JBV_HASIL', 'hasil_v2')
os.environ.setdefault('JBV_NVAL', '60')
os.environ['JBV_BACA_SAJA'] = '1'
from h1_common import HASIL, baca, tolak_shard   # noqa: E402
import numpy as np                                  # noqa: E402
import pandas as pd                                 # noqa: E402
import inferensi as INF                             # noqa: E402

LEARNER = ['RandomForest', 'LightGBM', 'XGBoost']


def main():
    tolak_shard('ringkas_v2.py')
    kf = json.load(open(HASIL + 'v2_konfigurasi.json'))
    R = baca(HASIL + 'v2_ramalan.csv')
    sk = baca(HASIL + 'v2_skala.csv').drop_duplicates('leaf').set_index('leaf')
    st = baca(HASIL + 'v2_setelan.csv').drop_duplicates(['leaf', 'model'], keep='last')
    assert len(R), 'v2_ramalan.csv kosong'
    kunci = ['leaf', 'blok', 'metode', 'lengan', 'seed', 'origin']
    ganda = int(R.duplicated(kunci).sum())
    assert ganda == 0, f'{ganda} baris ganda - satukan shard dengan gabung_shard.py dulu'

    # ---------------------------------------------------------- kelengkapan
    n_blok = {'uji': kf['nroll'], 'val': kf['nval']}
    sel = R.groupby(['leaf', 'blok', 'metode', 'lengan', 'seed']).origin.nunique().reset_index()
    kurang = sel[sel.origin != sel.blok.map(n_blok)]
    kosong = R[R.pred.isna()].groupby(['metode']).size().to_dict()
    print(f'sel: {len(sel)}, tidak lengkap: {len(kurang)}, ramalan kosong: {kosong or 0}')

    # ---------------------------------------------------------- MASE
    R['mase'] = (R.actual - R.pred).abs() / R.leaf.map(sk['den'])
    R['mase_penuh'] = (R.actual - R.pred).abs() / R.leaf.map(sk['den_penuh'])
    U = R[R.blok == 'uji']
    # random forest: rata-rata ramalan atas seed dulu, baru galatnya
    rata = (U.groupby(['leaf', 'origin', 'metode', 'lengan'], as_index=False)
             .agg(pred=('pred', 'mean'), actual=('actual', 'first')))
    rata['mase'] = (rata.actual - rata.pred).abs() / rata.leaf.map(sk['den'])
    M = rata.set_index(['leaf', 'origin', 'metode', 'lengan']).mase

    utama = M.xs('utama', level='lengan').unstack('metode')
    peringkat = utama.mean().sort_values()
    juara = str(peringkat.index[0])
    out = dict(konfigurasi=kf, n_sel=int(len(sel)), sel_tidak_lengkap=int(len(kurang)),
               ramalan_kosong=kosong, juara=juara,
               peringkat=[dict(metode=m, mase=float(v), median=float(utama[m].median()))
                          for m, v in peringkat.items()])
    out['banding_juara'] = [INF.banding(utama[juara], utama[m], m) for m in utama.columns if m != juara]
    INF.holm(out['banding_juara'])

    # MCS pada rata-rata harian
    harian = utama.groupby(level='origin').mean()
    tersisa, p = INF.mcs(harian, alpha=0.10)
    out['mcs'] = dict(tersisa=tersisa, p=p)

    # ---------------------------------------------------------- seed RF
    rf = U[(U.metode == 'RandomForest') & (U.lengan == 'utama')]
    per_seed = rf.groupby('seed').apply(lambda g: float(((g.actual - g.pred).abs() / g.leaf.map(sk['den'])).mean()))
    out['seed_rf'] = dict(mase_per_seed=per_seed.to_dict(),
                          rentang_persen=float(100 * (per_seed.max() / per_seed.min() - 1)))

    # ---------------------------------------------------------- lengan
    def lengan(nama, acuan):
        a = M.xs(acuan, level='lengan').unstack('metode')[LEARNER].stack()
        b = M.xs(nama, level='lengan').unstack('metode')[LEARNER].stack()
        a.index.names = b.index.names = ['leaf', 'origin', 'metode']
        return INF.banding(a, b, nama)

    out['komponen'] = INF.holm([lengan(x, 'utama') for x in ('tanpa_mrmr', 'tanpa_refit', 'tanpa_setelan')])
    out['k'] = INF.holm([lengan(x, 'k25') for x in ('k12', 'k40', 'k_semua')])
    out['pasar'] = INF.holm([lengan(x, 'k25') for x in ('pasar_ubah', 'pasar_level')])
    out['jendela'] = [lengan('jendela_2022', 'k25')]

    # ---------------------------------------------------------- kombinasi
    P = rata[rata.lengan == 'utama'].pivot_table(index=['leaf', 'origin'], columns='metode', values='pred')
    A = rata[rata.lengan == 'utama'].groupby(['leaf', 'origin']).actual.first()
    den = P.index.get_level_values('leaf').map(sk['den']).values
    ms = lambda pr: (pr - A).abs() / den
    komb = {'Mean of the three learners': P[LEARNER].mean(1),
            'Mean of all methods': P.mean(1), 'Median of all methods': P.median(1)}
    out['kombinasi'] = INF.holm([INF.banding(ms(P[juara]), ms(v), k) for k, v in komb.items()])

    # ---------------------------------------------------------- pemilihan per seri di validasi
    V = R[(R.blok == 'val')].copy()
    V = V[(V.lengan == 'utama') | V.lengan.str.startswith('cfg')]
    pil = st.set_index(['leaf', 'model']).cfg
    V = V[(V.lengan == 'utama') | (V.lengan == V.apply(lambda r: f"cfg{pil.get((r.leaf, r.metode), -1) + 1}", axis=1))]
    vm = V.groupby(['leaf', 'metode']).mase.mean().unstack()
    pilih = vm.idxmin(axis=1)
    terpilih = pd.concat([utama.xs(l, level='leaf', drop_level=False)[m] for l, m in pilih.items()])
    out['pilih_per_seri'] = dict(pilihan=pilih.to_dict(),
                                 banding=INF.banding(utama[juara], terpilih, 'per-series selection'))

    # ---------------------------------------------------------- per sub-periode
    tg = U.groupby('origin').tanggal.first()
    kw = pd.PeriodIndex(pd.to_datetime(tg), freq='Q')
    out['per_kuartal'] = {str(q): {m: float(utama[m][utama.index.get_level_values('origin').isin(tg.index[kw == q])].mean())
                                   for m in peringkat.index[:6]} for q in sorted(set(kw))}

    json.dump(out, open(HASIL + 'v2_ringkas.json', 'w'), indent=1, default=float)
    print(f'juara {juara}; peringkat:')
    for r in out['peringkat']:
        print(f"  {r['metode']:15s} {r['mase']:.3f}")
    for f in ('komponen', 'k', 'pasar', 'jendela', 'kombinasi'):
        for r in out[f]:
            print(f"  {f:9s} {r['label']:28s} {r['delta']:+6.2f}% [{r['lo95']:.2f}, {r['hi95']:.2f}]"
                  f"  setara+-2: {r['setara']}")
    print(f"  seed RF: rentang {out['seed_rf']['rentang_persen']:.2f}%")
    print(f"  MCS: {tersisa}")
    print('ditulis', HASIL + 'v2_ringkas.json')


if __name__ == '__main__':
    main()
