"""The computations on this computer (monitoreo.local): without network, the formulas, filters, reductions and
regions; with the network and Earth Engine (EE_PROJECT, pytest -m "ee and network"), the same time series and maps
computed in Earth Engine and on this computer must give the same values."""

import os

import numpy as np
import pytest

from monitoreo import catalog, cli, local, services, sensors
from monitoreo.grid import Grid

osgeo = pytest.importorskip('osgeo')

GUAJARES = {'bbox': [-3.62, 36.86, -3.50, 36.93]}  # a small box in Granada, Spain
TWO = {'geojson': {'type': 'FeatureCollection', 'features': [
	{'type': 'Feature', 'properties': {'name': 'west'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[-3.62, 36.86], [-3.56, 36.86], [-3.56, 36.93], [-3.62, 36.93], [-3.62, 36.86]]]}},
	{'type': 'Feature', 'properties': {'name': 'east'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[-3.56, 36.86], [-3.50, 36.86], [-3.50, 36.93], [-3.56, 36.93], [-3.56, 36.86]]]}},
]}}
GRID = Grid('EPSG:32630', 30, 450000, 4080000, 4, 3)


# Without network ---------------------------------------------------------------------------------------------------

def test_percentile_and_reductions_as_earth_engine():
	# values of Earth Engine (ImageCollection.reduce of constant images)
	assert local.percentile(np.array([1., 2, 3, 4]), 50) == 2.5
	ten = np.arange(1., 11)
	assert local.percentile(ten, 25) == 3 and local.percentile(ten, 90) == 9.5 and local.percentile(ten, 50) == 5.5
	assert local.percentile(np.array([np.nan, 4., 1, np.nan]), 0) == 1 and local.percentile(np.array([np.nan]), 50) != 0
	stack = np.array([[1., np.nan], [2, np.nan], [3, 5], [4, np.nan]])
	assert np.allclose(local.percentile(stack, 50, axis=0), [2.5, 5])
	for metric, expected in [('mean', [2.5, 5]), ('std', [1.118033988749895, 0]), ('min', [1, 5]), ('max', [4, 5]),
	                         ('sum', [10, 5]), ('count', [4, 1]), ('median', [2.5, 5]), ('p90', [4, 5])]:
		r = local.Reducer(metric, (2,))
		for row in stack:
			r.add(row.astype(np.float32))
		assert np.allclose(r.result(), expected), metric
	assert np.isnan(local.Reducer('mean', (3,)).result()).all()
	assert local.Reducer('count', (3,)).result().tolist() == [0, 0, 0]
	with pytest.raises(ValueError):
		local.Reducer('mode', (2,))
	assert local.statistic(np.array([1., 2, 3, 4]), 'median') == 2.5 and local.statistic(np.array([]), 'mean') is None


def test_formulas():
	# every formula of Sentinel-2 and Landsat in the catalog, with the bands as Earth Engine names them
	for e in catalog.variables():
		if e['sensor'] not in local.SENSORS:
			continue
		names = list(local.S2_BANDS) if e['sensor'] == 'Sentinel-2' else sensors.band_names(e)
		kind, bands = sensors.parse_formula(e, names)  # ValueError if a band has no name of the data
		if kind == 'expr':
			assert np.isfinite(local.evaluate(e['ft'], {name: np.array([0.1, 0.2]) for name in bands})).all(), e['ref']
	b8, b4, b2 = np.array([0.4]), np.array([0.1]), np.array([0.05])
	evi = local.evaluate('2.5 * ((B8 - B4) / (B8 + 6 * B4 - 7.5 * B2 + 1))', {'B8': b8, 'B4': b4, 'B2': b2})
	assert np.allclose(evi, 2.5 * (0.3 / (0.4 + 0.6 - 0.375 + 1)))
	assert local.evaluate('b / (b - b)', {'b': np.array([2.])}).tolist() == [0]  # x / 0 = 0, as in Earth Engine
	assert local.evaluate('-b ** 2', {'b': np.array([3.])}).tolist() == [-9]
	with pytest.raises(ValueError):
		local.evaluate('sqrt(b)', {'b': np.array([1.])})
	nd = local.normalized_difference(np.array([0., 0.1, -0.1, 0.3]), np.array([0., -0.05, 0.05, 0.1]))
	assert nd[0] == 0 and np.isnan(nd[1]) and np.isnan(nd[2]) and np.isclose(nd[3], 0.5)  # as Earth Engine


