from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel, 
                             QTextEdit, QHBoxLayout, QPushButton, QLineEdit, QMessageBox, 
                             QProgressDialog, QAbstractItemView, QMenuBar, QMenu, QMainWindow,
                             QWidget, QFileDialog)
from PyQt6.QtGui import QFont, QColor, QBrush, QTextCursor, QAction
from PyQt6.QtCore import pyqtSignal, QThread, QObject, Qt
from astropy.coordinates import Angle
import astropy.units as u
from astropy.time import Time
import os

class OrbitDataWindow(QMainWindow):
    row_selected = pyqtSignal(int, object)  # row index, ephemeris tuple
    def __init__(self, object_name, orbit_data, predicted_positions, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Orbital elements - {object_name}")
        self.setGeometry(300, 200, 800, 600)
        
        # Store data for stacking
        self.object_name = object_name
        self.orbit_data = orbit_data
        self.predicted_positions = predicted_positions
        self.parent_viewer = parent
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        
        # Create menu bar
        self._create_menu_bar()
        
        # Title
        self.elements_text = QTextEdit()
        self.elements_text.setReadOnly(True)
        self.elements_text.setMaximumHeight(200)
        self.elements_text.setFont(QFont("Courier New", 10))
        layout.addWidget(self.elements_text)
        
        # Predicted positions table
        positions_label = QLabel("Predicted Positions:")
        positions_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(positions_label)
        
        self.positions_table = QTableWidget()
        self.positions_table.setColumnCount(5)
        self.positions_table.setHorizontalHeaderLabels([
            "Date/Time", "RA (deg)", "Dec (deg)", "RA (h:m:s)", "Dec (d:m:s)"
        ])
        self.positions_table.setFont(QFont("Courier New", 10))
        self.positions_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.positions_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.positions_table)
        
        # Populate data
        self._populate_orbital_elements(orbit_data)
        self._populate_predicted_positions(predicted_positions)
        
        self.predicted_positions = predicted_positions  # Store for access on click
        self.positions_table.cellClicked.connect(self._on_row_clicked)
    
    def _populate_orbital_elements(self, orbit_data):
        """Populate the orbital elements text area."""
        elements = orbit_data.get('elements', {})
        
        def format_value(value, format_str="{}"):
            """Safely format a value, handling None and non-numeric values."""
            if value is None or value == 'Unknown':
                return 'Unknown'
            try:
                return format_str.format(value)
            except (ValueError, TypeError):
                return str(value)
        
        text = f"""Epoch: {elements.get('epoch_iso', 'Unknown')}
Semi-major axis (a): {format_value(elements.get('a'), '{:.6f}')} AU
Eccentricity (e): {format_value(elements.get('e'), '{:.6f}')}
Inclination (i): {format_value(elements.get('i'), '{:.3f}')}°
Argument of perihelion (ω): {format_value(elements.get('arg_per'), '{:.3f}')}°
Longitude of ascending node (Ω): {format_value(elements.get('asc_node'), '{:.3f}')}°
Mean anomaly at epoch (M): {format_value(elements.get('M'), '{:.3f}')}°

Additional Information:
Period: {format_value(elements.get('P'), '{:.3f}')} days
Perihelion distance (q): {format_value(elements.get('q'), '{:.6f}')} AU
Aphelion distance (Q): {format_value(elements.get('Q'), '{:.6f}')} AU
Absolute magnitude (H): {format_value(elements.get('H'), '{:.2f}')}
Phase parameter (G): {format_value(elements.get('G'), '{:.2f}')}

MOID (Minimum Orbit Intersection Distance):
- Earth: {format_value(elements.get('MOIDs', {}).get('Earth'), '{:.6f}')} AU
- Venus: {format_value(elements.get('MOIDs', {}).get('Venus'), '{:.6f}')} AU
- Mars: {format_value(elements.get('MOIDs', {}).get('Mars'), '{:.6f}')} AU

Orbit Quality:
- RMS residual: {format_value(elements.get('rms_residual'), '{:.5f}')} arcsec
- Weighted RMS: {format_value(elements.get('weighted_rms_residual'), '{:.4f}')} arcsec
- Number of residuals: {elements.get('n_resids', 'Unknown')}
- Uncertainty parameter (U): {format_value(elements.get('U'), '{:.4f}')}"""
        
        self.elements_text.setPlainText(text)
    
    def _populate_predicted_positions(self, predicted_positions):
        """Populate the predicted positions table with all fields from the ephemeris entry, except ISO_time, JD, and date_obs."""
        if not predicted_positions:
            self.positions_table.setRowCount(0)
            return
        # Use all keys from the first entry as columns, except the excluded ones
        exclude = {"ISO_time", "JD", "date_obs", "RA60", "Dec60"}
        columns = [k for k in predicted_positions[0].keys() if k not in exclude]
        self.positions_table.setColumnCount(len(columns))
        self.positions_table.setHorizontalHeaderLabels(columns)
        self.positions_table.setRowCount(len(predicted_positions))
        for i, entry in enumerate(predicted_positions):
            for j, key in enumerate(columns):
                value = entry.get(key, "")
                self.positions_table.setItem(i, j, QTableWidgetItem(str(value)))
        self.positions_table.resizeColumnsToContents()

    def _on_row_clicked(self, row, col):
        if 0 <= row < len(self.predicted_positions):
            self.row_selected.emit(row, self.predicted_positions[row])
    
    def _create_menu_bar(self):
        """Create the menu bar with Actions menu."""
        menubar = self.menuBar()
        
        # Create Actions menu
        actions_menu = menubar.addMenu("Actions")
        
        # Create Stack on ephemeris action
        stack_action = QAction("Stack on ephemeris", self)
        stack_action.setStatusTip("Stack loaded images with motion tracking for this object")
        stack_action.triggered.connect(self._stack_on_ephemeris)
        actions_menu.addAction(stack_action)
    
    def _stack_on_ephemeris(self):
        """Perform motion tracking integration and load result in viewer."""
        if not self.parent_viewer or not hasattr(self.parent_viewer, 'loaded_files'):
            QMessageBox.warning(self, "No Files", "No FITS files are currently loaded in the viewer.")
            return
        
        loaded_files = self.parent_viewer.loaded_files
        if len(loaded_files) < 2:
            QMessageBox.warning(self, "Insufficient Files", "At least 2 FITS files are required for stacking.")
            return
        
        # Create output directory if it doesn't exist
        import os
        output_dir = "/tmp/astropipes-stacked"
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate output filename
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_object_name = self.object_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
        output_file = os.path.join(output_dir, f"motion_tracked_{safe_object_name}_{timestamp}.fits")
        
        # Create console window for output
        from lib.gui.common.console_window import ConsoleOutputWindow
        console_window = ConsoleOutputWindow("Motion Tracking Integration", self)
        console_window.show_and_raise()
        
        # Start stacking in background thread
        self._stack_thread = QThread()
        self._stack_worker = MotionTrackingStackWorker(
            loaded_files, 
            self.object_name, 
            output_file,
            console_window
        )
        self._stack_worker.moveToThread(self._stack_thread)
        self._stack_thread.started.connect(self._stack_worker.run)
        
        def on_console_output(text):
            console_window.append_text(text)
        
        def on_finished(success, message):
            if success:
                console_window.append_text(f"\n\033[1;32mMotion tracking integration completed successfully!\033[0m\n\n{message}\n")
                # Add the result to the loaded files in the viewer
                if self.parent_viewer and hasattr(self.parent_viewer, 'loaded_files'):
                    # Add to loaded files list
                    self.parent_viewer.loaded_files.append(output_file)
                    # Load the file in the viewer
                    self.parent_viewer.open_and_add_file(output_file)
                    # Update navigation buttons and file count
                    if hasattr(self.parent_viewer, 'update_navigation_buttons'):
                        self.parent_viewer.update_navigation_buttons()
                    if hasattr(self.parent_viewer, 'update_image_count_label'):
                        self.parent_viewer.update_image_count_label()
            else:
                console_window.append_text(f"\n\033[1;31mMotion tracking integration failed:\033[0m\n\n{message}\n")
            
            self._stack_thread.quit()
            self._stack_thread.wait()
        
        def on_cancel():
            console_window.append_text("\n\033[1;31mCancelling motion tracking integration...\033[0m\n")
            self._stack_thread.quit()
            self._stack_thread.wait()
            console_window.close()
        
        self._stack_worker.console_output.connect(on_console_output)
        self._stack_worker.finished.connect(on_finished)
        console_window.cancel_requested.connect(on_cancel)
        self._stack_thread.start()

