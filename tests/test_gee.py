"""The app of the Earth Engine Code Editor (gee/core.js) against this package: the same cases, computed by both, must
give the same values. Needs Earth Engine (EE_PROJECT, pytest -m ee) and Node with the packages of gee/package.json
(npm install in gee)."""

import json
import math
import os
import shutil
import subprocess

import ee
import pytest

from monitoreo import areas, maps, services, trends
from monitoreo import variable as variables

GEE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gee')

pytestmark = [pytest.mark.ee, pytest.mark.skipif(not os.environ.get('EE_PROJECT'), reason='EE_PROJECT not set'),
              pytest.mark.skipif(not shutil.which('node') or not os.path.isdir(os.path.join(GEE, 'node_modules')),
                                 reason='no Node, or no npm install in gee')]

GUAJARES = {'bbox': [-3.62, 36.86, -3.50, 36.93]}  # a small box in Granada, Spain
TWO = {'geojson': {'type': 'FeatureCollection', 'features': [
	{'type': 'Feature', 'properties': {'name': 'west'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[-3.62, 36.86], [-3.56, 36.86], [-3.56, 36.93], [-3.62, 36.93], [-3.62, 36.86]]]}},
	{'type': 'Feature', 'properties': {'name': 'east'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[-3.56, 36.86], [-3.50, 36.86], [-3.50, 36.93], [-3.56, 36.93], [-3.56, 36.86]]]}},
]}}
SIERRA_BERMEJA = {'bbox': [-5.23, 36.47, -5.10, 36.57]}  # fire of September 2021
LAGUNAS = {'bbox': [-3.40, 37.03, -3.33, 37.07]}  # the glacial lakes of Sierra Nevada, below the Mulhacén

ABOVE_800 = {'variable': 'ELEVATION', 'sensor': 'Copernicus', 'ref': 106, 'min': 800}  # where: the app takes the ref
FLAT = {'variable': 'SLOPE', 'sensor': 'Copernicus', 'ref': 107, 'max': 20}
GREEN = {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'ref': 27, 'min': 0.3}

