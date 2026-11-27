"""The recovery metrics after a disturbance in the Earth Engine app, without Earth Engine: in Node, the STL of gee/core.js
(mo.stl) gives the seasonal component and the trend of monitoreo.stl; mo.ofSeries, mo.recoveryDifference and
mo.recoveryOf give the metrics of monitoreo.recovery (of_series, difference) and the rows of
services._recovery_row on monthly, 16-day and annual series with a drop and its recovery, with and without a control;
mo.recoveryCheck refuses what recovery.check refuses, with its words; and the panel (gee/ui.js, with the ui and ee of
tests/test_themes.py) has the section of the recovery in English and Spanish, its control area and its results."""

import datetime as dt
import json
import math
import os
import shutil
import subprocess

import numpy as np
import pytest

from monitoreo import catalog, recovery, services, stl

GEE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gee')
node = pytest.mark.skipif(not shutil.which('node'), reason='no Node')

CORE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
function nothing() { return new Proxy(function () {}, {get: function () { return nothing(); }, apply: nothing}); }
global.ee = nothing();
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[process.argv.length - 1], f), 'utf8'), {filename: f});
});
var mo = MonitorEO;
function nan(xs) { return xs && xs.map(function (v) { return typeof v === 'number' && isNaN(v) ? 'NaN' : v; }); }
function series(m) {
	var s = m._series || {}, out = {};
	['dates', 'values', 'deseasonalized', 'trend', 'seasonal'].forEach(function (k) { out[k] = nan(s[k] || null); });
	return out;
}
var out = {stl: input.stl.map(function (c) {
	var r = mo.stl(c.y, c.period, c.seasonal, c.trend, c.low_pass, c.robust);
	return [r.seasonal, r.trend, r.residual];
}), series: input.series.map(function (c) {
	var m = mo.ofSeries(c.rows, c.step, c.event, c.reference_years, c.equilibrium, c.relative);
	return {clean: mo.recoveryClean(m), series: series(m)};
}), difference: input.difference.map(function (c) {
	return mo.recoveryDifference(c.a, c.b, c.step);
}), of: input.of.map(function (c) {
	var r = mo.recoveryOf(c.affected, c.control, c.names, c.step, c.event);
	return r.rows;
}), check: input.check.map(function (c) {
	try { return mo.recoveryCheck.apply(null, c); } catch (e) { return 'error: ' + e.message; }
}), round: input.round.map(function (c) { return mo.pyRound(c[0], c[1]); }),
	addYears: input.addYears.map(function (c) { return mo.addYears(c[0], c[1]); }),
	columns: mo.RECOVERY_COLUMNS};
