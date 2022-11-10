''' Methods for astrometry analysis and solar system object (SSO) data.
    @author: Adrien Vilquin Barrajon <avilqu@gmail.com>
'''

from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u
from astroquery.imcce import Skybot
from astroquery.simbad import Simbad

from lib.class_data_display import DataDisplay


def overlay_sso(img, maglimit):
    d = DataDisplay(img)
    d.show()

    field = SkyCoord(img['header']['ra']*u.deg, img['header']['dec']*u.deg)
    epoch = Time(img['header']['date-obs'])
    search_scale = ((img['header']['scale'] * img['header']['naxis2']) / 60)*u.arcmin
    search_results = Skybot.cone_search(field, search_scale, epoch)

    objects = []
    for obj in search_results:
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

def find_object(img, text):
    d = DataDisplay(img)
    d.show()

    objects = Simbad.query_object(text)
    print(objects)

    for obj in objects:
        coord = SkyCoord(obj['RA'], obj['DEC'], unit=(u.hourangle, u.deg))
        d.overlay_object(coord, obj['MAIN_ID'])