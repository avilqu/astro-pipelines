from PyQt6.QtWidgets import QMenu
from PyQt6.QtGui import QAction

def build_single_file_menu(parent=None, show_header_callback=None):
    menu = QMenu(parent)
    show_header_action = QAction("Show header", menu)
    if show_header_callback:
        show_header_action.triggered.connect(show_header_callback)
    menu.addAction(show_header_action)
    return menu

def build_calibration_single_file_menu(parent=None, show_header_callback=None):
    menu = QMenu(parent)
    show_header_action = QAction("Show header", menu)
    if show_header_callback:
        show_header_action.triggered.connect(show_header_callback)
    menu.addAction(show_header_action)
    return menu

def build_multi_file_menu(parent=None):
    menu = QMenu(parent)
    menu.addAction("No actions available (multiple files)")
    return menu

def build_empty_menu(parent=None):
    menu = QMenu(parent)
    menu.addAction("No actions available (empty menu)")
    return menu 