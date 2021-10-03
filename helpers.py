''' Helper functions for the data reduction scripts.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

import config as cfg


def prompt():
    ''' Displays a Continue? (Y/n) prompt '''
    if input('\nContinue? (Y/n) ') == 'n':
        exit()


def config_display():
    print(f'CCD name: {cfg.CCD_NAME}')
    print(f'CCD label: {cfg.CCD_LABEL}')
    print(f'Telescope: {cfg.TELESCOPE}')
    print(f'Calibration path: {cfg.CALIBRATION_PATH}')


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
