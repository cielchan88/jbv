import pandas as pd
import numpy as np
from .lightgbm_model import LightGBMForecaster
from .randomforest_model import RandomForestForecaster
from .xgboost_model import XGBoostForecaster
from .arima_model import ARIMAForecaster
from .prophet_model import ProphetForecaster
from .apuva_model import APUVAForecaster
from .croston_model import CrostonForecaster
from .stacking_model import StackingForecaster
from .var_model import VARForecaster
from .naive_model import NaiveForecaster


def forecast_single_series(dates, values, model_name, n_days, holidays=None, external_series=None, row_id=None):
    """
    Forecast a single time series using the specified model.

    Parameters:
    -----------
    dates : array-like
        Historical dates
    values : array-like
        Historical values
    model_name : str
        Model name ('lightgbm', 'randomforest', 'xgboost', 'arima', 'prophet', 'apuva')
    n_days : int
        Number of business days to forecast
    holidays : list, optional
        List of holiday dates to skip
    external_series : dict, optional
        Dict of external series for cross-series features {series_id: values_array}
    row_id : str, optional
        Row ID for APUVA model (needed for sentiment factor)

    Returns:
    --------
    forecast_values : list
        Forecasted values
    forecast_dates : list
        Business dates for forecasts (weekends and holidays excluded)
    """
    if holidays is None:
        holidays = []

    # Select and initialize model
    model_map = {
        'lightgbm': LightGBMForecaster,
        'randomforest': RandomForestForecaster,
        'xgboost': XGBoostForecaster,
        'arima': ARIMAForecaster,
        'autoarima': ARIMAForecaster,  # Alias for ARIMA (same model with grid search)
        'prophet': ProphetForecaster,
        'apuva': APUVAForecaster,
        'croston': CrostonForecaster,
        'stacking': StackingForecaster,
        'var': VARForecaster,
        'naive': NaiveForecaster,
        'naivemean': NaiveForecaster,
    }

    model_name_lower = model_name.lower()
    if model_name_lower not in model_map:
        raise ValueError(f"Unknown model: {model_name}. Available models: {list(model_map.keys())}")

    # Initialize forecaster
    if model_name_lower == 'apuva':
        forecaster = model_map[model_name_lower](holidays=holidays, row_id=row_id)
    elif model_name_lower == 'naive':
        forecaster = model_map[model_name_lower](holidays=holidays, method='last')
    elif model_name_lower == 'naivemean':
        # Harus sama persis dengan konfigurasi yang dipakai di halaman Evaluasi,
        # kalau tidak model yang terpilih sebagai "terbaik" bukan model yang jalan.
        forecaster = model_map[model_name_lower](holidays=holidays, method='mean', window=90)
    elif model_name_lower == 'stacking':
        # Stacking also needs row_id for APUVA base model
        forecaster = model_map[model_name_lower](holidays=holidays, row_id=row_id)
    else:
        forecaster = model_map[model_name_lower](holidays=holidays)

    # Fit and predict (pass external_series for ML models, Stacking, and VAR, ignored for ARIMA/Prophet/APUVA)
    if model_name_lower in ['lightgbm', 'randomforest', 'xgboost', 'stacking', 'var']:
        forecaster.fit(dates, values, external_series=external_series)
    else:
        forecaster.fit(dates, values)

    forecast_values, forecast_dates = forecaster.predict(dates, values, n_days)

    return forecast_values, forecast_dates


