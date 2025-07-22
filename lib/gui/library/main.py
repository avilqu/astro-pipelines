#!/usr/bin/env python3
"""
Astronomical Image Library GUI
A PyQt6-based interface for managing a library of FITS files.
"""

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, 
    QMenuBar, QMessageBox, QProgressBar, QStatusBar, QSplitter, QStackedWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

# Import our modular components
from .database import DatabaseLoaderThread, DatabaseScannerThread, DatabaseManager
from .table_obslog import FitsTableWidget
from .table_main import MainFitsTableWidget
from .left_panel import LeftPanel
from .table_calibration import MasterDarksTableWidget, MasterBiasTableWidget, MasterFlatsTableWidget
from lib.db import get_db_manager
from lib.db.models import CalibrationMaster
from lib.gui.library.menu_bar import create_menu_bar


class AstroLibraryGUI(QMainWindow):
    """Main window for Astropipes Library."""
    
    def __init__(self):
        super().__init__()
        self.db_manager = DatabaseManager()
        self.fits_files = []
        self.init_ui()
        self.connect_signals()
        self.load_database()
    
    def init_ui(self):
        """Initialize the user interface."""
        # Set window properties
        self.setWindowTitle("Astropipes Library")
        self.setGeometry(100, 100, 1200, 800)
        
        # Create menu bar using the new function
        create_menu_bar(self, self.close, self.scan_for_files)
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left panel (menu)
        self.left_panel = LeftPanel()
        splitter.addWidget(self.left_panel)
        
        # Right panel (stacked widget for future extensibility)
        self.right_stack = QStackedWidget()
        self.table_widget = FitsTableWidget()
        self.main_table_widget = MainFitsTableWidget()
        self.master_darks_table = MasterDarksTableWidget()
        self.master_bias_table = MasterBiasTableWidget()
        self.master_flats_table = MasterFlatsTableWidget()
        self.right_stack.addWidget(self.table_widget)  # index 0: Obs log
        self.right_stack.addWidget(self.main_table_widget)  # index 1: Main table (targets/dates)
        self.right_stack.addWidget(self.master_darks_table)  # index 2: Master darks
        self.right_stack.addWidget(self.master_bias_table)   # index 3: Master bias
        self.right_stack.addWidget(self.master_flats_table)  # index 4: Master flats
        splitter.addWidget(self.right_stack)
        splitter.setStretchFactor(1, 1)  # Make right panel expand more
        splitter.setSizes([self.left_panel.minimumWidth(), 1000])  # Left panel at min width
        
        # Create status bar
        self.create_status_bar()
    
    def create_status_bar(self):
        """Create the status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)
        
        # Progress bar for operations
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
    
    def connect_signals(self):
        """Connect all the signals and slots."""
        # Table connections
        self.table_widget.selection_changed.connect(self.on_table_selection_changed)
        # Menu selection
        self.left_panel.menu_selection_changed.connect(self.on_menu_selection_changed)
    
    def load_database(self):
        """Load FITS files from the database."""
        self.status_label.setText("Loading database...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        
        # Use thread to avoid blocking GUI
        self.loader_thread = DatabaseLoaderThread('astropipes.db')
        self.loader_thread.data_loaded.connect(self.on_data_loaded)
        self.loader_thread.error_occurred.connect(self.on_database_error)
        self.loader_thread.start()
    
    def on_data_loaded(self, fits_files):
        """Handle loaded database data."""
        self.fits_files = fits_files
        self.table_widget.populate_table(fits_files)
        self.status_label.setText(f"Loaded {len(fits_files)} FITS files")
        self.progress_bar.setVisible(False)
    
    def on_database_error(self, error_message):
        """Handle database loading errors."""
        self.status_label.setText("Database error")
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Database Error", f"Failed to load database: {error_message}")
    
    def on_table_selection_changed(self, fits_file_ids):
        """Handle table selection changes."""
        # Currently no actions needed on selection change
        # The selection now returns a list of file IDs from the selected run(s)
        pass
    
    def on_menu_selection_changed(self, category, value):
        """Switch right panel content based on menu selection."""
        if category == "obslog":
            self.right_stack.setCurrentIndex(0)
        elif category == "target":
            filtered = [f for f in self.fits_files if f.target == value]
            self.main_table_widget.populate_table(filtered)
            self.right_stack.setCurrentIndex(1)
        elif category == "date":
            filtered = [f for f in self.fits_files if f.date_obs and f.date_obs.strftime('%Y-%m-%d') == value]
            self.main_table_widget.populate_table(filtered)
            self.right_stack.setCurrentIndex(1)
        elif category == "darks":
            db = get_db_manager()
            session = db.get_session()
            darks = session.query(CalibrationMaster).filter_by(frame="Dark").all()
            session.close()
            self.master_darks_table.populate(darks)
            self.right_stack.setCurrentIndex(2)
        elif category == "bias":
            db = get_db_manager()
            session = db.get_session()
            biases = session.query(CalibrationMaster).filter_by(frame="Bias").all()
            session.close()
            self.master_bias_table.populate(biases)
            self.right_stack.setCurrentIndex(3)
        elif category == "flats":
            db = get_db_manager()
            session = db.get_session()
            flats = session.query(CalibrationMaster).filter_by(frame="Flat").all()
            session.close()
            self.master_flats_table.populate(flats)
            self.right_stack.setCurrentIndex(4)
        # Do nothing for 'targets', 'dates', or other parent nodes
    
    def scan_for_files(self):
        """Scan for new FITS files."""
        self.status_label.setText("Scanning for new files...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        # Run scan in thread to avoid blocking GUI
        self.scanner_thread = DatabaseScannerThread()
        self.scanner_thread.scan_completed.connect(self.on_scan_completed)
        self.scanner_thread.error_occurred.connect(self.on_scan_error)
        self.scanner_thread.start()
    
    def on_scan_completed(self, results):
        """Handle scan completion."""
        self.progress_bar.setVisible(False)
        self.status_label.setText("Scan completed")
        
        QMessageBox.information(
            self, "Scan Complete",
            f"Scan completed successfully!\n\n"
            f"Files imported: {results['files_imported']}\n"
            f"Files skipped: {results['files_skipped']}\n"
            f"Total found: {results['total_files_found']}"
        )
        self.load_database()  # Refresh the table
    
    def on_scan_error(self, error_message):
        """Handle scan errors."""
        self.progress_bar.setVisible(False)
        self.status_label.setText("Scan failed")
        QMessageBox.critical(self, "Scan Error", f"Error during scan: {error_message}")


def main():
    """Main function to launch the GUI application."""
    app = QApplication(sys.argv)
    
    # Create and show the main window
    window = AstroLibraryGUI()
    window.show()
    
    # Start the event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main() 