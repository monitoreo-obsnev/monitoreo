"""Test of the analyses of the QGIS plugin added after the review of geemap (animations, area by class), without
Earth Engine, with the Python of QGIS (offscreen, seconds):

    PYTHONNOUSERSITE=1 PYTHONPATH=src <python of QGIS> qgis/test_analyses_offline.py

(macOS: /Applications/QGIS-final-4_0_3.app/Contents/MacOS/python, with QGIS_APP for another QGIS). The Python of QGIS
has no Pillow: it checks that monitoreo.animation draws the texts of the frames with Qt and writes the GIF by itself
(write_gif), and QMovie plays it. services.timelapse is faked (a GIF of three frames): it checks the group Animation
(greyed out for the fixed layers without dates, its metric fixed for the snow cover frequency), the arguments sent,
and the window of the result, with the GIF playing, its frames and the button to save it with its README.
services.area_by_class is faked too: the group Area by class (its kinds of classes and their fields), the arguments of
each kind (a land cover map without the land cover mask nor «Only the pixels where»; for its changes, the Sankey
diagram of the first feature, named in its title) and the window of the result (its table, with the colour of each
class). The land cover mask starts off, whatever the settings stored by other tests.
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
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsRectangle, QgsSettings  # noqa: E402
from qgis.gui import QgsMapCanvas, QgsMessageBar  # noqa: E402
from qgis.PyQt.QtCore import QDate, Qt  # noqa: E402
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
from monitoreo import animation, catalog, charts, sensors, services  # noqa: E402
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
	fw = max(160, animation.MIN_WIDTH)  # a map narrower than MIN_WIDTH, centred on a frame of MIN_WIDTH
	big, small, top, bar, bottom = animation.layout(fw)
	font = QFont()
	font.setPixelSize(small)
	width = QFontMetrics(font).horizontalAdvance  # the credits in as many lines as they need
	bottom = animation.layout(fw, len(animation._wrap(width, 'MonitorEO; Google Earth Engine', fw - 16)))[4]
	assert (frame.width(), frame.height()) == (fw, top + 120 + bottom)
	assert QColor(frame.pixel(fw // 2, top + 50)).getRgb()[:3] == (255, 0, 0)  # the map, under its texts
	assert any(QColor(frame.pixel(x, y)).getRgb()[:3] != (255, 255, 255) for x in range(8, 60) for y in range(6, 20))
	print('GIF without Pillow:', movie.frameCount(), 'frames', frame.width(), 'x', frame.height())
	# long credits: all of them, in as many lines as they need (the band below grows), not cut
	credits = ('MonitorEO; Google Earth Engine; Contains modified Copernicus Climate Change Service information '
	           '2021-2023; Source: FAO GAUL 2025 (CC BY 4.0)')
	lines = animation._wrap(width, credits, fw - 16)
	assert len(lines) > 2 and ' '.join(lines) == credits, lines
	out = animation.annotate(pictures[0], 0, ['2021'], 'NDVI', 0.1, 0.8, ['ff0000', '00ff00'], 'unit', credits)
	b, s, top, bar, bottom = animation.layout(fw, len(lines))
	assert out.shape == (top + 120 + bottom, fw, 3) and bottom > animation.layout(fw)[4], out.shape
	last = top + 120 + 6 + bar + 3 + s + 6 + (len(lines) - 1) * (s + 4)
	assert (out[last:last + s, 8:fw - 8] != 255).any()  # its last line written
	print('credits drawn with Qt in', len(lines), 'lines')
	# a narrow map (a strip of land, 18 x 65 pixels): centred on a frame of MIN_WIDTH, its credits in a few lines
	out = animation.annotate(np.full((65, 18, 3), 200, np.uint8), 0, ['2021'], 'NDVI', 0.1, 0.8, ['ff0000', '00ff00'],
	                         'unit', credits)
	x = (animation.MIN_WIDTH - 18) // 2
	assert out.shape == (top + 65 + bottom, animation.MIN_WIDTH, 3), out.shape
	assert (out[top:top + 61, x:x + 18] == 200).all() and (out[top:top + 61, :x] == 255).all()
	print('a map 18 pixels wide on a frame of', out.shape[1], 'x', out.shape[0])

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
	if opts.get('other_year'):  # the changes of a land cover map over two features: Sierra Nevada, then Doñana
		rows = [{'region': g, 'from_label': a, 'to_label': b, 'ha': ha, 'percent': p} for g, a, b, ha, p in
		        (('Sierra Nevada', '311 Broad-leaved forest', '324 Transitional woodland-shrub', 15.0, 15.0),
		         ('Doñana', '512 Water bodies', '512 Water bodies', 30.0, 100.0))]
		with open(csv, 'w') as f:
			f.write('region,from_label,to_label,ha,percent\n')
		return {'rows': rows, 'mode': 'transitions', 'scale': 100.0, 'unit': '', 'title': 'Changes', 'csv': csv,
		        'year': opts['year'], 'other_year': opts['other_year'], 'classes': [], 'references': [], 'credits': [],
		        'data_source': 'COPERNICUS/CORINE/V20/100m/2012; COPERNICUS/CORINE/V20/100m/2018',
		        'changed_ha': {'Sierra Nevada': 15.0, 'Doñana': 0.0},
		        'unchanged_ha': {'Sierra Nevada': 0.0, 'Doñana': 30.0},
		        'by_landcover': [{'region': 'Doñana', 'from_label': 'Water', 'to_label': 'Water', 'ha': 30.0},
		                         {'region': 'Sierra Nevada', 'from_label': 'Trees', 'to_label': 'Trees', 'ha': 15.0}]}
	rows = [{'region': 'extent', 'class': c, 'label': label, 'ha': ha, 'percent': p}
	        for c, label, ha, p in ((-1, 'significant decrease', 10.0, 10.0), (0, 'no significant trend', 80.0, 80.0),
	                                (1, 'significant increase', 10.0, 10.0))]
	with open(csv, 'w') as f:
		f.write('region,class,label,ha,percent\n')
	return {'rows': rows, 'mode': 'trend', 'scale': 250.0, 'unit': '', 'title': 'Area of each class', 'csv': csv,
	        'classes': [{'class': r['class'], 'label': r['label'], 'colour': c}
	                    for r, c in zip(rows, ('d7191c', 'bdbdbd', '1a9641'))], 'references': [], 'credits': []}


services.area_by_class = area_by_class
sankeys = []  # the Sankey diagrams drawn (without matplotlib in the Python of QGIS), with their line «Data: ...»
charts.sankey_png = lambda flows, colours=None, path=None, title=None, names=('', ''), source=None: sankeys.append(
	(flows, title, source))
for key in ('landcover_on', 'landcover_map', 'landcover_year', 'landcover_exclude'):  # the defaults: no land cover mask
	QgsSettings().remove('MonitorEO/' + key)


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


def time_series(region, csv=None, **opts):
	"""services.time_series of the NDVI of Sentinel-2 (monthly, 2022-2023) and, with doy and interannual or
	other_variable, its seasonal profile as services makes it (timeseries.doy_profile; no range of the y axes unless
	given, each axis from the values of its own variable), the other variable (a decreasing NDSI that crosses 0) on
	the right axis. The values of each month change from 2022 to 2023,
	so that their standard deviation is not 0."""
	calls.append(dict(opts, region=region, tool='time_series'))
	from monitoreo import timeseries
	other = opts.get('other_variable')
	names = ['NDVI Sentinel-2'] + ([f"{other} {opts['other_sensor']}"] if other else [])
	rows = [{'region': 'extent', 'date': f'{y}-{m:02d}-01', 'value': 0.1 * m + 0.04 * (y - 2022) if k == 0 else 0.6 - 0.1 * m + 0.02 * (y - 2022),
	         'n_pixels': 10, 'n_images': 2} for k in range(len(names)) for y in (2022, 2023) for m in range(1, 13)]
	if other:
		for i, r in enumerate(rows):
			r['variable'] = names[i // 24]
	if opts.get('doy'):
		import datetime
		for r in rows:
			d = datetime.date.fromisoformat(r['date'])
			r['year'], r['doy'] = d.year, d.timetuple().tm_yday
	out = {'rows': rows, 'csv': csv, 'chart': None, 'scale': 250.0, 'unit': '[unitless]', 'ylabel': 'NDVI',
	       'title': 'NDVI', 'n_steps': 24, 'regions': ['extent'], 'references': [], 'credits': []}
	if opts.get('doy'):
		out['ylim'] = None
	if opts.get('doy') and (opts.get('interannual') or other):
		between = opts.get('interannual') or 'median'
		out.update(profile=timeseries.doy_profile(rows, None, opts['step'], between, names[0]), variables=names,
		           units={n: '[unitless]' for n in names}, scales=dict(zip(names, (10.0, 20.0))), interannual=between,
		           ylim=services.check_ylim(opts.get('ylim')), other_ylim=services.check_ylim(opts.get('other_ylim')),
		           other_ylabel=f'{other} [unitless]' if other else None,
		           title=f"{' and '.join(names)} | {between} of the years by day of the year")
	return out


services.time_series = time_series

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

# the pixel filter of what the variable measures: unchecked and greyed out (snow with the NDSI, water with the NDWI),
# the others as the user leaves them, and those chosen back with another variable, also after the fixed ones of the SCF
def pick(text):
	dock.variable.setCurrentIndex(dock.variable.findText(text, Qt.MatchFlag.MatchStartsWith))
	assert dock.variable.currentText().startswith(text), text


def state():
	return {k: (w.isChecked(), w.isEnabled()) for k, w in dock.filters.items()}


pick('NDVI · Sentinel-2')
for w in dock.filters.values():
	w.setChecked(True)
pick('NDSI · Sentinel-2')
assert state() == {'clouds': (True, True), 'water': (True, True), 'snow': (False, False), 'aerosols': (True, True)}
assert 'NDSI' in dock.filters['snow'].toolTip() and not dock.filters['clouds'].toolTip()
assert not dock.quality_args()['snow'] and dock.quality_args(own=True)['snow']
dock.filters['aerosols'].setChecked(False)  # changed with the NDSI: kept
pick('NDWI · Sentinel-2')
assert state() == {'clouds': (True, True), 'water': (False, False), 'snow': (True, True), 'aerosols': (False, True)}
if scf >= 0:
	dock.variable.setCurrentIndex(scf)
	assert state() == {'clouds': (True, False), 'water': (True, False), 'snow': (False, False),
	                   'aerosols': (False, False)}
	assert {k: v for k, v in dock.quality_args(own=True).items() if k != 'cloud_score'} == \
		dict(clouds=True, water=True, snow=True, aerosols=False)
pick('NDVI · Sentinel-2')
assert state() == {'clouds': (True, True), 'water': (True, True), 'snow': (True, True), 'aerosols': (False, True)}
assert all(not w.toolTip() for w in dock.filters.values())
dock.filters['aerosols'].setChecked(True)
print('pixel filters: that of what the variable measures greyed out, the others kept')

dock.variable.setCurrentIndex(dock.variable.findText('NDVI · Sentinel-2', Qt.MatchFlag.MatchStartsWith))
assert [dock.anim_step.itemData(i) for i in range(dock.anim_step.count())] == ['annual', 'monthly', '16-day', 'daily']
print('group Animation:', [dock.anim_step.itemText(i) for i in range(dock.anim_step.count())])

# the animation: its arguments, and its window with the GIF playing, its frames and Save GIF…
dock.region_kind.setCurrentIndex(dock.region_kind.findData('extent'))
iface.canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
iface.canvas.setExtent(QgsRectangle(-3.45, 37.02, -3.30, 37.12))
# the biome at the center of the map, after the ecoregion (the layer and the map extent stay the first two): only its
# part in the map extent, the region {'biome_at': its center, 'within': the extent}
kinds = [dock.region_kind.itemData(i) for i in range(dock.region_kind.count())]
assert kinds[:2] == ['layer', 'extent'] and kinds.index('biome') == kinds.index('ecoregion') + 1, kinds
extent = dock.region()
dock.region_kind.setCurrentIndex(kinds.index('biome'))
biome = dock.region()
(w, s, e, n), (lon, lat) = extent['bbox'], biome['biome_at']
assert biome['within'] == extent and abs(lon - (w + e) / 2) < 1e-9 and abs(lat - (s + n) / 2) < 1e-9, biome
assert dock.region_kind.currentText() == 'Biome at the center of the map'
dock.region_kind.setCurrentIndex(kinds.index('extent'))
print('region: the biome at the center of the map, within the extent', biome)
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
assert buttons == ['Save GIF…', 'Copy parameters', 'Save parameters…', 'Close'], buttons
assert res['call']['analysis'] == 'timelapse' and res['call']['parameters']['fps'] == 4  # its parameters
from monitoreo_qgis.results import save_file  # noqa: E402
copy = os.path.join(TMP, 'copy.gif')
save_file(res['gif'], copy, res)
assert os.path.exists(copy) and os.path.exists(os.path.join(TMP, 'copy.README.txt'))
print('window of the animation:', dlg.windowTitle(), '| frames', dlg.movie.frameCount())

# Area by class: the fields of each kind, the arguments sent and the window
kinds = [dock.area_kind.itemData(i) for i in range(dock.area_kind.count())]
assert kinds == ['landcover', 'breaks', 'trend', 'classes'], kinds  # classes: of a categorical layer (BIOME...)
for kind, map_shown, breaks_shown in (('landcover', True, False), ('breaks', False, True), ('trend', False, False),
                                      ('classes', False, False)):
	dock.area_kind.setCurrentIndex(dock.area_kind.findData(kind))
	assert dock.area_map_row.isVisibleTo(dock) == map_shown and dock.area_breaks.isVisibleTo(dock) == breaks_shown, kind
dock.area_map.setCurrentIndex(dock.area_map.findData('CORINE'))
assert dock.area_year.currentData() == 2018 and dock.area_year.findData(1990) >= 0
dock.area_kind.setCurrentIndex(dock.area_kind.findData('landcover'))
assert not dock.landcover_box.isChecked() and not any(c['on'].isChecked() for c in dock.where)  # not stored ones
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
assert sankeys[-1] == ([('Trees', 'Trees', 15.0)], 'Changes (Sierra Nevada)',  # the first feature, named
                       'COPERNICUS/CORINE/V20/100m/2012; COPERNICUS/CORINE/V20/100m/2018'), sankeys
dock.area_change.setChecked(False)
# a land cover map refuses the land cover mask and «Only the pixels where», as services.area_by_class
made = len(calls)
for box in (dock.landcover_box, dock.where[0]['on']):
	box.setChecked(True)
	dock.run_areas()
	wait()
	box.setChecked(False)
	assert len(calls) == made and 'are for the classes of a variable' in messages[-1], messages[-1]
	assert messages[-1].startswith('Warning: The land cover mask and «Only the pixels where»'), messages[-1]
dock.area_kind.setCurrentIndex(dock.area_kind.findData('breaks'))
dock.area_breaks.setText('0.2, 0.4')
dock.run_areas()
wait()
assert calls[-1]['breaks'] == [0.2, 0.4] and calls[-1]['variable'] == 'NDVI', calls[-1]  # numbers (#85)
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
assert z['tool'] == 'region_stats' and z['zones'] == {'variable': 'ELEVATION', 'sensor': 'Copernicus', 'breaks': [1500.0]}
assert z['stats'] == ['p25', 'p50', 'p75', 'mean'] and z['variable'] == 'NDVI', z
dlg = dock.series_dialogs[len(dock.series) - 1]
table = dlg.findChild(QTableWidget)
assert [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())][:3] == ['Region', 'Zone', 'Percentile 25']
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

# the time series with a line per year over the days of the year: the chart of Qt (no matplotlib in QGIS)
dock.step.setCurrentIndex(dock.step.findData('monthly'))
dock.doy.setChecked(True)
dock.run_series()
wait()
assert calls[-1]['tool'] == 'time_series' and calls[-1]['doy'] is True, calls[-1]
from monitoreo_qgis.results import ChartWidget  # noqa: E402
chart = ChartWidget(dock.series[-1]['rows'], 'NDVI', 'NDVI')
assert chart.doy and sorted(chart.series) == ['2022', '2023'] and len(chart.series['2022']) == 12
old, new = chart.pen(0, '2022'), chart.pen(1, '2023')  # the newest year darker and thicker, as charts.doy_png
assert new.widthF() > old.widthF() and new.color().lightness() < old.color().lightness()
chart.resize(600, 320)
chart.grab()  # it paints
rows = [dict(r, region=g) for g in ('park', 'buffer') for r in dock.series[-1]['rows']]  # two regions: a dash each
two = ChartWidget(rows, 'NDVI', 'NDVI')
assert two.pen(0, 'park 2022').style() != two.pen(2, 'buffer 2022').style()
assert two.pen(0, 'park 2022').color() == two.pen(2, 'buffer 2022').color()
two.resize(600, 320)
two.grab()
dock.step.setCurrentIndex(dock.step.findData('annual'))
dock.run_series()
wait()
assert calls[-1]['doy'] is False  # a value per year: no line per year
dock.doy.setChecked(False)
print('series by day of the year:', sorted(chart.series))

# the seasonal profile: Between years (a metric of the values of each step of the year in the years of the period) and
# Right axis (a second variable), only with the chart by day of the year; its window with a y axis for each variable
from monitoreo_qgis import results  # noqa: E402
from monitoreo_qgis.helptexts import HELP  # noqa: E402

assert results.PROFILE_COLOURS == charts.PROFILE_COLOURS and results.MONTH_STARTS == charts.MONTH_STARTS
assert 'seasonal profile' in HELP['doy_interannual'] and 'right axis' in HELP['doy_other'] and HELP['doy']
assert not dock.doy_interannual.isEnabled() and not dock.doy_other.isEnabled()  # the chart by date
dock.step.setCurrentIndex(dock.step.findData('monthly'))
dock.doy.setChecked(True)
assert dock.doy_interannual.isEnabled() and dock.doy_other.isEnabled()
between = [dock.doy_interannual.itemData(i) for i in range(dock.doy_interannual.count())]
assert between == [None, 'mean', 'median', 'min', 'max', 'p25', 'p75', 'std', 'cv'], between
assert dock.doy_interannual.currentText() == 'A line per year' and dock.doy_other.currentText() == 'None'
others = [dock.doy_other.itemData(i) for i in range(1, dock.doy_other.count())]
pairs = [(o['variable'], o['sensor']) for o in others]
assert ('NDSI', 'Sentinel-2') in pairs and ('NDVI', 'Modis') in pairs and len(pairs) == len(set(pairs))  # each once
assert not {'ELEVATION', 'SLOPE', 'RBR', 'RdNBR', 'BIO01'} & {v for v, _ in pairs}  # only the variables with dates
ndsi = dock.doy_other.findText('NDSI (Sentinel-2)')
assert ndsi > 0 and 'COPERNICUS/S2' in dock.doy_other.itemData(ndsi, Qt.ItemDataRole.ToolTipRole)
assert 'MOD10A1' in dock.doy_other.itemData(dock.doy_other.findText('NDSI (Modis)'), Qt.ItemDataRole.ToolTipRole)
# a line per year: neither interannual nor other_variable
dock.run_series()
wait()
assert calls[-1]['doy'] is True and not {'interannual', 'other_variable', 'other_sensor'} & set(calls[-1]), calls[-1]
# a variable on the right axis: the median between the years (as services.time_series), then sent with it
dock.doy_other.setCurrentIndex(ndsi)
assert dock.doy_interannual.currentData() == 'median'
dock.run_series()
wait()
sent = calls[-1]
assert sent['doy'] is True and sent['interannual'] == 'median' and sent['variable'] == 'NDVI', sent
assert (sent['other_variable'], sent['other_sensor']) == ('NDSI', 'Sentinel-2'), sent
res = dock.series[-1]
assert res['label'].startswith('NDVI Sentinel-2 and NDSI Sentinel-2 | median of the years'), res['label']
dlg = dock.series_dialogs[len(dock.series) - 1]
try:
	import matplotlib  # noqa: F401
	plotted = True
except ImportError:
	plotted = False
assert (results.chart_png(res, os.path.join(TMP, 'profile.png')) is not None) == plotted  # matplotlib, else Qt
assert (dlg.chart is None) == plotted
chart = dlg.chart or results.ChartWidget(res['rows'], res['title'], results.ylabel(res), profile=res['profile'],
                                         other_unit=results.other_ylabel(res), ylim=res['ylim'],
                                         other_ylim=res['other_ylim'])
assert chart.profile and chart.names == ['NDVI Sentinel-2', 'NDSI Sentinel-2'], chart.names
assert sorted(chart.series) == ['NDSI Sentinel-2', 'NDVI Sentinel-2'] and len(chart.series['NDSI Sentinel-2']) == 12
# each axis from the minimum to the maximum of the values of its own variable (with a margin of 5 %), not -1 to 1
for k, name in enumerate(chart.names):
	own = [r['value'] for r in res['profile'] if r['variable'] == name and r['value'] is not None]
	low, high = chart.axis_range(k)
	assert low < min(own) < max(own) < high and high - low < 1.2 * (max(own) - min(own)), (name, low, high, own)
assert res['ylim'] is None and res['other_ylim'] is None and chart.axis_range(0) != chart.axis_range(1)
assert (chart.unit, chart.other_unit) == ('NDVI', 'NDSI [unitless]'), (chart.unit, chart.other_unit)
assert chart.pen(0, 'NDVI Sentinel-2').color() == QColor(results.PROFILE_COLOURS[0])
assert chart.pen(1, 'NDSI Sentinel-2').color() == QColor(results.PROFILE_COLOURS[1])
first = chart.series['NDSI Sentinel-2'][0]  # January: on day 1, the median of 0.50 (2022) and 0.52 (2023)
assert first[0] == 1 and abs(first[1] - 0.51) < 1e-9, first
chart.resize(700, 360)
image = chart.grab().toImage()


def near(colour, x0, x1):
	"""How many pixels of the columns X0 to X1 of IMAGE are of COLOUR (#rrggbb), or nearly."""
	c = QColor(colour).getRgb()[:3]
	pixels = (QColor(image.pixel(x, y)).getRgb()[:3] for x in range(x0, x1) for y in range(image.height()))
	return sum(1 for px in pixels if sum(abs(a - b) for a, b in zip(px, c)) < 60)


w = image.width()
assert near(results.PROFILE_COLOURS[1], w - 70, w) > 20  # the right axis in red: its numbers and its title
assert near(results.PROFILE_COLOURS[0], 0, 70) > 20  # the left one in blue
assert near(results.PROFILE_COLOURS[1], 80, w - 80) > 50 and near(results.PROFILE_COLOURS[0], 80, w - 80) > 50
table = dlg.findChild(QTableWidget)
headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
assert headers == ['Region', 'Variable', 'Step of the year', 'Day of the year', 'Value', 'Unit', 'Years'], headers
assert table.rowCount() == 24 and [table.item(0, j).text() for j in (1, 2, 3, 5, 6)] == \
	['NDVI Sentinel-2', 'Jan', '1', '[unitless]', '2'], [table.item(0, j).text() for j in range(7)]
assert table.item(12, 1).text() == 'NDSI Sentinel-2' and table.item(12, 4).text() == '0.51', table.item(12, 4).text()
text = results.series_text(res)
assert 'left axis: NDVI Sentinel-2, [unitless], pixels of 10 m · ' in text and 'y from' not in text, text
assert 'right axis: NDSI Sentinel-2, [unitless], pixels of 20 m · ' in text, text
given = dict(res, ylim=(0.0, 1.5))  # a range given: that of the axis
assert 'pixels of 10 m, y from 0 to 1.5 · ' in results.series_text(given)
assert results.ChartWidget([], 'NDVI', 'NDVI', profile=res['profile'], ylim=(0.0, 1.5)).axis_range(0) == (0.0, 1.5)
assert 'median of 48 values of each year in 24 steps of the year' in text, text
print('profile on two axes:', chart.names, '| table', table.rowCount(), 'rows')
# two regions: a dash for each, the colour of its axis
two = results.ChartWidget([], 'NDVI', 'NDVI', profile=[dict(r, region=g) for g in ('park', 'buffer')
                                                        for r in res['profile']], other_unit='NDSI')
assert two.pen(0, 'park · NDVI Sentinel-2').style() != two.pen(2, 'buffer · NDVI Sentinel-2').style()
assert two.pen(0, 'park · NDSI Sentinel-2').color() == QColor(results.PROFILE_COLOURS[1])
two.resize(600, 320)
two.grab()
# A line per year again: no variable on the right axis
dock.doy_interannual.setCurrentIndex(0)
assert dock.doy_other.currentData() is None
# a metric between the years without a right axis: one variable, one axis, from the standard deviations
dock.doy_interannual.setCurrentIndex(dock.doy_interannual.findData('std'))
dock.run_series()
wait()
sent = calls[-1]
assert sent['interannual'] == 'std' and not {'other_variable', 'other_sensor'} & set(sent), sent
res = dock.series[-1]
one = dock.series_dialogs[len(dock.series) - 1].chart or results.ChartWidget(
	res['rows'], res['title'], results.ylabel(res), profile=res['profile'], other_unit=results.other_ylabel(res) or '',
	ylim=res['ylim'], other_ylim=res['other_ylim'])
assert one.names == ['NDVI Sentinel-2'] and res['ylim'] is None and one.axis_range(0) != (-1.0, 1.0)
assert results.other_ylabel(res) is None and 'left axis' not in results.series_text(res)
one.resize(600, 320)
one.grab()
assert results.value_range([0.2, 0.4], (-1, 1)) == (-1.0, 1.0) and results.value_range([], None) is None
# the same variable on both axes: a warning, and nothing computed
dock.doy_other.setCurrentIndex(dock.doy_other.findText('NDVI (Sentinel-2)'))
made = len(calls)
dock.run_series()
wait()
assert len(calls) == made and 'is already the variable of the left axis' in messages[-1], messages[-1]
# the annual step: no chart by day of the year, so none of its options
dock.doy_other.setCurrentIndex(ndsi)
dock.step.setCurrentIndex(dock.step.findData('annual'))
dock.run_series()
wait()
assert calls[-1]['doy'] is False and not {'interannual', 'other_variable'} & set(calls[-1]), calls[-1]
dock.doy_other.setCurrentIndex(0)
dock.doy_interannual.setCurrentIndex(0)
dock.doy.setChecked(False)
assert not dock.doy_interannual.isEnabled()
dock.step.setCurrentIndex(dock.step.findData('monthly'))
print('options of the profile:', between)
# the CF of Sentinel-2 on the left axis (its filters greyed out, none checked) and the NDVI on the right one: the filters
# chosen before the CF (those of the NDVI), not those of the CF, as 'auto' (sensors.filters: each variable without the
# filter of what it measures), as services.time_series gives the NDVI without quality
chosen = dock.quality_args()
auto = dict({k: 'auto' if on else False for k, on in chosen.items() if k != 'cloud_score'},
            cloud_score=chosen['cloud_score'])
dock.variable.setCurrentIndex(dock.variable.findText('CF · Sentinel-2', Qt.MatchFlag.MatchStartsWith))
assert dock.variable.currentText().startswith('CF · Sentinel-2') and not any(w.isChecked() for w in dock.filters.values())
dock.doy.setChecked(True)
dock.doy_other.setCurrentIndex(dock.doy_other.findText('NDVI (Sentinel-2)'))
dock.run_series()
wait()
sent = calls[-1]
assert (sent['variable'], sent['other_variable']) == ('CF', 'NDVI') and sent['quality'] == auto, sent
assert any(sent['quality'][f] for f in ('clouds', 'water', 'snow')), sent['quality']
dock.doy_other.setCurrentIndex(0)  # without a right axis: the filters of the panel, as before
dock.run_series()
wait()
assert not any(calls[-1]['quality'][f] for f in ('clouds', 'water', 'snow', 'aerosols')), calls[-1]['quality']
# the NDSI on the left axis (its snow filter greyed out) and the NDVI on the right one, and the other way round: the
# snow filter chosen, as 'auto', leaves the snow in the NDSI and removes it from the NDVI, on either axis
entries = {name: catalog.find(name, 'Sentinel-2') for name in ('NDSI', 'NDVI')}
for left, right in (('NDSI', 'NDVI'), ('NDVI', 'NDSI')):
	dock.variable.setCurrentIndex(dock.variable.findText(f'{left} · Sentinel-2', Qt.MatchFlag.MatchStartsWith))
	dock.doy_other.setCurrentIndex(dock.doy_other.findText(f'{right} (Sentinel-2)'))
	dock.run_series()
	wait()
	sent = calls[-1]
	assert (sent['variable'], sent['other_variable']) == (left, right) and sent['quality'] == auto, sent
	assert not sensors.filters(entries['NDSI'], sent['quality'])['snow']
	assert sensors.filters(entries['NDVI'], sent['quality'])['snow']
dock.doy_other.setCurrentIndex(0)
dock.doy_interannual.setCurrentIndex(0)
dock.doy.setChecked(False)
dock.variable.setCurrentIndex(dock.variable.findText('NDVI · Sentinel-2', Qt.MatchFlag.MatchStartsWith))
assert dock.quality_args() == chosen
print('right axis of the CF, and the NDSI and the NDVI on two axes: the filters',
      sorted(f for f in chosen if chosen[f] is True), "as 'auto'")

# the search of the Earth Engine data catalog, in the theme of the data by its ID (the copy of its index)
dock.theme.setCurrentIndex(dock.theme.findData('earth_engine'))
assert dock.search_row.isVisibleTo(dock) and not dock.community_row.isVisibleTo(dock)
dock.catalog_text.setText('snow cover')
read = []
dock.read_asset = lambda asset=None: read.append(asset)
dock.search_catalog()
assert dock.catalog_found.count() > 0 and 'MODIS/061/MOD10A1' in [dock.catalog_found.itemData(i)
                                                                  for i in range(dock.catalog_found.count())]
dock.catalog_chosen(0)
assert dock.asset_id.text() == dock.catalog_found.itemData(0) and read == [dock.asset_id.text()]
print('catalog search:', dock.catalog_found.count(), 'datasets, first', dock.catalog_found.itemData(0))
# data by their ID on the left axis (a collection, with its own mask: the filters greyed out) and the NDSI of
# Sentinel-2 on the right one: the filters chosen before, as 'auto', so that the NDSI keeps its snow
SNOW = 'MODIS/061/MOD10A1'
dock.asset_id.setText(SNOW)
dock.asset_read({'asset': SNOW, 'type': 'image_collection', 'use': 'collection', 'title': 'MOD10A1',
                 'source': 'Earth Engine data catalog',
                 'bands': [{'band': 'NDSI_Snow_Cover', 'description': 'NDSI snow cover', 'units': '', 'unit': '',
                            'resolution_m': 500.0}],
                 'arguments': {'collection': SNOW, 'band': 'NDSI_Snow_Cover'}, 'notes': [], 'references': [],
                 'credits': []})
assert dock.variable.currentData().get('custom') and not dock.filters['snow'].isEnabled()
dock.doy.setChecked(True)
dock.doy_other.setCurrentIndex(dock.doy_other.findText('NDSI (Sentinel-2)'))
dock.run_series()
wait()
sent = calls[-1]
assert (sent.get('collection'), sent['other_variable']) == (SNOW, 'NDSI') and sent['quality'] == auto, sent
assert not sensors.filters(entries['NDSI'], sent['quality'])['snow']
dock.doy_other.setCurrentIndex(0)
dock.doy_interannual.setCurrentIndex(0)
dock.doy.setChecked(False)
print('data by ID on the left axis, the NDSI on the right one: the filters chosen, as', sent['quality']['snow'])
# the images (fixed layers) whatever the Period, and the map view zoomed out beyond the world (a project in EPSG:4326):
# within the world, not an error about a bbox nobody wrote
dock.region_kind.setCurrentIndex(dock.region_kind.findData('extent'))
iface.canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
iface.canvas.setExtent(QgsRectangle(-200, -110, 200, 110))
assert iface.canvas.extent().xMinimum() < -180 and iface.canvas.extent().yMinimum() < -90
dock.start.setDate(QDate(2020, 1, 1))
dock.end.setDate(QDate(2021, 12, 31))
dock.catalog_text.setText('worldclim')
before = len(messages)
dock.search_catalog()
assert len(messages) == before, messages[before:]
assert 'WORLDCLIM/V1/BIO' in [dock.catalog_found.itemData(i) for i in range(dock.catalog_found.count())]
print('catalog search, world view and fixed images:', dock.catalog_found.count(), 'datasets')
dock.theme.setCurrentIndex(dock.theme.count() - 1)

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
from monitoreo_qgis.dock import figure_layout, layer_credits, references_text  # noqa: E402


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

# a layer of an earlier version of the plugin has its credits at the end of its references, without their heading:
# those of the data of the catalog (Copernicus Sentinel, USGS, Copernicus DEM, FAO GAUL) are found among them
for args in ({'variable': 'NDVI', 'sensor': 'Landsat', 'start': '2020-01-01', 'end': '2020-12-31'},
             {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2023-06-01', 'end': '2023-08-31'},
             {'variable': 'ELEVATION', 'sensor': 'Copernicus'}):
	old = references.cite('map_layer', {'region': {'admin1': 'Andalucía', 'country': 'ESP'}, **args})
	text = 'MonitorEO: NDVI.\n\nReferences (cite them with this layer):\n' + '\n'.join(references.texts(old))
	assert old['credits'] and layer_credits(text) == old['credits'], (layer_credits(text), old['credits'])
	assert layer_credits('MonitorEO: NDVI.' + references_text(old)) == old['credits']
assert layer_credits('A layer of my own') == [] and layer_credits(None) == []
print('credits of the layers of an earlier plugin, without their heading:', len(old['credits']))
plugin.unload()
print('OK')
