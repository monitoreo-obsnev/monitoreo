"""Area of each class over each feature of a region, in hectares and in % of the area with classes (as the zonal
statistics by group of geemap, Wu 2020): the classes of

  landcover  a land cover map of a year (monitoreo.landcover: ESA WorldCover, Dynamic World, CORINE Land Cover, MODIS
             MCD12Q1), each class of the map with its broad land cover;
  breaks     the map of a variable (also of a fixed layer: elevation, slope) cut at some values, e.g. [0.2, 0.4, 0.6]:
             below 0.2, 0.2 to 0.4, 0.4 to 0.6 and 0.6 or more (a value equal to a break goes to the class above it);
  trend      the trend of a variable on each pixel (Mann-Kendall and Sen, see monitoreo.trends): significant decrease
             (p-value below alpha and slope below 0), no significant trend, and significant increase.

The area of each pixel is its true area on the ground (ee.Image.pixelArea), summed by class over each feature on a
grid of the pixel of the data (bigger over big regions, see scale_for). The pixels without data (no class, or masked
by the pixel filters, the land cover mask or where) are not counted: the % is of the area with a class.

    Wu, Q. (2020). geemap: A Python package for interactive mapping with Google Earth Engine. Journal of Open Source
      Software, 5(51), 2305. https://doi.org/10.21105/joss.02305
"""

import math

import ee

from . import landcover

MODES = ('landcover', 'breaks', 'trend')
TREND = [(-1, 'significant decrease', 'd7191c'), (0, 'no significant trend', 'bdbdbd'),
         (1, 'significant increase', '1a9641')]
TARGET_PIXELS = 1e7  # pixels per region for the automatic scale (the areas are sums: they need fewer than a map)
COLUMNS = {'landcover': ['region', 'map', 'year', 'class', 'label', 'landcover', 'ha', 'percent'],
           'breaks': ['region', 'class', 'label', 'value_from', 'value_to', 'ha', 'percent'],
           'trend': ['region', 'class', 'label', 'ha', 'percent']}
# colours of the broad land covers (those of Dynamic World, whose classes they are: see monitoreo.landcover)
LANDCOVER_COLOURS = {'water': '419bdf', 'trees': '397d49', 'grassland': '88b053', 'wetland': '7a87c6',
                     'cropland': 'e49635', 'shrubland': 'dfc35a', 'built': 'c4281b', 'bare': 'a59b8f',
                     'snow': 'b39fe1'}


def mode_of(landcover_map=None, breaks=None, trend=False):
	"""The kind of classes of a call: 'landcover', 'breaks' or 'trend'; ValueError (before Earth Engine) if it gives
	none or more than one."""
	given = [m for m, v in (('landcover', landcover_map), ('breaks', breaks), ('trend', trend)) if v]
	if len(given) != 1:
		raise ValueError('give one kind of classes: landcover (a land cover map, with its year), breaks (the values '
		                 'where to cut the map of a variable, e.g. [0.2, 0.4]) or trend (the trend of a variable: '
		                 'significant decrease, no trend, increase)' + (f"; not {' and '.join(given)}" if given else ''))
	return given[0]


def check_breaks(breaks):
	"""BREAKS as an increasing list of numbers (ValueError if it is not)."""
	if isinstance(breaks, str):
		breaks = [b for b in breaks.replace(';', ',').split(',') if b.strip()]
	try:
		out = [float(b) for b in breaks]
	except (TypeError, ValueError):
		raise ValueError(f'breaks are numbers, e.g. [0.2, 0.4, 0.6]; not {breaks!r}') from None
	if not out or any(not math.isfinite(b) for b in out):
		raise ValueError('give at least one break, e.g. [0.2, 0.4, 0.6]')
	if any(b2 <= b1 for b1, b2 in zip(out, out[1:])):
		raise ValueError(f'breaks go from the lowest to the highest, each once: {out}')
	return out


def _num(x):
	return f'{x:g}'


def break_classes(breaks, unit=''):
	"""[(class, label, from, to)] of the classes of BREAKS: class 0 below the first one, ..., len(BREAKS) from the last
	one (from and to None where there is no limit); the labels with UNIT."""
	u = f' {unit}' if unit else ''
	out = [(0, f'below {_num(breaks[0])}{u}', None, breaks[0])]
	for i, (a, b) in enumerate(zip(breaks, breaks[1:]), 1):
		out.append((i, f'{_num(a)} to {_num(b)}{u}', a, b))
	out.append((len(breaks), f'{_num(breaks[-1])}{u} or more', breaks[-1], None))
	return out


