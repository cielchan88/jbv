"""
Statistical Analytics untuk Eksplorasi Data
============================================

Fungsi-fungsi analisis statistik untuk halaman Eksplorasi:
- Deteksi outlier (IQR, Z-score, Modified Z-score/MAD)
- Deteksi structural break (binary segmentation + CUSUM)
- Uji stasioneritas (ADF, KPSS)
- ACF/PACF
- Statistik distribusi (skewness, kurtosis, Jarque-Bera)
- Analisis kualitas data (deret nilai nol, gap tanggal)

Semua fungsi di sini murni numerik (tanpa Streamlit) supaya bisa diuji
terpisah dan dipakai ulang di halaman lain.
"""

import numpy as np
import pandas as pd


# ============================================================================
# OUTLIER DETECTION
# ============================================================================

def detect_outliers_iqr(values, k=1.5):
    """
    Deteksi outlier dengan metode IQR (Tukey's fences).

    Returns:
        dict: mask (bool array), lower, upper, count
    """
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return {'mask': np.zeros(len(values), dtype=bool), 'lower': np.nan, 'upper': np.nan, 'count': 0}

    q1, q3 = np.percentile(finite, [25, 75])
    iqr = q3 - q1
    lower, upper = q1 - k * iqr, q3 + k * iqr
    mask = (values < lower) | (values > upper)
    return {'mask': mask, 'lower': float(lower), 'upper': float(upper), 'count': int(mask.sum())}


def detect_outliers_zscore(values, threshold=3.0):
    """
    Deteksi outlier dengan Z-score standar (mean/std).

    Catatan: kurang robust karena mean & std sendiri ikut terpengaruh outlier.
    Dipakai sebagai pembanding metode MAD.
    """
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if len(finite) == 0 or np.std(finite) == 0:
        return {'mask': np.zeros(len(values), dtype=bool), 'scores': np.zeros(len(values)), 'count': 0}

    mean, std = np.mean(finite), np.std(finite)
    scores = (values - mean) / std
    mask = np.abs(scores) > threshold
    return {'mask': mask, 'scores': scores, 'count': int(mask.sum())}


def detect_outliers_mad(values, threshold=3.5):
    """
    Deteksi outlier dengan Modified Z-score berbasis MAD (Median Absolute Deviation).

    Lebih robust dari Z-score biasa untuk data volatil karena median dan MAD
    tidak "tertarik" oleh nilai ekstrem. Konstanta 0.6745 membuat MAD sebanding
    dengan standar deviasi pada distribusi normal.
    """
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return {'mask': np.zeros(len(values), dtype=bool), 'scores': np.zeros(len(values)), 'count': 0}

    median = np.median(finite)
    mad = np.median(np.abs(finite - median))

    if mad == 0:
        # MAD nol (>50% data identik, mis. banyak nilai 0) - fallback ke mean abs deviation
        mad_alt = np.mean(np.abs(finite - median))
        if mad_alt == 0:
            return {'mask': np.zeros(len(values), dtype=bool), 'scores': np.zeros(len(values)), 'count': 0}
        scores = (values - median) / (1.253314 * mad_alt)
    else:
        scores = 0.6745 * (values - median) / mad

    mask = np.abs(scores) > threshold
    return {'mask': mask, 'scores': scores, 'count': int(mask.sum())}


