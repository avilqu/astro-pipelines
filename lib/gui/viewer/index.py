import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

import numpy as np
from astropy.io import fits
from PyQt6.QtWidgets import QApplication, QMainWindow, QScrollArea, QToolBar, QFileDialog, QDialog, QWidget, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QAction
from lib.gui.viewer.overlay import ImageLabel
from lib.gui.viewer.display import create_image_object
from lib.gui.viewer.navigation import NavigationMixin
from lib.gui.common.header_window import HeaderViewer
from lib.fits.header import get_fits_header_as_json
from lib.fits.catalogs import AstrometryCatalog
from PyQt6.QtWidgets import QStatusBar, QSizePolicy, QLabel
import config

class NoWheelScrollArea(QScrollArea):
    def wheelEvent(self, event):
        # Ignore wheel events so they are not used for scrolling
        event.ignore()

class SimpleFITSViewer(NavigationMixin, QMainWindow):
    def __init__(self, fits_path=None):
        super().__init__()
        self.setWindowTitle("Astropipes FITS Viewer")
        self.setGeometry(100, 100, 1000, 800)

        # --- Multi-file support ---
        self.loaded_files = []  # List of file paths
        self.current_file_index = -1  # Index of currently displayed file
        self._preloaded_fits = {}  # path -> (image_data, header, wcs)

        self.astrometry_catalog = AstrometryCatalog()
        self.pixmap = None  # For ImageLabel compatibility
        self.wcs = None    # For ImageLabel compatibility
        self.image_data = None  # Store current image data
        self.stretch_mode = 'log'  # 'linear' or 'log', default to log
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(False)  # Disable moving the toolbar
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)  # Remove handle visual
        self.addToolBar(self.toolbar)

        # --- Navigation buttons grouped at right end ---
        from PyQt6.QtGui import QIcon
        from PyQt6.QtWidgets import QLabel as QtLabel, QWidget, QHBoxLayout, QSpacerItem, QSizePolicy, QToolButton
        left_icon = QIcon.fromTheme("go-previous")
        if left_icon.isNull():
            left_icon = QIcon.fromTheme("arrow-left")
        self.prev_action = QAction(left_icon, "Previous", self)
        self.prev_action.setToolTip("Show previous FITS file")
        self.prev_action.triggered.connect(self.show_previous_file)
        right_icon = QIcon.fromTheme("go-next")
        if right_icon.isNull():
            right_icon = QIcon.fromTheme("arrow-right")
        self.next_action = QAction(right_icon, "Next", self)
        self.next_action.setToolTip("Show next FITS file")
        self.next_action.triggered.connect(self.show_next_file)
        self.image_count_label = QtLabel("- / -", self)
        self.image_count_label.setMinimumWidth(50)
        # Create a QWidget with QHBoxLayout to hold the navigation controls
        nav_widget = QWidget(self)
        from PyQt6.QtWidgets import QGridLayout
        nav_layout = QGridLayout()
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setHorizontalSpacing(4)
        # Previous button
        self.prev_button = QToolButton(self)
        self.prev_button.setDefaultAction(self.prev_action)
        self.prev_button.setFixedSize(32, 32)
        nav_layout.addWidget(self.prev_button, 0, 0)
        # Image count label (fixed width for e.g. '100 / 100')
        self.image_count_label.setFixedWidth(60)
        nav_layout.addWidget(self.image_count_label, 0, 1, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
        
        # Play/Pause button
        self.playing = False
        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(config.BLINK_PERIOD_MS)  # Use config value
        self.blink_timer.timeout.connect(self._blink_next_image)
        self.play_pause_button = QToolButton(self)
        self.play_icon = QIcon.fromTheme("media-playback-start")
        self.pause_icon = QIcon.fromTheme("media-playback-pause")
        if self.play_icon.isNull():
            self.play_icon = QIcon.fromTheme("play")
        if self.pause_icon.isNull():
            self.pause_icon = QIcon.fromTheme("pause")
        self.play_pause_button.setIcon(self.play_icon)
        self.play_pause_button.setToolTip("Play slideshow")
        self.play_pause_button.setFixedSize(32, 32)
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        nav_layout.addWidget(self.play_pause_button, 0, 2)
        # Next button (move to col 3)
        self.next_button = QToolButton(self)
        self.next_button.setDefaultAction(self.next_action)
        self.next_button.setFixedSize(32, 32)
        nav_layout.addWidget(self.next_button, 0, 3)
        nav_widget.setLayout(nav_layout)

        # --- Existing toolbar buttons (left side) ---
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
        # Add SIMBAD search button
        self.simbad_button = QAction("SIMBAD search", self)
        self.simbad_button.setToolTip("Search for an object in SIMBAD and overlay on image")
        self.simbad_button.setEnabled(True)
        self.simbad_button.triggered.connect(self.open_simbad_search_dialog)
        self.toolbar.addAction(self.simbad_button)
        self.toolbar.widgetForAction(self.simbad_button).setFixedSize(120, 32)
        # Overlay toggle action (toolbar)
        self.overlay_toggle_action = QAction("Toggle Overlay", self)
        self.overlay_toggle_action.setCheckable(True)
        self.overlay_toggle_action.setChecked(True)
        self.overlay_toggle_action.setVisible(False)
        self.overlay_toggle_action.triggered.connect(self.toggle_overlay_visibility)
        self.toolbar.addAction(self.overlay_toggle_action)

        # Add a spacer to push nav_widget to the right
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar.addWidget(spacer)
        self.toolbar.addWidget(nav_widget)
        # Remove sidebar and use only scroll_area as central widget
        self.scroll_area = NoWheelScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.setCentralWidget(self.scroll_area)
        self.image_label = ImageLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("QLabel { background-color: black; }")
        self.image_label.setText("No image loaded")
        self.scroll_area.setWidget(self.image_label)
        # Add default attributes for compatibility with ImageLabel
        self.bit_depth = None
        self.pixel_value_label = QLabel("--", self)
        self.pixel_value_label.setVisible(False)
        self.coord_label = QLabel("", self)
        self.coord_label.setVisible(False)
        self._overlay_visible = True
        if fits_path:
            self.open_and_add_file(fits_path)
        self.update_overlay_button_visibility()
        self.update_navigation_buttons()
        # Status bar: coordinates (left), pixel value (right)
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_coord_label = QLabel("No WCS - coordinates unavailable", self)
        self.status_coord_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.status_bar.addWidget(self.status_coord_label)
        self.status_pixel_label = QLabel("--", self)
        self.status_pixel_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.status_bar.addPermanentWidget(self.status_pixel_label)

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open FITS file", "", "FITS files (*.fits *.fit *.fts);;All files (*)")
        if file_path:
            self.open_and_add_file(file_path)

    def open_and_add_file(self, fits_path):
        # If already loaded, just switch to it
        if fits_path in self.loaded_files:
            self.current_file_index = self.loaded_files.index(fits_path)
            self.load_fits(fits_path)
        else:
            self.loaded_files.append(fits_path)
            self.current_file_index = len(self.loaded_files) - 1
            self._preload_fits_file(fits_path)
            self.load_fits(fits_path)
        self.update_navigation_buttons()
        self.update_image_count_label()

    def _preload_fits_file(self, fits_path):
        if fits_path in self._preloaded_fits:
            return
        try:
            from astropy.wcs import WCS
            with fits.open(fits_path) as hdul:
                image_data = hdul[0].data
                header = hdul[0].header
                try:
                    wcs = WCS(header)
                except Exception:
                    wcs = None
                self._preloaded_fits[fits_path] = (image_data, header, wcs)
        except Exception:
            self._preloaded_fits[fits_path] = (None, None, None)

    def show_previous_file(self):
        n = len(self.loaded_files)
        if n == 0:
            return
        # Loop around to the last file if at the first
        if self.current_file_index > 0:
            self.current_file_index -= 1
        else:
            self.current_file_index = n - 1
        self.load_fits(self.loaded_files[self.current_file_index])
        self.update_navigation_buttons()
        self.update_image_count_label()

    def show_next_file(self):
        n = len(self.loaded_files)
        if n == 0:
            return
        # Loop around to the first file if at the last
        if self.current_file_index < n - 1:
            self.current_file_index += 1
        else:
            self.current_file_index = 0
        self.load_fits(self.loaded_files[self.current_file_index])
        self.update_navigation_buttons()
        self.update_image_count_label()

    def update_navigation_buttons(self):
        n = len(self.loaded_files)
        # Always enable navigation if more than one file (for looping)
        enable = n > 1
        self.prev_action.setEnabled(enable)
        self.next_action.setEnabled(enable)
        self.prev_button.setEnabled(enable)
        self.next_button.setEnabled(enable)
        self.update_image_count_label()

    def update_image_count_label(self):
        n = len(self.loaded_files)
        if n == 0:
            self.image_count_label.setText("- / -")
        else:
            # Displayed as 1-based index
            self.image_count_label.setText(f"{self.current_file_index + 1} / {n}")

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
        # Set scale_factor for coordinate conversion
        self.scale_factor = self._zoom if hasattr(self, '_zoom') else 1.0
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
            # Use preloaded data if available
            if fits_path in self._preloaded_fits:
                image_data, header, wcs = self._preloaded_fits[fits_path]
            else:
                from astropy.wcs import WCS
                with fits.open(fits_path) as hdul:
                    image_data = hdul[0].data
                    header = hdul[0].header
                    try:
                        wcs = WCS(header)
                    except Exception:
                        wcs = None
                    self._preloaded_fits[fits_path] = (image_data, header, wcs)
            self._current_header = get_fits_header_as_json(fits_path)
            self.wcs = wcs
            if image_data is not None:
                if image_data.ndim == 2:
                    self.image_data = image_data
                    self._pending_zoom_to_fit = True
                    self.update_image_display(keep_zoom=False)
                    self.image_label.setText("")
                    self.setWindowTitle(f"Astropipes FITS Viewer - {fits_path}")
                    self.header_button.setEnabled(True)
                else:
                    self.image_label.setText("FITS file is not a 2D image.")
                    self.image_data = None
                    self.header_button.setEnabled(False)
            else:
                self.image_label.setText("No image data in FITS file.")
                self.image_data = None
                self.header_button.setEnabled(False)
            self._simbad_overlay = None
            self._overlay_visible = True
            self.update_overlay_button_visibility()
        except Exception as e:
            self.image_label.setText(f"Error loading FITS: {e}")
            self.image_data = None
            self.header_button.setEnabled(False)
            self._simbad_overlay = None
            self._overlay_visible = True
            self.update_overlay_button_visibility()
        self.update_navigation_buttons()
        self.update_image_count_label()

    def show_header_dialog(self):
        if hasattr(self, '_current_header') and self._current_header:
            dlg = HeaderViewer(self._current_header, self)
            dlg.exec()

    def toggle_overlay_visibility(self):
        self._overlay_visible = not self._overlay_visible
        self.overlay_toggle_action.setChecked(self._overlay_visible)
        self.image_label.update()

    def update_overlay_button_visibility(self):
        has_overlay = hasattr(self, '_simbad_overlay') and self._simbad_overlay is not None
        self.overlay_toggle_action.setVisible(has_overlay)
        if has_overlay:
            self.overlay_toggle_action.setChecked(self._overlay_visible)

    def open_simbad_search_dialog(self):
        from lib.gui.viewer.display import SIMBADSearchDialog
        dlg = SIMBADSearchDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result:
            simbad_object, pixel_coords = dlg.result
            # Store overlay info for drawing
            self._simbad_overlay = (simbad_object, pixel_coords)
            self._overlay_visible = True
            self.update_overlay_button_visibility()
            self.image_label.update()  # Trigger repaint
        else:
            self.update_overlay_button_visibility()

    def toggle_play_pause(self):
        if not self.playing:
            if len(self.loaded_files) > 1:
                self.playing = True
                self.play_pause_button.setIcon(self.pause_icon)
                self.play_pause_button.setToolTip("Pause slideshow")
                self.blink_timer.start()
        else:
            self.playing = False
            self.play_pause_button.setIcon(self.play_icon)
            self.play_pause_button.setToolTip("Play slideshow")
            self.blink_timer.stop()

    def _blink_next_image(self):
        if len(self.loaded_files) > 1:
            self.show_next_file()

def main():
    fits_paths = sys.argv[1:] if len(sys.argv) > 1 else []
    app = QApplication(sys.argv)
    viewer = SimpleFITSViewer()
    if fits_paths:
        for i, path in enumerate(fits_paths):
            viewer.open_and_add_file(path)
        # Show the first file
        if viewer.loaded_files:
            viewer.current_file_index = 0
            viewer.load_fits(viewer.loaded_files[0])
            viewer.update_navigation_buttons()
    viewer.show()
    # Ensure zoom to fit is called after the window is visible
    QTimer.singleShot(0, viewer.zoom_to_fit)
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 