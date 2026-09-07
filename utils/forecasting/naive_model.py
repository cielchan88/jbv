"""
Naive baseline forecasters.

Gunanya BUKAN untuk dipakai sebagai model produksi, tapi sebagai GARIS ACUAN:
tanpa pembanding trivial, metrik seperti "R2 = -0.18" atau "MAE = 37" tidak
punya arti - tidak ada cara tahu apakah model canggih benar-benar memberi nilai
tambah dibanding tebakan paling sederhana.

Aturan praktisnya: model apa pun yang tidak bisa mengalahkan baseline ini tidak
layak dipakai, karena baseline ini gratis secara komputasi dan tidak perlu
dilatih, di-tuning, atau dipelihara.
"""

import numpy as np
import pandas as pd
from .base import BaseForecaster
from .. import generate_business_dates


class NaiveForecaster(BaseForecaster):
    """
    Baseline sederhana untuk pembanding.

    method:
        'last'   - ulangi nilai terakhir yang teramati (random-walk / persistence).
                   Baseline standar untuk deret yang mendekati random walk.
        'mean'   - rata-rata `window` observasi terakhir (default 90 hari).
                   Baseline untuk deret yang mean-reverting.
        'drift'  - nilai terakhir + tren linear rata-rata dari seluruh histori.
    """

    def __init__(self, holidays=None, method='last', window=90):
        super().__init__(holidays)
        self.method = method
        self.window = window

    def fit(self, dates, values):
        values = np.asarray(values, dtype=float)
        values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)

        self.last_date = pd.to_datetime(dates[-1])
        self.values_ = values

        if len(values) == 0:
            self.forecast_value_ = 0.0
            self.drift_ = 0.0
            return self

        if self.method == 'mean':
            w = min(self.window, len(values))
            self.forecast_value_ = float(np.mean(values[-w:]))
        else:  # 'last' dan 'drift' sama-sama berangkat dari nilai terakhir
            self.forecast_value_ = float(values[-1])

        # Drift rata-rata per langkah (Hyndman's drift method)
        if self.method == 'drift' and len(values) > 1:
            self.drift_ = float((values[-1] - values[0]) / (len(values) - 1))
        else:
            self.drift_ = 0.0

        return self

    def predict(self, dates, values, n_days):
        if not hasattr(self, 'forecast_value_'):
            raise ValueError("Model not fitted. Call fit() first.")

        future_business_dates = generate_business_dates(self.last_date, n_days, self.holidays)

        if self.method == 'drift' and self.drift_ != 0.0:
            forecast_values = [
                self.forecast_value_ + self.drift_ * (i + 1)
                for i in range(len(future_business_dates))
            ]
        else:
            forecast_values = [self.forecast_value_] * len(future_business_dates)

        return forecast_values, future_business_dates