class OrbitComputationDialog(QDialog):
    def __init__(self, parent=None, target_name=None):
        super().__init__(parent)
        self.setWindowTitle("Get orbital elements")
        self.setModal(True)
        self.setFixedSize(400, 150)
        
        layout = QVBoxLayout(self)
        
        # Instructions
        instruction_label = QLabel("Enter the object designation (e.g., C34UMY1):")
        layout.addWidget(instruction_label)
        
        # Object name input
        self.object_input = QLineEdit()
        self.object_input.setPlaceholderText("Object designation...")
        # Pre-fill with target name if provided
        if target_name:
            self.object_input.setText(target_name)
        layout.addWidget(self.object_input)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.compute_button = QPushButton("Get")
        self.compute_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.compute_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def get_object_name(self):
        return self.object_input.text().strip()

class OrbitComputationWorker(QObject):
    finished = pyqtSignal(dict, list)  # orbit_data, predicted_positions
    error = pyqtSignal(str)
    console_output = pyqtSignal(str)
    
    def __init__(self, object_name, loaded_files, console_window=None):
        super().__init__()
        self.object_name = object_name
        self.loaded_files = loaded_files
        self.console_window = console_window
    
    def run(self):
        import sys
        from lib.gui.common.console_window import RealTimeStringIO
        import traceback
        try:
            # Redirect stdout/stderr to the console_output signal (thread-safe)
            rtio = RealTimeStringIO(self.console_output.emit)
            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = rtio
            from lib.astrometry.orbit import predict_position_findorb, get_neofixer_orbit
            predicted_positions = []
            orbit_data = None
            
            # Get orbital elements from NEOfixer
            try:
                orbit_data = get_neofixer_orbit(self.object_name)
            except Exception as e:
                print(f"Failed to get orbital elements for {self.object_name}: {e}")
                orbit_data = None
            
            # Collect all observation dates from FITS files
            dates_obs = []
            date_to_file_map = {}  # Map formatted dates back to file paths for debugging
            
            for fits_path in self.loaded_files:
                date_obs = None
                print(f"\n[DEBUG] Processing file: {fits_path}")
                try:
                    from astropy.io import fits
                    with fits.open(fits_path) as hdul:
                        header = hdul[0].header
                        date_obs = header.get('DATE-OBS')
                        print(f"[DEBUG] DATE-OBS from header: {date_obs}")
                except Exception as e:
                    print(f"[DEBUG] Failed to read FITS header for {fits_path}: {e}")
                
                # If not found in header, try database
                if not date_obs:
                    try:
                        from lib.db.manager import get_db_manager
                        db_manager = get_db_manager()
                        db_entry = db_manager.get_fits_file_by_path(fits_path)
                        if db_entry:
                            print(f"[DEBUG] Found DB entry for {fits_path}. date_obs: {db_entry.date_obs}")
                        else:
                            print(f"[DEBUG] No DB entry found for {fits_path}")
                        if db_entry and db_entry.date_obs:
                            # Convert datetime to ISO string
                            date_obs = db_entry.date_obs.isoformat(sep='T', timespec='seconds')
                    except Exception as e:
                        print(f"[DEBUG] Failed to get date_obs from database for {fits_path}: {e}")
                
                if date_obs:
                    # Format date_obs to YYYY-MM-DDTHH:MM:SS (with 'T' and seconds, no Z, no decimal)
                    import re
                    match = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::(\d{2}))?", date_obs)
                    if match:
                        seconds = match.group(3) if match.group(3) is not None else '00'
                        date_obs_fmt = f"{match.group(1)}T{match.group(2)}:{seconds}"
                    else:
                        # Fallback: try to parse and reformat
                        from datetime import datetime
                        try:
                            dt = datetime.fromisoformat(date_obs.replace('Z', '+00:00'))
                            date_obs_fmt = dt.strftime('%Y-%m-%dT%H:%M:%S')
                        except Exception:
                            date_obs_fmt = date_obs[:10] + 'T' + date_obs[11:16] + ':00'  # crude fallback
                    
                    print(f"[DEBUG] Using date_obs for prediction (formatted): {date_obs_fmt}")
                    dates_obs.append(date_obs_fmt)
                    date_to_file_map[date_obs_fmt] = fits_path
                else:
                    print(f"[DEBUG] No date_obs found for {fits_path}, skipping prediction.")
            
            # Make a single call to Find_Orb with all dates
            if dates_obs:
                print(f"\n[DEBUG] Making Find_Orb API call for {len(dates_obs)} dates")
                try:
                    result = predict_position_findorb(self.object_name, dates_obs)
                    if result:
                        # Convert the result dictionary to a list of positions
                        for date_obs_fmt in dates_obs:
                            if date_obs_fmt in result:
                                entry = result[date_obs_fmt]
                                entry['date_obs'] = date_obs_fmt  # Ensure date_obs is included
                                predicted_positions.append(entry)
                                print(f"[DEBUG] Added position for {date_to_file_map.get(date_obs_fmt, 'unknown file')}: RA={entry.get('RA', 'N/A')}, Dec={entry.get('Dec', 'N/A')}")
                            else:
                                print(f"[DEBUG] No position found for {date_obs_fmt} (file: {date_to_file_map.get(date_obs_fmt, 'unknown')})")
                    else:
                        print("[DEBUG] No results returned from Find_Orb")
                except Exception as e:
                    print(f"[DEBUG] Failed to get predicted positions from Find_Orb: {e}")
            else:
                print("[DEBUG] No valid dates found for any files")
            
            self.finished.emit(orbit_data, predicted_positions)
        except Exception as e:
            print(traceback.format_exc())
            self.error.emit(str(e))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


