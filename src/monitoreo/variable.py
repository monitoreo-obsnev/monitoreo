"""Earth Engine image of a variable described by a dictionary (a 'spec'), of one of three kinds:

catalog     a variable of MonitorEO: index (NDVI, LST, ...), sensor (Sentinel-2, Landsat, Modis) and, optionally,
            collection (when the catalog has several for that variable and sensor) or ref (ID of the entry).
collection  any other image collection of Earth Engine: collection and band (e.g. IDAHO_EPSCOR/TERRACLIMATE, pr),
            with optional scale and offset of the band and unit (of its values, in UDUNITS: 'mm', 'degC').
image       a fixed image (or a collection of tiles, mosaicked): image and band (e.g. COPERNICUS/DEM/GLO30, DEM),
            with optional scale, offset, unit and terrain (slope or aspect, in degrees, computed from the band). Like
            the fixed layers of the catalog, it has no dates: maps and their statistics, no time series, trends or
            comparisons.

The data of Earth Engine outside the catalog (any ID of the Earth Engine data catalog, of the GEE Community Catalog or
of a project the account can read: see monitoreo.assets) keep their own mask: the pixel filters of MonitorEO (quality)
are for the variables of the catalog.

The variables of the catalog and of other collections are aggregated in time with metric, temporal and
interannual over period and season (see composite). Other keys:
  quality            pixel filters (clouds, water, snow, aerosols) and scene filter of the catalog variables
                     (see sensors.QUALITY; by default all the pixel filters of MonitorEO)
  resample           'auto' (bilinear when the output pixels are smaller than those of the data), 'nearest',
                     'bilinear' or 'bicubic'
  aggregate          fixed images on pixels more than twice as big as theirs: 'auto' or 'mean' (mean of the
                     pixels of the data inside each output pixel) or 'none' (Earth Engine pyramids)
  exclude_landcover  classes of ESA WorldCover 2021 (10 m) set to NoData, e.g. [40, 50, 80]: crops, built-up, water
  where              the pixels of the study area to keep: a list of conditions, all of them true, each a variable of
                     the catalog aggregated over the period and season of the spec (none for the fixed layers) with
                     min and/or max, e.g. [{"variable": "ELEVATION", "sensor": "Copernicus", "min": 1500},
                     {"variable": "PRECIP", "sensor": "TerraClimate", "metric": "sum", "temporal": "annual",
                     "max": 600}]; also metric, temporal, interannual, season and quality (see where_specs)
"""

import datetime as dt
import re

import ee

from . import catalog, composite, sensors

WORLDCOVER = 'ESA/WorldCover/v200'
SENSOR_ABBR = {'Sentinel-2': 'S2', 'Landsat': 'L', 'Modis': 'MODIS'}
KEYS = {'name', 'index', 'sensor', 'collection', 'ref', 'image', 'band', 'scale', 'offset', 'unit', 'terrain',
        'metric', 'metrics', 'temporal', 'interannual', 'period', 'season', 'quality', 'resample', 'aggregate',
        'exclude_landcover', 'where'}
DEFAULTS = {'temporal': 'period', 'interannual': 'mean', 'resample': 'auto', 'aggregate': 'auto', 'quality': {},
            'season': None, 'exclude_landcover': None, 'where': None}
WHERE_KEYS = {'variable', 'sensor', 'collection', 'ref', 'metric', 'temporal', 'interannual', 'season', 'quality',
              'period',
              'min', 'max'}  # of a condition of where

_native = {}
_types = {}


def kind(spec):
	if spec.get('index'):
		return 'catalog'
	if spec.get('image'):
		return 'image'
	if spec.get('collection'):
		return 'collection'
	raise ValueError(f'variable {spec.get("name", spec)}: give index (and sensor), collection and band, or image')


def _metric_label(spec):
	m = str(spec['metric']).lower()
	if spec['temporal'] == 'period':
		return m
	return f"{spec['temporal']}-{m}_{str(spec['interannual']).lower()}"


