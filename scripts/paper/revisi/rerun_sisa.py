"""Tiga eksperimen pembanding yang tersisa, pada kolam fitur BARU.

    Tabel 7 + Gambar 5   ablasi jumlah fitur (k = 6, 8, 12, 16, 20, 25)
    Tabel 8 + Gambar 6   data pasar hidup/mati pada dua nilai k
    Gambar 10            Spearman lawan mRMR pada uji data pasar yang sama
    Tabel 8b             data pasar yang juga dipakai SAAT MERAMAL

SATU PENYEDERHANAAN, DINYATAKAN TERBUKA. Ketiganya memakai fit SEKALI per
blok, bukan refit harian seperti Tabel 6 dan 9.

Alasannya bukan penghematan semata. Ketiganya adalah eksperimen PEMBANDING:
yang dilaporkan selisih antar lengan, bukan tingkat akurasinya. Jalan pintas
yang sama diterapkan pada SETIAP lengan, jadi ia tidak menguntungkan lengan
mana pun - ia hanya menggeser kedua sisi dengan besaran yang sama. Dengan
refit harian ketiganya butuh sekitar 35 jam; dengan fit sekali sekitar dua
jam. Naskah menyatakan pembatasan ini di caption masing-masing.

Yang TIDAK disederhanakan: kolam 18 lag, seleksi mRMR, dan setelan
hyperparameter terpilih per leaf - ketiganya sama dengan Tabel 6.

Checkpoint per sel. Jalankan ulang untuk melanjutkan.
"""
import os
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h1_common import *          # noqa: F403
warnings.filterwarnings('ignore')

from rerun_optimal import (GRID, ML, NROLL, TOP_K, MRMR_BETA, S, TUNE, p1,
                           sudah, tulis, CACHE)
from utils.feature_engineering_optimized import select_top_features_optimized

OUT_K = jalur('sisa_kablasi.csv')
OUT_X = jalur('sisa_eksternal.csv')
OUT_P = jalur('sisa_pasar_benar.csv')
ARMS_K = [6, 8, 12, 16, 20, 25]
K_EXT = [12, 25]
BETAS = [0.0, MRMR_BETA]


def pasang(k, beta):
    for _, mod in ML.values():
        mod.TOP_K_FEATURES = k
        if beta <= 0:
            # mrmr_beta HARUS disebut eksplisit. Nilai bawaan
            # select_top_features_optimized adalah 1.0 sejak commit 7006b01,
            # jadi menyerahkan fungsinya begitu saja membuat lengan 'tanpa
            # mRMR' diam-diam TETAP memakai mRMR - identik dengan lengan
            # optimal, selisih persis 0,0000.
            mod.select_top_features = (lambda df, top_k=k:
                                       select_top_features_optimized(
                                           df, top_k=top_k, mrmr_beta=0.0))
        else:
            mod.select_top_features = (lambda df, top_k=k, _b=beta:
                                       select_top_features_optimized(df, top_k=top_k,
                                                                     mrmr_beta=_b))


def pasang_ext(on):
    for _, mod in ML.values():
        if on:
            mod.cross_series_for_recursive = lambda es, name='m': es
        else:
            from utils.feature_config import cross_series_for_recursive as f
            mod.cross_series_for_recursive = f


def panaskan_dua(d, y, esd=None):
    """Panaskan cache untuk leaf ini - dua kunci sekaligus kalau perlu.

    Di sini setiap sel fit di titik yang SAMA (d[:cut]), jadi satu leaf
    membangun bingkai yang identik puluhan kali: 18 sel di bagian 1, 24 sel
    di bagian 2. Dengan cache itu jadi satu bingkai per kunci.

    Dua kunci karena bagian 2 menjalankan lengan dengan dan tanpa data pasar
    di leaf yang sama, dan keduanya memberi bingkai berbeda. panaskan() dari
    rerun_optimal tidak dipakai di sini justru karena ia membersihkan cache
    lebih dulu - memanggilnya dua kali akan membuang bingkai pertama.
    """
    if CACHE is None:
        return
    CACHE.bersihkan()
    d_p, y_p = d[:len(y) - 1], y[:len(y) - 1]
    CACHE.siapkan(d_p, y_p)
    if esd is not None:
        CACHE.siapkan(d_p, y_p, external_series=esd)


