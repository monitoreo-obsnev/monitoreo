"""The parameters of an analysis (monitoreo.parameters, issue #85) in the QGIS plugin, without QGIS and without Earth
Engine: the parameters that the button Parameters of each analysis of the panel copies or saves are the arguments that
its button gives to monitoreo.services (one function builds them for both), the panel takes back what it saves, the
mapping of some parameters to the fields of the panel reports what it cannot apply (with the reason), the window of a
result shows and saves the parameters of its analysis, and the help explains them. The module dock is imported with
QGIS and Qt replaced by empty classes (as tests/test_rgb_qgis.py), its panel made of small fakes of its widgets, and
the services are faked; qgis/test_parameters_offline.py applies them to the real panel with the Python of QGIS."""

import ast
import inspect
import json
import os
import sys
import types

import pytest

from monitoreo import parameters, sensors, services

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, 'qgis', 'monitoreo_qgis')
QT = ('qgis', 'qgis.core', 'qgis.gui', 'qgis.PyQt', 'qgis.PyQt.QtCore', 'qgis.PyQt.QtGui', 'qgis.PyQt.QtWidgets')
REGION = {'bbox': [-3.62, 36.86, -3.5, 36.93]}
LINE = [[-3.6, 37.15], [-3.45, 37.1]]
OUTPUTS = ('csv', 'path', 'folder', 'chart')
# the button of each analysis of the panel (dock.PANEL) and the method it runs
RUNS = {'series': 'run_series', 'trend_table': 'run_trend_table', 'trend_map': 'run_trend_map', 'map': 'run_map',
        'areas': 'run_areas', 'zones': 'run_zones', 'transect': 'run_transect', 'animation': 'run_timelapse',
        'export_map': 'run_export_image', 'export_series': 'run_export_series', 'burn': 'run_burn'}


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
	"""The modules dock, results and helptexts of the plugin, imported with QGIS and Qt replaced by empty classes."""
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
	"""The services that the buttons of the panel call, faked (with the signatures of the real ones, which
	monitoreo.parameters reads): the calls they get, (service, arguments)."""
	calls = []

	def tool(name, first='region'):
		def call(*args, **kw):
			if args:
				kw = dict(kw, **{first: args[0]})
			calls.append((name, kw))
			return {'file': kw.get('path'), 'resolution': 30.0, 'native_resolution': 10.0, 'rows': [],
			        'operation': 'op', 'name': name}
		call.__signature__ = inspect.signature(getattr(services, name))
		monkeypatch.setattr(services, name, call)

	for name in ('time_series', 'compare_series', 'trend_table', 'download_trend', 'trend_map', 'download_image',
	             'map_layer', 'download_rgb', 'rgb_map', 'download_comparison', 'compare_map', 'area_by_class',
	             'region_stats', 'timelapse', 'export_image', 'time_series_to_drive', 'burn_severity'):
		tool(name)
	tool('transect', 'line')
	return calls


class _Combo:
	"""A QComboBox of (label, value), with its text when it is editable and empty."""

	def __init__(self, items, value=None, text=''):
		self.items, self.index, self.enabled, self.tip, self.text = list(items), 0, True, '', text
		if value is not None:
			self.index = [v for _, v in self.items].index(value)

	def currentData(self):
		return self.items[self.index][1] if self.items else None

	def currentText(self):
		return self.items[self.index][0] if self.items else self.text

	def currentIndex(self):
		return self.index

	def setCurrentIndex(self, i):
		self.index = i

	def count(self):
		return len(self.items)

	def itemData(self, i):
		return self.items[i][1]

	def isEnabled(self):
		return self.enabled

	def toolTip(self):
		return self.tip


class _Check:
	def __init__(self, on=False):
		self.on, self.enabled = on, True

	def isChecked(self):
		return self.on

	def setChecked(self, on):
		self.on = on

	def isEnabled(self):
		return self.enabled


class _Date:
	"""A QDateEdit with the day DAY (its date() is itself, and toString the day)."""

	def __init__(self, day):
		self.day = day

	def date(self):
		return self

	def toString(self, fmt):
		return self.day


class _Checkable(_Combo):
	"""A QgsCheckableComboBox of (label, value): the values checked."""

	def __init__(self, items):
		super().__init__(items)
		self.checked = set()

	def setItemCheckState(self, i, state):
		(self.checked.add if state == 'checked' else self.checked.discard)(self.items[i][1])


class _Text:
	def __init__(self, text=''):
		self.value, self.enabled = text, True

	def text(self):
		return self.value

	def setText(self, text):
		self.value = text

	def isEnabled(self):
		return self.enabled


class _Spin:
	def __init__(self, value=0.0):
		self.number = value

	def value(self):
		return self.number


def _row(variable, sensor):
	return next(v for v in services.list_variables(lang='en') if v['variable'] == variable and v['sensor'] == sensor)