def _default_name(spec):
	k = kind(spec)
	if k == 'catalog':
		base = f"{spec['index']}_{SENSOR_ABBR.get(spec.get('sensor'), spec.get('sensor') or '')}".rstrip('_')
	else:
		base = f"{spec.get(k).split('/')[-1]}_{spec.get('band') or ''}".rstrip('_')
		if spec.get('terrain'):
			base += '_' + spec['terrain']
	return base


def specs(var, defaults=None, two_periods=False):
	"""Specs of a variable of a recipe: one per metric of 'metric' (a metric or a list of them), with the keys
	missing in VAR taken from DEFAULTS and DEFAULTS of this module, and 'name' (a name for files: letters,
	digits, '-' and '_'). The variables of the catalog that compare two periods (RBR) only with TWO_PERIODS (the
	periods of burn_severity)."""
	unknown = set(var) - KEYS
	if unknown:
		raise ValueError(f"variable {var.get('name', var)}: unknown keys {', '.join(sorted(unknown))}")
	base = {**DEFAULTS, **{k: v for k, v in (defaults or {}).items() if k in KEYS}, **var}
	# all the quality options, so that the record of a file changes when a default changes
	base['quality'] = {**sensors.QUALITY, **((defaults or {}).get('quality') or {}), **(var.get('quality') or {})}
	unknown = set(base['quality']) - set(sensors.QUALITY)
	if unknown:
		raise ValueError(f"unknown quality options {', '.join(sorted(unknown))}: use {', '.join(sensors.QUALITY)}")
	k = kind(base)
	e = entry_of(base) if k == 'catalog' else {}
	if k == 'catalog' and base.get('unit') is not None:
		raise ValueError(f"{e['index']} ({e['sensor']}) has its unit in the catalog ({e['unit']}): unit is for the "
		                 'data of Earth Engine outside it (collection or image)')
	if k != 'catalog':
		base[k] = _asset_id(base[k])
		if not base.get('band'):
			raise ValueError(f"variable {base.get('name') or base[k]}: give the band of {base[k]} (one; describe_asset "
			                 'lists them)')
		if base.get('unit') is not None:
			base['unit'] = _udunits_text(base['unit'], base[k])
	if e.get('two_periods') and not two_periods:
		raise ValueError(f"{e['index']} ({e['sensor']}) compares a period before and a period after a fire: compute "
		                 f"it with burn_severity and index '{e['index']}'")
	if k == 'image' or e.get('static'):  # a fixed image (elevation, slope): no metric, period or season
		metrics = [None]
	else:
		metrics = base.pop('metrics', None) or base.get('metric')
		if metrics is None:
			raise ValueError(f"variable {base.get('name') or _default_name(base)}: give metric (e.g. median or [p5, p95])")
		metrics = metrics if isinstance(metrics, list) else [metrics]
		for m in metrics + ([base['interannual']] if base['temporal'] != 'period' else []):
			composite.check_metric(m)
		only = e.get('metric')  # the only metric of a variable (the SCF, a frequency, is the mean of its images)
		if only and any(str(m).strip().lower() != only for m in metrics):
			why = e.get('notes', {}).get('metric')
			raise ValueError(f"{e['index']} ({e['sensor']}) only takes the metric '{only}'{f': {why}' if why else ''}. "
			                 f"Use metric '{only}' (the metric between years, interannual, can be any)")
		if base['temporal'] not in composite.TEMPORAL:
			raise ValueError(f"unknown temporal {base['temporal']}: use {', '.join(composite.TEMPORAL)}")
		if not base.get('period'):
			raise ValueError(f'variable {base.get("name") or _default_name(base)}: give period [first day, last day]')
		composite.windows(base['period'], base['season'])
	if base.get('where'):
		where_specs(base)  # check its conditions now, without Earth Engine
	out = []
	for m in metrics:
		s = dict(base, metric=m)
		s.pop('metrics', None)
		name = var.get('name') or _default_name(s)
		if m is not None and (len(metrics) > 1 or not var.get('name')):
			name = f'{name}_{_metric_label(s)}'
		s['name'] = re.sub(r'[^A-Za-z0-9_-]', '_', str(name))
		out.append(s)
	return out


