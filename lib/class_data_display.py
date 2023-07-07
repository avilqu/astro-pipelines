''' Contains all functions for visual analysis of image files.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

import pyds9
from astropy.nddata import CCDData


class DataDisplay:

    def __init__(self, img):
        self.d = pyds9.DS9()
        self.filename = f'{img["path"]}'
        self.data = CCDData.read(self.filename, unit='adu')

    def show(self):
        self.d.set(f'file new {self.filename}')
        self.d.set('zoom to fit')
        self.d.set('scale zscale')

    def overlay_object(self, coord, name='', size=40, physical=False):
        if not physical:
            c = self.data.wcs.world_to_pixel(coord)
        else:
            c = coord
        self.d.set('regions', f'circle({c[0]},{c[1]},{size})')
        self.d.set('regions', f'text({c[0]},{c[1]-100},"{name}")')
