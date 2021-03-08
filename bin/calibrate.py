#!/opt/anaconda/bin/python

import ccdproc as ccdp
from astropy import units as u
from pathlib import Path
import os

calibrationPath = Path('/home/tan/Astro/calibration/ST402')
calibrationMasters = ccdp.ImageFileCollection(calibrationPath)


def headerCorrection(collection):
    for hdu in collection.hdus(overwrite=True):
        hdu.header['bunit'] = 'adu'
        hdu.header['instrume'] = 'SBIG ST-402ME'
        hdu.header['telescop'] = 'RC8 200/1620 f/8.1'
        hdu.header['observer'] = 'Adrien Vilquin Barrajon'
        hdu.header.pop('radecsys', None)
        hdu.header['radesys'] = 'FK5'


def findMasterBias(image, tempTolerance=1):
    temp = image.header['ccd-temp']
    match = False
    for img, fname in calibrationMasters.ccds(frame='Bias', return_fname=True):
        if (abs(img.header['ccd-temp'] - temp) <= tempTolerance):
            match = img
            masterBias = fname
            break
    if (match):
        print('Master bias: ' + fname)
        return match
    else:
        print('Could not find a suitable master bias for temperature {}C.'.format(temp))


def findMasterDark(image, tempTolerance=1, expTolerance=0.5):
    exposure = image.header['exptime']
    temp = image.header['ccd-temp']
    match = False
    for img, fname in calibrationMasters.ccds(frame='Dark', return_fname=True):
        if (abs(img.header['ccd-temp'] - temp) <= tempTolerance and abs(img.header['exptime'] - exposure) <= expTolerance):
            match = img
            masterDark = fname
            break
    if (match):
        print('Master dark: ' + fname)
        return match
    else:
        print('Could not find a suitable master dark for exposure {} and temperature {}C.'.format(
            exposure, temp))


def findCalibratedMasterDark(image, tempTolerance=1):
    exposure = image.header['exptime']
    temp = image.header['ccd-temp']
    match = False
    for img, fname in calibrationMasters.ccds(frame='Dark', return_fname=True):
        if (abs(img.header['ccd-temp'] - temp) <= tempTolerance and img.header['exptime'] >= exposure and 'subbias' in img.header):
            match = img
            masterDark = fname
            break
    if (match):
        print('Calibrated master dark: ' + fname)
        return match
    else:
        print('Could not find a suitable calibrated master dark for exposure {} and temperature {}C.'.format(
            exposure, temp))


def findMasterFlat(image, tempTolerance=1):
    temp = image.header['ccd-temp']
    filter = image.header['filter']
    match = False
    for img, fname in calibrationMasters.ccds(frame='Flat', filter=filter, return_fname=True):
        if (abs(img.header['ccd-temp'] - temp) <= tempTolerance):
            match = img
            masterFlat = fname
            break
    if (match):
        print('Master flat: ' + fname)
        return match
    else:
        print('Could not find a suitable master flat for filter {} and temperature {}C.'.format(
            filter, temp))


def imageCalibration(img, fname, options):
    print('Calibrating {}...'.format(fname))

    if (options.biasonly):
        masterBias = findMasterBias(img)
        print('Bias substraction...')
        img = ccdp.subtract_bias(img, masterBias)

    else:
        masterDark = findMasterDark(img)

        if (masterDark):
            print('Dark substraction...')
            img = ccdp.subtract_dark(
                img, masterDark, exposure_time='exptime', exposure_unit=u.second)

        else:
            masterDark = findCalibratedMasterDark(img)
            if (masterDark):
                masterBias = findMasterBias(img)
                if (masterBias):
                    print('Bias substraction...')
                    img = ccdp.subtract_bias(img, masterBias)
                if (masterDark):
                    print('Calibrated dark substraction...')
                    img = ccdp.subtract_dark(
                        img, masterDark, exposure_time='exptime', exposure_unit=u.second, scale=True)
            else:
                print('No dark or bias substraction.')

        if (not options.noflat):
            masterFlat = findMasterFlat(img)
            if (masterFlat):
                print('Flat correction...')
                img = ccdp.flat_correct(img, masterFlat)

        else:
            print('Skipping flat correction.')

    if (options.write):
        calibratedPath = Path(os.getcwd() + '/reduced')
        calibratedPath.mkdir(exist_ok=True)
        img.write(calibratedPath / fname, overwrite=True)

    print('---')

    return img


def calibrateCollection(collection, options):
    if (options.write):
        calibratedPath = Path(os.getcwd() + '/reduced')
        calibratedPath.mkdir(exist_ok=True)

        for img, fname in collection.ccds(return_fname=True):
            imageCalibration(img, fname, options).write(
                calibratedPath / fname, overwrite=True)

        return ccdp.ImageFileCollection(calibratedPath)


if __name__ == "__main__":

    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description='Basic image reduction script. Reads a list of calibration masters from the calibrationPath variable and finds the best match for each frame.')
    parser.add_argument('-d', '--dir', action='store_true',
                        help='calibrate all fits files in current directory')
    parser.add_argument('-f', '--files', nargs="+",
                        help='select fits files to calibrate')
    parser.add_argument('-n', '--noflat', action='store_true',
                        help='skip flat calibration')
    parser.add_argument('-b', '--biasonly', action='store_true',
                        help='only do bias substraction')
    parser.add_argument('-p', '--platesolve', action='store_true',
                        help='platesolve images with local astromery index')
    parser.add_argument('-w', '--write', action='store_true',
                        help='write file (default=True)', default=True)
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
        calibratedPath = Path(os.getcwd() + '/reduced')
        calibratedPath.mkdir(exist_ok=True)

        print('Caliration masters:')
        print(calibrationMasters.summary['file', 'frame', 'instrume',
                                         'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])
        # print(calibrationMasters.summary['file', 'frame', 'filter' ,'exptime', 'ccd-temp', 'naxis1', 'naxis2'])
        print('\nFiles to calibrate:')
        print(lightImages.summary['object', 'date-obs', 'frame',
                                  'instrume', 'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])
        # print(lightImages.summary['file', 'frame', 'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])

        if not args.noconfirm:
            if input('\nContinue? (Y/n) ') == 'n':
                exit()

        headerCorrection(lightImages)

        for img, fname in lightImages.ccds(return_fname=True):
            imageCalibration(img, fname, args).write(
                calibratedPath / fname, overwrite=True)
