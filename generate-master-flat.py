#!/opt/anaconda/bin/python

''' Generate master flat from a set of files and stores it in the calibration_path variable.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


from pathlib import Path
from subprocess import run
from datetime import datetime

import ccdproc as ccdp
from astropy.stats import mad_std
import numpy as np
from matplotlib import pyplot as plt

from calibrate import calibrate_collection
from lib_helpers import header_correction

calibration_path = Path('/home/tan/Astro/calibration/ST402')
calibration_masters = ccdp.ImageFileCollection(calibration_path)

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description='Master flat generation script. Uses average combination and sigma clipping pixel rejection. Generates bias-substracted and raw masters.')
    parser.add_argument(
        'files', help='input files (FITS only)', type=str, nargs='+')
    parser.add_argument('-c', '--calibrated', action='store_true',
                        help='generate bias-substracted master dark')
    parser.add_argument(
        '-s', '--sigmalow', help='sigma low threshold for pixel rejection', default=5)
    parser.add_argument(
        '-S', '--sigmahigh', help='sigma high threshold for pixel rejection', default=5)
    parser.add_argument('-y', '--noconfirm',
                        action='store_true', help='skip confirmation')
    args = parser.parse_args()

    flat_images = ccdp.ImageFileCollection(
        filenames=args.files).filter(frame='flat')

    if flat_images:
        print('\nFiles to combine:')
        print(flat_images.summary['date-obs', 'frame', 'instrume',
                                  'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])

        median_count = [np.median(data) for data in flat_images.data()]
        mean_count = [np.mean(data) for data in flat_images.data()]
        plt.plot(median_count, label='median')
        plt.plot(mean_count, label='mean')
        plt.xlabel('Image number')
        plt.ylabel('Count (ADU)')
        plt.title('Pixel value in calibrated flat frames')
        plt.legend()
        print('Close plot window to continue...')
        plt.show()

        if not args.noconfirm:
            if input('\nContinue? (Y/n) ') == 'n':
                exit()

        header_correction(flat_images)

        options = argparse.Namespace(noflat=True)
        calibrated_flat_images = calibrate_collection(flat_images, options)

        def inv_median(a):
            ''' Generate scale option for the combine method. '''
            return 1 / np.median(a)

        master_flat = ccdp.combine(
            calibrated_flat_images.files_filtered(include_path=True),
            method='average',
            scale=inv_median,
            sigma_clip=True,
            sigma_clip_low_thresh=int(args.sigmalow),
            sigma_clip_high_thresh=int(args.sigmahigh),
            sigma_clip_func=np.ma.median,
            signma_clip_dev_func=mad_std,
            mem_limit=350e6
        )

        date_obs = datetime.strptime(
            master_flat.header['date-obs'], '%Y-%m-%dT%H:%M:%S.%f')
        date_string = date_obs.strftime('%Y%m%d')
        filter_code = str(master_flat.header['filter'])
        ccd_temp = str(master_flat.header['ccd-temp'])
        filename = date_string + '_masterFlat' + filter_code + ccd_temp + 'C.fits'

        master_flat.meta['combined'] = True
        master_flat.write(calibration_path/filename, overwrite=True)
        run(['ds9', '-asinh', calibration_path/filename], check=True)
