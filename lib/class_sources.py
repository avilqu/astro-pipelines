''' Sources class definition (source extraction, seeing computing).
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

from astropy.io import fits
from photutils.detection import DAOStarFinder

from lib.class_data_display import DataDisplay

class Sources:

    def __init__(self, data):
        self.data = data
        self.nddata = fits.getdata(data['path'], ext=0)

        daofind = DAOStarFinder(fwhm=5.0, threshold=900)
        self.sources = daofind(self.nddata)

    def show_sources(self):
        d = DataDisplay(self.data)
        d.show()
        print(self.sources)

        for source in self.sources:
            coord = (source['xcentroid'], source['ycentroid'])
            d.overlay_object(coord, size=10, physical=True)
            # print(f'')