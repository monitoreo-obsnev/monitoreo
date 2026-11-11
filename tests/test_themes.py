"""The themes of the menus (catalog.THEMES, and catalog.OTHER_THEMES for the data of Earth Engine outside the catalog,
also in the app of the Earth Engine Code Editor: gee/core.js and gee/ui.js) and the links to suggest a change or report
an error (about.feedback), without Earth Engine."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import urllib.parse

import pytest

from monitoreo import about, assets, catalog, community, services, variable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_variable_has_one_theme():
	for e in catalog.variables():
		themes = [t['key'] for t in catalog.THEMES if e['index'] in t['indices']]
		assert len(themes) == 1, (e['index'], themes)
		assert e['theme'] == themes[0]
	assert all(t['en'] and t['es'] for t in catalog.THEMES)
	assert len({t['key'] for t in catalog.THEMES}) == len(catalog.THEMES)
	indices = {e['index'] for e in catalog.variables()}
	for t in catalog.THEMES:  # no theme lists a variable the catalog does not have
		assert set(t['indices']) <= indices, (t['key'], set(t['indices']) - indices)


def test_the_analyses_of_a_theme_are_tools():
	from monitoreo import mcp_server
	for t in catalog.THEMES:
		for name in t.get('analyses') or []:
			assert hasattr(services, name) and hasattr(mcp_server, name), name
	assert catalog.theme_of('NBR')['analyses'] == ['burn_severity']


def test_list_variables_by_theme():
	fire = services.list_variables(theme='fire')
	assert {v['variable'] for v in fire} == {'NBR', 'RBR'} and fire[0]['theme'] == 'Fire'
	assert services.list_variables(theme='Nieve', lang='es')[0]['theme'] == 'Nieve'
	assert {v['variable'] for v in services.list_variables(theme='terrain')} == {'ELEVATION', 'SLOPE'}
	with pytest.raises(ValueError, match='unknown theme'):
		services.list_variables(theme='mountains')
	assert services.describe_variable('LST', 'Modis')['theme'] == 'Energy and temperature'
	assert [t['key'] for t in services.themes()][:2] == ['vegetation', 'water']


def test_the_app_has_the_themes():
	with open(os.path.join(ROOT, 'gee', 'catalog.js'), encoding='utf-8') as f:
		text = f.read()
	data = json.loads(text[text.index('{'):text.rstrip().rindex('}') + 1])
	assert [t['key'] for t in data['themes']] == [t['key'] for t in catalog.THEMES]
	assert all(v['theme'] for v in data['variables'])
	links = data['about']['feedback']['links']
	assert 'tool=Earth+Engine+app' in links['issue'] and about.FORM in links['form']


def test_feedback_links():
	links = about.feedback('qgis', '0.3.15')
	issue = urllib.parse.urlparse(links['issue'])
	assert links['issue'].startswith(about.REPOSITORY + '/issues/new/choose?')
	assert urllib.parse.parse_qs(issue.query) == {'tool': ['QGIS plugin'], 'version': ['0.3.15']}
	form = urllib.parse.parse_qs(urllib.parse.urlparse(links['form']).query)
	assert form[about.FORM_FIELDS['tool']] == ['Complemento de QGIS / QGIS plugin']
	assert form[about.FORM_FIELDS['version']] == ['0.3.15'] and form['usp'] == ['pp_url']
	assert set(about.FEEDBACK['en']) == set(about.FEEDBACK['es']) == {'button', 'issue', 'form'}
	for name in ('error.yml', 'suggestion.yml', 'config.yml'):  # the templates the links open
		assert os.path.exists(os.path.join(ROOT, '.github', 'ISSUE_TEMPLATE', name))
	with open(os.path.join(ROOT, '.github', 'ISSUE_TEMPLATE', 'error.yml'), encoding='utf-8') as f:
		template = f.read()
	assert 'id: tool' in template and 'id: version' in template and about.FORM in template


# The data of Earth Engine outside the catalog in the app of the Code Editor (gee/core.js and gee/ui.js) ------------

GEE = os.path.join(ROOT, 'gee')


def _build():
	"""gee/build.py as a module (it writes catalog.js; here only its functions, without Earth Engine)."""
	spec = importlib.util.spec_from_file_location('monitoreo_gee_build', os.path.join(GEE, 'build.py'))
	build = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(build)
	return build


def _catalog_js():
	with open(os.path.join(GEE, 'catalog.js'), encoding='utf-8') as f:
		text = f.read()
	return json.loads(text[text.index('{'):text.rstrip().rindex('}') + 1])


def test_the_app_has_the_themes_of_the_data_of_earth_engine():
	"""gee/catalog.js carries the themes of catalog.OTHER_THEMES and the copy of the index of the GEE Community
	Catalog (community.json.gz) that build.py makes of them: run python gee/build.py --project ... after changing them."""
	data = _catalog_js()
	assert data.get('other_themes') == catalog.OTHER_THEMES, 'run gee/build.py: the app has other themes'
	assert data.get('community') == _build().community_index(), 'run gee/build.py: the app has another community index'


def test_the_slim_community_index_of_the_app():
	"""The copy of the index in the app has every image and collection of the package, with its title, type, theme,
	page and licence, in a valid JSON (one dataset per line)."""
	build = _build()
	index = build.community_index()
	datasets = community.datasets()
	assert len(index['datasets']) == len(datasets) > 1000
	assert [n for n, _ in index['themes']] == [t for t, _ in community.THEMES]
	for row, d in zip(index['datasets'], datasets):
		assert row[0] == d['id'] and row[1] == d['title'] and row[2] == (d['type'] == 'image_collection')
		assert index['themes'][row[3]][0] == d['theme']
		page = row[4] if row[4].startswith('http') else index['docs'] + row[4]
		assert page == d['docs']
		licence = d.get('license_text') if d.get('license') == 'custom' else d.get('license')
		assert (index['licences'][row[5]] if row[5] is not None else None) == licence
	text = build.catalog_text({'themes': catalog.THEMES, 'other_themes': catalog.OTHER_THEMES, 'community': index})
	assert json.loads(text)['community'] == json.loads(json.dumps(index))
	assert text.count('\n') < 1200  # the datasets one per line, not a line per value


NODE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
// an object ee that computes nothing: it logs every call of a function or method, [name, arguments] (its objects are
// '<ee>'), runs the function of map on one of its objects and answers evaluate with input.evaluate
var log = [], TAG = '__ee__', answer = null;
function arg(a) {
	if (a && (typeof a === 'object' || typeof a === 'function') && a[TAG]) return '<ee>';
	if (typeof a === 'function') return '<function>';
	if (Array.isArray(a)) return a.map(arg);
	return a === undefined ? null : a;
}
function object() {
	return new Proxy({}, {get: function (t, p) {
		return p === TAG ? true : typeof p === 'symbol' ? undefined : call(p);
	}});
}
function call(name) {
	return new Proxy(function () {
		var args = Array.prototype.slice.call(arguments);
		log.push([name].concat(args.map(arg)));
		if (name === 'map') args[0](object());
		if (name === 'evaluate') args[0](answer, answer === null && input.failed ? 'failed' : undefined);
		return object();
	}, {get: function (t, p) { return p === TAG ? true : typeof p === 'symbol' ? undefined : call(name + '.' + p); }});
}
var assetsOf = input.assets;
var data = {getAsset: function (id, done) { done(assetsOf[id] || null, assetsOf[id] ? undefined : 'not found'); }};
global.ee = new Proxy({}, {get: function (t, p) { return p === 'data' ? data : call(p); }});
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[1], f), 'utf8'), {filename: f});
});
CATALOG.community = input.community;  // those of the package, whatever the catalog.js there is
CATALOG.other_themes = input.other_themes;
var mo = global.MonitorEO;
function attempt(f) {
	try {
		return {value: f()};
	} catch (e) {
		return {error: e.message};
	}
}
var out = {};
out.ids = input.ids.map(mo.assetId);
out.units = input.units.map(function (u) {
	return input.metrics.map(function (m) {
		return attempt(function () {
			return mo.unitOf(mo.customEntry({asset: 'A/B', band: 'b', m: 30, unit: u[0]}), m);
		});
	});
});
out.catalogUnits = input.catalogUnits.map(function (u) { return mo.unitOf({unit: u[0]}, u[1]); });
out.chains = input.chains.map(function (c) {
	log = [];
	var e = mo.customEntry(c.entry);
	var s = mo.spec({entry: e, period: c.period, metric: 'mean'});
	if (e.static) mo.image(s, object(), c.res);
	else mo.collection(s, object(), c.res);
	return log.slice();
});
log = [];
var image = mo.spec({entry: mo.customEntry({asset: 'WORLDCLIM/V1/BIO', type: 'image', band: 'bio01', use: 'image',
	m: 927.67, scale: 0.1, unit: 'degC'})});
var collection = mo.spec({entry: mo.customEntry({asset: 'IDAHO_EPSCOR/TERRACLIMATE', type: 'image_collection',
	band: 'pr', m: 4638.3, unit: 'mm'}), period: ['2020-01-01', '2020-12-31']});
out.names = [mo.entryName(mo.entryOf(image)), mo.entryName(mo.entryOf(collection))];
out.checkDates = attempt(function () { mo.checkDates(image, 'time series'); });
out.checkRgb = attempt(function () { mo.checkRgb(collection); });
out.filters = mo.filters(mo.entryOf(collection), {});
out.fixed = mo.fixedFilters(mo.entryOf(collection));
out.rgb = mo.rgbOf(mo.customEntry({asset: 'MODIS/061/MOD09GA', type: 'image_collection', band: 'sur_refl_b01',
	m: 500}));
out.errors = input.errors.map(function (o) { return attempt(function () { return mo.customEntry(o); }); });
out.themes = {en: mo.communityThemes('en'), es: mo.communityThemes('es')};
out.datasets = input.themes.map(function (th) { return mo.communityDatasets(th); });
out.all = mo.communityDatasets().length;
out.unknownTheme = attempt(function () { return mo.communityDatasets('mountains'); });
out.records = input.records.map(mo.communityRecord);
out.sources = input.sources.map(function (id) { return mo.assetSource(id, assetsOf[id] || {}); });
out.info = input.infos.map(function (c) {
	answer = c.evaluate;
	var got = null;
	mo.assetInfo(c.asset, function (error, info) { got = error ? {error: error.message} : info; });
	return got;
});
out.otherThemes = mo.otherThemes().map(function (th) { return th.key; });
process.stdout.write(JSON.stringify(out));
"""


