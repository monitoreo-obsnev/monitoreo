"""Any image or collection of images of Earth Engine given by its ID, and the GEE Community Catalog by its themes
(monitoreo.assets, monitoreo.community), in the command line (--collection, --image, --band..., monitoreo asset,
monitoreo community) and in the MCP server (collection, image, band... in every tool that computes, describe_asset,
community_themes, community_datasets), without Earth Engine: the services are faked, or refuse before Earth Engine.
tests/test_assets.py tests the services themselves; tests/test_where.py, that every tool takes these arguments."""

import asyncio
import inspect
import json
import os
import re

import pytest

from monitoreo import community, services

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
YEARS = ('2001-01-01', '2020-12-31')
TERRACLIMATE = 'IDAHO_EPSCOR/TERRACLIMATE'
ARGS = ['--region', json.dumps(REGION), '--start', YEARS[0], '--end', YEARS[1]]
PNG = b'\x89PNG\r\n\x1a\n'  # what a preview of Earth Engine starts with
DESCRIBED = {'asset': TERRACLIMATE, 'type': 'image_collection', 'use': 'collection',
             'source': 'Earth Engine data catalog', 'bands': [{'band': 'pr', 'units': 'mm', 'unit': 'mm'}],
             'arguments': {'collection': TERRACLIMATE, 'band': 'pr', 'unit': 'mm'}, 'references': [], 'credits': []}


# The command line ---------------------------------------------------------------------------------------------------

@pytest.fixture
def computed(monkeypatch):
	"""The services of the command line faked: the calls they get ('init' when it connects to Earth Engine), and
	answers like those of Earth Engine."""
	calls = []

	def fake(tool):
		def run(region, variable=None, sensor=None, start=None, end=None, **kw):
			calls.append(dict(kw, tool=tool, region=region, variable=variable, sensor=sensor, start=start, end=end))
			name = f"{kw.get('collection') or kw.get('image')} {kw.get('band')}"
			out = {'title': f'{name} | {start} / {end}', 'scale': 4638.3, 'unit': kw.get('unit') or '', 'csv': None,
			       'chart': None, 'rows': [], 'profile': []}
			if tool == 'time_series':
				out['rows'] = [{'region': 'bbox', 'date': '2001-01-01', 'value': 41.25, 'n_pixels': 12, 'n_images': 1}]
			if tool == 'download_image':
				return {'file': kw['path'], 'grid': {'width': 60, 'height': 40}, 'resolution': 1000.0, 'images': None,
				        'name': name, 'unit': kw.get('unit') or '', 'min': 5.0, 'max': 15.25}
			return out
		return run

	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: calls.append('init') or 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	for name in ('time_series', 'trend_table', 'compare_series', 'download_image'):
		monkeypatch.setattr(services, name, fake(name))
	return calls


def _calls(calls):
	return [c for c in calls if c != 'init']


def test_the_command_line_computes_a_collection_by_its_id(computed, capsys):
	from monitoreo import cli
	cli.main(['series', '--collection', TERRACLIMATE, '--band', 'pr', '--unit', 'mm'] + ARGS +
	         ['--step', 'annual', '--metric', 'sum'])
	[call] = _calls(computed)
	assert (call['tool'], call['collection'], call['band'], call['unit']) == ('time_series', TERRACLIMATE, 'pr', 'mm')
	assert (call['variable'], call['sensor'], call['start'], call['end']) == (None, None) + YEARS
	assert (call['step'], call['metric'], call['where']) == ('annual', 'sum', None)
	assert not {'image', 'band_scale', 'band_offset', 'terrain'} & set(call)  # only what was given
	out = capsys.readouterr().out
	assert out.splitlines()[1].split() == ['bbox', '2001-01-01', '41.25', '12', '1']
	assert out.rstrip().splitlines()[-1] == f'{TERRACLIMATE} pr | 2001-01-01 / 2020-12-31 | scale 4638.3 m | unit mm'
	cli.main(['series', '--collection', TERRACLIMATE, '--band', 'pdsi'] + ARGS)  # without a unit: none printed
	assert capsys.readouterr().out.rstrip().endswith('| scale 4638.3 m')

	cli.main(['trend', '--collection', TERRACLIMATE, '--band', 'tmmx', '--band-scale', '0.1', '--band-offset',
	          '-273.15', '--unit', 'degC'] + ARGS)
	call = _calls(computed)[-1]
	assert (call['tool'], call['band'], call['band_scale'], call['band_offset']) == ('trend_table', 'tmmx', 0.1, -273.15)
	assert call['unit'] == 'degC' and 'slope in degC / year' in capsys.readouterr().out
	cli.main(['trend', '--collection', TERRACLIMATE, '--band', 'pdsi'] + ARGS)  # without a unit
	assert 'unit' not in _calls(computed)[-1] and '| slope per year' in capsys.readouterr().out

	cli.main(['compare', '--collection', TERRACLIMATE, '--band', 'pr', '--other-start', '2021-01-01', '--other-end',
	          '2024-12-31'] + ARGS)
	call = _calls(computed)[-1]
	assert (call['tool'], call['collection'], call['other_start'], call['other_end']) == \
	       ('compare_series', TERRACLIMATE, '2021-01-01', '2024-12-31')
	assert computed.count('init') == 5  # they compute in Earth Engine


