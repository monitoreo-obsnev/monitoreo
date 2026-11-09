"""Test of the QGIS plugin without its window (offscreen), with the Python of QGIS:

    EE_PROJECT=<project> <python of QGIS> qgis/test_plugin.py

(macOS: /Applications/QGIS-final-4_0_3.app/Contents/MacOS/python, with QGIS_APP for another QGIS). It
loads the plugin as QGIS does, opens its panel, checks the help of its buttons ⓘ and runs a search of protected
areas, a map layer, two time series (map extent, and a layer with two polygons) with the maps of two of their dates,
trends with their map, a comparison of periods and the burn severity of a fire (dNBR and RBR, only in the theme Fire),
waiting for their QGIS tasks.
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
print('themes:', [dock.theme.itemText(i) for i in range(dock.theme.count())], '| variables of',
      dock.theme.currentText() + ':', dock.variable.count(), '| selected:', dock.variable.currentText())
assert dock.theme.currentData() == 'vegetation' and dock.variable.currentText().startswith('NDVI · Sentinel-2')
links = dock.feedback_links
assert links['issue'].startswith('https://github.com/monitoreo-obsnev/monitoreo/issues/new/choose?tool=QGIS+plugin')
assert 'entry.1706228456=Complemento+de+QGIS' in links['form'], links
print('feedback:', links['issue'])
dock.theme.setCurrentIndex(dock.theme.findData('climate'))
assert all(dock.variable.itemData(i)['variable'] in ('PRECIP', 'TMEAN', 'TMIN', 'TMAX', 'PET', 'AET', 'CWD', 'SOILM',
                                                     'VPD') or dock.variable.itemData(i)['variable'].startswith('BIO')
           for i in range(dock.variable.count()))
dock.theme.setCurrentIndex(dock.theme.count() - 1)  # all the variables, for the help of each one
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


def add_from_window(res, index=0, significant=False):
	"""Add the map INDEX of res['maps'] with the button of the window of the result RES; the layers of its group."""
	dlg = dock.series_dialogs[dock.series.index(res)]
	dlg.findChild(QComboBox).setCurrentIndex(index)
	if significant:
		dlg.findChild(QCheckBox).setChecked(True)
	next(b for b in dlg.findChildren(QPushButton) if b.text() == 'Add to the map').click()
	wait(dock)
	group = QgsProject.instance().layerTreeRoot().findGroup(res['label'])
	assert group is not None, iface.messages[-3:]
	return [n.layer() for n in group.findLayers()]


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

# burn severity of a fire, only in the theme Fire (as in the Earth Engine app): the classes of the USGS (dNBR) and the
# RBR over a part of the fire of Sierra Bermeja (September 2021), their layers coloured as in the other tools
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
for index in ('dNBR', 'RBR'):
	dock.fire_index.setCurrentIndex(dock.fire_index.findData(index))
	before = set(QgsProject.instance().mapLayers())
	dock.run_burn()
	wait(dock)
	new = [l for k, l in QgsProject.instance().mapLayers().items() if k not in before]
	assert len(new) == 1 and new[0].bandCount() == 4, iface.messages[-2:]
	res = dock.series[-1]
	assert res['kind'] == 'burn' and res['index'] == index and res['readme'], res
	r = new[0].renderer()
	band = r.inputBand() if hasattr(r, 'inputBand') else r.band()
	if index == 'dNBR':
		assert r.type() == 'paletted' and band == 2, (r.type(), band)  # the band severity
		assert [c.color.name() for c in r.classes()] == [c['color'] for c in fire.legend()]
		assert [c.value for c in r.classes()] == [c['value'] for c in fire.legend()]
		burned = sum(res['burned_ha'].values())
		assert burned > 0, res['classes']
		print('burn severity:', new[0].name(), '| burned', round(burned), 'ha |',
		      [(c['class'], round(c['ha'])) for c in res['classes']])
	else:
		items = r.shader().rasterShaderFunction().colorRampItemList()
		assert r.type() == 'singlebandpseudocolor' and band == 1, (r.type(), band)  # the band rbr
		assert (r.classificationMin(), r.classificationMax()) == fire.RBR_RANGE
		assert items[0].color.name() == '#' + trends.DIVERGING[-1] and items[-1].color.name() == '#' + trends.DIVERGING[0]
		print('RBR:', new[0].name(), '|', {k: round(v, 3) for k, v in res['stats'][0].items() if k != 'region'})
dock.show_series_button.click()  # the window of the last one

print('messages:', iface.messages)
plugin.unload()
# the project no longer calls the deleted panel (it did when the plugin was reloaded)
QgsProject.instance().removeAllMapLayers()
print('OK')
