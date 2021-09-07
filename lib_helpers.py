''' Helper functions for the data reduction scripts.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

import config as cfg


def header_correction(collection):
    ''' Applies a correction to the FITS header '''

    for hdu in collection.hdus(overwrite=True):
        hdu.header['bunit'] = 'adu'
        hdu.header['instrume'] = cfg.CCD_NAME
        hdu.header['telescop'] = cfg.TELESCOPE
        hdu.header.pop('radecsys', None)
        hdu.header['radesys'] = 'FK5'
