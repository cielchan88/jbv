"""
Feature Engineering Utils for Time Series Forecasting
Shared between pages/3_predictive-new.py and pages/5_lembar_kerja.py
"""

import pandas as pd
import numpy as np
import json

from .feature_config import ENABLE_HOLIDAY_FEATURES


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
        >>> features = create_features_advanced(df, external_series=combined)
    """
    combined = {}

    # Add external features (from Excel)
    if external_features_dict:
        combined.update(external_features_dict)

    # Add cross-series features (from other time series)
    if cross_series_dict:
        combined.update(cross_series_dict)

    return combined


def create_features_advanced(df, lag_steps=90, holidays_list=None, external_series=None):
    """
    Advanced feature engineering for time series forecasting with cross-series features

    Args:
        df: DataFrame with 'ds' (date) and 'y' (value) columns
        lag_steps: Maximum lag steps to create
        holidays_list: List of holiday dates (optional)
        external_series: Dict of {series_id: values_array} for cross-series features (optional)
            Can include both:
            - External features from Excel (e.g., 'Sentiment_TradingEconomics', 'Oil_Price')
            - Cross-series from other time series (e.g., 'A.1.a', 'B.2.c')

            Use merge_external_features_with_cross_series() to combine both types.

    Returns:
        DataFrame with engineered features
    """
    df = df.copy()
    df['date'] = pd.to_datetime(df['ds'])
    df = df.rename(columns={'y': 'value'})

    # Basic time features
    df['day_of_week'] = df['date'].dt.dayofweek.astype('float64')
    df['day_of_month'] = df['date'].dt.day.astype('float64')
    df['month'] = df['date'].dt.month.astype('float64')
    df['quarter'] = df['date'].dt.quarter.astype('float64')
    df['week_of_year'] = df['date'].dt.isocalendar().week.astype('float64')

    # Cyclical encoding
    df['day_of_week_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['day_of_week_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
    df['day_of_month_sin'] = np.sin(2 * np.pi * df['day_of_month'] / 31)
    df['day_of_month_cos'] = np.cos(2 * np.pi * df['day_of_month'] / 31)

    # Weekend and month position
    df['is_weekend'] = (df['day_of_week'] >= 5).astype('float64')
    df['is_month_start'] = df['date'].dt.is_month_start.astype('float64')
    df['is_month_end'] = df['date'].dt.is_month_end.astype('float64')
    df['is_quarter_start'] = df['date'].dt.is_quarter_start.astype('float64')
    df['is_quarter_end'] = df['date'].dt.is_quarter_end.astype('float64')

    # Holiday features
    #
    # Dilewati sepenuhnya kalau ENABLE_HOLIDAY_FEATURES = False. Fungsi ini
    # dipakai oleh forecaster produksi (LightGBM/XGBoost/RandomForest di
    # utils/forecasting/), jadi tanpa gerbang ini saklar libur hanya berlaku di
    # halaman Evaluasi/Prediksi dan TIDAK di jalur forecast yang sebenarnya.
    if not ENABLE_HOLIDAY_FEATURES:
        pass
    elif holidays_list is not None and len(holidays_list) > 0:
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

    # Lag features (ADAPTIVE - more conservative to prevent "not in index" errors)
    # Rule: Only create lag if we have at least 5x the lag length in data
    available_lags = []
    all_possible_lags = [1, 2, 3, 7, 14, 21, 30, 60, 90]

    for lag in all_possible_lags:
        # Conservative: need at least 5x lag length OR explicit permission
        if len(df) >= lag * 5 or (lag <= 7 and len(df) >= lag * 3):
            available_lags.append(lag)

    # Ensure we always have at least lag_1
    if len(available_lags) == 0:
        available_lags = [1]

    # Create lag features
    for i in available_lags:
        df[f'lag_{i}'] = df['value'].shift(i)

    # Rolling statistics (ADAPTIVE windows based on data length)
    all_possible_windows = [3, 7, 14, 21, 30, 60, 90, 120, 180]
    available_windows = []

    for window in all_possible_windows:
        # Conservative: need at least 3x window length
        if len(df) >= window * 3:
            available_windows.append(window)

    # Ensure we have at least some windows
    if len(available_windows) == 0:
        available_windows = [3] if len(df) >= 9 else []

    for window in available_windows:
        if len(df) > window:
            df[f'rolling_mean_{window}'] = df['value'].shift(1).rolling(window=window).mean()
            df[f'rolling_std_{window}'] = df['value'].shift(1).rolling(window=window).std()
            df[f'rolling_min_{window}'] = df['value'].shift(1).rolling(window=window).min()
            df[f'rolling_max_{window}'] = df['value'].shift(1).rolling(window=window).max()
            df[f'rolling_median_{window}'] = df['value'].shift(1).rolling(window=window).median()
            df[f'rolling_skew_{window}'] = df['value'].shift(1).rolling(window=window).skew()
            df[f'rolling_kurt_{window}'] = df['value'].shift(1).rolling(window=window).kurt()

            # TAMBAHAN: Rolling range (max - min)
            try:
                df[f'rolling_range_{window}'] = df[f'rolling_max_{window}'] - df[f'rolling_min_{window}']
            except:
                df[f'rolling_range_{window}'] = 0

            # TAMBAHAN: Quantiles
            try:
                df[f'rolling_q25_{window}'] = df['value'].shift(1).rolling(window=window, min_periods=1).quantile(0.25)
                df[f'rolling_q75_{window}'] = df['value'].shift(1).rolling(window=window, min_periods=1).quantile(0.75)
            except:
                df[f'rolling_q25_{window}'] = 0
                df[f'rolling_q75_{window}'] = 0

    # Exponential weighted moving average (ADAPTIVE)
    all_possible_spans = [7, 14, 30, 60]
    available_spans = [span for span in all_possible_spans if len(df) >= span * 3]

    for span in available_spans:
        if len(df) > span:
            df[f'ewm_{span}'] = df['value'].shift(1).ewm(span=span).mean()
            df[f'ewm_std_{span}'] = df['value'].shift(1).ewm(span=span).std()

    # Trend features (ADAPTIVE)
    df['value_diff_1'] = df['value'].shift(1) - df['value'].shift(2)
    # Use safe division instead of pct_change to avoid division by zero
    df['value_pct_change_1'] = df['value'].diff(1).shift(1) / (df['value'].shift(2).fillna(0).abs() + 1e-8)

    if len(df) >= 24:  # Need at least 24 points for diff_7
        df['value_diff_7'] = df['value'].shift(1) - df['value'].shift(8)
        df['value_pct_change_7'] = (df['value'].shift(1) - df['value'].shift(8)) / (df['value'].shift(8).fillna(0).abs() + 1e-8)
    else:
        df['value_diff_7'] = 0
        df['value_pct_change_7'] = 0

    if len(df) >= 90:  # Need at least 90 points for diff_30
        df['value_diff_30'] = df['value'].shift(1) - df['value'].shift(31)
        df['value_pct_change_30'] = (df['value'].shift(1) - df['value'].shift(31)) / (df['value'].shift(31).fillna(0).abs() + 1e-8)
    else:
        df['value_diff_30'] = 0
        df['value_pct_change_30'] = 0

    # Volatility features (ADAPTIVE)
    volatility_windows = [w for w in [7, 14, 30] if len(df) >= w * 3]
    for window in volatility_windows:
        if len(df) > window:
            try:
                rolling_mean = df['value'].shift(1).rolling(window=window).mean()
                rolling_std = df['value'].shift(1).rolling(window=window).std()
                # Use abs(mean) + 1e-8 to prevent division by zero or negative
                df[f'volatility_{window}'] = rolling_std / (rolling_mean.fillna(0).abs() + 1e-8)
            except:
                df[f'volatility_{window}'] = 0

    # ========================================================================
    # VOLATILITY REGIME FEATURES (for high volatility data)
    # ========================================================================

    # Volatility ratio (short-term vs long-term)
    if 'volatility_7' in df.columns and 'volatility_30' in df.columns:
        df['volatility_ratio_7_30'] = df['volatility_7'] / (df['volatility_30'] + 1e-8)

    # High/Low volatility regime binary flag
    if 'volatility_14' in df.columns and len(df) > 60:
        vol_median = df['volatility_14'].shift(1).rolling(window=60, min_periods=1).median()
        df['is_high_volatility_regime'] = (df['volatility_14'].shift(1) > vol_median).astype('float64')
    else:
        df['is_high_volatility_regime'] = 0.0

    # Price level features (ratio to historical extremes)
    for window in [30, 60]:
        if len(df) > window:
            try:
                rolling_min = df['value'].shift(1).rolling(window=window, min_periods=1).min()
                rolling_max = df['value'].shift(1).rolling(window=window, min_periods=1).max()
                rolling_range = rolling_max - rolling_min

                # Normalized position in range (0 = at min, 1 = at max)
                df[f'price_position_{window}'] = (df['value'].shift(1) - rolling_min) / (rolling_range + 1e-8)
            except:
                df[f'price_position_{window}'] = 0

    # ========================================================================
    # ASYMMETRIC VOLATILITY FEATURES (Downside vs Upside risk)
    # ========================================================================

    # Separate returns into positive and negative
    # Use diff instead of pct_change to avoid division by zero
    returns_1d = df['value'].diff(1) / (df['value'].shift(1).fillna(0).abs() + 1e-8)

    for window in [7, 14, 30]:
        if len(df) > window:
            try:
                # Downside volatility (only negative returns)
                negative_returns = returns_1d.copy()
                negative_returns[negative_returns > 0] = 0
                df[f'downside_volatility_{window}'] = negative_returns.shift(1).rolling(window=window, min_periods=1).std()

                # Upside volatility (only positive returns)
                positive_returns = returns_1d.copy()
                positive_returns[positive_returns < 0] = 0
                df[f'upside_volatility_{window}'] = positive_returns.shift(1).rolling(window=window, min_periods=1).std()

                # Volatility skew (asymmetry measure)
                df[f'volatility_skew_{window}'] = (
                    df[f'downside_volatility_{window}'] / (df[f'upside_volatility_{window}'] + 1e-8)
                )
            except:
                df[f'downside_volatility_{window}'] = 0
                df[f'upside_volatility_{window}'] = 0
                df[f'volatility_skew_{window}'] = 0

    # ========================================================================
    # TECHNICAL INDICATORS
    # ========================================================================

    # RSI (Relative Strength Index)
    for window in [14, 30]:
        if len(df) > window:
            try:
                # Calculate price changes
                delta = df['value'].diff()

                # Separate gains and losses
                gains = delta.where(delta > 0, 0)
                losses = -delta.where(delta < 0, 0)

                # Calculate average gains and losses - SHIFT to prevent data leakage
                avg_gains = gains.shift(1).rolling(window=window, min_periods=1).mean()
                avg_losses = losses.shift(1).rolling(window=window, min_periods=1).mean()

                # Calculate RS and RSI
                rs = avg_gains / (avg_losses + 1e-8)
                df[f'rsi_{window}'] = 100 - (100 / (1 + rs))
            except:
                df[f'rsi_{window}'] = 50.0  # Neutral RSI

    # MACD (Moving Average Convergence Divergence)
    if len(df) > 26:
        try:
            # MACD uses EMA 12 and 26 - SHIFT to prevent data leakage
            ema_12 = df['value'].shift(1).ewm(span=12, adjust=False).mean()
            ema_26 = df['value'].shift(1).ewm(span=26, adjust=False).mean()

            # MACD line
            df['macd'] = ema_12 - ema_26

            # Signal line (9-day EMA of MACD) - SHIFT to prevent data leakage
            df['macd_signal'] = df['macd'].shift(1).ewm(span=9, adjust=False).mean()

            # MACD histogram (difference between MACD and signal)
            df['macd_histogram'] = df['macd'] - df['macd_signal']
        except:
            df['macd'] = 0
            df['macd_signal'] = 0
            df['macd_histogram'] = 0

    # Bollinger Bands
    for window in [20, 30]:
        if len(df) > window:
            try:
                rolling_mean = df['value'].shift(1).rolling(window=window).mean()
                rolling_std = df['value'].shift(1).rolling(window=window).std()

                # Upper and lower bands (2 std from mean)
                df[f'bb_upper_{window}'] = rolling_mean + (2 * rolling_std)
                df[f'bb_lower_{window}'] = rolling_mean - (2 * rolling_std)
                df[f'bb_middle_{window}'] = rolling_mean

                # Band width (volatility measure)
                df[f'bb_width_{window}'] = (df[f'bb_upper_{window}'] - df[f'bb_lower_{window}']) / (rolling_mean + 1e-8)

                # %B (position within bands) - no extra shift needed as bands already shifted
                df[f'bb_percent_{window}'] = (df['value'] - df[f'bb_lower_{window}']) / (df[f'bb_upper_{window}'] - df[f'bb_lower_{window}'] + 1e-8)
            except:
                df[f'bb_upper_{window}'] = 0
                df[f'bb_lower_{window}'] = 0
                df[f'bb_middle_{window}'] = 0
                df[f'bb_width_{window}'] = 0
                df[f'bb_percent_{window}'] = 0

    # ========================================================================
    # FOURIER FEATURES (for seasonal patterns)
    # ========================================================================

    # Add Fourier features for different frequencies
    if len(df) > 30:
        try:
            # Create time index (days from start)
            df['time_idx'] = np.arange(len(df))

            # Weekly cycle (7 days)
            df['fourier_weekly_sin'] = np.sin(2 * np.pi * df['time_idx'] / 7)
            df['fourier_weekly_cos'] = np.cos(2 * np.pi * df['time_idx'] / 7)

            # Monthly cycle (30 days)
            df['fourier_monthly_sin'] = np.sin(2 * np.pi * df['time_idx'] / 30)
            df['fourier_monthly_cos'] = np.cos(2 * np.pi * df['time_idx'] / 30)

            # Quarterly cycle (90 days)
            if len(df) > 90:
                df['fourier_quarterly_sin'] = np.sin(2 * np.pi * df['time_idx'] / 90)
                df['fourier_quarterly_cos'] = np.cos(2 * np.pi * df['time_idx'] / 90)

            # Drop time_idx (temporary column)
            df = df.drop('time_idx', axis=1)
        except:
            pass

    # ========================================================================
    # ENHANCED CALENDAR EFFECTS
    # ========================================================================

    # Days until month end
    df['days_until_month_end'] = df['date'].apply(
        lambda x: (pd.Period(x, freq='M').end_time.date() - x.date()).days
    ).astype('float64')

    # Days until quarter end
    df['days_until_quarter_end'] = df['date'].apply(
        lambda x: (pd.Period(x, freq='Q').end_time.date() - x.date()).days
    ).astype('float64')

    # Is near month end (last 5 days)
    df['is_near_month_end'] = (df['days_until_month_end'] <= 5).astype('float64')

    # Is near quarter end (last 10 days)
    df['is_near_quarter_end'] = (df['days_until_quarter_end'] <= 10).astype('float64')

    # ========================================================================
    # EXTREME VALUE DETECTION FEATURES
    # ========================================================================

    # Z-score features (distance from normal in std deviations)
    for window in [7, 14, 30]:
        if len(df) > window:
            try:
                rolling_mean = df['value'].shift(1).rolling(window=window, min_periods=1).mean()
                rolling_std = df['value'].shift(1).rolling(window=window, min_periods=1).std()
                df[f'z_score_{window}'] = (df['value'].shift(1) - rolling_mean) / (rolling_std + 1e-8)

                # Binary extreme flags (|z| > 2)
                df[f'is_extreme_high_{window}'] = (df[f'z_score_{window}'] > 2).astype('float64')
                df[f'is_extreme_low_{window}'] = (df[f'z_score_{window}'] < -2).astype('float64')
            except:
                df[f'z_score_{window}'] = 0
                df[f'is_extreme_high_{window}'] = 0
                df[f'is_extreme_low_{window}'] = 0

    # Jump detection (sudden large changes)
    if len(df) > 14:
        try:
            # Calculate typical change magnitude
            typical_change = df['value'].diff().shift(1).abs().rolling(window=14, min_periods=1).mean()
            typical_std = df['value'].diff().shift(1).rolling(window=14, min_periods=1).std()

            # Jump = change > mean + 2*std
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

    # Consecutive extremes counter
    try:
        if 'is_extreme_high_14' in df.columns:
            df['consecutive_extreme_highs'] = (
                df['is_extreme_high_14'].groupby((df['is_extreme_high_14'] != df['is_extreme_high_14'].shift()).cumsum()).cumsum()
            )
            df['consecutive_extreme_lows'] = (
                df['is_extreme_low_14'].groupby((df['is_extreme_low_14'] != df['is_extreme_low_14'].shift()).cumsum()).cumsum()
            )
    except:
        df['consecutive_extreme_highs'] = 0
        df['consecutive_extreme_lows'] = 0

    # Rate limiters (max/min changes in window)
    for window in [7, 14]:
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

    # Momentum features (ADAPTIVE)
    if len(df) >= 24:
        df['momentum_7'] = df['value'].shift(1) - df['value'].shift(8)
    else:
        df['momentum_7'] = 0

    if len(df) >= 90:
        df['momentum_30'] = df['value'].shift(1) - df['value'].shift(31)
    else:
        df['momentum_30'] = 0

    if len(df) >= 180:
        df['momentum_60'] = df['value'].shift(1) - df['value'].shift(61)
    else:
        df['momentum_60'] = 0

    # TAMBAHAN: Rate of Change (ROC) - ADAPTIVE
    all_roc_periods = [7, 14, 30, 60, 90]
    for period in all_roc_periods:
        if len(df) >= period * 3:
            # Use safe division instead of pct_change to avoid division by zero
            df[f'roc_{period}'] = (df['value'].shift(1) - df['value'].shift(period + 1)) / (df['value'].shift(period + 1).fillna(0).abs() + 1e-8)
        else:
            df[f'roc_{period}'] = 0

    # TAMBAHAN: Autocorrelation features
    for lag in [7, 14, 30]:
        if len(df) > lag + 60:  # Need at least 60 points for autocorr
            try:
                def safe_autocorr(x, lag_val):
                    try:
                        if len(x) > lag_val and x.std() > 0:
                            return x.autocorr(lag=lag_val)
                        return 0
                    except:
                        return 0

                df[f'autocorr_{lag}'] = df['value'].shift(1).rolling(window=60, min_periods=lag+1).apply(
                    lambda x: safe_autocorr(x, lag), raw=False
                )
            except Exception as e:
                df[f'autocorr_{lag}'] = 0

    # TAMBAHAN: Distance from rolling mean (normalized)
    for window in [7, 30, 60]:
        if len(df) > window and f'rolling_mean_{window}' in df.columns and f'rolling_std_{window}' in df.columns:
            try:
                rolling_mean = df[f'rolling_mean_{window}']
                rolling_std = df[f'rolling_std_{window}']
                df[f'distance_from_mean_{window}'] = (df['value'].shift(1) - rolling_mean) / (rolling_std + 1e-8)
            except Exception as e:
                df[f'distance_from_mean_{window}'] = 0

    # ========================================================================
    # CROSS-SERIES FEATURES (from correlated external series)
    # ========================================================================

    if external_series is not None and len(external_series) > 0:
        for series_id, series_values in external_series.items():
            try:
                # Clean series ID for column name (remove dots, make valid Python identifier)
                clean_id = series_id.replace('.', '_')

                # Create temporary dataframe for external series
                ext_df = pd.DataFrame({
                    'date': df['date'],
                    f'ext_{clean_id}': series_values[:len(df)]  # Ensure same length
                })

                # Add lag features from external series (only short lags to avoid too many features)
                for lag in [1, 7, 14]:
                    if len(df) >= lag * 3:
                        df[f'ext_{clean_id}_lag_{lag}'] = ext_df[f'ext_{clean_id}'].shift(lag)

                # Add rolling mean from external series
                if len(df) >= 21:
                    df[f'ext_{clean_id}_rolling_mean_7'] = ext_df[f'ext_{clean_id}'].shift(1).rolling(window=7).mean()

            except Exception as e:
                # Skip if error (e.g., length mismatch)
                continue

    # Interaction features
    df['lag1_x_dow'] = df.get('lag_1', 0) * df['day_of_week']
    df['lag7_x_dow'] = df.get('lag_7', 0) * df['day_of_week']
    df['rolling_mean_7_x_month'] = df.get('rolling_mean_7', 0) * df['month']
    df['rolling_mean_30_x_is_weekend'] = df.get('rolling_mean_30', 0) * df['is_weekend']

    if 'is_holiday' in df.columns:
        df['lag1_x_holiday'] = df.get('lag_1', 0) * df['is_holiday']

    # Clean inf and nan
    df = df.replace([np.inf, -np.inf], np.nan)

    # Get all numeric columns (should be all columns except 'date' and 'ds')
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if col != 'value':
            df[col] = df[col].ffill().bfill().fillna(0)

    # Convert ALL feature columns to float64 explicitly (fix object dtype issue)
    feature_cols = [col for col in df.columns if col not in ['date', 'ds', 'value']]
    for col in feature_cols:
        try:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype('float64')
        except:
            df[col] = 0.0

    df = df.dropna()
    return df


def select_top_features(train_df, top_k=25):
    """
    Select top K features using CORRELATION ONLY

    Args:
        train_df: Training DataFrame with features
        top_k: Number of top features to select

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

    # Get top K features
    top_features = [feat for feat, score in sorted_features[:top_k]]
    top_scores = {feat: score for feat, score in sorted_features[:top_k]}

    return top_features, top_scores
