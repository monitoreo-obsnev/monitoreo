"""The options of Landsat and of the series, without Earth Engine: Landsat 5 and 7 harmonized with Landsat 8 and 9
(quality {'harmonize': True}, Roy et al. 2016), Landsat 7 after the failure of its scan line corrector (quality
{'landsat7': True}) and the minimum coverage of the steps of a series (min_coverage). Which variables take them, the
errors of the others, the specs (unchanged when they are off), the dates of the images and their gap, the datasets and
references, the facts of the README, the command line and the rows of the series. The port of gee/core.js:
tests/test_coverage.py and the tests of the app."""

import json
import os
import shutil
import subprocess

import pytest

from monitoreo import catalog, cli, coverage, references, report, sensors, services, timeseries
from monitoreo import variable as variables

PERIOD = ['2010-01-01', '2015-12-31']
GAP = ['2012-06-01', '2013-02-28']  # between Landsat 5 and Landsat 8


def _spec(index, sensor, period=PERIOD, defaults=None, **quality):
	return variables.specs({'index': index, 'sensor': sensor, 'metric': 'mean', 'period': period,
	                        **({'quality': quality} if quality else {})}, defaults)[0]


def test_the_harmonization_is_that_of_roy_et_al():
	"""OLI = intercept + slope x ETM+ on the reflectance; _harmonized does it on the raw values (scale and offset of
	Collection 2 Level-2), so the formulas read them as those of Landsat 8 and 9."""
	assert sensors.HARMONIZE['nir'] == (0.8462, 0.0412) and sensors.HARMONIZE['red'] == (0.9047, 0.0061)
	assert set(sensors.HARMONIZE) == set(sensors.REFLECTANCE['Landsat'])
	scale, offset = sensors.LANDSAT_SR
	for band, (slope, intercept) in sensors.HARMONIZE.items():
		raw = 12345.0
		add = (intercept + (slope - 1) * offset) / scale
		assert (raw * slope + add) * scale + offset == pytest.approx(intercept + slope * (raw * scale + offset)), band


def test_specs_keep_them_only_when_on():
	before = _spec('NDVI', 'Landsat')
	assert 'harmonize' not in before['quality'] and 'landsat7' not in before['quality']
	assert _spec('NDVI', 'Landsat', harmonize=False, landsat7='off') == before
	q = _spec('NDVI', 'Landsat', harmonize='yes', landsat7=True)['quality']
	assert q['harmonize'] is True and q['landsat7'] is True
	with pytest.raises(ValueError, match='true or false'):
		_spec('NDVI', 'Landsat', harmonize='maybe')


@pytest.mark.parametrize('index, sensor, option, match', [
	('NDVI', 'Sentinel-2', 'harmonize', 'not a variable of Landsat'), ('LST', 'Landsat', 'harmonize', 'reflectances'),
	('SCF', 'Landsat', 'harmonize', 'shadow of the relief'), ('NDVI', 'Modis', 'landsat7', 'for the variables of Landsat'),
	('NDVI', 'Sentinel-2', 'landsat7', 'for the variables of Landsat')])
def test_the_others_refuse_them(index, sensor, option, match):
	with pytest.raises(ValueError, match=match):
		_spec(index, sensor, period=['2020-01-01', '2020-12-31'], **{option: True})


def test_from_the_defaults_of_a_recipe_only_where_they_apply():
	"""As snow_ndsi: the options of a whole recipe go to the variables that can have them, without an error."""
	defaults = {'quality': {'harmonize': True, 'landsat7': True}}
	q = _spec('NDVI', 'Sentinel-2', period=['2020-01-01', '2020-12-31'], defaults=defaults)['quality']
	assert 'harmonize' not in q and 'landsat7' not in q
	q = _spec('LST', 'Landsat', defaults=defaults)['quality']
	assert 'harmonize' not in q and q['landsat7'] is True
	q = _spec('NDVI', 'Landsat', defaults=defaults)['quality']
	assert q['harmonize'] is True and q['landsat7'] is True


def test_landsat7_fills_the_gap_of_2012():
	with pytest.raises(ValueError, match='quality landsat7: true') as e:
		_spec('NDVI', 'Landsat', period=GAP)
	assert '2012-05-06 to 2013-03-17' in str(e.value)
	assert _spec('NDVI', 'Landsat', period=GAP, landsat7=True)['quality']['landsat7'] is True
	entry = catalog.find('NDVI', 'Landsat')
	last = {p[0]: p[2] for p in coverage.parts(entry)}
	seven = {p[0]: p[2] for p in coverage.parts(entry, {'landsat7': True})}
	assert last['LANDSAT/LE07/C02/T1_L2'] == '2003-05-31' and seven['LANDSAT/LE07/C02/T1_L2'] > '2013-03-18'
	assert references.datasets('LANDSAT', tuple(GAP)) == []
	assert references.datasets('LANDSAT', tuple(GAP), {'landsat7': True}) == ['LANDSAT/LE07/C02/T1_L2']
	assert [c for c, _, last in sensors.landsat_parts({'landsat7': True}) if last] == []


def test_the_data_of_the_values_name_landsat7():
	spec = _spec('NDVI', 'Landsat', period=GAP, landsat7=True)
	with coverage.collect() as notes:
		coverage.used(spec, variables.entry_of(spec))
	assert 'LANDSAT/LE07/C02/T1_L2' in notes.source() and 'LC08' not in notes.source()
	index = coverage.app_index()
	assert [p[0] for p in index['landsat7']] == [c for c, _, _ in sensors.LANDSAT]


