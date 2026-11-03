"""Tests of the assistant and of its report that need neither Earth Engine nor a language model."""

import asyncio
import json

import pytest

from monitoreo import assistant, report

TOOLS = [
	{'name': 'time_series', 'description': 'Time series.', 'inputSchema': {'type': 'object', 'properties': {
		'region': {'type': 'object', 'additionalProperties': True}, 'variable': {'type': 'string'},
		'sensor': {'type': 'string'}, 'start': {'type': 'string'}, 'end': {'type': 'string'},
		'season': {'anyOf': [{'type': 'array', 'items': {'type': 'string'}}, {'type': 'null'}]},
		'collection': {'type': 'string'}}, 'required': ['region', 'variable', 'collection']}},
	{'name': 'connect', 'description': 'Connect.', 'inputSchema': {'type': 'object', 'properties': {
		'project': {'type': 'string'}}}},
	{'name': 'find_protected_areas', 'description': 'Protected areas.', 'inputSchema': {'type': 'object', 'properties': {
		'text': {'type': 'string'}, 'limit': {'type': 'integer'}}, 'required': ['text']}},
]
ROWS = [{'region': 'region', 'date': f'2021-{m:02d}-01', 'value': 0.5 + m / 1000, 'n_pixels': 100, 'n_images': 4}
        for m in range(1, 13)]
SERIES = {'title': 'NDVI', 'unit': '[unitless]', 'scale': 10, 'n_steps': 12, 'regions': ['region'], 'rows': ROWS,
          'csv': '/tmp/ndvi.csv', 'chart': None}
ARGS = {'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2021-01-01',
        'end': '2021-12-31'}


def test_model_tools():
	tools = assistant.model_tools(TOOLS)
	assert [t['function']['name'] for t in tools] == ['time_series', 'find_protected_areas']  # not connect
	series = tools[0]['function']
	assert 'collection' not in series['parameters']['properties']
	assert series['parameters']['required'] == ['region', 'variable']
	assert series['description'].endswith(assistant.RECEIPT_NOTE)
	assert 'limit' not in tools[1]['function']['parameters']['properties']


def test_fix_args():
	tools = assistant.model_tools(TOOLS)
	args = assistant.fix_args('time_series', {'region': '{"wdpa_id": 389011}', 'variable': 'NDVI', 'collection': 'X',
	                                          'season': '["06-01", "08-31"]', 'unknown': 1, 'sensor': None}, tools)
	assert args == {'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'season': ['06-01', '08-31']}
	assert assistant.fix_args('time_series', '{"variable": "EVI"}', tools) == {'variable': 'EVI'}


def test_instructions():
	text = assistant.instructions()
	assert 'No interpretes resultados' in text
	assert '- NDVI: ' in text and 'Sentinel-2 10 m desde 2017' in text and 'Landsat 30 m desde 1984' in text


AREAS = {'Sierra': [{'SITE_ID': 389011, 'NAME': 'Sierra Nevada', 'DESIG': 'Parque Nacional'}],
         'Doñana': [{'SITE_ID': 389012, 'NAME': 'Doñana', 'DESIG': 'Parque Nacional'},
                    {'SITE_ID': 349268, 'NAME': 'Doñana', 'DESIG': 'Parque Natural'}]}


@pytest.fixture(autouse=True)
def log(tmp_path, monkeypatch):
	"""The log of the assistant of the tests, not that of the user."""
	monkeypatch.setattr(assistant, 'LOG', str(tmp_path / 'assistant.log'))


class FakeAssistant(assistant.Assistant):
	"""An assistant whose MCP server answers a time series and the protected areas of WDPA."""

	async def call(self, name, args):
		if name == 'find_protected_areas':
			return None, [json.dumps(next((v for k, v in AREAS.items() if k in args.get('text', '')), []))], []
		self.called = (name, args)
		return None, [json.dumps(SERIES)], ['data:image/png;base64,iVBORw0KGgo=']


def test_the_model_does_not_get_the_results(monkeypatch):
	answers = iter([
		{'content': '', 'tool_calls': [{'function': {'name': 'find_protected_areas', 'arguments': {'text': 'Sierra'}}}]},
		{'content': '', 'tool_calls': [{'function': {'name': 'time_series', 'arguments': ARGS}}]},
		{'content': 'Listo: la serie está en pantalla.'},
	])
	seen = []

	def model(settings, system, messages, tools):
		seen.append(json.dumps(messages, ensure_ascii=False))
		return next(answers)

	monkeypatch.setattr(assistant, 'chat_model', model)
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)

	async def run():
		a = FakeAssistant({**assistant.DEFAULTS, 'project': 'p', 'ollama': 'http://127.0.0.1:1'})
		a.tools = assistant.model_tools(TOOLS)
		return a, [e async for e in a.chat('NDVI de Sierra Nevada en 2021')]

	a, events = asyncio.run(run())
	assert [e['type'] for e in events if e['type'] != 'status'] == ['areas', 'running', 'result', 'assistant']
	assert next(e for e in events if e['type'] == 'areas')['areas'] == [
		{'SITE_ID': 389011, 'NAME': 'Sierra Nevada', 'DESIG': 'Parque Nacional', 'match': False}]
	result = next(e for e in events if e['type'] == 'result')
	assert result['table']['rows'][0][1] == '0,501' and result['image'].startswith('data:image/png')
	assert 'Sierra Nevada (Parque Nacional) (WDPA 389011)' in dict(result['facts'])['Región']
	assert 'Sierra Nevada' in seen[1]  # the answer of an advice tool goes to the model
	assert '0.501' not in seen[2] and '0,501' not in seen[2] and 'Hecho:' in seen[2]  # that of a result does not
	assert len(a.results) == 1 and a.question == 'NDVI de Sierra Nevada en 2021'


