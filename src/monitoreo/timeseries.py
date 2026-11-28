"""Time series of a variable over one or several regions, as the charts of MonitorEO: one value per step and region.

Each step (a day with images, 16 days, a month or a year of the period, within the season if there is one) is
reduced in time with METRIC (e.g. the mean of the NDVI of the images of each month), and then over each region with
STAT (e.g. its spatial mean, or its coefficient of variation, 'cv', in %: see composite). Every row also gives the number of images of the step and of valid pixels of the
region, so that steps with few clear observations can be told apart. With MIN_COVERAGE (a fraction, 0 to 1), the rows
also give the fraction of the pixels of the region with a valid value in the step (coverage: n_pixels over the pixels of
the region kept by where and exclude_landcover), and the steps below it have no value: a month with clouds, shadow or
snow over most of the region gives the value of the few pixels left, which can be far from that of the region.

By day of the year (time_series with doy): the rows get the year and the day of the year of each step (with_doy), to
draw a line per year; or the seasonal profile (doy_profile), a metric between the years (over_years: e.g. the median)
of the values of each step of the year (each month, 16-day period or calendar day), a line per variable.
"""

import calendar
import csv
import datetime as dt
import math
import re
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
		col = variable.collection(dict(spec, resample='nearest', where=None, exclude_landcover=None), region_geom,
		                          1e9).filter(composite.date_filter(wins))  # the days with images: no mask
		days = col.aggregate_array('system:time_start').map(lambda t: ee.Date(t).format('YYYY-MM-dd')).distinct().sort()
		out = []
		for d in days.getInfo():
			day = dt.date.fromisoformat(d)
			out.append((day, day + dt.timedelta(days=1)))
	return [(a.isoformat(), b.isoformat()) for a, b in out]


def auto_scale(spec, regions):
	"""Pixel size (m) for the statistics: that of the data, or bigger so that the biggest region has about
	TARGET_PIXELS pixels (rounded to 10, 20, 50, 100, 200, ... m); in a large area (more than areas.LARGE_AREA_KM2: a
	country, a biome, most seas), 1 to 10 km, never finer than the data (areas.default_scale)."""
	return areas.default_scale(variable.native_scale(spec), areas.max_area(regions), TARGET_PIXELS)


# MODIS: its products are on the sinusoidal grid of NASA (SR-ORG:6974), of pixels of these sizes (their nominal 250,
# 500 and 1000 m) from the corner (-20015109.354, 10007554.677): at the resolution of the data, the statistics are
# computed on that grid (see native_grid), each pixel once, not on pixels of 1000 m of the UTM zone, each of them the
# MODIS pixel of its centre (2-3 per MODIS pixel, some from outside the region: the 1-km cells of a land cover mixed
# their neighbours)
MODIS_CRS = 'SR-ORG:6974'
MODIS_PIXEL = {250: 231.656358263958, 500: 463.312716527917, 1000: 926.625433055833}
MODIS_ORIGIN = (-20015109.354, 10007554.677)


def native_grid(spec, scale):
	"""(crs, crs_transform) of the grid of the MODIS product of SPEC (a variable of the catalog of Modis) when SCALE is
	its resolution (see MODIS_PIXEL), or None (other data, or a coarser scale: the UTM grid of region_crs)."""
	if variable.kind(spec) != 'catalog':
		return None
	e = variable.entry_of(spec)
	if e.get('sensor') != 'Modis' or not str(e.get('col', '')).startswith('MODIS/'):
		return None
	m = float(e['m'])  # the nominal size (250, 500, 1000) or the real one (463) of the catalog
	pixel = next((p for k, p in MODIS_PIXEL.items() if abs(m - k) < 1e-6 or abs(m - p) < 1), None)
	if pixel is None or scale is None or abs(float(scale) - m) > 1e-6:
		return None
	return MODIS_CRS, [pixel, 0, MODIS_ORIGIN[0], 0, -pixel, MODIS_ORIGIN[1]]


