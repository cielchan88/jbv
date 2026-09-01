"""
Optimized Feature Engineering for High Volatility Time Series
Reduces from 250+ features to ~92-104 features while preserving volatility capture

Key improvements:
1. 60-70% fewer features (faster training, less overfitting)
2. Preserves ALL volatility-sensitive features (critical for volatile data)
3. Removes perfect redundancies (momentum/ROC, distance_from_mean, autocorr)
4. Simplified rolling windows and statistics
5. Force-includes volatility features in selection (prevents correlation bias)
"""

import pandas as pd
import numpy as np
import json
from .feature_config import FEATURE_CONFIG, get_forced_features


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


def get_same_depth_series(df, target_row_id):
    """
    Get all series at the same depth level as target series

    Args:
        df: Main dataframe with Row_ID column
        target_row_id: Target series Row_ID (e.g., 'A.1.1.1')

    Returns:
        List of Row_IDs at same depth (excluding target itself)
    """
    # Calculate depth by counting dots
    target_depth = target_row_id.count('.')

    # Get all leaf nodes (series with no children - parse JSON strings)
    leaf_nodes = df[df['Children'].apply(lambda x: len(parse_children(x))) == 0].copy()

    # Filter by same depth
    same_depth_series = []
    for row_id in leaf_nodes['Row_ID']:
        if row_id != target_row_id and row_id.count('.') == target_depth:
            same_depth_series.append(row_id)

    return same_depth_series


def calculate_series_correlations(df, target_row_id, candidate_series, time_cols):
    """
    Calculate correlation between target series and candidate series

    Args:
        df: Main dataframe
        target_row_id: Target series Row_ID
        candidate_series: List of candidate Row_IDs
        time_cols: List of time column names

    Returns:
        Dict of {row_id: correlation_value}
    """
    # Get target series values
    target_data = df[df['Row_ID'] == target_row_id]
    if len(target_data) == 0:
        return {}

    target_values = target_data[time_cols].values.flatten()

    correlations = {}
    for candidate_id in candidate_series:
        try:
            candidate_data = df[df['Row_ID'] == candidate_id]
            if len(candidate_data) == 0:
                continue

            candidate_values = candidate_data[time_cols].values.flatten()

            # Calculate correlation
            if len(target_values) == len(candidate_values):
                corr = np.corrcoef(target_values, candidate_values)[0, 1]
                if not np.isnan(corr):
                    correlations[candidate_id] = abs(corr)  # Use absolute correlation
        except:
            continue

    return correlations


def select_top_correlated_series(correlations, top_k=30):
    """
    Select top K series with highest correlation

    Args:
        correlations: Dict of {row_id: correlation}
        top_k: Number of top series to select

    Returns:
        List of top K Row_IDs sorted by correlation (descending)
    """
    # Sort by correlation (descending)
    sorted_series = sorted(correlations.items(), key=lambda x: x[1], reverse=True)

    # Get top K
    top_series = [row_id for row_id, corr in sorted_series[:top_k]]

    return top_series


def prepare_external_series_data(df, top_series_ids, time_cols):
    """
    Prepare external series data for feature engineering

    Args:
        df: Main dataframe
        top_series_ids: List of Row_IDs to extract
        time_cols: List of time column names

    Returns:
        Dict of {series_id: values_array}
    """
    external_data = {}

    for series_id in top_series_ids:
        try:
            series_data = df[df['Row_ID'] == series_id]
            if len(series_data) > 0:
                values = series_data[time_cols].values.flatten()
                external_data[series_id] = values
        except:
            continue

    return external_data


def transform_target(y, method='signed_log'):
    """
    Transform target variable to handle extreme volatility and near-zero values

    Args:
        y: Target values (array-like)
        method: Transformation method
            - 'signed_log': sign(x) * log(|x| + 1) - handles positive/negative/zero
            - 'log': log(x + c) - for strictly positive values
            - 'none': no transformation

    Returns:
        Transformed target values
    """
    y = np.array(y)

    if method == 'signed_log':
        # Signed log: preserves sign, handles zeros, reduces extreme values
        return np.sign(y) * np.log1p(np.abs(y))

    elif method == 'log':
        # Standard log with shift to handle near-zero values
        min_val = np.min(y)
        shift = abs(min_val) + 1 if min_val <= 0 else 0
        return np.log(y + shift + 1)

    elif method == 'none':
        return y

    else:
        raise ValueError(f"Unknown transformation method: {method}")


