"""A biome of RESOLVE Ecoregions 2017 as a region (biome_id, biome_at), the part of any region within another (within)
and the automatic CRS of the regions too wide for a UTM zone (areas.auto_crs), without Earth Engine: the regions
checked before Earth Engine is asked anything, the calls of Earth Engine of the package (a fake ee) and the same calls,
errors and CRS in the app (gee/core.js in Node), their names in titles and READMEs, their references, the assistant,
the MCP server, the command line, the QGIS plugin and the R package. tests/test_gee.py computes them in Earth Engine."""

import ast
import asyncio
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys

import pytest

from monitoreo import areas, assistant, catalog, cli, readme, recipe, references, report, services, timeseries

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEE = os.path.join(ROOT, 'gee')
BOX = [-3.62, 36.86, -3.50, 36.93]
MEDITERRANEAN = 'Mediterranean Forests, Woodlands & Scrub'
GAUL_CREDIT = 'Source: FAO GAUL 2025'


def _read(*parts):
	with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
		return f.read()


# The regions, checked without Earth Engine -------------------------------------------------------------------------

class _NoEarthEngine:
	"""An ee that fails when it is used: the region must be refused before."""

	def __getattr__(self, name):
		pytest.fail(f'Earth Engine was asked for {name} before the region was checked')


def test_the_keys_of_the_regions():
	keys = areas.REGION_KEYS
	assert keys.index('biome_id') == keys.index('ecoregion_at') + 1 and keys.index('biome_at') == keys.index('biome_id') + 1
	assert 'within' not in keys  # a modifier of any region, as buffer
	assert areas.BIOME_MAX_ERROR == areas.WITHIN_MAX_ERROR == 100
	codes = [b['code'] for b in catalog.biomes()]
	assert codes == list(range(1, 15)) + [99] and areas.BIOME_CODES == '1 to 14 or 99 (Rock and Ice)'


@pytest.mark.parametrize('region, message', [
	({'biome_id': 15}, 'biome_id takes the codes of the biomes of RESOLVE Ecoregions 2017, 1 to 14 or 99 (Rock and '
	                   'Ice), not 15: list_classes of BIOME gives them'),
	({'biome_id': [12, 0]}, 'not 0: list_classes of BIOME gives them'),
	({'biome_id': '12.5'}, "not '12.5'"),
	({'biome_id': []}, '1 to 14 or 99 (Rock and Ice), e.g. 12'),
	({'biome_at': [-3.3]}, 'biome_at is a point, [lon, lat] in degrees, e.g. [-3.3, 37.1]; not [-3.3]'),
	({'biome_at': ['x', 37]}, 'biome_at is a point'),
	({'biome_id': 12, 'country': 'ESP'}, 'give one region: geojson, file, wdpa_id, wdpa_name, ecoregion_id, '
	                                     'ecoregion_at, biome_id, biome_at, country'),
	({'biome_id': 12, 'within': {'point': [-3.3, 37.1]}}, 'within takes a region with an area: give the point a buffer'),
	({'biome_id': 12, 'within': 'ESP'}, 'within is another region, a dictionary with one of: geojson'),
	({'biome_id': 12, 'within': {'country': 'ESP', 'admin1': 1}}, 'within is another region'),
	({'biome_id': 12, 'within': {}}, 'e.g. {"country": "ESP"}'),
	({'country': 'ESP', 'within': {'biome_id': 15}}, 'not 15'),  # the region of within is checked the same
	({'wdpa_id': 389011, 'within': {'country': 'ESP', 'within': {'biome_at': [1]}}}, 'biome_at is a point'),
])
def test_wrong_regions_are_refused_before_earth_engine(monkeypatch, region, message):
	monkeypatch.setattr(areas, 'ee', _NoEarthEngine())
	with pytest.raises(ValueError) as error:
		areas.region(region)
	assert message in str(error.value)


