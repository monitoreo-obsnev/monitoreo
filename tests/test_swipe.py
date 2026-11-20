"""The swipe and the time sliders (the split maps and the time sliders of geemap), without Earth Engine: in the Earth
Engine app (gee/ui.js in Node, with the ui and ee of tests/test_themes.py, which compute nothing), the swipe of the two
periods of a comparison and the slider of the frames of an animation; in the assistant (the code of the map of
ui/assistant.html in Node, with a DOM, a Leaflet and an API that compute nothing), its swipe and Play; in the viewer of
results (viewer/assets/map.js), its controls."""

import json
import os
import re
import shutil
import subprocess

import pytest

from monitoreo import catalog

HERE = os.path.dirname(os.path.abspath(__file__))
GEE = os.path.join(HERE, '..', 'gee')
SRC = os.path.join(HERE, '..', 'src', 'monitoreo')

STEPS = r"""
var out = {};
function results_() { return root.children[2]; }
// a region: the view of the map
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
function inResults(kind, test) { return find(results_(), kind, test); }
// a comparison of two periods, its map, and its swipe
check('Compare with another period').opts.onChange(true);
answer = {value_lo: -0.1, value_hi: 0.1};
button('Add to the map').opts.onClick();
var swipe = inResults('Button', function (w) { return w.opts.label === 'Swipe: the two periods side by side'; })[0];
out.swipeButton = Boolean(swipe);
answer = {reference_lo: 0.2, reference_hi: 0.7, other_lo: 0.1, other_hi: 0.8};
swipe.opts.onClick();
out.split = root.children[1].kind;
out.wipe = root.children[1].opts.wipe;
out.note = texts(results_()).filter(function (t) { return /^Left: reference period/.test(t); }).length;
inResults('Button', function (w) { return w.opts.label === 'Back to one map'; })[0].opts.onClick();
out.back = root.children[1] === map;
check('Compare with another period').opts.onChange(false);
// an animation of a frame per month and its slider of frames on the map
find(controls, 'Select', function (w) {
	return (w.opts.items || []).some(function (i) { return i.label === 'Month'; });
})[0].opts.onChange('monthly');
answer = {value_lo: 0.1, value_hi: 0.8};
button('Make the animation').opts.onClick();
var slider = inResults('Slider')[0];
out.slider = slider ? [slider.opts.min, slider.opts.max] : null;
slider.opts.onChange(1);
out.frame = [layers[layers.length - 1], texts(results_()).indexOf('February 2025') >= 0];
console.log(JSON.stringify(out));
"""


def _app(steps):  # what STEPS print, run on the app in Node with the ui and ee of tests/test_themes.py
	from test_themes import PANEL, _build
	script = PANEL[:PANEL.index('var out = {};')] + steps
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {}}
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_swipe_and_the_frames_of_the_app():
	out = _app(STEPS)
	assert out['swipeButton'] and out['split'] == 'SplitPanel' and out['wipe'] is True and out['note'] == 1
	assert out['back'] is True
	assert out['slider'] == [0, 11]  # the year of the app by default: a frame per month
	assert out['frame'] == ['January 2025', True]  # the frame on the map: the first one, then that of the slider


