"""Tests of the references of MonitorEO (monitoreo.references and the bibliography of catalog.json), without Earth
Engine: every variable and method is cited, and every result, report and GeoTIFF carries its references."""

import datetime as dt
import json
import re

import pytest

from monitoreo import about, catalog, publish, references, report, sensors, services

DOI = re.compile(r'^10\.\d{4,9}/\S+$')
# variables whose formula still has no reference (the team has to find its source): the albedo of Sentinel-2
PENDING = {13}


def test_bibliography():
	cat = catalog.load()
	refs = references.bibliography()
	for rid, r in refs.items():
		assert r['citation'].strip() and not r['citation'].startswith('http'), rid
		assert r.get('doi') or r.get('url'), f'{rid} has no DOI nor URL'
		if r.get('doi'):
			assert DOI.match(r['doi']) and 'doi.org' not in r['citation'], rid
	# only Key & Benson 2006, the WDPA and FAO GAUL 2025 have no DOI (cited with their URL, as their pages say)
	assert sum(1 for r in refs.values() if not r.get('doi')) <= 3
	for name, ids in cat['methods'].items():
		assert ids and set(ids) <= set(refs), name
	for col, d in cat['datasets'].items():
		assert d['references'] and set(d['references']) <= set(refs), col
	# the Earth Engine citation of about is that of the bibliography
	assert references.get('gorelick2017')['text'] == about.EARTH_ENGINE
	assert references.get(references.MONITOREO)['text'] == about.CITATION


def test_every_variable_is_cited():
	known = catalog.load()['datasets']
	for e in catalog.variables():
		where = f"{e['ref']} {e['index']} {e['sensor']}"
		assert set(e['references']) <= set(references.bibliography()), where
		if e['ref'] in PENDING:
			assert not e['references'] and e['notes']['references'], where  # said in its notes
		else:
			assert e['references'], f'{where} has no reference of its formula or algorithm'
		for col in references.datasets(e['col']):  # its Earth Engine datasets, as the Earth Engine catalog suggests
			assert col in known, f'{where}: {col} is not in the datasets of the catalog'
		got = references.of_entry(e)
		assert all(r['doi'] for r in got['references']), where  # all of them with DOI
	# the Landsat collections of the code are all in the datasets
	assert {c for c, _, _ in sensors.LANDSAT} <= set(known) and sensors.CLOUD_SCORE in known


def _ids(cited):
	return [r['id'] for r in cited['references']]


