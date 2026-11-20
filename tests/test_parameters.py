"""The parameters of an analysis as JSON, the same in every tool (monitoreo.parameters, issue #85), without Earth
Engine: what they keep, what can be applied and why not, the file next to the files of each result, the commands
parameters and run of the command line, and the tools save_parameters and apply_parameters of the MCP server (and of
the assistant, which takes its tools)."""

import inspect
import json

import pytest

from monitoreo import __version__, cli, parameters, services

REGION = {'wdpa_id': 389011}
def _fake(name, out, got):
	"""The function NAME of the services faked, with its signature (what check reads): its arguments go to GOT."""
	def fake(**kw):
		got.update(kw)
		return dict(out)
	fake.__signature__ = inspect.signature(getattr(services, name))
	return fake


ARGS = {'region': REGION, 'variable': 'NDVI', 'sensor': 'Landsat', 'start': '2023-01-01', 'end': '2026-10-30',
        'step': 'monthly', 'metric': 'mean', 'stat': 'mean'}


def test_make_keeps_what_was_computed_and_not_the_outputs():
	p = parameters.make('time_series', dict(ARGS, csv='a.csv', chart='a.png', progress=print, season=None, where=[]))
	assert p == {'monitoreo': __version__, 'analysis': 'time_series', 'parameters': ARGS}
	assert json.loads(json.dumps(p)) == p  # plain JSON
	# the data of Earth Engine by their ID (the **source of the services) as parameters of their own
	p = parameters.make('download_image', {'region': REGION, 'source': {'collection': 'X/Y', 'band': 'b1'}})
	assert p['parameters'] == {'region': REGION, 'collection': 'X/Y', 'band': 'b1'}
	# the map of the MCP server with figure is the figure of the services
	assert parameters.make('map_layer', {'region': REGION, 'figure': True, 'quick': True})['analysis'] == 'map_figure'
	with pytest.raises(ValueError, match='not an analysis of MonitorEO'):
		parameters.make('list_variables', {})


def test_every_analysis_is_a_function_of_the_services():
	for analysis in parameters.ANALYSES:
		assert callable(getattr(services, analysis)), analysis
		assert 'region' in parameters.accepted(analysis) or analysis == 'transect', analysis
		assert not parameters.accepted(analysis) & {'csv', 'chart', 'path', 'progress'}, analysis


def test_read_takes_a_dict_a_text_a_file_and_the_flat_form(tmp_path):
	saved = parameters.save('time_series', ARGS, str(tmp_path / 'p.json'))
	for source in (saved, open(saved, encoding='utf-8').read(), json.load(open(saved, encoding='utf-8'))):
		assert parameters.read(source)['parameters'] == ARGS
	flat = dict(ARGS, analysis='time_series', monitoreo='0.3.41')  # as the issue wrote it
	assert parameters.read(flat) == {'monitoreo': '0.3.41', 'analysis': 'time_series', 'parameters': ARGS}
	with pytest.raises(ValueError, match='not valid JSON'):
		parameters.read('{"analysis": ')
	with pytest.raises(ValueError, match='neither a JSON object'):
		parameters.read(str(tmp_path / 'missing.json'))


def test_check_says_what_cannot_be_applied_and_why():
	c = parameters.check({'monitoreo': '0.3.41', 'analysis': 'time_series',
	                      'parameters': dict(ARGS, colour='red', csv='x.csv')})
	assert c['parameters'] == ARGS and c['monitoreo'] == '0.3.41' and '0.3.41' in c['note']
	assert [(p['name'], p['reason']) for p in c['not_applied']] == [
		('colour', f'not a parameter of time_series in MonitorEO {__version__}'),
		('csv', 'an output: each tool writes its own files')]
	c = parameters.check({'analysis': 'map_layer', 'parameters': dict(ARGS, variable='NDVX')})
	assert {p['name'] for p in c['not_applied']} == {'variable', 'sensor', 'step', 'stat'}
	assert 'NDVX with sensor Landsat is not in the catalog' in parameters.text(c['not_applied'])
	assert 'note' not in parameters.check({'analysis': 'time_series', 'monitoreo': __version__, 'parameters': ARGS})
	with pytest.raises(ValueError, match="unknown analysis 'serie'"):
		parameters.check({'analysis': 'serie', 'parameters': ARGS})


