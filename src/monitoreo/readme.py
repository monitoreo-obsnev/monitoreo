"""Documentation of the files that MonitorEO writes, so that each one explains itself (as the guide of data management
of the British Ecological Society asks: what each column or band is, with its unit and missing values, how it was
computed, with which version and when, how to reproduce it and how to cite it):

  - a README next to the files of each result (<file>.README.txt), plain text: title, how it was computed, the columns
    of its CSV or the bands of its GeoTIFF, to reproduce it in Python and the references to cite;
  - the metadata of its GeoTIFFs: the call that made it (call), the version of MonitorEO (monitoreo_version), when it
    was computed (computed, ISO 8601), the references, and the name and unit of each band;
  - README.txt in each folder of a recipe (monitoreo.recipe), with every file, from the record of the folder.

monitoreo.services writes them with every result that has files (document); their paths are in the answer (readme).
"""

import datetime as dt
import json
import os
import textwrap

from . import __version__, about, publish, references

WIDTH = 100
NODATA = -9999
# outputs and callbacks of the functions of monitoreo.services: not part of what was computed
NOT_ARGS = {'csv', 'chart', 'path', 'thumbnail', 'progress', 'log', 'folder', 'tile', 'workers', 'record', 'wait',
            'drive_dir', 'overwrite', 'dry_run', 'quick'}

# the columns of the CSV files of the tools ({u}: the unit of the variable)
COLUMNS = {
	'region': 'name of the feature of the region (its name, or its number)',
	'date': 'first day of the time step (YYYY-MM-DD)',
	'value': 'value of the variable{u}: the spatial statistic, over the feature, of the temporal metric of the images '
	         'of the step on each pixel',
	'n_pixels': 'valid pixels of the feature in the step (those left by the pixel filters)',
	'n_images': 'images of the step',
	'key': 'part of the year: m01-m12 (months), p01-p23 (16-day periods from 1 January) or all (the year)',
	'label': 'name of the part of the year (or of the severity class)',
	'n': 'years with data',
	'tau': "Kendall's tau of the yearly values against the years (-1 to 1)",
	'z': 'Mann-Kendall Z (normal approximation, without correction for ties)',
	'p_value': 'two-sided p-value of the Mann-Kendall test',
	'significant': 'p_value below alpha (True or False)',
	'slope': "Sen's slope: change of the variable per year{uy}",
	'intercept': 'value of the Sen line in the first year{u}',
	'first_year': 'first year of the period',
	'last_year': 'last year of the period',
	'reference': 'mean of the part of the year over the years of the reference period{u}',
	'other': 'mean of the part of the year over the years of the other period{u}',
	'difference': 'other - reference{u}',
	'n_reference': 'years with data in the reference period',
	'n_other': 'years with data in the other period',
	'class': 'severity class of the USGS (-2 enhanced regrowth, high; -1 enhanced regrowth, low; 0 unburned; 1 low; '
	         '2 moderate-low; 3 moderate-high; 4 high)',
	'dnbr_min': 'lowest dNBR of the class',
	'dnbr_max': 'highest dNBR of the class (empty: no limit)',
	'ha': 'hectares',
	'mean': 'mean{u}', 'median': 'median{u}', 'std': 'standard deviation{u}', 'min': 'minimum{u}', 'max': 'maximum{u}',
	'p5': 'percentile 5{u}', 'p10': 'percentile 10{u}', 'p50': 'percentile 50{u}', 'p90': 'percentile 90{u}',
	'p95': 'percentile 95{u}',
	# what each row was made with
	'variable': 'variable of the catalog of MonitorEO (or the Earth Engine source)',
	'sensor': 'sensor',
	'step': 'time step', 'metric': 'temporal metric of the images', 'stat': 'spatial statistic over the feature',
	'unit': 'unit of the variable in UDUNITS (1: dimensionless)', 'slope_unit': 'unit of the slope in UDUNITS',
	'scale_m': 'pixel size of the computation (m)',
	'reference_period': 'reference period (first/last day)', 'other_period': 'other period (first/last day)',
	'before': 'period before the fire (first/last day)', 'after': 'period after the fire (first/last day)',
	'index': 'burn index',
}
BANDS = dict({'value': ('Value of the variable', '{u}')}, **publish.BANDS)
# the unit of each band in UDUNITS ({u}: that of the variable); the others are dimensionless ('1')
BAND_UDUNITS = {'value': '{u}', 'slope': '{u} year-1', 'intercept': '{u}', 'difference': '{u}', 'reference': '{u}',
                'other': '{u}'}


