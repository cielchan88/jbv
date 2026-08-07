"""
JSON Loader for API Sample Data
================================

Module untuk load data dari JSON sample files (offline mode).
Digunakan untuk development tanpa perlu koneksi ke API BI.

Author: Data Processing Team
Date: 2025-12-12
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# MAPPING: Transaction Code -> Excel Column Number
# ============================================================================
# Source: ETL header mapping dari source-data.xlsx
# Column 1 = date, Column 2 = blank, Column 3-42 = transaction data, Column 43 = total
CODE_TO_COLUMN = {
    31: 3,   # biaya administrasi
    30: 4,   # biaya overhead
    13: 5,   # Biaya Pendidikan
    14: 6,   # Biaya Perjalanan Luar Negeri
    36: 7,   # biaya remunerasi pegawai
    5: 8,    # Impor
    4: 9,    # Pembayaran Pinjaman LN
    3: 10,   # Penerimaan Pinjaman LN
    6: 11,   # Penjualan Devisa Hasil Ekspor
    22: 12,  # Dana Hasil Penjualan
    24: 13,  # Untuk disimpan pada rekening valas DN
    9: 14,   # Investasi Pembelian Obligasi Korporasi
    8: 15,   # Investasi Pembelian SBN
    7: 16,   # Investasi Pembelian Saham
    11: 17,  # Investasi Pembelian SBI
    1: 18,   # Investasi Pemberian Kredit
    0: 19,   # Investasi Penyertaan Langsung
    32: 20,  # kegiatan Pedagang Valuta Asing (PVA)
    28: 21,  # kegiatan remittance
    34: 22,  # pembayaran hutang
    33: 23,  # pembayaran pajak
    37: 24,  # pembelian barang
    39: 25,  # pembelian jasa
    35: 26,  # penambahan modal kerja
    41: 27,  # pencairan bunga/pokok dari penempatan valas DN
    38: 28,  # penjualan barang
    40: 29,  # penjualan jasa
    19: 30,  # Repatriasi dana hasil penjualan saham
    18: 31,  # Repatriasi dana pemberian kredit
    21: 32,  # Repatriasi dana penjualan obligasi korporat
    20: 33,  # Repatriasi dana penjualan SBN
    17: 34,  # Repatriasi dana penyertaan langsung
    23: 35,  # Repatriasi dividen dan kupon
    42: 36,  # repatriasi atas penghasilan dari jasa
    16: 37,  # Sosial (Konversi hasil sumbangan/grant)
    27: 38,  # transaksi antarbank cover posisi Bank ke LN
    26: 39,  # transaksi antarbank cover posisi nasabah ke DN
    25: 40,  # transaksi antarbank trading
    29: 41,  # transaksi valuta asing tanpa underlying
    43: 42,  # Lindung nilai atas kepemilikan valuta asing
}

# Mapping endpoint key to JSON filename
JSON_SAMPLE_FILES = {
    'korporasi': 'TTS_SDV_KORPORASI.json',
    'ptmn': 'TTS_SDV_PERTAMINA.json',
    'asing': 'TTS_PEL_LN_VS_LWN_DN_BANK.json',
    'individu': 'TTS_PEL_INDIV_DN_VS_LWN_BANK_DN.json'
}

# Default sample directory
DEFAULT_SAMPLE_DIR = Path('data/api_sample')


def load_json_sample(endpoint_key: str, sample_dir: Path = None) -> pd.DataFrame:
    """
    Load data dari JSON sample file (format LONG).

    Args:
        endpoint_key: Key untuk endpoint ('korporasi', 'ptmn', 'asing', 'individu')
        sample_dir: Directory tempat JSON sample disimpan (default: data/api_sample)

    Returns:
        DataFrame dengan kolom: TANGGAL_LAPORAN, TUJUAN_TRANSAKSI, VOLUME_NETT_RIBU_USD

    Raises:
        FileNotFoundError: Jika file JSON tidak ditemukan
        ValueError: Jika endpoint_key tidak valid atau JSON format salah
    """
    if endpoint_key not in JSON_SAMPLE_FILES:
        raise ValueError(f"Invalid endpoint key: {endpoint_key}. Must be one of {list(JSON_SAMPLE_FILES.keys())}")

    # Determine sample directory
    if sample_dir is None:
        sample_dir = DEFAULT_SAMPLE_DIR

    json_file = sample_dir / JSON_SAMPLE_FILES[endpoint_key]

    if not json_file.exists():
        raise FileNotFoundError(f"JSON sample not found: {json_file}")

    logger.info(f"Loading JSON sample: {json_file}")

    try:
        # Load JSON
        with open(json_file, 'r') as f:
            data = json.load(f)

        # Convert to DataFrame
        df = pd.DataFrame(data)

        # Validate required columns
        required_cols = ['TANGGAL_LAPORAN', 'TUJUAN_TRANSAKSI', 'VOLUME_NETT_RIBU_USD']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns in JSON: {missing_cols}")

        # Convert data types
        df['TANGGAL_LAPORAN'] = pd.to_datetime(df['TANGGAL_LAPORAN'])
        df['VOLUME_NETT_RIBU_USD'] = pd.to_numeric(df['VOLUME_NETT_RIBU_USD'], errors='coerce')

        logger.info(f"✓ Loaded {len(df)} records from JSON sample")
        logger.info(f"  Date: {df['TANGGAL_LAPORAN'].iloc[0]}")
        logger.info(f"  Categories: {df['TUJUAN_TRANSAKSI'].nunique()}")

        return df

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format in {json_file}: {e}")
    except Exception as e:
        raise ValueError(f"Error loading JSON sample: {e}")


def transform_json_to_wide(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform JSON data dari format LONG ke WIDE (matching Excel format).

    Excel Format:
        Column 1 = TANGGAL_LAPORAN (date)
        Column 2 = (blank/unused)
        Column 3-42 = Transaction data (mapped via CODE_TO_COLUMN)
        Column 43 = Total
        Column 44-47 = Calculated columns (will be filled by ETL pipeline)

    Mapping menggunakan CODE_TO_COLUMN dictionary yang sudah didefinisikan.

    Args:
        df: DataFrame dari load_json_sample() dalam format LONG

    Returns:
        DataFrame dalam format WIDE dengan kolom numeric 1-47
    """
    if len(df) == 0:
        logger.warning("Empty DataFrame - no data to transform")
        return pd.DataFrame()

    # Extract transaction code from TUJUAN_TRANSAKSI
    df = df.copy()
    df['transaction_code'] = df['TUJUAN_TRANSAKSI'].str.extract(r'^(\d+)')[0].astype(int)

    # Check for duplicates
    duplicates = df.groupby(['TANGGAL_LAPORAN', 'transaction_code']).size()
    duplicates = duplicates[duplicates > 1]

    if not duplicates.empty:
        logger.warning(f"Found {len(duplicates)} duplicate transaction codes - summing values")

    # Group by date and transaction code (sum duplicates)
    df_grouped = df.groupby(['TANGGAL_LAPORAN', 'transaction_code'], as_index=False).agg({
        'VOLUME_NETT_RIBU_USD': 'sum'
    })

    # Pivot to wide format
    df_wide = df_grouped.pivot_table(
        index='TANGGAL_LAPORAN',
        columns='transaction_code',
        values='VOLUME_NETT_RIBU_USD',
        aggfunc='sum',
        fill_value=0
    ).reset_index()

    # Create result DataFrame dengan struktur Excel yang benar
    result = pd.DataFrame()
    result[1] = df_wide['TANGGAL_LAPORAN']  # Column 1 = date

    # Initialize all columns 2-47 dengan 0
    for col_num in range(2, 48):
        result[col_num] = 0.0

    # Map transaction codes ke Excel columns menggunakan CODE_TO_COLUMN
    for code, col_num in CODE_TO_COLUMN.items():
        if code in df_wide.columns:
            result[col_num] = df_wide[code].values
            logger.debug(f"Mapped code {code:02d} -> column {col_num}")

    # Column 43 = Total (sum of columns 3-42)
    result[43] = result.loc[:, 3:42].sum(axis=1)

    # Convert date column to datetime
    result[1] = pd.to_datetime(result[1])

    logger.info(f"✓ Transformed to wide format: {result.shape}")
    logger.info(f"  Date: {result[1].iloc[0]}")
    logger.info(f"  Total (column 43): {result[43].iloc[0]:.2f}")

    return result


