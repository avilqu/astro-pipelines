#!/opt/anaconda/bin/python

''' Generate master dark from a set of files and stores it in the calibration_path variable.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


from pathlib import Path
from subprocess import run
from datetime import datetime

import ccdproc as ccdp
from astropy.stats import mad_std
import numpy as np

from calibrate import calibrate_collection
import config as cfg
import helpers as hlp


calibration_path = Path(cfg.CALIBRATION_PATH)
calibration_masters = ccdp.ImageFileCollection(calibration_path)

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description='Master dark generation script. Uses average combination and sigma clipping pixel rejection. Generates bias-substracted and raw masters.')
    parser.add_argument(
        'files', help='input files (FITS only)', type=str, nargs='+')
    parser.add_argument('-c', '--calibrated', action='store_true',
                        help='generate bias-substracted master dark')
    parser.add_argument(
        '-s', '--sigmalow', help='sigma low threshold for pixel rejection (default=5)', default=5)
    parser.add_argument(
        '-S', '--sigmahigh', help='sigma high threshold for pixel rejection (default=5)', default=5)
    parser.add_argument('-y', '--noconfirm',
                        action='store_true', help='skip confirmation')
    args = parser.parse_args()

    hlp.config_display()
    if not args.noconfirm:
        hlp.prompt()

    dark_images = ccdp.ImageFileCollection(
        filenames=args.files).filter(frame='dark')

    if dark_images:
        print('\nFiles to combine:')
        hlp.collection_summary(dark_images, ['frame', 'instrume', 'exptime'
                                             'ccd-temp', 'gain', 'offset', 'naxis1', 'naxis2'])

        if not args.noconfirm:
            hlp.prompt()

        hlp.header_correction(dark_images)

        if args.calibrated:
            options = argparse.Namespace(biasonly=True)
            calibrated_dark_images = calibrate_collection(dark_images, options)

            master_dark = ccdp.combine(
                calibrated_dark_images.files_filtered(include_path=True),
                method='average',
                sigma_clip=True,
                sigma_clip_low_thresh=int(args.sigmalow),
                sigma_clip_high_thresh=int(args.sigmahigh),
                sigma_clip_func=np.ma.median,
                sigma_clip_dev_func=mad_std,
                mem_limit=350e6
            )

            master_type = 'master_dark_calibrated'

        else:
            master_dark = ccdp.combine(
                dark_images.files_filtered(include_path=True),
                method='average',
                sigma_clip=True,
                sigma_clip_low_thresh=int(args.sigmalow),
                sigma_clip_high_thresh=int(args.sigmahigh),
                sigma_clip_func=np.ma.median,
                sigma_clip_dev_func=mad_std,
                mem_limit=600e7
            )

            master_type = 'master_dark'

        exptime = str(round(master_dark.header['exptime']))
        ccd_temp = str(round(master_dark.header['ccd-temp']))
        date_obs = datetime.strptime(
            master_dark.header['date-obs'], '%Y-%m-%dT%H:%M:%S.%f')
        date_string = date_obs.strftime('%Y%m%d')

        filename = f'{date_string}_{master_type}{exptime}s{ccd_temp}C'
        if 'gain' in master_dark.header:
            gain = str(round(master_dark.header['gain']))
            offset = str(round(master_dark.header['offset']))
            filename = f'{filename}_{gain}g{offset}o'
        filename = f'{filename}.fits'

        master_dark.meta['combined'] = True
        master_dark.write(calibration_path/filename, overwrite=True)
        run(['ds9', '-asinh', calibration_path/filename], check=True)
