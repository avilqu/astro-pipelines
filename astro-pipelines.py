#!/usr/bin/env python

''' Main entry for astro-pipelines.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


if __name__ == "__main__":

    import argparse
    import sys
    from colorama import Fore, Back, Style
    import warnings

    # Silencing warning and info messages
    from astropy import wcs
    from astropy.utils.exceptions import AstropyUserWarning
    warnings.filterwarnings("ignore", category=wcs.FITSFixedWarning)
    warnings.filterwarnings('ignore', category=AstropyUserWarning)
    import logging, sys
    logging.disable(sys.maxsize)

    from lib.class_image_sequence import ImageSequence
    from lib.data_display import DataDisplay
    import lib.helpers as hlp
    import lib.astrometry

    
    parser = argparse.ArgumentParser(description='Suite of various tools for astronomical images reduction. See /config.py before use.')
    parser.add_argument('files', help='input filename(s)', type=str, nargs='*')
    parser.add_argument('-M', '--masters', type=str, help='generate calibration masters from input files (arguments: "bias", "dark", "flat")')
    parser.add_argument('-C', '--calibrate', action='store_true', help='full image calibration on input files')
    parser.add_argument('--bias', action='store_true', help='subtract bias from input files')
    parser.add_argument('--dark', action='store_true', help='subtract dark from input files')
    parser.add_argument('--flat', action='store_true', help='flat correction on input files')
    parser.add_argument('-R', '--register', type=str, help='register platesolved files using WCS reprojection method (reference filename as argument)')
    parser.add_argument('-I', '--integrate', action='store_true', help='integrate input files')
    parser.add_argument('--blink',action='store_true', help='blink input files (interval in seconds as argument)')
    parser.add_argument('--sso',type=int, help='overlay solar system object (mag limit as argument')
    parser.add_argument('--show',action='store_true', help='display FITS image')
    parser.add_argument('--find', type=str, help='query SIMBAD and overlays result on input image')
    parser.add_argument('--config', action='store_true', help='print current config')
    args = parser.parse_args()

    def load_calibration_masters():
        print(f'{Style.BRIGHT}Loading calibration masters...{Style.RESET_ALL}')
        from lib.class_calibration_library import CalibrationLibrary
        return CalibrationLibrary()
    
    def single_file_filter():
        if len(args.files) > 1:
            print(f'{Style.BRIGHT + Fore.RED}This option requires a single input file.{Style.RESET_ALL}')
            sys.exit()

    if args.masters:
        cal = load_calibration_masters()
        print(f'{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}')
        seq = ImageSequence(args.files)
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
        seq = ImageSequence(args.files)
        seq.check_sequence_consistency()

        print(f'\n{Style.BRIGHT}Subtracting bias from {len(seq.filenames)} files.{Style.RESET_ALL}')
        hlp.prompt()

        for image in seq.files:
            filename = image['filename']
            print(f'\n{Style.BRIGHT}Calibrating {filename}...{Style.RESET_ALL}')
            cal.subtract_bias(image, write=True)

    elif args.dark:
        cal = load_calibration_masters()
        print(f'{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}')
        seq = ImageSequence(args.files)
        seq.check_sequence_consistency()

        print(f'\n{Style.BRIGHT}Subtracting dark from {len(seq.filenames)} files.{Style.RESET_ALL}')
        hlp.prompt()

        for image in seq.files:
            filename = image['filename']
            print(f'\n{Style.BRIGHT}Calibrating {filename}...{Style.RESET_ALL}')
            cal.subtract_dark(image, write=True)

    elif args.flat:
        cal = load_calibration_masters()
        print(f'{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}')
        seq = ImageSequence(args.files)
        seq.check_sequence_consistency()

        print(f'\n{Style.BRIGHT}Flat correction for {len(seq.filenames)} files.{Style.RESET_ALL}')
        hlp.prompt()

        for image in seq.files:
            filename = image['filename']
            print(f'\n{Style.BRIGHT}Calibrating {filename}...{Style.RESET_ALL}')
            cal.correct_flat(image, write=True)

    elif args.calibrate:
        cal = load_calibration_masters()
        print(f'{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}')
        seq = ImageSequence(args.files)
        seq.check_sequence_consistency()

        print(f'\n{Style.BRIGHT}Full image calibration for {len(seq.filenames)} files.{Style.RESET_ALL}')
        hlp.prompt()

        for image in seq.files:
            filename = image['filename']
            cal.calibrate_image(image, write=True)

    elif args.config:
        hlp.print_config()

    elif args.register:
        seq = ImageSequence(args.files)
        seq.check_sequence_consistency()
        
        seq.register_sequence(args.register)

    elif args.integrate:
        seq = ImageSequence(args.files)
        seq.check_sequence_consistency()
        
        seq.integrate_sequence(write=True)

    elif args.blink:
        seq = ImageSequence(args.files)
        
        seq.blink_sequence(args.blink)

    elif args.sso:
        single_file_filter()

        seq = ImageSequence(args.files)

        lib.astrometry.overlay_sso(seq.files[0], args.sso)

    elif args.show:
        single_file_filter()
        
        seq = ImageSequence(args.files)

        dd = DataDisplay(seq.files[0])
        dd.show()

    elif args.find:
        single_file_filter()
        
        seq = ImageSequence(args.files)

        lib.astrometry.find_object(seq.files[0], args.find)

    elif len(args.files) > 1:
        seq = ImageSequence(args.files)
        seq.check_sequence_consistency()

    elif len(args.files) == 1:
        print('one file only')
                  
    else:
        print(f'{Style.BRIGHT + Fore.RED}Wrong operation!{Style.RESET_ALL}')
        parser.print_help()