"""Tests of the true colour (RGB) of the images in the assistant (issue #24), without Earth Engine nor a language model:
the model calls rgb_map and download_rgb, their cards (a legend of text, the preview of the three bands of the
GeoTIFF in colour), the select Layer of the map of the page (Index, True colour (RGB), Both) with the true colour of
each date, its tiles again, the views of the map for the report and the page itself."""

import asyncio
import base64
import io
import json
import os

import pytest

from monitoreo import assistant, report
from monitoreo.steps import map_steps

REGION = {'wdpa_id': 389011}
NDVI = {'region': REGION, 'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2018-01-01', 'end': '2021-12-31',
        'temporal': 'annual'}  # a map of interannual values: a map of each year in the page
INDEX = {'url': 'https://ee/index/{z}/{x}/{y}', 'bounds': [-3.6, 36.9, -3.5, 37.0], 'min': 0.1, 'max': 0.8,
         'palette': ['ffffff', '00aa00'], 'unit': '[unitless]'}
RGB = {'url': 'https://ee/rgb/{z}/{x}/{y}', 'bounds': [-3.6, 36.9, -3.5, 37.0], 'bands': ['red', 'green', 'blue'],
       'min': 0.0, 'max': 0.3, 'unit': '[unitless]', 'name': 'NDVI Sentinel-2, true colour'}
TEXT = 'True colour (red, green, blue): reflectance from 0 to 0.3'
PNG = 'data:image/png;base64,iVBORw0KGgo='


@pytest.fixture(autouse=True)
def log(tmp_path, monkeypatch):
	"""The log and the reports of the assistant of the tests, not those of the user."""
	monkeypatch.setattr(assistant, 'LOG', str(tmp_path / 'assistant.log'))
	monkeypatch.setattr(report, 'FOLDER', str(tmp_path / 'informes'))
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)


class FakeAssistant(assistant.Assistant):
	"""An assistant whose MCP server answers the maps of a variable (map_layer) and of the true colour of its images
	(rgb_map), with new tiles at each call, and the statistics and series of a pixel; CALLS has its calls."""

	def __init__(self, *a, **k):
		super().__init__(*a, **k)
		self.calls = []

	async def call(self, name, args):
		self.calls.append((name, args))
		n = len(self.calls)
		if name == 'map_layer':
			return None, [json.dumps({**INDEX, 'url': f'https://ee/index{n}/{{z}}/{{x}}/{{y}}'})], []
		if name == 'rgb_map':
			r = {**RGB, 'url': f'https://ee/rgb{n}/{{z}}/{{x}}/{{y}}'}
			if args.get('vmin') is not None:  # the colours asked for
				r.update(min=args['vmin'], max=args['vmax'])
			return None, [json.dumps(r)], [] if args.get('quick') else [PNG]
		if name == 'region_stats':
			return None, [json.dumps({'rows': [{'region': 'point', 'mean': 0.42, 'n_pixels': 1}], 'unit': '[unitless]'})], []
		return None, [json.dumps({'rows': [], 'csv': '/tmp/x.csv'})], [PNG]


def tool(name, *props):
	return {'name': name, 'description': f'{name}.', 'inputSchema': {'type': 'object', 'properties': {
		**{p: {'type': 'string'} for p in props}, 'region': {'type': 'object'}, 'vmin': {'type': 'number'},
		'vmax': {'type': 'number'}, 'quick': {'type': 'boolean'}, 'crs': {'type': 'string'}}}}


VARIABLE = ('variable', 'sensor', 'start', 'end', 'metric', 'temporal')
TOOLS = [tool('map_layer', *VARIABLE), tool('rgb_map', *VARIABLE), tool('download_rgb', *VARIABLE, 'resolution')]


def new(cls=FakeAssistant):
	a = cls({**assistant.DEFAULTS, 'project': 'p'})
	a.tools = assistant.model_tools(TOOLS)
	a.names = {'389011': 'Sierra Nevada (Parque Nacional)'}  # found by find_protected_areas
	return a


