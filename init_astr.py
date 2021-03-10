#!/usr/bin/python

import os
from pathlib import Path

raw_path_str = os.getcwd()
new_path_str = raw_path_str.replace('data', 'astrometry', 1)

new_path = Path(new_path_str)
new_path.mkdir(parents=True, exist_ok=True)
os.symlink(raw_path_str, new_path_str + '/raw')
os.symlink(new_path_str, raw_path_str + '/reduced')

os.chdir(new_path_str)
