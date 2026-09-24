"""Desain headline: latih sampai hari kedua-terakhir, ramal hari terakhir.

Inilah Tabel 5 dan Lampiran A1 naskah - satu titik uji per leaf, sepuluh
metode. Bukan pengganti desain rolling, melainkan pelengkapnya: desain ini
adalah cara sistem benar-benar dipakai desk, tapi satu hari tidak memberi
sebaran sampel, jadi seluruh klaim inferensial tetap bersandar pada 30 origin.

KENAPA TAHAP INI ADA. Selama ini Tabel 5 dihitung oleh skrip lepas di luar
repo, jadi komputasi ulang lengkap menghasilkan Tabel 6 sampai 9 tanpa Tabel 5,
tanpa Lampiran A1, dan tanpa korelasi peringkat antar dua desain yang dikutip
naskah di beberapa tempat. Dengan tahap ini, satu perintah menghasilkan
seluruh isi naskah.

Refit harian tidak berlaku di sini - hanya ada satu origin - tapi kolam fitur,
seleksi mRMR dan setelan terpilih per leaf semuanya sama dengan Tabel 6, jadi
selisih antar kedua tabel murni soal desain evaluasi.

Checkpoint per sel ke headline.csv. Aman dijalankan ulang.
"""
import os
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h1_common import *          # noqa: F403
warnings.filterwarnings('ignore')

from rerun_optimal import (ALL_MODELS, GRID, ML, S, TUNE, build, p1,
                           pasang_mrmr, sudah, tulis)

OUT = S + 'headline.csv'


def main():
    t0 = time.time()
    print('=' * 64, flush=True)
    print('DESAIN HEADLINE - Tabel 5 dan Lampiran A1', flush=True)
    print('=' * 64, flush=True)
    if not os.path.exists(TUNE):
        print('BERHENTI: opt_tuned.csv belum ada. Jalankan rerun_optimal.py dulu.')
        return 1
    tuned = pd.read_csv(TUNE).set_index(['leaf', 'model'])['cfg'].to_dict()

    pasang_mrmr()
    panel, dcols, dall = load_panel()
    lv = leaves(panel)
    done = sudah(OUT, ('leaf', 'model'))
    print(f'  {len(lv)} leaf x {len(ALL_MODELS)} metode, '
          f'{len(lv) * len(ALL_MODELS) - len(done)} sel tersisa\n', flush=True)

    for i, (_, r) in enumerate(lv.iterrows(), 1):
        d, y = series_of(r, dcols, dall)
        # Latih semua kecuali hari terakhir, ramal hari itu. Penyebut MASE
        # dihitung dari sampel latih saja, sama seperti di desain rolling.
        dtr, ytr, yte = d[:-1], y[:-1], y[-1]
        den = scale_denom(ytr)
        print(f'  [{i}/{len(lv)}] {r["Row_ID"]}  aktual {yte:.1f}', flush=True)
        for nm in ALL_MODELS:
            if (r['Row_ID'], nm) in done:
                continue
            cfg = None
            if nm in ML:
                ci = tuned.get((r['Row_ID'], nm))
                cfg = GRID[nm][int(ci)] if ci is not None else None
            try:
                m = build(nm, r['Row_ID'], cfg)
                m.fit(dtr, ytr)
                rec = one_step_metrics(yte, p1(m, dtr, ytr), den)
            except Exception as e:
                print(f'    GAGAL {nm}: {type(e).__name__}: {e}', flush=True)
                continue
            rec.update(leaf=r['Row_ID'], model=nm)
            tulis(OUT, [rec])
            print(f'    {nm:15s} ramal {rec["pred"]:9.1f}  MASE {rec["mase"]:.3f}'
                  f'  ({time.time()-t0:.0f}s)', flush=True)

    print(f'\nSELESAI ({time.time()-t0:.0f}s)\n  {OUT}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
