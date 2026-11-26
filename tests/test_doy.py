"""Time series with a line per year over the days of the year (time_series with doy, as the day-of-year charts of
geemap), without Earth Engine: the days of the year, the error with an annual step, the chart, the README, the report,
the viewer of results, the command line, the MCP server, the assistant and the Earth Engine app (gee/ui.js in Node)."""

import json
import os
import shutil
import subprocess

import pytest

from monitoreo import catalog, readme, report, services, timeseries

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
ARGS = {'region': REGION, 'variable': 'NDSI', 'sensor': 'Modis', 'start': '2019-01-01', 'end': '2024-12-31',
        'step': '16-day', 'doy': True}


def _rows():
	return timeseries.with_doy([{'region': 'park', 'date': f'{y}-{m:02d}-01', 'value': float(m), 'n_pixels': 5,
	                             'n_images': 2} for y in (2023, 2024) for m in (1, 3, 12)])


def test_the_days_of_the_year():
	rows = _rows()
	assert [(r['year'], r['doy']) for r in rows] == [(2023, 1), (2023, 60), (2023, 335), (2024, 1), (2024, 61),
	                                                 (2024, 336)]
	with pytest.raises(ValueError, match='needs a step shorter than a year'):
		services.time_series(REGION, 'NDVI', 'Modis', '2020-01-01', '2021-12-31', step='annual', doy=True)


def test_the_chart_by_day_of_the_year(tmp_path):
	pytest.importorskip('matplotlib')
	from monitoreo import charts
	png = charts.doy_png(_rows(), str(tmp_path / 'doy.png'), 'NDSI', 'NDSI')
	assert png[:8] == b'\x89PNG\r\n\x1a\n'


def test_the_readme_the_report_and_the_viewer(tmp_path):
	from monitoreo import publish
	csv = tmp_path / 'series.csv'
	timeseries.write_csv(_rows(), str(csv), {}, timeseries.COLUMNS + ['year', 'doy'])
	result = {'rows': _rows(), 'csv': str(csv), 'unit': '[unitless]', 'ylabel': 'NDSI', 'title': 'NDSI', 'scale': 500.0}
	text = ' '.join(readme.text('time_series', ARGS, result, computed='2026-11-14T10:00:00+01:00').split())
	assert 'doy: day of the year (1-366) of the first day of the step' in text
	assert 'year: year of the first day of the step' in text
	assert 'Chart: a line per year over the days of the year' in text
	assert 'Wu, Q. (2020). geemap' in text  # the day-of-year charts of geemap, cited in HOW TO CITE IT
	assert report.item_title('time_series', ARGS).endswith(', by day of the year')
	spec = {'title': 'Snow', 'summary': 'Snow', 'region': {'name': 'Sierra Nevada'},
	        'results': [{'tool': 'time_series', 'args': ARGS, 'result': result}]}
	folder = tmp_path / 'report'
	folder.mkdir()
	rep = publish.build(spec, 'snow', str(tmp_path), [], None, str(folder))
	assert rep['results'][0]['chart'] == 'doy' and rep['results'][0]['ylabel'] == 'NDSI'
	assert publish.check_report(rep, str(folder)) == []


def test_the_series_by_day_of_the_year_cites_geemap():
	from monitoreo import references
	ids = [r['id'] for r in references.cite('time_series', ARGS)['references']]
	assert 'wu2020' in ids and {'gorelick2017', 'monitoreo'} <= set(ids)
	assert 'wu2020' not in [r['id'] for r in references.cite('time_series', dict(ARGS, doy=False))['references']]


def test_the_readme_of_the_areas_keeps_the_year_of_the_map(tmp_path):
	"""The column year of the CSV of area_by_class (a land cover map, and its changes to another year) is the year of
	the map, not that of a step of a time series."""
	from monitoreo import classes
	for mode, args in (('landcover', {'region': REGION, 'landcover': 'CORINE', 'year': 2018}),
	                   ('transitions', {'region': REGION, 'landcover': 'CORINE', 'year': 2012, 'other_year': 2018})):
		csv = tmp_path / f'{mode}.csv'
		csv.write_text(','.join(classes.COLUMNS[mode]) + '\n', encoding='utf-8')
		result = {'rows': [], 'mode': mode, 'scale': 100.0, 'unit': '', 'csv': str(csv), 'title': 'Areas'}
		text = ' '.join(readme.text('area_by_class', args, result, computed='2026-11-14T10:00:00+01:00').split())
		year = 'year: first year of the land cover map' if mode == 'transitions' else 'year: year of the land cover map'
		assert year in text and 'first day of the step' not in text, mode


@pytest.fixture
def calls(monkeypatch):
	out = []

	def fake(region, variable=None, sensor=None, start=None, end=None, step='monthly', metric='mean', stat='mean',
	         season=None, quality=None, scale=None, csv=None, chart=None, progress=None, doy=False, **source):
		out.append({'doy': doy, 'step': step, 'chart': chart})
		return {'rows': _rows() if doy else [], 'csv': csv, 'chart': None, 'scale': 500.0, 'unit': '', 'ylabel': '',
		        'title': 'NDSI', 'n_steps': 6, 'regions': ['park']}
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'time_series', fake)
	return out


