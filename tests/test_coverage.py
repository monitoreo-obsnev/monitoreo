"""The dates of the data (monitoreo.coverage), without Earth Engine: the first and last day of the images of each
variable from the copy of the index of the Earth Engine data catalog, a period without images refused before Earth
Engine, the warnings of a period that begins before the first image (or ends after the last one of data that ended) in
the answers and as Python warnings, and the data of the values ('data_source': the collections and their product level)
in the answers, the charts, the facts of the reports and every tool (MCP server, assistant, command line, the Earth
Engine app in Node)."""

import datetime as dt
import json
import os
import shutil
import subprocess
import warnings

import pytest

from monitoreo import assistant, catalog, charts, coverage, mcp_server, report, services, timeseries

S2 = 'COPERNICUS/S2_SR_HARMONIZED (Harmonized Sentinel-2 MSI, Level-2A (SR))'
TODAY = dt.date(2026, 11, 17)
GEE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gee')
REGION = {'bbox': [-3.45, 37.02, -3.30, 37.12]}


@pytest.fixture
def ended(monkeypatch):
	"""TerraClimate with its last image on 2024-12-01 (as the copy of the index of 2026-11-14), whatever the copy."""
	rec = coverage._records()['IDAHO_EPSCOR/TERRACLIMATE']
	monkeypatch.setitem(coverage._records(), 'IDAHO_EPSCOR/TERRACLIMATE', dict(rec, end='2024-12-01'))


def _check(index, sensor, start, end, season=None, today=TODAY):
	"""The warnings of coverage.check for the variable INDEX of SENSOR over START to END, without Python warnings."""
	with warnings.catch_warnings():
		warnings.simplefilter('ignore', coverage.DataDatesWarning)
		return coverage.check({'period': [start, end], 'season': season}, catalog.find(index, sensor), today)


def test_the_titles_and_the_product_level():
	assert coverage.short_title('Harmonized Sentinel-2 MSI: MultiSpectral Instrument, Level-2A (SR)') == \
		'Harmonized Sentinel-2 MSI, Level-2A (SR)'
	assert coverage.short_title('Harmonized Sentinel-2 MSI: MultiSpectral Instrument, Level-1C (TOA)') == \
		'Harmonized Sentinel-2 MSI, Level-1C (TOA)'
	assert coverage.title('IDAHO_EPSCOR/TERRACLIMATE') == 'TerraClimate'  # a long title: before its subtitle
	assert coverage.title('MODIS/061/MOD13Q1') == 'MOD13Q1.061 Terra Vegetation Indices 16-Day Global 250m'
	assert coverage.title('NOT/IN/ANY/INDEX') is None
	assert coverage.join_titles([f'USGS Landsat {n} Level 2, Collection 2, Tier 1' for n in (5, 7, 8, 9)]) == \
		'USGS Landsat 5, 7, 8 and 9 Level 2, Collection 2, Tier 1'
	assert coverage.join_titles(['A b', 'C d']) == 'A b; C d'


def test_the_dates_and_the_data_of_each_variable():
	s2 = catalog.find('NDVI', 'Sentinel-2')
	assert coverage.dates(s2) == {'start': '2017-03-28', 'end': None}  # level 2A: from 2017-03-28, it goes on
	assert coverage.of_entry(s2)['text'] == S2
	landsat = catalog.find('NDVI', 'Landsat')
	assert coverage.dates(landsat) == {'start': '1984-03-16', 'end': None}
	parts = dict((p[0], p[1:]) for p in coverage.parts(landsat))
	assert parts['LANDSAT/LE07/C02/T1_L2'][1] == '2003-05-31'  # Landsat 7 only until then (sensors.LANDSAT)
	recent = coverage.of_entry(landsat, [('2016-01-01', '2026-12-31')])
	assert recent['collections'] == ['LANDSAT/LC08/C02/T1_L2', 'LANDSAT/LC09/C02/T1_L2']
	assert recent['text'] == ('LANDSAT/LC08/C02/T1_L2 and LANDSAT/LC09/C02/T1_L2 (USGS Landsat 8 and 9 Level 2, '
	                          'Collection 2, Tier 1)')
	assert coverage.dates(catalog.find('PRECIP', 'TerraClimate'))['start'] == '1958-01-01'
	assert coverage.dates(catalog.find('NDWI', 'Modis')) == {'start': '2000-02-24', 'end': '2023-02-17'}  # it ended
	assert coverage.dates(catalog.find('ELEVATION', 'Copernicus')) == {'start': None, 'end': None}  # a fixed layer
	assert coverage.of_asset('COPERNICUS/S2_HARMONIZED')['text'] == \
		'COPERNICUS/S2_HARMONIZED (Harmonized Sentinel-2 MSI, Level-1C (TOA))'
	assert coverage.checked() >= '2026-11-14'


