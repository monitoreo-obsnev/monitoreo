"""Windows of the results: chart, table and buttons to save the CSV and the chart. The chart of a time series is the
PNG of monitoreo (matplotlib), made in the main thread, or, when QGIS has no matplotlib, one drawn with Qt; those of
the trends and of the comparison of periods are only the PNG (without matplotlib, the window has only the table).
Those of a series and of trends add to the map that of its whole period or of each of its dates or parts of the year
(of a series, also the true colour of its images, under it or alone). That of a burn severity has the hectares of
each class of the USGS (dNBR) or of Miller & Thode 2007 (RdNBR, and under them its statistics), with its colour, or the
statistics of the RBR. That of an animation (services.timelapse) plays its GIF, with the date and the images of each
frame. The results of the data of Earth Engine outside the catalog (given by their ID) are those of a
variable, named by their ID and band, with the unit given (if any) and without true colour. Each window says, under
its first line, which data its values come from («Data: ...», data_source: the Earth Engine collections and their
product level, as its chart) and the warnings of its period, in orange (days without images of its data: see
monitoreo.coverage), and ends with the references of its result (monitoreo.references), with the links of their
DOIs, and the parameters of its analysis (monitoreo.parameters), which Copy parameters and Save parameters… give as
JSON and which are saved next to its CSV, GeoTIFF, GIF or perimeter (<name>.parameters.json)."""

import datetime as dt
import json
import math
import os
import shutil

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QFontMetrics, QIcon, QMovie, QPainter, QPainterPath, QPen, QPixmap
from qgis.PyQt.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                                 QPushButton, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

COLUMNS = [('region', 'Region'), ('date', 'Date'), ('value', 'Value'), ('n_pixels', 'Pixels'), ('n_images', 'Images')]
# the seasonal profile by day of the year of one or two variables (services.time_series with doy and interannual or
# other_variable): a row per region, variable and step of the year, as the table of its report
PROFILE_COLUMNS = [('region', 'Region'), ('variable', 'Variable'), ('label', 'Step of the year'),
                   ('doy', 'Day of the year'), ('value', 'Value'), ('unit', 'Unit'), ('n_years', 'Years')]
PROFILE_COLOURS = ('#1f77b4', '#d62728')  # its left and right axes, as charts.doy_profile_png
MONTH_STARTS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]  # day of the year of the first of each month
COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
YEARS = ['#fde725', '#5ec962', '#21918c', '#3b528b', '#440154']  # the years: from the oldest (light) to the newest
TREND_COLUMNS = [('region', 'Region'), ('label', 'Part of the year'), ('n', 'Years'), ('tau', "Kendall's τ"),
                 ('z', 'Z'), ('p_value', 'p-value'), ('significant', 'Significant'),
                 ('slope', "Sen's slope (per year)"), ('intercept', 'Initial value (Sen)'), ('first_year', 'First year'),
                 ('last_year', 'Last year')]
# the columns of some trend tests (monitoreo.trends.TESTS), shown when they have values, and the names of the tests
TEST_COLUMNS = [('n_ratio', 'n/n* (Hamed-Rao)'), ('r1', 'r1 (TFPW)')]
TEST_SHORT = {'mk': 'Mann-Kendall', 'hamed-rao': 'Hamed-Rao', 'tfpw': 'TFPW'}  # monitoreo.trends.TEST_SHORT
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
AREA_COLUMNS = [('region', 'Region'), ('label', 'Class'), ('group_label', 'Biome'), ('from_label', 'From (first year)'),
                ('to_label', 'To (other year)'), ('landcover', 'Land cover'), ('value_from', 'From'),
                ('value_to', 'To'), ('ha', 'Hectares'), ('percent', '% of the area with classes')]
# the zones: the bands of a fixed layer, or the classes of a categorical layer; of a categorical variable, its majority
# class in each zone (mode_label)
ZONE_COLUMNS = [('region', 'Region'), ('zone_label', 'Zone'), ('p25', 'Percentile 25'), ('p50', 'Median'),
                ('p75', 'Percentile 75'), ('mean', 'Mean'), ('mode_label', 'Majority class'), ('n_pixels', 'Pixels')]
TRANSECT_COLUMNS = [('distance_m', 'Distance (m)'), ('value', 'Value'), ('elevation', 'Elevation (m)'),
                    ('lon', 'Longitude'), ('lat', 'Latitude')]
