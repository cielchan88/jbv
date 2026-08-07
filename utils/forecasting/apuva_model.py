"""APUVA (Algoritma Prediksi APUVA) - Baseline forecaster menggunakan proporsi historis"""

import pandas as pd
import numpy as np
from .base import BaseForecaster
from .. import generate_business_dates


class APUVAForecaster(BaseForecaster):
    """
    APUVA Forecaster - Baseline model berdasarkan algoritma eksisting.

    Formula:
    --------
    Prediksi = NILAI_KE_1 × NILAI_KE_2 × (1 + Faktor_Sentimen)

    NILAI_KE_1 = Proporsi_Bulan_Historis × Rata2_Tahunan
    - Proporsi_Bulan_Historis: Rata2 kontribusi bulan target untuk year-4, year-3, year-2
    - Rata2_Tahunan: Rata2 total tahunan untuk year-3, year-2, year-1

    NILAI_KE_2 = Proporsi_Tanggal_Dalam_Bulan
    - Rata2 nilai tanggal yang sama untuk year-6 sampai year-2
    - Dibagi dengan total rata2 bulan tersebut

    Faktor_Sentimen: Sentimen adjustment berdasarkan kategori transaksi
    """

    # Mapping faktor sentimen berdasarkan Row_ID
    SENTIMENT_FACTORS = {
        'A.1.a': 0.00,   # PTMN - Impor
        'A.1.b': 0.00,   # PTMN - Repatriasi
        'A.1.c': 0.00,   # PTMN - Lainnya
        'A.2.a': 0.80,   # Korporasi Lainnya - Ekspor
        'A.2.b': 1.37,   # Korporasi Lainnya - Transaksi tanpa underlying
        'A.2.c': 0.00,   # Korporasi Lainnya - Investasi
        'A.2.d': 0.25,   # Korporasi Lainnya - Impor
        'A.2.e': 0.00,   # Korporasi Lainnya - Repatriasi
        'A.2.f': 0.00,   # Korporasi Lainnya - Lainnya
        'B.a': 5.40,     # Individu - Ekspor
        'B.b': -2.20,    # Individu - Transaksi tanpa underlying
        'B.c': 0.10,     # Individu - Impor
        'B.d': 0.00,     # Individu - Lainnya
        'C.a': 0.49,     # Non Residen - Investasi
        'C.b': -0.50,    # Non Residen - Remittance
        'C.c': 1.95,     # Non Residen - Repatriasi
        'C.d': -0.40,    # Non Residen - Trading
        'C.e': 0.00,     # Non Residen - Lainnya
    }

    def __init__(self, holidays=None, row_id=None):
        super().__init__(holidays)
        self.row_id = row_id
        self.sentiment_factor = self.SENTIMENT_FACTORS.get(row_id, 0.0)

    def fit(self, dates, values):
        """
        Fit APUVA model - menyimpan data historis untuk perhitungan proporsi

        Parameters:
        -----------
        dates : array-like
            Historical dates (string format 'YYYY-MM-DD')
        values : array-like
            Historical values
        """
        # Convert to pandas for easier manipulation
        self.df_history = pd.DataFrame({
            'date': pd.to_datetime(dates),
            'value': values
        })
        self.df_history = self.df_history.sort_values('date')
        self.last_date = self.df_history['date'].iloc[-1]

        # Extract year, month, day
        self.df_history['year'] = self.df_history['date'].dt.year
        self.df_history['month'] = self.df_history['date'].dt.month
        self.df_history['day'] = self.df_history['date'].dt.day

        return self

    def _calculate_monthly_proportion(self, target_month, current_year):
        """
        Hitung NILAI_KE_1: Proporsi kontribusi bulan × Rata2 tahunan

        Steps:
        1. Hitung proporsi kontribusi bulan untuk year-4, year-3, year-2
        2. Rata-ratakan proporsi tersebut
        3. Hitung rata2 total tahunan untuk year-3, year-2, year-1
        4. Kalikan keduanya
        """
        # Proporsi bulan untuk year-4, year-3, year-2
        proportions = []
        for year_offset in [4, 3, 2]:
            year = current_year - year_offset

            # Total untuk bulan target di tahun tersebut
            month_total = self.df_history[
                (self.df_history['year'] == year) &
                (self.df_history['month'] == target_month)
            ]['value'].sum()

            # Total sepanjang tahun tersebut
            year_total = self.df_history[
                self.df_history['year'] == year
            ]['value'].sum()

            if year_total != 0:
                proportions.append(month_total / year_total)

        # Rata-ratakan proporsi (jika ada data)
        if len(proportions) > 0:
            avg_proportion = np.mean(proportions)
        else:
            avg_proportion = 1.0 / 12  # Fallback: asumsi distribusi merata

        # Rata2 total tahunan untuk year-3, year-2, year-1
        yearly_totals = []
        for year_offset in [3, 2, 1]:
            year = current_year - year_offset
            year_total = self.df_history[
                self.df_history['year'] == year
            ]['value'].sum()
            if year_total != 0:
                yearly_totals.append(year_total)

        if len(yearly_totals) > 0:
            avg_yearly = np.mean(yearly_totals)
        else:
            # Fallback: gunakan rata2 seluruh data
            avg_yearly = self.df_history['value'].sum() / self.df_history['year'].nunique()

        # NILAI_KE_1
        nilai_ke_1 = avg_proportion * avg_yearly
        return nilai_ke_1

    def _calculate_daily_proportion(self, target_month, target_day, current_year):
        """
        Hitung NILAI_KE_2: Proporsi tanggal dalam bulan

        Steps:
        1. Rata2 nilai tanggal yang sama untuk year-6 sampai year-2
        2. Total rata2 seluruh tanggal di bulan tersebut untuk year-6 sampai year-2
        3. Proporsi = rata2 tanggal / total rata2 bulan
        """
        # Rata2 nilai tanggal yang sama untuk year-6 sampai year-2
        # PENTING: Include nilai 0 (hari kerja dengan nilai 0), tapi skip blank (weekend/libur)
        daily_values = []
        for year_offset in [6, 5, 4, 3, 2]:
            year = current_year - year_offset

            # Cek apakah tanggal ini ada di dataset (hari kerja)
            day_data = self.df_history[
                (self.df_history['year'] == year) &
                (self.df_history['month'] == target_month) &
                (self.df_history['day'] == target_day)
            ]

            # Jika ada data (bukan blank/weekend), ambil nilainya (bisa 0 atau non-zero)
            if len(day_data) > 0:
                day_value = day_data['value'].sum()
                daily_values.append(day_value)

        if len(daily_values) > 0:
            avg_daily = np.mean(daily_values)
        else:
            # Fallback: gunakan rata2 hari di bulan tersebut
            month_data = self.df_history[self.df_history['month'] == target_month]
            if len(month_data) > 0:
                avg_daily = month_data['value'].mean()
            else:
                avg_daily = self.df_history['value'].mean()

        # JUMLAH dari rata2 setiap tanggal di bulan tersebut untuk year-6 sampai year-2
        # Contoh: untuk Sept, hitung rata2 setiap tanggal (1-30) lalu jumlahkan semua rata2 tersebut
        month_data = self.df_history[
            (self.df_history['month'] == target_month) &
            (self.df_history['year'].isin([current_year - i for i in [6, 5, 4, 3, 2]]))
        ]

        if len(month_data) > 0:
            # Untuk setiap unique day, hitung rata2 nilai untuk year 6-2
            unique_days = month_data['day'].unique()
            sum_of_daily_averages = 0

            for day in unique_days:
                day_values = month_data[month_data['day'] == day]['value'].values
                # INCLUDE zeros (hari kerja dengan nilai 0)
                # Hanya yang ada di dataset (bukan blank/weekend)
                if len(day_values) > 0:
                    avg_for_this_day = np.mean(day_values)
                    sum_of_daily_averages += avg_for_this_day

            avg_monthly_total = sum_of_daily_averages
        else:
            # Fallback: gunakan rata2 bulan dari seluruh data
            avg_monthly_total = self.df_history.groupby('month')['value'].sum().mean()

        # NILAI_KE_2: Proporsi
        if avg_monthly_total != 0:
            nilai_ke_2 = avg_daily / avg_monthly_total
        else:
            nilai_ke_2 = 1.0 / 20  # Fallback: asumsi 20 hari kerja per bulan

        return nilai_ke_2

    def predict(self, dates, values, n_days):
        """
        Predict n_days into the future using APUVA algorithm

        Returns:
        --------
        forecast_values : list
            Forecasted values
        forecast_dates : list
            Business dates for forecasts
        """
        if self.df_history is None:
            raise ValueError("Model not fitted. Call fit() first.")

        # Generate business dates for forecasting
        future_business_dates = generate_business_dates(self.last_date, n_days, self.holidays)

        forecast_values = []
        current_year = self.last_date.year

        for forecast_date in future_business_dates:
            target_month = forecast_date.month
            target_day = forecast_date.day

            # Jika forecast_date sudah di tahun berikutnya, update current_year
            if forecast_date.year > current_year:
                current_year = forecast_date.year

            # Hitung NILAI_KE_1
            nilai_ke_1 = self._calculate_monthly_proportion(target_month, current_year)

            # Hitung NILAI_KE_2
            nilai_ke_2 = self._calculate_daily_proportion(target_month, target_day, current_year)

            # Prediksi = NILAI_KE_1 × NILAI_KE_2 × (1 + Faktor_Sentimen)
            prediction = nilai_ke_1 * nilai_ke_2 * (1 + self.sentiment_factor)

            forecast_values.append(prediction)

        return forecast_values, future_business_dates
