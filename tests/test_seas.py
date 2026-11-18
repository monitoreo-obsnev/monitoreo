"""The oceans and seas as regions (monitoreo.seas: the sea areas of the IHO, of the intersect of the EEZs and IHO sea
areas of Marine Regions), and the pixels of 1 to 10 km of the large areas (areas.default_scale), without Earth Engine:
the index of the package and its search, the region {"sea": ...} or {"sea_at": ...} checked offline and its calls of
Earth Engine (a fake ee), its references and credit, its name in the READMEs, reports and titles, the warning of the
variables of the land over a sea, the dissolution of the parts by sea (GDAL), the command line, the MCP server, the
assistant (its list of seas, on the page too), the QGIS plugin and the R package. tests/test_seas_gee.py: the Earth
Engine app."""

import asyncio
import gzip
import json
import math
import os

import pytest

from monitoreo import areas, catalog, classes, cli, readme, references, report, seas, services, timeseries

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALBORAN = 3324
WESTERN, EASTERN = 4279, 4280  # the two basins of the Mediterranean Sea of the IHO


def _read(*parts):
	with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
		return f.read()


# The index of the package and its search ---------------------------------------------------------------------------

def test_the_index_of_the_package():
	idx = seas.load()
	assert idx['doi'] == '10.14284/699' == seas.DOI and idx['version'] == 5 and idx['asset'] == seas.ASSET
	assert idx['date'] == '2024-10-09' and seas.LAYER in idx['source'] and idx['credit'] == seas.CREDIT
	rows = idx['rows']
	assert len(rows) == 101  # the sea areas of the IHO, each once
	assert len({r[0] for r in rows}) == len({r[1] for r in rows}) == 101
	assert [r[1] for r in rows] == sorted(r[1] for r in rows)
	for mrgid, name, area, (w, s, e, n) in rows:
		assert isinstance(mrgid, int) and name and area > 1000, name
		assert -180 <= w < e <= 180 and -90 <= s < n <= 90, name
	alboran = next(r for r in rows if r[0] == ALBORAN)
	assert alboran[1] == 'Alboran Sea' and 54_000 < alboran[2] < 55_000
	assert {'Southern Ocean', 'Arctic Ocean', 'North Atlantic Ocean', 'South Pacific Ocean', 'Black Sea',
	        'Mediterranean Sea - Western Basin', 'Mediterranean Sea - Eastern Basin'} <= {r[1] for r in rows}
	assert sum(r[2] for r in rows) > 3.5e8  # the oceans of the Earth, some 361 million km²


def test_a_sea_by_its_name_in_any_case_and_accents_or_its_mrgid():
	assert seas.find('ALBORÁN') == [{'MRGID': ALBORAN, 'NAME': 'Alboran Sea', 'AREA_KM2': seas.area_of(ALBORAN),
	                                 'BOUNDS': [-5.354, 35.071, -1.188, 36.842]}]
	assert [s['MRGID'] for s in seas.find('mediterranean')] == [EASTERN, WESTERN]
	assert seas.find('3324')[0]['NAME'] == 'Alboran Sea'
	assert seas.find('balearic iberian')[0]['MRGID'] == 3322  # 'Balearic (Iberian Sea)'
	found = seas.find('sea', limit=200)
	assert found[0]['NAME'].lower().startswith('sea') or all(not s['NAME'].lower().startswith('sea') for s in found)
	assert len(seas.find('ocean', limit=3)) == 3 and seas.find('atlantis') == []
	names = [s['NAME'] for s in seas.find('north sea')]
	assert names[0] == 'North Sea'  # the very name first


def test_the_names_are_written_as_the_table():
	assert seas.plain('Balearic (Iberian Sea)') == 'balearic iberian sea'
	assert seas.plain('Mediterranean Sea - Eastern Basin') == 'mediterranean sea eastern basin'
	assert seas.plain('  Mar de ALBORÁN\t') == 'mar de alboran' and seas.plain('Gulf of St. Lawrence') == 'gulf of st lawrence'
	assert seas.plain('Bay of Fundy') == 'bay of fundy' and seas.plain('L’x') == "l'x"


