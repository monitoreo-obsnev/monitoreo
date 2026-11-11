"""Tests that do not need Earth Engine."""

import csv
import datetime as dt
import json
import os
import re

import pytest

from monitoreo import catalog, charts, composite, drive, fire, sensors, services, timeseries, trends, variable
from monitoreo.grid import Grid


def test_catalog():
	entries = catalog.variables()
	assert len(entries) == 75  # the 32 of catalog.json, NBR and RBR of Landsat and Sentinel-2, SCF of Landsat, the
	# elevation and slope of the Copernicus DEM, the cloud frequency of MODIS (Terra and Aqua), Sentinel-2 and Landsat,
	# 4 variables of ERA5-Land, 8 of TerraClimate, the precipitation of CHIRPS and the 19 of WorldClim
	assert len({e['ref'] for e in entries}) == len(entries)  # the refs are unique
	nbr = catalog.find('NBR', 'Sentinel-2')
	assert nbr['ref'] == 102 and nbr['ft'] == 'N(B8,B12)' and nbr['col'] == 'COPERNICUS/S2_SR_HARMONIZED'
	assert catalog.find('nbr', 'landsat')['ft'] == 'N(nir,swir2)'
	assert catalog.find('ndvi', 'sentinel-2')['col'] == 'COPERNICUS/S2_SR_HARMONIZED'
	assert catalog.find('NDVI', 'Modis')['col'] == 'MODIS/061/MOD13Q1'  # first entry of the catalog
	assert catalog.find(None, ref=32)['scale'] == 0.1  # FIXES: scale of LAI
	with pytest.raises(KeyError):
		catalog.find('NDVI', 'Planet')


def test_app_has_the_catalog():
	"""The catalog of the Earth Engine app (gee/catalog.js, written by gee/build.py) is that of the package: run
	gee/build.py after changing catalog.json or catalog.py."""
	path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gee', 'catalog.js')
	with open(path, encoding='utf-8') as f:
		text = f.read()
	app = {e['ref']: e for e in json.loads(text[text.index('{'):text.rindex('}') + 1])['variables']}
	entries = catalog.variables()
	assert sorted(app) == sorted(e['ref'] for e in entries), 'run gee/build.py: the app has other variables'
	for e in entries:
		for k, v in app[e['ref']].items():
			if k not in ('fk', 'fb'):  # the formula with the band names of Earth Engine
				assert v == e.get(k), f"run gee/build.py: {k} of {e['ref']} {e['index']} differs in the app"
	# the script of the app (monitoreo_app.js) carries that catalog, in ASCII
	with open(path.replace('catalog.js', 'monitoreo_app.js'), encoding='ascii') as f:
		script = f.read()
	assert ''.join(c if ord(c) < 128 else f'\\u{ord(c):04x}' for c in text) in script, 'run gee/build.py'


def test_rbr_in_the_catalog():
	# RBR (Silva-Cardoza et al. 2022): the NBR of B8A and B12 in Sentinel-2, NIR and SWIR2 in Landsat; it compares two
	# periods, so only burn_severity computes it
	s2, landsat = catalog.find('RBR', 'Sentinel-2'), catalog.find('rbr', 'landsat')
	assert (s2['ref'], s2['ft'], s2['m'], s2['col']) == (103, 'N(B8A,B12)', 20, 'COPERNICUS/S2_SR_HARMONIZED')
	assert (landsat['ref'], landsat['ft'], landsat['m']) == (104, 'N(nir,swir2)', 30)
	assert s2['two_periods'] and s2['vname_en'] == 'Relativized Burn Ratio' and '1.001' in s2['notes']['f']
	assert catalog.find('NBR', 'Sentinel-2')['ref'] == 102 and not catalog.find('NBR', 'Sentinel-2').get('two_periods')
	assert catalog.RBR_OFFSET == 1.001
	with pytest.raises(ValueError, match="burn_severity and index 'RBR'"):
		services.make_spec('RBR', 'Sentinel-2', '2021-07-15', '2021-08-31')
	assert services.make_spec('RBR', 'Sentinel-2', '2021-07-15', '2021-08-31', two_periods=True)['index'] == 'RBR'
	rows = services.list_variables(text='RBR')
	assert [r['ref'] for r in rows] == [103, 104] and all(r['two_periods'] for r in rows)
	assert 'two_periods' not in services.list_variables(text='NDVI')[0]
	with pytest.raises(ValueError, match='dNBR or RBR'):
		services.burn_severity({'bbox': [0, 0, 1, 1]}, index='NDVI')


def test_scf_in_the_catalog():
	# SCF: snow cover frequency of Landsat, from the bands of its NDSI; each image is 100 (snow) or 0, and its only
	# metric is the mean (the % of the clear observations with snow)
	e = catalog.find('scf', 'landsat')
	assert (e['ref'], e['col'], e['m'], e['unit'], e['minp'], e['maxp']) == (105, 'LANDSAT', 30, '[%]', 0, 100)
	assert e['vname_en'] == 'Snow cover frequency' and e['metric'] == 'mean' and e['scale'] == 2.75e-05
	assert sensors.is_scf(e) and not sensors.is_scf(catalog.find('NDSI', 'Landsat'))
	assert sensors.parse_formula(e) == ('scf', ['green', 'nir', 'swir1'])
	assert catalog.find('NDSI', 'Landsat')['unit'] == '[unitless]'  # the entry it copies is unchanged
	with pytest.raises(KeyError):
		catalog.find('SCF', 'Sentinel-2')
	# fixed filters: always clouds and water, whatever the quality; never snow (what it measures) nor aerosols
	fixed = {'clouds': True, 'water': True, 'snow': False, 'aerosols': False}
	assert sensors.filters(e) == fixed and sensors.fixed_filters(e) == ['clouds', 'water']
	assert sensors.filters(e, {'clouds': False, 'water': 'auto', 'snow': True, 'aerosols': True}) == fixed
	assert sensors.conflicts(e) == [] and sensors.fixed_filters(catalog.find('NDSI', 'Landsat')) is None
	assert sensors.filters(catalog.find('NDSI', 'Landsat'), {'water': False})['water'] is False  # the others: free
	assert sensors.SCF['ndsi'] == 0.35 and sensors.SCF['toa_green'] == 0.08 and sensors.SCF['min_elevation'] == 1500
	assert set(sensors.SCF_TOA) == {c for c, _, _ in sensors.LANDSAT}
	# the mean, also in maps (whose default is the median); between years, any
	spec = services.make_spec('SCF', 'Landsat', '2020-10-01', '2021-05-31', metric='mean')
	assert spec['metric'] == 'mean' and spec['name'] == 'SCF_L_mean'
	for metric in ('median', 'max', ['mean', 'p95']):
		with pytest.raises(ValueError, match="only takes the metric 'mean'"):
			variable.specs({'index': 'SCF', 'sensor': 'Landsat', 'metric': metric, 'period': ['2020-10-01', '2021-05-31']})
	with pytest.raises(ValueError, match="only takes the metric 'mean'"):
		services.map_layer({'bbox': [-3.4, 37.0, -3.3, 37.1]}, 'SCF', 'Landsat', '2020-10-01', '2021-05-31')
	spec = services.make_spec('SCF', 'Landsat', '2000-01-01', '2020-12-31', temporal='annual', interannual='median',
	                          season=['10-01', '05-31'])
	assert spec['interannual'] == 'median'
	d = services.describe_variable('SCF', 'Landsat')
	assert d['metric'] == 'mean' and d['measures'] == ['snow'] and d['unit'] == '[%]' and 'hillShadow' in d['notes']['ft']
	assert d['fixed_filters'] == ['clouds', 'water'] and d['pixel_filters'] == fixed
	assert [r['ref'] for r in services.list_variables(text='snow cover')] == [105]
	assert services.list_variables(text='snow cover')[0]['fixed_filters'] == ['clouds', 'water']
	assert 'fixed_filters' not in services.describe_variable('NDSI', 'Landsat')
	# the title of the y axis of its charts; the other variables keep their unit
	assert e['axis'] == 'Snow Cover Frequency (SCF)'
	assert services._ylabel(spec) == 'Snow Cover Frequency (SCF) [%]'
	assert services._ylabel(services.make_spec('NDSI', 'Landsat', '2020-10-01', '2021-05-31')) == '[unitless]'


