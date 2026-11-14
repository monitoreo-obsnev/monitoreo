"""Area of each class over each feature of a region (services.area_by_class and monitoreo.classes), without Earth
Engine: the kinds of classes and their errors, the classes of the breaks and of the trend, the rows and their %, the
citations, the README, the report, the viewer of results, the command line, the MCP server and the Earth Engine app
(gee/core.js in node, the same classes and rows as Python). tests/test_ee.py computes them in Earth Engine."""

import json
import os
import shutil
import subprocess

import pytest

from monitoreo import classes, readme, references, report, services

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}


def test_one_kind_of_classes():
	assert classes.mode_of('CORINE') == 'landcover' and classes.mode_of(breaks=[1]) == 'breaks'
	assert classes.mode_of(trend=True) == 'trend'
	for kwargs in ({}, {'landcover_map': 'CORINE', 'breaks': [1]}, {'breaks': [1], 'trend': True}):
		with pytest.raises(ValueError, match='give one kind of classes'):
			classes.mode_of(**kwargs)


def test_the_breaks():
	assert classes.check_breaks('1500, 2000;2500') == [1500.0, 2000.0, 2500.0]
	for bad, text in (([], 'at least one'), (['a'], 'are numbers'), ([2, 1], 'from the lowest'), ([1, 1], 'each once')):
		with pytest.raises(ValueError, match=text):
			classes.check_breaks(bad)
	assert classes.break_classes([0.2, 0.4], '°C') == [(0, 'below 0.2 °C', None, 0.2), (1, '0.2 to 0.4 °C', 0.2, 0.4),
	                                                   (2, '0.4 °C or more', 0.4, None)]


def test_the_rows_and_their_percent():
	legend = [(c, label, {}) for c, label, _ in classes.TREND]
	rows = classes.rows({'park': {-1: 10.0, 0: 70.0, 1: 20.0}, 'empty': {}}, legend, {'map': 'x'})
	assert [(r['region'], r['class'], r['ha'], r['percent']) for r in rows[:3]] == \
		[('park', -1, 10.0, 10.0), ('park', 0, 70.0, 70.0), ('park', 1, 20.0, 20.0)]
	assert rows[0]['map'] == 'x' and all(r['percent'] is None for r in rows[3:])
	table = [{'region': 'p', 'landcover': k, 'ha': h, 'percent': p} for k, h, p in
	         (('trees', 10.0, 10.0), ('water', 5.0, 5.0), ('trees', 20.0, 20.0))]
	assert [(r['landcover'], r['ha'], r['percent']) for r in classes.by_landcover(table)] == \
		[('water', 5.0, 5.0), ('trees', 30.0, 30.0)]


def test_the_land_cover_maps_and_their_classes():
	m, year = classes.landcover_map('corine')
	assert m['key'] == 'CORINE' and year == 2018
	assert classes.landcover_classes(m)[0] == (111, 'Continuous urban fabric', 'built')
	assert set(k for _, _, k in classes.landcover_classes(m)) <= set(classes.LANDCOVER_COLOURS)
	with pytest.raises(ValueError, match='has no map of 2001'):
		classes.landcover_map('CORINE', 2001)


def test_the_errors_before_earth_engine():
	with pytest.raises(ValueError, match='without a variable'):
		services.area_by_class(REGION, 'NDVI', 'Modis', landcover='CORINE')
	with pytest.raises(ValueError, match='where is for the classes of a variable'):
		services.area_by_class(REGION, landcover='CORINE', where=[{'variable': 'ELEVATION', 'sensor': 'Copernicus',
		                                                           'min': 1500}])
	with pytest.raises(ValueError, match='give one kind of classes'):
		services.area_by_class(REGION, 'NDVI', 'Modis', '2020-01-01', '2020-12-31')
	with pytest.raises(ValueError, match='from the lowest'):
		services.area_by_class(REGION, 'ELEVATION', 'Copernicus', breaks=[3, 2])


LANDCOVER = {'region': REGION, 'landcover': 'CORINE', 'year': 2018}
TREND = {'region': REGION, 'variable': 'NDVI', 'sensor': 'Modis', 'start': '2005-01-01', 'end': '2024-12-31',
         'trend': True}


