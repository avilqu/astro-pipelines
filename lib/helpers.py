''' Miscellaneous helpful functions for astro-pipelines.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

from astropy.nddata import CCDData
from astropy.io import fits
from astropy.wcs import WCS
import numpy as np

import config as cfg


def prompt():
    ''' Displays a Continue? (Y/n) prompt '''

    if input('-- Continue? (Y/n) ') == 'n':
        exit()


def header_summary(image):
    ''' Prints a summary of the values of the tested FITS header cards '''

    for card in cfg.TESTED_FITS_CARDS:
        card_name = card['name']
        value = image['header'][card_name]
        print(f'-- {card_name}: {value}')


def extract_ccd(image):
    ''' Returns CCDData of image in case it's an FITSSequence element '''

    if not isinstance(image, CCDData):
        return CCDData.read(image['path'], unit='adu')

    else:
        return image


def extract_coordinates_from_header(header):
    """
    Extract RA and Dec coordinates from FITS header.
    
    Parameters:
    -----------
    header : astropy.io.fits.Header
        FITS header to extract coordinates from
        
    Returns:
    --------
    tuple : (ra, dec, has_wcs, source)
        ra, dec in degrees, has_wcs boolean, and source description
    """
    ra_center = None
    dec_center = None
    has_wcs = False
    source = "none"
    
    # Check for WCS coordinates first (most accurate)
    if "CRVAL1" in header and "CRVAL2" in header:
        ra_center = header["CRVAL1"]
        dec_center = header["CRVAL2"]
        has_wcs = True
        source = "WCS (CRVAL1/CRVAL2)"
    # Fallback to simple RA/DEC keywords
    elif "ra" in header and "dec" in header:
        ra_center = header["ra"]
        dec_center = header["dec"]
        has_wcs = True
        source = "RA/DEC keywords"
    
    return ra_center, dec_center, has_wcs, source


def calculate_field_radius(wcs, ra_center, dec_center, default_radius=None):
    """
    Calculate field radius from WCS information.
    
    Parameters:
    -----------
    wcs : astropy.wcs.WCS
        World Coordinate System object
    ra_center : float
        RA center in degrees
    dec_center : float
        Dec center in degrees
    default_radius : float, optional
        Default radius to use if calculation fails
        
    Returns:
    --------
    float : Field radius in degrees
    """
    if default_radius is None:
        default_radius = cfg.SOLVER_SEARCH_RADIUS
    
    try:
        corners = wcs.calc_footprint()
        if corners is not None:
            max_radius = 0
            for corner_ra, corner_dec in corners:
                dra = (corner_ra - ra_center) * np.cos(np.radians(dec_center))
                ddec = corner_dec - dec_center
                radius = np.sqrt(dra**2 + ddec**2)
                max_radius = max(max_radius, radius)
            return max_radius + 0.1  # Add small buffer
        else:
            return default_radius
    except Exception as e:
        print(f"Error calculating field radius: {e}")
        return default_radius


def validate_wcs_solution(header):
    """
    Validate that a FITS header contains valid WCS information.
    
    Parameters:
    -----------
    header : astropy.io.fits.Header
        FITS header to validate
        
    Returns:
    --------
    tuple : (is_valid, error_message)
        Boolean indicating if WCS is valid and error message if not
    """
    # Check for basic WCS keywords
    wcs_keywords = ['CTYPE1', 'CTYPE2', 'CRVAL1', 'CRVAL2', 'CRPIX1', 'CRPIX2']
    has_wcs_keywords = all(key in header for key in wcs_keywords)
    
    if not has_wcs_keywords:
        return False, "No WCS keywords found in file"
    
    # Try to create a WCS object to verify it's valid
    try:
        test_wcs = WCS(header)
        if test_wcs.is_celestial:
            return True, "WCS is valid and celestial"
        else:
            return False, "WCS is not celestial"
    except Exception as e:
        return False, f"Invalid WCS - {e}"


def create_solver_options(files, ra=None, dec=None, radius=None, downsample=None, blind=False):
    """
    Create a solver options object with standard configuration.
    
    Parameters:
    -----------
    files : list
        List of file paths to solve
    ra : float, optional
        RA center in degrees
    dec : float, optional
        Dec center in degrees
    radius : float, optional
        Search radius in degrees
    downsample : int, optional
        Downsampling factor
    blind : bool, optional
        Whether to use blind solving
        
    Returns:
    --------
    object : Solver options object
    """
    class SolverOptions:
        def __init__(self):
            self.files = files
            self.downsample = downsample if downsample is not None else cfg.SOLVER_DOWNSAMPLE
            self.ra = ra
            self.dec = dec
            self.radius = radius if radius is not None else cfg.SOLVER_SEARCH_RADIUS
            self.blind = blind
    
    return SolverOptions()
