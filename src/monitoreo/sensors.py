"""Collections of the sensors of MonitorEO: quality masks, scale and offset of the bands and formula of the variable:

  - the pixel filters ('remove pixels with clouds, water, snow, aerosols') use the QA bands of the catalog
    (*_bandQA): SCL for Sentinel-2 (Cloud Score+ for its clouds), QA_PIXEL and SR_QA_AEROSOL for Landsat and the
    QA bands of each MODIS product;
  - the scale and offset are applied to the bands before the formula (constants of the formulas such as the + 1
    of EVI or the - 0.018 of the Landsat albedo need reflectances, not raw values);
  - band names of the formulas are matched without case (LST_day_1km is the band LST_Day_1km);
  - flag values of the MODIS products (e.g. 250 = cloud in NDSI_Snow_Cover) are masked;
  - Landsat 7 is only used until 2003-05-31, as the catalog says (failure of its scan line corrector);
  - the snow cover frequency (SCF, formula SCF(green,nir,swir1)) classifies the snow of each image with its own
    rules and masks (SCF below).

References (monitoreo.references gives them, with those of the data, with each result):
    Pasquarella, V. J., Brown, C. F., Czerwinski, W., & Rucklidge, W. J. (2023). Comprehensive quality assessment of
      optical satellite imagery using weakly supervised video learning. In Proceedings of the IEEE/CVF Conference on
      Computer Vision and Pattern Recognition Workshops (CVPRW) (pp. 2125–2135).
      https://doi.org/10.1109/CVPRW59228.2023.00206
    Main-Knorn, M., Pflug, B., Louis, J., Debaecker, V., Müller-Wilm, U., & Gascon, F. (2017). Sen2Cor for
      Sentinel-2. In L. Bruzzone, F. Bovolo, & J. A. Benediktsson (Eds.), Image and Signal Processing for Remote
      Sensing XXIII. SPIE. https://doi.org/10.1117/12.2278218
    Foga, S., Scaramuzza, P. L., Guo, S., Zhu, Z., Dilley, R. D., Beckmann, T., Schmidt, G. L., Dwyer, J. L.,
      Hughes, M. J., & Laue, B. (2017). Cloud detection algorithm comparison and validation for operational Landsat
      data products. Remote Sensing of Environment, 194, 379–390. https://doi.org/10.1016/j.rse.2017.03.026
    Farr, T. G., Rosen, P. A., Caro, E., Crippen, R., Duren, R., Hensley, S., Kobrick, M., Paller, M., Rodriguez,
      E., Roth, L., Seal, D., Shaffer, S., Shimada, J., Umland, J., Werner, M., Oskin, M., Burbank, D., & Alsdorf,
      D. (2007). The Shuttle Radar Topography Mission. Reviews of Geophysics, 45(2), RG2004.
      https://doi.org/10.1029/2005RG000183 (the SRTM of the shadow of the relief of the SCF)
    Chander, G., Markham, B. L., & Helder, D. L. (2009). Summary of current radiometric calibration coefficients for
      Landsat MSS, TM, ETM+, and EO-1 ALI sensors. Remote Sensing of Environment, 113(5), 893–903.
      https://doi.org/10.1016/j.rse.2009.01.007 (the TOA reflectance of the snow in the shadow of the SCF)
"""

import re

import ee

# Bands of Landsat 5 and 7, and of Landsat 8 and 9, with the names used by the formulas of the catalog
LANDSAT_57 = {'SR_B1': 'blue', 'SR_B2': 'green', 'SR_B3': 'red', 'SR_B4': 'nir', 'SR_B5': 'swir1', 'SR_B7': 'swir2',
              'ST_B6': 'st', 'QA_PIXEL': 'QA_PIXEL'}
