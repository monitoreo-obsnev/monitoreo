"""The seasonal profile by day of the year in the Earth Engine app (gee/core.js and gee/ui.js, in Node, without Earth
Engine): mo.overYears, mo.doyProfile and mo.udunits give the numbers of timeseries.over_years, timeseries.doy_profile
and catalog.udunits on the same values, and the panel, with «A line per year, over the days of the year» checked,
draws the metric between the years chosen of one or two variables (e.g. the NDSI and the NDVI) on two y axes, each
from the values of its own variable, with the CSV of the profile of services.time_series."""

import json
import os
import random
import re
import shutil
import subprocess

import pytest

from monitoreo import catalog, charts, timeseries

GEE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gee')
pytestmark = pytest.mark.skipif(not shutil.which('node'), reason='no Node')

# catalog.js and core.js in Node, with an ee that computes nothing: the functions of the profile need no Earth Engine
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
	try {
		return {value: f()};
	} catch (e) {
		return {error: e.message};
	}
}
var out = {};
out.overYears = input.values.map(function (v) {
	return input.metrics.map(function (m) { return attempt(function () { return mo.overYears(v, m); }); });
});
out.bad = input.bad.map(function (m) { return attempt(function () { return mo.overYears([1, 2], m); }); });
out.labels = input.days.map(mo.dayLabel);
out.withDoy = mo.withDoy(input.dated);
out.profiles = input.profiles.map(function (c) {
	return attempt(function () { return mo.doyProfile(mo.withDoy(c.rows), c.spec, c.step, c.interannual, c.variable); });
});
out.defaultRange = ['SPECTRAL_INDICES', 'INDEX_RANGE', 'SCALE_METRICS', 'indexYlim'].filter(function (k) {
	return k in mo;
});
out.udunits = input.units.map(mo.udunits);
out.constants = {UDUNITS: mo.UDUNITS, INTERANNUAL: mo.INTERANNUAL, PROFILE_COLUMNS: mo.PROFILE_COLUMNS,
	PROFILE_META: mo.PROFILE_META, MONTH_ABBR: mo.MONTH_ABBR, MONTH_STARTS: mo.MONTH_STARTS};
