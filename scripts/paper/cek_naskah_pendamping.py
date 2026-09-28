"""Audit INTERNAL naskah pendamping, tanpa masukan yang tidak ada di repo.

    python3 scripts/paper/cek_naskah_pendamping.py

KENAPA AUDIT INTERNAL, BUKAN VERIFIKASI. build_paper.js hanya MENATA ULANG
sebuah .docx; ia tidak menghitung satu angka pun. Prosanya beku di
doc_items.json, dan doc_items.json, h1_facts2.json, fig/ serta paperwt tidak
ada di repo. Jadi angka di naskah ini tidak punya jalan kembali ke datanya -
tidak seperti scripts/paper/naskah/, yang menurunkan setiap angka dari
tables.json dan punya cek_draft.py untuk memeriksanya.

Yang MASIH bisa diperiksa tanpa masukan apa pun, dan diperiksa di sini:

  1. ARITMETIKA. Angka agregat yang diketik di bagian yang ditulis ulang punya
     hubungan yang bisa diuji. Dekomposisi protokol pernah salah di sini:
     abstrak menyebut 10,1 dan 7,3 sebagai "percentage points" dari 18,1
     padahal 10,1 + 7,3 = 17,4. Ketiganya diukur terhadap penyebut berbeda dan
     BERLIPAT, tidak menjumlah.

  2. PENOMORAN TABEL. TMAP memetakan nomor lama ke baru dan T memuat nomor baru
     untuk teks yang ditulis ulang. Target ganda, lompatan nomor, atau sisi kiri
     PHRASE yang memuat nomor tabel (yang akan terpetakan dua kali, karena
     regex nomor jalan lebih dulu) semuanya merusak rujukan silang.

  3. ANGKA YANG DIPAKAI ULANG. Satu nilai yang muncul untuk dua besaran berbeda
     di paragraf yang sama terbaca seperti salah ketik. Dilaporkan untuk
     diperiksa manusia, bukan digagalkan.

Keluar dengan kode 1 kalau 1 atau 2 menemukan masalah.
"""
import math
import os
import re
import sys
from collections import Counter

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_paper.js')
if not os.path.exists(SRC):
    raise SystemExit(f'BERHENTI: {SRC} tidak ada.')
src = open(SRC, encoding='utf-8').read()

gagal, catatan = [], []


def fail(label, pesan):
    gagal.append(f'{label}: {pesan}')


# ----------------------------------------------------------------- 1 aritmetika
print('1. aritmetika angka agregat')

# Rata-rata MASE ketiga protokol, dibaca dari prosa supaya pemeriksa ini ikut
# basi kalau angkanya diperbarui tanpa memperbarui kalimatnya.
m = re.search(r'mean MASE is ([\d.]+) under teacher-forcing, ([\d.]+) under the '
              r'direct strategy and ([\d.]+) under recursion', src)
if not m:
    fail('protokol', 'kalimat rata-rata MASE ketiga protokol tidak ketemu - '
                     'kalau kalimatnya diubah, perbarui pemeriksa ini')
else:
    tf, dr, rc = (float(x) for x in m.groups())
    pen_total = 100 * (rc - tf) / tf          # recursion vs teacher-forcing
    pen_akum = 100 * (rc - dr) / dr           # recursion vs direct
    pen_bocor = 100 * (dr - tf) / tf          # direct vs teacher-forcing
    print(f'   tf={tf} direct={dr} recursion={rc}')
    print(f'   total {pen_total:.2f}%  akumulasi {pen_akum:.2f}%  '
          f'kebocoran {pen_bocor:.2f}%')

    for nama, hitung in (('total', pen_total), ('akumulasi', pen_akum),
                         ('kebocoran', pen_bocor)):
        if not re.search(rf'{hitung:.1f} per cent', src):
            fail(f'protokol/{nama}',
                 f'{hitung:.1f} per cent tidak muncul di prosa')

    # Dekomposisinya BERLIPAT. Kalau prosa memakai "percentage points" untuk
    # kedua komponen, ia menyiratkan penjumlahan - dan penjumlahannya salah.
    jumlah = pen_akum + pen_bocor
    kali = 100 * ((1 + pen_akum / 100) * (1 + pen_bocor / 100) - 1)
    print(f'   jumlah {jumlah:.2f}%  vs  berlipat {kali:.2f}%  '
          f'(total {pen_total:.2f}%)')
    if abs(kali - pen_total) > 0.05:
        fail('protokol/dekomposisi',
             f'berlipat {kali:.2f}% tidak cocok dengan total {pen_total:.2f}% - '
             'salah satu angkanya salah')
    if abs(jumlah - pen_total) > 0.05 and re.search(
            r'([\d.]+) percentage points are genuine', src):
        fail('protokol/dekomposisi',
             f'prosa menyebut "percentage points" padahal komponennya tidak '
             f'menjumlah ({jumlah:.1f} vs {pen_total:.1f}); dekomposisinya berlipat')

