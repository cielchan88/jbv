"""
Test External Features Integration

Tests the full flow:
1. Load external features from Excel
2. Merge with cross-series data
3. Create features with both
4. Verify feature creation

Author: APUVA Team
Date: 2025-11-11
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from etl.load_external import load_external_features, get_external_features_info
from utils.feature_engineering import (
    create_features_advanced,
    merge_external_features_with_cross_series
)


def test_load_external():
    """Test loading external features"""
    print("=" * 60)
    print("TEST 1: Load External Features")
    print("=" * 60)

    try:
        df, external_dict = load_external_features()
        print("✓ Successfully loaded external features")
        print(f"  - Features: {list(external_dict.keys())}")
        print(f"  - First feature shape: {external_dict[list(external_dict.keys())[0]].shape}")
        return external_dict
    except Exception as e:
        print(f"✗ Failed to load: {e}")
        return None


def test_merge_features():
    """Test merging external and cross-series features"""
    print("\n" + "=" * 60)
    print("TEST 2: Merge External + Cross-Series Features")
    print("=" * 60)

    try:
        # Load external features
        _, external_dict = load_external_features()

        # Simulate cross-series data
        cross_series_dict = {
            'A.1.a': np.random.randn(731),
            'B.2.c': np.random.randn(731),
        }

        # Merge
        combined = merge_external_features_with_cross_series(
            external_dict,
            cross_series_dict
        )

        print("✓ Successfully merged features")
        print(f"  - Total features: {len(combined)}")
        print(f"  - External features: {len(external_dict)}")
        print(f"  - Cross-series features: {len(cross_series_dict)}")
        print(f"  - Combined keys: {list(combined.keys())}")

        return combined
    except Exception as e:
        print(f"✗ Failed to merge: {e}")
        return None


def test_feature_engineering():
    """Test feature engineering with external features"""
    print("\n" + "=" * 60)
    print("TEST 3: Feature Engineering with External Features")
    print("=" * 60)

    try:
        # Create sample training data
        dates = pd.date_range(start='2024-01-01', end='2025-12-31', freq='D')
        values = np.random.randn(len(dates)).cumsum() + 1000

        train_df = pd.DataFrame({
            'ds': dates,
            'y': values
        })

        print(f"✓ Created sample training data: {len(train_df)} rows")

        # Load external features
        _, external_dict = load_external_features()

        # Create cross-series simulation
        cross_series_dict = {
            'A.1.a': np.random.randn(len(dates)),
            'B.2.c': np.random.randn(len(dates)),
        }

        # Merge
        combined = merge_external_features_with_cross_series(
            external_dict,
            cross_series_dict
        )

        print(f"✓ Merged {len(combined)} external features")

        # Create features
        features_df = create_features_advanced(
            train_df,
            lag_steps=90,
            holidays_list=None,
            external_series=combined
        )

        print(f"✓ Created features dataframe")
        print(f"  - Shape: {features_df.shape}")
        print(f"  - Columns: {len(features_df.columns)}")

        # Check for external feature columns
        external_cols = [col for col in features_df.columns if col.startswith('ext_')]
        print(f"  - External feature columns: {len(external_cols)}")

        if len(external_cols) > 0:
            print(f"  - Sample external columns: {external_cols[:5]}")
        else:
            print("  ⚠ Warning: No external feature columns found!")

        return features_df

    except Exception as e:
        print(f"✗ Failed feature engineering: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_get_info():
    """Test getting file info"""
    print("\n" + "=" * 60)
    print("TEST 4: Get External Features Info")
    print("=" * 60)

    try:
        info = get_external_features_info()
        print("✓ Successfully retrieved info")
        for key, value in info.items():
            print(f"  - {key}: {value}")
    except Exception as e:
        print(f"✗ Failed to get info: {e}")


def test_with_missing_file():
    """Test behavior when file doesn't exist"""
    print("\n" + "=" * 60)
    print("TEST 5: Handle Missing File")
    print("=" * 60)

    try:
        info = get_external_features_info('data/nonexistent.xlsx')
        print("✓ Handled missing file gracefully")
        print(f"  - File exists: {info['exists']}")
    except Exception as e:
        print(f"✗ Failed to handle missing file: {e}")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("EXTERNAL FEATURES INTEGRATION TEST")
    print("=" * 60)

    # Run all tests
    test_get_info()
    test_load_external()
    test_merge_features()
    test_feature_engineering()
    test_with_missing_file()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)
