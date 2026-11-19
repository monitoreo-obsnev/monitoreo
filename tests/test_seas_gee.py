"""The oceans and seas (monitoreo.seas) and the pixels of 1 to 10 km of the large areas in the Earth Engine app, without
Earth Engine: gee/core.js writes the names as the table (seas.plain), finds the seas on the server by their property
search or their MRGID, builds the regions {"sea": ...} and {"sea_at": ...} with the calls of Earth Engine of
areas.region, chooses the pixel of a large area as areas.default_scale, warns of a variable of the land over a sea as
services.sea_warning and gives the credit and reference of Marine Regions as the package cites them; gee/ui.js offers
the mode Sea or ocean (IHO), in English and Spanish, takes the regions sea and sea_at of some parameters and computes
the regions of more than 100,000 km² only with data of 250 m or more. What the table answers can only be checked in
Earth Engine, once it is there."""

import json
import os
import re
import shutil
import subprocess

import pytest

from monitoreo import areas, catalog, references, seas, services

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEE = os.path.join(ROOT, 'gee')
ALBORAN, WESTERN = 3324, 4279

NAMES = ['Alboran Sea', 'Balearic (Iberian Sea)', 'Mediterranean Sea - Eastern Basin', 'Gulf of St. Lawrence',
         'MAR DE ALBORÁN', '  many   spaces\tand\nlines ', 'L’x', 'ß æ ø', 'ﬁ', '', ' ', '3324', 'Bay of Fundy',
         'Sea of Marmara', 'emoji 😀 sea', 'a/b-c', "Côte d'Ivoire"]
MEDITERRANEAN, MARMARA = 1905, 3369  # the whole Mediterranean Sea (seas.GROUPS) and a sea that is not part of it
VALUES = [ALBORAN, '3324', 3324.0, 'Alboran Sea', '  alborán SEA ', ['Alboran Sea', WESTERN], [], '', None,
          MEDITERRANEAN, '1905', ' Mediterranean SEA', ['mediterranean sea', ALBORAN, 1905, 'Alboran Sea']]
SPECS = [ALBORAN, [ALBORAN, WESTERN], '3324', MEDITERRANEAN, 'Mediterranean Sea', [MARMARA, MEDITERRANEAN]]
# (native, area in km², target): the pixels of the statistics (1e6) and of the areas by class (1e7)
SCALES = [(native, km2, target) for native in (10, 30, 250, 463, 500, 1000, 4616, 11132, 27830)
          for km2 in (0, 1, 5000, 54_482, 99_999, 100_000, 100_001, 120_000, 476_707, 3e6, 7.7e7)
          for target in (1e6, 1e7)]

NODE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
var log = [], TAG = '__ee__';
function arg(a) {
	if (a && (typeof a === 'object' || typeof a === 'function') && a[TAG]) return '<ee>';
	if (typeof a === 'function') return '<function>';
	if (Array.isArray(a)) return a.map(arg);
	return a === undefined ? null : a;
}
function object() {
	return new Proxy({}, {get: function (t, p) { return p === TAG ? true : typeof p === 'symbol' ? undefined : call(p); }});
}
function call(name) {
	return new Proxy(function () {
		var args = Array.prototype.slice.call(arguments);
		log.push([name].concat(args.map(arg)));
		if (name === 'map') args[0](object());
		return object();
	}, {get: function (t, p) { return p === TAG ? true : typeof p === 'symbol' ? undefined : call(name + '.' + p); }});
}
global.ee = new Proxy({}, {get: function (t, p) { return call(p); }});
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[1], f), 'utf8'), {filename: f});
});
var mo = global.MonitorEO;
function attempt(f) {
	try { return {value: f()}; } catch (e) { return {error: e.message}; }
}
function chain(f) { log = []; f(); return log.slice(); }
var out = {};
out.plain = input.names.map(mo.seaPlain);
out.codes = input.values.map(function (v) { return attempt(function () { return mo.seaCodes(v); }); });
out.regions = input.specs.map(function (v) { return chain(function () { mo.seaRegion(v); }); });
out.named = chain(function () { mo.seaRegion(['Alboran Sea', 4279]); });
out.at = chain(function () { mo.seaAt(-2.5, 36); });
out.find = chain(function () { mo.findSeas('  Alborán ', 30); });
out.findCode = chain(function () { mo.findSeas('3324'); });
out.findGroup = chain(function () { mo.findSeas('Mediterranean', 30); });
out.findGroupCode = chain(function () { mo.findSeas('1905'); });
out.scales = input.scales.map(function (s) { return mo.defaultScale(s[0], s[1] * 1e6, s[2]); });
out.auto = [mo.autoScale({m: 250}, 476707e6), mo.areaScale(30, 200000e6)];
out.large = [mo.isLarge(1e11), mo.isLarge(1e11 + 1), mo.isLarge(0), mo.LARGE_AREA_KM2, mo.LARGE_PIXEL];
out.isSea = [{sea: 1}, {sea_at: [0, 0]}, {bbox: [0, 0, 1, 1], within: {sea: 1}}, {country: 'ESP'}, null]
	.map(mo.isSea);
