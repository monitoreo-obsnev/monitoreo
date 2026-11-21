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

Serial correlation: yearly values that depend on those of the years before (e.g. a slow recovery of the vegetation)
make the Mann-Kendall test find significant trends too often. TEST chooses the test of each trend (TESTS):
  mk         the Mann-Kendall test above (the default)
  hamed-rao  Hamed & Rao (1998): the variance of S multiplied by n/n*, from the autocorrelation of the ranks of the
             values without their trend (value - slope * year, with Sen's slope; values closer than 1e-6 relative
             are tied, as the slope is rounded):
               n/n* = 1 + 2 / (n (n - 1) (n - 2)) * sum of (n - k) (n - k - 1) (n - k - 2) r_k, lags k = 1 ... n - 3
             with only the significant r_k (|r_k| > 1.96 / sqrt(n), 5 %), as in Yue et al. (2002, eq. 13) and the
             packages modifiedmk and pyMannKendall; z is that of mk divided by sqrt(n/n*), tau is that of mk. An
             estimate n/n* <= 0 (possible with few years) is not used: n/n* = 1 (the test is mk). n_ratio is n/n*.
  tfpw       trend-free pre-whitening of Yue et al. (2002): the values without their Sen trend,
             X' = value - slope * year; their lag-1 autocorrelation r1; the pre-whitened values Y' = X'(year) - r1 X'(year - 1); the blended
             series Y = Y' + slope * year (one value less: a year needs the year before); tau, z and p_value are those
             of the Mann-Kendall test of Y (n stays the years with data of the values). r1 is the r1 used.
The autocorrelation of lag k is r_k = sum (a(t) - m) (a(t + k) - m) / sum (a(t) - m)^2 over the years t and t + k
with data (m: the mean of the years with data), the estimator of pyMannKendall; the lags are years of the calendar,
so a year without data does not join the years before and after it (with every year, as those packages). The slope
and the intercept are always Sen's, of the values. A correction needs 3 years with data (tfpw: and 2 blended values).

The comparison of periods aligns the values of a reference period and of another one by part (the same month or
16 days, or the year): the mean of the part over the years of each period and their difference (other - reference).

References (monitoreo.references gives them, with those of the data, with each result):
    Mann, H. B. (1945). Nonparametric tests against trend. Econometrica, 13(3), 245–259.
      https://doi.org/10.2307/1907187
    Kendall, M. G. (1938). A new measure of rank correlation. Biometrika, 30(1–2), 81–93.
      https://doi.org/10.1093/biomet/30.1-2.81
    Sen, P. K. (1968). Estimates of the regression coefficient based on Kendall's tau. Journal of the American
      Statistical Association, 63(324), 1379–1389. https://doi.org/10.1080/01621459.1968.10480934
    Hamed, K. H., & Rao, A. R. (1998). A modified Mann-Kendall trend test for autocorrelated data. Journal of
      Hydrology, 204(1–4), 182–196. https://doi.org/10.1016/S0022-1694(97)00125-X
    Yue, S., Pilon, P., Phinney, B., & Cavadias, G. (2002). The influence of autocorrelation on the ability to detect
      trend in hydrological series. Hydrological Processes, 16(9), 1807–1829. https://doi.org/10.1002/hyp.1095
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
TESTS = ('mk', 'hamed-rao', 'tfpw')
TEST_NAMES = {'mk': 'Mann-Kendall', 'hamed-rao': 'Mann-Kendall modified by Hamed and Rao (1998)',
              'tfpw': 'Mann-Kendall with trend-free pre-whitening (Yue et al. 2002)'}
TEST_SHORT = {'mk': 'Mann-Kendall', 'hamed-rao': 'Hamed-Rao', 'tfpw': 'TFPW'}
Z_LAG = 1.96  # the bound of a significant autocorrelation of the ranks (Hamed-Rao): 1.96 / sqrt(n), 5 %
TIE = 1e-6  # values without their trend that differ by less than TIE (relative) are tied (rounding of the slope and
# the float32 values of Earth Engine)
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December']
DIVERGING = ['a50026', 'd73027', 'f46d43', 'fdae61', 'fee08b', 'ffffbf', 'd9ef8b', 'a6d96a', '66bd63', '1a9850',
             '006837']  # decrease (red) to increase (green)
P_VALUE = ['0571b0', '92c5de', 'f7f7f7']  # significant (blue) to not (white)
YEARS = ['fde725', '5ec962', '21918c', '3b528b', '440154']