def test_unknown_protected_area(monkeypatch):
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)
	a = FakeAssistant({**assistant.DEFAULTS, 'project': 'p'})
	a.tools = assistant.model_tools(TOOLS)

	async def run(user, args=ARGS):
		a.reset()
		a.messages.append({'role': 'user', 'content': user})
		return [e async for e in a.run_tool({'name': 'time_series', 'arguments': args})]

	# 389011, made up or copied: the assistant searches the place named and takes the one of the designation asked for
	events = asyncio.run(run('Serie del NDVI en el Parque Nacional de Doñana'))
	assert [e['type'] for e in events if e['type'] != 'status'] == ['areas', 'running', 'result']
	assert a.called[1]['region'] == {'wdpa_id': 389012}
	# without the designation, two areas: the model gets them, the user sees them, nothing is computed
	events = asyncio.run(run('Serie del NDVI de Doñana'))
	assert [e['type'] for e in events if e['type'] != 'status'] == ['areas']
	assert 'SITE_ID 389012' in a.messages[-1]['content'] and 'pregúntale cuál' in a.messages[-1]['content']
	# no place in the message: the model has to search it, without asking the user
	assert asyncio.run(run('ndvi de un parque')) == [] and 'Busca tú el espacio' in a.messages[-1]['content']
	# the model gives the right one (it is among those found)
	events = asyncio.run(run('NDVI de Sierra Nevada'))
	assert events[-1]['type'] == 'result' and a.called[1]['region'] == {'wdpa_id': 389011}
	assert [e['type'] for e in asyncio.run(run('El de WDPA 389011'))][-1] == 'result'  # an ID the user gave


def test_place_in():
	assert assistant.place_in('Evolución mensual del NDVI en el Parque Nacional de Sierra Nevada en 2023') == \
	       'Parque Nacional de Sierra Nevada'
	assert assistant.place_in('Doñana en 2024, NDVI') == 'Doñana'
	assert assistant.place_in('Compara los veranos del Parque Natural de la Sierra de Cazorla, Segura y Las Villas') == \
	       'Parque Natural de la Sierra de Cazorla, Segura y Las Villas'
	assert assistant.place_in('Quiero el NDVI de Sentinel-2') is None
	assert assistant.place_in('ndvi en sierra nevada') is None
	assert assistant.place_in('Usa el del Parque Nacional') is None  # only a designation


