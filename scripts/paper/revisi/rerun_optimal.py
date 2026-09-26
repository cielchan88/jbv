"""Komputasi ulang hasil utama pada konfigurasi OPTIMAL.

Pengulas menolak tiga hal, dan ketiganya menuntut konfigurasi yang sama:

  1. Peringkat Tabel 6 memakai parameter bawaan, padahal RandomForest
     tersetel membaik 9,5% dan semestinya naik ke peringkat satu.
  2. Seleksi fitur memakai Spearman univariat, padahal mRMR lebih baik 7%.
  3. Parameter di-fit sekali di awal blok, padahal refit harian lebih baik
     4,5% dan biayanya hanya hitungan detik.

Jadi seluruh hasil utama dijalankan ulang dengan: mRMR (beta=1) + setelan
terpilih dari blok validasi + refit SETIAP HARI.

CHECKPOINT. Lingkungan ini pernah membunuh proses latar tanpa jejak, dan
pekerjaan ini berjam-jam. Setiap sel (leaf x model) ditulis ke CSV begitu
selesai, dan sel yang sudah ada di CSV dilewati saat dijalankan ulang. Mati
di tengah berarti kehilangan satu sel, bukan seluruh pekerjaan.
"""
import os
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h1_common import *          # noqa: F403

warnings.filterwarnings('ignore')

import utils.forecasting.randomforest_model as rfm
import utils.forecasting.lightgbm_model as lgm
import utils.forecasting.xgboost_model as xgm
from utils.forecasting import (ARIMAForecaster, APUVAForecaster,
                               CrostonForecaster, LightGBMForecaster,
                               NaiveForecaster, ProphetForecaster,
                               RandomForestForecaster, XGBoostForecaster)
from utils.feature_engineering_optimized import select_top_features_optimized
from cache_fitur import pasang_cache

# Cache bingkai fitur. Protokol refit harian membangun ulang seluruh bingkai
# di setiap origin padahal baris lama tidak berubah; lihat cache_fitur.py.
# JBV_CACHE=0 mematikannya kalau perlu membandingkan.
CACHE = (pasang_cache(rfm, lgm, xgm)
         if os.environ.get('JBV_CACHE', '1') != '0' else None)


def panaskan(d, y, external_series=None):
    """Bangun bingkai rentang terpanjang sekali, sebelum loop origin leaf ini.

    bersihkan() dulu supaya bingkai leaf sebelumnya dilepas - satu bingkai
    5.000 x 225 sekitar 9 MB, dan menyimpannya untuk 15 leaf sekaligus tidak
    ada gunanya karena leaf diproses satu per satu.
    """
    if CACHE is None:
        return
    CACHE.bersihkan()
    CACHE.siapkan(d[:len(y) - 1], y[:len(y) - 1], external_series=external_series)


S = HASIL                      # ikut JBV_PANEL / JBV_HASIL, lihat h1_common
os.makedirs(S, exist_ok=True)
# jalur() menyisipkan nomor shard saat JBV_SHARD disetel, supaya dua proses
# tidak pernah meng-append ke berkas yang sama. Pembacaan tetap menyatukan
# seluruh shard; lihat h1_common.
OUT = jalur('opt_rolling.csv')
TUNE = jalur('opt_tuned.csv')
NROLL = 30
# Origin validasi untuk memilih setelan. Lebih pendek dari blok uji dengan
# sengaja: ini tahap PEMILIHAN, bukan hasil yang dilaporkan, dan menyetel
# dengan refit harian pada 30 origin makan 10 menit per model per leaf -
# 9 jam hanya untuk menyetel. Sepuluh origin menahan biayanya di sepertiga
# tanpa mengubah hal yang dipersoalkan pengulas: setelan tetap dipilih pada
# blok yang MENDAHULUI blok uji, jadi tidak ada kebocoran.
# Panjang blok validasi. Sepuluh origin TIDAK memadai, dan hasilnya sendiri
# yang membuktikan: setelan terpilih justru lebih buruk 1,18% daripada bawaan
# library. Sepuluh galat satu langkah tidak cukup memisahkan empat kandidat,
# jadi yang terpilih sebagian besar derau.
#
# JBV_NVAL melebarkannya tanpa menyentuh blok uji, yang tetap 30 origin
# terakhir - blok validasi hanya memanjang MUNDUR, jadi tidak ada kebocoran.
# Biayanya linear: 3 model x 4 kandidat x NVAL fit per leaf, sekitar 8,75 detik
# per fit, jadi NVAL=60 berarti sekitar 105 menit per leaf untuk tahap
# penyetelan saja.
#
# Mengubah NVAL mengubah setelan terpilih, dan setelan itu dipakai Tabel 5, 6,
# 8, 9 dan 10 - jadi seluruh tahap harus dijalankan ulang di folder hasil yang
# BERSIH, bukan ditumpuk di atas yang lama.
NVAL = int(os.environ.get('JBV_NVAL', '10'))
TOP_K = 25              # sama dengan naskah, supaya hanya SATU hal berubah
MRMR_BETA = 1.0
SEASONAL = 'SeasonalDecomp'

