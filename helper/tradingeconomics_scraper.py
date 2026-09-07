"""
Trading Economics Auto-Complete: Scrape + Sentiment
====================================================

Google Colab Script - Copy Paste ke 1 Cell

Workflow:
1. Upload file existing (opsional)
2. Run this script
3. Download hasil dengan tanggal: trading_economics_YYYY-MM-DD.xlsx

Features:
- Auto-detect gap (scraping + sentiment)
- Filter: United States & Indonesia only
- Sentiment: FinBERT (ProsusAI/finbert) - Analyzed from TITLE ONLY
- Combine + Dedup + Progress bars (tqdm)

Output:
- File Excel dengan tanggal (trading_economics_2025-11-21.xlsx)
- Hanya data US & Indonesia
- Semua row dengan sentiment_label + sentiment_score

Author: Tim APUVA - Bank Indonesia
Date: 2025-11-21
"""

# ============================================================================
# STEP 1: Install dependencies (uncomment jika belum install)
# ============================================================================
# !pip install -q transformers torch pandas openpyxl requests tqdm sentencepiece

# ============================================================================
# STEP 2: Imports
# ============================================================================
import time
import random
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pathlib import Path
import pandas as pd
import requests
from requests.adapters import HTTPAdapter, Retry
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from tqdm.auto import tqdm

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://tradingeconomics.com/ws/stream.ashx"
BATCH_SIZE = 100
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://tradingeconomics.com/stream",
}
# ProsusAI/finbert's pipeline() already returns human-readable labels
# ('positive'/'negative'/'neutral') via the model's own id2label config, NOT
# generic 'LABEL_0'/'LABEL_1'/'LABEL_2'. The old LABEL_0/1/2-only mapping never
# matched, so LABEL_INDEX.get(label, 'neutral') silently fell through to the
# 'neutral' default for every single article regardless of the real prediction
# (confirmed: sentiment_score was always a real, varied confidence value, but
# sentiment_label was 100% 'neutral' even for clearly positive/negative titles).
# Keep the LABEL_N entries too in case a different checkpoint is swapped in later.
LABEL_INDEX = {
    'label_0': 'positive', 'label_1': 'neutral', 'label_2': 'negative',
    'positive': 'positive', 'negative': 'negative', 'neutral': 'neutral',
}

# Bump this whenever add_sentiment()'s labeling/scoring logic changes in a way
# that would give a different result for the SAME article (e.g. the LABEL_INDEX
# fix above). Every row is stamped with the version that produced it; rows
# stamped with an older version are treated as "needs retry" even if their
# score looks perfectly valid - so a future logic fix self-heals existing data
# on the next run instead of requiring someone to manually delete the raw file.
SENTIMENT_LOGIC_VERSION = 2

# Filter countries: US and Indonesia (case-insensitive)
TARGET_COUNTRIES = ['united states', 'indonesia']


# ============================================================================
# STEP 3: Helper Functions
# ============================================================================

def human_sleep(min_sec=1.2, max_sec=2.7):
    """Random sleep untuk mimic human behavior"""
    time.sleep(random.uniform(min_sec, max_sec))


def build_session():
    """Build requests session dengan retry mechanism"""
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update(HEADERS)
    return session


def fetch_batch(session, start, size=BATCH_SIZE):
    """Fetch 1 batch data dari Trading Economics API"""
    params = {"start": start, "size": size}
    for attempt in range(3):
        try:
            resp = session.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json() if isinstance(resp.json(), list) else []
        except Exception as e:
            if attempt == 2:
                logger.error(f"Failed to fetch batch {start}: {e}")
                return []
            time.sleep(2 * (attempt + 1))
    return []


