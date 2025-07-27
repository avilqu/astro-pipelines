#!.venv/bin/python

"""Methods for online and offline Astrometry.net engine.
@author: Adrien Vilquin Barrajon <avilqu@gmail.com>
"""


import sys
import os
import json
import time
import urllib.request
from pathlib import Path
from subprocess import run, TimeoutExpired
from colorama import Style, Fore
import signal

import requests
from astropy.io import fits
from astropy.wcs import WCS

import config


class SolverTimeoutError(Exception):
    """Custom exception for solver timeouts."""
    pass


# Global flag to track if solving should be interrupted
_solver_interrupted = False


def set_solver_interrupted(interrupted=True):
    """Set the solver interruption flag."""
    global _solver_interrupted
    _solver_interrupted = interrupted


def is_solver_interrupted():
    """Check if solver should be interrupted."""
    return _solver_interrupted


def timeout_handler(signum, frame):
    """Signal handler for timeout."""
    raise SolverTimeoutError("Solver operation timed out")


def validate_image_for_solving(filename):
    """
    Validate if an image is likely to be solvable.
    
    Parameters:
    -----------
    filename : str
        Path to the FITS file to validate
        
    Returns:
    --------
    tuple : (is_valid, reason)
        is_valid: bool indicating if image should be attempted
        reason: str explaining why image was rejected (if applicable)
    """
    print(f"{Style.BRIGHT}Validating image: {filename}{Style.RESET_ALL}")
    
    try:
        with fits.open(filename) as hdu:
            # Check if file has valid data
            if len(hdu) == 0:
                print(f"{Style.BRIGHT + Fore.RED}Validation failed: No HDUs found in file{Style.RESET_ALL}")
                return False, "No HDUs found in file"
                
            data = hdu[0].data
            if data is None:
                print(f"{Style.BRIGHT + Fore.RED}Validation failed: No data found in primary HDU{Style.RESET_ALL}")
                return False, "No data found in primary HDU"
                
            # Check image dimensions
            if len(data.shape) != 2:
                print(f"{Style.BRIGHT + Fore.RED}Validation failed: Expected 2D image, got {len(data.shape)}D{Style.RESET_ALL}")
                return False, f"Expected 2D image, got {len(data.shape)}D"
                
            height, width = data.shape
            if height < 100 or width < 100:
                print(f"{Style.BRIGHT + Fore.RED}Validation failed: Image too small: {width}x{height} pixels{Style.RESET_ALL}")
                return False, f"Image too small: {width}x{height} pixels"
                
            # Check for reasonable data range (not all zeros or all same value)
            data_min = data.min()
            data_max = data.max()
            data_mean = data.mean()
            data_std = data.std()
            
            print(f"  Image stats: {width}x{height}, min={data_min:.1f}, max={data_max:.1f}, mean={data_mean:.1f}, std={data_std:.2f}")
            
            if data_min == data_max:
                print(f"{Style.BRIGHT + Fore.RED}Validation failed: Image has no contrast (all pixels same value){Style.RESET_ALL}")
                return False, "Image has no contrast (all pixels same value)"
                
            if data_std < 1.0:
                print(f"{Style.BRIGHT + Fore.RED}Validation failed: Image has very low contrast (std={data_std:.2f}){Style.RESET_ALL}")
                return False, f"Image has very low contrast (std={data_std:.2f})"
                
            # Check for reasonable signal-to-noise (rough estimate)
            if data_mean < 10 or data_max < 50:
                print(f"{Style.BRIGHT + Fore.RED}Validation failed: Image appears too dark (mean={data_mean:.1f}, max={data_max:.1f}){Style.RESET_ALL}")
                return False, f"Image appears too dark (mean={data_mean:.1f}, max={data_max:.1f})"
                
            print(f"{Style.BRIGHT + Fore.GREEN}Validation passed: Image appears valid for solving{Style.RESET_ALL}")
            return True, "Image appears valid for solving"
            
    except Exception as e:
        print(f"{Style.BRIGHT + Fore.RED}Validation failed: Error reading file: {e}{Style.RESET_ALL}")
        return False, f"Error reading file: {e}"


