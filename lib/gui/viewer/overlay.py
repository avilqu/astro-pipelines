import sys
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.time import Time
from PyQt6.QtWidgets import QLabel, QScrollArea, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QMessageBox
from PyQt6.QtCore import Qt, QPoint, QTimer, QPointF, QRect
from PyQt6.QtGui import QPixmap, QPainter, QMouseEvent, QKeyEvent, QFont, QPen, QColor, QCursor

class ImageLabel(QLabel):
    """Custom QLabel that handles mouse events for panning and zooming, and supports overlays"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_viewer = parent
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.coord_timer = QTimer()
        self.coord_timer.setSingleShot(True)
        self.coord_timer.timeout.connect(self._update_coordinates)
        self.last_mouse_pos = QPoint()
        self.panning = False
        self.pan_start_pos = QPoint()
        self.pan_start_scroll = QPoint()
        self.original_cursor = None
        self.pan_timer = QTimer()
        self.pan_timer.timeout.connect(self._update_pan)
        self.pan_timer.setInterval(16)
        self.target_scroll_pos = QPoint()
        self._custom_cross_cursor = self._create_cross_cursor()
        # --- Zoom to region state ---
        self._zoom_region_mode = False
        self._zoom_region_start = None  # QPoint
        self._zoom_region_end = None    # QPoint
        self._zoom_region_active = False

    def _create_cross_cursor(self):
        # Create a 24x24 pixmap with a 1px thick white cross
        size = 24
        thickness = 1
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        pen = QPen(QColor(255, 255, 255), thickness)
        painter.setPen(pen)
        # Draw vertical line
        painter.drawLine(size // 2, 0, size // 2, size - 1)
        # Draw horizontal line
        painter.drawLine(0, size // 2, size - 1, size // 2)
        painter.end()
        # Hotspot at center
        return QCursor(pm, size // 2, size // 2)

    def enterEvent(self, event):
        if not self.panning:
            self.setCursor(self._custom_cross_cursor)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.panning:
            self.unsetCursor()
        super().leaveEvent(event)

    def set_zoom_region_mode(self, enabled):
        self._zoom_region_mode = enabled
        if not enabled:
            self._zoom_region_start = None
            self._zoom_region_end = None
            self._zoom_region_active = False
            self.update()

    def clear_zoom_region_rect(self):
        self._zoom_region_start = None
        self._zoom_region_end = None
        self._zoom_region_active = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if self._zoom_region_mode and event.button() == Qt.MouseButton.LeftButton:
            self._zoom_region_start = event.pos()
            self._zoom_region_end = event.pos()
            self._zoom_region_active = True
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.parent_viewer:
            self.panning = True
            self.pan_start_pos = event.pos()
            scroll_area = self.parent_viewer.scroll_area
            self.pan_start_scroll = QPoint(
                scroll_area.horizontalScrollBar().value(),
                scroll_area.verticalScrollBar().value()
            )
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.setCursor(Qt.CursorShape.BlankCursor)
            self.pan_timer.start()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._zoom_region_mode and self._zoom_region_active:
            self._zoom_region_end = event.pos()
            self.update()
            return
        if self.parent_viewer and self.parent_viewer.pixmap is not None:
            if self.panning:
                delta = event.pos() - self.pan_start_pos
                self.target_scroll_pos = QPoint(
                    self.pan_start_scroll.x() - delta.x(),
                    self.pan_start_scroll.y() - delta.y()
                )
            else:
                self.last_mouse_pos = event.pos()
                if not self.coord_timer.isActive():
                    self.coord_timer.start(50)
        super().mouseMoveEvent(event)

    def _update_pan(self):
        if not self.panning or not self.parent_viewer:
            return
        scroll_area = self.parent_viewer.scroll_area
        h_scroll = scroll_area.horizontalScrollBar()
        v_scroll = scroll_area.verticalScrollBar()
        
        # Allow panning beyond image boundaries by not constraining to maximum values
        # This enables viewing "empty space" around the image when zoomed out
        target_h = self.target_scroll_pos.x()
        target_v = self.target_scroll_pos.y()
        
        current_h = h_scroll.value()
        current_v = v_scroll.value()
        interpolation_factor = 0.7
        new_h = int(current_h + (target_h - current_h) * interpolation_factor)
        new_v = int(current_v + (target_v - current_v) * interpolation_factor)
        
        # Set the scroll values without constraining to maximum
        # This allows negative values and values beyond the image size
        h_scroll.setValue(new_h)
        v_scroll.setValue(new_v)

    def _update_coordinates(self):
        if not self.parent_viewer or not self.parent_viewer.wcs or self.panning:
            return
        mouse_pos = self.last_mouse_pos
        pixmap = self.pixmap()
        if not pixmap or self.parent_viewer.image_data is None:
            return
        img_h, img_w = self.parent_viewer.image_data.shape
        pixmap_w = pixmap.width()
        pixmap_h = pixmap.height()
        label_w = self.width()
        label_h = self.height()
        # Compute centering offset and scale (aspect ratio preserved)
        scale_x = pixmap_w / img_w
        scale_y = pixmap_h / img_h
        scale = scale_x  # or scale_y, they should be equal
        x_offset = (label_w - pixmap_w) // 2
        y_offset = (label_h - pixmap_h) // 2
        # Map mouse position to image coordinates
        pixmap_x = mouse_pos.x() - x_offset
        pixmap_y = mouse_pos.y() - y_offset
        if (0 <= pixmap_x < pixmap_w and 0 <= pixmap_y < pixmap_h):
            orig_x = pixmap_x / scale
            orig_y = pixmap_y / scale
            # Use direct y (no flip)
            pixel_value = None
            try:
                if (0 <= orig_x < img_w and 0 <= orig_y < img_h):
                    pixel_value = self.parent_viewer.image_data[int(orig_y), int(orig_x)]
            except Exception:
                pixel_value = None
            # Format sky coordinates
            coord_text = ""
            if pixel_value is not None:
                pixel_str = f"({orig_x:.1f}, {orig_y:.1f})"
            else:
                pixel_str = "(--)"
            try:
                sky_coords = self.parent_viewer.wcs.pixel_to_world(orig_x, orig_y)
                if hasattr(sky_coords, 'ra') and hasattr(sky_coords, 'dec'):
                    ra = sky_coords.ra.to_string(unit='hourangle', precision=1, pad=True)
                    dec = sky_coords.dec.to_string(unit='deg', precision=1, alwayssign=True, pad=True)
                else:
                    ra = sky_coords[0].to_string(unit='hourangle', precision=1, pad=True)
                    dec = sky_coords[1].to_string(unit='deg', precision=1, alwayssign=True, pad=True)
                coord_text = f"{ra} {dec}  {pixel_str}"
            except Exception:
                coord_text = f"WCS error  {pixel_str}"
            # Update status bar labels
            if hasattr(self.parent_viewer, 'status_coord_label'):
                self.parent_viewer.status_coord_label.setText(coord_text)
            if hasattr(self.parent_viewer, 'status_pixel_label'):
                if pixel_value is not None:
                    self.parent_viewer.status_pixel_label.setText(str(pixel_value))
                else:
                    self.parent_viewer.status_pixel_label.setText("--")
        else:
            if hasattr(self.parent_viewer, 'status_coord_label'):
                self.parent_viewer.status_coord_label.setText("No WCS - coordinates unavailable")
            if hasattr(self.parent_viewer, 'status_pixel_label'):
                self.parent_viewer.status_pixel_label.setText("--")

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._zoom_region_mode and self._zoom_region_active and event.button() == Qt.MouseButton.LeftButton:
            self._zoom_region_end = event.pos()
            self._zoom_region_active = False
            self.setCursor(self._custom_cross_cursor)
            # Convert the selection rectangle to image coordinates and call parent
            rect = self._get_zoom_region_rect()
            if rect is not None and self.parent_viewer is not None:
                (img_x0, img_y0), (img_x1, img_y1) = rect
                self.parent_viewer.zoom_to_region(img_x0, img_y0, img_x1, img_y1)
            self._zoom_region_start = None
            self._zoom_region_end = None
            self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.parent_viewer:
            self.panning = False
            self.pan_timer.stop()
            # Always restore the custom cross cursor after panning
            self.setCursor(self._custom_cross_cursor)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if self.parent_viewer:
            if event.key() == Qt.Key.Key_Plus or event.key() == Qt.Key.Key_Equal:
                self.parent_viewer.zoom_in_at_center()
            elif event.key() == Qt.Key.Key_Minus:
                self.parent_viewer.zoom_out_at_center()
            elif event.key() == Qt.Key.Key_0:
                self.parent_viewer.reset_zoom()
            elif event.key() == Qt.Key.Key_O:
                self.parent_viewer.open_file()
        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        # Draw SIMBAD overlay if enabled
        if (
            self.parent_viewer and
            hasattr(self.parent_viewer, '_simbad_overlay') and
            self.parent_viewer._simbad_overlay and
            getattr(self.parent_viewer, '_overlay_visible', True)
        ):
            try:
                from lib.gui.viewer.overlay import SIMBADOverlay
                simbad_object, pixel_coords = self.parent_viewer._simbad_overlay
                pixmap = self.pixmap()
                if pixmap is None or self.parent_viewer.image_data is None:
                    return
                img_h, img_w = self.parent_viewer.image_data.shape
                pixmap_w = pixmap.width()
                pixmap_h = pixmap.height()
                label_w = self.width()
                label_h = self.height()
                scale_x = pixmap_w / img_w
                scale_y = pixmap_h / img_h
                scale = scale_x
                x_offset = (label_w - pixmap_w) // 2
                y_offset = (label_h - pixmap_h) // 2
                x_img, y_img = pixel_coords
                # Use direct y (no flip)
                x_disp = x_img * scale + x_offset
                y_disp = y_img * scale + y_offset
                overlay = SIMBADOverlay(simbad_object.name, (x_disp, y_disp))
                painter = QPainter(self)
                overlay.draw(painter)
                painter.end()
            except Exception as e:
                pass
        # Draw SIMBAD field overlay if enabled
        if (
            self.parent_viewer and
            hasattr(self.parent_viewer, '_simbad_field_overlay') and
            self.parent_viewer._simbad_field_overlay and
            getattr(self.parent_viewer, '_overlay_visible', True)
        ):
            try:
                from lib.gui.viewer.overlay import SIMBADFieldOverlay
                simbad_objects, pixel_coords_list = self.parent_viewer._simbad_field_overlay
                pixmap = self.pixmap()
                if pixmap is None or self.parent_viewer.image_data is None:
                    return
                img_h, img_w = self.parent_viewer.image_data.shape
                pixmap_w = pixmap.width()
                pixmap_h = pixmap.height()
                label_w = self.width()
                label_h = self.height()
                scale_x = pixmap_w / img_w
                scale_y = pixmap_h / img_h
                scale = scale_x
                x_offset = (label_w - pixmap_w) // 2
                y_offset = (label_h - pixmap_h) // 2
                pixel_coords_disp = [
                    (x * scale + x_offset, y * scale + y_offset)
                    for (x, y) in pixel_coords_list
                ]
                highlight_index = getattr(self.parent_viewer, '_simbad_field_highlight_index', None)
                overlay = SIMBADFieldOverlay(simbad_objects, pixel_coords_disp, highlight_index=highlight_index)
                painter = QPainter(self)
                overlay.draw(painter)
                painter.end()
            except Exception as e:
                pass
        # Draw SSO overlay if enabled
        if (
            self.parent_viewer and
            hasattr(self.parent_viewer, '_sso_overlay') and
            self.parent_viewer._sso_overlay and
            getattr(self.parent_viewer, '_overlay_visible', True)
        ):
            try:
                from lib.gui.viewer.overlay import SSOOverlay
                sso_objects, pixel_coords_list = self.parent_viewer._sso_overlay
                pixmap = self.pixmap()
                if pixmap is None or self.parent_viewer.image_data is None:
                    return
                img_h, img_w = self.parent_viewer.image_data.shape
                pixmap_w = pixmap.width()
                pixmap_h = pixmap.height()
                label_w = self.width()
                label_h = self.height()
                scale_x = pixmap_w / img_w
                scale_y = pixmap_h / img_h
                scale = scale_x
                x_offset = (label_w - pixmap_w) // 2
                y_offset = (label_h - pixmap_h) // 2
                pixel_coords_disp = [
                    (x * scale + x_offset, y * scale + y_offset)
                    for (x, y) in pixel_coords_list
                ]
                highlight_index = getattr(self.parent_viewer, '_sso_highlight_index', None)
                overlay = SSOOverlay(sso_objects, pixel_coords_disp, highlight_index=highlight_index)
                painter = QPainter(self)
                overlay.draw(painter)
                painter.end()
            except Exception as e:
                pass
        # Draw Gaia overlay if enabled
        if (
            self.parent_viewer and
            hasattr(self.parent_viewer, '_gaia_overlay') and
            self.parent_viewer._gaia_overlay and
            getattr(self.parent_viewer, '_overlay_visible', True)
        ):
            try:
                from lib.gui.viewer.overlay import GaiaOverlay
                gaia_objects, pixel_coords_list = self.parent_viewer._gaia_overlay
                pixmap = self.pixmap()
                if pixmap is None or self.parent_viewer.image_data is None:
                    return
                img_h, img_w = self.parent_viewer.image_data.shape
                pixmap_w = pixmap.width()
                pixmap_h = pixmap.height()
                label_w = self.width()
                label_h = self.height()
                scale_x = pixmap_w / img_w
                scale_y = pixmap_h / img_h
                scale = scale_x
                x_offset = (label_w - pixmap_w) // 2
                y_offset = (label_h - pixmap_h) // 2
                pixel_coords_disp = [
                    (x * scale + x_offset, y * scale + y_offset)
                    for (x, y) in pixel_coords_list
                ]
                highlight_index = getattr(self.parent_viewer, '_gaia_highlight_index', None)
                overlay = GaiaOverlay(gaia_objects, pixel_coords_disp, highlight_index=highlight_index)
                painter = QPainter(self)
                overlay.draw(painter)
                painter.end()
            except Exception as e:
                pass
        # Draw ephemeris marker overlay if present
        if (
            self.parent_viewer and
            hasattr(self.parent_viewer, '_ephemeris_overlay') and
            self.parent_viewer._ephemeris_overlay is not None and
            getattr(self.parent_viewer, '_overlay_visible', True)
        ):
            try:
                pixmap = self.pixmap()
                if pixmap is None or self.parent_viewer.image_data is None:
                    return
                img_h, img_w = self.parent_viewer.image_data.shape
                pixmap_w = pixmap.width()
                pixmap_h = pixmap.height()
                label_w = self.width()
                label_h = self.height()
                scale_x = pixmap_w / img_w
                scale_y = pixmap_h / img_h
                scale = scale_x
                x_offset = (label_w - pixmap_w) // 2
                y_offset = (label_h - pixmap_h) // 2
                _, (x_img, y_img) = self.parent_viewer._ephemeris_overlay
                x_disp = x_img * scale + x_offset
                y_disp = y_img * scale + y_offset
                painter = QPainter(self)
                pen = QPen(QColor(255, 0, 0))
                pen.setWidth(1)  # Thinner lines
                painter.setPen(pen)
                radius = 24  # Twice as long as before
                gap = 6      # Length of the gap at the center
                # Draw a red cross with missing center (4 segments)
                # Horizontal segments
                painter.drawLine(int(x_disp - radius), int(y_disp), int(x_disp - gap), int(y_disp))
                painter.drawLine(int(x_disp + gap), int(y_disp), int(x_disp + radius), int(y_disp))
                # Vertical segments
                painter.drawLine(int(x_disp), int(y_disp - radius), int(x_disp), int(y_disp - gap))
                painter.drawLine(int(x_disp), int(y_disp + gap), int(x_disp), int(y_disp + radius))
                painter.end()
            except Exception as e:
                pass
        # Draw zoom region rectangle if active or if selection exists
        if self._zoom_region_mode and (self._zoom_region_active or (self._zoom_region_start and self._zoom_region_end)):
            painter = QPainter(self)
            pen = QPen(QColor(0, 180, 255), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            start = self._zoom_region_start
            end = self._zoom_region_end
            if start and end:
                rect = QRect(start, end)
                painter.drawRect(rect.normalized())
            painter.end()
        # Remove info insert drawing; now handled by status bar 

    def _get_zoom_region_rect(self):
        # Returns ((img_x0, img_y0), (img_x1, img_y1)) in image coordinates, or None
        if self._zoom_region_start is None or self._zoom_region_end is None:
            return None
        pixmap = self.pixmap()
        if pixmap is None or self.parent_viewer is None or self.parent_viewer.image_data is None:
            return None
        img_h, img_w = self.parent_viewer.image_data.shape
        pixmap_w = pixmap.width()
        pixmap_h = pixmap.height()
        label_w = self.width()
        label_h = self.height()
        scale_x = pixmap_w / img_w
        scale_y = pixmap_h / img_h
        scale = scale_x
        x_offset = (label_w - pixmap_w) // 2
        y_offset = (label_h - pixmap_h) // 2
        def to_img_coords(qpoint):
            px = qpoint.x() - x_offset
            py = qpoint.y() - y_offset
            img_x = px / scale
            img_y = py / scale
            return (img_x, img_y)
        return to_img_coords(self._zoom_region_start), to_img_coords(self._zoom_region_end)

class SIMBADOverlay:
    def __init__(self, name, pixel_coords, color=QColor(0, 255, 0), radius=12):
        self.name = name
        self.pixel_coords = pixel_coords  # (x, y)
        self.color = color
        self.radius = radius  # radius of the circle

    def draw(self, painter: QPainter):
        x, y = self.pixel_coords
        pen = QPen(self.color)
        pen.setWidth(3)
        painter.setPen(pen)
        # Draw circle
        painter.drawEllipse(int(x - self.radius), int(y - self.radius), 
                           int(2 * self.radius), int(2 * self.radius))
        # Draw name text to the right of the circle
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(self.color)
        # Position text to the right of the circle with some spacing
        text_x = int(x + self.radius + 8)
        text_y = int(y + 4)  # Slightly below center for better alignment
        painter.drawText(text_x, text_y, self.name) 

class SSOOverlay:
    def __init__(self, sso_objects, pixel_coords_list, color=QColor(255, 200, 0), radius=10, highlight_index=None):
        self.sso_objects = sso_objects  # List of SolarSystemObject
        self.pixel_coords_list = pixel_coords_list  # List of (x, y)
        self.color = color
        self.radius = radius
        self.highlight_index = highlight_index

    def _whiten_color(self, color, factor=0.5):
        # Blend color with white by the given factor (0.0 = original, 1.0 = white)
        r = int(color.red() + (255 - color.red()) * factor)
        g = int(color.green() + (255 - color.green()) * factor)
        b = int(color.blue() + (255 - color.blue()) * factor)
        return QColor(r, g, b)

    def draw(self, painter: QPainter):
        font = QFont()
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        for idx, (obj, (x, y)) in enumerate(zip(self.sso_objects, self.pixel_coords_list)):
            if self.highlight_index is not None and idx == self.highlight_index:
                color = QColor(255, 0, 0)  # Red for highlight
                pen = QPen(color)
                pen.setWidth(3)
            else:
                color = self.color
                pen = QPen(color)
                pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(int(x - self.radius), int(y - self.radius), int(2 * self.radius), int(2 * self.radius))
            # Draw name to the right
            text_x = int(x + self.radius + 4)
            text_y = int(y + 4)
            painter.drawText(text_x, text_y, obj.name)


class SIMBADFieldOverlay:
    """Overlay for displaying multiple SIMBAD objects found in the field."""
    def __init__(self, simbad_objects, pixel_coords_list, color=QColor(0, 255, 0), radius=8, highlight_index=None):
        self.simbad_objects = simbad_objects  # List of SIMBADObject
        self.pixel_coords_list = pixel_coords_list  # List of (x, y)
        self.color = color
        self.radius = radius
        self.highlight_index = highlight_index

    def draw(self, painter: QPainter):
        font = QFont()
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        
        for idx, (obj, (x, y)) in enumerate(zip(self.simbad_objects, self.pixel_coords_list)):
            if self.highlight_index is not None and idx == self.highlight_index:
                color = QColor(255, 0, 0)  # Red for highlight
                pen = QPen(color)
                pen.setWidth(3)
            else:
                color = self.color
                pen = QPen(color)
                pen.setWidth(2)
            
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(int(x - self.radius), int(y - self.radius), int(2 * self.radius), int(2 * self.radius))
            
            # Draw name to the right
            text_x = int(x + self.radius + 4)
            text_y = int(y + 4)
            painter.drawText(text_x, text_y, obj.name)


class GaiaOverlay:
    """Overlay for displaying multiple Gaia stars found in the field."""
    def __init__(self, gaia_objects, pixel_coords_list, color=QColor(0, 255, 255), radius=6, highlight_index=None):
        self.gaia_objects = gaia_objects  # List of GaiaObject
        self.pixel_coords_list = pixel_coords_list  # List of (x, y)
        self.color = color
        self.radius = radius
        self.highlight_index = highlight_index

    def draw(self, painter: QPainter):
        font = QFont()
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        
        for idx, (obj, (x, y)) in enumerate(zip(self.gaia_objects, self.pixel_coords_list)):
            if self.highlight_index is not None and idx == self.highlight_index:
                color = QColor(255, 0, 0)  # Red for highlight
                pen = QPen(color)
                pen.setWidth(3)
            else:
                color = self.color  # Use consistent color for all stars
                pen = QPen(color)
                pen.setWidth(2)
            
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(int(x - self.radius), int(y - self.radius), int(2 * self.radius), int(2 * self.radius))
            
            # Draw source ID to the right for highlighted objects
            if self.highlight_index is not None and idx == self.highlight_index:
                text_x = int(x + self.radius + 4)
                text_y = int(y + 4)
                painter.drawText(text_x, text_y, obj.source_id)


class OverlayMixin:
    """Mixin class providing overlay functionality for the FITS viewer."""
    
    def toggle_overlay_visibility(self):
        """Toggle the visibility of all overlays."""
        self._overlay_visible = not self._overlay_visible
        # Temporarily block signals to avoid circular dependency
        self.overlay_toggle_action.blockSignals(True)
        self.overlay_toggle_action.setChecked(self._overlay_visible)
        self.overlay_toggle_action.blockSignals(False)
        self.image_label.update()

    def update_overlay_button_visibility(self):
        """Update the overlay button visibility based on whether overlays are available."""
        self.toolbar_controller.update_overlay_button_visibility()

    def on_sso_row_selected(self, row_index):
        """Handle selection of a Solar System Object row."""
        self._sso_highlight_index = row_index
        self.image_label.update()

    def on_simbad_field_row_selected(self, row_index):
        """Handle selection of a SIMBAD field object row."""
        self._simbad_field_highlight_index = row_index
        self.image_label.update()

    def on_gaia_row_selected(self, row_index):
        """Handle selection of a Gaia star row."""
        self._gaia_highlight_index = row_index
        self.image_label.update()

    def on_ephemeris_row_selected(self, row_index, ephemeris):
        """Handle selection of an ephemeris row and show marker at the predicted position."""
        # Save current brightness before switching
        self.histogram_controller.save_state_before_switch()
        # Save current viewport state before switching
        if hasattr(self, '_zoom'):
            self._last_zoom = self._zoom
        self._last_center = self._get_viewport_center()
        # Load the corresponding FITS file and add a marker at the ephemeris position
        if not (0 <= row_index < len(self.loaded_files)):
            return
        self.current_file_index = row_index
        self.load_fits(self.loaded_files[row_index], restore_view=True)
        self.update_close_button_visibility()
        # Set marker overlay for ephemeris position
        ra = ephemeris.get("RA", 0.0)
        dec = ephemeris.get("Dec", 0.0)
        if self.wcs is not None:
            from astropy.wcs.utils import skycoord_to_pixel
            from astropy.coordinates import SkyCoord
            import astropy.units as u
            skycoord = SkyCoord(ra*u.deg, dec*u.deg, frame='icrs')
            x, y = skycoord_to_pixel(skycoord, self.wcs)
            self._ephemeris_overlay = ((ra, dec), (x, y))
            self._show_ephemeris_marker((x, y))
        else:
            self._ephemeris_overlay = None
            self._show_ephemeris_marker(None)
        self.image_label.update()

    def _show_ephemeris_marker(self, pixel_coords):
        """Store the marker position for overlay drawing."""
        self._ephemeris_marker_coords = pixel_coords
        self._overlay_visible = True
        self.update_overlay_button_visibility()
        self.image_label.update() 