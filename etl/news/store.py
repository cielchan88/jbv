"""Penyimpanan korpus berita untuk analisis sentimen.

Satu tabel SQLite, bukan kumpulan Excel. Alasannya praktis: rentang
2006-2026 berpotensi ratusan ribu artikel, penarikannya bertahap selama
berhari-hari, dan harus bisa dilanjutkan setelah putus. Excel tidak bisa
ditulis sebagian, tidak punya indeks, dan harus dimuat penuh ke memori
setiap kali.

DUA KEPUTUSAN YANG MENENTUKAN KREDIBILITAS

1. Waktu terbit disimpan dalam UTC yang sadar-zona, BUKAN tanggal polos.
   Sumber berita memberi cap waktu dalam zona yang berbeda-beda (WIB untuk
   media Indonesia, UTC atau ET untuk media asing). Kalau disimpan sebagai
   tanggal polos, artikel yang terbit 23.00 WIB dan 23.00 ET bisa jatuh di
   hari yang berbeda tanpa ada yang tahu.

2. Tanggal bisnis dihitung dari cap waktu itu dengan BATAS yang eksplisit,
   lihat business_date(). Ini satu-satunya pertahanan terhadap look-ahead:
   berita yang terbit setelah batas tidak boleh masuk ke hari itu, karena
   pada saat prakiraan dibuat berita tersebut belum ada.

Skema sengaja memisahkan PENGUMPULAN dari PENILAIAN. Kolom sentimen boleh
kosong; artikel tetap sah tanpa skor. Dengan begitu korpus cukup dikumpulkan
sekali, lalu bisa dinilai ulang berkali-kali ketika metodenya berubah -
tanpa menarik ulang apa pun.
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

import pandas as pd

# Zona waktu acuan. Panel SDV adalah data Bank Indonesia, jadi hari bisnisnya
# hari kerja Jakarta.
WIB = timezone(timedelta(hours=7))

# Batas penetapan hari bisnis, dalam jam WIB.
#
# Berita yang terbit SETELAH jam ini ditetapkan ke hari bisnis BERIKUTNYA.
#
# 16.00 dipilih karena kira-kira penutupan pasar domestik: prakiraan untuk
# besok disusun setelah pasar tutup, jadi seluruh berita sampai jam itu sudah
# tersedia bagi penyusunnya, dan berita setelahnya belum. Menaikkannya ke
# 23.59 berarti mengklaim penyusun prakiraan sudah membaca berita tengah malam
# - itu boleh saja, asal disadari dan dinyatakan. Jangan mengubahnya diam-diam:
# angka ini menentukan sah atau tidaknya seluruh hasil.
ASSIGN_CUTOFF_HOUR_WIB = 16

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    uid            TEXT PRIMARY KEY,   -- sidik jari isi, lihat make_uid()
    source         TEXT NOT NULL,      -- nama adapter, mis. 'gdelt', 'detik'
    url            TEXT,
    -- Judul BOLEH kosong. Sumber nada agregat seperti arsip peristiwa GDELT
    -- memberi skor tanpa judul sama sekali; baris seperti itu tetap sah asal
    -- membawa polarity-nya sendiri. Lihat syaratnya di upsert().
    title          TEXT,
    body           TEXT,               -- opsional; banyak sumber hanya judul
    language       TEXT,               -- 'en' / 'id'
    country        TEXT,               -- 'US' / 'ID' / NULL
    published_utc  TEXT NOT NULL,      -- ISO8601 dengan offset, selalu UTC
    business_date  TEXT NOT NULL,      -- YYYY-MM-DD, hasil business_date()
    cutoff_hour    INTEGER NOT NULL,   -- batas yang dipakai saat baris ditulis
    fetched_utc    TEXT NOT NULL,
    -- kolom penilaian, diisi belakangan oleh tahap sentimen
    scorer         TEXT,               -- 'finbert-v3' / 'gdelt-tone' / NULL
    polarity       REAL,               -- [-1, 1]; NULL berarti belum dinilai
    p_positive     REAL,
    p_negative     REAL,
    p_neutral      REAL,
    scored_utc     TEXT
);
CREATE INDEX IF NOT EXISTS ix_bdate  ON articles(business_date);
CREATE INDEX IF NOT EXISTS ix_scorer ON articles(scorer);
CREATE INDEX IF NOT EXISTS ix_source ON articles(source);
"""

DEFAULT_DB = Path('data/news/corpus.sqlite')


def make_uid(url: Optional[str], title: str, published_utc: str) -> str:
    """Sidik jari untuk deduplikasi.

    URL saja tidak cukup: satu berita kantor berita dimuat ulang di banyak
    situs dengan URL berbeda, dan sebaliknya satu URL bisa berubah isinya.
    Judul saja juga tidak cukup: judul pendek seperti 'Rupiah Menguat' muncul
    ratusan kali di tanggal berbeda.

    Karena itu kuncinya judul yang sudah dinormalkan + tanggal terbit. URL
    ikut kalau ada, supaya dua berita berjudul sama di hari sama dari dua
    media tetap terhitung dua - itu memang dua sinyal.
    """
    t = ' '.join(str(title or '').lower().split())
    day = str(published_utc)[:10]
    key = f'{t}|{day}|{url or ""}'
    return hashlib.sha1(key.encode('utf-8')).hexdigest()


