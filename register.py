#!/opt/anaconda/bin/python

''' Image registration script. Reprojection method (requiring valid WCS) only
    supported for now. Star alignment with astroalign package in the future.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


import os
from pathlib import Path

import ccdproc as ccdp
import astroalign as aa

import helpers as hlp

if __name__ == "__main__":

    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description='Image registration script. Methods supported are reprojection (requires a valid WCS header) and star alignment with astroalign.')
    parser.add_argument(
        'files', help='input files (FITS only)', type=str, nargs='+')
    parser.add_argument('-r', '--reference',
                        help='select reference image')
    parser.add_argument('-p', '--reproject', action='store_true',
                        help='use reprojection method (requires a valid WCS header)')
    parser.add_argument('-a', '--align', action='store_true',
                        help='use star alignment method')
    parser.add_argument('-y', '--noconfirm',
                        action='store_true', help='skip confirmation')
    args = parser.parse_args()

    if not args.reference:
        print('Need a reference image.')
        parser.print_usage()
        sys.exit()

    lightImages = ccdp.ImageFileCollection(
        filenames=args.files).filter(frame='light')

    if lightImages:
        registered_path = Path(os.getcwd() + '/registered')
        registered_path.mkdir(exist_ok=True)

        print('\nFiles to register:')
        hlp.collection_summary(lightImages, ['object', 'date-obs',
                                             'instrume', 'filter', 'exptime'])

        print('\nReference image: ' + args.reference)

        if not args.noconfirm:
            hlp.prompt()

        hlp.header_correction(lightImages)

        if args.reproject:
            target_wcs = ccdp.CCDData.read(args.reference).wcs
            for img, filename in lightImages.ccds(return_fname=True):
                ccdp.wcs_project(img, target_wcs).write(
                    registered_path / filename, overwrite=True)

        elif args.align:
            target_data = ccdp.CCDData.read(args.reference)
            for img, filename in lightImages.ccds(return_fname=True):
                registered_image, footprint = aa.register(img, target_data)
                registered_image.write(
                    registered_path / filename, overwrite=True)

        else:
            print('Need an alignment method.')
