"""Windows of the results: chart, table and buttons to save the CSV and the chart. The chart of a time series is the
PNG of monitoreo (matplotlib), made in the main thread, or, when QGIS has no matplotlib, one drawn with Qt; those of
the trends and of the comparison of periods are only the PNG (without matplotlib, the window has only the table).
Those of a series and of trends add to the map that of its whole period or of each of its dates or parts of the year
(of a series, also the true colour of its images, under it or alone). That of a burn severity has the hectares of
each class of the USGS (dNBR) or of Miller & Thode 2007 (RdNBR, and under them its statistics), with its colour, or the
statistics of the RBR. The results of the data of Earth Engine outside the catalog (given by their ID) are those of a
variable, named by their ID and band, with the unit given (if any) and without true colour. Each window ends with the
references of its result (monitoreo.references), with the links of their DOIs."""

import datetime as dt
import math
import os
import shutil

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton,
                                 QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

COLUMNS = [('region', 'Region'), ('date', 'Date'), ('value', 'Value'), ('n_pixels', 'Pixels'), ('n_images', 'Images')]
COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
TREND_COLUMNS = [('region', 'Region'), ('label', 'Part of the year'), ('n', 'Years'), ('tau', "Kendall's τ"),
                 ('z', 'Z'), ('p_value', 'p-value'), ('significant', 'Significant'),
                 ('slope', "Sen's slope (per year)"), ('intercept', 'Initial value (Sen)'), ('first_year', 'First year'),
                 ('last_year', 'Last year')]
COMPARISON_COLUMNS = [('region', 'Region'), ('label', 'Part of the year'), ('reference', 'Reference period'),
                      ('other', 'Other period'), ('difference', 'Difference'),
                      ('n_reference', 'Years of the reference'), ('n_other', 'Years of the other')]
BURN_COLUMNS = [('region', 'Region'), ('label', 'Class (USGS)'), ('dnbr_min', 'dNBR from'), ('dnbr_max', 'dNBR to'),
                ('ha', 'Hectares')]
RBR_COLUMNS = [('region', 'Region'), ('mean', 'Mean'), ('median', 'Median'), ('std', 'Standard deviation'),
               ('cv', 'Coefficient of variation (%)'), ('p10', 'Percentile 10'), ('p90', 'Percentile 90'),
               ('min', 'Minimum'), ('max', 'Maximum'), ('ha', 'Hectares with values')]
# the RdNBR: the hectares of the classes of Miller & Thode 2007 and, under them, its statistics (those of the RBR)
RDNBR_COLUMNS = [('region', 'Region'), ('label', 'Class (Miller & Thode 2007)'), ('rdnbr_min', 'RdNBR from'),
                 ('rdnbr_max', 'RdNBR to'), ('ha', 'Hectares')]
# the layers of a map: that of the variable, its true colour (services.download_rgb) or both (the true colour under it)
MAP_KINDS = [('Index', 'index'), ('True colour (RGB)', 'rgb'), ('Both', 'both')]
KINDS_TIP = ('Index: the map of the variable. True colour (RGB): the red, green and blue surface reflectance of the '
             'same images (sensor, dates, pixel filters and metric) and of the same pixels as the index, the three '
             'bands stretched together between their percentiles 2 and 98. Both: the true colour, and the index on top '
             'of it')


def unit_label(res, per_year=False):
	"""The unit of the values of RES for the text of its window ('[NDVI]', 'mm'; with PER_YEAR, that of a trend):
	'unit not given' for the data of Earth Engine outside the catalog computed without one."""
	unit = res.get('unit') or ''
	if not unit:
		return 'unit not given'
	return f'{unit} per year' if per_year else unit


def ylabel(res):
	"""Title of the y axis of the charts of RES: the axis title of the catalog with the unit (e.g. 'Snow Cover
	Frequency (SCF) [%]'), or the unit (None for the data of Earth Engine outside the catalog without one)."""
	return res.get('ylabel') or res.get('unit') or None


def chart_png(res, path):
	"""PNG of the chart of the time series RES made by monitoreo with matplotlib, or None without matplotlib (or if it
	fails): then the dialog draws it with Qt. Call it from the main thread."""
	try:
		from monitoreo import charts
		charts.time_series_png(res['rows'], path, title=res['title'], ylabel=ylabel(res))
		return path
	except Exception:
		return None


