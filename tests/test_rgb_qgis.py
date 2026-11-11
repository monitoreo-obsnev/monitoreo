"""The true colour of the images of a variable (services.download_rgb and services.rgb_map, issue #24) in the QGIS
plugin, without QGIS and without Earth Engine: the list Layer (Index, True colour (RGB), Both) of its group Map and of
the window of a time series, when it is greyed out, its help, the layers it computes (the true colour of the same
images and pixels as the map, on its grid) and the rules of Bandit for the code of the plugin. The module dock is
imported with QGIS and Qt replaced by empty classes, and the services are faked; qgis/test_plugin.py runs the plugin
with QGIS and Earth Engine."""

import ast
import os
import sys
import types

import pytest

from monitoreo import services

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, 'qgis', 'monitoreo_qgis')
REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
WHERE = [{'variable': 'ELEVATION', 'sensor': 'Copernicus', 'collection': 'COPERNICUS/DEM/GLO30_2024_1', 'min': 800.0},
         {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'collection': 'COPERNICUS/S2_SR_HARMONIZED', 'min': 0.2,
          'period': ['2021-01-01', '2021-12-31']}]
# the arguments of the map of June of a monthly series (dock.add_result_map), with its conditions
OPTS = {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'collection': 'COPERNICUS/S2_SR_HARMONIZED',
        'quality': {'clouds': True, 'water': True, 'snow': True, 'aerosols': True, 'cloud_score': 0.6},
        'where': WHERE, 'start': '2021-06-01', 'end': '2021-06-30', 'metric': 'mean'}
KINDS = [('Index', 'index'), ('True colour (RGB)', 'rgb'), ('Both', 'both')]  # the same in every tool
QT = ('qgis', 'qgis.core', 'qgis.gui', 'qgis.PyQt', 'qgis.PyQt.QtCore', 'qgis.PyQt.QtGui', 'qgis.PyQt.QtWidgets')


def _read(name):
	with open(os.path.join(PLUGIN, name), encoding='utf-8') as f:
		return f.read()


class _Qt(types.ModuleType):
	"""A module of QGIS or Qt whose names are empty classes: enough to import the plugin without QGIS."""

	def __getattr__(self, name):
		if name.startswith('__'):
			raise AttributeError(name)
		cls = type(name, (), {})
		setattr(self, name, cls)
		return cls


def _forget_plugin():
	return {m: sys.modules.pop(m) for m in [m for m in sys.modules if m.startswith('monitoreo_qgis')]}


@pytest.fixture
def plugin(monkeypatch):
	"""The modules dock, results and helptexts of the plugin, imported with QGIS and Qt replaced by empty classes (their
	functions, not their widgets)."""
	for name in QT:
		monkeypatch.setitem(sys.modules, name, _Qt(name))
	monkeypatch.syspath_prepend(os.path.join(ROOT, 'qgis'))
	before = _forget_plugin()
	import monitoreo_qgis.dock as dock
	import monitoreo_qgis.helptexts as helptexts
	import monitoreo_qgis.results as results
	yield types.SimpleNamespace(dock=dock, results=results, helptexts=helptexts)
	_forget_plugin()
	sys.modules.update(before)


@pytest.fixture
def fake(monkeypatch):
	"""The map services faked: the calls they get (tool, region, arguments), FAIL (the tools that fail) and answers
	like those of Earth Engine (the map on pixels of 30 m: a big region)."""
	calls, fail = [], set()

	def tool(name, out):
		def call(region, **kw):
			calls.append((name, region, kw))
			if name in fail:
				raise (ValueError if name == 'rgb_map' else RuntimeError)(f'{name} failed')
			return dict(out(kw), name=name)
		monkeypatch.setattr(services, name, call)

	tool('download_image', lambda kw: {'file': kw['path'], 'resolution': 30.0, 'native_resolution': 10.0, 'min': 0.2,
	                                   'max': 0.8, 'palette': ['000000', 'FFFFFF'], 'unit': '[unitless]'})
	tool('map_layer', lambda kw: {'url': 'https://tiles/{z}/{x}/{y}', 'min': 0.2, 'max': 0.8, 'palette': ['000000']})
	tool('download_rgb', lambda kw: {'file': kw['path'], 'resolution': kw['resolution'] or 10.0, 'min': 0.02,
	                                 'max': 0.25, 'bands': ['red', 'green', 'blue'], 'unit': '[unitless]'})
	tool('rgb_map', lambda kw: {'url': 'https://tiles/{z}/{x}/{y}', 'bands': ['red', 'green', 'blue'],
	                            'min': kw.get('vmin', 0.0), 'max': kw.get('vmax', 0.3)})
	return types.SimpleNamespace(calls=calls, fail=fail)


def _same(a, b):
	"""Whether the calls A and B got the same arguments of the variable (not the file nor the pixel size)."""
	strip = lambda kw: {k: v for k, v in kw.items() if k not in ('path', 'resolution')}  # noqa: E731
	return strip(a) == strip(b)