def test_unit_of_the_sums():
	"""The sum of a rate per month or per day (the annual precipitation) is a total in mm, in the results and in the
	metadata of the files; the other metrics keep the unit of the catalog."""
	from monitoreo import catalog, services, variable
	assert catalog.unit_of('[mm/month]', 'sum') == '[mm]'
	assert catalog.unit_of('[mm/day]', 'sum') == '[mm]'
	assert catalog.unit_of('[mm/month]', 'mean') == '[mm/month]'
	assert catalog.unit_of('[°C]', 'sum') == '[°C]'
	spec = services.make_spec('PRECIP', 'TerraClimate', '2020-01-01', '2020-12-31', metric='sum')
	assert services._unit(spec) == '[mm]'
	assert variable.describe(spec)['udunits'] == 'mm'
	spec = services.make_spec('PRECIP', 'TerraClimate', '2020-01-01', '2020-12-31')
	assert services._unit(spec) == '[mm/month]'


def test_cloud_frequency_and_climate_in_the_catalog():
	# cloud frequency (CF): % of the observations with clouds, of MODIS Terra and Aqua, Sentinel-2 and Landsat; its
	# only metric is the mean and it has no pixel filters (clouds are what it measures)
	cfs = [e for e in catalog.variables() if e['index'] == 'CF']
	assert [(e['ref'], e['sensor'], e['col']) for e in cfs] == [
		(108, 'Modis', 'MODIS/061/MOD09GA'), (109, 'Modis', 'MODIS/061/MYD09GA'),
		(110, 'Sentinel-2', 'COPERNICUS/S2_SR_HARMONIZED'), (111, 'Landsat', 'LANDSAT')]
	for e in cfs:
		assert sensors.is_cf(e) and sensors.fixed_filters(e) == [] and e['metric'] == 'mean' and e['unit'] == '[%]'
		assert not any(sensors.filters(e, {'clouds': True}).values()) and 'wilson2016' in e['references']
		assert sensors.parse_formula(e)[0] == 'cf'
	assert sensors.parse_formula(cfs[2]) == ('cf', ['cs_cdf']) and catalog.find('cf', 'modis')['ref'] == 108
	with pytest.raises(ValueError, match="only takes the metric 'mean'"):
		services.make_spec('CF', 'Modis', '2023-01-01', '2023-12-31', metric='median')
	# climate: ERA5-Land, TerraClimate and CHIRPS (series), WorldClim (fixed layers), without pixel filters
	precip = {e['sensor']: e for e in catalog.variables() if e['index'] == 'PRECIP'}
	assert set(precip) == {'ERA5-Land', 'TerraClimate', 'CHIRPS'}
	assert precip['ERA5-Land']['scale'] == 1000 and precip['ERA5-Land']['unit'] == '[mm/month]'
	assert precip['CHIRPS']['unit'] == '[mm/day]' and precip['CHIRPS']['col'] == 'UCSB-CHC/CHIRPS/V3/DAILY_SAT'
	assert catalog.find('TMEAN', 'ERA5-Land')['offset'] == -273.15 and catalog.find('TMAX', 'TerraClimate')['scale'] == 0.1
	assert not any(sensors.filters(precip['ERA5-Land']).values())
	bio = [e for e in catalog.variables() if e['sensor'] == 'WorldClim']
	assert [e['index'] for e in bio] == [f'BIO{i:02d}' for i in range(1, 20)] and all(e['static'] for e in bio)
	assert catalog.find('BIO01', 'WorldClim')['scale'] == 0.1 and catalog.find('BIO04', 'WorldClim')['scale'] == 0.01
	assert catalog.find('BIO12', 'WorldClim')['unit'] == '[mm]'
	spec = services.make_spec('BIO01', 'WorldClim')
	assert variable.is_static(spec) and variable._static_spec(spec)['scale'] == 0.1
	assert all(catalog.udunits(e['unit']) for e in catalog.variables())


def test_elevation_and_slope_in_the_catalog():
	# elevation and slope of the Copernicus DEM GLO-30: fixed layers, without dates (maps and their statistics only)
	for index, unit, terrain in (('ELEVATION', '[m]', None), ('SLOPE', '[°]', 'slope')):
		e = catalog.find(index, 'copernicus')
		assert (e['col'], e['band'], e['m'], e['unit'], e.get('terrain'), e['static']) == (
			'COPERNICUS/DEM/GLO30_2024_1', 'DEM', 30, unit, terrain, True)
		assert sensors.fixed_filters(e) == [] and not any(sensors.filters(e, {'clouds': True, 'water': True}).values())
		assert sensors.parse_formula(e) == ('static', ['DEM']) and e['type_en'] == 'Topography'
	assert [e['ref'] for e in catalog.variables() if e.get('static')] == [106, 107] + list(range(125, 144))
	# no metric, period nor season: one spec, named without them
	spec = services.make_spec('SLOPE', 'Copernicus')
	assert spec['metric'] is None and spec['name'] == 'SLOPE_Copernicus' and variable.is_static(spec)
	assert services.make_spec('SLOPE', 'Copernicus', '2020-01-01', '2020-12-31', metric='p95')['name'] == 'SLOPE_Copernicus'
	assert services._title(services.make_spec('ELEVATION', 'Copernicus', '2020-01-01', '2020-12-31')) == 'ELEVATION Copernicus'
	assert services._named(spec, 'median') == 'SLOPE Copernicus' and services._ylabel(spec) == '[°]'
	assert services._file_stem('SLOPE', 'Copernicus', 'median', None, None, {}) == 'SLOPE_Copernicus'
	ndvi = services.make_spec('NDVI', 'Sentinel-2', '2020-01-01', '2020-12-31')
	assert not variable.is_static(ndvi) and services._named(ndvi, 'median').endswith('(median)')
	# no time series, trends or comparisons, with an error before any call to Earth Engine
	region = {'bbox': [-3.4, 37.0, -3.3, 37.1]}
	with pytest.raises(ValueError, match='ELEVATION .Copernicus. is a fixed layer, without dates'):
		services.time_series(region, 'ELEVATION', 'Copernicus', '2020-01-01', '2020-12-31')
	with pytest.raises(ValueError, match='fixed layer, without dates.* no comparisons'):
		services.compare_series(region, 'SLOPE', 'Copernicus', '2020-01-01', '2020-12-31', '2021-01-01', '2021-12-31')
	with pytest.raises(ValueError, match='fixed layer, without dates'):
		variable.collection(spec, None, 30)
	d = services.describe_variable('SLOPE', 'Copernicus')
	assert d['static'] and d['fixed_filters'] == [] and d['group'] == 'Topography' and 'degrees' in d['notes']['ft']
	assert [(r['variable'], r['static']) for r in services.list_variables(sensor='Copernicus')] == [
		('ELEVATION', True), ('SLOPE', True)]
	assert 'static' not in services.describe_variable('NDVI', 'Sentinel-2')


def test_rbr_report():
	from monitoreo import publish, report
	args = {'sensor': 'Sentinel-2', 'start': '2021-07-15', 'end': '2021-08-31', 'other_start': '2021-09-20',
	        'other_end': '2021-10-31', 'index': 'RBR'}
	assert publish.fire_variable(args) == 'RBR' and publish.fire_variable(dict(args, index='dNBR')) == 'NBR'
	assert publish.default_title('burn_severity', args).startswith('Burn severity (RBR of Sentinel-2): before, 15 Jul')
	res = {'index': 'RBR', 'stats': [{'region': 'a', 'mean': 0.31, 'median': 0.29, 'p10': 0.02, 'p90': 0.6,
	                                  'min': -0.2, 'max': 0.9, 'ha': 812.4}]}
	cols, rows = report.item_table('burn_severity', res, args)
	assert cols[0] == 'RBR mean' and cols[-1] == 'Hectares' and rows == [['0.31', '0.29', '0.02', '0.6', '-0.2', '0.9',
	                                                                     '812.4']]
	facts = dict(report.item_facts('burn_severity', args, res))
	assert facts['Variable'].startswith('Relativized Burn Ratio') and '1.001' in facts['Method']
	assert 'USGS' in dict(report.item_facts('burn_severity', dict(args, index='dNBR'), {}))['Method']
	assert publish.BANDS['rbr'][0].startswith('RBR') and 'rbr' in publish.MAIN_BANDS


def test_list_and_describe():
	s2 = services.list_variables(sensor='Sentinel-2')
	assert s2 and all(v['sensor'] == 'Sentinel-2' for v in s2)
	assert services.list_variables(text='vegetación')
	d = services.describe_variable('NDSI', 'Modis')
	assert d['measures'] == ['snow'] and d['alternatives'] == ['MODIS/061/MYD10A1']


