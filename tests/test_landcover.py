"""Land cover masks (a condition of where that leaves out some land covers after a land cover map of a year), without
Earth Engine: the table of correspondences of the maps, the conditions, their text in the READMEs and reports, their
references, the tools that list the maps and the same answers in the Earth Engine app (gee/core.js)."""

import contextlib
import datetime as dt
import inspect
import io
import json
import os
import shutil
import subprocess

import pytest

from monitoreo import catalog, cli, landcover, references, report, services, variable

GEE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gee')
NO_WATER = {'landcover': 'CORINE', 'year': 2018, 'exclude': ['water', 'built']}
ABOVE = {'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 1500}


def spec(*where):
	return services.make_spec('NDVI', 'Sentinel-2', '2020-01-01', '2021-12-31', where=list(where))


# The table of correspondences -------------------------------------------------------------------------------------

def test_every_class_of_every_map_is_a_broad_land_cover():
	keys = {c['key'] for c in landcover.classes()}
	assert keys == {'water', 'trees', 'grassland', 'wetland', 'cropland', 'shrubland', 'built', 'bare', 'snow'}
	for c in landcover.classes():
		assert c['en'] and c['es'] and c['help'] and c['help_es'], c['key']
	for m in landcover.maps():
		assert set(m['classes']) == set(m['names']), m['key']  # every class of the map has its name and land cover
		assert set(m['classes'].values()) <= keys, m['key']
		assert set(m['classes'].values()) == keys, m['key']  # every broad land cover is in every map
		assert all(code.isdigit() for code in m['classes']), m['key']
		assert m['band'] and float(m['m']) > 0 and m['coverage'] and m['how'], m['key']
		assert m.get('years') or m.get('first_year'), m['key']


def test_the_classes_of_each_map():
	corine = landcover.find('CORINE')
	assert len(corine['classes']) == 44
	assert {c for c, k in corine['classes'].items() if k == 'water'} == {'511', '512', '521', '522', '523'}
	assert {c for c, k in corine['classes'].items() if k == 'built'} == {
		'111', '112', '121', '122', '123', '124', '131', '132', '133', '141', '142'}  # the artificial surfaces
	assert landcover.codes(corine, ['wetland']) == [411, 412, 421, 422, 423]
	dw = landcover.find('Dynamic World')
	assert dw['classes'] == {'0': 'water', '1': 'trees', '2': 'grassland', '3': 'wetland', '4': 'cropland',
	                         '5': 'shrubland', '6': 'built', '7': 'bare', '8': 'snow'}
	wc = landcover.find('worldcover')
	assert landcover.codes(wc, ['water', 'built']) == [50, 80]
	assert landcover.codes(wc, ['wetland']) == [90, 95]  # herbaceous wetland and mangroves (Venter et al. 2022)
	assert landcover.codes(wc, ['bare']) == [60, 100]  # bare / sparse vegetation and moss and lichen
	assert corine['classes']['324'] == 'trees' and corine['classes']['244'] == 'cropland'  # as MAES
	modis = landcover.find('MODIS')
	assert len(modis['classes']) == 17 and landcover.codes(modis, ['trees']) == [1, 2, 3, 4, 5, 8]


def test_the_datasets_of_the_maps_are_cited():
	known, bib = catalog.load()['datasets'], references.bibliography()
	for m in landcover.maps():
		for d in landcover.all_datasets(m):
			assert known.get(d, {}).get('references'), d
			assert all(r in bib and (bib[r].get('doi') or bib[r].get('url')) for r in known[d]['references']), d
		assert all(r in bib for r in m['crosswalk_references']), m['key']
		assert m['crosswalk'], m['key']
	assert len(landcover.all_datasets(landcover.find('CORINE'))) == 5  # an image (and a DOI) per year
	assert bib['venter2022']['doi'] == '10.3390/rs14164101'
	assert landcover.find('WorldCover')['crosswalk_references'] == ['venter2022']
	assert landcover.find('CORINE')['crosswalk_references'] == ['bise2023']


def test_years():
	today = dt.date(2026, 11, 13)
	dw = landcover.find('DynamicWorld')
	assert landcover.years(dw, today)[0] == 2016 and landcover.years(dw, today)[-1] == 2026
	assert landcover.years(landcover.find('MODIS')) == list(range(2001, 2026))
	assert landcover.default_year(dw, today) == 2025  # the last whole year
	assert landcover.years(landcover.find('WorldCover')) == [2020, 2021]
	assert landcover.default_year(landcover.find('CORINE')) == 2018


# The conditions ---------------------------------------------------------------------------------------------------

def test_a_condition_checked():
	m, year, exclude = landcover.check(NO_WATER)
	assert (m['key'], year, exclude) == ('CORINE', 2018, ['water', 'built'])
	m, year, exclude = landcover.check({'landcover': 'worldcover', 'exclude': 'WATER'})  # its last year, one land cover
	assert (m['key'], year, exclude) == ('WorldCover', 2021, ['water'])


@pytest.mark.parametrize('condition, message', [
	({'landcover': 'SIOSE', 'exclude': ['water']}, 'unknown land cover map'),
	({'landcover': 'CORINE', 'year': 2019, 'exclude': ['water']}, 'has no map of 2019'),
	({'landcover': 'CORINE', 'year': 'last', 'exclude': ['water']}, 'is a number'),
	({'landcover': 'CORINE', 'year': 2018}, 'needs exclude'),
	({'landcover': 'CORINE', 'year': 2018, 'exclude': ['urban']}, "unknown land cover 'urban'"),
	({'landcover': 'CORINE', 'year': 2018, 'exclude': ['water'], 'min': 1}, 'unknown keys min'),
])
def test_wrong_conditions(condition, message):
	with pytest.raises(ValueError, match=message):
		landcover.check(condition)
	with pytest.raises(ValueError, match=message):  # also before Earth Engine, in every tool (services.make_spec)
		spec(condition)


def test_with_the_conditions_on_variables():
	s = spec(ABOVE, NO_WATER)
	assert [cs['index'] for cs, _, _ in variable.where_specs(s)] == ['ELEVATION']  # the variables only
	assert variable.landcover_conditions(s) == [NO_WATER]
	# a fixed layer (no period) can be masked too, and so can the data of Earth Engine by their ID
	assert variable.landcover_conditions(services.make_spec('ELEVATION', 'Copernicus', where=[NO_WATER]))
	assert variable.landcover_conditions(services.make_spec(image='USGS/SRTMGL1_003', band='elevation',
	                                                        where=NO_WATER))


def test_the_same_pixels_in_every_period():
	"""The map of a year has no period: the other period of a comparison and the steps of a series keep it."""
	pinned = variable.pin_where([ABOVE, NO_WATER, dict(ABOVE, variable='NDVI', sensor='Modis')], '2020-01-01',
	                            '2020-12-31')
	assert pinned[1] == NO_WATER and 'period' not in pinned[1]
	assert pinned[2]['period'] == ['2020-01-01', '2020-12-31']
	assert services.same_area({'where': [NO_WATER]}, '2020-01-01', '2020-12-31')['where'] == [NO_WATER]


def test_text_and_facts():
	assert landcover.text(NO_WATER) == 'the land cover is not water or built-up (CORINE Land Cover 2018)'
	assert landcover.text(NO_WATER, 'es') == 'el uso del suelo no es agua ni urbano y artificial (CORINE Land Cover 2018)'
	text = report.where_text([ABOVE, NO_WATER])
	assert text.startswith('ELEVATION (Copernicus) ≥ 1,500 m') and text.endswith('; the land cover is not water or '
	                                                                             'built-up (CORINE Land Cover 2018)')
	facts = dict(report.item_facts('map_layer', {'region': {'bbox': [-3.6, 36.8, -3.5, 36.9]}, 'variable': 'NDVI',
	                                             'sensor': 'Sentinel-2', 'start': '2020-01-01', 'end': '2020-12-31',
	                                             'where': [NO_WATER]}))
	assert facts['Pixels of the region'] == 'only where the land cover is not water or built-up (CORINE Land Cover 2018)'


def test_references_of_the_land_cover_map():
	def ids(where):
		return [r['id'] for r in references.cite('map_layer', {'variable': 'NDVI', 'sensor': 'Sentinel-2',
		                                                        'start': '2020-01-01', 'end': '2020-12-31',
		                                                        'where': where})['references']]
	corine = ids([NO_WATER])
	assert 'clc2018' in corine and 'bise2023' in corine and 'clc2012' not in corine  # the map of the year only
	wc2020 = ids([{'landcover': 'WorldCover', 'year': 2020, 'exclude': ['water']}])
	assert 'zanaga2021' in wc2020 and 'venter2022' in wc2020
	assert 'zanaga2022' not in wc2020  # the map of 2021 (v200) is not that of 2020 (v100)
	assert 'brown2022' in ids([{'landcover': 'DynamicWorld', 'year': 2020, 'exclude': ['built']}])
	assert 'friedl2022' in ids([{'landcover': 'MODIS', 'year': 2020, 'exclude': ['built']}])
	credits = references.cite('map_layer', {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2020-01-01',
	                                        'end': '2020-12-31', 'where': [NO_WATER]})['credits']
	assert catalog.load()['datasets']['COPERNICUS/CORINE/V20/100m/2018']['credit'] in credits
	assert 'Copernicus Land Monitoring Service' in ' '.join(credits)


# The tools ------------------------------------------------------------------------------------------------------

def test_landcover_maps():
	d = services.landcover_maps()
	assert [m['key'] for m in d['maps']] == ['WorldCover', 'DynamicWorld', 'CORINE', 'MODIS']
	corine = d['maps'][2]
	assert corine['years'] == [1990, 2000, 2006, 2012, 2018] and corine['default_year'] == 2018
	assert corine['classes']['water'][0] == '511 Water courses'
	assert d['maps'][1]['years'].startswith('2016-')
	assert 'half' in d['rule']
	ids = [r['id'] for r in d['references']]
	assert {'venter2022', 'bise2023', 'brown2022', 'friedl2022', 'zanaga2021', 'zanaga2022', 'clc1990'} <= set(ids)
	assert len(ids) == len(set(ids)) and d['credits']
	assert all(m['crosswalk'] for m in d['maps'])
	assert services.landcover_maps('es')['classes'][0]['name'] == 'Agua'


def test_every_tool_explains_it():
	from monitoreo import assistant, mcp_server
	assert 'landcover' in mcp_server.WHERE_DOC and 'landcover_maps' in mcp_server.WHERE_DOC
	assert '"landcover": "CORINE"' in mcp_server.INSTRUCTIONS
	assert '"landcover": "CORINE"' in mcp_server.map_layer.__doc__  # every tool with where (tests/test_where.py)
	assert json.loads(mcp_server.landcover_maps('en'))['maps'][0]['key'] == 'WorldCover'
	assert 'landcover_maps' in assistant.ADVICE and 'landcover_maps' in mcp_server.NO_EECU_WARNING
	assert 'landcover' in assistant.PROMPT and 'landcover_maps' in assistant.LABELS
	assert 'landcover' in cli.WHERE_HELP
	assert 'landcover' in inspect.getsource(services.make_spec)


def test_command_line():
	out = io.StringIO()
	with contextlib.redirect_stdout(out):
		cli.main(['landcover'])
	text = out.getvalue()
	assert 'CORINE' in text and 'DynamicWorld' in text and 'built' in text
	out = io.StringIO()
	with contextlib.redirect_stdout(out):
		cli.main(['landcover', '--map', 'corine'])
	assert '511 Water courses' in out.getvalue()
	with pytest.raises(SystemExit, match='unknown land cover map'):
		cli.main(['landcover', '--map', 'SIOSE'])


# The Earth Engine app -------------------------------------------------------------------------------------------

@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_same_in_the_app():
	"""gee/core.js with the table of catalog.js gives the same checks, classes, years and texts as this package."""
	conditions = [NO_WATER, {'landcover': 'worldcover', 'exclude': ['water']},
	              {'landcover': 'Dynamic World', 'year': 2020, 'exclude': ['built', 'snow']},
	              {'landcover': 'MODIS', 'year': 2010, 'exclude': ['cropland', 'trees']}]
	script = """
	var fs = require('fs'), vm = require('vm'), path = require('path');
	global.ee = {};
	['catalog.js', 'core.js'].forEach(function (f) {
		vm.runInThisContext(fs.readFileSync(path.join(%r, f), 'utf8'), {filename: f});
	});
	var mo = global.MonitorEO, cases = %s;
	var out = cases.map(function (c) {
		var x = mo.landcoverCheck(c);
		return {map: x[0].key, year: x[1], exclude: x[2], codes: mo.landcoverCodes(x[0], x[2]),
			years: mo.landcoverYears(x[0]), text: mo.landcoverText(c, 'en'), es: mo.landcoverText(c, 'es')};
	});
	var errors = [{landcover: 'CORINE', year: 2019, exclude: ['water']}, {landcover: 'CORINE', exclude: []},
		{landcover: 'CORINE', exclude: ['urban']}].map(function (c) {
		try { mo.landcoverCheck(c); return null; } catch (e) { return e.message; }
	});
	var pinned = mo.pinWhere(cases.slice(0, 1).concat([{ref: 27, min: 0.3}]), '2020-01-01', '2020-12-31');
	console.log(JSON.stringify({out: out, errors: errors, pinned: pinned,
		maps: mo.landcoverMaps().length, classes: mo.landcoverClasses().length}));
	""" % (GEE, json.dumps(conditions))
	run = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=60)
	assert run.returncode == 0, run.stderr
	app = json.loads(run.stdout)
	for c, a in zip(conditions, app['out']):
		m, year, exclude = landcover.check(c)
		assert (a['map'], a['year'], a['exclude']) == (m['key'], year, exclude)
		assert a['codes'] == landcover.codes(m, exclude)
		assert a['years'] == landcover.years(m)
		assert (a['text'], a['es']) == (landcover.text(c), landcover.text(c, 'es'))
	assert all(app['errors'])
	assert 'period' not in app['pinned'][0] and app['pinned'][1]['period'] == ['2020-01-01', '2020-12-31']
	assert (app['maps'], app['classes']) == (len(landcover.maps()), len(landcover.classes()))


