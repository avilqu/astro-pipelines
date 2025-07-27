from PyQt6.QtCore import QObject, pyqtSignal, QThread, Qt
from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QCheckBox

# Import configuration
from config import DEFAULT_ALIGNMENT_METHOD, FALLBACK_ALIGNMENT_METHOD, SHOW_ALIGNMENT_METHOD_DIALOG, MAX_ALIGNMENT_IMAGES


class AlignmentMethodDialog(QDialog):
    """Dialog for selecting alignment method."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Alignment Method")
        self.setModal(True)
        self.setFixedSize(400, 200)
        
        # Get available methods
        from lib.fits.align import get_alignment_methods
        self.available_methods = get_alignment_methods()
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Description
        desc_label = QLabel("Choose the alignment method to use:")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # Method selection
        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("Method:"))
        
        self.method_combo = QComboBox()
        for method in self.available_methods:
            if method == "astroalign":
                self.method_combo.addItem("Astroalign (Fast - Asterism-based)", method)
            elif method == "wcs_reprojection":
                self.method_combo.addItem("WCS Reprojection (Slow - Precise)", method)
            else:
                self.method_combo.addItem(method, method)
        
        # Set default selection
        default_index = self.method_combo.findData(DEFAULT_ALIGNMENT_METHOD)
        if default_index >= 0:
            self.method_combo.setCurrentIndex(default_index)
        else:
            # Set to first available method as fallback
            if self.method_combo.count() > 0:
                self.method_combo.setCurrentIndex(0)
        
        method_layout.addWidget(self.method_combo)
        layout.addLayout(method_layout)
        
        # Remember choice checkbox
        self.remember_checkbox = QCheckBox("Remember this choice")
        self.remember_checkbox.setChecked(False)
        layout.addWidget(self.remember_checkbox)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def get_selected_method(self):
        """Get the selected alignment method."""
        method = self.method_combo.currentData()
        
        # Safety check - if method is None or invalid, use default
        if method is None or method not in self.available_methods:
            method = DEFAULT_ALIGNMENT_METHOD
        
        return method
    
    def should_remember_choice(self):
        """Check if the user wants to remember this choice."""
        return self.remember_checkbox.isChecked()


class AlignmentWorker(QObject):
    """Worker class for performing image alignment in a background thread."""
    progress = pyqtSignal(float)
    finished = pyqtSignal(list, object, int, int, list)  # aligned_datas, common_wcs, new_nx, new_ny, headers
    error = pyqtSignal(str)

    def __init__(self, image_datas, headers, pad_x, pad_y, method="astroalign"):
        super().__init__()
        self.image_datas = image_datas
        self.headers = headers
        self.pad_x = pad_x
        self.pad_y = pad_y
        self.method = method

    def run(self):
        """Execute the image alignment."""
        try:
            if self.method == "astroalign":
                from lib.fits.align import align_images_with_astroalign, check_astroalign_available
                from lib.fits.wcs import copy_wcs_from_reference
                
                if not check_astroalign_available():
                    raise ImportError("astroalign package is not available. Please install it with: pip install astroalign")
                
                aligned_datas, reference_header = align_images_with_astroalign(
                    self.image_datas, self.headers, reference_index=0, progress_callback=self.progress.emit
                )
                
                # Copy WCS information from reference header to all aligned images
                updated_headers = []
                for i, header in enumerate(self.headers):
                    if i == 0:  # Reference image - keep original header
                        updated_headers.append(header)
                    else:  # Aligned images - copy WCS from reference
                        new_header = copy_wcs_from_reference(reference_header, header)
                        updated_headers.append(new_header)
                
                # Create WCS object from reference header
                common_wcs = None
                if reference_header:
                    from astropy.wcs import WCS
                    try:
                        common_wcs = WCS(reference_header)
                    except:
                        pass
                
                # Use reference image dimensions
                new_nx = reference_header['NAXIS1'] if reference_header else aligned_datas[0].shape[1]
                new_ny = reference_header['NAXIS2'] if reference_header else aligned_datas[0].shape[0]
                
            else:  # WCS reprojection method
                from lib.fits.align import compute_padded_reference_wcs, reproject_images_to_common_wcs
                common_wcs, (new_nx, new_ny) = compute_padded_reference_wcs(self.headers, paddings=(self.pad_x, self.pad_y))
                aligned_datas = reproject_images_to_common_wcs(
                    self.image_datas, self.headers, common_wcs, (new_ny, new_nx), progress_callback=self.progress.emit
                )
                updated_headers = self.headers  # Headers are already properly handled in WCS reprojection
            
            self.finished.emit(aligned_datas, common_wcs, new_nx, new_ny, updated_headers)
        except Exception as e:
            self.error.emit(str(e))


class ImageOperationsMixin:
    """Mixin class providing image calibration, platesolving, and alignment functionality."""
    
    def cleanup_temp_files(self):
        """Clean up temporary aligned files."""
        import shutil
        if hasattr(self, '_temp_aligned_dirs'):
            for temp_dir in self._temp_aligned_dirs:
                try:
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                except Exception as e:
                    print(f"Warning: Could not remove temporary directory {temp_dir}: {e}")
            self._temp_aligned_dirs.clear()
    
    def closeEvent(self, event):
        """Override closeEvent to cleanup temporary files."""
        self.cleanup_temp_files()
        # Call parent closeEvent if it exists
        if hasattr(super(), 'closeEvent'):
            super().closeEvent(event)
        else:
            event.accept()
    
    def align_images(self, method=None):
        """Align all loaded images using the specified method or configuration default.
        
        Parameters:
        -----------
        method : str, optional
            Alignment method: "astroalign" (fast, asterism-based) or "wcs_reprojection" (slow, WCS-based)
            If None, uses the method from configuration or shows dialog if enabled.
        """
        from lib.fits.align import check_all_have_wcs, check_pixel_scales_match, check_astroalign_available, get_alignment_methods
        
        # Remove overlays before aligning
        self._simbad_overlay = None
        self._simbad_field_overlay = None
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
        
        # Check image count limit
        if len(image_datas) > MAX_ALIGNMENT_IMAGES:
            reply = QMessageBox.question(
                self, "Many Images", 
                f"You are trying to align {len(image_datas)} images. This may take a long time and use significant memory. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Determine alignment method
        if method is None:
            if SHOW_ALIGNMENT_METHOD_DIALOG:
                # Show method selection dialog
                dialog = AlignmentMethodDialog(self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    method = dialog.get_selected_method()
                    # TODO: If dialog.should_remember_choice(), save to user preferences
                else:
                    return  # User cancelled
            else:
                # Use configuration default
                method = DEFAULT_ALIGNMENT_METHOD
        
        # Validate method
        available_methods = get_alignment_methods()
        
        if method not in available_methods:
            # Try fallback method
            if FALLBACK_ALIGNMENT_METHOD in available_methods:
                QMessageBox.warning(self, "Alignment Method Unavailable", 
                                  f"Requested method '{method}' not available. Using fallback method '{FALLBACK_ALIGNMENT_METHOD}'.")
                method = FALLBACK_ALIGNMENT_METHOD
            else:
                QMessageBox.critical(self, "Alignment Error", 
                                   f"Alignment method '{method}' not available. Available methods: {', '.join(available_methods)}")
                return
        
        # Method-specific validation
        if method == "wcs_reprojection":
            # Check all have WCS
            if not check_all_have_wcs(headers):
                QMessageBox.critical(self, "Alignment Error", "One or more images is not platesolved (missing WCS). Alignment aborted.")
                return
            
            # Check pixel scales match
            if not check_pixel_scales_match(headers):
                QMessageBox.critical(self, "Alignment Error", "Pixel scales do not match between images. Alignment aborted.")
                return
        
        elif method == "astroalign":
            if not check_astroalign_available():
                QMessageBox.critical(self, "Alignment Error", 
                                   "astroalign package is not available. Please install it with: pip install astroalign")
                return
        
        pad_x, pad_y = 100, 100
        
        # Progress dialog
        method_name = "Asterism-based" if method == "astroalign" else "WCS reprojection"
        progress = QProgressDialog(f"Aligning images using {method_name}...", None, 0, len(image_datas), self)
        progress.setWindowTitle("Aligning")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()
        
        # Start worker thread
        self._align_thread = QThread()
        self._align_worker = AlignmentWorker(image_datas, headers, pad_x, pad_y, method)
        self._align_worker.moveToThread(self._align_thread)
        self._align_thread.started.connect(self._align_worker.run)
        self._align_worker.progress.connect(lambda frac: (progress.setValue(int(frac * len(image_datas))), QApplication.processEvents()))
        
        def on_finished(aligned_datas, common_wcs, new_nx, new_ny, headers):
            progress.close()
            
            # Create temporary directory for aligned files
            import tempfile
            import os
            from astropy.io import fits
            
            temp_dir = tempfile.mkdtemp(prefix="astropipes-aligned-")
            if not hasattr(self, '_temp_aligned_dirs'):
                self._temp_aligned_dirs = []
            self._temp_aligned_dirs.append(temp_dir)  # Track for cleanup
            new_file_paths = []
            
            for i, path in enumerate(self.loaded_files):
                # Use the updated header for this specific image
                new_header = headers[i].copy()
                new_header['NAXIS1'] = new_nx
                new_header['NAXIS2'] = new_ny
                # Add alignment method info to header
                new_header['ALIGN_MTH'] = method
                if method == "astroalign":
                    new_header['COMMENT'] = 'Aligned using astroalign asterism matching'
                else:
                    new_header['COMMENT'] = 'Aligned using WCS reprojection'
                
                # Create WCS object for this specific image
                image_wcs = None
                try:
                    from astropy.wcs import WCS
                    image_wcs = WCS(new_header)
                except:
                    pass
                
                # Save aligned image to temporary file
                original_filename = os.path.basename(path)
                name, ext = os.path.splitext(original_filename)
                aligned_filename = f"aligned_{name}{ext}"
                aligned_path = os.path.join(temp_dir, aligned_filename)
                
                # Create FITS file with aligned data and updated header
                hdu = fits.PrimaryHDU(aligned_datas[i], new_header)
                hdu.writeto(aligned_path, overwrite=True)
                
                new_file_paths.append(aligned_path)
                
                # Update the preloaded fits cache
                self._preloaded_fits[aligned_path] = (aligned_datas[i], new_header, image_wcs)
            
            # Update loaded_files list to point to the new aligned files
            self.loaded_files = new_file_paths
            
            self.current_file_index = 0
            self.load_fits(self.loaded_files[0], restore_view=False)
            self.update_navigation_buttons()
            self.update_image_count_label()
            self.update_align_button_visibility()
            self._align_thread.quit()
            self._align_thread.wait()
        
        def on_error(msg):
            progress.close()
            QMessageBox.critical(self, "Alignment Error", f"Error during alignment: {msg}")
            self._align_thread.quit()
            self._align_thread.wait()
        
        self._align_worker.finished.connect(on_finished)
        self._align_worker.error.connect(on_error)
        self._align_thread.start()

    def align_images_fast(self):
        """Align images using the fast astroalign method."""
        self.align_images(method="astroalign")

    def align_images_wcs(self):
        """Align images using the slow WCS reprojection method."""
        self.align_images(method="wcs_reprojection")

    def _format_platesolving_result(self, result):
        """Format platesolving results for display."""
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
        """Platesolve all loaded images using astrometry.net."""
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
        """Calibrate all loaded images using bias, dark, and flat frames."""
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

    def calibrate_current_image(self):
        """Calibrate the currently displayed image using bias, dark, and flat frames."""
        from lib.gui.common.console_window import ConsoleOutputWindow
        from lib.gui.library.calibration_thread import CalibrationThread
        
        if not self.loaded_files:
            QMessageBox.warning(self, "No files", "No FITS files loaded to calibrate.")
            return
        
        current_file = self.loaded_files[self.current_file_index]
        
        console_window = ConsoleOutputWindow("Calibrating Current File", self)
        console_window.show_and_raise()
        
        # Store thread as instance variable to prevent premature destruction
        self._calibrate_current_thread = CalibrationThread(current_file)
        self._calibrate_current_thread.output.connect(console_window.append_text)
        
        def on_finished(result):
            if result.get('success'):
                # Replace the current file with the calibrated version
                calibrated_path = result['calibrated_path']
                self.loaded_files[self.current_file_index] = calibrated_path
                # Reload all files to ensure cache is consistent
                self._preloaded_fits.clear()
                for path in self.loaded_files:
                    self._preload_fits_file(path)
                self.load_fits(calibrated_path, restore_view=True)
                self.update_navigation_buttons()
                self.update_image_count_label()
                self.update_align_button_visibility()
                self.update_platesolve_button_visibility()
                console_window.append_text("\nFile calibrated and loaded.\n")
            else:
                console_window.append_text("\nCalibration failed.\n")
                QMessageBox.critical(self, "Calibration Error", "Calibration failed for the current file.")
            
            # Clean up thread reference
            self._calibrate_current_thread = None
        
        self._calibrate_current_thread.finished.connect(on_finished)
        self._calibrate_current_thread.start()

    def platesolve_current_image(self):
        """Platesolve the currently displayed image using astrometry.net."""
        from lib.gui.common.console_window import ConsoleOutputWindow
        from lib.gui.library.platesolving_thread import PlatesolvingThread
        
        if not self.loaded_files:
            QMessageBox.warning(self, "No files", "No FITS files loaded to platesolve.")
            return
        
        current_file = self.loaded_files[self.current_file_index]
        
        console_window = ConsoleOutputWindow("Platesolving Current File", self)
        console_window.show_and_raise()
        
        # Store thread as instance variable to prevent premature destruction
        self._platesolve_current_thread = PlatesolvingThread(current_file)
        self._platesolve_current_thread.output.connect(console_window.append_text)
        
        def on_finished(result):
            msg = self._format_platesolving_result(result)
            console_window.append_text(f"\n{msg}\n")
            
            if hasattr(result, 'success') and result.success:
                # Reload all files after platesolving to ensure cache is consistent
                self._preloaded_fits.clear()
                for path in self.loaded_files:
                    self._preload_fits_file(path)
                self.load_fits(current_file, restore_view=True)
                self.update_navigation_buttons()
                self.update_image_count_label()
                self.update_align_button_visibility()
                self.update_platesolve_button_visibility()
            
            # Clean up thread reference
            self._platesolve_current_thread = None
        
        self._platesolve_current_thread.finished.connect(on_finished)
        self._platesolve_current_thread.start() 