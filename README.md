# Astro-Pipelines

A set of various tools to perform astronomical image reduction - image calibration (bias, dark, flat and calibration masters library), platesolving (using offline Astrometry.Net engine), image registration (WCS reprojection method), and sequence integration.

Miscellaneous other tools added as the project develops.

## Setup

### Python packages dependencies

Astro-Pipelines requires Python 3.11 to run as some of its dependencies aren't compatible with the latest versions (namely `astroscrappy`).

The recommended approach is to create a virtual environment:
- `python3.11 -m venv .venv`
- `source .venv/bin/activate`
- `pip install -r requirements.txt`

For manual installation, Astro-Pipelines depends on the following pakages:
- `colorama`
- `astropy`
- `ccdproc`
- `astroquery`
- `numpy`
- `pyds9`
- `photutils`
- `requests`
- `watchdog` (for autopipe.py)
- `PyQt6` (for GUI functionality)

### Astrometry.Net

The platesolving methods rely on local access to the [Astrometry.Net engine](https://astrometry.net/) (`solve-field` CLI) and required index files. This is a pretty heavy requirement (the whole index files package weighs over 50GB!).

Astrometry.Net must be built from source code and is available for MacOS, Linux and Unix. Reported to work on Windows via Cygwin.

Without Astrometry.Net engine installed, the `-S` option (`--solve`) won't work (the rest should work without issues). Note that this package includes a CLI wrapper for Astrometry.Net that can call the online solver (much slower and requires Internet connection) - `platesolve.py`.

### Timeout and Error Handling

Astro-Pipelines includes robust timeout and error handling mechanisms to prevent the astrometry engine from hanging on unsolvable images:

- **Configurable timeouts**: Set maximum solving time for both online and offline solving
- **Image validation**: Pre-screening of images to skip obviously unsolvable ones
- **Network error handling**: Graceful handling of connection issues with online solving
- **Progress reporting**: Clear status messages during long operations

See `TIMEOUT_FEATURES.md` for detailed documentation of these features.

## Use

### Initial config

Before using, the user must edit `config.py` to write down the correct `CALIBRATION_PATH`. This is the folder that contains (and/or where will be stored) the calibration masters. If using data from different rigs, this variable needs to be changed as it will hold data for one rig (camera/filters/telescope) only.

### Executable scripts

Astro-Pipelines has several executable scripts:

- `astro-pipelines.py`: Main script giving access to all the package functions. See `--help` option for details.
- `platesolve.py`: Separate wrapper for the Astrometry.Net engine. Use for online platesolving and better control over the platesolving options (although in that last case I would recommend to use `solve-field` directly). See `--help` option for details.
- `autopipe.py`: Automated pipeline that monitors the observation directory for new FITS files and automatically calibrates and platesolves them.

### GUI Viewer

Astro-Pipelines includes a PyQt6-based GUI viewer for FITS images (located in `lib/gui_pyqt.py`) with the following features:

- **Interactive Image Display**: Pan, zoom, and navigate through FITS images
- **WCS Coordinate Display**: Real-time RA/Dec coordinates when hovering over the image
- **Pixel Value Display**: Shows pixel values and bit depth information
- **FITS Header Viewer**: Complete FITS header display with formatted table view
- **Auto Stretch**: Toggle between no stretch and automatic histogram stretching
- **Image Information**: Display target, filter, exposure, gain, offset, and WCS status
- **Solar System Object Search**: Search for and display solar system objects in the field using Skybot cone search
- **Object Markers**: Visual green circles and labels for solar system objects found in the image

#### GUI Usage

```bash
# Open GUI without loading any file
python astro-pipelines.py -G

# Open GUI and load a specific FITS file
python astro-pipelines.py -G path/to/image.fits

# Alternative long form
python astro-pipelines.py --gui path/to/image.fits
```

#### GUI Controls

- **Mouse**: 
  - Left-click and drag to pan
  - Mouse wheel to zoom in/out
- **Keyboard**:
  - `+` or `=` to zoom in
  - `-` to zoom out
  - `0` to reset zoom
  - `O` to open a new file
- **Buttons**:
  - **Open FITS File**: Browse and load a FITS file
  - **Auto Stretch**: Toggle automatic histogram stretching
  - **FITS Header**: View complete FITS header information
  - **Solar System Objects**: Search for solar system objects in the field (requires WCS)
  - **Toggle Object Markers**: Show/hide green circles for solar system objects
  - **Reset Zoom**: Return to 100% zoom level

#### Plate Solving with Progress Dialog

The GUI includes an enhanced plate solving feature with real-time progress monitoring:

**Features:**
- **Progress Dialog**: A dedicated window shows solving progress with real-time console output
- **Live Output Capture**: See the actual `solve-field` command output as it happens
- **Cancel Support**: Ability to cancel solving process at any time
- **Button State Feedback**: Solve button changes to "Solving..." with orange background during processing
- **Threaded Processing**: Solving runs in background thread to keep GUI responsive

**Usage:**
1. Load a FITS image (with or without WCS information)
2. Click the "Solve" button
3. A progress dialog will open showing:
   - Real-time console output from the solving process
   - Cancel and Close buttons
4. The solve button will change to "Solving..." and be disabled
5. When solving completes, the dialog enables the Close button
6. If successful, the image is automatically reloaded with the new WCS information

**Solving Modes:**
- **Guided Solving**: Uses existing WCS information for faster, more accurate solving
- **Blind Solving**: Searches the entire sky when no WCS information is available

**Progress Dialog Features:**
- **Dark Theme**: Console output uses dark background with white text for better readability
- **Auto-scroll**: Output automatically scrolls to show the latest messages
- **Process Monitoring**: Shows the exact `solve-field` command being executed
- **Error Handling**: Displays detailed error messages if solving fails
- **WCS Validation**: Automatically validates and applies the WCS solution to the original file

#### Solar System Object Search

The GUI includes advanced functionality to search for and display solar system objects in astronomical images:

**Requirements:**
- FITS image with valid WCS (World Coordinate System) information
- Observation date/time in the FITS header (DATE-OBS, TIME-OBS, etc.)
- Internet connection for Skybot service access

**Features:**
- **Skybot Cone Search**: Uses the IMCCE Skybot service to find solar system objects in the field
- **Object Information**: Displays name, type, coordinates, magnitude, distance, and velocity
- **Visual Markers**: Green circles with object names overlaid on the image
- **Filtered Results**: Only shows objects actually within the image boundaries

**Usage:**
1. Load a FITS image with WCS information
2. Click "Solar System Objects" button
3. The system will search for objects and display results in a dialog
4. Use "Toggle Object Markers" to show/hide green circles on the image

**Object Information Displayed:**
- **Name**: Object identifier (e.g., asteroid number, comet designation)
- **Type**: Object classification (asteroid, comet, planet, etc.)
- **RA/Dec**: Right ascension and declination in degrees
- **Magnitude**: Apparent brightness
- **Distance**: Distance from Earth in Astronomical Units (AU)
- **Velocity**: Apparent motion in arcseconds per hour

### AutoPipe Usage

AutoPipe automatically monitors the observation directory (configured via `OBS_PATH` in `config.py`) for new FITS files and processes them through the calibration and platesolving pipeline.

Before using AutoPipe, make sure to set the correct `OBS_PATH` in `config.py`:

```python
OBS_PATH = '/path/to/your/observations'
```

Usage examples:

```bash
# Use default paths from config.py
python autopipe.py

# With custom observation directory
python autopipe.py --obs-path /custom/obs/path

# With custom output directory
python autopipe.py --autopipe-path /custom/output/path

# Process existing files before starting monitoring
python autopipe.py --process-existing
```

The default autopipe output directory is `OBS_PATH/autopipe`.