def _now():
	return dt.datetime.now().astimezone().isoformat(timespec='seconds')


def call_args(args):
	"""The arguments of a call that say what was computed (without its outputs and callbacks, nor those left empty)."""
	return {k: v for k, v in (args or {}).items()
	        if k not in NOT_ARGS and v is not None and not callable(v) and v != {} and v != []}


def _catalog_unit(result, args):
	"""The unit of the catalog ('[°C]') of the variable of a result."""
	unit = str((result or {}).get('unit') or '').replace('/ year', '').strip()
	if not unit and args.get('variable'):
		try:
			from . import catalog
			unit = catalog.find(args['variable'], args.get('sensor'), args.get('collection'))['unit']
		except (KeyError, ValueError):
			unit = ''
	return unit


def _unit(result, args):
	"""The unit of the variable of a result as shown ('°C', '' if dimensionless)."""
	return publish.unit_text(_catalog_unit(result, args))


def _udunits(result, args):
	"""The unit of the variable of a result in UDUNITS ('degC', '1'), or '' if unknown."""
	from . import catalog
	return catalog.udunits(_catalog_unit(result, args))


def _wrap(text, indent='  ', hang='    '):
	return textwrap.fill(str(text), WIDTH, initial_indent=indent, subsequent_indent=hang, break_long_words=False,
	                     break_on_hyphens=False)


def _csv_header(path):
	import csv
	with open(path, newline='', encoding='utf-8') as f:
		return next(csv.reader(f), [])


def _bands(path):
	"""[(number, name, unit)] of the bands of a GeoTIFF and its grid {crs, resolution, width, height}."""
	from osgeo import gdal, osr
	gdal.UseExceptions()
	ds = gdal.Open(path)
	srs = osr.SpatialReference(wkt=ds.GetProjection()) if ds.GetProjection() else None
	crs = f"EPSG:{srs.GetAuthorityCode(None)}" if srs is not None and srs.GetAuthorityCode(None) else 'unknown CRS'
	grid = {'crs': crs, 'resolution': abs(ds.GetGeoTransform()[1]), 'width': ds.RasterXSize,
	        'height': ds.RasterYSize}
	bands = [(i, ds.GetRasterBand(i).GetDescription(), ds.GetRasterBand(i).GetUnitType())
	         for i in range(1, ds.RasterCount + 1)]
	return bands, grid


def tag(path, tool, args, result, computed=None):
	"""Write to the metadata of the GeoTIFF PATH of a result the call that made it, the version of MonitorEO, when it
	was computed and its references, and give its bands a name (value, if it had none) and their unit."""
	from osgeo import gdal
	gdal.UseExceptions()
	ds = gdal.Open(path, gdal.GA_Update)
	ds.SetMetadataItem('call', json.dumps({'tool': tool, 'args': call_args(args)}, ensure_ascii=False, default=str))
	ds.SetMetadataItem('monitoreo_version', __version__)
	ds.SetMetadataItem('computed', computed or _now())
	if result.get('references'):
		ds.SetMetadataItem('references', '\n'.join(references.texts(result)))
	ds = None
	name_bands(path, _udunits(result, args))


def name_bands(path, unit):
	"""Give the bands of the GeoTIFF PATH a name (value, if it has one band without one) and their unit in UDUNITS,
	with UNIT that of the variable."""
	from osgeo import gdal
	gdal.UseExceptions()
	ds = gdal.Open(path, gdal.GA_Update)
	for i in range(1, ds.RasterCount + 1):
		b = ds.GetRasterBand(i)
		name = b.GetDescription() or ('value' if ds.RasterCount == 1 else f'band_{i}')
		b.SetDescription(name)
		band_unit = band_udunits(name, unit)
		if band_unit:
			b.SetUnitType(band_unit)
	ds = None


def band_udunits(band, unit):
	"""The unit in UDUNITS of a band of the tools, with UNIT that of the variable in UDUNITS ('' if unknown: then
	that of the bands of the variable is unknown too)."""
	template = BAND_UDUNITS.get(band, '1' if band in BANDS else '')
	if '{u}' not in template:
		return template
	if not unit:
		return ''
	return 'year-1' if template == '{u} year-1' and unit == '1' else template.replace('{u}', unit)


