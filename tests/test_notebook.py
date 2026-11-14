"""The maps of MonitorEO on those of geemap (monitoreo.notebook), without Earth Engine nor geemap: a geemap faked that
keeps what is asked of it, and the Earth Engine of the maps faked (the composites and their colours). With geemap and
Earth Engine, the same functions were run on the box of tests/test_ee.py."""

import datetime as dt
import sys
import types

import pytest

from monitoreo import maps, notebook, services, timeseries
from monitoreo import variable as variables

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
VIS_PARAMS = maps.vis_params  # the colours of the maps, which the fixture fakes


class FakeMap:
	def __init__(self, **kwargs):
		self.kwargs, self.calls = kwargs, []

	def __getattr__(self, name):
		def call(*args, **kwargs):
			self.calls.append((name, args, kwargs))
		return call


@pytest.fixture
def geemap(monkeypatch):
	fake = types.ModuleType('geemap')
	fake.Map = FakeMap
	fake.ee_tile_layer = lambda img, vis, name: ('tiles', name, vis)
	monkeypatch.setitem(sys.modules, 'geemap', fake)

	class Ee:  # an Earth Engine object that answers everything with itself
		stats = {'reference_p5': 0.2, 'reference_p95': 0.6, 'other_p5': 0.1, 'other_p95': 0.7}  # or an error

		def __getattr__(self, name):
			return lambda *a, **k: self

		def getInfo(self):
			if isinstance(self.stats, Exception):
				raise self.stats
			return self.stats
	ee = Ee()
	fake.ee = ee  # the Earth Engine faked, for the tests to change its answers
	monkeypatch.setattr(services, '_build', lambda *a, **k: (services.make_spec('NDVI', 'Sentinel-2', '2023-06-01',
	                                                                           '2023-08-31', metric='median'),
	                                                            ee, ee, 10.0))
	monkeypatch.setattr(services, '_comparison', lambda *a, **k: (None, ee, ee, 250.0, 'NDVI'))
	monkeypatch.setattr(services.areas, 'region', lambda region: ee)
	monkeypatch.setattr(variables, 'image', lambda *a, **k: ee)
	monkeypatch.setattr(variables, 'collection', lambda *a, **k: ee)
	monkeypatch.setattr(services.composite, '_reduce', lambda *a, **k: ee)
	monkeypatch.setattr(maps, 'vis_params', lambda *a, **k: {'min': 0.1, 'max': 0.8, 'palette': ['ff0000', '00ff00']})
	monkeypatch.setattr(notebook.ee, 'Image', lambda *a: ee)
	monkeypatch.setattr(notebook.ee.Reducer, 'percentile', staticmethod(lambda *a: ee))
	monkeypatch.setattr(notebook.ee, 'Date', lambda *a: ee)
	monkeypatch.setattr(notebook.ee.ImageCollection, 'fromImages', staticmethod(lambda imgs: ('collection', len(imgs))))
	return fake


def test_a_map_on_a_map_of_geemap(geemap):
	m = notebook.Map()
	out = notebook.add_map(m, REGION, 'NDVI', 'Sentinel-2', '2023-06-01', '2023-08-31')
	names = [c[0] for c in m.calls]
	assert names == ['add_layer', 'add_layer', 'add_colorbar', 'add_text', 'center_object']
	assert m.calls[0][1][1] == {'min': 0.1, 'max': 0.8, 'palette': ['ff0000', '00ff00']}
	assert m.calls[2][2]['label'].startswith('NDVI Sentinel-2') and 'Copernicus Sentinel' in m.calls[3][1][0]
	assert {'tucker1979', 'gorelick2017', 'monitoreo', 'wu2020'} <= {r['id'] for r in out['references']}


def test_two_periods_on_a_split_map(geemap):
	m, out = notebook.compare(REGION, 'NDVI', 'Modis', '2005-06-01', '2005-08-31', '2023-06-01', '2023-08-31')
	split = next(c for c in m.calls if c[0] == 'split_map')
	assert split[2]['left_label'] == '2005-06-01 / 2005-08-31' and split[2]['right_label'] == '2023-06-01 / 2023-08-31'
	assert (out['min'], out['max']) == (0.1, 0.8)  # one range for both
	# as the other maps: the outline of the region, the colour bar with its unit and the reference of geemap
	names = [c[0] for c in m.calls]
	assert names == ['split_map', 'add_layer', 'add_colorbar', 'center_object', 'add_text']
	bar = m.calls[2][2]
	assert bar['label'] == 'NDVI Modis (median)' and bar['vis_params'] == {k: out[k] for k in ('min', 'max', 'palette')}
	assert {'gorelick2017', 'monitoreo', 'wu2020'} <= {r['id'] for r in out['references']}
	# without the end of the reference period, the label is the period computed (up to today), not "/ None"
	m, out = notebook.compare(REGION, 'NDVI', 'Modis', '2005-06-01', None, '2023-06-01', '2023-08-31')
	split = next(c for c in m.calls if c[0] == 'split_map')
	assert split[2]['left_label'] == f'2005-06-01 / {dt.date.today().isoformat()}'