# Segmen horizon: persentase harus cocok dengan pasangan MASE-nya.
m = re.search(r'([\d.]+) against ([\d.]+), a penalty of (\d+) per cent', src)
if m:
    a, b, p = float(m.group(1)), float(m.group(2)), int(m.group(3))
    hit = 100 * (a - b) / b
    print(f'   horizon: {a} vs {b} -> {hit:.2f}% (prosa {p}%)')
    if abs(hit - p) > 0.5:
        fail('horizon', f'{a} vs {b} memberi {hit:.2f}%, prosa menulis {p}%')

# "more than half the distance": 29% harus benar-benar lebih dari separuh
# jarak terbaik-terburuk.
m = re.search(r'(\d+) per cent reduction in scaled error beyond', src)
m2 = re.search(r'non-stacked methods in Table \d+ \(([\d.]+) against ([\d.]+)\)', src)
if m and m2:
    red = int(m.group(1))
    best, worst = float(m2.group(1)), float(m2.group(2))
    separuh = 50 * (worst - best) / best
    print(f'   jarak terbaik-terburuk {100*(worst-best)/best:.1f}%, '
          f'separuhnya {separuh:.1f}%, klaim {red}%')
    if red <= separuh:
        fail('jarak', f'{red}% TIDAK lebih dari separuh ({separuh:.1f}%)')

# Uji permutasi eksak: p untuk rho = -1 adalah 1/n!, jadi p memaksa n.
# Naskah boleh menulis "p = 0.00139" atau "p = 1/6! = 0.00139"; bentuk kedua
# membuat regex yang hanya mencari angka pertama menangkap "1" dari "1/6!".
m = re.search(r'exact permutation p = (?:1/\d+!\s*=\s*)?([\d.]+)', src)
if m:
    p = float(m.group(1))
    n = next((k for k in range(2, 15)
              if abs(1 / math.factorial(k) - p) < 0.5 * p / 100), None)
    if n:
        print(f'   permutasi eksak p={p} -> 1/{n}! , jadi {n} item diperingkat')
        # Jumlahnya boleh ditulis angka atau huruf; versi pertama pemeriksa ini
        # hanya mencari digit, jadi ia akan tetap mengeluh setelah naskah
        # menyebutnya dengan kata ("six methods").
        EJA = {2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven',
               8: 'eight', 9: 'nine', 10: 'ten', 11: 'eleven', 12: 'twelve'}
        bentuk = rf'(?:{n}|{EJA.get(n, n)})'
        if not re.search(rf'\b{bentuk}\b[^.]{{0,80}}methods', src, re.I):
            catatan.append(
                f'p = {p} memaksa TEPAT {n} item yang diperingkat (1/{n}! = '
                f'{1/math.factorial(n):.6f}), tapi jumlah metode dalam '
                f'pemeringkatan itu tidak disebut di prosa. Abstrak menyebut '
                f'"ten methods" lalu "once the random walk is set aside", yang '
                f'terbaca sembilan; 1/9! = {1/math.factorial(9):.2e}.')
    else:
        catatan.append(f'p = {p} tidak cocok dengan 1/n! untuk n <= 14 - '
                       'periksa apakah ia memang uji permutasi eksak atas rho = -1')

