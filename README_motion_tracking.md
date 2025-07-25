# Motion Tracking Image Integration

This module provides functionality to integrate (stack) astronomical images while keeping moving objects static based on ephemeris information. This is particularly useful for tracking asteroids, comets, and other solar system objects.

## Overview

Traditional image stacking aligns images to a common WCS (World Coordinate System), which causes moving objects to appear as trails across the final stack. Motion tracking integration works differently:

1. **Calculate predicted positions**: For each image, calculate where the moving object should be based on its ephemeris
2. **Apply pixel shifts**: Shift each image so the moving object appears at the same pixel coordinates
3. **Stack the shifted images**: Integrate the shifted images using standard stacking algorithms

The result is a stacked image where the moving object appears as a single, sharp point while background stars appear as trails.

## Key Features

- **Ephemeris-based tracking**: Uses orbital elements to predict object positions
- **WCS-aware**: Properly handles coordinate transformations and pixel scales
- **Flexible integration**: Supports average, median, and sum stacking methods
- **Sigma clipping**: Built-in outlier rejection for robust stacking
- **Progress tracking**: Optional progress callbacks for GUI integration
- **Error handling**: Comprehensive error handling and validation

## Requirements

- `astropy` - For WCS handling and coordinate transformations
- `ccdproc` - For image processing and stacking
- `scipy` - For image shifting operations
- `numpy` - For numerical operations

## Usage

### Command Line Interface

The simplest way to use motion tracking integration is through the command-line script:

```bash
# Basic usage
python motion_stack.py "2025 BC" image1.fits image2.fits image3.fits

# With custom output and reference time
python motion_stack.py "2025 BC" *.fits --output stacked.fits --reference-time "2025-01-15T10:30:00"

# Use median stacking instead of average
python motion_stack.py "2025 BC" *.fits --method median

# Disable sigma clipping
python motion_stack.py "2025 BC" *.fits --no-sigma-clip

# Apply flat field scaling
python motion_stack.py "2025 BC" *.fits --flat-scale

# Use standard integration (no motion tracking) for comparison
python motion_stack.py "2025 BC" *.fits --standard
```

### Python API

For programmatic use, import the integration functions:

```python
from lib.fits.integration import integrate_with_motion_tracking, integrate_standard

# Motion tracking integration
result = integrate_with_motion_tracking(
    files=['image1.fits', 'image2.fits', 'image3.fits'],
    object_name='2025 BC',
    reference_time='2025-01-15T10:30:00',  # Optional
    method='average',
    sigma_clip=True,
    output_path='motion_tracked_stack.fits'
)

# Standard integration (for comparison)
result = integrate_standard(
    files=['image1.fits', 'image2.fits', 'image3.fits'],
    method='average',
    sigma_clip=True,
    output_path='standard_stack.fits'
)
```

### GUI Integration

The functions support progress callbacks for GUI integration:

```python
def progress_callback(progress):
    print(f"Progress: {progress*100:.1f}%")

result = integrate_with_motion_tracking(
    files=file_list,
    object_name=object_name,
    progress_callback=progress_callback
)
```

## How It Works

### 1. Ephemeris Prediction

For each image, the system:
- Extracts the observation time from the FITS header (`DATE-OBS`)
- Queries the Find_Orb online service for the object's predicted position
- Interpolates to the exact observation time if needed

### 2. Position Calculation

The system calculates the angular offset between the predicted position and a reference position:
- **Reference position**: Either the first image's position or a user-specified time
- **Angular offset**: Calculated in RA/Dec coordinates, accounting for cos(dec) factor
- **Pixel conversion**: Uses the image's WCS to convert angular offsets to pixel shifts

### 3. Image Shifting

Each image is shifted using bilinear interpolation:
- Positive shifts move the object toward the reference position
- The shift is applied to the entire image
- Background stars move relative to the tracked object

### 4. Integration

The shifted images are integrated using `ccdproc.combine()`:
- Supports average, median, and sum methods
- Optional sigma clipping for outlier rejection
- Optional scaling (e.g., for flat field correction)

