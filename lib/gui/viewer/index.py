import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

import numpy as np
from astropy.io import fits
from PyQt6.QtWidgets import QApplication, QMainWindow, QScrollArea, QToolBar, QFileDialog, QDialog, QWidget, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QAction
from lib.gui.viewer.overlay import ImageLabel
from lib.gui.viewer.display import create_image_object
from lib.gui.viewer.navigation import NavigationMixin
from lib.gui.common.header_window import HeaderViewer
from lib.fits.header import get_fits_header_as_json
from lib.fits.catalogs import AstrometryCatalog
from PyQt6.QtWidgets import QStatusBar, QSizePolicy, QLabel, QMessageBox, QProgressDialog
import config
from lib.fits.align import check_all_have_wcs, check_pixel_scales_match, compute_padded_reference_wcs, reproject_images_to_common_wcs
from PyQt6.QtWidgets import QFrame

def make_toolbar_separator(parent):
    sep = QFrame(parent)
    sep.setFixedWidth(8)  # Give it a little width for margin
    sep.setFixedHeight(32)  # Match your toolbar height
    sep.setStyleSheet("QFrame { border-left: 1px solid #777777; background: transparent; }")
    return sep

class NoWheelScrollArea(QScrollArea):
    def wheelEvent(self, event):
        # Ignore wheel events so they are not used for scrolling
        event.ignore()

