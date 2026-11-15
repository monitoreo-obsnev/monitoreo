"""Test of the bands combined on each pixel in the QGIS plugin (Combine bands: One band, Sum or Mean of the bands)
without Earth Engine, with the Python of QGIS (offscreen, seconds):

    PYTHONNOUSERSITE=1 PYTHONPATH=src <python of QGIS> qgis/test_bands_offline.py

(macOS: /Applications/QGIS-final-4_0_3.app/Contents/MacOS/python, with QGIS_APP for another QGIS). What
services.describe_asset says of an ID is given to the panel (asset_read) as if it had been read: it checks the list
Bands (shown only to combine the bands read), the band chosen checked first, the arguments that every computation sends
(the list of the bands and band_reducer), the names of the results, the errors (fewer than two bands, several without
Sum or Mean, a band that the ID has not), the bands written with commas before Read, the note on bands of different
pixel sizes or scales, and the settings kept. qgis/test_plugin.py computes with Earth Engine.
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
from qgis.PyQt.QtWidgets import QMainWindow  # noqa: E402

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
from monitoreo import services  # noqa: E402
from monitoreo_qgis.dock import data_name  # noqa: E402


def eecu_usage(*args, **kw):
	raise RuntimeError('offline')


services.init = lambda *args, **kw: 'project'
services.eecu_usage = eecu_usage
for key in ('band_reducer', 'asset_bands', 'asset_band', 'asset'):  # the defaults
	QgsSettings().remove('MonitorEO/' + key)

iface = Iface()
plugin = monitoreo_qgis.classFactory(iface)
plugin.initGui()
plugin.toggle(True)
dock = plugin.dock
dock.theme.setCurrentIndex(dock.theme.findData('earth_engine'))
assert dock.data_row.isVisibleTo(dock)

# one band by default: the field Band, not the list
assert dock.band_reducer.currentData() == '' and dock.band_field.isVisibleTo(dock)
assert not dock.bands_field.isVisibleTo(dock)

TERRACLIMATE = 'IDAHO_EPSCOR/TERRACLIMATE'
READ = {'asset': TERRACLIMATE, 'type': 'image_collection', 'use': 'collection', 'title': 'TerraClimate',
        'source': 'Earth Engine data catalog',
        'bands': [{'band': 'aet', 'description': 'Actual evapotranspiration', 'units': 'mm', 'unit': 'mm',
                   'band_scale': 0.1, 'resolution_m': 4638.3},
                  {'band': 'def', 'description': 'Climate water deficit', 'units': 'mm', 'unit': 'mm',
                   'band_scale': 0.1, 'resolution_m': 4638.3},
                  {'band': 'pr', 'description': 'Precipitation accumulation', 'units': 'mm', 'unit': 'mm',
                   'resolution_m': 4638.3},
                  {'band': 'tmmx', 'description': 'Maximum temperature', 'units': 'degC', 'unit': 'degC',
                   'band_scale': 0.1, 'resolution_m': 9000.0}],
        'arguments': {'collection': TERRACLIMATE, 'band': 'aet', 'band_scale': 0.1, 'unit': 'mm'},
        'notes': [], 'references': [], 'credits': []}
dock.asset_id.setText(TERRACLIMATE)
dock.asset_read(READ)
assert dock.asset_band.currentText() == 'aet' and dock.band_scale.text() == '0.1' and dock.asset_unit.text() == 'mm'
assert dock.asset_bands.count() == 4 and dock.checked_bands() == []
args = dock.variable_args()
assert args['band'] == 'aet' and 'band_reducer' not in args, args

# the sum of the bands: the list, with the band chosen checked first
dock.band_reducer.setCurrentIndex(dock.band_reducer.findData('sum'))
assert dock.bands_field.isVisibleTo(dock) and not dock.band_field.isVisibleTo(dock)
assert dock.checked_bands() == ['aet']
try:
	dock.data_args()
	raise AssertionError('no error with one band to combine')
except ValueError as e:
	assert 'check two or more bands of IDAHO_EPSCOR/TERRACLIMATE to combine them' in str(e), e
dock.asset_bands.setItemCheckState(1, Qt.CheckState.Checked)
args = dock.variable_args()
assert (args['collection'], args['band'], args['band_reducer']) == (TERRACLIMATE, ['aet', 'def'], 'sum'), args
assert args['band_scale'] == 0.1 and args['unit'] == 'mm' and args['start'] and args['end']
spec = services.make_spec(**{k: v for k, v in args.items() if k not in ('quality',)})  # the services take them
assert spec['band'] == ['aet', 'def'] and spec['band_reducer'] == 'sum'
entry = dock.variable.currentData()
assert entry['name'] == 'IDAHO_EPSCOR/TERRACLIMATE sum of aet, def' and entry['bands'] == ['aet', 'def'], entry
assert data_name(args) == 'IDAHO_EPSCOR/TERRACLIMATE sum of aet, def'
assert dock.bands_note.text() == '' and not dock.bands_note.isVisibleTo(dock)
# a band of other pixels and another scale: a note
dock.asset_bands.setItemCheckState(3, Qt.CheckState.Checked)
note = dock.bands_note.text()
assert 'pixels of different sizes' in note and '(4638.3 m)' in note and 'different units' in note, note
assert dock.bands_note.isVisibleTo(dock)
dock.asset_bands.setItemCheckState(3, Qt.CheckState.Unchecked)
assert dock.bands_note.text() == ''
# the mean of the bands, in the order of the data
dock.asset_bands.setItemCheckState(0, Qt.CheckState.Unchecked)
dock.asset_bands.setItemCheckState(2, Qt.CheckState.Checked)
dock.asset_bands.setItemCheckState(0, Qt.CheckState.Checked)
dock.band_reducer.setCurrentIndex(dock.band_reducer.findData('mean'))
args = dock.data_args()
assert args['band'] == ['aet', 'def', 'pr'] and args['band_reducer'] == 'mean', args
assert dock.variable.currentData()['name'] == 'IDAHO_EPSCOR/TERRACLIMATE mean of aet, def, pr'
# the settings: the reducer and the bands checked
dock.save_settings()
s = QgsSettings()
assert s.value('MonitorEO/band_reducer') == 'mean' and s.value('MonitorEO/asset_bands') == 'aet,def,pr'

# one band again: the field Band, and several written there are refused
dock.band_reducer.setCurrentIndex(dock.band_reducer.findData(''))
assert dock.band_field.isVisibleTo(dock) and not dock.bands_field.isVisibleTo(dock)
assert dock.data_args()['band'] == 'aet'
dock.asset_band.setEditText('aet,def')
try:
	dock.data_args()
	raise AssertionError('no error with several bands and One band')
except ValueError as e:
	assert 'choose Sum or Mean of the bands in Combine bands' in str(e), e

# before Read: several bands written with commas, checked against nothing
dock.asset_id.setText('users/someone/rain')
dock.asset_edited()
dock.asset_bands.clear()
dock.asset_band.setEditText('jan, feb ,mar')
dock.band_reducer.setCurrentIndex(dock.band_reducer.findData('sum'))
assert dock.band_field.isVisibleTo(dock) and not dock.bands_field.isVisibleTo(dock)  # nothing read to check
args = dock.data_args()
assert args['band'] == ['jan', 'feb', 'mar'] and args['band_reducer'] == 'sum', args
# then Read: the bands written are those checked; one that the ID has not, refused
dock.asset_read({'asset': 'users/someone/rain', 'type': 'image', 'use': 'image', 'title': 'users/someone/rain',
                 'source': 'Earth Engine asset', 'notes': [], 'references': [], 'credits': [], 'arguments': {},
                 'bands': [{'band': b, 'resolution_m': 1000.0} for b in ('jan', 'feb', 'mar', 'apr')]})
assert dock.checked_bands() == ['jan', 'feb', 'mar'] and dock.bands_field.isVisibleTo(dock)
assert dock.data_args() == {'image': 'users/someone/rain', 'band': ['jan', 'feb', 'mar'], 'band_reducer': 'sum'}
dock.asset_info = dict(dock.asset_info, bands=[{'band': 'jan'}, {'band': 'feb'}])  # as if read with fewer bands
try:
	dock.data_args()
	raise AssertionError('no error with a band that the ID has not')
except ValueError as e:
	assert 'users/someone/rain has no band mar' in str(e), e

for key in ('band_reducer', 'asset_bands', 'asset_band', 'asset'):
	s.remove('MonitorEO/' + key)
plugin.unload()
print('OK')
