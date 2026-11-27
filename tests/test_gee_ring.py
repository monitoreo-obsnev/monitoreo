"""The control ring of a disturbance in the Earth Engine app, without Earth Engine: in Node, mo.checkRing accepts and
refuses the same options as control.check, with the same messages; mo.ringDifference gives the rows of
control.difference_rows; mo.ringOf makes the conditions of where of services._ring; and the panel (gee/ui.js, with the
ui and ee of tests/test_themes.py) has the check boxes of the ring in the Time series and Recovery sections in English
and Spanish, builds the ring with the gap and width of its boxes (buffer and difference, as control.zones), adds the
difference affected - control to the chart and the CSV, and writes and applies the option ring of the parameters."""

import json
import math
import os
import shutil
import subprocess

import pytest

from monitoreo import catalog, control

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
function attempt(f) {
	try { return f(); } catch (e) { return 'error: ' + e.message; }
}
var opts = mo.checkRing(true);
process.stdout.write(JSON.stringify({
	check: input.check.map(function (c) { return attempt(function () { return mo.checkRing(c); }); }),
	difference: input.difference.map(mo.ringDifference),
	of: attempt(function () {
		return mo.ringOf({ha: {affected: 120.5, control: 900}, match: {ELEVATION: {value_lo: 1210.5, value_hi: 1830}}},
			opts);
	}),
	nothing: attempt(function () { return mo.ringOf({ha: {affected: 1, control: 2}, match: {ELEVATION: {}}}, opts); }),
	empty: attempt(function () { return mo.ringOf({ha: {affected: 120.5, control: null}, match: {}}, opts); }),
	elevation: mo.findEntry('ELEVATION', 'Copernicus').ref,
	names: mo.RING_NAMES}));