class _Call:
	"""A function or method of the fake ee of _python_chain: its call is logged, [name, arguments]."""

	def __init__(self, rec, name):
		self._rec, self._name = rec, name

	def __call__(self, *args):
		self._rec.append([self._name] + [_arg(a) for a in args])
		if self._name == 'map':
			args[0](_Obj(self._rec))
		return _Obj(self._rec)

	def __getattr__(self, attr):
		if attr.startswith('__'):
			raise AttributeError(attr)
		return _Call(self._rec, f'{self._name}.{attr}')


class _Obj:
	"""An object of the fake ee (an image, a collection, a reducer...): its methods are logged."""

	def __init__(self, rec):
		self._rec = rec

	def __getattr__(self, attr):
		if attr.startswith('__'):
			raise AttributeError(attr)
		return _Call(self._rec, attr)


class _Root(_Obj):
	def __getattr__(self, attr):
		if attr.startswith('__'):
			raise AttributeError(attr)
		return _Call(self._rec, attr)


def _arg(a):
	if isinstance(a, (_Call, _Obj)):
		return '<ee>'
	if callable(a):
		return '<function>'
	if isinstance(a, (list, tuple)):
		return [_arg(x) for x in a]
	return a


# The images of the data of Earth Engine as the package and the app build them: a collection (on the pixels of the
# data and on finer ones: bilinear), an image (stored scaled, on bigger pixels: their mean) and a collection of tiles
# given as an image, with the slope of its band
CHAINS = [
	{'entry': {'asset': 'IDAHO_EPSCOR/TERRACLIMATE', 'type': 'image_collection', 'band': 'pr', 'use': 'collection',
	           'm': 4638.3, 'unit': 'mm'}, 'period': ['2020-01-01', '2020-12-31'], 'res': 4638.3},
	{'entry': {'asset': 'IDAHO_EPSCOR/TERRACLIMATE', 'type': 'image_collection', 'band': 'tmmx', 'use': 'collection',
	           'm': 4638.3, 'scale': 0.1, 'offset': -2, 'unit': 'degC'}, 'period': ['2019-03-01', '2021-02-28'],
	 'res': 1000},
	{'entry': {'asset': 'WORLDCLIM/V1/BIO', 'type': 'image', 'band': 'bio01', 'use': 'image', 'm': 927.67,
	           'scale': 0.1, 'unit': 'degC'}, 'period': None, 'res': 927.67},
	{'entry': {'asset': 'WORLDCLIM/V1/BIO', 'type': 'image', 'band': 'bio12', 'use': 'image', 'm': 927.67},
	 'period': None, 'res': 5000},
	{'entry': {'asset': 'projects/sat-io/open-datasets/FABDEM', 'type': 'image_collection', 'band': 'b1',
	           'use': 'image', 'm': 30, 'terrain': 'slope', 'unit': 'm'}, 'period': None, 'res': 10},
]


