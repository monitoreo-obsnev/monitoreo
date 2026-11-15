"""The seasonal profile by day of the year (time_series with doy and interannual or other_variable) in the viewer of
results, without Earth Engine: its chart doy_profile in report.json (publish: the variables of its CSV in the order of
the axes, their names and axis titles, the ranges of both y axes, the metric between the years, its analysis and its
variables, from the result of the services, from an answer of the MCP server or from its CSV alone; check_report) and
its Vega-Lite spec (src/monitoreo/viewer/assets/charts.js in Node: one line per variable on two independent y axes,
each from the values of its own variable unless a range is given, the region chosen, the table)."""

import datetime as dt
import json
import math
import os
import shutil
import subprocess

import pytest

from monitoreo import publish, report, services, timeseries

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
TWO = {'region': REGION, 'variable': 'NDSI', 'sensor': 'Sentinel-2', 'start': '2021-01-01', 'end': '2023-12-31',
       'step': 'monthly', 'doy': True, 'other_variable': 'NDVI'}
MODIS = dict(TWO, sensor='Modis', step='16-day', interannual='p75', other_sensor='Sentinel-2', other_ylim=[0, 0.8])
ONE = {'region': REGION, 'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2021-01-01', 'end': '2023-12-31',
       'step': 'monthly', 'doy': True, 'interannual': 'cv'}
CHARTS_JS = os.path.join(os.path.dirname(publish.__file__), 'viewer', 'assets', 'charts.js')


@pytest.fixture
def series(monkeypatch):
	"""time_series without Earth Engine: a value per step and region (park and buffer) of each variable, the NDSI high
	in winter and the NDVI in summer (the NDSI snow cover of MODIS, 0-100)."""

	def fake(spec, regions, step='monthly', metric='mean', stat='mean', scale=None, progress=None, steps=None):
		rows = []
		for a, _ in timeseries.bins(spec, step):
			day = dt.date.fromisoformat(a)
			winter = math.cos(2 * math.pi * (day.month - 1) / 12)
			v = {'NDSI': winter / 2, 'NDVI': 0.3 - winter / 4}[spec['index']] + (day.year - 2021) / 100
			v = v * 100 if spec.get('sensor') == 'Modis' else v
			rows += [{'region': g, 'date': a, 'value': None if a.startswith('2022-02') else v, 'n_pixels': 5,
			          'n_images': 1} for g in ('park', 'buffer')]
		rows.sort(key=lambda r: (r['region'], r['date']))
		return rows, scale or (500.0 if spec.get('sensor') == 'Modis' else 10.0)

	monkeypatch.setattr(services.areas, 'region', lambda region: 'regions')
	monkeypatch.setattr(services.timeseries, 'series', fake)
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)


def _publish(tmp_path, items, rid='profile'):
	"""report.json of a report with the results ITEMS (written in TMP_PATH/RID), and its problems."""
	spec = {'title': 'Snow and greenness', 'summary': 'The seasons', 'region': {'name': 'Sierra Nevada'}, 'results': items}
	folder = tmp_path / rid
	folder.mkdir()
	rep = publish.build(spec, rid, str(tmp_path), [], None, str(folder))
	return rep, publish.check_report(rep, str(folder))


def _call(tmp_path, args, name):
	"""The result of time_series with ARGS (without its yearly rows, as the log of the MCP server keeps it)."""
	res = services.time_series(csv=str(tmp_path / f'{name}.csv'), **args)
	return {k: v for k, v in res.items() if k != 'rows'}


# report.json --------------------------------------------------------------------------------------------------------

