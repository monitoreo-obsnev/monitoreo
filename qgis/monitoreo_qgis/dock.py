"""MonitorEO panel: region, variable, period and pixel filters, and the buttons of the time series, the map layer
and the exports to Google Drive. The work runs in QGIS tasks (QgsTask), so QGIS keeps responding; every
computation is a function of monitoreo.services, the same as in the MCP server and the R package."""

import json
import os
import tempfile

from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsDataSourceUri,
                       QgsMapLayerProxyModel, QgsProject, QgsRasterLayer, QgsSettings, QgsTask)
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox
from qgis.PyQt.QtCore import QDate, Qt, QTimer
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDockWidget, QDoubleSpinBox, QFormLayout,
                                 QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
                                 QWidget)

from . import deps

deps.setup_path()
from monitoreo import services  # noqa: E402

SETTINGS = 'MonitorEO/'
STEPS = [('Mensual', 'monthly'), ('Anual', 'annual'), ('16 días', '16-day'), ('Diario (días con imágenes)', 'daily')]
METRICS = [('Media', 'mean'), ('Mediana', 'median'), ('Mínimo', 'min'), ('Máximo', 'max'), ('Percentil 5', 'p5'),
           ('Percentil 10', 'p10'), ('Percentil 90', 'p90'), ('Percentil 95', 'p95')]
STATS = [('Media', 'mean'), ('Mediana', 'median'), ('Mínimo', 'min'), ('Máximo', 'max'), ('Desviación típica', 'std')]
TEMPORAL = [('Todo el periodo', 'period'), ('Cada año y entre años', 'annual'), ('Cada mes y entre años', 'monthly')]
REGIONS = [('Capa (entidades seleccionadas o todas)', 'layer'), ('Extensión del mapa', 'extent'),
           ('Área protegida (WDPA)', 'wdpa'), ('Ecorregión del centro del mapa', 'ecoregion')]
POLL_MS = 30000
MAX_VERTICES = 20000


def level(name):
	"""Qgis message level NAME (Info, Warning, Critical, Success) in QGIS 3 and 4."""
	enum = getattr(Qgis, 'MessageLevel', None)
	return getattr(enum, name) if enum is not None and hasattr(enum, name) else getattr(Qgis, name)


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
		# the layer box can pick a new layer by itself without layerChanged (QGIS 4): follow the project too
		QgsProject.instance().layersAdded.connect(lambda layers: self.sync_fields())
		QgsProject.instance().layersRemoved.connect(lambda ids: self.sync_fields())
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
		b.setToolTip('Capa de teselas de Earth Engine: se calcula al verla, sin descargar nada')
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

	def stop(self):
		self.timer.stop()

	# Arguments --------------------------------------------------------------------------------------------------

	def save_settings(self):
		s = QgsSettings()
		s.setValue(SETTINGS + 'project', self.project.text().strip())
		s.setValue(SETTINGS + 'start', self.start.date().toString('yyyy-MM-dd'))
		s.setValue(SETTINGS + 'end', self.end.date().toString('yyyy-MM-dd'))
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

	def run_series(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		tmp = tempfile.mkdtemp(prefix='monitoreo_')
		step, metric, stat = self.step.currentData(), self.ts_metric.currentData(), self.stat.currentData()

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
			dlg = SeriesDialog(res, self.iface.mainWindow())
			dlg.show()
			self.dialogs = getattr(self, 'dialogs', []) + [dlg]

		self.run_task(f"Serie temporal de {var['variable']} ({var['sensor']})", work, done)

	def run_map(self):
		args = self.prepare()
		if not args:
			return
		region, var = args
		metric, temporal, inter = self.map_metric.currentData(), self.temporal.currentData(), self.interannual.currentData()
		self.run_task(f"Mapa de {var['variable']} ({var['sensor']})",
		              lambda: services.map_layer(region, metric=metric, temporal=temporal, interannual=inter, **var),
		              self.add_tile_layer)

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
		self.message(f"Capa añadida: {res['name']} (de {res['min']:.4g} a {res['max']:.4g} {res['unit']})", 'Success')

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