@pytest.mark.parametrize('value, mrgids', [
	(ALBORAN, [ALBORAN]), ('3324', [ALBORAN]), (3324.0, [ALBORAN]), ('Alboran Sea', [ALBORAN]),
	('  alborán SEA ', [ALBORAN]), (['Alboran Sea', WESTERN, 'alboran sea'], [ALBORAN, WESTERN]),
	(('Balearic (Iberian Sea)', 'Ligurian Sea'), [3322, 3363]),
])
def test_the_seas_by_their_mrgids_or_names(value, mrgids):
	assert seas.codes(value) == mrgids


@pytest.mark.parametrize('value', [[], 'Alboran', 'Atlantis', 99999, ['Alboran Sea', 'x'], True, None, '33.24'])
def test_what_is_not_a_sea_says_how_to_find_them(value):
	with pytest.raises(ValueError, match=r"sea is the MRGID of a sea area of the IHO \(e.g. 3324\) or its name .* "
	                                     r"\(find them with find_seas\)"):
		seas.codes(value)


# The region, checked without Earth Engine, and its calls of Earth Engine ----------------------------------------

class _NoEarthEngine:
	def __getattr__(self, name):
		pytest.fail(f'Earth Engine was asked for {name} before the region was checked')


def test_the_region_is_checked_without_earth_engine(monkeypatch):
	assert 'sea' in areas.REGION_KEYS and 'sea_at' in areas.REGION_KEYS
	assert areas.check({'sea': 'Alboran Sea'}) == 'sea' and areas.check({'sea_at': [-2.5, 36]}) == 'sea_at'
	assert areas.check({'wdpa_id': 1, 'within': {'sea': ALBORAN}}) == 'wdpa_id'
	monkeypatch.setattr(areas, 'ee', _NoEarthEngine())
	for region, words in (({'sea': 'Atlantis'}, 'find_seas'), ({'sea': []}, 'none given'),
	                      ({'sea_at': [-2.5]}, 'sea_at is a point'), ({'sea_at': 'Alboran'}, 'sea_at is a point'),
	                      ({'sea': ALBORAN, 'country': 'ESP'}, 'give one region'),
	                      ({'country': 'ESP', 'within': {'sea': 'Atlantis'}}, 'find_seas')):
		with pytest.raises(ValueError, match=words):
			areas.region(region)


def test_the_calls_of_earth_engine_of_a_sea(monkeypatch):
	"""{"sea": ...}: the table of the seas filtered by their MRGIDs (the names turned into them by the index); {"sea_at":
	[lon, lat]}: the sea at the point. Their features are named by the table (name)."""
	from test_regions import _chain
	assert _chain(monkeypatch, {'sea': ['Alboran Sea', WESTERN]}) == [
		['FeatureCollection', seas.ASSET], ['Filter.inList', 'mrgid', [ALBORAN, WESTERN]], ['filter', '<ee>']]
	assert _chain(monkeypatch, {'sea': ALBORAN}) == _chain(monkeypatch, {'sea': 'alboran sea'})
	assert _chain(monkeypatch, {'sea_at': [-2.5, 36]}) == [
		['FeatureCollection', seas.ASSET], ['Geometry.Point', [-2.5, 36.0]], ['filterBounds', '<ee>']]


def test_is_sea():
	assert areas.is_sea({'sea': 1}) and areas.is_sea({'sea_at': [0, 0]})
	assert areas.is_sea({'bbox': [0, 0, 1, 1], 'within': {'sea': ALBORAN}})
	assert not areas.is_sea({'country': 'ESP'}) and not areas.is_sea(None) and not areas.is_sea('sea')


# The pixels of the large areas -------------------------------------------------------------------------------------