def test_the_command_line_the_mcp_server_and_the_assistant(calls, monkeypatch, tmp_path):
	from monitoreo import assistant, cli
	cli.main(['series', 'NDSI', '--sensor', 'Modis', '--region', json.dumps(REGION), '--start', '2019-01-01', '--end',
	          '2024-12-31', '--step', '16-day', '--doy'])
	assert calls[-1]['doy'] is True and calls[-1]['step'] == '16-day'
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	mcp_server.time_series(REGION, 'NDSI', 'Modis', start='2019-01-01', end='2024-12-31', step='16-day', doy=True)
	assert calls[-1]['doy'] is True
	assert 'doy true' in assistant.PROMPT


STEPS = r"""
var out = {};
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 2};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
check('A line per year, over the days of the year').opts.onChange(true);
// two features, each in January and July of two years
answer = {features: ['Granada', 'Almeria'].reduce(function (a, g) {
	return a.concat([[2024, 1], [2024, 7], [2025, 1], [2025, 7]].map(function (p) {
		return {properties: {region: g, date: p[0] + '-0' + p[1] + '-01', value: p[1] + (g === 'Granada' ? 0.5 : 0),
			n_pixels: 4, n_images: 1}};
	}));
}, [])};
button('Compute the time series').opts.onClick();
out.charts = find(root.children[2], 'Chart').map(function (c) {
	return {head: c.opts.table[0], rows: c.opts.table.slice(1), type: c.opts.type, title: c.opts.options.title,
		axis: c.opts.options.hAxis.title, series: c.opts.options.series};
});
features = [];  // the rows of the CSV: the ee.Feature of each
find(root.children[2], 'Button', function (w) { return w.opts.label === 'Download CSV'; })[0].opts.onClick();
out.csv = features;
console.log(JSON.stringify(out));
"""