def test_not_ready(monkeypatch):
	monkeypatch.setattr(assistant, 'signed_in', lambda: False)
	a = FakeAssistant({**assistant.DEFAULTS, 'project': 'p'})
	a.tools = assistant.model_tools(TOOLS)

	async def run():
		args = {**ARGS, 'region': {'bbox': [-3.62, 36.86, -3.50, 36.93]}}
		return [e async for e in a.run_tool({'name': 'time_series', 'arguments': args})]

	events = asyncio.run(run())
	assert events[0]['type'] == 'error' and 'inicia sesión' in events[0]['text'] and not a.results


def test_report(tmp_path):
	items = [{'tool': 'time_series', 'args': ARGS, 'result': SERIES},
	         {'tool': 'time_series', 'args': ARGS, 'result': {**SERIES, 'rows': ROWS * 5}},
	         {'tool': 'region_stats', 'args': ARGS, 'result': [{'region': 'r', 'mean': 0.4, 'n_pixels': 1234}]}]
	path = report.write(items, str(tmp_path / 'informe.html'), title='NDVI <2021>', question='¿NDVI?', project='p',
	                    names={'389011': 'Sierra Nevada'})
	text = open(path, encoding='utf-8').read()
	assert '<title>NDVI &lt;2021&gt;</title>' in text and 'calculado en Google Earth Engine con el proyecto p' in text
	assert 'Sierra Nevada (WDPA 389011)' in text and 'Serie mensual de NDVI (Sentinel-2), 2021' in text
	assert '<td>0,501</td>' in text and '1.234' in text  # numbers as written in Spanish
	assert 'Anexo: tablas completas' in text and 'Tabla 2.' in text  # the table of 60 rows goes to the annex
	assert 'mo.time_series(region={&quot;wdpa_id&quot;: 389011}' in text and 'zenodo' in text.lower()
	assert text.count('data:image/') >= 3  # the logos, embedded
	assert report.item_table('trend_table', {'unit': '[ºC]', 'trends': [
		{'label': 'enero', 'n': 20, 'slope': 0.05, 'p_value': 0.01, 'significant': True}]})[0] == \
	       ['Parte del año', 'Años', 'Pendiente de Sen (°C/año)', 'p-valor', 'Significativa']


def _polygons(path, driver):
	"""Two squares of 1 km (100 ha) in ETRS89 / UTM 30N with the field nombre, written with GDAL."""
	from osgeo import ogr, osr
	ogr.UseExceptions()
	srs = osr.SpatialReference()
	srs.ImportFromEPSG(25830)
	ds = ogr.GetDriverByName(driver).CreateDataSource(str(path))
	lyr = ds.CreateLayer('parcelas', srs, ogr.wkbPolygon)
	lyr.CreateField(ogr.FieldDefn('nombre', ogr.OFTString))
	for i, name in enumerate(('norte', 'sur')):
		x, y = 450000, 4110000 - 2000 * i
		f = ogr.Feature(lyr.GetLayerDefn())
		f.SetField('nombre', name)
		f.SetGeometry(ogr.CreateGeometryFromWkt(f'POLYGON(({x} {y},{x + 1000} {y},{x + 1000} {y + 1000},{x} {y + 1000},'
		                                        f'{x} {y}))'))
		lyr.CreateFeature(f)
	ds = None