def pin_where(where, start, end):
	"""The conditions WHERE (see where_specs) with the period START to END for those that have no period of their own:
	the same pixels for a result of another period (the other period of a comparison, a map of a step of a series).
	Those of the fixed layers do not use it."""
	if not where or not start:
		return where
	conditions = [where] if isinstance(where, dict) else where
	return [dict(c, period=c.get('period') or [str(start), str(end or dt.date.today().isoformat())])
	        if isinstance(c, dict) else c for c in conditions]


def where_specs(spec):
	"""[(spec of its variable, min, max)] of each condition of SPEC['where']: the variable of the catalog aggregated
	over the period and season of SPEC (or over the period of the condition, [start, end], if it has one), with the
	metric, temporal, interannual and quality of the condition (by default the mean, or the only metric of the
	variable, of the whole period). The fixed layers (elevation, slope, WorldClim) have no period, so they can filter
	any result; a variable with dates needs a period, of the result or of the condition."""
	conditions = spec.get('where') or []
	if isinstance(conditions, dict):
		conditions = [conditions]
	out = []
	for c in conditions:
		if not isinstance(c, dict) or not c.get('variable'):
			raise ValueError('each condition of where is a dictionary with variable (and sensor), and min and/or max')
		unknown = set(c) - WHERE_KEYS
		if unknown:
			raise ValueError(f"a condition of where has unknown keys {', '.join(sorted(unknown))}: use "
			                 f"{', '.join(sorted(WHERE_KEYS))}")
		if c.get('min') is None and c.get('max') is None:
			raise ValueError(f"the condition on {c['variable']} of where needs min, max or both")
		e = catalog.find(c['variable'], c.get('sensor'), c.get('collection'), c.get('ref'))
		var = {'index': e['index'], 'sensor': e['sensor'], 'collection': c.get('collection'), 'ref': c.get('ref'),
		       'quality': c.get('quality') or {}, 'temporal': c.get('temporal') or 'period',
		       'interannual': c.get('interannual') or 'mean', 'season': c.get('season', spec.get('season'))}
		if not e.get('static'):
			period = c.get('period') or spec.get('period')
			if not period:
				raise ValueError(f"the condition on {e['index']} ({e['sensor']}) needs a period: this result has none "
				                 '(a fixed layer without dates), so give the condition its own, "period": [start, end], '
				                 'or filter by other fixed layers (ELEVATION, SLOPE, the BIO variables of WorldClim)')
			if not isinstance(period, (list, tuple)) or len(period) != 2:
				raise ValueError(f'the period of the condition on {e["index"]} is [start, end]')
			var.update(period=[str(d) for d in period], metric=c.get('metric') or e.get('metric') or 'mean')
		cs = specs({k: v for k, v in var.items() if v is not None})[0]
		out.append((cs, c.get('min'), c.get('max')))
	return out


def mask(spec, region, res):
	"""The image (1) of the pixels of SPEC that pass its conditions (where) and are not of the land covers it
	excludes (exclude_landcover), masked elsewhere; None without conditions. A pixel where a condition has no data is
	left out."""
	masks = []
	for cs, lo, hi in where_specs(spec):
		value = image(cs, region, res)
		m = ee.Image(1).updateMask(value.mask())
		if lo is not None:
			m = m.And(value.gte(float(lo)))
		if hi is not None:
			m = m.And(value.lte(float(hi)))
		masks.append(m)
	classes = spec.get('exclude_landcover')
	if classes:
		wc = ee.ImageCollection(WORLDCOVER).first()
		masks.append(wc.remap(list(classes), [0] * len(classes), 1))
	if not masks:
		return None
	out = masks[0]
	for m in masks[1:]:
		out = out.And(m)
	return out.selfMask()


