''' Helper functions for the data reduction scripts.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


def header_correction(collection):
    ''' Applies a correction to the FITS header '''

    for hdu in collection.hdus(overwrite=True):
        hdu.header['bunit'] = 'adu'
        hdu.header['instrume'] = 'SBIG ST-402ME'
        hdu.header['telescop'] = 'RC8 200/1620 f/8.1'
        hdu.header['observer'] = 'Adrien Vilquin Barrajon'
        hdu.header.pop('radecsys', None)
        hdu.header['radesys'] = 'FK5'