def test_windows_and_bins():
	w = composite.windows(['2018-01-01', '2019-12-31'])
	assert [x[0] for x in w] == [2018, 2019]
	w = composite.windows(['2018-03-15', '2020-06-30'], ['11-01', '02-29'])
	assert [(x[1].isoformat(), x[2].isoformat()) for x in w] == [('2018-11-01', '2019-03-01'), ('2019-11-01', '2020-03-01')]
	months = composite.bins((2020, dt.date(2020, 6, 1), dt.date(2020, 10, 1)), 'monthly')
	assert [m[0] for m in months] == [6, 7, 8, 9]
	spec = variable.specs({'index': 'NDVI', 'sensor': 'Sentinel-2', 'metric': 'mean', 'period': ['2020-01-01', '2020-12-31']})[0]
	assert len(timeseries.bins(spec, 'monthly')) == 12
	assert timeseries.bins(spec, 'annual') == [('2020-01-01', '2021-01-01')]
	assert len(timeseries.bins(spec, '16-day')) == 23


def test_metrics():
	for m in ('mean', 'median', 'p95', 'P2.5', 'std', 'count'):
		composite.check_metric(m)
	with pytest.raises(ValueError):
		composite.check_metric('foo')


def test_specs():
	s = variable.specs({'index': 'NDVI', 'sensor': 'Sentinel-2', 'metric': ['p95', 'p5'], 'period': ['2018-01-01', '2021-12-31']})
	assert [x['name'] for x in s] == ['NDVI_S2_p95', 'NDVI_S2_p5']
	assert s[0]['quality']['cloud_score'] == 0.6  # all quality options recorded
	with pytest.raises(ValueError):
		variable.specs({'index': 'NDVI', 'sensor': 'Sentinel-2', 'metric': 'mean', 'period': ['2018-01-01', '2021-12-31'],
		                'quality': {'clods': True}})
	spec = services.make_spec('LST', 'Modis', '2020-01-01', '2020-12-31', metric='max', temporal='annual')
	assert spec['temporal'] == 'annual' and variable.kind(spec) == 'catalog'
	spec = services.make_spec(image='COPERNICUS/DEM/GLO30_2024_1', band='DEM', terrain='slope')
	assert variable.kind(spec) == 'image'


def test_pixel_filters():
	ndsi = catalog.find('NDSI', 'Modis')
	assert sensors.filters(ndsi) == {'clouds': True, 'water': True, 'snow': False, 'aerosols': False}  # no QA band
	assert sensors.conflicts(catalog.find('NDSI', 'Sentinel-2')) == ['snow']
	assert sensors.filters(catalog.find('NDSI', 'Sentinel-2'), {'snow': 'auto'})['snow'] is False
	assert sensors.filters(catalog.find('NDVI', 'Landsat'))['aerosols'] is True
	assert sensors.filters(catalog.find('NDVI', 'Sentinel-2'))['aerosols'] is False


def test_grid():
	g = Grid.around('EPSG:32630', 10, 441310, 4078290, 455070, 4085990, margin=520)
	assert (g.width, g.height) == (1480, 874)
	assert g.extent == (440790.0, 4077770.0, 455590.0, 4086510.0)
	assert len(g.tiles(512)) == 6


def test_csv_climatology_chart(tmp_path):
	rows = [{'region': 'a', 'date': f'{y}-{m:02d}-01', 'value': m / 10, 'n_pixels': 5, 'n_images': 2}
	        for y in (2020, 2021) for m in range(1, 13)]
	rows[3]['value'] = None
	path = timeseries.write_csv(rows, tmp_path / 'ts.csv', {'variable': 'NDVI'})
	with open(path) as f:
		read = list(csv.DictReader(f))
	assert len(read) == 24 and read[3]['value'] == '' and read[0]['variable'] == 'NDVI'
	clim = timeseries.climatology(rows)
	assert len(clim) == 12 and clim[3]['n_years'] == 1
	png = charts.time_series_png(rows, tmp_path / 'ts.png', title='t', ylabel='u')
	assert png[:8] == b'\x89PNG\r\n\x1a\n' and (tmp_path / 'ts.png').exists()


def test_drive_folders(tmp_path):
	base = tmp_path / 'eHabitat_GEE'
	for d in (base, tmp_path / 'eHabitat_GEE (1)', tmp_path / 'eHabitat_GEE (2)', tmp_path / 'eHabitat_GEE old'):
		d.mkdir()
	(tmp_path / 'eHabitat_GEE (1)' / 'x_1.tif').write_bytes(b'')
	(tmp_path / 'eHabitat_GEE (2)' / 'x_1-0000000000-0000016384.tif').write_bytes(b'')
	(tmp_path / 'eHabitat_GEE old' / 'x_1.tif').write_bytes(b'')
	(base / 'x_10.tif').write_bytes(b'')
	assert len(drive.folders(str(base))) == 3
	found = [p.split('/')[-2:] for p in drive.find(str(base), 'x_1')]
	assert found == [['eHabitat_GEE (1)', 'x_1.tif'], ['eHabitat_GEE (2)', 'x_1-0000000000-0000016384.tif']]


def test_recipe(tmp_path):
	from monitoreo import recipe
	path = tmp_path / 'recipe.yaml'
	path.write_text("study: {resolution: 10}\nperiod: ['2018-01-01', '2021-12-31']\nvariables:\n"
	                "  - {index: NDVI, sensor: Sentinel-2, metric: [p95, p5]}\n"
	                "  - {name: slope, image: COPERNICUS/DEM/GLO30_2024_1, band: DEM, terrain: slope}\n")
	r = recipe.read(str(path))
	specs = recipe.expand(r)
	assert [s['file'] for s in specs] == ['1_NDVI_S2_p95.tif', '2_NDVI_S2_p5.tif', '3_slope.tif']
	assert specs[0]['period'] == ['2018-01-01', '2021-12-31'] and specs[0]['quality']['clouds'] is True
	with pytest.raises(ValueError, match='unknown keys'):
		recipe.read(dict(r, folder='gee'))
	assert recipe.read(dict(r, folder='gee'), extra={'folder'})
	with pytest.raises(ValueError, match='two variables'):
		recipe.expand(dict(r, variables=[{'name': 'a', 'image': 'X', 'band': 'b'}] * 2))
	with pytest.raises(ValueError, match='variable 1'):
		recipe.expand(dict(r, variables=[{'index': 'NDVI', 'sensor': 'Sentinel-2'}], period=None))
	warnings = []
	recipe.expand(dict(r, variables=[{'index': 'NDSI', 'sensor': 'Sentinel-2', 'metric': 'mean'}]), warn=warnings.append)
	assert len(warnings) == 1 and 'snow' in warnings[0]
	many = recipe.expand(dict(r, variables=[{'name': f'v{i}', 'image': 'X', 'band': 'b'} for i in range(10)]))
	assert many[0]['file'] == '01_v0.tif' and many[-1]['file'] == '10_v9.tif'


def test_update(monkeypatch):
	from monitoreo import update
	calls, quiet = [], (lambda msg: None)
	new, old = 'b' * 40, 'a' * 40
	monkeypatch.setattr(update, '_pip', lambda *args: calls.append(args))
	assert update.local_copy()  # these tests run the clone (src)
	monkeypatch.setattr(update, 'local_copy', lambda: None)
	monkeypatch.setattr(update, 'latest', lambda: new)
	monkeypatch.setattr(update, 'installed', lambda: ('0.2.0', old, None))
	told = []  # installing() is called before pip
	assert update.ensure_latest('mcp,plot', log=quiet, installing=lambda: told.append(len(calls))) == 'updated'
	url = f'https://github.com/monitoreo-obsnev/monitoreo/archive/{new}.zip'
	assert calls == [('--force-reinstall', '--no-deps', f'monitoreo @ {url}'), (f'monitoreo[mcp,plot] @ {url}',)]
	assert told == [0]
	monkeypatch.setattr(update, 'installed', lambda: ('0.2.0', new, None))
	assert update.ensure_latest(log=quiet, installing=lambda: told.append(len(calls))) == 'current' and told == [0]
	monkeypatch.setattr(update, 'local_copy', lambda: '/clone/src/monitoreo')
	assert update.ensure_latest(log=quiet) == 'local' and len(calls) == 2

	def offline():
		raise OSError('no network')
	monkeypatch.setattr(update, 'latest', offline)
	assert update.ensure_latest(log=quiet) == 'offline'


