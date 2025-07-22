from .table_main import MainFitsTableWidget
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtCore import Qt
import os
from datetime import datetime, date
from .header_viewer import HeaderViewer
from .context import build_single_file_menu, build_empty_menu, build_calibration_single_file_menu

class MasterDarksTableWidget(MainFitsTableWidget):
    """Table widget for displaying master dark calibration files, using the same model as MainFitsTableWidget."""
    def init_table(self):
        super().init_table()
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        try:
            self.itemSelectionChanged.disconnect()
        except Exception:
            pass
        self.itemSelectionChanged.connect(lambda: None)
        self.setSortingEnabled(True)
        self.setShowGrid(True)
        self.setGridStyle(self.gridStyle())
        # Set correct column count and headers for Darks
        self.setColumnCount(10)
        self.setHorizontalHeaderLabels([
            "Filename", "Date", "Age", "Exposure", "Bin", "Gain", "Offset", "CCD temp", "Size", "Count"
        ])
        header = self.horizontalHeader()
        for i in range(self.columnCount()):
            header.setSectionResizeMode(i, self.horizontalHeader().ResizeMode.Interactive)
        self.setColumnWidth(0, 200)   # Filename
        self.setColumnWidth(1, 120)   # Date
        self.setColumnWidth(2, 60)    # Age
        self.setColumnWidth(3, 80)    # Exposure
        self.setColumnWidth(4, 60)    # Bin
        self.setColumnWidth(5, 60)    # Gain
        self.setColumnWidth(6, 60)    # Offset
        self.setColumnWidth(7, 80)    # CCD temp
        self.setColumnWidth(8, 80)    # Size
        self.setColumnWidth(9, 80)    # Count
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self):
        selected_indexes = self.selectedIndexes()
        valid_rows = set(index.row() for index in selected_indexes)
        self.blockSignals(True)
        self.clearSelection()
        for row in valid_rows:
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    item.setSelected(True)
        self.blockSignals(False)

    def get_selected_calibration_files(self):
        selected_rows = self.selectionModel().selectedRows()
        selected_files = []
        for row in selected_rows:
            item = self.item(row.row(), 0)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data and 'is_calibration' in data and 'calibration' in data:
                    selected_files.append(data['calibration'])
        return selected_files

    def _show_context_menu(self, pos):
        selected_files = self.get_selected_calibration_files()
        if len(selected_files) == 1:
            cal = selected_files[0]
            def show_header():
                try:
                    header = cal.header_json if hasattr(cal, 'header_json') else {}
                    if isinstance(header, str):
                        import json
                        header = json.loads(header)
                except Exception as e:
                    header = {"Error": str(e)}
                dlg = HeaderViewer(header, self)
                dlg.exec()
            menu = build_calibration_single_file_menu(self, show_header_callback=show_header)
            menu.exec(self.viewport().mapToGlobal(pos))
            return
        # Fallback: use row under cursor
        index = self.indexAt(pos)
        if index.isValid():
            item = self.item(index.row(), 0)
            data = item.data(Qt.ItemDataRole.UserRole) if item else None
            if data and 'is_calibration' in data and 'calibration' in data:
                cal = data['calibration']
                def show_header():
                    try:
                        header = cal.header_json if hasattr(cal, 'header_json') else {}
                        if isinstance(header, str):
                            import json
                            header = json.loads(header)
                    except Exception as e:
                        header = {"Error": str(e)}
                    dlg = HeaderViewer(header, self)
                    dlg.exec()
                menu = build_calibration_single_file_menu(self, show_header_callback=show_header)
                menu.exec(self.viewport().mapToGlobal(pos))
                return
        menu = build_empty_menu(self)
        menu.exec(self.viewport().mapToGlobal(pos))

    def populate(self, darks):
        self._last_populated = darks
        self.blockSignals(True)
        self.setSortingEnabled(False)
        self.clearSelection()
        sorted_darks = sorted(darks, key=lambda d: getattr(d, 'date', '') or '', reverse=True)
        self.clearContents()
        self.setRowCount(len(sorted_darks))
        self.verticalHeader().setDefaultSectionSize(30)
        for row, dark in enumerate(sorted_darks):
            filename = os.path.basename(getattr(dark, 'path', ''))
            date_str = getattr(dark, 'date', '-') or '-'
            # Age calculation
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                age = (date.today() - file_date).days
            except Exception:
                age = '-'
            exptime = getattr(dark, 'exptime', '-')
            binning = getattr(dark, 'binning', '-') or '-'
            gain = getattr(dark, 'gain', '-')
            offset = getattr(dark, 'offset', '-')
            ccd_temp = getattr(dark, 'ccd_temp', '-')
            focus = getattr(dark, 'focus_position', '-')
            size_x = getattr(dark, 'size_x', '-')
            size_y = getattr(dark, 'size_y', '-')
            size = f"{size_x} × {size_y}" if size_x and size_y and size_x != '-' and size_y != '-' else "-"
            integration_count = getattr(dark, 'integration_count', '-')
            if integration_count in (None, '', 'None'):
                integration_count = '-'
            items = [
                QTableWidgetItem(str(filename)),
                QTableWidgetItem(str(date_str)),
                QTableWidgetItem(str(age)),
                QTableWidgetItem(f"{exptime:.1f}" if isinstance(exptime, (float, int)) else (str(exptime) if exptime not in (None, '', 'None') else '-')),
                QTableWidgetItem(str(binning)),
                QTableWidgetItem(f"{gain:.1f}" if isinstance(gain, (float, int)) else (str(gain) if gain not in (None, '', 'None') else '-')),
                QTableWidgetItem(f"{offset:.1f}" if isinstance(offset, (float, int)) else (str(offset) if offset not in (None, '', 'None') else '-')),
                QTableWidgetItem(f"{ccd_temp:.1f}" if isinstance(ccd_temp, (float, int)) else (str(ccd_temp) if ccd_temp not in (None, '', 'None') else '-')),
                QTableWidgetItem(str(size)),
                QTableWidgetItem(str(integration_count)),
            ]
            # Attach calibration object to first cell
            items[0].setData(Qt.ItemDataRole.UserRole, {'calibration': dark, 'is_calibration': True})
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(row, col, item)
        self._apply_striping()
        self.blockSignals(False)
        self.setSortingEnabled(True)
        if self.rowCount() > 1:
            self.sortItems(1, Qt.SortOrder.DescendingOrder) 

