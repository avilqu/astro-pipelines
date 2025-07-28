import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from PyQt6.QtWidgets import QApplication, QMainWindow, QScrollArea, QToolBar, QDialog
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtWidgets import QStatusBar, QSizePolicy, QLabel

from lib.gui.viewer.overlay import ImageLabel
from lib.gui.viewer.navigation import NavigationMixin
from lib.gui.viewer.catalogs import CatalogSearchMixin
from lib.gui.viewer.image_operations import ImageOperationsMixin
from lib.gui.viewer.files import FileOperationsMixin
from lib.gui.viewer.overlay import OverlayMixin
from lib.gui.viewer.integration import IntegrationMixin
from lib.gui.viewer.display import DisplayMixin
from lib.gui.viewer.histogram import HistogramController
from lib.gui.viewer.toolbar import ToolbarController
from lib.sci.catalogs import AstrometryCatalog
from lib.sci.sources import detect_sources_in_image, DetectedSource
from lib.gui.common.sources_window import SourcesResultWindow
from lib.gui.common.console_window import ConsoleOutputWindow, RealTimeStringIO
from lib.gui.common.source_detection_dialog import SourceDetectionDialog

import logging
import threading
import io
import sys


class SourceDetectionThread(QThread):
    """Thread for running source detection with console output."""
    
    # Signals
    detection_complete = pyqtSignal(object)  # SourceDetectionResult
    output_received = pyqtSignal(str)  # Console output
    error_occurred = pyqtSignal(str)  # Error message
    
    def __init__(self, image_data, wcs=None, timeout=300, **kwargs):  # 5 minute timeout
        super().__init__()
        self.image_data = image_data
        self.wcs = wcs
        self.kwargs = kwargs
        self.timeout = timeout
        self._stop_requested = False
        
    def run(self):
        """Run source detection in a separate thread."""
        try:
            # Capture stdout and stderr
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            
            # Create a custom stream that emits signals
            class SignalStream:
                def __init__(self, signal):
                    self.signal = signal
                    self.buffer = ""
                
                def write(self, text):
                    self.buffer += text
                    if text.endswith('\n'):
                        self.signal.emit(self.buffer)
                        self.buffer = ""
                
                def flush(self):
                    if self.buffer:
                        self.signal.emit(self.buffer)
                        self.buffer = ""
            
            # Redirect stdout and stderr
            signal_stdout = SignalStream(self.output_received)
            signal_stderr = SignalStream(self.output_received)
            sys.stdout = signal_stdout
            sys.stderr = signal_stderr
            
            # Also capture logging output
            class SignalHandler(logging.Handler):
                def __init__(self, signal):
                    super().__init__()
                    self.signal = signal
                
                def emit(self, record):
                    msg = self.format(record) + '\n'
                    self.signal.emit(msg)
            
            # Add signal handler to root logger
            signal_handler = SignalHandler(self.output_received)
            signal_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
            logging.getLogger().addHandler(signal_handler)
            
            try:
                # Run source detection with timeout using threading.Timer
                import threading
                import queue
                
                # Create a queue to communicate between threads
                result_queue = queue.Queue()
                error_queue = queue.Queue()
                
                def run_detection():
                    try:
                        # Debug: log the parameters being used
                        print(f"DEBUG: Using parameters: {self.kwargs}")
                        result = detect_sources_in_image(self.image_data, wcs=self.wcs, **self.kwargs)
                        result_queue.put(result)
                    except Exception as e:
                        error_queue.put(e)
                
                # Start detection in a separate thread
                detection_thread = threading.Thread(target=run_detection)
                detection_thread.daemon = True
                detection_thread.start()
                
                # Wait for result with timeout
                try:
                    result = result_queue.get(timeout=self.timeout)
                    self.detection_complete.emit(result)
                except queue.Empty:
                    # Timeout occurred
                    self.error_occurred.emit(f"Source detection timed out after {self.timeout} seconds")
                except Exception as e:
                    # Check if there was an error in the detection thread
                    try:
                        error = error_queue.get_nowait()
                        self.error_occurred.emit(str(error))
                    except queue.Empty:
                        self.error_occurred.emit(str(e))
                
            finally:
                # Restore original streams
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                logging.getLogger().removeHandler(signal_handler)
                
        except Exception as e:
            self.error_occurred.emit(str(e))
    
    def stop(self):
        """Request thread to stop."""
        self._stop_requested = True


