"""The search of the Earth Engine data catalog (monitoreo.eecatalog, services.find_datasets), without Earth Engine nor
the internet (the copy of its index in the package): the words, dates, area and kind, its errors, the command line,
the MCP server, the assistant, R and the Earth Engine app (gee/core.js in Node: the same search on its slim copy)."""

import datetime as dt
import json
import os
import shutil
import subprocess

import pytest

from monitoreo import eecatalog, services

GEE = os.path.join(os.path.dirname(__file__), '..', 'gee')


def test_the_copy_of_the_index():
	data = eecatalog.load()
	ids = {d['id'] for d in data['datasets']}
	assert len(ids) > 500 and {'COPERNICUS/S2_SR_HARMONIZED', 'MODIS/061/MOD13Q1', 'LANDSAT/LC08/C02/T1_L2'} <= ids
	assert all(d['type'] in eecatalog.RASTERS for d in data['datasets'])
	assert data['source'] == eecatalog.ROOT and data['downloaded']


def test_the_search():
	snow = eecatalog.search('snow cover', limit=3)
	assert snow[0]['id'] == 'MODIS/061/MOD10A1' and snow[0]['page'].endswith('/MODIS_061_MOD10A1')
	assert [d['id'] for d in eecatalog.search('sentinel-2', kind='image_collection', limit=50)
	        if d['id'] == 'COPERNICUS/S2_SR_HARMONIZED']  # sentinel-2 is a word, not sentinel and 2
	# dates: Sentinel-2 has no data in 2010
	assert 'COPERNICUS/S2_SR_HARMONIZED' not in [d['id'] for d in eecatalog.search('sentinel-2', start='2010-01-01',
	                                                                                end='2010-12-31', limit=100)]
	# an area outside every dataset of one region (the bbox of the Mar Menor is in the global ones)
	assert eecatalog.search('precipitation', bbox=[-1.0, 37.6, -0.7, 37.8], limit=5)
	assert all(d['type'] == 'image' for d in eecatalog.search('elevation', kind='image', limit=10))
	assert len(eecatalog.search(limit=1000)) == eecatalog.MAX_LIMIT
	for kwargs, text in (({'kind': 'table'}, 'unknown kind'), ({'start': '2020-13-01'}, 'a date'),
	                     ({'bbox': [10, 0, 0, 1]}, 'west, south'), ({'start': '2021-01-01', 'end': '2020-01-01'},
	                                                               'before start')):
		with pytest.raises(ValueError, match=text):
			eecatalog.search('x', **kwargs)
	assert services.find_datasets('snow cover', limit=1)[0]['id'] == 'MODIS/061/MOD10A1'


def test_the_images_whatever_their_dates():
	"""The dates are those of the collections of images: an image is a fixed layer, computed without dates (a DEM, the
	climate of WorldClim), so a search with the period of QGIS or of the app finds it too."""
	ids = [d['id'] for d in services.find_datasets('worldclim', '2020-01-01', '2021-12-31', limit=100)]
	assert 'WORLDCLIM/V1/BIO' in ids  # 1960-1991
	srtm = [d['id'] for d in eecatalog.search('srtm', start='2020-01-01', end='2021-12-31', limit=100)]
	assert {'USGS/SRTMGL1_003', 'CGIAR/SRTM90_V4'} <= set(srtm)
	images = lambda **dates: [d['id'] for d in eecatalog.search('elevation', kind='image', limit=100, **dates)]  # noqa: E731
	assert images(start='2020-01-01', end='2024-12-31') == images()
	# the collections, by their dates (Landsat 5 ended in 2012)
	assert 'LANDSAT/LT05/C02/T1_L2' not in [d['id'] for d in eecatalog.search('landsat', start='2020-01-01', limit=100)]


def test_the_collections_that_go_on():
	"""The record of a collection says the day of its last image, also when it goes on: in the copy, a collection whose
	last image is at most OPEN days older than the copy has no end, so it is found after the copy and goes 'to now'."""
	day = dt.date(2026, 11, 14)

	def record(kind, end):
		return eecatalog._record({'id': 'X', 'title': 'X', 'gee:type': kind,
		                          'extent': {'temporal': {'interval': [['2000-01-01T00:00:00Z', end]]}}}, day)

	assert 'end' not in record('image_collection', '2026-11-14T09:48:16Z')  # the day of the copy
	assert 'end' not in record('image_collection', '2026-10-01T00:00:00Z')  # a delay of some weeks (ERA5-Land)
	assert record('image_collection', '2012-05-05T00:00:00Z')['end'] == '2012-05-05'  # ended
	assert record('image_collection', '2100-12-31T00:00:00Z')['end'] == '2100-12-31'  # projections: after the copy
	assert record('image', '2026-11-01T00:00:00Z')['end'] == '2026-11-01'  # an image does not go on
	assert eecatalog._record({'id': 'X', 'gee:type': 'image_collection', 'extent': {'temporal': {'interval': [
		['2000-01-01', '2026-11-14']]}}})['end'] == '2026-11-14'  # without the day of the copy, as it is
	data = {d['id']: d for d in eecatalog.load()['datasets']}
	for asset in ('COPERNICUS/S2_SR_HARMONIZED', 'LANDSAT/LC08/C02/T1_L2', 'MODIS/061/MOD13Q1',
	              'ECMWF/ERA5_LAND/MONTHLY_AGGR'):
		assert 'end' not in data[asset], asset
	assert data['NASA/GDDP-CMIP6']['end'] == '2100-12-31' and data['LANDSAT/LT05/C02/T1_L2']['end'] == '2012-05-05'
	after = [d['id'] for d in eecatalog.search('sentinel-2', start='2027-01-01', end='2027-06-30', limit=100)]
	assert 'COPERNICUS/S2_SR_HARMONIZED' in after
	from monitoreo import assistant
	text = assistant.data_text('find_datasets', json.dumps(services.find_datasets('sentinel-2 surface reflectance')))
	assert '- NASA/HLS/HLSS30/v002 (image collection, 2015-11-28 to now' in text