def trends_png(res, path):
	"""PNG of the yearly values and Sen lines of the trends RES (or None). Call it from the main thread."""
	try:
		from monitoreo import charts
		charts.trends_png(res['yearly'], res['rows'], path, title=res['title'], ylabel=ylabel(res))
		return path
	except Exception:
		return None


def comparison_png(res, step, path):
	"""PNG of the comparison of periods RES by part of the year (or None). Call it from the main thread."""
	try:
		from monitoreo import charts
		labels = {r['part']: (r['key'] if step == '16-day' else r['label'][:3]) for r in res['profile']}
		charts.comparison_png(res['profile'], labels, path, title=res['title'], ylabel=ylabel(res), names=res['names'])
		return path
	except Exception:
		return None


def map_row(res, add_map):
	"""Row of the window of the series or trends RES with its maps (res['maps']: that of its whole period and those of
	each of its dates or parts of the year) and the button that adds the chosen one (ADD_MAP(res, map, significant,
	kind)); in a series whose images have a true colour (res['rgb'], see services.has_rgb), also the list Layer: its
	index, its true colour or both (KIND, see MAP_KINDS). None if it has no maps."""
	if add_map is None or not res.get('maps'):
		return None
	trends = res.get('kind') == 'trends'
	row = QHBoxLayout()
	row.addWidget(QLabel('Map of'))
	choice = QComboBox()
	choice.setObjectName('map_choice')
	for m in res['maps']:
		choice.addItem(m['label'])
	row.addWidget(choice, 1)
	significant = QCheckBox('Significant pixels only (p < 0.05)') if trends else None
	if significant:
		row.addWidget(significant)
	kind = None
	if not trends and res.get('rgb'):
		row.addWidget(QLabel('Layer'))
		kind = QComboBox()
		kind.setObjectName('map_kind')
		for label, value in MAP_KINDS:
			kind.addItem(label, value)
		kind.setToolTip(KINDS_TIP + ', with the same days in the Temporal Controller. The true colour maps of this '
		                'result are stretched as its first one, so that its dates can be compared')
		row.addWidget(kind)
	b = QPushButton('Add to the map')
	b.setToolTip(("Temporary GeoTIFF with Sen's slope, τ, Z, p-value, intercept and number of years of each pixel"
	              if trends else 'Temporary GeoTIFF with the values of each pixel'
	                             + (' (or, with Layer, its true colour)' if kind else '')
	                             + ', with its dates in the Temporal Controller of QGIS') + ' (queryable with the Identify '
	             'Features tool), in the group of this result and with the colors of its first map, so that they can '
	             'be compared')
	b.clicked.connect(lambda: add_map(res, res['maps'][choice.currentIndex()],
	                                  bool(significant and significant.isChecked()),
	                                  kind.currentData() if kind else 'index'))
	row.addWidget(b)
	return row


def _cell(v):
	if v is None:
		return ''
	if isinstance(v, bool):
		return 'yes' if v else 'no'
	return f'{v:.6g}' if isinstance(v, float) else str(v)


def save_file(src, path, res):
	"""Copy the file SRC of the result RES to PATH and, if it is its CSV, its GeoTIFF or its perimeter (the polygons
	of the burned area), its README next to it (<name>.README.txt), which explains its columns, bands or fields and how
	to cite it."""
	shutil.copyfile(src, path)
	readme = res.get('readme')
	if src in (res.get('csv'), res.get('file'), res.get('perimeter')) and isinstance(readme, str) and \
			os.path.exists(readme):
		shutil.copyfile(readme, os.path.splitext(path)[0] + '.README.txt')


def references_box(res):
	"""A box with the references and credits of the result RES (with the links of their DOIs), or None."""
	from .helptexts import cite_html
	text = cite_html(res.get('references'), res.get('credits') or (), 'References (cite them with this result)')
	if not text:
		return None
	box = QTextBrowser()
	box.setOpenExternalLinks(True)
	box.setHtml(text)
	box.setMaximumHeight(120)
	return box


