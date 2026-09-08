"""Add a place from coordinates or a confirmed Nominatim result.
The desktop alternative is Start.cmd > Places > Add.
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from travel_core import ROOT, POINT_FIELDS, TravelError, ensure_ids, save_record


def geocode(query, country=''):
    params = {'q':query, 'format':'jsonv2', 'limit':5, 'addressdetails':1}
    if country:
        params['countrycodes'] = country.lower()
    req = urllib.request.Request('https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(params),
                                 headers={'User-Agent':'yatutbuv-travellog/2.0 (occasional manual place lookup)'})
    time.sleep(1.1)
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('query', nargs='+')
    for name in ['layer','country','name','date','desc','color']:
        ap.add_argument('--'+name, default='', required=name=='layer')
    ap.add_argument('--lat', type=float)
    ap.add_argument('--lon', type=float)
    args = ap.parse_args()
    if (args.lat is None) != (args.lon is None):
        ap.error('Supply both --lat and --lon.')
    query = ' '.join(args.query)
    lat, lon, country = args.lat, args.lon, args.country.upper()
    if lat is None:
        hits = geocode(query,country)
        if not hits:
            raise TravelError('No results. Try a more specific name or enter coordinates.')
        for i,h in enumerate(hits,1):
            print(f"{i}. {h['display_name']}")
        choice = input('Choose a result number, or Enter to cancel: ').strip()
        if not choice:
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(hits):
            raise TravelError('Invalid selection; no place was saved.')
        hit = hits[int(choice)-1]
        lat, lon = hit['lat'], hit['lon']
        country = country or hit.get('address',{}).get('country_code','').upper()
    from project_lock import project_lock
    with project_lock(ROOT):
        ensure_ids()
        save_record('points', {'layer':args.layer,'name':args.name or query,'country':country,
                              'lat':lat,'lon':lon,'date':args.date,'description':args.desc,'color':args.color})
    print('Place saved. Open Start.cmd to build and publish when ready.')


if __name__ == '__main__':
    try:
        main()
    except (TravelError,OSError,ValueError) as e:
        print(f'ERROR: {e}',file=sys.stderr)
        sys.exit(1)
