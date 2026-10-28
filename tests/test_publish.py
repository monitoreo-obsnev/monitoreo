"""Tests of the publication of results in the static viewer (monitoreo.publish), without Earth Engine: report.json,
catalog.json, the COGs, the log of the MCP server and the local server."""

import csv
import functools
import http.client
import http.server
import inspect
import json
import os
import re
import threading

import pytest

from monitoreo import publish, services

gdal = pytest.importorskip('osgeo.gdal')
gdal.UseExceptions()

TREND_CALL = {'tool': 'download_trend', 'args': {'region': {'wdpa_id': 389011}, 'variable': 'EVI', 'sensor': 'Modis',
                                                  'start': '2001-01-01', 'end': '2024-12-31', 'step': 'annual'}}
SERIES_ARGS = {'region': {'wdpa_id': 389011}, 'variable': 'EVI', 'sensor': 'Modis', 'start': '2001-01-01',
               'end': '2024-12-31', 'step': 'annual'}


def _tif(path, bands, values, nodata=-9999.0):
	"""A GeoTIFF of 20 x 15 pixels of 250 m in UTM 30N with BANDS, the first rows NoData."""
	import numpy as np
	ds = gdal.GetDriverByName('GTiff').Create(str(path), 20, 15, len(bands), gdal.GDT_Float32)
	ds.SetGeoTransform([450000, 250, 0, 4110000, 0, -250])
	ds.SetProjection('EPSG:32630')
	for i, (name, v) in enumerate(zip(bands, values)):
		b = ds.GetRasterBand(i + 1)
		a = np.full((15, 20), v, dtype='float32') + np.linspace(0, abs(v) or 1, 300, dtype='float32').reshape(15, 20) * 0.1
		a[:2] = nodata
		b.WriteArray(a)
		b.SetNoDataValue(nodata)
		b.SetDescription(name)
	ds = None
	return str(path)


def _csv(path, rows):
	with open(path, 'w', newline='', encoding='utf-8') as f:
		w = csv.DictWriter(f, fieldnames=list(rows[0]))
		w.writeheader()
		w.writerows(rows)
	return str(path)


@pytest.fixture
def outputs(tmp_path):
	"""The outputs of an analysis as the MCP server writes them (in a folder that was moved: their paths in the
	answers do not exist, so they are found by name in `files`), and its answers saved with their calls."""
	out = tmp_path / 'mcp_out'
	out.mkdir()
	gone = '/tmp/does-not-exist/'
	_tif(out / 'trend_EVI_Modis_annual_None_2001-01-01_2024-12-31_20261028-233108.tif',
	     ['slope', 'tau', 'z', 'p_value', 'intercept', 'n'], [0.001, 0.3, 2.0, 0.01, 0.2, 24])
	_csv(out / 'trend_EVI_Modis_annual_2001-01-01_2024-12-31_20261028-233025.csv', [
		{'region': 'Sierra Nevada', 'key': 'all', 'label': 'año', 'n': 24, 'tau': 0.3, 'z': 2.0, 'p_value': 0.01,
		 'significant': True, 'slope': 0.001, 'intercept': 0.2, 'first_year': 2001, 'last_year': 2024,
		 'variable': 'EVI', 'sensor': 'Modis', 'step': 'annual', 'unit': '[unitless]'}])
	_csv(out / 'EVI_Modis_annual_mean_2001-01-01_2024-12-31_20261028-233410.csv', [
		{'region': 'Sierra Nevada', 'date': f'{y}-01-01', 'value': 0.2 + (y - 2001) * 0.001, 'n_pixels': 100,
		 'n_images': 23} for y in range(2001, 2025)])
	data = tmp_path / 'data'
	data.mkdir()
	answers = {
		'map': {'call': dict(TREND_CALL, id='map'), 'is_error': False, 'text': [{
			'file': gone + 'trend_EVI_Modis_annual_None_2001-01-01_2024-12-31_20261028-233108.tif', 'min': -0.002,
			'max': 0.002, 'palette': ['a50026', 'ffffbf', '006837'], 'unit': '[unitless] / year',
			'bands': ['slope', 'tau', 'z', 'p_value', 'intercept', 'n']}]},
		'trend': {'call': {'id': 'trend', 'tool': 'trend_table', 'args': SERIES_ARGS}, 'is_error': False, 'text': [{
			'title': 'EVI Modis', 'unit': '[unitless]',
			'csv': gone + 'trend_EVI_Modis_annual_2001-01-01_2024-12-31_20261028-233025.csv'}]},
		'series': {'call': {'id': 'series', 'tool': 'time_series', 'args': SERIES_ARGS}, 'is_error': False, 'text': [{
			'title': 'EVI Modis', 'unit': '[unitless]', 'regions': ['Sierra Nevada'],
			'csv': gone + 'EVI_Modis_annual_mean_2001-01-01_2024-12-31_20261028-233410.csv'}]},
	}
	for k, v in answers.items():
		(data / f'{k}.json').write_text(json.dumps(v), encoding='utf-8')
	(tmp_path / 'informe.pdf').write_bytes(b'%PDF-1.4 test')
	return tmp_path


