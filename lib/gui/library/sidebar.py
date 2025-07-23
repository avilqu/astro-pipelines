from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QInputDialog, QMessageBox
from PyQt6.QtCore import pyqtSignal, Qt
from lib.db import get_db_manager
from lib.db.edit import rename_target_across_database
from lib.gui.library.context_dropdown import build_sidebar_target_menu

class LeftPanel(QWidget):
    menu_selection_changed = pyqtSignal(str, str)  # (category, value)
    target_renamed = pyqtSignal(str, str)  # (old_name, new_name)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.menu_tree = QTreeWidget()
        self.menu_tree.setHeaderHidden(True)
        self.menu_tree.setIndentation(16)
        self.menu_tree.setAnimated(True)
        self.menu_tree.setMinimumWidth(200)
        self.menu_tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.menu_tree.setColumnCount(1)

        # Set up context menu for targets
        self.menu_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.menu_tree.customContextMenuRequested.connect(self._show_context_menu)

        # Set light grey text color, bigger font, and padding
        self.menu_tree.setStyleSheet("""
            QTreeWidget {
                color: #cccccc;
                font-size: 14px;
            }
    
        """)

        # Initialize database connection
        db = get_db_manager()
        
        # Top-level items
        self.obslog_item = QTreeWidgetItem(["Obs log"])
        self.targets_item = QTreeWidgetItem(["Targets"])
        self.dates_item = QTreeWidgetItem(["Dates"])
        self.menu_tree.addTopLevelItem(self.obslog_item)
        self.menu_tree.addTopLevelItem(self.targets_item)
        self.menu_tree.addTopLevelItem(self.dates_item)

        # Calibration section
        self.calibration_item = QTreeWidgetItem(["Calibration"])
        bias_count = db.get_calibration_file_count("Bias")
        darks_count = db.get_calibration_file_count("Dark")
        flats_count = db.get_calibration_file_count("Flat")
        self.bias_item = QTreeWidgetItem([f"Bias ({bias_count})"])
        self.darks_item = QTreeWidgetItem([f"Darks ({darks_count})"])
        self.flats_item = QTreeWidgetItem([f"Flats ({flats_count})"])
        self.calibration_item.addChild(self.bias_item)
        self.calibration_item.addChild(self.darks_item)
        self.calibration_item.addChild(self.flats_item)
        self.menu_tree.addTopLevelItem(self.calibration_item)
        self.menu_tree.expandItem(self.calibration_item)

        # Populate targets and dates immediately
        for target in db.get_unique_targets():
            count = db.get_file_count_by_target(target)
            QTreeWidgetItem(self.targets_item, [f"{target} ({count})"])
        for date in reversed(db.get_unique_dates()):
            count = db.get_file_count_by_date(date)
            QTreeWidgetItem(self.dates_item, [f"{date} ({count})"])

        # Expand both Targets and Dates by default
        self.menu_tree.expandItem(self.targets_item)
        self.menu_tree.expandItem(self.dates_item)

        layout.addWidget(self.menu_tree)
        self.setMinimumWidth(200)

        self.menu_tree.currentItemChanged.connect(self._emit_selection)

    def _emit_selection(self, current, previous):
        if current is self.obslog_item:
            self.menu_selection_changed.emit("obslog", "")
        elif current is self.targets_item:
            self.menu_selection_changed.emit("targets", "")
        elif current is self.dates_item:
            self.menu_selection_changed.emit("dates", "")
        elif current.parent() is self.targets_item:
            # Extract target name from "Target (count)" format
            target_text = current.text(0)
            target_name = target_text.split(" (")[0]
            self.menu_selection_changed.emit("target", target_name)
        elif current.parent() is self.dates_item:
            # Extract date from "Date (count)" format
            date_text = current.text(0)
            date_name = date_text.split(" (")[0]
            self.menu_selection_changed.emit("date", date_name)
        elif current is self.darks_item:
            self.menu_selection_changed.emit("darks", "")
        elif current is self.bias_item:
            self.menu_selection_changed.emit("bias", "")
        elif current is self.flats_item:
            self.menu_selection_changed.emit("flats", "")
        else:
            self.menu_selection_changed.emit("unknown", current.text(0))

    def _show_context_menu(self, pos):
        item = self.menu_tree.itemAt(pos)
        if item and item.parent() is self.targets_item:
            # This is a target item
            target_text = item.text(0)
            target_name = target_text.split(" (")[0]
            def show_info():
                # Placeholder: show info for the target
                print(f"Show info for target: {target_name}")
            def rename_target():
                new_name, ok = QInputDialog.getText(self, "Rename Target", f"Enter new name for target '{target_name}':")
                if ok and new_name and new_name.strip() and new_name.strip() != target_name:
                    result = rename_target_across_database(target_name, new_name.strip())
                    msg = f"Updated {result['files_updated']} files."
                    if result['errors']:
                        msg += f"\nErrors:\n" + '\n'.join(f"{e['path']}: {e['error']}" for e in result['errors'])
                    QMessageBox.information(self, "Rename Target", msg)
                    self.refresh_counts()
                    self.target_renamed.emit(target_name, new_name.strip())
            menu = build_sidebar_target_menu(self.menu_tree, target_name=target_name, show_info_callback=show_info, rename_target_callback=rename_target)
            menu.exec(self.menu_tree.viewport().mapToGlobal(pos))

    def set_menu_index(self, index):
        item = [self.obslog_item, self.targets_item, self.dates_item][index]
        self.menu_tree.setCurrentItem(item)

    def refresh_counts(self):
        """Refresh the file counts for all items in the tree."""
        db = get_db_manager()
        
        # Refresh target counts
        for i in range(self.targets_item.childCount()):
            child = self.targets_item.child(i)
            target_name = child.text(0).split(" (")[0]
            count = db.get_file_count_by_target(target_name)
            child.setText(0, f"{target_name} ({count})")
        
        # Refresh date counts
        for i in range(self.dates_item.childCount()):
            child = self.dates_item.child(i)
            date_name = child.text(0).split(" (")[0]
            count = db.get_file_count_by_date(date_name)
            child.setText(0, f"{date_name} ({count})")
        
        # Refresh calibration counts
        bias_count = db.get_calibration_file_count("Bias")
        darks_count = db.get_calibration_file_count("Dark")
        flats_count = db.get_calibration_file_count("Flat")
        self.bias_item.setText(0, f"Bias ({bias_count})")
        self.darks_item.setText(0, f"Darks ({darks_count})")
        self.flats_item.setText(0, f"Flats ({flats_count})") 