# The swipe of the app with two maps of its own (the ui of the tests gives the same map to every ui.Map), and the calls
# made on the image of the frame on the map
SWIPE = r"""
var out = {};
function results_() { return root.children[2]; }
function inResults(kind, test) { return find(results_(), kind, test); }
function resultButton(label) { return inResults('Button', function (w) { return w.opts.label === label; })[0]; }
ui.Map = Object.assign(function () {
	var m = new Widget('Map');
	m.vis = [];
	m.setOptions = m.setControlVisibility = m.centerObject = nothing;
	m.addLayer = function (img, vis) { m.vis.push(vis); return {}; };
	return m;
}, {Layer: ui.Map.Layer, Linker: nothing});
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
check('Compare with another period').opts.onChange(true);
// the map of a comparison and its swipe with the percentiles ST of the two periods: the range of the two maps and what
// the split shows
function swipe(st) {
	answer = {value_lo: -0.1, value_hi: 0.1};
	button('Add to the map').opts.onClick();
	answer = st;
	resultButton('Swipe: the two periods side by side').opts.onClick();
	var split = root.children[1], left = split.opts.firstPanel, right = split.opts.secondPanel;
	return {split: split.kind, range: [left.vis[0], right.vis[0]].map(function (v) { return [v.min, v.max]; }),
		left: texts(left), right: texts(right)};
}
out.legend = (function () { answer = {value_lo: -0.1, value_hi: 0.1}; button('Add to the map').opts.onClick();
	return texts(legend); })();
out.swipe = swipe({reference_lo: 0.2, reference_hi: 0.7, other_lo: 0.1, other_hi: 0.8});
out.legendSwiped = texts(legend);  // that of the map of the app, as it was
resultButton('Back to one map').opts.onClick();
out.back = [root.children[1] === map, texts(legend)];
// a period without pixels (its percentiles null), and both
out.oneEmpty = swipe({reference_lo: null, reference_hi: null, other_lo: 0.2, other_hi: 0.8}).range;
out.oneEmptyNegative = swipe({reference_lo: -0.5, reference_hi: -0.1, other_lo: null, other_hi: null}).range;
out.bothEmpty = swipe({reference_lo: null, reference_hi: null, other_lo: null, other_hi: null}).range;
var e = MonitorEO.byRef(27), catalogVis = MonitorEO.visParams(null, MonitorEO.rampEntry(e, 'median', 'period'));
out.catalog = [catalogVis.min, catalogVis.max];
// Close, any other result, a region (its layer) and the tools to draw bring the map of the app back
resultButton('Close').opts.onClick();
out.close = root.children[1] === map;
swipe({reference_lo: 0.2, reference_hi: 0.7, other_lo: 0.1, other_hi: 0.8});
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
button('Use the map view').opts.onClick();
out.region = root.children[1] === map;
swipe({reference_lo: 0.2, reference_hi: 0.7, other_lo: 0.1, other_hi: 0.8});
selectWith('view').opts.onChange('draw');
out.draw = root.children[1] === map;
selectWith('draw').opts.onChange('view');
swipe({reference_lo: 0.2, reference_hi: 0.7, other_lo: 0.1, other_hi: 0.8});
check('Compare with another period').opts.onChange(false);
var before = layers.length;
answer = {value_lo: 0.1, value_hi: 0.8};
button('Add to the map').opts.onClick();
out.other = [root.children[1] === map, layers.length - before, Boolean(resultButton('Back to one map'))];
// the frame on the map: the calls made on its image, the last ones before ui.Map.Layer and setEeObject
var made = [], plainCall = call;
call = function (name) {
	var f = plainCall(name);
	return new Proxy(f, {apply: function (t, self, args) { made.push(name); return Reflect.apply(f, self, args); }});
};
var frameCalls = [];
ui.Map.Layer = function (img, vis, name) {
	frameCalls.push(made.slice(-2));
	return {name: name, setName: nothing, setEeObject: function () { frameCalls.push(made.slice(-2)); }};
};
find(controls, 'Select', function (w) {
	return (w.opts.items || []).some(function (i) { return i.label === 'Month'; });
})[0].opts.onChange('monthly');
button('Make the animation').opts.onClick();
inResults('Slider')[0].opts.onChange(1);
out.frameCalls = frameCalls;
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_swipe_of_the_app_has_its_colour_bar_and_goes_back():
	out = _app(SWIPE)
	assert out['swipe']['split'] == 'SplitPanel' and out['swipe']['range'] == [[0.1, 0.8], [0.1, 0.8]]
	# the colour bar of the two periods on the left map, with its unit; the legend of the map of the app (that of the
	# difference) stays, and is right again after Back to one map
	assert out['swipe']['left'] == ['NDVI Sentinel-2 · Map view · Median [unitless]', '0.1000', '0.8000',
	                                'Colours: p1–p99 of the two periods over the region.']
	assert out['swipe']['right'] == []
	assert out['legend'][1:] == ['-0.1000', '0.1000', 'Colours: symmetric around 0, up to the largest of |p1| and '
	                             '|p99| of the difference over the region.'] and ' − ' in out['legend'][0]
	assert out['legendSwiped'] == out['legend'] and out['back'] == [True, out['legend']]
	# the range of the periods with pixels; that of the catalog when none has
	assert out['oneEmpty'] == [[0.2, 0.8], [0.2, 0.8]]
	assert out['oneEmptyNegative'] == [[-0.5, -0.1], [-0.5, -0.1]]
	assert out['bothEmpty'] == [out['catalog'], out['catalog']] and out['catalog'][1] - out['catalog'][0] > 0.1
	# Close, any other result, a region and the tools to draw put the map of the app back, and what they add goes to it
	assert out['close'] is True and out['region'] is True and out['draw'] is True
	assert out['other'] == [True, 1, False]
	# the frame on the map, cut to the region (not the white of the outside of the frame over the whole map)
	assert out['frameCalls'] == [['Image', 'clipToCollection'], ['Image', 'clipToCollection']]


def _read(*parts):
	with open(os.path.join(SRC, *parts), encoding='utf-8') as f:
		return f.read()


def test_the_assistant_has_the_slider_and_the_swipe():
	page = _read('ui', 'assistant.html')
	for id_ in ('stepslider', 'play', 'swipesel', 'swipe', 'swipebar'):
		assert f'id="{id_}"' in page, id_
	assert "createPane('swipe')" in page and 'style.clip' in page  # the map compared, clipped at the line
	assert re.search(r"\$\('mapstep'\)\.onchange = \(\) => \{ syncSlider\(\);", page)


# The map of the assistant (its code from «let leaflet» to the button of the snapshot) in Node, with a DOM, a Leaflet
# and an API that draw and compute nothing: result 1, made earlier, and result 2 with the maps of 2018, 2019 and 2020
PAGE = r"""
class Elem {
  constructor(tag, attrs = {}) {
    this.tag = tag; this.children = []; this.style = {}; this.attrs = {}; this.hidden = false; this.disabled = false;
    this.textContent = attrs.text || ''; this._value = attrs.value === undefined ? '' : String(attrs.value);
    this.id = attrs.id; this.selectedIndex = -1; this.classList = {toggle() {}};
  }
  get select() { return ['mapsel', 'mapstep', 'swipesel'].includes(this.id); }
  get options() { return this.children; }
  get value() { return this.select ? (this.children[this.selectedIndex] || {_value: ''})._value : this._value; }
  set value(v) {
    if (this.select) this.selectedIndex = this.children.findIndex(o => o._value === String(v)); else this._value = String(v);
  }
  get selectedOptions() { return this.children[this.selectedIndex] ? [this.children[this.selectedIndex]] : []; }
  setAttribute(k, v) { this.attrs[k] = v; }
  replaceChildren(...c) { this.children = c; this.selectedIndex = c.length ? 0 : -1; }
  insertBefore(c, before) { const i = this.children.indexOf(before); this.children.splice(i < 0 ? this.children.length : i, 0, c); }
  append(...c) { this.children.push(...c); c.forEach(x => { if (x.id) dom[x.id] = x; }); }
  remove() { if (dom[this.id] === this) delete dom[this.id]; }
}
const dom = {};
['mapsel', 'mapstep', 'steplabel', 'steptitle', 'layerlabel', 'layer', 'maptitle', 'mapbox', 'pixel', 'siglabel',
 'significant', 'maplegend', 'maphint', 'query', 'map', 'stepslider', 'play', 'swipebar', 'swipesel', 'swipe',
 'swipenote', 'basemap', 'opacity', 'snapshot', 'rangelabel', 'plo', 'phi', 'cmin', 'cmax', 'applyrange']
  .forEach(id => { dom[id] = new Elem('x', {id}); });
