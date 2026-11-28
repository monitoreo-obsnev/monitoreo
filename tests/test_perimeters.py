"""Official perimeters as regions (monitoreo.perimeters): Copernicus EMS, EFFIS, WFS and files on the web, without the
network or Earth Engine: their answers are small local files."""

import json
import os

import pytest

from monitoreo import areas, perimeters, references, report

pytest.importorskip('osgeo')


def square(lon, lat, d=0.01):
	return {'type': 'Polygon', 'coordinates': [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d],
	                                            [lon, lat]]]}


def collection(*geoms, props=None):
	return {'type': 'FeatureCollection', 'features': [
		{'type': 'Feature', 'geometry': g, 'properties': (props or [{}] * len(geoms))[i]} for i, g in enumerate(geoms)]}


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
	monkeypatch.setattr(perimeters, 'FOLDER', str(tmp_path / 'perimeters'))
	for d in (perimeters._memo, perimeters._credits, perimeters._names):
		d.clear()
	yield


def write(tmp_path, name, obj):
	path = tmp_path / name
	path.write_text(json.dumps(obj) if not isinstance(obj, str) else obj, encoding='utf-8')
	return str(path)


@pytest.mark.parametrize('spec, message', [
	({'ems': 'EMS375'}, 'activation of Copernicus EMS'),
	({'ems': 'EMSR375', 'product': 'map'}, '"delineation" or "grading"'),
	({'ems': 'EMSR375', 'aoi': 'one'}, 'aoi is a whole number'),
	({'effis_id': 'San Ildefonso'}, 'find_burnt_areas'),
	({'effis_id': 0}, 'find_burnt_areas'),
	({'wfs': 'https://si.icnf.pt/wfs/areas_ardidas'}, 'takes layer'),
	({'wfs': 'si.icnf.pt/wfs', 'layer': 'x'}, r'address \(http or https\) of a WFS'),
	({'url': 'perimeters.zip'}, r'address \(http or https\) of a vector file'),
	({'ems': 'EMSR375', 'layer': 'x'}, 'ems takes aoi, product, monitoring, not layer'),
])
def test_check_refuses_before_the_network(spec, message):
	with pytest.raises(ValueError, match=message):
		areas.check(spec)


def test_check_accepts_them_with_within():
	assert areas.check({'ems': 'emsr375', 'aoi': 1, 'product': 'Grading'}) == 'ems'
	assert areas.check({'effis_id': [17545, '18345'], 'within': {'wdpa_id': 555546231}}) == 'effis_id'
	assert areas.check({'wfs': 'https://si.icnf.pt/wfs/areas_ardidas', 'layer': 'BDG:ardida_2022',
	                    'cql_filter': 'AreaHaSIG > 10000', 'name_field': 'Cod_SGIF'}) == 'wfs'
	assert areas.check({'url': 'https://example.org/fires.zip', 'filter': "year = 2023", 'dissolve': True}) == 'url'
	with pytest.raises(ValueError, match='give one region'):
		areas.check({'ems': 'EMSR375', 'bbox': [0, 0, 1, 1]})


def test_read_filters_names_and_dissolves(tmp_path):
	path = write(tmp_path, 'fires.geojson', collection(square(-3.5, 37.0), square(-3.4, 37.0), square(-3.3, 37.0),
	                                                   props=[{'code': 'a', 'year': 2021}, {'code': 'b', 'year': 2023},
	                                                          {'code': 'c', 'year': 2023}]))
	feats = perimeters.read(path, name_field='code')
	assert [f['name'] for f in feats] == ['a', 'b', 'c']
	assert [f['name'] for f in perimeters.read(path, where='year = 2023', name_field='code')] == ['b', 'c']
	one = perimeters.read(path, where='year = 2023', dissolve=True, name='Fires of 2023')
	assert len(one) == 1 and one[0]['name'] == 'Fires of 2023' and one[0]['geometry']['type'] == 'MultiPolygon'
	assert [f['name'] for f in perimeters.read(path)] == ['Feature 1', 'Feature 2', 'Feature 3']
	with pytest.raises(ValueError, match="no field 'nombre'"):
		perimeters.read(path, name_field='nombre')
	with pytest.raises(ValueError, match='no polygons with year = 1990'):
		perimeters.read(path, where='year = 1990')
	with pytest.raises(ValueError, match='the fields are code, year'):
		perimeters.read(path, where='anyo = 1990')