def test_cite():
	date = dt.date(2026, 11, 8)
	c = references.cite('trend_table', {'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'sensor': 'Landsat',
	                                    'start': '2001-01-01', 'end': '2014-12-31'}, date)
	ids = _ids(c)
	assert {'tucker1979', 'mann1945', 'kendall1938', 'sen1968', 'gorelick2017', 'monitoreo', 'wdpa',
	        'foga2017'} <= set(ids)
	# the Landsat collections of the period only: 5, 7 (until 2003) and 8, not 9 (since 2021)
	assert {'usgs_landsat45', 'usgs_landsat7', 'usgs_landsat89'} <= set(ids)
	assert _ids(references.cite('map_layer', {'variable': 'NDVI', 'sensor': 'Landsat', 'start': '2022-01-01',
	                                          'end': '2022-12-31'})).count('usgs_landsat45') == 0
	assert c['credits'] == ['Landsat Collection 2 Level-2 data courtesy of the U.S. Geological Survey']
	assert [r['citation'] for r in c['references']] == sorted((r['citation'] for r in c['references']), key=str.lower)
	wdpa = next(r for r in c['references'] if r['id'] == 'wdpa')
	assert 'November 2026' in wdpa['citation'] and '(2026)' in wdpa['citation'] and wdpa['url']
	assert all(r['text'] == f"{r['citation']} {r['url']}" for r in c['references'])

	s2 = references.cite('time_series', {'region': {'bbox': [-3.6, 37, -3.5, 37.1]}, 'variable': 'NDVI',
	                                     'sensor': 'Sentinel-2', 'start': '2018-01-01', 'end': '2021-12-31'})
	assert {'esa_s2_l2a', 'pasquarella2023', 'mainknorn2017'} <= set(_ids(s2)) and 'mann1945' not in _ids(s2)
	assert s2['credits'] == ['Contains modified Copernicus Sentinel data 2018-2021']
	scl = references.cite('time_series', {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'quality': {'cloud_score': None},
	                                      'start': '2018-01-01', 'end': '2018-12-31'})
	assert 'pasquarella2023' not in _ids(scl) and 'mainknorn2017' in _ids(scl)  # SCL clouds, no Cloud Score+

	dnbr = _ids(references.cite('burn_severity', {'start': '2022-05-01', 'end': '2022-07-01'}))
	rbr = _ids(references.cite('burn_severity', {'start': '2022-05-01', 'end': '2022-07-01', 'index': 'rbr'}))
	assert {'garcia1991', 'key2006'} <= set(dnbr) and 'parks2014' not in dnbr
	assert {'parks2014', 'silvacardoza2022'} <= set(rbr) and 'key2006' not in rbr

	modis = _ids(references.cite('map_layer', {'variable': 'EVI', 'sensor': 'Modis',
	                                           'collection': 'MODIS/061/MYD13Q1', 'region': {'ecoregion_id': 793}}))
	assert {'myd13q1', 'huete2002', 'dinerstein2017'} <= set(modis) and 'mod13q1' not in modis
	other = _ids(references.cite('map_layer', {'collection': 'ESA/WorldCover/v200', 'band': 'Map'}))
	assert 'zanaga2022' in other
	recipe = {'period': ['2018-01-01', '2021-12-31'], 'ecoregion': {'resolution': 100},
	          'variables': [{'index': 'LSWI', 'sensor': 'Sentinel-2', 'exclude_landcover': [40]},
	                        {'name': 'slope', 'image': 'COPERNICUS/DEM/GLO30_2024_1', 'band': 'DEM'}]}
	got = references.cite('download_variables', {'recipe': recipe, 'area': {'wdpa_id': 389011}})
	assert {'xiao2004', 'zanaga2022', 'dinerstein2017', 'wdpa', 'esa_s2_l2a'} <= set(_ids(got))
	# describe_variable and find_protected_areas
	assert 'monitoreo' not in _ids(references.of_entry(catalog.find('LAI', 'Modis')))
	assert '[years of the data]' in references.of_entry(catalog.find('NDVI', 'Sentinel-2'))['credits'][0]
	assert 'wdpa' in _ids(references.cite('find_protected_areas', {'text': 'Doñana'}))
	# the cloud frequency (Wilson & Jetz 2016, and Cloud Score+ in Sentinel-2) and the climate, with their credits
	cf = references.cite('time_series', {'variable': 'CF', 'sensor': 'Sentinel-2', 'start': '2023-01-01',
	                                     'end': '2023-12-31'})
	assert {'wilson2016', 'pasquarella2023', 'esa_s2_l2a'} <= set(_ids(cf)) and 'mainknorn2017' not in _ids(cf)
	assert {'wilson2016', 'mod09ga061'} <= set(_ids(references.cite('map_layer', {'variable': 'CF', 'sensor': 'Modis'})))
	era5 = references.cite('time_series', {'variable': 'PRECIP', 'sensor': 'ERA5-Land', 'start': '2001-01-01',
	                                       'end': '2023-12-31'})
	assert {'munozsabater2021', 'munozsabater2019'} <= set(_ids(era5))
	assert era5['credits'][0].startswith('Contains modified Copernicus Climate Change Service information 2001-2023')
	assert 'hijmans2005' in _ids(references.cite('region_stats', {'variable': 'BIO12', 'sensor': 'WorldClim'}))
	# administrative units (FAO GAUL 2025, with its disclaimer as credit) and islands (Sayre et al. 2019)
	gaul = references.cite('time_series', {'region': {'admin2': 141938}, 'variable': 'NDVI', 'sensor': 'Modis'})
	assert 'fao_gaul2025' in _ids(gaul) and any(c.startswith('Source: FAO GAUL 2025') for c in gaul['credits'])
	assert 'fao_gaul2025' in _ids(references.cite('map_layer', {'region': {'country': 'ESP'}, 'variable': 'NDVI',
	                                                            'sensor': 'Modis'}))
	island = references.cite('region_stats', {'region': {'island_at': [2.9, 39.6]}, 'variable': 'ELEVATION',
	                                          'sensor': 'Copernicus'})
	assert 'sayre2019' in _ids(island) and any('CC BY-SA' in c for c in island['credits'])
	assert report.region_text({'admin2': 141938}) == 'Administrative unit 141938 of level 2 (FAO GAUL 2025)'
	assert report.region_text({'admin1': [1], 'x': 0}, {'admin1:1': 'Andalucía, Spain'}) == (
		'Andalucía, Spain (administrative unit, FAO GAUL 2025)')
	assert report.region_text({'country': 'esp'}, {'country:ESP': 'Spain'}) == 'Spain (country, FAO GAUL 2025)'
	assert report.region_text({'island_at': [2.9, 39.6]}) == 'Island at the point 39.6, 2.9 (lat., lon.)'
	# the elevation and the slope of the Copernicus DEM: the DEM, its credit line and, for the slope, its gradient
	dem = 'produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018'
	for index, more in (('ELEVATION', set()), ('SLOPE', {'zevenbergen1987'})):
		c = references.cite('map_layer', {'variable': index, 'sensor': 'Copernicus', 'region': {'wdpa_id': 389011}})
		assert {'esa_copernicus_dem', 'rizzoli2017'} | more <= set(_ids(c)) and c['credits'][0].startswith(dem), index
	assert 'esa_copernicus_dem' in _ids(got)  # the slope of the recipe, from the DEM image
	# the SCF also reads the TOA scenes (snow in the shadow) and the SRTM (its hillShadow), of the period only
	scf = references.cite('time_series', {'variable': 'SCF', 'sensor': 'Landsat', 'start': '2022-01-01',
	                                      'end': '2022-12-31'})
	assert {'hall1995', 'usgs_landsat89', 'usgs_landsat89_l1', 'chander2009', 'farr2007', 'nasa_srtmgl1'} <= set(_ids(scf))
	assert 'usgs_landsat45_l1' not in _ids(scf)
	assert 'Landsat Collection 2 Level-1 data courtesy of the U.S. Geological Survey' in scf['credits']