def _panel(plugin, monkeypatch, tmp_path):
	"""The panel (dock.MonitorEODock, without building it) with fakes of its widgets: the NDVI of Sentinel-2 from
	2021 to 2023 over REGION, every pixel filter, the options of each group at their defaults; the tasks run at once,
	without their done (which opens windows)."""
	d = plugin.dock
	monkeypatch.setattr(d.tempfile, 'mkdtemp', lambda prefix='': str(tmp_path))
	p = d.MonitorEODock.__new__(d.MonitorEODock)
	p.variable = _Combo([('NDVI · Sentinel-2', _row('NDVI', 'Sentinel-2'))])
	p.region = lambda: REGION
	p.line_points = lambda: LINE
	p.where, p.landcover_box = [], _Check(False)
	p.start, p.end = _Date('2021-01-01'), _Date('2023-12-31')
	p.season_on, p.season_start, p.season_end = _Check(False), _Text('06-01'), _Text('09-30')
	p.filters = {k: _Check(True) for k in sensors.FILTERS}
	p.cloud_score, p.set_filters, p.chosen_filters = _Check(True), set(), None
	p.compare_on, p.other_start, p.other_end = _Check(False), _Date('2024-01-01'), _Date('2024-12-31')
	p.step, p.ts_metric, p.stat = _Combo(d.STEPS, 'monthly'), _Combo(d.METRICS, 'mean'), _Combo(d.STATS, 'mean')
	p.doy, p.doy_interannual = _Check(False), _Combo(d.DOY_INTERANNUAL)
	p.doy_other = _Combo([('None', None), ('NDSI (Sentinel-2)', {'variable': 'NDSI', 'sensor': 'Sentinel-2'})])
	p.trend_step, p.trend_part = _Combo(d.TREND_STEPS, 'annual'), _Combo([('the year', 0)])
	p.trend_metric, p.trend_alpha = _Combo(d.METRICS, 'mean'), _Check(True)
	p.map_metric, p.temporal = _Combo(d.METRICS, 'median'), _Combo(d.TEMPORAL, 'period')
	p.interannual, p.map_kind = _Combo(d.METRICS, 'mean'), _Combo(d.MAP_KINDS, 'index')
	p.area_kind, p.area_breaks = _Combo(d.AREA_KINDS, 'landcover'), _Text('0.2, 0.4')
	p.area_map, p.area_change = _Combo([('CORINE Land Cover · 100 m · Europe', 'CORINE')]), _Check(False)
	p.area_year, p.area_other_year = _Combo([('2018', 2018), ('2012', 2012)]), _Combo([('2018', 2018)])
	p.zone_variable, p.zone_breaks = _Combo([('ELEVATION · Copernicus', _row('ELEVATION', 'Copernicus'))]), \
		_Text('1500, 2000')
	p.anim_step, p.anim_metric, p.anim_fps = _Combo(d.ANIMATION_STEPS, 'annual'), _Combo(d.METRICS, 'median'), \
		_Spin(2.0)
	p.resolution, p.folder = _Spin(0.0), _Text('MonitorEO')
	p.fire_index, p.fire_sensor = _Combo(d.FIRE_INDICES, 'dNBR'), _Combo(d.FIRE_SENSORS + d.FIRE_MODIS, 'Sentinel-2')
	p.fire_dates = {k: _Date(v) for k, v in d.FIRE_DATES.items()}
	p.fire_perimeter, p.fire_burned_min, p.fire_min_ha = _Check(True), _Text('0,27'), _Spin(2.0)
	p.messages, p.tasks = [], []
	p.message = lambda text, lvl='Info', duration=6: p.messages.append((lvl, text))
	p.run_task = lambda description, work, done: p.tasks.append(work())
	return p


def _given(args):
	"""ARGS without its outputs (its files) and those left empty (None: the defaults of the services)."""
	return {k: v for k, v in args.items() if k not in OUTPUTS and v is not None}


def _same_as_run(plugin, panel, fake, key):
	"""The parameters of the analysis KEY of PANEL: those of its builder, checked to be what its button sends to
	monitoreo.services, and those the panel takes back without reports."""
	analysis, args = panel.call_of(key, **({'folder': plugin.dock.tempfile.mkdtemp()} if key == 'burn' else {}))
	fake.clear()
	getattr(panel, RUNS[key])()
	assert panel.messages == [], panel.messages
	sent = (fake[-1][0], _given(fake[-1][1]))
	assert sent == (analysis, _given(args)), (key, sent, (analysis, args))
	assert parameters.make(*sent) == parameters.make(analysis, args)
	saved = parameters.make(analysis, args)
	checked = parameters.check(saved)
	assert checked['not_applied'] == [], (key, checked['not_applied'])
	group, fields, reports = plugin.dock.panel_fields(analysis, checked['parameters'])
	assert group == key and reports == [], (key, reports)
	return analysis, args, fields


