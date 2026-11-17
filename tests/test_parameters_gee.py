"""The parameters of an analysis as JSON (monitoreo.parameters, issue #85) in the Earth Engine app, without Earth
Engine: gee/core.js ports parameters.read, parameters.text and catalog.find (in Node, with an ee that computes
nothing); and the panel (gee/ui.js in Node, with the ui and ee of tests/test_themes.py) writes the parameters of each
analysis with the names of the functions of monitoreo.services and of their arguments, as the services take them
(parameters.check applies every one), and Apply sets the panel from the parameters of any tool, without computing,
listing what it cannot apply with the reasons of parameters.check."""

import inspect
import json
import os
import shutil
import subprocess

import pytest

from monitoreo import areas, catalog, parameters, readme, sensors, services

GEE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gee')
pytestmark = pytest.mark.skipif(not shutil.which('node'), reason='no Node')


def _node(script, data):
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout.strip().splitlines()[-1])


# catalog.js and core.js in Node, with an ee that computes nothing ------------------------------------------------

CORE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
function nothing() { return new Proxy(function () {}, {get: function () { return nothing(); }, apply: nothing}); }
global.ee = nothing();
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[process.argv.length - 1], f), 'utf8'), {filename: f});
});
var mo = MonitorEO;
function attempt(f) {
	try {
		return {value: f()};
	} catch (e) {
		return {error: e.message};
	}
}
var out = {analyses: mo.PARAMETER_ANALYSES, outputs: mo.PARAMETER_OUTPUTS, meta: mo.PARAMETER_META};
out.read = input.read.map(function (s) { return attempt(function () { return mo.readParameters(s); }); });
out.find = input.find.map(function (a) {
	return attempt(function () { return mo.findEntry(a[0], a[1], a[2], a[3]).ref; });
});
out.text = mo.parametersText(input.text);
process.stdout.write(JSON.stringify(out));
"""

READ = [
	'{"monitoreo": "0.3.52", "analysis": "time_series", "parameters": {"region": {"wdpa_id": 555588816}, '
	'"variable": "NDVI", "sensor": "Landsat", "start": "2023-01-01"}}',
	' {"analysis": "map_layer", "variable": "NDVI", "sensor": "Sentinel-2", "start": "2021-01-01"} ',  # a flat object
	'{"analysis": "map_layer", "parameters": [1, 2], "variable": "NDVI"}',  # parameters that are not an object
	{'analysis': 'trend_table', 'parameters': {'variable': 'LST', 'sensor': 'Modis'}},
]
BAD_READ = ['{"analysis": "map_layer",', [1, 2], 'map_layer.parameters.json']
FIND = [['NDVI', 'Sentinel-2', None, None], ['ndvi', 'MODIS', None, None], ['NDVI', 'Modis', 'MODIS/061/MYD13Q1', None],
        ['LST', 'Modis', 'MODIS/061/MOD11A1', 30], [None, None, None, 105], ['Elevation', 'copernicus', None, None],
        ['TWI', 'MERIT hydro', None, None]]
BAD_FIND = [['NDVI', 'Sentinel-3', None, None], ['XYZ', None, None, None], ['NDVI', 'Modis', 'X/Y', None],
            [None, None, None, 9999]]
TEXT = [{'name': 'sensor', 'value': 'MODIS', 'reason': 'not in the catalog'},
        {'name': 'where', 'value': [{'variable': 'ELEVATION', 'min': 1500, 'classes': [1, 2]}], 'reason': 'one only'},
        {'name': 'zones', 'value': None, 'reason': 'by zones'}, {'name': 'doy', 'value': True, 'reason': 'x'}]


def test_core_ports_the_parameters_of_the_package():
	"""core.js has the analyses and the outputs of the package, reads the parameters as parameters.read (the same
	errors, a flat object too), finds the variables as catalog.find (the same errors) and writes those not applied as
	parameters.text."""
	out = _node(CORE, {'read': READ + BAD_READ, 'find': FIND + BAD_FIND, 'text': TEXT})
	assert out['analyses'] == list(parameters.ANALYSES)
	assert sorted(out['outputs']) == sorted(readme.NOT_ARGS)
	assert out['meta'] == list(parameters.META)
	for source, got in zip(READ, out['read']):
		assert got == {'value': parameters.read(source)}, source
	errors = [g['error'] for g in out['read'][len(READ):]]
	with pytest.raises(ValueError, match='the parameters are not valid JSON'):
		parameters.read(BAD_READ[0])
	assert errors[0].startswith('the parameters are not valid JSON: ')
	with pytest.raises(ValueError) as error:
		parameters.read(BAD_READ[1])
	assert errors[1] == str(error.value)
	assert errors[2].startswith('map_layer.parameters.json: ')  # the app reads no files: their text is pasted
	for args, got in zip(FIND, out['find']):
		assert got == {'value': catalog.find(*args[:3], ref=args[3])['ref']}, args
	for args, got in zip(BAD_FIND, out['find'][len(FIND):]):
		with pytest.raises(KeyError) as error:
			catalog.find(*args[:3], ref=args[3])
		assert got == {'error': str(error.value).strip('"\'')}, args  # as parameters.check gives the reason
	assert out['text'] == parameters.text(TEXT)


# The panel of the app ---------------------------------------------------------------------------------------------

REGION = {'info': {'area': 8e7, 'centroid': [-3.56, 36.9], 'total': 8e7, 'boundsArea': 9e7}, 'n': 1}
# what every evaluate of the ee of the tests answers: the region (its area, its names), the geometries of a protected
# area and the bands of the data of Earth Engine read by their ID
ANSWER = dict(REGION, names=['Sierra Nevada'], bands=['aet', 'def', 'pr'],
              scales={'aet': 4638.3, 'def': 4638.3, 'pr': 4638.3}, dated=True,
              features=[{'type': 'Feature', 'properties': {'name': 'Sierra Nevada'}, 'geometry': {
	              'type': 'Polygon', 'coordinates': [[[-3.4, 37.0], [-3.2, 37.0], [-3.2, 37.1], [-3.4, 37.0]]]}}])
ASSETS = {'IDAHO_EPSCOR/TERRACLIMATE': {'type': 'IMAGE_COLLECTION', 'properties': {'title': 'TerraClimate'}},
          'WORLDCLIM/V1/BIO': {'type': 'IMAGE', 'properties': {}}}
HINT = 'Paste here the parameters of an analysis (JSON)'

# the steps of the tests in the panel: helpers to apply and show parameters, and what the box and the report say; the
# handlers of a click on the map and of a geometry drawn are kept (clicked, drawn), to call them
HELPERS = r"""
var out = {};
answer = input.answer;
function box() {
	return find(controls, 'Textbox', function (w) { return w.opts.placeholder === input.hint; })[0];
}
// what Show or Apply said: the labels after the buttons, to the header of About
function report() {
	var labels = texts(controls), at = labels.indexOf(input.hint);
	var shown = all(controls), i = shown.indexOf(box());
	return shown.slice(i + 1).filter(function (w) { return w.kind === 'Label' && w.opts.value; })
		.map(function (w) { return w.opts.value; })
		.filter(function (v, k, a) { return a.indexOf('About MonitorEO') < 0 || k < a.indexOf('About MonitorEO'); });
}
function show(analysis) {
	if (analysis) find(controls, 'Select', function (w) {
		return (w.opts.items || []).some(function (i) { return i.value === 'map_layer'; });
	})[0].opts.onChange(analysis);
	button('Show the parameters').opts.onClick();
	var text = box().opts.value;
	return {json: text ? JSON.parse(text) : null, report: report()};
}
function apply(p) {
	box().opts.value = typeof p === 'string' ? p : JSON.stringify(p);
	var before = layers.length;
	button('Apply parameters').opts.onClick();
	return {report: report(), layers: layers.slice(before), results: texts(results).slice(1)};
}
"""


def _panel():
	from test_themes import PANEL
	head = PANEL[:PANEL.index('var out = {};')]
	# the handlers of the map: a click (ecoregion, island, biome) and a geometry drawn (a polygon, a line)
	click = 'map.setOptions = map.setCenter = map.centerObject = map.onClick = function () {};'
	draw = 'onDraw: nothing'
	assert click in head and draw in head
	head = head.replace(click, 'map.setOptions = map.setCenter = map.centerObject = function () {};\n'
	                           'map.onClick = function (f) { clicked = f; };')
	return 'var clicked = null, drawn = null;\n' + head.replace(draw, 'onDraw: function (f) { drawn = f; }')


def _app(steps, **extra):
	"""What STEPS put in out, run on the panel with the data of the tests and EXTRA (in input)."""
	from test_themes import _build
	data = dict({'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': ASSETS,
	             'answer': ANSWER, 'hint': HINT}, **extra)
	return _node(_panel() + HELPERS + steps + '\nconsole.log(JSON.stringify(out));', data)


def _not_applied(report):
	"""The parameters not applied of a report of the app: {name: reason} (the last reason of each name)."""
	out = {}
	for line in report:
		if line.startswith('· '):
			name, rest = line[2:].split(' (', 1)
			out[name] = rest.split('): ', 1)[1]
	return out


QUALITY = {'clouds': True, 'water': True, 'snow': False, 'aerosols': True}
S2_QUALITY = dict(QUALITY, cloud_score=None)
# the parameters of every analysis of the app, as the app writes them: Apply sets the panel from them and Show writes
# them again, the same
CASES = [
	('map_layer', {'region': {'wdpa_id': 555588816}, 'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2021-01-01',
	               'end': '2023-12-31', 'metric': 'p90', 'temporal': 'annual', 'interannual': 'max',
	               'season': ['06-01', '08-31'], 'quality': S2_QUALITY,
	               'where': [{'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 1500, 'max': 2500},
	                         {'landcover': 'CORINE', 'year': 2018, 'exclude': ['built', 'cropland']}]}),
	('rgb_map', {'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'variable': 'NDVI', 'sensor': 'Landsat',
	             'start': '2020-06-01', 'end': '2020-09-30', 'metric': 'median', 'temporal': 'period',
	             'quality': QUALITY}),
	('compare_map', {'region': {'admin2': 61046}, 'variable': 'NDVI', 'sensor': 'Modis',
	                 'collection': 'MODIS/061/MYD13Q1', 'start': '2018-01-01', 'end': '2018-12-31',
	                 'other_start': '2022-01-01', 'other_end': '2022-12-31', 'metric': 'mean', 'temporal': 'period',
	                 'quality': QUALITY}),
	('area_by_class', {'region': {'ecoregion_at': [-3.3, 37.1]}, 'landcover': 'WorldCover', 'year': 2021,
	                   'other_year': 2020}),
	('area_by_class', {'region': {'island_at': [2.9, 39.6]}, 'variable': 'ELEVATION', 'sensor': 'Copernicus',
	                   'breaks': [1500, 2000],
	                   'where': [{'variable': 'NDVI', 'sensor': 'Sentinel-2', 'min': 0.3,
	                              'period': ['2021-01-01', '2021-12-31']}]}),
	('area_by_class', {'region': {'admin1': 1653}, 'variable': 'NDVI', 'sensor': 'Modis', 'start': '2010-01-01',
	                   'end': '2020-12-31', 'trend': True, 'step': 'monthly', 'part': 7, 'metric': 'max',
	                   'quality': QUALITY}),
	('area_by_class', {'region': {'bbox': [-6.0, 36.0, -2.0, 38.0]}, 'variable': 'BIOME', 'sensor': 'RESOLVE',
	                   'where': [{'variable': 'ECOREGION', 'sensor': 'RESOLVE', 'exclude': [785]}]}),
	('region_stats', {'region': {'biome_at': [-3.3, 37.1], 'within': {'bbox': [-3.62, 36.86, -3.5, 36.93]}},
	                  'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2021-01-01', 'end': '2021-12-31',
	                  'zones': {'variable': 'ELEVATION', 'sensor': 'Copernicus', 'breaks': [1500, 2000, 2500]},
	                  'metric': 'median', 'temporal': 'monthly', 'interannual': 'cv', 'quality': S2_QUALITY}),
	('region_stats', {'region': {'wdpa_id': [555588816, 389011]}, 'variable': 'SLOPE', 'sensor': 'Copernicus',
	                  'zones': {'variable': 'BIOME', 'sensor': 'RESOLVE'}}),
	('timelapse', {'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'variable': 'SCF', 'sensor': 'Landsat',
	               'start': '2015-01-01', 'end': '2020-12-31', 'step': 'monthly', 'metric': 'mean'}),
	('time_series', {'region': {'geojson': {'type': 'Feature', 'properties': {'name': 'Guájares'}, 'geometry': {
		'type': 'Polygon', 'coordinates': [[[-3.62, 36.86], [-3.5, 36.86], [-3.5, 36.93], [-3.62, 36.86]]]}}},
		'variable': 'NDSI', 'sensor': 'Modis', 'start': '2015-01-01', 'end': '2024-12-31', 'step': 'monthly',
		'metric': 'max', 'stat': 'p90', 'doy': True, 'other_variable': 'NDVI', 'other_sensor': 'Modis',
		'interannual': 'median', 'quality': dict(QUALITY, snow='auto'),  # snow: off for the NDSI, on for the NDVI
		'where': [{'landcover': 'DynamicWorld', 'year': 2021, 'exclude': ['built']}]}),
	('time_series', {'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'collection': 'IDAHO_EPSCOR/TERRACLIMATE',
	                 'band': ['aet', 'def'], 'band_reducer': 'sum', 'band_scale': 0.1, 'unit': 'mm',
	                 'start': '2000-01-01', 'end': '2020-12-31', 'step': 'annual', 'metric': 'mean', 'stat': 'mean'}),
	('compare_series', {'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'variable': 'NDVI', 'sensor': 'Landsat',
	                    'start': '2000-01-01', 'end': '2004-12-31', 'other_start': '2020-01-01',
	                    'other_end': '2024-12-31', 'step': '16-day', 'metric': 'median', 'stat': 'median',
	                    'quality': QUALITY}),
	('trend_table', {'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'variable': 'LST', 'sensor': 'Modis',
	                 'collection': 'MODIS/061/MOD11A1', 'ref': 30, 'start': '2010-01-01', 'end': '2020-12-31',
	                 'step': 'monthly', 'metric': 'mean', 'stat': 'mean', 'quality': QUALITY}),
	('trend_map', {'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
	               'start': '2017-01-01', 'end': '2024-12-31', 'step': '16-day', 'part': 5, 'output': 'p_value',
	               'metric': 'mean', 'alpha': 0.05, 'season': ['03-01', '09-30'], 'quality': S2_QUALITY}),
	('burn_severity', {'region': {'geojson': {'type': 'FeatureCollection', 'features': [
		{'type': 'Feature', 'properties': {'name': 'west'}, 'geometry': {'type': 'Polygon', 'coordinates': [
			[[-5.23, 36.47], [-5.1, 36.47], [-5.1, 36.57], [-5.23, 36.47]]]}}]}},
		'sensor': 'Modis', 'collection': 'MODIS/061/MYD09GA', 'start': '2021-06-01', 'end': '2021-08-31',
		'other_start': '2022-09-01', 'other_end': '2022-10-31', 'index': 'RdNBR', 'quality': QUALITY,
		'where': [{'variable': 'SLOPE', 'sensor': 'Copernicus', 'max': 30}]}),
	('map_layer', {'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'image': 'WORLDCLIM/V1/BIO', 'band': 'bio01',
	               'band_scale': 0.1, 'unit': 'degC'}),
]


def test_the_app_writes_the_parameters_of_the_services():
	"""Apply sets the panel from the parameters of each analysis of the app (every one applied, without computing:
	no layer but that of the region, no result), and Show writes them again, the same: the analysis is a function of
	monitoreo.services, the parameters are its arguments, as parameters.check applies them all, and the region is one
	that areas.region takes."""
	steps = 'out.cases = input.cases.map(function (c) {\n' \
	        '	var applied = apply({monitoreo: "0.3.52", analysis: c[0], parameters: c[1]});\n' \
	        '	return {applied: applied, shown: show()};\n' \
	        '});'
	from test_themes import _build
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': ASSETS,
	        'answer': dict(ANSWER, bands=['aet', 'def', 'pr', 'bio01'], scales={'aet': 4638.3, 'def': 4638.3,
	                                                                               'pr': 4638.3, 'bio01': 927.67}),
	        'hint': HINT, 'cases': CASES}
	out = _node(_panel() + HELPERS + steps + '\nconsole.log(JSON.stringify(out));', data)
	for (analysis, given), case in zip(CASES, out['cases']):
		applied, shown = case['applied'], case['shown']
		assert not _not_applied(applied['report']), (analysis, applied['report'])
		assert applied['report'][0].startswith(f'{analysis} (') and 'to compute it' in applied['report'][0]
		assert len(applied['layers']) == 1 and not applied['results'][1:], applied  # the region only: no result
		assert shown['json']['analysis'] == analysis and shown['json']['parameters'] == given, analysis
		assert shown['report'] == [f'Parameters of {analysis}: select the text of the box and copy it.']
		assert shown['json']['monitoreo']  # the version of the app (catalog.js)
		checked = parameters.check(shown['json'])
		assert checked['analysis'] == analysis and checked['not_applied'] == [], (analysis, checked['not_applied'])
		assert checked['parameters'] == given
		assert set(given) <= parameters.accepted(analysis)
		areas.check(given['region'])  # a region of areas.region, checked without Earth Engine
	items = _app('out.items = find(controls, "Select", function (w) { return (w.opts.items || []).some(function (i) {'
	             'return i.value === "map_layer"; }); })[0].opts.items.map(function (i) { return i.value; });')['items']
	assert {a for a, _ in CASES} == set(items) - {'transect'}  # every analysis of the app (transect: its line drawn)


TRANSECT = r"""
// a line drawn with Draw a line and its profile: the profile is computed, and its parameters are those of transect
var LINE = {type: 'LineString', coordinates: [[-3.4, 37.0], [-3.3, 37.05], [-3.2, 37.1]]};
function geometry(json) {  // a geometry drawn: a geometry of the client, with its GeoJSON
	return new Proxy({}, {get: function (t, p) {
		if (p === 'toGeoJSON') return function () { return json; };
		return p === TAG ? true : typeof p === 'symbol' ? undefined : call(p);
	}});
}
apply({analysis: 'map_layer', parameters: {variable: 'NDVI', sensor: 'Landsat', start: '2020-01-01', end: '2020-12-31',
	metric: 'mean', temporal: 'period'}});
