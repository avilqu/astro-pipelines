''' Tools for managing a sequence of FITS files.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

import sys
import os

from astropy.io import fits
from astropy.nddata import CCDData
from colorama import Fore, Back, Style

import config as cfg
import helpers as hlp
# from calibration_library import CalibrationLibrary

class ImageSequence:


    def __init__(self, data):
        if len(data) == 0:
            print(f'{Style.BRIGHT + Fore.RED}No input files!{Style.RESET_ALL}')
            sys.exit()
            
        self.files = []
        self.data = []
        self.filenames = []            

        for filename in data:
            self.files.append({
                'filename': os.path.basename(filename),
                'header': fits.getheader(filename, ext=0),
                'path': filename
                # 'data': fits.getdata(filename, ext=0),
                # 'ccd': CCDData.read(filename, unit='adu')
            })
            self.data.append(fits.getdata(filename, ext=0))
            self.filenames.append(filename)


    def check_array_consistency(self, array, name, tolerance = 0):
        ''' Checks how many distinct values in an array and issues a warning if more than 1 
        
            :param array: the array to check
            :param name: the header card name (eg: 'CCD-TEMP')
            :return: true if array is consistent
        '''
            
        values = []
        res = True

        for value in array:
            i = 0
            if len(values) == 0: values.append(value)
            if not value in values:
                values.append(value)

        if not tolerance:
            if len(values) > 1:
                res = False
                print(f'{Fore.YELLOW}-- There are multiple {name} values in the sequence: {Style.RESET_ALL}', values)
            else:
                print(f'{Fore.GREEN}-- {name} values are consistent: {Style.RESET_ALL}', values)

        else:
            average = sum(array, 0.0) / len(array)
            max_deviation = max(abs(el - average) for el in array)
            print(f'-- {name} average: ', round(average, 2))
            print(f'-- {name} max deviation: ', round(max_deviation, 2))
            if max_deviation < tolerance: 
                res = True
                print(f'{Fore.GREEN}-- {name} values are consistent.{Style.RESET_ALL}')
            else: 
                print(f'{Fore.YELLOW}-- There are multiple {name} values in the sequence: {Style.RESET_ALL}', values)

        return res


    def check_sequence_consistency(self):
        ''' Procedes to various checks over several header cards to
            test for the sanity of the FITS collection before integration 
        
            :return: true if no warnings
        '''

        tested_cards = cfg.TESTED_FITS_CARDS
        res = True
        
        print(f'\n{Style.BRIGHT}Checking FITS sequence consistency...{Style.RESET_ALL}')
        for card in tested_cards:
            for file in self.files:
                card['values'].append(file['header'][card['name']])
            if not self.check_array_consistency(card['values'], card['name'], card['tolerance']):
                res = False
                  
        if res:
            print(f'{Style.BRIGHT + Fore.GREEN}Consistent FITS sequence.{Style.RESET_ALL}')
        else:
            print(f'{Style.BRIGHT + Fore.RED}Inconsistent FITS sequence!{Style.RESET_ALL}')
            hlp.prompt()

        return res