def _check(step):
	if step not in STEPS:
		raise ValueError(f"unknown step {step} for trends and comparisons: use {', '.join(STEPS)}")


def check_test(test):
	"""TEST ('mk' when None), or a ValueError if it is not one of TESTS."""
	test = 'mk' if test in (None, '') else str(test).lower()
	if test not in TESTS:
		raise ValueError(f"unknown trend test {test}: use {', '.join(TESTS)}")
	return test


def test_note(test, sep=', '):
	"""'' for the Mann-Kendall test, else SEP and the short name of TEST (for titles)."""
	test = check_test(test)
	return '' if test == 'mk' else f'{sep}{TEST_SHORT[test]} test'


def parts(step):
	"""Parts of STEP: 1-12 (monthly), 1-23 (16-day) or [0] (annual)."""
	_check(step)
	return list(range(1, 13)) if step == 'monthly' else list(range(1, 24)) if step == '16-day' else [0]


def part_key(step, part):
	"""Short name of a part: m01, p01, all."""
	return f'm{part:02d}' if step == 'monthly' else f'p{part:02d}' if step == '16-day' else 'all'


def part_label(step, part):
	"""Name of a part for people: 'July', 'days 177-192', 'year'."""
	if step == 'monthly':
		return MONTHS[part - 1]
	if step == '16-day':
		first = (part - 1) * 16 + 1
		return f'days {first}-{min(first + 15, 366)}'
	return 'year'


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

def _yearly_images(spec, region, res, step, part, metric):
	"""[(year, image 'value': METRIC of the images of PART in that year, masked if it has none)], by year."""
	col = variables.collection(spec, region, res)
	composite.check_metric(metric)
	out = [(year, composite.reduce_span(col, metric, a, b)) for u, year, a, b in seasonal_bins(spec, step) if u == part]
	if not out:
		raise ValueError(f'the period has no {part_label(step, part)}')
	return out


def _with_years(images):
	return ee.ImageCollection.fromImages(
		[ee.Image.constant(year).toFloat().rename('t').updateMask(value.mask()).addBands(value) for year, value in images])


def yearly_collection(spec, region, res, step, part, metric='mean'):
	"""ee.ImageCollection, in the order of the years, of images with the bands 't' (the year) and 'value' (METRIC
	of the images of PART in that year, masked if it has none)."""
	return _with_years(_yearly_images(spec, region, res, step, part, metric))


def _z_of(tau, n):
	"""Mann-Kendall Z of the images TAU and N (years): tau * sqrt(9 n (n - 1) / (2 (2 n + 5)))."""
	return tau.multiply(n.multiply(n.subtract(1)).multiply(9).divide(n.multiply(2).add(5).multiply(2)).sqrt())


def _sum(images):
	return ee.ImageCollection.fromImages([i.unmask(0) for i in images]).sum() if images else ee.Image.constant(0)


def _lag_r(series, k, mean, den):
	"""Image of the autocorrelation of lag K (years) of SERIES ({year: image}): sum (a(t) - mean) (a(t + k) -
	mean) over the years t and t + k with data / DEN (0 where DEN is 0)."""
	num = _sum([series[t].subtract(mean).multiply(series[t + k].subtract(mean)) for t in series if t + k in series])
	return num.divide(den).where(den.eq(0), 0)


def _hamed_rao_image(series, slope, n, first):
	"""Image n/n* of Hamed & Rao (1998) of SERIES ({year: image of the value}), with the image SLOPE (Sen) and N
	(years with data), the years counted from FIRST; see the docstring of the module."""
	detrended = {t: v.subtract(slope.multiply(t - first)) for t, v in series.items()}
	ranks = {}
	for t, d in detrended.items():  # 1 + the values below + half the others tied with it (ties: the mean rank)
		below = []
		for u, o in detrended.items():
			if u != t:
				tied = o.subtract(d).abs().lte(o.abs().add(d.abs()).multiply(TIE))
				below.append(o.lt(d).And(tied.Not()).add(tied.multiply(0.5)))
		ranks[t] = _sum(below).add(1).updateMask(d.mask())
	mean = n.add(1).divide(2)
	den = _sum([r.subtract(mean).pow(2) for r in ranks.values()])
	years = sorted(series)
	total = ee.Image.constant(0)
	bound = ee.Image.constant(Z_LAG).divide(n.sqrt())
	for k in range(1, years[-1] - years[0] + 1):
		r = _lag_r(ranks, k, mean, den)
		weight = n.subtract(k).multiply(n.subtract(k + 1)).multiply(n.subtract(k + 2))
		use = r.abs().gt(bound).And(n.gte(k + 3))  # significant, and a lag of 1 ... n - 3
		total = total.add(weight.multiply(r).multiply(use))
	ratio = total.multiply(2).divide(n.multiply(n.subtract(1)).multiply(n.subtract(2))).add(1)
	return ratio.where(ratio.lte(0).Or(n.lt(3)), 1)


