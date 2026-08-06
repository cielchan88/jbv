# Changelog

Semua perubahan penting pada SDV Dashboard akan didokumentasikan di file ini.

Format berdasarkan [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
dan proyek ini mengikuti [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2025-11-24

### Ditambahkan
- **Manajemen Konfigurasi** ([config.py](config.py), [config.example.py](config.example.py))
  - API credentials dipindahkan ke `config.py` untuk keamanan lebih baik
  - Template `config.example.py` untuk setup user baru
  - Fallback mechanism jika `config.py` tidak ditemukan
  - Auto-import dari config dengan error handling

- **Enhanced Metadata Export** ([pages/6_Lembar_Kerja.py](pages/6_Lembar_Kerja.py), [pages/7_Adjustment.py](pages/7_Adjustment.py))
  - Sheet "Series Summary": Model yang digunakan per series dengan statistik
  - Sheet "Feature Details": SEMUA 25 fitur terpilih dengan skor korelasi Spearman
  - Tersedia di Lembar Kerja dan Adjustment
  - Traceability lengkap untuk audit dan debugging

- **Visualisasi UCL/LCL** ([pages/6_Lembar_Kerja.py:693-794](pages/6_Lembar_Kerja.py#L693-L794))
  - Plot interaktif Net Supply Demand Valas dengan confidence intervals
  - Gray train line, black recent historical, red dotted forecast
  - Blue CI band (95% confidence interval)
  - Statistik ringkasan: Last Historical, Average Forecast, Avg CI Width

- **External Features Tracking** ([data/external_features.xlsx](data/external_features.xlsx))
  - File sekarang tracked di git untuk reproducibility
  - Reference data untuk team collaboration
  - Memastikan konsistensi hasil forecasting

### Diubah
- **Confidence Interval Calculation** ([pages/6_Lembar_Kerja.py:467-539](pages/6_Lembar_Kerja.py#L467-L539))
  - **Sebelumnya**: Historical volatility (30-day std dengan cap 10%)
  - **Sekarang**: Residual-based approach untuk akurasi lebih baik
  - **ML Models**: In-sample residuals (fitted values) → std(residuals) × 1.96
  - **APUVA/Prophet/AutoARIMA**: Fallback ke historical volatility
  - Konsisten dengan [pages/4_Prediksi.py](pages/4_Prediksi.py) (residual-based)
  - Lebih akurat: Mengukur actual model error, bukan asumsi volatilitas

- **Unified Plot Styling** ([pages/6_Lembar_Kerja.py:719-792](pages/6_Lembar_Kerja.py#L719-L792))
  - Style konsisten dengan halaman Prediksi
  - Gray train line (width=1)
  - Black recent historical line (last 10 points, width=2)
  - Red dotted forecast line (dash='dot', width=2)
  - Blue CI band hanya di forecast period (rgba(68, 138, 255, 0.2))
  - Removed: UCL/LCL lines terpisah (lebih clean)

- **APUVA Data Handling** ([pages/5_Evaluasi.py](pages/5_Evaluasi.py), [pages/4_Prediksi.py](pages/4_Prediksi.py))
  - APUVA sekarang menggunakan FULL historical data (2006-2025)
  - Diperlukan untuk year-over-year calculations yang akurat
  - ML models tetap konsisten dengan 2019+ data (aligned dengan external features)
  - Filtering data di-apply di semua pages (Evaluasi, Prediksi, Lembar Kerja)

### Diperbaiki
- **Silent Fallback External Features** ([utils/external_loader.py:43-45](utils/external_loader.py#L43-L45))
  - Error handling yang lebih baik saat load external features
  - Silent fallback ke cross-series only jika external features gagal
  - Error message ditampilkan di higher level (tidak duplikat)

- **Feature Correlation Display** ([pages/4_Prediksi.py:237-248](pages/4_Prediksi.py#L237-L248))
  - Skor korelasi sekarang dihitung untuk SEMUA features (bukan hanya top 25)
  - Fixed bug: rank 26+ menampilkan skor 0
  - Menggunakan Spearman correlation untuk semua features sebelum selection

### Dihapus
- **Scraper Tab** ([pages/8_Scraper.py](pages/8_Scraper.py)) - REMOVED
  - Tab Scraper dihapus dari dashboard
  - Functionality tidak terintegrasi dengan workflow utama
  - Files masih tersedia di arsip jika diperlukan

- **Archived Scraper Files** (scraper-not-integrated/)
  - Notebooks: Trading_Economics_Auto_Complete.ipynb, Trading_Economics_Scraper_BERT.ipynb
  - Scripts: colab_scraper_sentiment.py, test_finbert_title.py, tradeEcoCSV.py, tradeEcoExcel.py
  - Data files: tradingeconomics_stream_ws.xlsx, tradingeconomics_stream_wsV1.xlsx
  - README: README_COLAB.md
  - Total: 1,759 lines removed untuk codebase yang lebih clean

### Keamanan
- **API Credentials Security** ([etl/api_client.py:36-72](etl/api_client.py#L36-L72))
  - Credentials dipindahkan dari hardcoded ke `config.py`
  - `config.py` ditambahkan ke [.gitignore:39](.gitignore#L39)
  - Mencegah credential leaks di version control
  - Template tersedia di `config.example.py` untuk setup

### Detail Teknis
- **Confidence Interval Formula**:
  - 95% CI = Forecast ± (1.96 × σ)
  - σ_ML = std(actual - fitted_values)  # In-sample residuals
  - σ_APUVA = std(historical_values) × 0.5  # Conservative estimate
  - σ_Prophet/AutoARIMA = std(historical_values) × 0.3

- **Gitignore Updates** ([.gitignore:19-21](.gitignore#L19-L21))
  - `data/forecast_versions/` - Auto-generated forecast outputs
  - `data/arsip/` - Archived data files
  - Catboost training logs tetap ignored

- **Plot Color Scheme**:
  - Historical: `gray` (width=1)
  - Recent: `black` (width=2)
  - Forecast: `red` dash='dot' (width=2)
  - CI band: `rgba(68, 138, 255, 0.2)`

### User Experience
- ✅ Confidence intervals lebih akurat (based on actual model error)
- ✅ Plot styling konsisten across pages
- ✅ API credentials terpisah dari code (easier setup)
- ✅ Enhanced metadata untuk full traceability
- ✅ Clean codebase (removed unused scraper files)

## [1.1.2] - 2025-11-21

### Diperbaiki
- **Undefined Variables in Prediksi Page** ([pages/4_Prediksi.py](pages/4_Prediksi.py))
  - Fix NameError: name 'dates' is not defined (line 675)
  - Fix NameError: name 'train' is not defined (line 318, 330)
  - Fix NameError: name 'test' is not defined (line 336, 364, 365)
  - AutoARIMA: Menggunakan train_ml dan test_ml yang sudah terdefinisi
  - Prophet: Menggunakan train_ml, test_ml, dan dates_ml yang sudah terdefinisi

### Detail Teknis
- Semua model ML (AutoARIMA, Prophet, XGBoost, RandomForest, LightGBM) sekarang konsisten menggunakan data 2019+ (`_ml` suffix)
- APUVA tetap menggunakan full historical data (2006-2025) dengan suffix `_apuva`
- Forecast dates generation sekarang menggunakan `dates_ml[-1]` untuk consistency

### User Experience
- Halaman Prediksi dapat berjalan tanpa error NameError
- Semua 6 model (APUVA, AutoARIMA, Prophet, RandomForest, LightGBM, XGBoost) dapat di-training dengan benar

## [1.1.1] - 2025-11-21

### Diperbaiki
- **Sheet Name Compatibility Fix** ([etl/load_external.py](etl/load_external.py))
  - Default sheet_name parameter menjadi None (auto-detect first sheet)
  - Menambahkan fallback logic jika sheet name tidak ditemukan
  - Fix error: "Worksheet named 'External_Features' not found"

- **Page Updates untuk Sheet Compatibility**
  - [pages/2_Fitur_Eksternal.py](pages/2_Fitur_Eksternal.py): Explicit sheet_name=None
  - [pages/3_Eksplorasi.py](pages/3_Eksplorasi.py): Remove hardcoded sheet_name parameter
  - [utils/external_loader.py](utils/external_loader.py): Explicit sheet_name=None

### Detail Teknis
- Loader sekarang bekerja dengan sheet name apapun (Sheet1, External_Features, dll)
- Tidak perlu rename sheet di Excel file
- Code-only fix: Excel file tetap as-is
- Backward compatible: Masih bisa specify sheet_name jika diperlukan

### User Experience
- No more sheet name errors saat load external features
- Excel file dari Colab bisa langsung digunakan tanpa rename sheet
- Flexibility: Sheet name apapun otomatis terdeteksi

## [1.1.0] - 2025-11-21

### Ditambahkan
- **Integrasi External Features Lengkap** ([utils/external_loader.py](utils/external_loader.py))
  - Centralized loader untuk external features dengan 10-min cache
  - Auto-merge dengan cross-series features
  - Adaptif: kolom baru di Excel otomatis terdeteksi dan digunakan
  - Integrasi di 3 halaman forecasting: Prediksi, Evaluasi, Lembar Kerja

- **Tab External Features di Eksplorasi** ([pages/3_Eksplorasi.py](pages/3_Eksplorasi.py))
  - Visualisasi time series (multi-select features)
  - Heatmap korelasi dengan kategori SDV (KORPORASI, INDIVIDU, NON RESIDEN, NET SDV)
  - Statistik ringkasan (Mean, Median, Std, Min, Max)
  - UI clean: Heatmap only untuk visual yang jelas

- **Complete Date Filling** ([data/external_features.xlsx](data/external_features.xlsx))
  - Missing dates (weekends/holidays) diisi dengan 0
  - Total rows: 1,888 → 2,467 (complete continuous date range)
  - News_Count = 0 dan Sentiment = 0.0 untuk missing dates
  - Model-ready: Tidak perlu forward fill, explicit 0 values

- **Colab Script Enhancement** ([scraper-not-integrated/colab_auto_complete.py](scraper-not-integrated/colab_auto_complete.py))
  - Auto-fill missing dates dengan 0 di output file
  - Fixed datetime parsing dengan format='mixed'
  - Output file langsung lengkap (no gaps)
  - Ready to copy-paste ke dashboard tanpa manual fixes

- **Test Script untuk FinBERT** ([scraper-not-integrated/test_finbert_title.py](scraper-not-integrated/test_finbert_title.py))
  - Test sentiment analysis pada TITLE ONLY
  - Validasi hasil FinBERT untuk financial news

### Diperbaiki
- **Datetime Parsing Error** ([scraper-not-integrated/colab_auto_complete.py](scraper-not-integrated/colab_auto_complete.py))
  - Fixed ValueError untuk datetime dengan/tanpa milliseconds
  - Menggunakan format='mixed' untuk handle berbagai format

### Detail Teknis
- Missing dates analysis: 97.6% adalah weekends (579 total missing dates)
- External features adaptif: tambah kolom ke Excel → auto-detected
- Cache TTL: 10 menit (balance antara freshness dan performance)
- Sentiment dari FinBERT (ProsusAI/finbert) - financial news sentiment
- Daily aggregation: News count + weighted sentiment average

### User Experience
- Complete date range: Tidak ada kebingungan tentang missing dates
- Visual correlation analysis: Mudah spot strong predictors
- Auto-integration: External features otomatis digunakan di forecasting
- Flexible: Tambah features baru ke Excel kapan saja (e.g., Bitcoin, Policy Rate)

## [1.0.1] - 2025-11-19

### Diperbaiki
- **Penanganan Duplikat Transaction Code dari API** ([etl/api_client.py](etl/api_client.py))
  - Memperbaiki error "cannot assemble with duplicate keys" saat transformasi data API
  - Menambahkan deteksi duplikat dengan warning log
  - Transaction code dengan nilai sama untuk tanggal yang sama otomatis dijumlahkan
  - Peningkatan error handling dan logging untuk kualitas data

### Diubah
- **Organisasi Test** ([tests/test_api_duplicate_fix.py](tests/test_api_duplicate_fix.py))
  - Memindahkan test duplicate handling ke folder `tests/` untuk organisasi lebih baik
  - Menambahkan skenario test komprehensif untuk edge cases

### Ditambahkan
- **Dokumentasi** ([docs/API_DUPLICATE_HANDLING.md](docs/API_DUPLICATE_HANDLING.md))
  - Dokumentasi detail untuk strategi penanganan duplikat API
  - Penjelasan rasional untuk penjumlahan duplicate transaction codes
  - Alternatif strategi dan panduan monitoring

## [1.0.0] - 2025-11-11

### Ditambahkan
- **Sistem Versioning Forecast** ([utils/forecast_version.py](utils/forecast_version.py))
  - Simpan forecast sebagai snapshot dengan metadata lengkap
  - Version ID: berbasis timestamp (YYYYMMDD_HHMMSS)
  - Storage: `data/forecast_versions/{version_id}/`
  - Metadata meliputi: model yang digunakan, parameter, features, timestamps

- **Adjustment Spesifik per Versi** ([pages/7_Adjustment.py](pages/7_Adjustment.py))
  - Adjustment disimpan per versi (adjustments_{version_id})
  - Setiap forecast versi independen
  - Tidak ada carry-over adjustment antar versi
  - Log adjustment disimpan ke Excel (3 sheets: Adjusted Forecast, Log, Metadata)

- **Integrasi Fitur Eksternal** ([etl/load_external.py](etl/load_external.py))
  - Load fitur eksternal dari Excel (`data/external_features.xlsx`)
  - Fitur: Sentiment, Oil Price, USD_IDR, Gold, US Treasury
  - Auto-generate lag features (1, 7, 14) dan rolling mean (7-day)
  - Integrasi dengan cross-series features
  - UI: Halaman Fitur Eksternal untuk monitoring

- **Peningkatan Download Excel**
  - Background merah (#FFCCCC) pada kolom forecast
  - Metadata sheet di semua download
  - Lembar Kerja: 2 sheets (Forecast + Metadata)
  - Adjustment: 3 sheets (Adjusted + Log + Metadata)

### Diubah
- **Reorganisasi Halaman**
  - Ditambahkan: [pages/2_Fitur_Eksternal.py](pages/2_Fitur_Eksternal.py) - Monitoring fitur eksternal
  - Direname: pages/2_Eksplorasi.py → pages/3_Eksplorasi.py
  - Direname: pages/3_Prediksi.py → pages/4_Prediksi.py
  - Direname: pages/4_Evaluasi.py → pages/5_Evaluasi.py
  - Dihapus: pages/5_Lembar_Kerja.py (diganti dengan 6_Lembar_Kerja.py)
  - Direname: pages/6_Hari_Libur.py → pages/7_Hari_Libur.py

### Detail Teknis
- Isolasi versi: adjustment tidak carry over
- Pelacakan metadata: audit trail lengkap untuk compliance
- Format openpyxl: background merah pada kolom forecast
- Cross-series: top 30 correlated series (konsisten)
- Business date generation: skip weekends & holidays

---

## Catatan Rilis

### Fokus Versi 1.0.1
Ini adalah **bug fix release** yang mengatasi masalah sinkronisasi data API:
- Peningkatan robustness transformasi data API
- Deteksi error dan logging yang lebih baik
- Dokumentasi yang diperkaya untuk troubleshooting

### Fokus Versi 1.0.0
Initial production release dengan:
- Sistem versioning forecast lengkap untuk audit compliance
- Dukungan fitur eksternal untuk modeling advanced
- Peningkatan user experience dengan download Excel

---

## Kontributor

- **Tim APUVA** - Bank Indonesia
