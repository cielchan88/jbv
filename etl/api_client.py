"""
API Client for CData Virtuality REST API
=========================================

Module untuk fetch data transaksi valas dari CData Virtuality REST API.
API ini menyediakan data real-time untuk tanggal hari ini.

Endpoints:
- TTS_SDV_KORPORASI: Data Korporasi
- TTS_PEL_LN_VS_LWN_DN_BANK: Data PTMN/Asing/Individu (semua jadi 1)

Author: Data Processing Team
Date: 2024-10-24
"""

import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
import xmltodict
from datetime import datetime
from pathlib import Path
import logging
import urllib3
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Disable SSL warnings for internal network
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

# Import configuration from config file
try:
    from config import API_CONFIG, API_ENDPOINTS as ENDPOINT_NAMES, SHEET_MAPPING
except ImportError:
    # Fallback to default config if config.py not found
    logger.warning("config.py not found - using default configuration")
    API_CONFIG = {
        'base_url': 'https://dc1datavirt02.corp.bi.go.id:443/rest/api/source/views',
        'username': 'redianto_s',
        'password': 'password',
        'timeout': 60,
        'verify_ssl': False
    }
    ENDPOINT_NAMES = {
        'korporasi': 'TTS_SDV_KORPORASI',
        'ptmn': 'TTS_SDV_PERTAMINA',
        'asing': 'TTS_PEL_LN_VS_LWN_DN_BANK',
        'individu': 'TTS_PEL_INDIV_DN_VS_LWN_BANK_DN'
    }
    SHEET_MAPPING = {
        'korporasi': 'Korporasi',
        'ptmn': 'PTMN',
        'asing': 'Asing',
        'individu': 'Individu'
    }

# Build full API endpoints
API_BASE_URL = API_CONFIG['base_url']
API_ENDPOINTS = {
    key: f"{API_BASE_URL}/{endpoint_name}"
    for key, endpoint_name in ENDPOINT_NAMES.items()
}

# Extract credentials from config
API_USERNAME = API_CONFIG['username']
API_PASSWORD = API_CONFIG['password']
REQUEST_TIMEOUT = API_CONFIG['timeout']


def fetch_api_data(endpoint_key: str = 'korporasi', verify_ssl: bool = False) -> pd.DataFrame:
    """
    Fetch data dari CData Virtuality REST API.

    Args:
        endpoint_key: Key untuk endpoint ('korporasi', 'ptmn', 'asing', 'individu')
        verify_ssl: Verify SSL certificate (default False untuk internal network)

    Returns:
        DataFrame dengan kolom: TANGGAL_LAPORAN, TUJUAN_TRANSAKSI, VOLUME_NETT_RIBU_USD

    Raises:
        requests.exceptions.RequestException: Jika API call gagal
        ValueError: Jika response tidak valid
    """
    if endpoint_key not in API_ENDPOINTS:
        raise ValueError(f"Invalid endpoint key: {endpoint_key}. Must be one of {list(API_ENDPOINTS.keys())}")

    url = API_ENDPOINTS[endpoint_key]

    logger.info(f"Fetching data from API: {endpoint_key}")
    logger.info(f"URL: {url}")

    try:
        # Create auth object
        auth = HTTPBasicAuth(API_USERNAME, API_PASSWORD)

        # Make HTTP GET request with authentication
        response = requests.get(
            url,
            auth=auth,
            timeout=REQUEST_TIMEOUT,
            verify=verify_ssl,
            headers={'Accept': 'application/xml'},
            proxies={'http': None, 'https': None}  # Disable proxy for internal network
        )

        # Check response status
        response.raise_for_status()

        logger.info(f"✓ API response received (status: {response.status_code})")

        # Parse XML response
        df = parse_xml_response(response.text)

        logger.info(f"✓ Parsed {len(df)} records from API")
        logger.info(f"  Date: {df['TANGGAL_LAPORAN'].iloc[0] if len(df) > 0 else 'N/A'}")
        logger.info(f"  Categories: {df['TUJUAN_TRANSAKSI'].nunique()}")

        return df

    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
        error_msg = str(e)
        if isinstance(e, requests.exceptions.Timeout):
            error_msg = f"API request timeout after {REQUEST_TIMEOUT}s"
        elif isinstance(e, requests.exceptions.ConnectionError):
            error_msg = "API connection error - check VPN/network connection"

        logger.error(f"✗ API fetch failed: {error_msg}")
        raise
    except Exception as e:
        logger.error(f"✗ Unexpected error: {e}")
        raise


