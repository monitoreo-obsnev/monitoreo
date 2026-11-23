"""The topographic correction SCS+C (Soenen et al. 2005) of the surface reflectance of Landsat, an option of the
pixels (quality {'topographic': True}), without Earth Engine: which variables take it and the errors of those
that do not, the specs and their records (unchanged when it is off), the references, the facts of the README, the
command line, the right axis of a profile and the port of gee/core.js (the same variables, in Node)."""

import json
import os
import shutil
import subprocess

import pytest

from monitoreo import catalog, cli, references, report, sensors, services
from monitoreo import variable as variables

GEE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gee')
PERIOD = ['2021-01-01', '2021-12-31']


def _spec(index, sensor, **quality):
	return variables.specs({'index': index, 'sensor': sensor, 'metric': 'median', 'period': PERIOD,
	                        'quality': quality})[0]


def test_which_variables_take_it():
	"""The surface reflectance of Landsat (also the NBR, RBR and RdNBR of the fires), not Sentinel-2 (its Level-2A is
	already corrected), the land surface temperature, the snow or cloud frequency, MODIS, the climate or the fixed
	layers."""
	can = {(e['index'], e['sensor']) for e in catalog.variables() if not sensors.no_topographic(e)}
	for v in [('NDVI', 'Landsat'), ('EVI', 'Landsat'), ('ALBEDO', 'Landsat'), ('NBR', 'Landsat'), ('RdNBR', 'Landsat'),
	          ('NDWI', 'Landsat')]:
		assert v in can, v
	for v in [('NDVI', 'Sentinel-2'), ('LST', 'Landsat'), ('SCF', 'Landsat'), ('SCD', 'Sentinel-2'), ('CF', 'Landsat'),
	          ('NDVI', 'Modis'), ('ELEVATION', 'Copernicus')]:
		assert v not in can, v
	assert {s for _, s in can} == {'Landsat'}
	assert 'Sen2Cor' in sensors.no_topographic(catalog.find('NDVI', 'Sentinel-2'))
	rows = services.list_variables()
	assert {(r['variable'], r['sensor']) for r in rows if r.get('topographic')} == can


def test_specs_keep_it_only_when_on():
	"""On, the spec has it (its record changes); off, false or 'false', the spec is that of before (no re-download)."""
	before = _spec('NDVI', 'Landsat')
	assert 'topographic' not in before['quality']
	for off in (False, None, 'false', 0):
		assert _spec('NDVI', 'Landsat', topographic=off) == before
	assert _spec('NDVI', 'Sentinel-2', topographic=False) == _spec('NDVI', 'Sentinel-2')
	on = _spec('NDVI', 'Landsat', topographic=True)
	assert on['quality']['topographic'] is True
	assert _spec('NDVI', 'Landsat', topographic='true')['quality']['topographic'] is True
	assert not sensors.topographic({'topographic': 'false'}) and sensors.topographic({'topographic': 'on'})
	assert not sensors.topographic(None) and not sensors.topographic({'topographic': 0})
	with pytest.raises(ValueError, match='true or false'):
		_spec('NDVI', 'Landsat', topographic='scs')


@pytest.mark.parametrize('index, sensor', [('NDVI', 'Sentinel-2'), ('LST', 'Landsat'), ('SCF', 'Sentinel-2'),
                                           ('NDVI', 'Modis'), ('CF', 'Landsat')])
def test_variables_without_it_say_why(index, sensor):
	with pytest.raises(ValueError, match='topographic correction'):
		_spec(index, sensor, topographic=True)


def test_data_by_id_without_it():
	with pytest.raises(ValueError, match='not for the data of Earth Engine'):
		variables.specs({'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr', 'metric': 'mean', 'period': PERIOD,
		                 'quality': {'topographic': True}})


def test_references_and_description():
	"""Soenen et al. 2005 and the SRTM of the slope and aspect are cited with it, and the metadata say it."""
	e = catalog.find('NDVI', 'Landsat')
	ids, _ = references.of_variable(e, {'topographic': True}, PERIOD)
	assert 'soenen2005' in ids and 'farr2007' in ids
	assert 'soenen2005' not in references.of_variable(e, {}, PERIOD)[0]
	assert references.get('soenen2005')['doi'] == '10.1109/TGRS.2005.852480'
	d = variables.describe(_spec('NDVI', 'Landsat', topographic=True))
	assert 'SCS+C' in d['topographic_correction'] and '10 km' in d['topographic_correction']
	assert 'topographic_correction' not in variables.describe(_spec('NDVI', 'Landsat'))


def test_facts_of_the_readme():
	args = {'region': {'bbox': [-3.5, 37, -3, 37.2]}, 'variable': 'NDVI', 'sensor': 'Landsat', 'start': PERIOD[0],
	        'end': PERIOD[1], 'quality': {'topographic': True}}
	facts = dict(report.item_facts('map_layer', args, {}))
	assert 'SCS+C' in facts['Topographic correction']
	assert 'Topographic correction' not in dict(report.item_facts('map_layer', dict(args, quality={}), {}))


def test_command_line(monkeypatch):
	"""--topographic-correction gives the quality of the services, and is refused with the data by ID."""
	seen = {}

	def fake(region, **kw):
		seen.update(kw)
		raise ValueError('stop')

	monkeypatch.setattr(services, 'map_figure', fake)
	monkeypatch.setattr(services, 'init', lambda *a, **k: None)
	with pytest.raises(SystemExit):
		cli.main(['figure', 'NDVI', '--sensor', 'Landsat', '--region', '{"bbox": [-3.5, 37, -3, 37.2]}', '--start',
		          PERIOD[0], '--end', PERIOD[1], '--out', 'x.png', '--topographic-correction'])
	assert seen['quality'] == {'topographic': True}
	with pytest.raises(SystemExit):
		cli.main(['figure', '--collection', 'IDAHO_EPSCOR/TERRACLIMATE', '--band', 'pr', '--region',
		          '{"bbox": [-3.5, 37, -3, 37.2]}', '--start', PERIOD[0], '--end', PERIOD[1], '--out', 'x.png',
		          '--topographic-correction'])


def test_right_axis_of_a_profile():
	"""The other variable of a profile gets it only if it is a surface reflectance (as 'auto' for the filters)."""
	q = {'topographic': True}
	lst = services._other_spec('LST', 'Landsat', PERIOD[0], PERIOD[1], 'mean', None, q, {})
	assert 'topographic' not in lst['quality']
	ndvi = services._other_spec('NDVI', 'Landsat', PERIOD[0], PERIOD[1], 'mean', None, q, {})
	assert ndvi['quality']['topographic'] is True


CORE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
function nothing() { return new Proxy(function () {}, {get: function () { return nothing(); }, apply: nothing}); }
global.ee = nothing();
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[process.argv.length - 1], f), 'utf8'), {filename: f});
});
var mo = MonitorEO;
var out = {};
input.refs.forEach(function (r) {
	var e = mo.byRef(r);
	if (e) out[r] = mo.noTopographic(e) === null;
});
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_app_takes_it_for_the_same_variables():
	refs = [e['ref'] for e in catalog.variables()]
	run = subprocess.run(['node', '-e', CORE, GEE], input=json.dumps({'refs': refs}), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	app = json.loads(run.stdout.strip().splitlines()[-1])
	python = {str(e['ref']): not sensors.no_topographic(e) for e in catalog.variables() if str(e['ref']) in app}
	assert python and {k: app[k] for k in python} == python
