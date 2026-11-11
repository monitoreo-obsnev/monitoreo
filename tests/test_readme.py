"""Tests of the documentation of the files of MonitorEO (monitoreo.readme) and of their units, without Earth Engine:
the README next to the files of each result, the metadata of the GeoTIFFs, the README of the folders of a recipe and
the units in UDUNITS."""

import json
import os

import pytest

from monitoreo import __version__, catalog, readme, services, timeseries, variable

gdal = pytest.importorskip('osgeo.gdal')
gdal.UseExceptions()

ARGS = {'region': {'wdpa_id': 389011}, 'variable': 'LST', 'sensor': 'Modis', 'start': '2021-06-01',
        'end': '2021-08-31', 'step': 'monthly'}


def _tif(path, bands=None):
	ds = gdal.GetDriverByName('GTiff').Create(str(path), 4, 3, len(bands or [None]), gdal.GDT_Float32)
	ds.SetGeoTransform([450000, 250, 0, 4110000, 0, -250])
	ds.SetProjection('EPSG:32630')
	for i, b in enumerate(bands or []):
		ds.GetRasterBand(i + 1).SetDescription(b)
	ds = None
	return str(path)


def test_units():
	units = {e['unit'] for e in catalog.variables()}
	assert not [u for u in units if 'º' in u], 'the degree sign is °, not the ordinal indicator º'
	assert units <= set(catalog.UDUNITS), f'units without UDUNITS: {units - set(catalog.UDUNITS)}'
	assert catalog.udunits('[°C]') == 'degC' and catalog.udunits('[ºC]') == 'degC'  # also old answers
	assert catalog.udunits('[unitless]') == '1' and catalog.udunits('[unitless]', per_year=True) == 'year-1'
	assert catalog.udunits('[kg/m²/8 days]', per_year=True) == 'kg m-2 (8 day)-1 year-1'
	assert catalog.udunits('') == '' and catalog.udunits('[furlongs]', per_year=True) == ''
	d = variable.describe(services.make_spec('LST', 'Modis', '2021-06-01', '2021-08-31', metric='median'))
	assert d['udunits'] == 'degC' and d['period'] == ['2021-06-01', '2021-08-31'] and d['metric'] == 'median'
	assert 'interannual' not in d  # only with an aggregation by year, month or 16 days


def test_csv_readme(tmp_path):
	"""The README of a time series: its files, how it was computed, its columns with units, the empty cells, how to
	reproduce it (without the paths of its files) and the references."""
	csv = str(tmp_path / 'LST_Modis_monthly.csv')
	rows = [{'region': 'Sierra Nevada', 'date': '2021-06-01', 'value': 21.5, 'n_pixels': 900, 'n_images': 30},
	        {'region': 'Sierra Nevada', 'date': '2021-07-01', 'value': None, 'n_pixels': 0, 'n_images': 0}]
	timeseries.write_csv(rows, csv, {'variable': 'LST', 'sensor': 'Modis', 'unit': catalog.udunits('[°C]')})
	assert open(csv, encoding='utf-8').read().splitlines()[2].startswith('Sierra Nevada,2021-07-01,,0,0')

	def time_series(region, variable=None, sensor=None, start=None, end=None, step='monthly', metric='mean',
	                stat='mean', csv=None, **source):
		return {'rows': rows, 'csv': csv, 'unit': '[°C]', 'scale': 1000, 'title': 'LST'}

	out = services._cited(time_series)(csv=csv, **ARGS)
	assert out['readme'] == str(tmp_path / 'LST_Modis_monthly.README.txt')
	text = open(out['readme'], encoding='utf-8').read()
	assert text.startswith('README of LST_Modis_monthly.csv') and f'MonitorEO {__version__}' in text
	assert 'Monthly time series of LST (MODIS), 1 Jun 2021 - 31 Aug 2021' in text and 'Region: Protected area WDPA 389011' in text
	assert 'value: value of the variable (°C)' in text and 'unit: unit of the variable in UDUNITS' in text
	assert 'in UDUNITS (the units of the CF conventions), degC.' in ' '.join(text.split())
	assert 'Empty cells: no data' in text and "mo.time_series(region={\"wdpa_id\": 389011}" in text
	assert 'csv=' not in text.split('TO REPRODUCE IT')[1].split('HOW TO CITE')[0]  # not the path of the file
	assert 'Wan, Z., & Dozier, J. (1996)' in text and 'https://doi.org/10.5067/MODIS/MOD11A1.061' in text
	assert all(len(line) <= readme.WIDTH for line in text.splitlines() if 'https://' not in line)


def test_geotiff_metadata(tmp_path):
	"""The GeoTIFF of a map: the call, the version, when, the references, and the name and unit of its band."""
	path = str(tmp_path / 'lst.tif')

	def download_image(region, variable=None, sensor=None, start=None, end=None, metric='median', path=None,
	                   progress=None, **source):
		_tif(path)
		return {'file': path, 'unit': '[°C]', 'images': 61}

	out = services._cited(download_image)(path=path, progress=print, **{k: v for k, v in ARGS.items() if k != 'step'})
	ds = gdal.Open(path)
	md = ds.GetMetadata()
	call = json.loads(md['call'])
	assert call['tool'] == 'download_image' and call['args']['variable'] == 'LST' and 'path' not in call['args']
	assert 'progress' not in call['args'] and md['monitoreo_version'] == __version__ and md['computed'][:2] == '20'
	assert 'https://doi.org/10.1016/j.rse.2017.06.031' in md['references']
	band = ds.GetRasterBand(1)
	assert (band.GetDescription(), band.GetUnitType()) == ('value', 'degC')
	text = open(out['readme'], encoding='utf-8').read()
	assert 'BANDS OF lst.tif' in text and '4 x 3 pixels of 250 m in EPSG:32630' in text
	assert '1 value: Value of the variable (degC)' in text


