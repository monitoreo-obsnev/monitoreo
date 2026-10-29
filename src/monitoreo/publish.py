"""Publication of the results of MonitorEO in a static web viewer, for the administrators of the site: a catalogue of
reports, each with its texts, maps (read by the browser from Cloud Optimized GeoTIFFs), charts (from the CSVs),
downloads and the call that produced each result.

A site is a folder:

    index.html, report.html, assets/   the viewer (copied from the folder viewer of this package at each publication)
    catalog.json                       the reports, made again from their report.json at each publication
    reports/<id>/report.json           a report: texts, region, variables, periods, results, files (see check_report)
    reports/<id>/maps/*.tif            its GeoTIFFs as COG (gdal_translate -of COG), with overviews
    reports/<id>/data/*.csv            its tables
    reports/<id>/files/*               the charts of the tools (PNG) and the other downloads (PDF, figures)
    reports/<id>/thumbnail.png         its image in the catalogue

Serve it with any web server that answers HTTP range requests (GitHub Pages, nginx, Apache) or, on this computer,
with serve(). The viewer only reads files: it has no accounts and no forms, so whoever can write in the site (push to
its GitHub repository, rsync to its server) is who publishes. Publishing needs GDAL (osgeo).

A report is described in Spanish, the language of the viewer, by a dictionary or a YAML file (read_specs):

    id: 2026-10-sierra-nevada            # lowercase letters, digits and hyphens (default: from the title)
    title: ¿En qué época del año ha cambiado el verdor desde 2001, y dónde?
    summary: Solo septiembre tiene una tendencia significativa del EVI ...       (the answer in short)
    answer: El EVI medio del parque sube en 9 de los 12 meses ...    (paragraphs separated by a blank line)
    method: ...
    sections: [{title: Frente a REMOTE, text: ...}]
    region: {name: Sierra Nevada, designation: Parque Nacional, wdpa_id: 389011, area_km2: 859}
    authors: [OBSNEV - Universidad de Granada]
    published: 2026-10-29                # default: today
    collection: Red de Parques Nacionales, octubre de 2026
    results:                             # the outputs of the analysis, in the order of the page
      - answer: data/sn_trend.json        # an answer of the MCP server saved with its call: {call: {tool, args}, text}
        title: Tendencia de cada mes      # default: made from the call
        caption: ...
      - tool: download_trend              # or the call and the result of a function of monitoreo.services
        args: {region: {wdpa_id: 389011}, variable: EVI, sensor: Modis, start: 2001-01-01, end: 2024-12-31}
        result: {file: trend.tif, min: -0.002, max: 0.002, palette: [...]}
        palette: [8c510a, f2efe6, 01665e] # colours of the main band of a map (default: those of the result)
      - file: ~/MonitorEO/trend_EVI_Modis_annual_None_2001-01-01_2024-12-31_20261028-233108.tif
                                          # or a file written by the MCP server: its call is read from its log
    downloads: [{path: informe.pdf, title: Informe completo (PDF)}]
    thumbnail: fig/sierra_nevada.png     # default: the first map, or the first chart of a tool
    files: mcp_out                       # folders where to look for the files of the results by their name
    license: CC-BY-4.0                   # of its data and maps: id in LICENSES (default: LICENSE) or {name, url, text}

A YAML file may have several reports in `reports:`, with its other keys as the default of each one. Relative paths
are relative to the folder of the file.
"""

import csv
import datetime as dt
import glob
import http.server
import json
import math
import os
import re
import shutil
import unicodedata

from . import __version__
from . import about as about_
from . import catalog, composite, fire, maps, trends

SCHEMA = 1
VIEWER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'viewer')
DEFAULT_SITE = os.path.expanduser(os.environ.get('MONITOREO_SITE') or '~/MonitorEO/visor')
CALLS_LOG = 'calls.jsonl'  # log of the MCP server in its folder of files: a line {time, tool, args, result} per call
SITE_TITLE = 'Resultados de MonitorEO-OBSNEV'
NODATA = -9999
THUMBNAIL_WIDTH = 480

# licences of the data and maps of a report, by their SPDX id (text: after a colon); LICENSE is that of a report that
# does not give one
LICENSES = {
	'CC-BY-4.0': {'name': 'CC BY 4.0', 'url': 'https://creativecommons.org/licenses/by/4.0/deed.es',
	              'text': 'se pueden copiar, redistribuir y adaptar para cualquier fin, también comercial, citando la '
	                      'fuente.'},
	'CC-BY-SA-4.0': {'name': 'CC BY-SA 4.0', 'url': 'https://creativecommons.org/licenses/by-sa/4.0/deed.es',
	                 'text': 'se pueden copiar, redistribuir y adaptar para cualquier fin, también comercial, citando '
	                         'la fuente y con la misma licencia.'},
	'CC0-1.0': {'name': 'CC0 1.0', 'url': 'https://creativecommons.org/publicdomain/zero/1.0/deed.es',
	            'text': 'dominio público: se pueden usar para cualquier fin sin condiciones.'},
}
LICENSE = 'CC-BY-4.0'

# type of analysis of each tool, and its name in the viewer
ANALYSES = {'time_series': 'series', 'trend_table': 'trend', 'download_trend': 'trend', 'compare_series': 'comparison',
            'download_comparison': 'comparison', 'burn_severity': 'burn_severity', 'download_image': 'map'}
ANALYSIS_NAMES = {'series': 'Serie temporal', 'trend': 'Tendencia', 'comparison': 'Comparación de periodos',
                  'burn_severity': 'Severidad de incendio', 'map': 'Mapa'}
CHARTS = {'time_series': 'series', 'trend_table': 'trends', 'compare_series': 'comparison',
          'burn_severity': 'burn_severity'}
CHART_TYPES = ('series', 'trends', 'comparison', 'burn_severity', 'table')

MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
          'noviembre', 'diciembre']
STEPS = {'daily': 'diaria', '16-day': 'de 16 días', 'monthly': 'mensual', 'annual': 'anual'}
PARTS = {'monthly': 'de cada mes', '16-day': 'de cada periodo de 16 días', 'annual': 'anual'}
SENSORS = {'Modis': 'MODIS'}

# bands of the GeoTIFFs of the tools: label and unit ({u}: the unit of the variable)
BANDS = {
	'slope': ('Pendiente de Sen', '{u}/año'),
	'tau': ('τ de Kendall', ''),
	'z': ('Z de Mann-Kendall', ''),
	'p_value': ('p-valor de Mann-Kendall', ''),
	'intercept': ('Valor de la recta de Sen el primer año', '{u}'),
	'n': ('Años con datos', 'años'),
	'difference': ('Diferencia', '{u}'),
	'reference': ('Periodo de referencia', '{u}'),
	'other': ('Otro periodo', '{u}'),
	'dnbr': ('dNBR (NBR antes − NBR después)', ''),
	'severity': ('Severidad (escala del USGS)', ''),
	'nbr_before': ('NBR antes del incendio', ''),
	'nbr_after': ('NBR después del incendio', ''),
}
DIVERGING_BANDS = ('slope', 'tau', 'z', 'difference', 'dnbr')
MAIN_BANDS = ('slope', 'difference', 'severity')  # shown first when a GeoTIFF has them


