"""Test of the true colour (RGB) in the QGIS plugin without Earth Engine, with the Python of QGIS (offscreen, seconds):

    PYTHONNOUSERSITE=1 PYTHONPATH=src <python of QGIS> qgis/test_rgb_offline.py

(macOS: /Applications/QGIS-final-4_0_3.app/Contents/MacOS/python, with QGIS_APP for another QGIS; earthengine-api
comes from the ext/ of the plugin, made by build_plugin.py, or from PYTHONPATH). The map services are faked (small
GeoTIFFs made with GDAL, and tiles that are never read): it checks the list Layer of the group Map (greyed out without
true colour, for the fixed layers and with Compare with), the map and its true colour (Both) on the same grid, the
window of a time series with the list Layer and its layers (the true colour under the index, with the same days in the
Temporal Controller and the stretch of the first true colour of the series), the tiles when the GeoTIFF cannot be
downloaded and the warning when only the true colour fails. qgis/test_plugin.py does it with Earth Engine.
"""

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

import numpy as np  # noqa: E402
from osgeo import gdal, osr  # noqa: E402
from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsProject, QgsRasterLayer,  # noqa: E402
                       QgsRectangle)
from qgis.gui import QgsMapCanvas, QgsMessageBar  # noqa: E402
from qgis.PyQt.QtCore import Qt  # noqa: E402
from qgis.PyQt.QtWidgets import QComboBox, QMainWindow, QPushButton  # noqa: E402

gdal.UseExceptions()
app = QgsApplication([], True)
QgsApplication.setPrefixPath(os.path.join(APP, 'Contents', 'MacOS'), True)
if os.path.isdir(os.path.join(APP, 'Contents', 'PlugIns', 'qgis')):
	QgsApplication.setPluginPath(os.path.join(APP, 'Contents', 'PlugIns', 'qgis'))
app.initQgis()
TMP = tempfile.mkdtemp(prefix='monitoreo_test_')


class Iface:
	def __init__(self):
		self.window = QMainWindow()
		self.canvas = QgsMapCanvas()
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
from monitoreo import services  # noqa: E402

calls = []   # (service, arguments)
fail = set()  # the services that fail


def tif(path, bands, res, value):
	"""A GeoTIFF of 20 x 10 pixels of RES m with BANDS (float32, NoData -9999), as those of the services."""
	ds = gdal.GetDriverByName('GTiff').Create(path, 20, 10, len(bands), gdal.GDT_Float32)
	ds.SetGeoTransform([500000, res, 0, 4100000, 0, -res])
	srs = osr.SpatialReference()
	srs.ImportFromEPSG(25830)
	ds.SetProjection(srs.ExportToWkt())
	for i, name in enumerate(bands, 1):
		band = ds.GetRasterBand(i)
		band.SetNoDataValue(-9999)
		band.SetDescription(name)
		band.WriteArray((value * i + np.arange(200).reshape(10, 20) / 1000).astype('float32'))
	ds = None


def name(opts, rgb=False):
	return f"NDVI Sentinel-2 | {opts['start']} / {opts['end']} ({opts['metric']})" + (', true colour' if rgb else '')


def download_image(region, path=None, max_pixels=None, **opts):
	calls.append(('download_image', opts))
	if 'download_image' in fail:
		raise RuntimeError('download_image failed')
	tif(path, ['value'], 30.0, 0.5)  # a big region: pixels of 30 m
	return {'file': path, 'resolution': 30.0, 'native_resolution': 10.0, 'images': 5, 'name': name(opts),
	        'unit': '[unitless]', 'min': 0.1 + 0.01 * len(calls), 'max': 0.9, 'palette': ['000000', 'FFFFFF']}