def summarize_outliers(dates, values, method='mad', **kwargs):
    """
    Ringkasan outlier jadi DataFrame yang siap ditampilkan.

    Returns:
        (DataFrame outlier terurut dari deviasi terbesar, dict info metode)
    """
    detectors = {
        'iqr': detect_outliers_iqr,
        'zscore': detect_outliers_zscore,
        'mad': detect_outliers_mad,
    }
    if method not in detectors:
        raise ValueError(f"Metode tidak dikenal: {method}. Pilih: {list(detectors)}")

    result = detectors[method](values, **kwargs)
    mask = result['mask']
    values = np.asarray(values, dtype=float)
    dates = pd.to_datetime(pd.Series(dates))

    if not mask.any():
        return pd.DataFrame(columns=['Tanggal', 'Nilai', 'Skor', 'Arah']), result

    scores = result.get('scores')
    if scores is None:
        # IQR tidak punya skor - pakai jarak relatif ke batas terdekat
        lower, upper = result['lower'], result['upper']
        scores = np.where(values > upper, values - upper, np.where(values < lower, values - lower, 0.0))

    out_df = pd.DataFrame({
        'Tanggal': dates[mask].dt.strftime('%Y-%m-%d').values,
        'Nilai': values[mask],
        'Skor': np.asarray(scores)[mask],
        'Arah': np.where(np.asarray(scores)[mask] > 0, 'Tinggi', 'Rendah'),
    })
    out_df = out_df.reindex(out_df['Skor'].abs().sort_values(ascending=False).index).reset_index(drop=True)
    return out_df, result


# ============================================================================
# STRUCTURAL BREAK DETECTION
# ============================================================================

def _segment_cost(prefix_sum, prefix_sq, s, e):
    """Sum of squared deviations dari mean untuk segmen [s, e), via prefix sums."""
    n = e - s
    if n <= 0:
        return 0.0
    seg_sum = prefix_sum[e] - prefix_sum[s]
    seg_sq = prefix_sq[e] - prefix_sq[s]
    return float(seg_sq - (seg_sum ** 2) / n)


def _best_split(values, prefix_sum, prefix_sq, s, e, min_size):
    """
    Cari titik split terbaik dalam segmen [s, e) - vectorized supaya tetap cepat
    untuk deret panjang (ribuan titik).

    Returns: (index split absolut, gain) atau (None, 0.0) kalau segmen terlalu pendek.
    """
    m = e - s
    if m < 2 * min_size:
        return None, 0.0

    idx = np.arange(s + min_size, e - min_size + 1)
    if len(idx) == 0:
        return None, 0.0

    left_n = idx - s
    right_n = e - idx
    left_sum = prefix_sum[idx] - prefix_sum[s]
    left_sq = prefix_sq[idx] - prefix_sq[s]
    right_sum = (prefix_sum[e] - prefix_sum[s]) - left_sum
    right_sq = (prefix_sq[e] - prefix_sq[s]) - left_sq

    cost_left = left_sq - (left_sum ** 2) / left_n
    cost_right = right_sq - (right_sum ** 2) / right_n
    base_cost = _segment_cost(prefix_sum, prefix_sq, s, e)
    gains = base_cost - (cost_left + cost_right)

    j = int(np.argmax(gains))
    return int(idx[j]), float(gains[j])


def detect_structural_breaks(values, max_breaks=5, min_size=60, min_gain_ratio=0.01):
    """
    Deteksi structural break (pergeseran level/mean) dengan binary segmentation.

    Algoritma: cari titik potong yang paling mengurangi total sum-of-squared-error
    terhadap mean segmen, lalu ulangi secara rekursif pada segmen hasil potongan.
    Berhenti kalau perbaikan (gain) sudah di bawah min_gain_ratio dari total
    variasi awal - supaya tidak memotong deret hanya karena noise.

    Parameters:
        max_breaks: maksimum jumlah break yang dicari
        min_size: minimum panjang tiap segmen (hari), mencegah break di ujung
        min_gain_ratio: ambang minimal perbaikan relatif untuk menerima break

    Returns:
        dict: breakpoints (list index), segments (list dict info per segmen)
    """
    values = np.asarray(values, dtype=float)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    n = len(values)

    if n < 2 * min_size:
        return {'breakpoints': [], 'segments': [], 'note': 'Data terlalu pendek untuk deteksi break'}

    prefix_sum = np.concatenate([[0.0], np.cumsum(values)])
    prefix_sq = np.concatenate([[0.0], np.cumsum(values ** 2)])

    total_cost = _segment_cost(prefix_sum, prefix_sq, 0, n)
    if total_cost <= 0:
        return {'breakpoints': [], 'segments': [], 'note': 'Data konstan - tidak ada break'}

    breakpoints = []
    for _ in range(max_breaks):
        bounds = [0] + sorted(breakpoints) + [n]
        best_gain, best_idx = 0.0, None
        for s, e in zip(bounds[:-1], bounds[1:]):
            idx, gain = _best_split(values, prefix_sum, prefix_sq, s, e, min_size)
            if idx is not None and gain > best_gain:
                best_gain, best_idx = gain, idx

        if best_idx is None or best_gain < min_gain_ratio * total_cost:
            break
        breakpoints.append(best_idx)

    breakpoints = sorted(breakpoints)

    segments = []
    bounds = [0] + breakpoints + [n]
    for s, e in zip(bounds[:-1], bounds[1:]):
        seg = values[s:e]
        segments.append({
            'start_idx': s,
            'end_idx': e - 1,
            'n': int(e - s),
            'mean': float(np.mean(seg)),
            'std': float(np.std(seg)),
        })

    return {'breakpoints': breakpoints, 'segments': segments, 'note': None}