def run(a, name, args):
	return asyncio.run(_events(a.run_tool({'name': name, 'arguments': args})))


async def _events(events):
	return [e async for e in events]


def test_the_model_calls_the_true_colour():
	# rgb_map and download_rgb are compute tools: their answers go to the page and the report, the model gets a
	# receipt; the colours (vmin, vmax) and quick are not for the model, as in map_layer
	tools = {t['function']['name']: t['function'] for t in assistant.model_tools(TOOLS)}
	assert 'rgb_map' in assistant.RESULTS and 'download_rgb' in assistant.RESULTS
	for name in ('rgb_map', 'download_rgb'):
		props = tools[name]['parameters']['properties']
		assert not {'vmin', 'vmax', 'quick', 'crs'} & set(props) and 'variable' in props, name
		assert tools[name]['description'].endswith(assistant.RECEIPT_NOTE)
	for text in (assistant.instructions(), assistant.instructions(big=True)):
		assert 'rgb_map, with the same arguments as map_layer' in text
		assert 'download_rgb, with those of download_image' in text
		assert 'interpret the map of an index with the colours of its images' in text
	big = assistant.instructions(big=True)
	assert 'Layer shows the Index, the True colour (RGB) of the same images and dates, or Both' in big


def test_card_of_the_true_colour_map(tmp_path):
	# a map of the true colour (rgb_map): its legend is a text with the range of the reflectance, without palette; its
	# map has no value of the pixel (that of the variable is in its map) nor a select Layer, and a map of each year
	a = new()
	events = run(a, 'rgb_map', NDVI)
	result = next(e for e in events if e['type'] == 'result')
	assert result['legend'] == {'text': TEXT} and result['image'] == PNG
	assert result['map'] == {'url': 'https://ee/rgb1/{z}/{x}/{y}', 'bounds': RGB['bounds'], 'pixel': False,
	                         'trend': False}
	assert result['rgb'] is False  # it is the true colour already
	assert result['title'].startswith('True colour of the images of NDVI (Sentinel-2), 2018-2021')
	assert [s['label'] for s in result['steps']] == ['2018', '2019', '2020', '2021']
	assert a.calls[0] == ('rgb_map', NDVI) and 'Done:' in a.messages[-1]['content']
	assert '0.3' not in a.messages[-1]['content']  # the model gets no values
	assert 'Colours' in dict(result['facts'])
	# a year: the true colour of its images, with the colours of the map of the result
	shown = asyncio.run(a.step_map(1, '2019-01-01/2019-12-31'))
	assert a.calls[-1] == ('rgb_map', {'region': REGION, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
	                                   'start': '2019-01-01', 'end': '2019-12-31', 'metric': 'median', 'vmin': 0.0,
	                                   'vmax': 0.3, 'quick': True})
	assert shown['legend'] == {'text': TEXT} and shown['map']['pixel'] is False
	assert shown['heading'].startswith('True colour of the images of Normalized Difference Vegetation Index (NDVI, '
	                                   'Sentinel-2), 2019')
	# the report: the legend of text under its preview, not a bar of colours
	html = open(a.write_report('RGB'), encoding='utf-8').read()
	assert f'<figcaption class="legend">{TEXT}</figcaption>' in html and 'linear-gradient' not in html
	assert report.map_style('rgb_map', {}, {'min': 0.01, 'max': 0.25}) == {
		'band': [1, 2, 3], 'min': 0.01, 'max': 0.25,
		'text': 'True colour (red, green, blue): reflectance from 0.01 to 0.25'}
	assert report._legend({'min': 0, 'max': 1}) == ''  # neither palette nor text: no legend, and no error


