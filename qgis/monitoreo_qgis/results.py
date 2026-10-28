"""Window of a time series: chart, table and buttons to save the CSV and the chart. The chart is the PNG of
monitoreo (matplotlib), made in the main thread, or, when QGIS has no matplotlib, one drawn with Qt."""

import datetime as dt
import math
import shutil

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from qgis.PyQt.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                                 QTableWidgetItem, QVBoxLayout, QWidget)

COLUMNS = [('region', 'Región'), ('date', 'Fecha'), ('value', 'Valor'), ('n_pixels', 'Píxeles'), ('n_images', 'Imágenes')]
COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']


def chart_png(res, path):
	"""PNG of the chart of the time series RES made by monitoreo with matplotlib, or None without matplotlib (or if it
	fails): then the dialog draws it with Qt. Call it from the main thread."""
	try:
		from monitoreo import charts
		charts.time_series_png(res['rows'], path, title=res['title'], ylabel=res['unit'] or None)
		return path
	except Exception:
		return None


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
			p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Sin valores')
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

	def __init__(self, res, parent=None):
		super().__init__(parent)
		self.res = res
		self.setWindowTitle(f"MonitorEO: {res['title']}")
		self.resize(900, 720)
		lay = QVBoxLayout(self)
		info = QLabel(f"{res['title']} · {res['unit']} · píxeles de {res['scale']:g} m · {len(res['rows'])} valores")
		info.setWordWrap(True)
		lay.addWidget(info)
		self.chart = None
		if res.get('chart'):
			label = QLabel()
			label.setPixmap(QPixmap(res['chart']).scaledToWidth(860, Qt.TransformationMode.SmoothTransformation))
			lay.addWidget(label)
		else:
			self.chart = ChartWidget(res['rows'], res['title'], res['unit'])
			lay.addWidget(self.chart, 1)
		table = QTableWidget(len(res['rows']), len(COLUMNS))
		table.setHorizontalHeaderLabels([c[1] for c in COLUMNS])
		for i, r in enumerate(res['rows']):
			for j, (key, _) in enumerate(COLUMNS):
				v = r.get(key)
				table.setItem(i, j, QTableWidgetItem('' if v is None else (f'{v:.6g}' if isinstance(v, float) else str(v))))
		table.resizeColumnsToContents()
		lay.addWidget(table, 1)
		row = QHBoxLayout()
		row.addStretch()
		if res.get('csv'):
			b = QPushButton('Guardar CSV…')
			b.clicked.connect(lambda: self.save(res['csv'], 'CSV (*.csv)'))
			row.addWidget(b)
		b = QPushButton('Guardar gráfica…')
		b.clicked.connect(self.save_chart)
		row.addWidget(b)
		b = QPushButton('Cerrar')
		b.clicked.connect(self.close)
		row.addWidget(b)
		lay.addLayout(row)

	def save(self, src, filt):
		path, _ = QFileDialog.getSaveFileName(self, 'Guardar', src.replace('\\', '/').rsplit('/', 1)[-1], filt)
		if path:
			shutil.copyfile(src, path)

	def save_chart(self):
		if self.res.get('chart'):
			self.save(self.res['chart'], 'PNG (*.png)')
			return
		path, _ = QFileDialog.getSaveFileName(self, 'Guardar', 'serie.png', 'PNG (*.png)')
		if path:
			self.chart.grab().save(path, 'PNG')