def test_series_split_and_retry(monkeypatch):
	import ee
	calls = []

	def table(spec, regions, step, metric, stat, scale, steps, crs):
		calls.append(list(steps))

		class FC:
			def getInfo(self):
				if len(steps) > 2:
					raise ee.EEException('Too many concurrent aggregations.')
				return {'features': [{'properties': {'date': s}} for s in steps]}
		return FC()
	monkeypatch.setattr(timeseries, 'table', table)
	monkeypatch.setattr(timeseries.time, 'sleep', lambda s: None)
	rows = timeseries._fetch(None, None, 'monthly', 'mean', 'mean', 250, list('abcdefg'), 'EPSG:32630')
	assert [r['date'] for r in rows] == list('abcdefg') and calls[0] == list('abcdefg')

	def broken(*args):
		class FC:
			def getInfo(self):
				raise ee.EEException('Image.load: asset not found')
		return FC()
	monkeypatch.setattr(timeseries, 'table', broken)
	with pytest.raises(ee.EEException, match='not found'):  # not retried
		timeseries._fetch(None, None, 'monthly', 'mean', 'mean', 250, list('ab'), 'EPSG:32630')


def test_steps_without_value(monkeypatch):
	# Earth Engine leaves out the null properties: a year without images (Landsat in 2012) or without valid pixels
	# has no value, and the trend table of the QGIS plugin 0.2.3 failed with KeyError: 'value'
	def table(*args):
		class FC:
			def getInfo(self):
				return {'features': [{'properties': {'date': '2011-01-01', 'value': 0.4, 'n_pixels': 30, 'n_images': 10}},
				                     {'properties': {'date': '2012-01-01', 'n_images': 0}},
				                     {'properties': {'date': '2013-01-01', 'n_images': 14}},
				                     {'properties': {'date': '2014-01-01', 'value': 0.5, 'n_pixels': 32, 'n_images': 21}}]}
		return FC()
	monkeypatch.setattr(timeseries, 'table', table)
	rows = timeseries._fetch(None, None, 'annual', 'mean', 'mean', 30, ['2011'], 'EPSG:32630')
	assert [r['value'] for r in rows] == [0.4, None, None, 0.5] and rows[1]['n_pixels'] == 0
	for r in rows:
		r.update(region='zona', part=0, year=int(r['date'][:4]))
	t = trends.trend_rows(rows, 'annual')[0]
	assert t['n'] == 2 and t['slope'] == pytest.approx(0.1 / 3) and (t['first_year'], t['last_year']) == (2011, 2014)
	assert t['label'] == 'year' and trends.part_label('monthly', 7) == 'July'
	assert trends.part_label('16-day', 12) == 'days 177-192' and trends.part_label('16-day', 23) == 'days 353-366'


def test_about():
	from monitoreo import about
	for lang in ('en', 'es'):
		a = services.about(lang)
		assert a['description'].startswith('MonitorEO-OBSNEV') and 'PID2023-151939OB-I00' in a['acknowledgements']
		assert 'C-EXP-074-UGR23' in a['acknowledgements'] and 'PCI 2025-163175' in a['acknowledgements']
		assert len(a['logos']) == 3 and a['doi'] == about.DOI and f'https://doi.org/{about.DOI}' in a['citation']
	assert all(open(p, 'rb').read(4) in (b'\x89PNG', b'\xff\xd8\xff\xe0', b'\xff\xd8\xff\xe1') for p in about.LOGOS)
	assert 'NevadEO' in about.text('en') and 'PRESINMED' in about.text('es') and about.MANUAL in about.text('es')
	assert f'Cómo citar: {about.CITATION}' in about.text('es') and f'How to cite: {about.CITATION}' in about.text('en')


def test_burn_severity_classes():
	assert [c for c, _, _ in fire.SEVERITY] == [-2, -1, 0, 1, 2, 3, 4]
	assert fire.limits(1) == (0.1, 0.27) and fire.limits(-2) == (None, -0.25) and fire.limits(4) == (0.66, None)
	rows = fire.table([{'class': 1, 'sum': 12.5}, {'class': 3, 'sum': 2.0}], 'Teide')
	assert len(rows) == 7 and {r['class']: r['ha'] for r in rows}[1] == 12.5 and rows[0]['ha'] == 0.0
	# the colours of UN-SPIDER, the same in the app of Earth Engine (gee/core.js), and the names in English
	assert fire.COLOURS == {-2: '7a8737', -1: 'acbe4d', 0: '0ae042', 1: 'fff70b', 2: 'ffaf38', 3: 'ff641b', 4: 'a41fd6'}
	core = open(os.path.join(os.path.dirname(__file__), '..', 'gee', 'core.js'), encoding='utf-8').read()
	js = re.search(r"var SEVERITY_COLOURS = \[([^\]]+)\]", core).group(1)
	assert re.findall(r"'(\w+)'", js) == [fire.COLOURS[c] for c, _, _ in fire.SEVERITY]
	assert [n for _, _, n in fire.SEVERITY][0] == 'Enhanced regrowth, high' and fire.SEVERITY[-1][2] == 'High severity'


def test_shared_account(monkeypatch, tmp_path):
	# without a project, init connects with the shared account of MonitorEO: tokens of its broker, renewed when they
	# expire; it cannot export to Google Drive
	import time
	import types

	import requests
	for v in ('EE_PROJECT', 'GOOGLE_CLOUD_PROJECT', 'MONITOREO_BROKER'):
		monkeypatch.delenv(v, raising=False)
	monkeypatch.setattr(services, '_project', None)
	monkeypatch.setattr(services, '_shared', False)
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)  # see test_eecu
	monkeypatch.setattr(services, 'USER_FILE', str(tmp_path / 'user_id'))
	monkeypatch.setattr(services, '_user', None)
	asked = []

	def get(url, timeout, headers):
		asked.append(url)
		return types.SimpleNamespace(status_code=200, headers={'Content-Type': 'application/json'},
		                             json=lambda: {'access_token': f'token{len(asked)}', 'project': 'shared-project',
		                                           'expires_at': time.time() + 3600})
	monkeypatch.setattr(requests, 'get', get)
	got = {}
	monkeypatch.setattr(services.ee, 'Initialize', lambda credentials=None, project=None: got.update(c=credentials,
	                                                                                                  p=project))
	assert services.init() == 'shared-project' and services.shared() and got['p'] == 'shared-project'
	user = services.user_id()
	assert asked == [services.BROKER + '/token?user=' + user] and got['c'].token == 'token1' and got['c'].valid
	assert services.ee.data.getWorkloadTag() == user  # what this user computes is tagged with their ID
	got['c'].refresh(None)
	assert got['c'].token == 'token2' and got['c'].valid
	assert services.init() == 'shared-project' and len(asked) == 2  # already connected
	with pytest.raises(RuntimeError, match='own Earth Engine account'):
		services.time_series_to_drive({'bbox': [0, 0, 1, 1]}, 'NDVI', 'Sentinel-2', '2020-01-01', '2020-02-01')
	with pytest.raises(RuntimeError, match='own Earth Engine account'):
		drive.export(None, None, 'name', 'MonitorEO', 'shared-project')

	monkeypatch.setattr(services.ee, 'Initialize', lambda project=None: got.update(c=None, p=project))
	assert services.init('mine') == 'mine' and not services.shared() and got['p'] == 'mine'
	assert services.ee.data.getWorkloadTag() == ''  # not with the user's own account
	services.need_own_account()  # nothing to stop with the user's own account

	monkeypatch.setattr(services, '_project', None)
	monkeypatch.setattr(requests, 'get', lambda url, timeout, headers: types.SimpleNamespace(
		status_code=429, headers={'Content-Type': 'application/json'}, json=lambda: {'error': 'too many requests'}))
	with pytest.raises(RuntimeError, match='shared account of MonitorEO: too many requests'):
		services.init()


class Response:
	def __init__(self, status, body):
		self.status_code, self.body = status, body
		self.headers = {'Content-Type': 'application/json'}

	def json(self):
		return self.body