def _python_spec(c):
	e = c['entry']
	start, end = c['period'] or (None, None)
	return services.make_spec(None, None, start, end, **{e['use']: e['asset']}, band=e['band'],
	                          band_scale=e.get('scale'), band_offset=e.get('offset'), unit=e.get('unit'),
	                          terrain=e.get('terrain'))


def _python_chain(c, monkeypatch):
	"""The calls of Earth Engine of variable.collection or variable.image for the case C of CHAINS."""
	e = c['entry']
	spec = _python_spec(c)
	monkeypatch.setitem(variable._native, (e['asset'], e['band']), e['m'])
	monkeypatch.setitem(variable._types, e['asset'], 'IMAGE' if e['type'] == 'image' else 'IMAGE_COLLECTION')
	rec = []
	monkeypatch.setattr(variable, 'ee', _Root(rec))
	if e['use'] == 'image':
		variable.image(spec, _Obj(rec), c['res'])
	else:
		variable.collection(spec, _Obj(rec), c['res'])
	return rec


IDS = ['IDAHO_EPSCOR/TERRACLIMATE', ' ee.ImageCollection("IDAHO_EPSCOR/TERRACLIMATE"); ', "'WORLDCLIM/V1/BIO'",
       "ee.Image('WORLDCLIM/V1/BIO')", 'projects/earthengine-public/assets/COPERNICUS/DEM/GLO30',
       'projects/sat-io/open-datasets/FABDEM', '"users/someone/an_image"']
UNITS = ['mm', ' mm ', '1', 'unitless', 'degC', '°C', 'º', 'mm month-1', 'mm day-1', 'kg m-2 s-1', '', None, 'm²',
         'mm/día']
METRICS = ['mean', 'sum', 'SUM', 'max']
COMMUNITY_THEMES = ['Hydrology', 'Tiempo y clima', 'soil properties']
INFOS = [  # what ee.data.getAsset and the evaluate of mo.assetInfo answer
	{'asset': 'WORLDCLIM/V1/BIO', 'evaluate': {'bands': ['bio01', 'bio12'], 'scales': {'bio01': 927.67, 'bio12': 927.67},
	                                           'dated': False}},
	{'asset': 'IDAHO_EPSCOR/TERRACLIMATE', 'evaluate': {'bands': ['aet', 'pr'], 'scales': {'aet': 4638.3, 'pr': 4638.3},
	                                                    'dated': True}},
	{'asset': 'projects/sat-io/open-datasets/FABDEM', 'evaluate': {'bands': ['b1'], 'scales': {'b1': 30.0},
	                                                               'dated': False}},
	{'asset': 'projects/someone/assets/empty', 'evaluate': None},
	{'asset': 'projects/someone/assets/regions', 'evaluate': None},
	{'asset': 'projects/someone/assets/folder', 'evaluate': None},
	{'asset': 'projects/someone/assets/missing', 'evaluate': None},
]
ASSETS = {'WORLDCLIM/V1/BIO': {'type': 'Image', 'properties': {'system:title': 'WorldClim BIO Variables V1'}},
          'IDAHO_EPSCOR/TERRACLIMATE': {'type': 'ImageCollection', 'properties': {}},
          'projects/sat-io/open-datasets/FABDEM': {'type': 'ImageCollection', 'properties': {}},
          'projects/someone/assets/empty': {'type': 'ImageCollection'},
          'projects/someone/assets/regions': {'type': 'Table'},
          'projects/someone/assets/folder': {'type': 'Folder'},
          'users/someone/an_image': {'type': 'Image', 'properties': {}}}


