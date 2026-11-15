"""Categorical layers: fixed layers of the catalog whose values are class codes, not quantities (the field classes of
an entry, the key of its table in classes of catalog.json): the ecoregions (ECOREGION, the ECO_ID of each pixel) and
the biomes (BIOME) of RESOLVE Ecoregions 2017 (Dinerstein et al. 2017), sensor RESOLVE.

Each table gives the code, name and colour of each class (and of each ecoregion, its biome). The polygons of the
dataset are rasterized once (image): the ECO_ID of the polygon of each pixel (reduceToImage with the first feature;
the pixels outside every polygon have no data, and ECO_ID 0, Rock and Ice, is a class like the others), and the biome
of each pixel from its ECO_ID with the table (remap), so that both layers have the same boundaries. Rock and Ice is the
biome 99, a code of MonitorEO: in the data it has BIOME_NUM 11, that of Tundra.

Class codes are never interpolated nor averaged: the maps are rasterized at their own pixel and, on pixels more than
twice as big as the nominal pixel of the layer (m, 1 km), each pixel is the majority class (mode) of its pixels of m.
Their statistic over a region is the majority class (region_stats: mode); the area of each class is area_by_class;
a categorical layer gives zones by class (region_stats with zones) and conditions of where that keep some classes or
leave them out:

    {"variable": "BIOME", "sensor": "RESOLVE", "classes": [12]}
    {"variable": "ECOREGION", "sensor": "RESOLVE", "exclude": [793]}

A pixel is kept when the classes kept cover half of it or more (or the classes left out less than half), the share of
its pixels of m on pixels more than twice as big, as the land cover masks (monitoreo.landcover), and left out where
the layer has no data. Everything here but image, present and keep works without Earth Engine.

    Dinerstein, E., Olson, D., Joshi, A., et al. (2017). An ecoregion-based approach to protecting half the terrestrial
      realm. BioScience, 67(6), 534-545. https://doi.org/10.1093/biosci/bix014
"""

import re
import unicodedata

from . import catalog, landcover

SHARE = landcover.SHARE  # a pixel is kept when the classes kept cover this share of it or more (as the land covers)
STATS = ('mode', 'count')  # the statistics of a categorical layer over a region: the majority class, the pixels
DESCRIBE_MAX = 50  # describe_variable lists the classes of a layer with at most these many (else list_classes)
GAP = 'bdbdbd'  # the colour of the codes between two classes in the palette of vis (no class has them)
EXAMPLE = '{"variable": "BIOME", "sensor": "RESOLVE", "classes": [12]}'  # a condition of where on classes


def table(key):
	"""The table of classes KEY of catalog.json ('ecoregions' or 'biomes'): {'name', 'dataset', 'property', 'fields',
	'group' (the table of the groups of its classes, if they have one), 'notes', 'classes': {code: [values of
	fields]}}."""
	return catalog.load()['classes'][key]


def is_categorical(entry):
	"""Whether the catalog ENTRY is a categorical layer (it has a table of classes)."""
	return bool((entry or {}).get('classes'))


def of(entry):
	"""The table of classes of the catalog ENTRY, or None if it is not a categorical layer."""
	return table(entry['classes']) if is_categorical(entry) else None


_by_code = {}


def _rows(key):
	"""{code: {field: value}} of the table KEY, by code (read once)."""
	if key not in _by_code:
		t = table(key)
		_by_code[key] = {int(code): dict(zip(t['fields'], values)) for code, values in t['classes'].items()}
	return _by_code[key]


def codes(entry):
	"""The codes of the classes of the categorical ENTRY, from the lowest."""
	return sorted(_rows(entry['classes']))


def name(entry, code, lang='en'):
	"""The name of the class CODE of ENTRY (in Spanish with LANG 'es', if the table has it), or its code as text."""
	row = _rows(entry['classes']).get(int(code))
	if row is None:
		return str(code)
	return (row.get('name_es') if lang == 'es' else None) or row['name']


def label(entry, code, lang='en'):
	"""The class CODE of ENTRY in a legend: its code and name, e.g. «12 Mediterranean Forests, Woodlands & Scrub»."""
	return f'{int(code)} {name(entry, code, lang)}'