def _spec(**kw):
	spec = {
		'id': '2026-10-sierra-nevada-verdor', 'title': '¿Ha cambiado el verdor desde 2001?',
		'summary': 'El EVI sube en el 30 % del parque.', 'answer': 'Primer párrafo.\n\nSegundo párrafo.',
		'method': 'Mann-Kendall y Sen.', 'sections': [{'title': 'Frente a REMOTE', 'text': 'Texto.'}],
		'region': {'name': 'Sierra Nevada', 'designation': 'Parque Nacional'}, 'published': '2026-10-29',
		'authors': ['OBSNEV'], 'files': 'mcp_out', 'downloads': [{'path': 'informe.pdf', 'title': 'Informe (PDF)'}],
		'results': [{'answer': 'data/map.json', 'palette': ['8c510a', 'f2efe6', '01665e']},
		            {'answer': 'data/series.json', 'title': 'EVI medio anual'}, {'answer': 'data/trend.json'}],
	}
	spec.update(kw)
	return spec


def test_report(outputs):
	site = outputs / 'site'
	r = publish.publish(_spec(), site, outputs, log='')
	folder = site / 'reports' / r['id']
	assert json.loads((folder / 'report.json').read_text(encoding='utf-8')) == r
	assert publish.check_report(r, str(folder)) == []
	assert r['region']['wdpa_id'] == 389011 and r['region']['name'] == 'Sierra Nevada'  # the WDPA ID of the calls
	w, s, e, n = r['region']['bounds']
	assert -3.6 < w < e < -3.4 and 37.0 < s < n < 37.2
	assert r['variables'] == [{'variable': 'EVI', 'sensor': 'MODIS', 'name': 'Índice de Vegetación Mejorado', 'unit': ''}]
	assert [a['id'] for a in r['analyses']] == ['trend', 'series'] and r['analyses'][0]['name'] == 'Tendencia'
	assert r['periods'] == [['2001-01-01', '2024-12-31']] and r['years'] == [2001, 2024]
	assert r['answer'] == 'Primer párrafo.\n\nSegundo párrafo.' and r['software']['monitoreo']

	m, series, trend = r['results']
	assert (m['kind'], series['chart'], trend['chart']) == ('map', 'series', 'trends')
	assert m['cog'] == 'maps/trend_EVI_Modis_annual_None_2001-01-01_2024-12-31.tif'  # without the time of the file
	assert 'LAYOUT=COG' in gdal.Info(str(folder / m['cog']))
	assert m['crs'] == 'EPSG:32630' and m['proj4'].startswith('+proj=utm +zone=30') and m['size'] == [20, 15]
	assert m['extent'] == [450000.0, 4106250.0, 455000.0, 4110000.0] and m['resolution'] == 250
	assert m['band'] == 'slope' and m['significance'] == {'band': 'p_value', 'alpha': 0.05}
	bands = {b['name']: b for b in m['bands']}
	assert list(bands) == ['slope', 'tau', 'z', 'p_value', 'intercept', 'n']
	assert bands['slope']['legend'] == {'type': 'continuous', 'min': -0.002, 'max': 0.002,
	                                    'palette': ['#8c510a', '#f2efe6', '#01665e']}  # range of the result, palette of the report
	assert bands['slope']['unit'] == 'por año' and bands['n']['unit'] == 'años'
	assert (bands['tau']['legend']['min'], bands['tau']['legend']['max']) == (-1.0, 1.0)
	assert bands['p_value']['stats']['count'] == 20 * 13  # the NoData rows left out
	assert m['call']['tool'] == 'download_trend' and m['call']['args'] == TREND_CALL['args']
	assert m['call']['python'].startswith('mo.download_trend(region={"wdpa_id": 389011}, variable="EVI"')

	assert series['title'] == 'EVI medio anual' and series['csv'].startswith('data/') and series['step'] == 'annual'
	sen = series['sen']  # the Sen line of the trend of the same series
	assert len(sen) == 1 and sen[0]['trend'] == trend['id'] and sen[0]['origin'] == 2001
	assert sen[0]['slope'] == 0.001 and sen[0]['significant'] is True and sen[0]['period'] == '2001-2024'
	assert trend['title'] == 'Tendencia anual de EVI (MODIS), 2001-2024' and trend['slope_unit'] == 'por año'

	paths = [f['path'] for f in r['files']]
	assert paths == [m['cog'], series['csv'], trend['csv'], 'files/informe.pdf']
	assert all(f['bytes'] == os.path.getsize(folder / f['path']) for f in r['files'])
	assert r['thumbnail'] == 'thumbnail.png' and (folder / 'thumbnail.png').read_bytes()[:4] == b'\x89PNG'