def _rgb_tif(path):
	"""A GeoTIFF of download_rgb (bands red, green and blue, reflectance, NoData -9999): the left half red, the right
	half cyan, the first 3 rows without data."""
	import numpy as np
	from osgeo import gdal, osr
	gdal.UseExceptions()
	ds = gdal.GetDriverByName('GTiff').Create(path, 40, 20, 3, gdal.GDT_Float32)
	srs = osr.SpatialReference()
	srs.ImportFromEPSG(32630)
	ds.SetProjection(srs.ExportToWkt())
	ds.SetGeoTransform([450000, 10, 0, 4090000, 0, -10])
	for i, (left, right) in enumerate([(0.3, 0.0), (0.0, 0.3), (0.0, 0.3)], 1):
		a = np.full((20, 40), right, dtype='float32')
		a[:, :20] = left
		a[:3] = -9999
		b = ds.GetRasterBand(i)
		b.SetNoDataValue(-9999)
		b.SetDescription(['red', 'green', 'blue'][i - 1])
		b.WriteArray(a)
	ds = None


def _png(url):
	"""The pixels (rows of [r, g, b, a] of 0 to 255) of a PNG data: URL."""
	from matplotlib import image
	a = image.imread(io.BytesIO(base64.b64decode(url.split(',', 1)[1])), format='png')
	return (a * 255).round().astype(int)


def test_card_of_the_true_colour_geotiff(tmp_path):
	# the GeoTIFF of download_rgb: its card shows its three bands as colours (not its first band with a ramp), with
	# the legend of text; the file to download
	pytest.importorskip('osgeo')
	pytest.importorskip('matplotlib')
	path = str(tmp_path / 'NDVI_RGB.tif')
	_rgb_tif(path)

	class Downloads(FakeAssistant):
		async def call(self, name, args):
			self.calls.append((name, args))
			return None, [json.dumps({'file': path, 'grid': {'crs': 'EPSG:32630', 'width': 40, 'height': 20},
			                          'resolution': 10, 'native_resolution': 10, 'images': 7, 'unit': '[unitless]',
			                          'bands': ['red', 'green', 'blue'], 'min': 0.0, 'max': 0.3,
			                          'name': 'NDVI Sentinel-2, true colour'})], []

	a = new(Downloads)
	result = next(e for e in run(a, 'download_rgb', {**NDVI, 'temporal': 'period'}) if e['type'] == 'result')
	px = _png(result['image'])
	assert px.shape[:2] == (20, 40)
	assert px[10, 5].tolist() == [255, 0, 0, 255] and px[10, 35].tolist() == [0, 255, 255, 255]  # its colours
	assert px[1, 5][3] == 0  # transparent without data
	assert result['legend'] == {'text': TEXT} and 'map' not in result
	assert result['files'][0]['name'] == 'NDVI_RGB.tif'
	assert result['title'].endswith('(GeoTIFF) · Sierra Nevada (Parque Nacional)')
	# without the range: stretched between the lowest percentile 2 and the highest percentile 98 of the bands
	assert _png(report.tif_preview(path, band=[1, 2, 3]))[10, 35].tolist() == [0, 255, 255, 255]
	assert report.tif_preview(path, band=(1, 2, 3), vmin=0, vmax=0.6) is not None
	assert report.tif_preview(str(tmp_path / 'nothing.tif'), band=[1, 2, 3]) is None
	html = open(a.write_report('RGB'), encoding='utf-8').read()
	assert TEXT in html and 'NDVI_RGB.tif' in html