def parse_xml_response(xml_text: str) -> pd.DataFrame:
    """
    Parse XML response dari API menjadi DataFrame.

    Expected XML structure:
    <result>
        <rows>
            <row>
                <TANGGAL_LAPORAN>2025-10-23</TANGGAL_LAPORAN>
                <TUJUAN_TRANSAKSI>05 - Import</TUJUAN_TRANSAKSI>
                <VOLUME_NETT_RIBU_USD>85062.5</VOLUME_NETT_RIBU_USD>
            </row>
            ...
        </rows>
    </result>

    Args:
        xml_text: Raw XML response string

    Returns:
        DataFrame dengan kolom: TANGGAL_LAPORAN, TUJUAN_TRANSAKSI, VOLUME_NETT_RIBU_USD
    """
    try:
        # Parse XML using xmltodict (same as test_api.py)
        data_dict = xmltodict.parse(xml_text)

        # Check if the expected data ('row') exists
        if 'result' not in data_dict or 'rows' not in data_dict['result'] or 'row' not in data_dict['result']['rows']:
            raise ValueError("No 'row' data found in XML response")

        # Extract rows
        rows = data_dict['result']['rows']['row']

        # Convert to DataFrame
        df = pd.DataFrame(rows)

        # Validate required columns
        required_cols = ['TANGGAL_LAPORAN', 'TUJUAN_TRANSAKSI', 'VOLUME_NETT_RIBU_USD']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        # Convert data types
        df['TANGGAL_LAPORAN'] = pd.to_datetime(df['TANGGAL_LAPORAN'])
        df['VOLUME_NETT_RIBU_USD'] = pd.to_numeric(df['VOLUME_NETT_RIBU_USD'], errors='coerce')

        return df

    except Exception as e:
        logger.error(f"Error parsing XML: {e}")
        raise ValueError(f"Invalid XML response: {e}")