def test_the_period_of_the_user_of_the_feedback_form():
	# a series of NDVI of Sentinel-2 from 2016 to 2026: its images (level 2A) start on 2017-03-28
	assert _check('NDVI', 'Sentinel-2', '2016-01-01', '2026-12-31') == [
		f'The images of {S2} start on 2017-03-28: the period asked for begins on 2016-01-01, so its first 15 months '
		'have no data.']
	assert _check('NDVI', 'Sentinel-2', '2017-03-01', '2017-12-31') == [
		f'The images of {S2} start on 2017-03-28: the period asked for begins on 2017-03-01, so its first 27 days '
		'have no data.']
	assert _check('NDVI', 'Sentinel-2', '2018-01-01', '2026-12-31') == []  # it goes on: no warning for its end
	assert _check('NDVI', 'Sentinel-2', '2016-01-01', '2020-12-31', ['06-01', '08-31']) == [
		f'The images of {S2} start on 2017-03-28: the period asked for (in its season) begins on 2016-06-01, so its '
		'first 10 months have no data.']
	assert _check('NDVI', 'Sentinel-2', '2017-06-01', '2020-12-31', ['06-01', '08-31']) == []


def test_a_period_without_images_is_an_error(ended):
	with pytest.raises(ValueError, match=r'start on 2017-03-28: the period asked for, 2015-01-01 to 2016-12-31, ends '
	                                     r'before them and has no data\. Choose a period from 2017-03-28 on\.'):
		_check('NDVI', 'Sentinel-2', '2015-01-01', '2016-12-31')
	with pytest.raises(ValueError, match=r'TERRACLIMATE \(TerraClimate\) end on 2024-12-01: the period asked for, '
	                                     r'2025-01-01 to 2025-12-31, begins after them'):
		_check('PRECIP', 'TerraClimate', '2025-01-01', '2025-12-31')
	# between the last image of Landsat 5 and the first of Landsat 8 (Landsat 7 only until 2003-05-31)
	with pytest.raises(ValueError, match='have none from 2012-05-06 to 2013-03-17: the period asked for, 2012-06-01 '
	                                     'to 2013-02-28, has no data'):
		_check('NDVI', 'Landsat', '2012-06-01', '2013-02-28')
	with pytest.raises(ValueError, match=r'begins after today \(2026-11-17\): there are no images of COPERNICUS/S2'):
		_check('NDVI', 'Sentinel-2', '2027-01-01', '2027-12-31')


def test_the_end_of_data_that_ended(ended):
	# TerraClimate, monthly: its last image (2024-12-01) covers December
	assert _check('PRECIP', 'TerraClimate', '2020-01-01', '2024-12-31') == []
	assert _check('PRECIP', 'TerraClimate', '2020-01-01', '2025-03-31') == [
		'The images of IDAHO_EPSCOR/TERRACLIMATE (TerraClimate) end on 2024-12-01: the period asked for ends on '
		'2025-03-31, so its last 3 months have no data.']
	assert coverage.step_days(catalog.find('ET', 'Modis')) == 8 and coverage.step_days({'tr': 'daily'}) == 1
	assert _check('ELEVATION', 'Copernicus', '1990-01-01', '1990-12-31') == []  # a fixed layer: no dates


def test_the_services_refuse_and_warn_before_earth_engine(ended):
	with pytest.raises(ValueError, match='start on 2017-03-28'):
		services.make_spec('NDVI', 'Sentinel-2', '2015-01-01', '2016-12-31')
	with pytest.warns(coverage.DataDatesWarning, match='first 15 months have no data'):
		services.make_spec('NDVI', 'Sentinel-2', '2016-01-01', '2026-12-31')
	# the conditions of where too, named
	with pytest.raises(ValueError, match=r'^where, the condition on PRECIP \(TerraClimate\): The images of '
	                                     'IDAHO_EPSCOR/TERRACLIMATE'):
		services.make_spec('NDVI', 'Modis', '2025-01-01', '2025-12-31',
		                   where=[{'variable': 'PRECIP', 'sensor': 'TerraClimate', 'min': 10}])
	# the data given by their ID: the dates of their record of the index
	with pytest.warns(coverage.DataDatesWarning, match=r'S2_HARMONIZED \(Harmonized Sentinel-2 MSI, Level-1C \(TOA\)\) '
	                                                   'start on 2015-06-27'):
		services.make_spec(collection='COPERNICUS/S2_HARMONIZED', band='B4', start='2014-01-01', end='2016-12-31')