def test_what_an_area_by_class_cites():
	ids = [r['id'] for r in references.cite('area_by_class', LANDCOVER)['references']]
	assert {'clc2018', 'bise2023', 'wu2020', 'gorelick2017', 'monitoreo'} <= set(ids)
	assert any('Copernicus' in c for c in references.cite('area_by_class', LANDCOVER)['credits'])
	ids = [r['id'] for r in references.cite('area_by_class', TREND)['references']]
	assert {'mann1945', 'sen1968', 'tucker1979', 'wu2020'} <= set(ids)


def test_the_readme_and_the_report(tmp_path):
	csv = tmp_path / 'areas.csv'
	csv.write_text('region,map,year,class,label,landcover,ha,percent,scale_m\n'
	               'bbox,CORINE Land Cover,2018,311,311 Broad-leaved forest,trees,120.5,60.0,100.0\n', encoding='utf-8')
	result = {'rows': [{'region': 'bbox', 'class': 311, 'label': '311 Broad-leaved forest', 'landcover': 'trees',
	                    'ha': 120.5, 'percent': 60.0}], 'mode': 'landcover', 'scale': 100.0, 'unit': '',
	          'csv': str(csv), 'title': 'Area of each class of CORINE Land Cover 2018'}
	text = readme.text('area_by_class', LANDCOVER, result, computed='2026-11-14T10:00:00+01:00')
	assert 'class: class: its code in the land cover map' in text and 'percent: % of the area of the feature' in text
	assert 'Land cover map: CORINE Land Cover 2018, pixel of 100 m' in text and 'zonal statistics by group' in text
	assert 'mo.area_by_class(region=' in text
	assert report.item_title('area_by_class', LANDCOVER) == 'Area of each class of CORINE Land Cover 2018'
	assert report.item_title('area_by_class', TREND) == 'Area of each class of the trend of NDVI (MODIS), 2005-2024'
	labels, body = report.item_table('area_by_class', result, LANDCOVER)
	assert labels == ['Class', 'Land cover', 'Hectares', '% of the area with classes'] and body[0][0] == \
		'311 Broad-leaved forest'
	facts = dict(report.item_facts('area_by_class', dict(TREND, alpha=0.01), {'scale': 250.0}))
	assert facts['Step'] == 'annual' and facts['Temporal metric'] == 'mean' and 'p < 0.01' in facts['Classes']


def test_the_viewer_of_results_draws_the_areas(tmp_path):
	from monitoreo import publish
	csv = tmp_path / 'areas.csv'
	csv.write_text('region,class,label,ha,percent\nbbox,-1,significant decrease,10,10\n'
	               'bbox,0,no significant trend,80,80\nbbox,1,significant increase,10,10\n', encoding='utf-8')
	result = {'csv': str(csv), 'mode': 'trend', 'unit': '',
	          'classes': [{'class': c, 'label': label, 'colour': colour} for c, label, colour in classes.TREND]}
	spec = {'title': 'Areas', 'summary': 'Areas', 'region': {'name': 'Sierra Nevada'},
	        'results': [{'tool': 'area_by_class', 'args': TREND, 'result': result}]}
	folder = tmp_path / 'report'
	folder.mkdir()
	rep = publish.build(spec, 'areas', str(tmp_path), [], None, str(folder))
	r = rep['results'][0]
	assert r['chart'] == 'areas' and r['classes'][0] == {'class': -1, 'label': 'significant decrease',
	                                                       'colour': 'd7191c'}
	assert rep['analyses'] == [{'id': 'areas', 'name': 'Area by class'}] and publish.check_report(rep, str(folder)) == []


@pytest.fixture
def calls(monkeypatch):
	out = []

	def fake(region, variable=None, sensor=None, start=None, end=None, metric=None, temporal='period',
	         interannual='mean', season=None, quality=None, landcover=None, year=None, breaks=None, trend=False,
	         step='annual', part=None, alpha=0.05, scale=None, csv=None, chart=None, other_year=None, **source):
		out.append(dict(source, region=region, variable=variable, sensor=sensor, landcover=landcover, year=year,
		                breaks=breaks, trend=trend, metric=metric, csv=csv, chart=chart, other_year=other_year))
		if other_year:
			return {'rows': [], 'mode': 'transitions', 'scale': 100.0, 'unit': '', 'title': 'Changes', 'csv': csv,
			        'chart': None, 'classes': [], 'changed_ha': {'bbox': 1.0}, 'unchanged_ha': {'bbox': 2.0},
			        'by_landcover': [{'region': 'bbox', 'from_label': 'Trees', 'to_label': 'Shrubland', 'ha': 1.0,
			                          'percent': 33.3}]}
		return {'rows': [{'region': 'bbox', 'class': 0, 'label': 'below 1500 m', 'ha': 12.25, 'percent': 100.0}],
		        'mode': 'landcover' if landcover else 'breaks', 'scale': 30.0, 'unit': 'm', 'title': 'Areas',
		        'csv': csv, 'chart': None, 'classes': []}
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	monkeypatch.setattr(services, 'area_by_class', fake)
	return out