def _old_rule(native, area, target):
	"""The automatic pixel before the large areas (timeseries.auto_scale and classes.scale_for until 0.3.58)."""
	need = math.sqrt(area / target) if area else native
	if need <= native:
		return float(native)
	nice = [m * 10 ** e for e in range(1, 6) for m in (1, 2, 5)]
	return float(next((n for n in nice if n >= need), nice[-1]))


@pytest.mark.parametrize('native, km2, target, metres', [
	(10, 120_000, 1e6, 1000.0),          # Sentinel-2 just over 100,000 km²: 1 km (it was 500 m)
	(250, 54_482, 1e6, 250.0),           # the Alboran Sea: not a large area, as before
	(250, 506_000, 1e6, 1000.0),         # Spain
	(250, 3_000_000, 1e6, 2000.0),       # about a million pixels
	(4616, 475_507, 1e6, 4616.0),        # the western Mediterranean with the Chl-a of MODIS: its 4.6 km
	(250, 76_681_173, 1e6, 10000.0),     # the South Pacific Ocean: 10 km at most
	(27830, 76_681_173, 1e6, 27830.0),   # OISST, of 28 km: never finer than the data
	(30, 200_000, 1e7, 1000.0),          # the areas by class (more pixels): 1 km too
	(30, 100_000, 1e6, 500.0),           # 100,000 km² is not more than 100,000 km²
])
def test_the_pixel_of_a_large_area_is_1_to_10_km(native, km2, target, metres):
	assert areas.default_scale(native, km2 * 1e6, target) == metres


def test_the_smaller_regions_keep_their_pixel():
	"""Up to 100,000 km², the rule of before: that of the data, or bigger for about TARGET pixels."""
	for native in (10, 20, 30, 100, 250, 463, 500, 1000, 4616, 11132):
		for km2 in (0, 0.01, 1, 10, 100, 1000, 5000, 20_000, 50_000, 99_999, 100_000):
			for target in (1e6, 1e7):
				assert areas.default_scale(native, km2 * 1e6, target) == _old_rule(native, km2 * 1e6, target)
	assert areas.LARGE_AREA_KM2 == 100_000 and areas.LARGE_PIXEL == (1000, 10000)
	assert not areas.is_large(1e11) and areas.is_large(1e11 + 1) and not areas.is_large(0)


def test_the_statistics_and_the_areas_use_the_rule(monkeypatch):
	monkeypatch.setattr(areas, 'max_area', lambda regions: 476_707e6)
	monkeypatch.setattr(timeseries.variable, 'native_scale', lambda spec: 250)
	assert timeseries.auto_scale({}, None) == 1000.0
	assert classes.scale_for(30, None) == 1000.0
	monkeypatch.setattr(areas, 'max_area', lambda regions: 50_000e6)
	assert timeseries.auto_scale({}, None) == 250 and classes.scale_for(30, None) == 100.0


# What the results say ----------------------------------------------------------------------------------------------

def test_the_references_and_the_credit_of_marine_regions():
	for region in ({'sea': ALBORAN}, {'sea_at': [-2.5, 36]}, {'bbox': [-3, 36, -2, 37], 'within': {'sea': ALBORAN}}):
		cited = references.cite('time_series', {'region': region, 'variable': 'Chl-a', 'sensor': 'Modis',
		                                        'start': '2020-01-01', 'end': '2020-12-31'})
		assert any(r['doi'] == '10.14284/699' and 'Flanders Marine Institute (2024)' in r['text']
		           for r in cited['references']), region
		assert seas.CREDIT in cited['credits'] and 'CC BY 4.0' in seas.CREDIT
	assert catalog.load()['datasets'][seas.ASSET] == {'references': ['vliz_eez_iho2024'], 'credit': seas.CREDIT}
	assert any('10.14284/699' in r for r in json.loads(_read('.zenodo.json'))['references'])


