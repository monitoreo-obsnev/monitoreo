"""Area of each class over each feature of a region (services.area_by_class and monitoreo.classes), without Earth
Engine: the kinds of classes and their errors, the classes of the breaks and of the trend, the rows and their % (also
of the features with the same name), the citations, the README, the report, the viewer of results (also of the answers
of the MCP server), the command line, the MCP server and the Earth Engine app (gee/core.js in node, the same classes and
rows as Python; ui.js, its refusals). tests/test_ee.py computes them in Earth Engine."""

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
	rows = classes.rows([('park', {-1: 10.0, 0: 70.0, 1: 20.0}), ('empty', {})], legend, {'map': 'x'})
	assert [(r['region'], r['class'], r['ha'], r['percent']) for r in rows[:3]] == \
		[('park', -1, 10.0, 10.0), ('park', 0, 70.0, 70.0), ('park', 1, 20.0, 20.0)]
	assert rows[0]['map'] == 'x' and all(r['percent'] is None for r in rows[3:])
	legend = [(311, '311 Broad-leaved forest', {'landcover': 'trees'}), (511, '511 Water courses', {'landcover': 'water'}),
	          (312, '312 Coniferous forest', {'landcover': 'trees'})]
	broad = classes.by_landcover([('p', {311: 10.0, 511: 5.0, 312: 20.0, 999: 65.0}), ('empty', {})], legend)
	assert [(r['region'], r['landcover'], r['ha'], r['percent']) for r in broad] == \
		[('p', 'water', 5.0, 100 * 5 / 35), ('p', 'trees', 30.0, 100 * 30 / 35),
		 ('empty', 'water', 0.0, None), ('empty', 'trees', 0.0, None)]  # no class: no %, not 0 %


class FakeEE:
	"""An ee that computes nothing: each of its objects and methods gives it back, and getInfo the FEATURES of
	reduceRegions."""

	def __init__(self, features):
		self.features = features

	def __getattr__(self, name):
		return self

	def __call__(self, *args, **kwargs):
		return self

	def getInfo(self):
		return {'features': self.features}


# two areas of WDPA with the same name (e.g. the National Park and the Natural Park of a wdpa_name), and an empty one
SAME_NAME = [{'properties': {'name': 'Sierra Nevada', 'groups': [{'class': 311, 'sum': 1000.0},
                                                                 {'class': 321, 'sum': 0.0}]}},
             {'properties': {'name': 'Sierra Nevada', 'groups': [{'class': 321, 'sum': 5.0}]}},
             {'properties': {'name': 'empty', 'groups': []}}]


def test_the_features_with_the_same_name_keep_their_own_rows(monkeypatch, tmp_path):
	"""Each feature of the region has its rows, its hectares of each broad land cover and its panel of the chart, also
	when another one has its name (as region_stats): none overwrites the other."""
	monkeypatch.setattr(classes, 'ee', FakeEE(SAME_NAME))
	ha = classes.hectares('classes', 'regions', 100, 'EPSG:3035')
	assert ha == [('Sierra Nevada', {311: 1000.0, 321: 0.0}), ('Sierra Nevada', {321: 5.0}), ('empty', {})]
	m, year = classes.landcover_map('CORINE', 2018)
	legend = [(code, f'{code} {name}', {'landcover': k}) for code, name, k in classes.landcover_classes(m)]
	rows = classes.rows(ha, legend)
	assert len(rows) == 3 * len(legend)
	assert [(r['region'], r['ha'], r['percent']) for r in rows if r['class'] == 311] == \
		[('Sierra Nevada', 1000.0, 100.0), ('Sierra Nevada', 0.0, 0.0), ('empty', 0.0, None)]
	assert [(r['region'], r['landcover'], r['ha'], r['percent']) for r in classes.by_landcover(ha, legend)
	        if r['ha']] == [('Sierra Nevada', 'trees', 1000.0, 100.0), ('Sierra Nevada', 'grassland', 5.0, 100.0)]
	# services.area_by_class, without Earth Engine: its rows, by_landcover and CSV keep both areas
	monkeypatch.setattr(services.areas, 'region', lambda region: FakeEE(SAME_NAME))
	monkeypatch.setattr(classes, 'scale_for', lambda native, regions: 100.0)
	monkeypatch.setattr(classes, 'source', lambda m, year, region=None: 'classes')
	monkeypatch.setattr(services.timeseries, 'region_crs', lambda regions: 'EPSG:3035')
	out = services.area_by_class({'wdpa_name': 'Sierra Nevada'}, landcover='CORINE', year=2018,
	                             csv=str(tmp_path / 'areas.csv'))
	assert out['rows'] == [dict(r, map='CORINE Land Cover', year=2018) for r in rows]
	assert out['by_landcover'] == classes.by_landcover(ha, legend)
	csv = (tmp_path / 'areas.csv').read_text(encoding='utf-8').splitlines()
	assert len(csv) == 1 + 3 * len(legend) and sum(1 for r in csv if r.startswith('Sierra Nevada,')) == 2 * len(legend)
	# the chart: a panel for each feature
	pytest.importorskip('matplotlib')
	from matplotlib.axes import Axes

	from monitoreo import charts
	titles = []
	monkeypatch.setattr(Axes, 'set_title', lambda self, label, *args, **kwargs: titles.append(label))
	charts.areas_png(rows, {}, str(tmp_path / 'areas.png'))
	assert titles == ['Sierra Nevada', 'Sierra Nevada', 'empty']


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
	assert 'Part of the year' not in facts and 'Part of the year' not in dict(
		report.item_facts('area_by_class', dict(TREND, part=7), {}))  # annual (the default): the whole year


