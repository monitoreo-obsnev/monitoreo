"""Seasonal trends (Mann-Kendall test and Sen's slope) and the comparison of a reference period with another.

Parts of the year: each year of the period gives one value per part of STEP, the METRIC (the mean by default) of the
images of that part in that year:
  monthly  12 parts, the months (January of every year, February of every year, ...): m01 ... m12
  16-day   23 parts of 16 days from 1 January (days of the year 1-16, 17-32, ..., 353-366): p01 ... p23
  annual   1 part, the whole year (or the season of each year): all

The trend of each part is computed on its yearly values (on each pixel, or on a statistic of a region per year):
  n          years with data
  tau        Kendall's tau of the values against the years (-1 to 1)
  z          Mann-Kendall Z, normal approximation without correction for ties: tau * sqrt(9 n (n - 1) / (2 (2 n + 5)))
  p_value    two-sided p-value of Z, 2 (1 - Phi(|Z|))
  slope      Sen's slope: median of the slopes between pairs of years (units of the variable per year)
  intercept  value of the Sen line in the first year of the period (median of value - slope * (year - first year))
A part needs MIN_YEARS years with data; n is that of each pixel or region (years with data), not the number of
years of the period.

The comparison of periods aligns the values of a reference period and of another one by part (the same month or
16 days, or the year): the mean of the part over the years of each period and their difference (other - reference).
"""

import calendar
import datetime as dt
import math

import ee

from . import composite
from . import variable as variables

STEPS = ('monthly', '16-day', 'annual')
OUTPUTS = ('slope', 'tau', 'z', 'p_value', 'intercept', 'n')
MIN_YEARS = 2
MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
          'noviembre', 'diciembre']
DIVERGING = ['a50026', 'd73027', 'f46d43', 'fdae61', 'fee08b', 'ffffbf', 'd9ef8b', 'a6d96a', '66bd63', '1a9850',
             '006837']  # decrease (red) to increase (green)
P_VALUE = ['0571b0', '92c5de', 'f7f7f7']  # significant (blue) to not (white)
YEARS = ['fde725', '5ec962', '21918c', '3b528b', '440154']


def _check(step):
	if step not in STEPS:
		raise ValueError(f"unknown step {step} for trends and comparisons: use {', '.join(STEPS)}")


def parts(step):
	"""Parts of STEP: 1-12 (monthly), 1-23 (16-day) or [0] (annual)."""
	_check(step)
	return list(range(1, 13)) if step == 'monthly' else list(range(1, 24)) if step == '16-day' else [0]


def part_key(step, part):
	"""Short name of a part: m01, p01, all."""
	return f'm{part:02d}' if step == 'monthly' else f'p{part:02d}' if step == '16-day' else 'all'


def part_label(step, part):
	"""Name of a part for people: 'julio', 'días 177-192', 'año'."""
	if step == 'monthly':
		return MONTHS[part - 1]
	if step == '16-day':
		first = (part - 1) * 16 + 1
		return f'días {first}-{min(first + 15, 366)}'
	return 'año'


def part_of(step, day):
	"""Part of the year of the date DAY."""
	if step == 'monthly':
		return day.month
	if step == '16-day':
		return (day.timetuple().tm_yday - 1) // 16 + 1
	return 0


def _part_span(step, part, year):
	"""(first day, day after the last) of a part in YEAR."""
	if step == 'monthly':
		last = calendar.monthrange(year, part)[1]
		return dt.date(year, part, 1), dt.date(year, part, last) + dt.timedelta(days=1)
	if step == '16-day':
		first = dt.date(year, 1, 1) + dt.timedelta(days=(part - 1) * 16)
		return first, min(first + dt.timedelta(days=16), dt.date(year + 1, 1, 1))
	return dt.date(year, 1, 1), dt.date(year + 1, 1, 1)


def seasonal_bins(spec, step):
	"""[(part, year, first day, day after the last)] ('YYYY-MM-DD') of the parts of every year of the period (and
	season) of SPEC. The year of a season that crosses the new year is that in which it starts."""
	_check(step)
	out = []
	for year, ws, we in composite.windows(spec['period'], spec['season']):
		if step == 'annual':
			out.append((0, year, ws.isoformat(), we.isoformat()))
			continue
		for y in range(ws.year, we.year + 1):
			for u in parts(step):
				a, b = _part_span(step, u, y)
				a, b = max(a, ws), min(b, we)
				if a < b:
					out.append((u, year, a.isoformat(), b.isoformat()))
	return out


# Trends on each pixel -----------------------------------------------------------------------------------------------

def yearly_collection(spec, region, res, step, part, metric='mean'):
	"""ee.ImageCollection, in the order of the years, of images with the bands 't' (the year) and 'value' (METRIC
	of the images of PART in that year, masked if it has none)."""
	col = variables.collection(spec, region, res)
	red = composite.reducer(metric)
	imgs = []
	for u, year, a, b in seasonal_bins(spec, step):
		if u == part:
			value = composite._reduce(col.filterDate(a, b), red)
			imgs.append(ee.Image.constant(year).toFloat().rename('t').updateMask(value.mask()).addBands(value))
	if not imgs:
		raise ValueError(f'the period has no {part_label(step, part)}')
	return ee.ImageCollection.fromImages(imgs)