def forecast_hierarchical(df_wide, model_name, n_days, holidays=None, leaf_nodes_only=True):
    """
    Forecast all series in hierarchical data.

    Parameters:
    -----------
    df_wide : DataFrame
        Wide format dataframe with columns: Row_ID, Row_Label, Parent, Children, Level, date columns...
    model_name : str
        Model name ('lightgbm', 'randomforest', 'xgboost', 'arima', 'prophet')
    n_days : int
        Number of business days to forecast
    holidays : list, optional
        List of holiday dates to skip
    leaf_nodes_only : bool, default True
        If True, only forecast leaf nodes (non-totals)

    Returns:
    --------
    df_result : DataFrame
        Dataframe with original data + forecast columns
    """
    if holidays is None:
        holidays = []

    # Identify metadata columns
    metadata_cols = ['Row_ID', 'Row_Label', 'Parent', 'Children', 'Level']
    time_cols = [col for col in df_wide.columns if col not in metadata_cols]

    # Filter nodes to forecast
    if leaf_nodes_only:
        # Only forecast leaf nodes (Children == [])
        nodes_to_forecast = df_wide[df_wide['Children'].apply(lambda x: len(x) == 0)].copy()
    else:
        nodes_to_forecast = df_wide.copy()

    # Initialize result dataframe
    df_result = df_wide.copy()

    # Generate business dates for forecast columns
    from .. import generate_business_dates
    last_date = pd.to_datetime(time_cols[-1])
    forecast_dates = generate_business_dates(last_date, n_days, holidays)

    # Add forecast columns to result
    for forecast_date in forecast_dates:
        date_str = forecast_date.strftime('%Y-%m-%d')
        if date_str not in df_result.columns:
            df_result[date_str] = 0.0

    # Forecast each node
    for idx, row in nodes_to_forecast.iterrows():
        row_id = row['Row_ID']

        # Get historical data
        dates = time_cols
        values = row[time_cols].values

        # Skip if all zeros or too few data points
        if len(values) < 10 or np.all(values == 0):
            continue

        try:
            # Forecast (pass row_id for APUVA model)
            forecast_values, forecast_dates_list = forecast_single_series(
                dates=dates,
                values=values,
                model_name=model_name,
                n_days=n_days,
                holidays=holidays,
                row_id=row_id
            )

            # Update result dataframe
            for forecast_date, forecast_value in zip(forecast_dates_list, forecast_values):
                date_str = forecast_date.strftime('%Y-%m-%d')
                df_result.loc[df_result['Row_ID'] == row_id, date_str] = round(forecast_value, 2)

        except Exception as e:
            print(f"Warning: Failed to forecast {row_id}: {str(e)}")
            continue

    # Calculate totals for parent nodes (bottom-up aggregation)
    if leaf_nodes_only:
        df_result = _aggregate_forecasts(df_result, forecast_dates, metadata_cols)

    return df_result


def _aggregate_forecasts(df, forecast_dates, metadata_cols):
    """
    Aggregate forecasts from leaf nodes to parent nodes using bottom-up approach.

    Parameters:
    -----------
    df : DataFrame
        Dataframe with forecasted leaf nodes
    forecast_dates : list
        List of forecast dates
    metadata_cols : list
        List of metadata column names

    Returns:
    --------
    df : DataFrame
        Dataframe with aggregated forecasts
    """
    # Get all nodes sorted by level (descending - from leaf to root)
    df_sorted = df.sort_values('Level', ascending=False)

    # Process each parent node
    for idx, row in df_sorted.iterrows():
        children = row['Children']

        # Skip leaf nodes
        if len(children) == 0:
            continue

        # Aggregate children for each forecast date
        for forecast_date in forecast_dates:
            date_str = forecast_date.strftime('%Y-%m-%d')

            if date_str in df.columns:
                # Sum children values
                children_values = df[df['Row_ID'].isin(children)][date_str].values
                total_value = np.sum(children_values)

                # Update parent
                df.loc[idx, date_str] = round(total_value, 2)

    # Special handling for A.2.x nodes (if FULL version with A.0 exists)
    has_a0 = len(df[df['Row_ID'] == 'A.0']) > 0
    if has_a0:
        # A.2.x = A.0.x - A.1.x for each sub-category
        a2_nodes = df[df['Row_ID'].str.startswith('A.2.', na=False)]

        for idx, row in a2_nodes.iterrows():
            row_id = row['Row_ID']
            # Extract sub-category (e.g., 'A.2.a' -> 'a')
            sub_cat = row_id.split('.')[-1]

            # Find corresponding A.0.x and A.1.x nodes
            a0_id = f'A.0.{sub_cat}'
            a1_id = f'A.1.{sub_cat}'

            a0_row = df[df['Row_ID'] == a0_id]
            a1_row = df[df['Row_ID'] == a1_id]

            if len(a0_row) > 0 and len(a1_row) > 0:
                for forecast_date in forecast_dates:
                    date_str = forecast_date.strftime('%Y-%m-%d')

                    if date_str in df.columns:
                        a0_value = a0_row[date_str].values[0]
                        a1_value = a1_row[date_str].values[0]
                        a2_value = a0_value - a1_value

                        df.loc[idx, date_str] = round(a2_value, 2)

    return df
