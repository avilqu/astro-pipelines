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
from subprocess import run
from colorama import Style

import requests
from astropy.io import fits
from astropy.wcs import WCS


def apply_wcs_to_file(original_file, wcs_file):
    """Apply WCS headers from a WCS file to the original FITS file."""
    
    try:
        # Read the WCS file
        wcs_hdu = fits.open(wcs_file)
        wcs_header = wcs_hdu[0].header
        
        # Read the original file
        original_hdu = fits.open(original_file, mode='update')
        
        # Update the WCS keywords in the original file
        wcs_keywords = ['CRPIX1', 'CRPIX2', 'CRVAL1', 'CRVAL2', 'CD1_1', 'CD1_2', 'CD2_1', 'CD2_2',
                       'CTYPE1', 'CTYPE2', 'CUNIT1', 'CUNIT2', 'CRRES1', 'CRRES2', 'LONPOLE', 'LATPOLE',
                       'PC1_1', 'PC1_2', 'PC2_1', 'PC2_2', 'CDELT1', 'CDELT2', 'CROTA1', 'CROTA2']
        
        keywords_updated = 0
        for keyword in wcs_keywords:
            if keyword in wcs_header:
                original_hdu[0].header[keyword] = wcs_header[keyword]
                keywords_updated += 1
        
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
        )
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
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
        )
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
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


def get_submission_status(subid):
    """Monitors file submission status from Astrometry.net server."""

    url = "http://nova.astrometry.net/api/submissions/" + str(subid)
    try:
        r = requests.post(url)
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
    return r.json()


def get_job_status(jobid):
    """Monitors job status from Astrometry.net server."""

    url = "http://nova.astrometry.net/api/jobs/" + str(jobid)
    try:
        r = requests.post(url)
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
    return r.json()


def get_job_results(jobid, original_filename):
    """Get job results from Astrometry.net server and apply WCS to original file."""

    try:
        r = requests.post(
            "http://nova.astrometry.net/api/jobs/" + str(jobid) + "/info"
        ).json()
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
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

    session = open_session(key)["session"]
    i = 1
    for filename in options.files:
        count = str(i) + "/" + str(len(options.files))
        subid = submit_file(filename, session, options)["subid"]
        sub_status = get_submission_status(subid)
        while sub_status["jobs"] == [] or sub_status["jobs"] == [None]:
            print(
                time.strftime("%x %X")
                + " | Waiting for job "
                + count
                + " to start..."
            )
            sub_status = get_submission_status(subid)
            time.sleep(3)
        print(time.strftime("%x %X") + " | Job " + count + " has started.")
        jobid = sub_status["jobs"][0]
        job_status = get_job_status(jobid)
        while job_status["status"] == "solving":
            print(
                time.strftime("%x %X")
                + " | Status: "
                + job_status["status"]
                + " image "
                + count
            )
            job_status = get_job_status(jobid)
            time.sleep(3)
        if job_status["status"] == "success":
            get_job_results(jobid, filename)
        else:
            print("\n===================================")
            print(
                time.strftime("%x %X") + " | E: Couldn't solve image " + count
            )
            print("===================================\n")
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
            print(f"\n{Style.BRIGHT}Solving {filename}.{Style.RESET_ALL}")

            # Generate WCS filename
            base_name = Path(filename).stem
            wcs_filename = f"solved/{base_name}.wcs"
            
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
            )
            print(f"Solver arguments: {proc.args}")
            
            # Apply WCS to original file
            if os.path.exists(wcs_filename):
                apply_wcs_to_file(filename, wcs_filename)
                # Clean up WCS file
                os.remove(wcs_filename)
            
            solver_cleanup()

    else:
        for filename in options.files:
            print(f"\n{Style.BRIGHT}Solving {filename}.{Style.RESET_ALL}")
            print(
                f"Downsample: {downsample}, RA: {ra}, Dec: {dec}, Radius: {radius}\n"
            )

            # Generate WCS filename
            base_name = Path(filename).stem
            wcs_filename = f"solved/{base_name}.wcs"
            
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
            )
            
            # Apply WCS to original file
            if os.path.exists(wcs_filename):
                apply_wcs_to_file(filename, wcs_filename)
                # Clean up WCS file
                os.remove(wcs_filename)
            
            solver_cleanup()
