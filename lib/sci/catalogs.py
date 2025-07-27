import requests
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astropy import units as u
from astropy.wcs import WCS
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple, Union
import logging

from astroquery.simbad import Simbad

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
        try:
            result = Simbad.query_object(object_name)
            if result is not None:
                ra = result['ra'][0]   # already in degrees
                dec = result['dec'][0] # already in degrees
                return SIMBADObject(object_name, ra, dec, "Unknown")
            else:
                return None
        except Exception as e:
            logging.error(f"Astroquery SIMBAD error: {e}")
            return None

    def simbad_cone_search(self, ra: float, dec: float, radius: float, 
                          max_magnitude: float = 25.0) -> List[SIMBADObject]:
        """Perform a SIMBAD cone search for objects within a specified radius."""
        try:
            # Use basic SIMBAD query without extra fields to avoid hanging
            Simbad.reset_votable_fields()
            
            # Perform the cone search
            result = Simbad.query_region(
                SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame='icrs'),
                radius=radius*u.deg
            )
            
            if result is None or len(result) == 0:
                logging.info(f"No SIMBAD objects found in cone search at RA={ra:.4f}, Dec={dec:.4f}, radius={radius:.2f}°")
                return []
            
            objects = []
            for row in result:
                try:
                    name = row['main_id'] if 'main_id' in row.colnames else str(row['matched_id'])
                    obj_ra = row['ra']  # already in degrees
                    obj_dec = row['dec']  # already in degrees
                    obj_type = "Unknown"  # We'll get this from a separate query if needed
                    magnitude = None  # We'll get this from a separate query if needed
                    distance = None  # We'll get this from a separate query if needed
                    
                    simbad_obj = SIMBADObject(name, obj_ra, obj_dec, obj_type, magnitude, distance)
                    objects.append(simbad_obj)
                    logging.info(f"Found SIMBAD object: {simbad_obj}")
                    
                except Exception as e:
                    logging.warning(f"Error parsing SIMBAD object: {e}")
                    continue
            
            logging.info(f"Found {len(objects)} SIMBAD objects in cone search")
            return objects
            
        except Exception as e:
            logging.error(f"Error in SIMBAD cone search: {e}")
            return []

    def check_object_in_field(self, wcs: WCS, image_shape: Tuple[int, int], 
                             simbad_object: SIMBADObject) -> Tuple[bool, Optional[Tuple[float, float]]]:
        try:
            obj_coords = SkyCoord(ra=simbad_object.ra*u.deg, dec=simbad_object.dec*u.deg)
            pixel_result = wcs.world_to_pixel(obj_coords)
            if hasattr(pixel_result, '__len__') and len(pixel_result) == 2:
                pixel_x, pixel_y = pixel_result
            else:
                pixel_x, pixel_y = pixel_result[0], pixel_result[1]
            if (0 <= pixel_x <= image_shape[1] and 
                0 <= pixel_y <= image_shape[0]):
                logging.info(f"Object {simbad_object.name} is in field at pixel coordinates ({pixel_x:.1f}, {pixel_y:.1f})")
                return True, (float(pixel_x), float(pixel_y))
            else:
                logging.info(f"Object {simbad_object.name} is out of field (pixel coordinates: {pixel_x:.1f}, {pixel_y:.1f})")
                return False, None
        except Exception as e:
            logging.error(f"Error checking if object {simbad_object.name} is in field: {e}")
            return False, None
    def skybot_cone_search(self, ra: float, dec: float, radius: float, 
                          epoch: Time, max_magnitude: float = 25.0) -> List[SolarSystemObject]:
        try:
            epoch_str = epoch.iso
            params = {
                'RA': ra,
                'DEC': dec,
                'SR': radius,
                'EPOCH': epoch_str,
                'LOCATION': '500',
                'MAXMAG': max_magnitude,
                'FORMAT': 'xml'
            }
            logging.info(f"Performing Skybot search at RA={ra:.4f}, Dec={dec:.4f}, radius={radius:.2f}°")
            logging.info(f"Epoch: {epoch_str}")
            response = requests.get(self.skybot_url, params=params, timeout=30)
            response.raise_for_status()
            objects = self._parse_skybot_response(response.text)
            logging.info(f"Found {len(objects)} solar system objects")
            return objects
        except requests.exceptions.RequestException as e:
            logging.error(f"Error making Skybot request: {e}")
            return []
        except Exception as e:
            logging.error(f"Error in skybot_cone_search: {e}")
            return []
    def _parse_skybot_response(self, xml_content: str) -> List[SolarSystemObject]:
        objects = []
        try:
            root = ET.fromstring(xml_content)
            error_elements = root.findall('.//error')
            if error_elements:
                for error in error_elements:
                    logging.error(f"Skybot error: {error.text}")
                return []
            tabledata = root.find('.//{http://www.ivoa.net/xml/VOTable/v1.3}TABLEDATA')
            if tabledata is None:
                logging.warning("No TABLEDATA found in Skybot response")
                return []
            rows = tabledata.findall('.//{http://www.ivoa.net/xml/VOTable/v1.3}TR')
            for row in rows:
                try:
                    cells = row.findall('.//{http://www.ivoa.net/xml/VOTable/v1.3}TD')
                    if len(cells) < 15:
                        logging.warning(f"Row has insufficient columns: {len(cells)}")
                        continue
                    num = cells[0].text.strip() if cells[0].text else ""
                    name = cells[1].text.strip() if cells[1].text else ""
                    ra_str = cells[12].text.strip() if cells[12].text else "0.0"
                    dec_str = cells[13].text.strip() if cells[13].text else "0.0"
                    try:
                        ra = float(ra_str)
                        dec = float(dec_str)
                    except ValueError:
                        logging.warning(f"Invalid coordinates for {name}: RA={ra_str}, Dec={dec_str}")
                        continue
                    obj_type = cells[4].text.strip() if cells[4].text else "Unknown"
                    mag_str = cells[5].text.strip() if cells[5].text else "99.0"
                    try:
                        magnitude = float(mag_str)
                    except ValueError:
                        magnitude = 99.0
                    dist_str = cells[9].text.strip() if cells[9].text else ""
                    try:
                        distance = float(dist_str) if dist_str else None
                    except ValueError:
                        distance = None
                    motion_ra_str = cells[7].text.strip() if cells[7].text else "0.0"
                    motion_dec_str = cells[8].text.strip() if cells[8].text else "0.0"
                    try:
                        motion_ra = float(motion_ra_str)
                        motion_dec = float(motion_dec_str)
                        velocity = np.sqrt(motion_ra**2 + motion_dec**2)
                    except ValueError:
                        velocity = None
                    if num and num != "-":
                        full_name = f"{num} {name}"
                    else:
                        full_name = name
                    sso = SolarSystemObject(full_name, ra, dec, magnitude, obj_type, distance, velocity)
                    objects.append(sso)
                    logging.info(f"Parsed object: {sso}")
                except (ValueError, AttributeError, IndexError) as e:
                    logging.warning(f"Error parsing row in Skybot response: {e}")
                    continue
        except ET.ParseError as e:
            logging.error(f"Error parsing Skybot XML response: {e}")
            return []
        return objects
    def get_field_objects(self, wcs: WCS, image_shape: Tuple[int, int], 
                         epoch: Time, radius_buffer: float = 0.1) -> List[SolarSystemObject]:
        try:
            center_x = image_shape[1] / 2
            center_y = image_shape[0] / 2
            center_coords = wcs.pixel_to_world(center_x, center_y)
            ra_center = center_coords.ra.deg
            dec_center = center_coords.dec.deg
            corners = wcs.calc_footprint()
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
            logging.info(f"Field center: RA={ra_center:.4f}°, Dec={dec_center:.4f}°")
            logging.info(f"Search radius: {search_radius:.3f}°")
            objects = self.skybot_cone_search(ra_center, dec_center, search_radius, epoch)
            filtered_objects = []
            for obj in objects:
                try:
                    obj_coords = SkyCoord(ra=obj.ra*u.deg, dec=obj.dec*u.deg)
                    pixel_result = wcs.world_to_pixel(obj_coords)
                    if hasattr(pixel_result, '__len__') and len(pixel_result) == 2:
                        pixel_x, pixel_y = pixel_result
                    else:
                        pixel_x, pixel_y = pixel_result[0], pixel_result[1]
                    if (0 <= pixel_x <= image_shape[1] and 
                        0 <= pixel_y <= image_shape[0]):
                        filtered_objects.append(obj)
                        logging.info(f"Object in field: {obj}")
                except Exception as e:
                    logging.warning(f"Error checking if object {obj.name} is in field: {e}")
                    continue
            return filtered_objects
        except Exception as e:
            logging.error(f"Error getting field objects: {e}")
            return []
    def get_object_pixel_coordinates(self, wcs: WCS, objects: List[SolarSystemObject]) -> List[Tuple[SolarSystemObject, float, float]]:
        pixel_coords = []
        for obj in objects:
            try:
                obj_coords = SkyCoord(ra=obj.ra*u.deg, dec=obj.dec*u.deg)
                pixel_result = wcs.world_to_pixel(obj_coords)
                if hasattr(pixel_result, '__len__') and len(pixel_result) == 2:
                    pixel_x, pixel_y = pixel_result
                else:
                    pixel_x, pixel_y = pixel_result[0], pixel_result[1]
                pixel_coords.append((obj, float(pixel_x), float(pixel_y)))
            except Exception as e:
                logging.warning(f"Error converting coordinates for {obj.name}: {e}")
                continue
        return pixel_coords 

    def get_field_simbad_objects(self, wcs: WCS, image_shape: Tuple[int, int], 
                                radius_buffer: float = 0.1) -> List[SIMBADObject]:
        """Get SIMBAD objects in the field of view."""
        try:
            center_x = image_shape[1] / 2
            center_y = image_shape[0] / 2
            center_coords = wcs.pixel_to_world(center_x, center_y)
            ra_center = center_coords.ra.deg
            dec_center = center_coords.dec.deg
            
            # Calculate search radius based on image diagonal
            corners = wcs.calc_footprint()
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
            
            logging.info(f"SIMBAD field center: RA={ra_center:.4f}°, Dec={dec_center:.4f}°")
            logging.info(f"SIMBAD search radius: {search_radius:.3f}°")
            
            objects = self.simbad_cone_search(ra_center, dec_center, search_radius)
            
            # Filter objects to only those actually in the field
            filtered_objects = []
            for obj in objects:
                try:
                    obj_coords = SkyCoord(ra=obj.ra*u.deg, dec=obj.dec*u.deg)
                    pixel_result = wcs.world_to_pixel(obj_coords)
                    if hasattr(pixel_result, '__len__') and len(pixel_result) == 2:
                        pixel_x, pixel_y = pixel_result
                    else:
                        pixel_x, pixel_y = pixel_result[0], pixel_result[1]
                    if (0 <= pixel_x <= image_shape[1] and 
                        0 <= pixel_y <= image_shape[0]):
                        filtered_objects.append(obj)
                        logging.info(f"SIMBAD object in field: {obj}")
                except Exception as e:
                    logging.warning(f"Error checking if SIMBAD object {obj.name} is in field: {e}")
                    continue
            
            return filtered_objects
            
        except Exception as e:
            logging.error(f"Error getting field SIMBAD objects: {e}")
            return []

    def get_simbad_object_pixel_coordinates(self, wcs: WCS, objects: List[SIMBADObject]) -> List[Tuple[SIMBADObject, float, float]]:
        """Get pixel coordinates for a list of SIMBAD objects."""
        pixel_coords = []
        for obj in objects:
            try:
                obj_coords = SkyCoord(ra=obj.ra*u.deg, dec=obj.dec*u.deg)
                pixel_result = wcs.world_to_pixel(obj_coords)
                if hasattr(pixel_result, '__len__') and len(pixel_result) == 2:
                    pixel_x, pixel_y = pixel_result
                else:
                    pixel_x, pixel_y = pixel_result[0], pixel_result[1]
                pixel_coords.append((obj, float(pixel_x), float(pixel_y)))
            except Exception as e:
                logging.warning(f"Error converting coordinates for SIMBAD object {obj.name}: {e}")
                continue
        return pixel_coords 