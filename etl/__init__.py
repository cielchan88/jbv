"""
ETL Module for SDV Dashboard

This module handles Extract-Transform-Load operations for Supply Demand Valas data.
"""

from .pipeline import run_pipeline

__all__ = ['run_pipeline']