def test_every_analysis_has_its_group_its_builder_and_its_button(plugin):
	dock = plugin.dock
	assert set(dock.GROUPS) == set(parameters.ANALYSES)
	assert set(dock.GROUPS.values()) == set(dock.PANEL) == set(RUNS)
	source = _read('dock.py')
	tree = ast.parse(source)
	methods = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
	for key, (builder, what, button) in dock.PANEL.items():
		assert builder in methods, builder
		run = ast.get_source_segment(source, methods[RUNS[key]])
		assert f"self.call_of('{key}'" in run, f'{RUNS[key]} does not build its arguments with {builder}'
		assert f"QPushButton('{button}')" in source, button
	for name in dock.FIELDS:  # each field of the parameters has its list or its function to set it
		assert name in dock.COMBOS or f'put_{name}' in methods, name
	assert "self.with_parameters(b, 'series')" in source and "self.parameters_button('export_map', 'export_series')" \
		in source and 'row.addWidget(self.apply_button())' in source


def test_the_time_series_and_its_comparison(plugin, monkeypatch, tmp_path, fake):
	panel = _panel(plugin, monkeypatch, tmp_path)
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'series')
	assert analysis == 'time_series' and args['region'] == REGION and args['doy'] is False
	assert {k: args[k] for k in ('variable', 'sensor', 'start', 'end', 'step', 'metric', 'stat')} == \
		{'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2021-01-01', 'end': '2023-12-31', 'step': 'monthly',
		 'metric': 'mean', 'stat': 'mean'}
	assert fields['region']['value'] == ('extent', REGION['bbox']) and fields['compare']['value'] is None
	assert fields['season']['value'] is None and fields['where']['value'] == {'conditions': [], 'landcover': None}
	assert fields['quality']['value']['filters'] == dict({f: True for f in sensors.FILTERS}, cloud_score=True)
	assert (fields['step']['value'], fields['ts_metric']['value'], fields['doy_other']['value']) == \
		('monthly', 'mean', None)
	assert fields['variable']['value']['collection'] == 'COPERNICUS/S2_SR_HARMONIZED'
	saved = parameters.make(analysis, args)
	assert saved['analysis'] == 'time_series' and 'csv' not in saved['parameters']

	# the seasonal profile with a variable on the right axis: each axis with the filters chosen, as 'auto'
	panel.doy.setChecked(True)
	panel.doy_interannual.setCurrentIndex(2)  # the median
	panel.doy_other.setCurrentIndex(1)
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'series')
	assert (args['doy'], args['interannual'], args['other_variable'], args['other_sensor']) == \
		(True, 'median', 'NDSI', 'Sentinel-2')
	assert args['quality']['snow'] == 'auto' and fields['quality']['value']['filters']['snow'] == 'auto'
	assert fields['doy_other']['value'] == {'variable': 'NDSI', 'sensor': 'Sentinel-2'}
	panel.doy_other.setCurrentIndex(0)
	panel.doy.setChecked(False)

	# Compare with: the comparison of the periods, refused with the daily step (no service called)
	panel.compare_on.setChecked(True)
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'series')
	assert analysis == 'compare_series' and (args['other_start'], args['other_end']) == ('2024-01-01', '2024-12-31')
	assert fields['compare']['value'] == ('2024-01-01', '2024-12-31')
	panel.step.setCurrentIndex(3)  # daily
	fake.clear()
	panel.run_series()
	assert fake == [] and panel.messages[-1] == ('Warning', 'To compare periods, choose the step Monthly, 16 days or '
	                                                        'Annual')
	assert panel.call_of('series') is None


def test_the_trends_the_map_and_the_exports(plugin, monkeypatch, tmp_path, fake):
	panel = _panel(plugin, monkeypatch, tmp_path)
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'trend_table')
	assert analysis == 'trend_table' and (args['step'], args['metric'], args['stat']) == ('annual', 'mean', 'mean')
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'trend_map')
	assert analysis == 'download_trend' and args['alpha'] == plugin.dock.ALPHA and args['part'] is None
	assert args['max_pixels'] == plugin.dock.MAP_PIXELS and fields['trend_alpha']['value'] is True
	assert 'part' not in parameters.make(analysis, args)['parameters']  # annual: no part, as the area by class
	panel.trend_step.setCurrentIndex(1)  # months: that chosen
	panel.trend_part = _Combo([('July', 7)])
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'trend_map')
	assert (args['step'], args['part']) == ('monthly', 7) and fields['trend_part']['value'] == 7
	panel.trend_step.setCurrentIndex(0)
	panel.trend_part = _Combo([('the year', 0)])
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'map')
	assert analysis == 'download_image' and (args['metric'], args['temporal'], args['interannual']) == \
		('median', 'period', 'mean')
	assert fields['map_kind']['value'] == 'index'
	panel.map_kind.setCurrentIndex(1)  # the true colour alone
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'map')
	assert analysis == 'download_rgb' and fields['map_kind']['value'] == 'rgb'
	panel.map_kind.setCurrentIndex(2)  # both: the parameters of the map (its true colour has the same)
	assert panel.call_of('map')[0] == 'download_image'
	panel.compare_on.setChecked(True)  # the difference of the periods
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'map')
	assert analysis == 'download_comparison' and args['other_start'] == '2024-01-01'
	panel.compare_on.setChecked(False)
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'export_map')
	assert analysis == 'export_image' and args['resolution'] is None and 'folder' not in args
	assert fake[-1][1]['folder'] == 'MonitorEO'
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'export_series')
	assert analysis == 'time_series_to_drive' and args['step'] == 'monthly'


