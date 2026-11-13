"""MonitorEO panel: region, variable, period and pixel filters, and the buttons of the time series, the map layer (the
map of the variable, the true colour of its images or both) and the exports to Google Drive; in the theme Fire, the
burn severity of a fire. Instead of a variable of the catalog, in the themes Earth Engine data (by its ID) and GEE
Community Catalog: any image or collection of images of Earth Engine given by its ID (read with
services.describe_asset), or a dataset of the GEE Community Catalog chosen by its themes (community_themes,
community_datasets). The work runs in QGIS tasks (QgsTask), so QGIS keeps responding; every computation is a
function of monitoreo.services, the same as in the MCP server and the R package. A bar shows the EECUs of Earth Engine
spent this month (the research EECUs of this user with the shared account, or the monthly quota of the user's project)
and the message bar warns when less than 10 % are left."""

import json
import os
import tempfile

from qgis.core import (Qgis, QgsApplication, QgsColorRampShader, QgsContrastEnhancement, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsDataSourceUri, QgsDateTimeRange, QgsMultiBandColorRenderer,
                       QgsPalettedRasterRenderer, QgsProject, QgsRasterLayer, QgsRasterShader, QgsRectangle,
                       QgsSettings, QgsSingleBandPseudoColorRenderer, QgsTask)
from qgis.gui import QgsCheckableComboBox, QgsCollapsibleGroupBox, QgsFieldComboBox, QgsMapLayerComboBox
from qgis.PyQt.QtCore import QDate, QDateTime, QEvent, QPoint, Qt, QTime, QTimer, QUrl
from qgis.PyQt.QtGui import QColor, QDesktopServices, QPixmap
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDockWidget, QDoubleSpinBox, QFormLayout,
                                 QGroupBox, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QScrollArea,
                                 QMenu, QToolButton, QVBoxLayout, QWhatsThis, QWidget)

from . import deps

deps.setup_path()
from monitoreo import assets, catalog, fire, landcover, services, steps, trends  # noqa: E402
from monitoreo.publish import period_text  # noqa: E402

from .helptexts import HELP, MANUAL, data_help, data_summary, data_use, esc, filters_help, variable_help  # noqa: E402
from .results import KINDS_TIP, MAP_KINDS  # noqa: E402

SETTINGS = 'MonitorEO/'
STEPS = [('Monthly', 'monthly'), ('Annual', 'annual'), ('16 days', '16-day'), ('Daily (days with images)', 'daily')]
METRICS = [('Mean', 'mean'), ('Median', 'median'), ('Minimum', 'min'), ('Maximum', 'max'), ('Percentile 5', 'p5'),
           ('Percentile 10', 'p10'), ('Percentile 90', 'p90'), ('Percentile 95', 'p95')]
STATS = [('Mean', 'mean'), ('Median', 'median'), ('Minimum', 'min'), ('Maximum', 'max'), ('Standard deviation', 'std')]
TEMPORAL = [('Whole period', 'period'), ('Each year, then between years', 'annual'),
            ('Each month, then between years', 'monthly')]
TREND_STEPS = [('Year', 'annual'), ('Months', 'monthly'), ('16 days', '16-day')]
REGIONS = [('Layer (selected features or all)', 'layer'), ('Map extent', 'extent'),
           ('Protected area (WDPA)', 'wdpa'), ('Administrative unit (FAO GAUL)', 'admin'), ('Country', 'country'),
           ('Ecoregion at the center of the map', 'ecoregion'), ('Island at the center of the map', 'island')]
FIRE_SENSORS = [('Sentinel-2 (10 m)', 'Sentinel-2'), ('Landsat (30 m)', 'Landsat')]
# MODIS, only for the burn indices that have it (services.BURN_SENSORS: the RdNBR): the daily surface reflectance of
# Terra or of Aqua (500 m), given to services.burn_severity as the sensor 'Modis' and the collection of each
FIRE_MODIS = [('MODIS Terra (500 m)', 'MODIS/061/MOD09GA'), ('MODIS Aqua (500 m)', 'MODIS/061/MYD09GA')]
FIRE_TIPS = {
	'MODIS/061/MOD09GA': 'Daily surface reflectance of MODIS Terra (MOD09GA, since 2000-02-24), bands 2 and 7, 500 m',
	'MODIS/061/MYD09GA': 'Daily surface reflectance of MODIS Aqua (MYD09GA, since 2002-07-04), bands 2 and 7, 500 m',
	'dNBR': 'NBR before minus NBR after the fire, in the 7 classes of the USGS (Key & Benson 2006)',
	'RBR': 'Relativized Burn Ratio (Parks et al. 2014): a continuous map, without classes',
	'RdNBR': 'Relative dNBR (Miller & Thode 2007): dNBR / sqrt(|NBR before|), in the 4 classes of the article '
	         '(unchanged, low, moderate and high severity); also with MODIS Terra and Aqua',
}
FIRE_INDICES = [('dNBR (USGS classes)', 'dNBR'), ('RBR (continuous, no classes)', 'RBR'),
                ('RdNBR (Miller & Thode 2007 classes)', 'RdNBR')]
# the two periods of the burn severity, at first those of the example of the manual: the fire of August 2023 in Teide
# National Park (Tenerife)
FIRE_DATES = {'before_start': '2023-05-15', 'before_end': '2023-08-14', 'after_start': '2023-09-15',
              'after_end': '2023-11-30'}
POLL_MS = 30000
ALPHA = 0.05  # «Significant pixels only»: the pixels with Mann-Kendall p < ALPHA
MAX_VERTICES = 20000
MAP_PIXELS = 4000000  # maps downloaded as GeoTIFF: at most these pixels (16 MB); bigger regions get bigger pixels
# the data of Earth Engine outside the catalog (monitoreo.assets): images with dates, aggregated in time like the
# variables (collection=), or a fixed image without dates, like the elevation (image=)
USES = [('Images with dates (collection)', 'collection'), ('Fixed image (image)', 'image')]
# their arguments besides collection, which the maps of a result keep (add_result_map)
SOURCE = ('image', 'band', 'band_scale', 'band_offset', 'unit', 'terrain')
NO_FILTERS = ('The data of Earth Engine outside the catalog keep only their own mask: the pixel filters are for the '
              'variables of the catalog')
READ_HINT = ('Write the ID of an image or a collection of images of Earth Engine (e.g. IDAHO_EPSCOR/TERRACLIMATE) and '
             'press Read: its bands, units, licence and how to cite it')


def level(name):
	"""Qgis message level NAME (Info, Warning, Critical, Success) in QGIS 3 and 4."""
	enum = getattr(Qgis, 'MessageLevel', None)
	return getattr(enum, name) if enum is not None and hasattr(enum, name) else getattr(Qgis, name)


def pseudocolor(layer, vmin, vmax, palette, band=1):
	"""Colour the band BAND of LAYER (default: the first) with the colours PALETTE (hex) spread from VMIN to VMAX."""
	if vmax <= vmin:
		vmax = vmin + 1e-6
	n = len(palette)
	items = [QgsColorRampShader.ColorRampItem(vmin + (vmax - vmin) * i / max(n - 1, 1), QColor('#' + c.lstrip('#')),
	                                          f'{vmin + (vmax - vmin) * i / max(n - 1, 1):.4g}')
	         for i, c in enumerate(palette)]
	ramp = QgsColorRampShader(vmin, vmax)
	ramp.setColorRampItemList(items)
	shader = QgsRasterShader()
	shader.setRasterShaderFunction(ramp)
	renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), band, shader)
	renderer.setClassificationMin(vmin)
	renderer.setClassificationMax(vmax)
	layer.setRenderer(renderer)


def rgb(layer, lo, hi, bands=(1, 2, 3)):
	"""Show the bands BANDS of LAYER (default: the first three, those of a true colour, red, green and blue) as its
	red, green and blue, the three stretched together from LO to HI (one range for the three, as in the other tools,
	so that the colours keep their balance)."""
	if hi <= lo:
		hi = lo + 1e-6
	provider = layer.dataProvider()
	renderer = QgsMultiBandColorRenderer(provider, *bands)
	for band, set_enhancement in zip(bands, (renderer.setRedContrastEnhancement, renderer.setGreenContrastEnhancement,
	                                         renderer.setBlueContrastEnhancement)):
		enhancement = QgsContrastEnhancement(provider.dataType(band))
		enhancement.setContrastEnhancementAlgorithm(
			QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum)
		enhancement.setMinimumValue(lo)
		enhancement.setMaximumValue(hi)
		set_enhancement(enhancement)
	layer.setRenderer(renderer)


def rgb_caption(lo, hi):
	"""The legend of a true colour shown from LO to HI (reflectance), as in the other tools."""
	return f'True colour (red, green, blue): reflectance from {lo:.4g} to {hi:.4g}'


def paletted(layer, band, classes):
	"""Colour the band BAND of LAYER with a colour for each of its values (a paletted renderer: unique values), from
	CLASSES ([{'value', 'color' ('#rrggbb'), 'label'}]); the legend of the layer shows their labels."""
	items = [QgsPalettedRasterRenderer.Class(c['value'], QColor(c['color']), c['label']) for c in classes]
	layer.setRenderer(QgsPalettedRasterRenderer(layer.dataProvider(), band, items))


def dated(layer, first, last):
	"""Give LAYER the days FIRST to LAST (YYYY-MM-DD) in the Temporal Controller of QGIS."""
	props = layer.temporalProperties()
	props.setMode(Qgis.RasterTemporalMode.FixedTemporalRange)
	begin = QDateTime(QDate.fromString(first, 'yyyy-MM-dd'), QTime(0, 0))
	end = QDateTime(QDate.fromString(last, 'yyyy-MM-dd').addDays(1), QTime(0, 0))
	props.setFixedTemporalRange(QgsDateTimeRange(begin, end, True, False))
	props.setIsActive(True)


def references_text(res):
	"""The references and credits of a result (monitoreo.references), for the abstract of its layer."""
	from monitoreo import references
	lines = references.texts(res) if res.get('references') else []
	return ('\n\nReferences (cite them with this layer):\n' + '\n'.join(lines)) if lines else ''


def add_layer(layer, group=None):
	"""Add LAYER to the project, on top of the layer tree or of GROUP."""
	if group is None:
		QgsProject.instance().addMapLayer(layer)
	else:
		QgsProject.instance().addMapLayer(layer, False)
		group.insertLayer(0, layer)


def result_maps(tool, args):
	"""The maps that the window of a result of TOOL ('time_series' or 'trend_table') with ARGS offers: that of its
	whole period (of a trend, the trend of the values of each year) and those of each of its steps (its years, months
	or periods of 16 days; of a trend, its parts of the year), as in the assistant (see monitoreo.steps)."""
	period = period_text(args['start'], args['end'])
	if tool == 'trend_table':
		main = {'key': '', 'label': f'Annual trend ({period})', 'step': 'annual'}
	else:
		main = {'key': '', 'label': f'Whole period ({period})', 'start': args['start'], 'end': args['end']}
	return [main] + steps.map_steps(tool, args)


def true_colour(region, opts, path, resolution=None, stretch=None):
	"""The true colour of the images of the map with the arguments OPTS (services.download_rgb: the GeoTIFF PATH with
	the bands red, green and blue, on the grid of pixels of RESOLUTION m, that of the map, so that their pixels match)
	or, if it cannot be downloaded, its Earth Engine tiles (services.rgb_map, stretched from STRETCH[0] to STRETCH[1]
	if given). In a task."""
	try:
		return services.download_rgb(region, path=path, resolution=resolution, max_pixels=MAP_PIXELS, **opts)
	except Exception as e:
		out = services.rgb_map(region, **opts, **({'vmin': stretch[0], 'vmax': stretch[1]} if stretch else {}))
		out['error'] = str(e)
		return out


def maps_work(kind, region, opts, folder, download, tiles, colors=None, stretch=None):
	"""The layers of a map with the arguments OPTS, in a task: with KIND 'index' or 'both', the map of the variable
	(DOWNLOAD: the GeoTIFF map.tif of FOLDER or, if it cannot be downloaded, TILES, with the colours COLORS (min, max)
	if given); with KIND 'rgb' or 'both', the true colour of the same images and pixels (rgb.tif, on the grid of the
	map; see true_colour). Returns {'index', 'rgb'} (those asked for) and, if only the true colour of 'both' failed,
	'rgb_error' instead of 'rgb' (the map is added all the same)."""
	out = {}
	if kind != 'rgb':
		try:
			out['index'] = download(region, path=os.path.join(folder, 'map.tif'), max_pixels=MAP_PIXELS, **opts)
		except Exception as e:
			out['index'] = tiles(region, **opts, **({'vmin': colors[0], 'vmax': colors[1]} if colors else {}))
			out['index']['error'] = str(e)
	if kind != 'index':
		try:
			out['rgb'] = true_colour(region, opts, os.path.join(folder, 'rgb.tif'),
			                         (out.get('index') or {}).get('resolution'), stretch)
		except Exception as e:
			if kind == 'rgb':
				raise
			out['rgb_error'] = str(e)
	return out


