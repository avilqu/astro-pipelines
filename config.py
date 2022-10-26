''' Constants config file for astro-pipelines.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

# astro-pipelines needs values at least for ROOT_PATH (astrophotography
# working directory). It will write masters (and expect them to stay)
# in CALIBRATION_PATH.
ROOT_PATH = '/home/tan/Astro'
CALIBRATION_PATH = f'{ROOT_PATH}/calibration/QHY163'

# Astrometry.net API key
ASTROMETRY_KEY = 'zrvbykzuksfbcilr'

# Tolerance values used when checking for sequence consistency and
# looking for suitable calibration masters
TEMP_TOLERANCE = 1      # CCD temperature
EXP_TOLERANCE = 0       # CCD exposure

# Sigma values for pixel rejection are found below. These values are
# used to reject outstanding pixels during image integration. It is used
# for both integrating light frames and creating calibration masters.
SIGMA_LOW = 5
SIGMA_HIGH = 5

# Header cards used for the consistency test before integration
TESTED_FITS_CARDS = [
            {
                'name': 'GAIN',
                'tolerance': 0,
                'values': []
            },
            {
                'name': 'OFFSET',
                'tolerance': 0,
                'values': []
            },
            {
                'name': 'EXPTIME',
                'tolerance': 0,
                'values': []
            },
            {
                'name': 'FILTER',
                'tolerance': 0,
                'values': []
            },
            {
                'name': 'CCD-TEMP',
                'tolerance': TEMP_TOLERANCE,
                'values': []
            },
            {
                'name': 'NAXIS1',
                'tolerance': 0,
                'values': []
            },
            {
                'name': 'NAXIS2',
                'tolerance': 0,
                'values': []
            },
            {
                'name': 'IMAGETYP',
                'tolerance': 0,
                'values': []
            },
        ]