def test_the_areas_the_gradients_and_the_animation(plugin, monkeypatch, tmp_path, fake):
	panel = _panel(plugin, monkeypatch, tmp_path)
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'areas')
	assert args == {'region': REGION, 'landcover': 'CORINE', 'year': 2018}
	assert fields['area_kind']['value'] == 'landcover' and fields['where']['value']['conditions'] == []
	panel.area_change.setChecked(True)
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'areas')
	assert args['other_year'] == 2018 and fields['area_map']['value']['other_year'] == 2018
	panel.landcover_box.setChecked(True)  # refused, as services
	assert panel.call_of('areas') is None and 'uncheck them' in panel.messages.pop()[1]
	panel.landcover_box.setChecked(False)
	panel.area_kind.setCurrentIndex(1)  # breaks
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'areas')
	assert args['breaks'] == [0.2, 0.4] and args['metric'] == 'median' and fields['area_breaks']['value'] == '0.2, 0.4'
	assert parameters.make(analysis, args)['parameters']['breaks'] == [0.2, 0.4]  # numbers, as the app and the MCP
	assert plugin.dock.panel_fields(analysis, dict(args, breaks='0.2; 0.4'))[1]['area_breaks']['value'] == '0.2; 0.4'
	panel.area_breaks.setText('0.4, abc')  # refused, as services
	assert panel.call_of('areas') is None and 'breaks are numbers' in panel.messages.pop()[1]
	panel.area_breaks.setText('0.2, 0.4')
	panel.area_kind.setCurrentIndex(2)  # trend
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'areas')
	assert args['trend'] is True and 'part' not in parameters.make(analysis, args)['parameters']
	panel.area_kind.setCurrentIndex(3)  # the classes of a categorical layer
	assert panel.call_of('areas') is None and 'ECOREGION or BIOME' in panel.messages.pop()[1]
	panel.variable = _Combo([('BIOME · RESOLVE', _row('BIOME', 'RESOLVE'))])
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'areas')
	assert args['variable'] == 'BIOME' and fields['area_kind']['value'] == 'classes'
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'zones')
	assert args['stats'] == ['mode']  # class codes: the majority class of each band
	panel.variable = _Combo([('NDVI · Sentinel-2', _row('NDVI', 'Sentinel-2'))])
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'zones')
	assert args['zones'] == {'variable': 'ELEVATION', 'sensor': 'Copernicus', 'breaks': [1500.0, 2000.0]}  # numbers
	assert args['stats'] == plugin.dock.ZONE_STATS and fields['zones']['value'] == args['zones']
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'transect')
	assert args['line'] == LINE and 'region' not in args and fields['line']['value'] == LINE
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'animation')
	assert (args['step'], args['metric'], args['fps']) == ('annual', 'median', 2.0) and fields['anim_fps']['value'] == 2


def test_the_burn_severity(plugin, monkeypatch, tmp_path, fake):
	panel = _panel(plugin, monkeypatch, tmp_path)
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'burn')
	assert analysis == 'burn_severity' and args['perimeter'] == str(tmp_path / 'burn_severity_perimeter.gpkg')
	assert (args['burned_min'], args['min_ha'], args['sensor']) == (0.27, 2.0, 'Sentinel-2')
	assert fake[-1][1]['path'] == str(tmp_path / 'burn_severity.tif')
	assert parameters.make(analysis, args)['parameters']['perimeter'] == 'burn_severity_perimeter.gpkg'
	assert panel.burn_call()[1]['perimeter'] == 'burn_severity_perimeter.gpkg'  # copied or saved: no folder
	assert fields['fire_before']['value'] == ('2023-05-15', '2023-08-14')
	assert fields['fire_perimeter']['value'] == {'on': True, 'burned_min': 0.27, 'min_ha': 2.0}
	assert fields['quality']['value']['own'] is True and 'season' not in fields
	panel.fire_index.setCurrentIndex(2)  # the RdNBR of MODIS Aqua
	panel.fire_sensor.setCurrentIndex(3)
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'burn')
	assert (args['sensor'], args['collection'], args['index']) == ('Modis', 'MODIS/061/MYD09GA', 'RdNBR')
	assert fields['fire_sensor']['value'] == 'MODIS/061/MYD09GA' and fields['fire_index']['value'] == 'RdNBR'
	panel.fire_burned_min.value = 'abc'  # refused, as before
	assert panel.call_of('burn') is None and panel.messages.pop()[1].startswith('Burned from: write a number')


