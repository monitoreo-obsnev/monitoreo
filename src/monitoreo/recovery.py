"""Severity and recovery after a disturbance from a time series: the metrics of the post-fire trajectories of Marcos
et al. (2023, Remote Sensing of Environment 286:113441, doi:10.1016/j.rse.2022.113441, sections 2.3 and 2.4), the
standardized anomalies of the steps after the event and the trends before and after it, of a series of an affected
area and, with a control area, of the control and of their difference (a BACI design), which separates the effect of
the disturbance from the variability of the climate of the region. Used by services.recovery_metrics.

The series (rows of time_series, a step monthly, 16-day or annual) is put on a regular grid, its gaps filled by linear
interpolation (their share is in the answer). Then:

- STL (Cleveland et al. 1990, robust; monitoreo.stl) with windows of the seasonal and the trend smoothers equal to the
  smallest odd number greater than the steps per year (13 monthly, 25 of 16 days); the deseasonalized series is the
  series minus its seasonal component. An annual series has no seasonality: its trend is a running median of 3 years.
- The reference: the median ± 1 MAD of the deseasonalized series in the REFERENCE_YEARS before the event.
- S95 = reference median - percentile 95 of the deseasonalized series in the first year after the event (S05 with
  the percentile 5): the direction of the change is that of the median of that year, and the extreme (percentile 5
  in a drop, 95 in a rise) gives the impact, in % of the reference median and in MADs.
- tINF, the first inflection of the trend after the event (its first local maximum of distance from the reference
  median, with a quarter of a year on each side); DIT = tINF - event.
- tREF, the first step from tINF when both the trend and the running median of a year of the deseasonalized series are
  in the reference interval; RRT = tREF - event (the recovery time).
- tEQ, the first of at least two consecutive medians of windows of a year (from tINF) whose relative change is below
  EQUILIBRIUM (5 %); RET = tEQ - event (the time to a new equilibrium). In the difference (affected - control), whose
  value is about 0, a relative change has no meaning: a change below 1 MAD of the reference instead.
- The share of the initial loss recovered in the last year with data.
- The standardized anomalies (z) of each step after the event against the steps of the same month (or 16 days) of
  every year before it; their extremes in the first year and the steps with |z| > 2.
- The Mann-Kendall test and the Sen slope of the yearly means before and after the year of the event.
- The seasonal amplitude (maximum - minimum of the seasonal component of STL in each year), its median in the years
  before and after the event: a change of the phenology (e.g. from an evergreen to a deciduous canopy).

It ports herramientas/metricas_recuperacion.py of the EVEREST case studies (2026-11), which used pandas and statsmodels.
"""

import calendar
import datetime as dt
import math

import numpy as np

from . import stl, trends

STEPS_PER_YEAR = {'monthly': 12, '16-day': 23, 'annual': 1}
REFERENCE_YEARS = 3
EQUILIBRIUM = 0.05


def check(step, event, start, end, reference_years=REFERENCE_YEARS, equilibrium=EQUILIBRIUM, season=None):
	"""(step, event date, reference years, equilibrium) checked, before Earth Engine: ValueError if the step is daily,
	the event is not a date inside the period, there are not REFERENCE_YEARS before it, or a SEASON goes with a monthly
	or 16-day step (the rest of each year would have no values, filled by interpolation)."""
	if step not in STEPS_PER_YEAR:
		raise ValueError(f'the recovery metrics need a series of step monthly (the best), 16-day or annual, not {step}')
	if season and step != 'annual':
		raise ValueError('a season with a monthly or 16-day step leaves the rest of each year without values, which the '
		                 'recovery metrics would fill by interpolation: no season, or step annual with the season')
	try:
		ev = dt.date.fromisoformat(str(event)[:10])
	except ValueError:
		raise ValueError(f'event: the date of the disturbance, YYYY-MM-DD, not {event!r}') from None
	s, e = dt.date.fromisoformat(str(start)[:10]), dt.date.fromisoformat(str(end)[:10])
	try:
		reference_years = int(reference_years)
		equilibrium = float(equilibrium)
	except (TypeError, ValueError):
		raise ValueError('reference_years is a whole number of years and equilibrium a fraction (e.g. 0.05)') from None
	if reference_years < 1 or not 0 < equilibrium < 1:
		raise ValueError('reference_years is at least 1, and equilibrium a fraction between 0 and 1 (e.g. 0.05)')
	if not s < ev <= e:
		raise ValueError(f'event {ev} is not inside the period {s} to {e}: the series has to cover the years before and '
		                 'after it')
	if add_years(ev, -reference_years) < s:
		raise ValueError(f'the period starts {s}: the reference needs the {reference_years} years before the event '
		                 f'({add_years(ev, -reference_years)} to {ev})')
	return step, ev, reference_years, equilibrium


