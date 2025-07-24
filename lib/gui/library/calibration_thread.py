#!/usr/bin/env python3
"""
Calibration Thread
Handles calibration operations in a background thread for the GUI.
"""

import sys
import os
import io
from PyQt6.QtCore import QThread, pyqtSignal
from colorama import init, Fore, Style

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from lib.fits.calibration import CalibrationManager


class CalibrationThread(QThread):
    """Thread for performing calibration operations."""
    
    output = pyqtSignal(str)  # Emit calibration output
    finished = pyqtSignal(dict)  # Emit calibration result
    
    def __init__(self, fits_file_path: str):
        super().__init__()
        self.fits_file_path = fits_file_path
        self._running = True
    
    def run(self):
        """Run the calibration process."""
        try:
            # Initialize colorama for colored output
            init()
            
            # Capture stdout to emit to GUI
            old_stdout = sys.stdout
            string_io = io.StringIO()
            sys.stdout = string_io
            
            # Initialize calibration manager
            calib_manager = CalibrationManager()
            
            # Perform calibration
            result = calib_manager.calibrate_file_simple(self.fits_file_path)
            
            # Restore stdout
            sys.stdout = old_stdout
            
            # Emit captured output
            output_text = string_io.getvalue()
            if output_text:
                self.output.emit(output_text)
            
            # Emit result
            self.finished.emit(result)
            
        except Exception as e:
            # Restore stdout in case of error
            sys.stdout = old_stdout
            error_msg = f"{Style.BRIGHT + Fore.RED}Error during calibration: {e}{Style.RESET_ALL}\n"
            self.output.emit(error_msg)
            self.finished.emit({'error': str(e)})
    
    def stop(self):
        """Stop the thread."""
        self._running = False 