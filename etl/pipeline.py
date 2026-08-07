"""
ETL Pipeline untuk Supply Demand Valas (SDV)
==============================================

Pipeline ini mentransformasi data transaksi valas dari Excel ke format wide CSV
untuk keperluan dashboard dan analisis.

Input:  source-data.xlsx (4 sheets: Korporasi, PTMN, Asing, Individu)
Output: sdv-wide.csv (62 rows × 1000+ date columns)

Flow:
1. Extract & Clean (001.r equivalent)
   - Read Excel sheets
   - Rename columns to x1, x2, ..., x47
   - Convert types & handle missing values

2. Transform & Calculate (002.r equivalent)
   - Add calculated columns x48-x59
   - Aggregate by transaction types

3. Build Hierarchy (003.r step 2-3)
   - Create hierarchical structure (Level 1-4)
   - Calculate parent-child relationships

4. Wide Format (003.r step 4)
   - Pivot dates to columns
   - Generate final wide format

Author: Data Processing Team
Date: 2024
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import logging
from typing import Dict, List, Tuple

# ============================================================================
# CONFIGURATION
# ============================================================================

# File paths (relative to project root)
BASE_DIR = Path(__file__).parent.parent
SOURCE_FILE = BASE_DIR / "data" / "raw" / "source-data.xlsx"
OUTPUT_FILE_FULL = BASE_DIR / "data" / "processed" / "sdv-wide-full.csv"
OUTPUT_FILE_SIMPLE = BASE_DIR / "data" / "processed" / "sdv-wide.csv"  # Default/Primary

# Date range untuk filtering
# NOTE: START_DATE set to 2019-01-01 untuk support APUVA model (butuh year-6 sampai year-2)
START_DATE = "2019-01-01"
# CUTOFF_DATE removed - will process all available data

# Sheet names yang akan diproses
SHEET_NAMES = ["Korporasi", "PTMN", "Asing", "Individu"]

# Mapping kolom kalkulasi ke nama jenis transaksi
TRANSACTION_MAP = {
    "x49": "Ekspor",
    "x50": "Impor",
    "x51": "Tarik_ULN",
    "x52": "Bayar_ULN",
    "x53": "Investasi",
    "x54": "Repatriasi",
    "x55": "Remittance",
    "x56": "Trading",
    "x57": "Transaksi_Tanpa_Underlying",
    "x58": "Lainnya"
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============================================================================
# STEP 1: EXTRACT & CLEAN (001.r equivalent)
# ============================================================================

def extract_and_clean() -> Dict[str, pd.DataFrame]:
    """
    Membaca data dari Excel dan melakukan cleaning dasar.

    Proses:
    - Read 4 sheets dari source Excel
    - Rename kolom menjadi x1, x2, ..., x47
    - Konversi x1 ke datetime
    - Konversi x2-x47 ke numeric
    - Replace NA dengan 0
    - Round ke 2 desimal

    Returns:
        Dict dengan key: nama sheet (lowercase), value: DataFrame
    """
    logger.info("=" * 70)
    logger.info("STEP 1: EXTRACT & CLEAN")
    logger.info("=" * 70)

    result = {}

    for sheet_name in SHEET_NAMES:
        logger.info(f"Processing sheet: {sheet_name}")

        # Read Excel sheet
        df_raw = pd.read_excel(SOURCE_FILE, sheet_name=sheet_name)

        # Rename columns to x1, x2, x3, ..., x47
        num_cols = len(df_raw.columns)
        df_raw.columns = [f"x{i+1}" for i in range(num_cols)]

        # Convert x1 to datetime
        df_raw['x1'] = pd.to_datetime(df_raw['x1'], errors='coerce')

        # Convert x2-x47 to numeric
        numeric_cols = [col for col in df_raw.columns if col != 'x1']
        for col in numeric_cols:
            df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce')

        # Replace NA with 0
        df_raw = df_raw.fillna(0)

        # Round numeric columns to 0 decimal places (integers)
        df_raw[numeric_cols] = df_raw[numeric_cols].round(0)

        # Store in result dict
        result[sheet_name.lower()] = df_raw

    logger.info(f"Step 1 completed: {len(result)} sheets processed\n")
    return result


# ============================================================================
# STEP 2: TRANSFORM & CALCULATE (002.r equivalent)
# ============================================================================

def transform_and_calculate(data_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Menambahkan kolom kalkulasi x48-x59 untuk setiap entitas.

    Kolom kalkulasi:
    - x48: Selisih total (verification)
    - x49: Ekspor (negative values dari kolom tertentu)
    - x50: Impor (positive values dari kolom tertentu)
    - x51: Tarik ULN
    - x52: Bayar ULN
    - x53: Investasi
    - x54: Repatriasi
    - x55: Remittance
    - x56: Trading
    - x57: Transaksi Tanpa Underlying
    - x58: Lainnya
    - x59: Net verification check

    Args:
        data_dict: Dictionary dari extract_and_clean()

    Returns:
        Dict dengan key: nama sheet (lowercase), value: DataFrame dengan kolom x1-x59
    """
    logger.info("=" * 70)
    logger.info("STEP 2: TRANSFORM & CALCULATE")
    logger.info("=" * 70)

    result = {}

    for sheet_name, df in data_dict.items():
        logger.info(f"Processing: {sheet_name}")

        # Create a copy to avoid modifying original
        df_calc = df.copy()

        # x48: Selisih total = x43 - sum(x3:x42)
        # Ini adalah verification bahwa total transaksi konsisten
        cols_to_sum = [f"x{i}" for i in range(3, 43)]  # x3 to x42
        df_calc['x48'] = df_calc['x43'] - df_calc[cols_to_sum].sum(axis=1)

        # x49: Ekspor (nilai negatif = supply/jual valas)
        # Kolom yang termasuk ekspor: x8, x11, x22, x24, x25, x28, x29, x46
        ekspor_cols = ['x8', 'x11', 'x22', 'x24', 'x25', 'x28', 'x29', 'x46']
        df_calc['x49'] = sum([df_calc[col].apply(lambda x: x if x < 0 else 0) for col in ekspor_cols])

        # x50: Impor (nilai positif = demand/beli valas)
        # Kolom yang sama dengan ekspor, tapi ambil nilai positif
        df_calc['x50'] = sum([df_calc[col].apply(lambda x: x if x > 0 else 0) for col in ekspor_cols])

        # x51: Tarik ULN (negative dari x9, x10)
        uln_tarik_cols = ['x9', 'x10']
        df_calc['x51'] = sum([df_calc[col].apply(lambda x: x if x < 0 else 0) for col in uln_tarik_cols])

        # x52: Bayar ULN (positive dari x9, x10)
        df_calc['x52'] = sum([df_calc[col].apply(lambda x: x if x > 0 else 0) for col in uln_tarik_cols])

        # x53: Investasi (negative dari berbagai kolom investasi)
        investasi_cols = ['x12', 'x14', 'x15', 'x16', 'x17', 'x18', 'x19',
                          'x30', 'x31', 'x32', 'x33', 'x34', 'x35', 'x36', 'x44']
        df_calc['x53'] = sum([df_calc[col].apply(lambda x: x if x < 0 else 0) for col in investasi_cols])

        # x54: Repatriasi (positive dari kolom investasi yang sama)
        df_calc['x54'] = sum([df_calc[col].apply(lambda x: x if x > 0 else 0) for col in investasi_cols])

        # x55: Remittance (x20 + x21)
        df_calc['x55'] = df_calc['x20'] + df_calc['x21']

        # x56: Trading (x38 + x39 + x40 + x47)
        df_calc['x56'] = df_calc['x38'] + df_calc['x39'] + df_calc['x40'] + df_calc['x47']

        # x57: Transaksi Tanpa Underlying (x41)
        df_calc['x57'] = df_calc['x41']

        # x58: Lainnya (kolom-kolom yang tidak termasuk kategori di atas)
        lainnya_cols = ['x2', 'x3', 'x4', 'x5', 'x6', 'x7', 'x13',
                        'x23', 'x26', 'x27', 'x37', 'x42', 'x45']
        df_calc['x58'] = df_calc[lainnya_cols].sum(axis=1)

        # x59: Net verification = sum(x49:x58) - x43
        # Harus mendekati 0 jika kalkulasi benar
        calc_cols = [f"x{i}" for i in range(49, 59)]
        df_calc['x59'] = df_calc[calc_cols].sum(axis=1) - df_calc['x43']

        # Round kolom kalkulasi ke 0 desimal (integers)
        calc_cols_with_48 = [f"x{i}" for i in range(48, 60)]
        df_calc[calc_cols_with_48] = df_calc[calc_cols_with_48].round(0)

        # Store in result dict
        result[sheet_name] = df_calc

    logger.info(f"Step 2 completed: {len(result)} sheets processed\n")
    return result


