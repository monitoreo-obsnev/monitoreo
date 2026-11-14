"""Gradients, without Earth Engine: the statistics of a map by bands of another variable (services.region_stats with
zones: the elevation bands) and its profile along a line with the elevation (services.transect): their errors before
Earth Engine, citations, README, report, viewer of results, command line, MCP server, assistant and the Earth Engine app
(gee/core.js in node: the same cuts of the line). tests/test_ee.py computes them in Earth Engine."""

import json
import os
import random
import shutil
import subprocess
import types

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
	# the period of a variable with dates, [start, end] as in the conditions of where: a text, one date or three were a
	# TypeError after Earth Engine started, or a period to today
	ndvi = {'variable': 'NDVI', 'sensor': 'Modis', 'breaks': [0.3]}
	assert services.zones_of(dict(ndvi, period=['2023-01-01', '2023-12-31'])) == [0.3]
	for period in ('2023-01-01/2023-12-31', ['2023-01-01'], ['2023-01-01', '2023-06-30', '2023-12-31']):
		with pytest.raises(ValueError, match=r'the period of zones on NDVI is \[start, end\]'):
			services.region_stats(REGION, 'LST', 'Modis', '2020-01-01', '2020-12-31', zones=dict(ndvi, period=period))


class _Stop(Exception):
	pass


def test_the_zones_have_the_percentiles_25_and_75_by_default(monkeypatch):
	"""region_stats with zones and the statistics by default also computes p25 and p75, the band of its chart (as the
	QGIS plugin and the Earth Engine app); without zones, or with the statistics given, those."""
	checked = []
	monkeypatch.setattr(services.composite, 'check_metric', checked.append)

	def build(*args):  # where Earth Engine would start
		raise _Stop

	monkeypatch.setattr(services, '_build', build)
	for zones, stats, expected in ((ZONES, None, services.REGION_STATS_ZONES), (None, None, services.REGION_STATS),
	                               (ZONES, ['p5', 'p50', 'p95'], ['p5', 'p50', 'p95'])):
		checked.clear()
		with pytest.raises(_Stop):
			services.region_stats(REGION, 'NDVI', 'Modis', '2023-06-01', '2023-08-31', stats=stats, zones=zones)
		assert checked == list(expected)
	assert set(services.REGION_STATS) | {'p25', 'p75'} == set(services.REGION_STATS_ZONES)


def test_the_chart_of_the_zones_says_its_band(monkeypatch):
	"""charts.zones_png: the median (or else the mean, or the first statistic) with the band of the percentiles 25 and
	75, or else 5 and 95 if the statistics have them and not those, or no band, named in the legend (as the wiki says)."""
	axes = pytest.importorskip('matplotlib.axes')
	from monitoreo import charts
	labels, lines = [], []
	plot = axes.Axes.plot
	monkeypatch.setattr(axes.Axes, 'fill_between', lambda self, x, lo, hi, **kw: labels.append(kw.get('label')))
	monkeypatch.setattr(axes.Axes, 'plot', lambda self, *args, **kw: lines.append(kw.get('label')) or
	                    plot(self, *args, **kw))
	rows = [{'region': 'bbox', 'zone_label': label, **{s: 0.1 * i for i, s in enumerate(services.REGION_STATS_ZONES)}}
	        for label in ('below 1500 m', '1500 m or more')]
	for stats, line, band in ((services.REGION_STATS_ZONES, 'p50', ['p25 to p75']),
	                          (services.REGION_STATS, 'p50', ['p5 to p95']), (['p50'], 'p50', []),
	                          (['p5', 'p50'], 'p50', []), (['cv', 'mean'], 'mean', []),
	                          (['std', 'p5', 'p95'], 'std', ['p5 to p95'])):
		labels.clear()
		lines.clear()
		assert charts.zones_png(rows, list(stats)).startswith(b'\x89PNG')
		assert (lines, labels) == ([line], band), stats


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
	# 100 × (L / 100) falls a hair short of L: a cut 3.6e-12 m before the end made a 101st segment of 0 m
	assert len(services.transect_cuts(29688.37984445807, 29688.37984445807 / 100)) == 99