out.beforeLine = show('transect');
button('Draw a line and its profile').opts.onClick();
answer = {length: 20000, centroid: [-3.3, 37.05]};
drawn(geometry(LINE));
out.analysis = find(controls, 'Select', function (w) {
	return (w.opts.items || []).some(function (i) { return i.value === 'map_layer'; });
})[0].opts.value;
out.line = show();
out.applied = apply(out.line.json);
// a polygon drawn, the map view and a click on the map (an ecoregion, an island, a biome in the map view) as regions
answer = input.answer;
selectWith('view').opts.onChange('draw');
var SQUARE = {type: 'Polygon', coordinates: [[[-3.6, 36.9], [-3.5, 36.9], [-3.5, 37.0], [-3.6, 36.9]]]};
drawn(geometry(SQUARE));
out.regions = [show('map_layer').json.parameters.region];
selectWith('draw').opts.onChange('view');
button('Use the map view').opts.onClick();
out.regions.push(show().json.parameters.region);
['ecoregion', 'island', 'biome'].forEach(function (mode) {
	selectWith('view').opts.onChange(mode);
	answer = Object.assign(['Somewhere'], input.answer);  // the names at the point, and the region
	clicked({lon: -3.3, lat: 37.1});
	out.regions.push(show().json.parameters.region);
	selectWith(mode).opts.onChange('view');
});
// the analysis of the last computation
answer = Object.assign([], input.answer, {features: []});
out.last = ['Compute the time series', 'Trend table', 'Trend map', 'Make the animation', 'Add to the map',
	'Compute the areas'].map(function (label) {
	button(label).opts.onClick();
	return show().json.analysis;
});
check('Compare with another period').opts.onChange(true);
button('Compute the time series').opts.onClick();
out.last.push(show().json.analysis);
button('Add to the map').opts.onClick();
out.last.push(show().json.analysis);
"""


def test_the_line_and_the_regions_of_the_map():
	"""The line drawn for a profile is the line of transect, and the regions chosen on the map (a polygon drawn, the
	map view, the ecoregion, island and biome at a point) are those of areas.region; the analysis shown is that of
	the last computation (a comparison of periods: compare_series, compare_map)."""
	out = _app(TRANSECT)
	assert out['beforeLine']['report'][-1] == 'Without line: draw it (Gradients).'
	assert out['analysis'] == 'transect'
	p = out['line']['json']['parameters']
	assert p['line'] == {'type': 'LineString', 'coordinates': [[-3.4, 37.0], [-3.3, 37.05], [-3.2, 37.1]]}
	checked = parameters.check(out['line']['json'])
	assert checked['analysis'] == 'transect' and checked['not_applied'] == [] and 'region' not in p
	assert set(p) <= parameters.accepted('transect')
	assert _not_applied(out['applied']['report']) == {
		'line': 'the app takes the line drawn on the map (Gradients: Draw a line and its profile)'}
	drawn, view, ecoregion, island, biome = out['regions']
	assert drawn == {'geojson': {'type': 'Feature', 'properties': {'name': 'Drawn polygon'}, 'geometry': {
		'type': 'Polygon', 'coordinates': [[[-3.6, 36.9], [-3.5, 36.9], [-3.5, 37.0], [-3.6, 36.9]]]}}}
	assert view == {'bbox': [-3.62, 36.86, -3.5, 36.93]}
	assert ecoregion == {'ecoregion_at': [-3.3, 37.1]} and island == {'island_at': [-3.3, 37.1]}
	assert biome == {'biome_at': [-3.3, 37.1], 'within': {'bbox': [-3.62, 36.86, -3.5, 36.93]}}
	for region in out['regions']:
		areas.check(region)
	assert out['last'] == ['time_series', 'trend_table', 'trend_map', 'timelapse', 'map_layer', 'area_by_class',
	                       'compare_series', 'compare_map']


NOT_APPLIED = r"""
out.cases = input.bad.map(function (p) { return apply(p).report; });
out.box = box().opts.value;
"""

BAD = [
	# outputs, parameters of the services that are not options of the app, and others of no analysis
	{'monitoreo': '0.1.0', 'analysis': 'map_layer', 'parameters': {
		'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'variable': 'NDVI', 'sensor': 'Sentinel-3', 'csv': 'a.csv',
		'thumbnail': 'a.png', 'vmin': 0.1, 'palette': ['red'], 'colour': 'red', 'stat': 'mean', 'metric': 'mode',
		'temporal': 'weekly', 'start': '2021-02-31x', 'season': ['6-1', '08-31'],
		'quality': {'clouds': True, 'scene_clouds': 20, 'cloud_score': 'high'}}},
	# a variable of the catalog with the bands of the data of Earth Engine, the snow cover frequency (fixed filters,
	# only the mean), and a region of a file (of Python, R or the command line)
	{'analysis': 'timelapse', 'parameters': {'region': {'file': '/home/me/area.gpkg', 'name_field': 'name'},
	                                         'variable': 'SCF', 'sensor': 'Landsat', 'band': 'B4', 'metric': 'max',
	                                         'quality': {'snow': False}, 'step': 'daily'}},
	{'analysis': 'time_series', 'parameters': {'region': {'country': 'ESP'}, 'variable': 'NDVI', 'sensor': 'Landsat',
	                                           'other_variable': 'ELEVATION', 'other_sensor': 'Copernicus',
	                                           'ylim': [0, 1], 'scale': 30}},
	{'analysis': 'trend_map', 'parameters': {'region': {'admin1': [1653, 1654]}, 'variable': 'NDVI', 'sensor': 'Modis',
	                                         'alpha': 0.1, 'step': 'annual', 'part': 3}},
	{'analysis': 'region_stats', 'parameters': {'region': {'ecoregion_at': [-3.3]}, 'variable': 'NDVI',
	                                            'sensor': 'Landsat', 'stats': ['mean'],
	                                            'where': [{'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 1},
	                                                      {'variable': 'SLOPE', 'sensor': 'Copernicus', 'max': 20},
	                                                      {'variable': 'NDVI', 'sensor': 'Landsat', 'min': 0.2,
	                                                       'metric': 'max'}]}},
	# the files of other tools: the GeoTIFF of a map (as its map), the perimeter of a burned area (in its results)
	{'analysis': 'download_image', 'parameters': {'variable': 'NDVI', 'sensor': 'Landsat', 'resolution': 30,
	                                              'path': 'ndvi.tif', 'crs': 'EPSG:25830'}},
	{'analysis': 'burn_severity', 'parameters': {'sensor': 'Landsat', 'index': 'dNBR', 'collection': 'MODIS/061/MYD09GA',
	                                             'perimeter': 'fire.gpkg', 'burned_min': 0.2, 'metric': 'mean'}},
	{'analysis': 'burn_severity', 'parameters': {'sensor': 'Modis', 'index': 'dNBR'}},
	# data of Earth Engine by their ID: a band they do not have, a scale that is not a number
	{'analysis': 'map_layer', 'parameters': {'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'tmax',
	                                         'band_scale': 'x', 'sensor': 'Landsat', 'quality': {'clouds': False}}},
	{'analysis': 'transect', 'parameters': {'region': {'bbox': [0, 0, 1, 1]}, 'line': [[0, 0], [1, 1]],
	                                        'variable': 'NDVI', 'sensor': 'Landsat', 'points': 50}},
	# what is not an analysis, nor parameters
	{'analysis': 'find_protected_areas', 'parameters': {}},
	{'parameters': {'variable': 'NDVI'}},
	'{"analysis": "map_layer", "parameters": {',
	'map_layer.parameters.json',
	# a flat object, as the issue proposed them
	{'analysis': 'trend_table', 'variable': 'NDVI', 'sensor': 'Landsat', 'step': 'monthly', 'alpha': 0.05},
]


def test_what_cannot_be_applied_is_listed_with_the_reason():
	"""Apply lists each parameter it cannot apply and why, with the reasons of parameters.check where they apply (an
	output, a variable or a sensor that is not in the catalog, an analysis that is not one): a parameter of the
	services that is not an option of the app, a value its select does not have, a region it cannot use (a file, a
	country, several units), a line (drawn on the map), more conditions than it takes; and applies the rest."""
	out = _app(NOT_APPLIED, bad=BAD)
	cases = out['cases']
	first = _not_applied(cases[0])
	py = {p['name']: p['reason'] for p in parameters.check(BAD[0])['not_applied']}
	assert first['csv'] == first['thumbnail'] == py['csv'] == 'an output: each tool writes its own files'
	assert first['variable'] == first['sensor'] == py['variable'] == py['sensor']  # not in the catalog
	assert 'Sentinel-3 is not in the catalog of MonitorEO' in first['variable']
	assert py['colour'].startswith('not a parameter of map_layer in MonitorEO')
	for name in ('vmin', 'palette', 'colour', 'stat'):
		assert first[name] == 'not a parameter of map_layer in the Earth Engine app', name
	assert first['metric'].startswith('not an option of the app: mean, median, min, max, p5')
	assert first['temporal'] == 'not an option of the app: period, annual, monthly, 16-day'
	assert first['start'] == 'Not a valid date: "2021-02-31x". Use YYYY-MM-DD (and MM-DD for the season).'
	assert first['season'].startswith('Not a valid date')
	assert any('"scene_clouds": 20' in line and 'the app has no option for it' in line for line in cases[0])
	assert any('"cloud_score": "high"' in line and 'cloud_score: "high" is not a number.' in line for line in cases[0])
	assert cases[0][0] == 'map_layer (Map): press «Add to the map» to compute it.'
	assert cases[0][1].startswith('Saved with MonitorEO 0.1.0, applied in the app of ')
	second = _not_applied(cases[1])
	assert second['region'].startswith('a file of the computer: the app reads no files')
	assert second['band'].startswith('band: only for the data of Earth Engine given by their ID')
	assert second['metric'] == "SCF (Landsat) only takes the metric 'mean'"
	assert second['quality'] == 'Fixed filters of this variable: they cannot be changed.'
	assert second['step'] == 'not an option of the app: annual, monthly, 16-day'  # daily: only in Python
	third = _not_applied(cases[2])
	assert third['region'].startswith('a region the app cannot use')
	assert third['other_variable'] == third['other_sensor'] == 'the right axis is a variable of the catalog with dates'
	assert third['ylim'] == third['scale'] == 'not a parameter of time_series in the Earth Engine app'
	fourth = _not_applied(cases[3])
	assert fourth == {'region': 'the app takes one administrative unit',
	                  'alpha': 'the app takes as significant the trends with p < 0.05',
	                  'part': 'part is a month (1-12) with step monthly, 1-23 with 16-day; none (or 0) with annual'}
	fifth = _not_applied(cases[4])
	assert fifth['region'] == 'ecoregion_at is a point, [lon, lat] in degrees, e.g. [-3.3, 37.1]; not [-3.3]'
	assert fifth['stats'] == 'not a parameter of region_stats in the Earth Engine app'
	assert fifth['zones'].startswith('the app computes region_stats by zones')
	wheres = [line for line in cases[4] if line.startswith('· where (')]
	assert len(wheres) == 2 and all('one condition on a variable' in line for line in wheres)
	sixth = cases[5]
	assert sixth[0] == 'download_image is computed in the app as map_layer. map_layer (Map): press «Add to the map» ' \
	                   'to compute it.'
	assert _not_applied(sixth) == {'resolution': 'not a parameter of map_layer in the Earth Engine app',
	                               'crs': 'not a parameter of map_layer in the Earth Engine app',
	                               'path': 'an output: each tool writes its own files'}
	seventh = _not_applied(cases[6])
	assert seventh['collection'].startswith('collection is only for the index RdNBR with sensor Modis')
	assert seventh['perimeter'] == seventh['burned_min'] == \
		'given in the results of the severity (Perimeter of the burned area)'
	assert seventh['metric'] == 'not an option of the app: median'
	with pytest.raises(ValueError) as error:  # as the package refuses MODIS for the dNBR
		services.burn_severity({'bbox': [0, 0, 1, 1]}, 'Modis', '2021-01-01', '2021-02-01', '2022-01-01', '2022-02-01')
	assert _not_applied(cases[7]) == {'sensor': str(error.value)}
	ninth = _not_applied(cases[8])
	assert ninth['band'] == 'IDAHO_EPSCOR/TERRACLIMATE has no band tmax: its bands are aet, def, pr'
	assert ninth['band_scale'] == 'Band scale: "x" is not a number.'
	assert ninth['sensor'] == 'only for a variable of the catalog (variable and sensor)'
	assert ninth['quality'].startswith('These data keep their own mask')
	tenth = _not_applied(cases[9])
	assert tenth == {'region': 'not a parameter of transect in the Earth Engine app',
	                 'line': 'the app takes the line drawn on the map (Gradients: Draw a line and its profile)',
	                 'points': 'not a parameter of transect in the Earth Engine app'}
	with pytest.raises(ValueError) as error:
		parameters.check({'analysis': 'find_protected_areas', 'parameters': {}})
	assert cases[10] == [str(error.value)]
	with pytest.raises(ValueError) as error:
		parameters.check({'parameters': {'variable': 'NDVI'}})
	assert cases[11] == [str(error.value)]
	assert cases[12][0].startswith('the parameters are not valid JSON: ')
	assert cases[13][0].startswith('map_layer.parameters.json: not a JSON object of parameters')
	assert cases[14] == ['trend_table (Trends (Mann-Kendall and Sen)): press «Trend table» to compute it.']


PROFILE = r"""
// the series asked for, each answered without rows: the variable and the pixel filters (sensors.filters of its spec)
// with which the app computes each axis
var asked = [];
MonitorEO.series = function (s) {
	var e = MonitorEO.entryOf(s);
	asked.push({ref: e.ref, filters: MonitorEO.filters(e, s.quality), cloud_score: s.quality.cloud_score});
	arguments[8](null, []);
};
out.cases = input.profiles.map(function (p) {
	var applied = apply({analysis: 'time_series', parameters: p});
	var shown = show();
	asked = [];
	button('Compute the time series').opts.onClick();
	return {applied: applied.report, shown: shown, asked: asked.splice(0)};
});
// the NDVI of MODIS Aqua (the second entry of NDVI and Modis) chosen for the right axis
function rightAxis() {
	return find(controls, 'Select', function (w) {
		var values = (w.opts.items || []).map(function (i) { return i.value; });
		return values.indexOf('none') >= 0 && values.indexOf(input.aqua) >= 0;
	})[0];
}
apply({analysis: 'time_series', parameters: input.profiles[0]});
rightAxis().opts.onChange(input.aqua);
out.aqua = show();
apply(out.aqua.json);
out.aquaApplied = rightAxis().opts.value;
"""

BBOX = {'bbox': [-3.62, 36.86, -3.5, 36.93]}
PROFILES = [
	# the NDSI on the left and the NDVI on the right, with the filters as the QGIS plugin writes them
	dict(variable='NDSI', sensor='Modis', other_variable='NDVI', other_sensor='Modis',
	     quality={'clouds': 'auto', 'water': 'auto', 'snow': 'auto', 'aerosols': 'auto'}),
	# the NDVI on the left and the NDSI on the right (other_sensor: that of the left), the default filters
	dict(variable='NDVI', sensor='Sentinel-2', other_variable='NDSI'),
	# the snow filter of the NDSI off, and the cloud filter off for both
	dict(variable='NDSI', sensor='Landsat', other_variable='NDVI', quality={'snow': False, 'clouds': False}),
	# fixed filters on the left (the SCF, the CF): the filters are those of the right axis
	dict(variable='SCF', sensor='Landsat', other_variable='NDVI', quality={'water': False, 'snow': 'auto'}),
	dict(variable='CF', sensor='Sentinel-2', other_variable='NDSI', quality={'cloud_score': None}),
	# the snow filter checked for the NDSI of the left (it measures it), and the NDSI on the right: no value gives both
	dict(variable='NDSI', sensor='Landsat', other_variable='NDSI', other_sensor='Sentinel-2', quality={'snow': True}),
]
PROFILES = [dict(region=BBOX, start='2019-01-01', end='2021-12-31', step='monthly', metric='mean', doy=True, **p)
            for p in PROFILES]
# the pixel filters that Show writes for each of them
PROFILE_QUALITY = [
	{'clouds': True, 'water': True, 'snow': 'auto', 'aerosols': True},
	{'clouds': True, 'water': True, 'snow': 'auto', 'aerosols': True, 'cloud_score': 0.6},
	{'clouds': False, 'water': True, 'snow': 'auto', 'aerosols': True},
	{'clouds': True, 'water': False, 'snow': True, 'aerosols': True},
	{'clouds': True, 'water': True, 'snow': 'auto', 'aerosols': True, 'cloud_score': None},
	{'clouds': True, 'water': True, 'snow': True, 'aerosols': True, 'cloud_score': 0.6},
]


def test_the_profile_on_two_axes_writes_the_filters_of_both():
	"""A profile with a variable on the right axis: the services take one quality for both variables
	(services._other_spec), so Show writes for each filter the value that gives each axis the filters the app computes
	it with ('auto' where only one of them leaves it out, as the QGIS plugin; with fixed filters on the left, those of
	the right axis), and Apply takes them back; a filter that no value gives both axes, and a right axis that the
	services cannot name (the second collection of a variable and sensor), are said."""
	aqua = catalog.find('NDVI', 'Modis', 'MODIS/061/MYD13Q1')
	out = _app(PROFILE, profiles=PROFILES, aqua=aqua['ref'])
	for given, want, case in zip(PROFILES, PROFILE_QUALITY, out['cases']):
		assert not _not_applied(case['applied']), (given, case['applied'])
		shown = case['shown']['json']
		assert shown['parameters']['quality'] == want, given
		checked = parameters.check(shown)
		assert checked['not_applied'] == [] and checked['parameters']['quality'] == want
		left = catalog.find(given['variable'], given['sensor'])
		right = catalog.find(given['other_variable'], given.get('other_sensor', given['sensor']))
		(app_left, app_right) = case['asked']
		assert (app_left['ref'], app_right['ref']) == (left['ref'], right['ref']), given
		assert sensors.filters(left, want) == app_left['filters'], given  # the left axis, as the app computes it
		assert app_right['cloud_score'] == want.get('cloud_score', sensors.QUALITY['cloud_score'])
		if given.get('quality', {}).get('snow') is not True:
			assert sensors.filters(right, want) == app_right['filters'], given  # and the right one
			assert case['shown']['report'] == ['Parameters of time_series: select the text of the box and copy it.']
	# the NDSI with its snow filter on, and the NDSI on the right: the app computes the right axis without it, the other
	# tools with it
	right = catalog.find('NDSI', 'Sentinel-2')
	app_right = out['cases'][-1]['asked'][1]['filters']
	assert dict(sensors.filters(right, PROFILE_QUALITY[-1]), snow=False) == app_right and not app_right['snow']
	assert out['cases'][-1]['shown']['report'][-1] == 'Right axis: the app computes NDSI Sentinel-2 without the snow ' \
	                                                  'filter; the other tools, with the same pixel filters on both ' \
	                                                  'axes, with it.'
	# the NDVI of MODIS Aqua on the right axis: named by its variable and sensor, which the services take as Terra
	parameters_aqua = out['aqua']['json']['parameters']
	assert (parameters_aqua['other_variable'], parameters_aqua['other_sensor']) == ('NDVI', 'Modis')
	terra = catalog.find('NDVI', 'Modis')
	assert terra['col'] == 'MODIS/061/MOD13Q1' and out['aquaApplied'] == terra['ref']
	assert out['aqua']['report'][-1] == 'Right axis: NDVI Modis of MODIS/061/MYD13Q1; the other tools take the first ' \
	                                    'collection of its variable and sensor, MODIS/061/MOD13Q1.'


FIRE_AND_TRENDS = r"""
// the period of the map, then the burn severity with a condition over the period before the fire, and over that of
// the map
apply({analysis: 'map_layer', parameters: {variable: 'NDVI', sensor: 'Landsat', start: '2015-01-01',
	end: '2020-12-31'}});