def detect_gap(filename):
    """Detect gap dari file existing sampai H-1"""
    if not filename or not Path(filename).exists():
        logger.warning("⚠️ No existing file - will scrape 30 days")
        today = datetime.now().date()
        return (today - timedelta(days=29), today)

    try:
        df = pd.read_excel(filename)
        # Fix: Use format='ISO8601' or format='mixed' untuk handle berbagai format datetime
        df['date_parsed'] = pd.to_datetime(df['date'], format='mixed', errors='coerce')
        last_date = df['date_parsed'].max().date()
        h_minus_1 = datetime.now().date() - timedelta(days=1)

        logger.info(f"\n{'='*70}")
        logger.info(f"Gap Detection:")
        logger.info(f"  Last date in file: {last_date}")
        logger.info(f"  H-1 (target): {h_minus_1}")

        if last_date >= h_minus_1:
            logger.info(f"  ✓ Data sudah lengkap sampai H-1!")
            logger.info(f"{'='*70}")
            return None

        gap_days = (h_minus_1 - last_date).days
        logger.info(f"  ⚠️ Gap: {gap_days} hari ({last_date + timedelta(days=1)} → {h_minus_1})")
        logger.info(f"{'='*70}")
        return (last_date + timedelta(days=1), h_minus_1)

    except Exception as e:
        logger.error(f"Error reading file: {e}")
        today = datetime.now().date()
        return (today - timedelta(days=29), today)


def scrape_date_range(start_date, end_date):
    """Scrape data dari start_date sampai end_date"""
    logger.info(f"\n{'='*70}")
    logger.info(f"Scraping: {start_date} → {end_date}")
    logger.info(f"{'='*70}")

    session = build_session()
    all_items = []
    start_idx = 1
    batch_num = 1
    max_batches = 200

    pbar = tqdm(total=max_batches, desc="📦 Fetching batches", unit="batch")

    while batch_num <= max_batches:
        data = fetch_batch(session, start_idx, BATCH_SIZE)

        if not data:
            pbar.set_description(f"📦 Batch {batch_num} - Empty, stopping")
            break

        oldest_seen = None
        for item in data:
            try:
                item_date = pd.to_datetime(item['date']).date()
                if oldest_seen is None or item_date < oldest_seen:
                    oldest_seen = item_date
                if start_date <= item_date <= end_date:
                    all_items.append(item)
            except:
                continue

        pbar.set_description(f"📦 Batch {batch_num} - {len(all_items)} items collected")
        pbar.update(1)

        if oldest_seen and oldest_seen < start_date:
            pbar.set_description(f"📦 Reached target - {len(all_items)} items total")
            break

        human_sleep(1.5, 3.5)
        start_idx += BATCH_SIZE
        batch_num += 1

    pbar.close()
    logger.info(f"✓ Scraped {len(all_items)} items")
    return all_items


def filter_us_indonesia(df):
    """Filter hanya data United States dan Indonesia"""
    logger.info(f"\n{'='*70}")
    logger.info("Filtering countries...")
    logger.info(f"{'='*70}")

    before_count = len(df)

    # Case-insensitive filter
    df_filtered = df[df['country'].str.lower().isin(TARGET_COUNTRIES)].copy()

    after_count = len(df_filtered)
    removed = before_count - after_count

    logger.info(f"  Before filter: {before_count:,} rows")
    logger.info(f"  After filter: {after_count:,} rows")
    logger.info(f"  Removed: {removed:,} rows")

    # Show country distribution
    logger.info(f"\n  Country distribution:")
    country_counts = df_filtered['country'].value_counts()
    for country, count in country_counts.items():
        pct = count / after_count * 100
        logger.info(f"    {country}: {count:,} ({pct:.1f}%)")

    return df_filtered


def load_sentiment_model():
    """Load FinBERT sentiment model (financial sentiment)"""
    logger.info(f"\n{'='*70}")
    logger.info("Loading FinBERT sentiment model...")
    logger.info(f"  Model: ProsusAI/finbert (Financial sentiment)")
    logger.info(f"{'='*70}")

    pretrained = "ProsusAI/finbert"
    model = AutoModelForSequenceClassification.from_pretrained(pretrained)
    tokenizer = AutoTokenizer.from_pretrained(pretrained)

    logger.info("✓ FinBERT model loaded!")
    return pipeline("sentiment-analysis", model=model, tokenizer=tokenizer)


