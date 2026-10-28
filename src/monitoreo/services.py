"""The functions of MonitorEO for the tools that use it (QGIS plugin, MCP server, R package, command line).

They take plain values (text, numbers, lists, dictionaries) and return plain values or files, so every tool
computes exactly the same. A variable is given by its name in the catalog of MonitorEO (variable='NDVI',
sensor='Sentinel-2'; see list_variables) or by an Earth Engine source (collection= and band=, or image= and band=).
A region is a dictionary (see areas.region): {'wdpa_id': 555513}, {'ecoregion_id': 793}, {'bbox': [w, s, e, n]},
{'point': [lon, lat], 'buffer': 1000}, {'geojson': ...} or {'file': 'area.gpkg'}.

Call init(project) first (or set EE_PROJECT): it uses the credentials of `earthengine authenticate`.
"""

import datetime as dt
import os
import re

import ee

from . import areas, catalog, charts, composite, drive, maps, sensors, timeseries
from . import variable as variables
from .grid import Grid

_project = None


def init(project=None):
	"""Connect to Earth Engine with the credentials of `earthengine authenticate` and the Google Cloud PROJECT
	registered in Earth Engine (default: the variable EE_PROJECT). Returns the project."""
	global _project
	project = project or os.environ.get('EE_PROJECT') or os.environ.get('GOOGLE_CLOUD_PROJECT')
	if not project:
		raise RuntimeError('give the Earth Engine project: init(project=...) or the variable EE_PROJECT')
	if project == _project:
		return project
	try:
		ee.Initialize(project=project)
	except Exception as e:
		raise RuntimeError(f'cannot connect to Earth Engine with the project {project}: {e}. Run '
		                   '`earthengine authenticate` once and check that the project is registered in Earth Engine '
		                   '(https://developers.google.com/earth-engine/guides/access)') from e
	_project = project
	return project


def project():
	return _project


# Catalog -----------------------------------------------------------------------------------------------------------

def _name(e, lang, field):
	return e.get(f'{field}_{lang}') or e[field] if lang != 'es' else e[field]


def list_variables(sensor=None, text=None, lang='es'):
	"""Variables of the catalog of MonitorEO: [{ref, variable, sensor, collection, name, group, resolution_m,
	dates, unit}], optionally of one SENSOR or with TEXT in their name or variable."""
	out = []
	for e in catalog.variables():
		if sensor and e['sensor'].lower() != str(sensor).lower():
			continue
		row = {'ref': e['ref'], 'variable': e['index'], 'sensor': e['sensor'], 'collection': e['col'],
		       'name': _name(e, lang, 'vname'), 'group': _name(e, lang, 'type'), 'resolution_m': e['m'],
		       'dates': e['dr'], 'unit': e['unit']}
		if text and str(text).lower() not in f"{row['variable']} {row['name']}".lower():
			continue
		out.append(row)
	return out


def describe_variable(variable_name, sensor=None, collection=None, ref=None, lang='es'):
	"""Everything about a variable of the catalog: formula, collection, scale, unit, pixel filters, notes, ..."""
	e = catalog.find(variable_name, sensor, collection, ref)
	out = {k: e.get(k) for k in ('ref', 'index', 'sensor', 'col', 'm', 'tr', 'dr', 'unit', 'ft', 'scale', 'offset')}
	out['name'] = _name(e, lang, 'vname')
	out['group'] = _name(e, lang, 'type')
	out['pixel_filters'] = sensors.filters(e)
	out['measures'] = [f for f, idx in sensors.MEASURES.items() if e['index'] in idx]
	out['notes'] = e.get('notes', {})
	if e['ref'] in catalog.FIXES:
		out['fixed'] = catalog.FIXES[e['ref']]
	out['alternatives'] = [a['col'] for a in catalog.alternatives(e)]
	return out


def find_protected_areas(text, limit=20):
	"""Protected areas of WDPA whose name contains TEXT: [{SITE_ID (WDPA ID), NAME, DESIG, IUCN_CAT, ISO3, REP_AREA, ...}]."""
	return areas.find_protected_areas(text, limit)


# Variables ---------------------------------------------------------------------------------------------------------

def make_spec(variable=None, sensor=None, start=None, end=None, metric='mean', temporal='period', interannual='mean',
              season=None, quality=None, collection=None, band=None, image=None, ref=None, band_scale=None,
              band_offset=None, terrain=None, exclude_landcover=None):
	"""Spec of a variable (see monitoreo.variable) from the arguments of the services."""
	var = {'metric': metric, 'temporal': temporal, 'interannual': interannual, 'season': season,
	       'quality': quality or {}, 'exclude_landcover': exclude_landcover}
	if start or end:
		var['period'] = [str(start), str(end or dt.date.today().isoformat())]
	if variable or ref is not None:
		var.update({'index': variable, 'sensor': sensor, 'collection': collection, 'ref': ref})
		if ref is not None and not variable:
			var['index'] = catalog.find(None, ref=ref)['index']
	elif image:
		var.update({'image': image, 'band': band, 'terrain': terrain})
		var.pop('metric')
	elif collection:
		var.update({'collection': collection, 'band': band})
	if band_scale is not None:
		var['scale'] = band_scale
	if band_offset is not None:
		var['offset'] = band_offset
	var = {k: v for k, v in var.items() if v is not None}
	return variable_specs(var)[0]


