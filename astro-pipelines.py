#!/usr/bin/env python

''' Main entry for astro-pipelines.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

import warnings
from astropy import wcs
warnings.filterwarnings("ignore", category=wcs.FITSFixedWarning)

import helpers as hlp

if __name__ == "__main__":

    import argparse

    from colorama import Fore, Back, Style

    from image_sequence import ImageSequence
    
    parser = argparse.ArgumentParser(description='Suite of various tools for astronomical images reduction. See /config.py before use.')
    parser.add_argument('files', help='input filename(s)', type=str, nargs='*')
    parser.add_argument('-M', '--masters', type=str, help='generate calibration masters from input files (arguments: "bias", "dark", "flat")')
    parser.add_argument('-C', '--calibrate', action='store_true', help='full image calibration on input files')
    parser.add_argument('-b', '--bias', action='store_true', help='subtract bias from input files')
    parser.add_argument('-d', '--dark', action='store_true', help='subtract dark from input files')
    parser.add_argument('-f', '--flat', action='store_true', help='flat correction on input files')
    parser.add_argument('-I', '--integrate', action='store_true', help='integrate input files')
    parser.add_argument('-c', '--config', action='store_true', help='print current config')
    args = parser.parse_args()

    print(f'{Style.BRIGHT}Loading calibration masters...{Style.RESET_ALL}')
    from calibration_library import CalibrationLibrary
    cal = CalibrationLibrary()

    if args.masters:
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
                  
    else:
        print(f'{Style.BRIGHT + Fore.RED}Wrong operation!{Style.RESET_ALL}')
        parser.print_help()

    # seq = ImageSequence(args.files)
    # cal.find_master_bias(seq.files[0])

    # seq.check_sequence_consistency()
    # mb = cal.generate_master_bias(seq)
    # seq.calibrate_sequence()