def trend_image(spec, region, res, step='annual', part=0, metric='mean', min_years=MIN_YEARS):
	"""ee.Image with the bands of OUTPUTS (see the docstring of the module) of the trend of PART of STEP of the
	variable SPEC over REGION, on pixels of RES metres; masked where there are fewer than MIN_YEARS years."""
	col = yearly_collection(spec, region, res, step, part, metric)
	first = float(composite.windows(spec['period'], spec['season'])[0][0])
	n = col.select('value').count().rename('n')
	tau = col.select('value').reduce(ee.Reducer.kendallsCorrelation()).select('value_tau').rename('tau')
	z = tau.multiply(n.multiply(n.subtract(1)).multiply(9).divide(n.multiply(2).add(5).multiply(2)).sqrt()).rename('z')
	p = ee.Image.constant(1).subtract(z.abs().divide(math.sqrt(2)).erf()).rename('p_value')
	sen = col.select(['t', 'value']).reduce(ee.Reducer.sensSlope())
	slope = sen.select('slope')
	intercept = sen.select('offset').add(slope.multiply(first)).rename('intercept')
	out = ee.Image.cat([slope, tau, z, p, intercept, n.toFloat()]).rename(list(OUTPUTS))
	return out.updateMask(n.gte(min_years))


def vis(output, lo=None, hi=None):
	"""Colour ramp of an output of the trends (or of a difference, output='difference') from the range of its
	values LO-HI: symmetric around 0 for slope, z and differences."""
	if output == 'tau':
		return {'min': -1.0, 'max': 1.0, 'palette': DIVERGING}
	if output == 'p_value':
		return {'min': 0.0, 'max': 0.1, 'palette': P_VALUE}
	if output in ('slope', 'z', 'difference'):
		m = max(abs(lo or 0), abs(hi or 0)) or (1.96 if output == 'z' else 1e-6)
		return {'min': -m, 'max': m, 'palette': DIVERGING}
	if output == 'n':
		return {'min': lo if lo is not None else 0, 'max': hi if hi is not None else 10, 'palette': YEARS}
	return None  # intercept: the colours of the variable


# Trends of a series -------------------------------------------------------------------------------------------------

def mann_kendall(years, values):
	"""(n, tau, z, p_value) of VALUES against YEARS (lists of the same length, None values left out)."""
	pts = sorted((x, y) for x, y in zip(years, values) if y is not None)
	n = len(pts)
	if n < 2:
		return n, None, None, None
	s = sum((pts[j][1] > pts[i][1]) - (pts[j][1] < pts[i][1]) for i in range(n) for j in range(i + 1, n))
	tau = s / (n * (n - 1) / 2)
	z = tau * math.sqrt(9 * n * (n - 1) / (2 * (2 * n + 5)))
	return n, tau, z, math.erfc(abs(z) / math.sqrt(2))


def _median(xs):
	xs = sorted(xs)
	m = len(xs) // 2
	return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def sen(years, values, first=None):
	"""(slope, intercept) of the Sen line of VALUES against YEARS; the intercept is its value in FIRST (default: the
	first year with a value)."""
	pts = sorted((x, y) for x, y in zip(years, values) if y is not None)
	if len(pts) < 2:
		return None, None
	slope = _median([(pts[j][1] - pts[i][1]) / (pts[j][0] - pts[i][0])
	                 for i in range(len(pts)) for j in range(i + 1, len(pts)) if pts[j][0] != pts[i][0]])
	first = pts[0][0] if first is None else first
	return slope, _median([y - slope * (x - first) for x, y in pts])


def trend_rows(yearly, step, first=None, min_years=MIN_YEARS, alpha=0.05):
	"""Trend of each region and part of YEARLY ([{region, part, year, value}]): [{region, part, key, label, n, tau,
	z, p_value, significant, slope, intercept, first_year, last_year}], significant if p_value < ALPHA."""
	groups = {}
	for r in yearly:
		groups.setdefault((r['region'], r['part']), []).append(r)
	out = []
	for (region, part), rows in sorted(groups.items()):
		years = [r['year'] for r in rows]
		values = [r['value'] for r in rows]
		n, tau, z, p = mann_kendall(years, values)
		ok = n >= min_years and tau is not None
		slope, intercept = sen(years, values, first) if ok else (None, None)
		valid = [x for x, y in zip(years, values) if y is not None]
		out.append({'region': region, 'part': part, 'key': part_key(step, part), 'label': part_label(step, part),
		            'n': n, 'tau': tau if ok else None, 'z': z if ok else None, 'p_value': p if ok else None,
		            'significant': bool(ok and p < alpha), 'slope': slope, 'intercept': intercept,
		            'first_year': min(valid) if valid else None, 'last_year': max(valid) if valid else None})
	return out


# Comparison of periods ----------------------------------------------------------------------------------------------

def profile(reference, other):
	"""Mean of each region and part over the years of the REFERENCE and OTHER periods ([{region, part, year,
	value}] each): [{region, part, reference, other, difference, n_reference, n_other}]."""
	def means(rows):
		acc = {}
		for r in rows:
			if r['value'] is not None:
				acc.setdefault((r['region'], r['part']), []).append(r['value'])
		return {k: (sum(v) / len(v), len(v)) for k, v in acc.items()}

	ref, oth = means(reference), means(other)
	keys = sorted(set(ref) | set(oth) | {(r['region'], r['part']) for r in reference + other})
	out = []
	for region, part in keys:
		a, na = ref.get((region, part), (None, 0))
		b, nb = oth.get((region, part), (None, 0))
		out.append({'region': region, 'part': part, 'reference': a, 'other': b,
		            'difference': None if a is None or b is None else b - a, 'n_reference': na, 'n_other': nb})
	return out
