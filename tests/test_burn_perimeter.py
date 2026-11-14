"""The perimeter of the burned area of burn_severity (fire.perimeter, services.burn_severity with perimeter): the value
from which a pixel is burned, the arguments checked before computing anything, the vector file of its polygons, its
README and facts, and the study area that the assistant makes of it; without Earth Engine (fire.perimeter is faked:
tests/test_gee.py computes it in Earth Engine, in Python and in the app)."""

import asyncio
import json
import os

import pytest

from monitoreo import areas, fire, readme, report, services

REGION = {'bbox': [-5.23, 36.47, -5.10, 36.57]}  # the fire of Sierra Bermeja, September 2021
PERIODS = dict(start='2021-07-15', end='2021-08-31', other_start='2021-09-20', other_end='2021-10-31')
# 4 pixels of 0.001° (one of them touching the others only by a corner: an invalid ring, as reduceToVectors gives
# them with eight neighbours) with a hole, and a square apart
LON, LAT = -5.2, 36.5
_d = 0.001
RING = [[LON, LAT], [LON + 2 * _d, LAT], [LON + 2 * _d, LAT + _d], [LON + 3 * _d, LAT + _d],
        [LON + 3 * _d, LAT + 2 * _d], [LON + 2 * _d, LAT + 2 * _d], [LON + 2 * _d, LAT + _d], [LON, LAT + _d],
        [LON, LAT]]
SQUARE = [[LON + 5 * _d, LAT], [LON + 6 * _d, LAT], [LON + 6 * _d, LAT + _d], [LON + 5 * _d, LAT + _d],
          [LON + 5 * _d, LAT]]
FEATURES = [  # as fire.perimeter gives them (getInfo): a feature for each feature of the region
	{'type': 'Feature', 'geometry': {'type': 'MultiPolygon', 'coordinates': [[RING], [SQUARE]]},
	 'properties': {'name': 'west', 'ha': 3.5, 'patches': 2}},
	{'type': 'Feature', 'geometry': {'type': 'MultiPolygon', 'coordinates': []},
	 'properties': {'name': 'east', 'ha': 0, 'patches': 0}},
]


def test_the_value_from_which_a_pixel_is_burned():
	assert fire.burned_min('dNBR') == fire.BURNED == 0.1
	assert fire.burned_min('RdNBR') == fire.RDNBR_BURNED == 0.069
	assert fire.burned_min('dNBR', '0.27') == 0.27  # the one given, for every index
	assert fire.burned_min('RBR', 0.1) == 0.1
	with pytest.raises(ValueError, match='the RBR has no classes: give burned_min'):
		fire.burned_min('RBR')
	assert fire.PERIMETER_MIN_HA == 1.0
	assert fire.PERIMETER_FIELDS == ['region', 'ha', 'patches', 'index', 'burned_min', 'min_ha', 'sensor', 'before',
	                                 'after']
	assert set(readme.FIELDS) == set(fire.PERIMETER_FIELDS)  # every field is explained in the README


@pytest.mark.parametrize('kw, error', [
	({'perimeter': 'fire.gpkg', 'index': 'RBR'}, 'the RBR has no classes: give burned_min'),
	({'perimeter': 'fire.kml'}, 'write the polygons to a file .gpkg, .geojson, .shp, not fire.kml'),
	({'perimeter': 'fire.gpkg', 'min_ha': -1}, 'min_ha, the smallest burned patch and unburned island'),
	({'burned_min': 0.2}, 'burned_min and min_ha are for the perimeter of the burned area: give also perimeter'),
	({'min_ha': 0}, 'burned_min and min_ha are for the perimeter of the burned area'),
])
def test_the_arguments_of_the_perimeter_are_checked_before_computing(monkeypatch, kw, error):
	"""A wrong perimeter is the user's mistake: a clear message, before Earth Engine computes anything."""
	monkeypatch.setattr(areas, 'region', lambda spec: pytest.fail('computed before checking the perimeter'))
	with pytest.raises(ValueError, match=error):
		services.burn_severity(REGION, 'Sentinel-2', **PERIODS, **kw)