def colour(entry, code):
	"""The colour of the class CODE of ENTRY (hex, without #), GAP if it has none."""
	row = _rows(entry['classes']).get(int(code))
	return row['colour'] if row else GAP


def group_of(entry, code):
	"""The group of the class CODE of ENTRY (the biome of an ecoregion), or None."""
	row = _rows(entry['classes']).get(int(code))
	return row.get('group') if row else None


def group_entry(entry):
	"""The categorical entry of the groups of the classes of ENTRY (BIOME for ECOREGION), or None."""
	key = of(entry).get('group')
	if not key:
		return None
	return next((e for e in catalog.variables() if e.get('classes') == key and e['col'] == entry['col']), None)


def classes(entry, lang='en'):
	"""The classes of the categorical ENTRY: [{'code', 'name', 'colour'}] and, with groups, 'group' (its code) and
	'group_name', from the lowest code."""
	group = group_entry(entry)
	out = []
	for code, row in sorted(_rows(entry['classes']).items()):
		c = {'code': code, 'name': (row.get('name_es') if lang == 'es' else None) or row['name'],
		     'colour': row['colour']}
		if group is not None:
			c.update(group=row.get('group'), group_name=name(group, row.get('group'), lang))
		out.append(c)
	return out


def _code(x):
	"""X as the code of a class (an integer), or ValueError."""
	try:
		f = float(str(x).strip())
	except (TypeError, ValueError):
		f = None
	if f is None or f != int(f):
		raise ValueError(f'the codes of the classes are whole numbers, e.g. [12]; not {x!r}')
	return int(f)


def check(entry, values, what='classes'):
	"""VALUES (a code, a list of codes or a text with commas) as the codes of classes of ENTRY, each once, in their
	order; ValueError if one is not a code of its table, or if there are none. Without Earth Engine."""
	if isinstance(values, str):
		values = [v for v in values.replace(';', ',').split(',') if v.strip()]
	elif isinstance(values, (int, float)):
		values = [values]
	if not isinstance(values, (list, tuple)) or not values:
		raise ValueError(f"the {what} of {entry['index']} ({entry['sensor']}) are a list of codes of its classes, e.g. "
		                 '[12]: list_classes gives them')
	out = []
	for v in values:
		c = _code(v)
		if c not in out:
			out.append(c)
	known = set(codes(entry))
	unknown = [c for c in out if c not in known]
	if unknown:
		raise ValueError(f"{entry['index']} ({entry['sensor']}) has no classes {', '.join(map(str, unknown))}: "
		                 'list_classes gives the codes of its classes')
	return out


def _plain(text):
	"""TEXT in lower case without accents, to search the names."""
	return ''.join(c for c in unicodedata.normalize('NFD', str(text).lower()) if unicodedata.category(c) != 'Mn')


def find(entry, text=None, limit=None, lang='en'):
	"""The classes of ENTRY (see classes) with every word of TEXT at the start of a word of their code, name (in English
	or Spanish) or group (its code and name), in any case, with or without accents ('iberian' finds the Iberian
	ecoregions, not the Siberian ones), at most LIMIT. Without Earth Engine."""
	rows = classes(entry, lang)
	if text not in (None, ''):
		words = _plain(text).split()
		group = group_entry(entry)

		def has(c):
			names = [str(c['code']), c['name'], name(entry, c['code'], 'en'), name(entry, c['code'], 'es')]
			if group is not None:
				names += [c.get('group_name') or '', name(group, c.get('group'), 'en'), str(c.get('group'))]
			text_ = _plain(' '.join(names))
			return all(re.search(r'(?<![a-z0-9])' + re.escape(w), text_) for w in words)

		rows = [c for c in rows if has(c)]
	return rows[:int(limit)] if limit else rows


def legend(entry, values=None, lang='en'):
	"""The legend of the classes VALUES of ENTRY (default: all of them), from the lowest code, as that of the burn
	severity (monitoreo.fire.legend), which every tool draws: [{'value', 'label', 'color' ('#rrggbb')}]."""
	values = codes(entry) if values is None else sorted({int(v) for v in values})
	return [{'value': v, 'label': label(entry, v, lang), 'color': '#' + colour(entry, v)} for v in values]


