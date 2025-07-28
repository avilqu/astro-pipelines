#!/usr/bin/env python3
"""
Test script to verify that SIMBAD field overlay creates a button.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from PyQt6.QtWidgets import QApplication
from lib.gui.viewer.index import FITSViewer

def main():
    """Test that SIMBAD field overlay creates a button."""
    app = QApplication(sys.argv)
    
    # Create the viewer
    viewer = FITSViewer()
    
    # Load a sample FITS file if available
    sample_file = "sample/NGC_6337_L_300s_1x1_2025-07-20T22-53-16_001.fits"
    if os.path.exists(sample_file):
        print(f"Loading sample file: {sample_file}")
        viewer.open_and_add_file(sample_file)
    else:
        print("No sample file found, starting with empty viewer")
    
    # Show the viewer
    viewer.show()
    
    print("FITS Viewer started successfully!")
    print("Test steps:")
    print("1. Load a FITS file")
    print("2. Go to SIMBAD menu -> Find deep-sky objects in field")
    print("3. Verify that a SIMBAD button appears in the left toolbar")
    print("4. Verify that the button can be toggled on/off")
    print("5. Verify that the overlay is drawn correctly")
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 