def cusum(values):
    """
    CUSUM (cumulative sum) dari deviasi terhadap mean keseluruhan.

    Dipakai untuk melihat SECARA VISUAL kapan deret mulai menyimpang konsisten
    dari rata-rata jangka panjangnya: tren naik pada kurva CUSUM = periode di
    atas rata-rata, tren turun = di bawah rata-rata. Titik balik pada kurva
    sering menandakan pergeseran rezim.
    """
    values = np.asarray(values, dtype=float)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    if len(values) == 0:
        return np.array([])
    return np.cumsum(values - np.mean(values))


# ============================================================================
# STATIONARITY & AUTOCORRELATION
# ============================================================================

def stationarity_tests(values):
    """
    Uji stasioneritas ADF dan KPSS.

    ADF  H0: ada unit root (TIDAK stasioner) -> p < 0.05 berarti stasioner
    KPSS H0: stasioner                       -> p < 0.05 berarti TIDAK stasioner

    Keduanya dipakai bersamaan karena saling melengkapi: kesimpulan paling
    kuat kalau keduanya sepakat.
    """
    from statsmodels.tsa.stattools import adfuller, kpss
    import warnings

    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    result = {}

    if len(values) < 20:
        return {'error': 'Data terlalu pendek untuk uji stasioneritas (min 20 observasi)'}

    try:
        # statsmodels akan mengganti return adfuller dari tuple ke ADFullerResult
        # (rilis 0.16+). Ditangani dua-duanya supaya tidak rusak saat upgrade.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            adf_out = adfuller(values, autolag='AIC')

        if hasattr(adf_out, 'stat'):  # ADFullerResult (statsmodels baru)
            adf_stat, adf_p, adf_crit = adf_out.stat, adf_out.pvalue, adf_out.critical_values
        else:  # tuple (statsmodels lama)
            adf_stat, adf_p, adf_crit = adf_out[0], adf_out[1], adf_out[4]

        result['adf'] = {
            'statistic': float(adf_stat),
            'pvalue': float(adf_p),
            'critical': {k: float(v) for k, v in dict(adf_crit).items()},
            'stationary': bool(adf_p < 0.05),
        }
    except Exception as e:
        result['adf'] = {'error': str(e)}

    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            kpss_stat, kpss_p, _, kpss_crit = kpss(values, regression='c', nlags='auto')
        result['kpss'] = {
            'statistic': float(kpss_stat),
            'pvalue': float(kpss_p),
            'critical': {k: float(v) for k, v in kpss_crit.items()},
            'stationary': bool(kpss_p >= 0.05),
        }
    except Exception as e:
        result['kpss'] = {'error': str(e)}

    adf_ok = result.get('adf', {}).get('stationary')
    kpss_ok = result.get('kpss', {}).get('stationary')
    if adf_ok is None or kpss_ok is None:
        result['conclusion'] = 'Tidak dapat disimpulkan (salah satu uji gagal)'
    elif adf_ok and kpss_ok:
        result['conclusion'] = 'STASIONER - kedua uji sepakat'
    elif not adf_ok and not kpss_ok:
        result['conclusion'] = 'TIDAK STASIONER - kedua uji sepakat (perlu differencing)'
    elif adf_ok and not kpss_ok:
        result['conclusion'] = 'Ambigu - kemungkinan trend-stationary (pertimbangkan detrending)'
    else:
        result['conclusion'] = 'Ambigu - kemungkinan difference-stationary (pertimbangkan differencing)'

    return result


