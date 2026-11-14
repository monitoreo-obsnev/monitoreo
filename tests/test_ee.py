"""Tests with Earth Engine: run with EE_PROJECT set (pytest -m ee), after `earthengine authenticate`."""

import os

import ee
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
	w, s, e, n = m['bounds']
	assert abs(w + 3.62) < 1e-3 and abs(n - 36.93) < 1e-3
	assert open(m['thumbnail'], 'rb').read(4) == b'\x89PNG'


def test_region_stats():
	res = services.region_stats(GUAJARES, 'NDVI', 'Sentinel-2', '2021-01-01', '2021-12-31')
	row = res['rows'][0]
	assert row['min'] <= row['p50'] <= row['max'] and row['n_pixels'] > 0


def test_protected_areas():
	parks = services.find_protected_areas('Sierra Nevada', 10)
	assert any(p['SITE_ID'] == 389011 for p in parks)


def test_cloud_frequency():
	"""The % of the observations with clouds: between 0 and 100, in MODIS (daily), Sentinel-2 and Landsat."""
	modis = services.time_series(GUAJARES, 'CF', 'Modis', '2023-01-01', '2023-12-31', step='monthly')['rows']
	assert len(modis) == 12 and all(0 <= r['value'] <= 100 and r['n_images'] >= 25 for r in modis)
	assert max(r['value'] for r in modis) > min(r['value'] for r in modis)  # more clouds in winter than in summer
	s2 = services.time_series(GUAJARES, 'CF', 'Sentinel-2', '2023-01-01', '2023-03-31', step='monthly')['rows']
	landsat = services.time_series(GUAJARES, 'CF', 'Landsat', '2023-01-01', '2023-12-31', step='annual')['rows']
	assert all(0 <= r['value'] <= 100 for r in s2 + landsat) and landsat[0]['n_images'] > 10


def test_climate():
	"""Precipitation and temperature of ERA5-Land, TerraClimate and CHIRPS, and WorldClim, in their units."""
	rain = services.time_series(GUAJARES, 'PRECIP', 'ERA5-Land', '2023-01-01', '2023-12-31', step='annual',
	                            metric='sum')['rows'][0]
	assert 100 < rain['value'] < 1500 and rain['n_images'] == 12  # mm in the year
	july = services.time_series(GUAJARES, 'TMAX', 'TerraClimate', '2020-07-01', '2020-07-31', step='monthly')['rows']
	assert 20 < july[0]['value'] < 40  # °C
	chirps = services.time_series(GUAJARES, 'PRECIP', 'CHIRPS', '2023-01-01', '2023-12-31', step='annual',
	                              metric='sum')['rows'][0]
	assert 100 < chirps['value'] < 1500 and chirps['n_images'] > 300  # daily images
	bio = services.region_stats(GUAJARES, 'BIO01', 'WorldClim')['rows'][0]
	assert 5 < bio['mean'] < 20  # °C: the annual mean temperature, scaled from tenths of a degree