"""

CASES = [True, {}, {'gap': 0}, {'gap': '200', 'width': '1000.5'}, {'gap': ' 1e2 ', 'width': 2}, {'gap': None},
         {'gap': True, 'width': 3}, {'gap': -1}, {'width': 0}, {'width': -5}, {'gap': 'a'}, {'gap': ''},
         {'width': [1]}, {'foo': 1}, {'foo': 1, 'bar': 2, 'gap': 3}, {'match': 'slope'},
         {'match': ['elevation', 'SLOPE']}, {'match': ['NDVI', 'x']}, {'match': ''}, {'match': []}, {'match': None},
         {'match': [None, 1.5]}, {'exclude': {'wdpa_id': 1}, 'within': {'bbox': [1, 2, 3, 4]}}, False, 'yes', 5,
         [1, 2], None]


def _node(script, data):
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=300)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout.strip().splitlines()[-1])


def _python(ring):
	try:
		return control.check(ring)
	except ValueError as error:
		return 'error: ' + str(error)


def _rows():
	rows = []
	for i, d in enumerate(['2021-03-01', '2021-01-01', '2021-02-01', '2021-04-01', '2021-05-01']):
		rows.append({'region': 'affected', 'date': d, 'value': None if i == 3 else 0.5 + i / 10, 'n_pixels': 4,
		             'n_images': i + 1})
		if i != 4:
			rows.append({'region': 'control', 'date': d, 'value': 0.6 - i / 20, 'n_pixels': 9, 'n_images': 2})
		rows.append({'region': 'other', 'date': d, 'value': 1.0, 'n_pixels': 1, 'n_images': 1})
	return rows


@node
def test_the_core_checks_the_ring_and_its_difference_as_the_package():
	"""mo.checkRing accepts and refuses the options of control.check, with its answer and its messages;
	mo.ringDifference gives the rows of control.difference_rows (by date, only those with both values); mo.ringOf
	gives the conditions of where of services._ring (the percentiles 5 and 95 of the elevation of the Copernicus DEM),
	none without them, and the error of an empty ring."""
	without_images = [{k: v for k, v in r.items() if k != 'n_images'} for r in _rows()]
	app = _node(CORE, {'check': CASES, 'difference': [_rows(), without_images, []]})
	for ring, got in zip(CASES, app['check']):
		assert got == _python(ring), (ring, got)
	for rows, got in zip([_rows(), without_images, []], app['difference']):
		assert got == control.difference_rows(rows)
	assert [r['date'] for r in app['difference'][0]] == ['2021-01-01', '2021-02-01', '2021-03-01']
	assert app['names'] == list(control.NAMES)
	ref = catalog.find('ELEVATION', control.MATCH['ELEVATION'])['ref']
	assert app['elevation'] == ref
	assert app['of'] == {'gap': 150, 'width': 1500, 'ha': {'affected': 120.5, 'control': 900},
	                     'match': {'ELEVATION': [1210.5, 1830]},
	                     'where': [{'ref': ref, 'min': 1210.5, 'max': 1830}]}
	assert app['nothing']['where'] == [] and app['nothing']['match'] == {}
	assert app['empty'] == ('error: the control ring is empty: give a larger width, a smaller gap, or fewer areas in '
	                        'exclude or a larger within')


KEYS = ('ringOn', 'recRing', 'ringGap', 'ringWidth', 'ringHelp', 'recRingNote', 'ringAreas', 'ringMatch', 'ringDoy',
        'ringLayer', 'ringOnly')

# the ee of the panel records its calls (CALLS: [name, the numbers and texts of its arguments]) and the ee.Feature of
# the rows of a CSV (CSV), and evaluate answers ANSWER(), if it is a function
RECORD = r"""
var CALLS = [], CSV = [];
function plain(a) {
	return typeof a === 'number' || typeof a === 'string' ? a : Array.isArray(a) && a.every(function (x) {
		return typeof x === 'number';
	}) ? a : null;
}
"""

STEPS = r"""
var info = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
var rows = [];
['affected', 'control'].forEach(function (g, k) {
	for (var m = 1; m <= 12; m++) {
		rows.push({properties: {region: g, date: '2025-' + (m < 10 ? '0' : '') + m + '-01', value: 0.5 + m / 100 - k / 10,
			n_pixels: 4, n_images: 1}});
	}
});
var ringInfo = {ha: {affected: 812.3, control: 6120}, match: {ELEVATION: {value_lo: 1210.5, value_hi: 1830}}};
function queue(answers) {
	answer = function () { return answers.shift(); };
}
function ringCalls() {
	return CALLS.filter(function (c) {
		return ['dissolve', 'buffer', 'difference', 'intersection', 'Reducer.percentile'].indexOf(c[0]) >= 0;
	});
}
function boxes(value) {
	return find(controls, 'Textbox', function (w) { return w.opts.value === value; });
}
answer = info;
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
var series = 'Control ring around the region (affected area)', recovery = 'Control ring around the region';
out.boxes = [Boolean(check(series)), Boolean(check(recovery))];
out.off = texts(controls).filter(function (s) { return /^Series of the affected area/.test(s); }).length;
check(series).opts.onChange(true);
out.on = texts(controls).filter(function (s) { return /^Series of the affected area/.test(s); }).length;
out.gapBoxes = [boxes('150').length, boxes('1500').length];
boxes('150')[0].opts.onChange('200');
boxes('1500')[0].opts.onChange('1000');
CALLS.length = 0;
queue([ringInfo, {features: rows}]);
button('Compute the time series').opts.onClick();
out.calls = ringCalls();
out.matched = CALLS.some(function (c) { return c[1].indexOf(1210.5) >= 0; }) &&
	CALLS.some(function (c) { return c[1].indexOf(1830) >= 0; });
