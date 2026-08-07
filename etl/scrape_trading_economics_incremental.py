"""
Trading Economics Stream - Incremental Scraper
===============================================

Script untuk scraping data Trading Economics stream secara incremental.
Melengkapi data yang sudah ada dari data/raw/trading_economics/stream_data.xlsx

Features:
- Auto-detect gap: scrape dari tanggal terakhir di Excel sampai H-1
- Append ke file existing
- Check duplicate berdasarkan ID
- Logging detail

Logika:
- Cek tanggal terakhir di Excel (misal: 2025-11-11)
- Hari ini: 2025-11-19
- H-1: 2025-11-18
- Gap: 2025-11-12 s/d 2025-11-18 (7 hari)
- Scrape 7 hari tersebut dan append ke Excel

Usage:
    # Mode auto: detect gap dan lengkapi sampai H-1
    python etl/scrape_trading_economics_incremental.py

    # Mode manual: scrape tanggal spesifik
    python etl/scrape_trading_economics_incremental.py --date 2025-11-18

    # Mode backfill: scrape N hari terakhir (force)
    python etl/scrape_trading_economics_incremental.py --backfill --days 7

Author: Tim APUVA - Bank Indonesia
Date: 2025-11-19
"""

import time
import random
import json
import argparse
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
import requests
from requests.adapters import HTTPAdapter, Retry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://tradingeconomics.com/ws/stream.ashx"
STREAM_FILE = "data/raw/trading_economics/stream_data.xlsx"
SHEET_NAME = "ws_stream"
BATCH_SIZE = 100

# Headers
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://tradingeconomics.com/stream",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}


def human_sleep(min_sec: float = 1.2, max_sec: float = 2.7):
    """Sleep dengan durasi random untuk meniru behavior manusia"""
    time.sleep(random.uniform(min_sec, max_sec))


