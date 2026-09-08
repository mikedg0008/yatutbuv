"""Route archive, cleaning and statistics regression tests."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import travel_core as c
import test_workflow as workflow
from test_workflow import gpx


class RouteImport(unittest.TestCase):
    setUp = workflow.Workflow.setUp
    tearDown = workflow.Workflow.tearDown
    features = workflow.Workflow.features

    def source(self):
        path=self.root/'raw.gpx'
        points=''.join(f'<trkpt lon="{i/100000}" lat="0"><ele>{i-20}</ele><time>2026-01-01T00:00:00Z</time></trkpt>' for i in range(101))
        path.write_text('<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'+points+'</trkseg></trk></gpx>')
        return path

    def row(self):
        return c.read_table(self.root/'data/routes.csv')[1][0]

    def import_route(self, path=None, tolerance=None):
        c.save_record('routes',{},self.root,record_id='r1',gpx=path or self.source(),tolerance=tolerance)
        return self.row()

    def test_archive_exact_and_clean_small_with_stats(self):
        source=self.source();raw=source.read_bytes()
        row=self.import_route(source)
        self.assertEqual((self.root/'data/routes_original'/row['original_file']).read_bytes(),raw)
        self.assertEqual(row['original_sha256'],hashlib.sha256(raw).hexdigest())
        cleaned=(self.root/'data/routes'/row['file']).read_bytes()
        self.assertNotIn(b'<ele',cleaned);self.assertNotIn(b'<time',cleaned)
        self.assertLess(len(cleaned),len(raw)/5)
        self.assertEqual(row['original_points'],'101');self.assertEqual(row['map_points'],'2')
        self.assertEqual(row['min_altitude_m'],'-20.0');self.assertEqual(row['max_altitude_m'],'80.0')
        c.build(self.root)
        props=self.features('drive')[0]['properties']
        self.assertEqual(props['max_altitude_m'],80.0)
        self.assertNotIn('original_file',props)

    def test_metadata_edit_does_not_recalculate_simplified_distance(self):
        row=self.import_route()
        before={k:row[k] for k in ['file','distance_km',*c.IMPORT_FIELDS]}
        c.save_record('routes',{'name':'Renamed'},self.root,record_id='r1')
        self.assertEqual(before,{k:self.row()[k] for k in before})

    def test_reclean_from_original_no_cumulative_loss(self):
        row=self.import_route()
        archived=self.root/'data/routes_original'/row['original_file']
        row=self.import_route(archived,tolerance=0)
        self.assertEqual(row['map_points'],'101')
        c.build(self.root)
        self.assertEqual(len(self.features('drive')[0]['geometry']['coordinates']),101)
        self.assertEqual(len(list(archived.parent.glob('*.gpx'))),1)

    def test_replace_then_delete_keeps_both_originals(self):
        first=self.import_route()
        second=self.root/'better.gpx';second.write_text(gpx([(1,1),(2,2)]))
        last=self.import_route(second)
        self.assertEqual(last['min_altitude_m'],'')
        c.delete_record('routes','r1',self.root)
        for row in [first,last]:
            self.assertTrue((self.root/'data/routes_original'/row['original_file']).exists())

    def test_duplicate_blocked_without_changing_index(self):
        source=self.source();self.import_route(source)
        before=(self.root/'data/routes.csv').read_bytes()
        with self.assertRaisesRegex(c.TravelError,'already imported'):
            c.save_record('routes',{'name':'Duplicate','mode':'drive'},self.root,gpx=source)
        self.assertEqual(before,(self.root/'data/routes.csv').read_bytes())

    def test_failed_save_keeps_archive_but_removes_new_active_file(self):
        source=self.source();before=(self.root/'data/routes.csv').read_bytes()
        with patch.object(c,'write_table',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.import_route(source)
        self.assertEqual(before,(self.root/'data/routes.csv').read_bytes())
        self.assertEqual([p.name for p in (self.root/'data/routes').glob('*')],['a.gpx'])
        self.assertEqual(len(list((self.root/'data/routes_original').glob('*.gpx'))),1)

    def test_missing_archive_warns_but_build_works(self):
        row=self.import_route()
        (self.root/'data/routes_original'/row['original_file']).unlink()
        self.assertIn('original archive missing',c.build(self.root))

    def test_invalid_elevation_and_missing_elevation_not_zero(self):
        path=self.root/'missing.gpx'
        path.write_text('<gpx><rte><rtept lon="0" lat="0"><ele>nan</ele></rtept><rtept lon="1" lat="0"/></rte></gpx>')
        row=self.import_route(path)
        self.assertEqual(row['min_altitude_m'],'');self.assertEqual(row['max_altitude_m'],'')

    def test_cleaner_preserves_segments_and_original_distance(self):
        path=self.root/'segments.gpx'
        path.write_text(gpx([(0,0),(0.00001,0.00001),(0.00002,0)],[(100,0),(100.01,0)]))
        expected=c.distance_km(c.parse_gpx(path))
        row=self.import_route(path)
        self.assertAlmostEqual(float(row['distance_km']),expected,places=6)
        self.assertEqual(len(c.parse_gpx(self.root/'data/routes'/row['file'])),2)
        c.build(self.root)
        self.assertEqual(self.features('drive')[0]['properties']['distance_km'],round(expected,1))

    def test_bad_input_and_tolerance(self):
        path=self.root/'bad.gpx';path.write_text('<gpx>')
        with self.assertRaises(c.TravelError):c.prepare_route(path,0.0001)
        path=self.source()
        for tolerance in [-1, 'nan', 1]:
            with self.assertRaises(c.TravelError):c.prepare_route(path,tolerance)

    def test_existing_archive_corruption_never_overwritten(self):
        source=self.source();row=self.import_route(source)
        archive=self.root/'data/routes_original'/row['original_file'];archive.write_bytes(b'changed')
        before=(self.root/'data/routes.csv').read_bytes()
        with self.assertRaisesRegex(c.TravelError,'has changed'):self.import_route(source)
        self.assertEqual(archive.read_bytes(),b'changed')
        self.assertEqual(before,(self.root/'data/routes.csv').read_bytes())

    def test_reclean_rejects_changed_archive(self):
        row=self.import_route()
        archive=self.root/'data/routes_original'/row['original_file']
        archive.write_text(gpx([(0,0),(1,0)]))
        with self.assertRaisesRegex(c.TravelError,'has changed'):
            self.import_route(archive)

    def test_old_csv_migration_preserves_values_and_gpx(self):
        fields=c.ROUTE_FIELDS[:8]
        c.write_table(self.root/'data/routes.csv',fields,self.routes)
        before=(self.root/'data/routes/a.gpx').read_bytes()
        c.ensure_ids(self.root)
        row=self.row()
        self.assertEqual({k:row[k] for k in fields},self.routes[0])
        self.assertTrue(all(row[k]=='' for k in c.IMPORT_FIELDS))
        self.assertEqual(before,(self.root/'data/routes/a.gpx').read_bytes())
        self.assertFalse((self.root/'data/routes_original').exists())

    def test_active_write_failure_keeps_old_index_and_source(self):
        original=c.atomic_bytes
        before=(self.root/'data/routes.csv').read_bytes()
        def fail(path,data):
            if Path(path).parent.name=='routes':raise OSError('disk full')
            return original(path,data)
        with patch.object(c,'atomic_bytes',side_effect=fail):
            with self.assertRaises(OSError):self.import_route()
        self.assertEqual(before,(self.root/'data/routes.csv').read_bytes())
        self.assertTrue((self.root/'data/routes/a.gpx').exists())


if __name__=='__main__':unittest.main()
