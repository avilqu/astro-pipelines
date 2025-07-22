from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import pyqtSignal, Qt
from lib.db import get_db_manager

class LeftPanel(QWidget):
    menu_selection_changed = pyqtSignal(str, str)  # (category, value)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.menu_tree = QTreeWidget()
        self.menu_tree.setHeaderHidden(True)
        self.menu_tree.setIndentation(16)
        self.menu_tree.setAnimated(True)
        self.menu_tree.setMinimumWidth(100)
        self.menu_tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.menu_tree.setColumnCount(1)

        # Set light grey text color
        self.menu_tree.setStyleSheet("QTreeWidget { color: #cccccc; }")

        # Top-level items
        self.obslog_item = QTreeWidgetItem(["Obs log"])
        self.targets_item = QTreeWidgetItem(["Targets"])
        self.dates_item = QTreeWidgetItem(["Dates"])
        self.menu_tree.addTopLevelItem(self.obslog_item)
        self.menu_tree.addTopLevelItem(self.targets_item)
        self.menu_tree.addTopLevelItem(self.dates_item)

        # Populate targets and dates immediately
        db = get_db_manager()
        for target in db.get_unique_targets():
            QTreeWidgetItem(self.targets_item, [target])
        for date in reversed(db.get_unique_dates()):
            QTreeWidgetItem(self.dates_item, [date])

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
            self.menu_selection_changed.emit("target", current.text(0))
        elif current.parent() is self.dates_item:
            self.menu_selection_changed.emit("date", current.text(0))
        else:
            self.menu_selection_changed.emit("unknown", current.text(0))

    def set_menu_index(self, index):
        item = [self.obslog_item, self.targets_item, self.dates_item][index]
        self.menu_tree.setCurrentItem(item) 