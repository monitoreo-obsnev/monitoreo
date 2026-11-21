"""The trend tests corrected for the serial correlation of the yearly values (monitoreo.trends.TESTS): the variance
correction of Hamed & Rao (1998) and the trend-free pre-whitening of Yue et al. (2002), without Earth Engine. The
expected values are those of pyMannKendall 1.4.3 (hamed_rao_modification_test, trend_free_pre_whitening_modification_test)
on series without missing years: n/n* (its var_s / that of original_test), the lag-1 autocorrelation r1 and the S of
the blended series; MonitorEO computes Z without the continuity and ties corrections of pyMannKendall, as its
Mann-Kendall test. The same in the port of the Earth Engine app (gee/core.js, in Node), in the references, the README
and every tool that takes the test."""

import inspect
import json
import math
import os
import shutil
import subprocess

import pytest

from monitoreo import cli, references, readme, report, services, trends

GEE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gee')
YEARS20 = list(range(2001, 2021))
# autocorrelated with a trend; autocorrelated without a trend; with ties
A = [10.0, 10.6, 10.9, 10.5, 10.2, 10.8, 11.6, 12.1, 11.8, 11.5, 12.3, 13.0, 13.4, 12.9, 12.6, 13.3, 14.1, 14.5, 14.0,
     13.8]
B = [4.45, 5.8, 6.18, 7.03, 7.0, 6.51, 5.11, 4.84, 4.12, 3.47, 2.59, 2.91, 3.14, 3.89, 5.32, 5.63, 6.55, 7.22, 6.77,
     6.53]
C = [3.1, 2.8, 3.4, 3.4, 3.0, 3.6, 3.4, 3.9, 3.7, 3.7, 4.1, 3.9]


def _s(values):
	n = len(values)
	return sum((values[j] > values[i]) - (values[j] < values[i]) for i in range(n) for j in range(i + 1, n))


def test_hamed_rao_as_pymannkendall():
	"""n/n* of the series B is that of pyMannKendall (2186.2224 / 950); z is that of Mann-Kendall divided by
	sqrt(n/n*), tau that of Mann-Kendall."""
	t = trends.trend_test(YEARS20, B, 'hamed-rao')
	mk = trends.trend_test(YEARS20, B, 'mk')
	assert t['n_ratio'] == pytest.approx(2186.222431077694 / 950, rel=1e-12)
	assert t['tau'] == mk['tau'] and t['n'] == 20 and t['r1'] is None
	assert t['z'] == pytest.approx(mk['z'] / math.sqrt(t['n_ratio']))
	assert t['p_value'] == pytest.approx(math.erfc(abs(t['z']) / math.sqrt(2)))


def test_hamed_rao_without_a_usable_estimate():
	"""An estimate n/n* <= 0 (the series A: -0.295 in pyMannKendall, which then gives no p-value) is not used: the
	test is that of Mann-Kendall. With ties broken only by the rounding of the slope (the series C, whose values
	without their trend are tied in exact arithmetic), no lag is significant: n/n* = 1."""
	for values, years in ((A, YEARS20), (C, YEARS20[:12])):
		t, mk = trends.trend_test(years, values, 'hamed-rao'), trends.trend_test(years, values, 'mk')
		assert t['n_ratio'] == 1 and t['z'] == mk['z'] and t['p_value'] == mk['p_value']


def test_tfpw_as_pymannkendall():
	"""r1 and the S of the blended series (n - 1 values) are those of pyMannKendall; tau is that of the blended
	series, n stays the years with data."""
	for values, r1, s in ((A, 0.3056477023709905, 133), (B, 0.852839920464742, 19), (C, -0.590425531914894, 41)):
		years = YEARS20[:len(values)]
		slope, _ = trends.sen(years, values)
		by, bv, got = trends.tfpw_series(years, values, slope)
		assert got == pytest.approx(r1, rel=1e-9) and len(bv) == len(values) - 1 and by == years[1:]
		assert _s(bv) == s
		t = trends.trend_test(years, values, 'tfpw')
		m = len(bv)
		assert t['n'] == len(values) and t['r1'] == got and t['tau'] == pytest.approx(s / (m * (m - 1) / 2))
		assert t['z'] == pytest.approx(t['tau'] * math.sqrt(9 * m * (m - 1) / (2 * (2 * m + 5))))


