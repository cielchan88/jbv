"""Centralized forecasting module for consistent predictions across all pages"""

from .base import BaseForecaster
from .randomforest_model import RandomForestForecaster
from .xgboost_model import XGBoostForecaster
from .lightgbm_model import LightGBMForecaster
from .arima_model import ARIMAForecaster
from .prophet_model import ProphetForecaster
from .apuva_model import APUVAForecaster
from .croston_model import CrostonForecaster
from .stacking_model import StackingForecaster
from .var_model import VARForecaster
from .naive_model import NaiveForecaster
from .lstm_model import LSTMForecaster
from .predictor import forecast_single_series, forecast_hierarchical

__all__ = [
    'BaseForecaster',
    'RandomForestForecaster',
    'XGBoostForecaster',
    'LightGBMForecaster',
    'ARIMAForecaster',
    'ProphetForecaster',
    'APUVAForecaster',
    'CrostonForecaster',
    'StackingForecaster',
    'LSTMForecaster',
    'VARForecaster',
    'NaiveForecaster',
    'forecast_single_series',
    'forecast_hierarchical',
]
