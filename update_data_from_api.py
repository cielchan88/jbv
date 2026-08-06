"""
Update Data from API
====================

Wrapper script untuk fetch data dari API dan update source-data.xlsx.
Run script ini untuk update data terbaru dari API BI.

Usage:
    python update_data_from_api.py

Requirements:
    - VPN connection to BI network
    - Valid credentials in config.py

Author: Data Processing Team
Date: 2025-12-12
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import and run the main script
from scripts.fetch_api_and_append import fetch_and_append_to_source

if __name__ == "__main__":
    print("\n" + "="*70)
    print("UPDATE DATA FROM API")
    print("="*70)
    print("\nThis will:")
    print("  1. Fetch latest data from 4 API endpoints")
    print("  2. Backup current data/raw/source-data.xlsx")
    print("  3. Append new data to source-data.xlsx")
    print("  4. Trigger ETL pipeline automatically on next dashboard load")
    print("\n" + "="*70)

    # Confirm before proceeding
    response = input("\nProceed? (y/n): ")

    if response.lower() != 'y':
        print("\n❌ Cancelled by user")
        sys.exit(0)

    print("\n" + "="*70)

    # Run the update
    result = fetch_and_append_to_source()

    if result:
        print("\n" + "="*70)
        print("✅ UPDATE SUCCESSFUL")
        print("="*70)
        print(f"\nData updated: {result}")
        print("\nNext steps:")
        print("  1. Data has been appended to source-data.xlsx")
        print("  2. Open Streamlit dashboard")
        print("  3. ETL pipeline will run automatically")
        print("  4. New data will be visible in Eksplorasi page")
        print("\nBackup location: data/raw/backup/")
        print("="*70)
    else:
        print("\n" + "="*70)
        print("❌ UPDATE FAILED")
        print("="*70)
        print("\nPossible reasons:")
        print("  - No VPN connection to BI network")
        print("  - Invalid credentials in config.py")
        print("  - API endpoint unavailable")
        print("  - Network timeout")
        print("\nCheck the logs above for details")
        print("="*70)
        sys.exit(1)
