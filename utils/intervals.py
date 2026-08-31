"""
Interval prediksi empiris berbasis backtest.

Menggantikan pendekatan lama di Lembar Kerja yang punya empat cacat sekaligus:

1. Residual dihitung IN-SAMPLE (`model.predict(X_train)`). RandomForest dengan
   max_depth=10 menghafal sebagian data latihnya, jadi residualnya jauh lebih
   kecil daripada error sesungguhnya - pita jadi terlalu sempit.
2. Lebar pita KONSTAN sepanjang horizon. Ketidakpastian forecast tumbuh seiring
   langkah; pita hari ke-60 tidak mungkin sama dengan hari ke-1.
3. Memakai kuantil normal (1,96) padahal uji normalitas DITOLAK di 18 dari 18
   leaf (Jarque-Bera, D'Agostino, Anderson-Darling, Shapiro-Wilk). Dengan ekor
   setebal itu, 1,96 sigma tidak mencakup 95%.
4. Mengabaikan volatility clustering, padahal itu struktur terkuat di data:
   autokorelasi |perubahan| lag-1 bermedian 0,489 dan positif di 18 dari 18
   leaf. Volatilitas bisa diprediksi, jadi lebar pita seharusnya mengikuti
   kondisi terkini - menyempit di periode tenang, melebar di periode bergejolak.

Pendekatan di sini:
  - Backtest rolling-origin memakai forecast_single_series(), yaitu jalur yang
    SAMA dengan produksi (recursive), sehingga error yang diukur adalah error
    yang benar-benar akan terjadi.
  - Skala error diukur PER LANGKAH HORIZON, lalu dipaksa monoton tidak-menurun.
  - Kuantil diambil EMPIRIS dari error yang sudah dinormalisasi, bukan dari
    asumsi normal - sehingga asimetri dan ekor tebal ikut terwakili.
  - Skala akhir disesuaikan dengan rasio volatilitas terkini terhadap
    volatilitas periode backtest.
"""

import numpy as np
import pandas as pd

# Batas rasio volatilitas. Tanpa batas, satu periode anomali di ujung histori
# bisa melipatgandakan pita sampai tidak berguna.
VOL_RATIO_MIN = 0.5
VOL_RATIO_MAX = 2.0

# Minimal data latih yang disisakan setiap jendela backtest.
MIN_TRAIN = 300


def _ewma_abs_change(values, span):
    """Volatilitas EWMA dari besaran perubahan harian."""
    d = np.abs(np.diff(np.asarray(values, dtype=float)))
    if len(d) == 0:
        return 0.0
    s = pd.Series(d).ewm(span=min(span, len(d)), adjust=False).mean()
    return float(s.iloc[-1])


def _monotone_scale(raw):
    """
    Paksa kurva skala tidak-menurun terhadap horizon.

    Error per langkah dari sedikit jendela sangat berisik; tanpa ini pita bisa
    menyempit di langkah jauh, yang tidak masuk akal secara struktural.
    Cumulative-max dipilih ketimbang regresi isotonik supaya tidak menambah
    dependensi dan perilakunya mudah ditebak.
    """
    raw = np.asarray(raw, dtype=float)
    out = np.maximum.accumulate(raw)
    return out


