"""Croston SBA forecaster for intermittent demand"""

import pandas as pd
import numpy as np
from .base import BaseForecaster
from .. import generate_business_dates


class CrostonForecaster(BaseForecaster):
    """
    Croston SBA (Syntetos-Boylan Approximation) forecaster for intermittent demand.

    Ideal for time series with:
    - Many zero values
    - Sporadic/irregular demand patterns
    - Low volume with irregular intervals

    The SBA variant applies a bias correction to the standard Croston method:
    forecast = (z / p) * (1 - alpha/2)

    Where:
    - z = smoothed demand size (when demand occurs)
    - p = smoothed inter-arrival time (intervals between demands)
    - alpha = smoothing parameter
    """

    def __init__(self, holidays=None, alpha=0.1):
        """
        Initialize Croston SBA forecaster.

        Parameters:
        -----------
        holidays : list, optional
            List of holiday dates to skip in forecasting
        alpha : float, default 0.1
            Smoothing parameter (0 < alpha < 1)
            Lower values = more smoothing, slower adaptation
            Higher values = less smoothing, faster adaptation
        """
        super().__init__(holidays)
        self.alpha = alpha
        self.z = None  # Smoothed demand size
        self.p = None  # Smoothed inter-arrival time
        self.forecast_value = None

    def fit(self, dates, values):
        """
        Fit Croston SBA model on historical data.

        Parameters:
        -----------
        dates : array-like
            Historical dates
        values : array-like
            Historical values (can contain zeros)

        Returns:
        --------
        self
        """
        self.last_date = pd.to_datetime(dates[-1])

        # Convert to numpy array
        values = np.array(values, dtype=float)
        values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)

        # Find non-zero demands
        non_zero_mask = values != 0
        non_zero_indices = np.where(non_zero_mask)[0]

        if len(non_zero_indices) < 2:
            # Not enough non-zero values, use simple average
            mean_value = np.mean(values) if np.mean(values) > 0 else 1.0
            self.z = mean_value
            self.p = len(values) / max(len(non_zero_indices), 1)
            self.forecast_value = self.z / self.p * (1 - self.alpha / 2)
            return self

        # Initialize z and p with first non-zero demand
        first_idx = non_zero_indices[0]
        self.z = values[first_idx]  # First demand size
        self.p = first_idx + 1 if first_idx > 0 else 1  # First inter-arrival time

        # Apply exponential smoothing for each subsequent non-zero demand
        for i in range(1, len(non_zero_indices)):
            current_idx = non_zero_indices[i]
            previous_idx = non_zero_indices[i - 1]

            # Demand size (z): actual demand when it occurs
            demand_size = values[current_idx]

            # Inter-arrival time (q): intervals between demands
            inter_arrival = current_idx - previous_idx

            # Exponential smoothing update
            self.z = self.alpha * demand_size + (1 - self.alpha) * self.z
            self.p = self.alpha * inter_arrival + (1 - self.alpha) * self.p

        # SBA bias correction: forecast = (z / p) * (1 - alpha/2)
        if self.p > 0:
            self.forecast_value = (self.z / self.p) * (1 - self.alpha / 2)
        else:
            self.forecast_value = self.z

        return self

    def predict(self, dates, values, n_days):
        """
        Predict n_days into the future using business dates.

        Croston produces a flat forecast (same value for all future periods)
        since it estimates the expected demand per period.

        Parameters:
        -----------
        dates : array-like
            Historical dates
        values : array-like
            Historical values
        n_days : int
            Number of business days to forecast

        Returns:
        --------
        forecast_values : list
            Forecasted values (flat forecast)
        forecast_dates : list
            Business dates for forecasts
        """
        if self.forecast_value is None:
            raise ValueError("Model not fitted. Call fit() first.")

        # Generate business dates for forecasting
        future_business_dates = generate_business_dates(self.last_date, n_days, self.holidays)

        # Croston produces flat forecast
        forecast_values = [float(self.forecast_value)] * len(future_business_dates)

        return forecast_values, future_business_dates
