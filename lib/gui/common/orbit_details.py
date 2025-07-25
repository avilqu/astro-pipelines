from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel, QTextEdit, QHBoxLayout, QPushButton, QLineEdit, QMessageBox, QProgressDialog, QAbstractItemView
from PyQt6.QtGui import QFont, QColor, QBrush, QTextCursor
from PyQt6.QtCore import pyqtSignal, QThread, QObject
from astropy.coordinates import Angle
import astropy.units as u
from astropy.time import Time
import os

class OrbitDataWindow(QDialog):
    row_selected = pyqtSignal(int, object)  # row index, ephemeris tuple
    def __init__(self, object_name, orbit_data, predicted_positions, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Orbital elements - {object_name}")
        self.setGeometry(300, 200, 800, 600)
        self.setModal(False)
        
        layout = QVBoxLayout(self)
        
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
        
        self.setLayout(layout)
    
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
        exclude = {"ISO_time", "JD", "date_obs"}
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

class OrbitComputationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compute Orbit Data")
        self.setModal(True)
        self.setFixedSize(400, 150)
        
        layout = QVBoxLayout(self)
        
        # Instructions
        instruction_label = QLabel("Enter the object designation (e.g., C34UMY1):")
        layout.addWidget(instruction_label)
        
        # Object name input
        self.object_input = QLineEdit()
        self.object_input.setPlaceholderText("Object designation...")
        layout.addWidget(self.object_input)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.compute_button = QPushButton("Compute")
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
    
    def __init__(self, object_name, loaded_files):
        super().__init__()
        self.object_name = object_name
        self.loaded_files = loaded_files
    
    def run(self):
        try:
            from lib.astrometry.orbit import predict_position_findorb, get_neofixer_orbit
            predicted_positions = []
            orbit_data = None
            
            # Get orbital elements from NEOfixer
            try:
                orbit_data = get_neofixer_orbit(self.object_name)
            except Exception as e:
                print(f"Failed to get orbital elements for {self.object_name}: {e}")
                orbit_data = None
            
            # Get predicted positions from Find_Orb for each FITS file
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
                    try:
                        result = predict_position_findorb(self.object_name, date_obs_fmt)
                        if result and 'ephemeris' in result and 'entries' in result['ephemeris']:
                            entry = result['ephemeris']['entries']['0']  # First entry
                            entry['date_obs'] = date_obs_fmt  # Add the formatted date_obs
                            predicted_positions.append(entry)
                    except Exception as e:
                        print(f"[DEBUG] Failed to get predicted position for {fits_path}: {e}")
                        continue
                else:
                    print(f"[DEBUG] No date_obs found for {fits_path}, skipping prediction.")
            self.finished.emit(orbit_data, predicted_positions)
        except Exception as e:
            self.error.emit(str(e)) 