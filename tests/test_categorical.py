"""The categorical layers (monitoreo.categorical: the ecoregions and biomes of RESOLVE Ecoregions 2017, ECOREGION and
BIOME of sensor RESOLVE), without Earth Engine: their table of classes, their entries and theme, the module, the images
that the package asks Earth Engine for (a fake ee), the conditions of where, the zones and the areas by class, the
statistics of a region, the maps and GeoTIFFs with the legend of their classes, the READMEs, reports and the viewer,
their references, the command line, the MCP server, the assistant, and the same answers and calls of Earth Engine in
the app (gee/core.js in Node). tests/test_gee.py computes them in Earth Engine."""

import asyncio
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

from monitoreo import catalog, categorical, classes, cli, publish, references, report, services, variable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEE = os.path.join(ROOT, 'gee')
REGION = {'bbox': [-3.45, 37.02, -3.30, 37.12]}
MEDITERRANEAN = {'variable': 'BIOME', 'sensor': 'RESOLVE', 'classes': [12]}
NOT_793 = {'variable': 'ECOREGION', 'sensor': 'RESOLVE', 'exclude': [793]}
ECO, BIO = catalog.find('ECOREGION', 'RESOLVE'), catalog.find('BIOME', 'RESOLVE')


# The tables of classes and the entries ---------------------------------------------------------------------------

def test_the_tables_of_classes():
	"""847 ecoregions (ECO_ID 0 to 846, Rock and Ice the 0) and 15 biome classes (the 14 of the data and Rock and Ice, 99,
	a code of MonitorEO), every ecoregion in a biome of the table, with their names (accents kept) and colours."""
	eco, bio = categorical.table('ecoregions'), categorical.table('biomes')
	assert len(eco['classes']) == 847 and sorted(map(int, eco['classes'])) == list(range(847))
	assert len(bio['classes']) == 15 and sorted(map(int, bio['classes'])) == list(range(1, 15)) + [99]
	assert eco['fields'] == ['name', 'colour', 'group'] and eco['group'] == 'biomes' and eco['property'] == 'ECO_ID'
	assert bio['fields'] == ['name', 'colour', 'name_es'] and bio['property'] == 'BIOME_NUM'
	for code, (name, colour, biome) in eco['classes'].items():
		assert name and name == name.strip() and re.fullmatch(r'[0-9a-f]{6}', colour), code
		assert str(biome) in bio['classes'], code  # every ecoregion's biome is in the table of the biomes
	for code, (name, colour, name_es) in bio['classes'].items():
		assert name and name_es and re.fullmatch(r'[0-9a-f]{6}', colour), code
	assert eco['classes']['0'] == ['Rock and Ice', 'e2e2e0', 99]
	assert bio['classes']['99'] == ['Rock and Ice', 'ffeaaf', 'Roca y hielo']
	assert eco['classes']['316'][2] == 13  # Godavari-Krishna mangroves: in the Deserts, as in the data
	assert eco['classes']['27'][0] == 'São Tomé, Príncipe, and Annobón forests'  # UTF-8 accents
	assert bio['classes']['12'] == ['Mediterranean Forests, Woodlands & Scrub', 'fe0000',
	                                'Bosques, bosques abiertos y matorrales mediterráneos']
	counts = {}
	for _, _, biome in eco['classes'].values():
		counts[biome] = counts.get(biome, 0) + 1
	assert counts[1] == 230 and counts[7] == 58 and counts[13] == 102 and counts[14] == 19 and counts[99] == 1
	assert 'Rock and Ice' in bio['notes'] and '99' in bio['notes'] and '316' in bio['notes']


def test_the_helpers_of_the_biomes():
	"""catalog.biomes and catalog.ecoregions_of_biome (for a biome as a region: the polygons of its ecoregions)."""
	b = catalog.biomes()
	assert [x['code'] for x in b] == list(range(1, 15)) + [99] and b[11]['name'].startswith('Mediterranean')
	assert catalog.biomes('es')[-1] == {'code': 99, 'name': 'Roca y hielo', 'colour': 'ffeaaf'}
	assert catalog.ecoregions_of_biome(99) == [0] and 0 not in catalog.ecoregions_of_biome(11)
	assert len(catalog.ecoregions_of_biome(12)) == 40 and 805 in catalog.ecoregions_of_biome(12)
	assert 316 in catalog.ecoregions_of_biome(13)  # as in the data
	assert sum(len(catalog.ecoregions_of_biome(x['code'])) for x in b) == 847
	assert catalog.classes_table('biomes') is catalog.load()['classes']['biomes']


def test_the_entries_and_their_theme():
	assert (ECO['ref'], BIO['ref']) == (149, 150)
	for e, key, band in ((ECO, 'ecoregions', 'ECO_ID'), (BIO, 'biomes', 'BIOME_NUM')):
		assert (e['sensor'], e['col'], e['m'], e['tr'], e['unit'], e['classes'], e['band']) == (
			'RESOLVE', 'RESOLVE/ECOREGIONS/2017', 1000, 'fixed', '[class]', key, band)
		assert e['static'] and e['large_areas'] and e['references'] == ['dinerstein2017'] and e['theme'] == 'ecosystems'
		assert e['type'] == 'Ecosistemas' and e['type_en'] == 'Ecosystems' and e['dr'].startswith('fixed layer')
		assert 'Rock and Ice' in e['notes']['ft'] and 'mode' in e['notes']['ft'] and 'class codes' in e['notes']['ft']
		assert catalog.udunits(e['unit']) == '' and e['unit'] in catalog.NO_UDUNITS
		assert categorical.is_categorical(e) and not categorical.is_categorical(catalog.find('ELEVATION', 'Copernicus'))
	assert (ECO['vname'], ECO['vname_en'], BIO['vname'], BIO['vname_en']) == ('Ecorregión', 'Ecoregion', 'Bioma', 'Biome')
	assert catalog.find('biome', 'resolve')['ref'] == 150 and catalog.find('ECOREGION')['ref'] == 149
	assert {v['variable'] for v in services.list_variables(theme='ecosystems')} == {'ECOREGION', 'BIOME'}
	assert services.list_variables(theme='Ecosistemas', lang='es')[0]['theme'] == 'Ecosistemas'
	rows = {r['variable']: r for r in services.list_variables(sensor='RESOLVE')}
	assert rows['BIOME']['categorical'] and rows['BIOME']['n_classes'] == 15 and rows['ECOREGION']['n_classes'] == 847
	assert 'categorical' not in services.list_variables(text='NDVI')[0]
	d = services.describe_variable('BIOME', 'RESOLVE')
	assert d['categorical'] and len(d['classes']) == 15 and d['classes'][-1] == {'code': 99, 'name': 'Rock and Ice',
	                                                                            'colour': 'ffeaaf'}
	d = services.describe_variable('ECOREGION', 'RESOLVE')
	assert d['n_classes'] == 847 and 'classes' not in d and 'list_classes' in d['classes_note']
	assert catalog.load()['datasets']['RESOLVE/ECOREGIONS/2017']['credit'] == \
		'Ecoregions2017 © Resolve, CC BY 4.0, rasterized by MonitorEO'
	assert 'classes' in catalog.load()['fields'] and 'RESOLVE' in catalog.load()['fields']['sensor']


