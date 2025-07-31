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
import json
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
        
        
        # Add Generate Substacks button (initially disabled)
        self.generate_substacks_button = QPushButton("Generate Substacks")
        self.generate_substacks_button.setFont(QFont("Arial", 10))
        self.generate_substacks_button.setEnabled(False)  # Enabled after LSPC computed
        self.generate_substacks_button.clicked.connect(lambda: self._generate_substacks(positions))
        positions_layout.addWidget(self.generate_substacks_button)
        
        # Add Measure object positions button (disabled until substacks generated)
        self.measure_button = QPushButton("Measure object positions")
        self.measure_button.setFont(QFont("Arial", 10))
        self.measure_button.setEnabled(False)
        self.measure_button.clicked.connect(self._measure_object_positions)
        positions_layout.addWidget(self.measure_button)
        
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

        # Automatically compute LSPC once positions are available
        self._compute_lspc(positions)
        
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
            
            # Automatically compute LSPC (button removed)
            
            # Add Generate Substacks button (initially disabled)
            self.generate_substacks_button = QPushButton("Generate Substacks")
            self.generate_substacks_button.setFont(QFont("Arial", 10))
            self.generate_substacks_button.setEnabled(False)
            self.generate_substacks_button.clicked.connect(lambda: self._generate_substacks(positions))
            positions_layout.addWidget(self.generate_substacks_button)
            
            # Add Measure object positions button (disabled until substacks generated)
            self.measure_button = QPushButton("Measure object positions")
            self.measure_button.setFont(QFont("Arial", 10))
            self.measure_button.setEnabled(False)
            self.measure_button.clicked.connect(self._measure_object_positions)
            positions_layout.addWidget(self.measure_button)
            
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

            # Automatically compute LSPC once positions are updated
            self._compute_lspc(positions)
    
    def _generate_substacks(self, positions):
        """Generate three motion tracked substacks from the dataset."""
        if not hasattr(self, 'parent_viewer') or not self.parent_viewer:
            QMessageBox.warning(self, "Error", "No parent viewer available.")
            return
        
        if not self.parent_viewer.loaded_files:
            QMessageBox.warning(self, "No Files", "No FITS files loaded in the viewer.")
            return
        
        # Filter out already stacked images, keeping only individual images
        individual_files = self._filter_individual_images(self.parent_viewer.loaded_files)
        
        if len(individual_files) < 3:
            QMessageBox.warning(self, "Insufficient Files", 
                              f"Only {len(individual_files)} individual images found. At least 3 individual images are required to generate substacks.")
            return
        
        # Get the object name from the parent viewer
        object_name = getattr(self.parent_viewer, '_ephemeris_object_name', 'Unknown_Object')
        
        # Create output directory
        output_dir = "/tmp/astropipes/substacks"
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate timestamp for unique filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_object_name = object_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
        
        # Sort files by date_obs to ensure chronological order
        sorted_files = self._sort_files_by_date(individual_files)
        
        # Calculate the size of each substack (one third of the dataset)
        total_files = len(sorted_files)
        substack_size = total_files // 3
        
        if substack_size < 1:
            QMessageBox.warning(self, "Insufficient Files", 
                              f"With only {total_files} individual files, each substack would have less than 1 file.")
            return
        
        # Create substack file lists
        substack1_files = sorted_files[:substack_size]
        substack2_files = sorted_files[substack_size:2*substack_size]
        substack3_files = sorted_files[2*substack_size:]
        
        # Calculate object positions for each substack based on the computed positions
        object_positions = self._calculate_object_positions_for_substacks(positions, substack1_files, substack2_files, substack3_files)
        
        # Create console window for output
        from lib.gui.common.console_window import ConsoleOutputWindow
        console_window = ConsoleOutputWindow("Substack Generation", self)
        console_window.show_and_raise()
        
        # Start substack generation in background thread
        self._substack_thread = QThread()
        self._substack_worker = SubstacksGenerationWorker(
            substack1_files, substack2_files, substack3_files,
            object_name, output_dir, safe_object_name, timestamp,
            console_window, object_positions
        )
        self._substack_worker.moveToThread(self._substack_thread)
        self._substack_thread.started.connect(self._substack_worker.run)
        
        def on_console_output(text):
            console_window.append_text(text)
        
        def on_finished(success, message, output_files):
            if success:
                console_window.append_text(f"\n\033[1;32mSubstack generation completed successfully!\033[0m\n\n{message}\n")
                # Load the generated substacks into the viewer
                # First load full-frame substacks, then cropped versions
                full_frame_files = [f for f in output_files if 'cropped' not in os.path.basename(f)]
                cropped_files = [f for f in output_files if 'cropped' in os.path.basename(f)]
                
                # Load full-frame files first
                for file_path in full_frame_files:
                    self.parent_viewer.open_and_add_file(file_path)
                
                # Then load cropped files at the end
                for file_path in cropped_files:
                    self.parent_viewer.open_and_add_file(file_path)
                
                # Update viewer UI
                self.parent_viewer.update_navigation_buttons()
                self.parent_viewer.update_image_count_label()
                
                # Enable 'Measure object positions' button now that substacks are generated
                if hasattr(self, 'measure_button'):
                    self.measure_button.setEnabled(True)
            else:
                console_window.append_text(f"\n\033[1;31mSubstack generation failed:\033[0m\n\n{message}\n")
            
            self._substack_thread.quit()
            self._substack_thread.wait()
        
        def on_cancel():
            console_window.append_text("\n\033[1;31mCancelling substack generation...\033[0m\n")
            self._substack_thread.quit()
            self._substack_thread.wait()
            console_window.close()
        
        self._substack_worker.console_output.connect(on_console_output)
        self._substack_worker.finished.connect(on_finished)
        console_window.cancel_requested.connect(on_cancel)
        self._substack_thread.start()
    
    def _filter_individual_images(self, files):
        """Filter out already stacked images, keeping only individual images."""
        individual_files = []
        
        for file_path in files:
            try:
                from astropy.io import fits
                with fits.open(file_path) as hdul:
                    header = hdul[0].header
                    
                    # Check if this is a stacked image by looking for COMBINED header
                    combined = header.get('COMBINED', False)
                    if isinstance(combined, str):
                        combined = combined.lower() in ('true', '1', 'yes')
                    
                    # If not a combined/stacked image, include it
                    if not combined:
                        individual_files.append(file_path)
                    else:
                        # Log that we're excluding this stacked image
                        filename = os.path.basename(file_path)
                        print(f"Excluding stacked image: {filename}")
                        
            except Exception as e:
                # If we can't read the header, assume it's an individual image
                print(f"Warning: Could not read header for {file_path}: {e}")
                individual_files.append(file_path)
        
        return individual_files
    
    def _calculate_object_positions_for_substacks(self, positions, substack1_files, substack2_files, substack3_files):
        """Calculate the object position for each substack based on the computed positions."""
        try:
            # Group positions by substack
            substack1_positions = [pos for pos in positions if pos['file_path'] in substack1_files]
            substack2_positions = [pos for pos in positions if pos['file_path'] in substack2_files]
            substack3_positions = [pos for pos in positions if pos['file_path'] in substack3_files]
            
            # Calculate the average object position for each substack
            # This will show the object's motion across the three time periods
            # In a motion-tracked stack the object is shifted so that the pixel
            # position of the FIRST image becomes the reference for the whole
            # sub-stack.  Therefore using the average of the coordinates would
            # introduce a systematic offset ≈½ × (object motion within the
            # sub-stack).  We instead take the coordinates belonging to the
            # first file of each substack – they match the reference position
            # used by the stacking algorithm.
            def get_reference_position(file_list):
                """Return (x, y) of the first image in *file_list* that has a
                matching entry in *positions*.  None if not found."""
                for fp in file_list:
                    match = next((p for p in positions if p['file_path'] == fp), None)
                    if match is not None:
                        return (match['original_x'], match['original_y'])
                return None

            pos1 = get_reference_position(substack1_files)
            pos2 = get_reference_position(substack2_files)
            pos3 = get_reference_position(substack3_files)
            
            # Debug output
            print(f"Substack 1 positions: {len(substack1_positions)} files, avg object pos: {pos1}")
            print(f"Substack 2 positions: {len(substack2_positions)} files, avg object pos: {pos2}")
            print(f"Substack 3 positions: {len(substack3_positions)} files, avg object pos: {pos3}")
            
            return [pos1, pos2, pos3]
            
        except Exception as e:
            # Fallback to using the original cursor position for all substacks
            print(f"Warning: Could not calculate substack-specific positions: {e}")
            return [self.cursor_coords, self.cursor_coords, self.cursor_coords]
    
    def _sort_files_by_date(self, files):
        """Sort files by DATE-OBS header value."""
        file_dates = []
        
        for file_path in files:
            date_obs = None
            try:
                from astropy.io import fits
                with fits.open(file_path) as hdul:
                    header = hdul[0].header
                    date_obs = header.get('DATE-OBS')
            except Exception:
                pass
            
            # If not found in header, try database
            if not date_obs:
                try:
                    from lib.db.manager import get_db_manager
                    db_manager = get_db_manager()
                    db_entry = db_manager.get_fits_file_by_path(file_path)
                    if db_entry and db_entry.date_obs:
                        date_obs = db_entry.date_obs.isoformat(sep='T', timespec='seconds')
                except Exception:
                    pass
            
            # Use file modification time as fallback
            if not date_obs:
                date_obs = datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
            
            file_dates.append((file_path, date_obs))
        
        # Sort by date and return file paths
        file_dates.sort(key=lambda x: x[1])
        return [file_path for file_path, _ in file_dates]
    
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
        
        # Validate Gaia detection results structure
        for i, result in enumerate(gaia_detection_results):
            if not isinstance(result, tuple) or len(result) != 3:
                QMessageBox.warning(self, "Invalid Gaia Data", 
                                  f"Gaia detection result {i} has invalid structure: {result}")
                return
            gaia_obj, detected_source, distance_arcsec = result
            if not hasattr(gaia_obj, 'ra') or not hasattr(gaia_obj, 'dec') or not hasattr(gaia_obj, 'source_id'):
                QMessageBox.warning(self, "Invalid Gaia Data", 
                                  f"Gaia object {i} missing required attributes")
                return
            if not hasattr(detected_source, 'x') or not hasattr(detected_source, 'y'):
                QMessageBox.warning(self, "Invalid Gaia Data", 
                                  f"Detected source {i} missing required coordinates")
                return
        
        # Check if we have enough stars for LSPC (need at least 3)
        if len(gaia_detection_results) < 3:
            QMessageBox.warning(self, "Insufficient Stars", 
                              f"Only {len(gaia_detection_results)} matched stars found.\n\n"
                              "At least 3 comparison stars are required for LSPC calculation.")
            return
        
        # Validate that positions data is available and valid
        if not positions:
            QMessageBox.warning(self, "No Positions", 
                              "No position data available for LSPC calculation.")
            return
        
        # Check that positions have required fields
        for i, pos in enumerate(positions):
            if not isinstance(pos, dict):
                QMessageBox.warning(self, "Invalid Position Data", 
                                  f"Position {i} is not a valid dictionary.")
                return
            if 'original_x' not in pos or 'original_y' not in pos:
                QMessageBox.warning(self, "Invalid Position Data", 
                                  f"Position {i} missing required coordinates (original_x, original_y).")
                return
            
            # Check that coordinates are numeric
            if not isinstance(pos['original_x'], (int, float)) or not isinstance(pos['original_y'], (int, float)):
                QMessageBox.warning(self, "Invalid Position Data", 
                                  f"Position {i} has non-numeric coordinates: original_x={pos['original_x']}, original_y={pos['original_y']}")
                return
        
        # Compute LSPC
        try:
            print(f"[DEBUG] Computing LSPC with {len(gaia_detection_results)} Gaia stars and {len(positions)} positions")
            print(f"[DEBUG] First position sample: {positions[0] if positions else 'No positions'}")
            lspc_results = self._calculate_lspc(gaia_detection_results, positions)
            self._update_positions_table_with_lspc(lspc_results)
            
            # Enable the Generate Substacks button after LSPC is computed
            if hasattr(self, 'generate_substacks_button'):
                self.generate_substacks_button.setEnabled(True)
                
            # Store a backup of the original positions data if not already stored
            if not hasattr(self, '_original_positions_data'):
                self._original_positions_data = positions.copy()
                
        except Exception as e:
            QMessageBox.critical(self, "LSPC Error", f"Error computing LSPC: {str(e)}")
    
    def _calculate_lspc(self, gaia_detection_results, positions):
        """Calculate LSPC using matched Gaia stars."""
        
        # Extract comparison star data
        # gaia_detection_results is a list of (GaiaObject, DetectedSource, distance_arcsec) tuples
        comparison_stars = []
        for gaia_obj, detected_source, distance_arcsec in gaia_detection_results:
            # Validate that all required data is present and numeric
            if (gaia_obj.ra is None or gaia_obj.dec is None or 
                detected_source.x is None or detected_source.y is None):
                print(f"Warning: Skipping star with None coordinates: Gaia RA={gaia_obj.ra}, Dec={gaia_obj.dec}, X={detected_source.x}, Y={detected_source.y}")
                continue
                
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
        
        # Check if we have enough valid comparison stars after filtering
        if len(comparison_stars) < 3:
            raise ValueError(f"Only {len(comparison_stars)} valid comparison stars found after filtering. At least 3 are required for LSPC calculation.")
        
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
        
        # Apply LSPC to the computed positions (only for individual images, not stacked images)
        lspc_positions = []
        individual_positions = []
        print(f"[DEBUG] Applying LSPC transformation to {len(positions)} positions")
        
        # First pass: identify individual vs stacked images
        for i, pos in enumerate(positions):
            original_x = pos.get('original_x')
            original_y = pos.get('original_y')
            file_path = pos.get('file_path', '')
            
            print(f"[DEBUG] Position {i}: original_x={original_x}, original_y={original_y}, file={os.path.basename(file_path)}")
            
            # Skip positions with invalid coordinates
            if original_x is None or original_y is None:
                print(f"Warning: Skipping position with None coordinates: {pos}")
                continue
            
            # Check if this is a stacked image
            is_stacked = False
            if hasattr(self, 'parent_viewer') and self.parent_viewer:
                try:
                    from astropy.io import fits
                    with fits.open(file_path) as hdul:
                        header = hdul[0].header
                        # Check for motion tracking flag or other stacking indicators
                        if header.get('MOTION_TRACKED', False) or 'STACK' in file_path.upper():
                            is_stacked = True
                            print(f"[DEBUG] Skipping stacked image: {os.path.basename(file_path)}")
                except Exception as e:
                    print(f"[DEBUG] Could not check header for {file_path}: {e}")
                    # If we can't check the header, assume it's not stacked
            
            if is_stacked:
                print(f"[DEBUG] Skipping stacked image position {i}")
                continue
            
            # This is an individual image, collect it for LSPC
            individual_positions.append(pos)
        
        # Second pass: apply LSPC transformation to individual images only
        print(f"[DEBUG] Applying LSPC to {len(individual_positions)} individual images")
        for pos in individual_positions:
            original_x = pos.get('original_x')
            original_y = pos.get('original_y')
            
            # Apply LSPC transformation only to individual images
            lspc_ra = a * original_x + b * original_y + c
            lspc_dec = d * original_x + e * original_y + f
            
            print(f"[DEBUG] LSPC RA={lspc_ra}, LSPC Dec={lspc_dec}")
            
            lspc_positions.append({
                **pos,
                'lspc_ra': lspc_ra,
                'lspc_dec': lspc_dec
            })
        
        result = {
            'plate_constants': {'a': a, 'b': b, 'c': c, 'd': d, 'e': e, 'f': f},
            'rms_ra': ra_rms,
            'rms_dec': dec_rms,
            'comparison_stars': comparison_stars,
            'lspc_positions': lspc_positions
        }
        
        print(f"[DEBUG] LSPC calculation completed successfully")
        print(f"[DEBUG] Result keys: {list(result.keys())}")
        print(f"[DEBUG] Number of LSPC positions: {len(lspc_positions)}")
        
        return result
    
    def _update_positions_table_with_lspc(self, lspc_results):
        """Update the positions table with LSPC results."""
        print(f"[DEBUG] Updating positions table with LSPC results")
        print(f"[DEBUG] LSPC results type: {type(lspc_results)}")
        print(f"[DEBUG] LSPC results keys: {list(lspc_results.keys()) if isinstance(lspc_results, dict) else 'Not a dict'}")
        
        if not isinstance(lspc_results, dict):
            print(f"Error: LSPC results is not a dictionary: {lspc_results}")
            return
            
        # Update the table headers to include LSPC columns
        self.computed_positions_table.setColumnCount(12)
        self.computed_positions_table.setHorizontalHeaderLabels([
            "File", "Original X", "Original Y", "Stacked X", "Stacked Y", 
            "Shift X", "Shift Y", "WCS RA", "WCS Dec", "LSPC RA", "LSPC Dec", "Difference"
        ])
        
        # Update the table data with LSPC results
        lspc_positions = lspc_results.get('lspc_positions', [])
        if not lspc_positions:
            print("Warning: No LSPC positions found in results")
            return
        
        # Create a mapping from file_path to LSPC results for easy lookup
        lspc_lookup = {}
        for lspc_pos in lspc_positions:
            file_path = lspc_pos.get('file_path')
            if file_path:
                lspc_lookup[file_path] = lspc_pos
        
        # Use the original positions data for the table, but add LSPC columns
        if not hasattr(self, 'computed_positions_data') or not self.computed_positions_data:
            print("Error: No computed positions data available")
            return
            
        original_positions = self.computed_positions_data
        print(f"[DEBUG] Original positions data has {len(original_positions)} entries")
        self.computed_positions_table.setRowCount(len(original_positions))
        
        for i, pos in enumerate(original_positions):
            print(f"[DEBUG] Processing position {i}: {pos}")
            try:
                # File name (basename only)
                filename = os.path.basename(pos['file_path'])
                self.computed_positions_table.setItem(i, 0, QTableWidgetItem(filename))
                
                # Original coordinates
                original_x = pos.get('original_x')
                original_y = pos.get('original_y')
                if original_x is not None and original_y is not None:
                    self.computed_positions_table.setItem(i, 1, QTableWidgetItem(f"{original_x:.2f}"))
                    self.computed_positions_table.setItem(i, 2, QTableWidgetItem(f"{original_y:.2f}"))
                else:
                    self.computed_positions_table.setItem(i, 1, QTableWidgetItem("N/A"))
                    self.computed_positions_table.setItem(i, 2, QTableWidgetItem("N/A"))
                
                # Stacked coordinates
                stacked_x = pos.get('stacked_x')
                stacked_y = pos.get('stacked_y')
                if stacked_x is not None and stacked_y is not None:
                    self.computed_positions_table.setItem(i, 3, QTableWidgetItem(f"{stacked_x:.2f}"))
                    self.computed_positions_table.setItem(i, 4, QTableWidgetItem(f"{stacked_y:.2f}"))
                else:
                    self.computed_positions_table.setItem(i, 3, QTableWidgetItem("N/A"))
                    self.computed_positions_table.setItem(i, 4, QTableWidgetItem("N/A"))
                
                # Shifts
                shift_x = pos.get('shift_x')
                shift_y = pos.get('shift_y')
                if shift_x is not None and shift_y is not None:
                    self.computed_positions_table.setItem(i, 5, QTableWidgetItem(f"{shift_x:.2f}"))
                    self.computed_positions_table.setItem(i, 6, QTableWidgetItem(f"{shift_y:.2f}"))
                else:
                    self.computed_positions_table.setItem(i, 5, QTableWidgetItem("N/A"))
                    self.computed_positions_table.setItem(i, 6, QTableWidgetItem("N/A"))
                
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
                file_path = pos.get('file_path')
                lspc_pos = lspc_lookup.get(file_path) if file_path else None
                
                # Check if this is a stacked image
                is_stacked = False
                if hasattr(self, 'parent_viewer') and self.parent_viewer:
                    try:
                        from astropy.io import fits
                        with fits.open(file_path) as hdul:
                            header = hdul[0].header
                            if header.get('MOTION_TRACKED', False) or 'STACK' in file_path.upper():
                                is_stacked = True
                    except Exception:
                        pass
                
                if lspc_pos and not is_stacked:
                    lspc_ra = lspc_pos.get('lspc_ra')
                    lspc_dec = lspc_pos.get('lspc_dec')
                    
                    if lspc_ra is not None and lspc_dec is not None:
                        self.computed_positions_table.setItem(i, 9, QTableWidgetItem(f"{lspc_ra:.6f}"))
                        self.computed_positions_table.setItem(i, 10, QTableWidgetItem(f"{lspc_dec:.6f}"))
                        
                        # Calculate and display difference
                        if wcs_ra != 'N/A' and wcs_dec != 'N/A':
                            ra_diff = (lspc_ra - wcs_ra) * 3600  # Convert to arcseconds
                            dec_diff = (lspc_dec - wcs_dec) * 3600
                            distance = np.sqrt(ra_diff**2 + dec_diff**2)
                            diff_text = f"{distance:.2f}\""
                        else:
                            diff_text = "N/A"
                    else:
                        self.computed_positions_table.setItem(i, 9, QTableWidgetItem("N/A"))
                        self.computed_positions_table.setItem(i, 10, QTableWidgetItem("N/A"))
                        diff_text = "N/A"
                else:
                    # No LSPC data available (either no LSPC results or stacked image)
                    if is_stacked:
                        self.computed_positions_table.setItem(i, 9, QTableWidgetItem("Stacked"))
                        self.computed_positions_table.setItem(i, 10, QTableWidgetItem("Stacked"))
                        diff_text = "N/A"
                    else:
                        self.computed_positions_table.setItem(i, 9, QTableWidgetItem("N/A"))
                        self.computed_positions_table.setItem(i, 10, QTableWidgetItem("N/A"))
                        diff_text = "N/A"
                
                self.computed_positions_table.setItem(i, 11, QTableWidgetItem(diff_text))
                
            except Exception as e:
                print(f"[DEBUG] Error processing position {i}: {e}")
                # Set all cells to error state
                for col in range(12):
                    self.computed_positions_table.setItem(i, col, QTableWidgetItem("ERROR"))
                continue
        
        # Resize columns to fit content
        self.computed_positions_table.resizeColumnsToContents()
        
        # Store the LSPC results separately, but keep the original position data for markers
        self.lspc_results = lspc_results
        # Note: We don't overwrite self.computed_positions_data here to preserve marker functionality
        
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
        constants = lspc_results.get('plate_constants', {})
        if constants:
            a = constants.get('a')
            b = constants.get('b')
            c = constants.get('c')
            d = constants.get('d')
            e = constants.get('e')
            f = constants.get('f')
            
            if all(v is not None for v in [a, b, c, d, e, f]):
                solution_text += f"a = {a:12.8f}  (RA = a*x + b*y + c)\n"
                solution_text += f"b = {b:12.8f}  (Dec = d*x + e*y + f)\n"
                solution_text += f"c = {c:12.8f}\n"
                solution_text += f"d = {d:12.8f}\n"
                solution_text += f"e = {e:12.8f}\n"
                solution_text += f"f = {f:12.8f}\n\n"
            else:
                solution_text += "Plate constants: N/A\n\n"
        else:
            solution_text += "Plate constants: N/A\n\n"
        
        # RMS residuals
        solution_text += "RMS RESIDUALS:\n"
        solution_text += "-" * 15 + "\n"
        rms_ra = lspc_results.get('rms_ra')
        rms_dec = lspc_results.get('rms_dec')
        
        if rms_ra is not None and rms_dec is not None:
            solution_text += f"RA  RMS: {rms_ra:10.6f} degrees\n"
            solution_text += f"Dec RMS: {rms_dec:10.6f} degrees\n"
            solution_text += f"RA  RMS: {rms_ra*3600:10.2f} arcseconds\n"
            solution_text += f"Dec RMS: {rms_dec*3600:10.2f} arcseconds\n\n"
        else:
            solution_text += "RA  RMS: N/A degrees\n"
            solution_text += "Dec RMS: N/A degrees\n"
            solution_text += "RA  RMS: N/A arcseconds\n"
            solution_text += "Dec RMS: N/A arcseconds\n\n"
        
        # Comparison stars info
        solution_text += "COMPARISON STARS:\n"
        solution_text += "-" * 18 + "\n"
        comparison_stars = lspc_results.get('comparison_stars', [])
        solution_text += f"Number of stars: {len(comparison_stars)}\n\n"
        
        # Show individual star residuals
        solution_text += "STAR RESIDUALS:\n"
        solution_text += "-" * 16 + "\n"
        solution_text += "Gaia ID          RA Residual    Dec Residual   Total\n"
        solution_text += "                 (arcsec)       (arcsec)       (arcsec)\n"
        solution_text += "-" * 60 + "\n"
        
        # Calculate and display residuals for each comparison star
        comparison_stars = lspc_results.get('comparison_stars', [])
        if comparison_stars and constants:
            a = constants.get('a')
            b = constants.get('b')
            c = constants.get('c')
            d = constants.get('d')
            e = constants.get('e')
            f = constants.get('f')
            
            if all(v is not None for v in [a, b, c, d, e, f]):
                for i, star in enumerate(comparison_stars):
                    # Apply LSPC transformation to measured coordinates
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
            else:
                solution_text += "Cannot calculate residuals: plate constants are missing\n"
        else:
            solution_text += "No comparison stars available for residual calculation\n"
        
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
                
                # Add LSPC data if available
                if hasattr(self, 'lspc_results') and self.lspc_results:
                    file_path = position_data.get('file_path')
                    if file_path:
                        lspc_positions = self.lspc_results.get('lspc_positions', [])
                        for lspc_pos in lspc_positions:
                            if lspc_pos.get('file_path') == file_path:
                                # Merge LSPC data with original position data
                                position_data = {**position_data, **lspc_pos}
                                break
                
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

    # ---------------- Measurement functions ----------------
    def _measure_object_positions(self):
        """
        Compute RA/Dec for each measurement marker found in motion-tracked
        stacked images (yellow markers) and show the results in a new
        'Measurements' tab.
        """
        if not hasattr(self, 'parent_viewer') or not self.parent_viewer:
            QMessageBox.warning(self, "Error", "No parent viewer available.")
            return

        loaded_files = getattr(self.parent_viewer, 'loaded_files', [])
        if not loaded_files:
            QMessageBox.warning(self, "No Files", "No files loaded in the viewer.")
            return

        import numpy as np
        from astropy.io import fits
        from astropy.time import Time
        from lib.fits.integration import compute_object_positions_from_motion_tracked

        measurements = []

        for file_path in loaded_files:
            try:
                with fits.open(file_path) as hdul:
                    header = hdul[0].header
                    meas_json = header.get('MEAS_POS')
                    if not meas_json:
                        continue
                    x, y = json.loads(meas_json)
                    substack_date = header.get('DATE-OBS')
            except Exception:
                continue

            # Compute positions back to original images
            try:
                positions = compute_object_positions_from_motion_tracked(
                    file_path, (x, y)
                )
            except Exception as exc:
                print(f"Warning: could not compute object positions for {file_path}: {exc}")
                continue

            # Gather RA/Dec with times from original images
            times_mjd, ras_deg, decs_deg = [], [], []
            for pos in positions:
                ra_deg = pos.get('ra')
                dec_deg = pos.get('dec')
                if ra_deg is None or dec_deg is None:
                    continue
                orig_path = pos['file_path']
                try:
                    with fits.open(orig_path) as hdul_o:
                        date_obs_orig = hdul_o[0].header.get('DATE-OBS')
                    if not date_obs_orig:
                        continue
                    t = Time(date_obs_orig, format='isot', scale='utc')
                except Exception:
                    continue
                times_mjd.append(t.mjd)
                ras_deg.append(ra_deg)
                decs_deg.append(dec_deg)

            if not times_mjd:
                continue

            # Determine target time (substack DATE-OBS); fall back to mean
            import numpy as np
            if substack_date:
                try:
                    target_time = Time(substack_date, format='isot', scale='utc').mjd
                except Exception:
                    target_time = np.mean(times_mjd)
            else:
                target_time = np.mean(times_mjd)

            # Interpolate RA/Dec to target time
            if len(times_mjd) == 1:
                ra_interp = ras_deg[0]
                dec_interp = decs_deg[0]
            else:
                # Handle RA wrap-around by working in radians and unwrapping
                ra_rad = np.deg2rad(ras_deg)
                ra_rad_unwrapped = np.unwrap(ra_rad)
                ra_interp_rad = np.interp(target_time, times_mjd, ra_rad_unwrapped)
                ra_interp = np.rad2deg(ra_interp_rad)
                dec_interp = np.interp(target_time, times_mjd, decs_deg)

            # Format RA/Dec
            ra_hms = Angle(ra_interp, unit=u.deg).to_string(unit='hourangle',
                                                            sep=':', precision=2, pad=True)
            dec_dms = Angle(dec_interp, unit=u.deg).to_string(unit='deg',
                                                              sep=':', precision=1, pad=True,
                                                              alwayssign=True)
            if not substack_date:
                substack_date = Time(target_time, format='mjd').isot

            measurements.append({
                'file_path': file_path,
                'date_obs': substack_date,
                'ra_deg': ra_interp,
                'dec_deg': dec_interp,
                'ra_hms': ra_hms,
                'dec_dms': dec_dms
            })

        if not measurements:
            QMessageBox.warning(self, "No Measurements",
                                "No measurement markers found or RA/Dec could not be computed.")
            return

        self._show_measurements_tab(measurements)

    def _show_measurements_tab(self, measurements):
        """Create or update the 'Measurements' tab with the provided data."""
        # Check if a Measurements tab already exists
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Measurements":
                # Remove it – easier than updating in-place
                self.tab_widget.removeTab(i)
                break

        # Create new tab
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        self.measurements_table = QTableWidget()
        tbl = self.measurements_table
        tbl.setColumnCount(6)
        tbl.setHorizontalHeaderLabels([
            "File", "Date/Time", "RA (deg)", "Dec (deg)", "RA (h:m:s)", "Dec (d:m:s)"
        ])
        tbl.setFont(QFont("Courier New", 9))
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tbl.setRowCount(len(measurements))

        for row, m in enumerate(measurements):
            tbl.setItem(row, 0, QTableWidgetItem(os.path.basename(m['file_path'])))
            tbl.setItem(row, 1, QTableWidgetItem(str(m['date_obs'])))
            tbl.setItem(row, 2, QTableWidgetItem(f"{m['ra_deg']:.6f}"))
            tbl.setItem(row, 3, QTableWidgetItem(f"{m['dec_deg']:.6f}"))
            tbl.setItem(row, 4, QTableWidgetItem(m['ra_hms']))
            tbl.setItem(row, 5, QTableWidgetItem(m['dec_dms']))

        tbl.resizeColumnsToContents()
        layout.addWidget(tbl)

        # Store data for later row selection
        self.measurements_data = measurements
        # Connect selection change handler
        tbl.selectionModel().selectionChanged.connect(self._on_measurements_selection_changed)

        self.tab_widget.addTab(widget, "Measurements")
        self.tab_widget.setCurrentWidget(widget)

    def _on_measurements_selection_changed(self, selected, deselected):
        """Handle selection changes in the measurements table and load the chosen substack."""
        if not hasattr(self, 'measurements_table') or not hasattr(self, 'measurements_data'):
            return
        selected_rows = self.measurements_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        if not (0 <= row < len(self.measurements_data)):
            return
        entry = self.measurements_data[row]
        file_path = entry.get('file_path')
        if not file_path or not hasattr(self, 'parent_viewer') or not self.parent_viewer:
            return
        # If the file is already loaded list, switch to it, otherwise load directly
        try:
            loaded_files = getattr(self.parent_viewer, 'loaded_files', [])
            if file_path in loaded_files:
                idx = loaded_files.index(file_path)
                self.parent_viewer.current_file_index = idx
            self.parent_viewer.load_fits(file_path, restore_view=True)
            if hasattr(self.parent_viewer, 'update_navigation_buttons'):
                self.parent_viewer.update_navigation_buttons()
        except Exception as exc:
            print(f"Warning: could not load {file_path}: {exc}")

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