def test_the_sea_is_named_in_the_readmes_reports_and_titles():
	assert report.region_text({'sea': ALBORAN}) == 'Alboran Sea (IHO sea area, Marine Regions)'
	assert report.region_text({'sea': ['alboran sea', WESTERN]}) == (
		'Alboran Sea (IHO sea area, Marine Regions); Mediterranean Sea - Western Basin (IHO sea area, Marine Regions)')
	assert report.region_text({'sea': 99999}) == 'Sea 99999 (IHO sea area, Marine Regions)'
	assert report.region_text({'sea': ALBORAN}, {'sea:3324': 'Alboran Sea'}).startswith('Alboran Sea (IHO')
	assert report.region_text({'sea_at': [-2.5, 36]}) == ('Sea at the point 36, -2.5 (lat., lon.; IHO sea areas, Marine '
	                                                      'Regions)')
	args = {'region': {'sea': ALBORAN}, 'variable': 'Chl-a', 'sensor': 'Modis', 'start': '2020-01-01',
	        'end': '2020-12-31'}
	assert report.item_facts('time_series', args, None)[0] == ('Region', 'Alboran Sea (IHO sea area, Marine Regions)')
	text = readme.text('time_series', args, {'unit': '[mg m⁻³]'})
	assert 'Alboran Sea (IHO sea area, Marine Regions)' in text and "{'sea'" not in text


def test_only_the_chlorophyll_of_modis_has_data_at_sea():
	assert 'sea' in catalog.load()['fields']
	assert sorted((e['index'], e['col']) for e in catalog.variables() if e.get('sea')) == [
		('Chl-a', 'NASA/OCEANDATA/MODIS-Aqua/L3SMI'), ('Chl-a', 'NASA/OCEANDATA/MODIS-Terra/L3SMI')]


def test_a_variable_of_the_land_over_a_sea_warns():
	warning = services.sea_warning({'region': {'sea': ALBORAN}, 'variable': 'NDVI', 'sensor': 'Modis'})
	assert warning == ('NDVI of Modis has no data over the open sea: its data are of the land (Sentinel-2 and Landsat '
	                   'see the coastal waters only). Over a sea, use Chl-a (Modis).')
	assert services.sea_warning({'region': {'sea_at': [-2.5, 36]}, 'variable': 'LST', 'sensor': 'Landsat'})
	assert services.sea_warning({'region': {'bbox': [0, 0, 1, 1], 'within': {'sea': 1}}, 'variable': 'EVI',
	                             'sensor': 'Sentinel-2'})
	for args in ({'region': {'sea': ALBORAN}, 'variable': 'Chl-a', 'sensor': 'Modis'},
	             {'region': {'sea': ALBORAN}, 'variable': 'Chl-a', 'sensor': 'Modis',
	              'collection': 'NASA/OCEANDATA/MODIS-Terra/L3SMI'},
	             {'region': {'country': 'ESP'}, 'variable': 'NDVI', 'sensor': 'Modis'},
	             {'region': {'sea': ALBORAN}, 'variable': 'NOAA/CDR/OISST/V2_1', 'collection': 'NOAA/CDR/OISST/V2_1'},
	             {'region': {'sea': ALBORAN}, 'image': 'X', 'variable': None},
	             {'region': {'sea': ALBORAN}}):
		assert services.sea_warning(args) is None, args


def test_the_results_have_the_warning(monkeypatch, tmp_path):
	"""Every tool of the services (_cited) adds it to the warnings of its result, after those of its period."""
	monkeypatch.chdir(tmp_path)

	@services._cited
	def region_stats(region, variable=None, sensor=None, start=None, end=None, **source):
		return {'warnings': ['The images of ... end on ...']}

	out = region_stats({'sea': ALBORAN}, 'NDVI', 'Modis', '2020-01-01', '2020-12-31')
	assert out['warnings'][0] == 'The images of ... end on ...' and 'no data over the open sea' in out['warnings'][1]
	assert region_stats({'sea': ALBORAN}, 'Chl-a', 'Modis', '2020-01-01', '2020-12-31')['warnings'] == [
		'The images of ... end on ...']


