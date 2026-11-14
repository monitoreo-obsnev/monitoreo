"""Temporal aggregation of a collection into one image.

temporal = 'period'   one metric over all the images of the period (and season): e.g. p95 of NDVI 2018-2021.
temporal = 'annual'   the metric of each year (or season of each year), then the interannual metric of those
                      images: e.g. the median of the annual maxima.
temporal = 'monthly'  the metric of each month, then the interannual metric of each calendar month (e.g. the mean
           '16-day'   of the twelve Julys), then the mean of the calendar months. '16-day' uses periods of 16 days
                      from the start of each year (or season) instead of months, grouped by the month in which
                      they start.

The true colour (RGB) of the images of a variable is aggregated with them (composite with bands): each band with the
metric (mean, median or pN), or, with max and min, the bands of the image where the variable is highest or lowest on
each pixel (Earth Engine qualityMosaic), so that the colours are those of one date and not a mix of the brightest
bands of several (clouds, snow). The metrics that do not give colours (sum, std, cv, count, mode) are refused
(check_rgb_metric).

The coefficient of variation ('cv', Pearson 1896) is 100 × the standard deviation / the mean, in %: of the images of
each pixel (as a metric, or between the years), or of the pixels of a region (as a statistic of the region: see
region_reducer and value_of). Earth Engine has no reducer of it: it is computed from those of the mean and of the
standard deviation (population, as std), without a value where the mean is 0. It compares the variability of
variables with a true zero and positive values (precipitation, NDVI of vegetation, albedo); with a mean near 0 (an
index around 0, a temperature in °C) it is huge and has no meaning.

The period is [first day, last day] (both included). A season ['MM-DD', 'MM-DD'] keeps only those days of each year;
it can cross the new year (['11-01', '02-28']), and then it belongs to the year in which it starts.
"""

import calendar
import datetime as dt
import re

import ee

TEMPORAL = ('period', 'annual', 'monthly', '16-day')
METRICS = ('mean, median, mode, min, max, sum, std (standard deviation), cv (coefficient of variation, %), count or '
           'pN (percentile N, e.g. p95, p2.5)')
SIMPLE = ('mean', 'median', 'mode', 'min', 'max', 'sum', 'std', 'cv', 'count')
RGB_METRICS = 'mean, median, min, max or pN'  # the metrics of the true colour (see the docstring)
MOSAICS = ('max', 'min')  # the metrics of the true colour taken from one image (qualityMosaic)
CV = 'cv'  # the coefficient of variation (see the docstring)
# the metrics whose values are not in the range of the variable: their colour ramp comes from the map, not the catalog
SPREAD = ('std', 'cv')


def _low(metric):
	return str(metric).strip().lower()


def is_cv(metric):
	"""Whether METRIC is the coefficient of variation."""
	return _low(metric) == CV


def reducer(metric):
	"""Earth Engine reducer of a metric. That of the coefficient of variation ('cv') is that of the mean and the
	standard deviation (outputs mean and stdDev), from which it is computed (see cv and value_of)."""
	m = _low(metric)
	simple = {'mean': ee.Reducer.mean, 'median': ee.Reducer.median, 'mode': ee.Reducer.mode,
	          'min': ee.Reducer.min, 'max': ee.Reducer.max, 'sum': ee.Reducer.sum,
	          'std': ee.Reducer.stdDev, 'count': ee.Reducer.count}
	if m in simple:
		return simple[m]()
	if m == CV:
		return ee.Reducer.mean().combine(ee.Reducer.stdDev(), '', True)
	p = re.fullmatch(r'p(\d+(?:\.\d+)?)', m)
	if p and 0 <= float(p.group(1)) <= 100:
		return ee.Reducer.percentile([float(p.group(1))])
	raise ValueError(f'unknown metric {metric}: use {METRICS}')


def check_metric(metric):
	"""Raise ValueError if METRIC is not valid (without Earth Engine)."""
	m = _low(metric)
	if m in SIMPLE:
		return
	p = re.fullmatch(r'p(\d+(?:\.\d+)?)', m)
	if not (p and 0 <= float(p.group(1)) <= 100):
		raise ValueError(f'unknown metric {metric}: use {METRICS}')


