"""The snow cover days (variable SCD, metric days) are drawn with a bar per step (a bar per day with images with the
daily step), with their table, in every tool: the PNG of the package (that of the command line, the MCP server, the
assistant and QGIS), the README and the report, and the results viewer; the other variables keep their lines."""

import datetime as dt
import json
import os
import shutil
import subprocess

import pytest

from monitoreo import charts, readme, timeseries

REGION = {'bbox': [-3.40, 37.03, -3.33, 37.07]}
ARGS = {'region': REGION, 'variable': 'SCD', 'sensor': 'Modis', 'start': '2022-02-01', 'end': '2022-02-07',
        'step': 'daily', 'metric': 'days'}


def _rows():
	"""Two regions, three days with images; the lake has no clear pixel on the second day."""
	return [{'region': g, 'date': d, 'value': None if (g, d) == ('lake', '2022-02-02') else 0.5 + (g == 'park') / 4,
	         'n_pixels': 0 if (g, d) == ('lake', '2022-02-02') else 40, 'n_images': 1}
	        for g in ('lake', 'park') for d in ('2022-02-01', '2022-02-02', '2022-02-07')]


def test_the_width_of_the_bars():
	day = dt.date(2022, 2, 1)
	assert charts.bar_width([day, day + dt.timedelta(days=1), day + dt.timedelta(days=6)]) == pytest.approx(0.8)
	assert charts.bar_width([dt.date(2022, m, 1) for m in (1, 2, 3)]) == pytest.approx(0.8 * 28)  # February
	assert charts.bar_width([day, day]) == pytest.approx(0.8)  # a single date: a day


def test_the_png_has_a_bar_per_step_and_region(monkeypatch, tmp_path):
	pytest.importorskip('matplotlib')
	from matplotlib.axes import Axes
	bars, lines = [], []
	bar, plot = Axes.bar, Axes.plot
	monkeypatch.setattr(Axes, 'bar', lambda self, x, h, *a, **k: bars.append((list(x), list(h), k)) or bar(self, x, h, *a, **k))
	monkeypatch.setattr(Axes, 'plot', lambda self, *a, **k: lines.append(a) or plot(self, *a, **k))
	png = charts.time_series_png(_rows(), str(tmp_path / 'scd.png'), 'SCD', 'Snow Cover Days (SCD) [days]', bars=True)
	assert png[:8] == b'\x89PNG\r\n\x1a\n' and not lines
	(lake_x, lake_h, lake_k), (park_x, park_h, park_k) = bars
	assert lake_h == [0.5, 0.5] and park_h == [0.75, 0.75, 0.75]  # no bar where a day has no value
	assert lake_k['width'] == park_k['width'] == pytest.approx(0.4)  # 80 % of a day, shared by the two regions
	assert park_x[0] - lake_x[0] == dt.timedelta(days=0.4)  # side by side around the day
	assert lake_k['label'] == 'lake'
	# under the bars, the label of each step: the year of each season (in which it starts), the month or the day
	ticks = []
	xticks = Axes.set_xticks
	monkeypatch.setattr(Axes, 'set_xticks', lambda self, x, labels=None, **k: ticks.append(labels) or
	                    xticks(self, x, labels, **k))
	seasons = [{'region': 'park', 'date': f'{y}-10-01', 'value': 150.0, 'n_pixels': 9, 'n_images': 40}
	           for y in (2017, 2018, 2019)]
	charts.time_series_png(seasons, str(tmp_path / 'seasons.png'), bars=True)
	months = [dict(r, date=f'2021-{m}-01') for r, m in zip(seasons, (10, 11, 12))]
	charts.time_series_png(months, str(tmp_path / 'months.png'), bars=True)
	days = [dict(r, date=(dt.date(2022, 1, 1) + dt.timedelta(days=k)).isoformat()) for k in range(60) for r in seasons[:1]]
	charts.time_series_png(days, str(tmp_path / 'days.png'), bars=True)
	assert ticks[0] == ['2017', '2018', '2019'] and ticks[1] == ['2021-10', '2021-11', '2021-12']
	assert ticks[2][:2] == ['2022-01-01', '2022-01-04'] and len(ticks[2]) <= 24  # one in every few days
	# the other variables: a line per region, as before
	bars.clear()
	charts.time_series_png(_rows(), str(tmp_path / 'ndvi.png'), 'NDVI', 'NDVI')
	assert not bars and len(lines) == 2