def test_eecu_month_and_limit():
	# the quotas of Earth Engine restart on the first day of each month at midnight Pacific Time (PDT or PST)
	utc = dt.timezone.utc
	assert services.eecu_month(dt.datetime(2026, 11, 1, 7, 30, tzinfo=utc)) == \
		(dt.datetime(2026, 11, 1, 7, tzinfo=utc), dt.date(2026, 12, 1))
	assert services.eecu_month(dt.datetime(2026, 11, 1, 6, 59, tzinfo=utc))[0] == dt.datetime(2026, 10, 1, 7, tzinfo=utc)
	assert services.eecu_month(dt.datetime(2026, 12, 31, 23, tzinfo=utc)) == \
		(dt.datetime(2026, 12, 1, 8, tzinfo=utc), dt.date(2027, 1, 1))
	assert services.eecu_limit() == 150 and services.eecu_limit('contributor') == 1000
	assert services.eecu_limit('Partner') == 100000 and services.eecu_limit(250) == 250
	# the project of MonitorEO is Contributor, whatever the setting says (its default, Community, too)
	assert services.eecu_limit(None, 'ee-ugr-default-project') == 1000
	assert services.eecu_limit('Community', 'ee-ugr-default-project') == 1000
	assert services.eecu_limit(None, 'my-project') == 150
	with pytest.raises(ValueError, match='tier'):
		services.eecu_limit('Gold')


def test_eecu_hours_of_cloud_monitoring():
	# the EECU-seconds completed (metric of Cloud Monitoring), day by day and page by page, in hours
	asked = []

	class Session:
		def get(self, url, params, timeout):
			asked.append(dict(params))
			if 'pageToken' not in params:
				return Response(200, {'timeSeries': [{'points': [{'value': {'doubleValue': 3600}},
				                                                 {'value': {'int64Value': '1800'}}]}],
				                      'nextPageToken': 'next'})
			return Response(200, {'timeSeries': [{'points': [{'value': {'doubleValue': 1800}}]}]})

	start = dt.datetime(2026, 11, 1, 7, tzinfo=dt.timezone.utc)
	assert services.eecu_hours(Session(), 'p', start, start + dt.timedelta(days=4)) == 2
	assert asked[0]['filter'] == 'metric.type = "earthengine.googleapis.com/project/cpu/usage_time"'
	assert asked[0]['interval.startTime'] == '2026-11-01T07:00:00Z' and asked[1]['pageToken'] == 'next'

	class Disabled:
		def get(self, url, params, timeout):
			return Response(403, {'error': {'message': 'Cloud Monitoring API has not been used', 'details': [
				{'@type': 'type.googleapis.com/google.rpc.ErrorInfo', 'reason': 'SERVICE_DISABLED'}]}})

	with pytest.raises(services._MonitoringError) as e:
		services.eecu_hours(Disabled(), 'p', start)
	assert e.value.reason == 'disabled'


def test_user_id(monkeypatch, tmp_path):
	# the anonymous ID of an installation: made at random once, kept in a file, valid as a workload tag of Earth Engine
	monkeypatch.setattr(services, 'USER_FILE', str(tmp_path / 'monitoreo' / 'user_id'))
	monkeypatch.setattr(services, '_user', None)
	user = services.user_id()
	assert re.fullmatch(r'mo-[0-9a-f]{16}', user) and services.ee.data._get_state().workload_tag.validate(user) == user
	monkeypatch.setattr(services, '_user', None)
	assert services.user_id() == user and (tmp_path / 'monitoreo' / 'user_id').read_text().strip() == user


def test_eecu(monkeypatch, tmp_path):
	# with the shared account, the research EECUs of this user (from the broker, without connecting to Earth Engine);
	# with the user's own, those of their project (Cloud Monitoring); a warning when less than 10 % are left
	import warnings
	for v in ('EE_PROJECT', 'GOOGLE_CLOUD_PROJECT'):
		monkeypatch.delenv(v, raising=False)
	monkeypatch.setattr(services, 'USER_FILE', str(tmp_path / 'user_id'))
	monkeypatch.setattr(services, '_user', None)
	monkeypatch.setattr(services, '_eecu', {})
	monkeypatch.setattr(services, '_eecu_warned', set())
	monkeypatch.setattr(services, '_project', None)
	monkeypatch.setattr(services, '_shared', False)
	monkeypatch.setattr(services, 'init', lambda *a, **kw: pytest.fail('it does not connect'))
	used = {'hours': 2.0}
	asked = []

	def broker(path, **params):
		asked.append((path, params))
		return {'project': 'shared-project', 'user': params['user'], 'used_hours': used['hours'], 'limit_hours': 10}
	monkeypatch.setattr(services, '_broker', broker)
	u = services.eecu_usage(lang='es')
	assert asked == [('/usage', {'user': services.user_id()})] and u['account'] == 'shared'
	assert u['name'] == 'research EECUs' and u['project'] == 'shared-project' and u['tier'] is None
	assert u['used_percent'] == 20 and u['left_percent'] == 80 and not u['low'] and u['warning'] is None
	assert u['bar'] == '[######------------------------] 20%'
	assert u['text'].startswith('research EECUs: 20,0 % gastado (2,00 de tus 10 EECU-h de este mes con la cuenta')
	assert services.eecu_warning() is None  # not connected

	monkeypatch.setattr(services, '_project', 'shared-project')
	monkeypatch.setattr(services, '_shared', True)
	used['hours'] = 9.3
	assert services.eecu_usage()['used_percent'] == 20 and len(asked) == 1  # kept EECU_TTL seconds
	u = services.eecu_usage(refresh=True)
	assert len(asked) == 2 and u['low'] and u['left_percent'] == 7
	assert u['warning'].startswith('Less than 10% of your research EECUs') and 'own Earth Engine account' in u['warning']
	with warnings.catch_warnings(record=True) as caught:
		warnings.simplefilter('always')
		assert services.eecu_warning(lang='es', once=True, python_warning=True).startswith(
			'Te quedan menos del 10 % de tus research EECUs')
		assert services.eecu_warning(once=True) is None  # once a month and project
		assert services.eecu_warning() is not None
	assert [w.category for w in caught] == [services.EECUWarning]
	used['hours'] = 10.2
	assert services.eecu_usage(refresh=True, lang='es')['warning'].startswith(
		'Has gastado tus research EECUs de este mes (10,2 de 10 EECU-h): la cuenta compartida de MonitorEO no calcula')

	# the broker says what is left: at most what the project has left for all the users of the shared account
	monkeypatch.setattr(services, '_broker', lambda path, **params: {
		'project': 'shared-project', 'used_hours': 2.0, 'limit_hours': 25, 'left_hours': 1.5, 'project_left_hours': 1.5})
	u = services.eecu_usage(refresh=True)
	assert u['used_percent'] == 8 and u['left_percent'] == 6 and u['left_hours'] == 1.5 and u['low']
	assert u['bar'] == '[############################--] 8%'
	assert 'only 2 EECU-hours left for all its users' in u['text'] and 'you have 1.50 left' in u['text']
	monkeypatch.setattr(services, '_broker', lambda path, **params: {
		'project': 'shared-project', 'used_hours': 2.0, 'limit_hours': 25, 'left_hours': 0, 'project_left_hours': 0})
	u = services.eecu_usage(refresh=True, lang='es')
	assert u['warning'].startswith('La cuenta compartida de MonitorEO ha gastado los EECU de este mes para sus usuarios')

	def fails(path, **params):
		raise RuntimeError('503')
	monkeypatch.setattr(services, '_broker', fails)
	with pytest.raises(RuntimeError, match='your research EECUs of the shared account'):
		services.eecu_usage(refresh=True)
	monkeypatch.setattr(services, '_eecu', {})
	assert services.eecu_warning() is None  # never fails

	# the user's own project, against the quota of its tier
	monkeypatch.setattr(services, '_project', 'mine')
	monkeypatch.setattr(services, '_shared', False)
	monkeypatch.setattr(services, '_own_eecu_hours', lambda project, start: 950.0)
	u = services.eecu_usage('Contributor', lang='en')
	assert u['account'] == 'own' and u['tier'] == 'Contributor' and u['used_percent'] == 95 and u['low']
	assert 'monthly EECU quota of the project mine' in u['warning'] and 'research' not in u['warning']
	assert services.eecu_usage(lang='en')['used_percent'] == 633.3  # Community: 150 EECU-hours

	def disabled(project, start):
		raise services._MonitoringError(Response(403, {'error': {'message': 'no', 'details': [
			{'reason': 'SERVICE_DISABLED'}]}}))
	monkeypatch.setattr(services, '_own_eecu_hours', disabled)
	with pytest.raises(RuntimeError, match='monitoring.googleapis.com\\?project=mine'):
		services.eecu_usage(refresh=True)


