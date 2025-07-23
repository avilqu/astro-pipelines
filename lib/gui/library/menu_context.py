from PyQt6.QtWidgets import QMenu
from PyQt6.QtGui import QAction, QFont

def build_single_file_menu(parent=None, show_header_callback=None, show_image_callback=None, solve_image_callback=None):
    menu = QMenu(parent)
    show_image_action = QAction("Show in FITS viewer", menu)
    font = show_image_action.font()
    font.setBold(True)
    show_image_action.setFont(font)
    if show_image_callback:
        show_image_action.triggered.connect(show_image_callback)
    menu.addAction(show_image_action)
    
    # Add separator before solve image action
    menu.addSeparator()
    
    solve_image_action = QAction("Platesolve image", menu)
    if solve_image_callback:
        solve_image_action.triggered.connect(solve_image_callback)
    menu.addAction(solve_image_action)
    
    show_header_action = QAction("Show header", menu)
    if show_header_callback:
        show_header_action.triggered.connect(show_header_callback)
    menu.addAction(show_header_action)
    return menu

def build_calibration_single_file_menu(parent=None, show_header_callback=None, show_image_callback=None, solve_image_callback=None):
    menu = QMenu(parent)
    show_image_action = QAction("Show in FITS viewer", menu)
    font = show_image_action.font()
    font.setBold(True)
    show_image_action.setFont(font)
    if show_image_callback:
        show_image_action.triggered.connect(show_image_callback)
    menu.addAction(show_image_action)
    
    # Add separator before solve image action
    menu.addSeparator()
    
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