def test_harmonized():
	raw = np.array([0, 999, 1000, 2500])
	assert local.harmonized(raw, '05.10').tolist() == [0, 0, 0, 1500]  # as COPERNICUS/S2_SR_HARMONIZED
	assert local.harmonized(raw, '03.01').tolist() == [0, 999, 1000, 2500]
	assert local.harmonized(raw).tolist() == [0, 999, 1000, 2500]  # Landsat


def test_quality_masks():
	s2 = local.Reader(catalog.find('NDVI', 'Sentinel-2'), {}, GRID)
	assert s2.used == ['B8', 'B4'] and s2.qa == ['SCL']
	scl = np.array([[4, 5, 8, 9], [10, 3, 6, 11], [7, 2, 1, 4]])
	assert s2._quality({'SCL': scl}).astype(int).tolist() == [[1, 1, 0, 0], [0, 0, 0, 0], [1, 1, 1, 1]]
	ndsi = local.Reader(catalog.find('NDSI', 'Sentinel-2'), {'snow': 'auto'}, GRID)  # the snow filter is off
	assert ndsi._quality({'SCL': scl})[1].astype(int).tolist() == [0, 0, 0, 1]
	none = local.Reader(catalog.find('NDVI', 'Sentinel-2'), {f: False for f in sensors.FILTERS}, GRID)
	assert none.qa == []
	ls = local.Reader(catalog.find('NDVI', 'Landsat'), {}, GRID)
	assert ls.used == ['nir', 'red'] and ls.qa == ['QA_PIXEL', 'SR_QA_AEROSOL']
	# QA_PIXEL: 21824 clear land (Landsat 8), bit 1 dilated cloud, 3 cloud, 4 shadow, 5 snow, 7 water
	qa = np.array([[21824, 21824 | 2, 21824 | 8, 21824 | 16], [21824 | 32, 21824 | 128, 21824, 21824]])
	aerosol = np.array([[0, 0, 0, 0], [0, 0, 192, 64]])  # bits 6-7: 3 = high
	assert ls._quality({'QA_PIXEL': qa, 'SR_QA_AEROSOL': aerosol}).astype(int).tolist() == [[1, 0, 0, 0], [0, 0, 0, 1]]
	assert ls._quality({'QA_PIXEL': qa}).astype(int).tolist() == [[1, 0, 0, 0], [0, 0, 1, 1]]  # Landsat 5 and 7
	assert local.Reader(catalog.find('LST', 'Landsat'), {}, GRID).used == ['st']


def test_resampling_as_earth_engine():
	s2 = local.Reader(catalog.find('ALBEDO', 'Sentinel-2'), {}, Grid('EPSG:32630', 20, 0, 0, 1, 1))
	assert s2.methods['B2'] == 'average' and s2.methods['B5'] == 'near' and s2.methods['SCL'] == 'near'
	assert local.Reader(catalog.find('NDVI', 'Landsat'), {}, Grid('EPSG:32630', 10, 0, 0, 1, 1)).methods['nir'] == 'bilinear'
	assert local.Reader(catalog.find('NDVI', 'Landsat'), {}, GRID, 'nearest').methods['nir'] == 'near'


