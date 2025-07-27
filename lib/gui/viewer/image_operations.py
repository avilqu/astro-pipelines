from PyQt6.QtCore import QObject, pyqtSignal, QThread, Qt
from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QApplication


class AlignmentWorker(QObject):
    """Worker class for performing image alignment in a background thread."""
    progress = pyqtSignal(float)
    finished = pyqtSignal(list, object, int, int, list)  # aligned_datas, common_wcs, new_nx, new_ny, headers
    error = pyqtSignal(str)

    def __init__(self, image_datas, headers, pad_x, pad_y):
        super().__init__()
        self.image_datas = image_datas
        self.headers = headers
        self.pad_x = pad_x
        self.pad_y = pad_y

    def run(self):
        """Execute the image alignment."""
        try:
            from lib.fits.align import compute_padded_reference_wcs, reproject_images_to_common_wcs
            common_wcs, (new_nx, new_ny) = compute_padded_reference_wcs(self.headers, paddings=(self.pad_x, self.pad_y))
            aligned_datas = reproject_images_to_common_wcs(
                self.image_datas, self.headers, common_wcs, (new_ny, new_nx), progress_callback=self.progress.emit
            )
            self.finished.emit(aligned_datas, common_wcs, new_nx, new_ny, self.headers)
        except Exception as e:
            self.error.emit(str(e))


class ImageOperationsMixin:
    """Mixin class providing image calibration, platesolving, and alignment functionality."""
    
    def align_images(self):
        """Align all loaded images using WCS information."""
        from lib.fits.align import check_all_have_wcs, check_pixel_scales_match
        
        # Remove overlays before aligning
        self._simbad_overlay = None
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
        
        # Check all have WCS
        if not check_all_have_wcs(headers):
            QMessageBox.critical(self, "Alignment Error", "One or more images is not platesolved (missing WCS). Alignment aborted.")
            return
        
        # Check pixel scales match
        if not check_pixel_scales_match(headers):
            QMessageBox.critical(self, "Alignment Error", "Pixel scales do not match between images. Alignment aborted.")
            return
        
        pad_x, pad_y = 100, 100
        
        # Progress dialog
        progress = QProgressDialog("Aligning images...", None, 0, len(image_datas), self)
        progress.setWindowTitle("Aligning")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()
        
        # Start worker thread
        self._align_thread = QThread()
        self._align_worker = AlignmentWorker(image_datas, headers, pad_x, pad_y)
        self._align_worker.moveToThread(self._align_thread)
        self._align_thread.started.connect(self._align_worker.run)
        self._align_worker.progress.connect(lambda frac: (progress.setValue(int(frac * len(image_datas))), QApplication.processEvents()))
        
        def on_finished(aligned_datas, common_wcs, new_nx, new_ny, headers):
            progress.close()
            for i, path in enumerate(self.loaded_files):
                new_header = headers[0].copy()
                new_header['NAXIS1'] = new_nx
                new_header['NAXIS2'] = new_ny
                self._preloaded_fits[path] = (aligned_datas[i], new_header, common_wcs)
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