def test_missing_years_are_years_of_the_calendar():
	"""A year without data does not join the years before and after it: the lag-1 pairs and the blended values of
	TFPW skip it, so each gap costs a blended value more."""
	values = list(A)
	values[4] = values[11] = None
	slope, _ = trends.sen(YEARS20, values)
	by, bv, r1 = trends.tfpw_series(YEARS20, values, slope)
	assert 2005 not in by and 2006 not in by and 2012 not in by and 2013 not in by and len(bv) == 18 - 3
	series = {y: v for y, v in zip(YEARS20, values) if v is not None}
	assert trends.lag_r(series, 1) == pytest.approx(
		sum((series[t] - sum(series.values()) / 18) * (series[t + 1] - sum(series.values()) / 18)
		    for t in series if t + 1 in series) / sum((v - sum(series.values()) / 18) ** 2 for v in series.values()))
	t = trends.trend_test(YEARS20, values, 'hamed-rao')
	assert t['n'] == 18 and t['n_ratio'] > 0


def test_few_years_and_constant_values():
	"""A correction needs 3 years with data; constant values have no autocorrelation (r1 = 0, n/n* = 1)."""
	for test in ('hamed-rao', 'tfpw'):
		t = trends.trend_test([2001, 2002], [1.0, 2.0], test)
		assert t['n'] == 2 and t['tau'] is t['z'] is t['p_value'] is None
	# without the test, the table keeps Sen's line, as the map: 2 years, or years that never follow one another (TFPW)
	for years, values, test in (([2001, 2002], [1.0, 2.0], 'hamed-rao'), ([2000, 2002, 2004], [1.0, 2.0, 4.0], 'tfpw')):
		(row,) = trends.trend_rows([{'region': 'R', 'part': 0, 'year': y, 'value': v} for y, v in zip(years, values)],
		                           'annual', test=test)
		assert row['p_value'] is None and not row['significant'] and row['slope'] is not None
	assert trends.trend_test(YEARS20[:5], [1.0] * 5, 'tfpw')['r1'] == 0
	assert trends.trend_test(YEARS20[:5], [1.0] * 5, 'hamed-rao')['n_ratio'] == 1


def test_trend_rows_with_a_test():
	"""trend_rows takes the test, and its rows have n_ratio and r1 (None for the other tests); an unknown test is an
	error that lists them."""
	yearly = [{'region': 'R', 'part': 0, 'year': y, 'value': v} for y, v in zip(YEARS20, B)]
	(mk,) = trends.trend_rows(yearly, 'annual')
	(hr,) = trends.trend_rows(yearly, 'annual', test='hamed-rao')
	(tf,) = trends.trend_rows(yearly, 'annual', test='TFPW')
	assert mk['n_ratio'] is mk['r1'] is None and hr['r1'] is None and tf['n_ratio'] is None
	assert hr['n_ratio'] > 1 and hr['p_value'] > mk['p_value'] and tf['r1'] == pytest.approx(0.852839920464742)
	assert mk['slope'] == hr['slope'] == tf['slope'] and mk['intercept'] == tf['intercept']
	with pytest.raises(ValueError, match='mk, hamed-rao, tfpw'):
		trends.trend_rows(yearly, 'annual', test='yue')
	with pytest.raises(ValueError, match='unknown trend test'):  # before computing anything in Earth Engine
		services.trend_table({'wdpa_id': 1}, 'NDVI', 'Modis', '2001-01-01', '2020-12-31', test='hamed_rao')
	assert set(services.TREND_COLUMNS) <= set(mk) | {'region', 'key', 'label'}


