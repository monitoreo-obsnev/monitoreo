"""Test of the land cover mask in the QGIS plugin without Earth Engine, with the Python of QGIS (offscreen, seconds):

    PYTHONNOUSERSITE=1 PYTHONPATH=src <python of QGIS> qgis/test_landcover_offline.py

(macOS: /Applications/QGIS-final-4_0_3.app/Contents/MacOS/python, with QGIS_APP for another QGIS). It checks the group
«Land cover mask» before the group Variable (folded and off by default, unfolded when checked), the years of each map,
the land covers of the checkable list, the condition of where that every computation sends (also with the conditions
on variables, and with the data of Earth Engine by their ID), the error without land covers and the help of «Leave
out» with the classes of the map chosen. qgis/test_plugin.py computes with Earth Engine.
"""

import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
APP = os.environ.get('QGIS_APP', '/Applications/QGIS-final-4_0_3.app')
for proj in ('Contents/Resources/proj', 'Contents/Resources/qgis/proj'):
	if os.path.exists(os.path.join(APP, proj, 'proj.db')):
		os.environ.setdefault('PROJ_DATA', os.path.join(APP, proj))
		os.environ.setdefault('PROJ_LIB', os.path.join(APP, proj))
sys.path.insert(0, os.path.join(APP, 'Contents', 'Resources', 'python'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qgis.core import QgsApplication, QgsSettings  # noqa: E402
from qgis.gui import QgsMapCanvas, QgsMessageBar  # noqa: E402
from qgis.PyQt.QtCore import Qt  # noqa: E402
from qgis.PyQt.QtWidgets import QGroupBox, QMainWindow  # noqa: E402

app = QgsApplication([], True)
QgsApplication.setPrefixPath(os.path.join(APP, 'Contents', 'MacOS'), True)
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
from monitoreo import landcover, services  # noqa: E402


def eecu_usage(*args, **kw):
	raise RuntimeError('offline')


services.init = lambda *args, **kw: 'project'
services.eecu_usage = eecu_usage
for key in ('landcover_on', 'landcover_map', 'landcover_year', 'landcover_exclude'):  # the defaults
	QgsSettings().remove('MonitorEO/' + key)

iface = Iface()
plugin = monitoreo_qgis.classFactory(iface)
plugin.initGui()
plugin.toggle(True)
dock = plugin.dock
box = dock.landcover_box

# before the group Variable, folded and off
titles = [b.title() for b in dock.findChildren(QGroupBox)]
assert titles.index('Land cover mask') < titles.index('Variable'), titles
assert not box.isChecked() and box.isCollapsed()
assert dock.where_args() is None  # off: no condition
box.setChecked(True)
assert not box.isCollapsed()  # it unfolds when checked

# the maps and their years: the last one (Dynamic World, the last whole year) when the map changes
maps = [dock.landcover_map.itemData(i) for i in range(dock.landcover_map.count())]
assert maps == [m['key'] for m in landcover.maps()], maps
assert dock.landcover_map.currentData() == 'WorldCover' and dock.landcover_year.currentData() == 2021
dock.landcover_map.setCurrentIndex(maps.index('CORINE'))
years = [dock.landcover_year.itemData(i) for i in range(dock.landcover_year.count())]
assert years == [2018, 2012, 2006, 2000, 1990] and dock.landcover_year.currentData() == 2018, years
dock.landcover_year.setCurrentIndex(years.index(2012))
dock.landcover_map.setCurrentIndex(maps.index('MODIS'))
assert dock.landcover_year.currentData() == 2012  # MODIS has 2012 too: it stays
dock.landcover_map.setCurrentIndex(maps.index('DynamicWorld'))  # since 2016: its last whole year
assert dock.landcover_year.currentData() == landcover.default_year(landcover.find('DynamicWorld'))
dock.landcover_map.setCurrentIndex(maps.index('CORINE'))
dock.landcover_year.setCurrentIndex(dock.landcover_year.findData(2018))

# the land covers: water and built-up checked by default
items = [dock.landcover_classes.itemData(i) for i in range(dock.landcover_classes.count())]
assert items == [c['key'] for c in landcover.classes()], items
assert sorted(dock.landcover_classes.checkedItemsData()) == ['built', 'water']
assert dock.landcover_args() == {'landcover': 'CORINE', 'year': 2018, 'exclude': ['water', 'built']}

# the condition goes with those on variables, and with the data of Earth Engine by their ID
dock.where[0]['on'].setChecked(True)
dock.where[0]['min'].setText('1500')
where = dock.where_args()
assert where[0]['variable'] == 'ELEVATION' and where[-1] == dock.landcover_args(), where
args = dock.variable_args()
assert args['where'][-1]['landcover'] == 'CORINE', args
services.make_spec(**{k: v for k, v in args.items() if k != 'quality'})  # the services take it
dock.where[0]['on'].setChecked(False)
assert dock.where_args() == [dock.landcover_args()]

# without land covers: an error that says what to do
for i in range(dock.landcover_classes.count()):
	dock.landcover_classes.setItemCheckState(i, Qt.CheckState.Unchecked)
try:
	dock.where_args()
	raise AssertionError('no error without land covers')
except ValueError as e:
	assert 'check the land covers' in str(e), e
dock.landcover_classes.setItemCheckState(items.index('cropland'), Qt.CheckState.Checked)
assert dock.landcover_args()['exclude'] == ['cropland']

# the help of «Leave out»: the classes of the map chosen
text = dock.landcover_help()
assert '244 Agro-forestry areas' in text and '<b>Cropland</b>' in text, text

# its settings are kept
dock.save_settings()
s = QgsSettings()
assert s.value('MonitorEO/landcover_on') == 'true' and s.value('MonitorEO/landcover_map') == 'CORINE'
assert s.value('MonitorEO/landcover_exclude') == 'cropland'
for key in ('landcover_on', 'landcover_map', 'landcover_year', 'landcover_exclude'):
	s.remove('MonitorEO/' + key)
plugin.unload()
print('OK')