FRAME_COLUMNS = [('frame', 'Frame'), ('label', 'Date'), ('date', 'First day'), ('images', 'Images')]
# with the colour range of each frame (services.timelapse: each frame its own, by default), if the animation has them
FRAME_RANGE_COLUMNS = [('min', 'Colours from'), ('max', 'Colours to')]
# the layers of a map: that of the variable, its true colour (services.download_rgb) or both (the true colour under it)
MAP_KINDS = [('Index', 'index'), ('True colour (RGB)', 'rgb'), ('Both', 'both')]
KINDS_TIP = ('Index: the map of the variable. True colour (RGB): the red, green and blue surface reflectance of the '
             'same images (sensor, dates, pixel filters and metric) and of the same pixels as the index, the three '
             'bands stretched together between their percentiles 2 and 98 (or those of the Colour range of the group Map, '
             'if changed). Both: the true colour, and the index on top of it')


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


def profile_of(res):
	"""The seasonal profile by day of the year of the time series RES (a list of rows of timeseries.doy_profile), or
	None if it has none (a line per year, or a series by date)."""
	return res.get('profile') if isinstance(res.get('profile'), list) else None


def other_ylabel(res):
	"""Title of the right y axis of the profile RES (that of its other variable, other_variable), or None."""
	names = res.get('variables') or []
	return res.get('other_ylabel') or ((res.get('units') or {}).get(names[1]) if len(names) > 1 else None) or None


def chart_png(res, path):
	"""PNG of the chart of the time series RES made by monitoreo with matplotlib (a line per year over the days of the
	year, or its seasonal profile with a y axis for each variable; the snow cover days with a bar per step, RES['bars']),
	or None without matplotlib (or if it fails): then the dialog draws it with Qt. Call it from the main thread."""
	try:
		from monitoreo import charts
		source = res.get('data_source')  # the line «Data: ...» under the chart
		if profile_of(res) is not None:  # a line per variable, the other on a right axis
			charts.doy_profile_png(res['profile'], path, title=res['title'], ylabel=ylabel(res),
			                       other_ylabel=other_ylabel(res), ylim=res.get('ylim'), other_ylim=res.get('other_ylim'),
			                       source=source)
		elif bool(res['rows']) and 'doy' in res['rows'][0]:  # a line per year over the days of the year
			charts.doy_png(res['rows'], path, title=res['title'], ylabel=ylabel(res), ylim=res.get('ylim'),
			               source=source)
		else:
			charts.time_series_png(res['rows'], path, title=res['title'], ylabel=ylabel(res), source=source,
			                       bars=bool(res.get('bars')))
		return path
	except Exception:
		return None


def series_text(res):
	"""What the window of the time series RES says over its chart: its title, unit, pixel size and number of values; of
	a seasonal profile, those of each variable, the range of its axis, and its steps of the year."""
	profile = profile_of(res)
	if profile is None:
		return f"{res['title']} · {unit_label(res)} · pixels of {res['scale']:g} m · {len(res['rows']):,} values"
	names = res.get('variables') or list(dict.fromkeys(r['variable'] for r in profile))
	units, scales = res.get('units') or {}, res.get('scales') or {}
	parts = [res['title']]
	for k, (name, lim) in enumerate(zip(names, (res.get('ylim'), res.get('other_ylim')))):
		axis = ('left axis: ' if k == 0 else 'right axis: ') if len(names) > 1 else ''
		scale = scales.get(name)
		parts.append(f"{axis}{name}, {units.get(name) or 'unit not given'}"
		             + (f', pixels of {scale:g} m' if isinstance(scale, (int, float)) else '')
		             + (f', y from {lim[0]:g} to {lim[1]:g}' if lim else ''))
	parts.append(f"{res.get('interannual') or 'median'} of {len(res['rows']):,} values of each year in "
	             f"{len(profile):,} steps of the year")
	return ' · '.join(parts)


def trends_png(res, path):
	"""PNG of the yearly values and Sen lines of the trends RES (or None). Call it from the main thread."""
	try:
		from monitoreo import charts
		charts.trends_png(res['yearly'], res['rows'], path, title=res['title'], ylabel=ylabel(res),
		                  source=res.get('data_source'))
		return path
	except Exception:
		return None


def comparison_png(res, step, path):
	"""PNG of the comparison of periods RES by part of the year (or None). Call it from the main thread."""
	try:
		from monitoreo import charts
		labels = {r['part']: (r['key'] if step == '16-day' else r['label'][:3]) for r in res['profile']}
		charts.comparison_png(res['profile'], labels, path, title=res['title'], ylabel=ylabel(res), names=res['names'],
		                      source=res.get('data_source'))
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
		kind.setToolTip(KINDS_TIP + ', with the same days in the Temporal Controller. With Same colours in every map '
		                'of a series or trends (group Map), the true colour maps of this result are stretched as its '
		                'first one, so that its dates can be compared')
		row.addWidget(kind)
	b = QPushButton('Add to the map')
	b.setToolTip(("Temporary GeoTIFF with Sen's slope, τ, Z, p-value, intercept and number of years of each pixel"
	              if trends else 'Temporary GeoTIFF with the values of each pixel'
	                             + (' (or, with Layer, its true colour)' if kind else '')
	                             + ', with its dates in the Temporal Controller of QGIS') + ' (queryable with the Identify '
	             'Features tool), in the group of this result, each map with its own colours (the Colour range of the group '
	             + ('Trends' if trends else 'Map') + ': by default its percentiles 1 and 99) or, with Same colours in every '
	             'map of a series or trends (group Map), those of its first map, so that they can be compared')
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