# Reading the reports ------------------------------------------------------------------------------------------------

def read_specs(path):
	"""The reports of a YAML (or JSON) file: one, or several in `reports:` with the other keys as the default of each
	one. Returns [(spec, folder of the file)]."""
	import yaml
	with open(os.path.expanduser(path), encoding='utf-8') as f:
		data = yaml.safe_load(f)
	base = os.path.dirname(os.path.abspath(os.path.expanduser(path)))
	if not isinstance(data, dict):
		raise ValueError(f'{path}: a report is a dictionary (see monitoreo.publish)')
	if 'reports' in data:
		common = {k: v for k, v in data.items() if k != 'reports'}
		return [(dict(common, **r), base) for r in data['reports']]
	return [(data, base)]


def slug(text):
	"""Lowercase ASCII letters, digits and hyphens of TEXT (an id of a report)."""
	text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode()
	return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:60]


def _list(x):
	return [] if x is None else list(x) if isinstance(x, (list, tuple)) else [x]


def _path(p, base):
	return os.path.normpath(os.path.join(base, os.path.expanduser(str(p))))


def _find(path, base, folders):
	"""PATH (relative to BASE), or a file of the same name in FOLDERS (the files of a result that were moved)."""
	p = _path(path, base)
	if os.path.isfile(p):
		return p
	for d in folders:
		q = os.path.join(d, os.path.basename(str(path)))
		if os.path.isfile(q):
			return q
	raise FileNotFoundError(f"cannot find {path}" + (f" (nor in {', '.join(folders)})" if folders else ''))


def calls_log(folder=None):
	"""Path of the log of the calls of the MCP server, in FOLDER (default: its folder MONITOREO_OUTPUT)."""
	folder = folder or os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO'
	return os.path.join(os.path.expanduser(folder), CALLS_LOG)


def log_call(tool, args, result, folder=None):
	"""Append the call of a tool that wrote files ({tool, args, result}) to the log of the MCP server, so that
	publish() finds the call of each file."""
	path = calls_log(folder)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, 'a', encoding='utf-8') as f:
		f.write(json.dumps({'time': dt.datetime.now().isoformat(timespec='seconds'), 'tool': tool, 'args': args,
		                    'result': result}, ensure_ascii=False, default=str) + '\n')


def _logged_call(path, log):
	"""The last call of the log LOG that wrote a file of the name of PATH: {tool, args, result}, or None."""
	if not log or not os.path.isfile(log):
		return None
	name, found = os.path.basename(path), None
	with open(log, encoding='utf-8') as f:
		for line in f:
			try:
				c = json.loads(line)
			except ValueError:
				continue
			res = c.get('result') or {}
			if any(isinstance(res.get(k), str) and os.path.basename(res[k]) == name for k in ('file', 'csv', 'chart')):
				found = c
	return found


def _items(spec, base, folders, log):
	"""The results of SPEC as {tool, args, result, title, caption, ...}, with the paths of their files resolved."""
	for item in _list(spec.get('results')):
		item = {'file': item} if isinstance(item, str) else dict(item)
		if 'answer' in item:
			ans = item.pop('answer')
			if isinstance(ans, str):
				with open(_find(ans, base, ()), encoding='utf-8') as f:
					ans = json.load(f)
			call = ans.get('call') or {}
			if ans.get('is_error'):
				raise ValueError(f"the answer of {call.get('tool')} is an error: {ans.get('text')}")
			text = [t for t in ans.get('text') or [] if isinstance(t, dict)]
			item.setdefault('tool', call.get('tool'))
			item.setdefault('args', call.get('args'))
			item.setdefault('result', text[0] if text else {})
		elif 'file' in item and 'result' not in item:
			path = _find(item.pop('file'), base, folders)
			c = _logged_call(path, log) or {}
			item.setdefault('tool', c.get('tool'))
			item.setdefault('args', c.get('args'))
			item['result'] = c.get('result') or {'file' if path.lower().endswith(('.tif', '.tiff')) else 'csv': path}
		res = dict(item.get('result') or {})
		for k in ('file', 'csv', 'chart'):
			if isinstance(res.get(k), str):
				res[k] = _find(res[k], base, folders)
		item['result'] = res
		item['args'] = dict(item.get('args') or {})
		yield item


# Texts --------------------------------------------------------------------------------------------------------------

def _date(d):
	y, m, day = str(d)[:10].split('-')
	return f'{int(day)} {MONTHS[int(m) - 1][:3]} {y}'


def period_text(start, end):
	"""'2001-2024', '2023' or '15 may 2023 - 14 ago 2023'."""
	start, end = str(start)[:10], str(end)[:10]
	if start[5:] == '01-01' and end[5:] == '12-31':
		return start[:4] if start[:4] == end[:4] else f'{start[:4]}-{end[:4]}'
	return f'{_date(start)} - {_date(end)}'


def season_text(season):
	"""' (de junio a agosto)' or ' (del 15 de mayo al 14 de agosto)' of a season ['MM-DD', 'MM-DD']."""
	if not season:
		return ''
	(m1, d1), (m2, d2) = [map(int, str(s).split('-')) for s in season]
	last = (dt.date(2001 + (m2 == 12), m2 % 12 + 1, 1) - dt.timedelta(days=1)).day
	if d1 == 1 and (d2 == last or (m2 == 2 and d2 >= 28)):
		return f' (de {MONTHS[m1 - 1]} a {MONTHS[m2 - 1]})'
	return f' (del {d1} de {MONTHS[m1 - 1]} al {d2} de {MONTHS[m2 - 1]})'


def _var(args):
	v = args.get('variable') or args.get('collection') or args.get('image') or ''
	s = SENSORS.get(args.get('sensor'), args.get('sensor'))
	return f'{v} ({s})' if s else str(v)


