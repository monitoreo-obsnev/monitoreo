"""The seasonal profile by day of the year (time_series with doy and interannual or other_variable): for each step of
the year (each month, 16-day period or calendar day) the metric between the years that the user chooses of its values,
a line per variable, e.g. the NDSI and the NDVI on two y axes, each from the values of its own variable. Without
Earth Engine: the series of each variable come from a fake timeseries.series, and every error comes before it."""

import csv
import datetime as dt
import math
import statistics

import pytest

from monitoreo import catalog, references, readme, report, services, timeseries

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
VALUES = [0.3, -0.2, 0.7, 0.1, 0.45]


# The metric between the years -------------------------------------------------------------------------------------

def test_the_metrics_between_the_years():
	np = pytest.importorskip('numpy')
	xs = VALUES + [None]  # the None left out
	assert timeseries.over_years(xs, 'mean') == pytest.approx(sum(VALUES) / 5)
	assert timeseries.over_years(xs, 'Median') == 0.3
	assert timeseries.over_years([4, 1, 3, 2], 'median') == 2.5  # the mean of the two middle values
	assert timeseries.over_years(xs, 'min') == -0.2 and timeseries.over_years(xs, 'max') == 0.7
	assert timeseries.over_years(xs, 'std') == pytest.approx(statistics.stdev(VALUES))  # sample: n - 1
	assert timeseries.over_years(xs, 'cv') == pytest.approx(100 * statistics.stdev(VALUES) / abs(statistics.mean(VALUES)))
	negative = [-0.4, -0.2, -0.3]
	assert timeseries.over_years(negative, 'cv') == pytest.approx(100 * statistics.stdev(negative) / 0.3)  # |mean|
	for p in (0, 5, 25, 50, 62.5, 75, 90, 100):
		assert timeseries.over_years(xs, f'p{p:g}') == pytest.approx(float(np.percentile(VALUES, p)))
	assert timeseries.over_years([0.2, 0.4], 'p25') == pytest.approx(0.25)
	assert timeseries.over_years([7], 'p90') == 7 and timeseries.over_years([7], 'median') == 7


def test_the_metrics_without_enough_years():
	for m in ('mean', 'median', 'min', 'max', 'std', 'cv', 'p25'):
		assert timeseries.over_years([], m) is None and timeseries.over_years([None, None], m) is None
	assert timeseries.over_years([0.5], 'std') is None and timeseries.over_years([0.5], 'cv') is None
	assert timeseries.over_years([-1, 1], 'cv') is None  # a mean of 0
	assert timeseries.over_years([0.5], 'mean') == 0.5


def test_the_metric_between_the_years_is_checked():
	assert timeseries.check_interannual(' Median ') == 'median' and timeseries.check_interannual('P25') == 'p25'
	assert timeseries.check_interannual('p100') == 'p100' and timeseries.check_interannual('p2.5') == 'p2.5'
	for bad in ('sum', 'count', 'mode', 'p101', 'variance', '', None):
		with pytest.raises(ValueError, match='unknown metric between the years'):
			timeseries.check_interannual(bad)
	with pytest.raises(ValueError, match='unknown metric between the years'):
		timeseries.over_years([1, 2], 'sum')


# The steps of the year --------------------------------------------------------------------------------------------

def _row(date, value, region='park', **more):
	return dict({'region': region, 'date': date, 'value': value, 'n_pixels': 5, 'n_images': 1}, **more)


def _spec(start, end, season=None):
	return {'period': [start, end], 'season': season}


def test_the_profile_by_month():
	rows = timeseries.with_doy([_row(f'{y}-{m:02d}-01', None if (y, m) == (2023, 2) or m == 12 else y - 2020 + m / 10)
	                            for y in (2021, 2022, 2023, 2024) for m in range(1, 13)])
	profile = timeseries.doy_profile(rows, _spec('2021-01-01', '2024-12-31'), 'monthly', 'median', 'NDVI Sentinel-2')
	assert [r['part'] for r in profile] == [str(m) for m in range(1, 13)]
	assert [r['label'] for r in profile] == timeseries.MONTH_ABBR
	assert list(profile[0]) == timeseries.PROFILE_COLUMNS
	jan, feb, mar, dec = profile[0], profile[1], profile[2], profile[11]
	assert jan == {'region': 'park', 'variable': 'NDVI Sentinel-2', 'part': '1', 'doy': 1, 'label': 'Jan',
	               'value': pytest.approx(2.6), 'n_years': 4}  # the median of 1.1, 2.1, 3.1 and 4.1
	assert feb['n_years'] == 3 and feb['value'] == pytest.approx(2.2)  # 2023 without a value
	assert mar['doy'] == 60  # 1 March: day 60 in three years, 61 in 2024
	assert dec['value'] is None and dec['n_years'] == 0 and dec['doy'] == 335  # kept, without a value


def test_the_rounding_of_the_day_of_the_year():
	# 1 March of 2023 (day 60) and 2024 (day 61): the median 60.5 is drawn on day 61 (.5 up, as Math.round)
	rows = timeseries.with_doy([_row('2023-03-01', 1.0), _row('2024-03-01', 2.0)])
	assert timeseries.doy_profile(rows, None, 'monthly', 'mean', 'x')[0]['doy'] == 61