@pytest.fixture
def ee(monkeypatch):
	"""time_series without Earth Engine: a value for each step of the period, and the chart drawn (or not)."""
	drawn = []

	def series(spec, regions, step='monthly', metric='mean', stat='mean', scale=None, progress=None, steps=None):
		return [{'region': 'park', 'date': a, 'value': 0.5, 'n_pixels': 4, 'n_images': 1}
		        for a, _ in timeseries.bins(spec, step)], 10.0

	monkeypatch.setattr(services.areas, 'region', lambda region: 'regions')
	monkeypatch.setattr(services.timeseries, 'series', series)
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	monkeypatch.setattr(services.charts, 'time_series_png', lambda rows, path, **kw: drawn.append(kw))
	return drawn


def test_the_answer_has_the_warnings_and_the_data(ee, tmp_path):
	with pytest.warns(coverage.DataDatesWarning) as caught:
		out = services.time_series(REGION, 'NDVI', 'Sentinel-2', '2016-01-01', '2026-12-31', step='annual',
		                           chart=str(tmp_path / 'chart.png'))
	assert len([w for w in caught if issubclass(w.category, coverage.DataDatesWarning)]) == 1  # once in a call
	assert out['warnings'] == [f'The images of {S2} start on 2017-03-28: the period asked for begins on 2016-01-01, '
	                           'so its first 15 months have no data.']
	assert out['data_source'] == S2
	assert ee[0]['source'] == S2  # the chart says it
	# a period with images of its data all along: no warnings, the data all the same
	out = services.time_series(REGION, 'NDVI', 'Landsat', '2016-01-01', '2020-12-31', step='annual')
	assert 'warnings' not in out
	assert out['data_source'].startswith('LANDSAT/LC08/C02/T1_L2 (USGS Landsat 8 Level 2')
	facts = dict(report.item_facts('time_series', {'region': REGION, 'variable': 'NDVI', 'sensor': 'Landsat',
	                                               'start': '2016-01-01', 'end': '2020-12-31'}, out))
	assert facts['Data source'] == out['data_source'] and 'Warnings' not in facts


def test_the_facts_of_a_result_with_warnings():
	result = {'data_source': S2, 'warnings': ['The images of X start on 2017-03-28: ...']}
	facts = dict(report.item_facts('time_series', {'region': REGION, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
	                                               'start': '2016-01-01', 'end': '2026-12-31'}, result))
	assert facts['Data source'] == S2
	assert facts['Warnings'] == 'The images of X start on 2017-03-28: ...'


def test_the_chart_says_where_its_values_come_from():
	pytest.importorskip('matplotlib')
	from matplotlib.figure import Figure
	fig = Figure(figsize=(10, 4.5))
	bottom = charts._with_source(fig, S2)
	assert 0 < bottom < 0.3 and [t.get_text() for t in fig.texts] == [f'Data: {S2}']
	assert charts._with_source(Figure(), None) == 0
	assert charts.source_line(S2) == f'Data: {S2}' and charts.source_line(None) is None
	rows = [{'region': 'park', 'date': '2018-01-01', 'value': 0.4}, {'region': 'park', 'date': '2018-02-01', 'value': 0.5}]
	assert charts.time_series_png(rows, source=S2) != charts.time_series_png(rows)


def test_describe_variable_gives_the_dates_of_the_data():
	d = services.describe_variable('NDVI', 'Sentinel-2')
	assert d['data_dates'] == {'start': '2017-03-28', 'end': None} and d['data_source'] == S2
	assert d['data_dates_checked'] == coverage.checked()
	assert services.describe_variable('ELEVATION', 'Copernicus')['data_dates'] is None


def test_the_mcp_server_and_the_assistant_pass_them_on():
	summary = {'title': 'x'}
	mcp_server._notes(summary, {'data_source': S2, 'warnings': ['w'], 'rows': []})
	assert summary == {'title': 'x', 'data_source': S2, 'warnings': ['w']}
	mcp_server._notes(summary := {}, {'data_source': None})
	assert summary == {}
	assert 'data_source' in mcp_server.INSTRUCTIONS and 'warnings' in mcp_server.INSTRUCTIONS
	assert assistant.data_warnings({'warnings': ['a', '', 'b']}) == ['a', 'b']
	assert assistant.data_warnings({'warnings': 'a'}) == [] and assistant.data_warnings(None) == []
	assert 'tell the user' in assistant.warnings_text(['a']) and assistant.warnings_text([]) == ''


def test_the_command_line_shows_them_as_warnings(capsys):
	from monitoreo import cli
	shown = warnings.showwarning
	try:
		cli._data_warnings()
		with warnings.catch_warnings():
			warnings.simplefilter('always')
			warnings.showwarning = warnings.showwarning  # catch_warnings keeps the one of cli
			services.make_spec('NDVI', 'Sentinel-2', '2016-06-01', '2026-12-31')
	finally:
		warnings.showwarning = shown
	assert 'WARNING: The images of COPERNICUS/S2_SR_HARMONIZED' in capsys.readouterr().err