def test_the_codes_and_names_of_the_biomes():
	assert areas.biome_codes([12, '4', 12.0, ' 99 ']) == [12, 4, 99] and areas.biome_codes('12; 4') == [12, 4]
	assert areas.biome_codes(12) == [12]
	assert areas.biome_name(12) == areas.biome_name('12') == MEDITERRANEAN and areas.biome_name(15) is None
	assert areas.biome_name(99, 'es') == 'Roca y hielo'
	assert areas.ecoregion_name(793) == 'Iberian sclerophyllous and semi-deciduous forests'
	assert areas.ecoregion_name(0) == 'Rock and Ice' and areas.ecoregion_name(9999) is None
	assert areas.check({'biome_id': 12, 'within': {'point': [-3.3, 37.1], 'buffer': 1000}}) == 'biome_id'
	assert areas.check({'wdpa_id': 389011, 'within': {'admin2': 141938}}) == 'wdpa_id'


# The calls of Earth Engine (a fake ee) -----------------------------------------------------------------------------

def _chain(monkeypatch, region):
	"""The calls of Earth Engine of areas.region(REGION), logged by the fake ee of tests/test_themes.py."""
	from test_themes import _Root
	rec = []
	monkeypatch.setattr(areas, 'ee', _Root(rec))
	areas.region(region)
	return rec


def test_a_biome_is_the_union_of_its_ecoregions(monkeypatch):
	"""A feature per biome, named by its name: the ecoregions of its ECO_IDs in the table of classes (not of its
	BIOME_NUM: Rock and Ice, 99, is the ECO_ID 0, whose BIOME_NUM is that of the Tundra), dissolved."""
	rec = _chain(monkeypatch, {'biome_id': [12, 99]})
	ids = catalog.ecoregions_of_biome(12)
	one = lambda ids, name, code: [['FeatureCollection', areas.ECOREGIONS], ['Filter.inList', 'ECO_ID', ids],  # noqa
	                               ['filter', '<ee>'], ['geometry', 100], ['dissolve', 100],
	                               ['Feature', '<ee>', {'name': name, 'biome': code}]]
	assert rec == one(ids, MEDITERRANEAN, 12) + one([0], 'Rock and Ice', 99) + [['FeatureCollection', ['<ee>', '<ee>']]]
	assert 793 in ids and 0 not in ids and len(ids) == 40  # the Mediterranean ecoregions of the table


def test_a_biome_within_another_region(monkeypatch):
	"""Within a box: only the ecoregions of the biome that touch it are joined, then the part of the biome inside it."""
	rec = _chain(monkeypatch, {'biome_id': 12, 'within': {'bbox': BOX}})
	box = [['Geometry.Rectangle', BOX, None, False], ['Feature', '<ee>', {'name': 'bbox'}], ['FeatureCollection', ['<ee>']],
	       ['geometry', 100]]
	assert rec[:4] == box
	assert rec[4:12] == [['FeatureCollection', areas.ECOREGIONS], ['Filter.inList', 'ECO_ID', catalog.ecoregions_of_biome(12)],
	                     ['filter', '<ee>'], ['filterBounds', '<ee>'], ['geometry', 100], ['dissolve', 100],
	                     ['Feature', '<ee>', {'name': MEDITERRANEAN, 'biome': 12}], ['FeatureCollection', ['<ee>']]]
	assert rec[12:] == [['filterBounds', '<ee>'], ['map', '<function>'], ['Feature', '<ee>'], ['intersection', '<ee>', 100]]
	# any region takes within: a protected area of the list in an administrative unit
	rec = _chain(monkeypatch, {'ecoregion_id': 793, 'within': {'admin2': 141938}})
	assert rec[:3] == [['FeatureCollection', areas.GAUL[2]], ['Filter.inList', 'GAUL2_CODE', [141938]], ['filter', '<ee>']]
	assert ['Filter.inList', 'ECO_ID', [793]] in rec and rec[-2:] == [['Feature', '<ee>'], ['intersection', '<ee>', 100]]