def test_the_readme_says_the_breaks_given_as_a_text(tmp_path):
	"""The command line and QGIS give the breaks as a text: the README says its numbers, not its characters."""
	args = {'region': REGION, 'variable': 'ELEVATION', 'sensor': 'Copernicus', 'breaks': '1500,2000'}
	facts = dict(report.item_facts('area_by_class', args, {'unit': 'm'}))
	assert facts['Classes'] == 'cut at 1500, 2000 m (a value equal to a break goes to the class above it)'
	csv = tmp_path / 'bands.csv'
	csv.write_text('region,class,label,value_from,value_to,ha,percent\nbbox,0,below 1500 m,,1500,10,100\n',
	               encoding='utf-8')
	text = readme.text('area_by_class', dict(args, breaks='0.2; 0.4'), {'csv': str(csv), 'mode': 'breaks', 'unit': '',
	                                                                    'scale': 30.0, 'title': 'Areas'})
	assert 'cut at 0.2, 0.4 (a value' in text


def test_the_part_of_the_year_of_a_trend_is_in_the_title_and_the_facts():
	"""The classes of the trend of a month or of 16 days say which, in the title and the facts, as trend_map."""
	july, period = dict(TREND, step='monthly', part=7), dict(TREND, step='16-day', part=12)
	assert report.item_title('area_by_class', july) == \
		'Area of each class of the trend of July of NDVI (MODIS), 2005-2024'
	assert report.item_title('area_by_class', period) == \
		'Area of each class of the trend of 16-day period 12 of NDVI (MODIS), 2005-2024'
	facts = dict(report.item_facts('area_by_class', july, {'scale': 250.0}))
	assert facts['Part of the year'] == 'July' and facts['Temporal metric'] == 'mean' and 'p < 0.05' in facts['Classes']
	assert dict(report.item_facts('area_by_class', period, {}))['Part of the year'] == '16-day period 12'


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