def add_sentiment(df, sentiment_pipeline):
    """
    Add sentiment untuk row yang belum ada.

    Returns (df, stats) - stats berisi hitungan sukses/gagal/title kosong,
    supaya caller bisa tahu kalau semua row jatuh ke fallback neutral/0.0
    (penyebab Sentiment_TradingEconomics harian jadi flat 0.5, lihat
    catatan di daily-aggregation step) alih-alih diam-diam dianggap sukses.
    """
    logger.info(f"\n{'='*70}")
    logger.info(f"Adding sentiment analysis...")
    logger.info(f"{'='*70}")

    if 'sentiment_label' not in df.columns:
        df['sentiment_label'] = None
        df['sentiment_score'] = None
    if 'sentiment_model_version' not in df.columns:
        df['sentiment_model_version'] = None

    # Count rows that need (re)processing:
    # - never processed (label/score null)
    # - score exactly 0.0 (fallback signature from a prior failed/empty-title attempt)
    # - stamped with an OLDER SENTIMENT_LOGIC_VERSION - i.e. processed before a
    #   labeling/scoring bugfix, so the stored result may be wrong even though
    #   it looks like a normal, valid value (this is what makes old data
    #   self-heal after a logic fix, instead of needing manual file deletion)
    needs_mask = (
        df['sentiment_label'].isna()
        | df['sentiment_score'].isna()
        | (df['sentiment_score'] == 0.0)
        | (df['sentiment_model_version'].fillna(0) != SENTIMENT_LOGIC_VERSION)
    )
    needs_sentiment = df[needs_mask]
    total_need = len(needs_sentiment)

    stats = {'success': 0, 'failed': 0, 'empty_title': 0, 'last_error': None}

    if total_need == 0:
        logger.info("✓ All rows already have sentiment (current logic version)!")
        return df, stats

    logger.info(f"  Processing {total_need:,} rows...")

    pbar = tqdm(total=len(df), desc="🤖 BERT sentiment", unit="row")

    processed = 0
    for idx, row in df.iterrows():
        # Skip hanya kalau sudah diproses versi logika SEKARANG dengan hasil valid
        if pd.notna(row.get('sentiment_label')) and pd.notna(row.get('sentiment_score')) \
                and row.get('sentiment_score') != 0.0 \
                and row.get('sentiment_model_version') == SENTIMENT_LOGIC_VERSION:
            pbar.update(1)
            continue

        # Use TITLE ONLY for sentiment analysis
        text = str(row.get('title', '')).strip()
        if text:
            try:
                result = sentiment_pipeline(text[:512])
                raw_label = str(result[0]['label']).strip().lower()
                df.at[idx, 'sentiment_label'] = LABEL_INDEX.get(raw_label, 'neutral')
                df.at[idx, 'sentiment_score'] = result[0]['score']
                stats['success'] += 1
            except Exception as e:
                df.at[idx, 'sentiment_label'] = 'neutral'
                df.at[idx, 'sentiment_score'] = 0.0
                stats['failed'] += 1
                stats['last_error'] = f"{type(e).__name__}: {e}"
                logger.error(f"  Sentiment inference failed for row {idx}: {stats['last_error']}")
        else:
            df.at[idx, 'sentiment_label'] = 'neutral'
            df.at[idx, 'sentiment_score'] = 0.0
            stats['empty_title'] += 1

        df.at[idx, 'sentiment_model_version'] = SENTIMENT_LOGIC_VERSION

        processed += 1
        pbar.set_description(f"🤖 BERT sentiment ({processed}/{total_need} processed)")
        pbar.update(1)

    pbar.close()
    logger.info(f"✓ Sentiment complete! Processed {total_need:,} rows "
                f"({stats['success']} sukses, {stats['failed']} gagal, {stats['empty_title']} judul kosong)")
    return df, stats


# ============================================================================
# STEP 4: Main Execution
# ============================================================================