process.stdout.write(JSON.stringify(out));
"""


def _node(script, data):
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=300)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout.strip().splitlines()[-1])


def _same(a, b, where=''):
	"""A (from Python) and B (from Node) equal: numbers to 1e-9, NaN as 'NaN' or None."""
	if isinstance(a, dict):
		assert isinstance(b, dict) and set(a) == set(b), (where, sorted(a), sorted(b) if isinstance(b, dict) else b)
		for k in a:
			_same(a[k], b[k], f'{where}.{k}')
	elif isinstance(a, (list, tuple, np.ndarray)):
		assert isinstance(b, list) and len(a) == len(b), (where, len(a), b if not isinstance(b, list) else len(b))
		for i, (x, y) in enumerate(zip(a, b)):
			_same(x, y, f'{where}[{i}]')
	elif isinstance(a, (bool, np.bool_)) or a is None or isinstance(a, str):
		assert a == b, (where, a, b)
	elif isinstance(a, (dt.date,)):
		assert str(a) == b, (where, a, b)
	elif math.isnan(a):
		assert b in ('NaN', None), (where, a, b)
	else:
		assert isinstance(b, (int, float)) and not isinstance(b, bool), (where, a, b)
		assert abs(a - b) <= 1e-9 * max(1, abs(a)), (where, a, b)


def _monthly(start, years, f):
	return [{'date': dt.date(start + i // 12, i % 12 + 1, 1).isoformat(), 'value': f(i, dt.date(start + i // 12,
	                                                                                              i % 12 + 1, 1))}
	        for i in range(12 * years)]


def _sixteen(start, years, f):
	out = []
	for y in range(start, start + years):
		for k in range(23):
			d = dt.date(y, 1, 1) + dt.timedelta(days=16 * k)
			out.append({'date': d.isoformat(), 'value': f(len(out), d)})
	return out


def _annual(start, years, f):
	return [{'date': f'{y}-01-01', 'value': f(i, dt.date(y, 7, 1))} for i, y in enumerate(range(start, start + years))]


def _drop(event, depth, years_back, period, noise, seed, gap_every=0, outlier=None):
	"""A value of 0.6 with a season of PERIOD steps that drops DEPTH on EVENT and recovers linearly in YEARS_BACK."""
	rng = np.random.default_rng(seed)
	eps = rng.normal(0, noise, 1000)

	def f(i, d):
		if gap_every and i % gap_every == 5:
			return None
		after = (d - event).days / 365.25
		loss = 0 if after < 0 else max(0.0, depth * (1 - after / years_back)) if years_back else depth
		v = 0.6 - loss + (0.1 * math.sin(2 * math.pi * i / period) if period > 1 else 0) + eps[i]
		return v - 0.5 if outlier is not None and i == outlier else v
	return f


def _cases():
	ev1, ev2, ev3 = dt.date(2018, 7, 15), dt.date(2017, 8, 20), dt.date(2014, 8, 1)
	affected = _monthly(2014, 10, _drop(ev1, 0.3, 4, 12, 0.02, 1, gap_every=17, outlier=60))
	control = _monthly(2014, 10, _drop(ev1, 0.0, 0, 12, 0.02, 2))
	series = [
		('monthly', affected, ev1, {}),
		('monthly', control, ev1, {}),
		('monthly', _monthly(2014, 10, _drop(ev1, 0.3, 0, 12, 0.01, 3)), ev1, {}),  # no recovery
		('monthly', _monthly(2014, 10, _drop(ev1, -0.2, 3, 12, 0.02, 4)), ev1, {'reference_years': 2,
		                                                                        'equilibrium': 0.1}),  # a rise
		('monthly', affected[:30], dt.date(2016, 3, 1), {}),  # too short after
		('monthly', affected[:24], dt.date(2015, 6, 1), {}),  # too short for STL
		('16-day', _sixteen(2014, 9, _drop(ev2, 0.25, 3, 23, 0.02, 5, gap_every=11)), ev2, {}),
		('annual', _annual(2005, 18, _drop(ev3, 0.3, 5, 1, 0.01, 6)), ev3, {}),
		('annual', _annual(2005, 18, _drop(ev3, 0.3, 5, 1, 0.01, 6)), ev3, {'relative': False}),
		('monthly', [], ev1, {}),
	]
	return series, affected, control, ev1


def _stl_cases():
	rng = np.random.default_rng(1)
	t = np.arange(240)
	y = 0.5 + 0.2 * np.sin(2 * np.pi * t / 12) + 0.0005 * t + rng.normal(0, 0.03, len(t))
	y[100] -= 0.6
	y[120:] -= 0.15
	z = 0.3 + 0.1 * np.cos(2 * np.pi * np.arange(23 * 6) / 23) + rng.normal(0, 0.02, 23 * 6)
	cases = []
	for robust in (True, False):
		# the shortest series: two cycles; robust, 25 values (the least of recovery.metrics): with 24 the fit leaves
		# residuals of the rounding alone, whose robustness weights are noise in numpy and in JavaScript alike
		short = y[:25] if robust else y[:24]
		cases += [(y, 12, 13, 13, None, robust), (y, 12, 7, None, None, robust), (y, 12, 8, 20, 14, robust),
		          (z, 23, 25, 25, None, robust), (z, 23, 7, None, None, robust), (short, 12, 13, 13, None, robust),
		          (y[:31], 4, 3, None, None, robust)]
	return cases


@node
def test_the_app_computes_the_recovery_as_the_package():
	series, affected, control, ev = _cases()
	stl_cases = _stl_cases()
	diff_cases = [(affected, control, 'monthly'), (control[3:50], affected, 'monthly'),
	              (series[6][1], series[6][1][10:], '16-day')]
	checks = [['monthly', '2018-07-15', '2014-01-01', '2023-12-31', 3, 0.05],
	          ['daily', '2018-07-15', '2014-01-01', '2023-12-31', 3, 0.05],
	          ['weekly', '2018-07-15', '2014-01-01', '2023-12-31', 3, 0.05],
	          ['monthly', '2018-02-30', '2014-01-01', '2023-12-31', 3, 0.05],
	          ['monthly', '', '2014-01-01', '2023-12-31', 3, 0.05],
	          ['monthly', '2018-07-15T10:00', '2014-01-01', '2023-12-31', '3', '0.05'],
	          ['annual', '2018-07-15', '2014-01-01', '2023-12-31', 'three', 0.05],
	          ['16-day', '2018-07-15', '2014-01-01', '2023-12-31', 3, 'x'],
	          ['monthly', '2018-07-15', '2014-01-01', '2023-12-31', 0, 0.05],
	          ['monthly', '2018-07-15', '2014-01-01', '2023-12-31', 3, 1],
	          ['monthly', '2018-07-15', '2014-01-01', '2023-12-31', 3, 0],
	          ['monthly', '2024-01-01', '2014-01-01', '2023-12-31', 3, 0.05],
	          ['monthly', '2014-01-01', '2014-01-01', '2023-12-31', 3, 0.05],
	          ['monthly', '2023-12-31', '2014-01-01', '2023-12-31', 3, 0.05],
	          ['monthly', '2016-07-15', '2014-01-01', '2023-12-31', 3, 0.05],
	          ['monthly', '2016-02-29', '2015-02-28', '2023-12-31', 1, 0.05],
	          ['annual', '2017-01-01', '2014-01-01', '2023-12-31', 3, 0.05],
	          ['monthly', '2018-07-15', '2014-01-01', '2023-12-31', 2.7, 0.5]]
	rounds = [[0.125, 2], [-0.125, 2], [0.375, 2], [2.5, 0], [3.5, 0], [0.15, 1], [1.005, 2], [-12.345678, 3],
	          [7, 4], [0.0001234567, 4], [123.45, 1], [-0.5, 0], [0.285, 2]]
	adds = [['2016-02-29', 1], ['2016-02-29', -4], ['2018-07-15', -3], ['2019-12-31', 1]]
	of_cases = [(affected, control, ['Burned', 'Unburned']), (affected, None, ['Burned', None])]
	data = {'stl': [{'y': list(y), 'period': p, 'seasonal': s, 'trend': tr, 'low_pass': lp, 'robust': rb}
	                for y, p, s, tr, lp, rb in stl_cases],
	        'series': [{'rows': rows, 'step': step, 'event': str(e), 'reference_years': kw.get('reference_years'),
	                    'equilibrium': kw.get('equilibrium'), 'relative': kw.get('relative', True)}
	                   for step, rows, e, kw in series],
	        'difference': [{'a': a, 'b': b, 'step': s} for a, b, s in diff_cases],
	        'of': [{'affected': a, 'control': c, 'names': n, 'step': 'monthly', 'event': str(ev)}
	               for a, c, n in of_cases],
	        'check': checks, 'round': rounds, 'addYears': adds}
	app = _node(CORE, data)
	# STL, to 1e-9 of monitoreo.stl
	for (y, p, s, tr, lp, rb), got in zip(stl_cases, app['stl']):
		want = stl.stl(y, p, seasonal=s, trend=tr, low_pass=lp, robust=rb)
		for a, b in zip(want, got):
			assert np.allclose(a, b, atol=1e-9, rtol=0), (p, s, tr, lp, rb, np.abs(np.array(a) - b).max())
	# every metric, its notes and the series of the chart
	for (step, rows, e, kw), got in zip(series, app['series']):
		m = recovery.of_series(rows, step, e, kw.get('reference_years', 3), kw.get('equilibrium', 0.05),
		                       kw.get('relative', True))
		_same(recovery.clean(m), got['clean'], f'{step} {e}')
		s = m.get('_series') or {}
		for k in ('dates', 'values', 'deseasonalized', 'trend', 'seasonal'):
			_same(s.get(k), got['series'][k], f'{step} {e} _series.{k}')
	# the cases reach every branch: recovered without equilibrium, in equilibrium, not recovered, a rise, no inflection,
	# too short for STL, 16-day, annual (relative and not) and no values
	got = [c['clean'] for c in app['series']]
	assert {'tINF', 'tREF', 'tEQ', 'recovered_pct', 'seasonal_amplitude'} <= set(got[0])
	assert got[0]['tREF'] and got[0]['tEQ'] is None and got[1]['tEQ'] and got[2]['tREF'] is None
	assert got[3]['direction'] == 'increase' and got[4]['tINF'] is None and 'S95' not in got[5]
	assert got[6]['tREF'] and got[7]['tEQ'] and got[8]['tEQ'] is None and got[9] == {'notes': ['no values'], 'gaps': 1}
	for (a, b, s), got in zip(diff_cases, app['difference']):
		_same(recovery.difference(a, b, s), got, 'difference')
	# the table of services.recovery_metrics: affected, control and their difference (relative=False)
	for (a, c, names), got in zip(of_cases, app['of']):
		ms = {'affected': recovery.of_series(a, 'monthly', ev)}
		if c:
			ms['control'] = recovery.of_series(c, 'monthly', ev)
			ms['difference'] = recovery.of_series(recovery.difference(a, c, 'monthly'), 'monthly', ev, relative=False)
		region = {'affected': names[0], 'control': names[1], 'difference': f'{names[0]} - {names[1]}'}
		_same([services._recovery_row(k, region[k], m) for k, m in ms.items()], got, 'rows')
	assert app['columns'] == services.RECOVERY_COLUMNS

	def check(c):
		try:
			return list(recovery.check(*c))
		except ValueError as error:
			return 'error: ' + str(error)
	for c, got in zip(checks, app['check']):
		want = check(c)
		_same([str(x) if isinstance(x, dt.date) else x for x in want] if isinstance(want, list) else want, got, c)
	assert [round(x, n) for x, n in rounds] == app['round']
	assert [str(recovery.add_years(dt.date.fromisoformat(d), n)) for d, n in adds] == app['addYears']


STEPS = r"""
function rowWith(label) {  // the widget after the label LABEL in its row
	return find(controls, 'Panel', function (w) {
		return w.children[0] && w.children[0].kind === 'Label' && w.children[0].opts.value === label;
	})[0].children[1];
}
function head(title) {
	return find(controls, 'Button', function (w) { return w.opts.label.slice(2).indexOf(title) === 0; })[0];
}
function compute() {
	button('Compute the recovery').opts.onClick();
	return last();
}
var info = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
var out = {};
answer = info;
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
out.section = Boolean(head('Recovery after a disturbance'));
out.stepItems = find(controls, 'Select', function (w) {
	return w.opts.value === 'monthly' && w.opts.items.length === 3;
}).map(function (w) { return w.opts.items.map(function (i) { return i.value; }); });
out.controls = texts(controls);
textbox(function (w) { return w.opts.value === '2025-01-01'; }).opts.onChange('2016-01-01');
textbox(function (w) { return w.opts.value === '2025-12-31'; }).opts.onChange('2024-12-31');
out.noEvent = compute();
rowWith('Date of the event (YYYY-MM-DD)').opts.onChange('2017-07-15');
out.early = compute();
rowWith('Date of the event (YYYY-MM-DD)').opts.onChange('2020-07-15');
button('Use this region as the control').opts.onClick();
out.controlIs = texts(controls).filter(function (x) { return x.indexOf('Control: ') === 0; });
out.same = compute();
answer = info;  // the affected region: the map view again
button('Use the map view').opts.onClick();
answer = {features: input.rows.map(function (r) { return {properties: r}; })};
out.result = compute();
out.tables = find(results, 'Chart', function (c) { return c.opts.type === 'Table'; }).map(function (c) {
	return c.opts.table;
});
out.lines = find(results, 'Chart', function (c) { return c.opts.type === 'LineChart'; }).map(function (c) {
	return {cols: c.opts.table.cols.map(function (x) { return x.label; }), rows: c.opts.table.rows.length};
});
find(results, 'Button', function (w) { return w.opts.label === 'Download CSV'; })[0].opts.onClick();
out.files = files;
button('Clear').opts.onClick();
out.cleared = texts(controls).filter(function (x) { return x.indexOf('Control: ') === 0; });
button('Español').opts.onClick();
out.spanish = {section: Boolean(head('Recuperación tras una perturbación')),
	buttons: ['Calcular la recuperación', 'Usar esta región como control'].map(function (b) { return Boolean(button(b)); }),
	labels: ['Fecha del evento (AAAA-MM-DD)', 'Años de referencia', 'Equilibrio (cambio relativo)'].map(function (l) {
		return texts(controls).indexOf(l) >= 0;
	})};