class SubstacksGenerationWorker(QObject):
    """Worker thread for generating motion tracked substacks."""
    console_output = pyqtSignal(str)  # console output text
    finished = pyqtSignal(bool, str, list)  # success, message, output_files
    
    def __init__(self, substack1_files, substack2_files, substack3_files, 
                 object_name, output_dir, safe_object_name, timestamp, console_window=None,
                 object_positions=None):
        super().__init__()
        self.substack1_files = substack1_files
        self.substack2_files = substack2_files
        self.substack3_files = substack3_files
        self.object_name = object_name
        self.output_dir = output_dir
        self.safe_object_name = safe_object_name
        self.timestamp = timestamp
        self.console_window = console_window
        self.object_positions = object_positions  # List of (x, y) coordinates for each substack
    
    def run(self):
        """Run the substack generation."""
        try:
            from lib.gui.common.console_window import RealTimeStringIO
            import sys
            
            # Redirect stdout/stderr to console output
            rtio = RealTimeStringIO(self.console_output.emit)
            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = rtio
            
            try:
                self.console_output.emit(f"\033[1;34mStarting substack generation for {self.object_name}\033[0m\n")
                self.console_output.emit(f"\033[1;34mTotal individual files: {len(self.substack1_files) + len(self.substack2_files) + len(self.substack3_files)}\033[0m\n")
                self.console_output.emit(f"\033[1;34mStacking method: Median\033[0m\n")
                self.console_output.emit(f"\033[1;34mNote: Only individual images are used (stacked images are excluded)\033[0m\n")
                if self.object_positions:
                    # Handle both string and numeric coordinates
                    for i, (x, y) in enumerate(self.object_positions):
                        self.console_output.emit(f"\033[1;34mObject position for substack {i+1}: ({x:.1f}, {y:.1f})\033[0m\n")
                self.console_output.emit(f"\n")
                
                output_files = []
                
                # Generate substack 1
                self.console_output.emit(f"\033[1;33m=== SUBSTACK 1 ===\033[0m\n")
                self.console_output.emit(f"Files ({len(self.substack1_files)}):\n")
                for i, file_path in enumerate(self.substack1_files, 1):
                    filename = os.path.basename(file_path)
                    self.console_output.emit(f"  {i:2d}. {filename}\n")
                self.console_output.emit(f"\n")
                
                output_file1 = os.path.join(self.output_dir, f"substack1_{self.safe_object_name}_{self.timestamp}.fits")
                self.console_output.emit(f"\033[1;33mCreating substack 1 (median)...\033[0m\n")
                
                result1 = self._create_motion_tracked_stack(self.substack1_files, self.object_name, output_file1)
                output_files.append(output_file1)
                
                self.console_output.emit(f"\033[1;32m✓ Substack 1 completed: {os.path.basename(output_file1)}\033[0m\n")
                
                # Add measurement marker to substack 1
                self._add_measurement_marker(output_file1, self.object_positions[0] if self.object_positions else None)
                
                self.console_output.emit(f"\n")
                
                # Generate substack 2
                self.console_output.emit(f"\033[1;33m=== SUBSTACK 2 ===\033[0m\n")
                self.console_output.emit(f"Files ({len(self.substack2_files)}):\n")
                for i, file_path in enumerate(self.substack2_files, 1):
                    filename = os.path.basename(file_path)
                    self.console_output.emit(f"  {i:2d}. {filename}\n")
                self.console_output.emit(f"\n")
                
                output_file2 = os.path.join(self.output_dir, f"substack2_{self.safe_object_name}_{self.timestamp}.fits")
                self.console_output.emit(f"\033[1;33mCreating substack 2 (median)...\033[0m\n")
                
                result2 = self._create_motion_tracked_stack(self.substack2_files, self.object_name, output_file2)
                output_files.append(output_file2)
                
                self.console_output.emit(f"\033[1;32m✓ Substack 2 completed: {os.path.basename(output_file2)}\033[0m\n")
                
                # Add measurement marker to substack 2
                self._add_measurement_marker(output_file2, self.object_positions[1] if self.object_positions else None)
                
                self.console_output.emit(f"\n")
                
                # Generate substack 3
                self.console_output.emit(f"\033[1;33m=== SUBSTACK 3 ===\033[0m\n")
                self.console_output.emit(f"Files ({len(self.substack3_files)}):\n")
                for i, file_path in enumerate(self.substack3_files, 1):
                    filename = os.path.basename(file_path)
                    self.console_output.emit(f"  {i:2d}. {filename}\n")
                self.console_output.emit(f"\n")
                
                output_file3 = os.path.join(self.output_dir, f"substack3_{self.safe_object_name}_{self.timestamp}.fits")
                self.console_output.emit(f"\033[1;33mCreating substack 3 (median)...\033[0m\n")
                
                result3 = self._create_motion_tracked_stack(self.substack3_files, self.object_name, output_file3)
                output_files.append(output_file3)
                
                self.console_output.emit(f"\033[1;32m✓ Substack 3 completed: {os.path.basename(output_file3)}\033[0m\n")
                
                # Add measurement marker to substack 3
                self._add_measurement_marker(output_file3, self.object_positions[2] if self.object_positions else None)
                
                self.console_output.emit(f"\n")
                
                # Success message
                message = f"Successfully generated 3 motion-tracked substacks\n"
                message += f"Object: {self.object_name}\n"
                message += f"Method: Median stacking\n"
                message += f"  – Substack 1: {len(self.substack1_files)} files → {os.path.basename(output_file1)}\n"
                message += f"  – Substack 2: {len(self.substack2_files)} files → {os.path.basename(output_file2)}\n"
                message += f"  – Substack 3: {len(self.substack3_files)} files → {os.path.basename(output_file3)}\n"
                message += f"Output directory: {self.output_dir}"
                
                self.finished.emit(True, message, output_files)
                
            finally:
                # Restore stdout/stderr
                sys.stdout = old_stdout
                sys.stderr = old_stderr
            
        except Exception as e:
            import traceback
            error_msg = f"Unexpected error during substack generation:\n{str(e)}\n\n{traceback.format_exc()}"
            self.finished.emit(False, error_msg, [])
    
    def _create_motion_tracked_stack(self, files, object_name, output_path):
        """Create a motion tracked stack from the given files."""
        try:
            from lib.fits.integration import integrate_with_motion_tracking
            
            # Use median stacking for substacks (override config default)
            from config import MOTION_TRACKING_SIGMA_CLIP
            
            result = integrate_with_motion_tracking(
                files=files,
                object_name=object_name,
                method='median',  # Force median stacking for substacks
                sigma_clip=MOTION_TRACKING_SIGMA_CLIP,
                output_path=output_path
            )
            
            return result
            
        except Exception as e:
            raise Exception(f"Error creating motion tracked stack: {str(e)}")
    
    def _add_measurement_marker(self, fits_path, object_position):
        """
        Store the expected object position (pixel coordinates) in the FITS
        header so that the viewer can show a yellow measurement marker.
        """
        if object_position is None:
            return
        try:
            from astropy.io import fits
            import json
            x, y = self._parse_coordinates(object_position)
            with fits.open(fits_path, mode='update') as hdul:
                hdul[0].header['MEAS_POS'] = json.dumps([float(x), float(y)])
                hdul.flush()
        except Exception as exc:
            print(f"Warning: could not write MEAS_POS to {fits_path}: {exc}")

    def _create_cropped_version(self, stacked_result, output_path, object_position):
        """Create a cropped version of the stacked image centered on the object position."""
        try:
            import numpy as np
            from astropy.io import fits
            import re
            
            # Get the stacked data
            stacked_data = stacked_result.data
            header = stacked_result.meta
            
            # Calculate crop boundaries (500x500 pixels centered on object)
            crop_size = 500
            
            # Parse coordinates - handle various formats
            center_x, center_y = self._parse_coordinates(object_position)
            
            # Calculate crop boundaries
            start_x = max(0, int(center_x - crop_size // 2))
            end_x = min(stacked_data.shape[1], start_x + crop_size)
            start_y = max(0, int(center_y - crop_size // 2))
            end_y = min(stacked_data.shape[0], start_y + crop_size)
            
            # Adjust if we're near the edges
            if end_x - start_x < crop_size:
                if start_x == 0:
                    end_x = min(stacked_data.shape[1], crop_size)
                else:
                    start_x = max(0, stacked_data.shape[1] - crop_size)
            
            if end_y - start_y < crop_size:
                if start_y == 0:
                    end_y = min(stacked_data.shape[0], crop_size)
                else:
                    start_y = max(0, stacked_data.shape[0] - crop_size)
            
            # Crop the data
            cropped_data = stacked_data[start_y:end_y, start_x:end_x]
            
            # Create new header for cropped image
            cropped_header = header.copy()
            
            # Update header with crop information
            cropped_header['NAXIS1'] = cropped_data.shape[1]
            cropped_header['NAXIS2'] = cropped_data.shape[0]
            cropped_header['CROPPED'] = True
            cropped_header['CROP_X1'] = start_x
            cropped_header['CROP_Y1'] = start_y
            cropped_header['CROP_X2'] = end_x
            cropped_header['CROP_Y2'] = end_y
            cropped_header['CROP_CENTER_X'] = center_x
            cropped_header['CROP_CENTER_Y'] = center_y
            cropped_header['CROP_SIZE'] = crop_size
            
            # Update WCS if present
            if 'WCSAXES' in cropped_header:
                try:
                    from astropy.wcs import WCS
                    wcs = WCS(cropped_header)
                    # Update WCS for the cropped region
                    wcs_cropped = wcs.slice((slice(start_y, end_y), slice(start_x, end_x)))
                    # Update header with new WCS
                    for key in wcs_cropped.to_header():
                        cropped_header[key] = wcs_cropped.to_header()[key]
                except Exception as e:
                    self.console_output.emit(f"Warning: Could not update WCS for cropped image: {e}\n")
            
            # Save cropped image
            hdu = fits.PrimaryHDU(cropped_data, cropped_header)
            hdu.writeto(output_path, overwrite=True)
            
            self.console_output.emit(f"  Cropped from ({start_x}, {start_y}) to ({end_x}, {end_y})\n")
            self.console_output.emit(f"  Final crop size: {cropped_data.shape[1]}x{cropped_data.shape[0]} pixels\n")
            
        except Exception as e:
            raise Exception(f"Error creating cropped version: {str(e)}")
    
    def _parse_coordinates(self, object_position):
        """Parse coordinates from various formats and return (x, y) as floats."""
        try:
            # If it's already a tuple or list with two elements
            if isinstance(object_position, (tuple, list)) and len(object_position) == 2:
                return float(object_position[0]), float(object_position[1])
            
            # If it's a string representation of a tuple like "(1158.9, 863.2)"
            if isinstance(object_position, str):
                # Use regex to extract numbers from the string
                import re
                numbers = re.findall(r'[-+]?\d*\.?\d+', object_position)
                if len(numbers) >= 2:
                    return float(numbers[0]), float(numbers[1])
            
            # If it's a single string with comma separation
            if isinstance(object_position, str) and ',' in object_position:
                parts = object_position.split(',')
                if len(parts) >= 2:
                    return float(parts[0].strip()), float(parts[1].strip())
            
            raise ValueError(f"Could not parse coordinates from: {object_position}")
            
        except (ValueError, TypeError) as e:
            raise Exception(f"Invalid object position coordinates: {object_position}. Expected numeric values. Error: {str(e)}")


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