def variable_specs(var):
	return variables.specs(var)


def _title(spec, step=None, metric=None, stat=None):
	k = variables.kind(spec)
	if k == 'catalog':
		e = variables.entry_of(spec)
		name = f"{e['index']} {e['sensor']}"
	else:
		name = f"{spec.get(k)} {spec.get('band') or ''}".strip()
	period = f"{spec['period'][0]} / {spec['period'][1]}" if spec.get('period') else ''
	parts = [name, period]
	if step:
		parts.append(f'{step} {metric}, spatial {stat}')
	return ' | '.join(p for p in parts if p)


def _unit(spec):
	return variables.entry_of(spec)['unit'] if variables.kind(spec) == 'catalog' else ''


def _slug(text):
	return re.sub(r'[^A-Za-z0-9_-]+', '_', str(text)).strip('_')[:80]


# Time series -------------------------------------------------------------------------------------------------------

def time_series(region, variable=None, sensor=None, start=None, end=None, step='monthly', metric='mean', stat='mean',
                season=None, quality=None, scale=None, csv=None, chart=None, progress=None, **source):
	"""Time series of a variable over REGION (one or several features): a value per STEP ('daily', '16-day',
	'monthly', 'annual') and region, reduced in time with METRIC and over the region with STAT (mean, median, min,
	max, std or pN). Writes the table to CSV and the chart to CHART (PNG) if given.
	Returns {'rows': [{region, date, value, n_pixels, n_images}], 'csv', 'chart', 'scale', 'unit', 'title'}."""
	spec = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	regions = areas.region(region)
	rows, used_scale = timeseries.series(spec, regions, step, metric, stat, scale, progress)
	unit = _unit(spec)
	title = _title(spec, step, metric, stat)
	out = {'rows': rows, 'csv': None, 'chart': None, 'scale': used_scale, 'unit': unit, 'title': title,
	       'n_steps': len({r['date'] for r in rows}), 'regions': sorted({r['region'] for r in rows})}
	if csv:
		meta = {'variable': variable or source.get('collection') or source.get('image'), 'sensor': sensor or '',
		        'step': step, 'metric': metric, 'stat': stat, 'unit': unit, 'scale_m': used_scale}
		out['csv'] = timeseries.write_csv(rows, csv, meta)
	if chart and rows:
		try:
			charts.time_series_png(rows, chart, title=title, ylabel=unit or None)
			out['chart'] = chart
		except ImportError:  # no matplotlib: the table and the CSV are still there
			pass
	return out


def time_series_to_drive(region, variable=None, sensor=None, start=None, end=None, step='monthly', metric='mean',
                         stat='mean', season=None, quality=None, scale=None, folder='MonitorEO', name=None, **source):
	"""Export the time series to a CSV file in FOLDER of Google Drive (for long series or many regions).
	Returns {'operation', 'file', 'folder'}."""
	spec = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	regions = areas.region(region)
	table = timeseries.table(spec, regions, step, metric, stat, scale)
	name = _slug(name or f"{variable or source.get('collection')}_{sensor or ''}_{step}_{metric}_{start}_{end}")
	task = ee.batch.Export.table.toDrive(collection=table, description=name[:100], folder=folder, fileNamePrefix=name,
	                                     fileFormat='CSV', selectors=timeseries.COLUMNS)
	task.start()
	return {'operation': task.operation_name or f'projects/{_project}/operations/{task.id}', 'file': name + '.csv',
	        'folder': folder}


# Maps --------------------------------------------------------------------------------------------------------------

def composite_image(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                    interannual='mean', season=None, quality=None, clip=True, resolution=None, **source):
	"""Earth Engine image (ee.Image, band 'value') of a variable over REGION aggregated in time (for rgee, geemap,
	...). Returns (image, regions)."""
	_, regions, img, _ = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                            quality, clip, resolution, source)
	return img, regions


def _build(region, var_name, sensor, start, end, metric, temporal, interannual, season, quality, clip, res, source):
	spec = make_spec(var_name, sensor, start, end, metric=metric, temporal=temporal, interannual=interannual,
	                 season=season, quality=quality, **source)
	regions = areas.region(region)
	res = res or variables.native_scale(spec)
	img = variables.image(spec, regions.geometry(), res)
	if clip:
		img = img.clipToCollection(regions)
	return spec, regions, img, res