def inverse_transform_target(y_transformed, method='signed_log', shift=0):
    """
    Inverse transform to get back original scale

    Args:
        y_transformed: Transformed target values
        method: Transformation method used (must match transform_target)
        shift: Shift value used in log transform (only for 'log' method)

    Returns:
        Original scale values
    """
    y_transformed = np.array(y_transformed)

    if method == 'signed_log':
        # Inverse of signed log
        return np.sign(y_transformed) * (np.exp(np.abs(y_transformed)) - 1)

    elif method == 'log':
        # Inverse of log transform
        return np.exp(y_transformed) - shift - 1

    elif method == 'none':
        return y_transformed

    else:
        raise ValueError(f"Unknown transformation method: {method}")


def merge_external_features_with_cross_series(
    external_features_dict,
    cross_series_dict
):
    """
    Merge external features (from Excel) with cross-series features (from other time series).

    This helper ensures both types of external data can be used together in feature engineering.

    Args:
        external_features_dict: Dict from load_external.py
            e.g., {'Sentiment_TradingEconomics': array([...]), 'Oil_Price': array([...])}
        cross_series_dict: Dict from prepare_external_series_data()
            e.g., {'A.1.a': array([...]), 'B.2.c': array([...])}

    Returns:
        Combined dictionary with both external features and cross-series

    Example:
        >>> from etl.load_external import load_external_features
        >>> _, external_dict = load_external_features()
        >>> cross_dict = prepare_external_series_data(df, top_series, time_cols)
        >>> combined = merge_external_features_with_cross_series(external_dict, cross_dict)
        >>> features = create_features_optimized(df, external_series=combined)
    """
    combined = {}

    # Add external features (from Excel)
    if external_features_dict:
        combined.update(external_features_dict)

    # Add cross-series features (from other time series)
    if cross_series_dict:
        combined.update(cross_series_dict)

    return combined


