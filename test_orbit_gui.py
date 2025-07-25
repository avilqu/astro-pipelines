#!/usr/bin/env python3
"""
Test script for the Orbit details window with menu bar.
"""

import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from lib.gui.common.orbit_details import OrbitDataWindow


def main():
    app = QApplication(sys.argv)
    
    # Create mock data for testing
    object_name = "2025 BC"
    orbit_data = {
        'elements': {
            'epoch_iso': '2025-01-15T00:00:00',
            'a': 1.5,
            'e': 0.3,
            'i': 15.0,
            'arg_per': 45.0,
            'asc_node': 180.0,
            'M': 90.0,
            'P': 365.25,
            'q': 1.05,
            'Q': 1.95,
            'H': 18.5,
            'G': 0.15,
            'MOIDs': {'Earth': 0.1, 'Venus': 0.2, 'Mars': 0.3},
            'rms_residual': 0.5,
            'weighted_rms_residual': 0.4,
            'n_resids': 50,
            'U': 0.8
        }
    }
    
    predicted_positions = [
        {
            'Date': '2025-01-15 10:00:00',
            'RA': 142.563695,
            'Dec': 37.057749,
            'mag': 18.421,
            'motion_rate': 15.18,
            'motionPA': 224.5
        },
        {
            'Date': '2025-01-15 10:05:00',
            'RA': 142.545168,
            'Dec': 37.042631,
            'mag': 18.420,
            'motion_rate': 15.24,
            'motionPA': 224.6
        },
        {
            'Date': '2025-01-15 10:10:00',
            'RA': 142.526549,
            'Dec': 37.027478,
            'mag': 18.418,
            'motion_rate': 15.30,
            'motionPA': 224.7
        }
    ]
    
    # Create the orbit window
    window = OrbitDataWindow(object_name, orbit_data, predicted_positions)
    
    # Set up auto-close after 5 seconds for testing
    timer = QTimer()
    timer.timeout.connect(window.close)
    timer.start(5000)  # 5 seconds
    
    window.show()
    
    print("Orbit details window opened. It will close automatically in 5 seconds.")
    print("You can test the 'Actions' -> 'Stack on ephemeris' menu item.")
    
    return app.exec()


if __name__ == "__main__":
    sys.exit(main()) 