"""Gradients, without Earth Engine: the statistics of a map by bands of another variable (services.region_stats with
zones: the elevation bands) and its profile along a line with the elevation (services.transect): their errors before
Earth Engine, citations, README, report, viewer of results, command line, MCP server, assistant and the Earth Engine app
(gee/core.js in node: the same cuts of the line). tests/test_ee.py computes them in Earth Engine."""

import json
import os
import shutil
import subprocess

import pytest

from monitoreo import readme, references, report, services

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
ZONES = {'variable': 'ELEVATION', 'sensor': 'Copernicus', 'breaks': [1500, 2000]}
LINE = [[-3.60, 37.15], [-3.45, 37.10], [-3.39, 37.06]]


def test_the_zones_before_earth_engine():
	assert services.zones_of(None) is None and services.zones_of(ZONES) == [1500.0, 2000.0]
	assert services.zone_name(ZONES) == 'ELEVATION (Copernicus) bands'
	for zones, text in (('ELEVATION', 'zones is a variable of the catalog'), ({'variable': 'ELEVATION'}, 'at least one'),
	                    (dict(ZONES, bands=3), 'unknown keys bands')):
		with pytest.raises(ValueError, match=text):
			services.region_stats(REGION, 'NDVI', 'Modis', '2020-01-01', '2020-12-31', zones=zones)


def test_the_line_of_a_profile():
	assert services.transect_line(LINE) == LINE
	assert services.transect_line({'geojson': {'type': 'Feature', 'geometry': {'type': 'LineString',
	                                                                         'coordinates': LINE}}}) == LINE
	assert services.transect_line(json.dumps({'type': 'LineString', 'coordinates': LINE})) == LINE
	for bad, text in (([[0, 0]], 'two points or more'), ([[200, 0], [0, 0]], 'in degrees'), ('x', 'list of points'),
	                  ({'type': 'Polygon'}, 'list of points')):
		with pytest.raises(ValueError, match=text):
			services.transect_line(bad)
	assert services.transect_cuts(1000.0, 300.0) == [300.0, 600.0, 900.0]
	assert services.transect_cuts(900.0, 300.0) == [300.0, 600.0]


ZONE_ARGS = {'region': REGION, 'variable': 'NDVI', 'sensor': 'Modis', 'start': '2023-06-01', 'end': '2023-08-31',
             'stats': ['p25', 'p50', 'p75'], 'zones': ZONES}
TRANSECT = {'line': LINE, 'variable': 'LST', 'sensor': 'Modis', 'start': '2023-07-01', 'end': '2023-08-31'}


def test_what_the_gradients_cite():
	ids = [r['id'] for r in references.cite('region_stats', ZONE_ARGS)['references']]
	assert {'mod13q1', 'wu2020', 'monitoreo'} <= set(ids) and any('DEM' in r['citation'] or 'Copernicus' in
	                                                                 r['citation'] for r in references.cite(
		'region_stats', ZONE_ARGS)['references'])
	cited = references.cite('transect', TRANSECT)
	assert 'wu2020' in [r['id'] for r in cited['references']] and any('Copernicus' in c for c in cited['credits'])


