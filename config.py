''' Constants config file for astro-pipelines.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

# astro-pipelines needs values at least for ROOT_PATH (astrophotography
# working directory). It will write masters (and expect them to stay)
# in CALIBRATION_PATH.
ROOT_PATH = '/home/tan/Astro'
CALIBRATION_PATH = f'{ROOT_PATH}/calibration/QHY163'

# The real-time pipeline will add/correct FITS header cards with
# the data below.
OBSERVER = 'Adrien Vilquin Barrajon'
TELESCOPE = 'RC8 200/1620 f/8'
CCD_NAME = 'QHYCCD QHY163M'

# Astrometry.net API key
ASTROMETRY_KEY = 'zrvbykzuksfbcilr'

# Maximum time a calibration master can be used after its creation (in days)
# FLAT_LIFESPAN = 1000
# DARK_LIFESPAN = 1000
# BIAS_LIFESPAN = 1000

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