def test_the_cuts_of_lines_of_any_length():
	"""Whatever the length of the line, POINTS segments with the spacing by default (its length / POINTS), and segments
	of STEP metres but the last, which is never of 0 m (no cut within a millionth of a step of the end)."""
	rnd = random.Random(2026)
	for _ in range(20000):
		length = rnd.uniform(100, 200000)
		points = rnd.choice([2, 10, 50, 100, 1000])
		assert len(services.transect_cuts(length, length / points)) == points - 1, (length, points)
		step = rnd.choice([10.0, 30.0, 250.0, 1000.0, length / points])
		cuts = services.transect_cuts(length, step)
		assert cuts == [step * i for i in range(1, len(cuts) + 1)]
		assert step * 1e-6 < length - (cuts[-1] if cuts else 0) <= step * (1 + 1e-6), (length, step)


class _List:
	"""A fake ee.List: its items (get out of them fails, as List.get of Earth Engine)."""

	def __init__(self, items):
		self.items = list(items)

	@staticmethod
	def sequence(start, end):
		return _List(range(start, int(end) + 1))

	def size(self):
		return types.SimpleNamespace(subtract=lambda k: len(self.items) - k)

	def get(self, i):
		return self.items[i]

	def map(self, fn):
		return [fn(i) for i in self.items]


class _Line:
	"""A fake ee.Geometry of a line of LENGTH metres that Earth Engine cuts in PIECES segments."""

	def __init__(self, length, pieces):
		self.metres, self.pieces, self.cuts = length, pieces, None

	def length(self, max_error):
		return types.SimpleNamespace(getInfo=lambda: self.metres)

	def cutLines(self, cuts, max_error):  # noqa: N802 (the names of Earth Engine)
		self.cuts = cuts
		return types.SimpleNamespace(geometries=lambda: [_Segment(i) for i in range(self.pieces)])

	def buffer(self, distance, max_error=None):
		return self


class _Segment:
	def __init__(self, i):
		self.i = i

	def buffer(self, distance, max_error=None):
		return self

	def centroid(self, max_error):
		return types.SimpleNamespace(coordinates=lambda: [-3.6 + self.i / 1000, 37.1])


class _Image:
	def rename(self, name):
		return self

	def reduceRegions(self, collection, **kwargs):  # noqa: N802
		return types.SimpleNamespace(getInfo=lambda: {'features': [
			{'properties': dict(f['properties'], value=float(f['properties']['i']), elevation=1000.0)}
			for f in collection]})


def test_the_profile_takes_the_segments_that_earth_engine_gives(monkeypatch):
	"""services.transect without Earth Engine: a line of 29,688.38 m in 100 segments (not 101), and the rows of all of
	them even if Earth Engine measures the line a hair shorter and cuts it in one segment fewer (the last row then
	empty), not an error of List.get."""
	length = 29688.37984445807
	for pieces in (100, 99):
		line = _Line(length, pieces)
		geometry = lambda g: g  # noqa: E731
		geometry.LineString = lambda coords: line
		monkeypatch.setattr(services, 'ee', types.SimpleNamespace(
			Geometry=geometry, List=_List, Feature=lambda g, props: {'properties': props},
			FeatureCollection=lambda fs: fs, Image=types.SimpleNamespace(cat=lambda images: _Image()),
			Reducer=types.SimpleNamespace(mean=lambda: None)))
		monkeypatch.setattr(services.variables, 'image', lambda spec, geom, scale: _Image())
		p = services.transect(LINE, 'NDVI', 'Sentinel-2', '2023-06-01', '2023-08-31')
		assert line.cuts == services.transect_cuts(length, length / 100) and len(line.cuts) == 99
		assert p['spacing'] == length / 100 and len(p['rows']) == 100
		assert [r['value'] for r in p['rows']] == [float(i) for i in range(pieces)] + [None] * (100 - pieces)
		assert p['rows'][-1]['distance_m'] == pytest.approx(length - length / 200)


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
	# the unit of zone_from and zone_to: that of the variable of the zones, not that of the map (the column unit)
	zones_csv = tmp_path / 'zones.csv'
	zones_csv.write_text('region,zone,zone_label,zone_from,zone_to,p50,n_pixels,unit\n'
	                     'bbox,0,below 1500 m,,1500,0.3,10,1\n', encoding='utf-8')
	for zones, unit in ((ZONES, '(m; UDUNITS m)'), ({'variable': 'NDVI', 'sensor': 'Modis', 'breaks': [0.3]},
	                                                '(dimensionless; UDUNITS 1)')):
		text = ' '.join(readme.text('region_stats', dict(ZONE_ARGS, zones=zones), dict(result, csv=str(zones_csv)),
		                            computed='2026-11-14T10:00:00+01:00').split())
		assert f'zone_from: lowest value of the variable of the zones in the zone {unit} (empty: no limit)' in text
		assert f'zone_to: value of the variable of the zones where the zone ends, not in it {unit}' in text
	csv = tmp_path / 'profile.csv'
	csv.write_text('distance_m,lon,lat,value,elevation\n500,-3.59,37.15,43.6,684\n', encoding='utf-8')
	res = {'rows': [], 'csv': str(csv), 'length_m': 21379.1, 'spacing': 1000.0, 'unit': '[°C]', 'scale': 1000.0}
	text = ' '.join(readme.text('transect', TRANSECT, res, computed='2026-11-14T10:00:00+01:00').split())
	assert 'distance_m: distance along the line to the middle of the segment (m)' in text
	assert 'Line: 21.38 km, 3 points; segments of 1,000 m' in text and 'as the transects of geemap' in text
	# the points of the line whatever its form: its JSON text (the command line), a GeoJSON LineString, a Feature
	feature = {'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': LINE}}
	for line in (json.dumps(LINE), feature['geometry'], {'geojson': feature}):
		facts = dict(report.item_facts('transect', dict(TRANSECT, line=line), res))
		assert facts['Line'] == '21.38 km, 3 points; segments of 1,000 m', line
	assert dict(report.item_facts('transect', dict(TRANSECT, line='x'), res))['Line'] == \
		'21.38 km; segments of 1,000 m'
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
	assert rep['analyses'] == [{'id': 'gradients', 'name': 'Gradients'}]  # not a map, which it has not
	spec['results'][0]['args'] = {k: v for k, v in ZONE_ARGS.items() if k != 'zones'}  # the statistics of a region
	rep = publish.build(spec, 'gradients2', str(tmp_path), [], None, str(tmp_path / 'report2'))
	assert [a['id'] for a in rep['analyses']] == ['map', 'gradients']