def test_the_biome_at_a_point(monkeypatch):
	"""The biome of the ecoregion at the point: for each biome of the table, its feature if one of its ecoregions is
	there (If: Earth Engine joins only that one); none in the sea."""
	rec = _chain(monkeypatch, {'biome_at': [-3.3, 37.1]})
	assert rec[:3] == [['FeatureCollection', areas.ECOREGIONS], ['Geometry.Point', [-3.3, 37.1]], ['filterBounds', '<ee>']]
	ifs = [r for r in rec if r[0] == 'Algorithms.If']
	assert len(ifs) == len(catalog.biomes()) == 15 and all(r == ['Algorithms.If', '<ee>', '<ee>', None] for r in ifs)
	tests = [r for r in rec if r[:2] == ['Filter.inList', 'ECO_ID']]
	assert [t[2] for t in tests[::2]] == [catalog.ecoregions_of_biome(b['code']) for b in catalog.biomes()]
	assert rec[-3:] == [['List', ['<ee>'] * 15], ['removeAll', [None]], ['FeatureCollection', '<ee>']]
	assert {'name': 'Rock and Ice', 'biome': 99} in [r[2] for r in rec if r[0] == 'Feature']


# The automatic CRS -------------------------------------------------------------------------------------------------

def _info(west, east, lon=None, lat=37.0):
	ring = [[west, 27.6], [east, 27.6], [east, 43.8], [west, 43.8], [west, 27.6]]
	return {'centroid': [lon if lon is not None else (west + east) / 2, lat], 'bounds': [ring]}


INFOS = [_info(-3.62, -3.50), _info(-18.2, 4.3, -3.6, 40.2), _info(-125, -66.9, -98.5, 39.8), _info(-180, 180, 95, 62),
         _info(-109.5, -66.4, -71, -35.7), _info(10, 50, 30), _info(10, 50.5, 30), _info(150, 170, 160, -40),
         {'centroid': [-3.56, 36.9]},
         # across the antimeridian, with its bounds in the Mercator of the Pacific: Fiji split at 180 (0.4 degrees: its UTM
         # zone, as Earth Engine gives it for the units of FAO GAUL) and a region of 60 degrees (EPSG:6933)
         dict(_info(-180, 180, 179.9, -16.5), pacific=[[[-22264, -1.9e6], [22264, -1.9e6], [22264, -1.8e6]]]),
         dict(_info(-180, 180, 180, 60), pacific=[[[-3339585, 5.6e6], [3339585, 5.6e6], [3339585, 1.1e7]]])]


def test_the_automatic_crs():
	"""The UTM zone of the centre (Sierra Nevada; Spain with the Canary Islands, some 22 degrees of longitude), or
	EPSG:6933 (equal area, metres) for the regions wider than 40 degrees (the USA, Chile with Easter Island) or across
	the antimeridian (Russia, the Tundra: their bounds span 360)."""
	got = [areas.crs_for(i) for i in INFOS]
	assert got == ['EPSG:32630', 'EPSG:32630', 'EPSG:6933', 'EPSG:6933', 'EPSG:6933', 'EPSG:32636', 'EPSG:6933',
	               'EPSG:32757', 'EPSG:32630', 'EPSG:32760', 'EPSG:6933']
	assert areas.GLOBAL_CRS == 'EPSG:6933' and areas.WIDE_DEGREES == 40