CASES = {
	# only the pixels of the region that pass conditions on variables (where): fixed layers and one with dates
	'series_s2_where_elevation': {'kind': 'series', 'region': GUAJARES, 'step': 'monthly', 'metric': 'mean',
	                              'stat': 'mean', 'spec': {'ref': 27, 'period': ['2021-05-01', '2021-07-31'],
	                                                       'where': [ABOVE_800]}},
	'map_s2_where_ndvi_and_slope': {'kind': 'percentiles', 'region': GUAJARES,
	                                'spec': {'ref': 27, 'period': ['2021-01-01', '2021-12-31'], 'metric': 'median',
	                                         'where': [GREEN, FLAT]}},
	'compare_modis_where_ndvi': {'kind': 'compare', 'region': GUAJARES, 'step': 'monthly', 'metric': 'mean',
	                             'stat': 'mean', 'spec': {'ref': 25, 'period': ['2018-01-01', '2018-12-31'],
	                                                      'where': [dict(GREEN, sensor='Modis', ref=25)]},
	                             'other': ['2020-01-01', '2020-12-31']},
	'map_elevation_where_slope': {'kind': 'percentiles', 'region': GUAJARES, 'spec': {'ref': 106, 'where': [FLAT]}},
	# cloud frequency (CF) of MODIS Terra, Sentinel-2 and Landsat; precipitation of ERA5-Land; WorldClim (an image)
	'series_cf_modis': {'kind': 'series', 'region': GUAJARES, 'step': 'monthly', 'metric': 'mean', 'stat': 'mean',
	                    'spec': {'ref': 108, 'period': ['2023-01-01', '2023-03-31']}},
	'series_cf_s2': {'kind': 'series', 'region': GUAJARES, 'step': 'monthly', 'metric': 'mean', 'stat': 'mean',
	                 'spec': {'ref': 110, 'period': ['2023-01-01', '2023-02-28']}},
	'series_cf_landsat': {'kind': 'series', 'region': GUAJARES, 'step': 'annual', 'metric': 'mean', 'stat': 'mean',
	                      'spec': {'ref': 111, 'period': ['2023-01-01', '2023-12-31']}},
	'series_precip_era5': {'kind': 'series', 'region': GUAJARES, 'step': 'annual', 'metric': 'sum', 'stat': 'mean',
	                       'spec': {'ref': 112, 'period': ['2023-01-01', '2023-12-31']}},
	'map_bio01_worldclim': {'kind': 'percentiles', 'region': GUAJARES, 'spec': {'ref': 125}},
	'series_s2_monthly': {'kind': 'series', 'region': GUAJARES, 'step': 'monthly', 'metric': 'mean', 'stat': 'mean',
	                      'spec': {'ref': 27, 'period': ['2021-05-01', '2021-07-31']}},
	'series_landsat_two_regions': {'kind': 'series', 'region': TWO, 'step': 'annual', 'metric': 'max', 'stat': 'median',
	                               'spec': {'ref': 14, 'period': ['2020-01-01', '2021-12-31']}},
	'series_modis_snow_season': {'kind': 'series', 'region': GUAJARES, 'step': '16-day', 'metric': 'max', 'stat': 'p90',
	                             'spec': {'ref': 6, 'period': ['2019-11-01', '2021-02-28'], 'season': ['11-01', '02-28'],
	                                      'quality': {'snow': False}}},
	'series_s2_daily_scl': {'kind': 'series', 'region': GUAJARES, 'step': 'daily', 'metric': 'mean', 'stat': 'mean',
	                        'spec': {'ref': 10, 'period': ['2022-03-01', '2022-03-31'],
	                                 'quality': {'cloud_score': None, 'water': False}}},
	'series_wdpa_modis': {'kind': 'series', 'region': {'wdpa_id': 389011}, 'step': 'annual', 'metric': 'mean',
	                      'stat': 'mean', 'spec': {'ref': 25, 'period': ['2018-01-01', '2020-12-31']}},
	'trends_modis_monthly': {'kind': 'trends', 'region': GUAJARES, 'step': 'monthly', 'metric': 'mean', 'stat': 'mean',
	                         'spec': {'ref': 21, 'period': ['2010-01-01', '2020-12-31']}},
	'compare_modis_monthly': {'kind': 'compare', 'region': GUAJARES, 'step': 'monthly', 'metric': 'mean',
	                          'stat': 'mean', 'spec': {'ref': 25, 'period': ['2018-01-01', '2018-12-31']},
	                          'other': ['2020-01-01', '2020-12-31']},
	'map_s2_median': {'kind': 'percentiles', 'region': GUAJARES,
	                  'spec': {'ref': 27, 'period': ['2021-01-01', '2021-12-31'], 'metric': 'median'}},
	'map_landsat_annual': {'kind': 'percentiles', 'region': GUAJARES,
	                       'spec': {'ref': 24, 'period': ['2015-01-01', '2020-12-31'], 'metric': 'max',
	                                'temporal': 'annual', 'interannual': 'median'}},
	'map_landsat_albedo': {'kind': 'percentiles', 'region': GUAJARES,
	                       'spec': {'ref': 11, 'period': ['2002-01-01', '2003-12-31'], 'metric': 'p25'}},
	'map_modis_lst_monthly': {'kind': 'percentiles', 'region': GUAJARES,
	                          'spec': {'ref': 15, 'period': ['2019-01-01', '2020-12-31'], 'metric': 'p90',
	                                   'temporal': 'monthly', 'interannual': 'mean'}},
	'map_modis_lai_16day': {'kind': 'percentiles', 'region': GUAJARES,
	                        'spec': {'ref': 32, 'period': ['2020-03-01', '2020-10-31'], 'metric': 'mean',
	                                 'temporal': '16-day', 'interannual': 'max', 'season': ['03-01', '10-31']}},
	'map_difference': {'kind': 'percentiles', 'region': GUAJARES, 'difference': ['2020-01-01', '2022-12-31'],
	                   'spec': {'ref': 21, 'period': ['2005-01-01', '2007-12-31'], 'metric': 'median'}},
	'trend_map_july': {'kind': 'trend_image', 'region': GUAJARES, 'step': 'monthly', 'part': 7, 'metric': 'mean',
	                   'spec': {'ref': 25, 'period': ['2005-01-01', '2020-12-31']}},
	'burn_severity': {'kind': 'burn', 'region': SIERRA_BERMEJA, 'after': ['2021-09-20', '2021-10-31'],
	                  'spec': {'ref': 102, 'period': ['2021-07-15', '2021-08-31'], 'metric': 'median'}},
	'burn_rbr': {'kind': 'burn_rbr', 'region': SIERRA_BERMEJA, 'after': ['2021-09-20', '2021-10-31'],
	             'spec': {'ref': 103, 'period': ['2021-07-15', '2021-08-31'], 'metric': 'median'}},
	# the RdNBR of Miller & Thode 2007 with its classes: Sentinel-2 (144, B8 and B12) and the daily surface reflectance
	# of MODIS Terra (146, MOD09GA, the default collection) and Aqua (147, MYD09GA, given as collection), 500 m
	'burn_rdnbr': {'kind': 'burn_rdnbr', 'region': SIERRA_BERMEJA, 'after': ['2021-09-20', '2021-10-31'],
	               'sensor': 'Sentinel-2',
	               'spec': {'ref': 144, 'period': ['2021-07-15', '2021-08-31'], 'metric': 'median'}},
	'burn_rdnbr_modis_terra': {'kind': 'burn_rdnbr', 'region': SIERRA_BERMEJA, 'after': ['2021-09-20', '2021-10-31'],
	                           'sensor': 'Modis',
	                           'spec': {'ref': 146, 'period': ['2021-07-15', '2021-08-31'], 'metric': 'median'}},
	'burn_rdnbr_modis_aqua': {'kind': 'burn_rdnbr', 'region': SIERRA_BERMEJA, 'after': ['2021-09-20', '2021-10-31'],
	                          'sensor': 'Modis', 'collection': 'MODIS/061/MYD09GA',
	                          'spec': {'ref': 147, 'period': ['2021-07-15', '2021-08-31'], 'metric': 'median'}},
	# snow cover frequency: Landsat 8 and 9 in winter (shadow of the relief) and Landsat 5 (TOA bands B2 and B5)
	'series_scf_winter': {'kind': 'series', 'region': LAGUNAS, 'step': 'monthly', 'metric': 'mean', 'stat': 'mean',
	                      'spec': {'ref': 105, 'period': ['2021-11-01', '2022-03-31']}},
	'map_scf_seasons': {'kind': 'percentiles', 'region': LAGUNAS,
	                    'spec': {'ref': 105, 'period': ['2008-10-01', '2011-05-31'], 'metric': 'mean',
	                             'temporal': 'annual', 'interannual': 'mean', 'season': ['10-01', '05-31']}},
	# the true colour of the images of a variable (rgb_map): the percentiles 2 and 98 of its bands red, green and blue
	'rgb_s2_median': {'kind': 'rgb_percentiles', 'region': GUAJARES,
	                  'spec': {'ref': 27, 'period': ['2021-06-01', '2021-08-31'], 'metric': 'median'}},
	'rgb_landsat_annual': {'kind': 'rgb_percentiles', 'region': GUAJARES,
	                       'spec': {'ref': 24, 'period': ['2019-01-01', '2020-12-31'], 'metric': 'median',
	                                'temporal': 'annual', 'interannual': 'mean', 'quality': {'snow': False}}},
	'rgb_scf_mean': {'kind': 'rgb_percentiles', 'region': LAGUNAS,
	                 'spec': {'ref': 105, 'period': ['2021-11-01', '2022-03-31'], 'metric': 'mean'}},
	'rgb_s2_ndvi_max': {'kind': 'rgb_percentiles', 'region': GUAJARES,  # the colours of the date of the highest NDVI
	                    'spec': {'ref': 27, 'period': ['2021-06-01', '2021-08-31'], 'metric': 'max'}},
	'rgb_cf_modis': {'kind': 'rgb_percentiles', 'region': GUAJARES,
	                 'spec': {'ref': 108, 'period': ['2023-01-01', '2023-01-31'], 'metric': 'mean'}},
	# data of Earth Engine outside the catalog, by their ID (custom: collection= or image=, band=, band_scale=, unit=):
	# the precipitation of TerraClimate (images with dates, a monthly series) and the mean annual temperature of
	# WorldClim 1.4 (a fixed image, stored in tenths of a degree: the statistics of its map)
	'series_custom_terraclimate': {'kind': 'series', 'region': GUAJARES, 'step': 'monthly', 'metric': 'mean',
	                               'stat': 'mean',
	                               'spec': {'custom': {'asset': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr',
	                                                   'use': 'collection', 'unit': 'mm'},
	                                        'period': ['2020-01-01', '2020-12-31']}},
	'map_custom_worldclim_bio01': {'kind': 'percentiles', 'region': GUAJARES,
	                               'spec': {'custom': {'asset': 'WORLDCLIM/V1/BIO', 'band': 'bio01', 'use': 'image',
	                                                   'scale': 0.1, 'unit': 'degC'}}},
	# the slope of the Copernicus DEM, a collection of tiles given as an image: the mosaic of its tiles, in degrees
	'map_custom_dem_slope': {'kind': 'percentiles', 'region': GUAJARES,
	                         'spec': {'custom': {'asset': 'COPERNICUS/DEM/GLO30', 'band': 'DEM', 'use': 'image',
	                                             'terrain': 'slope'}}},
}


