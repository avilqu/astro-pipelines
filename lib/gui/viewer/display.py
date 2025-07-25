import numpy as np
from PyQt6.QtGui import QPixmap, QImage

from PyQt6.QtWidgets import (QPushButton, QVBoxLayout, QHBoxLayout, 
                             QLabel, QDialog, QLineEdit, QMessageBox)
from PyQt6.QtCore import QObject, pyqtSignal, QThread
from PyQt6.QtWidgets import QProgressDialog, QApplication
from PyQt6.QtCore import Qt

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
        
        self.search_button.setEnabled(False)
        self.search_button.setText("Searching...")
        # Show progress dialog
        progress = QProgressDialog("Searching SIMBAD...", None, 0, 0, self)
        progress.setWindowTitle("SIMBAD Search")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()
        # Start worker thread
        self._simbad_thread = QThread()
        self._simbad_worker = SIMBADWorker(
            self.parent_viewer.astrometry_catalog,
            self.parent_viewer.wcs,
            self.parent_viewer.image_data.shape,
            object_name
        )
        self._simbad_worker.moveToThread(self._simbad_thread)
        self._simbad_thread.started.connect(self._simbad_worker.run)
        def on_finished(simbad_object, pixel_coords):
            progress.close()
            self._simbad_thread.quit()
            self._simbad_thread.wait()
            if simbad_object is None:
                QMessageBox.information(self, "Not Found", f"The object '{object_name}' was not found in SIMBAD.")
                self.search_button.setEnabled(True)
                self.search_button.setText("Search")
                return
            if pixel_coords is None:
                QMessageBox.information(self, "Object Out of Field", \
                    f"The object '{simbad_object.name}' was found in SIMBAD but is out of frame.\n" \
                    f"Coordinates: RA {simbad_object.ra:.4f}°, Dec {simbad_object.dec:.4f}°")
                self.search_button.setEnabled(True)
                self.search_button.setText("Search")
                self.reject()
                return
            self.result = (simbad_object, pixel_coords)
            QMessageBox.information(self, "Object Found", \
                f"Found '{simbad_object.name}' in the field!\n" \
                f"Type: {simbad_object.object_type}\n" \
                f"RA: {simbad_object.ra:.4f}°, Dec: {simbad_object.dec:.4f}°")
            self.search_button.setEnabled(True)
            self.search_button.setText("Search")
            self.accept()
        def on_error(msg):
            progress.close()
            self._simbad_thread.quit()
            self._simbad_thread.wait()
            QMessageBox.critical(self, "Search Error", f"Error searching SIMBAD: {msg}")
            self.search_button.setEnabled(True)
            self.search_button.setText("Search")
        self._simbad_worker.finished.connect(on_finished)
        self._simbad_worker.error.connect(on_error)
        self._simbad_thread.start()


class SIMBADWorker(QObject):
    finished = pyqtSignal(object, object)  # simbad_object, pixel_coords
    error = pyqtSignal(str)

    def __init__(self, astrometry_catalog, wcs, image_shape, object_name):
        super().__init__()
        self.astrometry_catalog = astrometry_catalog
        self.wcs = wcs
        self.image_shape = image_shape
        self.object_name = object_name

    def run(self):
        try:
            simbad_object = self.astrometry_catalog.simbad_search(self.object_name)
            if simbad_object is None:
                self.finished.emit(None, None)
                return
            if self.wcs is None:
                self.error.emit("No WCS information available. Please solve the image first.")
                return
            is_in_field, pixel_coords = self.astrometry_catalog.check_object_in_field(
                self.wcs, self.image_shape, simbad_object
            )
            if is_in_field:
                self.finished.emit(simbad_object, pixel_coords)
            else:
                self.finished.emit(simbad_object, None)
        except Exception as e:
            self.error.emit(str(e))


def create_image_object(image_data: np.ndarray, display_min=None, display_max=None, clipping=False, sigma_clip=3):
    """Convert numpy array to QPixmap for display - optimized version. NaNs are replaced with the minimum finite value. If clipping is True, use sigma_clip-sigma clipping for display range."""
    # Replace NaNs with the minimum finite value
    if np.isnan(image_data).any():
        finite_vals = image_data[np.isfinite(image_data)]
        fill_value = np.min(finite_vals) if finite_vals.size > 0 else 0
        image_data = np.nan_to_num(image_data, nan=fill_value)
    # Use provided display range or calculate from histogram or sigma clipping
    if display_min is None or display_max is None:
        if clipping:
            finite_vals = image_data[np.isfinite(image_data)]
            if finite_vals.size > 0:
                mean = np.mean(finite_vals)
                std = np.std(finite_vals)
                display_min = mean - sigma_clip * std
                display_max = mean + sigma_clip * std
            else:
                display_min = np.min(image_data)
                display_max = np.max(image_data)
        else:
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