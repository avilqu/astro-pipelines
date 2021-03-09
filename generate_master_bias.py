#!/opt/anaconda/bin/python

''' Generate master bias from a set of files and stores it in the calibration_path variable.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


from pathlib import Path
import sys
import os
from subprocess import run
from datetime import datetime

import ccdproc as ccdp
from astropy.stats import mad_std
import numpy as np

from helpers import header_correction

calibration_path = Path('/home/tan/Astro/calibration/ST402')

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description='Master bias generation script. Uses average combination and sigma clipping pixel rejection.')
    parser.add_argument('-d', '--dir', action='store_true',
                        help='combine all fits files in current directory')
    parser.add_argument('-f', '--files', nargs="+",
                        help='select fits files to combine')
    parser.add_argument(
        '-s', '--sigmalow', help='sigma low threshold for pixel rejection (default=5)', default=5)
    parser.add_argument(
        '-S', '--sigmahigh', help='sigma high threshold for pixel rejection (default=5)', default=5)
    parser.add_argument('-y', '--noconfirm',
                        action='store_true', help='skip confirmation')
    args = parser.parse_args()

    if args.dir and args.files:
        print('Options --dir and and --file are exclusive.')
        parser.print_usage()
        sys.exit()

    if args.dir:
        bias_images = ccdp.ImageFileCollection(
            os.getcwd()).filter(frame='bias')
    elif args.files:
        bias_images = ccdp.ImageFileCollection(
            filenames=args.files).filter(frame='bias')
    else:
        print('No files selected. User either --dir for the full current directory or --files for individual images.')
        parser.print_usage()
        sys.exit()

    if 'bias_images' in locals():
        print('\nFiles to combine:')
        print(bias_images.summary['date-obs', 'frame', 'instrume',
                                  'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])

        if not args.noconfirm:
            if input('\nContinue? (Y/n) ') == 'n':
                exit()

        header_correction(bias_images)

        master_bias = ccdp.combine(
            bias_images.files_filtered(include_path=True),
            method='average',
            sigma_clip=True,
            sigma_clip_low_thresh=int(args.sigmalow),
            sigma_clip_high_thresh=int(args.sigmahigh),
            sigma_clip_func=np.ma.median,
            sigma_clip_dev_func=mad_std,
            mem_limit=350e6
        )

        ccd_temp = str(round(master_bias.header['ccd-temp']))
        date_obs = datetime.strptime(
            master_bias.header['date-obs'], '%Y-%m-%dT%H:%M:%S.%f')
        date_string = date_obs.strftime('%Y%m%d')
        filename = date_string + '_master_bias' + ccd_temp + 'C.fits'

        master_bias.meta['combined'] = True
        master_bias.write(calibration_path/filename, overwrite=True)
        run(['ds9', '-asinh', calibration_path/filename], check=True)