@pytest.fixture(scope='module')
def app():
	"""The answers of gee/core.js (with catalog.js) in Node, with an object ee that computes nothing, and the themes
	and the community index of the package."""
	if not shutil.which('node'):
		pytest.skip('no Node')
	legacy = 'projects/earthengine-legacy/assets/' + next(d['id'] for d in community.datasets()
	                                                      if d['id'].startswith('projects/sat-io/'))
	data = {'ids': IDS, 'units': [[u] for u in UNITS], 'metrics': METRICS, 'chains': CHAINS,
	        'catalogUnits': [['[mm/month]', 'sum'], ['[mm/month]', 'mean'], ['[mm/day]', 'Sum'], ['[°C]', 'sum']],
	        'errors': [{'asset': 'A/B', 'band': '', 'm': 30},
	                   {'asset': 'WORLDCLIM/V1/BIO', 'type': 'image', 'band': 'bio01', 'use': 'collection', 'm': 927.67},
	                   {'asset': 'A/B', 'band': 'b', 'm': 30, 'unit': 'm²'},
	                   {'asset': 'A/B', 'band': 'b', 'use': 'image', 'm': 30, 'terrain': 'curvature'},
	                   {'asset': 'A/B', 'band': 'b'}, {'asset': ' ', 'band': 'b', 'm': 30}],
	        'themes': COMMUNITY_THEMES, 'records': [legacy, 'projects/someone/assets/nothing'],
	        'sources': ['IDAHO_EPSCOR/TERRACLIMATE', 'projects/sat-io/open-datasets/FABDEM', 'users/someone/an_image'],
	        'infos': INFOS, 'assets': ASSETS, 'community': _build().community_index(),
	        'other_themes': catalog.OTHER_THEMES}
	run = subprocess.run(['node', '-e', NODE, GEE], input=json.dumps(data), capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout)


def test_the_app_builds_the_images_of_the_data_of_earth_engine_as_the_package(app, monkeypatch):
	"""fromCollection and staticImage of gee/core.js call Earth Engine as variable._from_collection and variable._fixed:
	the band, its scale and offset, bilinear on finer pixels, the mean on pixels more than twice as big, the mosaic of
	the tiles, the terrain and the date of each image; no pixel filters."""
	for c, js in zip(CHAINS, app['chains']):
		assert js == _python_chain(c, monkeypatch), c
	assert ['resample', 'bilinear'] in app['chains'][1] and ['resample', 'bilinear'] not in app['chains'][0]
	assert ['Reducer.mean'] in app['chains'][3] and ['Terrain.slope', '<ee>'] in app['chains'][4]
	assert ['mosaic'] in app['chains'][4] and ['copyProperties', '<ee>', ['system:time_start']] in app['chains'][0]
	assert app['filters'] == {f: False for f in ('clouds', 'water', 'snow', 'aerosols')} and app['fixed'] == []
	assert app['rgb'] is None  # not even for a collection of the catalog given by its ID


def test_the_app_takes_the_ids_and_units_as_the_package(app):
	assert app['ids'] == [assets.normalize(i) for i in IDS]
	for u, row in zip(UNITS, app['units']):
		for m, js in zip(METRICS, row):
			try:
				spec = services.make_spec(None, None, '2020-01-01', '2020-12-31', collection='A/B', band='b', unit=u,
				                          metric=m)
			except ValueError as error:
				assert js == {'error': str(error)}, (u, m)
				continue
			assert js == {'value': services._unit(spec)}, (u, m)
	assert app['units'][UNITS.index('1')][0] == {'value': '[unitless]'}
	assert app['units'][UNITS.index('mm month-1')][1] == {'value': 'mm'}  # the sum of a rate is a total
	assert app['catalogUnits'] == [catalog.unit_of(u, m) for u, m in
	                               [['[mm/month]', 'sum'], ['[mm/month]', 'mean'], ['[mm/day]', 'Sum'], ['[°C]', 'sum']]]


def test_the_app_refuses_the_data_of_earth_engine_as_the_package(app, monkeypatch):
	"""The same names in the titles, and the same messages for a fixed image given for a time series, the true colour
	of data outside the catalog, an image given as a collection and a unit that is not UDUNITS."""
	image = _python_spec(CHAINS[2])
	collection = _python_spec(CHAINS[0])
	assert app['names'] == [services._title(image), services._title(collection).split(' | ')[0]]
	assert app['names'] == ['WORLDCLIM/V1/BIO bio01', 'IDAHO_EPSCOR/TERRACLIMATE pr']
	with pytest.raises(ValueError) as error:
		variable.check_dates(image, 'time series')
	assert app['checkDates'] == {'error': str(error.value)}
	with pytest.raises(ValueError) as error:
		variable.check_rgb(collection)
	assert app['checkRgb'] == {'error': str(error.value)}
	no_band, image_as_collection, bad_unit, bad_terrain, no_size, no_id = app['errors']
	assert 'give the band of A/B' in no_band['error']
	monkeypatch.setattr(variable, '_types', {})
	monkeypatch.setattr(assets, 'asset_type', lambda asset: 'image')
	spec = services.make_spec(None, None, '2020-01-01', '2020-12-31', collection='WORLDCLIM/V1/BIO', band='bio01')
	with pytest.raises(ValueError) as error:
		variable.check_asset(spec)
	assert image_as_collection == {'error': str(error.value)}
	with pytest.raises(ValueError) as error:
		services.make_spec(None, None, '2020-01-01', '2020-12-31', collection='A/B', band='b', unit='m²')
	assert bad_unit == {'error': str(error.value)}
	assert bad_terrain == {'error': 'unknown terrain curvature: use slope, aspect'}
	assert 'read its ID first' in no_size['error'] and 'give the ID' in no_id['error']