def test_two_indices_on_two_axes_in_the_report(series, tmp_path):
	rep, problems = _publish(tmp_path, [{'tool': 'time_series', 'args': TWO, 'result': _call(tmp_path, TWO, 'two')}])
	assert problems == []
	r = rep['results'][0]
	assert r['chart'] == 'doy_profile' and r['title'] == report.profile_title(TWO) == (
		'Monthly profile of NDSI (Sentinel-2) and NDVI (Sentinel-2) by day of the year, 2021-2023: median of the years')
	assert r['variables'] == ['NDSI Sentinel-2', 'NDVI Sentinel-2']  # as the column variable of its CSV
	assert r['labels'] == ['NDSI (Sentinel-2)', 'NDVI (Sentinel-2)']
	assert (r['ylabel'], r['other_ylabel']) == ('NDSI (Sentinel-2)', 'NDVI (Sentinel-2)')  # unitless: no unit
	assert r['ylim'] is None and r['other_ylim'] is None and r['interannual'] == 'median'  # each from its values
	with open(tmp_path / 'profile' / r['csv'], encoding='utf-8') as f:
		assert f.readline().strip().split(',') == timeseries.PROFILE_COLUMNS + timeseries.PROFILE_META
	assert rep['analyses'] == [{'id': 'profile', 'name': 'Seasonal profile'}]
	assert [(v['variable'], v['sensor']) for v in rep['variables']] == [('NDSI', 'Sentinel-2'), ('NDVI', 'Sentinel-2')]
	cat = publish.update_catalog(str(tmp_path / 'site'))  # the name of the analysis in the catalogue
	assert cat['analyses']['profile'] == 'Seasonal profile'


def test_the_axes_of_the_snow_cover_of_modis_and_of_one_index(series, tmp_path):
	rep, problems = _publish(tmp_path, [{'tool': 'time_series', 'args': MODIS, 'result': _call(tmp_path, MODIS, 'm')},
	                                    {'tool': 'time_series', 'args': ONE, 'result': _call(tmp_path, ONE, 'one')}])
	assert problems == []
	modis, one = rep['results']
	assert modis['variables'] == ['NDSI Modis', 'NDVI Sentinel-2'] and modis['labels'] == ['NDSI (MODIS)',
	                                                                                        'NDVI (Sentinel-2)']
	assert modis['ylim'] is None and modis['other_ylim'] == [0.0, 0.8]  # 0-100: from the data; the one given
	assert modis['interannual'] == 'p75' and modis['title'].endswith(': percentile 75 of the years')
	assert one['variables'] == ['NDVI Sentinel-2'] and one['other_ylabel'] is None and one['other_ylim'] is None
	assert one['ylabel'] == 'NDVI (Sentinel-2) [%]' and one['ylim'] is None  # the coefficient of variation, in %
	assert [(v['variable'], v['sensor']) for v in rep['variables']] == [('NDSI', 'MODIS'), ('NDVI', 'Sentinel-2')]


def test_an_answer_of_the_mcp_server_and_a_csv_without_its_call(series, tmp_path):
	"""The answer of the MCP server may not have the names, units and ranges of the axes: from the call (the ranges
	given, else none, and the unit of the catalog) and the CSV; a CSV alone is drawn as a profile by its columns."""
	args = dict(TWO, interannual='p25')
	res = _call(tmp_path, args, 'two')
	answer = {'csv': res['csv'], 'unit': res['unit'], 'title': res['title']}
	alone = tmp_path / 'alone.csv'
	shutil.copyfile(res['csv'], alone)
	rep, problems = _publish(tmp_path, [{'tool': 'time_series', 'args': args, 'result': answer}, {'file': str(alone)}])
	assert problems == []
	mcp, csv = rep['results']
	assert {k: mcp[k] for k in ('chart', 'variables', 'labels', 'ylabel', 'other_ylabel', 'ylim', 'other_ylim',
	                            'interannual')} == {
		'chart': 'doy_profile', 'variables': ['NDSI Sentinel-2', 'NDVI Sentinel-2'],
		'labels': ['NDSI (Sentinel-2)', 'NDVI (Sentinel-2)'], 'ylabel': 'NDSI (Sentinel-2)',
		'other_ylabel': 'NDVI (Sentinel-2)', 'ylim': None, 'other_ylim': None, 'interannual': 'p25'}
	given = _publish(tmp_path, [{'tool': 'time_series', 'args': dict(args, other_ylim='0, 0.8'),
	                             'result': answer}], 'call')[0]['results'][0]
	assert (given['ylim'], given['other_ylim']) == (None, [0.0, 0.8])  # the range of the call
	assert csv['chart'] == 'doy_profile' and csv['labels'] == csv['variables'] == mcp['variables']
	assert csv['interannual'] == 'p25' and csv['ylabel'] == 'NDSI Sentinel-2'  # from its CSV
	assert csv['ylim'] is None and csv['other_ylim'] is None  # without its call: from the data
	answer = dict(answer, units={'NDSI Sentinel-2': '[°C]', 'NDVI Sentinel-2': '[%]'}, ylim=[-2, 2], other_ylim=None)
	r = _publish(tmp_path, [{'tool': 'time_series', 'args': args, 'result': answer}], 'given')[0]['results'][0]
	assert (r['ylabel'], r['other_ylabel'], r['ylim'], r['other_ylim']) == (
		'NDSI (Sentinel-2) [°C]', 'NDVI (Sentinel-2) [%]', [-2.0, 2.0], None)  # those of the result