def parameters_text(p):
	"""The parameters P of an analysis (see monitoreo.parameters) as the JSON text of their files."""
	return json.dumps(p, ensure_ascii=False, indent=2)


def result_parameters(res):
	"""The parameters of the analysis of the result RES (see monitoreo.parameters): those the panel computed it with
	(res['call']) or else those that monitoreo wrote next to its files (res['parameters'], the path of their JSON);
	None if it has neither."""
	if isinstance(res.get('call'), dict):
		return res['call']
	path = res.get('parameters')
	if isinstance(path, str) and os.path.exists(path):
		from monitoreo import parameters
		try:
			return parameters.read(path)
		except (OSError, ValueError):
			return None
	return None


def write_parameters(p, path):
	"""Write the parameters P of an analysis to the JSON file PATH. Returns PATH."""
	with open(path, 'w', encoding='utf-8') as f:
		f.write(parameters_text(p) + '\n')
	return path


def save_file(src, path, res):
	"""Copy the file SRC of the result RES to PATH and, if it is its CSV, its GeoTIFF, its GIF or its perimeter (the
	polygons of the burned area), its README next to it (<name>.README.txt), which explains its columns, bands or
	fields and how to cite it, and the parameters of its analysis (<name>.parameters.json), to repeat it in any tool."""
	shutil.copyfile(src, path)
	if src not in (res.get('csv'), res.get('file'), res.get('gif'), res.get('perimeter')):
		return
	readme = res.get('readme')
	if isinstance(readme, str) and os.path.exists(readme):
		shutil.copyfile(readme, os.path.splitext(path)[0] + '.README.txt')
	p = result_parameters(res)
	if p:
		write_parameters(p, os.path.splitext(path)[0] + '.parameters.json')


def value_text(name, value, limit=240):
	"""The parameter NAME of value VALUE in a line: its JSON; a region of GeoJSON, its features and their names; long
	values cut at LIMIT characters (Copy parameters gives them whole)."""
	fc = value.get('geojson') if name == 'region' and isinstance(value, dict) else None
	if isinstance(fc, dict):
		features = fc.get('features') if fc.get('type') == 'FeatureCollection' else [fc]
		names = [str((f.get('properties') or {}).get('name', '')) for f in features or [] if isinstance(f, dict)]
		shown = ', '.join(n for n in names[:5] if n) + ('…' if len(names) > 5 else '')
		return f"GeoJSON of {len(names)} feature{'' if len(names) == 1 else 's'}" + (f' ({shown})' if shown else '')
	text = json.dumps(value, ensure_ascii=False)
	return text if len(text) <= limit else text[:limit] + '…'


def parameters_html(p):
	"""The parameters P of an analysis (see monitoreo.parameters) as rich text: the analysis and a line per parameter,
	name: value."""
	from .helptexts import esc
	rows = ''.join(f'<li><b>{esc(k)}</b>: {esc(value_text(k, v))}</li>' for k, v in p['parameters'].items())
	return (f"<p><b>Parameters of the analysis</b> {esc(p['analysis'])} (MonitorEO {esc(p.get('monitoreo') or '?')}; "
	        'the same names in Python, R, the command line, the MCP server and the Earth Engine app)</p>'
	        f'<ul>{rows}</ul>')


def data_warnings(res):
	"""The warnings of the period of the result RES (its days without images of its data, see monitoreo.coverage):
	[texts]."""
	found = res.get('warnings') if isinstance(res, dict) else None
	return [str(w) for w in found if w] if isinstance(found, list) else []


def notes_label(res):
	"""A label with the data of the values of the result RES («Data: ...», its data_source) and the warnings of its
	period, in orange, or None if it has neither."""
	from html import escape
	parts = [f'<span style="color: #555;">Data: {escape(str(res["data_source"]))}</span>'] \
		if res.get('data_source') else []
	parts += [f'<span style="color: #b35900;">⚠ {escape(w)}</span>' for w in data_warnings(res)]
	if not parts:
		return None
	label = QLabel('<br>'.join(parts))
	label.setWordWrap(True)
	label.setTextFormat(Qt.TextFormat.RichText)
	label.setObjectName('data_notes')
	return label