def test_the_app_reads_the_ids_as_the_package(app, monkeypatch):
	"""assetInfo: the type, bands and pixel sizes of an ID, its use (collection only if its images have dates, as
	assets.describe), where it comes from, and the messages of assets._asset for tables, folders and empty
	collections."""
	import ee

	worldclim, terraclimate, fabdem, empty, table, folder, missing = app['info']
	assert worldclim == {'asset': 'WORLDCLIM/V1/BIO', 'type': 'image', 'dated': False, 'use': 'image',
	                     'bands': ['bio01', 'bio12'], 'scales': {'bio01': 927.67, 'bio12': 927.67},
	                     'source': 'Earth Engine data catalog', 'title': 'WorldClim BIO Variables V1',
	                     'page': assets.page('WORLDCLIM/V1/BIO'), 'licence': None}
	assert (terraclimate['type'], terraclimate['use'], terraclimate['dated']) == ('image_collection', 'collection', True)
	rec = community.record('projects/sat-io/open-datasets/FABDEM')
	assert (fabdem['use'], fabdem['source'], fabdem['title'], fabdem['page'], fabdem['theme']) == \
		('image', 'GEE Community Catalog', rec['title'], rec['docs'], rec['theme'])
	assert fabdem['licence'] == (rec.get('license_text') if rec.get('license') == 'custom' else rec.get('license'))
	assert empty == {'error': 'the collection projects/someone/assets/empty has no images'}
	assert missing['error'].startswith('Earth Engine has no image or collection projects/someone/assets/missing, or')
	for got, kind in ((table, 'TABLE'), (folder, 'FOLDER')):
		monkeypatch.setattr(assets, '_info', {})
		monkeypatch.setattr(ee.data, 'getAsset', lambda asset, kind=kind: {'type': kind})
		with pytest.raises(ValueError) as error:
			assets.asset_type(got['error'].split(' ')[0])
		assert got == {'error': str(error.value)}
	sources = app['sources']
	assert sources[0]['source'] == 'Earth Engine data catalog' and sources[0]['page'] == \
		assets.page('IDAHO_EPSCOR/TERRACLIMATE')
	assert sources[1]['source'] == 'GEE Community Catalog'
	assert sources[2] == {'source': 'Earth Engine asset', 'title': 'users/someone/an_image', 'licence': None,
	                      'page': 'https://code.earthengine.google.com/?asset=users/someone/an_image'}


def test_the_app_lists_the_community_catalog_as_the_package(app):
	assert app['themes'] == {'en': community.themes('en'), 'es': community.themes('es')}
	assert app['all'] == len(community.datasets())
	for theme, js in zip(COMMUNITY_THEMES, app['datasets']):
		expected = [{'id': d['id'], 'title': d['title'], 'type': d['type'], 'theme': d['theme'], 'docs': d['docs'],
		             'license': d.get('license_text') if d.get('license') == 'custom' else d.get('license')}
		            for d in community.datasets(theme)]
		assert js == expected and len(js) > 3, theme
	with pytest.raises(ValueError) as error:
		community.datasets('mountains')
	assert app['unknownTheme'] == {'error': str(error.value)}
	legacy, nothing = app['records']
	assert legacy['id'].startswith('projects/sat-io/') and nothing is None  # with or without the old prefix
	assert app['otherThemes'] == [t['key'] for t in catalog.OTHER_THEMES] == ['earth_engine', 'community']


def _ui_texts(ui, lang):
	"""The texts of LANG of the dictionary T of gee/ui.js."""
	es, en = ui.index('\tes: {'), ui.index('\ten: {')
	block = ui[es:en] if lang == 'es' else ui[en:ui.index('var METRICS')]
	return dict(re.findall(r"""['"]?([\w-]+)['"]?: '((?:[^'\\]|\\.)*)'""", block))


def test_the_app_offers_the_data_of_earth_engine():
	"""The widgets of the two themes of catalog.OTHER_THEMES have the names of the QGIS plugin, in both languages."""
	with open(os.path.join(GEE, 'ui.js'), encoding='utf-8') as f:
		ui = f.read()
	en, es = _ui_texts(ui, 'en'), _ui_texts(ui, 'es')
	assert {k: en[k] for k in ('assetId', 'read', 'band', 'useAs', 'use_collection', 'use_image', 'bandScale',
	                           'bandOffset', 'unit', 'communityTheme', 'dataset')} == {
		'assetId': 'Earth Engine ID', 'read': 'Read', 'band': 'Band', 'useAs': 'Use as',
		'use_collection': 'Images with dates (collection)', 'use_image': 'Fixed image (image)',
		'bandScale': 'Band scale', 'bandOffset': 'Band offset', 'unit': 'Unit (UDUNITS)',
		'communityTheme': 'Theme of the catalog', 'dataset': 'Dataset'}
	assert set(en) == set(es)


