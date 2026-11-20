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

from monitoreo import assistant, catalog, charts, coverage, mcp_server, recipe, report, services, timeseries
from monitoreo.steps import map_steps

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


def _check_asset(asset, start, end, today=TODAY):
	"""The warnings of coverage.check for the data of Earth Engine ASSET (by its ID) over START to END."""
	with warnings.catch_warnings():
		warnings.simplefilter('ignore', coverage.DataDatesWarning)
		return coverage.check({'collection': asset, 'period': [start, end]}, None, today)


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
	# after the last image of data that ended in the copy of the index: a warning (Earth Engine may have added images)
	assert _check('PRECIP', 'TerraClimate', '2025-01-01', '2025-12-31') == [
		'The images of IDAHO_EPSCOR/TERRACLIMATE (TerraClimate) end on 2024-12-01 (in the copy of the Earth Engine data '
		f'catalog of {coverage.checked()}): the period asked for, 2025-01-01 to 2025-12-31, begins after them, so it may '
		'have no data, unless Earth Engine has added images since.']
	# between the last image of Landsat 5 and the first of Landsat 8 (Landsat 7 only until 2003-05-31)
	with pytest.raises(ValueError, match='have none from 2012-05-06 to 2013-03-17: the period asked for, 2012-06-01 '
	                                     'to 2013-02-28, has no data'):
		_check('NDVI', 'Landsat', '2012-06-01', '2013-02-28')
	with pytest.raises(ValueError, match=r'begins after today \(2026-11-17\): there are no images of COPERNICUS/S2'):
		_check('NDVI', 'Sentinel-2', '2027-01-01', '2027-12-31')


def test_a_period_after_today_is_refused_whatever_the_data(ended):
	# also for data that ended in the copy of the index (the warning would say Earth Engine may have added images)
	for index, sensor in (('PRECIP', 'TerraClimate'), ('NDWI', 'Modis'), ('Chl-a', 'Modis')):
		with pytest.raises(ValueError, match=r'^The period asked for, 2027-01-01 to 2027-12-31, begins after today '
		                                     r'\(2026-11-17\): there are no images of '):
			_check(index, sensor, '2027-01-01', '2027-12-31')
	assert 'begins after today' in coverage.refused({'period': ['2027-01-01', '2027-12-31']},
	                                                catalog.find('NDWI', 'Modis'), TODAY)
	assert coverage.refused({'period': ['2024-01-01', '2024-12-31']}, catalog.find('NDWI', 'Modis'), TODAY) is None
	with pytest.raises(ValueError, match='begins after today'):
		_check_asset('ESA/WorldCover/v200', '2027-01-01', '2027-12-31')


def test_the_data_by_id_end_on_the_day_before_the_end_of_their_extent():
	# ESA/WorldCover/v200 has an image, of 2021, and its extent ends on 2022-01-01: 2022 has no image at all
	assert _check_asset('ESA/WorldCover/v200', '2021-01-01', '2021-12-31') == []
	assert _check_asset('ESA/WorldCover/v200', '2022-01-01', '2022-12-31') == [
		'The images of ESA/WorldCover/v200 (ESA WorldCover 10m v200) end on 2021-12-31 (in the copy of the Earth Engine '
		f'data catalog of {coverage.checked()}): the period asked for, 2022-01-01 to 2022-12-31, begins after them, so '
		'it may have no data, unless Earth Engine has added images since.']
	assert coverage._last_image({'start': '2021-01-01', 'end': '2021-01-01'}) == '2021-01-01'  # not before the first
	assert coverage._last_image({'start': '2015-06-27', 'end': None}) is None


def test_the_warnings_of_a_condition_of_where_name_it():
	# the condition on the NDVI of Sentinel-2 begins before its first image, not the result (of Landsat)
	condition = {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'min': 0.3}
	text = (f'where, the condition on NDVI (Sentinel-2): The images of {S2} start on 2017-03-28: the period asked for '
	        'begins on 2016-01-01, so its first 15 months have no data.')
	with coverage.collect() as notes:
		with pytest.warns(coverage.DataDatesWarning, match=r'^where, the condition on NDVI \(Sentinel-2\): The images'):
			services.make_spec('NDVI', 'Landsat', '2016-01-01', '2020-12-31', where=[condition])
	assert notes.warnings == [text]
	# what was made, with those warnings (R: mo_image), with the period of the condition
	with warnings.catch_warnings():
		warnings.simplefilter('ignore', coverage.DataDatesWarning)
		spec, warned = coverage.noted(services.make_spec, 'NDVI', 'Landsat', '2018-01-01', '2020-12-31',
		                              where=[dict(condition, period=['2016-06-01', '2018-12-31'])])
	assert spec['index'] == 'NDVI' and warned == [
		f'where, the condition on NDVI (Sentinel-2): The images of {S2} start on 2017-03-28: the period asked for begins '
		'on 2016-06-01, so its first 10 months have no data.']
	assert coverage.noted(lambda: 1) == (1, [])


