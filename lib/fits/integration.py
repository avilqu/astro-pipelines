"""
Image integration module with motion tracking capabilities.

This module provides functions to integrate (stack) astronomical images while
keeping moving objects static based on ephemeris information. It combines
traditional WCS-based alignment with ephemeris-based motion tracking.
"""

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy.stats import mad_std
from astropy.time import Time
import ccdproc as ccdp
from typing import List, Dict, Optional, Tuple, Union, Callable
from pathlib import Path
import warnings

# Import configuration
from config import (SIGMA_LOW, SIGMA_HIGH, TESTED_FITS_CARDS, 
                   INTEGRATION_MEMORY_LIMIT, INTEGRATION_CHUNK_SIZE, INTEGRATION_ENABLE_CHUNKED)

# Memory management configuration
MEMORY_LIMIT = INTEGRATION_MEMORY_LIMIT
CHUNK_SIZE = INTEGRATION_CHUNK_SIZE
ENABLE_CHUNKED_PROCESSING = INTEGRATION_ENABLE_CHUNKED

# Import ephemeris functionality
from lib.astrometry.orbit import predict_position_findorb, get_neofixer_orbit


class MotionTrackingIntegrationError(Exception):
    """Exception raised for errors in motion tracking integration."""
    pass


def check_sequence_consistency(files: List[str]) -> bool:
    """
    Check consistency of FITS sequence before integration.
    
    Parameters:
    -----------
    files : List[str]
        List of FITS file paths
        
    Returns:
    --------
    bool
        True if sequence is consistent, False otherwise
    """
    if not files:
        raise MotionTrackingIntegrationError("No input files provided")
    
    print(f"\nChecking FITS sequence consistency for {len(files)} files...")
    
    # Read headers
    headers = []
    for file_path in files:
        try:
            header = fits.getheader(file_path, ext=0)
            headers.append(header)
        except Exception as e:
            print(f"Warning: Could not read header from {file_path}: {e}")
            return False
    
    # Check consistency for each tested card
    res = True
    for card_config in TESTED_FITS_CARDS:
        card_name = card_config['name']
        tolerance = card_config['tolerance']
        
        values = []
        for header in headers:
            if card_name in header:
                values.append(header[card_name])
            else:
                print(f"Warning: Missing header card '{card_name}' in some files")
                res = False
                break
        
        if not values:
            continue
            
        if tolerance == 0:
            # Exact match required
            if len(set(values)) > 1:
                print(f"Warning: Multiple {card_name} values in sequence: {set(values)}")
                res = False
            else:
                print(f"✓ {card_name} values are consistent: {values[0]}")
        else:
            # Allow tolerance
            average = np.mean(values)
            max_deviation = max(abs(val - average) for val in values)
            print(f"✓ {card_name} average: {average:.2f}, max deviation: {max_deviation:.2f}")
            if max_deviation > tolerance:
                print(f"Warning: {card_name} values exceed tolerance")
                res = False
    
    if res:
        print("✓ FITS sequence is consistent")
    else:
        print("✗ FITS sequence has inconsistencies")
    
    return res


def extract_ccd_data(file_path: str) -> ccdp.CCDData:
    """
    Extract CCDData from a FITS file.
    
    Parameters:
    -----------
    file_path : str
        Path to FITS file
        
    Returns:
    --------
    ccdp.CCDData
        CCDData object
    """
    try:
        return ccdp.CCDData.read(file_path, unit='adu')
    except Exception as e:
        raise MotionTrackingIntegrationError(f"Could not read {file_path}: {e}")


def get_observation_time(file_path: str) -> Optional[str]:
    """
    Extract observation time from FITS file.
    
    Parameters:
    -----------
    file_path : str
        Path to FITS file
        
    Returns:
    --------
    Optional[str]
        ISO format observation time string, or None if not found
    """
    try:
        header = fits.getheader(file_path, ext=0)
        date_obs = header.get('DATE-OBS')
        
        if not date_obs:
            return None
            
        # Format to ISO string
        import re
        from datetime import datetime
        
        match = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::(\d{2}))?", date_obs)
        if match:
            seconds = match.group(3) if match.group(3) is not None else '00'
            return f"{match.group(1)}T{match.group(2)}:{seconds}"
        else:
            # Fallback parsing
            try:
                dt = datetime.fromisoformat(date_obs.replace('Z', '+00:00'))
                return dt.strftime('%Y-%m-%dT%H:%M:%S')
            except Exception:
                return date_obs[:10] + 'T' + date_obs[11:16] + ':00'
                
    except Exception as e:
        print(f"Warning: Could not extract observation time from {file_path}: {e}")
        return None