LANDSAT_89 = {'SR_B2': 'blue', 'SR_B3': 'green', 'SR_B4': 'red', 'SR_B5': 'nir', 'SR_B6': 'swir1', 'SR_B7': 'swir2',
              'ST_B10': 'st', 'QA_PIXEL': 'QA_PIXEL', 'SR_QA_AEROSOL': 'SR_QA_AEROSOL'}
LANDSAT = [  # collection, bands, last date
	('LANDSAT/LT05/C02/T1_L2', LANDSAT_57, None),
	('LANDSAT/LE07/C02/T1_L2', LANDSAT_57, '2003-06-01'),
	('LANDSAT/LC08/C02/T1_L2', LANDSAT_89, None),
	('LANDSAT/LC09/C02/T1_L2', LANDSAT_89, None),
]
S2 = 'COPERNICUS/S2_SR_HARMONIZED'
CLOUD_SCORE = 'GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'

# Scene cloud cover property of each sensor, for quality['scene_clouds']
SCENE_CLOUDS = {'Sentinel-2': 'CLOUDY_PIXEL_PERCENTAGE', 'Landsat': 'CLOUD_COVER_LAND'}

# Quality options and their defaults. The pixel filters of MonitorEO (clouds, water, snow, aerosols) remove, in
# every image, the pixels that its QA bands flag; all of them are on by default. 'auto' = on, except for the
# variables that measure what the filter removes (MEASURES).
QUALITY = {
	'clouds': True,        # clouds and cloud shadows
	'water': True,         # water
	'snow': True,          # snow and ice
	'aerosols': True,      # high aerosol content (Landsat 8 and 9, MODIS NDVI, EVI and LAI)
	'cloud_score': 0.6,    # Sentinel-2 clouds: minimum Cloud Score+ (cs_cdf) of a clear pixel; None = SCL classes
	                       # (in Guajares Cloud Score+ gave an NDVI p5 closer to the reference)
	'scene_clouds': None,  # Sentinel-2 and Landsat: maximum cloud cover of a scene (%), None = all scenes
}
FILTERS = ('clouds', 'water', 'snow', 'aerosols')
MEASURES = {  # variables whose signal a filter removes
	'water': {'NDWI', 'Chl-a', 'NDCI'},  # open water and water quality
	'snow': {'NDSI', 'SCF'},
	'aerosols': {'ARSL'},
}
S2_SCL = {'clouds': [3, 8, 9, 10], 'water': [6], 'snow': [11]}  # cloud shadow, clouds, cirrus; water; snow

# Snow cover frequency (SCF) of Landsat: the % of the clear observations of each pixel with snow or ice, the mean of
# its images, each 100 (snow) or 0 (no snow). The method of the study of the snow of Sierra Nevada and its glacial
# lakes (OBSNEV), for the whole massif and its north and south slopes, 1985-2026:
#   - in the sun: snow if NDSI >= 0.35, green > 0.1 and NIR > 0.1 (surface reflectance); the green and NIR thresholds
#     discard dark surfaces and water, which can also have a high NDSI. The pixels flagged as water (QA_PIXEL bit 7)
#     are removed (filter 'water');
#   - in the shadow of the relief (ee.Terrain.hillShadow over the SRTM with the sun of each scene): snow in shadow only
#     gets diffuse light and does not reach those thresholds, and the surface reflectance of Landsat 8 and 9 is
#     negative there. Above 1500 m, snow if NDSI >= 0.35 and green >= 0.08 of the TOA reflectance (the water flag is
#     ignored: in shadow it marks shadow, not water); below 1500 m, no data (snow is rare there and the threshold was
#     not checked);
#   - clouds (filter 'clouds'): QA_PIXEL bit 3 (cloud) or bit 9 (medium or high cloud confidence); cloud shadows are
#     kept. Only scenes with CLOUD_COVER below 80 %. The filters of snow and aerosols do not apply.
SCF = {
	'ndsi': 0.35,           # minimum NDSI of snow (surface reflectance in the sun, TOA in the shadow)
	'green': 0.1,           # green and NIR surface reflectance of snow in the sun: above these
	'nir': 0.1,
	'toa_green': 0.08,      # green TOA reflectance of snow in the shadow: at least this
	'min_elevation': 1500,  # metres: pixels in the shadow below it have no data
	'shadow_reach': 70,     # reach of the shadows cast by the relief, in pixels (neighborhoodSize of hillShadow)
	'scene_clouds': 80,     # scenes with a CLOUD_COVER (%) below it
	'dem': 'USGS/SRTMGL1_003',
}
SCF_TOA = {  # TOA collection of each Landsat collection, with its green and SWIR1 bands
	'LANDSAT/LT05/C02/T1_L2': ('LANDSAT/LT05/C02/T1_TOA', ['B2', 'B5']),
	'LANDSAT/LE07/C02/T1_L2': ('LANDSAT/LE07/C02/T1_TOA', ['B2', 'B5']),
	'LANDSAT/LC08/C02/T1_L2': ('LANDSAT/LC08/C02/T1_TOA', ['B3', 'B6']),
	'LANDSAT/LC09/C02/T1_L2': ('LANDSAT/LC09/C02/T1_TOA', ['B3', 'B6']),
}
SCF_FILTERS = {'clouds', 'water'}  # fixed: the SCF is the % of the clear observations (see fixed_filters)
CF_CLOUD_SCORE = 0.6  # cloud frequency of Sentinel-2: a pixel is cloud when its Cloud Score+ (cs_cdf) is below it