PAGE = '''<a class="nav-link active" id="aoi-1-tab" data-bs-toggle="tab" type="button" role="tab">
	AOI01 La Granja de San Ildefonso
</a>
<p>Activation time</p><p>05/08/2019, 09:29</p>
<a href="https://cems-mapping-website.s3.eu-west-1.amazonaws.com/static/activations/EMSR375/EMSR375_AOI01_DEL_PRODUCT_r1_RTP01_v1_vector.zip">
<a href="https://cems-mapping-website.s3.eu-west-1.amazonaws.com/static/activations/EMSR375/EMSR375_AOI01_GRA_PRODUCT_r1_RTP01_v1_vector.zip">
<a href="https://cems-mapping-website.s3.eu-west-1.amazonaws.com/static/activations/EMSR375/EMSR375_AOI01_GRA_PRODUCT_r1_RTP01_v2_vector.zip">
'''


def test_ems_before_the_dashboard_reads_the_page_and_its_packages(tmp_path, monkeypatch):
	"""EMSR375 (2019): not in the dashboard of EMS; its page links its vector packages, of which the last version of
	the grading is used by default, and the delineation with product."""
	from osgeo import ogr, osr
	zips = {}
	for typ, ver in (('DEL', 1), ('GRA', 1), ('GRA', 2)):
		folder = tmp_path / f'{typ}{ver}'
		folder.mkdir()
		srs = osr.SpatialReference()
		srs.ImportFromEPSG(4326)
		ds = ogr.GetDriverByName('ESRI Shapefile').CreateDataSource(str(folder))
		for layer, d in ((f'EMSR375_AOI01_{typ}_PRODUCT_observedEventA_r1_v{ver}', 0.01 * ver + (0.02 if typ == 'GRA' else 0)),
		                 (f'EMSR375_AOI01_{typ}_PRODUCT_areaOfInterestA_r1_v{ver}', 0.5)):
			lyr = ds.CreateLayer(layer, srs, ogr.wkbPolygon)
			feat = ogr.Feature(lyr.GetLayerDefn())
			feat.SetGeometry(ogr.CreateGeometryFromJson(json.dumps(square(-4.0, 40.9, d))))
			lyr.CreateFeature(feat)
		ds = None
		import zipfile
		z = tmp_path / f'{typ}{ver}.zip'
		with zipfile.ZipFile(z, 'w') as f:
			for name in os.listdir(folder):
				f.write(folder / name, name)
		zips[f'EMSR375_AOI01_{typ}_PRODUCT_r1_RTP01_v{ver}_vector.zip'] = str(z)
	page = write(tmp_path, 'page.html', PAGE)
	monkeypatch.setattr(perimeters, '_json', lambda url, params=None, days=None: {'detail': 'Authentication'})

	def download(url, params=None, ext='', days=None):
		return page if url.startswith('https://mapping.') else zips[os.path.basename(url)]
	monkeypatch.setattr(perimeters, 'download', download)
	feats = perimeters.features('ems', {'ems': 'EMSR375'})
	assert [f['name'] for f in feats] == ['EMSR375 AOI01 La Granja de San Ildefonso: Grading Map']
	assert perimeters.credits({'ems': 'EMSR375'}) == [
		'Copernicus Emergency Management Service (© 2019 European Union), [EMSR375] La Granja de San Ildefonso (AOI01): '
		'Grading Map']
	west, east, _, _ = ogr.CreateGeometryFromJson(json.dumps(feats[0]['geometry'])).GetEnvelope()
	assert east - west == pytest.approx(0.04, abs=1e-4)  # the version 2 of the grading, not the area of interest
	feats = perimeters.features('ems', {'ems': 'EMSR375', 'product': 'delineation'})
	assert feats[0]['name'].endswith('Delineation Map')
	assert 'EMSR375 AOI01 La Granja de San Ildefonso: Delineation Map' in report.region_text(
		{'ems': 'EMSR375', 'product': 'delineation'})
	with pytest.raises(ValueError, match='has no AOI 2'):
		perimeters.features('ems', {'ems': 'EMSR375', 'aoi': 2})
	with pytest.raises(ValueError, match='no vector product of monitoring 3'):
		perimeters.features('ems', {'ems': 'EMSR375', 'monitoring': 3})


