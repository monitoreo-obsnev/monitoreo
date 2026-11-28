"""Standardized anomalies (z) of a time series against a reference period, and their episodes, without Earth Engine.

The z of each step (a day, a month, 16 days or a year) is its value minus the mean of the same part of the year (that
month, those 16 days; the year, in an annual series; for a day, the days within DAY_WINDOW days of the same date, as
one day of each year is too few and too often cloudy: its standard deviation is then that of those days, within and
between years, and its reference_n their number) in the years of the REFERENCE period, divided by their standard deviation
(sample, n - 1): how many standard deviations of the usual variation between years the step is above (z > 0) or below
(z < 0) the usual value of that time of the year. A part of the year needs at least MIN_YEARS values in the reference;
with fewer, or with no variation between them, its z has no value.

An episode is a run of consecutive steps with z at or beyond the THRESHOLD of the same sign (at most -THRESHOLD, a
negative episode, e.g. a drought or a defoliation; at least THRESHOLD, a positive one): its first and last step, its
number of steps, its peak (the most extreme z), its intensity (the sum of its z) and its mean z. A step without a z
(no image, too few reference years) ends an episode, and so does a gap between two steps (the months outside a
season: GAP_DAYS).

The parts of the year are those of the profiles (timeseries._part_of): with a season, the 16-day periods start on its
first day each year. A season across the new year makes the first and last years of a period partial (e.g. reference
2018-2020 with a season from November to March: January-March 2018, two whole seasons and November-December 2020):
their values count as those of their years; give a reference that starts and ends with the season.

References: the standardized anomaly (z-score) of a variable against its reference years, as in the anomalies of
recovery_metrics (Marcos et al. 2023, https://doi.org/10.1016/j.rse.2022.113441).
"""

import datetime as dt
import math

import numpy as np

STEPS = ('daily', 'monthly', '16-day', 'annual')
DAY_WINDOW = 7  # a daily step: its reference, the days within these days of the same date (15 days a year)
THRESHOLD = 1.5  # |z| from which a step is anomalous (as the default of the episodes)
MIN_YEARS = 3  # the values of the reference years that a part of the year needs for its z


def _date(x):
	if isinstance(x, dt.date):
		return x if not isinstance(x, dt.datetime) else x.date()
	return dt.date.fromisoformat(str(x)[:10])


def check(step, start, end, reference=None, threshold=THRESHOLD, min_years=MIN_YEARS):
	"""(step, reference (first, last day as dates), threshold, min_years) after checking them without Earth Engine;
	REFERENCE None is the whole period START to END. ValueError otherwise."""
	if step not in STEPS:
		raise ValueError(f"step of the anomalies: {', '.join(STEPS)}, not {step!r}")
	try:
		first, last = _date(start), _date(end)
	except (TypeError, ValueError):
		raise ValueError('give the period: start and end, YYYY-MM-DD') from None
	if reference is None:
		ref = (first, last)
	else:
		if not isinstance(reference, (list, tuple)) or len(reference) != 2:
			raise ValueError('reference is the reference period, [first day, last day] (YYYY-MM-DD)')
		try:
			ref = (_date(reference[0]), _date(reference[1]))
		except (TypeError, ValueError):
			raise ValueError('reference is the reference period, [first day, last day] (YYYY-MM-DD)') from None
		if ref[0] > ref[1]:
			raise ValueError('reference: its first day is after its last day')
		if ref[0] < first or ref[1] > last:
			raise ValueError(f'the reference period {ref[0]} / {ref[1]} must be inside the period {first} / {last}: '
			                 'the series must cover it')
	try:
		threshold = float(threshold)
	except (TypeError, ValueError):
		threshold = math.nan
	if not threshold > 0 or math.isinf(threshold):
		raise ValueError(f'threshold is the |z| of an anomalous step, a number above 0, not {threshold!r}')
	try:
		min_years = int(min_years)
	except (TypeError, ValueError):
		min_years = 0
	if min_years < 2:
		raise ValueError('min_years: at least 2 reference years (a standard deviation needs two values)')
	if ref[1].year - ref[0].year + 1 < min_years:
		raise ValueError(f'the reference period {ref[0]} / {ref[1]} has fewer than {min_years} years (min_years): '
		                 'give a longer one')
	return step, ref, threshold, min_years


def part(date, step, wins=(), season=None):
	"""The part of the year of DATE, the first day of a step of STEP: as the profiles by day of the year (see
	timeseries._part_of: the month, or the part of a month split by a SEASON that starts and ends in it; the 16-day
	period from the start of its window of WINS, composite.windows, so that leap years and seasons keep their periods),
	or 0 in an annual series."""
	if step == 'annual':
		return 0
	from . import timeseries
	return timeseries._part_of(date, step, list(wins), season)


GAP_DAYS = {'daily': 3, 'monthly': 45, '16-day': 24, 'annual': 400}  # daily: up to 2 cloudy days inside an episode  # more days between two steps: not consecutive (an off-season)