def apply_wcs_to_file(original_file, wcs_file):
    """Apply WCS headers from a WCS file to the original FITS file."""
    
    try:
        # Read the WCS file
        wcs_hdu = fits.open(wcs_file)
        wcs_header = wcs_hdu[0].header
        
        print(f"WCS file contains {len(wcs_header)} header cards")
        print("Available WCS keywords in WCS file:")
        wcs_keywords_in_file = [k for k in wcs_header.keys() if any(wcs_key in k for wcs_key in ['CRPIX', 'CRVAL', 'CD', 'CTYPE', 'CUNIT', 'CDELT', 'CROTA', 'PC'])]
        for k in wcs_keywords_in_file:
            print(f"  {k}: {wcs_header[k]}")
        
        # Read the original file
        original_hdu = fits.open(original_file, mode='update')
        
        # First, remove any existing WCS keywords that might conflict
        wcs_keywords_to_remove = ['CRPIX1', 'CRPIX2', 'CRVAL1', 'CRVAL2', 'CD1_1', 'CD1_2', 'CD2_1', 'CD2_2',
                                 'CTYPE1', 'CTYPE2', 'CUNIT1', 'CUNIT2', 'LONPOLE', 'LATPOLE',
                                 'PC1_1', 'PC1_2', 'PC2_1', 'PC2_2', 'CDELT1', 'CDELT2', 'CROTA1', 'CROTA2']
        
        for keyword in wcs_keywords_to_remove:
            if keyword in original_hdu[0].header:
                del original_hdu[0].header[keyword]
        
        # Update the WCS keywords in the original file
        # Standard WCS keywords that should be copied
        wcs_keywords = ['CRPIX1', 'CRPIX2', 'CRVAL1', 'CRVAL2', 'CD1_1', 'CD1_2', 'CD2_1', 'CD2_2',
                       'CTYPE1', 'CTYPE2', 'CUNIT1', 'CUNIT2', 'LONPOLE', 'LATPOLE',
                       'PC1_1', 'PC1_2', 'PC2_1', 'PC2_2', 'CDELT1', 'CDELT2', 'CROTA1', 'CROTA2']
        
        keywords_updated = 0
        for keyword in wcs_keywords:
            if keyword in wcs_header:
                original_hdu[0].header[keyword] = wcs_header[keyword]
                keywords_updated += 1
                print(f"  Updated {keyword}: {wcs_header[keyword]}")
        
        # Add a comment indicating the file was plate solved
        original_hdu[0].header['HISTORY'] = 'Plate solved with astrometry.net'
        
        # Save the updated file
        original_hdu.flush()
        original_hdu.close()
        wcs_hdu.close()
        
        print(f"Updated {keywords_updated} WCS headers in {original_file}")
        
    except Exception as e:
        print(f"Error applying WCS to {original_file}: {e}")
        # Make sure to close files even if there's an error
        try:
            if 'original_hdu' in locals():
                original_hdu.close()
            if 'wcs_hdu' in locals():
                wcs_hdu.close()
        except:
            pass


def apply_wcs_from_astrometry_net(original_file, jobid):
    """Apply WCS solution from Astrometry.net to the original file."""
    
    # Download the WCS file from Astrometry.net
    wcs_url = f"http://nova.astrometry.net/wcs_file/{jobid}"
    wcs_filename = f"temp_wcs_{jobid}.wcs"
    
    try:
        print(f"Downloading WCS solution for {original_file}...")
        urllib.request.urlretrieve(wcs_url, wcs_filename)
        apply_wcs_to_file(original_file, wcs_filename)
        # Clean up temporary WCS file
        os.remove(wcs_filename)
        print(f"Successfully applied WCS solution to {original_file}")
    except Exception as e:
        print(f"Error applying WCS to {original_file}: {e}")
        # Clean up temporary file if it exists
        if os.path.exists(wcs_filename):
            try:
                os.remove(wcs_filename)
            except:
                pass


