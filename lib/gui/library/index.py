#!/usr/bin/env python3
"""
Astronomical Image Library GUI
A PyQt6-based interface for managing a library of FITS files.
"""

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, 
    QMenuBar, QMessageBox, QProgressBar, QStatusBar, QSplitter, QStackedWidget, QDialog, QPushButton, QRadioButton, QHBoxLayout, QSpinBox, QGroupBox, QFileDialog, QLineEdit, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction

# Import our modular components
from .db_access import DatabaseLoaderThread, DatabaseScannerThread, DatabaseManager
from .obslog import FitsTableWidget
from .main_table import MainFitsTableWidget
from .sidebar import LeftPanel
from .calibration_tables import MasterDarksTableWidget, MasterBiasTableWidget, MasterFlatsTableWidget
from lib.db import get_db_manager
from lib.db.models import CalibrationMaster
from lib.gui.library.menu_bar import create_menu_bar
from lib.gui.common.console_window import ConsoleOutputWindow
import config
import importlib


class SettingsDialog(QDialog):
    settings_changed = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(320, 260)
        layout = QVBoxLayout(self)

        # Data path selection
        data_path_layout = QHBoxLayout()
        data_path_label = QLabel("Data Path:")
        self.data_path_edit = QLineEdit()
        self.data_path_edit.setReadOnly(True)
        data_path_browse = QPushButton("Browse")
        data_path_browse.clicked.connect(self.browse_data_path)
        data_path_layout.addWidget(data_path_label)
        data_path_layout.addWidget(self.data_path_edit)
        data_path_layout.addWidget(data_path_browse)
        layout.addLayout(data_path_layout)

        # Calibration path selection
        calib_path_layout = QHBoxLayout()
        calib_path_label = QLabel("Calibration Path:")
        self.calib_path_edit = QLineEdit()
        self.calib_path_edit.setReadOnly(True)
        calib_path_browse = QPushButton("Browse")
        calib_path_browse.clicked.connect(self.browse_calib_path)
        calib_path_layout.addWidget(calib_path_label)
        calib_path_layout.addWidget(self.calib_path_edit)
        calib_path_layout.addWidget(calib_path_browse)
        layout.addLayout(calib_path_layout)

        # Time mode radio buttons
        time_row = QHBoxLayout()
        time_label = QLabel("Time Display Mode:")
        self.utc_radio = QRadioButton("UTC time")
        self.local_radio = QRadioButton("Local time")
        time_row.addWidget(time_label)
        time_row.addWidget(self.utc_radio)
        time_row.addWidget(self.local_radio)
        time_row.addStretch()
        layout.addLayout(time_row)

        # Blink period input
        blink_layout = QHBoxLayout()
        blink_label = QLabel("Blink period (ms):")
        self.blink_spin = QSpinBox()
        self.blink_spin.setRange(10, 10000)
        self.blink_spin.setSingleStep(10)
        self.blink_spin.setValue(500)
        blink_layout.addWidget(blink_label)
        blink_layout.addWidget(self.blink_spin)
        layout.addLayout(blink_layout)

        # Save button
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)

        self.load_settings()

    def browse_data_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Data Path", self.data_path_edit.text() or "~")
        if path:
            self.data_path_edit.setText(path)

    def browse_calib_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Calibration Path", self.calib_path_edit.text() or "~")
        if path:
            self.calib_path_edit.setText(path)

    def load_settings(self):
        # Force reload config to get latest values
        importlib.reload(config)
        # Set data and calibration paths
        self.data_path_edit.setText(getattr(config, 'DATA_PATH', ''))
        self.calib_path_edit.setText(getattr(config, 'CALIBRATION_PATH', ''))
        # Set radio buttons
        if getattr(config, 'TIME_DISPLAY_MODE', 'UTC') == 'UTC':
            self.utc_radio.setChecked(True)
        else:
            self.local_radio.setChecked(True)
        # Set blink period
        self.blink_spin.setValue(getattr(config, 'BLINK_PERIOD_MS', 750))

    def save_settings(self):
        # Update config.py file with new values
        mode = 'UTC' if self.utc_radio.isChecked() else 'Local'
        blink = self.blink_spin.value()
        data_path = self.data_path_edit.text()
        calib_path = self.calib_path_edit.text()
        self.update_config_file(mode, blink, data_path, calib_path)
        self.settings_changed.emit()
        self.accept()

    def update_config_file(self, mode, blink, data_path, calib_path):
        import re
        import os
        config_path = os.path.join(os.path.dirname(__file__), '../../../config.py')
        with open(config_path, 'r') as f:
            lines = f.readlines()
        def replace_or_append(lines, key, value):
            pat = re.compile(rf'^{key}\s*=')
            for i, line in enumerate(lines):
                if pat.match(line):
                    lines[i] = f"{key} = {repr(value)}\n"
                    return lines
            lines.append(f"{key} = {repr(value)}\n")
            return lines
        lines = replace_or_append(lines, 'TIME_DISPLAY_MODE', mode)
        lines = replace_or_append(lines, 'BLINK_PERIOD_MS', blink)
        lines = replace_or_append(lines, 'DATA_PATH', data_path)
        lines = replace_or_append(lines, 'CALIBRATION_PATH', calib_path)
        with open(config_path, 'w') as f:
            f.writelines(lines)


