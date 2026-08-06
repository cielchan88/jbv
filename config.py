"""
Configuration File for SDV Dashboard
=====================================

This file contains sensitive configuration including API credentials.
DO NOT commit this file to version control (add to .gitignore).

Author: Data Processing Team
Date: 2024-11-24
"""

# API Configuration for CData Virtuality REST API
API_CONFIG = {
    'base_url': 'https://dc1datavirt02.corp.bi.go.id:443/rest/api/source/views',
    'username': 'redianto_s',
    'password': 'password',  # TODO: Change this to actual password
    'timeout': 60,  # seconds
    'verify_ssl': False  # Set to False for internal network
}

# Endpoints
API_ENDPOINTS = {
    'korporasi': 'TTS_SDV_KORPORASI',
    'ptmn': 'TTS_SDV_PERTAMINA',
    'asing': 'TTS_PEL_LN_VS_LWN_DN_BANK',
    'individu': 'TTS_PEL_INDIV_DN_VS_LWN_BANK_DN'
}

# Sheet mapping (endpoint key -> Excel sheet name)
SHEET_MAPPING = {
    'korporasi': 'Korporasi',
    'ptmn': 'PTMN',
    'asing': 'Asing',
    'individu': 'Individu'
}