# The module, without Earth Engine ----------------------------------------------------------------------------------

def test_labels_colours_legends_and_visualizations():
	assert categorical.label(BIO, 12) == '12 Mediterranean Forests, Woodlands & Scrub'
	assert categorical.label(BIO, 12, 'es') == '12 Bosques, bosques abiertos y matorrales mediterráneos'
	assert categorical.label(ECO, 0) == '0 Rock and Ice' and categorical.colour(BIO, 99) == 'ffeaaf'
	assert categorical.group_of(ECO, 805) == 12 and categorical.group_entry(ECO)['ref'] == 150
	assert categorical.group_entry(BIO) is None and categorical.colour(BIO, 50) == categorical.GAP
	assert categorical.legend(BIO, [13, 12, 12]) == [
		{'value': 12, 'label': '12 Mediterranean Forests, Woodlands & Scrub', 'color': '#fe0000'},
		{'value': 13, 'label': '13 Deserts & Xeric Shrublands', 'color': '#cc6767'}]
	assert len(categorical.legend(ECO)) == 847 and categorical.legend(ECO, []) == []
	# a palette by code from the lowest to the highest: each code gets the colour of its class (grey where none is)
	vis = categorical.vis(BIO, [14, 99])
	assert (vis['min'], vis['max'], len(vis['palette'])) == (14, 99, 86)
	assert vis['palette'][0] == 'fe01c4' and vis['palette'][-1] == 'ffeaaf' and vis['palette'][1] == categorical.GAP
	assert categorical.vis(BIO, [12]) == {'min': 12, 'max': 13, 'palette': ['fe0000', 'fe0000']}
	assert categorical.vis(ECO)['min'] == 0 and len(categorical.vis(ECO)['palette']) == 847


def test_finding_and_checking_classes():
	iberian = categorical.find(ECO, 'iberian')
	assert [c['code'] for c in iberian] == [792, 793, 800, 803, 805] and all(c['group'] == 12 for c in iberian)
	assert all('Siberian' not in c['name'] for c in iberian)  # at the start of a word
	assert [c['code'] for c in categorical.find(ECO, 'paramo', 2)] == [590, 591]  # without accents
	assert [c['code'] for c in categorical.find(BIO, 'mediterráneos')] == [12]  # the Spanish names too
	assert len(categorical.find(ECO, 'Mediterranean Forests')) >= 40  # the name of the biome
	assert categorical.check(BIO, [12, '4', 12.0, ' 99 ']) == [12, 4, 99] and categorical.check(BIO, '12, 4') == [12, 4]
	for values, message in (([], r'the classes of BIOME \(RESOLVE\) are a list of codes'), ('', 'a list of codes'),
	                        ([15, 98], r'BIOME \(RESOLVE\) has no classes 15, 98: list_classes'),
	                        (['12.5'], "whole numbers, e.g. \\[12\\]; not '12.5'"), ([1.5], 'not 1.5')):
		with pytest.raises(ValueError, match=message):
			categorical.check(BIO, values)


def test_the_options_that_would_mix_classes():
	for kw, message in (({'resample': 'bilinear'}, 'resample takes auto or nearest, not bilinear'),
	                    ({'resample': 'bicubic'}, 'not bicubic'),
	                    ({'aggregate': 'mean'}, 'aggregate takes auto, mode or none, not mean')):
		with pytest.raises(ValueError, match=message):
			variable.specs(dict({'index': 'BIOME', 'sensor': 'RESOLVE'}, **kw))
	for kw in ({'resample': 'nearest'}, {'aggregate': 'mode'}, {'aggregate': 'none'}):
		assert variable.specs(dict({'index': 'BIOME', 'sensor': 'RESOLVE'}, **kw))[0]['metric'] is None
	spec = services.make_spec('ECOREGION', 'RESOLVE', '2020-01-01', '2020-12-31', metric='mean')
	assert spec['metric'] is None and spec['name'] == 'ECOREGION_RESOLVE'
	assert variable.is_static(spec) and variable.is_categorical(spec)
	assert not variable.is_categorical(services.make_spec('ELEVATION', 'Copernicus'))
	with pytest.raises(ValueError, match='is a fixed layer, without dates'):
		variable.check_dates(spec)
	d = variable.describe(spec)
	assert (d['unit'], d['udunits'], d['categorical'], d['classes'], d['property']) == (
		'[class]', '', True, 'ecoregions', 'ECO_ID') and 'period' not in d


def test_the_statistics_of_a_categorical_layer():
	categorical.check_stats(BIO, ['mode', 'count', 'MODE'])
	for s in ('mean', 'std', 'cv', 'p95', 'median'):
		with pytest.raises(ValueError, match=f'BIOME \\(RESOLVE\\) is a categorical layer: its statistic over a region '
		                                     f'is the majority class \\(mode\\), not {s}; for the area of each class'):
			services.region_stats(REGION, 'BIOME', 'RESOLVE', stats=[s])
	with pytest.raises(ValueError, match='no profile along a line'):
		services.transect([[-3.4, 37.0], [-3.3, 37.1]], 'ECOREGION', 'RESOLVE')


# The images asked for (a fake ee) -----------------------------------------------------------------------------------

def _fake(monkeypatch):
	"""The calls of Earth Engine of the package, logged by a fake ee (that of tests/test_themes.py) in variable and in
	the lazy imports of categorical."""
	from test_themes import _Obj, _Root
	rec = []
	monkeypatch.setattr(variable, 'ee', _Root(rec))
	monkeypatch.setitem(sys.modules, 'ee', _Root(rec))
	return rec, _Obj(rec)