def download_rgb(region, path=None, resolution=None, max_pixels=None, **opts):
	calls.append(('download_rgb', dict(opts, resolution=resolution)))
	if 'download_rgb' in fail:
		raise RuntimeError('download_rgb failed')
	tif(path, ['red', 'green', 'blue'], resolution or 10.0, 0.05)
	return {'file': path, 'resolution': resolution or 10.0, 'native_resolution': 10.0, 'images': 5,
	        'name': name(opts, True), 'unit': '[unitless]', 'bands': ['red', 'green', 'blue'],
	        'min': 0.01 * len(calls), 'max': 0.25}


def rgb_map(region, vmin=None, vmax=None, **opts):
	calls.append(('rgb_map', dict(opts, vmin=vmin, vmax=vmax)))
	if 'rgb_map' in fail:
		raise ValueError('rgb_map failed')
	return {'url': 'https://tiles.invalid/{z}/{x}/{y}', 'bands': ['red', 'green', 'blue'],
	        'min': 0.0 if vmin is None else vmin, 'max': 0.3 if vmax is None else vmax, 'name': name(opts, True),
	        'unit': '[unitless]', 'bounds': [-3.6, 37.0, -3.5, 37.1], 'thumbnail': None}


def eecu_usage(*args, **kw):
	raise RuntimeError('offline')


services.init = lambda *args, **kw: 'project'
services.eecu_usage = eecu_usage
services.download_image = download_image
services.download_rgb = download_rgb
services.rgb_map = rgb_map

iface = Iface()
plugin = monitoreo_qgis.classFactory(iface)
plugin.initGui()
plugin.toggle(True)
dock = plugin.dock
messages = []
_message = dock.message
dock.message = lambda text, lvl='Info', duration=6: (messages.append(f'{lvl}: {text}'), _message(text, lvl, duration))


def wait(timeout=60):
	t0 = time.time()
	app.processEvents()
	while dock.tasks and time.time() - t0 < timeout:
		app.processEvents()
		time.sleep(0.05)
	assert not dock.tasks, 'tasks did not finish'


def days(layer):
	t = layer.temporalProperties().fixedTemporalRange()
	return layer.temporalProperties().isActive(), t.begin().toString('yyyy-MM-dd'), t.end().toString('yyyy-MM-dd')


def stretch(layer):
	"""(min, max) of the three bands of a true colour, the same for the three."""
	r = layer.renderer()
	assert r.type() == 'multibandcolor' and (r.redBand(), r.greenBand(), r.blueBand()) == (1, 2, 3), r.type()
	ranges = {(e.minimumValue(), e.maximumValue()) for e in (r.redContrastEnhancement(), r.greenContrastEnhancement(),
	                                                          r.blueContrastEnhancement())}
	assert len(ranges) == 1, ranges
	return ranges.pop()


wait()
dock.theme.setCurrentIndex(dock.theme.count() - 1)  # all the variables

# the list Layer of the group Map: greyed out at Index, with the reason, without true colour
kind = dock.map_kind
assert [kind.itemText(i) for i in range(kind.count())] == ['Index', 'True colour (RGB)', 'Both']
metric = dock.map_metric.currentIndex()
for text, enabled in (('NDVI · Modis · 250 m · MOD13Q1', False), ('ELEVATION · Copernicus', False),
                      ('PRECIP · ERA5-Land', False), ('CF · Modis · 1000 m · MOD09GA', True),
                      ('NDVI · Landsat', True), ('NDVI · Sentinel-2', True)):
	if kind.isEnabled():
		kind.setCurrentIndex(kind.findData('both'))
	dock.variable.setCurrentIndex(dock.variable.findText(text, Qt.MatchFlag.MatchStartsWith))
	assert dock.variable.currentText().startswith(text), text
	assert kind.isEnabled() == enabled, (text, kind.toolTip())
	assert enabled or (kind.currentData() == 'index' and 'true colour' in kind.toolTip()), (text, kind.toolTip())
dock.map_metric.setCurrentIndex(metric)  # (the CF fixes the metric)
kind.setCurrentIndex(kind.findData('both'))
dock.compare_on.setChecked(True)
assert not kind.isEnabled() and kind.currentData() == 'index' and 'Compare with' in kind.toolTip()
dock.compare_on.setChecked(False)
assert kind.isEnabled()
print('list Layer of the map:', kind.toolTip())