def test_run_computes_with_what_can_be_applied(monkeypatch):
	got = {}
	monkeypatch.setattr(services, 'time_series', _fake('time_series', {'rows': []}, got))
	out = parameters.run({'analysis': 'time_series', 'parameters': dict(ARGS, colour='red')}, csv='b.csv')
	assert got == dict(ARGS, csv='b.csv') and [p['name'] for p in out['not_applied']] == ['colour']


def test_every_result_with_files_writes_its_parameters(tmp_path):
	csv = str(tmp_path / 'NDVI_Landsat_monthly.csv')

	def time_series(region, variable=None, sensor=None, start=None, end=None, step='monthly', metric='mean',
	                stat='mean', csv=None, **source):
		with open(csv, 'w') as f:
			f.write('region,date,value\n')
		return {'rows': [], 'csv': csv, 'unit': '[unitless]', 'title': 'NDVI'}

	out = services._cited(time_series)(csv=csv, **ARGS)
	assert out['parameters'] == str(tmp_path / 'NDVI_Landsat_monthly.parameters.json')
	saved = json.load(open(out['parameters'], encoding='utf-8'))
	assert saved == {'monitoreo': __version__, 'analysis': 'time_series', 'parameters': ARGS}
	assert parameters.check(out['parameters'])['not_applied'] == []


def test_the_command_line_checks_and_runs_them(tmp_path, monkeypatch, capsys):
	saved = parameters.save('time_series', dict(ARGS, colour='red'), str(tmp_path / 'p.json'))
	cli.main(['parameters', saved])
	out, err = capsys.readouterr()
	assert json.loads(out) == {'analysis': 'time_series', 'parameters': ARGS} and 'not applied: colour' in err
	got = {}
	monkeypatch.setattr(services, 'init', lambda *a, **kw: 'project')
	monkeypatch.setattr(services, 'time_series', _fake('time_series', {'rows': [1, 2]}, got))
	cli.main(['run', saved, '--out', str(tmp_path / 'again')])
	out, err = capsys.readouterr()
	assert got == dict(ARGS, csv=str(tmp_path / 'again.csv'), chart=str(tmp_path / 'again.png'))
	assert json.loads(out)['rows'] == 2 and 'computed without: colour' in err
	with pytest.raises(SystemExit):
		cli.main(['parameters', str(tmp_path / 'missing.json')])


@pytest.fixture
def mcp(monkeypatch, tmp_path):
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	return mcp_server


def test_the_mcp_server_saves_and_applies_them(mcp, tmp_path):
	saved = json.loads(mcp.save_parameters('export_image_to_drive', {'region': REGION, 'variable': 'NDVI',
	                                                                   'sensor': 'Landsat', 'start': '2023-01-01',
	                                                                   'end': '2023-12-31'}, 'ndvi'))
	assert saved['contents']['analysis'] == 'export_image' and saved['parameters'].startswith(str(tmp_path))
	out = json.loads(mcp.apply_parameters(saved['parameters']))
	assert out['tool'] == 'export_image_to_drive' and out['arguments']['variable'] == 'NDVI' and not out['not_applied']
	text = json.dumps({'analysis': 'map_figure', 'parameters': {'region': REGION, 'variable': 'NDVI',
	                                                            'sensor': 'Landsat', 'dpi': 300, 'colour': 'red'}})
	out = json.loads(mcp.apply_parameters(text))
	assert out['tool'] == 'map_layer' and out['arguments']['figure'] is True
	assert {p['name'] for p in out['not_applied']} >= {'colour'} and 'after telling the user' in out['next']
	with pytest.raises(Exception, match='unknown analysis'):
		mcp.apply_parameters('{"analysis": "serie"}')


