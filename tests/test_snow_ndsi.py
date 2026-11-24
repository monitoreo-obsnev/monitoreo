"""The snow by its NDSI (quality {'snow_ndsi': 0.4}), an option of the pixels: with the snow filter on, Sentinel-2 and
Landsat also lose the pixels of each image whose NDSI (green, SWIR1) is that number or more. Without Earth Engine:
which variables take it and the errors of the others, the specs and their records (unchanged when it is off), the
references, the facts of the README, the command line, the right axis of a profile and the port of gee/core.js (the
same checks, in Node). The panel of the QGIS plugin: tests/test_parameters_qgis.py."""

import json
import os
import shutil
import subprocess

import pytest

from monitoreo import catalog, cli, references, report, sensors, services
from monitoreo import variable as variables

GEE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gee')
PERIOD = ['2021-06-01', '2021-09-30']


def _spec(index, sensor, **quality):
	return variables.specs({'index': index, 'sensor': sensor, 'metric': 'std', 'period': PERIOD,
	                        'quality': quality})[0]


def test_threshold():
	assert sensors.snow_ndsi({'snow_ndsi': 0.4}) == 0.4 and sensors.snow_ndsi({'snow_ndsi': '0.35'}) == 0.35
	assert sensors.snow_ndsi({'snow_ndsi': 1}) == 1.0
	for off in (None, False, '', 'none', 'off'):
		assert sensors.snow_ndsi({'snow_ndsi': off}) is None, off
	assert sensors.snow_ndsi(None) is None and sensors.snow_ndsi({}) is None
	for bad in (0, -0.1, 1.5, True, 'snow'):
		with pytest.raises(ValueError, match='snow_ndsi'):
			sensors.snow_ndsi({'snow_ndsi': bad})


def test_specs_keep_it_only_when_on():
	"""On, the spec has the number (its record changes); off, the spec is that of before (no re-download)."""
	before = _spec('LSWI', 'Sentinel-2')
	assert 'snow_ndsi' not in before['quality']
	for off in (None, False, ''):
		assert _spec('LSWI', 'Sentinel-2', snow_ndsi=off) == before
	assert _spec('LSWI', 'Sentinel-2', snow_ndsi='0.4')['quality']['snow_ndsi'] == 0.4
	assert _spec('NDVI', 'Landsat', snow_ndsi=0.4)['quality']['snow_ndsi'] == 0.4
	with pytest.raises(ValueError, match='at most 1'):
		_spec('LSWI', 'Sentinel-2', snow_ndsi=2)


@pytest.mark.parametrize('index, sensor', [('NDVI', 'Modis'), ('LST', 'Modis'), ('ELEVATION', 'Copernicus')])
def test_other_sensors_refuse_it(index, sensor):
	with pytest.raises(ValueError, match='Sentinel-2 and Landsat'):
		variables.specs({'index': index, 'sensor': sensor, 'metric': 'mean', 'period': PERIOD,
		                 'quality': {'snow_ndsi': 0.4}})


def test_where_it_applies():
	"""Only with the snow filter on, and not for the variables that measure water (open water has a high NDSI too),
	nor the fixed filters of the SCF, nor the NDSI with 'auto'."""
	q = {'snow_ndsi': 0.4}
	assert sensors.snow_ndsi_of(catalog.find('LSWI', 'Sentinel-2'), q) == 0.4
	assert sensors.snow_ndsi_of(catalog.find('NDVI', 'Landsat'), q) == 0.4
	for index in ('NDWI', 'NDCI', 'WAVI', 'Chl-a', 'SCF', 'NDSI'):
		assert sensors.snow_ndsi_of(catalog.find(index, 'Sentinel-2'), dict(q, snow='auto')) is None, index
	assert sensors.snow_ndsi_of(catalog.find('NDWI', 'Sentinel-2'), q) is None  # even with the snow filter on
	assert sensors.snow_ndsi_of(catalog.find('LSWI', 'Sentinel-2'), dict(q, snow=False)) is None
	assert sensors.snow_ndsi_of(catalog.find('NDVI', 'Modis'), q) is None
	e = catalog.find('NDWI', 'Sentinel-2')
	assert 'hall1995' not in references.of_variable(e, q, PERIOD)[0]
	assert 'snow_ndsi' not in variables.describe(variables.specs({'index': 'NDWI', 'sensor': 'Sentinel-2', 'metric': 'mean',
	                                                              'period': PERIOD, 'quality': q})[0])


def test_data_by_id_refuse_it():
	with pytest.raises(ValueError, match='not for the data of Earth Engine'):
		variables.specs({'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr', 'metric': 'mean', 'period': PERIOD,
		                 'quality': {'snow_ndsi': 0.4}})


