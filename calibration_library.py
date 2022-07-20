''' Contains all the routines related to the creation, storage and use of calibration masters (bias, darks, flats).
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

from pathlib import Path
from datetime import datetime
import shutil
import glob
import os

from astropy.io import fits
from astropy.stats import mad_std
from astropy.nddata import CCDData
from astropy import units as u
import ccdproc as ccdp
import numpy as np
from colorama import Fore, Back, Style

from image_sequence import ImageSequence
import config as cfg
import helpers as hlp


write_path = Path(f'{os.getcwd()}/calibrated')
write_path.mkdir(exist_ok=True)


class CalibrationLibrary:


    def __init__(self, data=None):
        self.master_files = []
        
        for file in glob.glob(f'{cfg.CALIBRATION_PATH}/*.fits'):
            self.master_files.append(file)
        self.masters = ImageSequence(self.master_files)
        
        self.biases = []
        self.darks = []
        self.flats = []
        
        for file in self.masters.files:
            if file['header']['FRAME'] == 'Bias':
                self.biases.append(file)
            if file['header']['FRAME'] == 'Dark':
                self.darks.append(file)
            if file['header']['FRAME'] == 'Flat':
                self.flats.append(file)


    def generate_master_bias(self, seq):
        ''' Generates a master bias from the input FITS sequence 
        
            :param seq: ImageSequence object
            :return: True if successful
        '''

        print(f'\n{Style.BRIGHT}Generating master bias from {len(seq.filenames)} files.{Style.RESET_ALL}')
        hlp.prompt()

        stack = seq.integrate_sequence(confirm=False)

        ccd_temp = str(round(stack.header['CCD-TEMP']))
        date_obs = datetime.strptime(stack.header['DATE-OBS'], '%Y-%m-%dT%H:%M:%S.%f')
        date_string = date_obs.strftime('%Y%m%d')
        gain = str(round(stack.header['GAIN']))
        offset = str(round(stack.header['OFFSET']))
        filename = f'master_bias_{ccd_temp}C_{gain}g{offset}o_{date_string}.fits'

        stack.meta['IMAGETYP'] = 'Master Bias'

        print(f'Writing {cfg.CALIBRATION_PATH}/{filename}...')
        stack.write(f'{cfg.CALIBRATION_PATH}/{filename}', overwrite=True)
        shutil.rmtree(f'{os.getcwd()}/calibrated/')

        return True


    def generate_master_dark(self, seq):
        ''' Generates a calibrated master dark (bias subtracted)
            from the input FITS sequence 
        
            :param seq: ImageSequence object
            :return: True if success, False if failure
        '''

        print(f'\n{Style.BRIGHT}Generating master dark from {len(seq.filenames)} files.{Style.RESET_ALL}')
        hlp.prompt()

        print(f'\n{Style.BRIGHT}Calibrating {len(seq.filenames)} files.{Style.RESET_ALL}...')
        for image in seq.files:
            filename = image['filename']
            ccd_temp = image['header']['CCD-TEMP']
            gain = image['header']['GAIN']
            offset = image['header']['OFFSET']
            exptime = image['header']['EXPTIME']
            print(f'\n{Style.BRIGHT}Calibrating {filename}...{Style.RESET_ALL}')
            print(f'-- CCD_TEMP: {ccd_temp}')
            print(f'-- GAIN: {gain}')
            print(f'-- OFFSET: {offset}')
            print(f'-- EXPTIME: {exptime}')
            
            master_bias = self.find_master_bias(image)
            if not master_bias:
                print(f'{Style.BRIGHT + Fore.RED}Cannot generate master dark{Style.RESET_ALL}')
                return False
            
            calibrated_image = self.subtract_bias(image, master_bias)
            
            new_filename = f'b_{filename}'
            print(f'-- Writing {write_path/new_filename}...')
            calibrated_image.write(write_path / new_filename, overwrite=True)

        calibrated_files = []
        for file in glob.glob(f'{write_path}/*.fits'):
            calibrated_files.append(file)
        calibrated_sequence = ImageSequence(calibrated_files)

        stack = calibrated_sequence.integrate_sequence(confirm=False)

        exptime = str(round(stack.header['EXPTIME']))
        ccd_temp = str(round(stack.header['CCD-TEMP']))
        date_obs = datetime.strptime(stack.header['DATE-OBS'], '%Y-%m-%dT%H:%M:%S.%f')
        date_string = date_obs.strftime('%Y%m%d')
        gain = str(round(stack.header['GAIN']))
        offset = str(round(stack.header['OFFSET']))
        filename = f'master_dark_{exptime}_{ccd_temp}C_{gain}g{offset}o_{date_string}.fits'

        stack.meta['IMAGETYP'] = 'Master Dark'

        print(f'Writing {cfg.CALIBRATION_PATH}/{filename}...')
        stack.write(f'{cfg.CALIBRATION_PATH}/{filename}', overwrite=True)
        shutil.rmtree(f'{os.getcwd()}/calibrated/')
        
        return True


    def generate_master_flat(self, seq):
        ''' Generates a master flat from the input FITS sequence 
        
            :param seq: ImageSequence object
            :return: True if success, False if failure
        '''

        print(f'\n{Style.BRIGHT}Generating master flat from {len(seq.filenames)} files.{Style.RESET_ALL}')
        hlp.prompt()

        print(f'\n{Style.BRIGHT}Calibrating {len(seq.filenames)} files.{Style.RESET_ALL}...')
        for image in seq.files:
            filename = image['filename']
            ccd_temp = image['header']['CCD-TEMP']
            gain = image['header']['GAIN']
            offset = image['header']['OFFSET']
            exptime = image['header']['EXPTIME']
            filter_code = image['header']['FILTER']
            print(f'\n{Style.BRIGHT}Calibrating {filename}...{Style.RESET_ALL}')
            print(f'-- CCD_TEMP: {ccd_temp}')
            print(f'-- GAIN: {gain}')
            print(f'-- OFFSET: {offset}')
            print(f'-- EXPTIME: {exptime}')
            print(f'-- FILTER: {filter_code}')
            
            master_bias = self.find_master_bias(image)
            if not master_bias:
                print(f'{Style.BRIGHT + Fore.RED}Could not generate master flat!{Style.RESET_ALL}')
                return False
            
            calibrated_image = self.subtract_bias(image, master_bias)
            
            master_dark = self.find_master_dark(image)
            if not master_dark:
                print(f'{Style.BRIGHT + Fore.RED}Could not generate master flat!{Style.RESET_ALL}')
                return False
            
            calibrated_image = self.subtract_dark(calibrated_image, master_dark)
            
            new_filename = f'b_d_{filename}'
            print(f'-- Writing {write_path/new_filename}...')
            calibrated_image.write(write_path / new_filename, overwrite=True)

        calibrated_files = []
        for file in glob.glob(f'{write_path}/*.fits'):
            calibrated_files.append(file)
        calibrated_sequence = ImageSequence(calibrated_files)

        stack = calibrated_sequence.integrate_sequence(flat=True, confirm=False)

        filter_code = stack.header['FILTER']
        ccd_temp = str(round(stack.header['CCD-TEMP']))
        date_obs = datetime.strptime(stack.header['DATE-OBS'], '%Y-%m-%dT%H:%M:%S.%f')
        date_string = date_obs.strftime('%Y%m%d')
        gain = str(round(stack.header['GAIN']))
        offset = str(round(stack.header['OFFSET']))
        filename = f'master_flat_{filter_code}_{ccd_temp}C_{gain}g{offset}o_{date_string}.fits'

        stack.meta['IMAGETYP'] = 'Master Flat'

        print(f'Writing {cfg.CALIBRATION_PATH}/{filename}...')
        stack.write(f'{cfg.CALIBRATION_PATH}/{filename}', overwrite=True)
        shutil.rmtree(f'{os.getcwd()}/calibrated/')
        
        return True
        

    def find_master_bias(self, image):
        ''' Selects a suitable master bias with matching bias,
            offset and CCD temperature

            :param image: single element from ImageSequence
            :return: single element from ImageSequence if found, False if not
        '''

        temp = image['header']['CCD-TEMP']
        match = False

        for master in self.masters.files:
            if master['header']['FRAME'] == 'Bias':
                if abs(master['header']['CCD-TEMP'] - temp) <= cfg.TEMP_TOLERANCE:
                    if not ('GAIN' in master['header'] and (master['header']['GAIN'] != image['header']['GAIN'] or master['header']['OFFSET'] != image['header']['OFFSET'])):
                        match = master
                        master_bias = master['filename']
                        break

        if match:
            print(f'-- Master bias: {master_bias}')
            return match
        else:
            print(f'{Fore.YELLOW}-- Could not find a suitable master bias.{Style.RESET_ALL}')
            return False


    def find_master_dark(self, image):
        ''' Selects a suitable calibrated master dark 
            with matching bias, offset and CCD temperature

            :param image: single element from ImageSequence
            :return: single element from ImageSequence if found, False if not
        '''

        exposure = image['header']['EXPTIME']
        temp = image['header']['CCD-TEMP']
        match = False

        for master in self.masters.files:
            if master['header']['FRAME'] == 'Dark':
                if abs(master['header']['CCD-TEMP'] - temp) <= cfg.TEMP_TOLERANCE and master['header']['exptime'] >= exposure:
                    if not ('gain' in master['header'] and (master['header']['GAIN'] != image['header']['GAIN'] or master['header']['OFFSET'] != image['header']['OFFSET'])):
                        match = master
                        master_dark = master['filename']
                        break

        if match:
            print(f'-- Master dark: {master_dark}')
            return match
        else:
            print(f'{Fore.YELLOW}-- Could not find a suitable master dark.{Style.RESET_ALL}')
            return False


    def find_master_flat(self, image):
        ''' Selects a suitable calibrated master flat with matching 
            filter, bias, offset and CCD temperature

            :param image: single element from ImageSequence
            :return: single element from ImageSequence if found, False if not
        '''

        filter_code = image['header']['FILTER']
        temp = image['header']['CCD-TEMP']
        match = False

        for master in self.masters.files:
            if master['header']['FRAME'] == 'Flat':
                if abs(master['header']['CCD-TEMP'] - temp) <= cfg.TEMP_TOLERANCE:
                    if master['header']['FILTER'] == filter_code:
                        match = master
                        master_flat = master['filename']
                        break

        if match:
            print(f'-- Master flat: {master_flat}')
            return match
        else:
            print(f'{Fore.YELLOW}-- Could not find a suitable master flat.{Style.RESET_ALL}')
            return False


    def subtract_bias(self, image, bias=None, write=False):
        ''' Subtract provided master bias from FITS image. 
            If no master is provided, calls self.find_master_bias().
            Autodetects if 'image' and 'bias' are CCDData objects 
            and creates them if not.

            :param image: single element from ImageSequence or CCDData
            :param bias: single element from ImageSequence or CCDData
            :param write: boolean, set to True to write file
            :return: CCDData object if succesful, False if not
        '''

        filename = False

        if not bias:
            bias = self.find_master_bias(image)
            if not bias:
                print(f'{Style.BRIGHT + Fore.RED}No bias substraction.{Style.RESET_ALL}')
                return False

        image = hlp.extract_ccd(image)
        bias = hlp.extract_ccd(bias)

        print(f'{Style.BRIGHT + Fore.GREEN}Bias subtraction...{Style.RESET_ALL}')
        calibrated_image = ccdp.subtract_bias(image, bias)
        
        if write and filename:
            new_filename = f'b_{filename}'
            print(f'-- Writing {write_path/new_filename}...')
            calibrated_image.write(write_path / new_filename, overwrite=True)

        return calibrated_image

    
    def subtract_dark(self, image, dark=None, write=False):
        ''' Subtract provided calibrated master dark from FITS image. 
            If no master is provided, calls self.find_master_dark().
            Autodetects if 'image' and 'bias' are CCDData objects 
            and creates them if not.

            :param image: single element from ImageSequence or CCDData
            :param dark: single element from ImageSequence or CCDData
            :param write: boolean, set to True to write file
            :return: CCDData object if succesful, False if not
        '''

        filename = False

        if not dark:
            dark = self.find_master_dark(image)
            if not dark:
                print(f'{Style.BRIGHT + Fore.RED}No dark substraction.{Style.RESET_ALL}')
                return False

        image = hlp.extract_ccd(image)
        dark = hlp.extract_ccd(dark)

        print(f'{Style.BRIGHT + Fore.GREEN}Dark subtraction...{Style.RESET_ALL}')
        calibrated_image = ccdp.subtract_dark(image, dark, exposure_time='EXPTIME', exposure_unit=u.second, scale=True)

        if write and filename:
            new_filename = f'd_{filename}'
            print(f'-- Writing {write_path/new_filename}...')
            calibrated_image.write(write_path / new_filename, overwrite=True)

        return calibrated_image


    def correct_flat(self, image, flat=None, write=False):
        ''' Correct FITS image with provided master flat. 
            If no master is provided, calls self.find_master_flat().
            Autodetects if 'image' and 'bias' are CCDData objects 
            and creates them if not.

            :param image: single element from ImageSequence or CCDData
            :param flat: single element from ImageSequence or CCDData
            :param write: boolean, set to True to write file
            :return: CCDData object if succesful, False if not
        '''

        filename = False

        if not flat:
            flat = self.find_master_flat(image)
            if not flat:
                print(f'{Style.BRIGHT + Fore.RED}No flat correction.{Style.RESET_ALL}')
                return False

        image = hlp.extract_ccd(image)
        flat = hlp.extract_ccd(flat)

        print(f'{Style.BRIGHT + Fore.GREEN}Flat correction...{Style.RESET_ALL}')
        calibrated_image = ccdp.flat_correct(image, flat)

        if write and filename:
            new_filename = f'f_{filename}'
            print(f'-- Writing {write_path/new_filename}...')
            calibrated_image.write(write_path / new_filename, overwrite=True)

        return calibrated_image


    def calibrate_image(self, image, steps=None, bias=None, dark=None, flat=None, write=False):
        ''' Full calibration of FITS file. Options argument allows to chose
            what calibration steps to apply.
            If no master is provided, calls self.find_master_flat().
            Autodetects if 'image' and 'bias' are CCDData objects 
            and creates them if not.

            :param image: single element from ImageSequence or CCDData
            :param steps: python dict {bias, dark, flat: True/False}
            :param bias: single element from ImageSequence or CCDData
            :param dark: single element from ImageSequence or CCDData
            :param flat: single element from ImageSequence or CCDData
            :return: CCDData object if succesful, False if not
        '''

        if not steps:
            steps = {
                'bias': True,
                'dark': True,
                'flat': True,
            }
        
        new_filename = image['filename']
        calibrated_image = image

        filename = image['filename']
        ccd_temp = image['header']['ccd-temp']
        gain = image['header']['gain']
        offset = image['header']['offset']
        exptime = image['header']['exptime']
        filter_code = image['header']['filter']
        print(f'\n{Style.BRIGHT}Calibrating {filename}...{Style.RESET_ALL}')
        print(f'-- CCD_TEMP: {ccd_temp}')
        print(f'-- GAIN: {gain}')
        print(f'-- OFFSET: {offset}')
        print(f'-- EXPTIME: {exptime}')
        print(f'-- FILTER: {filter_code}')

        if steps['bias']:
            if not bias:           
                bias = self.find_master_bias(image)        
            if bias:
                calibrated_image = self.subtract_bias(calibrated_image, bias)
                new_filename = f'b_{new_filename}'
        
        if steps['dark']:
            if not dark:
                dark = self.find_master_dark(image)
            if dark:
                calibrated_image = self.subtract_dark(calibrated_image, dark)
                new_filename = f'd_{new_filename}'
        
        if steps['flat']:
            if not flat:
                flat = self.find_master_flat(image)
            if flat:
                calibrated_image = self.correct_flat(calibrated_image, flat)
                new_filename = f'f_{new_filename}'

        if write:    
            print(f'-- Writing {write_path/new_filename}...')
            calibrated_image.write(write_path / new_filename, overwrite=True)
        
        return (calibrated_image, new_filename)