out.fire = input.fire.map(function (p) {
	var applied = apply({analysis: 'burn_severity', parameters: p});
	return {applied: applied.report, shown: show()};
});
// the annual trends of the QGIS plugin: part 0, the only part of the year (trends.parts)
out.annual = input.annual.map(function (c) {
	var applied = apply({analysis: c[0], parameters: c[1]});
	return {applied: applied.report, shown: show()};
});
"""


def test_the_condition_of_a_fire_and_the_part_of_annual_trends():
	"""The condition of a burn severity is computed over the period before the fire (as the package and the QGIS plugin
	write it): its own period is that one, not the period of the map; the annual trends of the QGIS plugin, with part
	0 (the year, trends.parts), are applied."""
	condition = {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'min': 0.2}
	fire = dict(region=BBOX, sensor='Sentinel-2', start='2023-06-01', end='2023-07-31', other_start='2023-09-01',
	            other_end='2023-10-31')
	fires = [dict(fire, where=[dict(condition, period=['2023-06-01', '2023-07-31'])]),
	         dict(fire, where=[dict(condition, period=['2015-01-01', '2020-12-31'])])]
	trend = dict(region=BBOX, variable='NDVI', sensor='Landsat', start='2010-01-01', end='2020-12-31', step='annual',
	             part=0)
	annual = [('trend_map', trend), ('area_by_class', dict(trend, trend=True))]
	out = _app(FIRE_AND_TRENDS, fire=fires, annual=annual)
	before, of_map = out['fire']
	assert not _not_applied(before['applied']), before['applied']
	assert before['shown']['json']['parameters']['where'] == [condition]  # over the period before the fire
	assert _not_applied(of_map['applied']) == {
		'where': 'the app computes the condition with its mean over the period of the analysis'}
	for (analysis, given), case in zip(annual, out['annual']):
		assert parameters.check({'analysis': analysis, 'parameters': given})['not_applied'] == []
		assert not _not_applied(case['applied']), (analysis, case['applied'])
		shown = case['shown']['json']['parameters']
		assert shown['step'] == 'annual' and 'part' not in shown, analysis


def test_the_app_takes_only_parameters_of_the_services():
	"""For each analysis, the parameters the app takes (those it does not list as not parameters of that analysis in
	the app, nor as outputs) are parameters of its function of monitoreo.services, given any name of any of them; the
	analyses of the package that the app computes as another one (the files of its maps and series) are applied as
	that one."""
	names = sorted(set().union(*(parameters.accepted(a) for a in parameters.ANALYSES)) | set(readme.NOT_ARGS) |
	               {'bogus', 'name', 'figure'})
	steps = r"""
