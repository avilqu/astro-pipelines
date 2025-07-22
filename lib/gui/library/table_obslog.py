"""
Table widget for displaying FITS files grouped by runs.
"""

import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QItemSelectionModel
from PyQt6.QtGui import QFont, QPalette, QColor
from .menu_context import build_single_file_menu, build_multi_file_menu, build_empty_menu
import json
from astropy.io import fits
from lib.gui.common.header_viewer import HeaderViewer
from lib.fits.header import get_fits_header_as_json


class RunSummaryWidget(QWidget):
    """Custom widget for displaying run summary information."""
    
    def __init__(self, run_data, parent=None):
        super().__init__(parent)
        self.run_data = run_data
        self.is_expanded = False
        self.init_ui()
    
    def init_ui(self):
        """Initialize the run summary display."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Create expand/collapse indicator
        self.indicator_label = QLabel("▶")  # Triangle pointing right (collapsed)
        self.indicator_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.indicator_label.setStyleSheet("color: #2c3e50; margin-right: 8px;")
        layout.addWidget(self.indicator_label)
        
        # Create summary text
        summary_text = self._build_summary_text()
        
        # Create label with custom styling
        label = QLabel(summary_text)
        label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        
        layout.addWidget(label)
        layout.addStretch()
    
    def set_expanded(self, expanded):
        """Update the visual indicator based on expansion state."""
        self.is_expanded = expanded
        if expanded:
            self.indicator_label.setText("▼")  # Triangle pointing down (expanded)
        else:
            self.indicator_label.setText("▶")  # Triangle pointing right (collapsed)
    
    def _build_summary_text(self):
        """Build the summary text for the run."""
        date_str = self.run_data['date_str']
        target = self.run_data['target']
        count = self.run_data['count']
        filters = self.run_data['filters']
        exposures = self.run_data['exposures']
        total_minutes = self.run_data['total_minutes']
        binning = self.run_data['binning']
        
        # Format filters
        filter_str = ", ".join(sorted(set(filters))) if filters else "-"
        
        # Format exposures
        exposure_str = ", ".join([f"{exp:.1f}s" for exp in sorted(set(exposures))]) if exposures else "-"
        
        return f"{date_str} / {target} / {count} files / {binning} / {filter_str} / {exposure_str} / Total: {total_minutes}mn"


class FitsTableWidget(QTableWidget):
    """Table widget for displaying FITS files grouped by runs."""
    
    # Custom signals
    selection_changed = pyqtSignal(list)  # Emits list of selected fits_file_ids
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fits_files = []
        self.run_groups = []
        self.expanded_runs = set()  # Track which runs are expanded
        self.init_table()
    
    def init_table(self):
        """Initialize the table structure."""
        self.setColumnCount(17)
        self.setHorizontalHeaderLabels([
            "Filename", "Date obs", "Target", "Filter", "Exposure", "Bin", "Gain", "Offset", "CCD temp", "Focus", "HFR", "Sources", "Size", "Image Scale", "RA Center", "DEC Center", "WCS Type"
        ])
        
        # Hide row numbers (vertical header)
        self.verticalHeader().setVisible(False)
        
        # Set selection mode to select individual cells
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        # Enable custom context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        # Disable sorting - order is fixed by date_obs
        self.setSortingEnabled(False)
        
        # Set table styling
        self.setShowGrid(True)
        self.setGridStyle(Qt.PenStyle.SolidLine)
        
        # Set column widths - all columns are manually resizable
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Filename
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Date obs (new column)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Target
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Filter
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)  # Exposure
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)  # Bin
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)  # Gain
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)  # Offset
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Interactive)  # CCD temp
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Interactive)  # Focus
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Interactive)  # HFR
        header.setSectionResizeMode(11, QHeaderView.ResizeMode.Interactive)  # Sources
        header.setSectionResizeMode(12, QHeaderView.ResizeMode.Interactive)  # Size
        header.setSectionResizeMode(13, QHeaderView.ResizeMode.Interactive)  # Image Scale
        header.setSectionResizeMode(14, QHeaderView.ResizeMode.Interactive)  # RA Center
        header.setSectionResizeMode(15, QHeaderView.ResizeMode.Interactive)  # DEC Center
        header.setSectionResizeMode(16, QHeaderView.ResizeMode.Interactive)  # WCS Type
        
        # Set default column widths
        self.setColumnWidth(0, 200)   # Filename
        self.setColumnWidth(1, 120)   # Date obs (new column)
        self.setColumnWidth(2, 100)   # Target
        self.setColumnWidth(3, 80)    # Filter
        self.setColumnWidth(4, 80)    # Exposure
        self.setColumnWidth(5, 60)    # Bin
        self.setColumnWidth(6, 60)    # Gain
        self.setColumnWidth(7, 60)    # Offset
        self.setColumnWidth(8, 80)    # CCD temp
        self.setColumnWidth(9, 100)   # Focus
        self.setColumnWidth(10, 60)   # HFR
        self.setColumnWidth(11, 60)   # Sources
        self.setColumnWidth(12, 80)   # Size
        self.setColumnWidth(13, 80)   # Image Scale
        self.setColumnWidth(14, 100)  # RA Center
        self.setColumnWidth(15, 100)  # DEC Center
        self.setColumnWidth(16, 80)   # WCS Type
        
        # Connect selection change and cell click
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.cellClicked.connect(self._on_cell_clicked)
    
    def _group_files_by_runs(self, fits_files):
        """Group FITS files by runs based on target and time proximity."""
        if not fits_files:
            return []
        
        # Sort files by date_obs (most recent first)
        sorted_files = sorted(fits_files, key=lambda x: x.date_obs or datetime.min, reverse=True)
        
        runs = []
        current_run = []
        
        for file in sorted_files:
            if not current_run:
                current_run = [file]
            else:
                # Check if this file belongs to the same run
                last_file = current_run[-1]
                
                # Same target and within 30 minutes of the last file
                same_target = file.target == last_file.target
                time_diff = abs((file.date_obs - last_file.date_obs).total_seconds() / 60) if file.date_obs and last_file.date_obs else float('inf')
                within_time_window = time_diff <= 30  # 30 minutes threshold
                
                if same_target and within_time_window:
                    current_run.append(file)
                else:
                    # End current run and start new one
                    if current_run:
                        runs.append(current_run)
                    current_run = [file]
        
        # Add the last run
        if current_run:
            runs.append(current_run)
        
        return runs
    
    def _create_run_summary_data(self, run_files):
        """Create summary data for a run."""
        count = len(run_files)
        target = run_files[0].target if run_files else "Unknown"
        filters = [f.filter_name for f in run_files if f.filter_name]
        exposures = [f.exptime for f in run_files if f.exptime]
        total_seconds = sum(exposures) if exposures else 0
        total_minutes = round(total_seconds / 60)
        binning = run_files[0].binning if run_files and hasattr(run_files[0], 'binning') else "-"
        date_str = run_files[0].date_obs.strftime("%Y-%m-%d") if run_files and hasattr(run_files[0], 'date_obs') and run_files[0].date_obs else "-"
        
        return {
            'count': count,
            'target': target,
            'filters': filters,
            'exposures': exposures,
            'total_minutes': total_minutes,
            'binning': binning,
            'date_str': date_str,
            'files': run_files
        }
    
    def populate_table(self, fits_files):
        """Populate the table with FITS files grouped by runs."""
        self.fits_files = fits_files
        self.expanded_runs.clear()
        
        # Group files by runs
        self.run_groups = self._group_files_by_runs(fits_files)
        
        # Calculate total rows needed (one row per run, plus expanded files)
        total_rows = len(self.run_groups)
        self.setRowCount(total_rows)
        
        # Set row height for run summary rows
        self.verticalHeader().setDefaultSectionSize(60)  # Double height
        
        # Populate each run as a summary row
        for row, run_files in enumerate(self.run_groups):
            self._add_run_summary_row(row, run_files)
        self._apply_striping()
        
        # Collapse all runs by default, expand only the most recent (first) run
        if self.run_groups:
            self._expand_run(0)

    def _add_run_summary_row(self, row, run_files):
        """Add a run summary row to the table."""
        # Set double row height for run summary rows
        self.verticalHeader().setSectionResizeMode(row, QHeaderView.ResizeMode.Fixed)
        self.setRowHeight(row, 60)  # Double height
        
        # Create run summary data
        run_data = self._create_run_summary_data(run_files)
        
        # Create custom widget for the summary
        summary_widget = RunSummaryWidget(run_data)
        
        # Set the widget to span all columns
        self.setCellWidget(row, 0, summary_widget)
        self.setSpan(row, 0, 1, self.columnCount())  # Span across all columns
        
        # Set the entire row background color and remove cell separations
        self._set_run_row_style(row)
        
        # Store the run data for selection handling
        if run_files:
            # Create a hidden item to store the run data
            hidden_item = QTableWidgetItem()
            hidden_item.setData(Qt.ItemDataRole.UserRole, {
                'run_files': run_files,
                'run_data': run_data,
                'is_run_summary': True,
                'run_index': row
            })
            self.setItem(row, 0, hidden_item)
    
    def _set_run_row_style(self, row):
        """Set the visual style for a run summary row."""
        # Set background color for the entire row and make cells non-editable and non-selectable
        for col in range(self.columnCount()):
            item = QTableWidgetItem()
            item.setBackground(QColor(236, 240, 241))  # Light gray background
            # Make it non-editable and non-selectable
            item.setFlags(Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsSelectable)
            # Remove borders by setting transparent border
            item.setData(Qt.ItemDataRole.UserRole, {'is_run_cell': True})
            self.setItem(row, col, item)
    
    def _add_file_rows(self, run_index, run_files):
        """Add individual file rows for an expanded run, with striping."""
        insert_row = run_index + 1
        for i, file in enumerate(run_files):
            self.insertRow(insert_row + i)
            self._add_file_row(insert_row + i, file, run_index)
        self._apply_striping()
        # Update run indices for subsequent runs
        for row in range(insert_row + len(run_files), self.rowCount()):
            item = self.item(row, 0)
            if item:
                run_data = item.data(Qt.ItemDataRole.UserRole)
                if run_data and 'is_run_summary' in run_data:
                    run_data['run_index'] = row

    def _apply_striping(self):
        """Apply a striped effect to file rows, skipping run summary rows, with dark mode support."""
        palette = self.palette()
        base_color = palette.color(self.backgroundRole())
        is_dark = base_color.value() < 128 if hasattr(base_color, 'value') else False
        # Use dark-friendly colors if in dark mode
        color1 = QColor(40, 40, 40) if is_dark else QColor(255, 255, 255)
        color2 = QColor(55, 55, 55) if is_dark else QColor(245, 245, 245)
        file_row_index = 0
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data and 'is_file' in data:
                    color = color2 if file_row_index % 2 == 1 else color1
                    for col in range(self.columnCount()):
                        cell = self.item(row, col)
                        if cell:
                            cell.setBackground(color)
                            # Only set foreground if not already colored (i.e., default brush), and skip filter column (2)
                            if is_dark and (col != 2 or cell.foreground().color() == QColor()):
                                cell.setForeground(QColor(230, 230, 230))
                    file_row_index += 1
    
    def _add_file_row(self, row, fits_file, parent_run_index):
        """Add a single file row."""
        # Set normal row height for file rows
        self.verticalHeader().setSectionResizeMode(row, QHeaderView.ResizeMode.Fixed)
        self.setRowHeight(row, 30)  # Normal height
        
        # Filename (extract from path)
        filename = os.path.basename(fits_file.path)
        filename_item = QTableWidgetItem(filename)
        filename_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        filename_item.setToolTip(fits_file.path)
        # Store file data in the filename item
        filename_item.setData(Qt.ItemDataRole.UserRole, {
            'fits_file': fits_file,
            'is_file': True,
            'parent_run_index': parent_run_index
        })
        self.setItem(row, 0, filename_item)
        
        # Date obs (new column)
        if hasattr(fits_file, 'date_obs') and fits_file.date_obs:
            if isinstance(fits_file.date_obs, str):
                date_obs_str = fits_file.date_obs
            else:
                date_obs_str = fits_file.date_obs.strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_obs_str = "-"
        date_obs_item = QTableWidgetItem(date_obs_str)
        date_obs_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 1, date_obs_item)
        
        # Target
        target = fits_file.target or "-"
        target_item = QTableWidgetItem(target)
        target_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 2, target_item)
        
        # Filter
        filter_name = fits_file.filter_name or "-"
        filter_item = QTableWidgetItem(filter_name)
        filter_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        # Set foreground color for the filter cell only
        filter_name_upper = (fits_file.filter_name or "").upper()
        if filter_name_upper == 'R':
            filter_item.setForeground(QColor(220, 30, 30))  # Red
        elif filter_name_upper == 'G':
            filter_item.setForeground(QColor(30, 180, 30))  # Green
        elif filter_name_upper == 'B':
            filter_item.setForeground(QColor(30, 80, 220))  # Blue
        # L or others: leave as default (white/system)
        self.setItem(row, 3, filter_item)
        
        # Exposure time
        if fits_file.exptime:
            exposure_str = f"{fits_file.exptime:.1f}s"
        else:
            exposure_str = "-"
        exposure_item = QTableWidgetItem(exposure_str)
        exposure_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 4, exposure_item)
        
        # Bin
        binning = fits_file.binning or "-"
        binning_item = QTableWidgetItem(binning)
        binning_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 5, binning_item)
        
        # Gain
        if fits_file.gain:
            gain_str = f"{fits_file.gain:.1f}"
        else:
            gain_str = "-"
        gain_item = QTableWidgetItem(gain_str)
        gain_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 6, gain_item)
        
        # Offset
        if fits_file.offset:
            offset_str = f"{fits_file.offset:.1f}"
        else:
            offset_str = "-"
        offset_item = QTableWidgetItem(offset_str)
        offset_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 7, offset_item)
        
        # CCD temperature
        temp_item = QTableWidgetItem(f"{fits_file.ccd_temp:.1f}°C" if fits_file.ccd_temp is not None else "-")
        temp_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 8, temp_item)
        
        # Focus
        focus_item = QTableWidgetItem(str(int(fits_file.focus_position)) if fits_file.focus_position is not None else "-")
        focus_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 9, focus_item)
        
        # HFR (Half-Flux Radius)
        if fits_file.hfr:
            hfr_str = f"{fits_file.hfr:.2f}"
        else:
            hfr_str = "-"
        hfr_item = QTableWidgetItem(hfr_str)
        hfr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 10, hfr_item)
        
        # Sources count
        if fits_file.sources_count:
            sources_str = str(fits_file.sources_count)
        else:
            sources_str = "-"
        sources_item = QTableWidgetItem(sources_str)
        sources_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 11, sources_item)
        
        # Image size (X x Y)
        if fits_file.size_x and fits_file.size_y:
            size_str = f"{fits_file.size_x} × {fits_file.size_y}"
        else:
            size_str = "-"
        size_item = QTableWidgetItem(size_str)
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 12, size_item)
        
        # Image scale
        if fits_file.image_scale:
            scale_str = f"{fits_file.image_scale:.2f}\""
        else:
            scale_str = "-"
        scale_item = QTableWidgetItem(scale_str)
        scale_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 13, scale_item)
        
        # RA Center
        if fits_file.ra_center:
            # Convert decimal degrees to hours:minutes:seconds
            ra_hours = fits_file.ra_center / 15.0  # Convert degrees to hours
            ra_h = int(ra_hours)
            ra_m = int((ra_hours - ra_h) * 60)
            ra_s = ((ra_hours - ra_h - ra_m/60) * 3600)
            ra_str = f"{ra_h:02d}:{ra_m:02d}:{ra_s:05.2f}"
        else:
            ra_str = "-"
        ra_item = QTableWidgetItem(ra_str)
        ra_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 14, ra_item)
        
        # DEC Center
        if fits_file.dec_center:
            # Convert decimal degrees to degrees:minutes:seconds
            dec_deg = fits_file.dec_center
            dec_sign = "+" if dec_deg >= 0 else "-"
            dec_deg_abs = abs(dec_deg)
            dec_d = int(dec_deg_abs)
            dec_m = int((dec_deg_abs - dec_d) * 60)
            dec_s = ((dec_deg_abs - dec_d - dec_m/60) * 3600)
            dec_str = f"{dec_sign}{dec_d:02d}:{dec_m:02d}:{dec_s:04.1f}"
        else:
            dec_str = "-"
        dec_item = QTableWidgetItem(dec_str)
        dec_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 15, dec_item)
        
        # WCS Type
        wcs_type = fits_file.wcs_type or "-"
        wcs_item = QTableWidgetItem(wcs_type)
        wcs_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 16, wcs_item)
    
    def _on_cell_clicked(self, row, column):
        """Handle cell clicks for expanding/collapsing runs."""
        item = self.item(row, 0)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and 'is_run_summary' in data:
                # Use the actual row argument, not data['run_index']
                if row in self.expanded_runs:
                    self._collapse_run(row)
                else:
                    self._expand_run(row)
    
    def _reindex_run_summaries(self):
        """Update run_index for all run summary rows to match their current row number."""
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item:
                run_data = item.data(Qt.ItemDataRole.UserRole)
                if run_data and 'is_run_summary' in run_data:
                    run_data['run_index'] = row

    def _expand_run(self, run_index):
        """Expand a run to show individual files."""
        if run_index in self.expanded_runs:
            return
        
        # Find the run data
        item = self.item(run_index, 0)
        if not item:
            return
        
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data or 'run_files' not in data:
            return
        
        run_files = data['run_files']
        
        # Update the visual indicator
        widget = self.cellWidget(run_index, 0)
        if widget and hasattr(widget, 'set_expanded'):
            widget.set_expanded(True)
        
        # Add file rows
        self._add_file_rows(run_index, run_files)
        
        # Mark as expanded
        self.expanded_runs.add(run_index)
        self._reindex_run_summaries()

    def _collapse_run(self, run_index):
        """Collapse a run to hide individual files."""
        if run_index not in self.expanded_runs:
            return
        
        # Find the run data
        item = self.item(run_index, 0)
        if not item:
            return
        
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data or 'run_files' not in data:
            return
        
        run_files = data['run_files']
        
        # Update the visual indicator
        widget = self.cellWidget(run_index, 0)
        if widget and hasattr(widget, 'set_expanded'):
            widget.set_expanded(False)
        
        # Remove file rows
        start_row = run_index + 1
        end_row = start_row + len(run_files)
        
        for _ in range(len(run_files)):
            self.removeRow(start_row)
        
        # Update run_index for all run summary rows below
        for row in range(run_index + 1, self.rowCount()):
            item = self.item(row, 0)
            if item:
                run_data = item.data(Qt.ItemDataRole.UserRole)
                if run_data and 'is_run_summary' in run_data:
                    run_data['run_index'] = row
        
        # Mark as collapsed
        self.expanded_runs.discard(run_index)
        self._apply_striping()
        self._reindex_run_summaries()
    
    def _on_selection_changed(self):
        """Handle table selection changes and prevent run summary rows from being selected or highlighted."""
        selected_indexes = self.selectedIndexes()
        valid_rows = set()
        selected_file_ids = []
        
        for index in selected_indexes:
            item = self.item(index.row(), 0)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data and 'is_file' in data and 'fits_file' in data:
                    valid_rows.add(index.row())
                    selected_file_ids.append(data['fits_file'].id)
        
        # Block signals to avoid recursion
        self.blockSignals(True)
        self.clearSelection()
        for row in valid_rows:
            for col in range(self.columnCount()):
                self.item(row, col).setSelected(True)
        self.blockSignals(False)
        
        # Emit only valid file selections
        self.selection_changed.emit(selected_file_ids)
    
    def get_selected_fits_file_ids(self):
        """Get the IDs of all selected FITS files."""
        selected_rows = self.selectionModel().selectedRows()
        selected_file_ids = []
        
        for row in selected_rows:
            item = self.item(row.row(), 0)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data:
                    if 'is_run_summary' in data and 'run_files' in data:
                        selected_file_ids.extend([f.id for f in data['run_files']])
                    elif 'is_file' in data and 'fits_file' in data:
                        selected_file_ids.append(data['fits_file'].id)
        
        return selected_file_ids
    
    def get_selected_fits_files(self):
        """Get all selected FITS file objects."""
        selected_file_ids = self.get_selected_fits_file_ids()
        return [f for f in self.fits_files if f.id in selected_file_ids]
    
    def clear_selection(self):
        """Clear the current selection."""
        self.clearSelection()
    
    def refresh_table(self):
        """Refresh the table display."""
        if self.fits_files:
            self.populate_table(self.fits_files) 

    def _show_context_menu(self, pos):
        """Show a context menu depending on the selection."""
        selected_files = self.get_selected_fits_files()
        if len(selected_files) == 1:
            def show_header():
                fits_file = selected_files[0]
                # Load header using the shared utility
                try:
                    header = get_fits_header_as_json(fits_file.path)
                except Exception as e:
                    header = {"Error": str(e)}
                dlg = HeaderViewer(header, self)
                dlg.exec()
            def show_image():
                import sys, subprocess
                fits_file = selected_files[0]
                fits_path = fits_file.path
                subprocess.Popen([
                    sys.executable,
                    'lib/gui/viewer/main_viewer.py',
                    fits_path
                ])
            menu = build_single_file_menu(self, show_header_callback=show_header, show_image_callback=show_image)
        elif len(selected_files) > 1:
            menu = build_multi_file_menu(self)
        else:
            menu = build_empty_menu(self)
        menu.exec(self.viewport().mapToGlobal(pos)) 

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.pos())
        if item:
            data = self.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
            if data and 'is_file' in data and 'fits_file' in data:
                fits_file = data['fits_file']
                fits_path = fits_file.path
                import sys, subprocess
                subprocess.Popen([
                    sys.executable,
                    'lib/gui/viewer/main_viewer.py',
                    fits_path
                ])
        super().mouseDoubleClickEvent(event) 