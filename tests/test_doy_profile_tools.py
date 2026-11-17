"""The seasonal profile by day of the year (time_series with doy and interannual or other_variable: one or two indices,
e.g. the NDSI and the NDVI on two y axes) in the command line, the MCP server and the assistant, without Earth Engine:
the series of each variable come from a fake timeseries.series, and the errors come before Earth Engine."""

import asyncio
import datetime as dt
import json
import math
import os
import re

import pytest

from monitoreo import report, services, timeseries

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
PERIOD = ['--start', '2021-01-01', '--end', '2023-12-31']
SERIES = ['series', 'NDSI', '--sensor', 'Sentinel-2', '--region', json.dumps(REGION)] + PERIOD
NAMES = ['NDSI Sentinel-2', 'NDVI Sentinel-2']


@pytest.fixture
def ee(monkeypatch):
	"""time_series without Earth Engine: a row per step of the period in one region ('park'), the NDSI high in winter
	and the NDVI in summer; the specs of the calls of the series in the list returned. Connecting to Earth Engine
	(services.init) fails."""
	calls = []

	def series(spec, regions, step='monthly', metric='mean', stat='mean', scale=None, progress=None, steps=None):
		calls.append(spec)
		if step == 'daily':
			first, last = (dt.date.fromisoformat(d) for d in spec['period'])
			dates = [(first + dt.timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]
		else:
			dates = [a for a, _ in timeseries.bins(spec, step)]
		winter = {d: math.cos(2 * math.pi * (int(d[5:7]) - 1) / 12) for d in dates}
		value = {'NDSI': lambda d: winter[d] / 2, 'NDVI': lambda d: 0.3 - winter[d] / 4}.get(spec.get('index'),
		                                                                                    lambda d: 0.1)
		rows = [{'region': 'park', 'date': d, 'value': value(d), 'n_pixels': 5, 'n_images': 1} for d in dates]
		return rows, scale or 10.0

	def init(*a, **k):
		raise AssertionError('it connects to Earth Engine')

	monkeypatch.setattr(services.areas, 'region', lambda region: 'regions')
	monkeypatch.setattr(services.timeseries, 'series', series)
	monkeypatch.setattr(services, 'init', init)
	monkeypatch.setattr(services, 'eecu_warning', lambda *a, **k: None)
	return calls


@pytest.fixture
def connected(ee, monkeypatch):
	"""As ee, connecting to Earth Engine (services.init, as the command line does before computing)."""
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	return ee


# The command line ---------------------------------------------------------------------------------------------------

def test_the_command_line_draws_two_indices_on_two_axes(connected, capsys, tmp_path):
	from monitoreo import cli
	csv, png = str(tmp_path / 'profile.csv'), str(tmp_path / 'profile.png')
	cli.main(SERIES + ['--doy', '--other-variable', 'NDVI', '--other-ylim=-0.5,1', '--csv', csv, '--png', png])
	assert [s['index'] for s in connected] == ['NDSI', 'NDVI']
	out = capsys.readouterr().out.splitlines()
	assert out[0].split() == timeseries.PROFILE_COLUMNS  # the profile, not the rows of each year
	assert out[1].split() == ['park', 'NDSI', 'Sentinel-2', '1', '1', 'Jan', '0.5', '3']  # the median of 3 Januaries
	assert out[13].split()[:6] == ['park', 'NDVI', 'Sentinel-2', '1', '1', 'Jan']  # then the other variable
	assert len([line for line in out if line.startswith('park')]) == 2 * 12
	last = out[-1]
	assert last.startswith('NDSI Sentinel-2 and NDVI Sentinel-2 | 2021-01-01 / 2023-12-31 | monthly mean, spatial '
	                       'mean | median of the years by day of the year')
	assert ' | scale NDSI Sentinel-2 10 m, NDVI Sentinel-2 10 m | units NDSI Sentinel-2 [unitless], NDVI Sentinel-2 ' \
	       '[unitless] | left y axis (NDSI Sentinel-2) from the data, right y axis (NDVI Sentinel-2) -0.5 to 1' in last
	assert f' | CSV {csv}' in last
	with open(csv, encoding='utf-8') as f:
		assert f.readline().strip().split(',') == timeseries.PROFILE_COLUMNS + timeseries.PROFILE_META
	pytest.importorskip('matplotlib')
	assert last.endswith(f' | chart {png}') and os.path.getsize(png) > 0


def test_the_command_line_with_one_index_and_a_metric_between_the_years(connected, capsys):
	from monitoreo import cli
	cli.main(SERIES + ['--step', '16-day', '--doy', '--interannual', 'P25', '--ylim', '-0.5', '0.8'])
	out = capsys.readouterr().out.splitlines()
	assert out[0].split() == [c for c in timeseries.PROFILE_COLUMNS if c != 'variable']  # one variable
	assert out[2].split()[:4] == ['park', '1', '17', 'Jan']  # the second 16-day period, on 17 January
	assert out[-1].endswith('| p25 of the years by day of the year | scale 10 m | unit [unitless] | y axis -0.5 to 0.8')
	cli.main(SERIES + ['--doy', '--interannual', 'cv'])  # without --ylim: the y axis from the data
	last = capsys.readouterr().out.splitlines()[-1]
	assert last.endswith('| cv of the years by day of the year | scale 10 m | unit [%] | y axis from the data')


def test_the_command_line_passes_the_options(monkeypatch):
	"""The options reach services.time_series: --ylim with negative numbers, also with commas."""
	from monitoreo import cli
	calls = []

	def fake(region, **kw):
		calls.append(kw)
		return {'rows': [], 'profile': [], 'variables': NAMES, 'units': {}, 'scales': {}, 'csv': None, 'chart': None,
		        'scale': 10.0, 'unit': '', 'title': 't', 'ylim': None, 'other_ylim': None}
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	monkeypatch.setattr(services, 'time_series', fake)
	cli.main(SERIES + ['--doy', '--interannual', 'mean', '--other-variable', 'NDVI', '--other-sensor', 'Landsat',
	                   '--ylim', '-1', '1', '--other-ylim', '-0.2,0.9'])
	kw = calls[-1]
	assert (kw['doy'], kw['interannual'], kw['other_variable'], kw['other_sensor']) == (True, 'mean', 'NDVI', 'Landsat')
	assert kw['ylim'] == [-1.0, 1.0] and kw['other_ylim'] == [-0.2, 0.9]
	cli.main(SERIES + ['--doy', '--ylim=-1,1'])  # a line per year, with its y axis
	assert calls[-1]['ylim'] == [-1.0, 1.0] and calls[-1]['interannual'] is None and calls[-1]['other_variable'] is None


def test_the_lists_of_numbers_of_the_command_line():
	from monitoreo import cli
	assert cli._list_args(['--ylim=-1,1']) == ['--ylim', '-1', '1']
	assert cli._list_args(['--other-ylim', '-1,', '1']) == ['--other-ylim', '-1', '1']
	assert cli._list_args(['--bbox=-3.6,36.9,-2.6,37.3']) == ['--bbox', '-3.6', '36.9', '-2.6', '37.3']
	assert cli._list_args(['--bbox', '-3.6,36.9,-2.6,37.3']) == ['--bbox', '-3.6', '36.9', '-2.6', '37.3']
	region = ['--region', '{"bbox": [-3.6, 36.9, -2.6, 37.3]}']
	assert cli._list_args(region) == region  # only the lists of numbers


@pytest.mark.parametrize('more, message', [
	(['--interannual', 'median'], '--interannual: only with --doy'),
	(['--other-variable', 'NDVI', '--ylim', '-1', '1'], '--other-variable, --ylim: only with --doy'),
	(['--doy', '--other-sensor', 'Modis'], '--other-sensor and --other-ylim are those of the variable of the right axis'),
	(['--doy', '--interannual', 'median', '--other-ylim', '0', '1'], 'give --other-variable'),
	(['--doy', '--ylim', '-1'], 'expected 2 arguments'),
])
def test_the_command_line_refuses_before_earth_engine(ee, capsys, more, message):
	from monitoreo import cli
	with pytest.raises(SystemExit) as e:
		cli.main(SERIES + more)
	assert e.value.code == 2 and message in capsys.readouterr().err and not ee


@pytest.mark.parametrize('more, message', [
	(['--doy', '--interannual', 'sum'], 'unknown metric between the years (interannual) sum'),
	(['--doy', '--other-variable', 'NDVI', '--other-sensor', 'Copernicus'], 'other_variable (the right axis): '),
	(['--doy', '--other-variable', 'NDSI'], 'NDSI Sentinel-2 is already the variable of the left axis'),
	(['--doy', '--interannual', 'mean', '--ylim', '1', '-1'], 'must be smaller than the second'),
	(['--step', 'annual', '--doy', '--interannual', 'mean'], 'needs a step shorter than a year'),
])
def test_the_errors_of_the_services_in_the_command_line(connected, more, message):
	from monitoreo import cli
	with pytest.raises(SystemExit) as e:
		cli.main(SERIES + more)
	assert str(e.value.code).startswith('ERROR: ') and message in str(e.value.code) and not connected


def test_the_help_of_the_command_line(capsys):
	from monitoreo import cli
	with pytest.raises(SystemExit):
		cli.main(['series', '--help'])
	text = ' '.join(capsys.readouterr().out.split())
	for option in ('--interannual METRIC', '--other-variable VARIABLE', '--other-sensor OTHER_SENSOR', '--ylim MIN MAX',
	               '--other-ylim MIN MAX'):
		assert option in text, option
	assert 'default: from the minimum to the maximum of the values of its variable' in text and '-1 to 1' not in text
	assert '--other-variable' in cli.__doc__ and 'seasonal profile' in cli.__doc__


# The MCP server ------------------------------------------------------------------------------------------------------

@pytest.fixture
def mcp(ee, monkeypatch, tmp_path):
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	return mcp_server


def test_the_mcp_server_answers_the_profile(mcp, tmp_path):
	out = mcp.time_series(REGION, 'NDSI', 'Sentinel-2', start='2021-01-01', end='2023-12-31', doy=True,
	                      other_variable='NDVI', other_ylim=[-0.5, 1])
	res = json.loads(out[0])
	assert res['variables'] == NAMES and res['interannual'] == 'median'
	assert res['units'] == {n: '[unitless]' for n in NAMES} and res['scales'] == {n: 10.0 for n in NAMES}
	assert res['ylim'] is None and res['other_ylim'] == [-0.5, 1]  # from the data, and the one given
	assert (res['ylabel'], res['other_ylabel']) == ('NDSI Sentinel-2 [unitless]', 'NDVI Sentinel-2 [unitless]')
	assert len(res['profile']) == 2 * 12 and list(res['profile'][0]) == timeseries.PROFILE_COLUMNS
	assert res['profile'][0]['label'] == 'Jan' and res['profile'][0]['n_years'] == 3
	assert len(res['rows']) == 2 * 36 and 'note' not in res  # the values of each year, as they fit
	assert res['title'].endswith('| median of the years by day of the year')
	assert {'readme', 'references', 'credits'} <= set(res)
	assert re.fullmatch(r'profile_NDSI_Sentinel-2_NDVI_Sentinel-2_monthly_mean_2021-01-01_2023-12-31_\d{8}-\d{6}\.csv',
	                    os.path.basename(res['csv']))
	with open(res['csv'], encoding='utf-8') as f:
		assert f.readline().strip().split(',') == timeseries.PROFILE_COLUMNS + timeseries.PROFILE_META
	if res['chart']:  # with matplotlib, the chart of the profile
		assert len(out) == 2 and res['chart'].endswith('.png')


def test_the_mcp_server_answers_a_long_profile_in_part(mcp):
	"""As compare_series, the profile (its first rows when there are many: a day of the year each), and the values of
	each year only when they fit."""
	res = json.loads(mcp.time_series(REGION, 'NDVI', 'Sentinel-2', start='2021-01-01', end='2021-12-31', step='daily',
	                                 doy=True, interannual='max')[0])
	assert len(res['profile']) == mcp.MAX_ROWS_SHOWN and 'rows' not in res
	assert res['note'] == (f'365 rows of the profile: the first {mcp.MAX_ROWS_SHOWN} are shown, all of them are in the '
	                       'CSV file; the 365 values of each year are not shown (time_series with doy, without '
	                       'interannual nor other_variable, gives them for each variable)')
	assert res['variables'] == ['NDVI Sentinel-2'] and res['other_ylim'] is None and res['other_ylabel'] is None
	assert re.fullmatch(r'profile_NDVI_Sentinel-2_daily_mean_2021-01-01_2021-12-31_\d{8}-\d{6}\.csv',
	                    os.path.basename(res['csv']))


def test_the_mcp_server_with_a_line_per_year(mcp):
	"""Without interannual nor other_variable, a line per year as before: the rows, and the y axis given."""
	res = json.loads(mcp.time_series(REGION, 'NDVI', 'Sentinel-2', start='2021-01-01', end='2022-12-31', doy=True,
	                                 ylim=[0, 1])[0])
	assert len(res['rows']) == 24 and 'profile' not in res and 'variables' not in res and res['ylim'] == [0, 1]
	assert re.fullmatch(r'NDVI_Sentinel-2_monthly_mean_2021-01-01_2022-12-31_\d{8}-\d{6}\.csv',
	                    os.path.basename(res['csv']))
	res = json.loads(mcp.time_series(REGION, 'NDVI', 'Sentinel-2', start='2021-01-01', end='2022-12-31')[0])
	assert 'ylim' not in res and len(res['rows']) == 24  # without doy, as before


@pytest.mark.parametrize('kw, message', [
	({'interannual': 'median'}, 'interannual: only for the chart by day of the year (doy)'),
	({'doy': True, 'other_ylim': [0, 1]}, 'give other_variable'),
	({'doy': True, 'ylim': [1, 0]}, 'ylim: the first number of the y axis (1) must be smaller than the second (0)'),
	({'doy': True, 'other_variable': 'ELEVATION', 'other_sensor': 'Copernicus'}, 'other_variable (the right axis): '),
	({'doy': True, 'other_variable': 'IDAHO_EPSCOR/TERRACLIMATE'}, 'the variable of the right axis is a variable of '
	                                                               'the catalog of MonitorEO'),
])
def test_the_mcp_server_refuses_before_earth_engine(mcp, ee, kw, message):
	with pytest.raises(mcp.ToolError, match=re.escape(message)):
		mcp.time_series(REGION, 'NDSI', 'Sentinel-2', start='2021-01-01', end='2023-12-31', **kw)
	assert not ee


def test_the_mcp_server_takes_the_axes_as_lists_of_numbers(mcp, ee):
	"""As the server calls the tool, with its arguments checked against its schema."""
	asyncio.run(mcp.server.call_tool('time_series', {'region': REGION, 'variable': 'NDSI', 'sensor': 'Modis',
	                                                 'start': '2021-01-01', 'end': '2021-12-31', 'step': '16-day',
	                                                 'doy': True, 'interannual': 'mean', 'other_variable': 'NDVI',
	                                                 'other_sensor': 'Sentinel-2', 'ylim': [0, 100],
	                                                 'other_ylim': [-1, 1]}))
	assert [(s['index'], s['sensor']) for s in ee] == [('NDSI', 'Modis'), ('NDVI', 'Sentinel-2')]


def test_the_mcp_server_says_it(mcp):
	text = ' '.join(mcp.INSTRUCTIONS.split())
	assert 'the seasonal profile of one or two variables on two y axes with interannual' in text
	assert 'other_variable (and other_sensor)' in text and '-1 to 1' not in text
	assert 'each y axis goes from the minimum to the maximum of its own variable, or as ylim and other_ylim say' in text
	doc = ' '.join(mcp.time_series.__doc__.split())
	assert 'with interannual (the metric between the years of each step, default median) or other_variable' in doc
	assert "ylim, other_ylim: [min, max] of the y axes (default: the data's)" in doc


# The assistant -------------------------------------------------------------------------------------------------------

def _model_tools(mcp):
	from monitoreo import assistant
	return assistant.model_tools([assistant._json(t) for t in asyncio.run(mcp.server.list_tools())])


def test_the_assistant_knows_the_profile(mcp):
	from monitoreo import assistant
	text = ' '.join(assistant.instructions().split())
	assert 'The seasonal profile of one or two indices on two axes («NDSI and NDVI by day of the year»): doy with ' \
	       'interannual' in text
	assert 'other_variable (and other_sensor) for the right axis' in text
	assert '(else each axis goes from the minimum to the maximum of the values of its own variable)' in text
	assert 'indices: -1 to 1' not in text
	tools = _model_tools(mcp)
	series = next(t['function'] for t in tools if t['function']['name'] == 'time_series')
	props = series['parameters']['properties']
	assert props['ylim'] == props['other_ylim'] == {'type': 'array', 'items': {'type': 'number'}}
	assert props['interannual'] == props['other_variable'] == props['other_sensor'] == {'type': 'string'}
	assert series['parameters']['required'] == ['region', 'start', 'end']
	assert len(json.dumps(tools)) < 42500  # the tools of the small models (see test_assistant)
	# the lists that small models give as text, decoded
	args = assistant.fix_args('time_series', {'region': REGION, 'variable': 'NDSI', 'sensor': 'Sentinel-2', 'doy': True,
	                                          'other_variable': 'NDVI', 'ylim': '[-1, 1]', 'other_ylim': ''}, tools)
	assert args['ylim'] == [-1, 1] and args['other_variable'] == 'NDVI' and 'other_ylim' not in args


def test_the_assistant_shows_the_profile(mcp, monkeypatch, tmp_path):
	"""The model asks for the NDSI and the NDVI by day of the year: the card of the result has the chart, the table of
	the profile, its title and how it was computed (the other variable, the metric between the years, the axes)."""
	from monitoreo import assistant
	monkeypatch.setattr(assistant, 'LOG', str(tmp_path / 'assistant.log'))
	monkeypatch.setattr(assistant, 'OUTPUT', str(tmp_path))
	asked = {'region': REGION, 'variable': 'NDSI', 'sensor': 'Sentinel-2', 'start': '2021-01-01', 'end': '2023-12-31',
	         'step': 'monthly', 'doy': True, 'interannual': 'median', 'other_variable': 'NDVI'}
	answers = iter([{'content': '', 'tool_calls': [{'function': {'name': 'time_series', 'arguments': asked}}]},
	                {'content': 'Done.'}])
	monkeypatch.setattr(assistant, 'chat_model', lambda settings, system, messages, tools: next(answers))
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)

	class Fake(assistant.Assistant):
		async def call(self, name, args):
			if name != 'time_series':  # the map of the period
				return 'not here', [], []
			out = mcp.time_series(**args)
			return None, [out[0]], ['data:image/png;base64,iVBORw0KGgo='] if len(out) > 1 else []

	tools = _model_tools(mcp)

	async def run():
		a = Fake({**assistant.DEFAULTS, 'project': 'p', 'ollama': 'http://127.0.0.1:1'})
		a.tools = tools
		return [e async for e in a.chat('NDSI y NDVI por día del año, 2021-2023')]

	events = asyncio.run(run())
	card = next(e for e in events if e['type'] == 'result')
	assert card['title'].startswith('Monthly profile of NDSI (Sentinel-2) and NDVI (Sentinel-2) by day of the year, '
	                                '2021-2023: median of the years')
	assert card['table']['labels'] == ['Variable', 'Step of the year', 'Day of the year', 'Value', 'Unit', 'Years']
	assert len(card['table']['rows']) == 2 * 12 and card['table']['rows'][0][:3] == ['NDSI Sentinel-2', 'Jan', '1']
	facts = dict(card['facts'])
	assert facts['Other variable (right axis)'].startswith('Normalized Difference Vegetation Index (NDVI)')
	assert facts['Between the years'].startswith('median of the values of each month')
	assert facts['Chart'].endswith('NDSI (Sentinel-2) on the left axis (from the data), NDVI (Sentinel-2) on the right '
	                               'axis (from the data)')
	if card['image']:  # with matplotlib, the chart
		assert card['image'].startswith('data:image/png')
	# the CSV, its README and its parameters (monitoreo.parameters)
	assert [f['name'].rsplit('.', 1)[-1] for f in card['files']] == ['csv', 'txt', 'json']
	assert report.is_profile(asked)