def test_layers(tmp_path, monkeypatch):
	pytest.importorskip('osgeo')
	import zipfile
	monkeypatch.setattr(assistant, 'LAYERS', str(tmp_path / 'capas'))
	_polygons(tmp_path / 'Mis parcelas.gpkg', 'GPKG')
	(tmp_path / 'shp').mkdir()
	_polygons(tmp_path / 'shp' / 'parcelas.shp', 'ESRI Shapefile')
	with zipfile.ZipFile(tmp_path / 'parcelas.zip', 'w') as z:
		for p in (tmp_path / 'shp').iterdir():
			z.write(p, f'carpeta/{p.name}')
	a = assistant.Assistant({**assistant.DEFAULTS})
	gpkg = a.add_layer('Mis parcelas.gpkg', (tmp_path / 'Mis parcelas.gpkg').read_bytes())
	assert gpkg['name'] == 'mis_parcelas' and gpkg['features'] == 2 and abs(gpkg['area_ha'] - 200) < 0.5
	assert gpkg['crs'] == 'EPSG:25830' and gpkg['name_field'] == 'nombre'
	shp = a.add_layer('parcelas.zip', (tmp_path / 'parcelas.zip').read_bytes())
	assert shp['file'].startswith('/vsizip/') and shp['file'].endswith('carpeta/parcelas.shp') and shp['features'] == 2
	assert '- parcelas (2 polígonos, 200 ha, nombres del campo nombre): región {"capa": "parcelas"}' in a.system_prompt()
	args = a.with_layer({'region': {'capa': 'Mis parcelas'}, 'variable': 'NDVI'})
	assert args == {'region': {'file': gpkg['file'], 'name_field': 'nombre'}, 'variable': 'NDVI'}
	for region in ('mis_parcelas', 'Mis parcelas', {'area_de_estudio': 'mis_parcelas'}, 'capa mis_parcelas',
	               {'capa': 'el área de estudio «mis_parcelas»'}):  # the ways small models give it
		assert a.with_layer({'region': region})['region'] == args['region']
	with pytest.raises(ValueError, match='no hay ningún área de estudio'):
		a.with_layer({'region': {'capa': 'otra'}})
	a.messages.append({'role': 'user', 'content': 'Serie del NDVI en el área de estudio mis_parcelas'})
	assert a.with_layer({'region': {'capa': 'nombre'}})['region'] == args['region']  # the example, copied
	assert a.with_layer({'region': {'bbox': [0, 0, 1, 1]}}) == {'region': {'bbox': [0, 0, 1, 1]}}
	assert report.region_text(args['region'], a.all_names()).startswith('Área de estudio «mis_parcelas» (2 polígonos')
	assert set(assistant.Assistant({**assistant.DEFAULTS}).layers) == {'mis_parcelas', 'parcelas'}  # kept
	a.remove_layer('parcelas')
	assert set(assistant.load_layers()) == {'mis_parcelas'} and not (tmp_path / 'capas' / 'parcelas.zip').exists()
	with pytest.raises(ValueError, match='formato no admitido'):
		a.add_layer('parcelas.shp', b'')


def test_areas_text():
	areas = [{'SITE_ID': 68175, 'NAME': 'Parque Nacional de Doñana', 'DESIG': 'Ramsar Site', 'REP_AREA': 1116.0},
	         {'SITE_ID': 389012, 'NAME': 'Doñana', 'DESIG': 'Parque Nacional', 'REP_AREA': 534.2}]
	lines = assistant.areas_text(areas, 'NDVI en el Parque Nacional de Doñana').splitlines()
	assert lines[1] == '- SITE_ID 389012: Doñana, Parque Nacional, 534,2 km² (su designación coincide con la consulta)'
	assert lines[2] == '- SITE_ID 68175: Parque Nacional de Doñana, Ramsar Site, 1.116 km²'
	assert 'Ningún espacio' in assistant.areas_text([], 'x')


def test_search_name():
	assert assistant.search_name('Parque Nacional de Doñana') == 'Doñana'
	assert assistant.search_name('parque natural de la Sierra de Cazorla') == 'Sierra de Cazorla'
	assert assistant.search_name('Reserva Natural Concertada del Peñón') == 'Peñón'
	assert assistant.search_name('ZEPA Doñana') == 'Doñana'
	assert assistant.search_name('Sierra Nevada') == 'Sierra Nevada'
	assert assistant.search_name('Parque Nacional') == 'Parque Nacional'  # nothing else: as it was