def test_the_command_line_computes_the_areas(calls, capsys):
	from monitoreo import cli
	cli.main(['areas', '--region', json.dumps(REGION), '--landcover', 'CORINE', '--year', '2018'])
	assert (calls[-1]['landcover'], calls[-1]['year'], calls[-1]['variable']) == ('CORINE', 2018, None)
	cli.main(['areas', 'ELEVATION', '--sensor', 'Copernicus', '--region', json.dumps(REGION), '--breaks',
	          '1500,2000'])
	assert calls[-1]['breaks'] == '1500,2000' and calls[-1]['variable'] == 'ELEVATION'
	out = capsys.readouterr().out
	assert 'below 1500 m' in out and '12.2' in out and '% of the area with classes' in out
	with pytest.raises(SystemExit):
		cli.main(['areas', 'NDVI', '--sensor', 'Modis', '--region', json.dumps(REGION), '--landcover', 'CORINE'])
	assert 'monitoreo areas' in cli.__doc__


def test_the_mcp_server_computes_the_areas(calls, monkeypatch, tmp_path):
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	out = mcp_server.area_by_class(REGION, landcover='CORINE', year=2018)
	answer = json.loads(out[0] if isinstance(out, list) else out)
	assert calls[-1]['landcover'] == 'CORINE' and answer['rows'][0]['ha'] == 12.25 and calls[-1]['csv'].endswith('.csv')
	with pytest.raises(Exception, match='fixed layer'):
		mcp_server.area_by_class(REGION, 'ELEVATION', 'Copernicus', trend=True, start='2001-01-01', end='2002-01-01')
	assert 'area_by_class' in mcp_server.INSTRUCTIONS


def test_the_assistant_knows_the_areas():
	from monitoreo import assistant
	assert 'area_by_class' in assistant.RESULTS and 'area_by_class' in assistant.PROMPT