def default_title(tool, args):
	"""A title in Spanish of the result of a call."""
	var, season = _var(args), season_text(args.get('season'))
	period = period_text(args['start'], args['end']) if args.get('start') and args.get('end') else ''
	other = period_text(args['other_start'], args['other_end']) \
		if args.get('other_start') and args.get('other_end') else ''
	step = args.get('step') or ('annual' if tool in ('trend_table', 'download_trend') else 'monthly')
	if tool == 'time_series':
		return f'Serie {STEPS.get(step, step)} de {var}, {period}{season}'
	if tool == 'trend_table':
		return f'Tendencia {PARTS.get(step, step)} de {var}, {period}{season}'
	if tool == 'download_trend':
		part = args.get('part')
		if step == 'annual' or not part:
			what = 'anual'
		else:
			what = f'de {MONTHS[int(part) - 1]}' if step == 'monthly' else f'del periodo {part} de 16 días'
		return f'Mapa de la tendencia {what} de {var}, {period}{season}'
	if tool == 'compare_series':
		return f'{var} {"por meses" if step == "monthly" else STEPS.get(step, step)}: {other} frente a {period}{season}'
	if tool == 'download_comparison':
		return f'Mapa de la diferencia de {var}: {other} menos {period}{season}'
	if tool == 'burn_severity':
		sensor = args.get('sensor') or 'Sentinel-2'
		return f'Severidad del incendio (dNBR de {SENSORS.get(sensor, sensor)}): antes, {period}; después, {other}'
	if tool == 'download_image':
		return f'Mapa de {var}, {period}{season}'
	return var or 'Resultado'


def unit_text(unit, per_year=False):
	"""The unit of the catalog ('[ºC]', '[unitless]') as shown: '°C', '' ('°C/año', 'por año' with PER_YEAR)."""
	u = str(unit or '').replace('/ year', '').strip().strip('[]').replace('º', '°').strip()
	u = '' if u.lower() in ('unitless', 'none') else u
	if per_year:
		return f'{u}/año' if u else 'por año'
	return u


def _py(v):
	"""V as a Python literal."""
	if isinstance(v, bool) or v is None:
		return repr(v)
	if isinstance(v, dict):
		return '{' + ', '.join(f'{_py(k)}: {_py(x)}' for k, x in v.items()) + '}'
	if isinstance(v, (list, tuple)):
		return '[' + ', '.join(_py(x) for x in v) + ']'
	if isinstance(v, str):
		return json.dumps(v, ensure_ascii=False)
	return repr(v)


def python_call(tool, args):
	"""The call of monitoreo.services (imported as mo) that gives the same result as the tool."""
	return f"mo.{tool}({', '.join(f'{k}={_py(v)}' for k, v in args.items())})" if tool else None


# Files --------------------------------------------------------------------------------------------------------------

class _Files:
	"""The files of a report in FOLDER, with clean and unique names, and their list for report.json."""

	def __init__(self, folder):
		self.folder, self.list, self._done = folder, [], {}

	def name(self, src, sub, ext=None):
		stem, e = os.path.splitext(os.path.basename(src))
		stem = re.sub(r'_\d{8}-\d{6}$', '', stem)  # the time of the files of the MCP server
		stem = re.sub(r'[^A-Za-z0-9._-]+', '_', stem).strip('_') or 'file'
		ext = ext or e.lower()
		rel, k = f'{sub}/{stem}{ext}', 1
		while os.path.exists(os.path.join(self.folder, rel)):
			k += 1
			rel = f'{sub}/{stem}-{k}{ext}'
		os.makedirs(os.path.join(self.folder, sub), exist_ok=True)
		return rel

	def add(self, src, sub, title, kind, convert=None):
		"""Copy SRC (or write it with CONVERT(src, dst)) to SUB/ once; returns its path in the report."""
		key = (os.path.realpath(src), sub)
		if key in self._done:
			return self._done[key]
		rel = self.name(src, sub, '.tif' if convert else None)
		dst = os.path.join(self.folder, rel)
		(convert or shutil.copyfile)(src, dst)
		self.list.append({'path': rel, 'title': title, 'type': kind, 'bytes': os.path.getsize(dst)})
		self._done[key] = rel
		return rel


def _gdal():
	try:
		from osgeo import gdal, osr
	except ImportError as e:
		raise RuntimeError('publishing maps needs GDAL: conda install -c conda-forge gdal') from e
	gdal.UseExceptions()
	return gdal, osr


def to_cog(src, dst):
	"""Write the GeoTIFF SRC as a Cloud Optimized GeoTIFF DST (gdal_translate -of COG), losslessly compressed, with
	overviews of the nearest pixel (their values are values of the map, also in the classes of a band)."""
	gdal, _ = _gdal()
	gdal.Translate(dst, src, format='COG', creationOptions=[
		'COMPRESS=DEFLATE', 'PREDICTOR=YES', 'BLOCKSIZE=256', 'OVERVIEW_RESAMPLING=NEAREST', 'NUM_THREADS=ALL_CPUS'])
	return dst


def _hex(colours):
	return ['#' + str(c).lstrip('#').lower() for c in colours]


def _stats(a):
	import numpy as np
	v = a[np.isfinite(a)]
	if not v.size:
		return None
	p2, p98 = np.percentile(v, [2, 98])
	return {'min': float(v.min()), 'max': float(v.max()), 'p2': float(p2), 'p98': float(p98), 'mean': float(v.mean()),
	        'count': int(v.size)}


def _continuous(lo, hi, palette, symmetric=False):
	if symmetric:
		m = max(abs(lo or 0), abs(hi or 0)) or 1e-6
		lo, hi = -m, m
	if hi is None or lo is None or hi <= lo:
		lo, hi = (lo or 0) - 0.5, (lo or 0) + 0.5
	return {'type': 'continuous', 'min': float(lo), 'max': float(hi), 'palette': _hex(palette)}


def _severity_legend():
	return {'type': 'categories', 'classes': [
		{'value': c, 'label': label, 'color': '#' + fire.COLOURS[c], 'dnbr_min': fire.limits(c)[0],
		 'dnbr_max': fire.limits(c)[1]} for c, _, label in fire.SEVERITY]}


def _entry(variable, sensor):
	"""The entry of the catalog of a variable and sensor, or None."""
	if not variable:
		return None
	try:
		return catalog.find(variable, sensor)
	except (KeyError, TypeError, ValueError):
		return None


