"""The maps of the QGIS plugin always on the pixels of the data (issue #86): services.check_pixels, before computing,
says whether the grid of a region fits in the most pixels a tool downloads and, if not, raises TooManyPixels with by
how much it exceeds them and what to change (the sensors of the variable whose map fits, a smaller region, Google
Drive). A large area (more than 100,000 km²) has pixels of 1 to 10 km by default (areas.default_scale), so its map
fits. Without Earth Engine: the region and its grid are faked."""

import types

import pytest

from monitoreo import services

MAX = 4_000_000


@pytest.fixture
def grid(monkeypatch):
	"""The grid of the region faked: AREA m² (the extent of its bounds, and of the region, a box), so its pixels are
	AREA / res²."""
	state = {'area': 0.0, 'res': [], 'asked': 0}

	def fake_grid(regions, res, crs):
		state['res'].append(res)
		return types.SimpleNamespace(pixels=int(state['area'] / res ** 2), crs='EPSG:32630')

	def fake_area(regions):  # the area of the biggest feature: asked only for bounds of a large area
		state['asked'] += 1
		return state['area']
	monkeypatch.setattr(services, '_grid', fake_grid)
	monkeypatch.setattr(services.areas, 'region', lambda region: region)
	monkeypatch.setattr(services.areas, 'max_area', fake_area)
	return state


def test_a_region_that_fits_is_computed_on_the_pixels_of_the_data(grid):
	grid['area'] = 3_000_000 * 30.0 ** 2
	out = services.check_pixels({'bbox': [0, 0, 1, 1]}, MAX, 'NDVI', 'Landsat', start='2023-01-01', end='2026-10-30')
	assert out == {'pixels': 3_000_000, 'max_pixels': MAX, 'resolution': 30.0} and grid['res'] == [30.0]


def test_a_bigger_region_says_by_how_much_and_which_sensors_fit(grid):
	grid['area'] = 480_000_000 * 30.0 ** 2  # the example of the issue: Landsat, 480 million pixels at 30 m
	with pytest.raises(services.TooManyPixels) as e:  # on the pixels of the data: a large area is 1 to 10 km else
		services.check_pixels({'bbox': [0, 0, 1, 1]}, MAX, 'NDVI', 'Landsat', resolution=30, start='2023-01-01',
		                      end='2026-10-30', step='monthly')  # not an argument of the variable: ignored
	e = e.value
	assert (e.pixels, e.max_pixels, e.resolution, e.excess) == (480_000_000, MAX, 30.0, 11_900)
	assert e.sensors == []  # MODIS at 250 m would have 6.9 million pixels: too many as well
	assert round(e.share, 2) == 0.83
	assert '11,900% more than the 4,000,000' in str(e) and 'at most 0.83% of its extent' in str(e)
	assert 'Google Drive' in str(e) and 'another sensor' not in str(e)


def test_the_sensors_whose_map_fits_from_the_finest(grid):
	grid['area'] = 40_000_000 * 10.0 ** 2  # Sentinel-2: 40 million pixels at 10 m, 900% more
	with pytest.raises(services.TooManyPixels) as e:
		services.check_pixels({'bbox': [0, 0, 1, 1]}, MAX, 'NDVI', 'Sentinel-2', start='2025-01-01', end='2025-12-31')
	assert e.value.excess == 900
	assert [(s['sensor'], s['resolution']) for s in e.value.sensors] == [('Modis', 250.0)]  # Landsat: 4.4 million
	assert 'another sensor (Modis (250 m))' in str(e.value)


def test_only_the_sensors_given(grid):
	"""The burn severity proposes only the sensors of its index (no MODIS for the dNBR)."""
	grid['area'] = 5_000_000 * 20.0 ** 2  # Sentinel-2: 5 million pixels at 20 m (B12)
	with pytest.raises(services.TooManyPixels) as e:
		services.check_pixels({'bbox': [0, 0, 1, 1]}, MAX, 'RdNBR', 'Sentinel-2', start='2025-06-01', end='2025-07-31',
		                      two_periods=True,
		                      sensors=('Sentinel-2', 'Landsat'))
	assert [s['sensor'] for s in e.value.sensors] == ['Landsat']
	with pytest.raises(services.TooManyPixels) as e:
		services.check_pixels({'bbox': [0, 0, 1, 1]}, MAX, 'RdNBR', 'Sentinel-2', start='2025-06-01', end='2025-07-31',
		                      two_periods=True)
	assert [s['sensor'] for s in e.value.sensors] == ['Landsat', 'Modis']


