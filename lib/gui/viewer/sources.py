import sys
import os
import logging
import threading
import queue
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import QDialog, QMessageBox
from lib.sci.sources import detect_sources_in_image
from lib.gui.common.sources_window import SourcesResultWindow
from lib.gui.common.console_window import ConsoleOutputWindow
from lib.gui.common.source_detection_dialog import SourceDetectionDialog
from lib.gui.common.gaia_detection_results_window import GaiaDetectionResultWindow
from lib.gui.viewer.catalogs import GaiaSearchDialog


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


class SourceDetectionMixin:
    """Mixin class for source detection functionality."""
    
    def detect_sources_action(self):
        """Slot for toolbar: detect sources in the current image and show results window."""
        if self.image_data is None:
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
            if hasattr(self, 'overlay_toolbar_controller'):
                self.overlay_toolbar_controller.update_overlay_button_visibility()
        
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

    def detect_gaia_stars_in_image(self):
        """Detect Gaia stars in the image and cross-match with detected sources."""
        if self.image_data is None:
            QMessageBox.warning(self, "No Image", "No image loaded for Gaia star detection.")
            return
        
        if self.wcs is None:
            QMessageBox.warning(self, "No WCS", "No WCS information available. Please solve the image first.")
            return
        
        # Ask user for magnitude limit using existing dialog
        gaia_dialog = GaiaSearchDialog(self)
        if gaia_dialog.exec() != QDialog.DialogCode.Accepted or not gaia_dialog.result:
            return  # User cancelled
        
        gaia_objects, pixel_coords_dict = gaia_dialog.result
        
        if not gaia_objects:
            QMessageBox.information(self, "No Gaia Stars", "No Gaia stars found in the field.")
            return
        
        # Now detect sources in the image using the same default parameters as regular source detection
        self.console_window = ConsoleOutputWindow("Gaia Star Detection Progress", self)
        self.console_window.show_and_raise()
        
        # Connect console window signals
        self.console_window.cancel_requested.connect(self.cancel_source_detection)
        
        # Use the same default parameters calculation as regular source detection
        img_height, img_width = self.image_data.shape
        max_dim = max(img_height, img_width)
        
        # Determine default parameters based on image size (same as regular detection)
        if max_dim > 3000:
            # For very large images, use very conservative parameters
            bg_box_size = 200
            bg_filter_size = 7
            threshold_sigma = 5.0  # More restrictive than regular detection
            npixels = 10
            min_area = 30  # More restrictive than regular detection
            min_snr = 5.0
            deblend = False
        elif max_dim > 1000:
            # For large images, use conservative parameters
            bg_box_size = min(100, max_dim // 20)
            bg_filter_size = 5
            threshold_sigma = 5.0  # More restrictive than regular detection
            npixels = 8
            min_area = 30  # More restrictive than regular detection
            min_snr = 4.0
            deblend = False
        else:
            # For smaller images, use moderately conservative parameters
            bg_box_size = 25
            bg_filter_size = 3
            threshold_sigma = 5.0  # More restrictive than regular detection
            npixels = 5
            min_area = 30  # More restrictive than regular detection
            min_snr = 3.0
            deblend = True
        
        # Use the same default parameters as regular source detection
        params = {
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
        
        # Create detection thread with same timeout as regular detection
        timeout = 600 if max_dim > 2000 else 300  # 10 minutes for very large images, 5 for others
        
        self.detection_thread = SourceDetectionThread(
            self.image_data,
            wcs=self.wcs,
            timeout=timeout,
            **params
        )
        
        # Connect thread signals
        self.detection_thread.output_received.connect(self.console_window.append_text)
        self.detection_thread.detection_complete.connect(
            lambda result: self.on_gaia_detection_complete(result, gaia_objects, pixel_coords_dict)
        )
        self.detection_thread.error_occurred.connect(self.on_detection_error)
        
        # Start detection
        self.console_window.append_text("Starting source detection for Gaia cross-matching...\n")
        self.console_window.append_text(f"Found {len(gaia_objects)} Gaia stars in the field.\n")
        self.console_window.append_text("Now detecting sources in the image using optimized settings...\n")
        self.console_window.append_text(f"Using parameters: threshold_sigma={threshold_sigma}, npixels={npixels}, min_area={min_area}, min_snr={min_snr}\n")
        self.console_window.append_text("Note: Using more restrictive parameters for Gaia cross-matching to find fewer, higher-quality sources.\n")
        
        # Start a timer to show progress
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self.show_progress)
        self.progress_timer.start(5000)  # Show progress every 5 seconds
        
        self.detection_thread.start()
    
    def on_gaia_detection_complete(self, detection_result, gaia_objects, pixel_coords_dict):
        """Handle completion of source detection for Gaia cross-matching."""
        # Stop progress timer
        if hasattr(self, 'progress_timer'):
            self.progress_timer.stop()
        
        self.console_window.append_text("\n" + "=" * 50 + "\n")
        self.console_window.append_text(f"Detection result: {detection_result}\n")
        
        if not detection_result.success:
            self.console_window.append_text(f"Detection failed: {detection_result.message}\n")
            return
        
        if not detection_result.sources:
            self.console_window.append_text("No sources detected above the threshold.\n")
            return
        
        # Cross-match Gaia stars with detected sources
        self.console_window.append_text("Cross-matching Gaia stars with detected sources...\n")
        
        gaia_detection_results = []
        match_tolerance_arcsec = 2.0  # 2 arcsecond tolerance for matching
        
        for gaia_obj in gaia_objects:
            gaia_ra = gaia_obj.ra
            gaia_dec = gaia_obj.dec
            
            # Find the closest detected source to this Gaia star
            closest_source = None
            min_distance_arcsec = float('inf')
            
            for detected_source in detection_result.sources:
                if detected_source.ra is None or detected_source.dec is None:
                    continue
                
                # Calculate angular distance in arcseconds
                import numpy as np
                from astropy.coordinates import SkyCoord
                from astropy import units as u
                
                gaia_coord = SkyCoord(ra=gaia_ra*u.deg, dec=gaia_dec*u.deg)
                detected_coord = SkyCoord(ra=detected_source.ra*u.deg, dec=detected_source.dec*u.deg)
                
                separation = gaia_coord.separation(detected_coord)
                distance_arcsec = separation.arcsec
                
                if distance_arcsec < min_distance_arcsec:
                    min_distance_arcsec = distance_arcsec
                    closest_source = detected_source
            
            # If we found a match within tolerance, add to results
            if closest_source is not None and min_distance_arcsec <= match_tolerance_arcsec:
                gaia_detection_results.append((gaia_obj, closest_source, min_distance_arcsec))
                self.console_window.append_text(
                    f"Matched Gaia {gaia_obj.source_id} (mag {gaia_obj.magnitude:.2f}) "
                    f"with source {closest_source.id} (distance: {min_distance_arcsec:.2f} arcsec)\n"
                )
        
        self.console_window.append_text(f"\nFound {len(gaia_detection_results)} matches.\n")
        
        if not gaia_detection_results:
            self.console_window.append_text("No Gaia stars matched with detected sources.\n")
            return
        
        # Show results window
        self.gaia_detection_result_window = GaiaDetectionResultWindow(gaia_detection_results, parent=self)
        
        # Connect source row selection to highlighting
        self.gaia_detection_result_window.gaia_detection_row_selected.connect(self.on_gaia_detection_row_selected)
        
        self.gaia_detection_result_window.show()
        
        # Set up overlay for matched Gaia stars
        self._gaia_detection_overlay = gaia_detection_results
        self._gaia_detection_highlight_index = None  # Reset highlight
        self._overlay_visible = True
        if hasattr(self, 'overlay_toolbar_controller'):
            self.overlay_toolbar_controller.update_overlay_button_visibility()
        
        self.image_label.update()
        
        self.console_window.append_text("Results window opened.\n")
        self.console_window.append_text("Overlay added to image.\n")
        self.console_window.append_text("=" * 50 + "\n")
    
    def on_gaia_detection_row_selected(self, row_index):
        """Handle Gaia detection row selection for highlighting."""
        self._gaia_detection_highlight_index = row_index
        self.image_label.update()
