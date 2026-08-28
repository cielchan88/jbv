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


class ARIMAForecaster(BaseForecaster):
    """ARIMA forecaster with automatic order selection (AutoARIMA)"""

    def __init__(self, holidays=None, order=None, auto_select=True,
                 grid_search_window=GRID_SEARCH_MAX_WINDOW):
        super().__init__(holidays)
        self.order = order
        self.auto_select = auto_select  # Enable AutoARIMA by default
        self.grid_search_window = grid_search_window

    def fit(self, dates, values):
        """Fit ARIMA model with optional grid search (AutoARIMA)"""
        self.last_date = pd.to_datetime(dates[-1])

        if self.auto_select:
            # AutoARIMA: Grid search for best parameters (SAME AS Prediksi.py)
            best_aic = np.inf
            best_order = None

            # Define parameter ranges
            p_values = range(0, 4)
            d_values = range(0, 3)
            q_values = range(0, 4)

            # Cari order pada jendela terakhir saja (lihat catatan di
            # GRID_SEARCH_MAX_WINDOW) - model final tetap pakai seluruh data.
            values_arr = np.asarray(values, dtype=float)
            if self.grid_search_window is not None and len(values_arr) > self.grid_search_window:
                search_values = values_arr[-self.grid_search_window:]
            else:
                search_values = values_arr

            # Generate all combinations and find best
            for p, d, q in itertools.product(p_values, d_values, q_values):
                try:
                    temp_model = SARIMAX(search_values, order=(p, d, q), enforce_stationarity=False, enforce_invertibility=False)
                    temp_fit = temp_model.fit(disp=False, maxiter=200)

                    if temp_fit.aic < best_aic:
                        best_aic = temp_fit.aic
                        best_order = (p, d, q)
                except:
                    continue

            if best_order is None:
                # Fallback to simple order
                self.order = (1, 1, 1)
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