def test_ems_of_the_dashboard(tmp_path, monkeypatch):
	"""EMSR685 (2023): its products in the dashboard of EMS, the observed event of each as GeoJSON; without grading,
	the last delineation (its monitoring)."""
	layers = {n: write(tmp_path, f'{n}.json', collection(square(-16.5, 28.3, d), square(-16.4, 28.3, d)))
	          for n, d in (('del0', 0.01), ('del2', 0.03))}
	act = {'results': [{'code': 'EMSR685', 'activationTime': '2023-08-16T08:00:00', 'aois': [
		{'number': 1, 'name': 'Candelaria', 'products': [
			{'type': 'DEL', 'monitoringNumber': '0', 'version': {'deliveryTime': '2023-08-19T03:40:00'},
			 'layers': [{'name': 'EMSR685/AOI01/DEL_PRODUCT/x_observedEventA_v1_VT', 'json': 'https://s3/del0.json'}]},
			{'type': 'DEL', 'monitoringNumber': '2', 'version': {'deliveryTime': '2023-08-25T00:41:00'},
			 'layers': [{'name': 'EMSR685/AOI01/DEL_MONIT02/x_observedEventA_v1_VT', 'json': 'https://s3/del2.json'},
			            {'name': 'EMSR685/AOI01/DEL_MONIT02/x_observedEventP_v1_VT', 'json': 'https://s3/p.json'}]},
			{'type': 'DEL', 'monitoringNumber': '3', 'layers': []}]}]}]}
	monkeypatch.setattr(perimeters, '_json', lambda url, params=None, days=None: act)
	monkeypatch.setattr(perimeters, 'download',
	                    lambda url, params=None, ext='', days=None: layers[os.path.basename(url)[:-5]])
	feats = perimeters.features('ems', {'ems': 'EMSR685'})
	assert [f['name'] for f in feats] == ['EMSR685 AOI01 Candelaria: Delineation Map (monitoring 2)']
	assert feats[0]['geometry']['type'] == 'MultiPolygon'  # the two polygons, one feature
	assert perimeters.credits({'ems': 'EMSR685'}) == [
		'Copernicus Emergency Management Service (© 2023 European Union), [EMSR685] Candelaria (AOI01): Delineation Map']
	assert perimeters.features('ems', {'ems': 'EMSR685', 'monitoring': 0})[0]['name'].endswith('Delineation Map')
	with pytest.raises(ValueError, match='no grading map'):
		perimeters.features('ems', {'ems': 'EMSR685', 'product': 'grading'})


