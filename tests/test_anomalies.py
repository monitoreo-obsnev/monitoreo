"""The standardized anomalies (monitoreo.anomalies, services.anomalies) and the z of compare_map, without Earth
Engine: the z of a series with known anomalies, its episodes, the arguments refused before Earth Engine, the service
with the series faked, its CSV, README columns and facts, the MCP tool and the command line."""

import csv
import datetime as dt
import os

import numpy as np
import pytest

from monitoreo import anomalies, cli, readme, references, report, services, timeseries


def _monthly(start_year, years, f):
	return [{'date': dt.date(start_year + i // 12, i % 12 + 1, 1).isoformat(), 'value': f(i)} for i in range(12 * years)]


def test_the_z_of_each_step_against_its_month():
	# a seasonal series with a little noise in 2001-2010 and a drop of 0.3 in the summers of 2012 and 2013
	rng = np.random.default_rng(1)
	noise = rng.normal(0, 0.02, 12 * 14)

	def f(i):
		d = dt.date(2001 + i // 12, i % 12 + 1, 1)
		drop = 0.3 if d.year in (2012, 2013) and d.month in (6, 7, 8) else 0
		return 0.5 + 0.2 * np.sin(2 * np.pi * i / 12) + noise[i] - drop
	rows = _monthly(2001, 14, f)
	step, ref, thr, years = anomalies.check('monthly', '2001-01-01', '2014-12-31', ['2001-01-01', '2010-12-31'])
	a = anomalies.of_series(rows, step, ref, thr, years)
	z = {r['date']: r['z'] for r in a['rows']}
	assert all(abs(z[f'{y}-{m:02d}-01']) < 4 for y in range(2001, 2011) for m in range(1, 13))
	assert all(z[f'{y}-{m:02d}-01'] < -5 for y in (2012, 2013) for m in (6, 7, 8))  # 0.3 is ~15 standard deviations
	july = [r for r in a['rows'] if r['date'] == '2012-07-01'][0]
	values = [r['value'] for r in rows if r['date'][5:7] == '07' and r['date'] < '2011']
	assert july['reference_n'] == 10 and july['reference_mean'] == pytest.approx(np.mean(values))
	assert july['reference_std'] == pytest.approx(np.std(values, ddof=1))
	neg = [e for e in a['episodes'] if e['sign'] == 'negative' and e['start'][:4] in ('2012', '2013') and
	       '06' <= e['start'][5:7] <= '08']
	assert [(e['start'], e['end'], e['steps']) for e in neg] == [('2012-06-01', '2012-08-01', 3),
	                                                            ('2013-06-01', '2013-08-01', 3)]
	assert neg[0]['peak'] == pytest.approx(min(z[d] for d in ('2012-06-01', '2012-07-01', '2012-08-01')), abs=1e-3)
	assert neg[0]['intensity'] == pytest.approx(sum(z[d] for d in ('2012-06-01', '2012-07-01', '2012-08-01')), abs=1e-3)
	assert a['summary']['longest_steps'] >= 3 and a['summary']['negative_episodes'] >= 2


def test_episodes_and_missing_values():
	rows = [{'date': f'{y}-01-01', 'value': v} for y, v in zip(range(2000, 2012),
	                                                          [1, 2, 1, 2, 1, 2, None, -5, -6, 9, 1, 1])]
	a = anomalies.of_series(rows, 'annual', (dt.date(2000, 1, 1), dt.date(2005, 12, 31)), 1.5, 3)
	assert [r['z'] is None for r in a['rows']][6] and a['rows'][0]['reference_n'] == 6
	eps = a['episodes']
	assert [(e['sign'], e['start'], e['end'], e['steps']) for e in eps] == [
		('negative', '2007-01-01', '2008-01-01', 2), ('positive', '2009-01-01', '2009-01-01', 1)]
	# without variation between the reference years, no z
	flat = anomalies.of_series([{'date': f'{y}-01-01', 'value': 1} for y in range(2000, 2006)], 'annual',
	                           (dt.date(2000, 1, 1), dt.date(2005, 12, 31)))
	assert all(r['z'] is None for r in flat['rows']) and flat['episodes'] == []


@pytest.mark.parametrize('args, message', [
	(('weekly', '2001-01-01', '2010-12-31'), 'step of the anomalies'),
	(('monthly', '2001-01-01', '2010-12-31', ['2020-01-01', '2021-12-31']), 'must be inside the period'),
	(('monthly', '2005-01-01', '2010-12-31', ['2001-01-01', '2007-12-31']), 'must be inside the period'),
	(('monthly', '2001-01-01', '2010-12-31', ['2001-01-01', '2002-12-31']), 'fewer than 3 years'),
	(('monthly', '2001-01-01', '2010-12-31', None, 0), 'above 0'),
	(('monthly', '2001-01-01', '2010-12-31', None, 1.5, 1), 'at least 2'),
	(('monthly', '2001-01-01', '2010-12-31', '2001'), r'\[first day, last day\]'),
])
def test_the_arguments_are_checked_before_earth_engine(args, message):
	with pytest.raises(ValueError, match=message):
		anomalies.check(*args)


def test_the_service(monkeypatch, tmp_path):
	rng = np.random.default_rng(2)
	noise = rng.normal(0, 0.02, 12 * 12)
	rows = [dict(r, region='park', n_pixels=10, n_images=2) for r in _monthly(
		2005, 12, lambda i: 0.5 + noise[i] - (0.4 if i == 12 * 10 + 6 else 0))]

	def series(spec, regions, step, metric, stat, scale, progress=None, steps=None, **kw):
		return rows, 250
	monkeypatch.setattr(timeseries, 'series', series)
	monkeypatch.setattr(services.areas, 'region', lambda r: None)
	path = str(tmp_path / 'anomalies.csv')
	res = services.anomalies({'wdpa_id': 1}, 'NDVI', 'Modis', '2005-01-01', '2016-12-31',
	                         reference=['2005-01-01', '2014-12-31'], threshold=4, csv=path)
	assert [(e['region'], e['start'], e['sign']) for e in res['episodes']] == [('park', '2015-07-01', 'negative')]
	assert res['summary']['park']['negative_steps'] == 1 and res['reference'] == ['2005-01-01', '2014-12-31']
	with open(path, encoding='utf-8') as f:
		assert next(csv.reader(f))[:len(services.ANOMALY_COLUMNS)] == services.ANOMALY_COLUMNS
	with open(res['episodes_csv'], encoding='utf-8') as f:
		assert next(csv.reader(f))[:len(services.EPISODE_COLUMNS)] == services.EPISODE_COLUMNS
	assert {'gorelick2017', 'monitoreo'} <= {r['id'] for r in res['references']}
	with open(res['readme'], encoding='utf-8') as f:
		text = f.read()
	assert 'standardized anomaly: (value - reference_mean) / reference_std' in text
	assert 'anomalies_episodes.csv' in text and 'Z of the trend test' not in text
	with pytest.raises(ValueError, match='fewer than 3 years'):
		services.anomalies({'wdpa_id': 1}, 'NDVI', 'Modis', '2005-01-01', '2016-12-31',
		                   reference=['2005-01-01', '2006-12-31'])


def test_the_z_of_compare_map_is_checked_before_earth_engine():
	with pytest.raises(ValueError, match='at least 3 years'):
		services.compare_map({'wdpa_id': 1}, 'NDVI', 'Modis', '2020-01-01', '2021-12-31', '2023-01-01', '2023-12-31',
		                     z=True)
	with pytest.raises(ValueError, match='give no temporal'):
		services.download_comparison({'wdpa_id': 1}, 'NDVI', 'Modis', '2001-01-01', '2015-12-31', '2023-01-01',
		                             '2023-12-31', temporal='monthly', z=True)


def test_readme_report_mcp_and_command_line(capsys):
	assert 'anomalies' in report.METHODS and 'anomalies' in references.EARTH_ENGINE
	args = {'region': {'wdpa_id': 1}, 'variable': 'NDVI', 'sensor': 'Modis', 'start': '2001-01-01',
	        'end': '2024-12-31', 'step': 'annual', 'reference': ['2001-01-01', '2015-12-31'], 'threshold': 2}
	facts = dict(report.item_facts('anomalies', args, {'scale': 250, 'reference': ['2001-01-01', '2015-12-31']}))
	assert '2001' in facts['Reference'] and '|z| ≥ 2' in facts['Episodes'] and facts['Step'] == report.STEPS['annual']
	z = dict(args, other_start='2023-01-01', other_end='2023-12-31', z=True)
	assert report.item_title('compare_map', z).startswith('Standardized anomaly (z) of NDVI')
	assert 'standard deviation' in dict(report.item_facts('compare_map', z, {}))['Standardized anomaly']
	assert readme.BAND_UDUNITS['z'] == '1'
	from monitoreo import mcp_server
	assert callable(getattr(mcp_server, 'anomalies', None))
	with pytest.raises(SystemExit):
		cli.main(['anomalies', '--help'])
	text = ' '.join(capsys.readouterr().out.split())
	assert '--reference' in text and '--threshold' in text and '--min-years' in text and '--season' in text


def test_parts_of_the_year_of_leap_years_seasons_and_gaps():
	"""The 16-day periods start on the first day of the season each year (2020 is leap: the same period as 2018), and an
	episode does not go across the months outside a season."""
	from monitoreo import composite
	season = ['03-05', '06-30']
	wins = composite.windows(('2018-01-01', '2020-12-31'), season)
	assert anomalies.part(dt.date(2018, 3, 5), '16-day', wins, season) == \
		anomalies.part(dt.date(2020, 3, 5), '16-day', wins, season) == 0
	assert anomalies.part(dt.date(2020, 3, 21), '16-day', wins, season) == 1
	# a season that starts and ends in October: its two parts of October apart
	assert anomalies.part(dt.date(2019, 10, 15), 'monthly', (), ['10-15', '10-14']) == '10-15'
	assert anomalies.part(dt.date(2019, 10, 1), 'monthly', (), ['10-15', '10-14']) == 10
	rows = [{'date': d, 'z': z} for d, z in (('2018-08-01', -2), ('2018-09-01', -2), ('2019-06-01', -2))]
	eps = anomalies._episodes(rows, 1.5, 'monthly')
	assert [(e['start'], e['end']) for e in eps] == [('2018-08-01', '2018-09-01'), ('2019-06-01', '2019-06-01')]


def test_features_of_the_same_name_stay_apart(monkeypatch):
	rows = []
	for i, v in enumerate((0.5, 0.6, 0.5, 0.6, 0.5, 0.6)):
		for name, off in (('park', 0), ('park', 10)):
			rows.append({'region': name, 'date': f'{2010 + i}-01-01', 'value': v + off})
	monkeypatch.setattr(timeseries, 'series', lambda *a, **k: (rows, 30))
	monkeypatch.setattr(services.areas, 'region', lambda r: None)
	res = services.anomalies({'wdpa_id': 1}, 'NDVI', 'Modis', '2010-01-01', '2015-12-31', step='annual')
	assert set(res['summary']) == {'park', 'park (2)'}
	assert all(r['reference_mean'] < 1 for r in res['rows'] if r['region'] == 'park')
	with pytest.raises(ValueError, match='give no interannual'):
		services.compare_map({'wdpa_id': 1}, 'NDVI', 'Modis', '2001-01-01', '2015-12-31', '2023-01-01', '2023-12-31',
		                     interannual='max', z=True)


def test_daily_anomalies_use_the_days_around_the_same_date():
	# a daily step: its reference, the days of the reference years within DAY_WINDOW days of the same date (one day a
	# year is too few), across the new year too; z of a hot day against them
	import datetime as dt
	rows = []
	for y in (2018, 2019, 2020, 2021):
		for k in range(-10, 11):
			d = dt.date(y, 7, 15) + dt.timedelta(days=k)
			rows.append({'date': d.isoformat(), 'value': 30.0 + (k % 3)})
	rows.append({'date': '2022-07-15', 'value': 40.0})
	out = anomalies.of_series(rows, 'daily', (dt.date(2018, 1, 1), dt.date(2021, 12, 31)), threshold=1.5)
	hot = next(r for r in out['rows'] if r['date'] == '2022-07-15')
	assert hot['reference_n'] == 4 * (2 * anomalies.DAY_WINDOW + 1) and hot['z'] > 10
	near = next(r for r in out['rows'] if r['date'] == '2019-07-08')  # 7 days before: its window reaches 1 July
	assert near['reference_n'] == 4 * (anomalies.DAY_WINDOW + 1 + 3)
	ny = anomalies._daily_reference([(dt.date(2019, 12, 30), 1.0), (dt.date(2020, 1, 3), 2.0)],
	                                dt.date(2019, 1, 1), dt.date(2020, 12, 31), {'01-01'})
	assert sorted(v for _, v in ny['01-01']) == [1.0, 2.0]  # across the new year
	assert anomalies.check('daily', '2018-01-01', '2022-12-31')[0] == 'daily'