def test_both_is_the_true_colour_of_the_same_images_and_pixels_on_the_grid_of_the_map(plugin, fake, tmp_path):
	out = plugin.dock.maps_work('both', REGION, OPTS, str(tmp_path), services.download_image, services.map_layer)
	assert [c[0] for c in fake.calls] == ['download_image', 'download_rgb']
	(_, r1, index), (_, r2, rgb) = fake.calls
	assert r1 == r2 == REGION and _same(index, rgb) and index['where'] == WHERE  # the same images and pixels
	assert rgb['resolution'] == 30.0  # the pixels of the map (a big region: bigger than the 10 m of the data)
	assert index['path'] == str(tmp_path / 'map.tif') and rgb['path'] == str(tmp_path / 'rgb.tif')
	assert index['max_pixels'] == rgb['max_pixels'] == plugin.dock.MAP_PIXELS
	assert set(out) == {'index', 'rgb'} and out['rgb']['name'] == 'download_rgb'


def test_the_true_colour_alone_and_its_tiles_with_the_stretch_of_the_series(plugin, fake, tmp_path):
	out = plugin.dock.maps_work('rgb', REGION, OPTS, str(tmp_path), services.download_image, services.map_layer)
	assert [c[0] for c in fake.calls] == ['download_rgb'] and set(out) == {'rgb'}
	assert fake.calls[0][2]['resolution'] is None  # the pixels of the data
	fake.calls.clear()
	fake.fail.add('download_rgb')
	out = plugin.dock.maps_work('rgb', REGION, OPTS, str(tmp_path), services.download_image, services.map_layer,
	                            stretch=(0.01, 0.2))
	assert [c[0] for c in fake.calls] == ['download_rgb', 'rgb_map']
	tiles = fake.calls[1][2]
	assert {k: tiles[k] for k in OPTS} == OPTS  # the same images and pixels
	assert (tiles['vmin'], tiles['vmax']) == (0.01, 0.2)  # comparable with the first true colour of the series
	assert 'url' in out['rgb'] and out['rgb']['error'] == 'download_rgb failed'


def test_the_map_is_added_even_if_its_true_colour_fails(plugin, fake, tmp_path):
	fake.fail.update({'download_rgb', 'rgb_map'})
	out = plugin.dock.maps_work('both', REGION, OPTS, str(tmp_path), services.download_image, services.map_layer)
	assert set(out) == {'index', 'rgb_error'} and out['rgb_error'] == 'rgb_map failed'
	with pytest.raises(ValueError, match='rgb_map failed'):  # alone: the task fails, with its message
		plugin.dock.maps_work('rgb', REGION, OPTS, str(tmp_path), services.download_image, services.map_layer)


def test_the_map_of_the_variable_alone_is_as_before(plugin, fake, tmp_path):
	out = plugin.dock.maps_work('index', REGION, OPTS, str(tmp_path), services.download_image, services.map_layer)
	assert [c[0] for c in fake.calls] == ['download_image'] and set(out) == {'index'}
	fake.fail.add('download_image')
	out = plugin.dock.maps_work('index', REGION, OPTS, str(tmp_path), services.download_image, services.map_layer,
	                            colors=(0.1, 0.9))
	assert [c[0] for c in fake.calls][1:] == ['download_image', 'map_layer']
	assert (fake.calls[-1][2]['vmin'], fake.calls[-1][2]['vmax']) == (0.1, 0.9)
	assert out['index']['error'] == 'download_image failed'


def test_what_has_no_true_colour_is_refused_before_earth_engine(plugin, monkeypatch, tmp_path):
	"""The real services: the NDVI of MODIS (MOD13Q1 has no green band) and the fixed layers are refused without
	Earth Engine; with Both, the map comes with the reason as a warning."""
	modis = dict(OPTS, sensor='Modis', collection='MODIS/061/MOD13Q1', where=None)
	with pytest.raises(ValueError, match='has no true colour'):
		plugin.dock.maps_work('rgb', REGION, modis, str(tmp_path), services.download_image, services.map_layer)
	elevation = {'variable': 'ELEVATION', 'sensor': 'Copernicus', 'collection': 'COPERNICUS/DEM/GLO30_2024_1'}
	with pytest.raises(ValueError, match='fixed layer'):
		plugin.dock.maps_work('rgb', REGION, elevation, str(tmp_path), services.download_image, services.map_layer)
	map_only = lambda region, path=None, max_pixels=None, **kw: {'file': path, 'resolution': 250.0}  # noqa: E731
	out = plugin.dock.maps_work('both', REGION, modis, str(tmp_path), map_only, services.map_layer)
	assert 'has no true colour' in out['rgb_error'] and out['index']['resolution'] == 250.0


class _Combo:
	"""A QComboBox of (label, value)."""

	def __init__(self, items):
		self.items, self.index, self.enabled, self.tip = list(items), 0, True, ''

	def findData(self, value):
		return [v for _, v in self.items].index(value)

	def setCurrentIndex(self, i):
		self.index = i

	def currentData(self):
		return self.items[self.index][1]

	def setEnabled(self, on):
		self.enabled = on

	def setToolTip(self, text):
		self.tip = text


