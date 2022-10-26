''' Methods for astrometry analysis and solar system object (SSO) data.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u
from astropy.nddata import CCDData
from astroquery.imcce import Skybot
import pyds9
import ccdproc as ccdp


def query_skybot(img):
    field = SkyCoord(img['header']['ra']*u.deg, img['header']['dec']*u.deg)
    epoch = Time(img['header']['date-obs'])
    objects = Skybot.cone_search(field, 15*u.arcmin, epoch)
    return objects

def overlay_sso(img):
    d = pyds9.DS9()
    filename = img['filename']
    d.set(f'file new {filename}')
    d.set('zoom to fit')
    d.set('scale zscale')

    objects = []
    try:
        for obj in query_skybot(img):
            objects.append({
                'name': obj['Name'],
                'mag': obj['V'],
                'type': obj['Type'],
                'geodist': obj['geodist'],
                'coord': SkyCoord(obj['RA'], obj['DEC'])
            })
        for obj in objects:
            # coord = img.wcs.world_to_pixel(obj['coord'])
            d.set('regions', f'circle({coord[0]},{coord[1]},15)')

        print(objects)
        d.set('regions', f'fk5; circle({obj["coord"]},15)')
    except:
        print('No solar system object found.')





# if __name__ == "__main__":

#     import argparse

#     parser = argparse.ArgumentParser(
#         description='Image analysis tool. Use with ds9.')
#     parser.add_argument(
#         'file', help='input files (FITS only)', type=str)
#     parser.add_argument('-a', '--all',
#                         action='store_true', help='runs all the below options')
#     parser.add_argument('-H', '--header',
#                         action='store_true', help='print a summary of the FITS header')
#     parser.add_argument('-W', '--wcs',
#                         action='store_true', help='finds and prints WCS data')
#     parser.add_argument('-A', '--astrometry',
#                         action='store_true', help='annotate solar system objects')
#     args = parser.parse_args()

#     img = CCDData.read(args.file)

#     d = pyds9.DS9()
#     d.set(f'file new {args.file}')
#     d.set('zoom to fit')
#     d.set('scale zscale')

#     if args.header or args.all:
#         print_header_summary(img, ['object', 'date-obs', 'frame',
#                              'instrume', 'filter', 'exptime', 'ccd-temp', 'gain', 'offset', 'naxis1', 'naxis2'])

#     if args.wcs or args.all:
#         print_wcs(img)

#     if args.astrometry or args.all:
#         objects = []
#         try:
#             for obj in query_skybot(img):
#                 objects.append({
#                     'name': obj['Name'],
#                     'mag': obj['V'],
#                     'type': obj['Type'],
#                     'geodist': obj['geodist'],
#                     'coord': SkyCoord(obj['RA'], obj['DEC'])
#                 })
#             for obj in objects:
#                 coord = img.wcs.world_to_pixel(obj['coord'])
#                 d.set('regions', f'circle({coord[0]},{coord[1]},15)')

#             print(objects)
#             d.set('regions', f'fk5; circle({obj["coord"]},15)')
#         except:
#             print('No solar system object found.')
