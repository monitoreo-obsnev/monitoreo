"""Test of the data of the results and the dates of the data in the QGIS plugin (monitoreo.coverage), without Earth
Engine, with the Python of QGIS (offscreen, seconds):

    PYTHONNOUSERSITE=1 PYTHONPATH=src <python of QGIS> qgis/test_dates_offline.py

(macOS: /Applications/QGIS-final-4_0_3.app/Contents/MacOS/python, with QGIS_APP for another QGIS). The windows of the
results say which data their values come from («Data: ...», data_source) and the warnings of their period (in orange);
the chart drawn with Qt (without matplotlib) and those of matplotlib say it under them; the message bar shows the
warnings of the answers of a task (dock.result_warnings, also those of a map: {'index', 'rgb'}); and a period without
images of the data is refused before Earth Engine, with the message of the package.
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

from qgis.core import QgsApplication  # noqa: E402
from qgis.gui import QgsMapCanvas, QgsMessageBar  # noqa: E402
from qgis.PyQt.QtGui import QColor  # noqa: E402
from qgis.PyQt.QtWidgets import QLabel, QMainWindow  # noqa: E402

app = QgsApplication([], True)
QgsApplication.setPrefixPath(os.path.join(APP, 'Contents', 'MacOS'), True)
app.initQgis()
TMP = tempfile.mkdtemp(prefix='monitoreo_test_')

import monitoreo_qgis  # noqa: E402
from monitoreo_qgis import deps  # noqa: E402

deps.setup_path()  # earthengine-api from the ext/ of the plugin (build_plugin.py), or from PYTHONPATH
from monitoreo import services  # noqa: E402
from monitoreo_qgis import dock as docks, results  # noqa: E402

S2 = 'COPERNICUS/S2_SR_HARMONIZED (Harmonized Sentinel-2 MSI, Level-2A (SR))'
WARNING = (f'The images of {S2} start on 2017-03-28: the period asked for begins on 2016-01-01, so its first 15 '
           'months have no data.')


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


def eecu_usage(*args, **kw):
	raise RuntimeError('offline')


services.init = lambda *args, **kw: 'project'
services.eecu_usage = eecu_usage

# the warnings of the answers of a task: of one answer, of several, of the maps of maps_work ({'index', 'rgb'})
assert docks.result_warnings({'warnings': [WARNING], 'data_source': S2}) == [WARNING]
assert docks.result_warnings({'index': {'warnings': ['a']}, 'rgb': {'warnings': ['a', 'b']}}) == ['a', 'b']
assert docks.result_warnings([{'warnings': ['a']}, None, {'warnings': 'not a list'}]) == ['a']
assert docks.result_warnings(None) == [] and docks.result_warnings({'rows': []}) == []
print('warnings of the answers of a task: those of every answer, once')

# the window of a series: the data under its first line, the warnings in orange; the chart drawn with Qt says it too
rows = [{'region': 'park', 'date': f'2017-{m:02d}-01', 'value': 0.3 + m / 100, 'n_pixels': 4, 'n_images': 1}
        for m in range(4, 13)]
res = {'title': 'NDVI Sentinel-2 | 2016-01-01 / 2026-12-31 | monthly mean, spatial mean', 'rows': rows, 'scale': 10.0,
       'unit': '[unitless]', 'ylabel': '[unitless]', 'csv': None, 'chart': None, 'references': [], 'credits': [],
       'data_source': S2, 'warnings': [WARNING]}
dialog = results.SeriesDialog(res)
notes = dialog.findChild(QLabel, 'data_notes')
assert notes is not None and f'Data: {S2}' in notes.text() and '⚠ The images of' in notes.text(), notes.text()
assert dialog.chart is not None and dialog.chart.source == S2
dialog.chart.resize(800, 360)
picture = dialog.chart.grab().toImage()
grey = [x for x in range(6, 400) for y in range(picture.height() - 16, picture.height() - 2)
        if QColor(picture.pixel(x, y)).getRgb()[:3] != (255, 255, 255)]
assert grey, 'no line «Data: ...» under the chart drawn with Qt'
assert results.notes_label({'title': 'x'}) is None  # an answer without them (an earlier version): nothing
assert results.data_warnings({'warnings': ['a', '', None]}) == ['a']
print('window of a series: «Data: ...» and the warnings, also under the chart of Qt')

# the window of the trends: the same label
trends = {'kind': 'trends', 'label': 'Trends', 'title': 'Trends of NDVI', 'rows': [], 'yearly': [], 'scale': 10.0,
          'unit': '[unitless]', 'references': [], 'credits': [], 'data_source': S2, 'warnings': [WARNING]}
window = results.ResultDialog(trends)
notes = window.findChild(QLabel, 'data_notes')
assert notes is not None and S2 in notes.text() and 'first 15 months' in notes.text()
print('window of the trends: «Data: ...» and the warnings')

# with matplotlib, the chart of monitoreo says it under it
try:
	import matplotlib  # noqa: F401
	path = os.path.join(TMP, 'series.png')
	assert results.chart_png(res, path) == path and os.path.getsize(path) > 0
	print('chart of matplotlib with «Data: ...»')
except ImportError:
	print('this QGIS has no matplotlib: the chart drawn with Qt only')

# the plugin: the message bar shows the warnings of the answer of a task, and a period without images is refused with
# the message of the package (before Earth Engine)
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
done = []
dock.run_task('Time series of NDVI', lambda: {'rows': [], 'warnings': [WARNING], 'data_source': S2}, done.append)
wait()
assert done and f'Warning: Time series of NDVI: {WARNING}' in messages, messages
messages.clear()
dock.run_task('Time series of NDVI', lambda: services.make_spec('NDVI', 'Sentinel-2', '2015-01-01', '2016-12-31'),
              done.append)
wait()
assert any(m.startswith('Critical: Time series of NDVI: The images of COPERNICUS/S2_SR_HARMONIZED') and
           'ends before them and has no data' in m for m in messages), messages
print('message bar: the warnings of an answer, and the error of a period without images')
plugin.unload()
print('OK')