def test_the_command_line_computes_an_image_by_its_id(computed, capsys, tmp_path):
	from monitoreo import cli
	tif = str(tmp_path / 'bio01.tif')
	cli.main(['image', '--image', 'WORLDCLIM/V1/BIO', '--band', 'bio01', '--band-scale', '0.1', '--unit', 'degC',
	          '--region', json.dumps(REGION), '--out', tif])
	[call] = _calls(computed)
	assert (call['tool'], call['image'], call['band'], call['band_scale'], call['unit']) == \
	       ('download_image', 'WORLDCLIM/V1/BIO', 'bio01', 0.1, 'degC')
	assert (call['variable'], call['start'], call['end'], call['path']) == (None, None, None, tif)
	assert 'collection' not in call
	assert capsys.readouterr().out == (f'{tif}: WORLDCLIM/V1/BIO bio01 | 60 x 40 pixels of 1000 m | fixed image | '
	                                   'p5-p95 5 to 15.25 degC\n')  # no images, nor "None images"
	cli.main(['image', '--image', 'COPERNICUS/DEM/GLO30', '--band', 'DEM', '--terrain', 'slope', '--region',
	          json.dumps(REGION), '--out', tif])
	call = _calls(computed)[-1]
	assert (call['image'], call['band'], call['terrain']) == ('COPERNICUS/DEM/GLO30', 'DEM', 'slope')
	assert capsys.readouterr().out.endswith('p5-p95 5 to 15.25\n')  # no unit given
	cli.main(['image', '--collection', TERRACLIMATE, '--band', 'pr', '--metric', 'sum', '--temporal', 'annual',
	          '--out', tif] + ARGS)
	call = _calls(computed)[-1]
	assert (call['collection'], call['metric'], call['temporal'], call['start']) == (TERRACLIMATE, 'sum', 'annual',
	                                                                                  YEARS[0])


@pytest.mark.parametrize('argv, message', [
	(['series'] + ARGS, 'give VARIABLE and --sensor (a variable of the catalog: monitoreo list), or --collection and '
	                    '--band'),
	(['image', '--out', 'x.tif'] + ARGS, 'or --collection or --image and --band'),
	(['series', 'NDVI'] + ARGS, 'give the sensor of NDVI'),
	(['series', TERRACLIMATE, '--band', 'pr'] + ARGS, f'{TERRACLIMATE} is not a variable of the catalog (monitoreo '
	                                                  'list): give an ID of Earth Engine with --collection and --band'),
	(['image', 'WORLDCLIM/V1/BIO', '--out', 'x.tif'] + ARGS, 'give an ID of Earth Engine with --collection or --image '
	                                                         'and --band, instead of VARIABLE'),
	(['series', TERRACLIMATE, '--sensor', 'TerraClimate'] + ARGS, f'{TERRACLIMATE} is not a variable of the catalog '
	                                                              '(monitoreo list): give an ID of Earth Engine with '
	                                                              '--collection and --band'),  # also with a sensor
	(['info', TERRACLIMATE], f'{TERRACLIMATE} is not a variable of the catalog (monitoreo list): monitoreo asset '
	                         f'{TERRACLIMATE} describes an ID of Earth Engine'),
	(['trend', 'NDVI', '--sensor', 'Modis', '--band', 'NDVI'] + ARGS, '--band: only for the data of Earth Engine given '
	                                                                  'by its ID (--collection instead of VARIABLE'),
	(['trend', '--collection', TERRACLIMATE] + ARGS, f'give --band: the band of {TERRACLIMATE} (one; monitoreo asset '
	                                                 f'{TERRACLIMATE} lists them)'),
	(['series', 'NDVI', '--sensor', 'Modis', '--band', 'NDVI', '--unit', '1'] + ARGS,
	 '--band, --unit: only for the data of Earth Engine given by its ID'),
	(['compare', '--collection', TERRACLIMATE, '--band', 'pr', '--sensor', 'TerraClimate', '--other-start',
	  '2021-01-01', '--other-end', '2021-12-31'] + ARGS, '--sensor is for the variables of the catalog (with VARIABLE): '
	                                                     'the data of Earth Engine given by its ID take --collection, '
	                                                     'and --band'),
	(['image', '--collection', TERRACLIMATE, '--image', 'WORLDCLIM/V1/BIO', '--band', 'pr', '--out', 'x.tif'] + ARGS,
	 'not both'),
	(['image', '--collection', TERRACLIMATE, '--band', 'pr', '--terrain', 'slope', '--out', 'x.tif'] + ARGS,
	 '--terrain is for --image'),
	(['image', '--image', 'WORLDCLIM/V1/BIO', '--band', 'bio01', '--rgb', 'x.tif'] + ARGS,
	 '--rgb is only for the variables of the catalog'),
	(['series', '--image', 'WORLDCLIM/V1/BIO', '--band', 'bio01'] + ARGS, 'unrecognized arguments: --image'),
	(['image', '--image', 'COPERNICUS/DEM/GLO30', '--band', 'DEM', '--terrain', 'hillshade', '--out', 'x.tif'] + ARGS,
	 "invalid choice: 'hillshade'"),
])
def test_the_command_line_refuses_what_it_cannot_compute(computed, capsys, argv, message):
	"""Neither a variable and its sensor nor data of Earth Engine and its band, or both mixed: an error of the command,
	before Earth Engine."""
	from monitoreo import cli
	with pytest.raises(SystemExit) as e:
		cli.main(argv)
	err = ' '.join(capsys.readouterr().err.split())
	assert e.value.code == 2 and 'error: ' in err and message in err, err
	assert not computed  # not even connected to Earth Engine