def test_the_data_of_earth_engine_by_their_id(plugin, monkeypatch, tmp_path, fake):
	panel = _panel(plugin, monkeypatch, tmp_path)
	panel.variable = _Combo([('Earth Engine data (by its ID)', {'custom': True})])
	panel.asset_id, panel.asset_info, panel.saved_bands = _Text('IDAHO_EPSCOR/TERRACLIMATE'), None, []
	panel.band_reducer, panel.asset_bands = _Combo(plugin.dock.REDUCERS, ''), _Combo([])
	panel.asset_band, panel.asset_use = _Combo([], text='pr'), _Combo(plugin.dock.USES, 'collection')
	panel.band_scale, panel.band_offset, panel.asset_unit = _Text('0.1'), _Text(''), _Text('mm')
	analysis, args, fields = _same_as_run(plugin, panel, fake, 'series')
	assert {k: args.get(k) for k in ('collection', 'band', 'band_scale', 'unit', 'variable', 'quality')} == \
		{'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr', 'band_scale': 0.1, 'unit': 'mm', 'variable': None,
		 'quality': None}
	value = fields['variable']['value']
	assert value == {'custom': True, 'use': 'collection', 'asset': 'IDAHO_EPSCOR/TERRACLIMATE', 'bands': ['pr'],
	                 'band_reducer': '', 'band_scale': 0.1, 'band_offset': None, 'unit': 'mm'}
	assert 'quality' not in fields  # their own mask: the filters of the panel are left as they are


def test_the_regions_of_the_panel(plugin):
	kind = plugin.dock.region_kind
	fc = {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': {'name': 'park'},
	                                                 'geometry': {'type': 'Point', 'coordinates': [0, 0]}}]}
	assert kind({'geojson': fc}) == ('layer', (fc, None))
	assert kind({'geojson': json.dumps(fc['features'][0]['geometry']), 'name_field': 'NAME'})[0] == 'layer'
	assert kind({'bbox': [1, 2, 3, 4]}) == ('extent', [1.0, 2.0, 3.0, 4.0])
	assert kind({'wdpa_id': 555588816}) == kind({'wdpa_id': [555588816]}) == ('wdpa', 555588816)
	assert kind({'admin2': 141938}) == ('admin', (2, 141938)) and kind({'country': 'esp'}) == ('country', 'ESP')
	assert kind({'ecoregion_at': [-3.3, 37.1]}) == ('ecoregion', [-3.3, 37.1])
	assert kind({'island_at': [-16.6, 28.3]}) == ('island', [-16.6, 28.3])
	assert kind({'biome_at': [-3.3, 37.1], 'within': {'bbox': [-4, 36, -3, 38]}}) == \
		('biome', {'at': [-3.3, 37.1], 'within': [-4, 36, -3, 38]})
	for region, words in (({'wdpa_id': [1, 2]}, 'one protected area'), ({'ecoregion_id': 793}, 'no region ecoregion_id'),
	                      ({'point': [0, 0], 'buffer': 100}, 'no region point'), ({'biome_id': 12}, 'no region biome'),
	                      ({'country': 'ESP', 'within': {'bbox': [0, 0, 1, 1]}}, 'within only for the biome'),
	                      ({'geojson': 'nonsense'}, 'not GeoJSON'), ({}, 'not a region'),
	                      ({'wdpa_id': 1, 'country': 'ESP'}, 'not a region')):
		got, reason = kind(region)
		assert got is None and words in reason, (region, reason)