def p1x(m, d, y, esd=None, edt=None):
    """Ramalan satu langkah; seri pasar ikut hanya kalau tanggalnya diberikan.

    edt WAJIB menyertai esd. Bingkai di predict() hanya 271 baris terakhir,
    dan penyejajaran tanpa tanggal memotong dari depan - nilai pasar 2006
    akan tertempel ke baris 2026. predict() menolak kalau tanggalnya hilang.
    """
    if esd is not None and edt is not None:
        v, _ = m.predict(d, y, 1, external_series=esd, external_series_dates=edt)
    else:
        v, _ = m.predict(d, y, 1)
    return float(np.asarray(v).ravel()[0])


def blok(cls, cfg, d, y, cut, den, esd, extra, edt=None):
    """Satu sel: fit sekali di awal blok, lalu 30 ramalan satu langkah.

    edt dibiarkan None untuk bagian 1 dan 2, supaya keduanya tetap persis
    seperti sebelumnya - fitur pasar ditambal nol saat meramal. Bagian 3
    mengirimkannya, dan di situlah pasar benar-benar dipakai saat meramal.
    """
    m = cls(**cfg)
    m.fit(d[:cut], y[:cut], external_series=esd) if esd is not None else m.fit(d[:cut], y[:cut])
    rows = []
    for t in range(cut, len(y)):
        rec = one_step_metrics(y[t], p1x(m, d[:t], y[:t], esd, edt), den)
        rec.update(origin=t - cut, **extra)
        rows.append(rec)
    return rows


