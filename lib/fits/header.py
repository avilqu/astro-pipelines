"""
FITS header parsing utilities.
"""

import json
from astropy.io import fits
from typing import Dict, Any


def get_fits_header_as_json(fits_file_path: str) -> Dict[str, Any]:
    """
    Read a FITS file and return its header as a JSON-serializable dictionary.
    
    Args:
        fits_file_path: Path to the FITS file
        
    Returns:
        Dictionary containing all header cards and their values
        
    Raises:
        FileNotFoundError: If the FITS file doesn't exist
        OSError: If the file can't be opened as a FITS file
    """
    try:
        with fits.open(fits_file_path) as hdul:
            # Get the primary header (first HDU)
            header = hdul[0].header
            
            # Convert header to dictionary, handling non-serializable objects
            header_dict = {}
            for key, value in header.items():
                # Convert special FITS objects to strings
                if hasattr(value, '__str__'):
                    header_dict[key] = str(value)
                else:
                    header_dict[key] = value
            
            return header_dict
            
    except FileNotFoundError:
        raise FileNotFoundError(f"FITS file not found: {fits_file_path}")
    except OSError as e:
        raise OSError(f"Error opening FITS file {fits_file_path}: {e}")


def get_fits_header_json_string(fits_file_path: str) -> str:
    """
    Read a FITS file and return its header as a JSON string.
    
    Args:
        fits_file_path: Path to the FITS file
        
    Returns:
        JSON string containing all header cards and their values
        
    Raises:
        FileNotFoundError: If the FITS file doesn't exist
        OSError: If the file can't be opened as a FITS file
        ValueError: If header can't be serialized to JSON
    """
    header_dict = get_fits_header_as_json(fits_file_path)
    
    try:
        return json.dumps(header_dict)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Error serializing header to JSON: {e}") 