def test_auto_crs_asks_earth_engine_once(monkeypatch):
	asked = []

	class Coordinates:
		def __init__(self, what, max_error):
			self.what = (what, max_error)

		def coordinates(self):
			return self.what

	class Pacific(Coordinates):
		def coordinates(self):
			return self

		def getInfo(self):  # the bounds in the Mercator of the Pacific, asked only across the antimeridian
			asked.append(self.what)
			return INFOS[-1]['pacific']

	class Geom:
		def centroid(self, max_error):
			return Coordinates('centroid', max_error)

		def bounds(self, max_error, proj=None):
			return Pacific(('bounds', proj), max_error) if proj else Coordinates('bounds', max_error)

	class Dictionary:
		def __init__(self, d):
			asked.append(d)

		def getInfo(self):
			return INFOS[1] if asked[-1]['centroid'][1] == 1000 else INFOS[3]

	monkeypatch.setattr(areas.ee, 'Dictionary', Dictionary)
	assert areas.auto_crs(Geom()) == 'EPSG:32630' and asked == [{'centroid': ('centroid', 1000),
	                                                              'bounds': ('bounds', 1000)}]
	# Russia: across the antimeridian (bounds of 360), so a second request, its span in the Mercator of the Pacific
	assert areas.auto_crs(Geom(), 1) == 'EPSG:6933' and asked[-2]['bounds'] == ('bounds', 1)
	assert asked[-1] == (('bounds', 'EPSG:3832'), 1)


def test_the_tools_choose_the_crs_with_auto_crs(monkeypatch):
	"""The statistics (timeseries.region_crs), the grids of the downloads (services._grid with crs auto) and the study
	areas of the recipes."""
	chosen = []
	monkeypatch.setattr(areas, 'auto_crs', lambda geom, max_error=1000: chosen.append(max_error) or 'EPSG:6933')

	class Info:
		def __init__(self, value):
			self.value = value

		def getInfo(self):
			return self.value

	class Geom:
		def bounds(self, res, crs):
			return Info({'coordinates': [[[0, 0], [1000, 0], [1000, 500], [0, 500], [0, 0]]]})

	class Regions:
		def geometry(self):
			return Geom()

	assert timeseries.region_crs(Regions()) == 'EPSG:6933' and chosen == [1000]
	grid = services._grid(Regions(), 100, 'auto')
	assert grid.crs == 'EPSG:6933' and chosen[-1] == 1
	assert services._grid(Regions(), 100, 'EPSG:25830').crs == 'EPSG:25830' and len(chosen) == 2
	monkeypatch.setattr(areas, 'region', lambda spec: Regions())
	geom, crs, box, name = recipe._study_area({'biome_id': 12, 'within': {'country': 'ESP'}}, None, 100, 'auto')
	assert crs == 'EPSG:6933' and chosen[-1] == 1 and box == (0, 0, 1000, 500)
	assert json.loads(name) == {'biome_id': 12, 'within': {'country': 'ESP'}}


# Names, references, READMEs ---------------------------------------------------------------------------------------

def test_the_names_of_the_regions():
	names = {'country:ESP': 'Spain', 'admin2:141938': 'Granada, Andalucía, Spain'}
	assert report.region_text({'biome_id': 12}) == f'{MEDITERRANEAN} (biome 12 of RESOLVE Ecoregions 2017)'
	assert report.region_text({'biome_id': [12, 99]}) == (f'{MEDITERRANEAN} (biome 12 of RESOLVE Ecoregions 2017); '
	                                                      'Rock and Ice (biome 99 of RESOLVE Ecoregions 2017)')
	assert report.region_text({'biome_at': [-3.3, 37.1]}) == 'Biome of the point 37.1, -3.3 (lat., lon.)'
	assert report.region_text({'biome_id': 12, 'within': {'country': 'ESP'}}, names) == (
		f'{MEDITERRANEAN} (biome 12 of RESOLVE Ecoregions 2017) within Spain (country, FAO GAUL 2025)')
	assert report.region_text({'wdpa_id': 389011, 'within': {'admin2': 141938}}, {**names, '389011': 'Sierra Nevada'}) == (
		'Sierra Nevada (WDPA 389011) within Granada, Andalucía, Spain (administrative unit, FAO GAUL 2025)')
	assert report.region_text({'biome_at': [-3.3, 37.1], 'within': {'bbox': BOX}}).endswith(
		' within Rectangle of longitude -3.62 to -3.5 and latitude 36.86 to 36.93')
	# a list of ecoregions: their names, as a list of protected areas (not «Ecoregion [793, 794]»)
	assert report.region_text({'ecoregion_id': [793, 794]}) == (
		'Iberian sclerophyllous and semi-deciduous forests (ecoregion 793 of RESOLVE Ecoregions 2017); Illyrian '
		'deciduous forests (ecoregion 794 of RESOLVE Ecoregions 2017)')
	assert report.region_text({'ecoregion_id': 9999}) == 'Ecoregion 9999 of RESOLVE Ecoregions 2017'
	assert '[' not in report.region_text({'ecoregion_id': [793]})


