from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt6.QtCore import Qt

class HeaderViewer(QDialog):
    def __init__(self, header_dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FITS Header")
        self.resize(600, 500)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(self)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Key", "Value"])
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(True)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.populate(header_dict)

    def populate(self, header_dict):
        self.table.setRowCount(len(header_dict))
        for i, (key, value) in enumerate(header_dict.items()):
            key_item = QTableWidgetItem(str(key))
            key_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            value_item = QTableWidgetItem(str(value))
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(i, 0, key_item)
            self.table.setItem(i, 1, value_item) 