def burn_text(res):
	"""What the window of the burn severity RES says over its table: the burned area of each region (dNBR), how the
	RBR is computed, or how the RdNBR is computed and the changed area of each region (RdNBR)."""
	return _burn_text(res) + perimeter_text(res)


def perimeter_text(res):
	"""The perimeter of the burned area of the burn severity RES, if it has one: its hectares in each region."""
	ha = res.get('perimeter_ha')
	if not res.get('perimeter') or not isinstance(ha, dict):
		return ''
	areas = ', '.join(f'{region}: {v:,.1f} ha' for region, v in ha.items()) if len(ha) > 1 else \
		f'{next(iter(ha.values())):,.1f} ha' if ha else '0 ha'
	return (f" · perimeter of the burned area ({res.get('index') or 'dNBR'} ≥ {res.get('burned_min', 0):g}, without "
	        f"patches nor islands of less than {res.get('min_ha', 0):g} ha): {areas}")


def _burn_text(res):
	from monitoreo import fire
	if res.get('index') == 'RBR':
		return (' · RBR = dNBR / (NBR before + 1.001), without phenological correction and without the factor 1000; '
		        'from red (burned) to green (regrowth)')
	burned = res.get('burned_ha') or {}
	areas = ', '.join(f'{region}: {ha:,.1f} ha' for region, ha in burned.items()) if len(burned) > 1 else \
		f'{next(iter(burned.values())):,.1f} ha' if burned else ''
	if res.get('index') == 'RdNBR':
		return (' · RdNBR = dNBR / sqrt(|NBR before|), |NBR before| at least 0.001, without the offset and without the '
		        'factor 1000 of Miller & Thode 2007; classes of their Table 4'
		        + (f' · changed area (RdNBR ≥ {fire.RDNBR_BURNED:g}): {areas}' if areas else ''))
	return f' · burned area (dNBR ≥ {fire.BURNED:g}): {areas}' if areas else ''


def table_of(rows, columns, colours=None):
	"""A table of the rows ROWS of a result with the COLUMNS [(key, title)] and, in those of a burn severity with
	classes, the colour of its class (COLOURS: {class: '#rrggbb'}) beside the label of each row."""
	colours = colours or {}
	table = QTableWidget(len(rows), len(columns))
	table.setHorizontalHeaderLabels([c[1] for c in columns])
	for i, r in enumerate(rows):
		for j, (key, _) in enumerate(columns):
			item = QTableWidgetItem(_cell(r.get(key)))
			if key == 'label' and r.get('class') in colours:
				item.setIcon(swatch(colours[r['class']]))
			table.setItem(i, j, item)
	table.resizeColumnsToContents()
	return table


def swatch(color):
	"""A small square of COLOR (#rrggbb), the icon of a class in a table."""
	pixmap = QPixmap(12, 12)
	pixmap.fill(QColor(color))
	return QIcon(pixmap)