def region_crs(regions):
	"""The CRS of the statistics of REGIONS, on square pixels: WGS 84 / UTM zone of their centre or, for regions too
	wide for one (a whole biome), an equal-area CRS in metres (areas.auto_crs)."""
	return areas.auto_crs(regions.geometry())


def _stat_name(stat):
	"""Name of the output of the spatial reducer STAT for a single band image (mean, median, p95, stdDev, ...; for the
	coefficient of variation, that of its mean: see composite.ee_value_of)."""
	return composite.reducer(stat).getOutputs().getInfo()[0]


def check_min_coverage(min_coverage):
	"""MIN_COVERAGE as a number greater than 0 and at most 1, or None (not asked: 0, None, '' or false); ValueError if
	it is something else (e.g. 50: give 0.5)."""
	v = min_coverage
	if v is None or v is False or (isinstance(v, str) and v.strip().lower() in ('', 'none', 'null', 'false', 'off')):
		return None
	try:
		x = float(v)
	except (TypeError, ValueError):
		raise ValueError(f'min_coverage: give the smallest fraction of valid pixels of a step, e.g. 0.5, not {v!r}') from None
	if isinstance(v, bool) or not 0 <= x <= 1:
		raise ValueError(f'min_coverage: a fraction of the pixels of the region, from 0 to 1 (e.g. 0.5 for half), not {v!r}')
	return x or None


def table(spec, regions, step='monthly', metric='mean', stat='mean', scale=None, steps=None, crs=None, tile_scale=4,
          min_coverage=None, coverage=False):
	"""ee.FeatureCollection with a row (region, date, value, n_pixels, n_images) per step of STEPS (default: all
	the steps of the period) and region of REGIONS (an ee.FeatureCollection with a 'name' property), computed on
	pixels of SCALE metres in CRS (default: that of region_crs, the UTM zone of the regions). The steps are reduced
	over the regions in a single pass, as the bands of one image: with a reduction per step, Earth Engine went over the
	regions again for each one (96 months over the Sierra Nevada National Park took 5 minutes). With MIN_COVERAGE, the
	rows also have coverage, and those of the steps below it no value (see the module); with COVERAGE, the rows have
	it without a minimum (image_count)."""
	min_coverage = check_min_coverage(min_coverage)
	coverage = bool(coverage) or min_coverage is not None
	if variable.kind(spec) == 'image':
		raise ValueError('a fixed image has no time series')
	geom = regions.geometry()
	scale = scale or auto_scale(spec, regions)
	crs = crs or region_crs(regions)
	native = native_grid(spec, scale)  # MODIS at its resolution: on its own grid
	grid = {'crs': native[0], 'crsTransform': native[1]} if native else {'scale': scale, 'crs': crs}
	col = variable.collection(spec, geom, scale)
	composite.check_metric(metric)
	composite.check_step(metric, step)  # the snow melt-out day: one per year
	# the statistic count is the number of pixels: once (Earth Engine refuses two outputs count)
	only_count = str(stat).strip().lower() == 'count'
	sred = ee.Reducer.count() if only_count else composite.reducer(stat).combine(ee.Reducer.count(), '', True)
	out = _stat_name(stat)
	steps = steps if steps is not None else bins(spec, step, geom)
	bands = [f's{i}' for i in range(len(steps))]
	img = ee.Image.cat([composite.reduce_span(col, metric, a, b).rename(band)
	                    for band, (a, b) in zip(bands, steps)])
	n_images = ee.List([col.filterDate(a, b).size() for a, b in steps])
	if coverage:  # the pixels of each region (those that where and exclude_landcover keep), apart:
		# a band more would change the names of the outputs of the steps (those of count are the names of the bands)
		kept = variable.mask(spec, geom, scale) if variable.kind(spec) == 'catalog' or spec.get('where') or \
			spec.get('exclude_landcover') else None
		total = (kept if kept is not None else ee.Image(1)).rename('total')

		def with_total(f):
			f = ee.Feature(f)
			# with the reducer of the steps, which counts the pixels as they do (with mean or median, also those that
			# the region only touches): with count alone, the region would have fewer pixels than its steps
			n = total.reduceRegion(sred, f.geometry(), **grid, maxPixels=1e13,
			                       tileScale=tile_scale).get('total' if only_count else 'total_count')
			return f.set('total_count', ee.Algorithms.If(n, n, 0))

		regions = regions.map(with_total)
	stats = img.reduceRegions(collection=regions, reducer=sred, **grid, tileScale=tile_scale)
	prefix = [f'{band}_' if len(bands) > 1 else '' for band in bands]  # a single band keeps the names of the outputs
	# the output count of each step: with the reducer count alone over several bands, the name of its band (s0, s1...)
	counted = [band if only_count and len(bands) > 1 else p + 'count' for band, p in zip(bands, prefix)]

	def row(f, i, p, a):
		value = f.get(counted[i]) if only_count else composite.ee_value_of(f, stat, out, p)
		props = {'region': f.get('name'), 'date': a, 'value': value, 'n_pixels': f.get(counted[i]),
		         'n_images': n_images.get(i)}
		if coverage:  # the fraction of the pixels of the region with a value (none without its count)
			total, valid = ee.Number(f.get('total_count')), f.get(counted[i])
			cover = ee.Algorithms.If(valid, ee.Algorithms.If(total.gt(0), ee.Number(valid).divide(total), 0), None)
			props['coverage'] = cover
			if min_coverage is not None:
				props['value'] = ee.Algorithms.If(ee.Algorithms.IsEqual(cover, None), props['value'], ee.Algorithms.If(
					ee.Number(cover).gte(min_coverage), props['value'], None))
		return ee.Feature(None, props)

	def rows(f):
		f = ee.Feature(f)
		return ee.FeatureCollection([row(f, i, p, a) for i, (p, (a, _)) in enumerate(zip(prefix, steps))])

	return stats.map(rows).flatten()