def test_the_tools(monkeypatch, tmp_path, capsys):
	from monitoreo import assistant, cli
	cli.main(['datasets', 'snow', 'cover', '--limit', '2'])
	out = capsys.readouterr().out
	assert 'MODIS/061/MOD10A1' in out and '2 datasets of the Earth Engine data catalog' in out
	# the area, with a west below 0: four numbers, or W,S,E,N (argparse reads -3.6,36.9,... alone as an option)
	for bbox in (['--bbox', '-3.6', '36.9', '-2.6', '37.3'], ['--bbox=-3.6,36.9,-2.6,37.3'],
	             ['--bbox', '-3.6,36.9,-2.6,37.3']):
		cli.main(['datasets', 'soil', 'moisture', *bbox, '--limit', '3'])
		assert 'NASA/SMAP/SPL3SMP_E/005' in capsys.readouterr().out, bbox
	with pytest.raises(SystemExit):
		cli.main(['datasets', 'soil', '--bbox', '-3.6', '36.9', '-2.6'])
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	rows = json.loads(mcp_server.find_datasets('snow cover', limit=2))
	assert rows[0]['id'] == 'MODIS/061/MOD10A1' and 'find_datasets' in mcp_server.INSTRUCTIONS
	# an ID that find_datasets gives is valid: said where the instructions say which ones are
	assert 'describe_asset, find_datasets, community_datasets' in ' '.join(mcp_server.INSTRUCTIONS.split())
	assert 'the user gives it, find_datasets finds those of the Earth Engine data catalog' in assistant.instructions()
	assert 'find_datasets' in assistant.ADVICE and 'find_datasets' in mcp_server.NO_EECU_WARNING
	text = assistant.data_text('find_datasets', json.dumps(rows))
	assert text.startswith('2 datasets of the Earth Engine data catalog') and '- MODIS/061/MOD10A1 (image collection' in text
	assert assistant.data_text('find_datasets', '[]').startswith('No dataset of the Earth Engine data catalog')


APP = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
global.ee = new Proxy({}, {get: function () { return function () { return {}; }; }});
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[1], f), 'utf8'), {filename: f});
});
var mo = global.MonitorEO;
process.stdout.write(JSON.stringify(input.queries.map(function (q) {
	return mo.searchCatalog(q[0], q[1], q[2], 10).map(function (d) { return d.id; });
})));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_app_searches_the_same(monkeypatch):
	"""The app searches the title, ID and keywords (its copy has no descriptions nor providers): the same order as
	Python on the same fields."""
	import importlib.util
	spec = importlib.util.spec_from_file_location('monitoreo_gee_build', os.path.join(GEE, 'build.py'))
	build = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(build)
	with open(os.path.join(GEE, 'catalog.js'), encoding='utf-8') as f:
		text = f.read()
	assert json.loads(text[text.index('{'):text.rstrip().rindex('}') + 1])['eecatalog'] == build.eecatalog_index(), \
		'run gee/build.py --indexes-only: the app has another index of the Earth Engine data catalog'
	queries = [('snow cover', None, None), ('land surface temperature modis', 2010, 2015), ('burned area', None, 2019),
	           ('sentinel-2', 2018, 2020), ('worldclim', 2025, 2025), ('srtm', 2020, 2021), ('sentinel-2', 2027, 2027)]
	run = subprocess.run(['node', '-e', APP, GEE], input=json.dumps({'queries': queries}), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	got = json.loads(run.stdout)
	assert 'WORLDCLIM/V1/BIO' in got[4] and 'COPERNICUS/S2_SR_HARMONIZED' in got[6]  # the images; what goes on
	data = eecatalog.load()
	slim = dict(data, datasets=[{k: v for k, v in d.items() if k not in ('provider', 'description')}
	                            for d in data['datasets']])
	monkeypatch.setattr(eecatalog, 'load', lambda: slim)
	for (q, a, b), ids in zip(queries, got):
		expected = eecatalog.search(q, f'{a}-01-01' if a else None, f'{b}-12-31' if b else None, limit=10)
		assert ids == [d['id'] for d in expected], q
