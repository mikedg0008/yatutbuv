"""
add_point.py  —  fast way to add one place to points.csv.

It mirrors your current habit ("search a location, pick it") but writes a clean
structured row instead of a hand-typed map pin.

Two modes:

  1) Geocode a search string (uses OpenStreetMap's free Nominatim service):
       python add_point.py --layer Hotels --country AT "Hotel Sacher Vienna"
       python add_point.py --layer Places "Historic Centre of Vienna" --date 2025

  2) Add exact coordinates yourself (no lookup):
       python add_point.py --layer Ski --country CH "Titlis" --lat 46.77 --lon 8.43

After adding, run build_map.py to regenerate the map data.

Nominatim's usage policy asks for a real User-Agent and <=1 request/second;
this script sends both and is fine for occasional manual use. Don't loop it.
"""
import argparse, csv, io, os, sys, time, json
import urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
POINTS = os.path.join(ROOT, "data", "points.csv")
FIELDS = ["layer", "country", "name", "lat", "lon", "date", "description", "color"]
UA = "yatutbuv-travellog/1.0 (personal use)"


def geocode(query):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "jsonv2", "limit": 5, "addressdetails": 1})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    time.sleep(1)  # be polite
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def read_delim(path):
    with open(path, encoding="utf-8-sig") as f:
        first = f.readline()
    return ";" if first.count(";") > first.count(",") else ","


def append_row(row):
    exists = os.path.exists(POINTS)
    delim = read_delim(POINTS) if exists else ","
    with open(POINTS, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter=delim)
        if not exists:
            w.writeheader()
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser(description="Add one place to points.csv")
    ap.add_argument("query", nargs="+", help="search text, or the place name if --lat/--lon given")
    ap.add_argument("--layer", required=True, help="e.g. Hotels, Places, Airports, Transport")
    ap.add_argument("--country", default="", help="ISO code, e.g. AT (optional; auto-filled from geocoder)")
    ap.add_argument("--name", default="", help="override the stored name")
    ap.add_argument("--date", default="", help="year or date")
    ap.add_argument("--desc", default="", help="description / note")
    ap.add_argument("--color", default="", help="optional per-point colour, e.g. #ffea00")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    args = ap.parse_args()

    query = " ".join(args.query)
    name = args.name or query
    country = args.country.upper()
    lat, lon = args.lat, args.lon

    if lat is None or lon is None:
        hits = geocode(query)
        if not hits:
            sys.exit(f"No result for: {query}")
        top = hits[0]
        lat, lon = float(top["lat"]), float(top["lon"])
        cc = (top.get("address", {}) or {}).get("country_code", "").upper()
        if not country and cc:
            country = cc
        print(f"Matched: {top.get('display_name','')[:90]}")
        print(f"  -> {lat:.6f}, {lon:.6f}  country={country or '?'}")

    row = {"layer": args.layer, "country": country, "name": name,
           "lat": round(lat, 6), "lon": round(lon, 6),
           "date": args.date, "description": args.desc, "color": args.color}
    append_row(row)
    print(f"Added to points.csv: [{args.layer}] {name}")
    print("Now run:  python scripts/build_map.py")


if __name__ == "__main__":
    main()
