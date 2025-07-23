from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QCursor

class NavigationMixin:
    def __init__(self):
        self._zoom = 1.0
        self._zoom_step = 1.15
        self._min_zoom = 0.05
        self._max_zoom = 20.0
        self._orig_pixmap = None
        self._panning = False
        self._last_pan_pos = None
        self._pan_speed = 1.5  # Coefficient to make panning match cursor
        super().__init__()

    def wheelEvent(self, event):
        if not hasattr(self, 'image_label'):
            return super().wheelEvent(event)
        label = self.image_label
        # Do not set self._orig_pixmap here; it should be set by the viewer to the original image
        if self._orig_pixmap is None:
            return
        angle = event.angleDelta().y()
        if angle == 0:
            return
        if angle > 0:
            self._zoom = min(self._zoom * self._zoom_step, self._max_zoom)
        else:
            self._zoom = max(self._zoom / self._zoom_step, self._min_zoom)
        new_width = int(self._orig_pixmap.width() * self._zoom)
        new_height = int(self._orig_pixmap.height() * self._zoom)
        label.setFixedSize(new_width, new_height)
        label.setPixmap(self._orig_pixmap.scaled(new_width, new_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and hasattr(self, 'scroll_area'):
            self._panning = True
            self._last_pan_pos = event.position().toPoint()
            self.image_label.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and hasattr(self, 'scroll_area'):
            current_pos = event.position().toPoint()
            if self._last_pan_pos is None:
                self._last_pan_pos = current_pos
                event.accept()
                return
            delta = current_pos - self._last_pan_pos
            if delta.manhattanLength() == 0:
                event.accept()
                return
            hbar = self.scroll_area.horizontalScrollBar()
            vbar = self.scroll_area.verticalScrollBar()
            # Apply pan speed coefficient
            hbar.setValue(hbar.value() - int(delta.x() * self._pan_speed))
            vbar.setValue(vbar.value() - int(delta.y() * self._pan_speed))
            self._last_pan_pos = current_pos
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = False
            self._last_pan_pos = None
            # self.image_label.setCursor(Qt.CursorShape.ArrowCursor)  # Remove this line to allow custom cursor
            event.accept()
        else:
            super().mouseReleaseEvent(event) 