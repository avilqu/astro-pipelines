import sys
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.time import Time
from PyQt6.QtWidgets import QLabel, QScrollArea, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QMessageBox
from PyQt6.QtCore import Qt, QPoint, QTimer, QPointF
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

    def mousePressEvent(self, event: QMouseEvent):
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
        target_h = max(0, min(self.target_scroll_pos.x(), h_scroll.maximum()))
        target_v = max(0, min(self.target_scroll_pos.y(), v_scroll.maximum()))
        current_h = h_scroll.value()
        current_v = v_scroll.value()
        interpolation_factor = 0.7
        new_h = int(current_h + (target_h - current_h) * interpolation_factor)
        new_v = int(current_v + (target_v - current_v) * interpolation_factor)
        new_h = max(0, min(new_h, h_scroll.maximum()))
        new_v = max(0, min(new_v, v_scroll.maximum()))
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
            # Format pixel value
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
        # Draw overlay if enabled
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
                x_disp = x_img * scale + x_offset
                y_disp = y_img * scale + y_offset
                overlay = SIMBADOverlay(simbad_object.name, (x_disp, y_disp))
                painter = QPainter(self)
                overlay.draw(painter)
                painter.end()
            except Exception as e:
                pass
        # Remove info insert drawing; now handled by status bar 

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