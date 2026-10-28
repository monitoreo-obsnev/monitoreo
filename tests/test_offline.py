"""Tests that do not need Earth Engine."""

import csv
import datetime as dt

import pytest

from monitoreo import catalog, charts, composite, drive, sensors, services, timeseries, variable
from monitoreo.grid import Grid


def test_catalog():
	entries = catalog.variables()
	assert len(entries) == 32
	assert catalog.find('ndvi', 'sentinel-2')['col'] == 'COPERNICUS/S2_SR_HARMONIZED'
	assert catalog.find('NDVI', 'Modis')['col'] == 'MODIS/061/MOD13Q1'  # first entry of the catalog
	assert catalog.find(None, ref=32)['scale'] == 0.1  # FIXES: scale of LAI
	with pytest.raises(KeyError):
		catalog.find('NDVI', 'Planet')
	assert catalog.load()['source']['imported']


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
	assert update.ensure_latest('mcp,plot', log=quiet) == 'updated'
	url = f'https://github.com/monitoreo-obsnev/monitoreo/archive/{new}.zip'
	assert calls == [('--force-reinstall', '--no-deps', f'monitoreo @ {url}'), (f'monitoreo[mcp,plot] @ {url}',)]
	monkeypatch.setattr(update, 'installed', lambda: ('0.2.0', new, None))
	assert update.ensure_latest(log=quiet) == 'current'
	monkeypatch.setattr(update, 'local_copy', lambda: '/clone/src/monitoreo')
	assert update.ensure_latest(log=quiet) == 'local' and len(calls) == 2

	def offline():
		raise OSError('no network')
	monkeypatch.setattr(update, 'latest', offline)
	assert update.ensure_latest(log=quiet) == 'offline'
