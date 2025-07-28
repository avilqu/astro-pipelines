#!/usr/bin/env python3
"""
Test script for the overlay toolbar functionality.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from PyQt6.QtWidgets import QApplication
from lib.gui.viewer.index import FITSViewer

def main():
    """Test the overlay toolbar functionality."""
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
    
    print("FITS Viewer with overlay toolbar started successfully!")
    print("Features to test:")
    print("1. Vertical toolbar on the left edge with overlay toggle buttons")
    print("2. Buttons should appear when overlays are available")
    print("3. Each overlay type can be toggled independently")
    print("4. Buttons use the same icons as the main toolbar")
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 