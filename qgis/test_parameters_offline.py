"""Test of the parameters of an analysis (monitoreo.parameters, issue #85) in the QGIS plugin without Earth Engine, with
the Python of QGIS (offscreen, seconds):

    PYTHONNOUSERSITE=1 PYTHONPATH=src <python of QGIS> qgis/test_parameters_offline.py

(macOS: /Applications/QGIS-final-4_0_3.app/Contents/MacOS/python, with QGIS_APP for another QGIS; earthengine-api
comes from the ext/ of the plugin, made by build_plugin.py, or from PYTHONPATH). It builds the real panel and, for
each analysis, sets its fields, copies its parameters (Parameters → Copy parameters: the clipboard), changes the
fields, pastes them (Apply parameters → Paste parameters) and checks that the fields give the same arguments to
monitoreo.services again, without computing anything: with the region of a layer, a protected area, an administrative
unit and a country, the data of Earth Engine by their ID, the burn severity from another theme and the profile along a
line (a temporary layer of it). Then the map extent and the points at its center, a region of GeoJSON (a temporary
layer, not added twice), Open parameters… of a file, what cannot be applied (a message that stays, with the reasons),
the names in any case (as the services take them) and the window of a result, with its parameters, its buttons and the
JSON next to its CSV. The services that compute
are faked, and fail the test if they are called while applying.
"""

import inspect
import json
import os
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
APP = os.environ.get('QGIS_APP', '/Applications/QGIS-final-4_0_3.app')
for proj in ('Contents/Resources/proj', 'Contents/Resources/qgis/proj'):
	if os.path.exists(os.path.join(APP, proj, 'proj.db')):
		os.environ.setdefault('PROJ_DATA', os.path.join(APP, proj))
		os.environ.setdefault('PROJ_LIB', os.path.join(APP, proj))
