"""Earth Engine image of a variable described by a dictionary (a 'spec'), of one of three kinds:

catalog     a variable of MonitorEO: index (NDVI, LST, ...), sensor (Sentinel-2, Landsat, Modis) and, optionally,
            collection (when the catalog has several for that variable and sensor) or ref (ID of the entry).
collection  any other image collection of Earth Engine: collection and band (e.g. IDAHO_EPSCOR/TERRACLIMATE, pr),
            with optional scale and offset of the band and unit (of its values, in UDUNITS: 'mm', 'degC').
image       a fixed image (or a collection of tiles, mosaicked): image and band (e.g. COPERNICUS/DEM/GLO30_2024_1,
            DEM), with optional scale, offset, unit and terrain ('slope' or 'aspect' of the band, in degrees: its unit
            is then degree). Like the fixed layers of the catalog, it has no dates: maps and their statistics, no time
            series, trends or comparisons.

The band of a collection or an image is one ('pr') or several (a list, ['aet', 'def'], or a text with commas,
'aet, def') with band_reducer, 'sum' or 'mean' (see BAND_REDUCERS): each band times scale plus offset, then, on each
pixel where every band has data, their sum (e.g. 12 monthly bands into the annual total) or their mean (e.g. the
depth bands of a soil), on the pixels of the first band. The unit is that of every band, so of their sum or mean: a
sum of bands is not turned from a rate into a total (12 monthly bands in mm give mm; the temporal metric 'sum' still
turns 'mm month-1' into 'mm', see catalog.unit_of). No terrain with several bands.

The data of Earth Engine outside the catalog (any ID of the Earth Engine data catalog, of the GEE Community Catalog or
of a project the account can read: see monitoreo.assets) keep their own mask: the pixel filters of MonitorEO (quality)
are for the variables of the catalog.

The variables of the catalog and of other collections are aggregated in time with metric, temporal and
interannual over period and season (see composite). Other keys:
  quality            pixel filters (clouds, water, snow, aerosols) and scene filter of the catalog variables
                     (see sensors.QUALITY; by default all the pixel filters of MonitorEO)
  resample           'auto' (bilinear when the output pixels are smaller than those of the data), 'nearest',
                     'bilinear' or 'bicubic'; a categorical layer (ECOREGION, BIOME: class codes), only 'auto' or
                     'nearest' (rasterized at the output pixel)
  aggregate          fixed images on pixels more than twice as big as theirs: 'auto' or 'mean' (mean of the
                     pixels of the data inside each output pixel) or 'none' (Earth Engine pyramids); a categorical
                     layer, 'auto' or 'mode' (the majority class of its pixels) or 'none' (see monitoreo.categorical)
  exclude_landcover  classes of ESA WorldCover 2021 (10 m) set to NoData, e.g. [40, 50, 80]: crops, built-up, water
  where              the pixels of the study area to keep: a list of conditions, all of them true, each a variable of
                     the catalog aggregated over the period and season of the spec (none for the fixed layers) with
                     min and/or max, e.g. [{"variable": "ELEVATION", "sensor": "Copernicus", "min": 1500},
                     {"variable": "PRECIP", "sensor": "TerraClimate", "metric": "sum", "temporal": "annual",
                     "max": 600}]; also metric, temporal, interannual, season and quality (see where_specs). A
                     condition can also leave out some land covers after a land cover map of a year (see
                     monitoreo.landcover), e.g. {"landcover": "CORINE", "year": 2018, "exclude": ["water", "built"]},
                     and a condition on a categorical layer keeps some of its classes (classes) or leaves them out
                     (exclude), e.g. {"variable": "BIOME", "sensor": "RESOLVE", "classes": [12]} (see
                     monitoreo.categorical)
"""

import datetime as dt
import math
import re

import ee

from . import catalog, categorical, composite, landcover, sensors

