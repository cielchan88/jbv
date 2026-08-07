"""
Test Script untuk API CData Virtuality
========================================

Script ini untuk test API connection dan melihat output data.
Jalankan saat sudah terhubung ke network BI.

Usage:
    python test_api.py
"""

from etl.api_client import test_api_connection, fetch_api_data, transform_api_to_wide, parse_xml_response
import pandas as pd

def main():
    print("\n" + "="*80)
    print(" TEST API CDATA VIRTUALITY")
    print("="*80 + "\n")

    # Step 1: Test Connection
    print("STEP 1: Testing API Connection...")
    print("-" * 80)
    status = test_api_connection()

    for endpoint, result in status.items():
        emoji = "✅" if result['status'] == 'OK' else "❌"
        print(f"{emoji} {endpoint.upper():20s}: {result['status']:10s} - {result['message']}")

    print()

    # Check if any endpoint is OK
    has_connection = any(s['status'] == 'OK' for s in status.values())

    if not has_connection:
        print("\n⚠️  TIDAK BISA CONNECT KE API")
        print("   Pastikan:")
        print("   1. Sudah terhubung ke VPN BI")
        print("   2. URL API benar")
        print("   3. Network internal BI accessible")
        return

    print("\n" + "="*80)
    print("STEP 2: Fetching Data from API")
    print("="*80 + "\n")

    # Step 2: Fetch data from each endpoint
    for endpoint_key in ['korporasi', 'ptmn', 'asing', 'individu']:
        if status[endpoint_key]['status'] != 'OK':
            print(f"⏭️  Skipping {endpoint_key} (connection failed)")
            continue

        print(f"\n{'='*80}")
        print(f" ENDPOINT: {endpoint_key.upper()}")
        print(f"{'='*80}\n")

        try:
            # Fetch raw data
            print(f"Fetching data from {endpoint_key}...")
            df_long = fetch_api_data(endpoint_key, verify_ssl=False)

            # Show raw API response (long format)
            print("\n📋 RAW API DATA (Long Format):")
            print("-" * 80)
            print(df_long.head(10).to_string())
            print(f"\nTotal records: {len(df_long)}")
            print(f"Unique dates: {df_long['TANGGAL_LAPORAN'].nunique()}")
            print(f"Date range: {df_long['TANGGAL_LAPORAN'].min()} to {df_long['TANGGAL_LAPORAN'].max()}")
            print(f"Transaction categories: {df_long['TUJUAN_TRANSAKSI'].nunique()}")

            # Show summary by transaction
            print("\n📊 SUMMARY BY TRANSACTION:")
            print("-" * 80)
            summary = df_long.groupby('TUJUAN_TRANSAKSI')['VOLUME_NETT_RIBU_USD'].sum().sort_values(ascending=False)
            print(summary.to_string())

            # Transform to wide format
            print(f"\n🔄 Transforming to wide format (Excel-compatible)...")
            df_wide = transform_api_to_wide(df_long)

            print("\n📋 WIDE FORMAT (Excel-compatible):")
            print("-" * 80)
            print(df_wide.to_string())
            print(f"\nShape: {df_wide.shape}")
            print(f"Columns: {list(df_wide.columns[:10])}... (total: {len(df_wide.columns)})")

            # Save to CSV for inspection
            output_file = f"test_output_{endpoint_key}.csv"
            df_wide.to_csv(output_file, index=False)
            print(f"\n💾 Saved to: {output_file}")

        except Exception as e:
            print(f"\n❌ ERROR fetching {endpoint_key}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*80)
    print(" TEST COMPLETED")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