def test_the_polygons_are_rasterized_once_and_never_interpolated(monkeypatch):
	rec, region = _fake(monkeypatch)
	monkeypatch.setattr(variable, '_static_spec', lambda spec: pytest.fail('a categorical layer is no image'))
	monkeypatch.setattr(variable, '_fixed', lambda spec, res: pytest.fail('a categorical layer is no image'))
	variable.image(services.make_spec('ECOREGION', 'RESOLVE'), region, 1000)
	assert rec[:4] == [['FeatureCollection', 'RESOLVE/ECOREGIONS/2017'], ['Reducer.first'],
	                   ['reduceToImage', ['ECO_ID'], '<ee>'], ['toInt']]
	assert rec[4:] == [['toInt'], ['rename', 'value']]  # at its own pixel: no mode, no resample
	rec.clear()
	variable.image(services.make_spec('BIOME', 'RESOLVE'), region, 5000)  # pixels more than twice m: the majority class
	ids = list(range(847))
	assert rec[4] == ['remap', ids, [categorical.group_of(ECO, i) for i in ids]]  # the biome from the ECO_ID
	assert rec[5:] == [['Projection', 'EPSG:4326'], ['atScale', 1000.0], ['setDefaultProjection', '<ee>'],
	                   ['Reducer.mode'], ['reduceResolution', '<ee>', False, 65535], ['toInt'], ['rename', 'value']]
	assert rec[4][2][0] == 99  # Rock and Ice
	rec.clear()
	variable.image(services.make_spec('BIOME', 'RESOLVE', where=None) | {'aggregate': 'none'}, region, 5000)
	assert ['Reducer.mode'] not in rec and ['Reducer.mean'] not in rec


def test_the_mask_of_a_condition_on_classes(monkeypatch):
	rec, region = _fake(monkeypatch)
	categorical.keep(BIO, [12], True, 5000)
	assert rec[-11:] == [['remap', [12], [1], 0], ['Projection', 'EPSG:4326'], ['atScale', 1000.0],
	                     ['setDefaultProjection', '<ee>'], ['Reducer.mean'], ['reduceResolution', '<ee>', True, 65535],
	                     ['Image', 1], ['mask'], ['updateMask', '<ee>'], ['gte', categorical.SHARE], ['And', '<ee>']]
	rec.clear()
	categorical.keep(ECO, [793, 805], False, 1000)  # at its own pixel: the class of the pixel
	assert ['Reducer.mean'] not in rec and rec[-2:] == [['lt', 0.5], ['And', '<ee>']]
	assert ['remap', [793, 805], [1, 1], 0] in rec


# The conditions of where ---------------------------------------------------------------------------------------------

def ndvi(*where):
	return services.make_spec('NDVI', 'Sentinel-2', '2020-01-01', '2021-12-31', where=list(where))