def _bands(tool, args, result, arrays, palette, unit):
	"""Label, unit, legend and statistics of each band of a map of TOOL."""
	entry = _entry(args.get('variable') or ('NBR' if tool == 'burn_severity' else None),
	               args.get('sensor') or ('Sentinel-2' if tool == 'burn_severity' else None))
	ramp = maps.ramp(entry)
	diverging = palette or result.get('palette') or trends.DIVERGING
	stats = {name: _stats(a) for name, a in arrays.items()}
	ref = period_text(args['start'], args['end']) if args.get('start') and args.get('end') else ''
	oth = period_text(args['other_start'], args['other_end']) if args.get('other_start') and args.get('other_end') else ''
	pair = [s for n, s in stats.items() if n in ('reference', 'other', 'nbr_before', 'nbr_after') and s]
	pair_range = (min(s['p2'] for s in pair), max(s['p98'] for s in pair)) if pair else (None, None)
	out = []
	for name, st in stats.items():
		label, u = BANDS.get(name, (None, '{u}'))
		if label is None:  # a single band map (download_image): the variable
			label = (entry or {}).get('vname') or _var(args) or name
		if tool == 'download_comparison' and name in ('reference', 'other', 'difference'):
			label = {'reference': f'Referencia ({ref})', 'other': f'Otro periodo ({oth})',
			         'difference': f'Diferencia ({oth} − {ref})'}[name]
		u = u.replace('{u}/año', unit_text(unit, per_year=True)).replace('{u}', unit_text(unit))
		lo, hi = (st['p2'], st['p98']) if st else (None, None)
		main = name in MAIN_BANDS or len(arrays) == 1
		if name == 'severity':
			legend = _severity_legend()
		elif name == 'p_value':
			legend = _continuous(0.0, 0.1, trends.P_VALUE)
		elif name == 'n':
			legend = _continuous(st['min'] if st else 0, st['max'] if st else 10, trends.YEARS)
		elif name in DIVERGING_BANDS:
			if main and result.get('min') is not None and result.get('max') is not None:
				lo, hi = result['min'], result['max']
			legend = _continuous(-1.0, 1.0, diverging) if name == 'tau' else _continuous(lo, hi, diverging, True)
		elif name in ('reference', 'other', 'nbr_before', 'nbr_after'):
			legend = _continuous(*pair_range, ramp)
		elif main and result.get('min') is not None and result.get('max') is not None:
			legend = _continuous(result['min'], result['max'], palette or result.get('palette') or ramp)
		else:
			legend = _continuous(lo, hi, palette if main and palette else ramp)
		out.append({'name': name, 'label': label, 'unit': u, 'legend': legend, 'stats': st})
	return out


def _read_map(path):
	"""(dataset, {band name: array with NaN as NoData}) of a GeoTIFF."""
	import numpy as np
	gdal, _ = _gdal()
	ds = gdal.Open(path)
	arrays = {}
	for i in range(ds.RasterCount):
		b = ds.GetRasterBand(i + 1)
		a = b.ReadAsArray().astype('float64')
		nd = b.GetNoDataValue()
		if nd is not None:
			a[a == nd] = np.nan
		name = b.GetDescription() or ('value' if ds.RasterCount == 1 else f'band{i + 1}')
		arrays[name] = a
	return ds, arrays


def _georef(ds):
	"""CRS (EPSG:code), its PROJ.4 definition, extent, bounds in longitude and latitude, size and resolution."""
	_, osr = _gdal()
	srs = osr.SpatialReference(wkt=ds.GetProjection())
	srs.AutoIdentifyEPSG()
	code = srs.GetAuthorityCode(None)
	gt = ds.GetGeoTransform()
	w, h = ds.RasterXSize, ds.RasterYSize
	xs, ys = [gt[0], gt[0] + gt[1] * w], [gt[3], gt[3] + gt[5] * h]
	extent = [min(xs), min(ys), max(xs), max(ys)]
	wgs = osr.SpatialReference()
	wgs.ImportFromEPSG(4326)
	wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
	srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
	tr = osr.CoordinateTransformation(srs, wgs)
	pts = [tr.TransformPoint(extent[0] + (extent[2] - extent[0]) * i / 4, extent[1] + (extent[3] - extent[1]) * j / 4)
	       for i in range(5) for j in range(5)]
	bounds = [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]
	return {'crs': f'EPSG:{code}' if code else 'EPSG:unknown', 'proj4': srs.ExportToProj4().strip(),
	        'extent': [round(v, 6) for v in extent], 'bounds': [round(v, 6) for v in bounds], 'size': [w, h],
	        'resolution': abs(gt[1])}


def _colours(values, legend):
	"""RGBA (uint8, H x W x 4) of the array VALUES (NaN: transparent) with a LEGEND of the viewer."""
	import numpy as np
	rgba = np.zeros(values.shape + (4,), dtype='uint8')
	ok = np.isfinite(values)
	if legend['type'] == 'categories':
		for c in legend['classes']:
			sel = ok & (np.round(values) == c['value'])
			rgba[sel] = [int(c['color'][i:i + 2], 16) for i in (1, 3, 5)] + [255]
		return rgba
	pal = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in legend['palette']], dtype='float64')
	t = np.clip((np.where(ok, values, legend['min']) - legend['min']) / (legend['max'] - legend['min']), 0, 1)
	x = t * (len(pal) - 1)
	i = np.minimum(np.floor(x).astype(int), len(pal) - 2) if len(pal) > 1 else np.zeros(x.shape, int)
	f = (x - i)[..., None] if len(pal) > 1 else 0
	col = pal[i] * (1 - f) + pal[np.minimum(i + 1, len(pal) - 1)] * f
	rgba[..., :3] = np.round(col).astype('uint8')
	rgba[..., 3] = np.where(ok, 255, 0)
	return rgba


NOT_SIGNIFICANT = '#dcdbd6'  # pixels without a significant trend


def _thumbnail_of_map(cog, entry, dst, width=THUMBNAIL_WIDTH):
	import numpy as np
	gdal, _ = _gdal()
	ds = gdal.Open(cog)
	h = max(1, round(ds.RasterYSize * width / ds.RasterXSize))
	names = [b['name'] for b in entry['bands']]

	def read(name):
		b = ds.GetRasterBand(names.index(name) + 1)
		a = b.ReadAsArray(buf_xsize=width, buf_ysize=h, resample_alg=gdal.GRIORA_NearestNeighbour).astype('float64')
		if b.GetNoDataValue() is not None:
			a[a == b.GetNoDataValue()] = np.nan
		return a

	band = next(b for b in entry['bands'] if b['name'] == entry['band'])
	values = read(band['name'])
	rgba = _colours(values, band['legend'])
	sig = entry.get('significance')
	if sig:
		p = read(sig['band'])
		grey = [int(NOT_SIGNIFICANT[i:i + 2], 16) for i in (1, 3, 5)] + [255]
		rgba[np.isfinite(values) & ~(p < sig['alpha'])] = grey
	_write_png(rgba, dst)


def _write_png(rgba, dst):
	gdal, _ = _gdal()
	h, w = rgba.shape[:2]
	mem = gdal.GetDriverByName('MEM').Create('', w, h, 4, gdal.GDT_Byte)
	for i in range(4):
		mem.GetRasterBand(i + 1).WriteArray(rgba[..., i])
	gdal.GetDriverByName('PNG').CreateCopy(dst, mem)


