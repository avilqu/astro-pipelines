#!/opt/anaconda/bin/python

''' Image registration script. Reprojection method (requiring valid WCS) only 
    supported for now. Star alignment with astroalign package in the future.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


import os
from pathlib import Path

import ccdproc as ccdp

from helpers import header_correction

if __name__ == "__main__":

    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description='Image registration script. Methods supported are reprojection (requires a valid WCS header) and star alignment with astroalign')
    parser.add_argument('-d', '--dir', action='store_true',
                        help='register all fits files in current directory')
    parser.add_argument('-f', '--files', nargs="+",
                        help='select fits files to register')
    parser.add_argument('-r', '--reference',
                        help='select reference image')
    parser.add_argument('-p', '--reproject', action='store_true',
                        help='use reprojection method (requires a valid WCS header')
    parser.add_argument('-a', '--align', action='store_true',
                        help='use star alignment method')
    parser.add_argument('-y', '--noconfirm',
                        action='store_true', help='skip confirmation')
    args = parser.parse_args()

    if not args.reference:
        print('Need a reference image.')
        parser.print_usage()
        sys.exit()

    if args.dir and args.files:
        print('Options --dir and and --file are exclusive.')
        parser.print_usage()
        sys.exit()

    if args.dir:
        lightImages = ccdp.ImageFileCollection(
            os.getcwd()).filter(frame='light')
    elif args.files:
        lightImages = ccdp.ImageFileCollection(
            filenames=args.files).filter(frame='light')
    else:
        print('No files selected. User either --dir for the full current directory or --files for individual images.')
        parser.print_usage()
        sys.exit()

    if 'lightImages' in locals():
        registered_path = Path(os.getcwd() + '/registered')
        registered_path.mkdir(exist_ok=True)

        print('\nFiles to register:')
        print(lightImages.summary['object', 'date-obs', 'frame',
                                  'instrume', 'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])

        target_wcs = ccdp.CCDData.read(args.reference).wcs
        print('\nReference image: ' + args.reference)

        if not args.noconfirm:
            if input('\nContinue? (Y/n) ') == 'n':
                sys.exit()

        header_correction(lightImages)

    for img, filename in lightImages.ccds(return_fname=True):
        ccdp.wcs_project(img, target_wcs).write(
            registered_path / filename, overwrite=True)
