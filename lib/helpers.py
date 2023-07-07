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


def header_summary(image):
    ''' Prints a summary of the values of the tested FITS header cards '''

    for card in cfg.TESTED_FITS_CARDS:
        card_name = card['name']
        value = image['header'][card_name]
        print(f'-- {card_name}: {value}')


def extract_ccd(image):
    ''' Returns CCDData of image in case it's an FITSSequence element '''

    if not isinstance(image, CCDData):
        return CCDData.read(image['path'], unit='adu')

    else:
        return image