VIEWER = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8')), specs = [];
function element() {
	return {append: function () {}, replaceChildren: function () {}, addEventListener: function () {},
		setAttribute: function () {}, clientWidth: 600};
}
global.Node = function () {};
global.document = {createElement: element, documentElement: {}};
global.getComputedStyle = function () {
	return {getPropertyValue: function () { return '#336699'; }, colorScheme: 'light'};
};
global.window = {matchMedia: function () { return {addEventListener: function () {}}; }};
global.vegaEmbed = function (box, spec) { specs.push(spec); return Promise.resolve({}); };
global.vega = {read: function (text) {
	var lines = text.trim().split('\n'), head = lines[0].split(',');
	return lines.slice(1).map(function (l) {
		var r = {}; l.split(',').forEach(function (v, i) { r[head[i]] = v; }); return r;
	});
}};
global.fetch = function () {
	return Promise.resolve({ok: true, text: function () { return Promise.resolve(input.csv); }});
};
['common.js', 'charts.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[1], f), 'utf8'), {filename: f});
});
var mo = vm.runInThisContext('MO');  // the const MO of common.js
input.stats.reduce(function (p, stats) {
	return p.then(function () { return mo.chart.render(element(), {chart: 'zones', csv: 'z.csv', stats: stats}, ''); });
}, Promise.resolve()).then(function () { process.stdout.write(JSON.stringify(specs)); });
"""


def test_the_viewer_says_the_band_of_the_zones():
	"""The chart of the zones of the viewer: the median and the band of the percentiles 25 and 75 (or else 5 and 95),
	each named in its legend, and their values in the tooltip."""
	if not shutil.which('node'):
		pytest.skip('no node')
	assets = os.path.join(os.path.dirname(__file__), '..', 'src', 'monitoreo', 'viewer', 'assets')
	stats = [list(services.REGION_STATS_ZONES), list(services.REGION_STATS), ['mean']]
	csv = 'region,zone,zone_label,p5,p25,p50,p75,p95,mean,n_pixels\nbbox,0,below 1500 m,0.1,0.2,0.3,0.4,0.5,0.3,10\n'
	run = subprocess.run(['node', '-e', VIEWER, assets], input=json.dumps({'csv': csv, 'stats': stats}),
	                     capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	specs = json.loads(run.stdout)
	for spec, band, name in zip(specs, (('p25', 'p75'), ('p5', 'p95')), ('Percentiles 25 to 75', 'Percentiles 5 to 95')):
		area, line = spec['layer']
		assert (area['encoding']['y']['field'], area['encoding']['y2']['field']) == band
		assert area['encoding']['color']['datum'] == name and line['encoding']['color']['datum'] == 'Median (percentile 50)'
		assert area['encoding']['color']['scale']['domain'] == ['Median (percentile 50)', name]
		assert [t['field'] for t in line['encoding']['tooltip']] == ['zone_label', 'p50', *band, 'n_pixels']
	assert [layer['mark']['type'] for layer in specs[2]['layer']] == ['line']  # no band


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
	cli.main(['stats', 'NDVI', '--sensor', 'Modis', '--region', json.dumps(REGION), '--start', '2023-06-01', '--end',
	          '2023-08-31', '--zones', json.dumps(ZONES)])
	assert calls[-1]['stats'] is None  # those of services.region_stats: with zones, also p25 and p75
	capsys.readouterr()
	with pytest.raises(SystemExit):
		cli.main(['stats', '--help'])
	assert f"with --zones, {','.join(services.REGION_STATS_ZONES)}" in ' '.join(capsys.readouterr().out.split())
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
	rnd = random.Random(2026)
	lengths = [rnd.uniform(100, 200000) for _ in range(500)]
	cases = [(1000.0, 300.0), (900.0, 300.0), (21379.1, 1000.0), (29688.37984445807, 29688.37984445807 / 100)] + \
		[(L, L / rnd.choice([10, 50, 100])) for L in lengths]
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
	assert out['cuts'] == [services.transect_cuts(a, b) for a, b in cases] and len(out['cuts'][3]) == 99
	assert [r['distance_m'] for r in out['rows']] == [150, 450, 650] and out['rows'][2]['value'] is None
	assert out['rows'][0] == {'distance_m': 150, 'lon': -3.6, 'lat': 37.2, 'value': 1.0, 'elevation': 800.0}
	assert [(r['zone_label'], r['p50'], r['n_pixels']) for r in out['zones']] == [('below 1500 m', None, 0),
	                                                                            ('1500 m or more', 2, 5)]


GRADIENT_STEPS = r"""
var out = {};
function after(label) {  // the select of a row of the panel, by its label
	return find(controls, 'Panel', function (w) {
		return w.children[0] && w.children[0].kind === 'Label' && w.children[0].opts.value === label;
	})[0].children[1];
}
function axes() {  // the titles of the left axis of the charts of the results
	return find(results, 'Chart').filter(function (c) { return c.opts.type === 'LineChart'; }).map(function (c) {
		var o = c.opts.options;
		return o.vAxis ? o.vAxis.title : o.vAxes[0].title;
	});
}
function gradients() {  // the statistics of each band, and the profile of a line drawn
	answer = {features: [{properties: {name: 'Map view', groups: [{zone: 1, p25: 1, p50: 2, p75: 3, mean: 2,
		count: 4}]}}]};
	button('Statistics of each band').opts.onClick();
	var bands = axes();
	answer = {length: 21379.1, centroid: [-3.5, 37.1], features: []};
	button('Draw a line and its profile').opts.onClick();
	drawn(object());
	return bands.concat(axes());
}
selectWith('earth_engine').opts.onChange('vegetation');
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
out.period = gradients();
selectWith('period').opts.onChange('annual');
after('Metric between years').opts.onChange('cv');
out.cv = gradients();
answer = {value_p5: 0, value_p95: 50};
button('Add to the map').opts.onClick();
out.legend = legendTitle();
process.stdout.write(JSON.stringify(out));
"""


def test_the_app_gives_the_unit_of_the_metric_between_years():
	"""The y axis of the charts of the section Gradients of the app (the statistics of each band and the profile) has
	the unit of the map, as the section Map: % for the coefficient of variation between the years (it said that of
	the variable)."""
	if not shutil.which('node'):
		pytest.skip('no node')
	from test_themes import PANEL, _build
	from monitoreo import catalog
	head = PANEL[:PANEL.index('var out = {};')]
	assert head.count('onDraw: nothing') == 1
	script = head.replace('onDraw: nothing', 'onDraw: function (f) { drawn = f; }').replace(
		'var map = new Widget', 'var drawn; var map = new Widget') + GRADIENT_STEPS
	gee = os.path.join(os.path.dirname(__file__), '..', 'gee')
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {}}
	run = subprocess.run(['node', '-e', script, gee], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	assert out['legend'].endswith('[%]')  # the map of the same options
	assert out['cv'] == ['[%]', '[%]'] and out['period'] == ['[unitless]', '[unitless]']