sys.path.insert(0, os.path.join(APP, 'Contents', 'Resources', 'python'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry,  # noqa: E402
                       QgsPointXY, QgsProject, QgsRectangle, QgsSettings, QgsVectorLayer)
from qgis.gui import QgsMapCanvas, QgsMessageBar  # noqa: E402
from qgis.PyQt.QtCore import QDate, Qt  # noqa: E402
from qgis.PyQt.QtWidgets import QApplication, QMainWindow, QPushButton, QTextBrowser, QToolButton  # noqa: E402

app = QgsApplication([], True)
QgsApplication.setPrefixPath(os.path.join(APP, 'Contents', 'MacOS'), True)
app.initQgis()
TMP = tempfile.mkdtemp(prefix='monitoreo_test_')


class Iface:
	def __init__(self):
		self.window = QMainWindow()
		self.canvas = QgsMapCanvas()
		self.canvas.resize(800, 600)
		self.bar = QgsMessageBar()

	def mainWindow(self):
		return self.window

	def mapCanvas(self):
		return self.canvas

	def messageBar(self):
		return self.bar

	def addDockWidget(self, area, dock):
		self.window.addDockWidget(area, dock)

	def removeDockWidget(self, dock):
		self.window.removeDockWidget(dock)

	def addToolBarIcon(self, action):
		pass

	def removeToolBarIcon(self, action):
		pass

	def addPluginToWebMenu(self, name, action):
		pass

	def removePluginWebMenu(self, name, action):
		pass


import monitoreo_qgis  # noqa: E402
from monitoreo_qgis import deps  # noqa: E402

deps.setup_path()
from monitoreo import parameters, services  # noqa: E402

computed = []  # the services that compute, called


def faked(name):
	"""The service NAME, which fails the test if it is called (with its signature, which monitoreo.parameters reads)."""
	def call(*args, **kw):
		computed.append(name)
		raise RuntimeError(f'{name} computed')
	call.__signature__ = inspect.signature(getattr(services, name))
	return call


services.init = lambda *args, **kw: 'project'
for name in parameters.ANALYSES + ('describe_asset', 'find_protected_areas', 'find_admin_units'):
	setattr(services, name, faked(name))
# the settings of the panel, restored at the end (its tasks store those of the fields: other tests read them)
STORED = {k: QgsSettings().value(k) for k in QgsSettings().allKeys() if k.startswith('MonitorEO/')}
for key in ('landcover_on', 'landcover_map', 'landcover_year', 'landcover_exclude', 'asset_bands'):
	QgsSettings().remove('MonitorEO/' + key)  # the defaults, whatever other tests stored

iface = Iface()
plugin = monitoreo_qgis.classFactory(iface)
plugin.initGui()
plugin.toggle(True)
dock = plugin.dock
messages = []
_message = dock.message
dock.message = lambda text, lvl='Info', duration=6: (messages.append((lvl, text, duration)),
                                                     _message(text, lvl, duration))


def wait(timeout=60):
	t0 = time.time()
	app.processEvents()
	while dock.tasks and time.time() - t0 < timeout:
		app.processEvents()
		time.sleep(0.05)
	assert not dock.tasks, 'tasks did not finish'


def pick(box, value=None, text=None):
	"""Choose in the list BOX the item of VALUE (or that whose text starts with TEXT)."""
	i = box.findText(text, Qt.MatchFlag.MatchStartsWith) if text else box.findData(value)
	assert i >= 0, (value, text)
	box.setCurrentIndex(i)


def day(edit, text):
	edit.setDate(QDate.fromString(text, 'yyyy-MM-dd'))


def roundtrip(key, change):
	"""Copy the parameters of the analysis KEY of the panel, CHANGE its fields and paste them: the fields give the same
	arguments again, without computing anything."""
	call = dock.call_of(key)
	assert call, messages[-1:]
	dock.copy_parameters(key)
	text = QApplication.clipboard().text()
	assert json.loads(text) == parameters.make(*call), text
	change()
	assert dock.call_of(key) != call, f'{key}: the change changed nothing'
	dock.paste_parameters()
	assert messages[-1][0] == 'Success' and messages[-1][1].startswith(f'Parameters of {call[0]} applied'), \
		messages[-1]
	again = dock.call_of(key)
	assert again == call, (key, again, call)
	assert not computed and not dock.tasks, computed
	print(f'{key} ({call[0]}): the same arguments after copy, change and paste')
	return call


wait()
dock.theme.setCurrentIndex(dock.theme.count() - 1)  # all the variables
assert dock.findChild(QToolButton, 'parameters_series') is not None
assert dock.apply_menu.actions()[0].text() == 'Paste parameters'

# a layer of two polygons named by their field name: the region of most of them
parks = QgsVectorLayer('Polygon?crs=EPSG:4326&field=name:string', 'parks', 'memory')
for name, (x, y) in (('park', (-3.40, 37.05)), ('buffer', (-3.30, 37.10))):
	f = QgsFeature(parks.fields())
	f.setGeometry(QgsGeometry.fromRect(QgsRectangle(x, y, x + 0.05, y + 0.04)))
	f['name'] = name
	parks.dataProvider().addFeatures([f])
QgsProject.instance().addMapLayer(parks)
pick(dock.region_kind, 'layer')
dock.layer.setLayer(parks)
dock.name_field.setField('name')
pick(dock.variable, text='NDVI · Landsat')
day(dock.start, '2018-01-01')
day(dock.end, '2022-12-31')
n_layers = len(QgsProject.instance().mapLayers())

# the time series: its options, the season, the filters, a condition and the land cover mask
pick(dock.step, '16-day')
pick(dock.ts_metric, 'median')
pick(dock.stat, 'p75')
dock.season_on.setChecked(True)
dock.season_start.setText('05-01')
dock.season_end.setText('09-30')
dock.filters['snow'].setChecked(False)
dock.cloud_score.setChecked(False)
dock.where[0]['on'].setChecked(True)
pick(dock.where[0]['variable'], text='ELEVATION · Copernicus')
dock.where[0]['min'].setText('1500')
dock.landcover_box.setChecked(True)
pick(dock.landcover_map, 'CORINE')
pick(dock.landcover_year, 2018)


def change_series():
	pick(dock.variable, text='NDSI · Sentinel-2')
	day(dock.start, '2020-01-01')
	dock.season_on.setChecked(False)
	for w in dock.filters.values():
		w.setChecked(True)
	dock.cloud_score.setChecked(True)
	dock.where[0]['on'].setChecked(False)
	dock.where[0]['min'].setText('')
	dock.landcover_box.setChecked(False)
	pick(dock.step, 'monthly')
	pick(dock.ts_metric, 'mean')
	pick(dock.stat, 'mean')
	pick(dock.region_kind, 'extent')
	dock.name_field.setField('')


call = roundtrip('series', change_series)
assert call[0] == 'time_series' and call[1]['where'][1]['landcover'] == 'CORINE' and call[1]['season'] == ['05-01',
                                                                                                             '09-30']
assert dock.layer.currentLayer() is parks and dock.name_field.currentField() == 'name'
assert len(QgsProject.instance().mapLayers()) == n_layers  # the layer chosen gives the region: none added
assert dock.region_kind.currentData() == 'layer' and dock.landcover_box.isChecked()

# Compare with, over a country
dock.where[0]['on'].setChecked(False)
dock.landcover_box.setChecked(False)
pick(dock.step, 'monthly')
pick(dock.region_kind, 'country')
dock.country.setText('PRT')
dock.compare_on.setChecked(True)
day(dock.other_start, '2023-01-01')
day(dock.other_end, '2023-12-31')


def change_comparison():
	dock.compare_on.setChecked(False)
	dock.country.setText('ESP')


call = roundtrip('series', change_comparison)
assert call[0] == 'compare_series' and call[1]['region'] == {'country': 'PRT'}
dock.compare_on.setChecked(False)

# the map (Both: the parameters of the map) over a protected area, added by its ID to a list that has not got it
pick(dock.region_kind, 'wdpa')
dock.wdpa.addItem('Sierra Nevada · National Park · ESP', 555588816)
dock.wdpa.setCurrentIndex(dock.wdpa.count() - 1)
pick(dock.map_metric, 'max')
pick(dock.temporal, 'annual')
pick(dock.interannual, 'median')
pick(dock.map_kind, 'both')
dock.map_colours.low.setValue(5)  # the Colour range: percentiles 5 and 95 and a maximum
dock.map_colours.high.setValue(95)
dock.map_colours.vmax.setText('0.8')


def change_map():
	dock.wdpa.clear()
	pick(dock.region_kind, 'country')
	pick(dock.map_metric, 'mean')
	pick(dock.temporal, 'period')
	dock.map_colours.put({})


call = roundtrip('map', change_map)
assert call[0] == 'download_image' and call[1]['region'] == {'wdpa_id': 555588816}
assert call[1]['percentiles'] == [5, 95] and call[1]['vmax'] == 0.8 and 'vmin' not in call[1]
dock.map_colours.put({})
assert 'WDPA 555588816' in dock.wdpa.currentText() and dock.map_kind.currentData() == 'both'
pick(dock.map_kind, 'rgb')
call = roundtrip('map', lambda: pick(dock.map_kind, 'index'))
assert call[0] == 'download_rgb' and dock.map_kind.currentData() == 'rgb'

# the trend map over an administrative unit, and the trend table
pick(dock.region_kind, 'admin')
dock.admin.addItem('Granada, Andalucía, Spain (GAUL 1234)', (2, 1234))
dock.admin.setCurrentIndex(dock.admin.count() - 1)
pick(dock.trend_step, 'monthly')
pick(dock.trend_part, 7)
pick(dock.trend_metric, 'max')
dock.trend_alpha.setChecked(False)


def change_trend():
	dock.admin.clear()
	pick(dock.trend_step, 'annual')
	dock.trend_alpha.setChecked(True)


call = roundtrip('trend_map', change_trend)
assert call[1]['region'] == {'admin2': 1234} and call[1]['part'] == 7 and call[1]['alpha'] is None
pick(dock.trend_step, 'annual')  # the whole year: no part, as the area by class (the app takes none)
assert dock.call_of('trend_map')[1]['part'] is None and 'part' not in parameters.make(*dock.call_of('trend_map'))[
	'parameters']
pick(dock.trend_step, 'monthly')
roundtrip('trend_table', lambda: pick(dock.trend_metric, 'mean'))

# the area by class of a land cover map and its changes, the bands, the animation and the exports
pick(dock.region_kind, 'layer')
pick(dock.area_kind, 'landcover')
pick(dock.area_map, 'CORINE')
dock.area_change.setChecked(True)
pick(dock.area_year, 2006)
pick(dock.area_other_year, 2018)


def change_areas():
	pick(dock.area_kind, 'breaks')
	pick(dock.area_map, 'WorldCover')


call = roundtrip('areas', change_areas)
assert (call[1]['landcover'], call[1]['year'], call[1]['other_year']) == ('CORINE', 2006, 2018)
pick(dock.area_kind, 'breaks')
dock.area_breaks.setText('0.2, 0.5')
call = roundtrip('areas', lambda: dock.area_breaks.setText('0.3'))
assert call[1]['breaks'] == [0.2, 0.5]  # numbers, as the app and the MCP server write them
dock.zone_breaks.setText('1000, 2000')
roundtrip('zones', lambda: dock.zone_breaks.setText('1500'))
pick(dock.anim_step, 'monthly')
dock.anim_fps.setValue(4)
dock.anim_same.setChecked(True)
dock.anim_colours.low.setValue(2.5)


def change_animation():
	dock.anim_fps.setValue(1)
	dock.anim_same.setChecked(False)
	dock.anim_colours.put({})


call = roundtrip('animation', change_animation)
assert call[1]['same_colours'] is True and call[1]['percentiles'] == [2.5, 99]
dock.anim_same.setChecked(False)
dock.anim_colours.put({})
dock.resolution.setValue(100)
call = roundtrip('export_map', lambda: dock.resolution.setValue(0))
assert call[1]['resolution'] == 100
roundtrip('export_series', lambda: pick(dock.ts_metric, 'max'))

# the profile along a line: back as a temporary layer of it once its layer is gone, and not added twice
lines = QgsVectorLayer('LineString?crs=EPSG:4326', 'lines', 'memory')
f = QgsFeature()
f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(-3.60, 37.15), QgsPointXY(-3.45, 37.10)]))
lines.dataProvider().addFeatures([f])
QgsProject.instance().addMapLayer(lines)
dock.line_layer.setLayer(lines)
call = roundtrip('transect', lambda: QgsProject.instance().removeMapLayer(lines.id()))
assert dock.line_layer.currentLayer().name() == 'Line of the parameters' and 'temporary layer' in messages[-1][1]
n = len(QgsProject.instance().mapLayers())
dock.apply_parameters(parameters.make(*call))
assert len(QgsProject.instance().mapLayers()) == n and dock.call_of('transect') == call