# The panel of the app (gee/ui.js, with catalog.js and core.js) in Node, driven as a user would: the themes, an ID read,
# its band, scale, offset, unit and use, then the map, its GeoTIFF, the time series, the comparison of periods, the
# trends, a condition (where), the errors, the same data as a fixed image, an image, a table, an ID that is not there,
# the GEE Community Catalog in Spanish and back to a variable. Its ui and ee compute nothing (see the comments).
PANEL = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
// an object ee that computes nothing: its objects answer every method; evaluate answers ANSWER (or, for 'rows', a row
// of each ee.Feature made since the last evaluate, as seriesTable makes them); getDownloadURL gives a link and keeps
// the name of the file; ee.data.getAsset answers input.assets
var TAG = '__ee__', answer = null, features = [], files = [];
function object() {
	return new Proxy({}, {get: function (t, p) {
		return p === TAG ? true : typeof p === 'symbol' ? undefined : call(p);
	}});
}
function call(name) {
	return new Proxy(function () {
		var args = Array.prototype.slice.call(arguments);
		if (name === 'Feature' && args[1] && args[1].date) features.push(args[1]);
		if (name === 'map' && typeof args[0] === 'function') args[0](object());
		if (name === 'evaluate') {
			var a = answer === 'rows' ? {features: features.map(function (p, i) {
				return {properties: {region: 'Map view', date: p.date, value: 10 + i % 7 + i / 10, n_pixels: 4, n_images: 1}};
			})} : answer;
			features = [];
			args[0](a, undefined);
		}
		if (name === 'getDownloadURL') {
			files.push(typeof args[0] === 'object' ? args[0].name : args[2]);
			args[args.length - 1]('https://example.org/download', undefined);
		}
		return object();
	}, {get: function (t, p) { return p === TAG ? true : typeof p === 'symbol' ? undefined : call(name + '.' + p); }});
}
var data = {getAsset: function (id, done) {
	return input.assets[id] ? done(input.assets[id]) : done(null, 'Asset ' + id + ' not found');
}};
global.ee = new Proxy({}, {get: function (t, p) { return p === 'data' ? data : call(p); }});
// a ui that draws nothing: each widget keeps its options, its widgets and whether it is greyed out
function Widget(kind, opts) {
	this.kind = kind;
	this.opts = opts || {};
	this.children = [];
	this.disabled = false;
}
Widget.prototype.style = function () { return {set: function () {}}; };
Widget.prototype.add = function (w) { this.children.push(w); };
Widget.prototype.clear = function () { this.children = []; };
Widget.prototype.setDisabled = function (v) { this.disabled = Boolean(v); };
Widget.prototype.getValue = function () { return this.opts.value; };
Widget.prototype.setLayout = function () {};
function widgets() {  // only the panels have widgets (disable in ui.js greys out those of a panel, or the widget)
	var self = this;
	return {forEach: function (f) { self.children.forEach(f); }, reset: function () {}, remove: function () {}};
}
var map = new Widget('Map'), layers = [];
function nothing() {}
var drawing = {setShown: nothing, setLinked: nothing, setDrawModes: nothing, onDraw: nothing, setShape: nothing,
	layers: function () { return {reset: nothing}; }};
map.setOptions = map.setCenter = map.centerObject = map.onClick = function () {};
map.drawingTools = function () { return drawing; };
map.layers = function () { return {remove: function () {}}; };
map.addLayer = function (img, vis, name) { layers.push(name); return {}; };
map.getBounds = function () { return [-3.62, 36.86, -3.50, 36.93]; };
var root = new Widget('root');
root.widgets = widgets;
global.ui = {
	Map: function () { return map; },
	Panel: Object.assign(function (items) {
		var w = new Widget('Panel');
		w.widgets = widgets;
		if (Array.isArray(items)) w.children = items.slice();
		return w;
	}, {Layout: {flow: function () {}}}),
	Label: function (value, style, url) {
		return new Widget('Label', typeof value === 'object' ? value : {value: value, url: url});
	},
	Select: function (o) { return new Widget('Select', o); },
	Textbox: function (o) { return new Widget('Textbox', o); },
	Button: function (o) { return new Widget('Button', o); },
	Checkbox: function (o) { return new Widget('Checkbox', o); },
	Chart: function (table, type, options) { return new Widget('Chart', {table: table, type: type, options: options}); },
	Thumbnail: function (o) { return new Widget('Thumbnail', o); },
	root: root
};
var GEE = process.argv[process.argv.length - 1];
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(GEE, f), 'utf8'), {filename: f});
});
CATALOG.community = input.community;  // those of the package, whatever the catalog.js there is
CATALOG.other_themes = input.other_themes;
vm.runInThisContext(fs.readFileSync(path.join(GEE, 'ui.js'), 'utf8'), {filename: 'ui.js'});

var controls = root.children[0], results = root.children[2], legend = map.children[0];
function all(w, out) {
	out = out || [];
	out.push(w);
	w.children.forEach(function (c) { all(c, out); });
	return out;
}
function find(panel, kind, test) {
	return all(panel).filter(function (w) { return w.kind === kind && (!test || test(w)); });
}
function texts(panel) {
	return find(panel, 'Label').map(function (w) { return w.opts.value; }).filter(function (v) { return v; });
}
function button(label) {
	return find(controls, 'Button', function (w) { return w.opts.label === label; })[0];
}
function selectWith(value) {
	return find(controls, 'Select', function (w) {
		return (w.opts.items || []).some(function (i) { return i.value === value; });
	})[0];
}
function textbox(test) {
	return find(controls, 'Textbox', test)[0];
}
function idBox() {
	return textbox(function (w) { return w.opts.placeholder === 'e.g. IDAHO_EPSCOR/TERRACLIMATE'; });
}
function field(placeholder) {
	return textbox(function (w) { return w.opts.placeholder === placeholder; });
}
function check(label) {
	return find(controls, 'Checkbox', function (w) { return w.opts.label === label; })[0];
}
function read(id, evaluated) {
	idBox().opts.value = id;
	answer = evaluated;
	button('Read').opts.onClick();
}
function last() {  // what the results say: the bold title, the charts and the last message
	var charts = find(results, 'Chart');
	return {texts: texts(results).slice(1), charts: charts.map(function (c) {
		return {type: c.opts.type, title: c.opts.options && c.opts.options.title,
			axis: c.opts.options && c.opts.options.vAxis && c.opts.options.vAxis.title,
			head: c.opts.type === 'Table' ? c.opts.table[0] : null};
	})};
}
function legendTitle() {
	return texts(legend)[0];
}
var out = {};
out.themes = selectWith('earth_engine').opts.items.map(function (i) { return i.value; });
selectWith('earth_engine').opts.onChange('earth_engine');
out.empty = texts(controls);
button('Add to the map').opts.onClick();
out.mapBeforeReading = last();
// a region: the view of the map
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
// TerraClimate, as the Code Editor writes it
read(' ee.ImageCollection("IDAHO_EPSCOR/TERRACLIMATE") ', {bands: ['aet', 'pr'], scales: {aet: 4638.3, pr: 4638.3},
	dated: true});