def test_the_select_layer_of_the_map():
	# the page offers Layer (Index, True colour (RGB), Both) only in the maps of a variable whose images have a true
	# colour, with dates and a metric that gives colours (as rgb_map refuses the others before Earth Engine)
	def rgb(tool, **args):
		return assistant.true_colour({'tool': tool, 'args': {'region': REGION, **args}})

	june = {'start': '2021-06-01', 'end': '2021-06-30'}
	assert rgb('map_layer', variable='NDVI', sensor='Sentinel-2', **june)
	assert rgb('map_layer', variable='NBR', sensor='Landsat', metric='max', **june)
	assert rgb('map_layer', variable='SCF', sensor='Landsat', metric='mean', **june)
	assert rgb('map_layer', variable='CF', sensor='Modis', metric='mean', **june)  # MOD09GA: red, green and blue
	assert rgb('map_layer', variable='NDVI', sensor='Sentinel-2', temporal='annual', interannual='median', **june)
	assert not rgb('map_layer', variable='NDVI', sensor='Modis', **june)  # MOD13Q1: no green band
	assert not rgb('map_layer', variable='LST', sensor='Modis', **june)
	assert not rgb('map_layer', variable='PRECIP', sensor='TerraClimate', metric='sum', **june)
	assert not rgb('map_layer', variable='ELEVATION', sensor='Copernicus')  # a fixed layer, without dates
	assert not rgb('map_layer', variable='NDVI', sensor='Sentinel-2', metric='sum', **june)  # sum: not a colour
	assert not rgb('map_layer', variable='NDVI', sensor='Sentinel-2', temporal='annual', interannual='std', **june)
	assert not rgb('map_layer', variable='NOPE', sensor='Sentinel-2', **june)
	assert not rgb('trend_map', variable='NDVI', sensor='Sentinel-2', **june)  # trends and comparisons: no
	assert not rgb('compare_map', variable='NDVI', sensor='Sentinel-2', **june)
	assert not rgb('rgb_map', variable='NDVI', sensor='Sentinel-2', **june)  # it is the true colour already

	# the cards: the result of map_layer and the map of the period of a series, with 'rgb' out of 'map'
	a = new()
	ndvi = next(e for e in run(a, 'map_layer', NDVI) if e['type'] == 'result')
	assert ndvi['rgb'] is True and set(ndvi['map']) == {'url', 'bounds', 'pixel', 'trend'}
	modis = next(e for e in run(a, 'map_layer', {**NDVI, 'sensor': 'Modis'}) if e['type'] == 'result')
	assert modis['rgb'] is False and modis['map']['pixel'] is True
	elevation = next(e for e in run(a, 'map_layer', {'region': REGION, 'variable': 'ELEVATION',
	                                                 'sensor': 'Copernicus'}) if e['type'] == 'result')
	assert elevation['rgb'] is False and elevation['map']['series'] is False
	a.results.append({'id': 4, 'tool': 'time_series', 'args': {**NDVI, 'step': 'monthly'}, 'result': {'rows': []},
	                  'image': None, 'title': 'Series'})
	shown = asyncio.run(a.period_map(a.results[-1]))
	assert shown['type'] == 'map' and shown['rgb'] is True and a.results[-1]['map']['tool'] == 'map_layer'
	with pytest.raises(ValueError, match='has no true colour'):
		asyncio.run(a.step_map(2, '', rgb=True))  # NDVI of MODIS


def test_the_true_colour_of_each_date():
	# Layer «True colour (RGB)» or «Both»: the server makes the true colour of the same map, or of its year, with
	# rgb_map and its arguments, once (key with |rgb), with the colours of the first one, so that the years compare;
	# its tiles are asked for again when they expire; Query pixel queries the variable
	a = new()
	run(a, 'map_layer', NDVI)
	a.calls.clear()
	main = asyncio.run(a.step_map(1, '', rgb=True))
	assert main['key'] == '|rgb' and main['legend'] == {'text': TEXT} and main['map']['pixel'] is False
	assert a.calls == [('rgb_map', {**NDVI, 'vmin': None, 'vmax': None, 'quick': False, 'preview': False})]  # its range
	# (once, without the PNG preview of the region, which the page does not show)
	asyncio.run(a.step_map(1, '', rgb=True))
	assert len(a.calls) == 1  # made once
	assert a.results[0]['maps']['|rgb']['title'].startswith('True colour of the images of NDVI (Sentinel-2), 2018-2021')
	# a year: its map of the variable and its true colour, with the colours of the first true colour
	year = '2019-01-01/2019-12-31'
	index = asyncio.run(a.step_map(1, year))
	colour = asyncio.run(a.step_map(1, year, rgb=True))
	assert index['key'] == year and colour['key'] == year + assistant.RGB
	step = {'region': REGION, 'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2019-01-01', 'end': '2019-12-31',
	        'metric': 'median', 'quick': True}
	assert a.calls[1] == ('map_layer', {**step, 'vmin': INDEX['min'], 'vmax': INDEX['max']})
	assert a.calls[2] == ('rgb_map', {**step, 'vmin': RGB['min'], 'vmax': RGB['max'], 'preview': False})
	assert colour['heading'].startswith('True colour of the images of Normalized Difference Vegetation Index (NDVI, '
	                                    'Sentinel-2), 2019')
	# its tiles again, with the same colours
	url = asyncio.run(a.refresh_map(1, year + assistant.RGB))
	assert a.calls[-1] == ('rgb_map', {**{k: v for k, v in step.items() if k != 'quick'}, 'vmin': RGB['min'],
	                                   'vmax': RGB['max'], 'quick': True})
	assert a.results[0]['maps'][year + assistant.RGB]['result']['url'] == url == f'https://ee/rgb{len(a.calls)}/{{z}}/{{x}}/{{y}}'
	# the pixel: the value of the variable on the map of that year (the page asks with the key of the index)
	px = asyncio.run(a.pixel(1, -3.55, 36.95, year))
	assert px['value'] == 0.42 and next(c for c in a.calls if c[0] == 'region_stats')[1]['start'] == '2019-01-01'
	with pytest.raises(ValueError, match='does not exist'):
		asyncio.run(a.step_map(1, '1990-01-01/1990-12-31', rgb=True))