def _spec_args(s):
	"""The arguments of the services for the spec S of a case: a variable of the catalog (ref) or, with custom, data of
	Earth Engine by its ID (collection or image, band, band_scale, band_offset, unit, terrain)."""
	out = {'metric': s.get('metric', 'mean'), 'season': s.get('season'), 'quality': s.get('quality'),
	       'where': s.get('where')}
	c = s.get('custom')
	if c:
		out.update({c['use']: c['asset'], 'band': c['band'], 'band_scale': c.get('scale'),
		            'band_offset': c.get('offset'), 'unit': c.get('unit'), 'terrain': c.get('terrain')})
	else:
		out['ref'] = s['ref']
	return out


def python(c):
	"""The result of the case C with this package."""
	s, region = c['spec'], c['region']
	start, end = s.get('period') or (None, None)  # none for the fixed layers (WorldClim, elevation)
	# the dates by their names (as the tools that need them take them: keyword-only in the MCP server)
	if c['kind'] == 'series':
		out = services.time_series(region, start=start, end=end, step=c['step'], stat=c['stat'],
		                           **dict(_spec_args(s), metric=c['metric']))
		return {'rows': out['rows'], 'scale': out['scale']}
	if c['kind'] == 'trends':
		out = services.trend_table(region, start=start, end=end, step=c['step'], stat=c['stat'],
		                           **dict(_spec_args(s), metric=c['metric']))
		return {'rows': out['rows'], 'yearly': out['yearly']}
	if c['kind'] == 'compare':
		out = services.compare_series(region, start=start, end=end, other_start=c['other'][0],
		                              other_end=c['other'][1], step=c['step'], stat=c['stat'],
		                              **dict(_spec_args(s), metric=c['metric']))
		return {'profile': out['profile']}
	if c['kind'] == 'burn':
		out = services.burn_severity(region, 'Sentinel-2', start=start, end=end, other_start=c['after'][0],
		                             other_end=c['after'][1])
		return {'classes': out['classes']}
	if c['kind'] == 'burn_rbr':
		out = services.burn_severity(region, 'Sentinel-2', start=start, end=end, other_start=c['after'][0],
		                             other_end=c['after'][1], index='RBR')
		return {'stats': out['stats']}
	if c['kind'] == 'burn_rdnbr':
		out = services.burn_severity(region, c['sensor'], start=start, end=end, other_start=c['after'][0],
		                             other_end=c['after'][1], index='RdNBR', collection=c.get('collection'))
		return {'classes': out['classes'], 'burned_ha': out['burned_ha'], 'stats': out['stats']}
	args = _spec_args(s)
	spec = services.make_spec(start=start, end=end, temporal=s.get('temporal', 'period'),
	                          interannual=s.get('interannual', 'mean'), **args)
	regions = areas.region(region)
	geom = regions.geometry()
	native = variables.native_scale(spec)
	if c['kind'] == 'trend_image':
		img = trends.trend_image(spec, geom, native, c['step'], c['part'], c['metric'])
		return img.reduceRegion(ee.Reducer.mean(), geom, native, bestEffort=True).getInfo()
	if c['kind'] == 'rgb_percentiles':
		img = variables.image(spec, geom, native, rgb=True).clipToCollection(regions)
		return img.reduceRegion(ee.Reducer.percentile(list(maps.RGB_STRETCH)), geom, native, bestEffort=True,
		                        maxPixels=int(1e6), tileScale=4).getInfo()  # as maps.rgb_vis
	if c.get('difference'):
		img = services._comparison(region, None, None, start, end, c['difference'][0], c['difference'][1],
		                           args['metric'], s.get('temporal', 'period'), s.get('interannual', 'mean'),
		                           args['season'], args['quality'], None,
		                           {'ref': s['ref'], 'where': s.get('where')})[2].select('difference')
	else:
		img = variables.image(spec, geom, native).clipToCollection(regions)
	return img.rename('value').reduceRegion(ee.Reducer.percentile([5, 95]), geom, native, bestEffort=True,
	                                        maxPixels=int(1e6)).getInfo()


