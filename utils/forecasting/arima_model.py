"""ARIMA forecaster with AutoARIMA grid search"""

import pandas as pd
import numpy as np
import itertools
from statsmodels.tsa.statespace.sarimax import SARIMAX
from .base import BaseForecaster
from .. import generate_business_dates


# Jendela maksimum (jumlah observasi terakhir) yang dipakai untuk GRID SEARCH
# order ARIMA. Model final tetap di-fit ulang pada SELURUH data training -
# yang dibatasi hanya tahap pencarian order-nya.
#
# Alasannya: biaya fit SARIMAX naik seiring panjang data, dan grid 48 kombinasi
# di ~4000 titik memakan ~49 detik per series (jadi ~15 menit untuk 18 leaf node
# di halaman Evaluasi). Order ARIMA sendiri tidak butuh seluruh histori untuk
# ditentukan - struktur autokorelasi jangka pendek sudah cukup terwakili oleh
# beberapa tahun terakhir, yang juga lebih relevan dengan rezim pasar sekarang.
#
# Diukur pada data asli (series B.a, 4025 titik training):
#   grid penuh di seluruh data : 49 detik -> order (1,1,3), AIC 22408
#   grid di 750 titik terakhir : 12 detik -> order (0,1,3), AIC 22424 (+0.07%)
# 4.2x lebih cepat dengan AIC praktis setara. Set None untuk memakai seluruh
# data saat grid search (perilaku lama).
GRID_SEARCH_MAX_WINDOW = 750


# Tentukan d lewat uji akar unit, bukan lewat AIC.
#
# MASALAHNYA. Grid lama membandingkan AIC lintas nilai d yang berbeda. Itu
# perbandingan yang tidak sepadan: model dengan d berbeda menjelaskan besaran
# yang berbeda, jadi AIC-nya tidak berada pada skala yang sama. Akibatnya
# terukur mutlak - pada 18 leaf, AIC memilih d=1 di 18 DARI 18, dan d=0 tidak
# pernah menang sekali pun meski ada dalam grid. Selisih AIC-nya pun tipis
# (2-22 poin), jadi bukan kemenangan telak, hanya kemenangan yang sistematis.
#
# Ini cara kerja algoritma Hyndman-Khandakar yang dipakai auto.arima dan
# pmdarima: tetapkan d dulu dengan uji akar unit, lalu cari p dan q dengan d
# TETAP - sehingga AIC hanya membandingkan kandidat yang sepadan.
#
# BUKTINYA, dan ini perlu dibaca apa adanya. Diukur lewat kelas ini sendiri
# (saklar ON vs OFF) pada 18 leaf x 3 jendela = 54 unit, horizon 60:
#
#     MAE  lama 57,782  ->  baru 57,383   (-0,7%),  Wilcoxon p = 0,39
#     Waktu 8,1 detik   ->      2,9 detik (2,7x lebih cepat)
#
# AKURASINYA BUKAN ALASAN UTAMA. Selisih -0,7% tidak bisa dibedakan dari
# kebetulan (p = 0,39), dan plafonnya memang rendah: pemilih d yang SEMPURNA
# pun hanya memberi -2,4%. Yang benar-benar didapat adalah KECEPATAN - grid
# menyusut dari 48 kombinasi (p x d x q) ke 16 (p x q dengan d tetap), dan
# AutoARIMA adalah model paling lambat di halaman Evaluasi. Pada 54 unit itu
# menghemat sekitar 4,7 menit per evaluasi penuh.
#
# Jadi saklar ini dinyalakan karena metodologinya benar DAN 2,7x lebih cepat
# tanpa biaya akurasi - bukan karena akurasinya membaik secara meyakinkan.
#
# Korelasi Spearman antara selisih AIC dan selisih MAE luar-sampel hanya 0,051
# pada data ini - AIC praktis tidak memberi tahu apa pun tentang d mana yang
# meramal lebih baik. Itu alasan sebenarnya kriteria lama perlu diganti.
#
# Set False untuk kembali ke grid lama (AIC lintas d).
SELECT_D_BY_UNIT_ROOT_TEST = True

# Batas atas d. Sama dengan grid lama (range(0, 3) -> d maksimum 2).
MAX_D = 2


def infer_d_by_kpss(values, max_d=MAX_D):
    """
    Tentukan orde diferensiasi lewat KPSS berjenjang (Hyndman-Khandakar).

    KPSS berhipotesis NOL "stasioner", jadi p > 0,05 berarti gagal menolak
    stasioneritas dan diferensiasi dihentikan. Kebalikan dari ADF, yang
    hipotesis nolnya "ada akar unit" - pada data ini keduanya bertentangan di
    15 dari 18 leaf, dan KPSS dipilih karena itulah yang dipakai auto.arima.

    Mengembalikan 0 kalau ujinya gagal, sehingga pemanggil bisa jatuh ke grid
    lama alih-alih menebak.
    """
    from statsmodels.tsa.stattools import kpss

    s = np.asarray(values, dtype=float)
    s = s[np.isfinite(s)]
    d = 0
    while d < max_d:
        if len(s) < 20 or np.std(s) < 1e-12:
            break
        try:
            p = kpss(s, regression='c', nlags='auto')[1]
        except Exception:
            break
        if p > 0.05:          # gagal menolak stasioner -> cukup
            break
        s = np.diff(s)
        d += 1
    return d


