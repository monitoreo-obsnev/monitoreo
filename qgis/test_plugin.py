"""Test of the QGIS plugin without its window (offscreen), with the Python of QGIS:

    EE_PROJECT=<project> <python of QGIS> qgis/test_plugin.py

(macOS: /Applications/QGIS-final-4_0_3.app/Contents/MacOS/python, with QGIS_APP for another QGIS). It
loads the plugin as QGIS does, opens its panel, checks the help of its buttons ⓘ and runs a search of protected
areas, a map layer (and its true colour under it), two time series (map extent, and a layer with two polygons) with
the maps of two of their dates (and the true colour of two others), trends with their map, a comparison of periods,
the burn severity of a fire (dNBR, RBR and RdNBR, also the RdNBR of MODIS Aqua, only in the theme Fire) and data of
Earth Engine given by their ID instead of a variable (a collection with dates, a fixed image and a dataset of the GEE
Community Catalog chosen by its themes), waiting for their QGIS tasks.
"""

import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
APP = os.environ.get('QGIS_APP', '/Applications/QGIS-final-4_0_3.app')
for proj in ('Contents/Resources/proj', 'Contents/Resources/qgis/proj'):
	if os.path.exists(os.path.join(APP, proj, 'proj.db')):
		os.environ.setdefault('PROJ_DATA', os.path.join(APP, proj))
		os.environ.setdefault('PROJ_LIB', os.path.join(APP, proj))
