#!/usr/bin/env python3
"""
Astronomical Image Library GUI
A PyQt6-based interface for managing a library of FITS files.
"""

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, 
    QMenuBar, QMessageBox, QProgressBar, QStatusBar
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

# Import our modular components
from .database import DatabaseLoaderThread, DatabaseScannerThread, DatabaseManager
from .table import FitsTableWidget


class AstroLibraryGUI(QMainWindow):
    """Main window for the Astronomical Image Library application."""
    
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
        self.setWindowTitle("Astronomical Image Library")
        self.setGeometry(100, 100, 1200, 800)
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Create table widget
        self.table_widget = FitsTableWidget()
        main_layout.addWidget(self.table_widget)
        
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
    
    def create_menu_bar(self):
        """Create the menu bar with File and Database menus."""
        menubar = self.menuBar()
        
        # Create File menu
        file_menu = menubar.addMenu("File")
        
        # Add Exit action
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Create Database menu
        db_menu = menubar.addMenu("Database")
        
        # Add Scan action
        scan_action = QAction("Scan for New Files", self)
        scan_action.triggered.connect(self.scan_for_files)
        db_menu.addAction(scan_action)
    
    def connect_signals(self):
        """Connect all the signals and slots."""
        # Table connections
        self.table_widget.selection_changed.connect(self.on_table_selection_changed)
    
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