def test_the_maps_of_the_steps_are_those_with_images():
	# Play in the assistant and the maps of a result in QGIS: no step before the first image, or after today
	s2 = {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2016-01-01', 'end': '2099-12-31'}
	years = [s['label'] for s in map_steps('time_series', dict(s2, step='annual'))]
	assert years == [str(y) for y in range(2017, dt.date.today().year + 1)]
	months = map_steps('time_series', dict(s2, step='monthly'))
	assert months[0]['label'] == 'Mar 2017' and months[-1]['start'] <= dt.date.today().isoformat()
	# Landsat: none between Landsat 5 and Landsat 8
	gap = [s['label'] for s in map_steps('map_layer', {'variable': 'NDVI', 'sensor': 'Landsat', 'start': '2012-01-01',
	                                                    'end': '2013-12-31', 'temporal': 'monthly'})]
	assert 'May 2012' in gap and 'Jun 2012' not in gap and 'Feb 2013' not in gap and 'Mar 2013' in gap
	# the data by their ID: the dates of their record; without known dates, every step
	ids = map_steps('map_layer', {'collection': 'ee.ImageCollection("ESA/WorldCover/v200")', 'band': 'Map',
	                              'start': '2019-01-01', 'end': '2023-12-31', 'temporal': 'annual'})
	assert [s['label'] for s in ids] == ['2021', '2022', '2023']
	assert len(map_steps('map_layer', {'start': '2016-01-01', 'end': '2020-12-31', 'temporal': 'annual'})) == 5
	assert map_steps('time_series', dict(s2, end='2017-12-31', step='annual')) == []  # one step left: no steps


def test_the_land_cover_maps_and_the_recipes_name_their_data():
	from monitoreo import classes
	for key, year, data in (('CORINE', 2018, 'COPERNICUS/CORINE/V20/100m/2018'),
	                        ('WorldCover', 2021, 'ESA/WorldCover/v200 (ESA WorldCover 10m v200)')):
		with coverage.collect() as notes:
			services._landcover_used(*classes.landcover_map(key, year))
		assert notes.source() == data
	# download_variables: the variables of its recipe (recipe.expand)
	with warnings.catch_warnings():
		warnings.simplefilter('ignore', coverage.DataDatesWarning)
		with coverage.collect() as notes:
			recipe.expand({'variables': [
				{'index': 'NDVI', 'sensor': 'Sentinel-2', 'period': ['2016-01-01', '2020-12-31'], 'metric': 'median'},
				{'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr', 'period': ['2020-01-01', '2020-12-31'],
				 'unit': 'mm', 'metric': 'sum'}]})
	assert notes.source() == f'{S2}; IDAHO_EPSCOR/TERRACLIMATE (TerraClimate)'
	assert 'first 15 months' in notes.warnings[0]


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
	with pytest.raises(ValueError, match=r'^where, the condition on NDVI \(Sentinel-2\): The images of '
	                                     'COPERNICUS/S2_SR_HARMONIZED'):
		services.make_spec('NDVI', 'Modis', '2001-01-01', '2001-12-31',
		                   where=[{'variable': 'NDVI', 'sensor': 'Sentinel-2', 'min': 0.2}])
	with pytest.warns(coverage.DataDatesWarning, match=r'TERRACLIMATE \(TerraClimate\) end on 2024-12-01'):
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


def test_the_assistant_shows_the_warnings_of_the_exports(monkeypatch):
	import asyncio
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)
	text = f'The images of {S2} start on 2017-03-28: the period asked for begins on 2016-01-01, so its first 15 ...'

	class Exports(assistant.Assistant):
		async def call(self, name, args):
			return None, [json.dumps({'operation': 'op', 'file': 'ndvi.tif', 'folder': 'MonitorEO',
			                          'warnings': [text], 'data_source': S2})], []

	a = Exports({**assistant.DEFAULTS, 'project': 'p'})
	a.tools = assistant.model_tools([{'name': 'export_image_to_drive', 'description': '', 'inputSchema': {
		'type': 'object', 'properties': {'region': {'type': 'object'}, 'variable': {'type': 'string'},
		                                 'sensor': {'type': 'string'}, 'start': {'type': 'string'},
		                                 'end': {'type': 'string'}}}}])

	async def run():
		return [e async for e in a.run_tool({'name': 'export_image_to_drive', 'arguments': {
			'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
			'start': '2016-01-01', 'end': '2020-12-31'}})]

	events = asyncio.run(run())
	assert {'type': 'data_warning', 'text': text} in events
	assert 'Export to Google Drive running' in next(e['text'] for e in events if e['type'] == 'notice')
	assert 'tell the user' in a.messages[-1]['content'] and text in a.messages[-1]['content']