def test_catalog(outputs):
	site = outputs / 'site'
	publish.publish(_spec(), site, outputs, log='')
	publish.publish(_spec(id='2026-11-teide', title='¿Qué quemó el incendio?', published='2026-11-02',
	                      region={'name': 'Teide'}, results=[{'answer': 'data/series.json'}], downloads=None), site,
	                outputs, log='')
	cat = json.loads((site / 'catalog.json').read_text(encoding='utf-8'))
	assert publish.check_catalog(cat, str(site)) == [] and publish.check_site(site) == []
	assert [r['id'] for r in cat['reports']] == ['2026-11-teide', '2026-10-sierra-nevada-verdor']  # newest first
	sn = cat['reports'][1]
	assert sn['path'] == 'reports/2026-10-sierra-nevada-verdor/report.json' and (sn['maps'], sn['charts']) == (1, 2)
	assert sn['thumbnail'] == 'reports/2026-10-sierra-nevada-verdor/thumbnail.png'
	assert sn['summary'] == 'El EVI sube en el 30 % del parque.' and sn['years'] == [2001, 2024]
	assert cat['reports'][0]['thumbnail'] is None  # no map and no chart of a tool
	assert 'PID2023-151939OB-I00' in cat['about']['acknowledgements'] and cat['analyses']['trend'] == 'Tendencia'
	assert all((site / p).is_file() for p in cat['about']['logos'])
	for page in ('index.html', 'report.html', 'assets/viewer.css', 'assets/common.js', 'assets/catalog.js',
	             'assets/report.js', 'assets/map.js', 'assets/charts.js', '.nojekyll'):
		assert (site / page).is_file()

	# publishing again replaces the report; removing it takes it out of the catalogue
	publish.publish(_spec(summary='Otro resumen.'), site, outputs, log='')
	cat = json.loads((site / 'catalog.json').read_text(encoding='utf-8'))
	assert len(cat['reports']) == 2 and cat['reports'][1]['summary'] == 'Otro resumen.'
	assert not [p for p in os.listdir(site / 'reports') if p.startswith('.')]
	publish.remove('2026-11-teide', site)
	assert [r['id'] for r in publish.update_catalog(site)['reports']] == ['2026-10-sierra-nevada-verdor']
	with pytest.raises(ValueError):
		publish.remove('../site', site)