def test_every_tool_takes_the_test():
	"""The services of the trends take test ('mk' by default), as the command line (the same choices) and the MCP
	server; the README describes the new columns and the reports say the test."""
	for f in (services.trend_table, services.trend_map, services.download_trend, services.area_by_class):
		assert inspect.signature(f).parameters['test'].default == 'mk'
	assert cli.TREND_TESTS == trends.TESTS
	from monitoreo import mcp_server
	for name in ('trend_table', 'trend_map', 'download_trend', 'area_by_class'):
		assert inspect.signature(getattr(mcp_server, name).fn if hasattr(getattr(mcp_server, name), 'fn')
		                         else getattr(mcp_server, name)).parameters['test'].default == 'mk'
	assert {'n_ratio', 'r1', 'test'} <= set(readme.COLUMNS)
	facts = dict(report.item_facts('trend_table', {'test': 'hamed-rao', 'region': {'wdpa_id': 1}}))
	assert facts['Trend test'].startswith('Mann-Kendall modified by Hamed and Rao (1998)')
	facts = dict(report.item_facts('area_by_class', {'trend': True, 'test': 'tfpw', 'region': {'wdpa_id': 1}}))
	assert 'TFPW, p < 0.05' in facts['Classes'] and 'pre-whitening' in facts['Trend test']
	assert trends.test_note('mk') == '' and trends.test_note('tfpw') == ', TFPW test'


def test_references_of_the_test():
	"""Each test cites its paper, besides Mann, Kendall and Sen; the Mann-Kendall test does not cite them."""
	args = {'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'sensor': 'Modis', 'start': '2001-01-01',
	        'end': '2020-12-31'}
	ids = lambda tool, **more: {r['id'] for r in references.cite(tool, dict(args, **more))['references']}  # noqa: E731
	assert {'mann1945', 'sen1968'} <= ids('trend_table') and not {'hamed1998', 'yue2002'} & ids('trend_table')
	assert 'hamed1998' in ids('trend_map', test='hamed-rao') and 'yue2002' not in ids('trend_map', test='hamed-rao')
	assert {'yue2002', 'mann1945'} <= ids('download_trend', test='tfpw')
	assert 'yue2002' in ids('area_by_class', trend=True, test='tfpw') and 'yue2002' not in ids('area_by_class',
	                                                                                           test='tfpw')


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_earth_engine_app_computes_the_same():
	"""gee/core.js (in Node, with an ee that computes nothing) gives the same rows as monitoreo.trends.trend_rows with
	each test, also with missing years and few years."""
	gaps = list(A)
	gaps[4] = gaps[11] = None
	yearly = [{'region': name, 'part': 0, 'year': y, 'value': v}
	          for name, values in (('A', A), ('B', B), ('C', C), ('gaps', gaps), ('few', [1.0, 3.0]))
	          for y, v in zip(YEARS20, values)]
	script = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
function nothing() { return new Proxy(function () {}, {get: function () { return nothing(); }, apply: nothing}); }
global.ee = nothing();
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[process.argv.length - 1], f), 'utf8'), {filename: f});
});
var mo = MonitorEO, out = {tests: mo.TREND_TESTS};
input.tests.forEach(function (t) { out[t] = mo.trendRows(input.yearly, 'annual', 2001, 'en', undefined, 0.05, t); });
try { mo.checkTest('yue'); } catch (e) { out.error = e.message; }
process.stdout.write(JSON.stringify(out));
"""
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps({'yearly': yearly, 'tests': list(trends.TESTS)}),
	                     capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	assert out['tests'] == list(trends.TESTS) and 'mk, hamed-rao, tfpw' in out['error']
	for test in trends.TESTS:
		expected = trends.trend_rows(yearly, 'annual', 2001, test=test)
		assert len(out[test]) == len(expected)
		for got, want in zip(out[test], expected):
			for k in ('region', 'n', 'tau', 'z', 'p_value', 'significant', 'slope', 'intercept', 'n_ratio', 'r1'):
				if isinstance(want[k], float):
					assert got[k] == pytest.approx(want[k], rel=1e-9, abs=1e-12), (test, want['region'], k)
				else:
					assert got[k] == want[k], (test, want['region'], k)
