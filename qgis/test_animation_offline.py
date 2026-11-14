"""Test of the animations (timelapses) in the QGIS plugin without Earth Engine, with the Python of QGIS (offscreen,
seconds):

    PYTHONNOUSERSITE=1 PYTHONPATH=src <python of QGIS> qgis/test_animation_offline.py

(macOS: /Applications/QGIS-final-4_0_3.app/Contents/MacOS/python, with QGIS_APP for another QGIS). The Python of QGIS
has no Pillow: it checks that monitoreo.animation draws the texts of the frames with Qt and writes the GIF by itself
(write_gif), and QMovie plays it. services.timelapse is faked (a GIF of three frames): it checks the group Animation
(greyed out for the fixed layers without dates, its metric fixed for the snow cover frequency), the arguments sent,
and the window of the result, with the GIF playing, its frames and the button to save it with its README.
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
	from qgis.PyQt.QtGui import QFont, QFontMetrics
	big, small, top, bar, bottom = animation.layout(160)
	font = QFont()
	font.setPixelSize(small)
	width = QFontMetrics(font).horizontalAdvance  # the credits in as many lines as they need
	bottom = animation.layout(160, len(animation._wrap(width, 'MonitorEO; Google Earth Engine', 160 - 16)))[4]
	assert (frame.width(), frame.height()) == (160, top + 120 + bottom)
	assert QColor(frame.pixel(80, top + 50)).getRgb()[:3] == (255, 0, 0)  # the map, under its texts
	assert any(QColor(frame.pixel(x, y)).getRgb()[:3] != (255, 255, 255) for x in range(8, 60) for y in range(6, 20))
	print('GIF without Pillow:', movie.frameCount(), 'frames', frame.width(), 'x', frame.height())
	# long credits: all of them, in as many lines as they need (the band below grows), not cut
	credits = ('MonitorEO; Google Earth Engine; Contains modified Copernicus Climate Change Service information '
	           '2021-2023; Source: FAO GAUL 2025 (CC BY 4.0)')
	lines = animation._wrap(width, credits, 160 - 16)
	assert len(lines) > 2 and ' '.join(lines) == credits, lines
	out = animation.annotate(pictures[0], 0, ['2021'], 'NDVI', 0.1, 0.8, ['ff0000', '00ff00'], 'unit', credits)
	b, s, top, bar, bottom = animation.layout(160, len(lines))
	assert out.shape == (top + 120 + bottom, 160, 3) and bottom > animation.layout(160)[4], out.shape
	last = top + 120 + 6 + bar + 3 + s + 6 + (len(lines) - 1) * (s + 4)
	assert (out[last:last + s, 8:152] != 255).any()  # its last line written
	print('credits drawn with Qt in', len(lines), 'lines')

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
plugin.unload()
print('OK')