def test_what_the_panel_cannot_apply_is_reported_with_the_reason(plugin):
	dock = plugin.dock
	source = {'monitoreo': '0.0.1', 'analysis': 'time_series', 'parameters': {
		'region': {'wdpa_id': [555588816, 389011]}, 'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2020-01-01',
		'end': '2020-12-31', 'step': 'weekly', 'metric': 'mean', 'stat': 'p95', 'scale': 30, 'ylim': [0, 1],
		'quality': {'clouds': True, 'scene_clouds': 20, 'cloud_score': 0.5, 'shadows': True},
		'where': [{'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 1500},
		          {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'min': 0.2, 'period': ['2019-01-01', '2019-12-31']},
		          {'variable': 'SLOPE', 'sensor': 'Copernicus', 'max': 20},
		          {'landcover': 'CORINE', 'year': 2018, 'exclude': ['water']},
		          {'landcover': 'WorldCover', 'year': 2021, 'exclude': ['built']}],
		'csv': 'out.csv', 'what': 1}}
	checked = parameters.check(source)
	assert {p['name'] for p in checked['not_applied']} == {'csv', 'what'} and 'note' in checked
	key, fields, reports = dock.panel_fields(checked['analysis'], checked['parameters'])
	why = {r['name']: r['reason'] for r in reports}
	assert key == 'series' and 'region' not in fields and 'one protected area' in why['region']
	assert 'not in its list in the panel' in why['step'] and 'step' not in fields  # its field keeps its value
	assert 'stat' not in why and fields['stat']['value'] == 'p95'
	assert why['scale'] == 'the panel has no option for it' and why['ylim'] == 'the panel has no option for it'
	assert 'Cloud Score+ 0.6' in why['quality.cloud_score'] and 'no such pixel filter' in why['quality.shadows']
	assert 'quality.scene_clouds' in why and fields['quality']['value']['filters']['cloud_score'] is True
	assert 'two conditions' in why['where[2]'] and 'one land cover mask' in why['where[4]']
	assert why['where[1].period'] == 'the panel takes the period of the analysis, 2020-01-01 to 2020-12-31'
	where = fields['where']['value']
	assert [i for i, _ in where['conditions']] == [0, 1] and where['landcover']['landcover'] == 'CORINE'

	# the options of other analyses: the significance of a trend map, the stats of the bands, the figure, the burn
	_, fields, reports = dock.panel_fields('download_trend', {'region': {'bbox': [0, 0, 1, 1]}, 'variable': 'NDVI',
	                                                          'sensor': 'Landsat', 'alpha': 0.01, 'max_pixels': 1e9})
	why = {r['name']: r['reason'] for r in reports}
	assert 'p < 0.05' in why['alpha'] and 'at most 4,000,000 pixels' in why['max_pixels']
	_, fields, reports = dock.panel_fields('region_stats', {'region': {'country': 'ESP'}, 'variable': 'NDVI',
	                                                        'sensor': 'Landsat', 'stats': ['mean']})
	assert [r['name'] for r in reports] == ['zones'] and fields['stats']['value'] == ['mean']
	_, fields, reports = dock.panel_fields('map_figure', {'region': {'country': 'ESP'}, 'variable': 'NDVI',
	                                                      'sensor': 'Landsat', 'dpi': 600, 'width': 7.0})
	assert [r['name'] for r in reports] == ['analysis', 'dpi'] and fields['map_kind']['value'] == 'index'
	_, fields, reports = dock.panel_fields('burn_severity', {'region': {'country': 'ESP'}, 'sensor': 'Modis',
	                                                         'season': ['06-01', '09-30'], 'metric': 'mean'})
	why = {r['name']: r['reason'] for r in reports}
	assert why['sensor'] == 'MODIS only with the index RdNBR, not dNBR' and set(why) == {'sensor', 'season', 'metric'}
	_, fields, reports = dock.panel_fields('burn_severity', {'region': {'country': 'ESP'}, 'sensor': 'Modis',
	                                                         'index': 'RdNBR', 'collection': 'MODIS/061/MOD13Q1'})
	assert 'MODIS Terra or Aqua' in reports[0]['reason'] and 'fire_sensor' not in fields
	_, fields, reports = dock.panel_fields('time_series', {'variable': 'RBR', 'sensor': 'Landsat'})
	assert 'only in the burn severity' in reports[0]['reason'] and 'variable' not in fields
	_, fields, reports = dock.panel_fields('download_rgb', {'collection': 'X/Y', 'band': ['a', 'b'],
	                                                        'band_reducer': 'max', 'sensor': 'Landsat'})
	assert {r['name'] for r in reports} == {'band_reducer', 'sensor'} and fields['map_kind']['value'] == 'rgb'
	assert fields['variable']['value']['bands'] == ['a', 'b'] and fields['variable']['value']['band_reducer'] == ''
	assert parameters.text(reports).startswith('band_reducer ("max"): the panel combines bands with sum or mean')


def test_the_defaults_of_the_parameters_not_given(plugin):
	"""Those not given are the defaults of their function of monitoreo.services (not reported), so that the panel
	computes what the parameters say: no season, no conditions, every pixel filter, no Compare with."""
	_, fields, reports = plugin.dock.panel_fields('download_image', {'region': {'country': 'ESP'}, 'variable': 'NDVI',
	                                                                  'sensor': 'Landsat'})
	assert reports == [] and fields['map_metric'] == {'value': 'median', 'given': False, 'name': 'metric'}
	assert fields['season']['value'] is None and fields['compare']['value'] is None
	assert fields['quality'] == {'value': {'filters': dict({f: True for f in sensors.FILTERS}, cloud_score=True),
	                                       'own': False}, 'given': False, 'name': 'quality'}
	_, fields, reports = plugin.dock.panel_fields('download_image', {'variable': 'ELEVATION', 'sensor': 'Copernicus'})
	assert 'quality' not in fields and 'period' not in fields  # a fixed layer
	_, fields, _ = plugin.dock.panel_fields('download_image', {
		'variable': 'ELEVATION', 'sensor': 'Copernicus', 'where': [{'variable': 'NDVI', 'sensor': 'Landsat', 'min': 0.3,
		                                                            'period': ['2020-01-01', '2020-12-31']}]})
	assert fields['period']['value'] == ('2020-01-01', '2020-12-31')  # that of its condition with dates
	_, fields, reports = plugin.dock.panel_fields('area_by_class', {'region': {'country': 'ESP'}, 'variable': 'NDVI',
	                                                                 'sensor': 'Landsat', 'trend': True})
	assert reports == [] and fields['trend_metric']['value'] == 'mean' and fields['area_kind']['value'] == 'trend'


def test_names_in_any_case_as_check_the_services_and_the_app(plugin, monkeypatch, tmp_path):
	"""The names of the variables, sensors, burn indices, land cover maps and land covers in any case and without
	spaces (catalog.name_key), as parameters.check, the services and the Earth Engine app take them: the parameters
	that Python, R, the command line or the MCP server write keep them as their user gave them."""
	dock = plugin.dock
	aqua = [v for v in services.list_variables(lang='en') if v['variable'] == 'NDVI' and v['sensor'] == 'Modis'][-1]
	for analysis, given, want in (
			('time_series', {'variable': 'ndvi', 'sensor': 'sentinel-2'}, ('NDVI', 'Sentinel-2', None)),
			('time_series', {'variable': 'NDVI', 'sensor': 'MODIS'}, ('NDVI', 'Modis', None)),
			('time_series', {'variable': 'ndvi', 'sensor': 'modis', 'collection': aqua['collection']},
			 ('NDVI', 'Modis', aqua['collection'])),
			('download_image', {'variable': 'elevation', 'sensor': 'copernicus'}, ('ELEVATION', 'Copernicus', None)),
			('download_image', {'variable': 'twi', 'sensor': 'merit hydro'}, ('TWI', 'MERIT Hydro', None))):
		params = dict(given, region={'country': 'ESP'})
		assert parameters.check({'analysis': analysis, 'parameters': params})['not_applied'] == []
		_, fields, reports = dock.panel_fields(analysis, params)
		row = fields['variable']['value']
		assert reports == [] and (row['variable'], row['sensor']) == want[:2], (given, reports)
		assert want[2] in (None, row['collection'])

	# the burn index and its sensor; MODIS without a collection: Terra, as services.burn_severity
	burn = {'region': {'country': 'ESP'}, 'start': '2023-05-15', 'end': '2023-08-14', 'other_start': '2023-09-15',
	        'other_end': '2023-11-30'}
	for given, want in (({'index': 'rbr', 'sensor': 'landsat'}, ('RBR', 'Landsat')),
	                    ({'index': 'DNBR', 'sensor': 'SENTINEL-2'}, ('dNBR', 'Sentinel-2')),
	                    ({'index': 'RdNBR', 'sensor': 'Modis'}, ('RdNBR', 'MODIS/061/MOD09GA')),
	                    ({'index': 'rdnbr', 'sensor': 'MODIS'}, ('RdNBR', 'MODIS/061/MOD09GA')),
	                    ({'index': 'RdNBR', 'sensor': 'modis', 'collection': 'MODIS/061/MYD09GA'},
	                     ('RdNBR', 'MODIS/061/MYD09GA'))):
		params = dict(burn, **given)
		assert parameters.check({'analysis': 'burn_severity', 'parameters': params})['not_applied'] == []
		_, fields, reports = dock.panel_fields('burn_severity', params)
		assert reports == [] and (fields['fire_index']['value'], fields['fire_sensor']['value']) == want, \
			(given, reports)

	# the right axis of a profile, the bands of a fixed layer and the land cover map of the areas
	panel = _panel(plugin, monkeypatch, tmp_path)
	assert panel.put_doy_other({'variable': 'ndsi', 'sensor': 'SENTINEL-2'}, True, 'other_variable') == []
	assert panel.doy_other.currentIndex() == 1
	panel.zone_variable = _Combo([(f"{v['variable']} · {v['sensor']}", v) for v in (_row('SLOPE', 'Copernicus'),
	                                                                                _row('ELEVATION', 'Copernicus'))])
	assert panel.put_zones({'variable': 'elevation', 'sensor': 'copernicus', 'breaks': [1000, 2000]}, True,
	                       'zones') == []
	assert panel.zone_variable.currentIndex() == 1 and panel.zone_breaks.text() == '1000, 2000'
	panel.area_map = _Combo([('ESA WorldCover', 'WorldCover'), ('CORINE Land Cover', 'CORINE')])
	assert panel.put_area_map({'landcover': 'corine land cover', 'year': 2018}, True, 'landcover') == []
	assert panel.area_map.currentData() == 'CORINE'

	# the conditions of «Only the pixels where» and the land cover mask
	monkeypatch.setattr(dock, 'Qt', types.SimpleNamespace(CheckState=types.SimpleNamespace(Checked='checked',
	                                                                                       Unchecked='unchecked')))
	row = {'on': _Check(False), 'keep': _Combo(dock.CLASS_CONDITIONS, 'classes'), 'codes': _Text(), 'min': _Text(),
	       'max': _Text(), 'variable': _Combo([(f"{v['variable']} · {v['sensor']}", v)
	                                           for v in (_row('SLOPE', 'Copernicus'), _row('ELEVATION', 'Copernicus'))])}
	panel.where, panel.where_changed, panel.fill_landcover_years = [row], lambda: None, lambda year=None: None
	panel.landcover_map = _Combo([('ESA WorldCover', 'WorldCover'), ('CORINE Land Cover', 'CORINE')])
	panel.landcover_year = _Combo([('2018', 2018)])
	panel.landcover_classes = _Checkable([(k, k) for k in ('water', 'trees', 'built')])
	rows, cover, reports, _ = dock.where_fields([{'variable': 'elevation', 'sensor': 'copernicus', 'min': 1500},
	                                             {'landcover': 'corine', 'year': 2018, 'exclude': ['Water', ' BUILT ']}])
	assert reports == [] and panel.put_where({'conditions': rows, 'landcover': cover}, True, 'where') == []
	assert row['variable'].currentIndex() == 1 and row['on'].isChecked() and row['min'].text() == '1500'
	assert panel.landcover_box.isChecked() and panel.landcover_map.currentData() == 'CORINE'
	assert panel.landcover_classes.checked == {'water', 'built'}
	reports = panel.put_where({'conditions': [], 'landcover': dict(cover, exclude=['Water', 'forest'])}, True, 'where')
	assert [(r['name'], r['value']) for r in reports] == [('where.exclude', 'forest')]
	assert panel.landcover_classes.checked == {'water'} and not row['on'].isChecked()


def test_cloud_score_also_while_the_variable_greys_it_out(plugin, monkeypatch, tmp_path):
	"""Cloud Score+ or the SCL of the parameters is set even while the variable of the panel greys it out (a variable
	with fixed filters, SCF): the burn severity and the right axis of a profile compute other variables with it."""
	panel = _panel(plugin, monkeypatch, tmp_path)
	panel.variable = _Combo([('SCF · Landsat', _row('SCF', 'Landsat'))])
	panel.cloud_score.enabled = False  # as variable_changed leaves it: greyed out, and checked
	panel.set_filters, panel.chosen_filters = {'clouds', 'water'}, {k: True for k in sensors.FILTERS}
	_, fields, reports = plugin.dock.panel_fields('burn_severity', {'region': REGION,
	                                                                'quality': dict(sensors.QUALITY, cloud_score=None)})
	quality = fields['quality']['value']
	assert reports == [] and quality['filters']['cloud_score'] is False
	assert panel.put_quality(quality, True, 'quality') == []
	assert not panel.cloud_score.isChecked() and panel.quality_args(own=True)['cloud_score'] is None
	assert panel.quality_args(own=True, auto=True)['cloud_score'] is None
	panel.put_quality(dict(quality, filters=dict(quality['filters'], cloud_score=True)), True, 'quality')
	assert panel.quality_args(own=True)['cloud_score'] == sensors.QUALITY['cloud_score']


def test_the_window_of_a_result_shows_and_saves_its_parameters(plugin, tmp_path):
	results = plugin.results
	p = parameters.make('time_series', {'region': {'geojson': {'type': 'FeatureCollection', 'features': [
		{'type': 'Feature', 'properties': {'name': n}, 'geometry': {'type': 'Point', 'coordinates': [0, 0]}}
		for n in ('park', 'buffer')]}}, 'variable': 'NDVI', 'sensor': 'Landsat', 'csv': 'x.csv'})
	csv, readme = tmp_path / 'series.csv', tmp_path / 'series.README.txt'
	csv.write_text('date,value\n')
	readme.write_text('README')
	res = {'csv': str(csv), 'readme': str(readme), 'call': p}
	assert results.result_parameters(res) is p
	results.save_file(str(csv), str(tmp_path / 'copy.csv'), res)
	assert json.loads((tmp_path / 'copy.parameters.json').read_text()) == p
	assert (tmp_path / 'copy.README.txt').read_text() == 'README'
	results.save_file(str(readme), str(tmp_path / 'other.txt'), res)  # not a file of the result: nothing next to it
	assert not (tmp_path / 'other.parameters.json').exists()
	written = parameters.save('time_series', {'variable': 'NDVI'}, str(tmp_path / 'series.parameters.json'))
	assert results.result_parameters({'parameters': written})['parameters'] == {'variable': 'NDVI'}
	assert results.result_parameters({'parameters': str(tmp_path / 'none.json')}) is None
	assert results.value_text('region', p['parameters']['region']) == 'GeoJSON of 2 features (park, buffer)'
	assert results.value_text('where', ['x' * 300]).endswith('…')
	html = results.parameters_html(p)
	assert '<b>variable</b>: &quot;NDVI&quot;' in html or '<b>variable</b>: "NDVI"' in html
	assert 'Parameters of the analysis</b> time_series' in html and 'the command line, the MCP server' in html
	assert json.loads(results.parameters_text(p)) == p
	source = _read('results.py')
	assert source.count('parameter_buttons(self, row, res)') == 3  # the windows of a series, of the others, animation
	assert "QPushButton('Copy parameters')" in source and "QPushButton('Save parameters…')" in source


def test_the_help_explains_the_parameters(plugin):
	help_ = plugin.helptexts.HELP
	text = help_['parameters']
	for words in ('"analysis": "time_series"', 'Python, R, the command line, the MCP server and the Earth Engine app',
	              '<b>Copy parameters</b>', '<b>Save parameters…</b>', '<b>Paste parameters</b>',
	              '<b>Open parameters…</b>', '<b>not applied</b>', 'compute nothing', 'name.parameters.json',
	              'More in the manual'):
		assert words in text, words
	# a region of a layer: the layer chosen (or an earlier one of the parameters) if it gives the same polygons
	assert 'chooses the layer of <b>Region → Layer</b>' in text and 'if it gives the same polygons, or else comes ' \
		'back as a temporary layer' in text
	assert f'{plugin.helptexts.about.MANUAL}/QGIS-plugin#parameters-of-an-analysis' in text
	assert '<b>Copy parameters</b>' in help_['series_list']
	assert "InfoButton(HELP['parameters'])" in _read('dock.py')