def test_a_line_per_year_keeps_its_chart_and_takes_a_range(series, tmp_path):
	args = {k: v for k, v in TWO.items() if k != 'other_variable'}
	given = dict(args, ylim=[-0.5, 1])
	rep, problems = _publish(tmp_path, [{'tool': 'time_series', 'args': args, 'result': _call(tmp_path, args, 'a')},
	                                    {'tool': 'time_series', 'args': given, 'result': _call(tmp_path, given, 'b')}])
	assert problems == []
	assert [(r['chart'], r['ylim']) for r in rep['results']] == [('doy', None), ('doy', [-0.5, 1.0])]
	assert 'variables' not in rep['results'][0] and rep['analyses'] == [{'id': 'series', 'name': 'Time series'}]


def test_the_problems_of_the_axes(series, tmp_path):
	rep, _ = _publish(tmp_path, [{'tool': 'time_series', 'args': TWO, 'result': _call(tmp_path, TWO, 'two')}])
	r = rep['results'][0]

	def problems(**change):
		return publish.check_report(dict(rep, results=[dict(r, **change)]))

	assert problems() == []
	assert problems(ylim=[1, -1]) == ['result r1: ylim is [min, max] of the y axis, or null']
	assert problems(other_ylim=[0, 'a']) == ['result r1: other_ylim is [min, max] of the y axis, or null']
	assert problems(ylim=[0, float('nan')]) and problems(ylim=[True, 2]) and problems(ylim=[0, 1, 2])
	assert problems(variables=[]) == ['result r1: variables is a list of one or two names']
	assert problems(labels=['NDSI']) == ['result r1: labels has a name for each variable']
	assert problems(other_ylabel='') == ['result r1: other_ylabel is the title of the axis of NDVI Sentinel-2']
	one = dict(variables=['NDSI Sentinel-2'], labels=['NDSI (Sentinel-2)'])
	assert problems(**one) == ['result r1: other_ylabel and other_ylim are those of a second variable']
	assert problems(**one, other_ylabel=None, other_ylim=None) == []
	assert publish.check_report(dict(rep, results=[dict(r, chart='doy', ylim='-1, 1')])) == [
		'result r1: ylim is [min, max] of the y axis, or null']


# The viewer (charts.js in Node) -------------------------------------------------------------------------------------