out.read = {texts: texts(controls), use: selectWith('collection').opts.value,
	useDisabled: selectWith('collection').disabled,
	bands: selectWith('pr').opts.items.map(function (i) { return i.value; }), band: selectWith('pr').opts.value,
	id: idBox().opts.value};
selectWith('pr').opts.onChange('pr');
field('1').opts.onChange('0.5');
field('0').opts.onChange('2');
field('e.g. mm, degC, kg m-2, 1').opts.onChange('mm month-1');
selectWith('pr').opts.onChange('pr');  // the same band: what was written stays
out.sameBand = [field('1').opts.value, field('0').opts.value, field('e.g. mm, degC, kg m-2, 1').opts.value];
selectWith('pr').opts.onChange('aet');  // another band: its own scale, offset and unit, unknown
out.otherBand = [field('1').opts.value, field('0').opts.value, field('e.g. mm, degC, kg m-2, 1').opts.value];
selectWith('pr').opts.onChange('pr');
field('e.g. mm, degC, kg m-2, 1').opts.onChange('mm month-1');
out.filters = ['clouds and shadows', 'water', 'snow', 'aerosols'].map(function (f) {
	return [check(f).opts.value, check(f).disabled];
});
out.controls = texts(controls);
// the map, its GeoTIFF, the time series and its CSV
answer = {value_p5: 2, value_p95: 80};
button('Add to the map').opts.onClick();
out.map = {layer: layers[layers.length - 1], legend: legendTitle(), results: last()};
find(results, 'Button', function (w) { return w.opts.label === 'Download GeoTIFF'; })[0].opts.onClick();
answer = 'rows';
button('Compute the time series').opts.onClick();
out.series = last();
find(results, 'Button', function (w) { return w.opts.label === 'Download CSV'; })[0].opts.onClick();
// the comparison of two periods: its map and its series
check('Compare with another period').opts.onChange(true);
answer = {value_p5: -5, value_p95: 5};
button('Add to the map').opts.onClick();
out.compareMap = {layer: layers[layers.length - 1], results: last()};
answer = 'rows';
button('Compute the time series').opts.onClick();
out.compareSeries = last();
check('Compare with another period').opts.onChange(false);
// the trends of 2015-2025
textbox(function (w) { return w.opts.value === '2025-01-01'; }).opts.onChange('2015-01-01');
answer = 'rows';
button('Trend table').opts.onClick();
out.trendTable = last();
answer = {value_p5: -1, value_p95: 1};
button('Trend map').opts.onClick();
out.trendMap = {layer: layers[layers.length - 1], legend: legendTitle(), results: last()};
// only the pixels above 1500 m
check('a variable is between two values').opts.onChange(true);
answer = {value_p5: 2, value_p95: 80};
button('Add to the map').opts.onClick();
out.where = {layer: layers[layers.length - 1], results: last()};
check('a variable is between two values').opts.onChange(false);
// a scale that is not a number, a unit that is not UDUNITS
field('1').opts.onChange('abc');
button('Add to the map').opts.onClick();
out.badScale = last();
field('1').opts.onChange('0.1');
field('e.g. mm, degC, kg m-2, 1').opts.onChange('m²');
button('Compute the time series').opts.onClick();
out.badUnit = last();
field('e.g. mm, degC, kg m-2, 1').opts.onChange('mm');
// the same collection as a fixed image (the mosaic of its images): no dates
selectWith('image').opts.onChange('image');
out.fixed = {controls: texts(controls), series: button('Compute the time series').disabled,
	trends: [button('Trend table').disabled, button('Trend map').disabled],
	compare: check('Compare with another period').disabled, metric: selectWith('median').disabled};
answer = {value_p5: 2, value_p95: 80};
button('Add to the map').opts.onClick();
out.fixed.layer = layers[layers.length - 1];
out.fixed.legend = legendTitle();
find(results, 'Button', function (w) { return w.opts.label === 'Download GeoTIFF'; })[0].opts.onClick();
button('Compute the time series').opts.onClick();  // greyed out: what if it were not
out.fixed.seriesAnyway = last();
// an image, a table and an ID that is not there
read('WORLDCLIM/V1/BIO', {bands: ['bio01', 'bio12'], scales: {bio01: 927.67, bio12: 927.67}, dated: false});
out.image = {use: selectWith('image').opts.value, disabled: selectWith('image').disabled, texts: texts(controls)};
read('projects/someone/assets/regions', null);
out.table = last();
read('projects/someone/assets/missing', null);
out.missing = last();
// the GEE Community Catalog, in Spanish
button('Español').opts.onClick();
selectWith('community').opts.onChange('community');
out.community = {themes: selectWith('Hydrology').opts.items};
selectWith('Hydrology').opts.onChange('Elevation and Bathymetry');
var datasets = find(controls, 'Select', function (w) {
	return w.opts.placeholder === 'Elige el conjunto de datos';
})[0];
out.community.datasets = datasets.opts.items;
answer = {bands: ['b1'], scales: {b1: 30}, dated: false};
datasets.opts.onChange('projects/sat-io/open-datasets/FABDEM');
out.community.id = find(controls, 'Textbox', function (w) {
	return w.opts.placeholder === 'p. ej. IDAHO_EPSCOR/TERRACLIMATE';
})[0].opts.value;
out.community.texts = texts(controls);
out.community.page = find(controls, 'Label', function (w) {
	return w.opts.value === 'Página del conjunto de datos';
}).map(function (w) { return w.opts.url; });
out.community.use = selectWith('image').opts.value;
// back to a variable of the catalog
button('English').opts.onClick();
selectWith('vegetation').opts.onChange('vegetation');
out.back = {variables: Boolean(selectWith(27)), clouds: [check('clouds and shadows').opts.value,
	check('clouds and shadows').disabled]};