def business_date(published_utc: datetime,
                  cutoff_hour: int = ASSIGN_CUTOFF_HOUR_WIB) -> str:
    """Tetapkan artikel ke hari bisnis, dengan batas eksplisit.

    Berita yang terbit setelah `cutoff_hour` WIB masuk ke hari berikutnya,
    karena belum tersedia saat prakiraan hari itu disusun.

    Catatan: fungsi ini TIDAK melompati akhir pekan. Berita Sabtu tetap
    bertanggal Sabtu. Pemetaan ke hari kerja dilakukan di tahap agregasi,
    yang tahu kalender panelnya - lihat daily.py.
    """
    if published_utc.tzinfo is None:
        raise ValueError('published_utc harus sadar-zona; tanggal polos '
                         'membuat penetapan hari bisnis tidak bisa diverifikasi')
    local = published_utc.astimezone(WIB)
    if local.hour >= cutoff_hour:
        local = local + timedelta(days=1)
    return local.date().isoformat()


def to_utc(ts, assume_tz: timezone = WIB) -> datetime:
    """Ubah cap waktu apa pun jadi datetime UTC sadar-zona.

    `assume_tz` dipakai HANYA kalau cap waktunya tidak membawa zona. Setiap
    adapter wajib menyatakan zona asumsinya sendiri - menebak diam-diam di
    sini adalah cara paling mudah menyelundupkan kesalahan sehari.
    """
    t = pd.to_datetime(ts, utc=False, format='mixed', errors='coerce')
    if pd.isna(t):
        raise ValueError(f'cap waktu tidak terbaca: {ts!r}')
    t = t.to_pydatetime() if hasattr(t, 'to_pydatetime') else t
    if t.tzinfo is None:
        t = t.replace(tzinfo=assume_tz)
    return t.astimezone(timezone.utc)


@contextmanager
def connect(db_path: Path | str = DEFAULT_DB) -> Iterator[sqlite3.Connection]:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    try:
        con.executescript(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def upsert(con: sqlite3.Connection, records: Iterable[dict]) -> dict:
    """Sisipkan artikel, lewati yang sudah ada.

    INSERT OR IGNORE dipakai dengan sengaja: penarikan ulang rentang yang
    sama tidak boleh menimpa skor sentimen yang sudah dihitung. Menarik ulang
    itu normal - rentang bertumpuk, proses putus lalu diulang - jadi jalur ini
    harus murah dan tidak merusak.
    """
    rows, seen = [], set()
    now = datetime.now(timezone.utc).isoformat()
    for r in records:
        pub = r['published_utc']
        pub = pub if isinstance(pub, datetime) else to_utc(pub)
        title = str(r.get('title') or '').strip() or None
        # Baris tanpa judul HANYA sah kalau sudah membawa skornya sendiri
        # (mis. nada agregat GDELT). Tanpa keduanya tidak ada yang bisa dinilai
        # sekarang maupun nanti, jadi baris itu hanya akan jadi sampah.
        if title is None and r.get('polarity') is None:
            continue
        cutoff = int(r.get('cutoff_hour', ASSIGN_CUTOFF_HOUR_WIB))
        uid = make_uid(r.get('url'), title, pub.isoformat())
        if uid in seen:
            continue                      # duplikat di dalam satu batch
        seen.add(uid)
        rows.append((
            uid, r['source'], r.get('url'), title, r.get('body'),
            r.get('language'), r.get('country'),
            pub.isoformat(), business_date(pub, cutoff), cutoff, now,
            r.get('scorer'), r.get('polarity'),
            r.get('p_positive'), r.get('p_negative'), r.get('p_neutral'),
            r.get('scored_utc'),
        ))
    before = con.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
    con.executemany(
        'INSERT OR IGNORE INTO articles VALUES (' + ','.join(['?'] * 17) + ')',
        rows)
    after = con.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
    return {'diterima': len(rows), 'baru': after - before,
            'duplikat': len(rows) - (after - before)}


def coverage(con: sqlite3.Connection) -> pd.DataFrame:
    """Cakupan per tahun per sumber - untuk melihat lubang sebelum memakainya."""
    return pd.read_sql_query("""
        SELECT substr(business_date,1,4) AS tahun, source,
               COUNT(*) AS artikel,
               COUNT(DISTINCT business_date) AS hari,
               SUM(polarity IS NOT NULL) AS dinilai
        FROM articles GROUP BY tahun, source ORDER BY tahun, source
    """, con)


def unscored(con: sqlite3.Connection, scorer: str,
             limit: Optional[int] = None) -> pd.DataFrame:
    """Artikel yang belum dinilai oleh `scorer` ini.

    Dipakai supaya penilaian bisa dilanjutkan: proses yang mati di tengah
    tinggal dijalankan lagi, tidak ada yang dihitung dua kali.
    """
    # Baris tanpa judul TIDAK ikut diantre. Baris seperti itu berasal dari
    # sumber nada agregat dan sudah membawa polarity-nya sendiri; FinBERT
    # tidak punya apa pun untuk dibaca di sana. Tanpa syarat ini baris itu
    # akan muncul di setiap antrean selamanya, karena nama scorer-nya memang
    # tidak akan pernah cocok.
    q = ('SELECT uid, title FROM articles '
         'WHERE title IS NOT NULL AND length(title) > 0 '
         '  AND (polarity IS NULL OR scorer IS NULL OR scorer != ?)')
    if limit:
        q += f' LIMIT {int(limit)}'
    return pd.read_sql_query(q, con, params=(scorer,))


def write_scores(con: sqlite3.Connection, scorer: str,
                 scores: Sequence[tuple]) -> int:
    """Tulis hasil penilaian. `scores` = [(uid, pol, ppos, pneg, pneu), ...]"""
    now = datetime.now(timezone.utc).isoformat()
    con.executemany(
        'UPDATE articles SET scorer=?, polarity=?, p_positive=?, '
        'p_negative=?, p_neutral=?, scored_utc=? WHERE uid=?',
        [(scorer, p, pp, pn, pu, now, uid) for uid, p, pp, pn, pu in scores])
    return len(scores)
