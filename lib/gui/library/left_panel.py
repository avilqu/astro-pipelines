from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QStyledItemDelegate
from PyQt6.QtCore import pyqtSignal, Qt, QRect
from PyQt6.QtGui import QPainter, QFont, QColor
from lib.db import get_db_manager

class CountStyledDelegate(QStyledItemDelegate):
    """Custom delegate to render counts with different styling."""
    
    def paint(self, painter, option, index):
        text = index.data()
        
        # Check if text contains a count (format: "Name (count)")
        if " (" in text and text.endswith(")"):
            # Split the text into name and count
            parts = text.split(" (")
            name = parts[0]
            count = parts[1].rstrip(")")
            
            # Set up the main text style
            painter.save()
            painter.setFont(option.font)
            painter.setPen(QColor("#cccccc"))  # Light grey for main text
            
            # Draw the main text
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            
            # Set up the count text style (smaller and different color)
            count_font = option.font
            count_font.setPointSize(option.font.pointSize() - 2)  # Smaller font
            painter.setFont(count_font)
            painter.setPen(QColor("#888888"))  # Darker grey for count
            
            # Calculate position for count text
            name_width = painter.fontMetrics().horizontalAdvance(name)
            count_text = f" ({count})"
            count_x = option.rect.x() + name_width
            
            # Draw the count text
            count_rect = QRect(count_x, option.rect.y(), 
                             option.rect.width() - name_width, option.rect.height())
            painter.drawText(count_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, count_text)
            
            painter.restore()
        else:
            # For items without counts, use default painting
            super().paint(painter, option, index)

class LeftPanel(QWidget):
    menu_selection_changed = pyqtSignal(str, str)  # (category, value)

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

        # Set light grey text color, bigger font, and padding
        self.menu_tree.setStyleSheet("""
            QTreeWidget {
                color: #cccccc;
                font-size: 14px;
            }
    
        """)
        
        # Apply custom delegate for styled count display
        self.menu_tree.setItemDelegate(CountStyledDelegate())

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