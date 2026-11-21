"""Area of each class over each feature of a region, in hectares and in % of the area with classes (as the zonal
statistics by group of geemap, Wu 2020): the classes of

  landcover  a land cover map of a year (monitoreo.landcover: ESA WorldCover, Dynamic World, CORINE Land Cover, MODIS
             MCD12Q1), each class of the map with its broad land cover;
  breaks     the map of a variable (also of a fixed layer: elevation, slope) cut at some values, e.g. [0.2, 0.4, 0.6]:
             below 0.2, 0.2 to 0.4, 0.4 to 0.6 and 0.6 or more (a value equal to a break goes to the class above it);
  trend      the trend of a variable on each pixel (Mann-Kendall and Sen, see monitoreo.trends): significant decrease
             (p-value below alpha and slope below 0), no significant trend, and significant increase;
  classes    the classes of a categorical layer (monitoreo.categorical: the ecoregions and biomes of RESOLVE), its own
             classes, those with area in some feature of the region; the ecoregions with their biome (group), and the
             hectares of each biome (by_group).

The changes between two years of a land cover map (transitions) are the area of each pair of classes (the class of the
pixel in the first year and in the other), as the Sankey diagrams of land cover change that geemap draws: each class
of the map and each broad land cover, the unchanged area (the same class in both years) and a Sankey diagram of the
broad land covers.

The area of each pixel is its true area on the ground (ee.Image.pixelArea), summed by class over each feature on a
grid of the pixel of the data (bigger over big regions, see scale_for). The pixels without data (no class, or masked
by the pixel filters, the land cover mask or where) are not counted: the % is of the area with a class.

    Wu, Q. (2020). geemap: A Python package for interactive mapping with Google Earth Engine. Journal of Open Source
      Software, 5(51), 2305. https://doi.org/10.21105/joss.02305
"""

import math

import ee

from . import landcover

MODES = ('landcover', 'breaks', 'trend', 'classes')
TREND = [(-1, 'significant decrease', 'd7191c'), (0, 'no significant trend', 'bdbdbd'),
         (1, 'significant increase', '1a9641')]
TARGET_PIXELS = 1e7  # pixels per region for the automatic scale (the areas are sums: they need fewer than a map)
COLUMNS = {'landcover': ['region', 'map', 'year', 'class', 'label', 'landcover', 'ha', 'percent'],
           'transitions': ['region', 'map', 'year', 'other_year', 'from_class', 'from_label', 'from_landcover',
                           'to_class', 'to_label', 'to_landcover', 'ha', 'percent'],
           'breaks': ['region', 'class', 'label', 'value_from', 'value_to', 'ha', 'percent'],
           'trend': ['region', 'class', 'label', 'ha', 'percent'],
           # the classes of a categorical layer (the ecoregions with their biome, group; the biomes without it)
           'classes': ['region', 'class', 'label', 'group', 'group_label', 'ha', 'percent']}
# colours of the broad land covers (those of Dynamic World, whose classes they are: see monitoreo.landcover)
LANDCOVER_COLOURS = {'water': '419bdf', 'trees': '397d49', 'grassland': '88b053', 'wetland': '7a87c6',
                     'cropland': 'e49635', 'shrubland': 'dfc35a', 'built': 'c4281b', 'bare': 'a59b8f',
                     'snow': 'b39fe1'}


