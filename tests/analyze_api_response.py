"""
Analyze API Response untuk debugging duplicate keys dan missing data
"""
import pandas as pd
import xmltodict

# Sample XML responses dari user
xml_responses = {
    'PTMN': '''<result>
<rows>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>29 - transaksi valuta asing yang dilakukan Bank dengan Nasabah tanpa underlying</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-205.45</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>37 - pembelian barang.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>118.25</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>43 - Lindung nilai atas kepemilikan valuta asing</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-1063.78</VOLUME_NETT_RIBU_USD>
</row>
</rows>
</result>''',

    'Individu': '''<result>
<rows>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>01 - Investasi Pemberian Kredit</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-144.45</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>07 - Investasi Pembelian Saham</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>26.11</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>24 - Disimpan pada rekening valas Dalam Negeri</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>851.68</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>30 - biaya overhead.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>64.24</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>41 - untuk pencairan bunga dan/atau pokok dari penempatan pada rekening valas dalam negeri.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-610.33</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>00 - Investasi Penyertaan Langsung</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>5.45</VOLUME_NETT_RIBU_USD>
</row>
</rows>
</result>'''
}

def analyze_xml_response(xml_text, category_name):
    """Analyze XML response untuk check duplicates dan missing data"""
    print(f"\n{'='*70}")
    print(f"Analyzing {category_name}")
    print(f"{'='*70}")

    # Parse XML
    data_dict = xmltodict.parse(xml_text)
    rows = data_dict['result']['rows']['row']
    df = pd.DataFrame(rows)

    # Extract transaction code
    df['transaction_code'] = df['TUJUAN_TRANSAKSI'].str.extract(r'^(\d+)')[0].astype(int)
    df['VOLUME_NETT_RIBU_USD'] = pd.to_numeric(df['VOLUME_NETT_RIBU_USD'])

    print(f"\nTotal rows: {len(df)}")
    print(f"Unique transaction codes: {df['transaction_code'].nunique()}")
    print(f"Date: {df['TANGGAL_LAPORAN'].iloc[0]}")

    # Check for duplicates
    duplicates = df.groupby(['TANGGAL_LAPORAN', 'transaction_code']).size()
    duplicates = duplicates[duplicates > 1]

    if not duplicates.empty:
        print(f"\n⚠️  DUPLICATE KEYS FOUND:")
        for (date, code), count in duplicates.items():
            print(f"  - Date {date}, Code {code}: {count} occurrences")
            duplicate_rows = df[df['transaction_code'] == code]
            print(f"    Values: {duplicate_rows['VOLUME_NETT_RIBU_USD'].tolist()}")
            print(f"    Sum: {duplicate_rows['VOLUME_NETT_RIBU_USD'].sum()}")
    else:
        print(f"\n✓ No duplicate keys")

    # Show transaction codes
    print(f"\nTransaction codes present:")
    for idx, row in df.sort_values('transaction_code').iterrows():
        print(f"  x{row['transaction_code']:02d}: {row['VOLUME_NETT_RIBU_USD']:>12.2f} - {row['TUJUAN_TRANSAKSI'][:50]}")

    # Check for missing codes (expected range: 0-47)
    all_codes = set(range(0, 48))
    present_codes = set(df['transaction_code'].unique())
    missing_codes = sorted(all_codes - present_codes)

    if missing_codes:
        print(f"\nMissing transaction codes ({len(missing_codes)}):")
        print(f"  {', '.join([f'x{c:02d}' for c in missing_codes[:20]])}")
        if len(missing_codes) > 20:
            print(f"  ... and {len(missing_codes) - 20} more")

    return df

# Analyze each category
for category, xml_text in xml_responses.items():
    df = analyze_xml_response(xml_text, category)

print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
print(f"\nPTMN: 3 transactions (very few - check if this is normal)")
print(f"Individu: Sample shows 6 transactions (partial data shown)")
print(f"\nPotential issues:")
print(f"1. If API returns duplicate transaction codes for same date:")
print(f"   → Code will sum the values (handled in api_client.py:232)")
print(f"2. If PTMN normally has more data:")
print(f"   → Check endpoint TTS_SDV_PERTAMINA configuration")
print(f"3. Missing codes will be filled with 0 (expected behavior)")