def test_problems(outputs):
	site = outputs / 'site'
	with pytest.raises(ValueError, match='title'):
		publish.publish(_spec(title=''), site, outputs, log='')
	with pytest.raises(ValueError, match='lowercase'):
		publish.publish(_spec(id='Sierra Nevada'), site, outputs, log='')
	with pytest.raises(FileNotFoundError):
		publish.publish(_spec(files=None), site, outputs, log='')  # the files of the answers are not found
	assert not (site / 'reports' / '2026-10-sierra-nevada-verdor').exists()  # nothing half published
	r = publish.publish(_spec(), site, outputs, log='')
	folder = str(site / 'reports' / r['id'])
	bad = json.loads(json.dumps(r))
	bad['results'][0]['bands'][0]['legend']['palette'] = ['red']
	bad['results'][1]['csv'] = '/etc/passwd'
	bad['files'][0]['path'] = '../../x.tif'
	bad['published'] = '29/10/2026'
	problems = ' | '.join(publish.check_report(bad, folder))
	for text in ('palette of 2 or more colours', 'its CSV is not in files', 'a relative path', 'published is a date'):
		assert text in problems
	os.remove(os.path.join(folder, r['results'][1]['csv']))
	assert any('does not exist' in p for p in publish.check_report(r, folder))
	assert any('does not exist' in p for p in publish.check_site(site))


def test_specs_and_services(outputs):
	(outputs / 'publicar.yaml').write_text(
		'published: 2026-10-29\nauthors: [OBSNEV]\nfiles: mcp_out\n'
		'reports:\n'
		'  - {id: uno, title: Uno, summary: S, region: {name: Sierra Nevada}, results: [{answer: data/series.json}]}\n'
		'  - {id: dos, title: Dos, summary: S, published: 2026-11-01, region: {name: Teide},\n'
		'     results: [{answer: data/map.json}]}\n', encoding='utf-8')
	specs = publish.read_specs(str(outputs / 'publicar.yaml'))
	assert [s['id'] for s, _ in specs] == ['uno', 'dos'] and specs[0][1] == str(outputs)
	assert str(specs[0][0]['published']) == '2026-10-29' and str(specs[1][0]['published']) == '2026-11-01'
	res = services.publish_report(str(outputs / 'publicar.yaml'), str(outputs / 'site'), log='')
	assert [r['id'] for r in res['reports']] == ['uno', 'dos'] and res['reports'][1]['page'] == 'report.html?id=dos'
	assert services.check_site(str(outputs / 'site')) == []
	assert services.remove_report('uno', str(outputs / 'site'))['removed'] == 'uno'


def test_calls_log(outputs, monkeypatch):
	"""publish_report of the MCP server gives the files written by the other tools: their calls come from its log."""
	out = outputs / 'mcp_out'
	tif = str(out / 'trend_EVI_Modis_annual_None_2001-01-01_2024-12-31_20261028-233108.tif')
	answer = json.loads((outputs / 'data' / 'map.json').read_text(encoding='utf-8'))['text'][0]
	publish.log_call('download_trend', TREND_CALL['args'], dict(answer, file=tif), str(out))
	publish.log_call('time_series', {'region': {'wdpa_id': 1}}, {'csv': str(out / 'other.csv')}, str(out))
	log = publish.calls_log(str(out))
	assert log == str(out / 'calls.jsonl') and len(open(log).readlines()) == 2
	assert publish._logged_call(tif, log)['tool'] == 'download_trend'
	assert publish._logged_call('/elsewhere/unknown.tif', log) is None
	r = publish.publish({'id': 'mcp', 'title': 'Desde el MCP', 'summary': 'S', 'results': [tif]}, outputs / 'site',
	                    outputs, log)
	assert r['results'][0]['call']['tool'] == 'download_trend' and r['region']['wdpa_id'] == 389011
	assert r['results'][0]['bands'][0]['legend']['min'] == -0.002  # the range of the logged result
	# a file without a logged call is published without its call
	r = publish.publish({'id': 'sin-llamada', 'title': 'Sin llamada', 'summary': 'S', 'region': 'Zona',
	                     'results': [str(out / 'EVI_Modis_annual_mean_2001-01-01_2024-12-31_20261028-233410.csv')]},
	                    outputs / 'site', outputs, log)
	assert r['results'][0]['call'] is None and r['results'][0]['chart'] == 'series' and r['region'] == {'name': 'Zona'}