def test_the_readme_and_the_report_of_the_gradients(tmp_path):
	assert report.item_title('region_stats', ZONE_ARGS) == \
		'Statistics of NDVI (MODIS) by ELEVATION (Copernicus) bands, 1 Jun 2023 - 31 Aug 2023'
	facts = dict(report.item_facts('region_stats', ZONE_ARGS, {'scale': 250.0}))
	assert facts['Zones'] == 'ELEVATION (Copernicus) bands, cut at 1500, 2000' and 'zonal statistics' in facts['Method']
	result = {'rows': [{'region': 'bbox', 'zone': 0, 'zone_label': 'below 1500 m', 'p25': 0.2, 'p50': 0.3, 'p75': 0.4,
	                    'n_pixels': 10}], 'stats': ['p25', 'p50', 'p75'], 'unit': '[unitless]'}
	labels, body = report.item_table('region_stats', result, ZONE_ARGS)
	assert labels[0] == 'Zone' and body[0][0] == 'below 1500 m'
	csv = tmp_path / 'profile.csv'
	csv.write_text('distance_m,lon,lat,value,elevation\n500,-3.59,37.15,43.6,684\n', encoding='utf-8')
	res = {'rows': [], 'csv': str(csv), 'length_m': 21379.1, 'spacing': 1000.0, 'unit': '[°C]', 'scale': 1000.0}
	text = ' '.join(readme.text('transect', TRANSECT, res, computed='2026-11-14T10:00:00+01:00').split())
	assert 'distance_m: distance along the line to the middle of the segment (m)' in text
	assert 'Line: 21.38 km, 3 points; segments of 1,000 m' in text and 'as the transects of geemap' in text
	assert 'Region:' not in text and 'Temporal metric: median' in text
	assert 'value: mean of the map of the variable (°C) over the pixels that the segment crosses' in text
	assert report.item_title('transect', TRANSECT).startswith('Profile of LST (MODIS) along a line')


def test_the_viewer_of_results_draws_the_gradients(tmp_path):
	from monitoreo import publish
	csv = tmp_path / 'zones.csv'
	csv.write_text('region,zone,zone_label,zone_from,zone_to,p25,p50,p75,n_pixels\n'
	               'bbox,0,below 1500 m,,1500,0.2,0.3,0.4,10\n', encoding='utf-8')
	profile = tmp_path / 'profile.csv'
	profile.write_text('distance_m,lon,lat,value,elevation\n500,-3.59,37.15,43.6,684\n', encoding='utf-8')
	spec = {'title': 'Gradients', 'summary': 'Gradients', 'region': {'name': 'Sierra Nevada'},
	        'results': [{'tool': 'region_stats', 'args': ZONE_ARGS,
	                     'result': {'csv': str(csv), 'stats': ['p25', 'p50', 'p75'], 'unit': '', 'ylabel': 'NDVI'}},
	                    {'tool': 'transect', 'args': TRANSECT, 'result': {'csv': str(profile), 'unit': '[°C]'}}]}
	folder = tmp_path / 'report'
	folder.mkdir()
	rep = publish.build(spec, 'gradients', str(tmp_path), [], None, str(folder))
	assert [r['chart'] for r in rep['results']] == ['zones', 'transect']
	assert rep['results'][0]['stats'] == ['p25', 'p50', 'p75'] and publish.check_report(rep, str(folder)) == []


@pytest.fixture
def calls(monkeypatch):
	out = []

	def stats(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
	          interannual='mean', season=None, quality=None, stats=None, scale=None, zones=None, csv=None, chart=None,
	          **source):
		out.append({'tool': 'region_stats', 'zones': zones, 'csv': csv, 'chart': chart, 'stats': stats})
		return {'rows': [{'region': 'bbox', 'zone_label': 'below 1500 m', 'p50': 0.3, 'n_pixels': 10}],
		        'stats': stats or ['p50'], 'scale': 250.0, 'unit': '', 'title': 'NDVI by bands', 'csv': csv, 'chart': None}

	def transect(line, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
	             interannual='mean', season=None, quality=None, spacing=None, points=100, scale=None, csv=None,
	             chart=None, **source):
		out.append({'tool': 'transect', 'line': line, 'variable': variable, 'spacing': spacing, 'points': points,
		            'csv': csv})
		return {'rows': [{'distance_m': 500.0, 'value': 43.6, 'elevation': 684.0, 'lon': -3.59, 'lat': 37.15}],
		        'length_m': 1000.0, 'spacing': 1000.0, 'scale': 1000.0, 'unit': '[°C]', 'title': 'LST along a line',
		        'csv': csv, 'chart': None}
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	monkeypatch.setattr(services, 'region_stats', stats)
	monkeypatch.setattr(services, 'transect', transect)
	return out