WORLDCOVER = 'ESA/WorldCover/v200'
SENSOR_ABBR = {'Sentinel-2': 'S2', 'Landsat': 'L', 'Modis': 'MODIS'}
KEYS = {'name', 'index', 'sensor', 'collection', 'ref', 'image', 'band', 'band_reducer', 'scale', 'offset', 'unit',
        'terrain', 'metric', 'metrics', 'temporal', 'interannual', 'period', 'season', 'quality', 'resample',
        'aggregate', 'exclude_landcover', 'where'}
DEFAULTS = {'temporal': 'period', 'interannual': 'mean', 'resample': 'auto', 'aggregate': 'auto', 'quality': {},
            'season': None, 'exclude_landcover': None, 'where': None}
WHERE_KEYS = {'variable', 'sensor', 'collection', 'ref', 'metric', 'temporal', 'interannual', 'season', 'quality',
              'period',
              'min', 'max', 'classes', 'exclude'}  # of a condition of where (classes, exclude: of a categorical layer)

TERRAIN = ('slope', 'aspect')  # of the band of an image (ee.Terrain), in degrees whatever the unit of the band
# how several bands of the data of Earth Engine by their ID are combined on each pixel (band_reducer): their sum or
# their mean (ee.Reducer.sum and mean over the bands)
BAND_REDUCERS = ('sum', 'mean')
TERRAIN_BANDS = ('terrain is the slope or the aspect of one band (an elevation): give one band, without '
                 'band_reducer')
# Units given in other words, in UDUNITS: those of the STAC records (monitoreo.assets.UNITS: 'C', 'W/m^2', 'mm/d') too
UNIT_WORDS = {'°C': 'degC', '°F': 'degF', '°': 'degree', 'deg C': 'degC', 'deg F': 'degF'}
DIMENSIONLESS = ('unitless', 'dimensionless', 'fraction', 'index')  # in any case: '1'

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


def bands_of(spec):
	"""The bands of the data of Earth Engine of SPEC: its band, one ('pr'), a list (['aet', 'def']) or a text with
	commas ('aet, def'), as a list of names without blanks ([] if none)."""
	band = spec.get('band')
	if band is None:
		return []
	items = band if isinstance(band, (list, tuple)) else str(band).split(',')
	return [str(b).strip() for b in items if str(b).strip()]


def _reducer(spec):
	return str(spec.get('band_reducer') or '').strip().lower()


def band_text(spec):
	"""The bands of SPEC in titles: the band ('pr'), or the reducer of several ('sum of aet, def')."""
	bands = bands_of(spec)
	if len(bands) < 2:
		return bands[0] if bands else ''
	return f"{_reducer(spec) or '?'} of {', '.join(bands)}"


def band_words(spec):
	"""The bands of SPEC in sentences: 'band pr', or 'the sum of the bands aet and def'."""
	bands = bands_of(spec)
	if len(bands) < 2:
		return f"band {bands[0] if bands else '?'}"
	return f"the {_reducer(spec) or '?'} of the bands {', '.join(bands[:-1])} and {bands[-1]}"


def band_stem(spec):
	"""The bands of SPEC in file names: the band ('pr'), the reducer and the bands ('sum_aet_def') or, for more than 3,
	the reducer, how many and the first and the last ('sum12_jan-dec')."""
	bands = bands_of(spec)
	if len(bands) < 2:
		return bands[0] if bands else ''
	if len(bands) > 3:
		return f"{_reducer(spec)}{len(bands)}_{bands[0]}-{bands[-1]}"
	return '_'.join([_reducer(spec)] + bands)


def data_name(spec):
	"""The name of the data of Earth Engine of SPEC (kind 'collection' or 'image') in titles and records: its ID, its
	band (or the reducer of its bands, see band_text) and its terrain ('COPERNICUS/DEM/GLO30_2024_1 DEM slope',
	'IDAHO_EPSCOR/TERRACLIMATE sum of aet, def'), so that the slope of a DEM is not named as its elevation."""
	k = kind(spec)
	return ' '.join(str(x) for x in (_asset_id(spec.get(k)), band_text(spec), spec.get('terrain')) if x)


