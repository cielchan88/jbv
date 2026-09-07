"""
Bangun fitur makro berfrekuensi tinggi untuk data/external_features.xlsx.

Variabel yang ditangani:
  - usdidr   : nilai tukar USD/IDR
  - ihsg     : indeks harga saham gabungan
  - sbn10y   : yield SBN tenor 10 tahun (persen)

Keluarannya berkas Excel siap unggah lewat laman "Fitur Eksternal". Kolom yang
sudah ada di berkas lama (sentimen, flows) dipertahankan; kolom makro baru
ditambahkan atau ditimpa.

------------------------------------------------------------------------------
DUA JEBAKAN DI DATA INI - dibaca sebelum mengubah apa pun.

1. NOL BUKAN HARGA. Di external_features.xlsx yang ada sekarang,
   closing_usdidr_mid memuat 831 nilai nol dari 2467 baris. Itu hari non-
   perdagangan (akhir pekan dan libur), bukan kurs nol. Kalau dideferensiasi
   mentah, setiap akhir pekan menghasilkan imbal hasil -100% lalu +tak hingga.
   Karena itu nol diperlakukan sebagai hilang, lalu di-ffill: harga terakhir
   yang diketahui berlaku sampai ada kuotasi baru. Ini juga yang benar secara
   ekonomi - pasar tutup, harganya tidak berubah.

2. JANGAN PAKAI NILAI MASA DEPAN. Semua jendela bergulir di sini backward-
   looking (bawaan pandas), dan ffill hanya merambat maju. Tidak ada bfill,
   karena mengisi mundur berarti memakai harga yang belum terjadi pada tanggal
   itu - kebocoran informasi yang persis dikritik di naskah evaluasi.
------------------------------------------------------------------------------

Pemakaian:

    # dari CSV yang diekspor sendiri (kolom: tanggal, nilai)
    python -m etl.fetch_macro_features \\
        --ihsg-csv ihsg.csv --sbn10y-csv sbn10y.csv -o data/external_new.xlsx

    # ambil otomatis dari Yahoo Finance (butuh akses internet keluar)
    python -m etl.fetch_macro_features --yahoo -o data/external_new.xlsx

USD/IDR tidak perlu diunduh kalau berkas lama sudah memuat closing_usdidr_mid:
skrip memakainya sebagai sumber, jadi deret kurs langsung terbentuk tanpa
akses jaringan sama sekali.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_IN = BASE_DIR / "data" / "external_features.xlsx"
DATE_COL = "Tanggal"

# Simbol Yahoo Finance. SBN 10 tahun tidak tersedia di sana - lihat catatan
# di bawah pada fetch_yahoo().
YAHOO = {"usdidr": "IDR=X", "ihsg": "^JKSE"}


# ---------------------------------------------------------------------------
# Pembacaan sumber
# ---------------------------------------------------------------------------
def read_series_csv(path: str, name: str) -> pd.Series:
    """Baca CSV dua kolom (tanggal, nilai) menjadi Series berindeks tanggal.

    Nama kolom bebas: kolom pertama dianggap tanggal, kolom numerik pertama
    dianggap nilainya. Ini disengaja supaya ekspor dari Bloomberg, Refinitiv,
    investing.com, atau spreadsheet mana pun bisa langsung dipakai tanpa
    penyesuaian header.
    """
    df = pd.read_csv(path)
    if df.shape[1] < 2:
        raise ValueError(f"{path}: butuh minimal dua kolom (tanggal, nilai)")

    dates = pd.to_datetime(df.iloc[:, 0], errors="coerce", dayfirst=False)
    val = None
    for c in df.columns[1:]:
        v = pd.to_numeric(
            df[c].astype(str).str.replace(",", "", regex=False), errors="coerce"
        )
        if v.notna().sum() > 0:
            val = v
            break
    if val is None:
        raise ValueError(f"{path}: tidak ada kolom numerik selain tanggal")

    s = pd.Series(val.to_numpy(), index=dates, name=name)
    s = s[s.index.notna()].sort_index()
    s = s[~s.index.duplicated(keep="last")]
    print(f"  {name:8s} dari {path}: {len(s)} baris, "
          f"{s.index.min().date()} -> {s.index.max().date()}")
    return s


def fetch_yahoo(symbol: str, name: str, start: str = "2019-01-01") -> pd.Series:
    """Ambil harga penutupan harian dari API chart Yahoo Finance.

    Dipakai untuk USD/IDR dan IHSG. Yield SBN 10 tahun TIDAK tersedia di Yahoo
    dan memang tidak dicoba di sini - sumber yang tepat untuknya adalah IBPA/PHEI
    atau data internal, dan disalurkan lewat --sbn10y-csv.
    """
    import json
    import urllib.request

    t0 = int(pd.Timestamp(start).timestamp())
    t1 = int(pd.Timestamp.now().timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?period1={t0}&period2={t1}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)

    res = payload["chart"]["result"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
    close = res["indicators"]["quote"][0]["close"]
    s = pd.Series(close, index=idx, name=name).dropna()
    s = s[~s.index.duplicated(keep="last")]
    print(f"  {name:8s} dari Yahoo ({symbol}): {len(s)} baris, "
          f"{s.index.min().date()} -> {s.index.max().date()}")
    return s


# ---------------------------------------------------------------------------
# Rekayasa fitur
# ---------------------------------------------------------------------------
def clean_level(s: pd.Series) -> pd.Series:
    """Nol dan non-positif diperlakukan sebagai hilang, lalu di-ffill.

    Lihat jebakan nomor 1 di docstring modul. Untuk harga dan indeks, nol
    tidak mungkin merupakan nilai sah.
    """
    s = pd.to_numeric(s, errors="coerce")
    return s.mask(s <= 0).ffill()


def clean_yield(s: pd.Series) -> pd.Series:
    """Untuk yield, nol secara teori mungkin tapi dalam praktik menandakan hari
    non-perdagangan pada deret SBN. Diperlakukan sama: hilang lalu ffill."""
    s = pd.to_numeric(s, errors="coerce")
    return s.mask(s == 0).ffill()


def build_features(s: pd.Series, name: str, kind: str) -> pd.DataFrame:
    """Turunkan fitur pergerakan dari satu deret level.

    Empat fitur per variabel, sengaja dijaga sedikit. Naskah evaluasi menemukan
    bahwa keluarga selisih dan rata-rata eksponensial menyumbang 38,6% importance
    dari hanya 8,7% slot, sedangkan momen bergulir yang saling kolinear memakan
    separuh anggaran fitur dan menyumbang kurang dari sepertiga. Menambah belasan
    fitur level yang saling berkorelasi justru memperburuk seleksi, jadi yang
    dibentuk di sini terutama PERGERAKAN, bukan level.

    kind='price' -> perubahan dinyatakan sebagai imbal hasil logaritmik (persen)
    kind='yield' -> perubahan dinyatakan sebagai selisih (basis poin)
    """
    lvl = clean_level(s) if kind == "price" else clean_yield(s)

    if kind == "price":
        d1 = np.log(lvl).diff() * 100.0
        d5 = np.log(lvl).diff(5) * 100.0
    else:
        d1 = lvl.diff() * 100.0
        d5 = lvl.diff(5) * 100.0

    out = pd.DataFrame({
        f"{name}_lvl": lvl,
        f"{name}_chg1": d1,
        f"{name}_chg5": d5,
        f"{name}_vol20": d1.rolling(20, min_periods=10).std(),
    })
    return out


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--input", default=str(DEFAULT_IN),
                    help="Excel fitur eksternal yang sudah ada (kolomnya dipertahankan)")
    ap.add_argument("-o", "--output", required=True, help="Excel keluaran")
    ap.add_argument("--yahoo", action="store_true",
                    help="Ambil USD/IDR dan IHSG dari Yahoo Finance")
    ap.add_argument("--usdidr-csv", help="CSV USD/IDR (tanggal, nilai)")
    ap.add_argument("--ihsg-csv", help="CSV IHSG (tanggal, nilai)")
    ap.add_argument("--sbn10y-csv", help="CSV yield SBN 10 tahun dalam persen")
    ap.add_argument("--start", default="2019-01-01", help="Tanggal awal untuk --yahoo")
    A = ap.parse_args(argv)

    # ---- kerangka tanggal: dari berkas lama kalau ada ----
    base = None
    if Path(A.input).exists():
        base = pd.read_excel(A.input)
        base[DATE_COL] = pd.to_datetime(base[DATE_COL])
        base = base.sort_values(DATE_COL).reset_index(drop=True)
        print(f"berkas lama: {len(base)} baris, "
              f"{base[DATE_COL].min().date()} -> {base[DATE_COL].max().date()}, "
              f"{base.shape[1] - 1} kolom fitur")
    else:
        print(f"berkas lama tidak ditemukan di {A.input}; membangun dari nol")

    print("\nsumber:")
    raw: dict[str, pd.Series] = {}

    # USD/IDR: pakai kolom lama kalau ada, supaya tidak perlu jaringan.
    if A.usdidr_csv:
        raw["usdidr"] = read_series_csv(A.usdidr_csv, "usdidr")
    elif base is not None and "closing_usdidr_mid" in base.columns:
        s = pd.Series(base["closing_usdidr_mid"].to_numpy(),
                      index=pd.DatetimeIndex(base[DATE_COL]), name="usdidr")
        raw["usdidr"] = s
        nz = int((pd.to_numeric(s, errors="coerce") <= 0).sum())
        print(f"  usdidr   dari kolom closing_usdidr_mid berkas lama: {len(s)} baris "
              f"({nz} nilai nol diperlakukan sebagai hari non-perdagangan)")
    elif A.yahoo:
        raw["usdidr"] = fetch_yahoo(YAHOO["usdidr"], "usdidr", A.start)

    if A.ihsg_csv:
        raw["ihsg"] = read_series_csv(A.ihsg_csv, "ihsg")
    elif A.yahoo:
        raw["ihsg"] = fetch_yahoo(YAHOO["ihsg"], "ihsg", A.start)

    if A.sbn10y_csv:
        raw["sbn10y"] = read_series_csv(A.sbn10y_csv, "sbn10y")

    if not raw:
        print("\nTidak ada satu pun sumber yang tersedia. Berikan --usdidr-csv / "
              "--ihsg-csv / --sbn10y-csv, atau --yahoo bila jaringan keluar terbuka.",
              file=sys.stderr)
        return 2

    for want in ("usdidr", "ihsg", "sbn10y"):
        if want not in raw:
            print(f"  ! {want} tidak tersedia - kolomnya tidak dibuat")

    # ---- kerangka tanggal gabungan (hari kerja) ----
    lo = min(s.index.min() for s in raw.values())
    hi = max(s.index.max() for s in raw.values())
    if base is not None:
        lo = min(lo, base[DATE_COL].min())
        hi = max(hi, base[DATE_COL].max())
    idx = pd.bdate_range(lo, hi)

    print(f"\nkerangka: {idx.min().date()} -> {idx.max().date()} "
          f"({len(idx)} hari kerja)")

    frames = []
    for name, s in raw.items():
        kind = "yield" if name == "sbn10y" else "price"
        frames.append(build_features(s.reindex(s.index.union(idx)).sort_index(),
                                     name, kind).reindex(idx))
    feat = pd.concat(frames, axis=1)
    feat.index.name = DATE_COL

    # ---- gabung dengan kolom lama ----
    out = feat.reset_index()
    if base is not None:
        keep = [c for c in base.columns if c == DATE_COL or c not in feat.columns]
        out = base[keep].merge(out, on=DATE_COL, how="outer").sort_values(DATE_COL)
    out = out.reset_index(drop=True)

    Path(A.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_excel(A.output, index=False)

    print(f"\nditulis: {A.output}")
    print(f"  {len(out)} baris, {out.shape[1] - 1} kolom fitur")
    print("\ncakupan kolom makro baru:")
    for c in feat.columns:
        v = pd.to_numeric(out[c], errors="coerce")
        print(f"  {c:18s} terisi {v.notna().sum():5d}/{len(out)}  "
              f"min {v.min():>10.3f}  maks {v.max():>10.3f}")
    print("\nUnggah berkas ini lewat laman 'Fitur Eksternal'. Ingat bahwa fitur "
          "eksternal baru dipakai model kalau ENABLE_EXTERNAL_FEATURES di "
          "utils/external_loader.py disetel True.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
