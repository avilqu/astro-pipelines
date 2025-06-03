#!.venv/bin/python

import sys
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout


class MainWindow(QWidget):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWindowTitle('PyQt QPushButton Widget')
        self.setGeometry(100, 100, 320, 210)

        button = QPushButton('Toggle Me')
        button.setCheckable(True)
        button.clicked.connect(self.on_toggle)

        # place the button on the window
        layout = QVBoxLayout()
        layout.addWidget(button)
        self.setLayout(layout)

        # show the window
        self.show()

    def on_toggle(self, checked):
        print(checked)


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # create the main window
    window = MainWindow()

    # start the event loop
    sys.exit(app.exec())
