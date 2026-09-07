"""
Utils Module for SDV Dashboard

Helper functions for data loading, date utilities, and more.
"""

from .date_utils import load_holidays, generate_business_dates, ML_START_DATE

__all__ = ['load_data_with_etl_check', 'load_holidays', 'generate_business_dates', 'ML_START_DATE']


def __getattr__(name):
    """
    Impor `load_data_with_etl_check` secara malas (PEP 562).

    Fungsi itu berada di data_loader.py yang mengimpor streamlit di tingkat
    modul. Kalau diimpor di sini secara langsung, maka SETIAP konsumen paket
    `utils` ikut menyeret streamlit - termasuk skrip batch, notebook Colab, dan
    proses evaluasi yang tidak punya (dan tidak butuh) streamlit sama sekali.
    Konsekuensinya bukan sekadar berat: `from utils import load_holidays` akan
    GAGAL total di lingkungan tanpa streamlit, padahal load_holidays sendiri
    hanya membaca JSON.

    Dengan __getattr__, `from utils import load_data_with_etl_check` tetap
    bekerja persis seperti sebelumnya untuk halaman Streamlit, tapi streamlit
    baru diimpor pada saat nama itu benar-benar diakses.
    """
    if name == 'load_data_with_etl_check':
        from .data_loader import load_data_with_etl_check
        return load_data_with_etl_check
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
