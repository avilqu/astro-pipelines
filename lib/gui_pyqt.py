import sys
import argparse
import numpy as np
import matplotlib.pyplot as plt
from astropy.io import fits
from astropy.wcs import WCS
from astropy.time import Time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, 
                             QVBoxLayout, QHBoxLayout, QFileDialog, QScrollArea,
                             QLabel, QFrame, QSizePolicy, QTextEdit, QDialog, QStatusBar,
                             QLineEdit, QMessageBox)
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer
from PyQt6.QtGui import QPixmap, QImage, QPainter, QWheelEvent, QMouseEvent, QKeyEvent, QFont, QPen, QColor
from .astrometry import AstrometryCatalog, SolarSystemObject, SIMBADObject
from .solver import solve_offline
from .helpers import extract_coordinates_from_header, calculate_field_radius, validate_wcs_solution, create_solver_options
import config


class ImageLabel(QLabel):
    """Custom QLabel that handles mouse events for panning and zooming"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_viewer = parent
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Add timer for coordinate updates to reduce CPU usage
        self.coord_timer = QTimer()
        self.coord_timer.setSingleShot(True)
        self.coord_timer.timeout.connect(self._update_coordinates)
        self.last_mouse_pos = QPoint()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events for panning"""
        if event.button() == Qt.MouseButton.LeftButton and self.parent_viewer:
            self.parent_viewer.panning = True
            self.parent_viewer.last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move events for panning and coordinate display"""
        if self.parent_viewer and self.parent_viewer.pixmap is not None:
            # Handle panning
            if self.parent_viewer.panning:
                delta = event.pos() - self.parent_viewer.last_mouse_pos
                scroll_area = self.parent_viewer.scroll_area
                h_scroll = scroll_area.horizontalScrollBar()
                v_scroll = scroll_area.verticalScrollBar()
                
                h_scroll.setValue(h_scroll.value() - delta.x())
                v_scroll.setValue(v_scroll.value() - delta.y())
                
                self.parent_viewer.last_mouse_pos = event.pos()
            
            # Throttle coordinate updates to reduce CPU usage
            self.last_mouse_pos = event.pos()
            if not self.coord_timer.isActive():
                self.coord_timer.start(50)  # Update every 50ms max
        
        super().mouseMoveEvent(event)
    
    def _update_coordinates(self):
        """Update coordinate display (called by timer to reduce CPU usage)"""
        if not self.parent_viewer or not self.parent_viewer.wcs:
            return
            
        mouse_pos = self.last_mouse_pos
        scaled_pixmap = self.pixmap()
        if not scaled_pixmap:
            return
            
        pixmap_size = scaled_pixmap.size()
        label_size = self.size()
        
        # Calculate position within the pixmap
        x_offset = (label_size.width() - pixmap_size.width()) // 2
        y_offset = (label_size.height() - pixmap_size.height()) // 2
        
        pixmap_x = mouse_pos.x() - x_offset
        pixmap_y = mouse_pos.y() - y_offset
        
        # Check if mouse is within the pixmap bounds
        if (0 <= pixmap_x < pixmap_size.width() and 
            0 <= pixmap_y < pixmap_size.height()):
            
            # Convert to original image coordinates
            orig_x = pixmap_x / self.parent_viewer.scale_factor
            orig_y = pixmap_y / self.parent_viewer.scale_factor
            
            # Get pixel value
            try:
                if (0 <= orig_x < self.parent_viewer.image_data.shape[1] and 
                    0 <= orig_y < self.parent_viewer.image_data.shape[0]):
                    pixel_value = self.parent_viewer.image_data[int(orig_y), int(orig_x)]
                    if self.parent_viewer.bit_depth:
                        self.parent_viewer.pixel_value_label.setText(f"{pixel_value} / {self.parent_viewer.bit_depth}")
                    else:
                        self.parent_viewer.pixel_value_label.setText(f"{pixel_value}")
                else:
                    self.parent_viewer.pixel_value_label.setText("--")
            except Exception:
                self.parent_viewer.pixel_value_label.setText("--")
            
            # Convert to sky coordinates
            try:
                sky_coords = self.parent_viewer.wcs.pixel_to_world(orig_x, orig_y)
                if hasattr(sky_coords, 'ra') and hasattr(sky_coords, 'dec'):
                    ra = sky_coords.ra.to_string(unit='hourangle', precision=2)
                    dec = sky_coords.dec.to_string(unit='deg', precision=2)
                else:
                    ra = sky_coords[0].to_string(unit='hourangle', precision=2)
                    dec = sky_coords[1].to_string(unit='deg', precision=2)
                coord_text = f"RA: {ra}  Dec: {dec}  Pixel: ({orig_x:.1f}, {orig_y:.1f})"
                self.parent_viewer.coord_label.setText(coord_text)
            except Exception as e:
                self.parent_viewer.coord_label.setText(f"WCS error: {str(e)}")
        else:
            self.parent_viewer.coord_label.setText("WCS ready - move mouse over image for coordinates")
            self.parent_viewer.pixel_value_label.setText("--")
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release events"""
        if event.button() == Qt.MouseButton.LeftButton and self.parent_viewer:
            self.parent_viewer.panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)
    
    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel events for zooming"""
        if self.parent_viewer and self.parent_viewer.base_pixmap is not None:
            event.accept()
            
            # Get the current scroll positions
            scroll_area = self.parent_viewer.scroll_area
            h_scroll = scroll_area.horizontalScrollBar()
            v_scroll = scroll_area.verticalScrollBar()
            
            # Get the mouse position relative to the viewport
            mouse_x = event.position().x()
            mouse_y = event.position().y()
            
            # Calculate the center point of the zoom (where the mouse is)
            zoom_center_x = mouse_x + h_scroll.value()
            zoom_center_y = mouse_y + v_scroll.value()
            
            # Store the old scale factor
            old_scale = self.parent_viewer.scale_factor
            
            # Apply zoom
            if event.angleDelta().y() > 0:
                self.parent_viewer.scale_factor *= 1.1
            else:
                self.parent_viewer.scale_factor /= 1.1
                if self.parent_viewer.scale_factor < 0.1:
                    self.parent_viewer.scale_factor = 0.1
            
            # Update the image display
            self.parent_viewer.update_image_display()
            
            # Calculate the new scroll positions to keep the zoom center point fixed
            scale_ratio = self.parent_viewer.scale_factor / old_scale
            new_zoom_center_x = zoom_center_x * scale_ratio
            new_zoom_center_y = zoom_center_y * scale_ratio
            
            # Set the new scroll positions
            new_h_scroll = int(new_zoom_center_x - mouse_x)
            new_v_scroll = int(new_zoom_center_y - mouse_y)
            
            h_scroll.setValue(new_h_scroll)
            v_scroll.setValue(new_v_scroll)
        else:
            super().wheelEvent(event)
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events"""
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


