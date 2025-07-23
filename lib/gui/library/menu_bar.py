from PyQt6.QtWidgets import QMenuBar
from PyQt6.QtGui import QAction

def create_menu_bar(parent, on_exit, on_scan):
    """Create the menu bar with File and Database menus, and connect actions to callbacks."""
    menubar = parent.menuBar() if hasattr(parent, 'menuBar') else QMenuBar(parent)

    # Create File menu
    file_menu = menubar.addMenu("File")
    exit_action = QAction("Exit", parent)
    exit_action.setShortcut("Ctrl+Q")
    exit_action.triggered.connect(on_exit)
    file_menu.addAction(exit_action)

    # Create Database menu
    db_menu = menubar.addMenu("Database")
    scan_action = QAction("Scan for new files", parent)
    scan_action.triggered.connect(on_scan)
    db_menu.addAction(scan_action)

    return menubar 