def test_the_colours_of_a_split_map_without_pixels_or_memory(geemap, monkeypatch):
	monkeypatch.setattr(maps, 'vis_params', VIS_PARAMS)
	args = (REGION, 'NDVI', 'Modis', '2005-06-01', '2005-08-31', '2023-06-01', '2023-08-31')
	_, out = notebook.compare(*args)
	assert (out['min'], out['max']) == (0.1, 0.7)  # the lowest percentile 5 and the highest 95 of both periods
	# no pixels in both periods (all masked): the range of the catalog, as map_layer and compare_map
	geemap.ee.stats = {'reference_p5': None, 'reference_p95': None, 'other_p5': None, 'other_p95': None}
	_, out = notebook.compare(*args)
	assert (out['min'], out['max']) == (-0.2, 1.0)
	_, out = notebook.compare(*args, vmin=0)  # what is given is kept
	assert (out['min'], out['max']) == (0.0, 1.0)
	# Earth Engine cannot compute them (out of memory): the range of the catalog too
	geemap.ee.stats = notebook.ee.EEException('User memory limit exceeded.')
	_, out = notebook.compare(*args)
	assert (out['min'], out['max']) == (-0.2, 1.0)


def test_the_method_of_the_coefficient_of_variation_is_cited(geemap):
	def ids(out):
		return {r['id'] for r in out['references']}
	_, out = notebook.compare(REGION, 'NDVI', 'Modis', '2005-06-01', '2005-08-31', '2023-06-01', '2023-08-31', metric='cv')
	assert 'pearson1896' in ids(out)
	_, out = notebook.compare(REGION, 'NDVI', 'Modis', '2005-01-01', '2007-12-31', '2021-01-01', '2023-12-31',
	                          temporal='annual', interannual='cv')
	assert 'pearson1896' in ids(out)
	_, out = notebook.compare(REGION, 'NDVI', 'Modis', '2005-06-01', '2005-08-31', '2023-06-01', '2023-08-31')
	assert 'pearson1896' not in ids(out)
	out = notebook.time_slider(notebook.Map(), REGION, 'NDVI', 'Modis', '2019-01-01', '2023-12-31', metric='cv')
	assert {'pearson1896', 'wu2020'} <= ids(out)
	out = notebook.add_map(notebook.Map(), REGION, 'NDVI', 'Sentinel-2', '2023-06-01', '2023-08-31', metric='cv')
	assert {'pearson1896', 'wu2020'} <= ids(out)


def test_a_time_slider(geemap):
	m = notebook.Map()
	out = notebook.time_slider(m, REGION, 'NDVI', 'Modis', '2019-01-01', '2023-12-31')
	slider = next(c for c in m.calls if c[0] == 'add_time_slider')
	assert slider[1][0] == ('collection', 5) and slider[2]['labels'] == ['2019', '2020', '2021', '2022', '2023']
	assert out['labels'] == slider[2]['labels']
	with pytest.raises(ValueError, match='unknown step'):
		notebook.time_slider(m, REGION, 'NDVI', 'Modis', '2019-01-01', '2023-12-31', step='daily')


def test_without_geemap(monkeypatch):
	monkeypatch.setitem(sys.modules, 'geemap', None)
	with pytest.raises(ValueError, match=r'pip install "monitoreo\[notebook\] @ https://github.com/monitoreo-obsnev/'):
		notebook.Map()


def test_the_extra_of_the_package():
	import tomllib
	with open(__file__.rsplit('/tests/', 1)[0] + '/pyproject.toml', 'rb') as f:
		extras = tomllib.load(f)['project']['optional-dependencies']
	assert any(d.startswith('geemap') for d in extras['notebook'])
	assert timeseries.bins  # the steps of the slider are those of the series