def test_the_command_line_gives_the_errors_of_the_services(monkeypatch):
	"""The ValueError of the services (the real ones, which refuse before Earth Engine) end the command with their
	message, not with a traceback."""
	from monitoreo import cli
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	with pytest.raises(SystemExit, match=r'^ERROR: the unit of IDAHO_EPSCOR/TERRACLIMATE is written in UDUNITS'):
		cli.main(['series', '--collection', TERRACLIMATE, '--band', 'pr', '--unit', 'mm!'] + ARGS)
	with pytest.raises(SystemExit, match=r'^ERROR: the unit of IDAHO_EPSCOR/TERRACLIMATE is written in UDUNITS'):
		cli.main(['trend', '--collection', TERRACLIMATE, '--band', 'pr', '--unit', 'kg/m2!'] + ARGS)
	with pytest.raises(SystemExit, match='^ERROR: '):  # a region that is not JSON: a message, not a traceback
		cli.main(['compare', '--collection', TERRACLIMATE, '--band', 'pr', '--other-start', '2021-01-01',
		          '--other-end', '2021-12-31', '--region', '{"bbox": [0, 0,', '--start', YEARS[0], '--end', YEARS[1]])


def test_the_command_line_lists_the_community_catalog(monkeypatch, capsys):
	"""monitoreo community: the themes of the GEE Community Catalog, or its datasets, from the copy of its index in
	MonitorEO, without Earth Engine."""
	from monitoreo import cli
	monkeypatch.setattr(services, 'init', lambda *a, **k: pytest.fail('it connected to Earth Engine'))
	cli.main(['community'])
	lines = capsys.readouterr().out.rstrip().splitlines()
	themes = services.community_themes()
	assert lines[0].split() == ['name', 'datasets'] and len(lines) == 1 + len(themes) + 2
	assert lines[1].startswith(themes[0]['name']) and lines[1].split()[-1] == str(themes[0]['datasets'])
	total = len(community.load()['datasets'])
	assert lines[-1] == (f'{total} images and collections of images of the GEE Community Catalog | monitoreo community '
	                     '--theme NAME lists those of a theme')
	cli.main(['community', '--lang', 'es'])
	assert 'Hidrología' in capsys.readouterr().out

	cli.main(['community', '--theme', 'Hydrology', '--kind', 'image_collection', '--limit', '3'])
	lines = capsys.readouterr().out.rstrip().splitlines()
	wanted = services.community_datasets('Hydrology', None, 'image_collection', 3)
	assert lines[0].split() == ['id', 'type', 'title'] and len(wanted) == 3
	assert [x.split()[:2] for x in lines[1:4]] == [[d['id'], 'image_collection'] for d in wanted]
	assert lines[-1].startswith('3 datasets of the GEE Community Catalog | monitoreo asset ID describes one')
	cli.main(['community', '--theme', 'hidrología', '--kind', 'image'])  # its name in Spanish, or part of it
	ids = [x.split()[0] for x in capsys.readouterr().out.splitlines()[1:] if x.strip()][:-1]
	assert ids == [d['id'] for d in services.community_datasets('Hydrology', kind='image')]
	cli.main(['community', '--text', 'FABDEM'])
	assert 'projects/sat-io/open-datasets/FABDEM' in capsys.readouterr().out
	with pytest.raises(SystemExit, match='^ERROR: unknown theme mountains of the GEE Community Catalog'):
		cli.main(['community', '--theme', 'mountains'])
	with pytest.raises(SystemExit):
		cli.main(['community', '--kind', 'table'])  # only images and collections of images


