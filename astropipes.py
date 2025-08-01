#!/home/tan/dev/astro-pipelines/.venv/bin/python

""" Main entry for astropipes.
    @author: A. Vilquin Barrajon <avilqu@gmail.com>
"""

import os
import sys

# --- ADD THIS BLOCK IMMEDIATELY AFTER THE ABOVE IMPORTS ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# ----------------------------------------------------------

# Initialize database
from lib.db import get_db_manager
import config
db_manager = get_db_manager(config.DATABASE_PATH)

VIEWER_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'lib/gui/viewer/index.py'))

if __name__ == "__main__":
    import argparse
    import sys
    from colorama import Fore, Style
    import warnings
    import logging
    import traceback

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
        "--scan", action="store_true", help="scan and import image FITS files into database"
    )
    parser.add_argument(
        "--scan-calibration", action="store_true", help="scan and import calibration master FITS files into database"
    )
    parser.add_argument(
        "--scan-all", action="store_true", help="scan and import both image and calibration FITS files into database"
    )
    parser.add_argument(
        "-S", "--solve", metavar="FITS_FILE", 
        help="solve a single FITS file using astrometry.net"
    )
    parser.add_argument(
        "-C", "--calibrate", metavar="FITS_FILE", 
        help="calibrate a single FITS file using master bias, dark, and flat"
    )
    parser.add_argument(
        "--get-obs", metavar="OBJECT_DESIGNATION", help="download and display MPC observations for the given asteroid designation"
    )
    parser.add_argument(
        "--get-neocp-obs", metavar="NEOCP_DESIGNATION", help="download and display NEOCP observations for the given object designation"
    )
    parser.add_argument(
        "--get-neocp-objects", action="store_true", help="get the current list of objects on the NEOCP"
    )
    
    args = parser.parse_args()

    def launch_gui():
        """Launch the PyQt6 GUI viewer"""
        try:
            from PyQt6.QtWidgets import QApplication
            from lib.gui.library.index import AstroLibraryGUI
            
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
            traceback.print_exc()
            sys.exit(1)
        except Exception as e:
            print(f"{Style.BRIGHT + Fore.RED}Error launching GUI: {e}{Style.RESET_ALL}")
            traceback.print_exc()
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

    def scan_calibration():
        """Scan and import calibration master FITS files into the database"""
        try:
            from lib.db import scan_calibration_masters
            import config
            print(f"{Style.BRIGHT + Fore.GREEN}Starting calibration master scan...{Style.RESET_ALL}")
            print(f"Scanning calibration directory: {config.CALIBRATION_PATH}")
            print(f"Database: {db_manager.db_path}")
            results = scan_calibration_masters()
            print(f"\n{Style.BRIGHT + Fore.GREEN}Calibration scan completed successfully!{Style.RESET_ALL}")
            print(f"Database updated with {results['files_imported']} new calibration master files")
        except ImportError as e:
            print(f"{Style.BRIGHT + Fore.RED}Error: Required modules not found.{Style.RESET_ALL}")
            print(f"Error details: {e}")
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"{Style.BRIGHT + Fore.RED}Error: {e}{Style.RESET_ALL}")
            sys.exit(1)
        except Exception as e:
            print(f"{Style.BRIGHT + Fore.RED}Error during calibration scan: {e}{Style.RESET_ALL}")
            sys.exit(1)

    def scan_all():
        """Scan and import both image and calibration master FITS files into the database"""
        print(f"{Style.BRIGHT + Fore.CYAN}Starting full scan (image + calibration)...{Style.RESET_ALL}")
        scan_library()
        print(f"\n{Style.BRIGHT + Fore.CYAN}Proceeding to calibration master scan...{Style.RESET_ALL}")
        scan_calibration()
        print(f"\n{Style.BRIGHT + Fore.CYAN}Full scan completed!{Style.RESET_ALL}")

    def solve_image():
        """Solve a single FITS image using astrometry.net"""
        try:
            from lib.sci.platesolving import solve_single_image
            import os
            import logging
            
            fits_file = args.solve
            
            # Check if file exists
            if not os.path.exists(fits_file):
                print(f"{Style.BRIGHT + Fore.RED}Error: File not found: {fits_file}{Style.RESET_ALL}")
                sys.exit(1)
            
            # Check if file has .fits extension
            if not fits_file.lower().endswith(('.fits', '.fit')):
                print(f"{Style.BRIGHT + Fore.RED}Error: File must be a FITS file (.fits or .fit extension){Style.RESET_ALL}")
                sys.exit(1)
            
            print(f"{Style.BRIGHT + Fore.BLUE}Starting platesolving for: {fits_file}{Style.RESET_ALL}")
            
            # Temporarily enable logging for platesolving
            logging.disable(logging.NOTSET)
            
            # Run the platesolving pipeline
            result = solve_single_image(
                fits_file_path=fits_file,
                solve_field_path="solve-field",
                output_dir="/tmp/astropipes/solved",
                timeout=300,
                apply_solution=True
            )
            
            # Disable logging again after platesolving
            logging.disable(sys.maxsize)
            
            # The solve_single_image function already handles console output
            # We just need to check the result for exit code
            if not result.success:
                sys.exit(1)
                
        except ImportError as e:
            print(f"{Style.BRIGHT + Fore.RED}Error: Required modules not found.{Style.RESET_ALL}")
            print(f"Error details: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"{Style.BRIGHT + Fore.RED}Error during platesolving: {e}{Style.RESET_ALL}")
            sys.exit(1)

    def calibrate_image():
        """Calibrate a single FITS image using master bias, dark, and flat"""
        try:
            from lib.fits.calibration import CalibrationManager
            import os
            
            fits_file = args.calibrate
            
            # Check if file exists
            if not os.path.exists(fits_file):
                print(f"{Style.BRIGHT + Fore.RED}Error: File not found: {fits_file}{Style.RESET_ALL}")
                sys.exit(1)
            
            # Check if file has .fits extension
            if not fits_file.lower().endswith(('.fits', '.fit')):
                print(f"{Style.BRIGHT + Fore.RED}Error: File must be a FITS file (.fits or .fit extension){Style.RESET_ALL}")
                sys.exit(1)
            
            print(f"{Style.BRIGHT + Fore.BLUE}Starting calibration for: {fits_file}{Style.RESET_ALL}")
            
            # Initialize calibration manager
            calib_manager = CalibrationManager()
            
            # Calibrate the file
            result = calib_manager.calibrate_file_simple(fits_file)
            
            if 'error' in result:
                print(f"{Style.BRIGHT + Fore.RED}Calibration failed: {result['error']}{Style.RESET_ALL}")
                sys.exit(1)
            
            if result['success']:
                print(f"\n{Style.BRIGHT + Fore.GREEN}Calibration completed successfully!{Style.RESET_ALL}")
                print(f"Original file: {result['original_path']}")
                print(f"Calibrated file: {result['calibrated_path']}")
                print(f"Filename: {result['filename']}")
                
        except ImportError as e:
            print(f"{Style.BRIGHT + Fore.RED}Error: Required modules not found.{Style.RESET_ALL}")
            print(f"Error details: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"{Style.BRIGHT + Fore.RED}Error during calibration: {e}{Style.RESET_ALL}")
            sys.exit(1)

    def get_observations():
        """Download and display MPC observations for a given asteroid designation using mpcq."""
        try:
            from lib.sci.orbit import get_asteroid_observations
            designation = args.get_obs
            print(f"{Style.BRIGHT + Fore.BLUE}Querying MPC observations for: {designation}{Style.RESET_ALL}")
            observations = get_asteroid_observations(designation)
            # Try to display as a table using pandas if possible
            try:
                import pandas as pd
                if hasattr(observations, 'to_pandas'):
                    df = observations.to_pandas()
                elif hasattr(observations, 'to_dataframe'):
                    df = observations.to_dataframe()
                else:
                    df = pd.DataFrame(observations)
                # Select only the specified columns
                columns_to_show = ['trksub', 'provid', 'stn', 'submission._id', 'ra', 'dec', 'mag']
                available_columns = [col for col in columns_to_show if col in df.columns]
                if available_columns:
                    df_filtered = df[available_columns]
                    print(df_filtered.to_string(index=False))
                else:
                    print(f"{Style.BRIGHT + Fore.YELLOW}None of the requested columns found. Available columns: {list(df.columns)}{Style.RESET_ALL}")
                    print(df.to_string(index=False))
            except Exception as e:
                print(f"{Style.BRIGHT + Fore.YELLOW}Could not display as table: {e}{Style.RESET_ALL}")
                print(observations)
        except ImportError as e:
            print(f"{Style.BRIGHT + Fore.RED}Error: mpcq library is required for this feature.{Style.RESET_ALL}")
            print(f"Install with: pip install mpcq")
            print(f"ImportError details: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"{Style.BRIGHT + Fore.RED}Error fetching observations: {e}{Style.RESET_ALL}")
            sys.exit(1)

    def get_neocp_observations():
        """Download and display NEOCP observations for a given object designation."""
        try:
            from lib.sci.orbit import get_neocp_observations
            designation = args.get_neocp_obs
            print(f"{Style.BRIGHT + Fore.BLUE}Querying NEOCP observations for: {designation}{Style.RESET_ALL}")
            observations = get_neocp_observations(designation)
            
            if not observations:
                print(f"{Fore.YELLOW}No observations found for {designation}{Style.RESET_ALL}")
                return
            
            print(f"{Style.BRIGHT}Found {len(observations)} observations:{Style.RESET_ALL}")
            print()
            
            # Display each observation line
            for i, obs in enumerate(observations, 1):
                print(f"{Fore.CYAN}{i:3d}.{Style.RESET_ALL} {obs}")
            
            print()
            print(f"{Style.BRIGHT}Total: {len(observations)} observations{Style.RESET_ALL}")
            
        except ImportError:
            print(f"{Fore.RED}Error: Could not import orbit module{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}Error fetching NEOCP observations: {e}{Style.RESET_ALL}")

    def get_neocp_objects():
        """Get and display the current list of objects on the NEOCP."""
        try:
            from lib.sci.orbit import get_neocp_objects
            print(f"{Style.BRIGHT + Fore.BLUE}Querying current NEOCP objects...{Style.RESET_ALL}")
            objects = get_neocp_objects()
            # Try to display as a table using pandas if possible
            try:
                import pandas as pd
                df = pd.DataFrame(objects)
                if not df.empty:
                    # Select key columns for NEOCP objects
                    columns_to_show = ['packed', 'priority', 'score', 'vmag', 'ra', 'dec', 'uncert', 'status', 'neocp']
                    available_columns = [col for col in columns_to_show if col in df.columns]
                    if available_columns:
                        df_filtered = df[available_columns]
                        print(df_filtered.to_string(index=False))
                    else:
                        print(f"{Style.BRIGHT + Fore.YELLOW}None of the requested columns found. Available columns: {list(df.columns)}{Style.RESET_ALL}")
                        print(df.to_string(index=False))
                else:
                    print(f"{Style.BRIGHT + Fore.YELLOW}No NEOCP objects found{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Style.BRIGHT + Fore.YELLOW}Could not display as table: {e}{Style.RESET_ALL}")
                print(objects)
        except ImportError as e:
            print(f"{Style.BRIGHT + Fore.RED}Error: requests library is required for this feature.{Style.RESET_ALL}")
            print(f"Install with: pip install requests")
            print(f"ImportError details: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"{Style.BRIGHT + Fore.RED}Error fetching NEOCP objects: {e}{Style.RESET_ALL}")
            sys.exit(1)

    # Handle arguments
    if args.gui is not None:
        launch_gui()
    elif args.config:
        show_config()
    elif args.scan:
        scan_library()
    elif args.scan_calibration:
        scan_calibration()
    elif args.scan_all:
        scan_all()
    elif args.solve:
        solve_image()
    elif args.calibrate:
        calibrate_image()
    elif args.get_obs:
        get_observations()
    elif args.get_neocp_obs:
        get_neocp_observations()
    elif args.get_neocp_objects:
        get_neocp_objects()
    else:
        # Default behavior: show help
        parser.print_help()