def _luminance(colour):
	r, g, b = (int(colour.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
	return 0.299 * r + 0.587 * g + 0.114 * b


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_app_draws_a_line_per_year():
	"""A chart for each feature (not only the first), with a line per year from the oldest (light) to the newest
	(dark, thicker), and the year and the day of the year in the CSV, as the other tools."""
	from test_themes import PANEL, _build
	script = PANEL[:PANEL.index('var out = {};')] + STEPS
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {}}
	run = subprocess.run(['node', '-e', script, os.path.join(os.path.dirname(__file__), '..', 'gee')],
	                     input=json.dumps(data), capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout.strip().splitlines()[-1])
	charts = out['charts']
	assert [c['title'].rsplit(' · ', 1)[-1] for c in charts] == ['Almeria', 'Granada']
	for c in charts:
		assert c['type'] == 'LineChart' and c['axis'] == 'Day of the year'
		assert c['head'] == ['Day of the year', '2024', '2025'] and [r[0] for r in c['rows']] == [1, 182, 183]
		old, new = c['series']['0'], c['series']['1']
		assert new['lineWidth'] > old['lineWidth'] and _luminance(new['color']) < _luminance(old['color'])
	assert charts[1]['rows'][0] == [1, 1.5, 1.5]  # the values of Granada, not those of Almeria
	assert [(r['region'], r['date'], r['year'], r['doy']) for r in out['csv'][:2]] == \
		[('Almeria', '2024-01-01', 2024, 1), ('Almeria', '2024-07-01', 2024, 183)]
	assert list(out['csv'][0]) == ['region', 'date', 'value', 'n_pixels', 'n_images', 'year', 'doy']


VIEWER = r"""
var fs = require('fs'), vm = require('vm');
var spec = null;
function el(tag, attrs) {
	return {tag: tag, attrs: attrs, clientWidth: 800, append: function () {}, replaceChildren: function () {}};
}
global.window = {matchMedia: function () { return {matches: false, addEventListener: function () {}}; }};
global.document = {documentElement: {}};
global.getComputedStyle = function () { return {colorScheme: 'light'}; };
global.MO = {el: el, css: function () { return '#000000'; }, MONTHS: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul',
	'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], text: async function () { return fs.readFileSync(0, 'utf8'); }};
global.vega = {read: function (text) {
	var lines = text.trim().split('\n'), head = lines[0].split(',');
	return lines.slice(1).map(function (l) {
		var r = {};
		l.split(',').forEach(function (v, i) { r[head[i]] = v; });
		return r;
	});
}};
global.vegaEmbed = async function (box, s) { spec = s; return {}; };
vm.runInThisContext(fs.readFileSync(process.argv[process.argv.length - 1], 'utf8'));
MO.chart.render(el('div'), {id: 'r', chart: 'doy', csv: 'series.csv', ylabel: 'NDSI'}, '').then(function () {
	console.log(JSON.stringify(spec.encoding));
});
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_viewer_draws_the_newest_year_dark_and_thick(tmp_path):
	from monitoreo import publish
	csv = tmp_path / 'series.csv'
	timeseries.write_csv(_rows(), str(csv), {}, timeseries.COLUMNS + ['year', 'doy'])
	charts = os.path.join(os.path.dirname(publish.__file__), 'viewer', 'assets', 'charts.js')
	run = subprocess.run(['node', '-e', VIEWER, charts], input=csv.read_text(encoding='utf-8'), capture_output=True,
	                     text=True, timeout=60)
	assert run.returncode == 0, run.stderr
	encoding = json.loads(run.stdout.strip().splitlines()[-1])
	# from light to dark, each year with its colour whichever years are shown
	assert encoding['color']['scale'] == {'scheme': 'viridis', 'reverse': True, 'domain': ['2023', '2024']}
	width = encoding['strokeWidth']
	assert width['condition']['test'] == {'field': 'year', 'equal': '2024'}  # the newest year, thicker
	assert width['condition']['value'] > width['value']


VIEWER_YEARS = r"""
var fs = require('fs'), vm = require('vm');
var specs = [], made = [];
function el(tag, attrs) {
	var kids = Array.prototype.slice.call(arguments, 2).flat(Infinity);
	var e = {tag: tag, attrs: attrs || {}, children: kids, clientWidth: 800, checked: (attrs || {}).checked,
		append: function () { for (var i = 0; i < arguments.length; i++) this.children.push(arguments[i]); },
		replaceChildren: function () { this.children = Array.prototype.slice.call(arguments); }};
	made.push(e);
	return e;
}
global.window = {matchMedia: function () { return {matches: false, addEventListener: function () {}}; }};
global.document = {documentElement: {}};
global.getComputedStyle = function () { return {colorScheme: 'light'}; };
global.MO = {el: el, css: function () { return '#000000'; }, text: async function () { return fs.readFileSync(0, 'utf8'); }};
global.vega = {read: function (text) {
	var lines = text.trim().split('\n'), head = lines[0].split(',');
	return lines.slice(1).map(function (l) {
		var r = {};
		l.split(',').forEach(function (v, i) { r[head[i]] = v; });
		return r;
	});
}};
global.vegaEmbed = async function (box, s) { specs.push(s); return {}; };
vm.runInThisContext(fs.readFileSync(process.argv[process.argv.length - 1], 'utf8'));
var tick = function () { return new Promise(function (r) { setTimeout(r, 0); }); };
var last = function () { return specs[specs.length - 1]; };
var years = function (s) { return Array.from(new Set(s.data.values.map(function (r) { return r.year; }))); };
MO.chart.render(el('div'), {id: 'r', chart: 'doy', csv: 'series.csv', ylabel: 'NDVI'}, '').then(async function () {
	var boxes = made.filter(function (e) { return e.tag === 'input' && e.attrs.type === 'checkbox'; });
	var button = function (t) { return made.find(function (e) { return e.tag === 'button' && e.children[0] === t; }); };
	var chart = made.find(function (e) { return e.attrs.class === 'chart'; });
	var out = {boxes: boxes.map(function (b) { return b.attrs.value; }), first: years(last()),
		domain: last().encoding.color.scale.domain};
	boxes[0].attrs.onchange({target: {checked: false}});
	await tick();
	out.without = years(last());
	out.domain_without = last().encoding.color.scale.domain;
	button('None').attrs.onclick();
	await tick();
	out.none = chart.children.map(function (c) { return c.attrs && c.attrs.class; });
	button('All').attrs.onclick();
	await tick();
	out.all = years(last());
	out.checked = boxes.map(function (b) { return b.checked; });
	console.log(JSON.stringify(out));
});
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_viewer_lets_the_reader_choose_the_years(tmp_path):
	"""A chart with a line per year has a checkbox per year (and All, None): the years unchecked leave the chart and
	the others keep their colours."""
	from monitoreo import publish
	csv = tmp_path / 'series.csv'
	timeseries.write_csv(_rows(), str(csv), {}, timeseries.COLUMNS + ['year', 'doy'])
	charts = os.path.join(os.path.dirname(publish.__file__), 'viewer', 'assets', 'charts.js')
	run = subprocess.run(['node', '-e', VIEWER_YEARS, charts], input=csv.read_text(encoding='utf-8'),
	                     capture_output=True, text=True, timeout=60)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout.strip().splitlines()[-1])
	assert out['boxes'] == ['2023', '2024'] and out['first'] == ['2023', '2024']
	assert out['without'] == ['2024'] and out['domain_without'] == out['domain'] == ['2023', '2024']
	assert out['none'] == ['empty']  # 'Choose one or more years.'
	assert out['all'] == ['2023', '2024'] and out['checked'] == [True, True]
