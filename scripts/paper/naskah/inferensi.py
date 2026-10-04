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
      setara bila CI 90 persen seluruhnya di dalam margin. Margin dipilih
      SESUDAH hasil terlihat (review ketiga), jadi dilaporkan juga +-1 dan
      +-3 persen, dan CI dengan blok 2 dan 10 hari.
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
MARGIN_SENS = (1.0, 2.0, 3.0)
BLOK_SENS = (2, 10)
RNG_SENS = np.random.default_rng(20261001)


def _indeks_blok(n, b=B, blok=BLOK, rng=RNG):
    """Bootstrap blok melingkar: b x n indeks tanggal."""
    nb = int(np.ceil(n / blok))
    awal = rng.integers(0, n, size=(b, nb))
    idx = (awal[:, :, None] + np.arange(blok)[None, None, :]) % n
    return idx.reshape(b, -1)[:, :n]


def ke_unit(s):
    """Rata-ratakan per (leaf, origin)."""
    return s.groupby(level=['leaf', 'origin']).mean()


def hodges_lehmann(d, maks=300_000):
    """Median rata-rata Walsh. Persis untuk n kecil (450 unit naskah); di atas
    `maks` pasangan dipakai sampel acak pasangan berseed tetap - 3.750 unit
    (jalan v2) berarti 7 juta pasangan per hitungan, dikali 500 ulangan."""
    d = np.asarray(d, float)
    n = len(d)
    if n * (n + 1) // 2 <= maks:
        i, j = np.triu_indices(n)
    else:
        g = np.random.default_rng(n)
        i, j = g.integers(0, n, maks), g.integers(0, n, maks)
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
    seri = np.isclose(j.a.values, j.b.values, rtol=0, atol=1e-12)
    # Sensitivitas: RNG TERPISAH, supaya CI utama tidak bergeser.
    sens = {}
    for bl in BLOK_SENS:
        ix = _indeks_blok(len(uniq), blok=bl, rng=RNG_SENS)
        bt = 100 * (sb[ix].sum(1) / sa[ix].sum(1) - 1)
        sens[bl] = [float(x) for x in np.percentile(bt, [2.5, 97.5, 5, 95])]
    return dict(label=label, n=int(len(j)), delta=float(delta), lo95=float(lo95), hi95=float(hi95),
                lo90=float(lo90), hi90=float(hi90),
                setara=bool(lo90 > -MARGIN and hi90 < MARGIN),
                beda=bool(lo95 > 0 or hi95 < 0),
                setara_margin={str(m): bool(lo90 > -m and hi90 < m) for m in MARGIN_SENS},
                blok_sens={str(k): v for k, v in sens.items()},
                a_lebih_baik=int((j.a.values < j.b.values)[~seri].sum()),
                b_lebih_baik=int((j.b.values < j.a.values)[~seri].sum()), seri=int(seri.sum()),
                hl=hodges_lehmann(d), hl_lo=float(np.percentile(hl_boot, 2.5)),
                hl_hi=float(np.percentile(hl_boot, 97.5)), p=p)


def holm(daftar):
    """Tambahkan p_holm ke setiap dict dalam satu keluarga uji."""
    urut, jalan = sorted(range(len(daftar)), key=lambda i: daftar[i]['p']), 0.0
    for r, i in enumerate(urut):
        jalan = max(jalan, min(1.0, (len(daftar) - r) * daftar[i]['p']))
        daftar[i]['p_holm'] = jalan
    return daftar


def pesaran_timmermann(aktual, ramal):
    """Uji arah Pesaran-Timmermann (1992). Masukan: tanda perubahan (+1/-1)."""
    from scipy.stats import norm
    y, x = np.asarray(aktual) > 0, np.asarray(ramal) > 0
    n = len(y)
    P, py, px = np.mean(y == x), y.mean(), x.mean()
    ps = py * px + (1 - py) * (1 - px)
    vp = ps * (1 - ps) / n
    vps = ((2 * py - 1) ** 2 * px * (1 - px) / n + (2 * px - 1) ** 2 * py * (1 - py) / n
           + 4 * py * px * (1 - py) * (1 - px) / n ** 2)
    if vp - vps <= 0:
        return float('nan'), float('nan')
    st = (P - ps) / np.sqrt(vp - vps)
    return float(st), float(norm.sf(st))


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