process.stdout.write(JSON.stringify(out));
"""

METRICS = ['mean', 'median', 'min', 'max', 'std', 'cv', 'p0', 'p25', 'p50', 'p75', 'p100', 'p2.5', 'p90', 'P75',
           ' Median ']
BAD = ['mode', 'sum', 'count', 'p101', 'p-5', 'px', '']
UNITS = ['[unitless]', '[%]', '[°C]', '[º]', ' [mm/month] ', 'mm day-1', 'mm', '', None, '[weird]', 'm²', '1']


def _node(script, data):
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout.strip().splitlines()[-1])


def _python(f):
	try:
		return {'value': f()}
	except ValueError as e:
		return {'error': str(e)}


def _values():
	"""Lists of values of each year: empty, without values, one, two, a mean of 0 (no cv), sums that are not exact
	in floating point, and random ones with gaps."""
	rnd = random.Random(2026)
	out = [[], [None], [0.42], [0.1, 0.2], [-1, 1], [0.1, 0.2, 0.3], [None, 0.7, None, -0.15, 0.3333333333333333],
	       [5, 5, 5, 5], [-0.4, -0.2, -0.3]]
	for n in range(2, 14):
		out.append([None if rnd.random() < 0.15 else round(rnd.uniform(-1, 1), rnd.choice([2, 4, 17]))
		            for _ in range(n)])
	return out


def _rows(dates, regions, seed, gaps=0.15):
	rnd = random.Random(seed)
	return [{'region': g, 'date': d, 'value': None if rnd.random() < gaps else rnd.uniform(-0.3, 0.9), 'n_pixels': 5,
	         'n_images': 2} for g in regions for d in dates]


def _dates(period, season, step):
	return [a for a, _ in timeseries.bins({'period': period, 'season': season}, step)]


def _profiles():
	"""Cases of mo.doyProfile: monthly with two variables and two regions, 16-day from 10 March and in a season that
	crosses the new year, daily with 29 February, and the errors of the step and of the metric."""
	monthly = _dates(['2021-01-01', '2024-12-31'], None, 'monthly')
	two = [dict(r, variable='NDSI Sentinel-2') for r in _rows(monthly, ['Granada', 'Almeria'], 1)] + \
		[dict(r, variable='NDVI Sentinel-2') for r in _rows(monthly, ['Granada', 'Almeria'], 2)]
	for r in two:  # a month without values in any year
		if r['region'] == 'Granada' and r['date'][5:7] == '02' and r['variable'] == 'NDVI Sentinel-2':
			r['value'] = None
	march = {'period': ['2021-03-10', '2024-12-31'], 'season': None}
	winter = {'period': ['2021-01-01', '2024-12-31'], 'season': ['11-01', '03-31']}
	hydro = {'period': ['2019-10-15', '2022-10-14'], 'season': ['10-15', '10-14']}  # two parts of October
	late = {'period': ['2018-01-01', '2019-03-31'], 'season': ['11-01', '03-31']}  # the first season from 1 January
	days = ['2023-02-28', '2023-03-01', '2024-02-28', '2024-02-29', '2024-03-01', '2025-03-01', '2025-12-31',
	        '2024-12-31']
	return [
		{'rows': two, 'spec': None, 'step': 'monthly', 'interannual': 'p25', 'variable': 'NDSI Sentinel-2'},
		{'rows': two, 'spec': None, 'step': 'monthly', 'interannual': 'cv', 'variable': ''},
		{'rows': _rows(_dates(march['period'], None, '16-day'), ['Map view'], 3), 'spec': march, 'step': '16-day',
		 'interannual': 'mean', 'variable': 'NDVI Modis'},
		{'rows': _rows(_dates(winter['period'], winter['season'], '16-day'), ['b', 'a'], 4), 'spec': winter,
		 'step': '16-day', 'interannual': 'median', 'variable': 'NDSI Modis'},
		{'rows': _rows(days, ['Map view'], 5, 0), 'spec': None, 'step': 'daily', 'interannual': 'max',
		 'variable': 'NDSI Landsat'},
		{'rows': _rows(days, ['Map view'], 5, 0), 'spec': None, 'step': 'annual', 'interannual': 'max',
		 'variable': 'x'},
		{'rows': _rows(days, ['Map view'], 5, 0), 'spec': None, 'step': 'daily', 'interannual': 'mode',
		 'variable': 'x'},
		{'rows': [{'region': 'Map view', 'date': '2021-03-10', 'value': 0.25},
		          {'region': 'Map view', 'date': '2022-03-06', 'value': 0.75}],
		 'spec': {'period': ['2021-03-10', '2022-12-31'], 'season': None}, 'step': '16-day', 'interannual': 'mean',
		 'variable': 'x'},
		{'rows': _rows(_dates(hydro['period'], hydro['season'], 'monthly'), ['Map view'], 6), 'spec': hydro,
		 'step': 'monthly', 'interannual': 'mean', 'variable': 'NDVI Landsat'},
		{'rows': _rows(monthly, ['Sierra Nevada', 'Sierra Nevada', 'Baza'], 7), 'spec': None, 'step': 'monthly',
		 'interannual': 'median', 'variable': 'NDVI Sentinel-2'},
		{'rows': _rows(_dates(late['period'], late['season'], '16-day'), ['Map view'], 8), 'spec': late,
		 'step': '16-day', 'interannual': 'median', 'variable': 'NDSI Modis'},
	]


@pytest.fixture(scope='module')
def core():
	data = {'values': _values(), 'metrics': METRICS, 'bad': BAD, 'days': list(range(-1, 368)) + [0.5, 59.5, 365.9],
	        'dated': [{'date': d} for d in ('2023-01-01', '2024-02-29', '2024-12-31', '2025-07-01T00:00:00')],
	        'profiles': _profiles(), 'units': UNITS}
	return data, _node(CORE, data)


def test_the_metric_between_the_years_is_that_of_python(core):
	"""The same numbers, not only close ones: the sums in the same order (std, cv), the median of an even number of
	values, the percentiles interpolated between the closest ranks; the same errors."""
	data, out = core
	for values, got in zip(data['values'], out['overYears']):
		assert got == [_python(lambda m=m: timeseries.over_years(values, m)) for m in METRICS], values
	assert out['bad'] == [_python(lambda m=m: timeseries.over_years([1, 2], m)) for m in BAD]
	assert all('error' in b for b in out['bad'])


def test_the_days_of_the_year_are_those_of_python(core):
	data, out = core
	assert out['labels'] == [timeseries.day_label(d) for d in data['days']]
	assert out['withDoy'] == timeseries.with_doy([dict(r) for r in data['dated']])


def test_the_profile_is_that_of_python(core):
	"""Every row of each profile (region, variable, step of the year, its day of the year and name, the metric between
	the years and how many years had a value) as timeseries.doy_profile gives it, in its order."""
	data, out = core
	for case, got in zip(data['profiles'], out['profiles']):
		rows = timeseries.with_doy([dict(r) for r in case['rows']])
		want = _python(lambda: timeseries.doy_profile(rows, case['spec'], case['step'], case['interannual'],
		                                              case['variable']))
		assert got == want, (case['step'], case['interannual'])
	monthly, cv, march, winter, daily, annual, mode, tenth, hydro, named, late = out['profiles']
	assert [r['part'] for r in monthly['value'][:3]] == ['1', '2', '3'] and monthly['value'][0]['region'] == 'Almeria'
	empty = [r for r in monthly['value'] if r['region'] == 'Granada' and r['variable'] == 'NDVI Sentinel-2'
	         and r['part'] == '2']
	assert empty == [{'region': 'Granada', 'variable': 'NDVI Sentinel-2', 'part': '2', 'doy': 32, 'label': 'Feb',
	                  'value': None, 'n_years': 0}]
	assert {r['part'] for r in march['value']} == {str(k) for k in range(23)}
	# 10 March 2021, the first day of the period, is in the fifth 16-day step from 1 January, with 6 March 2022
	assert tenth['value'] == [{'region': 'Map view', 'variable': 'x', 'part': '4', 'doy': 65, 'label': 'Mar 6',
	                           'value': 0.5, 'n_years': 2}]
	assert [r['label'] for r in winter['value'] if r['part'] == '0'] == ['Nov 1', 'Nov 1']  # of the regions a and b
	# 29 February and 1 March apart, on their days of a leap year
	assert [(r['label'], r['doy']) for r in daily['value']][1:3] == [('Feb 29', 60), ('Mar 1', 61)]
	# the two parts of October of a hydrological year from 15 October
	assert [r['label'] for r in hydro['value']][9:11] == ['Oct 1-14', 'Oct 15-31']
	assert all(r['n_years'] <= 3 for r in hydro['value'])
	# the features of the same name apart, the second numbered
	assert [r['region'] for r in named['value'][::12]] == ['Baza', 'Sierra Nevada', 'Sierra Nevada (2)']
	# 1 January of the first, partial, season with 4 January of the next one, not in June
	assert [(r['part'], r['label']) for r in late['value'][:2]] == [('4', 'Jan 4'), ('5', 'Jan 20')]
	assert all(r['doy'] < 100 or r['doy'] > 300 for r in late['value'])
	assert 'needs a step shorter than a year' in annual['error'] and 'interannual' in mode['error']


def test_no_default_range_of_the_y_axes(core):
	"""Each y axis of the profile goes from the values of its own variable, as in Python: no default range by variable."""
	data, out = core
	assert out['defaultRange'] == []


def test_the_units_and_constants_are_those_of_python(core):
	data, out = core
	assert out['udunits'] == [catalog.udunits(u) for u in UNITS]
	c = out['constants']
	assert c['UDUNITS'] == catalog.UDUNITS
	assert c['INTERANNUAL'] == list(timeseries.INTERANNUAL)
	assert c['PROFILE_COLUMNS'] == timeseries.PROFILE_COLUMNS and c['PROFILE_META'] == timeseries.PROFILE_META
	assert c['MONTH_ABBR'] == timeseries.MONTH_ABBR == charts.MONTH_LABELS
	assert c['MONTH_STARTS'] == charts.MONTH_STARTS


# The panel of the app (the harness PANEL of test_themes, driven as a user would) ---------------------------------

STEPS = r"""
var out = {}, csv = [], answers = [];
// the rows of the CSV of a profile: the properties of each ee.Feature with a step of the year (part)
var realEe = global.ee;
global.ee = new Proxy({}, {get: function (t, p) {
	if (p !== 'Feature') return realEe[p];
	return function (g, props) {
		if (props && props.part !== undefined) csv.push(props);
		return realEe.Feature(g, props);
	};
}});
// the series of each variable, in the order they are asked for (that of the left axis, then that of the right one)
function serve(lists) {
	answers = lists.map(function (rows) { return rows.map(function (r) { return {properties: r}; }); });
	answer = {get features() { return answers.shift(); }};
}
function rowSelect(label) {  // the select after the label LABEL in its row
	return find(controls, 'Panel', function (w) {
		return w.children.length > 1 && w.children[0].kind === 'Label' && w.children[0].opts.value === label;
	})[0].children[1];
}
function compute(lists, label) {
	serve(lists);
	button(label || 'Compute the time series').opts.onClick();
	var charts = find(results, 'Chart').map(function (c) {
		var o = c.opts.options;
		return {type: c.opts.type, title: o.title, cols: c.opts.table.cols, rows: c.opts.table.rows, series: o.series,
			vAxes: o.vAxes, hAxis: o.hAxis};
	});
	var said = texts(results).slice(1);
	csv = [];
	var b = find(results, 'Button', function (w) { return w.opts.label === 'Download CSV'; })[0];
	if (b) b.opts.onClick();
	return {charts: charts, texts: said, csv: csv, file: files[files.length - 1]};
}
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 2};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
textbox(function (w) { return w.opts.value === '2025-01-01'; }).opts.onChange('2021-01-01');
textbox(function (w) { return w.opts.value === '2025-12-31'; }).opts.onChange('2024-12-31');
// the NDSI of Sentinel-2, then the options by day of the year
selectWith('vegetation').opts.onChange('snow');
selectWith(8).opts.onChange(8);
out.before = {between: Boolean(selectWith('years')), others: Boolean(selectWith('none'))};
check('A line per year, over the days of the year').opts.onChange(true);
out.options = {between: selectWith('years').opts.items, value: selectWith('years').opts.value,
	others: selectWith('none').opts.items.map(function (i) { return i.value; }), other: selectWith('none').opts.value,
	label: rowSelect('Metric between years') === selectWith('years')};