def test_regions_and_masks():
	regs = local.regions(TWO)
	assert [n for n, _ in regs] == ['west', 'east']
	grid = local.grid_of(regs, 30)
	assert grid.crs == 'EPSG:32630' and grid.xmin % 30 == 0 and grid.ymax % 30 == 0
	(_, west), (_, east) = local.masks(regs, grid)
	assert west.sum() > 0 and east.sum() > 0 and not (west & east).any()  # a pixel centre is in one of them
	point = local.regions({'point': [-3.6, 36.9]})
	assert local.masks(point, local.grid_of(point, 10))[0][1].sum() == 1
	buffered = local.regions({'point': [-3.6, 36.9], 'buffer': 500})
	n = local.masks(buffered, local.grid_of(buffered, 10))[0][1].sum()
	assert abs(n * 100 - np.pi * 500 ** 2) / (np.pi * 500 ** 2) < 0.02
	assert local.auto_scale(catalog.find('NDVI', 'Sentinel-2'), local.regions(GUAJARES)) == 10
	assert local.auto_scale(catalog.find('NDVI', 'Sentinel-2'), local.regions({'bbox': [-3.7, 36.9, -3.5, 37.1]})) == 20
	assert local.auto_scale(catalog.find('NDVI', 'Sentinel-2'), local.regions({'bbox': [-4, 36.5, -3, 37.5]})) == 100
	for region in ({'wdpa_id': 555513}, {'ecoregion_at': [-3.5, 37]}):
		with pytest.raises(ValueError, match='Earth Engine'):
			local.regions(region)


def test_steps():
	spec = services.make_spec('NDVI', 'Sentinel-2', '2021-05-01', '2021-06-30')
	items = [{'properties': {'datetime': d}} for d in ('2021-05-03T10:56:19Z', '2021-05-03T10:56:30Z', '2021-06-12T10:56:19Z')]
	assert local._steps(spec, 'daily', items) == [('2021-05-03', '2021-05-04'), ('2021-06-12', '2021-06-13')]
	assert local._steps(spec, 'monthly', items) == [('2021-05-01', '2021-06-01'), ('2021-06-01', '2021-07-01')]
	assert [len(g) for g in local._groups(items, local._steps(spec, 'daily', items))] == [2, 1]


def test_where():
	gee, here = services.where_info('gee'), services.where_info('local')
	assert gee['where'] == 'gee' and 'Google account' in gee['credentials']
	assert here['where'] == 'local' and here['credentials'] == 'none' and here['computed_on'] == 'on this computer'
	assert 'credentials: none' in services.where_text(here) and 'on this computer' in services.where_text(here)
	assert "Google's cloud" in services.where_text(gee)
	with pytest.raises(ValueError):
		services.where_info('cloud')
	with pytest.raises(ValueError, match='Sentinel-2 and Landsat'):
		local.check(services.make_spec('NDVI', 'Modis', '2021-01-01', '2021-12-31'))
	with pytest.raises(ValueError, match='catalog'):
		local.check(services.make_spec(collection='IDAHO_EPSCOR/TERRACLIMATE', band='pr', start='2021-01-01', end='2021-12-31'))
	s2 = catalog.find('NDVI', 'Sentinel-2')
	assert local.notes(s2, {'period': ['2023-01-01', '2023-12-31']}) == ['Sentinel-2 clouds: SCL classes (Cloud Score+ is only in Earth Engine)']
	assert local.notes(s2, {'period': ['2023-01-01', '2023-12-31'], 'quality': {'cloud_score': None}}) == []
	assert 'other processings' in local.notes(s2, {'period': ['2021-01-01', '2023-12-31'], 'quality': {'cloud_score': None}})[0]
	assert local.notes(catalog.find('NDVI', 'Landsat'), {'period': ['1990-01-01', '2023-12-31']}) == []


def test_cli_says_where_before_computing(capsys):
	cli.main(['--project', 'my-project', 'series', 'NDVI', '--sensor', 'Sentinel-2', '--region',
	          '{"bbox": [-3.6, 36.9, -3.5, 37]}', '--start', '2021-01-01', '--end', '2021-12-31', '--plan'])
	err = capsys.readouterr().err
	assert err.startswith("Computing in Google's cloud (Google Earth Engine), project my-project") and 'credentials' in err


# With the network and Earth Engine: the same values ----------------------------------------------------------------

