"""The usability of the Earth Engine app (gee/ui.js and gee/core.js), as the audit of 2026-11-25 found it wanting,
run in Node with the ui and ee of tests/test_themes.py (nothing computes in Earth Engine):

- the dates of the time series chart are the days of its steps whatever the time zone of the browser (June 1, not
  «May 31» in Madrid);
- dates that do not exist (2025-02-30, 2025-13-45...) are refused, as the Python package does, and the errors of the
  period are in the language of the panel;
- searching and loading a region does not open the results beside the map (it would narrow it), and the region is
  framed again when the results open, unless the user moved the map;
- the first steps are written under the subtitle;
- in a narrow window (a phone) the panel, the map and the results take the whole width, one at a time, with buttons
  to go from one to another; and the widgets of the panel fit into it."""

import datetime as dt
import json
import os
import shutil
import subprocess

import pytest

from monitoreo import catalog, composite

GEE = os.path.join(os.path.dirname(__file__), '..', 'gee')
pytestmark = pytest.mark.skipif(not shutil.which('node'), reason='no Node')

STEPS = r"""
var centred = 0, moves = [], resizes = [];
var state0 = ['2025-01-01', '2025-12-31'];
map.centerObject = function () { centred += 1; };
function periodBox(i) {  // the boxes of the start and the end: two boxes in a row with the period
	var boxes = find(controls, 'Textbox');
	for (var k = 0; k + 1 < boxes.length; k++) {
		if (boxes[k].opts.value === state0[0] && boxes[k + 1].opts.value === state0[1]) return boxes[k + i];
	}
}
function setPeriod(i, v) {  // as a user writes it: the box shows it and the app is told
	var b = periodBox(i);
	b.opts.value = v;
	b.opts.onChange(v);
	state0[i] = v;
}
function results_() { return {shown: Boolean(results.styles.shown), texts: last().texts}; }
var out = {};
out.firstSteps = texts(controls).filter(function (s) { return /^First steps/.test(s); });
// the widths of the selects and boxes of the panel (every group: the folded ones are only hidden)
out.widths = all(controls).map(function (w) {
	return w.opts && w.opts.style && w.opts.style.width ? parseInt(w.opts.style.width, 10) : 0;
});
// a protected area: searching and loading it says so in the panel, the results stay closed
out.region = {};
// nothing found: said under the region, and gone with another kind of region
answer = {features: []};
button('Search').opts.onClick();
out.region.none = texts(controls).filter(function (s) { return /^No protected area/.test(s); }).length;
selectWith('wdpa').opts.onChange('admin');
out.region.noneAfterMode = texts(controls).filter(function (s) { return /^No protected area/.test(s); }).length;
selectWith('wdpa').opts.onChange('wdpa');
answer = {features: [{properties: {SITE_ID: 389011, NAME: 'Sierra Nevada', DESIG_ENG: 'National Park',
	DESIG: 'Parque Nacional', ISO3: 'ESP', REP_AREA: 859}}]};
button('Search').opts.onClick();
out.region.searched = results_().shown;
var choose = find(controls, 'Select', function (w) { return w.opts.placeholder === 'Choose the area'; })[0];
answer = {features: [{geometry: {type: 'Polygon', coordinates: [[[-3.5, 37], [-3, 37], [-3, 37.2], [-3.5, 37]]]},
	properties: {name: 'Sierra Nevada'}}], info: {area: 8.6e8, centroid: [-3.2, 37.1], total: 8.6e8,
	boundsArea: 9e8}, n: 1};
choose.opts.onChange(389011);
out.region.chosen = results_().shown;
out.region.centred = centred;
out.region.texts = texts(controls).filter(function (s) { return /Sierra Nevada/.test(s); });
// the first result opens the results: the region is framed again in the narrower map
answer = {value_lo: 0.1, value_hi: 0.8};
button('Add to the map').opts.onClick();
out.region.afterMap = centred;
// the user moves the map: closing the results does not frame it again
var realNow = Date.now;
Date.now = function () { return realNow() + 60000; };
moves.forEach(function (f) { f(); });
Date.now = realNow;
find(results, 'Button', function (w) { return w.opts.label === 'Close'; })[0].opts.onClick();
out.region.afterMove = centred;
// a monthly time series of June to August 2025: the cells of its dates
setPeriod(0, '2025-06-01');
setPeriod(1, '2025-08-31');
answer = 'rows';
button('Compute the time series').opts.onClick();
var chart = find(results, 'Chart').filter(function (c) { return c.opts.type === 'LineChart'; })[0];
out.cells = chart.opts.table.rows.map(function (r) { return r.c[0].v; });
// dates that do not exist, and an end before the start, in English and in Spanish
function tryPeriod(a, b) {
	setPeriod(0, a);
	setPeriod(1, b);
	button(out.lang === 'es' ? 'Añadir al mapa' : 'Add to the map').opts.onClick();
	return last().texts.join(' ');
}
out.lang = 'en';
out.bad = {};
['2025-02-30', '2025-06-31', '2025-13-45', '2025-00-10'].forEach(function (d) {
	out.bad[d] = tryPeriod(d, '2025-08-31');
});
out.bad.reversed = tryPeriod('2025-08-31', '2025-06-01');
button('Español').opts.onClick();
out.lang = 'es';
out.bad.es = tryPeriod('2025-02-30', '2025-08-31');
out.bad.esReversed = tryPeriod('2025-08-31', '2025-06-01');
out.firstStepsEs = texts(controls).filter(function (s) { return /^Primeros pasos/.test(s); });
button('English').opts.onClick();
out.lang = 'en';
tryPeriod('2025-06-01', '2025-08-31');
// the parameters of an analysis with a date that does not exist: not applied
var box = find(controls, 'Textbox', function (w) { return w.opts.placeholder === input.hint; })[0];
box.opts.value = JSON.stringify({monitoreo: input.version, analysis: 'map_layer',
	parameters: {start: '2025-06-31', end: '2025-08-31', season: ['06-01', '06-31']}});
button('Apply parameters').opts.onClick();
out.applied = texts(controls).filter(function (s) { return /valid date/.test(s); });
out.periodAfterApply = [periodBox(0) && periodBox(0).opts.value];
// the core: days that exist, and the windows of a period refusing those that do not
out.isDate = ['2024-02-29', '2025-02-29', '2025-02-30', '2025-13-01', '2025-1-01', 'x'].map(MonitorEO.isDate);
out.isMonthDay = ['02-29', '06-30', '06-31', '13-01', '00-10', '6-01'].map(MonitorEO.isMonthDay);
out.windows = [['2025-02-30', '2025-03-31'], ['2025-01-01', '2025-03-31']].map(function (p) {
	try { MonitorEO.windows(p, null); return 'ok'; } catch (err) { return err.message; }
});
// a narrow window (a phone): one of the panel, the map and the results at a time, over the whole width
function shown() {
	return {controls: controls.styles.shown !== false, map: map.styles.shown !== false,
		results: Boolean(results.styles.shown), controlsWidth: controls.styles.width, resultsWidth: results.styles.width,
		nav: map.children[1].styles.shown,
		navLabels: map.children[1].children.map(function (w) { return w.opts.label; })};
}
function top(panel) {
	return find(panel.children[0] || panel, 'Button').map(function (w) { return w.opts.label; });
}
out.narrow = {};
find(results, 'Button', function (w) { return w.opts.label === 'Close'; })[0].opts.onClick();
resizes.forEach(function (f) { f({width: 390, height: 844, is_mobile: true}); });
out.narrow.start = shown();
out.narrow.top = top(controls);
find(controls.children[0], 'Button', function (w) { return w.opts.label === 'Map'; })[0].opts.onClick();
out.narrow.map = shown();
map.children[1].children[0].opts.onClick();  // ☰ Options
answer = {value_lo: 0.1, value_hi: 0.8};
button('Add to the map').opts.onClick();
out.narrow.result = shown();
out.narrow.resultsNav = find(results, 'Button').map(function (w) { return w.opts.label; });
find(results, 'Button', function (w) { return w.opts.label === 'Map'; })[0].opts.onClick();
out.narrow.resultMap = shown();
resizes.forEach(function (f) { f({width: 1366, height: 860, is_desktop: true}); });
out.wide = shown();
out.wide.top = top(controls);
out.wide.resultsNav = find(results, 'Button').map(function (w) { return w.opts.label; });
// narrow again with the results open (a phone turned upright): the results, with their buttons
resizes.forEach(function (f) { f({width: 390, height: 844, is_mobile: true}); });
out.again = shown();
out.again.resultsNav = find(results, 'Button').map(function (w) { return w.opts.label; });
// the swipe of two periods in a narrow window: its map has the buttons too
check('Compare with another period').opts.onChange(true);
answer = {value_lo: -5, value_hi: 5};
button('Add to the map').opts.onClick();
answer = {reference_lo: 0, reference_hi: 1, other_lo: 0, other_hi: 1};
find(results, 'Button', function (w) { return w.opts.label === 'Swipe: the two periods side by side'; })[0].opts.onClick();
find(results, 'Button', function (w) { return w.opts.label === 'Map'; })[0].opts.onClick();
out.swipe = {split: root.children[1].kind, shown: root.children[1].styles.shown !== false,
	navs: map.children.filter(function (w) { return w.styles && w.styles.position === 'top-center'; }).map(function (w) {
		return [w.styles.shown, w.children.map(function (b) { return b.opts.label; })];
	})};
check('Compare with another period').opts.onChange(false);
process.stdout.write(JSON.stringify(out));
"""


