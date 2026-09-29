"""Bandingkan angka dan desain ANTARA kedua naskah, dan dengan kodenya.

    python3 scripts/paper/cek_antar_naskah.py

KENAPA PERLU. Kedua naskah memakai data yang sama dan sebagian metode yang sama,
lalu naskah utama sekarang MENGUTIP angka horizon 60 hari di 5.2. Kalau keduanya
dikirim berpasangan, pengulas akan membandingkannya - dan setiap klaim yang
berbeda tanpa penjelasan akan terlihat.

Yang TIDAK bisa diperiksa di sini: angka naskah pendamping terhadap datanya.
Prosanya beku di doc_items.json dan masukannya tidak ada di repo. Yang
dibandingkan adalah angka yang DIKETIK di build_paper.js terhadap tables.json,
terhadap data panel, dan terhadap konfigurasi kode.

    utama      = scripts/paper/naskah/       (horizon 1 hari, 15 sel gabungan)
    pendamping = scripts/paper/build_paper.js (horizon 60 hari, 18 sel asli)
"""
import json
import os
import re
import sys

import pandas as pd

DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(DIR))
sys.path.insert(0, os.path.join(DIR, 'naskah'))
import jalan  # noqa: E402

PEND = os.path.join(DIR, 'build_paper.js')
AB60 = os.path.join(DIR, 'naskah', 'ablasi_h60.json')
for p in (PEND, jalan.TABLES):
    if not os.path.exists(p):
        raise SystemExit(f'BERHENTI: {p} tidak ada.\n'
                         'Untuk tables.json jalankan dulu buat_tables.py.')
src = open(PEND, encoding='utf-8').read()
T = json.load(open(jalan.TABLES))
A60 = json.load(open(AB60)) if os.path.exists(AB60) else None

gagal, catatan = [], []
fail = lambda l, m: gagal.append(f'{l}: {m}')

# ------------------------------------------------------------------- 1 panel
print('1. panel')
m = re.search(r'on (\d+) daily foreign-exchange transaction-flow series observed '
              r'over (\d+) business days \(([^)]*)\)', src)
if not m:
    fail('panel', 'kalimat panel naskah pendamping tidak ketemu')
else:
    nsp, nhp, rentang = int(m.group(1)), int(m.group(2)), m.group(3)
    print(f'   pendamping: {nsp} seri, {nhp} hari, {rentang}')
    print(f'   utama     : {T["n_leaf"]} sel, {T["n_hari"]} hari, '
          f'{T["tgl_awal"]} -> {T["tgl_akhir"]}')
    if nhp != T['n_hari']:
        fail('panel/hari', f'pendamping {nhp} vs utama {T["n_hari"]}')
    # Tanggalnya harus sama; ditulis beda format, jadi dibandingkan sebagai tanggal.
    try:
        a, b = [pd.Timestamp(x.strip()) for x in rentang.split(' to ')]
        if (str(a.date()), str(b.date())) != (T['tgl_awal'], T['tgl_akhir']):
            fail('panel/tanggal',
                 f'pendamping {a.date()}..{b.date()} vs utama '
                 f'{T["tgl_awal"]}..{T["tgl_akhir"]}')
    except Exception as e:
        catatan.append(f'rentang tanggal pendamping tidak terbaca ({e})')
    # Jumlah sel BERBEDA dan itu benar - naskah utama menggabung tiga pasang.
    # Yang harus ada: penjelasannya di naskah utama.
    utama_js = open(os.path.join(DIR, 'naskah', 'build.js'), encoding='utf-8').read()
    if nsp != T['n_leaf']:
        print(f'   beda jumlah sel {nsp} vs {T["n_leaf"]} (penggabungan)')
        if not re.search(r'(?:aggregates|merges) of two reporting categories', utama_js):
            fail('panel/sel', f'pendamping {nsp} sel vs utama {T["n_leaf"]}, '
                              'dan naskah utama tidak menjelaskan penggabungannya')
        if nsp - T['n_leaf'] != 3:
            fail('panel/sel', f'selisihnya {nsp - T["n_leaf"]}, bukan 3 pasang '
                              'yang digabung seperti dinyatakan 3.2')

# --------------------------------------------------------------------- 2 MASE
print('\n2. definisi MASE')
pola = r'mean absolute first difference'
for nama, s in (('pendamping', src), ('utama', utama_js)):
    print(f'   {nama}: {"cocok" if re.search(pola, s) else "TIDAK KETEMU"}')
    if not re.search(pola, s):
        fail(f'MASE/{nama}', 'definisi penyebut "mean absolute first difference" '
                             'tidak ada - kalau penyebutnya beda, persentase '
                             'kedua naskah tidak sebanding')

