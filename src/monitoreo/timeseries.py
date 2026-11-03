"""Time series of a variable over one or several regions, as the charts of MonitorEO: one value per step and region.

Each step (a day with images, 16 days, a month or a year of the period, within the season if there is one) is
reduced in time with METRIC (e.g. the mean of the NDVI of the images of each month), and then over each region with
STAT (e.g. its spatial mean). Every row also gives the number of images of the step and of valid pixels of the
region, so that steps with few clear observations can be told apart.
"""

import csv
import datetime as dt
import math
import time

import ee

from . import areas, composite, variable

STEPS = ('daily', '16-day', 'monthly', 'annual')
COLUMNS = ['region', 'date', 'value', 'n_pixels', 'n_images']
MAX_ROWS = 4000      # rows per request to Earth Engine (getInfo returns at most 5000 elements)
MAX_STEPS = 120      # steps per request: reduced together, as the bands of one image
TARGET_PIXELS = 1e6  # pixels per region and step for the automatic scale
SPLIT_ERRORS = ('too many concurrent', 'memory limit', 'timed out', 'computation timed out')
RETRY_ERRORS = ('429', 'quota', 'unavailable', '503', '500', 'deadline', 'internal error')


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
	pixels of SCALE metres in CRS (default: the UTM zone of the regions). The steps are reduced over the regions in a
	single pass, as the bands of one image: with a reduction per step, Earth Engine went over the regions again for
	each one (96 months over the Sierra Nevada National Park took 5 minutes)."""
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
	bands = [f's{i}' for i in range(len(steps))]
	img = ee.Image.cat([composite._reduce(col.filterDate(a, b), red).rename(band) for band, (a, b) in zip(bands, steps)])
	n_images = ee.List([col.filterDate(a, b).size() for a, b in steps])
	stats = img.reduceRegions(collection=regions, reducer=sred, scale=scale, crs=crs, tileScale=tile_scale)
	prefix = [f'{band}_' if len(bands) > 1 else '' for band in bands]  # a single band keeps the names of the outputs

	def rows(f):
		f = ee.Feature(f)
		return ee.FeatureCollection([ee.Feature(None, {
			'region': f.get('name'), 'date': a, 'value': f.get(p + out), 'n_pixels': f.get(p + 'count'),
			'n_images': n_images.get(i)}) for i, (p, (a, _)) in enumerate(zip(prefix, steps))])

	return stats.map(rows).flatten()


def series(spec, regions, step='monthly', metric='mean', stat='mean', scale=None, progress=None, steps=None):
	"""Rows [{region, date, value, n_pixels, n_images}] of the time series, sorted by region and date, and the scale
	used. STEPS: [(first day, day after the last)] instead of the steps of STEP. The steps are requested in blocks of
	at most MAX_ROWS rows; PROGRESS(done, total) is called after each."""
	geom = regions.geometry()
	scale = scale or auto_scale(spec, regions)
	crs = region_crs(regions)
	steps = steps if steps is not None else bins(spec, step, geom)
	n_regions = max(regions.size().getInfo(), 1)
	block = max(1, min(MAX_ROWS // n_regions, MAX_STEPS))
	rows = []
	for i in range(0, len(steps), block):
		rows += _fetch(spec, regions, step, metric, stat, scale, steps[i:i + block], crs)
		if progress:
			progress(min(i + block, len(steps)), len(steps))
	for r in rows:
		r['region'] = str(r.get('region'))
	rows.sort(key=lambda r: (r['region'], r['date']))
	return rows, scale


def _fetch(spec, regions, step, metric, stat, scale, steps, crs, retries=4):
	"""Rows of the STEPS: the request is split in two when Earth Engine has too many aggregations at the same time
	or runs out of memory or time, and repeated (after 5, 10, 20 s) when it is busy."""
	for attempt in range(retries):
		try:
			fc = table(spec, regions, step, metric, stat, scale, steps, crs)
			# Earth Engine leaves out the null properties: a step without images (e.g. Landsat in 2012) has no value
			return [{'value': None, 'n_pixels': 0, **f['properties']} for f in fc.getInfo()['features']]
		except ee.EEException as e:
			msg = str(e).lower()
			if any(s in msg for s in SPLIT_ERRORS) and len(steps) > 1:
				half = len(steps) // 2
				return (_fetch(spec, regions, step, metric, stat, scale, steps[:half], crs, retries)
				        + _fetch(spec, regions, step, metric, stat, scale, steps[half:], crs, retries))
			if attempt == retries - 1 or not any(s in msg for s in SPLIT_ERRORS + RETRY_ERRORS):
				raise
		time.sleep(2 ** attempt * 5)


def write_csv(rows, path, meta=None, columns=COLUMNS):
	"""Write the COLUMNS of the rows to a CSV file, with the columns of META (e.g. variable, sensor, unit) repeated on
	every row."""
	meta = meta or {}
	with open(path, 'w', newline='', encoding='utf-8') as f:
		w = csv.writer(f)
		w.writerow(list(columns) + list(meta))
		for r in rows:
			w.writerow([r.get(c) if r.get(c) is not None else '' for c in columns] + list(meta.values()))
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