def _default_name(spec):
	k = kind(spec)
	if k == 'catalog':
		base = f"{spec['index']}_{SENSOR_ABBR.get(spec.get('sensor'), spec.get('sensor') or '')}".rstrip('_')
	else:
		base = f"{spec.get(k).split('/')[-1]}_{band_stem(spec)}".rstrip('_')
		if spec.get('terrain'):
			base += '_' + spec['terrain']
	return base


def check_bands(spec, asset):
	"""Check the bands of the data of Earth Engine ASSET of SPEC (kind 'collection' or 'image') and keep them as the
	specs do (SPEC is changed): one band as given (a text), several as a list with band_reducer ('sum' or 'mean'),
	required with two or more and refused with one, and never with terrain. ValueError, before Earth Engine, in the
	words of every tool (those of customEntry in gee/core.js too), in this order."""
	bands = bands_of(spec)
	if not bands:
		raise ValueError(f"variable {spec.get('name') or asset}: give the band of {asset} (one, or several with "
		                 'band_reducer; describe_asset lists them)')
	reducer = _reducer(spec)
	if reducer and reducer not in BAND_REDUCERS:
		raise ValueError(f"unknown band_reducer {spec['band_reducer']}: use {', '.join(BAND_REDUCERS)}")
	for i, b in enumerate(bands):
		if b in bands[:i]:
			raise ValueError(f'band {b} is given twice: give each band once')
	if len(bands) > 1 and spec.get('terrain'):  # the slope of a sum of bands is not that of an elevation
		raise ValueError(TERRAIN_BANDS)
	if len(bands) > 1 and not reducer:
		raise ValueError(f"{asset}: give band_reducer, 'sum' or 'mean', to combine its {len(bands)} bands "
		                 f"({', '.join(bands)}) into one value on each pixel")
	if len(bands) == 1 and reducer:
		raise ValueError('band_reducer combines several bands: give two or more in band (a list, or a text with '
		                 'commas)')
	spec.pop('band_reducer', None)  # not in the specs of one band: their records (recipe.spec_key) stay the same
	if len(bands) > 1:
		spec.update(band=bands, band_reducer=reducer)
	elif spec['band'] != bands[0]:  # a list of one, 'pr,' or ' pr ': its band, a text (as customEntry of the app)
		spec['band'] = bands[0]
	return spec


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
	if base.get('unit') is not None and not str(base['unit']).strip():
		base.pop('unit')  # '' or blank: not given, as in services.make_spec and the app (not dimensionless)
	if k == 'catalog' and base.get('unit') is not None:
		raise ValueError(f"{e['index']} ({e['sensor']}) has its unit in the catalog ({e['unit']}): unit is for the "
		                 'data of Earth Engine outside it (collection or image)')
	if k == 'catalog' and base.get('band_reducer') not in (None, ''):  # a recipe does not go through make_spec
		raise ValueError('band_reducer: only for the data of Earth Engine given by their ID (collection or image, '
		                 f"instead of variable and sensor); {e['index']} is a variable of the catalog")
	if k != 'catalog':
		base[k] = _asset_id(base[k])
		check_bands(base, base[k])
		if base.get('terrain') and k != 'image':  # a recipe does not go through services.make_spec
			raise ValueError('terrain is for an image (image=, e.g. a DEM), not for a collection')
		if base.get('terrain') and base['terrain'] not in TERRAIN:  # now, not when Earth Engine computes it
			raise ValueError(f"unknown terrain {base['terrain']}: use {', '.join(TERRAIN)}")
		base['unit'] = given_unit(base.get('unit'), base[k], base.get('terrain'))
		if not base['unit']:
			base.pop('unit')
	if e.get('two_periods') and not two_periods:
		raise ValueError(f"{e['index']} ({e['sensor']}) compares a period before and a period after a fire: compute "
		                 f"it with burn_severity and index '{e['index']}'")
	if categorical.is_categorical(e):  # class codes: never interpolated nor averaged
		categorical.check_options(e, base.get('resample'), base.get('aggregate'))
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
		landcover_conditions(base)
		class_conditions(base)
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
	        if isinstance(c, dict) and not landcover.is_landcover(c) else c for c in conditions]  # a map has its year