# A document that draws nothing (each element with its attributes and children), the CSV of input.csv and the specs
# given to vegaEmbed: those of the chart of input.result, of each region chosen in input.regions, and its table
VIEWER = r"""
var fs = require('fs'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8')), specs = [];
function el(tag, attrs) {
	var node = {tag: tag, attrs: attrs || {}, children: [], clientWidth: 800};
	node.append = function () {
		[].slice.call(arguments).flat(Infinity).forEach(function (c) { node.children.push(c); });
	};
	node.replaceChildren = function () { node.children = []; node.append.apply(node, arguments); };
	node.append.apply(node, [].slice.call(arguments, 2));
	return node;
}
var CSS = {'--series-1': '#2a78d6', '--series-other': '#e34948', '--baseline': '#cccccc'};
global.MO = {el: el, css: function (v) { return CSS[v] || ''; }, text: async function () { return input.csv; },
	MONTHS: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], num: String,
	round: String, pValue: String, safePath: Boolean};
global.window = {matchMedia: function () { return {addEventListener: function () {}}; }};
global.document = {documentElement: {}};
global.getComputedStyle = function () { return {colorScheme: 'light'}; };
global.vega = {read: function (text) {  // a CSV without quotes
	var lines = text.trim().split(/\r?\n/), head = lines[0].split(',');
	return lines.slice(1).map(function (l) {
		var r = {};
		l.split(',').forEach(function (v, i) { r[head[i]] = v; });
		return r;
	});
}};
global.vegaEmbed = async function (box, spec) { specs.push(JSON.parse(JSON.stringify(spec))); return {}; };
vm.runInThisContext(fs.readFileSync(process.argv[process.argv.length - 1], 'utf8'), {filename: 'charts.js'});
function all(node, out) {
	out = out || [];
	if (node && typeof node === 'object') {
		out.push(node);
		(node.children || []).forEach(function (c) { all(c, out); });
	}
	return out;
}
(async function () {
	var container = el('div');
	var drawn = await MO.chart.render(container, input.result, '');
	var select = all(container).filter(function (n) { return n.tag === 'select'; })[0];
	var options = select ? select.children.map(function (o) { return o.attrs.value; }) : [];
	for (var i = 0; i < (input.regions || []).length; i++) {
		await select.attrs.onchange({target: {value: input.regions[i]}});
	}
	var table = all(drawn.table()), text = function (n) { return n.children.join(''); };
	process.stdout.write(JSON.stringify({specs: specs, options: options,
		heads: table.filter(function (n) { return n.tag === 'th'; }).map(text),
		cells: table.filter(function (n) { return n.tag === 'td'; }).slice(0, 6).map(text)}));
})().catch(function (e) { console.error(e.stack || e); process.exit(1); });
"""


def _viewer(tmp_path, args, name, regions=()):
	"""The chart of the profile of ARGS (a result of report.json, as published) in the viewer of results: its specs,
	the regions of its selector and its table."""
	rep, problems = _publish(tmp_path, [{'tool': 'time_series', 'args': args, 'result': _call(tmp_path, args, name)}],
	                         name)
	assert problems == []
	result = rep['results'][0]
	with open(tmp_path / name / result['csv'], encoding='utf-8') as f:
		csv = f.read()
	run = subprocess.run(['node', '-e', VIEWER, CHARTS_JS], capture_output=True, text=True, timeout=60,
	                     input=json.dumps({'result': result, 'csv': csv, 'regions': list(regions)}))
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout)


