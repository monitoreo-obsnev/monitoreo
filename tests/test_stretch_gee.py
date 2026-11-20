"""The colour range of the maps of the Earth Engine app (gee/), without Earth Engine: its default percentiles are those
of the package (maps.STRETCH, 1 and 99; the true colour maps.RGB_STRETCH), core.js checks the percentiles and makes
the ramp as maps.check_percentiles and maps.vis_params, and in the app (gee/ui.js in Node, with the ui and ee of
tests/test_themes.py, which compute nothing) the percentiles, minimum and maximum given reach the reducer and the
colours, and the animation has one range for every frame (Same colours, checked by default) or, unchecked, each frame
between the percentiles of its own values."""

import json
import os
import re
import shutil
import subprocess
import types

import pytest

from monitoreo import maps

GEE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gee')
node = pytest.mark.skipif(not shutil.which('node'), reason='no Node')


def _read(name):
	with open(os.path.join(GEE, name), encoding='utf-8') as f:
		return f.read()


def test_the_default_percentiles_are_those_of_the_package():
	core, ui = _read('core.js'), _read('ui.js')
	assert json.loads(re.search(r'\bvar STRETCH = (\[.*?\]);', core).group(1)) == list(maps.STRETCH)
	assert json.loads(re.search(r'\bvar RGB_STRETCH = (\[.*?\]);', core).group(1)) == list(maps.RGB_STRETCH)
	# the boxes of the app start with them; the reducer names its outputs lo and hi (value_lo, value_hi), as maps
	assert 'pctLo: String(mo.STRETCH[0]), pctHi: String(mo.STRETCH[1])' in ui
	assert "ee.Reducer.percentile(pcts, ['lo', 'hi'])" in core
	# no percentiles 5 and 95 left in the app
	assert not re.search(r'value_p\d|percentile\(\[5, 95\]\)|percentiles 5 (and|y) 95', core + ui)


PERCENTILES = [None, '', [], '1,99', '2 98', '2.5; 97.5', [5, 95], [0, 100], [99, 1], [0, 101], [-1, 50], [50, 50],
               'a,b', [1], [1, 2, 3]]