FAKE_OLLAMA = '''#!{python}
"""A fake ollama: `ollama serve` answers /api/version and /api/tags at OLLAMA_HOST."""
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
	def log_message(self, *a): pass
	def do_GET(self):
		body = json.dumps({{'version': 'fake'}} if self.path == '/api/version' else {{'models': []}}).encode()
		self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers()
		self.wfile.write(body)
host, port = os.environ['OLLAMA_HOST'].split(':')
assert sys.argv[1:] == ['serve']
HTTPServer((host, int(port)), H).serve_forever()
'''


def _free_port():
	import socket
	with socket.socket() as s:
		s.bind(('127.0.0.1', 0))
		return s.getsockname()[1]


def test_engine_install_and_start(tmp_path, monkeypatch):
	import hashlib
	import io
	import sys
	import tarfile
	from monitoreo import engine
	if sys.platform == 'win32':
		pytest.skip('the fake ollama is a script')
	script = FAKE_OLLAMA.format(python=sys.executable).encode()
	buf = io.BytesIO()
	with tarfile.open(fileobj=buf, mode='w:gz') as t:
		info = tarfile.TarInfo('ollama')
		info.size, info.mode = len(script), 0o755
		t.addfile(info, io.BytesIO(script))
	data = buf.getvalue()
	monkeypatch.setattr(engine, 'ASSETS', {('x', 'y'): ('ollama-x.tgz', len(data), hashlib.sha256(data).hexdigest())})
	monkeypatch.setattr(engine.platform, 'system', lambda: 'X')
	monkeypatch.setattr(engine.platform, 'machine', lambda: 'Y')
	monkeypatch.setattr(engine, 'PORT', _free_port())
	monkeypatch.setattr(engine, 'SYSTEM_URL', f'http://127.0.0.1:{_free_port()}')  # nothing there
	monkeypatch.setattr(engine, 'system_binary', lambda: None)
	monkeypatch.setattr(engine.urllib.request, 'urlopen', _fake_download(data))
	e = engine.Engine(str(tmp_path / 'ollama'))
	assert e.find() is None and e.installed() is None  # nothing to use: install it
	try:
		steps = [s['status'] for s in e.install()]
		assert steps[0] == 'Descargando Ollama' and steps[-1] == 'success'
		assert e.how == 'started' and e.url == f'http://127.0.0.1:{engine.PORT}' and engine.answers(e.url)
		assert e.installed() == str(tmp_path / 'ollama' / engine.OLLAMA / 'ollama')
	finally:
		e.stop()
	assert e.url is None and not engine.answers(f'http://127.0.0.1:{engine.PORT}')
	try:
		assert e.find() == f'http://127.0.0.1:{engine.PORT}' and e.how == 'started'  # installed: started again
	finally:
		e.stop()
	monkeypatch.setattr(engine, 'ASSETS', {('x', 'y'): ('ollama-x.tgz', len(data), '0' * 64)})
	with pytest.raises(RuntimeError, match='SHA-256'):
		list(e.install())


def _fake_download(data):
	import io
	real = __import__('urllib.request').request.urlopen

	def urlopen(url, *a, **k):
		if isinstance(url, str) and url.startswith('https://github.com/ollama/'):
			return io.BytesIO(data)
		return real(url, *a, **k)
	return urlopen


def test_engine_older_version(tmp_path):
	from monitoreo import engine
	old = tmp_path / 'v0.1.0'
	old.mkdir()
	(old / 'ollama').write_text('')
	(tmp_path / f'{engine.OLLAMA}.tmp').mkdir()  # an installation that did not end
	assert engine.Engine(str(tmp_path)).installed() == str(old / 'ollama')  # used until Ollama is installed again
	assert engine.Engine(str(tmp_path / 'nothing')).installed() is None


