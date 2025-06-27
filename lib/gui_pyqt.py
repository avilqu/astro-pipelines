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

# Import our refactored modules
from .gui_widgets import ImageLabel, HeaderDialog, SolarSystemObjectsDialog, SIMBADSearchDialog
from .gui_image_processing import (create_image_object, add_object_markers, get_cached_zoom,
                                  calculate_bit_depth, apply_auto_stretch, apply_no_stretch)
from .gui_control_panel import create_control_panel, update_image_info
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
        """Search for solar system objects in the current field"""
        if self.wcs is None or self.image_data is None:
            print("No WCS information available for solar system object search")
            return
        
        try:
            # Get observation time from header
            epoch = self._get_observation_time()
            if epoch is None:
                print("Could not determine observation time from header")
                return
            
            # Get solar system objects in the field
            self.solar_system_objects = self.astrometry_catalog.get_field_objects(
                self.wcs, 
                self.image_data.shape, 
                epoch
            )
            
            # Get pixel coordinates for the objects
            self.object_pixel_coords = self.astrometry_catalog.get_object_pixel_coordinates(
                self.wcs, 
                self.solar_system_objects
            )
            
            print(f"Found {len(self.solar_system_objects)} solar system objects")
            
            # Enable the toggle markers button if objects were found
            if self.solar_system_objects:
                self.show_objects = True
                self.update_image_display()  # Redraw with markers
                
                # Show the objects dialog (non-modal)
                self.objects_dialog = SolarSystemObjectsDialog(self.solar_system_objects, self)
                self.objects_dialog.show()
            else:
                self.show_objects = False
                # Show a message that no objects were found (non-modal)
                self.objects_dialog = SolarSystemObjectsDialog([], self)
                self.objects_dialog.show()
                
        except Exception as e:
            print(f"Error searching for solar system objects: {e}")

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
        """Solve the current image using astrometry.net"""
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
            print(f"Solving image: {current_file}")
            
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
            
            # Use guided solving if WCS is available, otherwise use blind solving
            if has_wcs and ra_center is not None and dec_center is not None and radius is not None:
                print(f"Using guided solving with existing WCS information")
                print(f"Target RA / DEC: {ra_center:.6f}° / {dec_center:.6f}°")
                print(f"Search radius: {radius:.3f}°")
            else:
                print("Using blind solving (no WCS information available)")
            
            # Call the offline solver
            solve_offline(options)
            
            # Check if solving was successful using helper function
            try:
                with fits.open(current_file) as hdu:
                    header = hdu[0].header
                    is_valid, error_message = validate_wcs_solution(header)
                    
                    if is_valid:
                        print("Image solved successfully!")
                        
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
                        
                        # Reload the file to get the updated WCS information
                        self.load_file_from_path(current_file)
                    else:
                        print(f"Solving failed: {error_message}")
                        
            except Exception as e:
                print(f"Error checking solving result: {e}")
            
        except Exception as e:
            print(f"Error during solving: {e}")
            print("Solving failed!")

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