def _thumbnail_of_image(src, dst, width=THUMBNAIL_WIDTH):
	gdal, _ = _gdal()
	gdal.Translate(dst, src, format='PNG', width=width, height=0, resampleAlg='average')
	for aux in glob.glob(dst + '.aux.xml'):
		os.remove(aux)


# Results ------------------------------------------------------------------------------------------------------------

def _read_csv(path):
	with open(path, newline='', encoding='utf-8') as f:
		return list(csv.DictReader(f))


def _num(x):
	try:
		return float(x)
	except (TypeError, ValueError):
		return None


def _chart_type(tool, path):
	if tool in CHARTS:
		return CHARTS[tool]
	with open(path, newline='', encoding='utf-8') as f:
		cols = set(next(csv.reader(f), []))
	return ('series' if {'date', 'value'} <= cols else 'trends' if 'slope' in cols else
	        'comparison' if 'difference' in cols else 'burn_severity' if {'class', 'ha'} <= cols else 'table')


def _results(item, files, n):
	"""The results of report.json of a call (ITEM): a map with its GeoTIFF, a chart with its CSV, or both."""
	tool, args, res = item.get('tool'), item['args'], item['result']
	call = {'tool': tool, 'args': args, 'python': python_call(tool, args)} if tool else None
	title = item.get('title') or default_title(tool, args)
	unit = res.get('unit') or ''
	if unit.endswith('/ year'):
		unit = unit[:-len('/ year')].strip()
	out = []
	if res.get('file') and str(res['file']).lower().endswith(('.tif', '.tiff')):
		cog = files.add(res['file'], 'maps', f'Mapa (GeoTIFF): {title}', 'GeoTIFF', convert=to_cog)
		ds, arrays = _read_map(os.path.join(files.folder, cog))
		bands = _bands(tool, args, res, arrays, item.get('palette'), unit)
		names = [b['name'] for b in bands]
		main = item.get('band') or next((b for b in MAIN_BANDS if b in names), names[0])
		sig = None
		if 'p_value' in names and item.get('significance', True) is not False:
			sig = {'band': 'p_value', 'alpha': float(item.get('significance') or args.get('alpha') or 0.05)}
		entry = dict({'id': f'r{n + len(out) + 1}', 'kind': 'map', 'title': title, 'caption': item.get('caption'),
		              'tool': tool, 'cog': cog, 'nodata': NODATA, 'bands': bands, 'band': main,
		              'significance': sig, 'images': res.get('images'), 'call': call}, **_georef(ds))
		out.append(entry)
	if res.get('csv'):
		path = files.add(res['csv'], 'data', f'Tabla (CSV): {title}', 'CSV')
		chart = item.get('chart') or _chart_type(tool, res['csv'])
		entry = {'id': f'r{n + len(out) + 1}', 'kind': 'chart', 'chart': chart,
		         'title': item.get('chart_title') or title if out else title, 'caption': item.get('chart_caption') or
		         (item.get('caption') if not out else None), 'tool': tool, 'csv': path, 'png': None,
		         'unit': unit_text(unit), 'step': args.get('step'), 'call': call}
		if chart == 'trends':
			entry['slope_unit'] = unit_text(unit, per_year=True)
			entry['alpha'] = float(args.get('alpha') or 0.05)
		if chart == 'comparison':
			entry['names'] = [period_text(args.get('start'), args.get('end')),
			                  period_text(args.get('other_start'), args.get('other_end'))] \
				if args.get('start') and args.get('other_start') else ['Referencia', 'Otro periodo']
		if chart == 'burn_severity':
			entry['classes'] = _severity_legend()['classes']
			entry['burned_ha'] = res.get('burned_ha')
			if out:
				entry['title'] = item.get('chart_title') or 'Superficie de cada clase de severidad'
		if res.get('chart'):
			entry['png'] = files.add(res['chart'], 'files', f'Gráfico (PNG): {title}', 'PNG')
		out.append(entry)
	elif res.get('chart'):
		files.add(res['chart'], 'files', f'Gráfico (PNG): {title}', 'PNG')
	if not out:
		raise ValueError(f'the result of {tool or "a file"} has no GeoTIFF nor CSV to publish: {sorted(res)}')
	return out


SAME_SERIES = ('region', 'variable', 'sensor', 'season', 'quality', 'metric', 'stat', 'collection', 'step')


def _link_trends(results, folder):
	"""Add to each annual series the Sen lines of the trends of the same series over its period or part of it."""
	for s in results:
		call = s.get('call') or {}
		if s.get('chart') != 'series' or (call.get('args') or {}).get('step') != 'annual':
			continue
		a = call['args']
		lines = []
		for t in results:
			b = (t.get('call') or {}).get('args') or {}
			if t.get('chart') != 'trends' or any(a.get(k) != b.get(k) for k in SAME_SERIES if k != 'step'):
				continue
			if (b.get('step') or 'annual') != 'annual' or not (a['start'] <= b.get('start', '') <= b.get('end', '') <= a['end']):
				continue
			origin = composite.windows([b['start'], b['end']], b.get('season'))[0][0]
			for r in _read_csv(os.path.join(folder, t['csv'])):
				if _num(r.get('slope')) is None:
					continue
				lines.append({'region': r['region'], 'trend': t['id'], 'start': b['start'], 'end': b['end'],
				              'period': period_text(b['start'], b['end']), 'origin': origin,
				              'from': int(r['first_year']), 'to': int(r['last_year']), 'slope': _num(r['slope']),
				              'intercept': _num(r['intercept']), 'p_value': _num(r['p_value']),
				              'significant': r.get('significant') == 'True'})
		if lines:
			s['sen'] = lines


def _region(spec, items):
	region = spec.get('region') or {}
	region = {'name': region} if isinstance(region, str) else dict(region)
	if not region.get('wdpa_id'):
		for it in items:
			w = (it['args'].get('region') or {}).get('wdpa_id') if isinstance(it['args'].get('region'), dict) else None
			if w:
				region['wdpa_id'] = w[0] if isinstance(w, list) and len(w) == 1 else w
				break
	if not region.get('name'):
		names = [r for it in items for r in it['result'].get('regions') or []]
		region['name'] = ', '.join(dict.fromkeys(names)) or 'Región'
	return region


def _variables(items):
	out = {}
	for it in items:
		a = it['args']
		var = a.get('variable') or ('NBR' if it.get('tool') == 'burn_severity' else None)
		if not var:
			continue
		sensor = a.get('sensor') or ('Sentinel-2' if it.get('tool') == 'burn_severity' else None)
		e = _entry(var, sensor) or {}
		name, unit = e.get('vname'), unit_text(e.get('unit'))
		out.setdefault((var, sensor), {'variable': var, 'sensor': SENSORS.get(sensor, sensor), 'name': name,
		                               'unit': unit})
	return list(out.values())


