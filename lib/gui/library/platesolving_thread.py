import signal
from PyQt6.QtCore import QThread, pyqtSignal
from lib.fits.astrometry import solve_single_image, PlatesolvingResult

class PlatesolvingThread(QThread):
    output = pyqtSignal(str)
    finished = pyqtSignal(object)  # Emits PlatesolvingResult

    def __init__(self, fits_file_path):
        super().__init__()
        self.fits_file_path = fits_file_path
        self._process = None
        self._should_stop = False

    def set_process(self, process):
        self._process = process

    def stop(self):
        self._should_stop = True
        if self._process is not None:
            try:
                self.output.emit("\nCancelling platesolving...\n")
                self._process.send_signal(signal.SIGINT)
            except Exception as e:
                self.output.emit(f"\nError sending cancel signal: {e}\n")

    def run(self):
        def output_callback(line):
            self.output.emit(line)
        def process_callback(process):
            self.set_process(process)
        result = solve_single_image(self.fits_file_path, output_callback=output_callback, process_callback=process_callback)
        self.finished.emit(result) 