APP = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
global.ee = new Proxy({}, {get: function () { return function () { return {}; }; }});  // nothing is computed
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[1], f), 'utf8'), {filename: f});
});
var mo = global.MonitorEO;
function attempt(f) {
	try { return f(); } catch (e) { return 'ERROR ' + e.message; }
}
process.stdout.write(JSON.stringify({
	breaks: input.breaks.map(function (b) { return attempt(function () { return mo.breakClasses(mo.checkBreaks(b[0]), b[1], 'en'); }); }),
	bad: input.bad.map(function (b) { return attempt(function () { return mo.checkBreaks(b); }); }),
	scales: input.areas.map(function (a) { return mo.areaScale(a[0], a[1]); }),
	rows: mo.areaRows(input.features, mo.TREND_CLASSES.map(function (c) { return [c[0], c[1], {}]; }), {map: 'x'}),
	trend: mo.TREND_CLASSES.map(function (c) { return [c[0], c[1], c[2]]; })
}));
"""


def test_the_app_has_the_same_classes():
	"""The area by class of the Earth Engine app (gee/core.js, in node): the same classes, scales and rows."""
	import math
	if not shutil.which('node'):
		pytest.skip('no node')
	breaks = [('1500, 2000, 2500', 'm'), ([0.2, 0.4], '')]
	bad = [[], ['a'], [2, 1]]
	area_cases = [(10, 1e6), (10, 1e10), (500, 5e9)]
	features = [{'properties': {'name': 'park', 'groups': [{'class': -1, 'sum': 10.0}, {'class': 0, 'sum': 70.0},
	                                                        {'class': 1, 'sum': 20.0}]}},
	            {'properties': {'name': 'empty', 'groups': []}}]
	gee = os.path.join(os.path.dirname(__file__), '..', 'gee')
	run = subprocess.run(['node', '-e', APP, gee], input=json.dumps({'breaks': breaks, 'bad': bad, 'areas': area_cases,
	                                                                  'features': features}),
	                     capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	assert out['breaks'] == [[list(c) for c in classes.break_classes(classes.check_breaks(b), u)] for b, u in breaks]
	assert [o.split(':')[0] for o in out['bad']] == ['ERROR give at least one break, e.g. [0.2, 0.4, 0.6]',
	                                                 'ERROR breaks are numbers, e.g. [0.2, 0.4, 0.6]; not ["a"]',
	                                                 'ERROR breaks go from the lowest to the highest, each once']

	class Regions:  # classes.scale_for without Earth Engine: the area of the biggest region
		def __init__(self, area):
			self.area = area

		def map(self, f):
			return self

		def aggregate_max(self, key):
			return self

		def getInfo(self):
			return self.area
	assert out['scales'] == [classes.scale_for(n, Regions(a)) for n, a in area_cases]
	assert out['rows'] == classes.rows({'park': {-1: 10.0, 0: 70.0, 1: 20.0}, 'empty': {}},
	                                   [(c, label, {}) for c, label, _ in classes.TREND], {'map': 'x'})
	assert out['trend'] == [list(c) for c in classes.TREND]
	assert not math.isnan(out['scales'][0])


# The changes of a land cover map between two years --------------------------------------------------------------------

def test_the_pairs_of_classes_and_their_rows():
	m, _ = classes.landcover_map('CORINE')
	ha = {'park': {311 * 1000 + 311: 60.0, 311 * 1000 + 324: 30.0, 512 * 1000 + 512: 10.0}}
	rows = classes.transition_rows(ha, m, 2006, 2018)
	assert [(r['from_class'], r['to_class'], r['ha'], r['percent']) for r in rows] == \
		[(311, 311, 60.0, 60.0), (311, 324, 30.0, 30.0), (512, 512, 10.0, 10.0)]
	assert rows[1]['from_label'] == '311 Broad-leaved forest' and rows[1]['to_landcover'] == 'trees'
	assert classes.changed(rows) == {'park': (30.0, 70.0)}
	broad = classes.broad_transitions(rows)
	assert [(r['from_landcover'], r['to_landcover'], r['ha']) for r in broad] == [('water', 'water', 10.0),
	                                                                             ('trees', 'trees', 90.0)]


def test_the_changes_before_earth_engine():
	with pytest.raises(ValueError, match='other_year is for the changes of a land cover map'):
		services.area_by_class(REGION, 'ELEVATION', 'Copernicus', breaks=[1000], other_year=2018)
	with pytest.raises(ValueError, match='two different years'):
		services.area_by_class(REGION, landcover='CORINE', year=2018, other_year=2018)
	with pytest.raises(ValueError, match='has no map of 2017'):
		services.area_by_class(REGION, landcover='CORINE', year=2012, other_year=2017)
	for variable, sensor in (('NDVI', 'Modis'), (None, 'Modis')):  # a land cover map has its own classes, as one year
		for other_year in (None, 2018):
			with pytest.raises(ValueError, match='own classes'):
				services.area_by_class(REGION, variable, sensor, landcover='CORINE', year=2006, other_year=other_year)


@pytest.fixture
def changes(monkeypatch):
	"""services.area_by_class of the changes of CORINE without Earth Engine: two features, Sierra Nevada and then
	Doñana (the order of the region, not that of the alphabet); the Sankey diagrams it draws."""
	class Regions:
		def geometry(self):
			return None
	monkeypatch.setattr(services.areas, 'region', lambda region: Regions())
	monkeypatch.setattr(services.classes, 'source', lambda m, year, geom: year)
	monkeypatch.setattr(services.classes, 'pairs', lambda first, other: (first, other))
	monkeypatch.setattr(services.classes, 'hectares', lambda img, regions, scale, crs: {
		'Sierra Nevada': {311311: 80.0, 311324: 15.0, 324311: 5.0}, 'Doñana': {512512: 30.0, 311311: 10.0}})
	monkeypatch.setattr(services.timeseries, 'region_crs', lambda regions: 'EPSG:3035')
	drawn = []

	def sankey(flows, colours=None, path=None, title=None, names=('', '')):
		drawn.append({'flows': flows, 'title': title, 'names': names})
		with open(path, 'wb') as f:
			f.write(b'png')
	monkeypatch.setattr(services.charts, 'sankey_png', sankey)
	return drawn


def test_the_sankey_diagram_is_of_the_first_feature(changes, tmp_path):
	"""With several features, the Sankey diagram is of the first one of the region (that of the first rows of the CSV,
	which the viewer of results shows first), named in its title and in the README."""
	res = services.area_by_class(REGION, landcover='CORINE', year=2006, other_year=2018, scale=100.0,
	                             csv=str(tmp_path / 'changes.csv'), chart=str(tmp_path / 'changes.png'))
	assert res['rows'][0]['region'] == 'Sierra Nevada' and list(res['changed_ha']) == ['Sierra Nevada', 'Doñana']
	drawn, = changes
	assert drawn['title'].endswith(': broad land covers (Sierra Nevada)') and drawn['names'] == ('2006', '2018')
	assert sum(h for _, _, h in drawn['flows']) == 100.0 and 'Water' not in {a for a, _, _ in drawn['flows']}  # Doñana
	with open(res['readme'], encoding='utf-8') as f:
		text = ' '.join(f.read().split())
	assert 'changes.png: Sankey diagram (PNG) of the changes of the broad land covers of Sierra Nevada, the first ' \
	       'feature of the region' in text


def test_the_readme_of_the_changes(changes, tmp_path):
	"""The README of the CSV of the changes says what its columns are: the hectares of each pair of classes, its % of
	the area with a class in both years, and both years."""
	res = services.area_by_class(REGION, landcover='CORINE', year=2006, other_year=2018, scale=100.0,
	                             csv=str(tmp_path / 'changes.csv'))
	with open(res['readme'], encoding='utf-8') as f:
		text = ' '.join(f.read().split())
	assert 'year: first year of the land cover map (that of from_class)' in text
	assert 'other_year: other year of the land cover map (that of to_class)' in text
	assert 'ha: hectares of the pixels of the feature with from_class in year and to_class in other_year (true area ' \
	       'of its pixels)' in text
	assert 'percent: % of the area of the feature with a class in both years (the pixels without data in either ' \
	       'year are not counted)' in text
	assert 'hectares of the class in the feature' not in text and 'Sankey diagram (PNG)' not in text  # no chart


def test_the_sankey_diagram(tmp_path):
	pytest.importorskip('matplotlib')
	from monitoreo import charts
	png = charts.sankey_png([('Trees', 'Trees', 90.0), ('Trees', 'Shrubland', 5.0), ('Water', 'Water', 10.0)],
	                        {'Water': '419bdf', 'Trees': '397d49', 'Shrubland': 'dfc35a'}, str(tmp_path / 's.png'),
	                        'Changes', ('2006', '2018'))
	assert png[:8] == b'\x89PNG\r\n\x1a\n' and (tmp_path / 's.png').exists()


def test_the_bands_of_the_sankey_diagram_fill_their_classes(monkeypatch):
	"""Each band of the Sankey diagram ends in the classes it joins, which it fills with the others, with the same
	height per hectare in both columns, also when the two years have a different number of broad land covers (one
	appears or disappears): no band wider than its class nor below the plot."""
	pytest.importorskip('matplotlib')
	from matplotlib.patches import PathPatch, Rectangle
	from monitoreo import charts
	figs = []
	monkeypatch.setattr(charts, '_png', lambda fig, path=None: figs.append(fig) or b'')
	flows = [('Trees', 'Trees', 50.0), ('Trees', 'Shrubland', 10.0), ('Water', 'Water', 20.0)] + \
		[('Trees', k, 5.0) for k in ('Built', 'Bare', 'Grassland', 'Cropland')]
	for case in (flows, [(b, a, h) for a, b, h in flows]):  # 2 classes to 7, and 7 to 2
		charts.sankey_png(case)
		ax = figs[-1].axes[0]
		nodes = {(r.get_x() < 0.5, r.get_y(), r.get_y() + r.get_height()): 0.0 for r in ax.patches
		         if isinstance(r, Rectangle)}
		for band in (p for p in ax.patches if isinstance(p, PathPatch)):
			v = band.get_path().vertices
			for left, (hi, lo) in ((True, (v[0][1], v[7][1])), (False, (v[3][1], v[4][1]))):
				assert lo >= -1e-9, case
				node = [n for n in nodes if n[0] == left and n[1] - 1e-9 <= lo and hi <= n[2] + 1e-9]
				assert len(node) == 1, (case, left, lo, hi)
				nodes[node[0]] += hi - lo
		assert all(abs(filled - (hi - lo)) < 1e-9 for (_, lo, hi), filled in nodes.items()), case
		left, right = (sum(hi - lo for (on_left, lo, hi) in nodes if on_left == side) for side in (True, False))
		assert abs(left - right) < 1e-9, case  # the same hectares, the same height


CHANGES = dict(LANDCOVER, year=2006, other_year=2018)


def test_the_changes_are_cited_described_and_published(tmp_path):
	from monitoreo import publish
	ids = [r['id'] for r in references.cite('area_by_class', CHANGES)['references']]
	assert {'clc2006', 'clc2018', 'bise2023'} <= set(ids)
	assert report.item_title('area_by_class', CHANGES) == 'Changes of the classes of CORINE Land Cover from 2006 to 2018'
	result = {'mode': 'transitions', 'rows': [{'region': 'park', 'from_label': '311 Broad-leaved forest',
	                                           'to_label': '324 Transitional woodland-shrub', 'ha': 30.0, 'percent': 30.0}],
	          'changed_ha': {'park': 30.0}, 'unchanged_ha': {'park': 70.0}, 'scale': 100.0}
	facts = dict(report.item_facts('area_by_class', CHANGES, result))
	assert facts['Changed'] == '30 ha; unchanged 70 ha' and facts['Compared with'].startswith('CORINE Land Cover 2018')
	assert 'Sankey' in facts['Method']
	labels, body = report.item_table('area_by_class', result, CHANGES)
	assert labels == ['From', 'To', 'Hectares', '% of the area with classes']
	csv = tmp_path / 'changes.csv'
	csv.write_text('region,from_label,to_label,ha,percent\npark,311 Broad-leaved forest,324 Transitional,30,30\n',
	               encoding='utf-8')
	png = tmp_path / 'sankey.png'
	pytest.importorskip('PIL.Image').new('RGB', (40, 20), 'white').save(png)
	spec = {'title': 'Changes', 'summary': 'Changes', 'region': {'name': 'Sierra Nevada'},
	        'results': [{'tool': 'area_by_class', 'args': CHANGES,
	                     'result': dict(result, csv=str(csv), chart=str(png), classes=[])}]}
	folder = tmp_path / 'report'
	folder.mkdir()
	rep = publish.build(spec, 'changes', str(tmp_path), [], None, str(folder))
	r = rep['results'][0]
	assert r['chart'] == 'transitions' and r['png'].endswith('.png') and publish.check_report(rep, str(folder)) == []


# The viewer of results (src/monitoreo/viewer/assets/charts.js) in Node: a document that draws nothing, each element
# with its attributes and children; the CSV of input.csv; the images of the chart of each region chosen
VIEWER = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
function el(tag, attrs) {
	var node = {tag: tag, attrs: attrs || {}, children: [], clientWidth: 800};
	node.append = function () {
		Array.prototype.slice.call(arguments).forEach(function (c) {
			(Array.isArray(c) ? c : [c]).forEach(function (x) { node.children.push(x); });
		});
	};
	node.replaceChildren = function () { node.children = []; node.append.apply(node, arguments); };
	node.append.apply(node, Array.prototype.slice.call(arguments, 2));
	return node;
}
global.MO = {el: el, text: function () { return Promise.resolve(input.csv); },
	safePath: function (p) { return Boolean(p); }, round: String, num: String, pValue: String,
	css: function () { return ''; }};
global.vega = {read: function (text) {
	var lines = text.trim().split('\n').map(function (l) { return l.split(','); });
	return lines.slice(1).map(function (l) {
		var r = {};
		lines[0].forEach(function (k, i) { r[k] = l[i]; });
		return r;
	});
}};
global.window = {matchMedia: function () { return {addEventListener: function () {}}; }};
vm.runInThisContext(fs.readFileSync(path.join(process.argv[process.argv.length - 1], 'charts.js'), 'utf8'));
function all(node, out) {
	out = out || [];
	if (node && typeof node === 'object') {
		out.push(node);
		node.children.forEach(function (c) { all(c, out); });
	}
	return out;
}
function images(container) {
	return all(container).filter(function (n) { return n.tag === 'img'; }).map(function (n) { return n.attrs.alt; });
}
(async function () {
	var result = {id: 'r1', chart: 'transitions', title: 'Changes', csv: 'files/changes.csv', png: 'files/sankey.png'};
	var out = {};
	var container = el('div');
	await MO.chart.render(container, result, '');
	var select = all(container).filter(function (n) { return n.tag === 'select'; })[0];
	out.regions = select.children.map(function (o) { return o.attrs.value; });
	out.first = images(container);
	select.attrs.onchange({target: {value: out.regions[1]}});
	out.second = images(container);
	select.attrs.onchange({target: {value: out.regions[0]}});
	out.back = images(container);
	input.csv = input.csv.split('\n').filter(function (l) { return l.indexOf('Doñana') < 0; }).join('\n');
	container = el('div');
	await MO.chart.render(container, result, '');
	out.one = images(container);
	process.stdout.write(JSON.stringify(out));
})();
"""