def test_fixed_layers_and_scf():
	"""The README of a fixed layer (elevation, slope) has no period, temporal metric or pixel filters, even if the
	call gives them (QGIS sends its greyed-out dates), and that of the SCF its fixed filters, whatever the quality."""
	from monitoreo import report
	region = {'wdpa_id': 389011}
	for tool in ('download_image', 'map_layer', 'region_stats'):
		args = {'region': region, 'variable': 'SLOPE', 'sensor': 'Copernicus', 'start': '2025-01-01',
		        'end': '2025-12-31', 'metric': 'median', 'quality': {'clouds': True}}
		facts = dict(report.item_facts(tool, args))
		assert not {'Period', 'Temporal metric', 'Discarded pixels'} & set(facts), tool
		assert facts['Method'] == report.METHODS['static'] and '2025' not in report.item_title(tool, args)
	scf = dict(report.item_facts('download_image', {'region': region, 'variable': 'SCF', 'sensor': 'Landsat',
	                                                'start': '2001-01-01', 'end': '2024-12-31', 'metric': 'mean',
	                                                'quality': {'clouds': False, 'snow': True}}))
	assert scf['Discarded pixels'] == 'clouds, water' and scf['Temporal metric'] == 'mean'
	d = variable.describe({'index': 'ELEVATION', 'sensor': 'Copernicus', 'period': ['2018-01-01', '2021-12-31'],
	                       'season': ['06-01', '08-31'], 'metric': None, 'quality': {}})
	assert d['udunits'] == 'm' and not {'period', 'season', 'metric'} & set(d)


def test_trend_bands(tmp_path):
	path = _tif(tmp_path / 'trend.tif', ['slope', 'tau', 'z', 'p_value', 'intercept', 'n'])
	readme.tag(path, 'download_trend', dict(ARGS, variable='NDVI'), {'unit': '[unitless] / year'})
	ds = gdal.Open(path)
	units = {ds.GetRasterBand(i).GetDescription(): ds.GetRasterBand(i).GetUnitType() for i in range(1, 7)}
	assert units == {'slope': 'year-1', 'tau': '1', 'z': '1', 'p_value': '1', 'intercept': '1', 'n': '1'}
	assert readme.band_udunits('slope', 'degC') == 'degC year-1' and readme.band_udunits('value', '') == ''


def test_recipe_folder(tmp_path):
	rec = {'grid': {'crs': 'EPSG:32630', 'resolution': 250.0, 'width': 16, 'height': 14,
	                'extent': [463750.0, 4099750.0, 467750.0, 4103250.0]},
	       'study_area': '{"bbox": [-3.4, 37.05, -3.37, 37.07]}', 'catalog': {'file': 'catalog.json', 'monitoreo': '9.9'},
	       'files': {'1_LST_MODIS_median.tif': {
		       'spec': {'index': 'LST', 'sensor': 'Modis', 'metric': 'median', 'period': ['2023-06-01', '2023-07-31'],
		                'temporal': 'period'},
		       'source': {'variable': 'Land Surface Temperature', 'collection': 'MODIS/061/MOD11A1', 'unit': '[°C]',
		                  'udunits': 'degC', 'pixel_filters': {'clouds': True, 'water': False}},
		       'images': 61, 'downloaded': '2026-11-08T22:43:48'}},
	       'tasks': {}}
	(tmp_path / 'monitoreo.json').write_text(json.dumps(rec), encoding='utf-8')
	path = readme.document('download_variables', {}, {'folders': {'study': str(tmp_path)},
	                                                  'references': [{'text': 'Ref. https://doi.org/10.1/x'}]})
	text = open(path[0], encoding='utf-8').read()
	assert path == [str(tmp_path / 'README.txt')] and 'Made with MonitorEO 9.9' in text
	assert '1_LST_MODIS_median.tif: Land Surface Temperature (Modis); collection MODIS/061/MOD11A1; metric median; ' \
	       'period 2023-06-01 to 2023-07-31; unit [°C] (UDUNITS degC); pixels without clouds; 61 images' in \
	       ' '.join(text.split())
	assert '- Ref. https://doi.org/10.1/x' in text
	assert readme.document('download_variables', {}, {'files': []}) is None  # dry run: no folders


def test_mcp_answers_keep_readme(monkeypatch, tmp_path):
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	monkeypatch.setattr(services, 'eecu_warning', lambda *a, **k: None)
	res = {'title': 't', 'unit': '', 'scale': 250, 'csv': None, 'chart': None, 'rows': [], 'n_steps': 0,
	       'regions': [], 'profile': [], 'yearly': [], 'readme': '/x/y.README.txt', 'references': [], 'credits': []}
	for name in ('time_series', 'trend_table', 'compare_series'):
		monkeypatch.setattr(services, name, lambda *a, **k: res)
	args = ({'bbox': [0, 0, 1, 1]}, 'NDVI', 'Modis')
	dates = {'start': '2001-01-01', 'end': '2020-12-31'}  # by keyword, as MCP calls the tools
	for fn, more in ((mcp_server.time_series, {}), (mcp_server.trend_table, {}),
	                 (mcp_server.compare_series, {'other_start': '2021-01-01', 'other_end': '2022-12-31'})):
		out = fn(*args, **dates, **more)
		assert json.loads(out[0] if isinstance(out, list) else out)['readme'] == '/x/y.README.txt', fn.__name__