def test_the_profile_by_16_days():
	spec = _spec('2023-01-01', '2024-12-31')
	rows = timeseries.with_doy([_row(a, float(i % 23)) for i, (a, _) in enumerate(timeseries.bins(spec, '16-day'))])
	profile = timeseries.doy_profile(rows, spec, '16-day', 'mean', 'NDSI')
	assert [r['part'] for r in profile] == [str(i) for i in range(23)]
	assert [(r['doy'], r['label']) for r in profile[:3]] == [(1, 'Jan 1'), (17, 'Jan 17'), (33, 'Feb 2')]
	assert profile[-1]['doy'] == 353 and profile[-1]['label'] == 'Dec 19'
	assert all(r['n_years'] == 2 and r['value'] == float(r['part']) for r in profile)


def test_the_16_day_periods_of_a_period_that_starts_later():
	"""The 16-day periods are counted from 1 January, also in the first year of a period that starts later (its steps
	start on its first day): its 10 March is in the period of 6 March, the fifth one (4)."""
	spec = _spec('2022-03-10', '2024-12-31')
	rows = timeseries.with_doy([_row(a, 1.0) for a, _ in timeseries.bins(spec, '16-day')])
	assert rows[0]['date'] == '2022-03-10'
	profile = timeseries.doy_profile(rows, spec, '16-day', 'mean', 'x')
	part = {r['part']: r for r in profile}
	assert part['4']['n_years'] == 3 and part['0']['n_years'] == 2  # 2022 has no 1 January
	assert part['4']['doy'] == 65  # 6 March in 2023 (65) and 5 March in 2024 (65), 10 March in 2022 (69)


def test_the_16_day_periods_of_a_season_across_the_new_year():
	"""With a season, the 16-day periods start on its first day in each year (1 November), and those of January are
	in the season of the year before."""
	spec = _spec('2021-01-01', '2024-03-31', ['11-01', '02-28'])
	bins = timeseries.bins(spec, '16-day')
	rows = timeseries.with_doy([_row(a, 1.0 + i) for i, (a, _) in enumerate(bins)])
	profile = timeseries.doy_profile(rows, spec, '16-day', 'max', 'x')
	part = {r['part']: r for r in profile}
	assert part['0']['label'] == 'Nov 1' and part['0']['n_years'] == 3  # 2021, 2022 and 2023
	assert part['4']['label'] == 'Jan 4'  # 1 November + 64 days
	assert part['4']['n_years'] == 4  # also January 2021, in the season of 2020
	assert [r['part'] for r in profile][:4] == ['4', '5', '6', '7']  # by day of the year: January first
	assert int(profile[-1]['part']) == 3 and profile[-1]['doy'] >= 340


def test_the_16_day_periods_of_a_season_from_a_period_that_starts_inside_it():
	"""A period from 1 January with a season from 1 November: the steps of its first, partial, season start on 1
	January, and go with the closest period of the other years (1 January with 4 January, 17 January with 20 January),
	drawn on the days of those periods, not on the median of 1 January and 19 December (June)."""
	spec = _spec('2018-01-01', '2019-03-31', ('11-01', '03-31'))
	rows = timeseries.with_doy([_row(a, 1.0) for a, _ in timeseries.bins(spec, '16-day')])
	profile = timeseries.doy_profile(rows, spec, '16-day', 'median', 'x')
	part = {r['part']: r for r in profile}
	assert (part['3']['doy'], part['3']['label'], part['3']['n_years']) == (353, 'Dec 19', 1)  # only 2018
	assert (part['4']['doy'], part['4']['label'], part['4']['n_years']) == (4, 'Jan 4', 2)  # 1 and 4 January
	assert (part['5']['label'], part['5']['n_years']) == ('Jan 20', 2)  # 17 and 20 January
	assert all(r['doy'] < 100 or r['doy'] > 300 for r in profile)  # nothing in summer
	assert max(int(p) for p in part) == 9  # 25 March: none after the last period of the season


def test_a_monthly_profile_of_a_season_that_starts_and_ends_in_the_same_month():
	"""A hydrological year from 15 October to 14 October: the two parts of October of each window apart, each with a
	value per year."""
	spec = _spec('2019-10-15', '2022-10-14', ('10-15', '10-14'))
	rows = timeseries.with_doy([_row(a, 1.0 if a[8:] == '15' else 0.0) for a, _ in timeseries.bins(spec, 'monthly')])
	profile = timeseries.doy_profile(rows, spec, 'monthly', 'mean', 'NDVI')
	october = [(r['part'], r['label'], r['value'], r['n_years']) for r in profile if r['label'].startswith('Oct')]
	assert october == [('10', 'Oct 1-14', 0.0, 3), ('10-15', 'Oct 15-31', 1.0, 3)]
	assert len(profile) == 13 and all(r['n_years'] == 3 for r in profile)