def transform_api_to_wide(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform API data dari format long (rows per transaction) ke format wide (columns per transaction).

    API format (long):
        TANGGAL_LAPORAN | TUJUAN_TRANSAKSI      | VOLUME_NETT_RIBU_USD
        2025-10-23      | 05 - Import           | 85062.5
        2025-10-23      | 14 - Biaya Perjalanan | 18.04
        ...

    Excel format (wide):
        x1          | x2  | x3     | x4    | x5    | x6    | x7    | x8      | ...
        2025-10-23  | 0   | -405   | -40K  | -77   | 1231  | -89   | 259476  | ...

    Mapping menggunakan CODE_TO_COLUMN dictionary (code -> column number).

    Args:
        df: DataFrame dari parse_xml_response()

    Returns:
        DataFrame dalam format wide dengan kolom x1 (tanggal) dan x2-x47 (kategori transaksi)
    """
    if len(df) == 0:
        logger.warning("Empty DataFrame - no data to transform")
        return pd.DataFrame()

    # Extract transaction code from TUJUAN_TRANSAKSI (e.g., "05 - Import" -> 5)
    df['transaction_code'] = df['TUJUAN_TRANSAKSI'].str.extract(r'^(\d+)')[0].astype(int)

    # Check for duplicate transaction codes (same code for same date)
    duplicates = df.groupby(['TANGGAL_LAPORAN', 'transaction_code']).size()
    duplicates = duplicates[duplicates > 1]

    if not duplicates.empty:
        logger.warning(f"  ⚠️  Found {len(duplicates)} duplicate transaction codes for same date:")
        for (date, code), count in duplicates.items():
            logger.warning(f"    - Date {date.date()}, Code {code}: {count} rows")
        logger.warning("  → Summing duplicate values before pivot")

    # Group by date and transaction code to handle duplicates
    # This will sum values if there are multiple rows with same code for same date
    df_grouped = df.groupby(['TANGGAL_LAPORAN', 'transaction_code'], as_index=False).agg({
        'VOLUME_NETT_RIBU_USD': 'sum',
        'TUJUAN_TRANSAKSI': 'first'  # Keep first transaction name for reference
    })

    # Pivot to wide format
    df_wide = df_grouped.pivot_table(
        index='TANGGAL_LAPORAN',
        columns='transaction_code',
        values='VOLUME_NETT_RIBU_USD',
        aggfunc='sum',  # Use sum for safety
        fill_value=0
    ).reset_index()

    # Create result DataFrame dengan struktur Excel yang benar
    result = pd.DataFrame()
    result['x1'] = df_wide['TANGGAL_LAPORAN']  # Column x1 = date

    # Initialize all columns x2-x47 dengan 0
    for col_num in range(2, 48):
        result[f'x{col_num}'] = 0.0

    # Map transaction codes ke Excel columns menggunakan CODE_TO_COLUMN
    for code, col_num in CODE_TO_COLUMN.items():
        if code in df_wide.columns:
            result[f'x{col_num}'] = df_wide[code].values
            logger.debug(f"Mapped code {code:02d} -> x{col_num}")

    # Column x43 = Total (sum of columns x3-x42)
    cols_to_sum = [f'x{i}' for i in range(3, 43)]
    result['x43'] = result[cols_to_sum].sum(axis=1)

    # Ensure x2 is always 0 (this column is not used but must be 0, not NaN)
    result['x2'] = 0.0

    # Columns x44-x47 are legacy columns not provided by API - set to 0
    for col in ['x44', 'x45', 'x46', 'x47']:
        result[col] = 0.0

    # Reorder columns x1-x47
    all_cols = ['x1'] + [f'x{i}' for i in range(2, 48)]
    result = result[all_cols]

    # Convert x1 to datetime
    result['x1'] = pd.to_datetime(result['x1'])

    logger.info(f"✓ Transformed to wide format: {result.shape}")
    logger.info(f"  Date: {result['x1'].iloc[0]}")
    logger.info(f"  Total (x43): {result['x43'].iloc[0]:.2f}")

    return result


def fetch_all_endpoints() -> dict:
    """
    Fetch data dari semua API endpoints.

    Returns:
        Dictionary dengan key: endpoint name, value: DataFrame (wide format)
    """
    results = {}

    for endpoint_key in API_ENDPOINTS.keys():
        try:
            logger.info(f"\n{'='*70}")
            logger.info(f"Fetching {endpoint_key.upper()} data")
            logger.info(f"{'='*70}")

            # Fetch data
            df_long = fetch_api_data(endpoint_key)

            # Transform to wide format
            df_wide = transform_api_to_wide(df_long)

            results[endpoint_key] = df_wide

            logger.info(f"✓ {endpoint_key.upper()} completed\n")

        except Exception as e:
            logger.error(f"✗ Failed to fetch {endpoint_key}: {e}\n")
            results[endpoint_key] = None

    return results


def sync_today_data(excel_path: str, force_refresh: bool = False) -> dict:
    """
    Sync data hari ini dari API ke Excel file.

    Mekanisme:
    1. Cek tanggal terakhir di Excel untuk tiap sheet
    2. Jika tanggal terakhir < hari ini (atau force_refresh=True):
       - Fetch data dari API
       - Append/update ke Excel
       - Save Excel file
    3. Return status sync untuk ditampilkan di UI

    Args:
        excel_path: Path ke Excel file (e.g., 'data/raw/source-data.xlsx')
        force_refresh: Force refresh data hari ini (default False)

    Returns:
        Dictionary dengan status sync untuk tiap sheet:
        {
            'korporasi': {
                'status': 'success' | 'skipped' | 'error',
                'message': 'Data hari ini sudah tersedia',
                'last_date': '2025-11-11',
                'sync_time': '2025-11-11 08:30:15'
            },
            ...
        }
    """
    from openpyxl import load_workbook

    today = pd.Timestamp.now().normalize()
    sync_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Use sheet mapping from config
    sheet_mapping = SHEET_MAPPING

    results = {}
    excel_modified = False

    logger.info(f"\n{'='*70}")
    logger.info(f"Starting API Sync - {sync_time}")
    logger.info(f"Excel path: {excel_path}")
    logger.info(f"{'='*70}\n")

    # Load Excel file
    try:
        excel_file = pd.ExcelFile(excel_path)
        wb = load_workbook(excel_path)
    except FileNotFoundError:
        logger.error(f"Excel file not found: {excel_path}")
        return {'error': {'status': 'error', 'message': f'Excel file not found: {excel_path}'}}
    except Exception as e:
        logger.error(f"Failed to load Excel: {e}")
        return {'error': {'status': 'error', 'message': f'Failed to load Excel: {e}'}}

    # Process each endpoint/sheet
    for endpoint_key, sheet_name in sheet_mapping.items():
        try:
            logger.info(f"Processing {sheet_name}...")

            # Read existing data from Excel
            df_excel = pd.read_excel(excel_path, sheet_name=sheet_name)

            # Assume first column is date (x1)
            date_col = df_excel.columns[0]
            df_excel[date_col] = pd.to_datetime(df_excel[date_col])

            # Get last date in Excel
            last_date = df_excel[date_col].max()

            # Check if sync needed
            needs_sync = (last_date < today) or force_refresh

            # Calculate gap
            gap_days = (today - last_date).days

            if not needs_sync:
                results[endpoint_key] = {
                    'status': 'skipped',
                    'message': 'Data hari ini sudah tersedia',
                    'last_date': last_date.strftime('%Y-%m-%d'),
                    'sync_time': sync_time
                }
                logger.info(f"  ✓ Skipped - data already up to date (last: {last_date.date()})\n")
                continue

            # Fetch data from API
            logger.info(f"  → Fetching data from API...")
            df_long = fetch_api_data(endpoint_key)
            df_wide = transform_api_to_wide(df_long)

            if df_wide is None or len(df_wide) == 0:
                results[endpoint_key] = {
                    'status': 'error',
                    'message': 'API returned empty data',
                    'last_date': last_date.strftime('%Y-%m-%d'),
                    'sync_time': sync_time
                }
                logger.warning(f"  ⚠️  API returned empty data\n")
                continue

            # Get API date
            api_date = df_wide['x1'].iloc[0]

            # Check if API date already exists in Excel
            if api_date in df_excel[date_col].values and not force_refresh:
                results[endpoint_key] = {
                    'status': 'skipped',
                    'message': f'Data {api_date.date()} already exists',
                    'last_date': last_date.strftime('%Y-%m-%d'),
                    'sync_time': sync_time
                }
                logger.info(f"  ✓ Skipped - date {api_date.date()} already exists\n")
                continue

            # Append or update data
            if force_refresh and api_date in df_excel[date_col].values:
                # Update: remove old row and append new
                df_excel = df_excel[df_excel[date_col] != api_date]
                logger.info(f"  → Updating existing data for {api_date.date()}...")
            else:
                # Append new row
                logger.info(f"  → Appending new data for {api_date.date()}...")

            # Combine data
            df_combined = pd.concat([df_excel, df_wide], ignore_index=True)
            df_combined = df_combined.sort_values(date_col).reset_index(drop=True)

            # Write back to Excel
            with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                df_combined.to_excel(writer, sheet_name=sheet_name, index=False)

            excel_modified = True

            # Prepare result with gap warning if applicable
            result = {
                'status': 'success',
                'message': f'Data {api_date.date()} berhasil disimpan',
                'last_date': api_date.strftime('%Y-%m-%d'),
                'sync_time': sync_time,
                'rows_added': len(df_wide)
            }

            # Add gap warning if there's a significant gap
            if gap_days > 1:
                result['gap_warning'] = {
                    'gap_days': gap_days - 1,  # Exclude today
                    'missing_start': (last_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                    'missing_end': (today - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
                }
                logger.warning(f"  ⚠️  Gap detected: {gap_days - 1} days missing ({(last_date + pd.Timedelta(days=1)).date()} to {(today - pd.Timedelta(days=1)).date()})")

            results[endpoint_key] = result
            logger.info(f"  ✓ Success - added {len(df_wide)} row(s)\n")

        except Exception as e:
            results[endpoint_key] = {
                'status': 'error',
                'message': f'Error: {str(e)}',
                'last_date': last_date.strftime('%Y-%m-%d') if 'last_date' in locals() else 'N/A',
                'sync_time': sync_time
            }
            logger.error(f"  ✗ Error: {e}\n")

    if excel_modified:
        logger.info(f"✓ Excel file updated successfully\n")
    else:
        logger.info(f"ℹ No updates needed\n")

    logger.info(f"{'='*70}")
    logger.info(f"Sync completed - {sync_time}")
    logger.info(f"{'='*70}\n")

    return results


def test_api_connection() -> dict:
    """
    Test koneksi ke API endpoints dan return status.

    Returns:
        Dictionary dengan status untuk setiap endpoint
    """
    status = {}

    for endpoint_key, url in API_ENDPOINTS.items():
        try:
            auth = HTTPBasicAuth(API_USERNAME, API_PASSWORD)
            response = requests.get(
                url,
                auth=auth,
                timeout=10,
                verify=False,
                headers={'Accept': 'application/xml'},
                proxies={'http': None, 'https': None}
            )
            response.raise_for_status()

            status[endpoint_key] = {
                'status': 'OK',
                'status_code': response.status_code,
                'message': 'Connection successful'
            }
        except requests.exceptions.Timeout:
            status[endpoint_key] = {
                'status': 'ERROR',
                'status_code': None,
                'message': 'Request timeout'
            }
        except requests.exceptions.ConnectionError:
            status[endpoint_key] = {
                'status': 'ERROR',
                'status_code': None,
                'message': 'Connection error - check VPN/network'
            }
        except requests.exceptions.HTTPError as e:
            status[endpoint_key] = {
                'status': 'ERROR',
                'status_code': e.response.status_code,
                'message': f'HTTP error: {e.response.status_code}'
            }
        except Exception as e:
            status[endpoint_key] = {
                'status': 'ERROR',
                'status_code': None,
                'message': f'Unexpected error: {str(e)}'
            }

    return status


if __name__ == "__main__":
    # Test script
    print("\n" + "="*70)
    print("API CLIENT TEST")
    print("="*70 + "\n")

    # Test connection
    print("Testing API connection...")
    status = test_api_connection()
    for endpoint, result in status.items():
        print(f"  {endpoint}: {result['status']} - {result['message']}")

    print("\n" + "="*70)

    # Fetch data if connection OK
    if all(s['status'] == 'OK' for s in status.values()):
        print("\nFetching data from all endpoints...")
        results = fetch_all_endpoints()

        for endpoint, df in results.items():
            if df is not None and len(df) > 0:
                print(f"\n{endpoint.upper()} data:")
                print(df.head())
    else:
        print("\n⚠️  API connection failed - skipping data fetch")

    print("\n" + "="*70)


def sync_today_data(source_file_path: str, force_refresh: bool = False) -> dict:
    """
    Sync today's data from API to source-data.xlsx.
    This function is called from Streamlit Sumber Data page.

    Args:
        source_file_path: Path to source-data.xlsx
        force_refresh: Force refresh even if today's data exists

    Returns:
        Dictionary with sync results per endpoint:
        {
            'korporasi': {'status': 'success'|'skipped'|'error', 'message': str, ...},
            ...
        }
    """
    import shutil
    from datetime import datetime

    logger.info("="*70)
    logger.info("SYNC TODAY DATA FROM API")
    logger.info("="*70)

    source_file = Path(source_file_path)

    if not source_file.exists():
        return {
            'error': {
                'status': 'error',
                'message': f'Source file not found: {source_file}'
            }
        }

    # Create backup
    backup_dir = source_file.parent / 'backup'
    backup_dir.mkdir(exist_ok=True)
    backup_file = backup_dir / f'source-data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

    logger.info(f"Creating backup: {backup_file}")
    shutil.copy2(source_file, backup_file)

    # Fetch data from all endpoints
    sync_results = {}

    for endpoint_key, sheet_name in SHEET_MAPPING.items():
        try:
            logger.info(f"\n{'-'*70}")
            logger.info(f"Syncing {endpoint_key.upper()} ({sheet_name})")
            logger.info(f"{'-'*70}")

            # Fetch from API
            df_long = fetch_api_data(endpoint_key)

            # Transform to wide
            df_wide = transform_api_to_wide(df_long)

            # Convert column names from x1-x47 to 1-47
            column_mapping = {f'x{i}': i for i in range(1, 48)}
            df_wide = df_wide.rename(columns=column_mapping)

            # Normalize datetime
            df_wide[1] = pd.to_datetime(df_wide[1]).dt.normalize()

            # Read existing data
            df_existing = pd.read_excel(source_file, sheet_name=sheet_name)
            df_existing.iloc[:, 0] = pd.to_datetime(df_existing.iloc[:, 0]).dt.normalize()

            last_date = df_existing.iloc[-1, 0]
            new_date = df_wide[1].iloc[0]

            logger.info(f"Last date in Excel: {last_date.strftime('%Y-%m-%d')}")
            logger.info(f"New date from API: {new_date.strftime('%Y-%m-%d')}")

            # Check if new date is newer
            if new_date <= last_date and not force_refresh:
                sync_results[endpoint_key] = {
                    'status': 'skipped',
                    'message': f'Data sudah up-to-date',
                    'last_date': last_date.strftime('%Y-%m-%d'),
                    'new_date': new_date.strftime('%Y-%m-%d')
                }
                logger.info(f"✓ {sheet_name}: Skipped (already up-to-date)")
                continue

            # Check for gap
            gap_days = (new_date - last_date).days - 1
            gap_warning = None
            if gap_days > 0:
                gap_warning = {
                    'gap_days': gap_days,
                    'missing_start': (last_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                    'missing_end': (new_date - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
                }
                logger.warning(f"⚠️  Gap detected: {gap_days} days between {last_date.strftime('%Y-%m-%d')} and {new_date.strftime('%Y-%m-%d')}")

            # Append new data
            df_combined = pd.concat([df_existing, df_wide], ignore_index=True)

            # Ensure column 2 is always 0 (not NaN) - this column is always empty/zero
            df_combined.iloc[:, 1] = df_combined.iloc[:, 1].fillna(0.0)

            # Write back (we'll write all sheets at the end)
            sync_results[endpoint_key] = {
                'status': 'success',
                'message': f'Data berhasil ditambahkan',
                'last_date': new_date.strftime('%Y-%m-%d'),
                'sync_time': datetime.now().strftime('%H:%M:%S'),
                'new_data': df_combined,
                'gap_warning': gap_warning
            }

            logger.info(f"✓ {sheet_name}: Success")

        except Exception as e:
            logger.error(f"✗ {endpoint_key} failed: {e}")
            sync_results[endpoint_key] = {
                'status': 'error',
                'message': str(e)
            }

    # Write all sheets at once
    try:
        # Collect all sheets (updated + unchanged)
        all_sheets = {}

        for endpoint_key, sheet_name in SHEET_MAPPING.items():
            if endpoint_key in sync_results and sync_results[endpoint_key]['status'] == 'success':
                # Use updated data
                all_sheets[sheet_name] = sync_results[endpoint_key]['new_data']
                # Remove from results to avoid storing large dataframe
                del sync_results[endpoint_key]['new_data']
            else:
                # Keep existing data
                all_sheets[sheet_name] = pd.read_excel(source_file, sheet_name=sheet_name)

        # Write to Excel
        with pd.ExcelWriter(source_file, engine='openpyxl') as writer:
            for sheet_name, df in all_sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)

        logger.info(f"\n✓ File updated successfully: {source_file}")
        logger.info(f"  Backup: {backup_file}")

    except Exception as e:
        logger.error(f"\n✗ Failed to write Excel: {e}")
        # Restore from backup
        shutil.copy2(backup_file, source_file)
        logger.info("✓ Restored from backup")

        # Mark all as error
        for key in sync_results:
            if sync_results[key]['status'] == 'success':
                sync_results[key]['status'] = 'error'
                sync_results[key]['message'] = f'Write failed: {e}'

    return sync_results
