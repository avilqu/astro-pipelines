import requests
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astropy import units as u
from astropy.wcs import WCS
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple
import logging
from astroquery.simbad import Simbad

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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