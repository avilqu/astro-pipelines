#!/home/tan/dev/astro-pipelines/.venv/bin/python

''' CLI for online and offline Astrometry.net engine.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

from colorama import Fore, Style

import ccdproc as ccdp
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS
from astropy.io import fits

import lib.helpers as hlp
import lib.solver as slv
import config as cfg

if __name__ == "__main__":

    import argparse

    apiKey = cfg.ASTROMETRY_KEY

    parser = argparse.ArgumentParser(
        description='Solves one or a serie of FITS file using a local Astrometry.net engine. Tries by default to guess settings from WCS of first file in serie.')
    parser.add_argument('files', help='input filename(s)', type=str, nargs='+')
    parser.add_argument(
        '-r', '--ra', help='estimated RA center (angle)', type=float, dest='ra')
    parser.add_argument(
        '-d', '--dec', help='estimated DEC center (angle)', type=float, dest='dec')
    parser.add_argument(
        '-R', '--radius', help='search radius around center (degrees, default=15 unless no RA or DEC: 360)', type=str, dest='radius', default=15)
    parser.add_argument(
        '-s', '--scale', help='estimated field scale (arcminutes, online solver only)', type=int, dest='scaleEst')
    parser.add_argument(
        '-e', '--error', help='estimated field scale error (percent, online solver only)', type=int, dest='scaleErr')
    parser.add_argument('-D', '--downsample',
                        help='downsampling amount', type=int)
    parser.add_argument('-b', '--blind',
                        action='store_true', help='blind solve')
    parser.add_argument('-y', '--noconfirm',
                        action='store_true', help='skip confirmation')
    parser.add_argument('-o', '--online', action='store_true',
                        help='use online solver (requires internet connection)')
    args = parser.parse_args()

    images = ccdp.ImageFileCollection(filenames=args.files)
    print(
        f'{Style.BRIGHT}Platesolving {len(images.files)} files.{Style.RESET_ALL}')

    if (not args.ra and not args.dec) and not args.blind:
        try:
            # Try to read the first file and extract WCS information
            hdu = fits.open(args.files[0])
            header = hdu[0].header
            hdu.close()
            
            # First try to get coordinates from simple ra/dec keywords
            if 'ra' in header and 'dec' in header:
                args.ra = header['ra']
                args.dec = header['dec']
                print(f'{Style.BRIGHT + Fore.GREEN}Found RA/DEC keywords in file, using as target.{Style.RESET_ALL}')
            # If not found, try to extract from WCS
            elif 'CRVAL1' in header and 'CRVAL2' in header:
                args.ra = header['CRVAL1']
                args.dec = header['CRVAL2']
                print(f'{Style.BRIGHT + Fore.GREEN}Found WCS coordinates in file, using as target.{Style.RESET_ALL}')
                print(f'  CRVAL1 (RA): {args.ra} degrees')
                print(f'  CRVAL2 (DEC): {args.dec} degrees')
            else:
                raise Exception("No coordinate information found")
                
        except Exception as e:
            print(f'{Style.BRIGHT + Fore.RED}No WCS found: {e}{Style.RESET_ALL}')
            args.blind = True

    if not args.blind:
        c = SkyCoord(args.ra * u.degree, args.dec * u.degree)
        print(f'\nTarget RA / DEC: {c.to_string("hmsdms")}')
        print(f'Search radius (degrees): {str(args.radius)}')
    else:
        print(
            f'{Style.BRIGHT + Fore.RED}Blind solving.{Style.RESET_ALL}')

    if not args.noconfirm:
        hlp.prompt()

    if args.online:
        slv.solve_online(args, apiKey)
    else:
        slv.solve_offline(args)
