import sys
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.time import Time
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, 
                             QScrollArea, QLabel, QFrame, QSizePolicy, QTextEdit, 
                             QDialog, QStatusBar, QLineEdit, QMessageBox, QProgressBar)
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QPainter, QWheelEvent, QMouseEvent, QKeyEvent, QFont, QPen, QColor


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
        # Add panning state tracking
        self.panning = False
        self.pan_start_pos = QPoint()
        self.pan_start_scroll = QPoint()
        self.original_cursor = None
        # Add smooth panning timer
        self.pan_timer = QTimer()
        self.pan_timer.timeout.connect(self._update_pan)
        self.pan_timer.setInterval(16)  # ~60 FPS for smooth panning
        self.target_scroll_pos = QPoint()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events for panning"""
        if event.button() == Qt.MouseButton.LeftButton and self.parent_viewer:
            self.panning = True
            self.pan_start_pos = event.pos()
            # Store the initial scroll positions
            scroll_area = self.parent_viewer.scroll_area
            self.pan_start_scroll = QPoint(
                scroll_area.horizontalScrollBar().value(),
                scroll_area.verticalScrollBar().value()
            )
            # Store original cursor and set closed hand cursor
            self.original_cursor = self.cursor()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            # Hide the cursor during panning
            self.setCursor(Qt.CursorShape.BlankCursor)
            # Start the pan timer
            self.pan_timer.start()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move events for panning and coordinate display"""
        if self.parent_viewer and self.parent_viewer.pixmap is not None:
            # Handle panning with improved logic
            if self.panning:
                # Calculate the target scroll position based on total movement
                delta = event.pos() - self.pan_start_pos
                self.target_scroll_pos = QPoint(
                    self.pan_start_scroll.x() - delta.x(),
                    self.pan_start_scroll.y() - delta.y()
                )
            else:
                # Only update coordinates when not panning
                # Throttle coordinate updates to reduce CPU usage
                self.last_mouse_pos = event.pos()
                if not self.coord_timer.isActive():
                    self.coord_timer.start(50)  # Update every 50ms max
        
        super().mouseMoveEvent(event)
    
    def _update_pan(self):
        """Update panning position smoothly using timer"""
        if not self.panning or not self.parent_viewer:
            return
            
        scroll_area = self.parent_viewer.scroll_area
        h_scroll = scroll_area.horizontalScrollBar()
        v_scroll = scroll_area.verticalScrollBar()
        
        # Ensure target scroll values stay within bounds
        target_h = max(0, min(self.target_scroll_pos.x(), h_scroll.maximum()))
        target_v = max(0, min(self.target_scroll_pos.y(), v_scroll.maximum()))
        
        # Get current positions
        current_h = h_scroll.value()
        current_v = v_scroll.value()
        
        # Use simple linear interpolation
        interpolation_factor = 0.7
        new_h = int(current_h + (target_h - current_h) * interpolation_factor)
        new_v = int(current_v + (target_v - current_v) * interpolation_factor)
        
        # Ensure final values are within bounds
        new_h = max(0, min(new_h, h_scroll.maximum()))
        new_v = max(0, min(new_v, v_scroll.maximum()))
        
        # Update scroll positions
        h_scroll.setValue(new_h)
        v_scroll.setValue(new_v)
    
    def _update_coordinates(self):
        """Update coordinate display (called by timer to reduce CPU usage)"""
        if not self.parent_viewer or not self.parent_viewer.wcs or self.panning:
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
            self.panning = False
            # Stop the pan timer
            self.pan_timer.stop()
            # Restore the original cursor
            if self.original_cursor:
                self.setCursor(self.original_cursor)
                self.original_cursor = None
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


class SolvingProgressDialog(QDialog):
    """Dialog to show solving progress with real-time console output"""
    
    # Signals for thread-safe GUI updates
    output_added = pyqtSignal(str)
    solving_finished_signal = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Solving Progress")
        self.setGeometry(200, 200, 600, 400)
        self.setModal(True)
        
        # Setup layout
        layout = QVBoxLayout(self)
        
        # Console output area
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: 'Courier New', monospace;
                font-size: 10px;
                border: 1px solid #333333;
            }
        """)
        layout.addWidget(self.console_output)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_solving)
        button_layout.addWidget(self.cancel_button)
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        self.close_button.setEnabled(False)  # Disabled until solving completes
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        # Solving state
        self.solving_completed = False
        self.solving_successful = False
        self.solving_cancelled = False
        
        # Connect signals to slots
        self.output_added.connect(self._add_output_slot)
        self.solving_finished_signal.connect(self._solving_finished_slot)
        
    def add_output(self, text):
        """Add text to the console output (thread-safe)"""
        self.output_added.emit(text)
        
    def solving_finished(self, successful=True):
        """Called when solving is finished (thread-safe)"""
        self.solving_finished_signal.emit(successful)
        
    # Slot methods (run on main thread)
    def _add_output_slot(self, text):
        """Slot to add output on main thread"""
        self.console_output.append(text)
        # Auto-scroll to bottom
        cursor = self.console_output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.console_output.setTextCursor(cursor)
        
    def _solving_finished_slot(self, successful):
        """Slot to handle solving finished on main thread"""
        self.solving_completed = True
        self.solving_successful = successful
        
        # Enable close button and disable cancel button
        self.close_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        
    def cancel_solving(self):
        """Cancel the solving process"""
        self.solving_cancelled = True
        self.console_output.append("User cancelled solving process.")
        
        # Import and set the solver interruption flag
        from .solver import set_solver_interrupted
        set_solver_interrupted(True)
        
        # Enable close button
        self.close_button.setEnabled(True)
        self.cancel_button.setEnabled(False) 