''' Constants config file for astro-pipelines.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


# Folder setup
# ------------
# pipelines stores all calibration masters in /MAIN_PATH/CCD_LABEL/.

MAIN_PATH = '/home/tan/Astro/calibration/'  # Main calibration folder 
ROOT_PATH = '/home/tan/Astro/'              # Main folder
TELESCOPE = 'RC8 200/1620 f/8.1'            # Telescope name (unused)
CCD_NAME = 'QHYCCD QHY163M'                 # Camera name (unused)
CCD_LABEL = 'QHY163'                        # Camera label
# CCD_NAME = 'SBIG ST-402 ME'               # Camera name (unused)
# CCD_LABEL = 'ST402'                       # Camera label
CALIBRATION_PATH = f'{ROOT_PATH}calibration/{CCD_LABEL}'


# Calibration parameters
# ----------------------

TEMP_TOLERANCE = 1      # Max delta temp accepted for finding calibration master
SIGMA_LOW = 5           # Value of sigma low integration parameter
SIGMA_HIGH = 5          # Value of sigma high integration parameter