def _periods(items):
	out = []
	for it in items:
		a = it['args']
		for k0, k1 in (('start', 'end'), ('other_start', 'other_end')):
			if a.get(k0) and a.get(k1):
				p = [str(a[k0])[:10], str(a[k1])[:10]]
				if p not in out:
					out.append(p)
	return sorted(out)


def _paragraphs(text):
	return str(text).strip() if text else None


def license_of(value=None):
	"""The licence {id, name, url, text} of a report: an id of LICENSES or its name (e.g. 'CC BY 4.0'), a dictionary
	{name, url, text} or None (LICENSE)."""
	if isinstance(value, dict):
		return {k: str(value[k]) for k in ('id', 'name', 'url', 'text') if value.get(k)}
	key = str(value or LICENSE).strip().upper()
	for lid, lic in LICENSES.items():
		if key in (lid, lic['name'].upper(), lid.replace('-', ' ')):
			return {'id': lid, **lic}
	raise ValueError(f'unknown licence {value}: one of {", ".join(LICENSES)} or {{name, url, text}}')


def build(spec, rid, base, folders, log, folder):
	"""Write the files of the report SPEC to FOLDER and return its report.json."""
	files = _Files(folder)
	items = list(_items(spec, base, folders, log))
	results = []
	for it in items:
		results += _results(it, files, len(results))
	_link_trends(results, folder)
	for d in _list(spec.get('downloads')):
		d = {'path': d} if isinstance(d, str) else dict(d)
		src = _find(d['path'], base, folders)
		files.add(src, 'files', d.get('title') or os.path.basename(src), os.path.splitext(src)[1].lstrip('.').upper())
	thumbnail = 'thumbnail.png'
	dst = os.path.join(folder, thumbnail)
	maps_ = [r for r in results if r['kind'] == 'map']
	pngs = [r['png'] for r in results if r.get('png')]
	if spec.get('thumbnail'):
		_thumbnail_of_image(_find(spec['thumbnail'], base, folders), dst)
	elif maps_:
		_thumbnail_of_map(os.path.join(folder, maps_[0]['cog']), maps_[0], dst)
	elif pngs:
		_thumbnail_of_image(os.path.join(folder, pngs[0]), dst)
	else:
		thumbnail = None
	region = _region(spec, items)
	if maps_:
		bs = [r['bounds'] for r in maps_]
		region['bounds'] = [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)]
	periods = _periods(items)
	analyses = list(dict.fromkeys(ANALYSES.get(it.get('tool'), 'map') for it in items))
	published = str(spec.get('published') or dt.date.today().isoformat())[:10]
	sections = [{'title': str(s['title']), 'text': _paragraphs(s.get('text'))} for s in _list(spec.get('sections'))]
	return {
		'schema': SCHEMA, 'id': rid, 'title': str(spec['title']).strip(),
		'question': _paragraphs(spec.get('question')), 'summary': _paragraphs(spec.get('summary')) or '',
		'answer': _paragraphs(spec.get('answer')), 'method': _paragraphs(spec.get('method')), 'sections': sections,
		'region': region, 'variables': _variables(items),
		'analyses': [{'id': a, 'name': ANALYSIS_NAMES.get(a, a)} for a in analyses],
		'periods': periods, 'years': [int(min(p[0] for p in periods)[:4]), int(max(p[1] for p in periods)[:4])]
		if periods else None,
		'published': published,
		'authors': [str(a) for a in _list(spec.get('authors'))] or ['OBSNEV - Universidad de Granada'],
		'collection': spec.get('collection'), 'keywords': [str(k) for k in _list(spec.get('keywords'))],
		'license': license_of(spec.get('license')), 'thumbnail': thumbnail, 'results': results, 'files': files.list,
		'software': {'monitoreo': __version__},
	}


# Site ---------------------------------------------------------------------------------------------------------------

def site_folder(site=None):
	return os.path.abspath(os.path.expanduser(site or DEFAULT_SITE))


def _write_json(obj, path):
	tmp = path + '.tmp'
	with open(tmp, 'w', encoding='utf-8') as f:
		json.dump(obj, f, ensure_ascii=False, indent=1, allow_nan=False)
		f.write('\n')
	os.replace(tmp, path)


def publish(spec, site=None, base=None, log=None):
	"""Publish the report SPEC (a dictionary, see the docstring of the module) in the folder SITE (default:
	MONITOREO_SITE or ~/MonitorEO/visor), with the paths of SPEC relative to BASE (default: the current folder) and the
	calls of its files read from the log LOG of the MCP server (default: that of MONITOREO_OUTPUT). Writes
	SITE/reports/<id>/ (replacing the report of the same id), the viewer and SITE/catalog.json. Returns report.json."""
	site = site_folder(site)
	base = os.path.abspath(os.path.expanduser(base or os.getcwd()))
	if not spec.get('title'):
		raise ValueError('a report needs a title')
	rid = str(spec.get('id') or slug(f"{spec.get('published') or dt.date.today()}-{spec['title']}"))
	if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', rid):
		raise ValueError(f'the id of a report has lowercase letters, digits and hyphens: {rid}')
	license_of(spec.get('license'))
	folders = [_path(p, base) for p in _list(spec.get('files'))]
	reports = os.path.join(site, 'reports')
	os.makedirs(reports, exist_ok=True)
	tmp = os.path.join(reports, f'.{rid}.tmp')
	shutil.rmtree(tmp, ignore_errors=True)
	os.makedirs(tmp)
	try:
		report = build(spec, rid, base, folders, log if log is not None else calls_log(), tmp)
		problems = check_report(report, tmp)
		if problems:
			raise ValueError(f'report {rid}: ' + '; '.join(problems))
		_write_json(report, os.path.join(tmp, 'report.json'))
		final = os.path.join(reports, rid)
		shutil.rmtree(final, ignore_errors=True)
		os.rename(tmp, final)
	except BaseException:
		shutil.rmtree(tmp, ignore_errors=True)
		raise
	install_viewer(site)
	update_catalog(site)
	return report


def remove(rid, site=None):
	"""Remove the report RID from SITE and from its catalogue."""
	site = site_folder(site)
	folder = os.path.join(site, 'reports', str(rid))
	if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', str(rid)) or not os.path.isdir(folder):
		raise ValueError(f'there is no report {rid} in {site}')
	shutil.rmtree(folder)
	return update_catalog(site)


