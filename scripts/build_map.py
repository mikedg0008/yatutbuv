"""
build_map.py  —  the tool you run after every edit.

Reads:   ../data/points.csv
         ../data/routes.csv  +  ../data/routes/*.gpx
Writes:  ../build/<PointLayer>.geojson
         ../build/<mode>.geojson
         ../build/stats.md

Small output (route geometry simplified for display) and tolerant CSV reading
(handles Excel's ';' delimiter and comma decimals).

Usage:   python build_map.py
Requires: shapely   (pip install shapely)
"""
import csv, json, os, glob, io
import xml.etree.ElementTree as ET
from shapely.geometry import LineString

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
BUILD = os.path.join(ROOT, "build")

ROUTE_SIMPLIFY_DEG = 0.0001   # ~11 m; bigger = lighter
COORD_DECIMALS = 5            # ~1.1 m


def read_csv_tolerant(path):
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    if not text.strip():
        return []
    first = text.splitlines()[0]
    delim = ";" if first.count(";") > first.count(",") else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delim))


def to_float(v):
    if v is None:
        return None
    v = str(v).strip()
    if v == "":
        return None
    if "," in v and "." not in v:
        v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def write_geojson(name, features):
    os.makedirs(BUILD, exist_ok=True)
    path = os.path.join(BUILD, f"{name}.geojson")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features},
                  f, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(path)


def build_points():
    rows = read_csv_tolerant(os.path.join(DATA, "points.csv"))
    by_layer, skipped = {}, 0
    for r in rows:
        lat, lon = to_float(r.get("lat")), to_float(r.get("lon"))
        if lat is None or lon is None:
            skipped += 1
            continue
        props = {"name": (r.get("name") or "").strip(),
                 "country": (r.get("country") or "").strip(),
                 "date": (r.get("date") or "").strip(),
                 "description": (r.get("description") or "").strip()}
        color = (r.get("color") or "").strip()
        if color:
            props["_umap_options"] = {"color": color, "iconColor": color}
        feat = {"type": "Feature",
                "properties": {k: v for k, v in props.items() if v not in ("", None)},
                "geometry": {"type": "Point",
                             "coordinates": [round(lon, COORD_DECIMALS),
                                             round(lat, COORD_DECIMALS)]}}
        by_layer.setdefault((r.get("layer") or "Unsorted").strip(), []).append(feat)
    results = []
    for layer, feats in sorted(by_layer.items()):
        results.append((layer, len(feats), write_geojson(layer, feats)))
    return results, skipped


def parse_gpx(path):
    root = ET.parse(path).getroot()
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    pts = root.findall(".//g:trkpt", ns) or [e for e in root.iter() if e.tag.endswith("trkpt")]
    out = []
    for p in pts:
        try:
            out.append((float(p.get("lon")), float(p.get("lat"))))
        except (TypeError, ValueError):
            pass
    return out


def build_routes():
    idx = {r["file"]: r for r in read_csv_tolerant(os.path.join(DATA, "routes.csv"))}
    by_mode = {}
    for gpx in sorted(glob.glob(os.path.join(DATA, "routes", "*.gpx"))):
        fn = os.path.basename(gpx)
        meta = idx.get(fn, {})
        mode = (meta.get("mode") or fn.split("__", 1)[0]).strip()
        coords = parse_gpx(gpx)
        if len(coords) < 2:
            continue
        line = LineString(coords).simplify(ROUTE_SIMPLIFY_DEG, preserve_topology=False)
        rc = [[round(x, COORD_DECIMALS), round(y, COORD_DECIMALS)] for x, y in line.coords]
        props = {"name": (meta.get("name") or fn).strip(), "mode": mode,
                 "date": (meta.get("date") or "").strip(),
                 "distance_km": (meta.get("distance_km") or "").strip()}
        feat = {"type": "Feature",
                "properties": {k: v for k, v in props.items() if v != ""},
                "geometry": {"type": "LineString", "coordinates": rc}}
        by_mode.setdefault(mode, []).append(feat)
    results = []
    for mode, feats in sorted(by_mode.items()):
        results.append((mode, len(feats), write_geojson(mode, feats)))
    return results


def write_stats(point_results, route_results):
    rows = read_csv_tolerant(os.path.join(DATA, "routes.csv"))
    lines = ["# Travel log — stats", ""]
    lines.append(f"**Points:** {sum(n for _,n,_ in point_results)} across {len(point_results)} layers")
    for layer, n, _ in point_results:
        lines.append(f"- {layer}: {n}")
    lines += ["", "**Routes by mode:**"]
    tot = 0.0
    for mode, n, _ in route_results:
        km = sum(to_float(r.get("distance_km")) or 0 for r in rows if (r.get("mode") or "") == mode)
        tot += km
        lines.append(f"- {mode}: {n} routes, {km:,.0f} km")
    lines += ["", f"**Total logged distance:** {tot:,.0f} km"]
    with open(os.path.join(BUILD, "stats.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    pr, skipped = build_points()
    rr = build_routes()
    write_stats(pr, rr)
    print("POINT LAYERS")
    for layer, n, size in pr:
        print(f"  {layer:<18} {n:>4} pts   {size/1024:>7.0f} KB")
    if skipped:
        print(f"  ({skipped} rows skipped: missing/invalid lat-lon)")
    print("ROUTE LAYERS")
    for mode, n, size in rr:
        print(f"  {mode:<18} {n:>4} rts   {size/1024:>7.0f} KB")
    total = sum(s for _, _, s in pr) + sum(s for _, _, s in rr)
    print(f"\nbuild/ total: {total/1e6:.2f} MB   (see build/stats.md)")


if __name__ == "__main__":
    main()
