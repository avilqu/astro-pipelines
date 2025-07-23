import numpy as np
from PyQt6.QtGui import QPixmap, QImage


def create_image_object(image_data: np.ndarray, display_min=None, display_max=None):
    """Convert numpy array to QPixmap for display - optimized version"""
    # Use provided display range or calculate from histogram
    if display_min is None or display_max is None:
        histo = np.histogram(image_data, 60, None, True)
        display_min = histo[1][0]
        display_max = histo[1][-1]
    
    # Apply histogram stretching
    if display_max > display_min:
        clipped_data = np.clip(image_data, display_min, display_max)
        normalized_data = (clipped_data - display_min) / (display_max - display_min)
    else:
        normalized_data = image_data - image_data.min()
        if normalized_data.max() > 0:
            normalized_data = normalized_data / normalized_data.max()
    
    # Convert to 8-bit for display
    display_data = (normalized_data * 255).astype(np.uint8)
    
    # Create QImage from numpy array
    height, width = display_data.shape
    display_data = np.ascontiguousarray(display_data)
    q_image = QImage(display_data.data, width, height, width, QImage.Format.Format_Grayscale8)
    q_image = q_image.copy()
    
    # Convert to pixmap
    return QPixmap.fromImage(q_image)