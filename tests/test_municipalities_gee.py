"""The municipalities of Spain (the administrative units of level 3, monitoreo.municipalities) in the Earth Engine app,
without Earth Engine: gee/core.js finds them on the server by the property search of their table (the name as
municipalities._plain gives it, which municipalityPlain gives the same) or by their code of the INE, builds the region
{"admin3": CODE} with the same calls of Earth Engine as areas.region and gives the credit and reference of the IGN as
the package cites them; gee/ui.js offers them as the level 3 of the administrative units, with its help, in English
and Spanish; and gee/catalog.js and gee/monitoreo_app.js are those that gee/build.py writes from the sources. What the
table answers can only be checked in Earth Engine, once it is there."""

import importlib.util
import json
import os
import shutil
import subprocess

import pytest

from monitoreo import areas, catalog, municipalities, references

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEE = os.path.join(ROOT, 'gee')
MONACHIL = '18134'

# names with what municipalities._plain undoes: accents, ñ, ü, ç, ï, the middle dot of Catalan, apostrophes, the '/'
# of the bilingual names and the '-' of the compound ones, upper case, spaces of any kind, and some characters whose
# NFKD is other letters (ligatures, superscripts, roman numerals, full width) or none (ß, æ, ø: left out)
NAMES = [
	'Monachil', 'Güéjar Sierra', 'A Coruña', 'Alacant/Alicante', 'Donostia/San Sebastián', 'Arrasate/Mondragón',
	'Vitoria-Gasteiz', 'Aïnsa-Sobrarbe', 'Castelló de la Plana', 'Sant Llorenç des Cardassar', "L'Hospitalet de Llobregat",
	"Castellar de n'Hug", 'Vilanova i la Geltrú', 'Esterri d\'Àneu', 'Col·legats', 'ĿLEIDA', 'Peñarroya-Pueblonuevo',
	'Agüimes', 'Bolaños de Calatrava', 'Cáceres', 'Ávila', 'Écija', 'Ourense', 'Pontevedra', 'Las Palmas de Gran Canaria',
	'Santa Cruz de Tenerife', 'Ses Salines', 'Puerto de la Cruz', 'Villanueva de la Concepción', 'Navas de San Juan',
	'Valle de Ecija ', '  Múltiples   espacios\tY\nlíneas  ', 'MAYÚSCULAS ÑANDÚ', 'Ñ', 'ü', 'Øster', 'Straße', 'Æbeltoft',
	'ﬁnca', 'km²', 'Nª Sª', 'Nº 3', 'Ⅳ', 'ＡＢＣ', 'İstanbul', 'Ǆemal', 'non breaking', 'thin space',
	'hyphen‐minus', 'a/b-c / d - e', '--//--', '', ' ', 'sep\x1cara\x1fdo', 'emoji 😀 name', 18134, '04001',
]
CODES = ['18134', 18134, 4001, ' 4001 ', ['18134', '04001'], ('18134',), [], 'abc', ['18134', 'x'], '123456', '-1',
         '+18', 'Monachil', '18 134']


def _build():
	"""gee/build.py as a module (here only its functions, without Earth Engine)."""
	spec = importlib.util.spec_from_file_location('monitoreo_gee_build', os.path.join(GEE, 'build.py'))
	build = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(build)
	return build


def _read(*parts):
	with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
		return f.read()


