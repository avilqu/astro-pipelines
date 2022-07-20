''' Miscellaneous helpful functions for astro-pipelines.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

from colorama import Fore, Back, Style

import config as cfg


def prompt():
    ''' Displays a Continue? (Y/n) prompt '''
    if input('-- Continue? (Y/n) ') == 'n':
        exit()


def print_config():
    print(f'{Style.BRIGHT + Fore.BLUE}Root path:{Style.RESET_ALL} {cfg.ROOT_PATH}')
    print(f'{Style.BRIGHT + Fore.BLUE}Calibration path:{Style.RESET_ALL} {cfg.CALIBRATION_PATH}')
    print(f'{Style.BRIGHT + Fore.BLUE}Observer:{Style.RESET_ALL} {cfg.OBSERVER}')
    print(f'{Style.BRIGHT + Fore.BLUE}CCD name:{Style.RESET_ALL} {cfg.CCD_NAME}')
    print(f'{Style.BRIGHT + Fore.BLUE}Telescope:{Style.RESET_ALL} {cfg.TELESCOPE}')
    print(f'{Style.BRIGHT + Fore.BLUE}Temperature tolerance:{Style.RESET_ALL} {cfg.TEMP_TOLERANCE}')
    print(f'{Style.BRIGHT + Fore.BLUE}Exposure tolerance:{Style.RESET_ALL} {cfg.EXP_TOLERANCE}')
    print(f'{Style.BRIGHT + Fore.BLUE}Pixel rejection sigma low:{Style.RESET_ALL} {cfg.SIGMA_LOW}')
    print(f'{Style.BRIGHT + Fore.BLUE}Pixel rejection sigma high:{Style.RESET_ALL} {cfg.SIGMA_HIGH}')
    print(f'{Style.BRIGHT + Fore.BLUE}Tested FITS header cards:{Style.RESET_ALL} {cfg.TESTED_FITS_CARDS}')


def header_correction(collection):
    ''' Applies various corrections to the FITS header '''

    print('Applying header corrections...')
    for hdu in collection.hdus(overwrite=True):
        hdu.header['bunit'] = 'adu'
        hdu.header.pop('radecsys', None)
        hdu.header['radesys'] = 'FK5'


def collection_summary(collection, rows):
    ''' Displays a summary table of FITS collection '''

    for hdu in collection.hdus(overwrite=True):
        for row in rows:
            if not row in hdu.header:
                rows.remove(row)

    print(collection.summary[(rows)])