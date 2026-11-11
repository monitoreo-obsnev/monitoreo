"""The true colour of the images of a variable (services.rgb_map and services.download_rgb, issue #24) in the command
line (monitoreo image --rgb) and in the MCP server (the tools rgb_map and download_rgb), without Earth Engine: the
services are faked, and what has no true colour is refused before Earth Engine. tests/test_rgb.py tests the services
themselves and tests/test_ee.py their computation (pytest -m ee)."""

import asyncio
import inspect
import json
import os
import re

import pytest

from monitoreo import catalog, sensors, services

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
JUNE = ('2021-06-01', '2021-06-30')
ARGS = ['--region', json.dumps(REGION), '--start', JUNE[0], '--end', JUNE[1]]
ABOVE = [{'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 1500}]
PNG = b'\x89PNG\r\n\x1a\n'  # what a preview of Earth Engine starts with


@pytest.fixture
def downloads(monkeypatch):
	"""services.download_image and services.download_rgb faked: the calls they get, and answers like those of Earth
	Engine (the map on pixels of 20 m when no pixel size is asked, as with max_pixels)."""
	calls = []

	def fake(tool):
		def download(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
		             interannual='mean', **kw):
			calls.append(dict(kw, tool=tool, region=region, variable=variable, sensor=sensor, start=start, end=end,
			                  metric=metric, temporal=temporal, interannual=interannual))
			kw['progress'](1, 1)
			res = kw.get('resolution') or 20.0
			out = {'file': kw['path'], 'grid': {'width': 60, 'height': 40, 'resolution': res, 'crs': 'EPSG:32630'},
			       'resolution': res, 'native_resolution': 10.0, 'images': 6,
			       'name': f'{variable} {sensor} | {start} / {end} ({metric})', 'readme': kw['path'] + '.README.txt'}
			if tool == 'download_rgb':
				return dict(out, name=out['name'] + ', true colour', unit=catalog.RGB_UNIT, bands=list(sensors.RGB_BANDS),
				            min=0.01234, max=0.3104)
			return dict(out, unit='[unitless]', min=0.1234, max=0.8, palette=['ff0000', '00ff00'])
		return download

	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: calls.append('init') or 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	monkeypatch.setattr(services, 'download_image', fake('download_image'))
	monkeypatch.setattr(services, 'download_rgb', fake('download_rgb'))
	return calls


def _downloads(calls):
	return [c for c in calls if c != 'init']


def test_the_command_line_writes_the_true_colour(downloads, capsys, tmp_path):
	from monitoreo import cli
	rgb = str(tmp_path / 'ndvi_rgb.tif')
	cli.main(['image', 'NDVI', '--sensor', 'Sentinel-2'] + ARGS + ['--rgb', rgb, '--resolution', '30'])
	[call] = _downloads(downloads)  # only the true colour: no map of the variable
	assert call['tool'] == 'download_rgb' and call['path'] == rgb and call['resolution'] == 30.0
	assert (call['region'], call['variable'], call['sensor'], call['start'], call['end']) == \
	       (REGION, 'NDVI', 'Sentinel-2') + JUNE
	assert (call['metric'], call['temporal'], call['interannual'], call['where']) == ('median', 'period', 'mean', None)
	out = capsys.readouterr()
	assert out.out == (f'{rgb}: NDVI Sentinel-2 | 2021-06-01 / 2021-06-30 (median), true colour | 60 x 40 pixels of '
	                   '30 m | 6 images | bands red, green, blue | reflectance 0.01234 to 0.3104 (p2-p98)\n')
	assert '1/1 tiles' in out.err


def test_the_command_line_writes_both_on_the_same_grid(downloads, capsys, tmp_path):
	"""With --out and --rgb, the map of the variable and the true colour of the same images, with the same arguments;
	the true colour on the pixels of the map (those of its answer), so that both are on the same grid."""
	from monitoreo import cli
	tif, rgb = str(tmp_path / 'ndvi.tif'), str(tmp_path / 'ndvi_rgb.tif')
	cli.main(['image', 'NDVI', '--sensor', 'Landsat'] + ARGS + ['--metric', 'max', '--temporal', 'annual',
	                                                            '--interannual', 'median', '--where', json.dumps(ABOVE),
	                                                            '--out', tif, '--rgb', rgb])
	image, colour = _downloads(downloads)
	assert (image['tool'], image['path'], image['resolution']) == ('download_image', tif, None)
	assert (colour['tool'], colour['path'], colour['resolution']) == ('download_rgb', rgb, 20.0)  # that of the map
	same = ('region', 'variable', 'sensor', 'start', 'end', 'metric', 'temporal', 'interannual', 'where')
	assert {k: image[k] for k in same} == {k: colour[k] for k in same}
	assert (colour['metric'], colour['temporal'], colour['interannual'], colour['where']) == \
	       ('max', 'annual', 'median', ABOVE)
	lines = capsys.readouterr().out.splitlines()
	assert lines[0] == (f'{tif}: NDVI Landsat | 2021-06-01 / 2021-06-30 (max) | 60 x 40 pixels of 20 m | 6 images | '
	                    'p5-p95 0.1234 to 0.8 [unitless]')
	assert lines[1].startswith(f'{rgb}: NDVI Landsat | 2021-06-01 / 2021-06-30 (max), true colour | 60 x 40 pixels of '
	                           '20 m | 6 images | bands red, green, blue | reflectance 0.01234 to 0.3104 (p2-p98)')
	assert len(lines) == 2


def test_the_command_line_needs_out_or_rgb(downloads, capsys):
	from monitoreo import cli
	with pytest.raises(SystemExit) as e:
		cli.main(['image', 'NDVI', '--sensor', 'Sentinel-2'] + ARGS)
	err = capsys.readouterr().err
	assert e.value.code == 2 and 'usage: monitoreo image' in err
	assert 'monitoreo image: error: give --out (GeoTIFF of the variable), --rgb (GeoTIFF of its true colour) or ' \
	       'both' in err
	assert not downloads  # not even connected to Earth Engine
	with pytest.raises(SystemExit) as e:
		cli.main(['image', '--help'])
	assert e.value.code == 0
	text = ' '.join(capsys.readouterr().out.split())
	assert '--out OUT GeoTIFF file of the variable' in text and '--rgb FILE GeoTIFF file of the true colour' in text
	assert '[--out F.tif] [--rgb F.tif]' in cli.__doc__


def test_the_command_line_refuses_what_has_no_true_colour(downloads, capsys, tmp_path):
	"""What has no true colour is refused with a message, before Earth Engine computes anything: with --out too,
	before the map of the variable."""
	from monitoreo import cli
	tif, rgb = str(tmp_path / 'ndvi.tif'), str(tmp_path / 'ndvi_rgb.tif')
	with pytest.raises(SystemExit, match=r'^ERROR: NDVI \(Modis\) has no true colour: only the variables of'):
		cli.main(['image', 'NDVI', '--sensor', 'Modis'] + ARGS + ['--out', tif, '--rgb', rgb])
	with pytest.raises(SystemExit, match=r'^ERROR: the true colour of the images takes the metrics .*not a colour'):
		cli.main(['image', 'NDVI', '--sensor', 'Sentinel-2'] + ARGS + ['--metric', 'sum', '--out', tif, '--rgb', rgb])
	with pytest.raises(SystemExit, match='^ERROR: '):  # a region that is not JSON: a message, not a traceback
		cli.main(['image', 'NDVI', '--sensor', 'Sentinel-2', '--region', '{"bbox": [0, 0,', '--rgb', rgb])
	assert not _downloads(downloads)


def test_the_command_line_gives_the_errors_of_the_services(monkeypatch):
	"""The ValueError of services.download_rgb and services.download_image (the real ones, which refuse before Earth
	Engine) end the command with their message."""
	from monitoreo import cli
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	with pytest.raises(SystemExit, match=r'^ERROR: ELEVATION \(Copernicus\) is a fixed layer'):
		cli.main(['image', 'ELEVATION', '--sensor', 'Copernicus', '--region', json.dumps(REGION), '--rgb', 'x.tif'])
	with pytest.raises(SystemExit, match=r'^ERROR: LST \(Modis\) has no true colour'):
		cli.main(['image', 'LST', '--sensor', 'Modis'] + ARGS + ['--rgb', 'x.tif'])
	with pytest.raises(SystemExit, match="^ERROR: .*only takes the metric 'mean'"):  # the map alone too
		cli.main(['image', 'SCF', '--sensor', 'Landsat'] + ARGS + ['--out', 'x.tif'])


def test_the_command_line_without_valid_pixels(downloads, monkeypatch, capsys):
	from monitoreo import cli
	monkeypatch.setattr(services, 'download_rgb', lambda *a, **k: {'file': k['path'], 'min': None, 'max': None})
	cli.main(['image', 'NDVI', '--sensor', 'Sentinel-2'] + ARGS + ['--rgb', 'x_RGB.tif'])
	assert capsys.readouterr().out == 'x_RGB.tif: no valid pixel\n'


@pytest.fixture
def mcp(monkeypatch, tmp_path):
	"""The MCP server, writing to TMP_PATH, without connecting to Earth Engine."""
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	monkeypatch.setattr(services, 'eecu_warning', lambda *a, **k: None)
	return mcp_server


def test_the_mcp_server_maps_the_true_colour(mcp, monkeypatch, tmp_path):
	calls = []

	def rgb_map(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
	            interannual='mean', season=None, quality=None, vmin=None, vmax=None, clip=True, thumbnail=None,
	            quick=False, **source):
		calls.append(dict(source, region=region, variable=variable, sensor=sensor, start=start, end=end, metric=metric,
		                  temporal=temporal, interannual=interannual, season=season, quality=quality, vmin=vmin,
		                  vmax=vmax, thumbnail=thumbnail, quick=quick))
		if thumbnail:
			with open(thumbnail, 'wb') as f:
				f.write(PNG)
		return {'url': 'https://earthengine.googleapis.com/v1/projects/p/maps/m/tiles/{z}/{x}/{y}',
		        'bands': list(sensors.RGB_BANDS), 'min': 0.0 if quick else vmin, 'max': 0.3 if quick else vmax,
		        'name': f'{variable} {sensor} | {start} / {end} ({metric}), true colour', 'unit': catalog.RGB_UNIT,
		        'bounds': REGION['bbox'], 'thumbnail': thumbnail}

	monkeypatch.setattr(services, 'rgb_map', services._cited(rgb_map))
	out = mcp.rgb_map(REGION, 'NDVI', 'Sentinel-2', *JUNE, season=['06-01', '06-30'], vmin=0.02, vmax=0.25,
	                  where=ABOVE)
	assert len(out) == 2 and isinstance(out[1], mcp.Image)  # the answer and its preview
	call = calls[-1]
	assert (call['metric'], call['temporal'], call['interannual'], call['quick']) == ('median', 'period', 'mean', False)
	assert (call['vmin'], call['vmax'], call['where'], call['season']) == (0.02, 0.25, ABOVE, ['06-01', '06-30'])
	assert os.path.dirname(call['thumbnail']) == str(tmp_path)
	assert re.fullmatch(r'rgb_NDVI_Sentinel-2_median_2021-06-01_2021-06-30_\d{8}-\d{6}\.png',
	                    os.path.basename(call['thumbnail']))
	answer = json.loads(out[0])
	assert answer['bands'] == ['red', 'green', 'blue'] and (answer['min'], answer['max']) == (0.02, 0.25)
	assert answer['unit'] == '[unitless]' and 'palette' not in answer and answer['url'].endswith('{z}/{x}/{y}')
	ids = {r['id'] for r in answer['references']}
	assert {'esa_s2_l2a', 'gorelick2017', 'monitoreo'} <= ids and 'tucker1979' not in ids  # not the NDVI formula
	assert answer['credits'][0] == 'Contains modified Copernicus Sentinel data 2021'
	assert 'Copernicus WorldDEM-30' in answer['credits'][1]  # that of the elevation of where
	out = mcp.rgb_map(REGION, 'NDVI', 'Sentinel-2', *JUNE, quick=True)  # only the tiles, at once
	assert len(out) == 1 and calls[-1]['thumbnail'] is None and calls[-1]['quick'] is True
	assert json.loads(out[0])['max'] == 0.3
	assert not (tmp_path / 'calls.jsonl').exists()  # tiles are no file: not in the log of publish_report


def test_the_mcp_server_downloads_the_true_colour(mcp, monkeypatch, tmp_path):
	gdal = pytest.importorskip('osgeo.gdal')
	gdal.UseExceptions()
	calls = []

	def download_rgb(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
	                 interannual='mean', season=None, quality=None, resolution=None, crs='auto', path=None, clip=True,
	                 max_pixels=None, tile=512, workers=8, progress=None, **source):
		calls.append(dict(source, metric=metric, temporal=temporal, interannual=interannual, season=season,
		                  quality=quality, resolution=resolution, crs=crs, path=path, clip=clip))
		ds = gdal.GetDriverByName('GTiff').Create(path, 4, 3, 3, gdal.GDT_Float32)
		ds.SetGeoTransform([450000, 60, 0, 4110000, 0, -60])
		ds.SetProjection('EPSG:32630')
		for i, b in enumerate(sensors.RGB_BANDS):
			ds.GetRasterBand(i + 1).SetDescription(b)
		ds = None
		return {'file': path, 'grid': {'width': 4, 'height': 3, 'resolution': 60, 'crs': 'EPSG:32630'},
		        'resolution': 60, 'native_resolution': 30, 'images': 4, 'unit': catalog.RGB_UNIT,
		        'name': f'{variable} {sensor} | {start} / {end} ({metric}), true colour',
		        'bands': list(sensors.RGB_BANDS), 'min': 0.01, 'max': 0.31}

	monkeypatch.setattr(services, 'download_rgb', services._cited(download_rgb))
	answer = json.loads(mcp.download_rgb(REGION, 'NDVI', 'Landsat', *JUNE, metric='p50', temporal='annual',
	                                     interannual='median', quality={'snow': False}, resolution=60, where=ABOVE))
	call = calls[-1]
	assert (call['metric'], call['temporal'], call['interannual'], call['quality']) == \
	       ('p50', 'annual', 'median', {'snow': False})
	assert (call['resolution'], call['crs'], call['clip'], call['where'], call['collection']) == \
	       (60, 'auto', True, ABOVE, None)
	assert answer['file'] == call['path'] and os.path.dirname(answer['file']) == str(tmp_path)
	assert re.fullmatch(r'NDVI_Landsat_p50_2021-06-01_2021-06-30_RGB_\d{8}-\d{6}\.tif', os.path.basename(answer['file']))
	assert answer['bands'] == ['red', 'green', 'blue'] and 'palette' not in answer
	assert os.path.isfile(answer['readme'])  # the README next to the GeoTIFF, as the other tools
	assert 'usgs_landsat89' in {r['id'] for r in answer['references']}
	assert 'Landsat Collection 2 Level-2 data courtesy of the U.S. Geological Survey' in answer['credits']
	ds = gdal.Open(answer['file'])
	assert [ds.GetRasterBand(i).GetDescription() for i in (1, 2, 3)] == ['red', 'green', 'blue']
	ds = None
	[logged] = [json.loads(x) for x in open(tmp_path / 'calls.jsonl', encoding='utf-8')]  # for publish_report
	assert logged['tool'] == 'download_rgb' and logged['result']['file'] == answer['file']
	assert (logged['args']['variable'], logged['args']['sensor'], logged['args']['metric']) == ('NDVI', 'Landsat', 'p50')


def test_the_refusals_reach_the_mcp_client(mcp, tmp_path):
	"""What has no true colour reaches the client as an error with the message of services (the real ones, which
	refuse before Earth Engine), not as an image."""
	with pytest.raises(mcp.ToolError, match=r'ValueError: NDVI \(Modis\) has no true colour: only the variables of'):
		mcp.rgb_map(REGION, 'NDVI', 'Modis', *JUNE)
	with pytest.raises(mcp.ToolError, match='not a colour'):
		mcp.download_rgb(REGION, 'NDVI', 'Sentinel-2', *JUNE, metric='sum')
	with pytest.raises(mcp.ToolError, match='burn_severity'):
		mcp.download_rgb(REGION, 'RBR', 'Sentinel-2', *JUNE)
	args = {'region': REGION, 'variable': 'PRECIP', 'sensor': 'TerraClimate', 'start': JUNE[0], 'end': JUNE[1],
	        'metric': 'mean'}
	with pytest.raises(mcp.ToolError, match=r'PRECIP \(TerraClimate\) has no true colour'):
		asyncio.run(mcp.server.call_tool('rgb_map', args))  # as the server calls it
	try:
		from mcp import Client  # mcp >= 2: a client connected to the server in this process
	except ImportError:
		return

	async def call():
		async with Client(mcp.server) as client:
			return await client.call_tool('download_rgb', args)
	res = asyncio.run(call())
	assert res.is_error and 'PRECIP (TerraClimate) has no true colour' in res.content[0].text
	assert not [f for f in os.listdir(tmp_path) if f.endswith(('.png', '.tif', '.jsonl'))]  # nothing written


def test_the_mcp_server_tells_which_variables_have_true_colour(mcp):
	rows = json.loads(mcp.list_variables())
	assert sum(1 for r in rows if r.get('rgb')) == sum(1 for r in services.list_variables() if r.get('rgb')) > 0
	have = {(r['variable'], r['sensor']) for r in rows if r.get('rgb')}
	assert {('NDVI', 'Sentinel-2'), ('NBR', 'Landsat'), ('CF', 'Modis')} <= have
	assert not have & {('NDVI', 'Modis'), ('RBR', 'Sentinel-2'), ('ELEVATION', 'Copernicus'), ('PRECIP', 'ERA5-Land')}
	assert all(r.get('rgb') for r in json.loads(mcp.list_variables(sensor='Landsat')) if r['variable'] != 'RBR')
	assert json.loads(mcp.describe_variable('NDVI', 'Sentinel-2'))['rgb'] is True
	assert json.loads(mcp.describe_variable('NDVI', 'Modis'))['rgb'] is False
	assert 'rgb' in mcp.list_variables.__doc__ and 'rgb' in mcp.describe_variable.__doc__


def test_the_tools_of_the_true_colour_in_the_mcp_server(mcp):
	"""rgb_map and download_rgb take the arguments of map_layer and download_image (the same images and pixels), and
	the model learns what they are and when to use them."""
	params = lambda fn: set(inspect.signature(fn).parameters)  # noqa: E731
	assert params(mcp.rgb_map) == params(mcp.map_layer) | {'preview'}  # its range without the PNG (the assistant)
	assert params(mcp.download_rgb) == params(mcp.download_image)
	for name in ('rgb_map', 'download_rgb'):  # every argument goes to services
		fn, service = getattr(mcp, name), inspect.signature(getattr(services, name)).parameters
		assert params(fn) - set(service) <= {'collection', 'where', 'preview'}, name
		assert 'where: only the pixels' in fn.__doc__ and 'same images and pixels' in fn.__doc__, name
	assert 'burned areas' in mcp.rgb_map.__doc__ and 'rgb in list_variables' in mcp.rgb_map.__doc__
	tools = {t.name: t for t in asyncio.run(mcp.server.list_tools())}
	for name in ('rgb_map', 'download_rgb'):
		schema = getattr(tools[name], 'input_schema', None) or tools[name].inputSchema  # mcp 2.x or 1.x
		assert schema['required'] == ['region', 'variable', 'sensor', 'start', 'end'], name
	text = ' '.join(mcp.INSTRUCTIONS.split())
	assert 'rgb_map (tiles and preview) and download_rgb (GeoTIFF)' in text and 'rgb in list_variables' in text
	assert 'not yet the true colour of download_rgb' in mcp.publish_report.__doc__