def load_all_json_samples(sample_dir: Path = None) -> dict:
    """
    Load semua JSON samples dan transform ke format WIDE.

    Args:
        sample_dir: Directory tempat JSON samples disimpan

    Returns:
        Dictionary dengan key: endpoint name, value: DataFrame (wide format)
    """
    results = {}

    for endpoint_key in JSON_SAMPLE_FILES.keys():
        try:
            logger.info(f"\n{'='*70}")
            logger.info(f"Loading {endpoint_key.upper()} from JSON")
            logger.info(f"{'='*70}")

            # Load JSON data
            df_long = load_json_sample(endpoint_key, sample_dir)

            # Transform to wide format
            df_wide = transform_json_to_wide(df_long)

            results[endpoint_key] = df_wide

            logger.info(f"✓ {endpoint_key.upper()} completed\n")

        except Exception as e:
            logger.error(f"✗ Failed to load {endpoint_key}: {e}\n")
            results[endpoint_key] = None

    return results


if __name__ == "__main__":
    # Test script
    import sys
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*70)
    print("JSON LOADER TEST")
    print("="*70 + "\n")

    # Test loading one endpoint
    print("Testing Korporasi endpoint...")
    try:
        df_long = load_json_sample('korporasi')
        print(f"✓ Loaded LONG format: {df_long.shape}")
        print(df_long.head())

        df_wide = transform_json_to_wide(df_long)
        print(f"\n✓ Transformed to WIDE format: {df_wide.shape}")
        print(df_wide)

        # Compare with Excel
        print("\n" + "="*70)
        print("COMPARING WITH EXCEL")
        print("="*70)

        df_excel = pd.read_excel('arsip/source-data.xlsx', sheet_name='Korporasi', nrows=3)
        print(f"\nExcel structure: {df_excel.shape}")
        print(f"Excel columns: {list(df_excel.columns)}")
        print(f"\nJSON structure: {df_wide.shape}")
        print(f"JSON columns: {list(df_wide.columns)}")

        if list(df_wide.columns) == list(df_excel.columns):
            print("\n✅ COLUMNS MATCH!")
        else:
            print("\n❌ COLUMNS DON'T MATCH")
            print(f"Difference: {set(df_excel.columns) - set(df_wide.columns)}")

        # Save to Excel for visual inspection
        output_file = Path('output') / f'test_json_loader_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        output_file.parent.mkdir(exist_ok=True)
        df_wide.to_excel(output_file, index=False)
        print(f"\n✓ Test output saved to: {output_file}")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