def test_the_command_line_describes_an_asset(monkeypatch, capsys):
	"""monitoreo asset ID: what describe_asset says, as JSON; it reads the metadata in Earth Engine, so it connects."""
	from monitoreo import cli
	calls = []
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: calls.append(project) or 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	monkeypatch.setattr(services, 'describe_asset', lambda asset: calls.append(asset) or DESCRIBED)
	cli.main(['--project', 'my-project', 'asset', TERRACLIMATE])
	assert calls == ['my-project', TERRACLIMATE]
	assert json.loads(capsys.readouterr().out) == DESCRIBED

	def unknown(asset):
		raise ValueError(f'Earth Engine has no image or collection {asset}, or this account cannot read it')
	monkeypatch.setattr(services, 'describe_asset', unknown)
	with pytest.raises(SystemExit, match='^ERROR: Earth Engine has no image or collection X/Y'):
		cli.main(['asset', 'X/Y'])


def test_the_command_line_explains_the_data_by_its_id(capsys):
	from monitoreo import cli
	with pytest.raises(SystemExit):
		cli.main(['series', '--help'])
	text = ' '.join(capsys.readouterr().out.split())
	for option in ('[variable]', '--collection ID', '--band BAND', '--band-scale F', '--band-offset F', '--unit UNIT'):
		assert option in text, option
	assert '--image' not in text and '--terrain' not in text  # no series of a fixed image
	with pytest.raises(SystemExit):
		cli.main(['image', '--help'])
	text = ' '.join(capsys.readouterr().out.split())
	assert '--image ID' in text and '--terrain {slope,aspect}' in text and 'UDUNITS' in text
	for line in ('monitoreo series --collection ID --band B', 'monitoreo asset ID', 'monitoreo community [--theme T]'):
		assert line in cli.__doc__, line
	with pytest.raises(SystemExit, match='^ERROR: Earth Engine data \\(by its ID\\) has no variables of the catalog'):
		cli.main(['list', '--theme', 'earth_engine'])
	# the slope and the aspect are in degrees, whatever the unit of the band (of a DEM, m)
	terrain = text[text.index('--terrain {slope,aspect}'):]
	assert 'in degrees (its unit is then degree: give no --unit, or degree, not that of the band)' in terrain
	assert 'with --terrain, none or degree' in text and '--terrain slope|aspect (in degrees' in cli.__doc__


@pytest.mark.parametrize('theme, words', [
	('earth_engine', 'monitoreo asset ID describes it'),
	('community', 'monitoreo community lists its themes'),
	('Catálogo de la comunidad de GEE', 'monitoreo community lists its themes'),  # its name in Spanish
])
def test_the_command_line_names_its_own_commands_for_the_other_themes(monkeypatch, theme, words):
	"""monitoreo list --theme of the data of Earth Engine outside the catalog: its commands and options (monitoreo
	asset, monitoreo community, --collection, --image, --band), not those of Python or of the MCP server."""
	from monitoreo import cli
	monkeypatch.setattr(services, 'init', lambda *a, **k: pytest.fail('it connected to Earth Engine'))
	with pytest.raises(SystemExit) as e:
		cli.main(['list', '--theme', theme])
	text = str(e.value.code)
	assert text.startswith('ERROR: ') and 'has no variables of the catalog: ' in text and words in text, text
	assert '--collection (or --image, in monitoreo image) and --band' in text
	assert not re.search(r'describe_asset|community_(themes|datasets)|collection=|image=|band=', text), text


def test_the_command_line_says_how_to_give_an_image(computed, monkeypatch):
	"""When the services refuse data given with --collection that go as an image (an image, or a collection of tiles
	without dates), the command line adds its own option for them; other errors as they are."""
	from monitoreo import cli
	said = {}

	def refuse(*a, **kw):
		raise ValueError(said['error'])
	for name in ('time_series', 'trend_table', 'download_image'):
		monkeypatch.setattr(services, name, refuse)
	said['error'] = 'WORLDCLIM/V1/BIO is an image, not a collection of images: give it as an image (a fixed layer)'
	with pytest.raises(SystemExit) as e:
		cli.main(['series', '--collection', 'WORLDCLIM/V1/BIO', '--band', 'bio01'] + ARGS)
	assert str(e.value.code) == (f"ERROR: {said['error']}; in the command line, monitoreo image --image "
	                             'WORLDCLIM/V1/BIO --band bio01 (a GeoTIFF)')
	with pytest.raises(SystemExit) as e:
		cli.main(['trend', '--collection', 'WORLDCLIM/V1/BIO', '--band', 'bio01'] + ARGS)
	assert str(e.value.code).endswith('monitoreo image --image WORLDCLIM/V1/BIO --band bio01 (a GeoTIFF)')
	said['error'] = 'X/TILES is a collection of images without dates (tiles): give it as an image (their mosaic)'
	with pytest.raises(SystemExit) as e:
		cli.main(['image', '--collection', 'X/TILES', '--band', 'b1', '--out', 'x.tif'] + ARGS)
	assert str(e.value.code) == f"ERROR: {said['error']}; in the command line, --image X/TILES instead of --collection"
	said['error'] = 'the unit of X is written in UDUNITS'
	with pytest.raises(SystemExit) as e:
		cli.main(['series', '--collection', 'X', '--band', 'b1'] + ARGS)
	assert str(e.value.code) == f"ERROR: {said['error']}"


