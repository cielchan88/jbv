"""ARIMA forecaster with AutoARIMA grid search"""

import pandas as pd
import numpy as np
import itertools
from statsmodels.tsa.statespace.sarimax import SARIMAX
from .base import BaseForecaster
from .. import generate_business_dates


class ARIMAForecaster(BaseForecaster):
    """ARIMA forecaster with automatic order selection (AutoARIMA)"""

    def __init__(self, holidays=None, order=None, auto_select=True):
        super().__init__(holidays)
        self.order = order
        self.auto_select = auto_select  # Enable AutoARIMA by default

    def fit(self, dates, values):
        """Fit ARIMA model with optional grid search (AutoARIMA)"""
        self.last_date = pd.to_datetime(dates[-1])

        if self.auto_select:
            # AutoARIMA: Grid search for best parameters (SAME AS Prediksi.py)
            best_aic = np.inf
            best_order = None
            best_model_fit = None

            # Define parameter ranges
            p_values = range(0, 4)
            d_values = range(0, 3)
            q_values = range(0, 4)

            # Generate all combinations and find best
            for p, d, q in itertools.product(p_values, d_values, q_values):
                try:
                    temp_model = SARIMAX(values, order=(p, d, q), enforce_stationarity=False, enforce_invertibility=False)
                    temp_fit = temp_model.fit(disp=False, maxiter=200)

                    if temp_fit.aic < best_aic:
                        best_aic = temp_fit.aic
                        best_order = (p, d, q)
                        best_model_fit = temp_fit
                except:
                    continue

            if best_model_fit is None:
                # Fallback to simple order
                self.model = SARIMAX(values, order=(1, 1, 1), enforce_stationarity=False, enforce_invertibility=False)
                self.fitted_model = self.model.fit(disp=False)
                self.order = (1, 1, 1)
            else:
                self.fitted_model = best_model_fit
                self.order = best_order
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
