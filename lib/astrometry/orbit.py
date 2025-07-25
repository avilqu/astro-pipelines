import os
import requests
from typing import Any, List, Dict, Optional, Tuple
from datetime import datetime, timedelta
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

def compute_ephemeris(orbit_data: Dict[str, Any], date_obs: str) -> Tuple[float, float]:
    """
    Compute the geocentric apparent right-ascension and declination of a solar-system object
    for a given observation epoch using its osculating orbital elements.

    This implementation follows the classic ephemeris computation steps described in
    “Computation of an Ephemeris” (E. Myers, 2013) and is designed to provide reasonable
    accuracy (typically < 1′) for minor-planet predictions a few decades from the
    elements’ epoch.

    Parameters
    ----------
    orbit_data : Dict[str, Any]
        Dictionary returned by ``get_neofixer_orbit``.  The orbital elements are expected
        under the key ``"elements"`` and must at minimum contain the following keys:

        * ``a``        – semi-major axis [AU]
        * ``e``        – eccentricity
        * ``i``        – inclination [deg]
        * ``asc_node`` – longitude of ascending node Ω [deg]
        * ``arg_per``  – argument of perihelion ω [deg]
        * ``M``        – mean anomaly at epoch M₀ [deg]
        * ``epoch``    – epoch of elements (JD)

    date_obs : str
        Observation time in ISO format (e.g. ``'2025-01-22T11:35:43.182'``).

    Returns
    -------
    Tuple[float, float]
        A tuple ``(ra_deg, dec_deg)`` giving **geocentric** right ascension and
        declination in decimal degrees (ICRS, J2000).  RA is returned in the range
        0 ≤ RA < 360.
    """
    if not ASTROPY_AVAILABLE:
        raise ImportError("astropy is required for orbital calculations. Please install it with 'pip install astropy'.")

    try:
        # --- 1. Extract and prepare orbital elements ---------------------------------
        el = orbit_data["elements"]
        a_AU: float = el["a"]          # semi-major axis [AU]
        e: float = el["e"]             # eccentricity
        i_deg: float = el["i"]        # inclination [deg]
        omega_deg: float = el["arg_per"]   # argument of perihelion ω [deg]
        Omega_deg: float = el["asc_node"]  # longitude of ascending node Ω [deg]
        M0_deg: float = el["M"]        # mean anomaly at epoch [deg]
        epoch_jd: float = el["epoch"]  # epoch of elements (JD, TT)

        # --- 2. Compute mean anomaly at observation epoch ----------------------------
        # Gaussian gravitational constant k (√(GM☉)) in AU^{3/2}/day
        k = 0.01720209895  # IAU 1976 value
        n_rad_per_day = k / (a_AU ** 1.5)      # mean motion n [rad/day]

        # Observation epoch in Julian Date (TT assumed sufficiently close to UTC for minutes-level precision)
        t_obs = Time(date_obs, format="isot", scale="utc")
        jd_obs = t_obs.jd
        dt_days = jd_obs - epoch_jd

        M_rad = np.radians((M0_deg % 360.0)) + n_rad_per_day * dt_days
        M_rad = np.fmod(M_rad, 2.0 * np.pi)  # wrap into [0,2π)

        # --- 3. Solve Kepler's equation to obtain eccentric anomaly -------------------
        E_rad = _solve_kepler_equation_simple(M_rad, e)

        # --- 4. True anomaly and heliocentric distance --------------------------------
        sin_E2 = np.sin(E_rad / 2.0)
        cos_E2 = np.cos(E_rad / 2.0)

        # True anomaly f
        f_rad = 2.0 * np.arctan2(np.sqrt(1 + e) * sin_E2,
                                 np.sqrt(1 - e) * cos_E2 + 1e-15)  # avoid division by zero

        # heliocentric distance r [AU]
        r_AU = a_AU * (1 - e * np.cos(E_rad))

        # --- 5. Heliocentric state vector in orbital plane ----------------------------
        x_orb = r_AU * np.cos(f_rad)
        y_orb = r_AU * np.sin(f_rad)
        z_orb = 0.0

        # --- 6. Rotate into ecliptic coordinates -------------------------------------
        # Rotation sequence: argument of perihelion (ω) -> inclination (i) -> Ω
        cos_ω, sin_ω = np.cos(np.radians(omega_deg)), np.sin(np.radians(omega_deg))
        cos_i, sin_i = np.cos(np.radians(i_deg)), np.sin(np.radians(i_deg))
        cos_Omega, sin_Omega = np.cos(np.radians(Omega_deg)), np.sin(np.radians(Omega_deg))

        # 6a. ω
        x1 = x_orb * cos_ω - y_orb * sin_ω
        y1 = x_orb * sin_ω + y_orb * cos_ω
        z1 = z_orb
        # 6b. i
        x2 = x1
        y2 = y1 * cos_i
        z2 = y1 * sin_i
        # 6c. Ω
        x_ecl = x2 * cos_Omega - y2 * sin_Omega
        y_ecl = x2 * sin_Omega + y2 * cos_Omega
        z_ecl = z2

        # --- 7. Convert to equatorial (ICRS) coordinates -----------------------------
        epsilon_rad = np.radians(23.43928)  # obliquity of ecliptic (J2000)
        cos_eps, sin_eps = np.cos(epsilon_rad), np.sin(epsilon_rad)

        x_eq = x_ecl
        y_eq = y_ecl * cos_eps - z_ecl * sin_eps
        z_eq = y_ecl * sin_eps + z_ecl * cos_eps

        # --- 8. Compute geocentric vector -------------------------------------------
        # Earth barycentric position (AU) in ICRS at observation epoch
        earth_bary = get_body_barycentric_posvel("earth", t_obs)[0].xyz.to(u.AU).value  # numpy array length-3
        x_geo = x_eq - earth_bary[0]
        y_geo = y_eq - earth_bary[1]
        z_geo = z_eq - earth_bary[2]

        # --- 9. Convert to RA/Dec ----------------------------------------------------
        r_geo = np.sqrt(x_geo ** 2 + y_geo ** 2 + z_geo ** 2)
        ra_rad = np.arctan2(y_geo, x_geo)
        dec_rad = np.arcsin(z_geo / r_geo)

        ra_deg = np.degrees(ra_rad) % 360.0
        dec_deg = np.degrees(dec_rad)

        return ra_deg, dec_deg

    except KeyError as err:
        raise ValueError(f"Missing expected orbital element key: {err}")
    except Exception as exc:
        raise Exception(f"Failed to compute ephemeris: {exc}") 

