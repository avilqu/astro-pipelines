#!/usr/bin/env python3
"""
Test script to verify that overlays are preserved when opening search dialogs.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from PyQt6.QtWidgets import QApplication
from lib.gui.viewer.index import FITSViewer

def main():
    """Test that overlays are preserved when opening search dialogs."""
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
    print("2. Perform a SIMBAD search to add an overlay")
    print("3. Open the Gaia search dialog (magnitude limit dialog)")
    print("4. Verify that the SIMBAD overlay and its button remain visible")
    print("5. Cancel the Gaia dialog")
    print("6. Verify that the SIMBAD overlay is still there")
    print("7. Perform a Gaia search")
    print("8. Verify that both SIMBAD and Gaia overlays are visible")
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 