def test_the_viewer_shows_the_sankey_diagram_with_its_region():
	"""The viewer of results shows the Sankey diagram (of the first feature, as services.area_by_class draws it) with
	the table of that feature only, named in its text, and alone with one feature."""
	if not shutil.which('node'):
		pytest.skip('no node')
	csv = ('region,from_label,to_label,ha,percent\nSierra Nevada,311 Broad-leaved forest,324 Transitional,15,15\n'
	       'Doñana,512 Water bodies,512 Water bodies,30,100\n')
	assets = os.path.join(os.path.dirname(__file__), '..', 'src', 'monitoreo', 'viewer', 'assets')
	run = subprocess.run(['node', '-e', VIEWER, assets], input=json.dumps({'csv': csv}), capture_output=True,
	                     text=True, timeout=60)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	assert out['regions'] == ['Sierra Nevada', 'Doñana']  # as the CSV
	sankey = 'Changes: Sankey diagram of the changes of the broad land covers'
	assert out['first'] == out['back'] == [f'{sankey} (Sierra Nevada)'] and out['second'] == []
	assert out['one'] == [sankey]


# The group Area by class of the app (gee/ui.js) with «Its changes to», driven as a user would (the ui and ee of
# tests/test_themes.py, which compute nothing): the two years of each map, ticked before or after choosing the map
APP_CHANGES = r"""
var out = {};
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
function years() {  // the values of the selects of the first year and of the other
	return find(controls, 'Select', function (w) {
		return (w.opts.items || []).some(function (i) { return i.value === input.oldest; });
	}).map(function (w) { return w.opts.value; });
}
function compute() {
	answer = {features: []};
	button('Compute the areas').opts.onClick();
	return last().texts;
}
selectWith('DynamicWorld').opts.onChange('DynamicWorld');
input.oldest = 2016;
out.before = years();
check('Its changes to').opts.onChange(true);
out.dynamic = {years: years(), texts: compute()};
input.oldest = 1990;
selectWith('CORINE').opts.onChange('CORINE');  // ticked, then another map
out.corine = {years: years(), texts: compute()};
CATALOG.landcover.maps.forEach(function (m) { if (m.key === 'WorldCover') m.years = [2021]; });  // a map of one year
input.oldest = 2021;
selectWith('WorldCover').opts.onChange('WorldCover');
out.one = {years: years(), controls: texts(controls)};
process.stdout.write(JSON.stringify(out));
"""