def test_services_cite(monkeypatch, tmp_path):
	"""The functions of monitoreo.services add the references of their call to their answer and their GeoTIFF."""
	gdal = pytest.importorskip('osgeo.gdal')

	def download_trend(region, variable=None, sensor=None, start=None, end=None, step='annual', path=None,
	                   **source):
		ds = gdal.GetDriverByName('GTiff').Create(path, 2, 2, 1, gdal.GDT_Float32)
		ds = None
		return {'file': path}

	path = str(tmp_path / 'trend.tif')
	out = services._cited(download_trend)({'wdpa_id': 1}, 'NDVI', 'Modis', '2001-01-01', '2020-12-31', path=path)
	assert {'mann1945', 'sen1968', 'mod13q1', 'wdpa', 'gorelick2017', 'monitoreo'} <= set(_ids(out))
	tag = gdal.Open(path).GetMetadataItem('references')
	assert 'https://doi.org/10.2307/1907187' in tag and tag.count('\n') == len(out['references']) - 1
	# a source of Earth Engine given by collection (**source)
	src = services._cited(download_trend)({'bbox': [0, 0, 1, 1]}, path=str(tmp_path / 'b.tif'),
	                                       collection='MODIS/061/MOD13Q1', band='NDVI')
	assert 'mod13q1' in _ids(src)
	d = services.describe_variable('NDCI', 'Sentinel-2')
	assert 'mishra2012' in _ids(d) and d['credits']
	assert services.about()['earth_engine'] == about.EARTH_ENGINE and 'Earth Engine' in about.text()
	# every function of services that computes cites
	for name in ('time_series', 'map_layer', 'region_stats', 'export_image', 'download_image', 'download_variables',
	             'trend_table', 'trend_map', 'download_trend', 'compare_series', 'compare_map', 'download_comparison',
	             'burn_severity', 'time_series_to_drive'):
		assert getattr(services, name).__wrapped__, name