# Sentinel-2 from 2022 (before, Planetary Computer has other processings: local.S2_SAME_FROM), and periods without the
# few images that Planetary Computer lacks (e.g. 5 of the 73 of Guajares in 2021, from 15 October to 4 November)
SERIES = {  # case: (region, arguments of services.time_series)
	's2_ndvi_daily': (GUAJARES, dict(variable='NDVI', sensor='Sentinel-2', start='2024-06-01', end='2024-07-31',
	                                 step='daily', quality={'cloud_score': None})),
	's2_evi_monthly_p90': (GUAJARES, dict(variable='EVI', sensor='Sentinel-2', start='2022-05-01', end='2022-08-31',
	                                      step='monthly', metric='median', stat='p90', quality={'cloud_score': None})),
	's2_albedo_16day': (GUAJARES, dict(variable='ALBEDO', sensor='Sentinel-2', start='2024-07-01', end='2024-09-30',
	                                   step='16-day', quality={'cloud_score': None})),
	'landsat_two_regions': (TWO, dict(variable='NDVI', sensor='Landsat', start='2018-01-01', end='2019-12-31',
	                                  step='annual', metric='max', stat='median')),
	'landsat_5_and_7': (GUAJARES, dict(variable='NDVI', sensor='Landsat', start='2000-01-01', end='2001-12-31',
	                                   step='annual', metric='mean')),
	'landsat_lst_monthly': (GUAJARES, dict(variable='LST', sensor='Landsat', start='2019-06-01', end='2019-08-31',
	                                       step='monthly', metric='mean')),
}


@pytest.fixture(scope='module')
def earth_engine():
	services.init()


@pytest.mark.parametrize('case', SERIES)
@pytest.mark.ee
@pytest.mark.network
@pytest.mark.skipif(not os.environ.get('EE_PROJECT'), reason='EE_PROJECT not set')
def test_series_as_earth_engine(case, earth_engine):
	region, args = SERIES[case]
	gee = services.time_series(region, **args)
	here = services.time_series(region, where='local', **args)
	assert (gee['where'], here['where']) == ('gee', 'local') and gee['scale'] == here['scale']
	assert [(r['region'], r['date']) for r in gee['rows']] == [(r['region'], r['date']) for r in here['rows']]
	most = max(r['n_pixels'] for r in gee['rows'])
	compared = same = 0
	for g, h in zip(gee['rows'], here['rows']):
		if g['n_images'] != h['n_images']:  # an image that one of the catalogs lacks
			continue
		compared += 1
		if abs(g['n_pixels'] - h['n_pixels']) <= 0.02 * most:
			same += 1
		# steps with few clear pixels differ more: the edges of the clouds, and a few granules processed twice by
		# ESA, with other SCL classes (S2B_MSIL2A_20240626T105619 of 14:23 in Earth Engine, of 15:18 in Planetary
		# Computer: 5 % and 2 % of clear pixels in Guajares)
		if g['n_pixels'] > 0.3 * most and h['n_pixels'] > 0.3 * most:
			assert abs(g['n_pixels'] - h['n_pixels']) <= 0.02 * most, (case, g, h)
			assert abs(g['value'] - h['value']) <= 0.005 * max(1, abs(g['value'])), (case, g, h)
	assert compared >= 0.6 * len(gee['rows']) and same >= 0.8 * compared, case


@pytest.mark.ee
@pytest.mark.network
@pytest.mark.skipif(not os.environ.get('EE_PROJECT'), reason='EE_PROJECT not set')
def test_map_as_earth_engine(tmp_path, earth_engine):
	from osgeo import gdal
	args = dict(variable='NDVI', sensor='Sentinel-2', start='2022-01-01', end='2022-12-31', metric='median',
	            quality={'cloud_score': None})
	gee = services.download_image(GUAJARES, path=str(tmp_path / 'gee.tif'), **args)
	here = services.download_image(GUAJARES, path=str(tmp_path / 'local.tif'), where='local', **args)
	assert gee['grid'] == here['grid'] and gee['images'] == here['images']
	a, b = (gdal.Open(r['file']).ReadAsArray() for r in (gee, here))
	both = (a != -9999) & (b != -9999)
	assert both.sum() > 0.97 * max((a != -9999).sum(), (b != -9999).sum())
	diff = np.abs(a[both] - b[both])
	assert np.median(diff) < 0.002 and np.percentile(diff, 95) < 0.02
	assert abs(gee['min'] - here['min']) < 0.01 and abs(gee['max'] - here['max']) < 0.01
