#!/opt/anaconda/bin/python

from pathlib import Path
import sys
import os
from subprocess import run
from datetime import datetime

import ccdproc as ccdp
from astropy.stats import mad_std
import numpy as np

from calibrate import headerCorrection

calibrationPath = Path('/home/tan/Astro/calibration/ST402')

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(description='Master bias generation script. Uses average combination and sigma clipping pixel rejection.')
    parser.add_argument('-d', '--dir', action='store_true', help='combine all fits files in current directory')
    parser.add_argument('-f', '--files', nargs="+", help='select fits files to combine')
    parser.add_argument('-s', '--sigmalow', help='sigma low threshold for pixel rejection (default=5)', default=5)
    parser.add_argument('-S', '--sigmahigh', help='sigma high threshold for pixel rejection (default=5)', default=5)
    parser.add_argument('-y', '--noconfirm', action='store_true', help='skip confirmation')
    args = parser.parse_args()

    if args.dir and args.files:
        print('Options --dir and and --file are exclusive.')
        parser.print_usage()
        sys.exit()

    if args.dir:
        biasImages = ccdp.ImageFileCollection(os.getcwd()).filter(frame='bias')
    elif args.files:
        biasImages = ccdp.ImageFileCollection(filenames=args.files).filter(frame='bias')
    else:
        print('No files selected. User either --dir for the full current directory or --files for individual images.')
        parser.print_usage()
        sys.exit()

    if 'biasImages' in locals():
        print('\nFiles to combine:')
        print(biasImages.summary['date-obs', 'frame', 'instrume', 'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])

        if not args.noconfirm:
            if input('\nContinue? (Y/n) ') == 'n':
                exit()

        headerCorrection(biasImages)

        masterBias = ccdp.combine(
            biasImages.files_filtered(include_path=True),
            method='average',
            sigma_clip=True,
            sigma_clip_low_thresh=int(args.sigmalow),
            sigma_clip_high_thresh=int(args.sigmahigh),
            sigma_clip_func=np.ma.median,
            sigma_clip_dev_func=mad_std,
            mem_limit=350e6
        )

        ccdTemp = str(round(masterBias.header['ccd-temp']))
        dateObs = datetime.strptime(masterBias.header['date-obs'], '%Y-%m-%dT%H:%M:%S.%f')
        dateString = dateObs.strftime('%Y%m%d')
        filename = dateString + '_masterBias' + ccdTemp + 'C.fits'

        masterBias.meta['combined'] = True
        masterBias.write(calibrationPath/filename, overwrite=True)
        run(['ds9', '-asinh', calibrationPath/filename])
