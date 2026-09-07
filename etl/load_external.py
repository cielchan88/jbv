"""
External Features Loader
Loads external features from Excel and prepares them for model training.

Author: APUVA Team
Date: 2025-11-11
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import warnings


def load_external_features(
    filepath: str = 'data/external_features.xlsx',
    sheet_name: str = None,
    date_column: str = 'Tanggal',
    validate: bool = True
) -> Tuple[pd.DataFrame, Dict[str, np.ndarray]]:
    """
    Load external features from Excel file.

    Parameters:
    -----------
    filepath : str
        Path to external features Excel file
    sheet_name : str, optional
        Name of the sheet containing external features.
        If None (default), uses the first sheet in the file.
    date_column : str
        Name of the date column
    validate : bool
        Whether to perform validation checks

    Returns:
    --------
    df : pd.DataFrame
        DataFrame with all external features
    external_dict : Dict[str, np.ndarray]
        Dictionary mapping feature names to value arrays
        Format: {'feature_name': array([values...])}

    Raises:
    -------
    FileNotFoundError
        If the Excel file doesn't exist
    ValueError
        If validation fails

    Example:
    --------
    >>> df, external_dict = load_external_features('data/external_features.xlsx')
    >>> print(external_dict.keys())
    dict_keys(['Sentiment_TradingEconomics', 'Oil_Price_Brent', 'USD_IDR', ...])
    """
    # Check file exists
    file_path = Path(filepath)
    if not file_path.exists():
        raise FileNotFoundError(f"External features file not found: {filepath}")

    # Load Excel (use default sheet if sheet_name is None)
    try:
        if sheet_name:
            # Try specific sheet name with fallback to default
            try:
                df = pd.read_excel(filepath, sheet_name=sheet_name)
            except ValueError as e:
                if "Worksheet named" in str(e):
                    warnings.warn(f"Sheet '{sheet_name}' not found, using default sheet")
                    df = pd.read_excel(filepath)  # Use default (first) sheet
                else:
                    raise ValueError(f"Failed to read Excel file: {e}")
        else:
            # Use default (first) sheet
            df = pd.read_excel(filepath)
    except Exception as e:
        raise ValueError(f"Failed to read Excel file: {e}")

    # Validate
    if validate:
        _validate_external_features(df, date_column)

    # Convert date column to datetime
    df[date_column] = pd.to_datetime(df[date_column])

    # Sort by date
    df = df.sort_values(date_column).reset_index(drop=True)

    # Create dictionary for external_series parameter
    feature_columns = [col for col in df.columns if col != date_column]
    external_dict = {}

    for col in feature_columns:
        # Convert to numpy array and handle NaN
        values = df[col].values

        # Forward fill NaN values
        if np.isnan(values).any():
            warnings.warn(f"Feature '{col}' has {np.isnan(values).sum()} NaN values. Forward filling...")
            df[col] = df[col].fillna(method='ffill')
            # Backward fill for leading NaNs
            df[col] = df[col].fillna(method='bfill')
            values = df[col].values

        external_dict[col] = values

    return df, external_dict


def _validate_external_features(df: pd.DataFrame, date_column: str) -> None:
    """
    Validate external features DataFrame.

    Checks:
    - Date column exists
    - At least one feature column
    - No duplicate dates
    - Reasonable date range
    """
    # Check date column exists
    if date_column not in df.columns:
        raise ValueError(f"Date column '{date_column}' not found. Available columns: {df.columns.tolist()}")

    # Check at least one feature
    feature_cols = [col for col in df.columns if col != date_column]
    if len(feature_cols) == 0:
        raise ValueError("No feature columns found. Need at least one feature besides date column.")

    # Convert to datetime for validation
    try:
        dates = pd.to_datetime(df[date_column])
    except Exception as e:
        raise ValueError(f"Failed to parse date column '{date_column}': {e}")

    # Check duplicate dates
    duplicates = dates.duplicated()
    if duplicates.any():
        dup_dates = dates[duplicates].tolist()
        raise ValueError(f"Found {len(dup_dates)} duplicate dates. First few: {dup_dates[:5]}")

    # Check date range
    min_date = dates.min()
    max_date = dates.max()
    date_range = (max_date - min_date).days

    if date_range < 30:
        warnings.warn(f"Date range is only {date_range} days. Recommend at least 90 days for meaningful features.")

    # Check for excessive NaN
    for col in feature_cols:
        nan_pct = df[col].isna().sum() / len(df) * 100
        if nan_pct > 50:
            warnings.warn(f"Feature '{col}' has {nan_pct:.1f}% missing values. Consider data quality.")

    print(f"✓ Validation passed:")
    print(f"  - Date range: {min_date.date()} to {max_date.date()} ({date_range} days)")
    print(f"  - Total rows: {len(df)}")
    print(f"  - Features: {len(feature_cols)} ({', '.join(feature_cols)})")


def merge_with_training_data(
    train_df: pd.DataFrame,
    external_df: pd.DataFrame,
    date_column: str = 'Tanggal',
    how: str = 'left'
) -> pd.DataFrame:
    """
    Merge external features with training data by date.

    Parameters:
    -----------
    train_df : pd.DataFrame
        Training data with date index or date column
    external_df : pd.DataFrame
        External features DataFrame
    date_column : str
        Name of the date column
    how : str
        Merge strategy ('left', 'inner', 'outer')

    Returns:
    --------
    merged_df : pd.DataFrame
        Merged DataFrame with both training and external features

    Example:
    --------
    >>> merged = merge_with_training_data(train_df, external_df)
    """
    # Ensure both have datetime index
    if date_column not in train_df.columns:
        # Assume index is date
        train_df = train_df.reset_index()
        train_df.rename(columns={'index': date_column}, inplace=True)

    train_df[date_column] = pd.to_datetime(train_df[date_column])
    external_df[date_column] = pd.to_datetime(external_df[date_column])

    # Merge
    merged = train_df.merge(external_df, on=date_column, how=how)

    # Handle NaN from merge (dates in train but not in external)
    external_cols = [col for col in external_df.columns if col != date_column]
    for col in external_cols:
        if merged[col].isna().any():
            # Forward fill first
            merged[col] = merged[col].fillna(method='ffill')
            # Then backward fill for leading NaNs
            merged[col] = merged[col].fillna(method='bfill')
            # If still NaN, fill with median
            if merged[col].isna().any():
                merged[col] = merged[col].fillna(merged[col].median())

    return merged


def get_external_features_info(filepath: str = 'data/external_features.xlsx') -> Dict:
    """
    Get information about external features file without loading full data.

    Returns:
    --------
    info : Dict
        Dictionary with file info
    """
    file_path = Path(filepath)

    if not file_path.exists():
        return {
            'exists': False,
            'path': str(filepath)
        }

    try:
        # Read just first few rows (use default sheet)
        df = pd.read_excel(filepath, nrows=5)
        full_df = pd.read_excel(filepath)

        date_col = 'Tanggal'
        feature_cols = [col for col in df.columns if col != date_col]

        dates = pd.to_datetime(full_df[date_col])

        return {
            'exists': True,
            'path': str(filepath),
            'num_rows': len(full_df),
            'num_features': len(feature_cols),
            'features': feature_cols,
            'date_range': {
                'start': dates.min().strftime('%Y-%m-%d'),
                'end': dates.max().strftime('%Y-%m-%d')
            },
            'file_size_kb': file_path.stat().st_size / 1024
        }
    except Exception as e:
        return {
            'exists': True,
            'path': str(filepath),
            'error': str(e)
        }


def align_external_features_to_dates(
    external_dict: Dict[str, np.ndarray],
    external_dates: pd.DatetimeIndex,
    target_dates: pd.DatetimeIndex
) -> Dict[str, np.ndarray]:
    """
    Align external features to match target dates.

    This is useful when your training data has different dates than external data.

    Parameters:
    -----------
    external_dict : Dict[str, np.ndarray]
        External features dictionary
    external_dates : pd.DatetimeIndex
        Dates corresponding to external_dict values
    target_dates : pd.DatetimeIndex
        Target dates to align to

    Returns:
    --------
    aligned_dict : Dict[str, np.ndarray]
        Aligned external features
    """
    # Create DataFrame for easier alignment
    external_df = pd.DataFrame(external_dict, index=external_dates)
    external_df = external_df[~external_df.index.duplicated(keep='last')].sort_index()

    # Reindex to target dates with forward fill
    aligned_df = external_df.reindex(target_dates, method='ffill')

    # Backward fill for leading NaNs
    aligned_df = aligned_df.bfill()

    # Convert back to dict
    aligned_dict = {col: aligned_df[col].values for col in aligned_df.columns}

    return aligned_dict


if __name__ == "__main__":
    # Test the loader
    print("Testing External Features Loader...")
    print("=" * 60)

    try:
        # Load features
        df, external_dict = load_external_features()

        print("\n✓ Successfully loaded external features!")
        print(f"\nFeatures available: {list(external_dict.keys())}")
        print(f"\nSample values for first feature:")
        first_feature = list(external_dict.keys())[0]
        print(f"{first_feature}: {external_dict[first_feature][:5]}")

        # Get info
        print("\n" + "=" * 60)
        info = get_external_features_info()
        print("File Info:")
        for key, value in info.items():
            print(f"  {key}: {value}")

    except Exception as e:
        print(f"\n✗ Error: {e}")
