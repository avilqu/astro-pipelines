"""
Database operations and threading for the GUI.
"""

import os
from PyQt6.QtCore import QThread, pyqtSignal
from lib.db import get_db_manager


class DatabaseLoaderThread(QThread):
    """Thread for loading database data to avoid blocking the GUI."""
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
    
    def run(self):
        try:
            db_manager = get_db_manager(self.db_path)
            fits_files = db_manager.get_all_fits_files()
            self.data_loaded.emit(fits_files)
        except Exception as e:
            self.error_occurred.emit(str(e))


class DatabaseScannerThread(QThread):
    """Thread for scanning FITS files and calibration masters to avoid blocking the GUI."""
    scan_completed = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    output_received = pyqtSignal(str)  # New signal for real-time output

    def run(self):
        import sys
        import io
        from contextlib import redirect_stdout
        try:
            from lib.db import scan_fits_library, scan_calibration_masters
            class SignalStringIO(io.StringIO):
                def __init__(self, signal, buffer_size=100):
                    super().__init__()
                    self.signal = signal
                    self.buffer = []
                    self.buffer_size = buffer_size
                def write(self, text):
                    lines = text.splitlines(keepends=True)
                    for line in lines:
                        self.buffer.append(line)
                        if len(self.buffer) >= self.buffer_size:
                            self._emit_buffer()
                def flush(self):
                    self._emit_buffer()
                    super().flush()
                def close(self):
                    self._emit_buffer()
                    super().close()
                def _emit_buffer(self):
                    if self.buffer:
                        self.signal.emit(''.join(self.buffer))
                        self.buffer.clear()
            sio = SignalStringIO(self.output_received, buffer_size=100)
            with redirect_stdout(sio):
                fits_results = scan_fits_library()
                print("\n--- Calibration Masters Scan ---\n")
                calib_results = scan_calibration_masters()
            sio.flush()  # Ensure any remaining output is emitted

            # Combine results for summary
            summary = {
                'files_imported': fits_results.get('files_imported', 0),
                'files_skipped': fits_results.get('files_skipped', 0),
                'total_files_found': fits_results.get('total_files_found', 0),
                'calib_imported': calib_results.get('files_imported', 0),
                'calib_skipped': calib_results.get('files_skipped', 0),
                'calib_total_found': calib_results.get('total_files_found', 0),
                'errors': (fits_results.get('errors', []) or []) + (calib_results.get('errors', []) or [])
            }
            self.scan_completed.emit(summary)
        except Exception as e:
            self.error_occurred.emit(str(e))


class DatabaseManager:
    """Manages database operations for the GUI."""
    
    def __init__(self, db_path=None):
        if db_path is None:
            import config
            db_path = config.DATABASE_PATH
        self.db_path = db_path
    
    def get_db_manager(self):
        """Get the database manager instance."""
        return get_db_manager(self.db_path)
    
    def delete_fits_file(self, fits_file_id):
        """Delete a FITS file from the database."""
        try:
            db_manager = self.get_db_manager()
            return db_manager.delete_fits_file(fits_file_id)
        except Exception as e:
            raise Exception(f"Error deleting file: {str(e)}")
    
    def get_fits_file_by_id(self, fits_file_id, fits_files):
        """Get a FITS file by ID from the provided list."""
        return next((f for f in fits_files if f.id == fits_file_id), None) 