"""The functions of MonitorEO for the tools that use it (QGIS plugin, MCP server, R package, command line).

They take plain values (text, numbers, lists, dictionaries) and return plain values or files, so every tool
computes exactly the same. A variable is given by its name in the catalog of MonitorEO (variable='NDVI',
sensor='Sentinel-2'; see list_variables) or by an Earth Engine source (collection= and band=, or image= and band=).
A region is a dictionary (see areas.region): {'wdpa_id': 555513}, {'ecoregion_id': 793}, {'bbox': [w, s, e, n]},
{'point': [lon, lat], 'buffer': 1000}, {'geojson': ...} or {'file': 'area.gpkg'}.

Besides time series, maps and statistics, the variables are downloaded as GeoTIFFs: one map (download_image, or
export_image to Google Drive) or a recipe of several variables on aligned grids over a study area and its ecoregions
(download_variables, see monitoreo.recipe). The seasonal trends (Mann-Kendall and Sen: trend_table, trend_map,
download_trend) and the comparison of a reference period with another (compare_series, compare_map,
download_comparison) are those of MonitorEO-TEST (see monitoreo.trends).

Call init(project) first (or set EE_PROJECT): it uses the credentials of `earthengine authenticate`.
"""

import datetime as dt
import json
import math
import os
import re

import ee