def calibrate_intervals(dates, values, model_name, horizon,
                        holidays=None, external_series=None, row_id=None,
                        n_windows=2, alpha=0.05, vol_span=60):
    """
    Kalibrasi interval lewat backtest rolling-origin.

    Returns dict:
        scale     : ndarray (horizon,) skala error per langkah
        q_lo, q_hi: kuantil empiris dari error terstandardisasi
        vol_ratio : penyesuaian volatilitas terkini
        n_errors  : jumlah pasangan error yang dipakai
        method    : 'backtest' atau 'fallback'
        note      : penjelasan singkat untuk ditampilkan ke user
    """
    from .forecasting import forecast_single_series

    values = np.asarray(values, dtype=float)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    horizon = int(horizon)

    dates_idx = pd.to_datetime(pd.Series(list(dates)))
    err_by_step = {h: [] for h in range(horizon)}
    used_windows = 0
    backtest_span_start = len(values)

    for w in range(int(n_windows)):
        end = len(values) - w * horizon
        start = end - horizon
        if start < MIN_TRAIN:
            break

        tr_v = values[:start]
        tr_d = dates_idx.iloc[:start].dt.strftime('%Y-%m-%d').tolist()
        actual = values[start:end]

        try:
            fv, _ = forecast_single_series(
                dates=tr_d, values=tr_v, model_name=model_name,
                n_days=len(actual), holidays=holidays,
                external_series=external_series, row_id=row_id)
            fv = np.asarray(fv, dtype=float)
        except Exception:
            continue

        if len(fv) == 0 or not np.all(np.isfinite(fv)):
            continue

        n = min(len(fv), len(actual))
        for h in range(n):
            err_by_step[h].append(float(actual[h] - fv[h]))

        used_windows += 1
        backtest_span_start = min(backtest_span_start, start)

    total_errors = sum(len(v) for v in err_by_step.values())

    # ---- Fallback: backtest tidak memungkinkan (histori terlalu pendek) ----
    #
    # Tetap jauh lebih baik daripada residual in-sample: memakai sebaran
    # perubahan harian yang benar-benar teramati, dan tetap melebar seiring
    # horizon mengikuti akar kuadrat langkah.
    if used_windows == 0 or total_errors == 0:
        d = np.diff(values)
        base = float(np.std(d, ddof=1)) if len(d) > 1 else float(np.std(values))
        if not np.isfinite(base) or base <= 0:
            base = max(float(np.std(values)), 1e-6)
        scale = base * np.sqrt(np.arange(1, horizon + 1, dtype=float))
        # Kuantil empiris dari perubahan harian yang distandardisasi
        if len(d) > 20 and base > 0:
            z = d / base
            q_lo = float(np.quantile(z, alpha / 2))
            q_hi = float(np.quantile(z, 1 - alpha / 2))
        else:
            q_lo, q_hi = -1.96, 1.96
        return {'scale': scale, 'q_lo': q_lo, 'q_hi': q_hi, 'vol_ratio': 1.0,
                'n_errors': 0, 'method': 'fallback',
                'note': 'Histori tidak cukup untuk backtest; pita diperkirakan '
                        'dari sebaran perubahan harian dengan pelebaran akar-horizon.'}

    # ---- Skala per langkah ----
    #
    # Median |error| per langkah, diskalakan ke satuan "simpangan" lewat 1,4826
    # (konsisten dengan MAD) supaya kuantil terstandardisasi di bawah punya
    # besaran yang wajar. Langkah tanpa data mengambil nilai terakhir yang ada.
    raw = np.zeros(horizon, dtype=float)
    last = None
    for h in range(horizon):
        if err_by_step[h]:
            raw[h] = 1.4826 * float(np.median(np.abs(err_by_step[h])))
            last = raw[h]
        elif last is not None:
            raw[h] = last
    if last is None:
        last = 1e-6
    raw[raw <= 0] = max(np.median(raw[raw > 0]) if np.any(raw > 0) else last, 1e-6)
    scale = _monotone_scale(raw)

    # ---- Kuantil empiris dari error terstandardisasi ----
    #
    # Semua error dari semua langkah dibagi skala langkahnya masing-masing,
    # sehingga bisa dikumpulkan jadi satu sebaran. Kuantilnya diambil langsung
    # dari sebaran itu - inilah yang membuat asimetri dan ekor tebal terwakili,
    # alih-alih dipaksa ke +/-1,96.
    z = []
    for h in range(horizon):
        if scale[h] > 0:
            z.extend([e / scale[h] for e in err_by_step[h]])
    z = np.asarray(z, dtype=float)
    z = z[np.isfinite(z)]

    if len(z) >= 20:
        q_lo = float(np.quantile(z, alpha / 2))
        q_hi = float(np.quantile(z, 1 - alpha / 2))
    else:
        # Terlalu sedikit titik untuk kuantil empiris yang stabil.
        q_lo, q_hi = -1.96, 1.96

    # Jaga agar pita tidak kolaps kalau kebetulan backtest-nya mulus
    if q_hi - q_lo < 0.5:
        q_lo, q_hi = min(q_lo, -0.25), max(q_hi, 0.25)

    # ---- Penyesuaian volatilitas terkini ----
    #
    # Inilah bagian yang menjawab volatility clustering: kalau pasar sedang
    # bergejolak dibanding periode backtest, pita melebar; kalau tenang,
    # menyempit.
    vol_now = _ewma_abs_change(values[-max(vol_span * 3, 120):], vol_span)
    vol_bt = _ewma_abs_change(values[max(backtest_span_start - vol_span * 3, 0):], vol_span)
    if vol_bt > 1e-9 and np.isfinite(vol_now):
        vol_ratio = float(np.clip(vol_now / vol_bt, VOL_RATIO_MIN, VOL_RATIO_MAX))
    else:
        vol_ratio = 1.0

    return {
        'scale': scale, 'q_lo': q_lo, 'q_hi': q_hi, 'vol_ratio': vol_ratio,
        'n_errors': int(len(z)), 'method': 'backtest',
        'note': f'Dikalibrasi dari {used_windows} jendela backtest '
                f'({len(z)} error), kuantil empiris, faktor volatilitas '
                f'{vol_ratio:.2f}x.'
    }