def where_specs(spec):
	"""[(spec of its variable, min, max)] of each condition of SPEC['where']: the variable of the catalog aggregated
	over the period and season of SPEC (or over the period of the condition, [start, end], if it has one), with the
	metric, temporal, interannual and quality of the condition (by default the mean, or the only metric of the
	variable, of the whole period). The fixed layers (elevation, slope, TWI, WorldClim) have no period, so they can
	filter any result; a variable with dates needs a period, of the result or of the condition. The land cover
	conditions (see landcover_conditions) are not variables, and those on a categorical layer (classes or exclude: see
	class_conditions) are not values between min and max: they are left out here (those, checked)."""
	out = []
	for c in _conditions(spec):
		if landcover.is_landcover(c):
			continue
		if not isinstance(c, dict) or not c.get('variable'):
			raise ValueError('each condition of where is a dictionary with variable (and sensor), and min and/or max (or, '
			                 'for a categorical layer, classes or exclude), or with landcover, year and exclude (the land '
			                 'covers to leave out)')
		unknown = set(c) - WHERE_KEYS
		if unknown:
			raise ValueError(f"a condition of where has unknown keys {', '.join(sorted(unknown))}: use "
			                 f"{', '.join(sorted(WHERE_KEYS))}")
		e = catalog.find(c['variable'], c.get('sensor'), c.get('collection'), c.get('ref'))
		if categorical.is_categorical(e) or c.get('classes') is not None or c.get('exclude') is not None:
			categorical.condition(c, e)  # checked (an error on a variable with values): see class_conditions
			continue
		if c.get('min') is None and c.get('max') is None:
			raise ValueError(f"the condition on {c['variable']} of where needs min, max or both")
		var = {'index': e['index'], 'sensor': e['sensor'], 'collection': c.get('collection'), 'ref': c.get('ref'),
		       'quality': c.get('quality') or {}, 'temporal': c.get('temporal') or 'period',
		       'interannual': c.get('interannual') or 'mean', 'season': c.get('season', spec.get('season'))}
		if not e.get('static'):
			period = c.get('period') or spec.get('period')
			if not period:
				raise ValueError(f"the condition on {e['index']} ({e['sensor']}) needs a period: this result has none "
				                 '(a fixed layer without dates), so give the condition its own, "period": [start, end], '
				                 'or filter by other fixed layers '
				                 '(ELEVATION, SLOPE, TWI, the BIO variables of WorldClim)')
			if not isinstance(period, (list, tuple)) or len(period) != 2:
				raise ValueError(f'the period of the condition on {e["index"]} is [start, end]')
			var.update(period=[str(d) for d in period], metric=c.get('metric') or e.get('metric') or 'mean')
		cs = specs({k: v for k, v in var.items() if v is not None})[0]
		out.append((cs, c.get('min'), c.get('max')))
	return out


def _conditions(spec):
	conditions = spec.get('where') or []
	return [conditions] if isinstance(conditions, dict) else conditions


def landcover_conditions(spec):
	"""The land cover conditions of SPEC['where'] (see monitoreo.landcover), checked (ValueError if one is wrong)."""
	out = [c for c in _conditions(spec) if landcover.is_landcover(c)]
	for c in out:
		landcover.check(c)
	return out


