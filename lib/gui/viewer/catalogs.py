from PyQt6.QtCore import QObject, pyqtSignal, QThread, Qt
from PyQt6.QtWidgets import QDialog, QMessageBox, QProgressDialog, QApplication, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit
from astropy.time import Time


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
    """Worker class for performing SIMBAD searches in a background thread."""
    finished = pyqtSignal(object, object)  # simbad_object, pixel_coords
    error = pyqtSignal(str)

    def __init__(self, astrometry_catalog, wcs, image_shape, object_name):
        super().__init__()
        self.astrometry_catalog = astrometry_catalog
        self.wcs = wcs
        self.image_shape = image_shape
        self.object_name = object_name

    def run(self):
        """Execute the SIMBAD search."""
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


class SkybotWorker(QObject):
    """Worker class for performing SkyBot searches in a background thread."""
    finished = pyqtSignal(list, dict)  # sso_list, pixel_coords_dict
    error = pyqtSignal(str)

    def __init__(self, astrometry_catalog, wcs, image_shape, epoch):
        super().__init__()
        self.astrometry_catalog = astrometry_catalog
        self.wcs = wcs
        self.image_shape = image_shape
        self.epoch = epoch

    def run(self):
        """Execute the SkyBot search."""
        try:
            sso_list = self.astrometry_catalog.get_field_objects(self.wcs, self.image_shape, self.epoch)
            pixel_coords = self.astrometry_catalog.get_object_pixel_coordinates(self.wcs, sso_list)
            pixel_coords_dict = {obj: (x, y) for (obj, x, y) in pixel_coords}
            self.finished.emit(sso_list, pixel_coords_dict)
        except Exception as e:
            self.error.emit(str(e))


class SIMBADFieldWorker(QObject):
    """Worker class for performing SIMBAD field searches in a background thread."""
    finished = pyqtSignal(list, list)  # simbad_objects, pixel_coords_list
    error = pyqtSignal(str)

    def __init__(self, astrometry_catalog, wcs, image_shape):
        super().__init__()
        self.astrometry_catalog = astrometry_catalog
        self.wcs = wcs
        self.image_shape = image_shape

    def run(self):
        """Execute the SIMBAD field search."""
        try:
            simbad_objects = self.astrometry_catalog.get_field_simbad_objects(self.wcs, self.image_shape)
            pixel_coords = self.astrometry_catalog.get_simbad_object_pixel_coordinates(self.wcs, simbad_objects)
            pixel_coords_list = [(x, y) for (obj, x, y) in pixel_coords]
            self.finished.emit(simbad_objects, pixel_coords_list)
        except Exception as e:
            self.error.emit(str(e))


class CatalogSearchMixin:
    """Mixin class providing SIMBAD and SkyBot search functionality."""
    
    def open_simbad_search_dialog(self):
        """Open the SIMBAD search dialog and handle results."""
        # Clear field overlay before single object search
        self._simbad_field_overlay = None
        
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
        """Open the Solar System Object search dialog using SkyBot."""
        from lib.sci.catalogs import SolarSystemObject
        
        # Remove overlays before new search
        self._simbad_overlay = None
        self._simbad_field_overlay = None
        self._sso_overlay = None
        self._overlay_visible = True
        self.update_overlay_button_visibility()
        
        if self.wcs is None or self.image_data is None:
            QMessageBox.warning(self, "No WCS", "No WCS/image data available. Please solve the image first.")
            return
        
        # --- Use DATE-OBS from FITS header as epoch ---
        epoch = self._get_epoch_from_header()
        
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
            # Temporarily block signals to avoid circular dependency
            self.overlay_toggle_action.blockSignals(True)
            self.overlay_toggle_action.setChecked(True)
            self.overlay_toggle_action.blockSignals(False)
        
        def on_error(msg):
            progress.close()
            self._skybot_thread.quit()
            self._skybot_thread.wait()
            QMessageBox.critical(self, "SSO Search Error", f"Error searching for solar system objects: {msg}")
        
        self._skybot_worker.finished.connect(on_finished)
        self._skybot_worker.error.connect(on_error)
        self._skybot_thread.start()

    def open_simbad_field_search_dialog(self):
        """Open the SIMBAD field search dialog and handle results."""
        # Clear single object overlay before field search
        self._simbad_overlay = None
        
        if self.wcs is None or self.image_data is None:
            QMessageBox.warning(self, "No WCS", "No WCS/image data available. Please solve the image first.")
            return
        
        # Progress dialog
        progress = QProgressDialog("Searching SIMBAD for field objects...", None, 0, 0, self)
        progress.setWindowTitle("SIMBAD Field Search")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()
        
        # Start worker thread
        self._simbad_field_thread = QThread()
        self._simbad_field_worker = SIMBADFieldWorker(self.astrometry_catalog, self.wcs, self.image_data.shape)
        self._simbad_field_worker.moveToThread(self._simbad_field_thread)
        self._simbad_field_thread.started.connect(self._simbad_field_worker.run)
        
        def on_finished(simbad_objects, pixel_coords_list):
            progress.close()
            self._simbad_field_thread.quit()
            self._simbad_field_thread.wait()
            if not simbad_objects:
                QMessageBox.information(self, "No Field Objects", "No field objects found in the image.")
                return
            # Overlay only those in field
            self._simbad_field_overlay = (simbad_objects, pixel_coords_list)
            self._simbad_field_highlight_index = None  # Reset highlight
            self._overlay_visible = True
            self.update_overlay_button_visibility()
            self.image_label.update()
            # Show SIMBAD field result window (all objects, with pixel coords if in field)
            try:
                from lib.gui.common.simbad_field_window import SIMBADFieldResultWindow
                dlg = SIMBADFieldResultWindow(simbad_objects, pixel_coords_list, self)
                dlg.simbad_field_row_selected.connect(self.on_simbad_field_row_selected)
                dlg.show()
            except ImportError:
                pass
            self.overlay_toggle_action.setVisible(True)
            # Temporarily block signals to avoid circular dependency
            self.overlay_toggle_action.blockSignals(True)
            self.overlay_toggle_action.setChecked(True)
            self.overlay_toggle_action.blockSignals(False)
        
        def on_error(msg):
            progress.close()
            self._simbad_field_thread.quit()
            self._simbad_field_thread.wait()
            QMessageBox.critical(self, "SIMBAD Field Search Error", f"Error searching for field objects: {msg}")
        
        self._simbad_field_worker.finished.connect(on_finished)
        self._simbad_field_worker.error.connect(on_error)
        self._simbad_field_thread.start()

    def _get_epoch_from_header(self):
        """Extract epoch from FITS header DATE-OBS field."""
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
        
        return epoch 