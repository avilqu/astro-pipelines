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
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtWidgets import QMenu  # Add this to the imports if not present

def make_toolbar_separator(parent):
    sep = QFrame(parent)
    sep.setFixedWidth(8)  # Give it a little width for margin
    sep.setFixedHeight(32)  # Match your toolbar height
    sep.setStyleSheet("QFrame { margin-left: 5px; border-left: 1px solid #777777; background: transparent; }")
    return sep

class NoWheelScrollArea(QScrollArea):
    def wheelEvent(self, event):
        # Ignore wheel events so they are not used for scrolling
        event.ignore()

class NoContextToolBar(QToolBar):
    def contextMenuEvent(self, event):
        # Completely ignore context menu events
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
        
        # Set global stylesheet for better disabled state visibility
        self.setStyleSheet("""
            QAction:disabled {
                color: #333333;
            }
            QPushButton:disabled {
                color: #333333;
            }
            QLabel:disabled {
                color: #333333;
            }
        """)

        # --- Multi-file support ---
        self.loaded_files = []  # List of file paths
        self.current_file_index = -1  # Index of currently displayed file
        self._preloaded_fits = {}  # path -> (image_data, header, wcs)

        self.astrometry_catalog = AstrometryCatalog()
        self.pixmap = None  # For ImageLabel compatibility
        self.wcs = None    # For ImageLabel compatibility
        self.image_data = None  # Store current image data
        self.stretch_mode = 'linear'  # 'linear' or 'log', default to linear
        self.toolbar = NoContextToolBar("Main Toolbar")
        self.toolbar.setMovable(False)  # Disable moving the toolbar
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)  # Remove handle visual
        # Also disable context menu on the main window
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.toolbar.setStyleSheet("""
            QToolBar { background: #222222; }
            QToolButton { 
                border: none; 
                background: transparent; 
                padding: 4px;
            }
            QToolButton:hover { 
                border: 1px solid #555555; 
                background: #333333; 
                border-radius: 4px;
            }
            QToolButton:pressed { 
                border: 1px solid #777777; 
                background: #444444; 
                border-radius: 4px;
            }
            QToolButton:checked {
                border: 1px solid #777777;
                background: #444444;
                border-radius: 4px;
            }
            QToolButton:disabled {
                color: #333333;
            }
        """)
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
        
        # Next button (move back to col 3)
        self.next_button = QToolButton(self)
        self.next_button.setDefaultAction(self.next_action)
        self.next_button.setFixedSize(32, 32)
        nav_layout.addWidget(self.next_button, 0, 3)
        nav_widget.setLayout(nav_layout)
        nav_widget.setStyleSheet("""
            QToolButton { 
                border: none; 
                background: transparent; 
                padding: 4px;
            }
            QToolButton:hover { 
                border: 1px solid #555555; 
                background: #333333; 
                border-radius: 4px;
            }
            QToolButton:pressed { 
                border: 1px solid #777777; 
                background: #444444; 
                border-radius: 4px;
            }
        """)

        # --- Existing toolbar buttons (left side) ---
        open_icon = QIcon.fromTheme("document-open")
        if open_icon.isNull():
            open_icon = QIcon.fromTheme("folder-open")
        load_action = QAction(open_icon, "Open FITS", self)
        load_action.setToolTip("Open FITS file")
        load_action.triggered.connect(self.open_file_dialog)
        self.toolbar.addAction(load_action)
        self.toolbar.widgetForAction(load_action).setFixedSize(32, 32)

        # Add Close button next to Open button
        close_icon = QIcon.fromTheme("dialog-close")
        if close_icon.isNull():
            close_icon = QIcon.fromTheme("window-close")
        self.close_action = QAction(close_icon, "Close FITS", self)
        self.close_action.setToolTip("Close current FITS file")
        self.close_action.setEnabled(False)  # Initially disabled until a file is loaded
        self.close_action.triggered.connect(self.close_current_file)
        self.toolbar.addAction(self.close_action)
        self.toolbar.widgetForAction(self.close_action).setFixedSize(32, 32)

        self.toolbar.addWidget(make_toolbar_separator(self))

        self.reset_zoom_action = QAction(QIcon.fromTheme("zoom-original"), "", self)
        self.reset_zoom_action.setToolTip("Reset zoom to 1:1")
        self.reset_zoom_action.triggered.connect(self.reset_zoom)
        self.toolbar.addAction(self.reset_zoom_action)
        self.toolbar.widgetForAction(self.reset_zoom_action).setFixedSize(32, 32)
        self.zoom_to_fit_action = QAction(QIcon.fromTheme("zoom-fit-width"), "", self)
        self.zoom_to_fit_action.setToolTip("Zoom to fit image in viewport")
        self.zoom_to_fit_action.triggered.connect(self.zoom_to_fit)
        self.toolbar.addAction(self.zoom_to_fit_action)
        self.toolbar.widgetForAction(self.zoom_to_fit_action).setFixedSize(32, 32)

        # Add Zoom to Region button
        self.zoom_region_action = QAction(QIcon.fromTheme("page-zoom"), "", self)
        self.zoom_region_action.setCheckable(True)
        self.zoom_region_action.setChecked(False)
        self.zoom_region_action.setToolTip("Zoom to selected region (draw rectangle)")
        self.zoom_region_action.toggled.connect(self.on_zoom_region_toggled)
        self.toolbar.addAction(self.zoom_region_action)
        self.toolbar.widgetForAction(self.zoom_region_action).setFixedSize(32, 32)

        self.toolbar.addWidget(make_toolbar_separator(self))

        self.linear_action = QAction(QIcon.fromTheme("view-object-histogram-linear-symbolic"), "", self)
        self.linear_action.setToolTip("Linear histogram stretch")
        self.linear_action.triggered.connect(self.set_linear_stretch)
        self.toolbar.addAction(self.linear_action)
        self.toolbar.widgetForAction(self.linear_action).setFixedSize(32, 32)
        self.log_action = QAction(QIcon.fromTheme("view-object-histogram-logarithmic"), "", self)
        self.log_action.setToolTip("Logarithmic histogram stretch")
        self.log_action.triggered.connect(self.set_log_stretch)
        self.toolbar.addAction(self.log_action)
        self.toolbar.widgetForAction(self.log_action).setFixedSize(32, 32)

        # Add brightness slider (not related to sigma clipping)
        from PyQt6.QtWidgets import QSlider, QLabel
        
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.brightness_slider.setMinimum(0)
        self.brightness_slider.setMaximum(100)
        self.brightness_slider.setValue(50)  # Default to middle position
        self.brightness_slider.setFixedWidth(120)
        self.brightness_slider.setToolTip("Adjust image brightness")
        self.brightness_slider.valueChanged.connect(self.on_brightness_slider_changed)
        self.brightness_slider.setStyleSheet("""
            QSlider:disabled {
                color: #333333;
            }
        """)
        self.toolbar.addWidget(self.brightness_slider)

        # Add Clipping button
        self.clipping_action =  QAction(QIcon.fromTheme("upindicator"), "", self)
        self.clipping_action.setCheckable(True)
        self.clipping_action.setChecked(False) # Default to off
        self.clipping_action.setToolTip(f"Toggle sigma clipping for display stretch (sigma={3.0})")
        self.clipping_action.triggered.connect(self.toggle_clipping)
        self.toolbar.addAction(self.clipping_action)
        self.toolbar.widgetForAction(self.clipping_action).setFixedSize(32, 32)

        # Lock stretch functionality is now always enabled by default
        # (removed the lock stretch button)
        
        self.toolbar.addWidget(make_toolbar_separator(self))
        
        # Add SIMBAD search button
        self.simbad_button = QAction(QIcon.fromTheme("file-search-symbolic"), "", self)
        self.simbad_button.setToolTip("Search for an object in SIMBAD and overlay on image")
        self.simbad_button.setEnabled(True)
        self.simbad_button.triggered.connect(self.open_simbad_search_dialog)
        self.toolbar.addAction(self.simbad_button)
        self.toolbar.widgetForAction(self.simbad_button).setFixedSize(32, 32)
        # Add Solar System Objects button (before SIMBAD)
        sso_icon = QIcon.fromTheme("kstars_planets")
        if sso_icon.isNull():
            sso_icon = QIcon.fromTheme("applications-science")
        # Replace QAction with QToolButton + QMenu for dropdown
        self.sso_button = QToolButton(self)
        self.sso_button.setIcon(sso_icon)
        self.sso_button.setToolTip("Solar System Objects")
        self.sso_button.setEnabled(True)
        self.sso_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.sso_button.setFixedSize(32, 32)
        # Create dropdown menu
        sso_menu = QMenu(self.sso_button)
        find_sso_action = QAction("Find SSO in field", self)
        find_sso_action.triggered.connect(self.open_sso_search_dialog)
        sso_menu.addAction(find_sso_action)
        
        # Add separator
        sso_menu.addSeparator()
        
        # Add Compute orbit data action
        compute_orbit_action = QAction("Get orbital elements", self)
        compute_orbit_action.triggered.connect(self.open_orbit_computation_dialog)
        sso_menu.addAction(compute_orbit_action)
        
        self.sso_button.setMenu(sso_menu)
        # Remove the dropdown arrow via stylesheet
        self.sso_button.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
        # Do NOT connect .clicked to open_sso_search_dialog; only menu triggers the action
        self.toolbar.addWidget(self.sso_button)
        # Overlay toggle action (toolbar)
        self.overlay_toggle_action = QAction(QIcon.fromTheme("shapes"), "", self)
        self.overlay_toggle_action.setCheckable(True)
        self.overlay_toggle_action.setChecked(True)
        self.overlay_toggle_action.setVisible(False)
        self.overlay_toggle_action.triggered.connect(self.toggle_overlay_visibility)
        self.toolbar.addAction(self.overlay_toggle_action)
        self.toolbar.widgetForAction(self.overlay_toggle_action).setFixedSize(32, 32)

        self.toolbar.addWidget(make_toolbar_separator(self))
        
        # Add Calibrate button (after platesolve)
        from lib.gui.library.calibration_thread import CalibrationThread
        calibrate_icon = QIcon.fromTheme("blur")
        if calibrate_icon.isNull():
            calibrate_icon = QIcon.fromTheme("edit-blur")
        self.calibrate_action = QAction(calibrate_icon, "", self)
        self.calibrate_action.setToolTip("Calibrate all loaded images")
        self.calibrate_action.setEnabled(True)
        self.calibrate_action.triggered.connect(self.calibrate_all_images)
        self.toolbar.addAction(self.calibrate_action)
        self.toolbar.widgetForAction(self.calibrate_action).setFixedSize(32, 32)

        # Add Platesolve button (before FITS header button)
        self.platesolve_action = QAction(QIcon.fromTheme("map-globe"), "", self)
        self.platesolve_action.setToolTip("Platesolve all loaded images")
        self.platesolve_action.setEnabled(False)
        self.platesolve_action.triggered.connect(self.platesolve_all_images)
        self.toolbar.addAction(self.platesolve_action)
        self.toolbar.widgetForAction(self.platesolve_action).setFixedSize(32, 32)

        self.header_button = QAction(QIcon.fromTheme("view-financial-list"), "", self)
        self.header_button.setToolTip("Show FITS header")
        self.header_button.setEnabled(False)
        self.header_button.triggered.connect(self.show_header_dialog)
        self.toolbar.addAction(self.header_button)
        self.toolbar.widgetForAction(self.header_button).setFixedSize(32, 32)

        self.toolbar.addWidget(make_toolbar_separator(self))

        # Add Integration button with dropdown (QToolButton to remove arrow)
        integration_icon = QIcon.fromTheme("black_sum")
        if integration_icon.isNull():
            integration_icon = QIcon.fromTheme("applications-science")
        self.integration_button = QToolButton(self)
        self.integration_button.setIcon(integration_icon)
        self.integration_button.setToolTip("Integration")
        self.integration_button.setEnabled(False)  # Initially disabled
        self.integration_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.integration_button.setFixedSize(32, 32)
        
        # Create dropdown menu
        integration_menu = QMenu(self.integration_button)
        align_wcs_action = QAction("Align on WCS", self)
        align_wcs_action.triggered.connect(self.align_images)
        integration_menu.addAction(align_wcs_action)
        
        # Add separator
        integration_menu.addSeparator()
        
        stack_wcs_action = QAction("Stack aligned images", self)
        stack_wcs_action.triggered.connect(self.stack_align_wcs)
        integration_menu.addAction(stack_wcs_action)
        stack_ephemeris_action = QAction("Stack on ephemeris", self)
        stack_ephemeris_action.triggered.connect(self.stack_align_ephemeris)
        integration_menu.addAction(stack_ephemeris_action)
        
        self.integration_button.setMenu(integration_menu)
        # Remove the dropdown arrow via stylesheet
        self.integration_button.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
        self.toolbar.addWidget(self.integration_button)

        # Add a simple test label to see if widgets are being added correctly
        # test_label = QLabel("TEST", self)
        # test_label.setStyleSheet("QLabel { background-color: red; color: white; padding: 2px; }")
        # self.toolbar.addWidget(test_label)

        # Add a spacer to push navigation elements to the right
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar.addWidget(spacer)

        # Align button removed - functionality moved to Integration dropdown

        self.toolbar.addWidget(nav_widget)

        # Add File List toggle button (only visible if >1 image loaded) - pushed to the far right
        self.filelist_action = QAction(QIcon.fromTheme("view-list-details"), "", self)
        self.filelist_action.setToolTip("Show list of loaded FITS files")
        self.filelist_action.setVisible(False)
        self.filelist_action.setCheckable(True)
        self.filelist_action.setChecked(False)
        self.filelist_action.triggered.connect(self.toggle_filelist_window)
        self.toolbar.addAction(self.filelist_action)
        self.toolbar.widgetForAction(self.filelist_action).setFixedSize(32, 32)
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
        # Stretch lock attributes - now always locked by default
        self.stretch_locked = True
        self.locked_display_min = None
        self.locked_display_max = None
        self.brightness_adjustment = 0.0  # Track user's brightness adjustment separately
        self._sso_highlight_index = None
        self._zoom_region_mode = False  # Track if zoom-to-region is active
        self._pending_zoom_rect = None  # Store the last selected rectangle
        if fits_path:
            self.open_and_add_file(fits_path)
        self.update_overlay_button_visibility()
        self.update_navigation_buttons()
        self.update_align_button_visibility()
        self.update_display_minmax_tooltips() # Initialize tooltips
        self.update_platesolve_button_visibility()
        self.update_close_button_visibility()
        
        # Set initial button states (disabled if no image loaded)
        if not fits_path:
            self.update_button_states_for_no_image()
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

    def open_file(self):
        """Alias for open_file_dialog for keyboard shortcuts"""
        self.open_file_dialog()

    def close_current_file(self):
        """Close the currently displayed FITS file and remove it from the image list"""
        if not self.loaded_files or self.current_file_index < 0:
            return
        
        # Remove the current file from the list
        removed_file = self.loaded_files.pop(self.current_file_index)
        
        # Remove from preloaded data
        if removed_file in self._preloaded_fits:
            del self._preloaded_fits[removed_file]
        
        # Update current file index
        if not self.loaded_files:
            # No files left - completely reset the viewer state
            self.current_file_index = -1
            self.image_data = None
            self.wcs = None
            self._current_header = None
            self.pixmap = None
            self._orig_pixmap = None
            
            # Clear the image label and set proper styling for text display
            self.image_label.clear()
            self.image_label.setText("No image loaded")
            self.image_label.setStyleSheet("QLabel { background-color: #f0f0f0; color: #333333; font-size: 14px; }")
            self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Reset the label size to allow proper text display
            self.image_label.setFixedSize(400, 300)
            
            # Center the label in the scroll area
            self.scroll_area.setWidgetResizable(True)
            self.scroll_area.ensureWidgetVisible(self.image_label)
            
            self.setWindowTitle("Astropipes FITS Viewer")
            self.header_button.setEnabled(False)
            self.close_action.setEnabled(False)
            
            # Disable all image-dependent buttons
            self.update_button_states_for_no_image()
            
            # Clear any overlays
            self._simbad_overlay = None
            self._sso_overlay = None
            self._ephemeris_overlay = None
            self._overlay_visible = False
            self.update_overlay_button_visibility()
        else:
            # Adjust current index if necessary
            if self.current_file_index >= len(self.loaded_files):
                self.current_file_index = len(self.loaded_files) - 1
            
            # Load the new current file
            self.load_fits(self.loaded_files[self.current_file_index], restore_view=False)
        
        # Update UI elements
        self.update_navigation_buttons()
        self.update_image_count_label()
        self.update_align_button_visibility()
        self.update_platesolve_button_visibility()
        self.update_close_button_visibility()
        
        # Update file list window if open
        if hasattr(self, '_filelist_window') and self._filelist_window is not None:
            self._filelist_window.table.setRowCount(len(self.loaded_files))
            for i, path in enumerate(self.loaded_files):
                item = QTableWidgetItem(os.path.basename(path))
                item.setToolTip(path)
                self._filelist_window.table.setItem(i, 0, item)
            self._filelist_window.file_paths = list(self.loaded_files)
            if self.current_file_index >= 0:
                self._filelist_window.select_row(self.current_file_index)

    def _get_viewport_center(self):
        # Returns the center of the viewport in image coordinates (x, y)
        if self.image_label.pixmap() is None or self.image_data is None:
            return None
            
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()
        viewport_w = self.scroll_area.viewport().width()
        viewport_h = self.scroll_area.viewport().height()
        label_w = self.image_label.width()
        label_h = self.image_label.height()
        
        if label_w > 0 and label_h > 0:
            # Get the original image dimensions
            img_h, img_w = self.image_data.shape
            
            # Calculate the image dimensions in the current zoom
            pixmap_w = self.image_label.pixmap().width()
            pixmap_h = self.image_label.pixmap().height()
            
            # Calculate the scale factor (same as in overlay coordinate conversion)
            scale_x = pixmap_w / img_w
            scale_y = pixmap_h / img_h
            scale = scale_x  # or scale_y, they should be equal
            
            # Calculate the offset to center the image within the padded label
            x_offset = (label_w - pixmap_w) // 2
            y_offset = (label_h - pixmap_h) // 2
            
            # Get the center of the viewport in label coordinates
            center_x = hbar.value() + viewport_w // 2
            center_y = vbar.value() + viewport_h // 2
            
            # Convert from label coordinates to image coordinates (reverse of overlay conversion)
            pixmap_x = center_x - x_offset
            pixmap_y = center_y - y_offset
            
            if (0 <= pixmap_x < pixmap_w and 0 <= pixmap_y < pixmap_h):
                img_cx = pixmap_x / scale
                img_cy = pixmap_y / scale
                return (img_cx, img_cy)
        return None

    def _set_viewport_center(self, img_cx, img_cy):
        # Centers the viewport on (img_cx, img_cy) in image coordinates
        if self.image_label.pixmap() is None:
            return
            
        viewport_w = self.scroll_area.viewport().width()
        viewport_h = self.scroll_area.viewport().height()
        label_w = self.image_label.width()
        label_h = self.image_label.height()
        
        if label_w > 0 and label_h > 0:
            # Get the original image dimensions
            img_h, img_w = self.image_data.shape
            
            # Calculate the image dimensions in the current zoom
            pixmap_w = self.image_label.pixmap().width()
            pixmap_h = self.image_label.pixmap().height()
            
            # Calculate the scale factor (same as in overlay coordinate conversion)
            scale_x = pixmap_w / img_w
            scale_y = pixmap_h / img_h
            scale = scale_x  # or scale_y, they should be equal
            
            # Calculate the offset to center the image within the padded label
            x_offset = (label_w - pixmap_w) // 2
            y_offset = (label_h - pixmap_h) // 2
            
            # Convert image coordinates to label coordinates (same as overlay conversion)
            center_x = int(img_cx * scale) + x_offset
            center_y = int(img_cy * scale) + y_offset
            
            hbar = self.scroll_area.horizontalScrollBar()
            vbar = self.scroll_area.verticalScrollBar()
            # Allow centering beyond image boundaries by not constraining to minimum values
            hbar.setValue(center_x - viewport_w // 2)
            vbar.setValue(center_y - viewport_h // 2)

    def _center_image_in_viewport(self):
        """Center the image in the viewport, accounting for padding"""
        if self.image_label.pixmap() is None:
            return
        
        viewport_w = self.scroll_area.viewport().width()
        viewport_h = self.scroll_area.viewport().height()
        label_w = self.image_label.width()
        label_h = self.image_label.height()
        
        # Calculate the center of the image within the padded label
        # The image is centered in the label, so its center is at label_w/2, label_h/2
        image_center_x = label_w // 2
        image_center_y = label_h // 2
        
        # Calculate scroll position to center the image in the viewport
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()
        
        scroll_x = image_center_x - viewport_w // 2
        scroll_y = image_center_y - viewport_h // 2
        
        hbar.setValue(scroll_x)
        vbar.setValue(scroll_y)

    def open_and_add_file(self, fits_path):
        # Save zoom, center, and brightness before switching
        if self.image_data is not None:
            self._last_zoom = self._zoom
            self._last_center = self._get_viewport_center()
            self._last_brightness = self.brightness_slider.value()
        else:
            self._last_zoom = 1.0
            self._last_center = None
            self._last_brightness = 50
        # If already loaded, just switch to it
        if fits_path in self.loaded_files:
            self.current_file_index = self.loaded_files.index(fits_path)
            self.load_fits(fits_path, restore_view=True)
        else:
            self.loaded_files.append(fits_path)
            self.current_file_index = len(self.loaded_files) - 1
            self._preload_fits_file(fits_path)
            self.load_fits(fits_path, restore_view=False)  # New files should be centered, not restore view
            # Auto-zoom to fit for the first file loaded
            if len(self.loaded_files) == 1:
                from PyQt6.QtCore import QTimer
                from PyQt6.QtWidgets import QApplication
                # Process events and then apply zoom to fit
                def delayed_zoom():
                    QApplication.processEvents()
                    self.zoom_to_fit()
                QTimer.singleShot(100, delayed_zoom)
        self.update_navigation_buttons()
        self.update_image_count_label()
        self.update_align_button_visibility()
        self.update_platesolve_button_visibility()
        self.update_close_button_visibility()
        # Update file list window if open
        if hasattr(self, '_filelist_window') and self._filelist_window is not None:
            self._filelist_window.table.setRowCount(len(self.loaded_files))
            for i, path in enumerate(self.loaded_files):
                item = QTableWidgetItem(os.path.basename(path))
                item.setToolTip(path)
                self._filelist_window.table.setItem(i, 0, item)
            self._filelist_window.file_paths = list(self.loaded_files)
            self._filelist_window.select_row(self.current_file_index)

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
        # Save zoom, center, and brightness before switching
        if self.image_data is not None:
            self._last_zoom = self._zoom
            self._last_center = self._get_viewport_center()
            self._last_brightness = self.brightness_slider.value()
        else:
            self._last_zoom = 1.0
            self._last_center = None
            self._last_brightness = 50
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
        self.update_platesolve_button_visibility()
        self.update_close_button_visibility()
        # Update highlight in file list window
        if hasattr(self, '_filelist_window') and self._filelist_window is not None:
            self._filelist_window.select_row(self.current_file_index)

    def show_next_file(self):
        # Save zoom, center, and brightness before switching
        if self.image_data is not None:
            self._last_zoom = self._zoom
            self._last_center = self._get_viewport_center()
            self._last_brightness = self.brightness_slider.value()
        else:
            self._last_zoom = 1.0
            self._last_center = None
            self._last_brightness = 50
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
        self.update_platesolve_button_visibility()
        self.update_close_button_visibility()
        # Update highlight in file list window
        if hasattr(self, '_filelist_window') and self._filelist_window is not None:
            self._filelist_window.select_row(self.current_file_index)

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



    def on_brightness_slider_changed(self, value):
        # Convert slider value (0-100) to brightness adjustment
        # 50 = neutral, 0 = darkest, 100 = brightest
        if self.display_min is None or self.display_max is None:
            auto_min, auto_max = self._get_auto_display_minmax()
            self.display_min = auto_min
            self.display_max = auto_max
        
        # Calculate the adjustment range based on image statistics
        step = self._get_display_min_step()
        adjustment_range = 10 * step  # Allow for significant brightness adjustment
        
        # Convert slider value to adjustment
        # value 50 = no adjustment, value 0 = darkest, value 100 = brightest
        adjustment = (value - 50) / 50.0 * adjustment_range
        
        # Store the brightness adjustment separately
        self.brightness_adjustment = adjustment
        
        # Apply adjustment to display_min (lower values = brighter image)
        auto_min, auto_max = self._get_auto_display_minmax()
        adjusted_min = auto_min - adjustment
        
        # Update display parameters
        self.display_min = adjusted_min
        self.locked_display_min = self.display_min
        self.locked_display_max = self.display_max
        
        # Update the image display
        self.update_image_display(keep_zoom=True)
        self.update_brightness_slider_tooltip()

    def update_brightness_slider_tooltip(self):
        # Update tooltip to show current brightness level
        if self.display_min is not None:
            self.brightness_slider.setToolTip(f"Adjust image brightness (min: {self.display_min:.2f})")
        else:
            self.brightness_slider.setToolTip("Adjust image brightness")

    def _get_auto_display_minmax(self):
        # Compute the default min/max as would be used by create_image_object
        if self.stretch_mode == 'log':
            data = self.image_data.astype(float)
            # Avoid divide-by-zero warning by only computing log10 for positive values
            mask = data > 0
            log_data = np.zeros_like(data)
            log_data[mask] = np.log10(data[mask])
            data = log_data
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
            # Avoid divide-by-zero warning by only computing log10 for positive values
            mask = data > 0
            log_data = np.zeros_like(data)
            log_data[mask] = np.log10(data[mask])
            data = log_data
        else:
            data = self.image_data
        if data is not None:
            finite_vals = data[np.isfinite(data)]
            if finite_vals.size > 0:
                return float(np.std(finite_vals)) * 0.4  # 4x bigger than before
        return 4.0

    def update_display_minmax_tooltips(self):
        # Update brightness slider tooltip
        self.update_brightness_slider_tooltip()

    def set_linear_stretch(self):
        self.stretch_mode = 'linear'
        # Recalculate base parameters with new stretch mode
        auto_min, auto_max = self._get_auto_display_minmax()
        # Apply the stored brightness adjustment to preserve user's settings
        adjusted_min = auto_min - self.brightness_adjustment
        self.locked_display_min = adjusted_min
        self.locked_display_max = auto_max
        self.display_min = self.locked_display_min
        self.display_max = self.locked_display_max
        # Update the display with the new stretch mode
        self.update_image_display(keep_zoom=True)
        # Don't call zoom_to_fit() as it changes the viewport position

    def set_log_stretch(self):
        self.stretch_mode = 'log'
        # Recalculate base parameters with new stretch mode
        auto_min, auto_max = self._get_auto_display_minmax()
        # Apply the stored brightness adjustment to preserve user's settings
        adjusted_min = auto_min - self.brightness_adjustment
        self.locked_display_min = adjusted_min
        self.locked_display_max = auto_max
        self.display_min = self.locked_display_min
        self.display_max = self.locked_display_max
        # Update the display with the new stretch mode
        self.update_image_display(keep_zoom=True)
        # Don't call zoom_to_fit() as it changes the viewport position

    def toggle_clipping(self):
        self.clipping_enabled = not self.clipping_enabled
        self.clipping_action.setChecked(self.clipping_enabled)
        # Recalculate base parameters with new clipping setting
        auto_min, auto_max = self._get_auto_display_minmax()
        # Apply the stored brightness adjustment to preserve user's settings
        adjusted_min = auto_min - self.brightness_adjustment
        self.locked_display_min = adjusted_min
        self.locked_display_max = auto_max
        self.display_min = self.locked_display_min
        self.display_max = self.locked_display_max
        # Update the display with the new clipping setting
        self.update_image_display(keep_zoom=True)

    def update_image_display(self, keep_zoom=False):
        if self.image_data is None:
            return
        # Save current zoom and viewport center
        if keep_zoom:
            current_zoom = self._zoom if hasattr(self, '_zoom') else 1.0
            # Save current viewport center for restoration
            saved_center = self._get_viewport_center()
        else:
            current_zoom = getattr(self, '_zoom', 1.0)
        viewport_w = self.scroll_area.viewport().width()
        viewport_h = self.scroll_area.viewport().height()
        if self.stretch_mode == 'linear':
            orig_pixmap = create_image_object(self.image_data, display_min=self.display_min, display_max=self.display_max, clipping=self.clipping_enabled, sigma_clip=self.sigma_clip)
        else:
            data = self.image_data.astype(float)
            # Avoid divide-by-zero warning by only computing log10 for positive values
            mask = data > 0
            log_data = np.zeros_like(data)
            log_data[mask] = np.log10(data[mask])
            orig_pixmap = create_image_object(log_data, display_min=self.display_min, display_max=self.display_max, clipping=self.clipping_enabled, sigma_clip=self.sigma_clip)
        self._orig_pixmap = orig_pixmap  # Always set to the unscaled pixmap
        # Set the display pixmap according to current zoom
        new_width = int(orig_pixmap.width() * self._zoom)
        new_height = int(orig_pixmap.height() * self._zoom)
        display_pixmap = orig_pixmap.scaled(new_width, new_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(display_pixmap)
        
        # Add padding around the image to allow panning beyond boundaries
        # The padding should be large enough to allow significant panning
        padding = max(1000, max(new_width, new_height) * 2)  # At least 1000px or 2x image size
        padded_width = new_width + padding
        padded_height = new_height + padding
        self.image_label.setFixedSize(padded_width, padded_height)
        self.pixmap = orig_pixmap
        # Set scale_factor for coordinate conversion
        self.scale_factor = self._zoom if hasattr(self, '_zoom') else 1.0
        
        # If this is a new image (not restoring view), center it in the viewport
        if not keep_zoom:
            self._center_image_in_viewport()
        else:
            # Restore the viewport center with a small delay to ensure image is loaded
            if saved_center:
                from PyQt6.QtCore import QTimer
                def restore_center():
                    self._set_viewport_center(saved_center[0], saved_center[1])
                QTimer.singleShot(10, restore_center)
        # If zoom mode is set to fit, update zoom
        if getattr(self, '_pending_zoom_to_fit', False):
            self._pending_zoom_to_fit = False
            self.zoom_to_fit()

    def reset_zoom(self):
        self._zoom = 1.0
        self.update_image_display(keep_zoom=False)

    def zoom_in_at_center(self):
        """Zoom in at the current viewport center"""
        if self._orig_pixmap is None:
            return
        self._zoom = min(self._zoom * 1.15, 20.0)
        self.update_image_display(keep_zoom=True)

    def zoom_out_at_center(self):
        """Zoom out at the current viewport center"""
        if self._orig_pixmap is None:
            return
        self._zoom = max(self._zoom / 1.15, 0.05)
        self.update_image_display(keep_zoom=True)

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
        # Use the proper display update mechanism
        self.update_image_display(keep_zoom=False)
        # Center the image in the viewport
        self._center_image_in_viewport()
        # Force a repaint to ensure the viewport is updated
        self.image_label.update()
        self.scroll_area.viewport().update()
        # Force the viewport to center on the image
        label_w = self.image_label.width()
        label_h = self.image_label.height()
        viewport_w = self.scroll_area.viewport().width()
        viewport_h = self.scroll_area.viewport().height()
        center_x = (label_w - viewport_w) // 2
        center_y = (label_h - viewport_h) // 2
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()
        hbar.setValue(center_x)
        vbar.setValue(center_y)

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
                    
                    # Restore proper image display styling
                    self.image_label.setStyleSheet("QLabel { background-color: black; }")
                    self.scroll_area.setWidgetResizable(False)
                    
                    # Restore zoom and center if requested
                    if restore_view and hasattr(self, '_last_zoom') and self._last_zoom:
                        self._zoom = self._last_zoom
                    else:
                        self._zoom = 1.0
                    self._pending_zoom_to_fit = False
                    self.update_image_display(keep_zoom=restore_view)
                    self.image_label.setText("")
                    self.setWindowTitle(f"Astropipes FITS Viewer - {fits_path}")
                    self.header_button.setEnabled(True)
                    
                    # Enable all image-dependent buttons
                    self.update_button_states_for_image_loaded()
                    # Since stretch is always locked, initialize locked parameters on first load
                    if self.locked_display_min is None or self.locked_display_max is None:
                        # First time loading - calculate and store locked parameters
                        auto_min, auto_max = self._get_auto_display_minmax()
                        self.locked_display_min = auto_min
                        self.locked_display_max = auto_max
                        self.display_min = self.locked_display_min
                        self.display_max = self.locked_display_max
                    else:
                        # Use existing locked parameters - DO NOT recalculate based on new image
                        # Apply the stored brightness adjustment to the new image
                        auto_min, auto_max = self._get_auto_display_minmax()
                        adjusted_min = auto_min - self.brightness_adjustment
                        self.locked_display_min = adjusted_min
                        self.locked_display_max = auto_max
                        self.display_min = self.locked_display_min
                        self.display_max = self.locked_display_max
                        # Update the display with the locked parameters
                        self.update_image_display(keep_zoom=restore_view)
                    # Restore brightness slider position and apply adjustment
                    if hasattr(self, '_last_brightness'):
                        self.brightness_slider.setValue(self._last_brightness)
                        # The brightness adjustment is already applied above, just update the slider tooltip
                        self.update_brightness_slider_tooltip()
                    else:
                        self.brightness_slider.setValue(50)
                else:
                    self.image_label.setText("FITS file is not a 2D image.")
                    self.image_data = None
                    self.header_button.setEnabled(False)
            else:
                self.image_label.setText("No image data in FITS file.")
                self.image_data = None
                self.header_button.setEnabled(False)
            # self._simbad_overlay = None  # Do NOT clear SIMBAD overlay when switching images
            self.update_overlay_button_visibility()
        except Exception as e:
            self.image_label.setText(f"Error loading FITS: {e}")
            self.image_data = None
            self.header_button.setEnabled(False)
            # self._simbad_overlay = None  # Do NOT clear SIMBAD overlay on error
            self.update_overlay_button_visibility()
        self.update_navigation_buttons()
        self.update_image_count_label()
        self.update_close_button_visibility()
        # After loading, update ephemeris marker if present
        if hasattr(self, '_ephemeris_predicted_positions') and self._ephemeris_predicted_positions:
            idx = self.current_file_index
            if 0 <= idx < len(self._ephemeris_predicted_positions):
                ephemeris = self._ephemeris_predicted_positions[idx]
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

    def show_header_dialog(self):
        if hasattr(self, '_current_header') and self._current_header:
            file_path = None
            if self.loaded_files and 0 <= self.current_file_index < len(self.loaded_files):
                file_path = self.loaded_files[self.current_file_index]
            dlg = HeaderViewer(self._current_header, file_path, self)
            dlg.show()

    def toggle_overlay_visibility(self):
        self._overlay_visible = not self._overlay_visible
        self.overlay_toggle_action.setChecked(self._overlay_visible)
        self.image_label.update()

    def update_overlay_button_visibility(self):
        has_overlay = (
            (hasattr(self, '_simbad_overlay') and self._simbad_overlay is not None) or
            (hasattr(self, '_sso_overlay') and self._sso_overlay is not None) or
            (hasattr(self, '_ephemeris_overlay') and self._ephemeris_overlay is not None)
        )
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

    def open_sso_search_dialog(self):
        from astropy.time import Time
        from lib.fits.catalogs import SolarSystemObject
        from PyQt6.QtWidgets import QProgressDialog
        # Remove overlays before new search
        self._simbad_overlay = None
        self._sso_overlay = None
        self._overlay_visible = True
        self.update_overlay_button_visibility()
        if self.wcs is None or self.image_data is None:
            QMessageBox.warning(self, "No WCS", "No WCS/image data available. Please solve the image first.")
            return
        # --- Use DATE-OBS from FITS header as epoch ---
        epoch = None
        date_obs = None
        header = None
        # Try to get header from preloaded fits
        if self.loaded_files and 0 <= self.current_file_index < len(self.loaded_files):
            fits_path = self.loaded_files[self.current_file_index]
            if fits_path in self._preloaded_fits:
                _, header, _ = self._preloaded_fits[fits_path]
        if header is not None:
            date_obs = header.get('DATE-OBS')
        if date_obs:
            try:
                epoch = Time(date_obs, format='isot', scale='utc')
            except Exception:
                try:
                    epoch = Time(date_obs)
                except Exception:
                    epoch = None
        if epoch is None:
            epoch = Time.now()
            QMessageBox.warning(self, "DATE-OBS missing", "DATE-OBS not found or invalid in FITS header. Using current time for Skybot search.")
        # Progress dialog
        progress = QProgressDialog("Searching Skybot for solar system objects...", None, 0, 0, self)
        progress.setWindowTitle("Skybot Search")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()
        # Start worker thread
        self._skybot_thread = QThread()
        self._skybot_worker = SkybotWorker(self.astrometry_catalog, self.wcs, self.image_data.shape, epoch)
        self._skybot_worker.moveToThread(self._skybot_thread)
        self._skybot_thread.started.connect(self._skybot_worker.run)
        def on_finished(sso_list, pixel_coords_dict):
            progress.close()
            self._skybot_thread.quit()
            self._skybot_thread.wait()
            if not sso_list:
                QMessageBox.information(self, "No Solar System Objects", "No solar system objects found in the field.")
                return
            # Overlay only those in field
            sso_objects = list(pixel_coords_dict.keys())
            coords_list = list(pixel_coords_dict.values())
            self._sso_overlay = (sso_objects, coords_list)
            self._sso_highlight_index = None  # Reset highlight
            self._overlay_visible = True
            self.update_overlay_button_visibility()
            self.image_label.update()
            # Show SSO result window (all objects, with pixel coords if in field)
            try:
                from lib.gui.common.sso_window import SSOResultWindow
                dlg = SSOResultWindow(sso_list, pixel_coords_dict, self)
                dlg.sso_row_selected.connect(self.on_sso_row_selected)
                dlg.show()
            except ImportError:
                pass
            self.overlay_toggle_action.setVisible(True)
            self.overlay_toggle_action.setChecked(True)
        def on_error(msg):
            progress.close()
            self._skybot_thread.quit()
            self._skybot_thread.wait()
            QMessageBox.critical(self, "SSO Search Error", f"Error searching for solar system objects: {msg}")
        self._skybot_worker.finished.connect(on_finished)
        self._skybot_worker.error.connect(on_error)
        self._skybot_thread.start()

    def open_orbit_computation_dialog(self):
        """Open dialog to compute orbit data for a specific object."""
        if not self.loaded_files:
            QMessageBox.warning(self, "No Files", "No FITS files loaded. Please load some files first.")
            return
        
        # Extract target name from current FITS file
        target_name = None
        if self.current_file_index >= 0 and self.current_file_index < len(self.loaded_files):
            current_file_path = self.loaded_files[self.current_file_index]
            
            # Try to get target name from preloaded FITS data first
            if current_file_path in self._preloaded_fits:
                _, header, _ = self._preloaded_fits[current_file_path]
                if header:
                    target_name = header.get('OBJECT', '').strip()
            
            # If not found in preloaded data, try to read from file directly
            if not target_name:
                try:
                    from astropy.io import fits
                    with fits.open(current_file_path) as hdul:
                        header = hdul[0].header
                        target_name = header.get('OBJECT', '').strip()
                except Exception:
                    pass
        
        from lib.gui.common.orbit_details import OrbitComputationDialog
        dialog = OrbitComputationDialog(self, target_name)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            object_name = dialog.get_object_name()
            if not object_name:
                QMessageBox.warning(self, "No Object", "Please enter an object designation.")
                return
            
            # Console output window for orbit computation
            from lib.gui.common.console_window import ConsoleOutputWindow
            console_window = ConsoleOutputWindow(f"Orbit Computation: {object_name}", self)
            console_window.show_and_raise()
            
            # Start worker thread
            self._orbit_thread = QThread()
            from lib.gui.common.orbit_details import OrbitComputationWorker
            self._orbit_worker = OrbitComputationWorker(object_name, self.loaded_files, console_window)
            self._orbit_worker.moveToThread(self._orbit_thread)
            self._orbit_worker.console_output.connect(console_window.append_text)
            self._orbit_thread.started.connect(self._orbit_worker.run)
            
            def on_finished(predicted_positions, pseudo_mpec_text):
                console_window.append_text("\nComputation finished.\n")
                self._orbit_thread.quit()
                self._orbit_thread.wait()
                
                # Show orbit data window
                from lib.gui.common.orbit_details import OrbitDataWindow
                dlg = OrbitDataWindow(object_name, predicted_positions, pseudo_mpec_text, self)
                dlg.row_selected.connect(self.on_ephemeris_row_selected)
                self._ephemeris_predicted_positions = predicted_positions
                self._ephemeris_object_name = object_name
                dlg.show()
                # Store reference to prevent garbage collection
                self._orbit_window = dlg
                # Optionally, select the current file's row by default
                if self.current_file_index >= 0:
                    dlg.positions_table.selectRow(self.current_file_index)
                    self.on_ephemeris_row_selected(self.current_file_index, predicted_positions[self.current_file_index])
            
            def on_error(msg):
                console_window.append_text(f"\nError: {msg}\n")
                self._orbit_thread.quit()
                self._orbit_thread.wait()
                QMessageBox.critical(self, "Orbit Computation Error", f"Error computing orbit data: {msg}")
            
            self._orbit_worker.finished.connect(on_finished)
            self._orbit_worker.error.connect(on_error)
            self._orbit_thread.start()

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
        # Update integration button visibility based on number of loaded files
        visible = len(self.loaded_files) > 1
        self.filelist_action.setVisible(visible)
        # For QToolButton, always keep visible, but enable/disable
        if hasattr(self, 'integration_button'):
            self.integration_button.setEnabled(visible)
            self.toolbar.update()
            self.toolbar.repaint()

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

    def toggle_stretch_lock(self):
        # This method is no longer used since stretch is always locked by default
        pass

    def update_platesolve_button_visibility(self):
        # Enable if at least one file is loaded
        self.platesolve_action.setEnabled(len(self.loaded_files) > 0)

    def update_close_button_visibility(self):
        """Update the close button enabled state based on whether files are loaded"""
        self.close_action.setEnabled(len(self.loaded_files) > 0)

    def update_button_states_for_no_image(self):
        """Disable all buttons that require an image to be loaded"""
        # Disable image-dependent buttons
        self.reset_zoom_action.setEnabled(False)
        self.zoom_to_fit_action.setEnabled(False)
        self.zoom_region_action.setEnabled(False)
        
        # Disable stretch buttons
        self.linear_action.setEnabled(False)
        self.log_action.setEnabled(False)
        
        # Disable brightness slider
        self.brightness_slider.setEnabled(False)
        
        # Disable clipping button
        self.clipping_action.setEnabled(False)
        
        # Disable search buttons
        self.simbad_button.setEnabled(False)
        self.sso_button.setEnabled(False)
        
        # Disable overlay toggle
        self.overlay_toggle_action.setEnabled(False)
        
        # Disable calibration and platesolve buttons
        self.calibrate_action.setEnabled(False)
        self.platesolve_action.setEnabled(False)
        
        # Disable integration button
        self.integration_button.setEnabled(False)

    def update_button_states_for_image_loaded(self):
        """Enable all buttons that require an image to be loaded"""
        # Enable image-dependent buttons
        self.reset_zoom_action.setEnabled(True)
        self.zoom_to_fit_action.setEnabled(True)
        self.zoom_region_action.setEnabled(True)
        
        # Enable stretch buttons
        self.linear_action.setEnabled(True)
        self.log_action.setEnabled(True)
        
        # Enable brightness slider
        self.brightness_slider.setEnabled(True)
        
        # Enable clipping button
        self.clipping_action.setEnabled(True)
        
        # Enable search buttons
        self.simbad_button.setEnabled(True)
        self.sso_button.setEnabled(True)
        
        # Overlay toggle is managed separately based on overlay availability
        # self.overlay_toggle_action.setEnabled(True)
        
        # Enable calibration and platesolve buttons
        self.calibrate_action.setEnabled(True)
        self.platesolve_action.setEnabled(True)
        
        # Integration button is managed separately based on number of files
        # self.integration_button.setEnabled(True)

    def _format_platesolving_result(self, result):
        if hasattr(result, 'success') and result.success:
            success_msg = "Image successfully solved!\n\n"
            if getattr(result, 'ra_center', None) is not None and getattr(result, 'dec_center', None) is not None:
                success_msg += f"Center: RA={result.ra_center:.4f}°, Dec={result.dec_center:.4f}°\n"
            else:
                success_msg += "Center: Unknown\n"
            if getattr(result, 'pixel_scale', None) is not None:
                success_msg += f"Pixel scale: {result.pixel_scale:.3f} arcsec/pixel\n"
            else:
                success_msg += "Pixel scale: Unknown\n"
            return success_msg
        else:
            return f"Could not solve image: {getattr(result, 'message', str(result))}"

    def platesolve_all_images(self):
        from lib.gui.common.console_window import ConsoleOutputWindow
        from lib.gui.library.platesolving_thread import PlatesolvingThread
        # Minimal wrapper for .path attribute
        class FilePathObj:
            def __init__(self, path):
                self.path = path
        files = [FilePathObj(p) for p in self.loaded_files]
        if not files:
            QMessageBox.warning(self, "No files", "No FITS files loaded to platesolve.")
            return
        console_window = ConsoleOutputWindow("Platesolving All Files", self)
        console_window.show_and_raise()
        queue = list(files)
        results = []
        cancelled = {"flag": False}
        if not hasattr(self, '_platesolving_threads'):
            self._platesolving_threads = []
        def next_in_queue():
            if cancelled["flag"]:
                console_window.append_text("\nPlatesolving cancelled by user.\n")
                return
            if not queue:
                console_window.append_text("\nAll files platesolved.\n")
                # Reload all loaded files after platesolving
                current_index = self.current_file_index
                loaded_files_copy = list(self.loaded_files)
                self._preloaded_fits.clear()
                for path in loaded_files_copy:
                    self._preload_fits_file(path)
                # Try to restore the current file index
                if loaded_files_copy:
                    self.current_file_index = min(current_index, len(loaded_files_copy) - 1)
                    self.load_fits(loaded_files_copy[self.current_file_index], restore_view=True)
                self.update_navigation_buttons()
                self.update_image_count_label()
                self.update_align_button_visibility()
                self.update_platesolve_button_visibility()
                return
            fits_file = queue.pop(0)
            fits_path = fits_file.path
            console_window.append_text(f"\nPlatesolving: {fits_path}\n")
            thread = PlatesolvingThread(fits_path)
            self._platesolving_threads.append(thread)
            thread.output.connect(console_window.append_text)
            def on_finished(result):
                results.append(result)
                msg = self._format_platesolving_result(result)
                console_window.append_text(f"\n{msg}\n")
                if thread in self._platesolving_threads:
                    self._platesolving_threads.remove(thread)
                next_in_queue()
            thread.finished.connect(on_finished)
            thread.start()
        console_window.cancel_requested.connect(lambda: cancelled.update({"flag": True}))
        next_in_queue()

    def calibrate_all_images(self):
        from lib.gui.common.console_window import ConsoleOutputWindow
        from lib.gui.library.calibration_thread import CalibrationThread
        # Minimal wrapper for .path attribute
        class FilePathObj:
            def __init__(self, path):
                self.path = path
        files = [FilePathObj(p) for p in self.loaded_files]
        if not files:
            QMessageBox.warning(self, "No files", "No FITS files loaded to calibrate.")
            return
        console_window = ConsoleOutputWindow("Calibrating All Files", self)
        console_window.show_and_raise()
        queue = list(files)
        results = []
        cancelled = {"flag": False}
        if not hasattr(self, '_calibration_threads'):
            self._calibration_threads = []
        def next_in_queue():
            if cancelled["flag"]:
                console_window.append_text("\nCalibration cancelled by user.\n")
                return
            if not queue:
                # Check for errors
                errors = [r for r in results if not r.get('success')]
                if errors:
                    console_window.append_text("\nCalibration failed for one or more files. No files were replaced.\n")
                    QMessageBox.critical(self, "Calibration Error", "Calibration failed for one or more files. No files were replaced.")
                    return
                # All succeeded: replace loaded files with calibrated equivalents
                new_files = [r['calibrated_path'] for r in results]
                self.loaded_files = new_files
                self._preloaded_fits.clear()
                for path in new_files:
                    self._preload_fits_file(path)
                self.current_file_index = 0
                self.load_fits(self.loaded_files[0], restore_view=False)
                self.update_navigation_buttons()
                self.update_image_count_label()
                self.update_align_button_visibility()
                self.update_platesolve_button_visibility()
                console_window.append_text("\nAll files calibrated and loaded.\n")
                return
            fits_file = queue.pop(0)
            fits_path = fits_file.path
            console_window.append_text(f"\nCalibrating: {fits_path}\n")
            thread = CalibrationThread(fits_path)
            self._calibration_threads.append(thread)
            thread.output.connect(console_window.append_text)
            def on_finished(result):
                results.append(result)
                if thread in self._calibration_threads:
                    self._calibration_threads.remove(thread)
                next_in_queue()
            thread.finished.connect(on_finished)
            thread.start()
        console_window.cancel_requested.connect(lambda: cancelled.update({"flag": True}))
        next_in_queue()

    def on_sso_row_selected(self, row_index):
        self._sso_highlight_index = row_index
        self.image_label.update()

    def toggle_filelist_window(self):
        if not hasattr(self, '_filelist_window') or self._filelist_window is None:
            def on_row_selected(row):
                # Save current brightness before switching
                if self.image_data is not None:
                    self._last_brightness = self.brightness_slider.value()
                else:
                    self._last_brightness = 50
                # Save current viewport state before switching
                if hasattr(self, '_zoom'):
                    self._last_zoom = self._zoom
                self._last_center = self._get_viewport_center()
                self.current_file_index = row
                self.load_fits(self.loaded_files[row], restore_view=True)
                self.update_navigation_buttons()
                self.update_image_count_label()
                self.update_align_button_visibility()
                self.update_platesolve_button_visibility()
                self.update_close_button_visibility()
                # Update highlight in file list window
                if hasattr(self, '_filelist_window') and self._filelist_window is not None:
                    self._filelist_window.select_row(row)
            self._filelist_window = FileListWindow(self.loaded_files, self.current_file_index, on_row_selected, self)
            self._filelist_window.finished.connect(self._on_filelist_closed)
            self.filelist_action.setChecked(True)
            self._filelist_window.show()
        else:
            self._filelist_window.close()

    def _on_filelist_closed(self):
        self.filelist_action.setChecked(False)
        self._filelist_window = None

    def on_ephemeris_row_selected(self, row_index, ephemeris):
        # Save current brightness before switching
        if self.image_data is not None:
            self._last_brightness = self.brightness_slider.value()
        else:
            self._last_brightness = 50
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
        # Store the marker position for overlay drawing
        self._ephemeris_marker_coords = pixel_coords
        self._overlay_visible = True
        self.update_overlay_button_visibility()
        self.image_label.update()

    def stack_align_wcs(self):
        # TODO: Implement stack alignment on WCS
        pass

    def stack_align_ephemeris(self):
        """Perform motion tracking integration using ephemeris data."""
        if not hasattr(self, '_ephemeris_predicted_positions') or not self._ephemeris_predicted_positions:
            QMessageBox.warning(self, "No Ephemeris Data", 
                              "No ephemeris data available. Please compute orbit data first using the Solar System Objects menu.")
            return
        
        if not self.loaded_files:
            QMessageBox.warning(self, "No Files", "No FITS files are currently loaded in the viewer.")
            return
        
        if len(self.loaded_files) < 2:
            QMessageBox.warning(self, "Insufficient Files", "At least 2 FITS files are required for stacking.")
            return
        
        # Create output directory if it doesn't exist
        import os
        output_dir = "/tmp/astropipes-stacked"
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate output filename
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_object_name = self._ephemeris_object_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
        output_file = os.path.join(output_dir, f"motion_tracked_{safe_object_name}_{timestamp}.fits")
        
        # Create console window for output
        from lib.gui.common.console_window import ConsoleOutputWindow
        console_window = ConsoleOutputWindow("Motion Tracking Integration", self)
        console_window.show_and_raise()
        
        # Start stacking in background thread
        self._stack_thread = QThread()
        from lib.gui.common.orbit_details import MotionTrackingStackWorker
        self._stack_worker = MotionTrackingStackWorker(
            self.loaded_files, 
            self._ephemeris_object_name, 
            output_file,
            console_window
        )
        self._stack_worker.moveToThread(self._stack_thread)
        self._stack_thread.started.connect(self._stack_worker.run)
        
        def on_console_output(text):
            console_window.append_text(text)
        
        def on_finished(success, message):
            if success:
                console_window.append_text(f"\n\033[1;32mMotion tracking integration completed successfully!\033[0m\n\n{message}\n")
                # Add the result to the loaded files in the viewer
                self.loaded_files.append(output_file)
                # Load the file in the viewer
                self.open_and_add_file(output_file)
                # Update navigation buttons and file count
                self.update_navigation_buttons()
                self.update_image_count_label()
            else:
                console_window.append_text(f"\n\033[1;31mMotion tracking integration failed:\033[0m\n\n{message}\n")
            
            self._stack_thread.quit()
            self._stack_thread.wait()
        
        def on_cancel():
            console_window.append_text("\n\033[1;31mCancelling motion tracking integration...\033[0m\n")
            self._stack_thread.quit()
            self._stack_thread.wait()
            console_window.close()
        
        self._stack_worker.console_output.connect(on_console_output)
        self._stack_worker.finished.connect(on_finished)
        console_window.cancel_requested.connect(on_cancel)
        self._stack_thread.start()

    def on_zoom_region_toggled(self, checked):
        self._zoom_region_mode = checked
        self.image_label.set_zoom_region_mode(checked)
        if not checked:
            self._pending_zoom_rect = None
            self.image_label.clear_zoom_region_rect()

    def zoom_to_region(self, img_x0, img_y0, img_x1, img_y1):
        # img_x0, img_y0, img_x1, img_y1 are in image coordinates (float)
        # Compute the rectangle in image coordinates
        x0, x1 = sorted([img_x0, img_x1])
        y0, y1 = sorted([img_y0, img_y1])
        width = x1 - x0
        height = y1 - y0
        if width < 5 or height < 5:
            return  # Ignore too small regions
        # Compute the zoom factor needed to fit this region in the viewport
        viewport = self.scroll_area.viewport()
        if width == 0 or height == 0:
            return
        scale_x = viewport.width() / width
        scale_y = viewport.height() / height
        self._zoom = min(scale_x, scale_y)
        # Center the viewport on the center of the selected region
        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2
        # Update display with new zoom level
        self.update_image_display(keep_zoom=False)  # Use keep_zoom=False to apply new zoom
        # Set viewport center after display is updated
        self._set_viewport_center(center_x, center_y)
        # Optionally, turn off region mode after zoom
        self.zoom_region_action.setChecked(False)

class SkybotWorker(QObject):
    finished = pyqtSignal(list, dict)  # sso_list, pixel_coords_dict
    error = pyqtSignal(str)

    def __init__(self, astrometry_catalog, wcs, image_shape, epoch):
        super().__init__()
        self.astrometry_catalog = astrometry_catalog
        self.wcs = wcs
        self.image_shape = image_shape
        self.epoch = epoch

    def run(self):
        try:
            sso_list = self.astrometry_catalog.get_field_objects(self.wcs, self.image_shape, self.epoch)
            pixel_coords = self.astrometry_catalog.get_object_pixel_coordinates(self.wcs, sso_list)
            pixel_coords_dict = {obj: (x, y) for (obj, x, y) in pixel_coords}
            self.finished.emit(sso_list, pixel_coords_dict)
        except Exception as e:
            self.error.emit(str(e))

class FileListWindow(QDialog):
    def __init__(self, file_paths, current_index, on_row_selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Loaded FITS Files")
        self.resize(400, 400)
        self.table = QTableWidget(self)
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(["Filename"])
        self.table.setRowCount(len(file_paths))
        self.file_paths = file_paths
        self.on_row_selected = on_row_selected
        for i, path in enumerate(file_paths):
            item = QTableWidgetItem(os.path.basename(path))
            item.setToolTip(path)
            self.table.setItem(i, 0, item)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.select_row(current_index)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        self.setLayout(layout)
        # Connect selection change instead of clicks to enable keyboard navigation
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def _row_activated(self, row, col):
        if 0 <= row < len(self.file_paths):
            self.on_row_selected(row)
            # Do not close the window here

    def _on_selection_changed(self, selected, deselected):
        """Handle selection changes to enable keyboard navigation."""
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            if 0 <= row < len(self.file_paths):
                self.on_row_selected(row)

    def select_row(self, row):
        if 0 <= row < self.table.rowCount():
            self.table.selectRow(row)

def main():
    fits_paths = sys.argv[1:] if len(sys.argv) > 1 else []
    app = QApplication(sys.argv)
    viewer = SimpleFITSViewer()
    if fits_paths:
        for i, path in enumerate(fits_paths):
            viewer.open_and_add_file(path)
        # The first file is already loaded by open_and_add_file
        viewer.update_navigation_buttons()
    viewer.show()
    # Ensure zoom to fit is called after the window is visible
    QTimer.singleShot(0, viewer.zoom_to_fit)
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 