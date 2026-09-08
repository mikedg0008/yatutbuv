"""Travel records, validation, safe edits and map generation (Python 3.10+)."""
from __future__ import annotations

import csv
import datetime as dt
import io
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
POINT_FIELDS = ['id', 'layer', 'country', 'name', 'lat', 'lon', 'date', 'description', 'color']
ROUTE_FIELDS = ['id', 'file', 'mode', 'name', 'date', 'distance_km', 'notes', 'source']
IMPORT_FIELDS = ['original_file', 'original_sha256', 'min_altitude_m', 'max_altitude_m',
                 'original_points', 'map_points', 'simplify_degrees']
ROUTE_FIELDS += IMPORT_FIELDS
SOURCES = ['', 'recorded', 'reconstructed', 'approximate']


class TravelError(ValueError):
    pass


def config(root=ROOT):
    return json.loads((Path(root) / 'map_config.json').read_text(encoding='utf-8-sig'))


def read_table(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        text = f.read()
    if not text.strip():
        raise TravelError(f'{Path(path).name}: missing CSV header.')
    header = text.splitlines()[0]
    delim = ';' if header.count(';') > header.count(',') else ','
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    fields = reader.fieldnames or []
    if len(fields) != len(set(fields)):
        raise TravelError(f'{Path(path).name}: duplicate column names.')
    rows = []
    for number, row in enumerate(reader, 2):
        if None in row or any(v is None for v in row.values()):
            raise TravelError(f'{Path(path).name}, row {number}: wrong number of cells.')
        rows.append({k: v.strip() for k, v in row.items()})
    return fields, rows, delim


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.writing-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_table(path, fields, rows, delim=','):
    out = io.StringIO(newline='')
    w = csv.DictWriter(out, fieldnames=fields, delimiter=delim)
    w.writeheader()
    w.writerows(rows)
    atomic_bytes(path, out.getvalue().encode('utf-8-sig'))


def backup(root, paths):
    dest = Path(root) / 'backups' / ('edit-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    for path in paths:
        path = Path(path)
        if path.exists():
            target = dest / path.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return dest


def number(value, label):
    try:
        n = float(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError):
        raise TravelError(f'{label}: enter a number.') from None
    if not math.isfinite(n):
        raise TravelError(f'{label}: must be a finite number.')
    return n


def coordinates(lon, lat):
    lon, lat = number(lon, 'Longitude'), number(lat, 'Latitude')
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise TravelError('Coordinates must be longitude -180..180 and latitude -90..90.')
    return lon, lat


def check_date(value):
    if not value:
        return
    if re.fullmatch(r'\d{4}', value) and 1 <= int(value) <= 9999:
        return
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError()
        dt.date.fromisoformat(value)
    except ValueError:
        raise TravelError('Date must be blank, YYYY or YYYY-MM-DD.') from None


def check_row(row, kind, cfg):
    if not row.get('name', '').strip():
        raise TravelError('Name is required.')
    check_date(row.get('date', ''))
    if kind == 'points':
        if row.get('layer') not in cfg['point_layers']:
            raise TravelError(f"Unknown point layer: {row.get('layer')}")
        coordinates(row.get('lon'), row.get('lat'))
        if row.get('country') and not re.fullmatch('[A-Z]{2}', row['country']):
            raise TravelError('Country must be a two-letter uppercase code or blank.')
    else:
        if row.get('mode') not in cfg['route_modes']:
            raise TravelError(f"Unknown route mode: {row.get('mode')}")
        if row.get('source', '') not in SOURCES:
            raise TravelError('Source must be blank, recorded, reconstructed or approximate.')
        fn = row.get('file', '')
        if not fn or '/' in fn or '\\' in fn or Path(fn).suffix.lower() != '.gpx':
            raise TravelError('Route file must be a GPX filename inside data/routes/.')
        original = row.get('original_file', '')
        if original and (not re.fullmatch(r'[a-f0-9]{64}\.gpx', original)):
            raise TravelError('Original file must be an archived GPX hash filename.')
        for key in ('min_altitude_m', 'max_altitude_m', 'distance_km', 'simplify_degrees'):
            if row.get(key):
                value = number(row[key], key)
                if key in ('distance_km', 'simplify_degrees') and value < 0:
                    raise TravelError(f'{key}: cannot be negative.')
        if row.get('min_altitude_m') and row.get('max_altitude_m'):
            if number(row['min_altitude_m'], 'Minimum altitude') > number(row['max_altitude_m'], 'Maximum altitude'):
                raise TravelError('Minimum altitude exceeds maximum altitude.')
        if original and not row.get('distance_km'):
            raise TravelError('Imported route is missing its original distance. Reimport its GPX.')


def parse_gpx(path, with_stats=False):
    """Preserve each track segment; support GPX 1.0/1.1 and GPX routes."""
    label = Path(path).name if isinstance(path, (str, os.PathLike)) else 'GPX'
    try:
        doc = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as e:
        raise TravelError(f'{label}: {e}') from None
    tag = lambda e: e.tag.rsplit('}', 1)[-1]
    if tag(doc) != 'gpx':
        raise TravelError(f'{label}: not a GPX document.')
    groups, elevations = [], []
    for parent in doc.iter():
        if tag(parent) in ('trkseg', 'rte'):
            point_tag = 'trkpt' if tag(parent) == 'trkseg' else 'rtept'
            pts = [coordinates(p.get('lon'), p.get('lat')) for p in parent if tag(p) == point_tag]
            if pts:
                groups.append(pts)
            for p in parent:
                if tag(p) == point_tag:
                    for child in p:
                        if tag(child) == 'ele' and child.text:
                            try:
                                elevations.append(number(child.text, 'Elevation'))
                            except TravelError:
                                pass  # Missing/invalid elevations do not invalidate the route.
    if not groups or not any(len(g) >= 2 for g in groups):
        raise TravelError(f'{label}: no track/route segment with at least two points.')
    # A one-point segment has no line geometry or distance. Do not bridge it.
    segments = [g for g in groups if len(g) >= 2]
    if with_stats:
        return segments, {'distance_km': f'{distance_km(segments):.6f}',
                          'original_points': str(sum(map(len, groups))),
                          'min_altitude_m': f'{min(elevations):.1f}' if elevations else '',
                          'max_altitude_m': f'{max(elevations):.1f}' if elevations else ''}
    return segments


def prepare_route(path, tolerance):
    """Read once: archive these exact bytes and derive all outputs from them."""
    try:
        from shapely.geometry import LineString
    except ImportError:
        raise TravelError('Shapely is missing. Run setup.cmd first.') from None
    tolerance = number(tolerance, 'Simplification')
    if not 0 <= tolerance <= 0.001:
        raise TravelError('Simplification must be between 0 and 0.001 degrees.')
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if Path(path).parent.name == 'routes_original' and Path(path).name != digest+'.gpx':
        raise TravelError('Archived original has changed. Restore it from backup before re-cleaning.')
    segments, stats = parse_gpx(io.BytesIO(raw), with_stats=True)
    doc = ET.Element('gpx', xmlns='http://www.topografix.com/GPX/1/1', version='1.1', creator='Yatutbuv')
    track = ET.SubElement(doc, 'trk')
    count = 0
    for segment in segments:
        points = list(LineString(segment).simplify(tolerance, preserve_topology=False).coords) if tolerance else segment
        part = ET.SubElement(track, 'trkseg')
        for x, y in points:
            ET.SubElement(part, 'trkpt', lon=repr(x), lat=repr(y))
        count += len(points)
    stats.update(original_file=digest+'.gpx', original_sha256=digest,
                 map_points=str(count), simplify_degrees=str(tolerance))
    return raw, ET.tostring(doc, encoding='utf-8', xml_declaration=True), stats


def distance_km(segments):
    total = 0.0
    for segment in segments:
        for (x1, y1), (x2, y2) in zip(segment, segment[1:]):
            a = math.sin(math.radians(y2-y1)/2)**2
            a += math.cos(math.radians(y1))*math.cos(math.radians(y2))*math.sin(math.radians(x2-x1)/2)**2
            total += 12742.0176 * math.asin(math.sqrt(min(1, max(0, a))))
    return total


def load_records(root=ROOT):
    cfg = config(root)
    tables, warnings, errors = {}, [], []
    for kind, required in [('points', POINT_FIELDS[1:]), ('routes', ROUTE_FIELDS[1:7])]:
        fields, rows, _ = read_table(Path(root) / 'data' / f'{kind}.csv')
        missing = set(required) - set(fields)
        if missing:
            raise TravelError(f'{kind}.csv: missing columns: {", ".join(sorted(missing))}')
        seen, filenames = set(), set()
        for i, row in enumerate(rows, 2):
            try:
                check_row(row, kind, cfg)
                rid = row.get('id')
                if rid and rid in seen:
                    raise TravelError(f'Duplicate ID: {rid}')
                if rid:
                    seen.add(rid)
                if kind == 'routes':
                    fn = row['file']
                    if fn.casefold() in filenames:
                        raise TravelError(f'GPX referenced more than once: {fn}')
                    filenames.add(fn.casefold())
                    row['_segments'] = parse_gpx(Path(root) / 'data/routes' / fn)
                    row['_km'] = number(row['distance_km'], 'Original distance') if row.get('original_file') else distance_km(row['_segments'])
                    if row.get('original_file') and not (Path(root)/'data/routes_original'/row['original_file']).exists():
                        warnings.append(f'{row["name"]}: original archive missing locally; map still builds, but restore it before re-cleaning.')
            except TravelError as e:
                errors.append(f'{kind}.csv row {i} ({row.get("name", "")}): {e}')
        tables[kind] = rows
    if errors:
        raise TravelError('Build stopped; existing output was not changed.\n' + '\n'.join(errors))
    indexed = {r['file'] for r in tables['routes']}
    extra = [p.name for p in (Path(root)/'data/routes').glob('*') if p.suffix.lower() == '.gpx' and p.name not in indexed]
    if extra:
        warnings.append(f'{len(extra)} unindexed GPX file(s) ignored: ' + ', '.join(sorted(extra)[:5]))
    return cfg, tables, warnings


def ensure_ids(root=ROOT):
    """Upgrade old CSVs once. Preserve existing values and unknown columns."""
    load_records(root)  # validate the complete project before touching any CSV
    changes = []
    for kind, wanted in [('points', POINT_FIELDS), ('routes', ROUTE_FIELDS)]:
        path = Path(root)/'data'/f'{kind}.csv'
        fields, rows, delim = read_table(path)
        new_fields = fields + [x for x in wanted if x not in fields]
        changed = fields != new_fields
        for row in rows:
            for k in new_fields:
                row.setdefault(k, '')
            if not row['id']:
                row['id'] = ('p-' if kind == 'points' else 'r-') + uuid.uuid4().hex
                changed = True
        if changed:
            changes.append((path, new_fields, rows, delim))
    if changes:
        backup(root, [x[0] for x in changes])
        for path, fields, rows, delim in changes:
            write_table(path, fields, rows, delim)


def save_record(kind, values, root=ROOT, record_id=None, gpx=None, tolerance=None):
    root = Path(root)
    path = root/'data'/f'{kind}.csv'
    fields, rows, delim = read_table(path)
    if kind == 'routes':
        fields += [k for k in IMPORT_FIELDS if k not in fields]
        for existing in rows:
            for key in IMPORT_FIELDS:
                existing.setdefault(key, '')
    index = next((i for i, r in enumerate(rows) if r.get('id') == record_id), None) if record_id else None
    if record_id and index is None:
        raise TravelError('This record no longer exists. Refresh the list.')
    row = dict(rows[index]) if index is not None else {k: '' for k in fields}
    row.update({k: str(v).strip() for k, v in values.items() if k in fields and k not in ('id', 'file', 'distance_km', *IMPORT_FIELDS)})
    row['id'] = record_id or ('p-' if kind == 'points' else 'r-') + uuid.uuid4().hex
    if kind == 'routes' and row.get('file'):
        check_row(row, kind, config(root))
    old_path = root/'data/routes'/row['file'] if kind == 'routes' and row.get('file') else None
    new_path = None
    prepared = None
    if kind == 'routes':
        segments = parse_gpx(gpx or old_path) if (gpx or old_path) else None
        if segments is None:
            raise TravelError('Choose a GPX file.')
        if gpx:
            prepared = prepare_route(gpx, config(root)['simplify_degrees'] if tolerance is None else tolerance)
            raw, cleaned, stats = prepared
            if any(r.get('original_sha256') == stats['original_sha256'] and r.get('id') != record_id for r in rows):
                raise TravelError('This exact GPX is already imported. Edit that route or use Replace GPX.')
            new_path = root/'data/routes'/('route-' + uuid.uuid4().hex + '.gpx')
            row['file'] = new_path.name
            row.update(stats)
        elif not row.get('original_file'):
            row['distance_km'] = f'{distance_km(segments):.1f}'
    check_row(row, kind, config(root))
    backup(root, [path] + ([old_path] if old_path else []))
    if index is None:
        rows.append(row)
    else:
        rows[index] = row
    try:
        if prepared:
            original = root/'data/routes_original'/row['original_file']
            if original.exists():
                if original.read_bytes() != raw:
                    raise TravelError('Archived original has changed. Restore it from backup before retrying.')
            else:
                atomic_bytes(original, raw)
            atomic_bytes(new_path, cleaned)
        write_table(path, fields, rows, delim)
    except Exception:
        if new_path:
            new_path.unlink(missing_ok=True)
        raise
    if new_path and old_path and old_path.exists():
        old_path.unlink()  # already backed up, CSV now points at the cleaned file
    return row['id']


def delete_record(kind, record_id, root=ROOT):
    root = Path(root)
    path = root/'data'/f'{kind}.csv'
    fields, rows, delim = read_table(path)
    row = next((r for r in rows if r.get('id') == record_id), None)
    if row is None:
        raise TravelError('Record not found.')
    gpx = root/'data/routes'/row['file'] if kind == 'routes' else None
    backup(root, [path] + ([gpx] if gpx else []))
    write_table(path, fields, [r for r in rows if r['id'] != record_id], delim)
    if gpx:
        gpx.unlink(missing_ok=True)


def build(root=ROOT, check_only=False):
    root = Path(root)
    cfg, records, warnings = load_records(root)
    if check_only:
        return f'Valid: {len(records["points"])} places; {len(records["routes"])} routes.' + ('\n'+'\n'.join(warnings) if warnings else '')
    try:
        from shapely.geometry import LineString
    except ImportError:
        raise TravelError('Shapely is missing. Run setup.cmd once, then reopen Start.cmd.') from None
    decimals, tolerance = cfg['coordinate_decimals'], cfg['simplify_degrees']
    layer_names = set(cfg['point_layers'] + cfg['route_modes'])
    layer_names.update(p.stem for p in (root/'build').glob('*.geojson'))
    layers = {name: [] for name in sorted(layer_names)}
    for i, r in enumerate(records['points']):
        props = {k:r[k] for k in ('name', 'country', 'date', 'description') if r.get(k)}
        if r.get('color'):
            props['_umap_options'] = {'color': r['color'], 'iconColor': r['color']}
        lon, lat = coordinates(r['lon'], r['lat'])
        layers[r['layer']].append({'type':'Feature', 'id':r.get('id') or f'legacy-point-{i}', 'properties':props,
                                  'geometry':{'type':'Point', 'coordinates':[round(lon,decimals),round(lat,decimals)]}})
    for r in records['routes']:
        parts = []
        for segment in r['_segments']:
            line = LineString(segment) if r.get('original_file') else LineString(segment).simplify(tolerance, preserve_topology=False)
            parts.append([[x,y] if r.get('original_file') else [round(x,decimals),round(y,decimals)] for x,y in line.coords])
        geometry = {'type':'LineString','coordinates':parts[0]} if len(parts)==1 else {'type':'MultiLineString','coordinates':parts}
        props = {k:r[k] for k in ('name','mode','date','notes','source') if r.get(k)}
        props['distance_km'] = round(r['_km'],1)
        for key in ('min_altitude_m', 'max_altitude_m'):
            if r.get(key):
                props[key] = number(r[key], key)
        layers[r['mode']].append({'type':'Feature','id':r.get('id') or r['file'],'properties':props,'geometry':geometry})
    report = ['# Travel log', '', f'Places: {len(records["points"])}', f'Routes: {len(records["routes"])}', '', '| Mode | Routes | km |', '|---|---:|---:|']
    for mode in cfg['route_modes']:
        rr = [r for r in records['routes'] if r['mode']==mode]
        report.append(f'| {mode} | {len(rr)} | {sum(r["_km"] for r in rr):.1f} |')
    report += ['', f'Total distance: {sum(r["_km"] for r in records["routes"]):.1f} km', '', 'Distances are calculated from source GPX segments, before display simplification.']
    report += ['', *warnings] if warnings else []
    stage = Path(tempfile.mkdtemp(prefix='.build-', dir=root))
    try:
        for name, feats in layers.items():
            if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
                raise TravelError(f'Unsafe layer filename: {name}')
            (stage/f'{name}.geojson').write_text(json.dumps({'type':'FeatureCollection','features':feats},ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
        (stage/'stats.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
        # Local optional import file, separate from the hosted output.
        exported = {'type':'umap','geometry':cfg.get('map_geometry'),'properties':cfg.get('map_properties',{}),'layers':[]}
        for name in cfg['route_modes'] + cfg['point_layers']:
            settings = dict(cfg.get('layer_settings',{}).get(name,{}), name=name, remoteData={})
            exported['layers'].append({'type':'FeatureCollection','properties':settings,'features':layers[name]})
        output = root/'build'
        previous = root/'backups/previous-build'
        previous.parent.mkdir(parents=True,exist_ok=True)
        if previous.exists():
            shutil.rmtree(previous)
        if output.exists():
            output.rename(previous)
        try:
            stage.rename(output)
            atomic_bytes(root/'exports/yatutbuv.umap',json.dumps(exported,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8'))
        except Exception:
            if output.exists():
                shutil.rmtree(output)
            if previous.exists():
                previous.rename(output)
            raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    total = sum(f.stat().st_size for f in (root/'build').glob('*.geojson'))
    return f'Built {len(records["points"])} places and {len(records["routes"])} routes ({total/1e6:.2f} MB).\nLocal export: exports/yatutbuv.umap\n'+'\n'.join(warnings)