def is_scf(entry):
	"""Whether ENTRY is the snow cover frequency (formula SCF(green,nir,swir1))."""
	return str(entry.get('ft', '')).replace(' ', '').upper().startswith('SCF(')


def is_cf(entry):
	"""Whether ENTRY is the cloud frequency (formula CF(band of the cloud flags))."""
	return str(entry.get('ft', '')).replace(' ', '').upper().startswith('CF(')


def fixed_filters(entry):
	"""Pixel filters always on for ENTRY, whatever the quality, or None if they can be chosen: those of the snow cover
	frequency, clouds and water (never snow, what it measures, nor aerosols); none for the fixed layers without dates
	(elevation and slope) and for the cloud frequency (clouds are what it measures)."""
	if entry.get('static') or is_cf(entry):
		return []
	return [f for f in FILTERS if f in SCF_FILTERS] if is_scf(entry) else None


def bits(band, first, last=None):
	"""Value of the bits FIRST to LAST of a QA band."""
	last = first if last is None else last
	return band.rightShift(first).bitwiseAnd((1 << (last - first + 1)) - 1)


def _modis_cloud_state(qa):
	# bits 3-4: 0 clear, 1 cloudy, 2 mixed, 3 not set (assumed clear)
	state = bits(qa, 3, 4)
	return state.eq(0).Or(state.eq(3))


def _vi_clouds(i):
	# MOD13Q1: SummaryQA 3 = cloudy; DetailedQA bit 8 adjacent cloud, 10 mixed clouds, 15 shadow
	qa = i.select('DetailedQA')
	return i.select('SummaryQA').neq(3).And(bits(qa, 8).eq(0)).And(bits(qa, 10).eq(0)).And(bits(qa, 15).eq(0))