def calculate_motion_shifts(files: List[str], object_name: str, 
                          reference_time: Optional[str] = None) -> List[Tuple[float, float]]:
    """
    Calculate pixel shifts needed to keep moving object static.
    
    Parameters:
    -----------
    files : List[str]
        List of FITS file paths
    object_name : str
        Name of the moving object (e.g., '2025 BC')
    reference_time : Optional[str]
        Reference time for position (ISO format). If None, uses first image time.
        
    Returns:
    --------
    List[Tuple[float, float]]
        List of (dx, dy) pixel shifts for each image
    """
    print(f"\nCalculating motion shifts for object {object_name}...")
    
    shifts = []
    reference_ra = None
    reference_dec = None
    
    for i, file_path in enumerate(files):
        print(f"Processing {i+1}/{len(files)}: {Path(file_path).name}")
        
        # Get observation time
        obs_time = get_observation_time(file_path)
        if not obs_time:
            print(f"Warning: No observation time for {file_path}, using zero shift")
            shifts.append((0.0, 0.0))
            continue
        
        # Get predicted position
        try:
            result = predict_position_findorb(object_name, obs_time)
            if result and 'ephemeris' in result and 'entries' in result['ephemeris']:
                entry = result['ephemeris']['entries']['0']
                ra = float(entry.get('RA', 0.0))
                dec = float(entry.get('Dec', 0.0))
                print(f"  Predicted position: RA={ra:.6f}°, Dec={dec:.6f}°")
            else:
                print(f"Warning: Could not get ephemeris for {file_path}")
                shifts.append((0.0, 0.0))
                continue
        except Exception as e:
            print(f"Warning: Error getting ephemeris for {file_path}: {e}")
            shifts.append((0.0, 0.0))
            continue
        
        # Set reference position (first image or specified time)
        if reference_ra is None:
            if reference_time is None:
                # Use first image as reference
                reference_ra, reference_dec = ra, dec
                print(f"  Using first image as reference: RA={reference_ra:.6f}°, Dec={reference_dec:.6f}°")
            else:
                # Get reference position at specified time
                try:
                    ref_result = predict_position_findorb(object_name, reference_time)
                    if ref_result and 'ephemeris' in ref_result and 'entries' in ref_result['ephemeris']:
                        ref_entry = ref_result['ephemeris']['entries']['0']
                        reference_ra = float(ref_entry.get('RA', 0.0))
                        reference_dec = float(ref_entry.get('Dec', 0.0))
                        print(f"  Reference position at {reference_time}: RA={reference_ra:.6f}°, Dec={reference_dec:.6f}°")
                    else:
                        reference_ra, reference_dec = ra, dec
                        print(f"  Using first image as reference: RA={reference_ra:.6f}°, Dec={reference_dec:.6f}°")
                except Exception as e:
                    print(f"Warning: Could not get reference ephemeris: {e}")
                    reference_ra, reference_dec = ra, dec
                    print(f"  Using first image as reference: RA={reference_ra:.6f}°, Dec={reference_dec:.6f}°")
        
        # Calculate angular offset
        dra = (ra - reference_ra) * np.cos(np.radians(reference_dec))
        ddec = dec - reference_dec
        
        # Convert to pixel shifts using WCS
        try:
            wcs = WCS(fits.getheader(file_path, ext=0))
            if wcs.is_celestial:
                # Convert angular offset to pixel offset
                pixel_scale = wcs.pixel_scale_matrix.diagonal()
                dx = -dra / (pixel_scale[0] * u.deg).to(u.arcsec).value * 3600  # Convert to arcsec
                dy = -ddec / (pixel_scale[1] * u.deg).to(u.arcsec).value * 3600
                
                # Convert arcsec to pixels using pixel scale
                dx_pix = dx / (pixel_scale[0] * u.deg).to(u.arcsec).value
                dy_pix = dy / (pixel_scale[1] * u.deg).to(u.arcsec).value
                
                shifts.append((dx_pix, dy_pix))
                print(f"  Shift: dx={dx_pix:.2f} pix, dy={dy_pix:.2f} pix")
            else:
                print(f"Warning: No valid WCS in {file_path}")
                shifts.append((0.0, 0.0))
        except Exception as e:
            print(f"Warning: Error calculating pixel shift for {file_path}: {e}")
            shifts.append((0.0, 0.0))
    
    return shifts


