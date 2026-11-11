"""The true colour (RGB) of the images of a variable in the app of the Earth Engine Code Editor (gee/), without Earth
Engine: the bands of each sensor, the metrics and the stretch of gee/core.js are those of the package, the app refuses
what the package refuses with the same messages (with Node, if it is installed), its option Layer of the map is in
both languages and gee/monitoreo_app.js is catalog.js, core.js and ui.js as they are. tests/test_gee.py computes the
true colour with both, with Earth Engine."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import types

import pytest

from monitoreo import catalog, composite, maps, sensors, services, variable

GEE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gee')
FILES = ('catalog.js', 'core.js', 'ui.js')


def _read(name):
	with open(os.path.join(GEE, name), encoding='utf-8') as f:
		return f.read()


def _js_value(text, name):
	"""The value of `var NAME = ...;` of a script of the app (a literal of strings, numbers, lists and objects)."""
	m = re.search(rf'\bvar {name} = (.+?);', text, re.S)
	assert m, f'no var {name}'
	literal = re.sub(r'([{,]\s*)(\w+)\s*:', r'\1"\2":', m.group(1).replace("'", '"'))  # keys without quotes
	return json.loads(literal)


def test_the_bands_metrics_and_stretch_are_those_of_the_package():
	core = _read('core.js')
	assert _js_value(core, 'RGB') == {k: [bands, scale, offset] for k, (bands, scale, offset) in sensors.RGB.items()}
	assert _js_value(core, 'RGB_BANDS') == sensors.RGB_BANDS
	# Landsat: the bands named red, green and blue by rawCollection, as sensors.raw_collection
	assert _js_value(core, 'LANDSAT_57') == sensors.LANDSAT_57 and _js_value(core, 'LANDSAT_89') == sensors.LANDSAT_89
	assert _js_value(core, 'RGB_METRICS') == composite.RGB_METRICS
	assert tuple(_js_value(core, 'MOSAICS')) == composite.MOSAICS
	assert tuple(_js_value(core, 'RGB_STRETCH')) == maps.RGB_STRETCH
	assert tuple(_js_value(core, 'RGB_RANGE')) == maps.RGB_RANGE


def _cases():
	"""Every variable of the menu of the app (not RBR, which compares two periods) with metrics that give colours
	and that do not, in the whole period and between years."""
	out = []
	for e in catalog.variables():
		if e.get('two_periods'):
			continue
		for metric, temporal, interannual in [('median', 'period', 'mean'), ('max', 'period', 'mean'),
		                                      ('p25', 'annual', 'min'), ('std', 'period', 'mean'),
		                                      ('count', 'period', 'mean'), ('sum', 'period', 'mean'),
		                                      ('mode', 'period', 'mean'), ('mean', 'annual', 'std'),
		                                      ('mean', 'monthly', 'p101')]:
			out.append({'ref': e['ref'], 'only': e.get('metric'), 'metric': metric, 'temporal': temporal,
			            'interannual': interannual})
	return out


def _python_check(c):
	"""The message of variable.check_rgb for the case C, or None if it has a true colour."""
	e = catalog.find(None, ref=c['ref'])
	dates = (None, None) if e.get('static') else ('2021-06-01', '2021-06-30')
	spec = services.make_spec(None, None, *dates, metric=c['only'] or 'mean', ref=c['ref'])
	spec.update(metric=c['metric'], temporal=c['temporal'], interannual=c['interannual'])
	try:
		variable.check_rgb(spec)
	except ValueError as error:
		return str(error)
	return None


VIS = [  # [percentiles of the bands, vmin, vmax]
	[{'red_p2': 0.03, 'red_p98': 0.21, 'green_p2': 0.025, 'green_p98': 0.18, 'blue_p2': 0.011, 'blue_p98': 0.16},
	 None, None],
	[{'red_p2': 0.03, 'red_p98': 0.21, 'green_p2': None, 'green_p98': 0.18, 'blue_p2': 0.011, 'blue_p98': 0.16},
	 None, None],  # a band without data: the fixed range
	[{}, None, None],
	[{'red_p2': 0.1, 'red_p98': 0.1, 'green_p2': 0.1, 'green_p98': 0.1, 'blue_p2': 0.1, 'blue_p98': 0.1}, None, None],
	[{'red_p2': 0.03, 'red_p98': 0.21, 'green_p2': 0.025, 'green_p98': 0.18, 'blue_p2': 0.011, 'blue_p98': 0.16},
	 0.0, None],
	[None, 0.02, 0.25],
]

NODE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
global.ee = {};  // the true colour is refused before Earth Engine: no function of ee is called
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[1], f), 'utf8'), {filename: f});
});
var mo = global.MonitorEO;
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
var checks = input.cases.map(function (c) {
	try {
		var s = mo.spec({ref: c.ref, period: ['2021-06-01', '2021-06-30'], metric: c.only || 'mean'});
		s.metric = c.metric;
		s.temporal = c.temporal;
		s.interannual = c.interannual;
		mo.checkRgb(s);
		return null;
	} catch (e) {
		return e.message;
	}
});
var rgb = mo.variables().filter(function (e) { return mo.rgbOf(e); }).map(function (e) { return e.ref; });
var vis = input.vis.map(function (v) { return mo.rgbVis(v[0], v[1], v[2]); });
var mosaics = input.mosaics.map(function (m) { return mo.mosaic(m[0], m[1]); });
var functions = input.functions.filter(function (f) { return typeof mo[f] !== 'function'; });
process.stdout.write(JSON.stringify({checks: checks, rgb: rgb, vis: vis, mosaics: mosaics, missing: functions}));
"""