def references_box(res):
	"""A box with the references and credits of the result RES (with the links of their DOIs) and the parameters of
	its analysis, or None if it has neither."""
	from .helptexts import cite_html, esc
	links = [m for m in res.get('manual') or [] if isinstance(m, dict) and m.get('url')]  # what each variable is
	text = ('<p><b>What it is (manual of MonitorEO):</b> ' + ' · '.join(
		f'<a href="{esc(m["url"])}">{esc(m["title"])}</a>' for m in links) + '</p>' if links else '') + \
		cite_html(res.get('references'), res.get('credits') or (), 'References (cite them with this result)')
	p = result_parameters(res)
	if p:
		text += parameters_html(p)
	if not text:
		return None
	box = QTextBrowser()
	box.setObjectName('details')
	box.setOpenExternalLinks(True)
	box.setHtml(text)
	box.setMaximumHeight(160)
	return box


def parameter_buttons(dialog, row, res):
	"""Add to the ROW of buttons of the window DIALOG of the result RES the buttons Copy parameters and Save
	parameters… of its analysis, if it has them."""
	p = result_parameters(res)
	if not p:
		return
	b = QPushButton('Copy parameters')
	b.setToolTip('Copy the parameters of this analysis (JSON) to repeat it in the panel (Apply parameters) or in '
	             'Python, R, the command line, the MCP server or the Earth Engine app')
	b.clicked.connect(lambda checked=False: QApplication.clipboard().setText(parameters_text(p)))
	row.addWidget(b)
	b = QPushButton('Save parameters…')
	b.setToolTip('Save the parameters of this analysis as a JSON file')
	b.clicked.connect(lambda checked=False: save_parameters(dialog, res, p))
	row.addWidget(b)


def save_parameters(dialog, res, p):
	"""Save the parameters P of the result RES to a JSON file chosen by the user (by default, beside the name of its
	files)."""
	src = next((res[k] for k in ('csv', 'file', 'gif') if isinstance(res.get(k), str)), None)
	name = os.path.splitext(os.path.basename(src))[0] if src else p['analysis']
	path, _ = QFileDialog.getSaveFileName(dialog, 'Save parameters', name + '.parameters.json', 'Parameters (*.json)')
	if path:
		write_parameters(p, path)


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
		elif kind == 'areas':  # the columns of its kind of classes (a land cover map, breaks or a trend)
			rows = res['rows']
			columns = [c for c in AREA_COLUMNS if any(c[0] in r for r in rows)]
		elif kind in ('zones', 'transect'):  # the bands of the elevation, or a profile along a line
			rows = res['rows']
			columns = [c for c in (ZONE_COLUMNS if kind == 'zones' else TRANSECT_COLUMNS) if any(c[0] in r for r in rows)]
		else:
			rows = res['rows'] if trends else res['profile']
			columns = TREND_COLUMNS + [c for c in TEST_COLUMNS if any(r.get(c[0]) is not None for r in res['rows'])] \
				if trends else COMPARISON_COLUMNS
		self.setWindowTitle(f"MonitorEO: {res['label']}")
		self.resize(980, 760)
		lay = QVBoxLayout(self)
		if kind == 'burn':
			text = f"{res['title']} · pixels of {res['scale']:g} m" + burn_text(res)
		elif kind in ('zones', 'transect'):
			text = f"{res['title']} · {unit_label(res)} · pixels of {res['scale']:g} m" + (
				f" · segments of {res['spacing']:.4g} m, elevation in m" if kind == 'transect' else '')
		elif kind == 'areas':
			text = f"{res['title']} · pixels of {res['scale']:g} m · % of the area with classes"
			for region, ha in (res.get('changed_ha') or {}).items():  # the changes of a land cover map
				text += f" · {region}: changed {ha:,.1f} ha, unchanged {res['unchanged_ha'][region]:,.1f} ha"
		else:
			text = (f"{res['title']} · {unit_label(res, trends)} · pixels of {res['scale']:g} m"
			        + (f" · significant: p < 0.05 ({TEST_SHORT.get((res.get('args') or {}).get('test') or 'mk')})"
			           if trends else
			           ' · difference = other period - reference'))
		info = QLabel(text)
		info.setWordWrap(True)
		lay.addWidget(info)
		notes = notes_label(res)
		if notes:
			lay.addWidget(notes)
		if res.get('chart'):
			label = QLabel()
			label.setPixmap(QPixmap(res['chart']).scaledToWidth(940, Qt.TransformationMode.SmoothTransformation))
			lay.addWidget(label)
		colours = {}
		if kind == 'areas':  # the colour of each class, as in its chart
			colours = {c['class']: f"#{c['colour']}" for c in res.get('classes') or [] if c.get('colour')}
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
		parameter_buttons(self, row, res)
		b = QPushButton('Close')
		b.clicked.connect(self.close)
		row.addWidget(b)
		lay.addLayout(row)

	def save(self, src, filt):
		path, _ = QFileDialog.getSaveFileName(self, 'Save', src.replace('\\', '/').rsplit('/', 1)[-1], filt)
		if path:
			save_file(src, path, self.res)


