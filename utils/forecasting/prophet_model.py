"""Prophet forecaster"""

import pandas as pd
from prophet import Prophet
from .base import BaseForecaster
from .. import generate_business_dates
from ..feature_config import ENABLE_HOLIDAY_FEATURES


class ProphetForecaster(BaseForecaster):
    """Prophet forecaster"""

    def __init__(self, holidays=None):
        super().__init__(holidays)

    def fit(self, dates, values):
        """Fit Prophet model"""
        # Prepare data for Prophet
        prophet_df = pd.DataFrame({
            'ds': pd.to_datetime(dates),
            'y': values
        })

        kwargs = dict(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            changepoint_prior_scale=0.05
        )

        # Efek hari libur hanya dimodelkan kalau saklarnya hidup. Lihat
        # ENABLE_HOLIDAY_FEATURES di utils/feature_config.py untuk alasannya.
        if ENABLE_HOLIDAY_FEATURES and len(self.holidays) > 0:
            kwargs['holidays'] = pd.DataFrame({
                'holiday': 'holiday',
                'ds': pd.to_datetime(self.holidays),
                'lower_window': 0,
                'upper_window': 0
            })

        self.model = Prophet(**kwargs)
        self.model.fit(prophet_df)
        self.last_date = pd.to_datetime(dates[-1])

        return self

    def predict(self, dates, values, n_days):
        """Predict n_days into the future using business dates"""
        if self.model is None:
            raise ValueError("Model not fitted. Call fit() first.")

        # Generate business dates for forecasting
        future_business_dates = generate_business_dates(self.last_date, n_days, self.holidays)

        # Create future dataframe with business dates only
        future_df = pd.DataFrame({'ds': future_business_dates})

        # Predict
        forecast = self.model.predict(future_df)
        forecast_values = forecast['yhat'].tolist()

        return forecast_values, future_business_dates