NODE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
global.ee = {};
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[1], f), 'utf8'), {filename: f});
});
var mo = global.MonitorEO;
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
var checks = input.percentiles.map(function (p) {
	try {
		return mo.checkPercentiles(p);
	} catch (e) {
		return 'error: ' + e.message;
	}
});
var vis = input.vis.map(function (v) { return mo.visParams(v[0], v[1], null, v[2], v[3]); });
process.stdout.write(JSON.stringify({checks: checks, vis: vis, rgb: mo.checkPercentiles(null, mo.RGB_STRETCH)}));
"""

VIS = [  # [percentiles, entry, vmin, vmax]
	[{'value_lo': 0.12, 'value_hi': 0.63}, {'minp': 0, 'maxp': 1}, None, None],
	[{'value_lo': 0.12, 'value_hi': 0.63}, {'minp': 0, 'maxp': 1}, 0.0, None],
	[{'value_lo': 0.12, 'value_hi': 0.63}, {'minp': 0, 'maxp': 1}, None, 0.5],
	[{'value_lo': None, 'value_hi': None}, {'minp': -1, 'maxp': 1}, None, None],  # without pixels: the catalog
	[{}, {'minp': -1, 'maxp': 1}, None, 0.2],
	[{'value_lo': 0.3, 'value_hi': 0.3}, None, None, None],
]


@pytest.fixture(scope='module')
def core():
	if not shutil.which('node'):
		pytest.skip('no Node')
	run = subprocess.run(['node', '-e', NODE, GEE], input=json.dumps({'percentiles': PERCENTILES, 'vis': VIS}),
	                     capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout)


def test_the_percentiles_are_checked_as_the_package(core):
	for p, js in zip(PERCENTILES, core['checks']):
		try:
			py = list(maps.check_percentiles(p))
		except ValueError as e:
			assert isinstance(js, str) and js.startswith('error: percentiles must be two numbers'), (p, js)
			assert str(e).split(',')[0] == js[len('error: '):].split(',')[0], (p, js)
		else:
			assert js == py, p
	assert core['rgb'] == list(maps.RGB_STRETCH)


def test_the_ramp_is_that_of_the_package(core, monkeypatch):
	"""visParams gives the ramp of maps.vis_params from the same percentiles (value_lo, value_hi) and ends given."""
	class Image:
		def __init__(self, stats):
			self.stats = stats

		def reduceRegion(self, *args, **kwargs):
			return self

		def getInfo(self):
			return self.stats

	monkeypatch.setattr(maps, 'ee', types.SimpleNamespace(Image=Image, EEException=Exception,
	                                                      Reducer=types.SimpleNamespace(percentile=lambda *a: a)))
	for (stats, entry, vmin, vmax), js in zip(VIS, core['vis']):
		assert js == maps.vis_params(stats, None, entry, 30, vmin, vmax), (stats, vmin, vmax)


# In the app: the reducers of the percentiles made (their arguments), what the legend and the results say
STEPS = r"""
var out = {};
function results_() { return root.children[2]; }
function inResults(kind, test) { return find(results_(), kind, test); }
var reducers = [], plainCall = call;
call = function (name) {
	var f = plainCall(name);
	if (name !== 'Reducer.percentile') return f;
	return new Proxy(f, {apply: function (t, self, args) { reducers.push(args); return Reflect.apply(f, self, args); }});
};
function boxes() { return find(controls, 'Textbox'); }
function pctBox(i) { return boxes().filter(function (w) { return w.opts.value === ['1', '99'][i]; })[0]; }
function endBoxes() { return boxes().filter(function (w) { return w.opts.placeholder === 'optional'; }); }
out.boxes = [pctBox(0) && pctBox(0).opts.value, pctBox(1) && pctBox(1).opts.value, endBoxes().length];
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
// by default: the percentiles 1 and 99 of the map; the index with the true colour (Both): 2 and 98 for the latter
reducers = [];
answer = {value_lo: 0.2, value_hi: 0.7};
button('Add to the map').opts.onClick();
out.byDefault = {reducers: reducers, legend: texts(legend)};
selectWith('both').opts.onChange('both');
reducers = [];
answer = {value_lo: 0.2, value_hi: 0.7, red_lo: 0.01, red_hi: 0.2, green_lo: 0.02, green_hi: 0.18, blue_lo: 0.03,
	blue_hi: 0.15};
