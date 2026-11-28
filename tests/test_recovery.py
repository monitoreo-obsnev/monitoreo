"""The recovery metrics after a disturbance (monitoreo.recovery, services.recovery_metrics) and their STL in numpy
(monitoreo.stl), without Earth Engine: STL as statsmodels computes it (when it is installed), the metrics of a series
with a known drop and recovery, the arguments refused before Earth Engine, the service with the series faked, its CSV,
references and README facts, and the command line. The test marked ee computes the fire of Lanjarón (2005)."""

import csv
import datetime as dt
import os

import numpy as np
import pytest

from monitoreo import cli, readme, recovery, references, report, services, stl, timeseries


def _monthly(start_year, years, f):
	return [{'date': dt.date(start_year + i // 12, i % 12 + 1, 1).isoformat(), 'value': f(i)} for i in range(12 * years)]


def _season(i):
	return 0.1 * np.sin(2 * np.pi * i / 12)


def test_stl_is_that_of_statsmodels():
	statsmodels = pytest.importorskip('statsmodels.tsa.seasonal')
	rng = np.random.default_rng(1)
	t = np.arange(240)
	y = 0.5 + 0.2 * np.sin(2 * np.pi * t / 12) + 0.0005 * t + rng.normal(0, 0.03, len(t))
	y[100] -= 0.6
	y[120:] -= 0.15
	for robust in (True, False):
		for period, seasonal, trend in ((12, 13, 13), (12, 7, None), (23, 25, 25)):
			kw = {'period': period, 'seasonal': seasonal, 'robust': robust, **({'trend': trend} if trend else {})}
			ref = statsmodels.STL(y, **kw).fit()
			season, tr, res = stl.stl(y, period, seasonal=seasonal, trend=trend, robust=robust)
			assert np.allclose(season, ref.seasonal, atol=1e-9) and np.allclose(tr, ref.trend, atol=1e-9), kw
			assert np.allclose(season + tr + res, y)


def test_stl_refuses_what_it_cannot_decompose():
	with pytest.raises(ValueError, match='two cycles'):
		stl.stl(np.ones(20), 12)
	with pytest.raises(ValueError, match='without missing values'):
		stl.stl(np.r_[np.ones(30), np.nan], 12)


def test_the_metrics_of_a_drop_and_its_recovery():
	"""A monthly series of 0.6 with a season, which drops to 0.3 the month of the event (2010-07) and recovers
	linearly in 4 years, with a noise of 0.02: a decrease, S95 near 0.3, back in the reference in about 4 years, and
	recovered."""
	event = dt.date(2010, 7, 15)
	noise = np.random.default_rng(3).normal(0, 0.02, 144)

	def f(i):
		d = dt.date(2005 + i // 12, i % 12 + 1, 1)
		after = (d - dt.date(2010, 7, 1)).days / 365.25
		loss = 0 if after < 0 else max(0.0, 0.3 * (1 - after / 4))
		return 0.6 - loss + _season(i) + noise[i]
	m = recovery.of_series(_monthly(2005, 12, f), 'monthly', event)
	assert m['direction'] == 'decrease' and 0.2 < m['S95'] < 0.35 and m['impact_pct'] < -30
	assert 0 <= m['DIT_years'] < 1 and 3 < m['RRT_years'] < 5 and m['recovered_pct'] > 90
	assert m['reference']['from'] >= '2007-07-01' and m['gaps'] == 0
	assert m['trends']['before']['n'] == 5 and m['anomalies']['z_min_first_year'] < -2
	assert 0.15 < m['seasonal_amplitude']['before'] < 0.22  # the 0.1 * sin of the season, smoothed by STL


def test_gaps_differences_and_annual_series():
	rows = _monthly(2000, 6, lambda i: 1.0 + i)
	rows[5]['value'] = None
	dates, y, gaps = recovery.regular(rows, 'monthly')
	assert y[5] == 6.0 and round(gaps, 4) == round(1 / 72, 4)  # filled by linear interpolation
	diff = recovery.difference(rows, _monthly(2000, 6, lambda i: 0.5), 'monthly')
	assert diff[0] == {'date': '2000-01-01', 'value': 0.5}
	yearly = [{'date': f'{y}-01-01', 'value': 1.0 if y < 2010 else 0.5 + 0.1 * (y - 2010)} for y in range(2000, 2021)]
	m = recovery.of_series(yearly, 'annual', dt.date(2010, 3, 1))
	assert m['direction'] == 'decrease' and 'seasonal_amplitude' not in m and m['RRT_years'] is not None


def test_the_arguments_are_checked_before_earth_engine():
	assert recovery.check('monthly', '2005-09-22', '1995-01-01', '2020-12-31')[1] == dt.date(2005, 9, 22)
	for args, match in ((('daily', '2005-09-22', '1995-01-01', '2020-12-31'), 'monthly'),
	                    (('monthly', '22/09/2005', '1995-01-01', '2020-12-31'), 'YYYY-MM-DD'),
	                    (('monthly', '2025-09-22', '1995-01-01', '2020-12-31'), 'not inside the period'),
	                    (('monthly', '2005-09-22', '2004-01-01', '2020-12-31'), 'the 3 years before')):
		with pytest.raises(ValueError, match=match):
			recovery.check(*args)
	with pytest.raises(ValueError, match='equilibrium'):
		recovery.check('monthly', '2005-09-22', '1995-01-01', '2020-12-31', equilibrium=5)
	with pytest.raises(ValueError, match='season'):  # the rest of each year would be filled by interpolation
		recovery.check('monthly', '2005-09-22', '1995-01-01', '2020-12-31', season=['06-01', '09-30'])
	assert recovery.check('annual', '2005-09-22', '1995-01-01', '2020-12-31', season=['06-01', '09-30'])[0] == 'annual'


def test_the_trends_have_the_continuity_correction_of_the_script():
	"""Four rising yearly means: p 0.0894 with the continuity correction (not significant; 0.0415 without it)."""
	t = recovery._trend([2001, 2002, 2003, 2004], [1.0, 2.0, 3.0, 4.0])
	assert t['tau'] == 1.0 and t['p_value'] == 0.0894 and not t['significant'] and t['sen_per_year'] == 1.0
	assert recovery._trend([2001, 2002, 2003, 2004, 2005], [1.0, 2.0, 3.0, 4.0, 5.0])['p_value'] == 0.0275


def test_the_service(monkeypatch, tmp_path):
	event = dt.date(2010, 7, 15)

	def affected(i):
		d = dt.date(2005 + i // 12, i % 12 + 1, 1)
		return 0.6 - (0.3 if dt.date(2010, 7, 1) <= d < dt.date(2012, 1, 1) else 0) + _season(i)
	rows = [dict(r, region='burned', n_pixels=10, n_images=2) for r in _monthly(2005, 12, affected)] + \
		[dict(r, region='ring', n_pixels=10, n_images=2) for r in _monthly(2005, 12, lambda i: 0.6 + _season(i))]
	got = {}

	def series(spec, regions, step, metric, stat, scale, progress=None, steps=None, **kw):
		got.update(step=step, kw=kw)
		return rows, 30
	monkeypatch.setattr(timeseries, 'series', series)
	monkeypatch.setattr(services.areas, 'region', lambda r: None)
	path = str(tmp_path / 'recovery.csv')
	res = services.recovery_metrics({'wdpa_id': 1}, 'NDVI', 'Landsat', '2005-01-01', '2016-12-31', event=str(event),
	                                affected='burned', control='ring', csv=path)
	assert [r['series'] for r in res['rows']] == ['affected', 'control', 'difference']
	assert res['rows'][2]['region'] == 'burned - ring' and res['metrics']['control'].get('direction') is not None
	assert res['rows'][0]['direction'] == 'decrease' and res['rows'][0]['RRT_years'] < 3
	with open(path, encoding='utf-8') as f:
		assert next(csv.reader(f))[:len(services.RECOVERY_COLUMNS)] == services.RECOVERY_COLUMNS
	ids = [r['id'] for r in res['references']]
	assert {'marcos2023', 'cleveland1990', 'mann1945', 'sen1968'} <= set(ids)
	with pytest.raises(ValueError, match='one of burned, ring'):
		services.recovery_metrics({'wdpa_id': 1}, 'NDVI', 'Landsat', '2005-01-01', '2016-12-31', event=str(event))
	with pytest.raises(ValueError, match='another feature'):
		services.recovery_metrics({'wdpa_id': 1}, 'NDVI', 'Landsat', '2005-01-01', '2016-12-31', event=str(event),
		                          affected='burned', control='burned')


def test_pairs_the_baci_of_several_affected_areas(monkeypatch, tmp_path):
	"""Several fenced plots (or treated stands) and their controls in one call: the three series of each pair."""
	event = dt.date(2018, 6, 1)

	def plot(gain):
		def f(i):
			d = dt.date(2014 + i // 12, i % 12 + 1, 1)
			return 0.3 + (gain if d >= event else 0) + _season(i)
		return f
	rows = []
	for name, f in (('fence1', plot(0.2)), ('around1', plot(0)), ('fence2', plot(0.05)), ('around2', plot(0))):
		rows += [dict(r, region=name, n_pixels=10, n_images=2) for r in _monthly(2014, 10, f)]
	monkeypatch.setattr(timeseries, 'series', lambda *a, **k: (rows, 10))
	monkeypatch.setattr(services.areas, 'region', lambda r: None)
	res = services.recovery_metrics({'file': 'plots.gpkg'}, 'MSAVI2', 'Sentinel-2', '2014-01-01', '2023-12-31',
	                                event=str(event), pairs=[['fence1', 'around1'], {'affected': 'fence2',
	                                                                                 'control': 'around2'}],
	                                csv=str(tmp_path / 'pairs.csv'), chart=str(tmp_path / 'pairs.png'))
	assert [r['region'] for r in res['rows']] == ['fence1', 'around1', 'fence1 - around1', 'fence2', 'around2',
	                                              'fence2 - around2']
	assert set(res['metrics']) == {'fence1 | around1', 'fence2 | around2'} and len(res['pairs']) == 2
	assert res['rows'][2]['direction'] == 'increase' and res['affected'] == ['fence1', 'fence2']
	assert os.path.exists(res['csv']) and (res['chart'] is None or os.path.exists(res['chart']))
	facts = dict(report.item_facts('recovery_metrics', {'region': {'file': 'plots.gpkg'}, 'variable': 'MSAVI2',
	                                                    'sensor': 'Sentinel-2', 'start': '2014-01-01',
	                                                    'end': '2023-12-31', 'event': str(event),
	                                                    'pairs': [['fence1', 'around1'], ['fence2', 'around2']]}, {}))
	assert facts['Areas'].startswith('2 pairs') and 'fence2 and around2' in facts['Areas']
	for bad, message in (([['fence1', 'fence1']], 'two features'), ([['fence1']], r'each pair is \[affected'),
	                     ([], 'a list of'), ([['fence1', 'around1'], ['fence1', 'around1']], 'repeated')):
		with pytest.raises(ValueError, match=message):
			services.recovery_metrics({'file': 'plots.gpkg'}, 'MSAVI2', 'Sentinel-2', '2014-01-01', '2023-12-31',
			                          event=str(event), pairs=bad)
	with pytest.raises(ValueError, match='give no affected, control nor ring'):
		services.recovery_metrics({'file': 'plots.gpkg'}, 'MSAVI2', 'Sentinel-2', '2014-01-01', '2023-12-31',
		                          event=str(event), pairs=[['fence1', 'around1']], ring=True)
	twice = rows + [dict(r, region='around1') for r in rows if r['region'] == 'around2']
	monkeypatch.setattr(timeseries, 'series', lambda *a, **k: (twice, 10))
	with pytest.raises(ValueError, match='several features named around1'):
		services.recovery_metrics({'file': 'plots.gpkg'}, 'MSAVI2', 'Sentinel-2', '2014-01-01', '2023-12-31',
		                          event=str(event), pairs=[['fence1', 'around1']])
	monkeypatch.setattr(timeseries, 'series', lambda *a, **k: (rows, 10))
	assert [k for k, _ in report.TABLES['recovery_metrics'][1]][:2] == ['series', 'region']
	with pytest.raises(ValueError, match='fence9 is not a feature'):
		services.recovery_metrics({'file': 'plots.gpkg'}, 'MSAVI2', 'Sentinel-2', '2014-01-01', '2023-12-31',
		                          event=str(event), pairs=[['fence9', 'around1']])


def test_readme_report_and_command_line(capsys):
	assert 'S95' in readme.COLUMNS and 'recovery_metrics' in report.METHODS and 'recovery_metrics' in references.EARTH_ENGINE
	args = {'region': {'wdpa_id': 1}, 'variable': 'NDVI', 'sensor': 'Landsat', 'start': '1995-01-01',
	        'end': '2020-12-31', 'event': '2005-09-22', 'affected': 'burned', 'control': 'ring', 'reference_years': 10}
	facts = dict(report.item_facts('recovery_metrics', args, {'scale': 30}))
	assert facts['Event'] == '2005-09-22' and 'control ring' in facts['Areas'] and '10 years' in facts['Reference']
	with pytest.raises(SystemExit):
		cli.main(['recovery', '--help'])
	text = ' '.join(capsys.readouterr().out.split())
	assert '--event' in text and '--control' in text and '--reference-years' in text and '--pairs' in text


ZONES = '/Users/javier/Downloads/Claude/everest/resultados/sierra_nevada/zonas.gpkg'


@pytest.mark.ee
@pytest.mark.skipif(not os.environ.get('EE_PROJECT') or not os.path.exists(ZONES), reason='EE_PROJECT or the zones')
def test_the_fire_of_lanjaron():
	"""The NDVI of Landsat of the fire of Lanjarón (2005-09-22) and its control, with the arguments of the EVEREST case
	study: the same metrics as the script that this module ports (checked on 2026-11-27, 23 minutes)."""
	services.init()
	where = [{'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 1300, 'max': 2292},
	         {'landcover': 'CORINE', 'year': 2000, 'exclude': ['water', 'built', 'cropland', 'bare']}]
	res = services.recovery_metrics({'file': ZONES, 'name_field': 'region'}, 'NDVI', 'Landsat', '1984-03-16',
	                                '2026-10-31', event='2005-09-22', affected='afectada', control='control',
	                                reference_years=10, scale=60, quality={'water': False}, where=where)
	a, d = res['metrics']['affected'], res['metrics']['difference']
	assert a['direction'] == 'decrease' and abs(a['S95'] - 0.1524) < 0.0005 and a['impact_pct'] == -61.3
	assert (a['DIT_years'], a['RRT_years'], a['RET_years'], a['recovered_pct']) == (0.52, 6.61, 8.52, 95.4)
	assert abs(d['S95'] - 0.1493) < 0.0005 and d['RRT_years'] is None and d['RET_years'] == 15.52
