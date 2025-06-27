from PyQt6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt


def create_control_panel(parent_viewer):
    """Create the control panel with buttons"""
    panel = QFrame()
    panel.setFrameStyle(QFrame.Shape.Box)
    panel.setMaximumWidth(200)
    
    layout = QVBoxLayout(panel)
    
    # Open file button
    parent_viewer.open_button = QPushButton("Open FITS File")
    parent_viewer.open_button.clicked.connect(parent_viewer.open_file)
    layout.addWidget(parent_viewer.open_button)
    
    # Auto Stretch button
    parent_viewer.stretch_button = QPushButton("Auto Stretch")
    parent_viewer.stretch_button.setToolTip("Toggle between no stretch and auto stretch")
    parent_viewer.stretch_button.setCheckable(True)  # Make it a toggleable button
    parent_viewer.stretch_button.clicked.connect(parent_viewer.toggle_stretch)
    layout.addWidget(parent_viewer.stretch_button)
    
    # FITS Header button
    parent_viewer.header_button = QPushButton("FITS Header")
    parent_viewer.header_button.setToolTip("View full FITS header")
    parent_viewer.header_button.clicked.connect(parent_viewer.show_header)
    parent_viewer.header_button.setEnabled(False)  # Disabled until a file is loaded
    layout.addWidget(parent_viewer.header_button)
    
    # Solar System Objects button
    parent_viewer.objects_button = QPushButton("Show SSO")
    parent_viewer.objects_button.setToolTip("Search for and display solar system objects in the field")
    parent_viewer.objects_button.clicked.connect(parent_viewer.toggle_solar_system_objects)
    parent_viewer.objects_button.setEnabled(False)  # Disabled until a file is loaded
    layout.addWidget(parent_viewer.objects_button)
    
    # SIMBAD Search button
    parent_viewer.simbad_button = QPushButton("Find Object")
    parent_viewer.simbad_button.setToolTip("Search for an object in the SIMBAD database")
    parent_viewer.simbad_button.clicked.connect(parent_viewer.search_simbad_object)
    parent_viewer.simbad_button.setEnabled(False)  # Disabled until a file is loaded
    layout.addWidget(parent_viewer.simbad_button)
    
    # Solve button
    parent_viewer.solve_button = QPushButton("Solve")
    parent_viewer.solve_button.setToolTip("Plate solve the current image using astrometry.net")
    parent_viewer.solve_button.clicked.connect(parent_viewer.solve_current_image)
    parent_viewer.solve_button.setEnabled(False)  # Disabled until a file is loaded
    layout.addWidget(parent_viewer.solve_button)
    
    # Reset zoom button
    reset_zoom_button = QPushButton("Reset Zoom")
    reset_zoom_button.clicked.connect(parent_viewer.reset_zoom)
    layout.addWidget(reset_zoom_button)
    
    # Add stretch to push everything to the top
    layout.addStretch()
    
    # Image information section
    info_label = QLabel("Image Information: ")
    info_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
    layout.addWidget(info_label)
    
    # Create info display labels
    parent_viewer.target_label = QLabel("Target: --")
    parent_viewer.filter_label = QLabel("Filter: --")
    parent_viewer.exposure_label = QLabel("Exposure: --")
    parent_viewer.gain_label = QLabel("Gain: --")
    parent_viewer.offset_label = QLabel("Offset: --")
    parent_viewer.wcs_label = QLabel("WCS: --")
    
    # Add info labels to layout
    layout.addWidget(parent_viewer.target_label)
    layout.addWidget(parent_viewer.filter_label)
    layout.addWidget(parent_viewer.exposure_label)
    layout.addWidget(parent_viewer.gain_label)
    layout.addWidget(parent_viewer.offset_label)
    layout.addWidget(parent_viewer.wcs_label)
    
    return panel


def update_image_info(hdu_list, parent_viewer):
    """Update the image information display with FITS header data"""
    header = hdu_list[0].header
    
    # Target name - try common header keywords
    target = "--"
    for key in ['OBJECT', 'TARGET', 'TELESCOP', 'OBSERVER']:
        if key in header:
            target = str(header[key]).strip()
            break
    parent_viewer.target_label.setText(f"Target: {target}")
    
    # Filter information - try common header keywords
    filter_info = "--"
    for key in ['FILTER', 'FILT', 'FILTER1', 'FILTER2', 'FILT1', 'FILT2', 'BANDPASS']:
        if key in header:
            filter_info = str(header[key]).strip()
            break
    parent_viewer.filter_label.setText(f"Filter: {filter_info}")
    
    # Exposure time
    exposure = "--"
    for key in ['EXPTIME', 'EXPOSURE', 'EXPOSURE_TIME']:
        if key in header:
            exposure = f"{header[key]:.1f}s"
            break
    parent_viewer.exposure_label.setText(f"Exposure: {exposure}")
    
    # Gain
    gain = "--"
    for key in ['GAIN', 'EGAIN', 'CCDGAIN']:
        if key in header:
            gain = f"{header[key]:.1f}"
            break
    parent_viewer.gain_label.setText(f"Gain: {gain}")
    
    # Offset
    offset = "--"
    for key in ['OFFSET', 'CCDOFFSET', 'BIAS']:
        if key in header:
            offset = f"{header[key]:.1f}"
            break
    parent_viewer.offset_label.setText(f"Offset: {offset}")
    
    # WCS status
    wcs_status = "No WCS"
    wcs_color = "red"
    parent_viewer.wcs = None  # Reset WCS
    
    if 'CTYPE1' in header and 'CTYPE2' in header:
        ctype1 = header['CTYPE1']
        ctype2 = header['CTYPE2']
        # Extract projection type from CTYPE (e.g., "RA---TAN" -> "TAN")
        if '-' in ctype1:
            projection = ctype1.split('-')[-1]  # Get the last part after the last dash
            wcs_status = f"WCS: {projection}"
        else:
            wcs_status = f"WCS: {ctype1}/{ctype2}"
        wcs_color = "white"
        
        # Try to create WCS object
        try:
            from astropy.wcs import WCS
            parent_viewer.wcs = WCS(header)
            parent_viewer.coord_label.setText("WCS ready - move mouse over image for coordinates")
        except Exception as e:
            parent_viewer.coord_label.setText("WCS present but invalid")
            
    elif 'CD1_1' in header or 'CDELT1' in header:
        wcs_status = "WCS: Present"
        wcs_color = "white"
        try:
            from astropy.wcs import WCS
            parent_viewer.wcs = WCS(header)
            parent_viewer.coord_label.setText("WCS ready - move mouse over image for coordinates")
        except Exception as e:
            parent_viewer.coord_label.setText("WCS present but invalid")
    else:
        parent_viewer.coord_label.setText("No WCS - coordinates unavailable")
    
    parent_viewer.wcs_label.setText(wcs_status)
    parent_viewer.wcs_label.setStyleSheet(f"color: {wcs_color};")
    
    # Enable objects button if WCS is available
    if parent_viewer.wcs is not None:
        parent_viewer.objects_button.setEnabled(True)
        parent_viewer.simbad_button.setEnabled(True)
    else:
        parent_viewer.objects_button.setEnabled(False)
        parent_viewer.simbad_button.setEnabled(False)
    
    # Enable solve button when a file is loaded
    parent_viewer.solve_button.setEnabled(True) 