class MasterBiasTableWidget(MainFitsTableWidget):
    """Table widget for displaying master bias calibration files."""
    def init_table(self):
        super().init_table()
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        # Set correct column count and headers for Bias
        self.setColumnCount(9)
        self.setHorizontalHeaderLabels([
            "Filename", "Date", "Age", "Bin", "Gain", "Offset", "CCD temp", "Size", "Count"
        ])
        header = self.horizontalHeader()
        for i in range(self.columnCount()):
            header.setSectionResizeMode(i, self.horizontalHeader().ResizeMode.Interactive)
        self.setColumnWidth(0, 200)   # Filename
        self.setColumnWidth(1, 120)   # Date
        self.setColumnWidth(2, 60)    # Age
        self.setColumnWidth(3, 60)    # Bin
        self.setColumnWidth(4, 60)    # Gain
        self.setColumnWidth(5, 60)    # Offset
        self.setColumnWidth(6, 80)    # CCD temp
        self.setColumnWidth(7, 80)    # Size
        self.setColumnWidth(8, 100)   # Count
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self):
        selected_indexes = self.selectedIndexes()
        valid_rows = set(index.row() for index in selected_indexes)
        self.blockSignals(True)
        self.clearSelection()
        for row in valid_rows:
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    item.setSelected(True)
        self.blockSignals(False)

    def get_selected_calibration_files(self):
        selected_rows = self.selectionModel().selectedRows()
        selected_files = []
        for row in selected_rows:
            idx = row.row()
            if hasattr(self, '_last_populated') and self._last_populated and len(self._last_populated) > idx:
                selected_files.append(self._last_populated[idx])
        return selected_files

    def _show_context_menu(self, pos):
        index = self.indexAt(pos)
        if index.isValid():
            if not self.item(index.row(), 0).isSelected():
                self.clearSelection()
                for col in range(self.columnCount()):
                    item = self.item(index.row(), col)
                    if item:
                        item.setSelected(True)
        selected_files = self.get_selected_calibration_files()
        if len(selected_files) == 1:
            cal = selected_files[0]
            def show_header():
                try:
                    header = cal.header_json if hasattr(cal, 'header_json') else {}
                    if isinstance(header, str):
                        import json
                        header = json.loads(header)
                except Exception as e:
                    header = {"Error": str(e)}
                dlg = HeaderViewer(header, self)
                dlg.exec()
            menu = build_calibration_single_file_menu(self, show_header_callback=show_header)
            menu.exec(self.viewport().mapToGlobal(pos))
        elif len(selected_files) > 1:
            menu = build_empty_menu(self)
            menu.exec(self.viewport().mapToGlobal(pos))
        else:
            menu = build_empty_menu(self)
            menu.exec(self.viewport().mapToGlobal(pos))

    def populate(self, biases):
        self._last_populated = biases
        self.blockSignals(True)
        self.setSortingEnabled(False)
        self.clearSelection()
        sorted_biases = sorted(biases, key=lambda b: getattr(b, 'date', '') or '', reverse=True)
        self.clearContents()
        self.setRowCount(len(sorted_biases))
        self.verticalHeader().setDefaultSectionSize(30)
        for row, bias in enumerate(sorted_biases):
            filename = os.path.basename(getattr(bias, 'path', ''))
            date_str = getattr(bias, 'date', '-') or '-'
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                age = (date.today() - file_date).days
            except Exception:
                age = '-'
            binning = getattr(bias, 'binning', '-') or '-'
            gain = getattr(bias, 'gain', '-')
            offset = getattr(bias, 'offset', '-')
            ccd_temp = getattr(bias, 'ccd_temp', '-')
            size_x = getattr(bias, 'size_x', '-')
            size_y = getattr(bias, 'size_y', '-')
            size = f"{size_x} × {size_y}" if size_x and size_y and size_x != '-' and size_y != '-' else "-"
            count = getattr(bias, 'integration_count', '-')
            if count in (None, '', 'None'):
                count = '-'
            items = [
                QTableWidgetItem(str(filename)),
                QTableWidgetItem(str(date_str)),
                QTableWidgetItem(str(age)),
                QTableWidgetItem(str(binning)),
                QTableWidgetItem(f"{gain:.1f}" if isinstance(gain, (float, int)) else (str(gain) if gain not in (None, '', 'None') else '-')),
                QTableWidgetItem(f"{offset:.1f}" if isinstance(offset, (float, int)) else (str(offset) if offset not in (None, '', 'None') else '-')),
                QTableWidgetItem(f"{ccd_temp:.1f}" if isinstance(ccd_temp, (float, int)) else (str(ccd_temp) if ccd_temp not in (None, '', 'None') else '-')),
                QTableWidgetItem(str(size)),
                QTableWidgetItem(str(count)),
            ]
            # Attach calibration object to first cell
            items[0].setData(Qt.ItemDataRole.UserRole, {'calibration': bias, 'is_calibration': True})
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(row, col, item)
        self._apply_striping()
        self.blockSignals(False)
        self.setSortingEnabled(True)
        if self.rowCount() > 1:
            self.sortItems(1, Qt.SortOrder.DescendingOrder) 