def vis(entry, values=None):
	"""The visualization of the classes VALUES of ENTRY (default: all of them) in Earth Engine: {'min' (the lowest
	code), 'max' (the highest), 'palette' (the colour of each code from min to max; GAP for the codes without a
	class)}, so that each code gets the colour of its class."""
	values = sorted({int(v) for v in (codes(entry) if not values else values)})
	lo, hi = values[0], values[-1]
	palette = [colour(entry, c) for c in range(lo, hi + 1)]
	if hi == lo:  # Earth Engine needs max > min: a second colour, the same
		return {'min': lo, 'max': lo + 1, 'palette': palette * 2}
	return {'min': lo, 'max': hi, 'palette': palette}


def _ecoregions(entry):
	"""The image of the ECO_ID of each pixel of the dataset of ENTRY (the first polygon of the pixel), integer, masked
	where there is none (ECO_ID 0, Rock and Ice, is a class)."""
	import ee
	base = table('ecoregions')
	return ee.FeatureCollection(entry['col']).reduceToImage([base['property']], ee.Reducer.first()).toInt()


def image(entry, res=None, aggregate='auto'):
	"""The image of the classes of the categorical ENTRY (band 'value', integer: the codes), for output pixels of RES
	metres: the polygons rasterized at the output pixel (see the module) and, on pixels more than twice as big as m (with
	AGGREGATE 'auto' or 'mode'), the majority class (mode) of its pixels of m; with 'none', as Earth Engine computes
	it at that pixel."""
	import ee
	img = _ecoregions(entry)
	if entry['classes'] != 'ecoregions':  # the groups of the ecoregions (the biomes), from the ECO_ID of each pixel
		if table('ecoregions').get('group') != entry['classes']:
			raise ValueError(f"the classes of {entry['index']} are not those of the ecoregions nor their groups")
		rows = _rows('ecoregions')
		ids = sorted(rows)
		img = img.remap(ids, [rows[i]['group'] for i in ids])
	m = float(entry['m'])
	if res and float(res) > 2 * m and str(aggregate or 'auto').lower() in ('auto', 'mode'):
		img = img.setDefaultProjection(ee.Projection('EPSG:4326').atScale(m)).reduceResolution(ee.Reducer.mode(), False,
		                                                                                     65535)
	return img.toInt().rename('value')


def present(entry, geometry):
	"""The codes of the classes of ENTRY in GEOMETRY (an ee.Geometry), from the lowest: those of the polygons that touch
	it (a query of the polygons, without rasterizing them), for the legends of the maps; for the groups (the biomes),
	those of the ecoregions there."""
	import ee
	base = table('ecoregions')
	ids = ee.FeatureCollection(entry['col']).filterBounds(geometry).aggregate_array(base['property']).distinct()
	got = {int(round(float(i))) for i in ids.getInfo() or []}
	if entry['classes'] == 'ecoregions':
		return sorted(got)
	rows = _rows('ecoregions')
	return sorted({rows[i]['group'] for i in got if i in rows})


def condition(c, entry=None):
	"""(entry, codes, keep) of the condition C of where on a categorical layer: {'variable', 'sensor', 'classes'} (keep
	True: only the pixels of those classes) or {..., 'exclude'} (keep False: without those classes); ValueError, without
	Earth Engine, if it is wrong: classes or exclude on a continuous variable, min or max on a categorical one, both
	classes and exclude, neither, or codes that are not of its classes."""
	e = entry or catalog.find(c['variable'], c.get('sensor'), c.get('collection'), c.get('ref'))
	given = [k for k in ('classes', 'exclude') if c.get(k) is not None]
	if not is_categorical(e):
		raise ValueError(f"classes and exclude are for a categorical layer (ECOREGION, BIOME): {e['index']} "
		                 f"({e['sensor']}) takes min and max")
	if c.get('min') is not None or c.get('max') is not None:
		raise ValueError(f"{e['index']} ({e['sensor']}) is a categorical layer, whose values are class codes: a "
		                 'condition on it takes classes (the classes to keep) or exclude (those to leave out), not min '
		                 'or max')
	if len(given) == 2:
		raise ValueError(f"the condition on {e['index']} of where takes classes or exclude, not both")
	if not given:
		raise ValueError(f"the condition on {e['index']} of where needs classes (the classes to keep) or exclude (those "
		                 f'to leave out), e.g. {EXAMPLE}')
	return e, check(e, c[given[0]], given[0]), given[0] == 'classes'