def build_session() -> requests.Session:
    """Build session dengan retry mechanism"""
    session = requests.Session()
    retries = Retry(
        total=5,
        connect=3,
        read=3,
        backoff_factor=1.5,
        status_forcelist=(405, 408, 409, 429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update(HEADERS)
    return session


def fetch_batch(
    session: requests.Session,
    start: int,
    size: int = BATCH_SIZE
) -> List[Dict[str, Any]]:
    """
    Fetch satu batch data dari Trading Economics stream API.

    Parameters:
    -----------
    session : requests.Session
        HTTP session
    start : int
        Start index
    size : int
        Batch size

    Returns:
    --------
    data : List[Dict]
        List of stream items
    """
    params = {"start": start, "size": size}
    attempts = 0

    while True:
        attempts += 1
        try:
            resp = session.get(BASE_URL, params=params, timeout=30)

            # Handle error status codes dengan retry
            if resp.status_code in (405, 409, 429, 500, 502, 503, 504):
                wait = min(20, 2 * attempts + random.uniform(0.5, 1.5))
                logger.warning(
                    f"  ⚠️ Status {resp.status_code} @ start={start} "
                    f"→ retry #{attempts} (tunggu {wait:.1f}s)"
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()

            # Parse JSON
            try:
                data = resp.json()
            except json.JSONDecodeError:
                data = json.loads(resp.text.strip())

            if not isinstance(data, list):
                logger.warning(f"  ⚠️ Response bukan list. Length={len(resp.text)}")
                return []

            return data

        except requests.RequestException as e:
            if attempts >= 6:
                logger.error(f"  ✗ Gagal permanent untuk start={start}: {e}")
                return []

            wait = min(20, 2 * attempts + random.uniform(0.5, 1.5))
            logger.warning(f"  ⚠️ Error '{e}' → retry #{attempts} dalam {wait:.1f}s")
            time.sleep(wait)


def fetch_until_date(
    session: requests.Session,
    target_date: datetime,
    max_batches: int = 50
) -> List[Dict[str, Any]]:
    """
    Fetch data sampai menemukan data dari target_date.

    Trading Economics stream diurut dari newest → oldest, jadi:
    - Start dari index 1 (newest)
    - Fetch batch-batch sampai ketemu data target_date
    - Stop kalau sudah lewat target_date

    Parameters:
    -----------
    session : requests.Session
        HTTP session
    target_date : datetime
        Target date to fetch
    max_batches : int
        Maximum batches to fetch (safety limit)

    Returns:
    --------
    results : List[Dict]
        All items from target_date
    """
    logger.info(f"\n{'='*70}")
    logger.info(f"Fetching data untuk tanggal: {target_date.date()}")
    logger.info(f"{'='*70}")

    results = []
    start = 1
    found_target = False
    passed_target = False

    for batch_num in range(max_batches):
        logger.info(f"📦 Batch {batch_num + 1}/{max_batches} | start={start}")

        data = fetch_batch(session, start, BATCH_SIZE)

        if not data:
            logger.warning("  ⛔ Batch kosong/gagal — stop")
            break

        # Parse date untuk setiap item
        for item in data:
            try:
                item_date = pd.to_datetime(item['date'])
                item_date_only = item_date.date()

                # Check apakah item dari target date
                if item_date_only == target_date.date():
                    results.append(item)
                    found_target = True
                elif item_date_only < target_date.date():
                    # Sudah lewat target date (karena urutan newest → oldest)
                    passed_target = True
                    break

            except Exception as e:
                logger.warning(f"  ⚠️ Error parsing date: {e}")
                continue

        # Stop conditions
        if passed_target:
            logger.info(f"  ✓ Sudah melewati target date — stop")
            break

        # Delay sebelum batch berikutnya
        human_sleep(1.5, 3.5)
        start += BATCH_SIZE

    # Summary
    logger.info(f"\n{'='*70}")
    logger.info(f"Hasil scraping untuk {target_date.date()}:")
    logger.info(f"  Total items: {len(results)}")
    logger.info(f"  Found target: {found_target}")
    logger.info(f"{'='*70}")

    return results


def load_existing_stream() -> pd.DataFrame:
    """
    Load existing stream data dari Excel.

    Returns:
    --------
    df : pd.DataFrame
        Existing stream data
    """
    file_path = Path(STREAM_FILE)

    if not file_path.exists():
        logger.warning(f"⚠️ File stream tidak ditemukan: {STREAM_FILE}")
        logger.info("  → Akan buat file baru")
        return pd.DataFrame(columns=[
            "no", "ID", "title", "description", "url", "author",
            "country", "category", "image", "importance",
            "date", "expiration", "html", "type"
        ])

    try:
        df = pd.read_excel(STREAM_FILE, sheet_name=SHEET_NAME)
        logger.info(f"✓ Loaded existing stream: {len(df)} rows")

        # Parse date
        df['date_parsed'] = pd.to_datetime(df['date'], errors='coerce')
        last_date = df['date_parsed'].max()

        logger.info(f"  Last date in file: {last_date.date() if pd.notna(last_date) else 'N/A'}")

        return df

    except Exception as e:
        logger.error(f"✗ Error loading stream: {e}")
        raise


def append_to_stream(new_items: List[Dict[str, Any]]) -> None:
    """
    Append new items ke existing stream file.

    Parameters:
    -----------
    new_items : List[Dict]
        New stream items to append
    """
    if not new_items:
        logger.info("  ℹ️ Tidak ada data baru untuk di-append")
        return

    logger.info(f"\n{'='*70}")
    logger.info(f"Updating stream file...")
    logger.info(f"{'='*70}")

    # Load existing
    df_existing = load_existing_stream()

    # Get existing IDs untuk check duplicate
    existing_ids = set(df_existing['ID'].dropna().astype(int).tolist())
    logger.info(f"  Existing IDs: {len(existing_ids)}")

    # Filter new items (skip duplicates)
    new_items_filtered = []
    duplicates = 0

    for item in new_items:
        item_id = item.get('ID')
        if item_id in existing_ids:
            duplicates += 1
            continue
        new_items_filtered.append(item)

    logger.info(f"  New items: {len(new_items)}")
    logger.info(f"  Duplicates (skipped): {duplicates}")
    logger.info(f"  To append: {len(new_items_filtered)}")

    if not new_items_filtered:
        logger.info("  ✓ Tidak ada data baru (semua duplicate)")
        return

    # Create DataFrame untuk new items
    df_new = pd.DataFrame(new_items_filtered)

    # Reorder columns untuk match existing
    expected_cols = [
        "no", "ID", "title", "description", "url", "author",
        "country", "category", "image", "importance",
        "date", "expiration", "html", "type"
    ]

    for col in expected_cols:
        if col not in df_new.columns:
            df_new[col] = None

    df_new = df_new[expected_cols]

    # Update nomor urut
    if len(df_existing) > 0:
        last_no = df_existing['no'].max()
        df_new['no'] = range(last_no + 1, last_no + 1 + len(df_new))
    else:
        df_new['no'] = range(1, len(df_new) + 1)

    # Combine
    df_combined = pd.concat([df_existing, df_new], ignore_index=True)

    # Remove parsed date column if exists
    if 'date_parsed' in df_combined.columns:
        df_combined = df_combined.drop(columns=['date_parsed'])

    # Save
    try:
        # Create directory if needed
        Path(STREAM_FILE).parent.mkdir(parents=True, exist_ok=True)

        # Save to Excel
        with pd.ExcelWriter(STREAM_FILE, engine='openpyxl') as writer:
            df_combined.to_excel(writer, sheet_name=SHEET_NAME, index=False)

        logger.info(f"✓ Stream updated: {STREAM_FILE}")
        logger.info(f"  Total rows: {len(df_combined)}")
        logger.info(f"  New rows added: {len(df_new)}")

    except Exception as e:
        logger.error(f"✗ Failed to save stream: {e}")
        raise


def get_missing_dates() -> List[datetime]:
    """
    Deteksi tanggal yang missing dari file Excel sampai H-1.

    Returns:
    --------
    missing_dates : List[datetime]
        List tanggal yang perlu di-scrape
    """
    # Load existing data
    df_existing = load_existing_stream()

    # Get last date in file
    if len(df_existing) == 0:
        logger.warning("⚠️ File kosong - tidak bisa deteksi gap")
        return []

    df_existing['date_parsed'] = pd.to_datetime(df_existing['date'], errors='coerce')
    last_date = df_existing['date_parsed'].max()

    if pd.isna(last_date):
        logger.warning("⚠️ Tidak bisa parse tanggal dari file")
        return []

    last_date_only = last_date.date()

    # Get H-1 (yesterday)
    today = pd.Timestamp.now().normalize()
    h_minus_1 = today - timedelta(days=1)
    h_minus_1_only = h_minus_1.date()

    logger.info(f"\n{'='*70}")
    logger.info(f"Gap Detection:")
    logger.info(f"  Tanggal terakhir di Excel: {last_date_only}")
    logger.info(f"  Hari ini: {today.date()}")
    logger.info(f"  H-1 (target): {h_minus_1_only}")

    # Calculate gap
    if last_date_only >= h_minus_1_only:
        logger.info(f"  ✓ Data sudah lengkap sampai H-1")
        logger.info(f"{'='*70}")
        return []

    # Generate missing dates (dari last_date + 1 sampai H-1)
    start_date = last_date_only + timedelta(days=1)
    missing_dates = []

    current = start_date
    while current <= h_minus_1_only:
        missing_dates.append(pd.Timestamp(current))
        current += timedelta(days=1)

    logger.info(f"  ⚠️ Gap detected: {len(missing_dates)} hari")
    logger.info(f"  Range: {start_date} s/d {h_minus_1_only}")
    logger.info(f"{'='*70}")

    return missing_dates


def main():
    """Main execution"""
    parser = argparse.ArgumentParser(
        description='Scrape Trading Economics stream - melengkapi gap sampai H-1'
    )
    parser.add_argument(
        '--date',
        type=str,
        help='Target date (YYYY-MM-DD). Override auto-detect mode'
    )
    parser.add_argument(
        '--backfill',
        action='store_true',
        help='Backfill mode: scrape last N days (force)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days to backfill. Default: 7'
    )

    args = parser.parse_args()

    # Determine target date(s)
    if args.date:
        # Manual mode: scrape tanggal spesifik
        target_dates = [pd.to_datetime(args.date)]
        logger.info(f"Mode: Manual - scrape tanggal {args.date}")
    elif args.backfill:
        # Backfill mode: scrape last N days (force)
        today = pd.Timestamp.now().normalize()
        target_dates = [today - timedelta(days=i) for i in range(1, args.days + 1)]
        target_dates.reverse()  # Sort oldest → newest
        logger.info(f"Mode: Backfill - scrape {args.days} hari terakhir (force)")
    else:
        # Auto mode: detect gap dan lengkapi sampai H-1
        logger.info(f"Mode: Auto - detect gap dan lengkapi sampai H-1")
        target_dates = get_missing_dates()

        if not target_dates:
            logger.info("\n✓ Tidak ada gap - data sudah lengkap!")
            return

    # Initialize session
    session = build_session()

    # Process each date
    for target_date in target_dates:
        logger.info(f"\n{'#'*70}")
        logger.info(f"Processing: {target_date.date()}")
        logger.info(f"{'#'*70}")

        # Fetch data
        items = fetch_until_date(session, target_date, max_batches=50)

        if not items:
            logger.warning(f"⚠️ Tidak ada data untuk {target_date.date()}")
            continue

        # Append to file
        try:
            append_to_stream(items)
        except Exception as e:
            logger.error(f"✗ Failed to append for {target_date.date()}: {e}")
            continue

    logger.info(f"\n{'='*70}")
    logger.info("✓ Scraping selesai!")
    logger.info(f"{'='*70}")


if __name__ == "__main__":
    main()