# the map and its true colour (Both), with the same arguments and the pixels of the map: the true colour under it
dock.region_kind.setCurrentIndex(dock.region_kind.findData('extent'))
iface.canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
iface.canvas.setExtent(QgsRectangle(-3.62, 36.86, -3.50, 36.93))
dock.where[0]['on'].setChecked(True)
dock.where[0]['min'].setText('800')
kind.setCurrentIndex(kind.findData('both'))
calls.clear()
before = set(QgsProject.instance().mapLayers())
dock.run_map()
wait()
assert [c[0] for c in calls] == ['download_image', 'download_rgb'], calls
index_opts, rgb_opts = calls[0][1], dict(calls[1][1])
assert rgb_opts.pop('resolution') == 30.0 and rgb_opts == index_opts and index_opts['where'][0]['min'] == 800.0
assert index_opts['metric'] == dock.map_metric.currentData() and index_opts['temporal'] == 'period'
new = [n.layer() for n in QgsProject.instance().layerTreeRoot().findLayers() if n.layer().id() not in before]
assert len(new) == 2, messages[-3:]
top, under = new
assert top.renderer().type() == 'singlebandpseudocolor' and under.name().endswith(', true colour')
assert stretch(under) == (0.02, 0.25) and (under.width(), under.height()) == (top.width(), top.height())
assert 'True colour (red, green, blue): reflectance from 0.02 to 0.25' in under.serverProperties().abstract()
print('map and true colour:', [layer.name() for layer in new])
dock.where[0]['on'].setChecked(False)
kind.setCurrentIndex(kind.findData('index'))

# a time series (faked) and its window: the list Layer beside Map of
from monitoreo_qgis.dock import result_maps  # noqa: E402
from monitoreo_qgis.results import ResultDialog, SeriesDialog  # noqa: E402
where = [{'variable': 'NDVI', 'sensor': 'Sentinel-2', 'collection': 'COPERNICUS/S2_SR_HARMONIZED', 'min': 0.2,
          'period': ['2021-01-01', '2021-12-31']}]