def test_broker_limits_each_user(monkeypatch, tmp_path):
	# the broker (on this computer, with Cloud Monitoring faked) gives tokens only to users who have not spent their
	# research EECUs of the month, and tells each one what they have spent; the package asks for them with its ID
	import importlib.util
	import os
	import threading
	from http.server import ThreadingHTTPServer
	monkeypatch.setenv('PUBLIC_SA', 'public@p.iam.gserviceaccount.com')
	monkeypatch.setenv('EE_PROJECT', 'shared-project')
	path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'broker', 'main.py')

	def load():
		spec = importlib.util.spec_from_file_location('broker_main', path)
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		return module
	broker = load()  # the Contributor tier: 25 EECU-hours a month for each user, 100 of the 1,000 kept for the app
	assert (broker.USER_LIMIT, broker.EECU_LIMIT, broker.PROJECT_RESERVE, broker.REQUIRE_USER) == (25, 1000, 100, True)
	monkeypatch.setenv('USER_LIMIT', '10')
	monkeypatch.setenv('EECU_LIMIT', '30')  # a reserve of 3: 12.5 EECU-hours left for the users of the shared account
	broker = load()
	assert broker.USER_LIMIT == 10 and broker.PROJECT_RESERVE == 3
	alice, bob = 'mo-' + 'a' * 16, 'mo-' + 'b' * 16
	monitoring = []

	def fake_json(url, data=None, headers=None):
		if url == broker.METADATA:
			return {'access_token': 'broker-token'}
		monitoring.append(url)
		seconds = {alice: 3 * 3600, bob: 10.5 * 3600}
		return {'timeSeries': [{'metric': {'labels': {'workload_tag': k}}, 'points': [{'value': {'doubleValue': v}}]}
		                       for k, v in seconds.items()] + [{'metric': {}, 'points': [{'value': {'int64Value': '3600'}}]}]}
	monkeypatch.setattr(broker, '_json', fake_json)
	monkeypatch.setattr(broker, 'token', lambda: {'access_token': 'shared-token', 'expires_at': 2e9,
	                                              'project': 'shared-project'})
	server = ThreadingHTTPServer(('127.0.0.1', 0), broker.Handler)
	threading.Thread(target=server.serve_forever, daemon=True).start()
	monkeypatch.setenv('MONITOREO_BROKER', f'http://127.0.0.1:{server.server_port}')
	try:
		with pytest.raises(services.BrokerError) as e:
			services._broker('/token')  # a version without the ID of its user
		assert e.value.code == 'user'
		assert services._broker('/token', user=alice)['access_token'] == 'shared-token'
		with pytest.raises(services.BrokerError) as e:
			services._broker('/token', user=bob)
		assert e.value.code == 'spent' and 'spent your research EECUs' in str(e.value)
		u = services._broker('/usage', user=alice)
		assert u['used_hours'] == 3 and u['limit_hours'] == 10 and u['project_used_hours'] == 14.5
		assert u['left_hours'] == 7 and u['project_left_hours'] == 12.5 and u['project_reserve_hours'] == 3
		monkeypatch.setattr(broker, 'EECU_LIMIT', 20.0)  # 2.5 left for all the users: what alice has left
		u = services._broker('/usage', user=alice)
		assert u['left_hours'] == 2.5 and u['project_left_hours'] == 2.5
		monkeypatch.setattr(broker, 'EECU_LIMIT', 17.0)  # nothing left for them but the reserve of the app
		with pytest.raises(services.BrokerError) as e:
			services._broker('/token', user=alice)
		assert e.value.code == 'project' and 'kept for the app of Earth Engine' in str(e.value)
		assert services._broker('/usage', user=alice)['left_hours'] == 0
		monkeypatch.setattr(broker, 'EECU_LIMIT', 30.0)
		assert len(monitoring) == 1 and 'workload_tag' in monitoring[0]  # one query for every user, kept 5 minutes

		# the package: the research EECUs of the user of this installation, and no connection once they are spent
		for v in ('GOOGLE_CLOUD_PROJECT',):
			monkeypatch.delenv(v, raising=False)
		monkeypatch.delenv('EE_PROJECT')
		monkeypatch.setattr(services, '_eecu', {})
		monkeypatch.setattr(services, '_project', None)
		monkeypatch.setattr(services, '_shared', False)
		monkeypatch.setattr(services, '_user', bob)
		u = services.eecu_usage(lang='es')
		assert u['used_percent'] == 105 and u['left_percent'] == 0 and u['warning'].startswith('Has gastado')
		with pytest.raises(RuntimeError, match='spent your research EECUs.*Meanwhile, use your own account'):
			services.init()
		assert services.project() is None
	finally:
		server.shutdown()


def test_broker_chat(monkeypatch):
	# /chat of the broker (on this computer, with Gemini faked): the model, the effort and the length of answer of the
	# broker whatever the request asks, its scope before the instructions, the key only towards Gemini, and the limits
	# of each address and of each user
	import importlib.util
	import io
	import threading
	import urllib.error
	import urllib.request
	from http.server import ThreadingHTTPServer
	monkeypatch.setenv('PUBLIC_SA', 'public@p.iam.gserviceaccount.com')
	monkeypatch.setenv('EE_PROJECT', 'shared-project')
	monkeypatch.setenv('CHAT_LIMIT', '3')
	monkeypatch.setenv('CHAT_USER_DAY', '2')
	monkeypatch.setenv('CHAT_MODELS', 'gemini-3.8-flash')
	monkeypatch.delenv('CHAT_CHOOSE', raising=False)
	monkeypatch.delenv('GEMINI_API_KEY', raising=False)
	path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'broker', 'main.py')
	spec = importlib.util.spec_from_file_location('broker_main', path)
	broker = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(broker)
	assert (broker.CHAT_MODELS, broker.CHAT_REASONING, broker.CHAT_LIMIT, broker.CHAT_USER_DAY) == (
		['gemini-3.8-flash'], 'low', 3, 2)
	sent = []

	class Answer(io.BytesIO):
		def __enter__(self):
			return self

		def __exit__(self, *a):
			return False

	def gemini(req, timeout=None):
		sent.append((req.full_url, dict(req.header_items()), json.loads(req.data)))
		return Answer(json.dumps({'choices': [{'message': {'role': 'assistant', 'content': 'Hola'}}],
		                          'usage': {'prompt_tokens': 10, 'completion_tokens': 2}}).encode())
	monkeypatch.setattr(urllib.request, 'urlopen', gemini)
	server = ThreadingHTTPServer(('127.0.0.1', 0), broker.Handler)
	threading.Thread(target=server.serve_forever, daemon=True).start()
	monkeypatch.setenv('MONITOREO_BROKER', f'http://127.0.0.1:{server.server_port}')
	alice, bob = 'mo-' + 'a' * 16, 'mo-' + 'b' * 16
	body = {'model': 'gemini-4-argon', 'max_tokens': 10 ** 6, 'stream': True, 'n': 4, 'temperature': 0.2,
	        'messages': [{'role': 'system', 'content': 'You are the assistant of MonitorEO.'},
	                     {'role': 'user', 'content': 'NDVI'}],
	        'tools': [{'type': 'function', 'function': {'name': 'time_series'}}]}
	try:
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body, user=alice)
		assert e.value.code == 'off'  # without the key of Gemini
		monkeypatch.setattr(broker, 'GEMINI_API_KEY', 'the-key')
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body)
		assert e.value.code == 'user'  # a version without the ID of its user
		answer = services._broker('/chat', body=body, user=alice)
		assert answer['choices'][0]['message']['content'] == 'Hola' and 'the-key' not in json.dumps(answer)
		url, headers, request = sent[0]
		assert url == broker.GEMINI and headers['Authorization'] == 'Bearer the-key'
		assert request['model'] == 'gemini-3.8-flash' and request['max_tokens'] == 8192 and request['stream'] is False
		assert request['reasoning_effort'] == 'low' and 'n' not in request and request['tools'] == body['tools']
		assert request['messages'][0]['content'] == broker.SCOPE + 'You are the assistant of MonitorEO.'
		assert request['messages'][1:] == body['messages'][1:]
		services._broker('/chat', body={'messages': [{'role': 'user', 'content': 'x'}]}, user=alice)
		assert sent[1][2]['messages'][0] == {'role': 'system', 'content': broker.SCOPE.strip()}  # its own one
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body, user=alice)
		assert e.value.code == 'day' and len(sent) == 2  # 2 requests a day for each user
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body, user=bob)
		assert e.value.code == 'address'  # and 3 an hour for each address
		monkeypatch.setattr(broker, 'CHAT_LIMIT', 100)
		monkeypatch.setattr(broker, 'CHAT_USER_DAY', 100)
		monkeypatch.setattr(broker, 'CHAT_MAX_BYTES', 100)
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body, user=bob)
		assert e.value.code == 'request' and len(sent) == 2  # too big: not sent to Gemini
		monkeypatch.setattr(broker, 'CHAT_MAX_BYTES', 2 ** 20)
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body={'messages': []}, user=bob)
		assert e.value.code == 'request'

		def refused(status, detail):
			def urlopen(req, timeout=None):
				raise urllib.error.HTTPError(req.full_url, status, 'error', {}, io.BytesIO(json.dumps(detail).encode()))
			return urlopen
		monkeypatch.setattr(urllib.request, 'urlopen', refused(429, {'error': {'message': 'quota'}}))
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body, user=bob)
		assert e.value.code == 'busy' and 'try again in a minute' in str(e.value)
		monkeypatch.setattr(urllib.request, 'urlopen', refused(400, [{'error': {'message': 'Invalid schema'}}]))
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body, user=bob)
		assert e.value.code == 'model' and str(e.value).endswith('did not take the request: Invalid schema')
	finally:
		server.shutdown()


