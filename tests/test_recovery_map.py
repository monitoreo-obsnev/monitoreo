"""The recovery on each pixel (services.recovery_map, monitoreo.recovery.pixel_metrics), without Earth Engine: each pixel
gets the metrics that recovery_metrics gives to the same annual series, its gaps filled, the pixels without reference
or without years after left out, the README of its bands and the command line. The test marked ee maps the fire of
Lanjarón (2005)."""

import datetime as dt
import os

import numpy as np
import pytest

from monitoreo import cli, publish, readme, recovery, references, report, services


def _series(drop, back, years=range(1999, 2021), noise=0.0, seed=0):
	rng = np.random.default_rng(seed)
	out = []
	for y in years:
		v = 0.6 - (drop * max(0.0, 1 - (y - 2006) / back) if y >= 2006 else 0.0)
		out.append(v + rng.normal(0, noise))
	return np.array(out)


def test_each_pixel_has_the_metrics_of_its_annual_series():
	years = list(range(1999, 2021))
	event = dt.date(2005, 9, 22)
	a, b = _series(0.3, 5, noise=0.02, seed=1), _series(0.1, 12, noise=0.02, seed=2)
	c = _series(0.2, 3, noise=0.02, seed=3)
	c[[3, 10]] = np.nan  # gaps, filled as of_series fills them
	d = np.full(len(years), np.nan)
	d[-5:] = 0.5  # no year before the event: no metrics
	stack = np.empty((len(years), 2, 2))
	stack[:, 0, 0], stack[:, 0, 1], stack[:, 1, 0], stack[:, 1, 1] = a, b, c, d
	got = recovery.pixel_metrics(stack, years, event)
	for (i, j), y in (((0, 0), a), ((0, 1), b), ((1, 0), c)):
		rows = [{'date': f'{yr}-01-01', 'value': None if np.isnan(v) else float(v)} for yr, v in zip(years, y)]
		m = recovery.of_series(rows, 'annual', event)
		assert got['reference_median'][i, j] == pytest.approx(m['reference']['median'])
		assert got['direction'][i, j] == (-1 if m['direction'] == 'decrease' else 1)
		for band in ('impact', 'impact_pct', 'impact_mad', 'DIT_years', 'RRT_years', 'RET_years', 'recovered_pct'):
			want = m.get(band)
			assert (np.isnan(got[band][i, j]) if want is None else got[band][i, j] == pytest.approx(want)), (i, j, band)
	assert np.isnan(got['reference_median'][1, 1]) and got['n_years'][1, 1] == 5 and got['n_years'][1, 0] == 20
	assert set(got) == set(recovery.PIXEL_BANDS)


def test_the_bands_are_documented():
	for band in recovery.PIXEL_BANDS:
		assert band in publish.BANDS, band
	assert readme.band_udunits('RRT_years', '1') == 'year' and readme.band_udunits('impact', 'degC') == 'degC'
	assert readme.band_udunits('n_years', '1') == '1'
	assert readme.band_udunits('y2005', '1') == '1' and readme.band_udunits('impact_pct', '1') == '%'
	assert 'recovery_map' in references.EARTH_ENGINE
	ids = [r['id'] for r in references.cite('recovery_map', {'region': {'wdpa_id': 1}, 'variable': 'NDVI',
	                                                          'sensor': 'Landsat', 'start': '1999-01-01',
	                                                          'end': '2020-12-31'})['references']]
	assert 'marcos2023' in ids
	facts = dict(report.item_facts('recovery_map', {'region': {'wdpa_id': 1}, 'variable': 'NDVI', 'sensor': 'Landsat',
	                                                'start': '1999-01-01', 'end': '2020-12-31', 'event': '2005-09-22'},
	                               {'summary': {'pixels': 100, 'recovered_share': 0.25}}))
	assert facts['Temporal metric'] == 'median' and facts['Event'] == '2005-09-22' and '25 %' in facts['Pixels']


def test_the_arguments_and_the_command_line(capsys):
	with pytest.raises(ValueError, match='not inside the period'):
		services.recovery_map({'wdpa_id': 1}, 'NDVI', 'Landsat', '1999-01-01', '2004-12-31', event='2005-09-22')
	with pytest.raises(ValueError, match='across the new year'):
		services.recovery_map({'wdpa_id': 1}, 'NDSI', 'Modis', '2001-01-01', '2020-12-31', event='2010-01-15',
		                      season=['11-01', '03-31'])
	with pytest.raises(SystemExit, match='ERROR: event 2025-09-22 is not inside'):  # a message, not a traceback
		cli.main(['recovery-map', 'NDVI', '--sensor', 'Landsat', '--region', '{"wdpa_id": 1}', '--start', '1999-01-01',
		          '--end', '2004-12-31', '--event', '2025-09-22'])
	with pytest.raises(SystemExit):
		cli.main(['recovery-map', '--help'])
	text = ' '.join(capsys.readouterr().out.split())
	assert '--event' in text and '--season' in text and '--out' in text


@pytest.mark.ee
@pytest.mark.skipif(not os.environ.get('EE_PROJECT'), reason='EE_PROJECT not set')
def test_the_map_of_the_fire_of_lanjaron(tmp_path):
	"""The Landsat perimeter of the fire of Lanjarón (2005), its summers of 1999 to 2025 at 60 m: most pixels lost NDVI,
	and both files are written with their bands."""
	services.init()
	fire = services.burn_severity({'bbox': [-3.60, 36.88, -3.36, 37.06]}, sensor='Landsat', start='2005-06-01',
	                              end='2005-09-15', other_start='2005-10-01', other_end='2005-11-30',
	                              perimeter=str(tmp_path / 'fire.gpkg'), largest=True)
	res = services.recovery_map({'file': fire['perimeter'], 'name_field': 'region'}, 'NDVI', 'Landsat', '1999-01-01',
	                            '2025-12-31', event='2005-09-22', season=['07-01', '09-30'], resolution=60,
	                            path=str(tmp_path / 'recovery.tif'))
	s = res['summary']
	assert s['pixels'] > 5000 and s['impact_pct_median'] < -20 and 0 < s['recovered_share'] < 1
	assert os.path.exists(res['file']) and os.path.exists(res['yearly']) and res['years'][0] == 1999
	assert res['bands'] == recovery.PIXEL_BANDS