def of_series(rows, step, reference, threshold=THRESHOLD, min_years=MIN_YEARS, wins=(), season=None):
	"""The anomalies of the time series ROWS of one feature ([{'date', 'value', ...}], sorted or not), whose parts of
	the year come from the windows WINS of its period and its SEASON (see part): {'rows':
	[{date, value, part, reference_mean, reference_std, reference_n, z}], 'episodes': [{sign, start, end, steps,
	peak, intensity, mean_z}], 'summary': {steps, steps_with_z, negative_steps, positive_steps, episodes,
	negative_episodes, positive_episodes, longest_steps, most_intense}}."""
	pts = sorted(((_date(r['date']), r.get('value')) for r in rows), key=lambda p: p[0])
	first, last = reference
	ref = {}
	for d, v in pts:
		if first <= d <= last and v is not None and math.isfinite(float(v)):
			ref.setdefault(part(d, step, wins, season), []).append(float(v))
	if step == 'daily':  # the days of the reference within DAY_WINDOW days of the same date (see _daily_reference)
		ref = _daily_reference(pts, first, last, {part(d, step, wins, season) for d, _ in pts})
	stats = {}
	for k, vals in ref.items():
		years = len({y for y, _ in vals}) if step == 'daily' else len(vals)
		vals = [v for _, v in vals] if step == 'daily' else vals
		if years >= min_years and len(vals) >= 2:
			a = np.array(vals)
			sd = float(np.std(a, ddof=1))
			stats[k] = (float(a.mean()), sd, len(vals))
	out = []
	for d, v in pts:
		k = part(d, step, wins, season)
		mean, sd, n = stats.get(k, (None, None, len(ref.get(k, []))))
		z = None
		if v is not None and math.isfinite(float(v)) and mean is not None and sd and sd > 0:
			z = (float(v) - mean) / sd
		out.append({'date': d.isoformat(), 'value': v, 'part': k, 'reference_mean': mean, 'reference_std': sd,
		            'reference_n': n, 'z': z})
	episodes = _episodes(out, threshold, step)
	neg = [e for e in episodes if e['sign'] == 'negative']
	pos = [e for e in episodes if e['sign'] == 'positive']
	summary = {'steps': len(out), 'steps_with_z': sum(r['z'] is not None for r in out),
	           'negative_steps': sum(r['z'] is not None and r['z'] <= -threshold for r in out),
	           'positive_steps': sum(r['z'] is not None and r['z'] >= threshold for r in out),
	           'episodes': len(episodes), 'negative_episodes': len(neg), 'positive_episodes': len(pos),
	           'longest_steps': max((e['steps'] for e in episodes), default=0),
	           'most_intense': max(episodes, key=lambda e: abs(e['intensity']))['start'] if episodes else None}
	return {'rows': out, 'episodes': episodes, 'summary': summary}


def _daily_reference(pts, first, last, parts):
	"""{'MM-DD': [(year, value)]}: for each calendar day of PARTS, the values of the points PTS [(date, value)] of the
	reference FIRST to LAST within DAY_WINDOW days of that date (across the new year), with their year."""
	vals = [(d, float(v)) for d, v in pts if first <= d <= last and v is not None and math.isfinite(float(v))]
	out = {}
	for k in parts:
		m, dd = int(k[:2]), int(k[3:])
		out[k] = []
		for d, v in vals:
			best = None
			for y in (d.year - 1, d.year, d.year + 1):  # the same date in the year before, that one and the next
				try:
					c = dt.date(y, m, dd)
				except ValueError:  # 29 February of a common year: the 28th
					c = dt.date(y, m, 28)
				gap = abs((d - c).days)
				best = gap if best is None else min(best, gap)
			if best <= DAY_WINDOW:
				out[k].append((d.year, v))
	return out


def _episodes(rows, threshold, step='monthly'):
	"""The runs of consecutive ROWS with z at or beyond THRESHOLD of the same sign (see the docstring): two steps more
	than GAP_DAYS apart (the months outside a season) are not consecutive."""
	out, run, sign = [], [], None

	def close():
		if run:
			zs = [r['z'] for r in run]
			peak = min(zs) if sign == 'negative' else max(zs)
			out.append({'sign': sign, 'start': run[0]['date'], 'end': run[-1]['date'], 'steps': len(run),
			            'peak': round(peak, 3), 'intensity': round(sum(zs), 3), 'mean_z': round(sum(zs) / len(zs), 3)})

	last = None
	for r in rows:
		if step == 'daily' and r['z'] is None:  # a cloudy day does not end an episode: a gap of GAP_DAYS does
			continue
		z = r['z']
		s = None if z is None else 'negative' if z <= -threshold else 'positive' if z >= threshold else None
		day = _date(r['date'])
		gap = last is not None and (day - last).days > GAP_DAYS.get(step, 45)
		last = day
		if s != sign or s is None or gap:
			close()
			run = []
		sign = s
		if s is not None:
			run.append(r)
	close()
	return out