dom.basemap.value = 'osm'; dom.opacity.value = '0.8'; dom.swipe.value = '50';
const $ = id => dom[id] || null;
function el(tag, attrs = {}, ...children) { const e = new Elem(tag, attrs); e.append(...children.filter(c => c != null)); return e; }
function text(n) { return typeof n === 'string' ? n : n.textContent + n.children.map(text).join(''); }
class Layer {
  constructor(url, options) { this.url = url; this.options = options; this.opacity = options.opacity; this.handlers = {}; }
  on(ev, f) { (this.handlers[ev] = this.handlers[ev] || []).push(f); return this; }
  addTo() { return this; }
  remove() { this.removed = true; }
  setUrl(u) { this.url = u; }
  setOpacity(o) { this.opacity = o; }
  bringToBack() {}
  fire(ev) { (this.handlers[ev] || []).forEach(f => f()); }
}
const panes = {};
const map = {on() {}, fitBounds() {}, invalidateSize() {}, getPane: n => panes[n], createPane: n => (panes[n] = {style: {}}),
             getSize: () => ({x: 800, y: 600}), containerPointToLayerPoint: p => Array.isArray(p) ? {x: p[0], y: p[1]} : p,
             latLngToContainerPoint: ll => ({x: ll.x, y: ll.y})};
const L = {map: () => map, tileLayer: (url, options) => new Layer(url, options),
           circleMarker: () => ({addTo() { return this; }, remove() {}})};