def cv(mean, std):
	"""ee.Image of the coefficient of variation (%) from the ee.Images of the mean and of the standard deviation:
	100 × STD / MEAN, masked where the mean is 0 (Earth Engine would give 0 there)."""
	mean, std = ee.Image(mean), ee.Image(std)
	return std.divide(mean).multiply(100).updateMask(mean.neq(0))


def cv_number(mean, std):
	"""The coefficient of variation (%) of the numbers MEAN and STD (Python), or None without them or with a mean
	of 0."""
	if mean is None or std is None or mean == 0:
		return None
	return 100.0 * std / mean


def _bases(stats):
	"""The metrics whose reducers give STATS, each once: the coefficient of variation needs the mean and the
	standard deviation (Earth Engine refuses two outputs with the same name)."""
	out = []
	for s in stats:
		for b in (('mean', 'std') if is_cv(s) else (_low(s),)):
			if b not in out:
				out.append(b)
	return out


def region_reducer(stats, count=True):
	"""ee.Reducer of the statistics STATS (e.g. ['mean', 'cv', 'p95']) over a region, for an image of one band
	(with COUNT, also the number of pixels, output count), and the names of the outputs of its reducers, {metric:
	output} (e.g. {'mean': 'mean', 'std': 'stdDev', 'p95': 'p95'}), from which value_of reads each statistic."""
	bases = _bases(stats)
	reds = [reducer(b) for b in bases]
	names = ee.List([r.getOutputs().get(0) for r in reds]).getInfo()
	red = ee.Reducer.count() if count else None
	for r in reds:
		red = r if red is None else red.combine(r, '', True)
	return red, dict(zip(bases, names))


def value_of(props, stat, names, prefix=''):
	"""The statistic STAT of a region from the properties PROPS (a dict, from getInfo) of the result of
	region_reducer (NAMES), with PREFIX before the names of its outputs (the band, e.g. 's0_')."""
	if is_cv(stat):
		return cv_number(props.get(prefix + names['mean']), props.get(prefix + names['std']))
	return props.get(prefix + names[_low(stat)])


def ee_value_of(feature, stat, out, prefix=''):
	"""The statistic STAT of a region, in Earth Engine (ee.Feature FEATURE, the result of the reducer of STAT over a
	region): the output OUT (its name), or, for the coefficient of variation, 100 × stdDev / mean (null without them
	or with a mean of 0)."""
	feature = ee.Feature(feature)
	if not is_cv(stat):
		return feature.get(prefix + out if isinstance(out, str) else ee.String(prefix).cat(out))
	mean, std = feature.get(prefix + 'mean'), feature.get(prefix + 'stdDev')
	return ee.Algorithms.If(mean, ee.Algorithms.If(std, ee.Number(std).multiply(100).divide(mean), 0), None)


def check_rgb_metric(metric):
	"""Raise ValueError if METRIC does not give the true colour of the images (see the docstring)."""
	check_metric(metric)
	m = _low(metric)
	if m not in ('mean', 'median', 'min', 'max') and not m.startswith('p'):
		raise ValueError(f"the true colour of the images takes the metrics {RGB_METRICS}, not {metric}: the {m} of "
		                 'the red, green and blue bands is not a colour')


def _date(text):
	return dt.date.fromisoformat(str(text))


def _md(year, md):
	"""Date of MM-DD in YEAR (29 February is the 28th in common years)."""
	month, day = (int(x) for x in str(md).split('-'))
	return dt.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def windows(period, season=None):
	"""(year, first day, day after the last) of each year of PERIOD, or of each season of each year."""
	start, end = _date(period[0]), _date(period[1])
	if end < start:
		raise ValueError(f'period {period}: the end is before the start')
	out = []
	for y in range(start.year - (1 if season else 0), end.year + 1):
		if season:
			ws, we = _md(y, season[0]), _md(y, season[1])
			if we < ws:
				we = _md(y + 1, season[1])
		else:
			ws, we = dt.date(y, 1, 1), dt.date(y, 12, 31)
		ws, we = max(ws, start), min(we, end)
		if ws <= we:
			out.append((y, ws, we + dt.timedelta(days=1)))
	if not out:
		raise ValueError(f'no day of the season {season} in the period {period}')
	return out


