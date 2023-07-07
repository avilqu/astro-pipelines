#!/usr/bin/env python

''' Main entry for astro-pipelines.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


if __name__ == "__main__":

    import argparse
    import sys
    from colorama import Fore, Style
    import warnings
    import types

    from astropy import units as u
    from astropy.coordinates import SkyCoord

    # Silencing warning and info messages
    from astropy import wcs
    from astropy.utils.exceptions import AstropyUserWarning
    warnings.filterwarnings("ignore", category=wcs.FITSFixedWarning)
    warnings.filterwarnings('ignore', category=AstropyUserWarning)
    import logging
    logging.disable(sys.maxsize)

    from lib.class_fits_sequence import FITSSequence
    from lib.class_data_display import DataDisplay
    from lib.class_sources import Sources
    import lib.helpers as hlp
    import lib.astrometry
    import lib.solver
    import config

    parser = argparse.ArgumentParser(
        description='Suite of various tools for astronomical images reduction. See /config.py before use.')
    parser.add_argument('files', help='input filename(s)', type=str, nargs='*')
    parser.add_argument('-M', '--masters', type=str,
                        help='generate calibration masters from input files (arguments: "bias", "dark", "flat")')
    parser.add_argument('-C', '--calibrate', action='store_true',
                        help='full image calibration on input files')
    parser.add_argument('--bias', action='store_true',
                        help='subtract bias from input files')
    parser.add_argument('--dark', action='store_true',
                        help='subtract dark from input files')
    parser.add_argument('--flat', action='store_true',
                        help='flat correction on input files')
    parser.add_argument('-S', '--solve', action='store_true',
                        help='platesolve input files')
    parser.add_argument('-R', '--register', type=str,
                        help='register platesolved files using WCS reprojection method (reference filename as argument)')
    parser.add_argument('-I', '--integrate',
                        action='store_true', help='integrate input files')
    parser.add_argument('--blink', action='store_true',
                        help='blink input files (interval in seconds as argument)')
    parser.add_argument(
        '--sso', type=int, help='overlay solar system object (mag limit as argument)')
    parser.add_argument('--show', action='store_true',
                        help='display FITS image')
    parser.add_argument('--sources', action='store_true',
                        help='extract and show sources')
    parser.add_argument('--find', type=str,
                        help='query SIMBAD and overlays result on input image')
    parser.add_argument('--config', action='store_true',
                        help='print current config')
    args = parser.parse_args()

    def load_calibration_masters():
        print(f'{Style.BRIGHT}Loading calibration masters...{Style.RESET_ALL}')
        from lib.class_calibrator import Calibrator
        return Calibrator()

    def single_file_filter():
        if len(args.files) > 1:
            print(
                f'{Style.BRIGHT + Fore.RED}This option requires a single input file.{Style.RESET_ALL}')
            sys.exit()

    if args.masters:
        cal = load_calibration_masters()
        print(f'{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}')
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        if args.masters == 'bias':
            cal.generate_master_bias(seq)
        elif args.masters == 'dark':
            cal.generate_master_dark(seq)
        elif args.masters == 'flat':
            cal.generate_master_flat(seq)
        else:
            print(f'{Style.BRIGHT + Fore.RED}Wrong operation!{Style.RESET_ALL}')
            parser.print_help()

    elif args.bias:
        cal = load_calibration_masters()
        print(f'{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}')
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        print(
            f'\n{Style.BRIGHT}Subtracting bias from {len(seq.filenames)} files.{Style.RESET_ALL}')
        hlp.prompt()

        for image in seq.files:
            filename = image['filename']
            print(f'\n{Style.BRIGHT}Calibrating {filename}...{Style.RESET_ALL}')
            cal.subtract_bias(image, write=True)

    elif args.dark:
        cal = load_calibration_masters()
        print(f'{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}')
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        print(
            f'\n{Style.BRIGHT}Subtracting dark from {len(seq.filenames)} files.{Style.RESET_ALL}')
        hlp.prompt()

        for image in seq.files:
            filename = image['filename']
            print(f'\n{Style.BRIGHT}Calibrating {filename}...{Style.RESET_ALL}')
            cal.subtract_dark(image, write=True)

    elif args.flat:
        cal = load_calibration_masters()
        print(f'{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}')
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        print(
            f'\n{Style.BRIGHT}Flat correction for {len(seq.filenames)} files.{Style.RESET_ALL}')
        hlp.prompt()

        for image in seq.files:
            filename = image['filename']
            print(f'\n{Style.BRIGHT}Calibrating {filename}...{Style.RESET_ALL}')
            cal.correct_flat(image, write=True)

    elif args.calibrate:
        cal = load_calibration_masters()
        print(f'{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}')
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        print(
            f'\n{Style.BRIGHT}Full image calibration for {len(seq.filenames)} files.{Style.RESET_ALL}')
        hlp.prompt()

        for image in seq.files:
            filename = image['filename']
            cal.calibrate_image(image, write=True)

    elif args.solve:
        seq = FITSSequence(args.files)
        solver_options = types.SimpleNamespace()
        solver_options.blind = False
        solver_options.radius = config.SOLVER_SEARCH_RADIUS
        solver_options.downsample = config.SOLVER_DOWNSAMPLE
        solver_options.files = seq.filenames

        print(f'{Style.BRIGHT}Platesolving {len(seq.files)} files.{Style.RESET_ALL}')
        try:
            solver_options.ra = seq.files[0]['header']['ra']
            solver_options.dec = seq.files[0]['header']['dec']
            print(
                f'{Style.BRIGHT + Fore.GREEN}Found WCS in file, using as target.{Style.RESET_ALL}')
        except Exception:
            print(f'{Style.BRIGHT + Fore.RED}No WCS found.{Style.RESET_ALL}')
            solver_blind = True

        if not solver_options.blind:
            c = SkyCoord(solver_options.ra * u.degree,
                         solver_options.dec * u.degree)
            print(f'\nTarget RA / DEC: {c.to_string("hmsdms")}')
            print(f'Search radius (degrees): {str(solver_options.radius)}')
            hlp.prompt()
            lib.solver.solve_offline(solver_options)

        else:
            print(f'{Style.BRIGHT + Fore.RED}Blind solving.{Style.RESET_ALL}')
            hlp.prompt()
            lib.solver.solve_offline({
                'downsample': config.SOLVER_DOWNSAMPLE,
                'ra': 0,
                'dec': 0,
                'radius': 360
            })

    elif args.register:
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        seq.register_sequence(args.register)

    elif args.integrate:
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        seq.integrate_sequence(write=True)

    elif args.blink:
        seq = FITSSequence(args.files)

        seq.blink_sequence(args.blink)

    elif args.sso:
        single_file_filter()

        seq = FITSSequence(args.files)

        lib.astrometry.overlay_sso(seq.files[0], args.sso)

    elif args.show:
        single_file_filter()

        seq = FITSSequence(args.files)

        dd = DataDisplay(seq.files[0])
        dd.show()

    elif args.find:
        single_file_filter()

        seq = FITSSequence(args.files)

        lib.astrometry.find_object(seq.files[0], args.find)

    elif args.sources:
        single_file_filter()

        seq = FITSSequence(args.files)

        sources = Sources(seq.files[0])
        sources.show_sources()

    elif len(args.files) > 1:
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

    elif len(args.files) == 1:
        print('one file only')

    else:
        print(f'{Style.BRIGHT + Fore.RED}Wrong operation!{Style.RESET_ALL}')
        parser.print_help()