class AlignmentWorker(QObject):
    progress = pyqtSignal(float)
    finished = pyqtSignal(list, object, int, int, list)  # aligned_datas, common_wcs, new_nx, new_ny, headers
    error = pyqtSignal(str)

    def __init__(self, image_datas, headers, pad_x, pad_y):
        super().__init__()
        self.image_datas = image_datas
        self.headers = headers
        self.pad_x = pad_x
        self.pad_y = pad_y

    def run(self):
        try:
            from lib.fits.align import compute_padded_reference_wcs, reproject_images_to_common_wcs
            common_wcs, (new_nx, new_ny) = compute_padded_reference_wcs(self.headers, paddings=(self.pad_x, self.pad_y))
            aligned_datas = reproject_images_to_common_wcs(
                self.image_datas, self.headers, common_wcs, (new_ny, new_nx), progress_callback=self.progress.emit
            )
            self.finished.emit(aligned_datas, common_wcs, new_nx, new_ny, self.headers)
        except Exception as e:
            self.error.emit(str(e))

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
        self.toolbar.setStyleSheet("QToolBar { background: #222222; }")
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

        self.toolbar.addWidget(make_toolbar_separator(self))

        reset_zoom_action = QAction(QIcon.fromTheme("zoom-original"), "", self)
        reset_zoom_action.setToolTip("Reset zoom to 1:1")
        reset_zoom_action.triggered.connect(self.reset_zoom)
        self.toolbar.addAction(reset_zoom_action)
        self.toolbar.widgetForAction(reset_zoom_action).setFixedSize(32, 32)
        zoom_to_fit_action = QAction(QIcon.fromTheme("zoom-fit-width"), "", self)
        zoom_to_fit_action.setToolTip("Zoom to fit image in viewport")
        zoom_to_fit_action.triggered.connect(self.zoom_to_fit)
        self.toolbar.addAction(zoom_to_fit_action)
        self.toolbar.widgetForAction(zoom_to_fit_action).setFixedSize(32, 32)
        
        self.toolbar.addWidget(make_toolbar_separator(self))

        linear_action = QAction(QIcon.fromTheme("view-object-histogram-linear-symbolic"), "", self)
        linear_action.setToolTip("Linear histogram stretch")
        linear_action.triggered.connect(self.set_linear_stretch)
        self.toolbar.addAction(linear_action)
        self.toolbar.widgetForAction(linear_action).setFixedSize(32, 32)
        log_action = QAction(QIcon.fromTheme("view-object-histogram-logarithmic"), "", self)
        log_action.setToolTip("Logarithmic histogram stretch")
        log_action.triggered.connect(self.set_log_stretch)
        self.toolbar.addAction(log_action)
        self.toolbar.widgetForAction(log_action).setFixedSize(32, 32)

        # Add brightness -/+ buttons (not related to sigma clipping)
        from PyQt6.QtWidgets import QToolButton
        self.brightness_minus_button = QToolButton(self)
        self.brightness_minus_button.setText("-")
        self.brightness_minus_button.setToolTip("Darken image")
        self.brightness_minus_button.setFixedSize(32, 32)
        self.brightness_minus_button.clicked.connect(self.increase_display_min)
        self.toolbar.addWidget(self.brightness_minus_button)
        self.brightness_plus_button = QToolButton(self)
        self.brightness_plus_button.setText("+")
        self.brightness_plus_button.setToolTip("Brighten image")
        self.brightness_plus_button.setFixedSize(32, 32)
        self.brightness_plus_button.clicked.connect(self.decrease_display_min)
        self.toolbar.addWidget(self.brightness_plus_button)

        # Add Clipping button
        self.clipping_action =  QAction(QIcon.fromTheme("arrow-up-double"), "", self)
        self.clipping_action.setCheckable(True)
        self.clipping_action.setChecked(False) # Default to off
        self.clipping_action.setToolTip(f"Toggle sigma clipping for display stretch (sigma={3.0})")
        self.clipping_action.triggered.connect(self.toggle_clipping)
        self.toolbar.addAction(self.clipping_action)
        self.toolbar.widgetForAction(self.clipping_action).setFixedSize(32, 32)
        
        self.toolbar.addWidget(make_toolbar_separator(self))
        
        self.header_button = QAction(QIcon.fromTheme("view-financial-list"), "", self)
        self.header_button.setToolTip("Show FITS header")
        self.header_button.setEnabled(False)
        self.header_button.triggered.connect(self.show_header_dialog)
        self.toolbar.addAction(self.header_button)
        self.toolbar.widgetForAction(self.header_button).setFixedSize(32, 32)

        # Add SIMBAD search button
        self.simbad_button = QAction(QIcon.fromTheme("file-search-symbolic"), "", self)
        self.simbad_button.setToolTip("Search for an object in SIMBAD and overlay on image")
        self.simbad_button.setEnabled(True)
        self.simbad_button.triggered.connect(self.open_simbad_search_dialog)
        self.toolbar.addAction(self.simbad_button)
        self.toolbar.widgetForAction(self.simbad_button).setFixedSize(32, 32)
        # Overlay toggle action (toolbar)
        self.overlay_toggle_action = QAction("Toggle Overlay", self)
        self.overlay_toggle_action.setCheckable(True)
        self.overlay_toggle_action.setChecked(True)
        self.overlay_toggle_action.setVisible(False)
        self.overlay_toggle_action.triggered.connect(self.toggle_overlay_visibility)
        self.toolbar.addAction(self.overlay_toggle_action)

        # Add a spacer to push navigation elements to the right
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar.addWidget(spacer)
        
        # Add Align button (only visible if >1 image loaded) - moved to right side
        self.align_action = QAction(QIcon.fromTheme("image-rotate-symbolic"), "", self)
        self.align_action.setToolTip("Align all images using WCS")
        self.align_action.setVisible(False)
        self.align_action.triggered.connect(self.align_images)
        self.toolbar.addAction(self.align_action)
        self.toolbar.widgetForAction(self.align_action).setFixedSize(32, 32)
        
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
        self._zoom = 1.0  # Track current zoom level
        self._last_center = None  # Track last center (in image coordinates)
        self.clipping_enabled = False
        self.display_min = None
        self.display_max = None
        self.sigma_clip = 3.0
        if fits_path:
            self.open_and_add_file(fits_path)
        self.update_overlay_button_visibility()
        self.update_navigation_buttons()
        self.update_align_button_visibility()
        self.update_display_minmax_tooltips() # Initialize tooltips
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

    def _get_viewport_center(self):
        # Returns the center of the viewport in image coordinates (x, y)
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()
        viewport_w = self.scroll_area.viewport().width()
        viewport_h = self.scroll_area.viewport().height()
        img_w = self.image_label.width()
        img_h = self.image_label.height()
        if img_w > 0 and img_h > 0:
            center_x = hbar.value() + viewport_w // 2
            center_y = vbar.value() + viewport_h // 2
            # Convert to image coordinates
            img_cx = int(center_x / self._zoom)
            img_cy = int(center_y / self._zoom)
            return (img_cx, img_cy)
        return None

    def _set_viewport_center(self, img_cx, img_cy):
        # Centers the viewport on (img_cx, img_cy) in image coordinates
        new_width = self.image_label.width()
        new_height = self.image_label.height()
        viewport_w = self.scroll_area.viewport().width()
        viewport_h = self.scroll_area.viewport().height()
        if new_width > 0 and new_height > 0:
            center_x = int(img_cx * self._zoom)
            center_y = int(img_cy * self._zoom)
            hbar = self.scroll_area.horizontalScrollBar()
            vbar = self.scroll_area.verticalScrollBar()
            hbar.setValue(max(0, center_x - viewport_w // 2))
            vbar.setValue(max(0, center_y - viewport_h // 2))

    def open_and_add_file(self, fits_path):
        # Save zoom and center before switching
        if self.image_data is not None:
            self._last_zoom = self._zoom
            self._last_center = self._get_viewport_center()
        else:
            self._last_zoom = 1.0
            self._last_center = None
        # If already loaded, just switch to it
        if fits_path in self.loaded_files:
            self.current_file_index = self.loaded_files.index(fits_path)
            self.load_fits(fits_path, restore_view=True)
        else:
            self.loaded_files.append(fits_path)
            self.current_file_index = len(self.loaded_files) - 1
            self._preload_fits_file(fits_path)
            self.load_fits(fits_path, restore_view=True)
        self.update_navigation_buttons()
        self.update_image_count_label()
        self.update_align_button_visibility()

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
        # Save zoom and center before switching
        if self.image_data is not None:
            self._last_zoom = self._zoom
            self._last_center = self._get_viewport_center()
        else:
            self._last_zoom = 1.0
            self._last_center = None
        n = len(self.loaded_files)
        if n == 0:
            return
        # Loop around to the last file if at the first
        if self.current_file_index > 0:
            self.current_file_index -= 1
        else:
            self.current_file_index = n - 1
        self.load_fits(self.loaded_files[self.current_file_index], restore_view=True)
        self.update_navigation_buttons()
        self.update_image_count_label()
        self.update_align_button_visibility()

    def show_next_file(self):
        # Save zoom and center before switching
        if self.image_data is not None:
            self._last_zoom = self._zoom
            self._last_center = self._get_viewport_center()
        else:
            self._last_zoom = 1.0
            self._last_center = None
        n = len(self.loaded_files)
        if n == 0:
            return
        # Loop around to the first file if at the last
        if self.current_file_index < n - 1:
            self.current_file_index += 1
        else:
            self.current_file_index = 0
        self.load_fits(self.loaded_files[self.current_file_index], restore_view=True)
        self.update_navigation_buttons()
        self.update_image_count_label()
        self.update_align_button_visibility()

    def update_navigation_buttons(self):
        n = len(self.loaded_files)
        # Hide navigation elements if only one or no files loaded
        visible = n > 1
        self.prev_action.setVisible(visible)
        self.next_action.setVisible(visible)
        self.prev_button.setVisible(visible)
        self.next_button.setVisible(visible)
        self.play_pause_button.setVisible(visible)
        self.image_count_label.setVisible(visible)
        self.update_image_count_label()

    def update_image_count_label(self):
        n = len(self.loaded_files)
        if n == 0:
            self.image_count_label.setText("- / -")
        else:
            # Displayed as 1-based index
            self.image_count_label.setText(f"{self.current_file_index + 1} / {n}")

    def increase_display_min(self):
        # Make image darker by increasing display_min
        if self.display_min is None or self.display_max is None:
            auto_min, auto_max = self._get_auto_display_minmax()
            self.display_min = auto_min
            self.display_max = auto_max
        self.display_min += self._get_display_min_step()
        self.update_image_display(keep_zoom=True)
        self.update_display_minmax_tooltips()

    def decrease_display_min(self):
        # Make image brighter by decreasing display_min
        if self.display_min is None or self.display_max is None:
            auto_min, auto_max = self._get_auto_display_minmax()
            self.display_min = auto_min
            self.display_max = auto_max
        self.display_min -= self._get_display_min_step()
        self.update_image_display(keep_zoom=True)
        self.update_display_minmax_tooltips()

    def _get_auto_display_minmax(self):
        # Compute the default min/max as would be used by create_image_object
        if self.stretch_mode == 'log':
            data = self.image_data.astype(float)
            data = np.where(data > 0, np.log10(data), 0)
        else:
            data = self.image_data
        if self.clipping_enabled:
            finite_vals = data[np.isfinite(data)]
            if finite_vals.size > 0:
                mean = float(np.mean(finite_vals))
                std = float(np.std(finite_vals))
                return mean - self.sigma_clip * std, mean + self.sigma_clip * std
            else:
                return float(np.min(data)), float(np.max(data))
        else:
            finite_vals = data[np.isfinite(data)]
            if finite_vals.size > 0:
                histo = np.histogram(finite_vals, 60, None, True)
                return float(histo[1][0]), float(histo[1][-1])
            else:
                return float(np.min(data)), float(np.max(data))

    def _get_display_min_step(self):
        # Use a step based on the image stddev
        if self.stretch_mode == 'log':
            data = self.image_data.astype(float)
            data = np.where(data > 0, np.log10(data), 0)
        else:
            data = self.image_data
        if data is not None:
            finite_vals = data[np.isfinite(data)]
            if finite_vals.size > 0:
                return float(np.std(finite_vals)) * 0.4  # 4x bigger than before
        return 4.0

    def update_display_minmax_tooltips(self):
        self.brightness_minus_button.setToolTip(f"Darken image (min: {self.display_min})")
        self.brightness_plus_button.setToolTip(f"Brighten image (min: {self.display_min})")

    def set_linear_stretch(self):
        self.stretch_mode = 'linear'
        self.display_min = None
        self.display_max = None
        self.update_image_display(keep_zoom=True)
        self.zoom_to_fit()

    def set_log_stretch(self):
        self.stretch_mode = 'log'
        self.display_min = None
        self.display_max = None
        self.update_image_display(keep_zoom=True)
        self.zoom_to_fit()

    def toggle_clipping(self):
        self.clipping_enabled = not self.clipping_enabled
        self.clipping_action.setChecked(self.clipping_enabled)
        self.update_image_display(keep_zoom=True)

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
            orig_pixmap = create_image_object(self.image_data, display_min=self.display_min, display_max=self.display_max, clipping=self.clipping_enabled, sigma_clip=self.sigma_clip)
        else:
            data = self.image_data.astype(float)
            data = np.where(data > 0, np.log10(data), 0)
            orig_pixmap = create_image_object(data, display_min=self.display_min, display_max=self.display_max, clipping=self.clipping_enabled, sigma_clip=self.sigma_clip)
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

    def load_fits(self, fits_path, restore_view=False):
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
                    # Restore zoom and center if requested
                    if restore_view and hasattr(self, '_last_zoom') and self._last_zoom:
                        self._zoom = self._last_zoom
                    else:
                        self._zoom = 1.0
                    self._pending_zoom_to_fit = False
                    self.update_image_display(keep_zoom=True)
                    self.image_label.setText("")
                    self.setWindowTitle(f"Astropipes FITS Viewer - {fits_path}")
                    self.header_button.setEnabled(True)
                    self.display_min = None
                    self.display_max = None
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

    def update_align_button_visibility(self):
        # Hide align button if only one or no files loaded
        self.align_action.setVisible(len(self.loaded_files) > 1)

    def align_images(self):
        # Remove overlays before aligning
        self._simbad_overlay = None
        self._overlay_visible = True
        self.update_overlay_button_visibility()
        # Gather image data and headers
        image_datas = []
        headers = []
        for path in self.loaded_files:
            img, hdr, wcs = self._preloaded_fits.get(path, (None, None, None))
            if img is None or hdr is None:
                QMessageBox.critical(self, "Alignment Error", f"Could not load image or header for {path}")
                return
            image_datas.append(img)
            headers.append(hdr)
        # Check all have WCS
        if not check_all_have_wcs(headers):
            QMessageBox.critical(self, "Alignment Error", "One or more images is not platesolved (missing WCS). Alignment aborted.")
            return
        # Check pixel scales match
        if not check_pixel_scales_match(headers):
            QMessageBox.critical(self, "Alignment Error", "Pixel scales do not match between images. Alignment aborted.")
            return
        pad_x, pad_y = 100, 100
        # Progress dialog
        progress = QProgressDialog("Aligning images...", None, 0, len(image_datas), self)
        progress.setWindowTitle("Aligning")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()
        # Start worker thread
        self._align_thread = QThread()
        self._align_worker = AlignmentWorker(image_datas, headers, pad_x, pad_y)
        self._align_worker.moveToThread(self._align_thread)
        self._align_thread.started.connect(self._align_worker.run)
        self._align_worker.progress.connect(lambda frac: (progress.setValue(int(frac * len(image_datas))), QApplication.processEvents()))
        def on_finished(aligned_datas, common_wcs, new_nx, new_ny, headers):
            progress.close()
            for i, path in enumerate(self.loaded_files):
                new_header = headers[0].copy()
                new_header['NAXIS1'] = new_nx
                new_header['NAXIS2'] = new_ny
                self._preloaded_fits[path] = (aligned_datas[i], new_header, common_wcs)
            self.current_file_index = 0
            self.load_fits(self.loaded_files[0], restore_view=False)
            self.update_navigation_buttons()
            self.update_image_count_label()
            self.update_align_button_visibility()
            self._align_thread.quit()
            self._align_thread.wait()
        self._align_worker.finished.connect(on_finished)
        def on_error(msg):
            progress.close()
            QMessageBox.critical(self, "Alignment Error", f"Error during alignment: {msg}")
            self._align_thread.quit()
            self._align_thread.wait()
        self._align_worker.error.connect(on_error)
        self._align_thread.start()

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