def _layers(group):
	"""{mark type: layer} of the layers of an axis of the spec of a profile."""
	return {layer['mark']['type']: layer for layer in group['layer']}


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_viewer_draws_two_indices_on_two_axes(series, tmp_path):
	out = _viewer(tmp_path, TWO, 'two', ['park'])
	assert out['options'] == ['buffer', 'park']  # the region chosen, as the other charts
	first, park = out['specs']
	assert {r['region'] for r in first['data']['values']} == {'buffer'}
	assert {r['region'] for r in park['data']['values']} == {'park'}
	assert first['resolve'] == {'scale': {'y': 'independent'}} and len(first['layer']) == 2
	left, right = (_layers(g) for g in first['layer'])
	for layers, name, title, orient, colour in ((left, 'NDSI Sentinel-2', 'NDSI (Sentinel-2)', 'left', '#2a78d6'),
	                                            (right, 'NDVI Sentinel-2', 'NDVI (Sentinel-2)', 'right', '#e34948')):
		line, point = layers['line'], layers['point']
		assert line['transform'] == point['transform'] == [{'filter': {'field': 'variable', 'equal': name}}]
		y = line['encoding']['y']
		assert y['field'] == 'value' and y['title'] == title
		assert y['scale'] == {'zero': False} and line['mark']['clip'] is False  # from its values, not from 0
		assert 'domain' not in y['scale']
		assert y['axis']['orient'] == orient and y['axis']['titleColor'] == y['axis']['labelColor'] == colour
		x = line['encoding']['x']
		assert x['field'] == 'doy' and x['scale']['domain'] == [1, 366] and x['axis']['values'][:3] == [1, 32, 60]
		assert '"Jan"' in x['axis']['labelExpr'] and 'indexof' in x['axis']['labelExpr']
		assert [t['title'] for t in point['encoding']['tooltip']][:3] == ['Step of the year', 'Variable',
		                                                                  'Value (median of the years)']
	colour = left['line']['encoding']['color']
	assert colour['scale'] == {'domain': ['NDSI (Sentinel-2)', 'NDVI (Sentinel-2)'], 'range': ['#2a78d6', '#e34948']}
	assert colour['legend'] is not None  # both names
	# a line at 0 on the left axis only: the NDSI goes from -0.5 to 0.5, the NDVI from 0.05 to 0.57, without 0
	assert left['rule']['encoding']['y']['datum'] == 0 and 'rule' not in right
	jan = [r for r in first['data']['values'] if r['variable'] == 'NDSI Sentinel-2'][0]
	assert (jan['label'], jan['doy'], jan['n_years'], jan['serie']) == ('Jan', 1, 3, 'NDSI (Sentinel-2)')
	assert jan['value'] == pytest.approx(0.51)  # the median of 0.5, 0.51 and 0.52
	assert out['heads'] == ['Region', 'Variable', 'Step of the year', 'Day of the year', 'Value', 'Years']
	assert out['cells'][:4] == ['buffer', 'NDSI Sentinel-2', 'Jan', '1'] and out['cells'][5] == '3'


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_viewer_draws_the_axes_of_their_ranges(series, tmp_path):
	"""The NDSI snow cover of MODIS (0-100) from the data, with its line at 0, and the NDVI from 0 to 0.8 (given), whose
	0 is not inside; one index alone: one axis, without a legend."""
	spec = _viewer(tmp_path, MODIS, 'modis')['specs'][0]
	left, right = (_layers(g) for g in spec['layer'])
	assert left['line']['encoding']['y']['scale'] == {'zero': False} and left['line']['mark']['clip'] is False
	assert right['line']['encoding']['y']['scale'] == {'domain': [0, 0.8], 'nice': False, 'zero': False}
	assert 'rule' in left and 'rule' not in right
	assert left['point']['encoding']['tooltip'][2]['title'] == 'Value (percentile 75 of the years)'
	assert [(r['label'], r['doy']) for r in spec['data']['values'][:2]] == [('Jan 1', 1), ('Jan 17', 17)]
	spec = _viewer(tmp_path, ONE, 'one')['specs'][0]
	assert 'resolve' not in spec and spec['layer'][0]['mark']['type'] == 'line'  # one axis: no line at 0 (cv, %)
	layers = _layers(spec)
	y = layers['line']['encoding']['y']
	assert y['title'] == 'NDVI (Sentinel-2) [%]' and y['axis'] == {'orient': 'left', 'grid': True}
	assert layers['line']['encoding']['color']['legend'] is None
	assert layers['point']['encoding']['tooltip'][2]['title'] == 'Value (coefficient of variation of the years)'


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_viewer_draws_a_line_per_year_with_its_range(series, tmp_path):
	args = dict({k: v for k, v in TWO.items() if k != 'other_variable'}, ylim=[-1, 1])
	spec = _viewer(tmp_path, args, 'doy')['specs'][0]
	assert spec['encoding']['y']['scale'] == {'domain': [-1, 1], 'nice': False, 'zero': False}
	assert spec['mark']['clip'] is True and spec['encoding']['color']['field'] == 'year'
	args.pop('ylim')
	spec = _viewer(tmp_path, args, 'doy2')['specs'][0]
	assert spec['encoding']['y']['scale'] == {'zero': False} and spec['mark']['clip'] is False
