"""Periksa angka naskah terhadap sumbernya, dan laporkan yang tidak terlacak.

    python scripts/paper/naskah/cek_draft.py

TIGA PEMERIKSAAN, dan yang kedua adalah yang paling berguna.

  1. KLAIM KUNCI. Sejumlah angka yang wajib muncul di badan naskah dicari di
     teksnya. Formatnya harus sama persis dengan yang dicetak build.js -
     versi pertama pemeriksa ini menuntut tiga desimal padahal naskah mencetak
     satu, lalu melaporkan 21 kegagalan palsu. Pemeriksa yang berbohong soal
     kegagalan lebih buruk daripada tidak ada pemeriksa.

  2. SEL TABEL. Setiap angka di tabel dibandingkan NUMERIK dengan nilai
     sumbernya, bukan sebagai teks, jadi bebas dari asumsi pembulatan.

  3. ANGKA YATIM. Setiap angka di prosa yang tidak bisa diturunkan dari
     tables.json dilaporkan untuk diperiksa manusia. Sebagian besar akan
     berupa tahun sitasi dan nomor halaman; yang bukan itu layak dicurigai
     sebagai angka usang yang tertinggal dari draf sebelumnya.
"""
import json, os, re, sys
from docx import Document

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jalan import TABLES, DOCX

for j in (TABLES, DOCX):
    if not os.path.exists(j):
        raise SystemExit(f'BERHENTI: {j} belum ada.')
T = json.load(open(TABLES))
d = Document(DOCX)

prosa = '\n'.join(p.text for p in d.paragraphs)
tbs = [[[c.text.strip() for c in r.cells] for r in t.rows] for t in d.tables]
teks = prosa + '\n' + '\n'.join(' | '.join(r) for t in tbs for r in t)
teks = teks.replace('—', '-').replace('−', '-')

ok, gagal = [], []
nf = lambda v, dp=3: f'{v:.{dp}f}'


def cek(label, jarum):
    (ok if str(jarum) in teks else gagal).append((label, jarum))


# ------------------------------------------------- 1. klaim kunci di prosa
g = T['tabel8b_gabungan']
cek('abstrak: penalti dinolkan', f"{g['delta_nol']:.1f}")
cek('abstrak: penalti disuplai', f"{g['delta_benar']:.1f}")
cek('abstrak: kerusakan hilang', f"{g['rusak_hilang_pct']:.0f}")
cek('abstrak: leaf membaik', str(T['n_leaf_membaik']))
cek('slot-kerusakan dinolkan rho', f"{T['slot_damage']['nol']['rho']:.3f}")
cek('slot-kerusakan disuplai rho', f"{T['slot_damage']['benar']['rho']:.3f}")
for k in ('Moving average', 'Lag', 'External'):      # hanya yang disebut prosa
    if k in T['shap_family']:
        cek(f'SHAP {k}', f"{T['shap_family'][k]:.1f}")
cek('slot lag rata', f"{T['mean_lag_slots']:.1f}")
cek('slot pasar rata', f"{T['mean_ext_slots']:.1f}")
cek('kandidat internal', str(T['pool_internal']))
cek('kandidat total', str(T['pool_total']))
cek('jumlah leaf', str(T['n_leaf']))
if T.get('arima_repro'):
    a = T['arima_repro']
    cek('ARIMA sel berbeda', str(a['sel_berbeda'].get('ARIMA', '')))
    cek('ARIMA mean lama', nf(a['mean_lama'], 4))
    cek('ARIMA mean baru', nf(a['mean_baru'], 4))
for nm in ('python', 'numpy', 'pandas', 'sklearn', 'lightgbm', 'xgboost'):
    if T['versi'].get(nm):
        cek(f'versi {nm}', T['versi'][nm])

# ------------------------------------------------------ 2. sel tabel, numerik
num = lambda s: (float(re.sub(r'[^0-9.\-]', '', s))
                 if re.search(r'\d', s) else None)
n_sel, beda = 0, []


def judul(*awal):
    for t in tbs:
        if t and t[0][:len(awal)] == list(awal):
            return t
    return None


def banding(tag, got, want, tol=5e-4):
    global n_sel
    n_sel += 1
    if got is None or abs(got - want) > tol:
        beda.append(f'{tag}: naskah {got} vs sumber {want}')


NICE = {'Random forest': 'RandomForest', 'LightGBM': 'LightGBM',
        'XGBoost': 'XGBoost', 'ARIMA': 'ARIMA', 'Croston': 'Croston',
        'Prophet': 'Prophet', 'Random walk': 'Naive', 'RW w/ drift': 'NaiveDrift',
        'Rolling mean': 'NaiveMean', 'Seasonal decomp': 'SeasonalDecomp'}

