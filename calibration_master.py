#!/opt/anaconda/bin/python

''' Contains main class for calibration masters generation and image calibration.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


from pathlib import Path
from datetime import datetime
import os
import shutil

import ccdproc as ccdp
from astropy import units as u
from astropy.stats import mad_std
import numpy as np

import config as cfg
import helpers as hlp


calib_path = Path(cfg.CALIBRATION_PATH)


class CalibrationMaster:

    def __init__(self, data=None):
        self.main_path = Path(cfg.CALIBRATION_PATH)
        self.masters = ccdp.ImageFileCollection(self.main_path)

        if data:
            self.collection = ccdp.ImageFileCollection(filenames=data)

    def print_calibration_masters(self):
        print(f'Calibration masters for camera {cfg.CCD_LABEL}')
        try:
            print(self.masters.summary['frame', 'exptime', 'instrume',
                  'filter', 'ccd-temp', 'gain', 'offset', 'naxis1', 'naxis2'])
        except:
            print(self.masters.summary['frame', 'exptime', 'instrume',
                  'filter', 'ccd-temp', 'naxis1', 'naxis2'])

    def image_integration(self, flat=False):
        scale = None
        if flat:
            def inv_median(a):
                return 1 / np.median(a)
            scale = inv_median

        print('Integrating files...')
        stack = ccdp.combine(
            self.collection.files_filtered(include_path=True),
            method='average',
            scale=scale,
            sigma_clip=True,
            sigma_clip_low_thresh=cfg.SIGMA_LOW,
            sigma_clip_high_thresh=cfg.SIGMA_HIGH,
            sigma_clip_func=np.ma.median,
            sigma_clip_dev_func=mad_std,
            mem_limit=600e7
        )

        return stack

    def generate_calibration_master(self, frame):
        if not hasattr(self, 'collection'):
            print('[E] No input files. Cannot generate calibration master.')
            return

        hlp.header_correction(self.collection)

        if frame == 'bias' or frame == 'dark':
            stack = self.image_integration()

        elif frame == 'dark_c':
            self.collection = self.calibrate_collection(
                {'biasonly': True}, self.collection)
            stack = self.image_integration()
            stack.header['frame'] = 'Dark_c'
            shutil.rmtree(f'{os.getcwd()}/calibrated/')

        elif frame == 'flat':
            self.collection = self.calibrate_collection(
                {'noflat': True}, self.collection)
            stack = self.image_integration(True)
            shutil.rmtree(f'{os.getcwd()}/calibrated/')

        else:
            print('[E] Wrong operation')

        exptime = str(round(stack.header['exptime']))
        ccd_temp = str(round(stack.header['ccd-temp']))
        date_obs = datetime.strptime(
            stack.header['date-obs'], '%Y-%m-%dT%H:%M:%S.%f')
        date_string = date_obs.strftime('%Y%m%d')

        if frame == 'bias':
            filename = f'{date_string}_master_bias_{ccd_temp}C'
        if frame == 'dark':
            filename = f'{date_string}_master_dark_{exptime}s{ccd_temp}C'
        if frame == 'dark_c':
            filename = f'{date_string}_master_dark_calibrated_{exptime}s{ccd_temp}C'
        if frame == 'flat':
            filename = f'{date_string}_master_flat_{str(stack.header["filter"])}{ccd_temp}C'
        if 'gain' in stack.header:
            gain = str(round(stack.header['gain']))
            offset = str(round(stack.header['offset']))
            filename = f'{filename}_{gain}g{offset}o'
        filename = f'{filename}.fits'

        stack.meta['combined'] = True
        stack.write(calib_path/filename, overwrite=True)

        return calib_path/filename

    def find_master_bias(self, image):
        temp = image.header['ccd-temp']
        match = False

        for img, fname in self.masters.ccds(frame='Bias', return_fname=True):
            if abs(img.header['ccd-temp'] - temp) <= cfg.TEMP_TOLERANCE:
                if not ('gain' in img.header and (img.header['gain'] != image.header['gain'] or img.header['offset'] != image.header['offset'])):
                    match = img
                    master_bias = fname
                    break
        if match:
            print('Master bias: ' + master_bias)
            return match
        else:
            print('[W] Could not find a suitable master bias.')
            return False

    def find_master_dark(self, image):
        exposure = image.header['exptime']
        temp = image.header['ccd-temp']
        match = False

        for img, fname in self.masters.ccds(frame='Dark', return_fname=True):
            if abs(img.header['ccd-temp'] - temp) <= cfg.TEMP_TOLERANCE and abs(img.header['exptime'] - exposure) <= cfg.TEMP_TOLERANCE:
                if not ('gain' in img.header and (img.header['gain'] != image.header['gain'] or img.header['offset'] != image.header['offset'])):
                    match = img
                    master_dark = fname
                    break
        if match:
            print('Master dark: ' + master_dark)
            return match
        else:
            print('[W] Could not find a suitable master dark.')
            return False

    def find_master_dark_c(self, image):
        exposure = image.header['exptime']
        temp = image.header['ccd-temp']
        results = []
        exp_diff = []
        filenames = []

        for img, fname in self.masters.ccds(frame='Dark_c', return_fname=True):
            if abs(img.header['ccd-temp'] - temp) <= cfg.TEMP_TOLERANCE and img.header['exptime'] >= exposure:
                if not ('gain' in img.header and (img.header['gain'] != image.header['gain'] or img.header['offset'] != image.header['offset'])):
                    results.append(img)
                    exp_diff.append(img.header['exptime'] - exposure)
                    filenames.append(fname)

        if len(results) > 0:
            match = exp_diff.index(min(exp_diff))
            print('Calibrated master dark: ' + filenames[match])
            return results[match]

        else:
            print('[W] Could not find a suitable calibrated master dark.')
            return False

    def find_master_flat(self, image):
        temp = image.header['ccd-temp']
        filter_code = image.header['filter']
        match = False
        for img, fname in self.masters.ccds(frame='Flat', filter=filter_code, return_fname=True):
            if abs(img.header['ccd-temp'] - temp) <= cfg.TEMP_TOLERANCE:
                match = img
                master_flat = fname
                break
        if match:
            print('Master flat: ' + master_flat)
            return match
        else:
            print('[W] Could not find a suitable master flat.')
            return False

    def calibrate_image(self, options, img):
        if 'biasonly' in options:
            master_bias = self.find_master_bias(img)
            if master_bias:
                print('Bias substraction...')
                img = ccdp.subtract_bias(img, master_bias)

        elif 'flatonly' in options:
            master_flat = self.find_master_flat(img)
            if master_flat:
                print('Flat correction...')
                img = ccdp.flat_correct(img, master_flat)

        else:
            master_dark = self.find_master_dark(img)

            if master_dark:
                print('Dark substraction...')
                img = ccdp.subtract_dark(
                    img, master_dark, exposure_time='exptime', exposure_unit=u.second)

            else:
                master_dark = self.find_master_dark_c(img)
                if master_dark:
                    master_bias = self.find_master_bias(img)
                    if master_bias:
                        print('Bias substraction...')
                        img = ccdp.subtract_bias(img, master_bias)
                        print('Calibrated dark substraction...')
                    else:
                        print('Substracting calibrated dark without bias...')
                    img = ccdp.subtract_dark(
                        img, master_dark, exposure_time='exptime', exposure_unit=u.second, scale=True)
                else:
                    master_bias = self.find_master_bias(img)
                    if master_bias:
                        print('No dark substraction.')
                        print('Bias substraction...')
                        img = ccdp.subtract_bias(img, master_bias)
                    else:
                        print('No dark or bias substraction.')

            if not 'noflat' in options:
                master_flat = self.find_master_flat(img)
                if master_flat:
                    print('Flat correction...')
                    img = ccdp.flat_correct(img, master_flat)
                else:
                    print('No flat correction.')

            else:
                print('Skipping flat correction.')

        return img

    def calibrate_collection(self, options, collection):
        write_path = Path(f'{os.getcwd()}/calibrated')
        write_path.mkdir(exist_ok=True)

        for img, fname in collection.ccds(return_fname=True):
            self.calibrate_image(options, img).write(
                write_path / fname, overwrite=True)

        return ccdp.ImageFileCollection(write_path)

    def calibrate(self, options):
        hlp.header_correction(self.collection)
        self.calibrate_collection(options, self.collection)

    def register_collection(self, reference):
        write_path = Path(f'{os.getcwd()}/registered')
        write_path.mkdir(exist_ok=True)
        target_wcs = ccdp.CCDData.read(reference).wcs
        for img, fname in self.collection.ccds(return_fname=True):
            ccdp.wcs_project(img, target_wcs).write(
                write_path / fname, overwrite=True)