# The table: the parts dissolved by sea (GDAL) ---------------------------------------------------------------------

def test_the_parts_are_dissolved_by_sea(tmp_path, monkeypatch):
	"""Two parts of a sea (two EEZs) are one polygon with the sum of their areas; another sea, its own; the index has
	their MRGID, name, area and bounds, by name."""
	pytest.importorskip('osgeo')

	def part(mrgid, name, area, w, e):
		return {'type': 'Feature', 'properties': {'iho_mrgid': mrgid, 'iho_sea': name, 'area_km2': area},
		        'geometry': {'type': 'Polygon', 'coordinates': [[[w, 0], [e, 0], [e, 1], [w, 1], [w, 0]]]}}

	with open(tmp_path / 'parts.geojson', 'w', encoding='utf-8') as f:
		for p in (part(2, 'B Sea', 10, 0, 1), part(2, 'B Sea', 10, 1, 2), part(1, 'A Sea', 200_000, 5, 6.000004)):
			f.write(json.dumps(p) + '\n')
	assert seas.dissolve(str(tmp_path), progress=None) == 2
	rows = [json.loads(line) for line in open(tmp_path / 'seas.geojson', encoding='utf-8')]
	assert [r['properties'] for r in rows] == [
		{'mrgid': 1, 'name': 'A Sea', 'area_km2': 200000, 'bounds': [5.0, 0.0, 6.0, 1.0]},
		{'mrgid': 2, 'name': 'B Sea', 'area_km2': 20, 'bounds': [0.0, 0.0, 2.0, 1.0]}]
	assert rows[1]['geometry']['type'] == 'MultiPolygon' and len(rows[1]['geometry']['coordinates']) == 1  # one
	assert rows[0]['geometry']['coordinates'][0][0][1] == [6.0, 0.0]  # rounded to DIGITS decimals
	monkeypatch.setattr(seas, 'INDEX', str(tmp_path / 'seas.json.gz'))
	assert seas.make_index(str(tmp_path), '2024-10-09') == 2
	with gzip.open(tmp_path / 'seas.json.gz', 'rt', encoding='utf-8') as f:
		idx = json.load(f)
	assert idx['rows'] == [[1, 'A Sea', 200000, [5.0, 0.0, 6.0, 1.0]], [2, 'B Sea', 20, [0.0, 0.0, 2.0, 1.0]]]
	assert (seas.TOLERANCE, seas.LARGE_TOLERANCE, seas.LARGE_KM2) == (0.001, 0.01, 100_000)


# The tools ---------------------------------------------------------------------------------------------------------

def test_the_command_line_without_earth_engine(capsys, monkeypatch):
	def refused(*args, **kw):
		raise AssertionError('Earth Engine used')
	monkeypatch.setattr(services, 'init', refused)
	monkeypatch.setattr(services, 'eecu_warning', refused)
	cli.main(['seas', 'alborán'])
	out = capsys.readouterr().out
	assert 'MRGID' in out and '3324' in out and 'Alboran Sea' in out and '-5.354 35.071 -1.188 36.842' in out
	cli.main(['seas', 'atlantis'])
	assert 'try its English name' in capsys.readouterr().err
	assert 'monitoreo seas TEXT' in cli.__doc__ and '{"sea": "Alboran Sea"}' in cli.__doc__
	assert '1 to 10 km' in cli.__doc__