def _broker_module(monkeypatch, **env):
	"""broker/main.py loaded with ENV (and the variables it needs)."""
	import importlib.util
	monkeypatch.setenv('PUBLIC_SA', 'public@p.iam.gserviceaccount.com')
	monkeypatch.setenv('EE_PROJECT', 'shared-project')
	for k in ('GEMINI_API_KEY', 'ANTHROPIC_API_KEY', 'CHAT_MODELS', 'CHAT_MODEL', 'CHAT_CHOOSE'):
		monkeypatch.delenv(k, raising=False)
	for k, v in env.items():
		monkeypatch.setenv(k, v)
	path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'broker', 'main.py')
	spec = importlib.util.spec_from_file_location('broker_main', path)
	broker = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(broker)
	return broker


def test_broker_gemini_schemas(monkeypatch):
	# the schemas of the tools as Gemini takes them: «X or null» as X, a region (an object without properties) as JSON
	# text, which the assistant decodes, and without titles, defaults nor additionalProperties; and only what Gemini gave
	# of the blocks of the messages
	broker = _broker_module(monkeypatch)
	tools = [{'type': 'function', 'function': {'name': 'time_series', 'description': 'Series.', 'parameters': {
		'type': 'object', 'title': 'Args', 'required': ['region', 'variable', 'collection'], 'properties': {
			'region': {'type': 'object', 'additionalProperties': True, 'title': 'Region'},
			'variable': {'type': 'string'},
			'season': {'anyOf': [{'type': 'array', 'items': {'type': 'string'}}, {'type': 'null'}], 'default': None},
			'metric': {'anyOf': [{'type': 'string', 'enum': ['mean', 'median']}, {'type': 'null'}], 'default': None,
			           'title': 'Metric', 'description': 'The statistic.'}}}}},
		{'type': 'function', 'function': {'name': 'list_variables', 'description': 'Variables.',
		                                  'parameters': {'type': 'object', 'properties': {}}}}]
	out = broker.gemini_tools(tools)
	params = out[0]['function']['parameters']
	assert params['properties']['region'] == {'type': 'string', 'description': 'A JSON object, written as text.'}
	assert params['properties']['season'] == {'type': 'array', 'items': {'type': 'string'}}
	assert params['properties']['metric'] == {'type': 'string', 'enum': ['mean', 'median'],
	                                          'description': 'The statistic.'}
	assert params['required'] == ['region', 'variable']
	assert 'parameters' not in out[1]['function']  # a tool without arguments
	text = json.dumps(out)
	assert '"title"' not in text and '"default"' not in text and 'additionalProperties' not in text and 'anyOf' not in text
	request = broker.gemini_request({'model': 'gemini-3.8-flash', 'max_tokens': 10, 'tools': tools, 'messages': [
		{'role': 'assistant', 'content': '', 'extra_content': {'anthropic': {'content': []}, 'google': {'s': 1}},
		 'tool_calls': [{'id': 'c', 'extra_content': {'anthropic': 1}, 'function': {'name': 'x', 'arguments': '{}'}}]},
		{'role': 'assistant', 'content': 'a', 'extra_content': {'anthropic': {'content': []}}}]})
	assert request['messages'][0]['extra_content'] == {'google': {'s': 1}}
	assert 'extra_content' not in request['messages'][0]['tool_calls'][0] and 'extra_content' not in request['messages'][1]
	assert request['stream'] is False and request['reasoning_effort'] == 'low' and request['tools'] == out


def test_broker_claude(monkeypatch):
	# Claude through /chat: the request of the assistant (in the form of OpenAI) as the Messages API takes it, with the
	# instructions and the conversation cached, the blocks that Claude gave back as they came, the answers of the tools
	# of a turn together, drop_block, the fallbacks where they exist and no temperature; and its answer in the form of
	# OpenAI, with its blocks to be sent back
	import threading
	from http.server import ThreadingHTTPServer
	broker = _broker_module(monkeypatch, CHAT_MODELS='gemini-3.8-flash,claude-sonnet-5-5,claude-haiku-5-5',
	                        CHAT_CHOOSE='1',
	                        GEMINI_API_KEY='g', ANTHROPIC_API_KEY='a')
	assert broker.CHAT_MODELS == ['gemini-3.8-flash', 'claude-sonnet-5-5', 'claude-haiku-5-5']
	called = []
	thinking = {'type': 'thinking', 'thinking': '', 'signature': 'sig1'}

	def claude_call(params):
		called.append(params)
		return {'model': params['model'], 'stop_reason': 'tool_use', 'content': [
			{'type': 'thinking', 'thinking': '', 'signature': 'sig2'}, {'type': 'text', 'text': 'Busco el área.'},
			{'type': 'tool_use', 'id': 'toolu_2', 'name': 'find_protected_areas', 'input': {'text': 'Doñana'}}],
			'usage': {'input_tokens': 50, 'cache_read_input_tokens': 7000, 'cache_creation_input_tokens': 300,
			          'output_tokens': 120},
			'input_transformations': [{'type': 'thinking_dropped', 'reason': 'prefix_binding_mismatch'}]}
	monkeypatch.setattr(broker, '_claude_call', claude_call)
	asked_gemini = []
	monkeypatch.setattr(broker, 'gemini', lambda request: asked_gemini.append(request['model']) or {
		'model': request['model'], 'choices': [{'message': {'role': 'assistant', 'content': 'Hola'}}]})
	server = ThreadingHTTPServer(('127.0.0.1', 0), broker.Handler)
	threading.Thread(target=server.serve_forever, daemon=True).start()
	monkeypatch.setenv('MONITOREO_BROKER', f'http://127.0.0.1:{server.server_port}')
	user = 'mo-' + 'd' * 16
	tools = [{'type': 'function', 'function': {'name': 'time_series', 'description': 'Series.', 'parameters': {
		'type': 'object', 'properties': {'region': {'type': 'object', 'additionalProperties': True}}}}},
		{'type': 'function', 'function': {'name': 'list_variables', 'description': 'Variables.'}}]
	earlier = [thinking, {'type': 'tool_use', 'id': 'toolu_1', 'name': 'time_series', 'input': {'variable': 'NDVI'}},
	           {'type': 'tool_use', 'id': 'toolu_9', 'name': 'list_variables', 'input': {}}]
	body = {'model': 'claude-sonnet-5-5', 'temperature': 0.2, 'tools': tools, 'messages': [
		{'role': 'system', 'content': 'You are the assistant of MonitorEO.'},
		{'role': 'user', 'content': 'NDVI'},
		{'role': 'assistant', 'content': 'shown text, fixed by the assistant',
		 'extra_content': {'anthropic': {'content': earlier}},
		 'tool_calls': [{'id': 'toolu_1', 'type': 'function', 'function': {'name': 'time_series', 'arguments': '{}'}}]},
		{'role': 'tool', 'tool_call_id': 'toolu_1', 'content': 'Done'},
		{'role': 'tool', 'tool_call_id': 'toolu_9', 'content': 'No answer.'},
		{'role': 'assistant', 'content': 'Hecho.'},
		{'role': 'user', 'content': 'Y en Doñana'}]}
	from monitoreo import services
	try:
		answer = services._broker('/chat', body=body, user=user)
		params = called[0]
		assert params['model'] == 'claude-sonnet-5-5' and params['max_tokens'] == 8192 and 'temperature' not in params
		assert params['system'] == [{'type': 'text', 'text': broker.SCOPE + 'You are the assistant of MonitorEO.',
		                             'cache_control': {'type': 'ephemeral'}}]
		assert params['cache_control'] == {'type': 'ephemeral'}  # and the conversation, with the automatic breakpoint
		assert params['thinking'] == {'type': 'adaptive', 'block_binding': {'prefix_mismatch_behavior': 'drop_block'}}
		assert params['betas'] == ['thinking-binding-controls-2026-08-01', 'server-side-fallback-2026-07-01']
		assert params['fallbacks'] == 'default' and params['output_config'] == {'effort': 'low'}
		assert params['tools'] == [{'name': 'time_series', 'description': 'Series.', 'input_schema': {
			'type': 'object', 'properties': {'region': {'type': 'object', 'additionalProperties': True}}}},
			{'name': 'list_variables', 'description': 'Variables.', 'input_schema': {'type': 'object', 'properties': {}}}]
		assert params['messages'] == [
			{'role': 'user', 'content': 'NDVI'},
			{'role': 'assistant', 'content': earlier},  # as Claude gave it, not the text shown
			{'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'toolu_1', 'content': 'Done'},
			                             {'type': 'tool_result', 'tool_use_id': 'toolu_9', 'content': 'No answer.'}]},
			{'role': 'assistant', 'content': [{'type': 'text', 'text': 'Hecho.'}]},  # a turn of another model
			{'role': 'user', 'content': 'Y en Doñana'}]
		message = answer['choices'][0]['message']
		assert answer['model'] == 'claude-sonnet-5-5' and message['content'] == 'Busco el área.'
		assert message['tool_calls'] == [{'id': 'toolu_2', 'type': 'function', 'function': {
			'name': 'find_protected_areas', 'arguments': '{"text": "Doñana"}'}}]
		assert message['extra_content']['anthropic']['content'][0]['signature'] == 'sig2'
		assert answer['usage'] == {'prompt_tokens': 7350, 'completion_tokens': 120, 'cache_read_tokens': 7000,
		                           'cache_write_tokens': 300} and 'dropped_thinking' not in answer
		services._broker('/chat', body={**body, 'model': 'claude-haiku-5-5'}, user=user)
		assert 'fallbacks' not in called[1] and called[1]['betas'] == ['thinking-binding-controls-2026-08-01']
		services._broker('/chat', body={**body, 'model': 'claude-opus-9'}, user=user)  # not one of CHAT_MODELS
		assert asked_gemini == ['gemini-3.8-flash'] and len(called) == 2  # the first one
	finally:
		server.shutdown()
	refused = broker.claude_answer({'model': 'claude-sonnet-5-5', 'stop_reason': 'refusal', 'content': []})
	assert refused['choices'][0]['message'] == {'role': 'assistant',
	                                           'content': 'The language model of MonitorEO declined this request.'}
	monkeypatch.setattr(broker, 'ANTHROPIC_API_KEY', '')
	with pytest.raises(broker.ChatError) as e:
		broker.chat(json.dumps({**body, 'model': 'claude-sonnet-5-5'}).encode(), '1.2.3.4', user)
	assert e.value.answer['code'] == 'off'  # without its key