def add_years(d, n):
	"""The date D plus N years (29 February: 28 February in a common year)."""
	y = d.year + n
	return d.replace(year=y, day=min(d.day, calendar.monthrange(y, d.month)[1]))


def years_between(a, b):
	return round((b - a).days / 365.25, 2)


def regular(rows, step):
	"""(dates, values, share of gaps) of ROWS ([{date, value}]) on the regular grid of STEP (the first day of each month,
	the start of each 16 days from 1 January, 1 July of each year), the steps without value filled by linear
	interpolation and, before the first or after the last value, with the nearest one."""
	pts = {}
	for r in rows:
		if r.get('value') is None or (isinstance(r['value'], float) and math.isnan(r['value'])):
			continue
		d = dt.date.fromisoformat(str(r['date'])[:10])
		k = d.year * 12 + d.month - 1 if step == 'monthly' else d.year * 23 + (d.timetuple().tm_yday - 1) // 16 \
			if step == '16-day' else d.year
		pts.setdefault(k, []).append(float(r['value']))
	if not pts:
		return [], np.array([]), 1.0
	keys = np.arange(min(pts), max(pts) + 1)
	vals = np.array([np.mean(pts[k]) if k in pts else np.nan for k in keys])
	gaps = float(np.isnan(vals).mean())
	have = ~np.isnan(vals)
	vals = np.interp(keys, keys[have], vals[have])
	if step == 'monthly':
		dates = [dt.date(int(k // 12), int(k % 12) + 1, 1) for k in keys]
	elif step == '16-day':
		dates = [dt.date(int(k // 23), 1, 1) + dt.timedelta(days=int(k % 23) * 16) for k in keys]
	else:
		dates = [dt.date(int(k), 7, 1) for k in keys]
	return dates, vals, gaps


def _rolling_median(x, window):
	"""The centred running median of WINDOW steps of X, with at least WINDOW // 2 values at its ends (as pandas)."""
	half, least = window // 2, max(1, window // 2)
	out = np.empty(len(x))
	for i in range(len(x)):
		part = x[max(0, i - half):i + half + 1]
		out[i] = np.median(part) if len(part) >= least else np.nan
	return out


def metrics(dates, y, event, per, reference_years=REFERENCE_YEARS, equilibrium=EQUILIBRIUM, relative=True):
	"""The metrics of Marcos et al. (2023) of a regular series (see the module): a dictionary with notes on what could
	not be computed, and '_series' (the deseasonalized series, the trend and the seasonal component) for the chart."""
	out = {'notes': []}
	y = np.asarray(y, dtype=float)
	window = per + 1 if per % 2 == 0 else per + 2  # the smallest odd number greater than the steps per year
	if per > 1:
		if len(y) < 2 * per + 1:
			out['notes'].append('the series is too short for STL (two years at least)')
			return out
		season, tr, _ = stl.stl(y, per, seasonal=window, trend=window, robust=True)
		sa = y - season
	else:  # annual: no seasonality
		season = np.zeros(len(y))
		sa, tr = y.copy(), _rolling_median(y, 3)
		window = 1
	d = np.array(dates)
	pre = sa[(d < event) & (d >= add_years(event, -reference_years))]
	if len(pre) < max(3, per):
		out['notes'].append(f'only {len(pre)} values in the {reference_years} years before the event')
	if len(pre) == 0:
		return out
	med = float(np.median(pre))
	mad = float(np.median(np.abs(pre - med)))
	first = d[(d < event) & (d >= add_years(event, -reference_years))]
	out['reference'] = {'median': med, 'mad': mad, 'interval': [med - mad, med + mad], 'from': str(first.min()),
	                    'to': str(first.max())}
	post = d >= event
	if not post.any():
		out['notes'].append('no values after the event')
		return out
	year1 = sa[post & (d < add_years(event, 1))]
	if not len(year1):
		out['notes'].append('no values in the first year after the event')
		return out
	p95, p05 = float(np.percentile(year1, 95)), float(np.percentile(year1, 5))
	sign = -1 if np.median(year1) < med else 1  # -1: the disturbance lowers the variable
	extreme = p05 if sign < 0 else p95
	out.update(S95=med - p95, S05=med - p05, direction='decrease' if sign < 0 else 'increase', impact=med - extreme,
	           impact_pct=round(100 * (extreme - med) / abs(med), 1) if relative and abs(med) > 1e-9 else None,
	           impact_mad=round((extreme - med) / mad, 2) if mad > 0 else None)
	# tINF: the first local maximum of the distance of the trend from the reference median, after the event
	idx = np.where(post)[0]
	away = (tr[idx] - med) * sign
	h = max(1, per // 4)
	tinf = None
	for i in range(len(away)):
		lo, hi = max(0, i - h), min(len(away), i + h + 1)
		if hi - i > h and away[i] >= away[lo:hi].max():  # the maximum around it, with values after it
			tinf = idx[i]
			break
	out['tINF'] = str(d[tinf]) if tinf is not None else None
	out['DIT_years'] = years_between(event, d[tinf]) if tinf is not None else None
	if tinf is None:
		out['notes'].append('no inflection of the trend: the series still moves away from the reference, or is short')
		out['_series'] = {'dates': dates, 'deseasonalized': sa, 'trend': tr, 'seasonal': season}
		return out
	# tREF: the trend and the running median of a year inside the reference interval
	lo_i, hi_i = med - mad, med + mad
	running = _rolling_median(sa, window)
	tref = next((i for i in range(tinf, len(sa)) if lo_i <= tr[i] <= hi_i and lo_i <= running[i] <= hi_i), None)
	out['tREF'] = str(d[tref]) if tref is not None else None
	out['RRT_years'] = years_between(event, d[tref]) if tref is not None else None
	if tref is None:
		out['notes'].append('not back in the reference interval yet')
	# tEQ: the medians of consecutive windows of a year from tINF
	since = sa[tinf:]
	medians = [(d[tinf + k], float(np.median(since[k:k + per]))) for k in range(0, len(since) - per + 1, per)]
	rates = []
	for j in range(1, len(medians)):
		prev, cur = medians[j - 1][1], medians[j][1]
		rates.append(abs(cur - prev) / max(abs(prev), 1e-9) if relative else
		             (abs(cur - prev) / mad if mad > 0 else float('inf')))
	limit = equilibrium if relative else 1
	teq = next((medians[j + 1][0] for j in range(len(rates) - 1) if rates[j] < limit and rates[j + 1] < limit), None)
	out['tEQ'] = str(teq) if teq is not None else None
	out['RET_years'] = years_between(event, teq) if teq is not None else None
	out['yearly_medians_from_tINF'] = [[str(a), b] for a, b in medians]
	if teq is None:
		out['notes'].append('no equilibrium: fewer than two stable yearly windows in a row after tINF')
	# the share of the initial loss recovered in the last year with data
	last = sa[d > add_years(d[-1], -1)]
	if abs(extreme - med) > 0 and len(last):
		out['recovered_pct'] = round(100 * (1 - (float(np.median(last)) - med) / (extreme - med)), 1)
		out['last_year'] = str(d[-1])
	out['_series'] = {'dates': dates, 'deseasonalized': sa, 'trend': tr, 'seasonal': season}
	return out


def anomalies(dates, y, event, step):
	"""The standardized anomalies (z) of the steps after the event against those of the same part of the year (month,
	16 days; the year, in an annual series) of every year before it."""
	d = np.array(dates)
	y = np.asarray(y, dtype=float)
	if step == 'monthly':
		key = np.array([x.month for x in dates])
	elif step == '16-day':
		key = np.array([(x.timetuple().tm_yday - 1) // 16 for x in dates])
	else:
		key = np.zeros(len(dates), dtype=int)
	z = np.full(len(y), np.nan)
	before = d < event
	least = 3 if step == 'annual' else 2  # as the script: more than 2 years before an annual series
	for k in set(key.tolist()):
		ref = y[before & (key == k)]
		if len(ref) >= least and np.std(ref, ddof=1) > 0:
			z[key == k] = (y[key == k] - ref.mean()) / np.std(ref, ddof=1)
	post = ~before
	year1 = post & (d < add_years(event, 1))
	out_z = post & (np.abs(z) > 2)
	return {'z_min_first_year': round(float(np.nanmin(z[year1])), 2) if np.isfinite(z[year1]).any() else None,
	        'z_max_first_year': round(float(np.nanmax(z[year1])), 2) if np.isfinite(z[year1]).any() else None,
	        'steps_abs_z_over_2_after': int(out_z.sum()),
	        'last_abs_z_over_2': str(d[out_z].max()) if out_z.any() else None,
	        'reference_years': sorted({x.year for x in d[before]})}


def _trend(years, values):
	"""The Mann-Kendall test, with its continuity correction (z = (S - sign S) / sqrt(var S), as the script; few yearly
	values are the rule here), and the Sen slope (monitoreo.trends.sen) of yearly VALUES: {n, tau, p_value,
	sen_per_year, significant}, or None with fewer than 4 years."""
	if len(values) < 4:
		return None
	pts = sorted(zip(years, values))
	n = len(pts)
	s = sum((pts[j][1] > pts[i][1]) - (pts[j][1] < pts[i][1]) for i in range(n) for j in range(i + 1, n))
	var = n * (n - 1) * (2 * n + 5) / 18
	z = 0.0 if s == 0 else (s - math.copysign(1, s)) / math.sqrt(var)
	p = math.erfc(abs(z) / math.sqrt(2))
	tau = s / (n * (n - 1) / 2)
	slope, _ = trends.sen(years, values)
	return {'n': n, 'tau': round(tau, 3), 'p_value': round(p, 4), 'sen_per_year': slope, 'significant': p < 0.05}


def yearly_trends(dates, y, event):
	"""The trends of the yearly means before the year of the event and after it."""
	by = {}
	for x, v in zip(dates, y):
		by.setdefault(x.year, []).append(v)
	years = sorted(by)
	means = [float(np.mean(by[k])) for k in years]
	pre = [(k, m) for k, m in zip(years, means) if k < event.year]
	post = [(k, m) for k, m in zip(years, means) if k > event.year]
	return {'before': _trend([k for k, _ in pre], [m for _, m in pre]),
	        'after': _trend([k for k, _ in post], [m for _, m in post]),
	        'years_before': [pre[0][0], pre[-1][0]] if pre else None,
	        'years_after': [post[0][0], post[-1][0]] if post else None}


def seasonal_amplitude(dates, season, event):
	"""The median of the yearly amplitude (maximum - minimum) of the seasonal component in the whole years before and
	after the year of the event: {'before', 'after'} (None without them)."""
	by = {}
	for x, s in zip(dates, season):
		by.setdefault(x.year, []).append(s)
	amp = {k: max(v) - min(v) for k, v in by.items() if len(v) > 1}
	pre = [a for k, a in amp.items() if k < event.year]
	post = [a for k, a in amp.items() if k > event.year]
	return {'before': float(np.median(pre)) if pre else None, 'after': float(np.median(post)) if post else None}


def clean(m):
	"""The metrics M without their series, with the floats rounded to 4 decimals."""
	return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items() if not k.startswith('_')}


def of_series(rows, step, event, reference_years=REFERENCE_YEARS, equilibrium=EQUILIBRIUM, relative=True):
	"""Every metric of the series ROWS: those of Marcos et al. (2023), the anomalies, the trends and the seasonal
	amplitude, and 'gaps' (the share of steps filled), with '_series' for the chart."""
	dates, y, gaps = regular(rows, step)
	if not dates:
		return {'notes': ['no values'], 'gaps': 1.0}
	m = metrics(dates, y, event, STEPS_PER_YEAR[step], reference_years, equilibrium, relative)
	m['gaps'] = round(gaps, 3)
	m['anomalies'] = anomalies(dates, y, event, step)
	m['trends'] = yearly_trends(dates, y, event)
	if '_series' in m and STEPS_PER_YEAR[step] > 1:
		m['seasonal_amplitude'] = seasonal_amplitude(dates, m['_series']['seasonal'], event)
	m.setdefault('_series', {'dates': dates, 'deseasonalized': y, 'trend': None, 'seasonal': None})
	m['_series']['values'] = y
	return m


def common(rows_a, rows_b, step):
	"""The rows of B (its regular grid, filled) on the steps that A has too: the control on the dates of the affected
	area, as the script computed its metrics."""
	da, _, _ = regular(rows_a, step)
	db, yb, _ = regular(rows_b, step)
	a = set(da)
	return [{'date': str(x), 'value': float(v)} for x, v in zip(db, yb) if x in a]


def difference(rows_a, rows_b, step):
	"""The rows of the difference A - B on the steps that both have (dates of the regular grid)."""
	da, ya, _ = regular(rows_a, step)
	db, yb, _ = regular(rows_b, step)
	b = dict(zip(db, yb))
	return [{'date': str(x), 'value': float(v - b[x])} for x, v in zip(da, ya) if x in b]
