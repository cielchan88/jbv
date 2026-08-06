# Supply Demand Valas (SDV) Dashboard

Dashboard prediksi Supply Demand Valas dengan integrasi ETL otomatis.

## 🚀 Fitur Utama

- **Auto ETL Integration**: Dashboard otomatis detect & run ETL saat ada data baru
- **Dual Version Output**:
  - **SIMPLE** (default): Kategori utama, sub-level collapsed
  - **FULL**: Lengkap dengan semua sub-kategori detail
- **5 Model Prediksi**: LightGBM, ARIMA, Random Forest, Prophet, XGBoost
- **Multi-page Dashboard**: Exploratory, Predictive, Evaluation, Worksheet, dll.

## 📁 Struktur Direktori

```
dashboard/
├── app.py                      # Main entry point
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker configuration
│
├── config/                     # Konfigurasi
│   ├── holidays.json           # Data hari libur
│   └── model_config.json       # Konfigurasi model
│
├── data/                       # Data files
│   ├── raw/                    # Data mentah
│   │   └── source-data.xlsx    # Input Excel
│   ├── processed/              # Data hasil ETL
│   │   ├── sdv-wide.csv        # Output SIMPLE (PRIMARY)
│   │   └── sdv-wide-full.csv   # Output FULL (detailed)
│   └── models/                 # Saved models (future)
│
├── etl/                        # ETL pipeline module
│   ├── __init__.py
│   └── pipeline.py             # ETL transformation logic
│
├── utils/                      # Helper functions
│   ├── __init__.py
│   ├── data_loader.py          # Auto ETL detection & loading
│   └── date_utils.py           # Date & holiday utilities
│
├── pages/                      # Streamlit pages
│   ├── 1_exploratory.py        # Analisis eksploratori
│   ├── 2_predictive.py         # Prediksi (single model)
│   ├── 3_predictive-new.py     # Prediksi (multi model)
│   ├── 4_evaluation.py         # Evaluasi & comparison
│   ├── 5_lembar_kerja.py       # Worksheet forecasting
│   └── 6_hari_libur.py         # Kelola hari libur
│
└── temp/                       # Temporary files
```

## 🔄 ETL Pipeline

### Input
- **File**: `data/raw/source-data.xlsx`
- **Sheets**: Korporasi, PTMN, Asing, Individu
- **Format**: Time series data transaksi valas

### Process
ETL pipeline berjalan **in-memory** tanpa intermediate files:
1. **Extract & Clean**: Read 4 Excel sheets, normalize columns
2. **Transform & Calculate**: Add derived columns (x48-x59)
3. **Tidy Transform**: Convert to long format
4. **Build Hierarchy**: Create 2 hierarchical structures (full & simple)
5. **Wide Format**: Pivot to wide format → Output 2 files

**No intermediate files saved** - hanya 2 output final.

### Output

#### 1. SIMPLE Version (`sdv-wide.csv`) - PRIMARY
Struktur simplified untuk dashboard utama:
- **24 rows** total
- Kategori utama saja
- Sub-level collapsed ke "Lainnya"
- Struktur:
  ```
  A. KORPORASI
     1. PTMN
        a. Impor
        b. Repatriasi
        c. Lainnya
     2. Korporasi Lainnya
        a. Ekspor
        b. Transaksi tanpa underlying
        c. Investasi
        d. Impor
        e. Repatriasi
        f. Lainnya
  B. INDIVIDU
     a. Ekspor
     b. Transaksi tanpa underlying
     c. Impor
     d. Lainnya
  C. NON RESIDEN
     a. Investasi
     b. Remittance
     c. Repatriasi
     d. Trading
     e. Lainnya
  D. NET SUPPLY DEMAND VALAS (A+B+C)
  ```

#### 2. FULL Version (`sdv-wide-full.csv`) - DETAILED
Struktur lengkap untuk analisis detail:
- **61 rows** total
- Semua sub-kategori detail
- Level 1-4 hierarchy

### Auto ETL Trigger

Dashboard otomatis menjalankan ETL jika:
- `source-data.xlsx` lebih baru dari `sdv-wide.csv`, ATAU
- `sdv-wide.csv` belum ada

Proses berjalan **silent** di background dengan notifikasi sukses/gagal.

### Manual ETL

Jika perlu run ETL manual:

```bash
python -m etl.pipeline
```

## 🛠️ Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup Data

Pastikan file `source-data.xlsx` ada di:
```
data/raw/source-data.xlsx
```

### 3. Run Dashboard

```bash
streamlit run app.py
```

Dashboard akan otomatis:
1. Check data freshness
2. Run ETL jika diperlukan
3. Load processed data
4. Ready untuk analisis & prediksi

## 📊 Penggunaan Dashboard

### 1. Exploratory (Page 1)
- Visualisasi NET SDV
- Decomposition (Trend, Seasonal, Residual)
- Eksplorasi hierarki data

### 2. Predictive (Page 2 & 3)
- **Page 2**: Single model prediction (ARIMA/XGBoost/Prophet)
- **Page 3**: Multi-model comparison (5 models)
- Pilih kategori → Pilih komponen → Forecast
- Confidence intervals & metrics

### 3. Evaluation (Page 4)
- Compare 5 models untuk semua leaf nodes
- Metrics: MAE, RMSE, MAPE, R², DA
- Simpan konfigurasi model terbaik

### 4. Worksheet (Page 5)
- Generate forecast untuk semua leaf nodes
- Mode: Custom (per-model) atau Single model
- Export hasil ke CSV

### 5. Hari Libur (Page 6)
- Kelola data hari libur
- Affect forecasting models

## 🔧 Configuration

### Holidays (`config/holidays.json`)
```json
[
  {
    "tanggal": "2025-01-01",
    "nama": "Tahun Baru",
    "kategori": "Nasional"
  }
]
```

### Model Config (`config/model_config.json`)
Konfigurasi model terbaik untuk setiap leaf node (dihasilkan dari Evaluation page).

## 📦 Docker Deployment

```bash
# Build image
docker build -t sdv-dashboard .

# Run container
docker run -p 8501:8501 sdv-dashboard
```

Access dashboard di: `http://localhost:8501`

## 🐛 Troubleshooting

### ETL Gagal
- Check file `source-data.xlsx` ada dan valid
- Check log error di console
- Pastikan semua sheets (Korporasi, PTMN, Asing, Individu) tersedia

### Import Error
- Pastikan berada di root directory dashboard
- Check Python path: `export PYTHONPATH="${PYTHONPATH}:$(pwd)"`

### Cache Issues
Jika data tidak update:
1. Clear Streamlit cache: `c` di terminal
2. Atau restart dashboard

## 📝 Notes

- **Primary Output**: `sdv-wide.csv` (SIMPLE version)
- **ETL Duration**: ~8-10 seconds
- **Auto-refresh**: ETL check setiap page load (cached 5 menit)
- **Date Range**: 2021-10-01 to latest (konfigurasi di `etl/pipeline.py`)

## 🤝 Contributors

Data Processing Team - DPMA

---

**Version**: 2.0
**Last Updated**: 2025-10-16
