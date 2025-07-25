#!/usr/bin/env python3
"""
Motion tracking image integration script.

This script demonstrates how to integrate a stack of astronomical images
while keeping a moving object (like an asteroid) static using ephemeris information.

Usage:
    python motion_stack.py <object_name> <fits_files...> [options]

Example:
    python motion_stack.py "2025 BC" image1.fits image2.fits image3.fits --output stacked.fits
"""

import argparse
import sys
from pathlib import Path
from typing import List

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from lib.fits.integration import (
    integrate_with_motion_tracking,
    integrate_standard,
    MotionTrackingIntegrationError
)


def main():
    parser = argparse.ArgumentParser(
        description="Integrate astronomical images with motion tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "object_name",
        help="Name of the moving object (e.g., '2025 BC', 'C34UMY1')"
    )
    
    parser.add_argument(
        "fits_files",
        nargs="+",
        help="FITS files to integrate"
    )
    
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: motion_tracked_stack.fits)"
    )
    
    parser.add_argument(
        "--reference-time",
        help="Reference time for object position (ISO format, e.g., '2025-01-15T10:30:00')"
    )
    
    parser.add_argument(
        "--method",
        choices=["average", "median", "sum"],
        default="average",
        help="Integration method (default: average)"
    )
    
    parser.add_argument(
        "--no-sigma-clip",
        action="store_true",
        help="Disable sigma clipping"
    )
    
    parser.add_argument(
        "--standard",
        action="store_true",
        help="Use standard integration (no motion tracking)"
    )
    
    parser.add_argument(
        "--flat-scale",
        action="store_true",
        help="Apply flat field scaling (1/median)"
    )
    
    parser.add_argument(
        "--memory-limit",
        type=float,
        help="Memory limit in GB (default: 2GB)"
    )
    
    parser.add_argument(
        "--chunk-size",
        type=int,
        help="Number of images per chunk (default: 10)"
    )
    
    parser.add_argument(
        "--force-chunked",
        action="store_true",
        help="Force chunked processing even for small datasets"
    )
    
    args = parser.parse_args()
    
    # Validate input files
    files = []
    for file_path in args.fits_files:
        path = Path(file_path)
        if not path.exists():
            print(f"Error: File not found: {file_path}")
            sys.exit(1)
        if not path.suffix.lower() == '.fits':
            print(f"Warning: File may not be FITS format: {file_path}")
        files.append(str(path))
    
    if not files:
        print("Error: No valid FITS files provided")
        sys.exit(1)
    
    # Set output path
    if args.output:
        output_path = args.output
    else:
        if args.standard:
            output_path = "standard_stack.fits"
        else:
            output_path = "motion_tracked_stack.fits"
    
    # Set scaling function for flat fielding
    scale = None
    if args.flat_scale:
        import numpy as np
        def inv_median(data):
            return 1 / np.median(data)
        scale = inv_median
    
    # Set memory management parameters
    memory_limit = None
    if args.memory_limit:
        memory_limit = args.memory_limit * 1e9  # Convert GB to bytes
    
    try:
        print(f"Processing {len(files)} FITS files...")
        
        if args.standard:
            print("Using standard integration (no motion tracking)")
            result = integrate_standard(
                files=files,
                method=args.method,
                sigma_clip=not args.no_sigma_clip,
                scale=scale,
                output_path=output_path,
                memory_limit=memory_limit
            )
        else:
            print(f"Using motion tracking integration for object: {args.object_name}")
            result = integrate_with_motion_tracking(
                files=files,
                object_name=args.object_name,
                reference_time=args.reference_time,
                method=args.method,
                sigma_clip=not args.no_sigma_clip,
                scale=scale,
                output_path=output_path,
                force_chunked=args.force_chunked,
                chunk_size=args.chunk_size,
                memory_limit=memory_limit
            )
        
        print(f"\n✓ Integration completed successfully!")
        print(f"Output saved to: {output_path}")
        
        # Print some metadata
        if hasattr(result, 'meta'):
            print(f"\nMetadata:")
            if 'MOTION_TRACKED' in result.meta:
                print(f"  Motion tracked: {result.meta['MOTION_TRACKED']}")
            if 'TRACKED_OBJECT' in result.meta:
                print(f"  Tracked object: {result.meta['TRACKED_OBJECT']}")
            if 'REFERENCE_TIME' in result.meta:
                print(f"  Reference time: {result.meta['REFERENCE_TIME']}")
            if 'CHUNKED_PROCESSING' in result.meta:
                print(f"  Chunked processing: {result.meta['CHUNKED_PROCESSING']}")
            if 'TOTAL_CHUNKS' in result.meta:
                print(f"  Total chunks: {result.meta['TOTAL_CHUNKS']}")
            if 'FILTER' in result.meta:
                print(f"  Filter: {result.meta['FILTER']}")
            if 'EXPTIME' in result.meta:
                print(f"  Exposure time: {result.meta['EXPTIME']}s")
        
        print(f"\nImage shape: {result.data.shape}")
        print(f"Data type: {result.data.dtype}")
        print(f"Data range: {result.data.min():.2f} to {result.data.max():.2f}")
        
    except MotionTrackingIntegrationError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 