def test_the_help_says_what_is_refused():
	from monitoreo import cli
	assert 'begins after today' in ' '.join(cli.__doc__.split()) and 'falls between Landsat 5 and Landsat 8' in \
		' '.join(cli.__doc__.split())
	instructions = ' '.join(mcp_server.INSTRUCTIONS.split())
	assert 'begins after today is an error' in instructions and 'where, the condition on' in instructions
	assert 'A period without images of the data is an error' not in instructions


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
// the warnings of a condition of where, named as its errors
mo.resetNotes();
mo.whereSpecs({where: [{ref: input.cases[0].ref, min: 0.3}], period: input.condition, season: null});
out.condition = mo.notes().warnings;
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
	('PRECIP', 'TerraClimate', '2027-01-01', '2027-12-31', None), ('NDWI', 'Modis', '2027-01-01', '2027-12-31', None),
	('ET', 'Modis', '2016-01-01', '2022-12-31', None), ('NDWI', 'Modis', '2022-01-01', '2024-12-31', None),
	('Chl-a', 'Modis', '2024-01-01', '2026-10-31', None), ('ELEVATION', 'Copernicus', '2020-01-01', '2020-12-31', None)]


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_app_checks_and_names_the_data_as_the_package():
	cases = [{'ref': catalog.find(i, s)['ref'], 'period': [a, b], 'season': season} for i, s, a, b, season in CASES]
	titles = ['Harmonized Sentinel-2 MSI: MultiSpectral Instrument, Level-2A (SR)', 'TerraClimate: Monthly Climate and '
	          'Climatic Water Balance for Global Terrestrial Surfaces, University of Idaho', 'A: b', '  ']
	joined = [[f'USGS Landsat {n} Level 2, Collection 2, Tier 1' for n in (8, 9)], ['A b', 'C d'], ['x'], []]
	data = {'cases': cases, 'today': TODAY.isoformat(), 'titles': titles, 'joined': joined,
	        'condition': ['2016-01-01', '2020-12-31']}
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
	assert out['condition'] == ['where, the condition on NDVI (Sentinel-2): ' + out['notes'][0]]


def test_the_app_has_the_dates_of_the_package():
	with open(os.path.join(GEE, 'catalog.js'), encoding='utf-8') as f:
		text = f.read()
	assert json.loads(text[text.index('{'):text.rstrip().rindex('}') + 1])['coverage'] == \
		json.loads(json.dumps(coverage.app_index())), 'run gee/build.py --indexes-only: the app has other dates'