def mode_of(landcover_map=None, breaks=None, trend=False, categorical=None):
	"""The kind of classes of a call: 'landcover', 'breaks', 'trend' or, for a CATEGORICAL layer (its entry, see
	monitoreo.categorical) without the others, 'classes'; ValueError (before Earth Engine) if it gives none or more than
	one, or breaks or a trend for a categorical layer, which has its own classes."""
	given = [m for m, v in (('landcover', landcover_map), ('breaks', breaks), ('trend', trend)) if v]
	if categorical and not landcover_map:
		if given:
			raise ValueError(f"the classes of {categorical['index']} ({categorical['sensor']}) are its own (a categorical "
			                 f"layer, of class codes): give no {' nor '.join(given)}")
		return 'classes'
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
	significant decrease, 0 no significant trend, 1 significant increase (p-value of its trend test below ALPHA), masked
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
	TARGET_PIXELS pixels (rounded to 10, 20, 50, 100, ... m); in a large area (more than areas.LARGE_AREA_KM2), 1 to 10
	km, never finer than the data (areas.default_scale)."""
	from . import areas
	return areas.default_scale(native, areas.max_area(regions), TARGET_PIXELS)


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


def by_group(ha, classes, group):
	"""The hectares of each feature of HA ([(region, {class: hectares})], see hectares) of the classes of a categorical
	layer (CLASSES: [(class, label, {'group': its group, ...})], the ecoregions with their biome) summed by group: [{region,
	group, label, ha, percent}], in the order of the features and of the codes of the groups, only those with area;
	GROUP is the categorical entry of the groups (BIOME), for their labels; percent of the area with a class of the
	feature (None if it has none)."""
	from . import categorical
	out = []
	for region, by in ha:
		total = sum(by.get(c, 0.0) for c, _, _ in classes)
		acc = {}
		for c, _, more in classes:
			if by.get(c):
				acc[more['group']] = acc.get(more['group'], 0.0) + by[c]
		for g in sorted(acc):
			out.append({'region': region, 'group': g, 'label': categorical.label(group, g), 'ha': acc[g],
			            'percent': 100 * acc[g] / total if total else None})
	return out


# Changes of a land cover map between two years -----------------------------------------------------------------------

PAIR = 1000  # the pair of classes of a pixel: its class in the first year × PAIR + its class in the other (< 1000)


def pairs(first, other):
	"""The image of the pair of classes of each pixel (band 'class'): its class in the image FIRST × PAIR + its class in
	OTHER, masked where either is."""
	return ee.Image(first).multiply(PAIR).add(ee.Image(other)).toInt().rename('class')


def numbered(ha):
	"""HA ([(region, {...})], see hectares) with the features of the same name numbered from the second one ('Sierra
	Nevada (2)'), as the viewer names them, so that the changes of each one stay apart."""
	seen, out = {}, []
	for region, by in ha:
		seen[region] = seen.get(region, 0) + 1
		out.append((region if seen[region] == 1 else f'{region} ({seen[region]})', by))
	return out


def transition_rows(ha, m, year, other_year):
	"""Rows [{region, map, year, other_year, from_class, from_label, from_landcover, to_class, to_label, to_landcover,
	ha, percent}] of the pairs of classes with area of each feature of HA ([(region, {pair: hectares})], see hectares
	and pairs; those of the same name numbered, see numbered) of the land cover map M, sorted by hectares; percent of
	the area with a class in both years."""
	names = {code: (f'{code} {name}', k) for code, name, k in landcover_classes(m)}
	out = []
	for region, by in numbered(ha):
		total = sum(by.values())
		for pair, h in sorted(by.items(), key=lambda x: -x[1]):
			a, b = divmod(int(pair), PAIR)
			fa, fb = names.get(a, (str(a), None)), names.get(b, (str(b), None))
			out.append({'region': region, 'map': m['name'], 'year': year, 'other_year': other_year, 'from_class': a,
			            'from_label': fa[0], 'from_landcover': fa[1], 'to_class': b, 'to_label': fb[0],
			            'to_landcover': fb[1], 'ha': h, 'percent': 100 * h / total if total else None})
	return out


def broad_transitions(rows):
	"""The ROWS of transition_rows summed by broad land cover: [{region, from_landcover, from_label, to_landcover,
	to_label, ha, percent}], in the order of the broad land covers."""
	acc = {}
	for r in rows:
		k = (r['region'], r['from_landcover'], r['to_landcover'])
		acc.setdefault(k, {'region': r['region'], 'from_landcover': r['from_landcover'],
		                   'from_label': landcover.label(r['from_landcover']), 'to_landcover': r['to_landcover'],
		                   'to_label': landcover.label(r['to_landcover']), 'ha': 0.0, 'percent': 0.0})
		acc[k]['ha'] += r['ha']
		acc[k]['percent'] += r['percent'] or 0.0
	order = [c['key'] for c in landcover.classes()]
	pos = lambda k: order.index(k) if k in order else len(order)
	return sorted(acc.values(), key=lambda r: (r['region'], pos(r['from_landcover']), pos(r['to_landcover'])))


def changed(rows):
	"""{region: (changed hectares, unchanged hectares)} of the ROWS of transition_rows: a pixel is unchanged if it has
	the same class of the map in both years."""
	out = {}
	for r in rows:
		c, u = out.get(r['region'], (0.0, 0.0))
		out[r['region']] = (c, u + r['ha']) if r['from_class'] == r['to_class'] else (c + r['ha'], u)
	return out