class ResultDialog(QDialog):
	"""Window of the trends, of the comparison of periods or of the burn severity: chart (PNG), table and buttons to
	save them."""

	def __init__(self, res, parent=None, add_map=None):
		super().__init__(parent)
		self.res = res
		kind = res.get('kind')
		trends = kind == 'trends'
		if kind == 'burn':
			index = res.get('index')
			rbr = index == 'RBR'
			rows, columns = (res['stats'], RBR_COLUMNS) if rbr else \
				(res['classes'], RDNBR_COLUMNS if index == 'RdNBR' else BURN_COLUMNS)
		else:
			rows = res['rows'] if trends else res['profile']
			columns = TREND_COLUMNS if trends else COMPARISON_COLUMNS
		self.setWindowTitle(f"MonitorEO: {res['label']}")
		self.resize(980, 760)
		lay = QVBoxLayout(self)
		if kind == 'burn':
			text = f"{res['title']} · pixels of {res['scale']:g} m" + burn_text(res)
		else:
			text = (f"{res['title']} · {unit_label(res, trends)} · pixels of {res['scale']:g} m"
			        + (' · significant: p < 0.05 (Mann-Kendall)' if trends else
			           ' · difference = other period - reference'))
		info = QLabel(text)
		info.setWordWrap(True)
		lay.addWidget(info)
		if res.get('chart'):
			label = QLabel()
			label.setPixmap(QPixmap(res['chart']).scaledToWidth(940, Qt.TransformationMode.SmoothTransformation))
			lay.addWidget(label)
		colours = {}
		if kind == 'burn' and not rbr:  # the colour of each class, as in its layer (USGS or Miller & Thode 2007)
			from monitoreo import fire
			colours = {c['value']: c['color'] for c in fire.legend('RdNBR' if index == 'RdNBR' else 'dNBR')}
		lay.addWidget(table_of(rows, columns, colours), 1)
		if kind == 'burn' and index == 'RdNBR' and res.get('stats'):  # and under them, its statistics, as the RBR
			lay.addWidget(QLabel('RdNBR over each feature of the region'))
			stats = table_of(res['stats'], RBR_COLUMNS)
			stats.setObjectName('rdnbr_stats')
			stats.setMaximumHeight(min(200, stats.horizontalHeader().sizeHint().height() + 2 * stats.frameWidth() + 2
			                           + stats.verticalHeader().defaultSectionSize() * len(res['stats'])))
			lay.addWidget(stats)
		maps = map_row(res, add_map)
		if maps:
			lay.addLayout(maps)
		refs = references_box(res)
		if refs:
			lay.addWidget(refs)
		row = QHBoxLayout()
		row.addStretch()
		for text, path, filt in (('Save CSV…', res.get('csv'), 'CSV (*.csv)'),
		                         ('Save chart…', res.get('chart'), 'PNG (*.png)'),
		                         ('Save GeoTIFF…', res.get('file'), 'GeoTIFF (*.tif)'),
		                         ('Save perimeter…', res.get('perimeter'), 'GeoPackage (*.gpkg)')):
			if path:
				b = QPushButton(text)
				b.clicked.connect(lambda checked=False, p=path, f=filt: self.save(p, f))
				row.addWidget(b)
		b = QPushButton('Close')
		b.clicked.connect(self.close)
		row.addWidget(b)
		lay.addLayout(row)

	def save(self, src, filt):
		path, _ = QFileDialog.getSaveFileName(self, 'Save', src.replace('\\', '/').rsplit('/', 1)[-1], filt)
		if path:
			save_file(src, path, self.res)


def nice_ticks(lo, hi, n=5):
	if hi <= lo:
		return [lo]
	step = 10 ** math.floor(math.log10((hi - lo) / n))
	for m in (1, 2, 2.5, 5, 10):
		if (hi - lo) / (m * step) <= n:
			step *= m
			break
	first = math.ceil(lo / step) * step
	return [first + i * step for i in range(int((hi - first) / step) + 1)]


