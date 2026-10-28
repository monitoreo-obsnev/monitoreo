"""MonitorEO panel: region, variable, period and pixel filters, and the buttons of the time series, the map layer
and the exports to Google Drive. The work runs in QGIS tasks (QgsTask), so QGIS keeps responding; every
computation is a function of monitoreo.services, the same as in the MCP server and the R package."""

import json
import os
import tempfile

from qgis.core import (Qgis, QgsApplication, QgsColorRampShader, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsDataSourceUri, QgsMapLayerProxyModel, QgsProject, QgsRasterLayer, QgsRasterShader,
                       QgsRectangle, QgsSettings, QgsSingleBandPseudoColorRenderer, QgsTask)
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox
from qgis.PyQt.QtCore import QDate, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QPixmap
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDockWidget, QDoubleSpinBox, QFormLayout,
                                 QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
                                 QWidget)

from . import deps

deps.setup_path()
from monitoreo import services, trends  # noqa: E402

SETTINGS = 'MonitorEO/'
STEPS = [('Mensual', 'monthly'), ('Anual', 'annual'), ('16 días', '16-day'), ('Diario (días con imágenes)', 'daily')]
METRICS = [('Media', 'mean'), ('Mediana', 'median'), ('Mínimo', 'min'), ('Máximo', 'max'), ('Percentil 5', 'p5'),
           ('Percentil 10', 'p10'), ('Percentil 90', 'p90'), ('Percentil 95', 'p95')]
STATS = [('Media', 'mean'), ('Mediana', 'median'), ('Mínimo', 'min'), ('Máximo', 'max'), ('Desviación típica', 'std')]
TEMPORAL = [('Todo el periodo', 'period'), ('Cada año y entre años', 'annual'), ('Cada mes y entre años', 'monthly')]
TREND_STEPS = [('Año', 'annual'), ('Meses', 'monthly'), ('16 días', '16-day')]
REGIONS = [('Capa (entidades seleccionadas o todas)', 'layer'), ('Extensión del mapa', 'extent'),
           ('Área protegida (WDPA)', 'wdpa'), ('Ecorregión del centro del mapa', 'ecoregion')]
POLL_MS = 30000
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


def polygon_filter():
	enum = getattr(Qgis, 'LayerFilter', None)
	return enum.PolygonLayer if enum is not None and hasattr(enum, 'PolygonLayer') else QgsMapLayerProxyModel.PolygonLayer


