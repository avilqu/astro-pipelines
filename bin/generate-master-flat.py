#!/opt/anaconda/bin/python

from pathlib import Path
import sys
import os
from subprocess import run
from datetime import datetime

import ccdproc as ccdp
from astropy.stats import mad_std
import numpy as np
from matplotlib import pyplot as plt

from calibrate import headerCorrection, calibrateCollection

calibrationPath = Path('/home/tan/Astro/calibration/ST402')
calibrationMasters = ccdp.ImageFileCollection(calibrationPath)

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description='Master flat generation script. Uses average combination and sigma clipping pixel rejection. Generates bias-substracted and raw masters.')
    parser.add_argument('-d', '--dir', action='store_true',
                        help='combine all fits files in current directory')
    parser.add_argument('-f', '--files', nargs="+",
                        help='select fits files to combine')
    parser.add_argument('-c', '--calibrated', action='store_true',
                        help='generate bias-substracted master dark')
    parser.add_argument(
        '-s', '--sigmalow', help='sigma low threshold for pixel rejection', default=5)
    parser.add_argument(
        '-S', '--sigmahigh', help='sigma high threshold for pixel rejection', default=5)
    parser.add_argument('-y', '--noconfirm',
                        action='store_true', help='skip confirmation')
    args = parser.parse_args()

    if args.dir and args.files:
        print('Options --dir and and --file are exclusive.')
        parser.print_usage()
        sys.exit()

    if args.dir:
        flatImages = ccdp.ImageFileCollection(os.getcwd()).filter(frame='flat')
    elif args.files:
        flatImages = ccdp.ImageFileCollection(
            filenames=args.files).filter(frame='flat')
    else:
        print('No files selected. User either --dir for the full current directory or --files for individual images.')
        parser.print_usage()
        sys.exit()

    if 'flatImages' in locals():
        print('\nFiles to combine:')
        print(flatImages.summary['date-obs', 'frame', 'instrume',
                                 'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])

        medianCount = [np.median(data) for data in flatImages.data()]
        meanCount = [np.mean(data) for data in flatImages.data()]
        plt.plot(medianCount, label='median')
        plt.plot(meanCount, label='mean')
        plt.xlabel('Image number')
        plt.ylabel('Count (ADU)')
        plt.title('Pixel value in calibrated flat frames')
        plt.legend()
        print('Close plot window to continue...')
        plt.show()

        if not args.noconfirm:
            if input('\nContinue? (Y/n) ') == 'n':
                exit()

        headerCorrection(flatImages)

        options = argparse.Namespace(noflat=True, biasonly=False, write=True)
        calibratedFlatImages = calibrateCollection(flatImages, options)

        def inv_median(a):
            return 1 / np.median(a)

        masterFlat = ccdp.combine(
            calibratedFlatImages.files_filtered(include_path=True),
            method='average',
            scale=inv_median,
            sigma_clip=True,
            sigma_clip_low_thresh=int(args.sigmalow),
            sigma_clip_high_thresh=int(args.sigmahigh),
            sigma_clip_func=np.ma.median,
            signma_clip_dev_func=mad_std,
            mem_limit=350e6
        )

        dateObs = datetime.strptime(
            masterFlat.header['date-obs'], '%Y-%m-%dT%H:%M:%S.%f')
        dateString = dateObs.strftime('%Y%m%d')
        filterCode = str(masterFlat.header['filter'])
        ccdTemp = str(masterFlat.header['ccd-temp'])
        filename = dateString + '_masterFlat' + filterCode + ccdTemp + 'C.fits'

        masterFlat.meta['combined'] = True
        masterFlat.write(calibrationPath/filename, overwrite=True)
        run(['ds9', '-asinh', calibrationPath/filename], check=True)
