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

PANEL = 'data/processed/sdv-wide.csv'
EXT = 'data/external_features.xlsx'


def load_panel():
    p = pd.read_csv(PANEL)
    dcols = [c for c in p.columns if c[:2] == '20']
    return p, dcols, pd.to_datetime(dcols)


def leaves(panel):
    """Leaf = simpul tanpa anak, diturunkan dari prefiks Row_ID.

    'Level terdalam' BUKAN definisi leaf - level 3 hanya memberi 9 baris karena
    cabang B dan C berhenti di level 2. D adalah total A+B+C dan dikeluarkan.
    """
    ids = list(panel['Row_ID'])
    def punya_anak(i):
        return any(j != i and j.startswith(i + '.') for j in ids)
    lv = panel[panel['Row_ID'].apply(lambda i: not punya_anak(i))
               & (panel['Row_ID'] != 'D')]
    assert len(lv) == 18, f'harus 18 leaf, dapat {len(lv)}'
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
