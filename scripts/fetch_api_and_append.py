"""
Fetch API Data and Append to source-data.xlsx
==============================================

Production script untuk:
1. Fetch data dari 4 API endpoints (Korporasi, PTMN, Asing, Individu)
2. Transform ke format WIDE (menggunakan CODE_TO_COLUMN mapping)
3. Append row baru ke data/raw/source-data.xlsx

Usage:
    python scripts/fetch_api_and_append.py

Author: Data Processing Team
Date: 2025-12-12
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import logging
import shutil

# Import from ETL modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from etl.api_client import fetch_api_data, transform_api_to_wide
from config import SHEET_MAPPING

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_and_append_to_source():
    """
    Fetch data dari API dan append ke data/raw/source-data.xlsx
    """
    print("\n" + "="*70)
    print("FETCH API DATA AND APPEND TO SOURCE-DATA.XLSX")
    print("="*70)

    # File paths
    source_file = Path('data/raw/source-data.xlsx')
    backup_dir = Path('data/raw/backup')
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Check if source file exists
    if not source_file.exists():
        logger.error(f"✗ Source file not found: {source_file}")
        logger.info("  Please place source-data.xlsx in data/raw/ directory")
        return None

    # Create backup
    backup_file = backup_dir / f'source-data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    logger.info(f"Creating backup: {backup_file}")
    shutil.copy2(source_file, backup_file)
    logger.info(f"✓ Backup created")

    # Fetch data from all API endpoints
    logger.info(f"\n{'='*70}")
    logger.info("FETCHING DATA FROM API")
    logger.info(f"{'='*70}")

    new_data = {}

    for endpoint_key, sheet_name in SHEET_MAPPING.items():
        try:
            logger.info(f"\n{'-'*70}")
            logger.info(f"Fetching {endpoint_key.upper()} ({sheet_name})")
            logger.info(f"{'-'*70}")

            # Fetch from API (LONG format)
            df_long = fetch_api_data(endpoint_key)

            # Transform to WIDE format
            df_wide = transform_api_to_wide(df_long)

            # Convert column names from x1-x47 to 1-47 (integers)
            # api_client returns columns as 'x1', 'x2', etc.
            # Excel expects integer columns 1, 2, 3, etc.
            column_mapping = {f'x{i}': i for i in range(1, 48)}
            df_wide = df_wide.rename(columns=column_mapping)

            # Normalize datetime to midnight (for consistent comparison)
            # Keep as datetime64[ns] but set time to 00:00:00
            df_wide[1] = pd.to_datetime(df_wide[1]).dt.normalize()

            logger.info(f"✓ Data ready: {df_wide.shape}")
            logger.info(f"  Date: {df_wide[1].iloc[0].strftime('%Y-%m-%d')}")
            logger.info(f"  Total: {df_wide[43].iloc[0]:.2f}")

            new_data[sheet_name] = df_wide

        except Exception as e:
            logger.error(f"✗ Failed to fetch {endpoint_key}: {e}")
            import traceback
            traceback.print_exc()
            new_data[sheet_name] = None

    # Check if any data was fetched
    if not any(df is not None for df in new_data.values()):
        logger.error("\n✗ No data fetched from API - aborting")
        return None

    # Append to Excel
    logger.info(f"\n{'='*70}")
    logger.info("APPENDING TO source-data.xlsx")
    logger.info(f"{'='*70}")

    try:
        # Read all sheets first, combine with new data
        all_sheets = {}

        for sheet_name, df_new in new_data.items():
            logger.info(f"\n{sheet_name}:")

            # Read existing data from sheet
            df_existing = pd.read_excel(source_file, sheet_name=sheet_name)
            logger.info(f"  Existing rows: {len(df_existing)}")

            # Normalize existing date column for comparison
            df_existing.iloc[:, 0] = pd.to_datetime(df_existing.iloc[:, 0]).dt.normalize()
            logger.info(f"  Last date: {df_existing.iloc[-1, 0].strftime('%Y-%m-%d')}")

            if df_new is None:
                logger.warning(f"  ⚠️  No new data - keeping original")
                all_sheets[sheet_name] = df_existing
                continue

            logger.info(f"  New rows: {len(df_new)}")
            logger.info(f"  New date: {df_new[1].iloc[0].strftime('%Y-%m-%d')}")

            # Check for duplicate date (normalize both for comparison)
            last_date = pd.to_datetime(df_existing.iloc[-1, 0]).normalize()
            new_date = pd.to_datetime(df_new[1].iloc[0]).normalize()

            if new_date <= last_date:
                logger.warning(f"  ⚠️  Date {new_date.strftime('%Y-%m-%d')} is not newer than last date {last_date.strftime('%Y-%m-%d')} - skipping {sheet_name}")
                all_sheets[sheet_name] = df_existing
                continue

            # Ensure column alignment
            if list(df_existing.columns) != list(df_new.columns):
                logger.warning(f"  ⚠️  Column mismatch - fixing...")
                logger.debug(f"    Existing: {list(df_existing.columns)[:5]}...")
                logger.debug(f"    New: {list(df_new.columns)[:5]}...")
                # Ensure new data has same column names as existing
                df_new.columns = df_existing.columns

            # Append new data
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)

            # Ensure column 2 is always 0 (not NaN) - this column is always empty/zero
            df_combined.iloc[:, 1] = df_combined.iloc[:, 1].fillna(0.0)

            logger.info(f"  Combined rows: {len(df_combined)}")

            all_sheets[sheet_name] = df_combined
            logger.info(f"✓ Prepared {sheet_name}")

        # Write all sheets at once (more reliable than mode='a')
        logger.info(f"\nWriting all sheets to {source_file}...")
        with pd.ExcelWriter(source_file, engine='openpyxl') as writer:
            for sheet_name, df in all_sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                logger.info(f"  ✓ Wrote {sheet_name}: {len(df)} rows")

        logger.info(f"\n✓ source-data.xlsx updated successfully")
        logger.info(f"  File size: {source_file.stat().st_size / 1024:.2f} KB")
        logger.info(f"  Backup: {backup_file}")

        # Summary
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"\nFile: {source_file}")
        print(f"Backup: {backup_file}")
        print(f"\nData appended:")

        for sheet_name in SHEET_MAPPING.values():
            df = pd.read_excel(source_file, sheet_name=sheet_name)
            print(f"\n  {sheet_name}:")
            print(f"    Total rows: {len(df)}")
            print(f"    Last date: {df.iloc[-1, 0]}")
            print(f"    Last total: {df.iloc[-1, 42]:.2f}")

        print("\n" + "="*70)
        print("✓ COMPLETED SUCCESSFULLY")
        print("="*70)

        return source_file

    except Exception as e:
        logger.error(f"\n✗ Failed to append data: {e}")
        import traceback
        traceback.print_exc()

        # Restore from backup
        logger.info(f"\nRestoring from backup...")
        shutil.copy2(backup_file, source_file)
        logger.info(f"✓ File restored from backup")

        return None


if __name__ == "__main__":
    print("\n" + "="*70)
    print("PRODUCTION: Fetch API and Append to source-data.xlsx")
    print("="*70)
    print("\nThis script will:")
    print("  1. Fetch data from 4 API endpoints")
    print("  2. Create backup of source-data.xlsx")
    print("  3. Append new data to source-data.xlsx")
    print("\n" + "="*70)

    result = fetch_and_append_to_source()

    if result:
        print(f"\n✅ SUCCESS: Data appended to {result}")
    else:
        print("\n❌ FAILED: Could not append data")
        print("Check the logs above for details")