class AnimationDialog(QDialog):
	"""Window of an animation (services.timelapse): its GIF playing, the date and the images of each frame, and buttons to
	save it."""

	def __init__(self, res, parent=None, add_map=None):
		super().__init__(parent)
		self.res = res
		self.setWindowTitle(f"MonitorEO: {res['label']}")
		self.resize(760, 900)
		lay = QVBoxLayout(self)
		empty = sum(1 for f in res.get('frames') or [] if not f.get('images'))
		stretch = res.get('stretch') if isinstance(res.get('stretch'), dict) else {}
		info = QLabel(f"{res['name']} · {res['n_frames']} frames, {res['fps']:g} per second · colours from "
		              f"{res['min']:.4g} to {res['max']:.4g} {unit_label(res)}".rstrip()
		              + (f" ({stretch['text']})" if stretch.get('text') else '')
		              + (f' · {empty} frames without images (grey)' if empty else ''))
		info.setWordWrap(True)
		lay.addWidget(info)
		notes = notes_label(res)
		if notes:
			lay.addWidget(notes)
		self.picture = QLabel()
		self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
		self.movie = QMovie(res['gif'])
		self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
		self.picture.setMovie(self.movie)
		lay.addWidget(self.picture, 3)
		self.movie.start()
		rows = [dict(f, frame=i) for i, f in enumerate(res.get('frames') or [], 1)]
		ranged = any(f.get('min') is not None for f in rows)  # the colour range of each frame (not in older results)
		lay.addWidget(table_of(rows, FRAME_COLUMNS + (FRAME_RANGE_COLUMNS if ranged else [])), 1)
		refs = references_box(res)
		if refs:
			lay.addWidget(refs)
		row = QHBoxLayout()
		row.addStretch()
		for text, path, filt in (('Save GIF…', res.get('gif'), 'GIF (*.gif)'),
		                         ('Save video…', res['file'] if str(res.get('file')).lower().endswith('.mp4') else None,
		                          'MP4 (*.mp4)')):
			if path:
				b = QPushButton(text)
				b.clicked.connect(lambda checked=False, p=path, f=filt: self.save(p, f))
				row.addWidget(b)
		parameter_buttons(self, row, res)
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


def year_colour(k, n):
	"""Colour of the year K of N, from the oldest (light) to the newest (dark), as charts.doy_png (viridis reversed)."""
	x = (0.15 + 0.85 * k / max(n - 1, 1)) * (len(YEARS) - 1)
	i = min(int(x), len(YEARS) - 2)
	a, b, w = QColor(YEARS[i]), QColor(YEARS[i + 1]), x - i
	return QColor(round(a.red() + (b.red() - a.red()) * w), round(a.green() + (b.green() - a.green()) * w),
	              round(a.blue() + (b.blue() - a.blue()) * w))


def value_range(values, lim=None):
	"""(min, max) of a y axis: LIM if given, else that of VALUES with a margin of 5 % (None without values)."""
	if lim:
		return float(lim[0]), float(lim[1])
	if not values:
		return None
	v0, v1 = min(values), max(values)
	pad = (v1 - v0) * 0.05 or abs(v0) * 0.05 or 1
	return v0 - pad, v1 + pad