def entry_of(spec):
	return catalog.find(spec['index'], spec.get('sensor'), spec.get('collection'), spec.get('ref'))


def _asset_id(asset):
	from . import assets
	return assets.normalize(asset)


def _udunits_text(unit, asset):
	"""UNIT of data of Earth Engine outside the catalog, as given (in UDUNITS: 'mm', 'degC', 'kg m-2', '1' if
	dimensionless); ValueError if it cannot be one."""
	text = ' '.join(str(unit).replace('º', '°').split())
	text = {'°C': 'degC', '°': 'degree', 'unitless': '1', 'dimensionless': '1', '': '1'}.get(text, text)
	if not catalog.UDUNITS_TEXT.fullmatch(text):
		raise ValueError(f"the unit of {asset} is written in UDUNITS (the units of the CF conventions), e.g. 'mm', "
		                 f"'degC', 'kg m-2', 'mm day-1' or '1' (dimensionless), not {unit!r}")
	return text


def is_static(spec):
	"""Whether SPEC is a fixed layer without dates: a variable of the catalog without them (elevation, slope) or an
	image of Earth Engine (kind 'image'), with maps and their statistics but no time series, trends or
	comparisons."""
	k = kind(spec)
	return k == 'image' or (k == 'catalog' and bool(entry_of(spec).get('static')))


def check_dates(spec, what='time series, trends or comparisons'):
	"""Error if SPEC is a fixed layer without dates, for WHAT needs them."""
	if kind(spec) == 'image':
		raise ValueError(f"{spec['image']} (band {spec.get('band')}) is given as a fixed image, without dates "
		                 f"(image=): it has maps, GeoTIFFs and statistics of the region (map_layer, download_image, "
		                 f"region_stats), but no {what}. A collection of images with dates is given as collection=")
	if is_static(spec):
		e = entry_of(spec)
		raise ValueError(f"{e['index']} ({e['sensor']}) is a fixed layer, without dates: it has maps, GeoTIFFs and "
		                 f"statistics of the region (map_layer, download_image, region_stats), but no {what}")


def _static_spec(spec):
	"""The spec of kind 'image' of the fixed layer of the catalog SPEC (its collection, band, terrain, scale and
	offset)."""
	e = entry_of(spec)
	if e.get('image_asset'):  # known to be an image (WorldClim): no need to ask Earth Engine
		_types[e['col']] = 'IMAGE'
	return dict(spec, image=e['col'], band=e['band'], terrain=e.get('terrain'), scale=e.get('scale'),
	            offset=e.get('offset'))  # e.g. the temperatures of WorldClim are in tenths of a degree


def _span(spec):
	wins = composite.windows(spec['period'], spec['season'])
	return wins[0][1].isoformat(), wins[-1][2].isoformat()


def check_asset(spec):
	"""Error if the data of Earth Engine of SPEC (kind 'collection' or 'image') cannot be computed as given: an ID that
	this account cannot read, a table or a folder, or an image given as a collection (see monitoreo.assets)."""
	from . import assets
	k = kind(spec)
	if k == 'catalog':
		return
	t = assets.asset_type(spec[k])
	_types[spec[k]] = 'IMAGE' if t == 'image' else 'IMAGE_COLLECTION'
	if k == 'collection' and t == 'image':
		raise ValueError(f"{spec[k]} is an image, not a collection of images: give it as image='{spec[k]}' (a fixed "
		                 'layer, without dates)')


def native_scale(spec):
	"""Pixel size (m) of the data of SPEC."""
	k = kind(spec)
	if k == 'catalog':
		return float(entry_of(spec)['m'])
	key = (spec.get(k), spec.get('band'))
	if key not in _native:
		check_asset(spec)
	if key not in _native:
		src = ee.Image(spec['image']) if k == 'image' and _is_image(spec['image']) else ee.ImageCollection(spec.get(k)).first()
		_native[key] = src.select(spec['band']).projection().nominalScale().getInfo()
	return _native[key]