def test_the_arguments_of_the_perimeter():
	outline = services._perimeter_args('dNBR', 'fire.gpkg', None, None, 'Sentinel-2', ('2021-07-15', '2021-08-31'),
	                                   ('2021-09-20', '2021-10-31'))
	assert outline == {'path': 'fire.gpkg', 'index': 'dNBR', 'burned_min': 0.1, 'min_ha': 1.0, 'sensor': 'Sentinel-2',
	                   'before': '2021-07-15/2021-08-31', 'after': '2021-09-20/2021-10-31'}
	assert services._perimeter_args('RdNBR', 'x.geojson', None, 0, 'Modis', ('a', 'b'), ('c', 'd'))['min_ha'] == 0
	assert services._perimeter_args('dNBR', None, None, None, 'Sentinel-2', ('a', 'b'), ('c', 'd')) is None


@pytest.mark.parametrize('ext', ['gpkg', 'geojson', 'shp'])
def test_the_polygons_are_written_valid_with_their_fields(tmp_path, ext):
	pytest.importorskip('osgeo')
	from osgeo import ogr
	rows = [dict(r, index='dNBR', burned_min=0.1, min_ha=1.0, sensor='Sentinel-2', before='2021-07-15/2021-08-31',
	             after='2021-09-20/2021-10-31') for r in fire.perimeter_rows(FEATURES)]
	path = areas.save_polygons(rows, str(tmp_path / f'fire.{ext}'), 'perimeter', fire.PERIMETER_TYPES)
	ds = ogr.Open(path)
	lyr = ds.GetLayer(0)
	assert lyr.GetSpatialRef().GetAuthorityCode(None) == '4326'
	assert [lyr.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(lyr.GetLayerDefn().GetFieldCount())] == \
	       fire.PERIMETER_FIELDS
	west, east = list(lyr)
	assert (west['region'], west['ha'], west['patches'], west['index'], west['burned_min']) == \
	       ('west', 3.5, 2, 'dNBR', 0.1)
	assert (west['before'], west['after']) == ('2021-07-15/2021-08-31', '2021-09-20/2021-10-31')
	g = west.GetGeometryRef()
	assert g.IsValid() and ogr.GT_Flatten(g.GetGeometryType()) == ogr.wkbMultiPolygon
	assert g.GetGeometryCount() == 3  # the pixel joined by a corner, a polygon of its own
	assert abs(g.GetArea() - 4 * _d * _d) < 1e-12  # 3 pixels and the square: nothing lost
	assert east['region'] == 'east' and east['ha'] == 0 and east.GetGeometryRef() is None  # no burned pixel
	info = areas.describe_file(path)
	assert info['name_field'] == 'region'  # as a region: {'file': path, 'name_field': 'region'}
	ds = None
	areas.save_polygons(rows[:1], path, 'perimeter', fire.PERIMETER_TYPES)  # written again over the old one
	assert ogr.Open(path).GetLayer(0).GetFeatureCount() == 1


class _Computed:
	def __init__(self, features):
		self.features = features

	def getInfo(self):
		return {'type': 'FeatureCollection', 'features': self.features}


def test_burn_severity_writes_the_perimeter_and_answers_its_hectares(monkeypatch, tmp_path):
	pytest.importorskip('osgeo')
	got = {}

	def perimeter(value, burned_min, regions, scale, crs, min_ha):
		got.update(value=value, burned_min=burned_min, regions=regions, scale=scale, crs=crs, min_ha=min_ha)
		return _Computed(FEATURES)

	monkeypatch.setattr(fire, 'perimeter', perimeter)
	path = str(tmp_path / 'fire.geojson')
	outline = services._perimeter_args('RBR', path, 0.12, 2, 'Landsat', ('a', 'b'), ('c', 'd'))
	out = services._burn_perimeter('rbr image', 'regions', 30.0, 'EPSG:32630', outline)
	assert got == {'value': 'rbr image', 'burned_min': 0.12, 'regions': 'regions', 'scale': 30.0, 'crs': 'EPSG:32630',
	               'min_ha': 2.0}
	assert out == {'perimeter': path, 'perimeter_ha': {'west': 3.5, 'east': 0.0},
	               'perimeter_patches': {'west': 2, 'east': 0}, 'burned_min': 0.12, 'min_ha': 2.0}
	with open(path, encoding='utf-8') as f:
		written = json.load(f)
	assert [x['properties']['region'] for x in written['features']] == ['west', 'east']
	assert written['features'][0]['properties']['index'] == 'RBR'
	assert written['features'][0]['properties']['sensor'] == 'Landsat'


