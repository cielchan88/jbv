"""Jalan ulang v2 - desain yang diminta review ketiga, dalam SATU jalan.

    JBV_HASIL=hasil_v2 python scripts/paper/revisi/rerun_v2.py          # satu proses
    python scripts/paper/revisi/vps.py mulai --rencana v2                # di VPS, paralel

APA YANG BERUBAH DARI JALAN SEBELUMNYA (hasil_w5)

  1. Blok uji 250 origin (bukan 30), blok validasi 60 origin di depannya.
  2. Fitur pasar sebagai PERUBAHAN harian: kurs dan NDF memakai harga tengah
     (rata-rata bid dan ask) sebagai log-return, imbal hasil sebagai selisih,
     DXY dan IHSG sebagai log-return, arus ekuitas nonresiden apa adanya (sudah
     berupa arus). Lengan level lama tetap ada sebagai pembanding.
  3. Lengan tanpa seleksi fitur: seluruh kandidat internal (k = semua).
  4. Tiga seed untuk random forest. LightGBM dan XGBoost dengan setelan grid
     ini DETERMINISTIK - random_state tidak mengubah satu bit pun ramalannya
     (diuji: selisih maksimum 0,0) - jadi seed ganda untuk keduanya hanya
     membuang waktu. Variansnya nol, bukan tidak diukur.
  5. Pelatihan dimulai dari LAPORAN PERTAMA tiap seri (nol struktural sebelum
     kategori masuk kerangka pelaporan dibuang), dan penyebut MASE dihitung
     dari periode yang sama. Lengan jendela geser: hanya data sejak 2022.
  6. Benchmark tambahan: ETS (tren aditif teredam), Theta, seasonal naive
     (lima hari kerja) dan regresi ridge pada fitur terpilih yang sama.
  7. Ramalan blok validasi untuk SEMUA metode, supaya pemilihan metode per
     seri bisa dipilih di validasi dan dinilai di blok uji.

LENGAN LEARNER (setiap learner, setelan terpilih kecuali disebut lain)

  harian   utama          mRMR, k = 25, refit setiap origin
           tanpa_mrmr     seleksi univariat (beta = 0)
           tanpa_setelan  konfigurasi 1 (disalin dari utama kalau terpilih = 1)
           tanpa_refit    fit sekali per sub-blok 30 origin
  mingguan k12 k25 k40 k_semua            jumlah fitur, refit tiap 5 origin
           pasar_ubah pasar_level         data pasar, k = 25
           jendela_2022                   latih hanya sejak 2022
  Lengan mingguan dibandingkan dengan k25 (mingguan), bukan dengan utama,
  supaya kedua sisi perbandingan memakai jadwal refit yang sama.

KENAPA BINGKAI FITUR DIBANGUN SEKALI. Semua fitur menoleh ke belakang (baris t
hanya memakai nilai sampai t-1), jadi bingkai seri penuh yang diiris sama
persis dengan bingkai yang dibangun dari riwayat terpotong - lihat
cache_fitur.py, diuji bit-identik. Baris t bingkai itu juga persis baris yang
dipakai untuk meramal t satu langkah ke depan.

CHECKPOINT. Satu sel = (leaf, blok, metode, lengan, seed). Sel ditulis begitu
selesai dan dilewati saat dijalankan ulang, jadi mati di tengah hanya
kehilangan satu sel.

UJI CEPAT. JBV_V2_CEPAT=1 memperpendek blok (uji 10, validasi 5) dan cukup
dengan JBV_LEAF=A.2.d untuk satu seri - untuk memeriksa skrip, bukan hasil.
"""
import gc
import json
import os
import sys
import time
import warnings

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
os.environ.setdefault('JBV_PANEL', 'data/processed/sdv-wide-gabung.csv')
os.environ.setdefault('JBV_HASIL', 'hasil_v2')
os.environ.setdefault('JBV_NVAL', '60')
from h1_common import *          # noqa: F403,E402  (chdir ke akar repo)

warnings.filterwarnings('ignore')