def data_name(var, sensor=True):
	"""What the arguments VAR compute, for the titles of the tasks: the variable of the catalog with its sensor (with
	SENSOR: NDVI (Sentinel-2)), or the ID and band of the data of Earth Engine outside it (IDAHO_EPSCOR/TERRACLIMATE
	pr), which have no variable nor sensor."""
	if var.get('variable'):
		return f"{var['variable']} ({var['sensor']})" if sensor else var['variable']
	return f"{var.get('collection') or var.get('image') or '?'} {var.get('band') or ''}".strip()


def burn_label(title, collection=None):
	"""The name of a burn severity of title TITLE in the list of results and of its layer: TITLE, with the product of
	MODIS of COLLECTION after the sensor (Modis MYD09GA), so that Terra and Aqua can be told apart, if it does not say
	it already."""
	short = str(collection or '').split('/')[-1]
	if not short or short in title:
		return title
	return title.replace(' Modis ', f' Modis {short} ', 1)


def number(value):
	"""VALUE (a number, or None) as the text of a field: '' if None."""
	return '' if value is None else format(float(value), '.10g')


def unit_text(res):
	"""The unit of the values of the map RES for its abstract ('[NDVI]', 'mm', 'mm / year' of a trend): '(unit not
	given)' for the data of Earth Engine outside the catalog computed without one (whose trends have ' / year')."""
	unit = str(res.get('unit') or '').strip()
	return '(unit not given)' if not unit or unit.startswith('/') else unit


def combo(items, current=None):
	c = QComboBox()
	for label, value in items:
		c.addItem(label, value)
	if current is not None:
		c.setCurrentIndex([v for _, v in items].index(current))
	return c


class InfoButton(QToolButton):
	"""Small button ⓘ beside an option: a click shows its help (TEXT, or TEXT() if it is a function) in a balloon
	that stays until the next click; its links open in the browser."""

	def __init__(self, text):
		super().__init__()
		self.help_text = text
		icon = QgsApplication.getThemeIcon('/mActionPropertiesWidget.svg')  # a blue ⓘ in QGIS 3 and 4
		if icon.isNull():
			self.setText('ⓘ')
		else:
			self.setIcon(icon)
		self.setAutoRaise(True)
		self.setToolTip('Help')
		self.clicked.connect(self.show_help)

	def help(self):
		return self.help_text() if callable(self.help_text) else self.help_text

	def show_help(self):
		QWhatsThis.showText(self.mapToGlobal(QPoint(0, self.height())), self.help(), self)

	def event(self, e):
		if e.type() == QEvent.Type.WhatsThisClicked:  # a link of the balloon
			QDesktopServices.openUrl(QUrl(e.href()))
			QWhatsThis.hideText()
			return True
		return super().event(e)


def plugin_version():
	"""The version of the plugin, from its metadata.txt."""
	import configparser
	meta = configparser.ConfigParser()
	meta.read(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'metadata.txt'), encoding='utf-8')
	return meta.get('general', 'version', fallback='?')


def info(field, text):
	"""FIELD (a widget, or a row of them) with an InfoButton with TEXT at its right, for a row of a QFormLayout."""
	if isinstance(field, QHBoxLayout):
		row = field
	else:
		row = QHBoxLayout()
		row.addWidget(field, 1)
	row.addWidget(InfoButton(text))
	return row


