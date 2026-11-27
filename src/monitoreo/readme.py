"""Documentation of the files that MonitorEO writes, so that each one explains itself (as the guide of data management
of the British Ecological Society asks: what each column or band is, with its unit and missing values, how it was
computed, with which version and when, how to reproduce it and how to cite it):

  - a README next to the files of each result (<file>.README.txt), plain text: title, how it was computed, the columns
    of its CSV or the bands of its GeoTIFF, to reproduce it in Python and the references to cite;
  - the metadata of its GeoTIFFs: the call that made it (call), the version of MonitorEO (monitoreo_version), when it
    was computed (computed, ISO 8601), the references, and the name and unit of each band;
  - README.txt in each folder of a recipe (monitoreo.recipe), with every file, from the record of the folder;
  - the parameters of the analysis as JSON (<file>.parameters.json, see monitoreo.parameters), to repeat it in any tool.

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
# outputs that are part of what was computed: a file whose name the call keeps (without its folder), so that the call to
# reproduce it writes it again (the perimeter of the burned area of burn_severity)
NAMED_OUTPUTS = {'perimeter'}

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
	'z': 'Z of the trend test (column test; Mann-Kendall: normal approximation, without correction for ties)',
	'p_value': 'two-sided p-value of the trend test (column test)',
	'significant': 'p_value below alpha (True or False)',
	'slope': "Sen's slope: change of the variable per year{uy}",
	'intercept': 'value of the Sen line in the first year{u}',
	'first_year': 'first year of the period',
	'last_year': 'last year of the period',
	'n_ratio': 'test hamed-rao: n/n*, the factor of the variance of the Mann-Kendall S for the autocorrelation of the '
	           'ranks of the yearly values without their trend (1: not corrected; empty with the other tests)',
	'r1': 'test tfpw: lag-1 autocorrelation of the yearly values without their trend, removed before the test (empty '
	      'with the other tests)',
	'test': 'trend test: mk (Mann-Kendall), hamed-rao (Mann-Kendall modified by Hamed and Rao, 1998) or tfpw '
	        '(Mann-Kendall with trend-free pre-whitening, Yue et al., 2002)',
	'reference': 'mean of the part of the year over the years of the reference period{u}',
	'other': 'mean of the part of the year over the years of the other period{u}',
	'difference': 'other - reference{u}',
	'n_reference': 'years with data in the reference period',
	'n_other': 'years with data in the other period',
	'class': 'severity class of the USGS (-2 enhanced regrowth, high; -1 enhanced regrowth, low; 0 unburned; 1 low; '
	         '2 moderate-low; 3 moderate-high; 4 high)',
	'dnbr_min': 'lowest dNBR of the class',
	'dnbr_max': 'highest dNBR of the class (empty: no limit)',
	'rdnbr_min': 'lowest RdNBR of the class (empty: no limit)',
	'rdnbr_max': 'highest RdNBR of the class (empty: no limit)',
	'ha': 'hectares',
	'mean': 'mean{u}', 'median': 'median{u}', 'std': 'standard deviation{u}', 'min': 'minimum{u}', 'max': 'maximum{u}',
	'cv': 'coefficient of variation (%): 100 × standard deviation / mean; empty where the mean is 0',
	'p5': 'percentile 5{u}', 'p10': 'percentile 10{u}', 'p25': 'percentile 25{u}', 'p50': 'percentile 50{u}',
	'p75': 'percentile 75{u}', 'p90': 'percentile 90{u}', 'p95': 'percentile 95{u}',
	'mode': 'most frequent value{u}; of a categorical layer, the majority class (the code of the class of most of the '
	        'pixels)',
	'mode_label': 'the majority class: its code and name',
	'count': 'number of valid pixels',
	'group': 'group of the class: the code of the biome of the ecoregion',
	'group_label': 'the biome of the ecoregion: its code and name',
	# what each row was made with
	'variable': 'variable of the catalog of MonitorEO (or the Earth Engine source)',
	'sensor': 'sensor',
	'step': 'time step', 'metric': 'temporal metric of the images', 'stat': 'spatial statistic over the feature',
	'unit': 'unit of the variable in UDUNITS (1: dimensionless)', 'slope_unit': 'unit of the slope in UDUNITS',
	'scale_m': 'pixel size of the computation (m)',
	'reference_period': 'reference period (first/last day)', 'other_period': 'other period (first/last day)',
	'before': 'period before the fire (first/last day)', 'after': 'period after the fire (first/last day)',
	'index': 'burn index',
	'percent': '% of the area of the feature with a class (the pixels without data are not counted)',
	'landcover': 'broad land cover of the class (that of the land cover masks: water, trees, grassland, wetland, '
	             'cropland, shrubland, built, bare or snow)',
	'map': 'land cover map',
	'value_from': 'lowest value of the class{u} (empty: no limit)',
	'value_to': 'value where the class ends, not in it{u} (empty: no limit)',
	'period': 'period of the data (first/last day)',
	'year': 'year of the first day of the step', 'doy': 'day of the year (1-366) of the first day of the step',
	'other_year': 'the other year of the land cover map', 'from_class': 'class of the map in the first year (code)',
	'from_label': 'name of the class in the first year', 'from_landcover': 'broad land cover of the class in the first year',
	'to_class': 'class of the map in the other year (code)', 'to_label': 'name of the class in the other year',
	'to_landcover': 'broad land cover of the class in the other year',
	'zone': 'zone: its number from 0 (below the first break of the variable of the zones)',
	'zone_label': 'name of the zone (its values of the variable of the zones)',
	'zone_from': 'lowest value of the variable of the zones in the zone{zu} (empty: no limit)',
	'zone_to': 'value of the variable of the zones where the zone ends, not in it{zu} (empty: no limit)',
	'distance_m': 'distance along the line to the middle of the segment (m)',
	'lon': 'longitude of the middle of the segment (degrees, WGS 84)', 'lat': 'latitude of the middle of the segment '
	                                                                       '(degrees, WGS 84)',
	'elevation': 'mean elevation of the segment (m, Copernicus DEM GLO-30)',
}
# the columns of the CSV of area_by_class that differ (its year is that of the land cover map, not of a step)
COLUMNS_AREAS = {
	'class': 'class: its code in the land cover map; for the classes of a variable, its number from 0 (below the first '
	         'break); for a trend, -1 (significant decrease), 0 (no significant trend) or 1 (significant increase); for '
	         'a categorical layer, its code (ECO_ID of the ecoregions, BIOME_NUM of the biomes; Rock and Ice, 99)',
	'label': 'name of the class', 'year': 'year of the land cover map',
	'ha': 'hectares of the class in the feature (true area of its pixels)',
}
# the columns of region_stats with the zones of a categorical layer (its classes) that differ
COLUMNS_CLASS_ZONES = {
	'zone': 'zone: the code of its class in the categorical layer of the zones',
	'zone_label': 'name of the zone: the code and name of its class',
	'zone_from': 'empty (the zones are classes, not values)', 'zone_to': 'empty (the zones are classes, not values)',
}
# the columns of the CSV of the changes of a land cover map (area_by_class with other_year) that differ from those of
# COLUMNS_AREAS
COLUMNS_TRANSITIONS = {
	'year': 'first year of the land cover map (that of from_class)',
	'other_year': 'other year of the land cover map (that of to_class)',
	'ha': 'hectares of the pixels of the feature with from_class in year and to_class in other_year (true area of its '
	      'pixels)',
	'percent': '% of the area of the feature with a class in both years (the pixels without data in either year are '
	           'not counted)',
}
# the fields of the vector file of the perimeter of the burned area (burn_severity with perimeter: fire.PERIMETER_TYPES)
FIELDS = {
	'region': 'name of the feature of the region (its name, or its number)',
	'ha': 'area of the polygons, in hectares (UDUNITS ha), computed on the grid of the pixels',
	'patches': 'burned patches of the feature: groups of burned pixels joined by a side or a corner (count)',
	'index': 'burn index (dNBR, RBR or RdNBR)',
	'burned_min': 'value of the index from which a pixel is burned (dimensionless, UDUNITS 1)',
	'min_ha': 'smallest burned patch kept and smallest unburned island left as a hole, in hectares (UDUNITS ha)',
	'sensor': 'sensor of the images',
	'before': 'period before the fire (first/last day)',
	'after': 'period after the fire (first/last day)',
}
# the files of polygons that the tools write (areas.VECTOR_DRIVERS)
VECTOR_KINDS = {'.gpkg': 'polygons (GeoPackage, EPSG:4326, layer perimeter)', '.geojson': 'polygons (GeoJSON, EPSG:4326)',
                '.shp': 'polygons (Shapefile, EPSG:4326, with its .shx, .dbf and .prj)'}
# the animations (services.timelapse)
ANIMATION_KINDS = {'.gif': 'animation (GIF), a frame per time step', '.mp4': 'animation (MP4 video, H.264), a frame '
                                                                          'per time step'}
# the columns of the CSV of the seasonal profile by day of the year (time_series with doy and interannual or
# other_variable: timeseries.PROFILE_COLUMNS and PROFILE_META) that differ ({i}: the metric between the years)
COLUMNS_PROFILE = {
	'region': 'name of the feature of the region (its name, or its number); those of the same name are numbered from '
	          'the second one, e.g. Sierra Nevada (2)',
	'variable': 'variable of the line: its name and sensor (e.g. NDVI Sentinel-2); the first one on the left y axis of '
	            'the chart, the other one on the right y axis',
	'part': 'step of the year: the month (1-12) with a monthly step (in a season that starts and ends in the same '
	        'month, the part of that month from the first day of the season is MM-DD, e.g. 10-15); the number of the '
	        '16-day period from 1 January, or from the first day of the season (0, 1, 2, ...), the closest one to the '
	        'first day of the step, with a 16-day step; the calendar day (MM-DD) with a daily step',
	'doy': 'day of the year (1-366) where the step is drawn: monthly, the median of the days of the year of its first '
	       'day in the years; 16-day, that of its first day in a year of 365 days; daily, that of the calendar day in a '
	       'year of 366 days (29 February is 60, 1 March 61)',
	'label': 'name of the step of the year: Jan to Dec (Oct 1-14 and Oct 15-31 for the two parts of a month), or a day '
	         '(e.g. Jan 17) in a year of 365 days',
	'value': '{i} of the values of the step in the years of the period{u}: each one the spatial statistic, over the '
	         'feature, of the temporal metric of the images of the step on each pixel',
	'n_years': 'years with a value in the step (0: no value in any year, value empty)',
	'interannual': 'metric between the years of each step of the year',
	'unit': 'unit of the variable of the row in UDUNITS (1: dimensionless)',
	'scale_m': 'pixel size of the computation of the variable of the row (m)',
	'sensor': 'sensor of the variable of the row',
}
# the columns of the CSV of the RdNBR (burn_severity with index RdNBR, a CSV with the column rdnbr_min) that differ
COLUMNS_RDNBR = {
	'class': 'severity class of Miller & Thode 2007, their Table 4 (0 unchanged; 1 low; 2 moderate; 3 high)',
	'label': 'name of the severity class',
}
BANDS = dict({'value': ('Value of the variable', '{u}')}, **publish.BANDS)
# the unit of each band in UDUNITS ({u}: that of the variable); the others are dimensionless ('1')
BAND_UDUNITS = {'value': '{u}', 'slope': '{u} year-1', 'intercept': '{u}', 'difference': '{u}', 'reference': '{u}',
                'other': '{u}'}


def _now():
	return dt.datetime.now().astimezone().isoformat(timespec='seconds')


def call_args(args):
	"""The arguments of a call that say what was computed (without its outputs and callbacks, nor those left empty)."""
	return {k: os.path.basename(v) if k in NAMED_OUTPUTS and isinstance(v, str) else v for k, v in (args or {}).items()
	        if k not in NOT_ARGS and v is not None and not callable(v) and v != {} and v != []}


def _catalog_unit(result, args):
	"""The unit of the catalog ('[°C]') of the variable of a result."""
	unit = str((result or {}).get('unit') or '').replace('/ year', '').strip()
	if not unit and args.get('variable'):
		try:
			from . import catalog
			unit = catalog.unit_of(catalog.find(args['variable'], args.get('sensor'), args.get('collection'))['unit'],
			                       *_metrics(args))
		except (KeyError, ValueError):
			unit = ''
	return unit


def _metrics(args):
	"""The metric of the images, the metric between the years (if the images are aggregated by years) and the
	statistic over the region of a call (see catalog.unit_of). A fixed layer (elevation, slope, an image) has no
	images: the metrics of the call, which the services ignore, are not those of its values."""
	if publish.is_static(args):
		return None, None, args.get('stat')
	between = args.get('interannual') if (args.get('temporal') or 'period') != 'period' else None
	return args.get('metric'), between, args.get('stat')


def _unit(result, args):
	"""The unit of the variable of a result as shown ('°C', '' if dimensionless)."""
	return publish.unit_text(_catalog_unit(result, args))


def _udunits(result, args):
	"""The unit of the variable of a result in UDUNITS ('degC', '1'), or '' if unknown."""
	from . import catalog
	return catalog.udunits(_catalog_unit(result, args))


def categorical_entry(args):
	"""The catalog entry of the variable of a call when it is a categorical layer (class codes, see
	monitoreo.categorical), else None."""
	from . import catalog, categorical
	if not args.get('variable'):
		return None
	try:
		e = catalog.find(args['variable'], args.get('sensor'), args.get('collection'))
	except (KeyError, ValueError, TypeError):
		return None
	return e if categorical.is_categorical(e) else None


def classes_text(entry):
	"""What the values of the categorical layer ENTRY are, for the READMEs: «class codes of ..., without a unit»."""
	from . import categorical
	t = categorical.of(entry)
	return (f"The values are class codes, not quantities: the {t['property']} of the {t['name']}, without a unit (no "
	        'UDUNITS unit: the bands of the GeoTIFF and the column unit of the CSV have none, as the flag values of '
	        'the CF conventions). Each code is a class, named in the classes of the files.')


def _zone_unit(args):
	"""The unit of the variable of the zones of a call of region_stats (zone_from, zone_to), as shown and in UDUNITS,
	e.g. ' (m; UDUNITS m)', or '' without zones."""
	z = args.get('zones')
	if not isinstance(z, dict):
		return ''
	zargs = {'variable': z.get('variable') or z.get('index'), 'sensor': z.get('sensor'), 'collection': z.get('collection'),
	         'metric': z.get('metric') or 'mean', 'temporal': z.get('temporal'),
	         'interannual': z.get('interannual') or 'mean'}
	ud = _udunits(None, zargs)
	return f" ({_unit(None, zargs) or 'dimensionless'}; UDUNITS {ud})" if ud else ''


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

	from . import areas
	gdal.UseExceptions()
	ds = gdal.Open(path)
	srs = osr.SpatialReference(wkt=ds.GetProjection()) if ds.GetProjection() else None
	# a CRS without a code (one given by its WKT, as areas.GLOBAL_CRS) by the code of the same CRS, else by its name
	crs = (areas.crs_code(srs) or srs.GetName() or 'unknown CRS') if srs is not None else 'unknown CRS'
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
	if categorical_entry(args) and isinstance(result.get('classes'), list):  # what each code of a categorical layer is
		ds.SetMetadataItem('classes', json.dumps({str(c['value']): c['label'] for c in result['classes']
		                                          if isinstance(c, dict) and 'value' in c}, ensure_ascii=False))
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
	files = _files(result, ('file', 'gif', 'csv', 'chart', 'perimeter'))
	name = os.path.basename(files[0]) if files else tool
	title = report.item_title(tool, given, result)
	out = [f'README of {name}', '=' * min(WIDTH, len(f'README of {name}')), '', title,
	       _wrap(f'Computed with MonitorEO {__version__} in Google Earth Engine on {computed or _now()}.', '', '')]
	out += _section('Files')
	figure = 'figure of the map ({}), with its grid, scale bar, north arrow, colour ramp and credits'
	kinds = {'.csv': 'table (CSV, UTF-8, comma-separated, a header row)',
	         '.tif': f'map (GeoTIFF, float32, NoData {NODATA})', '.png': 'chart (PNG)', **VECTOR_KINDS,
	         **ANIMATION_KINDS, **({'.png': figure.format('PNG'), '.pdf': figure.format('PDF'),
	                                '.svg': figure.format('SVG')} if tool == 'map_figure' else {})}
	if result.get('mode') == 'transitions':  # the changes of a land cover map: the Sankey diagram of its first feature
		regions = list(result.get('changed_ha') or {})
		kinds['.png'] = 'Sankey diagram (PNG) of the changes of the broad land covers' + \
			(f' of {regions[0]}, the first feature of the region' if len(regions) > 1 else '')
	out += [_wrap(f'{os.path.basename(f)}: {kinds.get(os.path.splitext(f)[1].lower(), "")}') for f in files]
	out += _section('How it was computed')
	out += [_wrap(f'{k}: {v}') for k, v in report.item_facts(tool, given, result)]
	unit, ud = _unit(result, args), _udunits(result, args)
	u, uy = (f' ({unit})' if unit else ''), f" ({unit + '/year' if unit else 'per year'})"
	zu = _zone_unit(given) if tool == 'region_stats' else ''
	profile = tool == 'time_series' and report.is_profile(given)
	between = report._interannual(given, result) if profile else None
	units = dict(result.get('units') or {}) if profile else {}
	from . import catalog
	if len(units) > 1:  # two variables, each in its unit, on its axis
		each = '; '.join(f"{name}, {publish.unit_text(un) or 'dimensionless'} (UDUNITS "
		                 f"{catalog.udunits(un) or 'unknown'})" for name, un in units.items())
		u = ' (in the unit of the variable of the row: ' + ', '.join(
			f"{name} {publish.unit_text(un) or 'dimensionless'}" for name, un in units.items()) + ')'
		out += _section('Units')
		out.append(_wrap(f'Each variable is in its own unit, on its own y axis of the chart: {each}. The column unit of '
		                 'the CSV gives that of the variable of each row, in UDUNITS (the units of the CF conventions; 1 '
		                 'is dimensionless).'))
	elif categorical_entry(given):  # class codes: no unit, but what they are
		out += _section('Values')
		out.append(_wrap(classes_text(categorical_entry(given))))
	elif ud:
		out += _section('Units')
		per_year = f"; its change per year, {band_udunits('slope', ud)}" if 'trend' in tool else ''
		what = 'The values are coefficients of variation (100 × standard deviation / mean), in %' \
			if catalog.is_cv(*_metrics(given), between) else f"The variable is {'in ' + unit if unit else 'dimensionless'}"
		where = 'The colour ramp of the animation is in this unit.' if tool == 'timelapse' else \
			'The columns unit and slope_unit of the CSV and the units of the bands of the GeoTIFF are in UDUNITS (1 is ' \
			'dimensionless).'
		out.append(_wrap(f"{what}: in UDUNITS (the units of the CF conventions), {ud}{per_year}. {where}"))
	for f in files:
		ext = os.path.splitext(f)[1].lower()
		if ext == '.csv':
			out += _section('Columns of', os.path.basename(f))
			header = _csv_header(f)
			columns = dict(COLUMNS, **COLUMNS_PROFILE) if profile and 'n_years' in header else \
				dict(COLUMNS, **COLUMNS_RDNBR) if 'rdnbr_min' in header else \
				dict(COLUMNS, **COLUMNS_CLASS_ZONES) if tool == 'region_stats' and _class_zones(given) else \
				{**COLUMNS, **COLUMNS_AREAS, **(COLUMNS_TRANSITIONS if 'from_class' in header else {})} \
				if tool == 'area_by_class' else \
				dict(COLUMNS, value='mean of the map of the variable{u} over the pixels that the segment crosses') \
				if tool == 'transect' else COLUMNS
			out += [_wrap(f'{c}: {columns.get(c, "")}'.rstrip(': ').format(u=u, uy=uy, zu=zu, i=_between_text(between)))
			        for c in header]
			out.append(_wrap('Empty cells: no data (no valid pixels or no images).'))
		elif ext in ('.tif', '.tiff'):
			bands, grid = _bands(f)
			out += _section('Bands of', os.path.basename(f))
			out.append(_wrap(f"{grid['width']} x {grid['height']} pixels of {grid['resolution']:g} m in {grid['crs']}; "
			                 f'NoData {NODATA}. Its metadata repeat the call, the version and the references.'))
			names = [b for _, b, _ in bands]
			klass = categorical_entry(given)
			for i, b, bu in bands:
				label = publish.band_text(b, names)[0] if b == 'severity' else BANDS.get(b, ('', ''))[0]
				if klass and b == 'value':  # class codes, without a unit
					label = f"Class of each pixel: its code ({klass['band']} of {klass['col']}), without a unit"
				out.append(_wrap(f'{i} {b}: {label}' + (f' ({bu})' if bu else '')))
			if klass and isinstance(result.get('classes'), list):  # the code and name of each class in the file
				out += _section('Classes of', os.path.basename(f))
				shown = [c for c in result['classes'] if isinstance(c, dict) and 'value' in c]
				out.append(_wrap(f'The {len(shown)} classes in the file, by their code (also in its metadata, item '
				                 'classes):'))
				out += [_wrap(f"{c['label']} (colour {c.get('color', '')})") for c in shown]
		elif ext in ANIMATION_KINDS and result.get('frames'):
			out += _section('Frames of', os.path.basename(f))
			out.append(_wrap('Each frame is a time step: its date (first and last day), its title and the number of '
			                 'images of the step (0: no images, the region in grey).'))
			out += [_wrap(f"{i} {fr.get('label', '')}: {fr.get('date', '')} to the day before {fr.get('end', '')}, "
			              f"{fr.get('images') if fr.get('images') is not None else '?'} images")
			        for i, fr in enumerate(result['frames'], 1)]
		elif ext in VECTOR_KINDS:
			out += _section('Fields of', os.path.basename(f))
			out.append(_wrap('The perimeter of the burned area: a feature for each feature of the region, a MultiPolygon '
			                 'of its burned pixels (without geometry if none), to use as the study area of other '
			                 f"analyses: region {{'file': '{os.path.basename(f)}', 'name_field': 'region'}}."))
			out += [_wrap(f'{k}: {v}') for k, v in FIELDS.items()]
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
	out += ['', _wrap(f'Manual of MonitorEO: {about.MANUAL}/English', '', '')] + manual_lines(args, result)
	return '\n'.join(out) + '\n'


def manual_lines(args, result=None):
	"""The lines of a README with the sections of the manual (the wiki) that explain the variables of the result (its
	manual, or those of ARGS: see monitoreo.wiki.variable_links), in English and in Spanish."""
	from . import wiki
	links = (result or {}).get('manual') if isinstance(result, dict) else None
	links = links or wiki.variable_links(args)
	return [_wrap(f"What {link['variable']} is: {link['title']}, {link['url']} (en español: {link['url_es']})", '', '  ')
	        for link in links]


def _class_zones(args):
	"""Whether the zones of a call of region_stats are the classes of a categorical layer."""
	z = args.get('zones')
	return isinstance(z, dict) and categorical_entry({'variable': z.get('variable') or z.get('index'),
	                                                  'sensor': z.get('sensor'),
	                                                  'collection': z.get('collection')}) is not None


def _between_text(metric):
	"""The metric between the years of a profile as said in the columns: 'Median', 'Percentile 25', 'Sample standard
	deviation', 'Coefficient of variation (%, 100 × sample standard deviation / |mean|)' (see timeseries.over_years)."""
	from . import report
	m = str(metric or 'median')
	text = 'coefficient of variation (%, 100 × sample standard deviation / |mean|)' if m == 'cv' else \
		'sample standard deviation' if m == 'std' else report._stat(m)
	return text[:1].upper() + text[1:]


