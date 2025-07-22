"""
FITS file utilities for astro-pipelines.
"""

from .header import get_fits_header_as_json, get_fits_header_json_string

__all__ = ['get_fits_header_as_json', 'get_fits_header_json_string'] 