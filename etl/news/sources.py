"""Adapter sumber berita.

TIDAK ADA SATU SUMBER PUN yang menutup 2006-2026 dengan judul artikel utuh
dan gratis. Itu bukan keterbatasan kode ini, melainkan kenyataan arsip:

  2006-2016  Arsip judul tidak tersedia bebas. Yang ada adalah NADA AGREGAT
             per peristiwa (arsip peristiwa GDELT 1.0, bulanan sejak 2006-01).
             Nada itu dihitung dengan leksikon umum, bukan model keuangan.
  2017-2026  Judul tersedia (GDELT DOC API dan arsip situs media), jadi
             FinBERT bisa dipakai.

Konsekuensinya SATU DERET SENTIMEN YANG SERAGAM DARI 2006 TIDAK BISA DIBUAT
dari sumber gratis. Yang bisa dibuat adalah dua lapis dengan metode berbeda.
Kolom `scorer` di store.py ada supaya patahan metode itu KELIHATAN dan bisa
diuji, bukan tersembunyi di dalam satu kolom yang tampak mulus.

Sebelum memakai deret gabungan itu di model, uji dulu patahannya: bandingkan
sebaran polaritas beberapa tahun sebelum dan sesudah titik sambung. Kalau
rata-rata atau ragamnya melompat, deret itu membawa artefak metode, bukan
hanya sentimen - dan pohon keputusan akan mempelajari tanggal sambungannya.

Setiap adapter mengembalikan iterator dict siap-upsert. Tidak ada yang
menulis ke basis data sendiri; itu tugas run.py.
"""
from __future__ import annotations

import io
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Iterator, Optional

import pandas as pd
import requests

from .store import to_utc

UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120 Safari/537.36')


