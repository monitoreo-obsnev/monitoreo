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