def compute_acf_pacf(values, nlags=40):
    """
    Hitung ACF & PACF beserta confidence interval 95%.

    Berguna untuk membaca struktur autokorelasi: lag mana yang masih signifikan,
    dan apakah ada pola musiman (mis. lonjakan di lag 5 untuk data hari kerja).
    """
    from statsmodels.tsa.stattools import acf, pacf

    values = np.asarray(values, dtype=float)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    n = len(values)

    if n < 10:
        return {'error': 'Data terlalu pendek untuk ACF/PACF'}

    nlags = int(min(nlags, max(1, n // 2 - 1)))

    try:
        acf_vals = acf(values, nlags=nlags, fft=True)
        pacf_vals = pacf(values, nlags=nlags)
    except Exception as e:
        return {'error': str(e)}

    conf = 1.96 / np.sqrt(n)
    return {
        'lags': np.arange(len(acf_vals)),
        'acf': acf_vals,
        'pacf': pacf_vals,
        'conf': float(conf),
        'nlags': nlags,
    }


# ============================================================================
# DISTRIBUTION
# ============================================================================

def distribution_stats(values):
    """
    Statistik bentuk distribusi: skewness, kurtosis, dan uji normalitas Jarque-Bera.

    Relevan untuk forecasting karena banyak model (mis. ARIMA/VAR dengan CI
    berbasis normal) mengasumsikan residual mendekati normal - kalau data sangat
    skewed/heavy-tailed, interval kepercayaan bisa menyesatkan.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]

    if len(values) < 8:
        return {'error': 'Data terlalu pendek untuk statistik distribusi'}

    n = len(values)
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1))

    if std == 0:
        return {'error': 'Data konstan - tidak ada variasi'}

    z = (values - mean) / std
    skewness = float(np.mean(z ** 3))
    kurtosis_excess = float(np.mean(z ** 4) - 3.0)

    # Jarque-Bera statistic
    jb_stat = n / 6.0 * (skewness ** 2 + (kurtosis_excess ** 2) / 4.0)
    try:
        from scipy.stats import chi2
        jb_p = float(1 - chi2.cdf(jb_stat, df=2))
    except Exception:
        jb_p = None

    return {
        'n': n,
        'mean': mean,
        'std': std,
        'skewness': skewness,
        'kurtosis_excess': kurtosis_excess,
        'jb_statistic': float(jb_stat),
        'jb_pvalue': jb_p,
        'normal': (jb_p is not None and jb_p >= 0.05),
    }


def normality_diagnostics(values, shapiro_max_n=5000, random_state=42):
    """
    Bahan untuk grafik normalitas (Q-Q plot dan ECDF) plus uji normalitas
    pelengkap di luar Jarque-Bera.

    Kenapa Q-Q plot, bukan cukup histogram: histogram menunjukkan bentuk secara
    kasar, tapi mata sulit menilai EKOR distribusi dari histogram - padahal
    justru ekor yang menentukan apakah confidence interval berbasis normal
    (ARIMA/VAR) bisa dipercaya. Q-Q plot memetakan kuantil data terhadap kuantil
    normal teoretis, sehingga penyimpangan di ekor terlihat sebagai lengkungan
    di ujung garis - jelas dan bisa dibaca langsung.

    Kenapa beberapa uji sekaligus: masing-masing peka pada hal berbeda.
    Jarque-Bera menghukum skewness/kurtosis, Anderson-Darling paling sensitif di
    ekor, D'Agostino K2 menggabungkan skew dan kurtosis. Shapiro-Wilk paling
    kuat untuk sampel kecil tapi p-value-nya tidak andal di n besar, jadi
    dijalankan pada subsampel acak dan ditandai sebagai subsampel.

    Returns dict berisi:
        theoretical_q, sample_q : koordinat Q-Q plot
        line_slope, line_int    : garis acuan (data normal jatuh di garis ini)
        r_squared               : kecocokan titik terhadap garis
        ecdf_x, ecdf_emp, ecdf_theo : ECDF empiris vs CDF normal
        tests                   : list dict {'nama','statistik','p','normal','catatan'}
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]

    if len(values) < 8:
        return {'error': 'Data terlalu pendek untuk diagnostik normalitas'}

    n = len(values)
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1))
    if std == 0:
        return {'error': 'Data konstan - tidak ada variasi'}

    sample_q = np.sort(values)

    # Posisi plotting Blom - konvensi yang sama dipakai scipy.stats.probplot,
    # menghindari p = 0 atau 1 yang membuat ppf menjadi tak hingga.
    i = np.arange(1, n + 1)
    p = (i - 0.375) / (n + 0.25)

    try:
        from scipy.stats import norm
        theoretical_q = norm.ppf(p)
        ecdf_theo = norm.cdf((sample_q - mean) / std)
    except Exception:
        return {'error': 'scipy tidak tersedia - diagnostik normalitas butuh scipy'}

    # Garis acuan lewat kuartil (robust): tidak ikut tertarik oleh outlier
    # ekstrem seperti garis kuadrat terkecil, jadi penyimpangan ekor tetap
    # terlihat sebagai penyimpangan, bukan tersamarkan oleh garis yang miring
    # mengikuti outlier itu sendiri.
    q25_s, q75_s = np.percentile(sample_q, [25, 75])
    q25_t, q75_t = norm.ppf(0.25), norm.ppf(0.75)
    slope = (q75_s - q25_s) / (q75_t - q25_t)
    intercept = q25_s - slope * q25_t

    fitted = slope * theoretical_q + intercept
    ss_res = float(np.sum((sample_q - fitted) ** 2))
    ss_tot = float(np.sum((sample_q - np.mean(sample_q)) ** 2))
    r_squared = float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan

    ecdf_emp = i / n

    # ---- Uji normalitas pelengkap ----
    tests = []

    try:
        from scipy.stats import jarque_bera
        jb = jarque_bera(values)
        tests.append({'nama': 'Jarque-Bera', 'statistik': float(jb[0]),
                      'p': float(jb[1]), 'normal': float(jb[1]) >= 0.05,
                      'catatan': 'Peka pada skewness & kurtosis'})
    except Exception:
        pass

    try:
        from scipy.stats import normaltest
        dag = normaltest(values)
        tests.append({'nama': "D'Agostino K²", 'statistik': float(dag[0]),
                      'p': float(dag[1]), 'normal': float(dag[1]) >= 0.05,
                      'catatan': 'Gabungan uji skewness dan kurtosis'})
    except Exception:
        pass

    try:
        from scipy.stats import anderson
        ad = anderson(values, dist='norm')
        # Anderson-Darling tidak memberi p-value, tapi nilai kritis per taraf.
        # Dibandingkan pada taraf 5% (indeks 2 pada daftar bawaan scipy).
        crit_5 = float(ad.critical_values[2])
        tests.append({'nama': 'Anderson-Darling', 'statistik': float(ad.statistic),
                      'p': None, 'normal': float(ad.statistic) < crit_5,
                      'catatan': f'Paling peka di ekor. Nilai kritis 5% = {crit_5:.3f}'})
    except Exception:
        pass

    try:
        from scipy.stats import shapiro
        if n > shapiro_max_n:
            rng = np.random.default_rng(random_state)
            sub = rng.choice(values, size=shapiro_max_n, replace=False)
            note = f'Subsampel acak {shapiro_max_n} dari {n} (p-value tidak andal di n besar)'
        else:
            sub = values
            note = 'Paling kuat untuk sampel kecil'
        sw = shapiro(sub)
        tests.append({'nama': 'Shapiro-Wilk', 'statistik': float(sw[0]),
                      'p': float(sw[1]), 'normal': float(sw[1]) >= 0.05,
                      'catatan': note})
    except Exception:
        pass

    return {
        'n': n,
        'mean': mean,
        'std': std,
        'theoretical_q': theoretical_q,
        'sample_q': sample_q,
        'line_slope': float(slope),
        'line_intercept': float(intercept),
        'r_squared': r_squared,
        'ecdf_x': sample_q,
        'ecdf_emp': ecdf_emp,
        'ecdf_theo': ecdf_theo,
        'ks_distance': float(np.max(np.abs(ecdf_emp - ecdf_theo))),
        'tests': tests,
    }


