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

def build_multi_file_menu(parent=None, load_in_viewer_callback=None):
    menu = QMenu(parent)
    if load_in_viewer_callback:
        load_action = QAction("Load files in FITS viewer", menu)
        font = load_action.font()
        font.setBold(True)
        load_action.setFont(font)
        load_action.triggered.connect(load_in_viewer_callback)
        menu.addAction(load_action)
    else:
        menu.addAction("No actions available (multiple files)")
    return menu

def build_empty_menu(parent=None):
    menu = QMenu(parent)
    menu.addAction("No actions available (empty menu)")
    return menu 

def build_sidebar_target_menu(parent=None, target_name=None, show_info_callback=None, rename_target_callback=None):
    menu = QMenu(parent)
    # Add rename action
    rename_action = QAction("Rename target", menu)
    if rename_target_callback:
        rename_action.triggered.connect(rename_target_callback)
    menu.addAction(rename_action)
    return menu 