out.analyses = parameters_analyses = find(controls, 'Select', function (w) {
	return (w.opts.items || []).some(function (i) { return i.value === 'map_layer'; });
})[0].opts.items.map(function (i) { return i.value; });
out.taken = {};
out.applied = {};
input.all.forEach(function (analysis) {
	var p = {};
	input.names.forEach(function (n) { p[n] = '?'; });
	var r = apply({analysis: analysis, parameters: p}).report;
	out.applied[analysis] = r[0];
	var refused = r.filter(function (l) {
		return / \("\?"\): (not a parameter of |an output: )/.test(l);
	}).map(function (l) { return l.slice(2).split(' (')[0]; });
	out.taken[analysis] = input.names.filter(function (n) { return refused.indexOf(n) < 0; });
});
"""
	from test_themes import _build
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': ASSETS,
	        'answer': ANSWER, 'hint': HINT, 'names': names, 'all': list(parameters.ANALYSES)}
	out = _node(_panel() + HELPERS + steps + '\nconsole.log(JSON.stringify(out));', data)
	assert set(out['analyses']) <= set(parameters.ANALYSES)
	for analysis in parameters.ANALYSES:
		applied = out['applied'][analysis]
		target = applied.split(' (')[0].split(' is computed in the app as ')[-1].split('. ')[-1]
		assert target in out['analyses'], applied  # every analysis of the package is applied
		assert set(out['taken'][analysis]) <= parameters.accepted(target), (analysis, target)
	assert out['taken']['map_layer'] and 'region' in out['taken']['map_layer']


DEFAULTS = r"""
// the panel far from the defaults, then the parameters of each analysis with only the variable: the others are the
// defaults of the services
apply({analysis: 'trend_map', parameters: {variable: 'NDVI', sensor: 'Sentinel-2', step: '16-day', part: 3,
	output: 'tau', metric: 'max', alpha: 0.05, season: ['01-01', '02-01'], quality: {clouds: false},
	where: [{variable: 'SLOPE', sensor: 'Copernicus', max: 10}]}});