from sklearn.ensemble import RandomForestRegressor          # noqa: E402
from sklearn.linear_model import RidgeCV                    # noqa: E402
from lightgbm import LGBMRegressor                          # noqa: E402
from xgboost import XGBRegressor                            # noqa: E402
from statsmodels.tsa.holtwinters import ExponentialSmoothing  # noqa: E402
from statsmodels.tsa.forecasting.theta import ThetaModel    # noqa: E402
from utils.feature_engineering_optimized import (create_features_optimized,       # noqa: E402
                                                 select_top_features_optimized)
from utils.forecasting import (ARIMAForecaster, APUVAForecaster,                  # noqa: E402
                               CrostonForecaster, NaiveForecaster, ProphetForecaster)
import logging                                                                    # noqa: E402

# Prophet mencetak dua baris per fit (cmdstanpy), statsmodels memperingatkan
# p-value KPSS di luar tabel: 15 seri x 310 origin membuat log tak terbaca.
logging.getLogger('cmdstanpy').setLevel(logging.WARNING)
logging.getLogger('prophet').setLevel(logging.WARNING)
warnings.filterwarnings('ignore')

CEPAT = os.environ.get('JBV_V2_CEPAT') == '1'
NROLL = 10 if CEPAT else int(os.environ.get('JBV_V2_NROLL', '250'))
NVAL = 5 if CEPAT else int(os.environ.get('JBV_NVAL', '60'))
MINGGU = 5            # refit lengan mingguan
SUBBLOK = 30          # lengan tanpa refit: satu fit per 30 origin, seperti jalan lama
SEED_RF = (42, 1, 2)       # 42 = seed jalan lama, jadi seed pertama mereproduksi pipeline lama
K_UTAMA = 25
K_LENGAN = (12, 25, 40, 'semua')
AWAL_2022 = '2022-01-01'
MIN_NOL_STRUKTURAL = 250   # aturan yang sama dengan koreksi skala di naskah

GRID = {
    'RandomForest': [dict(n_estimators=100, max_depth=10), dict(n_estimators=300, max_depth=10),
                     dict(n_estimators=300, max_depth=None), dict(n_estimators=100, max_depth=4)],
    'LightGBM': [dict(n_estimators=100, learning_rate=0.05, max_depth=5),
                 dict(n_estimators=400, learning_rate=0.02, max_depth=5),
                 dict(n_estimators=100, learning_rate=0.10, max_depth=3),
                 dict(n_estimators=400, learning_rate=0.05, max_depth=8)],
    'XGBoost': [dict(n_estimators=100, max_depth=5, learning_rate=0.05),
                dict(n_estimators=400, max_depth=5, learning_rate=0.02),
                dict(n_estimators=100, max_depth=3, learning_rate=0.10),
                dict(n_estimators=400, max_depth=8, learning_rate=0.05)],
}
LEARNER = list(GRID)
BENCH = ['Naive', 'NaiveMean', 'NaiveDrift', 'SeasonalNaive', 'Croston', 'SeasonalDecomp',
         'ARIMA', 'ETS', 'Theta', 'Prophet', 'Ridge']

OUT = jalur('v2_ramalan.csv')
TUNE = jalur('v2_setelan.csv')
SKALA = jalur('v2_skala.csv')


# ------------------------------------------------------------------ konfigurasi
def sidik():
    return dict(nroll=NROLL, nval=NVAL, minggu=MINGGU, subblok=SUBBLOK, seed_rf=list(SEED_RF),
                k_utama=K_UTAMA, k_lengan=[str(k) for k in K_LENGAN], awal_2022=AWAL_2022,
                benchmark=BENCH, cepat=CEPAT)


def periksa_sidik():
    p = HASIL + 'v2_konfigurasi.json'
    if not os.path.exists(p):
        json.dump(sidik(), open(p, 'w'), indent=1)
        return
    lama = json.load(open(p))
    if lama != sidik():
        print('BERHENTI: desain v2 di folder ini berbeda dari skrip.', file=sys.stderr)
        for k in sidik():
            if lama.get(k) != sidik()[k]:
                print(f'  {k}: folder {lama.get(k)}  sekarang {sidik()[k]}', file=sys.stderr)
        print('  Pakai folder lain: JBV_HASIL=hasil_v2_<nama> ...', file=sys.stderr)
        sys.exit(2)