def install_viewer(site=None):
	"""Copy the viewer (index.html, report.html, assets/ and the logos of monitoreo.about) to SITE."""
	site = site_folder(site)
	for src in glob.glob(os.path.join(VIEWER, '**', '*'), recursive=True):
		if os.path.isfile(src):
			dst = os.path.join(site, os.path.relpath(src, VIEWER))
			os.makedirs(os.path.dirname(dst), exist_ok=True)
			shutil.copyfile(src, dst)
	logos = os.path.join(site, 'assets', 'logos')
	os.makedirs(logos, exist_ok=True)
	for p in about_.LOGOS:
		shutil.copyfile(p, os.path.join(logos, os.path.basename(p)))
	open(os.path.join(site, '.nojekyll'), 'w').close()  # GitHub Pages: serve the files as they are
	return site


CATALOG_KEYS = ('id', 'title', 'question', 'summary', 'region', 'variables', 'analyses', 'periods', 'years',
                'published', 'authors', 'collection', 'keywords', 'license')


def update_catalog(site=None):
	"""Make SITE/catalog.json again from the report.json of SITE/reports, the newest first. Returns the catalogue."""
	site = site_folder(site)
	entries = []
	for path in glob.glob(os.path.join(site, 'reports', '*', 'report.json')):
		with open(path, encoding='utf-8') as f:
			r = json.load(f)
		folder = f"reports/{r['id']}"
		e = {k: r.get(k) for k in CATALOG_KEYS}
		e.update(path=f'{folder}/report.json', thumbnail=f"{folder}/{r['thumbnail']}" if r.get('thumbnail') else None,
		         maps=sum(x['kind'] == 'map' for x in r['results']),
		         charts=sum(x['kind'] == 'chart' for x in r['results']))
		entries.append(e)
	entries.sort(key=lambda e: (slug(e['region'].get('name') or ''), e['title']))
	entries.sort(key=lambda e: e['published'], reverse=True)
	a = about_.about('es')
	a['logos'] = [f'assets/logos/{os.path.basename(p)}' for p in a['logos']]
	cat = {'schema': SCHEMA, 'title': SITE_TITLE, 'updated': dt.datetime.now().isoformat(timespec='seconds'),
	       'software': {'monitoreo': __version__}, 'about': a, 'license': license_of(), 'analyses': ANALYSIS_NAMES,
	       'reports': entries}
	os.makedirs(site, exist_ok=True)
	_write_json(cat, os.path.join(site, 'catalog.json'))
	return cat


# Checks -------------------------------------------------------------------------------------------------------------

def _date_ok(s):
	try:
		dt.date.fromisoformat(str(s))
		return True
	except ValueError:
		return False


def _rel_ok(p):
	return isinstance(p, str) and p and not os.path.isabs(p) and '..' not in p.split('/') and '\\' not in p


def _legend_problems(legend, where):
	if not isinstance(legend, dict):
		return [f'{where}: no legend']
	if legend.get('type') == 'continuous':
		ok = all(isinstance(legend.get(k), (int, float)) and math.isfinite(legend[k]) for k in ('min', 'max'))
		out = [] if ok and legend['min'] < legend['max'] else [f'{where}: min < max']
		pal = legend.get('palette')
		if not isinstance(pal, list) or len(pal) < 2 or not all(re.fullmatch(r'#[0-9a-f]{6}', str(c)) for c in pal):
			out.append(f'{where}: palette of 2 or more colours #rrggbb')
		return out
	if legend.get('type') == 'categories':
		cl = legend.get('classes')
		if not isinstance(cl, list) or not cl or not all(
				isinstance(c.get('value'), (int, float)) and c.get('label')
				and re.fullmatch(r'#[0-9a-f]{6}', str(c.get('color'))) for c in cl):
			return [f'{where}: classes with value, label and colour #rrggbb']
		return []
	return [f"{where}: unknown legend type {legend.get('type')}"]


def _license_problems(lic, where):
	ok = isinstance(lic, dict) and lic.get('name') and re.fullmatch(r'https://\S+', str(lic.get('url', '')))
	return [] if ok else [f'{where} has a name and an https url']


def check_report(report, folder=None):
	"""Problems (texts) of a report.json, and of its files in FOLDER if given; [] if it is right."""
	p = []
	if report.get('schema') != SCHEMA:
		p.append(f'schema is not {SCHEMA}')
	if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', str(report.get('id', ''))):
		p.append('id of lowercase letters, digits and hyphens')
	for k in ('title', 'summary'):
		if not isinstance(report.get(k), str) or (k == 'title' and not report[k].strip()):
			p.append(f'{k} is a text')
	if not _date_ok(report.get('published')):
		p.append('published is a date YYYY-MM-DD')
	if not isinstance(report.get('authors'), list) or not report['authors']:
		p.append('authors is a list')
	p += _license_problems(report.get('license'), 'license')
	region = report.get('region')
	if not isinstance(region, dict) or not region.get('name'):
		p.append('region has a name')
	elif region.get('bounds') is not None:
		w, s, e, n = region['bounds']
		if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
			p.append('region.bounds are [west, south, east, north] in degrees')
	lists = [f'{k} is a list' for k in ('variables', 'analyses', 'periods', 'results', 'files', 'sections', 'keywords')
	         if not isinstance(report.get(k), list)]
	if lists:  # the rest cannot be checked
		return p + lists
	if any(not v.get('variable') for v in report['variables']):
		p.append('every variable has a name')
	if any(not a.get('id') or not a.get('name') for a in report['analyses']):
		p.append('every analysis has an id and a name')
	for per in report['periods']:
		if not (isinstance(per, list) and len(per) == 2 and all(_date_ok(d) for d in per) and per[0] <= per[1]):
			p.append(f'period {per} is [first day, last day]')
	if report['periods'] and report.get('years') != [int(min(x[0] for x in report['periods'])[:4]),
	                                                 int(max(x[1] for x in report['periods'])[:4])]:
		p.append('years are those of the periods')
	if not report['results']:
		p.append('a report has results')
	ids = [r.get('id') for r in report['results']]
	if len(set(ids)) != len(ids):
		p.append('the ids of the results are different')
	paths = [f.get('path') for f in report['files']]
	for r in report['results']:
		where = f"result {r.get('id')}"
		if not r.get('title'):
			p.append(f'{where}: no title')
		call = r.get('call')
		if call is not None and (not call.get('tool') or not isinstance(call.get('args'), dict)):
			p.append(f'{where}: the call has a tool and its args')
		if r.get('kind') == 'map':
			missing = [f'{where}: no {k}' for k in ('cog', 'crs', 'proj4', 'bounds', 'extent', 'size', 'bands', 'band')
			           if not r.get(k)]
			if missing:
				p += missing
				continue
			if r['cog'] not in paths:
				p.append(f'{where}: its COG is not in files')
			names = [b.get('name') for b in r['bands']]
			if r['band'] not in names:
				p.append(f'{where}: band {r["band"]} is not one of {names}')
			for b in r['bands']:
				if not b.get('label') or 'unit' not in b:
					p.append(f"{where}: band {b.get('name')} has a label and a unit")
				p += _legend_problems(b.get('legend'), f"{where}, band {b.get('name')}")
			sig = r.get('significance')
			if sig and (sig.get('band') not in names or not 0 < sig.get('alpha', 0) < 1):
				p.append(f'{where}: significance is {{band, alpha}}')
			w, s, e, n = r['bounds']
			if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
				p.append(f'{where}: bounds are [west, south, east, north] in degrees')
		elif r.get('kind') == 'chart':
			if r.get('chart') not in CHART_TYPES:
				p.append(f"{where}: chart is one of {', '.join(CHART_TYPES)}")
			if r.get('csv') not in paths:
				p.append(f'{where}: its CSV is not in files')
			if r.get('png') and r['png'] not in paths:
				p.append(f'{where}: its PNG is not in files')
		else:
			p.append(f'{where}: kind is map or chart')
	for f in report['files']:
		if not _rel_ok(f.get('path')) or not f.get('title') or not isinstance(f.get('bytes'), int):
			p.append(f"file {f.get('path')}: a relative path, a title and its bytes")
		elif folder and not os.path.isfile(os.path.join(folder, f['path'])):
			p.append(f"file {f['path']} does not exist")
	if report.get('thumbnail') is not None:
		if not _rel_ok(report['thumbnail']):
			p.append('thumbnail is a relative path')
		elif folder and not os.path.isfile(os.path.join(folder, report['thumbnail'])):
			p.append(f"thumbnail {report['thumbnail']} does not exist")
	return p


