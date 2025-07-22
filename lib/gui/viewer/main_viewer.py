import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

import numpy as np
from astropy.io import fits
from PyQt6.QtWidgets import QApplication, QMainWindow, QScrollArea, QToolBar, QFileDialog
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QAction
from lib.gui_widgets import ImageLabel
from lib.gui_image_processing import create_image_object
from lib.gui.viewer.navigation import NavigationMixin
from lib.gui.common.header_viewer import HeaderViewer
from lib.fits.header import get_fits_header_as_json

class NoWheelScrollArea(QScrollArea):
    def wheelEvent(self, event):
        # Ignore wheel events so they are not used for scrolling
        event.ignore()

class SimpleFITSViewer(NavigationMixin, QMainWindow):
    def __init__(self, fits_path=None):
        super().__init__()
        self.setWindowTitle("Astropipes FITS Viewer")
        self.setGeometry(100, 100, 1000, 800)

        self.pixmap = None  # For ImageLabel compatibility
        self.wcs = None    # For ImageLabel compatibility
        self.image_data = None  # Store current image data
        self.stretch_mode = 'log'  # 'linear' or 'log', default to log
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self.toolbar)
        open_icon = QIcon.fromTheme("document-open")
        if open_icon.isNull():
            open_icon = QIcon.fromTheme("folder-open")
        load_action = QAction(open_icon, "Open FITS", self)
        load_action.setToolTip("Open FITS file")
        load_action.triggered.connect(self.open_file_dialog)
        self.toolbar.addAction(load_action)
        self.toolbar.widgetForAction(load_action).setFixedSize(32, 32)
        reset_zoom_action = QAction("reset zoom", self)
        reset_zoom_action.setToolTip("Reset zoom to 1:1")
        reset_zoom_action.triggered.connect(self.reset_zoom)
        self.toolbar.addAction(reset_zoom_action)
        self.toolbar.widgetForAction(reset_zoom_action).setFixedSize(80, 32)
        zoom_to_fit_action = QAction("zoom to fit", self)
        zoom_to_fit_action.setToolTip("Zoom to fit image in viewport")
        zoom_to_fit_action.triggered.connect(self.zoom_to_fit)
        self.toolbar.addAction(zoom_to_fit_action)
        self.toolbar.widgetForAction(zoom_to_fit_action).setFixedSize(90, 32)
        linear_action = QAction("0", self)
        linear_action.setToolTip("Linear histogram stretch")
        linear_action.triggered.connect(self.set_linear_stretch)
        self.toolbar.addAction(linear_action)
        self.toolbar.widgetForAction(linear_action).setFixedSize(32, 32)
        log_action = QAction("+", self)
        log_action.setToolTip("Logarithmic histogram stretch")
        log_action.triggered.connect(self.set_log_stretch)
        self.toolbar.addAction(log_action)
        self.toolbar.widgetForAction(log_action).setFixedSize(32, 32)
        self.header_button = QAction("FITS header", self)
        self.header_button.setToolTip("Show FITS header")
        self.header_button.setEnabled(False)
        self.header_button.triggered.connect(self.show_header_dialog)
        self.toolbar.addAction(self.header_button)
        self.toolbar.widgetForAction(self.header_button).setFixedSize(90, 32)
        self.scroll_area = NoWheelScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.setCentralWidget(self.scroll_area)
        self.image_label = ImageLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("QLabel { background-color: black; }")
        self.image_label.setText("No image loaded")
        self.scroll_area.setWidget(self.image_label)
        if fits_path:
            self._pending_zoom_to_fit = True
            self.load_fits(fits_path)

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open FITS file", "", "FITS files (*.fits *.fit *.fts);;All files (*)")
        if file_path:
            self.load_fits(file_path)

    def set_linear_stretch(self):
        self.stretch_mode = 'linear'
        self.update_image_display(keep_zoom=True)
        self.zoom_to_fit()

    def set_log_stretch(self):
        self.stretch_mode = 'log'
        self.update_image_display(keep_zoom=True)
        self.zoom_to_fit()

    def update_image_display(self, keep_zoom=False):
        if self.image_data is None:
            return
        # Save current zoom and center of view in image coordinates
        if keep_zoom:
            current_zoom = self._zoom if hasattr(self, '_zoom') else 1.0
        else:
            current_zoom = getattr(self, '_zoom', 1.0)
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()
        viewport_w = self.scroll_area.viewport().width()
        viewport_h = self.scroll_area.viewport().height()
        old_width = self.image_label.width()
        old_height = self.image_label.height()
        # Compute center of viewport in image coordinates
        if old_width > 0 and old_height > 0:
            center_x = hbar.value() + viewport_w // 2
            center_y = vbar.value() + viewport_h // 2
            rel_cx = center_x / old_width
            rel_cy = center_y / old_height
        else:
            rel_cx = rel_cy = 0.5
        if self.stretch_mode == 'linear':
            orig_pixmap = create_image_object(self.image_data)
        else:
            # Logarithmic stretch: scale data, then use create_image_object
            data = self.image_data.astype(float)
            data = np.where(data > 0, np.log10(data), 0)
            orig_pixmap = create_image_object(data)
        self._orig_pixmap = orig_pixmap  # Always set to the unscaled pixmap
        # Set the display pixmap according to current zoom
        new_width = int(orig_pixmap.width() * self._zoom)
        new_height = int(orig_pixmap.height() * self._zoom)
        display_pixmap = orig_pixmap.scaled(new_width, new_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(display_pixmap)
        self.image_label.setFixedSize(new_width, new_height)
        self.pixmap = orig_pixmap
        # Restore scroll position to keep the same view center
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()
        new_cx = int(rel_cx * new_width)
        new_cy = int(rel_cy * new_height)
        hbar.setValue(max(0, new_cx - viewport_w // 2))
        vbar.setValue(max(0, new_cy - viewport_h // 2))
        # If zoom mode is set to fit, update zoom
        if getattr(self, '_pending_zoom_to_fit', False):
            self._pending_zoom_to_fit = False
            self.zoom_to_fit()

    def reset_zoom(self):
        self._zoom = 1.0
        self.update_image_display(keep_zoom=False)

    def zoom_to_fit(self):
        if self.image_label.pixmap() is None:
            return
        viewport = self.scroll_area.viewport()
        pixmap = self._orig_pixmap
        if pixmap is None:
            return
        # Compute scale to fit
        scale_x = viewport.width() / pixmap.width()
        scale_y = viewport.height() / pixmap.height()
        self._zoom = min(scale_x, scale_y)
        # Update display
        new_width = int(pixmap.width() * self._zoom)
        new_height = int(pixmap.height() * self._zoom)
        self.image_label.setFixedSize(new_width, new_height)
        self.image_label.setPixmap(self._orig_pixmap.scaled(new_width, new_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def load_fits(self, fits_path):
        try:
            with fits.open(fits_path) as hdul:
                image_data = hdul[0].data
                # Use get_fits_header_as_json to get (value, comment) tuples
                self._current_header = get_fits_header_as_json(fits_path)
                if image_data is not None:
                    # Only display 2D images
                    if image_data.ndim == 2:
                        self.image_data = image_data
                        self._pending_zoom_to_fit = True
                        self.update_image_display(keep_zoom=False)
                        self.image_label.setText("")
                        self.setWindowTitle(f"Simple FITS Viewer - {fits_path}")
                        self.header_button.setEnabled(True)
                    else:
                        self.image_label.setText("FITS file is not a 2D image.")
                        self.image_data = None
                        self.header_button.setEnabled(False)
                else:
                    self.image_label.setText("No image data in FITS file.")
                    self.image_data = None
                    self.header_button.setEnabled(False)
        except Exception as e:
            self.image_label.setText(f"Error loading FITS: {e}")
            self.image_data = None
            self.header_button.setEnabled(False)

    def show_header_dialog(self):
        if hasattr(self, '_current_header') and self._current_header:
            dlg = HeaderViewer(self._current_header, self)
            dlg.exec()

def main():
    fits_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication(sys.argv)
    viewer = SimpleFITSViewer(fits_path)
    viewer.show()
    # Ensure zoom to fit is called after the window is visible
    QTimer.singleShot(0, viewer.zoom_to_fit)
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 