# ============================================================================
# STEP 3: BUILD HIERARCHY (003.r step 2-3)
# ============================================================================

def tidy_transform(data_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Transformasi ke format tidy (long format).

    Proses:
    - Filter berdasarkan date range
    - Pivot kolom x49-x58 menjadi rows
    - Add metadata: Jenis_Transaksi, Entitas
    - Convert to thousands (divide by 1000)

    Args:
        data_dict: Dictionary hasil transform_and_calculate()

    Returns:
        Dict dengan key: nama entitas, value: DataFrame tidy format
    """
    logger.info("=" * 70)
    logger.info("STEP 3A: TIDY TRANSFORMATION")
    logger.info("=" * 70)

    result = {}
    start_dt = pd.to_datetime(START_DATE)

    for entitas_name, df in data_dict.items():
        logger.info(f"Processing: {entitas_name}")

        # Filter by start date only (no cutoff - process all available data)
        df_filtered = df[df['x1'] >= start_dt].copy()

        # Select only date and calculated columns (x49-x58)
        cols_to_pivot = ['x1'] + [f"x{i}" for i in range(49, 59)]
        df_selected = df_filtered[cols_to_pivot].copy()
        df_selected.rename(columns={'x1': 'Tanggal'}, inplace=True)

        # Pivot longer: kolom x49-x58 menjadi rows
        df_tidy = df_selected.melt(
            id_vars=['Tanggal'],
            value_vars=[f"x{i}" for i in range(49, 59)],
            var_name='Jenis_Transaksi',
            value_name='Nilai_Ribu_USD'
        )

        # Map kolom ke nama transaksi yang readable
        df_tidy['Jenis_Transaksi'] = df_tidy['Jenis_Transaksi'].map(TRANSACTION_MAP)

        # Convert to thousands (bagi 1000)
        df_tidy['Nilai_Ribu_USD'] = (df_tidy['Nilai_Ribu_USD'] / 1000).round(0)

        # Add entitas column
        df_tidy['Entitas'] = entitas_name.upper()

        # Reorder columns
        df_tidy = df_tidy[['Tanggal', 'Jenis_Transaksi', 'Nilai_Ribu_USD', 'Entitas']]

        result[entitas_name] = df_tidy

    logger.info(f"Step 3A completed: {len(result)} datasets transformed\n")
    return result


def build_hierarchical(tidy_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Membangun struktur hierarki untuk dashboard.

    Struktur Hierarki:
    Level 1: A (Korporasi), B (Individu), C (Non Residen), D (Net Total)
    Level 2: Sub-kategori utama (PTMN, Korporasi Lainnya, dll)
    Level 3: Detail transaksi
    Level 4: Sub-detail transaksi

    Args:
        tidy_dict: Dictionary hasil tidy_transform()

    Returns:
        DataFrame dengan struktur hierarki (long format)
    """
    logger.info("=" * 70)
    logger.info("STEP 3B: BUILD HIERARCHICAL STRUCTURE (FULL)")
    logger.info("=" * 70)

    # Get all unique dates (sorted)
    all_dates = sorted(tidy_dict['korporasi']['Tanggal'].unique())
    logger.info(f"Processing {len(all_dates)} unique dates from {all_dates[0]} to {all_dates[-1]}")

    # Helper function untuk membuat row
    def create_row(tanggal, row_id, row_label, level, parent_id, nilai, is_calc, calc_type):
        """Helper untuk membuat satu baris data hierarki"""
        return {
            'Tanggal': tanggal,
            'Row_ID': row_id,
            'Row_Label': row_label,
            'Level': level,
            'Parent_ID': parent_id,
            'Nilai_Ribu_USD': round(nilai, 0),
            'Is_Calculated': is_calc,
            'Calculation_Type': calc_type
        }

    # Process setiap tanggal
    all_rows = []

    for tgl in all_dates:
        # Filter data untuk tanggal ini
        korp = tidy_dict['korporasi'][tidy_dict['korporasi']['Tanggal'] == tgl]
        ptmn = tidy_dict['ptmn'][tidy_dict['ptmn']['Tanggal'] == tgl]
        indv = tidy_dict['individu'][tidy_dict['individu']['Tanggal'] == tgl]
        asin = tidy_dict['asing'][tidy_dict['asing']['Tanggal'] == tgl]

        # Convert to dict untuk akses mudah: {Jenis_Transaksi: Nilai}
        korp_values = dict(zip(korp['Jenis_Transaksi'], korp['Nilai_Ribu_USD']))
        ptmn_values = dict(zip(ptmn['Jenis_Transaksi'], ptmn['Nilai_Ribu_USD']))
        indv_values = dict(zip(indv['Jenis_Transaksi'], indv['Nilai_Ribu_USD']))
        asin_values = dict(zip(asin['Jenis_Transaksi'], asin['Nilai_Ribu_USD']))

        # ====================================================================
        # A. KORPORASI (Level 1)
        # ====================================================================

        # A.0. KORPORASI - Data mentah dari sheet Korporasi (Level 2)
        korp_total = sum(korp_values.values())

        all_rows.append(create_row(tgl, "A.0", "KORPORASI", 2, "A", korp_total, True, "sum_children"))
        all_rows.append(create_row(tgl, "A.0.a", "a. Ekspor", 3, "A.0", korp_values.get("Ekspor", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.0.b", "b. Impor", 3, "A.0", korp_values.get("Impor", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.0.c", "c. Tarik ULN", 3, "A.0", korp_values.get("Tarik_ULN", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.0.d", "d. Bayar ULN", 3, "A.0", korp_values.get("Bayar_ULN", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.0.e", "e. Investasi", 3, "A.0", korp_values.get("Investasi", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.0.f", "f. Repatriasi", 3, "A.0", korp_values.get("Repatriasi", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.0.g", "g. Remittance", 3, "A.0", korp_values.get("Remittance", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.0.h", "h. Trading", 3, "A.0", korp_values.get("Trading", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.0.i", "i. Transaksi tanpa underlying", 3, "A.0", korp_values.get("Transaksi_Tanpa_Underlying", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.0.j", "j. Lainnya", 3, "A.0", korp_values.get("Lainnya", 0), False, "source"))

        # A.1. PTMN (Level 2)
        # PTMN fokus pada Impor, Repatriasi, dan Lainnya
        ptmn_lainnya = sum([
            ptmn_values.get("Ekspor", 0),
            ptmn_values.get("Tarik_ULN", 0),
            ptmn_values.get("Bayar_ULN", 0),
            ptmn_values.get("Investasi", 0),
            ptmn_values.get("Remittance", 0),
            ptmn_values.get("Trading", 0),
            ptmn_values.get("Transaksi_Tanpa_Underlying", 0),
            ptmn_values.get("Lainnya", 0)
        ])
        ptmn_total = ptmn_values.get("Impor", 0) + ptmn_values.get("Repatriasi", 0) + ptmn_lainnya

        all_rows.append(create_row(tgl, "A.1", "1. PTMN", 2, "A", ptmn_total, True, "sum_children"))
        all_rows.append(create_row(tgl, "A.1.a", "a. Impor", 3, "A.1", ptmn_values.get("Impor", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.1.b", "b. Repatriasi", 3, "A.1", ptmn_values.get("Repatriasi", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.1.c", "c. Lainnya", 3, "A.1", ptmn_lainnya, True, "sum_children"))
        all_rows.append(create_row(tgl, "A.1.c.1", "1-Ekspor", 4, "A.1.c", ptmn_values.get("Ekspor", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.1.c.2", "2-Tarik ULN", 4, "A.1.c", ptmn_values.get("Tarik_ULN", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.1.c.3", "3-Bayar ULN", 4, "A.1.c", ptmn_values.get("Bayar_ULN", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.1.c.4", "4-Investasi", 4, "A.1.c", ptmn_values.get("Investasi", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.1.c.5", "5-Remittance", 4, "A.1.c", ptmn_values.get("Remittance", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.1.c.6", "6-Trading", 4, "A.1.c", ptmn_values.get("Trading", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.1.c.7", "7-Transaksi tanpa underlying", 4, "A.1.c", ptmn_values.get("Transaksi_Tanpa_Underlying", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.1.c.8", "8-Lainnya", 4, "A.1.c", ptmn_values.get("Lainnya", 0), False, "source"))

        # A.2. Korporasi Lainnya (Level 2) - Selisih antara Korporasi dan PTMN
        korp_lain_ekspor = korp_values.get("Ekspor", 0) - ptmn_values.get("Ekspor", 0)
        korp_lain_nonund = korp_values.get("Transaksi_Tanpa_Underlying", 0) - ptmn_values.get("Transaksi_Tanpa_Underlying", 0)
        korp_lain_investasi = korp_values.get("Investasi", 0) - ptmn_values.get("Investasi", 0)
        korp_lain_impor = korp_values.get("Impor", 0) - ptmn_values.get("Impor", 0)
        korp_lain_repatriasi = korp_values.get("Repatriasi", 0) - ptmn_values.get("Repatriasi", 0)

        korp_lain_tarik_uln = korp_values.get("Tarik_ULN", 0) - ptmn_values.get("Tarik_ULN", 0)
        korp_lain_bayar_uln = korp_values.get("Bayar_ULN", 0) - ptmn_values.get("Bayar_ULN", 0)
        korp_lain_remittance = korp_values.get("Remittance", 0) - ptmn_values.get("Remittance", 0)
        korp_lain_trading = korp_values.get("Trading", 0) - ptmn_values.get("Trading", 0)
        korp_lain_lainnya_val = korp_values.get("Lainnya", 0) - ptmn_values.get("Lainnya", 0)

        korp_lain_lainnya = korp_lain_tarik_uln + korp_lain_bayar_uln + korp_lain_remittance + korp_lain_trading + korp_lain_lainnya_val
        korp_lain_total = korp_lain_ekspor + korp_lain_nonund + korp_lain_investasi + korp_lain_impor + korp_lain_repatriasi + korp_lain_lainnya

        all_rows.append(create_row(tgl, "A.2", "2. Korporasi Lainnya", 2, "A", korp_lain_total, True, "sum_children"))
        all_rows.append(create_row(tgl, "A.2.a", "a. Ekspor", 3, "A.2", korp_lain_ekspor, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.b", "b. Transaksi tanpa underlying", 3, "A.2", korp_lain_nonund, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.c", "c. Investasi", 3, "A.2", korp_lain_investasi, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.d", "d. Impor", 3, "A.2", korp_lain_impor, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.e", "e. Repatriasi", 3, "A.2", korp_lain_repatriasi, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.f", "f. Lainnya", 3, "A.2", korp_lain_lainnya, True, "sum_children"))
        all_rows.append(create_row(tgl, "A.2.f.1", "1-Tarik ULN", 4, "A.2.f", korp_lain_tarik_uln, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.f.2", "2-Bayar ULN", 4, "A.2.f", korp_lain_bayar_uln, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.f.3", "3-Remittance", 4, "A.2.f", korp_lain_remittance, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.f.4", "4-Trading", 4, "A.2.f", korp_lain_trading, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.f.5", "5-Lainnya", 4, "A.2.f", korp_lain_lainnya_val, True, "difference"))

        # A. KORPORASI Total (Level 1)
        korp_level1_total = ptmn_total + korp_lain_total
        all_rows.append(create_row(tgl, "A", "A. KORPORASI", 1, None, korp_level1_total, True, "sum_children"))

        # ====================================================================
        # B. INDIVIDU (Level 1)
        # ====================================================================

        indv_lainnya = sum([
            indv_values.get("Tarik_ULN", 0),
            indv_values.get("Bayar_ULN", 0),
            indv_values.get("Investasi", 0),
            indv_values.get("Repatriasi", 0),
            indv_values.get("Remittance", 0),
            indv_values.get("Trading", 0),
            indv_values.get("Lainnya", 0)
        ])
        indv_total = indv_values.get("Ekspor", 0) + indv_values.get("Transaksi_Tanpa_Underlying", 0) + indv_values.get("Impor", 0) + indv_lainnya

        all_rows.append(create_row(tgl, "B", "B. INDIVIDU", 1, None, indv_total, True, "sum_children"))
        all_rows.append(create_row(tgl, "B.a", "a. Ekspor", 2, "B", indv_values.get("Ekspor", 0), False, "source"))
        all_rows.append(create_row(tgl, "B.b", "b. Transaksi tanpa underlying", 2, "B", indv_values.get("Transaksi_Tanpa_Underlying", 0), False, "source"))
        all_rows.append(create_row(tgl, "B.c", "c. Impor", 2, "B", indv_values.get("Impor", 0), False, "source"))
        all_rows.append(create_row(tgl, "B.d", "d. Lainnya", 2, "B", indv_lainnya, True, "sum_children"))
        all_rows.append(create_row(tgl, "B.d.1", "1-Tarik ULN", 3, "B.d", indv_values.get("Tarik_ULN", 0), False, "source"))
        all_rows.append(create_row(tgl, "B.d.2", "2-Bayar ULN", 3, "B.d", indv_values.get("Bayar_ULN", 0), False, "source"))
        all_rows.append(create_row(tgl, "B.d.3", "3-Investasi", 3, "B.d", indv_values.get("Investasi", 0), False, "source"))
        all_rows.append(create_row(tgl, "B.d.4", "4-Repatriasi", 3, "B.d", indv_values.get("Repatriasi", 0), False, "source"))
        all_rows.append(create_row(tgl, "B.d.5", "5-Remittance", 3, "B.d", indv_values.get("Remittance", 0), False, "source"))
        all_rows.append(create_row(tgl, "B.d.6", "6-Trading", 3, "B.d", indv_values.get("Trading", 0), False, "source"))
        all_rows.append(create_row(tgl, "B.d.7", "7-Lainnya", 3, "B.d", indv_values.get("Lainnya", 0), False, "source"))

        # ====================================================================
        # C. NON RESIDEN (Level 1)
        # ====================================================================

        asin_lainnya = sum([
            asin_values.get("Ekspor", 0),
            asin_values.get("Impor", 0),
            asin_values.get("Tarik_ULN", 0),
            asin_values.get("Bayar_ULN", 0),
            asin_values.get("Transaksi_Tanpa_Underlying", 0),
            asin_values.get("Lainnya", 0)
        ])
        asin_total = asin_values.get("Investasi", 0) + asin_values.get("Remittance", 0) + asin_values.get("Repatriasi", 0) + asin_values.get("Trading", 0) + asin_lainnya

        all_rows.append(create_row(tgl, "C", "C. NON RESIDEN", 1, None, asin_total, True, "sum_children"))
        all_rows.append(create_row(tgl, "C.a", "a. Investasi", 2, "C", asin_values.get("Investasi", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.b", "b. Remittance", 2, "C", asin_values.get("Remittance", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.c", "c. Repatriasi", 2, "C", asin_values.get("Repatriasi", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.d", "d. Trading", 2, "C", asin_values.get("Trading", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.e", "e. Lainnya", 2, "C", asin_lainnya, True, "sum_children"))
        all_rows.append(create_row(tgl, "C.e.1", "1-Ekspor", 3, "C.e", asin_values.get("Ekspor", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.e.2", "2-Impor", 3, "C.e", asin_values.get("Impor", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.e.3", "3-Tarik ULN", 3, "C.e", asin_values.get("Tarik_ULN", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.e.4", "4-Bayar ULN", 3, "C.e", asin_values.get("Bayar_ULN", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.e.5", "5-Transaksi tanpa underlying", 3, "C.e", asin_values.get("Transaksi_Tanpa_Underlying", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.e.6", "6-Lainnya", 3, "C.e", asin_values.get("Lainnya", 0), False, "source"))

        # ====================================================================
        # D. NET SUPPLY DEMAND VALAS (Level 1)
        # ====================================================================

        net_total = korp_level1_total + indv_total + asin_total
        all_rows.append(create_row(tgl, "D", "D. NET SUPPLY DEMAND VALAS (A+B+C)", 1, None, net_total, True, "sum"))

    # Convert to DataFrame
    df_hierarchical = pd.DataFrame(all_rows)

    logger.info(f"✓ Full hierarchy built: {len(df_hierarchical):,} rows, {df_hierarchical['Row_ID'].nunique()} unique nodes")
    logger.info(f"Step 3B completed\n")

    return df_hierarchical


def build_hierarchical_simple(tidy_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Membangun struktur hierarki SIMPLIFIED untuk dashboard (versi simple).

    Struktur Simple (HANYA kategori utama, sub-level dijadikan "Lainnya"):

    A. KORPORASI
       1. PTMN
          a. Impor
          b. Repatriasi
          c. Lainnya (total dari: Ekspor, Tarik_ULN, Bayar_ULN, Investasi, Remittance, Trading, Transaksi_Tanpa_Underlying, Lainnya)
       2. Korporasi Lainnya
          a. Ekspor
          b. Transaksi tanpa underlying
          c. Investasi
          d. Impor
          e. Repatriasi
          f. Lainnya (total dari: Tarik_ULN, Bayar_ULN, Remittance, Trading, Lainnya)

    B. INDIVIDU
       a. Ekspor
       b. Transaksi tanpa underlying
       c. Impor
       d. Lainnya (total dari: Tarik_ULN, Bayar_ULN, Investasi, Repatriasi, Remittance, Trading, Lainnya)

    C. NON RESIDEN
       a. Investasi
       b. Remittance
       c. Repatriasi
       d. Trading
       e. Lainnya (total dari: Ekspor, Impor, Tarik_ULN, Bayar_ULN, Transaksi_Tanpa_Underlying, Lainnya)

    D. NET SUPPLY DEMAND VALAS (A+B+C)

    Args:
        tidy_dict: Dictionary hasil tidy_transform()

    Returns:
        DataFrame dengan struktur hierarki simple (long format)
    """
    logger.info("=" * 70)
    logger.info("STEP 3B-SIMPLE: BUILD SIMPLIFIED HIERARCHICAL STRUCTURE")
    logger.info("=" * 70)

    # Get all unique dates (sorted)
    all_dates = sorted(tidy_dict['korporasi']['Tanggal'].unique())
    logger.info(f"Processing {len(all_dates)} unique dates from {all_dates[0]} to {all_dates[-1]}")

    # Helper function
    def create_row(tanggal, row_id, row_label, level, parent_id, nilai, is_calc, calc_type):
        return {
            'Tanggal': tanggal,
            'Row_ID': row_id,
            'Row_Label': row_label,
            'Level': level,
            'Parent_ID': parent_id,
            'Nilai_Ribu_USD': round(nilai, 0),
            'Is_Calculated': is_calc,
            'Calculation_Type': calc_type
        }

    all_rows = []

    for tgl in all_dates:
        # Filter data
        korp = tidy_dict['korporasi'][tidy_dict['korporasi']['Tanggal'] == tgl]
        ptmn = tidy_dict['ptmn'][tidy_dict['ptmn']['Tanggal'] == tgl]
        indv = tidy_dict['individu'][tidy_dict['individu']['Tanggal'] == tgl]
        asin = tidy_dict['asing'][tidy_dict['asing']['Tanggal'] == tgl]

        # Convert to dict
        korp_values = dict(zip(korp['Jenis_Transaksi'], korp['Nilai_Ribu_USD']))
        ptmn_values = dict(zip(ptmn['Jenis_Transaksi'], ptmn['Nilai_Ribu_USD']))
        indv_values = dict(zip(indv['Jenis_Transaksi'], indv['Nilai_Ribu_USD']))
        asin_values = dict(zip(asin['Jenis_Transaksi'], asin['Nilai_Ribu_USD']))

        # ====================================================================
        # A. KORPORASI
        # ====================================================================

        # A.1. PTMN - SIMPLIFIED
        ptmn_lainnya = sum([
            ptmn_values.get("Ekspor", 0),
            ptmn_values.get("Tarik_ULN", 0),
            ptmn_values.get("Bayar_ULN", 0),
            ptmn_values.get("Investasi", 0),
            ptmn_values.get("Remittance", 0),
            ptmn_values.get("Trading", 0),
            ptmn_values.get("Transaksi_Tanpa_Underlying", 0),
            ptmn_values.get("Lainnya", 0)
        ])
        ptmn_total = ptmn_values.get("Impor", 0) + ptmn_values.get("Repatriasi", 0) + ptmn_lainnya

        all_rows.append(create_row(tgl, "A.1", "1. PTMN", 2, "A", ptmn_total, True, "sum_children"))
        all_rows.append(create_row(tgl, "A.1.a", "a. Impor", 3, "A.1", ptmn_values.get("Impor", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.1.b", "b. Repatriasi", 3, "A.1", ptmn_values.get("Repatriasi", 0), False, "source"))
        all_rows.append(create_row(tgl, "A.1.c", "c. Lainnya", 3, "A.1", ptmn_lainnya, True, "sum"))

        # A.2. Korporasi Lainnya - SIMPLIFIED
        korp_lain_ekspor = korp_values.get("Ekspor", 0) - ptmn_values.get("Ekspor", 0)
        korp_lain_nonund = korp_values.get("Transaksi_Tanpa_Underlying", 0) - ptmn_values.get("Transaksi_Tanpa_Underlying", 0)
        korp_lain_investasi = korp_values.get("Investasi", 0) - ptmn_values.get("Investasi", 0)
        korp_lain_impor = korp_values.get("Impor", 0) - ptmn_values.get("Impor", 0)
        korp_lain_repatriasi = korp_values.get("Repatriasi", 0) - ptmn_values.get("Repatriasi", 0)

        korp_lain_lainnya = (
            (korp_values.get("Tarik_ULN", 0) - ptmn_values.get("Tarik_ULN", 0)) +
            (korp_values.get("Bayar_ULN", 0) - ptmn_values.get("Bayar_ULN", 0)) +
            (korp_values.get("Remittance", 0) - ptmn_values.get("Remittance", 0)) +
            (korp_values.get("Trading", 0) - ptmn_values.get("Trading", 0)) +
            (korp_values.get("Lainnya", 0) - ptmn_values.get("Lainnya", 0))
        )

        korp_lain_total = korp_lain_ekspor + korp_lain_nonund + korp_lain_investasi + korp_lain_impor + korp_lain_repatriasi + korp_lain_lainnya

        all_rows.append(create_row(tgl, "A.2", "2. Korporasi Lainnya", 2, "A", korp_lain_total, True, "sum_children"))
        all_rows.append(create_row(tgl, "A.2.a", "a. Ekspor", 3, "A.2", korp_lain_ekspor, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.b", "b. Transaksi tanpa underlying", 3, "A.2", korp_lain_nonund, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.c", "c. Investasi", 3, "A.2", korp_lain_investasi, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.d", "d. Impor", 3, "A.2", korp_lain_impor, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.e", "e. Repatriasi", 3, "A.2", korp_lain_repatriasi, True, "difference"))
        all_rows.append(create_row(tgl, "A.2.f", "f. Lainnya", 3, "A.2", korp_lain_lainnya, True, "sum"))

        # A. KORPORASI Total
        korp_level1_total = ptmn_total + korp_lain_total
        all_rows.append(create_row(tgl, "A", "A. KORPORASI", 1, None, korp_level1_total, True, "sum_children"))

        # ====================================================================
        # B. INDIVIDU - SIMPLIFIED
        # ====================================================================

        indv_lainnya = sum([
            indv_values.get("Tarik_ULN", 0),
            indv_values.get("Bayar_ULN", 0),
            indv_values.get("Investasi", 0),
            indv_values.get("Repatriasi", 0),
            indv_values.get("Remittance", 0),
            indv_values.get("Trading", 0),
            indv_values.get("Lainnya", 0)
        ])
        indv_total = indv_values.get("Ekspor", 0) + indv_values.get("Transaksi_Tanpa_Underlying", 0) + indv_values.get("Impor", 0) + indv_lainnya

        all_rows.append(create_row(tgl, "B", "B. INDIVIDU", 1, None, indv_total, True, "sum_children"))
        all_rows.append(create_row(tgl, "B.a", "a. Ekspor", 2, "B", indv_values.get("Ekspor", 0), False, "source"))
        all_rows.append(create_row(tgl, "B.b", "b. Transaksi tanpa underlying", 2, "B", indv_values.get("Transaksi_Tanpa_Underlying", 0), False, "source"))
        all_rows.append(create_row(tgl, "B.c", "c. Impor", 2, "B", indv_values.get("Impor", 0), False, "source"))
        all_rows.append(create_row(tgl, "B.d", "d. Lainnya", 2, "B", indv_lainnya, True, "sum"))

        # ====================================================================
        # C. NON RESIDEN - SIMPLIFIED
        # ====================================================================

        asin_lainnya = sum([
            asin_values.get("Ekspor", 0),
            asin_values.get("Impor", 0),
            asin_values.get("Tarik_ULN", 0),
            asin_values.get("Bayar_ULN", 0),
            asin_values.get("Transaksi_Tanpa_Underlying", 0),
            asin_values.get("Lainnya", 0)
        ])
        asin_total = asin_values.get("Investasi", 0) + asin_values.get("Remittance", 0) + asin_values.get("Repatriasi", 0) + asin_values.get("Trading", 0) + asin_lainnya

        all_rows.append(create_row(tgl, "C", "C. NON RESIDEN", 1, None, asin_total, True, "sum_children"))
        all_rows.append(create_row(tgl, "C.a", "a. Investasi", 2, "C", asin_values.get("Investasi", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.b", "b. Remittance", 2, "C", asin_values.get("Remittance", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.c", "c. Repatriasi", 2, "C", asin_values.get("Repatriasi", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.d", "d. Trading", 2, "C", asin_values.get("Trading", 0), False, "source"))
        all_rows.append(create_row(tgl, "C.e", "e. Lainnya", 2, "C", asin_lainnya, True, "sum"))

        # ====================================================================
        # D. NET SUPPLY DEMAND VALAS
        # ====================================================================

        net_total = korp_level1_total + indv_total + asin_total
        all_rows.append(create_row(tgl, "D", "D. NET SUPPLY DEMAND VALAS (A+B+C)", 1, None, net_total, True, "sum"))

    # Convert to DataFrame
    df_hierarchical = pd.DataFrame(all_rows)

    logger.info(f"✓ Simple hierarchy built: {len(df_hierarchical):,} rows, {df_hierarchical['Row_ID'].nunique()} unique nodes")
    logger.info(f"Step 3C completed\n")

    return df_hierarchical


# ============================================================================
# STEP 4: WIDE FORMAT (003.r step 4)
# ============================================================================

def to_wide_format(hierarchical_df: pd.DataFrame, output_file: Path, version: str = "full") -> pd.DataFrame:
    """
    Transformasi dari long format ke wide format untuk dashboard.

    Proses:
    - Pivot: Tanggal menjadi kolom
    - Rows: Row_ID, Row_Label, Level
    - Values: Nilai_Ribu_USD

    Args:
        hierarchical_df: DataFrame hasil build_hierarchical()
        output_file: Path untuk menyimpan output
        version: Versi output ("full" atau "simple")

    Returns:
        DataFrame wide format
    """
    logger.info("=" * 70)
    logger.info(f"STEP 4: WIDE FORMAT TRANSFORMATION ({version.upper()})")
    logger.info("=" * 70)

    # Select relevant columns
    df_for_pivot = hierarchical_df[['Row_ID', 'Row_Label', 'Level', 'Tanggal', 'Nilai_Ribu_USD']].copy()

    # Pivot: Tanggal -> columns
    df_wide = df_for_pivot.pivot_table(
        index=['Row_ID', 'Row_Label', 'Level'],
        columns='Tanggal',
        values='Nilai_Ribu_USD',
        aggfunc='first'  # Seharusnya hanya ada 1 nilai per kombinasi
    ).reset_index()

    # Sort by Row_ID untuk urutan yang konsisten
    df_wide = df_wide.sort_values('Row_ID')

    # Convert date columns to string format (YYYY-MM-DD)
    date_cols = [col for col in df_wide.columns if isinstance(col, pd.Timestamp)]
    for col in date_cols:
        df_wide.rename(columns={col: col.strftime('%Y-%m-%d')}, inplace=True)

    # Save to output file
    df_wide.to_csv(output_file, index=False)

    logger.info(f"✓ Saved: {output_file}")
    logger.info(f"  Shape: {df_wide.shape[0]} rows × {df_wide.shape[1]} columns")
    logger.info(f"  Date columns: {len(date_cols)}")
    logger.info(f"Step 4 completed: Wide format ({version}) created\n")

    return df_wide


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def run_pipeline():
    """
    Menjalankan full ETL pipeline dari Excel ke wide CSV.

    Generates 2 versions:
    1. FULL version (sdv-wide-full.csv) - dengan semua sub-kategori detail
    2. SIMPLE version (sdv-wide.csv) - kategori utama, sub-level collapsed ke "Lainnya"
    """
    start_time = datetime.now()

    logger.info("\n" + "=" * 70)
    logger.info("ETL PIPELINE - SUPPLY DEMAND VALAS (DUAL VERSION)")
    logger.info("=" * 70)
    logger.info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Source: {SOURCE_FILE}")
    logger.info(f"Output FULL: {OUTPUT_FILE_FULL}")
    logger.info(f"Output SIMPLE: {OUTPUT_FILE_SIMPLE}")
    logger.info(f"Date range: {START_DATE} to [latest available data]\n")

    try:
        # Step 1: Extract & Clean
        data_dict = extract_and_clean()

        # Step 2: Transform & Calculate
        data_calculated = transform_and_calculate(data_dict)

        # Step 3A: Tidy Transform
        tidy_dict = tidy_transform(data_calculated)

        # Step 3B: Build Hierarchy - FULL VERSION
        hierarchical_df_full = build_hierarchical(tidy_dict)

        # Step 3C: Build Hierarchy - SIMPLE VERSION
        hierarchical_df_simple = build_hierarchical_simple(tidy_dict)

        # Step 4A: Wide Format - FULL VERSION
        wide_df_full = to_wide_format(hierarchical_df_full, OUTPUT_FILE_FULL, version="full")

        # Step 4B: Wide Format - SIMPLE VERSION
        wide_df_simple = to_wide_format(hierarchical_df_simple, OUTPUT_FILE_SIMPLE, version="simple")

        # Summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info("=" * 70)
        logger.info("PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)
        logger.info(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"\nOutput summary:")
        logger.info(f"  FULL VERSION:")
        logger.info(f"    - File: {OUTPUT_FILE_FULL}")
        logger.info(f"    - Rows: {wide_df_full.shape[0]}")
        logger.info(f"    - Columns: {wide_df_full.shape[1]}")
        logger.info(f"  SIMPLE VERSION (PRIMARY):")
        logger.info(f"    - File: {OUTPUT_FILE_SIMPLE}")
        logger.info(f"    - Rows: {wide_df_simple.shape[0]}")
        logger.info(f"    - Columns: {wide_df_simple.shape[1]}")

        # Get actual date range from data
        date_cols = [col for col in wide_df_simple.columns if col not in ['Row_ID', 'Row_Label', 'Level']]
        if date_cols:
            logger.info(f"  Date range: {date_cols[0]} to {date_cols[-1]}")
        else:
            logger.info(f"  Date range: {START_DATE} to [latest available data]")
        logger.info("=" * 70 + "\n")

        return wide_df_simple, wide_df_full

    except Exception as e:
        logger.error(f"\n{'=' * 70}")
        logger.error("PIPELINE FAILED")
        logger.error(f"{'=' * 70}")
        logger.error(f"Error: {str(e)}")
        logger.error(f"{'=' * 70}\n")
        raise


if __name__ == "__main__":
    run_pipeline()