def test_the_command_line_computes_the_gradients(calls, capsys):
	from monitoreo import cli
	cli.main(['stats', 'NDVI', '--sensor', 'Modis', '--region', json.dumps(REGION), '--start', '2023-06-01', '--end',
	          '2023-08-31', '--stats', 'p50', '--zones', json.dumps(ZONES)])
	assert calls[-1]['zones'] == ZONES and 'below 1500 m' in capsys.readouterr().out
	cli.main(['transect', 'LST', '--sensor', 'Modis', '--line', json.dumps(LINE), '--start', '2023-07-01', '--end',
	          '2023-08-31', '--spacing', '500'])
	assert calls[-1]['line'] == json.dumps(LINE) and calls[-1]['spacing'] == 500.0
	assert '43.6' in capsys.readouterr().out and 'monitoreo transect' in cli.__doc__


def test_the_mcp_server_computes_the_gradients(calls, monkeypatch, tmp_path):
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	out = mcp_server.region_stats(REGION, 'NDVI', 'Modis', '2023-06-01', '2023-08-31', stats=['p50'], zones=ZONES)
	assert calls[-1]['zones'] == ZONES and calls[-1]['csv'].endswith('.csv') and isinstance(out, list)
	assert isinstance(mcp_server.region_stats(REGION, 'NDVI', 'Modis', '2023-06-01', '2023-08-31'), str)  # as before
	out = mcp_server.transect(LINE, 'LST', 'Modis', '2023-07-01', '2023-08-31')
	assert calls[-1]['line'] == LINE and json.loads(out[0])['rows'][0]['elevation'] == 684.0
	assert 'transect' in mcp_server.INSTRUCTIONS


def test_the_assistant_knows_the_gradients():
	from monitoreo import assistant
	assert 'transect' in assistant.RESULTS and 'transect' in assistant.PROMPT and 'zones' in assistant.PROMPT


APP = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
global.ee = new Proxy({}, {get: function () { return function () { return {}; }; }});
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[1], f), 'utf8'), {filename: f});
});
var mo = global.MonitorEO;
process.stdout.write(JSON.stringify({
	cuts: input.cuts.map(function (c) { return mo.transectCuts(c[0], c[1]); }),
	rows: mo.transectRows(input.features, [300, 600], 700),
	zones: mo.zoneRows(input.zones, mo.breakClasses([1500], 'm', 'en'))
}));
"""


def test_the_app_has_the_same_profiles():
	if not shutil.which('node'):
		pytest.skip('no node')
	cases = [(1000.0, 300.0), (900.0, 300.0), (21379.1, 1000.0)]
	features = [{'properties': {'i': 1, 'value': 2.0, 'elevation': 900.0, 'centre': [-3.5, 37.1]}},
	            {'properties': {'i': 0, 'value': 1.0, 'elevation': 800.0, 'centre': [-3.6, 37.2]}}]
	zones = [{'properties': {'name': 'park', 'groups': [{'zone': 1, 'p25': 1, 'p50': 2, 'p75': 3, 'mean': 2,
	                                                      'count': 5}]}}]
	gee = os.path.join(os.path.dirname(__file__), '..', 'gee')
	run = subprocess.run(['node', '-e', APP, gee], input=json.dumps({'cuts': cases, 'features': features,
	                                                                  'zones': zones}),
	                     capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	assert out['cuts'] == [services.transect_cuts(a, b) for a, b in cases]
	assert [r['distance_m'] for r in out['rows']] == [150, 450, 650] and out['rows'][2]['value'] is None
	assert out['rows'][0] == {'distance_m': 150, 'lon': -3.6, 'lat': 37.2, 'value': 1.0, 'elevation': 800.0}
	assert [(r['zone_label'], r['p50'], r['n_pixels']) for r in out['zones']] == [('below 1500 m', None, 0),
	                                                                            ('1500 m or more', 2, 5)]