def test_the_api_of_the_true_colour():
	# /api/map/step takes rgb, and passes it to the assistant
	from starlette.requests import Request
	seen = []

	class Fake:
		async def step_map(self, *args):
			seen.append(args)
			return {'key': args[1] + assistant.RGB}

	app = assistant.make_app(Fake(), 'tok', 8765)
	route = next(r for r in app.routes if r.path == '/api/map/step')
	for body in (b'{"id": 1, "key": "2019-01-01/2019-12-31", "rgb": true}', b'{"id": 1, "key": ""}'):
		async def receive(body=body):
			return {'type': 'http.request', 'body': body, 'more_body': False}

		request = Request({'type': 'http', 'method': 'POST', 'path': '/api/map/step', 'query_string': b'',
		                   'headers': [(b'host', b'127.0.0.1:8765'), (b'x-token', b'tok')]}, receive)
		assert asyncio.run(route.endpoint(request)).status_code == 200
	assert seen == [(1, '2019-01-01/2019-12-31', False, True), (1, '', False, False)]


def test_views_of_the_map_with_the_true_colour(tmp_path, monkeypatch):
	# Add this view to the report: what is seen, the true colour alone (its legend of text) or the map of the variable
	# over its true colour (both tiles, the true colour without transparency, and both legends)
	drawn = []

	def map_view(bounds, zoom, overlay, base='osm', opacity=0.85, marker=None):
		drawn.append((overlay, opacity))
		return PNG

	monkeypatch.setattr(report, 'map_view', map_view)
	a = new()
	run(a, 'map_layer', NDVI)
	year = '2019-01-01/2019-12-31'
	asyncio.run(a.step_map(1, year))
	asyncio.run(a.step_map(1, year, rgb=True))
	maps = a.results[0]['maps']
	view = {'bounds': [-3.6, 36.9, -3.5, 37.0], 'zoom': 12, 'base': 'osm', 'opacity': 0.7, 'key': year}
	both = asyncio.run(a.snapshot(1, {**view, 'layer': 'both'}))
	assert drawn[-1] == ([maps[year + assistant.RGB]['result']['url'], maps[year]['result']['url']], [1.0, 0.7])
	card = a.events[-1]
	assert card['under'] == {'text': TEXT} and card['legend']['palette'] == INDEX['palette']
	assert card['title'].endswith('(map view over the true colour of its images)') and 'map' not in card
	alone = asyncio.run(a.snapshot(1, {**view, 'layer': 'rgb'}))
	assert drawn[-1] == (maps[year + assistant.RGB]['result']['url'], 0.7)
	assert a.events[-1]['legend'] == {'text': TEXT} and 'under' not in a.events[-1]
	assert a.results[-1]['tool'] == 'rgb_map' and a.results[-1]['title'].startswith('True colour of the images')
	asyncio.run(a.snapshot(1, view))  # the map of the variable, as before
	assert drawn[-1] == (maps[year]['result']['url'], 0.7)
	html = open(a.write_report('Views', ids=[both, alone]), encoding='utf-8').read()
	assert html.count(f'<figcaption class="legend">{TEXT}</figcaption>') == 2 and 'linear-gradient' in html


