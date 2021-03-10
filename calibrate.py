#!/opt/anaconda/bin/python

''' Image reduction script. Can be executed or used by importing image_calibration or calibrate_collection.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


import os
from pathlib import Path

import ccdproc as ccdp
from astropy import units as u

from helpers import header_correction

calibration_path = Path('/home/tan/Astro/calibration/ST402')
calibration_masters = ccdp.ImageFileCollection(calibration_path)


def find_master_bias(image, temp_tolerance=1):
    ''' Finds and returns a master bias with matching temperature for the input image. '''

    temp = image.header['ccd-temp']
    match = False
    for img, fname in calibration_masters.ccds(frame='Bias', return_fname=True):
        if abs(img.header['ccd-temp'] - temp) <= temp_tolerance:
            match = img
            master_bias = fname
            break
    if match:
        print('Master bias: ' + master_bias)
        return match
    else:
        print('Could not find a suitable master bias for temperature {}C.'.format(temp))
        return False


def find_master_dark(image, temp_tolerance=1, exposure_tolerance=0.5):
    ''' Finds and returns a master dark with matching temperature and exposure for the input image. '''

    exposure = image.header['exptime']
    temp = image.header['ccd-temp']
    match = False
    for img, fname in calibration_masters.ccds(frame='Dark', return_fname=True):
        if abs(img.header['ccd-temp'] - temp) <= temp_tolerance and abs(img.header['exptime'] - exposure) <= exposure_tolerance:
            match = img
            master_dark = fname
            break
    if match:
        print('Master dark: ' + master_dark)
        return match
    else:
        print('Could not find a suitable master dark for exposure {} and temperature {}C.'.format(
            exposure, temp))
        return False


def find_calibrated_master_dark(image, temp_tolerance=1):
    ''' Finds and returns a calibrated master dark with matching temperature for the input image. '''

    exposure = image.header['exptime']
    temp = image.header['ccd-temp']
    match = False
    for img, fname in calibration_masters.ccds(frame='Dark', return_fname=True):
        if abs(img.header['ccd-temp'] - temp) <= temp_tolerance and img.header['exptime'] >= exposure and 'subbias' in img.header:
            match = img
            master_dark = fname
            break
    if match:
        print('Calibrated master dark: ' + master_dark)
        return match
    else:
        print('Could not find a suitable calibrated master dark for exposure {} and temperature {}C.'.format(
            exposure, temp))
        return False


def find_master_flat(image, temp_tolerance=1):
    ''' Finds and returns a master flat with matching temperature and filter for the input image. '''

    temp = image.header['ccd-temp']
    filter_code = image.header['filter']
    match = False
    for img, fname in calibration_masters.ccds(frame='Flat', filter=filter_code, return_fname=True):
        if abs(img.header['ccd-temp'] - temp) <= temp_tolerance:
            match = img
            master_flat = fname
            break
    if match:
        print('Master flat: ' + master_flat)
        return match
    else:
        print('Could not find a suitable master flat for filter {} and temperature {}C.'.format(
            filter_code, temp))
        return False


def image_calibration(img, fname, options):
    ''' Contains the calibration routine. Takes a single image as input and returns a calibrated image. '''

    print('Calibrating {}...'.format(fname))

    if 'biasonly' in options and options.biasonly:
        master_bias = find_master_bias(img)
        print('Bias substraction...')
        img = ccdp.subtract_bias(img, master_bias)

    elif 'flatonly' in options and options.flatonly:
        master_flat = find_master_flat(img)
        if master_flat:
            print('Flat correction...')
            img = ccdp.flat_correct(img, master_flat)

    else:
        master_dark = find_master_dark(img)

        if master_dark:
            print('Dark substraction...')
            img = ccdp.subtract_dark(
                img, master_dark, exposure_time='exptime', exposure_unit=u.second)

        else:
            master_dark = find_calibrated_master_dark(img)
            if master_dark:
                master_bias = find_master_bias(img)
                if master_bias:
                    print('Bias substraction...')
                    img = ccdp.subtract_bias(img, master_bias)
                if master_dark:
                    print('Calibrated dark substraction...')
                    img = ccdp.subtract_dark(
                        img, master_dark, exposure_time='exptime', exposure_unit=u.second, scale=True)
            else:
                print('No dark or bias substraction.')

        if not options.noflat:
            master_flat = find_master_flat(img)
            if master_flat:
                print('Flat correction...')
                img = ccdp.flat_correct(img, master_flat)

        else:
            print('Skipping flat correction.')

    write_path = Path(os.getcwd() + '/reduced')
    write_path.mkdir(exist_ok=True)
    img.write(write_path / fname, overwrite=True)

    print('---')

    return img


def calibrate_collection(collection, options):
    ''' Wrapper to use the image_calibration function with a whole collection. Returns calibrated collection. '''

    write_path = Path(os.getcwd() + '/reduced')
    write_path.mkdir(exist_ok=True)

    for img, fname in collection.ccds(return_fname=True):
        image_calibration(img, fname, options).write(
            write_path / fname, overwrite=True)

    return ccdp.ImageFileCollection(write_path)


if __name__ == "__main__":

    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description='Basic image reduction script. Reads a list of calibration masters from the calibration_path variable and finds the best match for each frame.')
    parser.add_argument('-d', '--dir', action='store_true',
                        help='calibrate all fits files in current directory')
    parser.add_argument('-f', '--files', nargs="+",
                        help='select fits files to calibrate')
    parser.add_argument('-n', '--noflat', action='store_true',
                        help='skip flat correction')
    parser.add_argument('-b', '--biasonly', action='store_true',
                        help='only apply bias substraction')
    parser.add_argument('-F', '--flatonly', action='store_true',
                        help='only apply flat correction')
    parser.add_argument('-p', '--platesolve', action='store_true',
                        help='platesolve images with local astromery index')
    parser.add_argument('-y', '--noconfirm',
                        action='store_true', help='skip confirmation')
    args = parser.parse_args()

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
        calibrated_path = Path(os.getcwd() + '/reduced')
        calibrated_path.mkdir(exist_ok=True)

        print('Caliration masters:')
        print(calibration_masters.summary['file', 'frame', 'instrume',
                                          'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])
        # print(calibration_masters.summary['file', 'frame', 'filter' ,'exptime', 'ccd-temp', 'naxis1', 'naxis2'])
        print('\nFiles to calibrate:')
        print(lightImages.summary['object', 'date-obs', 'frame',
                                  'instrume', 'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])
        # print(lightImages.summary['file', 'frame', 'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])

        if not args.noconfirm:
            if input('\nContinue? (Y/n) ') == 'n':
                exit()

        header_correction(lightImages)

        print(args)

        for frame, filename in lightImages.ccds(return_fname=True):
            image_calibration(frame, filename, args).write(
                calibrated_path / filename, overwrite=True)
