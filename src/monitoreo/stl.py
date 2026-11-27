"""STL: the seasonal-trend decomposition by loess of Cleveland et al. (1990), in numpy, for the recovery metrics
(monitoreo.recovery), without a dependency on statsmodels: a series y of a regular step = seasonal + trend + residual.

It ports the Fortran of the authors (stl.f, netlib), as statsmodels.tsa.seasonal.STL does, with its defaults: loess of
degree 1 in the three smoothers, the low-pass filter of the smallest odd length greater than the period, every point
computed (jumps of 1), and, robust, 2 inner and 15 outer iterations (without robustness, 5 inner and none outer).
tests/test_recovery.py compares it with statsmodels when it is installed.

Reference: Cleveland, R. B., Cleveland, W. S., McRae, J. E., & Terpenning, I. (1990). STL: A seasonal-trend
decomposition procedure based on loess. Journal of Official Statistics, 6(1), 3-73.
"""

import numpy as np


def _est(y, n, length, ideg, xs, nleft, nright, userw, rw):
	"""The loess value at XS (1-based) of Y (0-based array of N values) from its points NLEFT..NRIGHT (1-based), with
	a window of LENGTH points, of degree IDEG (0 or 1), and the robustness weights RW if USERW: (value, ok)."""
	rng = n - 1.0
	h = max(xs - nleft, nright - xs)
	if length > n:
		h += (length - n) // 2
	h9, h1 = 0.999 * h, 0.001 * h
	j = np.arange(nleft, nright + 1, dtype=float)
	r = np.abs(j - xs)
	w = np.zeros(len(j))
	near = r <= h9
	w[near] = np.where(r[near] <= h1, 1.0, (1.0 - (r[near] / h) ** 3) ** 3) if h > 0 else 1.0
	if userw:
		w = w * rw[nleft - 1:nright]
	a = w.sum()
	if a <= 0:
		return 0.0, False
	w = w / a
	if h > 0 and ideg > 0:
		a = (w * j).sum()
		b = xs - a
		c = (w * (j - a) ** 2).sum()
		if np.sqrt(c) > 0.001 * rng:
			w = w * (b / c * (j - a) + 1.0)
	return float((w * y[nleft - 1:nright]).sum()), True


def _ess(y, length, ideg, userw, rw):
	"""The loess smoothing of every point of Y (window of LENGTH points, degree IDEG, robustness weights RW if USERW),
	as ess of stl.f with jumps of 1, every point at once: a value that cannot be computed keeps that of Y."""
	y = np.asarray(y, dtype=float)
	n = len(y)
	if n < 2:
		return y.copy()
	xs = np.arange(1, n + 1, dtype=float)
	if length >= n:
		nleft = np.ones(n, dtype=int)
		width = n
	else:  # the window of LENGTH points around each point, kept inside the series
		nsh = (length + 1) // 2
		nleft = np.clip(np.arange(1, n + 1) - nsh + 1, 1, n - length + 1)
		width = length
	j = nleft[:, None] + np.arange(width)[None, :]  # the points of each window (1-based)
	h = np.maximum(xs - nleft, nleft + width - 1 - xs)
	if length > n:
		h = h + (length - n) // 2
	r = np.abs(j - xs[:, None])
	hh = h[:, None]
	with np.errstate(divide='ignore', invalid='ignore'):
		w = np.where(r <= 0.001 * hh, 1.0, np.where(r <= 0.999 * hh, (1.0 - (r / hh) ** 3) ** 3, 0.0))
	if userw:
		w = w * np.asarray(rw)[j - 1]
	a = w.sum(axis=1)
	ok = a > 0
	w[ok] = w[ok] / a[ok, None]
	if ideg > 0:
		mean = (w * j).sum(axis=1)
		c = (w * (j - mean[:, None]) ** 2).sum(axis=1)
		fit = ok & (h > 0) & (np.sqrt(c) > 0.001 * (n - 1.0))
		b = np.zeros(n)
		b[fit] = (xs[fit] - mean[fit]) / c[fit]
		w[fit] = w[fit] * (b[fit, None] * (j[fit] - mean[fit, None]) + 1.0)
	ys = (w * y[j - 1]).sum(axis=1)
	return np.where(ok, ys, y)