def _run(tz='UTC'):
	from test_themes import PANEL, _build
	head = PANEL[:PANEL.index('var out = {};')]
	# the root and the map of Earth Engine Apps that test_themes does not give: onResize and the moves of the map
	head = head.replace("var GEE = process.argv", "root.onResize = function (f) { resizes.push(f); f({width: 1366}); };\n"
	                    "map.onChangeCenter = map.onChangeZoom = function (f) { moves.push(f); };\n"
	                    "var GEE = process.argv", 1)
	head = head.replace("var fs = require('fs')", "var resizes = [], moves = [];\nvar fs = require('fs')", 1)
	script = head + STEPS.replace(', moves = [], resizes = [];', ';', 1)
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {},
	        'hint': 'Paste here the parameters of an analysis (JSON)', 'version': __import__('monitoreo').__version__}
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120, env=dict(os.environ, TZ=tz))
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.fixture(scope='module')
def app():
	return _run()


def _day_of(cell, tz):
	"""The day the charts of the Code Editor show for CELL ('Date(y, m, d, h)', parsed in the time zone of the browser
	TZ as the Google charts parse it, then read in UTC and in that time zone)."""
	script = ("var a = process.argv[1].match(/-?\\d+/g).map(Number);"
	          "var d = new Date(a[0], a[1], a[2], a[3] || 0);"
	          "process.stdout.write(JSON.stringify([d.toISOString().slice(0, 10), [d.getFullYear(), d.getMonth() + 1,"
	          " d.getDate()].join('-')]));")
	run = subprocess.run(['node', '-e', script, cell], capture_output=True, text=True, env=dict(os.environ, TZ=tz),
	                     timeout=30)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout)


