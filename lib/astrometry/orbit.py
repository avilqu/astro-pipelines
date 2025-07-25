import os
import requests
from typing import Any, List, Dict, Optional, Tuple
from datetime import datetime
import numpy as np

try:
    from mpcq import BigQueryMPCClient
except ImportError:
    BigQueryMPCClient = None

# Always import dataset IDs from config
from config import MPCQ_DATASET_ID, MPCQ_VIEWS_DATASET_ID

# Import astropy components for orbital calculations
try:
    from astropy import units as u
    from astropy.time import Time
    from astropy.coordinates import SkyCoord, EarthLocation
    from astropy.coordinates import get_body_barycentric_posvel
    from astropy.coordinates import solar_system_ephemeris
    from astropy.coordinates import GCRS, ICRS
    from astropy.coordinates import CartesianRepresentation, SphericalRepresentation
    from astropy.coordinates import HeliocentricMeanEcliptic
    import astropy.constants as const
    ASTROPY_AVAILABLE = True
except ImportError:
    ASTROPY_AVAILABLE = False

# def get_asteroid_observations(object_designation: str) -> List[Any]:
#     """
#     Query asteroid observations from the Minor Planet Center using the mpcq library.
#     Returns the raw list of observations as provided by mpcq.
#     
#     Args:
#         object_designation (str): The asteroid designation (e.g., '2025 BC').
#     Returns:
#         List[Any]: Raw list of observations from mpcq.
#     Raises:
#         ImportError: If mpcq is not installed.
#         Exception: For other errors during query.
#     """
#     if BigQueryMPCClient is None:
#         raise ImportError("mpcq library is not installed. Please install it with 'pip install mpcq'.")
#
#     try:
#         client = BigQueryMPCClient(dataset_id=MPCQ_DATASET_ID, views_dataset_id=MPCQ_VIEWS_DATASET_ID)
#         observations = client.query_observations([object_designation])
#         return observations
#     except Exception as e:
#         raise Exception(f"Failed to query observations for {object_designation}: {e}")

def test_neofixer_api() -> bool:
    """
    Test if the NEOfixer API is accessible and working.
    
    Returns:
        bool: True if API is working, False otherwise.
    """
    try:
        # Test the base API endpoint
        url = "https://neofixerapi.arizona.edu"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"NEOfixer API test failed: {e}")
        return False

def get_neofixer_observations(object_designation: str) -> List[Any]:
    """
    Query NEOCP observations using the NEOfixer API.
    Returns observations for objects on the Near Earth Object Confirmation Page.
    
    Args:
        object_designation (str): The NEOCP object designation (e.g., 'C34UMY1').
    Returns:
        List[Any]: List of observations from NEOCP via NEOfixer.
    Raises:
        Exception: For errors during query.
    """
    try:
        # NEOfixer observations API endpoint - returns text format
        url = "https://neofixerapi.arizona.edu/obs/"
        
        # Parameters for the request
        params = {
            'object': object_designation
        }
        
        # Make the request
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        # The API returns text format, not JSON
        observations_text = response.text
        
        if not observations_text.strip():
            return []
        
        # Parse the text observations into a list of lines
        # Each line represents one observation
        observations = []
        for line in observations_text.strip().split('\n'):
            if line.strip():
                observations.append(line.strip())
        
        return observations
        
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to query NEOCP observations for {object_designation}: {e}")
    except Exception as e:
        raise Exception(f"Error processing NEOCP data for {object_designation}: {e}")

def get_neocp_objects(site: str = 'R56', num: int = 40) -> List[Any]:
    """
    Get the current list of objects on the NEOCP using the NEOfixer API.
    Returns the list of NEOCP objects with their designations and basic information.
    
    Args:
        site (str): The NEOfixer telescope or site name (typically 3 character MPC code).
        num (int): Number of objects to retrieve.
    Returns:
        List[Any]: List of NEOCP objects.
    Raises:
        Exception: For errors during query.
    """
    try:
        # NEOfixer targets API endpoint
        url = "https://neofixerapi.arizona.edu/targets/"
        
        # Parameters for the request
        params = {
            'site': site,
            'num': num
        }
        
        # Make the request
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        # Parse the response
        data = response.json()
        
        # Check for errors in the response
        if 'error' in data:
            raise Exception(f"NEOfixer API error: {data['error']}")
        
        # Return the objects from the result
        result = data.get('result', {})
        objects = result.get('objects', {})
        
        # Convert the objects dictionary to a list
        return list(objects.values())
        
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to query NEOCP objects: {e}")
    except Exception as e:
        raise Exception(f"Error processing NEOCP objects data: {e}") 