def _ma(x, length):
	"""The moving average of LENGTH points of X (len(x) - length + 1 values)."""
	c = np.cumsum(np.concatenate([[0.0], x]))
	return (c[length:] - c[:-length]) / length


def _ss(y, period, ns, isdeg, userw, rw):
	"""The smoothing of the cycle-subseries of Y (the values of each position of the period), each extended by one
	value at each end: an array of len(y) + 2 * period values (stlss of stl.f)."""
	n = len(y)
	season = np.empty(n + 2 * period)
	for j in range(period):
		sub = y[j::period]
		k = len(sub)
		w = rw[j::period] if userw else None
		smooth = np.empty(k + 2)
		smooth[1:k + 1] = _ess(sub, ns, isdeg, userw, w)
		v, ok = _est(sub, k, ns, isdeg, 0.0, 1, min(ns, k), userw, w)
		smooth[0] = v if ok else smooth[1]
		v, ok = _est(sub, k, ns, isdeg, float(k + 1), max(1, k - ns + 1), k, userw, w)
		smooth[k + 1] = v if ok else smooth[k]
		season[j::period] = smooth
	return season


def _robustness(y, fit):
	"""The bisquare robustness weights of the residuals of FIT (stlrwt of stl.f)."""
	r = np.abs(y - fit)
	n = len(r)
	s = np.sort(r)
	m1 = n // 2 + 1
	m2 = n - m1 + 1
	cmad = 3.0 * (s[m1 - 1] + s[m2 - 1])  # 6 times the median
	c9, c1 = 0.999 * cmad, 0.001 * cmad
	with np.errstate(divide='ignore', invalid='ignore'):  # a flat series: every residual 0, every weight 1
		return np.where(r <= c1, 1.0, np.where(r <= c9, (1.0 - (r / cmad) ** 2) ** 2, 0.0))


def stl(y, period, seasonal=7, trend=None, low_pass=None, robust=False, inner=None, outer=None):
	"""STL of the series Y (no missing values) with PERIOD values per cycle: (seasonal, trend, residual), arrays as Y.
	SEASONAL, TREND and LOW_PASS: the odd lengths of the loess windows of the cycle-subseries, the trend and the
	low-pass filter (default TREND: the smallest odd integer >= 1.5 * PERIOD / (1 - 1.5 / SEASONAL), as statsmodels;
	LOW_PASS: the smallest odd integer > PERIOD). ROBUST: robustness weights against outliers."""
	y = np.asarray(y, dtype=float)
	n = len(y)
	if period < 2 or n < 2 * period:
		raise ValueError(f'STL needs a period of at least 2 and two cycles of values: {n} values, period {period}')
	if not np.all(np.isfinite(y)):
		raise ValueError('STL needs a series without missing values: fill its gaps first')

	def odd(v):
		v = int(np.ceil(v))
		return v + 1 if v % 2 == 0 else v
	seasonal = odd(max(3, seasonal))
	trend = odd(trend if trend else 1.5 * period / (1 - 1.5 / seasonal))
	low_pass = odd(low_pass if low_pass else period + 1)
	inner = inner if inner is not None else (2 if robust else 5)
	outer = outer if outer is not None else (15 if robust else 0)
	rw = np.ones(n)
	season = np.zeros(n)
	tr = np.zeros(n)
	userw = False
	for k in range(outer + 1):
		for _ in range(inner):
			c = _ss(y - tr, period, seasonal, 1, userw, rw)
			low = _ma(_ma(_ma(c, period), period), 3)
			low = _ess(low, low_pass, 1, False, None)
			season = c[period:period + n] - low
			tr = _ess(y - season, trend, 1, userw, rw)
		if k == outer:
			break
		rw = _robustness(y, season + tr)
		userw = True
	return season, tr, y - season - tr
