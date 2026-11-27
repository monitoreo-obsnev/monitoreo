"""The options of the burn severity in the Earth Engine app, without Earth Engine: the patches the perimeter keeps
(seed and largest: mo.checkKeep, the port of fire.check_keep) and the offset region (offset_region: mo.burnOffset and
mo.lessOffset, the port of services._offset), with their texts and parameters in gee/ui.js."""

import json
import os
import re
import shutil
import subprocess

import pytest

from monitoreo import fire

GEE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gee')
CORE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
function nothing() { return new Proxy(function () {}, {get: function () { return nothing(); }, apply: nothing}); }
global.ee = nothing();
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[process.argv.length - 1], f), 'utf8'), {filename: f});
});
var mo = MonitorEO;
process.stdout.write(JSON.stringify({keep: input.keep.map(function (c) {
	try { return mo.checkKeep(c[0], c[1]); } catch (e) { return 'error: ' + e.message; }
}), exported: ['checkKeep', 'burnOffset', 'lessOffset', 'burnPerimeter'].filter(function (k) {
	return typeof mo[k] === 'function';
}), none: mo.OFFSET_NONE,
	offsetArgs: /^function burnOffset\(([^)]*)\)/.exec(String(mo.burnOffset))[1]}));
"""

CASES = [[None, False], [[], False], [None, True], [[], True], [[-3.42, 37.01], False], [['-3.42', ' 37.01 '], False],
         [[-3.42, 37.01], True], [[1], False], [[1, 2, 3], False], [[200, 0], False], [[0, 95], False],
         [[-180, -90], False], [[180, 90], False], [['a', 1], False], [[None, 1], False], [['', 1], False],
         [[True, 1], False], [5, False], ['', False], [[[1], 2], False], [['1e1', '.5'], False], [None, 1],
         [None, 0], [None, ''], [[0, 0], 0]]


def _python(seed, largest):
	try:
		return fire.check_keep(seed, largest)
	except ValueError as error:
		return ('error', str(error))


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_app_keeps_the_patches_as_the_package():
	"""mo.checkKeep accepts and refuses the same seeds and largest as fire.check_keep, with the same answer, and the
	errors begin as those of the package."""
	run = subprocess.run(['node', '-e', CORE, GEE], input=json.dumps({'keep': CASES}), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	app = json.loads(run.stdout.strip().splitlines()[-1])
	assert app['exported'] == ['checkKeep', 'burnOffset', 'lessOffset', 'burnPerimeter']
	for (seed, largest), got in zip(CASES, app['keep']):
		want = _python(seed, largest)
		if isinstance(want, tuple):  # the same error: its words up to the first comma
			assert isinstance(got, str) and got.startswith('error: '), (seed, largest, got)
			assert got[len('error: '):].split(',')[0] == want[1].split(',')[0], (seed, largest, got, want)
		else:
			assert got == want, (seed, largest, got, want)
	assert app['none'].startswith('offset_region has no pixel with a dNBR')
	# as services._offset: the NBR before and after computed over the offset regions themselves, not over the region of
	# the fire (an offset region outside it works)
	assert app['offsetArgs'] == 'before, after, offsetRegions, scale, crs'


def _ui():
	with open(os.path.join(GEE, 'ui.js'), encoding='utf-8') as f:
		return f.read()


def test_the_panel_has_the_options_in_both_languages():
	"""The texts of the patches kept and the offset region are in Spanish and English, the burn severity takes seed,
	largest and offset_region in its parameters, and the note of the RdNBR no longer says it never has the offset."""
	ui = _ui()
	for key in ('keep', 'keep_all', 'keep_largest', 'keep_nearest', 'keepPoint', 'perimeterKept', 'keptLargest',
	            'keptNearest', 'offsetUse', 'offsetClear', 'offsetNone', 'offsetIs', 'offsetValue', 'offsetApply',
	            'paramsNoOffset'):
		assert len(re.findall(r'\b%s: ' % key, ui)) == 2, key
	assert "'offset_region', 'seed', 'largest']" in ui
	assert 'the mean dNBR of unburned land outside the fire' not in ui
	assert 'unless an offset region gives it' in ui and 'salvo que lo dé una región de' in ui
	assert 'mo.checkKeep(' in ui and 'mo.burnOffset(' in ui
	with open(os.path.join(GEE, 'monitoreo_app.js'), encoding='utf-8') as f:
		app = f.read()
	assert 'function checkKeep(' in app and 'offsetUse' in app  # built


STEPS = r"""
var bbox = [-3.62, 36.86, -3.5, 36.93];
out.applied = apply({analysis: 'burn_severity', parameters: {region: {bbox: bbox}, sensor: 'Landsat',
	start: '2021-06-01', end: '2021-07-31', other_start: '2022-06-01', other_end: '2022-07-31', seed: [-3.55, 36.9],
	largest: false, offset_region: {bbox: bbox}}}).report;
out.before = show('burn_severity').json.parameters;
out.none = texts(controls).filter(function (s) { return /^Offset region: /.test(s); });
button('Use this region as the offset region').opts.onClick();
out.set = texts(controls).filter(function (s) { return /^Offset region: /.test(s); });
out.after = show('burn_severity').json.parameters;
button('Clear').opts.onClick();
out.cleared = show('burn_severity').json.parameters;
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_panel_takes_the_offset_region_with_its_button():
	"""Apply lists seed and largest as given in the results (as burned_min and min_ha) and offset_region as taken with
	its button; the button stores the region of the panel, which Show writes as offset_region, and Clear removes it."""
	from test_parameters_gee import _app, _not_applied
	out = _app(STEPS)
	skipped = _not_applied(out['applied'])
	assert skipped['seed'] == skipped['largest'] == 'given in the results of the severity (Perimeter of the burned area)'
	assert skipped['offset_region'].startswith('the app takes the offset region with its button')
	assert 'offset_region' not in out['before'] and out['none'][0].startswith('Offset region: none.')
	assert out['set'] and not out['set'][0].startswith('Offset region: none.')
	assert out['after']['offset_region'] == {'bbox': [-3.62, 36.86, -3.5, 36.93]}
	assert 'offset_region' not in out['cleared']
	assert not {'seed', 'largest'} & set(out['after'])