def _ids(cited):
	return [r['id'] for r in cited['references']]


def test_the_references_of_the_regions():
	"""A biome cites RESOLVE (Dinerstein et al. 2017), and the region of within its own (FAO GAUL and its credit,
	WDPA)."""
	args = {'variable': 'NDVI', 'sensor': 'Modis', 'start': '2020-01-01', 'end': '2020-12-31'}
	for region in ({'biome_id': 12}, {'biome_at': [-3.3, 37.1]}):
		assert 'dinerstein2017' in _ids(references.cite('time_series', {**args, 'region': region})), region
	assert 'fao_gaul2025' not in _ids(references.cite('time_series', {**args, 'region': {'biome_id': 12}}))
	both = references.cite('time_series', {**args, 'region': {'biome_id': 12, 'within': {'country': 'ESP'}}})
	assert {'dinerstein2017', 'fao_gaul2025'} <= set(_ids(both))
	assert any(c.startswith(GAUL_CREDIT) for c in both['credits'])
	eco = references.cite('map_layer', {**args, 'region': {'ecoregion_id': 793, 'within': {'admin2': 141938}}})
	assert {'dinerstein2017', 'fao_gaul2025'} <= set(_ids(eco))
	wdpa = references.cite('map_layer', {**args, 'region': {'biome_id': 12, 'within': {'wdpa_id': 389011}}})
	assert {'dinerstein2017', 'wdpa'} <= set(_ids(wdpa)) and _ids(wdpa).count('dinerstein2017') == 1
	nested = references.cite('map_layer', {**args, 'region': {'biome_id': 12, 'within': {'ecoregion_id': 793, 'within': {
		'island_at': [2.9, 39.6]}}}})
	assert {'dinerstein2017', 'sayre2019'} <= set(_ids(nested)) and _ids(nested).count('dinerstein2017') == 1
	recipe_area = references.cite('download_variables', {'recipe': {'variables': []},
	                                                     'area': {'biome_id': 12, 'within': {'country': 'ESP'}}})
	assert {'dinerstein2017', 'fao_gaul2025'} <= set(_ids(recipe_area))


def test_the_readme_of_a_biome_within_a_country(tmp_path):
	args = {'region': {'biome_id': 12, 'within': {'country': 'ESP'}}, 'variable': 'NDVI', 'sensor': 'Modis',
	        'start': '2020-01-01', 'end': '2020-12-31', 'step': 'annual'}
	csv = tmp_path / 'series.csv'
	csv.write_text('region,date,value\n', encoding='utf-8')
	text = ' '.join(readme.text('time_series', args, {'csv': str(csv), 'rows': []}).split())
	assert f'{MEDITERRANEAN} (biome 12 of RESOLVE Ecoregions 2017) within ESP (country, FAO GAUL 2025)' in text
	assert 'Dinerstein' in text and GAUL_CREDIT in text


# The assistant, the MCP server and the command line ----------------------------------------------------------------

