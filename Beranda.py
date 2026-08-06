import streamlit as st
import warnings
from version import get_full_version_info, __version__

# Suppress deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*keyword arguments have been deprecated.*')

# Page config
st.set_page_config(
    page_title="Beranda - JBV Dashboard",
    page_icon="👋",
    layout="wide"
)

# Title
st.title("👋 Halo Tim APUVA")
st.markdown("Selamat datang di Dashboard Forecasting Jual Beli Valas (JBV).")

st.divider()

# Sidebar version info (fixed at bottom)
st.sidebar.markdown(
    f"""
    <div style="position: fixed; bottom: 10px; font-size: 12px; color: gray;">
        📦 Version {__version__}<br>
        © 2025 APUVA - Bank Indonesia
    </div>
    """,
    unsafe_allow_html=True
)

