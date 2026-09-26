"""Perkakas bersama untuk seluruh eksperimen satu-langkah naskah.

Semua eksperimen memakai definisi leaf, pemuat data, dan metrik yang sama dari
sini supaya angkanya konsisten antar tabel.
"""
import glob, os, re, sys, warnings

# ---------------------------------------------------------------------------
# JUMLAH UTAS DIKUNCI, DAN INI HARUS SEBELUM numpy DIIMPOR.
#
# Pemilihan ordo ARIMA deterministik kalau hasil titik mengambangnya sama, dan
# yang menggesernya adalah JUMLAH UTAS: banyak utas mengubah urutan penjumlahan
# BLAS, hasilnya bergeser di bit terakhir, lalu pencarian ordo mendarat di ordo
# lain. Terukur: menjalankan ulang kode dan data yang sama dengan jumlah utas
# berbeda menggeser 392 dari 450 sel ARIMA.
#
# Dengan utas dikunci ia bit-identik antar-run - diuji pada tiga leaf, 30
# origin masing-masing, dua run penuh, selisih maksimum 0,0. Jadi ini BUKAN
# soal seed; ARIMA di sini tidak memakai bilangan acak sama sekali.
#
# Harus di sini, sebelum numpy diimpor: pustaka BLAS membaca variabel ini saat
# dimuat, dan menyetelnya sesudah itu tidak berpengaruh.
#
# JBV_UTAS>1 mengembalikan multi-utas kalau kecepatan lebih penting daripada
# reprodusibilitas ARIMA. jalankan_paralel.py memang sudah menyetelnya ke 1
# per proses; ini membuat skrip yang dijalankan LANGSUNG ikut terlindungi.
# ---------------------------------------------------------------------------
_UTAS = os.environ.get('JBV_UTAS', '1')
for _v in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
           'NUMEXPR_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ.setdefault(_v, _UTAS)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
os.chdir(_REPO); sys.path.insert(0, _REPO)
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Panel bisa dialihkan lewat env JBV_PANEL supaya satu salinan kode melayani
# beberapa dataset - misalnya panel 18 leaf dan panel 15 leaf hasil
# penggabungan A.1 ke A.2.
#
# JEBAKANNYA, DAN KENAPA FOLDER HASIL IKUT BERGESER SENDIRI. Seluruh skrip
# rerun_* memakai checkpoint per sel dan melewati sel yang kuncinya sudah ada
# di berkas keluaran. Kunci itu (leaf, model, origin) TIDAK menyebut panel.
# Kalau panel diganti tapi folder hasil tidak, sel A.2.d dari panel lama
# dianggap sudah selesai - padahal datanya kini berbeda - dan hasilnya jadi
# campuran dua dataset tanpa satu pun pesan galat. Karena itu menyetel
# JBV_PANEL otomatis memindahkan folder hasil, kecuali JBV_HASIL disetel
# eksplisit.
# ---------------------------------------------------------------------------
_PANEL_ENV = os.environ.get('JBV_PANEL')
PANEL = _PANEL_ENV or 'data/processed/sdv-wide.csv'
EXT = 'data/external_features.xlsx'

_HASIL_BAWAAN = ('hasil' if not _PANEL_ENV else
                 'hasil_' + os.path.splitext(os.path.basename(PANEL))[0])
HASIL = os.path.join(_DIR, os.environ.get('JBV_HASIL', _HASIL_BAWAAN)) + os.sep

# Jumlah leaf yang seharusnya, per panel. Dipakai leaves() sebagai penegasan.
NLEAF_HARUS = {'sdv-wide.csv': 18, 'sdv-wide-gabung.csv': 15}

def _lapor_awal():
    if os.environ.get('JBV_DIAM') == '1':
        return
    print(f'[h1_common] panel {PANEL}', flush=True)
    print(f'[h1_common] hasil {HASIL}', flush=True)
    if os.environ.get('JBV_LEAF'):
        print(f'[h1_common] leaf  {os.environ["JBV_LEAF"]}', flush=True)
    elif os.environ.get('JBV_SHARD'):
        print(f'[h1_common] shard {os.environ["JBV_SHARD"]}', flush=True)


