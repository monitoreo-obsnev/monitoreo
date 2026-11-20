"""The panel of the Earth Engine app (gee/ui.js) folds its groups under their titles: only the region and the variable
are open at first, each section opens and closes with its button, stays as it is when the panel is drawn again, and
Apply parameters opens the section of the analysis it sets. Run in Node with the ui and ee of tests/test_themes.py."""

import json
import os
import shutil
import subprocess

import pytest

from monitoreo import catalog

GEE = os.path.join(os.path.dirname(__file__), '..', 'gee')

STEPS = r"""
// the sections: [the label of the button, whether its panel is shown], in the order of the panel
function sections() {
	var kids = controls.children, out = [];
	kids.forEach(function (w, i) {
		if (w.kind === 'Button' && /^[▸▾] /.test(w.opts.label)) {
			out.push([w.opts.label, kids[i + 1].styles.shown]);
		}
	});
	return out;
}
function head(title) {
	return find(controls, 'Button', function (w) { return w.opts.label.slice(2).indexOf(title) === 0; })[0];
}
var out = {first: sections()};
head('Map').opts.onClick();
out.map = sections().filter(function (s) { return s[0].indexOf('Map') === 2; });
head('Region').opts.onClick();
out.region = sections()[0];
button('Español').opts.onClick();  // the panel is drawn again, in Spanish: the sections keep as they were
out.spanish = sections();
button('English').opts.onClick();
out.folded_still_has_buttons = Boolean(button('Compute the time series'));
// Apply parameters of a time series unfolds its section
var box = find(controls, 'Textbox', function (w) { return w.opts.placeholder === input.hint; })[0];
box.opts.value = JSON.stringify({monitoreo: input.version, analysis: 'time_series', parameters: {}});
button('Apply parameters').opts.onClick();
out.applied = sections().filter(function (s) { return s[0].indexOf('Time series') === 2; });
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_panel_folds_its_groups_under_their_titles():
	from test_themes import PANEL, _build
	script = PANEL[:PANEL.index('var out = {};')] + STEPS
	build = _build()
	data = {'community': build.community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {},
	        'hint': 'Paste here the parameters of an analysis (JSON)', 'version': __import__('monitoreo').__version__}
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout.strip().splitlines()[-1])
	titles = [s[0][2:].split(' · ')[0] for s in out['first']]
	assert titles == ['Region', 'Variable and period', 'Pixel filters', 'Map', 'Area by class',
	                  'Gradients (elevation bands and profiles)', 'Animation (timelapse)', 'Time series',
	                  'Trends (Mann-Kendall and Sen)', 'Parameters of the analysis (JSON)', 'About MonitorEO']
	shown = {s[0][2:].split(' · ')[0]: s[1] for s in out['first']}
	assert [k for k, v in shown.items() if v] == ['Region', 'Variable and period']  # the others folded
	assert all(s[0].startswith('▸ ') for s in out['first'] if not s[1])
	assert out['map'] == [['▾ Map', True]]  # a click unfolds it
	assert out['region'][1] is False and out['region'][0].startswith('▸ Region')  # and folds Region again
	spanish = {s[0][2:].split(' · ')[0]: s[1] for s in out['spanish']}
	assert spanish['Mapa'] is True and spanish['Región'] is False and spanish['Variable y periodo'] is True
	assert out['folded_still_has_buttons']  # folded sections are only hidden
	assert out['applied'] == [['▾ Time series', True]]
