from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel, QTextEdit, QHBoxLayout, QPushButton, QLineEdit, QMessageBox, QProgressDialog
from PyQt6.QtGui import QFont, QColor, QBrush, QTextCursor
from PyQt6.QtCore import pyqtSignal, QThread, QObject
from astropy.coordinates import Angle
import astropy.units as u
from astropy.time import Time
import os

class OrbitDataWindow(QDialog):
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
        layout.addWidget(self.positions_table)
        
        # Populate data
        self._populate_orbital_elements(orbit_data)
        self._populate_predicted_positions(predicted_positions)
        
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
        """Populate the predicted positions table."""
        self.positions_table.setRowCount(len(predicted_positions))
        
        for i, (date_obs, ra, dec) in enumerate(predicted_positions):
            # Format RA and Dec in different ways
            try:
                ra_angle = Angle(ra, unit=u.deg)
                dec_angle = Angle(dec, unit=u.deg)
                ra_hms = ra_angle.to_string(unit=u.hourangle, sep=':', precision=1, pad=True)
                dec_dms = dec_angle.to_string(unit=u.deg, sep=':', precision=1, alwayssign=True, pad=True)
            except Exception:
                ra_hms = f"{ra:.6f}"
                dec_dms = f"{dec:.6f}"
            
            items = [
                QTableWidgetItem(date_obs),
                QTableWidgetItem(f"{ra:.6f}"),
                QTableWidgetItem(f"{dec:.6f}"),
                QTableWidgetItem(ra_hms),
                QTableWidgetItem(dec_dms)
            ]
            
            for col, item in enumerate(items):
                self.positions_table.setItem(i, col, item)
        
        self.positions_table.resizeColumnsToContents()

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
            from lib.astrometry.orbit import get_neofixer_orbit, predict_position_from_orbit
            
            # Get orbit data
            orbit_data = get_neofixer_orbit(self.object_name)
            
            # Get dates from loaded FITS files
            predicted_positions = []
            for fits_path in self.loaded_files:
                try:
                    from astropy.io import fits
                    with fits.open(fits_path) as hdul:
                        header = hdul[0].header
                        date_obs = header.get('DATE-OBS')
                        if date_obs:
                            # Predict position for this date
                            ra, dec = predict_position_from_orbit(orbit_data, date_obs)
                            predicted_positions.append((date_obs, ra, dec))
                except Exception as e:
                    # Skip files that can't be read
                    continue
            
            self.finished.emit(orbit_data, predicted_positions)
            
        except Exception as e:
            self.error.emit(str(e)) 