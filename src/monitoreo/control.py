"""The control area of a disturbance: a ring around the affected area, as the EVEREST case studies built it
(herramientas/zonas.py): the land from GAP to GAP + WIDTH metres from the affected area (150 and 1500 m by default),
without the land near the areas of EXCLUDE (other fires or disturbances, within GAP of them) and, with WITHIN, only
inside that region (e.g. the protected area). Its pixels are then matched with those of the affected area by the
variables of MATCH (by default the elevation of the Copernicus DEM): a condition of where with their percentiles 5 and
95 in the affected area, for both areas. Used by services.control_ring, and by time_series and recovery_metrics with
ring: the series of the affected area, of the control and of their difference (a BACI design), which separates the
effect of the disturbance from the variability of the climate of the region.

The ring is a buffer in metres of the affected area (Earth Engine, with an error of MAX_ERROR m): its pixels of the
same ecosystem are not guaranteed, only those of the same elevation; check the map of the ring, add conditions of where
(e.g. a land cover) or give another control area (a feature of the region) when they differ.
"""

import ee

DEFAULTS = {'gap': 150.0, 'width': 1500.0, 'exclude': None, 'within': None, 'match': ['ELEVATION']}
MATCH = {'ELEVATION': 'Copernicus', 'SLOPE': 'Copernicus'}  # the fixed layers that can match the pixels
PERCENTILES = (5, 95)
MAX_ERROR = 10  # metres, of the buffers of the ring
NAMES = ('affected', 'control')


def check(ring):
	"""The options of RING (True, or a dictionary of DEFAULTS' keys) with their defaults, checked before Earth Engine:
	ValueError for an unknown key, a gap below 0, a width of 0 or less, or a variable of match that cannot match."""
	if ring is True or ring == {}:
		return dict(DEFAULTS)
	if not isinstance(ring, dict):
		raise ValueError(f'ring: true, or the options of the control ring {sorted(DEFAULTS)}, not {ring!r}')
	unknown = sorted(set(ring) - set(DEFAULTS))
	if unknown:
		raise ValueError(f"ring: unknown options {', '.join(unknown)}; the options are {', '.join(sorted(DEFAULTS))}")
	out = dict(DEFAULTS, **{k: v for k, v in ring.items() if v is not None})
	try:
		out['gap'], out['width'] = float(out['gap']), float(out['width'])
	except (TypeError, ValueError):
		raise ValueError('ring: gap and width are distances in metres (e.g. 150 and 1500)') from None
	if out['gap'] < 0 or out['width'] <= 0:
		raise ValueError('ring: gap (the distance from the affected area) is 0 or more metres, and width (that of the '
		                 'ring) more than 0')
	match = out['match']
	match = [match] if isinstance(match, str) else list(match or [])
	wrong = [m for m in match if str(m).upper() not in MATCH]
	if wrong:
		raise ValueError(f"ring: match takes {', '.join(MATCH)} (fixed layers of the Copernicus DEM), not "
		                 f"{', '.join(map(str, wrong))}; give other conditions in where")
	out['match'] = [str(m).upper() for m in match]
	return out


def zones(regions, opts, exclude=None, within=None):
	"""ee.FeatureCollection of two features, the affected area (the union of the features of REGIONS) and its control
	ring (see the module) with the options OPTS (check), named 'affected' and 'control'; EXCLUDE and WITHIN are the
	ee.FeatureCollection of those options, or None."""
	affected = regions.geometry().dissolve(MAX_ERROR)
	gap, width = opts['gap'], opts['width']
	outer = affected.buffer(gap + width, MAX_ERROR)
	inner = affected.buffer(gap, MAX_ERROR) if gap > 0 else affected
	ring = outer.difference(inner, MAX_ERROR)
	if exclude is not None:
		ring = ring.difference(exclude.geometry().buffer(gap, MAX_ERROR) if gap > 0 else exclude.geometry(), MAX_ERROR)
	if within is not None:
		ring = ring.intersection(within.geometry(), MAX_ERROR)
	return ee.FeatureCollection([ee.Feature(affected, {'name': NAMES[0]}), ee.Feature(ring, {'name': NAMES[1]})])


def difference_rows(rows):
	"""The rows of the difference affected - control of the series ROWS (those of both, by region and date): a row
	per date with both values, region 'affected - control' and the value of their difference."""
	by = {}
	for r in rows:
		by.setdefault(r['date'], {})[r['region']] = r
	out = []
	for date in sorted(by):
		a, c = by[date].get(NAMES[0]), by[date].get(NAMES[1])
		if a and c and a.get('value') is not None and c.get('value') is not None:
			out.append({'region': f'{NAMES[0]} - {NAMES[1]}', 'date': date, 'value': a['value'] - c['value'],
			            'n_pixels': None, 'n_images': a.get('n_images')})
	return out