out.files = files;
process.stdout.write(JSON.stringify(out));
"""


def test_the_panel_of_the_app_computes_the_data_of_earth_engine():
	"""The data read feed the maps, series, trends and comparisons of the variables, named by their ID and band and
	with their unit, without pixel filters; as a fixed image they have only the map; each band has its own scale,
	offset and unit; the errors are those of the package."""
	if not shutil.which('node'):
		pytest.skip('no Node')
	with open(os.path.join(GEE, 'ui.js'), encoding='utf-8') as f:
		en = _ui_texts(f.read(), 'en')
	data = {'community': _build().community_index(), 'other_themes': catalog.OTHER_THEMES, 'assets': {
		'IDAHO_EPSCOR/TERRACLIMATE': {'type': 'IMAGE_COLLECTION', 'properties': {'title': 'TerraClimate'}},
		'WORLDCLIM/V1/BIO': {'type': 'IMAGE', 'properties': {}},
		'projects/sat-io/open-datasets/FABDEM': {'type': 'IMAGE_COLLECTION', 'properties': {}},
		'projects/someone/assets/regions': {'type': 'TABLE'}}}
	run = subprocess.run(['node', '-e', PANEL, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	assert out['themes'] == [t['key'] for t in catalog.THEMES] + ['earth_engine', 'community', 'all']
	assert en['readFirst'] in out['empty'] and out['mapBeforeReading']['texts'] == [en['readFirst']]
	# what was read: a collection with dates, its bands and its source
	read = out['read']
	assert (read['id'], read['use'], read['useDisabled'], read['bands'], read['band']) == \
		('IDAHO_EPSCOR/TERRACLIMATE', 'collection', False, ['aet', 'pr'], 'aet')  # the first band, as describe_asset
	assert f"TerraClimate · {en['src_data']} · {en['type_image_collection']} · {en['licenceInPage']}" in read['texts']
	assert out['sameBand'] == ['0.5', '2', 'mm month-1'] and out['otherBand'] == ['', '', '']
	assert out['filters'] == [[False, True]] * 4  # no pixel filters: greyed out, off
	assert any(t.startswith(en['customFilters']) for t in out['controls'])
	# the map, the series, the comparison and the trends: named by the ID and the band, with the unit given
	name = 'IDAHO_EPSCOR/TERRACLIMATE pr · Map view'
	assert out['map']['layer'] == f'{name} · Median · 2025-01-01/2025-12-31'
	assert out['map']['legend'] == out['map']['layer'] + ' [mm month-1]'
	series, = out['series']['charts']
	assert series['title'].startswith(name) and series['axis'] == '[mm month-1]'
	assert out['compareMap']['layer'] == f'{name} · Median · 2020-01-01/2020-12-31 − 2025-01-01/2025-12-31'
	assert out['compareSeries']['charts'][0]['axis'] == '[mm month-1]'
	table = out['trendTable']['charts'][0]
	assert table['type'] == 'Table' and table['head'][-1] == 'Sen ([mm month-1]/year)'
	assert out['trendMap']['legend'].endswith('[mm month-1] / year')
	assert out['where']['layer'].startswith(f'{name} (ELEVATION ≥ 1500 [m])')
	# the errors of what was written, as the package says them
	assert out['badScale']['texts'] == ['Band scale: "abc" is not a number.']
	with pytest.raises(ValueError) as error:
		services.make_spec(None, None, '2025-01-01', '2025-12-31', collection='IDAHO_EPSCOR/TERRACLIMATE', band='pr',
		                   unit='m²')
	assert out['badUnit']['texts'] == [str(error.value)]
	# as a fixed image (the mosaic of its images): only the map, without dates
	fixed = out['fixed']
	assert fixed['series'] and fixed['trends'] == [True, True] and fixed['compare'] and fixed['metric']
	assert any(t.startswith(en['staticNote']) for t in fixed['controls'])
	assert fixed['layer'] == name and fixed['legend'] == name + ' [mm]'
	with pytest.raises(ValueError) as error:
		variable.check_dates(services.make_spec(image='IDAHO_EPSCOR/TERRACLIMATE', band='pr'))
	assert fixed['seriesAnyway']['texts'] == [str(error.value)]
	assert out['files'] == ['TERRACLIMATE_pr_Map_view_Median_2025-01-01_2025-12-31',
	                        'TERRACLIMATE_pr_Map_view_Mean_monthly_mean', 'TERRACLIMATE_pr_Map_view']
	# an image is only a fixed image; a table and an ID that is not there say so
	assert out['image']['use'] == 'image' and out['image']['disabled']
	assert out['table']['texts'][0].startswith('projects/someone/assets/regions is a table (ee.FeatureCollection)')
	assert out['missing']['texts'][0].startswith('Earth Engine has no image or collection projects/someone/assets/'
	                                             'missing, or this app cannot read it')
	# the GEE Community Catalog, in Spanish: its themes and datasets, and the one chosen read
	com = out['community']
	assert com['themes'] == [{'value': t['theme'], 'label': f"{t['name']} ({t['datasets']})"}
	                         for t in community.themes('es')]
	kinds = {'image_collection': 'colección', 'image': 'imagen'}
	assert com['datasets'] == [{'value': d['id'], 'label': f"{d['title']} · {kinds[d['type']]}"}
	                           for d in community.datasets('Elevation and Bathymetry')]
	rec = community.record('projects/sat-io/open-datasets/FABDEM')
	assert com['id'] == rec['id'] and com['page'] == [rec['docs']] and com['use'] == 'image'
	assert any(rec['title'] in t and 'Catálogo de la comunidad de GEE' in t and rec['license'] in t
	           for t in com['texts'])
	# back to a variable of the catalog, with its pixel filters
	assert out['back'] == {'variables': True, 'clouds': [True, False]}
