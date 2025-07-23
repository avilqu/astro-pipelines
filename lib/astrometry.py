import requests
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astropy import units as u
from astropy.wcs import WCS
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple, Union
import logging
import os
import time
from pathlib import Path
from subprocess import run, TimeoutExpired
import shutil
from colorama import Style, Fore

from astroquery.simbad import Simbad

# Import our FITS utilities
from .fits.wcs import (
    validate_fits_file, 
    ImageValidationResult, 
    get_platesolving_constraints,
    extract_wcs_from_file,
    apply_wcs_to_fits,
    WCSExtractionError,
    WCSApplicationError
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Disable all logging to avoid INFO: output
logging.disable(logging.CRITICAL)


class PlatesolvingError(Exception):
    """Exception raised when platesolving fails."""
    pass


class PlatesolvingResult:
    """Result of a platesolving operation."""
    
    def __init__(self, success: bool, message: str = "", 
                 wcs_file_path: Optional[str] = None,
                 ra_center: Optional[float] = None,
                 dec_center: Optional[float] = None,
                 pixel_scale: Optional[float] = None,
                 orientation: Optional[float] = None,
                 radius: Optional[float] = None,
                 objects_in_field: Optional[int] = None):
        self.success = success
        self.message = message
        self.wcs_file_path = wcs_file_path
        self.ra_center = ra_center
        self.dec_center = dec_center
        self.pixel_scale = pixel_scale
        self.orientation = orientation
        self.radius = radius
        self.objects_in_field = objects_in_field
    
    def __str__(self):
        status = "SUCCESS" if self.success else "FAILED"
        result = f"{status}: {self.message}"
        if self.success and self.ra_center and self.dec_center:
            result += f" (RA={self.ra_center:.4f}°, Dec={self.dec_center:.4f}°)"
        return result


class SolarSystemObject:
    """Class to represent a solar system object found in the field"""
    
    def __init__(self, name: str, ra: float, dec: float, magnitude: float, 
                 object_type: str, distance: float = None, velocity: float = None):
        self.name = name
        self.ra = ra  # degrees
        self.dec = dec  # degrees
        self.magnitude = magnitude
        self.object_type = object_type
        self.distance = distance  # AU
        self.velocity = velocity  # arcsec/hour
        
    def __str__(self):
        return f"{self.name} ({self.object_type}) - RA: {self.ra:.4f}°, Dec: {self.dec:.4f}°, Mag: {self.magnitude:.2f}"


class SIMBADObject:
    """Class to represent a SIMBAD object found in the field"""
    
    def __init__(self, name: str, ra: float, dec: float, object_type: str = "Unknown", 
                 magnitude: float = None, distance: float = None):
        self.name = name
        self.ra = ra  # degrees
        self.dec = dec  # degrees
        self.object_type = object_type
        self.magnitude = magnitude
        self.distance = distance  # parsecs
        
    def __str__(self):
        mag_str = f", Mag: {self.magnitude:.2f}" if self.magnitude is not None else ""
        dist_str = f", Dist: {self.distance:.1f}pc" if self.distance is not None else ""
        return f"{self.name} ({self.object_type}) - RA: {self.ra:.4f}°, Dec: {self.dec:.4f}°{mag_str}{dist_str}"


class AstrometryCatalog:
    """Class to handle catalog searches and astrometry operations"""
    
    def __init__(self):
        self.skybot_url = "http://vo.imcce.fr/webservices/skybot/skybotconesearch_query.php"
        self.simbad_url = "http://simbad.u-strasbg.fr/simbad/sim-id"
        
    def simbad_search(self, object_name: str) -> Optional[SIMBADObject]:
        """
        Search for an object in the SIMBAD database using astroquery
        """
        try:
            result = Simbad.query_object(object_name)
            if result is not None:
                ra = result['ra'][0]   # already in degrees
                dec = result['dec'][0] # already in degrees
                return SIMBADObject(object_name, ra, dec, "Unknown")
            else:
                return None
        except Exception as e:
            logger.error(f"Astroquery SIMBAD error: {e}")
            return None
    
    def check_object_in_field(self, wcs: WCS, image_shape: Tuple[int, int], 
                             simbad_object: SIMBADObject) -> Tuple[bool, Optional[Tuple[float, float]]]:
        """
        Check if a SIMBAD object is within the image field
        
        Parameters:
        -----------
        wcs : WCS
            World Coordinate System object
        image_shape : Tuple[int, int]
            Image dimensions (height, width)
        simbad_object : SIMBADObject
            The SIMBAD object to check
            
        Returns:
        --------
        Tuple[bool, Optional[Tuple[float, float]]]
            (is_in_field, pixel_coordinates) where pixel_coordinates is (x, y) if in field
        """
        try:
            # Convert object coordinates to pixel coordinates
            obj_coords = SkyCoord(ra=simbad_object.ra*u.deg, dec=simbad_object.dec*u.deg)
            pixel_result = wcs.world_to_pixel(obj_coords)
            
            # Handle both single coordinates and arrays
            if hasattr(pixel_result, '__len__') and len(pixel_result) == 2:
                pixel_x, pixel_y = pixel_result
            else:
                pixel_x, pixel_y = pixel_result[0], pixel_result[1]
            
            # Check if object is within image bounds
            if (0 <= pixel_x <= image_shape[1] and 
                0 <= pixel_y <= image_shape[0]):
                logger.info(f"Object {simbad_object.name} is in field at pixel coordinates ({pixel_x:.1f}, {pixel_y:.1f})")
                return True, (float(pixel_x), float(pixel_y))
            else:
                logger.info(f"Object {simbad_object.name} is out of field (pixel coordinates: {pixel_x:.1f}, {pixel_y:.1f})")
                return False, None
                
        except Exception as e:
            logger.error(f"Error checking if object {simbad_object.name} is in field: {e}")
            return False, None
    
    def skybot_cone_search(self, ra: float, dec: float, radius: float, 
                          epoch: Time, max_magnitude: float = 25.0) -> List[SolarSystemObject]:
        """
        Perform a Skybot cone search for solar system objects
        
        Parameters:
        -----------
        ra : float
            Right ascension in degrees
        dec : float
            Declination in degrees  
        radius : float
            Search radius in degrees
        epoch : Time
            Observation time
        max_magnitude : float
            Maximum magnitude to include in search
            
        Returns:
        --------
        List[SolarSystemObject]
            List of solar system objects found in the field
        """
        try:
            # Format the epoch for Skybot
            epoch_str = epoch.iso
            
            # Prepare the request parameters
            params = {
                'RA': ra,
                'DEC': dec,
                'SR': radius,
                'EPOCH': epoch_str,
                'LOCATION': '500',  # Geocentric
                'MAXMAG': max_magnitude,
                'FORMAT': 'xml'
            }
            
            logger.info(f"Performing Skybot search at RA={ra:.4f}, Dec={dec:.4f}, radius={radius:.2f}°")
            logger.info(f"Epoch: {epoch_str}")
            
            # Make the request
            response = requests.get(self.skybot_url, params=params, timeout=30)
            response.raise_for_status()
            
            # Parse the XML response
            objects = self._parse_skybot_response(response.text)
            
            logger.info(f"Found {len(objects)} solar system objects")
            return objects
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making Skybot request: {e}")
            return []
        except Exception as e:
            logger.error(f"Error in skybot_cone_search: {e}")
            return []
    
    def _parse_skybot_response(self, xml_content: str) -> List[SolarSystemObject]:
        """Parse the VOTable XML response from Skybot"""
        objects = []
        
        try:
            root = ET.fromstring(xml_content)
            
            # Check for error messages
            error_elements = root.findall('.//error')
            if error_elements:
                for error in error_elements:
                    logger.error(f"Skybot error: {error.text}")
                return []
            
            # Find the TABLEDATA section
            tabledata = root.find('.//{http://www.ivoa.net/xml/VOTable/v1.3}TABLEDATA')
            if tabledata is None:
                logger.warning("No TABLEDATA found in Skybot response")
                return []
            
            # Find all TR (table row) elements
            rows = tabledata.findall('.//{http://www.ivoa.net/xml/VOTable/v1.3}TR')
            
            for row in rows:
                try:
                    # Get all TD (table data) elements in the row
                    cells = row.findall('.//{http://www.ivoa.net/xml/VOTable/v1.3}TD')
                    
                    if len(cells) < 15:  # Expect at least 15 columns based on the VOTable structure
                        logger.warning(f"Row has insufficient columns: {len(cells)}")
                        continue
                    
                    # Extract data from cells (order matches the VOTable field definitions)
                    num = cells[0].text.strip() if cells[0].text else ""
                    name = cells[1].text.strip() if cells[1].text else ""
                    
                    # RA and Dec are in the hidden fields (columns 12 and 13)
                    ra_str = cells[12].text.strip() if cells[12].text else "0.0"
                    dec_str = cells[13].text.strip() if cells[13].text else "0.0"
                    
                    # Parse RA and Dec
                    try:
                        ra = float(ra_str)
                        dec = float(dec_str)
                    except ValueError:
                        logger.warning(f"Invalid coordinates for {name}: RA={ra_str}, Dec={dec_str}")
                        continue
                    
                    # Object classification
                    obj_type = cells[4].text.strip() if cells[4].text else "Unknown"
                    
                    # Magnitude
                    mag_str = cells[5].text.strip() if cells[5].text else "99.0"
                    try:
                        magnitude = float(mag_str)
                    except ValueError:
                        magnitude = 99.0
                    
                    # Distance from observer (AU)
                    dist_str = cells[9].text.strip() if cells[9].text else ""
                    try:
                        distance = float(dist_str) if dist_str else None
                    except ValueError:
                        distance = None
                    
                    # Motion (arcsec/hour) - combine RA and Dec motion
                    motion_ra_str = cells[7].text.strip() if cells[7].text else "0.0"
                    motion_dec_str = cells[8].text.strip() if cells[8].text else "0.0"
                    try:
                        motion_ra = float(motion_ra_str)
                        motion_dec = float(motion_dec_str)
                        velocity = np.sqrt(motion_ra**2 + motion_dec**2)
                    except ValueError:
                        velocity = None
                    
                    # Create object name (combine number and name)
                    if num and num != "-":
                        full_name = f"{num} {name}"
                    else:
                        full_name = name
                    
                    # Create SolarSystemObject
                    sso = SolarSystemObject(full_name, ra, dec, magnitude, obj_type, distance, velocity)
                    objects.append(sso)
                    logger.info(f"Parsed object: {sso}")
                    
                except (ValueError, AttributeError, IndexError) as e:
                    logger.warning(f"Error parsing row in Skybot response: {e}")
                    continue
                    
        except ET.ParseError as e:
            logger.error(f"Error parsing Skybot XML response: {e}")
            return []
        
        return objects
    
    def get_field_objects(self, wcs: WCS, image_shape: Tuple[int, int], 
                         epoch: Time, radius_buffer: float = 0.1) -> List[SolarSystemObject]:
        """
        Get solar system objects in the image field
        
        Parameters:
        -----------
        wcs : WCS
            World Coordinate System object
        image_shape : Tuple[int, int]
            Image dimensions (height, width)
        epoch : Time
            Observation time
        radius_buffer : float
            Additional buffer radius in degrees
            
        Returns:
        --------
        List[SolarSystemObject]
            List of solar system objects in the field
        """
        try:
            # Get the center of the image
            center_x = image_shape[1] / 2
            center_y = image_shape[0] / 2
            
            # Convert to sky coordinates (SkyCoord object)
            center_coords = wcs.pixel_to_world(center_x, center_y)
            ra_center = center_coords.ra.deg
            dec_center = center_coords.dec.deg
            
            # Calculate field radius using corners (floats)
            corners = wcs.calc_footprint()  # shape (N, 2), RA/Dec in degrees
            if corners is not None:
                max_radius = 0
                for corner_ra, corner_dec in corners:
                    dra = (corner_ra - ra_center) * np.cos(np.radians(dec_center))
                    ddec = corner_dec - dec_center
                    radius = np.sqrt(dra**2 + ddec**2)
                    max_radius = max(max_radius, radius)
                search_radius = max_radius + radius_buffer
            else:
                search_radius = 1.0 + radius_buffer
            
            logger.info(f"Field center: RA={ra_center:.4f}°, Dec={dec_center:.4f}°")
            logger.info(f"Search radius: {search_radius:.3f}°")
            
            # Perform the cone search
            objects = self.skybot_cone_search(ra_center, dec_center, search_radius, epoch)
            
            # Filter objects to only include those actually in the image
            filtered_objects = []
            for obj in objects:
                # Convert object coordinates to pixel coordinates
                try:
                    obj_coords = SkyCoord(ra=obj.ra*u.deg, dec=obj.dec*u.deg)
                    pixel_result = wcs.world_to_pixel(obj_coords)
                    if hasattr(pixel_result, '__len__') and len(pixel_result) == 2:
                        pixel_x, pixel_y = pixel_result
                    else:
                        pixel_x, pixel_y = pixel_result[0], pixel_result[1]
                    # Check if object is within image bounds
                    if (0 <= pixel_x <= image_shape[1] and 
                        0 <= pixel_y <= image_shape[0]):
                        filtered_objects.append(obj)
                        logger.info(f"Object in field: {obj}")
                except Exception as e:
                    logger.warning(f"Error checking if object {obj.name} is in field: {e}")
                    continue
            
            return filtered_objects
            
        except Exception as e:
            logger.error(f"Error getting field objects: {e}")
            return []
    
    def get_object_pixel_coordinates(self, wcs: WCS, objects: List[SolarSystemObject]) -> List[Tuple[SolarSystemObject, float, float]]:
        """
        Convert sky coordinates of objects to pixel coordinates
        
        Parameters:
        -----------
        wcs : WCS
            World Coordinate System object
        objects : List[SolarSystemObject]
            List of solar system objects
            
        Returns:
        --------
        List[Tuple[SolarSystemObject, float, float]]
            List of (object, x_pixel, y_pixel) tuples
        """
        pixel_coords = []
        
        for obj in objects:
            try:
                obj_coords = SkyCoord(ra=obj.ra*u.deg, dec=obj.dec*u.deg)
                pixel_result = wcs.world_to_pixel(obj_coords)
                
                # Handle both single coordinates and arrays
                if hasattr(pixel_result, '__len__') and len(pixel_result) == 2:
                    pixel_x, pixel_y = pixel_result
                else:
                    pixel_x, pixel_y = pixel_result[0], pixel_result[1]
                
                pixel_coords.append((obj, float(pixel_x), float(pixel_y)))
            except Exception as e:
                logger.warning(f"Error converting coordinates for {obj.name}: {e}")
                continue
        
        return pixel_coords 


class AstrometryEngine:
    """Interface to the astrometry.net solve-field engine."""
    
    def __init__(self, solve_field_path: str = "solve-field", 
                 output_dir: str = "/tmp/astropipes-solved", timeout: int = 300):
        """
        Initialize the astrometry engine interface.
        
        Parameters:
        -----------
        solve_field_path : str
            Path to the solve-field executable
        output_dir : str
            Directory for temporary output files
        timeout : int
            Timeout in seconds for solve-field execution
        """
        self.solve_field_path = solve_field_path
        self.output_dir = output_dir
        self.timeout = timeout
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
    
    def solve_image(self, fits_file_path: str, constraints: Dict[str, Union[float, bool]]) -> PlatesolvingResult:
        """
        Solve a single image using the astrometry.net engine.
        
        Parameters:
        -----------
        fits_file_path : str
            Path to the FITS file to solve
        constraints : Dict[str, Union[float, bool]]
            Solving constraints from get_platesolving_constraints()
            
        Returns:
        --------
        PlatesolvingResult
            Result of the solving operation
        """
        try:
            # Generate output filenames
            base_name = Path(fits_file_path).stem
            new_filename = os.path.join(self.output_dir, f"{base_name}.new")
            
            # Build solve-field command
            cmd = [
                self.solve_field_path,
                "--dir", self.output_dir,
                "--no-plots",
                "--no-verify",
                "--overwrite",
                "--downsample", "2",
                "--new-fits", new_filename,
                fits_file_path
            ]
            
            # Add constraints if not blind solving
            if not constraints.get('blind', True):
                if constraints.get('ra') is not None:
                    cmd.extend(["--ra", str(constraints['ra'])])
                if constraints.get('dec') is not None:
                    cmd.extend(["--dec", str(constraints['dec'])])
                if constraints.get('radius') is not None:
                    cmd.extend(["--radius", str(constraints['radius'])])
                # Note: solve-field doesn't use scale constraints for offline solving
                # Scale constraints are only used for online astrometry.net
            else:
                # Blind solving - add guess-scale option
                cmd.append("--guess-scale")
            
            # Debug: Show the exact command being executed
            print(f"   Command: {' '.join(cmd)}")
            
            # Run solve-field with live output
            start_time = time.time()
            print(f"{Style.BRIGHT + Fore.BLUE}Running solve-field...{Style.RESET_ALL}")
            result = run(cmd, check=True, timeout=self.timeout, text=True)
            solve_time = time.time() - start_time
            
            # Check if .new file was created
            if os.path.exists(new_filename):
                print(f"   Solution file generated: {new_filename}")
                
                # Extract solution information
                solution_info = self._extract_solution_info(new_filename, fits_file_path)
                
                # Don't clean up yet - the file is needed for WCS application
                # Cleanup will be done after WCS application in solve_single_image
                
                return PlatesolvingResult(
                    success=True,
                    message="Image successfully solved",
                    wcs_file_path=new_filename,
                    ra_center=solution_info.get('ra_center'),
                    dec_center=solution_info.get('dec_center'),
                    pixel_scale=solution_info.get('pixel_scale'),
                    orientation=solution_info.get('orientation'),
                    radius=solution_info.get('radius'),
                    objects_in_field=solution_info.get('objects_in_field')
                )
            else:
                print(f"   No solution file generated by solve-field")
                self._cleanup_temp_files(base_name)
                return PlatesolvingResult(
                    success=False,
                    message="No WCS solution generated"
                )
                
        except TimeoutExpired:
            logger.error(f"solve-field timed out after {self.timeout}s")
            self._cleanup_temp_files(Path(fits_file_path).stem)
            return PlatesolvingResult(
                success=False,
                message=f"solve-field timed out after {self.timeout}s"
            )
        except Exception as e:
            logger.error(f"Error running solve-field: {e}")
            self._cleanup_temp_files(Path(fits_file_path).stem)
            return PlatesolvingResult(
                success=False,
                message=f"Error running solve-field: {e}"
            )
    
    def _extract_solution_info(self, solution_file_path: str, original_file_path: str) -> Dict[str, Union[float, int]]:
        """
        Extract solution information from the solution file.
        
        Parameters:
        -----------
        solution_file_path : str
            Path to the generated solution file (.new)
        original_file_path : str
            Path to the original FITS file
            
        Returns:
        --------
        Dict[str, Union[float, int]]
            Dictionary containing solution information
        """
        try:
            # Import fits here to avoid import issues
            from astropy.io import fits
            
            # Extract WCS data from the solution file
            wcs_data = extract_wcs_from_file(solution_file_path)
            
            # Create WCS object for calculations
            wcs = WCS(solution_file_path)
            
            # Get image dimensions from original file
            with fits.open(original_file_path) as hdul:
                image_shape = hdul[0].data.shape
            
            # Calculate center coordinates
            center_x = image_shape[1] / 2
            center_y = image_shape[0] / 2
            center_coords = wcs.pixel_to_world(center_x, center_y)
            
            # Calculate pixel scale
            pixel_scale = None
            if 'CDELT1' in wcs_data:
                pixel_scale = abs(float(wcs_data['CDELT1'])) * 3600.0  # Convert to arcsec
            
            # Calculate orientation
            orientation = None
            if 'CROTA2' in wcs_data:
                orientation = float(wcs_data['CROTA2'])
            
            # Calculate field radius
            corners = wcs.calc_footprint()
            radius = None
            if corners is not None:
                ra_center = center_coords.ra.deg
                dec_center = center_coords.dec.deg
                max_radius = 0
                for corner_ra, corner_dec in corners:
                    dra = (corner_ra - ra_center) * np.cos(np.radians(dec_center))
                    ddec = corner_dec - dec_center
                    corner_radius = np.sqrt(dra**2 + ddec**2)
                    max_radius = max(max_radius, corner_radius)
                radius = max_radius
            
            return {
                'ra_center': center_coords.ra.deg,
                'dec_center': center_coords.dec.deg,
                'pixel_scale': pixel_scale,
                'orientation': orientation,
                'radius': radius,
                'objects_in_field': None  # Not available from solve-field output
            }
            
        except Exception as e:
            print(f"   Error extracting solution info: {e}")
            return {}
    
    def _cleanup_temp_files(self, base_name: str):
        """
        Clean up temporary files generated by solve-field.
        
        Parameters:
        -----------
        base_name : str
            Base name of the input file (without extension)
        """
        temp_extensions = ['.xyls', '.axy', '.corr', '.match', '.rdls', '.solved', '.new']
        
        for ext in temp_extensions:
            temp_file = os.path.join(self.output_dir, f"{base_name}{ext}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.debug(f"Cleaned up: {temp_file}")
                except Exception as e:
                    logger.warning(f"Could not remove {temp_file}: {e}")


def solve_single_image(fits_file_path: str, 
                      solve_field_path: str = "solve-field",
                      output_dir: str = "/tmp/astropipes-solved",
                      timeout: int = 300,
                      apply_solution: bool = True) -> PlatesolvingResult:
    """
    Solve a single FITS image using the complete platesolving pipeline.
    
    This function performs the complete platesolving workflow:
    1. Validate the FITS file
    2. Extract existing WCS information
    3. Generate solving constraints
    4. Run astrometry.net engine
    5. Apply solution to original file (if requested)
    
    Parameters:
    -----------
    fits_file_path : str
        Path to the FITS file to solve
    solve_field_path : str
        Path to the solve-field executable
    output_dir : str
        Directory for temporary output files
    timeout : int
        Timeout in seconds for solve-field execution
    apply_solution : bool
        Whether to apply the solution to the original FITS file
        
    Returns:
    --------
    PlatesolvingResult
        Result of the platesolving operation
    """
    try:
        # Step 1: Validate the FITS file
        print(f"{Style.BRIGHT + Fore.BLUE}Validating FITS file...{Style.RESET_ALL}")
        validation_result = validate_fits_file(fits_file_path)
        
        if not validation_result.is_valid:
            # Print error message in bold red
            print(f"{Style.BRIGHT + Fore.RED}Image validation failed: {validation_result.reason}{Style.RESET_ALL}")
            return PlatesolvingResult(
                success=False,
                message=f"Image validation failed: {validation_result.reason}"
            )
        
        print(f"{Style.BRIGHT + Fore.GREEN}Image validation passed{Style.RESET_ALL}")
        
        # Step 2: Extract existing WCS information and generate constraints
        print(f"{Style.BRIGHT + Fore.BLUE}Generating solving constraints...{Style.RESET_ALL}")
        constraints = get_platesolving_constraints(validation_result)
        
        # Step 3: Run astrometry.net engine
        print(f"{Style.BRIGHT + Fore.BLUE}Running astrometry.net engine...{Style.RESET_ALL}")
        engine = AstrometryEngine(solve_field_path, output_dir, timeout)
        solve_result = engine.solve_image(fits_file_path, constraints)
        
        if not solve_result.success:
            # Print error message in bold red
            print(f"{Style.BRIGHT + Fore.RED}Could not solve {fits_file_path}{Style.RESET_ALL}")
            return solve_result
        
        # Step 4: Apply solution to original file (if requested)
        if apply_solution and solve_result.wcs_file_path:
            print(f"{Style.BRIGHT + Fore.BLUE}Applying solution to original file...{Style.RESET_ALL}")
            try:
                wcs_data = extract_wcs_from_file(solve_result.wcs_file_path)
                apply_wcs_to_fits(fits_file_path, wcs_data, backup_original=False)
                print(f"   Successfully applied WCS solution to {fits_file_path}")
                
                # Clean up the solution file after applying
                os.remove(solve_result.wcs_file_path)
                solve_result.wcs_file_path = None
                
            except (WCSExtractionError, WCSApplicationError) as e:
                print(f"{Style.BRIGHT + Fore.RED}Error applying WCS solution: {e}{Style.RESET_ALL}")
                return PlatesolvingResult(
                    success=False,
                    message=f"Error applying WCS solution: {e}"
                )
        
        # Clean up any remaining temporary files
        base_name = Path(fits_file_path).stem
        engine._cleanup_temp_files(base_name)
        
        # Print success message in bold green
        print(f"{Style.BRIGHT + Fore.GREEN}Successfully solved {fits_file_path}{Style.RESET_ALL}")
        if solve_result.ra_center and solve_result.dec_center:
            print(f"{Style.BRIGHT + Fore.GREEN}   Center: RA={solve_result.ra_center:.4f}°, Dec={solve_result.dec_center:.4f}°{Style.RESET_ALL}")
        if solve_result.pixel_scale:
            print(f"{Style.BRIGHT + Fore.GREEN}   Pixel scale: {solve_result.pixel_scale:.3f} arcsec/pixel{Style.RESET_ALL}")
        
        return solve_result
        
    except Exception as e:
        print(f"{Style.BRIGHT + Fore.RED}Error in platesolving pipeline: {e}{Style.RESET_ALL}")
        return PlatesolvingResult(
            success=False,
            message=f"Error in platesolving pipeline: {e}"
        ) 