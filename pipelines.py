#!/opt/anaconda/bin/python

''' Main entry for pipelines.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

import warnings
from astropy.utils.exceptions import AstropyWarning

from calibration_master import CalibrationMaster
import helpers as hlp

warnings.filterwarnings('ignore', category=AstropyWarning, append=True)


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description='Suite of various tools for astronomical images reduction. See /config.py before use.')
    parser.add_argument(
        'files', help='input files (FITS only)', type=str, nargs='*')
    parser.add_argument(
        '-M', '--masters', type=str, help='list or generate calibration masters from input files ("list", "bias", "dark", "dark_c", "flat")')
    parser.add_argument(
        '-C', '--calibrate', type=str, help='calibrate file(s) with options ("full", "biasonly", "flatonly", "noflat")')
    args = parser.parse_args()

    cm = CalibrationMaster(args.files)

    if args.masters:
        if args.masters == 'list':
            cm.print_calibration_masters()
        else:
            cm.generate_calibration_master(args.masters)

    if args.calibrate:
        options = {}
        if args.calibrate == 'biasonly':
            options = {'biasonly': True}
        elif args.calibrate == 'flatonly':
            options = {'flatonly': True}
        elif args.calibrate == 'noflat':
            options = {'noflat': True}
        cm.calibrate(options)

    # hlp.collection_summary(
    #     cm.masters, ['frame', 'filter', 'ccd-temp', 'exp-time', 'gain', 'offset'])
    # print(cm.browse_raws())