# ============================================================================
# DATA QUALITY
# ============================================================================

def analyze_zero_runs(dates, values, min_run=2):
    """
    Cari deret nilai nol berturut-turut.

    Penting karena ETL mengubah nilai kosong menjadi 0 (lihat etl/pipeline.py),
    sehingga "0" bisa berarti dua hal berbeda: benar-benar tidak ada transaksi,
    ATAU data belum tersedia. Deret nol yang panjang biasanya pertanda masalah
    ketersediaan data, bukan kondisi pasar.

    Returns:
        DataFrame berisi periode deret nol dengan panjangnya.
    """
    values = np.asarray(values, dtype=float)
    dates = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)

    is_zero = (values == 0)
    runs = []
    start = None

    for i, z in enumerate(is_zero):
        if z and start is None:
            start = i
        elif not z and start is not None:
            if i - start >= min_run:
                runs.append((start, i - 1))
            start = None
    if start is not None and len(is_zero) - start >= min_run:
        runs.append((start, len(is_zero) - 1))

    if not runs:
        return pd.DataFrame(columns=['Mulai', 'Selesai', 'Jumlah Hari'])

    return pd.DataFrame({
        'Mulai': [dates.iloc[s].strftime('%Y-%m-%d') for s, _ in runs],
        'Selesai': [dates.iloc[e].strftime('%Y-%m-%d') for _, e in runs],
        'Jumlah Hari': [e - s + 1 for s, e in runs],
    }).sort_values('Jumlah Hari', ascending=False).reset_index(drop=True)


