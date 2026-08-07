"""
Bottom-up aggregation utilities for hierarchical data.
Used by Adjustment page and other pages that need to recalculate parent nodes.
"""

import numpy as np
import pandas as pd
import ast


def _compute_children(df):
    """
    Compute children for each row based on Row_ID hierarchy structure.

    Hierarchy rules:
    - A's children are A.1, A.2 (direct sub-nodes starting with A.)
    - A.1's children are A.1.a, A.1.b, A.1.c (nodes starting with A.1.)
    - Leaf nodes (no children) get empty list

    Returns:
    --------
    Series with list of children Row_IDs for each row
    """
    all_row_ids = set(df['Row_ID'].tolist())
    children_map = {}

    for row_id in all_row_ids:
        # Find direct children: nodes that start with this row_id + '.'
        # and have exactly one more level
        prefix = row_id + '.'
        children = []

        for other_id in all_row_ids:
            if other_id.startswith(prefix):
                # Check if it's a direct child (only one level deeper)
                suffix = other_id[len(prefix):]
                # Direct child has no more dots in suffix
                if '.' not in suffix:
                    children.append(other_id)

        children_map[row_id] = sorted(children)

    return df['Row_ID'].map(children_map)


def recalculate_parents(df, date_cols):
    """
    Recalculate parent nodes from leaf nodes using bottom-up aggregation.

    Parameters:
    -----------
    df : DataFrame
        Dataframe with Row_ID, Level columns and date columns
        (Children column is optional - will be computed from Row_ID structure)
    date_cols : list
        List of date column names to recalculate

    Returns:
    --------
    df : DataFrame
        Dataframe with recalculated parent values

    Example:
    --------
    >>> df_adjusted = recalculate_parents(df_forecast, future_date_cols)
    # Now A.1 = sum(A.1.a + A.1.b + ...) and A = sum(A.1 + A.2 + ...)
    """
    df = df.copy()

    # If Children column doesn't exist, compute it from Row_ID structure
    if 'Children' not in df.columns:
        df['Children'] = _compute_children(df)
    elif df['Children'].dtype == 'object':
        # Parse Children column if it's string
        df['Children'] = df['Children'].apply(
            lambda x: ast.literal_eval(x) if isinstance(x, str) else x
        )

    # Get all nodes sorted by level (descending - from leaf to root)
    df_sorted = df.sort_values('Level', ascending=False)

    # Process each parent node
    for idx, row in df_sorted.iterrows():
        row_id = row['Row_ID']
        children = row['Children']

        # Skip leaf nodes (no children)
        if not children or len(children) == 0:
            continue

        # SPECIAL CASE: D is NET SDV = A + B + C, NOT sum of D.UCL/D.LCL
        # D.UCL and D.LCL are confidence interval bounds, not children
        if row_id == 'D':
            for date_col in date_cols:
                if date_col in df.columns:
                    a_val = df.loc[df['Row_ID'] == 'A', date_col].values
                    b_val = df.loc[df['Row_ID'] == 'B', date_col].values
                    c_val = df.loc[df['Row_ID'] == 'C', date_col].values
                    if len(a_val) > 0 and len(b_val) > 0 and len(c_val) > 0:
                        total_value = a_val[0] + b_val[0] + c_val[0]
                        df.loc[idx, date_col] = round(total_value, 2)
            continue

        # Aggregate children for each date column
        for date_col in date_cols:
            if date_col in df.columns:
                # Sum children values
                children_values = df[df['Row_ID'].isin(children)][date_col].values
                total_value = np.sum(children_values)

                # Update parent
                df.loc[idx, date_col] = round(total_value, 2)

    # Special handling for A.2.x nodes (NET SDV = Total - KORPORASI)
    # A.2.x = A.0.x - A.1.x for each sub-category
    has_a0 = len(df[df['Row_ID'] == 'A.0']) > 0
    if has_a0:
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
                for date_col in date_cols:
                    if date_col in df.columns:
                        a0_value = a0_row[date_col].values[0]
                        a1_value = a1_row[date_col].values[0]
                        a2_value = a0_value - a1_value

                        df.loc[idx, date_col] = round(a2_value, 2)

    return df