def _tfpw_images(series, slope, n, first):
	"""([(year, image of the blended value Y)], image r1) of the trend-free pre-whitening of Yue et al. (2002) of
	SERIES ({year: image of the value}), with the image SLOPE (Sen) and N (years with data), the years counted from
	FIRST."""
	detrended = {t: v.subtract(slope.multiply(t - first)) for t, v in series.items()}
	mean = _sum(list(detrended.values())).divide(n)
	den = _sum([d.subtract(mean).pow(2) for d in detrended.values()])
	r1 = _lag_r(detrended, 1, mean, den)
	blended = [(t, d.subtract(detrended[t - 1].multiply(r1)).add(slope.multiply(t - first)).rename('value'))
	           for t, d in sorted(detrended.items()) if t - 1 in detrended]
	return blended, r1


def trend_image(spec, region, res, step='annual', part=0, metric='mean', min_years=MIN_YEARS, test='mk'):
	"""ee.Image with the bands of OUTPUTS (see the docstring of the module) of the trend of PART of STEP of the
	variable SPEC over REGION, on pixels of RES metres, with the trend test TEST (TESTS); masked where there are
	fewer than MIN_YEARS years."""
	test = check_test(test)
	images = _yearly_images(spec, region, res, step, part, metric)
	col = _with_years(images)
	first = float(composite.windows(spec['period'], spec['season'])[0][0])
	n = col.select('value').count().toDouble().rename('n')  # a double: (n + 1) / 2 and 9 n (n - 1) / ... not truncated
	sen = col.select(['t', 'value']).reduce(ee.Reducer.sensSlope())
	slope = sen.select('slope')
	series = {year: value.rename('value').toDouble() for year, value in images}
	y0 = images[0][0]
	if test == 'tfpw':
		blended, _ = _tfpw_images(series, slope, n, y0)
		if blended:
			bcol = _with_years(blended)
			nb = bcol.select('value').count().toDouble()
			tau = bcol.select('value').reduce(ee.Reducer.kendallsCorrelation()).select('value_tau')
		else:  # a single year: no blended values
			nb, tau = ee.Image.constant(0).toDouble(), ee.Image.constant(0).toDouble().updateMask(0)
		z = _z_of(tau, nb).updateMask(nb.gte(2).And(n.gte(3)))
		tau = tau.updateMask(z.mask())
	else:
		tau = col.select('value').reduce(ee.Reducer.kendallsCorrelation()).select('value_tau')
		z = _z_of(tau, n)
		if test == 'hamed-rao':
			z = z.divide(_hamed_rao_image(series, slope, n, y0).sqrt()).updateMask(n.gte(3))
			tau = tau.updateMask(n.gte(3))
	p = ee.Image.constant(1).subtract(z.abs().divide(math.sqrt(2)).erf())
	intercept = sen.select('offset').add(slope.multiply(first))
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


def lag_r(series, k):
	"""Autocorrelation of lag K (years) of SERIES ({year: value}): sum (a(t) - m) (a(t + k) - m) over the years t
	and t + k with data / sum (a(t) - m)^2 (m: the mean); 0 if the values are all equal."""
	m = sum(series.values()) / len(series)
	den = sum((a - m) ** 2 for a in series.values())
	num = sum((a - m) * (series[t + k] - m) for t, a in series.items() if t + k in series)
	return num / den if den else 0.0


def _tied(a, b):
	return abs(a - b) <= TIE * (abs(a) + abs(b))


def _ranks(values):
	"""Ranks of VALUES (1 ... n; ties, values that differ by less than TIE: their mean rank)."""
	return [1 + sum(0.5 if _tied(o, v) else float(o < v) for j, o in enumerate(values) if j != i)
	        for i, v in enumerate(values)]


