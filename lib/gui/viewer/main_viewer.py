import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

import numpy as np
from astropy.io import fits
from PyQt6.QtWidgets import QApplication, QMainWindow, QScrollArea, QToolBar, QFileDialog
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QAction
from lib.gui_widgets import ImageLabel
from lib.gui_image_processing import create_image_object
from lib.gui.viewer.navigation import NavigationMixin

class NoWheelScrollArea(QScrollArea):
    def wheelEvent(self, event):
        # Ignore wheel events so they are not used for scrolling
        event.ignore()

class SimpleFITSViewer(NavigationMixin, QMainWindow):
    def __init__(self, fits_path=None):
        super().__init__()
        self.setWindowTitle("Astropipes FITS Viewer")
        self.setGeometry(100, 100, 1000, 800)

        self.pixmap = None  # For ImageLabel compatibility
        self.wcs = None    # For ImageLabel compatibility
        self.image_data = None  # Store current image data
        self.stretch_mode = 'linear'  # 'linear' or 'log'

        # Add a toolbar
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self.toolbar)
        # Open FITS button
        open_icon = QIcon.fromTheme("document-open")
        if open_icon.isNull():
            open_icon = QIcon.fromTheme("folder-open")
        load_action = QAction(open_icon, "Open FITS", self)
        load_action.setToolTip("Open FITS file")
        load_action.triggered.connect(self.open_file_dialog)
        self.toolbar.addAction(load_action)
        self.toolbar.widgetForAction(load_action).setFixedSize(32, 32)
        # Linear stretch button (0)
        linear_action = QAction("0", self)
        linear_action.setToolTip("Linear histogram stretch")
        linear_action.triggered.connect(self.set_linear_stretch)
        self.toolbar.addAction(linear_action)
        self.toolbar.widgetForAction(linear_action).setFixedSize(32, 32)
        # Log stretch button (+)
        log_action = QAction("+", self)
        log_action.setToolTip("Logarithmic histogram stretch")
        log_action.triggered.connect(self.set_log_stretch)
        self.toolbar.addAction(log_action)
        self.toolbar.widgetForAction(log_action).setFixedSize(32, 32)

        # Central widget: scroll area with image label
        self.scroll_area = NoWheelScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.setCentralWidget(self.scroll_area)

        self.image_label = ImageLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("QLabel { background-color: black; }")
        self.image_label.setText("No image loaded")
        self.scroll_area.setWidget(self.image_label)

        if fits_path:
            self.load_fits(fits_path)

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open FITS file", "", "FITS files (*.fits *.fit *.fts);;All files (*)")
        if file_path:
            self.load_fits(file_path)

    def set_linear_stretch(self):
        self.stretch_mode = 'linear'
        self.update_image_display()

    def set_log_stretch(self):
        self.stretch_mode = 'log'
        self.update_image_display()

    def update_image_display(self):
        if self.image_data is None:
            return
        if self.stretch_mode == 'linear':
            pixmap = create_image_object(self.image_data)
        else:
            # Logarithmic stretch: scale data, then use create_image_object
            data = self.image_data.astype(float)
            data = np.where(data > 0, np.log10(data), 0)
            pixmap = create_image_object(data)
        self.image_label.setPixmap(pixmap)
        self.image_label.setFixedSize(pixmap.size())
        self.pixmap = pixmap

    def load_fits(self, fits_path):
        try:
            with fits.open(fits_path) as hdul:
                image_data = hdul[0].data
                if image_data is not None:
                    # Only display 2D images
                    if image_data.ndim == 2:
                        self.image_data = image_data
                        self.update_image_display()
                        self.image_label.setText("")
                        self.setWindowTitle(f"Simple FITS Viewer - {fits_path}")
                    else:
                        self.image_label.setText("FITS file is not a 2D image.")
                        self.image_data = None
                else:
                    self.image_label.setText("No image data in FITS file.")
                    self.image_data = None
        except Exception as e:
            self.image_label.setText(f"Error loading FITS: {e}")
            self.image_data = None

def main():
    fits_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication(sys.argv)
    viewer = SimpleFITSViewer(fits_path)
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 