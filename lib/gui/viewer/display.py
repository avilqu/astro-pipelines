import numpy as np
from PyQt6.QtGui import QPixmap, QImage

from PyQt6.QtWidgets import (QPushButton, QVBoxLayout, QHBoxLayout, 
                             QLabel, QDialog, QLineEdit, QMessageBox)

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
                self.reject()
                
        except Exception as e:
            QMessageBox.critical(self, "Search Error", f"Error searching SIMBAD: {str(e)}")
        finally:
            # Re-enable search button
            self.search_button.setEnabled(True)
            self.search_button.setText("Search")


def create_image_object(image_data: np.ndarray, display_min=None, display_max=None):
    """Convert numpy array to QPixmap for display - optimized version"""
    # Use provided display range or calculate from histogram
    if display_min is None or display_max is None:
        histo = np.histogram(image_data, 60, None, True)
        display_min = histo[1][0]
        display_max = histo[1][-1]
    
    # Apply histogram stretching
    if display_max > display_min:
        clipped_data = np.clip(image_data, display_min, display_max)
        normalized_data = (clipped_data - display_min) / (display_max - display_min)
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