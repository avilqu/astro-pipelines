#!/opt/anaconda/bin/python

''' Generate master bias from a set of files and stores it in the CALIBRATION_PATH config constant.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


from pathlib import Path
from subprocess import run
from datetime import datetime

import ccdproc as ccdp
from astropy.stats import mad_std
import numpy as np

import config as cfg
import helpers as hlp


calibration_path = Path(cfg.CALIBRATION_PATH)

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description='Master bias generation script. Uses average combination and sigma clipping pixel rejection.')
    parser.add_argument(
        'files', help='input files (FITS only)', type=str, nargs='+')
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

    bias_images = ccdp.ImageFileCollection(
        filenames=args.files).filter(frame='bias')

    if bias_images:
        print('\nFiles to combine:')
        hlp.collection_summary(bias_images, ['frame', 'instrume',
                                             'ccd-temp', 'gain', 'offset', 'naxis1', 'naxis2'])

        if not args.noconfirm:
            hlp.prompt()

        hlp.header_correction(bias_images)

        master_bias = ccdp.combine(
            bias_images.files_filtered(include_path=True),
            method='average',
            sigma_clip=True,
            sigma_clip_low_thresh=int(args.sigmalow),
            sigma_clip_high_thresh=int(args.sigmahigh),
            sigma_clip_func=np.ma.median,
            sigma_clip_dev_func=mad_std,
            mem_limit=600e7
        )

        ccd_temp = str(round(master_bias.header['ccd-temp']))
        date_obs = datetime.strptime(
            master_bias.header['date-obs'], '%Y-%m-%dT%H:%M:%S.%f')
        date_string = date_obs.strftime('%Y%m%d')

        filename = f'{date_string}_master_bias{ccd_temp}C'
        if 'gain' in master_bias.header:
            gain = str(round(master_bias.header['gain']))
            offset = str(round(master_bias.header['offset']))
            filename = f'{filename}_{gain}g{offset}o'
        filename = f'{filename}.fits'

        master_bias.meta['combined'] = True
        master_bias.write(calibration_path/filename, overwrite=True)
        run(['ds9', '-asinh', calibration_path/filename], check=True)