def test_the_readme_explains_the_perimeter(tmp_path):
	pytest.importorskip('osgeo')
	path = str(tmp_path / 'burn_severity_perimeter.gpkg')
	areas.save_polygons(fire.perimeter_rows(FEATURES), path, 'perimeter', fire.PERIMETER_TYPES)
	args = dict(REGION=None, region=REGION, sensor='Sentinel-2', **PERIODS, perimeter=path, min_ha=2)
	del args['REGION']
	result = {'index': 'dNBR', 'classes': fire.table([{'class': 1, 'sum': 3.0}], 'bbox'), 'burned_ha': {'bbox': 3.0},
	          'perimeter': path, 'perimeter_ha': {'bbox': 3.5}, 'perimeter_patches': {'bbox': 2}, 'burned_min': 0.1,
	          'min_ha': 2.0, 'scale': 10.0}
	text = readme.text('burn_severity', args, result)
	flat = ' '.join(text.split())
	assert 'burn_severity_perimeter.gpkg: polygons (GeoPackage, EPSG:4326, layer perimeter)' in flat
	assert 'FIELDS OF burn_severity_perimeter.gpkg' in text
	for k, v in readme.FIELDS.items():
		assert f"{k}: {' '.join(v.split())}" in flat, k
	assert "region {'file': 'burn_severity_perimeter.gpkg', 'name_field': 'region'}" in flat
	assert 'UDUNITS ha' in flat
	# the call to reproduce it writes the same file, by its name (not the folder of this computer)
	assert 'perimeter="burn_severity_perimeter.gpkg"' in flat and str(tmp_path) not in flat
	assert 'min_ha=2' in flat
	assert ('Perimeter of the burned area: polygons of the pixels with dNBR ≥ 0.1, without the patches of less than '
	        '2 ha and with the unburned islands of less than 2 ha filled: 3.5 ha in 2 patches') in flat
	assert readme.document('burn_severity', args, result) == str(tmp_path / 'burn_severity_perimeter.README.txt')


def test_the_facts_of_the_perimeter():
	result = {'perimeter': 'x.gpkg', 'perimeter_ha': {'west': 3.5, 'east': 0.0},
	          'perimeter_patches': {'west': 2, 'east': 0}, 'burned_min': 0.069, 'min_ha': 0}
	facts = dict(report.item_facts('burn_severity', dict(region=REGION, index='RdNBR', **PERIODS), result))
	assert facts['Perimeter of the burned area'] == ('polygons of the pixels with RdNBR ≥ 0.069: west: 3.5 ha in 2 '
	                                                 'patches; east: 0 ha in 0 patches')
	assert 'Perimeter of the burned area' not in dict(report.item_facts('burn_severity', dict(region=REGION,
	                                                                                           **PERIODS), {}))