out.series = last();
out.lines = find(results, 'Chart', function (c) { return c.opts.type === 'LineChart'; }).map(function (c) {
	return c.opts.table.cols.map(function (x) { return x.label; });
});
out.layers = layers.slice();
find(results, 'Button', function (w) { return w.opts.label === 'Download CSV'; })[0].opts.onClick();
out.csv = CSV.filter(function (p) { return p.region === 'affected - control'; });
out.shown = show('time_series').json.parameters;
boxes('200')[0].opts.onChange('0');
CALLS.length = 0;
queue([ringInfo, {features: rows}]);
button('Compute the time series').opts.onClick();
out.noGap = ringCalls();
check('A line per year, over the days of the year').opts.onChange(true);
button('Compute the time series').opts.onClick();
out.doy = last().texts;
check('A line per year, over the days of the year').opts.onChange(false);
out.applied = apply({analysis: 'time_series', parameters: {region: {bbox: [-3.62, 36.86, -3.5, 36.93]},
	variable: 'NDVI', sensor: 'Sentinel-2', start: '2025-01-01', end: '2025-12-31',
	ring: {gap: 300, width: 2000}}}).report;
out.appliedBoxes = [Boolean(check(series).opts.value), boxes('300').length, boxes('2000').length];
out.reshown = show('time_series').json.parameters;
out.excluded = apply({analysis: 'time_series', parameters: {region: {bbox: [-3.62, 36.86, -3.5, 36.93]},
	variable: 'NDVI', sensor: 'Sentinel-2', start: '2025-01-01', end: '2025-12-31',
	ring: {exclude: {bbox: [-3.6, 36.9, -3.55, 36.92]}}}}).report;