def _session(rate_delay: float = 1.0) -> requests.Session:
    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Accept': '*/*'})
    s._rate_delay = rate_delay          # dibaca _get()
    return s


def _get(s: requests.Session, url: str, **kw) -> requests.Response:
    """GET dengan jeda tetap.

    Jeda ini BUKAN hiasan. Penarikan 2006-2026 berarti ribuan permintaan ke
    server yang sama; tanpa jeda itu membebani sumber dan hampir pasti
    berujung pemblokiran alamat IP VPS. Jangan menurunkannya di bawah 1 detik
    untuk situs media, dan periksa robots.txt sumbernya sebelum menambah
    adapter baru.
    """
    time.sleep(getattr(s, '_rate_delay', 1.0))
    r = s.get(url, timeout=kw.pop('timeout', 60), **kw)
    r.raise_for_status()
    return r


# ===========================================================================
# GDELT 1.0 - arsip peristiwa, nada agregat, 2006-01 sampai sekarang
# ===========================================================================
GDELT_EVENT_BASE = 'http://data.gdeltproject.org/events/'

# Nama kolom arsip peristiwa GDELT 1.0, menurut buku kodenya.
#
# PERINGATAN: daftar ini TIDAK bisa diverifikasi dari lingkungan pengembangan
# ini karena data.gdeltproject.org diblokir proxy. Karena itu jangan
# dipercaya buta - gdelt_validate() di bawah mencocokkannya dengan berkas
# sungguhan dan MELEMPAR kalau tidak cocok. Jalankan itu sekali di VPS
# sebelum penarikan panjang; kalau GDELT mengubah skemanya, lebih baik
# berhenti keras daripada diam-diam membaca kolom yang salah sebagai nada.
GDELT_V1_COLUMNS = [
    'GLOBALEVENTID', 'SQLDATE', 'MonthYear', 'Year', 'FractionDate',
    'Actor1Code', 'Actor1Name', 'Actor1CountryCode', 'Actor1KnownGroupCode',
    'Actor1EthnicCode', 'Actor1Religion1Code', 'Actor1Religion2Code',
    'Actor1Type1Code', 'Actor1Type2Code', 'Actor1Type3Code',
    'Actor2Code', 'Actor2Name', 'Actor2CountryCode', 'Actor2KnownGroupCode',
    'Actor2EthnicCode', 'Actor2Religion1Code', 'Actor2Religion2Code',
    'Actor2Type1Code', 'Actor2Type2Code', 'Actor2Type3Code',
    'IsRootEvent', 'EventCode', 'EventBaseCode', 'EventRootCode',
    'QuadClass', 'GoldsteinScale', 'NumMentions', 'NumSources',
    'NumArticles', 'AvgTone',
    'Actor1Geo_Type', 'Actor1Geo_FullName', 'Actor1Geo_CountryCode',
    'Actor1Geo_ADM1Code', 'Actor1Geo_Lat', 'Actor1Geo_Long', 'Actor1Geo_FeatureID',
    'Actor2Geo_Type', 'Actor2Geo_FullName', 'Actor2Geo_CountryCode',
    'Actor2Geo_ADM1Code', 'Actor2Geo_Lat', 'Actor2Geo_Long', 'Actor2Geo_FeatureID',
    'ActionGeo_Type', 'ActionGeo_FullName', 'ActionGeo_CountryCode',
    'ActionGeo_ADM1Code', 'ActionGeo_Lat', 'ActionGeo_Long', 'ActionGeo_FeatureID',
    'DATEADDED', 'SOURCEURL',
]

# Negara yang relevan untuk pasokan-permintaan valas Indonesia.
GDELT_COUNTRIES = ('IDN', 'USA')

# AvgTone GDELT secara teori di [-100, 100], tapi sebaran nyatanya hampir
# seluruhnya di [-10, 10]. Dibagi 10 lalu dipotong supaya sepadan dengan
# polaritas FinBERT di [-1, 1]. Penyekalaan ini PILIHAN, bukan sesuatu yang
# baku - dan karena itu kedua lapis tetap tidak benar-benar sepadan. Lihat
# catatan patahan metode di kepala berkas.
GDELT_TONE_SCALE = 10.0


def gdelt_month_urls(start: date, end: date) -> list[str]:
    """Berkas bulanan 2006-01..2013-03, berkas harian sejak 2013-04.

    Pembagian ini milik GDELT, bukan pilihan kita: arsip 1.0 disimpan bulanan
    sampai Maret 2013 lalu harian setelahnya.
    """
    urls, cur = [], date(start.year, start.month, 1)
    daily_from = date(2013, 4, 1)
    while cur <= end:
        if cur < daily_from:
            urls.append(f'{GDELT_EVENT_BASE}{cur:%Y%m}.zip')
            cur = date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)
        else:
            d = max(cur, daily_from)
            while d <= end:
                urls.append(f'{GDELT_EVENT_BASE}{d:%Y%m%d}.export.CSV.zip')
                d += timedelta(days=1)
            break
    return urls


def _gdelt_frame(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        name = z.namelist()[0]
        with z.open(name) as fh:
            return pd.read_csv(fh, sep='\t', header=None, dtype=str,
                               names=GDELT_V1_COLUMNS, on_bad_lines='skip')


def gdelt_validate(content: bytes) -> dict:
    """Cocokkan berkas GDELT sungguhan dengan GDELT_V1_COLUMNS.

    Jalankan SEKALI di VPS sebelum penarikan panjang. Melempar kalau jumlah
    kolomnya tidak cocok atau kolom AvgTone tidak masuk akal sebagai angka -
    dua tanda paling jelas bahwa daftar kolom di atas sudah usang.
    """
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        with z.open(z.namelist()[0]) as fh:
            raw = pd.read_csv(fh, sep='\t', header=None, dtype=str,
                              nrows=200, on_bad_lines='skip')
    n = raw.shape[1]
    if n != len(GDELT_V1_COLUMNS):
        raise ValueError(
            f'GDELT punya {n} kolom, GDELT_V1_COLUMNS punya '
            f'{len(GDELT_V1_COLUMNS)}. Buku kode berubah - perbarui daftarnya '
            f'sebelum menarik apa pun, jangan dipaksa jalan.')
    tone = pd.to_numeric(raw.iloc[:, GDELT_V1_COLUMNS.index('AvgTone')],
                         errors='coerce')
    if tone.isna().mean() > 0.5 or not (-100 <= tone.min() <= tone.max() <= 100):
        raise ValueError(
            f'Kolom AvgTone tidak masuk akal (NaN {tone.isna().mean():.0%}, '
            f'rentang {tone.min()}..{tone.max()}). Kemungkinan urutan kolom '
            f'bergeser.')
    return {'kolom': n, 'tone_min': float(tone.min()),
            'tone_max': float(tone.max()), 'baris_contoh': len(raw)}


def fetch_gdelt(start: date, end: date, rate_delay: float = 1.0,
                countries: tuple = GDELT_COUNTRIES,
                validate_first: bool = True) -> Iterator[dict]:
    """Tarik nada agregat GDELT 1.0 untuk rentang tanggal.

    Menghasilkan SATU baris per peristiwa, sudah membawa polarity - jadi
    tidak perlu dan tidak bisa dinilai FinBERT (tidak ada judulnya).
    """
    s = _session(rate_delay)
    first = True
    for url in gdelt_month_urls(start, end):
        try:
            content = _get(s, url).content
        except Exception as e:                     # berkas hilang itu biasa
            print(f'  lewati {url.rsplit("/", 1)[-1]}: {type(e).__name__}')
            continue
        if first and validate_first:
            print('  validasi skema GDELT:', gdelt_validate(content))
            first = False
        df = _gdelt_frame(content)
        m = (df['Actor1CountryCode'].isin(countries)
             | df['Actor2CountryCode'].isin(countries)
             | df['ActionGeo_CountryCode'].isin(countries))
        df = df[m]
        tone = pd.to_numeric(df['AvgTone'], errors='coerce') / GDELT_TONE_SCALE
        tone = tone.clip(-1, 1)
        for (_, row), pol in zip(df.iterrows(), tone):
            if pd.isna(pol):
                continue
            # SQLDATE adalah tanggal peristiwa tanpa jam. Diasumsikan UTC
            # tengah hari supaya penetapan hari bisnis tidak bergantung pada
            # jam yang memang tidak ada datanya. Ini asumsi, dan dicatat di
            # sini supaya tidak jadi keajaiban di kemudian hari.
            yield {
                'source': 'gdelt', 'url': row.get('SOURCEURL'),
                'title': None, 'language': None,
                'country': row.get('ActionGeo_CountryCode'),
                'published_utc': to_utc(
                    datetime.strptime(str(row['SQLDATE']), '%Y%m%d')
                    .replace(hour=12, tzinfo=timezone.utc)),
                'scorer': 'gdelt-tone', 'polarity': float(pol),
            }


# ===========================================================================
# Arsip situs media - digerakkan konfigurasi, bukan satu kelas per situs
# ===========================================================================
# Setiap situs Indonesia punya pola indeks harian sendiri. Alih-alih menulis
# satu adapter per situs, polanya ditaruh di sini sebagai data. Selector HTML
# TIDAK bisa saya uji dari lingkungan ini (seluruh situs diblokir proxy), jadi
# nilai di bawah adalah TITIK AWAL yang wajib diperiksa dengan
# utils/test_scraping_selector.py sebelum dipakai.
#
# Perhatikan juga: situs berita mengubah tata letaknya beberapa kali dalam 20
# tahun. Satu selector hampir pasti tidak cukup untuk 2006-2026; sediakan
# beberapa kandidat dan ambil yang pertama berhasil.
SITE_CONFIGS = {
    'detik': {
        'index': 'https://finance.detik.com/indeks?date={d:%m/%d/%Y}',
        'item': ['article .media__title a', '.list-content__item .media__title a',
                 'article h2 a', '.list_content article a'],
        'tz': 7, 'language': 'id', 'country': 'ID',
    },
    'kontan': {
        'index': 'https://www.kontan.co.id/indeks?tanggal={d:%d}&bulan={d:%m}&tahun={d:%Y}',
        'item': ['.list-berita li h1 a', '.sp-hl a', 'li .linkto-black'],
        'tz': 7, 'language': 'id', 'country': 'ID',
    },
    'antara': {
        'index': 'https://www.antaranews.com/indeks/ekonomi/{d:%Y/%m/%d}',
        'item': ['.simple-post h3 a', 'article h3 a'],
        'tz': 7, 'language': 'id', 'country': 'ID',
    },
}


def fetch_site_archive(site: str, start: date, end: date,
                       rate_delay: float = 1.5,
                       max_days: Optional[int] = None) -> Iterator[dict]:
    """Telusuri indeks harian satu situs dan ambil judulnya.

    Sengaja hanya JUDUL, bukan isi artikel: mengambil isi berarti satu
    permintaan tambahan PER ARTIKEL, yang untuk 20 tahun berarti ratusan ribu
    permintaan tambahan. Judul sudah cukup untuk FinBERT, dan itu pun batasan
    yang sudah dinyatakan di naskah.
    """
    from bs4 import BeautifulSoup          # lokal: hanya jalur ini yang butuh

    cfg = SITE_CONFIGS[site]
    tz = timezone(timedelta(hours=cfg['tz']))
    s = _session(rate_delay)
    d, n = start, 0
    while d <= end and (max_days is None or n < max_days):
        try:
            html = _get(s, cfg['index'].format(d=d)).text
            soup = BeautifulSoup(html, 'html.parser')
            links = []
            for sel in cfg['item']:
                links = soup.select(sel)
                if links:
                    break
            if not links:
                # Nol tautan berarti selector-nya sudah tidak cocok untuk era
                # ini, BUKAN berarti tidak ada berita. Dilaporkan supaya
                # ketahuan, bukan dilewati diam-diam sebagai hari sepi.
                print(f'  [{site}] {d}: 0 tautan - periksa selector untuk era ini')
            for a in links:
                title = a.get_text(strip=True)
                if not title:
                    continue
                yield {
                    'source': site, 'url': a.get('href'), 'title': title,
                    'language': cfg['language'], 'country': cfg['country'],
                    # Indeks harian hanya memberi tanggal. Jam diasumsikan
                    # 12.00 zona lokal situs - di bawah batas 16.00 WIB, jadi
                    # artikel tetap masuk ke harinya sendiri.
                    'published_utc': to_utc(
                        datetime(d.year, d.month, d.day, 12, tzinfo=tz)),
                }
        except Exception as e:
            print(f'  [{site}] {d}: GAGAL {type(e).__name__}')
        d += timedelta(days=1)
        n += 1