def main():
    t0 = time.time()
    print('=' * 64, flush=True)
    print('EKSPERIMEN PEMBANDING SISA - kolam 18 lag, fit sekali per blok', flush=True)
    print('=' * 64, flush=True)
    if not ada(TUNE):
        print('BERHENTI: opt_tuned.csv belum ada.'); return
    tuned = (baca(TUNE).drop_duplicates(['leaf', 'model'], keep='last')
             .set_index(['leaf', 'model'])['cfg'].to_dict())
    panel, dcols, dall = load_panel()
    lv = leaves(panel)
    esd, edt = load_external()
    print(f'  {len(lv)} leaf, setelan {len(tuned)} sel terbaca\n', flush=True)

    # ---------- 1. ablasi jumlah fitur ----------
    done = sudah(OUT_K, ('leaf', 'model', 'top_k'))
    # sudah() membaca seluruh shard, jadi hitungan sisa disaring ke leaf
    # milik proses ini - kalau tidak, ia ikut menghitung sel proses lain.
    milik = set(lv['Row_ID'])
    print(f'[1/2] ablasi jumlah fitur - '
          f'{len(lv)*len(ML)*len(ARMS_K)-len([k for k in done if k[0] in milik])} sel',
          flush=True)
    pasang_ext(False)
    for i, (_, r) in enumerate(lv.iterrows(), 1):
        d, y = series_of(r, dcols, dall)
        cut = len(y) - NROLL; den = scale_denom(y[:cut])
        panaskan_dua(d, y)                 # bagian ini tanpa data pasar
        for k in ARMS_K:
            for nm, (cls, _m) in ML.items():
                if (r['Row_ID'], nm, k) in done:
                    continue
                pasang(k, MRMR_BETA)
                try:
                    rows = blok(cls, GRID[nm][int(tuned[(r['Row_ID'], nm)])],
                                d, y, cut, den, None,
                                dict(leaf=r['Row_ID'], model=nm, top_k=k))
                except Exception as e:
                    print(f'    GAGAL {r["Row_ID"]}/{nm}/k={k}: {type(e).__name__}',
                          flush=True); continue
                tulis(OUT_K, rows)
        print(f'  [{i}/{len(lv)}] {r["Row_ID"]} ({time.time()-t0:.0f}s)', flush=True)

    # ---------- 2. data pasar, dua penyeleksi ----------
    done = sudah(OUT_X, ('leaf', 'model', 'top_k', 'ext', 'beta'))
    total = len(lv)*len(ML)*len(K_EXT)*2*len(BETAS)
    print(f'\n[2/2] data pasar x penyeleksi - '
          f'{total-len([k for k in done if k[0] in milik])} sel', flush=True)
    for i, (_, r) in enumerate(lv.iterrows(), 1):
        d, y = series_of(r, dcols, dall)
        cut = len(y) - NROLL; den = scale_denom(y[:cut])
        # pasang_ext(True) dulu, baru panaskan: panaskan_dua melewatkan seri
        # pasar lewat saringan modul yang SEDANG terpasang, supaya kuncinya
        # sama persis dengan yang nanti diminta fit(). Kalau saringan masih
        # yang asli, seri pasar dibuang dan kunci 'dengan pasar' tidak pernah
        # terisi.
        pasang_ext(True)
        panaskan_dua(d, y, esd)
        for beta in BETAS:
            for k in K_EXT:
                for on in (False, True):
                    pasang(k, beta); pasang_ext(on)
                    for nm, (cls, _m) in ML.items():
                        key = (r['Row_ID'], nm, k, on, beta)
                        if key in done:
                            continue
                        try:
                            rows = blok(cls, GRID[nm][int(tuned[(r['Row_ID'], nm)])],
                                        d, y, cut, den, esd if on else None,
                                        dict(leaf=r['Row_ID'], model=nm, top_k=k,
                                             ext=on, beta=beta))
                        except Exception as e:
                            print(f'    GAGAL {r["Row_ID"]}/{nm}: {type(e).__name__}',
                                  flush=True); continue
                        tulis(OUT_X, rows)
        print(f'  [{i}/{len(lv)}] {r["Row_ID"]} ({time.time()-t0:.0f}s)', flush=True)

    # ---------- 3. data pasar yang BENAR-BENAR dipakai saat meramal ----------
    #
    # Bagian 2 mengukur lengan yang dilumpuhkan. predict() dulu tidak punya
    # jalan untuk menerima seri pasar, jadi fitur ext_* yang dipakai saat fit
    # selalu hilang saat meramal dan ditambal NOL. Untuk ramalan rekursif
    # multi-langkah itu tak terhindarkan - nilai seri lain di masa depan tidak
    # ada. Tapi desain naskah ini SATU langkah, dan di situ ext_lag_1 adalah
    # nilai pasar hari sebelumnya: sudah diketahui, begitu juga lag 2-14.
    #
    # Gejalanya terukur di hasil lama: kerusakan per leaf berkorelasi dengan
    # jumlah slot yang direbut fitur pasar, Spearman 0,690 (p=0,004), dan dua
    # leaf yang tidak memberi slot pasar sama sekali nyaris tidak rusak.
    #
    # Bagian ini menjalankan lengan yang sama dengan pasar ikut saat meramal.
    # Lengan TANPA pasar tidak diulang - ia identik dengan ext=False di bagian
    # 2, jadi pakai baris itu sebagai pembanding.
    done = sudah(OUT_P, ('leaf', 'model', 'top_k', 'beta'))
    total = len(lv) * len(ML) * len(K_EXT) * len(BETAS)
    milik = set(lv['Row_ID'])
    print(f'\n[3/3] data pasar dipakai saat meramal - '
          f'{total-len([k for k in done if k[0] in milik])} sel', flush=True)
    for i, (_, r) in enumerate(lv.iterrows(), 1):
        d, y = series_of(r, dcols, dall)
        cut = len(y) - NROLL; den = scale_denom(y[:cut])
        pasang_ext(True)
        panaskan_dua(d, y, esd)
        for beta in BETAS:
            for k in K_EXT:
                pasang(k, beta)
                for nm, (cls, _m) in ML.items():
                    if (r['Row_ID'], nm, k, beta) in done:
                        continue
                    try:
                        rows = blok(cls, GRID[nm][int(tuned[(r['Row_ID'], nm)])],
                                    d, y, cut, den, esd,
                                    dict(leaf=r['Row_ID'], model=nm, top_k=k,
                                         beta=beta),
                                    edt=edt)          # <-- inilah bedanya
                    except Exception as e:
                        print(f'    GAGAL {r["Row_ID"]}/{nm}: {type(e).__name__}: {e}',
                              flush=True); continue
                    tulis(OUT_P, rows)
        print(f'  [{i}/{len(lv)}] {r["Row_ID"]} ({time.time()-t0:.0f}s)', flush=True)

    print(f'\nSISA SELESAI ({time.time()-t0:.0f}s)', flush=True)
    if CACHE is not None:
        st = CACHE()
        print(f'  cache fitur: kena {st["kena_cache"]}, bangun ulang '
              f'{st["bangun_ulang"]} ({st["persen_kena"]:.0f}% kena, '
              f'{st["n_kunci"]} kunci)', flush=True)
    print(f'  {OUT_K}\n  {OUT_X}\n  {OUT_P}', flush=True)


if __name__ == '__main__':
    main()
