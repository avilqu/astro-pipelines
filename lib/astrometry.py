''' Methods for astrometry analysis and solar system object (SSO) data.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u
from astroquery.imcce import Skybot

from lib.data_display import DataDisplay


def query_skybot(img):
    field = SkyCoord(img['header']['ra']*u.deg, img['header']['dec']*u.deg)
    epoch = Time(img['header']['date-obs'])
    objects = Skybot.cone_search(field, 15*u.arcmin, epoch)
    return objects

def overlay_sso(img, maglimit):
    d = DataDisplay(img)
    d.show()

    objects = []
    for obj in query_skybot(img):
        if obj['V'].value < maglimit:
            objects.append({
                'name': obj['Name'],
                'mag': obj['V'],
                'type': obj['Type'],
                'geodist': obj['geodist'],
                'coord': SkyCoord(obj['RA'], obj['DEC'])
            })

    for obj in objects:
        d.overlay_object(obj['coord'], obj['name'])
        print(f'{obj["name"]}, V mag: {obj["mag"].value}')