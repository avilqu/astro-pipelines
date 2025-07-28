#!/usr/bin/env python3
"""
Example script demonstrating source detection functionality.

This script shows how to use the source detection module to extract sources
from astronomical images using photutils.
"""

import numpy as np
import matplotlib.pyplot as plt
from astropy.io import fits
from astropy.wcs import WCS
import os

# Import our source detection module
from lib.sci.sources import (
    detect_sources_in_image,
    detect_sources_from_fits,
    aperture_photometry_sources,
    DetectedSource,
    SourceDetectionResult
)


def example_basic_detection():
    """Example of basic source detection from a FITS file."""
    print("=== Basic Source Detection Example ===")
    
    # Example FITS file path (you would replace this with your actual file)
    fits_file = "your_image.fits"
    
    if not os.path.exists(fits_file):
        print(f"FITS file {fits_file} not found. Please provide a valid FITS file path.")
        return
    
    # Detect sources with default parameters
    result = detect_sources_from_fits(fits_file)
    
    if result.success:
        print(f"Detection successful: {result.message}")
        print(f"Found {len(result.sources)} sources")
        
        # Print first few sources
        for i, source in enumerate(result.sources[:5]):
            print(f"  {source}")
        
        # Convert to dictionary format
        data_dict = result.to_dict()
        print(f"\nDetection threshold: {data_dict['detection_threshold']:.4f}")
        
    else:
        print(f"Detection failed: {result.message}")


def example_custom_parameters():
    """Example with custom detection parameters."""
    print("\n=== Custom Parameters Example ===")
    
    # Create a synthetic image for demonstration
    np.random.seed(42)
    image = np.random.normal(100, 10, (512, 512))
    
    # Add some synthetic sources
    sources_positions = [(100, 100), (200, 150), (300, 400), (450, 200)]
    for x, y in sources_positions:
        # Create a Gaussian source
        xx, yy = np.meshgrid(np.arange(512), np.arange(512))
        source = 1000 * np.exp(-((xx - x)**2 + (yy - y)**2) / (2 * 5**2))
        image += source
    
    # Detect sources with custom parameters
    result = detect_sources_in_image(
        image,
        threshold_sigma=2.5,  # Higher threshold for cleaner detection
        npixels=10,           # Require more connected pixels
        min_area=20,          # Minimum area in pixels
        min_snr=5.0,          # Higher SNR requirement
        deblend=True,         # Enable deblending
        background_box_size=25,
        background_filter_size=5
    )
    
    if result.success:
        print(f"Detection successful: {result.message}")
        print(f"Found {len(result.sources)} sources")
        
        # Print source details
        for source in result.sources:
            print(f"  {source}")
            print(f"    Area: {source.area:.1f} pixels")
            print(f"    Eccentricity: {source.eccentricity:.3f}")
            print(f"    Peak value: {source.peak_value:.1f}")
            print()
        
        # Perform aperture photometry
        photometry_results = aperture_photometry_sources(
            image, 
            result.sources,
            aperture_radius=5.0,
            background_annulus=(8.0, 12.0)
        )
        
        print("Aperture photometry results:")
        for phot in photometry_results:
            print(f"  Source {phot['source_id']}:")
            print(f"    Background-subtracted flux: {phot['background_subtracted_sum']:.2f}")
            print(f"    Flux error: {phot['flux_error']:.2f}")
            print(f"    SNR: {phot['snr']:.2f}")
            print()


def example_with_wcs():
    """Example showing WCS coordinate conversion."""
    print("\n=== WCS Coordinate Example ===")
    
    # Create a synthetic image with WCS
    np.random.seed(42)
    image = np.random.normal(100, 10, (256, 256))
    
    # Add a synthetic source
    x, y = 128, 128
    xx, yy = np.meshgrid(np.arange(256), np.arange(256))
    source = 2000 * np.exp(-((xx - x)**2 + (yy - y)**2) / (2 * 8**2))
    image += source
    
    # Create a simple WCS (example coordinates)
    from astropy.wcs import WCS
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [128, 128]  # Reference pixel
    wcs.wcs.crval = [180.0, 30.0]  # Reference coordinates (RA=180°, Dec=30°)
    wcs.wcs.cdelt = [-0.001, 0.001]  # Pixel scale (degrees per pixel)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    
    # Detect sources with WCS
    result = detect_sources_in_image(
        image,
        wcs=wcs,
        threshold_sigma=3.0,
        npixels=5,
        min_snr=3.0
    )
    
    if result.success:
        print(f"Detection successful: {result.message}")
        
        for source in result.sources:
            print(f"  {source}")
            if source.ra is not None and source.dec is not None:
                print(f"    Sky coordinates: RA={source.ra:.6f}°, Dec={source.dec:.6f}°")


def example_visualization():
    """Example showing how to visualize detection results."""
    print("\n=== Visualization Example ===")
    
    # Create a synthetic image
    np.random.seed(42)
    image = np.random.normal(100, 15, (256, 256))
    
    # Add multiple sources
    sources_positions = [(64, 64), (128, 128), (192, 64), (64, 192)]
    for x, y in sources_positions:
        xx, yy = np.meshgrid(np.arange(256), np.arange(256))
        source = 1500 * np.exp(-((xx - x)**2 + (yy - y)**2) / (2 * 6**2))
        image += source
    
    # Detect sources
    result = detect_sources_in_image(
        image,
        threshold_sigma=2.0,
        npixels=5,
        min_snr=3.0
    )
    
    if result.success and len(result.sources) > 0:
        # Create visualization
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        
        # Original image
        axes[0].imshow(image, cmap='viridis', origin='lower')
        axes[0].set_title('Original Image')
        axes[0].set_xlabel('X (pixels)')
        axes[0].set_ylabel('Y (pixels)')
        
        # Background
        if result.background is not None:
            axes[1].imshow(result.background, cmap='viridis', origin='lower')
            axes[1].set_title('Background')
            axes[1].set_xlabel('X (pixels)')
            axes[1].set_ylabel('Y (pixels)')
        
        # Segmentation map
        if result.segmentation_map is not None:
            axes[2].imshow(result.segmentation_map, cmap='tab10', origin='lower')
            axes[2].set_title('Segmentation Map')
            axes[2].set_xlabel('X (pixels)')
            axes[2].set_ylabel('Y (pixels)')
            
            # Overlay source positions
            for source in result.sources:
                axes[2].plot(source.x, source.y, 'rx', markersize=8, markeredgewidth=2)
        
        plt.tight_layout()
        plt.savefig('source_detection_example.png', dpi=150, bbox_inches='tight')
        print("Visualization saved as 'source_detection_example.png'")
        
        # Print source summary
        print(f"\nDetected {len(result.sources)} sources:")
        for source in result.sources:
            print(f"  Source {source.id}: ({source.x:.1f}, {source.y:.1f}) - SNR: {source.snr:.2f}")


if __name__ == "__main__":
    print("Source Detection Examples")
    print("=" * 50)
    
    # Run examples
    example_custom_parameters()
    example_with_wcs()
    example_visualization()
    
    print("\nNote: To run the basic detection example, provide a valid FITS file path.")
    print("You can modify the 'fits_file' variable in example_basic_detection().") 