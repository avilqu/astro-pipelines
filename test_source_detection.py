#!/usr/bin/env python3
"""
Test script for source detection functions using the sample FITS file.
"""

import sys
import os
import numpy as np
import matplotlib.pyplot as plt
from astropy.io import fits
from astropy.wcs import WCS
import time

# Add the lib directory to the path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))

from sci.sources import detect_sources_from_fits, detect_sources_in_image, aperture_photometry_sources

def test_source_detection():
    """Test source detection on the sample FITS file."""
    
    # Path to the sample FITS file
    fits_file = "sample/NGC_6337_L_300s_1x1_2025-07-20T22-53-16_001.fits"
    
    print(f"Testing source detection on: {fits_file}")
    print("=" * 60)
    
    # Check if file exists
    if not os.path.exists(fits_file):
        print(f"Error: File {fits_file} not found!")
        return
    
    # First, let's examine the FITS file
    print("Examining FITS file...")
    with fits.open(fits_file) as hdul:
        print(f"Number of extensions: {len(hdul)}")
        for i, hdu in enumerate(hdul):
            print(f"Extension {i}: {hdu.name} - Shape: {hdu.data.shape if hdu.data is not None else 'No data'}")
        
        # Get the primary data
        data = hdul[0].data
        header = hdul[0].header
        
        print(f"Image shape: {data.shape}")
        print(f"Data type: {data.dtype}")
        print(f"Data range: {np.min(data):.2f} to {np.max(data):.2f}")
        print(f"Data mean: {np.mean(data):.2f}")
        print(f"Data std: {np.std(data):.2f}")
        
        # Try to extract WCS
        try:
            wcs = WCS(header)
            print(f"WCS available: {wcs}")
        except Exception as e:
            print(f"WCS not available: {e}")
            wcs = None
    
    print("\n" + "=" * 60)
    print("Running source detection...")
    print("=" * 60)
    
    # Test 1: Basic source detection
    print("\nTest 1: Basic source detection")
    start_time = time.time()
    
    result = detect_sources_from_fits(
        fits_file,
        threshold_sigma=2.0,
        npixels=5,
        min_area=10,
        min_snr=3.0
    )
    
    elapsed_time = time.time() - start_time
    print(f"Detection completed in {elapsed_time:.2f} seconds")
    print(f"Result: {result}")
    
    if result.success:
        print(f"Number of sources detected: {len(result.sources)}")
        
        if len(result.sources) > 0:
            print("\nFirst 10 sources:")
            for i, source in enumerate(result.sources[:10]):
                print(f"  {source}")
            
            # Test 2: Aperture photometry
            print("\n" + "=" * 60)
            print("Test 2: Aperture photometry")
            print("=" * 60)
            
            photometry_results = aperture_photometry_sources(
                data, 
                result.sources,
                aperture_radius=3.0,
                background_annulus=(5.0, 8.0)
            )
            
            print(f"Aperture photometry completed for {len(photometry_results)} sources")
            
            if len(photometry_results) > 0:
                print("\nFirst 5 photometry results:")
                for i, phot in enumerate(photometry_results[:5]):
                    print(f"  Source {phot['source_id']}: "
                          f"Flux={phot['background_subtracted_sum']:.2f} ± {phot['flux_error']:.2f}, "
                          f"SNR={phot['snr']:.2f}")
            
            # Test 3: Visualization
            print("\n" + "=" * 60)
            print("Test 3: Creating visualization")
            print("=" * 60)
            
            try:
                # Create a simple visualization
                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
                
                # Original image
                im1 = ax1.imshow(data, cmap='viridis', origin='lower')
                ax1.set_title('Original Image')
                ax1.set_xlabel('X (pixels)')
                ax1.set_ylabel('Y (pixels)')
                plt.colorbar(im1, ax=ax1)
                
                # Image with detected sources overlaid
                im2 = ax2.imshow(data, cmap='viridis', origin='lower')
                ax2.set_title(f'Detected Sources ({len(result.sources)})')
                ax2.set_xlabel('X (pixels)')
                ax2.set_ylabel('Y (pixels)')
                plt.colorbar(im2, ax=ax2)
                
                # Plot source positions
                if len(result.sources) > 0:
                    x_coords = [s.x for s in result.sources]
                    y_coords = [s.y for s in result.sources]
                    ax2.scatter(x_coords, y_coords, c='red', s=20, alpha=0.7, marker='+')
                
                plt.tight_layout()
                plt.savefig('source_detection_test.png', dpi=150, bbox_inches='tight')
                print("Visualization saved as 'source_detection_test.png'")
                
            except Exception as e:
                print(f"Visualization failed: {e}")
    
    else:
        print(f"Source detection failed: {result.message}")
    
    print("\n" + "=" * 60)
    print("Test completed!")

if __name__ == "__main__":
    test_source_detection() 