def test_downloads_and_exports(monkeypatch):
	tools = assistant.model_tools(TOOLS + [
		{'name': n, 'description': n, 'inputSchema': {'type': 'object', 'properties': {
			'region': {'type': 'object'}, 'resolution': {'type': 'number'}, 'crs': {'type': 'string'},
			'operation': {'type': 'string'}}}}
		for n in ('download_image', 'export_image_to_drive', 'task_status', 'publish_report')])
	names = [t['function']['name'] for t in tools]
	assert 'download_image' in names and 'export_image_to_drive' in names and 'publish_report' not in names
	props = next(t for t in tools if t['function']['name'] == 'download_image')['function']['parameters']['properties']
	assert 'resolution' in props and 'crs' not in props
	tif = {'file': '/tmp/NDVI.tif', 'grid': {'crs': 'EPSG:32630', 'resolution': 20, 'width': 1200, 'height': 800},
	       'resolution': 20, 'native_resolution': 10, 'images': 12, 'name': 'NDVI', 'unit': '[unitless]',
	       'min': 0.12, 'max': 0.63, 'palette': ['ffffff', '00aa00']}
	facts = dict(report.item_facts('download_image', ARGS, tif))
	assert facts['GeoTIFF'] == '1.200 × 800 píxeles de 20 m (los datos, de 10 m), en EPSG:32630'
	assert facts['Valores (percentiles 5 y 95)'] == '0,12 a 0,63' and facts['Imágenes'] == '12'
	assert report.item_title('download_image', ARGS) == 'Mapa de NDVI (Sentinel-2), 2021 (GeoTIFF)'
	assert assistant.task_text('task_status', json.dumps({'state': 'RUNNING', 'progress': 0.42})) == \
	       'Exportación a Google Drive: en marcha (42 %).'
	assert 'carpeta MonitorEO' in assistant.task_text('export_image_to_drive', json.dumps(
		{'operation': 'projects/p/operations/X', 'file': 'NDVI.tif', 'folder': 'MonitorEO'}))
	recipe = {'period': ['2018-01-01', '2021-12-31'], 'variables': [{'index': 'NDVI', 'sensor': 'Sentinel-2',
	                                                                 'metric': ['p95', 'p5']}]}
	plan = {'grids': {'study': {'width': 500, 'height': 400, 'resolution': 10, 'mb_per_variable': 0.76}},
	        'files': [{'file': '01_NDVI_p95.tif', 'pixel_filters': ['clouds', 'snow'], 'images': 310}]}
	facts = dict(report.item_facts('download_variables', {'recipe': recipe, 'area': {'bbox': [0, 0, 1, 1]},
	                                                       'name': 'modelo', 'dry_run': True}, plan))
	assert facts['Variables'] == 'NDVI (Sentinel-2): percentil 95, percentil 5' and 'solo el plan' in facts['Descarga']
	assert report.item_table('download_variables', plan)[1] == [['01_NDVI_p95.tif', '310', 'nubes, nieve']]


