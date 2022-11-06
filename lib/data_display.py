''' Contains all functions for visual analysis of image files.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

import pyds9
from astropy.nddata import CCDData



class DataDisplay:

    def __init__(self, img):
        self.d = pyds9.DS9()
        self.filename = img['filename']
        self.data = CCDData.read(self.filename)
    
    def show(self):
        self.d.set(f'file new {self.filename}')
        self.d.set('zoom to fit')
        self.d.set('scale zscale')

    def overlay_object(self, coord, mag=15):
        self.d.set('regions', f'circle({coord[0]},{coord[1]},{mag})')