def _section(title, name=''):
	"""The heading of a section: TITLE in capitals, and the name of its file as it is."""
	return ['', title.upper() + (f' {name}' if name else '')]


def text(tool, args, result, computed=None):
	"""The README of a result of TOOL called with ARGS (see the module)."""
	from . import report
	result = result if isinstance(result, dict) else {}
	given = call_args(args)
	files = [result[k] for k in ('file', 'csv', 'chart') if isinstance(result.get(k), str) and
	         os.path.exists(result[k])]
	name = os.path.basename(files[0]) if files else tool
	title = report.item_title(tool, given, result)
	out = [f'README of {name}', '=' * min(WIDTH, len(f'README of {name}')), '', title,
	       _wrap(f'Computed with MonitorEO {__version__} in Google Earth Engine on {computed or _now()}.', '', '')]
	out += _section('Files')
	kinds = {'.csv': 'table (CSV, UTF-8, comma-separated, a header row)',
	         '.tif': f'map (GeoTIFF, float32, NoData {NODATA})', '.png': 'chart (PNG)'}
	out += [_wrap(f'{os.path.basename(f)}: {kinds.get(os.path.splitext(f)[1].lower(), "")}') for f in files]
	out += _section('How it was computed')
	out += [_wrap(f'{k}: {v}') for k, v in report.item_facts(tool, given, result)]
	unit, ud = _unit(result, args), _udunits(result, args)
	u, uy = (f' ({unit})' if unit else ''), f" ({unit + '/year' if unit else 'per year'})"
	if ud:
		out += _section('Units')
		per_year = f"; its change per year, {band_udunits('slope', ud)}" if 'trend' in tool else ''
		out.append(_wrap(f"The variable is {'in ' + unit if unit else 'dimensionless'}: in UDUNITS (the units of the CF "
		                 f'conventions), {ud}{per_year}. The columns unit and slope_unit of the CSV and the units of '
		                 'the bands of the GeoTIFF are in UDUNITS (1 is dimensionless).'))
	for f in files:
		ext = os.path.splitext(f)[1].lower()
		if ext == '.csv':
			out += _section('Columns of', os.path.basename(f))
			out += [_wrap(f'{c}: {COLUMNS.get(c, "")}'.rstrip(': ').format(u=u, uy=uy)) for c in _csv_header(f)]
			out.append(_wrap('Empty cells: no data (no valid pixels or no images).'))
		elif ext in ('.tif', '.tiff'):
			bands, grid = _bands(f)
			out += _section('Bands of', os.path.basename(f))
			out.append(_wrap(f"{grid['width']} x {grid['height']} pixels of {grid['resolution']:g} m in {grid['crs']}; "
			                 f'NoData {NODATA}. Its metadata repeat the call, the version and the references.'))
			for i, b, bu in bands:
				label = BANDS.get(b, ('', ''))[0]
				out.append(_wrap(f'{i} {b}: {label}' + (f' ({bu})' if bu else '')))
	call = publish.python_call(tool, given)
	if call:
		out += _section('To reproduce it in Python')
		out += ['  import monitoreo.services as mo', "  mo.init('<Google Cloud project>')  # or mo.init() with the "
		        'shared account of MonitorEO', _wrap(call, '  ', '      ')]
	cited = references.of_result(tool, given, result)
	out += _section('How to cite it')
	out.append(_wrap('Cite these references when the data go into a report, a paper or a map:'))
	out += [_wrap(f'- {r}', '  ', '    ') for r in references.texts({'references': cited['references']})]
	if cited.get('credits'):
		out.append(_wrap('Credits of the data: ' + '; '.join(cited['credits']) + '.'))
	out += ['', _wrap(f'Manual of MonitorEO: {about.MANUAL}/English', '', '')]
	return '\n'.join(out) + '\n'


def readme_path(path):
	"""The README of the file PATH: <file without extension>.README.txt."""
	return os.path.splitext(path)[0] + '.README.txt'