out.excludedOn = check(series).opts.value;
out.none = show('time_series').json.parameters;
// the recovery: the ring instead of the control of the button
answer = info;
button('Use the map view').opts.onClick();
button('Use this region as the control').opts.onClick();
out.controlBefore = texts(controls).filter(function (x) { return x.indexOf('Control: ') === 0; });
check(recovery).opts.onChange(true);
out.controlAfter = texts(controls).filter(function (x) { return x.indexOf('Control: ') === 0; });
out.note = texts(controls).indexOf('The ring replaces the control chosen with the button: one or the other, not both.');
out.useButton = Boolean(button('Use this region as the control'));
find(controls, 'Panel', function (w) {
	var c = w.children[0];
	return c && c.kind === 'Label' && c.opts.value === 'Date of the event (YYYY-MM-DD)';
})[0].children[1].opts.onChange('2021-07-15');
find(controls, 'Textbox', function (w) { return w.opts.value === '2025-01-01'; })[0].opts.onChange('2017-01-01');
rows = [];
['affected', 'control'].forEach(function (g, k) {
	for (var y = 2017; y <= 2025; y++) for (var m = 1; m <= 12; m++) {
		var after = y > 2021 || (y === 2021 && m > 7);
		rows.push({properties: {region: g, date: y + '-' + (m < 10 ? '0' : '') + m + '-01',
			value: 0.6 + 0.1 * Math.sin(m / 2) - (after && !k ? 0.3 : 0) + ((y * 12 + m) % 5) / 100, n_pixels: 4,
			n_images: 1}});
	}
});
CALLS.length = 0;
queue([ringInfo, {features: rows}]);
button('Compute the recovery').opts.onClick();
out.recoveryCalls = ringCalls();
out.recovery = last();
out.table = find(results, 'Chart', function (c) { return c.opts.type === 'Table'; }).map(function (c) {
	return c.opts.table.map(function (r) { return r.slice(0, 2); });
});
check(recovery).opts.onChange(false);
out.back = texts(controls).filter(function (x) { return x.indexOf('Control: ') === 0; });
check(series).opts.onChange(true);
button('Español').opts.onClick();
out.spanish = [Boolean(find(controls, 'Checkbox', function (w) {
	return w.opts.label === 'Anillo de control alrededor de la región (área afectada)';
})[0]), Boolean(find(controls, 'Checkbox', function (w) {
	return w.opts.label === 'Anillo de control alrededor de la región';
})[0]), texts(controls).indexOf('Separación (m)') >= 0, texts(controls).indexOf('Anchura (m)') >= 0];
"""


def _panel():
	from test_parameters_gee import _panel as panel
	text = panel()
	args = 'var args = Array.prototype.slice.call(arguments);'
	answers = '})} : answer;'
	assert text.count(args) == 1 and text.count(answers) == 1
	text = text.replace(args, args + '\n\t\tCALLS.push([name, args.map(plain)]);\n'
	                    "\t\tif (name === 'Feature' && args[0] === null && args[1]) CSV.push(args[1]);")
	return RECORD + text.replace(answers, "})} : typeof answer === 'function' ? answer() : answer;")


@node
def test_the_panel_has_the_ring_in_both_languages():
	"""The check boxes of the ring in Time series and Recovery after a disturbance, with their gap and width; the
	series of the affected area, its ring (buffer and difference with the distances of the boxes, as control.zones)
	matched by elevation, and their difference in the chart and the CSV; Show and Apply of the option ring; the ring
	instead of the control of the button in the recovery; and the texts in Spanish."""
	import test_parameters_gee as tp
	from test_themes import _build
	with open(os.path.join(GEE, 'ui.js'), encoding='utf-8') as f:
		ui = f.read()
	for key in KEYS:
		assert ui.count(f'\t{key}: ') + ui.count(f' {key}: ') >= 2, key  # in Spanish and in English
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': tp.ASSETS,
	        'answer': tp.ANSWER, 'hint': tp.HINT}
	out = _node(_panel() + tp.HELPERS + STEPS + '\nconsole.log(JSON.stringify(out));', data)
	assert out['boxes'] == [True, True] and out['off'] == 0 and out['on'] == 1 and out['gapBoxes'] == [1, 1]
	e = control.MAX_ERROR
	assert out['calls'] == [['dissolve', [e]], ['buffer', [1200, e]], ['buffer', [200, e]], ['difference', [None, e]],
	                        ['Reducer.percentile', [[5, 95], None]]]
	assert out['noGap'] == [['dissolve', [e]], ['buffer', [1000, e]], ['difference', [None, e]],
	                        ['Reducer.percentile', [[5, 95], None]]]
	assert out['matched']  # the where of the elevation of the affected area, in the series of both
	assert out['lines'] == [['Date', 'affected', 'control', 'affected - control']]
	assert 'Control ring' in out['layers']
	assert ('Affected area: 812.3 ha; control ring: 6120 ha, from 200 to 1200 m from it. Pixels of both between 1210.5 '
	        'and 1830 m of elevation.') in out['series']['texts']
	assert len(out['csv']) == 12 and all(math.isclose(r['value'], 0.1) for r in out['csv'])
	assert out['shown']['ring'] == {'gap': 200, 'width': 1000}
	assert out['doy'] == ['The control ring is not for the series by day of the year: uncheck one of them.']
	skipped = tp._not_applied(out['applied'])
	assert 'ring' not in skipped and out['appliedBoxes'] == [True, 1, 1]
	assert out['reshown']['ring'] == {'gap': 300, 'width': 2000}
	assert tp._not_applied(out['excluded'])['ring'].startswith('the app takes the ring with its gap and width')
	assert out['excludedOn'] is False and 'ring' not in out['none']
	# the recovery: the ring replaces the control of the button
	assert out['controlBefore'][0].startswith('Control: Map view.') and out['controlAfter'] == []
	assert out['note'] >= 0 and not out['useButton']
	# the gap and width applied, shared by both sections
	assert out['recoveryCalls'] == [['dissolve', [e]], ['buffer', [2300, e]], ['buffer', [300, e]],
	                                ['difference', [None, e]], ['Reducer.percentile', [[5, 95], None]]]
	assert [r[0] for r in out['table'][0][1:]] == ['affected', 'control', 'difference']
	assert [r[1] for r in out['table'][0][1:]] == ['affected', 'control', 'affected - control']
	assert any(t.startswith('Affected area: 812.3 ha; control ring: 6120 ha') for t in out['recovery']['texts'])
	assert out['back'][0].startswith('Control: none')  # the control of the button was cleared by the ring
	assert out['spanish'] == [True, True, True, True]
	with open(os.path.join(GEE, 'monitoreo_app.js'), encoding='utf-8') as f:
		app = f.read()
	assert 'function checkRing(' in app and 'ringOn' in app  # built