@pytest.mark.parametrize('tz', ['Europe/Madrid', 'America/Bogota', 'Asia/Tokyo', 'UTC'])
def test_the_dates_of_the_series_are_the_days_of_its_steps_in_any_time_zone(app, tz):
	assert len(app['cells']) == 3
	days = [_day_of(c, tz) for c in app['cells']]
	assert days == [['2025-06-01', '2025-6-1'], ['2025-07-01', '2025-7-1'], ['2025-08-01', '2025-8-1']]


def test_the_app_refuses_dates_that_do_not_exist(app):
	for d in ['2025-02-30', '2025-06-31', '2025-13-45', '2025-00-10']:
		assert f'Not a valid date: "{d}"' in app['bad'][d]
	assert 'Period 2025-08-31 / 2025-06-01: the end is before the start.' in app['bad']['reversed']
	assert 'Fecha no válida: «2025-02-30»' in app['bad']['es']
	assert 'Periodo 2025-08-31 / 2025-06-01: el final es anterior al inicio.' in app['bad']['esReversed']
	assert app['isDate'] == [True, False, False, False, False, False]
	assert app['isMonthDay'] == [True, True, False, False, False, False]
	assert app['windows'][0] == 'not a valid date (YYYY-MM-DD): 2025-02-30' and app['windows'][1] == 'ok'
	# the parameters: the start and the season that do not exist are not applied
	assert any('2025-06-31' in s for s in app['applied']) and any('06-31' in s for s in app['applied'])
	assert app['periodAfterApply'] == ['2025-06-01']


