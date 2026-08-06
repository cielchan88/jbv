"""
Version information for JBV Dashboard

Update this file when releasing a new version.
Follow Semantic Versioning: MAJOR.MINOR.PATCH
- MAJOR: Incompatible API changes
- MINOR: New features (backwards-compatible)
- PATCH: Bug fixes (backwards-compatible)
"""

__version__ = "1.2.0"
__release_date__ = "2025-11-24"
__author__ = "APUVA Team - Bank Indonesia"

VERSION_INFO = {
    "version": __version__,
    "release_date": __release_date__,
    "author": __author__,
    "description": "Jual Beli Valas Forecasting Dashboard",
    "changelog": {
        "1.2.0": {
            "date": "2025-11-24",
            "type": "minor",
            "highlights": [
                "Unified confidence interval calculation (residual-based)",
                "API credentials moved to config.py for security",
                "Enhanced metadata export with feature details",
                "Unified plot styling across pages",
                "Removed Scraper tab (cleaned 1,759 lines)"
            ]
        },
        "1.1.2": {
            "date": "2025-11-21",
            "type": "patch",
            "highlights": [
                "Fixed NameError in Prediksi page",
                "APUVA uses full historical data (2006-2025)",
                "ML models consistently use 2019+ data"
            ]
        },
        "1.1.1": {
            "date": "2025-11-21",
            "type": "patch",
            "highlights": [
                "Sheet name compatibility fix for external features",
                "Auto-detect first sheet (no hardcoded names)"
            ]
        }
    }
}

def get_version_string():
    """Return formatted version string"""
    return f"v{__version__}"

def get_full_version_info():
    """Return full version information"""
    return f"JBV Dashboard v{__version__} ({__release_date__})"

def get_changelog(version: str = None):
    """
    Get changelog for a specific version or all versions

    Args:
        version: Version string (e.g., "1.2.0"). If None, returns all.

    Returns:
        Dictionary with changelog info
    """
    if version:
        return VERSION_INFO["changelog"].get(version, {})
    return VERSION_INFO["changelog"]

def get_latest_changes():
    """Return highlights of the latest version"""
    return VERSION_INFO["changelog"][__version__]["highlights"]