# the data of Earth Engine by their ID: two bands combined, without reading them
pick(dock.theme, 'earth_engine')
dock.asset_id.setText('IDAHO_EPSCOR/TERRACLIMATE')
pick(dock.asset_use, 'collection')
dock.band_offset.setText('')
pick(dock.band_reducer, 'sum')
dock.asset_band.setEditText('aet, def')
dock.band_scale.setText('0.1')
dock.asset_unit.setText('mm')
call = roundtrip('series', lambda: dock.theme.setCurrentIndex(dock.theme.count() - 1))
assert call[1]['collection'] == 'IDAHO_EPSCOR/TERRACLIMATE' and call[1]['band'] == ['aet', 'def']
assert call[1]['band_reducer'] == 'sum' and call[1]['unit'] == 'mm' and dock.theme.currentData() == 'earth_engine'
dock.theme.setCurrentIndex(dock.theme.count() - 1)
pick(dock.variable, text='NDVI · Landsat')

# the burn severity: its theme, chosen when it is not that of the panel
pick(dock.fire_index, 'RdNBR')
pick(dock.fire_sensor, 'MODIS/061/MYD09GA')
day(dock.fire_dates['before_start'], '2021-06-01')
dock.fire_perimeter.setChecked(True)
dock.fire_burned_min.setText('0.1')
dock.fire_min_ha.setValue(3)