class ChartWidget(QWidget):
	"""Line chart of the rows (a line per region), drawn with QPainter; with the day of the year in the rows (doy), a line
	per year (and region) over the days of one year, from the oldest year (light) to the newest (dark, thicker), a dash
	for each region. With a seasonal profile (PROFILE: the rows of timeseries.doy_profile of services.time_series with
	doy and interannual or other_variable), a line per variable over the days of the year (1 to 366): the first on the
	left axis (blue, UNIT, YLIM) and the other, if any, on a right axis (red, OTHER_UNIT, OTHER_YLIM), each axis in the
	colour of its line, with a line at 0 where an axis has it, and a dash for each region, as charts.doy_profile_png.
	YLIM, OTHER_YLIM: (min, max) of each y axis (default: from the values). SOURCE: the data of the values (data_source),
	written under the chart as «Data: SOURCE», as charts.source_line. With BARS (the snow cover days: services.time_series
	gives bars), a bar per step from 0 instead of the lines, those of the regions side by side, as
	charts.time_series_png."""

	def __init__(self, rows, title='', unit='', parent=None, profile=None, other_unit='', ylim=None, other_ylim=None,
	             source='', bars=False):
		super().__init__(parent)
		self.title, self.unit, self.other_unit = title, unit, other_unit or ''
		self.source = source or ''
		self.bars = bool(bars) and not profile and not (bool(rows) and 'doy' in rows[0])
		self.ylims = [tuple(ylim) if ylim else None, tuple(other_ylim) if other_ylim else None]
		self.profile = isinstance(profile, list)
		self.doy = self.profile or (bool(rows) and 'doy' in rows[0])
		self.names = []  # of a profile, its variables: that of the left axis, and that of the right one
		self.years = sorted({r['year'] for r in rows}) if self.doy and not self.profile else []
		self.keys = {}  # with doy, the region and the year of each line; of a profile, the region and the axis
		self.series = {}
		if self.profile:  # x: the day of the year of each step of the year
			self.names = list(dict.fromkeys(r['variable'] for r in profile))[:2]
			regions = list(dict.fromkeys(r['region'] for r in profile))
			for r in profile:
				if r['variable'] not in self.names:
					continue
				key = f"{r['region']} · {r['variable']}" if len(regions) > 1 else str(r['variable'])
				self.keys[key] = (regions.index(r['region']), self.names.index(r['variable']))
				self.series.setdefault(key, []).append((int(r['doy']), r.get('value')))
			rows = []
		regions = list(dict.fromkeys(r['region'] for r in rows))
		for r in rows:
			d = dt.date.fromisoformat(r['date'])
			if self.doy:  # every year on the days of 2000 (a leap year: 366 days)
				key = f"{r['region']} {d.year}" if len(regions) > 1 else str(d.year)
				self.keys[key] = (regions.index(r['region']), r['year'])
				self.series.setdefault(key, []).append((dt.date(2000, 1, 1) + dt.timedelta(days=r['doy'] - 1),
				                                        r.get('value')))
			else:
				self.series.setdefault(r['region'], []).append((d, r.get('value')))
		for v in self.series.values():
			v.sort(key=lambda point: point[0])
		self.setMinimumHeight(320)

	def pen(self, i, name):
		"""Pen of the line I (NAME): a colour of COLORS or, with doy, that of its year (the newest thicker) and a dash for
		each region; of a profile, the colour of its axis (PROFILE_COLOURS) and a dash for each region."""
		if not self.doy:
			return QPen(QColor(COLORS[i % len(COLORS)]), 1.8)
		if self.profile:
			region, axis = self.keys[name]
			pen = QPen(QColor(PROFILE_COLOURS[axis]), 1.8)
		else:
			region, year = self.keys[name]
			k = self.years.index(year)
			pen = QPen(year_colour(k, len(self.years)), 2.2 if k == len(self.years) - 1 else 1.0)
		pen.setStyle((Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine,
		              Qt.PenStyle.DashDotLine)[region % 4])
		return pen

	def axis_range(self, axis):
		"""(min, max) of the y axis AXIS (0 left, 1 right) of a profile, or None if its variable has no values."""
		values = [v for key, s in self.series.items() if self.keys[key][1] == axis for _, v in s if v is not None]
		return value_range(values, self.ylims[axis])

	def paint_source(self, p):
		"""The line «Data: ...» at the bottom left, in small grey letters (cut with … if it is longer than the chart)."""
		if not self.source:
			return
		p.save()
		font = QFont(p.font())
		font.setPointSizeF(max(6.0, font.pointSizeF() * 0.8))
		p.setFont(font)
		p.setPen(QColor('#555555'))
		text = QFontMetrics(font).elidedText(f'Data: {self.source}', Qt.TextElideMode.ElideRight, self.width() - 12)
		p.drawText(QRectF(6, self.height() - 16, self.width() - 12, 14), Qt.AlignmentFlag.AlignLeft, text)
		p.restore()

	def paintEvent(self, event):
		p = QPainter(self)
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		p.fillRect(self.rect(), QColor('white'))
		self.paint_source(p)
		pts = [(d, v) for s in self.series.values() for d, v in s if v is not None]
		if not pts:
			p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'No values')
			return
		if self.profile:
			self.paint_profile(p)
			return
		d0, d1 = min(d for d, _ in pts), max(d for d, _ in pts)
		v0, v1 = value_range([v for _, v in pts], self.ylims[0])
		width = 0  # of the bars, in days
		if self.bars:  # from 0, and half a bar more at each end so that the first and the last are whole
			from monitoreo import charts
			width = charts.bar_width([d for s in self.series.values() for d, _ in s])
			v0, v1 = min(v0, 0), max(v1, 0)
		days = max((d1 - d0).days + width, 1)
		left, right, top, bottom = 70, 20, 30, 45
		plot = QRectF(left, top, self.width() - left - right, self.height() - top - bottom)

		def xy(d, v, shift=0.0):  # SHIFT: days after D (the bars)
			return QPointF(plot.left() + plot.width() * ((d - d0).days + width / 2 + shift) / days,
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
		marks = [dt.date(y, m, 1) for y in years for m in (range(1, 13) if self.doy else
		                                                     (1,) if len(years) > 3 else (1, 4, 7, 10))]
		for d in marks:
			if d0 <= d <= d1:
				x = xy(d, v0).x()
				p.setPen(grid)
				p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
				p.setPen(QColor('black'))
				p.drawText(QRectF(x - 40, plot.bottom() + 4, 80, 16), Qt.AlignmentFlag.AlignHCenter,
				           d.strftime('%b') if self.doy else d.strftime('%Y-%m'))
		p.drawRect(plot)
		if self.unit:
			p.save()
			p.translate(14, plot.center().y())
			p.rotate(-90)
			p.drawText(QRectF(-100, -8, 200, 16), Qt.AlignmentFlag.AlignCenter, self.unit)
			p.restore()
		n = len(self.series)
		for i, (name, s) in enumerate(self.series.items()):
			pen = self.pen(i, name)
			p.setPen(pen)
			if self.bars:  # each bar at its date, those of the regions side by side around it
				mid, half = width / n * (i - (n - 1) / 2), width / n / 2
				self.draw_bars(p, pen.color(), plot, [(xy(d, 0, mid - half), xy(d, v, mid + half))
				                                      for d, v in s if v is not None])
			else:
				self.draw_line(p, pen, plot, [(xy(d, v) if v is not None else None) for d, v in s])
			if len(self.series) > 1:
				p.drawText(QPointF(plot.left() + 8, plot.top() + 16 + 15 * i), name)

	def draw_bars(self, p, colour, plot, corners):
		"""Draw a bar filled with COLOUR between each pair of opposite CORNERS (QPointF: the bottom left at 0 and the top
		right at its value), inside PLOT."""
		p.save()
		p.setClipRect(plot)
		p.setPen(Qt.PenStyle.NoPen)
		p.setBrush(colour)
		for a, b in corners:
			p.drawRect(QRectF(a, b).normalized())
		p.restore()

	def draw_line(self, p, pen, plot, points):
		"""Draw the line of POINTS (QPointF, or None for a gap) with PEN and a dot on each point, inside PLOT."""
		p.save()
		p.setClipRect(plot)
		p.setPen(pen)
		path, drawing = QPainterPath(), False
		for pt in points:
			if pt is None:
				drawing = False
				continue
			path.lineTo(pt) if drawing else path.moveTo(pt)
			drawing = True
			p.setBrush(pen.color())
			p.drawEllipse(pt, 2.5, 2.5)
		p.setBrush(Qt.BrushStyle.NoBrush)
		p.drawPath(path)
		p.restore()

	def paint_profile(self, p):
		"""The seasonal profile: x from day 1 to 366 with the first day of each month, the left y axis (that of the first
		variable) with its grid and, with two variables, the right one, each in the colour of its line."""
		two = len(self.names) > 1
		ranges = [self.axis_range(k) for k in range(len(self.names))]
		left, right, top, bottom = 70, 70 if two else 20, 30, 45
		plot = QRectF(left, top, self.width() - left - right, self.height() - top - bottom)
		black, grid = QColor('black'), QPen(QColor('#dddddd'))

		def x_of(doy):
			return plot.left() + plot.width() * (doy - 1) / 365

		def y_of(v, axis):
			v0, v1 = ranges[axis]
			return plot.bottom() - plot.height() * (v - v0) / (v1 - v0)

		p.setPen(black)
		p.drawText(QRectF(0, 4, self.width(), 22), Qt.AlignmentFlag.AlignHCenter, self.title)
		for d, label in zip(MONTH_STARTS, ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov',
		                                   'Dec')):
			x = x_of(d)
			p.setPen(grid)
			p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
			p.setPen(black)
			p.drawText(QRectF(x - 40, plot.bottom() + 4, 80, 16), Qt.AlignmentFlag.AlignHCenter, label)
		for axis, rng in enumerate(ranges):
			if rng is None:  # a variable without values: no axis
				continue
			colour = QColor(PROFILE_COLOURS[axis]) if two else black
			for t in nice_ticks(*rng):
				y = y_of(t, axis)
				if axis == 0:
					p.setPen(grid)
					p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
					box, align = QRectF(0, y - 8, left - 6, 16), Qt.AlignmentFlag.AlignRight
				else:
					p.setPen(colour)
					p.drawLine(QPointF(plot.right(), y), QPointF(plot.right() + 4, y))
					box, align = QRectF(plot.right() + 6, y - 8, right - 6, 16), Qt.AlignmentFlag.AlignLeft
				p.setPen(colour)
				p.drawText(box, align | Qt.AlignmentFlag.AlignVCenter, f'{t:.4g}')
			# the line at 0 where the axis has it (that of the right axis, dotted, if it is not at the same height)
			if rng[0] < 0 < rng[1] and (axis == 0 or ranges[0] is None or y_of(0, 1) != y_of(0, 0)):
				zero = QPen(QColor('#888888') if axis == 0 else colour, 0.8)
				zero.setStyle(Qt.PenStyle.SolidLine if axis == 0 else Qt.PenStyle.DotLine)
				p.setPen(zero)
				p.drawLine(QPointF(plot.left(), y_of(0, axis)), QPointF(plot.right(), y_of(0, axis)))
			unit = (self.unit, self.other_unit)[axis]
			if unit:
				p.save()
				p.setPen(colour)
				p.translate(14 if axis == 0 else self.width() - 14, plot.center().y())
				p.rotate(-90)  # both read from the bottom up, as in charts.doy_profile_png
				p.drawText(QRectF(-150, -8, 300, 16), Qt.AlignmentFlag.AlignCenter, unit)
				p.restore()
		p.setPen(black)
		p.drawRect(plot)
		lines = []
		for i, (name, s) in enumerate(self.series.items()):
			axis = self.keys[name][1]
			if ranges[axis] is not None:
				pen = self.pen(i, name)
				points = [QPointF(x_of(d), y_of(v, axis)) if v is not None else None for d, v in s]
				self.draw_line(p, pen, plot, points)
				lines.append((name, pen.color(), points))
		self.draw_legend(p, plot, lines)

	def draw_legend(self, p, plot, lines):
		"""The legend of LINES ([(name, colour, points)]): each name in the colour of its line, on a white box in the
		corner of PLOT that its lines cross the least (as the legend of matplotlib with loc='best')."""
		metrics = p.fontMetrics()
		width = max(metrics.horizontalAdvance(name) for name, _, _ in lines) + 12
		height = 15 * len(lines) + 8
		corners = [QRectF(x, y, width, height) for y in (plot.top() + 4, plot.bottom() - 4 - height)
		           for x in (plot.left() + 4, plot.right() - 4 - width)]
		samples = []  # the points of the lines, and 10 between each two of them
		for _, _, points in lines:
			for a, b in zip(points, points[1:]):
				if a is not None and b is not None:
					samples += [a + (b - a) * (k / 10) for k in range(10)]
			samples += [pt for pt in points[-1:] if pt is not None]
		box = min(corners, key=lambda r: sum(1 for pt in samples if r.contains(pt)))  # the first one, if tied
		p.save()
		p.setPen(QColor('#cccccc'))
		p.setBrush(QColor(255, 255, 255, 220))
		p.drawRect(box)
		for i, (name, colour, _) in enumerate(lines):
			p.setPen(colour)
			p.drawText(QPointF(box.left() + 6, box.top() + 4 + metrics.ascent() + 15 * i), name)
		p.restore()


