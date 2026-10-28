"""Test of the QGIS plugin without its window (offscreen), with the Python of QGIS:

    EE_PROJECT=<project> <python of QGIS> qgis/test_plugin.py

(macOS: /Applications/QGIS-LTR.app/Contents/MacOS/bin/python3.9, with QGIS_APP=/Applications/QGIS-LTR.app). It
loads the plugin as QGIS does, opens its panel and runs a search of protected areas, a map layer and two time series
(map extent, and a layer with two polygons), waiting for their QGIS tasks.
"""

import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
APP = os.environ.get('QGIS_APP', '/Applications/QGIS-LTR.app')
for proj in ('Contents/Resources/proj', 'Contents/Resources/qgis/proj'):
	if os.path.exists(os.path.join(APP, proj, 'proj.db')):
		os.environ.setdefault('PROJ_DATA', os.path.join(APP, proj))
		os.environ.setdefault('PROJ_LIB', os.path.join(APP, proj))
sys.path.insert(0, os.path.join(APP, 'Contents', 'Resources', 'python'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsFeature, QgsField, QgsGeometry,  # noqa: E402
                       QgsProject, QgsRectangle, QgsVectorLayer)
from qgis.gui import QgsMapCanvas, QgsMessageBar  # noqa: E402
from qgis.PyQt.QtCore import QVariant  # noqa: E402
from qgis.PyQt.QtWidgets import QMainWindow  # noqa: E402

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
print('variables:', dock.variable.count(), '| selected:', dock.variable.currentText())

# protected areas
dock.region_kind.setCurrentIndex([dock.region_kind.itemData(i) for i in range(dock.region_kind.count())].index('wdpa'))
dock.wdpa_text.setText('Sierra Nevada')
dock.search_wdpa()
wait(dock)
print('WDPA:', dock.wdpa.count(), 'areas, first:', dock.wdpa.itemText(0))

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
chart = dock.series_dialogs[len(dock.series) - 1].chart
if chart is not None and os.environ.get('TEST_OUT'):  # chart drawn with Qt (no matplotlib)
	chart.resize(860, 360)
	chart.grab().save(os.path.join(os.environ['TEST_OUT'], 'qt_chart.png'), 'PNG')
	print('Qt chart saved')

# time series over a layer with two polygons, in UTM
lyr = QgsVectorLayer('Polygon?crs=EPSG:25830', 'zonas', 'memory')
lyr.dataProvider().addAttributes([QgsField('zona', QVariant.String)])  # (deprecated in QGIS 4, still works)
lyr.updateFields()
for name, x0 in (('oeste', 445000), ('este', 450000)):
	f = QgsFeature(lyr.fields())
	f.setGeometry(QgsGeometry.fromRect(QgsRectangle(x0, 4079000, x0 + 4000, 4084000)))
	f['zona'] = name
	lyr.dataProvider().addFeature(f)
QgsProject.instance().addMapLayer(lyr)
dock.region_kind.setCurrentIndex(0)
dock.layer.setLayer(lyr)
dock.name_field.setField('zona')
dock.step.setCurrentIndex([dock.step.itemData(i) for i in range(dock.step.count())].index('annual'))
dock.run_series()
wait(dock)
res = dock.series[-1]
print('series (layer):', [(r['region'], r['date'], round(r['value'], 3)) for r in res['rows']])
assert sorted(res['regions']) == ['este', 'oeste']

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

print('messages:', iface.messages)
plugin.unload()
# the project no longer calls the deleted panel (it did when the plugin was reloaded)
QgsProject.instance().removeAllMapLayers()
print('OK')