def change_burn():
	pick(dock.theme, 'vegetation')
	pick(dock.fire_index, 'dNBR')
	dock.fire_perimeter.setChecked(False)


call = roundtrip('burn', change_burn)
assert (call[1]['index'], call[1]['sensor'], call[1]['collection']) == ('RdNBR', 'Modis', 'MODIS/061/MYD09GA')
assert call[1]['perimeter'] == 'burn_severity_rdnbr_perimeter.gpkg' and dock.fire_box.isVisibleTo(dock)
assert dock.theme_has('burn_severity')
dock.theme.setCurrentIndex(dock.theme.count() - 1)
pick(dock.variable, text='NDVI · Landsat')

# the map extent and the points at its center: the map zoomed to them
iface.canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
pick(dock.region_kind, 'extent')
iface.canvas.setExtent(QgsRectangle(-3.45, 37.02, -3.30, 37.12))
call = dock.call_of('map')
saved = parameters.make(*call)
iface.canvas.setExtent(QgsRectangle(0, 0, 1, 1))
pick(dock.region_kind, 'country')
reports = dock.apply_parameters(saved)
got = dock.region()['bbox']
assert dock.region_kind.currentData() == 'extent' and reports == [], reports
assert all(abs(a - b) < 1e-6 for a, b in zip(got, call[1]['region']['bbox'])), (got, call[1]['region'])
for region in ({'ecoregion_at': [-3.3, 37.1]}, {'island_at': [-16.6, 28.3]}, {'sea_at': [-2.5, 36.0]}):
	reports = dock.apply_parameters({'analysis': 'map_layer', 'parameters': dict(region=region, variable='NDVI',
	                                                                             sensor='Landsat')})
	kind = next(iter(region))
	assert reports == [] and all(abs(a - b) < 1e-6 for a, b in zip(dock.region()[kind], region[kind])), reports