# The panel of the app (gee/ui.js, with the ui and ee of tests/test_themes.py, which compute nothing), as a user drives
# it: «No data in that period» with the warning that explains it, the line «Data: ...» with the elevation of a profile
# and the zones of the statistics of each band, and the notes of a computation that answers after a click that failed
APP = r"""
var out = {};
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
var period = ['2025-01-01', '2025-12-31'];
function setPeriod(a, b) {  // the first and last day, in their boxes
	[a, b].forEach(function (v, i) {
		var box = textbox(function (w) { return w.opts.value === period[i]; });
		box.opts.onChange(v);
		box.opts.value = v;
	});
	period = [a, b];
}
// the NDWI of MODIS, whose images end on 2023-02-17 (in the copy of the index): no data in 2024
selectWith('vegetation').opts.onChange('water');
selectWith(input.ndwi).opts.onChange(input.ndwi);
setPeriod('2024-01-01', '2024-12-31');
answer = {features: []};
button('Compute the time series').opts.onClick();
out.noData = last().texts;
// the NDVI of Sentinel-2: the statistics of each band of elevation, and the profile of a line, with the elevation
selectWith('water').opts.onChange('vegetation');
selectWith(input.ndvi).opts.onChange(input.ndvi);
answer = {features: [{properties: {name: 'Map view', groups: [{zone: 1, p25: 1, p50: 2, p75: 3, mean: 2, count: 4}]}}]};
button('Statistics of each band').opts.onClick();
out.zones = last().texts;
answer = {length: 21379.1, centroid: [-3.5, 37.1], features: []};
button('Draw a line and its profile').opts.onClick();
drawn(object());
out.profile = last().texts;
// a map from 2016 whose range comes after a click that fails (a wrong date): it keeps its own warning
setPeriod('2016-01-01', '2021-12-31');
var held = [], percentiles = MonitorEO.percentiles;
MonitorEO.percentiles = function () { return {evaluate: function (f) { held.push(f); }}; };
button('Add to the map').opts.onClick();
setPeriod('2016-1-01', '2021-12-31');
button('Add to the map').opts.onClick();
out.failed = last().texts;
MonitorEO.percentiles = percentiles;
held[0]({value_p5: 0, value_p95: 1});
out.held = last().texts;
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_panel_of_the_app_keeps_the_notes_of_each_computation():
	from test_themes import PANEL, _build
	head = PANEL[:PANEL.index('var out = {};')]
	script = head.replace('onDraw: nothing', 'onDraw: function (f) { drawn = f; }').replace(
		'var map = new Widget', 'var drawn; var map = new Widget') + APP
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {},
	        'ndwi': catalog.find('NDWI', 'Modis')['ref'], 'ndvi': catalog.find('NDVI', 'Sentinel-2')['ref']}
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	ndwi = coverage.of_entry(catalog.find('NDWI', 'Modis'))['text']
	assert out['noData'] == [
		f'⚠ The images of {ndwi} end on 2023-02-17 (in the copy of the Earth Engine data catalog of '
		f'{coverage.checked()}): the period asked for, 2024-01-01 to 2024-12-31, begins after them, so it may have no '
		'data, unless Earth Engine has added images since.', 'No data in that period.',
		'What it is (manual): NDWI: Normalized Difference Water Index', f'Data: {ndwi}']  # what NDWI is: the wiki
	dem = coverage.of_entry(catalog.find('ELEVATION', 'Copernicus'))['text']
	assert out['zones'][-1] == out['profile'][-1] == f'Data: {S2}; {dem}'  # as services.region_stats and transect
	assert out['failed'] == ['Not a valid date: "2016-1-01". Use YYYY-MM-DD (and MM-DD for the season).']
	assert out['held'][0] == (f'⚠ The images of {S2} start on 2017-03-28: the period asked for begins on 2016-01-01, so '
	                          'its first 15 months have no data.') and out['held'][-1] == f'Data: {S2}'


# The blocks of a series of the app fetched after a newer computation began note in the notes of their own
SERIES = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
var queue = [];  // the answers of evaluate, given when the test says
function nothing() {
	return new Proxy(function () {}, {get: function (t, p) {
		return p === 'evaluate' ? function (f) { queue.push(f); } : nothing();
	}, apply: nothing});
}
global.ee = nothing();
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[process.argv.length - 1], f), 'utf8'), {filename: f});
});
var mo = MonitorEO, out = {};
mo.resetNotes();
var own = mo.notes();
var s = mo.spec({ref: input.landsat, period: ['2016-01-01', '2020-12-31'], metric: 'mean',
	where: [{ref: input.s2, min: 0.3}]});
var steps = [];
for (var i = 0; i < 130; i++) steps.push(['2016-01-01', '2016-01-17']);  // two blocks
mo.series(s, nothing(), 1, 'mean', 'mean', 30, 'EPSG:4326', steps, function () {}, null);
out.first = own.warnings.slice();
own.warnings.length = 0;
mo.resetNotes();  // a newer computation
var newer = mo.notes();
queue[0]({features: []});  // the first block answers: the second is fetched now
out.own = own.warnings;
out.newer = newer.warnings;
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_blocks_of_a_series_of_the_app_note_in_their_own_computation():
	data = {'landsat': catalog.find('NDVI', 'Landsat')['ref'], 's2': catalog.find('NDVI', 'Sentinel-2')['ref']}
	run = subprocess.run(['node', '-e', SERIES, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=60)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	text = (f'where, the condition on NDVI (Sentinel-2): The images of {S2} start on 2017-03-28: the period asked for '
	        'begins on 2016-01-01, so its first 15 months have no data.')
	assert out == {'first': [text], 'own': [text], 'newer': []}


def test_the_evapotranspiration_from_its_gap_filled_version():
	"""ET and LE of MODIS (sensors.GAP_FILLED): MOD16A2GF.061 from 2000 to the date of catalog.json, then MOD16A2.061
	(which begins in 2021): no period of them since 2000 is refused, and their data name each dataset in its period."""
	e = catalog.find('ET', 'Modis')
	end = catalog.load()['collections']['MODIS/061/MOD16A2GF']['end']
	assert coverage.parts(e)[0] == ('MODIS/061/MOD16A2GF', '2000-01-01', end)
	assert coverage.parts(e)[1][0] == 'MODIS/061/MOD16A2' and coverage.dates(e) == {'start': '2000-01-01', 'end': None}
	assert _check('ET', 'Modis', '2005-01-01', '2010-12-31') == []
	assert coverage.of_entry(e, [('2005-01-01', '2010-12-31')])['collections'] == ['MODIS/061/MOD16A2GF']
	assert coverage.of_entry(e, [('2024-01-01', '2026-06-30')])['collections'] == ['MODIS/061/MOD16A2GF',
	                                                                              'MODIS/061/MOD16A2']

