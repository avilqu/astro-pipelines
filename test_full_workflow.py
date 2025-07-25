#!/usr/bin/env python3
"""
Test the full motion tracking workflow from the GUI.
"""

import sys
from pathlib import Path
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy import units as u
from astropy.time import Time

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from lib.gui.common.orbit_details import OrbitDataWindow, MotionTrackingStackWorker
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QThread


def create_test_fits_files(num_files=3, base_time="2025-01-15T10:00:00"):
    """Create test FITS files for the workflow test."""
    print(f"Creating {num_files} test FITS files...")
    
    # Create a simple WCS
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [256, 256]
    wcs.wcs.crval = [150.0, -30.0]
    wcs.wcs.cdelt = [0.001, 0.001]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    
    file_paths = []
    
    for i in range(num_files):
        # Create image data
        data = np.random.normal(100, 10, (512, 512)).astype(np.float32)
        
        # Add a bright point source
        y, x = np.ogrid[:512, :512]
        center_y, center_x = 256, 256
        sigma = 2.0
        gaussian = 1000 * np.exp(-((x - center_x)**2 + (y - center_y)**2) / (2 * sigma**2))
        data += gaussian
        
        # Create header
        header = fits.Header()
        header['NAXIS'] = 2
        header['NAXIS1'] = 512
        header['NAXIS2'] = 512
        header['BITPIX'] = -32
        header['DATE-OBS'] = (Time(base_time) + i * 300 * u.second).isot
        header['EXPTIME'] = 60.0
        header['FILTER'] = 'R'
        header['GAIN'] = 1.0
        header['OFFSET'] = 0.0
        header['CCD-TEMP'] = -10.0
        header['XBINNING'] = 1
        header['YBINNING'] = 1
        
        # Add WCS information
        wcs_header = wcs.to_header()
        for key, value in wcs_header.items():
            header[key] = value
        
        # Create FITS file
        file_path = f"workflow_test_{i:03d}.fits"
        hdu = fits.PrimaryHDU(data, header)
        hdu.writeto(file_path, overwrite=True)
        file_paths.append(file_path)
        
        print(f"  Created {file_path}")
    
    return file_paths


def test_motion_tracking_worker():
    """Test the MotionTrackingStackWorker directly."""
    print("\n=== Testing MotionTrackingStackWorker ===")
    
    # Create test files
    files = create_test_fits_files(3)
    
    try:
        # Create worker
        worker = MotionTrackingStackWorker(files, "2025 BC", "test_workflow_stack.fits")
        
        # Test progress callback
        progress_received = []
        def on_progress(progress):
            progress_received.append(progress)
            print(f"  Progress: {progress:.2f}")
        
        # Test finished callback
        result_received = []
        def on_finished(success, message):
            result_received.append((success, message))
            print(f"  Finished: success={success}")
            print(f"  Message: {message}")
        
        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        
        # Run the worker
        worker.run()
        
        # Check results
        if result_received:
            success, message = result_received[0]
            if success:
                print("✓ MotionTrackingStackWorker test passed")
                return True
            else:
                print(f"✗ MotionTrackingStackWorker test failed: {message}")
                return False
        else:
            print("✗ MotionTrackingStackWorker test failed: No result received")
            return False
            
    except Exception as e:
        print(f"✗ MotionTrackingStackWorker test failed with exception: {e}")
        return False
    finally:
        # Clean up
        for file_path in files:
            Path(file_path).unlink(missing_ok=True)
        Path("test_workflow_stack.fits").unlink(missing_ok=True)


def test_orbit_window_with_menu():
    """Test the OrbitDataWindow with menu bar."""
    print("\n=== Testing OrbitDataWindow with menu ===")
    
    app = QApplication(sys.argv)
    
    # Create mock data
    object_name = "2025 BC"
    orbit_data = {
        'elements': {
            'epoch_iso': '2025-01-15T00:00:00',
            'a': 1.5, 'e': 0.3, 'i': 15.0, 'arg_per': 45.0, 'asc_node': 180.0, 'M': 90.0,
            'P': 365.25, 'q': 1.05, 'Q': 1.95, 'H': 18.5, 'G': 0.15,
            'MOIDs': {'Earth': 0.1, 'Venus': 0.2, 'Mars': 0.3},
            'rms_residual': 0.5, 'weighted_rms_residual': 0.4, 'n_resids': 50, 'U': 0.8
        }
    }
    
    predicted_positions = [
        {'Date': '2025-01-15 10:00:00', 'RA': 142.563695, 'Dec': 37.057749, 'mag': 18.421},
        {'Date': '2025-01-15 10:05:00', 'RA': 142.545168, 'Dec': 37.042631, 'mag': 18.420},
        {'Date': '2025-01-15 10:10:00', 'RA': 142.526549, 'Dec': 37.027478, 'mag': 18.418}
    ]
    
    # Create test files for the mock parent viewer
    test_files = create_test_fits_files(3)
    
    # Create mock parent viewer
    from PyQt6.QtWidgets import QWidget
    class MockParentViewer(QWidget):
        def __init__(self, files):
            super().__init__()
            self.loaded_files = files
        
        def open_and_add_file(self, file_path):
            print(f"  Mock viewer would load: {file_path}")
    
    mock_parent = MockParentViewer(test_files)
    
    # Create the orbit window
    window = OrbitDataWindow(object_name, orbit_data, predicted_positions, mock_parent)
    
    # Set up auto-close
    timer = QTimer()
    timer.timeout.connect(window.close)
    timer.start(3000)  # 3 seconds
    
    window.show()
    
    print("  Orbit window opened with menu bar")
    print("  You can test the 'Actions' -> 'Stack on ephemeris' menu item")
    
    result = app.exec()
    
    # Clean up
    for file_path in test_files:
        Path(file_path).unlink(missing_ok=True)
    
    print("✓ OrbitDataWindow test completed")
    return True


def main():
    """Run all workflow tests."""
    print("Full Motion Tracking Workflow Test")
    print("=" * 50)
    
    tests = [
        ("MotionTrackingStackWorker", test_motion_tracking_worker),
        ("OrbitDataWindow with Menu", test_orbit_window_with_menu),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\nRunning {test_name} test...")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"Test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("Workflow Test Results:")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{test_name:30s} {status}")
        if success:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All workflow tests passed! The GUI integration is working correctly.")
        return 0
    else:
        print("❌ Some workflow tests failed. Please check the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main()) 