def analyze_date_gaps(dates, expect_business_days=True):
    """
    Cari lompatan tanggal yang tidak wajar dalam deret.

    Kalau expect_business_days=True, gap normal adalah 1-3 hari kalender
    (akhir pekan). Gap lebih dari itu ditandai sebagai potensi data hilang.
    """
    dates = pd.to_datetime(pd.Series(dates)).sort_values().reset_index(drop=True)
    if len(dates) < 2:
        return pd.DataFrame(columns=['Dari', 'Sampai', 'Selisih Hari'])

    diffs = dates.diff().dt.days
    threshold = 4 if expect_business_days else 1
    gap_idx = diffs[diffs > threshold].index

    if len(gap_idx) == 0:
        return pd.DataFrame(columns=['Dari', 'Sampai', 'Selisih Hari'])

    return pd.DataFrame({
        'Dari': dates.iloc[gap_idx - 1].dt.strftime('%Y-%m-%d').values,
        'Sampai': dates.iloc[gap_idx].dt.strftime('%Y-%m-%d').values,
        'Selisih Hari': diffs.iloc[gap_idx].astype(int).values,
    }).sort_values('Selisih Hari', ascending=False).reset_index(drop=True)


def rolling_statistics(values, window=90):
    """Rolling mean & std - dasar visual untuk melihat pergeseran level/volatilitas."""
    s = pd.Series(np.asarray(values, dtype=float))
    return {
        'mean': s.rolling(window=window, min_periods=max(2, window // 3)).mean().values,
        'std': s.rolling(window=window, min_periods=max(2, window // 3)).std().values,
    }
