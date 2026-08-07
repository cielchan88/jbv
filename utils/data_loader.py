"""
Data Loader with Auto ETL Detection

This module automatically checks if source data is newer than processed data,
and triggers ETL pipeline if needed.
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import os
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent.parent
SOURCE_FILE = BASE_DIR / "data" / "raw" / "source-data.xlsx"
PROCESSED_FILE = BASE_DIR / "data" / "processed" / "sdv-wide.csv"
# ETL_OUTPUT_FILE is the same as PROCESSED_FILE (sdv-wide.csv is the ETL output!)
ETL_OUTPUT_FILE = PROCESSED_FILE


def parse_children(children_value):
    """
    Parse Children column value (JSON string) to list.
    Handles both string and list types for compatibility.
    """
    if isinstance(children_value, str):
        try:
            return json.loads(children_value)
        except:
            return []
    elif isinstance(children_value, list):
        return children_value
    else:
        return []


def get_file_mtime(file_path):
    """Get file modification time"""
    try:
        return os.path.getmtime(file_path)
    except:
        return 0


def needs_etl_refresh():
    """
    Check if ETL needs to be run.

    Returns:
        bool: True if source is newer than processed or processed doesn't exist
    """
    if not PROCESSED_FILE.exists():
        return True

    if not SOURCE_FILE.exists():
        return False

    source_mtime = get_file_mtime(SOURCE_FILE)
    processed_mtime = get_file_mtime(PROCESSED_FILE)

    return source_mtime > processed_mtime


def run_etl_silent():
    """
    Run ETL pipeline silently in background.

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        from etl import run_pipeline

        # Suppress ETL logging output
        logging.getLogger('etl.pipeline').setLevel(logging.WARNING)

        # Run pipeline
        run_pipeline()

        return True, "✅ Data berhasil diupdate dari source-data.xlsx"

    except Exception as e:
        return False, f"❌ ETL gagal: {str(e)}"


@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_data_with_etl_check():
    """
    Load data with automatic ETL refresh detection.

    This function:
    1. Checks if source data is newer than processed data
    2. Runs ETL automatically if needed
    3. Shows notification to user
    4. Returns the processed data

    Returns:
        tuple: (df, metadata_cols, time_cols)
    """
    # Check if ETL is needed
    if needs_etl_refresh():
        with st.spinner('🔄 Mendeteksi data baru... Menjalankan ETL pipeline...'):
            success, message = run_etl_silent()

            if success:
                st.success(message, icon="✅")
            else:
                st.error(message, icon="❌")
                # Try to load existing data anyway

    # Load processed data
    try:
        df = pd.read_csv(PROCESSED_FILE)

        # Separate metadata and time series columns
        metadata_cols = ['Row_ID', 'Row_Label', 'Level']
        time_cols = [col for col in df.columns if col not in metadata_cols]

        # Build hierarchy from Row_ID structure
        def get_children(parent_id):
            """Get children of a parent Row_ID based on hierarchy"""
            # Special case: D has children A, B, C (top-level aggregation)
            if parent_id == 'D':
                return ['A', 'B', 'C']

            children = []
            for idx, row in df.iterrows():
                row_id = row['Row_ID']
                if row_id.startswith(parent_id + '.') and row_id != parent_id:
                    parent_dots = parent_id.count('.')
                    child_dots = row_id.count('.')
                    if child_dots == parent_dots + 1:
                        children.append(row_id)

            return children

        # Store Children as JSON strings to avoid caching issues with lists
        df['Children'] = df['Row_ID'].apply(lambda x: json.dumps(get_children(x)))

        return df, metadata_cols, time_cols

    except FileNotFoundError:
        st.error(f"❌ File data tidak ditemukan: {PROCESSED_FILE}")
        st.info("💡 Pastikan file source-data.xlsx ada di folder data/raw/")
        st.stop()

    except Exception as e:
        st.error(f"❌ Error loading data: {str(e)}")
        st.stop()


@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_etl_output():
    """
    Load ETL output data for Eksplorasi and Prediksi pages.

    This function loads the FINAL ETL-processed data (etl_output.csv),
    which has gone through:
    - Data cleaning (missing values, outliers)
    - Business logic aggregation
    - Quality validation

    This is the CORRECT data to use for analysis and forecasting,
    NOT the raw processed_sdv.csv!

    Returns:
        tuple: (df, metadata_cols, time_cols)
    """
    # Check if ETL output exists, if not try to generate it
    if not ETL_OUTPUT_FILE.exists():
        st.warning("⚠️ ETL output tidak ditemukan. Menjalankan ETL pipeline...")
        success, message = run_etl_silent()

        if not success:
            st.error(message)
            st.error("❌ Tidak dapat memuat data ETL. Pastikan ETL pipeline berjalan dengan benar.")
            st.stop()

    # Load ETL output
    try:
        df = pd.read_csv(ETL_OUTPUT_FILE)

        # Separate metadata and time series columns
        metadata_cols = ['Row_ID', 'Row_Label', 'Level']
        time_cols = [col for col in df.columns if col not in metadata_cols]

        # Build hierarchy from Row_ID structure
        def get_children(parent_id):
            """Get children of a parent Row_ID based on hierarchy"""
            # Special case: D has children A, B, C (top-level aggregation)
            if parent_id == 'D':
                return ['A', 'B', 'C']

            children = []
            for idx, row in df.iterrows():
                row_id = row['Row_ID']
                if row_id.startswith(parent_id + '.') and row_id != parent_id:
                    parent_dots = parent_id.count('.')
                    child_dots = row_id.count('.')
                    if child_dots == parent_dots + 1:
                        children.append(row_id)

            return children

        # Store Children as JSON strings to avoid caching issues with lists
        df['Children'] = df['Row_ID'].apply(lambda x: json.dumps(get_children(x)))

        return df, metadata_cols, time_cols

    except FileNotFoundError:
        st.error(f"❌ File ETL output tidak ditemukan: {ETL_OUTPUT_FILE}")
        st.info("💡 Jalankan ETL pipeline terlebih dahulu dari halaman ETL")
        st.stop()

    except Exception as e:
        st.error(f"❌ Error loading ETL output: {str(e)}")
        st.stop()