# The MCP server -----------------------------------------------------------------------------------------------------

@pytest.fixture
def mcp(monkeypatch, tmp_path):
	"""The MCP server, writing to TMP_PATH, without connecting to Earth Engine (READY: when it would)."""
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	mcp_server.READY = []
	monkeypatch.setattr(mcp_server, '_ready', lambda: mcp_server.READY.append(True))
	monkeypatch.setattr(services, 'eecu_warning', lambda *a, **k: None)
	return mcp_server


# the tools that compute, with the function of services they call and their dates
COMPUTE = {'time_series': 'time_series', 'export_time_series_to_drive': 'time_series_to_drive',
           'map_layer': 'map_layer', 'region_stats': 'region_stats', 'download_image': 'download_image',
           'export_image_to_drive': 'export_image', 'trend_table': 'trend_table', 'trend_map': 'trend_map',
           'download_trend': 'download_trend', 'compare_series': 'compare_series', 'compare_map': 'compare_map',
           'download_comparison': 'download_comparison'}
OTHER = {'other_start': '2021-01-01', 'other_end': '2024-12-31'}
DATED = ('time_series', 'export_time_series_to_drive', 'trend_table', 'trend_map', 'download_trend', 'compare_series',
         'compare_map', 'download_comparison')  # the tools that need dates, whatever the data
COLLECTION = {'collection': TERRACLIMATE, 'band': 'tmmx', 'band_scale': 0.1, 'unit': 'degC'}
IMAGE = {'image': 'COPERNICUS/DEM/GLO30', 'band': 'DEM', 'terrain': 'slope', 'unit': 'degree'}


@pytest.fixture
def faked(mcp, monkeypatch):
	"""The services of the tools that compute faked: the calls they get (their keywords), and answers that name the
	files they wrote."""
	calls = []

	def fake(name):
		def run(region, variable=None, sensor=None, *args, **kw):
			calls.append(dict(kw, service=name, region=region, variable=variable, sensor=sensor, args=args))
			for k in ('csv', 'chart', 'thumbnail', 'path'):
				if kw.get(k):
					with open(kw[k], 'wb') as f:
						f.write(PNG)
			return {'title': 't', 'unit': 'degC', 'ylabel': '[degC]', 'scale': 4638.3, 'n_steps': 0, 'regions': [],
			        'rows': [], 'yearly': [], 'profile': [], 'csv': kw.get('csv'), 'chart': kw.get('chart'),
			        'thumbnail': kw.get('thumbnail'), 'file': kw.get('path'), 'url': 'https://x/{z}/{x}/{y}',
			        'operation': 'projects/p/operations/1', 'references': [], 'credits': []}
		return run

	for name in set(COMPUTE.values()):
		monkeypatch.setattr(services, name, fake(name))
	return calls


def _files(call):
	return [os.path.basename(call[k]) for k in ('csv', 'chart', 'thumbnail', 'path') if call.get(k)]


@pytest.mark.parametrize('tool', list(COMPUTE))
def test_a_collection_by_its_id_reaches_the_services(faked, mcp, tool, tmp_path):
	"""Every tool that computes passes collection, band, band_scale, band_offset and unit by keyword to services, and
	the names of its files say the end of the ID and the band, without None."""
	dates = dict(start=YEARS[0], end=YEARS[1], **(OTHER if 'compar' in tool else {}))
	getattr(mcp, tool)(REGION, **COLLECTION, **dates)
	[call] = faked
	assert call['service'] == COMPUTE[tool] and mcp.READY
	assert {k: call.get(k) for k in COLLECTION} == COLLECTION
	assert (call['variable'], call['sensor']) == (None, None)
	assert not {'image', 'terrain', 'band_offset'} & set(call)  # only what was given
	for name in _files(call):
		assert 'None' not in name and name.startswith(('TERRACLIMATE_tmmx', 'map_TERRACLIMATE_tmmx',
		                                               'trend_TERRACLIMATE_tmmx', 'comparison_TERRACLIMATE_tmmx')), name
	if tool == 'time_series':
		assert re.fullmatch(r'TERRACLIMATE_tmmx_monthly_mean_2001-01-01_2020-12-31_\d{8}-\d{6}\.csv',
		                    _files(call)[0])
		[logged] = [json.loads(x) for x in open(tmp_path / 'calls.jsonl', encoding='utf-8')]  # for publish_report
		assert {k: logged['args'].get(k) for k in COLLECTION} == COLLECTION and 'variable' not in logged['args']