def _files(result, keys):
	"""The files of RESULT that exist, under KEYS, each once (the GIF of an animation is also its file)."""
	out = []
	for k in keys:
		f = result.get(k)
		if isinstance(f, str) and os.path.exists(f) and f not in out:
			out.append(f)
	return out


def readme_path(path):
	"""The README of the file PATH: <file without extension>.README.txt."""
	return os.path.splitext(path)[0] + '.README.txt'


def document(tool, args, result, computed=None):
	"""Document the files of a result of TOOL (see the module): the metadata of its GeoTIFF, its README and the file of
	its parameters (its path in RESULT, 'parameters'). Returns the path of the README (or of the READMEs of the folders
	of a recipe), or None if it has no files."""
	if not isinstance(result, dict):
		return None
	computed = computed or _now()
	if tool == 'download_variables':
		folders = result.get('folders') or {}
		paths = [recipe_folder(d, result) for d in (folders.values() if isinstance(folders, dict) else folders)]
		return [p for p in paths if p] or None
	files = _files(result, ('file', 'gif', 'csv', 'perimeter'))
	if not files:
		return None
	for f in files:
		if f.lower().endswith(('.tif', '.tiff')):
			tag(f, tool, args, result, computed)
	path = readme_path(files[0])
	with open(path, 'w', encoding='utf-8') as fh:
		fh.write(text(tool, args, result, computed))
	from . import parameters  # and its parameters, to repeat it in any tool (monitoreo.parameters)
	if publish.services_call(tool, dict(args or {}))[0] in parameters.ANALYSES:
		result['parameters'] = parameters.save(tool, args, parameters.path_of(files[0]))
	return path