# ---------------------------------------------------------------------------
# SIDIK JARI KONFIGURASI FITUR.
#
# Nama folder hasil hanya mengikuti PANEL. Kolam fitur tidak ikut di dalamnya,
# padahal checkpoint per sel berkunci (leaf, model, origin) - juga tanpa
# menyebut kolam fitur. Akibatnya, mengubah kolam lag lalu menjalankan ulang ke
# folder yang sama membuat SELURUH sel dianggap sudah selesai: skrip berhenti
# dalam hitungan detik dan hasilnya tetap hasil lama, tanpa satu pun pesan.
# Kalau hanya sebagian sel terisi, hasilnya lebih buruk lagi - campuran dua
# kolam fitur di satu berkas.
#
# Sidik jari ini ditulis saat folder hasil pertama kali dipakai, lalu dicocokkan
# setiap kali. Kolam berubah tanpa memindahkan folder akan berhenti di sini.
# ---------------------------------------------------------------------------
def _sidik_konfigurasi():
    from utils.feature_config import FEATURE_CONFIG as FC
    return {
        'lag_target': list(FC['lag_features']['lags']),
        'lag_pasar': list(FC['cross_series_features']['lags']),
        'rata_pasar': FC['cross_series_features']['rolling_mean_window'],
        'panel': os.path.basename(PANEL),
        # Panjang blok validasi ikut di sini karena ia menentukan setelan
        # terpilih, dan setelan itu dipakai SELURUH tahap lanjutan. Menjalankan
        # NVAL yang berbeda ke folder yang sama akan mencampur dua penyetelan
        # tanpa satu pun pesan.
        'nval': int(os.environ.get('JBV_NVAL', '10')),
    }


def periksa_konfigurasi():
    import json as _json
    os.makedirs(HASIL, exist_ok=True)
    jalan = HASIL + 'konfigurasi.json'
    kini = _sidik_konfigurasi()
    if not os.path.exists(jalan):
        _json.dump(kini, open(jalan, 'w'), indent=1)
        return
    lama = _json.load(open(jalan))
    # Folder hasil yang dibuat sebelum 'nval' ada di sidik jari pasti memakai
    # NVAL=10, karena itu satu-satunya nilai yang mungkin saat itu. Isi
    # mundur nilainya alih-alih menolak folder yang sebenarnya cocok - tapi
    # HANYA kalau yang diminta sekarang juga 10. Kalau tidak, ia memang beda
    # dan harus berhenti.
    if 'nval' not in lama and kini.get('nval') == 10:
        lama['nval'] = 10
        _json.dump(lama, open(jalan, 'w'), indent=1)
    if lama == kini:
        return
    beda = [k for k in kini if lama.get(k) != kini[k]]
    print('\n' + '=' * 68, file=sys.stderr)
    print('BERHENTI: konfigurasi fitur berbeda dari isi folder hasil ini.', file=sys.stderr)
    print('=' * 68, file=sys.stderr)
    for k in beda:
        print(f'  {k}\n      folder : {lama.get(k)}\n      sekarang: {kini[k]}', file=sys.stderr)
    print(f'\n  folder: {HASIL}', file=sys.stderr)
    print('\n  Checkpoint per sel tidak menyebut kolam fitur, jadi melanjutkan di', file=sys.stderr)
    print('  sini akan mencampur dua konfigurasi dalam satu berkas.', file=sys.stderr)
    print('\n  Pakai folder lain, misalnya:', file=sys.stderr)
    print('    JBV_HASIL=hasil_<nama-yang-menjelaskan> python ...', file=sys.stderr)
    sys.exit(2)


periksa_konfigurasi()


def catat_versi():
    """Catat versi pustaka ke versi.json - DICATAT, tidak dibandingkan.

    KENAPA PERLU. Hasil VPS tidak bisa direproduksi di mesin lain: XGBoost
    berbeda di seluruh sel yang diuji, dan sebagian sel RandomForest dan
    LightGBM juga, semata karena versi pustakanya berbeda. Angka naskah karena
    itu terikat pada satu tumpukan pustaka tertentu, dan tumpukan itu harus
    ikut dilaporkan supaya orang lain tahu apa yang mereka bandingkan.

    KENAPA TIDAK MASUK SIDIK JARI KONFIGURASI. periksa_konfigurasi() berhenti
    dengan exit 2 kalau isinya berbeda dari yang tercatat di folder. Kalau
    versi pustaka ikut di sana, memperbarui satu paket akan memblokir
    kelanjutan komputasi yang sudah berjam-jam jalan - padahal yang benar
    adalah mencatatnya, lalu manusia yang memutuskan.
    """
    import json as _json
    catatan = {'python': sys.version.split()[0]}
    for nama in ('numpy', 'pandas', 'scipy', 'sklearn', 'lightgbm', 'xgboost',
                 'statsmodels', 'prophet', 'shap'):
        try:
            catatan[nama] = __import__(nama).__version__
        except Exception:
            catatan[nama] = None          # tidak terpasang, dan itu bukan galat
    os.makedirs(HASIL, exist_ok=True)
    _json.dump(catatan, open(HASIL + 'versi.json', 'w'), indent=1)
    return catatan


catat_versi()