def test_the_assistant_makes_the_perimeter_a_study_area(tmp_path, monkeypatch):
	"""The perimeter of a burn severity becomes a study area of the user, burned_area_<result>, that the model gives as
	the region of the next analyses; a perimeter without polygons does not."""
	pytest.importorskip('osgeo')
	from monitoreo import assistant
	monkeypatch.setattr(assistant, 'LAYERS', str(tmp_path / 'capas'))
	monkeypatch.setattr(assistant, 'LOG', str(tmp_path / 'assistant.log'))
	path = str(tmp_path / 'burn_severity_perimeter.gpkg')
	areas.save_polygons(fire.perimeter_rows(FEATURES[:1]), path, 'perimeter', fire.PERIMETER_TYPES)
	a = assistant.Assistant({**assistant.DEFAULTS})
	item = {'id': 3, 'result': {'perimeter': path, 'perimeter_ha': {'west': 3.5}}}
	assert a.perimeter_area(item) == 'burned_area_3'
	layer = a.layers['burned_area_3']
	assert layer['features'] == 1 and layer['name_field'] == 'region'
	assert a.with_layer({'region': {'layer': 'burned_area_3'}})['region'] == {'file': layer['file'],
	                                                                          'name_field': 'region'}
	assert '- burned_area_3 (1 polygon' in a.system_prompt()
	assert a.perimeter_area({'id': 4, 'result': {'perimeter': path, 'perimeter_ha': {'west': 0}}}) is None
	assert a.perimeter_area({'id': 5, 'result': {'csv': 'x.csv'}}) is None
	assert a.perimeter_area({'id': 6, 'result': {'perimeter': str(tmp_path / 'gone.gpkg'),
	                                             'perimeter_ha': {'w': 1}}}) is None


def test_the_assistant_shows_the_perimeter_and_tells_the_model(tmp_path, monkeypatch):
	"""A burn severity with its perimeter: its file in the card, the study area in the page and, for the model, the
	region of the analyses inside it."""
	pytest.importorskip('osgeo')
	from monitoreo import assistant
	monkeypatch.setattr(assistant, 'LAYERS', str(tmp_path / 'capas'))
	monkeypatch.setattr(assistant, 'LOG', str(tmp_path / 'assistant.log'))
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)
	path = str(tmp_path / 'burn_severity_perimeter.gpkg')
	areas.save_polygons(fire.perimeter_rows(FEATURES[:1]), path, 'perimeter', fire.PERIMETER_TYPES)
	answer = {'index': 'dNBR', 'classes': fire.table([{'class': 1, 'sum': 3.0}], 'west'), 'burned_ha': {'west': 3.0},
	          'title': 'Burn severity (dNBR, USGS)', 'scale': 10.0, 'perimeter': path, 'perimeter_ha': {'west': 3.5},
	          'perimeter_patches': {'west': 2}, 'burned_min': 0.1, 'min_ha': 1.0}

	class Fake(assistant.Assistant):
		async def call(self, name, args):
			self.called = (name, args)
			return None, [json.dumps(answer)], []

	string, boolean = {'type': 'string'}, {'type': 'boolean'}
	tools = [{'name': 'burn_severity', 'description': 'Burn severity.', 'inputSchema': {'type': 'object', 'properties': {
		'region': {'type': 'object', 'additionalProperties': True}, 'start': string, 'end': string,
		'other_start': string, 'other_end': string, 'perimeter': boolean}}}]

	async def run():
		a = Fake({**assistant.DEFAULTS, 'project': 'p'})
		a.tools = assistant.model_tools(tools)
		events = [e async for e in a.run_tool({'name': 'burn_severity', 'arguments': dict(
			region=REGION, perimeter=True, **PERIODS)})]
		return a, events

	a, events = asyncio.run(run())
	assert a.called[1]['perimeter'] is True
	card = next(e for e in events if e['type'] == 'result')
	assert os.path.basename(path) in [f['name'] for f in card['files']]
	assert dict(card['facts'])['Perimeter of the burned area'].endswith('3.5 ha in 2 patches')
	shown = next(e for e in events if e['type'] == 'layers')
	assert [x['name'] for x in shown['layers']] == ['burned_area_1']
	assert any('study area «burned_area_1»' in e.get('text', '') for e in events if e['type'] == 'notice')
	told = a.messages[-1]['content']
	assert 'The perimeter of its burned area is the study area «burned_area_1»: region {"layer": "burned_area_1"}' \
	       in told