button('Add to the map').opts.onClick();
out.both = {reducers: reducers, legend: texts(legend)};
selectWith('both').opts.onChange('index');
// other percentiles (a decimal comma too) and a minimum
var lo = pctBox(0), hi = pctBox(1), ends = endBoxes();
lo.opts.onChange('2,5');
hi.opts.onChange('97.5');
ends[0].opts.onChange('0,1');
reducers = [];
answer = {value_lo: 0.2, value_hi: 0.7};
button('Add to the map').opts.onClick();
out.given = {reducers: reducers, legend: texts(legend)};
// both ends: no percentiles to compute
ends[1].opts.onChange('0.9');
reducers = [];
button('Add to the map').opts.onClick();
out.bothEnds = {reducers: reducers, legend: texts(legend)};
// the true colour with the percentiles changed: those of the user
ends[0].opts.onChange('');
ends[1].opts.onChange('');
selectWith('both').opts.onChange('rgb');
reducers = [];
button('Add to the map').opts.onClick();
out.rgbChanged = reducers;
selectWith('rgb').opts.onChange('index');
// wrong percentiles or ends: an error before Earth Engine
lo.opts.onChange('99');
hi.opts.onChange('1');
button('Add to the map').opts.onClick();
out.badPercentiles = texts(results_());
lo.opts.onChange('1');
hi.opts.onChange('99');
ends[0].opts.onChange('0.8');
ends[1].opts.onChange('0.2');
button('Add to the map').opts.onClick();
out.badEnds = texts(results_());
ends[0].opts.onChange('');
ends[1].opts.onChange('');
// the animation of a frame per month, with Same colours unchecked (checked by default): each frame between the
// percentiles of its own values, in one request
out.sameByDefault = check('Same colours in every frame').opts.value;
check('Same colours in every frame').opts.onChange(false);
find(controls, 'Select', function (w) {
	return (w.opts.items || []).some(function (i) { return i.label === 'Month'; });
})[0].opts.onChange('monthly');
reducers = [];
answer = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map(function (i) { return {value_lo: i / 10, value_hi: 1 + i / 10}; });
answer[3] = {value_lo: null, value_hi: null};  // a frame without values: the range of the catalog
button('Make the animation').opts.onClick();
out.frames = {reducers: reducers.length, texts: texts(results_()), legend: texts(legend)};
inResults('Slider')[0].opts.onChange(2);
out.frames.slid = {legend: texts(legend), texts: texts(results_())};
// Same colours in every frame: the percentiles of the map of the whole period
check('Same colours in every frame').opts.onChange(true);
reducers = [];
answer = {value_lo: 0.1, value_hi: 0.9};
button('Make the animation').opts.onClick();
out.same = {reducers: reducers.length, texts: texts(results_()), legend: texts(legend)};
console.log(JSON.stringify(out));
"""


@node
def test_the_colour_range_of_the_app():
	from test_swipe import _app
	out = _app(STEPS)
	assert out['boxes'] == ['1', '99', 2]
	# by default, the percentiles 1 and 99 of the map, said in the legend
	assert out['byDefault']['reducers'] == [[[1, 99], ['lo', 'hi']]]
	assert out['byDefault']['legend'][1:] == ['0.2000', '0.7000', 'Colours: p1–p99 of the map over the region.']
	# the true colour keeps 2 and 98 (one range for the three bands), said under the colour bar of the index
	assert out['both']['reducers'] == [[[1, 99], ['lo', 'hi']], [[2, 98], ['lo', 'hi']]]
	assert out['both']['legend'][-2:] == ['True colour (red, green, blue): reflectance from 0.01 to 0.2',
	                                      'Colours: p2–p98 of the red, green and blue reflectance over the region.']
	# the percentiles and the minimum given reach the reducer and the colours
	assert out['given']['reducers'] == [[[2.5, 97.5], ['lo', 'hi']]]
	assert out['given']['legend'][1:] == ['0.1000', '0.7000',
	                                      'Colours: minimum given, maximum the p97.5 of the map over the region.']
	assert out['bothEnds']['reducers'] == []
	assert out['bothEnds']['legend'][1:] == ['0.1000', '0.9000', 'Colours: range given (Min and Max).']
	assert out['rgbChanged'] == [[[2.5, 97.5], ['lo', 'hi']]]
	assert any('percentiles must be two numbers 0 <= low < high <= 100' in t for t in out['badPercentiles'])
	assert any('must be lower than its maximum' in t for t in out['badEnds'])
	# the animation: each frame its own range (one request, the reducer once per frame), written beside each frame
	assert out['sameByDefault'] is True  # one range for every frame by default
	frames = out['frames']
	assert frames['reducers'] == 12
	summary = next(t for t in frames['texts'] if t.startswith('12 frames'))
	assert summary.startswith('12 frames, each with the colours of its own values (its range in brackets): '
	                          'January 2025 (0 – 1), February 2025 (0.1000 – 1.100), March 2025 (0.2000 – 1.200), '
	                          'April 2025 (0 – 1)')  # a frame without values: the range of the catalog of NDVI
	assert 'Colours: p1–p99 of each frame over the region (each one its own range).' in frames['texts']
	assert frames['legend'][1:3] == ['0', '1']
	# the slider: the colour bar and the range of the frame on the map
	assert frames['slid']['legend'][1:3] == ['0.2000', '1.200'] and 'March 2025' in frames['slid']['legend'][0]
	assert '0.2000 – 1.200' in frames['slid']['texts']
	# Same colours: one ramp, from the percentiles of the map of the whole period
	same = out['same']
	assert same['reducers'] == 1
	assert any(t.startswith('12 frames, with the same colours (from 0.1000 to 0.9000)') for t in same['texts'])
	assert 'Colours: p1–p99 of the map of the whole period (the same colours in every frame).' in same['texts']