def _is_image(asset):
	if asset not in _types:
		from . import assets
		_types[asset] = 'IMAGE' if assets.asset_type(asset) == 'image' else 'IMAGE_COLLECTION'
	return _types[asset] == 'IMAGE'


def _resample(spec, res, native):
	method = str(spec.get('resample') or 'auto').lower()
	if method == 'auto':
		return 'bilinear' if res < native else None
	return None if method == 'nearest' else method


def _fixed(spec, res):
	"""Image of a spec of kind 'image'."""
	if _is_image(spec['image']):
		img = ee.Image(spec['image']).select(spec['band'])
	else:
		col = ee.ImageCollection(spec['image']).select(spec['band'])
		img = col.mosaic().setDefaultProjection(col.first().projection())
	native = native_scale(spec)
	img = img.multiply(float(spec.get('scale') or 1)).add(float(spec.get('offset') or 0))
	method = _resample(spec, res, native)
	if method:
		img = img.resample(method)
	terrain = spec.get('terrain')
	if terrain:
		ops = {'slope': ee.Terrain.slope, 'aspect': ee.Terrain.aspect}
		if terrain not in ops:
			raise ValueError(f"unknown terrain {terrain}: use {', '.join(ops)}")
		img = ops[terrain](img)
	agg = str(spec.get('aggregate') or 'auto').lower()
	if agg in ('auto', 'mean') and res > 2 * native:
		img = img.reduceResolution(ee.Reducer.mean(), True, 65535)
	return img.toFloat().rename('value')


def _from_collection(spec, region, res):
	"""Collection of single band images ('value') of a spec of kind 'collection'."""
	start, end = _span(spec)
	scale, offset = float(spec.get('scale') or 1), float(spec.get('offset') or 0)
	method = _resample(spec, res, native_scale(spec))

	def prep(img):
		img = ee.Image(img)
		out = img.select(spec['band']).multiply(scale).add(offset)
		if method:
			out = out.resample(method)
		return out.toFloat().rename('value').copyProperties(img, ['system:time_start'])

	return ee.ImageCollection(spec['collection']).filterBounds(region).filterDate(start, end).map(prep)


def check_rgb(spec):
	"""Raise ValueError, without Earth Engine, if SPEC has no true colour (see sensors.RGB): other sources than the
	catalog, fixed layers, variables whose images have no red, green and blue bands, and the metrics that do not give
	colours (see composite.check_rgb_metric)."""
	if kind(spec) != 'catalog':
		raise ValueError('only the variables of the catalog of MonitorEO have a true colour (of Sentinel-2, Landsat '
		                 'and the cloud frequency of MODIS)')
	e = entry_of(spec)
	if e.get('static'):
		raise ValueError(f"{e['index']} ({e['sensor']}) is a fixed layer, without dates: it has no images, nor true "
		                 'colour')
	if sensors.rgb_of(e) is None:
		raise sensors._no_rgb(e)
	composite.check_rgb_metric(spec['metric'])
	if spec.get('temporal', 'period') != 'period':
		composite.check_rgb_metric(spec['interannual'])


def collection(spec, region, res, rgb=False):
	"""Collection of single band images ('value') of a spec of kind 'catalog' or 'collection', before the temporal
	aggregation (with RGB, also the bands red, green and blue of their true colour: see sensors.collection)."""
	if rgb:
		check_rgb(spec)
	if kind(spec) == 'collection':
		col = _from_collection(spec, region, res)
	else:
		check_dates(spec)
		entry = entry_of(spec)
		start, end = _span(spec)
		col = sensors.collection(entry, region, start, end, spec['quality'], _resample(spec, res, float(entry['m'])),
		                         rgb)
	m = mask(spec, region, res)  # the pixels of the study area to keep, in every image (n_pixels and count too)
	return col if m is None else col.map(lambda i: ee.Image(i).updateMask(m))


