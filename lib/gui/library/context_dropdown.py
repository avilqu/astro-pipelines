from PyQt6.QtWidgets import QMenu
from PyQt6.QtGui import QAction, QFont
from lib.gui.common.console_window import ConsoleOutputWindow
from .platesolving_thread import PlatesolvingThread

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

def build_multi_file_menu(parent=None, load_in_viewer_callback=None, platesolve_all_callback=None):
    menu = QMenu(parent)
    if load_in_viewer_callback:
        load_action = QAction("Load files in FITS viewer", menu)
        font = load_action.font()
        font.setBold(True)
        load_action.setFont(font)
        load_action.triggered.connect(load_in_viewer_callback)
        menu.addAction(load_action)
    if platesolve_all_callback:
        platesolve_action = QAction("Platesolve all files", menu)
        platesolve_action.triggered.connect(platesolve_all_callback)
        menu.addAction(platesolve_action)
    if not load_in_viewer_callback and not platesolve_all_callback:
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

def platesolve_multiple_files(parent, files, on_all_finished=None):
    """
    Platesolve a list of FITS files sequentially, showing output in a console window.
    parent: the parent widget (for dialog parenting)
    files: list of file objects (must have .path)
    on_all_finished: optional callback to call when all files are done
    """
    console_window = ConsoleOutputWindow("Platesolving All Files", parent)
    console_window.show_and_raise()
    queue = list(files)
    results = []
    cancelled = {"flag": False}
    # Ensure threads are kept alive
    if not hasattr(parent, '_platesolving_threads'):
        parent._platesolving_threads = []

    def next_in_queue():
        if cancelled["flag"]:
            console_window.append_text("\nPlatesolving cancelled by user.\n")
            if on_all_finished:
                on_all_finished(results)
            return
        if not queue:
            console_window.append_text("\nAll files platesolved.\n")
            if on_all_finished:
                on_all_finished(results)
            return
        fits_file = queue.pop(0)
        fits_path = fits_file.path
        console_window.append_text(f"\nPlatesolving: {fits_path}\n")
        thread = PlatesolvingThread(fits_path)
        parent._platesolving_threads.append(thread)
        thread.output.connect(console_window.append_text)
        def on_finished(result):
            results.append(result)
            msg = parent._format_platesolving_result(result) if hasattr(parent, '_format_platesolving_result') else str(result)
            console_window.append_text(f"\n{msg}\n")
            # Remove thread from list
            if thread in parent._platesolving_threads:
                parent._platesolving_threads.remove(thread)
            next_in_queue()
        thread.finished.connect(on_finished)
        console_window.cancel_requested.connect(lambda: cancel(thread))
        parent.platesolving_thread = thread  # For possible cancellation
        thread.start()

    def cancel(thread):
        cancelled["flag"] = True
        thread.stop()

    next_in_queue() 