class MotionTrackingStackWorker(QObject):
    """Worker thread for motion tracking integration."""
    console_output = pyqtSignal(str)  # console output text
    finished = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, files, object_name, output_path, console_window=None):
        super().__init__()
        self.files = files
        self.object_name = object_name
        self.output_path = output_path
        self.console_window = console_window
    
    def run(self):
        """Run the motion tracking integration."""
        try:
            import sys
            from lib.gui.common.console_window import RealTimeStringIO
            from lib.fits.integration import integrate_with_motion_tracking, MotionTrackingIntegrationError
            
            # Redirect stdout/stderr to console output
            rtio = RealTimeStringIO(self.console_output.emit)
            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = rtio
            
            try:
                self.console_output.emit(f"\033[1;34mStarting motion tracking integration for {self.object_name}\033[0m\n")
                self.console_output.emit(f"\033[1;34mProcessing {len(self.files)} files\033[0m\n")
                self.console_output.emit(f"\033[1;34mOutput will be saved to: {self.output_path}\033[0m\n\n")
                
                # Perform motion tracking integration
                result = integrate_with_motion_tracking(
                    files=self.files,
                    object_name=self.object_name,
                    method='average',
                    sigma_clip=True,
                    output_path=self.output_path
                )
                
                # Success message
                message = f"Successfully created motion tracked stack:\n"
                message += f"Object: {self.object_name}\n"
                message += f"Files processed: {len(self.files)}\n"
                message += f"Output: {self.output_path}\n"
                message += f"Image shape: {result.data.shape}\n"
                message += f"Data range: {result.data.min():.2f} to {result.data.max():.2f}"
                
                self.finished.emit(True, message)
                
            finally:
                # Restore stdout/stderr
                sys.stdout = old_stdout
                sys.stderr = old_stderr
            
        except MotionTrackingIntegrationError as e:
            self.finished.emit(False, f"Motion tracking integration error: {e}")
        except Exception as e:
            import traceback
            error_msg = f"Unexpected error during motion tracking integration:\n{str(e)}\n\n{traceback.format_exc()}"
            self.finished.emit(False, error_msg) 