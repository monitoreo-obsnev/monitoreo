"""Tests with Earth Engine: run with EE_PROJECT set (pytest -m ee), after `earthengine authenticate`."""

import os

import pytest

from monitoreo import services

pytestmark = [pytest.mark.ee, pytest.mark.skipif(not os.environ.get('EE_PROJECT'), reason='EE_PROJECT not set')]

GUAJARES = {'bbox': [-3.62, 36.86, -3.50, 36.93]}  # a small box in Granada, Spain


@pytest.fixture(scope='module', autouse=True)
def connect():
	services.init()


def test_time_series(tmp_path):
	res = services.time_series(GUAJARES, 'NDVI', 'Sentinel-2', '2021-05-01', '2021-07-31', step='monthly',
	                           csv=str(tmp_path / 'ts.csv'), chart=str(tmp_path / 'ts.png'))
	assert [r['date'] for r in res['rows']] == ['2021-05-01', '2021-06-01', '2021-07-01']
	assert all(0 < r['value'] < 1 and r['n_images'] > 0 and r['n_pixels'] > 0 for r in res['rows'])
	assert os.path.getsize(res['csv']) > 0 and os.path.getsize(res['chart']) > 0


def test_two_regions_and_landsat():
	region = {'geojson': {'type': 'FeatureCollection', 'features': [
		{'type': 'Feature', 'properties': {'name': 'west'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[-3.62, 36.86], [-3.56, 36.86], [-3.56, 36.93], [-3.62, 36.93], [-3.62, 36.86]]]}},
		{'type': 'Feature', 'properties': {'name': 'east'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[-3.56, 36.86], [-3.50, 36.86], [-3.50, 36.93], [-3.56, 36.93], [-3.56, 36.86]]]}},
	]}}
	res = services.time_series(region, 'LST', 'Landsat', '2020-01-01', '2021-12-31', step='annual', metric='max', stat='median')
	assert res['regions'] == ['east', 'west'] and len(res['rows']) == 4
	assert all(20 < r['value'] < 70 for r in res['rows'])  # degrees Celsius


def test_map_layer_and_thumbnail(tmp_path):
	m = services.map_layer(GUAJARES, 'NDVI', 'Sentinel-2', '2021-01-01', '2021-12-31', metric='median',
	                       thumbnail=str(tmp_path / 'map.png'))
	assert m['url'].startswith('https://') and '{z}' in m['url'] and m['min'] < m['max']
	assert open(m['thumbnail'], 'rb').read(4) == b'\x89PNG'


def test_region_stats():
	res = services.region_stats(GUAJARES, 'NDVI', 'Sentinel-2', '2021-01-01', '2021-12-31')
	row = res['rows'][0]
	assert row['min'] <= row['p50'] <= row['max'] and row['n_pixels'] > 0


def test_protected_areas():
	parks = services.find_protected_areas('Sierra Nevada', 10)
	assert any(p['SITE_ID'] == 389011 for p in parks)


RECIPE = {'study': {'resolution': 250, 'buffer': 500}, 'ecoregion': {'resolution': 10000},
          'period': ['2021-01-01', '2021-12-31'],
          'variables': [{'index': 'NDVI', 'sensor': 'Modis', 'metric': 'median'},
                        {'name': 'temp', 'image': 'WORLDCLIM/V1/BIO', 'band': 'bio01', 'scale': 0.1}]}


def _values(path):
	from osgeo import gdal
	ds = gdal.Open(path)
	a = ds.GetRasterBand(1).ReadAsArray()
	return a[a != -9999], a.size, ds.GetGeoTransform()


def test_download_variables(tmp_path):
	out = str(tmp_path / 'vars')
	plan = services.download_variables(RECIPE, GUAJARES, out, dry_run=True)
	assert set(plan['grids']) == {'study', 'ecoregion'} and plan['ecoregions'][0]['ECO_ID'] == 793
	assert [f['file'] for f in plan['files']] == ['1_NDVI_MODIS_median.tif', '2_temp.tif']
	assert plan['files'][0]['images'] == 23 and plan['files'][1]['images'] is None
	res = services.download_variables(RECIPE, GUAJARES, out)
	assert res['done'] and res['folders']['ecoregion'] == os.path.join(out, 'ecoregion')
	ndvi, n, gt = _values(os.path.join(out, '1_NDVI_MODIS_median.tif'))
	assert 0.9 * n < len(ndvi) and 0.1 < ndvi.mean() < 0.8 and gt[1] == 250 and gt[0] % 250 == 0  # sea: NoData
	temp, n, _ = _values(os.path.join(out, 'ecoregion', '2_temp.tif'))
	assert 0 < len(temp) < n and 5 < temp.mean() < 20  # NoData outside the ecoregion; degrees Celsius
	from osgeo import ogr
	ds = ogr.Open(os.path.join(out, 'ecoregion', 'ecoregions.gpkg'))
	feats = list(ds.GetLayer(0))
	assert [f.GetField('ECO_ID') for f in feats] == [793]
	assert all(f.GetGeometryRef().GetGeometryType() == ogr.wkbMultiPolygon for f in feats)
	log = []
	again = services.download_variables(RECIPE, GUAJARES, out, log=log.append)
	assert again['done'] and sum('up to date' in m for m in log) == 4


def test_download_variables_vector_file(tmp_path):
	w, s, e, n = GUAJARES['bbox']
	area = tmp_path / 'area.geojson'
	area.write_text('{"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": '
	                f'{{"type": "Polygon", "coordinates": [[[{w}, {s}], [{e}, {s}], [{e}, {n}], [{w}, {n}], [{w}, {s}]]]}}}}]}}')
	plan = services.download_variables(dict(RECIPE, ecoregion=None), str(area), str(tmp_path), dry_run=True)
	g = plan['grids']['study']
	assert list(plan['grids']) == ['study'] and g['crs'] == 'EPSG:32630' and plan['area'] == 'area.geojson'
	assert 40 < g['width'] < 60 and 30 < g['height'] < 50  # 11 x 8 km at 250 m, plus 500 m and 2 pixels


def test_download_image(tmp_path):
	res = services.download_image(GUAJARES, 'NDVI', 'Modis', '2021-01-01', '2021-12-31', resolution=250,
	                              path=str(tmp_path / 'ndvi.tif'))
	values, n, gt = _values(res['file'])
	assert res['images'] == 23 and res['grid']['crs'] == 'EPSG:32630' and gt[1] == 250
	assert 0 < len(values) <= n and 0.1 < values.mean() < 0.8
