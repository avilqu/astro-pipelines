#!/opt/anaconda/bin/python

''' Integrate calibrated and registered light frames.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


from subprocess import run

import ccdproc as ccdp
from astropy.stats import mad_std
import numpy as np

import helpers as hlp


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description='Integrate calibrated and registered light frames. Uses average combination and sigma clipping pixel rejection.')
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

    light_images = ccdp.ImageFileCollection(
        filenames=args.files).filter(frame='light')

    if light_images:
        # print('\nFiles to combine:')
        # hlp.collection_summary(light_images, ['object', 'date-obs',
        #                                       'instrume', 'filter', 'exptime'])

        # if not args.noconfirm:
        #     hlp.prompt()

        # hlp.header_correction(light_images)

        master = ccdp.combine(
            light_images.files_filtered(include_path=True),
            method='average',
            sigma_clip=True,
            sigma_clip_low_thresh=int(args.sigmalow),
            sigma_clip_high_thresh=int(args.sigmahigh),
            sigma_clip_func=np.ma.median,
            sigma_clip_dev_func=mad_std,
            mem_limit=600e7
        )

        filter_code = master.header['filter']
        filename = f'master_{filter_code}.fits'

        master.meta['combined'] = True
        master.write(filename, overwrite=True)
        run(['ds9', '-asinh', filename], check=True)