assert dock.region_kind.currentData() == 'sea_point'  # the sea at the center of the map
# an ocean or sea by its name or its MRGID (the index of the package, without Earth Engine): the list Sea, its MRGID
reports = dock.apply_parameters({'analysis': 'map_layer', 'parameters': {'region': {'sea': 'alborán sea'},
                                                                         'variable': 'Chl-a', 'sensor': 'Modis'}})
assert reports == [] and dock.region() == {'sea': 3324} and dock.sea.currentText() == 'Alboran Sea (MRGID 3324)'
assert dock.sea_row.isVisibleTo(dock) and dock.sea.isVisibleTo(dock) and not dock.admin.isVisibleTo(dock)
dock.sea_text.setText('MEDITERRANEAN')
dock.search_seas()
assert [dock.sea.itemData(i) for i in range(dock.sea.count())] == [4280, 4279]
assert dock.sea.itemText(1) == 'Mediterranean Sea - Western Basin · 475,507 km² (MRGID 4279)'
dock.sea.setCurrentIndex(1)
assert dock.region() == {'sea': 4279} and 'No sea' not in messages[-1][1]
dock.sea_text.setText('atlantis')
dock.search_seas()
assert dock.sea.count() == 0 and 'No sea with "atlantis"' in messages[-1][1]
reports = dock.apply_parameters({'analysis': 'map_layer', 'parameters': {'region': {'sea': 'Atlantis'},
                                                                         'variable': 'Chl-a', 'sensor': 'Modis'}})
assert [r['name'] for r in reports] == ['region'] and 'find_seas' in reports[0]['reason'], reports
print('the seas: by name or MRGID, searched without Earth Engine, and the sea at the center of the map')
reports = dock.apply_parameters({'analysis': 'map_layer', 'parameters': {'region': {'biome_at': [-3.3, 37.1]},
                                                                         'variable': 'NDVI', 'sensor': 'Landsat'}})
assert dock.region_kind.currentData() == 'biome' and [r['name'] for r in reports] == ['region.within'], reports
assert messages[-1][0] == 'Warning' and messages[-1][2] == 0 and 'the part of the biome in the map extent' in \
	messages[-1][1]
print('the map extent and the points at its center:', got)

# a region of GeoJSON: a temporary layer, not added twice
square = {'type': 'Polygon', 'coordinates': [[[-3.6, 36.9], [-3.5, 36.9], [-3.5, 37.0], [-3.6, 37.0], [-3.6, 36.9]]]}
source = {'analysis': 'time_series', 'parameters': {'region': {'geojson': square}, 'variable': 'NDVI',
                                                   'sensor': 'Landsat', 'start': '2020-01-01', 'end': '2020-12-31'}}
n = len(QgsProject.instance().mapLayers())
assert dock.apply_parameters(source) == []
layer = dock.layer.currentLayer()
assert layer.name() == 'Region of the parameters' and layer.featureCount() == 1 and dock.region_kind.currentData() == \
	'layer'
assert dock.region()['geojson']['features'][0]['geometry'] == square
assert dock.apply_parameters(source) == [] and len(QgsProject.instance().mapLayers()) == n + 1

# Open parameters… of a file: those that a result writes next to its files
path = os.path.join(TMP, 'series.parameters.json')
parameters.save('time_series', {'region': {'country': 'ESP'}, 'variable': 'LST', 'sensor': 'Modis', 'step': 'annual',
                                'start': '2019-01-01', 'end': '2021-12-31'}, path)
