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

from monitoreo import publish, services, wiki

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
		{'region': 'Sierra Nevada', 'key': 'all', 'label': 'year', 'n': 24, 'tau': 0.3, 'z': 2.0, 'p_value': 0.01,
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


def test_the_sen_lines_of_combined_bands(tmp_path):
	"""The viewer draws on an annual series the Sen line of a trend of the same data: with several bands of Earth
	Engine combined, only of the same bands and band_reducer (the mean of two bands is not their sum)."""
	trend = [{'region': 'r', 'slope': 1.5, 'intercept': 100, 'p_value': 0.01, 'significant': 'True', 'first_year': 2001,
	          'last_year': 2020}]
	_csv(tmp_path / 'sum.csv', trend)
	_csv(tmp_path / 'mean.csv', trend)
	args = {'region': {'wdpa_id': 1}, 'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': ['aet', 'def'],
	        'band_reducer': 'sum', 'band_scale': 0.1, 'unit': 'mm', 'metric': 'sum', 'step': 'annual',
	        'start': '2001-01-01', 'end': '2020-12-31'}
	results = [{'id': 's', 'chart': 'series', 'call': {'args': args}},
	           {'id': 't1', 'chart': 'trends', 'csv': 'sum.csv', 'call': {'args': args}},
	           {'id': 't2', 'chart': 'trends', 'csv': 'mean.csv', 'call': {'args': dict(args, band_reducer='mean')}}]
	publish._link_trends(results, str(tmp_path))
	assert [x['trend'] for x in results[0]['sen']] == ['t1'] and 'band_reducer' in publish.SAME_SERIES
	assert publish.default_title('time_series', args).startswith(
		'Annual time series of IDAHO_EPSCOR/TERRACLIMATE sum of aet, def')


def test_report(outputs):
	site = outputs / 'site'
	r = publish.publish(_spec(), site, outputs, log='')
	folder = site / 'reports' / r['id']
	assert json.loads((folder / 'report.json').read_text(encoding='utf-8')) == r
	assert publish.check_report(r, str(folder)) == []
	assert r['region']['wdpa_id'] == 389011 and r['region']['name'] == 'Sierra Nevada'  # the WDPA ID of the calls
	w, s, e, n = r['region']['bounds']
	assert -3.6 < w < e < -3.4 and 37.0 < s < n < 37.2
	assert r['variables'] == [{'variable': 'EVI', 'sensor': 'MODIS', 'name': 'Enhanced Vegetation Index', 'unit': ''}]
	assert [a['id'] for a in r['analyses']] == ['trend', 'series'] and r['analyses'][0]['name'] == 'Trend'
	assert r['periods'] == [['2001-01-01', '2024-12-31']] and r['years'] == [2001, 2024]
	assert r['answer'] == 'Primer párrafo.\n\nSegundo párrafo.' and r['software']['monitoreo']
	assert r['license']['id'] == 'CC-BY-4.0' and r['license']['url'] == 'https://creativecommons.org/licenses/by/4.0/deed.en'
	assert r['license']['text'].startswith('they can be copied, redistributed and adapted for any purpose')

	m, series, trend = r['results']
	assert (m['kind'], series['chart'], trend['chart']) == ('map', 'series', 'trends')
	# what the variable is: its section of the wiki, under each result (monitoreo.wiki)
	assert all(x['manual'] == [{'variable': 'EVI', 'title': 'EVI: Enhanced Vegetation Index',
	                            'url': wiki.variable_section('EVI')['url'],
	                            'url_es': wiki.variable_section('EVI')['url_es']}] for x in (m, series, trend))
	assert m['cog'] == 'maps/trend_EVI_Modis_annual_None_2001-01-01_2024-12-31.tif'  # without the time of the file
	assert 'LAYOUT=COG' in gdal.Info(str(folder / m['cog']))
	assert m['crs'] == 'EPSG:32630' and m['proj4'].startswith('+proj=utm +zone=30') and m['size'] == [20, 15]
	assert m['extent'] == [450000.0, 4106250.0, 455000.0, 4110000.0] and m['resolution'] == 250
	assert m['band'] == 'slope' and m['significance'] == {'band': 'p_value', 'alpha': 0.05}
	bands = {b['name']: b for b in m['bands']}
	assert list(bands) == ['slope', 'tau', 'z', 'p_value', 'intercept', 'n']
	assert bands['slope']['legend'] == {'type': 'continuous', 'min': -0.002, 'max': 0.002,
	                                    'palette': ['#8c510a', '#f2efe6', '#01665e']}  # range of the result, palette of the report
	assert bands['slope']['unit'] == 'per year' and bands['n']['unit'] == 'years'
	assert (bands['slope']['label'], bands['p_value']['label']) == ("Sen's slope", 'Mann-Kendall p-value')
	assert (bands['tau']['legend']['min'], bands['tau']['legend']['max']) == (-1.0, 1.0)
	assert bands['p_value']['stats']['count'] == 20 * 13  # the NoData rows left out
	assert m['call']['tool'] == 'download_trend' and m['call']['args'] == TREND_CALL['args']
	assert m['call']['python'].startswith('mo.download_trend(region={"wdpa_id": 389011}, variable="EVI"')

	assert series['title'] == 'EVI medio anual' and series['csv'].startswith('data/') and series['step'] == 'annual'
	sen = series['sen']  # the Sen line of the trend of the same series
	assert len(sen) == 1 and sen[0]['trend'] == trend['id'] and sen[0]['origin'] == 2001
	assert sen[0]['slope'] == 0.001 and sen[0]['significant'] is True and sen[0]['period'] == '2001-2024'
	assert trend['title'] == 'Annual trend of EVI (MODIS), 2001-2024' and trend['slope_unit'] == 'per year'
	assert m['title'] == 'Map of the annual trend of EVI (MODIS), 2001-2024'

	paths = [f['path'] for f in r['files']]
	assert paths == [m['cog'], series['csv'], trend['csv'], 'files/informe.pdf']
	assert [f['title'] for f in r['files']][:3] == [f'Map (GeoTIFF): {m["title"]}', 'Table (CSV): EVI medio anual',
	                                                f'Table (CSV): {trend["title"]}']
	assert all(f['bytes'] == os.path.getsize(folder / f['path']) for f in r['files'])
	assert r['thumbnail'] == 'thumbnail.png' and (folder / 'thumbnail.png').read_bytes()[:4] == b'\x89PNG'
	# the references of the results, numbered, and the numbers of those of each result
	cites = [x['citation'] for x in r['references']]
	assert cites == sorted(cites, key=str.lower) and all(x['url'] for x in r['references'])
	for x in r['results']:
		assert x['references'] and all(1 <= n <= len(cites) for n in x['references'])
	mann = next(i + 1 for i, c in enumerate(cites) if c.startswith('Mann, H. B.'))
	assert mann in m['references'] and mann in trend['references'] and mann not in series['references']
	assert any(c.startswith('Didan, K. (2021). MODIS/Terra Vegetation Indices') for c in cites)
	assert any(c.startswith('UNEP-WCMC & IUCN (2026)') and 'October 2026' in c for c in cites)  # date of publication


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
	assert 'PID2023-151939OB-I00' in cat['about']['acknowledgements'] and cat['analyses']['trend'] == 'Trend'
	assert cat['about']['description'].startswith('MonitorEO-OBSNEV is an open monitoring tool')
	assert cat['about']['doi'] in cat['about']['citation']
	assert cat['license']['name'] == sn['license']['name'] == 'CC BY 4.0'  # of the site and of each report
	assert all((site / p).is_file() for p in cat['about']['logos'])
	# a report published by an older version, with the names of its analyses in Spanish: in English in the catalogue
	path = site / sn['path']
	old = json.loads(path.read_text(encoding='utf-8'))
	old['analyses'] = [{'id': 'trend', 'name': 'Tendencia'}, {'id': 'series', 'name': 'Serie temporal'}]
	path.write_text(json.dumps(old), encoding='utf-8')
	names = {r['id']: [a['name'] for a in r['analyses']] for r in publish.update_catalog(site)['reports']}
	assert names['2026-10-sierra-nevada-verdor'] == ['Trend', 'Time series']
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



def test_tags_and_the_orthophoto(outputs, monkeypatch):
	"""The tags of a report reach its report.json and the catalogue (which filters by them); with basemap pnoa its
	maps open over the PNOA orthophoto, which is also under its image in the catalogue, and the credits name it."""
	import numpy as np
	asked = []

	def ortho(wkt, extent, width, height, timeout=30):
		asked.append((width, height))
		return np.full((height, width, 3), (10, 20, 30), dtype='uint8')

	monkeypatch.setattr(publish, '_orthophoto', ortho)
	site = outputs / 'site'
	r = publish.publish(_spec(tags=['PRESINMED', ' PRESINMED', 'Sierra Nevada'], basemap='PNOA'), site, outputs, log='')
	folder = site / 'reports' / r['id']
	assert r['tags'] == ['PRESINMED', 'Sierra Nevada'] and publish.check_report(r, str(folder)) == []
	m = r['results'][0]
	assert m['kind'] == 'map' and m['basemap'] == 'pnoa' and publish.PNOA_CREDIT in r['credits']
	assert asked == [(publish.THUMBNAIL_WIDTH, round(15 * publish.THUMBNAIL_WIDTH / 20))]
	png = gdal.Open(str(folder / 'thumbnail.png'))
	rgba = np.dstack([png.GetRasterBand(i).ReadAsArray() for i in (1, 2, 3, 4)])
	png = None  # closed: Windows does not delete an open file when the report is published again
	assert (rgba[..., 3] == 255).all()  # opaque: the orthophoto where the map has no data
	assert rgba[0, 0].tolist() == [10, 20, 30, 255] and rgba[-1, -1].tolist() != [10, 20, 30, 255]
	cat = json.loads((site / 'catalog.json').read_text(encoding='utf-8'))
	assert cat['reports'][0]['tags'] == ['PRESINMED', 'Sierra Nevada'] and publish.check_site(site) == []

	# a map can have its own base map; without one, OpenStreetMap, and neither the orthophoto nor its credit
	asked.clear()
	r = publish.publish(_spec(tags='PRESINMED', basemap='pnoa', results=[
		{'answer': 'data/map.json', 'basemap': 'osm'}, {'answer': 'data/series.json'}]), site, outputs, log='')
	assert r['tags'] == ['PRESINMED'] and r['results'][0]['basemap'] == 'osm' and not asked
	assert publish.PNOA_CREDIT not in r['credits']
	r = publish.publish(_spec(), site, outputs, log='')  # without tags in its YAML: it keeps those it had
	assert r['tags'] == ['PRESINMED'] and r['results'][0]['basemap'] == 'osm' and 'view' not in r['results'][0]
	assert publish.publish(_spec(tags=[]), site, outputs, log='')['tags'] == []

	# a view: the map opens there, and its image in the catalogue is that part of it
	asked.clear()
	view = [-3.55, 37.105, -3.52, 37.125]
	r = publish.publish(_spec(basemap='pnoa', view=view), site, outputs, log='')
	assert r['results'][0]['view'] == view and publish.check_report(r, str(folder)) == []
	(w, h), = asked
	assert w == publish.THUMBNAIL_WIDTH and h != round(15 * w / 20)  # not the shape of the whole map
	png = gdal.Open(str(folder / 'thumbnail.png'))
	assert (png.RasterXSize, png.RasterYSize) == (w, h)
	png = None

	# wrong values: nothing is published
	with pytest.raises(ValueError, match='basemap'):
		publish.publish(_spec(id='otro', basemap='satellite'), site, outputs, log='')
	with pytest.raises(ValueError, match='basemap'):
		publish.publish(_spec(id='otro', results=[{'answer': 'data/map.json', 'basemap': 'google'}]), site, outputs,
		                log='')
	with pytest.raises(ValueError, match='tag'):
		publish.publish(_spec(id='otro', tags=['<b>PRESINMED</b>']), site, outputs, log='')
	with pytest.raises(ValueError, match='view'):
		publish.publish(_spec(id='otro', view=[-3.5, 37.2, -3.6, 37.1]), site, outputs, log='')
	assert not (site / 'reports' / 'otro').exists()
	bad = json.loads(json.dumps(r))
	bad['tags'] = 'PRESINMED'
	bad['results'][0]['basemap'] = 'google'
	bad['results'][0]['view'] = [10, 50]
	problems = ' | '.join(publish.check_report(bad, str(site / 'reports' / r['id'])))
	assert 'tags is a list' in problems and 'its basemap is one of osm, pnoa, none' in problems
	assert 'its view is [west, south, east, north]' in problems
	# a report published before the tags and the base maps is still right
	old = json.loads(json.dumps(r))
	del old['tags'], old['results'][0]['basemap'], old['results'][0]['view']
	assert publish.check_report(old, str(site / 'reports' / r['id'])) == []



def test_the_names_of_the_classes(tmp_path):
	"""class_labels gives names that say what each class of an area by class is (Dry, not below 0.05), in order."""
	csv_path = _csv(tmp_path / 'state.csv', [
		{'region': 'Borreguiles', 'class': c, 'label': label, 'ha': ha, 'percent': pct}
		for c, label, ha, pct in ((0, 'below 0.05', 80.0, 9.2), (1, '0.05 to 0.1', 162.0, 18.6), (2, '0.1 or more', 630.0, 72.2))])
	item = {'tool': 'area_by_class', 'args': {'region': {'wdpa_id': 389011}, 'variable': 'LSWI', 'sensor': 'Sentinel-2',
	                                          'start': '2017-06-01', 'end': '2019-09-30', 'breaks': [0.05, 0.1]},
	        'result': {'csv': csv_path, 'classes': [{'class': 0, 'label': 'below 0.05', 'colour': 'ecab4e'},
	                                                {'class': 1, 'label': '0.05 to 0.1', 'colour': '529400'},
	                                                {'class': 2, 'label': '0.1 or more', 'colour': '023701'}]}}
	site = tmp_path / 'site'
	spec = _spec(files=None, downloads=None, results=[dict(item, class_labels=['Dry', 'Intermediate', 'Wet'])])
	r = publish.publish(spec, site, tmp_path, log='')
	(chart,) = r['results']
	assert chart['chart'] == 'areas' and [c['label'] for c in chart['classes']] == ['Dry', 'Intermediate', 'Wet']
	assert [c['colour'] for c in chart['classes']] == ['ecab4e', '529400', '023701']  # the colours stay
	assert publish.check_report(r, str(site / 'reports' / r['id'])) == []
	r = publish.publish(_spec(files=None, downloads=None, results=[item]), site, tmp_path, log='')
	assert [c['label'] for c in r['results'][0]['classes']] == ['below 0.05', '0.05 to 0.1', '0.1 or more']
	with pytest.raises(ValueError, match='one per class'):
		publish.publish(_spec(id='otro', files=None, downloads=None, results=[dict(item, class_labels=['Dry', 'Wet'])]),
		                site, tmp_path, log='')


def test_a_map_in_classes(tmp_path):
	"""breaks draws a map in classes of its values (as area_by_class), named by class_labels and with the colours of
	palette (one per class), also in its image of the catalogue; the difference of a comparison stays continuous."""
	import numpy as np
	tif = _tif(tmp_path / 'state.tif', ['difference', 'reference', 'other'], [0.01, 0.04, 0.12])
	item = {'tool': 'download_comparison',
	        'args': {'region': {'wdpa_id': 389011}, 'variable': 'LSWI', 'sensor': 'Sentinel-2', 'start': '2017-06-01',
	                 'end': '2019-09-30', 'other_start': '2023-06-01', 'other_end': '2025-09-30'},
	        'result': {'file': tif, 'bands': ['difference', 'reference', 'other'], 'min': -0.1, 'max': 0.1}}
	site = tmp_path / 'site'
	r = publish.publish(_spec(files=None, downloads=None, results=[dict(
		item, band='other', breaks=[0.05, 0.10], class_labels=['Dry', 'Intermediate', 'Wet'],
		palette=['ecab4e', '529400', '023701'])]), site, tmp_path, log='')
	(m,) = r['results']
	legends = {b['name']: b['legend'] for b in m['bands']}
	assert legends['difference']['type'] == 'continuous' and m['band'] == 'other'
	assert legends['other'] == legends['reference'] == {'type': 'breaks', 'breaks': [0.05, 0.1], 'classes': [
		{'label': 'Dry', 'color': '#ecab4e'}, {'label': 'Intermediate', 'color': '#529400'},
		{'label': 'Wet', 'color': '#023701'}]}
	assert publish.check_report(r, str(site / 'reports' / r['id'])) == []
	png = gdal.Open(str(site / 'reports' / r['id'] / 'thumbnail.png'))
	rgba = np.dstack([png.GetRasterBand(i).ReadAsArray() for i in (1, 2, 3, 4)])
	png = None
	assert rgba[-1, -1].tolist() == [2, 55, 1, 255] and rgba[0, 0, 3] == 0  # wet (0.12 and more); NoData
	# without names nor colours: those of area_by_class with breaks
	r = publish.publish(_spec(files=None, downloads=None, results=[dict(item, breaks=[0.05, 0.10])]), site, tmp_path,
	                    log='')
	classes = r['results'][0]['bands'][1]['legend']['classes']
	assert [c['label'] for c in classes] == ['below 0.05', '0.05 to 0.1', '0.1 or more']
	assert all(re.fullmatch(r'#[0-9a-f]{6}', c['color']) for c in classes)
	with pytest.raises(ValueError, match='one per class'):
		publish.publish(_spec(id='otro', files=None, downloads=None,
		                      results=[dict(item, breaks=[0.05, 0.10], class_labels=['Dry', 'Wet'])]), site, tmp_path,
		                log='')

def test_the_step_of_a_table_without_its_call(tmp_path):
	"""A CSV published without its call (a table made from several results) gets its step from its dates."""
	annual = _csv(tmp_path / 'a.csv', [{'region': 'r', 'date': f'{y}-01-01', 'value': 1} for y in (2017, 2018)])
	monthly = _csv(tmp_path / 'm.csv', [{'region': 'r', 'date': f'2017-{m:02d}-01', 'value': 1} for m in (1, 2)])
	daily = _csv(tmp_path / 'd.csv', [{'region': 'r', 'date': '2017-01-05', 'value': 1}])
	assert [publish._step_of(p) for p in (annual, monthly, daily)] == ['annual', 'monthly', None]


def test_the_trend_of_a_series_of_its_own_values(tmp_path):
	"""trend: true draws on an annual series without a trend_table (a table made from several results) the Sen line
	of its own values, with its Mann-Kendall p-value; a series that is not annual cannot have it."""
	values = [46, 86, 70, 68, 74, 56, 70, 73, 70]
	csv_path = _csv(tmp_path / 'wet.csv', [{'region': 'Borreguiles', 'date': f'{2017 + i}-01-01', 'value': v}
	                                      for i, v in enumerate(values)])
	site = tmp_path / 'site'
	item = {'result': {'csv': csv_path, 'unit': '%'}, 'title': 'Wet share', 'trend': True}
	r = publish.publish(_spec(files=None, downloads=None, results=[item]), site, tmp_path, log='')
	(s,) = r['results']
	assert s['chart'] == 'series' and s['step'] == 'annual' and publish.check_report(r, str(site / 'reports' / r['id'])) == []
	(line,) = s['sen']
	from monitoreo import trends
	years = list(range(2017, 2026))
	slope, intercept = trends.sen(years, values)
	assert (line['from'], line['to'], line['origin'], line['period']) == (2017, 2025, 2017, '2017-2025')
	assert line['slope'] == slope and line['intercept'] == intercept and line['significant'] is False
	assert abs(line['p_value'] - trends.mann_kendall(years, values)[3]) < 1e-12
	monthly = _csv(tmp_path / 'm.csv', [{'region': 'r', 'date': f'2017-{m:02d}-01', 'value': m} for m in (1, 2, 3)])
	with pytest.raises(ValueError, match='annual series'):
		publish.publish(_spec(id='otro', files=None, downloads=None, results=[dict(item, result={'csv': monthly})]),
		                site, tmp_path, log='')


def test_two_variables_over_the_years(tmp_path):
	"""chart: series_two draws a table of two variables over the years (its column variable), each with its axis."""
	rows = [{'region': 'Borreguiles', 'variable': v, 'date': f'{y}-01-01', 'value': x}
	        for v, base in (('NDVI', 0.4), ('LSWI', 0.1)) for y, x in zip(range(2017, 2020), (base, base + 0.02, base + 0.01))]
	csv_path = _csv(tmp_path / 'both.csv', rows)
	site = tmp_path / 'site'
	item = {'result': {'csv': csv_path}, 'title': 'NDVI and LSWI', 'chart': 'series_two'}
	r = publish.publish(_spec(files=None, downloads=None, results=[item]), site, tmp_path, log='')
	(c,) = r['results']
	assert c['chart'] == 'series_two' and c['variables'] == ['NDVI', 'LSWI']
	assert (c['ylabel'], c['other_ylabel']) == ('NDVI', 'LSWI') and publish.check_report(r, str(site / 'reports' / r['id'])) == []
	one = _csv(tmp_path / 'one.csv', rows[:3])
	with pytest.raises(ValueError, match='two variables'):
		publish.publish(_spec(id='otro', files=None, downloads=None, results=[dict(item, result={'csv': one})]), site,
		                tmp_path, log='')

def test_the_orthophoto_without_network(tmp_path, monkeypatch):
	"""Without the WMS of the IGN the image of the catalogue is made without the orthophoto."""
	import urllib.request

	def down(*a, **k):
		raise OSError('no network')

	monkeypatch.setattr(urllib.request, 'urlopen', down)
	ds = gdal.Open(_tif(tmp_path / 'm.tif', ['value'], [0.5]))
	assert publish._orthophoto(ds.GetProjection(), (450000, 4106250, 455000, 4110000), 40, 30) is None
	assert publish._window(ds, None) == (0, 0, 20, 15)
	assert publish._window(ds, [10, 50, 11, 51]) == (0, 0, 20, 15)  # a view outside the map: all of it

def test_problems(outputs):
	site = outputs / 'site'
	with pytest.raises(ValueError, match='title'):
		publish.publish(_spec(title=''), site, outputs, log='')
	with pytest.raises(ValueError, match='lowercase'):
		publish.publish(_spec(id='Sierra Nevada'), site, outputs, log='')
	with pytest.raises(FileNotFoundError):
		publish.publish(_spec(files=None), site, outputs, log='')  # the files of the answers are not found
	with pytest.raises(ValueError, match='licence'):
		publish.publish(_spec(license='GPL'), site, outputs, log='')
	assert not (site / 'reports' / '2026-10-sierra-nevada-verdor').exists()  # nothing half published
	r = publish.publish(_spec(), site, outputs, log='')
	folder = str(site / 'reports' / r['id'])
	bad = json.loads(json.dumps(r))
	bad['results'][0]['bands'][0]['legend']['palette'] = ['red']
	bad['results'][1]['csv'] = '/etc/passwd'
	bad['files'][0]['path'] = '../../x.tif'
	bad['published'] = '29/10/2026'
	bad['license'] = {'name': 'CC BY 4.0', 'url': 'javascript:alert(1)'}
	problems = ' | '.join(publish.check_report(bad, folder))
	for text in ('palette of 2 or more colours', 'its CSV is not in files', 'a relative path', 'published is a date',
	             'license has a name and an https url'):
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


def test_tags_of_a_published_report(outputs):
	"""The tags of a published report without publishing it again (those published before the tags): in its
	report.json and the catalogue; published again without tags it keeps them, with tags it takes those."""
	site = outputs / 'site'
	r = publish.publish(_spec(), site, outputs, log='')
	assert r['tags'] == []
	res = services.tag_report(r['id'], ['Fire', 'National parks', 'Fire'], str(site))
	assert res['tags'] == ['Fire', 'National parks']
	report = json.loads((site / 'reports' / r['id'] / 'report.json').read_text(encoding='utf-8'))
	cat = json.loads((site / 'catalog.json').read_text(encoding='utf-8'))
	assert report['tags'] == ['Fire', 'National parks'] and cat['reports'][0]['tags'] == ['Fire', 'National parks']
	assert publish.check_site(site) == []
	assert publish.publish(_spec(), site, outputs, log='')['tags'] == ['Fire', 'National parks']  # its YAML has none
	assert publish.publish(_spec(tags=['Snow']), site, outputs, log='')['tags'] == ['Snow']
	assert services.tag_report(r['id'], [], str(site))['tags'] == []
	with pytest.raises(ValueError, match='there is no report'):
		publish.set_tags('no-such-report', ['Fire'], site)
	with pytest.raises(ValueError, match='a tag is a short text'):
		publish.set_tags(r['id'], ['<b>'], site)
	from monitoreo import cli
	assert cli.main(['publish', '--site', str(site), '--tags', r['id'], 'Wet meadows', 'Snow']) in (None, 0)
	assert json.loads((site / 'catalog.json').read_text(encoding='utf-8'))['reports'][0]['tags'] == ['Wet meadows', 'Snow']


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
	assert publish.period_text('2023-05-15', '2023-08-14') == '15 May 2023 - 14 Aug 2023'
	assert publish.season_text(['06-01', '08-31']) == ' (June to August)'
	assert publish.season_text(['12-01', '02-28']) == ' (December to February)'
	assert publish.season_text(['05-15', '08-14']) == ' (15 May to 14 August)'
	assert publish.unit_text('[ºC]') == '°C' and publish.unit_text('[unitless]') == ''
	assert publish.unit_text('[ºC]', per_year=True) == '°C/year' and publish.unit_text('', per_year=True) == 'per year'
	assert publish.slug('Aigüestortes i Estany de Sant Maurici') == 'aiguestortes-i-estany-de-sant-maurici'
	assert publish.license_of()['id'] == publish.license_of('cc by 4.0')['id'] == 'CC-BY-4.0'
	assert publish.license_of('CC0-1.0')['name'] == 'CC0 1.0'
	assert publish.license_of({'name': 'ODbL', 'url': 'https://opendatacommons.org/licenses/odbl/'}) == \
		{'name': 'ODbL', 'url': 'https://opendatacommons.org/licenses/odbl/'}
	assert publish.python_call('trend_table', {'region': {'wdpa_id': 1}, 'quality': {'snow': False}, 'alpha': None}) \
		== 'mo.trend_table(region={"wdpa_id": 1}, quality={"snow": False}, alpha=None)'
	args = {'variable': 'NDSI', 'sensor': 'Modis', 'start': '2001-01-01', 'end': '2005-12-31',
	        'other_start': '2020-01-01', 'other_end': '2024-12-31', 'season': ['03-01', '05-31']}
	assert publish.default_title('download_comparison', args) == \
		'Map of the difference of NDSI (MODIS): 2020-2024 minus 2001-2005 (March to May)'
	assert publish.default_title('compare_series', args) == \
		'NDSI (MODIS) by month: 2020-2024 compared with 2001-2005 (March to May)'
	assert publish.default_title('time_series', dict(args, step='16-day')) == \
		'16-day time series of NDSI (MODIS), 2001-2005 (March to May)'
	assert publish.default_title('trend_table', dict(args, step='monthly')) == \
		'Trend of each month of NDSI (MODIS), 2001-2005 (March to May)'
	assert publish.default_title('download_trend', dict(args, step='monthly', part=7)) == \
		'Map of the trend of July of NDSI (MODIS), 2001-2005 (March to May)'
	assert publish.default_title('burn_severity', dict(args, sensor='Sentinel-2')) == \
		'Burn severity (dNBR of Sentinel-2): before, 2001-2005; after, 2020-2024'


def test_rdnbr(tmp_path):
	"""A burn severity with the RdNBR (Miller & Thode 2007) in the viewer: its GeoTIFF with its band severity in the
	classes of the article (not those of the USGS) and its band rdnbr, and the chart of its classes; the dNBR, as
	before."""
	from monitoreo import fire, trends
	out = tmp_path / 'mcp_out'
	out.mkdir()
	bands = ['rdnbr', 'severity', 'dnbr', 'nbr_before', 'nbr_after']
	_tif(out / 'burn_RdNBR.tif', bands, [0.4, 2, 0.3, 0.5, 0.2])
	rows = fire.table([{'class': 1, 'sum': 12.5}, {'class': 3, 'sum': 3.0}], 'Fire', 'RdNBR')
	_csv(out / 'burn_RdNBR.csv', [dict(r, index='RdNBR', sensor='Landsat') for r in rows])
	args = {'region': {'wdpa_id': 389011}, 'sensor': 'Landsat', 'index': 'RdNBR', 'start': '2022-06-01',
	        'end': '2022-07-31', 'other_start': '2023-06-01', 'other_end': '2023-07-31'}
	data = tmp_path / 'data'
	data.mkdir()
	(data / 'burn.json').write_text(json.dumps({'call': {'id': 'burn', 'tool': 'burn_severity', 'args': args},
	                                            'is_error': False, 'text': [{
		'index': 'RdNBR', 'classes': rows, 'burned_ha': {'Fire': 15.5}, 'bands': bands,
		'file': '/tmp/does-not-exist/burn_RdNBR.tif', 'csv': '/tmp/does-not-exist/burn_RdNBR.csv'}]}),
		encoding='utf-8')
	r = publish.publish(_spec(results=[{'answer': 'data/burn.json'}], downloads=[]), tmp_path / 'site', tmp_path,
	                    log='')
	assert publish.check_report(r, str(tmp_path / 'site' / 'reports' / r['id'])) == []
	m, chart = r['results']
	assert m['title'] == 'Burn severity (RdNBR of Landsat): before, 1 Jun 2022 - 31 Jul 2022; after, ' \
	                     '1 Jun 2023 - 31 Jul 2023'
	assert m['band'] == 'severity'  # shown first: the classes
	b = {x['name']: x for x in m['bands']}
	assert b['severity']['label'] == 'Severity class of Miller & Thode 2007 (0 unchanged, 1 low, 2 moderate, 3 high)'
	assert b['severity']['legend'] == {'type': 'categories', 'classes': fire.legend('RdNBR')}
	assert [c['color'] for c in b['severity']['legend']['classes']] == ['#' + fire.RDNBR_COLOURS[c] for c in range(4)]
	assert b['rdnbr']['label'] == 'RdNBR (dNBR / sqrt(max(|NBR before|, 0.001)))'
	assert b['rdnbr']['legend']['palette'] == [f'#{c}' for c in reversed(trends.DIVERGING)]  # burned in red
	assert b['rdnbr']['legend']['min'] == -b['rdnbr']['legend']['max']
	assert (chart['chart'], chart['index'], chart['burned_min']) == ('burn_severity', 'RdNBR', fire.RDNBR_BURNED)
	assert chart['classes'] == fire.legend('RdNBR') and chart['burned_ha'] == {'Fire': 15.5}
	assert chart['title'] == 'Area of each severity class'
	assert r['variables'] == [{'variable': 'RdNBR', 'sensor': 'Landsat',
	                           'name': 'Relative differenced Normalized Burn Ratio', 'unit': ''}]
	assert any(c['citation'].startswith('Miller, J. D., & Thode, A. E. (2007)') for c in r['references'])
	# the dNBR keeps the scale of the USGS
	dnbr = ['dnbr', 'severity', 'nbr_before', 'nbr_after']
	assert publish.band_text('severity', dnbr) == ('Severity (USGS scale)', '')
	assert publish.band_text('severity', bands)[0].startswith('Severity class of Miller & Thode 2007')
	assert publish._severity_legend(fire.index_of(dnbr)) == {'type': 'categories', 'classes': fire.legend()}
	assert publish._severity_legend('RBR') == {'type': 'categories', 'classes': fire.legend()}  # as before
	assert publish.default_title('burn_severity', dict(args, sensor='Modis', collection='MODIS/061/MYD09GA')) == \
		'Burn severity (RdNBR of MODIS Aqua): before, 1 Jun 2022 - 31 Jul 2022; after, 1 Jun 2023 - 31 Jul 2023'
	assert publish.default_title('burn_severity', dict(args, index='RBR')).startswith('Burn severity (RBR of Landsat)')


def test_rbr_table(tmp_path):
	"""A burn severity with the RBR in the viewer: its CSV has the statistics of the RBR of each region (no classes), so
	it is a table, not the chart of the severity classes; the dNBR keeps the chart of its classes."""
	from monitoreo import fire
	out = tmp_path / 'mcp_out'
	out.mkdir()
	bands = ['rbr', 'dnbr', 'nbr_before', 'nbr_after']
	_tif(out / 'burn_RBR.tif', bands, [0.3, 0.3, 0.5, 0.2])
	stats = {'region': 'Fire', 'mean': 0.21, 'median': 0.18, 'std': 0.15, 'cv': 71.43, 'p10': 0.02, 'p90': 0.45,
	         'min': -0.1, 'max': 0.7, 'ha': 120.5}
	assert list(stats) == services.RBR_COLUMNS
	_csv(out / 'burn_RBR.csv', [dict(stats, index='RBR', sensor='Sentinel-2', before='2022-06-01/2022-07-31',
	                                 after='2023-06-01/2023-07-31', metric='median', scale_m=20)])
	_csv(out / 'burn_dNBR.csv', fire.table([{'class': 1, 'sum': 12.5}, {'class': 3, 'sum': 3.0}], 'Fire'))
	args = {'region': {'wdpa_id': 389011}, 'sensor': 'Sentinel-2', 'index': 'RBR', 'start': '2022-06-01',
	        'end': '2022-07-31', 'other_start': '2023-06-01', 'other_end': '2023-07-31'}
	data = tmp_path / 'data'
	data.mkdir()
	gone = '/tmp/does-not-exist/'
	(data / 'rbr.json').write_text(json.dumps({'call': {'id': 'rbr', 'tool': 'burn_severity', 'args': args},
	                                           'is_error': False, 'text': [{
		'index': 'RBR', 'stats': [stats], 'bands': bands, 'file': gone + 'burn_RBR.tif',
		'csv': gone + 'burn_RBR.csv'}]}), encoding='utf-8')
	dnbr = dict(args, index='dNBR')
	(data / 'dnbr.json').write_text(json.dumps({'call': {'id': 'dnbr', 'tool': 'burn_severity', 'args': dnbr},
	                                            'is_error': False, 'text': [{
		'classes': [], 'burned_ha': {'Fire': 15.5}, 'csv': gone + 'burn_dNBR.csv'}]}), encoding='utf-8')
	r = publish.publish(_spec(results=[{'answer': 'data/rbr.json'}, {'answer': 'data/dnbr.json'}], downloads=[]),
	                    tmp_path / 'site', tmp_path, log='')
	assert publish.check_report(r, str(tmp_path / 'site' / 'reports' / r['id'])) == []
	m, table, classes = r['results']
	assert m['kind'] == 'map' and m['band'] == 'rbr'
	assert (table['kind'], table['chart']) == ('chart', 'table')  # not the chart of the severity classes
	assert 'classes' not in table and 'burned_ha' not in table
	assert table['title'] == 'Statistics of the RBR in each region'
	assert (classes['chart'], classes['index']) == ('burn_severity', 'dNBR')
	assert classes['classes'] == fire.legend() and classes['burned_ha'] == {'Fire': 15.5}


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
	assert html.count('<html lang="en">') == 2 and 'wiki/Results-viewer"' in html
