"""Time series of a variable over one or several regions, as the charts of MonitorEO: one value per step and region.

Each step (a day with images, 16 days, a month or a year of the period, within the season if there is one) is
reduced in time with METRIC (e.g. the mean of the NDVI of the images of each month), and then over each region with
STAT (e.g. its spatial mean). Every row also gives the number of images of the step and of valid pixels of the
region, so that steps with few clear observations can be told apart.
"""

import csv
import datetime as dt
import math

import ee

from . import areas, composite, variable

STEPS = ('daily', '16-day', 'monthly', 'annual')
COLUMNS = ['region', 'date', 'value', 'n_pixels', 'n_images']
MAX_ROWS = 4000      # rows per request to Earth Engine (getInfo returns at most 5000 elements)
TARGET_PIXELS = 1e6  # pixels per region and step for the automatic scale


def bins(spec, step, region_geom=None):
	"""[(first day, day after the last)] ('YYYY-MM-DD') of the steps of the period (and season) of SPEC. The days
	('daily') are those with images over REGION_GEOM."""
	if step not in STEPS:
		raise ValueError(f"unknown step {step}: use {', '.join(STEPS)}")
	wins = composite.windows(spec['period'], spec['season'])
	if step == 'annual':
		out = [(ws, we) for _, ws, we in wins]
	elif step in ('monthly', '16-day'):
		out = [(bs, be) for w in wins for _, bs, be in composite.bins(w, step)]
	else:
		col = variable.collection(dict(spec, resample='nearest'), region_geom, 1e9).filter(composite.date_filter(wins))
		days = col.aggregate_array('system:time_start').map(lambda t: ee.Date(t).format('YYYY-MM-dd')).distinct().sort()
		out = []
		for d in days.getInfo():
			day = dt.date.fromisoformat(d)
			out.append((day, day + dt.timedelta(days=1)))
	return [(a.isoformat(), b.isoformat()) for a, b in out]


def auto_scale(spec, regions):
	"""Pixel size (m) for the statistics: that of the data, or bigger so that the biggest region has about
	TARGET_PIXELS pixels (rounded to 10, 20, 50, 100, 200, ... m)."""
	native = variable.native_scale(spec)
	area = regions.map(lambda f: ee.Feature(None, {'a': f.geometry().area(1)})).aggregate_max('a').getInfo() or 0
	need = math.sqrt(area / TARGET_PIXELS) if area else native
	if need <= native:
		return native
	nice = [m * 10 ** e for e in range(1, 6) for m in (1, 2, 5)]
	return float(next((n for n in nice if n >= need), nice[-1]))


def region_crs(regions):
	"""WGS 84 / UTM zone of the centre of REGIONS, for statistics on square pixels."""
	lon, lat = regions.geometry().centroid(1000).coordinates().getInfo()
	return areas.utm_of(lon, lat)


def _stat_name(stat):
	"""Name of the output of the spatial reducer STAT for a single band image (mean, median, p95, stdDev, ...)."""
	return composite.reducer(stat).getOutputs().getInfo()[0]


def table(spec, regions, step='monthly', metric='mean', stat='mean', scale=None, steps=None, crs=None, tile_scale=4):
	"""ee.FeatureCollection with a row (region, date, value, n_pixels, n_images) per step of STEPS (default: all
	the steps of the period) and region of REGIONS (an ee.FeatureCollection with a 'name' property), computed on
	pixels of SCALE metres in CRS (default: the UTM zone of the regions)."""
	if variable.kind(spec) == 'image':
		raise ValueError('a fixed image has no time series')
	geom = regions.geometry()
	scale = scale or auto_scale(spec, regions)
	crs = crs or region_crs(regions)
	col = variable.collection(spec, geom, scale)
	red = composite.reducer(metric)
	sred = composite.reducer(stat).combine(ee.Reducer.count(), '', True)
	out = _stat_name(stat)
	steps = steps if steps is not None else bins(spec, step, geom)

	def step_rows(b):
		b = ee.List(b)
		start, end = ee.String(b.get(0)), ee.String(b.get(1))
		sub = col.filterDate(start, end)
		img = composite._reduce(sub, red)
		n = sub.size()
		stats = img.reduceRegions(collection=regions, reducer=sred, scale=scale, crs=crs, tileScale=tile_scale)
		return stats.map(lambda f: ee.Feature(None, {
			'region': f.get('name'), 'date': start, 'value': f.get(out), 'n_pixels': f.get('count'), 'n_images': n}))

	return ee.FeatureCollection(ee.List([list(s) for s in steps]).map(step_rows)).flatten()


def series(spec, regions, step='monthly', metric='mean', stat='mean', scale=None, progress=None):
	"""Rows [{region, date, value, n_pixels, n_images}] of the time series, sorted by region and date, and the scale
	used. The steps are requested in blocks of at most MAX_ROWS rows; PROGRESS(done, total) is called after each."""
	geom = regions.geometry()
	scale = scale or auto_scale(spec, regions)
	crs = region_crs(regions)
	steps = bins(spec, step, geom)
	n_regions = max(regions.size().getInfo(), 1)
	block = max(1, MAX_ROWS // n_regions)
	rows = []
	for i in range(0, len(steps), block):
		fc = table(spec, regions, step, metric, stat, scale, steps[i:i + block], crs)
		rows += [f['properties'] for f in fc.getInfo()['features']]
		if progress:
			progress(min(i + block, len(steps)), len(steps))
	for r in rows:
		r['region'] = str(r.get('region'))
	rows.sort(key=lambda r: (r['region'], r['date']))
	return rows, scale


def write_csv(rows, path, meta=None):
	"""Write the rows to a CSV file, with the columns of META (e.g. variable, sensor, unit) repeated on every row."""
	meta = meta or {}
	with open(path, 'w', newline='', encoding='utf-8') as f:
		w = csv.writer(f)
		w.writerow(COLUMNS + list(meta))
		for r in rows:
			w.writerow([r.get(c) if r.get(c) is not None else '' for c in COLUMNS] + list(meta.values()))
	return path


def climatology(rows):
	"""Mean of each calendar month over the years, per region: [{region, month, value, n_years}]."""
	acc = {}
	for r in rows:
		if r.get('value') is None:
			continue
		key = (r['region'], int(r['date'][5:7]))
		acc.setdefault(key, []).append(r['value'])
	return [{'region': k[0], 'month': k[1], 'value': sum(v) / len(v), 'n_years': len(v)} for k, v in sorted(acc.items())]