# ------------------------------------------------------------------ data pasar
def pasar():
    """Dua versi data pasar, keduanya sejajar tanggal dengan panel.

    level  : delapan kolom apa adanya, seperti jalan sebelumnya.
    ubah   : enam variabel sebagai perubahan harian (lihat docstring modul).
    Nilai hilang diisi ke depan SEBELUM perubahan dihitung, jadi hari tanpa
    kuotasi menjadi perubahan nol, bukan lompatan dua hari.
    """
    e = pd.read_excel(EXT)
    e['Tanggal'] = pd.to_datetime(e['Tanggal'])
    e = e.sort_values('Tanggal').reset_index(drop=True)
    kol = [c for c in e.columns if c != 'Tanggal']
    lv = e[kol].ffill().bfill()
    level = {c: lv[c].values for c in kol}
    mid_spot = (lv.bid_usdidr + lv.ask_usdidr) / 2
    mid_ndf = (lv.bid_ndf1m + lv.ask_ndf1m) / 2
    ubah = {
        'usdidr_mid_ret': np.log(mid_spot).diff(),
        'ndf1m_mid_ret': np.log(mid_ndf).diff(),
        'yield10y_chg': lv.yield_sbn_10year.diff(),
        'dxy_ret': np.log(lv.dxy).diff(),
        'jci_ret': np.log(lv.jci_index).diff(),
        'flows_nr_eq': lv.flows_nr_eq,
    }
    ubah = {k: v.fillna(0.0).values for k, v in ubah.items()}
    return level, ubah, e['Tanggal'].values


# ------------------------------------------------------------------ penulisan
def sudah():
    d = baca(OUT)
    kunci = ['leaf', 'blok', 'metode', 'lengan', 'seed']
    if not len(d):
        return set()
    return set(map(tuple, d[kunci].drop_duplicates().astype(str).values))


KOLOM_OUT = ['leaf', 'blok', 'origin', 'tanggal', 'metode', 'lengan', 'seed', 'pred', 'actual', 'cfg', 'salinan']


def tulis(path, rows):
    """Append dengan susunan kolom TETAP: CSV yang di-append tidak punya
    header kedua, jadi baris dengan kolom tambahan akan bergeser."""
    if rows:
        df = pd.DataFrame(rows)
        if path == OUT:
            df = df[KOLOM_OUT]
        df.to_csv(path, mode='a', header=not os.path.exists(path), index=False)


