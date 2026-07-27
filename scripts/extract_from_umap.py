"""
extract_from_umap.py  —  ONE-TIME migration.

Reads your original uMap backup (../backups/umap_backup_mykhaylo.umap) and
produces the flat-file source of truth:
    ../data/points.csv        one row per point
    ../data/routes.csv        index of routes (name, mode, date, distance)
    ../data/routes/*.gpx      one GPX file per route

You normally run this only once. After that you edit points.csv / routes/ by
hand and use build_map.py. Re-running it will OVERWRITE those files, so don't
run it again after you've started editing.
"""
import json, re, csv, os
from xml.sax.saxutils import escape
from shapely.geometry import LineString

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC  = os.path.join(ROOT, "backups", "umap_backup_mykhaylo.umap")

POINT_LAYERS = {"Airports","Football_stadiums","Places","Hotels",
                "Transport","Ski","Border_Crossing","Car_Rentals"}  # Lived intentionally excluded
ROUTE_LAYERS = {"drive","ride","train","waterways"}

# Fixes for country codes found to be wrong/non-ISO in THIS dataset.
COUNTRY_FIX = {"UK": "GB", "NE": "NL"}

def s(x):
    return x if isinstance(x, str) else ("" if x is None else str(x))

def parse_prefix(name):
    m = re.match(r"^([A-Z]{2}) - (.*)$", name)
    if m:
        return COUNTRY_FIX.get(m.group(1), m.group(1)), m.group(2).strip()
    return "", name

def extract_year(desc):
    desc = s(desc)
    if re.fullmatch(r"(19|20)\d{2}", desc.strip()):
        return desc.strip(), ""
    m = re.search(r"\b(19|20)\d{2}\b", desc)
    return (m.group(0) if m else ""), desc

def slug(x):
    return re.sub(r"[^A-Za-z0-9]+", "-", x).strip("-")[:50] or "route"

def haversine_km(coords):
    from math import radians, sin, cos, asin, sqrt
    R = 6371.0088; d = 0.0
    for (lo1,la1),(lo2,la2) in zip(coords, coords[1:]):
        dlo=radians(lo2-lo1); dla=radians(la2-la1)
        a=sin(dla/2)**2+cos(radians(la1))*cos(radians(la2))*sin(dlo/2)**2
        d+=2*R*asin(sqrt(a))
    return d

def main():
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    layers = data["layers"]

    # ---- points ----
    rows = []
    for layer in layers:
        lname = layer["properties"].get("name")
        if lname not in POINT_LAYERS:
            continue
        for feat in layer["features"]:
            p = feat.get("properties", {})
            lon, lat = (feat["geometry"]["coordinates"] + [0, 0])[:2]
            cc, clean = parse_prefix(s(p.get("name")))
            year, desc = extract_year(p.get("description"))
            rows.append({"layer": lname, "country": cc, "name": clean,
                         "lat": round(lat,6), "lon": round(lon,6), "date": year,
                         "description": s(desc).replace("\n"," ").strip(),
                         "color": s(p.get("icon-color"))})
    with open(os.path.join(ROOT,"data","points.csv"),"w",newline="",encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["layer","country","name","lat","lon","date","description","color"])
        w.writeheader(); w.writerows(rows)
    print(f"points.csv: {len(rows)} rows")

    # ---- routes ----
    idx = []
    routes_dir = os.path.join(ROOT,"data","routes")
    for layer in layers:
        mode = layer["properties"].get("name")
        if mode not in ROUTE_LAYERS:
            continue
        for i, feat in enumerate(layer["features"]):
            g = feat.get("geometry", {})
            if g.get("type") != "LineString":
                continue
            raw = [(c[0], c[1]) for c in g["coordinates"] if len(c) >= 2]
            if len(raw) < 2:
                continue
            simp = [(round(x,6), round(y,6)) for x,y in
                    LineString(raw).simplify(0.00007, preserve_topology=False).coords]
            name = s(feat.get("properties",{}).get("name")) or f"{mode} {i}"
            ym = re.search(r"\b(19|20)\d{2}\b", name)
            date = ym.group(0) if ym else ""
            dist = round(haversine_km(simp), 1)
            fn = f"{mode}__{i:04d}_{slug(name)}.gpx"
            pts = "\n".join(f'      <trkpt lat="{la}" lon="{lo}"></trkpt>' for lo,la in simp)
            gpx = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
                   f'<gpx version="1.1" creator="yatutbuv" xmlns="http://www.topografix.com/GPX/1/1">\n'
                   f'  <trk><name>{escape(name)}</name><trkseg>\n{pts}\n  </trkseg></trk>\n</gpx>\n')
            with open(os.path.join(routes_dir, fn), "w", encoding="utf-8") as rf:
                rf.write(gpx)
            idx.append({"file": fn, "mode": mode, "name": name,
                        "date": date, "distance_km": dist, "notes": ""})
    with open(os.path.join(ROOT,"data","routes.csv"),"w",newline="",encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["file","mode","name","date","distance_km","notes"])
        w.writeheader(); w.writerows(idx)
    print(f"routes.csv: {len(idx)} routes -> data/routes/*.gpx "
          f"({sum(r['distance_km'] for r in idx):,.0f} km total)")

if __name__ == "__main__":
    main()
