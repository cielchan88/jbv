"""Base forecaster class for all models"""

class BaseForecaster:
    """Base class for all forecasters"""

    def __init__(self, holidays=None):
        self.holidays = holidays if holidays is not None else []
        self.model = None

    def fit(self, dates, values):
        """Fit the model on historical data"""
        raise NotImplementedError

    def predict(self, dates, values, n_days):
        """
        Predict n_days into the future (business days only)

        Returns:
        --------
        forecast_values : list
            Forecasted values
        forecast_dates : list
            Business dates for forecasts (weekends and holidays excluded)
        """
        raise NotImplementedError