def series(spec, regions, step='monthly', metric='mean', stat='mean', scale=None, progress=None, steps=None,
           min_coverage=None, coverage=False):
	"""Rows [{region, date, value, n_pixels, n_images}] of the time series, sorted by region and date, and the scale
	used. STEPS: [(first day, day after the last)] instead of the steps of STEP. The steps are requested in blocks of
	at most MAX_ROWS rows; PROGRESS(done, total) is called after each. With MIN_COVERAGE, also coverage in each row, and
	no value in the steps below it (see table); with COVERAGE, coverage without a minimum."""
	min_coverage = check_min_coverage(min_coverage)
	geom = regions.geometry()
	scale = scale or auto_scale(spec, regions)
	crs = region_crs(regions)
	steps = steps if steps is not None else bins(spec, step, geom)
	n_regions = max(regions.size().getInfo(), 1)
	block = max(1, min(MAX_ROWS // n_regions, MAX_STEPS))
	rows = []
	for i in range(0, len(steps), block):
		rows += _fetch(spec, regions, step, metric, stat, scale, steps[i:i + block], crs, min_coverage=min_coverage,
		               coverage=coverage)
		if progress:
			progress(min(i + block, len(steps)), len(steps))
	for r in rows:
		r['region'] = str(r.get('region'))
	rows.sort(key=lambda r: (r['region'], r['date']))
	return rows, scale


def _fetch(spec, regions, step, metric, stat, scale, steps, crs, retries=4, min_coverage=None, coverage=False):
	"""Rows of the STEPS: the request is split in two when Earth Engine has too many aggregations at the same time
	or runs out of memory or time, and repeated (after 5, 10, 20 s) when it is busy."""
	for attempt in range(retries):
		try:
			covered = coverage or min_coverage is not None
			fc = table(spec, regions, step, metric, stat, scale, steps, crs,
			           **({'min_coverage': min_coverage} if min_coverage is not None else {}),
			           **({'coverage': True} if coverage else {}))
			# Earth Engine leaves out the null properties: a step without images (e.g. Landsat in 2012) has no value
			blank = {'value': None, 'n_pixels': 0, **({'coverage': 0} if covered else {})}
			return [{**blank, **f['properties']} for f in fc.getInfo()['features']]
		except ee.EEException as e:
			msg = str(e).lower()
			if any(s in msg for s in SPLIT_ERRORS) and len(steps) > 1:
				half = len(steps) // 2
				return (_fetch(spec, regions, step, metric, stat, scale, steps[:half], crs, retries, min_coverage, coverage)
				        + _fetch(spec, regions, step, metric, stat, scale, steps[half:], crs, retries, min_coverage,
				                 coverage))
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


def with_doy(rows):
	"""ROWS with the year and the day of the year (1-366) of the first day of each step: 'year' and 'doy', to draw a
	line per year over the days of the year (as the day-of-year charts of geemap)."""
	for r in rows:
		d = dt.date.fromisoformat(str(r['date'])[:10])
		r['year'], r['doy'] = d.year, d.timetuple().tm_yday
	return rows


# The seasonal profile of a series by day of the year (time_series with doy and interannual or other_variable): for each
# step of the year (a month, a 16-day period, a calendar day) of each region and variable, a metric between the years
# (INTERANNUAL, or a percentile pN) of the values of that step in the years of the period
INTERANNUAL = ('mean', 'median', 'min', 'max', 'std', 'cv')
INTERANNUAL_TEXT = 'mean, median, min, max, std (sample standard deviation), cv (coefficient of variation, %) or pN ' \
                   '(percentile N, e.g. p25)'
PROFILE_COLUMNS = ['region', 'variable', 'part', 'doy', 'label', 'value', 'n_years']
# the columns of the CSV of a profile after PROFILE_COLUMNS: what each row was made with (the sensor, unit in UDUNITS
# and pixel size of the computation of its variable, the same step, metrics and statistic for both variables)
PROFILE_META = ['sensor', 'step', 'metric', 'stat', 'interannual', 'unit', 'scale_m']
MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
COMMON_YEAR = 2023  # a year of 365 days, for the names of the days of the year
LEAP_YEAR = 2024  # a year of 366 days, for the days of the year of the calendar days (29 February apart from 1 March)


def check_interannual(metric):
	"""METRIC between the years of a profile in lower case (see INTERANNUAL), or ValueError (without Earth Engine)."""
	m = str(metric or '').strip().lower()
	p = re.fullmatch(r'p(\d+(?:\.\d+)?)', m)
	if m in INTERANNUAL or (p and 0 <= float(p.group(1)) <= 100):
		return m
	raise ValueError(f'unknown metric between the years (interannual) {metric}: use {INTERANNUAL_TEXT}')


def over_years(values, metric):
	"""METRIC (see check_interannual) of VALUES (numbers, one per year; the None left out), or None without values: the
	mean; the median (the mean of the two middle values when they are even); the minimum; the maximum; std, the sample
	standard deviation (n - 1; None with fewer than 2 values); cv, 100 × std / |mean| (None with fewer than 2 values or a
	mean of 0); pN, the percentile N with linear interpolation between the closest ranks (as numpy.percentile). The sums
	add the values in their order, one by one, as gee/core.js (mo.overYears) does."""
	m = check_interannual(metric)
	xs = [float(v) for v in values if v is not None]
	n = len(xs)
	if not n:
		return None

	def mean():
		total = 0.0
		for x in xs:
			total += x
		return total / n

	def std():
		mu, total = mean(), 0.0
		for x in xs:
			d = x - mu
			total += d * d
		return math.sqrt(total / (n - 1))

	if m == 'mean':
		return mean()
	if m in ('min', 'max'):
		return min(xs) if m == 'min' else max(xs)
	if m in ('std', 'cv'):
		if n < 2:
			return None
		if m == 'std':
			return std()
		mu = mean()
		return None if mu == 0 else 100.0 * std() / abs(mu)
	s = sorted(xs)
	if m == 'median':
		return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
	rank = float(m[1:]) / 100 * (n - 1)
	lo = math.floor(rank)
	hi = min(lo + 1, n - 1)
	return s[lo] + (s[hi] - s[lo]) * (rank - lo)


def day_label(doy):
	"""Name in English of the day of the year DOY (1-366) in a common year: 'Jan 17' (366 is 'Dec 31')."""
	d = dt.date(COMMON_YEAR, 1, 1) + dt.timedelta(days=min(max(int(doy), 1), 365) - 1)
	return f'{MONTH_ABBR[d.month - 1]} {d.day}'


def _split_month(season):
	"""(month, first day) of the SEASON ('MM-DD', 'MM-DD') when it starts and ends in the same month and crosses the new
	year (e.g. a hydrological year from 15 October to 14 October), whose windows have two parts of that month (from its
	first day, and to its last day); else None."""
	if not season:
		return None
	(m0, d0), (m1, d1) = ((int(x) for x in str(md).split('-')) for md in season)
	return (m0, d0) if m0 == m1 and d0 > d1 else None


def _part_of(day, step, wins, season):
	"""The step of the year of the first day DAY of a step of STEP: the month (1-12), or 'MM-DD' for the part of a month
	from the first day of a SEASON that starts and ends in that month (see _split_month: '10-15', from 15 October; the
	rest of October is 10); the number of the 16-day period from the start of its window of WINS (see composite.windows:
	1 January, or the first day of the SEASON, even if the period starts later), 0, 1, 2, ..., the closest one to DAY
	(the steps of a window that starts later start on its first day: 1 January in a season from 1 November is in the
	period of 4 January, 1 November + 64 days), and none after the last one of the window; or the calendar day
	'MM-DD'."""
	if step == 'monthly':
		split = _split_month(season)
		if split and day.month == split[0] and day.day >= split[1]:
			return f'{split[0]:02d}-{split[1]:02d}'
		return day.month
	if step == 'daily':
		return day.strftime('%m-%d')
	year, end = next(((y, we) for y, ws, we in wins if ws <= day < we), (day.year, None))
	first = composite._md(year, season[0]) if season else dt.date(year, 1, 1)
	part = math.floor((day - first).days / 16 + 0.5)
	return min(part, ((end - first).days - 1) // 16) if end else part


def _part_doy(part, step, season, doys):
	"""The day of the year (1-366) where the step of the year PART (see _part_of) of STEP is drawn: monthly, the median
	(rounded, .5 up) of the days of the year DOYS of its rows; daily, that of the calendar day in a leap year (29 February
	is 60, 1 March 61, 31 December 366); 16-day, that of the first day of the period in a common year (the first day of
	the window, 1 January or the first day of the SEASON, + 16 × PART days), which goes on after 31 December (1 November
	+ 64 days is 4 January), as the median of the days of its rows would not."""
	if step == 'daily':
		return dt.date(LEAP_YEAR, int(part[:2]), int(part[3:])).timetuple().tm_yday
	if step == '16-day':
		first = composite._md(COMMON_YEAR, season[0]) if season else dt.date(COMMON_YEAR, 1, 1)
		return (first.timetuple().tm_yday - 1 + 16 * part) % 365 + 1
	doys = sorted(doys)
	k = len(doys)
	mid = doys[k // 2] if k % 2 else (doys[k // 2 - 1] + doys[k // 2]) / 2
	return int(math.floor(mid + 0.5))


def _part_label(part, step, season, doy):
	"""The name in English of the step of the year PART (see _part_of) of STEP drawn on the day of the year DOY: monthly
	the month, 'Jan' to 'Dec', or its two parts in a season that starts and ends in it ('Oct 15-31' and 'Oct 1-14');
	daily the calendar day ('Feb 29'); 16-day the day of DOY in a common year (see day_label)."""
	if step == 'monthly':
		split = _split_month(season)
		if isinstance(part, str):
			last = calendar.monthrange(COMMON_YEAR, split[0])[1]
			return f'{MONTH_ABBR[split[0] - 1]} {split[1]}-{last}'
		if split and part == split[0]:
			return f'{MONTH_ABBR[part - 1]} 1-{split[1] - 1}'
		return MONTH_ABBR[part - 1]
	if step == 'daily':
		return f'{MONTH_ABBR[int(part[:2]) - 1]} {int(part[3:])}'
	return day_label(doy)


def doy_profile(rows, spec, step, interannual, variable=''):
	"""The seasonal profile of the time series ROWS ([{region, date, value, ...}], with 'variable' when they are of
	two variables, else VARIABLE, its name) of a STEP shorter than a year: [{region, variable, part, doy, label, value,
	n_years}] (PROFILE_COLUMNS), a row per region, variable and step of the year (part: the month '1'-'12' monthly, see
	_part_of, the number of the 16-day period in the year or the season of SPEC '0', '1', ..., or the calendar day
	'MM-DD' daily), whose value is INTERANNUAL (see over_years) of the values of that step in the years of the period
	(n_years: how many are not None; a step without them has value None and n_years 0); doy is the day of the year
	where it is drawn (see _part_doy) and label its name (see _part_label). The features of the same name are numbered
	from the second one ('Sierra Nevada (2)'), as the viewer names them, so that the values of each one stay apart: the
	rows of each date come in the order of the features (see series). Sorted by region, variable (in the order of
	ROWS), doy and part."""
	if step not in STEPS or step == 'annual':
		raise ValueError(f'the profile by day of the year needs a step shorter than a year: daily, 16-day or monthly, '
		                 f'not {step}')
	interannual = check_interannual(interannual)
	season = (spec or {}).get('season') if step != 'daily' else None
	wins = composite.windows(spec['period'], season) if step == '16-day' else []
	groups, names, seen = {}, [], {}
	for r in rows:
		date = str(r['date'])[:10]
		day = dt.date.fromisoformat(date)
		name = r.get('variable') or variable
		if name not in names:
			names.append(name)
		region = str(r['region'])
		k = seen[(region, name, date)] = seen.get((region, name, date), 0) + 1
		region = region if k == 1 else f'{region} ({k})'
		doy = r.get('doy') or day.timetuple().tm_yday
		groups.setdefault((region, name, _part_of(day, step, wins, season)), []).append((date, doy, r.get('value')))
	out = []
	for (region, name, part), items in groups.items():
		items.sort(key=lambda t: t[0])  # by date: the values in the order of the years
		doy = _part_doy(part, step, season, [d for _, d, _ in items])
		values = [v for _, _, v in items if v is not None]
		out.append({'region': region, 'variable': name, 'part': str(part), 'doy': doy,
		            'label': _part_label(part, step, season, doy), 'value': over_years(values, interannual),
		            'n_years': len(values)})
	out.sort(key=lambda r: (r['region'], names.index(r['variable']), r['doy'], r['part']))
	return out


def climatology(rows):
	"""Mean of each calendar month over the years, per region: [{region, month, value, n_years}]."""
	acc = {}
	for r in rows:
		if r.get('value') is None:
			continue
		key = (r['region'], int(r['date'][5:7]))
		acc.setdefault(key, []).append(r['value'])
	return [{'region': k[0], 'month': k[1], 'value': sum(v) / len(v), 'n_years': len(v)} for k, v in sorted(acc.items())]
