"""Test of the perimeter of the burned area in the QGIS plugin without Earth Engine, with the Python of QGIS (offscreen,
seconds):

    PYTHONNOUSERSITE=1 PYTHONPATH=src <python of QGIS> qgis/test_perimeter_offline.py

(macOS: /Applications/QGIS-final-4_0_3.app/Contents/MacOS/python, with QGIS_APP for another QGIS). services.burn_severity
is faked (a small GeoTIFF, its CSV and the GeoPackage of the perimeter written with monitoreo.areas, as the services do
it): it checks the options of the perimeter in the group of the burn severity (the hint of the value from which a pixel
is burned for each index, greyed out without the perimeter, the RBR without a value refused), the arguments sent, the
layer of polygons over the severity, the window of the result (its hectares and Save perimeter…) and the layer chosen
as the region of the next analysis. qgis/test_plugin.py runs the plugin with Earth Engine.
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
from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsProject, QgsRectangle,  # noqa: E402
                       QgsVectorLayer, QgsWkbTypes)
from qgis.gui import QgsMapCanvas, QgsMessageBar  # noqa: E402
from qgis.PyQt.QtWidgets import QLabel, QMainWindow, QPushButton  # noqa: E402

gdal.UseExceptions()
app = QgsApplication([], True)
QgsApplication.setPrefixPath(os.path.join(APP, 'Contents', 'MacOS'), True)
if os.path.isdir(os.path.join(APP, 'Contents', 'PlugIns', 'qgis')):
	QgsApplication.setPluginPath(os.path.join(APP, 'Contents', 'PlugIns', 'qgis'))
app.initQgis()


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
from monitoreo import areas, fire, services  # noqa: E402

calls = []
SQUARE = {'type': 'MultiPolygon', 'coordinates': [[[[-3.60, 36.87], [-3.55, 36.87], [-3.55, 36.90], [-3.60, 36.90],
                                                    [-3.60, 36.87]]]]}


def burn_severity(region, sensor, start, end, other_start, other_end, perimeter=None, burned_min=None, min_ha=None,
                  path=None, csv=None, index='dNBR', **kw):
	"""As services.burn_severity: the GeoTIFF of the dNBR, its CSV and, with PERIMETER, its polygons."""
	calls.append(dict(kw, region=region, perimeter=perimeter, burned_min=burned_min, min_ha=min_ha, index=index))
	bands = ['dnbr', 'severity', 'nbr_before', 'nbr_after']
	ds = gdal.GetDriverByName('GTiff').Create(path, 20, 10, len(bands), gdal.GDT_Float32)
	ds.SetGeoTransform([500000, 10, 0, 4100000, 0, -10])
	srs = osr.SpatialReference()
	srs.ImportFromEPSG(32630)
	ds.SetProjection(srs.ExportToWkt())
	for i, name in enumerate(bands, 1):
		ds.GetRasterBand(i).SetNoDataValue(-9999)
		ds.GetRasterBand(i).SetDescription(name)
		ds.GetRasterBand(i).WriteArray(np.full((10, 20), 1.0 if name == 'severity' else 0.3, 'float32'))
	ds = None
	classes = fire.table([{'class': 1, 'sum': 1500.0}], 'extent')
	out = {'index': 'dNBR', 'classes': classes, 'burned_ha': {'extent': 1500.0}, 'scale': 10.0, 'csv': None,
	       'file': path, 'bands': bands, 'resolution': 10.0, 'native_resolution': 10.0, 'references': [],
	       'credits': [], 'title': f'Burn severity (dNBR, USGS) {sensor} (median) | before {start} / {end}, after '
	                              f'{other_start} / {other_end}'}
	if perimeter:
		low = fire.burned_min(index, burned_min)
		areas.save_polygons([{'region': 'extent', 'ha': 1480.5, 'patches': 3, 'geometry': SQUARE, 'index': index,
		                      'burned_min': low, 'min_ha': min_ha}], perimeter, 'perimeter', fire.PERIMETER_TYPES)
		out.update(perimeter=perimeter, perimeter_ha={'extent': 1480.5}, perimeter_patches={'extent': 3},
		           burned_min=low, min_ha=min_ha)
	return out


def eecu_usage(*args, **kw):
	raise RuntimeError('offline')


services.init = lambda *args, **kw: 'project'
services.eecu_usage = eecu_usage
services.burn_severity = burn_severity

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


wait()
dock.theme.setCurrentIndex(dock.theme.findData('fire'))
assert dock.fire_box.isVisibleTo(dock.fire_box.parentWidget())

# the options of the perimeter: on by default, the value of the classes of each index as hint, the RBR without one
dock.fire_perimeter.setChecked(True)
dock.fire_index.setCurrentIndex(dock.fire_index.findData('dNBR'))
assert dock.fire_burned_min.placeholderText() == 'dNBR 0.1' and dock.fire_burned_min.isEnabled()
assert dock.fire_min_ha.value() == fire.PERIMETER_MIN_HA
dock.fire_index.setCurrentIndex(dock.fire_index.findData('RdNBR'))
assert dock.fire_burned_min.placeholderText() == 'RdNBR 0.069'
dock.fire_index.setCurrentIndex(dock.fire_index.findData('RBR'))
assert dock.fire_burned_min.placeholderText() == 'write the RBR, e.g. 0.1'
dock.fire_perimeter.setChecked(False)
assert not dock.fire_burned_min.isEnabled() and not dock.fire_min_ha.isEnabled()
dock.fire_perimeter.setChecked(True)
print('options:', dock.fire_burned_min.placeholderText())

dock.region_kind.setCurrentIndex(dock.region_kind.findData('extent'))
iface.canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
iface.canvas.setExtent(QgsRectangle(-3.62, 36.86, -3.50, 36.93))
# the RBR without the value from which a pixel is burned: refused, nothing computed
dock.fire_burned_min.setText('')
dock.run_burn()
wait()
assert not calls and messages[-1].startswith('Warning: The RBR has no classes: write in Burned from'), messages[-1]
dock.fire_burned_min.setText('abc')
dock.run_burn()
assert not calls and messages[-1].startswith('Warning: Burned from: write a number'), messages[-1]

# the dNBR from 0.27 (with a comma), patches of 2 ha: the arguments, the layer of polygons and the window
dock.fire_index.setCurrentIndex(dock.fire_index.findData('dNBR'))
dock.fire_burned_min.setText('0,27')
dock.fire_min_ha.setValue(2)
before = set(QgsProject.instance().mapLayers())
dock.run_burn()
wait()
call = calls[-1]
assert call['perimeter'].endswith('burn_severity_perimeter.gpkg') and call['burned_min'] == 0.27, call
assert call['min_ha'] == 2.0 and call['index'] == 'dNBR'
added = [QgsProject.instance().mapLayer(i) for i in set(QgsProject.instance().mapLayers()) - before]
vectors = [x for x in added if isinstance(x, QgsVectorLayer)]
assert len(added) == 2 and len(vectors) == 1, [x.name() for x in added]
outline = vectors[0]
assert outline.isValid() and outline.name().endswith(' · perimeter') and outline.featureCount() == 1
assert QgsWkbTypes.geometryType(outline.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry
assert outline.renderer().symbol().color().alpha() == 0  # only its outline, over the severity
about = outline.serverProperties().abstract()
assert 'dNBR ≥ 0.27' in about and 'less than 2 ha' in about
assert any(m.startswith('Success: Layer added: ') and m.endswith('Choose it in Region → Layer to analyse inside it')
           for m in messages), messages[-3:]
dlg = dock.series_dialogs[max(dock.series_dialogs)]
texts = ' '.join(w.text() for w in dlg.findChildren(QLabel))
assert 'perimeter of the burned area (dNBR ≥ 0.27, without patches nor islands of less than 2 ha): 1,480.5 ha' in \
	texts, texts
assert 'Save perimeter…' in [b.text() for b in dlg.findChildren(QPushButton)]
print('perimeter:', outline.name(), outline.featureCount())

# the layer of the perimeter as the region of the next analysis
dock.region_kind.setCurrentIndex(dock.region_kind.findData('layer'))
dock.layer.setLayer(outline)
region = dock.region()
assert len(region['geojson']['features']) == 1
assert region['geojson']['features'][0]['geometry']['type'] in ('MultiPolygon', 'Polygon')
print('region:', region['geojson']['features'][0]['geometry']['type'])

# without the perimeter: no polygons
dock.fire_perimeter.setChecked(False)
dock.region_kind.setCurrentIndex(dock.region_kind.findData('extent'))
n = len(QgsProject.instance().mapLayers())
dock.run_burn()
wait()
assert calls[-1]['perimeter'] is None and calls[-1]['burned_min'] is None and calls[-1]['min_ha'] is None
assert len(QgsProject.instance().mapLayers()) == n + 1  # only the severity
plugin.unload()
QgsProject.instance().removeAllMapLayers()
print('OK')
