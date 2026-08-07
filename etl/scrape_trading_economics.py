"""
Trading Economics Data Scraper
================================

Script untuk scraping data ekonomi dari Trading Economics dan mengintegrasikannya
dengan external features dashboard.

Features:
- Scrape USD/IDR, Oil Price, Gold Price, US Treasury 10Y
- Update incremental (hanya data baru)
- Error handling dan retry mechanism
- Logging detail untuk monitoring

Usage:
    python etl/scrape_trading_economics.py
    python etl/scrape_trading_economics.py --date 2025-11-19
    python etl/scrape_trading_economics.py --backfill --start-date 2024-01-01

Author: Tim APUVA - Bank Indonesia
Date: 2025-11-19
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import time
import argparse
from openpyxl import load_workbook
import warnings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://tradingeconomics.com"
EXTERNAL_FEATURES_FILE = "data/external_features.xlsx"
SHEET_NAME = "External_Features"

# Trading Economics indicators
INDICATORS = {
    'USD_IDR': {
        'url': f'{BASE_URL}/indonesia/currency',
        'selector': '.table-responsive',  # Example - needs verification
        'column_name': 'USD_IDR'
    },
    'Oil_Price_Brent': {
        'url': f'{BASE_URL}/commodity/brent',
        'selector': '.table-responsive',
        'column_name': 'Oil_Price_Brent'
    },
    'Gold_Price': {
        'url': f'{BASE_URL}/commodity/gold',
        'selector': '.table-responsive',
        'column_name': 'Gold_Price'
    },
    'US_Treasury_10Y': {
        'url': f'{BASE_URL}/united-states/government-bond-yield',
        'selector': '.table-responsive',
        'column_name': 'US_Treasury_10Y'
    }
}

# Request headers to mimic browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}


class TradingEconomicsScraper:
    """Scraper for Trading Economics data"""

    def __init__(self, retry_count: int = 3, retry_delay: int = 5):
        """
        Initialize scraper.

        Parameters:
        -----------
        retry_count : int
            Number of retries on failure
        retry_delay : int
            Delay between retries (seconds)
        """
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch HTML page with retry mechanism.

        Parameters:
        -----------
        url : str
            URL to fetch

        Returns:
        --------
        html : str or None
            HTML content if successful, None otherwise
        """
        for attempt in range(self.retry_count):
            try:
                logger.info(f"Fetching: {url} (attempt {attempt + 1}/{self.retry_count})")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                logger.info(f"✓ Successfully fetched (status {response.status_code})")
                return response.text

            except requests.exceptions.Timeout:
                logger.warning(f"⚠ Timeout on attempt {attempt + 1}")
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay)
                    continue
                logger.error("✗ Max retries reached - timeout")
                return None

            except requests.exceptions.RequestException as e:
                logger.warning(f"⚠ Request error on attempt {attempt + 1}: {e}")
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay)
                    continue
                logger.error(f"✗ Max retries reached - {e}")
                return None

        return None

    def parse_indicator_data(self, html: str, indicator_name: str) -> Optional[float]:
        """
        Parse indicator value from HTML.

        CATATAN: Ini adalah template - selector perlu disesuaikan dengan
        struktur HTML Trading Economics yang sebenarnya.

        Parameters:
        -----------
        html : str
            HTML content
        indicator_name : str
            Name of indicator (for logging)

        Returns:
        --------
        value : float or None
            Indicator value if found, None otherwise
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # TODO: Update selector berdasarkan struktur HTML Trading Economics
            # Contoh selector (perlu diverifikasi):

            # Option 1: Cari di tabel dengan class tertentu
            value_elem = soup.select_one('#ctl00_ContentPlaceHolder1_ctl00_ctl02_Panel1 td')

            # Option 2: Cari di span dengan id tertentu
            # value_elem = soup.select_one('#p')

            # Option 3: Cari berdasarkan pattern text
            # value_elem = soup.find('td', text=re.compile(r'Previous'))

            if value_elem:
                value_text = value_elem.get_text().strip()
                # Clean text: remove commas, currency symbols, etc
                value_text = value_text.replace(',', '').replace('$', '').replace('%', '')
                value = float(value_text)
                logger.info(f"  ✓ Parsed {indicator_name}: {value}")
                return value
            else:
                logger.warning(f"  ⚠ Could not find value element for {indicator_name}")
                return None

        except Exception as e:
            logger.error(f"  ✗ Error parsing {indicator_name}: {e}")
            return None

    def scrape_indicator(self, indicator_key: str, target_date: datetime) -> Optional[float]:
        """
        Scrape single indicator for specific date.

        Parameters:
        -----------
        indicator_key : str
            Key from INDICATORS dict
        target_date : datetime
            Date to scrape for

        Returns:
        --------
        value : float or None
            Indicator value
        """
        config = INDICATORS[indicator_key]
        url = config['url']

        logger.info(f"\nScraping {config['column_name']} for {target_date.date()}...")

        # Fetch page
        html = self.fetch_page(url)
        if not html:
            return None

        # Parse value
        value = self.parse_indicator_data(html, config['column_name'])

        # Add small delay to be respectful to server
        time.sleep(1)

        return value

    def scrape_all_indicators(self, target_date: datetime) -> Dict[str, float]:
        """
        Scrape all indicators for specific date.

        Parameters:
        -----------
        target_date : datetime
            Date to scrape for

        Returns:
        --------
        data : Dict[str, float]
            Dictionary of indicator values
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"Scraping all indicators for {target_date.date()}")
        logger.info(f"{'='*70}")

        data = {'Tanggal': target_date}

        for indicator_key in INDICATORS:
            value = self.scrape_indicator(indicator_key, target_date)
            column_name = INDICATORS[indicator_key]['column_name']
            data[column_name] = value

        # Summary
        logger.info(f"\n{'='*70}")
        logger.info("Scraping Summary:")
        successful = sum(1 for k, v in data.items() if k != 'Tanggal' and v is not None)
        total = len(INDICATORS)
        logger.info(f"  Success: {successful}/{total} indicators")
        logger.info(f"{'='*70}")

        return data