class FITSViewer(NavigationMixin, CatalogSearchMixin, ImageOperationsMixin, FileOperationsMixin, OverlayMixin, IntegrationMixin, DisplayMixin, QMainWindow):
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
        
        # Initialize toolbar controller first (creates the toolbar)
        self.toolbar_controller = ToolbarController(self)
        
        # Initialize histogram controller (needs access to toolbar)
        self.histogram_controller = HistogramController(self)
        
        # Connect histogram control signals
        self.toolbar_controller.connect_histogram_signals()
        
        # Get references to toolbar and navigation elements
        self.toolbar = self.toolbar_controller.toolbar
        self.prev_action = self.toolbar_controller.prev_action
        self.next_action = self.toolbar_controller.next_action
        self.prev_button = self.toolbar_controller.prev_button
        self.next_button = self.toolbar_controller.next_button
        self.play_pause_button = self.toolbar_controller.play_pause_button
        self.image_count_label = self.toolbar_controller.image_count_label
        self.load_action = self.toolbar_controller.load_action
        self.close_action = self.toolbar_controller.close_action
        self.reset_zoom_action = self.toolbar_controller.reset_zoom_action
        self.zoom_to_fit_action = self.toolbar_controller.zoom_to_fit_action
        self.zoom_region_action = self.toolbar_controller.zoom_region_action
        self.simbad_button = self.toolbar_controller.simbad_button
        self.sso_button = self.toolbar_controller.sso_button
        self.overlay_toggle_action = self.toolbar_controller.overlay_toggle_action
        self.calibrate_button = self.toolbar_controller.calibrate_button
        self.platesolve_button = self.toolbar_controller.platesolve_button
        self.header_button = self.toolbar_controller.header_button
        self.integration_button = self.toolbar_controller.integration_button
        self.filelist_action = self.toolbar_controller.filelist_action
        
        # Navigation state
        self.playing = self.toolbar_controller.playing
        self.blink_timer = self.toolbar_controller.blink_timer
        self.play_icon = self.toolbar_controller.play_icon
        self.pause_icon = self.toolbar_controller.pause_icon
        # Remove sidebar and use only scroll_area as central widget
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        # Ignore wheel events so they are not used for scrolling
        self.scroll_area.wheelEvent = lambda event: event.ignore()
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
        self._sso_highlight_index = None
        self._source_highlight_index = None  # Track highlighted source
        self._source_overlay = None  # Store source overlay data
        self._zoom_region_mode = False  # Track if zoom-to-region is active
        self._pending_zoom_rect = None  # Store the last selected rectangle
        if fits_path:
            self.open_and_add_file(fits_path)
        self.update_overlay_button_visibility()
        self.update_navigation_buttons()
        self.update_align_button_visibility()
        self.update_platesolve_button_visibility()
        self.update_close_button_visibility()
        
        # Set initial button states (disabled if no image loaded)
        if not fits_path:
            self.update_button_states_for_no_image()
        # Status bar: coordinates (left), pixel value (right)
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_coord_label = QLabel("No WCS", self)
        self.status_coord_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.status_bar.addWidget(self.status_coord_label)
        self.status_pixel_label = QLabel("--", self)
        self.status_pixel_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.status_bar.addPermanentWidget(self.status_pixel_label)

    def detect_sources_action(self):
        """Slot for toolbar: detect sources in the current image and show results window."""
        if self.image_data is None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Image", "No image loaded for source detection.")
            return
        
        # Use WCS if available
        wcs = getattr(self, 'wcs', None)
        
        # Calculate default parameters based on image size
        img_height, img_width = self.image_data.shape
        max_dim = max(img_height, img_width)
        
        # Determine default parameters based on image size
        if max_dim > 3000:
            # For very large images, use very conservative parameters
            bg_box_size = 200
            bg_filter_size = 7
            threshold_sigma = 3.0
            npixels = 10
            min_area = 20
            min_snr = 5.0
            deblend = False
        elif max_dim > 1000:
            # For large images, use conservative parameters
            bg_box_size = min(100, max_dim // 20)
            bg_filter_size = 5
            threshold_sigma = 2.5
            npixels = 8
            min_area = 15
            min_snr = 4.0
            deblend = False
        else:
            # For smaller images, use moderately conservative parameters
            bg_box_size = 25
            bg_filter_size = 3
            threshold_sigma = 2.0
            npixels = 5
            min_area = 8
            min_snr = 3.0
            deblend = True
        
        # Create default parameters for dialog
        default_params = {
            'threshold_sigma': threshold_sigma,
            'npixels': npixels,
            'min_area': min_area,
            'min_snr': min_snr,
            'max_area': 1000,
            'min_eccentricity': 0.0,
            'max_eccentricity': 0.9,
            'deblend': deblend,
            'connectivity': 8,
            'background_box_size': bg_box_size,
            'background_filter_size': bg_filter_size
        }
        
        # Show parameter dialog
        dialog = SourceDetectionDialog(self, default_params)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return  # User cancelled
        
        # Get parameters from dialog
        params = dialog.get_parameters()
        
        # Debug: log the parameters being passed to the thread
        print(f"DEBUG: Parameters from dialog: {params}")
        
        # Create console window for real-time output
        self.console_window = ConsoleOutputWindow("Source Detection Progress", self)
        self.console_window.show_and_raise()
        
        # Connect console window signals
        self.console_window.cancel_requested.connect(self.cancel_source_detection)
        
        # Create detection thread with user-selected parameters
        timeout = 600 if max_dim > 2000 else 300  # 10 minutes for very large images, 5 for others
        
        self.detection_thread = SourceDetectionThread(
            self.image_data,
            wcs=wcs,
            timeout=timeout,
            **params
        )
        
        # Connect thread signals
        self.detection_thread.output_received.connect(self.console_window.append_text)
        self.detection_thread.detection_complete.connect(self.on_detection_complete)
        self.detection_thread.error_occurred.connect(self.on_detection_error)
        
        # Start detection
        self.console_window.append_text("Starting source detection...\n")
        self.console_window.append_text(f"Image data shape: {self.image_data.shape}\n")
        self.console_window.append_text(f"Image data min/max: {self.image_data.min():.2f} / {self.image_data.max():.2f}\n")
        self.console_window.append_text(f"Image data mean/std: {self.image_data.mean():.2f} / {self.image_data.std():.2f}\n")
        
        if wcs is not None:
            self.console_window.append_text(f"WCS available: {wcs}\n")
        else:
            self.console_window.append_text("No WCS available\n")
        
        self.console_window.append_text(f"Using user-selected parameters:\n")
        self.console_window.append_text(f"  Background box size: {params['background_box_size']}\n")
        self.console_window.append_text(f"  Background filter size: {params['background_filter_size']}\n")
        self.console_window.append_text(f"  Threshold sigma: {params['threshold_sigma']} (higher = fewer sources)\n")
        self.console_window.append_text(f"  Min pixels: {params['npixels']} (more = fewer sources)\n")
        self.console_window.append_text(f"  Min area: {params['min_area']} (larger = fewer sources)\n")
        self.console_window.append_text(f"  Min SNR: {params['min_snr']} (higher = fewer sources)\n")
        self.console_window.append_text(f"  Max area: {params['max_area']} (filters out extended objects)\n")
        self.console_window.append_text(f"  Max eccentricity: {params['max_eccentricity']} (filters out very elongated objects)\n")
        self.console_window.append_text(f"  Deblend: {params['deblend']}\n")
        self.console_window.append_text(f"  Connectivity: {params['connectivity']}\n")
        self.console_window.append_text(f"Timeout set to {timeout} seconds\n")
        self.console_window.append_text("=" * 50 + "\n")
        self.console_window.append_text("Starting detection process...\n")
        self.console_window.append_text("Using user-selected parameters for detection.\n")
        self.console_window.append_text("You can cancel at any time using the Cancel button.\n")
        self.console_window.append_text("=" * 50 + "\n")
        
        # Start a timer to show progress
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self.show_progress)
        self.progress_timer.start(5000)  # Show progress every 5 seconds
        
        self.detection_thread.start()
    
    def show_progress(self):
        """Show progress indicator."""
        self.console_window.append_text("Still processing... (Press Cancel if taking too long)\n")
    
    def cancel_source_detection(self):
        """Cancel the source detection process."""
        if hasattr(self, 'detection_thread') and self.detection_thread.isRunning():
            self.detection_thread.stop()
            self.detection_thread.quit()
            self.detection_thread.wait()
            self.console_window.append_text("\nSource detection cancelled by user.\n")
        
        # Stop progress timer
        if hasattr(self, 'progress_timer'):
            self.progress_timer.stop()
    
    def on_detection_complete(self, result):
        """Handle completion of source detection."""
        # Stop progress timer
        if hasattr(self, 'progress_timer'):
            self.progress_timer.stop()
        
        self.console_window.append_text("\n" + "=" * 50 + "\n")
        self.console_window.append_text(f"Detection result: {result}\n")
        
        if not result.success:
            self.console_window.append_text(f"Detection failed: {result.message}\n")
            return
        
        if not result.sources:
            self.console_window.append_text("No sources detected above the threshold. Try adjusting the detection parameters.\n")
            return
        
        # Set up source overlay
        if result.sources:
            # Convert source coordinates to pixel coordinates for overlay
            pixel_coords_list = []
            for source in result.sources:
                # Use the x, y coordinates from the source
                pixel_coords_list.append((source.x, source.y))
            
            # Store source overlay data
            self._source_overlay = (result.sources, pixel_coords_list)
            self._source_highlight_index = None  # Reset highlight
        
        # Show results window
        self.sources_result_window = SourcesResultWindow(result.sources, parent=self)
        
        # Connect source row selection to highlighting
        self.sources_result_window.source_row_selected.connect(self.on_source_row_selected)
        
        self.sources_result_window.show()
        
        self.console_window.append_text(f"Detected {len(result.sources)} sources\n")
        self.console_window.append_text("Results window opened.\n")
        self.console_window.append_text("Click on a row in the results window to highlight the corresponding source on the image.\n")
    
    def on_detection_error(self, error_message):
        """Handle errors during source detection."""
        # Stop progress timer
        if hasattr(self, 'progress_timer'):
            self.progress_timer.stop()
        
        self.console_window.append_text(f"\nError during source detection: {error_message}\n")
    
    def on_source_row_selected(self, row_index):
        """Handle source row selection for highlighting."""
        self._source_highlight_index = row_index
        self.image_label.update()

def main():
    fits_paths = sys.argv[1:] if len(sys.argv) > 1 else []
    app = QApplication(sys.argv)
    viewer = FITSViewer()
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