def mean_pairwise_correlation(series_matrix, on_changes=True):
    """
    Rata-rata korelasi pasangan antar seri, dijepit ke [0, 1].

    Dipakai untuk menggabungkan interval anak menjadi interval induk. Yang
    relevan adalah korelasi pada PERUBAHAN harian, bukan pada level: korelasi
    level pada data ini didominasi tren bersama (median |rho| 0,197, maks
    0,859) sedangkan pada perubahan harian median |rho| hanya 0,070 dan tidak
    ada satu pun pasangan di atas 0,384 - untuk keperluan peramalan, seri-seri
    ini praktis independen.

    series_matrix: DataFrame, satu kolom per seri anak.
    """
    m = pd.DataFrame(series_matrix).astype(float)
    if on_changes:
        m = m.diff().dropna(how='all')
    if m.shape[1] < 2 or len(m) < 30:
        return 0.0
    c = m.corr(method='spearman').to_numpy(copy=True)
    if c.size == 0:
        return 0.0
    np.fill_diagonal(c, np.nan)
    r = np.nanmean(c)
    if not np.isfinite(r):
        return 0.0
    return float(np.clip(r, 0.0, 1.0))


def combine_halfwidths(sum_h, sum_h_sq, rho_bar):
    """
    Gabungkan setengah-lebar interval anak menjadi setengah-lebar induk.

    Menjumlahkan batas atas anak-anak - yang dilakukan kode sebelumnya -
    diam-diam mengasumsikan seluruh anak bergerak serempak (korelasi = 1).
    Pada data ini asumsi itu salah: korelasi rata-rata perubahan harian antar
    leaf mendekati nol, sehingga sebagian error saling meniadakan saat
    dijumlahkan. Akibatnya pita di level induk jauh lebih lebar dari
    seharusnya - untuk 18 leaf yang independen, selisihnya bisa sampai
    sekitar akar-18 kali.

        Var(S) = sum(h_i^2) + rho_bar * [ (sum h_i)^2 - sum(h_i^2) ]

    rho_bar = 1 mengembalikan perilaku lama (sum h_i), rho_bar = 0 memberi
    sqrt(sum h_i^2). Diberi rho_bar terukur, hasilnya ada di antaranya.

    sum_h, sum_h_sq: hasil penjumlahan hierarkis biasa atas h dan h^2.
    """
    sum_h = np.asarray(sum_h, dtype=float)
    sum_h_sq = np.asarray(sum_h_sq, dtype=float)
    rho = float(np.clip(rho_bar, 0.0, 1.0))

    var = sum_h_sq + rho * (sum_h ** 2 - sum_h_sq)
    var = np.maximum(var, 0.0)
    return np.sqrt(var)


def apply_intervals(forecast_values, calib):
    """
    Terapkan hasil kalibrasi ke deret forecast.

    Returns (lower, upper), keduanya ndarray sepanjang forecast_values.
    """
    f = np.asarray(forecast_values, dtype=float)
    n = len(f)

    scale = np.asarray(calib['scale'], dtype=float)
    if len(scale) < n:
        scale = np.concatenate([scale, np.full(n - len(scale), scale[-1] if len(scale) else 0.0)])
    scale = scale[:n] * float(calib.get('vol_ratio', 1.0))

    lower = f + float(calib['q_lo']) * scale
    upper = f + float(calib['q_hi']) * scale
    return lower, upper