args = {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'collection': 'COPERNICUS/S2_SR_HARMONIZED', 'start': '2021-01-01',
        'end': '2021-12-31', 'quality': {'clouds': True, 'cloud_score': 0.6}, 'where': where,
        'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'step': 'monthly', 'metric': 'mean'}
res = {'kind': 'series', 'title': 'NDVI Sentinel-2 | 2021-01-01 / 2021-12-31 (mean)', 'unit': '[unitless]',
       'scale': 10.0, 'regions': ['bbox'], 'chart': None, 'args': args, 'label': 'NDVI Sentinel-2 · bbox',
       'rows': [{'region': 'bbox', 'date': f'2021-{m:02d}-01', 'value': 0.3 + m / 100, 'n_pixels': 10, 'n_images': 3}
                for m in range(1, 13)],
       'maps': result_maps('time_series', args), 'rgb': services.has_rgb('NDVI', 'Sentinel-2')}
assert res['rgb'] is True
dock.add_result(res)
dlg = dock.series_dialogs[dock.series.index(res)]
choice, layer_kind = dlg.findChild(QComboBox, 'map_choice'), dlg.findChild(QComboBox, 'map_kind')
assert [layer_kind.itemText(i) for i in range(layer_kind.count())] == ['Index', 'True colour (RGB)', 'Both']
assert layer_kind.currentData() == 'index' and 'percentiles 2 and 98' in layer_kind.toolTip()
print('window of the series:', layer_kind.toolTip())


def add(index, value):
	"""Add the map INDEX of the series with the layer VALUE of the list Layer; the layers of its group."""
	choice.setCurrentIndex(index)
	layer_kind.setCurrentIndex(layer_kind.findData(value))
	next(b for b in dlg.findChildren(QPushButton) if b.text() == 'Add to the map').click()
	wait()
	return [n.layer() for n in QgsProject.instance().layerTreeRoot().findGroup(res['label']).findLayers()]


calls.clear()
june = add(6, 'rgb')[0]  # the first true colour of the series: its stretch is kept
assert [c[0] for c in calls] == ['download_rgb'] and calls[0][1]['where'] == where and calls[0][1]['resolution'] is None
assert (calls[0][1]['start'], calls[0][1]['end'], calls[0][1]['metric']) == ('2021-06-01', '2021-06-30', 'mean')
assert june.name() == 'NDVI Sentinel-2 · Jun 2021 · true colour' and days(june) == (True, '2021-06-01', '2021-07-01')
kept = res['rgb_stretch']
assert stretch(june) == kept
calls.clear()
july, july_rgb = add(7, 'both')[:2]  # the index on top of its true colour, the same days, the stretch of June
assert [c[0] for c in calls] == ['download_image', 'download_rgb'], calls
rgb_opts = dict(calls[1][1])
assert rgb_opts.pop('resolution') == 30.0 and rgb_opts == calls[0][1] and calls[0][1]['where'] == where
assert july.renderer().type() == 'singlebandpseudocolor' and stretch(july_rgb) == kept
assert days(july) == days(july_rgb) == (True, '2021-07-01', '2021-08-01')
whole, whole_rgb = add(0, 'both')[:2]  # the whole period: no days in the Temporal Controller
assert not whole.temporalProperties().isActive() and not whole_rgb.temporalProperties().isActive()
print('maps of the series:', [layer.name() for layer in (june, july, july_rgb)], '| stretch', kept)

# the true colour cannot be downloaded: its tiles, with the stretch of the series and the same days
calls.clear()
fail.add('download_rgb')
august = add(8, 'rgb')[0]
assert [c[0] for c in calls] == ['download_rgb', 'rgb_map'] and (calls[1][1]['vmin'], calls[1][1]['vmax']) == kept
assert august.providerType() == 'wms' and days(august) == (True, '2021-08-01', '2021-09-01')
assert 'True colour (red, green, blue): reflectance from' in august.serverProperties().abstract()
# only the true colour of Both fails: a warning, and the index all the same
fail.add('rgb_map')
n = len(add(8, 'index'))
layers = add(9, 'both')
assert len(layers) == n + 1 and layers[0].renderer().type() == 'singlebandpseudocolor'
assert any(m.startswith('Warning: True colour of NDVI Sentinel-2 · Sep 2021: rgb_map failed') for m in messages)
# the true colour alone fails: the message of the task, and no layer
assert len(add(10, 'rgb')) == len(layers) and messages[-1].startswith('Critical: True colour of NDVI Sentinel-2 · Oct')
fail.clear()
print('tiles and failures:', messages[-1])

# the windows of a series without true colour and of trends: no list Layer
assert SeriesDialog(dict(res, rgb=False), None, lambda *a: None).findChild(QComboBox, 'map_kind') is None
trends = {'kind': 'trends', 'title': 'trends', 'label': 'trends', 'unit': '[unitless]', 'scale': 10.0, 'rows': [],
          'rgb': True, 'maps': [{'key': '', 'label': 'Annual trend (2021)', 'step': 'annual'}]}
assert ResultDialog(trends, None, lambda *a: None).findChild(QComboBox, 'map_kind') is None

# rgb() on a GeoTIFF of three bands
from monitoreo_qgis.dock import rgb  # noqa: E402
path = os.path.join(TMP, 'three.tif')
tif(path, ['red', 'green', 'blue'], 10.0, 0.05)
layer = QgsRasterLayer(path, 'three')
rgb(layer, 0.02, 0.28)
assert stretch(layer) == (0.02, 0.28)
print('rgb():', layer.renderer().type(), [layer.bandName(i) for i in (1, 2, 3)])
plugin.unload()
QgsProject.instance().removeAllMapLayers()
print('OK')