def get_neofixer_orbit(object_designation: str) -> Dict[str, Any]:
    """
    Query orbital elements from NEOfixer API.
    Returns orbital elements for a given object.
    
    Args:
        object_designation (str): The NEOCP object designation (e.g., 'C34UMY1' or '2025 BC').
    Returns:
        Dict[str, Any]: Orbital elements and metadata from NEOfixer.
    Raises:
        Exception: For errors during query.
    """
    try:
        # NEOfixer orbit API endpoint
        url = "https://neofixerapi.arizona.edu/orbit/"
        
        # Parameters for the request
        params = {
            'object': object_designation
        }
        
        # Make the request
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        # Parse the JSON response
        data = response.json()
        
        # Check for errors in the response
        if 'error' in data:
            raise Exception(f"NEOfixer API error: {data['error']}")
        
        # Return the orbit data
        result = data.get('result', {})
        objects = result.get('objects', {})
        
        # Try to find the object - it might be returned under a different key
        found_object = None
        for obj_id, obj_data in objects.items():
            # Check if this object matches our designation
            if (obj_data.get('object') == object_designation or 
                obj_data.get('packed') == object_designation or
                obj_id == object_designation):
                found_object = obj_data
                break
        
        if found_object is None:
            # If not found, return the first object (API might return it under a different key)
            if objects:
                found_object = list(objects.values())[0]
                print(f"Warning: Object '{object_designation}' not found exactly, using returned object: {found_object.get('object', 'Unknown')}")
            else:
                raise Exception(f"Object {object_designation} not found in orbit data")
        
        return found_object
        
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to query orbit for {object_designation}: {e}")
    except Exception as e:
        raise Exception(f"Error processing orbit data for {object_designation}: {e}")

