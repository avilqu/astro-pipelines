"""
FITS file scanner for importing files into the database.
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from .main import get_db_manager
from ..fits import get_fits_header_as_json


class FitsFileScanner:
    """Scanner for importing FITS files into the database."""
    
    def __init__(self, data_path: Optional[str] = None):
        """
        Initialize the scanner.
        
        Args:
            data_path: Path to scan for FITS files. If None, uses config.DATA_PATH.
        """
        if data_path is None:
            import config
            data_path = config.DATA_PATH
        
        self.data_path = Path(data_path)
        self.db_manager = get_db_manager()
        
        if not self.data_path.exists():
            raise FileNotFoundError(f"Data path does not exist: {self.data_path}")
    
    def scan_directory(self, verbose: bool = True) -> Dict[str, Any]:
        """
        Scan the data directory and import FITS files into the database.
        
        Args:
            verbose: Whether to print progress information
            
        Returns:
            Dictionary with scan results
        """
        if verbose:
            print(f"Scanning directory: {self.data_path}")
            print(f"Expected structure: {self.data_path}/Target/Filter/file.fits")
            print("-" * 60)
        
        results = {
            'total_files_found': 0,
            'files_imported': 0,
            'files_skipped': 0,
            'errors': [],
            'targets_found': set(),
            'filters_found': set()
        }
        
        # Walk through the directory structure
        for target_dir in self.data_path.iterdir():
            if not target_dir.is_dir():
                continue
                
            target_name = target_dir.name
            results['targets_found'].add(target_name)
            
            if verbose:
                print(f"Processing target: {target_name}")
            
            # Look for filter subdirectories
            for filter_dir in target_dir.iterdir():
                if not filter_dir.is_dir():
                    continue
                    
                filter_name = filter_dir.name
                results['filters_found'].add(filter_name)
                
                if verbose:
                    print(f"  Processing filter: {filter_name}")
                
                # Look for FITS files
                for fits_file in filter_dir.glob("*.fits"):
                    results['total_files_found'] += 1
                    
                    if verbose:
                        print(f"    Processing: {fits_file.name}")
                    
                    try:
                        success = self._process_fits_file(fits_file, target_name, filter_name)
                        if success:
                            results['files_imported'] += 1
                        else:
                            results['files_skipped'] += 1
                    except Exception as e:
                        error_msg = f"Error processing {fits_file}: {e}"
                        results['errors'].append(error_msg)
                        if verbose:
                            print(f"    ❌ {error_msg}")
        
        # Convert sets to lists for JSON serialization
        results['targets_found'] = list(results['targets_found'])
        results['filters_found'] = list(results['filters_found'])
        
        if verbose:
            self._print_summary(results)
        
        return results
    
    def _process_fits_file(self, fits_file: Path, target_name: str, filter_name: str) -> bool:
        """
        Process a single FITS file and add it to the database.
        
        Args:
            fits_file: Path to the FITS file
            target_name: Name of the target (from directory structure)
            filter_name: Name of the filter (from directory structure)
            
        Returns:
            True if file was imported, False if it was skipped (already exists)
        """
        # Check if file already exists in database
        existing_file = self.db_manager.get_fits_file_by_path(str(fits_file))
        if existing_file:
            return False  # File already exists
        
        # Parse FITS header
        header_dict = get_fits_header_as_json(str(fits_file))
        
        # Extract key information from header
        fits_data = {
            'path': str(fits_file),
            'target': target_name,  # Use directory name as target
            'filter_name': filter_name,  # Use directory name as filter
            'date_obs': self._parse_date_obs(header_dict.get('DATE-OBS')),
            'exptime': header_dict.get('EXPTIME'),
            'gain': header_dict.get('GAIN'),
            'offset': header_dict.get('OFFSET'),
            'ccd_temp': header_dict.get('CCD-TEMP'),
            'binning': self._format_binning(header_dict.get('XBINNING'), header_dict.get('YBINNING')),
            'size_x': header_dict.get('NAXIS1'),
            'size_y': header_dict.get('NAXIS2'),
            'image_scale': header_dict.get('SCALE'),  # arcsec/pixel (was PIXSCALE)
            'ra_center': header_dict.get('CRVAL1'),  # Right Ascension of center
            'dec_center': header_dict.get('CRVAL2'),  # Declination of center
            'wcs_type': header_dict.get('CTYPE1'),  # WCS solution type
            'header_json': json.dumps(header_dict),  # Full header as JSON
            'simbad_objects': '[]'  # Empty array for now
        }
        
        # Add to database
        self.db_manager.add_fits_file(fits_data)
        return True
    
    def _parse_date_obs(self, date_obs: Any) -> Optional[datetime]:
        """
        Parse the DATE-OBS header value into a datetime object.
        
        Args:
            date_obs: The DATE-OBS value from the header
            
        Returns:
            Parsed datetime object or None if parsing fails
        """
        if not date_obs:
            return None
        
        try:
            # Try to parse the date string
            if isinstance(date_obs, str):
                # Handle different date formats
                for fmt in ['%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                    try:
                        return datetime.strptime(date_obs, fmt)
                    except ValueError:
                        continue
            return None
        except Exception:
            return None
    
    def _format_binning(self, xbin: Any, ybin: Any) -> str:
        """
        Format binning information as a string.
        
        Args:
            xbin: X binning value
            ybin: Y binning value
            
        Returns:
            Formatted binning string (e.g., "1x1", "2x2")
        """
        x = xbin if xbin is not None else 1
        y = ybin if ybin is not None else 1
        return f"{x}x{y}"
    
    def _print_summary(self, results: Dict[str, Any]):
        """Print a summary of the scan results."""
        print("\n" + "=" * 60)
        print("SCAN SUMMARY")
        print("=" * 60)
        print(f"Total files found: {results['total_files_found']}")
        print(f"Files imported: {results['files_imported']}")
        print(f"Files skipped (already in DB): {results['files_skipped']}")
        print(f"Errors: {len(results['errors'])}")
        
        if results['targets_found']:
            print(f"\nTargets found: {', '.join(sorted(results['targets_found']))}")
        
        if results['filters_found']:
            print(f"Filters found: {', '.join(sorted(results['filters_found']))}")
        
        if results['errors']:
            print(f"\nErrors encountered:")
            for error in results['errors']:
                print(f"  - {error}")


def scan_fits_library(data_path: Optional[str] = None, verbose: bool = True) -> Dict[str, Any]:
    """
    Convenience function to scan the FITS library.
    
    Args:
        data_path: Path to scan for FITS files. If None, uses config.DATA_PATH.
        verbose: Whether to print progress information
        
    Returns:
        Dictionary with scan results
    """
    scanner = FitsFileScanner(data_path)
    return scanner.scan_directory(verbose) 