# ------------------------------------------------------------------ satu seri
class Seri:
    """Satu leaf: data sejak laporan pertama, bingkai fitur, blok, penyebut."""

    def __init__(self, r, dcols, dall, pasar_level, pasar_ubah, tgl_pasar):
        d, y = series_of(r, dcols, dall)
        nz = np.nonzero(y)[0]
        self.s0 = int(nz[0]) if len(nz) and nz[0] >= MIN_NOL_STRUKTURAL else 0
        self.leaf = r['Row_ID']
        self.d, self.y = d[self.s0:], y[self.s0:]
        self.d_penuh, self.y_penuh = d, y
        N = len(self.y)
        self.uji0 = N - NROLL
        self.val0 = self.uji0 - NVAL
        assert self.val0 > 500, f'{self.leaf}: riwayat terlalu pendek'
        df = pd.DataFrame({'ds': self.d, 'y': self.y})
        self.F = {'int': create_features_optimized(df)}
        self.F['level'] = create_features_optimized(df, external_series=pasar_level,
                                                    external_series_dates=tgl_pasar)
        self.F['ubah'] = create_features_optimized(df, external_series=pasar_ubah,
                                                   external_series_dates=tgl_pasar)
        for k, f in self.F.items():
            assert len(f) == N, f'{self.leaf}/{k}: bingkai {len(f)} baris, seri {N}'
            f.reset_index(drop=True, inplace=True)
        self.kand_int = [c for c in self.F['int'].columns if c not in ('ds', 'date', 'value')]
        tgl = pd.DatetimeIndex(self.d)
        self.mulai_2022 = int(np.argmax(tgl >= pd.Timestamp(AWAL_2022)))
        # Penyebut MASE: dari laporan pertama sampai awal blok (utama), juga
        # versi seluruh riwayat dan versi sejak 2022 untuk perbandingan.
        cut_penuh = len(self.y_penuh) - NROLL
        self.den = scale_denom(self.y[:self.uji0])
        self.den_penuh = scale_denom(self.y_penuh[:cut_penuh])
        self.den_2022 = scale_denom(self.y[self.mulai_2022:self.uji0])
        self.den_val = scale_denom(self.y[:self.val0])
        self._sel = {}

    def pilih(self, fk, t, k, beta):
        """Fitur terpilih pada data latih baris < t (cache per origin)."""
        if k == 'semua':
            return self.kand_int
        kunci = (fk, t, k, beta)
        if kunci not in self._sel:
            top, _ = select_top_features_optimized(self.F[fk].iloc[:t], top_k=k, mrmr_beta=beta)
            self._sel[kunci] = list(top)
        return self._sel[kunci]

    def lupakan_seleksi(self):
        self._sel.clear()

    def rentang(self, blok):
        return range(self.val0, self.uji0) if blok == 'val' else range(self.uji0, len(self.y))

    def baris(self, blok, t, metode, lengan, seed, pred, extra=None):
        r = dict(leaf=self.leaf, blok=blok, origin=t - (self.val0 if blok == 'val' else self.uji0),
                 tanggal=str(pd.Timestamp(self.d[t]).date()), metode=metode, lengan=lengan,
                 seed=seed, pred=float(pred), actual=float(self.y[t]), cfg=np.nan, salinan=0)
        if extra:
            assert set(extra) <= set(r), f'kolom tak dikenal: {set(extra) - set(r)}'
            r.update(extra)
        return r


def model(nama, cfg, seed):
    if nama == 'RandomForest':
        return RandomForestRegressor(random_state=seed, n_jobs=1, **cfg)
    if nama == 'LightGBM':
        return LGBMRegressor(random_state=42, verbose=-1, n_jobs=1, **cfg)
    return XGBRegressor(random_state=42, verbosity=0, n_jobs=1, **cfg)


def ramal_learner(S, nama, cfg, seed, blok, fk='int', k=K_UTAMA, beta=1.0, jadwal=1, latih0=0):
    """Ramalan satu langkah di sepanjang blok.

    jadwal = 1 berarti refit setiap origin. jadwal > 1: model di-fit di origin
    pertama tiap kelompok lalu dipakai untuk origin berikutnya dengan fitur
    yang diperbarui dari riwayat aktual. latih0: baris latih pertama (jendela).
    """
    F = S.F[fk]
    out, m, kol = [], None, None
    rg = list(S.rentang(blok))
    for i, t in enumerate(rg):
        if i % jadwal == 0:
            kol = S.pilih(fk, t, k, beta)
            if latih0:
                # Seleksi juga hanya melihat jendela yang dilatih.
                top, _ = select_top_features_optimized(F.iloc[latih0:t], top_k=k, mrmr_beta=beta)
                kol = list(top)
            del m
            m = model(nama, cfg, seed).fit(F[kol].values[latih0:t], F['value'].values[latih0:t])
        out.append(float(m.predict(F[kol].values[t:t + 1])[0]))
    del m
    gc.collect()
    return rg, out