apply({analysis: 'time_series', parameters: {variable: 'NDVI', sensor: 'Landsat', step: 'daily', metric: 'p5',
	stat: 'cv', doy: true, interannual: 'max'}});
apply({analysis: 'map_layer', parameters: {variable: 'NDVI', sensor: 'Landsat', metric: 'p95', temporal: 'annual',
	interannual: 'std'}});
apply({analysis: 'timelapse', parameters: {variable: 'NDVI', sensor: 'Landsat', step: 'monthly', metric: 'p95'}});
apply({analysis: 'burn_severity', parameters: {sensor: 'Landsat', index: 'RBR'}});
out.shown = {};
input.analyses.forEach(function (analysis) {
	apply({analysis: analysis, parameters: analysis === 'burn_severity' ? {} : {variable: 'NDVI', sensor: 'Landsat'}});
	out.shown[analysis] = show(analysis).json.parameters;
});
"""


def test_what_is_not_given_takes_the_defaults_of_the_services():
	"""Apply sets what the parameters do not give to the defaults of the arguments of the services (the metric, the
	step, the statistic...; the pixel filters of sensors.QUALITY; no season, no conditions), whatever the panel had."""
	analyses = ['map_layer', 'rgb_map', 'compare_map', 'region_stats', 'transect', 'timelapse', 'time_series',
	            'compare_series', 'trend_table', 'trend_map', 'burn_severity']
	from test_themes import _build
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': ASSETS,
	        'answer': ANSWER, 'hint': HINT, 'analyses': analyses}
	out = _node(_panel() + HELPERS + DEFAULTS + '\nconsole.log(JSON.stringify(out));', data)
	for analysis in analyses:
		shown = out['shown'][analysis]
		signature = inspect.signature(getattr(services, analysis)).parameters
		for name, value in shown.items():
			if name in signature and signature[name].default not in (None, inspect.Parameter.empty):
				assert value == signature[name].default, (analysis, name)
		assert 'season' not in shown and 'where' not in shown and 'doy' not in shown and 'alpha' not in shown, analysis
		if analysis != 'burn_severity':  # Landsat: no Cloud Score+
			assert shown['quality'] == {f: sensors.QUALITY[f] for f in sensors.FILTERS}, analysis
	assert out['shown']['map_layer'] == {'variable': 'NDVI', 'sensor': 'Landsat', 'start': '2025-01-01',
	                                     'end': '2025-12-31', 'metric': 'median', 'temporal': 'period',
	                                     'quality': {f: True for f in sensors.FILTERS}}
	assert out['shown']['burn_severity']['sensor'] == 'Sentinel-2' and out['shown']['burn_severity']['index'] == 'dNBR'
	assert out['shown']['burn_severity']['quality'] == {f: True for f in sensors.FILTERS} | {'cloud_score': 0.6}


def test_the_help_of_the_parameters_in_both_languages():
	"""The group of the parameters says what Show and Apply do, in English and Spanish, with a link to the page of the
	Earth Engine app of the manual, as the other links of the app to the manual."""
	steps = r"""
