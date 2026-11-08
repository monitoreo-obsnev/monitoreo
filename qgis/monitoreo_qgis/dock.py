"""MonitorEO panel: region, variable, period and pixel filters, and the buttons of the time series, the map layer
and the exports to Google Drive. The work runs in QGIS tasks (QgsTask), so QGIS keeps responding; every
computation is a function of monitoreo.services, the same as in the MCP server and the R package. A bar shows the
EECUs of Earth Engine spent this month (the research EECUs of this user with the shared account, or the monthly quota
of the user's project) and the message bar warns when less than 10 % are left."""

import json
import os
import tempfile

from qgis.core import (Qgis, QgsApplication, QgsColorRampShader, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsDataSourceUri, QgsDateTimeRange, QgsProject, QgsRasterLayer, QgsRasterShader, QgsRectangle,
                       QgsSettings, QgsSingleBandPseudoColorRenderer, QgsTask)
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox
from qgis.PyQt.QtCore import QDate, QDateTime, QEvent, QPoint, Qt, QTime, QTimer, QUrl
from qgis.PyQt.QtGui import QColor, QDesktopServices, QPixmap
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDockWidget, QDoubleSpinBox, QFormLayout,
                                 QGroupBox, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QScrollArea,
                                 QToolButton, QVBoxLayout, QWhatsThis, QWidget)

from . import deps

deps.setup_path()
from monitoreo import services, steps, trends  # noqa: E402
from monitoreo.publish import period_text  # noqa: E402

from .helptexts import HELP, MANUAL, filters_help, variable_help  # noqa: E402

SETTINGS = 'MonitorEO/'
STEPS = [('Monthly', 'monthly'), ('Annual', 'annual'), ('16 days', '16-day'), ('Daily (days with images)', 'daily')]
METRICS = [('Mean', 'mean'), ('Median', 'median'), ('Minimum', 'min'), ('Maximum', 'max'), ('Percentile 5', 'p5'),
           ('Percentile 10', 'p10'), ('Percentile 90', 'p90'), ('Percentile 95', 'p95')]
STATS = [('Mean', 'mean'), ('Median', 'median'), ('Minimum', 'min'), ('Maximum', 'max'), ('Standard deviation', 'std')]
TEMPORAL = [('Whole period', 'period'), ('Each year, then between years', 'annual'),
            ('Each month, then between years', 'monthly')]
TREND_STEPS = [('Year', 'annual'), ('Months', 'monthly'), ('16 days', '16-day')]
REGIONS = [('Layer (selected features or all)', 'layer'), ('Map extent', 'extent'),
           ('Protected area (WDPA)', 'wdpa'), ('Ecoregion at the center of the map', 'ecoregion')]
POLL_MS = 30000
ALPHA = 0.05  # «Significant pixels only»: the pixels with Mann-Kendall p < ALPHA
MAX_VERTICES = 20000
MAP_PIXELS = 4000000  # maps downloaded as GeoTIFF: at most these pixels (16 MB); bigger regions get bigger pixels


def level(name):
	"""Qgis message level NAME (Info, Warning, Critical, Success) in QGIS 3 and 4."""
	enum = getattr(Qgis, 'MessageLevel', None)
	return getattr(enum, name) if enum is not None and hasattr(enum, name) else getattr(Qgis, name)


def pseudocolor(layer, vmin, vmax, palette):
	"""Colour LAYER (band 1) with the colours PALETTE (hex) spread from VMIN to VMAX."""
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
	renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
	renderer.setClassificationMin(vmin)
	renderer.setClassificationMax(vmax)
	layer.setRenderer(renderer)