def ramal_bench(S, nama, blok):
    """Benchmark statistik, refit di setiap origin pada data sejak laporan pertama."""
    d, y = S.d, S.y
    rg, out = list(S.rentang(blok)), []
    for t in rg:
        try:
            if nama == 'SeasonalNaive':
                p = y[t - MINGGU]
            elif nama == 'ETS':
                p = ExponentialSmoothing(y[:t], trend='add', damped_trend=True,
                                         initialization_method='estimated').fit().forecast(1)[0]
            elif nama == 'Theta':
                p = ThetaModel(y[:t], period=MINGGU, deseasonalize=False).fit().forecast(1)
                p = float(np.asarray(p).ravel()[0])
            elif nama == 'Ridge':
                kol = S.pilih('int', t, K_UTAMA, 1.0)
                X = S.F['int'][kol].values
                mu, sd = X[:t].mean(0), X[:t].std(0) + 1e-12
                rm = RidgeCV(alphas=np.logspace(-3, 3, 13)).fit((X[:t] - mu) / sd, y[:t])
                p = rm.predict((X[t:t + 1] - mu) / sd)[0]
            else:
                m = {'Naive': lambda: NaiveForecaster(method='last'),
                     'NaiveMean': lambda: NaiveForecaster(method='mean'),
                     'NaiveDrift': lambda: NaiveForecaster(method='drift'),
                     'Croston': CrostonForecaster, 'ARIMA': ARIMAForecaster,
                     'Prophet': ProphetForecaster,
                     'SeasonalDecomp': lambda: APUVAForecaster(row_id=S.leaf)}[nama]()
                m.fit(d[:t], y[:t])
                v, _ = m.predict(d[:t], y[:t], 1)
                p = float(np.asarray(v).ravel()[0])
        except Exception as e:                       # satu origin gagal, sel tetap jalan
            print(f'      {S.leaf}/{nama} origin {t}: {type(e).__name__}', flush=True)
            p = np.nan
        out.append(float(p))
    return rg, out


# ------------------------------------------------------------------ alur per leaf
def kerjakan(S, selesai, t0):
    L = S.leaf

    def ada(blok, metode, lengan, seed):
        return (L, blok, metode, lengan, str(seed)) in selesai

    def simpan(blok, metode, lengan, seed, rg, pred, extra=None):
        tulis(OUT, [S.baris(blok, t, metode, lengan, seed, p, extra) for t, p in zip(rg, pred)])
        selesai.add((L, blok, metode, lengan, str(seed)))
        print(f'    {blok:3s} {metode:14s} {lengan:14s} seed {seed}  ({time.time() - t0:.0f}s)', flush=True)

    tulis(SKALA, [] if (L, 'skala') in selesai else [dict(
        leaf=L, s0=S.s0, mulai=str(pd.Timestamp(S.d[0]).date()), n_latih=S.uji0,
        uji_awal=str(pd.Timestamp(S.d[S.uji0]).date()), den=S.den, den_penuh=S.den_penuh,
        den_2022=S.den_2022, den_val=S.den_val)])
    selesai.add((L, 'skala'))

    # 1. penyetelan di blok validasi (seed 0), ramalan setiap konfigurasi disimpan
    tun = baca(TUNE)
    pilihan = {}
    if len(tun):
        tun = tun[tun.leaf == L]
        pilihan = dict(zip(tun.model, tun.cfg))
    for nm in LEARNER:
        if nm in pilihan:
            continue
        skor = []
        sd0 = SEED_RF[0] if nm == 'RandomForest' else 0
        for ci, cfg in enumerate(GRID[nm]):
            lg = f'cfg{ci + 1}'
            if ada('val', nm, lg, sd0):
                v = baca(OUT)
                v = v[(v.leaf == L) & (v.blok == 'val') & (v.metode == nm) & (v.lengan == lg)]
                rg, pr = None, None
                skor.append((float(np.mean(np.abs(v.actual - v.pred))) / S.den_val, ci))
                continue
            rg, pr = ramal_learner(S, nm, cfg, sd0, 'val')
            simpan('val', nm, lg, sd0, rg, pr)
            skor.append((float(np.mean(np.abs(S.y[list(rg)] - np.array(pr)))) / S.den_val, ci))
        best = min(skor)[1]
        pilihan[nm] = best
        tulis(TUNE, [dict(leaf=L, model=nm, cfg=best, mase_val=min(skor)[0])])

    # 2. benchmark, validasi lalu uji
    for blok in ('val', 'uji'):
        for nm in BENCH:
            if not ada(blok, nm, 'utama', 0):
                rg, pr = ramal_bench(S, nm, blok)
                simpan(blok, nm, 'utama', 0, rg, pr)

    # 3. lengan harian learner
    for nm in LEARNER:
        cfg = GRID[nm][pilihan[nm]]
        seeds = SEED_RF if nm == 'RandomForest' else (0,)
        for sd in seeds:
            if not ada('uji', nm, 'utama', sd):
                rg, pr = ramal_learner(S, nm, cfg, sd, 'uji')
                simpan('uji', nm, 'utama', sd, rg, pr, dict(cfg=pilihan[nm] + 1))
            if not ada('uji', nm, 'tanpa_mrmr', sd):
                rg, pr = ramal_learner(S, nm, cfg, sd, 'uji', beta=0.0)
                simpan('uji', nm, 'tanpa_mrmr', sd, rg, pr)
            if not ada('uji', nm, 'tanpa_setelan', sd):
                if pilihan[nm] == 0:
                    v = baca(OUT)
                    v = v[(v.leaf == L) & (v.blok == 'uji') & (v.metode == nm)
                          & (v.lengan == 'utama') & (v.seed.astype(str) == str(sd))].sort_values('origin')
                    rg, pr = [S.uji0 + o for o in v.origin], list(v.pred)
                    simpan('uji', nm, 'tanpa_setelan', sd, rg, pr, dict(salinan=1))
                else:
                    rg, pr = ramal_learner(S, nm, GRID[nm][0], sd, 'uji')
                    simpan('uji', nm, 'tanpa_setelan', sd, rg, pr)
            if not ada('uji', nm, 'tanpa_refit', sd):
                rg, pr = ramal_learner(S, nm, cfg, sd, 'uji', jadwal=SUBBLOK)
                simpan('uji', nm, 'tanpa_refit', sd, rg, pr)

    # 4. lengan mingguan
    lengan_m = [(f'k{k}' if k != 'semua' else 'k_semua', dict(k=k)) for k in K_LENGAN] + [
        ('pasar_ubah', dict(fk='ubah')), ('pasar_level', dict(fk='level')),
        ('jendela_2022', dict(latih0=S.mulai_2022))]
    for nm in LEARNER:
        cfg = GRID[nm][pilihan[nm]]
        for sd in (SEED_RF if nm == 'RandomForest' else (0,)):
            for lg, kw in lengan_m:
                if not ada('uji', nm, lg, sd):
                    rg, pr = ramal_learner(S, nm, cfg, sd, 'uji', jadwal=MINGGU, **kw)
                    simpan('uji', nm, lg, sd, rg, pr)


