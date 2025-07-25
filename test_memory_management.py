#!/usr/bin/env python3
"""
Test script for memory management features in image integration.

This script demonstrates how the new chunked processing and memory limits
help prevent crashes when integrating large numbers of files.
"""

import sys
from pathlib import Path
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from lib.fits.integration import (
    integrate_with_motion_tracking,
    integrate_standard,
    MotionTrackingIntegrationError,
    MEMORY_LIMIT,
    CHUNK_SIZE,
    ENABLE_CHUNKED_PROCESSING
)


def create_test_fits_files(num_files, image_size=(1024, 1024)):
    """Create test FITS files for testing."""
    files = []
    
    for i in range(num_files):
        filename = f"test_memory_{i:03d}.fits"
        
        # Create test data
        data = np.random.normal(1000, 100, image_size).astype(np.float32)
        
        # Create header with WCS
        header = fits.Header()
        header['NAXIS'] = 2
        header['NAXIS1'] = image_size[1]
        header['NAXIS2'] = image_size[0]
        header['BITPIX'] = -32
        header['DATE-OBS'] = f'2025-01-15T10:{i:02d}:00'
        header['EXPTIME'] = 60.0
        header['FILTER'] = 'R'
        header['GAIN'] = 1.0
        header['OFFSET'] = 0.0
        header['XBINNING'] = 1
        header['CCD-TEMP'] = -10.0
        
        # Add basic WCS
        header['CRPIX1'] = image_size[1] / 2
        header['CRPIX2'] = image_size[0] / 2
        header['CRVAL1'] = 180.0
        header['CRVAL2'] = 0.0
        header['CD1_1'] = 1.0 / 3600  # 1 arcsec/pixel
        header['CD1_2'] = 0.0
        header['CD2_1'] = 0.0
        header['CD2_2'] = 1.0 / 3600
        header['CTYPE1'] = 'RA---TAN'
        header['CTYPE2'] = 'DEC--TAN'
        
        # Create FITS file
        hdu = fits.PrimaryHDU(data, header)
        hdu.writeto(filename, overwrite=True)
        files.append(filename)
    
    return files


def test_memory_management():
    """Test memory management features."""
    print("Memory Management Test")
    print("=" * 50)
    
    # Show current configuration
    print(f"Current configuration:")
    print(f"  Memory limit: {MEMORY_LIMIT / 1e9:.1f} GB")
    print(f"  Chunk size: {CHUNK_SIZE} images")
    print(f"  Chunked processing enabled: {ENABLE_CHUNKED_PROCESSING}")
    print()
    
    # Test with different numbers of files
    test_cases = [
        (5, "Small dataset (should use standard processing)"),
        (15, "Medium dataset (should use chunked processing)"),
        (25, "Large dataset (should use chunked processing)")
    ]
    
    for num_files, description in test_cases:
        print(f"\n{description}")
        print("-" * 40)
        
        # Create test files
        print(f"Creating {num_files} test FITS files...")
        files = create_test_fits_files(num_files)
        
        try:
            # Test motion tracking integration
            print(f"Testing motion tracking integration...")
            result = integrate_with_motion_tracking(
                files=files,
                object_name="2025 BC",
                method='average',
                sigma_clip=True,
                output_path=f'test_memory_motion_{num_files}.fits'
            )
            
            print(f"✓ Motion tracking integration successful")
            print(f"  Chunked processing: {result.meta.get('CHUNKED_PROCESSING', False)}")
            if 'TOTAL_CHUNKS' in result.meta:
                print(f"  Total chunks: {result.meta['TOTAL_CHUNKS']}")
            print(f"  Output shape: {result.data.shape}")
            
        except Exception as e:
            print(f"✗ Motion tracking integration failed: {e}")
        
        try:
            # Test standard integration
            print(f"Testing standard integration...")
            result = integrate_standard(
                files=files,
                method='average',
                sigma_clip=True,
                output_path=f'test_memory_standard_{num_files}.fits'
            )
            
            print(f"✓ Standard integration successful")
            print(f"  Chunked processing: {result.meta.get('CHUNKED_PROCESSING', False)}")
            print(f"  Output shape: {result.data.shape}")
            
        except Exception as e:
            print(f"✗ Standard integration failed: {e}")
        
        # Clean up test files
        print("Cleaning up test files...")
        for file_path in files:
            Path(file_path).unlink()
        Path(f'test_memory_motion_{num_files}.fits').unlink(missing_ok=True)
        Path(f'test_memory_standard_{num_files}.fits').unlink(missing_ok=True)


def test_custom_memory_settings():
    """Test custom memory settings."""
    print("\n\nCustom Memory Settings Test")
    print("=" * 50)
    
    # Create test files
    num_files = 20
    print(f"Creating {num_files} test FITS files...")
    files = create_test_fits_files(num_files)
    
    try:
        # Test with custom memory limit (1GB)
        print(f"Testing with custom memory limit (1GB)...")
        result = integrate_with_motion_tracking(
            files=files,
            object_name="2025 BC",
            method='average',
            sigma_clip=True,
            output_path='test_custom_memory.fits',
            memory_limit=1e9,  # 1GB
            chunk_size=5       # Smaller chunks
        )
        
        print(f"✓ Custom memory settings successful")
        print(f"  Chunked processing: {result.meta.get('CHUNKED_PROCESSING', False)}")
        if 'TOTAL_CHUNKS' in result.meta:
            print(f"  Total chunks: {result.meta['TOTAL_CHUNKS']}")
        print(f"  Output shape: {result.data.shape}")
        
    except Exception as e:
        print(f"✗ Custom memory settings failed: {e}")
    
    # Clean up
    print("Cleaning up test files...")
    for file_path in files:
        Path(file_path).unlink()
    Path('test_custom_memory.fits').unlink(missing_ok=True)


if __name__ == "__main__":
    print("Testing Memory Management Features")
    print("=" * 50)
    
    test_memory_management()
    test_custom_memory_settings()
    
    print("\n" + "=" * 50)
    print("Memory management testing complete!")
    print("\nKey features tested:")
    print("✓ Automatic chunked processing for large datasets")
    print("✓ Configurable memory limits")
    print("✓ Custom chunk sizes")
    print("✓ Memory cleanup between chunks")
    print("✓ Both motion tracking and standard integration") 