# MODIS (and other) products: band of valid raw values (flags above max) and the mask of each pixel filter
# {collection: {'valid': (band, max raw value), filter: f(img) -> 1 = keep}}
PRODUCTS = {
	'MODIS/061/MOD13Q1': {  # DetailedQA: bits 6-7 aerosols (3 high), 11-13 land/water (1 land), 14 snow/ice
		'clouds': _vi_clouds,
		'water': lambda i: bits(i.select('DetailedQA'), 11, 13).eq(1),
		'snow': lambda i: i.select('SummaryQA').neq(2).And(bits(i.select('DetailedQA'), 14).eq(0)),
		'aerosols': lambda i: bits(i.select('DetailedQA'), 6, 7).neq(3),
	},
	'MODIS/061/MOD11A1': {'clouds': lambda i: bits(i.select('QC_Day'), 0, 1).eq(0)},  # LST of good quality
	'MODIS/061/MOD16A2': {'valid': ('ET', 32700), 'clouds': lambda i: _modis_cloud_state(i.select('ET_QC'))},
	'MODIS/061/MCD15A3H': {  # FparExtra_QC: bits 0-1 land/sea (0 land), 2 snow, 3 aerosol, 4 cirrus, 5 cloud, 6 shadow
		'valid': ('Lai', 100),
		'clouds': lambda i: _modis_cloud_state(i.select('FparLai_QC')).And(bits(i.select('FparExtra_QC'), 4, 6).eq(0)),
		'water': lambda i: bits(i.select('FparExtra_QC'), 0, 1).eq(0),
		'snow': lambda i: bits(i.select('FparExtra_QC'), 2).eq(0),
		'aerosols': lambda i: bits(i.select('FparExtra_QC'), 3).eq(0),
	},
	# NDSI_Snow_Cover 200-255 are flags (the classes of NDSI_Snow_Cover_Class: 237 inland water, 239 ocean,
	# 250 cloud, ...), not values: masked always
	'MODIS/061/MOD10A1': {
		'valid': ('NDSI_Snow_Cover', 100),
		'clouds': lambda i: i.select('NDSI_Snow_Cover_Class').unmask(0).neq(250),
		'water': lambda i: i.select('NDSI_Snow_Cover_Class').unmask(0).remap([237, 239], [0, 0], 1),
	},
	'MODIS/061/MCD19A2_GRANULES': {  # AOD_QA: bits 0-2 cloud mask (1 clear), 3-4 land (0), water (1), snow, ice
		'clouds': lambda i: bits(i.select('AOD_QA'), 0, 2).eq(1),
		'water': lambda i: bits(i.select('AOD_QA'), 3, 4).neq(1),
		'snow': lambda i: bits(i.select('AOD_QA'), 3, 4).lt(2),
	},
	# 0 = full BRDF inversion, 1 = magnitude inversion (too few clear observations)
	'MODIS/061/MCD43A3': {'clouds': lambda i: i.select('BRDF_Albedo_Band_Mandatory_Quality_shortwave').eq(0)},
}
PRODUCTS['MODIS/061/MYD13Q1'] = PRODUCTS['MODIS/061/MOD13Q1']
PRODUCTS['MODIS/061/MYD11A1'] = PRODUCTS['MODIS/061/MOD11A1']
PRODUCTS['MODIS/061/MYD10A1'] = PRODUCTS['MODIS/061/MOD10A1']


def filters(entry, quality=None):
	"""Pixel filters (clouds, water, snow, aerosols) that apply to ENTRY with QUALITY: {filter: True/False}, with
	'auto' resolved and False for the filters its sensor has no QA band for (e.g. aerosols of Sentinel-2); with fixed
	filters (the SCF), those, whatever QUALITY says."""
	fixed = fixed_filters(entry)
	if fixed is not None:
		return {f: f in fixed for f in FILTERS}
	quality = dict(QUALITY, **(quality or {}))
	sensor, col = entry['sensor'], entry['col']
	available = {'Sentinel-2': {'clouds', 'water', 'snow'}, 'Landsat': set(FILTERS)}.get(sensor)
	if available is None:
		available = {f for f in FILTERS if f in PRODUCTS.get(col, {})}
	out = {}
	for f in FILTERS:
		on = quality[f]
		if str(on).lower() == 'auto':
			on = entry['index'] not in MEASURES.get(f, ())
		out[f] = bool(on) and f in available
	return out


