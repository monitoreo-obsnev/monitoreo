"""The maps of MonitorEO on those of geemap (monitoreo.notebook), without Earth Engine nor geemap: a geemap faked that
keeps what is asked of it, and the Earth Engine of the maps faked (the composites and their colours). With geemap and
Earth Engine, the same functions were run on the box of tests/test_ee.py."""

import sys
import types

import pytest

from monitoreo import maps, notebook, services, timeseries
from monitoreo import variable as variables

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}


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
		def __getattr__(self, name):
			return lambda *a, **k: self

		def getInfo(self):
			return {'reference_p5': 0.2, 'reference_p95': 0.6, 'other_p5': 0.1, 'other_p95': 0.7}
	ee = Ee()
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
	assert {'tucker1979', 'gorelick2017', 'monitoreo'} <= {r['id'] for r in out['references']}


def test_two_periods_on_a_split_map(geemap):
	m, out = notebook.compare(REGION, 'NDVI', 'Modis', '2005-06-01', '2005-08-31', '2023-06-01', '2023-08-31')
	split = next(c for c in m.calls if c[0] == 'split_map')
	assert split[2]['left_label'] == '2005-06-01 / 2005-08-31' and split[2]['right_label'] == '2023-06-01 / 2023-08-31'
	assert (out['min'], out['max']) == (0.1, 0.8)  # one range for both


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
	with pytest.raises(ValueError, match=r'pip install "monitoreo\[notebook\]"'):
		notebook.Map()


def test_the_extra_of_the_package():
	import tomllib
	with open(__file__.rsplit('/tests/', 1)[0] + '/pyproject.toml', 'rb') as f:
		extras = tomllib.load(f)['project']['optional-dependencies']
	assert any(d.startswith('geemap') for d in extras['notebook'])
	assert timeseries.bins  # the steps of the slider are those of the series