from . import areas, catalog, charts, composite, drive, maps, sensors, timeseries, trends
from . import recipe as recipes
from . import variable as variables
from .grid import Grid, download

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
	Engine tiles (XYZ, valid for some hours; their values cannot be queried: download_image for that) and colour
	ramp. Writes a PNG preview to THUMBNAIL if given.
	Returns {'url', 'min', 'max', 'palette', 'name', 'unit', 'bounds' (of the region, [w, s, e, n]), 'thumbnail'}."""
	spec, regions, img, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                 quality, clip, None, source)
	entry = variable_entry(spec)
	vis = maps.vis_params(img, regions.geometry(), entry, res, vmin, vmax, palette)
	out = dict(vis, url=maps.tile_url(img, vis), name=_title(spec) + f' ({metric})', unit=_unit(spec),
	           bounds=_bounds(regions), thumbnail=None)
	if thumbnail:
		maps.thumbnail(maps.with_outline(img, vis, regions), regions.geometry().bounds(), None, path=thumbnail)
		out['thumbnail'] = thumbnail
	return out


def _bounds(regions):
	"""[west, south, east, north] (degrees) of REGIONS."""
	ring = regions.geometry().bounds(1).getInfo()['coordinates'][0]
	return [min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring)]


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
	grid = _grid(regions, res, crs)
	name = _slug(name or _file_stem(variable, sensor, metric, start, end, source))
	op = drive.export(img, grid, name, folder, _project)
	return {'operation': op, 'file': name + '.tif', 'folder': folder, 'grid': grid.describe()}


def _grid(regions, res, crs):
	"""Grid of RES metres in CRS ('auto' = WGS 84 / UTM of the centre) that covers REGIONS."""
	geom = regions.geometry()
	if str(crs).lower() == 'auto':
		lon, lat = geom.centroid(1).coordinates().getInfo()
		crs = areas.utm_of(lon, lat)
	ring = geom.bounds(res, crs).getInfo()['coordinates'][0]
	xs, ys = [p[0] for p in ring], [p[1] for p in ring]
	return Grid.around(crs, res, min(xs), min(ys), max(xs), max(ys))


def _file_stem(variable, sensor, metric, start, end, source):
	return f"{variable or source.get('collection') or source.get('image')}_{sensor or ''}_{metric}_{start}_{end}"


def download_image(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                   interannual='mean', season=None, quality=None, resolution=None, crs='auto', path=None, clip=True,
                   max_pixels=None, tile=512, workers=8, progress=None, **source):
	"""Download the map of a variable over REGION to the GeoTIFF PATH (float32, NoData -9999) on a grid of RESOLUTION
	metres (default: that of the data) in CRS ('auto' = WGS 84 / UTM of the centre of the region), directly: Earth
	Engine computes it in tiles of TILE pixels, WORKERS at a time (PROGRESS(done, total) after each one). With
	MAX_PIXELS, a grid with more pixels gets a pixel 2, 3, ... times bigger. Fine for small regions; for big ones at
	full resolution, export_image (Google Drive).
	Returns {'file', 'grid', 'resolution', 'native_resolution' (that of the data), 'images', 'name', 'unit', 'min',
	'max' (percentiles 5 and 95 of the values, as the maps of MonitorEO), 'palette'}."""
	spec = make_spec(variable, sensor, start, end, metric=metric, temporal=temporal, interannual=interannual,
	                 season=season, quality=quality, **source)
	regions = areas.region(region)
	native = float(variables.native_scale(spec))
	grid, res = _fit_grid(regions, float(resolution or native), crs, max_pixels)
	img = variables.image(spec, regions.geometry(), res)
	if clip:
		img = img.clipToCollection(regions)
	path = path or _slug(_file_stem(variable, sensor, metric, start, end, source)) + '.tif'
	desc = variables.describe(spec)
	download(img, grid, path, tile=tile, workers=workers, progress=progress,
	         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(desc, default=str)})
	vmin, vmax = _percentiles(path)
	return {'file': path, 'grid': grid.describe(), 'resolution': res, 'native_resolution': native,
	        'images': variables.n_images(spec, regions.geometry()), 'name': _title(spec) + f' ({metric})',
	        'unit': _unit(spec), 'min': vmin, 'max': vmax, 'palette': maps.ramp(variable_entry(spec))}


def _fit_grid(regions, res, crs, max_pixels=None):
	"""(grid, pixel size) of REGIONS: pixels of RES m, or 2, 3, ... times bigger if the grid has more than MAX_PIXELS."""
	grid = _grid(regions, res, crs)
	if max_pixels and grid.pixels > max_pixels:
		res *= math.ceil(math.sqrt(grid.pixels / max_pixels))
		grid = _grid(regions, res, grid.crs)
	return grid, res


def _percentiles(path, lo=5, hi=95, band=1):
	"""Percentiles LO and HI of the valid values of a band of a GeoTIFF (None, None if it has none)."""
	import numpy as np
	from osgeo import gdal
	gdal.UseExceptions()
	ds = gdal.Open(path)
	band = ds.GetRasterBand(band)
	a = band.ReadAsArray()
	a = a[(a != band.GetNoDataValue()) & np.isfinite(a)]
	ds = None
	if not a.size:
		return None, None
	return float(np.percentile(a, lo)), float(np.percentile(a, hi))


def download_variables(recipe, area, folder, layer=None, buffer=None, only=None, dry_run=False, overwrite=False,
                       drive_all=False, drive_dir=None, wait=True, record=recipes.RECORD, tile=512, workers=8, log=None,
                       progress=None):
	"""Download the variables of RECIPE (a dictionary or a YAML file, see monitoreo.recipe: variables with one or
	several metrics, period, pixel filters and pixel sizes) as GeoTIFFs on aligned grids over the study AREA (a vector
	file, or a region such as {'wdpa_id': 555513}) in FOLDER and, if the recipe has ecoregion: resolution, over the
	ecoregions of RESOLVE 2017 that it touches in FOLDER/ecoregion. Running it again downloads only what changed
	(OVERWRITE: everything) and imports the finished exports to Google Drive (WAIT: wait for them). DRY_RUN: only the
	plan and the number of images. LOG(message) and PROGRESS(file, done, total) follow it.
	Returns {'area', 'grids', 'ecoregions', 'files', ...} and, unless DRY_RUN, {'done', 'folders', 'pending',
	'in_drive', 'failed'}."""
	log = log or recipes._quiet
	p = recipes.plan(recipe, area, layer, buffer, only, warn=log)
	out = p.summary()
	if dry_run:
		images = recipes.n_images(p)
		for f in out['files']:
			f['images'] = images[f['file']]
		return out
	res = recipes.run(p, folder, record, overwrite, drive_all, drive_dir, wait=wait, tile=tile, workers=workers,
	                  project=_project or p.recipe.get('project'), log=log, progress=progress)
	out.update({k: v for k, v in res.items() if k != 'files'})
	return out


# Seasonal trends and comparison of periods ---------------------------------------------------------------------------

def _seasonal_rows(spec, regions, step, metric, stat, scale, progress):
	"""Regional values of each part of the year of STEP in each year: ([{region, part, year, date, value, n_pixels,
	n_images}], scale)."""
	bins = trends.seasonal_bins(spec, step)
	part_year = {a: (p, y) for p, y, a, _ in bins}
	rows, used = timeseries.series(spec, regions, step, metric, stat, scale, progress,
	                               steps=[(a, b) for _, _, a, b in bins])
	for r in rows:
		r['part'], r['year'] = part_year[r['date']]
	return rows, used


def _part(step, part):
	"""The part of the year to map: PART, or the year for 'annual'."""
	if step == 'annual':
		return 0
	if part is None or int(part) not in trends.parts(step):
		raise ValueError(f"give the part of the year: 1-12 (monthly) or 1-23 (16-day), not {part}")
	return int(part)


TREND_COLUMNS = ['region', 'key', 'label', 'n', 'tau', 'z', 'p_value', 'significant', 'slope', 'intercept',
                 'first_year', 'last_year']
COMPARISON_COLUMNS = ['region', 'key', 'label', 'reference', 'other', 'difference', 'n_reference', 'n_other']


def trend_table(region, variable=None, sensor=None, start=None, end=None, step='annual', metric='mean', stat='mean',
                season=None, quality=None, scale=None, alpha=0.05, csv=None, chart=None, progress=None, **source):
	"""Seasonal trends of a variable over each feature of REGION (see monitoreo.trends): the spatial STAT of the
	METRIC of each part of the year of STEP ('monthly': 12 months, '16-day': 23 parts of 16 days, 'annual': the
	year) in each year, and the trend of each part over the years (Mann-Kendall tau, Z and p-value, Sen's slope per
	year). Writes the trends to CSV and the chart of the yearly values with their Sen lines to CHART if given.
	Returns {'rows': [{region, part, key, label, n, tau, z, p_value, significant (p < ALPHA), slope, intercept,
	first_year, last_year}], 'yearly': [{region, part, year, value, n_pixels, n_images}], 'csv', 'chart', 'scale',
	'unit', 'title'}."""
	spec = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	regions = areas.region(region)
	yearly, used = _seasonal_rows(spec, regions, step, metric, stat, scale, progress)
	first = composite.windows(spec['period'], spec['season'])[0][0]
	rows = trends.trend_rows(yearly, step, first, alpha=alpha)
	unit = _unit(spec)
	title = _title(spec) + f' | trends of the {step} {metric}, spatial {stat}'
	out = {'rows': rows, 'yearly': yearly, 'csv': None, 'chart': None, 'scale': used, 'unit': unit, 'title': title}
	if csv:
		meta = {'variable': variable or source.get('collection') or source.get('image'), 'sensor': sensor or '',
		        'step': step, 'metric': metric, 'stat': stat, 'unit': unit, 'slope_unit': f'{unit} / year',
		        'scale_m': used}
		out['csv'] = timeseries.write_csv(rows, csv, meta, TREND_COLUMNS)
	if chart and any(r['slope'] is not None for r in rows):
		try:
			charts.trends_png(yearly, rows, chart, title=title, ylabel=unit or None)
			out['chart'] = chart
		except ImportError:  # no matplotlib
			pass
	return out


def _trend(region, variable, sensor, start, end, step, part, metric, season, quality, alpha, res, source):
	spec = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	regions = areas.region(region)
	part = _part(step, part)
	native = float(variables.native_scale(spec))
	img = trends.trend_image(spec, regions.geometry(), res or native, step, part, metric)
	if alpha:
		img = img.updateMask(img.select('p_value').lt(alpha))
	name = f"{_title(spec)} | trend {trends.part_key(step, part)} ({metric})"
	return spec, regions, img.clipToCollection(regions), part, native, name


def trend_map(region, variable=None, sensor=None, start=None, end=None, step='annual', part=None, output='slope',
              metric='mean', season=None, quality=None, alpha=None, vmin=None, vmax=None, palette=None,
              thumbnail=None, **source):
	"""Map of the trend of a part of the year (PART: month 1-12 with STEP 'monthly', 1-23 with '16-day', none with
	'annual') of a variable over REGION, computed on each pixel: OUTPUT is 'slope' (Sen, per year), 'tau', 'z',
	'p_value', 'intercept' or 'n' (years with data); ALPHA (e.g. 0.05) leaves only the pixels with p_value < ALPHA.
	Earth Engine tiles (the values cannot be queried: download_trend for that).
	Returns {'url', 'min', 'max', 'palette', 'name', 'unit', 'bounds', 'thumbnail'}."""
	if output not in trends.OUTPUTS:
		raise ValueError(f"unknown output {output}: use {', '.join(trends.OUTPUTS)}")
	spec, regions, img, part, native, name = _trend(region, variable, sensor, start, end, step, part, metric, season,
	                                                quality, alpha, None, source)
	band = img.select(output)
	vis = trends.vis(output)
	if vis is None or (output in ('slope', 'z', 'n') and (vmin is None or vmax is None)):
		auto = maps.vis_params(band.rename('value'), regions.geometry(), variable_entry(spec), native)
		vis = trends.vis(output, auto['min'], auto['max']) or auto
	vis = dict(vis, **({'min': vmin} if vmin is not None else {}), **({'max': vmax} if vmax is not None else {}))
	if palette:
		vis['palette'] = maps.ramp(None, palette)
	unit = _unit(spec)
	out = dict(vis, url=maps.tile_url(band, vis), name=f'{name}: {output}', bounds=_bounds(regions), thumbnail=None,
	           unit=f'{unit} / year' if output == 'slope' else unit if output == 'intercept' else '')
	if thumbnail:
		maps.thumbnail(maps.with_outline(band, vis, regions), regions.geometry().bounds(), None, path=thumbnail)
		out['thumbnail'] = thumbnail
	return out


def download_trend(region, variable=None, sensor=None, start=None, end=None, step='annual', part=None, metric='mean',
                   season=None, quality=None, alpha=None, resolution=None, crs='auto', path=None, max_pixels=None,
                   tile=512, workers=8, progress=None, **source):
	"""Download the trend of a part of the year of a variable over REGION (see trend_map) to the GeoTIFF PATH, with a
	band per output: slope, tau, z, p_value, intercept, n (NoData -9999 where there are fewer than 2 years or, with
	ALPHA, p_value >= ALPHA), on a grid of RESOLUTION metres (default: that of the data; 2, 3, ... times bigger if
	the grid has more than MAX_PIXELS).
	Returns {'file', 'bands', 'grid', 'resolution', 'native_resolution', 'name', 'unit' (of the slope), 'min', 'max'
	(symmetric range of the slope), 'palette'}."""
	regions_ = areas.region(region)
	spec0 = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	native = float(variables.native_scale(spec0))
	grid, res = _fit_grid(regions_, float(resolution or native), crs, max_pixels)
	spec, regions, img, part, native, name = _trend(regions_, variable, sensor, start, end, step, part, metric, season,
	                                                quality, alpha, res, source)
	path = path or _slug(f"trend_{_file_stem(variable, sensor, metric, start, end, source)}_{trends.part_key(step, part)}") + '.tif'
	download(img, grid, path, tile=tile, workers=workers, progress=progress, bands=list(trends.OUTPUTS),
	         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(dict(
	             variables.describe(spec), trend=step, part=trends.part_key(step, part), alpha=alpha), default=str)})
	lo, hi = _percentiles(path)
	vis = trends.vis('slope', lo, hi)
	return dict(vis, file=path, bands=list(trends.OUTPUTS), grid=grid.describe(), resolution=res,
	            native_resolution=native, name=name, unit=f'{_unit(spec)} / year')


def compare_series(region, variable=None, sensor=None, start=None, end=None, other_start=None, other_end=None,
                   step='monthly', metric='mean', stat='mean', season=None, quality=None, scale=None, csv=None,
                   chart=None, progress=None, **source):
	"""Comparison of a reference period (START to END) with another (OTHER_START to OTHER_END) over each feature of
	REGION: the spatial STAT of the METRIC of each part of the year of STEP ('monthly', '16-day' or 'annual') in each
	year of both periods, and the mean of each part in each period and their difference (other - reference). Writes
	the comparison to CSV and the chart of both periods by part of the year to CHART if given.
	Returns {'profile': [{region, part, key, label, reference, other, difference, n_reference, n_other}], 'rows':
	[{period ('reference' or 'other'), region, part, year, date, value, n_pixels, n_images}], 'csv', 'chart',
	'scale', 'unit', 'title', 'periods': {'reference': [first, last day], 'other': [...]}, 'names' (short names
	of both periods, e.g. 2018-2021)}."""
	if not other_start or not other_end:
		raise ValueError('give the other period: other_start and other_end')
	ref = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	oth = make_spec(variable, sensor, other_start, other_end, metric=metric, season=season, quality=quality, **source)
	regions = areas.region(region)
	scale = scale or timeseries.auto_scale(ref, regions)
	ref_rows, _ = _seasonal_rows(ref, regions, step, metric, stat, scale, progress)
	oth_rows, _ = _seasonal_rows(oth, regions, step, metric, stat, scale, progress)
	for rows, name in ((ref_rows, 'reference'), (oth_rows, 'other')):
		for r in rows:
			r['period'] = name
	profile = trends.profile(ref_rows, oth_rows)
	for r in profile:
		r['key'], r['label'] = trends.part_key(step, r['part']), trends.part_label(step, r['part'])
	unit = _unit(ref)
	title = (f"{_title(dict(ref, period=None))} | {ref['period'][0]} / {ref['period'][1]} vs "
	         f"{oth['period'][0]} / {oth['period'][1]} | {step} {metric}, spatial {stat}")
	names = tuple(a[:4] if a[:4] == b[:4] else f'{a[:4]}-{b[:4]}' for a, b in (ref['period'], oth['period']))
	out = {'profile': profile, 'rows': ref_rows + oth_rows, 'csv': None, 'chart': None, 'scale': scale, 'unit': unit,
	       'title': title, 'periods': {'reference': ref['period'], 'other': oth['period']}, 'names': names}
	if csv:
		meta = {'variable': variable or source.get('collection') or source.get('image'), 'sensor': sensor or '',
		        'reference': '/'.join(ref['period']), 'other': '/'.join(oth['period']), 'step': step,
		        'metric': metric, 'stat': stat, 'unit': unit, 'scale_m': scale}
		out['csv'] = timeseries.write_csv(profile, csv, meta, COMPARISON_COLUMNS)
	if chart and any(r['reference'] is not None or r['other'] is not None for r in profile):
		try:
			labels = {r['part']: (r['label'][:3] if step == 'monthly' else r['key']) for r in profile}
			charts.comparison_png(profile, labels, chart, title=title, ylabel=unit or None, names=names)
			out['chart'] = chart
		except ImportError:  # no matplotlib
			pass
	return out


def _comparison(region, variable, sensor, start, end, other_start, other_end, metric, temporal, interannual, season,
                quality, res, source):
	if not other_start or not other_end:
		raise ValueError('give the other period: other_start and other_end')
	ref = make_spec(variable, sensor, start, end, metric=metric, temporal=temporal, interannual=interannual,
	                season=season, quality=quality, **source)
	oth = make_spec(variable, sensor, other_start, other_end, metric=metric, temporal=temporal,
	                interannual=interannual, season=season, quality=quality, **source)
	regions = areas.region(region)
	native = float(variables.native_scale(ref))
	geom = regions.geometry()
	a = variables.image(ref, geom, res or native)
	b = variables.image(oth, geom, res or native)
	img = ee.Image.cat([b.subtract(a), a, b]).rename(['difference', 'reference', 'other']).clipToCollection(regions)
	name = (f"{_title(dict(ref, period=None))} ({metric}) | {oth['period'][0]} / {oth['period'][1]} - "
	        f"{ref['period'][0]} / {ref['period'][1]}")
	return ref, regions, img, native, name


def compare_map(region, variable=None, sensor=None, start=None, end=None, other_start=None, other_end=None,
                metric='median', temporal='period', interannual='mean', season=None, quality=None, vmin=None,
                vmax=None, palette=None, thumbnail=None, **source):
	"""Map of the difference between the variable aggregated in time over another period (OTHER_START to OTHER_END)
	and over the reference period (START to END), over REGION (e.g. the median NDVI of 2023 minus that of
	2018-2021). Earth Engine tiles (the values cannot be queried: download_comparison for that).
	Returns {'url', 'min', 'max', 'palette', 'name', 'unit', 'bounds', 'thumbnail'}."""
	spec, regions, img, native, name = _comparison(region, variable, sensor, start, end, other_start, other_end, metric,
	                                               temporal, interannual, season, quality, None, source)
	diff = img.select('difference')
	if vmin is None or vmax is None:
		auto = maps.vis_params(diff.rename('value'), regions.geometry(), None, native)
		vis = trends.vis('difference', auto['min'], auto['max'])
	else:
		vis = {'min': vmin, 'max': vmax, 'palette': trends.DIVERGING}
	if palette:
		vis['palette'] = maps.ramp(None, palette)
	out = dict(vis, url=maps.tile_url(diff, vis), name=f'{name}: difference', unit=_unit(spec),
	           bounds=_bounds(regions), thumbnail=None)
	if thumbnail:
		maps.thumbnail(maps.with_outline(diff, vis, regions), regions.geometry().bounds(), None, path=thumbnail)
		out['thumbnail'] = thumbnail
	return out


def download_comparison(region, variable=None, sensor=None, start=None, end=None, other_start=None, other_end=None,
                        metric='median', temporal='period', interannual='mean', season=None, quality=None,
                        resolution=None, crs='auto', path=None, max_pixels=None, tile=512, workers=8, progress=None,
                        **source):
	"""Download the comparison of two periods (see compare_map) to the GeoTIFF PATH, with the bands 'difference'
	(other - reference), 'reference' and 'other' (NoData -9999), on a grid of RESOLUTION metres (default: that of the
	data; 2, 3, ... times bigger if the grid has more than MAX_PIXELS).
	Returns {'file', 'bands', 'grid', 'resolution', 'native_resolution', 'name', 'unit', 'min', 'max' (symmetric
	range of the difference), 'palette'}."""
	regions_ = areas.region(region)
	spec0 = make_spec(variable, sensor, start, end, metric=metric, temporal=temporal, interannual=interannual,
	                  season=season, quality=quality, **source)
	grid, res = _fit_grid(regions_, float(resolution or variables.native_scale(spec0)), crs, max_pixels)
	spec, regions, img, native, name = _comparison(regions_, variable, sensor, start, end, other_start, other_end,
	                                               metric, temporal, interannual, season, quality, res, source)
	path = path or _slug(f"comparison_{variable or source.get('collection')}_{sensor or ''}_{metric}_{start}_{end}_"
	                     f"{other_start}_{other_end}") + '.tif'
	bands = ['difference', 'reference', 'other']
	download(img, grid, path, tile=tile, workers=workers, progress=progress, bands=bands,
	         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(dict(
	             variables.describe(spec), reference=[start, end], other=[other_start, other_end]), default=str)})
	lo, hi = _percentiles(path)
	vis = trends.vis('difference', lo, hi)
	return dict(vis, file=path, bands=bands, grid=grid.describe(), resolution=res, native_resolution=native, name=name,
	            unit=_unit(spec))


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
