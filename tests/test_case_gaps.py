"""The gaps of MonitorEO that the EVEREST case studies found (2026-11-28), without Earth Engine: the snow variables
count their images, the LST of MODIS has a snow filter, the albedo of MODIS keeps its magnitude inversions, the
annual trend can weigh the months the same, and MODIS is reduced on its own grid at its resolution."""
import pytest

from monitoreo import catalog, sensors, services, timeseries, trends, variable


@pytest.mark.parametrize('index, sensor', [('SCF', 'Modis'), ('SCD', 'Sentinel-2'), ('SMOD', 'Landsat')])
def test_the_snow_variables_take_the_metric_count_of_image_count(index, sensor):
	services.make_spec(index, sensor, '2020-01-01', '2020-12-31', metric='count')  # no error
	with pytest.raises(ValueError, match='only takes the metric'):
		services.make_spec(index, sensor, '2020-01-01', '2020-12-31', metric='median')


@pytest.mark.parametrize('col', ['MODIS/061/MOD11A1', 'MODIS/061/MYD11A1'])
def test_the_lst_of_modis_has_a_snow_filter_on_by_default(col):
	for var in ('LST', 'LST_NIGHT'):
		e = variable.entry_of(services.make_spec(var, 'Modis', '2020-01-01', '2020-03-31', collection=col))
		assert 'snow' in sensors.PRODUCTS[sensors.product_of(e)]
		assert sensors.filters(e)['snow'] and not sensors.filters(e, {'snow': False})['snow']


def test_snow_ndsi_of_modis_says_which_filter_it_has():
	with pytest.raises(ValueError, match=r'quality \{"snow": true\}'):
		services.make_spec('NDVI', 'Modis', '2020-01-01', '2020-03-31', quality={'snow_ndsi': 0.4})
	with pytest.raises(ValueError, match='has no snow filter'):
		services.make_spec('ET', 'Modis', '2020-01-01', '2020-03-31', quality={'snow_ndsi': 0.4})


def test_deseasonalized_years_weigh_every_month_the_same():
	# the summer has more images (and values) in a plain mean; here a year with a missing winter month keeps its value
	monthly = []
	for y in range(2010, 2016):
		for m in range(1, 13):
			if y == 2012 and m == 1:
				continue  # a cloudy January: no value
			monthly.append({'region': 'a', 'part': m, 'year': y, 'value': 10.0 * (m in (7, 8)) + 0.5 * (y - 2010),
			                'n_pixels': 4, 'n_images': 3})
	out = {r['year']: r for r in trends.deseasonalized_years(monthly)}
	assert out[2012]['n_months'] == 11 and out[2011]['n_months'] == 12
	steps = [out[y + 1]['value'] - out[y]['value'] for y in range(2010, 2015)]
	# the trend, not the usual value of the missing month (only the climatology of January moves, by 0.05 / 12)
	assert all(abs(s - 0.5) < 0.01 for s in steps)
	assert out[2010]['n_images'] == 36 and out[2010]['n_pixels'] == 4
	few = trends.deseasonalized_years([r for r in monthly if not (r['year'] == 2013 and r['part'] > 3)])
	assert 2013 not in {r['year'] for r in few}  # under half of the months


def test_deseasonalize_is_for_the_annual_step():
	with pytest.raises(ValueError, match="deseasonalize is for step 'annual'"):
		services.trend_table({'bbox': [-3.3, 37.0, -3.2, 37.1]}, 'LST', 'Modis', '2010-01-01', '2020-12-31',
		                     step='monthly', deseasonalize=True)


def test_modis_at_its_resolution_is_reduced_on_its_own_grid():
	lst = services.make_spec('LST', 'Modis', '2020-01-01', '2020-12-31')
	crs, t = timeseries.native_grid(lst, 1000.0)
	assert crs == 'SR-ORG:6974' and t[0] == pytest.approx(926.625433055833) and t[4] == -t[0]
	assert t[2] / t[0] == pytest.approx(-21600) and t[5] / t[0] == pytest.approx(10800)  # whole pixels from the corner
	assert timeseries.native_grid(lst, 2000.0) is None  # a coarser scale: the UTM grid
	ndvi = services.make_spec('NDVI', 'Modis', '2020-01-01', '2020-12-31')
	assert timeseries.native_grid(ndvi, 250.0)[1][0] == pytest.approx(231.656358263958)
	assert timeseries.native_grid(services.make_spec('NDVI', 'Sentinel-2', '2020-01-01', '2020-12-31'), 10.0) is None
	for e in catalog.variables():  # every MODIS product of the catalog has a pixel of the grid
		if e.get('sensor') == 'Modis' and str(e.get('col', '')).startswith('MODIS/') and not e.get('static') \
				and not e.get('two_periods'):
			if e['col'].startswith('MODIS/061/') or e['col'].startswith('MODIS/MOD09GA'):
				spec = services.make_spec(e['index'], 'Modis', '2020-01-01', '2020-12-31', collection=e['col'],
				                          metric=e.get('metric') or 'mean')
				assert timeseries.native_grid(spec, float(e['m'])), (e['index'], e['col'], e['m'])


def test_the_snow_product_of_the_lst_of_modis_is_cited():
	from monitoreo import references
	for col, snow in (('MODIS/061/MOD11A1', 'MOD10A1'), ('MODIS/061/MYD11A1', 'MYD10A1')):
		e = variable.entry_of(services.make_spec('LST', 'Modis', '2020-01-01', '2020-03-31', collection=col))
		ids, _ = references.of_variable(e, {}, ['2020-01-01', '2020-03-31'])
		off, _ = references.of_variable(e, {'snow': False}, ['2020-01-01', '2020-03-31'])
		assert any(snow.lower() in str(i).lower() for i in ids), ids
		assert not any(snow.lower() in str(i).lower() for i in off), off


def test_a_cloudy_day_does_not_end_a_daily_episode():
	import datetime as dt
	from monitoreo import anomalies
	rows = [{'date': (dt.date(2022, 7, 1) + dt.timedelta(days=k)).isoformat(), 'z': z}
	        for k, z in enumerate([2.0, None, 2.5, 2.1, None, None, None, 1.8])]
	eps = anomalies._episodes(rows, 1.5, 'daily')
	assert [(e['start'], e['steps']) for e in eps] == [('2022-07-01', 3), ('2022-07-08', 1)]  # 3 cloudy days end it


def test_every_recipe_of_the_package_is_valid():
	# a SKILL.md that does not parse (e.g. ': ' in an unquoted description) leaves the catalog without saying so
	import os
	from monitoreo import skills
	folders = {d for d in os.listdir(skills.FOLDER) if os.path.isfile(os.path.join(skills.FOLDER, d, 'SKILL.md'))}
	assert {r['name'] for r in skills.catalog()} == folders