def open_session(key):
    """Opens HTTP session with Astrometry.net server."""

    request_json = json.dumps({"apikey": key})
    try:
        r = requests.post(
            "http://nova.astrometry.net/api/login",
            data={"request-json": request_json},
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        print(f"Error opening session: {e}")
        return None
    if r.json()["status"] == "success":
        print(
            time.strftime("%x %X")
            + " | Opened connection. Session ID: "
            + r.json()["session"]
        )
        return r.json()
    else:
        print("\n===================================")
        print(time.strftime("%x %X") + " | E: " + r.json()["errormessage"])
        print("===================================\n")
        return None


def submit_file(filename, key, options):
    """Sends image file to Astrometry.net server."""

    request_json = {
        "session": key,
        "publicly_visible": "n",
        "allow_modifications": "n",
        "allow_commercial_use": "n",
    }

    if options.ra:
        request_json["center_ra"] = options.ra
    if options.dec:
        request_json["center_dec"] = options.dec
    if options.radius:
        request_json["radius"] = options.radius
    if options.scaleEst:
        request_json["scale_est"] = options.scaleEst
    if options.scaleErr:
        request_json["scale_err"] = options.scaleErr

    try:
        r = requests.post(
            "http://nova.astrometry.net/api/upload",
            files=[
                (
                    "request-json",
                    (None, json.dumps(request_json), "text/plain"),
                ),
                (
                    "file",
                    (
                        filename,
                        open(filename, "rb"),
                        "application/octet-stream",
                    ),
                ),
            ],
            timeout=60,  # Longer timeout for file upload
        )
    except requests.exceptions.RequestException as e:
        print(f"Error submitting file: {e}")
        raise
    if r.json()["status"] == "success":
        print(
            time.strftime("%x %X")
            + " | File "
            + filename
            + " sent with options:"
        )
        print(request_json)
        return r.json()
    else:
        print("\n===================================")
        print(time.strftime("%x %X") + " | E: " + r.json()["errormessage"])
        print("===================================\n")
        raise Exception(f"Failed to submit file: {r.json()['errormessage']}")


def get_submission_status(subid):
    """Monitors file submission status from Astrometry.net server."""

    url = "http://nova.astrometry.net/api/submissions/" + str(subid)
    try:
        r = requests.post(url, timeout=30)  # Add timeout to prevent hanging
    except requests.exceptions.RequestException as e:
        print(f"Error checking submission status: {e}")
        return None
    return r.json()


def get_job_status(jobid):
    """Monitors job status from Astrometry.net server."""

    url = "http://nova.astrometry.net/api/jobs/" + str(jobid)
    try:
        r = requests.post(url, timeout=30)  # Add timeout to prevent hanging
    except requests.exceptions.RequestException as e:
        print(f"Error checking job status: {e}")
        return None
    return r.json()


def get_job_results(jobid, original_filename):
    """Get job results from Astrometry.net server and apply WCS to original file."""

    try:
        r = requests.post(
            "http://nova.astrometry.net/api/jobs/" + str(jobid) + "/info",
            timeout=30,
        ).json()
    except requests.exceptions.RequestException as e:
        print(f"Error getting job results: {e}")
        raise
    print("\n===================================")
    print("Image solved ! (" + time.strftime("%x %X") + ")")
    print("Filename: " + r["original_filename"])
    print("RA: " + str(r["calibration"]["ra"]))
    print("DEC: " + str(r["calibration"]["dec"]))
    print("Radius: " + str(r["calibration"]["radius"]))
    print("Orientation: " + str(r["calibration"]["orientation"]))
    print("Pixel scale: " + str(r["calibration"]["pixscale"]))
    print("Objects in field: " + str(r["objects_in_field"]))
    print("===================================\n")
    
    # Apply WCS to the original file instead of downloading a new one
    apply_wcs_from_astrometry_net(original_filename, jobid)


def solve_online(options, key):
    """Wrapper function for the whole online solving process."""

    session_data = open_session(key)
    if session_data is None:
        print(f"{Style.BRIGHT}Failed to open session with Astrometry.net{Style.RESET_ALL}")
        return
        
    session = session_data["session"]
    i = 1
    for filename in options.files:
        count = str(i) + "/" + str(len(options.files))
        print(f"\n{Style.BRIGHT}Processing {count}: {filename}{Style.RESET_ALL}")
        
        # Validate image before attempting to solve
        if config.SOLVER_VALIDATE_IMAGES:
            is_valid, reason = validate_image_for_solving(filename)
            if not is_valid:
                print(f"{Style.BRIGHT}Skipping {filename}: {reason}{Style.RESET_ALL}")
                i += 1
                continue
        
        # Submit file
        try:
            subid = submit_file(filename, session, options)["subid"]
        except Exception as e:
            print(f"{Style.BRIGHT}Error submitting {filename}: {e}{Style.RESET_ALL}")
            i += 1
            continue
        
        # Wait for job to start with timeout
        start_time = time.time()
        sub_status = get_submission_status(subid)
        while (sub_status is None or 
               sub_status.get("jobs") == [] or 
               sub_status.get("jobs") == [None]):
            
            if time.time() - start_time > config.SOLVER_ONLINE_TIMEOUT:
                print(f"{Style.BRIGHT}Timeout waiting for job {count} to start{Style.RESET_ALL}")
                break
                
            print(
                time.strftime("%x %X")
                + " | Waiting for job "
                + count
                + " to start..."
            )
            time.sleep(config.SOLVER_ONLINE_POLL_INTERVAL)
            sub_status = get_submission_status(subid)
            
        if sub_status is None or sub_status.get("jobs") == [] or sub_status.get("jobs") == [None]:
            print(f"{Style.BRIGHT}Failed to start job for {filename}{Style.RESET_ALL}")
            i += 1
            continue
            
        print(time.strftime("%x %X") + " | Job " + count + " has started.")
        jobid = sub_status["jobs"][0]
        
        # Monitor job status with timeout
        start_time = time.time()
        job_status = get_job_status(jobid)
        while job_status is not None and job_status.get("status") == "solving":
            
            if time.time() - start_time > config.SOLVER_ONLINE_TIMEOUT:
                print(f"{Style.BRIGHT}Timeout solving {filename}{Style.RESET_ALL}")
                break
                
            print(
                time.strftime("%x %X")
                + " | Status: "
                + job_status.get("status", "unknown")
                + " image "
                + count
            )
            time.sleep(config.SOLVER_ONLINE_POLL_INTERVAL)
            job_status = get_job_status(jobid)
            
        if job_status is None:
            print(f"{Style.BRIGHT}Error checking job status for {filename}{Style.RESET_ALL}")
            i += 1
            continue
            
        if job_status.get("status") == "success":
            try:
                get_job_results(jobid, filename)
                print(f"{Style.BRIGHT}Successfully solved {filename}{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Style.BRIGHT}Error applying solution to {filename}: {e}{Style.RESET_ALL}")
        else:
            print(f"\n{Style.BRIGHT}Failed to solve {filename} - Status: {job_status.get('status', 'unknown')}{Style.RESET_ALL}")
            
        i += 1


def solver_cleanup():
    """Delete all the temporary files generated by solve-field."""

    solved_directory = "./solved"

    solver_files = os.listdir(solved_directory)
    xyls_files = [file for file in solver_files if file.endswith(".xyls")]
    axy_files = [file for file in solver_files if file.endswith(".axy")]
    corr_files = [file for file in solver_files if file.endswith(".corr")]
    match_files = [file for file in solver_files if file.endswith(".match")]
    rdls_files = [file for file in solver_files if file.endswith(".rdls")]
    solved_files = [file for file in solver_files if file.endswith(".solved")]
    wcs_files = [file for file in solver_files if file.endswith(".wcs")]

    for file in xyls_files:
        file_path = os.path.join(solved_directory, file)
        os.remove(file_path)

    for file in axy_files:
        file_path = os.path.join(solved_directory, file)
        os.remove(file_path)

    for file in corr_files:
        file_path = os.path.join(solved_directory, file)
        os.remove(file_path)

    for file in match_files:
        file_path = os.path.join(solved_directory, file)
        os.remove(file_path)

    for file in rdls_files:
        file_path = os.path.join(solved_directory, file)
        os.remove(file_path)

    for file in solved_files:
        file_path = os.path.join(solved_directory, file)
        os.remove(file_path)

    # Note: .wcs files are now cleaned up immediately after use in the solving functions
    # This cleanup is kept for any remaining .wcs files that might exist
    for file in wcs_files:
        file_path = os.path.join(solved_directory, file)
        os.remove(file_path)


def solve_offline(options):
    """Wrapper function for the offline solve-field CLI."""

    downsample = 1

    if options.downsample:
        downsample = str(options.downsample)
    if options.ra:
        ra = str(options.ra)
    if options.dec:
        dec = str(options.dec)
    if options.radius:
        radius = str(options.radius)

    if options.blind:
        for filename in options.files:
            # Check if solving should be interrupted
            if is_solver_interrupted():
                print(f"{Style.BRIGHT}Solver interrupted by user.{Style.RESET_ALL}")
                raise KeyboardInterrupt("Solver interrupted by user")
                
            print(f"\n{Style.BRIGHT}Solving {filename}.{Style.RESET_ALL}")

            # Validate image before attempting to solve
            if config.SOLVER_VALIDATE_IMAGES:
                print(f"{Style.BRIGHT}Image validation is enabled.{Style.RESET_ALL}")
                is_valid, reason = validate_image_for_solving(filename)
                if not is_valid:
                    print(f"{Style.BRIGHT}Skipping {filename}: {reason}{Style.RESET_ALL}")
                    continue
            else:
                print(f"{Style.BRIGHT}Image validation is disabled.{Style.RESET_ALL}")

            # Generate WCS filename
            base_name = Path(filename).stem
            wcs_filename = f"solved/{base_name}.wcs"
            
            try:
                proc = run(
                    [
                        "solve-field",
                        "--dir",
                        "solved",
                        "--no-plots",
                        "--no-verify",
                        "--overwrite",
                        "--downsample",
                        str(downsample),
                        "--wcs",
                        wcs_filename,
                        filename,
                    ],
                    check=True,
                    timeout=config.SOLVER_OFFLINE_TIMEOUT,
                )
                print(f"Solver arguments: {proc.args}")
                
                # Apply WCS to original file
                if os.path.exists(wcs_filename):
                    apply_wcs_to_file(filename, wcs_filename)
                    # Clean up WCS file
                    os.remove(wcs_filename)
                    print(f"{Style.BRIGHT}Successfully solved {filename}{Style.RESET_ALL}")
                else:
                    print(f"{Style.BRIGHT}No WCS file generated for {filename}{Style.RESET_ALL}")
                    
            except TimeoutExpired:
                print(f"{Style.BRIGHT}Timeout solving {filename} (exceeded {config.SOLVER_OFFLINE_TIMEOUT}s){Style.RESET_ALL}")
            except Exception as e:
                print(f"{Style.BRIGHT}Error solving {filename}: {e}{Style.RESET_ALL}")
            finally:
                solver_cleanup()

    else:
        for filename in options.files:
            # Check if solving should be interrupted
            if is_solver_interrupted():
                print(f"{Style.BRIGHT}Solver interrupted by user.{Style.RESET_ALL}")
                raise KeyboardInterrupt("Solver interrupted by user")
                
            print(f"\n{Style.BRIGHT}Solving {filename}.{Style.RESET_ALL}")
            print(
                f"Downsample: {downsample}, RA: {ra}, Dec: {dec}, Radius: {radius}\n"
            )

            # Validate image before attempting to solve
            if config.SOLVER_VALIDATE_IMAGES:
                print(f"{Style.BRIGHT}Image validation is enabled.{Style.RESET_ALL}")
                is_valid, reason = validate_image_for_solving(filename)
                if not is_valid:
                    print(f"{Style.BRIGHT}Skipping {filename}: {reason}{Style.RESET_ALL}")
                    continue
            else:
                print(f"{Style.BRIGHT}Image validation is disabled.{Style.RESET_ALL}")

            # Generate WCS filename
            base_name = Path(filename).stem
            wcs_filename = f"solved/{base_name}.wcs"
            
            try:
                proc = run(
                    [
                        "solve-field",
                        "--dir",
                        "solved",
                        "--no-plots",
                        "--no-verify",
                        "--guess-scale",
                        "--overwrite",
                        "--downsample",
                        str(downsample),
                        "--ra",
                        str(ra),
                        "--dec",
                        str(dec),
                        "--radius",
                        str(radius),
                        "--wcs",
                        wcs_filename,
                        filename,
                    ],
                    check=True,
                    timeout=config.SOLVER_OFFLINE_TIMEOUT,
                )
                
                # Apply WCS to original file
                if os.path.exists(wcs_filename):
                    apply_wcs_to_file(filename, wcs_filename)
                    # Clean up WCS file
                    os.remove(wcs_filename)
                    print(f"{Style.BRIGHT}Successfully solved {filename}{Style.RESET_ALL}")
                else:
                    print(f"{Style.BRIGHT}No WCS file generated for {filename}{Style.RESET_ALL}")
                    
            except TimeoutExpired:
                print(f"{Style.BRIGHT}Timeout solving {filename} (exceeded {config.SOLVER_OFFLINE_TIMEOUT}s){Style.RESET_ALL}")
            except Exception as e:
                print(f"{Style.BRIGHT}Error solving {filename}: {e}{Style.RESET_ALL}")
            finally:
                solver_cleanup()