class AstroLibraryGUI(QMainWindow):
    """Main window for Astropipes Library."""
    
    def __init__(self):
        super().__init__()
        self.db_manager = DatabaseManager()
        self.fits_files = []
        self.last_menu_category = None
        self.last_menu_value = None
        self.console_window = None  # For scan output
        self.init_ui()
        self.connect_signals()
        self.load_database()
    
    def init_ui(self):
        """Initialize the user interface."""
        # Set window properties
        self.setWindowTitle("Astropipes FITS Library")
        self.setGeometry(100, 100, 1200, 800)
        
        # Create menu bar using the new function
        create_menu_bar(self, self.close, self.scan_for_files, self.open_settings_dialog)
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        main_layout.setSpacing(0)  # Remove spacing between widgets
        
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
        # Add spacing to the left of the status label
        self.status_label = QLabel()
        self.status_label.setText("   Ready")  # Add left padding with spaces
        self.status_bar.addWidget(self.status_label)

        # Add a visual separator and a label for time display mode
        self.status_separator = QFrame()
        self.status_separator.setFrameShape(QFrame.Shape.VLine)
        self.status_separator.setFrameShadow(QFrame.Shadow.Sunken)
        self.status_bar.addWidget(self.status_separator)

        self.time_mode_label = QLabel()
        self.status_bar.addWidget(self.time_mode_label)

        # Progress bar for operations
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
    
    def connect_signals(self):
        """Connect all the signals and slots."""
        # Table connections
        self.table_widget.selection_changed.connect(self.on_table_selection_changed)
        self.table_widget.platesolving_completed.connect(self.load_database)
        self.main_table_widget.platesolving_completed.connect(self.load_database)
        # Menu selection
        self.left_panel.menu_selection_changed.connect(self.on_menu_selection_changed)
        self.left_panel.target_renamed.connect(lambda old, new: self.load_database())
    
    def load_database(self):
        """Load FITS files from the database."""
        self.status_label.setText("Loading database...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        
        # Use thread to avoid blocking GUI
        import config
        self.loader_thread = DatabaseLoaderThread(config.DATABASE_PATH)
        self.loader_thread.data_loaded.connect(self.on_data_loaded)
        self.loader_thread.error_occurred.connect(self.on_database_error)
        self.loader_thread.start()
    
    def on_data_loaded(self, fits_files):
        """Handle loaded database data."""
        self.fits_files = fits_files
        self.table_widget.populate_table(fits_files)
        # If main_table_widget is visible, repopulate it with the correct filter
        if self.right_stack.currentIndex() == 1:
            if self.last_menu_category == "target":
                filtered = [f for f in self.fits_files if f.target == self.last_menu_value]
                self.main_table_widget.populate_table(filtered)
            elif self.last_menu_category == "date":
                from config import TIME_DISPLAY_MODE, to_display_time
                if TIME_DISPLAY_MODE == 'Local':
                    filtered = [
                        f for f in self.fits_files
                        if f.date_obs and to_display_time(f.date_obs).strftime('%Y-%m-%d') == self.last_menu_value
                    ]
                else:
                    filtered = [
                        f for f in self.fits_files
                        if f.date_obs and f.date_obs.strftime('%Y-%m-%d') == self.last_menu_value
                    ]
                self.main_table_widget.populate_table(filtered)
        self.update_status_bar()
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
        self.last_menu_category = category
        self.last_menu_value = value
        if category == "obslog":
            self.right_stack.setCurrentIndex(0)
        elif category == "target":
            filtered = [f for f in self.fits_files if f.target == value]
            self.main_table_widget.populate_table(filtered)
            self.right_stack.setCurrentIndex(1)
        elif category == "date":
            from config import TIME_DISPLAY_MODE, to_display_time
            if TIME_DISPLAY_MODE == 'Local':
                filtered = [
                    f for f in self.fits_files
                    if f.date_obs and to_display_time(f.date_obs).strftime('%Y-%m-%d') == value
                ]
            else:
                filtered = [
                    f for f in self.fits_files
                    if f.date_obs and f.date_obs.strftime('%Y-%m-%d') == value
                ]
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
        self.update_status_bar()
    
    def scan_for_files(self):
        """Scan for new FITS files."""
        # Show console window for scan output
        if self.console_window is not None:
            self.console_window.close()
        self.console_window = ConsoleOutputWindow(title="Database Scan Output", parent=self)
        self.console_window.clear_output()
        self.console_window.show_and_raise()
        # Optionally, connect cancel button to stop scan (not implemented yet)
        # self.console_window.cancel_requested.connect(self.cancel_scan)
        # Start scan in thread
        self.status_label.setText("Scanning for new files...")
        # Hide progress bar
        self.progress_bar.setVisible(False)
        self.scanner_thread = DatabaseScannerThread()
        self.scanner_thread.output_received.connect(self.console_window.append_text)
        self.scanner_thread.scan_completed.connect(self.on_scan_completed)
        self.scanner_thread.error_occurred.connect(self.on_scan_error)
        self.scanner_thread.start()
    
    def on_scan_completed(self, results):
        """Handle scan completion."""
        self.status_label.setText("Scan completed")
        if self.console_window:
            self.console_window.append_text("\nScan completed successfully!\n")
            self.console_window.close_button.setEnabled(True)
        # Compose a single summary message
        msg = (
            "Scan completed successfully!\n\n"
            f"Files imported: {results.get('files_imported', 0)}\n"
            f"Files skipped: {results.get('files_skipped', 0)}\n"
            f"Total files found: {results.get('total_files_found', 0)}\n\n"
            f"Calibration masters imported: {results.get('calib_imported', 0)}\n"
            f"Calibration masters skipped: {results.get('calib_skipped', 0)}\n"
            f"Total calibration masters found: {results.get('calib_total_found', 0)}"
        )
        errors = results.get('errors', [])
        if errors:
            msg += f"\n\nErrors: {len(errors)}"
            if len(errors) > 0:
                msg += f"\nFirst error: {errors[0]}"
        QMessageBox.information(self, "Scan Complete", msg)
        self.left_panel.repopulate_targets_and_dates()
        self.load_database()  # Refresh the table
    
    def on_scan_error(self, error_message):
        """Handle scan errors."""
        self.status_label.setText("Scan failed")
        if self.console_window:
            self.console_window.append_text(f"\nScan failed: {error_message}\n")
            self.console_window.close_button.setEnabled(True)
        QMessageBox.critical(self, "Scan Error", f"Error during scan: {error_message}")

    def open_settings_dialog(self):
        dlg = SettingsDialog(self)
        dlg.settings_changed.connect(self.on_settings_changed)
        dlg.exec()

    def on_settings_changed(self):
        import importlib
        importlib.reload(config)
        self.left_panel.repopulate_targets_and_dates()
        self.load_database()

    def update_status_bar(self):
        """Update the status bar to show 'Showing x / y files' for the current view and the time display mode."""
        import config
        total = len(self.fits_files)
        current_index = self.right_stack.currentIndex()
        if current_index == 0:
            # Obs log
            shown = self.table_widget.get_visible_file_count()
        elif current_index == 1:
            shown = self.main_table_widget.get_visible_file_count()
        elif current_index == 2:
            shown = self.master_darks_table.get_visible_file_count()
        elif current_index == 3:
            shown = self.master_bias_table.get_visible_file_count()
        elif current_index == 4:
            shown = self.master_flats_table.get_visible_file_count()
        else:
            shown = 0
        self.status_label.setText(f"   Showing {shown} / {total} files")  # Add left padding
        # Update the time display mode label
        mode = getattr(config, 'TIME_DISPLAY_MODE', 'UTC')
        self.time_mode_label.setText(f"Time display mode: {mode}")


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