def main(input_filename=None):
    """Main execution function"""

    logger.info("\n" + "#" * 70)
    logger.info("Trading Economics Auto-Complete")
    logger.info("#" * 70)

    # Step 1: Detect scraping gap
    gap_info = detect_gap(input_filename)

    # Step 2: Scrape jika ada gap
    if gap_info is None:
        logger.info("\n✓ Tidak ada scraping gap!")
        df_existing = pd.read_excel(input_filename) if input_filename else pd.DataFrame()
        df_scraped = pd.DataFrame()
    else:
        start_date, end_date = gap_info
        items = scrape_date_range(start_date, end_date)
        df_scraped = pd.DataFrame(items) if items else pd.DataFrame()
        df_existing = pd.read_excel(input_filename) if input_filename and Path(input_filename).exists() else pd.DataFrame()

    # Step 3: Combine data
    logger.info(f"\n{'='*70}")
    logger.info("Combining data...")
    logger.info(f"{'='*70}")

    if len(df_existing) > 0 and len(df_scraped) > 0:
        df = pd.concat([df_existing, df_scraped], ignore_index=True)
        df = df.drop_duplicates(subset=['ID'], keep='first')
        logger.info(f"  Existing: {len(df_existing):,} rows")
        logger.info(f"  Scraped: {len(df_scraped):,} rows")
        logger.info(f"  Combined: {len(df):,} rows (after dedup)")
    elif len(df_existing) > 0:
        df = df_existing
        logger.info(f"  Using existing: {len(df):,} rows")
    elif len(df_scraped) > 0:
        df = df_scraped
        logger.info(f"  Using scraped: {len(df):,} rows")
    else:
        raise Exception("❌ No data available!")

    # Step 3b: Filter US & Indonesia only
    df = filter_us_indonesia(df)

    if len(df) == 0:
        raise Exception("❌ No data after filtering US & Indonesia!")

    # Step 4: Check sentiment gap (score==0.0 = fallback, or an older logic version = needs retry too)
    has_cols = 'sentiment_label' in df.columns and 'sentiment_score' in df.columns
    if has_cols:
        version_col = df['sentiment_model_version'] if 'sentiment_model_version' in df.columns else pd.Series(0, index=df.index)
        missing = df[
            df['sentiment_label'].isna() | df['sentiment_score'].isna() | (df['sentiment_score'] == 0.0)
            | (version_col.fillna(0) != SENTIMENT_LOGIC_VERSION)
        ]
        logger.info(f"\n{'='*70}")
        logger.info(f"Sentiment Gap Check:")
        logger.info(f"  Total rows: {len(df):,}")
        logger.info(f"  Missing sentiment: {len(missing):,} rows")
        logger.info(f"{'='*70}")
    else:
        logger.info(f"\n{'='*70}")
        logger.info(f"Sentiment Gap Check:")
        logger.info(f"  No sentiment columns - will add for all {len(df):,} rows")
        logger.info(f"{'='*70}")

    # Step 5: Add sentiment
    if not has_cols or len(missing) > 0:
        sentiment_pipeline = load_sentiment_model()
        df, sentiment_stats = add_sentiment(df, sentiment_pipeline)
        if sentiment_stats['failed'] > 0:
            logger.warning(f"⚠️ {sentiment_stats['failed']} row gagal analisis sentimen "
                            f"(fallback ke neutral/0.0). Contoh error: {sentiment_stats['last_error']}")
    else:
        logger.info("\n✓ All rows already have sentiment - skip BERT")

    # Step 6: Save hasil dengan tanggal
    today_str = datetime.now().strftime('%Y-%m-%d')
    output_filename = f'trading_economics_{today_str}.xlsx'

    logger.info(f"\n{'='*70}")
    logger.info(f"Saving output...")
    logger.info(f"{'='*70}")

    # Reorder columns
    col_order = [
        'no', 'ID', 'date', 'title', 'description', 'url', 'author',
        'country', 'category', 'image', 'importance',
        'sentiment_label', 'sentiment_score', 'sentiment_model_version',
        'expiration', 'html', 'type'
    ]

    for col in col_order:
        if col not in df.columns:
            df[col] = None

    df = df[col_order]
    df['no'] = range(1, len(df) + 1)

    df.to_excel(output_filename, sheet_name='stream_data', index=False)

    logger.info(f"\n" + "=" * 70)
    logger.info(f"✅ File 1: Full Data Saved!")
    logger.info(f"=" * 70)
    logger.info(f"  Output file: {output_filename}")
    logger.info(f"  Total rows: {len(df):,}")
    logger.info(f"  Date range: {df['date'].min()} → {df['date'].max()}")
    logger.info(f"  Sentiment: All rows complete")
    logger.info(f"=" * 70)

    # Sentiment distribution
    logger.info(f"\nSentiment Distribution:")
    sent_counts = df['sentiment_label'].value_counts()
    for label, count in sent_counts.items():
        pct = count / len(df) * 100
        logger.info(f"  {label:8s}: {count:6,} ({pct:5.1f}%)")

    # Step 7: Generate external_features format (daily aggregation)
    logger.info(f"\n{'='*70}")
    logger.info(f"Generating external_features format...")
    logger.info(f"{'='*70}")

    # Convert sentiment to numeric score
    # positive = 1.0, neutral = 0.5, negative = 0.0
    sentiment_map = {'positive': 1.0, 'neutral': 0.5, 'negative': 0.0}
    df['sentiment_numeric'] = df['sentiment_label'].map(sentiment_map)

    # Parse date to date only (remove time) - handle mixed datetime formats
    df['date_only'] = pd.to_datetime(df['date'], format='mixed', errors='coerce').dt.date

    # Daily aggregation with multiple metrics
    daily_agg = df.groupby('date_only').agg({
        'ID': 'count',  # Count news items
        'sentiment_numeric': lambda x: (x * df.loc[x.index, 'sentiment_score']).sum() / df.loc[x.index, 'sentiment_score'].sum()
        if df.loc[x.index, 'sentiment_score'].sum() > 0 else 0.5  # Weighted average
    }).reset_index()

    daily_agg.columns = ['Tanggal', 'News_Count', 'Sentiment_TradingEconomics']

    # Convert Tanggal to datetime
    daily_agg['Tanggal'] = pd.to_datetime(daily_agg['Tanggal'])

    # Sort by date
    daily_agg = daily_agg.sort_values('Tanggal').reset_index(drop=True)

    # Fill missing dates with 0 (weekends/holidays)
    logger.info(f"\n  Filling missing dates...")
    date_range_complete = pd.date_range(
        start=daily_agg['Tanggal'].min(),
        end=daily_agg['Tanggal'].max(),
        freq='D'
    )

    df_complete = pd.DataFrame({'Tanggal': date_range_complete})
    daily_agg = df_complete.merge(daily_agg, on='Tanggal', how='left')

    # Fill missing values with 0
    daily_agg['News_Count'] = daily_agg['News_Count'].fillna(0).astype(int)
    daily_agg['Sentiment_TradingEconomics'] = daily_agg['Sentiment_TradingEconomics'].fillna(0.0)

    missing_filled = len(date_range_complete) - len(daily_agg[daily_agg['News_Count'] > 0])
    logger.info(f"  ✓ Filled {missing_filled} missing dates with 0 (weekends/holidays)")

    logger.info(f"\n  Daily records: {len(daily_agg):,} days (complete)")
    logger.info(f"  Date range: {daily_agg['Tanggal'].min().date()} → {daily_agg['Tanggal'].max().date()}")
    logger.info(f"  News count range: {daily_agg['News_Count'].min():.0f} - {daily_agg['News_Count'].max():.0f} per day")
    logger.info(f"  Average news per day: {daily_agg['News_Count'].mean():.1f}")
    logger.info(f"  Sentiment range: {daily_agg['Sentiment_TradingEconomics'].min():.3f} - {daily_agg['Sentiment_TradingEconomics'].max():.3f}")
    logger.info(f"  Average sentiment: {daily_agg['Sentiment_TradingEconomics'].mean():.3f}")

    # Save external_features format
    external_features_filename = f'external_features_sentiment_{today_str}.xlsx'
    daily_agg.to_excel(external_features_filename, index=False)

    logger.info(f"\n" + "=" * 70)
    logger.info(f"✅ File 2: External Features Saved!")
    logger.info(f"=" * 70)
    logger.info(f"  Output file: {external_features_filename}")
    logger.info(f"  Format: Ready to merge with external_features.xlsx")
    logger.info(f"  Columns: Tanggal, News_Count, Sentiment_TradingEconomics")
    logger.info(f"=" * 70)

    print(f"\n✅ Files saved:")
    print(f"   1. {output_filename} (full data)")
    print(f"   2. {external_features_filename} (daily sentiment for forecasting)")
    print(f"\n💡 Next time:")
    print(f"   1. Upload: {output_filename}")
    print(f"   2. Run script lagi")
    print(f"   3. Download: trading_economics_<tanggal-besok>.xlsx + external_features_sentiment_<tanggal-besok>.xlsx")

    return output_filename, external_features_filename