def test_credits_without_the_network(monkeypatch):
	"""The credits never fail: an EMS that cannot be read gets the general line; the others need no download."""
	def fail(*a, **k):
		raise ValueError('cannot download')
	monkeypatch.setattr(perimeters, 'download', fail)
	monkeypatch.setattr(perimeters, '_json', fail)
	assert perimeters.credits({'ems': 'EMSR999'}) == ['Copernicus Emergency Management Service (© European Union), '
	                                                  '[EMSR999]']
	assert perimeters.credits({'effis_id': 1, 'within': {'wfs': 'https://a.org/wfs?x=1', 'layer': 'L'}}) == [
		perimeters.EFFIS_CREDIT, 'Perimeters: layer L of the WFS https://a.org/wfs']
	assert perimeters.credits({'wdpa_id': 1}) == []
	cited = references.cite('region_stats', {'region': {'effis_id': 17545}, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
	                                         'start': '2019-09-01', 'end': '2019-09-30'})
	assert 'sanmiguelayanz2012' in [r['id'] for r in cited['references']]
	assert perimeters.EFFIS_CREDIT in cited['credits']
	assert report.region_text({'effis_id': [17545, 18345]}) == 'Burnt area of EFFIS 17545, 18345'
	assert report.region_text({'url': 'https://a.org/f.zip', 'layer': 'fires', 'filter': 'year = 2023'}) == \
		'File https://a.org/f.zip, layer fires (year = 2023)'


def test_effis_and_find_burnt_areas(tmp_path, monkeypatch):
	shape = {'type': 'MultiPolygon', 'coordinates': [square(-4.0, 40.88, 0.04)['coordinates']]}
	burnt = {'id': 17545, 'shape': shape, 'firedate': '2019-08-04T00:00:00+02:00', 'area_ha': '393',
	         'province': 'Segovia', 'commune': 'Real Sitio de San Ildefonso'}
	wfs = collection(square(-4.0, 40.88, 0.04), square(-3.8, 40.95, 0.02), square(-4.1, 40.75, 0.01), props=[
		{'id': '17545', 'FIREDATE': '2019-08-04 00:00:00', 'FINALDATE': '2019-08-05 00:00:00', 'AREA_HA': '393',
		 'COUNTRY': 'ES', 'PROVINCE': 'Segovia', 'COMMUNE': 'Real Sitio de San Ildefonso'},
		{'id': '18345', 'FIREDATE': '2019-08-04 00:00:00', 'AREA_HA': '222', 'COUNTRY': 'ES', 'PROVINCE': 'Madrid'},
		{'id': '9', 'FIREDATE': '2005-07-01 00:00:00', 'AREA_HA': '40', 'COUNTRY': 'ES', 'PROVINCE': 'Madrid'}])
	asked = []

	def answer(url, params=None, days=None):
		asked.append((url, params))
		return burnt if url.endswith('/17545/') else wfs
	monkeypatch.setattr(perimeters, '_json', answer)
	feats = perimeters.features('effis_id', {'effis_id': 17545})
	assert feats[0]['name'] == 'EFFIS 17545: Real Sitio de San Ildefonso, Segovia, 2019-08-04, 393 ha'
	rows = perimeters.find_burnt_areas([-4.2, 40.7, -3.7, 41.0], start='2010-01-01')
	assert [r['effis_id'] for r in rows] == [17545, 18345] and rows[0]['region'] == {'effis_id': 17545}
	assert asked[-1][1]['bbox'] == '40.7,-4.2,41.0,-3.7,EPSG:4326'  # WFS 1.1.0 in EPSG:4326: latitude first
	touch = square(-3.99, 40.89, 0.005)  # only the first one touches it
	assert [r['effis_id'] for r in perimeters.find_burnt_areas([-4.2, 40.7, -3.7, 41.0], touch)] == [17545]
	assert [r['effis_id'] for r in perimeters.find_burnt_areas([-4.2, 40.7, -3.7, 41.0], min_area_ha=300)] == [17545]


def test_wfs_falls_back_to_gml(tmp_path, monkeypatch):
	"""A WFS without GeoJSON (an exception) is asked again for its GML."""
	gml = write(tmp_path, 'answer.gml', '')
	exception = write(tmp_path, 'answer.json', '<?xml version="1.0"?><ows:ExceptionReport>no json</ows:ExceptionReport>')
	geojson = write(tmp_path, 'fires.geojson', collection(square(-8.0, 41.8)))
	formats = []

	def download(url, params=None, ext='', days=None):
		formats.append(params.get('outputFormat'))
		return exception if params.get('outputFormat') else gml
	monkeypatch.setattr(perimeters, 'download', download)
	monkeypatch.setattr(perimeters, 'read', lambda path, *a, **k: [{'name': path, 'geometry': square(0, 0)}])
	feats, credits = perimeters.wfs('https://si.icnf.pt/wfs/areas_ardidas', 'BDG:ardida_2022')
	assert formats == ['application/json', None] and feats[0]['name'] == gml
	assert credits == ['Perimeters: layer BDG:ardida_2022 of the WFS https://si.icnf.pt/wfs/areas_ardidas']
	assert os.path.exists(geojson)