@pytest.mark.parametrize('tool', ['map_layer', 'region_stats', 'download_image', 'export_image_to_drive'])
def test_an_image_by_its_id_reaches_the_services(faked, mcp, tool):
	getattr(mcp, tool)(REGION, **IMAGE)
	[call] = faked
	assert {k: call.get(k) for k in IMAGE} == IMAGE and 'collection' not in call
	for name in _files(call):  # a fixed image: no metric nor dates in its name
		assert re.fullmatch(r'(map_)?GLO30_DEM_slope_\d{8}-\d{6}\.(png|tif)', name), name


def test_the_server_takes_the_arguments_of_the_data(faked, mcp):
	"""As the server calls a tool, with its arguments checked against the schema of the tool (no variable nor sensor;
	band_scale a number)."""
	asyncio.run(mcp.server.call_tool('download_image', {'region': REGION, 'image': 'WORLDCLIM/V1/BIO', 'band': 'bio01',
	                                                    'band_scale': 0.1, 'unit': 'degC'}))
	[call] = faked
	assert (call['image'], call['band'], call['band_scale'], call['unit']) == ('WORLDCLIM/V1/BIO', 'bio01', 0.1, 'degC')
	assert re.fullmatch(r'BIO_bio01_\d{8}-\d{6}\.tif', _files(call)[0])
	# band_offset too: the land surface temperature of MODIS, in kelvin * 50, in degC; the ID as in the Code Editor
	lst = {'collection': 'ee.ImageCollection("MODIS/061/MOD11A2")', 'band': 'LST_Day_1km', 'band_scale': 0.02,
	       'band_offset': -273.15, 'unit': 'degC'}
	asyncio.run(mcp.server.call_tool('time_series', dict(lst, region=REGION, start=YEARS[0], end=YEARS[1])))
	assert {k: faked[-1].get(k) for k in lst} == lst  # the services read the ID (assets.normalize)
	assert re.fullmatch(r'MOD11A2_LST_Day_1km_monthly_mean_2001-01-01_2020-12-31_\d{8}-\d{6}\.csv',
	                    _files(faked[-1])[0])


def test_the_catalog_still_reaches_the_services(faked, mcp):
	"""The variables of the catalog as before: the same names of the files, collection one of those of the variable."""
	mcp.time_series(REGION, 'NDVI', 'Modis', start=YEARS[0], end=YEARS[1], collection='MODIS/061/MOD13Q1')
	call = faked[-1]
	assert (call['variable'], call['sensor'], call['collection']) == ('NDVI', 'Modis', 'MODIS/061/MOD13Q1')
	assert re.fullmatch(r'NDVI_Modis_monthly_mean_2001-01-01_2020-12-31_\d{8}-\d{6}\.csv', _files(call)[0])
	assert not {'image', 'band', 'band_scale', 'band_offset', 'unit'} & set(call)
	mcp.map_layer(REGION, 'ELEVATION', 'Copernicus')  # a fixed layer: no None for its dates
	assert re.fullmatch(r'map_ELEVATION_Copernicus_median_\d{8}-\d{6}\.png', _files(faked[-1])[0])
	mcp.download_trend(REGION, 'EVI', 'Modis', start=YEARS[0], end=YEARS[1])
	assert re.fullmatch(r'trend_EVI_Modis_annual_2001-01-01_2020-12-31_\d{8}-\d{6}\.tif', _files(faked[-1])[0])