# ============================================================================
# STEP 4b: Dashboard Integration (persistent files, merge into external_features.xlsx)
# ============================================================================
# Dipakai oleh pages/2_Fitur_Eksternal.py untuk menjalankan scraping ini langsung
# dari dashboard, bukan manual di Google Colab. Bedanya dengan main() di atas:
# - Raw stream disimpan di path TETAP (bukan nama file bertanggal) supaya
#   detect_gap() bisa jalan incremental antar run.
# - Hasil agregasi harian di-MERGE ke data/external_features.xlsx berdasarkan
#   tanggal (bukan file terpisah yang perlu di-copy manual).

import shutil


def merge_daily_sentiment_into_external_features(daily_agg, external_features_path):
    """
    Merge kolom News_Count & Sentiment_TradingEconomics (hasil agregasi harian)
    ke data/external_features.xlsx berdasarkan Tanggal - menimpa kolom lama
    dengan nama sama (kalau ada) tapi tidak menyentuh kolom fitur lain
    (Oil_Price, USD_IDR, dll).
    """
    external_features_path = Path(external_features_path)

    if external_features_path.exists():
        existing = pd.read_excel(external_features_path)
        existing['Tanggal'] = pd.to_datetime(existing['Tanggal'])
    else:
        existing = pd.DataFrame({'Tanggal': pd.Series(dtype='datetime64[ns]')})

    for col in ['News_Count', 'Sentiment_TradingEconomics']:
        if col in existing.columns:
            existing = existing.drop(columns=[col])

    merged = existing.merge(
        daily_agg[['Tanggal', 'News_Count', 'Sentiment_TradingEconomics']],
        on='Tanggal', how='outer'
    )
    return merged.sort_values('Tanggal').reset_index(drop=True)