ML = {'RandomForest': (RandomForestForecaster, rfm),
      'LightGBM': (LightGBMForecaster, lgm),
      'XGBoost': (XGBoostForecaster, xgm)}

GRID = {
    'RandomForest': [dict(n_estimators=100, max_depth=10),
                     dict(n_estimators=300, max_depth=10),
                     dict(n_estimators=300, max_depth=None),
                     dict(n_estimators=100, max_depth=4)],
    'LightGBM': [dict(n_estimators=100, learning_rate=0.05, max_depth=5),
                 dict(n_estimators=400, learning_rate=0.02, max_depth=5),
                 dict(n_estimators=100, learning_rate=0.10, max_depth=3),
                 dict(n_estimators=400, learning_rate=0.05, max_depth=8)],
    'XGBoost': [dict(n_estimators=100, max_depth=5, learning_rate=0.05),
                dict(n_estimators=400, max_depth=5, learning_rate=0.02),
                dict(n_estimators=100, max_depth=3, learning_rate=0.10),
                dict(n_estimators=400, max_depth=8, learning_rate=0.05)],
}

ALL_MODELS = ['Naive', 'NaiveMean', 'NaiveDrift', 'Croston', SEASONAL,
              'ARIMA', 'Prophet', 'RandomForest', 'LightGBM', 'XGBoost']


def build(name, row_id, cfg=None):
    if name == 'Naive':        return NaiveForecaster(method='last')
    if name == 'NaiveMean':    return NaiveForecaster(method='mean')
    if name == 'NaiveDrift':   return NaiveForecaster(method='drift')
    if name == 'Croston':      return CrostonForecaster()
    if name == SEASONAL:       return APUVAForecaster(row_id=row_id)
    if name == 'ARIMA':        return ARIMAForecaster()
    if name == 'Prophet':      return ProphetForecaster()
    return ML[name][0](**(cfg or {}))


def p1(m, d, y):
    v, _ = m.predict(d, y, 1)
    return float(np.asarray(v).ravel()[0])


def pasang_mrmr():
    """mRMR untuk ketiga model berbasis fitur."""
    for _, mod in ML.values():
        mod.TOP_K_FEATURES = TOP_K
        mod.select_top_features = (
            lambda df, top_k=TOP_K, _b=MRMR_BETA:
            select_top_features_optimized(df, top_k=top_k, mrmr_beta=_b))


def sudah(path, kunci):
    """Sel yang sudah tercatat, untuk melewati saat dijalankan ulang.

    Membaca SELURUH shard, bukan hanya berkas yang ditulis proses ini, supaya
    sel yang sudah dikerjakan proses lain - atau yang sudah disatukan ke
    berkas kanonik oleh gabung_shard.py - tidak dihitung ulang.
    """
    d = baca(path)
    if not len(d) or any(k not in d.columns for k in kunci):
        return set()
    return set(map(tuple, d[list(kunci)].drop_duplicates().values))


def tulis(path, rows):
    df = pd.DataFrame(rows)
    df.to_csv(path, mode='a', header=not os.path.exists(path), index=False)


def pilih_setelan(r, d, y, t0):
    """Pilih setelan per (leaf, model) di blok validasi yang MENDAHULUI uji.

    Tanpa pemisahan ini, setelan terpilih sudah melihat blok uji dan
    angkanya bocor.
    """
    done = sudah(TUNE, ('leaf', 'model'))
    te_cut = len(y) - NROLL
    va_cut = te_cut - NVAL
    den_va = scale_denom(y[:va_cut])
    rows = []
    for nm in ML:
        if (r['Row_ID'], nm) in done:
            continue
        skor = []
        for ci, cfg in enumerate(GRID[nm]):
            ae = []
            # Denyut. Satu sel butuh 2-5 menit; tanpa tanda hidup di sini,
            # layar diam begitu lama tidak bisa dibedakan dari proses macet.
            print(f'      {nm} cfg{ci+1}/{len(GRID[nm])} ...',
                  end='\r', flush=True)
            try:
                # Blok validasi juga memakai refit harian, supaya setelan
                # dipilih pada rezim yang sama dengan yang nanti dipakai.
                for t in range(va_cut, te_cut):
                    m = build(nm, r['Row_ID'], cfg)
                    m.fit(d[:t], y[:t])
                    ae.append(one_step_metrics(y[t], p1(m, d[:t], y[:t]), den_va)['mase'])
                skor.append((float(np.nanmean(ae)), ci))
            except Exception:
                skor.append((float('inf'), ci))
        best = min(skor)[1]
        # Tulis SETIAP SEL, jangan ditumpuk sampai leaf selesai. Proses ini
        # bisa mati di tengah; menumpuk berarti kehilangan seluruh leaf
        # padahal selnya sudah dihitung.
        tulis(TUNE, [{'leaf': r['Row_ID'], 'model': nm, 'cfg': best,
                      'mase_val': min(skor)[0]}])
        print(f'    {nm:13s} -> cfg{best}  MASE_val {min(skor)[0]:.3f}  '
              f'({time.time()-t0:.0f}s)', flush=True)