def test_the_assistant(tmp_path, monkeypatch):
	"""The instructions give the forms of the biomes (with their codes and names, from the table) and within; the titles
	name the biome and its within; a code of an administrative unit or a WDPA ID made up inside within is refused as at
	the top of the region, and a WDPA ID of the user's place is put where the model gave the other."""
	monkeypatch.setattr(assistant, 'LOG', str(tmp_path / 'assistant.log'))  # not the log of the user
	from test_assistant import ARGS, AREAS, FakeAssistant
	for text in (assistant.instructions(), assistant.instructions(big=True)):
		text = ' '.join(text.split())
		assert '{"biome_at": [lon, lat]}' in text and '{"biome_id": N}' in text and '"within"' in text
		assert '{"biome_id": 12, "within": {"country": "ESP"}}' in text
		assert all(f"{b['code']} {b['name']}" in text for b in catalog.biomes())
		assert '13 Deserts & Xeric Shrublands; 14 Mangroves; 99 Rock and Ice' in text
	a = FakeAssistant({**assistant.DEFAULTS, 'project': 'p'})
	a.names.update({'admin2:141938': 'Granada, Andalucía, Spain', 'country:ESP': 'Spain', '389011': 'Sierra Nevada'})
	title = a.titled('time_series', {**ARGS, 'region': {'biome_id': 12, 'within': {'admin2': 141938}}})
	assert title.endswith(f' · {MEDITERRANEAN} (biome 12 of RESOLVE Ecoregions 2017) within Granada, Andalucía, Spain '
	                      '(administrative unit, FAO GAUL 2025)'), title
	assert a.region_name({'region': {'wdpa_id': 389011, 'within': {'country': 'ESP'}}}) == (
		'Sierra Nevada within Spain (country, FAO GAUL 2025)')
	a.messages.append({'role': 'user', 'content': 'NDVI del bioma mediterráneo en Sierra Nevada'})
	assert a.unknown_units({'region': {'biome_id': 12, 'within': {'admin2': 12345}}}) == ['admin2 12345']
	assert a.unknown_units({'region': {'biome_id': 12, 'within': {'admin2': 141938}}}) == []
	assert a.unknown_areas({'region': {'biome_id': 12, 'within': {'wdpa_id': 555}}}) == [555]
	assert a.unknown_areas({'region': {'biome_id': 12, 'within': {'wdpa_id': 389011}}}) == []

	async def known():
		return [e async for e in a.known_areas('time_series', {**ARGS, 'region': {'biome_id': 12, 'within': {
			'wdpa_id': 555}}})]

	monkeypatch.setattr(assistant, 'place_in', lambda text: 'Sierra Nevada')
	assert AREAS['Sierra'][0]['SITE_ID'] == 389011
	events = asyncio.run(known())
	assert events[-1]['args']['region'] == {'biome_id': 12, 'within': {'wdpa_id': 389011}}

	async def known_within():  # a known protected area within an invented one: only the invented ID is replaced
		return [e async for e in a.known_areas('time_series', {**ARGS, 'region': {'wdpa_id': 389011, 'within': {
			'wdpa_id': 555}}})]

	assert asyncio.run(known_within())[-1]['args']['region'] == {'wdpa_id': 389011, 'within': {'wdpa_id': 389011}}


def test_the_mcp_server_and_the_command_line():
	from monitoreo import mcp_server
	text = ' '.join(mcp_server.INSTRUCTIONS.split())
	assert '{"biome_id": 12}' in text and '{"biome_at": [lon, lat]}' in text and '"within"' in text
	assert '{"biome_id": 12, "within": {"country": "ESP"}}' in text and 'EPSG:6933' in text
	assert 'RESOLVE ecoregions and biomes' in text and '{"variable": "BIOME", "sensor": "RESOLVE", "classes": [12]}' in text
	doc = ' '.join(cli.__doc__.split())
	assert '\'{"biome_id": 12, "within": {"country": "ESP"}}\'' in doc and '\'{"biome_at": [-3.3, 37.1]}\'' in doc
	for command, example in (('series', '"within": {"country": "ESP"}'), ('stats', '{"biome_at": [-3.3, 37.1]}')):
		out = io.StringIO()
		with contextlib.redirect_stdout(out), pytest.raises(SystemExit):
			cli.main([command, '--help'])  # argparse refuses a lone % in a help text
		assert example in ' '.join(out.getvalue().split()), command


