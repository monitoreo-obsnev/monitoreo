"""Land cover masks: the pixels of a study area of some land covers (e.g. water bodies, built-up areas) left out of a
result, after a land cover map of a year.

Each land cover map has its own classes, so the masks take a few broad land covers common to all of them (CLASSES:
water, trees, grassland, wetland, cropland, shrubland, built, bare, snow), and the table of correspondences of
catalog.json (landcover) says which classes of each map are each of them. A mask is a condition of where (see
monitoreo.variable.where_specs):

    {"landcover": "CORINE", "year": 2018, "exclude": ["water", "built"]}

landcover is one of the maps (MAPS: ESA WorldCover, Dynamic World, CORINE Land Cover, MODIS MCD12Q1), year one of its
years (by default its last one) and exclude the broad land covers to leave out. A pixel of the result is left out when
the land covers excluded cover half of it or more (on pixels more than twice as big as those of the map, the share of
its pixels of the map; otherwise, the class of the map at the pixel), and also where the map has no data (e.g. CORINE
outside Europe), as the other conditions of where.

The broad land covers are the classes of Dynamic World. The classes of ESA WorldCover go to them as Venter et al.
(2022) did; those of CORINE Land Cover, as the correspondence of the CORINE classes and the ecosystem types of MAES
(BISE, 2023); those of MODIS MCD12Q1 (IGBP), by the definitions of its classes (see 'crosswalk' of each map).

References:
    Brown, C. F., Brumby, S. P., Guzder-Williams, B., et al. (2022). Dynamic World, Near real-time global 10 m land use
    land cover mapping. Scientific Data, 9, 251. https://doi.org/10.1038/s41597-022-01307-4
    Venter, Z. S., Barton, D. N., Chakraborty, T., Simensen, T., & Singh, G. (2022). Global 10 m land use land cover
    datasets: A comparison of Dynamic World, World Cover and Esri Land Cover. Remote Sensing, 14(16), 4101.
    https://doi.org/10.3390/rs14164101
    Biodiversity Information System for Europe (2023). Correspondence between CORINE Land Cover classes and ecosystem
    types. https://biodiversity.europa.eu/maes/correspondence-between-corine-land-cover-classes-and-ecosystem-types
"""

import datetime as dt

from . import catalog

KEYS = {'landcover', 'year', 'exclude'}  # of a land cover condition of where
SHARE = 0.5  # a pixel of a result is left out when the land covers excluded cover this share of it or more


def table():
	"""The table of correspondences of catalog.json: {'classes': [{key, en, es, ...}], 'maps': [{key, name, ...}]}."""
	return catalog.load()['landcover']


def classes():
	"""The broad land covers of the masks: [{'key', 'en', 'es', 'help'}], in the order of the menus."""
	return table()['classes']


def maps():
	"""The land cover maps: [{'key', 'name', 'm' (pixel size, m), 'coverage', 'band', 'dataset', ..., 'classes' ({code:
	broad land cover}), 'names' ({code: name of the class in the map})}]."""
	return table()['maps']


def find(key):
	"""The map KEY (its key or its name, in any case, without spaces: 'dynamicworld' is Dynamic World)."""
	low = lambda s: str(s).lower().replace(' ', '').replace('_', '').replace('-', '')
	for m in maps():
		if low(key) in (low(m['key']), low(m['name'])):
			return m
	raise ValueError(f"unknown land cover map {key!r}: use one of {', '.join(m['key'] for m in maps())}")


def years(m, today=None):
	"""The years of the map M: those of its images, or from its first year to its last (to this year if it has none)."""
	if m.get('years'):
		return [int(y) for y in m['years']]
	last = m.get('last_year') or (today or dt.date.today()).year
	return list(range(int(m['first_year']), int(last) + 1))


def default_year(m, today=None):
	"""The year of the map M when a condition gives none: its last one; for a map made every year until now (Dynamic
	World), the last whole year."""
	if m.get('years') or m.get('last_year'):
		return years(m)[-1]
	return (today or dt.date.today()).year - 1


def is_landcover(condition):
	return isinstance(condition, dict) and 'landcover' in condition


def check(condition):
	"""(map, year, [broad land covers excluded]) of the land cover CONDITION of where, or ValueError with what is
	wrong (without Earth Engine)."""
	unknown = set(condition) - KEYS
	if unknown:
		raise ValueError(f"a land cover condition of where has unknown keys {', '.join(sorted(unknown))}: use "
		                 f"{', '.join(sorted(KEYS))}, e.g. {{\"landcover\": \"CORINE\", \"year\": 2018, \"exclude\": "
		                 '["water", "built"]}')
	m = find(condition['landcover'])
	year = condition.get('year')
	if year in (None, ''):
		year = default_year(m)
	try:
		year = int(year)
	except (TypeError, ValueError):
		raise ValueError(f"the year of the land cover map {m['name']} is a number, not {year!r}") from None
	ys = years(m)
	if year not in ys:
		span = ', '.join(map(str, ys)) if m.get('years') else f'{ys[0]} to {ys[-1]}'
		raise ValueError(f"{m['name']} has no map of {year}: its years are {span}")
	exclude = condition.get('exclude')
	if isinstance(exclude, str):
		exclude = [exclude]
	keys = [c['key'] for c in classes()]
	if not exclude:
		raise ValueError(f"a land cover condition of where needs exclude: the land covers to leave out, of "
		                 f"{', '.join(keys)}")
	out = []
	for x in exclude:
		k = str(x).strip().lower()
		if k not in keys:
			raise ValueError(f"unknown land cover {x!r}: use {', '.join(keys)}")
		if k not in out:
			out.append(k)
	return m, year, out