def test_map_view_of_two_layers(monkeypatch):
	# report.map_view draws a list of tiles in its order: the true colour, then the map of the variable over it
	pytest.importorskip('PIL')
	from PIL import Image
	colours = {'osm': (200, 200, 200, 255), 'rgb': (255, 0, 0, 255), 'index': (0, 0, 255, 255)}

	def urlopen(req, timeout=None):
		buf = io.BytesIO()
		Image.new('RGBA', (256, 256), next(c for k, c in colours.items() if k in req.full_url)).save(buf, 'PNG')
		return io.BytesIO(buf.getvalue())

	monkeypatch.setattr(report.urllib.request, 'urlopen', urlopen)
	url = report.map_view([-3.6, 36.86, -3.5, 36.93], 13, ['https://ee/rgb/{z}/{x}/{y}', 'https://ee/index/{z}/{x}/{y}'],
	                      'osm', [1.0, 0.5])
	r, g, b = Image.open(io.BytesIO(base64.b64decode(url.split(',')[1]))).getpixel((5, 5))
	assert 120 <= r <= 135 and g <= 5 and 120 <= b <= 135  # the blue at half opacity over the red, not over the grey


def test_steps_of_the_true_colour():
	steps = map_steps('rgb_map', NDVI)
	assert [s['label'] for s in steps] == ['2018', '2019', '2020', '2021']
	assert map_steps('rgb_map', {**NDVI, 'temporal': 'monthly', 'start': '2021-01-01'})[0]['label'] == 'Jan 2021'
	assert map_steps('rgb_map', {**NDVI, 'start': '2021-06-01', 'end': '2021-08-31'}) == []  # one year: one map


def test_the_page_has_the_select_layer():
	with open(os.path.join(os.path.dirname(assistant.__file__), 'ui', 'assistant.html'), encoding='utf-8') as f:
		page = f.read()
	assert all(f'id="{i}"' in page for i in ('layerlabel', 'layer'))
	assert '<label id="layerlabel" hidden' in page  # only in the maps with a true colour
	for value, label in (('index', 'Index'), ('rgb', 'True colour (RGB)'), ('both', 'Both')):
		assert f'<option value="{value}">{label}</option>' in page
	assert "$('layerlabel').hidden = !e.rgb" in page and "api('/api/map/step', {id, key, rgb: true})" in page
	assert "const RGB = '|rgb'" in page and assistant.RGB == '|rgb'  # the same key as the server
	assert 'if (!lg.palette) return lg.text' in page  # the legend of text of the true colour
	assert "layer: under ? 'both'" in page  # the view of the report, as seen


def test_two_true_colours_at_once_share_the_range():
	"""Two dates asked at the same time (the page and a refresh): the first true colour computes the range and the
	other waits for it and takes it, so that the dates can be compared."""
	a = new()
	run(a, 'map_layer', NDVI)
	a.calls.clear()
	fake = a.call

	async def slow(name, args):  # Earth Engine takes a while: the other request comes meanwhile
		await asyncio.sleep(0.01)
		return await fake(name, args)

	a.call = slow

	async def both():
		return await asyncio.gather(a.step_map(1, '', rgb=True), a.step_map(1, '2019-01-01/2019-12-31', rgb=True))

	asyncio.run(both())
	rgb = [c[1] for c in a.calls if c[0] == 'rgb_map']
	assert len(rgb) == 2 and sorted(c['quick'] for c in rgb) == [False, True]
	rgb.sort(key=lambda c: c['quick'])
	assert (rgb[1]['vmin'], rgb[1]['vmax']) == (RGB['min'], RGB['max'])