def run_scrape_and_update(
    raw_stream_path='data/raw/tradingeconomics_stream.xlsx',
    external_features_path='data/external_features.xlsx',
    backfill_start_date=None,
):
    """
    Orkestrasi penuh untuk dipanggil dari dashboard: deteksi gap -> scrape ->
    filter US/Indonesia -> sentiment (FinBERT) -> agregasi harian -> merge ke
    data/external_features.xlsx (dengan backup otomatis file lama).

    Parameters
    ----------
    backfill_start_date : date, optional
        Kalau diisi, PAKSA scrape dari tanggal ini sampai H-1, mengabaikan
        gap-detection normal (yang cuma isi selisih sejak data terakhir).
        Dipakai untuk mengisi histori jauh ke belakang (mis. sampai 2019
        untuk kebutuhan model ML). HATI-HATI: rentang panjang = banyak
        batch scraping + banyak inferensi FinBERT, bisa makan waktu lama
        (puluhan menit sampai berjam-jam tergantung volume berita). Kalau
        dijalankan lewat tombol di web, ini berisiko timeout di nginx/browser
        walau proses di server tetap lanjut - untuk backfill panjang lebih
        aman dijalankan langsung di server (SSH), bukan lewat tombol.

    Returns dict ringkasan hasil (raw_rows, daily_rows, date_range, merged_rows).
    Raises Exception kalau tidak ada data sama sekali (baru & lama).
    """
    raw_stream_path = Path(raw_stream_path)
    raw_stream_path.parent.mkdir(parents=True, exist_ok=True)

    if backfill_start_date is not None:
        gap_info = (backfill_start_date, datetime.now().date() - timedelta(days=1))
    else:
        gap_info = detect_gap(str(raw_stream_path) if raw_stream_path.exists() else None)

    if gap_info is None:
        df_existing = pd.read_excel(raw_stream_path)
        df_scraped = pd.DataFrame()
        scrape_note = "Data sudah lengkap sampai H-1, tidak ada scraping baru."
    else:
        start_date, end_date = gap_info
        items = scrape_date_range(start_date, end_date)
        df_scraped = pd.DataFrame(items) if items else pd.DataFrame()
        df_existing = pd.read_excel(raw_stream_path) if raw_stream_path.exists() else pd.DataFrame()
        if len(df_scraped) == 0:
            scrape_note = (
                f"⚠️ 0 berita berhasil di-scrape untuk rentang {start_date} s/d {end_date}. "
                f"Kemungkinan server tidak bisa akses tradingeconomics.com (cek firewall/koneksi)."
            )
        else:
            scrape_note = f"{len(df_scraped)} berita baru di-scrape ({start_date} s/d {end_date})."

    scraped_count = len(df_scraped)

    if len(df_existing) == 0 and len(df_scraped) == 0:
        raise Exception("Tidak ada data baru (scraping kosong) maupun data lama. " + scrape_note)

    if len(df_existing) > 0 and len(df_scraped) > 0:
        df = pd.concat([df_existing, df_scraped], ignore_index=True)
        df = df.drop_duplicates(subset=['ID'], keep='first')
    else:
        df = df_existing if len(df_existing) > 0 else df_scraped

    total_before_filter = len(df)
    df = filter_us_indonesia(df)
    filtered_count = len(df)
    if len(df) == 0:
        raise Exception("Tidak ada data tersisa setelah filter US & Indonesia.")

    # score==0.0 (fallback) atau versi logika lebih lama dari SENTIMENT_LOGIC_VERSION
    # (mis. baris yang sudah diproses sebelum bugfix label) - retry juga
    has_cols = 'sentiment_label' in df.columns and 'sentiment_score' in df.columns
    if has_cols:
        version_col = df['sentiment_model_version'] if 'sentiment_model_version' in df.columns else pd.Series(0, index=df.index)
        missing = df[
            df['sentiment_label'].isna() | df['sentiment_score'].isna() | (df['sentiment_score'] == 0.0)
            | (version_col.fillna(0) != SENTIMENT_LOGIC_VERSION)
        ]
    else:
        missing = df
    sentiment_stats = {'success': 0, 'failed': 0, 'empty_title': 0, 'last_error': None}
    if not has_cols or len(missing) > 0:
        sentiment_pipeline = load_sentiment_model()
        df, sentiment_stats = add_sentiment(df, sentiment_pipeline)

    # Simpan raw stream (path tetap, dipakai lagi utk incremental run berikutnya)
    col_order = [
        'no', 'ID', 'date', 'title', 'description', 'url', 'author',
        'country', 'category', 'image', 'importance',
        'sentiment_label', 'sentiment_score', 'sentiment_model_version',
        'expiration', 'html', 'type'
    ]
    for col in col_order:
        if col not in df.columns:
            df[col] = None
    df_to_save = df[col_order].copy()
    df_to_save['no'] = range(1, len(df_to_save) + 1)
    df_to_save.to_excel(raw_stream_path, sheet_name='stream_data', index=False)

    # Agregasi harian (sama seperti main(), lihat Step 7 di atas)
    sentiment_map = {'positive': 1.0, 'neutral': 0.5, 'negative': 0.0}
    df['sentiment_numeric'] = df['sentiment_label'].map(sentiment_map)
    df['date_only'] = pd.to_datetime(df['date'], format='mixed', errors='coerce').dt.date

    daily_agg = df.groupby('date_only').agg({
        'ID': 'count',
        'sentiment_numeric': lambda x: (
            (x * df.loc[x.index, 'sentiment_score']).sum() / df.loc[x.index, 'sentiment_score'].sum()
            if df.loc[x.index, 'sentiment_score'].sum() > 0 else 0.5
        )
    }).reset_index()
    daily_agg.columns = ['Tanggal', 'News_Count', 'Sentiment_TradingEconomics']
    daily_agg['Tanggal'] = pd.to_datetime(daily_agg['Tanggal'])
    daily_agg = daily_agg.sort_values('Tanggal').reset_index(drop=True)

    # Hari dengan berita (News_Count > 0) tapi Sentiment_TradingEconomics persis 0.5
    # berarti SEMUA artikel hari itu gagal/kosong (lihat fallback di lambda di atas
    # dan di add_sentiment) - bukan sentimen netral yang wajar, tapi tanda analisis
    # sentimennya tidak jalan sama sekali untuk hari tersebut.
    flat_fallback_mask = (daily_agg['News_Count'] > 0) & (daily_agg['Sentiment_TradingEconomics'] == 0.5)
    flat_fallback_days = int(flat_fallback_mask.sum())

    date_range_complete = pd.date_range(
        start=daily_agg['Tanggal'].min(), end=daily_agg['Tanggal'].max(), freq='D'
    )
    df_complete = pd.DataFrame({'Tanggal': date_range_complete})
    daily_agg = df_complete.merge(daily_agg, on='Tanggal', how='left')
    daily_agg['News_Count'] = daily_agg['News_Count'].fillna(0).astype(int)
    daily_agg['Sentiment_TradingEconomics'] = daily_agg['Sentiment_TradingEconomics'].fillna(0.0)

    # Merge ke external_features.xlsx (backup dulu file lama)
    external_features_path = Path(external_features_path)
    if external_features_path.exists():
        backup_dir = external_features_path.parent / 'backup'
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / f"external_features_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        shutil.copy2(external_features_path, backup_file)

    merged = merge_daily_sentiment_into_external_features(daily_agg, external_features_path)
    merged.to_excel(external_features_path, index=False)

    return {
        'scrape_note': scrape_note,
        'scraped_count': scraped_count,
        'total_before_filter': total_before_filter,
        'filtered_count': filtered_count,
        'sentiment_stats': sentiment_stats,
        'flat_fallback_days': flat_fallback_days,
        'raw_rows': len(df),
        'daily_rows': len(daily_agg),
        'date_start': daily_agg['Tanggal'].min(),
        'date_end': daily_agg['Tanggal'].max(),
        'merged_rows': len(merged),
    }