def test_references_and_description():
	"""Hall et al. 1995 (the NDSI) is cited with it when the snow filter is on, and the metadata say it."""
	e = catalog.find('LSWI', 'Sentinel-2')
	assert 'hall1995' in references.of_variable(e, {'snow_ndsi': 0.4}, PERIOD)[0]
	assert 'hall1995' not in references.of_variable(e, {}, PERIOD)[0]
	assert 'hall1995' not in references.of_variable(e, {'snow_ndsi': 0.4, 'snow': False}, PERIOD)[0]
	assert variables.describe(_spec('LSWI', 'Sentinel-2', snow_ndsi=0.4))['snow_ndsi'] == 0.4
	assert 'snow_ndsi' not in variables.describe(_spec('LSWI', 'Sentinel-2'))
	assert 'snow_ndsi' not in variables.describe(_spec('LSWI', 'Sentinel-2', snow_ndsi=0.4, snow=False))


def test_facts_of_the_readme():
	args = {'region': {'bbox': [-3.5, 37, -3, 37.2]}, 'variable': 'LSWI', 'sensor': 'Sentinel-2', 'start': PERIOD[0],
	        'end': PERIOD[1], 'quality': {'snow_ndsi': 0.4}}
	facts = dict(report.item_facts('map_layer', args, {}))
	assert 'NDSI (green, SWIR1) of 0.4 or more' in facts['Discarded pixels']
	assert 'NDSI' not in dict(report.item_facts('map_layer', dict(args, quality={}), {}))['Discarded pixels']


def test_command_line(monkeypatch):
	"""--snow-ndsi gives the quality of the services, and is refused with the data by ID."""
	seen = {}

	def fake(region, **kw):
		seen.update(kw)
		raise ValueError('stop')

	monkeypatch.setattr(services, 'map_figure', fake)
	monkeypatch.setattr(services, 'init', lambda *a, **k: None)
	with pytest.raises(SystemExit):
		cli.main(['figure', 'LSWI', '--sensor', 'Sentinel-2', '--region', '{"bbox": [-3.5, 37, -3, 37.2]}', '--start',
		          PERIOD[0], '--end', PERIOD[1], '--out', 'x.png', '--snow-ndsi', '0.4'])
	assert seen['quality'] == {'snow_ndsi': 0.4}
	with pytest.raises(SystemExit):
		cli.main(['figure', '--collection', 'IDAHO_EPSCOR/TERRACLIMATE', '--band', 'pr', '--region',
		          '{"bbox": [-3.5, 37, -3, 37.2]}', '--start', PERIOD[0], '--end', PERIOD[1], '--out', 'x.png',
		          '--snow-ndsi', '0.4'])


def test_right_axis_of_a_profile():
	"""The other variable of a profile gets it only if it is of Sentinel-2 or Landsat."""
	q = {'snow_ndsi': 0.4}
	modis = services._other_spec('NDVI', 'Modis', PERIOD[0], PERIOD[1], 'mean', None, q, {})
	assert 'snow_ndsi' not in modis['quality']
	s2 = services._other_spec('NDVI', 'Sentinel-2', PERIOD[0], PERIOD[1], 'mean', None, q, {})
	assert s2['quality']['snow_ndsi'] == 0.4


CORE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
function nothing() { return new Proxy(function () {}, {get: function () { return nothing(); }, apply: nothing}); }
global.ee = nothing();
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[process.argv.length - 1], f), 'utf8'), {filename: f});
});
var mo = MonitorEO;
var out = {values: input.values.map(function (v) {
	try { return mo.snowNdsi({snow_ndsi: v}); } catch (e) { return 'error'; }
}), sensors: Object.keys(mo.SNOW_NDSI).sort(), bands: mo.SNOW_NDSI, def: mo.SNOW_NDSI_DEFAULT,
	of: input.refs.map(function (r) { return mo.snowNdsiOf(mo.byRef(r), input.quality); })};
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_app_takes_it_as_the_package():
	values = [0.4, '0.35', 1, None, False, '', '  ', 'off', 0, -0.1, 1.5, True, 'snow']
	refs = [e['ref'] for e in catalog.variables() if e['sensor'] in sensors.SNOW_NDSI]
	quality = {'snow_ndsi': 0.4, 'snow': 'auto'}
	run = subprocess.run(['node', '-e', CORE, GEE], input=json.dumps({'values': values, 'refs': refs, 'quality': quality}),
	                     capture_output=True,
	                     text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	app = json.loads(run.stdout.strip().splitlines()[-1])

	def python(v):
		try:
			return sensors.snow_ndsi({'snow_ndsi': v})
		except ValueError:
			return 'error'

	assert app['values'] == [python(v) for v in values]
	assert app['sensors'] == sorted(sensors.SNOW_NDSI) and app['def'] == sensors.SNOW_NDSI_DEFAULT
	assert {k: tuple(v) for k, v in app['bands'].items()} == sensors.SNOW_NDSI
	python_of = [sensors.snow_ndsi_of(catalog.find(None, ref=r), quality) for r in refs]
	assert app['of'] == python_of and 0.4 in python_of and None in python_of
