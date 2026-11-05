"""Tests that do not need Earth Engine."""

import csv
import datetime as dt
import json
import re

import pytest

from monitoreo import catalog, charts, composite, drive, fire, sensors, services, timeseries, trends, variable
from monitoreo.grid import Grid


def test_catalog():
	entries = catalog.variables()
	assert len(entries) == 34  # the 32 of catalog.json and NBR of Landsat and Sentinel-2
	nbr = catalog.find('NBR', 'Sentinel-2')
	assert nbr['ref'] == 102 and nbr['ft'] == 'N(B8,B12)' and nbr['col'] == 'COPERNICUS/S2_SR_HARMONIZED'
	assert catalog.find('nbr', 'landsat')['ft'] == 'N(nir,swir2)'
	assert catalog.find('ndvi', 'sentinel-2')['col'] == 'COPERNICUS/S2_SR_HARMONIZED'
	assert catalog.find('NDVI', 'Modis')['col'] == 'MODIS/061/MOD13Q1'  # first entry of the catalog
	assert catalog.find(None, ref=32)['scale'] == 0.1  # FIXES: scale of LAI
	with pytest.raises(KeyError):
		catalog.find('NDVI', 'Planet')


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
	spec = importlib.util.spec_from_file_location('broker_main', os.path.join(
		os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'broker', 'main.py'))
	broker = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(broker)
	assert broker.USER_LIMIT == 10 and broker.REQUIRE_USER
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
