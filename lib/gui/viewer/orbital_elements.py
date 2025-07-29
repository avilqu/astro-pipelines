import sys
import os
import numpy as np
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTabWidget, QTableWidget, QTableWidgetItem, 
                             QLabel, QTextEdit, QPushButton, QAbstractItemView,
                             QMessageBox, QDialog, QLineEdit, QProgressDialog,
                             QMenuBar, QMenu, QFileDialog)
from PyQt6.QtGui import QFont, QColor, QBrush, QTextCursor, QAction
from PyQt6.QtCore import pyqtSignal, QThread, QObject, Qt
from astropy.coordinates import Angle
import astropy.units as u
from astropy.time import Time
import re
from datetime import datetime
from scipy.optimize import least_squares

class OrbitDataWindow(QMainWindow):
    row_selected = pyqtSignal(int, object)  # row index, ephemeris tuple
    def __init__(self, object_name, predicted_positions, pseudo_mpec_text="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Orbit Details - {object_name}")
        self.setGeometry(300, 200, 1000, 700)
        
        # Store data for stacking
        self.object_name = object_name
        self.predicted_positions = predicted_positions
        self.pseudo_mpec_text = pseudo_mpec_text
        self.parent_viewer = parent
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Create Positions tab
        self._create_positions_tab()
        
        # Create Pseudo MPEC tab
        self._create_pseudo_mpec_tab()
        
        # Populate data
        self._populate_predicted_positions(predicted_positions)
        self._populate_pseudo_mpec(pseudo_mpec_text)
    
    def _create_positions_tab(self):
        """Create the Positions tab with the predicted positions table."""
        positions_widget = QWidget()
        positions_layout = QVBoxLayout()
        positions_widget.setLayout(positions_layout)
        
        # Predicted positions table
        self.positions_table = QTableWidget()
        self.positions_table.setColumnCount(5)
        self.positions_table.setHorizontalHeaderLabels([
            "Date/Time", "RA (deg)", "Dec (deg)", "RA (h:m:s)", "Dec (d:m:s)"
        ])
        self.positions_table.setFont(QFont("Courier New", 10))
        self.positions_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.positions_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        positions_layout.addWidget(self.positions_table)
        
        # Connect selection change instead of clicks to enable keyboard navigation
        self.positions_table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        
        # Add the tab
        self.tab_widget.addTab(positions_widget, "Ephemerides")
    
    def _create_pseudo_mpec_tab(self):
        """Create the Pseudo MPEC tab with text display."""
        pseudo_mpec_widget = QWidget()
        pseudo_mpec_layout = QVBoxLayout()
        pseudo_mpec_widget.setLayout(pseudo_mpec_layout)
        
        # Pseudo MPEC text area
        self.pseudo_mpec_text_edit = QTextEdit()
        self.pseudo_mpec_text_edit.setReadOnly(True)
        self.pseudo_mpec_text_edit.setFont(QFont("Courier New", 10))
        pseudo_mpec_layout.addWidget(self.pseudo_mpec_text_edit)
        
        # Add the tab
        self.tab_widget.addTab(pseudo_mpec_widget, "Pseudo MPEC")
    
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
        
        # Set initial selection to first row to trigger viewer update
        if predicted_positions:
            self.positions_table.selectRow(0)

    def _populate_pseudo_mpec(self, pseudo_mpec_text):
        """Populate the pseudo MPEC text area."""
        if pseudo_mpec_text:
            self.pseudo_mpec_text_edit.setPlainText(pseudo_mpec_text)
        else:
            self.pseudo_mpec_text_edit.setPlainText("No pseudo MPEC data available.")

    def _on_row_clicked(self, row, col):
        if 0 <= row < len(self.predicted_positions):
            self.row_selected.emit(row, self.predicted_positions[row])

    def _on_selection_changed(self, selected, deselected):
        """Handle selection changes to enable keyboard navigation."""
        selected_rows = self.positions_table.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            if 0 <= row < len(self.predicted_positions):
                self.row_selected.emit(row, self.predicted_positions[row])

    def add_positions_tab(self, positions, cursor_coords):
        """Add a new tab showing computed object positions."""
        # Check if the Positions tab already exists
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Positions":
                # Update existing tab
                self._update_positions_tab(positions, cursor_coords, i)
                return
        
        # Create new Positions tab
        self._create_positions_tab_new(positions, cursor_coords)
    
    def _create_positions_tab_new(self, positions, cursor_coords):
        """Create a new Positions tab with the computed positions."""
        positions_widget = QWidget()
        positions_layout = QVBoxLayout()
        positions_widget.setLayout(positions_layout)
        
        # Store cursor coordinates for later use
        self.cursor_coords = cursor_coords
        
        # Add Compute LSPC button
        lspc_button = QPushButton("Compute LSPC")
        lspc_button.setFont(QFont("Arial", 10))
        lspc_button.clicked.connect(lambda: self._compute_lspc(positions))
        positions_layout.addWidget(lspc_button)
        
        # Create LSPC solution text area
        self.lspc_solution_text = QTextEdit()
        self.lspc_solution_text.setReadOnly(True)
        self.lspc_solution_text.setFont(QFont("Courier New", 10))
        self.lspc_solution_text.setMaximumHeight(150)
        self.lspc_solution_text.setPlaceholderText("LSPC solution will appear here after computation...")
        positions_layout.addWidget(self.lspc_solution_text)
        
        # Create table for positions
        self.computed_positions_table = QTableWidget()
        self.computed_positions_table.setColumnCount(8)
        self.computed_positions_table.setHorizontalHeaderLabels([
            "File", "Original X", "Original Y", "Stacked X", "Stacked Y", 
            "Shift X", "Shift Y", "RA/Dec"
        ])
        self.computed_positions_table.setFont(QFont("Courier New", 9))
        self.computed_positions_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.computed_positions_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        positions_layout.addWidget(self.computed_positions_table)
        
        # Connect selection change to enable keyboard navigation
        self.computed_positions_table.selectionModel().selectionChanged.connect(self._on_computed_positions_selection_changed)
        
        # Store the positions data for row selection
        self.computed_positions_data = positions
        
        # Populate the table
        self._populate_computed_positions(positions)
        
        # Add the tab
        self.tab_widget.addTab(positions_widget, "Positions")
    
    def _update_positions_tab(self, positions, cursor_coords, tab_index):
        """Update an existing Positions tab with new data."""
        positions_widget = self.tab_widget.widget(tab_index)
        if positions_widget:
            # Store cursor coordinates for later use
            self.cursor_coords = cursor_coords
            
            # Clear existing layout
            for i in reversed(range(positions_widget.layout().count())):
                child = positions_widget.layout().itemAt(i).widget()
                if child:
                    child.deleteLater()
            
            # Recreate the layout
            positions_layout = positions_widget.layout()
            
            # Add information about the cursor position
            info_label = QLabel(f"Cursor position in stacked image: {cursor_coords}")
            info_label.setFont(QFont("Arial", 10))
            positions_layout.addWidget(info_label)
            
            # Add Compute LSPC button
            lspc_button = QPushButton("Compute LSPC")
            lspc_button.setFont(QFont("Arial", 10))
            lspc_button.clicked.connect(lambda: self._compute_lspc(positions))
            positions_layout.addWidget(lspc_button)
            
            # Create LSPC solution text area
            self.lspc_solution_text = QTextEdit()
            self.lspc_solution_text.setReadOnly(True)
            self.lspc_solution_text.setFont(QFont("Courier New", 10))
            self.lspc_solution_text.setMaximumHeight(150)
            self.lspc_solution_text.setPlaceholderText("LSPC solution will appear here after computation...")
            positions_layout.addWidget(self.lspc_solution_text)
            
            # Create table for positions
            self.computed_positions_table = QTableWidget()
            self.computed_positions_table.setColumnCount(8)
            self.computed_positions_table.setHorizontalHeaderLabels([
                "File", "Original X", "Original Y", "Stacked X", "Stacked Y", 
                "Shift X", "Shift Y", "RA/Dec"
            ])
            self.computed_positions_table.setFont(QFont("Courier New", 9))
            self.computed_positions_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.computed_positions_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            positions_layout.addWidget(self.computed_positions_table)
            
            # Connect selection change to enable keyboard navigation
            self.computed_positions_table.selectionModel().selectionChanged.connect(self._on_computed_positions_selection_changed)
            
            # Store the positions data for row selection
            self.computed_positions_data = positions
            
            # Populate the table
            self._populate_computed_positions(positions)
    
    def _compute_lspc(self, positions):
        """Compute LSPC using matched Gaia stars."""
        if not hasattr(self, 'parent_viewer') or not self.parent_viewer:
            QMessageBox.warning(self, "Error", "No parent viewer available.")
            return
        
        # Check if Gaia detection results are available
        if not hasattr(self.parent_viewer, '_gaia_detection_overlay') or not self.parent_viewer._gaia_detection_overlay:
            QMessageBox.warning(self, "No Star Catalog", 
                              "Load a star catalog first.\n\n"
                              "To load a star catalog:\n"
                              "1. Go to the Catalogs menu\n"
                              "2. Select 'Detect Gaia Stars in Image'\n"
                              "3. This will load Gaia DR3 stars and match them with detected sources")
            return
        
        gaia_detection_results = self.parent_viewer._gaia_detection_overlay
        
        if not gaia_detection_results:
            QMessageBox.warning(self, "No Matched Stars", 
                              "No matched Gaia stars available.\n\n"
                              "Please load Gaia stars and match them with detected sources first.")
            return
        
        # Check if we have enough stars for LSPC (need at least 3)
        if len(gaia_detection_results) < 3:
            QMessageBox.warning(self, "Insufficient Stars", 
                              f"Only {len(gaia_detection_results)} matched stars found.\n\n"
                              "At least 3 comparison stars are required for LSPC calculation.")
            return
        
        # Compute LSPC
        try:
            lspc_results = self._calculate_lspc(gaia_detection_results, positions)
            self._update_positions_table_with_lspc(lspc_results)
        except Exception as e:
            QMessageBox.critical(self, "LSPC Error", f"Error computing LSPC: {str(e)}")
    
    def _calculate_lspc(self, gaia_detection_results, positions):
        """Calculate LSPC using matched Gaia stars."""
        
        # Extract comparison star data
        # gaia_detection_results is a list of (GaiaObject, DetectedSource, distance_arcsec) tuples
        comparison_stars = []
        for gaia_obj, detected_source, distance_arcsec in gaia_detection_results:
            comparison_stars.append({
                'catalog_ra': gaia_obj.ra,      # Catalog RA (degrees)
                'catalog_dec': gaia_obj.dec,    # Catalog Dec (degrees)
                'measured_x': detected_source.x, # Measured pixel X
                'measured_y': detected_source.y, # Measured pixel Y
                'gaia_id': gaia_obj.source_id
            })
        
        # For now, we'll use a simple linear transformation
        # In practice, you might want to use a more sophisticated plate model
        # This is a simplified version - you can enhance it later
        
        # Collect data for least squares
        catalog_ras = np.array([star['catalog_ra'] for star in comparison_stars])
        catalog_decs = np.array([star['catalog_dec'] for star in comparison_stars])
        measured_xs = np.array([star['measured_x'] for star in comparison_stars])
        measured_ys = np.array([star['measured_y'] for star in comparison_stars])
        
        # Simple linear transformation: RA = a*x + b*y + c, Dec = d*x + e*y + f
        def residuals(params):
            a, b, c, d, e, f = params
            predicted_ra = a * measured_xs + b * measured_ys + c
            predicted_dec = d * measured_xs + e * measured_ys + f
            ra_residuals = predicted_ra - catalog_ras
            dec_residuals = predicted_dec - catalog_decs
            return np.concatenate([ra_residuals, dec_residuals])
        
        # Initial guess (simple scaling)
        initial_guess = [0.001, 0.0, np.mean(catalog_ras), 0.0, -0.001, np.mean(catalog_decs)]
        
        # Solve least squares
        result = least_squares(residuals, initial_guess)
        
        if not result.success:
            raise ValueError("LSPC calculation failed to converge")
        
        a, b, c, d, e, f = result.x
        
        # Calculate RMS residuals
        final_residuals = residuals(result.x)
        ra_rms = np.sqrt(np.mean(final_residuals[:len(comparison_stars)]**2))
        dec_rms = np.sqrt(np.mean(final_residuals[len(comparison_stars):]**2))
        
        # Apply LSPC to the computed positions
        lspc_positions = []
        for pos in positions:
            original_x = pos['original_x']
            original_y = pos['original_y']
            
            # Apply LSPC transformation
            lspc_ra = a * original_x + b * original_y + c
            lspc_dec = d * original_x + e * original_y + f
            
            lspc_positions.append({
                **pos,
                'lspc_ra': lspc_ra,
                'lspc_dec': lspc_dec
            })
        
        return {
            'plate_constants': {'a': a, 'b': b, 'c': c, 'd': d, 'e': e, 'f': f},
            'rms_ra': ra_rms,
            'rms_dec': dec_rms,
            'comparison_stars': comparison_stars,
            'lspc_positions': lspc_positions
        }
    
    def _update_positions_table_with_lspc(self, lspc_results):
        """Update the positions table with LSPC results."""
        # Update the table headers to include LSPC columns
        self.computed_positions_table.setColumnCount(12)
        self.computed_positions_table.setHorizontalHeaderLabels([
            "File", "Original X", "Original Y", "Stacked X", "Stacked Y", 
            "Shift X", "Shift Y", "WCS RA", "WCS Dec", "LSPC RA", "LSPC Dec", "Difference"
        ])
        
        # Update the table data with LSPC results
        lspc_positions = lspc_results['lspc_positions']
        self.computed_positions_table.setRowCount(len(lspc_positions))
        
        for i, pos in enumerate(lspc_positions):
            # File name (basename only)
            filename = os.path.basename(pos['file_path'])
            self.computed_positions_table.setItem(i, 0, QTableWidgetItem(filename))
            
            # Original coordinates
            self.computed_positions_table.setItem(i, 1, QTableWidgetItem(f"{pos['original_x']:.2f}"))
            self.computed_positions_table.setItem(i, 2, QTableWidgetItem(f"{pos['original_y']:.2f}"))
            
            # Stacked coordinates
            self.computed_positions_table.setItem(i, 3, QTableWidgetItem(f"{pos['stacked_x']:.2f}"))
            self.computed_positions_table.setItem(i, 4, QTableWidgetItem(f"{pos['stacked_y']:.2f}"))
            
            # Shifts
            self.computed_positions_table.setItem(i, 5, QTableWidgetItem(f"{pos['shift_x']:.2f}"))
            self.computed_positions_table.setItem(i, 6, QTableWidgetItem(f"{pos['shift_y']:.2f}"))
            
            # WCS coordinates
            wcs_ra = pos.get('ra', 'N/A')
            wcs_dec = pos.get('dec', 'N/A')
            if wcs_ra != 'N/A' and wcs_dec != 'N/A':
                self.computed_positions_table.setItem(i, 7, QTableWidgetItem(f"{wcs_ra:.6f}"))
                self.computed_positions_table.setItem(i, 8, QTableWidgetItem(f"{wcs_dec:.6f}"))
            else:
                self.computed_positions_table.setItem(i, 7, QTableWidgetItem("N/A"))
                self.computed_positions_table.setItem(i, 8, QTableWidgetItem("N/A"))
            
            # LSPC coordinates
            self.computed_positions_table.setItem(i, 9, QTableWidgetItem(f"{pos['lspc_ra']:.6f}"))
            self.computed_positions_table.setItem(i, 10, QTableWidgetItem(f"{pos['lspc_dec']:.6f}"))
            
            # Calculate and display difference
            if wcs_ra != 'N/A' and wcs_dec != 'N/A':
                ra_diff = (pos['lspc_ra'] - wcs_ra) * 3600  # Convert to arcseconds
                dec_diff = (pos['lspc_dec'] - wcs_dec) * 3600
                distance = np.sqrt(ra_diff**2 + dec_diff**2)
                diff_text = f"{distance:.2f}\""
            else:
                diff_text = "N/A"
            
            self.computed_positions_table.setItem(i, 11, QTableWidgetItem(diff_text))
        
        # Resize columns to fit content
        self.computed_positions_table.resizeColumnsToContents()
        
        # Update the stored positions data with LSPC results
        self.computed_positions_data = lspc_positions
        
        # Show LSPC information in the tab
        self._show_lspc_info_in_tab(lspc_results)
    
    def _show_lspc_info_in_tab(self, lspc_results):
        """Show LSPC information in the current Positions tab."""
        # Format LSPC solution values for display
        solution_text = "LSPC SOLUTION VALUES\n"
        solution_text += "=" * 50 + "\n\n"
        
        # Plate constants
        solution_text += "PLATE CONSTANTS:\n"
        solution_text += "-" * 20 + "\n"
        constants = lspc_results['plate_constants']
        solution_text += f"a = {constants['a']:12.8f}  (RA = a*x + b*y + c)\n"
        solution_text += f"b = {constants['b']:12.8f}  (Dec = d*x + e*y + f)\n"
        solution_text += f"c = {constants['c']:12.8f}\n"
        solution_text += f"d = {constants['d']:12.8f}\n"
        solution_text += f"e = {constants['e']:12.8f}\n"
        solution_text += f"f = {constants['f']:12.8f}\n\n"
        
        # RMS residuals
        solution_text += "RMS RESIDUALS:\n"
        solution_text += "-" * 15 + "\n"
        solution_text += f"RA  RMS: {lspc_results['rms_ra']:10.6f} degrees\n"
        solution_text += f"Dec RMS: {lspc_results['rms_dec']:10.6f} degrees\n"
        solution_text += f"RA  RMS: {lspc_results['rms_ra']*3600:10.2f} arcseconds\n"
        solution_text += f"Dec RMS: {lspc_results['rms_dec']*3600:10.2f} arcseconds\n\n"
        
        # Comparison stars info
        solution_text += "COMPARISON STARS:\n"
        solution_text += "-" * 18 + "\n"
        solution_text += f"Number of stars: {len(lspc_results['comparison_stars'])}\n\n"
        
        # Show individual star residuals
        solution_text += "STAR RESIDUALS:\n"
        solution_text += "-" * 16 + "\n"
        solution_text += "Gaia ID          RA Residual    Dec Residual   Total\n"
        solution_text += "                 (arcsec)       (arcsec)       (arcsec)\n"
        solution_text += "-" * 60 + "\n"
        
        # Calculate and display residuals for each comparison star
        for i, star in enumerate(lspc_results['comparison_stars']):
            # Apply LSPC transformation to measured coordinates
            a, b, c, d, e, f = (constants['a'], constants['b'], constants['c'], 
                               constants['d'], constants['e'], constants['f'])
            
            predicted_ra = a * star['measured_x'] + b * star['measured_y'] + c
            predicted_dec = d * star['measured_x'] + e * star['measured_y'] + f
            
            ra_residual = (predicted_ra - star['catalog_ra']) * 3600  # Convert to arcseconds
            dec_residual = (predicted_dec - star['catalog_dec']) * 3600
            total_residual = np.sqrt(ra_residual**2 + dec_residual**2)
            
            # Format Gaia ID (truncate if too long)
            gaia_id = str(star['gaia_id'])
            if len(gaia_id) > 15:
                gaia_id = gaia_id[:12] + "..."
            
            solution_text += f"{gaia_id:15s} {ra_residual:10.2f} {dec_residual:10.2f} {total_residual:10.2f}\n"
        
        # Update the LSPC solution text area
        if hasattr(self, 'lspc_solution_text'):
            self.lspc_solution_text.setPlainText(solution_text)
    
    def _on_computed_positions_selection_changed(self, selected, deselected):
        """Handle selection changes in the computed positions table."""
        selected_rows = self.computed_positions_table.selectionModel().selectedRows()
        if selected_rows and hasattr(self, 'computed_positions_data'):
            row = selected_rows[0].row()
            if 0 <= row < len(self.computed_positions_data):
                position_data = self.computed_positions_data[row]
                # Emit signal to parent viewer to show marker
                if hasattr(self, 'parent_viewer') and self.parent_viewer:
                    self.parent_viewer.on_computed_positions_row_selected(row, position_data)
    
    def _populate_computed_positions(self, positions):
        """Populate the computed positions table."""
        if not positions:
            self.computed_positions_table.setRowCount(0)
            return
        
        self.computed_positions_table.setRowCount(len(positions))
        
        for i, pos in enumerate(positions):
            # File name (basename only)
            filename = os.path.basename(pos['file_path'])
            self.computed_positions_table.setItem(i, 0, QTableWidgetItem(filename))
            
            # Original coordinates
            self.computed_positions_table.setItem(i, 1, QTableWidgetItem(f"{pos['original_x']:.2f}"))
            self.computed_positions_table.setItem(i, 2, QTableWidgetItem(f"{pos['original_y']:.2f}"))
            
            # Stacked coordinates
            self.computed_positions_table.setItem(i, 3, QTableWidgetItem(f"{pos['stacked_x']:.2f}"))
            self.computed_positions_table.setItem(i, 4, QTableWidgetItem(f"{pos['stacked_y']:.2f}"))
            
            # Shifts
            self.computed_positions_table.setItem(i, 5, QTableWidgetItem(f"{pos['shift_x']:.2f}"))
            self.computed_positions_table.setItem(i, 6, QTableWidgetItem(f"{pos['shift_y']:.2f}"))
            
            # RA/Dec
            if pos['ra'] is not None and pos['dec'] is not None:
                ra_str = f"{pos['ra']:.6f}"
                dec_str = f"{pos['dec']:.6f}"
                ra_dec_str = f"{ra_str}, {dec_str}"
            else:
                ra_dec_str = "N/A"
            self.computed_positions_table.setItem(i, 7, QTableWidgetItem(ra_dec_str))
        
        self.computed_positions_table.resizeColumnsToContents()

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
    finished = pyqtSignal(list, str)  # predicted_positions, pseudo_mpec_text
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
            from lib.sci.orbit import predict_position_findorb
            predicted_positions = []
            pseudo_mpec_text = ""
            
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
                    match = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::(\d{2}))?", date_obs)
                    if match:
                        seconds = match.group(3) if match.group(3) is not None else '00'
                        date_obs_fmt = f"{match.group(1)}T{match.group(2)}:{seconds}"
                    else:
                        # Fallback: try to parse and reformat
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
                        # Extract pseudo_mpec data
                        pseudo_mpec_text = result.get('pseudo_mpec', '')
                        print(f"[DEBUG] Extracted pseudo_mpec data: {len(pseudo_mpec_text)} characters")
                        
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
                        # Emit error for Find_Orb failure
                        self.error.emit("Could not get orbital elements from Find_Orb. The service may be temporarily unavailable.")
                        return
                except Exception as e:
                    print(f"[DEBUG] Failed to get predicted positions from Find_Orb: {e}")
                    # Emit error for Find_Orb failure
                    self.error.emit("Could not get orbital elements from Find_Orb. The service may be temporarily unavailable.")
                    return
            else:
                print("[DEBUG] No valid dates found for any files")
                # Emit error for no DATE-OBS found
                self.error.emit("No DATE-OBS found in loaded FITS files. Cannot compute predicted positions.")
                return
            
            self.finished.emit(predicted_positions, pseudo_mpec_text)
        except Exception as e:
            print(traceback.format_exc())
            self.error.emit(str(e))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr 