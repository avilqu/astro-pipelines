from PyQt6.QtWidgets import QMenuBar
from PyQt6.QtGui import QAction

def create_menu_bar(parent, on_exit, on_scan, on_settings=None, on_refresh=None, on_cleanup=None):
    """Create the menu bar with File and Database menus, and connect actions to callbacks."""
    menubar = parent.menuBar() if hasattr(parent, 'menuBar') else QMenuBar(parent)

    # Create File menu
    file_menu = menubar.addMenu("File")
    if on_settings is not None:
        settings_action = QAction("Settings", parent)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(on_settings)
        file_menu.addAction(settings_action)
    exit_action = QAction("Exit", parent)
    exit_action.setShortcut("Ctrl+Q")
    exit_action.triggered.connect(on_exit)
    file_menu.addAction(exit_action)

    # Create Database menu
    db_menu = menubar.addMenu("Database")
    scan_action = QAction("Scan for new files", parent)
    scan_action.triggered.connect(on_scan)
    db_menu.addAction(scan_action)
    if on_refresh is not None:
        refresh_action = QAction("Refresh database", parent)
        refresh_action.triggered.connect(on_refresh)
        db_menu.addAction(refresh_action)
    if on_cleanup is not None:
        cleanup_action = QAction("Cleanup temp directories", parent)
        cleanup_action.triggered.connect(on_cleanup)
        db_menu.addAction(cleanup_action)

    return menubar 