def classify_breaks(value, breaks):
	"""The class (0 to len(BREAKS)) of each pixel of the single band image VALUE, masked where it is."""
	out = ee.Image.constant(0).updateMask(ee.Image(value).mask().select(0))
	for b in breaks:
		out = out.add(ee.Image(value).gte(b))
	return out.toInt().rename('class')


def classify_trend(trend, alpha=0.05):
	"""The class of TREND (an image of monitoreo.trends.trend_image: bands slope and p_value) on each pixel: -1
	significant decrease, 0 no significant trend, 1 significant increase (Mann-Kendall p-value below ALPHA), masked
	where the trend is (fewer than 2 years)."""
	trend = ee.Image(trend)
	significant = trend.select('p_value').lt(alpha)
	slope = trend.select('slope')
	return significant.multiply(slope.gt(0).subtract(slope.lt(0))).toInt().rename('class').updateMask(slope.mask())


def landcover_map(key, year=None):
	"""(map, year) of the land cover map KEY (see monitoreo.landcover.maps) of YEAR (default: its last), or
	ValueError."""
	m, year, _ = landcover.check({'landcover': key, 'year': year, 'exclude': [landcover.classes()[0]['key']]})
	return m, year


def source(m, year, region=None):
	"""The image of the classes (band 'class') of the land cover map M of YEAR (see monitoreo.landcover.source)."""
	return landcover.source(m, year, region).rename('class')


def landcover_classes(m):
	"""[(code, name of the class in the map, broad land cover)] of the classes of the land cover map M."""
	return [(int(code), m['names'][code], k) for code, k in sorted(m['classes'].items(), key=lambda x: int(x[0]))]


def scale_for(native, regions):
	"""The pixel size (m) of the areas over REGIONS: that of the data, or bigger so that the biggest region has about
	TARGET_PIXELS pixels (rounded to 10, 20, 50, 100, ... m)."""
	area = regions.map(lambda f: ee.Feature(None, {'a': f.geometry().area(1)})).aggregate_max('a').getInfo() or 0
	need = math.sqrt(area / TARGET_PIXELS) if area else native
	if need <= native:
		return float(native)
	nice = [m * 10 ** e for e in range(1, 6) for m in (1, 2, 5)]
	return float(next((n for n in nice if n >= need), nice[-1]))


def hectares(classes_img, regions, scale, crs):
	"""[(region, {class: hectares})] of the image of classes CLASSES_IMG (band 'class') over each feature of REGIONS,
	one for each feature in their order (region: its name; features with the same name, e.g. the areas of a wdpa_name,
	each with its own, as region_stats), on pixels of SCALE metres in CRS (the true area of each pixel)."""
	img = ee.Image.pixelArea().divide(1e4).updateMask(ee.Image(classes_img).mask()).addBands(classes_img)
	fc = img.reduceRegions(collection=regions, reducer=ee.Reducer.sum().group(1, 'class'), scale=scale, crs=crs,
	                       tileScale=4).getInfo()['features']
	return [(str(f['properties'].get('name')), {int(g['class']): g['sum'] for g in f['properties'].get('groups') or []})
	        for f in fc]


def rows(ha, classes, extra=None):
	"""Rows [{region, class, label, ..., ha, percent}] of every class of CLASSES ([(class, label, {more columns})]) in
	each feature of HA ([(region, {class: hectares})], see hectares), with the columns of EXTRA in each one; percent of
	the area with a class of the feature (None if it has none)."""
	out = []
	for region, by in ha:
		total = sum(by.get(c, 0.0) for c, _, _ in classes)
		for c, label, more in classes:
			h = by.get(c, 0.0)
			out.append(dict({'region': region}, **(extra or {}), **{'class': c, 'label': label}, **more,
			                ha=h, percent=100 * h / total if total else None))
	return out


def by_landcover(ha, classes):
	"""The hectares of each feature of HA ([(region, {class: hectares})], see hectares) of the classes of a land cover
	map (CLASSES: [(class, label, {'landcover': its broad land cover})]) summed by broad land cover: [{region,
	landcover, label, ha, percent}], in the order of the features and of the broad land covers; percent of the area with
	a class of the feature (None if it has none)."""
	order = [c['key'] for c in landcover.classes()]
	out = []
	for region, by in ha:
		total = sum(by.get(c, 0.0) for c, _, _ in classes)
		acc = {}
		for c, _, more in classes:
			acc[more['landcover']] = acc.get(more['landcover'], 0.0) + by.get(c, 0.0)
		for k in sorted(acc, key=lambda k: order.index(k) if k in order else len(order)):
			out.append({'region': region, 'landcover': k, 'label': landcover.label(k), 'ha': acc[k],
			            'percent': 100 * acc[k] / total if total else None})
	return out