MOSAICS = [['max', ['value', 'red', 'green', 'blue']], ['MIN', ['value', 'red', 'green', 'blue']],
           ['median', ['value', 'red', 'green', 'blue']], ['max', ['value']], ['p90', ['value', 'red']]]


@pytest.fixture(scope='module')
def app():
	"""The answers of gee/core.js (with catalog.js) in Node, with an object ee that computes nothing."""
	if not shutil.which('node'):
		pytest.skip('no Node')
	data = {'cases': _cases(), 'vis': VIS, 'mosaics': MOSAICS,
	        'functions': ['rgbOf', 'withRgb', 'checkMetric', 'checkRgbMetric', 'checkRgb', 'mosaic', 'composite',
	                      'image', 'collection', 'sensorCollection', 'rgbPercentiles', 'rgbVis']}
	run = subprocess.run(['node', '-e', NODE, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout)


def test_the_app_refuses_what_the_package_refuses(app):
	"""The same variables have a true colour, and the same refusals have the same messages (fixed layers, MODIS NDVI
	without a green band, the climate, sum, std, count and mode, also between years)."""
	assert app['missing'] == []
	assert sorted(app['rgb']) == sorted(e['ref'] for e in catalog.variables() if sensors.rgb_of(e))
	cases = _cases()
	assert len(app['checks']) == len(cases)
	for c, js in zip(cases, app['checks']):
		assert js == _python_check(c), c
	messages = set(app['checks'])
	assert None in messages  # some have it
	assert any(m and 'is a fixed layer, without dates: it has no images, nor true colour' in m for m in messages)
	assert 'NDVI (Modis) has no true colour: only the variables of Sentinel-2 and Landsat and the cloud frequency of ' \
		'MODIS (MOD09GA, MYD09GA) have images with red, green and blue bands' in messages
	assert any(m and m.endswith('the sum of the red, green and blue bands is not a colour') for m in messages)
	assert any(m and m.startswith('unknown metric p101') for m in messages)


def test_the_stretch_and_the_mosaics_of_the_app(app, monkeypatch):
	"""rgbVis gives the range of maps.rgb_vis from the same percentiles (the lowest p2 and the highest p98 of the three
	bands, or 0 to 0.3 without them), and mosaic that of composite._mosaic."""
	class Image:
		def __init__(self, stats):
			self.stats = stats

		def select(self, bands):
			return self

		def reduceRegion(self, *args, **kwargs):
			return self

		def getInfo(self):
			return self.stats

	fake = types.SimpleNamespace(Image=Image, Reducer=types.SimpleNamespace(percentile=lambda p: p),
	                             EEException=Exception)
	monkeypatch.setattr(maps, 'ee', fake)
	for (stats, vmin, vmax), js in zip(VIS, app['vis']):
		assert js == maps.rgb_vis(stats, None, None, vmin, vmax), (stats, vmin, vmax)
	assert app['vis'][0] == {'bands': ['red', 'green', 'blue'], 'min': 0.011, 'max': 0.21}
	assert (app['vis'][1]['min'], app['vis'][1]['max']) == maps.RGB_RANGE
	assert [composite._mosaic(m, bands) for m, bands in MOSAICS] == app['mosaics'] == ['max', 'min', None, None, None]


def _texts(ui, lang):
	"""The texts of LANG of the dictionary T of gee/ui.js."""
	es, en = ui.index('\tes: {'), ui.index('\ten: {')
	block = ui[es:en] if lang == 'es' else ui[en:ui.index('var METRICS')]
	return dict(re.findall(r"""['"]?([\w-]+)['"]?: '((?:[^'\\]|\\.)*)'""", block))


def test_the_layer_of_the_map_in_both_languages():
	ui = _read('ui.js')
	es, en = _texts(ui, 'es'), _texts(ui, 'en')
	assert set(es) == set(en)  # every text in both languages
	assert {k: en[k] for k in ('layer', 'l_index', 'l_rgb', 'l_both')} == \
		{'layer': 'Layer', 'l_index': 'Index', 'l_rgb': 'True colour (RGB)', 'l_both': 'Both'}
	assert {k: es[k] for k in ('layer', 'l_index', 'l_rgb', 'l_both')} == \
		{'layer': 'Capa', 'l_index': 'Índice', 'l_rgb': 'Color verdadero (RGB)', 'l_both': 'Ambas'}
	assert en['rgbLegend'] == 'True colour (red, green, blue): reflectance from %s to %s'
	assert es['rgbLegend'] == 'Color verdadero (rojo, verde, azul): reflectancia de %s a %s'
	# every reason why there is no true colour, and the other texts of the true colour, in both languages
	reasons = set(re.findall(r"return '(rgb\w+)';", ui))
	assert reasons == {'rgbStatic', 'rgbNone', 'rgbCompare', 'rgbMetric'}
	keys = reasons | {'rgbNote', 'rgbLegend', 'rgbRangeNote', 'downloadRgb'}
	assert keys <= set(es) and keys <= set(en)
	assert all(es[k] != en[k] for k in keys)
	# the select of the layer: the index, the true colour or both; both adds the true colour first (under the index)
	assert "['index', 'rgb', 'both'].map(function (x) { return {value: x, label: t('l_' + x)}; })" in ui
	add = ui[ui.index('function addMap()'):ui.index('function mapWidgets()')]
	assert 'mo.image(s, geom, null, true)' in add and 'mo.rgbPercentiles(' in add
	assert add.index('map.addLayer(rgb, ') < add.index('map.addLayer(band, vis, name)')
	assert "downloadWidget(rgb, e, mo.RGB_BANDS, name, t('downloadRgb'), '_RGB')" in add


def test_the_script_of_the_app_is_its_parts(tmp_path, monkeypatch):
	"""gee/monitoreo_app.js is catalog.js, core.js and ui.js as they are: python gee/build.py --app-only after
	changing core.js or ui.js (without Earth Engine)."""
	spec = importlib.util.spec_from_file_location('monitoreo_gee_build', os.path.join(GEE, 'build.py'))
	build = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(build)
	for name in FILES:
		shutil.copy(os.path.join(GEE, name), tmp_path)
	monkeypatch.setattr(build, 'HERE', str(tmp_path))
	build.app()
	with open(os.path.join(GEE, 'monitoreo_app.js'), encoding='ascii') as f:
		assert f.read() == (tmp_path / 'monitoreo_app.js').read_text(encoding='ascii'), \
			'run python gee/build.py --app-only'


def test_the_stretch_reduces_as_the_app(monkeypatch):
	"""The percentiles of the stretch of the true colour are reduced with the same arguments in Python (maps.rgb_vis)
	and in the app (rgbPercentiles): those of Earth Engine are approximate, and the size of the tiles (tileScale)
	changes them a little (the parity of the SCF of Sierra Nevada differed in its percentile 2)."""
	import types
	got = {}

	class Image:
		def __init__(self, *a):
			pass

		def select(self, bands):
			return self

		def reduceRegion(self, *args, **kwargs):
			got.update(kwargs)
			return self

		def getInfo(self):
			return {}

	fake = types.SimpleNamespace(Image=Image, Reducer=types.SimpleNamespace(percentile=lambda p: p),
	                             EEException=Exception)
	monkeypatch.setattr(maps, 'ee', fake)
	maps.rgb_vis(None, None, 30)
	js = re.search(r'function rgbPercentiles\(.*?\n\t}', _read('core.js'), re.S).group(0)
	assert (got['bestEffort'], got['maxPixels'], got['tileScale']) == (True, int(1e6), 4)
	assert 'bestEffort: true' in js and 'maxPixels: 1e6' in js and 'tileScale: 4' in js
