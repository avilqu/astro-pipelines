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

### Astrometry.Net

The platesolving methods rely on local access to the [Astrometry.Net engine](https://astrometry.net/) (`solve-field` CLI) and required index files. This is a pretty heavy requirement (the whole index files package weighs over 50GB!).

Astrometry.Net must be built from source code and is available for MacOS, Linux and Unix. Reported to work on Windows via Cygwin.

Without Astrometry.Net engine installed, the `-S` option (`--solve`) won't work (the rest should work without issues). Note that this package includes a CLI wrapper for Astrometry.Net that can call the online solver (much slower and requires Internet connection) - `platesolve.py`.

## Use

### Initial config

Before using, the user must edit `config.py` to write down the correct `CALIBRATION_PATH`. This is the folder that contains (and/or where will be stored) the calibration masters. If using data from different rigs, this variable needs to be changed as it will hold data for one rig (camera/filters/telescope) only.

### Executable scripts

Astro-Pipelines has two executable scrips.

- `astro-pipelines.py`: Main script giving access to all the package functions. See `--help` option for details.
- `platesolve.py`: Separate wrapper for the Astrometry.Net engine. Use for online platesolving and better control over the platesolving options (although in that last case I would recommend to use `solve-field` directly). See `--help` option for details.
