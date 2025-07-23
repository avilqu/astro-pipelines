import numpy as np
from astropy.wcs import WCS
from astropy.io import fits
from typing import List, Tuple, Optional

try:
    from reproject import reproject_interp
except ImportError:
    reproject_interp = None  # Will raise error if used without install

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