def hamed_rao_ratio(years, values, slope):
	"""n/n* of Hamed & Rao (1998) of VALUES against YEARS, with Sen's SLOPE (see the docstring of the module); 1
	with fewer than 3 years or an estimate <= 0."""
	pts = sorted((x, y) for x, y in zip(years, values) if y is not None)
	n = len(pts)
	if n < 3:
		return 1.0
	ranks = dict(zip([x for x, _ in pts], _ranks([y - slope * (x - pts[0][0]) for x, y in pts])))
	total = 0.0
	for k in range(1, min(n - 3, pts[-1][0] - pts[0][0]) + 1):
		r = lag_r(ranks, k)
		if abs(r) > Z_LAG / math.sqrt(n):
			total += (n - k) * (n - k - 1) * (n - k - 2) * r
	ratio = 1 + 2 * total / (n * (n - 1) * (n - 2))
	return ratio if ratio > 0 else 1.0


def tfpw_series(years, values, slope):
	"""(years, blended values, r1) of the trend-free pre-whitening of Yue et al. (2002) of VALUES against YEARS,
	with Sen's SLOPE (see the docstring of the module)."""
	pts = sorted((x, y) for x, y in zip(years, values) if y is not None)
	x0 = pts[0][0] if pts else 0  # the years from the first: the same blended trend, without rounding
	detrended = {x: y - slope * (x - x0) for x, y in pts}
	r1 = lag_r(detrended, 1) if len(detrended) > 1 else 0.0
	out = [(x, d - r1 * detrended[x - 1] + slope * (x - x0)) for x, d in detrended.items() if x - 1 in detrended]
	return [x for x, _ in out], [y for _, y in out], r1


def trend_test(years, values, test='mk'):
	"""{n, tau, z, p_value, n_ratio, r1} of VALUES against YEARS with the trend test TEST (TESTS; see the
	docstring of the module): n is the years with data; n_ratio (hamed-rao) and r1 (tfpw) None for the other tests;
	tau, z and p_value None if the test needs more years."""
	test = check_test(test)
	n, tau, z, p = mann_kendall(years, values)
	out = {'n': n, 'tau': tau, 'z': z, 'p_value': p, 'n_ratio': None, 'r1': None}
	if test == 'mk' or tau is None:
		return out
	if n < 3:
		return dict(out, tau=None, z=None, p_value=None)
	slope, _ = sen(years, values)
	if test == 'hamed-rao':
		ratio = hamed_rao_ratio(years, values, slope)
		z = z / math.sqrt(ratio)
		return dict(out, z=z, p_value=math.erfc(abs(z) / math.sqrt(2)), n_ratio=ratio)
	by, bv, r1 = tfpw_series(years, values, slope)
	nb, tau, z, p = mann_kendall(by, bv)
	return dict(out, tau=tau, z=z, p_value=p, r1=r1)


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


def trend_rows(yearly, step, first=None, min_years=MIN_YEARS, alpha=0.05, test='mk'):
	"""Trend of each region and part of YEARLY ([{region, part, year, value}]) with the trend test TEST (TESTS):
	[{region, part, key, label, n, tau, z, p_value, significant, slope, intercept, first_year, last_year, n_ratio,
	r1}], significant if p_value < ALPHA; n_ratio (n/n*, hamed-rao) and r1 (tfpw) None for the other tests."""
	test = check_test(test)
	groups = {}
	for r in yearly:
		groups.setdefault((r['region'], r['part']), []).append(r)
	out = []
	for (region, part), rows in sorted(groups.items()):
		years = [r['year'] for r in rows]
		values = [r['value'] for r in rows]
		t = trend_test(years, values, test)
		n, tau, z, p = t['n'], t['tau'], t['z'], t['p_value']
		ok = n >= min_years and tau is not None
		# Sen's line with the years of the map (a correction that needs more years leaves only the test without values)
		slope, intercept = sen(years, values, first) if n >= max(min_years, 2) else (None, None)
		valid = [x for x, y in zip(years, values) if y is not None]
		out.append({'region': region, 'part': part, 'key': part_key(step, part), 'label': part_label(step, part),
		            'n': n, 'tau': tau if ok else None, 'z': z if ok else None, 'p_value': p if ok else None,
		            'significant': bool(ok and p < alpha), 'slope': slope, 'intercept': intercept,
		            'first_year': min(valid) if valid else None, 'last_year': max(valid) if valid else None,
		            'n_ratio': t['n_ratio'] if ok else None, 'r1': t['r1'] if ok else None})
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