class MasterFlatsTableWidget(MainFitsTableWidget):
    """Table widget for displaying master flat calibration files."""
    def init_table(self):
        super().init_table()
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        # Set correct column count and headers for Flats
        self.setColumnCount(12)
        self.setHorizontalHeaderLabels([
            "Filename", "Date", "Age", "Filter", "Exposure", "Bin", "Gain", "Offset", "CCD temp", "Focus", "Size", "Count"
        ])
        header = self.horizontalHeader()
        for i in range(self.columnCount()):
            header.setSectionResizeMode(i, self.horizontalHeader().ResizeMode.Interactive)
        self.setColumnWidth(0, 200)   # Filename
        self.setColumnWidth(1, 120)   # Date
        self.setColumnWidth(2, 60)    # Age
        self.setColumnWidth(3, 80)    # Filter
        self.setColumnWidth(4, 80)    # Exposure
        self.setColumnWidth(5, 60)    # Bin
        self.setColumnWidth(6, 60)    # Gain
        self.setColumnWidth(7, 60)    # Offset
        self.setColumnWidth(8, 80)    # CCD temp
        self.setColumnWidth(9, 100)   # Focus
        self.setColumnWidth(10, 80)   # Size
        self.setColumnWidth(11, 100)  # Count
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self):
        selected_indexes = self.selectedIndexes()
        valid_rows = set(index.row() for index in selected_indexes)
        self.blockSignals(True)
        self.clearSelection()
        for row in valid_rows:
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    item.setSelected(True)
        self.blockSignals(False)

    def get_selected_calibration_files(self):
        selected_rows = self.selectionModel().selectedRows()
        selected_files = []
        for row in selected_rows:
            idx = row.row()
            if hasattr(self, '_last_populated') and self._last_populated and len(self._last_populated) > idx:
                selected_files.append(self._last_populated[idx])
        return selected_files

    def _show_context_menu(self, pos):
        index = self.indexAt(pos)
        if index.isValid():
            if not self.item(index.row(), 0).isSelected():
                self.clearSelection()
                for col in range(self.columnCount()):
                    item = self.item(index.row(), col)
                    if item:
                        item.setSelected(True)
        selected_files = self.get_selected_calibration_files()
        if len(selected_files) == 1:
            cal = selected_files[0]
            def show_header():
                try:
                    header = cal.header_json if hasattr(cal, 'header_json') else {}
                    if isinstance(header, str):
                        import json
                        header = json.loads(header)
                except Exception as e:
                    header = {"Error": str(e)}
                dlg = HeaderViewer(header, self)
                dlg.exec()
            menu = build_calibration_single_file_menu(self, show_header_callback=show_header)
            menu.exec(self.viewport().mapToGlobal(pos))
        elif len(selected_files) > 1:
            menu = build_empty_menu(self)
            menu.exec(self.viewport().mapToGlobal(pos))
        else:
            menu = build_empty_menu(self)
            menu.exec(self.viewport().mapToGlobal(pos))

    def populate(self, flats):
        self._last_populated = flats
        self.blockSignals(True)
        self.setSortingEnabled(False)
        self.clearSelection()
        sorted_flats = sorted(flats, key=lambda f: getattr(f, 'date', '') or '', reverse=True)
        self.clearContents()
        self.setRowCount(len(sorted_flats))
        self.verticalHeader().setDefaultSectionSize(30)
        for row, flat in enumerate(sorted_flats):
            filename = os.path.basename(getattr(flat, 'path', ''))
            date_str = getattr(flat, 'date', '-') or '-'
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                age = (date.today() - file_date).days
            except Exception:
                age = '-'
            filter_name = getattr(flat, 'filter_name', '-') or '-'
            exptime = getattr(flat, 'exptime', '-')
            binning = getattr(flat, 'binning', '-') or '-'
            gain = getattr(flat, 'gain', '-')
            offset = getattr(flat, 'offset', '-')
            ccd_temp = getattr(flat, 'ccd_temp', '-')
            focus = getattr(flat, 'focus_position', '-')
            size_x = getattr(flat, 'size_x', '-')
            size_y = getattr(flat, 'size_y', '-')
            size = f"{size_x} × {size_y}" if size_x and size_y and size_x != '-' and size_y != '-' else "-"
            count = getattr(flat, 'integration_count', '-')
            if count in (None, '', 'None'):
                count = '-'
            items = [
                QTableWidgetItem(str(filename)),
                QTableWidgetItem(str(date_str)),
                QTableWidgetItem(str(age)),
                QTableWidgetItem(str(filter_name)),
                QTableWidgetItem(f"{exptime:.1f}" if isinstance(exptime, (float, int)) else (str(exptime) if exptime not in (None, '', 'None') else '-')),
                QTableWidgetItem(str(binning)),
                QTableWidgetItem(f"{gain:.1f}" if isinstance(gain, (float, int)) else (str(gain) if gain not in (None, '', 'None') else '-')),
                QTableWidgetItem(f"{offset:.1f}" if isinstance(offset, (float, int)) else (str(offset) if offset not in (None, '', 'None') else '-')),
                QTableWidgetItem(f"{ccd_temp:.1f}" if isinstance(ccd_temp, (float, int)) else (str(ccd_temp) if ccd_temp not in (None, '', 'None') else '-')),
                QTableWidgetItem(str(int(focus)) if isinstance(focus, (float, int)) and focus not in (None, '', 'None') else (str(focus) if focus not in (None, '', 'None') else '-')),
                QTableWidgetItem(str(size)),
                QTableWidgetItem(str(count)),
            ]
            # Attach calibration object to first cell
            items[0].setData(Qt.ItemDataRole.UserRole, {'calibration': flat, 'is_calibration': True})
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(row, col, item)
        self._apply_striping()
        self.blockSignals(False)
        self.setSortingEnabled(True)
        if self.rowCount() > 1:
            self.sortItems(1, Qt.SortOrder.DescendingOrder) 