"""
Forecast Version Management

Manages forecast versions with full metadata for tracking and audit.
Each forecast is saved as a version with:
- Timestamp
- Model configuration (per leaf node)
- Parameters used
- Features used
- Cross-series info
- etc.

Author: APUVA Team
Date: 2025-11-11
"""

import os
import json
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional


FORECAST_VERSIONS_DIR = "data/forecast_versions"


def ensure_versions_dir():
    """Ensure forecast versions directory exists"""
    os.makedirs(FORECAST_VERSIONS_DIR, exist_ok=True)


def save_forecast_version(
    df_forecast: pd.DataFrame,
    metadata: Dict[str, Any]
) -> str:
    """
    Save forecast as a version with metadata

    Args:
        df_forecast: Forecast DataFrame
        metadata: Dictionary containing:
            - timestamp: str (ISO format)
            - forecast_days: int
            - model_mode: str (e.g., "Custom (Hasil Evaluasi)")
            - model_config: dict (leaf_id -> model_name)
            - config_name: str (if using saved config)
            - total_leaf_nodes: int
            - future_date_cols: list of str
            - leaf_nodes: list of str
            - time_cols: list of str
            - cross_series_used: bool
            - external_features_used: bool (future)
            - holidays_count: int
            - etc.

    Returns:
        version_id: str (timestamp-based ID)
    """
    ensure_versions_dir()

    # Generate version ID from timestamp
    timestamp = metadata.get('timestamp', datetime.now().isoformat())
    version_id = datetime.fromisoformat(timestamp).strftime('%Y%m%d_%H%M%S')

    # Create version directory
    version_dir = os.path.join(FORECAST_VERSIONS_DIR, version_id)
    os.makedirs(version_dir, exist_ok=True)

    # Save forecast data as CSV
    forecast_file = os.path.join(version_dir, 'forecast.csv')
    df_forecast.to_csv(forecast_file, index=False)

    # Save metadata as JSON
    metadata_file = os.path.join(version_dir, 'metadata.json')
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)

    return version_id


def load_forecast_version(version_id: str) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Load forecast version by ID

    Args:
        version_id: Version ID (timestamp format)

    Returns:
        (df_forecast, metadata)
    """
    version_dir = os.path.join(FORECAST_VERSIONS_DIR, version_id)

    if not os.path.exists(version_dir):
        raise FileNotFoundError(f"Version {version_id} not found")

    # Load forecast data
    forecast_file = os.path.join(version_dir, 'forecast.csv')
    df_forecast = pd.read_csv(forecast_file)

    # Load metadata
    metadata_file = os.path.join(version_dir, 'metadata.json')
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)

    return df_forecast, metadata


def list_forecast_versions() -> List[Dict[str, Any]]:
    """
    List all available forecast versions

    Returns:
        List of version info dicts with keys:
        - version_id: str
        - timestamp: str
        - forecast_days: int
        - model_mode: str
        - total_leaf_nodes: int
        - config_name: str (if available)
    """
    ensure_versions_dir()

    versions = []

    if not os.path.exists(FORECAST_VERSIONS_DIR):
        return versions

    for version_id in os.listdir(FORECAST_VERSIONS_DIR):
        version_dir = os.path.join(FORECAST_VERSIONS_DIR, version_id)

        if not os.path.isdir(version_dir):
            continue

        metadata_file = os.path.join(version_dir, 'metadata.json')

        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                versions.append({
                    'version_id': version_id,
                    'timestamp': metadata.get('timestamp', ''),
                    'forecast_days': metadata.get('forecast_days', 0),
                    'model_mode': metadata.get('model_mode', 'Unknown'),
                    'total_leaf_nodes': metadata.get('total_leaf_nodes', 0),
                    'config_name': metadata.get('config_name', '-'),
                    'cross_series_used': metadata.get('cross_series_used', False),
                })
            except:
                pass

    # Sort by timestamp (newest first)
    versions = sorted(versions, key=lambda x: x['version_id'], reverse=True)

    return versions


def delete_forecast_version(version_id: str) -> bool:
    """
    Delete a forecast version

    Args:
        version_id: Version ID to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    version_dir = os.path.join(FORECAST_VERSIONS_DIR, version_id)

    if not os.path.exists(version_dir):
        return False

    try:
        import shutil
        shutil.rmtree(version_dir)
        return True
    except:
        return False


def get_version_summary(version_id: str) -> Dict[str, Any]:
    """
    Get detailed summary of a forecast version

    Args:
        version_id: Version ID

    Returns:
        Dictionary with detailed info including:
        - All metadata
        - Model usage counts
        - File size
        - etc.
    """
    version_dir = os.path.join(FORECAST_VERSIONS_DIR, version_id)

    if not os.path.exists(version_dir):
        return {}

    metadata_file = os.path.join(version_dir, 'metadata.json')
    forecast_file = os.path.join(version_dir, 'forecast.csv')

    with open(metadata_file, 'r') as f:
        metadata = json.load(f)

    # Calculate model usage counts
    model_config = metadata.get('model_config', {})
    model_counts = {}
    for model_name in model_config.values():
        model_counts[model_name] = model_counts.get(model_name, 0) + 1

    # Get file size
    file_size_bytes = os.path.getsize(forecast_file)
    file_size_kb = file_size_bytes / 1024

    summary = {
        **metadata,
        'model_counts': model_counts,
        'file_size_kb': file_size_kb,
    }

    return summary


def format_timestamp(timestamp_str: str) -> str:
    """
    Format timestamp string for display

    Args:
        timestamp_str: ISO format timestamp

    Returns:
        Formatted string like "2025-11-11 14:30:25"
    """
    try:
        dt = datetime.fromisoformat(timestamp_str)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return timestamp_str
