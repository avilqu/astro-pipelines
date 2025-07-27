import numpy as np
from astropy.wcs import WCS
from astropy.io import fits
from typing import List, Tuple, Optional

try:
    from reproject import reproject_interp
except ImportError:
    reproject_interp = None  # Will raise error if used without install

try:
    import astroalign as aa
    ASTROALIGN_AVAILABLE = True
except ImportError:
    ASTROALIGN_AVAILABLE = False

class AlignmentError(Exception):
    pass

def check_all_have_wcs(headers: List[fits.Header]) -> bool:
    """Return True if all headers have valid WCS, else False."""
    for header in headers:
        try:
            wcs = WCS(header)
            if not wcs.has_celestial:
                return False
        except Exception:
            return False
    return True

def check_pixel_scales_match(headers: List[fits.Header]) -> bool:
    """Return True if all images have the same pixel scale within 0.01 arcsec tolerance."""
    scales = []
    for header in headers:
        wcs = WCS(header)
        try:
            # Pixel scale in degrees per pixel
            scale_deg = np.abs(wcs.pixel_scale_matrix.diagonal())
            scales.append(scale_deg)
        except Exception:
            return False
    # Convert to arcsec per pixel
    scales_arcsec = [s * 3600 for s in scales]
    ref = scales_arcsec[0]
    for s in scales_arcsec[1:]:
        if not np.all(np.abs(ref - s) <= 0.01):
            return False
    return True

def compute_padded_reference_wcs(headers: List[fits.Header], paddings: Tuple[int, int]=(0, 0)) -> Tuple[WCS, Tuple[int, int]]:
    """
    Use the WCS of the first header as the reference, with no extra padding.
    Returns: (new_wcs, (new_nx, new_ny))
    """
    ref_header = headers[0].copy()
    wcs = WCS(ref_header)
    # No padding: use original CRPIX and NAXIS values
    new_nx = ref_header['NAXIS1']
    new_ny = ref_header['NAXIS2']
    return WCS(ref_header), (new_nx, new_ny)

def reproject_images_to_common_wcs(image_datas: List[np.ndarray], headers: List[fits.Header], common_wcs: WCS, shape_out: Tuple[int, int], progress_callback=None) -> List[np.ndarray]:
    """
    Reproject all images to the common WCS frame.
    progress_callback: optional function(progress: float) for UI updates.
    Returns list of reprojected images.
    """
    if reproject_interp is None:
        raise ImportError("reproject package is required for WCS alignment.")
    result = []
    n = len(image_datas)
    for i, (data, header) in enumerate(zip(image_datas, headers)):
        wcs = WCS(header)
        array, _ = reproject_interp((data, wcs), common_wcs, shape_out=shape_out, order='bilinear')
        result.append(array)
        if progress_callback:
            progress_callback((i+1)/n)
    return result

# New astroalign-based alignment functions
def _fix_byte_order_for_astroalign(image: np.ndarray) -> np.ndarray:
    """
    Convert image to native byte order for astroalign compatibility.
    
    Parameters:
    -----------
    image : np.ndarray
        Input image array
        
    Returns:
    --------
    np.ndarray
        Image with native byte order
    """
    if image.dtype.byteorder == '>':  # Big-endian
        return image.astype(image.dtype.newbyteorder('='))
    else:
        return image

def align_images_with_astroalign(image_datas: List[np.ndarray], reference_index: int = 0, progress_callback=None) -> List[np.ndarray]:
    """
    Align images using astroalign's asterism matching.
    
    Parameters:
    -----------
    image_datas : List[np.ndarray]
        List of image arrays to align
    reference_index : int
        Index of the reference image (default: 0)
    progress_callback : callable, optional
        Progress callback function(progress: float)
        
    Returns:
    --------
    List[np.ndarray]
        List of aligned images
    """
    if not ASTROALIGN_AVAILABLE:
        raise ImportError("astroalign package is required for asterism-based alignment.")
    
    if len(image_datas) < 2:
        return image_datas
    
    # Use the first image as reference
    reference_image = image_datas[reference_index]
    aligned_images = [reference_image]  # Reference image stays unchanged
    
    n = len(image_datas) - 1  # Exclude reference image
    current = 0
    
    for i, image in enumerate(image_datas):
        if i == reference_index:
            continue
            
        try:
            # Fix byte order issues for astroalign compatibility
            # Convert to native byte order if needed
            image_native = _fix_byte_order_for_astroalign(image)
            reference_native = _fix_byte_order_for_astroalign(reference_image)
            
            # Align current image to reference
            aligned_image, _ = aa.register(image_native, reference_native)
            aligned_images.append(aligned_image)
            
            current += 1
            if progress_callback:
                progress_callback(current / n)
                
        except Exception as e:
            print(f"Warning: Failed to align image {i} using astroalign: {e}")
            # If astroalign fails, use the original image
            aligned_images.append(image)
            current += 1
            if progress_callback:
                progress_callback(current / n)
    
    # Reorder to match original order
    result = [None] * len(image_datas)
    result[reference_index] = reference_image
    
    current = 0
    for i in range(len(image_datas)):
        if i != reference_index:
            result[i] = aligned_images[current + 1]  # +1 because aligned_images[0] is reference
            current += 1
    
    return result

def find_transform_with_astroalign(source_image: np.ndarray, target_image: np.ndarray) -> Tuple[np.ndarray, List[Tuple[float, float]]]:
    """
    Find the transformation matrix between two images using astroalign.
    
    Parameters:
    -----------
    source_image : np.ndarray
        Source image
    target_image : np.ndarray
        Target image
        
    Returns:
    --------
    Tuple[np.ndarray, List[Tuple[float, float]]]
        Transformation matrix and list of matched source points
    """
    if not ASTROALIGN_AVAILABLE:
        raise ImportError("astroalign package is required for asterism-based alignment.")
    
    try:
        # Fix byte order issues for astroalign compatibility
        source_native = _fix_byte_order_for_astroalign(source_image)
        target_native = _fix_byte_order_for_astroalign(target_image)
        
        # Find transformation matrix
        transform_matrix, (source_stars, target_stars) = aa.find_transform(source_native, target_native)
        return transform_matrix, source_stars
    except Exception as e:
        raise AlignmentError(f"Failed to find transformation: {e}")

def apply_transform_with_astroalign(image: np.ndarray, transform_matrix: np.ndarray, target_shape: Optional[Tuple[int, int]] = None) -> np.ndarray:
    """
    Apply transformation matrix to an image.
    
    Parameters:
    -----------
    image : np.ndarray
        Image to transform
    transform_matrix : np.ndarray
        Transformation matrix from astroalign
    target_shape : Tuple[int, int], optional
        Target shape for the output image
        
    Returns:
    --------
    np.ndarray
        Transformed image
    """
    if not ASTROALIGN_AVAILABLE:
        raise ImportError("astroalign package is required for asterism-based alignment.")
    
    try:
        # Fix byte order issues for astroalign compatibility
        image_native = _fix_byte_order_for_astroalign(image)
        
        if target_shape is None:
            target_shape = image.shape
        
        transformed_image = aa.apply_transform(transform_matrix, image_native, target_shape)
        return transformed_image
    except Exception as e:
        raise AlignmentError(f"Failed to apply transformation: {e}")

def check_astroalign_available() -> bool:
    """Check if astroalign is available for use."""
    return ASTROALIGN_AVAILABLE

def get_alignment_methods() -> List[str]:
    """Get list of available alignment methods."""
    methods = ["wcs_reprojection"]
    if ASTROALIGN_AVAILABLE:
        methods.append("astroalign")
    return methods 