def codes(m, exclude):
	"""The classes (codes) of the map M that are the broad land covers EXCLUDE."""
	return sorted(int(code) for code, k in m['classes'].items() if k in exclude)


def source(m, year, region=None):
	"""The image of the classes of the map M of YEAR (band of the map, with its own projection)."""
	import ee
	band = m['band']
	if m.get('images'):  # an image per year (CORINE)
		return ee.Image(m['images'][str(year)]).select(band)
	if m.get('collections'):  # a collection with a single image per year (ESA WorldCover v100, v200)
		return ee.ImageCollection(m['collections'][str(year)]).first().select(band)
	col = ee.ImageCollection(m['collection']).filterDate(f'{year}-01-01', f'{year + 1}-01-01').select(band)
	if m.get('composite') == 'mode':  # the most frequent class of the images of the year (Dynamic World)
		if region is not None:
			col = col.filterBounds(region)
		return col.mode().setDefaultProjection(col.first().projection())
	return col.first()  # the image of the year (MODIS MCD12Q1)


def keep(condition, region, res):
	"""The image (1) of the pixels of RES metres kept by the land cover CONDITION, 0 where the land covers excluded
	cover SHARE of the pixel or more, masked where the map has no data."""
	import ee
	m, year, exclude = check(condition)
	cs = codes(m, exclude)
	excluded = source(m, year, region).remap(cs, [1] * len(cs), 0)  # 1: a land cover excluded; masked: no data
	if res and res > 2 * float(m['m']):
		excluded = excluded.reduceResolution(ee.Reducer.mean(), True, 65535)  # the share of the pixel excluded
	return ee.Image(1).updateMask(excluded.mask()).And(excluded.lt(SHARE))


def label(key, lang='en'):
	c = next((c for c in classes() if c['key'] == key), None)
	return (c.get(lang) or c['en']) if c else key


def text(condition, lang='en'):
	"""The land cover CONDITION in words, e.g. «the land cover is not water or built-up (CORINE Land Cover 2018)»."""
	try:
		m, year, exclude = check(condition)
	except ValueError:
		return str(condition)
	names = [label(k, lang).lower() for k in exclude]
	which = f" {'ni' if lang == 'es' else 'or'} ".join([', '.join(names[:-1]), names[-1]] if len(names) > 1 else names)
	if lang == 'es':
		return f"el uso del suelo no es {which} ({m['name']} {year})"
	return f"the land cover is not {which} ({m['name']} {year})"


def dataset(m, year):
	"""The dataset of catalog.json (its citation and credit line) of the map M of YEAR: the image of the year of CORINE
	(each year has its own DOI), the collection of the year of ESA WorldCover, or the collection of the map."""
	if m.get('images'):
		return m['images'][str(year)]
	if m.get('collections'):
		return m['collections'][str(year)]
	return m['dataset']


def all_datasets(m):
	"""The datasets of catalog.json of every year of the map M."""
	if m.get('images') or m.get('collections'):
		return list(dict.fromkeys(dataset(m, y) for y in years(m)))
	return [m['dataset']]


def citations(condition):
	"""([dataset of the map of the year], [references of its table of correspondences]) of the land cover CONDITION,
	for its citations (see monitoreo.references); nothing if it is wrong."""
	try:
		m, year, _ = check(condition)
	except (ValueError, KeyError, TypeError):
		return [], []
	return [dataset(m, year)], list(m.get('crosswalk_references') or [])


def describe(lang='en'):
	"""The land cover maps and the broad land covers of the masks, for the tools that list them: {'classes': [{key,
	name, help}], 'maps': [{key, name, resolution_m, coverage, years, default_year, dataset, how, crosswalk (how its
	classes go to the broad land covers), classes: {broad land cover: ['code name', ...]}}], 'rule'}."""
	out = {'classes': [{'key': c['key'], 'name': c.get(lang) or c['en'], 'help': c.get('help_' + lang) or c['help']}
	                   for c in classes()], 'maps': []}
	for m in maps():
		ys = years(m)
		by = {}
		for code, k in sorted(m['classes'].items(), key=lambda x: int(x[0])):
			by.setdefault(k, []).append(f"{code} {m['names'][code]}")
		out['maps'].append({'key': m['key'], 'name': m['name'], 'resolution_m': m['m'], 'coverage': m['coverage'],
		                    'years': ys if m.get('years') else f'{ys[0]}-{ys[-1]}', 'default_year': default_year(m),
		                    'dataset': m.get('dataset'), 'how': m.get('how', ''), 'crosswalk': m.get('crosswalk', ''),
		                    'classes': {c['key']: by.get(c['key'], []) for c in classes()}})
	out['rule'] = ('A pixel of the result is left out when the land covers excluded cover half of it or more, and '
	               'where the map has no data.')
	return out