# ============================================================================
# STEP 5: Upload File & Run
# ============================================================================

if __name__ == "__main__":
    # Untuk Google Colab - upload file
    try:
        from google.colab import files

        print("=" * 70)
        print("Upload file Excel existing (opsional):")
        print("- Skip jika belum punya data (scrape 30 hari)")
        print("- Upload jika sudah ada data (auto-detect gap)")
        print("=" * 70)

        uploaded = files.upload()

        if uploaded:
            input_filename = list(uploaded.keys())[0]
            print(f"\n✓ File uploaded: {input_filename}\n")
        else:
            print("\n⚠️ No file uploaded - will scrape 30 days\n")
            input_filename = None

    except ImportError:
        # Jika bukan di Colab, bisa set manual
        print("Not in Google Colab - set input_filename manually")
        input_filename = "tradingeconomics_stream_wsV1.xlsx"  # Edit ini

    # Run main
    output_file, external_features_file = main(input_filename)

    # Download hasil (Colab only)
    try:
        from google.colab import files
        print(f"\n📥 Downloading files...")
        print(f"  1. {output_file}")
        files.download(output_file)
        print(f"  2. {external_features_file}")
        files.download(external_features_file)
        print("\n✅ Download complete! (2 files)")
    except ImportError:
        print(f"✅ Files saved locally:")
        print(f"  1. {output_file}")
        print(f"  2. {external_features_file}")