# gee/core.js in Node, with an ee that computes nothing (as in tests/test_regions.py): it logs every call
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
out.plain = input.names.map(mo.municipalityPlain);
out.codes = input.codes.map(function (v) { return attempt(function () { return mo.municipalityCodes(v); }); });
out.regions = input.specs.map(function (v) { return chain(function () { mo.municipalityRegion(v); }); });
out.admin = [chain(function () { mo.adminRegion(3, '18134'); }), chain(function () { mo.adminRegion('3', 18134); })];
out.find = chain(function () { mo.findMunicipalities('  Güéjar-SIERRA ', 30); });
out.findCode = chain(function () { mo.findMunicipalities(18134); });
out.credits = [1, 2, 3].map(mo.adminCredits);
out.constants = [mo.MUNICIPALITIES, mo.ADMIN_DATASETS];
process.stdout.write(JSON.stringify(out));
"""
SPECS = [MONACHIL, [MONACHIL, '04001'], 18134, [4001]]


@pytest.fixture(scope='module')
def app():
	if not shutil.which('node'):
		pytest.skip('no Node')
	data = {'names': [str(n) if not isinstance(n, str) else n for n in NAMES], 'codes': CODES, 'specs': SPECS}
	data['names'] += sorted({r[1] for r in municipalities.load()['rows']})  # every name of the index
	run = subprocess.run(['node', '-e', NODE, GEE], input=json.dumps(data), capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	return dict(json.loads(run.stdout), names=data['names'])


def test_the_app_writes_the_names_as_the_table(app):
	"""municipalityPlain is municipalities._plain (the property search of the table, upload): for the names with
	accents, ñ, ü, '/', '-'... and for every name of the index."""
	assert len(app['plain']) == len(app['names']) > len(NAMES) + 1000
	for name, js in zip(app['names'], app['plain']):
		assert js == municipalities._plain(name), repr(name)
	plain = dict(zip(app['names'], app['plain']))
	assert plain['Güéjar Sierra'] == 'guejar sierra' and plain['A Coruña'] == 'a coruna'
	assert plain['Alacant/Alicante'] == 'alacant alicante' and plain['Vitoria-Gasteiz'] == 'vitoria gasteiz'
	assert plain['Col·legats'] == 'collegats' and plain["L'Hospitalet de Llobregat"] == "l'hospitalet de llobregat"
	assert plain['  Múltiples   espacios\tY\nlíneas  '] == 'multiples espacios y lineas' and plain['Straße'] == 'strae'


def test_the_app_builds_the_region_of_a_municipality_as_the_package(app, monkeypatch):
	"""{"admin3": CODE}: the table of the municipalities filtered by the codes (inList), each named 'name (province)',
	with the calls of Earth Engine of areas.region; adminRegion of level 3 is that region."""
	from test_regions import _chain
	for spec, js in zip(SPECS, app['regions']):
		assert js == _chain(monkeypatch, {'admin3': spec}), spec
	assert app['regions'][1][:3] == [['FeatureCollection', municipalities.ASSET],
	                                 ['Filter.inList', 'code', [MONACHIL, '04001']], ['filter', '<ee>']]
	assert app['regions'][1][3:] == [['map', '<function>'], ['get', 'name'], ['String', '<ee>'], ['cat', ' ('],
	                                 ['get', 'province'], ['cat', '<ee>'], ['cat', ')'], ['set', 'name', '<ee>']]
	assert app['admin'][0] == app['admin'][1] == _chain(monkeypatch, {'admin3': MONACHIL})
	assert app['constants'][0] == municipalities.ASSET
	assert app['constants'][1] == {'1': areas.GAUL[1], '2': areas.GAUL[2], '3': municipalities.ASSET}


def test_the_app_checks_the_codes_as_the_package(app):
	"""The codes of the INE as 5 digits (str.zfill), and the same errors for those that are not; the app, without the
	index of the package, cannot know whether a code of 5 digits is that of a municipality (its search lists only
	those of the table)."""
	for v, js in zip(CODES, app['codes']):
		try:
			expected = {'value': areas.municipality_codes(v)}
		except ValueError as error:
			expected = {'error': str(error)}
		assert js == expected, v
	assert app['codes'][1] == {'value': ['18134']} and app['codes'][2] == app['codes'][3] == {'value': ['04001']}
	assert app['codes'][6] == {'error': "admin3 is the code of the INE of a municipality of Spain (5 digits, e.g. "
	                                    "'18134'): none given is not one (find them with find_admin_units, level 3)"}
	with pytest.raises(ValueError, match='99999 is not one'):
		areas.municipality_codes('99999')
	assert municipalities.name_of('99999') is None


def test_the_app_finds_the_municipalities_on_the_server(app):
	"""findMunicipalities: the table filtered by its property search (the text as municipalityPlain gives it) or by
	the start of the code, without geometries, sorted by 'order' (0 the very name, 1 those that begin with it, 2 the
	others; then the name and the code) and at most LIMIT."""
	t = 'guejar sierra'
	log = app['find']
	assert log[:5] == [['Filter.stringContains', 'search', t], ['Filter.stringStartsWith', 'code', t],
	                   ['Filter.or', '<ee>', '<ee>'], ['FeatureCollection', municipalities.ASSET], ['filter', '<ee>']]
	assert log[5] == ['map', '<function>'] and log[-2:] == [['sort', 'order'], ['limit', 30]]
	assert ['equals', t] in log and ['index', t] in log and ['eq', 0] in log
	assert ['toDictionary', ['code', 'name', 'province', 'region']] in log and ['set', 'level', 3] in log
	assert ['Algorithms.If', '<ee>', '1', '2'] in log and ['Algorithms.If', '<ee>', '0', '<ee>'] in log
	assert ['get', 'search'] in log and ['get', 'code'] in log and ['cat', ' '] in log
	assert app['findCode'][:2] == [['Filter.stringContains', 'search', MONACHIL],
	                               ['Filter.stringStartsWith', 'code', MONACHIL]]
	assert app['findCode'][-1] == ['limit', 20]  # as municipalities.find


def _server(text, limit):
	"""What the table answers to findMunicipalities(TEXT, LIMIT), from the index of the package: the rows whose
	search contains the text, or whose code begins with it, by their order (as core.js computes it on the server)."""
	t = municipalities._plain(text)
	found = []
	for code, name, _, _ in municipalities.load()['rows']:
		s = municipalities._plain(name)  # the property search of the table (municipalities.upload)
		if t in s or code.startswith(t):
			rank = '0' if s == t else '1' if s.startswith(t) else '2'
			found.append((rank + s + ' ' + code, code))
	return [code for _, code in sorted(found)[:limit]]


@pytest.mark.parametrize('text', ['Monachil', 'granada', 'san', 'SANT', 'la', 'villa', 'a coruña', 'Alicante',
                                  'castell', 'santa maría', 'de', 'o', 'pobla', "l'", 'güéjar', 'sierra', '18', '0',
                                  '181', ''])
def test_the_order_of_the_server_is_that_of_the_package(text):
	"""The order of findMunicipalities (its property order) lists the same municipalities as municipalities.find."""
	assert _server(text, 30) == [r['ADMIN3_CODE'] for r in municipalities.find(text, limit=30)], text


def test_the_credits_of_the_app_are_those_of_the_package(app):
	"""adminCredits: the credit line and the reference of the IGN for the municipalities (FAO GAUL 2025 for the levels
	1 and 2), the texts of catalog.json that references.cite gives with a result of such a region."""
	period = {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2020-01-01', 'end': '2020-12-31'}
	for level, js in zip((1, 2, 3), app['credits']):
		code = {1: 2541, 2: 141938, 3: MONACHIL}[level]
		cited = references.cite('region_stats', dict(period, region={f'admin{level}': code}))
		assert js['credits'] and all(c in cited['credits'] for c in js['credits']), level
		texts = [r['text'] for r in cited['references']]
		assert js['references'] and all(r['text'] in texts for r in js['references']), level
	ign = app['credits'][2]
	assert ign['credits'] == [municipalities.CREDIT] == [catalog.load()['datasets'][municipalities.ASSET]['credit']]
	ref = references.get('ign_au')
	assert ign['references'] == [{'citation': ref['citation'], 'url': ref['url'], 'text': ref['text']}]
	assert 'Instituto Geográfico Nacional' in ref['citation'] and 'CC BY 4.0 ign.es' in ign['credits'][0]
	assert app['credits'][0]['credits'][0].startswith('Source: FAO GAUL 2025')


# gee/ui.js in Node, driven as a user would (the ui and ee that compute nothing of tests/test_themes.py)
DRIVE = r"""
var controls = root.children[0];
function all(w, out) {
	out = out || [];
	out.push(w);
	w.children.forEach(function (c) { all(c, out); });
	return out;
}
function find(kind, test) {
	return all(controls).filter(function (w) { return w.kind === kind && (!test || test(w)); });
}
function labels() {
	return find('Label').filter(function (w) { return w.opts.value; }).map(function (w) {
		return [w.opts.value, w.opts.url || null];
	});
}
function items(value) {
	return function (w) { return (w.opts.items || []).some(function (i) { return i.value === value; }); };
}
function levels(w) {  // the select of the levels of the administrative units
	return JSON.stringify((w.opts.items || []).map(function (i) { return i.value; })) === '[1,2,3]';
}
var calls = [], mo = MonitorEO;
['findMunicipalities', 'findAdminUnits', 'adminRegion'].forEach(function (name) {
	var f = mo[name];
	mo[name] = function () {
		calls.push([name].concat(Array.prototype.slice.call(arguments)));
		return f.apply(null, arguments);
	};
});
var out = {};
find('Select', items('admin'))[0].opts.onChange('admin');
out.levels = find('Select', levels)[0].opts.items;
out.level1 = {boxes: find('Textbox').map(function (w) { return w.opts.placeholder; })};
find('Select', levels)[0].opts.onChange(3);
out.level3 = {boxes: find('Textbox').map(function (w) { return w.opts.placeholder; }), labels: labels()};
find('Textbox', function (w) { return w.opts.placeholder === input.hint; })[0].setValue('güéjar');
answer = {features: input.found.map(function (p) { return {properties: p}; })};
find('Button', function (w) { return w.opts.label === 'Search'; })[0].opts.onClick();
var unit = find('Select', function (w) { return w.opts.placeholder === 'Choose the unit'; })[0];
out.items = unit.opts.items;
answer = {info: {area: 2.5e8, centroid: [-3.5, 37.1], total: 2.5e8, boundsArea: 4e8, pacific: null,
	bounds: [[[-3.6, 37.0], [-3.4, 37.0], [-3.4, 37.2], [-3.6, 37.2], [-3.6, 37.0]]]}, n: 1};
