''' Constants config file for astro-pipelines.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

import tzlocal
from datetime import timezone

def to_display_time(dt_utc):
    """Convert a UTC datetime to local time if TIME_DISPLAY_MODE is 'Local', else return as UTC."""
    if dt_utc is None:
        return None
    if TIME_DISPLAY_MODE == 'Local':
        local_tz = tzlocal.get_localzone()
        return dt_utc.replace(tzinfo=timezone.utc).astimezone(local_tz)
    else:
        return dt_utc.replace(tzinfo=timezone.utc)

# astro-pipelines will write calibration masters
# (and expect them to stay) in CALIBRATION_PATH.
CALIBRATION_PATH = '/home/tan/Astro/calibration'
DATA_PATH = '/home/tan/Astro/obs'
OBS_PATH = '/home/tan/Astro/obs'

# Database configuration
DATABASE_PATH = '/home/tan/dev/astro-pipelines/astropipes.db'  # SQLite database file path (absolute path)

# Astrometry.net API key
ASTROMETRY_KEY = 'zrvbykzuksfbcilr'

# Solver methods default options. Search radius in degrees.
SOLVER_DOWNSAMPLE = 2
SOLVER_SEARCH_RADIUS = 15

# Solver timeout settings (in seconds)
SOLVER_OFFLINE_TIMEOUT = 30  # timeout for offline solve-field
SOLVER_ONLINE_TIMEOUT = 300   # timeout for online solving
SOLVER_ONLINE_POLL_INTERVAL = 5  # How often to check online solver status
SOLVER_MAX_RETRIES = 3  # Maximum number of retries for failed solves
SOLVER_VALIDATE_IMAGES = True  # Whether to validate images before attempting to solve

# Sigma values for pixel rejection are found below. These values are
# used to reject outstanding pixels during image integration. It is used
# for both integrating light frames and creating calibration masters.
SIGMA_LOW = 4
SIGMA_HIGH = 3

# Constraints for selecting calibratin masters. Note that
# astro-pipelines generates and uses calibrated master darks
# and scales them to match the exposure of the light frame
BIAS_CONSTRAINTS = ['GAIN', 'OFFSET', 'CCD-TEMP', 'XBINNING']
DARK_CONSTRAINTS = ['GAIN', 'OFFSET', 'CCD-TEMP', 'XBINNING']
FLAT_CONSTRAINTS = ['FILTER', 'XBINNING']

# Header cards used for the sequence consistency tests and header
# summary display. Script will issue an error if testing a card
# that isn't present. Comment them out from this list if you
# get one of these errors.
TESTED_FITS_CARDS = [
    {
        'name': 'GAIN',
        'tolerance': 0,
    },
    {
        'name': 'OFFSET',
        'tolerance': 0,
    },
    {
        'name': 'XBINNING',
        'tolerance': 0,
    },
    {
        'name': 'EXPTIME',
        'tolerance': 1,
    },
    {
        'name': 'FILTER',
        'tolerance': 0,
    },
    {
        'name': 'CCD-TEMP',
        'tolerance': 2,
    },
    {
        'name': 'NAXIS1',
        'tolerance': 0,
    },
    {
        'name': 'NAXIS2',
        'tolerance': 0,
    },
    # {
    #     'name': 'FRAME',
    #     'tolerance': 0,
    # },
]

# --- User Settings ---
TIME_DISPLAY_MODE = 'Local'
BLINK_PERIOD_MS = 1000