# ----------------------------------------------------------------- 3 metode
print('\n3. himpunan metode')
# ARIMA dan AutoARIMA adalah ARIMAForecaster yang SAMA, hanya beda nama di dua
# naskah. Kalau alias ini dilupakan, irisannya terhitung 6 padahal 7.
ALIAS = {'AutoARIMA': 'ARIMA'}
utama_set = {r['model'] for r in T['e2_summary']}
m = re.search(r'evaluate (\w+) methods — (\w+) traditional and (\w+) machine-learning', src)
KATA = {'ten': 10, 'nine': 9, 'eight': 8, 'seven': 7, 'six': 6, 'five': 5,
        'four': 4, 'three': 3, 'two': 2, 'one': 1}
if m:
    np_, ntr, nml = (KATA.get(x.lower()) for x in m.groups())
    print(f'   pendamping menyebut {np_} metode ({ntr} tradisional + {nml} ML)')
    print(f'   utama      memakai  {len(utama_set)} metode')
    if ntr and nml and ntr + nml != np_:
        fail('metode', f'{ntr} + {nml} != {np_}')
    if np_ == len(utama_set):
        catatan.append(
            f'KEDUA naskah menyebut "{m.group(1)} methods" tapi himpunannya '
            f'berbeda. Kalau dikirim berpasangan, sebutkan bahwa keduanya bukan '
            f'perbandingan yang sama.')
# Himpunan metode pendamping diambil dari run_one_step.py, BUKAN dari prosa
# build_paper.js: prosanya sebagian besar beku di doc_items.json yang tidak ada
# di repo, jadi menyaring berdasarkan "nama muncul di build_paper.js" akan
# melewatkan hampir semuanya dan melaporkan irisan yang terlalu kecil.
_ros = open(os.path.join(DIR, 'run_one_step.py'), encoding='utf-8').read()
_nama = []
for var in ('FUNCFORM', 'LAGBASED'):
    mv = re.search(rf'^{var} = \[(.*?)\]', _ros, re.M | re.S)
    if mv:
        _nama += re.findall(r"'([^']+)'", mv.group(1))
if not _nama:
    catatan.append('FUNCFORM/LAGBASED tidak terbaca dari run_one_step.py - '
                   'himpunan metode pendamping tidak dibandingkan')
pend_set = {ALIAS.get(x, x) for x in _nama}
print(f'   pendamping (dari run_one_step.py): {len(pend_set)} metode')
print(f'   irisan (setelah alias): {sorted(utama_set & pend_set)}')
print(f'   hanya utama           : {sorted(utama_set - pend_set)}')
print(f'   hanya pendamping      : {sorted(pend_set - utama_set)}')
# Nama metode disamakan lewat DUA mekanisme, dan keduanya harus ada: entri
# PHRASE mengurus teks beku dari doc_items.json, NAMA_METODE mengurus kolom
# Method tabel satu langkah yang dibangun langsung dari h1_facts2.json dan tidak
# lewat fix(). Memeriksa sekadar "apakah kata AutoARIMA ada di build_paper.js"
# akan salah: sisi KIRI aturan renamenya sendiri memuat kata itu.
for mek, pola in (('PHRASE', r"\['AutoARIMA',\s*'ARIMA'\]"),
                  ('NAMA_METODE', r'NAMA_METODE\s*=\s*\{[^}]*AutoARIMA:\s*.ARIMA.')):
    if not re.search(pola, src):
        fail('nama/AutoARIMA',
             f'aturan rename {mek} tidak ada, jadi nama metode kedua naskah '
             f'berbeda untuk ARIMAForecaster yang SAMA')
# Prosa yang DIKETIK di build_paper.js tidak boleh lagi memuat nama lama: ia
# memang lewat fix(), tapi membiarkannya berarti sumbernya dan keluarannya beda.
#
# Komentar dibuang lebih dulu. Versi pertama pemeriksa ini hanya melewati baris
# yang diawali "//", sehingga ia menandai penjelasan di dalam komentar BLOK yang
# memang harus menyebut nama lamanya - positif palsu atas dokumentasinya sendiri.
tanpa_komentar = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
tanpa_komentar = re.sub(r'^\s*//.*$', '', tanpa_komentar, flags=re.M)
hard = [ln for ln in tanpa_komentar.split('\n')
        if 'AutoARIMA' in ln and not re.search(r"NAMA_METODE|\['AutoARIMA'", ln)]
if hard:
    fail('nama/AutoARIMA', f'{len(hard)} baris prosa yang diketik masih memakai '
                           f'"AutoARIMA": {hard[0].strip()[:90]}')