def shift_image(image: np.ndarray, dx: float, dy: float, 
                interpolation: str = 'bilinear') -> np.ndarray:
    """
    Shift an image by the specified pixel offsets.
    
    Parameters:
    -----------
    image : np.ndarray
        Input image array
    dx : float
        X-axis shift in pixels
    dy : float
        Y-axis shift in pixels
    interpolation : str
        Interpolation method ('bilinear', 'bicubic', 'nearest')
        
    Returns:
    --------
    np.ndarray
        Shifted image
    """
    from scipy.ndimage import shift
    
    if dx == 0 and dy == 0:
        return image
    
    # scipy.ndimage.shift uses (dy, dx) order
    shifted = shift(image, (dy, dx), order=1, mode='constant', cval=np.nan)
    
    return shifted


def integrate_chunked(files: List[str], 
                     object_name: str,
                     reference_time: Optional[str] = None,
                     method: str = 'average',
                     sigma_clip: bool = True,
                     scale: Optional[Callable] = None,
                     output_path: Optional[str] = None,
                     progress_callback: Optional[Callable] = None,
                     chunk_size: Optional[int] = None,
                     memory_limit: Optional[float] = None) -> ccdp.CCDData:
    """
    Integrate images in chunks to prevent memory issues with large datasets.
    
    Parameters:
    -----------
    files : List[str]
        List of FITS file paths to integrate
    object_name : str
        Name of the moving object (e.g., '2025 BC')
    reference_time : Optional[str]
        Reference time for object position (ISO format). If None, uses first image.
    method : str
        Integration method ('average', 'median', 'sum')
    sigma_clip : bool
        Whether to apply sigma clipping
    scale : Optional[Callable]
        Scaling function (e.g., for flat fielding)
    output_path : Optional[str]
        Path to save the integrated image
    progress_callback : Optional[Callable]
        Progress callback function(progress: float)
    chunk_size : Optional[int]
        Number of images per chunk. If None, uses default CHUNK_SIZE.
    memory_limit : Optional[float]
        Memory limit in bytes. If None, uses default MEMORY_LIMIT.
        
    Returns:
    --------
    ccdp.CCDData
        Integrated image with motion tracking applied
    """
    if not files:
        raise MotionTrackingIntegrationError("No input files provided")
    
    # Use defaults if not specified
    chunk_size = chunk_size or CHUNK_SIZE
    memory_limit = memory_limit or MEMORY_LIMIT
    
    print(f"\nIntegrating {len(files)} images with chunked processing")
    print(f"Chunk size: {chunk_size} images")
    print(f"Memory limit: {memory_limit / 1e9:.1f} GB")
    
    # Check sequence consistency
    if not check_sequence_consistency(files):
        print("Warning: Sequence has inconsistencies, proceeding anyway...")
    
    # Calculate motion shifts for all files
    shifts = calculate_motion_shifts(files, object_name, reference_time)
    
    # Process in chunks
    total_chunks = (len(files) + chunk_size - 1) // chunk_size
    chunk_results = []
    
    for chunk_idx in range(total_chunks):
        start_idx = chunk_idx * chunk_size
        end_idx = min(start_idx + chunk_size, len(files))
        chunk_files = files[start_idx:end_idx]
        chunk_shifts = shifts[start_idx:end_idx]
        
        print(f"\nProcessing chunk {chunk_idx + 1}/{total_chunks} ({len(chunk_files)} images)")
        
        # Load and shift images for this chunk
        shifted_images = []
        for i, (file_path, (dx, dy)) in enumerate(zip(chunk_files, chunk_shifts)):
            if progress_callback:
                overall_progress = (chunk_idx * chunk_size + i) / len(files)
                progress_callback(overall_progress)
                
            print(f"  Processing {start_idx + i + 1}/{len(files)}: {Path(file_path).name}")
            
            try:
                # Load image
                ccd = extract_ccd_data(file_path)
                
                # Apply shift
                if dx != 0 or dy != 0:
                    shifted_data = shift_image(ccd.data, dx, dy)
                    ccd.data = shifted_data
                    print(f"    Applied shift: dx={dx:.2f}, dy={dy:.2f}")
                
                shifted_images.append(ccd)
                
            except Exception as e:
                print(f"Warning: Error processing {file_path}: {e}")
                continue
        
        if not shifted_images:
            print(f"Warning: No valid images in chunk {chunk_idx + 1}")
            continue
        
        # Integrate this chunk
        print(f"  Integrating chunk {chunk_idx + 1} ({len(shifted_images)} images)...")
        try:
            if sigma_clip:
                chunk_stack = ccdp.combine(
                    shifted_images,
                    method=method,
                    scale=scale,
                    sigma_clip=True,
                    sigma_clip_low_thresh=SIGMA_LOW,
                    sigma_clip_high_thresh=SIGMA_HIGH,
                    sigma_clip_func=np.ma.median,
                    sigma_clip_dev_func=mad_std,
                    mem_limit=memory_limit,
                    unit='adu',
                    dtype='float32'
                )
            else:
                chunk_stack = ccdp.combine(
                    shifted_images,
                    method=method,
                    scale=scale,
                    mem_limit=memory_limit,
                    unit='adu',
                    dtype='float32'
                )
            
            # Add chunk metadata
            chunk_stack.meta['CHUNK_ID'] = chunk_idx
            chunk_stack.meta['CHUNK_SIZE'] = len(shifted_images)
            chunk_stack.meta['TOTAL_CHUNKS'] = total_chunks
            
            chunk_results.append(chunk_stack)
            
            # Clear memory
            del shifted_images
            import gc
            gc.collect()
            
        except Exception as e:
            print(f"Error integrating chunk {chunk_idx + 1}: {e}")
            continue
    
    if not chunk_results:
        raise MotionTrackingIntegrationError("No valid chunks to integrate")
    
    # Combine all chunks
    print(f"\nCombining {len(chunk_results)} chunks...")
    try:
        if len(chunk_results) == 1:
            # Only one chunk, use it directly
            final_stack = chunk_results[0]
        else:
            # Multiple chunks, combine them
            if sigma_clip:
                final_stack = ccdp.combine(
                    chunk_results,
                    method=method,
                    scale=scale,
                    sigma_clip=True,
                    sigma_clip_low_thresh=SIGMA_LOW,
                    sigma_clip_high_thresh=SIGMA_HIGH,
                    sigma_clip_func=np.ma.median,
                    sigma_clip_dev_func=mad_std,
                    mem_limit=memory_limit,
                    unit='adu',
                    dtype='float32'
                )
            else:
                final_stack = ccdp.combine(
                    chunk_results,
                    method=method,
                    scale=scale,
                    mem_limit=memory_limit,
                    unit='adu',
                    dtype='float32'
                )
        
        # Clean up metadata
        final_stack.meta['COMBINED'] = True
        final_stack.meta['MOTION_TRACKED'] = True
        final_stack.meta['TRACKED_OBJECT'] = object_name
        final_stack.meta['CHUNKED_PROCESSING'] = True
        final_stack.meta['TOTAL_CHUNKS'] = total_chunks
        if reference_time:
            final_stack.meta['REFERENCE_TIME'] = reference_time
        final_stack.uncertainty = None
        final_stack.mask = None
        final_stack.flags = None
        
        # Remove chunk-specific metadata
        for key in ['CHUNK_ID', 'CHUNK_SIZE']:
            if key in final_stack.meta:
                del final_stack.meta[key]
        
        print(f"✓ Chunked integration complete")
        
        # Save if requested
        if output_path:
            print(f"Saving integrated image to {output_path}")
            final_stack.write(output_path, overwrite=True)
        
        if progress_callback:
            progress_callback(1.0)
            
        return final_stack
        
    except Exception as e:
        raise MotionTrackingIntegrationError(f"Error during chunk combination: {e}")


