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
	assert 'Chart: a line per year over the days of the year' in text
	assert report.item_title('time_series', ARGS).endswith(', by day of the year')
	spec = {'title': 'Snow', 'summary': 'Snow', 'region': {'name': 'Sierra Nevada'},
	        'results': [{'tool': 'time_series', 'args': ARGS, 'result': result}]}
	folder = tmp_path / 'report'
	folder.mkdir()
	rep = publish.build(spec, 'snow', str(tmp_path), [], None, str(folder))
	assert rep['results'][0]['chart'] == 'doy' and rep['results'][0]['ylabel'] == 'NDSI'
	assert publish.check_report(rep, str(folder)) == []


@pytest.fixture
def calls(monkeypatch):
	out = []

	def fake(region, variable=None, sensor=None, start=None, end=None, step='monthly', metric='mean', stat='mean',
	         season=None, quality=None, scale=None, csv=None, chart=None, progress=None, doy=False, **source):
		out.append({'doy': doy, 'step': step, 'chart': chart})
		return {'rows': _rows() if doy else [], 'csv': csv, 'chart': None, 'scale': 500.0, 'unit': '', 'ylabel': '',
		        'title': 'NDSI', 'n_steps': 6, 'regions': ['park']}
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
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
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
check('A line per year, over the days of the year').opts.onChange(true);
answer = 'rows';
button('Compute the time series').opts.onClick();
var chart = find(root.children[2], 'Chart')[0];
out.head = chart.opts.table[0];
out.type = chart.opts.type;
out.axis = chart.opts.options.hAxis.title;
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_app_draws_a_line_per_year():
	from test_themes import PANEL, _build
	script = PANEL[:PANEL.index('var out = {};')] + STEPS
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {}}
	run = subprocess.run(['node', '-e', script, os.path.join(os.path.dirname(__file__), '..', 'gee')],
	                     input=json.dumps(data), capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout.strip().splitlines()[-1])
	assert out == {'head': ['Day of the year', '2025'], 'type': 'LineChart', 'axis': 'Day of the year'}
