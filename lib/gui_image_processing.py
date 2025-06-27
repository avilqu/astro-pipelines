import numpy as np
from PyQt6.QtGui import QPixmap, QImage, QPainter, QFont, QPen, QColor
from PyQt6.QtCore import Qt


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


def add_object_markers(pixmap, object_pixel_coords, show_objects, 
                      simbad_object, simbad_pixel_coords, show_simbad_object, scale_factor):
    """Add circles for solar system objects and SIMBAD objects to the pixmap - optimized version"""
    # Add solar system objects (green circles)
    if show_objects and object_pixel_coords:
        # Create a painter to draw on the pixmap
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate font size based on zoom level (larger font for higher zoom)
        base_font_size = 16
        scaled_font_size = max(8, base_font_size * scale_factor)
        font = QFont("Arial", int(scaled_font_size))
        painter.setFont(font)
        
        # Scale circle size and line width with zoom level (larger circles for higher zoom)
        base_circle_radius = 12
        scaled_circle_radius = max(6, base_circle_radius * scale_factor)
        scaled_pen_width = max(1, 2 * scale_factor)
        
        # Draw circles for each solar system object
        for obj, x_pixel, y_pixel in object_pixel_coords:
            if (0 <= x_pixel < pixmap.width() and 0 <= y_pixel < pixmap.height()):
                # Draw circle in green
                circle_pen = QPen(QColor(0, 255, 0))
                circle_pen.setWidth(int(scaled_pen_width))
                painter.setPen(circle_pen)
                painter.drawEllipse(int(x_pixel - scaled_circle_radius), int(y_pixel - scaled_circle_radius), 
                                   int(scaled_circle_radius * 2), int(scaled_circle_radius * 2))
                
                # Add object name
                if len(object_pixel_coords) <= 10:
                    text_x = int(x_pixel + scaled_circle_radius + 8)
                    text_y = int(y_pixel + 8)
                    
                    # Draw outline
                    outline_pen = QPen(QColor(0, 0, 0))
                    outline_pen.setWidth(int(max(2, 5 * scale_factor)))
                    painter.setPen(outline_pen)
                    painter.drawText(text_x, text_y, obj.name)
                    
                    # Draw text in green
                    text_pen = QPen(QColor(0, 255, 0))
                    painter.setPen(text_pen)
                    painter.drawText(text_x, text_y, obj.name)
        
        painter.end()
    
    # Add SIMBAD object (red circle)
    if show_simbad_object and simbad_object and simbad_pixel_coords:
        # Create a painter to draw on the pixmap
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate font size based on zoom level (larger font for higher zoom)
        base_font_size = 16
        scaled_font_size = max(8, base_font_size * scale_factor)
        font = QFont("Arial", int(scaled_font_size))
        painter.setFont(font)
        
        # Scale circle size and line width with zoom level (larger circles for higher zoom)
        base_circle_radius = 15  # Slightly larger for SIMBAD objects
        scaled_circle_radius = max(8, base_circle_radius * scale_factor)
        scaled_pen_width = max(2, 3 * scale_factor)  # Thicker line for SIMBAD objects
        
        x_pixel, y_pixel = simbad_pixel_coords
        
        if (0 <= x_pixel < pixmap.width() and 0 <= y_pixel < pixmap.height()):
            # Draw circle in red
            circle_pen = QPen(QColor(255, 0, 0))
            circle_pen.setWidth(int(scaled_pen_width))
            painter.setPen(circle_pen)
            painter.drawEllipse(int(x_pixel - scaled_circle_radius), int(y_pixel - scaled_circle_radius), 
                               int(scaled_circle_radius * 2), int(scaled_circle_radius * 2))
            
            # Add object name
            text_x = int(x_pixel + scaled_circle_radius + 8)
            text_y = int(y_pixel + 8)
            
            # Draw outline
            outline_pen = QPen(QColor(0, 0, 0))
            outline_pen.setWidth(int(max(2, 5 * scale_factor)))
            painter.setPen(outline_pen)
            painter.drawText(text_x, text_y, simbad_object.name)
            
            # Draw text in red
            text_pen = QPen(QColor(255, 0, 0))
            painter.setPen(text_pen)
            painter.drawText(text_x, text_y, simbad_object.name)
        
        painter.end()
    
    return pixmap


def get_cached_zoom(scale_factor, working_pixmap, zoom_cache, max_cache_size):
    """Get cached zoom level or create and cache it"""
    # Round scale factor to reduce cache size
    rounded_scale = round(scale_factor, 2)
    cache_key = (rounded_scale, working_pixmap.width(), working_pixmap.height())
    
    if cache_key in zoom_cache:
        return zoom_cache[cache_key]
    
    # Calculate the scaled size
    scaled_width = int(working_pixmap.width() * rounded_scale)
    scaled_height = int(working_pixmap.height() * rounded_scale)
    
    # Use faster scaling for better performance
    if rounded_scale > 2.0:
        # For high zoom levels, use smooth transformation
        scaled_pixmap = working_pixmap.scaled(
            scaled_width,
            scaled_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
    else:
        # For normal zoom levels, use fast transformation
        scaled_pixmap = working_pixmap.scaled(
            scaled_width,
            scaled_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )
    
    # Cache the result
    zoom_cache[cache_key] = scaled_pixmap
    
    # Limit cache size
    if len(zoom_cache) > max_cache_size:
        # Remove oldest entry (simple FIFO)
        oldest_key = next(iter(zoom_cache))
        del zoom_cache[oldest_key]
    
    return scaled_pixmap


def calculate_bit_depth(image_data):
    """Calculate bit depth information from image data"""
    if image_data is None:
        return None
    
    data_type = image_data.dtype
    if data_type == np.uint8:
        return "255 (8 bits)"
    elif data_type == np.uint16:
        return "65535 (16 bits)"
    elif data_type == np.uint32:
        return "4294967295 (32 bits)"
    elif data_type == np.int16:
        return "32767 (16 bits)"
    elif data_type == np.int32:
        return "2147483647 (32 bits)"
    elif data_type == np.float32:
        return "float (32 bits)"
    elif data_type == np.float64:
        return "float (64 bits)"
    else:
        return f"{data_type}"


def apply_auto_stretch(image_data):
    """Apply auto histogram stretching using bright stretch code"""
    if image_data is None:
        return None, None
    
    # Use 5th and 95th percentiles (the bright stretch code that works)
    display_min = np.percentile(image_data, 1)
    display_max = np.percentile(image_data, 99)
    return display_min, display_max


def apply_no_stretch(image_data):
    """Apply no histogram stretching - use actual data min/max"""
    display_min = image_data.min()
    display_max = image_data.max()
    return display_min, display_max 