assert dock.apply_parameters(path) == []
assert dock.region_kind.currentData() == 'country' and dock.country.text() == 'ESP' and dock.step.currentData() == \
	'annual' and dock.variable.currentData()['variable'] == 'LST'

# what cannot be applied: a message that stays, with the reasons; the rest applied
reports = dock.apply_parameters({'monitoreo': '0.0.1', 'analysis': 'time_series', 'parameters': {
	'region': {'wdpa_id': [555588816, 389011]}, 'variable': 'NDVI', 'sensor': 'Sentinel-2', 'step': 'weekly',
	'scale': 30, 'what': 1, 'start': '2024-01-01', 'end': '2024-06-30'}})
lvl, text, duration = messages[-1]
assert lvl == 'Warning' and duration == 0 and 'Not applied: ' in text, messages[-1]
for words in ('what (1): not a parameter of time_series', 'region ({"wdpa_id": [555588816, 389011]}): the panel '
              'takes one protected area', 'step ("weekly"): not in its list in the panel', 'scale (30): the panel has '
              'no option for it', 'saved with MonitorEO 0.0.1'):
	assert words in text, (words, text)
assert dock.variable.currentData()['sensor'] == 'Sentinel-2' and dock.start.date().toString('yyyy-MM-dd') == \
	'2024-01-01' and dock.step.currentData() == 'annual'
pick(dock.variable, text='SCF · Landsat')  # an option greyed out for the variable: its reason
reports = dock.apply_parameters({'analysis': 'time_series', 'parameters': {'variable': 'SCF', 'sensor': 'Landsat',
                                                                           'metric': 'max'}})
assert [r['name'] for r in reports] == ['metric'] and 'only takes the mean' in reports[0]['reason'], reports
reports = dock.apply_parameters({'analysis': 'download_rgb', 'parameters': {'variable': 'NDVI', 'sensor': 'Modis',
                                                                            'collection': 'MODIS/061/MOD13Q1'}})
assert [r['name'] for r in reports] == ['analysis'] and 'has no true colour' in reports[0]['reason'], reports
reports = dock.apply_parameters({'analysis': 'time_series', 'parameters': {'variable': 'XYZ', 'sensor': 'Landsat'}})
assert {r['name'] for r in reports} == {'variable', 'sensor'}, reports
for bad in ('{not json', '{"analysis": "nothing"}'):
	assert dock.apply_parameters(bad) is None and messages[-1][0] == 'Critical', messages[-1]
assert not computed and not dock.tasks, computed
print('not applied, with the reasons:', text[text.index('Not applied'):][:200], '…')

# names in any case and without spaces, as parameters.check, the services and the Earth Engine app take them (those
# that Python, R, the command line or the MCP server write keep them as their user gave them)
pick(dock.variable, text='NDSI · Sentinel-2')
pick(dock.landcover_map, 'WorldCover')
reports = dock.apply_parameters({'analysis': 'time_series', 'parameters': {
	'region': {'country': 'ESP'}, 'variable': 'ndvi', 'sensor': 'landsat', 'start': '2020-01-01', 'end': '2020-12-31',
	'doy': True, 'interannual': 'median', 'other_variable': 'ndsi', 'other_sensor': 'SENTINEL-2',
	'where': [{'variable': 'elevation', 'sensor': 'copernicus', 'min': 1500},
	          {'landcover': 'corine', 'year': 2018, 'exclude': ['Water', 'BUILT']}]}})
assert reports == [], reports
assert (dock.variable.currentData()['variable'], dock.variable.currentData()['sensor']) == ('NDVI', 'Landsat')
assert dock.doy_other.currentData() == {'variable': 'NDSI', 'sensor': 'Sentinel-2'}
assert dock.where[0]['on'].isChecked() and dock.where[0]['variable'].currentData()['variable'] == 'ELEVATION'
assert dock.landcover_box.isChecked() and dock.landcover_map.currentData() == 'CORINE'
assert sorted(dock.landcover_classes.checkedItemsData()) == ['built', 'water']
pick(dock.area_map, 'WorldCover')
reports = dock.apply_parameters({'analysis': 'area_by_class', 'parameters': {
	'region': {'country': 'ESP'}, 'landcover': 'corine land cover', 'year': 2018}})