def test_the_mcp_server_and_the_assistant():
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	found = json.loads(mcp_server.find_seas('alboran'))
	assert found[0]['MRGID'] == ALBORAN
	assert '{"sea": 3324} or {"sea": "Alboran Sea"}' in mcp_server.INSTRUCTIONS and 'find_seas' in mcp_server.INSTRUCTIONS
	from monitoreo import assistant
	assert 'find_seas' in assistant.ADVICE and 'find_seas' in assistant.LABELS
	assert '{"sea": 3324}: Alboran Sea (54,482 km²)' in assistant.seas_text(found)
	assert 'No ocean or sea with that name' in assistant.seas_text([])
	both = json.loads(mcp_server.find_seas('mediterranean'))
	assert assistant.seas_must_choose(both, 'mediterranean') and not assistant.seas_must_choose(found, 'alboran')
	assert not assistant.seas_must_choose(both, 'mediterranean', 'the sea 4279 please')
	assert '{"sea": MRGID}' in assistant.PROMPT and 'sea_at' in assistant.PROMPT


def test_the_assistant_refuses_the_mrgids_it_did_not_find():
	from monitoreo import assistant
	a = assistant.Assistant.__new__(assistant.Assistant)
	a.names, a.messages, a.documents = {}, [{'role': 'user', 'content': 'Chl-a of the Alboran Sea'}], []
	a.user_text = lambda: 'Chl-a of the Alboran Sea'
	a.document_numbers = lambda: set()
	assert a.unknown_seas({'region': {'sea': ALBORAN}}) == [ALBORAN]
	assert a.unknown_seas({'region': {'sea': 'Alboran Sea'}}) == []  # names: checked by the index when computed
	assert a._remember_seas(json.dumps(seas.find('alboran'))) == seas.find('alboran')
	assert a.names['sea:3324'] == 'Alboran Sea' and a.unknown_seas({'region': {'sea': [3324]}}) == []
	assert a.unknown_seas({'region': {'bbox': [0, 0, 1, 1], 'within': {'sea': '4279'}}}) == ['4279']
	a.user_text = lambda: 'the sea 4279'
	assert a.unknown_seas({'region': {'sea': 4279}}) == []


def test_the_page_of_the_assistant_lists_the_seas():
	page = _read('src', 'monitoreo', 'ui', 'assistant.html')
	assert "else if (e.type === 'seas') $('chat').append(seasCard(e));" in page
	assert 'function seasCard(e)' in page and '`, sea ${s.MRGID}`' in page


def test_the_qgis_plugin_and_the_r_package():
	dock = _read('qgis', 'monitoreo_qgis', 'dock.py')
	assert "('Sea or ocean (IHO)', 'sea')" in dock and "('Sea at the center of the map', 'sea_point')" in dock
	assert 'def search_seas(self):' in dock and "return {'sea': self.sea.currentData()}" in dock
	helps = _read('qgis', 'monitoreo_qgis', 'helptexts.py')
	assert "'sea':" in helps and 'https://doi.org/10.14284/699' in helps and '1 to 10 km' in helps
	r = _read('r', 'monitoreo', 'R', 'monitoreo.R')
	assert 'mo_seas <- function(text, limit = 20)' in r and 'services()$find_seas' in r
	assert 'mo_sea <- function(id = NULL, lon = NULL, lat = NULL)' in r
	namespace = _read('r', 'monitoreo', 'NAMESPACE')
	assert 'export(mo_sea)' in namespace and 'export(mo_seas)' in namespace
	assert os.path.exists(os.path.join(ROOT, 'r', 'monitoreo', 'man', 'mo_seas.Rd'))
	assert 'mo_sea(3324)' in _read('r', 'monitoreo', 'man', 'regions.Rd')


def test_the_help_of_the_tools_says_the_pixels_of_the_large_areas():
	mcp = _read('src', 'monitoreo', 'mcp_server.py')
	assert 'computed by default on pixels of 1 to 10 km' in mcp
	assert '1 to 10 km' in _read('src', 'monitoreo', 'assistant.py')


def test_the_mcp_tools_list_has_find_seas():
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	names = [t.name for t in asyncio.run(mcp_server.server.list_tools())]
	assert 'find_seas' in names