def test_geotiff_preview(tmp_path, monkeypatch):
	pytest.importorskip('osgeo')
	pytest.importorskip('matplotlib')
	import numpy as np
	from osgeo import gdal, osr
	gdal.UseExceptions()
	path = str(tmp_path / 'ndvi.tif')
	ds = gdal.GetDriverByName('GTiff').Create(path, 40, 30, 1, gdal.GDT_Float32)
	srs = osr.SpatialReference()
	srs.ImportFromEPSG(32630)
	ds.SetProjection(srs.ExportToWkt())
	ds.SetGeoTransform([450000, 10, 0, 4090000, 0, -10])
	band = ds.GetRasterBand(1)
	band.SetNoDataValue(-9999)
	a = np.linspace(0, 1, 1200, dtype='float32').reshape(30, 40)
	a[:5] = -9999
	band.WriteArray(a)
	ds = None
	assert report.tif_preview(path, ['ffffff', '00aa00'], 0.1, 0.9).startswith('data:image/png;base64,')
	assert report.tif_preview(str(tmp_path / 'nothing.tif')) is None
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)

	class Downloads(FakeAssistant):
		async def call(self, name, args):
			return None, [json.dumps({'file': path, 'palette': ['ffffff', '00aa00'], 'min': 0.1, 'max': 0.9,
			                          'grid': {'crs': 'EPSG:32630', 'width': 40, 'height': 30}, 'resolution': 10})], []

	a = Downloads({**assistant.DEFAULTS, 'project': 'p'})
	a.tools = assistant.model_tools(TOOLS + [{'name': 'download_image', 'description': '', 'inputSchema': {
		'type': 'object', 'properties': {'region': {'type': 'object'}, 'variable': {'type': 'string'}}}}])

	async def run():
		return [e async for e in a.run_tool({'name': 'download_image', 'arguments': {
			'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'variable': 'NDVI'}})]

	result = next(e for e in asyncio.run(run()) if e['type'] == 'result')
	assert result['image'].startswith('data:image/png') and result['files'][0]['name'] == 'ndvi.tif'
	assert 'Hecho:' in a.messages[-1]['content'] and '0.9' not in a.messages[-1]['content']


def test_default_model():
	assert [m['name'] for m in assistant.RECOMMENDED][0] == assistant.DEFAULTS['model'] == 'qwen3:8b'
	assert assistant.default_model('qwen3:8b', ['qwen3:8b', 'gpt-oss:20b']) == 'qwen3:8b'  # the chosen one, installed
	assert assistant.default_model('qwen3:8b', ['gpt-oss:20b', 'qwen3:4b']) == 'qwen3:4b'  # installed, in their order
	assert assistant.default_model('qwen3:8b', ['nomic-embed-text']) == 'qwen3:8b'  # not one without tools
	assert assistant.default_model('qwen3:8b', []) == 'qwen3:8b'


WIKI_PAGES = {
	'Conceptos': '# Conceptos\n\nIntro.\n\n## Variables\n\n| `NDVI` | Índice de vegetación de diferencia normalizada | '
	             'Sentinel-2 (10 m) |\n\n## Filtros por píxel\n\nSe quitan las nubes y la nieve.\n',
	'Python': '# Python\n\n## Serie temporal\n\n```python\nmo.time_series(variable="NDVI")  # NDVI NDVI NDVI\n```\n',
	'Home': '# Inicio\n\n## Cómo citar\n\nCítalo con su DOI: [Zenodo](https://doi.org/x).\n<img src="images/a.png">\n',
}


def test_manual(tmp_path):
	from monitoreo import manual
	for name, text in WIKI_PAGES.items():
		(tmp_path / f'{name}.md').write_text(text, encoding='utf-8')
	(tmp_path / '_Sidebar.md').write_text('[Inicio](Home)', encoding='utf-8')
	secs = manual.sections(str(tmp_path))
	assert {(s['page'], s['title']) for s in secs} >= {('Conceptos', 'Variables'), ('Inicio', 'Cómo citar')}
	cite = next(s for s in secs if s['title'] == 'Cómo citar')
	assert cite['url'].endswith('/wiki/Home#cómo-citar') and cite['text'] == 'Cítalo con su DOI: Zenodo.'
	assert manual.search('¿Qué es el NDVI?', folder=str(tmp_path))[0]['title'] == 'Variables'  # not the code
	assert manual.search('¿cómo cito MonitorEO?', folder=str(tmp_path))[0]['title'] == 'Cómo citar'
	assert manual.search('filtro de nubes', folder=str(tmp_path))[0]['title'] == 'Filtros por píxel'
	assert manual.search('xyz', folder=str(tmp_path)) == []
	assert manual.words('Imágenes, citar y cito') == ['imagen', 'cit', 'cit']


def test_manual_tool(monkeypatch):
	found = [{'page': 'Conceptos', 'title': 'Variables', 'url': 'https://w/Conceptos#variables', 'text': 'NDVI: ...'}]
	monkeypatch.setattr(assistant, '_search_manual', lambda q: found if 'NDVI' in q else [])
	a = FakeAssistant({**assistant.DEFAULTS})
	a.tools = assistant.model_tools(TOOLS) + [assistant.MANUAL_TOOL]

	async def run(question):
		return [e async for e in a.run_tool({'name': 'manual', 'arguments': {'pregunta': question}})]

	events = asyncio.run(run('¿Qué es el NDVI?'))
	assert events[-1] == {'type': 'sources', 'sources': [{'title': 'Conceptos › Variables',
	                                                     'url': 'https://w/Conceptos#variables'}]}
	assert 'NDVI: ...' in a.messages[-1]['content'] and 'https://w/Conceptos#variables' in a.messages[-1]['content']
	asyncio.run(run('otra cosa'))
	assert 'El manual no tiene nada' in a.messages[-1]['content']
	assert 'App-de-Earth-Engine' in assistant.instructions() and 'manual' in assistant.instructions()


def test_other_tool():
	assert assistant.other_tool('Quiero el NDVI de 30 parques cada mes de forma automática')[0].startswith('el paquete de Python')
	assert assistant.other_tool('¿Lo puedo hacer en R?')[0] == 'el paquete de R'
	assert assistant.other_tool('quiero editar mi capa')[0] == 'el plugin de QGIS'
	assert assistant.other_tool('Serie del NDVI de cada mes de 2024 en Doñana') is None
	assert assistant.other_tool('¿Qué es el NDVI?') is None


def test_check_update(monkeypatch):
	from monitoreo import update
	monkeypatch.setattr(update, 'local_copy', lambda: None)
	monkeypatch.setattr(update, 'installed', lambda: ('0.3.11', 'a' * 40, None))
	monkeypatch.setattr(update, 'latest', lambda: 'b' * 40)
	assert assistant.check_update() == {'available': True, 'current': 'aaaaaaa', 'latest': 'bbbbbbb'}
	monkeypatch.setattr(update, 'latest', lambda: 'a' * 40)
	assert assistant.check_update()['available'] is False
	monkeypatch.setattr(update, 'latest', lambda: (_ for _ in ()).throw(OSError('offline')))
	assert assistant.check_update() is None
	monkeypatch.setattr(update, 'local_copy', lambda: '/src/monitoreo')
	assert assistant.check_update() is None  # a clone is not updated


def test_events_of_the_conversation(monkeypatch):
	answers = iter([{'content': 'Primera respuesta.'}, {'content': 'Segunda.'}])
	monkeypatch.setattr(assistant, 'chat_model', lambda *a: next(answers))

	async def run():
		a = FakeAssistant({**assistant.DEFAULTS, 'ollama': 'http://127.0.0.1:1'})
		a.tools = assistant.model_tools(TOOLS)

		async def until_done(since=0):
			got = []
			async for e in a.follow(since, ping=0.05):
				got.append(e)
				if e['type'] == 'done':
					return got

		a.start('Hola')
		with pytest.raises(ValueError, match='espera'):
			a.start('Otra')  # one message at a time
		first = await until_done()
		later = await until_done()  # a page opened afterwards gets the whole conversation again
		a.start('Otra pregunta')
		second = await until_done(first[-1]['seq'] + 1)  # and one that follows, only what is new
		a.new_conversation()
		after_reset = [e async for e in _take(a.follow(second[-1]['seq'] + 1), 1)]
		return first, later, second, after_reset, a

	first, later, second, after_reset, a = asyncio.run(run())
	assert [e['type'] for e in first if e['type'] != 'status'] == ['user', 'assistant', 'done']
	assert later == first and [e['seq'] for e in first] == list(range(len(first)))
	assert second[0] == {'type': 'user', 'text': 'Otra pregunta', 'seq': len(first)}
	assert after_reset[0]['type'] == 'reset' and not a.messages and not a.running()


async def _take(events, n):
	async for e in events:
		yield e
		n -= 1
		if not n:
			return