def test_mcp_log(tmp_path, monkeypatch):
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))

	def download_trend(region, variable, sensor, start, end, step='annual', part=None):
		return json.dumps({'file': str(tmp_path / 'x.tif'), 'min': 0})

	sig = inspect.signature(download_trend)
	out = download_trend({'wdpa_id': 1}, 'EVI', 'Modis', '2001-01-01', '2024-12-31')
	mcp_server._log('download_trend', sig, ({'wdpa_id': 1}, 'EVI', 'Modis', '2001-01-01', '2024-12-31'), {}, out)
	mcp_server._log('list_variables', sig, (), {}, '[{"ref": 1}]')  # no file: not logged
	lines = [json.loads(x) for x in open(tmp_path / 'calls.jsonl')]
	assert len(lines) == 1 and lines[0]['tool'] == 'download_trend'
	assert lines[0]['args'] == {'region': {'wdpa_id': 1}, 'variable': 'EVI', 'sensor': 'Modis', 'start': '2001-01-01',
	                            'end': '2024-12-31'}
	assert 'publish_report' in inspect.getsource(mcp_server)


def test_texts():
	assert publish.period_text('2001-01-01', '2024-12-31') == '2001-2024'
	assert publish.period_text('2023-01-01', '2023-12-31') == '2023'
	assert publish.period_text('2023-05-15', '2023-08-14') == '15 may 2023 - 14 ago 2023'
	assert publish.season_text(['06-01', '08-31']) == ' (de junio a agosto)'
	assert publish.season_text(['12-01', '02-28']) == ' (de diciembre a febrero)'
	assert publish.season_text(['05-15', '08-14']) == ' (del 15 de mayo al 14 de agosto)'
	assert publish.unit_text('[ºC]') == '°C' and publish.unit_text('[unitless]') == ''
	assert publish.unit_text('[ºC]', per_year=True) == '°C/año' and publish.unit_text('', per_year=True) == 'por año'
	assert publish.slug('Aigüestortes i Estany de Sant Maurici') == 'aiguestortes-i-estany-de-sant-maurici'
	assert publish.python_call('trend_table', {'region': {'wdpa_id': 1}, 'quality': {'snow': False}, 'alpha': None}) \
		== 'mo.trend_table(region={"wdpa_id": 1}, quality={"snow": False}, alpha=None)'
	args = {'variable': 'NDSI', 'sensor': 'Modis', 'start': '2001-01-01', 'end': '2005-12-31',
	        'other_start': '2020-01-01', 'other_end': '2024-12-31', 'season': ['03-01', '05-31']}
	assert publish.default_title('download_comparison', args) == \
		'Mapa de la diferencia de NDSI (MODIS): 2020-2024 menos 2001-2005 (de marzo a mayo)'
	assert publish.default_title('compare_series', args).startswith('NDSI (MODIS) por meses: 2020-2024 frente a 2001-2005')


def test_server(tmp_path):
	"""The local server answers range requests, as GitHub Pages: the browser reads the COGs by parts."""
	(tmp_path / 'a.tif').write_bytes(bytes(range(100)))
	httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(publish._Handler, directory=str(tmp_path)))
	threading.Thread(target=httpd.serve_forever, daemon=True).start()
	try:
		def get(headers):
			c = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=10)
			c.request('GET', '/a.tif', headers=headers)
			r = c.getresponse()
			return r.status, dict(r.getheaders()), r.read()

		status, h, body = get({'Range': 'bytes=10-19'})
		assert status == 206 and body == bytes(range(10, 20)) and h['Content-Range'] == 'bytes 10-19/100'
		assert h['Content-Type'] == 'image/tiff' and h['Accept-Ranges'] == 'bytes'
		assert get({'Range': 'bytes=-5'})[2] == bytes(range(95, 100))
		assert get({'Range': 'bytes=90-'})[2] == bytes(range(90, 100))
		assert get({'Range': 'bytes=200-300'})[0] == 416
		assert get({})[0] == 200 and len(get({})[2]) == 100
	finally:
		httpd.shutdown()


def test_viewer_files():
	"""The pages of the viewer load their scripts from the package or from a CDN at exact versions, with SRI."""
	html = ''.join(open(os.path.join(publish.VIEWER, p), encoding='utf-8').read() for p in ('index.html', 'report.html'))
	for src in re.findall(r'(?:src|href)="([^"]+\.(?:js|css))"', html):
		if src.startswith('http'):
			assert re.match(r'https://cdn\.jsdelivr\.net/npm/[a-z0-9-]+@\d+\.\d+\.\d+/', src), src
			assert re.search(re.escape(src) + r'" integrity="sha384-', html), src
		else:
			assert os.path.isfile(os.path.join(publish.VIEWER, src)), src
	assert '<html lang="es">' in html