sys.path.insert(0, os.path.join(APP, 'Contents', 'Resources', 'python'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsFeature, QgsField, QgsGeometry,  # noqa: E402
                       QgsProject, QgsRectangle, QgsVectorLayer)
from qgis.gui import QgsMapCanvas, QgsMessageBar  # noqa: E402
from qgis.PyQt.QtCore import Qt, QVariant  # noqa: E402
from qgis.PyQt.QtWidgets import QCheckBox, QComboBox, QMainWindow, QPushButton  # noqa: E402

app = QgsApplication([], True)
QgsApplication.setPrefixPath(os.path.join(APP, 'Contents', 'MacOS'), True)
if os.path.isdir(os.path.join(APP, 'Contents', 'PlugIns', 'qgis')):  # data providers (WMS/XYZ) outside the app
	QgsApplication.setPluginPath(os.path.join(APP, 'Contents', 'PlugIns', 'qgis'))
app.initQgis()


class Iface:
	def __init__(self):
		self.window = QMainWindow()
		self.canvas = QgsMapCanvas()
		self.bar = QgsMessageBar()
		self.messages = []

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


def wait(dock, timeout=900):
	t0 = time.time()
	while dock.tasks and time.time() - t0 < timeout:
		app.processEvents()
		time.sleep(0.2)
	app.processEvents()
	assert not dock.tasks, 'tasks did not finish'


iface = Iface()
import monitoreo_qgis  # noqa: E402
plugin = monitoreo_qgis.classFactory(iface)
plugin.initGui()
plugin.toggle(True)
dock = plugin.dock
assert dock is not None, 'the panel did not open'
_message = dock.message
dock.message = lambda text, lvl='Info', duration=6: (iface.messages.append(f'{lvl}: {text}'), _message(text, lvl, duration))
dock.project.setText(os.environ['EE_PROJECT'])
names = [dock.theme.itemText(i) for i in range(dock.theme.count())]
print('themes:', names, '| variables of', dock.theme.currentText() + ':', dock.variable.count(), '| selected:',
      dock.variable.currentText())
assert dock.theme.currentData() == 'vegetation' and dock.variable.currentText().startswith('NDVI · Sentinel-2')
# after the themes of the catalog, those of the data of Earth Engine outside it (services.themes), as in the app
assert names[-3:] == ['Earth Engine data (by its ID)', 'GEE Community Catalog', 'All the variables'], names
assert not dock.data_row.isVisibleTo(dock) and dock.variable_field.isVisibleTo(dock)
links = dock.feedback_links
assert links['issue'].startswith('https://github.com/monitoreo-obsnev/monitoreo/issues/new/choose?tool=QGIS+plugin')
assert 'entry.1706228456=Complemento+de+QGIS' in links['form'], links
print('feedback:', links['issue'])
dock.theme.setCurrentIndex(dock.theme.findData('climate'))
assert all(dock.variable.itemData(i)['variable'] in ('PRECIP', 'TMEAN', 'TMIN', 'TMAX', 'PET', 'AET', 'CWD', 'SOILM',
                                                     'VPD') or dock.variable.itemData(i)['variable'].startswith('BIO')
           for i in range(dock.variable.count()))
dock.theme.setCurrentIndex(names.index('All the variables'))  # for the help of each one
dock.variable.setCurrentIndex(dock.variable.findText('NDVI · Sentinel-2 · 10 m', Qt.MatchFlag.MatchStartsWith))
assert dock.variable.currentData()['variable'] == 'NDVI'
print('all the variables:', dock.variable.count())

# the buttons ⓘ of the options: a help with a link to the manual, also with each variable (help of the variable and
# of the filters); the ⓘ of the list of protected areas hides with it
from monitoreo_qgis.dock import InfoButton  # noqa: E402
buttons = dock.findChildren(InfoButton)
selected = dock.variable.currentIndex()
for i in range(dock.variable.count()):
	dock.variable.setCurrentIndex(i)
	assert all('More in the manual' in b.help() for b in buttons)
dock.variable.setCurrentIndex(selected)
assert not dock.wdpa_field.findChild(InfoButton).isVisibleTo(dock)
print('info buttons:', len(buttons))

# protected areas
dock.region_kind.setCurrentIndex([dock.region_kind.itemData(i) for i in range(dock.region_kind.count())].index('wdpa'))
dock.wdpa_text.setText('Sierra Nevada')
dock.search_wdpa()
wait(dock)
print('WDPA:', dock.wdpa.count(), 'areas, first:', dock.wdpa.itemText(0))
dock.ramsar.setChecked(True)  # only the Ramsar sites
dock.wdpa_text.setText('Doñana')
dock.search_wdpa()
wait(dock)
assert dock.wdpa.count() and all('Ramsar' in dock.wdpa.itemText(i) for i in range(dock.wdpa.count()))
dock.ramsar.setChecked(False)
kinds = [dock.region_kind.itemData(i) for i in range(dock.region_kind.count())]

# administrative units (FAO GAUL 2025), countries and islands
dock.region_kind.setCurrentIndex(kinds.index('admin'))
assert dock.admin_row.isVisibleTo(dock) and not dock.wdpa_row.isVisibleTo(dock)
dock.admin_text.setText('Granada')
dock.admin_level.setCurrentIndex(1)  # level 2
dock.admin_country.setText('esp')
dock.search_admin()
wait(dock)
assert 'Granada, Andalucía, Spain' in dock.admin.itemText(0), dock.admin.itemText(0)
assert dock.region() == {'admin2': 141938}
dock.region_kind.setCurrentIndex(kinds.index('country'))
dock.country.setText('esp')
assert dock.region() == {'country': 'ESP'}
canvas = iface.mapCanvas()
canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
canvas.setExtent(QgsRectangle(2.8, 39.5, 3.0, 39.7))  # Mallorca
dock.region_kind.setCurrentIndex(kinds.index('island'))
assert dock.region() == {'island_at': [2.9, 39.6]} or abs(dock.region()['island_at'][0] - 2.9) < 1e-6
print('regions: administrative unit, country and island')

# map layer over the map extent
canvas = iface.mapCanvas()
canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
canvas.setExtent(QgsRectangle(-3.62, 36.86, -3.50, 36.93))
dock.region_kind.setCurrentIndex(1)
dock.start.setDate(dock.start.date().fromString('2021-01-01', 'yyyy-MM-dd'))
dock.end.setDate(dock.end.date().fromString('2021-12-31', 'yyyy-MM-dd'))
n_layers = len(QgsProject.instance().mapLayers())
dock.run_map()
wait(dock)
layers = list(QgsProject.instance().mapLayers().values())
assert len(layers) == n_layers + 1, iface.messages
print('map layer:', layers[-1].name(), '| valid:', layers[-1].isValid(), '| provider:', layers[-1].providerType())

# the list Layer of the map: the true colour only for the variables whose images have it, without Compare with
kind = dock.map_kind
assert [kind.itemData(i) for i in range(kind.count())] == ['index', 'rgb', 'both'] and kind.isEnabled()
selected, metric = dock.variable.currentIndex(), dock.map_metric.currentIndex()  # (the CF fixes the metric)
for text, enabled in (('NDVI · Modis · 250 m · MOD13Q1', False), ('ELEVATION · Copernicus', False),
                      ('PRECIP · ERA5-Land', False), ('CF · Modis · 1000 m · MOD09GA', True),
                      ('NDVI · Landsat', True), ('NDVI · Sentinel-2', True)):
	dock.variable.setCurrentIndex(dock.variable.findText(text, Qt.MatchFlag.MatchStartsWith))
	assert dock.variable.currentText().startswith(text), text
	assert kind.isEnabled() == enabled, (text, kind.toolTip())
	assert enabled or (kind.currentData() == 'index' and 'true colour' in kind.toolTip()), (text, kind.toolTip())
dock.variable.setCurrentIndex(selected)
dock.map_metric.setCurrentIndex(metric)
kind.setCurrentIndex(kind.findData('both'))
dock.compare_on.setChecked(True)
assert not kind.isEnabled() and kind.currentData() == 'index' and 'Compare with' in kind.toolTip()
dock.compare_on.setChecked(False)
assert kind.isEnabled()

# the map and its true colour (Both): two layers, the true colour (red, green and blue stretched together) under the
# map, on the same grid
kind.setCurrentIndex(kind.findData('both'))
before = set(QgsProject.instance().mapLayers())
dock.run_map()
wait(dock)
kind.setCurrentIndex(kind.findData('index'))
tree = [n.layer() for n in QgsProject.instance().layerTreeRoot().findLayers()]
new = [layer for layer in tree if layer.id() not in before]
assert len(new) == 2, iface.messages[-3:]
index_layer, rgb_layer = new  # the map on top
assert index_layer.renderer().type() == 'singlebandpseudocolor' and index_layer.bandCount() == 1
r = rgb_layer.renderer()
assert rgb_layer.bandCount() == 3 and r.type() == 'multibandcolor', (rgb_layer.bandCount(), r.type())
assert (r.redBand(), r.greenBand(), r.blueBand()) == (1, 2, 3)
stretches = [(e.minimumValue(), e.maximumValue()) for e in (r.redContrastEnhancement(), r.greenContrastEnhancement(),
                                                           r.blueContrastEnhancement())]
assert len(set(stretches)) == 1 and stretches[0][0] < stretches[0][1], stretches  # one range for the three
assert rgb_layer.name().endswith('true colour') and rgb_layer.extent() == index_layer.extent()
assert (rgb_layer.width(), rgb_layer.height()) == (index_layer.width(), index_layer.height())
assert 'True colour (red, green, blue): reflectance from' in rgb_layer.serverProperties().abstract()
print('true colour:', rgb_layer.name(), '| stretch', stretches[0])

# time series over the extent
dock.step.setCurrentIndex([dock.step.itemData(i) for i in range(dock.step.count())].index('monthly'))
dock.run_series()
wait(dock)
res = dock.series[-1]
print('series (extent):', len(res['rows']), 'rows, first', res['rows'][0], '| matplotlib chart', bool(res['chart']))

# only the pixels where: the elevation above 800 m (a fixed layer) and the NDVI of Sentinel-2 (with the period)
c = dock.where[0]
c['on'].setChecked(True)
c['min'].setText('800')
assert c['unit'].text() == '[m]', c['unit'].text()
d = dock.where[1]
d['variable'].setCurrentIndex(d['variable'].findText('NDVI · Sentinel-2'))
d['on'].setChecked(True)
d['min'].setText('0,2')
where = dock.variable_args()['where']
assert where[0] == {'variable': 'ELEVATION', 'sensor': 'Copernicus', 'collection': 'COPERNICUS/DEM/GLO30_2024_1',
                    'min': 800.0}, where
assert where[1]['min'] == 0.2 and where[1]['period'] == ['2021-01-01', '2021-12-31'], where
d['on'].setChecked(False)
dock.run_series()
wait(dock)
part = dock.series[-1]
assert part['rows'][0]['n_pixels'] < res['rows'][0]['n_pixels'], (part['rows'][0], res['rows'][0])
print('series (only above 800 m):', part['rows'][0]['n_pixels'], 'of', res['rows'][0]['n_pixels'], 'pixels')
c['min'].setText('')
try:
	dock.variable_args()
	raise AssertionError('a condition without limits')
except ValueError as e:
	assert 'min, a max or both' in str(e)
c['on'].setChecked(False)
chart = dock.series_dialogs[len(dock.series) - 1].chart
if chart is not None and os.environ.get('TEST_OUT'):  # chart drawn with Qt (no matplotlib)
	chart.resize(860, 360)
	chart.grab().save(os.path.join(os.environ['TEST_OUT'], 'qt_chart.png'), 'PNG')
	print('Qt chart saved')


def variable_help_text(dock):
	"""The help of the data of Earth Engine of the panel (that of the button ⓘ of their ID), with what
	services.describe_asset read of them."""
	from monitoreo_qgis.helptexts import data_help
	return data_help(dock.variable.currentData(), dock.described())


def add_from_window(res, index=0, significant=False, kind=None):
	"""Add the map INDEX of res['maps'] with the button of the window of the result RES (with KIND, that layer of the
	list Layer: 'index', 'rgb' or 'both'); the layers of its group."""
	dlg = dock.series_dialogs[dock.series.index(res)]
	dlg.findChild(QComboBox, 'map_choice').setCurrentIndex(index)
	if kind:
		layer = dlg.findChild(QComboBox, 'map_kind')
		layer.setCurrentIndex(layer.findData(kind))
	if significant:
		dlg.findChild(QCheckBox).setChecked(True)
	next(b for b in dlg.findChildren(QPushButton) if b.text() == 'Add to the map').click()
	wait(dock)
	group = QgsProject.instance().layerTreeRoot().findGroup(res['label'])
	assert group is not None, iface.messages[-3:]
	return [n.layer() for n in group.findLayers()]


# the window of a series whose images have no true colour (e.g. the NDVI of MODIS): no list Layer
from monitoreo_qgis.results import SeriesDialog  # noqa: E402
plain = SeriesDialog(dict(res, rgb=False), None, lambda *args: None)
assert plain.findChild(QComboBox, 'map_choice') is not None and plain.findChild(QComboBox, 'map_kind') is None

# the maps of two dates of the series (June and July), in the group of the series, with the colours of the first one
# and their days in the Temporal Controller
assert [m['label'] for m in res['maps'][:3]] == ['Whole period (2021)', 'Jan 2021', 'Feb 2021'], res['maps'][:3]
add_from_window(res, 6)
july, june = add_from_window(res, 7)  # the last one on top
ramps = [(r.classificationMin(), r.classificationMax()) for r in (june.renderer(), july.renderer())]
assert ramps[0] == ramps[1], ramps
times = [l.temporalProperties().fixedTemporalRange() for l in (june, july)]
assert all(l.temporalProperties().isActive() for l in (june, july))
assert [(t.begin().toString('yyyy-MM-dd'), t.end().toString('yyyy-MM-dd')) for t in times] == \
       [('2021-06-01', '2021-07-01'), ('2021-07-01', '2021-08-01')], times
print('maps of the series:', [l.name() for l in (june, july)], '| colours', ramps[0])

# the true colour of two other dates (August with its index, Both; September alone), under the index, with the same
# days and stretched as the first true colour of the series, so that they can be compared
assert res['rgb'] is True and dock.series_dialogs[dock.series.index(res)].findChild(QComboBox, 'map_kind')
august, august_rgb = add_from_window(res, 8, kind='both')[:2]
september_rgb = add_from_window(res, 9, kind='rgb')[0]
assert august.renderer().type() == 'singlebandpseudocolor', august.renderer().type()
assert (august.renderer().classificationMin(), august.renderer().classificationMax()) == ramps[0]
for layer, days in ((august, ('2021-08-01', '2021-09-01')), (august_rgb, ('2021-08-01', '2021-09-01')),
                    (september_rgb, ('2021-09-01', '2021-10-01'))):
	t = layer.temporalProperties().fixedTemporalRange()
	assert layer.temporalProperties().isActive() and \
	       (t.begin().toString('yyyy-MM-dd'), t.end().toString('yyyy-MM-dd')) == days, (layer.name(), t)
stretches = []
for layer in (august_rgb, september_rgb):
	r = layer.renderer()
	assert r.type() == 'multibandcolor' and layer.bandCount() == 3 and layer.name().endswith('· true colour'), \
		(layer.name(), r.type())
	stretches.append((r.redContrastEnhancement().minimumValue(), r.redContrastEnhancement().maximumValue()))
assert stretches[0] == stretches[1] == res['rgb_stretch'], (stretches, res.get('rgb_stretch'))
assert (august_rgb.width(), august_rgb.height()) == (august.width(), august.height())
print('true colour of the series:', [layer.name() for layer in (august_rgb, september_rgb)], '| stretch',
      stretches[0])

# time series over a layer with two polygons, in UTM
lyr = QgsVectorLayer('Polygon?crs=EPSG:25830', 'zones', 'memory')
lyr.dataProvider().addAttributes([QgsField('zone', QVariant.String)])  # (deprecated in QGIS 4, still works)
lyr.updateFields()
for name, x0 in (('west', 445000), ('east', 450000)):
	f = QgsFeature(lyr.fields())
	f.setGeometry(QgsGeometry.fromRect(QgsRectangle(x0, 4079000, x0 + 4000, 4084000)))
	f['zone'] = name
	lyr.dataProvider().addFeature(f)
QgsProject.instance().addMapLayer(lyr)
dock.region_kind.setCurrentIndex(0)
dock.layer.setLayer(lyr)
dock.name_field.setField('zone')
dock.step.setCurrentIndex([dock.step.itemData(i) for i in range(dock.step.count())].index('annual'))
dock.run_series()
wait(dock)
res = dock.series[-1]
print('series (layer):', [(r['region'], r['date'], round(r['value'], 3)) for r in res['rows']])
assert sorted(res['regions']) == ['east', 'west']

# seasonal trends (MODIS, by years) and their map, over the map extent
from qgis.PyQt.QtCore import QDate  # noqa: E402
dock.region_kind.setCurrentIndex(1)
dock.variable.setCurrentIndex(dock.variable.findText('NDVI · Modis · 250 m · MOD13Q1'))
dock.start.setDate(QDate(2014, 1, 1))
dock.end.setDate(QDate(2021, 12, 31))
dock.run_trend_table()
wait(dock)
res = dock.series[-1]
assert res['kind'] == 'trends' and res['rows'][0]['n'] == 8, res['rows']
print('trends:', [(r['key'], r['n'], round(r['tau'], 2), round(r['p_value'], 3), round(r['slope'], 4)) for r in res['rows']],
      '| chart', bool(res['chart']))
assert [m['label'] for m in res['maps']] == ['Annual trend (2014-2021)'], res['maps']  # by years: no parts
layers = add_from_window(res, 0, significant=True)
assert len(layers) == 1 and layers[0].bandCount() == 6 and layers[0].name().endswith('(p < 0.05)'), iface.messages[-2:]
assert dock.series_dialogs[dock.series.index(res)].findChild(QComboBox, 'map_kind') is None  # no true colour of trends
print('map of the trends:', layers[0].name())
before = set(QgsProject.instance().mapLayers())
dock.run_trend_map()
wait(dock)
new = [l for k, l in QgsProject.instance().mapLayers().items() if k not in before]
assert len(new) == 1 and new[0].bandCount() == 6, iface.messages[-2:]
layer = new[0]
print('trend map:', layer.name(), '| bands', [layer.bandName(i) for i in range(1, 7)], '| renderer', layer.renderer().type())

# comparison of two periods: series (monthly) and map
dock.compare_on.setChecked(True)
dock.start.setDate(QDate(2016, 1, 1))
dock.end.setDate(QDate(2018, 12, 31))
dock.other_start.setDate(QDate(2021, 1, 1))
dock.other_end.setDate(QDate(2021, 12, 31))
dock.step.setCurrentIndex([dock.step.itemData(i) for i in range(dock.step.count())].index('monthly'))
dock.run_series()
wait(dock)
res = dock.series[-1]
assert res['kind'] == 'comparison' and len(res['profile']) == 12, res
print('comparison:', [(r['key'], round(r['difference'], 3)) for r in res['profile'][:3]], '... | chart', bool(res['chart']))
dock.show_series_button.click()
before = set(QgsProject.instance().mapLayers())
dock.run_map()
wait(dock)
new = [l for k, l in QgsProject.instance().mapLayers().items() if k not in before]
assert len(new) == 1 and new[0].bandCount() == 3, iface.messages[-2:]
layer = new[0]
print('comparison map:', layer.name(), '| bands', [layer.bandName(i) for i in range(1, 4)])
dock.compare_on.setChecked(False)

# burn severity of a fire, only in the theme Fire (as in the Earth Engine app): the classes of the USGS (dNBR), the RBR
# and the classes of Miller & Thode 2007 (RdNBR, with Sentinel-2 and with MODIS Aqua) over a part of the fire of Sierra
# Bermeja (September 2021), their layers coloured as in the other tools
from monitoreo import fire, trends  # noqa: E402
assert dock.theme.currentData() is None and dock.fire_box.isVisibleTo(dock)  # all the variables: every analysis
# it computes the NBR with the filters the user chose, also while a variable with fixed filters greys them out
dock.variable.setCurrentIndex(dock.variable.findText('ELEVATION · Copernicus', Qt.MatchFlag.MatchStartsWith))
assert not dock.filters['clouds'].isChecked() and not dock.filters['clouds'].isEnabled()
assert dock.quality_args()['clouds'] is False and dock.quality_args(own=True)['clouds'] is True
dock.theme.setCurrentIndex(dock.theme.findData('vegetation'))
assert not dock.fire_box.isVisibleTo(dock)
dock.theme.setCurrentIndex(dock.theme.findData('fire'))
assert dock.fire_box.isVisibleTo(dock) and dock.variable.currentData()['variable'] == 'NBR'
canvas.setExtent(QgsRectangle(-5.20, 36.50, -5.15, 36.54))
for key, day in (('before_start', '2021-07-15'), ('before_end', '2021-08-31'), ('after_start', '2021-09-20'),
                 ('after_end', '2021-10-31')):
	dock.fire_dates[key].setDate(QDate.fromString(day, 'yyyy-MM-dd'))
MODIS = ['MODIS/061/MOD09GA', 'MODIS/061/MYD09GA']  # Terra and Aqua, only for the RdNBR
sensors = lambda: [dock.fire_sensor.itemData(i) for i in range(dock.fire_sensor.count())]  # noqa: E731
for index, sensor in (('dNBR', 'Sentinel-2'), ('RBR', 'Sentinel-2'), ('RdNBR', 'Sentinel-2'),
                      ('RdNBR', 'MODIS/061/MYD09GA')):
	dock.fire_index.setCurrentIndex(dock.fire_index.findData(index))
	assert [s for s in sensors() if s in MODIS] == (MODIS if index == 'RdNBR' else []), (index, sensors())
	dock.fire_sensor.setCurrentIndex(dock.fire_sensor.findData(sensor))
	before = set(QgsProject.instance().mapLayers())
	dock.run_burn()
	wait(dock)
	new = [l for k, l in QgsProject.instance().mapLayers().items() if k not in before]
	assert len(new) == 1 and new[0].bandCount() == (5 if index == 'RdNBR' else 4), iface.messages[-2:]
	res = dock.series[-1]
	assert res['kind'] == 'burn' and res['index'] == index and res['readme'], res
	if sensor in MODIS:  # the sensor Modis with the collection of Aqua, in pixels of 500 m
		assert res['args']['sensor'] == 'Modis' and res['args']['collection'] == sensor, res['args']
		assert res['resolution'] >= 500 and 'MYD09GA' in new[0].name(), (res['resolution'], new[0].name())
	r = new[0].renderer()
	band = r.inputBand() if hasattr(r, 'inputBand') else r.band()
	if index in ('dNBR', 'RdNBR'):
		legend = fire.legend(index)  # the classes of the USGS or those of Miller & Thode 2007
		assert r.type() == 'paletted' and band == 2, (r.type(), band)  # the band severity
		assert [c.color.name() for c in r.classes()] == [c['color'] for c in legend]
		assert [c.value for c in r.classes()] == [c['value'] for c in legend]
		assert [c.label for c in r.classes()] == [fire.class_label(c) for c in legend]
		burned = sum(res['burned_ha'].values())
		assert burned > 0, res['classes']
		if index == 'RdNBR':
			assert len(res['classes']) == len(fire.RDNBR_SEVERITY) * len(res['stats']) and res['stats'][0]['ha'] > 0
			assert r.classes()[-1].label == 'High severity (RdNBR ≥ 0.641)', r.classes()[-1].label
		print(f'burn severity ({index}):', new[0].name(), '| burned' if index == 'dNBR' else '| changed', round(burned),
		      'ha |', [(c['class'], round(c['ha'])) for c in res['classes']])
	else:
		items = r.shader().rasterShaderFunction().colorRampItemList()
		assert r.type() == 'singlebandpseudocolor' and band == 1, (r.type(), band)  # the band rbr
		assert (r.classificationMin(), r.classificationMax()) == fire.RBR_RANGE
		assert items[0].color.name() == '#' + trends.DIVERGING[-1] and items[-1].color.name() == '#' + trends.DIVERGING[0]
		print('RBR:', new[0].name(), '|', {k: round(v, 3) for k, v in res['stats'][0].items() if k != 'region'})
dock.show_series_button.click()  # the window of the last one (the RdNBR of MODIS Aqua: its classes and statistics)
from monitoreo_qgis.results import ResultDialog  # noqa: E402
from qgis.PyQt.QtWidgets import QTableWidget  # noqa: E402
window = dock.series_dialogs[len(dock.series) - 1]
assert isinstance(window, ResultDialog) and window.findChild(QTableWidget, 'rdnbr_stats') is not None
# back to the dNBR from MODIS: MODIS is no longer offered, and Landsat is chosen (as in the Earth Engine app)
dock.fire_index.setCurrentIndex(dock.fire_index.findData('dNBR'))
assert dock.fire_sensor.currentData() == 'Landsat' and not [s for s in sensors() if s in MODIS], sensors()
assert dock.fire_source() == ('Landsat', None)
dock.fire_sensor.setCurrentIndex(dock.fire_sensor.findData('Sentinel-2'))

# data of Earth Engine given by their ID instead of a variable (theme Earth Engine data): a collection with dates (the
# precipitation of TerraClimate: a monthly series, the map of one of its months from its window, trends and the map of
# its period) and a fixed image (bio01 of WorldClim, stored in tenths of °C: its map), without pixel filters nor true
# colour; and a dataset of the GEE Community Catalog chosen by its themes (FABDEM), which fills the ID and reads it
from monitoreo import services  # noqa: E402
from monitoreo_qgis.dock import number  # noqa: E402
dock.theme.setCurrentIndex(dock.theme.findData('earth_engine'))
assert dock.data_row.isVisibleTo(dock) and not dock.community_row.isVisibleTo(dock)
assert not dock.variable_field.isVisibleTo(dock) and not dock.fire_box.isVisibleTo(dock)
entry = dock.variable.currentData()
assert entry['custom'] and entry['fixed_filters'] == [] and not entry['rgb'] and 'variable' not in entry, entry
assert all('More in the manual' in b.help() for b in dock.findChildren(InfoButton))  # also before reading
canvas.setExtent(QgsRectangle(-3.60, 36.90, -2.90, 37.20))  # Sierra Nevada
dock.region_kind.setCurrentIndex(kinds.index('extent'))
dock.asset_id.setText('ee.ImageCollection("IDAHO_EPSCOR/TERRACLIMATE")')  # as in the Code Editor
dock.read_asset()
wait(dock)
read = dock.described()
assert read and read['type'] == 'image_collection' and read['use'] == 'collection', iface.messages[-2:]
assert dock.asset_id.text() == 'IDAHO_EPSCOR/TERRACLIMATE' and read['source'] == 'Earth Engine data catalog'
bands = [dock.asset_band.itemText(i) for i in range(dock.asset_band.count())]
assert 'pr' in bands and dock.asset_use.currentData() == 'collection' and dock.asset_use.isEnabled(), bands
dock.asset_band.setCurrentIndex(bands.index('pr'))
pr = next(b for b in read['bands'] if b['band'] == 'pr')
assert dock.asset_unit.text() == (pr.get('unit') or '') and dock.band_scale.text() == number(pr.get('band_scale'))
assert 'Earth Engine data catalog' in dock.asset_label.text() and read['references']
assert 'use it as Images with dates (collection)' in dock.asset_label.text(), dock.asset_label.text()
dock.asset_unit.setText('mm')
assert not any(w.isEnabled() or w.isChecked() for w in dock.filters.values()) and not dock.cloud_score.isEnabled()
assert not dock.map_kind.isEnabled() and dock.map_kind.currentData() == 'index'  # no true colour
assert dock.series_box.isEnabled() and dock.trends_box.isEnabled() and dock.export_series_button.isEnabled()
for b in dock.findChildren(InfoButton):
	assert 'More in the manual' in b.help()
assert 'IDAHO_EPSCOR/TERRACLIMATE' in variable_help_text(dock) and 'Abatzoglou' in variable_help_text(dock)
dock.start.setDate(QDate(2019, 1, 1))
dock.end.setDate(QDate(2020, 12, 31))
args = dock.variable_args()
assert args['collection'] == 'IDAHO_EPSCOR/TERRACLIMATE' and args['band'] == 'pr' and args['unit'] == 'mm', args
assert args['start'] == '2019-01-01' and not {'variable', 'sensor', 'quality', 'image'} & set(args), args
dock.step.setCurrentIndex([dock.step.itemData(i) for i in range(dock.step.count())].index('monthly'))
dock.run_series()
wait(dock)
res = dock.series[-1]
assert res['kind'] == 'series' and res['n_steps'] == 24 and res['unit'] == 'mm', (res.get('unit'), iface.messages[-2:])
assert res['title'].startswith('IDAHO_EPSCOR/TERRACLIMATE pr') and res['rgb'] is False and res['references'], res
assert dock.series_dialogs[dock.series.index(res)].findChild(QComboBox, 'map_kind') is None
july = add_from_window(res, 7)[0]  # July 2019
t = july.temporalProperties().fixedTemporalRange()
assert july.bandCount() == 1 and (t.begin().toString('yyyy-MM-dd'), t.end().toString('yyyy-MM-dd')) == \
       ('2019-07-01', '2019-08-01'), (july.name(), t)
assert 'mm, pixels of' in july.serverProperties().abstract(), july.serverProperties().abstract()
print('Earth Engine data, series:', res['title'], '|', len(res['rows']), 'rows | map of the series:', july.name())
dock.trend_step.setCurrentIndex(dock.trend_step.findData('annual'))
dock.start.setDate(QDate(2013, 1, 1))
dock.run_trend_table()
wait(dock)
res = dock.series[-1]
assert res['kind'] == 'trends' and res['rows'][0]['n'] == 8, (res['rows'], iface.messages[-2:])
before = set(QgsProject.instance().mapLayers())
dock.run_map()
wait(dock)
new = [l for k, l in QgsProject.instance().mapLayers().items() if k not in before]
assert len(new) == 1 and new[0].name().startswith('IDAHO_EPSCOR/TERRACLIMATE pr'), iface.messages[-2:]
print('Earth Engine data, trends:', res['rows'][0]['slope'], '| map:', new[0].name())

# a fixed image: only its map, as the elevation (no period, metrics, series, trends nor comparisons)
dock.asset_id.setText('WORLDCLIM/V1/BIO')
dock.asset_edited()  # as written by hand
dock.read_asset()
wait(dock)
read = dock.described()
assert read and read['type'] == 'image' and dock.asset_use.currentData() == 'image', iface.messages[-2:]
assert not dock.asset_use.isEnabled()  # an image is never a collection
assert 'use it as Fixed image (image)' in dock.asset_label.text(), dock.asset_label.text()  # the words of the panel
dock.asset_band.setCurrentIndex(dock.asset_band.findText('bio01'))
dock.band_scale.setText('0.1')
dock.asset_unit.setText('degC')
assert not dock.series_box.isEnabled() and not dock.trends_box.isEnabled() and not dock.export_series_button.isEnabled()
assert not dock.compare_on.isEnabled() and not dock.map_metric.isEnabled() and not dock.start.isEnabled()
args = dock.variable_args()  # no dates (and the offset of its record, if it gives one: 0)
assert args.pop('band_offset', 0) == 0 and args == {'image': 'WORLDCLIM/V1/BIO', 'band': 'bio01', 'band_scale': 0.1,
                                                    'unit': 'degC'}, args
before = set(QgsProject.instance().mapLayers())
dock.run_map()
wait(dock)
new = [l for k, l in QgsProject.instance().mapLayers().items() if k not in before]
assert len(new) == 1 and new[0].bandCount() == 1, iface.messages[-2:]
abstract = new[0].serverProperties().abstract()
assert new[0].name() == 'WORLDCLIM/V1/BIO bio01' and 'degC' in abstract and 'References' in abstract, \
	(new[0].name(), abstract)
print('Earth Engine image:', new[0].name(), '|', abstract.split('. ')[0])
# a band that it does not have, and an ID that cannot be read: clear errors (that of the ID also under the options)
dock.asset_band.setEditText('bio99')
try:
	dock.variable_args()
	raise AssertionError('a band that the image does not have')
except ValueError as e:
	assert 'has no band bio99' in str(e), e
dock.asset_band.setEditText('bio01')
dock.asset_id.setText('NOT/AN/ASSET')
dock.asset_edited()
dock.read_asset()
wait(dock)
assert dock.described() is None and 'could not be read' in dock.asset_label.text(), dock.asset_label.text()

# the GEE Community Catalog: its themes and their datasets from the copy of its index (no Earth Engine); a choice
# fills the ID and reads it
dock.theme.setCurrentIndex(dock.theme.findData('community'))
assert dock.community_row.isVisibleTo(dock) and dock.data_row.isVisibleTo(dock)
themes = [dock.community_theme.itemData(i) for i in range(dock.community_theme.count())]
assert len(themes) == len(services.community_themes()) and 'Elevation and Bathymetry' in themes, themes
dock.community_theme.setCurrentIndex(themes.index('Elevation and Bathymetry'))
ids = [dock.community_dataset.itemData(i) for i in range(dock.community_dataset.count())]
assert dock.community_dataset.currentIndex() == -1 and 'projects/sat-io/open-datasets/FABDEM' in ids, ids
dock.dataset_chosen(ids.index('projects/sat-io/open-datasets/FABDEM'))  # as a choice of the user (activated)
assert dock.asset_id.text() == 'projects/sat-io/open-datasets/FABDEM' and 'GEE Community Catalog' in \
       dock.asset_label.text()
wait(dock)
read = dock.described()
assert read and read['source'] == 'GEE Community Catalog' and read['bands'], iface.messages[-2:]
assert dock.asset_use.currentData() == read['use'] and 'Roy' in variable_help_text(dock)
dock.asset_use.setCurrentIndex(dock.asset_use.findData('image'))  # the mosaic of its tiles
dock.asset_unit.setText('m')
canvas.setExtent(QgsRectangle(-3.40, 37.00, -3.30, 37.08))
before = set(QgsProject.instance().mapLayers())
dock.run_map()
wait(dock)
new = [l for k, l in QgsProject.instance().mapLayers().items() if k not in before]
assert len(new) == 1 and new[0].name().startswith('projects/sat-io/open-datasets/FABDEM'), iface.messages[-2:]
assert 'Roy' in new[0].serverProperties().abstract()  # the community catalog is cited with its datasets
print('GEE Community Catalog:', new[0].name(), '| pixels of', new[0].rasterUnitsPerPixelX())
dock.theme.setCurrentIndex(dock.theme.findData('vegetation'))  # back to the catalog: its variable again
assert dock.variable_field.isVisibleTo(dock) and not dock.data_row.isVisibleTo(dock)
assert dock.variable.currentData().get('variable') and dock.filters['clouds'].isEnabled()

print('messages:', iface.messages)
plugin.unload()
# the project no longer calls the deleted panel (it did when the plugin was reloaded)
QgsProject.instance().removeAllMapLayers()
print('OK')