def test_conditions_on_classes():
	spec = ndvi(MEDITERRANEAN, NOT_793, {'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 1500})
	assert [(e['index'], codes, kept) for e, codes, kept in variable.class_conditions(spec)] == [
		('BIOME', [12], True), ('ECOREGION', [793], False)]
	assert [s['index'] for s, _, _ in variable.where_specs(spec)] == ['ELEVATION']  # those with min and max only
	pinned = variable.pin_where(spec['where'], '2020-01-01', '2020-12-31')  # the maps of each step: the same classes
	assert [(e['index'], codes) for e, codes, _ in variable.class_conditions(dict(spec, where=pinned))] == [
		('BIOME', [12]), ('ECOREGION', [793])]
	text = report.where_text([MEDITERRANEAN, NOT_793])
	assert text == ('BIOME (RESOLVE) is 12 Mediterranean Forests, Woodlands & Scrub; ECOREGION (RESOLVE) is not 793 '
	                'Iberian sclerophyllous and semi-deciduous forests')
	assert categorical.text({'variable': 'BIOME', 'sensor': 'RESOLVE', 'classes': [12, 4, 5]}, 'es') == \
		'BIOME (RESOLVE) es 12 Bosques, bosques abiertos y matorrales mediterráneos, 4 Bosques templados de hoja ' \
		'ancha y mixtos o 5 Bosques templados de coníferas'
	# a fixed layer filtered by classes, with no period
	assert variable.class_conditions(services.make_spec('ELEVATION', 'Copernicus', where=[MEDITERRANEAN]))


@pytest.mark.parametrize('condition, message', [
	(dict(MEDITERRANEAN, min=3), r'BIOME \(RESOLVE\) is a categorical layer, whose values are class codes: a condition '
	                             r'on it takes classes \(the classes to keep\) or exclude \(those to leave out\), not '
	                             r'min or max'),
	({'variable': 'ELEVATION', 'sensor': 'Copernicus', 'classes': [1]},
	 r'classes and exclude are for a categorical layer \(ECOREGION, BIOME\): ELEVATION \(Copernicus\) takes min and max'),
	(dict(MEDITERRANEAN, exclude=[4]), 'the condition on BIOME of where takes classes or exclude, not both'),
	({'variable': 'BIOME', 'sensor': 'RESOLVE'}, r'the condition on BIOME of where needs classes \(the classes to keep\) '
	                                             r'or exclude \(those to leave out\), e.g. \{"variable": "BIOME"'),
	(dict(MEDITERRANEAN, classes=[]), r'the classes of BIOME \(RESOLVE\) are a list of codes of its classes'),
	(dict(NOT_793, exclude=[900]), r'ECOREGION \(RESOLVE\) has no classes 900'),
	(dict(MEDITERRANEAN, above=1), 'unknown keys above'),
])
def test_wrong_conditions_on_classes(condition, message):
	with pytest.raises(ValueError, match=message):
		ndvi(condition)


def test_the_conditions_are_cited():
	cited = references.cite('map_layer', {'region': REGION, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
	                                      'where': [MEDITERRANEAN]})
	ids = [r['id'] for r in cited['references']]
	assert 'dinerstein2017' in ids and 'Ecoregions2017 © Resolve, CC BY 4.0, rasterized by MonitorEO' in cited['credits']


# Zones, areas and statistics with the services faked ---------------------------------------------------------------

class _Result:
	def __init__(self, info):
		self.info = info

	def getInfo(self):
		return self.info


class _Image:
	"""An image of the fake services: what reduceRegions answers is INFO; its bands, those added."""

	def __init__(self, info=None, log=None):
		self.info, self.log = info, log if log is not None else []

	def __getattr__(self, name):
		if name.startswith('__'):
			raise AttributeError(name)

		def method(*args, **kwargs):
			self.log.append((name, args, kwargs))
			if name == 'reduceRegions':
				return _Result(self.info)
			return self
		return method


def _services(monkeypatch, info, log):
	"""region_stats and area_by_class with Earth Engine faked: _build gives an image that answers INFO."""
	def build(region, var_name, sensor, start, end, metric, temporal, interannual, season, quality, clip, res, source,
	          rgb=False):
		spec = services.make_spec(var_name, sensor, start, end, metric=metric or 'mean', **source)
		return spec, _Image(log=log), _Image(info, log), res or 1000.0

	monkeypatch.setattr(services, '_build', build)
	monkeypatch.setattr(services.timeseries, 'auto_scale', lambda spec, regions: 1000.0)
	monkeypatch.setattr(services.timeseries, 'region_crs', lambda regions: 'EPSG:32630')
	monkeypatch.setattr(services.composite, 'region_reducer', lambda stats: (
		_Image(log=log), {s: {'mean': 'mean', 'mode': 'mode', 'p50': 'p50'}.get(s, s) for s in stats if s != 'count'}))


def test_the_majority_class_of_a_region(monkeypatch, tmp_path):
	log = []
	_services(monkeypatch, {'features': [{'properties': {'name': 'park', 'mode': 12.0, 'count': 300}},
	                                     {'properties': {'name': 'sea', 'count': 0}}]}, log)
	res = services.region_stats(REGION, 'BIOME', 'RESOLVE', csv=str(tmp_path / 'stats.csv'))
	assert res['stats'] == ['mode'] and res['unit'] == '[class]' and 'ylabel' not in res
	assert res['rows'][0] == {'region': 'park', 'mode': 12, 'n_pixels': 300,
	                          'mode_label': '12 Mediterranean Forests, Woodlands & Scrub'}
	assert res['rows'][1]['mode'] is None and res['rows'][1]['mode_label'] is None
	header = open(res['csv'], encoding='utf-8').readline().strip().split(',')
	assert header[:4] == ['region', 'mode', 'mode_label', 'n_pixels'] and 'unit' in header
	text = open(res['readme'], encoding='utf-8').read()
	assert '\nVALUES\n' in text and 'class codes, not quantities' in text and '\nUNITS\n' not in text
	assert 'mode_label: the majority class: its code and name' in text
	facts = dict(report.item_facts('region_stats', {'region': REGION, 'variable': 'BIOME', 'sensor': 'RESOLVE'}, res))
	assert facts['Statistic'].startswith('the majority class') and facts['Method'] == report.METHODS['region_stats_categorical']
	labels, rows = report.item_table('region_stats', res)
	assert labels == ['Region', 'Majority class', 'Pixels'] and rows[0][1] == '12 Mediterranean Forests, Woodlands & Scrub'


def test_zones_by_class(monkeypatch, tmp_path):
	"""The zones of a categorical layer: its classes with pixels in each feature, without breaks; only those given."""
	log = []
	groups = [{'zone': 13.0, 'p50': 0.2, 'count': 10}, {'zone': 12.0, 'p50': 0.4, 'count': 50}]
	_services(monkeypatch, {'features': [{'properties': {'name': 'park', 'groups': groups}}]}, log)
	zone = _Image(log=log)
	monkeypatch.setattr(services.variables, 'image', lambda spec, region, scale: zone)
	zones = {'variable': 'BIOME', 'sensor': 'RESOLVE'}
	res = services.region_stats(REGION, 'NDVI', 'Modis', '2023-06-01', '2023-08-31', stats=['p50'], zones=zones,
	                            csv=str(tmp_path / 'zones.csv'))
	assert [(r['zone'], r['zone_label'], r['p50'], r['n_pixels']) for r in res['rows']] == [
		(12, '12 Mediterranean Forests, Woodlands & Scrub', 0.4, 50), (13, '13 Deserts & Xeric Shrublands', 0.2, 10)]
	assert res['rows'][0]['zone_from'] is None and res['title'].endswith('by BIOME (RESOLVE) classes')
	assert ('rename', ('zone',), {}) in log and not any(name == 'remap' for name, _, _ in log)
	log.clear()
	services.region_stats(REGION, 'NDVI', 'Modis', '2023-06-01', '2023-08-31', stats=['p50'],
	                      zones=dict(zones, classes=[12]))
	assert ('remap', ([12], [12]), {}) in log  # only those classes
	assert services.zones_of(zones) == {'classes': None} and services.zone_name(zones) == 'BIOME (RESOLVE) classes'
	assert services.zone_name({'variable': 'ELEVATION', 'sensor': 'Copernicus', 'breaks': [1]}) == \
		'ELEVATION (Copernicus) bands'
	for z, message in ((dict(zones, breaks=[3]), r'the zones of BIOME \(RESOLVE\) are its classes'),
	                   ({'variable': 'ELEVATION', 'sensor': 'Copernicus', 'classes': [1]}, 'classes are for the zones of'),
	                   (dict(zones, classes=[50]), r'BIOME \(RESOLVE\) has no classes 50')):
		with pytest.raises(ValueError, match=message):
			services.zones_of(z)
	text = open(res['readme'], encoding='utf-8').read()
	assert 'zone: zone: the code of its class' in text
	facts = dict(report.item_facts('region_stats', {'region': REGION, 'variable': 'NDVI', 'sensor': 'Modis',
	                                                'zones': zones}, res))
	assert facts['Zones'] == 'BIOME (RESOLVE) classes: each class a zone, those with pixels in each feature'
	cited = references.cite('region_stats', {'region': REGION, 'variable': 'NDVI', 'sensor': 'Modis', 'zones': zones})
	assert 'dinerstein2017' in [r['id'] for r in cited['references']]


def test_the_area_of_each_class(monkeypatch, tmp_path):
	"""area_by_class of a categorical layer: the classes with area in some feature, with the colours of the table, the
	ecoregions with their biome and the hectares of each biome; breaks and trend refused."""
	log = []
	_services(monkeypatch, None, log)
	monkeypatch.setattr(services.classes, 'scale_for', lambda native, regions: 1000.0)
	monkeypatch.setattr(services.classes, 'hectares', lambda img, regions, res, crs: [
		('park', {805: 300.0, 793: 100.0, 1: 0.0}), ('other', {805: 50.0})])
	res = services.area_by_class(REGION, 'ECOREGION', 'RESOLVE', csv=str(tmp_path / 'areas.csv'))
	assert res['mode'] == 'classes' and res['unit'] == '' and res['title'] == 'Area of each class of ECOREGION RESOLVE'
	assert res['classes'] == [{'class': 793, 'label': '793 Iberian sclerophyllous and semi-deciduous forests',
	                           'colour': 'e54c00'},
	                          {'class': 805, 'label': '805 Southwest Iberian Mediterranean sclerophyllous and mixed forests',
	                           'colour': 'a80000'}]
	assert [(r['region'], r['class'], r['ha'], r['percent'], r['group']) for r in res['rows']] == [
		('park', 793, 100.0, 25.0, 12), ('park', 805, 300.0, 75.0, 12), ('other', 793, 0.0, 0.0, 12),
		('other', 805, 50.0, 100.0, 12)]
	assert res['rows'][0]['group_label'] == '12 Mediterranean Forests, Woodlands & Scrub'
	assert res['by_group'] == [{'region': 'park', 'group': 12, 'label': '12 Mediterranean Forests, Woodlands & Scrub',
	                            'ha': 400.0, 'percent': 100.0},
	                           {'region': 'other', 'group': 12, 'label': '12 Mediterranean Forests, Woodlands & Scrub',
	                            'ha': 50.0, 'percent': 100.0}]
	assert open(res['csv'], encoding='utf-8').readline().startswith(
		'region,class,label,group,group_label,ha,percent')
	for kw, message in (({'breaks': [3]}, r'the classes of ECOREGION \(RESOLVE\) are its own .*give no breaks'),
	                    ({'trend': True}, 'give no trend')):
		with pytest.raises(ValueError, match=message):
			services.area_by_class(REGION, 'ECOREGION', 'RESOLVE', **kw)
	facts = dict(report.item_facts('area_by_class', {'region': REGION, 'variable': 'ECOREGION', 'sensor': 'RESOLVE'},
	                               res))
	assert facts['Method'] == report.METHODS['area_by_class_classes']
	labels, rows = report.item_table('area_by_class', res)
	assert 'Biome' in labels
	assert publish._area_classes({'variable': 'ECOREGION', 'sensor': 'RESOLVE'}, res['csv']) == res['classes']


def test_the_area_of_each_biome(monkeypatch):
	_services(monkeypatch, None, [])
	monkeypatch.setattr(services.classes, 'scale_for', lambda native, regions: 1000.0)
	monkeypatch.setattr(services.classes, 'hectares', lambda img, regions, res, crs: [('park', {13: 5.0, 12: 15.0})])
	res = services.area_by_class(REGION, 'BIOME', 'RESOLVE')
	assert 'by_group' not in res and [c['class'] for c in res['classes']] == [12, 13]
	assert 'group' not in res['rows'][0] and res['classes'][0]['colour'] == 'fe0000'


# Maps and GeoTIFFs: the legend of their classes ----------------------------------------------------------------------

def test_the_map_of_a_categorical_layer(monkeypatch):
	_services(monkeypatch, None, [])
	got = {}
	monkeypatch.setattr(services.categorical, 'present', lambda entry, geom: [13, 12])
	monkeypatch.setattr(services.maps, 'tile_url', lambda img, vis: got.setdefault('vis', vis) and 'https://tiles')
	monkeypatch.setattr(services, '_bounds', lambda regions: [-3.45, 37.02, -3.30, 37.12])
	res = services.map_layer(REGION, 'BIOME', 'RESOLVE')
	assert got['vis'] == {'min': 12, 'max': 13, 'palette': ['fe0000', 'cc6767']}
	assert (res['url'], res['min'], res['max'], res['palette'], res['unit']) == ('https://tiles', None, None, None,
	                                                                            '[class]')
	assert res['classes'] == categorical.legend(BIO, [12, 13]) and res['name'] == 'BIOME RESOLVE'
	assert report.map_style('map_layer', {}, res) == {'band': 1, 'classes': res['classes']}
	assert report.map_style('area_by_class', {}, {'classes': [{'class': 1, 'label': 'a', 'colour': 'ffffff'}]}) is None
	assert report.class_label(res['classes'][0]) == '12 Mediterranean Forests, Woodlands & Scrub'  # no «(dNBR ...)»
	assert report.class_label(services.fire.legend()[0]).endswith(')')  # the burn severity, with its values
	facts = dict(report.item_facts('map_layer', {'region': REGION, 'variable': 'BIOME', 'sensor': 'RESOLVE'}, res))
	assert facts['Classes'].startswith('2 in the map: 12 Mediterranean') and facts['Method'] == report.METHODS['categorical']
	assert publish.unit_text('[class]') == '' and services.unit_text_of('[class]') == ''


def test_the_geotiff_of_a_categorical_layer(tmp_path):
	"""The classes in the GeoTIFF instead of its percentiles, its README with them, its metadata and its band without a
	unit, and its categories in the viewer."""
	gdal_ = pytest.importorskip('osgeo.gdal')
	np = pytest.importorskip('numpy')
	gdal_.UseExceptions()
	path = str(tmp_path / 'BIOME_RESOLVE.tif')
	ds = gdal_.GetDriverByName('GTiff').Create(path, 3, 2, 1, gdal_.GDT_Float32)
	ds.SetGeoTransform([450000, 1000, 0, 4110000, 0, -1000])
	ds.SetProjection('EPSG:32630')
	ds.GetRasterBand(1).WriteArray(np.array([[12, 12, 13], [-9999, 99, 12]], dtype='float32'))
	ds.GetRasterBand(1).SetNoDataValue(-9999)
	ds = None
	assert services._values(path) == [12, 13, 99]

	def download_image(region, variable=None, sensor=None, start=None, end=None, metric='median', path=None,
	                   progress=None, **source):
		return {'file': path, 'unit': '[class]', 'images': None, 'min': None, 'max': None, 'palette': None,
		        'classes': categorical.legend(BIO, services._values(path)), 'resolution': 1000,
		        'native_resolution': 1000, 'name': 'BIOME RESOLVE'}

	out = services._cited(download_image)(REGION, 'BIOME', 'RESOLVE', path=path)
	text = ' '.join(open(out['readme'], encoding='utf-8').read().split())
	assert 'CLASSES OF BIOME_RESOLVE.tif' in text and '99 Rock and Ice (colour #ffeaaf)' in text
	assert '1 value: Class of each pixel: its code (BIOME_NUM of RESOLVE/ECOREGIONS/2017), without a unit' in text
	assert 'Ecoregions2017 © Resolve, CC BY 4.0, rasterized by MonitorEO' in text and 'Dinerstein' in text
	ds = gdal_.Open(path)
	assert json.loads(ds.GetMetadataItem('classes'))['12'] == '12 Mediterranean Forests, Woodlands & Scrub'
	assert ds.GetRasterBand(1).GetUnitType() == '' and ds.GetRasterBand(1).GetDescription() == 'value'
	ds = None
	_, arrays = publish._read_map(path)
	band = publish._bands('download_image', {'variable': 'BIOME', 'sensor': 'RESOLVE'}, out, arrays, None, '[class]')[0]
	assert band['legend'] == {'type': 'categories', 'classes': categorical.legend(BIO, [12, 13, 99])}
	assert band['unit'] == ''
	style = report.map_style('download_image', {}, out)
	assert style['classes'] == out['classes'] and report.tif_preview(path, classes=style['classes'])


def test_the_figure_of_a_categorical_layer(tmp_path):
	"""The figure of the map: the legend of its classes (at most figures.LEGEND_CLASSES, then how many more) instead of
	the colour ramp."""
	pytest.importorskip('matplotlib')
	from monitoreo import figures
	png = io.BytesIO()
	from matplotlib import pyplot as plt
	plt.imsave(png, [[0.0, 1.0], [1.0, 0.0]], format='png')
	legend = categorical.legend(ECO, list(range(1, 20)))
	path = figures.map_figure(png.getvalue(), [-3.5, 37.0, -3.3, 37.1], categorical.vis(ECO, list(range(1, 20))), '',
	                          'Ecoregions', ['credit'], str(tmp_path / 'f.png'), 72, 5.0, legend)
	assert os.path.getsize(path) > 0


# Tools: command line, MCP server, assistant ------------------------------------------------------------------------

def test_the_command_line():
	out = io.StringIO()
	with contextlib.redirect_stdout(out):
		cli.main(['classes', 'BIOME'])
	text = out.getvalue()
	assert '99    Rock and Ice' in text and '15 classes' in text and '"classes": [1]' in text
	out = io.StringIO()
	with contextlib.redirect_stdout(out):
		cli.main(['classes', 'ecoregion', '--text', 'iberian', '--limit', '2'])
	assert '792' in out.getvalue() and '793' in out.getvalue() and '800' not in out.getvalue()
	with pytest.raises(SystemExit, match='not a categorical layer'):
		cli.main(['classes', 'NDVI', '--sensor', 'Modis'])
	assert 'classes' in cli.WHERE_HELP and 'monitoreo classes' in cli.__doc__


def test_the_mcp_server():
	from monitoreo import assistant, mcp_server
	rows = json.loads(mcp_server.list_classes('ECOREGION', text='Sierra Nevada'))
	assert rows == [{'code': 366, 'name': 'Sierra Nevada forests', 'colour': '499964', 'group': 5,
	                 'group_name': 'Temperate Conifer Forests'}]
	assert 'list_classes' in mcp_server.NO_EECU_WARNING and 'list_classes' in assistant.ADVICE
	assert '"classes": [12]' in mcp_server.WHERE_DOC and 'ECOREGION and BIOME' in mcp_server.INSTRUCTIONS
	assert 'by_group' in __import__('inspect').getsource(mcp_server.area_by_class)


def test_the_assistant(tmp_path, monkeypatch):
	"""The instructions say how to ask for the categorical layers; a pixel of their map is its class (code and name),
	without a time series; the map has the legend of its classes."""
	from monitoreo import assistant
	monkeypatch.setattr(assistant, 'LOG', str(tmp_path / 'assistant.log'))  # not the log of the user
	from test_assistant import MAP, FakeAssistant
	text = ' '.join(assistant.instructions().split())
	assert '"ECOREGION" and "BIOME", sensor "RESOLVE"' in text and 'list_classes' in text
	assert '{"variable": "BIOME", "sensor": "RESOLVE", "classes": [12]}' in text
	line = next(x for x in assistant.variables_text().splitlines() if x.startswith('- BIOME'))
	assert 'RESOLVE 1000 m' in line and 'categorical' in line and 'since' not in line
	calls = []
	legend = categorical.legend(BIO, [12, 13])

	class Maps(FakeAssistant):
		async def call(self, name, args):
			calls.append((name, args))
			return None, [json.dumps({'rows': [{'region': 'point', 'mode': 12, 'n_pixels': 1,
			                                    'mode_label': '12 Mediterranean Forests, Woodlands & Scrub'}],
			                          'unit': '[class]'})], []

	async def run():
		a = Maps({**assistant.DEFAULTS, 'project': 'p'})
		args = {'region': {'wdpa_id': 389011}, 'variable': 'BIOME', 'sensor': 'RESOLVE'}
		result = {**MAP, 'min': None, 'max': None, 'palette': None, 'classes': legend, 'unit': '[class]'}
		a.results.append({'id': 1, 'tool': 'map_layer', 'args': args, 'image': None,
		                  'title': a.titled('map_layer', args), 'result': result})
		return a.card(a.results[0]), await a.pixel(1, -3.3, 37.05)

	card, px = asyncio.run(run())
	assert card['legend'] == {'classes': [{'label': c['label'], 'color': c['color']} for c in legend]}
	assert card['map']['series'] is False
	assert px == {'lon': -3.3, 'lat': 37.05, 'value': 12, 'unit': '', 'label': 'class',
	              'text': '12 Mediterranean Forests, Woodlands & Scrub'}
	assert calls[0] == ('region_stats', {'variable': 'BIOME', 'sensor': 'RESOLVE', 'region': {'point': [-3.3, 37.05]},
	                                     'stats': ['mode']})
	page = open(os.path.join(ROOT, 'src', 'monitoreo', 'ui', 'assistant.html'), encoding='utf-8').read()
	assert 'r.text || fmt(r.value)' in page


# The Earth Engine app: gee/core.js with the same answers and calls of Earth Engine -------------------------------------

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
		return object();
	}, {get: function (t, p) { return p === TAG ? true : typeof p === 'symbol' ? undefined : call(name + '.' + p); }});
}
global.ee = new Proxy({}, {get: function (t, p) { return call(p); }});
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[1], f), 'utf8'), {filename: f});
});
// the tables and entries of the package (whatever the catalog.js there is: gee/build.py writes them there)
CATALOG.classes = input.classes;
CATALOG.variables = CATALOG.variables.filter(function (v) { return v.ref !== 149 && v.ref !== 150; }).concat(input.entries);
var mo = global.MonitorEO;
function attempt(f) {
	try { return {value: f()}; } catch (e) { return {error: e.message}; }
}
function chain(f) { log = []; f(); return log.slice(); }
var eco = mo.byRef(149), bio = mo.byRef(150), out = {};
out.images = input.images.map(function (c) { return chain(function () { mo.categoricalImage(mo.byRef(c[0]), c[1]); }); });
out.keeps = input.keeps.map(function (c) { return chain(function () { mo.classKeep(mo.byRef(c[0]), c[1], c[2], c[3]); }); });
out.where = chain(function () { mo.image(mo.spec({ref: 150, where: [{ref: 149, exclude: [793]}]}), object(), 5000); });
out.zone = chain(function () { mo.classZone(mo.spec({ref: 150, quality: {}}), object(), 5000, [12, 4]); });
out.conditions = input.conditions.map(function (c) { return attempt(function () { return mo.classCondition(c)[1]; }); });
out.checks = input.checks.map(function (v) { return attempt(function () { return mo.checkClasses(bio, v); }); });
out.stats = attempt(function () { mo.checkClassStats(bio, ['mode', 'mean']); });
out.legend = mo.categoryLegend(bio, [13, 12, 12], 'en');
out.vis = [mo.classVis(bio, [14, 99]), mo.classVis(bio, [12]), mo.classVis(eco).palette.length];
out.find = [mo.findClasses(eco, 'iberian'), mo.findClasses(eco, 'paramo', 2), mo.findClasses(bio, 'mediterráneos'),
	mo.layerClasses(bio, 'es')];