def conflicts(entry, quality=None):
	"""Filters on for ENTRY that remove what its variable measures (e.g. snow for NDSI)."""
	on = filters(entry, quality)
	return [f for f in FILTERS if on[f] and entry['index'] in MEASURES.get(f, ())]

_band_names = {}


def number(v, default):
	"""Number of a field of the catalog ('#' or missing = DEFAULT)."""
	try:
		return float(v)
	except (TypeError, ValueError):
		return default


def band_names(entry):
	"""Band names of the images of the collection of ENTRY."""
	if entry['sensor'] == 'Landsat':
		return list(LANDSAT_89.values())
	col = entry['col']
	if col not in _band_names:
		_band_names[col] = ee.ImageCollection(col).first().bandNames().getInfo()
	return _band_names[col]


def parse_formula(entry):
	"""(kind, bands) of the formula of ENTRY: ('nd', [b1, b2]) for N(b1,b2), ('scf', [green, nir, swir1]) for
	SCF(green,nir,swir1), ('static', [band]) for the fixed layers (elevation and slope: an image, see
	variable.is_static), else ('expr', {name: band}) with the band of every name of the expression (matched without
	case)."""
	if entry.get('static'):
		return 'static', [entry['band']]
	if is_cf(entry):  # the band of the cloud flags (cs_cdf of Sentinel-2 comes from Cloud Score+, not from the images)
		return 'cf', [entry['ft'].strip()[3:-1].strip()]
	ft = entry['ft'].strip()
	names = band_names(entry)
	lower = {b.lower(): b for b in names}

	def band(name):
		b = lower.get(name.strip().lower())
		if b is None:
			raise ValueError(f"band {name.strip()} of the formula {ft} of {entry['index']} ({entry['sensor']}) "
			                 f"not found; bands: {', '.join(names)}")
		return b

	if ft.startswith('N(') and ft.endswith(')'):
		return 'nd', [band(b) for b in ft[2:-1].split(',')]
	if is_scf(entry) and ft.endswith(')'):
		return 'scf', [band(b) for b in ft[ft.index('(') + 1:-1].split(',')]
	return 'expr', {name: band(name) for name in set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', ft))}


def quality_mask(img, entry, quality):
	"""Mask of the pixels of an image of the collection of ENTRY that pass the pixel filters of QUALITY
	(None = no mask)."""
	sensor, col = entry['sensor'], entry['col']
	on = filters(entry, quality)
	masks = []
	if sensor == 'Sentinel-2':
		scl = img.select('SCL')
		for f, classes in S2_SCL.items():
			if not on[f]:
				continue
			if f == 'clouds' and quality.get('cloud_score') is not None:
				masks.append(img.select('cs_cdf').gte(quality['cloud_score']))
			else:
				masks.append(scl.remap(classes, [0] * len(classes), 1))
	elif sensor == 'Landsat':
		qa = img.select('QA_PIXEL')
		if on['clouds']:
			masks.append(bits(qa, 1, 4).eq(0))  # dilated cloud, cirrus, cloud, cloud shadow
		if on['snow']:
			masks.append(bits(qa, 5).eq(0))
		if on['water']:
			masks.append(bits(qa, 7).eq(0))
		if on['aerosols']:
			masks.append(bits(img.select('SR_QA_AEROSOL'), 6, 7).neq(3))  # aerosol level 3 = high
	else:
		product = PRODUCTS.get(col, {})
		if 'valid' in product:
			b, vmax = product['valid']
			masks.append(img.select(b).lte(vmax))
		masks += [product[f](img) for f in FILTERS if on[f]]
	if not masks:
		return None
	mask = masks[0]
	for m in masks[1:]:
		mask = mask.And(m)
	return mask


def _with_toa(col, col_id, region, start, end):
	"""Images of COL (of the Landsat collection COL_ID) with the bands toa_green and toa_swir1 of the same scene in
	the TOA collection (the scenes without it are left out)."""
	toa_id, bands = SCF_TOA[col_id]
	toa = ee.ImageCollection(toa_id).filterBounds(region).filterDate(start, end)
	same = ee.Filter.equals(leftField='system:index', rightField='system:index')
	joined = ee.ImageCollection(ee.Join.saveFirst('toa').apply(col, toa, same))
	return joined.map(lambda i: ee.Image(i).addBands(ee.Image(ee.Image(i).get('toa')).select(bands, ['toa_green', 'toa_swir1'])))


def raw_collection(entry, region, start, end, quality):
	"""Images of the collection of ENTRY over REGION between START and END (excluded), with the band names of the
	formulas, filtered by the scene cloud cover if asked (and, for the SCF, with its scene filter and the TOA
	bands)."""
	sensor = entry['sensor']
	prop = SCENE_CLOUDS.get(sensor)
	scene = quality.get('scene_clouds')

	def scene_filter(col):
		return col.filter(ee.Filter.lte(prop, scene)) if prop and scene is not None else col

	if sensor == 'Landsat':
		scf = is_scf(entry)
		cols = []
		for col_id, aliases, last in LANDSAT:
			end_l = min(end, last) if last else end
			if end_l <= start:
				continue
			c = scene_filter(ee.ImageCollection(col_id).filterBounds(region).filterDate(start, end_l))
			if scf:
				c = c.filter(ee.Filter.lt('CLOUD_COVER', SCF['scene_clouds']))
			c = c.select(list(aliases), list(aliases.values()))
			if 'SR_QA_AEROSOL' not in aliases:  # Landsat 5 and 7 have no aerosol QA: nothing is removed
				c = c.map(lambda i: i.addBands(ee.Image.constant(0).toUint8().rename('SR_QA_AEROSOL')))
			if scf:
				c = _with_toa(c, col_id, region, start, end_l)
			cols.append(c)
		col = cols[0]
		for c in cols[1:]:
			col = col.merge(c)
		return col
	col = scene_filter(ee.ImageCollection(entry['col']).filterBounds(region).filterDate(start, end))
	if sensor == 'Sentinel-2' and filters(entry, quality)['clouds'] and quality.get('cloud_score') is not None:
		col = col.linkCollection(ee.ImageCollection(CLOUD_SCORE), ['cs_cdf'])
	return col


def collection(entry, region, start, end, quality=None, resample=None):
	"""Collection of single band images ('value', float) of the variable of ENTRY over REGION between START and END
	(dates 'YYYY-MM-DD', END excluded), with the quality masks of QUALITY (see QUALITY) and, if given, the
	resampling method RESAMPLE ('bilinear' or 'bicubic') of the bands when the output pixels are smaller."""
	quality = dict(QUALITY, **(quality or {}))
	scale = number(entry.get('scale'), 1.0)
	offset = number(entry.get('offset'), 0.0)
	kind, bands = parse_formula(entry)
	if kind == 'scf':
		return scf_collection(entry, region, start, end, quality, resample)
	if kind == 'cf':
		return cf_collection(entry, region, start, end, quality)
	used = list(bands) if kind == 'nd' else sorted(set(bands.values()))

	def compute(img):
		img = ee.Image(img)
		data = img.select(used).multiply(scale).add(offset)
		if resample:
			data = data.resample(resample)
		mask = quality_mask(img, entry, quality)
		if mask is not None:
			data = data.updateMask(mask)
		if kind == 'nd':
			out = data.normalizedDifference(bands)
		else:
			out = data.expression(entry['ft'], {name: data.select(b) for name, b in bands.items()})
		return out.toFloat().rename('value').copyProperties(img, ['system:time_start'])

	return raw_collection(entry, region, start, end, quality).map(compute)


def scf_collection(entry, region, start, end, quality, resample=None):
	"""Collection of single band images ('value', float) of the snow of the SCF (see SCF): 100 where a valid
	observation has snow, 0 where it has none, masked where there is no valid observation."""
	_, (green, nir, swir1) = parse_formula(entry)
	scale = number(entry.get('scale'), 1.0)
	offset = number(entry.get('offset'), 0.0)
	dem = ee.Image(SCF['dem'])
	high = dem.gte(SCF['min_elevation'])

	def compute(img):
		img = ee.Image(img)
		sr = img.select([green, nir, swir1]).multiply(scale).add(offset)
		toa = img.select(['toa_green', 'toa_swir1'])
		if resample:
			sr, toa = sr.resample(resample), toa.resample(resample)
		g, n, s = sr.select(green), sr.select(nir), sr.select(swir1)
		snow_sun = g.subtract(s).divide(g.add(s)).gte(SCF['ndsi']).And(g.gt(SCF['green'])).And(n.gt(SCF['nir']))
		tg, ts = toa.select('toa_green'), toa.select('toa_swir1')
		snow_shade = tg.subtract(ts).divide(tg.add(ts)).gte(SCF['ndsi']).And(tg.gte(SCF['toa_green']))
		zenith = ee.Number(90).subtract(ee.Number(img.get('SUN_ELEVATION')))
		lit = ee.Terrain.hillShadow(dem, ee.Number(img.get('SUN_AZIMUTH')), zenith, SCF['shadow_reach'], True)
		shade = lit.Not()
		qa = img.select('QA_PIXEL')
		clear = bits(qa, 3).eq(0).And(bits(qa, 9).eq(0))  # its fixed filters (SCF_FILTERS): clouds and water
		dry = bits(qa, 7).eq(0)
		valid_sun = lit.And(clear).And(dry).And(snow_sun.mask())
		valid_shade = shade.And(high).And(clear.unmask(0)).And(snow_shade.mask())
		snow = snow_sun.unmask(0).And(lit).Or(snow_shade.unmask(0).And(shade))
		valid = valid_sun.unmask(0).Or(valid_shade.unmask(0))
		return snow.multiply(100).updateMask(valid).toFloat().rename('value').copyProperties(img, ['system:time_start'])

	return raw_collection(entry, region, start, end, quality).map(compute)


def cf_collection(entry, region, start, end, quality):
	"""Collection of single band images ('value', float) of the clouds of the cloud frequency (CF): 100 where the cloud
	flags of an image say cloud, 0 where they say clear, masked where the image has no data. MODIS: state_1km bits 0-1
	cloudy (1) or mixed (2); Sentinel-2: Cloud Score+ cs_cdf below CF_CLOUD_SCORE; Landsat: QA_PIXEL bit 3 (cloud) or
	bit 9 (medium or high cloud confidence), without the fill pixels (bit 0)."""
	sensor = entry['sensor']
	if sensor == 'Sentinel-2':
		col = ee.ImageCollection(entry['col']).filterBounds(region).filterDate(start, end)
		col = col.linkCollection(ee.ImageCollection(CLOUD_SCORE), ['cs_cdf'])

		def compute(img):
			img = ee.Image(img)
			return img.select('cs_cdf').lt(CF_CLOUD_SCORE).multiply(100)
	elif sensor == 'Landsat':
		col = raw_collection(entry, region, start, end, quality)

		def compute(img):
			img = ee.Image(img)
			qa = img.select('QA_PIXEL')
			cloud = bits(qa, 3).eq(1).Or(bits(qa, 9).eq(1))
			return cloud.multiply(100).updateMask(bits(qa, 0).eq(0))
	else:  # MODIS
		col = ee.ImageCollection(entry['col']).filterBounds(region).filterDate(start, end)

		def compute(img):
			img = ee.Image(img)
			state = bits(img.select('state_1km'), 0, 1)
			return state.eq(1).Or(state.eq(2)).multiply(100)

	return col.map(lambda img: compute(img).toFloat().rename('value').copyProperties(ee.Image(img),
	                                                                                ['system:time_start']))