def test_the_readme_and_the_report_say_the_bars(tmp_path):
	from monitoreo import publish
	csv = tmp_path / 'scd.csv'
	timeseries.write_csv(_rows(), str(csv), {'variable': 'SCD', 'step': 'daily', 'metric': 'days'})
	result = {'rows': _rows(), 'csv': str(csv), 'unit': '[days]', 'ylabel': 'Snow Cover Days (SCD) [days]',
	          'title': 'Daily SCD', 'scale': 500.0, 'bars': True}
	text = ' '.join(readme.text('time_series', ARGS, result, computed='2026-11-17T20:00:00+01:00').split())
	assert 'Chart: a bar per step (each day with images: the share of its clear pixels with snow, 0 to 1 day)' in text
	monthly = dict(ARGS, step='monthly', start='2021-10-01', end='2022-05-31')
	text = ' '.join(readme.text('time_series', monthly, result).split())
	assert 'Chart: a bar per step' in text and 'each day with images' not in text
	assert 'a bar per step' not in readme.text('time_series', dict(ARGS, variable='NDSI', metric='mean'), result)
	# the results viewer: the entry of the series says bars, those of the other variables do not
	folder = tmp_path / 'report'
	folder.mkdir()
	spec = {'title': 'Snow', 'summary': 'Snow', 'region': {'name': 'Lakes'},
	        'results': [{'tool': 'time_series', 'args': ARGS, 'result': result},
	                    {'tool': 'time_series', 'args': dict(ARGS, variable='NDSI', metric='mean'),
	                     'result': dict(result, bars=False)}]}
	rep = publish.build(spec, 'snow', str(tmp_path), [], None, str(folder))
	scd, ndsi = rep['results']
	assert scd['chart'] == 'series' and scd['bars'] is True and scd['step'] == 'daily'
	assert ndsi['chart'] == 'series' and 'bars' not in ndsi
	assert publish.check_report(rep, str(folder)) == []


VIEWER = r"""
var fs = require('fs'), vm = require('vm');
var spec = null;
function el(tag, attrs) {
	return {tag: tag, attrs: attrs, clientWidth: 800, append: function () {}, replaceChildren: function () {}};
}
global.window = {matchMedia: function () { return {matches: false, addEventListener: function () {}}; }};
global.document = {documentElement: {}};
global.getComputedStyle = function () { return {colorScheme: 'light', getPropertyValue: function () { return ''; }}; };
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
MO.chart.render(el('div'), {id: 'r', chart: 'series', csv: 'scd.csv', step: 'daily', bars: true,
	ylabel: 'Snow Cover Days (SCD) [days]'}, '').then(function () {
	console.log(JSON.stringify({mark: spec.mark, encoding: spec.encoding, n: spec.data.values.length}));
});
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_viewer_draws_bars(tmp_path):
	from monitoreo import publish
	csv = tmp_path / 'scd.csv'
	timeseries.write_csv(_rows(), str(csv), {})
	path = os.path.join(os.path.dirname(publish.__file__), 'viewer', 'assets', 'charts.js')
	run = subprocess.run(['node', '-e', VIEWER, path], input=csv.read_text(encoding='utf-8'), capture_output=True,
	                     text=True, timeout=60)
	assert run.returncode == 0, run.stderr
	spec = json.loads(run.stdout.strip().splitlines()[-1])
	assert spec['mark']['type'] == 'bar' and spec['n'] == 5  # no bar where a day has no value
	assert spec['encoding']['x']['field'] == 'step' and spec['encoding']['xOffset'] == {'field': 'region',
	                                                                                      'sort': ['lake', 'park']}
	assert spec['encoding']['y']['title'] == 'Snow Cover Days (SCD) [days]'
