#!/opt/anaconda/bin/python

''' CLI for online and offline Astrometry.net engine.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


import sys
import os
import json
import time
import urllib.request
from pathlib import Path
from subprocess import run

import requests
import ccdproc as ccdp
from astropy import units as u
from astropy.coordinates import SkyCoord


def open_session(key):
    ''' Opens HTTP session with Astrometry.net server. '''

    request_json = json.dumps({"apikey": key})
    try:
        r = requests.post('http://nova.astrometry.net/api/login',
                          data={'request-json': request_json})
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
    if r.json()['status'] == 'success':
        print(time.strftime('%x %X') +
              ' | Opened connection. Session ID: ' + r.json()['session'])
        return r.json()
    else:
        print('\n===================================')
        print(time.strftime('%x %X') + ' | E: ' + r.json()['errormessage'])
        print('===================================\n')


def submit_file(filename, key, options):
    ''' Sends image file to Astrometry.net server. '''

    request_json = {
        "session": key,
        "publicly_visible": "n",
        "allow_modifications": "n",
        "allow_commercial_use": "n"
    }

    if options.ra:
        request_json['center_ra'] = options.ra
    if options.dec:
        request_json['center_dec'] = options.dec
    if options.radius:
        request_json['radius'] = options.radius
    if options.scaleEst:
        request_json['scale_est'] = options.scaleEst
    if options.scaleErr:
        request_json['scale_err'] = options.scaleErr

    try:
        r = requests.post('http://nova.astrometry.net/api/upload', files=[('request-json', (None, json.dumps(
            request_json), 'text/plain')), ('file', (filename, open(filename, 'rb'), 'application/octet-stream'))])
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
    if r.json()['status'] == 'success':
        print(time.strftime('%x %X') + ' | File ' +
              filename + ' sent with options:')
        print(request_json)
        return r.json()
    else:
        print('\n===================================')
        print(time.strftime('%x %X') + ' | E: ' + r.json()['errormessage'])
        print('===================================\n')


def get_submission_status(subid):
    ''' Monitors file submission status from Astrometry.net server. '''

    url = 'http://nova.astrometry.net/api/submissions/' + str(subid)
    try:
        r = requests.post(url)
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
    return r.json()


def get_job_status(jobid):
    ''' Monitors job status from Astrometry.net server. '''

    url = 'http://nova.astrometry.net/api/jobs/' + str(jobid)
    try:
        r = requests.post(url)
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
    return r.json()


def get_job_results(jobid):
    ''' Get job results from Astrometry.net server. '''

    solved_dir_name = 'solved'
    solved_path = Path(os.getcwd() + '/' + solved_dir_name)
    solved_path.mkdir(exist_ok=True)
    try:
        r = requests.post(
            'http://nova.astrometry.net/api/jobs/' + str(jobid) + '/info').json()
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
    print('\n===================================')
    print('Image solved ! (' + time.strftime('%x %X') + ')')
    print('Filename: ' + r['original_filename'])
    print('RA: ' + str(r['calibration']['ra']))
    print('DEC: ' + str(r['calibration']['dec']))
    print('Radius: ' + str(r['calibration']['radius']))
    print('Orientation: ' + str(r['calibration']['orientation']))
    print('Pixel scale: ' + str(r['calibration']['pixscale']))
    print('Objects in field: ' + str(r['objects_in_field']))
    print('===================================\n')
    filename = solved_dir_name + '/' + \
        r['original_filename'][:-5] + '.solved.fits'
    fits_url = 'http://nova.astrometry.net/new_fits_file/' + str(jobid)
    urllib.request.urlretrieve(fits_url, filename)


def solve_online(options, key):
    ''' Wrapper function for the whole online solving process. '''

    session = open_session(key)['session']
    i = 1
    for filename in options.files:
        count = str(i) + '/' + str(len(options.files))
        subid = submit_file(filename, session, options)['subid']
        sub_status = get_submission_status(subid)
        while sub_status['jobs'] == [] or sub_status['jobs'] == [None]:
            print(time.strftime('%x %X') +
                  ' | Waiting for job ' + count + ' to start...')
            sub_status = get_submission_status(subid)
            time.sleep(3)
        print(time.strftime('%x %X') + ' | Job ' + count + ' has started.')
        jobid = sub_status['jobs'][0]
        job_status = get_job_status(jobid)
        while job_status['status'] == 'solving':
            print(time.strftime('%x %X') + ' | Status: ' +
                  job_status['status'] + ' image ' + count)
            job_status = get_job_status(jobid)
            time.sleep(3)
        if job_status['status'] == 'success':
            get_job_results(jobid)
        else:
            print('\n===================================')
            print(time.strftime('%x %X') +
                  ' | E: Couldn\'t solve image ' + count)
            print('===================================\n')
        i += 1


def solver_cleanup():
    ''' Delete all the files generated by solve-field to kep only X.solved.fits. '''

    solved_directory = './solved'

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

    for file in wcs_files:
        file_path = os.path.join(solved_directory, file)
        os.remove(file_path)


def solve_offline(options):
    ''' Wrapper function for the offline solve-field CLI. '''

    downsample = 1
    ra = 180
    dec = 0
    radius = 360

    if options.downsample:
        downsample = str(options.downsample)
    if options.ra:
        ra = str(options.ra)
    if options.dec:
        dec = str(options.dec)
    if options.radius:
        radius = str(options.radius)

    for filename in options.files:
        new_filename = 'solved/' + filename[filename.find('/') + 1:]
        proc = run(['solve-field',
                    '--dir', 'solved',
                    '--no-plots',
                    '--guess-scale',
                    '--overwrite',
                    '--downsample', str(downsample),
                    '--ra', str(ra),
                    '--dec', str(dec),
                    '--radius', str(radius),
                    '--new-fits', new_filename,
                    filename],
                   check=True)
        print('\n===================================')
        print(proc.args)
        print('===================================\n')
        solver_cleanup()


if __name__ == "__main__":

    import argparse

    apiKey = 'zrvbykzuksfbcilr'

    parser = argparse.ArgumentParser(
        description='Simple CLI for Astrometry.Net engine, both online and offline. Guesses scale and coordinates from FITS header by default. Outputs only one file per input file.')
    parser.add_argument('files', help='input filename(s)', type=str, nargs='+')
    parser.add_argument(
        '-r', '--ra', help='estimated RA center (angle)', type=float, dest='ra')
    parser.add_argument(
        '-d', '--dec', help='estimated DEC center (angle)', type=float, dest='dec')
    parser.add_argument(
        '-R', '--radius', help='search radius around center (degrees, default=15 unless no RA or DEC: 360)', type=str, dest='radius', default=15)
    parser.add_argument(
        '-s', '--scale', help='estimated field scale (arcminutes, online solver only)', type=int, dest='scaleEst')
    parser.add_argument(
        '-e', '--error', help='estimated field scale error (percent, online solver only)', type=int, dest='scaleErr')
    parser.add_argument('-D', '--downsample',
                        help='downsampling amount', type=int)
    parser.add_argument('-y', '--noconfirm',
                        action='store_true', help='skip confirmation')
    parser.add_argument('-o', '--online', action='store_true',
                        help='use online solver (requires internet connection)')
    args = parser.parse_args()

    images = ccdp.ImageFileCollection(filenames=args.files)
    print('\nFiles to calibrate:')
    print(images.summary['object', 'date-obs', 'frame',
                         'instrume', 'filter', 'exptime', 'ccd-temp', 'naxis1', 'naxis2'])

    if not args.ra:
        try:
            args.ra = ccdp.CCDData.read(args.files[0]).header['ra']
        except:
            print('No RA found, blind solving...')

    if not args.dec:
        try:
            args.dec = ccdp.CCDData.read(args.files[0]).header['dec']
        except:
            print('No DEC found, blind solving...')

    if not args.ra and not args.dec:
        args.radius = 360

    c = SkyCoord(args.ra * u.degree, args.dec * u.degree)
    print('\nTarget RA / DEC: ' + c.to_string('hmsdms'))
    print('Search radius (degrees): args.radius')

    if not args.noconfirm:
        if input('\nContinue? (Y/n) ') == 'n':
            exit()

    if args.online:
        solve_online(args, apiKey)
    else:
        solve_offline(args)
