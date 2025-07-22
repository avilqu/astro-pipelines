import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

import numpy as np
from astropy.io import fits
from PyQt6.QtWidgets import QApplication, QMainWindow, QScrollArea
from PyQt6.QtCore import Qt
from lib.gui_widgets import ImageLabel
from lib.gui_image_processing import create_image_object

class SimpleFITSViewer(QMainWindow):
    def __init__(self, fits_path=None):
        super().__init__()
        self.setWindowTitle("Simple FITS Viewer")
        self.setGeometry(100, 100, 1000, 800)

        self.pixmap = None  # For ImageLabel compatibility
        self.wcs = None    # For ImageLabel compatibility

        # Central widget: scroll area with image label
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.setCentralWidget(self.scroll_area)

        self.image_label = ImageLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("QLabel { background-color: black; }")
        self.image_label.setText("No image loaded")
        self.scroll_area.setWidget(self.image_label)

        if fits_path:
            self.load_fits(fits_path)

    def load_fits(self, fits_path):
        try:
            with fits.open(fits_path) as hdul:
                image_data = hdul[0].data
                if image_data is not None:
                    # Only display 2D images
                    if image_data.ndim == 2:
                        pixmap = create_image_object(image_data)
                        self.image_label.setPixmap(pixmap)
                        self.image_label.setFixedSize(pixmap.size())
                        self.image_label.setText("")
                        self.setWindowTitle(f"Simple FITS Viewer - {fits_path}")
                        self.pixmap = pixmap  # For ImageLabel compatibility
                    else:
                        self.image_label.setText("FITS file is not a 2D image.")
                else:
                    self.image_label.setText("No image data in FITS file.")
        except Exception as e:
            self.image_label.setText(f"Error loading FITS: {e}")

def main():
    fits_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication(sys.argv)
    viewer = SimpleFITSViewer(fits_path)
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 