def document(tool, args, result, computed=None):
	"""Document the files of a result of TOOL (see the module): the metadata of its GeoTIFF and its README. Returns the
	path of the README (or of the READMEs of the folders of a recipe), or None if it has no files."""
	if not isinstance(result, dict):
		return None
	computed = computed or _now()
	if tool == 'download_variables':
		folders = result.get('folders') or {}
		paths = [recipe_folder(d, result) for d in (folders.values() if isinstance(folders, dict) else folders)]
		return [p for p in paths if p] or None
	files = [result[k] for k in ('file', 'csv') if isinstance(result.get(k), str) and os.path.exists(result[k])]
	if not files:
		return None
	for f in files:
		if f.lower().endswith(('.tif', '.tiff')):
			tag(f, tool, args, result, computed)
	path = readme_path(files[0])
	with open(path, 'w', encoding='utf-8') as fh:
		fh.write(text(tool, args, result, computed))
	return path


def recipe_folder(folder, result=None, record='monitoreo.json'):
	"""Write README.txt in a FOLDER of a recipe from its record: its grid and each file with its variable, metric,
	period, pixel filters, images and download, and the references of RESULT (the answer of download_variables).
	Returns its path, or None without a record."""
	rec_path = os.path.join(folder, record)
	if not os.path.exists(rec_path):
		return None
	with open(rec_path, encoding='utf-8') as f:
		rec = json.load(f)
	g = rec.get('grid') or {}
	out = [f'README of the folder {os.path.basename(os.path.normpath(folder))}', '',
	       _wrap('GeoTIFFs of a recipe of variables of MonitorEO (monitoreo.recipe), all on the same grid: '
	             f"{g.get('width')} x {g.get('height')} pixels of {g.get('resolution')} m in {g.get('crs')}, "
	             f"extent {g.get('extent')} (west, south, east, north), float32, NoData {NODATA}. Made with MonitorEO "
	             f"{(rec.get('catalog') or {}).get('monitoreo', __version__)}; {record} keeps what each file was made "
	             'with, and the metadata of each GeoTIFF repeat it with its references.', '', ''),
	       _wrap(f"Study area: {rec.get('study_area')}", '', '')]
	out += _section('Files')
	for name, f in sorted((rec.get('files') or {}).items()):
		spec, src = f.get('spec') or {}, f.get('source') or {}
		what = src.get('variable') or spec.get('index') or spec.get('image') or spec.get('collection') or ''
		dated = spec.get('metric') is not None  # the fixed layers (elevation, slope, images) have no period
		parts = [f"{what} ({spec['sensor']})" if spec.get('sensor') else what, f"collection {src['collection']}"
		         if src.get('collection') else '', f"metric {spec.get('metric')}" if spec.get('metric') else '',
		         'period ' + ' to '.join(spec['period']) if dated and spec.get('period') else '',
		         f"season {' to '.join(spec['season'])}" if dated and spec.get('season') else '',
		         f"temporal aggregation {spec.get('temporal')}"
		         if dated and spec.get('temporal') not in (None, 'period') else '',
		         f"unit {src['unit']} (UDUNITS {src['udunits']})" if src.get('udunits') else
		         f"unit {src['unit']}" if src.get('unit') else '',
		         'pixels without ' + ', '.join(k for k, v in (src.get('pixel_filters') or {}).items() if v)
		         if any((src.get('pixel_filters') or {}).values()) else '',
		         f"{f['images']} images" if f.get('images') is not None else '',
		         f"downloaded {f['downloaded']}" if f.get('downloaded') else '', f"via {f['via']}" if f.get('via') else '']
		out.append(_wrap(f"{name}: " + '; '.join(p for p in parts if p) + '.'))
	if rec.get('tasks'):
		out.append(_wrap(f"Still exporting to Google Drive: {', '.join(sorted(rec['tasks']))} (run the recipe again "
		                 'to import them).'))
	if result and result.get('references'):
		out += _section('How to cite them')
		out += [_wrap(f'- {r}', '  ', '    ') for r in references.texts({'references': result['references']})]
		if result.get('credits'):
			out.append(_wrap('Credits of the data: ' + '; '.join(result['credits']) + '.'))
	out += ['', _wrap(f'Manual of MonitorEO: {about.MANUAL}/English', '', '')]
	path = os.path.join(folder, 'README.txt')
	with open(path, 'w', encoding='utf-8') as fh:
		fh.write('\n'.join(out) + '\n')
	return path
