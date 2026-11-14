"""The statistics of the RBR and the RdNBR of burn_severity over each region (mean, median, standard deviation,
coefficient of variation, percentiles 10 and 90, minimum, maximum and hectares): percentiles from a histogram of fire.PERCENTILE_BUCKETS buckets, so that a few
outliers do not make them coarse. With the default of Earth Engine, the RdNBR -16 and 4 of the unburned surroundings
of the fire of Sierra Bermeja (Sentinel-2, 2021 to 2022) gave the same percentile 10 and median (-0.049), whereas the
pixels of its GeoTIFF give -0.120 and -0.037. Without Earth Engine (a fake ee) but the last test, which computes a
synthetic index with outliers in Earth Engine (pytest -m ee, with EE_PROJECT)."""

import os
import types

import pytest

from monitoreo import fire, services


class _Reducer:
	"""A fake ee.Reducer: the reducers it combines, with their arguments."""

	def __init__(self, name, *args):
		self.parts = [(name, args)]

	def combine(self, other, prefix='', shared=False):
		assert (prefix, shared) == ('', True)  # the outputs named <band>_<statistic>
		combined = _Reducer(None)
		combined.parts = self.parts + other.parts
		return combined


class _Image:
	"""A fake ee.Image: the arguments of its reduceRegions, and the answer of Earth Engine."""

	def __init__(self, features=None):
		self.features, self.args = features, {}

	def mask(self):
		return self

	def divide(self, x):
		return self

	def updateMask(self, m):  # noqa: N802 (the names of Earth Engine)
		return self

	def rename(self, name):
		return self

	def addBands(self, other):  # noqa: N802
		return self

	def reduceRegions(self, **kwargs):  # noqa: N802
		self.args = kwargs
		return self

	def getInfo(self):  # noqa: N802
		return {'features': self.features}


@pytest.fixture
def fake_ee(monkeypatch):
	reducer = types.SimpleNamespace(**{name: (lambda name: lambda *a: _Reducer(name, *a))(name)
	                                   for name in ('mean', 'median', 'percentile', 'stdDev', 'minMax', 'sum')})
	fake = types.SimpleNamespace(Reducer=reducer, Image=types.SimpleNamespace(pixelArea=_Image))
	monkeypatch.setattr(fire, 'ee', fake)
	monkeypatch.setattr(services, 'ee', fake)


def test_the_percentiles_come_from_a_fine_histogram(fake_ee):
	"""The percentiles 10, 50 (the median) and 90 of a histogram of PERCENTILE_BUCKETS buckets: 0.0005 wide over the
	range -16 to 4 of the unburned surroundings of Sierra Bermeja, not the default of Earth Engine."""
	assert fire.PERCENTILE_BUCKETS >= 2 ** 16
	parts = fire.stats_reducer().parts
	assert parts == [('mean', ()), ('percentile', ([10, 50, 90], ['p10', 'median', 'p90'], fire.PERCENTILE_BUCKETS)),
	                 ('stdDev', ()), ('minMax', ())]
	assert not [p for p in parts if p[0] == 'median']  # ee.Reducer.median() with its default histogram
	width = 2.0 ** -20
	while (4 - -16) / width > fire.PERCENTILE_BUCKETS:  # the width of the buckets: a power of 2
		width *= 2
	assert width <= 0.0005


@pytest.mark.parametrize('band', ['rbr', 'rdnbr'])
def test_the_rows_of_the_statistics(fake_ee, band):
	"""services._burn_stats, of services._rbr and services._rdnbr: the answer of Earth Engine (<band>_<statistic> and
	ha_sum) in the rows of the answer, with the keys and order of the CSV of the RBR: also the standard deviation
	(stdDev) and the coefficient of variation, 100 × stdDev / mean (none where the mean is 0)."""
	answer = {f'{band}_mean': -0.047, f'{band}_median': -0.037, f'{band}_stdDev': 0.94, f'{band}_p10': -0.120,
	          f'{band}_p90': 0.022, f'{band}_min': -15.95, f'{band}_max': 3.80, 'ha_sum': 3708.1, 'ha_mean': 0.01,
	          'ha_p10': 0.01}
	zero = {f'{band}_mean': 0, f'{band}_median': 0, f'{band}_stdDev': 0.1, f'{band}_p10': -0.1, f'{band}_p90': 0.1,
	        f'{band}_min': -0.2, f'{band}_max': 0.2, 'ha_sum': 1.0}
	image = _Image([{'properties': dict(answer, name='Unburned surroundings (1-3 km)')},
	                {'properties': {'name': 'No data', 'ha_sum': None}},
	                {'properties': dict(zero, name='Mean of 0')}])
	rows = services._burn_stats(image, band, 'regions', 10.0, 'EPSG:32630')
	assert rows == [
		{'region': 'Unburned surroundings (1-3 km)', 'mean': -0.047, 'median': -0.037, 'std': 0.94,
		 'cv': pytest.approx(100 * 0.94 / -0.047), 'p10': -0.120, 'p90': 0.022, 'min': -15.95, 'max': 3.80,
		 'ha': 3708.1},
		{'region': 'No data', 'mean': None, 'median': None, 'std': None, 'cv': None, 'p10': None, 'p90': None,
		 'min': None, 'max': None, 'ha': 0.0},
		{'region': 'Mean of 0', 'mean': 0, 'median': 0, 'std': 0.1, 'cv': None, 'p10': -0.1, 'p90': 0.1, 'min': -0.2,
		 'max': 0.2, 'ha': 1.0},
	]
	assert [list(r) for r in rows] == [services.RBR_COLUMNS] * 3
	args = dict(image.args)
	reducer = args.pop('reducer')
	assert args == {'collection': 'regions', 'scale': 10.0, 'crs': 'EPSG:32630', 'tileScale': 4}
	assert reducer.parts == fire.stats_reducer().parts + [('sum', ())]  # and the hectares with values