def test_the_features_of_the_same_name_stay_apart():
	"""Two features named Sierra Nevada (WDPA has several designations of that name): the second numbered, as the
	viewer names it, each with a value per year."""
	rows = timeseries.with_doy([_row(f'{y}-{m:02d}-01', v + (y - 2021) / 100, 'Sierra Nevada')
	                            for y in (2021, 2022, 2023) for m in (1, 2) for v in (0.3, 0.7)])
	profile = timeseries.doy_profile(rows, None, 'monthly', 'median', 'NDVI')
	assert [(r['region'], r['part'], r['value'], r['n_years']) for r in profile] == [
		('Sierra Nevada', '1', pytest.approx(0.31), 3), ('Sierra Nevada', '2', pytest.approx(0.31), 3),
		('Sierra Nevada (2)', '1', pytest.approx(0.71), 3), ('Sierra Nevada (2)', '2', pytest.approx(0.71), 3)]


def test_the_profile_by_day():
	rows = timeseries.with_doy([_row(d, v) for d, v in (('2023-02-28', 1.0), ('2023-03-01', 2.0), ('2024-02-28', 3.0),
	                                                    ('2024-02-29', 4.0), ('2024-03-01', 5.0), ('2022-03-01', 6.0))])
	profile = timeseries.doy_profile(rows, None, 'daily', 'p50', 'x')
	# the days of the calendar days in a leap year: 29 February and 1 March apart
	assert [(r['part'], r['doy'], r['label'], r['value'], r['n_years']) for r in profile] == [
		('02-28', 59, 'Feb 28', 2.0, 2), ('02-29', 60, 'Feb 29', 4.0, 1), ('03-01', 61, 'Mar 1', 5.0, 3)]
	last = timeseries.doy_profile(timeseries.with_doy([_row('2023-12-31', 1.0)]), None, 'daily', 'mean', 'x')
	assert last[0]['doy'] == 366 and last[0]['label'] == 'Dec 31'


def test_a_daily_profile_with_a_29_february_without_a_value(figure, tmp_path):
	from monitoreo import charts
	"""The 29 February without a value of a leap year among common years: its own step, drawn apart from 1 March,
	and the chart of the profile does not compare the values of the steps of the same day (it raised a TypeError)."""
	rows = timeseries.with_doy([_row(f'{y}-{md}', None if (y, md) == (2020, '02-29') else 0.5)
	                            for y in (2019, 2020, 2021) for md in ('02-28', '02-29', '03-01', '03-02')
	                            if md != '02-29' or y == 2020])
	profile = timeseries.doy_profile(rows, None, 'daily', 'median', 'NDSI Modis')
	assert [(r['part'], r['doy'], r['value'], r['n_years']) for r in profile] == [
		('02-28', 59, 0.5, 3), ('02-29', 60, None, 0), ('03-01', 61, 0.5, 3), ('03-02', 62, 0.5, 3)]
	# two steps on one day, one of them without a value (as 29 February and 1 March were): by day only
	charts.doy_profile_png(profile + [dict(profile[2], doy=60)], str(tmp_path / 'p.png'), 'x', 'NDSI')
	assert (tmp_path / 'p.png').stat().st_size > 1000 and len(figure) == 1


def test_the_order_of_the_profile_and_its_errors():
	ndsi, ndvi = 'NDSI Sentinel-2', 'NDVI Sentinel-2'
	rows = [_row('2023-01-01', 1.0, 'b', variable=ndsi), _row('2023-02-01', 2.0, 'b', variable=ndsi),
	        _row('2023-01-01', 3.0, 'a', variable=ndsi),
	        _row('2023-01-01', 4.0, 'a', variable=ndvi), _row('2023-01-01', 5.0, 'b', variable=ndvi)]
	profile = timeseries.doy_profile(rows, None, 'monthly', 'mean')
	assert [(r['region'], r['variable'], r['part']) for r in profile] == [
		('a', 'NDSI Sentinel-2', '1'), ('a', 'NDVI Sentinel-2', '1'), ('b', 'NDSI Sentinel-2', '1'),
		('b', 'NDSI Sentinel-2', '2'), ('b', 'NDVI Sentinel-2', '1')]
	with pytest.raises(ValueError, match='step shorter than a year'):
		timeseries.doy_profile(rows, None, 'annual', 'mean')
	with pytest.raises(ValueError, match='unknown metric between the years'):
		timeseries.doy_profile(rows, None, 'monthly', 'sum')


def test_a_range_of_the_y_axis_is_checked():
	assert services.check_ylim([-1, 1]) == (-1.0, 1.0) and services.check_ylim((0, '0.5')) == (0.0, 0.5)
	assert services.check_ylim('-0.2, 1') == (-0.2, 1.0) and services.check_ylim('[-1 1]') == (-1.0, 1.0)
	for none in (None, '', [], ()):
		assert services.check_ylim(none) is None
	for bad in ([1, -1], [1, 1], [1], [1, 2, 3], 'a b', [True, 2], [float('nan'), 1], 5, {'min': 0, 'max': 1}):
		with pytest.raises(ValueError, match='other_ylim'):
			services.check_ylim(bad, 'other_ylim')


