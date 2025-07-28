#!/usr/bin/env python3
"""
Comprehensive test script for source detection functions using the sample FITS file.
Tests different parameter combinations to show the effects of various settings.
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

def test_different_parameters():
    """Test source detection with different parameter combinations."""
    
    # Path to the sample FITS file
    fits_file = "sample/NGC_6337_L_300s_1x1_2025-07-20T22-53-16_001.fits"
    
    print(f"Comprehensive source detection test on: {fits_file}")
    print("=" * 80)
    
    # Check if file exists
    if not os.path.exists(fits_file):
        print(f"Error: File {fits_file} not found!")
        return
    
    # Define different parameter sets to test
    parameter_sets = [
        {
            'name': 'Conservative (High SNR)',
            'threshold_sigma': 5.0,
            'npixels': 20,
            'min_area': 50,
            'min_snr': 10.0,
            'deblend': False,
            'max_area': 1000
        },
        {
            'name': 'Moderate',
            'threshold_sigma': 3.0,
            'npixels': 10,
            'min_area': 20,
            'min_snr': 5.0,
            'deblend': False,
            'max_area': 500
        },
        {
            'name': 'Sensitive (Low SNR)',
            'threshold_sigma': 2.0,
            'npixels': 5,
            'min_area': 10,
            'min_snr': 3.0,
            'deblend': False,
            'max_area': 200
        }
    ]
    
    results = []
    
    for i, params in enumerate(parameter_sets):
        print(f"\n{'='*60}")
        print(f"Test {i+1}: {params['name']}")
        print(f"{'='*60}")
        print(f"Parameters: threshold_sigma={params['threshold_sigma']}, "
              f"npixels={params['npixels']}, min_area={params['min_area']}, "
              f"min_snr={params['min_snr']}")
        
        start_time = time.time()
        
        # Remove 'name' from params before passing to function
        test_params = {k: v for k, v in params.items() if k != 'name'}
        
        result = detect_sources_from_fits(
            fits_file,
            **test_params
        )
        
        elapsed_time = time.time() - start_time
        
        print(f"Detection completed in {elapsed_time:.2f} seconds")
        print(f"Result: {result}")
        
        if result.success:
            print(f"Number of sources detected: {len(result.sources)}")
            
            if len(result.sources) > 0:
                # Calculate some statistics
                fluxes = [s.flux for s in result.sources]
                snrs = [s.snr for s in result.sources]
                areas = [s.area for s in result.sources]
                
                print(f"Flux statistics: min={min(fluxes):.0f}, max={max(fluxes):.0f}, mean={np.mean(fluxes):.0f}")
                print(f"SNR statistics: min={min(snrs):.1f}, max={max(snrs):.1f}, mean={np.mean(snrs):.1f}")
                print(f"Area statistics: min={min(areas):.0f}, max={max(areas):.0f}, mean={np.mean(areas):.0f}")
                
                # Show first 5 sources
                print("\nFirst 5 sources:")
                for j, source in enumerate(result.sources[:5]):
                    print(f"  {source}")
                
                results.append({
                    'name': params['name'],
                    'params': params,
                    'result': result,
                    'elapsed_time': elapsed_time,
                    'n_sources': len(result.sources),
                    'fluxes': fluxes,
                    'snrs': snrs,
                    'areas': areas
                })
        else:
            print(f"Detection failed: {result.message}")
    
    # Summary comparison
    print(f"\n{'='*80}")
    print("SUMMARY COMPARISON")
    print(f"{'='*80}")
    
    if results:
        print(f"{'Test':<20} {'Sources':<10} {'Time (s)':<10} {'Mean SNR':<10} {'Mean Flux':<15}")
        print("-" * 70)
        
        for result_data in results:
            mean_snr = np.mean(result_data['snrs'])
            mean_flux = np.mean(result_data['fluxes'])
            print(f"{result_data['name']:<20} {result_data['n_sources']:<10} "
                  f"{result_data['elapsed_time']:<10.1f} {mean_snr:<10.1f} {mean_flux:<15.0f}")
    
    # Create comparison visualization
    if len(results) > 1:
        print(f"\n{'='*80}")
        print("Creating comparison visualization...")
        print(f"{'='*80}")
        
        try:
            fig, axes = plt.subplots(2, 2, figsize=(15, 12))
            
            # Plot 1: Number of sources vs test
            test_names = [r['name'] for r in results]
            n_sources = [r['n_sources'] for r in results]
            axes[0, 0].bar(test_names, n_sources, color=['blue', 'green', 'red'])
            axes[0, 0].set_title('Number of Sources Detected')
            axes[0, 0].set_ylabel('Number of Sources')
            axes[0, 0].tick_params(axis='x', rotation=45)
            
            # Plot 2: Processing time vs test
            times = [r['elapsed_time'] for r in results]
            axes[0, 1].bar(test_names, times, color=['blue', 'green', 'red'])
            axes[0, 1].set_title('Processing Time')
            axes[0, 1].set_ylabel('Time (seconds)')
            axes[0, 1].tick_params(axis='x', rotation=45)
            
            # Plot 3: SNR distribution
            for i, result_data in enumerate(results):
                axes[1, 0].hist(result_data['snrs'], bins=20, alpha=0.7, 
                               label=result_data['name'], density=True)
            axes[1, 0].set_title('SNR Distribution')
            axes[1, 0].set_xlabel('Signal-to-Noise Ratio')
            axes[1, 0].set_ylabel('Density')
            axes[1, 0].legend()
            
            # Plot 4: Flux distribution
            for i, result_data in enumerate(results):
                axes[1, 1].hist(np.log10(result_data['fluxes']), bins=20, alpha=0.7,
                               label=result_data['name'], density=True)
            axes[1, 1].set_title('Log Flux Distribution')
            axes[1, 1].set_xlabel('Log10(Flux)')
            axes[1, 1].set_ylabel('Density')
            axes[1, 1].legend()
            
            plt.tight_layout()
            plt.savefig('source_detection_comparison.png', dpi=150, bbox_inches='tight')
            print("Comparison visualization saved as 'source_detection_comparison.png'")
            
        except Exception as e:
            print(f"Visualization failed: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*80}")
    print("Comprehensive test completed!")
    print(f"{'='*80}")

if __name__ == "__main__":
    test_different_parameters() 