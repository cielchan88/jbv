"""Perkakas bersama untuk seluruh eksperimen satu-langkah naskah.

Semua eksperimen memakai definisi leaf, pemuat data, dan metrik yang sama dari
sini supaya angkanya konsisten antar tabel.
"""
import os, sys, warnings
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

if os.environ.get('JBV_DIAM') != '1':
    print(f'[h1_common] panel {PANEL}', flush=True)
    print(f'[h1_common] hasil {HASIL}', flush=True)


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
    return lv


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