def create_features_optimized(df, lag_steps=90, holidays_list=None, external_series=None,
                               external_series_dates=None, config=None):
    """
    OPTIMIZED feature engineering for high volatility time series
    Reduces from 250+ features to ~92-104 features

    Args:
        df: DataFrame with 'ds' (date) and 'y' (value) columns
        lag_steps: Maximum lag steps to create (ignored - using config)
        holidays_list: List of holiday dates (optional)
        external_series: Dict of {series_id: values_array} for cross-series features (optional)
        external_series_dates: Dates that each array in external_series corresponds to,
            in order (optional but strongly recommended). When provided, values are
            aligned to df['date'] by actual date instead of raw array position - this
            matters because df is often a train/test SLICE of the full series, so
            positional truncation (series_values[:len(df)]) silently grabs the wrong
            date range for anything but the very first rows. Falls back to the old
            positional behavior when omitted, for backward compatibility.
        config: Feature configuration dict (default: FEATURE_CONFIG from feature_config.py)

    Returns:
        DataFrame with engineered features
    """
    if config is None:
        config = FEATURE_CONFIG

    df = df.copy()
    df['date'] = pd.to_datetime(df['ds'])
    df = df.rename(columns={'y': 'value'})

    # ========================================================================
    # TIME FEATURES (8 features)
    # ========================================================================
    if config["time_features"]:
        # Basic time features (3 features)
        for feat in config["time_features"]["basic"]:
            if feat == "day_of_week":
                df['day_of_week'] = df['date'].dt.dayofweek.astype('float64')
            elif feat == "month":
                df['month'] = df['date'].dt.month.astype('float64')
            elif feat == "week_of_year":
                df['week_of_year'] = df['date'].dt.isocalendar().week.astype('float64')

        # Cyclical encoding (4 features)
        if "day_of_week_sin" in config["time_features"]["cyclical"]:
            df['day_of_week_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
            df['day_of_week_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
        if "month_sin" in config["time_features"]["cyclical"]:
            df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
            df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

        # Binary features (1 feature)
        if "is_weekend" in config["time_features"]["binary"]:
            df['is_weekend'] = (df['day_of_week'] >= 5).astype('float64')

    # ========================================================================
    # HOLIDAY FEATURES (3 features)
    # ========================================================================
    if config["holiday_features"]["enabled"]:
        if holidays_list is not None and len(holidays_list) > 0:
            df['is_holiday'] = df['date'].dt.date.isin(holidays_list).astype('float64')

            # Days until next holiday
            def days_to_next_holiday(date):
                future_holidays = [h for h in holidays_list if h > date.date()]
                if future_holidays:
                    return (min(future_holidays) - date.date()).days
                return 30  # Default if no future holiday

            df['days_to_holiday'] = df['date'].apply(days_to_next_holiday).astype('float64')

            # Days since last holiday
            def days_from_last_holiday(date):
                past_holidays = [h for h in holidays_list if h < date.date()]
                if past_holidays:
                    return (date.date() - max(past_holidays)).days
                return 30  # Default if no past holiday

            df['days_from_holiday'] = df['date'].apply(days_from_last_holiday).astype('float64')
        else:
            df['is_holiday'] = 0.0
            df['days_to_holiday'] = 30.0
            df['days_from_holiday'] = 30.0

    # ========================================================================
    # LAG FEATURES (4 features)
    # ========================================================================
    if config["lag_features"]["enabled"]:
        for lag in config["lag_features"]["lags"]:
            if len(df) >= lag * 3:  # Conservative check
                df[f'lag_{lag}'] = df['value'].shift(lag)

    # ========================================================================
    # ROLLING STATISTICS (20 features)
    # ========================================================================
    if config["rolling_statistics"]["enabled"]:
        for window in config["rolling_statistics"]["windows"]:
            if len(df) >= window * 3:  # Conservative check
                for stat in config["rolling_statistics"]["stats"]:
                    if stat == "mean":
                        df[f'rolling_mean_{window}'] = df['value'].shift(1).rolling(window=window).mean()
                    elif stat == "std":
                        df[f'rolling_std_{window}'] = df['value'].shift(1).rolling(window=window).std()
                    elif stat == "min":
                        df[f'rolling_min_{window}'] = df['value'].shift(1).rolling(window=window).min()
                    elif stat == "max":
                        df[f'rolling_max_{window}'] = df['value'].shift(1).rolling(window=window).max()

    # ========================================================================
    # EXPONENTIAL WEIGHTED MOVING AVERAGE (4 features)
    # ========================================================================
    if config["ewm_features"]["enabled"]:
        for span in config["ewm_features"]["spans"]:
            if len(df) >= span * 3:
                df[f'ewm_{span}'] = df['value'].shift(1).ewm(span=span).mean()
                df[f'ewm_std_{span}'] = df['value'].shift(1).ewm(span=span).std()

    # ========================================================================
    # TREND FEATURES (6 features)
    # ========================================================================
    if config["trend_features"]["enabled"]:
        # Difference features
        for period in config["trend_features"]["diff_periods"]:
            if period == 1:
                df['value_diff_1'] = df['value'].shift(1) - df['value'].shift(2)
            elif len(df) >= period * 3:
                df[f'value_diff_{period}'] = df['value'].shift(1) - df['value'].shift(period + 1)

        # Percentage change features
        for period in config["trend_features"]["pct_change_periods"]:
            if period == 1:
                df['value_pct_change_1'] = df['value'].diff(1).shift(1) / (df['value'].shift(2).fillna(0).abs() + 1e-8)
            elif len(df) >= period * 3:
                df[f'value_pct_change_{period}'] = (df['value'].shift(1) - df['value'].shift(period + 1)) / (df['value'].shift(period + 1).fillna(0).abs() + 1e-8)

    # ========================================================================
    # VOLATILITY FEATURES (15 features) - CRITICAL FOR VOLATILE DATA
    # ========================================================================
    if config["volatility_features"]["enabled"]:
        # Basic volatility (3 features)
        for window in config["volatility_features"]["windows"]:
            if len(df) >= window * 3:
                try:
                    rolling_mean = df['value'].shift(1).rolling(window=window).mean()
                    rolling_std = df['value'].shift(1).rolling(window=window).std()
                    df[f'volatility_{window}'] = rolling_std / (rolling_mean.fillna(0).abs() + 1e-8)
                except:
                    df[f'volatility_{window}'] = 0

        # Volatility regime features (2 features)
        if config["volatility_features"]["regime_features"]:
            if 'volatility_7' in df.columns and 'volatility_30' in df.columns:
                df['volatility_ratio_7_30'] = df['volatility_7'] / (df['volatility_30'] + 1e-8)

            if 'volatility_14' in df.columns and len(df) > 60:
                vol_median = df['volatility_14'].shift(1).rolling(window=60, min_periods=1).median()
                df['is_high_volatility_regime'] = (df['volatility_14'].shift(1) > vol_median).astype('float64')

        # Price position features (2 features)
        for window in config["volatility_features"]["price_position_windows"]:
            if len(df) > window:
                try:
                    rolling_min = df['value'].shift(1).rolling(window=window, min_periods=1).min()
                    rolling_max = df['value'].shift(1).rolling(window=window, min_periods=1).max()
                    rolling_range = rolling_max - rolling_min
                    df[f'price_position_{window}'] = (df['value'].shift(1) - rolling_min) / (rolling_range + 1e-8)
                except:
                    df[f'price_position_{window}'] = 0

        # Asymmetric volatility features (6 features)
        if config["volatility_features"]["asymmetric"]:
            # FIX LEAKAGE: Use shifted returns (yesterday's return, not today's)
            returns_1d = df['value'].shift(1).diff(1) / (df['value'].shift(2).fillna(0).abs() + 1e-8)

            for window in config["volatility_features"]["asymmetric_windows"]:
                if len(df) > window:
                    try:
                        # Downside volatility (returns_1d already shifted, no extra shift needed)
                        negative_returns = returns_1d.copy()
                        negative_returns[negative_returns > 0] = 0
                        df[f'downside_volatility_{window}'] = negative_returns.rolling(window=window, min_periods=1).std()

                        # Upside volatility
                        positive_returns = returns_1d.copy()
                        positive_returns[positive_returns < 0] = 0
                        df[f'upside_volatility_{window}'] = positive_returns.rolling(window=window, min_periods=1).std()

                        # Volatility skew
                        df[f'volatility_skew_{window}'] = (
                            df[f'downside_volatility_{window}'] / (df[f'upside_volatility_{window}'] + 1e-8)
                        )
                    except:
                        df[f'downside_volatility_{window}'] = 0
                        df[f'upside_volatility_{window}'] = 0
                        df[f'volatility_skew_{window}'] = 0

    # ========================================================================
    # TECHNICAL INDICATORS (7 features)
    # ========================================================================
    if config["technical_indicators"]:
        # RSI (1 feature)
        if config["technical_indicators"]["rsi"]["enabled"]:
            for window in config["technical_indicators"]["rsi"]["windows"]:
                if len(df) > window:
                    try:
                        # FIX LEAKAGE: Calculate delta from shifted values (yesterday's change)
                        delta = df['value'].shift(1).diff()  # Change between t-2 and t-1
                        gains = delta.where(delta > 0, 0)
                        losses = -delta.where(delta < 0, 0)
                        avg_gains = gains.rolling(window=window, min_periods=1).mean()
                        avg_losses = losses.rolling(window=window, min_periods=1).mean()
                        rs = avg_gains / (avg_losses + 1e-8)
                        df[f'rsi_{window}'] = 100 - (100 / (1 + rs))
                    except:
                        df[f'rsi_{window}'] = 50.0

        # MACD (3 features)
        if config["technical_indicators"]["macd"]["enabled"]:
            if len(df) > 26:
                try:
                    ema_12 = df['value'].shift(1).ewm(span=12, adjust=False).mean()
                    ema_26 = df['value'].shift(1).ewm(span=26, adjust=False).mean()
                    df['macd'] = ema_12 - ema_26
                    df['macd_signal'] = df['macd'].shift(1).ewm(span=9, adjust=False).mean()
                    df['macd_histogram'] = df['macd'] - df['macd_signal']
                except:
                    df['macd'] = 0
                    df['macd_signal'] = 0
                    df['macd_histogram'] = 0

        # Bollinger Bands (5 features)
        if config["technical_indicators"]["bollinger_bands"]["enabled"]:
            for window in config["technical_indicators"]["bollinger_bands"]["windows"]:
                if len(df) > window:
                    try:
                        rolling_mean = df['value'].shift(1).rolling(window=window).mean()
                        rolling_std = df['value'].shift(1).rolling(window=window).std()
                        df[f'bb_upper_{window}'] = rolling_mean + (2 * rolling_std)
                        df[f'bb_lower_{window}'] = rolling_mean - (2 * rolling_std)
                        df[f'bb_middle_{window}'] = rolling_mean
                        df[f'bb_width_{window}'] = (df[f'bb_upper_{window}'] - df[f'bb_lower_{window}']) / (rolling_mean + 1e-8)
                        # FIX LEAKAGE: Use shift(1) to avoid using current value
                        df[f'bb_percent_{window}'] = (df['value'].shift(1) - df[f'bb_lower_{window}']) / (df[f'bb_upper_{window}'] - df[f'bb_lower_{window}'] + 1e-8)
                    except:
                        df[f'bb_upper_{window}'] = 0
                        df[f'bb_lower_{window}'] = 0
                        df[f'bb_middle_{window}'] = 0
                        df[f'bb_width_{window}'] = 0
                        df[f'bb_percent_{window}'] = 0

    # ========================================================================
    # FOURIER FEATURES (6 features)
    # ========================================================================
    if config["fourier_features"]["enabled"] and len(df) > 30:
        try:
            df['time_idx'] = np.arange(len(df))

            if config["fourier_features"]["cycles"]["weekly"]:
                df['fourier_weekly_sin'] = np.sin(2 * np.pi * df['time_idx'] / 7)
                df['fourier_weekly_cos'] = np.cos(2 * np.pi * df['time_idx'] / 7)

            if config["fourier_features"]["cycles"]["monthly"]:
                df['fourier_monthly_sin'] = np.sin(2 * np.pi * df['time_idx'] / 30)
                df['fourier_monthly_cos'] = np.cos(2 * np.pi * df['time_idx'] / 30)

            if config["fourier_features"]["cycles"]["quarterly"] and len(df) > 90:
                df['fourier_quarterly_sin'] = np.sin(2 * np.pi * df['time_idx'] / 90)
                df['fourier_quarterly_cos'] = np.cos(2 * np.pi * df['time_idx'] / 90)

            df = df.drop('time_idx', axis=1)
        except:
            pass

    # ========================================================================
    # CALENDAR EFFECTS (4 features)
    # ========================================================================
    if config["calendar_features"]["enabled"]:
        df['days_until_month_end'] = df['date'].apply(
            lambda x: (pd.Period(x, freq='M').end_time.date() - x.date()).days
        ).astype('float64')

        df['days_until_quarter_end'] = df['date'].apply(
            lambda x: (pd.Period(x, freq='Q').end_time.date() - x.date()).days
        ).astype('float64')

        df['is_near_month_end'] = (df['days_until_month_end'] <= 5).astype('float64')
        df['is_near_quarter_end'] = (df['days_until_quarter_end'] <= 10).astype('float64')

    # ========================================================================
    # EXTREME VALUE DETECTION (11 features) - CRITICAL FOR VOLATILE DATA
    # ========================================================================
    if config["extreme_detection"]["enabled"]:
        # Z-score features (2 features + 4 binary flags)
        for window in config["extreme_detection"]["z_score_windows"]:
            if len(df) > window:
                try:
                    rolling_mean = df['value'].shift(1).rolling(window=window, min_periods=1).mean()
                    rolling_std = df['value'].shift(1).rolling(window=window, min_periods=1).std()
                    df[f'z_score_{window}'] = (df['value'].shift(1) - rolling_mean) / (rolling_std + 1e-8)

                    if config["extreme_detection"]["extreme_flags"]:
                        df[f'is_extreme_high_{window}'] = (df[f'z_score_{window}'] > 2).astype('float64')
                        df[f'is_extreme_low_{window}'] = (df[f'z_score_{window}'] < -2).astype('float64')
                except:
                    df[f'z_score_{window}'] = 0
                    df[f'is_extreme_high_{window}'] = 0
                    df[f'is_extreme_low_{window}'] = 0

        # Jump detection (3 features)
        if config["extreme_detection"]["jump_detection"] and len(df) > 14:
            try:
                typical_change = df['value'].diff().shift(1).abs().rolling(window=14, min_periods=1).mean()
                typical_std = df['value'].diff().shift(1).rolling(window=14, min_periods=1).std()
                current_change = df['value'].shift(1).diff()
                df['jump_size'] = current_change.abs() / (typical_change + 1e-8)
                df['is_jump'] = (current_change.abs() > (typical_change + 2 * typical_std)).astype('float64')

                # Time since last jump
                jump_indices = df.index[df['is_jump'] == 1].tolist()
                df['days_since_jump'] = 0.0
                for i in range(len(df)):
                    if i > 0:
                        recent_jumps = [j for j in jump_indices if j < i]
                        if recent_jumps:
                            df.loc[df.index[i], 'days_since_jump'] = i - max(recent_jumps)
                        else:
                            df.loc[df.index[i], 'days_since_jump'] = i
            except:
                df['jump_size'] = 0
                df['is_jump'] = 0
                df['days_since_jump'] = 0

        # Change limits (3 features)
        if config["extreme_detection"]["change_limits"]["enabled"]:
            for window in config["extreme_detection"]["change_limits"]["windows"]:
                if len(df) > window:
                    try:
                        changes = df['value'].diff().shift(1)
                        df[f'max_change_{window}d'] = changes.rolling(window=window, min_periods=1).max()
                        df[f'min_change_{window}d'] = changes.rolling(window=window, min_periods=1).min()
                        df[f'change_range_{window}d'] = df[f'max_change_{window}d'] - df[f'min_change_{window}d']
                    except:
                        df[f'max_change_{window}d'] = 0
                        df[f'min_change_{window}d'] = 0
                        df[f'change_range_{window}d'] = 0

    # ========================================================================
    # CROSS-SERIES FEATURES (~12 features for 3 external series)
    # ========================================================================
    if config["cross_series_features"]["enabled"] and external_series is not None and len(external_series) > 0:
        if external_series_dates is not None:
            full_date_index = pd.DatetimeIndex(pd.to_datetime(external_series_dates))

        for series_id, series_values in external_series.items():
            try:
                clean_id = series_id.replace('.', '_')

                if external_series_dates is not None:
                    # Align by actual date so a train/test SLICE of df still gets the
                    # correct segment of series_values, not just its first len(df) entries.
                    aligned_values = (
                        pd.Series(series_values, index=full_date_index)
                        .reindex(df['date'])
                        .values
                    )
                else:
                    # Legacy fallback: assumes df starts at the same date as series_values.
                    aligned_values = series_values[:len(df)]

                ext_df = pd.DataFrame({
                    'date': df['date'],
                    f'ext_{clean_id}': aligned_values
                })

                # Lag features from external series
                for lag in config["cross_series_features"]["lags"]:
                    if len(df) >= lag * 3:
                        df[f'ext_{clean_id}_lag_{lag}'] = ext_df[f'ext_{clean_id}'].shift(lag)

                # Rolling mean from external series
                window = config["cross_series_features"]["rolling_mean_window"]
                if len(df) >= window * 3:
                    df[f'ext_{clean_id}_rolling_mean_{window}'] = ext_df[f'ext_{clean_id}'].shift(1).rolling(window=window).mean()

            except Exception as e:
                continue

    # ========================================================================
    # INTERACTION FEATURES (4 features)
    # ========================================================================
    if config["interaction_features"]["enabled"]:
        for feat1, feat2 in config["interaction_features"]["interactions"]:
            if feat1 in df.columns and feat2 in df.columns:
                df[f'{feat1}_x_{feat2}'] = df[feat1] * df[feat2]

    # ========================================================================
    # CLEANUP
    # ========================================================================
    # Clean inf and nan
    df = df.replace([np.inf, -np.inf], np.nan)

    # Get all numeric columns
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if col != 'value':
            df[col] = df[col].ffill().bfill().fillna(0)

    # Convert all feature columns to float64
    feature_cols = [col for col in df.columns if col not in ['date', 'ds', 'value']]
    for col in feature_cols:
        try:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype('float64')
        except:
            df[col] = 0.0

    # Only drop rows where 'value' is NaN (not all columns)
    df = df.dropna(subset=['value'])
    return df


def select_top_features_optimized(train_df, top_k=25, volatility_quota=0, mrmr_beta=0.0):
    """
    Select top K features using correlation (Spearman), with an optional
    reserved quota for volatility features.

    Args:
        train_df: Training DataFrame with features
        top_k: Number of top features to select
        volatility_quota: Berapa dari top_k slot yang dipesan untuk fitur di
            VOLATILITY_PRIORITY_FEATURES. 0 = perilaku lama (korelasi murni).
            Lihat penjelasan di badan fungsi. TERUKUR MEMPERBURUK - jangan
            diaktifkan tanpa bukti baru.
        mrmr_beta: Bobot penalti redundansi (mRMR). 0 = perilaku lama.
            Lihat penjelasan di badan fungsi.

    Returns:
        Tuple of (top_features_list, scores_dict)
    """
    # Get feature columns (exclude date, ds, and value)
    feature_cols = [col for col in train_df.columns if col not in ['date', 'ds', 'value']]

    if len(feature_cols) == 0:
        return [], {}

    # Prepare data
    X = train_df[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
    y = train_df['value'].fillna(0)

    # Calculate correlation scores using Spearman (handles non-linear relationships)
    corr_scores = {}
    for col in feature_cols:
        try:
            corr = abs(X[col].corr(y, method='spearman'))
            if not np.isnan(corr):
                corr_scores[col] = corr
            else:
                corr_scores[col] = 0
        except:
            corr_scores[col] = 0

    # Sort by correlation (descending)
    sorted_features = sorted(corr_scores.items(), key=lambda x: x[1], reverse=True)

    # ------------------------------------------------------------------
    # Kuota fitur volatilitas.
    #
    # Seleksi murni korelasi punya titik buta yang sudah diantisipasi penulis
    # config (lihat get_forced_features di feature_config.py): fitur volatilitas
    # mengukur SEBERAPA BESAR pergerakan, bukan ke arah mana, sehingga korelasi
    # Spearman-nya terhadap level sering rendah - lalu tersingkir. Padahal
    # volatility clustering adalah struktur terkuat di data ini (autokorelasi
    # |perubahan| lag-1 bermedian 0,489, positif di 18 dari 18 leaf).
    #
    # Tanpa kuota, rata-rata hanya 6,7 dari 29 fitur prioritas yang lolos top-25
    # pada data nyata.
    #
    # Kuota TIDAK menambah jumlah fitur - ia hanya memesan sebagian dari top_k,
    # sehingga perbandingan dengan baseline tetap adil (kompleksitas model sama).
    # volatility_quota=0 mengembalikan perilaku lama persis.
    #
    # ------------------------------------------------------------------
    # HASIL PENGUKURAN: KUOTA MEMPERBURUK. JANGAN DIAKTIFKAN TANPA BUKTI BARU.
    #
    # Diuji pada 18 leaf x 3 jendela x 3 model (486 unit), horizon 60 hari:
    #
    #   kuota   LightGBM   RandomForest   XGBoost    Wilcoxon vs kuota 0
    #      12    +0,88%        +1,91%      +0,82%    menang 64/162, p=0,036
    #      18    +2,30%        +3,12%      +4,06%    menang 78/162, p=0,129
    #
    # Kuota 12 lebih buruk secara signifikan. Ketiga model memburuk di kedua
    # kuota, tanpa perkecualian.
    #
    # Penafsirannya: dugaan penulis config bahwa seleksi korelasi "membuang
    # fitur volatilitas yang berguna" tidak terbukti. Fitur volatilitas yang
    # tersingkir memang tersingkir karena tidak membantu memprediksi LEVEL -
    # yang justru ditugaskan pada model ini. Volatility clustering nyata dan
    # kuat di data (ACF |perubahan| lag-1 median 0,489), tapi jalan untuk
    # memanfaatkannya adalah memodelkan RAGAM BERSYARAT - misalnya untuk lebar
    # interval, seperti sudah dilakukan di utils/intervals.py - bukan menjejalkan
    # fitur volatilitas ke model rata-rata bersyarat.
    #
    # Keterbatasan: pengukuran memakai mode direct. Seleksi fitur memengaruhi
    # model yang TERLATIH, dan model terlatihnya sama di kedua protokol, jadi
    # hasilnya informatif - tapi kemungkinan fitur volatilitas membantu khusus
    # pada kestabilan recursive belum diuji.
    # ------------------------------------------------------------------
    if volatility_quota and volatility_quota > 0:
        from .feature_config import VOLATILITY_PRIORITY_FEATURES
        prio = set(VOLATILITY_PRIORITY_FEATURES)

        # Kuota adalah LANTAI, bukan jumlah pasti. Kalau seleksi korelasi murni
        # sudah menghasilkan fitur volatilitas sebanyak atau lebih dari kuota,
        # tidak ada yang perlu diubah - memaksa jumlahnya turun ke angka kuota
        # justru membuang fitur yang lolos atas kekuatannya sendiri.
        base = sorted_features[:top_k]
        n_vol = sum(1 for f, _ in base if f in prio)
        need = int(volatility_quota) - n_vol
        if need <= 0:
            return [f for f, _ in base], {f: s for f, s in base}

        # Tambahkan fitur volatilitas terbaik yang belum masuk, sambil membuang
        # fitur non-volatilitas berkorelasi terlemah - jumlah total tetap top_k.
        in_base = {f for f, _ in base}
        add = [(f, s) for f, s in sorted_features if f in prio and f not in in_base][:need]
        if not add:
            return [f for f, _ in base], {f: s for f, s in base}

        keep_vol = [(f, s) for f, s in base if f in prio]
        keep_oth = [(f, s) for f, s in base if f not in prio]
        drop = len(add)
        keep_oth = keep_oth[:max(len(keep_oth) - drop, 0)]

        picked = keep_vol + add + keep_oth
        picked = sorted(picked, key=lambda x: x[1], reverse=True)[:top_k]
        return [f for f, _ in picked], {f: s for f, s in picked}

    # ------------------------------------------------------------------
    # Seleksi sadar-redundansi (mRMR).
    #
    # Seleksi univariat menilai tiap fitur SENDIRI-SENDIRI terhadap target,
    # tanpa memeriksa apakah ia sudah diwakili fitur yang terpilih sebelumnya.
    # Pada data ini akibatnya terukur: rata-rata |korelasi| ANTAR 25 fitur
    # terpilih adalah 0,667, dan analisis komponen utama menunjukkan ke-25
    # fitur itu hanya membawa informasi setara 8,8 fitur bebas.
    #
    # Wujud konkretnya, fitur yang terpilih di >=15 dari 18 leaf mencakup
    # rolling_mean_7/14/30/60/90, ewm_7, ewm_30, dan bb_middle_20 - delapan
    # varian dari benda yang sama, karena garis tengah Bollinger secara
    # definisi juga rata-rata bergerak.
    #
    # mRMR memilih secara serakah dengan skor:
    #     relevansi(f) - beta * rata-rata |korelasi(f, yang sudah terpilih)|
    #
    # beta=0 mengembalikan perilaku lama persis. Berbeda dari kuota
    # volatilitas yang sudah diuji dan GAGAL (ia memaksa masuk fitur yang
    # datanya bilang tidak berguna), di sini relevansi tetap jadi kriteria -
    # redundansi hanya memutus seri antar fitur yang sama-sama relevan.
    # ------------------------------------------------------------------
    if mrmr_beta and mrmr_beta > 0:
        cand = [f for f, _ in sorted_features]
        # Batasi kandidat agar matriks korelasinya murah dihitung
        cand = cand[:min(len(cand), max(top_k * 3, 40))]
        if len(cand) > 1:
            Xc = X[cand]
            R = Xc.corr(method='spearman').abs().fillna(0.0)

            picked = [cand[0]]
            while len(picked) < min(top_k, len(cand)):
                best_f, best_v = None, -np.inf
                for f in cand:
                    if f in picked:
                        continue
                    red = float(R.loc[f, picked].mean())
                    val = corr_scores[f] - mrmr_beta * red
                    if val > best_v:
                        best_v, best_f = val, f
                if best_f is None:
                    break
                picked.append(best_f)

            return picked, {f: corr_scores[f] for f in picked}

    # Select top K features by correlation only
    top_features = []
    top_scores = {}

    for feat, score in sorted_features:
        top_features.append(feat)
        top_scores[feat] = score

        if len(top_features) >= top_k:
            break

    return top_features, top_scores
