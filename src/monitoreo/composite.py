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
bands of several (clouds, snow). The metrics that do not give colours (sum, std, count, mode) are refused
(check_rgb_metric).

The period is [first day, last day] (both included). A season ['MM-DD', 'MM-DD'] keeps only those days of each year;
it can cross the new year (['11-01', '02-28']), and then it belongs to the year in which it starts.
"""

import calendar
import datetime as dt
import re

import ee

TEMPORAL = ('period', 'annual', 'monthly', '16-day')
METRICS = 'mean, median, mode, min, max, sum, std, count or pN (percentile N, e.g. p95, p2.5)'
RGB_METRICS = 'mean, median, min, max or pN'  # the metrics of the true colour (see the docstring)
MOSAICS = ('max', 'min')  # the metrics of the true colour taken from one image (qualityMosaic)


def reducer(metric):
	"""Earth Engine reducer of a metric."""
	m = str(metric).strip().lower()
	simple = {'mean': ee.Reducer.mean, 'median': ee.Reducer.median, 'mode': ee.Reducer.mode,
	          'min': ee.Reducer.min, 'max': ee.Reducer.max, 'sum': ee.Reducer.sum,
	          'std': ee.Reducer.stdDev, 'count': ee.Reducer.count}
	if m in simple:
		return simple[m]()
	p = re.fullmatch(r'p(\d+(?:\.\d+)?)', m)
	if p and 0 <= float(p.group(1)) <= 100:
		return ee.Reducer.percentile([float(p.group(1))])
	raise ValueError(f'unknown metric {metric}: use {METRICS}')


def check_metric(metric):
	"""Raise ValueError if METRIC is not valid (without Earth Engine)."""
	m = str(metric).strip().lower()
	if m in ('mean', 'median', 'mode', 'min', 'max', 'sum', 'std', 'count'):
		return
	p = re.fullmatch(r'p(\d+(?:\.\d+)?)', m)
	if not (p and 0 <= float(p.group(1)) <= 100):
		raise ValueError(f'unknown metric {metric}: use {METRICS}')


def check_rgb_metric(metric):
	"""Raise ValueError if METRIC does not give the true colour of the images (see the docstring)."""
	check_metric(metric)
	m = str(metric).strip().lower()
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


def _reduce(col, red, bands=('value',), mosaic=None):
	"""Image of COL reduced with RED, with the bands BANDS (one, 'value', by default), all masked if COL is empty.
	With MOSAIC ('max' or 'min'), the bands of the image where the first band is highest or lowest on each pixel
	instead (the true colour of the date of the maximum or minimum of the variable)."""
	bands = list(bands)
	empty = ee.Image.constant([0] * len(bands) if len(bands) > 1 else 0).toFloat().rename(bands).updateMask(0)
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
	m = str(metric).strip().lower()
	return m if len(bands) > 1 and m in MOSAICS else None


def composite(col, metric, temporal='period', interannual='mean', period=None, season=None, bands=('value',)):
	"""One image of the collection COL of images of PERIOD, aggregated as described in the docstring of the module:
	images with one band, 'value', or with BANDS, the variable ('value') and its true colour (red, green, blue)."""
	if temporal not in TEMPORAL:
		raise ValueError(f"unknown temporal aggregation {temporal}: use {', '.join(TEMPORAL)}")
	bands = tuple(bands)
	wins = windows(period, season)
	red, mosaic = reducer(metric), _mosaic(metric, bands)
	if temporal == 'period':
		return _reduce(col.filter(date_filter(wins)), red, bands, mosaic)
	red2, mosaic2 = reducer(interannual), _mosaic(interannual, bands)
	if temporal == 'annual':
		years = [_reduce(col.filterDate(_iso(ws), _iso(we)), red, bands, mosaic) for _, ws, we in wins]
		return _reduce(ee.ImageCollection.fromImages(years), red2, bands, mosaic2)
	parts = {}
	for win in wins:
		for month, bs, be in bins(win, temporal):
			parts.setdefault(month, []).append(_reduce(col.filterDate(_iso(bs), _iso(be)), red, bands, mosaic))
	months = [_reduce(ee.ImageCollection.fromImages(imgs), red2, bands, mosaic2) for _, imgs in sorted(parts.items())]
	return _reduce(ee.ImageCollection.fromImages(months), ee.Reducer.mean(), bands)