def integrate_with_motion_tracking(files: List[str], 
                                 object_name: str,
                                 reference_time: Optional[str] = None,
                                 method: str = 'average',
                                 sigma_clip: bool = True,
                                 scale: Optional[Callable] = None,
                                 output_path: Optional[str] = None,
                                 progress_callback: Optional[Callable] = None,
                                 force_chunked: bool = False,
                                 chunk_size: Optional[int] = None,
                                 memory_limit: Optional[float] = None) -> ccdp.CCDData:
    """
    Integrate a sequence of images while keeping a moving object static.
    
    Parameters:
    -----------
    files : List[str]
        List of FITS file paths to integrate
    object_name : str
        Name of the moving object (e.g., '2025 BC')
    reference_time : Optional[str]
        Reference time for object position (ISO format). If None, uses first image.
    method : str
        Integration method ('average', 'median', 'sum')
    sigma_clip : bool
        Whether to apply sigma clipping
    scale : Optional[Callable]
        Scaling function (e.g., for flat fielding)
    output_path : Optional[str]
        Path to save the integrated image
    progress_callback : Optional[Callable]
        Progress callback function(progress: float)
    force_chunked : bool
        Force chunked processing even for small datasets
    chunk_size : Optional[int]
        Number of images per chunk for chunked processing
    memory_limit : Optional[float]
        Memory limit in bytes for processing
        
    Returns:
    --------
    ccdp.CCDData
        Integrated image with motion tracking applied
    """
    if not files:
        raise MotionTrackingIntegrationError("No input files provided")
    
    # Determine if we should use chunked processing
    use_chunked = force_chunked or (ENABLE_CHUNKED_PROCESSING and len(files) > CHUNK_SIZE)
    
    if use_chunked:
        print(f"Using chunked processing for {len(files)} images")
        return integrate_chunked(
            files=files,
            object_name=object_name,
            reference_time=reference_time,
            method=method,
            sigma_clip=sigma_clip,
            scale=scale,
            output_path=output_path,
            progress_callback=progress_callback,
            chunk_size=chunk_size,
            memory_limit=memory_limit
        )
    
    print(f"\nIntegrating {len(files)} images with motion tracking for {object_name}")
    
    # Check sequence consistency
    if not check_sequence_consistency(files):
        print("Warning: Sequence has inconsistencies, proceeding anyway...")
    
    # Calculate motion shifts
    shifts = calculate_motion_shifts(files, object_name, reference_time)
    
    # Load and shift images
    print(f"\nLoading and shifting images...")
    shifted_images = []
    
    for i, (file_path, (dx, dy)) in enumerate(zip(files, shifts)):
        if progress_callback:
            progress_callback(i / len(files))
            
        print(f"Processing {i+1}/{len(files)}: {Path(file_path).name}")
        
        try:
            # Load image
            ccd = extract_ccd_data(file_path)
            
            # Apply shift
            if dx != 0 or dy != 0:
                shifted_data = shift_image(ccd.data, dx, dy)
                ccd.data = shifted_data
                print(f"  Applied shift: dx={dx:.2f}, dy={dy:.2f}")
            
            shifted_images.append(ccd)
            
        except Exception as e:
            print(f"Warning: Error processing {file_path}: {e}")
            continue
    
    if not shifted_images:
        raise MotionTrackingIntegrationError("No valid images to integrate")
    
    print(f"\nIntegrating {len(shifted_images)} shifted images...")
    
    # Use configured memory limit
    mem_limit = memory_limit or MEMORY_LIMIT
    
    # Integrate using ccdproc
    try:
        if sigma_clip:
            stack = ccdp.combine(
                shifted_images,
                method=method,
                scale=scale,
                sigma_clip=True,
                sigma_clip_low_thresh=SIGMA_LOW,
                sigma_clip_high_thresh=SIGMA_HIGH,
                sigma_clip_func=np.ma.median,
                sigma_clip_dev_func=mad_std,
                mem_limit=mem_limit,
                unit='adu',
                dtype='float32'
            )
        else:
            stack = ccdp.combine(
                shifted_images,
                method=method,
                scale=scale,
                mem_limit=mem_limit,
                unit='adu',
                dtype='float32'
            )
        
        # Clean up metadata
        stack.meta['COMBINED'] = True
        stack.meta['MOTION_TRACKED'] = True
        stack.meta['TRACKED_OBJECT'] = object_name
        stack.meta['CHUNKED_PROCESSING'] = False
        if reference_time:
            stack.meta['REFERENCE_TIME'] = reference_time
        stack.uncertainty = None
        stack.mask = None
        stack.flags = None
        
        print(f"✓ Integration complete")
        
        # Save if requested
        if output_path:
            print(f"Saving integrated image to {output_path}")
            stack.write(output_path, overwrite=True)
        
        if progress_callback:
            progress_callback(1.0)
            
        return stack
        
    except Exception as e:
        raise MotionTrackingIntegrationError(f"Error during integration: {e}")