def _where(where):
	from . import report  # imported here: report needs the package loaded first
	return report.where_text(where)


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
		         f"class codes of the {src.get('classes_table') or src.get('classes')}, without a unit"
		         if src.get('categorical') else  # a categorical layer (ECOREGION, BIOME)
		         f"unit {src['unit']} (UDUNITS {src['udunits']})" if src.get('udunits') else
		         f"unit {src['unit']}" if src.get('unit') else '',
		         'pixels without ' + ', '.join(k for k, v in (src.get('pixel_filters') or {}).items() if v)
		         if any((src.get('pixel_filters') or {}).values()) else '',
		         f"topographic correction {src['topographic_correction']}" if src.get('topographic_correction') else '',
		         f"snow also where the NDSI (green, SWIR1) is {src['snow_ndsi']:g} or more" if src.get('snow_ndsi') else '',
		         f"water: the {src['water_filter']}" if src.get('water_filter') else '',
		         'only the pixels where ' + _where(src['where']) if src.get('where') else '',
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
	out += ['', _wrap(f'Manual of MonitorEO: {about.MANUAL}/English', '', '')] + manual_lines({}, result)
	path = os.path.join(folder, 'README.txt')
	with open(path, 'w', encoding='utf-8') as fh:
		fh.write('\n'.join(out) + '\n')
	return path