class SeriesDialog(QDialog):

	def __init__(self, res, parent=None, add_map=None):
		super().__init__(parent)
		self.res = res
		self.setWindowTitle(f"MonitorEO: {res['title']}")
		self.resize(900, 720)
		lay = QVBoxLayout(self)
		info = QLabel(series_text(res))
		info.setWordWrap(True)
		lay.addWidget(info)
		notes = notes_label(res)
		if notes:
			lay.addWidget(notes)
		profile = profile_of(res)  # the seasonal profile by day of the year, a y axis for each variable
		self.chart = None
		if res.get('chart'):
			label = QLabel()
			label.setPixmap(QPixmap(res['chart']).scaledToWidth(860, Qt.TransformationMode.SmoothTransformation))
			lay.addWidget(label)
		else:
			self.chart = ChartWidget(res['rows'], res['title'], ylabel(res) or '', profile=profile,
			                         other_unit=other_ylabel(res) or '', ylim=res.get('ylim'),
			                         other_ylim=res.get('other_ylim'), source=res.get('data_source') or '',
			                         bars=res.get('bars'))
			lay.addWidget(self.chart, 1)
		if profile is not None:  # the table of the profile (what the chart and the CSV have), with the unit of each row
			units = res.get('units') or {}
			table = table_of([dict(r, unit=units.get(r['variable']) or 'unit not given') for r in profile],
			                 PROFILE_COLUMNS)
		else:
			# with the minimum coverage (min_coverage), also the coverage of each step
			columns = COLUMNS + ([('coverage', 'Coverage')] if any('coverage' in r for r in res['rows']) else [])
			table = QTableWidget(len(res['rows']), len(columns))
			table.setHorizontalHeaderLabels([c[1] for c in columns])
			for i, r in enumerate(res['rows']):
				for j, (key, _) in enumerate(columns):
					v = r.get(key)
					table.setItem(i, j, QTableWidgetItem('' if v is None else
					                                     (f'{v:.6g}' if isinstance(v, float) else str(v))))
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
		parameter_buttons(self, row, res)
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