def main():
    t0 = time.time()
    print('=' * 64, flush=True)
    print('KOMPUTASI ULANG NASKAH - KONFIGURASI OPTIMAL', flush=True)
    print('=' * 64, flush=True)
    print(f'  selektor        : mRMR (beta={MRMR_BETA})', flush=True)
    print(f'  jumlah fitur    : {TOP_K}', flush=True)
    print(f'  origin validasi : {NVAL}   (untuk memilih setelan)', flush=True)
    print(f'  origin uji      : {NROLL}  (refit harian)', flush=True)
    print(f'  keluaran        : {S}', flush=True)
    print('  memuat panel ...', flush=True)

    panel, dcols, dall = load_panel()
    lv = leaves(panel)
    print(f'  panel  : {len(dcols):,} hari, {dcols[0]} s/d {dcols[-1]}', flush=True)
    print(f'  leaf   : {len(lv)}', flush=True)
    pasang_mrmr()

    # ---- tahap 1: setelan per leaf/model dari blok validasi ----
    # Hitungan sisa disaring ke leaf milik shard ini. sudah() sengaja membaca
    # seluruh shard, jadi tanpa penyaringan ini angkanya ikut menghitung sel
    # milik proses lain - dan bisa jadi negatif.
    milik = set(lv['Row_ID'])
    sisa = (len(lv) * len(ML)
            - len([k for k in sudah(TUNE, ('leaf', 'model')) if k[0] in milik]))
    print(f'\nTAHAP 1/2  penyetelan - {sisa} sel tersisa '
          f'(~2-5 menit per sel)\n', flush=True)
    for i, (_, r) in enumerate(lv.iterrows(), 1):
        d, y = series_of(r, dcols, dall)
        print(f'  [{i}/{len(lv)}] {r["Row_ID"]}', flush=True)
        panaskan(d, y)
        pilih_setelan(r, d, y, t0)
    print(f'\nTAHAP 1 SELESAI ({time.time()-t0:.0f}s)', flush=True)

    tuned = (baca(TUNE).drop_duplicates(['leaf', 'model'], keep='last')
             .set_index(['leaf', 'model'])['cfg'].to_dict())

    # ---- tahap 2: blok uji, refit harian, seluruh model ----
    done = sudah(OUT, ('leaf', 'model'))
    print(f'\nTAHAP 2/2  blok uji - '
          f'{len(lv) * len(ALL_MODELS) - len([k for k in done if k[0] in milik])} '
          f'sel tersisa\n', flush=True)
    for i, (_, r) in enumerate(lv.iterrows(), 1):
        d, y = series_of(r, dcols, dall)
        cut = len(y) - NROLL
        den = scale_denom(y[:cut])
        print(f'  [{i}/{len(lv)}] {r["Row_ID"]}', flush=True)
        panaskan(d, y)
        for nm in ALL_MODELS:
            if (r['Row_ID'], nm) in done:
                continue
            cfg = None
            if nm in ML:
                ci = tuned.get((r['Row_ID'], nm))
                cfg = GRID[nm][int(ci)] if ci is not None else None
            rows = []
            try:
                for t in range(cut, len(y)):
                    # Denyut per origin. Tanpa ini layar diam sepanjang satu
                    # model penuh - tiga menit untuk RandomForest, lebih lama
                    # lagi untuk ARIMA yang memilih ordo di setiap origin - dan
                    # diam selama itu tidak bisa dibedakan dari proses macet.
                    # Hanya cetakan; tidak ada perhitungan yang berubah.
                    print(f'      {nm} origin {t-cut+1}/{NROLL} ...',
                          end='\r', flush=True)
                    m = build(nm, r['Row_ID'], cfg)
                    m.fit(d[:t], y[:t])          # REFIT HARIAN
                    rec = one_step_metrics(y[t], p1(m, d[:t], y[:t]), den)
                    rec.update(leaf=r['Row_ID'], model=nm, origin=t - cut)
                    rows.append(rec)
            except Exception as e:
                print(f'  GAGAL {r["Row_ID"]}/{nm}: {type(e).__name__}: {e}',
                      flush=True)
                continue
            tulis(OUT, rows)
            print(f'    {nm:15s} MASE {np.nanmean([x["mase"] for x in rows]):.3f}'
                  f'  ({time.time()-t0:.0f}s)',
                  flush=True)
    print(f'SELESAI TOTAL ({time.time()-t0:.0f}s)', flush=True)
    if CACHE is not None:
        st = CACHE()
        print(f'  cache fitur: kena {st["kena_cache"]}, bangun ulang '
              f'{st["bangun_ulang"]} ({st["persen_kena"]:.0f}% kena, '
              f'{st["n_kunci"]} kunci)', flush=True)


if __name__ == '__main__':
    main()
