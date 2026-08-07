"""VAR (Vector Autoregression) forecaster for multivariate time series"""

import pandas as pd
import numpy as np
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import adfuller
from .base import BaseForecaster
from .. import generate_business_dates


class VARForecaster(BaseForecaster):
    """VAR forecaster for multivariate time series with automatic lag selection"""

    def __init__(self, holidays=None, maxlags=None, ic='aic'):
        """
        Initialize VAR forecaster.

        Parameters:
        -----------
        holidays : list, optional
            List of holiday dates to skip
        maxlags : int, optional
            Maximum number of lags to consider. If None, uses min(10, nobs/5)
        ic : str, default 'aic'
            Information criterion for lag selection ('aic', 'bic', 'hqic', 'fpe')
        """
        super().__init__(holidays)
        self.maxlags = maxlags
        self.ic = ic
        self.fitted_model = None
        self.optimal_lag = None
        self.diff_order = {}  # Track differencing for each series
        self.last_values = {}  # Store last values for inverse differencing
        self.series_names = []

    def _check_stationarity(self, series, significance=0.05):
        """Check if series is stationary using ADF test"""
        try:
            result = adfuller(series.dropna(), autolag='AIC')
            return result[1] < significance  # p-value < significance means stationary
        except:
            return True  # Assume stationary if test fails

    def _make_stationary(self, df):
        """
        Make all series stationary through differencing if needed.
        Returns differenced dataframe and tracks differencing order.
        """
        df_stationary = df.copy()

        for col in df.columns:
            series = df[col]
            d = 0

            # Store original last values for inverse differencing
            self.last_values[col] = series.iloc[-1]

            # Check stationarity and difference if needed (max 2 times)
            temp_series = series.copy()
            while not self._check_stationarity(temp_series) and d < 2:
                temp_series = temp_series.diff().dropna()
                d += 1

            self.diff_order[col] = d
            if d > 0:
                df_stationary[col] = df[col].diff(d)

        return df_stationary.dropna()

    def _inverse_difference(self, forecasts, col_idx, col_name):
        """Inverse differencing to get original scale forecasts"""
        d = self.diff_order.get(col_name, 0)

        if d == 0:
            return forecasts

        result = np.array(forecasts).copy()
        last_val = self.last_values[col_name]

        # Inverse differencing: cumsum and add last value
        for _ in range(d):
            result = last_val + np.cumsum(result)

        return result

    def fit(self, dates, values, external_series=None):
        """
        Fit VAR model on historical data.

        Parameters:
        -----------
        dates : array-like
            Historical dates
        values : array-like
            Historical values for the main series
        external_series : dict, optional
            Dict of external series for VAR modeling {series_id: values_array}
            If None or empty, falls back to univariate ARIMA-like behavior
        """
        self.last_date = pd.to_datetime(dates[-1])

        # Prepare multivariate data
        df = pd.DataFrame({'main': values}, index=pd.to_datetime(dates))
        self.series_names = ['main']

        # Add external series if provided
        if external_series and len(external_series) > 0:
            for series_id, series_values in external_series.items():
                if len(series_values) == len(values):
                    col_name = str(series_id)[:20]  # Truncate long names
                    df[col_name] = series_values
                    self.series_names.append(col_name)

        # Make all series stationary
        df_stationary = self._make_stationary(df)

        if len(df_stationary) < 10:
            # Not enough data, use simple approach
            self.fitted_model = None
            self._fallback_values = values
            return self

        try:
            model = VAR(df_stationary)
            # Select optimal lag using information criterion
            maxlags = self.maxlags or min(10, len(df_stationary) // 5)
            maxlags = max(1, min(maxlags, len(df_stationary) - 1))

            # Fit with lag selection
            self.fitted_model = model.fit(maxlags=maxlags, ic=self.ic)
            self.optimal_lag = self.fitted_model.k_ar

            # Ensure minimum lag of 1 for forecasting
            if self.optimal_lag == 0:
                self.fitted_model = model.fit(1)
                self.optimal_lag = 1

        except Exception as e:
            print(f"VAR fit warning: {str(e)}, using fallback")
            self.fitted_model = None
            self._fallback_values = values

        self._original_df = df
        return self

    def predict(self, dates, values, n_days):
        """
        Predict n_days into the future using business dates.

        Parameters:
        -----------
        dates : array-like
            Historical dates (used for context)
        values : array-like
            Historical values (used for context)
        n_days : int
            Number of business days to forecast

        Returns:
        --------
        forecast_values : list
            Forecasted values for the main series
        forecast_dates : list
            Business dates for forecasts
        """
        # Generate business dates for forecasting
        future_business_dates = generate_business_dates(self.last_date, n_days, self.holidays)

        if self.fitted_model is None:
            # Fallback: use last value or simple mean
            if hasattr(self, '_fallback_values') and len(self._fallback_values) > 0:
                last_val = self._fallback_values[-1]
                forecast_values = [last_val] * len(future_business_dates)
            else:
                forecast_values = [0] * len(future_business_dates)
            return forecast_values, future_business_dates

        try:
            # VAR forecast
            lag_order = self.fitted_model.k_ar
            forecast_input = self.fitted_model.endog[-lag_order:]

            # Forecast
            forecast_result = self.fitted_model.forecast(forecast_input, steps=len(future_business_dates))

            # Get main series forecast (first column)
            main_forecast = forecast_result[:, 0]

            # Inverse difference to get original scale
            forecast_values = self._inverse_difference(main_forecast, 0, 'main')

            return list(forecast_values), future_business_dates

        except Exception as e:
            print(f"VAR predict warning: {str(e)}, using fallback")
            # Fallback
            if hasattr(self, '_original_df'):
                last_val = self._original_df['main'].iloc[-1]
                forecast_values = [last_val] * len(future_business_dates)
            else:
                forecast_values = [values[-1] if len(values) > 0 else 0] * len(future_business_dates)
            return forecast_values, future_business_dates

    def get_model_summary(self):
        """Get summary of the fitted VAR model"""
        if self.fitted_model is None:
            return "Model not fitted or using fallback"

        return {
            'optimal_lag': self.optimal_lag,
            'series_count': len(self.series_names),
            'series_names': self.series_names,
            'diff_orders': self.diff_order,
            'aic': self.fitted_model.aic,
            'bic': self.fitted_model.bic
        }