# The Earth Engine app (gee/core.js), in Node: the same checks and texts as the package --------------------------------

NODE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
function nothing() { return new Proxy(function () {}, {get: function () { return nothing(); }, apply: nothing}); }
global.ee = nothing();
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[process.argv.length - 1], f), 'utf8'), {filename: f});
});
var mo = MonitorEO;
var out = {checks: input.cases.map(function (c) {
	try {
		return {value: mo.checkPeriod({ref: c.ref, period: c.period, season: c.season}, input.today)};
	} catch (e) {
		return {error: e.message};
	}
}), sources: input.cases.map(function (c) { return mo.dataSource(mo.byRef(c.ref), [c.period]); }),
	titles: input.titles.map(mo.shortTitle), joined: input.joined.map(mo.joinTitles)};
mo.resetNotes();
mo.used({ref: input.cases[0].ref, period: input.cases[0].period});
out.source = mo.sourceText();
try {
	mo.spec({ref: input.cases[0].ref, period: input.cases[0].period, metric: 'mean'});
} catch (e) {
	out.specError = e.message;
}
out.notes = mo.notes().warnings;
process.stdout.write(JSON.stringify(out));
"""

CASES = [  # variable, sensor, start, end, season
	('NDVI', 'Sentinel-2', '2016-01-01', '2026-12-31', None), ('NDVI', 'Sentinel-2', '2015-01-01', '2016-12-31', None),
	('NDVI', 'Sentinel-2', '2017-03-01', '2017-12-31', None), ('NDVI', 'Sentinel-2', '2027-01-01', '2027-12-31', None),
	('NDVI', 'Sentinel-2', '2016-01-01', '2020-12-31', ['06-01', '08-31']),
	('NDVI', 'Landsat', '2012-06-01', '2013-02-28', None), ('NDVI', 'Landsat', '1980-01-01', '1990-12-31', None),
	('NDVI', 'Landsat', '2016-01-01', '2026-12-31', None),
	('PRECIP', 'TerraClimate', '2020-01-01', '2024-12-31', None),
	('PRECIP', 'TerraClimate', '2020-01-01', '2025-03-31', None),
	('PRECIP', 'TerraClimate', '2025-01-01', '2025-12-31', None),
	('ET', 'Modis', '2016-01-01', '2022-12-31', None), ('NDWI', 'Modis', '2022-01-01', '2024-12-31', None),
	('Chl-a', 'Modis', '2024-01-01', '2026-10-31', None), ('ELEVATION', 'Copernicus', '2020-01-01', '2020-12-31', None)]


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_app_checks_and_names_the_data_as_the_package():
	cases = [{'ref': catalog.find(i, s)['ref'], 'period': [a, b], 'season': season} for i, s, a, b, season in CASES]
	titles = ['Harmonized Sentinel-2 MSI: MultiSpectral Instrument, Level-2A (SR)', 'TerraClimate: Monthly Climate and '
	          'Climatic Water Balance for Global Terrestrial Surfaces, University of Idaho', 'A: b', '  ']
	joined = [[f'USGS Landsat {n} Level 2, Collection 2, Tier 1' for n in (8, 9)], ['A b', 'C d'], ['x'], []]
	data = {'cases': cases, 'today': TODAY.isoformat(), 'titles': titles, 'joined': joined}
	run = subprocess.run(['node', '-e', NODE, GEE], input=json.dumps(data), capture_output=True, text=True, timeout=60)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	for case, (i, s, a, b, season), js, source in zip(cases, CASES, out['checks'], out['sources']):
		try:
			expected = {'value': _check(i, s, a, b, season)}
		except ValueError as e:
			expected = {'error': str(e)}
		assert js == expected, (i, s, a, b)
		assert source == coverage.of_entry(catalog.find(i, s), [(a, b)])['text']
	assert out['titles'] == [coverage.short_title(t) for t in titles]
	assert out['joined'] == [coverage.join_titles(t) for t in joined]
	assert out['source'] == S2
	assert out['notes'] == [f'The images of {S2} start on 2017-03-28: the period asked for begins on 2016-01-01, so its '
	                        'first 15 months have no data.']  # mo.spec checks the period, and notes its warnings


def test_the_app_has_the_dates_of_the_package():
	with open(os.path.join(GEE, 'catalog.js'), encoding='utf-8') as f:
		text = f.read()
	assert json.loads(text[text.index('{'):text.rstrip().rindex('}') + 1])['coverage'] == \
		json.loads(json.dumps(coverage.app_index())), 'run gee/build.py --indexes-only: the app has other dates'