t = judul('Selector', 'k', 'Market off')
if t:
    src = {(('univariate' if r['beta'] == 0 else 'mRMR'), str(r['k'])): r
           for r in T['tabel8b']}
    for row in t[1:]:
        r = T['tabel8b_gabungan'] if row[0] == 'pooled' else src.get((row[0], row[1]))
        if not r:
            continue
        for kol, key in ((2, 'mati'), (3, 'nol'), (5, 'benar')):
            banding(f'T9 {row[0]}/{row[1]} {key}', num(row[kol]), round(r[key], 3))
        banding(f'T9 {row[0]}/{row[1]} recovered', num(row[7]),
                round(r['rusak_hilang_pct']), 0.5)

t = judul('Component removed')
if t:
    src = {r['component']: r for r in T['reverse_ablation']}
    for row in t[1:]:
        r = src.get(row[0])
        if r:
            banding(f'T10 {row[0]} opt', num(row[1]), round(r['opt'], 4))
            banding(f'T10 {row[0]} off', num(row[2]), round(r['off'], 4))
            banding(f'T10 {row[0]} wins', num(row[4].split('/')[0]), r['wins'], 0.5)

# Tabel 5 dan 6 punya header yang IDENTIK - keduanya peringkat metode - dan
# angkanya memang berbeda karena desainnya berbeda. Versi pertama pemeriksa
# ini mencocokkan yang pertama ditemukan dengan sumber yang kedua, lalu
# melaporkan 16 ketidakcocokan palsu. Urutannya yang membedakan: tabel
# peringkat pertama adalah desain headline, yang kedua desain bergulir.
peringkat = [t for t in tbs
             if t and t[0][:3] == ['Rank', 'Method', 'Mean MASE'] and len(t) > 10]
for idx, (tb, kunci, tag) in enumerate(
        zip(peringkat, ('e1_summary', 'e2_summary'), ('T5', 'T6'))):
    src = {m['model']: m for m in T[kunci]}
    for row in tb[1:]:
        key = NICE.get(row[1])
        if key in src:
            banding(f'{tag} {row[1]} mean', num(row[2]), round(src[key]['mase'], 3))
            banding(f'{tag} {row[1]} median', num(row[3]), round(src[key]['med'], 3))

t = judul('Series', 'Purpose', 'FE only')
if t:
    p25 = {r['leaf']: r for r in T['per_leaf_ext'] if r['k'] == 25}
    p12 = {r['leaf']: r for r in T['per_leaf_ext'] if r['k'] == 12}
    for row in t[1:]:
        if row[0] in p25:
            banding(f'T8 {row[0]} fe12', num(row[2]), round(p12[row[0]]['fe'], 3))
            banding(f'T8 {row[0]} fe25', num(row[5]), round(p25[row[0]]['fe'], 3))
            banding(f'T8 {row[0]} slot', num(row[8]), p25[row[0]]['n_ext'], 0.5)

# ---------------------------------------------------- 3. angka yatim di prosa
sah = set()


def tambah(v):
    try:
        v = float(v)
    except Exception:
        return
    for dp in range(0, 5):
        sah.add(f'{v:.{dp}f}'); sah.add(f'{abs(v):.{dp}f}')


def jelajah(o):
    if isinstance(o, dict):
        for x in o.values():
            jelajah(x)
    elif isinstance(o, list):
        for x in o:
            jelajah(x)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        tambah(o)
        for m in (100*o, o/100, 100*(o-1), 100*(1-o)):
            tambah(m)


jelajah(T)
sah |= {str(i) for i in range(0, 2100)}          # tahun sitasi dan angka kecil
angka = re.findall(r'(?<![\w.])\d+(?:\.\d+)?(?![\w])', prosa)
yatim = sorted({a for a in angka if a not in sah}, key=float)

print(f'1. klaim kunci : {len(ok)} cocok, {len(gagal)} tidak ketemu')
for lbl, v in gagal:
    print(f'     {lbl:40s} {v}')
print(f'2. sel tabel   : {n_sel} dibandingkan, {len(beda)} tidak cocok')
for b in beda:
    print(f'     {b}')
print(f'3. angka yatim : {len(yatim)} di prosa tidak terlacak ke tables.json')
if yatim:
    print('     (tahun sitasi dan nomor halaman wajar muncul di sini)')
    for a in yatim:
        kal = [s.strip() for s in re.split(r'(?<=[.!?]) ', prosa)
               if re.search(r'(?<![\w.])' + re.escape(a) + r'(?![\w])', s)]
        print(f'     {a:>10s}  {kal[0][:110] if kal else ""}')

sys.exit(1 if (gagal or beda) else 0)