class ChartWidget(QWidget):
	"""Line chart of the rows (a line per region), drawn with QPainter."""

	def __init__(self, rows, title='', unit='', parent=None):
		super().__init__(parent)
		self.title, self.unit = title, unit
		self.series = {}
		for r in rows:
			self.series.setdefault(r['region'], []).append((dt.date.fromisoformat(r['date']), r.get('value')))
		for v in self.series.values():
			v.sort()
		self.setMinimumHeight(320)

	def paintEvent(self, event):
		p = QPainter(self)
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		p.fillRect(self.rect(), QColor('white'))
		pts = [(d, v) for s in self.series.values() for d, v in s if v is not None]
		if not pts:
			p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'No values')
			return
		d0, d1 = min(d for d, _ in pts), max(d for d, _ in pts)
		v0, v1 = min(v for _, v in pts), max(v for _, v in pts)
		pad = (v1 - v0) * 0.05 or abs(v0) * 0.05 or 1
		v0, v1 = v0 - pad, v1 + pad
		days = max((d1 - d0).days, 1)
		left, right, top, bottom = 70, 20, 30, 45
		plot = QRectF(left, top, self.width() - left - right, self.height() - top - bottom)

		def xy(d, v):
			return QPointF(plot.left() + plot.width() * (d - d0).days / days,
			               plot.bottom() - plot.height() * (v - v0) / (v1 - v0))

		grid = QPen(QColor('#dddddd'))
		p.setPen(QColor('black'))
		p.drawText(QRectF(0, 4, self.width(), 22), Qt.AlignmentFlag.AlignHCenter, self.title)
		for t in nice_ticks(v0, v1):
			y = xy(d0, t).y()
			p.setPen(grid)
			p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
			p.setPen(QColor('black'))
			p.drawText(QRectF(0, y - 8, left - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f'{t:.4g}')
		years = range(d0.year, d1.year + 1)
		marks = [dt.date(y, m, 1) for y in years for m in ((1,) if len(years) > 3 else (1, 4, 7, 10))]
		for d in marks:
			if d0 <= d <= d1:
				x = xy(d, v0).x()
				p.setPen(grid)
				p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
				p.setPen(QColor('black'))
				p.drawText(QRectF(x - 40, plot.bottom() + 4, 80, 16), Qt.AlignmentFlag.AlignHCenter, d.strftime('%Y-%m'))
		p.drawRect(plot)
		if self.unit:
			p.save()
			p.translate(14, plot.center().y())
			p.rotate(-90)
			p.drawText(QRectF(-100, -8, 200, 16), Qt.AlignmentFlag.AlignCenter, self.unit)
			p.restore()
		for i, (name, s) in enumerate(self.series.items()):
			color = QColor(COLORS[i % len(COLORS)])
			p.setPen(QPen(color, 1.8))
			path, drawing = QPainterPath(), False
			for d, v in s:
				if v is None:
					drawing = False
					continue
				pt = xy(d, v)
				path.lineTo(pt) if drawing else path.moveTo(pt)
				drawing = True
				p.setBrush(color)
				p.drawEllipse(pt, 2.5, 2.5)
			p.setBrush(Qt.BrushStyle.NoBrush)
			p.drawPath(path)
			if len(self.series) > 1:
				p.drawText(QPointF(plot.left() + 8, plot.top() + 16 + 15 * i), name)


class SeriesDialog(QDialog):

	def __init__(self, res, parent=None, add_map=None):
		super().__init__(parent)
		self.res = res
		self.setWindowTitle(f"MonitorEO: {res['title']}")
		self.resize(900, 720)
		lay = QVBoxLayout(self)
		info = QLabel(f"{res['title']} · {unit_label(res)} · pixels of {res['scale']:g} m · {len(res['rows']):,} values")
		info.setWordWrap(True)
		lay.addWidget(info)
		self.chart = None
		if res.get('chart'):
			label = QLabel()
			label.setPixmap(QPixmap(res['chart']).scaledToWidth(860, Qt.TransformationMode.SmoothTransformation))
			lay.addWidget(label)
		else:
			self.chart = ChartWidget(res['rows'], res['title'], ylabel(res) or '')
			lay.addWidget(self.chart, 1)
		table = QTableWidget(len(res['rows']), len(COLUMNS))
		table.setHorizontalHeaderLabels([c[1] for c in COLUMNS])
		for i, r in enumerate(res['rows']):
			for j, (key, _) in enumerate(COLUMNS):
				v = r.get(key)
				table.setItem(i, j, QTableWidgetItem('' if v is None else (f'{v:.6g}' if isinstance(v, float) else str(v))))
		table.resizeColumnsToContents()
		lay.addWidget(table, 1)
		maps = map_row(res, add_map)
		if maps:
			lay.addLayout(maps)
		refs = references_box(res)
		if refs:
			lay.addWidget(refs)
		row = QHBoxLayout()
		row.addStretch()
		if res.get('csv'):
			b = QPushButton('Save CSV…')
			b.clicked.connect(lambda: self.save(res['csv'], 'CSV (*.csv)'))
			row.addWidget(b)
		b = QPushButton('Save chart…')
		b.clicked.connect(self.save_chart)
		row.addWidget(b)
		b = QPushButton('Close')
		b.clicked.connect(self.close)
		row.addWidget(b)
		lay.addLayout(row)

	def save(self, src, filt):
		path, _ = QFileDialog.getSaveFileName(self, 'Save', src.replace('\\', '/').rsplit('/', 1)[-1], filt)
		if path:
			save_file(src, path, self.res)

	def save_chart(self):
		if self.res.get('chart'):
			self.save(self.res['chart'], 'PNG (*.png)')
			return
		path, _ = QFileDialog.getSaveFileName(self, 'Save', 'series.png', 'PNG (*.png)')
		if path:
			self.chart.grab().save(path, 'PNG')
