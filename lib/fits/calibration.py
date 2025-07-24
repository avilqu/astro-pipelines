"""
Calibration module for astro-pipelines.
Handles finding and applying calibration masters to FITS files.
"""

import os
import tempfile
import shutil
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from sqlalchemy import and_, or_, func
from colorama import Fore, Style

from astropy import units as u
import ccdproc as ccdp
from astropy.nddata import CCDData
from astropy.io import fits

from lib.db.manager import get_db_manager
from lib.db.models import CalibrationMaster, FitsFile
import config


class CalibrationManager:
    """Manages calibration operations for FITS files."""
    
    def __init__(self):
        """Initialize the calibration manager."""
        self.db_manager = get_db_manager()
    
    def find_master_bias(self, fits_file: FitsFile) -> Optional[CalibrationMaster]:
        """
        Find the most suitable master bias for a given FITS file.
        
        For bias frames, we match on binning, filter, gain, offset, and CCD temperature,
        and choose the nearest PREVIOUS available bias (not future dates).
        
        Args:
            fits_file: The FitsFile object to find calibration for
            
        Returns:
            CalibrationMaster object if found, None otherwise
        """
        session = self.db_manager.get_session()
        try:
            # Get tolerance values from config
            ccd_temp_tolerance = 2  # From config.TESTED_FITS_CARDS
            
            # Get all bias masters that match the constraints with proper tolerances
            query = session.query(CalibrationMaster).filter(
                and_(
                    CalibrationMaster.frame == 'Bias',
                    CalibrationMaster.binning == fits_file.binning,
                    CalibrationMaster.filter_name == fits_file.filter_name,
                    CalibrationMaster.gain == fits_file.gain,
                    CalibrationMaster.offset == fits_file.offset,
                    CalibrationMaster.ccd_temp.between(
                        fits_file.ccd_temp - ccd_temp_tolerance,
                        fits_file.ccd_temp + ccd_temp_tolerance
                    ),
                    CalibrationMaster.date <= fits_file.date_obs.strftime('%Y-%m-%d')
                )
            ).order_by(CalibrationMaster.date.desc())
            
            masters = query.all()
            
            if not masters:
                print(f"{Style.BRIGHT + Fore.RED}Could not find a suitable master bias.{Style.RESET_ALL}")
                print(f"  Required: binning={fits_file.binning}, filter={fits_file.filter_name}")
                print(f"  Gain={fits_file.gain}, offset={fits_file.offset}, ccd_temp={fits_file.ccd_temp}±{ccd_temp_tolerance}°C")
                print(f"  Date constraint: <= {fits_file.date_obs.strftime('%Y-%m-%d')}")
                return None
            
            # Return the most recent one (closest previous date)
            selected_master = masters[0]
            print(f"Selected master bias: {selected_master.path}")
            print(f"  Date: {selected_master.date}, Binning: {selected_master.binning}, Filter: {selected_master.filter_name}")
            print(f"  Gain: {selected_master.gain}, Offset: {selected_master.offset}, Temp: {selected_master.ccd_temp}°C")
            
            return selected_master
            
        finally:
            session.close()
    
    def find_master_dark(self, fits_file: FitsFile) -> Optional[CalibrationMaster]:
        """
        Find the most suitable master dark for a given FITS file.
        
        For dark frames, we match on binning, gain, offset, and CCD temperature,
        and require exposure time >= the target file. If multiple options exist,
        choose the one with closest date_obs.
        
        Args:
            fits_file: The FitsFile object to find calibration for
            
        Returns:
            CalibrationMaster object if found, None otherwise
        """
        session = self.db_manager.get_session()
        try:
            # Get tolerance values from config
            ccd_temp_tolerance = 2  # From config.TESTED_FITS_CARDS
            
            # Get all dark masters that match the constraints with proper tolerances
            query = session.query(CalibrationMaster).filter(
                and_(
                    CalibrationMaster.frame == 'Dark',
                    CalibrationMaster.binning == fits_file.binning,
                    CalibrationMaster.gain == fits_file.gain,
                    CalibrationMaster.offset == fits_file.offset,
                    CalibrationMaster.ccd_temp.between(
                        fits_file.ccd_temp - ccd_temp_tolerance,
                        fits_file.ccd_temp + ccd_temp_tolerance
                    ),
                    CalibrationMaster.exptime >= fits_file.exptime
                )
            )
            
            masters = query.all()
            
            if not masters:
                print(f"{Style.BRIGHT + Fore.RED}Could not find a suitable master dark.{Style.RESET_ALL}")
                print(f"  Required: binning={fits_file.binning}, gain={fits_file.gain}, "
                      f"offset={fits_file.offset}, ccd_temp={fits_file.ccd_temp}±{ccd_temp_tolerance}°C")
                print(f"  Exposure constraint: >= {fits_file.exptime}s")
                return None
            
            # Find the one with closest date_obs
            closest_master = None
            min_date_diff = float('inf')
            
            for master in masters:
                # Parse the date from the master
                master_date = datetime.strptime(master.date, '%Y-%m-%d')
                date_diff = abs((master_date - fits_file.date_obs).days)
                
                if date_diff < min_date_diff:
                    min_date_diff = date_diff
                    closest_master = master
            
            if closest_master:
                print(f"Selected master dark: {closest_master.path}")
                print(f"  Date: {closest_master.date}, Exposure: {closest_master.exptime}s")
                print(f"  Binning: {closest_master.binning}, Gain: {closest_master.gain}, "
                      f"Offset: {closest_master.offset}, Temp: {closest_master.ccd_temp}°C")
            
            return closest_master
            
        finally:
            session.close()
    
    def find_master_flat(self, fits_file: FitsFile) -> Optional[CalibrationMaster]:
        """
        Find the most suitable master flat for a given FITS file.
        
        For flat frames, we match on binning and filter, and choose the nearest
        PREVIOUS available flat (not future dates).
        
        Args:
            fits_file: The FitsFile object to find calibration for
            
        Returns:
            CalibrationMaster object if found, None otherwise
        """
        session = self.db_manager.get_session()
        try:
            # Get all flat masters that match binning and filter
            query = session.query(CalibrationMaster).filter(
                and_(
                    CalibrationMaster.frame == 'Flat',
                    CalibrationMaster.binning == fits_file.binning,
                    CalibrationMaster.filter_name == fits_file.filter_name,
                    CalibrationMaster.date <= fits_file.date_obs.strftime('%Y-%m-%d')
                )
            ).order_by(CalibrationMaster.date.desc())
            
            masters = query.all()
            
            if not masters:
                print(f"{Style.BRIGHT + Fore.RED}Could not find a suitable master flat.{Style.RESET_ALL}")
                print(f"  Required: binning={fits_file.binning}, filter={fits_file.filter_name}")
                print(f"  Date constraint: <= {fits_file.date_obs.strftime('%Y-%m-%d')}")
                return None
            
            # Return the most recent one (closest previous date)
            selected_master = masters[0]
            print(f"Selected master flat: {selected_master.path}")
            print(f"  Date: {selected_master.date}, Binning: {selected_master.binning}, Filter: {selected_master.filter_name}")
            
            return selected_master
            
        finally:
            session.close()
    
    def find_calibration_masters(self, fits_file: FitsFile) -> Dict[str, Optional[CalibrationMaster]]:
        """
        Find all suitable calibration masters for a given FITS file.
        
        Args:
            fits_file: The FitsFile object to find calibration for
            
        Returns:
            Dictionary with keys 'bias', 'dark', 'flat' containing the selected masters
        """
        print(f"\n{Style.BRIGHT}Finding calibration masters for: {fits_file.path}{Style.RESET_ALL}")
        print(f"  Date: {fits_file.date_obs.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Filter: {fits_file.filter_name}, Binning: {fits_file.binning}")
        print(f"  Gain: {fits_file.gain}, Offset: {fits_file.offset}, Temp: {fits_file.ccd_temp}°C")
        print(f"  Exposure: {fits_file.exptime}s")
        
        masters = {
            'bias': self.find_master_bias(fits_file),
            'dark': self.find_master_dark(fits_file),
            'flat': self.find_master_flat(fits_file)
        }
        
        # Summary
        print(f"\n{Style.BRIGHT}Calibration masters summary:{Style.RESET_ALL}")
        for calib_type, master in masters.items():
            if master:
                print(f"  {calib_type.upper()}: ✓ Found ({master.path})")
            else:
                print(f"  {calib_type.upper()}: ✗ Not found")
        
        return masters
    
    def get_fits_file_by_path(self, file_path: str) -> Optional[FitsFile]:
        """
        Get a FitsFile object from the database by its path.
        
        Args:
            file_path: Path to the FITS file
            
        Returns:
            FitsFile object if found, None otherwise
        """
        return self.db_manager.get_fits_file_by_path(file_path)
    
    def calibrate_file(self, file_path: str) -> Dict[str, Any]:
        """
        Find calibration masters for a given file path.
        
        Args:
            file_path: Path to the FITS file to calibrate
            
        Returns:
            Dictionary containing the calibration masters and status
        """
        # Get the FITS file from database
        fits_file = self.get_fits_file_by_path(file_path)
        if not fits_file:
            print(f"{Style.BRIGHT + Fore.RED}File not found in database: {file_path}{Style.RESET_ALL}")
            return {'error': 'File not found in database'}
        
        # Find calibration masters
        masters = self.find_calibration_masters(fits_file)
        
        return {
            'fits_file': fits_file,
            'masters': masters,
            'success': all(masters.values())  # True if all masters were found
        }
    
    def _extract_ccd(self, image_path: str) -> CCDData:
        """
        Extract CCDData from a FITS file path.
        
        Args:
            image_path: Path to the FITS file
            
        Returns:
            CCDData object
        """
        return CCDData.read(image_path, unit='adu')
    
    def _create_temp_dir(self) -> Path:
        """
        Create the temporary directory for calibrated files.
        
        Returns:
            Path to the temporary directory
        """
        temp_dir = Path("/tmp/astropipes-calibrated")
        temp_dir.mkdir(exist_ok=True)
        return temp_dir
    
    def subtract_bias(self, image_path: str, bias_master: CalibrationMaster) -> CCDData:
        """
        Subtract master bias from FITS image.
        
        Args:
            image_path: Path to the FITS file to calibrate
            bias_master: CalibrationMaster object for bias
            
        Returns:
            CCDData object with bias subtracted
        """
        print(f"{Style.BRIGHT + Fore.GREEN}Bias subtraction...{Style.RESET_ALL}")
        
        # Load the images
        image = self._extract_ccd(image_path)
        bias = self._extract_ccd(bias_master.path)
        
        # Perform bias subtraction
        calibrated_image = ccdp.subtract_bias(image, bias)
        calibrated_image.data = calibrated_image.data.astype('float32')
        
        return calibrated_image
    
    def subtract_dark(self, image: CCDData, dark_master: CalibrationMaster, original_exptime: float) -> CCDData:
        """
        Subtract master dark from FITS image with proper scaling.
        
        Args:
            image: CCDData object (already bias-subtracted)
            dark_master: CalibrationMaster object for dark
            original_exptime: Original exposure time of the target image
            
        Returns:
            CCDData object with dark subtracted
        """
        print(f"{Style.BRIGHT + Fore.GREEN}Dark subtraction...{Style.RESET_ALL}")
        
        # Load the dark master
        dark = self._extract_ccd(dark_master.path)
        
        # Perform dark subtraction with scaling
        calibrated_image = ccdp.subtract_dark(
            image, dark, 
            exposure_time='EXPTIME', 
            exposure_unit=u.second, 
            scale=True
        )
        calibrated_image.data = calibrated_image.data.astype('float32')
        
        return calibrated_image
    
    def correct_flat(self, image: CCDData, flat_master: CalibrationMaster) -> CCDData:
        """
        Apply flat correction to FITS image.
        
        Args:
            image: CCDData object (already bias and dark subtracted)
            flat_master: CalibrationMaster object for flat
            
        Returns:
            CCDData object with flat correction applied
        """
        print(f"{Style.BRIGHT + Fore.GREEN}Flat correction...{Style.RESET_ALL}")
        
        # Load the flat master
        flat = self._extract_ccd(flat_master.path)
        
        # Apply flat correction
        calibrated_image = ccdp.flat_correct(image, flat)
        calibrated_image.data = calibrated_image.data.astype('float32')
        
        return calibrated_image
    
    def restore_wcs_header(self, original_path: str, calibrated_path: str):
        """
        Restore WCS header from original file to calibrated file.
        
        Args:
            original_path: Path to original FITS file
            calibrated_path: Path to calibrated FITS file
        """
        with fits.open(original_path) as orig, fits.open(calibrated_path, mode='update') as cal:
            wcs_keys = ['CTYPE1', 'CTYPE2', 'CRPIX1', 'CRPIX2', 'CRVAL1', 'CRVAL2', 'CD1_1', 'CD1_2', 'CD2_1', 'CD2_2']
            copied_keys = []
            for key in wcs_keys:
                if key in orig[0].header:
                    cal[0].header[key] = orig[0].header[key]
                    copied_keys.append(key)
            removed_keys = []
            for key in ['CDELT1', 'CDELT2', 'CROTA1', 'CROTA2']:
                if key in cal[0].header:
                    del cal[0].header[key]
                    removed_keys.append(key)
            cal.flush()
    
    def calibrate_file(self, file_path: str, steps: Dict[str, bool] = None) -> Dict[str, Any]:
        """
        Calibrate a FITS file using the found calibration masters.
        
        Args:
            file_path: Path to the FITS file to calibrate
            steps: Dictionary specifying which calibration steps to apply
                   {'bias': True, 'dark': True, 'flat': True}
            
        Returns:
            Dictionary containing calibration results
        """
        if steps is None:
            steps = {
                'bias': True,
                'dark': True,
                'flat': True,
            }
        
        # Get the FITS file from database
        fits_file = self.get_fits_file_by_path(file_path)
        if not fits_file:
            print(f"{Style.BRIGHT + Fore.RED}File not found in database: {file_path}{Style.RESET_ALL}")
            return {'error': 'File not found in database'}
        
        # Find calibration masters
        masters = self.find_calibration_masters(fits_file)
        
        # Check if we have all required masters
        missing_masters = []
        for step, required in steps.items():
            if required and not masters.get(step):
                missing_masters.append(step)
        
        if missing_masters:
            print(f"{Style.BRIGHT + Fore.RED}Cannot calibrate: missing masters for {', '.join(missing_masters)}{Style.RESET_ALL}")
            return {'error': f'Missing masters: {missing_masters}'}
        
        print(f"\n{Style.BRIGHT}Calibrating {os.path.basename(file_path)}...{Style.RESET_ALL}")
        
        # Create temporary directory
        temp_dir = self._create_temp_dir()
        
        try:
            # Start with the original image
            calibrated_image = self._extract_ccd(file_path)
            new_filename = os.path.basename(file_path)
            
            # Apply calibration steps
            if steps['bias'] and masters['bias']:
                calibrated_image = self.subtract_bias(file_path, masters['bias'])
                new_filename = f"b_{new_filename}"
            
            if steps['dark'] and masters['dark']:
                calibrated_image = self.subtract_dark(calibrated_image, masters['dark'], fits_file.exptime)
                new_filename = f"d_{new_filename}"
            
            if steps['flat'] and masters['flat']:
                calibrated_image = self.correct_flat(calibrated_image, masters['flat'])
                new_filename = f"f_{new_filename}"
            
            # Write the calibrated image
            output_path = temp_dir / new_filename
            print(f"{Style.BRIGHT + Fore.GREEN}Writing calibrated image: {output_path}{Style.RESET_ALL}")
            calibrated_image.write(output_path, overwrite=True)
            
            # Restore WCS header if it exists
            try:
                self.restore_wcs_header(file_path, str(output_path))
                print(f"{Style.BRIGHT + Fore.GREEN}WCS header restored{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Style.BRIGHT + Fore.YELLOW}Warning: Could not restore WCS header: {e}{Style.RESET_ALL}")
            
            return {
                'success': True,
                'original_path': file_path,
                'calibrated_path': str(output_path),
                'filename': new_filename,
                'masters_used': masters
            }
            
        except Exception as e:
            print(f"{Style.BRIGHT + Fore.RED}Error during calibration: {e}{Style.RESET_ALL}")
            return {'error': str(e)}
    
    def calibrate_file_simple(self, file_path: str) -> Dict[str, Any]:
        """
        Simple calibration interface that finds masters and calibrates in one step.
        
        Args:
            file_path: Path to the FITS file to calibrate
            
        Returns:
            Dictionary containing calibration results
        """
        return self.calibrate_file(file_path) 