def test_the_app_has_the_same_percentiles():
	"""gee/core.js, the port of the app, computes the statistics with the same histogram."""
	from test_rgb_gee import _js_value, _read
	core = _read('core.js')
	assert _js_value(core, 'PERCENTILE_BUCKETS') == fire.PERCENTILE_BUCKETS
	assert ("ee.Reducer.percentile([10, 50, 90], ['p10', 'median', 'p90'], PERCENTILE_BUCKETS)" in
	        core.split('function burnStatsReducer')[1].split('function ')[0])
	assert 'ee.Reducer.median()' not in core.split('function burnStatsReducer')[1].split('function ')[0]
	assert 'ee.Reducer.stdDev()' in core.split('function burnStatsReducer')[1].split('function ')[0]
	assert _js_value(core, 'RBR_COLUMNS') == services.RBR_COLUMNS  # the columns of its CSV


# With Earth Engine --------------------------------------------------------------------------------------------------

@pytest.mark.ee
@pytest.mark.skipif(not os.environ.get('EE_PROJECT'), reason='EE_PROJECT not set')
def test_the_percentiles_of_a_burn_index_with_outliers():
	"""A synthetic RdNBR of 400 x 250 pixels of 20 m (UTM 30N): -0.12 to 0 from west to east, but the southern row, of
	-16 (its western half) and 4 (its eastern half), like the unburned surroundings of the fire of Sierra Bermeja. Its
	percentiles 10, 50 and 90 are within 0.001 of those of its pixels (with the default of Earth Engine, all three
	were -0.060), and its mean, minimum, maximum and hectares are those of its pixels."""
	import ee
	import numpy as np
	services.init()
	x0, y0, res, nx, ny = 300000, 4100000, 20, 400, 250
	utm = ee.Projection('EPSG:32630')
	xy = ee.Image.pixelCoordinates(utm)
	i = xy.select('x').subtract(x0).divide(res).floor()  # the column and the row of each pixel
	j = xy.select('y').subtract(y0).divide(res).floor()
	outliers = ee.Image.constant(-16).where(i.gte(nx // 2), 4)
	rdnbr = i.multiply(0.12 / (nx - 1)).subtract(0.12).where(j.eq(0), outliers).rename('rdnbr')
	box = ee.Geometry.Rectangle([x0, y0, x0 + nx * res, y0 + ny * res], utm, False)
	regions = ee.FeatureCollection([ee.Feature(box, {'name': 'unburned'})])
	(row,) = services._burn_stats(rdnbr, 'rdnbr', regions, res, 'EPSG:32630')
	cols, rows = np.meshgrid(np.arange(nx), np.arange(ny))
	pixels = cols * (0.12 / (nx - 1)) - 0.12
	pixels[rows == 0] = np.where(cols[rows == 0] >= nx // 2, 4, -16)
	p10, median, p90 = np.percentile(pixels, [10, 50, 90])
	assert (p10, median, p90) == pytest.approx((-0.108, -0.06, -0.012), abs=1e-3)
	assert row['region'] == 'unburned'
	assert row['p10'] < row['median'] < row['p90']
	assert (row['p10'], row['median'], row['p90']) == pytest.approx((p10, median, p90), abs=1e-3)
	assert (row['min'], row['max']) == (-16, 4) and row['mean'] == pytest.approx(pixels.mean(), abs=1e-6)
	assert row['ha'] == pytest.approx(nx * ny * res ** 2 / 1e4, rel=1e-3)