process.stdout.write(JSON.stringify(out));
"""

KEYS = ('recovery', 'recEvent', 'recReference', 'recEquilibrium', 'recHelp', 'recControlUse', 'recControlClear',
        'recControlNone', 'recControlIs', 'recSame', 'computeRecovery', 'recAffected', 'recControl', 'recDifference',
        'recSeries', 'recDeseasonalized', 'recTrend', 'recReferenceLow', 'recReferenceHigh', 'recEventIs', 'recMethod')


@node
def test_the_panel_has_the_recovery_in_both_languages():
	"""The section Recovery after a disturbance in every theme: its options, the errors of recovery.check, the control
	area chosen as the region, the table, notes, charts and CSV of the affected area, the control and their difference,
	and its texts in Spanish."""
	from test_themes import PANEL, _build
	with open(os.path.join(GEE, 'ui.js'), encoding='utf-8') as f:
		ui = f.read()
	for key in KEYS:
		assert ui.count(f'\t{key}: ') + ui.count(f' {key}: ') >= 2, key  # in Spanish and in English
	ev = dt.date(2020, 7, 15)
	affected = _monthly(2016, 9, _drop(ev, 0.3, 3, 12, 0.02, 7))
	control = _monthly(2016, 9, _drop(ev, 0.0, 0, 12, 0.02, 8))
	rows = [dict(r, region=name, n_pixels=4, n_images=1) for name, rs in (('affected', affected), ('control', control))
	        for r in rs]
	build = _build()
	data = {'community': build.community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {}, 'rows': rows}
	out = _node(PANEL[:PANEL.index('var out = {};')] + STEPS, data)
	assert out['section'] and ['monthly', '16-day', 'annual'] in out['stepItems']
	assert any(t.startswith('Severity and recovery after a fire') for t in out['controls'])
	assert any(t.startswith('Control: none (optional)') for t in out['controls'])

	def error(*args):
		with pytest.raises(ValueError) as e:
			recovery.check(*args)
		return [str(e.value)]
	assert out['noEvent']['texts'] == error('monthly', '', '2016-01-01', '2024-12-31')
	assert out['early']['texts'] == error('monthly', '2017-07-15', '2016-01-01', '2024-12-31')
	assert out['controlIs'][0].startswith('Control: Map view. Its series and the difference')
	assert out['same']['texts'][0].startswith('The control is the affected region')
	# the table of the three series, with the values of the package
	table, = out['tables']
	ms = {'affected': recovery.of_series(affected, 'monthly', ev), 'control': recovery.of_series(control, 'monthly', ev)}
	ms['difference'] = recovery.of_series(recovery.difference(affected, control, 'monthly'), 'monthly', ev,
	                                      relative=False)
	assert table[0] == ['Series', 'Region', 'direction', 'S95', 'impact_pct', 'DIT_years', 'RRT_years', 'RET_years',
	                    'recovered_pct']
	assert [r[:3] for r in table[1:]] == [['affected', 'Map view', 'decrease'], ['control', 'Map view',
	                                      ms['control']['direction']], ['difference', 'Map view - Map view', 'decrease']]
	for i, k in enumerate(table[0][3:], 3):  # the numbers with 4 significant digits (num of ui.js)
		for row, m in zip(table[1:], ms.values()):
			assert (row[i] == '' and m.get(k) is None) or float(row[i]) == pytest.approx(m[k], rel=1e-3), (k, row[i])
	assert out['lines'][0]['cols'] == ['Date', 'affected', 'affected, without seasonality', 'affected, trend (STL)',
	                                   'reference (median − MAD)', 'reference (median + MAD)', 'control']
	assert out['lines'][1]['cols'][1:4] == ['difference', 'difference, without seasonality', 'difference, trend (STL)']
	assert [x['rows'] for x in out['lines']] == [108, 108]
	texts = out['result']['texts']
	assert 'NDVI Sentinel-2 · Map view · recovery after a disturbance · event 2020-07-15' in texts
	assert any(t.startswith('Metrics of Marcos et al. (2023)') for t in texts)
	assert out['files'][-1].endswith('recovery_after_a_disturbance_event_2020-07-15')
	assert out['cleared'][0].startswith('Control: none')
	assert out['spanish'] == {'section': True, 'buttons': [True, True], 'labels': [True, True, True]}
