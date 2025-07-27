"""
Common GUI components for the Astropipes application.
"""

from .header_window import HeaderViewer
from .console_window import ConsoleOutputWindow, RealTimeStringIO
from .sso_window import SSOResultWindow
from .simbad_field_window import SIMBADFieldResultWindow

__all__ = ['HeaderViewer', 'ConsoleOutputWindow', 'RealTimeStringIO', 'SSOResultWindow', 'SIMBADFieldResultWindow'] 