def test_read_invalid_collections_and_zips_without_extension(tmp_path):
	"""A ring that crosses itself is made valid before the union; the polygons of a collection are kept; a zip is
	read by its signature, whatever its name."""
	bowtie = {'type': 'Polygon', 'coordinates': [[[0, 0], [0.01, 0.01], [0.01, 0], [0, 0.01], [0, 0]]]}
	path = write(tmp_path, 'bad.geojson', collection(bowtie, square(0.005, 0.0, 0.01)))
	one = perimeters.read(path, dissolve=True, name='Fire')
	assert len(one) == 1 and one[0]['name'] == 'Fire'
	mixed = {'type': 'GeometryCollection', 'geometries': [square(1, 1), {'type': 'Point', 'coordinates': [1, 1]}]}
	path = write(tmp_path, 'mixed.geojson', collection(mixed))
	assert perimeters.read(path)[0]['geometry']['type'] in ('Polygon', 'MultiPolygon')
	import zipfile
	z = tmp_path / 'descarga'  # a download endpoint without an extension
	with zipfile.ZipFile(z, 'w') as f:
		f.writestr('fires.geojson', json.dumps(collection(square(2, 2))))
	assert len(perimeters.read(str(z))) == 1
	with pytest.raises(ValueError, match='cannot read'):
		perimeters.read(write(tmp_path, 'page.html', '<html>not a vector file</html>'))


def test_odd_answers_of_ems_and_big_downloads(tmp_path, monkeypatch):
	"""An answer of EMS of another shape is no product (the page is read, then the general credit line); a download
	over MAX_BYTES leaves no file behind."""
	monkeypatch.setattr(perimeters, '_json', lambda url, params=None, days=None: {'results': ['x', {'code': 'EMSR1',
	                                                                                            'aois': ['y']}]})
	assert perimeters._ems_api('EMSR1') == ([], None)
	assert perimeters._ems_api('EMSR100') == (None, None)
	monkeypatch.setattr(perimeters, '_ems_page', lambda code: (_ for _ in ()).throw(KeyError('odd')))
	assert perimeters.credits({'ems': 'EMSR100'}) == ['Copernicus Emergency Management Service (© European Union), '
	                                                  '[EMSR100]']

	class Big:
		url = 'https://a.org/big.zip'

		def __enter__(self):
			return self

		def __exit__(self, *a):
			return False

		def raise_for_status(self):
			pass

		def iter_content(self, n):
			while True:
				yield b'x' * n
	import requests
	monkeypatch.setattr(requests, 'get', lambda *a, **k: Big())
	monkeypatch.setattr(perimeters, 'MAX_BYTES', 3 << 20)
	with pytest.raises(ValueError, match='bigger than 3 MB'):
		perimeters.download('https://a.org/big.zip')
	assert os.listdir(perimeters.FOLDER) == []


def test_perimeters_of_a_control_ring_are_cited():
	for tool, args in (('control_ring', {'region': {'wdpa_id': 1}, 'exclude': {'effis_id': 5}}),
	                   ('time_series', {'region': {'wdpa_id': 1}, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
	                                    'start': '2019-01-01', 'end': '2019-12-31', 'ring': {'exclude': {'effis_id': 5}}})):
		cited = references.cite(tool, args)
		assert perimeters.EFFIS_CREDIT in cited['credits']
		assert 'sanmiguelayanz2012' in [r['id'] for r in cited['references']]