def integrate_standard(files: List[str],
                      method: str = 'average',
                      sigma_clip: bool = True,
                      scale: Optional[Callable] = None,
                      output_path: Optional[str] = None,
                      progress_callback: Optional[Callable] = None,
                      memory_limit: Optional[float] = None) -> ccdp.CCDData:
    """
    Standard image integration without motion tracking.
    
    Parameters:
    -----------
    files : List[str]
        List of FITS file paths to integrate
    method : str
        Integration method ('average', 'median', 'sum')
    sigma_clip : bool
        Whether to apply sigma clipping
    scale : Optional[Callable]
        Scaling function (e.g., for flat fielding)
    output_path : Optional[str]
        Path to save the integrated image
    progress_callback : Optional[Callable]
        Progress callback function(progress: float)
    memory_limit : Optional[float]
        Memory limit in bytes for processing
        
    Returns:
    --------
    ccdp.CCDData
        Integrated image
    """
    if not files:
        raise MotionTrackingIntegrationError("No input files provided")
    
    print(f"\nIntegrating {len(files)} images (standard method)")
    
    # Check sequence consistency
    if not check_sequence_consistency(files):
        print("Warning: Sequence has inconsistencies, proceeding anyway...")
    
    # Load images
    print(f"Loading images...")
    images = []
    
    for i, file_path in enumerate(files):
        if progress_callback:
            progress_callback(i / len(files))
            
        try:
            ccd = extract_ccd_data(file_path)
            images.append(ccd)
        except Exception as e:
            print(f"Warning: Error loading {file_path}: {e}")
            continue
    
    if not images:
        raise MotionTrackingIntegrationError("No valid images to integrate")
    
    print(f"Integrating {len(images)} images...")
    
    # Use configured memory limit
    mem_limit = memory_limit or MEMORY_LIMIT
    
    # Integrate using ccdproc
    try:
        if sigma_clip:
            stack = ccdp.combine(
                images,
                method=method,
                scale=scale,
                sigma_clip=True,
                sigma_clip_low_thresh=SIGMA_LOW,
                sigma_clip_high_thresh=SIGMA_HIGH,
                sigma_clip_func=np.ma.median,
                sigma_clip_dev_func=mad_std,
                mem_limit=mem_limit,
                unit='adu',
                dtype='float32'
            )
        else:
            stack = ccdp.combine(
                images,
                method=method,
                scale=scale,
                mem_limit=mem_limit,
                unit='adu',
                dtype='float32'
            )
        
        # Clean up metadata
        stack.meta['COMBINED'] = True
        stack.meta['MOTION_TRACKED'] = False
        stack.meta['CHUNKED_PROCESSING'] = False
        stack.uncertainty = None
        stack.mask = None
        stack.flags = None
        
        print(f"✓ Integration complete")
        
        # Save if requested
        if output_path:
            print(f"Saving integrated image to {output_path}")
            stack.write(output_path, overwrite=True)
        
        if progress_callback:
            progress_callback(1.0)
            
        return stack
        
    except Exception as e:
        raise MotionTrackingIntegrationError(f"Error during integration: {e}") 