def dated(layer, first, last):
	"""Give LAYER the days FIRST to LAST (YYYY-MM-DD) in the Temporal Controller of QGIS."""
	props = layer.temporalProperties()
	props.setMode(Qgis.RasterTemporalMode.FixedTemporalRange)
	begin = QDateTime(QDate.fromString(first, 'yyyy-MM-dd'), QTime(0, 0))
	end = QDateTime(QDate.fromString(last, 'yyyy-MM-dd').addDays(1), QTime(0, 0))
	props.setFixedTemporalRange(QgsDateTimeRange(begin, end, True, False))
	props.setIsActive(True)


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
		main.addWidget(box)

		box = QGroupBox('Variable')
		f = QFormLayout(box)
		self.variable = QComboBox()
		for v in services.list_variables(lang='en'):  # the English names of the catalog (vname_en, type_en)
			if v.get('two_periods'):  # RBR: only the burn severity of the Python package, the MCP server and the app
				continue
			self.variable.addItem(f"{v['variable']} · {v['sensor']} · {v['resolution_m']} m · {v['collection'].split('/')[-1]}", v)
			self.variable.setItemData(self.variable.count() - 1, f"{v['name']} ({v['unit']}), {v['dates']}",
			                          Qt.ItemDataRole.ToolTipRole)
		self.variable.setCurrentIndex(max(0, self.variable.findText('NDVI · Sentinel-2', Qt.MatchFlag.MatchContains)))
		f.addRow('Variable', info(self.variable, lambda: variable_help(self.variable.currentData())))
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
		b = QPushButton('Add the layer to the map')
		b.setToolTip('Downloads the map as a temporary GeoTIFF, with the values of the variable (queryable with the '
		             'Identify Features tool), at the resolution of the data or, in big regions, with bigger pixels '
		             f'(up to {MAP_PIXELS / 1e6:g} million pixels)')
		b.clicked.connect(self.run_map)
		f.addRow(b)
		main.addWidget(box)

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
		# the options that do not apply to the variable: the other metrics of the SCF, the filters and the dates of the
		# fixed layers (elevation, slope)
		self.variable.currentIndexChanged.connect(self.variable_changed)
		self.variable_changed()
		main.addWidget(self.about_box())
		main.addStretch()

		scroll = QScrollArea()
		scroll.setWidgetResizable(True)
		scroll.setWidget(body)
		self.setWidget(scroll)
		self.region_changed()

	def sync_fields(self):
		layer = self.layer.currentLayer()
		if self.name_field.layer() is not layer:
			self.name_field.setLayer(layer)

	def region_changed(self):
		kind = self.region_kind.currentData()
		self.layer_row.setVisible(kind == 'layer')
		for w in (self.wdpa_row, self.wdpa_field, self.wdpa_label):
			if w is not None:
				w.setVisible(kind == 'wdpa')

	def message(self, text, lvl='Info', duration=6):
		self.iface.messageBar().pushMessage('MonitorEO', text, level=level(lvl), duration=duration)

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
		for text in (about.DESCRIPTION['en'], about.ACKNOWLEDGEMENTS['en'],
		             f"<b>{about.HOW_TO_CITE['en']}:</b> " + about.CITATION.replace(doi, f'<a href="{doi}">{doi}</a>'),
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
		if kind == 'wdpa':
			if self.wdpa.currentData() is None:
				raise ValueError('search for a protected area and choose it in the list')
			return {'wdpa_id': self.wdpa.currentData()}
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
		quality = {k: w.isChecked() for k, w in self.filters.items()}
		quality['cloud_score'] = 0.6 if self.cloud_score.isChecked() else None
		args = {'variable': v['variable'], 'sensor': v['sensor'], 'collection': v['collection'],
		        'start': self.start.date().toString('yyyy-MM-dd'), 'end': self.end.date().toString('yyyy-MM-dd'),
		        'quality': quality}
		if self.season_on.isChecked():
			args['season'] = [self.season_start.text().strip(), self.season_end.text().strip()]
		return args

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

		self.run_task('Search protected areas', lambda: services.find_protected_areas(text, 30), done)

	def other_period(self):
		"""(first day, last day) of the period to compare with the reference one, or None."""
		if not self.compare_on.isChecked() or (self.variable.currentData() or {}).get('static'):
			return None
		return self.other_start.date().toString('yyyy-MM-dd'), self.other_end.date().toString('yyyy-MM-dd')

	def add_result(self, res):
		"""Keep a result (series, trends or comparison) in the list of the session and open its window."""
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
			self.add_result(res)

		self.run_task(f"Time series of {var['variable']} ({var['sensor']})", work, done)

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

		self.run_task(f"Comparison of periods of {var['variable']} ({var['sensor']})", work, done)

	def variable_changed(self):
		"""The metrics of the images, fixed at the only metric of the variable if it has one, and its pixel filters,
		greyed out and checked those always on if they are fixed (the snow cover frequency: the mean, the % of the clear
		observations with snow, without clouds and water). The filters chosen before come back with another variable.
		The fixed layers without dates (elevation, slope): only maps, so the period, the metrics, the filters, the time
		series and the trends greyed out."""
		v = self.variable.currentData() or {}
		only = v.get('metric')
		static = bool(v.get('static'))
		for w in (self.ts_metric, self.trend_metric, self.map_metric):
			if only:
				w.setCurrentIndex(max(0, w.findData(only)))
			w.setEnabled(not only and not static)
			w.setToolTip(f"{v['variable']} only takes the {only}" if only else '')
		for w in (self.start, self.end, self.compare_on, self.season_on, self.season_start, self.season_end,
		          self.temporal, self.interannual, self.series_box, self.trends_box, self.export_series_button):
			w.setEnabled(not static)
		for w in (self.other_start, self.other_end):
			w.setEnabled(not static and self.compare_on.isChecked())
		fixed = v.get('fixed_filters')
		self.cloud_score.setEnabled(fixed is None)
		if fixed is not None and self.chosen_filters is None:
			self.chosen_filters = {k: w.isChecked() for k, w in self.filters.items()}
		for k, w in self.filters.items():
			if fixed is not None:
				w.setChecked(k in fixed)
			elif self.chosen_filters is not None:
				w.setChecked(self.chosen_filters[k])
			w.setEnabled(fixed is None)
			w.setToolTip(f"Fixed filters of {v['variable']}: they cannot be changed" if fixed is not None else '')
		if fixed is None:
			self.chosen_filters = None

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

		self.run_task(f"Trends of {var['variable']} ({var['sensor']})", work, done)

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

		self.run_task(f"Trend map of {var['variable']} ({var['sensor']})", work,
		              lambda res: self.add_tile_layer(res) if 'url' in res else self.add_map_layer(res))

	def update_series_list(self):
		self.series_list.clear()
		for i, res in enumerate(self.series):
			self.series_list.addItem(f"{i + 1}. {res['label']}", i)
		self.series_list.setEnabled(bool(self.series))
		self.show_series_button.setEnabled(bool(self.series))

	def show_series(self):
		"""Open the window of the chosen series, trends or comparison (or bring it to the front if it is open)."""
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
		path = os.path.join(tempfile.mkdtemp(prefix='monitoreo_'), 'map.tif')
		other = self.other_period()
		opts = dict(var, metric=metric, temporal=temporal, interannual=inter)
		if other:
			opts.update(other_start=other[0], other_end=other[1])
		download, tiles = ((services.download_comparison, services.compare_map) if other else
		                   (services.download_image, services.map_layer))

		def work():
			"""The map as a GeoTIFF with the values (with OTHER, the difference between the periods, and both); if it
			cannot be downloaded, Earth Engine tiles (colours only)."""
			try:
				return download(region, path=path, max_pixels=MAP_PIXELS, **opts)
			except Exception as e:
				res = tiles(region, **opts)
				res['error'] = str(e)
				return res

		self.run_task(f"Map of {var['variable']} ({var['sensor']})", work,
		              lambda res: self.add_tile_layer(res) if 'url' in res else self.add_map_layer(res))

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
		layer.setAbstract(f"MonitorEO: {res['name']} {res['unit']}, pixels of {res['resolution']:g} m"
		                  + (f", {res['images']:,} images" if res.get('images') is not None else '')
		                  + (f", bands {bands}" if bands else '') + f". Temporary GeoTIFF: {res['file']}")
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

	def zoom_to(self, rect, crs):
		canvas = self.iface.mapCanvas()
		tr = QgsCoordinateTransform(crs, canvas.mapSettings().destinationCrs(), QgsProject.instance())
		r = tr.transformBoundingBox(rect)
		r.scale(1.05)
		canvas.setExtent(r)
		canvas.refresh()

	def add_tile_layer(self, res, name=None, group=None, zoom=True):
		name = name or res['name']
		uri = QgsDataSourceUri()
		uri.setParam('type', 'xyz')
		uri.setParam('url', res['url'])
		uri.setParam('zmin', '0')
		uri.setParam('zmax', '20')
		layer = QgsRasterLayer(bytes(uri.encodedUri()).decode(), name, 'wms')
		if not layer.isValid():
			raise RuntimeError('QGIS could not open the tiles of Earth Engine')
		layer.setAbstract(f"MonitorEO: {res['name']} {res['unit']}. Color ramp from {res['min']:.4g} to {res['max']:.4g}: "
		                  f"{', '.join('#' + c for c in res['palette'])}. Earth Engine tiles, valid for a few hours.")
		add_layer(layer, group)
		if zoom:
			self.zoom_to(QgsRectangle(*res['bounds']), QgsCoordinateReferenceSystem('EPSG:4326'))
		self.message(f"Tile layer added: {name} (from {res['min']:.4g} to {res['max']:.4g} {res['unit']}; "
		             f"no queryable values: the GeoTIFF could not be downloaded: {res.get('error')})", 'Warning', 15)

	def result_group(self, res):
		"""The group of the layer tree with the maps of the result RES (made the first time, on top)."""
		root = QgsProject.instance().layerTreeRoot()
		return root.findGroup(res['label']) or root.insertGroup(0, res['label'])

	def add_result_map(self, res, entry, significant=False):
		"""Add the map ENTRY (one of res['maps']: its whole period or one of its steps) of the series or trends RES,
		as a GeoTIFF in the group of the result, with the colours of the first map of the result, so that its maps can
		be compared; the dates of a series, with their days in the Temporal Controller of QGIS. Trends with
		SIGNIFICANT: only the pixels with p < ALPHA. If the GeoTIFF cannot be downloaded, Earth Engine tiles."""
		a = res['args']
		region = a['region']
		var = {k: a[k] for k in ('variable', 'sensor', 'collection', 'quality', 'season') if k in a}
		path = os.path.join(tempfile.mkdtemp(prefix='monitoreo_'), 'map.tif')
		if res['kind'] == 'trends':
			opts = dict(var, start=a['start'], end=a['end'], step=entry.get('step') or a['step'], part=entry.get('part'),
			            metric=a['metric'], alpha=ALPHA if significant else None)
			download, tiles = services.download_trend, services.trend_map
		else:
			opts = dict(var, start=entry['start'], end=entry['end'], metric=a['metric'])
			download, tiles = services.download_image, services.map_layer
		colors = res.get('colors')  # (min, max) of the first map of the result
		name = f"{res['title'].split(' | ')[0]} · {entry['label']}" + (' (p < 0.05)' if significant else '')
		period = (entry['start'], entry['end']) if res['kind'] == 'series' and entry['key'] else None

		def work():
			try:
				return download(region, path=path, max_pixels=MAP_PIXELS, **opts)
			except Exception as e:
				out = tiles(region, **opts, **({'vmin': colors[0], 'vmax': colors[1]} if colors else {}))
				out['error'] = str(e)
				return out

		def done(r):
			first = 'colors' not in res
			if first and r.get('min') is not None:
				res['colors'] = (r['min'], r['max'])
			group = self.result_group(res)
			if 'url' in r:
				self.add_tile_layer(r, name, group, zoom=first)
			else:
				self.add_map_layer(r, name, group, res.get('colors'), zoom=first, period=period)

		self.run_task(f'Map of {name}', work, done)

	def run_export_image(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		res = self.resolution.value() or None
		folder = self.folder.text().strip() or 'MonitorEO'
		metric, temporal, inter = self.map_metric.currentData(), self.temporal.currentData(), self.interannual.currentData()
		self.run_task(f"Export the map of {var['variable']}",
		              lambda: services.export_image(region, metric=metric, temporal=temporal, interannual=inter,
		                                            resolution=res, folder=folder, **var), self.follow_export)

	def run_export_series(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		folder = self.folder.text().strip() or 'MonitorEO'
		step, metric, stat = self.step.currentData(), self.ts_metric.currentData(), self.stat.currentData()
		self.run_task(f"Export the series of {var['variable']}",
		              lambda: services.time_series_to_drive(region, step=step, metric=metric, stat=stat, folder=folder,
		                                                    **var), self.follow_export)

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
