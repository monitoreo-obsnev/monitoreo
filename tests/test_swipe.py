"""The swipe and the time sliders (the split maps and the time sliders of geemap), without Earth Engine: in the Earth
Engine app (gee/ui.js in Node, with the ui and ee of tests/test_themes.py, which compute nothing), the swipe of the two
periods of a comparison and the slider of the frames of an animation; in the assistant (ui/assistant.html) and in the
viewer of results (viewer/assets/map.js), their controls."""

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
answer = {value_p5: -0.1, value_p95: 0.1};
button('Add to the map').opts.onClick();
var swipe = inResults('Button', function (w) { return w.opts.label === 'Swipe: the two periods side by side'; })[0];
out.swipeButton = Boolean(swipe);
answer = {reference_p5: 0.2, reference_p95: 0.7, other_p5: 0.1, other_p95: 0.8};
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
answer = {value_p5: 0.1, value_p95: 0.8};
button('Make the animation').opts.onClick();
var slider = inResults('Slider')[0];
out.slider = slider ? [slider.opts.min, slider.opts.max] : null;
slider.opts.onChange(1);
out.frame = [layers[layers.length - 1], texts(results_()).indexOf('February 2025') >= 0];
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_swipe_and_the_frames_of_the_app():
	from test_themes import PANEL, _build
	script = PANEL[:PANEL.index('var out = {};')] + STEPS
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {}}
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout.strip().splitlines()[-1])
	assert out['swipeButton'] and out['split'] == 'SplitPanel' and out['wipe'] is True and out['note'] == 1
	assert out['back'] is True
	assert out['slider'] == [0, 11]  # the year of the app by default: a frame per month
	assert out['frame'] == ['January 2025', True]  # the frame on the map: the first one, then that of the slider


def _read(*parts):
	with open(os.path.join(SRC, *parts), encoding='utf-8') as f:
		return f.read()


def test_the_assistant_has_the_slider_and_the_swipe():
	page = _read('ui', 'assistant.html')
	for id_ in ('stepslider', 'play', 'swipesel', 'swipe', 'swipebar'):
		assert f'id="{id_}"' in page, id_
	assert "createPane('swipe')" in page and 'style.clip' in page  # the map compared, clipped at the line
	assert re.search(r"\$\('mapstep'\)\.onchange = \(\) => \{ syncSlider\(\);", page)


def test_the_viewer_compares_two_layers():
	js = _read('viewer', 'assets', 'map.js')
	assert 'Compare with (left)' in js and 'gl.scissor' in js and 'SCISSOR_TEST' in js