def test_references_and_facts():
	entry = catalog.find('NDVI', 'Landsat')
	ids, _ = references.of_variable(entry, {'harmonize': True})
	assert 'roy2016' in ids and 'roy2016' not in references.of_variable(entry, {})[0]
	assert catalog.load()['references']['roy2016']['doi'] == '10.1016/j.rse.2015.12.024'
	spec = _spec('NDVI', 'Landsat', harmonize=True, landsat7=True)
	d = variables.describe(spec)
	assert d['harmonization'] == variables.HARMONIZE_TEXT and d['landsat7'] == variables.LANDSAT7_TEXT
	off = variables.describe(_spec('NDVI', 'Landsat'))
	assert 'harmonization' not in off and 'landsat7' not in off
	assert '0.0412 + 0.8462 x nir' in variables.HARMONIZE_TEXT


def test_the_minimum_coverage():
	assert timeseries.check_min_coverage(0.5) == 0.5 and timeseries.check_min_coverage('0.25') == 0.25
	for off in (None, False, '', 'off', 0):
		assert timeseries.check_min_coverage(off) is None, off
	for bad in (50, -0.1, True, 'half'):
		with pytest.raises(ValueError, match='min_coverage'):
			timeseries.check_min_coverage(bad)


def test_the_rows_without_value_have_coverage(monkeypatch):
	seen = []

	def table(spec, regions, step, metric, stat, scale, steps, crs, **kw):
		seen.append(kw)

		class FC:
			def getInfo(self):
				return {'features': [{'properties': {'date': s, 'n_images': 1}} for s in steps]}
		return FC()
	monkeypatch.setattr(timeseries, 'table', table)
	rows = timeseries._fetch(None, None, 'monthly', 'mean', 'mean', 30, ['a'], 'EPSG:32630', min_coverage=0.5)
	assert rows == [{'value': None, 'n_pixels': 0, 'coverage': 0, 'date': 'a', 'n_images': 1}]
	assert seen == [{'min_coverage': 0.5}]
	rows = timeseries._fetch(None, None, 'monthly', 'mean', 'mean', 30, ['a'], 'EPSG:32630')
	assert 'coverage' not in rows[0] and seen[-1] == {}


def test_the_services_pass_it(monkeypatch):
	got = []

	def series(spec, regions, step, metric, stat, scale, progress=None, steps=None, **kw):
		got.append(kw)
		return [], 30
	monkeypatch.setattr(timeseries, 'series', series)
	monkeypatch.setattr(services.areas, 'region', lambda r: None)
	services.time_series({'wdpa_id': 1}, 'NDVI', 'Landsat', '2014-01-01', '2014-12-31', min_coverage=0.4)
	assert got[-1] == {'min_coverage': 0.4}
	with pytest.raises(ValueError, match='min_coverage'):
		services.time_series({'wdpa_id': 1}, 'NDVI', 'Landsat', '2014-01-01', '2014-12-31', min_coverage=40)


def test_the_command_line(capsys):
	import argparse
	args = argparse.Namespace(harmonize=True, landsat7=True, topographic_correction=False, snow_ndsi=None)
	assert cli._topographic(args) == {'quality': {'harmonize': True, 'landsat7': True}}
	for cmd in ('series', 'trend', 'compare'):
		with pytest.raises(SystemExit):
			cli.main([cmd, '--help'])
		text = ' '.join(capsys.readouterr().out.split())
		assert '--harmonize' in text and '--landsat7' in text and '--min-coverage' in text, cmd


def test_the_facts_of_the_readme():
	args = {'variable': 'NDVI', 'sensor': 'Landsat', 'start': '1990-01-01', 'end': '2020-12-31',
	        'quality': {'harmonize': True, 'landsat7': True}, 'min_coverage': 0.5}
	facts = dict(report.item_facts('time_series', args, {'scale': 30}))
	assert facts['Landsat 5 and 7 harmonized'] == variables.HARMONIZE_TEXT
	assert facts['Landsat 7'] == variables.LANDSAT7_TEXT and '0.5' in facts['Minimum coverage']


GEE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gee')
CORE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
function nothing() { return new Proxy(function () {}, {get: function () { return nothing(); }, apply: nothing}); }
global.ee = nothing();
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[process.argv.length - 1], f), 'utf8'), {filename: f});
});
var mo = MonitorEO;
function tried(f) { try { return f(); } catch (e) { return 'error'; } }
process.stdout.write(JSON.stringify({
	coverage: input.coverage.map(function (v) { return tried(function () { return mo.checkMinCoverage(v); }); }),
	harmonize: input.refs.map(function (r) { return mo.noHarmonize(mo.byRef(r)) === null; }),
	parts: [false, true].map(function (q) { return mo.landsatParts({landsat7: q}); }),
	table: mo.HARMONIZE}));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_app_takes_them_as_the_package():
	coverage = [0.5, '0.25', 1, 0, None, False, '', 'off', 50, -0.1, True, 'half']
	refs = [e['ref'] for e in catalog.variables()]
	run = subprocess.run(['node', '-e', CORE, GEE], input=json.dumps({'coverage': coverage, 'refs': refs}),
	                     capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	app = json.loads(run.stdout.strip().splitlines()[-1])

	def python(v):
		try:
			return timeseries.check_min_coverage(v)
		except ValueError:
			return 'error'

	assert app['coverage'] == [python(v) for v in coverage]
	assert app['harmonize'] == [sensors.no_harmonize(catalog.find(None, ref=r)) is None for r in refs]
	assert True in app['harmonize'] and False in app['harmonize']
	for q, parts in zip((False, True), app['parts']):
		assert [[c, last] for c, _, last in sensors.landsat_parts({'landsat7': q})] == [[p[0], p[2]] for p in parts]
	assert {k: tuple(v) for k, v in app['table'].items()} == sensors.HARMONIZE
