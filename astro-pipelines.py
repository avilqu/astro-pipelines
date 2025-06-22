#!/home/tan/dev/astro-pipelines/.venv/bin/python

"""Main entry for astro-pipelines.
@author: Adrien Vilquin Barrajon <avilqu@gmail.com>
"""


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
    warnings.filterwarnings("ignore", category=AstropyUserWarning)
    import logging

    logging.disable(sys.maxsize)

    from lib.class_fits_sequence import FITSSequence
    import lib.helpers as hlp
    import lib.solver
    import config

    parser = argparse.ArgumentParser(
        description="Suite of various tools for astronomical images reduction. See /config.py before use."
    )
    parser.add_argument("files", help="input filename(s)", type=str, nargs="*")
    parser.add_argument(
        "-M",
        "--masters",
        type=str,
        help='generate calibration masters from input files (arguments: "bias", "dark", "flat")',
    )
    parser.add_argument(
        "-C",
        "--calibrate",
        action="store_true",
        help="full image calibration on input files",
    )
    parser.add_argument(
        "--bias", action="store_true", help="subtract bias from input files"
    )
    parser.add_argument(
        "--dark", action="store_true", help="subtract dark from input files"
    )
    parser.add_argument(
        "--flat", action="store_true", help="flat correction on input files"
    )
    parser.add_argument(
        "-S", "--solve", action="store_true", help="platesolve input files"
    )
    parser.add_argument(
        "-R",
        "--register",
        type=str,
        help="register platesolved files using WCS reprojection method (reference filename as argument)",
    )
    parser.add_argument(
        "-I", "--integrate", action="store_true", help="integrate input files"
    )
    parser.add_argument(
        "--config", action="store_true", help="print current config"
    )
    parser.add_argument(
        "-G", "--gui", nargs="?", const="", metavar="FITS_FILE",
        help="open GUI viewer (optionally with a FITS file to load)"
    )
    args = parser.parse_args()

    def load_calibration_masters():
        print(f"{Style.BRIGHT}Loading calibration masters...{Style.RESET_ALL}")
        from lib.class_calibrator import Calibrator

        return Calibrator()

    def single_file_filter():
        if len(args.files) > 1:
            print(
                f"{Style.BRIGHT + Fore.RED}This option requires a single input file.{Style.RESET_ALL}"
            )
            sys.exit()

    def launch_gui():
        """Launch the PyQt6 GUI viewer"""
        try:
            from PyQt6.QtWidgets import QApplication
            from lib.gui_pyqt import FITSImageViewer
            
            app = QApplication(sys.argv)
            window = FITSImageViewer()
            window.show()
            
            # Load file if provided
            if args.gui and args.gui.strip():
                window.load_file_from_path(args.gui.strip())
            
            sys.exit(app.exec())
        except ImportError as e:
            print(f"{Style.BRIGHT + Fore.RED}Error: PyQt6 is required for GUI functionality.{Style.RESET_ALL}")
            print(f"Install with: pip install PyQt6")
            sys.exit(1)
        except Exception as e:
            print(f"{Style.BRIGHT + Fore.RED}Error launching GUI: {e}{Style.RESET_ALL}")
            sys.exit(1)

    if args.gui is not None:
        launch_gui()

    elif args.masters:
        cal = load_calibration_masters()
        print(f"{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}")
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        if args.masters == "bias":
            cal.generate_master_bias(seq)
        elif args.masters == "dark":
            cal.generate_master_dark(seq)
        elif args.masters == "flat":
            cal.generate_master_flat(seq)
        else:
            print(
                f"{Style.BRIGHT + Fore.RED}Wrong operation!{Style.RESET_ALL}"
            )
            parser.print_help()

    elif args.bias:
        cal = load_calibration_masters()
        print(f"{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}")
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        print(
            f"\n{Style.BRIGHT}Subtracting bias from {len(seq.filenames)} files.{Style.RESET_ALL}"
        )
        hlp.prompt()

        for image in seq.files:
            filename = image["filename"]
            print(
                f"\n{Style.BRIGHT}Calibrating {filename}...{Style.RESET_ALL}"
            )
            cal.subtract_bias(image, write=True)

    elif args.dark:
        cal = load_calibration_masters()
        print(f"{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}")
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        print(
            f"\n{Style.BRIGHT}Subtracting dark from {len(seq.filenames)} files.{Style.RESET_ALL}"
        )
        hlp.prompt()

        for image in seq.files:
            filename = image["filename"]
            print(
                f"\n{Style.BRIGHT}Calibrating {filename}...{Style.RESET_ALL}"
            )
            cal.subtract_dark(image, write=True)

    elif args.flat:
        cal = load_calibration_masters()
        print(f"{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}")
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        print(
            f"\n{Style.BRIGHT}Flat correction for {len(seq.filenames)} files.{Style.RESET_ALL}"
        )
        hlp.prompt()

        for image in seq.files:
            filename = image["filename"]
            print(
                f"\n{Style.BRIGHT}Calibrating {filename}...{Style.RESET_ALL}"
            )
            cal.correct_flat(image, write=True)

    elif args.calibrate:
        cal = load_calibration_masters()
        print(f"{Style.BRIGHT}Loading FITS sequence...{Style.RESET_ALL}")
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        print(
            f"\n{Style.BRIGHT}Full image calibration for {len(seq.filenames)} files.{Style.RESET_ALL}"
        )
        hlp.prompt()

        for image in seq.files:
            filename = image["filename"]
            cal.calibrate_image(image, write=True)

    elif args.solve:
        seq = FITSSequence(args.files)
        solver_options = types.SimpleNamespace()
        solver_options.blind = False
        solver_options.radius = config.SOLVER_SEARCH_RADIUS
        solver_options.downsample = config.SOLVER_DOWNSAMPLE
        solver_options.files = seq.filenames

        print(
            f"{Style.BRIGHT}Platesolving {len(seq.files)} files.{Style.RESET_ALL}"
        )
        try:
            # Try WCS coordinates first (most accurate)
            header = seq.files[0]["header"]
            if "CRVAL1" in header and "CRVAL2" in header:
                solver_options.ra = header["CRVAL1"]
                solver_options.dec = header["CRVAL2"]
                print(
                    f"{Style.BRIGHT + Fore.GREEN}Found WCS coordinates in file, using as target.{Style.RESET_ALL}"
                )
                print(f'  CRVAL1 (RA): {solver_options.ra} degrees')
                print(f'  CRVAL2 (DEC): {solver_options.dec} degrees')
            # Fallback to simple RA/DEC keywords
            elif "ra" in header and "dec" in header:
                solver_options.ra = header["ra"]
                solver_options.dec = header["dec"]
                print(
                    f"{Style.BRIGHT + Fore.GREEN}Found RA/DEC in file, using as target.{Style.RESET_ALL}"
                )
            else:
                print(f"{Style.BRIGHT + Fore.RED}No WCS found.{Style.RESET_ALL}")
                solver_options.blind = True
        except Exception as e:
            print(f"{Style.BRIGHT + Fore.RED}Error reading coordinates: {e}{Style.RESET_ALL}")
            solver_options.blind = True

        if not solver_options.blind:
            c = SkyCoord(
                solver_options.ra * u.degree, solver_options.dec * u.degree
            )
            print(f'\nTarget RA / DEC: {c.to_string("hmsdms")}')
            print(f"Search radius (degrees): {str(solver_options.radius)}")
            hlp.prompt()
            lib.solver.solve_offline(solver_options)

        else:
            print(f"{Style.BRIGHT + Fore.RED}Blind solving.{Style.RESET_ALL}")
            hlp.prompt()
            lib.solver.solve_offline(
                {
                    "downsample": config.SOLVER_DOWNSAMPLE,
                    "ra": 0,
                    "dec": 0,
                    "radius": 360,
                }
            )

    elif args.register:
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        seq.register_sequence(args.register)

    elif args.integrate:
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

        seq.integrate_sequence(write=True)

    elif len(args.files) > 1:
        seq = FITSSequence(args.files)
        seq.check_sequence_consistency()

    elif len(args.files) == 1:
        print("one file only")

    else:
        print(f"{Style.BRIGHT + Fore.RED}Wrong operation!{Style.RESET_ALL}")
        parser.print_help()
