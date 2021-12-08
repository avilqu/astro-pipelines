#!/opt/anaconda/bin/python

''' Contains main class for image and collection analysis.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''


from pathlib import Path
from datetime import datetime
import os
import shutil
from colorama import Fore, Back, Style

import ccdproc as ccdp
from astropy import units as u
from astropy.stats import mad_std
import numpy as np

import config as cfg
import helpers as hlp


class DataAnalysis:

    def __init__(self, data=None):
        if data:
            self.collection = ccdp.ImageFileCollection(filenames=data)

    def adu_eval(self):
        print(
            f'{Style.BRIGHT}ADU values for {len(self.collection.files)} files.{Style.RESET_ALL}')