@pytest.mark.parametrize('tool, kw, message', [
	('time_series', dict(start=YEARS[0], end=YEARS[1]), 'give variable and sensor (a variable of the catalog: '
	                                                     'list_variables), or collection or image and band'),
	('time_series', dict(variable='NDVI', start=YEARS[0], end=YEARS[1]), 'give the sensor of NDVI'),
	('time_series', dict(variable=TERRACLIMATE, band='pr', start=YEARS[0], end=YEARS[1]),
	 f'{TERRACLIMATE} is not a variable of the catalog (list_variables): give an ID of Earth Engine as collection or '
	 'image'),
	('trend_table', dict(variable=TERRACLIMATE, sensor='TerraClimate', start=YEARS[0], end=YEARS[1]),
	 f'{TERRACLIMATE} is not a variable of the catalog (list_variables): give an ID of Earth Engine as collection or '
	 'image'),
	('map_layer', dict(variable=TERRACLIMATE, sensor='TerraClimate', collection=TERRACLIMATE, band='pr'),
	 f'{TERRACLIMATE} is not a variable of the catalog (list_variables)'),
	('trend_table', dict(collection=TERRACLIMATE, start=YEARS[0], end=YEARS[1]), f'give band: the band of {TERRACLIMATE}'),
	('map_layer', dict(variable='NDVI', sensor='Modis', band='NDVI', band_scale=0.0001),
	 'band, band_scale: only for the data of Earth Engine given by its ID'),
	('map_layer', dict(sensor='TerraClimate', collection=TERRACLIMATE, band='pr'), 'sensor is for the variables of the '
	                                                                               'catalog'),
	('download_image', dict(collection=TERRACLIMATE, image='WORLDCLIM/V1/BIO', band='pr'),
	 'give collection (a collection of images with dates) or image (a fixed image), not both'),
	('region_stats', dict(collection=TERRACLIMATE, band='pr', terrain='slope'), 'terrain is for an image'),
	('time_series', dict(collection=TERRACLIMATE, band='pr', start='', end=''), 'give start and end'),
	('compare_series', dict(collection=TERRACLIMATE, band='pr', start=YEARS[0], end=YEARS[1], other_start='',
	                        other_end=''), 'give other_start and other_end'),
	# a fixed image where dates are needed: what the services say, also before asking for the dates
	('time_series', dict(image='WORLDCLIM/V1/BIO', band='bio01', start=YEARS[0], end=YEARS[1]),
	 'WORLDCLIM/V1/BIO (band bio01) is given as a fixed image, without dates (image=): it has maps, GeoTIFFs and '
	 'statistics of the region (map_layer, download_image, region_stats), but no time series'),
	('trend_map', dict(image='WORLDCLIM/V1/BIO', band='bio01', start='', end=''), 'WORLDCLIM/V1/BIO (band bio01) is '
	                                                                              'given as a fixed image, without dates'),
	('download_comparison', dict(image='ee.Image("WORLDCLIM/V1/BIO")', band='bio01', start='', end='', other_start='',
	                             other_end=''), 'WORLDCLIM/V1/BIO (band bio01) is given as a fixed image, without dates'),
	('trend_table', dict(variable='ELEVATION', sensor='Copernicus', start='', end=''),
	 'ELEVATION (Copernicus) is a fixed layer, without dates'),  # and those of the catalog
	('time_series', dict(variable='NDVI', sensor='Modis', start='', end=''), 'give start and end'),
])
def test_the_mcp_server_refuses_what_it_cannot_compute(faked, mcp, tool, kw, message):
	with pytest.raises(mcp.ToolError, match='^ValueError: ' + re.escape(message)):
		getattr(mcp, tool)(REGION, **kw)
	assert not faked and not mcp.READY  # before Earth Engine


def test_the_mcp_server_requires_the_dates(faked, mcp):
	"""Through the server, a tool that needs dates without them is refused by its schema, before the tool: the
	model learns that they are required (they come after variable and sensor, which have a default)."""
	for tool, more in (('time_series', {}), ('trend_map', {}), ('compare_map', {'start': YEARS[0], 'end': YEARS[1]})):
		with pytest.raises(Exception, match='start|other_start') as e:
			asyncio.run(mcp.server.call_tool(tool, dict(more, region=REGION, variable='NDVI', sensor='Modis')))
		assert 'Field required' in str(e.value), str(e.value)
	assert not faked and not mcp.READY


def test_the_mcp_server_does_not_describe_an_id_as_a_variable(mcp):
	with pytest.raises(mcp.ToolError, match=f'^ValueError: {TERRACLIMATE} is not a variable of the catalog '
	                                        r'\(list_variables\): describe_asset describes an ID of Earth Engine'):
		mcp.describe_variable(TERRACLIMATE)


def test_the_mcp_server_gives_the_errors_of_the_services(mcp, tmp_path):
	"""The refusals of the services (the real ones, before Earth Engine) reach the client with their message."""
	with pytest.raises(mcp.ToolError, match=r'^ValueError: period \[.2020-12-31., .2020-01-01.\]: the end is before'):
		mcp.compare_map(REGION, collection=TERRACLIMATE, band='pr', start='2020-12-31', end='2020-01-01', **OTHER)
	with pytest.raises(mcp.ToolError, match='is written in UDUNITS'):
		mcp.trend_table(REGION, collection=TERRACLIMATE, band='pr', unit='mm/month!', start=YEARS[0], end=YEARS[1])
	assert not [f for f in os.listdir(tmp_path) if f.endswith(('.png', '.csv', '.jsonl'))]  # nothing written


