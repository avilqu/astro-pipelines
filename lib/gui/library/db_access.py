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
    """Thread for scanning FITS files to avoid blocking the GUI."""
    scan_completed = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def run(self):
        try:
            from lib.db import scan_fits_library
            results = scan_fits_library()
            self.scan_completed.emit(results)
        except Exception as e:
            self.error_occurred.emit(str(e))


class DatabaseManager:
    """Manages database operations for the GUI."""
    
    def __init__(self, db_path='astropipes.db'):
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