#!/usr/bin/env python3
"""
Test the file path generation for motion tracking output.
"""

import os
import time
from pathlib import Path

def test_file_path_generation():
    """Test the file path generation logic."""
    
    # Test parameters
    object_name = "2025 BC"
    
    # Create output directory if it doesn't exist
    output_dir = "/tmp/astropipes-stacked"
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate output filename
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_object_name = object_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
    output_file = os.path.join(output_dir, f"motion_tracked_{safe_object_name}_{timestamp}.fits")
    
    print(f"Object name: {object_name}")
    print(f"Safe object name: {safe_object_name}")
    print(f"Output directory: {output_dir}")
    print(f"Output file: {output_file}")
    
    # Check if directory exists
    if os.path.exists(output_dir):
        print(f"✓ Output directory exists: {output_dir}")
    else:
        print(f"✗ Output directory does not exist: {output_dir}")
    
    # Test with different object names
    test_objects = [
        "2025 BC",
        "C/2023 A3",
        "1P/Halley",
        "Object with spaces",
        "Object/with/slashes",
        "Object\\with\\backslashes"
    ]
    
    print("\nTesting different object names:")
    for obj in test_objects:
        safe_name = obj.replace(' ', '_').replace('/', '_').replace('\\', '_')
        test_file = os.path.join(output_dir, f"motion_tracked_{safe_name}_{timestamp}.fits")
        print(f"  '{obj}' -> '{safe_name}' -> {test_file}")
    
    return True

if __name__ == "__main__":
    test_file_path_generation() 