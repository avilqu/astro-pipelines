"""
Refactored main GUI for Astro-Pipelines (formerly gui_pyqt_refactored.py)
"""

import sys
import argparse
import numpy as np
from astropy.io import fits
from astropy.time import Time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QFileDialog, 
                             QScrollArea, QLabel, QStatusBar, QSizePolicy, QDialog, QHBoxLayout)
from PyQt6.QtCore import Qt
from astropy.coordinates import SkyCoord
from astropy import units as u

# Import our refactored modules
from .gui_widgets import ImageLabel, HeaderDialog, SolarSystemObjectsDialog, SIMBADSearchDialog, SolvingProgressDialog, SSOProgressDialog
from .gui_image_processing import (create_image_object, add_object_markers, get_cached_zoom,
                                  calculate_bit_depth, apply_auto_stretch, apply_no_stretch)
from .gui_control_panel import create_control_panel, update_image_info, set_solve_button_solving, set_sso_button_searching
from .astrometry import AstrometryCatalog
from .solver import solve_offline
from .helpers import (extract_coordinates_from_header, calculate_field_radius, 
                     validate_wcs_solution, create_solver_options)
import config


class FITSImageViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Astro-Pipelines - PyQt6')
        self.setGeometry(100, 100, 1200, 800)
        
        # Image data and display variables
        self.image_data = None
        self.pixmap = None
        self.base_pixmap = None  # Cache the base pixmap without scaling
        self.scale_factor = 1.0
        self.current_header = None
        self.wcs = None
        self.bit_depth = None
        
        # Performance optimization: cache display parameters
        self.display_min = None
        self.display_max = None
        self.last_stretch_state = None  # Track if stretch changed
        
        # Zoom cache for performance
        self.zoom_cache = {}  # Cache scaled pixmaps for common zoom levels
        self.max_cache_size = 10  # Maximum number of cached zoom levels
        
        # Astrometry and solar system objects
        self.astrometry_catalog = AstrometryCatalog()
        self.solar_system_objects = []
        self.object_pixel_coords = []
        self.show_objects = False
        self.objects_dialog = None
        self.header_dialog = None
        
        # SIMBAD objects
        self.simbad_object = None
        self.simbad_pixel_coords = None
        self.show_simbad_object = False
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        
        # Create control panel
        control_panel = create_control_panel(self)
        layout.addWidget(control_panel)
        
        # Create scroll area for image
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.scroll_area, 1)
        
        # Create custom image label
        self.image_label = ImageLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(800, 600)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.image_label.setStyleSheet("QLabel { background-color: black; }")
        self.image_label.setText("No image loaded")
        self.scroll_area.setWidget(self.image_label)
        
        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.coord_label = QLabel("No WCS - coordinates unavailable")
        self.pixel_value_label = QLabel("--")
        self.status_bar.addWidget(self.coord_label)
        self.status_bar.addPermanentWidget(self.pixel_value_label)

    def toggle_stretch(self):
        """Toggle between no stretch and auto stretch"""
        if self.stretch_button.isChecked():
            self.apply_auto_stretch()
        else:
            self.apply_no_stretch()

    def apply_no_stretch(self):
        """Apply no histogram stretching - use actual data min/max"""
        if self.image_data is not None:
            self.display_min, self.display_max = apply_no_stretch(self.image_data)
            self.update_image_display()

    def apply_auto_stretch(self):
        """Apply auto histogram stretching using bright stretch code"""
        if self.image_data is not None:
            self.display_min, self.display_max = apply_auto_stretch(self.image_data)
            self.update_image_display()

    def open_file(self):
        """Open a FITS file and display it"""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open FITS File",
            "",
            "FITS Files (*.fits);;All Files (*.*)"
        )
        
        if filepath:
            self.load_file_from_path(filepath)

    def load_file_from_path(self, filepath):
        """Load a FITS file from a given filepath"""
        try:
            hdu_list = fits.open(filepath)
            image_data = hdu_list[0].data
            self.load_image(image_data, filepath)
            update_image_info(hdu_list, self)
            self.current_header = hdu_list[0].header
            self.current_file_path = filepath  # Store the file path
            self.header_button.setEnabled(True)  # Enable header button
            
            hdu_list.close()
        except Exception as e:
            print(f"Error opening file: {e}")
            self.header_button.setEnabled(False)  # Disable header button on error
            self.objects_button.setEnabled(False)  # Disable objects button on error
            self.solve_button.setEnabled(False)  # Disable solve button on error

    def clear_zoom_cache(self):
        """Clear the zoom cache when image changes"""
        self.zoom_cache.clear()

    def update_image_display(self):
        """Update the displayed image with current scale and position - optimized version"""
        if self.base_pixmap is None or self.image_data is None:
            return
        
        # Check if stretch settings changed
        current_stretch = (self.display_min, self.display_max)
        if current_stretch != self.last_stretch_state:
            # Recreate base pixmap with new stretch settings
            self.base_pixmap = create_image_object(self.image_data, self.display_min, self.display_max)
            self.last_stretch_state = current_stretch
            # Clear zoom cache when stretch changes
            self.clear_zoom_cache()
        
        # Start with base pixmap
        working_pixmap = self.base_pixmap
        
        # Add object markers if enabled
        if self.show_objects and self.object_pixel_coords:
            working_pixmap = working_pixmap.copy()
            working_pixmap = add_object_markers(
                working_pixmap, self.object_pixel_coords, self.show_objects,
                self.simbad_object, self.simbad_pixel_coords, self.show_simbad_object, 
                self.scale_factor
            )
        elif self.show_simbad_object and self.simbad_object:
            working_pixmap = working_pixmap.copy()
            working_pixmap = add_object_markers(
                working_pixmap, self.object_pixel_coords, self.show_objects,
                self.simbad_object, self.simbad_pixel_coords, self.show_simbad_object, 
                self.scale_factor
            )
        
        # Get cached or create scaled pixmap
        scaled_pixmap = get_cached_zoom(self.scale_factor, working_pixmap, self.zoom_cache, self.max_cache_size)
        
        # Set the pixmap
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.setFixedSize(scaled_pixmap.size())
        
        # Store current pixmap for coordinate calculations
        self.pixmap = scaled_pixmap

    def load_image(self, image_data=None, title=None):
        """Load and display an image - optimized version"""
        self.image_data = image_data
        
        # Calculate bit depth information
        self.bit_depth = calculate_bit_depth(image_data)
        
        # Create base pixmap (without scaling)
        self.base_pixmap = create_image_object(image_data)
        self.pixmap = self.base_pixmap
        self.scale_factor = 1.0
        self.last_stretch_state = None
        
        # Clear zoom cache for new image
        self.clear_zoom_cache()
        
        self.update_image_display()
        
        if title:
            self.setWindowTitle(f'Astro-Pipelines - {title}')

    def zoom_in(self):
        """Zoom in by 25% (deprecated - use zoom_in_at_center)"""
        self.scale_factor *= 1.25
        self.update_image_display()

    def zoom_out(self):
        """Zoom out by 25% (deprecated - use zoom_out_at_center)"""
        self.scale_factor /= 1.25
        if self.scale_factor < 0.1:
            self.scale_factor = 0.1
        self.update_image_display()

    def zoom_in_at_center(self):
        """Zoom in by 25% keeping the center of the viewport fixed"""
        self._zoom_at_center(1.25)

    def zoom_out_at_center(self):
        """Zoom out by 25% keeping the center of the viewport fixed"""
        self._zoom_at_center(1/1.25)

    def _zoom_at_center(self, zoom_factor):
        """Helper method to zoom while keeping the center of the viewport fixed"""
        if self.base_pixmap is None:
            return
            
        # Get current scroll positions
        h_scroll = self.scroll_area.horizontalScrollBar()
        v_scroll = self.scroll_area.verticalScrollBar()
        
        # Calculate the center of the current viewport
        viewport_center_x = h_scroll.value() + self.scroll_area.viewport().width() // 2
        viewport_center_y = v_scroll.value() + self.scroll_area.viewport().height() // 2
        
        # Calculate the center of the image label
        label_center_x = self.image_label.width() // 2
        label_center_y = self.image_label.height() // 2
        
        # Calculate the pixel in the original image coordinates at the viewport center
        if self.pixmap:
            pixmap_size = self.pixmap.size()
            label_size = self.image_label.size()
            
            # Calculate position within the pixmap
            x_offset = (label_size.width() - pixmap_size.width()) // 2
            y_offset = (label_size.height() - pixmap_size.height()) // 2
            
            # Calculate the pixel position relative to the image label
            pixmap_x = viewport_center_x - x_offset
            pixmap_y = viewport_center_y - y_offset
            
            # Convert to original image coordinates
            orig_x = pixmap_x / self.scale_factor
            orig_y = pixmap_y / self.scale_factor
        
        # Apply zoom
        old_scale = self.scale_factor
        self.scale_factor *= zoom_factor
        if self.scale_factor < 0.1:
            self.scale_factor = 0.1
        
        # Update the image display
        self.update_image_display()
        
        # Calculate new scroll positions to keep the same pixel centered
        if self.pixmap and (0 <= pixmap_x < pixmap_size.width() and 0 <= pixmap_y < pixmap_size.height()):
            # Calculate the new position of the same pixel after zooming
            new_pixmap_x = orig_x * self.scale_factor
            new_pixmap_y = orig_y * self.scale_factor
            
            # Calculate the new scroll positions to center this pixel
            new_h_scroll = new_pixmap_x - self.scroll_area.viewport().width() // 2
            new_v_scroll = new_pixmap_y - self.scroll_area.viewport().height() // 2
            
            # Apply the new scroll positions
            h_scroll.setValue(int(new_h_scroll))
            v_scroll.setValue(int(new_v_scroll))

    def reset_zoom(self):
        """Reset zoom to 100%"""
        self.scale_factor = 1.0
        self.update_image_display()

    def show_header(self):
        """Show the FITS header dialog"""
        if self.current_header is not None:
            # Create or show the header dialog (non-modal)
            if self.header_dialog is None or not self.header_dialog.isVisible():
                self.header_dialog = HeaderDialog(self.current_header, self)
                self.header_dialog.show()
            else:
                # Bring existing dialog to front
                self.header_dialog.raise_()
                self.header_dialog.activateWindow()

    def toggle_solar_system_objects(self):
        """Toggle solar system objects display - search on first click, then toggle dialog/markers"""
        if not self.solar_system_objects:
            # First time - perform the search
            self.search_solar_system_objects()
        else:
            # Subsequent clicks - toggle dialog and markers
            if self.objects_dialog and self.objects_dialog.isVisible():
                # Hide dialog and markers
                self.objects_dialog.hide()
                self.show_objects = False
                self.update_image_display()
            else:
                # Show dialog and markers
                if self.objects_dialog:
                    self.objects_dialog.show()
                else:
                    # Recreate dialog if it was closed
                    self.objects_dialog = SolarSystemObjectsDialog(self.solar_system_objects, self)
                    self.objects_dialog.show()
                self.show_objects = True
                self.update_image_display()

    def search_solar_system_objects(self):
        """Search for solar system objects in the current field with progress dialog"""
        if self.wcs is None or self.image_data is None:
            print("No WCS information available for solar system object search")
            return
        
        try:
            # Create and show progress dialog
            progress_dialog = SSOProgressDialog(self)
            
            # Set SSO button to searching state
            set_sso_button_searching(self, True)
            
            # Show the dialog
            progress_dialog.show()
            
            # Run the search process in a separate thread to avoid blocking the GUI
            from PyQt6.QtCore import QThread, pyqtSignal
            
            class SSOSearchThread(QThread):
                finished = pyqtSignal(bool)
                output_signal = pyqtSignal(str)
                show_objects_dialog = pyqtSignal(list)  # Signal to show objects dialog
                
                def __init__(self, parent_viewer, progress_dialog):
                    super().__init__()
                    self.parent_viewer = parent_viewer
                    self.progress_dialog = progress_dialog
                
                def run(self):
                    try:
                        self._search_with_signals()
                        self.finished.emit(True)
                    except Exception as e:
                        self.output_signal.emit(f"Error in SSO search thread: {e}")
                        self.progress_dialog.search_finished(False)
                        self.finished.emit(False)
                
                def _search_with_signals(self):
                    """Search for solar system objects with signal-based output"""
                    try:
                        self.output_signal.emit("Starting solar system object search...")
                        
                        # Get observation time from header
                        epoch = self.parent_viewer._get_observation_time()
                        if epoch is None:
                            self.output_signal.emit("Could not determine observation time from header")
                            self.output_signal.emit("Using current time as fallback")
                            epoch = Time.now()
                        
                        self.output_signal.emit(f"Observation time: {epoch.iso}")
                        
                        # Get field center and radius
                        center_x = self.parent_viewer.image_data.shape[1] / 2
                        center_y = self.parent_viewer.image_data.shape[0] / 2
                        center_coords = self.parent_viewer.wcs.pixel_to_world(center_x, center_y)
                        ra_center = center_coords.ra.deg
                        dec_center = center_coords.dec.deg
                        
                        self.output_signal.emit(f"Field center: RA={ra_center:.4f}°, Dec={dec_center:.4f}°")
                        
                        # Calculate field radius
                        corners = self.parent_viewer.wcs.calc_footprint()
                        if corners is not None:
                            max_radius = 0
                            for corner_ra, corner_dec in corners:
                                dra = (corner_ra - ra_center) * np.cos(np.radians(dec_center))
                                ddec = corner_dec - dec_center
                                radius = np.sqrt(dra**2 + ddec**2)
                                max_radius = max(max_radius, radius)
                            search_radius = max_radius + 0.1
                        else:
                            search_radius = 1.1
                        
                        self.output_signal.emit(f"Search radius: {search_radius:.3f}°")
                        self.output_signal.emit("")
                        
                        # Check if search was cancelled
                        if self.progress_dialog.search_cancelled:
                            self.output_signal.emit("Search cancelled by user.")
                            return
                        
                        # Perform the cone search
                        self.output_signal.emit("Making API call to Skybot service...")
                        self.output_signal.emit("This may take a few seconds...")
                        
                        objects = self.parent_viewer.astrometry_catalog.skybot_cone_search(
                            ra_center, dec_center, search_radius, epoch
                        )
                        
                        # Check if search was cancelled
                        if self.progress_dialog.search_cancelled:
                            self.output_signal.emit("Search cancelled by user.")
                            return
                        
                        self.output_signal.emit(f"Found {len(objects)} objects in search area")
                        
                        # Filter objects to only include those actually in the image
                        filtered_objects = []
                        for obj in objects:
                            # Check if search was cancelled
                            if self.progress_dialog.search_cancelled:
                                self.output_signal.emit("Search cancelled by user.")
                                return
                            
                            # Convert object coordinates to pixel coordinates
                            try:
                                obj_coords = SkyCoord(ra=obj.ra*u.deg, dec=obj.dec*u.deg)
                                pixel_result = self.parent_viewer.wcs.world_to_pixel(obj_coords)
                                if hasattr(pixel_result, '__len__') and len(pixel_result) == 2:
                                    pixel_x, pixel_y = pixel_result
                                else:
                                    pixel_x, pixel_y = pixel_result[0], pixel_result[1]
                                # Check if object is within image bounds
                                if (0 <= pixel_x <= self.parent_viewer.image_data.shape[1] and 
                                    0 <= pixel_y <= self.parent_viewer.image_data.shape[0]):
                                    filtered_objects.append(obj)
                                    self.output_signal.emit(f"Object in field: {obj.name}")
                            except Exception as e:
                                self.output_signal.emit(f"Error checking if object {obj.name} is in field: {e}")
                                continue
                        
                        self.output_signal.emit(f"")
                        self.output_signal.emit(f"Final result: {len(filtered_objects)} objects in image field")
                        
                        # Store the results in the parent viewer
                        self.parent_viewer.solar_system_objects = filtered_objects
                        
                        # Get pixel coordinates for the objects
                        self.parent_viewer.object_pixel_coords = self.parent_viewer.astrometry_catalog.get_object_pixel_coordinates(
                            self.parent_viewer.wcs, 
                            filtered_objects
                        )
                        
                        # Signal to show the objects dialog on the main thread
                        self.show_objects_dialog.emit(filtered_objects)
                        
                        self.progress_dialog.search_finished(True)
                        
                    except Exception as e:
                        self.output_signal.emit(f"Error searching for solar system objects: {e}")
                        self.progress_dialog.search_finished(False)
            
            # Create and start the search thread
            self.sso_search_thread = SSOSearchThread(self, progress_dialog)
            
            # Connect signals
            self.sso_search_thread.output_signal.connect(progress_dialog.add_output)
            self.sso_search_thread.show_objects_dialog.connect(self._show_objects_dialog)
            self.sso_search_thread.finished.connect(lambda success: self._on_sso_search_finished(success, progress_dialog))
            
            self.sso_search_thread.start()
            
        except Exception as e:
            print(f"Error during SSO search: {e}")
            print("SSO search failed!")
    
    def _on_sso_search_finished(self, success, progress_dialog):
        """Called when SSO search thread finishes"""
        # Reset SSO button to not searching state
        set_sso_button_searching(self, False)
    
    def _show_objects_dialog(self, filtered_objects):
        """Show the objects dialog on the main thread"""
        # Enable the toggle markers if objects were found
        if filtered_objects:
            self.show_objects = True
            self.update_image_display()  # Redraw with markers
            
            # Show the objects dialog (non-modal)
            self.objects_dialog = SolarSystemObjectsDialog(filtered_objects, self)
            self.objects_dialog.show()
        else:
            self.show_objects = False
            # Show a message that no objects were found (non-modal)
            self.objects_dialog = SolarSystemObjectsDialog([], self)
            self.objects_dialog.show()

    def _get_observation_time(self):
        """Extract observation time from FITS header"""
        if self.current_header is None:
            return None
        
        header = self.current_header
        
        # Try different date/time keywords
        date_keywords = ['DATE-OBS', 'DATE', 'MJD-OBS', 'MJD']
        time_keywords = ['TIME-OBS', 'TIME', 'UT', 'UTC']
        
        date_str = None
        time_str = None
        
        # Get date
        for key in date_keywords:
            if key in header:
                date_str = str(header[key]).strip()
                break
        
        # Get time
        for key in time_keywords:
            if key in header:
                time_str = str(header[key]).strip()
                break
        
        try:
            if date_str and time_str:
                # Combine date and time
                datetime_str = f"{date_str}T{time_str}"
                return Time(datetime_str)
            elif date_str:
                # Just date
                return Time(date_str)
            else:
                # Fallback to current time
                print("No observation time found in header, using current time")
                return Time.now()
        except Exception as e:
            print(f"Error parsing observation time: {e}")
            # Fallback to current time
            return Time.now()

    def solve_current_image(self):
        """Solve the current image using astrometry.net with progress dialog"""
        if self.image_data is None:
            print("No image data loaded to solve")
            return
        
        # Get the current file path from the window title or use a default
        current_file = None
        if hasattr(self, 'current_file_path') and self.current_file_path:
            current_file = self.current_file_path
        else:
            print("No file path available for solving")
            return
        
        try:
            # Extract coordinates from header using helper function
            try:
                header = fits.getheader(current_file)
                
                ra_center, dec_center, has_wcs, source = extract_coordinates_from_header(header)
                
                if has_wcs:
                    print(f"Found coordinates in file, using as target.")
                    print(f"  Source: {source}")
                    print(f"  RA: {ra_center} degrees")
                    print(f"  Dec: {dec_center} degrees")
                else:
                    print("No WCS found.")
                
                # Calculate field radius if we have WCS
                radius = None
                if has_wcs and self.wcs is not None:
                    radius = calculate_field_radius(self.wcs, ra_center, dec_center)
                    
            except Exception as e:
                print(f"Error reading WCS from file: {e}")
                has_wcs = False
                ra_center = dec_center = radius = None
            
            # Create solver options using helper function
            options = create_solver_options(
                files=[current_file],
                ra=ra_center,
                dec=dec_center,
                radius=radius,
                blind=not has_wcs
            )
            
            # Create and show progress dialog
            progress_dialog = SolvingProgressDialog(self)
            
            # Set solve button to solving state
            set_solve_button_solving(self, True)
            
            # Use guided solving if WCS is available, otherwise use blind solving
            if has_wcs and ra_center is not None and dec_center is not None and radius is not None:
                progress_dialog.add_output(f"Using guided solving with existing WCS information")
                progress_dialog.add_output(f"Target RA / DEC: {ra_center:.6f}° / {dec_center:.6f}°")
                progress_dialog.add_output(f"Search radius: {radius:.3f}°")
            else:
                progress_dialog.add_output("Using blind solving (no WCS information available)")
            
            # Show the dialog
            progress_dialog.show()
            
            # Run the solving process in a separate thread to avoid blocking the GUI
            from PyQt6.QtCore import QThread, pyqtSignal
            
            class SolvingThread(QThread):
                finished = pyqtSignal(bool)
                output_signal = pyqtSignal(str)
                
                def __init__(self, options, progress_dialog, parent_viewer):
                    super().__init__()
                    self.options = options
                    self.progress_dialog = progress_dialog
                    self.parent_viewer = parent_viewer
                
                def run(self):
                    try:
                        # Create a custom solving function that uses signals
                        self._solve_with_signals()
                        self.finished.emit(True)
                    except Exception as e:
                        self.output_signal.emit(f"Error in solving thread: {e}")
                        self.progress_dialog.solving_finished(False)
                        self.finished.emit(False)
                
                def _solve_with_signals(self):
                    """Solve with signal-based output instead of direct dialog calls"""
                    import subprocess
                    import sys
                    import os
                    from pathlib import Path
                    from .solver import set_solver_interrupted, is_solver_interrupted
                    
                    def run_solve_field_with_output(options):
                        """Run solve-field with real-time output capture"""
                        try:
                            # Reset interruption flag
                            set_solver_interrupted(False)
                            
                            # Build solve-field command
                            cmd = ["solve-field"]
                            cmd.extend(["--dir", "solved"])
                            cmd.extend(["--no-plots", "--no-verify", "--overwrite"])
                            
                            if options.downsample:
                                cmd.extend(["--downsample", str(options.downsample)])
                            
                            if not options.blind and options.ra and options.dec and options.radius:
                                cmd.extend(["--guess-scale"])
                                cmd.extend(["--ra", str(options.ra)])
                                cmd.extend(["--dec", str(options.dec)])
                                cmd.extend(["--radius", str(options.radius)])
                            
                            # Add WCS output filename
                            if options.files:
                                base_name = Path(options.files[0]).stem
                                wcs_filename = f"solved/{base_name}.wcs"
                                cmd.extend(["--wcs", wcs_filename])
                            
                            # Add input file
                            if options.files:
                                cmd.append(options.files[0])
                            
                            self.output_signal.emit(f"Running command: {' '.join(cmd)}")
                            
                            # Run the process with real-time output capture
                            process = subprocess.Popen(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                universal_newlines=True,
                                bufsize=1
                            )
                            
                            # Read output in real-time
                            while True:
                                # Check if solving was cancelled
                                if is_solver_interrupted() or self.progress_dialog.solving_cancelled:
                                    process.terminate()
                                    self.output_signal.emit("Process terminated by user.")
                                    return False
                                
                                # Read a line of output
                                output = process.stdout.readline()
                                if output == '' and process.poll() is not None:
                                    break
                                if output:
                                    self.output_signal.emit(output.strip())
                            
                            # Wait for process to complete
                            return_code = process.wait()
                            
                            if return_code == 0:
                                self.output_signal.emit("solve-field completed successfully!")
                                return True
                            else:
                                self.output_signal.emit(f"solve-field failed with return code: {return_code}")
                                return False
                                
                        except Exception as e:
                            self.output_signal.emit(f"Error running solve-field: {e}")
                            return False
                    
                    try:
                        # Create solved directory if it doesn't exist
                        solved_dir = "solved"
                        if not os.path.exists(solved_dir):
                            os.makedirs(solved_dir)
                            self.output_signal.emit(f"Created directory: {solved_dir}")
                        
                        # Start solving process
                        self.output_signal.emit("Starting plate solving process...")
                        self.output_signal.emit(f"File: {self.options.files[0] if self.options.files else 'Unknown'}")
                        
                        if self.options.blind:
                            self.output_signal.emit("Mode: Blind solving")
                        else:
                            self.output_signal.emit(f"Mode: Guided solving")
                            self.output_signal.emit(f"Target: RA={self.options.ra:.6f}°, Dec={self.options.dec:.6f}°")
                            self.output_signal.emit(f"Radius: {self.options.radius}°")
                        
                        self.output_signal.emit(f"Downsample: {self.options.downsample}")
                        self.output_signal.emit("")
                        
                        # Run the solving process
                        success = run_solve_field_with_output(self.options)
                        
                        if success:
                            # Apply WCS to original file
                            if self.options.files:
                                base_name = Path(self.options.files[0]).stem
                                wcs_filename = f"solved/{base_name}.wcs"
                                
                                if os.path.exists(wcs_filename):
                                    self.output_signal.emit("Applying WCS solution to original file...")
                                    
                                    # Import the apply_wcs_to_file function
                                    from .solver import apply_wcs_to_file
                                    apply_wcs_to_file(self.options.files[0], wcs_filename)
                                    
                                    # Clean up WCS file
                                    os.remove(wcs_filename)
                                    self.output_signal.emit("WCS solution applied successfully!")
                                    
                                    # Clean up other temporary files
                                    from .solver import solver_cleanup
                                    solver_cleanup()
                                    
                                    # Validate the solution
                                    try:
                                        from astropy.io import fits
                                        from .helpers import validate_wcs_solution
                                        
                                        with fits.open(self.options.files[0]) as hdu:
                                            header = hdu[0].header
                                            is_valid, error_message = validate_wcs_solution(header)
                                            
                                            if is_valid:
                                                self.output_signal.emit("WCS solution validated successfully!")
                                                self.progress_dialog.solving_finished(True)
                                                
                                                # Signal to reload the file in the main viewer
                                                self.finished.emit(True)
                                            else:
                                                self.output_signal.emit(f"WCS validation failed: {error_message}")
                                                self.progress_dialog.solving_finished(False)
                                                self.finished.emit(False)
                                    except Exception as e:
                                        self.output_signal.emit(f"Error validating WCS: {e}")
                                        self.progress_dialog.solving_finished(False)
                                        self.finished.emit(False)
                                else:
                                    self.output_signal.emit("No WCS file generated!")
                                    self.progress_dialog.solving_finished(False)
                                    self.finished.emit(False)
                            else:
                                self.output_signal.emit("No input file specified!")
                                self.progress_dialog.solving_finished(False)
                                self.finished.emit(False)
                        else:
                            self.output_signal.emit("Solving process failed!")
                            self.progress_dialog.solving_finished(False)
                            self.finished.emit(False)
                            
                    except Exception as e:
                        self.output_signal.emit(f"Unexpected error during solving: {e}")
                        self.progress_dialog.solving_finished(False)
                        self.finished.emit(False)
            
            # Create and start the solving thread
            self.solving_thread = SolvingThread(options, progress_dialog, self)
            
            # Connect signals
            self.solving_thread.output_signal.connect(progress_dialog.add_output)
            self.solving_thread.finished.connect(lambda success: self._on_solving_finished(success, progress_dialog))
            
            self.solving_thread.start()
            
        except Exception as e:
            print(f"Error during solving: {e}")
            print("Solving failed!")
    
    def _on_solving_finished(self, success, progress_dialog):
        """Called when solving thread finishes"""
        # Reset solve button to not solving state
        set_solve_button_solving(self, False)
        
        if success:
            # Reset all state variables to clean state
            self.solar_system_objects = []
            self.object_pixel_coords = []
            self.show_objects = False
            
            # Clear SIMBAD objects
            self.simbad_object = None
            self.simbad_pixel_coords = None
            self.show_simbad_object = False
            
            # Close any open dialogs
            if self.objects_dialog and self.objects_dialog.isVisible():
                self.objects_dialog.close()
                self.objects_dialog = None
            if self.header_dialog and self.header_dialog.isVisible():
                self.header_dialog.close()
                self.header_dialog = None
    
    def closeEvent(self, event):
        """Handle window close event to clean up threads"""
        # Clean up solving thread if it exists and is running
        if hasattr(self, 'solving_thread') and self.solving_thread.isRunning():
            self.solving_thread.terminate()
            self.solving_thread.wait(1000)  # Wait up to 1 second for thread to finish
        
        # Clean up SSO search thread if it exists and is running
        if hasattr(self, 'sso_search_thread') and self.sso_search_thread.isRunning():
            self.sso_search_thread.terminate()
            self.sso_search_thread.wait(1000)  # Wait up to 1 second for thread to finish
            
        super().closeEvent(event)

    def search_simbad_object(self):
        """Search for an object in SIMBAD and display it if found in the field"""
        if self.wcs is None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No WCS", "No WCS information available. Please solve the image first.")
            return
        
        # Create and show the SIMBAD search dialog
        dialog = SIMBADSearchDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result:
            simbad_object, pixel_coords = dialog.result
            
            # Store the SIMBAD object and its pixel coordinates
            self.simbad_object = simbad_object
            self.simbad_pixel_coords = pixel_coords
            self.show_simbad_object = True
            
            # Update the image display to show the SIMBAD object
            self.update_image_display()
            
            print(f"SIMBAD object displayed: {simbad_object.name} at pixel coordinates {pixel_coords}")

    def clear_simbad_object(self):
        """Clear the current SIMBAD object display"""
        self.simbad_object = None
        self.simbad_pixel_coords = None
        self.show_simbad_object = False
        self.update_image_display()


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='FITS Image Viewer with PyQt6')
    parser.add_argument('fits_file', nargs='?', help='FITS file to open')
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    
    # Create and show the main window
    window = FITSImageViewer()
    window.show()
    
    # Load the FITS file if provided as argument
    if args.fits_file:
        window.load_file_from_path(args.fits_file)
    
    # Start the event loop
    sys.exit(app.exec())


if __name__ == '__main__':
    main() 