STEPS = r"""
var out = {};
var lc = 'Leave some land covers out of the results';
out.order = texts(controls);
out.before = {on: check(lc).opts.value, maps: Boolean(selectWith('CORINE'))};
check(lc).opts.onChange(true);
out.worldcover = {map: selectWith('CORINE').opts.value, year: selectWith(2021).opts.value,
	years: selectWith(2021).opts.items.map(function (i) { return i.value; })};
selectWith('CORINE').opts.onChange('CORINE');
out.corine = {year: selectWith(2018).opts.value, years: selectWith(2018).opts.items.map(function (i) { return i.value; }),
	checks: find(controls, 'Checkbox').map(function (w) { return [w.opts.label, w.opts.value]; })};
// a region (the view of the map) and the map of the NDVI without water and built-up areas
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
answer = {value_p5: 0.1, value_p95: 0.8};
button('Add to the map').opts.onClick();
out.map = {layer: layers[layers.length - 1], results: last()};
// without land covers: what to do
check('Water (511, 512, 521, 522, 523)').opts.onChange(false);
check('Built-up (111, 112, 121, 122, 123, 124, 131, 132, 133, 141, 142)').opts.onChange(false);
button('Add to the map').opts.onClick();
out.none = last();
check(lc).opts.onChange(false);
answer = {value_p5: 0.1, value_p95: 0.8};
button('Add to the map').opts.onClick();
out.off = layers[layers.length - 1];
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_panel_of_the_app():
	"""The land cover mask of the app (gee/ui.js) in Node, as a user drives it (the ui and ee of tests/test_themes.py,
	which compute nothing): before the theme, unfolded when checked, the years of each map, the classes of the map in
	each land cover, the title of the map with the land covers left out, and the error without land covers."""
	from test_themes import PANEL, _build
	script = PANEL[:PANEL.index('var out = {};')] + STEPS
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {}}
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	assert out['order'].index('Land cover mask') < out['order'].index('Theme')
	assert out['before'] == {'on': False, 'maps': False}  # folded
	assert out['worldcover'] == {'map': 'WorldCover', 'year': 2021, 'years': [2021, 2020]}
	assert out['corine']['year'] == 2018 and out['corine']['years'] == [2018, 2012, 2006, 2000, 1990]
	checks = dict(out['corine']['checks'])
	assert checks['Water (511, 512, 521, 522, 523)'] and checks['Cropland (211, 212, 213, 221, 222, 223, 241, 242, '
	                                                           '243, 244)'] is False
	assert 'the land cover is not water or built-up (CORINE Land Cover 2018)' in out['map']['layer']
	assert out['none']['texts'][-1].endswith('Land cover mask: check the land covers to leave out (or uncheck the '
	                                         'mask).')
	assert 'land cover' not in out['off']