def test_only_the_pixels_where():
	"""Conditions on variables (where): fewer pixels, all of them within the limits, in series, statistics, trends
	and comparisons; the fixed layers filter each other; a burn severity keeps only its pixels."""
	high = [{'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 800}]
	elev = services.region_stats(GUAJARES, 'ELEVATION', 'Copernicus', scale=90)['rows'][0]
	only = services.region_stats(GUAJARES, 'ELEVATION', 'Copernicus', scale=90, where=high)['rows'][0]
	assert elev['min'] < 800 <= only['min'] and only['n_pixels'] < elev['n_pixels']
	flat = services.region_stats(GUAJARES, 'SLOPE', 'Copernicus', scale=90,
	                             where=[{'variable': 'SLOPE', 'sensor': 'Copernicus', 'max': 10}])['rows'][0]
	assert flat['max'] <= 10
	full = services.time_series(GUAJARES, 'NDVI', 'Modis', '2021-01-01', '2021-12-31', step='annual')['rows'][0]
	part = services.time_series(GUAJARES, 'NDVI', 'Modis', '2021-01-01', '2021-12-31', step='annual',
	                            where=high)['rows'][0]
	assert 0 < part['n_pixels'] < full['n_pixels']
	green = services.region_stats(GUAJARES, 'NDVI', 'Modis', '2021-01-01', '2021-12-31', metric='mean',
	                              where=[{'variable': 'NDVI', 'sensor': 'Modis', 'min': 0.4}])['rows'][0]
	assert green['min'] >= 0.4 - 1e-6  # the condition is the mean of the period, as this map
	rain = services.region_stats(GUAJARES, 'PRECIP', 'TerraClimate', '2020-01-01', '2020-12-31', metric='sum',
	                             where=[{'variable': 'PRECIP', 'sensor': 'TerraClimate', 'metric': 'sum',
	                                     'min': 0}])['rows'][0]
	assert rain['n_pixels'] > 0
	cmp = services.compare_series(GUAJARES, 'NDVI', 'Modis', '2018-01-01', '2018-12-31', '2020-01-01', '2020-12-31',
	                              step='annual', where=high)
	assert cmp['profile'] and cmp['profile'][0]['reference'] is not None
	with pytest.raises(Exception, match='needs a period'):
		services.region_stats(GUAJARES, 'ELEVATION', 'Copernicus', where=[{'variable': 'NDVI', 'sensor': 'Modis',
		                                                                   'min': 0.3}])


def test_ramsar_sites():
	sites = services.find_protected_areas('Doñana', 10, designation='ramsar')
	assert sites and all('Ramsar' in s['DESIG_ENG'] for s in sites) and any(s['SITE_ID'] == 68175 for s in sites)
	with pytest.raises(ValueError, match='ramsar'):
		services.find_protected_areas('Doñana', 10, designation='unesco')


def test_administrative_units_and_islands():
	units = services.find_admin_units('Granada', level=2, country='ESP')
	granada = next(u for u in units if u['GAUL2_NAME'] == 'Granada')
	assert granada['level'] == 2 and granada['ISO3_CODE'] == 'ESP' and 'Andaluc' in granada['DISP_EN']
	res = services.region_stats({'admin2': granada['GAUL2_CODE']}, 'ELEVATION', 'Copernicus', scale=1000)
	row = res['rows'][0]
	assert row['region'] == granada['DISP_EN'] and 0 <= row['min'] < 100 and 3000 < row['max'] < 3500  # Mulhacén
	assert services.find_admin_units('Andalucía', level=1, country='ESP')[0]['GAUL1_NAME'] == 'Andalucía'
	spain = services.region_stats({'country': 'ESP'}, 'ELEVATION', 'Copernicus', scale=5000)['rows'][0]
	assert spain['region'] == 'Spain' and spain['max'] > 3000
	mallorca = services.region_stats({'island_at': [2.9, 39.6]}, 'ELEVATION', 'Copernicus', scale=1000)['rows'][0]
	assert mallorca['region'] == 'Majorca' and 1000 < mallorca['max'] < 1500


def test_wdpa_region_fetched_once():
	import time
	from monitoreo import areas
	areas._wdpa.clear()
	t = time.time()
	park = areas.region({'wdpa_id': 389011})  # WDPA has it as a geometry collection with 3 lines
	first = time.time() - t
	t = time.time()
	areas.region({'wdpa_id': 389011})
	assert time.time() - t < 0.5 < first
	geom = park.first().geometry()
	assert geom.type().getInfo() == 'MultiPolygon' and park.first().get('name').getInfo() == 'Sierra Nevada'
	assert abs(geom.area(100).getInfo() / 1e6 - 859) < 5


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
	assert res['native_resolution'] == 250 and 0 < res['min'] < res['max'] < 1 and len(res['palette']) > 2
	small = services.download_image(GUAJARES, 'NDVI', 'Sentinel-2', '2021-06-01', '2021-08-31', max_pixels=10000,
	                                path=str(tmp_path / 's2.tif'))
	g = small['grid']
	assert small['resolution'] % 10 == 0 and small['resolution'] > 10 and g['width'] * g['height'] <= 10000


def test_trend_on_a_pixel_as_in_python():
	"""The trend of a pixel (Earth Engine) is that of its yearly values computed in Python."""
	from monitoreo import trends
	spec = services.make_spec('NDVI', 'Modis', '2014-01-01', '2021-12-31', metric='mean')
	pt = ee.Geometry.Point(-3.55, 36.9)
	col = trends.yearly_collection(spec, pt, 250, 'monthly', 7)
	vals = col.getRegion(pt, 250).getInfo()
	head = vals[0]
	years = [r[head.index('t')] for r in vals[1:]]
	values = [r[head.index('value')] for r in vals[1:]]
	img = trends.trend_image(spec, pt, 250, 'monthly', 7)
	got = img.reduceRegion(ee.Reducer.first(), pt, 250).getInfo()
	n, tau, z, p = trends.mann_kendall(years, values)
	slope, intercept = trends.sen(years, values, 2014)
	assert got['n'] == n == 8
	for k, v in (('tau', tau), ('z', z), ('p_value', p), ('slope', slope), ('intercept', intercept)):
		assert abs(got[k] - v) < 1e-4 * max(1, abs(v)), (k, got[k], v)


def test_trend_table_and_maps(tmp_path):
	res = services.trend_table(GUAJARES, 'NDVI', 'Modis', '2014-01-01', '2021-12-31', step='annual',
	                           csv=str(tmp_path / 't.csv'), chart=str(tmp_path / 't.png'))
	(row,) = res['rows']
	assert row['key'] == 'all' and row['n'] == 8 and -1 <= row['tau'] <= 1 and 0 <= row['p_value'] <= 1
	assert len(res['yearly']) == 8 and os.path.getsize(res['csv']) > 0 and os.path.getsize(res['chart']) > 0
	monthly = services.trend_table(GUAJARES, 'NDVI', 'Modis', '2016-01-01', '2021-12-31', step='monthly')
	assert [r['key'] for r in monthly['rows']] == [f'm{m:02d}' for m in range(1, 13)]
	m = services.trend_map(GUAJARES, 'NDVI', 'Modis', '2014-01-01', '2021-12-31', step='monthly', part=7)
	assert '{z}' in m['url'] and m['min'] == -m['max'] and m['unit'].endswith('/ year')
	d = services.download_trend(GUAJARES, 'NDVI', 'Modis', '2014-01-01', '2021-12-31', step='annual',
	                            path=str(tmp_path / 'trend.tif'))
	from osgeo import gdal
	ds = gdal.Open(d['file'])
	assert ds.RasterCount == 6 and ds.GetRasterBand(1).GetDescription() == 'slope'
	n = ds.GetRasterBand(6).ReadAsArray()
	assert n.max() == 8 and d['min'] == -d['max']


def test_comparison(tmp_path):
	res = services.compare_series(GUAJARES, 'NDVI', 'Modis', '2016-01-01', '2018-12-31', '2021-01-01', '2021-12-31',
	                              step='monthly', csv=str(tmp_path / 'c.csv'), chart=str(tmp_path / 'c.png'))
	assert len(res['profile']) == 12 and all(r['n_reference'] == 3 and r['n_other'] == 1 for r in res['profile'])
	r = res['profile'][6]
	assert r['label'] == 'July' and abs(r['difference'] - (r['other'] - r['reference'])) < 1e-12  # tools in English
	assert {x['period'] for x in res['rows']} == {'reference', 'other'} and os.path.getsize(res['chart']) > 0
	m = services.compare_map(GUAJARES, 'NDVI', 'Modis', '2016-01-01', '2018-12-31', '2021-01-01', '2021-12-31')
	assert '{z}' in m['url'] and m['min'] == -m['max']
	d = services.download_comparison(GUAJARES, 'NDVI', 'Modis', '2016-01-01', '2018-12-31', '2021-01-01',
	                                 '2021-12-31', path=str(tmp_path / 'cmp.tif'))
	from osgeo import gdal
	ds = gdal.Open(d['file'])
	b = [ds.GetRasterBand(i).ReadAsArray() for i in (1, 2, 3)]
	ok = (b[0] != -9999) & (b[1] != -9999) & (b[2] != -9999)
	assert ds.GetRasterBand(1).GetDescription() == 'difference' and ok.any()
	assert abs((b[2][ok] - b[1][ok]) - b[0][ok]).max() < 1e-5


def _bands_of(path):
	"""(arrays of the bands, nodata, names) of a GeoTIFF."""
	from osgeo import gdal
	gdal.UseExceptions()
	ds = gdal.Open(path)
	bands = [ds.GetRasterBand(i + 1) for i in range(ds.RasterCount)]
	out = [b.ReadAsArray() for b in bands], bands[0].GetNoDataValue(), [b.GetDescription() for b in bands]
	ds = None
	return out


def test_true_colour_on_the_pixels_of_the_variable(tmp_path):
	"""The true colour of the images of a variable (issue #24): three bands of reflectance on the same grid and the same
	pixels as the map of the variable with the same arguments, and a stretch between its percentiles 2 and 98."""
	args = dict(region=GUAJARES, variable='NDVI', sensor='Sentinel-2', start='2021-06-01', end='2021-08-31',
	            metric='median', max_pixels=40000)
	idx = services.download_image(path=str(tmp_path / 'ndvi.tif'), **args)
	rgb = services.download_rgb(path=str(tmp_path / 'rgb.tif'), **args)
	(value,), nodata, _ = _bands_of(idx['file'])
	colours, nodata_rgb, names = _bands_of(rgb['file'])
	assert names == ['red', 'green', 'blue'] and nodata_rgb == nodata and rgb['grid'] == idx['grid']
	for band in colours:
		assert band.shape == value.shape
		assert ((band == nodata) == (value == nodata)).all()  # the same pixels
		valid = band[band != nodata]
		assert valid.size and -0.05 < valid.mean() < 0.6  # surface reflectance
	assert rgb['images'] == idx['images'] and rgb['bands'] == ['red', 'green', 'blue']
	assert 0 <= rgb['min'] < rgb['max'] < 1 and rgb['unit'] == '[unitless]'
	assert 'tucker' not in str(rgb['references']).lower() and rgb['readme'].endswith('.README.txt')


def test_true_colour_metrics_and_sensors(tmp_path):
	"""The maximum is the colour of the image of the highest NDVI of each pixel; Landsat by years; the SCF (with its
	own masks) and the tiles of the map."""
	box = {'bbox': [-3.58, 36.88, -3.55, 36.90]}
	top = services.download_rgb(box, 'NDVI', 'Sentinel-2', '2021-04-01', '2021-09-30', metric='max',
	                            path=str(tmp_path / 'max.tif'))
	assert 0 <= top['min'] < top['max'] < 1
	landsat = services.download_rgb(box, 'NBR', 'Landsat', '2018-01-01', '2020-12-31', metric='median',
	                                temporal='annual', interannual='mean', path=str(tmp_path / 'landsat.tif'))
	assert landsat['resolution'] == 30 and landsat['min'] < landsat['max']
	scf = services.rgb_map(GUAJARES, 'SCF', 'Landsat', '2020-01-01', '2020-03-31', metric='mean')
	assert '{z}' in scf['url'] and scf['bands'] == ['red', 'green', 'blue'] and scf['min'] < scf['max']
	m = services.rgb_map(GUAJARES, 'NDVI', 'Sentinel-2', '2021-06-01', '2021-08-31', thumbnail=str(tmp_path / 'rgb.png'))
	assert m['url'].startswith('https://') and open(m['thumbnail'], 'rb').read(4) == b'\x89PNG'
	quick = services.rgb_map(GUAJARES, 'NDVI', 'Sentinel-2', '2021-06-01', '2021-08-31', quick=True)
	assert (quick['min'], quick['max']) == (0.0, 0.3)
