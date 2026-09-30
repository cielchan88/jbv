"""Inferensi tambahan untuk naskah utama, dari berkas hasil yang sudah ada.

Menjawab review kedua (A1): unit uji dihitung berulang dan 30 origin
berurutan saling bergantung. Tidak ada model yang dilatih ulang di sini.

    - UNIT DIRATA-RATA per (seri, tanggal). Tiga learner, atau empat kondisi
      data pasar, yang meramal hari yang sama bukan replikasi independen.
      Semua perbandingan di sini memakai 15 x 30 = 450 unit.
    - CI BOOTSTRAP BLOK per tanggal. Tanggal diambil ulang dalam blok lima
      hari kerja (satu minggu), dan ke-15 seri pada tanggal yang sama ikut
      bersama, jadi ketergantungan antar-seri dan antar-hari sama-sama
      dipertahankan. Dengan hanya 30 tanggal, CI-nya lebar, dan itu jujur.
    - EKUIVALENSI (TOST) dengan margin +-2 persen pada perubahan mean MASE:
      setara bila CI 90 persen seluruhnya di dalam margin.
    - HODGES-LEHMANN: penaksir lokasi selisih berpasangan yang sesuai dengan
      Wilcoxon (yang menguji pseudo-median, bukan mean).
    - DIEBOLD-MARIANO dengan koreksi Harvey-Leybourne-Newbold, per seri.
    - MODEL CONFIDENCE SET (Hansen, Lunde dan Nason, 2011), statistik T_max,
      pada rata-rata harian MASE ke-10 metode.
    - SKALA MASE yang dikoreksi untuk seri yang baru dilaporkan sejak 2013.
"""
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon, t as tdist

RNG = np.random.default_rng(20260930)
B = 2000
BLOK = 5
MARGIN = 2.0


def _indeks_blok(n, b=B, blok=BLOK, rng=RNG):
    """Bootstrap blok melingkar: b x n indeks tanggal."""
    nb = int(np.ceil(n / blok))
    awal = rng.integers(0, n, size=(b, nb))
    idx = (awal[:, :, None] + np.arange(blok)[None, None, :]) % n
    return idx.reshape(b, -1)[:, :n]


def ke_unit(s):
    """Rata-ratakan per (leaf, origin)."""
    return s.groupby(level=['leaf', 'origin']).mean()


def hodges_lehmann(d):
    d = np.asarray(d, float)
    i, j = np.triu_indices(len(d))
    return float(np.median((d[i] + d[j]) / 2))


def banding(a, b, label):
    """a = pembanding (acuan), b = lengan yang diuji. Seri pandas ber-indeks
    (leaf, origin, ...). Perubahan positif = b lebih buruk dari a."""
    a, b = ke_unit(a), ke_unit(b)
    j = pd.concat([a, b], axis=1, keys=['a', 'b']).dropna()
    tgl = j.index.get_level_values('origin')
    uniq = np.sort(tgl.unique())
    sa = j.a.groupby(tgl).sum().reindex(uniq).values
    sb = j.b.groupby(tgl).sum().reindex(uniq).values
    delta = 100 * (sb.sum() / sa.sum() - 1)
    idx = _indeks_blok(len(uniq))
    boot = 100 * (sb[idx].sum(1) / sa[idx].sum(1) - 1)
    lo95, hi95 = np.percentile(boot, [2.5, 97.5])
    lo90, hi90 = np.percentile(boot, [5, 95])
    d = (j.b - j.a).values
    # CI Hodges-Lehmann lewat bootstrap blok yang sama (500 ulangan cukup
    # untuk persentil 2,5 dan 97,5 pada ukuran ini).
    per_tgl = [d[tgl == u] for u in uniq]
    hl_boot = [hodges_lehmann(np.concatenate([per_tgl[k] for k in row])) for row in idx[:500]]
    p = float(wilcoxon(j.b, j.a).pvalue) if np.any(d != 0) else float('nan')
    return dict(label=label, n=int(len(j)), delta=float(delta), lo95=float(lo95), hi95=float(hi95),
                lo90=float(lo90), hi90=float(hi90),
                setara=bool(lo90 > -MARGIN and hi90 < MARGIN),
                beda=bool(lo95 > 0 or hi95 < 0),
                hl=hodges_lehmann(d), hl_lo=float(np.percentile(hl_boot, 2.5)),
                hl_hi=float(np.percentile(hl_boot, 97.5)), p=p)


def dm_hln(e1, e2):
    """Diebold-Mariano satu langkah dengan koreksi HLN. Kerugian = |galat|.
    Positif = model 2 lebih buruk."""
    d = np.abs(e2) - np.abs(e1)
    n = len(d)
    if n < 3 or np.allclose(d, 0):
        return 0.0, 1.0
    s = np.var(d, ddof=0)
    dm = d.mean() / np.sqrt(s / n)
    dm *= np.sqrt((n + 1 - 2 + 0) / n)          # h = 1
    p = 2 * tdist.sf(abs(dm), n - 1)
    return float(dm), float(p)


def mcs(L, alpha=0.10):
    """Model Confidence Set, statistik T_max (Hansen, Lunde dan Nason 2011).
    L: DataFrame tanggal x model, kerugian rata-rata harian. Mengembalikan
    (himpunan tersisa, p-value MCS per model)."""
    M = list(L.columns)
    X = L.values
    n = X.shape[0]
    idx = _indeks_blok(n)
    pval, jalan = {}, 0.0
    while len(M) > 1:
        cols = [L.columns.get_loc(m) for m in M]
        Y = X[:, cols]
        d = Y - Y.mean(1, keepdims=True)                 # d_i. per tanggal
        dbar = d.mean(0)
        db = np.stack([d[r].mean(0) for r in idx])       # B x m
        sd = db.std(0, ddof=1)
        t_i = dbar / sd
        Tmax = t_i.max()
        Tb = ((db - dbar) / sd).max(1)
        p = float((Tb >= Tmax).mean())
        jalan = max(jalan, p)
        buang = M[int(np.argmax(t_i))]
        pval[buang] = jalan
        if jalan >= alpha:
            break
        M.remove(buang)
    for m in M:
        pval.setdefault(m, 1.0)
    tersisa = [m for m in L.columns if pval[m] >= alpha]
    return tersisa, pval