def test_the_period_does_not_change_the_pixels(grid):
	grid['area'] = 5_000_000 * 30.0 ** 2
	excess = set()
	for start, end in (('2023-01-01', '2023-01-31'), ('1990-01-01', '2026-10-30')):
		with pytest.raises(services.TooManyPixels) as e:
			services.check_pixels({'bbox': [0, 0, 1, 1]}, MAX, 'NDVI', 'Landsat', start=start, end=end)
		excess.add(e.value.excess)
	assert excess == {25}


def test_the_percentages_are_exact_and_safe(grid):
	"""The excess rounded up without floating error, and the share of the extent rounded down (a region of it fits)."""
	for pixels, excess, share in ((4_400_000, 10, 90), (4_040_000, 1, 99), (4_000_001, 1, 99), (12_000_000, 200, 33),
	                              (4_000_000 * 120, 11_900, 0.83), (4_000_000 * 1000, 99_900, 0.1)):
		e = services.TooManyPixels(pixels, MAX, 10.0)
		assert e.excess == excess and abs(e.share - share) < 1e-9, (pixels, e.excess, e.share)
		assert 'e+' not in str(e)


def test_a_true_colour_proposes_only_sensors_with_one(grid):
	grid['area'] = 40_000_000 * 10.0 ** 2  # NDVI of Sentinel-2: MODIS (250 m) fits, but has no true colour
	with pytest.raises(services.TooManyPixels) as e:
		services.check_pixels({'bbox': [0, 0, 1, 1]}, MAX, 'NDVI', 'Sentinel-2', start='2025-01-01', end='2025-12-31',
		                      rgb=True)
	assert e.value.sensors == [] and 'another sensor' not in str(e.value)



@pytest.mark.parametrize('variable, sensor, km2, metres', [
	('NDVI', 'Landsat', 432_000, 1000.0),       # the region of the issue: 1 km, 432,000 pixels
	('NDVI', 'Sentinel-2', 120_000, 1000.0),    # just over 100,000 km²: 1 km, never 10 m
	('NDVI', 'Modis', 3_000_000, 2000.0),       # about a million pixels
	('Chl-a', 'Modis', 476_707, 4616.0),        # the western Mediterranean: the 4.6 km of the data
	('Chl-a', 'Modis', 76_681_173, 10000.0),    # the South Pacific Ocean: at most 10 km
	('PRECIP', 'TerraClimate', 76_681_173, 10000.0),
])
def test_a_large_area_is_computed_on_pixels_of_1_to_10_km(grid, variable, sensor, km2, metres):
	"""More than 100,000 km² (a country, a biome, most seas): pixels of 1 to 10 km by default, never finer than the
	data, and its map fits; the area of the region is asked only because its bounds are of a large area."""
	grid['area'] = km2 * 1e6
	out = services.check_pixels({'bbox': [0, 0, 1, 1]}, MAX, variable, sensor, start='2023-01-01', end='2023-12-31')
	assert out['resolution'] == metres and out['pixels'] <= MAX and grid['asked'] == 1


def test_the_area_is_asked_only_for_bounds_of_a_large_area(grid):
	grid['area'] = 99_000 * 1e6  # bounds of less than 100,000 km²: the pixels of the data, nothing more asked
	with pytest.raises(services.TooManyPixels):
		services.check_pixels({'bbox': [0, 0, 1, 1]}, MAX, 'NDVI', 'Sentinel-2', start='2025-01-01', end='2025-12-31')
	assert grid['asked'] == 0 and grid['res'] == [10.0]
	grid['area'] = 432_000 * 1e6  # a resolution given is the resolution
	with pytest.raises(services.TooManyPixels):
		services.check_pixels({'bbox': [0, 0, 1, 1]}, MAX, 'NDVI', 'Landsat', resolution=30, start='2023-01-01',
		                      end='2023-12-31')
	assert grid['asked'] == 0