VIEWER = r"""
var fs = require('fs'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8')), specs = [];
function node(tag, attrs, children) {  // the elements of the page, without a browser
	return {tag: tag, attrs: attrs || {}, children: children, clientWidth: 800,
		append: function () { this.children.push.apply(this.children, arguments); },
		replaceChildren: function () { this.children = []; }};
}
global.MO = {el: function (tag, attrs) { return node(tag, attrs, [].slice.call(arguments, 2).flat(Infinity)); },
	MONTHS: [], css: function () { return ''; }, text: async function () { return input.csv; }};
global.window = {matchMedia: function () { return {addEventListener: function () {}}; }};
global.document = {documentElement: {}};
global.getComputedStyle = function () { return {colorScheme: 'light'}; };
global.vega = {read: function (text) {  // a CSV without quotes
	var lines = text.trim().split(/\r?\n/), cols = lines[0].split(',');
	return lines.slice(1).map(function (l) {
		var v = l.split(','), r = {};
		cols.forEach(function (c, i) { r[c] = v[i]; });
		return r;
	});
}};
global.vegaEmbed = async function (box, spec) {
	specs.push(spec.data.values.map(function (r) { return [r.region, r.label, r.ha]; }));
};
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'), {filename: 'charts.js'});
function find(n, tag) {
	if (!n || typeof n !== 'object') return null;
	if (n.tag === tag) return n;
	for (var i = 0; i < (n.children || []).length; i++) {
		var f = find(n.children[i], tag);
		if (f) return f;
	}
	return null;
}
(async function () {
	var container = node('div', {}, []);
	await MO.chart.render(container, {chart: 'areas', csv: 'areas.csv', id: 'a', classes: input.classes}, '');
	var select = find(container, 'select'), options = select ? select.children.map(function (o) { return o.attrs.value; }) : [];
	if (select) select.attrs.onchange({target: {value: options[1]}});
	await new Promise(function (resolve) { setTimeout(resolve, 0); });
	process.stdout.write(JSON.stringify({options: options, specs: specs}));
})();
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_viewer_draws_each_feature_also_those_with_the_same_name():
	"""The chart of an area by class in the viewer of results (charts.js, in node): one feature at a time, chosen in
	Region, also those with the same name (numbered), as the panels of the chart of Python; not their bars together."""
	import csv
	import io
	legend = [(311, '311 Broad-leaved forest', {}), (321, '321 Natural grasslands', {})]
	rows = classes.rows([('Sierra Nevada', {311: 1000.0, 321: 20.0}), ('Sierra Nevada', {321: 5.0}), ('empty', {})],
	                    legend)
	text = io.StringIO()
	writer = csv.DictWriter(text, ['region', 'class', 'label', 'ha', 'percent'], lineterminator='\n')
	writer.writeheader()
	writer.writerows({k: '' if r[k] is None else r[k] for k in writer.fieldnames} for r in rows)
	charts_js = os.path.join(os.path.dirname(classes.__file__), 'viewer', 'assets', 'charts.js')
	run = subprocess.run(['node', '-e', VIEWER, charts_js],
	                     input=json.dumps({'csv': text.getvalue(), 'classes': [{'label': label, 'colour': '6baed6'}
	                                                                          for _, label, _ in legend]}),
	                     capture_output=True, text=True, timeout=60)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	assert out['options'] == ['Sierra Nevada', 'Sierra Nevada (2)', 'empty'], out
	assert out['specs'] == [[['Sierra Nevada', '311 Broad-leaved forest', 1000], ['Sierra Nevada', '321 Natural grasslands', 20]],
	                        [['Sierra Nevada', '321 Natural grasslands', 5]]], out


@pytest.fixture
def calls(monkeypatch):
	out = []

	def fake(region, variable=None, sensor=None, start=None, end=None, metric=None, temporal='period',
	         interannual='mean', season=None, quality=None, landcover=None, year=None, breaks=None, trend=False,
	         step='annual', part=None, alpha=0.05, scale=None, csv=None, chart=None, **source):
		out.append(dict(source, region=region, variable=variable, sensor=sensor, landcover=landcover, year=year,
		                breaks=breaks, trend=trend, metric=metric, csv=csv, chart=chart))
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


AREA_CALLS = {'landcover': ({'landcover': 'CORINE', 'year': 2018}, {311: 70.0, 512: 30.0}),
              'breaks': ({'variable': 'ELEVATION', 'sensor': 'Copernicus', 'breaks': [1500, 2000]}, {0: 40.0, 2: 60.0}),
              'trend': ({'variable': 'NDVI', 'sensor': 'Modis', 'start': '2005-01-01', 'end': '2024-12-31',
                         'trend': True}, {-1: 10.0, 0: 90.0})}


@pytest.mark.parametrize('kind', list(AREA_CALLS))
def test_the_report_of_an_area_by_class_of_the_mcp_server_has_its_classes(kind, monkeypatch, tmp_path):
	"""The answer of the MCP server, and so its log that publish_report reads, has no classes (it stays small): the
	report takes them from the CSV, with the colours of services.area_by_class (its chart in the viewer)."""
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	from monitoreo import publish
	call, groups = AREA_CALLS[kind]
	regions = FakeEE([{'properties': {'name': 'bbox', 'groups': [{'class': c, 'sum': h} for c, h in groups.items()]}}])
	monkeypatch.setattr(classes, 'ee', regions)  # services.area_by_class without Earth Engine
	monkeypatch.setattr(services.areas, 'region', lambda region: regions)
	monkeypatch.setattr(classes, 'scale_for', lambda native, regions: 100.0)
	monkeypatch.setattr(classes, 'source', lambda m, year, region=None: 'classes')
	monkeypatch.setattr(services.timeseries, 'region_crs', lambda regions: 'EPSG:3035')
	monkeypatch.setattr(services, '_build', lambda region, variable, sensor, start, end, metric, *args:
	                    (services.make_spec(variable, sensor, start, end, metric), regions, 'value', 30))
	monkeypatch.setattr(services, '_trend', lambda region, variable, sensor, start, end, step, part, metric, *args, **kw:
	                    (services.make_spec(variable, sensor, start, end, metric), regions, 'trend', 0, 250.0, 'NDVI'))
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	expected = services.area_by_class(REGION, **call)['classes']
	assert all(c['colour'] for c in expected)
	out = mcp_server.area_by_class(REGION, **call)
	answer = json.loads(out[0] if isinstance(out, list) else out)
	assert 'classes' not in answer and answer['csv']
	spec = {'title': 'Areas', 'summary': 'Areas', 'results': [os.path.basename(answer['csv'])]}
	folder = tmp_path / 'report'
	folder.mkdir()
	rep = publish.build(spec, 'areas', str(tmp_path), [], publish.calls_log(str(tmp_path)), str(folder))
	r = rep['results'][0]
	assert r['tool'] == 'area_by_class' and r['chart'] == 'areas' and r['classes'] == expected


# The Area by class of the panel of the app in Node (the ui and ee of tests/test_themes.py, which compute nothing): a
# land cover map refuses the land cover mask and «Only the pixels where», as services.area_by_class
STEPS = r"""
var out = {};
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
var mask = 'Leave some land covers out of the results', where = 'a variable is between two values';
check(mask).opts.onChange(true);
button('Compute the areas').opts.onClick();
out.mask = last();
check(mask).opts.onChange(false);
check(where).opts.onChange(true);
button('Compute the areas').opts.onClick();
out.where = last();
check(where).opts.onChange(false);
answer = {features: [{properties: {name: 'Map view', groups: [{'class': 10, sum: 70}, {'class': 30, sum: 30}]}}]};
button('Compute the areas').opts.onClick();
out.none = last();
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_app_refuses_the_mask_and_where_for_a_land_cover_map():
	"""Area by class of a land cover map in the app: with the land cover mask or «Only the pixels where» on, the
	message of the refusal and nothing computed; with both off, its chart and table."""
	from test_themes import GEE, PANEL, _build

	from monitoreo import catalog
	script = PANEL[:PANEL.index('var out = {};')] + STEPS
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {}}
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	refusal = ('The land cover mask and «Only the pixels where» are for the classes of a variable (breaks, trend), not '
	           'for those of a land cover map: uncheck them.')
	for case in ('mask', 'where'):
		assert out[case]['texts'][-1] == refusal and not out[case]['charts'], out[case]
	assert [c['type'] for c in out['none']['charts']] == ['BarChart', 'Table'], out['none']


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
	            {'properties': {'name': 'park', 'groups': [{'class': 1, 'sum': 5.0}]}},  # another one of that name
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
	assert out['rows'] == classes.rows([('park', {-1: 10.0, 0: 70.0, 1: 20.0}), ('park', {1: 5.0}), ('empty', {})],
	                                   [(c, label, {}) for c, label, _ in classes.TREND], {'map': 'x'})
	assert len(out['rows']) == 9  # each feature its rows, also those of the same name
	assert out['trend'] == [list(c) for c in classes.TREND]
	assert not math.isnan(out['scales'][0])