out.warnings = input.warnings.map(function (w) { return mo.seaWarning(w[0], w[1] === null ? null : mo.byRef(w[1])); });
out.credits = mo.adminCredits('sea');
out.constants = [mo.SEAS, mo.CITED_REGIONS, mo.SEA_GROUPS, mo.SEA_GROUP_MAX_ERROR];
process.stdout.write(JSON.stringify(out));
"""
WARNINGS = [({'sea': ALBORAN}, e['ref']) for e in catalog.variables()] + [
	({'country': 'ESP'}, catalog.find('NDVI', 'Modis')['ref']), ({'sea': 1}, None),
	({'bbox': [0, 0, 1, 1], 'within': {'sea_at': [0, 0]}}, catalog.find('LST', 'Modis')['ref'])]


def _read(*parts):
	with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
		return f.read()


@pytest.fixture(scope='module')
def app():
	if not shutil.which('node'):
		pytest.skip('no Node')
	data = {'names': NAMES + [r[1] for r in seas.load()['rows']], 'values': VALUES, 'specs': SPECS,
	        'scales': SCALES, 'warnings': WARNINGS}
	run = subprocess.run(['node', '-e', NODE, GEE], input=json.dumps(data), capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	return dict(json.loads(run.stdout), names=data['names'])


def test_the_app_writes_the_names_as_the_table(app):
	"""seaPlain is seas.plain (the property search of the table, upload), for odd names and every name of the index."""
	assert len(app['plain']) == len(NAMES) + 101
	for name, js in zip(app['names'], app['plain']):
		assert js == seas.plain(name), repr(name)


def test_the_app_builds_the_region_of_a_sea_as_the_package(app, monkeypatch):
	"""{"sea": MRGIDs}: the table filtered by them, as areas.region; by name, the app (without the index of the
	package) filters by the property search of the table; {"sea_at": [lon, lat]}: the sea at the point."""
	from test_regions import _chain
	for spec, js in zip(SPECS, app['regions']):
		assert js == _chain(monkeypatch, {'sea': spec}), spec
	assert app['named'] == [['FeatureCollection', seas.ASSET], ['Filter.inList', 'mrgid', [WESTERN]],
	                        ['Filter.inList', 'search', ['alboran sea']], ['Filter.or', '<ee>', '<ee>'], ['filter', '<ee>']]
	assert app['at'] == _chain(monkeypatch, {'sea_at': [-2.5, 36]})
	assert app['constants'][0] == seas.ASSET
	assert app['constants'][1]['sea'] == seas.ASSET and app['constants'][1]['3'].endswith('municipalities_es')


def test_the_app_checks_the_seas(app):
	codes = dict(zip((json.dumps(v, ensure_ascii=False) for v in VALUES), app['codes']))
	assert codes['3324'] == codes['"3324"'] == codes['3324.0'] == {'value': {'mrgids': [ALBORAN], 'names': [],
	                                                                          'groups': []}}
	assert codes['"  alborán SEA "'] == {'value': {'mrgids': [], 'names': ['alboran sea'], 'groups': []}}
	assert codes[json.dumps(['Alboran Sea', WESTERN])] == {'value': {'mrgids': [WESTERN], 'names': ['alboran sea'],
	                                                                 'groups': []}}
	# the whole Mediterranean Sea (seas.GROUPS), by its MRGID or its name, once
	group = {'value': {'mrgids': [], 'names': [], 'groups': [MEDITERRANEAN]}}
	assert codes['1905'] == codes['"1905"'] == codes['" Mediterranean SEA"'] == group
	assert codes[json.dumps(['mediterranean sea', ALBORAN, 1905, 'Alboran Sea'])] == {
		'value': {'mrgids': [ALBORAN], 'names': ['alboran sea'], 'groups': [MEDITERRANEAN]}}
	for empty in ('[]', '""', 'null'):
		assert codes[empty]['error'].startswith("sea is the MRGID of a sea area of the IHO (e.g. 3324) or its name")
		assert codes[empty]['error'].endswith('(find them with find_seas)')


def test_the_app_finds_the_seas_on_the_server(app):
	"""findSeas: the table filtered by its property search (or, for digits, by the MRGID), without geometries, sorted
	by 'order' (0 the very name, 1 those that begin with it, 2 the others; then the name) and at most LIMIT."""
	log = app['find']
	assert log[:3] == [['Filter.stringContains', 'search', 'alboran'], ['FeatureCollection', seas.ASSET],
	                   ['filter', '<ee>']]
	assert log[3] == ['map', '<function>'] and log[-2:] == [['sort', 'order'], ['limit', 30]]
	assert ['toDictionary', ['mrgid', 'name', 'area_km2']] in log and ['equals', 'alboran'] in log
	assert app['findCode'][:3] == [['Filter.stringContains', 'search', '3324'], ['Filter.eq', 'mrgid', 3324],
	                               ['Filter.or', '<ee>', '<ee>']]
	assert app['findCode'][-1] == ['limit', 20]


@pytest.mark.parametrize('text', ['alboran', 'sea', 'ocean', 'north', 'gulf', 'mediterranean', 'of', 'bay', 'b', ''])
def test_the_order_of_the_server_is_that_of_the_package(text):
	"""The order of findSeas (its property order) lists the same seas as seas.find."""
	t = seas.plain(text)
	found = []
	for mrgid, name, _, _ in seas.load()['rows'] + seas.group_rows():  # the table, and the groups of the app
		s = seas.plain(name)
		if t in s:
			found.append(('0' if s == t else '1' if s.startswith(t) else '2') + s)
	server = [o[1:] for o in sorted(found)[:30]]
	assert server == [seas.plain(s['NAME']) for s in seas.find(text, limit=30) if t in seas.plain(s['NAME'])]


def test_the_app_has_the_whole_mediterranean_sea_as_the_package(app):
	"""SEA_GROUPS of the app is seas.GROUPS, with the area of its sea areas; findSeas adds it to what the table finds
	(it is not there), as a feature without geometry with its mrgid, name, area_km2 and order."""
	groups, max_error = app['constants'][2:]
	assert groups == {str(c): {'name': n, 'parts': list(p), 'area_km2': seas.area_of(c)} for c, (n, p) in seas.GROUPS.items()}
	assert max_error == seas.GROUP_MAX_ERROR
	props = {'mrgid': MEDITERRANEAN, 'name': 'Mediterranean Sea', 'area_km2': seas.area_of(MEDITERRANEAN),
	         'order': '1mediterranean sea'}
	log = app['findGroup']
	assert ['Feature', None, props] in log and log[-4:] == [['FeatureCollection', ['<ee>']], ['merge', '<ee>'],
	                                                         ['sort', 'order'], ['limit', 30]]
	assert ['Feature', None, dict(props, order='2mediterranean sea')] in app['findGroupCode']
	assert not any(c[0] == 'merge' for c in app['find'])  # "Alborán": no group


def test_the_app_chooses_the_pixel_as_the_package(app):
	for (native, km2, target), js in zip(SCALES, app['scales']):
		assert js == areas.default_scale(native, km2 * 1e6, target), (native, km2, target)
	assert app['auto'] == [1000, 1000]
	assert app['large'] == [False, True, False, areas.LARGE_AREA_KM2, list(areas.LARGE_PIXEL)]
	assert app['isSea'] == [True, True, True, False, False]


def test_the_app_warns_as_the_package(app):
	"""seaWarning is services.sea_warning: every variable of the catalog over a sea, and none outside a sea."""
	for (region, ref), js in zip(WARNINGS, app['warnings']):
		entry = catalog.find(None, ref=ref) if ref is not None else None
		expected = services.sea_warning({'region': region, 'variable': entry['index'], 'sensor': entry['sensor'],
		                                 'collection': entry['col']}) if entry else None
		assert js == expected, (region, ref)
	assert sum(w is None for w in app['warnings'][:len(catalog.variables())]) == 2  # the Chl-a of MODIS


def test_the_credits_of_the_app_are_those_of_the_package(app):
	ids, credits = references.of_datasets([seas.ASSET])
	assert app['credits']['credits'] == credits == [seas.CREDIT]
	assert [r['citation'] for r in app['credits']['references']] == [references.get(i)['citation'] for i in ids]
	assert app['credits']['references'][0]['url'] == 'https://doi.org/10.14284/699'


# gee/ui.js ---------------------------------------------------------------------------------------------------------

def test_the_panel_has_the_mode_sea():
	ui = _read('gee', 'ui.js')
	assert ui.count("mode_sea: '") == 2 and "mode_sea: 'Mar u océano (IHO)'" in ui and \
		"mode_sea: 'Sea or ocean (IHO)'" in ui
	for key in ('seaHint', 'chooseSea', 'noSea', 'seaHelp', 'largeOnly'):
		assert ui.count(f'{key}: ') == 2, key
	assert "['wdpa', 'admin', 'ecoregion', 'biome', 'island', 'sea', 'view', 'draw']" in ui
	assert "setRegion(sea, names[0], {sea_at: [coords.lon, coords.lat]}, undefined, 'sea')" in ui  # a click on the map
	assert "setRegion(mo.seaRegion([mrgid]), state.seaNames[mrgid], {sea: mrgid}, undefined, 'sea')" in ui
	assert "'country', 'admin1', 'admin2', 'admin3', 'island_at', 'sea', 'sea_at', 'bbox', 'point'];" in ui
	assert "} else if (k === 'sea' || k === 'sea_at') {" in ui  # from some parameters


def test_the_app_computes_large_areas_only_with_coarse_data():
	ui = _read('gee', 'ui.js')
	limits = dict(re.findall(r'^\t\t(\w+): ([\d.e]+),?', ui[ui.index('var LIMITS'):ui.index('};', ui.index('var LIMITS'))],
	                         re.M))
	assert float(limits['maxAreaKm2']) == areas.LARGE_AREA_KM2 and float(limits['largeM']) == 250
	assert float(limits['maxLargeAreaKm2']) == 1e8 > max(r[2] for r in seas.load()['rows'])  # every ocean of the IHO
	assert 'if (area > LIMITS.maxAreaKm2 && Number(e.m) < LIMITS.largeM) {' in ui
	assert 'var sea = mo.seaWarning(state.regionSpec, e);' in ui and 'mo.noteWarning(sea)' in ui
	# the maps to download: 1 to 10 km at least in a large area, then bigger if the file would be too big
	assert 'var res = mo.isLarge(area) ? mo.defaultScale(native, area, mo.TARGET_PIXELS) : native;' in ui
	assert 'mo.defaultScale(e.m, state.info.boundsArea, 2.5e5)' in ui  # the percentiles of the colour ramp


def test_catalog_js_knows_the_variables_with_data_at_sea():
	data = _read('gee', 'catalog.js')
	data = json.loads(data[data.index('{'):data.rindex('}') + 1])
	assert sorted(v['col'] for v in data['variables'] if v.get('sea')) == [
		'NASA/OCEANDATA/MODIS-Aqua/L3SMI', 'NASA/OCEANDATA/MODIS-Terra/L3SMI']
	assert data['regions'][seas.ASSET]['credit'] == seas.CREDIT
