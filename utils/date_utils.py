"""
Date Utilities

Helper functions for working with dates, holidays, and business dates.
"""

import pandas as pd
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
HOLIDAYS_FILE = BASE_DIR / "config" / "holidays.json"

# Tanggal mulai data yang dipakai model ML (RandomForest/XGBoost/LightGBM/Prophet/
# ARIMA/VAR/Stacking di pages/4,5,6). Sebelumnya dipatok "2019-01-01" karena
# data/external_features.xlsx baru tersedia dari situ - sekarang external
# features dimatikan sementara (lihat utils/external_loader.py:ENABLE_EXTERNAL_FEATURES),
# jadi alasan pembatasan itu sudah tidak berlaku. None berarti ML pakai seluruh
# histori yang sama dengan yang dipakai APUVA/ETL (tidak ada cutoff terpisah lagi).
# Set balik ke string 'YYYY-MM-DD' di sini kalau external features diaktifkan lagi
# dan butuh titik mulai yang selaras dengannya.
ML_START_DATE = None


def load_holidays():
    """
    Load holidays from JSON file

    Returns:
        list: List of datetime.date objects representing holidays
    """
    if os.path.exists(HOLIDAYS_FILE):
        try:
            with open(HOLIDAYS_FILE, 'r') as f:
                holidays = json.load(f)
            return [pd.to_datetime(h['tanggal']).date() for h in holidays]
        except:
            return []
    return []


def generate_business_dates(start_date, num_days, holidays):
    """
    Generate business dates skipping weekends and holidays

    Args:
        start_date: Starting date (pandas Timestamp)
        num_days: Number of business days to generate
        holidays: List of holiday dates

    Returns:
        list: List of pandas Timestamps representing business dates
    """
    business_dates = []
    current_date = start_date

    while len(business_dates) < num_days:
        current_date = current_date + pd.Timedelta(days=1)

        # Skip weekends (Saturday=5, Sunday=6)
        if current_date.dayofweek >= 5:
            continue

        # Skip holidays
        if current_date.date() in holidays:
            continue

        business_dates.append(current_date)

    return business_dates
