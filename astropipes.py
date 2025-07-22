#!/home/tan/dev/astro-pipelines/.venv/bin/python

""" Main entry for astropipes.
    @author: A. Vilquin Barrajon <avilqu@gmail.com>
"""

# Initialize database
from lib.db import get_db_manager
db_manager = get_db_manager('astropipes.db')

if __name__ == "__main__":
    import argparse
    import sys
    from colorama import Fore, Style
    import warnings
    import logging

    # Silencing warning and info messages
    from astropy import wcs
    from astropy.utils.exceptions import AstropyUserWarning

    warnings.filterwarnings("ignore", category=wcs.FITSFixedWarning)
    warnings.filterwarnings("ignore", category=AstropyUserWarning)
    logging.disable(sys.maxsize)

    parser = argparse.ArgumentParser(
        description="Astronomical Image Processing and Library Management Tool"
    )
    parser.add_argument(
        "-G", "--gui", nargs="?", const="", metavar="FITS_FILE",
        help="open GUI viewer (optionally with a FITS file to load)"
    )
    parser.add_argument(
        "--config", action="store_true", help="print current config"
    )
    parser.add_argument(
        "--scan", action="store_true", help="scan and import FITS files into database"
    )
    
    args = parser.parse_args()

    def launch_gui():
        """Launch the PyQt6 GUI viewer"""
        try:
            from PyQt6.QtWidgets import QApplication
            from lib.gui.main import AstroLibraryGUI
            
            app = QApplication(sys.argv)
            window = AstroLibraryGUI()
            window.show()
            
            # TODO: Load file if provided (will be implemented later)
            # if args.gui and args.gui.strip():
            #     window.load_file_from_path(args.gui.strip())
            
            sys.exit(app.exec())
        except ImportError as e:
            print(f"{Style.BRIGHT + Fore.RED}Error: PyQt6 is required for GUI functionality.{Style.RESET_ALL}")
            print(f"Install with: pip install PyQt6")
            print(f"ImportError details: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"{Style.BRIGHT + Fore.RED}Error launching GUI: {e}{Style.RESET_ALL}")
            sys.exit(1)

    def show_config():
        """Display current configuration"""
        import config
        print(f"{Style.BRIGHT + Fore.BLUE}Config:{Style.RESET_ALL}")
        print(f"Calibration Path: {config.CALIBRATION_PATH}")
        print(f"Data Path: {config.DATA_PATH}")
        print(f"Obs Path: {config.OBS_PATH}")

    def scan_library():
        """Scan and import FITS files into the database"""
        try:
            from lib.db import scan_fits_library
            import config
            
            print(f"{Style.BRIGHT + Fore.GREEN}Starting FITS library scan...{Style.RESET_ALL}")
            print(f"Scanning directory: {config.DATA_PATH}")
            print(f"Database: {db_manager.db_path}")
            
            results = scan_fits_library()
            
            print(f"\n{Style.BRIGHT + Fore.GREEN}Scan completed successfully!{Style.RESET_ALL}")
            print(f"Database updated with {results['files_imported']} new files")
            
        except ImportError as e:
            print(f"{Style.BRIGHT + Fore.RED}Error: Required modules not found.{Style.RESET_ALL}")
            print(f"Error details: {e}")
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"{Style.BRIGHT + Fore.RED}Error: {e}{Style.RESET_ALL}")
            sys.exit(1)
        except Exception as e:
            print(f"{Style.BRIGHT + Fore.RED}Error during scan: {e}{Style.RESET_ALL}")
            sys.exit(1)

    # Handle arguments
    if args.gui is not None:
        launch_gui()
    elif args.config:
        show_config()
    elif args.scan:
        scan_library()
    else:
        # Default behavior: show help
        parser.print_help()