unit.opts.onChange(input.found[0].code);
out.region = labels();
find('Button', function (w) { return w.opts.label === 'Español'; })[0].opts.onClick();
out.spanish = labels();
out.calls = calls;
process.stdout.write(JSON.stringify(out));
"""
EN_HELP = ('The municipalities of Spain of the Instituto Geográfico Nacional (its INSPIRE administrative units, CC BY '
           '4.0 ign.es). Search by name, whatever the case and accents, or by the code of the INE (5 digits, e.g. 18134).')
ES_HELP = ('Los municipios de España del Instituto Geográfico Nacional (sus unidades administrativas INSPIRE, CC BY 4.0 '
           'ign.es). Busca por el nombre, sin importar mayúsculas ni tildes, o por el código del INE (5 dígitos, p. ej. '
           '18134).')
FOUND = [{'code': '18096', 'name': 'Güéjar Sierra', 'province': 'Granada', 'region': 'Andalucía', 'level': 3},
         {'code': MONACHIL, 'name': 'Monachil', 'province': 'Granada', 'region': 'Andalucía', 'level': 3}]


def _ui_texts(lang):
	from test_themes import _ui_texts
	return _ui_texts(_read('gee', 'ui.js'), lang)


@pytest.fixture(scope='module')
def panel():
	if not shutil.which('node'):
		pytest.skip('no Node')
	from test_themes import PANEL
	start = PANEL[:PANEL.index('var controls = root.children[0]')]
	data = _build().read_catalog()
	data = {'community': data['community'], 'other_themes': data['other_themes'], 'assets': {},
	        'hint': _ui_texts('en')['adminHint3'], 'found': FOUND}
	run = subprocess.run(['node', '-e', start + DRIVE, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout)


def test_the_panel_has_the_level_3(panel):
	"""Administrative unit: the level 3, the municipalities of Spain, with the help of the IGN and no country (they
	are those of Spain); the search lists 'name (province)' and the code of the INE, and the region is {"admin3": CODE}
	named 'name (province)', with the credit and the reference of the IGN."""
	en = _ui_texts('en')
	assert panel['levels'] == [{'value': 1, 'label': en['level1']}, {'value': 2, 'label': en['level2']},
	                           {'value': 3, 'label': 'Level 3 (municipalities of Spain, IGN)'}]
	assert en['countryHint'] in panel['level1']['boxes'] and en['countryHint'] not in panel['level3']['boxes']
	assert en['adminHint3'] in panel['level3']['boxes'] and en['adminHint'] not in panel['level3']['boxes']
	assert [EN_HELP, None] in panel['level3']['labels']
	assert panel['calls'][0] == ['findMunicipalities', 'güéjar', 30]
	assert panel['items'] == [{'value': '18096', 'label': 'Güéjar Sierra (Granada) · INE 18096'},
	                          {'value': MONACHIL, 'label': 'Monachil (Granada) · INE 18134'}]
	assert panel['calls'][1] == ['adminRegion', 3, '18096']
	assert not any(c[0] == 'findAdminUnits' for c in panel['calls'])
	ref = references.get('ign_au')
	assert ['Region: Güéjar Sierra (Granada) · 250 km²', None] in panel['region']
	assert [municipalities.CREDIT, None] in panel['region']
	assert ['References: ' + ref['citation'], ref['url']] in panel['region']
	assert ['Región: Güéjar Sierra (Granada) · 250 km²', None] in panel['spanish']
	assert ['Referencias: ' + ref['citation'], ref['url']] in panel['spanish']


def test_the_help_of_the_level_3(panel):
	"""The texts of the level 3 in English and Spanish: the municipalities of Spain of the Instituto Geográfico Nacional
	(CC BY 4.0 ign.es), found by name or by the code of the INE; the mode names both sources."""
	en, es = _ui_texts('en'), _ui_texts('es')
	assert en['level3'] == 'Level 3 (municipalities of Spain, IGN)' and es['level3'] == 'Nivel 3 (municipios de España, IGN)'
	assert en['adminHint3'] == 'Name or INE code, e.g. Monachil'
	assert es['adminHint3'] == 'Nombre o código del INE, p. ej. Monachil'
	assert en['mode_admin'] == 'Administrative unit'  # as in QGIS: FAO GAUL (levels 1, 2) and IGN (level 3)
	assert es['mode_admin'] == 'Unidad administrativa'
	assert [EN_HELP, None] in panel['level3']['labels'] and [ES_HELP, None] in panel['spanish']


def test_catalog_js_has_the_credits_of_catalog_json():
	"""The credits and references of the administrative units in catalog.js (regions) are those that build.py writes
	from catalog.json: run python gee/build.py --about-only after changing them."""
	build = _build()
	assert build.read_catalog()['regions'] == build.region_credits(), 'run gee/build.py --about-only'
	assert build.ADMIN_DATASETS == [areas.GAUL[1], areas.GAUL[2], municipalities.ASSET]


def test_monitoreo_app_js_is_written_from_the_sources(tmp_path, monkeypatch):
	"""gee/monitoreo_app.js is catalog.js, core.js and ui.js as they are: run python gee/build.py --app-only after
	changing them."""
	build = _build()
	for name in ('catalog.js', 'core.js', 'ui.js'):
		shutil.copy(os.path.join(GEE, name), tmp_path / name)
	monkeypatch.setattr(build, 'HERE', str(tmp_path))
	build.app()
	assert (tmp_path / 'monitoreo_app.js').read_text('ascii') == _read('gee', 'monitoreo_app.js'), \
		'run gee/build.py --app-only'
	app_js = _read('gee', 'monitoreo_app.js')
	assert 'findMunicipalities' in app_js and municipalities.ASSET in app_js