def test_no_default_range_of_the_y_axes():
	"""Each y axis goes from the values of its own variable unless a range is given: no default range by variable."""
	for name in ('SPECTRAL_INDICES', 'INDEX_RANGE', 'SCALE_METRICS', 'index_ylim'):
		assert not hasattr(catalog, name), name
	assert not hasattr(services, '_default_ylim')


# time_series ------------------------------------------------------------------------------------------------------

def _value(spec, day):
	"""A value of the fake series: the NDSI in winter, the NDVI in summer (and the CF and the NDSI of MODIS, in %)."""
	index = spec.get('index') or 'data'
	winter = math.cos(2 * math.pi * (day.month - 1) / 12)
	base = {'NDSI': winter / 2, 'NDVI': 0.3 - winter / 4}
	v = base.get(index, 0.1 * day.month) + (day.year - 2021) / 100
	return v * 100 if spec.get('sensor') == 'Modis' and index == 'NDSI' else v


@pytest.fixture
def ee(monkeypatch):
	"""time_series without Earth Engine: the series of each variable (its calls in 'specs') with a row per step and
	region (park and buffer), the scale of its sensor (10 m of Sentinel-2, 500 m of MODIS) if none is given."""
	calls = []

	def series(spec, regions, step='monthly', metric='mean', stat='mean', scale=None, progress=None, steps=None):
		calls.append({'spec': spec, 'step': step, 'metric': metric, 'stat': stat, 'scale': scale})
		if step == 'daily':
			days = [dt.date(y, m, d) for y in range(int(spec['period'][0][:4]), int(spec['period'][1][:4]) + 1)
			        for m, d in ((2, 28), (3, 1), (7, 15))]
			bins = [(d.isoformat(), None) for d in days]
		else:
			bins = timeseries.bins(spec, step)
		rows = [{'region': g, 'date': a, 'value': None if a.startswith('2022-02') else _value(spec, dt.date.fromisoformat(a)),
		         'n_pixels': 5, 'n_images': 1} for a, _ in bins for g in ('park', 'buffer')]
		if progress:
			progress(len(bins), len(bins))
		rows.sort(key=lambda r: (r['region'], r['date']))
		return rows, scale or (500.0 if spec.get('sensor') == 'Modis' else 10.0)

	monkeypatch.setattr(services.areas, 'region', lambda region: 'regions')
	monkeypatch.setattr(services.timeseries, 'series', series)
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	return calls


TWO = {'variable': 'NDSI', 'sensor': 'Sentinel-2', 'start': '2021-01-01', 'end': '2023-12-31', 'step': 'monthly',
       'doy': True, 'other_variable': 'NDVI'}


def test_two_indices_on_two_axes(ee, tmp_path):
	steps = []
	out = services.time_series(REGION, csv=str(tmp_path / 'profile.csv'), progress=lambda d, t: steps.append((d, t)),
	                           **TWO)
	assert [c['spec']['index'] for c in ee] == ['NDSI', 'NDVI'] and steps == [(36, 72), (72, 72)]
	assert ee[1]['spec']['sensor'] == 'Sentinel-2' and ee[1]['spec']['period'] == ['2021-01-01', '2023-12-31']
	assert out['variables'] == ['NDSI Sentinel-2', 'NDVI Sentinel-2'] and out['interannual'] == 'median'
	assert out['units'] == {'NDSI Sentinel-2': '[unitless]', 'NDVI Sentinel-2': '[unitless]'}
	assert out['scales'] == {'NDSI Sentinel-2': 10.0, 'NDVI Sentinel-2': 10.0}
	assert out['ylim'] is None and out['other_ylim'] is None  # each axis from the values of its own variable
	assert (out['ylabel'], out['other_ylabel']) == ('NDSI Sentinel-2 [unitless]', 'NDVI Sentinel-2 [unitless]')  # each axis
	assert out['title'] == ('NDSI Sentinel-2 and NDVI Sentinel-2 | 2021-01-01 / 2023-12-31 | monthly mean, spatial mean '
	                        '| median of the years by day of the year')
	rows = out['rows']  # the yearly rows of both variables, each with its name
	assert len(rows) == 2 * 2 * 36 and {r['variable'] for r in rows} == set(out['variables'])
	assert [(r['region'], r['variable']) for r in rows[::36]] == [
		('buffer', 'NDSI Sentinel-2'), ('buffer', 'NDVI Sentinel-2'), ('park', 'NDSI Sentinel-2'),
		('park', 'NDVI Sentinel-2')]
	assert all({'year', 'doy'} <= set(r) for r in rows)
	profile = out['profile']
	assert len(profile) == 2 * 2 * 12
	assert [(r['region'], r['variable']) for r in profile[::12]] == [(r['region'], r['variable']) for r in rows[::36]]
	jan = profile[0]
	assert jan['label'] == 'Jan' and jan['n_years'] == 3 and jan['value'] == pytest.approx(0.51)  # 0.5 + 1/100
	assert profile[1]['n_years'] == 2  # February 2022 without a value
	with open(out['csv'], newline='', encoding='utf-8') as f:
		table = list(csv.DictReader(f))
	assert list(table[0]) == timeseries.PROFILE_COLUMNS + timeseries.PROFILE_META
	assert len(table) == len(profile) and table[0]['variable'] == 'NDSI Sentinel-2' and table[0]['part'] == '1'
	assert {k: table[0][k] for k in timeseries.PROFILE_META} == {
		'sensor': 'Sentinel-2', 'step': 'monthly', 'metric': 'mean', 'stat': 'mean', 'interannual': 'median',
		'unit': '1', 'scale_m': '10.0'}