function help() {
	return find(controls, 'Label', function (w) { return w.opts.url && /parameters|parámetros/.test(w.opts.url); })
		.map(function (w) { return [w.opts.value, w.opts.url]; });
}
out.en = help();
button('Español').opts.onClick();
out.es = help();
out.buttons = ['Mostrar los parámetros', 'Aplicar los parámetros'].map(function (l) { return Boolean(button(l)); });
"""
	out = _app(steps)
	manual = _catalog_about()['manual']
	(en, url_en), = out['en']
	(es, url_es), = out['es']
	assert url_en == manual + '/Earth-Engine-app#parameters-of-the-analysis'
	assert url_es == manual + '/App-de-Earth-Engine#parámetros-del-análisis'
	assert 'Show' in en and 'Apply' in en and 'without computing' in en and 'Manual: Earth Engine app.' in en
	assert 'Mostrar' in es and 'Aplicar' in es and 'sin calcular' in es and 'Manual: App de Earth Engine.' in es
	assert out['buttons'] == [True, True]


def _catalog_about():
	with open(os.path.join(GEE, 'catalog.js'), encoding='utf-8') as f:
		text = f.read()
	return json.loads(text[text.index('{'):text.rstrip().rindex('}') + 1])['about']


def test_the_app_published_has_the_parameters():
	"""gee/monitoreo_app.js (python gee/build.py --app-only) carries the parameters of core.js and ui.js."""
	with open(os.path.join(GEE, 'monitoreo_app.js'), encoding='ascii') as f:
		app = f.read()
	for name in ('function readParameters(', 'function findEntry(', 'function applyParameters(',
	             'function parametersOf(', 'function parametersWidgets('):
		assert name in app, name