def test_the_mcp_server_describes_assets_and_the_community_catalog(mcp, monkeypatch):
	asked = []
	monkeypatch.setattr(services, 'describe_asset', lambda asset: asked.append(asset) or DESCRIBED)
	monkeypatch.setattr(services, 'eecu_warning', lambda *a, **k: 'Few left')
	answer = json.loads(mcp.describe_asset(TERRACLIMATE))
	assert asked == [TERRACLIMATE] and mcp.READY  # it reads the metadata in Earth Engine
	assert answer == dict(DESCRIBED, eecu_warning='Few left')
	mcp.READY.clear()
	assert json.loads(mcp.community_themes()) == services.community_themes()  # no Earth Engine, nor its warning
	assert json.loads(mcp.community_themes('es'))[0]['name'] == services.community_themes('es')[0]['name']
	rows = json.loads(mcp.community_datasets(theme='Elevation and Bathymetry'))
	assert len(rows) == len(services.community_datasets('Elevation and Bathymetry'))  # all of them, as in the others
	weather = json.loads(mcp.community_datasets(theme='Weather and Climate Layers'))
	assert len(weather) == len(services.community_datasets('Weather and Climate Layers')) > 50  # no cut at 50
	assert len(json.loads(mcp.community_datasets(theme='Weather and Climate Layers', limit=5))) == 5
	assert {r['theme'] for r in rows} == {'Elevation and Bathymetry'} and all(r['id'] and r['docs'] for r in rows)
	rows = json.loads(mcp.community_datasets(text='FABDEM', kind='image_collection', limit=None))
	assert 'projects/sat-io/open-datasets/FABDEM' in {r['id'] for r in rows}
	assert not mcp.READY
	with pytest.raises(mcp.ToolError, match='unknown theme mountains'):
		mcp.community_datasets(theme='mountains')
	for name in ('describe_asset', 'community_themes', 'community_datasets'):
		assert callable(getattr(services, name)) and callable(getattr(mcp, name)), name
	assert {'community_themes', 'community_datasets'} <= set(mcp.NO_EECU_WARNING)
	assert 'describe_asset' not in mcp.NO_EECU_WARNING


def test_the_model_learns_the_data_by_its_id(mcp):
	text = ' '.join(mcp.INSTRUCTIONS.split())
	for words in ('any image or collection of images of Earth Engine given by its ID', 'First describe_asset with the ID',
	              'as collection (images with dates', 'as image (a fixed image', 'no time series, trends or comparisons',
	              'community_themes, then community_datasets', 'Never invent an ID',
	              'The pixel filters of MonitorEO (quality) are not for these data',
	              'Cite the dataset as describe_asset', 'list_variables, community_themes'):
		assert words in text, words
	tools = {t.name: t for t in asyncio.run(mcp.server.list_tools())}
	schema = lambda name: getattr(tools[name], 'input_schema', None) or tools[name].inputSchema  # noqa: E731
	for name in COMPUTE:  # dates required where they are needed, variable and sensor never (data by ID instead)
		dates = ['start', 'end'] + (['other_start', 'other_end'] if 'compar' in name else [])
		assert schema(name)['required'] == (['region'] + dates if name in DATED else ['region']), name
		params = inspect.signature(getattr(mcp, name)).parameters
		assert all(params[d].kind is inspect.Parameter.KEYWORD_ONLY for d in dates if name in DATED), name
	assert {'collection', 'image', 'band', 'band_scale', 'band_offset', 'unit', 'terrain'} <= \
		set(schema('map_layer')['properties'])
	assert schema('rgb_map')['required'] == ['region', 'variable', 'sensor', 'start', 'end']  # the catalog only
	assert schema('describe_asset')['required'] == ['asset']
	assert not schema('community_datasets').get('required') and not schema('community_themes').get('required')
	assert schema('community_datasets')['properties']['limit']['default'] is None  # all of them
	for name, service in COMPUTE.items():  # every argument goes to services: by position or among those of the data
		params, given = set(inspect.signature(getattr(mcp, name)).parameters), \
			set(inspect.signature(getattr(services, service)).parameters)
		assert params - given <= {'collection', 'image', 'band', 'band_scale', 'band_offset', 'unit', 'terrain',
		                          'where'}, name
	assert 'ee.ImageCollection' in mcp.describe_asset.__doc__ and 'references and credits' in mcp.describe_asset.__doc__
	# the slope and the aspect are in degrees, whatever the unit of the band (that describe_asset gives: m for a DEM)
	assert 'in degrees (its unit is then degree: give no unit, or "degree", not that of the band)' in \
		' '.join(mcp.TERRAIN_DOC.split())
	assert 'the values are in degrees (its unit is then degree: give no unit' in text
	assert 'Without Earth Engine' in mcp.community_themes.__doc__ and 'describe_asset' in \
		mcp.community_datasets.__doc__