def load_existing_features() -> pd.DataFrame:
    """
    Load existing external features from Excel.

    Returns:
    --------
    df : pd.DataFrame
        Existing features, or empty DataFrame if file doesn't exist
    """
    file_path = Path(EXTERNAL_FEATURES_FILE)

    if not file_path.exists():
        logger.warning(f"⚠ External features file not found: {EXTERNAL_FEATURES_FILE}")
        logger.info("  → Will create new file")
        # Return empty DataFrame with expected columns
        columns = ['Tanggal', 'Sentiment_TradingEconomics'] + [
            INDICATORS[k]['column_name'] for k in INDICATORS
        ]
        return pd.DataFrame(columns=columns)

    try:
        df = pd.read_excel(EXTERNAL_FEATURES_FILE, sheet_name=SHEET_NAME)
        df['Tanggal'] = pd.to_datetime(df['Tanggal'])
        logger.info(f"✓ Loaded existing features: {len(df)} rows")
        logger.info(f"  Date range: {df['Tanggal'].min().date()} to {df['Tanggal'].max().date()}")
        return df
    except Exception as e:
        logger.error(f"✗ Error loading existing features: {e}")
        raise


def update_external_features(new_data: Dict[str, float], mode: str = 'append') -> None:
    """
    Update external features Excel file with new data.

    Parameters:
    -----------
    new_data : Dict[str, float]
        New data to add (including 'Tanggal' key)
    mode : str
        Update mode: 'append' (default) or 'update' (replace existing date)
    """
    logger.info(f"\n{'='*70}")
    logger.info(f"Updating external features file...")
    logger.info(f"{'='*70}")

    # Load existing data
    df_existing = load_existing_features()

    # Create DataFrame from new data
    df_new = pd.DataFrame([new_data])
    df_new['Tanggal'] = pd.to_datetime(df_new['Tanggal'])

    target_date = df_new['Tanggal'].iloc[0]

    # Check if date already exists
    date_exists = target_date in df_existing['Tanggal'].values

    if date_exists:
        if mode == 'update':
            logger.info(f"  → Updating existing data for {target_date.date()}")
            # Remove old data for this date
            df_existing = df_existing[df_existing['Tanggal'] != target_date]
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        else:
            logger.warning(f"  ⚠ Data for {target_date.date()} already exists")
            logger.info(f"  → Skipping (use mode='update' to overwrite)")
            return
    else:
        logger.info(f"  → Appending new data for {target_date.date()}")
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)

    # Sort by date
    df_combined = df_combined.sort_values('Tanggal').reset_index(drop=True)

    # Ensure all expected columns exist
    expected_cols = ['Tanggal', 'Sentiment_TradingEconomics'] + [
        INDICATORS[k]['column_name'] for k in INDICATORS
    ]
    for col in expected_cols:
        if col not in df_combined.columns:
            df_combined[col] = np.nan

    # Reorder columns
    df_combined = df_combined[expected_cols]

    # Save to Excel
    try:
        # Create directory if doesn't exist
        Path(EXTERNAL_FEATURES_FILE).parent.mkdir(parents=True, exist_ok=True)

        # Save with openpyxl
        with pd.ExcelWriter(EXTERNAL_FEATURES_FILE, engine='openpyxl') as writer:
            df_combined.to_excel(writer, sheet_name=SHEET_NAME, index=False)

        logger.info(f"✓ Successfully updated: {EXTERNAL_FEATURES_FILE}")
        logger.info(f"  Total rows: {len(df_combined)}")
        logger.info(f"  Date range: {df_combined['Tanggal'].min().date()} to {df_combined['Tanggal'].max().date()}")

    except Exception as e:
        logger.error(f"✗ Failed to save Excel file: {e}")
        raise


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description='Scrape Trading Economics data and update external features'
    )
    parser.add_argument(
        '--date',
        type=str,
        help='Target date (YYYY-MM-DD). Default: today'
    )
    parser.add_argument(
        '--backfill',
        action='store_true',
        help='Backfill mode: scrape date range'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        help='Start date for backfill (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        help='End date for backfill (YYYY-MM-DD). Default: today'
    )
    parser.add_argument(
        '--mode',
        type=str,
        choices=['append', 'update'],
        default='append',
        help='Update mode: append (skip existing) or update (overwrite existing)'
    )

    args = parser.parse_args()

    # Determine target date(s)
    if args.backfill:
        if not args.start_date:
            logger.error("✗ --start-date required for backfill mode")
            return

        start_date = pd.to_datetime(args.start_date)
        end_date = pd.to_datetime(args.end_date) if args.end_date else pd.Timestamp.now()
        date_range = pd.date_range(start_date, end_date, freq='D')

        logger.info(f"Backfill mode: {start_date.date()} to {end_date.date()} ({len(date_range)} days)")
    else:
        target_date = pd.to_datetime(args.date) if args.date else pd.Timestamp.now()
        date_range = [target_date]
        logger.info(f"Single date mode: {target_date.date()}")

    # Initialize scraper
    scraper = TradingEconomicsScraper()

    # Scrape each date
    for target_date in date_range:
        logger.info(f"\n{'#'*70}")
        logger.info(f"Processing: {target_date.date()}")
        logger.info(f"{'#'*70}")

        # Scrape data
        data = scraper.scrape_all_indicators(target_date)

        # Check if we got any data
        scraped_values = [v for k, v in data.items() if k != 'Tanggal' and v is not None]
        if not scraped_values:
            logger.warning(f"⚠ No data scraped for {target_date.date()} - skipping update")
            continue

        # Update external features
        try:
            update_external_features(data, mode=args.mode)
        except Exception as e:
            logger.error(f"✗ Failed to update features for {target_date.date()}: {e}")
            continue

        # Add delay between dates in backfill mode
        if args.backfill and target_date != date_range[-1]:
            logger.info("  Waiting 5 seconds before next date...")
            time.sleep(5)

    logger.info(f"\n{'='*70}")
    logger.info("✓ Scraping completed!")
    logger.info(f"{'='*70}")


if __name__ == "__main__":
    main()