def predict_position_from_orbit(orbit_data: Dict[str, Any], date_obs: str) -> Tuple[float, float]:
    """
    Predict the RA and Dec of an object at a given time using orbital elements.
    
    Args:
        orbit_data (Dict[str, Any]): Orbital elements from NEOfixer API
        date_obs (str): Observation date/time in ISO format (e.g., '2025-01-15T10:30:00')
    
    Returns:
        Tuple[float, float]: (RA_degrees, Dec_degrees) in decimal degrees
    
    Raises:
        ImportError: If astropy is not available
        Exception: For calculation errors
    """
    if not ASTROPY_AVAILABLE:
        raise ImportError("astropy is required for orbital calculations. Please install it with 'pip install astropy'.")
    
    try:
        # Extract orbital elements
        elements = orbit_data['elements']
        
        # Get epoch and elements
        epoch_jd = elements['epoch']
        a = elements['a']  # Semi-major axis in AU
        e = elements['e']  # Eccentricity
        i = elements['i']  # Inclination in degrees
        arg_per = elements['arg_per']  # Argument of perihelion in degrees
        asc_node = elements['asc_node']  # Longitude of ascending node in degrees
        M = elements['M']  # Mean anomaly at epoch in degrees
        n = elements['n']  # Mean motion in degrees per day (provided by API)
        
        # Convert observation time to Julian Date
        obs_time = Time(date_obs, format='isot', scale='utc')
        obs_jd = obs_time.jd
        
        # Calculate time since epoch in days
        delta_t_days = obs_jd - epoch_jd
        
        # Calculate mean anomaly at observation time using provided mean motion
        M_obs_deg = M + n * delta_t_days
        
        # Normalize mean anomaly to [0, 360)
        M_obs_deg = M_obs_deg % 360.0
        
        # Convert to radians for calculations
        M_obs_rad = np.radians(M_obs_deg)
        
        # Solve Kepler's equation for eccentric anomaly
        E_rad = _solve_kepler_equation_simple(M_obs_rad, e)
        
        # Calculate true anomaly
        f_rad = 2 * np.arctan(np.sqrt((1 + e) / (1 - e)) * np.tan(E_rad / 2))
        
        # Calculate distance from Sun
        r = a * (1 - e * np.cos(E_rad))
        
        # Calculate heliocentric position in orbital plane
        x_orbit = r * np.cos(f_rad)
        y_orbit = r * np.sin(f_rad)
        z_orbit = 0.0
        
        # Transform to equatorial coordinates using standard orbital mechanics
        # Convert angles to radians
        arg_per_rad = np.radians(arg_per)
        i_rad = np.radians(i)
        asc_node_rad = np.radians(asc_node)
        
        # Standard orbital mechanics transformation matrix
        # First, rotate by argument of perihelion (ω)
        cos_w = np.cos(arg_per_rad)
        sin_w = np.sin(arg_per_rad)
        x1 = x_orbit * cos_w - y_orbit * sin_w
        y1 = x_orbit * sin_w + y_orbit * cos_w
        z1 = z_orbit
        
        # Then, rotate by inclination (i)
        cos_i = np.cos(i_rad)
        sin_i = np.sin(i_rad)
        x2 = x1
        y2 = y1 * cos_i - z1 * sin_i
        z2 = y1 * sin_i + z1 * cos_i
        
        # Finally, rotate by longitude of ascending node (Ω)
        cos_omega = np.cos(asc_node_rad)
        sin_omega = np.sin(asc_node_rad)
        x_eq = x2 * cos_omega - y2 * sin_omega
        y_eq = x2 * sin_omega + y2 * cos_omega
        z_eq = z2
        
        # Convert to spherical coordinates (heliocentric)
        r_mag = np.sqrt(x_eq**2 + y_eq**2 + z_eq**2)
        ra_helio_rad = np.arctan2(y_eq, x_eq)
        dec_helio_rad = np.arcsin(z_eq / r_mag)
        
        ra_helio_deg = np.degrees(ra_helio_rad)
        dec_helio_deg = np.degrees(dec_helio_rad)
        if ra_helio_deg < 0:
            ra_helio_deg += 360
        
        # Get Earth's position and apply parallax correction
        earth_pos = get_body_barycentric_posvel('earth', obs_time)[0]
        
        # Calculate geocentric position (heliocentric - Earth position)
        x_geo = x_eq - earth_pos.x.value
        y_geo = y_eq - earth_pos.y.value
        z_geo = z_eq - earth_pos.z.value
        
        # Convert to spherical coordinates (geocentric)
        r_geo = np.sqrt(x_geo**2 + y_geo**2 + z_geo**2)
        ra_geo_rad = np.arctan2(y_geo, x_geo)
        dec_geo_rad = np.arcsin(z_geo / r_geo)
        
        # Convert to degrees
        ra_geo_deg = np.degrees(ra_geo_rad)
        dec_geo_deg = np.degrees(dec_geo_rad)
        
        # Ensure RA is in [0, 360)
        if ra_geo_deg < 0:
            ra_geo_deg += 360
            
        return ra_geo_deg, dec_geo_deg
        
    except Exception as e:
        raise Exception(f"Error calculating position: {e}")

def _solve_kepler_equation_simple(M: float, e: float, tolerance: float = 1e-8, max_iterations: int = 100) -> float:
    """
    Solve Kepler's equation M = E - e*sin(E) for eccentric anomaly E.
    
    Args:
        M: Mean anomaly in radians
        e: Eccentricity
        tolerance: Convergence tolerance
        max_iterations: Maximum number of iterations
    
    Returns:
        Eccentric anomaly E in radians
    """
    # Initial guess: E = M
    E = M
    
    for _ in range(max_iterations):
        E_new = M + e * np.sin(E)
        if abs(E_new - E) < tolerance:
            return E_new
        E = E_new
    
    raise Exception("Kepler equation did not converge") 