def test_the_list_layer_of_the_map_only_with_a_true_colour(plugin):
	"""The list Layer of the group Map is greyed out, at Index and with the reason in its tooltip, for the variables
	without true colour (services.has_rgb), the fixed layers and Compare with."""
	dock = plugin.dock
	assert dock.MAP_KINDS == plugin.results.MAP_KINDS == KINDS
	rows = [v for v in services.list_variables(lang='en') if not v.get('two_periods')]
	seen = set()
	for row in rows:
		for compare in (False, True):
			panel = types.SimpleNamespace(map_kind=_Combo(KINDS),
			                              variable=types.SimpleNamespace(currentData=lambda v=row: v),
			                              compare_on=types.SimpleNamespace(isChecked=lambda on=compare: on))
			panel.map_kind.setCurrentIndex(2)  # Both
			dock.MonitorEODock.update_map_kind(panel)
			rgb = services.has_rgb(row['variable'], row['sensor'], row['collection'])
			assert bool(row.get('rgb')) == rgb, row
			enabled = rgb and not row.get('static') and not compare
			assert panel.map_kind.enabled == enabled, (row['variable'], row['sensor'], compare)
			assert panel.map_kind.currentData() == ('both' if enabled else 'index')
			if row.get('static'):
				assert 'fixed layer' in panel.map_kind.tip
			elif not rgb:
				assert 'has no true colour' in panel.map_kind.tip
			elif compare:
				assert 'Compare with' in panel.map_kind.tip
			else:
				assert 'percentiles 2 and 98' in panel.map_kind.tip
			seen.add((row['sensor'], enabled))
	assert {('Sentinel-2', True), ('Landsat', True), ('Modis', True), ('Modis', False), ('Copernicus', False),
	        ('ERA5-Land', False)} <= seen


def test_the_window_of_a_series_and_the_panel_offer_the_true_colour(plugin):
	"""The window of a series has the list Layer (map_kind) beside Map of (map_choice) only if its images have a true
	colour, which the panel tells it (res['rgb'], services.has_rgb); its maps keep the pixels of the series (its
	conditions «Only the pixels where») and the stretch of its first true colour."""
	results, dock = _read('results.py'), _read('dock.py')
	assert "setObjectName('map_choice')" in results and "setObjectName('map_kind')" in results
	assert "if not trends and res.get('rgb'):" in results and "row.addWidget(QLabel('Layer'))" in results
	assert "kind.currentData() if kind else 'index'" in results
	assert "res['rgb'] = services.has_rgb(var['variable'], var['sensor'], var['collection'])" in dock
	assert "f.addRow('Layer', info(self.map_kind, HELP['map_kind']))" in dock
	assert "('variable', 'sensor', 'collection', 'quality', 'season', 'where')" in dock  # the where of the series
	assert "kept['rgb_stretch'] = (c['min'], c['max'])" in dock and "f'{label} · true colour'" in dock
	for name in ('download_rgb', 'rgb_map'):
		assert f'services.{name}(' in dock


def test_the_true_colour_layer_and_its_legend(plugin):
	dock = plugin.dock
	assert dock.rgb_caption(0.0123, 0.25) == 'True colour (red, green, blue): reflectance from 0.0123 to 0.25'
	source = _read('dock.py')
	assert 'QgsMultiBandColorRenderer(provider, *bands)' in source
	assert 'QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum' in source  # QGIS 4 enums
	assert 'self.add_rgb_layer(c, rgb_name, group, kept.get(' in source


def test_the_help_explains_the_true_colour(plugin):
	help_ = plugin.helptexts.HELP
	text = help_['map_kind']
	for words in ('<b>Index</b>', '<b>True colour (RGB)</b>', '<b>Both</b>', 'percentiles 2 and 98',
	              'same pixels', 'Compare with', 'fixed layers', 'More in the manual'):
		assert words in text, words
	assert f'{plugin.helptexts.about.MANUAL}/QGIS-plugin#4-add-the-map' in text
	assert '<b>True colour (RGB)</b>' in help_['series_list'] and '<b>Layer</b>' in help_['series_list']


def test_the_code_of_the_plugin_follows_the_rules_of_bandit():
	"""plugins.qgis.org scans the plugin with Bandit (qgis/build_plugin.py fails on any finding): no assert and no
	broad except that only passes."""
	for name in sorted(os.listdir(PLUGIN)):
		if not name.endswith('.py'):
			continue
		for node in ast.walk(ast.parse(_read(name))):
			assert not isinstance(node, ast.Assert), f'{name}:{node.lineno}: assert'
			if isinstance(node, ast.ExceptHandler):
				broad = node.type is None or getattr(node.type, 'id', None) in ('Exception', 'BaseException')
				only_pass = all(isinstance(s, (ast.Pass, ast.Continue)) for s in node.body)
				assert not (broad and only_pass), f'{name}:{node.lineno}: except: pass'
