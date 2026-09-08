"""Regression tests for data loss, replacement, GPX geometry and publishing.
Run: python -m unittest discover -s tests -v
"""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import travel_core as c
import publish as pub
from project_lock import project_lock


def gpx(*segments, route=False):
    tag='rtept' if route else 'trkpt'
    bodies=[]
    for segment in segments:
        pts=''.join(f'<{tag} lon="{x}" lat="{y}"/>' for x,y in segment)
        bodies.append('<rte>'+pts+'</rte>' if route else '<trk><trkseg>'+pts+'</trkseg></trk>')
    return '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">'+''.join(bodies)+'</gpx>'


class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'data/routes').mkdir(parents=True)
        self.cfg={'map_url':'https://example.invalid','point_layers':['Places','Hotels'],
                  'route_modes':['drive','train','ride','waterways'],'coordinate_decimals':5,'simplify_degrees':0.0001,
                  'map_properties':{'name':'Test'},'map_geometry':None,'layer_settings':{}}
        (self.root/'map_config.json').write_text(json.dumps(self.cfg))
        self.points=[dict(zip(c.POINT_FIELDS,['p1','Places','PL','Warsaw','52.2','21.0','2026','Original note','']))]
        self.routes=[dict(zip(c.ROUTE_FIELDS,['r1','a.gpx','drive','Journey','2026','999','Route note','']))]
        c.write_table(self.root/'data/points.csv',c.POINT_FIELDS,self.points)
        c.write_table(self.root/'data/routes.csv',c.ROUTE_FIELDS,self.routes)
        (self.root/'data/routes/a.gpx').write_text(gpx([(0,0),(0.01,0)]))

    def tearDown(self):self.tmp.cleanup()
    def features(self,name):return json.loads((self.root/f'build/{name}.geojson').read_text())['features']

    def test_missing_source_never_changes_existing_build(self):
        c.build(self.root)
        old={p.name:p.read_bytes() for p in (self.root/'build').iterdir()}
        (self.root/'data/routes/a.gpx').unlink()
        with self.assertRaises(c.TravelError):c.build(self.root)
        self.assertEqual(old,{p.name:p.read_bytes() for p in (self.root/'build').iterdir()})

    def test_missing_csv_column_fails(self):
        c.write_table(self.root/'data/points.csv',['name'],[{'name':'bad'}])
        with self.assertRaisesRegex(c.TravelError,'missing columns'):c.build(self.root)

    def test_replacement_preserves_identity_metadata_and_changes_distance(self):
        source=self.root/'better.gpx';source.write_text(gpx([(0,0),(0.1,0)]))
        c.save_record('routes',{},self.root,record_id='r1',gpx=source)
        _,rows,_=c.read_table(self.root/'data/routes.csv')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['id'],'r1');self.assertEqual(rows[0]['notes'],'Route note')
        self.assertEqual(rows[0]['date'],'2026');self.assertFalse((self.root/'data/routes/a.gpx').exists())
        self.assertAlmostEqual(float(rows[0]['distance_km']),11.1,places=1)
        self.assertTrue(list((self.root/'backups').glob('edit-*/data/routes/a.gpx')))
        c.build(self.root);self.assertEqual(len(self.features('drive')),1)

    def test_removing_index_row_excludes_leftover_gpx_and_clears_last_layer(self):
        c.build(self.root)
        c.write_table(self.root/'data/routes.csv',c.ROUTE_FIELDS,[])
        result=c.build(self.root)
        self.assertEqual(self.features('drive'),[])
        self.assertIn('1 unindexed GPX',result)
        self.assertIn('Total distance: 0.0 km',(self.root/'build/stats.md').read_text())

    def test_delete_last_point_and_route(self):
        c.build(self.root)
        c.delete_record('points','p1',self.root);c.delete_record('routes','r1',self.root)
        c.build(self.root)
        self.assertEqual(self.features('Places'),[]);self.assertEqual(self.features('drive'),[])
        self.assertFalse((self.root/'data/routes/a.gpx').exists())

    def test_track_segments_are_not_joined(self):
        (self.root/'data/routes/a.gpx').write_text(gpx([(0,0),(0.01,0)],[(100,0),(100.01,0)]))
        c.build(self.root);f=self.features('drive')[0]
        self.assertEqual(f['geometry']['type'],'MultiLineString')
        self.assertEqual(len(f['geometry']['coordinates']),2)
        self.assertAlmostEqual(f['properties']['distance_km'],2.2,places=1)

    def test_gpx_route_points_and_invalid_coordinates(self):
        path=self.root/'route.gpx';path.write_text(gpx([(0,0),(1,0)],route=True))
        self.assertEqual(len(c.parse_gpx(path)[0]),2)
        path.write_text(gpx([(0,0),(1,91)]))
        with self.assertRaises(c.TravelError):c.parse_gpx(path)

    def test_nonfinite_coordinates_and_bad_calendar_dates(self):
        for value in ['nan','inf','-inf']:
            with self.assertRaises(c.TravelError):c.coordinates(value,0)
        with self.assertRaises(c.TravelError):c.check_date('2026-02-30')
        for value in ['', '2026','2024-02-29']:c.check_date(value)

    def test_semicolon_comma_decimal_and_extra_columns_preserved(self):
        rows=[dict(self.points[0],lat='52,2',lon='21,0',extra='keep me')]
        fields=c.POINT_FIELDS+['extra'];c.write_table(self.root/'data/points.csv',fields,rows,';')
        c.save_record('points',{'name':'Corrected'},self.root,record_id='p1')
        f,rr,delimiter=c.read_table(self.root/'data/points.csv')
        self.assertEqual(delimiter,';');self.assertEqual(rr[0]['extra'],'keep me')
        c.build(self.root);self.assertEqual(self.features('Places')[0]['geometry']['coordinates'],[21.0,52.2])

    def test_id_upgrade_is_once_and_preserves_existing_values(self):
        row={k:v for k,v in self.points[0].items() if k!='id'}
        c.write_table(self.root/'data/points.csv',c.POINT_FIELDS[1:],[row])
        c.ensure_ids(self.root)
        first=(self.root/'data/points.csv').read_bytes()
        c.ensure_ids(self.root);self.assertEqual(first,(self.root/'data/points.csv').read_bytes())
        _,rr,_=c.read_table(self.root/'data/points.csv')
        self.assertEqual({k:v for k,v in rr[0].items() if k!='id'},row)

    def test_duplicate_file_and_path_escape_rejected(self):
        self.routes.append(dict(self.routes[0],id='r2'))
        c.write_table(self.root/'data/routes.csv',c.ROUTE_FIELDS,self.routes)
        with self.assertRaisesRegex(c.TravelError,'referenced more than once'):c.build(self.root)
        self.routes[0]['file']='../outside.gpx'
        c.write_table(self.root/'data/routes.csv',c.ROUTE_FIELDS,self.routes[:1])
        with self.assertRaises(c.TravelError):c.build(self.root)

    def test_bad_replacement_leaves_record_and_gpx_intact(self):
        before=(self.root/'data/routes.csv').read_bytes()
        bad=self.root/'bad.gpx';bad.write_text('not xml')
        with self.assertRaises(c.TravelError):c.save_record('routes',{},self.root,record_id='r1',gpx=bad)
        self.assertEqual(before,(self.root/'data/routes.csv').read_bytes())
        self.assertTrue((self.root/'data/routes/a.gpx').exists())

    def test_csv_write_failure_during_replacement_keeps_original(self):
        before=(self.root/'data/routes.csv').read_bytes()
        path=self.root/'new.gpx';path.write_text(gpx([(0,0),(1,0)]))
        with patch.object(c,'write_table',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):c.save_record('routes',{},self.root,record_id='r1',gpx=path)
        self.assertEqual(before,(self.root/'data/routes.csv').read_bytes())
        self.assertEqual([p.name for p in (self.root/'data/routes').glob('*.gpx')],['a.gpx'])

    def test_repeated_builds_identical_and_export_complete(self):
        c.build(self.root)
        first={p.name:p.read_bytes() for p in (self.root/'build').iterdir()}
        c.build(self.root)
        self.assertEqual(first,{p.name:p.read_bytes() for p in (self.root/'build').iterdir()})
        export=json.loads((self.root/'exports/yatutbuv.umap').read_text())
        self.assertEqual(sum(len(x['features']) for x in export['layers']),2)
        self.assertTrue(all(x['properties']['remoteData']=={} for x in export['layers']))

    def test_export_write_failure_restores_previous_build(self):
        c.build(self.root)
        before={p.name:p.read_bytes() for p in (self.root/'build').iterdir()}
        old_export=(self.root/'exports/yatutbuv.umap').read_bytes()
        (self.root/'data/routes/a.gpx').write_text(gpx([(0,0),(1,0)]))
        with patch.object(c,'atomic_bytes',side_effect=OSError('export locked')):
            with self.assertRaises(OSError):c.build(self.root)
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'build').iterdir()})
        self.assertEqual(old_export,(self.root/'exports/yatutbuv.umap').read_bytes())

    def test_second_process_cannot_lock_project(self):
        with project_lock(self.root):
            with self.assertRaises(c.TravelError):
                with project_lock(self.root):pass

    def test_publish_real_local_remote_and_retry_no_changes(self):
        # Real git integration, using a temporary local bare remote only.
        remote=self.root/'remote.git'
        subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
        def git(*args):return subprocess.run(['git',*args],cwd=self.root,check=True,capture_output=True,text=True)
        git('init');git('config','user.name','Test');git('config','user.email','test@example.invalid')
        git('add','data','map_config.json');git('commit','-m','Initial')
        git('remote','add','origin',str(remote));git('push','-u','origin','HEAD')
        secret=self.root/'build_private';secret.mkdir();(secret/'private.txt').write_text('Do not stage')
        raw=self.root/'new.gpx';raw.write_text(gpx([(0,0),(0.1,0)]))
        c.save_record('routes',{},self.root,record_id='r1',gpx=raw)
        result=pub.publish(self.root);self.assertIn('Pushed',result)
        self.assertNotIn('private',git('ls-files').stdout)
        self.assertNotIn('routes_original',git('ls-files').stdout)
        head=git('rev-parse','HEAD').stdout
        pub.publish(self.root);self.assertEqual(head,git('rev-parse','HEAD').stdout)
        (self.root/'unrelated.txt').write_text('Unrelated');git('add','unrelated.txt')
        with self.assertRaisesRegex(c.TravelError,'Unrelated'):pub.publish(self.root)

    def test_publish_commit_failure_stops_before_push(self):
        calls=[]
        def fake(root,*args,**kwargs):
            calls.append(args)
            if args[0]=='rev-parse':return subprocess.CompletedProcess(args,0,'origin/main','')
            if args[0]=='diff' and '--quiet' in args:return subprocess.CompletedProcess(args,1,'','')
            if args[0]=='commit':raise c.TravelError('Commit rejected')
            return subprocess.CompletedProcess(args,0,'','')
        with patch.object(pub,'git',fake):
            with self.assertRaisesRegex(c.TravelError,'Commit rejected'):pub.publish(self.root)
        self.assertFalse(any(a[0]=='push' for a in calls))


if __name__=='__main__':unittest.main()