class MonitorEODock(QDockWidget):

	def __init__(self, iface):
		super().__init__('MonitorEO')
		self.iface = iface
		self.setObjectName('MonitorEODock')
		self.tasks = []          # running QgsTasks (kept so that Python does not delete them)
		self.series = []         # results of the time series of this session
		self.series_dialogs = {}  # their windows, by index in self.series
		self.exports = []        # export tasks of Earth Engine being followed
		self.timer = QTimer(self)
		self.timer.timeout.connect(self.poll_exports)
		self.eecu_warned = set()  # (project, account, month) whose warning of few EECUs left was shown
		self.build()
		QTimer.singleShot(0, self.check_eecu)

	# Interface --------------------------------------------------------------------------------------------------

	def build(self):
		s = QgsSettings()
		body = QWidget()
		main = QVBoxLayout(body)
		row = QHBoxLayout()
		row.addStretch()
		row.addWidget(self.feedback_button())
		main.addLayout(row)

		box = QGroupBox('Google Earth Engine')
		f = QFormLayout(box)
		self.project = QLineEdit(s.value(SETTINGS + 'project', os.environ.get('EE_PROJECT', '')))
		self.project.setPlaceholderText('empty: shared account of MonitorEO · or your Google Cloud project')
		row = QHBoxLayout()
		row.addWidget(self.project)
		b = QPushButton('Connect')
		b.clicked.connect(self.connect)
		row.addWidget(b)
		b = QPushButton('Authenticate…')
		b.setToolTip('Sign in with your Google account in the browser (as earthengine authenticate), to compute with '
		             'your project and export to Google Drive')
		b.clicked.connect(self.authenticate)
		row.addWidget(b)
		f.addRow('Project', info(row, HELP['project']))
		row = QHBoxLayout()
		self.eecu_bar = QProgressBar()
		self.eecu_bar.setRange(0, 100)
		self.eecu_bar.setValue(0)
		self.eecu_bar.setFormat('not checked yet')
		self.eecu_bar.setToolTip('EECUs (compute units of Earth Engine) spent this month')
		row.addWidget(self.eecu_bar, 1)
		tier = s.value(SETTINGS + 'eecu_tier', 'Community')
		self.eecu_tier = combo([(k, k) for k in services.EECU_TIERS],
		                       tier if tier in services.EECU_TIERS else 'Community')
		self.eecu_tier.setToolTip('Earth Engine tier of your project, with its monthly quota: Community 150 EECU-hours, '
		                          'Contributor 1,000, Partner 100,000 (not used with the shared account)')
		self.eecu_tier.currentIndexChanged.connect(lambda i: self.check_eecu())
		row.addWidget(self.eecu_tier)
		b = QPushButton('Check')
		b.setToolTip('Ask again for the EECUs spent this month')
		b.clicked.connect(lambda: self.check_eecu(refresh=True, asked=True))
		row.addWidget(b)
		self.eecu_label = QLabel('EECUs of the month')
		f.addRow(self.eecu_label, info(row, HELP['eecu']))
		main.addWidget(box)

		box = QGroupBox('Region')
		f = QFormLayout(box)
		self.region_kind = combo(REGIONS)
		self.region_kind.currentIndexChanged.connect(self.region_changed)
		f.addRow('Region', info(self.region_kind, HELP['region']))
		self.layer = QgsMapLayerComboBox()
		self.layer.setFilters(Qgis.LayerFilter.PolygonLayer)
		self.name_field = QgsFieldComboBox()
		self.name_field.setAllowEmptyFieldName(True)
		self.layer.layerChanged.connect(lambda layer: self.sync_fields())
		# the layer box can pick a new layer by itself without layerChanged (QGIS 4): follow the project too, and stop
		# following it in stop(), or the project would call this panel once deleted (when the plugin is reloaded)
		self.project_signals = [QgsProject.instance().layersAdded, QgsProject.instance().layersRemoved]
		for signal in self.project_signals:
			signal.connect(self.project_layers_changed)
		self.sync_fields()
		self.layer_row = QWidget()
		lf = QFormLayout(self.layer_row)
		lf.setContentsMargins(0, 0, 0, 0)
		lf.addRow('Layer', info(self.layer, HELP['layer']))
		lf.addRow('Name', info(self.name_field, HELP['name_field']))
		f.addRow(self.layer_row)
		self.wdpa_row = QWidget()
		wl = QHBoxLayout(self.wdpa_row)
		wl.setContentsMargins(0, 0, 0, 0)
		self.wdpa_text = QLineEdit()
		self.wdpa_text.setPlaceholderText('name of the area (e.g. Sierra Nevada)')
		self.wdpa_text.returnPressed.connect(self.search_wdpa)
		wl.addWidget(self.wdpa_text)
		self.ramsar = QCheckBox('Ramsar only')
		self.ramsar.setToolTip('Only the Ramsar sites (Wetlands of International Importance)')
		wl.addWidget(self.ramsar)
		b = QPushButton('Search')
		b.clicked.connect(self.search_wdpa)
		wl.addWidget(b)
		wl.addWidget(InfoButton(HELP['wdpa']))
		f.addRow(self.wdpa_row)
		self.wdpa = QComboBox()
		self.wdpa_field = QWidget()  # the list and its ⓘ, shown only with the region WDPA
		row = info(self.wdpa, HELP['wdpa_area'])
		row.setContentsMargins(0, 0, 0, 0)
		self.wdpa_field.setLayout(row)
		f.addRow('Area', self.wdpa_field)
		self.wdpa_label = f.labelForField(self.wdpa_field)
		self.admin_row = QWidget()  # administrative units of FAO GAUL 2025: search by name, level and country
		al = QHBoxLayout(self.admin_row)
		al.setContentsMargins(0, 0, 0, 0)
		self.admin_text = QLineEdit()
		self.admin_text.setPlaceholderText('name of the unit (e.g. Granada)')
		self.admin_text.returnPressed.connect(self.search_admin)
		al.addWidget(self.admin_text)
		self.admin_level = combo([('Level 1', 1), ('Level 2', 2)])
		self.admin_level.setToolTip('Level 1: regions, states, provinces...; level 2: provinces, districts, '
		                            'municipalities...')
		al.addWidget(self.admin_level)
		self.admin_country = QLineEdit()
		self.admin_country.setPlaceholderText('ISO3')
		self.admin_country.setToolTip('Country (ISO3 code, e.g. ESP): optional')
		self.admin_country.setMaximumWidth(60)
		al.addWidget(self.admin_country)
		b = QPushButton('Search')
		b.clicked.connect(self.search_admin)
		al.addWidget(b)
		al.addWidget(InfoButton(HELP['admin']))
		f.addRow(self.admin_row)
		self.admin = QComboBox()
		f.addRow('Unit', self.admin)
		self.admin_label = f.labelForField(self.admin)
		self.country = QLineEdit()
		self.country.setPlaceholderText('ISO3 code of the country (e.g. ESP)')
		self.country_field = QWidget()
		row = info(self.country, HELP['country'])
		row.setContentsMargins(0, 0, 0, 0)
		self.country_field.setLayout(row)
		f.addRow('Country', self.country_field)
		self.country_label = f.labelForField(self.country_field)
		main.addWidget(box)
		self.landcover_group(s, main)

		box = QGroupBox('Variable')
		f = QFormLayout(box)
		# first the theme (catalog.THEMES), then the variables of that theme; after them, as in the Earth Engine app,
		# the themes of the data of Earth Engine outside the catalog (catalog.OTHER_THEMES, with 'data'), which have no
		# variables: any image or collection by its ID, and the GEE Community Catalog
		self.theme = QComboBox()
		themes = services.themes('en')
		for t in themes:
			self.theme.addItem(t['name'], t['key'])
		self.theme.addItem('All the variables', None)
		self.data_themes = {t['key']: t['data'] for t in themes if t.get('data')}
		f.addRow('Theme', info(self.theme, HELP['theme']))
		f.addRow(self.data_block(s))
		# the English names of the catalog (vname_en, type_en); RBR and RdNBR, which compare two periods: only the burn
		# severity (Burn severity of a fire, below)
		self.all_variables = [v for v in services.list_variables(lang='en') if not v.get('two_periods')]
		self.catalog_choice = None  # the variable chosen before a theme of other data, chosen again when back
		self.variable = QComboBox()
		self.variable_field = QWidget()  # the list and its ⓘ, hidden in the themes of other data
		row = info(self.variable, lambda: variable_help(self.variable.currentData(), self.described()))
		row.setContentsMargins(0, 0, 0, 0)
		self.variable_field.setLayout(row)
		f.addRow('Variable', self.variable_field)
		self.variable_label = f.labelForField(self.variable_field)
		self.fill_variables('NDVI · Sentinel-2')
		self.theme.currentIndexChanged.connect(lambda i: self.fill_variables())
		self.start = QDateEdit(QDate.fromString(s.value(SETTINGS + 'start', '2020-01-01'), 'yyyy-MM-dd'))
		self.end = QDateEdit(QDate.fromString(s.value(SETTINGS + 'end', '2021-12-31'), 'yyyy-MM-dd'))
		for d in (self.start, self.end):
			d.setCalendarPopup(True)
			d.setDisplayFormat('yyyy-MM-dd')
		row = QHBoxLayout()
		row.addWidget(self.start)
		row.addWidget(QLabel('to'))
		row.addWidget(self.end)
		f.addRow('Period', info(row, HELP['period']))
		self.compare_on = QCheckBox('other period:')
		self.compare_on.setToolTip('Compares the reference period (the one above) with this one: the time series gives '
		                           'the mean of each part of the year in the two periods and their difference, and the '
		                           'map, the difference (this period minus the reference period)')
		self.other_start = QDateEdit(QDate.fromString(s.value(SETTINGS + 'other_start', '2023-01-01'), 'yyyy-MM-dd'))
		self.other_end = QDateEdit(QDate.fromString(s.value(SETTINGS + 'other_end', '2023-12-31'), 'yyyy-MM-dd'))
		row = QHBoxLayout()
		row.addWidget(self.compare_on)
		for i, d in enumerate((self.other_start, self.other_end)):
			d.setCalendarPopup(True)
			d.setDisplayFormat('yyyy-MM-dd')
			d.setEnabled(False)
			self.compare_on.toggled.connect(d.setEnabled)
			if i:
				row.addWidget(QLabel('to'))
			row.addWidget(d)
		f.addRow('Compare with', info(row, HELP['compare']))
		self.season_on = QCheckBox('only')
		self.season_start = QLineEdit('06-01')
		self.season_end = QLineEdit('09-30')
		for w in (self.season_start, self.season_end):
			w.setMaximumWidth(60)
			w.setPlaceholderText('MM-DD')
		row = QHBoxLayout()
		row.addWidget(self.season_on)
		row.addWidget(self.season_start)
		row.addWidget(QLabel('to'))
		row.addWidget(self.season_end)
		row.addWidget(QLabel('of each year'))
		row.addStretch()
		f.addRow('Season', info(row, HELP['season']))
		self.filters = {}
		self.chosen_filters = None  # the filters checked by the user while a variable with fixed filters is chosen
		row = QHBoxLayout()
		for key, label in (('clouds', 'clouds'), ('water', 'water'), ('snow', 'snow'), ('aerosols', 'aerosols')):
			self.filters[key] = QCheckBox(label)
			self.filters[key].setChecked(True)
			row.addWidget(self.filters[key])
		f.addRow('Remove pixels with', info(row, lambda: filters_help(self.variable.currentData())))
		self.cloud_score = QCheckBox('Sentinel-2 clouds with Cloud Score+')  # unchecked, with SCL: in its help ⓘ
		self.cloud_score.setChecked(True)
		f.addRow('', info(self.cloud_score, HELP['cloud_score']))
		# where: up to two conditions on variables, the only pixels of the region that pass them all
		self.where = []
		for i, default in enumerate(('ELEVATION · Copernicus', 'SLOPE · Copernicus')):
			on, var, lo, hi, unit = QCheckBox(), QComboBox(), QLineEdit(), QLineEdit(), QLabel('')
			for v in services.list_variables(lang='en'):
				if not v.get('two_periods'):
					var.addItem(f"{v['variable']} · {v['sensor']}", v)
					var.setItemData(var.count() - 1, f"{v['name']} ({v['unit']}), {v['dates']}",
					                Qt.ItemDataRole.ToolTipRole)
			var.setCurrentIndex(max(0, var.findText(default, Qt.MatchFlag.MatchStartsWith)))
			for w, text in ((lo, 'min'), (hi, 'max')):
				w.setPlaceholderText(text)
				w.setMaximumWidth(70)
			row = QHBoxLayout()
			row.addWidget(on)
			row.addWidget(var, 1)
			f.addRow('Only the pixels where' if i == 0 else 'and where', info(row, HELP['where']) if i == 0 else row)
			row = QHBoxLayout()
			for w in (QLabel('between'), lo, QLabel('and'), hi, unit):
				row.addWidget(w)
			row.addStretch()
			f.addRow('', row)
			condition = {'on': on, 'variable': var, 'min': lo, 'max': hi, 'unit': unit}
			self.where.append(condition)
			on.toggled.connect(self.where_changed)
			var.currentIndexChanged.connect(self.where_changed)
		main.addWidget(box)

		box = QGroupBox('Time series')
		self.series_box = box  # greyed out for the fixed layers without dates (elevation, slope)
		f = QFormLayout(box)
		self.step = combo(STEPS, 'monthly')
		self.ts_metric = combo(METRICS, 'mean')
		self.stat = combo(STATS, 'mean')
		f.addRow('Step', info(self.step, HELP['step']))
		f.addRow('Metric of each step', info(self.ts_metric, HELP['ts_metric']))
		f.addRow('Statistic of the region', info(self.stat, HELP['stat']))
		b = QPushButton('Compute the time series')
		b.clicked.connect(self.run_series)
		f.addRow(b)
		self.series_list = QComboBox()  # the series computed in this session, to open them again
		self.series_list.setToolTip('Series computed in this QGIS session')
		self.show_series_button = QPushButton('Show')
		self.show_series_button.setToolTip('Open again the chart and the table of the chosen series')
		self.show_series_button.clicked.connect(self.show_series)
		row = QHBoxLayout()
		row.addWidget(self.series_list, 1)
		row.addWidget(self.show_series_button)
		f.addRow('Series', info(row, HELP['series_list']))
		self.update_series_list()
		main.addWidget(box)

		box = QGroupBox('Trends (Mann-Kendall and Sen)')
		self.trends_box = box
		box.setToolTip("Trend of each part of the year over the years of the period: Kendall's τ, Mann-Kendall Z and "
		               "p-value, and Sen's slope (change per year). Better with 8 years or more")
		f = QFormLayout(box)
		self.trend_step = combo(TREND_STEPS, 'annual')
		self.trend_part = QComboBox()
		self.trend_step.currentIndexChanged.connect(self.update_trend_parts)
		self.update_trend_parts()
		self.trend_metric = combo(METRICS, 'mean')
		self.trend_alpha = QCheckBox('only pixels with a significant trend (p < 0.05)')
		f.addRow('Parts of the year', info(self.trend_step, HELP['trend_step']))
		f.addRow('Metric of each year', info(self.trend_metric, HELP['trend_metric']))
		b = QPushButton('Trend table of the region')
		b.setToolTip('Trend of each part of the year of the statistic of the region (that of the time series)')
		b.clicked.connect(self.run_trend_table)
		f.addRow(b)
		f.addRow('Part of the year of the map', info(self.trend_part, HELP['trend_part']))
		f.addRow('', info(self.trend_alpha, HELP['trend_alpha']))
		b = QPushButton('Trend map')
		b.setToolTip("Temporary GeoTIFF with Sen's slope, τ, Z, p-value, intercept and number of years of each pixel "
		             '(queryable with the Identify Features tool)')
		b.clicked.connect(self.run_trend_map)
		f.addRow(b)
		main.addWidget(box)

		box = QGroupBox('Map')
		f = QFormLayout(box)
		self.map_metric = combo(METRICS, 'median')
		self.temporal = combo(TEMPORAL, 'period')
		self.interannual = combo(METRICS[:4], 'mean')
		f.addRow('Metric', info(self.map_metric, HELP['map_metric']))
		f.addRow('Temporal aggregation', info(self.temporal, HELP['temporal']))
		f.addRow('Metric between years', info(self.interannual, HELP['interannual']))
		self.map_kind = combo(MAP_KINDS, 'index')  # the map of the variable, its true colour or both
		f.addRow('Layer', info(self.map_kind, HELP['map_kind']))
		b = QPushButton('Add the layer to the map')
		b.setToolTip('Downloads the map as a temporary GeoTIFF, with the values of the variable (queryable with the '
		             'Identify Features tool) or, with Layer, its true colour, at the resolution of the data or, in '
		             f'big regions, with bigger pixels (up to {MAP_PIXELS / 1e6:g} million pixels)')
		b.clicked.connect(self.run_map)
		f.addRow(b)
		main.addWidget(box)
		self.compare_on.toggled.connect(lambda on: self.update_map_kind())

		box = QGroupBox('Export to Google Drive')
		f = QFormLayout(box)
		self.resolution = QDoubleSpinBox()
		self.resolution.setRange(0, 100000)
		self.resolution.setSpecialValueText('that of the data')
		self.resolution.setSuffix(' m')
		f.addRow('Resolution', info(self.resolution, HELP['resolution']))
		self.folder = QLineEdit(s.value(SETTINGS + 'folder', 'MonitorEO'))
		f.addRow('Drive folder', info(self.folder, HELP['folder']))
		row = QHBoxLayout()
		b = QPushButton('Map (GeoTIFF)')
		b.clicked.connect(self.run_export_image)
		row.addWidget(b)
		b = QPushButton('Series (CSV)')
		b.clicked.connect(self.run_export_series)
		self.export_series_button = b
		row.addWidget(b)
		f.addRow(row)
		self.export_status = QLabel('')
		self.export_status.setWordWrap(True)
		f.addRow(self.export_status)
		main.addWidget(box)

		# the analyses of a theme (catalog.THEMES): only in the themes that have them, and with «All the variables»
		box = QGroupBox('Burn severity of a fire (dNBR, RBR or RdNBR)')
		self.fire_box = box
		f = QFormLayout(box)
		# first the index, as its sensors depend on it (MODIS only for the RdNBR)
		self.fire_index = combo(FIRE_INDICES, 'dNBR')
		for i, (_, value) in enumerate(FIRE_INDICES):
			self.fire_index.setItemData(i, FIRE_TIPS[value], Qt.ItemDataRole.ToolTipRole)
		f.addRow('Index', info(self.fire_index, HELP['fire_index']))
		self.fire_sensor = QComboBox()
		self.fill_fire_sensors(s.value(SETTINGS + 'fire_sensor', 'Sentinel-2'))
		self.fire_index.currentIndexChanged.connect(lambda i: self.fill_fire_sensors())
		f.addRow('Sensor', info(self.fire_sensor, HELP['fire_sensor']))
		self.fire_dates = {}
		for when, label in (('before', 'Before the fire'), ('after', 'After the fire')):
			row = QHBoxLayout()
			for i, key in enumerate((f'{when}_start', f'{when}_end')):
				d = QDateEdit(QDate.fromString(s.value(SETTINGS + 'fire_' + key, FIRE_DATES[key]), 'yyyy-MM-dd'))
				d.setCalendarPopup(True)
				d.setDisplayFormat('yyyy-MM-dd')
				self.fire_dates[key] = d
				if i:
					row.addWidget(QLabel('to'))
				row.addWidget(d)
			f.addRow(label, info(row, HELP['fire_' + when]))
		b = QPushButton('Compute the severity')
		b.setToolTip('Hectares of each class of the USGS (dNBR) or of Miller & Thode 2007 (RdNBR, also its statistics), '
		             'or statistics of the RBR, over each feature of the region, in a window, and a temporary GeoTIFF '
		             'with its colours (queryable with the Identify Features tool)')
		b.clicked.connect(self.run_burn)
		f.addRow(b)
		main.addWidget(box)
		self.theme.currentIndexChanged.connect(lambda i: self.show_analyses())
		self.show_analyses()
		# the options that do not apply to the variable: the other metrics of the SCF, the filters and the dates of the
		# fixed layers (elevation, slope)
		self.variable.currentIndexChanged.connect(self.variable_changed)
		self.where_changed()  # also variable_changed
		main.addWidget(self.about_box())
		main.addStretch()

		scroll = QScrollArea()
		scroll.setWidgetResizable(True)
		scroll.setWidget(body)
		self.setWidget(scroll)
		self.region_changed()

	def data_block(self, s):
		"""The options of the data of Earth Engine outside the catalog, shown in their themes instead of the list
		Variable (with the settings S): the theme and the dataset of the GEE Community Catalog (only in its theme), the
		ID of an image or a collection of images with the button Read (services.describe_asset), its band, how it is
		used (images with dates or a fixed image), the scale, offset and unit of its values, and what its record says.
		Their values reach the list Variable as an entry of it (custom_entry), so that the panel greys out what does
		not apply to them as it does for the variables of the catalog."""
		self.asset_info = None  # what services.describe_asset said of the last ID read
		self.community_records = {}  # the records of the datasets listed, by ID
		self.data_row = QWidget()
		form = QFormLayout(self.data_row)
		form.setContentsMargins(0, 0, 0, 0)
		self.community_row = QWidget()  # the GEE Community Catalog: from the copy of its index (no Earth Engine)
		cf = QFormLayout(self.community_row)
		cf.setContentsMargins(0, 0, 0, 0)
		self.community_theme = QComboBox()
		for t in services.community_themes('en'):
			self.community_theme.addItem(f"{t['name']} ({t['datasets']})", t['theme'])
		self.community_theme.setCurrentIndex(max(0, self.community_theme.findData(
			s.value(SETTINGS + 'community_theme', ''))))
		cf.addRow('Theme of the catalog', info(self.community_theme, HELP['community_theme']))
		self.community_dataset = QComboBox()
		self.community_dataset.setPlaceholderText('choose the dataset')  # as the Earth Engine app
		self.community_dataset.activated.connect(self.dataset_chosen)  # only a choice of the user reads it
		cf.addRow('Dataset', info(self.community_dataset, HELP['community_dataset']))
		self.fill_datasets()
		self.community_theme.currentIndexChanged.connect(lambda i: self.fill_datasets())
		form.addRow(self.community_row)
		self.asset_id = QLineEdit(s.value(SETTINGS + 'asset', ''))
		self.asset_id.setPlaceholderText('e.g. IDAHO_EPSCOR/TERRACLIMATE or projects/sat-io/open-datasets/FABDEM')
		self.asset_id.returnPressed.connect(self.read_asset)
		row = QHBoxLayout()
		row.addWidget(self.asset_id, 1)
		b = QPushButton('Read')
		b.setToolTip('Reads in Earth Engine what this ID is (an image or a collection of images) and its bands; for the '
		             'Earth Engine data catalog, also their units, scale and offset, its licence and how to cite it')
		b.clicked.connect(lambda checked=False: self.read_asset())
		row.addWidget(b)
		form.addRow('Earth Engine ID', info(row, lambda: data_help(self.variable.currentData(), self.described())))
		self.asset_band = QComboBox()  # the bands read, or one written
		self.asset_band.setEditable(True)
		self.asset_band.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
		self.asset_band.setEditText(s.value(SETTINGS + 'asset_band', ''))
		self.asset_band.lineEdit().setPlaceholderText('press Read, or write it')
		form.addRow('Band', info(self.asset_band, HELP['asset_band']))
		use = s.value(SETTINGS + 'asset_use', 'collection')
		self.asset_use = combo(USES, use if use in dict(USES).values() else 'collection')
		form.addRow('Use as', info(self.asset_use, HELP['asset_use']))
		self.band_scale = QLineEdit(s.value(SETTINGS + 'band_scale', ''))
		self.band_scale.setPlaceholderText('1: the values as stored')
		form.addRow('Band scale', info(self.band_scale, HELP['band_scale']))
		self.band_offset = QLineEdit(s.value(SETTINGS + 'band_offset', ''))
		self.band_offset.setPlaceholderText('0')
		form.addRow('Band offset', info(self.band_offset, HELP['band_offset']))
		self.asset_unit = QLineEdit(s.value(SETTINGS + 'asset_unit', ''))
		self.asset_unit.setPlaceholderText('e.g. mm, degC, kg m-2, mm day-1 or 1 (dimensionless)')
		form.addRow('Unit (UDUNITS)', info(self.asset_unit, HELP['asset_unit']))
		self.asset_label = QLabel(READ_HINT)  # title, source, licence and page of the data read
		self.asset_label.setWordWrap(True)
		self.asset_label.setOpenExternalLinks(True)
		self.asset_label.setStyleSheet('font-size: 11px; color: #444;')
		form.addRow(self.asset_label)
		# connected once filled: every change reaches the entry of the list Variable
		self.asset_id.textEdited.connect(lambda text: self.asset_edited())
		self.asset_id.textChanged.connect(lambda text: self.custom_changed())
		self.asset_band.currentIndexChanged.connect(lambda i: self.band_changed())
		self.asset_band.currentTextChanged.connect(lambda text: self.custom_changed())
		self.asset_use.currentIndexChanged.connect(lambda i: self.custom_changed())
		for w in (self.band_scale, self.band_offset, self.asset_unit):
			w.textChanged.connect(lambda text: self.custom_changed())
		return self.data_row

	def sync_fields(self):
		layer = self.layer.currentLayer()
		if self.name_field.layer() is not layer:
			self.name_field.setLayer(layer)

	def region_changed(self):
		kind = self.region_kind.currentData()
		self.layer_row.setVisible(kind == 'layer')
		for widgets, shown in (((self.wdpa_row, self.wdpa_field, self.wdpa_label), kind == 'wdpa'),
		                       ((self.admin_row, self.admin, self.admin_label), kind == 'admin'),
		                       ((self.country_field, self.country_label), kind == 'country')):
			for w in widgets:
				if w is not None:
					w.setVisible(shown)

	def message(self, text, lvl='Info', duration=6):
		self.iface.messageBar().pushMessage('MonitorEO', text, level=level(lvl), duration=duration)

	def feedback_button(self):
		"""The button to suggest a change or report an error: an issue of GitHub or the anonymous form, filled with
		the plugin and its version (see monitoreo.about.feedback)."""
		from monitoreo import __version__, about
		texts = about.FEEDBACK['en']
		links = about.feedback('qgis', f'{plugin_version()} (monitoreo {__version__})')
		button = QToolButton()
		button.setText(texts['button'])
		button.setToolTip('Opens a new issue of GitHub, or the anonymous form, in the browser')
		button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
		menu = QMenu(button)
		for key in ('issue', 'form'):
			action = menu.addAction(texts[key])
			action.triggered.connect(lambda checked=False, url=links[key]: QDesktopServices.openUrl(QUrl(url)))
		button.setMenu(menu)
		self.feedback_links = links
		return button

	def about_box(self):
		"""What MonitorEO-OBSNEV is, who funds it and how to cite it, with the logos of the institutions and projects."""
		from monitoreo import about
		box = QGroupBox('About MonitorEO')
		lay = QVBoxLayout(box)
		for path in about.about('en')['logos']:
			logo = QLabel()
			logo.setPixmap(QPixmap(path).scaled(330, 48, Qt.AspectRatioMode.KeepAspectRatio,
			                                    Qt.TransformationMode.SmoothTransformation))
			logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
			lay.addWidget(logo)
		doi = f'https://doi.org/{about.DOI}'
		gee = 'https://doi.org/10.1016/j.rse.2017.06.031'
		for text in (about.DESCRIPTION['en'], about.ACKNOWLEDGEMENTS['en'],
		             f"<b>{about.HOW_TO_CITE['en']}:</b> " + about.CITATION.replace(doi, f'<a href="{doi}">{doi}</a>'),
		             f"{about.CITE_ALSO['en']}: " + about.EARTH_ENGINE.replace(gee, f'<a href="{gee}">{gee}</a>'),
		             f'<a href="{MANUAL}">Manual</a> · <a href="{about.REPOSITORY}">Code</a>'):
			label = QLabel(text)
			label.setWordWrap(True)
			label.setOpenExternalLinks(True)
			label.setStyleSheet('font-size: 11px; color: #444;')
			lay.addWidget(label)
		return box

	def project_layers_changed(self, *args):
		self.sync_fields()

	def stop(self):
		self.timer.stop()
		for signal in self.project_signals:
			try:
				signal.disconnect(self.project_layers_changed)
			except (TypeError, RuntimeError):  # already disconnected
				pass

	# Arguments --------------------------------------------------------------------------------------------------

	def save_settings(self):
		s = QgsSettings()
		s.setValue(SETTINGS + 'project', self.project.text().strip())
		s.setValue(SETTINGS + 'eecu_tier', self.eecu_tier.currentData())
		s.setValue(SETTINGS + 'start', self.start.date().toString('yyyy-MM-dd'))
		s.setValue(SETTINGS + 'end', self.end.date().toString('yyyy-MM-dd'))
		s.setValue(SETTINGS + 'other_start', self.other_start.date().toString('yyyy-MM-dd'))
		s.setValue(SETTINGS + 'other_end', self.other_end.date().toString('yyyy-MM-dd'))
		s.setValue(SETTINGS + 'folder', self.folder.text().strip())
		s.setValue(SETTINGS + 'fire_sensor', self.fire_sensor.currentData())
		for key, d in self.fire_dates.items():
			s.setValue(SETTINGS + 'fire_' + key, d.date().toString('yyyy-MM-dd'))
		# the data of Earth Engine outside the catalog: the last ID, band, use, scale, offset and unit, as written
		s.setValue(SETTINGS + 'asset', self.asset_id.text().strip())
		s.setValue(SETTINGS + 'asset_band', self.asset_band.currentText().strip())
		s.setValue(SETTINGS + 'asset_use', self.asset_use.currentData())
		for key, w in (('band_scale', self.band_scale), ('band_offset', self.band_offset), ('asset_unit', self.asset_unit)):
			s.setValue(SETTINGS + key, w.text().strip())
		s.setValue(SETTINGS + 'community_theme', self.community_theme.currentData() or '')
		# the land cover mask: on or off, its map, year and land covers left out
		s.setValue(SETTINGS + 'landcover_on', 'true' if self.landcover_box.isChecked() else 'false')
		s.setValue(SETTINGS + 'landcover_map', self.landcover_map.currentData())
		s.setValue(SETTINGS + 'landcover_year', str(self.landcover_year.currentData() or ''))
		s.setValue(SETTINGS + 'landcover_exclude', ','.join(self.landcover_classes.checkedItemsData()))

	def region(self):
		"""Region of the services from the widgets (read in the main thread)."""
		kind = self.region_kind.currentData()
		wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
		if kind == 'extent':
			canvas = self.iface.mapCanvas()
			tr = QgsCoordinateTransform(canvas.mapSettings().destinationCrs(), wgs84, QgsProject.instance())
			r = tr.transformBoundingBox(canvas.extent())
			return {'bbox': [r.xMinimum(), r.yMinimum(), r.xMaximum(), r.yMaximum()]}
		if kind == 'ecoregion':
			canvas = self.iface.mapCanvas()
			tr = QgsCoordinateTransform(canvas.mapSettings().destinationCrs(), wgs84, QgsProject.instance())
			c = tr.transform(canvas.extent().center())
			return {'ecoregion_at': [c.x(), c.y()]}
		if kind == 'island':
			canvas = self.iface.mapCanvas()
			tr = QgsCoordinateTransform(canvas.mapSettings().destinationCrs(), wgs84, QgsProject.instance())
			c = tr.transform(canvas.extent().center())
			return {'island_at': [c.x(), c.y()]}
		if kind == 'wdpa':
			if self.wdpa.currentData() is None:
				raise ValueError('search for a protected area and choose it in the list')
			return {'wdpa_id': self.wdpa.currentData()}
		if kind == 'admin':
			if self.admin.currentData() is None:
				raise ValueError('search for an administrative unit and choose it in the list')
			level, code = self.admin.currentData()
			return {f'admin{level}': code}
		if kind == 'country':
			code = self.country.text().strip().upper()
			if len(code) != 3:
				raise ValueError('write the ISO3 code of the country (e.g. ESP)')
			return {'country': code}
		layer = self.layer.currentLayer()
		if layer is None:
			raise ValueError('choose a layer of polygons')
		self.sync_fields()
		feats = list(layer.getSelectedFeatures()) or list(layer.getFeatures())
		if not feats:
			raise ValueError(f'the layer {layer.name()} has no features')
		tr = QgsCoordinateTransform(layer.crs(), wgs84, QgsProject.instance())
		field = self.name_field.currentField()
		vertices = sum(f.geometry().constGet().nCoordinates() for f in feats if f.hasGeometry())
		tol = 0.0001 * max(1.0, vertices / MAX_VERTICES)  # degrees: simplify only big geometries
		out = []
		for f in feats:
			if not f.hasGeometry():
				continue
			g = f.geometry()
			g.transform(tr)
			if vertices > MAX_VERTICES:
				g = g.simplify(tol)
			name = f[field] if field else f.id()
			out.append({'type': 'Feature', 'properties': {'name': str(name)}, 'geometry': json.loads(g.asJson())})
		return {'geojson': {'type': 'FeatureCollection', 'features': out}}

	def variable_args(self):
		v = self.variable.currentData()
		where = self.where_args()
		if v.get('custom'):  # data of Earth Engine by its ID: no variable, sensor nor pixel filters (their own mask)
			args = self.data_args()
			if 'collection' in args:  # images with dates; a fixed image has none (greyed out, as the elevation)
				args.update(start=self.start.date().toString('yyyy-MM-dd'), end=self.end.date().toString('yyyy-MM-dd'))
				if self.season_on.isChecked():
					args['season'] = [self.season_start.text().strip(), self.season_end.text().strip()]
			if where:  # conditions on variables of the catalog
				args['where'] = where
			return args
		if v.get('static'):  # elevation, slope: without dates, pixel filters or season (greyed out), nor in the README
			return dict({'variable': v['variable'], 'sensor': v['sensor'], 'collection': v['collection']},
			            **({'where': where} if where else {}))
		args = {'variable': v['variable'], 'sensor': v['sensor'], 'collection': v['collection'],
		        'start': self.start.date().toString('yyyy-MM-dd'), 'end': self.end.date().toString('yyyy-MM-dd'),
		        'quality': self.quality_args()}
		if self.season_on.isChecked():
			args['season'] = [self.season_start.text().strip(), self.season_end.text().strip()]
		if where:
			args['where'] = where
		return args

	def data_args(self):
		"""The data of Earth Engine of the panel as the services take them instead of variable and sensor:
		{'collection' or 'image': its ID, 'band'} and the 'band_scale', 'band_offset' and 'unit' written (see
		monitoreo.assets)."""
		asset = self.asset_text()
		if not asset:
			raise ValueError('Earth Engine data: write the ID of an image or a collection of images (or choose a '
			                 'dataset) and press Read')
		band = self.asset_band.currentText().strip()
		if not band:
			raise ValueError(f'Earth Engine data: choose or write the band of {asset} (Read lists them)')
		read = self.described()
		names = [b.get('band') for b in (read or {}).get('bands') or []]
		if read and band not in names:
			raise ValueError(f"Earth Engine data: {asset} has no band {band}: choose one of {', '.join(names)}")
		args = {self.asset_use.currentData(): asset, 'band': band}
		for key, w in (('band_scale', self.band_scale), ('band_offset', self.band_offset)):
			text = w.text().strip().replace(',', '.')
			if text:
				try:
					args[key] = float(text)
				except ValueError:
					raise ValueError(f"Earth Engine data: the {key.replace('_', ' ')} of {asset} is not a number: "
					                 f'{text}') from None
		unit = self.asset_unit.text().strip()
		if unit:
			args['unit'] = unit
		return args

	def asset_text(self):
		"""The ID written, as the services take it (monitoreo.assets.normalize: also ee.ImageCollection('...'))."""
		return assets.normalize(self.asset_id.text())

	def described(self):
		"""What services.describe_asset said of the ID written, or None if it has not been read."""
		read = self.asset_info
		return read if read and read.get('asset') == self.asset_text() else None

	def custom_entry(self):
		"""The data of Earth Engine of the panel as an entry of the list Variable, so that the panel treats them as a
		variable: an image is a fixed layer without dates (static: no series, trends, comparisons nor exports of
		series), they have no pixel filters (fixed_filters: none) nor true colour (rgb), and they have no variable nor
		sensor of the catalog (custom)."""
		asset, band, use = self.asset_text(), self.asset_band.currentText().strip(), self.asset_use.currentData()
		return {'custom': True, 'asset': asset, 'band': band, 'use': use, 'static': use == 'image',
		        'fixed_filters': [], 'rgb': False, 'name': f'{asset} {band}'.strip() or 'Earth Engine data',
		        'band_scale': self.band_scale.text().strip(), 'band_offset': self.band_offset.text().strip(),
		        'unit': self.asset_unit.text().strip()}

	def custom_changed(self):
		"""The data of Earth Engine changed: their entry of the list Variable, and what applies to them."""
		if not hasattr(self, 'where'):  # not built yet
			return
		if (self.variable.currentData() or {}).get('custom'):
			self.variable.setItemData(0, self.custom_entry())
			self.variable_changed()

	def show_data(self):
		"""The options of the data of Earth Engine in their themes (those of the GEE Community Catalog only in its
		own), instead of the list Variable."""
		data = self.data_themes.get(self.theme.currentData())
		self.data_row.setVisible(data is not None)
		self.community_row.setVisible(data == 'community')
		for w in (self.variable_field, self.variable_label):
			if w is not None:
				w.setVisible(data is None)

	def read_asset(self, asset=None):
		"""Read in Earth Engine what the ID ASSET (default: the one written) is, with services.describe_asset in a
		task with the project of the panel (metadata, without computing), and fill its bands, its use, the scale,
		offset and unit of its band and what its record says."""
		asset = assets.normalize(asset or self.asset_id.text())
		if not asset:
			self.message(READ_HINT, 'Warning')
			return

		def work():
			try:
				return services.describe_asset(asset)
			except Exception as e:  # an unknown ID, one without access, a table...: also said under the options
				return {'asset': asset, 'error': str(e)}

		self.run_task(f'Read {asset} in Earth Engine', work, self.asset_read)

	def asset_read(self, d):
		"""Show what services.describe_asset said (D): its bands (the one of its arguments chosen, or the one written
		if it has it), how it is used (only as a fixed image if it is an image), the scale, offset and unit of the band
		and its title, source, licence and page; or why it could not be read. Nothing if another ID was written
		meanwhile (its own Read applies)."""
		if d['asset'] != self.asset_text():
			return
		if d.get('error'):
			self.asset_label.setText(f"<b>{esc(d['asset'])}</b>: it could not be read: {esc(d['error'])}")
			self.message(f"Read {d['asset']} in Earth Engine: {d['error']}", 'Critical', 15)
			return
		self.asset_info = d
		typed = self.asset_band.currentText().strip()
		if self.asset_id.text() != d['asset']:
			self.asset_id.setText(d['asset'])
		bands = d.get('bands') or []
		names = [b['band'] for b in bands]
		self.asset_band.blockSignals(True)
		self.asset_band.clear()
		for b in bands:
			self.asset_band.addItem(b['band'], b)
			tip = ' · '.join(str(x) for x in (b.get('description'), b.get('units'), b.get('resolution_m') and
			                                  f"{b['resolution_m']:g} m", b.get('data_type')) if x)
			self.asset_band.setItemData(self.asset_band.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
		chosen = typed if typed in names else (d.get('arguments') or {}).get('band')
		self.asset_band.setCurrentIndex(names.index(chosen) if chosen in names else (0 if names else -1))
		self.asset_band.blockSignals(False)
		image = d.get('type') == 'image'
		self.asset_use.setCurrentIndex(max(0, self.asset_use.findData(d.get('use') or 'collection')))
		self.asset_use.setEnabled(not image)  # an image has no dates: never a collection
		self.asset_use.setToolTip('An image has no dates: only a fixed image (maps and their statistics)' if image
		                          else 'As its record suggests; a collection of tiles (e.g. a DEM) is a fixed image')
		self.band_changed()
		self.asset_label.setText(data_summary(d))
		self.custom_changed()
		self.message(f"{d['asset']}: {data_use(d)} ({len(names)} band{'' if len(names) == 1 else 's'})", 'Success', 10)

	def asset_edited(self):
		"""A new ID written by hand or chosen in the GEE Community Catalog: what was read of the former one no longer
		applies until it is read."""
		self.asset_use.setEnabled(True)
		self.asset_use.setToolTip('')
		self.asset_label.setText(READ_HINT)

	def band_changed(self):
		"""The scale, offset and unit of the band chosen, as the record of its data says (services.describe_asset);
		if it gives its unit but not in UDUNITS, the field says it."""
		b = self.asset_band.currentData()
		if not isinstance(b, dict):  # a band written, not read
			return
		self.band_scale.setText(number(b.get('band_scale')))
		self.band_offset.setText(number(b.get('band_offset')))
		self.asset_unit.setText(b.get('unit') or '')
		self.asset_unit.setPlaceholderText(f"its record says {b['units']}: write it in UDUNITS" if b.get('units') and
		                                   not b.get('unit') else 'e.g. mm, degC, kg m-2, mm day-1 or 1 (dimensionless)')

	def fill_datasets(self):
		"""The datasets of the theme of the GEE Community Catalog chosen (services.community_datasets, from the copy of
		its index in MonitorEO: no Earth Engine), none of them chosen."""
		self.community_records = {}
		self.community_dataset.clear()
		for d in services.community_datasets(theme=self.community_theme.currentData()):
			self.community_records[d['id']] = d
			kind = 'collection' if d['type'] == 'image_collection' else 'image'
			self.community_dataset.addItem(f"{d['title']} ({kind})", d['id'])
			licence = d.get('license_text') if d.get('license') == 'custom' else d.get('license')
			self.community_dataset.setItemData(self.community_dataset.count() - 1,
			                                   '\n'.join(x for x in (d['id'], d.get('provider'), licence and
			                                                         f'Licence: {licence}') if x),
			                                   Qt.ItemDataRole.ToolTipRole)
		self.community_dataset.setCurrentIndex(-1)

	def dataset_chosen(self, i):
		"""A dataset of the GEE Community Catalog chosen: its ID and what its record says, then read in Earth Engine
		(its bands)."""
		asset = self.community_dataset.itemData(i)
		if not asset:
			return
		rec = self.community_records.get(asset) or {}
		self.asset_id.setText(asset)
		self.asset_edited()
		self.asset_label.setText(data_summary({
			'asset': asset, 'title': rec.get('title'), 'source': 'GEE Community Catalog', 'provider': rec.get('provider'),
			'licence': rec.get('license_text') if rec.get('license') == 'custom' else rec.get('license'),
			'page': rec.get('docs'), 'type': rec.get('type')}, read=False))
		self.read_asset(asset)

	def quality_args(self, own=False):
		"""The pixel filters checked in the panel (clouds, with Cloud Score+ or the SCL of Sentinel-2). OWN: those the
		user chose, also while a variable with fixed filters is selected (elevation, slope, cloud or snow cover
		frequency, which grey them out), for the analyses that compute other variables (the burn severity, the NBR)."""
		chosen = self.chosen_filters if own and self.chosen_filters is not None else \
			{k: w.isChecked() for k, w in self.filters.items()}
		quality = dict(chosen)
		quality['cloud_score'] = 0.6 if self.cloud_score.isChecked() else None
		return quality

	def fill_variables(self, choose=None):
		"""The variables of the theme chosen (all of them with «All the variables»), keeping the one chosen if it is
		there; else CHOOSE (the start of its text) or the first one. In the themes of the data of Earth Engine outside
		the catalog, only the entry of those data (custom_entry), with their options instead of the list."""
		key = self.theme.currentData()
		was = self.variable.currentData() or {}
		current = (self.catalog_choice if was.get('custom') else self.variable.currentText()) or choose
		self.variable.blockSignals(True)
		self.variable.clear()
		if key in self.data_themes:
			self.catalog_choice = current  # chosen again back in a theme of the catalog
			self.variable.addItem('Earth Engine data (by its ID)', self.custom_entry())
			self.variable.blockSignals(False)
			self.show_data()
			if hasattr(self, 'where'):  # built: the options of the data
				self.variable_changed()
			return
		for v in self.all_variables:
			if key is not None and (catalog.theme_of(v['variable']) or {}).get('key') != key:
				continue
			self.variable.addItem(f"{v['variable']} · {v['sensor']} · {v['resolution_m']} m · "
			                      f"{v['collection'].split('/')[-1]}", v)
			self.variable.setItemData(self.variable.count() - 1, f"{v['name']} ({v['unit']}), {v['dates']}",
			                          Qt.ItemDataRole.ToolTipRole)
		self.variable.setCurrentIndex(max(0, self.variable.findText(current or '', Qt.MatchFlag.MatchStartsWith)))
		self.variable.blockSignals(False)
		self.show_data()
		if hasattr(self, 'where'):  # built: the options of the variable chosen
			self.variable_changed()

	def landcover_group(self, s, main):
		"""The land cover mask (monitoreo.landcover), before the variable: a group that unfolds when checked, with the
		land cover map, its year and the broad land covers to leave out of every result (a condition of where)."""
		box = QgsCollapsibleGroupBox('Land cover mask')
		box.setCheckable(True)
		box.setChecked(str(s.value(SETTINGS + 'landcover_on', 'false')).lower() == 'true')
		box.setCollapsed(not box.isChecked())
		box.toggled.connect(lambda on: box.setCollapsed(not on))
		self.landcover_box = box
		f = QFormLayout(box)
		self.landcover_map = QComboBox()
		for m in landcover.maps():
			self.landcover_map.addItem(f"{m['name']} · {m['m']} m · {m['coverage']}", m['key'])
		self.landcover_map.setCurrentIndex(max(0, self.landcover_map.findData(s.value(SETTINGS + 'landcover_map',
		                                                                              'WorldCover'))))
		f.addRow('Map', info(self.landcover_map, HELP['landcover_map']))
		self.landcover_year = QComboBox()
		f.addRow('Year', self.landcover_year)
		self.landcover_classes = QgsCheckableComboBox()
		self.landcover_classes.setDefaultText('choose the land covers')
		chosen = str(s.value(SETTINGS + 'landcover_exclude', 'water,built')).split(',')
		for c in landcover.classes():
			self.landcover_classes.addItemWithCheckState(
				c['en'], Qt.CheckState.Checked if c['key'] in chosen else Qt.CheckState.Unchecked, c['key'])
			self.landcover_classes.setItemData(self.landcover_classes.count() - 1, c['help'],
			                                   Qt.ItemDataRole.ToolTipRole)
		f.addRow('Leave out', info(self.landcover_classes, self.landcover_help))
		self.fill_landcover_years(s.value(SETTINGS + 'landcover_year', ''))
		self.landcover_map.currentIndexChanged.connect(lambda i: self.fill_landcover_years())
		main.addWidget(box)

	def fill_landcover_years(self, year=None):
		"""The years of the land cover map chosen, keeping YEAR (or the year chosen) if the map has it; otherwise its
		last one (for Dynamic World, the last whole year)."""
		m = landcover.find(self.landcover_map.currentData())
		year = str(year or self.landcover_year.currentData() or '')
		self.landcover_year.blockSignals(True)
		self.landcover_year.clear()
		for y in reversed(landcover.years(m)):
			self.landcover_year.addItem(str(y), y)
		i = self.landcover_year.findData(int(year)) if year.isdigit() else -1
		self.landcover_year.setCurrentIndex(i if i >= 0 else self.landcover_year.findData(landcover.default_year(m)))
		self.landcover_year.blockSignals(False)

	def landcover_help(self):
		"""The help of «Leave out»: the classes of the map chosen that are each broad land cover."""
		m = landcover.find(self.landcover_map.currentData())
		rows = []
		for c in landcover.classes():
			codes = sorted((code for code, k in m['classes'].items() if k == c['key']), key=int)
			names = ', '.join(f"{code} {m['names'][code]}" for code in codes) or 'none'
			rows.append(f"<li><b>{esc(c['en'])}</b>: {esc(names)}</li>")
		return HELP['landcover'] + f"<p>The classes of {esc(m['name'])} in each:</p><ul>{''.join(rows)}</ul>"

	def landcover_args(self):
		"""The land cover condition of where of the group «Land cover mask» (see monitoreo.landcover), or None if it is
		off."""
		if not self.landcover_box.isChecked():
			return None
		exclude = [k for k in self.landcover_classes.checkedItemsData()]
		if not exclude:
			raise ValueError('Land cover mask: check the land covers to leave out (or uncheck the mask)')
		return {'landcover': self.landcover_map.currentData(), 'year': self.landcover_year.currentData(),
		        'exclude': exclude}

	def where_args(self, period=None):
		"""The checked conditions of «Only the pixels where» (see monitoreo.variable.where_specs), or None. Those of
		variables with dates are the mean over the period of the panel (or PERIOD: the first and the last day), fixed
		in each condition, so that the maps of each step of a series, and the other period of a comparison, keep the
		same pixels."""
		out = []
		for c in self.where:
			if not c['on'].isChecked():
				continue
			v = c['variable'].currentData()
			limits = {}
			for key in ('min', 'max'):
				text = c[key].text().strip().replace(',', '.')
				if text:
					try:
						limits[key] = float(text)
					except ValueError:
						raise ValueError(f"Only the pixels where: the {key} of {v['variable']} is not a number: {text}")
			if not limits:
				raise ValueError(f"Only the pixels where: give a min, a max or both for {v['variable']}")
			cond = {'variable': v['variable'], 'sensor': v['sensor'], 'collection': v['collection'], **limits}
			if not v.get('static'):
				cond['period'] = list(period or (self.start.date().toString('yyyy-MM-dd'),
				                                 self.end.date().toString('yyyy-MM-dd')))
			out.append(cond)
		lc = self.landcover_args()  # the land covers left out: a map of a year, not the period
		if lc:
			out.append(lc)
		return out or None

	def where_changed(self):
		"""The unit of each condition of «Only the pixels where», and the period on when a condition needs it (a
		variable with dates filtering a fixed layer)."""
		for c in self.where:
			v = c['variable'].currentData() or {}
			c['unit'].setText(v.get('unit') or '')
			for key in ('variable', 'min', 'max'):
				c[key].setEnabled(c['on'].isChecked())
		self.variable_changed()

	# Tasks ------------------------------------------------------------------------------------------------------

	def run_task(self, description, work, done):
		"""Run WORK() in a QGIS task and DONE(result) in the main thread; errors go to the message bar."""
		self.save_settings()
		project = self.project.text().strip() or None

		def run(task):
			services.init(project, shared=not project, warn=False)  # an empty field: the shared account of MonitorEO
			return work()

		def finished(exception, result=None):
			self.tasks = [t for t in self.tasks if t is not task]
			if exception is not None:
				self.message(f'{description}: {exception}', 'Critical', 15)
				return
			try:
				done(result)
			except Exception as e:
				self.message(f'{description}: {e}', 'Critical', 15)
			self.check_eecu()  # what this task spent (the answers are kept some minutes: no new query each time)

		task = QgsTask.fromFunction(description, run, on_finished=finished)
		self.tasks.append(task)
		QgsApplication.taskManager().addTask(task)
		self.message(f'{description}…', 'Info', 3)
		return task

	def prepare(self):
		"""Region and variable arguments, or None (with a message) if they are not valid."""
		try:
			return self.region(), self.variable_args()
		except Exception as e:
			self.message(str(e), 'Warning')
			return None

	def connect(self):
		self.run_task('Connect to Earth Engine', lambda: (services.project(), services.shared()),
		              lambda r: self.message(f'Connected to Earth Engine with the shared account of MonitorEO '
		                                     f'(project {r[0]})' if r[1] else
		                                     f'Connected to Earth Engine with your account (project {r[0]})', 'Success'))

	def check_eecu(self, refresh=False, asked=False):
		"""Show in its bar the EECUs of Earth Engine spent this month, in a task of QGIS; warn when less than 10 % are
		left (once a month, or ASKED by the button Check, which also asks again: REFRESH)."""
		project = self.project.text().strip() or None
		tier = self.eecu_tier.currentData()

		def run(task):
			if project:  # the research EECUs of the shared account are asked without connecting (also when spent)
				services.init(project, warn=False)
			return services.eecu_usage(tier, refresh=refresh, lang='en', shared=not project)

		def finished(exception, result=None):
			self.tasks = [t for t in self.tasks if t is not task]
			if exception is not None:
				self.eecu_bar.setValue(0)
				self.eecu_bar.setFormat('cannot be checked')
				self.eecu_bar.setToolTip(str(exception))
				if asked:
					self.message(f'EECUs of the month: {exception}', 'Warning', 15)
				return
			self.show_eecu(result, asked)

		task = QgsTask.fromFunction('Check the EECUs of Earth Engine of the month', run, on_finished=finished)
		self.tasks.append(task)
		QgsApplication.taskManager().addTask(task)

	def show_eecu(self, u, asked=False):
		used = 100 - u.get('left_percent', 100 - u['used_percent'])  # what can no longer be used (also by the project)
		self.eecu_bar.setValue(int(min(100, round(used))))
		self.eecu_bar.setFormat(f'{used:.1f}% used')
		self.eecu_label.setText('research EECUs' if u['account'] == 'shared' else 'EECUs of the month')
		self.eecu_bar.setToolTip(u['text'])
		color = '#c0392b' if u['low'] else '#d68910' if used >= 75 else '#2e7d32'
		self.eecu_bar.setStyleSheet(f'QProgressBar {{ text-align: center; }} '
		                            f'QProgressBar::chunk {{ background-color: {color}; }}')
		key = (u['project'], u['account'], u['month'])
		if u['warning'] and (asked or key not in self.eecu_warned):
			self.eecu_warned.add(key)
			hint = ' In this panel: write your project in "Project" and press "Authenticate…".' \
				if u['account'] == 'shared' else ''
			self.message(u['warning'] + hint, 'Warning', 60)
		elif asked:
			self.message(u['text'], 'Info', 10)

	def authenticate(self):
		def work():
			import ee
			ee.Authenticate(auth_mode='localhost', force=True)
			return True

		task = QgsTask.fromFunction('Authenticate with Earth Engine', lambda t: work(),
		                            on_finished=lambda e, r=None: self.message(
			                            'Authenticated with Earth Engine' if e is None else f'Authentication: {e}',
			                            'Success' if e is None else 'Critical', 10))
		self.tasks.append(task)
		QgsApplication.taskManager().addTask(task)
		self.message('Sign in with your Google account in the browser', 'Info', 10)

	def search_wdpa(self):
		text = self.wdpa_text.text().strip()
		if not text:
			return

		def done(parks):
			self.wdpa.clear()
			for p in parks:
				self.wdpa.addItem(f"{p['NAME']} · {p.get('DESIG', '')} · {p.get('ISO3', '')} · {p.get('REP_AREA', 0):,.0f} km² "
				                  f"(WDPA {p['SITE_ID']})", int(p['SITE_ID']))
			self.message(f'{len(parks)} protected areas with "{text}"', 'Info', 4)

		more = {'designation': 'ramsar'} if self.ramsar.isChecked() else {}
		self.run_task('Search protected areas', lambda: services.find_protected_areas(text, 30, **more), done)

	def search_admin(self):
		text, level = self.admin_text.text().strip(), self.admin_level.currentData()
		country = self.admin_country.text().strip().upper() or None
		if not text:
			return

		def done(units):
			self.admin.clear()
			for u in units:
				code = u[f'GAUL{level}_CODE']
				self.admin.addItem(f"{u.get('DISP_EN') or u[f'GAUL{level}_NAME']} (GAUL {code})", (level, int(code)))
			self.message(f'{len(units)} administrative units with "{text}"', 'Info', 4)

		self.run_task('Search administrative units', lambda: services.find_admin_units(text, level, country, 30), done)

	def other_period(self):
		"""(first day, last day) of the period to compare with the reference one, or None."""
		if not self.compare_on.isChecked() or (self.variable.currentData() or {}).get('static'):
			return None
		return self.other_start.date().toString('yyyy-MM-dd'), self.other_end.date().toString('yyyy-MM-dd')

	def add_result(self, res):
		"""Keep a result (series, trends, comparison or burn severity) in the list of the session and open its
		window."""
		self.series.append(res)
		self.update_series_list()
		self.series_list.setCurrentIndex(self.series_list.count() - 1)
		self.show_series()

	def run_series(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		tmp = tempfile.mkdtemp(prefix='monitoreo_')
		step, metric, stat = self.step.currentData(), self.ts_metric.currentData(), self.stat.currentData()
		other = self.other_period()
		if other:
			return self.run_comparison(region, var, other, step, metric, stat, tmp)

		def work():
			return services.time_series(region, step=step, metric=metric, stat=stat, csv=os.path.join(tmp, 'series.csv'),
			                            **var)

		def done(res):
			from .results import SeriesDialog, chart_png
			if not res['rows']:
				self.message('The series has no values', 'Warning')
				return
			# the chart is drawn here, in the main thread: matplotlib in the thread of a task can crash QGIS (the
			# OpenBLAS of numpy overflows the small stack of those threads on macOS)
			res['chart'] = chart_png(res, os.path.join(tmp, 'series.png'))
			res['label'] = f"{res['title']} · {', '.join(res['regions'])}"
			res['kind'] = 'series'
			res['args'] = dict(var, region=region, step=step, metric=metric)
			res['maps'] = result_maps('time_series', res['args'])
			# whether its maps can also be the true colour of their images (the list Layer of its window): never for
			# the data of Earth Engine outside the catalog
			res['rgb'] = False
			if var.get('variable'):
				res['rgb'] = services.has_rgb(var['variable'], var['sensor'], var['collection'])
			self.add_result(res)

		self.run_task(f"Time series of {data_name(var)}", work, done)

	def run_comparison(self, region, var, other, step, metric, stat, tmp):
		if step not in trends.STEPS:
			self.message('To compare periods, choose the step Monthly, 16 days or Annual', 'Warning')
			return

		def work():
			return services.compare_series(region, other_start=other[0], other_end=other[1], step=step, metric=metric,
			                               stat=stat, csv=os.path.join(tmp, 'comparison.csv'), **var)

		def done(res):
			from .results import comparison_png
			if not any(r['reference'] is not None or r['other'] is not None for r in res['profile']):
				self.message('The comparison has no values', 'Warning')
				return
			res['chart'] = comparison_png(res, step, os.path.join(tmp, 'comparison.png'))  # in the main thread
			res['label'] = f"Comparison: {res['title']}"
			res['kind'] = 'comparison'
			self.add_result(res)

		self.run_task(f"Comparison of periods of {data_name(var)}", work, done)

	def variable_changed(self):
		"""The metrics of the images, fixed at the only metric of the variable if it has one, and its pixel filters,
		greyed out and checked those always on if they are fixed (the snow cover frequency: the mean, the % of the clear
		observations with snow, without clouds and water). The filters chosen before come back with another variable.
		The fixed layers without dates (elevation, slope): only maps, so the period, the metrics, the filters, the time
		series and the trends greyed out. The data of Earth Engine outside the catalog (custom_entry): no pixel filters
		and, a fixed image, as those layers. The list Layer of the map, with the true colour only if it has one
		(update_map_kind)."""
		v = self.variable.currentData() or {}
		only = v.get('metric')
		static = bool(v.get('static'))
		for w in (self.ts_metric, self.trend_metric, self.map_metric):
			if only:
				w.setCurrentIndex(max(0, w.findData(only)))
			w.setEnabled(not only and not static)
			w.setToolTip(f"{v['variable']} only takes the {only}" if only else '')
		for w in (self.compare_on, self.season_on, self.season_start, self.season_end,
		          self.temporal, self.interannual, self.series_box, self.trends_box, self.export_series_button):
			w.setEnabled(not static)
		dated = any(c['on'].isChecked() and not (c['variable'].currentData() or {}).get('static')
		            for c in getattr(self, 'where', []))  # the period of a condition with dates
		for w in (self.start, self.end):
			w.setEnabled(not static or dated)
		for w in (self.other_start, self.other_end):
			w.setEnabled(not static and self.compare_on.isChecked())
		fixed = v.get('fixed_filters')
		self.cloud_score.setEnabled(fixed is None)
		self.cloud_score.setToolTip(NO_FILTERS if v.get('custom') else '')
		if fixed is not None and self.chosen_filters is None:
			self.chosen_filters = {k: w.isChecked() for k, w in self.filters.items()}
		for k, w in self.filters.items():
			if fixed is not None:
				w.setChecked(k in fixed)
			elif self.chosen_filters is not None:
				w.setChecked(self.chosen_filters[k])
			w.setEnabled(fixed is None)
			w.setToolTip('' if fixed is None else NO_FILTERS if v.get('custom') else
			             f"Fixed filters of {v['variable']}: they cannot be changed")
		if fixed is None:
			self.chosen_filters = None
		self.update_map_kind()

	def update_map_kind(self):
		"""The list Layer of the group Map (the map of the variable, its true colour or both): only for the variables
		whose images have a true colour (services.has_rgb), not for the fixed layers, the data of Earth Engine outside
		the catalog nor the difference of «Compare with»; else it is the map of the variable, and its tooltip says
		why."""
		if not hasattr(self, 'map_kind'):  # not built yet
			return
		v = self.variable.currentData() or {}
		if v.get('custom'):
			why = (f"{v.get('name')}: the data of Earth Engine outside the catalog have no true colour (only the "
			       'variables of Sentinel-2 and Landsat and the cloud frequency of MODIS)')
		elif v.get('static'):
			why = f"{v['variable']} is a fixed layer, without dates: it has no images, nor true colour"
		elif not v.get('rgb'):
			why = (f"{v.get('variable')} of {v.get('sensor')} has no true colour: only the variables of Sentinel-2 and "
			       'Landsat and the cloud frequency of MODIS (MOD09GA, MYD09GA) have images with red, green and blue '
			       'bands')
		elif self.compare_on.isChecked():
			why = 'No true colour with Compare with: the map is the difference between two periods'
		else:
			why = None
		if why:
			self.map_kind.setCurrentIndex(self.map_kind.findData('index'))
		self.map_kind.setEnabled(why is None)
		self.map_kind.setToolTip(why or KINDS_TIP + ', with the same pixels')

	def update_trend_parts(self):
		step = self.trend_step.currentData()
		self.trend_part.clear()
		for p in trends.parts(step):
			self.trend_part.addItem('the year' if step == 'annual' else trends.part_label(step, p), p)
		self.trend_part.setEnabled(step != 'annual')

	def run_trend_table(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		tmp = tempfile.mkdtemp(prefix='monitoreo_')
		step, metric, stat = self.trend_step.currentData(), self.trend_metric.currentData(), self.stat.currentData()

		def work():
			return services.trend_table(region, step=step, metric=metric, stat=stat,
			                            csv=os.path.join(tmp, 'trends.csv'), **var)

		def done(res):
			from .results import trends_png
			if not any(r['slope'] is not None for r in res['rows']):
				self.message('There are not enough years to compute trends (2 or more are needed)', 'Warning')
				return
			res['chart'] = trends_png(res, os.path.join(tmp, 'trends.png'))  # in the main thread
			res['label'] = f"Trends: {res['title']}"
			res['kind'] = 'trends'
			res['args'] = dict(var, region=region, step=step, metric=metric)
			res['maps'] = result_maps('trend_table', res['args'])
			self.add_result(res)

		self.run_task(f"Trends of {data_name(var)}", work, done)

	def run_trend_map(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		step, part, metric = self.trend_step.currentData(), self.trend_part.currentData(), self.trend_metric.currentData()
		alpha = ALPHA if self.trend_alpha.isChecked() else None
		path = os.path.join(tempfile.mkdtemp(prefix='monitoreo_'), 'trend.tif')

		def work():
			try:
				return services.download_trend(region, step=step, part=part, metric=metric, alpha=alpha, path=path,
				                               max_pixels=MAP_PIXELS, **var)
			except Exception as e:
				res = services.trend_map(region, step=step, part=part, metric=metric, alpha=alpha, **var)
				res['error'] = str(e)
				return res

		self.run_task(f"Trend map of {data_name(var)}", work,
		              lambda res: self.add_tile_layer(res) if 'url' in res else self.add_map_layer(res))

	def update_series_list(self):
		self.series_list.clear()
		for i, res in enumerate(self.series):
			self.series_list.addItem(f"{i + 1}. {res['label']}", i)
		self.series_list.setEnabled(bool(self.series))
		self.show_series_button.setEnabled(bool(self.series))

	def show_series(self):
		"""Open the window of the chosen series, trends, comparison or burn severity (or bring it to the front if it
		is open)."""
		from .results import ResultDialog, SeriesDialog
		i = self.series_list.currentData()
		if i is None:
			return
		dlg = self.series_dialogs.get(i)
		if dlg is None:
			res = self.series[i]
			cls = SeriesDialog if res.get('kind', 'series') == 'series' else ResultDialog
			dlg = self.series_dialogs[i] = cls(res, self.iface.mainWindow(), self.add_result_map)
		dlg.show()
		dlg.raise_()
		dlg.activateWindow()

	def run_map(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		metric, temporal, inter = self.map_metric.currentData(), self.temporal.currentData(), self.interannual.currentData()
		folder = tempfile.mkdtemp(prefix='monitoreo_')
		other = self.other_period()
		static = (self.variable.currentData() or {}).get('static')  # no temporal metric for the fixed layers
		opts = dict(var) if static else dict(var, metric=metric, temporal=temporal, interannual=inter)
		if other:
			opts.update(other_start=other[0], other_end=other[1])
		download, tiles = ((services.download_comparison, services.compare_map) if other else
		                   (services.download_image, services.map_layer))
		# the map of the variable, its true colour or both (never of a fixed layer or a difference: see update_map_kind)
		kind = 'index' if static or other or not self.map_kind.isEnabled() else self.map_kind.currentData()
		title = {'index': 'Map', 'rgb': 'True colour', 'both': 'Map and true colour'}[kind]

		def work():
			"""The map as a GeoTIFF with the values (with OTHER, the difference between the periods, and both) and/or
			its true colour; if they cannot be downloaded, Earth Engine tiles (colours only)."""
			return maps_work(kind, region, opts, folder, download, tiles)

		self.run_task(f"{title} of {data_name(var)}", work, self.add_maps)

	def add_maps(self, r, name=None, rgb_name=None, group=None, zoom=True, period=None, kept=None):
		"""Add the layers of R (see maps_work): first its true colour, then the map of the variable on top of it, both
		with PERIOD in the Temporal Controller, and zoom to the first one (with ZOOM). NAME and RGB_NAME: their names
		(by default, those of the results). KEPT (the result of a series): the colours of its first map ('colors') and
		the stretch of its first true colour ('rgb_stretch'), kept there for its next maps, so that they can be
		compared."""
		kept = {} if kept is None else kept
		if r.get('rgb_error'):  # only the true colour failed: the map is added all the same
			self.message(f"True colour of {name or r['index']['name']}: {r['rgb_error']} (only the map was added)",
			             'Warning', 15)
		c = r.get('rgb')
		if c is not None:
			if 'rgb_stretch' not in kept and c.get('min') is not None:
				kept['rgb_stretch'] = (c['min'], c['max'])
			if 'url' in c:
				self.add_tile_layer(c, rgb_name, group, zoom=zoom, period=period)
			else:
				self.add_rgb_layer(c, rgb_name, group, kept.get('rgb_stretch'), zoom=zoom, period=period)
			zoom = False
		i = r.get('index')
		if i is not None:
			if 'colors' not in kept and i.get('min') is not None:
				kept['colors'] = (i['min'], i['max'])
			if 'url' in i:
				self.add_tile_layer(i, name, group, zoom=zoom, period=period)
			else:
				self.add_map_layer(i, name, group, kept.get('colors'), zoom=zoom, period=period)

	def add_map_layer(self, res, name=None, group=None, colors=None, zoom=True, period=None):
		"""Add the GeoTIFF of a map with the colour ramp of MonitorEO (percentiles 5 and 95, or COLORS: (min, max))
		and zoom to it; with GROUP, in that group of the layer tree, and with PERIOD (first and last day), with those
		days in the Temporal Controller."""
		name = name or res['name']
		layer = QgsRasterLayer(res['file'], name)
		if not layer.isValid():
			raise RuntimeError(f"QGIS could not open {res['file']}")
		if res['min'] is None:
			self.message(f"{name}: no values in the region (no images, or all filtered out)", 'Warning', 10)
		else:
			pseudocolor(layer, *(colors or (res['min'], res['max'])), res['palette'])
		bands = ', '.join(res.get('bands') or [])
		# (the data of Earth Engine outside the catalog may have no unit: none was given)
		layer.setAbstract(f"MonitorEO: {res['name']} {unit_text(res)}, pixels of {res['resolution']:g} m"
		                  + (f", {res['images']:,} images" if res.get('images') is not None else '')
		                  + (f", bands {bands}" if bands else '') + f". Temporary GeoTIFF: {res['file']}"
		                  + references_text(res))
		if period:
			dated(layer, *period)
		add_layer(layer, group)
		if zoom:
			self.zoom_to(layer.extent(), layer.crs())
		native = res['resolution'] <= res['native_resolution']
		self.message(f"Layer added: {name}, pixels of {res['resolution']:g} m"
		             + ('' if native else ' (big region: pixels bigger than those of the data; for the full resolution, '
		                                 'export the map to Google Drive)')
		             + '. Query the values with the Identify Features tool', 'Success', 10)

	def add_rgb_layer(self, res, name=None, group=None, stretch=None, zoom=True, period=None):
		"""Add the GeoTIFF of a true colour (services.download_rgb: the bands red, green and blue, reflectance) with the
		three bands stretched together between its percentiles 2 and 98 (or STRETCH: (min, max), that of the first true
		colour of a series, so that its dates can be compared) and zoom to it; with GROUP and PERIOD, as
		add_map_layer."""
		name = name or res['name']
		layer = QgsRasterLayer(res['file'], name)
		if not layer.isValid():
			raise RuntimeError(f"QGIS could not open {res['file']}")
		lo, hi = stretch or (res['min'], res['max'])
		if res['min'] is None:
			self.message(f"{name}: no values in the region (no images, or all filtered out)", 'Warning', 10)
		if lo is not None and hi is not None:
			rgb(layer, lo, hi)
		caption = rgb_caption(lo, hi) if lo is not None and hi is not None else 'True colour (red, green, blue)'
		layer.setAbstract(f"MonitorEO: {res['name']} {res['unit']}, pixels of {res['resolution']:g} m"
		                  + (f", {res['images']:,} images" if res.get('images') is not None else '')
		                  + f", bands {', '.join(res.get('bands') or ['red', 'green', 'blue'])}. {caption}. "
		                  f"Temporary GeoTIFF: {res['file']}" + references_text(res))
		if period:
			dated(layer, *period)
		add_layer(layer, group)
		if zoom:
			self.zoom_to(layer.extent(), layer.crs())
		native = res['resolution'] <= res['native_resolution']
		self.message(f"Layer added: {name}, pixels of {res['resolution']:g} m"
		             + ('' if native else ' (big region: pixels bigger than those of the data)')
		             + f'. {caption}. Query the reflectance with the Identify Features tool', 'Success', 10)

	def zoom_to(self, rect, crs):
		canvas = self.iface.mapCanvas()
		tr = QgsCoordinateTransform(crs, canvas.mapSettings().destinationCrs(), QgsProject.instance())
		r = tr.transformBoundingBox(rect)
		r.scale(1.05)
		canvas.setExtent(r)
		canvas.refresh()

	def add_tile_layer(self, res, name=None, group=None, zoom=True, period=None):
		"""Add the Earth Engine tiles RES of a map (with its colour ramp) or of a true colour (services.rgb_map: without
		palette, the bands red, green and blue), when its GeoTIFF could not be downloaded; with GROUP and PERIOD, as
		add_map_layer."""
		name = name or res['name']
		uri = QgsDataSourceUri()
		uri.setParam('type', 'xyz')
		uri.setParam('url', res['url'])
		uri.setParam('zmin', '0')
		uri.setParam('zmax', '20')
		layer = QgsRasterLayer(bytes(uri.encodedUri()).decode(), name, 'wms')
		if not layer.isValid():
			raise RuntimeError('QGIS could not open the tiles of Earth Engine')
		# the unit of a map of values (see unit_text); that of a true colour, as it comes
		unit = unit_text(res) if res.get('palette') else str(res.get('unit') or '')
		if res.get('palette'):
			colours = (f"Color ramp from {res['min']:.4g} to {res['max']:.4g}: "
			           f"{', '.join('#' + c for c in res['palette'])}")
			shown = f"from {res['min']:.4g} to {res['max']:.4g} {unit}"
		else:  # a true colour
			colours = shown = rgb_caption(res['min'], res['max'])
		layer.setAbstract(f"MonitorEO: {res['name']} {unit}".rstrip() + f". {colours}. Earth Engine tiles, valid for a "
		                  'few hours.' + references_text(res))
		if period:
			dated(layer, *period)
		add_layer(layer, group)
		if zoom:
			self.zoom_to(QgsRectangle(*res['bounds']), QgsCoordinateReferenceSystem('EPSG:4326'))
		self.message(f"Tile layer added: {name} ({shown}; no queryable values: the GeoTIFF could not be downloaded: "
		             f"{res.get('error')})", 'Warning', 15)

	def result_group(self, res):
		"""The group of the layer tree with the maps of the result RES (made the first time, on top)."""
		root = QgsProject.instance().layerTreeRoot()
		return root.findGroup(res['label']) or root.insertGroup(0, res['label'])

	def add_result_map(self, res, entry, significant=False, kind='index'):
		"""Add the map ENTRY (one of res['maps']: its whole period or one of its steps) of the series or trends RES,
		as a GeoTIFF in the group of the result, with the colours of the first map of the result, so that its maps can
		be compared; the dates of a series, with their days in the Temporal Controller of QGIS. Trends with
		SIGNIFICANT: only the pixels with p < ALPHA. A series with KIND 'rgb' or 'both': the true colour of the same
		images and pixels (services.download_rgb, with the same arguments and on the same grid), stretched as the first
		true colour of the result, alone or under the map, with the same days. If a GeoTIFF cannot be downloaded,
		Earth Engine tiles."""
		a = res['args']
		region = a['region']
		# the same pixels as the series: its filters, season and conditions (those with dates, over its whole period);
		# of the data of Earth Engine outside the catalog, their ID, band, scale, offset and unit (SOURCE)
		var = {k: a[k] for k in ('variable', 'sensor', 'collection', 'quality', 'season', 'where') + SOURCE if k in a}
		folder = tempfile.mkdtemp(prefix='monitoreo_')
		if res['kind'] == 'trends':
			kind = 'index'
			opts = dict(var, start=a['start'], end=a['end'], step=entry.get('step') or a['step'], part=entry.get('part'),
			            metric=a['metric'], alpha=ALPHA if significant else None)
			download, tiles = services.download_trend, services.trend_map
		else:
			opts = dict(var, start=entry['start'], end=entry['end'], metric=a['metric'])
			download, tiles = services.download_image, services.map_layer
		# (min, max) of the first map and of the first true colour of the result
		colors, stretch = res.get('colors'), res.get('rgb_stretch')
		label = f"{res['title'].split(' | ')[0]} · {entry['label']}"
		name = label + (' (p < 0.05)' if significant else '')
		period = (entry['start'], entry['end']) if res['kind'] == 'series' and entry['key'] else None
		title = {'index': f'Map of {name}', 'rgb': f'True colour of {label}', 'both': f'Map and true colour of {label}'}

		def work():
			return maps_work(kind, region, opts, folder, download, tiles, colors, stretch)

		def done(r):
			first = 'colors' not in res and 'rgb_stretch' not in res  # zoom to the first map of the result
			self.add_maps(r, name, f'{label} · true colour', self.result_group(res), first, period, res)

		self.run_task(title[kind], work, done)

	def run_export_image(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		res = self.resolution.value() or None
		folder = self.folder.text().strip() or 'MonitorEO'
		metric, temporal, inter = self.map_metric.currentData(), self.temporal.currentData(), self.interannual.currentData()
		time = {} if (self.variable.currentData() or {}).get('static') else \
			{'metric': metric, 'temporal': temporal, 'interannual': inter}  # none for the fixed layers
		self.run_task(f"Export the map of {data_name(var, sensor=False)}",
		              lambda: services.export_image(region, resolution=res, folder=folder, **time, **var),
		              self.follow_export)

	def run_export_series(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		folder = self.folder.text().strip() or 'MonitorEO'
		step, metric, stat = self.step.currentData(), self.ts_metric.currentData(), self.stat.currentData()
		self.run_task(f"Export the series of {data_name(var, sensor=False)}",
		              lambda: services.time_series_to_drive(region, step=step, metric=metric, stat=stat, folder=folder,
		                                                    **var), self.follow_export)

	# Burn severity ----------------------------------------------------------------------------------------------

	def theme_has(self, name):
		"""Whether the theme chosen has the analysis NAME of its own (e.g. burn_severity, of the fires), as themeHas of
		the Earth Engine app: with «All the variables», every analysis."""
		key = self.theme.currentData()
		return key is None or any(t['key'] == key and name in t['analyses'] for t in services.themes('en'))

	def show_analyses(self):
		"""The groups of the analyses of a theme, shown only in that theme (and with «All the variables»)."""
		self.fire_box.setVisible(self.theme_has('burn_severity'))

	def fill_fire_sensors(self, choose=None):
		"""The sensors of the burn index chosen (services.BURN_SENSORS): Sentinel-2 and Landsat, and MODIS Terra and
		Aqua only for the RdNBR. Keeps the sensor chosen (at first, CHOOSE) if the index has it; going back to the dNBR
		or the RBR with MODIS chosen chooses Landsat (as the Earth Engine app: a big region), never MODIS; else,
		Sentinel-2."""
		index = self.fire_index.currentData()
		current = self.fire_sensor.currentData() if self.fire_sensor.count() else choose
		items = FIRE_SENSORS + (FIRE_MODIS if 'Modis' in services.BURN_SENSORS.get(index, ()) else [])
		values = [v for _, v in items]
		if current not in values:
			current = 'Landsat' if current in [v for _, v in FIRE_MODIS] else 'Sentinel-2'
		self.fire_sensor.blockSignals(True)
		self.fire_sensor.clear()
		for i, (label, value) in enumerate(items):
			self.fire_sensor.addItem(label, value)
			if value in FIRE_TIPS:
				self.fire_sensor.setItemData(i, FIRE_TIPS[value], Qt.ItemDataRole.ToolTipRole)
		self.fire_sensor.setCurrentIndex(values.index(current))
		self.fire_sensor.blockSignals(False)

	def fire_source(self):
		"""The sensor and the collection of the burn severity (services.burn_severity): MODIS is the sensor 'Modis'
		with the collection of Terra (MOD09GA) or Aqua (MYD09GA); Sentinel-2 and Landsat go without a collection."""
		value = self.fire_sensor.currentData()
		if value in [v for _, v in FIRE_MODIS]:
			return 'Modis', value
		return value, None

	def fire_periods(self):
		"""The periods before and after the fire ([first day, last day] each), checked."""
		day = lambda key: self.fire_dates[key].date().toString('yyyy-MM-dd')  # noqa: E731
		before, after = [day('before_start'), day('before_end')], [day('after_start'), day('after_end')]
		if before[0] > before[1] or after[0] > after[1]:
			raise ValueError('Burn severity: each period has to end after it starts')
		if before[1] >= after[0]:
			raise ValueError('Burn severity: the period before the fire has to end before the period after it starts')
		return before, after

	def run_burn(self):
		"""Burn severity of a fire over the region (services.burn_severity), with the pixel filters and the conditions
		of «Only the pixels where» of the panel (over the period before the fire): the window of its table (hectares
		of each class of the USGS and burned area, statistics of the RBR, or hectares of each class of Miller & Thode
		2007, changed area and statistics of the RdNBR) and its GeoTIFF, in colours."""
		try:
			region = self.region()
			before, after = self.fire_periods()
			where = self.where_args(before)
		except Exception as e:
			self.message(str(e), 'Warning')
			return
		quality = self.quality_args(own=True)  # the NBR, whatever the variable selected
		(sensor, collection), index = self.fire_source(), self.fire_index.currentData()
		source = self.fire_sensor.currentText().split(' (')[0]  # Sentinel-2, Landsat, MODIS Terra or MODIS Aqua
		stem = os.path.join(tempfile.mkdtemp(prefix='monitoreo_'),
		                    'burn_severity' + {'RBR': '_rbr', 'RdNBR': '_rdnbr'}.get(index, ''))
		more = {'collection': collection} if collection else {}  # MODIS (RdNBR): Terra or Aqua

		def work():
			return services.burn_severity(region, sensor, before[0], before[1], after[0], after[1], quality=quality,
			                              path=stem + '.tif', csv=stem + '.csv', max_pixels=MAP_PIXELS, index=index,
			                              where=where, **more)

		def done(res):
			if not any((r.get('ha') or 0) > 0 for r in res.get('classes') or res.get('stats') or []):
				self.message(f"{res['title'].split(' | ')[0]}: no values in the region (no images in a period, or all "
				             'filtered out)', 'Warning', 15)
				return
			res['label'] = burn_label(res['title'], collection)
			res['kind'] = 'burn'
			res['args'] = dict({'region': region, 'sensor': sensor, 'start': before[0], 'end': before[1],
			                    'other_start': after[0], 'other_end': after[1], 'index': index}, **more)
			self.add_burn_layer(res)
			self.add_result(res)

		self.run_task(f'Burn severity ({index}, {source})', work, done)

	def add_burn_layer(self, res):
		"""Add the GeoTIFF of the burn severity RES coloured as in the other tools (fire.map_style, as the assistant):
		the classes of its band severity, with their names and values in the legend (those of the USGS for the dNBR,
		those of Miller & Thode 2007 for the RdNBR), or the RBR from red (burned) to green (regrowth)."""
		name = res.get('label') or res['title']
		layer = QgsRasterLayer(res['file'], name)
		if not layer.isValid():
			raise RuntimeError(f"QGIS could not open {res['file']}")
		style = fire.map_style(res.get('bands'))
		if style and style.get('classes'):
			paletted(layer, style['band'], [dict(c, label=fire.class_label(c)) for c in style['classes']])
		elif style:
			pseudocolor(layer, style['min'], style['max'], style['palette'], band=style['band'])
		layer.setAbstract(f"MonitorEO: {name}, pixels of {res['resolution']:g} m, bands {', '.join(res['bands'])}. "
		                  f"Temporary GeoTIFF: {res['file']}" + references_text(res))
		add_layer(layer)
		self.zoom_to(layer.extent(), layer.crs())
		native = res['resolution'] <= res['native_resolution']
		self.message(f"Layer added: {name}, pixels of {res['resolution']:g} m"
		             + ('' if native else ' (big region: pixels bigger than those of the data)')
		             + '. Query the values with the Identify Features tool', 'Success', 10)

	# Exports ----------------------------------------------------------------------------------------------------

	def follow_export(self, res):
		res['state'] = 'PENDING'
		self.exports.append(res)
		self.show_exports()
		self.message(f"Exporting {res['file']} to Google Drive/{res['folder']}", 'Info')
		if not self.timer.isActive():
			self.timer.start(POLL_MS)

	def show_exports(self):
		self.export_status.setText('\n'.join(f"{e['file']}: {e['state'].lower()}" for e in self.exports[-6:]))

	def poll_exports(self):
		running = [e for e in self.exports if e['state'] not in ('SUCCEEDED', 'FAILED', 'CANCELLED', 'UNKNOWN')]
		if not running:
			self.timer.stop()
			return

		def work():
			return [(e, services.task_status(e['operation'])) for e in running]

		def done(states):
			for e, st in states:
				if st['state'] != e['state']:
					e['state'] = st['state']
					if st['state'] == 'SUCCEEDED':
						self.exported(e)
					elif st['state'] in ('FAILED', 'CANCELLED', 'UNKNOWN'):
						self.message(f"{e['file']}: {st['state'].lower()} {st['error'] or ''}", 'Critical', 15)
			self.show_exports()

		task = QgsTask.fromFunction('MonitorEO: state of the exports', lambda t: work(),
		                            on_finished=lambda exc, r=None: done(r) if exc is None else None)
		self.tasks.append(task)
		QgsApplication.taskManager().addTask(task)

	def exported(self, e):
		"""Open an exported GeoTIFF from Google Drive for desktop, if it is on this computer."""
		roots = services.local_drive_folders()
		files = []
		for root in roots:
			files += services.find_exported(os.path.join(root, e['folder']), e['file'])
		tifs = [f for f in files if f.lower().endswith('.tif')]
		if not tifs:
			self.message(f"{e['file']} is in Google Drive/{e['folder']}", 'Success', 10)
			return
		path = tifs[0]
		if len(tifs) > 1:
			from osgeo import gdal
			path = os.path.join(tempfile.mkdtemp(prefix='monitoreo_'), os.path.splitext(e['file'])[0] + '.vrt')
			gdal.BuildVRT(path, tifs)
		layer = QgsRasterLayer(path, os.path.splitext(e['file'])[0])
		if layer.isValid():
			QgsProject.instance().addMapLayer(layer)
			self.message(f"{e['file']} added from Google Drive ({path})", 'Success', 10)
