#!/usr/bin/python

import sys
import os
import requests
import json
import urllib.request
import time
from pathlib import Path
from subprocess import run
from astropy import units as u
from astropy.coordinates import SkyCoord

def openSession(key):
    requestJson = json.dumps({"apikey": key})
    try:
        r = requests.post('http://nova.astrometry.net/api/login', data={'request-json': requestJson})
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
    if r.json()['status'] == 'success':
        print(time.strftime('%x %X') + ' | Opened connection. Session ID: ' + r.json()['session'])
        return r.json()
    else:
        print('\n===================================')
        print(time.strftime('%x %X') + ' | E: ' + r.json()['errormessage'])
        print('===================================\n')

def submitFile(filename, key, args):
    requestJson = {
        "session": key,
        "publicly_visible": "n",
        "allow_modifications": "n",
        "allow_commercial_use": "n"
        }

    if args.ra and args.dec:
        c = SkyCoord(args.ra * u.degree, args.dec * u.degree)
        print(time.strftime('%x %X') + ' | Input coordinates: ' + c.to_string('hmsdms'))

    if args.ra: requestJson['center_ra'] = args.ra
    if args.dec: requestJson['center_dec'] = args.dec
    if args.radius: requestJson['radius'] = args.radius
    if args.scaleEst: requestJson['scale_est'] = args.scaleEst
    if args.scaleErr: requestJson['scale_err'] = args.scaleErr

    try:
        r = requests.post('http://nova.astrometry.net/api/upload', files=[('request-json', (None, json.dumps(requestJson), 'text/plain')), ('file', (filename, open(filename, 'rb'), 'application/octet-stream'))])
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
    if r.json()['status'] == 'success':
        print(time.strftime('%x %X') + ' | File ' + filename + ' sent with options:')
        print(requestJson)
        return r.json()
    else:
        print('\n===================================')
        print(time.strftime('%x %X') + ' | E: ' + r.json()['errormessage'])
        print('===================================\n')

def getSubmissionStatus(subid):
    url = 'http://nova.astrometry.net/api/submissions/' + str(subid)
    try:
        r = requests.post(url)
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
    return r.json()

def getJobStatus(jobid):
    url = 'http://nova.astrometry.net/api/jobs/' + str(jobid)
    try:
        r = requests.post(url)
    except requests.exceptions.RequestException as e:
        print(e)
        sys.exit(1)
    return r.json()

def getJobResults(jobid):
    solvedDirName = 'solved'
    solvedPath = Path(os.getcwd() + '/' + solvedDirName)
    solvedPath.mkdir(exist_ok=True)
    try:
        r = requests.post('http://nova.astrometry.net/api/jobs/' + str(jobid) + '/info').json()
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
    filename = solvedDirName + '/' + r['original_filename'] + '.solved.fits'
    fitsUrl = 'http://nova.astrometry.net/new_fits_file/' + str(jobid)
    urllib.request.urlretrieve(fitsUrl, filename)

def solveOnline(args, key):
    session = openSession(key)['session']
    i = 1
    for filename in args.files:
        count = str(i) + '/' + str(len(args.files))
        subid = submitFile(filename, session, args)['subid']
        subStatus = getSubmissionStatus(subid)
        while subStatus['jobs'] == [] or subStatus['jobs'] == [None]:
            print(time.strftime('%x %X') + ' | Waiting for job ' + count + ' to start...')
            subStatus = getSubmissionStatus(subid)
            time.sleep(3)
        print(time.strftime('%x %X') + ' | Job ' + count + ' has started.')
        jobid = subStatus['jobs'][0]
        jobStatus = getJobStatus(jobid)
        while jobStatus['status'] == 'solving':
            print(time.strftime('%x %X') + ' | Status: ' + jobStatus['status'] + ' image ' + count)
            jobStatus = getJobStatus(jobid)
            time.sleep(3)
        if jobStatus['status'] == 'success':
            getJobResults(jobid)
        else:
            print('\n===================================')
            print(time.strftime('%x %X') + ' | E: Couldn\'t solve image ' + count)
            print('===================================\n')
        i += 1

def solveOffline(args):
    downsample = 1
    ra = 180
    dec = 0
    radius = 360

    if args.downsample:
        downsample = str(args.downsample)
    if args.ra:
        ra = str(args.ra)
    if args.dec:
        dec = str(args.dec)
    if args.radius:
        radius = str(args.radius)

    if args.ra and args.dec:
        c = SkyCoord(args.ra * u.degree, args.dec * u.degree)
        print('---\nInput coordinates: ' + c.to_string('hmsdms') + '\n---\n\n')

    for filename in args.files:
        proc = run(['solve-field', '--dir', 'solved', '--no-plots', '--guess-scale', '--overwrite', '--downsample', str(downsample), '--ra', str(ra), '--dec', str(dec), '--radius', str(radius), filename])
        print('\n===================================')
        print(proc.args)
        print('===================================\n')


if __name__ == "__main__":

    import argparse

    apiKey = 'zrvbykzuksfbcilr'

    parser = argparse.ArgumentParser(description='Simple CLI for Astrometry.Net engine, both online and offline. Can solve multiple files.')
    parser.add_argument('files', help='input filename(s)', type=str, nargs='+')
    # parser.add_argument('-d', '--dir', action='store_true', help='plate solve all fits files in current directory')
    # parser.add_argument('-f', '--files', nargs="+", help='select fits files to plate solve')
    parser.add_argument('-r', '--ra', help='estimated RA center (angle)', type=float, dest='ra')
    parser.add_argument('-d', '--dec', help='estimated DEC center (angle)', type=float, dest='dec')
    parser.add_argument('-R', '--radius', help='search radius around center (degrees)', type=str, dest='radius')
    parser.add_argument('-s', '--scale', help='estimated field scale (arcminutes)', type=int, dest='scaleEst')
    parser.add_argument('-e', '--error', help='estimated field scale error (percent)', type=int, dest='scaleErr')
    parser.add_argument('-D', '--downsample', help='downsampling amount', type=int)
    parser.add_argument('-o', '--online', action='store_true', help='use online solver (requires connection)')
    args = parser.parse_args()

    if args.online:
        solveOnline(args, apiKey)
    else:
        solveOffline(args)