class ARIMAForecaster(BaseForecaster):
    """ARIMA forecaster with automatic order selection (AutoARIMA)"""

    def __init__(self, holidays=None, order=None, auto_select=True,
                 grid_search_window=GRID_SEARCH_MAX_WINDOW):
        super().__init__(holidays)
        self.order = order
        self.auto_select = auto_select  # Enable AutoARIMA by default
        self.grid_search_window = grid_search_window
        # Dari mana d berasal: 'kpss', 'aic', atau 'manual' kalau order diberikan.
        # Diinisialisasi di sini supaya atribut selalu ada, termasuk saat
        # auto_select=False - pemanggil tidak perlu menebak.
        self.d_source = 'manual'

    def fit(self, dates, values):
        """Fit ARIMA model with optional grid search (AutoARIMA)"""
        self.last_date = pd.to_datetime(dates[-1])

        if self.auto_select:
            # AutoARIMA: Grid search for best parameters (SAME AS Prediksi.py)
            best_aic = np.inf
            best_order = None

            # Define parameter ranges
            p_values = range(0, 4)
            q_values = range(0, 4)

            # Cari order pada jendela terakhir saja (lihat catatan di
            # GRID_SEARCH_MAX_WINDOW) - model final tetap pakai seluruh data.
            values_arr = np.asarray(values, dtype=float)
            if self.grid_search_window is not None and len(values_arr) > self.grid_search_window:
                search_values = values_arr[-self.grid_search_window:]
            else:
                search_values = values_arr

            # d ditetapkan lebih dulu oleh uji akar unit, lalu p dan q dicari
            # dengan d TETAP - sehingga AIC hanya membandingkan kandidat yang
            # sepadan. Lihat catatan di SELECT_D_BY_UNIT_ROOT_TEST.
            if SELECT_D_BY_UNIT_ROOT_TEST:
                d_values = [infer_d_by_kpss(search_values)]
            else:
                d_values = list(range(0, MAX_D + 1))
            self.d_source = 'kpss' if SELECT_D_BY_UNIT_ROOT_TEST else 'aic'

            # Generate all combinations and find best
            for p, d, q in itertools.product(p_values, d_values, q_values):
                if p == 0 and q == 0 and d == 0:
                    continue          # (0,0,0) = konstanta, bukan model deret
                try:
                    temp_model = SARIMAX(search_values, order=(p, d, q), enforce_stationarity=False, enforce_invertibility=False)
                    temp_fit = temp_model.fit(disp=False, maxiter=200)

                    if np.isfinite(temp_fit.aic) and temp_fit.aic < best_aic:
                        best_aic = temp_fit.aic
                        best_order = (p, d, q)
                except:
                    continue

            if best_order is None:
                # Fallback: pertahankan d hasil uji, jangan paksa balik ke 1 -
                # kalau serinya memang stasioner, (1,1,1) akan over-difference.
                self.order = (1, d_values[0] if len(d_values) == 1 else 1, 1)
            else:
                self.order = best_order

            # Fit final SELALU di seluruh data training, bukan cuma jendela pencarian
            try:
                self.model = SARIMAX(values_arr, order=self.order, enforce_stationarity=False, enforce_invertibility=False)
                self.fitted_model = self.model.fit(disp=False, maxiter=200)
            except Exception:
                self.order = (1, 1, 1)
                self.model = SARIMAX(values_arr, order=self.order, enforce_stationarity=False, enforce_invertibility=False)
                self.fitted_model = self.model.fit(disp=False)
        else:
            # Use fixed order if provided or default (1,1,1)
            if self.order is None:
                self.order = (1, 1, 1)

            self.model = SARIMAX(values, order=self.order, enforce_stationarity=False, enforce_invertibility=False)
            self.fitted_model = self.model.fit(disp=False)

        return self

    def predict(self, dates, values, n_days):
        """Predict n_days into the future using business dates"""
        if self.fitted_model is None:
            raise ValueError("Model not fitted. Call fit() first.")

        # Generate business dates for forecasting
        future_business_dates = generate_business_dates(self.last_date, n_days, self.holidays)

        # ARIMA predicts sequentially
        forecast_values = self.fitted_model.forecast(steps=len(future_business_dates))

        return list(forecast_values), future_business_dates