# ---------------------------------------------------------------------------
# PEMBAGIAN KERJA PER LEAF.
#
# Leaf saling bebas: tidak ada tahap yang memakai hasil leaf lain. Jadi 15 leaf
# boleh dikerjakan beberapa proses sekaligus. Yang mahal - pembangunan fitur
# dan seleksi mRMR, 79% waktu - berjalan satu utas, jadi menambah proses
# benar-benar menambah laju.
#
# BERKAS KELUARAN HARUS TERPISAH PER SHARD. Ini bukan kehati-hatian berlebih:
# dua proses yang meng-append ke satu CSV persis yang melahirkan baris ganda
# 125,9% dan 163,3% di folder hasil panel 18 seri. append tidak atomik untuk
# tulisan sebesar satu sel, dan barisnya saling menyisip. Karena itu setiap
# shard menulis ke berkasnya sendiri, dan gabung_shard.py menyatukannya
# sesudah semua selesai.
#
# MEMBACA tetap menyatukan seluruh shard, supaya checkpoint tetap berlaku
# lintas shard - melanjutkan pekerjaan yang sudah digabung tidak mengulangnya.
#
#     JBV_SHARD=2/4   kerjakan bagian ke-2 dari 4, leaf dibagi berselang-seling
#     JBV_LEAF=A.2.a,B.b   kerjakan leaf itu saja (menang atas JBV_SHARD)
# ---------------------------------------------------------------------------
LEAF_PILIH = os.environ.get('JBV_LEAF')
_SHARD_ENV = os.environ.get('JBV_SHARD')


def _baca_shard(teks):
    if not teks:
        return None
    m = re.fullmatch(r'\s*(\d+)\s*/\s*(\d+)\s*', teks)
    if not m:
        sys.exit(f'JBV_SHARD harus berbentuk "i/n", dapat: {teks!r}')
    i, n = int(m.group(1)), int(m.group(2))
    if not 1 <= i <= n:
        sys.exit(f'JBV_SHARD={teks}: i harus antara 1 dan n')
    return i, n


SHARD = _baca_shard(_SHARD_ENV)
_lapor_awal()          # sesudah SHARD terbaca, supaya barisnya ikut tercetak


def _sisipan():
    """Penanda yang membedakan berkas proses ini dari proses paralel lain.

    JBV_LEAF ikut dapat sisipan, bukan hanya JBV_SHARD. Tanpa itu dua
    perintah JBV_LEAF yang jalan bersamaan akan meng-append ke berkas kanonik
    yang sama - persis cara baris ganda 125,9% dan 163,3% itu lahir.
    """
    if LEAF_PILIH:
        aman = re.sub(r'[^A-Za-z0-9]+', '-',
                      ','.join(sorted(x.strip() for x in LEAF_PILIH.split(',')
                                      if x.strip()))).strip('-')
        return f'.shard-leaf-{aman[:60]}'
    if SHARD is not None:
        i, n = SHARD
        return f'.shard-{i}-of-{n}'
    return ''


def jalur(nama):
    """Berkas yang DITULIS proses ini - bersisipan penanda shard kalau ada."""
    sisip = _sisipan()
    if not sisip:
        return HASIL + nama
    batang, ekor = os.path.splitext(nama)
    return HASIL + f'{batang}{sisip}{ekor}'


def semua_jalur(path):
    """Seluruh berkas yang memuat isi logis path ini: kanonik + semua shard.

    Dipakai untuk MEMBACA. Dengan begitu satu shard tahu sel yang sudah
    dikerjakan shard lain, dan pekerjaan yang sudah digabung ke berkas
    kanonik tidak dihitung ulang.
    """
    folder, nama = os.path.split(path)
    batang, ekor = os.path.splitext(nama)
    batang = re.sub(r'\.shard-(?:\d+-of-\d+|leaf-[A-Za-z0-9-]*)$', '', batang)
    kandidat = ([os.path.join(folder, batang + ekor)]
                + sorted(glob.glob(os.path.join(folder, batang + '.shard-*' + ekor))))
    return [p for p in kandidat if os.path.exists(p)]


def ada(path):
    """Apakah isi logis path ini sudah ada, di berkas kanonik atau shard mana pun."""
    return bool(semua_jalur(path))


def baca(path):
    """Baca isi logis path ini dari seluruh shard sekaligus.

    Mengembalikan DataFrame kosong kalau belum ada apa-apa, jadi pemanggil
    cukup memeriksa len().
    """
    bagian = []
    for p in semua_jalur(path):
        try:
            # float_precision='round_trip': pembaca CSV pandas tidak bolak-balik
            # persis secara bawaan - 2,0406320647409077 kembali sebagai
            # 2,040632064740908. Di sini itu membuat berkas kanonik berbeda
            # satu bit dari berkas shard sumbernya.
            d = pd.read_csv(p, float_precision='round_trip')
        except Exception as e:
            print(f'  ({os.path.basename(p)} belum terbaca: {type(e).__name__})',
                  flush=True)
            continue
        if len(d):
            bagian.append(d)
    return pd.concat(bagian, ignore_index=True) if bagian else pd.DataFrame()