# 54 unit harus benar-benar hasil kali seri x jendela.
m = re.search(r'on (\d+) daily foreign-exchange transaction-flow series', src)
mj = re.search(r'rolling-origin validation with (\w+) windows', src)
KATA = {'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6}
if m and mj:
    nseri, njen = int(m.group(1)), KATA.get(mj.group(1).lower())
    unit = sorted({int(x) for x in re.findall(r'of (\d+) series-window units', src)}
                  | {int(x) for x in re.findall(r'of the (\d+) estimations', src)})
    print(f'   {nseri} seri x {njen} jendela = {nseri*njen}; '
          f'unit yang disebut prosa: {unit}')
    for u in unit:
        if njen and u != nseri * njen:
            fail('unit', f'prosa menyebut {u} unit tapi {nseri} x {njen} = {nseri*njen}')

# ------------------------------------------------------------- 2 penomoran
print('\n2. penomoran tabel')
TMAP = {int(k): int(v) for k, v in re.findall(
    r'(\d+):\s*(\d+)', re.search(r'const TMAP = \{([^}]*)\}', src).group(1))}
T = {k: int(v) for k, v in re.findall(
    r'(\w+):\s*(\d+)', re.search(r'const T = \{(.*?)\n\};', src, re.S).group(1))}

ganda = {k: v for k, v in Counter(TMAP.values()).items() if v > 1}
if ganda:
    fail('TMAP', f'target ganda: {ganda}')
ganda = {k: v for k, v in Counter(T.values()).items() if v > 1}
if ganda:
    fail('T', f'nomor ganda: {ganda}')

nomor = sorted(T.values())
if nomor != list(range(1, max(nomor) + 1)):
    fail('T', f'nomor tidak lengkap 1..{max(nomor)}: {nomor}')
print(f'   {len(T)} tabel, nomor 1..{max(nomor)} tanpa ganda maupun lompatan')
baru = sorted(set(T.values()) - set(TMAP.values()))
print(f'   ditulis baru (tidak dipetakan dari lama): {baru} -> '
      f'{[k for k, v in T.items() if v in baru]}')

# Sisi KIRI PHRASE tidak boleh memuat nomor tabel: regex nomor jalan lebih
# dulu, jadi nomor di sisi kiri sudah tergeser ketika PHRASE dijalankan dan
# penggantiannya tidak akan pernah cocok.
ph = re.search(r'const PHRASE = \[(.*?)\n\];', src, re.S).group(1)
pasang = re.findall(r"\[\s*'((?:[^'\\]|\\.)*)'\s*,\s*\n?\s*'((?:[^'\\]|\\.)*)'\s*\]", ph)
kiri = [a for a, _ in pasang if re.search(r'Tabl?e\s+\d+', a)]
if kiri:
    fail('PHRASE', f'{len(kiri)} sisi kiri memuat nomor tabel (akan terpetakan '
                   f'dua kali): {kiri[:2]}')
print(f'   {len(pasang)} pasang PHRASE, nol sisi kiri memuat nomor tabel')

luar = [r for r in sorted({int(x) for x in re.findall(r'Table\s+(\d+)', src)})
        if r > max(nomor)]
if luar:
    fail('rujukan', f'Table {luar} di luar 1..{max(nomor)}')

# -------------------------------------------------------- 3 angka dipakai ulang
print('\n3. angka yang dipakai ulang di satu paragraf')
for blok in re.findall(r"'((?:[^'\\]|\\.){400,})'", src):
    angka = re.findall(r'(?<![\w.])(\d+\.\d+) per cent', blok)
    for v, c in Counter(angka).items():
        if c > 1:
            catatan.append(f'{v} per cent muncul {c}x di satu paragraf: '
                           f'"...{blok[:70]}..."')

# ------------------------------------------------------------------- laporan
print()
if gagal:
    print(f'GAGAL: {len(gagal)} masalah')
    for g in gagal:
        print(f'  - {g}')
else:
    print('aritmetika dan penomoran: nol masalah')
if catatan:
    print(f'\nperlu diperiksa manusia ({len(catatan)}):')
    for c in catatan:
        print(f'  - {c}')
print('\nCATATAN: pemeriksa ini TIDAK memverifikasi angka terhadap data. '
      'Naskah ini\nmenata ulang .docx yang prosanya beku, dan masukannya tidak '
      'ada di repo.')
sys.exit(1 if gagal else 0)
