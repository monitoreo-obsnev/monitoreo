"""Test of the analyses of the QGIS plugin added after the review of geemap (animations, area by class), without
Earth Engine, with the Python of QGIS (offscreen, seconds):

    PYTHONNOUSERSITE=1 PYTHONPATH=src <python of QGIS> qgis/test_analyses_offline.py

(macOS: /Applications/QGIS-final-4_0_3.app/Contents/MacOS/python, with QGIS_APP for another QGIS). The Python of QGIS
has no Pillow: it checks that monitoreo.animation draws the texts of the frames with Qt and writes the GIF by itself
(write_gif), and QMovie plays it. services.timelapse is faked (a GIF of three frames): it checks the group Animation
(greyed out for the fixed layers without dates, its metric fixed for the snow cover frequency), the arguments sent,
and the window of the result, with the GIF playing, its frames and the button to save it with its README.
services.area_by_class is faked too: the group Area by class (its kinds of classes and their fields), the arguments of
each kind and the window of the result (its table, with the colour of each class).
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
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsRectangle  # noqa: E402
from qgis.gui import QgsMapCanvas, QgsMessageBar  # noqa: E402
from qgis.PyQt.QtCore import Qt  # noqa: E402
from qgis.PyQt.QtGui import QColor  # noqa: E402
from qgis.PyQt.QtWidgets import QMainWindow, QPushButton, QTableWidget  # noqa: E402

app = QgsApplication([], True)
QgsApplication.setPrefixPath(os.path.join(APP, 'Contents', 'MacOS'), True)
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
		pass

	def removeDockWidget(self, dock):
		pass

	def addToolBarIcon(self, action):
		pass

	def removeToolBarIcon(self, action):
		pass

	def addPluginToWebMenu(self, name, action):
		pass

	def removePluginWebMenu(self, name, action):
		pass

	def openLayoutDesigner(self, layout):
		self.opened = layout


import monitoreo_qgis  # noqa: E402
from monitoreo_qgis import deps  # noqa: E402

deps.setup_path()  # earthengine-api from the ext/ of the plugin (build_plugin.py), or from PYTHONPATH
from monitoreo import animation, services  # noqa: E402
from qgis.PyQt.QtGui import QMovie  # noqa: E402

# without Pillow: the texts with Qt, the GIF by monitoreo.animation
try:
	import PIL  # noqa: F401
	print('WARNING: this QGIS has Pillow: the way without it is not tested')
except ImportError:
	pictures = [np.full((120, 160, 3), c, np.uint8) for c in ((255, 0, 0), (0, 128, 0), (217, 217, 217))]
	gif = animation.write(pictures, os.path.join(TMP, 'qt.gif'), ['2021', '2022', '2023 · no images'], 'NDVI', 0.1,
	                      0.8, ['ff0000', '00ff00'], 'unit', 'MonitorEO; Google Earth Engine', fps=4)
	movie = QMovie(gif)
	assert movie.isValid() and movie.frameCount() == 3, movie.frameCount()
	movie.jumpToFrame(0)
	frame = movie.currentImage()
	big, small, top, bar, bottom = animation.layout(160)
	assert (frame.width(), frame.height()) == (160, top + 120 + bottom)
	assert QColor(frame.pixel(80, top + 50)).getRgb()[:3] == (255, 0, 0)  # the map, under its texts
	assert any(QColor(frame.pixel(x, y)).getRgb()[:3] != (255, 255, 255) for x in range(8, 60) for y in range(6, 20))
	print('GIF without Pillow:', movie.frameCount(), 'frames', frame.width(), 'x', frame.height())

calls = []


def timelapse(region, path=None, **opts):
	calls.append(dict(opts, region=region, path=path))
	frames = [np.full((40, 60, 3), c, np.uint8) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
	animation.write_gif(frames, path, 500)
	readme = os.path.splitext(path)[0] + '.README.txt'
	with open(readme, 'w') as f:
		f.write('README')
	return {'file': path, 'gif': path, 'readme': readme, 'n_frames': 3, 'fps': opts.get('fps', 2), 'step': 'annual',
	        'min': 0.1, 'max': 0.8, 'palette': ['ff0000', '00ff00'], 'unit': '[unitless]', 'name': 'NDVI Sentinel-2',
	        'frames': [{'date': f'{y}-01-01', 'end': f'{y + 1}-01-01', 'label': str(y), 'images': n}
	                   for y, n in ((2021, 12), (2022, 0), (2023, 9))],
	        'references': [{'citation': 'Wu, Q. (2020). geemap.', 'url': 'https://doi.org/10.21105/joss.02305'}],
	        'credits': ['Contains modified Copernicus Sentinel data 2021-2023']}


def eecu_usage(*args, **kw):
	raise RuntimeError('offline')


services.init = lambda *args, **kw: 'project'
services.eecu_usage = eecu_usage
services.timelapse = timelapse


def area_by_class(region, csv=None, **opts):
	calls.append(dict(opts, region=region, csv=csv, tool='area_by_class'))
	rows = [{'region': 'extent', 'class': c, 'label': label, 'ha': ha, 'percent': p}
	        for c, label, ha, p in ((-1, 'significant decrease', 10.0, 10.0), (0, 'no significant trend', 80.0, 80.0),
	                                (1, 'significant increase', 10.0, 10.0))]
	with open(csv, 'w') as f:
		f.write('region,class,label,ha,percent\n')
	return {'rows': rows, 'mode': 'trend', 'scale': 250.0, 'unit': '', 'title': 'Area of each class', 'csv': csv,
	        'classes': [{'class': r['class'], 'label': r['label'], 'colour': c}
	                    for r, c in zip(rows, ('d7191c', 'bdbdbd', '1a9641'))], 'references': [], 'credits': []}


services.area_by_class = area_by_class


def region_stats(region, csv=None, **opts):
	calls.append(dict(opts, region=region, tool='region_stats'))
	rows = [{'region': 'extent', 'zone': z, 'zone_label': label, 'p25': 0.2, 'p50': 0.3, 'p75': 0.4, 'mean': 0.3,
	         'n_pixels': 10} for z, label in ((0, 'below 1500 m'), (1, '1500 m or more'))]
	return {'rows': rows, 'stats': opts.get('stats'), 'scale': 250.0, 'unit': '[unitless]', 'ylabel': 'NDVI',
	        'title': 'NDVI by ELEVATION (Copernicus) bands', 'csv': csv, 'references': [], 'credits': []}


def transect(line, csv=None, **opts):
	calls.append(dict(opts, line=line, tool='transect'))
	rows = [{'distance_m': d, 'value': 0.3, 'elevation': 1000.0 + d, 'lon': -3.5, 'lat': 37.1} for d in (50.0, 150.0)]
	return {'rows': rows, 'length_m': 200.0, 'spacing': 100.0, 'scale': 10.0, 'unit': '[unitless]', 'ylabel': 'NDVI',
	        'title': 'NDVI along a line', 'csv': csv, 'references': [], 'credits': []}


services.region_stats = region_stats
services.transect = transect

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
dock.theme.setCurrentIndex(dock.theme.count() - 1)  # all the variables

# the group Animation: greyed out for the fixed layers, the only metric of the snow cover frequency
for text, enabled in (('ELEVATION · Copernicus', False), ('NDVI · Sentinel-2', True)):
	dock.variable.setCurrentIndex(dock.variable.findText(text, Qt.MatchFlag.MatchStartsWith))
	assert dock.variable.currentText().startswith(text), text
	assert dock.animation_box.isEnabled() == enabled, text
scf = dock.variable.findText('SCF · Landsat', Qt.MatchFlag.MatchStartsWith)
if scf >= 0:
	dock.variable.setCurrentIndex(scf)
	assert dock.anim_metric.currentData() == 'mean' and not dock.anim_metric.isEnabled()
dock.variable.setCurrentIndex(dock.variable.findText('NDVI · Sentinel-2', Qt.MatchFlag.MatchStartsWith))
assert [dock.anim_step.itemData(i) for i in range(dock.anim_step.count())] == ['annual', 'monthly', '16-day', 'daily']
print('group Animation:', [dock.anim_step.itemText(i) for i in range(dock.anim_step.count())])

# the animation: its arguments, and its window with the GIF playing, its frames and Save GIF…
dock.region_kind.setCurrentIndex(dock.region_kind.findData('extent'))
iface.canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
iface.canvas.setExtent(QgsRectangle(-3.45, 37.02, -3.30, 37.12))
dock.anim_step.setCurrentIndex(dock.anim_step.findData('monthly'))
dock.anim_metric.setCurrentIndex(dock.anim_metric.findData('max'))
dock.anim_fps.setValue(4)
dock.run_timelapse()
wait()
assert len(calls) == 1, messages[-3:]
sent = calls[0]
assert sent['step'] == 'monthly' and sent['metric'] == 'max' and sent['fps'] == 4 and sent['variable'] == 'NDVI'
assert sent['path'].endswith('.gif') and sent['region']
res = dock.series[-1]
assert res['kind'] == 'animation' and res['label'].startswith('Animation of NDVI')
dlg = dock.series_dialogs[dock.series.index(res)]
assert dlg.movie.isValid() and dlg.movie.frameCount() == 3, dlg.movie.frameCount()
table = dlg.findChild(QTableWidget)
assert table.rowCount() == 3 and table.item(1, 1).text() == '2022' and table.item(1, 3).text() == '0'
assert '1 frames without images (grey)' in dlg.findChildren(type(dlg.picture))[0].text()
buttons = [b.text() for b in dlg.findChildren(QPushButton)]
assert buttons == ['Save GIF…', 'Close'], buttons
from monitoreo_qgis.results import save_file  # noqa: E402
copy = os.path.join(TMP, 'copy.gif')
save_file(res['gif'], copy, res)
assert os.path.exists(copy) and os.path.exists(os.path.join(TMP, 'copy.README.txt'))
print('window of the animation:', dlg.windowTitle(), '| frames', dlg.movie.frameCount())

# Area by class: the fields of each kind, the arguments sent and the window
kinds = [dock.area_kind.itemData(i) for i in range(dock.area_kind.count())]
assert kinds == ['landcover', 'breaks', 'trend'], kinds
for kind, map_shown, breaks_shown in (('landcover', True, False), ('breaks', False, True), ('trend', False, False)):
	dock.area_kind.setCurrentIndex(dock.area_kind.findData(kind))
	assert dock.area_map_row.isVisibleTo(dock) == map_shown and dock.area_breaks.isVisibleTo(dock) == breaks_shown, kind
dock.area_map.setCurrentIndex(dock.area_map.findData('CORINE'))
assert dock.area_year.currentData() == 2018 and dock.area_year.findData(1990) >= 0
dock.area_kind.setCurrentIndex(dock.area_kind.findData('landcover'))
calls.clear()
dock.run_areas()
wait()
assert calls[-1]['landcover'] == 'CORINE' and calls[-1]['year'] == 2018 and 'variable' not in calls[-1], calls[-1]
assert 'other_year' not in calls[-1]
dock.area_change.setChecked(True)  # the changes of the map: from 2012 to 2018 by default
assert (dock.area_year.currentData(), dock.area_other_year.currentData()) == (2012, 2018)
dock.run_areas()
wait()
assert (calls[-1]['year'], calls[-1]['other_year']) == (2012, 2018), calls[-1]
dock.area_change.setChecked(False)
dock.area_kind.setCurrentIndex(dock.area_kind.findData('breaks'))
dock.area_breaks.setText('0.2, 0.4')
dock.run_areas()
wait()
assert calls[-1]['breaks'] == '0.2, 0.4' and calls[-1]['variable'] == 'NDVI', calls[-1]
assert calls[-1]['metric'] == dock.map_metric.currentData(), calls[-1]
dock.area_kind.setCurrentIndex(dock.area_kind.findData('trend'))
dock.run_areas()
wait()
assert calls[-1]['trend'] is True and calls[-1]['step'] == dock.trend_step.currentData(), calls[-1]
res = dock.series[-1]
assert res['kind'] == 'areas' and res['label'].startswith('Area by class: NDVI')
dlg = dock.series_dialogs[dock.series.index(res)]
table = dlg.findChild(QTableWidget)
headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
assert headers == ['Region', 'Class', 'Hectares', '% of the area with classes'], headers
assert table.rowCount() == 3 and not table.item(0, 1).icon().isNull()  # the colour of the class
print('window of the areas:', dlg.windowTitle(), headers)

# Gradients: the statistics of each elevation band, and the profile along the selected line of a layer
assert dock.zone_variable.currentText().startswith('ELEVATION · Copernicus')
dock.zone_breaks.setText('1500')
dock.run_zones()
wait()
z = calls[-1]
assert z['tool'] == 'region_stats' and z['zones'] == {'variable': 'ELEVATION', 'sensor': 'Copernicus', 'breaks': '1500'}
assert z['stats'] == ['p25', 'p50', 'p75', 'mean'] and z['variable'] == 'NDVI', z
dlg = dock.series_dialogs[len(dock.series) - 1]
table = dlg.findChild(QTableWidget)
assert [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())][:3] == ['Region', 'Band', 'Percentile 25']
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer  # noqa: E402
lines = QgsVectorLayer('LineString?crs=EPSG:4326', 'lines', 'memory')
f = QgsFeature()
f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(-3.60, 37.15), QgsPointXY(-3.45, 37.10)]))
lines.dataProvider().addFeatures([f])
QgsProject.instance().addMapLayer(lines)
dock.line_layer.setLayer(lines)
dock.run_transect()
wait()
t = calls[-1]
assert t['tool'] == 'transect' and t['line'] == [[-3.6, 37.15], [-3.45, 37.1]] and t['variable'] == 'NDVI', t
res = dock.series[-1]
assert res['kind'] == 'transect' and dock.series_dialogs[len(dock.series) - 1].findChild(QTableWidget).rowCount() == 2
print('gradients:', z['zones'], '| line', t['line'])
QgsProject.instance().removeMapLayer(lines.id())

# the figure: a print layout of the canvas with its map, grid, legend, scale bar, north arrow, title and credits
from qgis.core import QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemMap, QgsLayoutItemScaleBar  # noqa: E402
lines = QgsVectorLayer('LineString?crs=EPSG:4326', 'lines', 'memory')
lines.dataProvider().addFeatures([f])
QgsProject.instance().addMapLayer(lines)
dock.make_layout()
layout = iface.opened
items = layout.items()
assert layout.name().startswith('MonitorEO figure') and any(isinstance(i, QgsLayoutItemMap) for i in items)
assert any(isinstance(i, QgsLayoutItemLegend) for i in items) and any(isinstance(i, QgsLayoutItemScaleBar) for i in items)
texts = [i.text() for i in items if isinstance(i, QgsLayoutItemLabel)]
assert any('MonitorEO [Software]' in t for t in texts), texts
dock.make_layout()
assert iface.opened.name() == layout.name() + ' 2'  # a free name
print('figure:', layout.name(), len(items), 'items')

# whatever the shape of the canvas (tall, wide, of 2 km), the map of the layout keeps its 205 x 160 mm with all the
# canvas in it, the scale bar on it and the credits under it in the page; the labels of its grid have the decimals of
# its step; and the credits are all those of the data of the layers (USGS, FAO GAUL...), not only those of Copernicus
from monitoreo import references  # noqa: E402
from monitoreo_qgis.dock import figure_layout, references_text  # noqa: E402


class Canvas:
	"""A canvas of EXTENT in EPSG:4326."""

	def __init__(self, extent):
		self.box = extent

	def extent(self):
		return self.box

	def mapSettings(self):
		return self

	def destinationCrs(self):
		return QgsCoordinateReferenceSystem('EPSG:4326')


cited = references.cite('map_layer', {'region': {'admin1': 'Andalucía', 'country': 'ESP'}, 'variable': 'NDVI',
                                      'sensor': 'Landsat', 'start': '2020-01-01', 'end': '2020-12-31'})
assert len(cited['credits']) == 2 and not any(c.startswith('Contains') for c in cited['credits']), cited['credits']
lines.setAbstract('MonitorEO: NDVI (Landsat).' + references_text(cited))
for box, decimals in ((QgsRectangle(-3.5, 36.9, -3.4, 37.3), 2), (QgsRectangle(-4.0, 37.0, -2.5, 37.1), 2),
                      (QgsRectangle(-3.41, 37.09, -3.39, 37.11), 3)):
	items = figure_layout(Canvas(box)).items()
	m = next(i for i in items if isinstance(i, QgsLayoutItemMap))
	y, h = m.positionWithUnits().y(), m.sizeWithUnits().height()
	assert (round(m.sizeWithUnits().width()), round(h), round(y)) == (205, 160, 18), (box.toString(), y, h)
	assert m.extent().buffered(1e-9).contains(box), (m.extent().toString(), box.toString())
	assert m.grid().annotationPrecision() == decimals, (box.toString(), m.grid().intervalX())
	scale = next(i for i in items if isinstance(i, QgsLayoutItemScaleBar))
	assert y < scale.positionWithUnits().y() < y + h, scale.positionWithUnits().y()  # on the map
	note = next(i for i in items if isinstance(i, QgsLayoutItemLabel) and 'MonitorEO [Software]' in i.text())
	top = note.positionWithUnits().y()
	assert y + h <= top and top + note.sizeWithUnits().height() <= 210, top  # under the map, in the A4 page
	assert all(c in note.text().split('\n') for c in cited['credits']), note.text()
print('figure of a tall, a wide and a small canvas: the map 205 x 160 mm, credits', len(cited['credits']))
plugin.unload()
print('OK')