class HeaderDialog(QDialog):
    """Dialog window to display FITS header information"""
    
    def __init__(self, header, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FITS Header")
        self.setGeometry(200, 200, 600, 500)
        
        layout = QVBoxLayout(self)
        
        # Create text area for header display
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFont(QFont("Courier", 10))
        layout.addWidget(self.text_area)
        
        # Display the header
        self.display_header(header)
    
    def display_header(self, header):
        """Display the FITS header in the text area with colored formatting in table format"""
        header_html = """
        <table style="font-family: 'Courier New', monospace; font-size: 10pt; border-collapse: collapse; width: 100%;">
        <tr style="background-color: #333333;">
            <th style="color: #666666; text-align: left; padding: 2px 5px; border-bottom: 1px solid #555555;">#</th>
            <th style="color: #0066CC; text-align: left; padding: 2px 5px; border-bottom: 1px solid #555555;">Keyword</th>
            <th style="color: #FFFFFF; text-align: left; padding: 2px 5px; border-bottom: 1px solid #555555;">Value</th>
            <th style="color: #888888; text-align: left; padding: 2px 5px; border-bottom: 1px solid #555555;">Comment</th>
        </tr>
        """
        
        for i, card in enumerate(header.cards):
            # Parse the FITS card
            keyword = card.keyword
            value = card.value
            comment = card.comment
            
            # Format the value
            if value is not None:
                if isinstance(value, str):
                    value_str = f'"{value}"'
                else:
                    value_str = str(value)
            else:
                value_str = ""
            
            # Format the comment
            comment_str = comment if comment else ""
            
            # Create table row
            row_color = "#222222" if i % 2 == 0 else "#2A2A2A"  # Alternating row colors
            header_html += f"""
            <tr style="background-color: {row_color};">
                <td style="color: #666666; padding: 2px 5px; border-right: 1px solid #555555;">{i+1:3d}</td>
                <td style="color: #0066CC; font-weight: bold; padding: 2px 5px; border-right: 1px solid #555555;">{keyword}</td>
                <td style="color: #FFFFFF; padding: 2px 5px; border-right: 1px solid #555555;">{value_str}</td>
                <td style="color: #888888; padding: 2px 5px;">{comment_str}</td>
            </tr>
            """
        
        header_html += "</table>"
        self.text_area.setHtml(header_html)


class SolarSystemObjectsDialog(QDialog):
    """Dialog window to display solar system objects found in the field"""
    
    def __init__(self, objects, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Solar System Objects")
        self.setGeometry(200, 200, 700, 500)
        
        layout = QVBoxLayout(self)
        
        # Create text area for objects display
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFont(QFont("Courier", 10))
        layout.addWidget(self.text_area)
        
        # Display the objects
        self.display_objects(objects)
    
    def display_objects(self, objects):
        """Display the solar system objects in a formatted table"""
        if not objects:
            self.text_area.setHtml("""
            <div style="color: #FFFFFF; font-family: 'Courier New', monospace; font-size: 12pt; text-align: center; padding: 20px;">
                No solar system objects found in this field.
            </div>
            """)
            return
        
        objects_html = """
        <table style="font-family: 'Courier New', monospace; font-size: 10pt; border-collapse: collapse; width: 100%;">
        <tr style="background-color: #333333;">
            <th style="color: #666666; text-align: left; padding: 2px 5px; border-bottom: 1px solid #555555;">#</th>
            <th style="color: #00CC00; text-align: left; padding: 2px 5px; border-bottom: 1px solid #555555;">Name</th>
            <th style="color: #0066CC; text-align: left; padding: 2px 5px; border-bottom: 1px solid #555555;">Type</th>
            <th style="color: #FFFFFF; text-align: left; padding: 2px 5px; border-bottom: 1px solid #555555;">RA (deg)</th>
            <th style="color: #FFFFFF; text-align: left; padding: 2px 5px; border-bottom: 1px solid #555555;">Dec (deg)</th>
            <th style="color: #FFFF00; text-align: left; padding: 2px 5px; border-bottom: 1px solid #555555;">Mag</th>
            <th style="color: #FF8800; text-align: left; padding: 2px 5px; border-bottom: 1px solid #555555;">Distance (AU)</th>
            <th style="color: #FF0088; text-align: left; padding: 2px 5px; border-bottom: 1px solid #555555;">Velocity (″/h)</th>
        </tr>
        """
        
        for i, obj in enumerate(objects):
            # Format the values
            ra_str = f"{obj.ra:.4f}" if obj.ra is not None else "--"
            dec_str = f"{obj.dec:.4f}" if obj.dec is not None else "--"
            mag_str = f"{obj.magnitude:.2f}" if obj.magnitude is not None and obj.magnitude < 99 else "--"
            dist_str = f"{obj.distance:.2f}" if obj.distance is not None else "--"
            vel_str = f"{obj.velocity:.2f}" if obj.velocity is not None else "--"
            
            # Create table row
            row_color = "#222222" if i % 2 == 0 else "#2A2A2A"  # Alternating row colors
            objects_html += f"""
            <tr style="background-color: {row_color};">
                <td style="color: #666666; padding: 2px 5px; border-right: 1px solid #555555;">{i+1:2d}</td>
                <td style="color: #00CC00; font-weight: bold; padding: 2px 5px; border-right: 1px solid #555555;">{obj.name}</td>
                <td style="color: #0066CC; padding: 2px 5px; border-right: 1px solid #555555;">{obj.object_type}</td>
                <td style="color: #FFFFFF; padding: 2px 5px; border-right: 1px solid #555555;">{ra_str}</td>
                <td style="color: #FFFFFF; padding: 2px 5px; border-right: 1px solid #555555;">{dec_str}</td>
                <td style="color: #FFFF00; padding: 2px 5px; border-right: 1px solid #555555;">{mag_str}</td>
                <td style="color: #FF8800; padding: 2px 5px; border-right: 1px solid #555555;">{dist_str}</td>
                <td style="color: #FF0088; padding: 2px 5px;">{vel_str}</td>
            </tr>
            """
        
        objects_html += "</table>"
        self.text_area.setHtml(objects_html)


class SIMBADSearchDialog(QDialog):
    """Dialog window for SIMBAD object search"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SIMBAD Object Search")
        self.setGeometry(300, 300, 400, 150)
        self.setModal(True)
        
        self.parent_viewer = parent
        self.result = None
        
        layout = QVBoxLayout(self)
        
        # Instructions
        instruction_label = QLabel("Enter the name of an astronomical object to search in SIMBAD:")
        instruction_label.setWordWrap(True)
        layout.addWidget(instruction_label)
        
        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("e.g., M31, NGC 224, Vega, Sirius")
        self.search_input.returnPressed.connect(self.search_object)
        layout.addWidget(self.search_input)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_object)
        button_layout.addWidget(self.search_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        # Set focus to search input
        self.search_input.setFocus()
    
    def search_object(self):
        """Search for the object in SIMBAD"""
        object_name = self.search_input.text().strip()
        
        if not object_name:
            QMessageBox.warning(self, "Search Error", "Please enter an object name.")
            return
        
        # Disable search button during search
        self.search_button.setEnabled(False)
        self.search_button.setText("Searching...")
        
        try:
            # Search SIMBAD
            simbad_object = self.parent_viewer.astrometry_catalog.simbad_search(object_name)
            
            if simbad_object is None:
                QMessageBox.information(self, "Not Found", f"The object '{object_name}' was not found in SIMBAD.")
                return
            
            # Check if object is in the field
            if self.parent_viewer.wcs is None:
                QMessageBox.warning(self, "No WCS", "No WCS information available. Please solve the image first.")
                return
            
            is_in_field, pixel_coords = self.parent_viewer.astrometry_catalog.check_object_in_field(
                self.parent_viewer.wcs, 
                self.parent_viewer.image_data.shape, 
                simbad_object
            )
            
            if is_in_field:
                # Object found and in field
                self.result = (simbad_object, pixel_coords)
                QMessageBox.information(self, "Object Found", 
                    f"Found '{simbad_object.name}' in the field!\n"
                    f"Type: {simbad_object.object_type}\n"
                    f"RA: {simbad_object.ra:.4f}°, Dec: {simbad_object.dec:.4f}°")
                self.accept()
            else:
                # Object found but out of field
                QMessageBox.information(self, "Object Out of Field", 
                    f"The object '{simbad_object.name}' was found in SIMBAD but is out of frame.\n"
                    f"Coordinates: RA {simbad_object.ra:.4f}°, Dec {simbad_object.dec:.4f}°")
                
        except Exception as e:
            QMessageBox.critical(self, "Search Error", f"Error searching SIMBAD: {str(e)}")
        finally:
            # Re-enable search button
            self.search_button.setEnabled(True)
            self.search_button.setText("Search")


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
        self.last_mouse_pos = QPoint()
        self.panning = False
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
        control_panel = self.create_control_panel()
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

    def create_control_panel(self):
        """Create the control panel with buttons"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.Box)
        panel.setMaximumWidth(200)
        
        layout = QVBoxLayout(panel)
        
        # Open file button
        self.open_button = QPushButton("Open FITS File")
        self.open_button.clicked.connect(self.open_file)
        layout.addWidget(self.open_button)
        
        # Auto Stretch button
        self.stretch_button = QPushButton("Auto Stretch")
        self.stretch_button.setToolTip("Toggle between no stretch and auto stretch")
        self.stretch_button.setCheckable(True)  # Make it a toggleable button
        self.stretch_button.clicked.connect(self.toggle_stretch)
        layout.addWidget(self.stretch_button)
        
        # FITS Header button
        self.header_button = QPushButton("FITS Header")
        self.header_button.setToolTip("View full FITS header")
        self.header_button.clicked.connect(self.show_header)
        self.header_button.setEnabled(False)  # Disabled until a file is loaded
        layout.addWidget(self.header_button)
        
        # Solar System Objects button
        self.objects_button = QPushButton("Show SSO")
        self.objects_button.setToolTip("Search for and display solar system objects in the field")
        self.objects_button.clicked.connect(self.toggle_solar_system_objects)
        self.objects_button.setEnabled(False)  # Disabled until a file is loaded
        layout.addWidget(self.objects_button)
        
        # SIMBAD Search button
        self.simbad_button = QPushButton("Find Object")
        self.simbad_button.setToolTip("Search for an object in the SIMBAD database")
        self.simbad_button.clicked.connect(self.search_simbad_object)
        self.simbad_button.setEnabled(False)  # Disabled until a file is loaded
        layout.addWidget(self.simbad_button)
        
        # Solve button
        self.solve_button = QPushButton("Solve")
        self.solve_button.setToolTip("Plate solve the current image using astrometry.net")
        self.solve_button.clicked.connect(self.solve_current_image)
        self.solve_button.setEnabled(False)  # Disabled until a file is loaded
        layout.addWidget(self.solve_button)
        
        # Reset zoom button
        reset_zoom_button = QPushButton("Reset Zoom")
        reset_zoom_button.clicked.connect(self.reset_zoom)
        layout.addWidget(reset_zoom_button)
        
        # Add stretch to push everything to the top
        layout.addStretch()
        
        # Image information section
        info_label = QLabel("Image Information: ")
        info_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(info_label)
        
        # Create info display labels
        self.target_label = QLabel("Target: --")
        self.filter_label = QLabel("Filter: --")
        self.exposure_label = QLabel("Exposure: --")
        self.gain_label = QLabel("Gain: --")
        self.offset_label = QLabel("Offset: --")
        self.wcs_label = QLabel("WCS: --")
        
        # Add info labels to layout
        layout.addWidget(self.target_label)
        layout.addWidget(self.filter_label)
        layout.addWidget(self.exposure_label)
        layout.addWidget(self.gain_label)
        layout.addWidget(self.offset_label)
        layout.addWidget(self.wcs_label)
        
        return panel

    def toggle_stretch(self):
        """Toggle between no stretch and auto stretch"""
        if self.stretch_button.isChecked():
            self.apply_auto_stretch()
        else:
            self.apply_no_stretch()

    def apply_no_stretch(self):
        """Apply no histogram stretching - use actual data min/max"""
        if self.image_data is not None:
            # Use actual data min/max for true "no stretch"
            self.display_min = self.image_data.min()
            self.display_max = self.image_data.max()
            self.update_image_display()

    def apply_auto_stretch(self):
        """Apply auto histogram stretching using bright stretch code"""
        if self.image_data is not None:
            # Use 5th and 95th percentiles (the bright stretch code that works)
            self.display_min = np.percentile(self.image_data, 1)
            self.display_max = np.percentile(self.image_data, 99)
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

    def update_image_info(self, hdu_list):
        """Update the image information display with FITS header data"""
        header = hdu_list[0].header
        
        # Target name - try common header keywords
        target = "--"
        for key in ['OBJECT', 'TARGET', 'TELESCOP', 'OBSERVER']:
            if key in header:
                target = str(header[key]).strip()
                break
        self.target_label.setText(f"Target: {target}")
        
        # Filter information - try common header keywords
        filter_info = "--"
        for key in ['FILTER', 'FILT', 'FILTER1', 'FILTER2', 'FILT1', 'FILT2', 'BANDPASS']:
            if key in header:
                filter_info = str(header[key]).strip()
                break
        self.filter_label.setText(f"Filter: {filter_info}")
        
        # Exposure time
        exposure = "--"
        for key in ['EXPTIME', 'EXPOSURE', 'EXPOSURE_TIME']:
            if key in header:
                exposure = f"{header[key]:.1f}s"
                break
        self.exposure_label.setText(f"Exposure: {exposure}")
        
        # Gain
        gain = "--"
        for key in ['GAIN', 'EGAIN', 'CCDGAIN']:
            if key in header:
                gain = f"{header[key]:.1f}"
                break
        self.gain_label.setText(f"Gain: {gain}")
        
        # Offset
        offset = "--"
        for key in ['OFFSET', 'CCDOFFSET', 'BIAS']:
            if key in header:
                offset = f"{header[key]:.1f}"
                break
        self.offset_label.setText(f"Offset: {offset}")
        
        # WCS status
        wcs_status = "No WCS"
        wcs_color = "red"
        self.wcs = None  # Reset WCS
        
        if 'CTYPE1' in header and 'CTYPE2' in header:
            ctype1 = header['CTYPE1']
            ctype2 = header['CTYPE2']
            # Extract projection type from CTYPE (e.g., "RA---TAN" -> "TAN")
            if '-' in ctype1:
                projection = ctype1.split('-')[-1]  # Get the last part after the last dash
                wcs_status = f"WCS: {projection}"
            else:
                wcs_status = f"WCS: {ctype1}/{ctype2}"
            wcs_color = "white"
            
            # Try to create WCS object
            try:
                self.wcs = WCS(header)
                self.coord_label.setText("WCS ready - move mouse over image for coordinates")
            except Exception as e:
                self.coord_label.setText("WCS present but invalid")
                
        elif 'CD1_1' in header or 'CDELT1' in header:
            wcs_status = "WCS: Present"
            wcs_color = "white"
            try:
                self.wcs = WCS(header)
                self.coord_label.setText("WCS ready - move mouse over image for coordinates")
            except Exception as e:
                self.coord_label.setText("WCS present but invalid")
        else:
            self.coord_label.setText("No WCS - coordinates unavailable")
        
        self.wcs_label.setText(wcs_status)
        self.wcs_label.setStyleSheet(f"color: {wcs_color};")
        
        # Enable objects button if WCS is available
        if self.wcs is not None:
            self.objects_button.setEnabled(True)
            self.simbad_button.setEnabled(True)
        else:
            self.objects_button.setEnabled(False)
            self.simbad_button.setEnabled(False)
        
        # Enable solve button when a file is loaded
        self.solve_button.setEnabled(True)

    def load_file_from_path(self, filepath):
        """Load a FITS file from a given filepath"""
        try:
            hdu_list = fits.open(filepath)
            image_data = hdu_list[0].data
            self.load_image(image_data, filepath)
            self.update_image_info(hdu_list)
            self.current_header = hdu_list[0].header
            self.current_file_path = filepath  # Store the file path
            self.header_button.setEnabled(True)  # Enable header button
            
            hdu_list.close()
        except Exception as e:
            print(f"Error opening file: {e}")
            self.header_button.setEnabled(False)  # Disable header button on error
            self.objects_button.setEnabled(False)  # Disable objects button on error
            self.solve_button.setEnabled(False)  # Disable solve button on error

    def create_image_object(self, image_data: np.ndarray, display_min=None, display_max=None):
        """Convert numpy array to QPixmap for display - optimized version"""
        # Use provided display range or calculate from histogram
        if display_min is None or display_max is None:
            histo = np.histogram(image_data, 60, None, True)
            self.display_min = histo[1][0]
            self.display_max = histo[1][-1]
        else:
            self.display_min = display_min
            self.display_max = display_max
        
        # Apply histogram stretching
        if self.display_max > self.display_min:
            clipped_data = np.clip(image_data, self.display_min, self.display_max)
            normalized_data = (clipped_data - self.display_min) / (self.display_max - self.display_min)
        else:
            normalized_data = image_data - image_data.min()
            if normalized_data.max() > 0:
                normalized_data = normalized_data / normalized_data.max()
        
        # Convert to 8-bit for display
        display_data = (normalized_data * 255).astype(np.uint8)
        
        # Create QImage from numpy array
        height, width = display_data.shape
        display_data = np.ascontiguousarray(display_data)
        q_image = QImage(display_data.data, width, height, width, QImage.Format.Format_Grayscale8)
        q_image = q_image.copy()
        
        # Convert to pixmap
        return QPixmap.fromImage(q_image)

    def _add_object_markers(self, pixmap):
        """Add circles for solar system objects and SIMBAD objects to the pixmap - optimized version"""
        # Add solar system objects (green circles)
        if self.object_pixel_coords:
            # Create a painter to draw on the pixmap
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Calculate font size based on zoom level (larger font for higher zoom)
            base_font_size = 16
            scaled_font_size = max(8, base_font_size * self.scale_factor)
            font = QFont("Arial", int(scaled_font_size))
            painter.setFont(font)
            
            # Scale circle size and line width with zoom level (larger circles for higher zoom)
            base_circle_radius = 12
            scaled_circle_radius = max(6, base_circle_radius * self.scale_factor)
            scaled_pen_width = max(1, 2 * self.scale_factor)
            
            # Draw circles for each solar system object
            for obj, x_pixel, y_pixel in self.object_pixel_coords:
                if (0 <= x_pixel < pixmap.width() and 0 <= y_pixel < pixmap.height()):
                    # Draw circle in green
                    circle_pen = QPen(QColor(0, 255, 0))
                    circle_pen.setWidth(int(scaled_pen_width))
                    painter.setPen(circle_pen)
                    painter.drawEllipse(int(x_pixel - scaled_circle_radius), int(y_pixel - scaled_circle_radius), 
                                       int(scaled_circle_radius * 2), int(scaled_circle_radius * 2))
                    
                    # Add object name
                    if len(self.object_pixel_coords) <= 10:
                        text_x = int(x_pixel + scaled_circle_radius + 8)
                        text_y = int(y_pixel + 8)
                        
                        # Draw outline
                        outline_pen = QPen(QColor(0, 0, 0))
                        outline_pen.setWidth(int(max(2, 5 * self.scale_factor)))
                        painter.setPen(outline_pen)
                        painter.drawText(text_x, text_y, obj.name)
                        
                        # Draw text in green
                        text_pen = QPen(QColor(0, 255, 0))
                        painter.setPen(text_pen)
                        painter.drawText(text_x, text_y, obj.name)
            
            painter.end()
        
        # Add SIMBAD object (red circle)
        if self.show_simbad_object and self.simbad_object and self.simbad_pixel_coords:
            # Create a painter to draw on the pixmap
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Calculate font size based on zoom level (larger font for higher zoom)
            base_font_size = 16
            scaled_font_size = max(8, base_font_size * self.scale_factor)
            font = QFont("Arial", int(scaled_font_size))
            painter.setFont(font)
            
            # Scale circle size and line width with zoom level (larger circles for higher zoom)
            base_circle_radius = 15  # Slightly larger for SIMBAD objects
            scaled_circle_radius = max(8, base_circle_radius * self.scale_factor)
            scaled_pen_width = max(2, 3 * self.scale_factor)  # Thicker line for SIMBAD objects
            
            x_pixel, y_pixel = self.simbad_pixel_coords
            
            if (0 <= x_pixel < pixmap.width() and 0 <= y_pixel < pixmap.height()):
                # Draw circle in red
                circle_pen = QPen(QColor(255, 0, 0))
                circle_pen.setWidth(int(scaled_pen_width))
                painter.setPen(circle_pen)
                painter.drawEllipse(int(x_pixel - scaled_circle_radius), int(y_pixel - scaled_circle_radius), 
                                   int(scaled_circle_radius * 2), int(scaled_circle_radius * 2))
                
                # Add object name
                text_x = int(x_pixel + scaled_circle_radius + 8)
                text_y = int(y_pixel + 8)
                
                # Draw outline
                outline_pen = QPen(QColor(0, 0, 0))
                outline_pen.setWidth(int(max(2, 5 * self.scale_factor)))
                painter.setPen(outline_pen)
                painter.drawText(text_x, text_y, self.simbad_object.name)
                
                # Draw text in red
                text_pen = QPen(QColor(255, 0, 0))
                painter.setPen(text_pen)
                painter.drawText(text_x, text_y, self.simbad_object.name)
            
            painter.end()
        
        return pixmap

    def _get_cached_zoom(self, scale_factor, working_pixmap):
        """Get cached zoom level or create and cache it"""
        # Round scale factor to reduce cache size
        rounded_scale = round(scale_factor, 2)
        cache_key = (rounded_scale, working_pixmap.width(), working_pixmap.height())
        
        if cache_key in self.zoom_cache:
            return self.zoom_cache[cache_key]
        
        # Calculate the scaled size
        scaled_width = int(working_pixmap.width() * rounded_scale)
        scaled_height = int(working_pixmap.height() * rounded_scale)
        
        # Use faster scaling for better performance
        if rounded_scale > 2.0:
            # For high zoom levels, use smooth transformation
            scaled_pixmap = working_pixmap.scaled(
                scaled_width,
                scaled_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            # For normal zoom levels, use fast transformation
            scaled_pixmap = working_pixmap.scaled(
                scaled_width,
                scaled_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
        
        # Cache the result
        self.zoom_cache[cache_key] = scaled_pixmap
        
        # Limit cache size
        if len(self.zoom_cache) > self.max_cache_size:
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(self.zoom_cache))
            del self.zoom_cache[oldest_key]
        
        return scaled_pixmap

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
            self.base_pixmap = self.create_image_object(self.image_data, self.display_min, self.display_max)
            self.last_stretch_state = current_stretch
            # Clear zoom cache when stretch changes
            self.clear_zoom_cache()
        
        # Start with base pixmap
        working_pixmap = self.base_pixmap
        
        # Add object markers if enabled
        if self.show_objects and self.object_pixel_coords:
            working_pixmap = working_pixmap.copy()
            working_pixmap = self._add_object_markers(working_pixmap)
        elif self.show_simbad_object and self.simbad_object:
            working_pixmap = working_pixmap.copy()
            working_pixmap = self._add_object_markers(working_pixmap)
        
        # Get cached or create scaled pixmap
        scaled_pixmap = self._get_cached_zoom(self.scale_factor, working_pixmap)
        
        # Set the pixmap
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.setFixedSize(scaled_pixmap.size())
        
        # Store current pixmap for coordinate calculations
        self.pixmap = scaled_pixmap

    def load_image(self, image_data=None, title=None):
        """Load and display an image - optimized version"""
        self.image_data = image_data
        
        # Calculate bit depth information
        if image_data is not None:
            data_type = image_data.dtype
            if data_type == np.uint8:
                self.bit_depth = "255 (8 bits)"
            elif data_type == np.uint16:
                self.bit_depth = "65535 (16 bits)"
            elif data_type == np.uint32:
                self.bit_depth = "4294967295 (32 bits)"
            elif data_type == np.int16:
                self.bit_depth = "32767 (16 bits)"
            elif data_type == np.int32:
                self.bit_depth = "2147483647 (32 bits)"
            elif data_type == np.float32:
                self.bit_depth = "float (32 bits)"
            elif data_type == np.float64:
                self.bit_depth = "float (64 bits)"
            else:
                self.bit_depth = f"{data_type}"
        else:
            self.bit_depth = None
        
        # Create base pixmap (without scaling)
        self.base_pixmap = self.create_image_object(image_data)
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
                from astropy.io import fits
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