def check_catalog(cat, site=None):
	"""Problems (texts) of a catalog.json, and of its reports in SITE if given; [] if it is right."""
	p = []
	if cat.get('schema') != SCHEMA:
		p.append(f'schema is not {SCHEMA}')
	if not isinstance(cat.get('about'), dict) or not cat['about'].get('acknowledgements'):
		p.append('about has the description and the acknowledgements')
	p += _license_problems(cat.get('license'), 'license')
	if not isinstance(cat.get('reports'), list):
		return p + ['reports is a list']
	ids = [r.get('id') for r in cat['reports']]
	if len(set(ids)) != len(ids):
		p.append('the ids of the reports are different')
	dates = [r.get('published') or '' for r in cat['reports']]
	if dates != sorted(dates, reverse=True):
		p.append('the reports are sorted from the newest')
	for r in cat['reports']:
		where = f"report {r.get('id')}"
		for k in ('title', 'summary', 'region', 'published', 'variables', 'analyses', 'license', 'path'):
			if r.get(k) is None:
				p.append(f'{where}: no {k}')
		if r.get('path') != f"reports/{r.get('id')}/report.json":
			p.append(f'{where}: path is reports/<id>/report.json')
		elif site:
			path = os.path.join(site, r['path'])
			if not os.path.isfile(path):
				p.append(f'{where}: {r["path"]} does not exist')
				continue
			with open(path, encoding='utf-8') as f:
				rep = json.load(f)
			if rep.get('id') != r['id'] or rep.get('title') != r['title']:
				p.append(f'{where}: it is not that of {r["path"]}')
			p += [f'{where}: {x}' for x in check_report(rep, os.path.dirname(path))]
		if r.get('thumbnail') and site and not os.path.isfile(os.path.join(site, r['thumbnail'])):
			p.append(f"{where}: {r['thumbnail']} does not exist")
	if site:
		for logo in cat.get('about', {}).get('logos', []):
			if not os.path.isfile(os.path.join(site, logo)):
				p.append(f'logo {logo} does not exist')
		for page in ('index.html', 'report.html'):
			if not os.path.isfile(os.path.join(site, page)):
				p.append(f'{page} does not exist')
	return p


def check_site(site=None):
	"""Problems (texts) of the catalogue and the reports of SITE; [] if it is right."""
	site = site_folder(site)
	path = os.path.join(site, 'catalog.json')
	if not os.path.isfile(path):
		return [f'{path} does not exist']
	with open(path, encoding='utf-8') as f:
		cat = json.load(f)
	p = check_catalog(cat, site)
	listed = {r.get('id') for r in cat.get('reports') or []}
	for d in glob.glob(os.path.join(site, 'reports', '*', 'report.json')):
		rid = os.path.basename(os.path.dirname(d))
		if rid not in listed:
			p.append(f'report {rid} is not in the catalogue (publish again or update_catalog)')
	return p


# Local server -------------------------------------------------------------------------------------------------------

class _Handler(http.server.SimpleHTTPRequestHandler):
	"""Static files with HTTP range requests (the browser reads the COGs by parts), as GitHub Pages or nginx."""

	extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map, **{
		'.tif': 'image/tiff', '.json': 'application/json', '.js': 'text/javascript', '.csv': 'text/csv'})
	_range = None

	def end_headers(self):
		self.send_header('Accept-Ranges', 'bytes')
		self.send_header('Cache-Control', 'no-cache')
		super().end_headers()

	def send_head(self):
		self._range = None
		path = self.translate_path(self.path)
		m = re.fullmatch(r'bytes=(\d*)-(\d*)', (self.headers.get('Range') or '').strip())
		if not m or not os.path.isfile(path) or m.group(0) == 'bytes=-':
			return super().send_head()
		size = os.path.getsize(path)
		if m.group(1):
			start, end = int(m.group(1)), min(int(m.group(2) or size - 1), size - 1)
		else:
			start, end = max(0, size - int(m.group(2))), size - 1
		if start >= size or start > end:
			self.send_response(416)
			self.send_header('Content-Range', f'bytes */{size}')
			self.end_headers()
			return None
		f = open(path, 'rb')
		f.seek(start)
		self._range = end - start + 1
		self.send_response(206)
		self.send_header('Content-Type', self.guess_type(path))
		self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
		self.send_header('Content-Length', str(self._range))
		self.end_headers()
		return f

	def copyfile(self, source, outputfile):
		if self._range is None:
			return super().copyfile(source, outputfile)
		left = self._range
		while left > 0:
			chunk = source.read(min(65536, left))
			if not chunk:
				break
			outputfile.write(chunk)
			left -= len(chunk)

	def log_message(self, fmt, *args):
		pass


def serve(site=None, port=8000, host='127.0.0.1'):
	"""Serve SITE at http://HOST:PORT/ (with range requests, as the web servers of the published site) until Ctrl+C."""
	import functools
	site = site_folder(site)
	httpd = http.server.ThreadingHTTPServer((host, port), functools.partial(_Handler, directory=site))
	print(f'Viewer of {site} at http://{host}:{port}/ (Ctrl+C to stop)', flush=True)
	try:
		httpd.serve_forever()
	except KeyboardInterrupt:
		pass
	finally:
		httpd.server_close()