# The QGIS plugin and the R package --------------------------------------------------------------------------------

def test_the_qgis_plugin(monkeypatch):
	"""The biome at the center of the map after the ecoregion (the indices 0, layer, and 1, extent, of the tests stay),
	always within the map extent; its help text and the description of the plugin (without a % sign)."""
	dock = _read('qgis', 'monitoreo_qgis', 'dock.py')
	tree = ast.parse(dock)
	regions = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
	               and getattr(n.targets[0], 'id', None) == 'REGIONS')
	kinds = [k for _, k in regions]
	assert kinds == ['layer', 'extent', 'wdpa', 'admin', 'country', 'ecoregion', 'biome', 'island', 'sea', 'sea_point']
	assert ('Biome at the center of the map', 'biome') in regions
	assert "return {'biome_at': [c.x(), c.y()], 'within': extent}" in dock
	monkeypatch.syspath_prepend(os.path.join(ROOT, 'qgis'))  # the help of the plugin does not need QGIS
	for name in [m for m in sys.modules if m.startswith('monitoreo_qgis')]:
		monkeypatch.delitem(sys.modules, name)
	import monitoreo_qgis.helptexts as help_
	assert '<b>Biome at the center of the map</b>' in help_.HELP['region'] and 'map extent' in help_.HELP['region']
	about = next(x for x in _read('qgis', 'monitoreo_qgis', 'metadata.txt').splitlines() if x.startswith('about='))
	assert 'a biome (its part in the map extent)' in about and '%' not in about


def test_the_r_package():
	r = _read('r', 'monitoreo', 'R', 'monitoreo.R')
	assert 'mo_biome <- function(id = NULL, lon = NULL, lat = NULL, within = NULL) {' in r
	assert "#' mo_biome(12, within = mo_country(\"ESP\"))" in r and "#' @param within another region" in r
	assert '\\code{mo_biome()}, \\code{mo_country()}' in r  # in the region of every function (mo_params)
	assert 'export(mo_biome)' in _read('r', 'monitoreo', 'NAMESPACE')
	tests = _read('r', 'monitoreo', 'tests', 'testthat', 'test-monitoreo.R')
	assert 'list(biome_id = list(12L), within = list(country = list("ESP")))' in tests


# The Earth Engine app: gee/core.js with the same calls, errors and CRS -----------------------------------------------

NODE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
// an object ee that computes nothing: it logs every call, [name, arguments] (its objects are '<ee>'), and runs the
// function of map on one of its objects (as the fake ee of tests/test_themes.py)
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
CATALOG.classes = input.classes;  // those of the package (gee/build.py writes them into catalog.js)
var mo = global.MonitorEO;
function attempt(f) {
	try { return {value: f()}; } catch (e) { return {error: e.message}; }
}
function chain(f) { log = []; f(); return log.slice(); }
// a region of areas.region as the app builds it: the biome by its code or at a point, within a box
function region(r) {
	var inside = r.within ? mo.bboxRegion(r.within.bbox).geometry(mo.WITHIN_MAX_ERROR) : undefined;
	var fc = r.biome_id !== undefined ? mo.biomeRegion(r.biome_id, inside) : mo.biomeAt(r.biome_at[0], r.biome_at[1], inside);
	return inside ? mo.withinRegion(fc, inside) : fc;
}
var out = {};
out.chains = input.regions.map(function (r) { return chain(function () { region(r); }); });
out.codes = input.codes.map(function (v) { return attempt(function () { return mo.biomeCodes(v); }); });
out.crs = input.infos.map(mo.regionCrs);
out.names = [mo.biomeName(12), mo.biomeName('99', 'es'), mo.biomeName(15), mo.ecoregionsOfBiome(99),
	mo.ecoregionsOfBiome(12), mo.biomes('es')];