def combo(items, current=None):
	c = QComboBox()
	for label, value in items:
		c.addItem(label, value)
	if current is not None:
		c.setCurrentIndex([v for _, v in items].index(current))
	return c


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
		self.build()

	# Interface --------------------------------------------------------------------------------------------------

	def build(self):
		s = QgsSettings()
		body = QWidget()
		main = QVBoxLayout(body)

		box = QGroupBox('Google Earth Engine')
		f = QFormLayout(box)
		self.project = QLineEdit(s.value(SETTINGS + 'project', os.environ.get('EE_PROJECT', '')))
		self.project.setPlaceholderText('proyecto de Google Cloud registrado en Earth Engine')
		row = QHBoxLayout()
		row.addWidget(self.project)
		b = QPushButton('Conectar')
		b.clicked.connect(self.connect)
		row.addWidget(b)
		b = QPushButton('Autenticar…')
		b.setToolTip('Inicia sesión con tu cuenta de Google en el navegador (como earthengine authenticate)')
		b.clicked.connect(self.authenticate)
		row.addWidget(b)
		f.addRow('Proyecto', row)
		main.addWidget(box)

		box = QGroupBox('Región')
		f = QFormLayout(box)
		self.region_kind = combo(REGIONS)
		self.region_kind.currentIndexChanged.connect(self.region_changed)
		f.addRow('Región', self.region_kind)
		self.layer = QgsMapLayerComboBox()
		self.layer.setFilters(polygon_filter())
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
		lf.addRow('Capa', self.layer)
		lf.addRow('Nombre', self.name_field)
		f.addRow(self.layer_row)
		self.wdpa_row = QWidget()
		wl = QHBoxLayout(self.wdpa_row)
		wl.setContentsMargins(0, 0, 0, 0)
		self.wdpa_text = QLineEdit()
		self.wdpa_text.setPlaceholderText('nombre del área (p. ej. Sierra Nevada)')
		self.wdpa_text.returnPressed.connect(self.search_wdpa)
		wl.addWidget(self.wdpa_text)
		b = QPushButton('Buscar')
		b.clicked.connect(self.search_wdpa)
		wl.addWidget(b)
		f.addRow(self.wdpa_row)
		self.wdpa = QComboBox()
		f.addRow('Área', self.wdpa)
		self.wdpa_label = f.labelForField(self.wdpa)
		main.addWidget(box)

		box = QGroupBox('Variable')
		f = QFormLayout(box)
		self.variable = QComboBox()
		for v in services.list_variables():
			self.variable.addItem(f"{v['variable']} · {v['sensor']} · {v['resolution_m']} m · {v['collection'].split('/')[-1]}", v)
			self.variable.setItemData(self.variable.count() - 1, f"{v['name']} ({v['unit']}), {v['dates']}",
			                          Qt.ItemDataRole.ToolTipRole)
		self.variable.setCurrentIndex(max(0, self.variable.findText('NDVI · Sentinel-2', Qt.MatchFlag.MatchContains)))
		f.addRow('Variable', self.variable)
		self.start = QDateEdit(QDate.fromString(s.value(SETTINGS + 'start', '2020-01-01'), 'yyyy-MM-dd'))
		self.end = QDateEdit(QDate.fromString(s.value(SETTINGS + 'end', '2021-12-31'), 'yyyy-MM-dd'))
		for d in (self.start, self.end):
			d.setCalendarPopup(True)
			d.setDisplayFormat('yyyy-MM-dd')
		row = QHBoxLayout()
		row.addWidget(self.start)
		row.addWidget(QLabel('a'))
		row.addWidget(self.end)
		f.addRow('Periodo', row)
		self.compare_on = QCheckBox('otro periodo:')
		self.compare_on.setToolTip('Compara el periodo de referencia (el de arriba) con este: la serie temporal da la '
		                           'media de cada parte del año en los dos periodos y su diferencia, y el mapa, la '
		                           'diferencia (este periodo menos el de referencia)')
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
				row.addWidget(QLabel('a'))
			row.addWidget(d)
		f.addRow('Comparar con', row)
		self.season_on = QCheckBox('solo')
		self.season_start = QLineEdit('06-01')
		self.season_end = QLineEdit('09-30')
		for w in (self.season_start, self.season_end):
			w.setMaximumWidth(60)
			w.setPlaceholderText('MM-DD')
		row = QHBoxLayout()
		row.addWidget(self.season_on)
		row.addWidget(self.season_start)
		row.addWidget(QLabel('a'))
		row.addWidget(self.season_end)
		row.addWidget(QLabel('de cada año'))
		row.addStretch()
		f.addRow('Temporada', row)
		self.filters = {}
		row = QHBoxLayout()
		for key, label in (('clouds', 'nubes'), ('water', 'agua'), ('snow', 'nieve'), ('aerosols', 'aerosoles')):
			self.filters[key] = QCheckBox(label)
			self.filters[key].setChecked(True)
			row.addWidget(self.filters[key])
		f.addRow('Quitar píxeles con', row)
		self.cloud_score = QCheckBox('nubes de Sentinel-2 con Cloud Score+ (si no, con SCL, como MonitorEO)')
		self.cloud_score.setChecked(True)
		f.addRow('', self.cloud_score)
		main.addWidget(box)

		box = QGroupBox('Serie temporal')
		f = QFormLayout(box)
		self.step = combo(STEPS, 'monthly')
		self.ts_metric = combo(METRICS, 'mean')
		self.stat = combo(STATS, 'mean')
		f.addRow('Paso', self.step)
		f.addRow('Métrica de cada paso', self.ts_metric)
		f.addRow('Estadístico de la región', self.stat)
		b = QPushButton('Calcular la serie temporal')
		b.clicked.connect(self.run_series)
		f.addRow(b)
		self.series_list = QComboBox()  # the series computed in this session, to open them again
		self.series_list.setToolTip('Series calculadas en esta sesión de QGIS')
		self.show_series_button = QPushButton('Ver')
		self.show_series_button.setToolTip('Abre otra vez la gráfica y la tabla de la serie elegida')
		self.show_series_button.clicked.connect(self.show_series)
		row = QHBoxLayout()
		row.addWidget(self.series_list, 1)
		row.addWidget(self.show_series_button)
		f.addRow('Series', row)
		self.update_series_list()
		main.addWidget(box)

		box = QGroupBox('Tendencias (Mann-Kendall y Sen)')
		box.setToolTip('Tendencia de cada parte del año a lo largo de los años del periodo, como las "Tendencias '
		               'estacionales" de MonitorEO: τ de Kendall, Z y p-valor de Mann-Kendall y pendiente de Sen '
		               '(cambio por año). Mejor con 8 años o más')
		f = QFormLayout(box)
		self.trend_step = combo(TREND_STEPS, 'annual')
		self.trend_part = QComboBox()
		self.trend_step.currentIndexChanged.connect(self.update_trend_parts)
		self.update_trend_parts()
		self.trend_metric = combo(METRICS, 'mean')
		self.trend_alpha = QCheckBox('solo píxeles con tendencia significativa (p < 0,05)')
		f.addRow('Partes del año', self.trend_step)
		f.addRow('Métrica de cada año', self.trend_metric)
		b = QPushButton('Tabla de tendencias de la región')
		b.setToolTip('Tendencia de cada parte del año del estadístico de la región (el de la serie temporal)')
		b.clicked.connect(self.run_trend_table)
		f.addRow(b)
		f.addRow('Parte del año del mapa', self.trend_part)
		f.addRow('', self.trend_alpha)
		b = QPushButton('Mapa de tendencia')
		b.setToolTip('GeoTIFF temporal con la pendiente de Sen, τ, Z, p-valor, ordenada y número de años de cada píxel '
		             '(consultables con la herramienta Identificar)')
		b.clicked.connect(self.run_trend_map)
		f.addRow(b)
		main.addWidget(box)

		box = QGroupBox('Mapa')
		f = QFormLayout(box)
		self.map_metric = combo(METRICS, 'median')
		self.temporal = combo(TEMPORAL, 'period')
		self.interannual = combo(METRICS[:4], 'mean')
		f.addRow('Métrica', self.map_metric)
		f.addRow('Agregación temporal', self.temporal)
		f.addRow('Métrica entre años', self.interannual)
		b = QPushButton('Añadir la capa al mapa')
		b.setToolTip('Descarga el mapa como GeoTIFF temporal, con los valores de la variable (consultables con la '
		             'herramienta Identificar), a la resolución de los datos o, en regiones grandes, con píxeles '
		             f'mayores (hasta {MAP_PIXELS / 1e6:g} millones de píxeles)')
		b.clicked.connect(self.run_map)
		f.addRow(b)
		main.addWidget(box)

		box = QGroupBox('Exportar a Google Drive')
		f = QFormLayout(box)
		self.resolution = QDoubleSpinBox()
		self.resolution.setRange(0, 100000)
		self.resolution.setSpecialValueText('la de los datos')
		self.resolution.setSuffix(' m')
		f.addRow('Resolución', self.resolution)
		self.folder = QLineEdit(s.value(SETTINGS + 'folder', 'MonitorEO'))
		f.addRow('Carpeta de Drive', self.folder)
		row = QHBoxLayout()
		b = QPushButton('Mapa (GeoTIFF)')
		b.clicked.connect(self.run_export_image)
		row.addWidget(b)
		b = QPushButton('Serie (CSV)')
		b.clicked.connect(self.run_export_series)
		row.addWidget(b)
		f.addRow(row)
		self.export_status = QLabel('')
		self.export_status.setWordWrap(True)
		f.addRow(self.export_status)
		main.addWidget(box)
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
		for w in (self.wdpa_row, self.wdpa, self.wdpa_label):
			if w is not None:
				w.setVisible(kind == 'wdpa')

	def message(self, text, lvl='Info', duration=6):
		self.iface.messageBar().pushMessage('MonitorEO', text, level=level(lvl), duration=duration)

	def about_box(self):
		"""What MonitorEO-OBSNEV is and who funds it, with the logos of the institutions and projects."""
		from monitoreo import about
		box = QGroupBox('Acerca de MonitorEO')
		lay = QVBoxLayout(box)
		for path in about.about('es')['logos']:
			logo = QLabel()
			logo.setPixmap(QPixmap(path).scaledToWidth(330, Qt.TransformationMode.SmoothTransformation))
			logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
			lay.addWidget(logo)
		for text in (about.DESCRIPTION['es'], about.ACKNOWLEDGEMENTS['es'],
		             f'<a href="{about.APP}">App de MonitorEO</a> · <a href="{about.MANUAL}">Manual</a> · '
		             f'<a href="{about.REPOSITORY}">Código</a>'):
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
				raise ValueError('busca un área protegida y elígela en la lista')
			return {'wdpa_id': self.wdpa.currentData()}
		layer = self.layer.currentLayer()
		if layer is None:
			raise ValueError('elige una capa de polígonos')
		self.sync_fields()
		feats = list(layer.getSelectedFeatures()) or list(layer.getFeatures())
		if not feats:
			raise ValueError(f'la capa {layer.name()} no tiene entidades')
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
			services.init(project)
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
		self.run_task('Conectar con Earth Engine', lambda: services.project(),
		              lambda p: self.message(f'Conectado con Earth Engine (proyecto {p})', 'Success'))

	def authenticate(self):
		def work():
			import ee
			ee.Authenticate(auth_mode='localhost', force=True)
			return True

		task = QgsTask.fromFunction('Autenticar en Earth Engine', lambda t: work(),
		                            on_finished=lambda e, r=None: self.message(
			                            'Autenticado en Earth Engine' if e is None else f'Autenticación: {e}',
			                            'Success' if e is None else 'Critical', 10))
		self.tasks.append(task)
		QgsApplication.taskManager().addTask(task)
		self.message('Inicia sesión con tu cuenta de Google en el navegador', 'Info', 10)

	def search_wdpa(self):
		text = self.wdpa_text.text().strip()
		if not text:
			return

		def done(parks):
			self.wdpa.clear()
			for p in parks:
				self.wdpa.addItem(f"{p['NAME']} · {p.get('DESIG', '')} · {p.get('ISO3', '')} · {p.get('REP_AREA', 0):.0f} km² "
				                  f"(WDPA {p['SITE_ID']})", int(p['SITE_ID']))
			self.message(f'{len(parks)} áreas protegidas con "{text}"', 'Info', 4)

		self.run_task('Buscar áreas protegidas', lambda: services.find_protected_areas(text, 30), done)

	def other_period(self):
		"""(first day, last day) of the period to compare with the reference one, or None."""
		if not self.compare_on.isChecked():
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
			return services.time_series(region, step=step, metric=metric, stat=stat, csv=os.path.join(tmp, 'serie.csv'),
			                            **var)

		def done(res):
			from .results import SeriesDialog, chart_png
			if not res['rows']:
				self.message('La serie no tiene valores', 'Warning')
				return
			# the chart is drawn here, in the main thread: matplotlib in the thread of a task can crash QGIS (the
			# OpenBLAS of numpy overflows the small stack of those threads on macOS)
			res['chart'] = chart_png(res, os.path.join(tmp, 'serie.png'))
			res['label'] = f"{res['title']} · {', '.join(res['regions'])}"
			res['kind'] = 'series'
			self.add_result(res)

		self.run_task(f"Serie temporal de {var['variable']} ({var['sensor']})", work, done)

	def run_comparison(self, region, var, other, step, metric, stat, tmp):
		if step not in trends.STEPS:
			self.message('Para comparar periodos, elige el paso mensual, de 16 días o anual', 'Warning')
			return

		def work():
			return services.compare_series(region, other_start=other[0], other_end=other[1], step=step, metric=metric,
			                               stat=stat, csv=os.path.join(tmp, 'comparacion.csv'), **var)

		def done(res):
			from .results import comparison_png
			if not any(r['reference'] is not None or r['other'] is not None for r in res['profile']):
				self.message('La comparación no tiene valores', 'Warning')
				return
			res['chart'] = comparison_png(res, step, os.path.join(tmp, 'comparacion.png'))  # in the main thread
			res['label'] = f"Comparación: {res['title']}"
			res['kind'] = 'comparison'
			self.add_result(res)

		self.run_task(f"Comparación de periodos de {var['variable']} ({var['sensor']})", work, done)

	def update_trend_parts(self):
		step = self.trend_step.currentData()
		self.trend_part.clear()
		for p in trends.parts(step):
			self.trend_part.addItem('el año' if step == 'annual' else trends.part_label(step, p), p)
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
			                            csv=os.path.join(tmp, 'tendencias.csv'), **var)

		def done(res):
			from .results import trends_png
			if not any(r['slope'] is not None for r in res['rows']):
				self.message('No hay años suficientes para calcular tendencias (hacen falta 2 o más)', 'Warning')
				return
			res['chart'] = trends_png(res, os.path.join(tmp, 'tendencias.png'))  # in the main thread
			res['label'] = f"Tendencias: {res['title']}"
			res['kind'] = 'trends'
			self.add_result(res)

		self.run_task(f"Tendencias de {var['variable']} ({var['sensor']})", work, done)

	def run_trend_map(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		step, part, metric = self.trend_step.currentData(), self.trend_part.currentData(), self.trend_metric.currentData()
		alpha = 0.05 if self.trend_alpha.isChecked() else None
		path = os.path.join(tempfile.mkdtemp(prefix='monitoreo_'), 'tendencia.tif')

		def work():
			try:
				return services.download_trend(region, step=step, part=part, metric=metric, alpha=alpha, path=path,
				                               max_pixels=MAP_PIXELS, **var)
			except Exception as e:
				res = services.trend_map(region, step=step, part=part, metric=metric, alpha=alpha, **var)
				res['error'] = str(e)
				return res

		self.run_task(f"Mapa de tendencia de {var['variable']} ({var['sensor']})", work,
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
			dlg = self.series_dialogs[i] = cls(res, self.iface.mainWindow())
		dlg.show()
		dlg.raise_()
		dlg.activateWindow()

	def run_map(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		metric, temporal, inter = self.map_metric.currentData(), self.temporal.currentData(), self.interannual.currentData()
		path = os.path.join(tempfile.mkdtemp(prefix='monitoreo_'), 'mapa.tif')
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

		self.run_task(f"Mapa de {var['variable']} ({var['sensor']})", work,
		              lambda res: self.add_tile_layer(res) if 'url' in res else self.add_map_layer(res))

	def add_map_layer(self, res):
		"""Add the GeoTIFF of a map with the colour ramp of MonitorEO (percentiles 5 and 95) and zoom to it."""
		layer = QgsRasterLayer(res['file'], res['name'])
		if not layer.isValid():
			raise RuntimeError(f"QGIS no ha podido abrir {res['file']}")
		if res['min'] is None:
			self.message(f"{res['name']}: sin valores en la región (sin imágenes, o todo filtrado)", 'Warning', 10)
		else:
			pseudocolor(layer, res['min'], res['max'], res['palette'])
		bands = ', '.join(res.get('bands') or [])
		layer.setAbstract(f"MonitorEO: {res['name']} {res['unit']}, píxeles de {res['resolution']:g} m"
		                  + (f", {res['images']} imágenes" if res.get('images') is not None else '')
		                  + (f", bandas {bands}" if bands else '') + f". GeoTIFF temporal: {res['file']}")
		QgsProject.instance().addMapLayer(layer)
		self.zoom_to(layer.extent(), layer.crs())
		native = res['resolution'] <= res['native_resolution']
		self.message(f"Capa añadida: {res['name']}, píxeles de {res['resolution']:g} m"
		             + ('' if native else ' (región grande: píxeles mayores que los de los datos; para la resolución '
		                                 'completa, exporta el mapa a Google Drive)')
		             + '. Consulta los valores con la herramienta Identificar', 'Success', 10)

	def zoom_to(self, rect, crs):
		canvas = self.iface.mapCanvas()
		tr = QgsCoordinateTransform(crs, canvas.mapSettings().destinationCrs(), QgsProject.instance())
		r = tr.transformBoundingBox(rect)
		r.scale(1.05)
		canvas.setExtent(r)
		canvas.refresh()

	def add_tile_layer(self, res):
		uri = QgsDataSourceUri()
		uri.setParam('type', 'xyz')
		uri.setParam('url', res['url'])
		uri.setParam('zmin', '0')
		uri.setParam('zmax', '20')
		layer = QgsRasterLayer(bytes(uri.encodedUri()).decode(), res['name'], 'wms')
		if not layer.isValid():
			raise RuntimeError('QGIS no ha podido abrir las teselas de Earth Engine')
		layer.setAbstract(f"MonitorEO: {res['name']} {res['unit']}. Rampa de color de {res['min']:.4g} a {res['max']:.4g}: "
		                  f"{', '.join('#' + c for c in res['palette'])}. Teselas de Earth Engine válidas unas horas.")
		QgsProject.instance().addMapLayer(layer)
		self.zoom_to(QgsRectangle(*res['bounds']), QgsCoordinateReferenceSystem('EPSG:4326'))
		self.message(f"Capa de teselas añadida: {res['name']} (de {res['min']:.4g} a {res['max']:.4g} {res['unit']}; "
		             f"sin valores consultables: no se pudo descargar el GeoTIFF: {res.get('error')})", 'Warning', 15)

	def run_export_image(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		res = self.resolution.value() or None
		folder = self.folder.text().strip() or 'MonitorEO'
		metric, temporal, inter = self.map_metric.currentData(), self.temporal.currentData(), self.interannual.currentData()
		self.run_task(f"Exportar el mapa de {var['variable']}",
		              lambda: services.export_image(region, metric=metric, temporal=temporal, interannual=inter,
		                                            resolution=res, folder=folder, **var), self.follow_export)

	def run_export_series(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		folder = self.folder.text().strip() or 'MonitorEO'
		step, metric, stat = self.step.currentData(), self.ts_metric.currentData(), self.stat.currentData()
		self.run_task(f"Exportar la serie de {var['variable']}",
		              lambda: services.time_series_to_drive(region, step=step, metric=metric, stat=stat, folder=folder,
		                                                    **var), self.follow_export)

	# Exports ----------------------------------------------------------------------------------------------------

	def follow_export(self, res):
		res['state'] = 'PENDING'
		self.exports.append(res)
		self.show_exports()
		self.message(f"Exportando {res['file']} a Google Drive/{res['folder']}", 'Info')
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

		task = QgsTask.fromFunction('MonitorEO: estado de las exportaciones', lambda t: work(),
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
			self.message(f"{e['file']} está en Google Drive/{e['folder']}", 'Success', 10)
			return
		path = tifs[0]
		if len(tifs) > 1:
			from osgeo import gdal
			path = os.path.join(tempfile.mkdtemp(prefix='monitoreo_'), os.path.splitext(e['file'])[0] + '.vrt')
			gdal.BuildVRT(path, tifs)
		layer = QgsRasterLayer(path, os.path.splitext(e['file'])[0])
		if layer.isValid():
			QgsProject.instance().addMapLayer(layer)
			self.message(f"{e['file']} añadido desde Google Drive ({path})", 'Success', 10)