def test_reports(tmp_path):
	args = {'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2021-01-01',
	        'end': '2021-12-31', 'step': 'monthly'}
	items = [{'tool': 'time_series', 'args': args, 'result': {'rows': [], 'unit': '[unitless]'}},
	         {'tool': 'trend_table', 'args': dict(args, variable='EVI'), 'result': {'rows': []}}]
	refs, credits, numbers = references.of_items(items)
	assert len(refs) == len({r['id'] for r in refs}) and credits == ['Contains modified Copernicus Sentinel data 2021']
	mann = next(i + 1 for i, r in enumerate(refs) if r['id'] == 'mann1945')
	assert mann in numbers[1] and mann not in numbers[0]
	text = open(report.write(items, str(tmp_path / 'r.html'), title='t'), encoding='utf-8').read()
	assert '<h2>References</h2>' in text and 'https://doi.org/10.1016/0034-4257(79)90013-0' in text
	assert 'Huete, A., Didan, K.' in text and 'Contains modified Copernicus Sentinel data 2021' in text
	assert re.search(r'<dt>References</dt><dd>\[\d+\](, \[\d+\])*', text)


def test_viewer_has_references():
	js = open(publish.__file__.replace('publish.py', 'viewer/assets/report.js'), encoding='utf-8').read()
	assert 'report.references' in js and 'r.references' in js


def test_mcp_answers_keep_references(monkeypatch, tmp_path):
	"""time_series, trend_table and compare_series of the MCP server summarize the answer: with its references."""
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	monkeypatch.setattr(services, 'eecu_warning', lambda *a, **k: None)
	cited = references.cite('trend_table', {'variable': 'NDVI', 'sensor': 'Modis'})
	res = dict(cited, title='t', unit='', scale=250, csv=None, chart=None, rows=[], n_steps=0, regions=[], profile=[],
	           yearly=[])
	for name in ('time_series', 'trend_table', 'compare_series'):
		monkeypatch.setattr(services, name, lambda *a, **k: res)
	args = ({'bbox': [0, 0, 1, 1]}, 'NDVI', 'Modis', '2001-01-01', '2020-12-31')
	for fn, more in ((mcp_server.time_series, ()), (mcp_server.trend_table, ()),
	                 (mcp_server.compare_series, ('2021-01-01', '2022-12-31'))):
		out = fn(*args, *more)
		answer = json.loads(out[0] if isinstance(out, list) else out)
		assert answer['references'] == json.loads(json.dumps(cited['references'])), fn.__name__
		assert 'credits' in answer, fn.__name__
	assert about.EARTH_ENGINE in mcp_server.INSTRUCTIONS and 'references and credits' in mcp_server.INSTRUCTIONS


def test_zenodo_metadata():
	"""Zenodo reads .zenodo.json: the creator, title, license and keywords of CITATION.cff, the core team as
	contributors (in alphabetical order of their surnames) and the references of the catalog."""
	import os
	import unicodedata
	root = os.path.join(os.path.dirname(__file__), '..')
	with open(os.path.join(root, '.zenodo.json'), encoding='utf-8') as f:
		z = json.load(f)
	cff = open(os.path.join(root, 'CITATION.cff'), encoding='utf-8').read()
	assert z['title'] == 'MonitorEO' and f'title: "{z["title"]}"' in cff and z['upload_type'] == 'software'
	creator = z['creators'][0]['name']
	assert creator == 'Observatorio de Cambio Global de Sierra Nevada' and creator in cff
	assert f"license: {z['license']}" in cff and all(f'  - {k}' in cff for k in z['keywords'])
	assert about.DESCRIPTION['en'] in z['description'] and about.ACKNOWLEDGEMENTS['en'] in z['description']
	names = [c['name'] for c in z['contributors']]
	plain = lambda n: unicodedata.normalize('NFKD', n).encode('ascii', 'ignore').decode().lower()
	assert names == sorted(names, key=plain) and len(names) == 5
	assert all(c['type'] == 'ProjectMember' and re.fullmatch(r'[^,]+, [^,]+', c['name']) for c in z['contributors'])
	for c in z['contributors']:  # every one with their ORCID, with its ISO 7064 11,2 check digit
		assert re.fullmatch(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', c.get('orcid', '')), f"{c['name']} has no ORCID"
		digits = c['orcid'].replace('-', '')
		total = 0
		for d in digits[:-1]:
			total = (total + int(d)) * 2
		check = (12 - total % 11) % 11
		assert digits[-1] == ('X' if check == 10 else str(check)), c
	assert z['references'] == references.bibliography_texts(), \
		'update the references of .zenodo.json: monitoreo.references.bibliography_texts()'
