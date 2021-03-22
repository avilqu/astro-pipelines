#!/opt/anaconda/bin/python

''' Blink WCS matched FITS frames.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

# from astropy.coordinates import SkyCoord
# from astropy.time import Time
# import astropy.units as u
# from astroquery.imcce import Skybot
import pyds9
import ccdproc as ccdp


# def query_skybot(img):
#     field = SkyCoord(img.header['ra']*u.deg, img.header['dec']*u.deg)
#     epoch = Time(img.header['date-obs'])
#     objects = Skybot.cone_search(field, 15*u.arcmin, epoch)
#     return objects


# def display_image(img):
#     d = ds9.init_ds9()


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description='Blink WCS matched FITS frames.')
    parser.add_argument(
        'files', help='input files (FITS only)', type=str, nargs='+')
    parser.add_argument('-i', '--interval',
                        type=float, help='interval (seconds, default=0.5)', default=0.5)
    parser.add_argument('-y', '--noconfirm',
                        action='store_true', help='skip confirmation')
    args = parser.parse_args()

    images = ccdp.ImageFileCollection(filenames=args.files)
    print('\nImages to blink:')
    print(images.summary['object', 'date-obs', 'frame',
                         'instrume', 'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])

    if not args.noconfirm:
        if input('\nContinue? (Y/n) ') == 'n':
            exit()

    work_pwd = './' + args.files[0][0:args.files[0].find('/')] + '/'
    d = pyds9.DS9()

    for img, fname in images.ccds(return_fname=True):
        # query_skybot(img).pprint()
        d.set('file new ' + work_pwd + fname)
        d.set('zoom to fit')
        d.set('scale zscale')

    d.set('frame move first')
    d.set('frame delete')
    d.set('frame match wcs')
    d.set('blink yes')
    d.set('blink interval ' + str(args.interval))