out.info = chain(function () { mo.regionInfo(object()); });
out.constants = [mo.BIOME_MAX_ERROR, mo.WITHIN_MAX_ERROR, mo.GLOBAL_CRS, mo.WIDE_DEGREES];
process.stdout.write(JSON.stringify(out));
"""
REGIONS = [{'biome_id': 12}, {'biome_id': [12, 99], 'within': {'bbox': BOX}}, {'biome_at': [-3.3, 37.1]},
           {'biome_at': [-3.56, 36.9], 'within': {'bbox': BOX}}]
CODES = [12, [12, '4', 12.0, ' 99 '], '12; 4', 15, [12, 0], '12.5', 'x', [], [1.5], ' ']


@pytest.fixture(scope='module')
def app():
	if not shutil.which('node'):
		pytest.skip('no Node')
	data = {'classes': catalog.load()['classes'], 'regions': REGIONS, 'codes': CODES, 'infos': INFOS}
	run = subprocess.run(['node', '-e', NODE, GEE], input=json.dumps(data), capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout)


def test_the_app_builds_the_same_regions(app, monkeypatch):
	"""biomeRegion, biomeAt and withinRegion (with the box of the map view) call Earth Engine as areas.region."""
	for r, js in zip(REGIONS, app['chains']):
		assert js == _chain(monkeypatch, r), r
	assert ['dissolve', 100] in app['chains'][0] and ['intersection', '<ee>', 100] in app['chains'][1]


def test_the_app_checks_the_biomes_and_chooses_the_crs_as_the_package(app):
	for v, js in zip(CODES, app['codes']):
		try:
			expected = {'value': areas.biome_codes(v)}
		except ValueError as error:
			expected = {'error': str(error)}
		assert js == expected, v
	assert app['crs'] == [areas.crs_for(i) for i in INFOS]
	assert app['names'] == [MEDITERRANEAN, 'Roca y hielo', None, [0], catalog.ecoregions_of_biome(12),
	                        catalog.biomes('es')]
	assert app['constants'] == [areas.BIOME_MAX_ERROR, areas.WITHIN_MAX_ERROR, areas.GLOBAL_CRS, areas.WIDE_DEGREES]
	assert ['bounds', 1000] in app['info'] and ['centroid', 1000] in app['info']  # regionInfo: what regionCrs needs


def test_the_app_has_the_biome_mode():
	"""The mode Biome (Bioma) of the app: a click on the map gives the biome there, only its part in the map view,
	with the CRS of areas.auto_crs; and parity.js builds the regions of tests/test_gee.py with biomes and within."""
	ui = _read('gee', 'ui.js')
	assert "mode_biome: 'Bioma'" in ui and "mode_biome: 'Biome'" in ui and ui.count('biomeHelp: ') == 2
	assert ui.count('noBiome: ') == 2
	assert "['wdpa', 'admin', 'ecoregion', 'biome', 'island', 'sea', 'view', 'draw']" in ui
	assert 'mo.withinRegion(mo.biomeAt(coords.lon, coords.lat, inside), inside)' in ui
	assert 'mo.bboxRegion(map.getBounds()).geometry(mo.WITHIN_MAX_ERROR)' in ui
	assert 'state.info.crs = mo.regionCrs(d.info)' in ui and 'mo.utmOf(d.info.centroid' not in ui
	parity = _read('gee', 'parity.js')
	assert 'mo.biomeRegion(r.biome_id, inside)' in parity and 'mo.withinRegion(fc, geom)' in parity
	assert 'crs: mo.regionCrs(d.info)' in parity and 'mo.utmOf' not in parity
	from test_gee import CASES
	assert CASES['series_modis_biome_within']['region'] == {'biome_id': 12, 'within': {'bbox': BOX}}
