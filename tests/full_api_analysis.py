"""
Full API Response Analysis - Semua 4 kategori
"""
import pandas as pd
import xmltodict

# All 4 XML responses dari user (full data)
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
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>09 - Investasi Pembelian Obligasi Korporasi</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>100.48</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>38 - penjualan barang.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-20.46</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>29 - transaksi valuta asing yang dilakukan Bank dengan Nasabah tanpa underlying</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-972.8</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>05 - Import</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>12172.53</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>06 - Penjualan Devisa Hasil Ekspor</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-2.3</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>31 - biaya administrasi.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>8.56</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>42 - repatriasi atas penghasilan dari jasa yang dilakukan di dalam negeri.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-140.95</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>19 - Repatriasi dana hasil penjualan saham</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>4.82</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>20 - Repatriasi dana penjualan SBN</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>0.1</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>22 - Dana Hasil Penjualan</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>0.09</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>16 - Sosial (Konversi hasil sumbangan/grant)</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>58.45</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>37 - pembelian barang.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>1828.36</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>33 - pembayaran pajak.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>7.16</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>14 - Biaya Perjalanan Luar Negeri</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>298.57</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>40 - penjualan jasa.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-11.62</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>43 - Lindung nilai atas kepemilikan valuta asing</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>546.6</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>34 - pembayaran hutang.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>152.08</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>39 - pembelian jasa.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-332.28</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>35 - penambahan modal kerja.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-39.66</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>28 - kegiatan remittance.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>1404.21</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>04 - Pembayaran Pinjaman Luar Negeri</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>105.05</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>08 - Investasi Pembelian SBN</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>2420.79</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>13 - Biaya Pendidikan</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>72.14</VOLUME_NETT_RIBU_USD>
</row>
</rows>
</result>''',

    'Asing': '''<result>
<rows>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>07 - Investasi Pembelian Saham</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-85748.48</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>24 - Disimpan pada rekening valas Dalam Negeri</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>575.44</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>01 - Investasi Pemberian Kredit</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-2734.58</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>38 - penjualan barang.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-30.7</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>29 - transaksi valuta asing yang dilakukan Bank dengan Nasabah tanpa underlying</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-10336.94</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>20 - Repatriasi dana penjualan SBN</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>63163.42</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>05 - Import</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>969.42</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>19 - Repatriasi dana hasil penjualan saham</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>213852.08</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>42 - repatriasi atas penghasilan dari jasa yang dilakukan di dalam negeri.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>6060.05</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>06 - Penjualan Devisa Hasil Ekspor</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-300</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>27 - transaksi antarbank dalam rangka cover posisi Bank kepada bank luar negeri atau pihak luar.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-13436.09</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>37 - pembelian barang.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>3173.54</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>14 - Biaya Perjalanan Luar Negeri</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-7.87</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>43 - Lindung nilai atas kepemilikan valuta asing</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>84.77</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>23 - Repatriasi dividen dan kupon</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>403.95</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>39 - pembelian jasa.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>3086.28</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>25 - transaksi antarbank dalam rangka trading.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-25679.47</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>35 - penambahan modal kerja.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-8</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>26 - transaksi antarbank dalam rangka cover posisi nasabah kepada Bank di dalam negeri.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-5229.16</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>28 - kegiatan remittance.</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-3612.1</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>08 - Investasi Pembelian SBN</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-30144.14</VOLUME_NETT_RIBU_USD>
</row>
<row>
<TANGGAL_LAPORAN>2025-11-11</TANGGAL_LAPORAN>
<TUJUAN_TRANSAKSI>13 - Biaya Pendidikan</TUJUAN_TRANSAKSI>
<VOLUME_NETT_RIBU_USD>-3.53</VOLUME_NETT_RIBU_USD>
</row>
</rows>
</result>'''
}

def analyze_category(xml_text, category_name):
    """Analyze XML response"""
    print(f"\n{'='*70}")
    print(f"{category_name.upper()}")
    print(f"{'='*70}")

    data_dict = xmltodict.parse(xml_text)
    rows = data_dict['result']['rows']['row']
    df = pd.DataFrame(rows)

    df['transaction_code'] = df['TUJUAN_TRANSAKSI'].str.extract(r'^(\d+)')[0].astype(int)
    df['VOLUME_NETT_RIBU_USD'] = pd.to_numeric(df['VOLUME_NETT_RIBU_USD'])

    print(f"Total rows: {len(df)}")
    print(f"Unique codes: {df['transaction_code'].nunique()}")

    # Check duplicates
    duplicates = df.groupby(['TANGGAL_LAPORAN', 'transaction_code']).size()
    duplicates = duplicates[duplicates > 1]

    if not duplicates.empty:
        print(f"\n❌ DUPLICATE KEYS DETECTED:")
        for (date, code), count in duplicates.items():
            print(f"  Code x{code:02d}: {count} rows")
            dup_rows = df[df['transaction_code'] == code]
            for idx, row in dup_rows.iterrows():
                print(f"    - {row['VOLUME_NETT_RIBU_USD']:>12.2f} | {row['TUJUAN_TRANSAKSI'][:60]}")
            print(f"    SUM: {dup_rows['VOLUME_NETT_RIBU_USD'].sum():>12.2f}")
        return True
    else:
        print(f"✓ No duplicates")
        return False

# Run analysis
has_duplicates = False
for category, xml in xml_responses.items():
    if analyze_category(xml, category):
        has_duplicates = True

print(f"\n{'='*70}")
print(f"CONCLUSION")
print(f"{'='*70}")
if not has_duplicates:
    print(f"\n✓ NO DUPLICATE KEYS found in any category")
    print(f"\nKesimpulan:")
    print(f"- PTMN: 3 rows (sangat sedikit - perlu dicek normalnya berapa)")
    print(f"- Individu: 29 rows")
    print(f"- Asing: 22 rows")
    print(f"- Korporasi: (tidak ada data sample)")
    print(f"\nJika ada error 'duplicate keys', kemungkinan:")
    print(f"1. Terjadi di Korporasi (tidak ada sample XML)")
    print(f"2. Terjadi di tanggal lain")
    print(f"3. Kode sudah handle sum duplicates (api_client.py:232)")
else:
    print(f"\n❌ DUPLICATE KEYS FOUND - see details above")