def bins(win, temporal):
	"""(month, first day, day after the last) of the months or 16 days periods of a window."""
	_, ws, we = win
	out = []
	d = ws
	while d < we:
		if temporal == 'monthly':
			nxt = dt.date(d.year + d.month // 12, d.month % 12 + 1, 1)
		else:
			nxt = d + dt.timedelta(days=16)
		out.append((d.month, d, min(nxt, we)))
		d = nxt
	return out


def _iso(d):
	return d.isoformat()


def _reduce(col, metric, bands=('value',), mosaic=None):
	"""Image of COL reduced with METRIC (its name, or an ee.Reducer), with the bands BANDS (one, 'value', by default),
	all masked if COL is empty. With MOSAIC ('max' or 'min'), the bands of the image where the first band is highest or
	lowest on each pixel instead (the true colour of the date of the maximum or minimum of the variable)."""
	bands = list(bands)
	empty = ee.Image.constant([0] * len(bands) if len(bands) > 1 else 0).toFloat().rename(bands).updateMask(0)
	if isinstance(metric, str) and is_cv(metric):  # one band: the true colour refuses it (check_rgb_metric)
		both = col.reduce(reducer(CV))  # bands <band>_mean and <band>_stdDev
		out = cv(both.select(0), both.select(1)).rename(bands)
		return ee.Image(ee.Algorithms.If(col.size().gt(0), out, empty))
	red = reducer(metric) if isinstance(metric, str) else metric
	if mosaic == 'max':
		out = col.qualityMosaic(bands[0]).select(bands)
	elif mosaic == 'min':
		low = col.map(lambda i: ee.Image(i).addBands(ee.Image(i).select(bands[0]).multiply(-1).rename('_low')))
		out = low.qualityMosaic('_low').select(bands)
	else:
		out = col.reduce(red).rename(bands)
	return ee.Image(ee.Algorithms.If(col.size().gt(0), out, empty))


def date_filter(wins):
	"""Filter of the dates of the windows."""
	filters = [ee.Filter.date(_iso(ws), _iso(we)) for _, ws, we in wins]
	return filters[0] if len(filters) == 1 else ee.Filter.Or(*filters)


def _mosaic(metric, bands):
	"""The mosaic of METRIC for an image with BANDS (see _reduce): only for the true colour, whose first band is the
	variable."""
	m = _low(metric)
	return m if len(bands) > 1 and m in MOSAICS else None


def composite(col, metric, temporal='period', interannual='mean', period=None, season=None, bands=('value',)):
	"""One image of the collection COL of images of PERIOD, aggregated as described in the docstring of the module:
	images with one band, 'value', or with BANDS, the variable ('value') and its true colour (red, green, blue)."""
	if temporal not in TEMPORAL:
		raise ValueError(f"unknown temporal aggregation {temporal}: use {', '.join(TEMPORAL)}")
	bands = tuple(bands)
	wins = windows(period, season)
	check_metric(metric)
	red, mosaic = metric, _mosaic(metric, bands)
	if temporal == 'period':
		return _reduce(col.filter(date_filter(wins)), red, bands, mosaic)
	check_metric(interannual)
	red2, mosaic2 = interannual, _mosaic(interannual, bands)
	if temporal == 'annual':
		years = [_reduce(col.filterDate(_iso(ws), _iso(we)), red, bands, mosaic) for _, ws, we in wins]
		return _reduce(ee.ImageCollection.fromImages(years), red2, bands, mosaic2)
	parts = {}
	for win in wins:
		for month, bs, be in bins(win, temporal):
			parts.setdefault(month, []).append(_reduce(col.filterDate(_iso(bs), _iso(be)), red, bands, mosaic))
	months = [_reduce(ee.ImageCollection.fromImages(imgs), red2, bands, mosaic2) for _, imgs in sorted(parts.items())]
	return _reduce(ee.ImageCollection.fromImages(months), 'mean', bands)