## Example Workflow

Here's a complete example of processing a sequence of asteroid images:

```python
from lib.fits.integration import integrate_with_motion_tracking
from pathlib import Path

# Define your files and object
files = ['asteroid_001.fits', 'asteroid_002.fits', 'asteroid_003.fits']
object_name = '2025 BC'

# Check that all files have WCS information
for file_path in files:
    from astropy.io import fits
    header = fits.getheader(file_path)
    if 'CRVAL1' not in header:
        print(f"Warning: {file_path} may not be platesolved")

# Perform motion tracking integration
result = integrate_with_motion_tracking(
    files=files,
    object_name=object_name,
    method='average',
    sigma_clip=True,
    output_path='asteroid_stack.fits'
)

print(f"Integration complete! Object {object_name} should appear as a single point.")
```

## Comparison: Standard vs Motion Tracking

### Standard Integration
- Images aligned to common WCS
- Moving objects appear as trails
- Background stars appear as points
- Good for deep sky objects

### Motion Tracking Integration
- Images shifted to keep object static
- Moving objects appear as points
- Background stars appear as trails
- Good for solar system objects

## Supported Objects

The system can track any object with available ephemeris data:
- **Asteroids**: Numbered and provisional designations (e.g., "2025 BC", "C34UMY1")
- **Comets**: Periodic and non-periodic comets
- **Planets**: Major planets and their moons
- **Artificial satellites**: Earth-orbiting objects

## Error Handling

The system includes comprehensive error handling:
- **Missing ephemeris data**: Falls back to zero shift with warning
- **Invalid WCS**: Skips problematic images with warning
- **Network errors**: Handles temporary ephemeris service outages
- **File errors**: Continues processing with valid files

## Performance Considerations

- **Memory usage**: Large images may require significant memory
- **Processing time**: Ephemeris queries add overhead per image
- **Network dependency**: Requires internet access for ephemeris data
- **Parallel processing**: Consider processing in batches for large sequences

## Troubleshooting

### Common Issues

1. **"No ephemeris data found"**
   - Check object name spelling
   - Verify object has available ephemeris data
   - Try alternative object designations

2. **"No valid WCS in file"**
   - Ensure images are platesolved
   - Check for valid WCS keywords in headers

3. **"Sequence has inconsistencies"**
   - Review header consistency warnings
   - Consider using `--no-sigma-clip` for testing

4. **Large memory usage**
   - Process fewer images at once
   - Use smaller image regions if possible

### Debug Mode

Enable verbose output by setting the logging level:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Advanced Usage

### Custom Scaling Functions

You can provide custom scaling functions for special cases:

```python
def custom_scale(data):
    # Your custom scaling logic
    return scale_factor

result = integrate_with_motion_tracking(
    files=files,
    object_name=object_name,
    scale=custom_scale
)
```

### Reference Time Selection

Choose a specific reference time for the object position:

```python
# Use middle of observation sequence
reference_time = "2025-01-15T10:30:00"

result = integrate_with_motion_tracking(
    files=files,
    object_name=object_name,
    reference_time=reference_time
)
```

### Integration Methods

Different integration methods have different characteristics:

- **Average**: Best signal-to-noise, sensitive to outliers
- **Median**: Robust against outliers, lower signal-to-noise
- **Sum**: Preserves total flux, may saturate bright objects

## Future Enhancements

Planned improvements include:
- **Offline ephemeris**: Local ephemeris calculation without network dependency
- **Batch processing**: Parallel processing for large image sequences
- **GUI integration**: Full integration with the existing GUI
- **Advanced tracking**: Support for multiple objects in same field
- **Quality metrics**: Automatic assessment of tracking quality

## Contributing

To contribute to this module:
1. Follow the existing code style
2. Add comprehensive tests for new features
3. Update documentation for API changes
4. Test with real astronomical data

## License

This module is part of the astro-pipelines project and follows the same license terms. 