const calls = [], notices = [];
const notice = t => notices.push(t);
const legendItems = () => [];
const fmt = v => String(v);
const BOUNDS = [-3.6, 36.9, -3.5, 37];
async function api(path, body) {
  calls.push([path, body]);
  if (path === '/api/map/step') {
    if (body.key === '2020') throw new Error('User memory limit exceeded.');
    return {map: {url: 'step-' + body.key, bounds: BOUNDS, pixel: true}, title: body.key};
  }
  if (path === '/api/map/refresh') return {url: 'fresh-' + body.id + '-' + body.key};
  if (path === '/api/pixel') return {lat: body.lat, lon: body.lon, value: body.id * 10 + (body.key ? 1 : 0), label: 'NDVI', key: null};
}
const realTimeout = setTimeout;  // the pause of Play, short
globalThis.setTimeout = (f, ms) => realTimeout(f, ms === 1200 ? 5 : ms);
const wait = ms => new Promise(r => realTimeout(r, ms));
"""

PAGE_STEPS = r"""
(async () => {
  const out = {};
  addMap({id: 1, title: 'NDVI 2023', map: {url: 'old-1', bounds: BOUNDS, pixel: true}});
  addMap({id: 2, title: 'NDVI by year', map: {url: 'tiles-2', bounds: BOUNDS, pixel: true}, main: 'Whole period',
          steps: [{key: '2018', label: '2018'}, {key: '2019', label: '2019'}, {key: '2020', label: '2020'}]});
  // Compare with: result 1, whose tiles have expired
  $('swipesel').value = 'r1';
  await $('swipesel').onchange();
  const compared = swiped.layer;
  compared.fire('tileerror');
  await wait(10);
  out.refresh = [calls.filter(c => c[0] === '/api/map/refresh').map(c => c[1]), compared.url];
  // Opacity: both maps
  $('opacity').value = '0.3';
  $('opacity').oninput();
  out.opacity = [overlay.opacity, compared.opacity];
  // Query pixel on each side of the line (at 400 of the 800 pixels of the map)
  await pixelAt({lat: 37, lng: -3.55, x: 100, y: 10});
  out.left = [calls[calls.length - 1][1], text($('pixel'))];
  await pixelAt({lat: 37, lng: -3.55, x: 600, y: 10});
  out.right = [calls[calls.length - 1][1], text($('pixel'))];
  // Compare with the date of 2019, then go to 2019 with the slider: the date compared is the one shown
  $('swipesel').value = 'd2019';
  await $('swipesel').onchange();
  out.swipedDate = swiped && swiped.name;
  $('stepslider').value = '2';
  $('stepslider').oninput();
  await wait(10);
  out.sameDate = [$('mapstep').value, $('swipesel').value, swiped && swiped.name, Boolean($('swipeline')),
                  $('swipe').disabled, $('swipenote').textContent];
  // Play, whose next map (2020) cannot be prepared
  const before = notices.length;
  $('play').onclick();
  await wait(100);
  out.play = [calls.filter(c => c[0] === '/api/map/step' && c[1].key === '2020').length, notices.slice(before),
              playing, $('play').textContent, $('play').attrs['aria-pressed'], $('mapstep').value];
  if (playing) $('play').onclick();
  await wait(20);
  console.log(JSON.stringify(out));
})();
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_swipe_and_play_of_the_assistant():
	page = _read('ui', 'assistant.html')
	code = page[page.index('let leaflet = null'):page.index("$('snapshot').onclick")]
	run = subprocess.run(['node', '-e', PAGE + code + PAGE_STEPS], capture_output=True, text=True, timeout=60)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout.strip().splitlines()[-1])
	# the map compared asks for its tiles again when they expire, as the map shown, and takes them
	assert out['refresh'] == [[{'id': 1, 'key': ''}], 'fresh-1-']
	assert out['opacity'] == [0.3, 0.3]  # Opacity changes both maps, as in the viewer
	# Query pixel on the left of the line: the map compared (result 1), said so; on the right, the map shown
	assert out['left'][0] == {'id': 1, 'key': '', 'lon': -3.55, 'lat': 37}
	assert 'NDVI on the map on the left: 10' in out['left'][1]
	assert out['right'][0] == {'id': 2, 'key': '', 'lon': -3.55, 'lat': 37}
	assert 'NDVI on this map: 20' in out['right'][1]
	# the date compared shown on the right: no swipe left, and the select says so
	assert out['swipedDate'] == 'd2019'
	assert out['sameDate'] == ['2019', '', None, False, True, '']
	# Play stops at the map that cannot be prepared, said once
	assert out['play'][0] == 1 and len(out['play'][1]) == 1 and 'Play has stopped' in out['play'][1][0]
	assert out['play'][2:] == [None, '▶ Play', 'false', '2019']


def test_the_viewer_compares_two_layers():
	js = _read('viewer', 'assets', 'map.js')
	assert 'Compare with (left)' in js and 'gl.scissor' in js and 'SCISSOR_TEST' in js
