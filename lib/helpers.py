''' Miscellaneous helpful functions for astro-pipelines.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

import inspect

from astropy.nddata import CCDData
from colorama import Fore, Back, Style

import config as cfg


def prompt():
    ''' Displays a Continue? (Y/n) prompt '''
   
    if input('-- Continue? (Y/n) ') == 'n':
        exit()


def extract_ccd(image):
    ''' Returns CCDData of image in case it's an FITSSequence element '''
    
    if not isinstance(image, CCDData):
        return CCDData.read(image['path'], unit='adu')

    else: return image


def print_config():
    ''' Prints all config constants '''

    print(f'{Style.BRIGHT + Fore.BLUE}Calibration path:{Style.RESET_ALL} {cfg.CALIBRATION_PATH}')
    print(f'{Style.BRIGHT + Fore.BLUE}Temperature tolerance:{Style.RESET_ALL} {cfg.TEMP_TOLERANCE}')
    print(f'{Style.BRIGHT + Fore.BLUE}Exposure tolerance:{Style.RESET_ALL} {cfg.EXP_TOLERANCE}')
    print(f'{Style.BRIGHT + Fore.BLUE}Pixel rejection sigma low:{Style.RESET_ALL} {cfg.SIGMA_LOW}')
    print(f'{Style.BRIGHT + Fore.BLUE}Pixel rejection sigma high:{Style.RESET_ALL} {cfg.SIGMA_HIGH}')
    print(f'{Style.BRIGHT + Fore.BLUE}Tested FITS header cards:{Style.RESET_ALL} {cfg.TESTED_FITS_CARDS}')