def predict_position_findorb(object_designation: str, dates_obs: list):
    """
    Query Find_Orb online service for ephemeris and return interpolated positions for multiple dates.
    Args:
        object_designation (str): The object name (e.g., '2025 BC').
        dates_obs (list): List of observation dates/times in ISO format (e.g., ['2025-01-22T11:36:18', '2025-01-22T12:36:18']).
    Returns:
        dict: Dictionary with date_obs as keys and interpolated positions as values.
    """
    import requests
    from datetime import datetime
    import json
    
    if not dates_obs:
        return {}
    
    # Find the date range to cover all requested dates
    parsed_dates = []
    for date_obs in dates_obs:
        if 'T' in date_obs:
            obs_dt = datetime.fromisoformat(date_obs.replace('Z', '+00:00'))
        else:
            obs_dt = datetime.strptime(date_obs, '%Y-%m-%d %H:%M:%S')
        parsed_dates.append(obs_dt)
    
    # Use the middle date for the API call to ensure we get good coverage
    sorted_dates = sorted(parsed_dates)
    middle_date = sorted_dates[len(sorted_dates) // 2]
    
    # Calculate time span needed to cover all dates
    time_span = (sorted_dates[-1] - sorted_dates[0]).total_seconds() / 3600  # hours
    # Add some padding and ensure minimum coverage
    time_span = max(time_span + 2, 4)  # at least 4 hours coverage
    
    # Calculate number of steps needed (1 step per hour, minimum 6 steps)
    n_steps = max(int(time_span) + 2, 6)
    
    findorb_url = "https://www.projectpluto.com/cgi-bin/fo/fo_serve.cgi"
    data = {
        "TextArea": "",
        "obj_name": object_designation,
        "year": middle_date.strftime('%Y-%m-%dT%H:%M:%S'),
        "n_steps": str(n_steps),
        "stepsize": "1h",  # 1 hour steps
        "mpc_code": "R56",
        "faint_limit": "99",
        "ephem_type": "0",
        "sigmas": "on",
        "total_motion": "on",
        "element_center": "-2",
        "epoch": "",
        "resids": "0",
        "language": "e",
        "file_no": "3",  # JSON output
    }
    files = {
        "upfile": ("", b""),
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': 'https://www.projectpluto.com/fo.htm',
        'Accept': 'application/json, text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Origin': 'https://www.projectpluto.com',
        'Connection': 'keep-alive',
    }
    
    try:
        resp = requests.post(findorb_url, data=data, files=files, headers=headers, timeout=60)
        resp.raise_for_status()
        try:
            result_json = resp.json()
        except Exception as e:
            # Try to extract JSON from the response text even if resp.json() fails
            import re
            print(f"[DEBUG] resp.json() failed: {e}, attempting to extract JSON from text...")
            text = resp.text
            # Find the first '{' and last '}'
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1 and end > start:
                json_str = text[start:end+1]
                try:
                    result_json = json.loads(json_str)
                except Exception as e2:
                    print(f"[DEBUG] Failed to parse JSON from response text: {e2}")
                    print(text[:2000])
                    return {}
            else:
                print("[DEBUG] Could not find JSON object in response text.")
                print(text[:2000])
                return {}
        
        # Parse ephemeris entries
        if 'ephemeris' not in result_json or 'entries' not in result_json['ephemeris']:
            print("No ephemeris data found in response")
            return {}
        
        entries = result_json['ephemeris']['entries']
        if len(entries) < 2:
            print(f"Expected at least 2 ephemeris entries, got {len(entries)}")
            return {}
        
        # Convert entries to list and sort by time
        ephemeris_entries = []
        for key, entry in entries.items():
            time_str = entry.get('ISO_time', entry.get('Date', ''))
            try:
                if 'T' in time_str:
                    dt = datetime.strptime(time_str[:19], '%Y-%m-%dT%H:%M:%S')
                else:
                    dt = datetime.strptime(time_str[:16], '%Y-%m-%dT%H:%M')
                ephemeris_entries.append((dt, entry))
            except ValueError:
                print(f"[DEBUG] Could not parse time from entry: {time_str}")
                continue
        
        ephemeris_entries.sort(key=lambda x: x[0])  # Sort by datetime
        
        # Interpolate positions for each requested date
        results = {}
        for date_obs in dates_obs:
            if 'T' in date_obs:
                obs_dt = datetime.fromisoformat(date_obs.replace('Z', '+00:00'))
            else:
                obs_dt = datetime.strptime(date_obs, '%Y-%m-%d %H:%M:%S')
            
            # Find the two ephemeris entries that bracket the observation time
            before_entry = None
            after_entry = None
            
            for i, (ephem_dt, entry) in enumerate(ephemeris_entries):
                if ephem_dt <= obs_dt:
                    before_entry = (ephem_dt, entry)
                if ephem_dt >= obs_dt:
                    after_entry = (ephem_dt, entry)
                    break
            
            # If we don't have both before and after, use the closest available
            if before_entry is None and after_entry is not None:
                before_entry = after_entry
            elif after_entry is None and before_entry is not None:
                after_entry = before_entry
            elif before_entry is None and after_entry is None:
                print(f"[DEBUG] No ephemeris entries found for {date_obs}")
                continue
            
            # Interpolate between the two entries
            dt1, entry1 = before_entry
            dt2, entry2 = after_entry
            
            if dt1 == dt2:
                # No interpolation needed
                interpolated_result = entry1.copy()
            else:
                # Linear interpolation
                total_time_diff = (dt2 - dt1).total_seconds()
                obs_time_diff = (obs_dt - dt1).total_seconds()
                interpolation_factor = obs_time_diff / total_time_diff
                
                ra1 = float(entry1.get('RA', 0))
                ra2 = float(entry2.get('RA', 0))
                dec1 = float(entry1.get('Dec', 0))
                dec2 = float(entry2.get('Dec', 0))
                
                # Handle RA wrap-around
                if abs(ra2 - ra1) > 180:
                    if ra2 > ra1:
                        ra1 += 360
                    else:
                        ra2 += 360
                
                interpolated_ra = ra1 + interpolation_factor * (ra2 - ra1)
                interpolated_dec = dec1 + interpolation_factor * (dec2 - dec1)
                interpolated_ra = interpolated_ra % 360.0
                
                interpolated_result = entry1.copy()
                interpolated_result['RA'] = interpolated_ra
                interpolated_result['Dec'] = interpolated_dec
            
            interpolated_result['date_obs'] = date_obs
            interpolated_result['Date'] = obs_dt.strftime('%Y-%m-%d %H:%M:%S')
            results[date_obs] = interpolated_result
            
            print(f"Interpolated position at {obs_dt}: RA={interpolated_result['RA']:.6f}, Dec={interpolated_result['Dec']:.6f}")
        
        return results
        
    except Exception as e:
        print(f"Failed to query Find_Orb or parse JSON: {e}")
        if 'resp' in locals():
            print(resp.text[:2000])
        return {}


def test_findorb_ephemeris():
    """
    Test the Find_Orb ephemeris workflow for object '2025 BC' at a specific date.
    Prints the predicted RA/Dec and compares to expected values.
    """
    object_name = "2025 BC"
    date_obs = "2025-01-22T11:36:18.572"
    expected_ra_hms = "06:00:22.7"
    expected_dec_dms = "-37:34:08.2"
    from astropy.coordinates import Angle
    import astropy.units as u
    
    print(f"Testing Find_Orb ephemeris for {object_name} at {date_obs}")
    try:
        result = predict_position_findorb(object_name, [date_obs])
        if result and date_obs in result:
            entry = result[date_obs]
            ra_deg = entry.get('RA', 0.0)
            dec_deg = entry.get('Dec', 0.0)
            
            ra_angle = Angle(ra_deg, unit=u.deg)
            dec_angle = Angle(dec_deg, unit=u.deg)
            
            ra_hms = ra_angle.hms
            dec_dms = dec_angle.dms
            
            print(f"Predicted RA: {ra_angle.hms[0]:02.0f}:{ra_angle.hms[1]:02.0f}:{ra_angle.hms[2]:.1f}")
            print(f"Predicted Dec: {dec_angle.dms[0]:+03.0f}:{abs(dec_angle.dms[1]):02.0f}:{abs(dec_angle.dms[2]):.1f}")
            print(f"Expected RA: {expected_ra_hms}")
            print(f"Expected Dec: {expected_dec_dms}")
            
            # Convert expected values to degrees for comparison
            expected_ra_angle = Angle(expected_ra_hms, unit=u.hourangle)
            expected_dec_angle = Angle(expected_dec_dms, unit=u.deg)
            
            ra_diff = abs(ra_deg - expected_ra_angle.deg)
            dec_diff = abs(dec_deg - expected_dec_angle.deg)
            
            print(f"RA difference: {ra_diff:.3f} degrees")
            print(f"Dec difference: {dec_diff:.3f} degrees")
            
            # Allow for some tolerance (e.g., 0.1 degrees)
            tolerance = 0.1
            if ra_diff < tolerance and dec_diff < tolerance:
                print("Test PASSED: Predicted position matches expected values within tolerance")
            else:
                print("Test FAILED: Predicted position differs significantly from expected values")
        else:
            print("Test FAILED: Invalid response format")
    except Exception as e:
        print(f"Test FAILED: {e}") 