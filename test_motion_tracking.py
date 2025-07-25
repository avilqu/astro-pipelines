#!/usr/bin/env python3
"""
Test script for motion tracking integration functionality.

This script tests the motion tracking integration module with sample data
and verifies that the basic functionality works correctly.
"""

import sys
from pathlib import Path
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from lib.fits.integration import (
    integrate_with_motion_tracking,
    integrate_standard,
    calculate_motion_shifts,
    check_sequence_consistency,
    MotionTrackingIntegrationError
)


def create_test_fits_files(num_files=3, base_time="2025-01-15T10:00:00"):
    """
    Create test FITS files with simulated asteroid motion.
    
    Parameters:
    -----------
    num_files : int
        Number of test files to create
    base_time : str
        Base observation time
        
    Returns:
    --------
    List[str]
        List of created file paths
    """
    print(f"Creating {num_files} test FITS files...")
    
    # Create a simple WCS
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [256, 256]  # Reference pixel
    wcs.wcs.crval = [150.0, -30.0]  # Reference coordinates (RA, Dec)
    wcs.wcs.cdelt = [0.001, 0.001]  # Pixel scale (degrees/pixel)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    
    # Simulate asteroid motion (simple linear motion)
    # RA increases by 0.01 degrees per image, Dec increases by 0.005 degrees per image
    ra_motion = 0.01  # degrees per image
    dec_motion = 0.005  # degrees per image
    
    file_paths = []
    
    for i in range(num_files):
        # Create image data (simple Gaussian)
        data = np.random.normal(100, 10, (512, 512)).astype(np.float32)
        
        # Add a bright point source at the center
        y, x = np.ogrid[:512, :512]
        center_y, center_x = 256, 256
        sigma = 2.0
        gaussian = 1000 * np.exp(-((x - center_x)**2 + (y - center_y)**2) / (2 * sigma**2))
        data += gaussian
        
        # Create header with observation time
        header = fits.Header()
        header['NAXIS'] = 2
        header['NAXIS1'] = 512
        header['NAXIS2'] = 512
        header['BITPIX'] = -32
        header['DATE-OBS'] = (Time(base_time) + i * 300 * u.second).isot  # 5 min intervals
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
        file_path = f"test_asteroid_{i:03d}.fits"
        hdu = fits.PrimaryHDU(data, header)
        hdu.writeto(file_path, overwrite=True)
        file_paths.append(file_path)
        
        print(f"  Created {file_path}")
    
    return file_paths


def test_sequence_consistency():
    """Test sequence consistency checking."""
    print("\n=== Testing sequence consistency ===")
    
    # Create test files
    files = create_test_fits_files(3)
    
    try:
        # Test consistency check
        is_consistent = check_sequence_consistency(files)
        print(f"Sequence consistency: {is_consistent}")
        
        # Clean up
        for file_path in files:
            Path(file_path).unlink()
            
        return True
    except Exception as e:
        print(f"Error in sequence consistency test: {e}")
        return False


def test_motion_shifts():
    """Test motion shift calculation."""
    print("\n=== Testing motion shift calculation ===")
    
    # Create test files
    files = create_test_fits_files(3)
    
    try:
        # Test motion shift calculation
        shifts = calculate_motion_shifts(files, "2025 BC")
        print(f"Calculated {len(shifts)} shifts:")
        for i, (dx, dy) in enumerate(shifts):
            print(f"  Image {i}: dx={dx:.3f}, dy={dy:.3f}")
        
        # Clean up
        for file_path in files:
            Path(file_path).unlink()
            
        return True
    except Exception as e:
        print(f"Error in motion shift test: {e}")
        return False


def test_standard_integration():
    """Test standard integration."""
    print("\n=== Testing standard integration ===")
    
    # Create test files
    files = create_test_fits_files(3)
    
    try:
        # Test standard integration
        result = integrate_standard(
            files=files,
            method='average',
            sigma_clip=True,
            output_path='test_standard_stack.fits'
        )
        
        print(f"Standard integration successful")
        print(f"  Output shape: {result.data.shape}")
        print(f"  Data range: {result.data.min():.2f} to {result.data.max():.2f}")
        
        # Clean up
        for file_path in files:
            Path(file_path).unlink()
        Path('test_standard_stack.fits').unlink()
            
        return True
    except Exception as e:
        print(f"Error in standard integration test: {e}")
        return False


def test_motion_tracking_integration():
    """Test motion tracking integration."""
    print("\n=== Testing motion tracking integration ===")
    
    # Create test files
    files = create_test_fits_files(3)
    
    try:
        # Test motion tracking integration
        result = integrate_with_motion_tracking(
            files=files,
            object_name="2025 BC",
            method='average',
            sigma_clip=True,
            output_path='test_motion_tracked_stack.fits'
        )
        
        print(f"Motion tracking integration successful")
        print(f"  Output shape: {result.data.shape}")
        print(f"  Data range: {result.data.min():.2f} to {result.data.max():.2f}")
        print(f"  Motion tracked: {result.meta.get('MOTION_TRACKED', False)}")
        print(f"  Tracked object: {result.meta.get('TRACKED_OBJECT', 'None')}")
        
        # Clean up
        for file_path in files:
            Path(file_path).unlink()
        Path('test_motion_tracked_stack.fits').unlink()
            
        return True
    except Exception as e:
        print(f"Error in motion tracking integration test: {e}")
        return False


def main():
    """Run all tests."""
    print("Motion Tracking Integration Test Suite")
    print("=" * 50)
    
    tests = [
        ("Sequence Consistency", test_sequence_consistency),
        ("Motion Shifts", test_motion_shifts),
        ("Standard Integration", test_standard_integration),
        ("Motion Tracking Integration", test_motion_tracking_integration),
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
    print("Test Results Summary:")
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
        print("🎉 All tests passed! Motion tracking integration is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main()) 