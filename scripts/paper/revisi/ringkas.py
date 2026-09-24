"""Ringkas hasil komputasi ulang. Aman dijalankan kapan saja, termasuk
saat penarikan masih berjalan - ia membaca checkpoint apa adanya dan
menyatakan bagian mana yang belum lengkap.

    python scripts/paper/revisi/ringkas.py

Sengaja dipisah dari skrip penghitung supaya bisa dijalankan di panel lain
tanpa mengganggu proses yang sedang jalan.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Folder hasil dan jumlah leaf ikut JBV_PANEL, dengan aturan turunan yang
# sama seperti h1_common - ringkas.py sengaja tidak mengimpornya supaya tetap
# bisa dijalankan tanpa memuat seluruh utils.
_P = os.environ.get('JBV_PANEL')
_BAWAAN = 'hasil' if not _P else 'hasil_' + os.path.splitext(os.path.basename(_P))[0]
H = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 os.environ.get('JBV_HASIL', _BAWAAN))
_NLEAF = {'sdv-wide.csv': 18, 'sdv-wide-gabung.csv': 15}
NLEAF = int(os.environ.get('JBV_NLEAF', _NLEAF.get(os.path.basename(_P or 'sdv-wide.csv'), 18)))
NROLL = 30
ALL_MODELS = ['Naive', 'NaiveMean', 'NaiveDrift', 'Croston', 'SeasonalDecomp',
              'ARIMA', 'Prophet', 'RandomForest', 'LightGBM', 'XGBoost']
ML3 = ['RandomForest', 'LightGBM', 'XGBoost']


def baca(nama):
    p = os.path.join(H, nama)
    if not os.path.exists(p):
        return None
    try:
        d = pd.read_csv(p)
        return d if len(d) else None
    except Exception as e:
        print(f'  ({nama} belum terbaca: {type(e).__name__})')
        return None


def garis(judul):
    print('\n' + '=' * 68)
    print(judul)
    print('=' * 68)


def wilcoxon(a, b):
    """Uji peringkat bertanda berpasangan. Mengembalikan (p, menang, n)."""
    from scipy.stats import wilcoxon as w
    m = np.isfinite(a) & np.isfinite(b)
    a, b = np.asarray(a)[m], np.asarray(b)[m]
    if len(a) < 10 or np.allclose(a, b):
        return np.nan, int((a < b).sum()), len(a)
    try:
        return float(w(a, b).pvalue), int((a < b).sum()), len(a)
    except Exception:
        return np.nan, int((a < b).sum()), len(a)


def kemajuan():
    garis('KEMAJUAN')
    t = baca('opt_tuned.csv')
    r = baca('opt_rolling.csv')
    a = baca('opt_ablasi.csv')

    n_t = 0 if t is None else len(t.drop_duplicates(['leaf', 'model']))
    print(f'  Tahap 1  penyetelan   {n_t:3d} / {NLEAF * len(ML3)} sel')

    n_r = 0 if r is None else len(r.drop_duplicates(['leaf', 'model']))
    print(f'  Tahap 2  blok uji     {n_r:3d} / {NLEAF * len(ALL_MODELS)} sel')

    n_a = 0 if a is None else len(a.drop_duplicates(['leaf', 'model', 'arm']))
    print(f'  Tahap 3  ablasi       {n_a:3d} / {NLEAF * len(ML3) * 3} sel')

    if r is not None:
        leaf_lengkap = (r.groupby('leaf')['model'].nunique() == len(ALL_MODELS)).sum()
        print(f'\n  Leaf dengan 10 metode lengkap: {leaf_lengkap} / {NLEAF}')
    return t, r, a


def tabel_setelan(t):
    if t is None:
        return
    garis('SETELAN TERPILIH (dari blok validasi)')
    piv = t.drop_duplicates(['leaf', 'model']).pivot(
        index='leaf', columns='model', values='cfg')
    print(piv.to_string())
    print('\n  Sebaran pilihan per model:')
    for m in [c for c in ML3 if c in piv.columns]:
        v = piv[m].value_counts().sort_index()
        print(f'    {m:14s} ' + '  '.join(f'cfg{int(k)}:{int(n)}' for k, n in v.items()))
    print('\n  Kalau satu cfg mendominasi, grid-nya terlalu sempit atau')
    print('  perbedaan antar setelan memang kecil pada deret ini.')


def peringkat(r):
    if r is None:
        return
    garis('PERINGKAT METODE - konfigurasi optimal, refit harian')
    lengkap = r.groupby('leaf')['model'].nunique()
    leaf_ok = lengkap[lengkap == len(ALL_MODELS)].index
    if len(leaf_ok) == 0:
        print('  Belum ada leaf yang lengkap 10 metode. Tabel ditahan supaya')
        print('  peringkatnya tidak dihitung dari himpunan leaf yang berbeda')
        print('  antar metode - itu akan menyesatkan.')
        return
    if len(leaf_ok) < NLEAF:
        print(f'  SEMENTARA: {len(leaf_ok)} dari {NLEAF} leaf. Peringkat bisa')
        print(f'  berubah sampai lengkap.\n')

    d = r[r['leaf'].isin(leaf_ok)]
    g = d.groupby('model')['mase'].agg(
        rata='mean', median='median', maksimum='max', n='size')
    g = g.sort_values('rata')
    g.insert(0, 'peringkat', range(1, len(g) + 1))
    print(g.round(3).to_string())

    best = g.index[0]
    print(f'\n  Terbaik menurut rata-rata: {best}')
    med = g.sort_values('median').index[0]
    if med != best:
        print(f'  Terbaik menurut median  : {med}  <- rata-rata dan median TIDAK')
        print('     sepakat; laporkan keduanya, jangan pilih yang menguntungkan.')

    # apakah unggulnya nyata, atau dalam derau
    print('\n  Uji berpasangan terhadap juara (Wilcoxon, per titik uji):')
    pv = d.pivot_table(index=['leaf', 'origin'], columns='model', values='mase')
    for m in g.index[1:4]:
        if m in pv.columns and best in pv.columns:
            p, menang, n = wilcoxon(pv[best].values, pv[m].values)
            tanda = 'nyata' if (p == p and p < 0.05) else 'TIDAK nyata'
            print(f'    {best} vs {m:14s} menang {menang}/{n}  p={p:.4g}  {tanda}')


def ablasi(a, r):
    if a is None:
        return
    garis('ABLASI TERBALIK - berapa yang HILANG bila satu komponen dimatikan')
    if r is None:
        print('  Butuh opt_rolling.csv sebagai acuan. Belum ada.')
        return
    acuan = r[r['model'].isin(ML3)].pivot_table(
        index=['leaf', 'model', 'origin'], values='mase')
    rows = []
    for arm in sorted(a['arm'].unique()):
        sub = a[a['arm'] == arm].pivot_table(
            index=['leaf', 'model', 'origin'], values='mase')
        j = acuan.join(sub, lsuffix='_opt', rsuffix='_arm', how='inner').dropna()
        if not len(j):
            continue
        opt, off = j['mase_opt'].values, j['mase_arm'].values
        delta = 100.0 * (np.mean(off) - np.mean(opt)) / np.mean(opt)
        p, menang, n = wilcoxon(opt, off)
        rows.append({'lengan': arm, 'MASE_optimal': np.mean(opt),
                     'MASE_dimatikan': np.mean(off), 'selisih_%': delta,
                     'p': p, 'n': n})
    if not rows:
        print('  Belum ada sel ablasi yang berpasangan dengan blok uji.')
        return
    print(pd.DataFrame(rows).round(4).to_string(index=False))
    print('\n  selisih_% positif = konfigurasi optimal LEBIH BAIK sebanyak itu.')
    print('  Angka inilah yang jadi isi Bagian 4.3 versi revisi.')


def selesai():
    """Satu jawaban untuk 'sudah selesai belum?' atas kelima tahap.

    Target dihitung dari NLEAF, jadi ikut panel yang dipakai. Berkas CSV
    dihitung barisnya (tanpa header); dua tahap terakhir hanya perlu ada.
    """
    garis('STATUS KELIMA TAHAP')
    N = NLEAF
    TARGET = [
        ('1 penyetelan',  'opt_tuned.csv',      N * 3),
        ('2 blok uji',    'opt_rolling.csv',    N * 10 * 30),
        ('2b headline',   'headline.csv',       N * 10),
        ('3 ablasi balik', 'opt_ablasi.csv',    N * 3 * 3 * 30),
        ('4a jumlah fitur', 'sisa_kablasi.csv', N * 3 * 6 * 30),
        ('4b data pasar', 'sisa_eksternal.csv', N * 3 * 2 * 2 * 2 * 30),
    ]
    tuntas = True
    for nama, berkas, target in TARGET:
        jalan = os.path.join(H, berkas)
        n = 0
        if os.path.exists(jalan):
            with open(jalan) as f:
                n = max(0, sum(1 for _ in f) - 1)
        pct = 100 * n / target if target else 0
        tanda = 'OK   ' if n >= target else '     '
        if n < target:
            tuntas = False
        print(f'  {tanda}{nama:16s} {berkas:20s} {n:6d} / {target:6d}  {pct:5.1f}%')

    for nama, berkas in (('5 SHAP', 'shap_ringkas.json'),
                         ('6 uji statistik', 'uji_statistik.json')):
        ada = os.path.exists(os.path.join(H, berkas))
        if not ada:
            tuntas = False
        print(f'  {"OK   " if ada else "     "}{nama:16s} {berkas:20s} '
              f'{"ada" if ada else "belum ada"}')

    print()
    if tuntas:
        print('  SELESAI. Kirim isi folder ini untuk penyusunan naskahnya:')
        print(f'    {H}')
    else:
        print('  BELUM SELESAI. Kalau prosesnya sudah tidak berjalan, jalankan')
        print('  lagi perintah yang sama - semua tahap melanjutkan dari checkpoint:')
        print('    python scripts/paper/revisi/jalankan_semua.py gabung')
        print('\n  Cek prosesnya masih hidup atau tidak:')
        print('    pgrep -af "[j]alankan_semua"')
    return tuntas


def main():
    if not os.path.isdir(H):
        print(f'Folder hasil belum ada: {H}')
        print('Jalankan dulu: python scripts/paper/revisi/rerun_optimal.py')
        return 1
    selesai()
    t, r, a = kemajuan()
    tabel_setelan(t)
    peringkat(r)
    ablasi(a, r)
    print('\n' + '=' * 68)
    print('Kirim isi folder hasil/ untuk penyusunan tabel dan naskahnya.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