def test_broker_without_credit(monkeypatch):
	# Claude Sonnet 5.5 answers, whatever model the request asks for (the users do not choose); only when the API of
	# Anthropic says that there is no credit does Gemini answer, for an hour, and then Claude is asked again
	broker = _broker_module(monkeypatch, GEMINI_API_KEY='g', ANTHROPIC_API_KEY='a')
	assert broker.CHAT_MODELS == ['claude-sonnet-5-5', 'gemini-3.8-flash'] and not broker.CHAT_CHOOSE
	asked, credit = [], {'left': True}

	def claude_call(params):
		asked.append(params['model'])
		if not credit['left']:
			raise broker.ChatError(503, 'credit', 'the language model of MonitorEO has no credit left')
		return {'model': params['model'], 'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'Hola'}]}

	def gemini(request):
		asked.append(request['model'])
		return {'model': request['model'], 'choices': [{'message': {'role': 'assistant', 'content': 'Hola'}}]}
	monkeypatch.setattr(broker, '_claude_call', claude_call)
	monkeypatch.setattr(broker, 'gemini', gemini)
	user = 'mo-' + 'f' * 16
	body = json.dumps({'model': 'gemini-3.8-flash', 'messages': [{'role': 'user', 'content': 'Hola'}]}).encode()
	assert broker.chat(body, '1.1.1.1', user)['model'] == 'claude-sonnet-5-5' and asked == ['claude-sonnet-5-5']
	credit['left'] = False
	assert broker.chat(body, '1.1.1.1', user)['model'] == 'gemini-3.8-flash'
	assert asked[1:] == ['claude-sonnet-5-5', 'gemini-3.8-flash']
	broker.chat(body, '1.1.1.1', user)
	assert asked[3:] == ['gemini-3.8-flash']  # Claude is not asked meanwhile
	broker._no_credit['claude-sonnet-5-5'] = 0  # an hour later
	credit['left'] = True
	assert broker.chat(body, '1.1.1.1', user)['model'] == 'claude-sonnet-5-5'

	def busy(params):
		raise broker.ChatError(503, 'busy', 'the language model of MonitorEO is busy: try again in a minute')
	monkeypatch.setattr(broker, '_claude_call', busy)
	with pytest.raises(broker.ChatError) as e:
		broker.chat(body, '1.1.1.1', user)
	assert e.value.answer['code'] == 'busy' and asked[-1] == 'claude-sonnet-5-5'  # only without credit, Gemini
	monkeypatch.setattr(broker, 'ANTHROPIC_API_KEY', '')
	assert broker.chat(body, '1.1.1.1', user)['model'] == 'gemini-3.8-flash'  # without the key of Claude


def test_eecu_in_the_cli_and_the_mcp_server(monkeypatch, capsys):
	from monitoreo import cli
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	low = {'account': 'shared', 'name': 'research EECUs', 'project': 'p', 'used_percent': 95.0, 'left_percent': 5.0,
	       'bar': '[#############################-] 95%', 'text': 'research EECUs: 95% used', 'warning': 'Few left',
	       'low': True}
	monkeypatch.setattr(services, 'eecu_usage', lambda limit=None, refresh=False, lang='en': low)
	cli.main(['eecu'])
	out = capsys.readouterr()
	assert out.out == 'research EECUs [#############################-] 95%\nresearch EECUs: 95% used\n'
	assert 'WARNING: Few left' in out.err

	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: 'Few left')
	monkeypatch.setattr(services, 'find_protected_areas', lambda text, limit: [])
	cli.main(['parks', 'Sierra'])
	assert 'WARNING: Few left' in capsys.readouterr().err  # after the commands that compute

	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	assert json.loads(mcp_server._eecu_warning('{"a": 1}')) == {'a': 1, 'eecu_warning': 'Few left'}
	out = mcp_server._eecu_warning(['{"a": 1}', 'image'])
	assert json.loads(out[0])['eecu_warning'] == 'Few left' and out[1] == 'image'
	assert mcp_server._eecu_warning('[1, 2]') == '[1, 2]'  # only in objects
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	assert mcp_server._eecu_warning('{"a": 1}') == '{"a": 1}'


def test_assistant_api_unforeseen_error():
	# an error that the API of the assistant does not foresee comes to the page with its cause, not as «Internal
	# Server Error» (issue #26)
	import asyncio
	from starlette.requests import Request
	from monitoreo import assistant

	class Broken:
		async def pixel(self, *a):
			raise IndexError('list index out of range')

	app = assistant.make_app(Broken(), 'tok', 8765)
	route = next(r for r in app.routes if r.path == '/api/pixel')

	async def receive():
		return {'type': 'http.request', 'body': b'{"id": 1, "lon": -3.4, "lat": 37.1}', 'more_body': False}

	request = Request({'type': 'http', 'method': 'POST', 'path': '/api/pixel', 'query_string': b'',
	                   'headers': [(b'host', b'127.0.0.1:8765'), (b'x-token', b'tok')]}, receive)
	response = asyncio.run(route.endpoint(request))
	assert response.status_code == 500
	assert json.loads(response.body) == {'error': 'IndexError: list index out of range'}