assert reports == [] and dock.area_map.currentData() == 'CORINE' and dock.area_kind.currentData() == 'landcover', \
	reports
pick(dock.zone_variable, text='ELEVATION')
reports = dock.apply_parameters({'analysis': 'region_stats', 'parameters': {
	'region': {'country': 'ESP'}, 'variable': 'NDVI', 'sensor': 'Landsat', 'start': '2020-01-01', 'end': '2020-12-31',
	'zones': {'variable': 'slope', 'sensor': 'COPERNICUS'}, 'stats': ['p25', 'p50', 'p75', 'mean']}})
assert reports == [] and dock.zone_variable.currentData()['variable'] == 'SLOPE', reports
dock.doy.setChecked(False)

# the burn severity: MODIS without a collection is Terra, as services.burn_severity; Cloud Score+ or the SCL also while
# the variable greys it out (SCF: fixed filters), since the burn severity computes the NBR with it
dock.cloud_score.setChecked(True)
pick(dock.variable, text='SCF · Landsat')
assert not dock.cloud_score.isEnabled() and dock.cloud_score.isChecked()
pick(dock.fire_index, 'dNBR')
pick(dock.fire_sensor, 'Sentinel-2')
reports = dock.apply_parameters({'analysis': 'burn_severity', 'parameters': {
	'region': {'country': 'ESP'}, 'index': 'rdnbr', 'sensor': 'MODIS', 'start': '2023-05-15', 'end': '2023-08-14',
	'other_start': '2023-09-15', 'other_end': '2023-11-30', 'quality': {'cloud_score': None}}})
assert reports == [], reports
assert dock.fire_index.currentData() == 'RdNBR' and dock.fire_sensor.currentData() == 'MODIS/061/MOD09GA'
call = dock.call_of('burn')
assert (call[1]['index'], call[1]['sensor'], call[1]['collection']) == ('RdNBR', 'Modis', 'MODIS/061/MOD09GA'), call
assert not dock.cloud_score.isChecked() and call[1]['quality']['cloud_score'] is None, call[1]['quality']
dock.cloud_score.setChecked(True)
assert not computed and not dock.tasks, computed
print('names in any case, MODIS Terra and the SCL of the burn severity: applied')

# the window of a result: its parameters in the details, its buttons and the JSON next to its CSV
pick(dock.variable, text='NDVI · Landsat')
pick(dock.region_kind, 'country')
pick(dock.area_kind, 'trend')


def area_by_class(region, csv=None, **opts):
	with open(csv, 'w') as f:
		f.write('region,class,label,ha,percent\n')
	rows = [{'region': 'ESP', 'class': 0, 'label': 'no significant trend', 'ha': 1.0, 'percent': 100.0}]
	return {'rows': rows, 'mode': 'trend', 'scale': 30.0, 'unit': '', 'title': 'Areas', 'csv': csv, 'references': [],
	        'credits': [], 'classes': [{'class': 0, 'label': 'no significant trend', 'colour': 'bdbdbd'}]}


services.area_by_class = area_by_class
call = dock.call_of('areas')
dock.run_areas()
wait()
res = dock.series[-1]
assert res['call'] == parameters.make(*call), res.get('call')
dlg = dock.series_dialogs[len(dock.series) - 1]
buttons = [b.text() for b in dlg.findChildren(QPushButton)]
assert buttons[-3:] == ['Copy parameters', 'Save parameters…', 'Close'], buttons
details = dlg.findChild(QTextBrowser, 'details').toPlainText()
assert 'Parameters of the analysis area_by_class' in details and 'trend: true' in details, details
next(b for b in dlg.findChildren(QPushButton) if b.text() == 'Copy parameters').click()
assert json.loads(QApplication.clipboard().text()) == res['call']
from monitoreo_qgis.results import save_file  # noqa: E402
save_file(res['csv'], os.path.join(TMP, 'areas.csv'), res)
with open(os.path.join(TMP, 'areas.parameters.json'), encoding='utf-8') as f:
	assert json.load(f) == res['call']
print('window of the result:', buttons, '| its parameters next to its CSV')

plugin.unload()
QgsProject.instance().removeAllMapLayers()
settings = QgsSettings()
for key in [k for k in settings.allKeys() if k.startswith('MonitorEO/')]:
	settings.remove(key)
for key, value in STORED.items():
	settings.setValue(key, value)
print('OK')
