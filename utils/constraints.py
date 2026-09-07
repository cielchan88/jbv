"""
Batasan tanda per seri.

Sembilan dari 18 leaf tidak pernah sekali pun berganti tanda sepanjang 20,6
tahun: Impor dan Repatriasi selalu satu arah, Ekspor dan Investasi selalu arah
sebaliknya. Itu konvensi pembukuan aliran devisa, bukan dinamika yang perlu
diramal.

Model tidak diberi tahu hal itu. LightGBM bisa saja mengeluarkan angka positif
untuk seri yang secara struktural selalu negatif - nilai yang tidak mungkin
terjadi. Menjepitnya ke sisi yang benar tidak membuang informasi apa pun, hanya
membuang prediksi mustahil.

PENTING: polaritas HARUS disimpulkan dari data yang tersedia pada saat forecast
dibuat, bukan dari keseluruhan seri. Menyimpulkannya dari seluruh histori -
termasuk periode uji - adalah kebocoran informasi masa depan, dan akan membuat
evaluasi tampak lebih baik daripada yang sebenarnya bisa dicapai.
"""

import numpy as np

# Ambang untuk menyatakan sebuah seri "terkunci" tandanya. Sengaja ketat:
# menjepit seri yang sesekali berganti tanda akan menghapus pergerakan yang
# nyata, dan biayanya jauh lebih besar daripada manfaat menjepit.
SIGN_LOCK_THRESHOLD = 0.995

# Minimal jumlah observasi bukan-nol sebelum polaritas boleh disimpulkan.
# Tanpa ini, seri yang kebetulan baru punya sedikit transaksi searah akan
# dikunci berdasarkan bukti yang terlalu tipis.
MIN_NONZERO = 100


def infer_sign_polarity(values, threshold=SIGN_LOCK_THRESHOLD, min_nonzero=MIN_NONZERO):
    """
    Simpulkan polaritas seri dari histori.

    Returns:
        +1 : tidak pernah negatif  -> forecast dijepit ke >= 0
        -1 : tidak pernah positif  -> forecast dijepit ke <= 0
         0 : dua arah              -> tanpa batasan
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    nz = v[v != 0]

    if len(nz) < min_nonzero:
        return 0

    frac_pos = float(np.mean(nz > 0))
    if frac_pos >= threshold:
        return 1
    if frac_pos <= (1.0 - threshold):
        return -1
    return 0


def apply_sign_constraint(forecast, polarity):
    """
    Jepit forecast ke sisi yang diizinkan polaritas.

    Nol tetap diperbolehkan di kedua arah - seri yang tidak pernah negatif
    tetap boleh bernilai nol (hari tanpa transaksi), dan itu memang terjadi
    pada sebagian besar seri terkunci.
    """
    f = np.asarray(forecast, dtype=float)
    if polarity > 0:
        return np.maximum(f, 0.0)
    if polarity < 0:
        return np.minimum(f, 0.0)
    return f


def constrain_interval(lower, upper, polarity):
    """
    Terapkan batasan yang sama pada batas interval.

    Separuh pita yang menyeberang nol pada seri terkunci adalah pemborosan
    lebar: ia mengklaim kemungkinan yang tidak pernah terjadi dalam 20 tahun.
    """
    lo = np.asarray(lower, dtype=float)
    hi = np.asarray(upper, dtype=float)
    if polarity > 0:
        lo = np.maximum(lo, 0.0)
        hi = np.maximum(hi, 0.0)
    elif polarity < 0:
        lo = np.minimum(lo, 0.0)
        hi = np.minimum(hi, 0.0)
    return lo, hi


def describe_polarity(polarity):
    """Label singkat untuk ditampilkan di UI."""
    return {1: "selalu >= 0", -1: "selalu <= 0", 0: "dua arah"}.get(int(polarity), "dua arah")