// the NDVI of Sentinel-2 on the right axis: the median of the years instead of a line per year
selectWith('none').opts.onChange(27);
out.afterOther = selectWith('years').opts.value;
selectWith('years').opts.onChange('p25');
out.p25 = compute([input.first, input.other]);
// the coefficient of variation, in %
selectWith('years').opts.onChange('cv');
out.cv = compute([input.first, input.other]);
// the NDSI of MODIS on the right axis (the NDSI snow cover, 0-100)
selectWith('years').opts.onChange('median');
selectWith('none').opts.onChange(6);
out.modis = compute([input.first, input.modis]);
// one variable: the profile on one axis
selectWith('none').opts.onChange('none');
selectWith('years').opts.onChange('mean');
out.one = compute([input.first]);
// a line per year leaves the right axis out
selectWith('none').opts.onChange(27);
selectWith('years').opts.onChange('years');
out.lines = {other: selectWith('none').opts.value, chart: compute([input.first]).charts[0]};
// the errors: the same variable on both axes, the only metric of the SCF on the right axis
selectWith('none').opts.onChange(8);
out.same = compute([input.first, input.first]).texts;
selectWith('none').opts.onChange(105);
rowSelect('Metric of each step').opts.onChange('median');
out.scf = compute([input.first, input.first]).texts;
rowSelect('Metric of each step').opts.onChange('mean');
// 16-day steps in a season that crosses the new year, from 1 November
check('Only this season of each year (MM-DD)').opts.onChange(true);
textbox(function (w) { return w.opts.value === '06-01'; }).opts.onChange('11-01');
textbox(function (w) { return w.opts.value === '08-31'; }).opts.onChange('03-31');
selectWith('daily').opts.onChange('16-day');
selectWith('none').opts.onChange(27);
selectWith('years').opts.onChange('mean');
out.winter = compute([input.winter, input.winterOther]);
// the pixel filters of each axis: the NDSI on the left (its snow filter unchecked) and the NDVI on the right, then the
// NDVI on the left (its snow filter checked) and the NDSI on the right: the NDSI keeps its snow, the NDVI never does
var qualities = [], seriesOf = MonitorEO.series;
MonitorEO.series = function (s) {
	qualities.push(JSON.parse(JSON.stringify(s.quality)));
	return seriesOf.apply(null, arguments);
};
var ndsiLeft = compute([input.winter, input.winterOther]);
out.ndsiLeft = {qualities: qualities.splice(0), csv: ndsiLeft.csv.length};
selectWith('snow').opts.onChange('vegetation');
selectWith(27).opts.onChange(27);
selectWith('none').opts.onChange(8);
var ndviLeft = compute([input.winter, input.winterOther]);
out.ndviLeft = {qualities: qualities.splice(0), csv: ndviLeft.csv.length, texts: texts(controls)};
// the CF of Sentinel-2 on the left axis (its filters greyed out, none on) and the NDVI on the right one: the NDVI with
// the filters chosen before the CF, not with those of the CF
selectWith('vegetation').opts.onChange('atmosphere');
selectWith(110).opts.onChange(110);
selectWith('none').opts.onChange(27);
var cf = compute([input.winter, input.winterOther]);
out.cf = {qualities: qualities.splice(0), csv: cf.csv.length, texts: texts(controls)};
// the SCF of Landsat on the left axis right after the NDSI of Landsat (the first of the theme Snow, its snow filter
// unchecked only because it measures it) and the NDVI of Landsat on the right one: the NDVI without the snow
selectWith('atmosphere').opts.onChange('snow');
out.afterNdsi = {snow: check('snow').opts.value};
selectWith(105).opts.onChange(105);
selectWith('none').opts.onChange(24);
compute([input.winter, input.winterOther]);
out.afterNdsi.qualities = qualities.splice(0);
MonitorEO.series = seriesOf;
selectWith('snow').opts.onChange('vegetation');
selectWith(27).opts.onChange(27);
selectWith('none').opts.onChange(8);
// in Spanish
button('Español').opts.onClick();
out.es = {between: selectWith('years').opts.items, chart: compute([input.winterOther, input.winter],
	'Calcular la serie temporal').charts[0]};