def test_one_form_for_every_tool_where_and_the_perimeter(tmp_path):
	"""A land cover mask alone (a dictionary in the services) is a list of conditions, and the perimeter of the burn
	severity the name of its file (the MCP tool asks for it with true), so that every tool takes them (review of #85)."""
	mask = {'landcover': 'CORINE', 'year': 2018, 'exclude': ['water']}
	p = parameters.make('download_image', dict(ARGS, where=mask))
	assert p['parameters']['where'] == [mask]
	assert parameters.check({'analysis': 'download_image', 'parameters': dict(ARGS, where=mask)})['parameters'][
		'where'] == [mask]
	burn = {'region': REGION, 'start': '2021-07-15', 'end': '2021-08-31', 'other_start': '2021-09-20',
	        'other_end': '2021-10-31'}
	assert parameters.make('burn_severity', dict(burn, perimeter=True))['parameters']['perimeter'] == 'perimeter.gpkg'
	assert 'perimeter' not in parameters.make('burn_severity', dict(burn, perimeter=False))['parameters']
	assert parameters.make('burn_severity', dict(burn, perimeter='/x/fire_perimeter.gpkg'))['parameters'][
		'perimeter'] == 'fire_perimeter.gpkg'


def test_check_with_a_collection_without_sensor_and_an_unknown_ref():
	c = parameters.check({'analysis': 'time_series', 'parameters': dict(
		{k: v for k, v in ARGS.items() if k != 'sensor'}, variable='NDVX', collection='MODIS/061/MOD13Q1')})
	assert {p['name'] for p in c['not_applied']} == {'variable', 'collection'}
	c = parameters.check({'analysis': 'time_series', 'parameters': dict(ARGS, ref=99999)})
	assert [p['name'] for p in c['not_applied']] == ['ref'] and c['parameters']['variable'] == 'NDVI'


def test_paths_with_the_home(tmp_path, monkeypatch):
	monkeypatch.setenv('HOME', str(tmp_path))
	parameters.save('time_series', ARGS, '~/p.json')
	assert (tmp_path / 'p.json').exists() and parameters.read('~/p.json')['parameters'] == ARGS


def test_the_command_line_exits_well_and_runs_an_mp4(tmp_path, monkeypatch, capsys):
	saved = parameters.save('time_series', ARGS, str(tmp_path / 'p.json'))
	assert cli.main(['parameters', saved]) is None  # exit status 0
	capsys.readouterr()
	got = {}
	monkeypatch.setattr(services, 'init', lambda *a, **kw: 'project')
	monkeypatch.setattr(services, 'timelapse', _fake('timelapse', {'gif': 'x'}, got))
	saved = parameters.save('timelapse', {k: v for k, v in ARGS.items() if k not in ('stat',)}, str(tmp_path / 't.json'))
	cli.main(['run', saved, '--out', str(tmp_path / 'fire.mp4')])
	assert got['path'] == str(tmp_path / 'fire.mp4')


def test_the_mcp_server_applies_the_perimeter_and_the_assistant_has_the_tools(mcp, tmp_path):
	burn = {'region': REGION, 'start': '2021-07-15', 'end': '2021-08-31', 'other_start': '2021-09-20',
	        'other_end': '2021-10-31', 'perimeter': 'fire_perimeter.gpkg'}
	out = json.loads(mcp.apply_parameters(json.dumps({'analysis': 'burn_severity', 'parameters': burn})))
	assert out['arguments']['perimeter'] is True and not out['not_applied']
	from monitoreo import assistant
	assert 'apply_parameters' in assistant.ADVICE  # (saving: the file next to the files of each result)
	assert assistant.other_tool('repeat this: {"analysis": "time_series", "parameters": {}}') is None
	assert assistant.other_tool('repite el análisis de ~/MonitorEO/ndvi.parameters.json') is None
	assert assistant.other_tool('automate it every month') is not None