def map_layer(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
              interannual='mean', season=None, quality=None, vmin=None, vmax=None, palette=None, clip=True,
              thumbnail=None, **source):
	"""Map of a variable over REGION aggregated in time (e.g. the median NDVI of 2018-2021): URL of its Earth
	Engine tiles (XYZ, valid for some hours) and colour ramp. Writes a PNG preview to THUMBNAIL if given.
	Returns {'url', 'min', 'max', 'palette', 'name', 'unit', 'thumbnail'}."""
	spec, regions, img, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                 quality, clip, None, source)
	entry = variable_entry(spec)
	vis = maps.vis_params(img, regions.geometry(), entry, res, vmin, vmax, palette)
	out = dict(vis, url=maps.tile_url(img, vis), name=_title(spec) + f' ({metric})', unit=_unit(spec), thumbnail=None)
	if thumbnail:
		maps.thumbnail(maps.with_outline(img, vis, regions), regions.geometry().bounds(), None, path=thumbnail)
		out['thumbnail'] = thumbnail
	return out


def variable_entry(spec):
	return variables.entry_of(spec) if variables.kind(spec) == 'catalog' else None


def thumbnail(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
              interannual='mean', season=None, quality=None, vmin=None, vmax=None, palette=None, dimensions=768,
              path=None, **source):
	"""PNG (bytes) of the map of a variable over REGION, with the outline of the region."""
	spec, regions, img, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                 quality, True, None, source)
	vis = maps.vis_params(img, regions.geometry(), variable_entry(spec), res, vmin, vmax, palette)
	return maps.thumbnail(maps.with_outline(img, vis, regions), regions.geometry().bounds(), None, dimensions, path)


def region_stats(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                 interannual='mean', season=None, quality=None, stats=('mean', 'std', 'min', 'p5', 'p50', 'p95', 'max'),
                 scale=None, **source):
	"""Statistics over each feature of REGION of the map of a variable aggregated in time:
	[{region, mean, std, min, p5, p50, p95, max, n_pixels}]."""
	spec, regions, img, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                 quality, False, None, source)
	scale = scale or timeseries.auto_scale(spec, regions)
	red = ee.Reducer.count()
	names = {}
	for s in stats:
		r = composite.reducer(s)
		names[s] = r.getOutputs().getInfo()[0]
		red = red.combine(r, '', True)
	fc = img.reduceRegions(collection=regions, reducer=red, scale=scale, crs=timeseries.region_crs(regions), tileScale=4)
	rows = []
	for f in fc.getInfo()['features']:
		p = f['properties']
		row = {'region': str(p.get('name'))}
		row.update({s: p.get(n) for s, n in names.items()})
		row['n_pixels'] = p.get('count')
		rows.append(row)
	return {'rows': rows, 'scale': scale, 'unit': _unit(spec), 'title': _title(spec) + f' ({metric})'}


# Exports -----------------------------------------------------------------------------------------------------------

def export_image(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                 interannual='mean', season=None, quality=None, resolution=None, crs='auto', folder='MonitorEO',
                 name=None, clip=True, **source):
	"""Export the map of a variable over REGION to a GeoTIFF in FOLDER of Google Drive, on a grid of RESOLUTION
	metres (default: that of the data) in CRS ('auto' = WGS 84 / UTM of the centre of the region).
	Returns {'operation', 'file', 'folder', 'grid'}."""
	spec, regions, img, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                 quality, clip, resolution, source)
	geom = regions.geometry()
	if str(crs).lower() == 'auto':
		lon, lat = geom.centroid(1).coordinates().getInfo()
		crs = areas.utm_of(lon, lat)
	ring = geom.bounds(res, crs).getInfo()['coordinates'][0]
	xs, ys = [p[0] for p in ring], [p[1] for p in ring]
	grid = Grid.around(crs, res, min(xs), min(ys), max(xs), max(ys))
	name = _slug(name or f"{variable or source.get('collection') or source.get('image')}_{sensor or ''}_{metric}_{start}_{end}")
	op = drive.export(img, grid, name, folder, _project)
	return {'operation': op, 'file': name + '.tif', 'folder': folder, 'grid': grid.describe()}


def task_status(operation):
	"""State of an export task: {'state': PENDING|RUNNING|SUCCEEDED|FAILED|CANCELLED|UNKNOWN, 'progress', 'error'}."""
	state, progress, error = drive.status(operation)
	return {'operation': operation, 'state': state, 'progress': progress, 'error': error}


def local_drive_folders():
	"""Folders 'My Drive' of Google Drive for desktop on this computer (to open the exported files)."""
	return drive.local_drives()


def find_exported(folder, name):
	"""Files exported as NAME (NAME.tif or its pieces, or NAME.csv) in the local FOLDER of Google Drive and its
	namesakes 'FOLDER (1)', ..."""
	stem = os.path.splitext(name)[0]
	files = drive.find(folder, stem)
	for d in drive.folders(folder):
		p = os.path.join(d, stem + '.csv')
		if os.path.exists(p):
			files.append(p)
	return files