def test_the_app_compares_two_different_years():
	"""«Its changes to» of the app gives two different years, the first one the year before the other (as the QGIS
	plugin), when it is ticked and when the map changes; with a map of a single year, it says so."""
	if not shutil.which('node'):
		pytest.skip('no node')
	from test_themes import GEE, PANEL, _build
	from monitoreo import catalog
	script = PANEL[:PANEL.index('var out = {};')] + APP_CHANGES
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {}}
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	assert out['before'] == [2025, 2025]  # the last whole year of Dynamic World, before ticking
	assert out['dynamic']['years'] == [2024, 2025] and out['corine']['years'] == [2012, 2018]
	for case in ('dynamic', 'corine'):
		assert not any('choose two different years' in t for t in out[case]['texts']), out[case]
	assert out['one']['years'] == [2021, 2021]
	assert 'ESA WorldCover has a map of a single year: there are no changes to compute.' in out['one']['controls']


def test_the_command_line_and_the_mcp_server_compare_two_years(calls, monkeypatch, tmp_path, capsys):
	from monitoreo import cli
	cli.main(['areas', '--region', json.dumps(REGION), '--landcover', 'CORINE', '--year', '2006', '--other-year',
	          '2018'])
	assert (calls[-1]['year'], calls[-1].get('other_year')) == (2006, 2018)
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	mcp_server.area_by_class(REGION, landcover='CORINE', year=2006, other_year=2018)
	assert calls[-1].get('other_year') == 2018 and '_2006_2018' in calls[-1]['csv']