def tolak_shard(nama):
    """Berhenti kalau tahap seluruh-panel dijalankan dengan JBV_SHARD.

    Tahap yang menulis SATU berkas ringkasan - bukan menambah baris per sel -
    tidak bisa dibagi: tiap shard akan menimpa ringkasan shard sebelumnya dan
    yang tersisa hanya potongan terakhir, tanpa pesan galat. Lebih baik
    berhenti di sini daripada menghasilkan ringkasan yang diam-diam tidak
    lengkap. Biasanya ini sisa env dari perintah sebelumnya.
    """
    if SHARD is None and not LEAF_PILIH:
        return
    print(f'\nBERHENTI: {nama} memproses seluruh panel dan tidak bisa dibagi '
          f'per leaf.', file=sys.stderr)
    print(f'  JBV_SHARD={_SHARD_ENV or "-"}  JBV_LEAF={LEAF_PILIH or "-"}',
          file=sys.stderr)
    print('  Lepaskan dulu:  unset JBV_SHARD JBV_LEAF', file=sys.stderr)
    sys.exit(2)


def load_panel():
    p = pd.read_csv(PANEL)
    dcols = [c for c in p.columns if c[:2] == '20']
    return p, dcols, pd.to_datetime(dcols)


def leaves(panel):
    """Leaf = simpul tanpa anak, diturunkan dari prefiks Row_ID.

    'Level terdalam' BUKAN definisi leaf - level 3 hanya memberi 9 baris karena
    cabang B dan C berhenti di level 2. D adalah total A+B+C dan dikeluarkan.

    Jumlahnya ditegaskan, bukan sekadar dihitung, supaya salah-definisi seperti
    di atas berhenti di sini alih-alih diam-diam mengecilkan panel. Angkanya
    ikut panel: 18 untuk panel penuh, 15 untuk panel gabungan. JBV_NLEAF
    menimpanya kalau ada panel ketiga.
    """
    ids = list(panel['Row_ID'])
    def punya_anak(i):
        return any(j != i and j.startswith(i + '.') for j in ids)
    lv = panel[panel['Row_ID'].apply(lambda i: not punya_anak(i))
               & (panel['Row_ID'] != 'D')]
    harus = int(os.environ.get('JBV_NLEAF', NLEAF_HARUS.get(os.path.basename(PANEL), 0)))
    assert harus, (f'panel {os.path.basename(PANEL)} belum terdaftar di '
                   f'NLEAF_HARUS; setel JBV_NLEAF kalau memang disengaja '
                   f'(dapat {len(lv)} leaf)')
    assert len(lv) == harus, f'harus {harus} leaf, dapat {len(lv)}'
    # Penyaringan shard SESUDAH penegasan di atas, supaya penjaga jumlah leaf
    # tetap memeriksa panel utuh - bukan potongan yang kebetulan dikerjakan
    # proses ini.
    return _saring_leaf(lv)


def _saring_leaf(lv):
    if LEAF_PILIH:
        minta = [x.strip() for x in LEAF_PILIH.split(',') if x.strip()]
        punya = set(lv['Row_ID'])
        hilang = [x for x in minta if x not in punya]
        assert not hilang, f'JBV_LEAF menyebut leaf yang tidak ada: {hilang}'
        return lv[lv['Row_ID'].isin(minta)]
    if SHARD is None:
        return lv
    i, n = SHARD
    # Berselang-seling, bukan blok berurutan: leaf bertetangga cenderung
    # sebesar dan selambat satu sama lain, jadi membaginya berselang membuat
    # beban tiap shard lebih rata.
    return lv.iloc[[k for k in range(len(lv)) if k % n == i - 1]]


def series_of(row, dcols, dates_all):
    y = pd.to_numeric(row[dcols].values, errors='coerce')
    ok = ~pd.isna(y)
    return dates_all[ok], y[ok].astype(float)


def load_external():
    e = pd.read_excel(EXT)
    e['Tanggal'] = pd.to_datetime(e['Tanggal'])
    cols = [c for c in e.columns if c != 'Tanggal']
    d = {c: e[c].ffill().bfill().values for c in cols}
    return d, e['Tanggal'].values


def scale_denom(train):
    """Penyebut MASE: rata-rata |selisih pertama| pada periode training."""
    d = np.mean(np.abs(np.diff(np.asarray(train, float))))
    return d if np.isfinite(d) and d > 0 else np.nan


def one_step_metrics(actual, pred, denom):
    a = float(actual); p = float(pred)
    err = a - p
    return {
        'actual': a, 'pred': p, 'err': err,
        'ae': abs(err),
        'mase': abs(err) / denom if np.isfinite(denom) else np.nan,
        'smape': 200.0 * abs(err) / (abs(a) + abs(p)) if (abs(a) + abs(p)) > 0 else 0.0,
    }