def class_conditions(spec):
	"""[(entry, codes, keep)] of the conditions of SPEC['where'] on a categorical layer (see
	monitoreo.categorical.condition: keep True, only the pixels of those classes; False, without them), checked
	(ValueError if one is wrong)."""
	out = []
	for c in _conditions(spec):
		if landcover.is_landcover(c) or not isinstance(c, dict) or not c.get('variable'):
			continue
		e = catalog.find(c['variable'], c.get('sensor'), c.get('collection'), c.get('ref'))
		if categorical.is_categorical(e):
			out.append(categorical.condition(c, e))
	return out


def mask(spec, region, res):
	"""The image (1) of the pixels of SPEC that pass its conditions (where) and are not of the land covers it
	excludes (exclude_landcover, and the land cover conditions of where), masked elsewhere; None without conditions. A
	pixel where a condition has no data is left out; the conditions on a categorical layer keep the pixels where the
	classes kept cover half of them or more (see monitoreo.categorical.keep)."""
	masks = [landcover.keep(c, region, res) for c in landcover_conditions(spec)]
	masks += [categorical.keep(e, codes, kept, res) for e, codes, kept in class_conditions(spec)]
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
	dimensionless), with the words of the STAC records translated ('C' and '°C' are degC, 'W/m^2' is W m-2, 'unitless'
	or 'Fraction' is 1: see monitoreo.assets.UNITS); ValueError if it cannot be one, as the code of a variable of the
	catalog ('NDVI': a name, not a unit). Empty: not given (see given_unit)."""
	from . import assets
	text = ' '.join(str(unit).replace('º', '°').split())
	if text.lower() in DIMENSIONLESS:
		return '1'
	text = UNIT_WORDS.get(text) or assets.UNITS.get(text) or text  # 'C' alone is coulomb in UDUNITS: here degC
	if not catalog.UDUNITS_TEXT.fullmatch(text) or text.upper() in _codes():
		raise ValueError(f"the unit of {asset} is written in UDUNITS (the units of the CF conventions), e.g. 'mm', "
		                 f"'degC', 'kg m-2', 'mm day-1' or '1' (dimensionless), not {unit!r}")
	return text


def _codes():
	"""The codes of the variables of the catalog, in capitals (NDVI, LST, ...)."""
	return {str(e['index']).upper() for e in catalog.variables()}


def given_unit(unit, asset, terrain=None):
	"""The unit in UDUNITS of the data of Earth Engine ASSET outside the catalog with UNIT given by the user (see
	_udunits_text), or '' if none was given (None, '' or blank); with TERRAIN (the slope or the aspect of the band of
	an image), 'degree', whatever the unit of the band: ValueError if another one is given. Several bands combined
	(band_reducer) have the unit of every band: their sum is not turned from a rate into a total, as the temporal
	metric 'sum' is (catalog.unit_of)."""
	text = _udunits_text(unit, asset) if unit is not None and str(unit).strip() else ''
	if terrain:
		if text not in ('', 'degree'):
			raise ValueError(f"the {terrain} of {asset} is in degrees: give no unit, or 'degree' (not {unit!r}, the "
			                 'unit of its band)')
		return 'degree'
	return text


def is_categorical(spec):
	"""Whether SPEC is a categorical layer of the catalog (ECOREGION, BIOME: its values are class codes, see
	monitoreo.categorical); also a fixed layer (is_static)."""
	return kind(spec) == 'catalog' and categorical.is_categorical(entry_of(spec))


def is_static(spec):
	"""Whether SPEC is a fixed layer without dates: a variable of the catalog without them (elevation, slope) or an
	image of Earth Engine (kind 'image'), with maps and their statistics but no time series, trends or
	comparisons."""
	k = kind(spec)
	return k == 'image' or (k == 'catalog' and bool(entry_of(spec).get('static')))


def check_dates(spec, what='time series, trends or comparisons'):
	"""Error if SPEC is a fixed layer without dates, for WHAT needs them."""
	if kind(spec) == 'image':
		raise ValueError(f"{spec['image']} ({band_words(spec)}) is given as a fixed image, without dates "
		                 f"(image=): it has maps, GeoTIFFs and statistics of the region (map_layer, download_image, "
		                 f"region_stats), but no {what}. A collection of images with dates is given as collection=")
	if is_static(spec):
		e = entry_of(spec)
		raise ValueError(f"{e['index']} ({e['sensor']}) is a fixed layer, without dates: it has maps, GeoTIFFs and "
		                 f"statistics of the region (map_layer, download_image, region_stats), but no {what}")


def _static_spec(spec):
	"""The spec of kind 'image' of the fixed layer of the catalog SPEC (its collection, band, terrain, scale and
	offset, and its formula: see sensors.parse_formula; the TWI, from two bands)."""
	e = entry_of(spec)
	if e.get('image_asset'):  # known to be an image (WorldClim, MERIT Hydro): no need to ask Earth Engine
		_types[e['col']] = 'IMAGE'
	return dict(spec, image=e['col'], band=e['band'], terrain=e.get('terrain'), scale=e.get('scale'),
	            offset=e.get('offset'),  # e.g. the temperatures of WorldClim are in tenths of a degree
	            formula=sensors.parse_formula(e))


def _span(spec):
	wins = composite.windows(spec['period'], spec['season'])
	return wins[0][1].isoformat(), wins[-1][2].isoformat()


def check_asset(spec):
	"""Error if the data of Earth Engine of SPEC (kind 'collection' or 'image') cannot be computed as given: an ID that
	this account cannot read, a table or a folder, an image given as a collection, or a collection of images without
	dates (tiles, e.g. a DEM) given as a collection, which the period would leave empty (see monitoreo.assets). The
	words are those of every tool (no argument of Python): the command line and R read them too."""
	from . import assets
	k = kind(spec)
	if k == 'catalog':
		return
	t = assets.asset_type(spec[k])
	_types[spec[k]] = 'IMAGE' if t == 'image' else 'IMAGE_COLLECTION'
	if k == 'collection' and t == 'image':
		raise ValueError(f'{spec[k]} is an image, not a collection of images: give it as an image (a fixed layer, '
		                 'without dates: maps, GeoTIFFs and statistics of the region)')
	if k == 'collection' and not assets.first_date(spec[k]):  # Earth Engine filters out the images without a date
		raise ValueError(f'{spec[k]} is a collection of images without dates (tiles): give it as an image (their '
		                 'mosaic, a fixed layer, without dates)')


def native_scale(spec):
	"""Pixel size (m) of the data of SPEC."""
	k = kind(spec)
	if k == 'catalog':
		return float(entry_of(spec)['m'])
	# every time, not only the first (its answers are cached in monitoreo.assets): the same ID given as an image and
	# then as a collection shares the pixel size, but not what can be computed with it
	check_asset(spec)
	band = spec.get('band')
	key = (spec.get(k), tuple(band) if isinstance(band, (list, tuple)) else band)
	if key not in _native:  # several bands: the pixels of the first (those of the result, see _combine)
		src = ee.Image(spec['image']) if k == 'image' and _is_image(spec['image']) else \
			_with_band(ee.ImageCollection(spec.get(k)), band).first()
		_native[key] = src.select(bands_of(spec)[0]).projection().nominalScale().getInfo()
	return _native[key]


def _with_band(col, band):
	"""The images of the collection COL that have BAND (or all the bands of a list of them): some collections change
	their bands from image to image (Sentinel-1: VV and VH, or HH and HV), and select would fail on those without
	it."""
	for b in band if isinstance(band, (list, tuple)) else [band]:
		col = col.filter(ee.Filter.listContains('system:band_names', b))
	return col


def _projection(img, bands):
	"""The projection of IMG, that of the first of its BANDS if several: projection() of an image whose bands have
	different projections fails."""
	return img.select(bands[0]).projection() if len(bands) > 1 else img.projection()


def _combine(img, reducer, proj):
	"""The bands of IMG combined on each pixel with REDUCER ('sum' or 'mean', see BAND_REDUCERS) into one band, only
	where every band has data (reduce would leave out the bands without data, and a sum would be smaller there), with
	the projection PROJ, that of the first band (reduce does not keep that of the bands)."""
	img = img.updateMask(img.mask().reduce(ee.Reducer.min()))
	return img.reduce(getattr(ee.Reducer, reducer)()).setDefaultProjection(proj)


def _is_image(asset):
	if asset not in _types:
		from . import assets
		_types[asset] = 'IMAGE' if assets.asset_type(asset) == 'image' else 'IMAGE_COLLECTION'
	return _types[asset] == 'IMAGE'


def _resample(spec, res, native):
	# (a categorical layer never comes here: categorical.image rasterizes it at the output pixel, the mode on big ones)
	method = str(spec.get('resample') or 'auto').lower()
	if method == 'auto':
		return 'bilinear' if res < native else None
	return None if method == 'nearest' else method


def _twi(image_id, elv_band, area_band):
	"""The topographic wetness index (TWI) of the image IMAGE_ID (MERIT Hydro, see sensors.TWI): ln(a / tan β), with a
	the upstream drainage area of AREA_BAND (km²) per metre of contour (at least the area of the pixel, divided by the
	square root of its area: in m) and β the slope of the elevation ELV_BAND (ee.Terrain.slope, in degrees), tan β at
	least sensors.TWI['min_tan_slope'] (the flats). On the grid of the elevation, so that the bilinear interpolation
	and the mean of the bigger pixels (_fixed) are those of the TWI, not of the upstream area. The same calls of Earth
	Engine, in the same order, as twiImage of gee/core.js (tests/test_themes.py compares them)."""
	src = ee.Image(image_id)
	elv = src.select(elv_band)
	px = ee.Image.pixelArea()
	a = src.select(area_band).multiply(sensors.TWI['area_scale']).max(px).divide(px.sqrt())
	tan = ee.Terrain.slope(elv).multiply(math.pi / 180).tan().max(sensors.TWI['min_tan_slope'])
	return a.divide(tan).log().setDefaultProjection(elv.projection())


def _fixed(spec, res):
	"""Image of a spec of kind 'image' (also those of the fixed layers of the catalog, see _static_spec; several bands:
	combined on each pixel, see _combine)."""
	formula, twi_bands = spec.get('formula') or ('static', None)
	if formula == 'twi':  # the topographic wetness index, from two bands: no scale, offset or terrain
		img = _twi(spec['image'], *twi_bands)
		native = native_scale(spec)
	else:
		bands, proj = bands_of(spec), None
		if _is_image(spec['image']):
			img = ee.Image(spec['image']).select(spec['band'])
			if len(bands) > 1:
				proj = _projection(img, bands)
		else:
			col = ee.ImageCollection(spec['image'])
			if kind(spec) != 'catalog':  # data by its ID: only the tiles with the band (those of the catalog all have it)
				col = _with_band(col, spec['band'])
			col = col.select(spec['band'])
			img = col.mosaic()
			proj = _projection(col.first(), bands)
			img = img.setDefaultProjection(proj)
		native = native_scale(spec)
		img = img.multiply(float(spec.get('scale') or 1)).add(float(spec.get('offset') or 0))  # each band, before
		if len(bands) > 1:
			img = _combine(img, spec['band_reducer'], proj)
	method = _resample(spec, res, native)
	if formula == 'twi' and not method and res <= 2 * native and str(spec.get('resample') or 'auto').lower() == 'auto':
		# also on pixels as big as those of MERIT Hydro (the default) or up to twice: interpolated from the TWI of its
		# grid (its default projection), not computed on the output pixels with the slope and the area of their own
		method = 'bilinear'
	if method:
		img = img.resample(method)
	terrain = spec.get('terrain')
	if terrain:
		if terrain not in TERRAIN:
			raise ValueError(f"unknown terrain {terrain}: use {', '.join(TERRAIN)}")
		img = getattr(ee.Terrain, terrain)(img)
	agg = str(spec.get('aggregate') or 'auto').lower()
	if agg in ('auto', 'mean') and res > 2 * native:
		img = img.reduceResolution(ee.Reducer.mean(), True, 65535)
	return img.toFloat().rename('value')


def _from_collection(spec, region, res):
	"""Collection of single band images ('value') of a spec of kind 'collection' (several bands: combined on each pixel
	of each image, see _combine; only the images with all of them)."""
	start, end = _span(spec)
	scale, offset = float(spec.get('scale') or 1), float(spec.get('offset') or 0)
	method = _resample(spec, res, native_scale(spec))
	bands = bands_of(spec)

	def prep(img):
		img = ee.Image(img)
		out = img.select(spec['band']).multiply(scale).add(offset)  # each band, before they are combined
		if len(bands) > 1:
			out = _combine(out, spec['band_reducer'], _projection(img, bands))
		if method:
			out = out.resample(method)
		return out.toFloat().rename('value').copyProperties(img, ['system:time_start'])

	return _with_band(ee.ImageCollection(spec['collection']).filterBounds(region).filterDate(start, end),
	                  spec['band']).map(prep)


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
	elif is_categorical(spec):  # before is_static: polygons (a collection of features) rasterized, never interpolated
		img = categorical.image(entry_of(spec), res, spec.get('aggregate'))
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
		d.update({'variable': data_name(spec), k: spec[k], 'band': spec.get('band'),
		          'band_reducer': spec.get('band_reducer'), 'scale': spec.get('scale'), 'offset': spec.get('offset'),
		          'terrain': spec.get('terrain'), 'pixel_filters': {}})
		if spec.get('unit') or catalog.is_cv(d.get('metric'), d.get('interannual')):
			unit = catalog.unit_of(catalog.custom_unit(spec.get('unit')), d.get('metric'), d.get('interannual'))
			d.update({'unit': unit, 'udunits': catalog.udunits(unit)})
		d = {key: v for key, v in d.items() if v is not None}
	if k == 'catalog':
		e = entry_of(spec)
		d.update({'monitoreo_ref': e['ref'], 'variable': e['vname_en'], 'collection': e['col'],
		          'formula': e['ft'], 'scale': e.get('scale'), 'offset': e.get('offset'),
		          'unit': catalog.unit_of(e['unit'], d.get('metric'), d.get('interannual')),
		          'udunits': catalog.udunits(catalog.unit_of(e['unit'], d.get('metric'), d.get('interannual'))),
		          'native_resolution': e['m'], 'pixel_filters': sensors.filters(e, spec['quality'])})
		if e['ref'] in catalog.FIXES:
			d['fixed'] = catalog.FIXES[e['ref']]
		if e.get('notes', {}).get('ft'):
			d['note'] = e['notes']['ft']
		if categorical.is_categorical(e):  # class codes, without a unit: the table that says what each one is
			t = categorical.of(e)
			d.update({'categorical': True, 'classes': e['classes'], 'classes_table': t['name'],
			          'property': t['property']})
	if spec.get('where'):
		d['where'] = spec['where']  # the pixels of the study area kept
	if rgb:
		bands, scale, offset = sensors.rgb_of(entry_of(spec))
		d['true_colour'] = {'bands': dict(zip(sensors.RGB_BANDS, bands)), 'scale': scale, 'offset': offset,
		                    'pixels': 'those of the variable', 'unit': 'surface reflectance', 'udunits': '1'}
		d['unit'], d['udunits'] = catalog.RGB_UNIT, '1'
	return d