# Judul dibangun dari IT[0] dan pernah memakainya MENTAH, satu-satunya potong
# teks beku yang tidak lewat fix() - artinya rename dan penomoran tabel akan
# terlewat di situ.
if re.search(r'text:\s*IT\[0\]\.text', src):
    fail('nama/judul', 'judul memakai IT[0].text mentah, tidak lewat fix() - '
                       'rename maupun penomoran tabel akan terlewat di judul')
# APUVA punya cacat yang sama, tapi naskah utama MENYATAKAN aliasnya, jadi
# pembaca kedua naskah bisa menghubungkannya. Dilaporkan, tidak digagalkan.
if re.search(r'\bAPUVA\b', _ros) and 'SeasonalDecomp' in utama_set:
    if re.search(r'known internally as the APUVA algorithm', utama_js):
        print('   APUVA: pendamping memakai "APUVA", utama "SeasonalDecomp" - '
              'tapi utama MENYATAKAN aliasnya')
    else:
        catatan.append('pendamping memakai "APUVA", utama "SeasonalDecomp" untuk '
                       'APUVAForecaster yang sama, dan aliasnya tidak dinyatakan '
                       'di mana pun.')

# ------------------------------------------------- 4 jumlah fitur dan kodenya
print('\n4. jumlah fitur yang dipertahankan')
try:
    sys.path.insert(0, REPO)
    from utils.feature_config import TOP_K_FEATURES as KODE
except Exception as e:
    KODE = None
    catatan.append(f'TOP_K_FEATURES tidak terbaca dari kode ({e})')
k_utama = T['ablation_best']
k_pend = 25 if re.search(r'of twenty-five retained features', src) else None
print(f'   utama melaporkan k terbaik  = {k_utama}')
print(f'   pendamping melaporkan       = {k_pend}')
print(f'   default di kode SEKARANG    = {KODE}')
if A60:
    print(f'   ablasi h=60 memilih         = {A60["terbaik_k"]}')
    # Inilah inti argumen lintas-horizon naskah utama: k terbaik BERBEDA menurut
    # horizon. Kalau suatu saat keduanya sama, kalimat di 5.2 kehilangan dasarnya.
    if A60['terbaik_k'] == k_utama:
        fail('fitur', f'ablasi h=60 dan h=1 sama-sama memilih k={k_utama}, '
                      'jadi klaim ketergantungan horizon di 5.2 tidak lagi berdasar')
    d12 = next((r['delta'] for r in T['ablation'] if r['k'] == A60['terbaik_k']), None)
    if d12 is not None:
        print(f'   k={A60["terbaik_k"]} di h=1: {d12:+.2f}% (positif = lebih buruk)')
if KODE is not None and KODE != k_utama:
    catatan.append(
        f'default kode TOP_K_FEATURES = {KODE}, yang berasal dari ablasi horizon '
        f'{A60["horizon"] if A60 else 60} hari, BUKAN dari naskah utama yang '
        f'memakai k={T.get("ablation_acuan", 25)} (terbaik di ablasinya k={k_utama}) dan menemukan k={KODE} '
        f'{d12:+.2f}% lebih buruk di h=1. Siapa pun yang menjalankan kode ini '
        f'apa adanya untuk ramalan satu hari memakai setelan yang tidak didukung '
        f'naskah utama - ini justru contoh "tune at the horizon you will run" '
        f'pada kode sendiri.')

# ------------------------------------------------------------- 5 inversi h1/h60
print('\n5. inversi peringkat h=1 vs h=60')
mean1 = T['blok_validasi']['mean_panjang'] if T.get('blok_validasi') else None
m = re.search(r'\(RandomForest, in-sample MASE [\d.]+\) is the worst out of sample '
              r'\(([\d.]+)\), while the worst-fitting model \(Prophet, [\d.]+\) is '
              r'the best \(([\d.]+)\)', src)
if mean1 and m:
    urut = sorted(mean1, key=lambda k: mean1[k])
    rf, pr = urut.index('RandomForest') + 1, urut.index('Prophet') + 1
    print(f'   h=1 (utama): RandomForest peringkat {rf}, Prophet peringkat {pr}')
    print(f'   h=60 (pendamping): RandomForest TERBURUK {m.group(1)}, '
          f'Prophet TERBAIK {m.group(2)}')
    if rf >= pr:
        fail('inversi', f'di h=1 RandomForest ({rf}) TIDAK lebih baik daripada '
                        f'Prophet ({pr}), jadi inversi yang diklaim pendamping '
                        'tidak didukung naskah utama')
    else:
        print('   -> searah: inversi konsisten di kedua naskah')

