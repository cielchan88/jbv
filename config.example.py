"""
Configuration Template for SDV Dashboard
=========================================

Copy this file to 'config.py' and fill in your credentials.

Steps:
1. cp config.example.py config.py
2. Edit config.py with your actual credentials
3. DO NOT commit config.py to version control

Author: Data Processing Team
Date: 2024-11-24
"""

# API Configuration for CData Virtuality REST API
API_CONFIG = {
    'base_url': 'https://dc1datavirt02.corp.bi.go.id:443/rest/api/source/views',
    'username': 'your_username_here',  # CHANGE THIS
    'password': 'your_password_here',  # CHANGE THIS
    'timeout': 60,  # seconds
    'verify_ssl': False  # Set to False for internal network
}

# Endpoints (DO NOT CHANGE)
API_ENDPOINTS = {
    'korporasi': 'TTS_SDV_KORPORASI',
    'ptmn': 'TTS_SDV_PERTAMINA',
    'asing': 'TTS_PEL_LN_VS_LWN_DN_BANK',
    'individu': 'TTS_PEL_INDIV_DN_VS_LWN_BANK_DN'
}

# Sheet mapping (DO NOT CHANGE)
SHEET_MAPPING = {
    'korporasi': 'Korporasi',
    'ptmn': 'PTMN',
    'asing': 'Asing',
    'individu': 'Individu'
}