def test_the_axes_of_two_variables_of_different_sensors(ee, tmp_path):
	out = services.time_series(REGION, 'NDSI', 'Modis', '2021-01-01', '2022-12-31', step='16-day', doy=True,
	                           interannual='p75', other_variable='NDVI', other_sensor='Sentinel-2',
	                           other_ylim=[0, 0.8], csv=str(tmp_path / 'p.csv'))
	assert out['ylim'] is None and out['other_ylim'] == (0.0, 0.8)  # the NDSI snow cover of MODIS: from the data
	assert out['scales'] == {'NDSI Modis': 500.0, 'NDVI Sentinel-2': 10.0}
	assert [r['part'] for r in out['profile'][:3]] == ['0', '1', '2'] and out['profile'][1]['label'] == 'Jan 17'
	with open(out['csv'], newline='', encoding='utf-8') as f:
		table = list(csv.DictReader(f))
	assert {(r['variable'], r['sensor'], r['scale_m'], r['interannual']) for r in table} == {
		('NDSI Modis', 'Modis', '500.0', 'p75'), ('NDVI Sentinel-2', 'Sentinel-2', '10.0', 'p75')}


def test_the_same_options_for_the_other_variable(ee):
	quality = {'clouds': True, 'snow': False}
	where = [{'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 1500}]
	services.time_series(REGION, 'NDSI', 'Sentinel-2', '2021-01-01', '2022-12-31', step='monthly', metric='median',
	                     stat='p90', season=['10-01', '05-31'], quality=quality, scale=250, doy=True,
	                     other_variable='NDVI', where=where)
	first, other = ee
	assert other['step'] == 'monthly' and other['metric'] == 'median' and other['stat'] == 'p90'
	assert other['scale'] == first['scale'] == 250
	for key in ('period', 'season', 'quality', 'where', 'metric'):
		assert other['spec'][key] == first['spec'][key], key


def test_one_index_with_a_metric_between_the_years(ee, tmp_path):
	out = services.time_series(REGION, 'NDVI', 'Sentinel-2', '2021-01-01', '2023-12-31', doy=True, interannual='mean',
	                           csv=str(tmp_path / 'p.csv'))
	assert len(ee) == 1 and out['variables'] == ['NDVI Sentinel-2'] and out['ylim'] is None
	assert out['other_ylim'] is None and out['other_ylabel'] is None
	assert 'variable' not in out['rows'][0] and {r['variable'] for r in out['profile']} == {'NDVI Sentinel-2'}
	assert out['title'].endswith('| monthly mean, spatial mean | mean of the years by day of the year')
	cv = services.time_series(REGION, 'NDVI', 'Sentinel-2', '2021-01-01', '2023-12-31', doy=True, interannual='cv')
	assert cv['ylim'] is None and cv['unit'] == '[%]' and cv['units'] == {'NDVI Sentinel-2': '[%]'}
	assert cv['ylabel'] == 'Coefficient of variation [%]'
	std = services.time_series(REGION, 'NDVI', 'Sentinel-2', '2021-01-01', '2023-12-31', stat='std', doy=True,
	                           interannual='median')
	assert std['ylim'] is None
	given = services.time_series(REGION, 'NDVI', 'Sentinel-2', '2021-01-01', '2023-12-31', doy=True,
	                             interannual='median', ylim='0 0.6')
	assert given['ylim'] == (0.0, 0.6)


def test_the_daily_profile(ee):
	out = services.time_series(REGION, 'NDVI', 'Sentinel-2', '2022-01-01', '2024-12-31', step='daily', doy=True,
	                           interannual='max')
	park = [r for r in out['profile'] if r['region'] == 'park']
	assert [(r['part'], r['label'], r['n_years']) for r in park] == [('02-28', 'Feb 28', 2), ('03-01', 'Mar 1', 3),
	                                                                ('07-15', 'Jul 15', 3)]  # none in February 2022
	assert park[1]['doy'] == 61  # 1 March in a leap year


def test_a_line_per_year_is_as_before(ee, tmp_path):
	out = services.time_series(REGION, 'NDVI', 'Sentinel-2', '2021-01-01', '2022-12-31', doy=True,
	                           csv=str(tmp_path / 's.csv'))
	assert 'profile' not in out and 'variables' not in out and out['ylim'] is None
	assert out['title'].endswith(' | by day of the year') and out['unit'] == '[unitless]'
	with open(out['csv'], newline='', encoding='utf-8') as f:
		assert next(csv.reader(f))[:7] == timeseries.COLUMNS + ['year', 'doy']
	plain = services.time_series(REGION, 'NDVI', 'Sentinel-2', '2021-01-01', '2022-12-31')
	assert 'ylim' not in plain and 'profile' not in plain


@pytest.mark.parametrize('call, message', [
	({'interannual': 'median'}, 'interannual: only for the chart by day of the year'),
	({'other_variable': 'NDVI'}, 'other_variable: only for the chart by day of the year'),
	({'ylim': [-1, 1], 'other_ylim': [0, 1]}, 'ylim, other_ylim: only for the chart by day of the year'),
	({'doy': True, 'step': 'annual', 'interannual': 'median'}, 'needs a step shorter than a year'),
	({'doy': True, 'interannual': 'sum'}, 'unknown metric between the years'),
	({'doy': True, 'other_sensor': 'Modis'}, 'give other_variable'),
	({'doy': True, 'interannual': 'mean', 'other_ylim': [0, 1]}, 'give other_variable'),
	({'doy': True, 'other_variable': 'FOO'}, r'other_variable \(the right axis\): FOO with sensor Sentinel-2 is not in'),
	({'doy': True, 'other_variable': 'NDVI', 'other_sensor': 'Copernicus'}, 'is not in the catalog'),
	({'doy': True, 'other_variable': 'MODIS/061/MOD13Q1'}, 'a variable of the catalog of MonitorEO'),
	({'doy': True, 'other_variable': 'ELEVATION', 'other_sensor': 'Copernicus'}, 'is a fixed layer, without dates'),
	({'doy': True, 'other_variable': 'BIO01', 'other_sensor': 'WorldClim'}, 'is a fixed layer, without dates'),
	({'doy': True, 'other_variable': 'RBR'}, 'compute it with burn_severity'),
	({'doy': True, 'metric': 'median', 'other_variable': 'SCF', 'other_sensor': 'Landsat'},
	 r"other_variable \(the right axis\): SCF \(Landsat\) only takes the metric 'mean'"),
	({'doy': True, 'metric': 'p90', 'other_variable': 'CF'}, "CF \\(Sentinel-2\\) only takes the metric 'mean'"),
	({'doy': True, 'other_variable': 'NDVI', 'other_sensor': 'Sentinel-2', 'variable': 'NDVI'},
	 'NDVI Sentinel-2 is already the variable of the left axis'),
	({'doy': True, 'interannual': 'median', 'ylim': [1, 0]},
	 r'ylim: the first number of the y axis \(1\) must be smaller'),
	({'doy': True, 'other_variable': 'NDVI', 'other_ylim': [0]}, 'other_ylim: give two numbers'),
])
def test_the_errors_come_before_earth_engine(call, message, monkeypatch):
	monkeypatch.setattr(services.areas, 'region', lambda region: pytest.fail('computed before checking the call'))
	args = dict({'variable': 'NDSI', 'sensor': 'Sentinel-2', 'start': '2021-01-01', 'end': '2022-12-31'}, **call)
	with pytest.raises(ValueError, match=message):
		services.time_series(REGION, **args)


def test_the_snow_cover_frequency_with_the_mean(ee):
	out = services.time_series(REGION, 'NDVI', 'Landsat', '2021-01-01', '2022-12-31', doy=True, other_variable='SCF',
	                           interannual='p25')
	assert out['variables'] == ['NDVI Landsat', 'SCF Landsat'] and out['other_ylim'] is None
	assert out['units']['SCF Landsat'] == '[%]' and out['other_ylabel'] == 'Snow Cover Frequency (SCF) [%]'


def test_data_of_earth_engine_with_an_index_of_the_catalog(ee):
	out = services.time_series(REGION, collection='IDAHO_EPSCOR/TERRACLIMATE', band='pr', unit='mm', start='2021-01-01',
	                           end='2022-12-31', doy=True, other_variable='NDVI', other_sensor='Modis')
	assert out['variables'] == ['IDAHO_EPSCOR/TERRACLIMATE pr', 'NDVI Modis']
	assert out['ylim'] is None and out['other_ylim'] is None and out['units']['IDAHO_EPSCOR/TERRACLIMATE pr'] == 'mm'
	with pytest.raises(ValueError, match='give its sensor'):
		services.time_series(REGION, collection='IDAHO_EPSCOR/TERRACLIMATE', band='pr', start='2021-01-01',
		                     end='2022-12-31', doy=True, other_variable='NDVI')


# The chart ---------------------------------------------------------------------------------------------------------

@pytest.fixture
def figure(monkeypatch):
	"""The figure of the last chart (its PNG is drawn too)."""
	pytest.importorskip('matplotlib')
	from monitoreo import charts
	got = []
	png = charts._png
	monkeypatch.setattr(charts, '_png', lambda fig, path=None: got.append(fig) or png(fig, path))
	return got


def test_the_chart_of_two_indices(ee, figure, tmp_path):
	out = services.time_series(REGION, chart=str(tmp_path / 'profile.png'), **TWO)
	assert out['chart'] and open(out['chart'], 'rb').read(8) == b'\x89PNG\r\n\x1a\n'
	axes = figure[-1].axes
	assert len(axes) == 4  # a panel per region, each with its left and right axes
	from monitoreo import charts
	for region, (left, right) in zip(('buffer', 'park'), (axes[0:2], axes[2:4])):
		# each axis from the minimum to the maximum of the values of its own variable (with the margin of matplotlib)
		for name, a in zip(out['variables'], (left, right)):
			values = [r['value'] for r in out['profile'] if r['region'] == region and r['variable'] == name
			          and r['value'] is not None]
			low, high = a.get_ylim()
			assert low <= min(values) < max(values) <= high and high - low < 1.2 * (max(values) - min(values)), name
		assert left.get_ylim() != right.get_ylim() and left.get_xlim() == (1, 366)
		assert list(left.get_xticks()) == charts.MONTH_STARTS
		assert [ln.get_color() for ln in left.get_lines() if ln.get_label() == 'NDSI Sentinel-2'] == ['#1f77b4']
		assert [ln.get_color() for ln in right.get_lines() if ln.get_label() == 'NDVI Sentinel-2'] == ['#d62728']
		assert left.yaxis.label.get_color() == '#1f77b4' and right.yaxis.label.get_color() == '#d62728'
		assert any(ln.get_ydata()[0] == 0 and len(set(ln.get_ydata())) == 1 for ln in left.get_lines())  # the 0 line
	assert [t.get_text() for t in axes[0].get_legend().get_texts()] == out['variables']
	assert [axes[0].get_title(loc='left'), axes[2].get_title(loc='left')] == ['buffer', 'park']


def test_the_chart_of_one_index_and_of_many_regions(figure, tmp_path):
	from monitoreo import charts
	profile = [{'region': f'r{i}', 'variable': 'NDSI Modis', 'part': str(m), 'doy': charts.MONTH_STARTS[m - 1],
	            'label': '', 'value': 10.0 * m if m != 4 else None, 'n_years': 2} for i in range(5) for m in range(1, 13)]
	png = charts.doy_profile_png(profile, str(tmp_path / 'p.png'), 'NDSI', '[unitless]')
	assert png[:8] == b'\x89PNG\r\n\x1a\n'
	axes = figure[-1].axes
	assert len(axes) == 4 and axes[0].get_ylim()[1] > 100  # the first 4 regions, one axis each, from the data
	values = axes[0].get_lines()[0].get_ydata()
	assert math.isnan(values[3]) and values[0] == 10.0  # a gap where a step has no value


def test_a_line_per_year_takes_a_range(ee, figure, tmp_path):
	out = services.time_series(REGION, 'NDVI', 'Sentinel-2', '2021-01-01', '2022-12-31', doy=True, ylim=[0, 0.5],
	                           chart=str(tmp_path / 'years.png'))
	assert out['ylim'] == (0.0, 0.5) and figure[-1].axes[0].get_ylim() == (0.0, 0.5)
	assert [ln.get_label() for ln in figure[-1].axes[0].get_lines()] == ['2021', '2022']


# What to cite, the report and the README ---------------------------------------------------------------------------

def _ids(args):
	return [r['id'] for r in references.cite('time_series', args)['references']]


def test_the_references_of_both_variables():
	args = dict(TWO, region=REGION, variable='NDSI', sensor='Modis', other_sensor='Sentinel-2')
	ids = _ids(args)
	assert {'hall1995', 'riggs2017', 'tucker1979', 'wu2020', 'gorelick2017', 'monitoreo'} <= set(ids)
	cited = references.cite('time_series', args)
	assert any('Copernicus Sentinel' in c for c in cited['credits'])  # the NDVI of Sentinel-2
	assert 'tucker1979' not in _ids(dict(args, other_variable=None))
	assert 'pearson1896' in _ids(dict(args, interannual='cv')) and 'pearson1896' not in _ids(args)
	assert 'pearson1896' not in _ids(dict(args, doy=False, other_variable=None, interannual='cv'))
	snow = _ids(dict(args, sensor='Sentinel-2', other_variable='SCF', other_sensor='Landsat'))
	assert 'tucker1979' not in snow  # the SCF (its Landsat collections, TOA scenes and SRTM), not the NDVI
	alone = _ids({'region': REGION, 'variable': 'SCF', 'sensor': 'Landsat', 'start': TWO['start'], 'end': TWO['end']})
	assert set(alone) <= set(snow)


def test_the_report_of_a_profile():
	args = dict(TWO, region=REGION, ylim=[-0.5, 1])
	assert report.item_title('time_series', args) == ('Monthly profile of NDSI (Sentinel-2) and NDVI (Sentinel-2) by '
	                                                  'day of the year, 2021-2023: median of the years')
	assert report.item_title('time_series', dict(args, other_variable=None, interannual='p25')).endswith(
		'of NDSI (Sentinel-2) by day of the year, 2021-2023: percentile 25 of the years')
	assert report.item_title('time_series', dict(args, other_variable=None)).endswith(', by day of the year')
	facts = dict(report.item_facts('time_series', args, {}))
	assert facts['Other variable (right axis)'].startswith('Normalized Difference Vegetation Index (NDVI), Sentinel-2')
	assert facts['Between the years'].startswith('median of the values of each month (1-12) in the years')
	assert facts['Chart'].endswith('NDSI (Sentinel-2) on the left axis (-0.5 to 1), NDVI (Sentinel-2) on the right axis '
	                               '(from the data)')  # the given range, and none: from the values of the NDVI
	assert facts['Method'] == report.METHODS['time_series_profile']
	modis = dict(report.item_facts('time_series', dict(args, sensor='Modis', ylim=None, other_variable=None,
	                                                   interannual='cv', step='16-day'), {}))
	assert modis['Chart'].endswith('NDSI (MODIS) on the y axis (from the data)')
	assert 'Other variable (right axis)' not in modis
	assert 'each 16-day period from 1 January' in modis['Between the years']
	assert modis['Between the years'].startswith('coefficient of variation (%) of the values')
	years = dict(report.item_facts('time_series', dict(args, other_variable=None), {}))
	assert years['Chart'].startswith('a line per year') and 'Between the years' not in years
	assert 'Discarded pixels (right axis)' not in years


def test_the_discarded_pixels_of_each_variable_of_a_profile():
	"""The pixel filters as each variable has them (sensors.filters): 'auto' keeps the snow of the NDSI and removes
	that of the NDVI; the SCF on the left keeps its fixed filters, the NDVI on the right gets the default ones."""
	auto = dict(report.item_facts('time_series', dict(TWO, region=REGION, quality={'snow': 'auto'}), {}))
	assert auto['Discarded pixels'] == 'clouds, water'  # the NDSI of Sentinel-2: no aerosols band
	assert auto['Discarded pixels (right axis)'] == 'clouds, water, snow'
	assert 'pixel filters chosen, as they apply to it' in auto['Other variable (right axis)']
	assert auto['Chart'].startswith('a line per variable over the days of the year (each month at the median day')
	scf = dict(report.item_facts('time_series', dict(TWO, region=REGION, variable='SCF', sensor='Landsat'), {}))
	assert scf['Discarded pixels'] == 'clouds, water'
	assert scf['Discarded pixels (right axis)'] == 'clouds, water, snow, aerosols'
	off = dict(report.item_facts('time_series', dict(TWO, region=REGION, quality={'snow': False}), {}))
	assert off['Discarded pixels'] == off['Discarded pixels (right axis)'] == 'clouds, water'
	daily = dict(report.item_facts('time_series', dict(TWO, region=REGION, step='daily'), {}))
	assert '(each calendar day at its day in a leap year)' in daily['Chart']


def test_the_table_of_a_profile_in_the_report(ee):
	out = services.time_series(REGION, **TWO)
	labels, body = report.item_table('time_series', out, TWO)
	assert labels == ['Region', 'Variable', 'Step of the year', 'Day of the year', 'Value', 'Unit', 'Years']
	assert body[0][:4] == ['buffer', 'NDSI Sentinel-2', 'Jan', '1'] and body[0][5:] == ['dimensionless', '3']
	one = services.time_series(REGION, 'NDVI', 'Sentinel-2', '2021-01-01', '2023-12-31', doy=True, interannual='cv')
	labels, body = report.item_table('time_series', one, {})
	assert labels == ['Region', 'Step of the year', 'Day of the year', 'Value (%)', 'Years']


def test_the_readme_of_a_profile(ee, tmp_path):
	out = services.time_series(REGION, csv=str(tmp_path / 'profile.csv'), chart=str(tmp_path / 'profile.png'), **TWO)
	text = ' '.join(open(out['readme'], encoding='utf-8').read().split())
	assert 'Monthly profile of NDSI (Sentinel-2) and NDVI (Sentinel-2) by day of the year' in text
	assert ('Each variable is in its own unit, on its own y axis of the chart: NDSI Sentinel-2, dimensionless (UDUNITS '
	        '1); NDVI Sentinel-2, dimensionless (UDUNITS 1)') in text
	assert ('value: Median of the values of the step in the years of the period (in the unit of the variable of the '
	        'row: NDSI Sentinel-2 dimensionless, NDVI Sentinel-2 dimensionless)') in text
	for column in timeseries.PROFILE_COLUMNS + timeseries.PROFILE_META:
		assert f' {column}: ' in text, column
	assert 'part: step of the year: the month (1-12)' in text and 'n_years: years with a value in the step' in text
	assert 'Between the years: median of the values of each month (1-12)' in text
	assert ('NDSI (Sentinel-2) on the left axis (from the data), NDVI (Sentinel-2) on the right axis (from the '
	        'data)') in text
	assert 'other_variable="NDVI"' in text and 'Tucker, C. J. (1979)' in text and 'Wu, Q. (2020)' in text
	one = services.time_series(REGION, 'NDVI', 'Sentinel-2', '2021-01-01', '2023-12-31', doy=True, interannual='cv',
	                           csv=str(tmp_path / 'cv.csv'))
	text = ' '.join(readme.text('time_series', {'region': REGION, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
	                                            'start': '2021-01-01', 'end': '2023-12-31', 'doy': True,
	                                            'interannual': 'cv'}, one).split())
	assert 'The values are coefficients of variation (100 × standard deviation / mean), in %: in UDUNITS (the units ' \
	       'of the CF conventions), %' in text
	assert 'value: Coefficient of variation (%, 100 × sample standard deviation / |mean|) of the values of the step ' \
	       'in the years of the period (%)' in text
	assert 'Pearson, K. (1896)' in text