def target_baris(n_leaf=15):
    """Jumlah baris v2_ramalan.csv yang harus dicapai (dipakai vps.py)."""
    n_seed = {'RandomForest': len(SEED_RF), 'LightGBM': 1, 'XGBoost': 1}
    per = NVAL * (len(BENCH) + 4 * len(LEARNER)) + NROLL * (
        len(BENCH) + sum(n_seed.values()) * (4 + len(K_LENGAN) + 3))
    return n_leaf * per


def main():
    t0 = time.time()
    periksa_sidik()
    catat_versi()
    print('=' * 64, flush=True)
    print('JALAN ULANG v2', flush=True)
    print('=' * 64, flush=True)
    for k, v in sidik().items():
        print(f'  {k:10s}: {v}', flush=True)
    print(f'  keluaran  : {HASIL}', flush=True)
    panel, dcols, dall = load_panel()
    lv = leaves(panel)
    pl, pu, tp = pasar()
    selesai = sudah()
    sk = baca(SKALA)
    if len(sk):
        selesai |= {(l, 'skala') for l in sk.leaf}
    for i, (_, r) in enumerate(lv.iterrows(), 1):
        print(f'\n[{i}/{len(lv)}] {r["Row_ID"]}  membangun bingkai fitur ...', flush=True)
        S = Seri(r, dcols, dall, pl, pu, tp)
        print(f'  mulai {pd.Timestamp(S.d[0]).date()} (dibuang {S.s0} hari nol struktural), '
              f'uji {pd.Timestamp(S.d[S.uji0]).date()} s/d {pd.Timestamp(S.d[-1]).date()}', flush=True)
        kerjakan(S, selesai, t0)
        del S
        gc.collect()
    print(f'\nSELESAI ({time.time() - t0:.0f}s)', flush=True)


if __name__ == '__main__':
    main()