def image(spec, region, res, rgb=False):
	"""Image ('value') of the variable SPEC over REGION (ee.Geometry) for output pixels of RES metres; with RGB, the
	true colour of its images instead (bands red, green and blue: surface reflectance), on the same pixels and with the
	same metric (see composite)."""
	if rgb:
		check_rgb(spec)
		col = collection(spec, region, res, rgb=True)
		bands = ['value'] + sensors.RGB_BANDS
		return composite.composite(col, spec['metric'], spec['temporal'], spec['interannual'], spec['period'],
		                           spec['season'], bands).select(sensors.RGB_BANDS)
	if kind(spec) == 'image':
		img = _fixed(spec, res)
	elif is_static(spec):
		img = _fixed(_static_spec(spec), res)
	else:  # its collection is masked already (see collection)
		return composite.composite(collection(spec, region, res), spec['metric'], spec['temporal'],
		                           spec['interannual'], spec['period'], spec['season'])
	m = mask(spec, region, res)
	return img if m is None else img.updateMask(m)


def n_images(spec, region):
	"""Number of images of the period (and season) of SPEC over REGION (None for a fixed image)."""
	if kind(spec) == 'image' or is_static(spec):
		return None
	wins = composite.windows(spec['period'], spec['season'])
	col = collection(dict(spec, resample='nearest', where=None, exclude_landcover=None), region, 1e9)  # no mask
	return col.filter(composite.date_filter(wins)).size().getInfo()


def describe(spec, rgb=False):
	"""What SPEC computes, for the record of the downloaded files: its source and, if given, its period, season and
	temporal metric and aggregation; with RGB, of its true colour (see image)."""
	k = kind(spec)
	d = {'kind': k}
	fixed = k == 'image' or is_static(spec)  # no period, season or temporal metric: they do not apply
	for key in ('period', 'season', 'metric', 'temporal', 'interannual') if not fixed else ():
		if spec.get(key) is not None and not (key == 'interannual' and spec.get('temporal', 'period') == 'period'):
			d[key] = spec[key]
	if k != 'catalog':  # the data of Earth Engine as given, without the pixel filters of MonitorEO
		d.update({'variable': f"{spec[k]} {spec.get('band') or ''}".strip(), k: spec[k], 'band': spec.get('band'),
		          'scale': spec.get('scale'), 'offset': spec.get('offset'), 'terrain': spec.get('terrain'),
		          'pixel_filters': {}})
		if spec.get('unit'):
			unit = catalog.unit_of(catalog.custom_unit(spec['unit']), d.get('metric'))
			d.update({'unit': unit, 'udunits': catalog.udunits(unit)})
		d = {key: v for key, v in d.items() if v is not None}
	if k == 'catalog':
		e = entry_of(spec)
		d.update({'monitoreo_ref': e['ref'], 'variable': e['vname_en'], 'collection': e['col'],
		          'formula': e['ft'], 'scale': e.get('scale'), 'offset': e.get('offset'),
		          'unit': catalog.unit_of(e['unit'], d.get('metric')),
		          'udunits': catalog.udunits(catalog.unit_of(e['unit'], d.get('metric'))),
		          'native_resolution': e['m'], 'pixel_filters': sensors.filters(e, spec['quality'])})
		if e['ref'] in catalog.FIXES:
			d['fixed'] = catalog.FIXES[e['ref']]
		if e.get('notes', {}).get('ft'):
			d['note'] = e['notes']['ft']
	if spec.get('where'):
		d['where'] = spec['where']  # the pixels of the study area kept
	if rgb:
		bands, scale, offset = sensors.rgb_of(entry_of(spec))
		d['true_colour'] = {'bands': dict(zip(sensors.RGB_BANDS, bands)), 'scale': scale, 'offset': offset,
		                    'pixels': 'those of the variable', 'unit': 'surface reflectance', 'udunits': '1'}
		d['unit'], d['udunits'] = catalog.RGB_UNIT, '1'
	return d