# ------------------------------------ 6 desain ablasi h=60 vs naskah pendamping
print('\n6. desain ablasi h=60 vs naskah pendamping')
mj = re.search(r'rolling-origin validation with (\w+) windows', src)
njen = KATA.get(mj.group(1).lower()) if mj else None
if njen is None:
    catatan.append('jumlah jendela naskah pendamping tidak terbaca dari prosanya')
if A60:
    print(f'   ablasi: {A60["n_leaf"]} sel x {A60["n_jendela"]} jendela x '
          f'{A60["n_model"]} model = {A60["n_unit"]}')
    print(f'   pendamping: {nsp} seri x {njen} jendela')
    if A60['n_leaf'] != nsp:
        fail('ablasi', f'ablasi memakai {A60["n_leaf"]} sel, pendamping {nsp}')
    if njen and A60['n_jendela'] != njen:
        fail('ablasi', f'ablasi {A60["n_jendela"]} jendela, pendamping {njen}')

# ------------------------------------------------- 7 sel degenerat di kedua sisi
print('\n7. sel degenerat A.1.b')
panel = os.path.join(REPO, 'data', 'processed', 'sdv-wide.csv')
if os.path.exists(panel):
    d = pd.read_csv(panel)
    tgl = [c for c in d.columns if c[:2] == '20']
    r = d[d.Row_ID == 'A.1.b']
    if len(r):
        v = pd.to_numeric(r.iloc[0][tgl], errors='coerce')
        z = 100 * (v == 0).sum() / len(tgl)
        print(f'   A.1.b nol pada {z:.2f}% hari (data)')
        mu = re.search(r'zero on ([\d.]+) per cent of days', utama_js)
        if mu and abs(float(mu.group(1)) - z) > 0.05:
            fail('A.1.b', f'naskah utama menulis {mu.group(1)}%, data {z:.2f}%')
        # Pendamping MEMASUKKAN sel ini; utama membuangnya. Naskah utama harus
        # mengatakannya, karena ia mengutip angka horizon dari ablasi 18 sel.
        if A60 and not re.search(r'include the degenerate series this paper', utama_js):
            fail('A.1.b', 'naskah utama mengutip ablasi 18 sel tapi tidak '
                          'menyatakan bahwa sel degenerat ikut di dalamnya')
else:
    catatan.append(f'{panel} tidak ada - pangsa nol A.1.b tidak diperiksa')

# --------------------------------------------------------------- 8 libur
print('\n8. penanganan hari libur')
ros = open(os.path.join(DIR, 'run_one_step.py'), encoding='utf-8').read()
rop = open(os.path.join(DIR, 'revisi', 'rerun_optimal.py'), encoding='utf-8').read()
pend_libur = bool(re.search(r'NaiveForecaster\(hol', ros))
utama_libur = bool(re.search(r'NaiveForecaster\(hol', rop))
print(f'   pendamping meneruskan libur ke peramal : {pend_libur}')
print(f'   utama      meneruskan libur ke peramal : {utama_libur}')
if pend_libur != utama_libur:
    try:
        from utils.feature_config import ENABLE_HOLIDAY_FEATURES
        import utils.feature_config as fc
        C = [v for k, v in vars(fc).items()
             if isinstance(v, dict) and 'cross_series_features' in v][0]
        mati = (not ENABLE_HOLIDAY_FEATURES
                and not C['holiday_features'].get('enabled'))
    except Exception:
        mati = False
    if mati:
        print('   -> BEDA, tapi MATI: holiday_features dan '
              'ENABLE_HOLIDAY_FEATURES keduanya False, dan p1() mengambil nilai '
              'pertama tanpa melihat label tanggal.')
        catatan.append(
            'kedua studi mengonfigurasi libur secara berbeda - pendamping '
            'meneruskan load_holidays() ke setiap peramal, utama tidak. Sekarang '
            'inert karena holiday_features dan ENABLE_HOLIDAY_FEATURES sama-sama '
            'False. JANGAN menyamakan salah satu skrip tanpa menjalankan ulang: '
            'menyalakan flag itu akan mengubah angka di satu naskah saja.')
    else:
        fail('libur', 'kedua studi meneruskan libur secara berbeda DAN '
                      'fiturnya aktif - angkanya tidak sebanding')

# ------------------------------------------------------------------- laporan
print()
if gagal:
    print(f'GAGAL: {len(gagal)} masalah')
    for g in gagal:
        print(f'  - {g}')
else:
    print('konsistensi antar-naskah: nol masalah')
if catatan:
    print(f'\nperlu diputuskan manusia ({len(catatan)}):')
    for c in catatan:
        print(f'  - {c}')
sys.exit(1 if gagal else 0)