out.present = [mo.presentCodes(bio, [805.0, 793.0, 0.0]), mo.presentCodes(eco, [805.0, 793.0, 805.0])];
out.texts = input.texts.map(function (c) { return [mo.classText(c, 'en'), mo.classText(c, 'es')]; });
var legend = mo.classAreaLegend(eco, input.features, 'en');
out.areas = {legend: legend, rows: mo.areaRows(input.features, legend, {}),
	groups: mo.classGroupRows(input.features, legend, mo.categoryGroupEntry(eco), 'en')};
out.zoneRows = mo.classZoneRows(input.zoneFeatures, bio, 'en');
out.udunits = mo.UDUNITS;
out.classLabel = mo.classLabel(mo.categoryLegend(bio, [12], 'en')[0], 'en');  // fire.class_label: without dNBR
process.stdout.write(JSON.stringify(out));
"""
FEATURES = [{'properties': {'name': 'park', 'groups': [{'class': 805.0, 'sum': 300.0}, {'class': 793.0, 'sum': 100.0},
                                                         {'class': 1.0, 'sum': 0.0}]}},
            {'properties': {'name': 'other', 'groups': [{'class': 805.0, 'sum': 50.0}]}}]
ZONE_FEATURES = [{'properties': {'name': 'park', 'groups': [{'zone': 13.0, 'p50': 0.2, 'count': 10},
                                                              {'zone': 12.0, 'p50': 0.4, 'p25': 0.1, 'count': 50}]}}]
IMAGES = [(149, 1000), (149, 1500), (150, 2000.5), (150, 30000)]
KEEPS = [(150, [12], True, 5000), (149, [793, 805], False, 1000), (150, [4, 5], True, None)]
CONDITIONS = [MEDITERRANEAN, NOT_793, dict(MEDITERRANEAN, min=3), {'variable': 'ELEVATION', 'sensor': 'Copernicus',
                                                                     'classes': [1]},
              dict(MEDITERRANEAN, exclude=[4]), {'variable': 'BIOME', 'sensor': 'RESOLVE'},
              dict(MEDITERRANEAN, classes=[]), dict(NOT_793, exclude=[900, 'x']), dict(MEDITERRANEAN, classes='12, 4'),
              dict(MEDITERRANEAN, classes=['1.5'])]
CHECKS = [[12, '4', 12.0, ' 99 '], '12, 4', [], '', [15, 98], ['12.5'], [1.5], 12]


def _app_input():
	from monitoreo import sensors
	from test_themes import _build
	build = _build()
	entries = [dict({k: e.get(k) for k in build.FIELDS}, fk=sensors.parse_formula(e)[0], fb=sensors.parse_formula(e)[1])
	           for e in (ECO, BIO)]
	ref = lambda c: {('ref' if k == 'variable' else k): (catalog.find(v, c.get('sensor'))['ref'] if k == 'variable' else v)
	                 for k, v in c.items() if k != 'sensor'}  # noqa: E731
	return {'classes': catalog.load()['classes'], 'entries': entries, 'images': IMAGES, 'keeps': KEEPS,
	        'conditions': [ref(c) for c in CONDITIONS], 'checks': CHECKS, 'texts': [ref(c) for c in CONDITIONS[:2]],
	        'features': FEATURES, 'zoneFeatures': ZONE_FEATURES}


@pytest.fixture(scope='module')
def app():
	if not shutil.which('node'):
		pytest.skip('no Node')
	run = subprocess.run(['node', '-e', NODE, GEE], input=json.dumps(_app_input()), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout)


def _chain(monkeypatch, f):
	rec, region = _fake(monkeypatch)
	f(region)
	return [['and' if x[0] == 'And' else x[0]] + x[1:] for x in rec]  # ee.Image.And of Python is and in JavaScript


def test_the_app_asks_earth_engine_for_the_same_images(app, monkeypatch):
	"""categoricalImage, classKeep, the image of a layer with a condition on classes and the zones of classes of
	gee/core.js call Earth Engine as categorical.image, categorical.keep, variable.image and services._class_zone."""
	for (ref, res), js in zip(IMAGES, app['images']):
		assert js == _chain(monkeypatch, lambda r: categorical.image(catalog.find(None, ref=ref), res)), (ref, res)
	assert ['Reducer.mode'] not in app['images'][0] and ['Reducer.mode'] not in app['images'][1]  # 1500 < 2 × 1000
	assert ['Reducer.mode'] in app['images'][2] and ['Reducer.mode'] in app['images'][3]
	for (ref, values, kept, res), js in zip(KEEPS, app['keeps']):
		assert js == _chain(monkeypatch, lambda r: categorical.keep(catalog.find(None, ref=ref), values, kept, res))
	spec = services.make_spec('BIOME', 'RESOLVE', where=[NOT_793])
	assert app['where'] == _chain(monkeypatch, lambda r: variable.image(spec, r, 5000))
	assert app['where'][-2:] == [['selfMask'], ['updateMask', '<ee>']]
	zspec = services.make_spec('BIOME', 'RESOLVE')
	assert app['zone'] == _chain(monkeypatch, lambda r: services._class_zone(zspec, r, 5000, [12, 4]))
	assert app['udunits'] == catalog.UDUNITS
	assert app['classLabel'] == services.fire.class_label(categorical.legend(BIO, [12])[0]) == categorical.label(BIO, 12)


def test_the_app_checks_and_names_the_classes_as_the_package(app):
	for c, js in zip(CONDITIONS, app['conditions']):
		try:
			expected = {'value': categorical.condition(c)[1]}
		except ValueError as error:
			expected = {'error': str(error)}
		assert js == expected, c
	for v, js in zip(CHECKS, app['checks']):
		try:
			expected = {'value': categorical.check(BIO, v)}
		except ValueError as error:
			expected = {'error': str(error)}
		assert js == expected, v
	with pytest.raises(ValueError) as error:
		categorical.check_stats(BIO, ['mode', 'mean'])
	assert app['stats'] == {'error': str(error.value)}
	assert app['legend'] == categorical.legend(BIO, [13, 12, 12])
	assert app['vis'] == [categorical.vis(BIO, [14, 99]), categorical.vis(BIO, [12]), 847]
	assert app['find'] == [categorical.find(ECO, 'iberian'), categorical.find(ECO, 'paramo', 2),
	                       categorical.find(BIO, 'mediterráneos'), categorical.classes(BIO, 'es')]
	assert app['present'] == [[12, 99], [793, 805]]  # the biomes of the ecoregions: 0, Rock and Ice, is 99
	assert app['texts'] == [[categorical.text(c, 'en'), categorical.text(c, 'es')] for c in CONDITIONS[:2]]


def test_the_app_gives_the_same_areas_and_zones(app):
	ha = [(f['properties']['name'], {int(g['class']): g['sum'] for g in f['properties']['groups']}) for f in FEATURES]
	present = sorted({c for _, by in ha for c, h in by.items() if h})
	legend = [(c, categorical.label(ECO, c), {'group': categorical.group_of(ECO, c),
	                                           'group_label': categorical.label(BIO, categorical.group_of(ECO, c))})
	          for c in present]
	assert [tuple(x) for x in app['areas']['legend']] == legend
	assert app['areas']['rows'] == classes.rows(ha, legend)
	assert app['areas']['groups'] == classes.by_group(ha, legend, BIO)
	rows = app['zoneRows']
	assert [(r['zone'], r['zone_label'], r['p50'], r['p25'], r['n_pixels']) for r in rows] == [
		(12, '12 Mediterranean Forests, Woodlands & Scrub', 0.4, 0.1, 50), (13, '13 Deserts & Xeric Shrublands', 0.2, None,
		                                                                   10)]


def test_the_app_has_the_ecosystems():
	"""gee/build.py carries the tables of classes and the field classes into catalog.js (after the rebuild); ui.js
	offers the conditions, areas and zones of classes, and its texts in both languages."""
	from test_themes import _build
	build = _build()
	assert 'classes' in build.FIELDS and "'classes': catalog.load()['classes']" in open(
		os.path.join(GEE, 'build.py'), encoding='utf-8').read()
	ui = open(os.path.join(GEE, 'ui.js'), encoding='utf-8').read()
	for name in ('addClassMap', 'classZoneStatistics', 'mo.classAreaLegend', 'mo.checkClasses', "k_classes",
	             'profileCategorical'):
		assert name in ui, name
	for key in ('categoricalNote', 'whereExclude', 'whereFound', 'k_classes', 'areaClassesNote', 'zoneClassTitle'):
		assert ui.count(key + ':') == 2, key  # Spanish and English


# the panel of the app (ui.js with the ui of tests/test_themes.py, which draws nothing) with the categorical layers
PANEL_CLASSES = r"""
var GEE = process.argv[process.argv.length - 1];
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(GEE, f), 'utf8'), {filename: f});
});
CATALOG.community = input.community;
CATALOG.other_themes = input.other_themes;
CATALOG.themes = input.themes;  // those of the package, and its tables and entries: gee/build.py writes them there
CATALOG.classes = input.classes;
CATALOG.variables = CATALOG.variables.filter(function (v) { return v.ref !== 149 && v.ref !== 150; }).concat(input.entries);
vm.runInThisContext(fs.readFileSync(path.join(GEE, 'ui.js'), 'utf8'), {filename: 'ui.js'});
"""
PANEL_STEPS = r"""
function selectOf(refs) {
	return find(controls, 'Select', function (w) {
		var values = (w.opts.items || []).map(function (i) { return i.value; });
		return refs.every(function (r) { return values.indexOf(r) >= 0; });
	})[0];
}
answer = {info: {area: 8e7, centroid: [-3.56, 36.9], total: 8e7, boundsArea: 9e7}, n: 1};
selectWith('view').opts.onChange('view');
button('Use the map view').opts.onClick();
selectWith('ecosystems').opts.onChange('ecosystems');
selectOf([149, 150]).opts.onChange(150);
out.controls = texts(controls);
answer = [805, 793, 0];  // the ECO_ID of the polygons of the region (classesIn)
button('Add to the map').opts.onClick();
out.map = {layer: layers[layers.length - 1], legend: texts(legend), results: last()};
selectWith('classes').opts.onChange('classes');  // Area by class: the classes of a categorical layer
answer = {features: [{properties: {name: 'Map view', groups: [{'class': 12, sum: 300}, {'class': 99, sum: 5}]}}]};
button('Compute the areas').opts.onClick();
out.areas = last();
button('Statistics of each band').opts.onClick();  // a categorical layer as the variable: no percentiles
out.zonesOfClasses = last();
selectWith('vegetation').opts.onChange('vegetation');
selectOf([106, 150]).opts.onChange(150);  // the zones: the biomes
answer = {features: [{properties: {name: 'Map view', groups: [{zone: 12, p50: 0.4, count: 10}]}}]};
button('Statistics of each band').opts.onClick();
out.zones = last();
check('a variable is between two values').opts.onChange(true);  // only the pixels of the Mediterranean biome
selectOf([27, 149, 150]).opts.onChange(150);
out.whereControls = texts(controls);
button('Add to the map').opts.onClick();
out.noCodes = last();
textbox(function (w) { return w.opts.placeholder === 'codes, e.g. 12, 4'; }).opts.onChange('12');
answer = {value_p5: 0.1, value_p95: 0.8};
button('Add to the map').opts.onClick();
out.where = {layer: layers[layers.length - 1], results: last()};
textbox(function (w) { return w.opts.placeholder === 'codes, e.g. 12, 4'; }).opts.onChange('12, 50');
button('Add to the map').opts.onClick();
out.badCode = last();
process.stdout.write(JSON.stringify(out));
"""


def test_the_panel_of_the_app_with_the_categorical_layers():
	"""ui.js draws the map of a categorical layer with the legend of its classes, its areas by class, the zones of its
	classes and the condition of where on its classes, without errors (an ee and a ui that compute and draw nothing)."""
	if not shutil.which('node'):
		pytest.skip('no Node')
	from test_themes import PANEL
	head = PANEL[:PANEL.index('var GEE = process.argv')]
	helpers = PANEL[PANEL.index('var controls = root.children[0]'):PANEL.index('var out = {};') + len('var out = {};')]
	data = dict(_app_input(), assets={}, themes=catalog.THEMES, other_themes=catalog.OTHER_THEMES,
	            community=__import__('test_themes')._build().community_index())
	run = subprocess.run(['node', '-e', head + PANEL_CLASSES + helpers + PANEL_STEPS, GEE], input=json.dumps(data),
	                     capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	assert any(t.startswith('Categorical layer: its values are class codes') for t in out['controls'])
	assert out['map']['layer'] == 'BIOME RESOLVE · Map view'
	assert out['map']['legend'][1:] == ['12 Mediterranean Forests, Woodlands & Scrub', '99 Rock and Ice']
	assert out['map']['results']['texts'][:2] == ['BIOME RESOLVE · Map view', '2 classes in the region.']
	assert out['areas']['charts'][1]['head'] == ['Class', 'ha', '% of the area with classes']
	assert out['areas']['texts'][0] == 'Area of each class of BIOME RESOLVE · Map view'
	assert out['zonesOfClasses']['texts'][0].startswith('A categorical layer as the variable has no percentiles')
	assert out['zones']['charts'][0]['head'][0] == 'Class' and 'by classes of BIOME' in str(out['zones'])
	assert any('12 Mediterranean Forests, Woodlands & Scrub' in t for t in out['whereControls'])  # the biomes listed
	assert out['noCodes']['texts'] == ['Give the codes of the classes (find them by their name).']
	assert 'BIOME (RESOLVE) is 12 Mediterranean Forests, Woodlands & Scrub' in out['where']['layer']
	assert out['badCode']['texts'] == ['BIOME (RESOLVE) has no classes 50: list_classes gives the codes of its classes']
