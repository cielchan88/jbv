"""Ablasi TERBALIK untuk Bagian 4.3.

Di draf lama, penyetelan / mRMR / refit harian disajikan sebagai eksperimen
ketahanan terpisah - seolah naskahnya memakai konfigurasi lemah lalu
memeriksa apakah itu penting. Pengulas benar bahwa itu terbalik.

Sekarang ketiganya jadi konfigurasi UTAMA, dan bagian 4.3 menjawab
pertanyaan yang berbeda: berapa yang HILANG kalau masing-masing dimatikan.
Arah pertanyaannya membalik, tapi bukti yang sudah dibayar mahal tetap
terpakai, dan pembaca mendapat jawaban atas "kenapa konfigurasi ini"
alih-alih sekadar diberi tahu.

Tiga lengan, masing-masing mematikan SATU hal dari konfigurasi optimal:

    tanpa_setelan  parameter bawaan   (mRMR + refit harian tetap)
    tanpa_mrmr     Spearman univariat (setelan + refit harian tetap)
    tanpa_refit    fit sekali di awal (setelan + mRMR tetap)

Hanya tiga model berbasis fitur: ketiga komponen itu memang hanya berlaku
di sana.
"""
import os
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h1_common import *          # noqa: F403

warnings.filterwarnings('ignore')

# panaskan/CACHE ikut dari rerun_optimal: cache fitur dipasang sekali di sana,
# saat modul itu diimpor. Mengimpornya lagi di sini tidak melapisi ulang.
from rerun_optimal import (GRID, ML, NROLL, TOP_K, MRMR_BETA, S, TUNE,
                           p1, sudah, tulis, panaskan, CACHE)
from utils.feature_engineering_optimized import select_top_features_optimized

OUT = jalur('opt_ablasi.csv')
ARMS = ('tanpa_setelan', 'tanpa_mrmr', 'tanpa_refit')


def pasang_selektor(beta):
    for _, mod in ML.values():
        mod.TOP_K_FEATURES = TOP_K
        if beta <= 0:
            # mrmr_beta HARUS disebut eksplisit. Nilai bawaan
            # select_top_features_optimized adalah 1.0 sejak commit 7006b01,
            # jadi menyerahkan fungsinya begitu saja membuat lengan 'tanpa
            # mRMR' diam-diam TETAP memakai mRMR - identik dengan lengan
            # optimal, selisih persis 0,0000.
            mod.select_top_features = (lambda df, top_k=TOP_K:
                                       select_top_features_optimized(
                                           df, top_k=top_k, mrmr_beta=0.0))
        else:
            mod.select_top_features = (
                lambda df, top_k=TOP_K, _b=beta:
                select_top_features_optimized(df, top_k=top_k, mrmr_beta=_b))


def main():
    t0 = time.time()
    print('=' * 64, flush=True)
    print('ABLASI TERBALIK - Bagian 4.3', flush=True)
    print('=' * 64, flush=True)
    print(f'  lengan   : {", ".join(ARMS)}', flush=True)
    print(f'  model    : {", ".join(ML)}', flush=True)
    print(f'  origin   : {NROLL} per sel', flush=True)
    print(f'  keluaran : {OUT}', flush=True)

    if not ada(TUNE):
        print('\nBERHENTI: opt_tuned.csv belum ada.', flush=True)
        print(f'Jalankan dulu: {sys.executable} scripts/paper/revisi/rerun_optimal.py',
              flush=True)
        return
    tuned = (baca(TUNE).drop_duplicates(['leaf', 'model'], keep='last')
             .set_index(['leaf', 'model'])['cfg'].to_dict())
    print(f'  setelan  : {len(tuned)} sel terbaca', flush=True)
    print('  memuat panel ...', flush=True)

    panel, dcols, dall = load_panel()
    lv = leaves(panel)
    done = sudah(OUT, ('leaf', 'model', 'arm'))
    # sudah() membaca seluruh shard, jadi hitungan sisa disaring ke leaf
    # milik proses ini - kalau tidak, ia ikut menghitung sel proses lain.
    milik = set(lv['Row_ID'])
    total = len(lv) * len(ML) * len(ARMS)
    print(f'  panel    : {len(dcols):,} hari, {len(lv)} leaf', flush=True)
    print(f'\n{total - len([k for k in done if k[0] in milik])} sel tersisa dari {total} '
          f'(~1-3 menit per sel)\n', flush=True)

    for i, (_, r) in enumerate(lv.iterrows(), 1):
        d, y = series_of(r, dcols, dall)
        cut = len(y) - NROLL
        den = scale_denom(y[:cut])
        print(f'  [{i}/{len(lv)}] {r["Row_ID"]}', flush=True)
        panaskan(d, y)
        for arm in ARMS:
            # mRMR menyala kecuali lengan ini yang mematikannya
            pasang_selektor(0.0 if arm == 'tanpa_mrmr' else MRMR_BETA)
            for nm, (cls, _mod) in ML.items():
                if (r['Row_ID'], nm, arm) in done:
                    continue
                # Denyut. Satu sel butuh 1-3 menit; tanpa tanda hidup di sini,
                # layar diam selama itu tidak bisa dibedakan dari proses macet.
                print(f'      {arm} / {nm} ...', end='\r', flush=True)
                ci = tuned.get((r['Row_ID'], nm))
                # setelan terpilih menyala kecuali lengan ini yang mematikannya
                cfg = ({} if arm == 'tanpa_setelan' or ci is None
                       else GRID[nm][int(ci)])
                rows = []
                try:
                    if arm == 'tanpa_refit':
                        m = cls(**cfg)
                        m.fit(d[:cut], y[:cut])          # sekali saja
                    for t in range(cut, len(y)):
                        if arm != 'tanpa_refit':
                            m = cls(**cfg)
                            m.fit(d[:t], y[:t])          # refit harian
                        rec = one_step_metrics(y[t], p1(m, d[:t], y[:t]), den)
                        rec.update(leaf=r['Row_ID'], model=nm, arm=arm,
                                   origin=t - cut)
                        rows.append(rec)
                except Exception as e:
                    print(f'  GAGAL {r["Row_ID"]}/{nm}/{arm}: '
                          f'{type(e).__name__}', flush=True)
                    continue
                tulis(OUT, rows)
                print(f'    {arm:14s} {nm:13s} MASE '
                      f'{np.nanmean([x["mase"] for x in rows]):.3f}'
                      f'  ({time.time()-t0:.0f}s)',
                      flush=True)
    print(f'ABLASI SELESAI ({time.time()-t0:.0f}s)', flush=True)
    if CACHE is not None:
        st = CACHE()
        print(f'  cache fitur: kena {st["kena_cache"]}, bangun ulang '
              f'{st["bangun_ulang"]} ({st["persen_kena"]:.0f}% kena, '
              f'{st["n_kunci"]} kunci)', flush=True)


if __name__ == '__main__':
    main()