def test_the_python_package_refuses_the_same_dates():
	for period in [('2025-02-30', '2025-08-31'), ('2025-06-31', '2025-08-31'), ('2025-13-45', '2025-08-31')]:
		with pytest.raises(ValueError):
			composite.windows(period)
	for season in [('06-01', '06-31'), ('13-01', '12-31'), ('00-10', '06-01'), ('06', '07-01')]:
		with pytest.raises(ValueError, match='not a valid day of the season'):
			composite.windows(('2024-01-01', '2025-12-31'), season)
	# 29 February is a day of the season, the 28th in common years
	assert composite.windows(('2025-01-01', '2025-12-31'), ('02-29', '03-10'))[-1][1] == dt.date(2025, 2, 28)


def test_searching_and_loading_a_region_keeps_the_results_closed(app):
	assert app['region']['searched'] is False and app['region']['chosen'] is False
	assert app['region']['centred'] == 1  # framed once its bounds are known
	assert any(s.startswith('Region: Sierra Nevada') for s in app['region']['texts'])


def test_the_region_is_framed_again_when_the_results_open_unless_the_user_moved_the_map(app):
	assert app['region']['afterMap'] == 2
	assert app['region']['afterMove'] == 2


def test_the_first_steps_under_the_subtitle(app):
	assert len(app['firstSteps']) == 1 and 'click its button' in app['firstSteps'][0]
	assert len(app['firstStepsEs']) == 1 and 'pulsa su botón' in app['firstStepsEs'][0]


def test_the_widgets_fit_into_the_panel(app):
	# the panel is 380 px with 10 px of padding on each side, its groups 6 px in: a select of 320 px and its margins
	assert max(app['widths']) == 320


def test_a_narrow_window_shows_the_panel_the_map_and_the_results_one_at_a_time(app):
	n = app['narrow']
	assert n['start'] == {'controls': True, 'map': False, 'results': False, 'controlsWidth': '100%',
	                      'resultsWidth': '100%', 'nav': True, 'navLabels': ['☰ Options']}
	assert n['top'] == ['Map']
	assert n['map']['map'] and not n['map']['controls'] and not n['map']['results']
	assert n['result']['results'] and not n['result']['map'] and not n['result']['controls']
	assert n['result']['navLabels'] == ['☰ Options', 'Results']
	assert {'Close', 'Map', '☰ Options'} <= set(n['resultsNav'])
	assert n['resultMap']['map'] and not n['resultMap']['results']
	w = app['wide']
	assert w['controls'] and w['map'] and w['results'] and not w['nav']
	assert w['controlsWidth'] == '380px' and w['resultsWidth'] == '460px'
	assert 'Map' not in w['top'] and not {'Map', '☰ Options'} & set(w['resultsNav'])
	a = app['again']
	assert a['results'] and not a['map'] and not a['controls']
	assert {'Close', 'Map', '☰ Options'} <= set(a['resultsNav'])
	sw = app['swipe']
	assert sw['split'] == 'SplitPanel' and sw['shown']
	assert sw['navs'] and all(shown and labels == ['☰ Options', 'Results'] for shown, labels in sw['navs'][-1:])


def test_a_notice_of_the_region_goes_with_another_kind_of_region(app):
	assert app['region']['none'] == 1 and app['region']['noneAfterMode'] == 0