console.log(JSON.stringify(out));
"""


def _app_profile(parts, names, spec, step, interannual, meta):
	"""What the app gives for the series PARTS of the variables NAMES: the CSV of services.time_series of the profile."""
	rows = [dict(r, variable=n) for n, p in zip(names, parts) for r in timeseries.with_doy([dict(r) for r in p])]
	prof = timeseries.doy_profile(rows, spec, step, interannual, names[0])
	return [dict({k: '' if r[k] is None else r[k] for k in timeseries.PROFILE_COLUMNS},
	             **dict(meta[r['variable']], step=step, metric='mean', stat='mean', interannual=interannual))
	        for r in prof]


def test_the_app_draws_the_profile_of_two_indices_on_two_axes():
	from test_themes import PANEL, _build, _ui_texts
	with open(os.path.join(GEE, 'ui.js'), encoding='utf-8') as f:
		ui = f.read()
	en, es = _ui_texts(ui, 'en'), _ui_texts(ui, 'es')
	monthly = _dates(['2021-01-01', '2024-12-31'], None, 'monthly')
	first, other, modis = (_rows(monthly, ['Granada', 'Almeria'], k) for k in (11, 12, 13))
	for r in other:  # a month without the NDVI in any year
		if r['region'] == 'Granada' and r['date'][5:7] == '02':
			r['value'] = None
	winter = {'period': ['2021-01-01', '2024-12-31'], 'season': ['11-01', '03-31']}
	days = _dates(winter['period'], winter['season'], '16-day')
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {},
	        'first': first, 'other': other, 'modis': modis, 'winter': _rows(days, ['Map view'], 14),
	        'winterOther': _rows(days, ['Map view'], 15)}
	out = _node(PANEL[:PANEL.index('var out = {};')] + STEPS, data)
	# the options appear with the chart by day of the year: a line per year by default, no variable on the right
	assert out['before'] == {'between': False, 'others': False}
	opts = out['options']
	assert [i['value'] for i in opts['between']] == ['years', 'mean', 'median', 'min', 'max', 'p25', 'p75', 'std', 'cv']
	assert opts['between'][0]['label'] == en['doyLines'] and opts['value'] == 'years' and opts['label']
	dated = {e['ref'] for e in catalog.variables() if not e.get('static') and not e.get('two_periods')}
	assert opts['others'][0] == 'none' and set(opts['others'][1:]) == dated and opts['other'] == 'none'
	assert out['afterOther'] == 'median'
	# NDSI and NDVI of Sentinel-2, the percentile 25 of the years: a chart for each feature, two axes, each from the
	# values of its own variable (no viewWindow)
	names = ['NDSI Sentinel-2', 'NDVI Sentinel-2']
	meta = {n: {'sensor': 'Sentinel-2', 'unit': '1', 'scale_m': 10} for n in names}
	p25 = out['p25']
	assert p25['csv'] == _app_profile([first, other], names, None, 'monthly', 'p25', meta)
	assert list(p25['csv'][0]) == timeseries.PROFILE_COLUMNS + timeseries.PROFILE_META
	almeria, granada = p25['charts']
	assert almeria['title'] == 'NDSI Sentinel-2 and NDVI Sentinel-2 · Map view · Mean monthly · mean · ' \
	                           'percentile 25 of the years · Almeria' and granada['title'].endswith(' · Granada')
	assert [c['label'] for c in almeria['cols']] == ['Day of the year'] + names
	profile = [r for r in p25['csv'] if r['region'] == 'Granada']
	assert [[c['v'] for c in r['c']] for r in granada['rows']] == \
		[[r['doy'], r['value'] if r['value'] != '' else None, s['value'] if s['value'] != '' else None]
		 for r, s in zip(profile[:12], profile[12:])]
	assert [r['c'][0]['f'] for r in granada['rows']] == timeseries.MONTH_ABBR
	assert granada['rows'][1]['c'][2]['v'] is None  # February without the NDVI in any year
	assert almeria['series'] == {'0': {'targetAxisIndex': 0, 'color': '#1f77b4'},
	                             '1': {'targetAxisIndex': 1, 'color': '#d62728'}}
	for k, colour in (('0', '#1f77b4'), ('1', '#d62728')):
		assert almeria['vAxes'][k] == {'title': '[unitless]', 'titleTextStyle': {'color': colour},
		                               'textStyle': {'color': colour}}
	assert almeria['hAxis']['viewWindow'] == {'min': 1, 'max': 366}
	assert almeria['hAxis']['ticks'] == [{'v': d, 'f': m} for d, m in zip(charts.MONTH_STARTS, timeseries.MONTH_ABBR)]
	assert p25['texts'][0].startswith('Each point: percentile 25 of the values of that step of the year')
	assert p25['texts'][1].startswith('Computed on pixels of 10 m (NDSI Sentinel-2) and of 10 m (NDVI Sentinel-2).')
	assert p25['file'].startswith('NDSI_Sentinel-2_and_NDVI_Sentinel-2_Map_view_Mean_monthly_mean_percentile_25')
	# the coefficient of variation between the years: in %
	cv = out['cv']
	assert cv['csv'] == _app_profile([first, other], names, None, 'monthly', 'cv',
	                                 {n: dict(meta[n], unit='%') for n in names})
	assert cv['charts'][0]['vAxes']['0'] == {'title': 'Coefficient of variation [%]',
	                                         'titleTextStyle': {'color': '#1f77b4'}, 'textStyle': {'color': '#1f77b4'}}
	# the NDSI of MODIS on the right axis: the NDSI snow cover, 0-100, from the data; its own pixels
	modis = out['modis']
	want = _app_profile([first, data['modis']], ['NDSI Sentinel-2', 'NDSI Modis'], None, 'monthly', 'median',
	                    {'NDSI Sentinel-2': meta['NDSI Sentinel-2'],
	                     'NDSI Modis': {'sensor': 'Modis', 'unit': '1', 'scale_m': 500}})
	assert modis['csv'] == want
	axes = modis['charts'][0]['vAxes']
	assert 'viewWindow' not in axes['0'] and 'viewWindow' not in axes['1']
	assert modis['texts'][1].startswith('Computed on pixels of 10 m (NDSI Sentinel-2) and of 500 m (NDSI Modis).')
	# one variable: one axis, still the profile (the mean of the years)
	one = out['one']
	assert one['csv'] == _app_profile([first], ['NDSI Sentinel-2'], None, 'monthly', 'mean', meta)
	chart = one['charts'][0]
	assert [c['label'] for c in chart['cols']] == ['Day of the year', 'NDSI Sentinel-2']
	assert list(chart['vAxes']) == ['0'] and chart['vAxes']['0'] == {'title': '[unitless]'}
	assert one['texts'][1].startswith('Computed on pixels of 10 m.')
	# a line per year again: of one variable, as before
	assert out['lines']['other'] == 'none' and out['lines']['chart']['type'] == 'LineChart'
	assert 'vAxes' not in out['lines']['chart'] and out['lines']['chart']['title'].endswith(' · Almeria')
	# the errors, before Earth Engine
	assert out['same'] == [en['sameOther'].replace('%s', 'NDSI Sentinel-2')]
	scf, = out['scf']
	assert scf.startswith('Right axis: SCF (') and "only takes the metric 'mean'" in scf
	# 16-day steps in a season from 1 November: the steps counted from the first day of the season
	winter_csv = out['winter']['csv']
	assert winter_csv == _app_profile([data['winter'], data['winterOther']], names, winter, '16-day', 'mean', meta)
	assert [r['label'] for r in winter_csv if r['part'] == '0'] == ['Nov 1', 'Nov 1']  # of both variables
	# the pixel filters of each axis: the snow filter unchecked by the NDSI still removes the snow of the NDVI on the
	# other axis, and that of the NDVI never removes the snow that the NDSI measures; no note of a conflict
	ndsi_quality, ndvi_quality = out['ndsiLeft']['qualities']
	assert not ndsi_quality['snow'] and ndvi_quality['snow'] and out['ndsiLeft']['csv']
	ndvi_quality, ndsi_quality = out['ndviLeft']['qualities']
	assert ndvi_quality['snow'] and not ndsi_quality['snow'] and out['ndviLeft']['csv']
	assert not [x for x in out['ndviLeft']['texts'] if 'removes what' in x]
	# the CF on the left axis: its fixed filters (none) for it, those chosen before it (all, of the NDVI) for the NDVI
	cf_quality, ndvi_quality = out['cf']['qualities']
	assert not any(cf_quality[f] for f in ('clouds', 'water', 'snow', 'aerosols'))
	assert all(ndvi_quality[f] for f in ('clouds', 'water', 'snow')) and out['cf']['csv']  # no aerosols in Sentinel-2
	assert not [x for x in out['cf']['texts'] if 'removes what' in x]
	# the SCF right after the NDSI (the first variable of the theme Snow, which unchecked the snow filter): the NDVI on
	# the right axis still without the snow, as in the QGIS plugin
	scf_quality, ndvi_quality = out['afterNdsi']['qualities']
	assert out['afterNdsi']['snow'] is False and scf_quality['snow'] is False  # the fixed filters of the SCF
	assert ndvi_quality['snow'] and ndvi_quality['clouds'], ndvi_quality
	# in Spanish: the options and the names of the steps of the year
	assert out['es']['between'][0]['label'] == es['doyLines'] and out['es']['between'][2]['label'] == 'Mediana'
	chart = out['es']['chart']
	steps = {r['c'][0]['v']: r['c'][0]['f'] for r in chart['rows']}
	assert steps[305] == '1 nov' and chart['hAxis']['ticks'][0] == {'v': 1, 'f': 'ene'}
	assert chart['cols'][0]['label'] == es['dayOfYear']
	# one feature: not named again after the region
	assert chart['title'] == 'NDVI Sentinel-2 y NDSI Sentinel-2 · Map view · Media 16 días · media · media de los años'


def test_the_texts_of_the_profile_are_in_both_languages():
	from test_themes import _ui_texts
	with open(os.path.join(GEE, 'ui.js'), encoding='utf-8') as f:
		ui = f.read()
	en, es = _ui_texts(ui, 'en'), _ui_texts(ui, 'es')
	keys = ('doyLines', 'doyOther', 'noOther', 'ofTheYears', 'rightAxis', 'doyNote', 'sameOther', 'scalesNote')
	assert all(en.get(k) and es.get(k) and en[k] != es[k] for k in keys)
	for lang in ('es', 'en'):  # once in each language: a key written twice keeps only the last text
		start = ui.index(f'\t{lang}: {{')
		block = ui[start:ui.index('\ten: {') if lang == 'es' else ui.index('var METRICS')]
		assert all(len(re.findall(rf'\b{k}: ', block)) == 1 for k in keys), lang
	assert (en['doyOther'], es['doyOther']) == ('Other index (right axis)', 'Otro índice (eje derecho)')


CHART = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8')), GEE = process.argv[process.argv.length - 1];
function nothing() { return new Proxy(function () {}, {get: function () { return nothing(); }, apply: nothing}); }
global.ee = nothing();
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(GEE, f), 'utf8'), {filename: f});
});
var ui = fs.readFileSync(path.join(GEE, 'ui.js'), 'utf8');
var src = ui.slice(ui.indexOf('\tfunction stepName(r)'), ui.indexOf('\t// Whether the series by day of the year is its'));
var table = null;
var chart = new Function('mo', 'state', 't', 'partName', 'ui', 'PROFILE_COLOURS', src + '; return profileChart;')(
	MonitorEO, {lang: 'en'}, function (k) { return k; }, function (s, i) { return String(i); },
	{Chart: function (data) { table = data; }}, ['#1f77b4', '#d62728']);
chart(input.profile, ['NDSI Modis'], [{title: 'NDSI', ylim: null}], 'x', 'park', false);
process.stdout.write(JSON.stringify(table.rows));
"""


def test_the_chart_keeps_every_step_of_the_year():
	"""A point per step of the year of the profile, also for two steps on the same day (one without a value): none
	takes the value of the other, as in the CSV."""
	profile = [{'region': 'park', 'variable': 'NDSI Modis', 'part': p, 'doy': d, 'label': l, 'value': v, 'n_years': n}
	           for p, d, l, v, n in (('02-28', 59, 'Feb 28', 50.0, 3), ('02-29', 60, 'Feb 29', 90.0, 1),
	                                 ('03-01', 60, 'Mar 1', None, 0), ('03-02', 62, 'Mar 2', 20.0, 3))]
	rows = _node(CHART, {'profile': profile})
	assert [[c.get('f', c['v']) for c in r['c']] for r in rows] == [
		['Feb 28', 50.0], ['Feb 29', 90.0], ['Mar 1', None], ['Mar 2', 20.0]]
	assert [r['c'][0]['v'] for r in rows] == [59, 60, 60, 62]