def same(py, js, where='result'):
	"""Assert that the values of JS (the app) are those of PY (the package)."""
	if isinstance(js, dict):
		assert isinstance(py, dict), where
		for k, v in js.items():
			assert k in py, f'{where}: {k} only in the app'
			same(py[k], v, f'{where}.{k}')
	elif isinstance(js, list):
		assert isinstance(py, list) and len(py) == len(js), f'{where}: {len(py)} rows in Python, {len(js)} in the app'
		for i, (a, b) in enumerate(zip(py, js)):
			same(a, b, f'{where}[{i}]')
	elif isinstance(js, (int, float)) and not isinstance(js, bool) and py is not None:
		assert math.isclose(py, js, rel_tol=1e-6, abs_tol=1e-9), f'{where}: {py} in Python, {js} in the app'
	else:
		assert py == js, f'{where}: {py!r} in Python, {js!r} in the app'


@pytest.fixture(scope='module')
def app():
	"""The results of all the cases with the app (gee/parity.js)."""
	import google.auth.transport.requests

	project = services.init()
	credentials = ee.data.get_persistent_credentials()
	credentials.refresh(google.auth.transport.requests.Request())
	env = dict(os.environ, EE_ACCESS_TOKEN=credentials.token, EE_PROJECT=project)
	run = subprocess.run(['node', 'parity.js'], input=json.dumps(CASES), capture_output=True, text=True, cwd=GEE,
	                     env=env, timeout=1800)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout)


@pytest.mark.parametrize('name', sorted(CASES))
def test_same_as_python(app, name):
	js = app[name]
	assert 'error' not in js, js.get('error')
	same(python(CASES[name]), js, name)
