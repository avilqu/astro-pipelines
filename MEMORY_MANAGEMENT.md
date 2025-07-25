# Memory Management for Image Integration

## Overview

The astro-pipelines integration system now includes robust memory management features to prevent crashes when processing large numbers of FITS files. This is especially important when integrating hundreds or thousands of images that could consume gigabytes of RAM.

## Problem Solved

**Before**: The integration process loaded all images into memory simultaneously, which could cause:
- Memory shortage crashes
- System instability
- Inability to process large datasets
- Poor performance on systems with limited RAM

**After**: The new system uses chunked processing and configurable memory limits to:
- Process images in manageable batches
- Prevent memory crashes
- Handle datasets of any size
- Optimize performance for different system configurations

## Key Features

### 1. Automatic Chunked Processing

The system automatically switches to chunked processing when:
- Dataset size exceeds the configured chunk size (default: 10 images)
- Chunked processing is enabled in configuration

**How it works:**
1. Images are processed in chunks of configurable size
2. Each chunk is integrated separately
3. Chunk results are combined into final output
4. Memory is cleaned up between chunks

### 2. Configurable Memory Limits

- **Default memory limit**: 2GB (reduced from 6GB)
- **Configurable**: Can be set per integration call
- **ccdproc integration**: Uses the limit for internal memory management

### 3. Memory Cleanup

- Automatic garbage collection between chunks
- Explicit deletion of temporary arrays
- Reduced memory footprint during processing

## Configuration

### Global Settings (config.py)

```python
# Memory management settings for image integration
INTEGRATION_MEMORY_LIMIT = 2e9  # 2GB memory limit for integration (in bytes)
INTEGRATION_CHUNK_SIZE = 10     # Number of images to process in each chunk
INTEGRATION_ENABLE_CHUNKED = True  # Enable chunked processing for large datasets
```

### Per-Call Settings

You can override global settings for specific integrations:

```python
from lib.fits.integration import integrate_with_motion_tracking

# Custom memory settings
result = integrate_with_motion_tracking(
    files=files,
    object_name="2025 BC",
    memory_limit=1e9,    # 1GB limit
    chunk_size=5,        # 5 images per chunk
    force_chunked=True   # Force chunked processing
)
```

## Usage Examples

### Command Line Interface

```bash
# Use default memory management
python motion_stack.py "2025 BC" *.fits

# Custom memory limit (1GB)
python motion_stack.py "2025 BC" *.fits --memory-limit 1

# Custom chunk size
python motion_stack.py "2025 BC" *.fits --chunk-size 5

# Force chunked processing
python motion_stack.py "2025 BC" *.fits --force-chunked

# Combine multiple options
python motion_stack.py "2025 BC" *.fits --memory-limit 1 --chunk-size 5 --force-chunked
```

### Python API

```python
from lib.fits.integration import integrate_with_motion_tracking

# Standard integration with automatic memory management
result = integrate_with_motion_tracking(
    files=files,
    object_name="2025 BC"
)

# Custom memory settings
result = integrate_with_motion_tracking(
    files=files,
    object_name="2025 BC",
    memory_limit=1e9,      # 1GB
    chunk_size=5,          # 5 images per chunk
    force_chunked=True     # Force chunked processing
)

# Standard integration with memory management
from lib.fits.integration import integrate_standard

result = integrate_standard(
    files=files,
    memory_limit=1e9
)
```

## Performance Considerations

### Memory Usage

- **Small datasets** (< 10 images): Standard processing, minimal memory overhead
- **Large datasets** (> 10 images): Chunked processing, controlled memory usage
- **Memory limit**: Prevents ccdproc from exceeding specified memory usage

### Processing Time

- **Chunked processing**: Slightly slower due to multiple integration passes
- **Memory efficiency**: Better overall system performance
- **Scalability**: Can handle datasets of any size

### Recommended Settings

| System RAM | Memory Limit | Chunk Size | Use Case |
|------------|--------------|------------|----------|
| 4GB        | 1GB          | 5          | Small datasets |
| 8GB        | 2GB          | 10         | Medium datasets |
| 16GB+      | 4GB          | 20         | Large datasets |

## Monitoring and Debugging

### Progress Tracking

The system provides detailed progress information:

```
Integrating 50 images with chunked processing
Chunk size: 10 images
Memory limit: 2.0 GB

Processing chunk 1/5 (10 images)
  Processing 1/50: image_001.fits
    Applied shift: dx=1.23, dy=-0.45
  ...
  Integrating chunk 1 (10 images)...
✓ Integration complete
```

### Metadata

Integrated images include memory management metadata:

```python
# Check if chunked processing was used
chunked = result.meta.get('CHUNKED_PROCESSING', False)
total_chunks = result.meta.get('TOTAL_CHUNKS', 1)

print(f"Chunked processing: {chunked}")
print(f"Total chunks: {total_chunks}")
```

### Error Handling

The system gracefully handles memory-related errors:

- **Memory limit exceeded**: Automatically reduces chunk size
- **Individual chunk failures**: Continues with remaining chunks
- **Partial results**: Returns what was successfully processed

## Testing

Run the memory management test script:

```bash
python test_memory_management.py
```

This will test:
- Automatic chunked processing
- Custom memory settings
- Different dataset sizes
- Both motion tracking and standard integration

## Troubleshooting

### Common Issues

1. **"Memory limit exceeded"**
   - Reduce the memory limit
   - Decrease chunk size
   - Close other applications

2. **"Chunked processing not working"**
   - Check `INTEGRATION_ENABLE_CHUNKED` setting
   - Use `force_chunked=True` parameter
   - Verify dataset size > chunk size

3. **"Slow processing"**
   - Increase chunk size (if memory allows)
   - Increase memory limit
   - Use SSD storage for better I/O

### Performance Optimization

1. **For large datasets**: Use smaller chunks with higher memory limits
2. **For small datasets**: Disable chunked processing for speed
3. **For memory-constrained systems**: Use smaller chunks and lower memory limits

## Future Enhancements

Potential improvements include:
- **Adaptive chunk sizing**: Automatically adjust based on available memory
- **Parallel processing**: Process chunks in parallel (requires careful memory management)
- **Memory monitoring**: Real-time memory usage tracking
- **Disk-based processing**: Use memory-mapped files for very large datasets 