def keep(entry, values, kept=True, res=None):
	"""The image (1) of the pixels of RES metres kept by a condition on the categorical ENTRY: with KEPT, where the
	classes VALUES cover SHARE of the pixel or more; else, where they cover less; masked where the layer has no data.
	On pixels more than twice as big as m, the share of its pixels of m; otherwise, the class at the pixel."""
	import ee
	inside = image(entry).remap(list(values), [1] * len(values), 0)  # 1: a class of VALUES; masked: no data
	m = float(entry['m'])
	if res and float(res) > 2 * m:
		inside = inside.setDefaultProjection(ee.Projection('EPSG:4326').atScale(m)).reduceResolution(ee.Reducer.mean(),
		                                                                                        True, 65535)
	return ee.Image(1).updateMask(inside.mask()).And(inside.gte(SHARE) if kept else inside.lt(SHARE))


def text(c, lang='en'):
	"""The condition C of where on a categorical layer in words, e.g. «BIOME (RESOLVE) is 12 Mediterranean Forests,
	Woodlands & Scrub» or «ECOREGION (RESOLVE) is not 793 Iberian sclerophyllous and semi-deciduous forests»."""
	try:
		e, values, kept = condition(c)
	except (ValueError, KeyError):
		return str(c)
	names = [label(e, v, lang) for v in values]
	if lang == 'es':
		which = ' o '.join([', '.join(names[:-1]), names[-1]] if len(names) > 1 else names)
		return f"{e['index']} ({e['sensor']}) {'es' if kept else 'no es'} {which}"
	which = ' or '.join([', '.join(names[:-1]), names[-1]] if len(names) > 1 else names)
	return f"{e['index']} ({e['sensor']}) is {'' if kept else 'not '}{which}"


def check_stats(entry, stats):
	"""ValueError, without Earth Engine, for a statistic over a region of the categorical ENTRY that is not one of
	STATS (the mean of class codes means nothing)."""
	for s in stats:
		if str(s).strip().lower() not in STATS:
			raise ValueError(f"{entry['index']} ({entry['sensor']}) is a categorical layer: its statistic over a region "
			                 f'is the majority class (mode), not {s}; for the area of each class, area_by_class')


def check_options(entry, resample=None, aggregate=None):
	"""ValueError, without Earth Engine, for a way of resampling or aggregating the pixels of the categorical ENTRY
	that would mix its classes (bilinear, bicubic, the mean)."""
	r = str(resample or 'auto').strip().lower()
	if r not in ('auto', 'nearest'):
		raise ValueError(f"{entry['index']} ({entry['sensor']}) is a categorical layer, whose values are class codes: "
		                 f'resample takes auto or nearest, not {resample} (a value between two classes is no class)')
	a = str(aggregate or 'auto').strip().lower()
	if a not in ('auto', 'mode', 'none'):
		raise ValueError(f"{entry['index']} ({entry['sensor']}) is a categorical layer, whose values are class codes: "
		                 f'aggregate takes auto, mode or none, not {aggregate} (the mean of class codes is no class)')


def describe(entry, lang='en'):
	"""What describe_variable says of the classes of the categorical ENTRY: {'categorical': True, 'n_classes',
	'classes_table' (its name and notes), 'classes' (when there are at most DESCRIBE_MAX: [{code, name, colour}]) or
	'classes_note' (else, how to list them)}."""
	t = of(entry)
	out = {'categorical': True, 'n_classes': len(t['classes']),
	       'classes_table': {'name': t['name'], 'property': t['property'], 'notes': t.get('notes', '')}}
	if len(t['classes']) <= DESCRIBE_MAX:
		out['classes'] = classes(entry, lang)
	else:
		out['classes_note'] = (f"{len(t['classes'])} classes: list_classes gives them (their code, name, colour and "
		                       'group), and finds them by name')
	return out
