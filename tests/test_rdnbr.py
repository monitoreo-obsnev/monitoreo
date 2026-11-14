"""The relative dNBR (RdNBR) of Miller & Thode 2007 (https://doi.org/10.1016/j.rse.2006.12.006), the third burn index
of burn_severity, with the severity classes of the article: its entries in the catalog (Sentinel-2, Landsat, MODIS
Terra and Aqua), its classes, legends and maps (monitoreo.fire), the checks of services.burn_severity, the pixel
filters of the daily surface reflectance of MODIS and its references, without Earth Engine (its arithmetic with a fake
ee). The last test computes it in Earth Engine (pytest -m ee, with EE_PROJECT)."""

import csv
import os
import types

import pytest

from monitoreo import catalog, fire, references, sensors, services, trends

REGION = {'bbox': [-5.23, 36.47, -5.10, 36.57]}  # the fire of Sierra Bermeja, September 2021
# the extended assessment of Miller & Thode 2007: the period after, one year after the fire, in the season of the
# period before
BEFORE, AFTER = ('2021-07-15', '2021-08-31'), ('2022-07-15', '2022-08-31')
TERRA, AQUA = 'MODIS/061/MOD09GA', 'MODIS/061/MYD09GA'
BANDS = ['rdnbr', 'severity', 'dnbr', 'nbr_before', 'nbr_after']


def _ids(cited):
	return [r['id'] for r in cited['references']]


# The catalog --------------------------------------------------------------------------------------------------------

def test_the_rdnbr_in_the_catalog():
	"""Entries 144 to 147: the NBR of B8 and B12 of Sentinel-2 (Howe et al. 2022), of NIR and SWIR2 of Landsat, and of
	bands 2 and 7 of the daily surface reflectance of MODIS Terra and Aqua (Veraverbeke et al. 2010), each with two
	periods (only burn_severity computes them)."""
	s2, landsat = catalog.find('RdNBR', 'Sentinel-2'), catalog.find('rdnbr', 'landsat')
	terra, aqua = catalog.find('RdNBR', 'Modis'), catalog.find('RdNBR', 'Modis', AQUA)
	assert (s2['ref'], s2['ft'], s2['m'], s2['col']) == (144, 'N(B8,B12)', 10, 'COPERNICUS/S2_SR_HARMONIZED')
	assert (landsat['ref'], landsat['ft'], landsat['m'], landsat['col']) == (145, 'N(nir,swir2)', 30, 'LANDSAT')
	assert (terra['ref'], terra['col'], terra['m']) == (146, TERRA, 500)  # Terra, the default of MODIS
	assert (aqua['ref'], aqua['col'], aqua['m']) == (147, AQUA, 500)
	assert catalog.find(None, ref=146)['col'] == TERRA and catalog.find(None, ref=147)['col'] == AQUA
	for e in (terra, aqua):
		assert e['ft'] == 'N(sur_refl_b02,sur_refl_b07)' and e['scale'] == 0.0001 and e['tr'] == 'daily'
		assert e['references'] == ['miller2007', 'howe2022', 'veraverbeke2010']
		assert '500 m' in e['notes']['m'] and 'approximate' in e['notes']['m']
	assert terra['dr'].startswith('2000/02/24') and aqua['dr'].startswith('2002/07/04')
	for e in (s2, landsat, terra, aqua):
		assert e['index'] == 'RdNBR' and e['sensor'] in ('Sentinel-2', 'Landsat', 'Modis')
		assert e['two_periods'] is True and e['unit'] == '[unitless]' and catalog.UDUNITS[e['unit']] == '1'
		assert e['vname_en'] == 'Relative differenced Normalized Burn Ratio'
		assert {'miller2007', 'howe2022'} <= set(e['references'])
		notes = e['notes']['f']
		assert '0.001' in notes and 'without the factor 1000' in notes and 'offset' in notes
		assert '0.069' in notes and '0.316' in notes and '0.641' in notes
	assert catalog.RDNBR_MIN_NBR == 0.001
	# the NBR and the RBR are unchanged
	assert catalog.find('NBR', 'Sentinel-2')['ref'] == 102 and not catalog.find('NBR', 'Sentinel-2').get('two_periods')
	assert catalog.find('RBR', 'Sentinel-2')['ft'] == 'N(B8A,B12)' and catalog.find('RBR', 'Landsat')['ref'] == 104
	with pytest.raises(KeyError):
		catalog.find('RBR', 'Modis')  # MODIS only for the RdNBR


def test_the_rdnbr_in_the_theme_fire_and_in_the_lists():
	assert catalog.theme_of('RdNBR')['key'] == 'fire' and catalog.theme_of('RdNBR')['analyses'] == ['burn_severity']
	assert [t for t in catalog.THEMES if t['key'] == 'fire'][0]['indices'] == ['NBR', 'RBR', 'RdNBR']
	rows = services.list_variables(text='RdNBR')
	assert [r['ref'] for r in rows] == [144, 145, 146, 147]
	assert all(r['two_periods'] and r['theme'] == 'Fire' and r['unit'] == '[unitless]' for r in rows)
	assert not any(r.get('rgb') for r in rows)  # no true colour: it compares two periods
	assert [r['ref'] for r in services.list_variables(text='RBR')] == [103, 104]  # not the RdNBR
	d = services.describe_variable('RdNBR', 'Modis', collection=AQUA)
	assert (d['ref'], d['col'], d['theme'], d['rgb']) == (147, AQUA, 'Fire', False)
	assert {'miller2007', 'howe2022', 'veraverbeke2010', 'myd09ga061'} <= set(_ids(d))


@pytest.mark.parametrize('sensor, collection', [('Sentinel-2', None), ('Landsat', None), ('Modis', None),
                                                ('Modis', AQUA)])
@pytest.mark.parametrize('tool, kwargs', [
	('time_series', {}), ('map_layer', {}), ('region_stats', {}), ('download_image', {'path': 'x.tif'}),
	('trend_table', {}), ('compare_series', {'other_start': AFTER[0], 'other_end': AFTER[1]}), ('rgb_map', {}),
	('download_rgb', {'path': 'x.tif'}),
])
def test_the_tools_of_one_period_refuse_it(tool, kwargs, sensor, collection):
	"""The RdNBR compares a period before and one after a fire: the other tools refuse it, before Earth Engine, and
	tell which tool computes it."""
	args = dict(kwargs, collection=collection) if collection else kwargs
	with pytest.raises(ValueError, match=rf"RdNBR \({sensor}\) compares a period before and a period after a fire: "
	                                     r"compute it with burn_severity and index 'RdNBR'"):
		getattr(services, tool)(REGION, 'RdNBR', sensor, *BEFORE, **args)


def test_specs_and_recipes_refuse_it_but_burn_severity():
	for sensor in ('Sentinel-2', 'Landsat', 'Modis'):
		with pytest.raises(ValueError, match="burn_severity and index 'RdNBR'"):
			services.make_spec('RdNBR', sensor, *BEFORE)
		with pytest.raises(ValueError, match="burn_severity and index 'RdNBR'"):  # download_variables
			services.variable_specs({'index': 'RdNBR', 'sensor': sensor, 'period': list(BEFORE), 'metric': 'median'})
	spec = services.make_spec('RdNBR', 'Modis', *BEFORE, two_periods=True, collection=AQUA)
	assert (spec['index'], spec['sensor'], spec['collection'], spec['period']) == ('RdNBR', 'Modis', AQUA, list(BEFORE))


# The classes of Miller & Thode 2007 -------------------------------------------------------------------------------

def test_the_classes_of_miller_and_thode():
	"""The RdNBR of their Table 4 (unchanged < 69, low 69-315, moderate 316-640, high >= 641) divided by 1000."""
	assert fire.RDNBR_SEVERITY == [(0, None, 'Unchanged'), (1, 0.069, 'Low severity'), (2, 0.316, 'Moderate severity'),
	                               (3, 0.641, 'High severity')]
	assert fire.RDNBR_BURNED == 0.069 == fire.RDNBR_SEVERITY[1][1]  # changed: classes low to high
	assert fire.RDNBR_COLOURS == {0: '0ae042', 1: 'fff70b', 2: 'ff641b', 3: 'a41fd6'}
	# the colours of UN-SPIDER of the classes of the dNBR of the same name (unburned, low, moderate-high, high)
	assert [fire.RDNBR_COLOURS[c] for c in range(4)] == [fire.COLOURS[c] for c in (0, 1, 3, 4)]
	assert fire.RDNBR_RANGE == (-1.2, 1.2)
	assert set(fire.CLASSES) == {'dNBR', 'RdNBR'} and fire.CLASSES['RdNBR']['key'] == 'rdnbr'
	assert fire.CLASSES['RdNBR']['classes'] is fire.RDNBR_SEVERITY and fire.CLASSES['dNBR']['classes'] is fire.SEVERITY
	assert fire.limits(0, 'RdNBR') == (None, 0.069) and fire.limits(1, 'RdNBR') == (0.069, 0.316)
	assert fire.limits(2, 'rdnbr') == (0.316, 0.641) and fire.limits(3, 'RdNBR') == (0.641, None)
	with pytest.raises(ValueError, match='has no classes'):
		fire.limits(1, 'RBR')  # a continuous index


def test_the_legend_of_the_rdnbr():
	legend = fire.legend('RdNBR')
	assert [c['value'] for c in legend] == [0, 1, 2, 3]
	assert [c['label'] for c in legend] == ['Unchanged', 'Low severity', 'Moderate severity', 'High severity']
	assert [c['color'] for c in legend] == ['#0ae042', '#fff70b', '#ff641b', '#a41fd6']
	assert all(set(c) == {'value', 'label', 'color', 'rdnbr_min', 'rdnbr_max'} for c in legend)
	assert (legend[0]['rdnbr_min'], legend[0]['rdnbr_max'], legend[-1]['rdnbr_min'], legend[-1]['rdnbr_max']) == (
		None, 0.069, 0.641, None)
	assert [fire.class_label(c) for c in legend] == ['Unchanged (RdNBR < 0.069)', 'Low severity (RdNBR 0.069 to 0.316)',
	                                                 'Moderate severity (RdNBR 0.316 to 0.641)',
	                                                 'High severity (RdNBR ≥ 0.641)']
	# the legend of the dNBR is unchanged, and the default
	dnbr = fire.legend()
	assert dnbr == fire.legend('dNBR') and [c['value'] for c in dnbr] == [c for c, _, _ in fire.SEVERITY]
	assert all(set(c) == {'value', 'label', 'color', 'dnbr_min', 'dnbr_max'} for c in dnbr)
	assert [c['color'] for c in dnbr] == ['#' + fire.COLOURS[c] for c, _, _ in fire.SEVERITY]
	assert fire.class_label(dnbr[0]) == 'Enhanced regrowth, high (dNBR < -0.25)'
	assert fire.class_label(dnbr[3]) == 'Low severity (dNBR 0.1 to 0.27)'
	assert fire.class_label(dnbr[-1]) == 'High severity (dNBR ≥ 0.66)'


def test_the_table_of_the_classes():
	"""The hectares of every class (0 for those without pixels), the rows of the CSV of burn_severity."""
	rows = fire.table([{'class': 1, 'sum': 120.5}, {'class': 3, 'sum': 30.0}, {'class': 0.0, 'sum': 7.25}], 'Bermeja',
	                  'RdNBR')
	assert [r['class'] for r in rows] == [0, 1, 2, 3] and all(r['region'] == 'Bermeja' for r in rows)
	assert [r['ha'] for r in rows] == [7.25, 120.5, 0.0, 30.0]
	assert [list(r) for r in rows] == [services.RDNBR_COLUMNS] * 4  # the columns of its CSV, in order
	assert (rows[2]['label'], rows[2]['rdnbr_min'], rows[2]['rdnbr_max']) == ('Moderate severity', 0.316, 0.641)
	assert fire.table(None, 'x', 'RdNBR')[3]['ha'] == 0.0
	# the table of the dNBR is unchanged
	dnbr = fire.table([{'class': 1, 'sum': 12.5}], 'Teide')
	assert len(dnbr) == 7 and [list(r) for r in dnbr] == [services.BURN_COLUMNS] * 7
	assert services.RDNBR_COLUMNS == ['region', 'class', 'label', 'rdnbr_min', 'rdnbr_max', 'ha']


def test_the_maps_of_the_rdnbr():
	"""The GeoTIFF of the RdNBR is drawn with the classes of its band severity, and an RdNBR without them with the
	reversed diverging ramp of the RBR from RDNBR_RANGE."""
	assert fire.index_of(BANDS) == 'RdNBR' and fire.index_of(['rdnbr']) == 'RdNBR'
	assert fire.index_of(['rbr', 'dnbr', 'nbr_before', 'nbr_after']) == 'RBR'
	assert fire.index_of(['dnbr', 'severity', 'nbr_before', 'nbr_after']) == 'dNBR'
	assert fire.index_of(['difference']) is None and fire.index_of(None) is None
	style = fire.map_style(BANDS)
	assert style == {'band': 2, 'classes': fire.legend('RdNBR')}
	alone = fire.map_style(['rdnbr'])
	assert alone == {'band': 1, 'min': -1.2, 'max': 1.2, 'palette': list(reversed(trends.DIVERGING))}
	# the dNBR and the RBR, as before
	assert fire.map_style(['dnbr', 'severity', 'nbr_before', 'nbr_after']) == {'band': 2, 'classes': fire.legend()}
	assert fire.map_style(['rbr', 'dnbr']) == {'band': 1, 'min': -0.5, 'max': 0.5,
	                                           'palette': list(reversed(trends.DIVERGING))}


class _Image:
	"""A fake ee.Image of numbers: the operations of fire.rdnbr, fire.rbr and fire.classify, pixel by pixel."""

	def __init__(self, values, mask=None):
		import numpy as np
		self.v = np.asarray(values, dtype=float)
		self.m = np.ones_like(self.v) if mask is None else np.asarray(mask, dtype=float)
		self.name = None

	def _of(self, x):
		return x.v if isinstance(x, _Image) else x

	def _new(self, v):
		return _Image(v, self.m)

	def divide(self, x):
		return self._new(self.v / self._of(x))

	def add(self, x):
		import numpy as np
		return _Image(self.v + self._of(x), np.broadcast_to(self.m, np.shape(self.v + self._of(x))))

	def abs(self):
		return self._new(abs(self.v))

	def max(self, x):
		import numpy as np
		return self._new(np.maximum(self.v, self._of(x)))

	def sqrt(self):
		return self._new(self.v ** 0.5)

	def gte(self, x):
		return self._new((self.v >= x).astype(float))

	def mask(self):
		return _Image(self.m)

	def updateMask(self, m):  # noqa: N802 (the name of Earth Engine)
		return _Image(self.v, m.v)

	def toInt8(self):  # noqa: N802
		return self._new(self.v.astype(int))

	def rename(self, name):
		self.name = name
		return self


@pytest.fixture
def fake_ee(monkeypatch):
	monkeypatch.setattr(fire, 'ee', types.SimpleNamespace(Image=types.SimpleNamespace(constant=_Image)))


def test_the_arithmetic_of_the_rdnbr(fake_ee):
	"""RdNBR = dNBR / sqrt(|NBR before|), with |NBR before| at least 0.001 (Howe et al. 2022), on the scale of the dNBR;
	and its classes, the pixels at a limit in the class above it."""
	dnbr, before = _Image([0.5, 0.5, 0.3, 0.02, -0.1]), _Image([0.25, -0.25, 0.0, 0.0001, 0.64])
	rdnbr = fire.rdnbr(dnbr, before)
	assert rdnbr.name == 'rdnbr'
	assert rdnbr.v.tolist() == pytest.approx([1.0, 1.0, 0.3 / 0.001 ** 0.5, 0.02 / 0.001 ** 0.5, -0.125])
	values = _Image([-0.5, 0.0, 0.0689, 0.069, 0.2, 0.316, 0.64, 0.641, 3.0], mask=[1, 1, 1, 1, 1, 1, 1, 1, 0])
	cls = fire.classify(values, 'RdNBR')
	assert cls.name == 'severity' and cls.v.tolist() == [0, 0, 0, 1, 1, 2, 2, 3, 3]
	assert cls.m.tolist() == values.m.tolist()  # masked as the RdNBR
	assert fire.classify(values, 'rdnbr').v.tolist() == cls.v.tolist()
	# the classes of the dNBR are unchanged, and the default
	dnbr = _Image([-0.3, -0.25, -0.1, 0.0, 0.1, 0.27, 0.44, 0.66, 1.0])
	assert fire.classify(dnbr).v.tolist() == [-2, -1, 0, 0, 1, 2, 3, 4, 4]
	assert fire.classify(dnbr, 'dNBR').v.tolist() == fire.classify(dnbr).v.tolist()
	assert fire.rbr(_Image([0.5]), _Image([0.499])).v.tolist() == pytest.approx([0.5 / 1.5])  # the RBR, unchanged


# services.burn_severity, before Earth Engine ---------------------------------------------------------------------

def test_burn_severity_checks_its_index_sensor_and_collection():
	with pytest.raises(ValueError, match='unknown burn index: use dNBR, RBR or RdNBR'):
		services.burn_severity(REGION, index='NDVI')
	assert services.BURN_INDICES == ('dNBR', 'RBR', 'RdNBR')
	assert services.BURN_SENSORS == {'dNBR': ('Sentinel-2', 'Landsat'), 'RBR': ('Sentinel-2', 'Landsat'),
	                                 'RdNBR': ('Sentinel-2', 'Landsat', 'Modis')}
	for index in ('dNBR', 'RBR', 'rbr'):  # MODIS only for the RdNBR
		with pytest.raises(ValueError, match='MODIS only with index RdNBR'):
			services.burn_severity(REGION, 'Modis', *BEFORE, *AFTER, index=index)
	with pytest.raises(ValueError, match='computed with the sensors Sentinel-2, Landsat, Modis, not Planet'):
		services.burn_severity(REGION, 'Planet', *BEFORE, *AFTER, index='RdNBR')
	for index in ('dNBR', 'RBR'):  # the collection of MODIS Aqua, only for the RdNBR
		with pytest.raises(ValueError, match='collection is only for the index RdNBR with sensor Modis'):
			services.burn_severity(REGION, 'Sentinel-2', *BEFORE, *AFTER, index=index, collection=AQUA)
	for sensor in (None, 'Sentinel-2', 'Landsat'):  # and with sensor Modis: not an Aqua labelled and cited as another
		with pytest.raises(ValueError, match='collection is only for the index RdNBR with sensor Modis'):
			services.burn_severity(REGION, sensor, *BEFORE, *AFTER, index='RdNBR', collection=AQUA)


@pytest.fixture
def rdnbr(monkeypatch):
	"""services._rdnbr faked (no Earth Engine): the arguments it gets, and an answer like that of Earth Engine."""
	calls = []

	def fake(region, sensor, start, end, other_start, other_end, metric, season, quality, resolution, crs, path, csv_,
	         max_pixels, tile, workers, progress, where=None, collection=None, outline=None):
		calls.append({'region': region, 'sensor': sensor, 'start': start, 'end': end, 'other_start': other_start,
		              'other_end': other_end, 'metric': metric, 'where': where, 'collection': collection,
		              'outline': outline})
		classes = fire.table([{'class': 1, 'sum': 600.0}, {'class': 3, 'sum': 400.0}, {'class': 0, 'sum': 50.0}],
		                     'bbox', 'RdNBR')
		return {'index': 'RdNBR', 'classes': classes, 'burned_ha': {'bbox': 1000.0}, 'scale': 500.0, 'csv': None,
		        'file': None, 'bands': None, 'title': f'Burn severity (RdNBR, Miller & Thode 2007) {sensor} ({metric})'}

	monkeypatch.setattr(services, '_rdnbr', fake)
	return calls


@pytest.mark.parametrize('index', ['RdNBR', 'rdnbr', 'RDNBR'])
@pytest.mark.parametrize('sensor', ['Sentinel-2', 'landsat', 'Modis', 'MODIS'])
def test_burn_severity_computes_the_rdnbr_with_every_sensor(rdnbr, index, sensor):
	"""Any case of the index and of the sensor; the answer cites the article, Howe et al. 2022 and the data."""
	out = services.burn_severity(REGION, sensor, *BEFORE, *AFTER, index=index)
	call = rdnbr[-1]
	assert (call['sensor'], call['start'], call['end'], call['other_start'], call['other_end'], call['metric']) == (
		sensor, *BEFORE, *AFTER, 'median')
	assert call['collection'] is None and call['where'] is None
	assert out['index'] == 'RdNBR' and {'miller2007', 'howe2022', 'gorelick2017', 'monitoreo'} <= set(_ids(out))
	assert not {'key2006', 'parks2014', 'silvacardoza2022'} & set(_ids(out))
	data = {'sentinel-2': 'esa_s2_l2a', 'landsat': 'usgs_landsat89', 'modis': 'mod09ga061'}[sensor.lower()]
	assert data in _ids(out)
	assert ('veraverbeke2010' in _ids(out)) == (sensor.lower() == 'modis')


def test_burn_severity_asks_the_rdnbr_for_its_perimeter(rdnbr):
	"""The perimeter of the RdNBR: from its changed pixels (0.069) by default; none unless asked for."""
	services.burn_severity(REGION, 'Sentinel-2', *BEFORE, *AFTER, index='RdNBR', perimeter='fire.gpkg')
	assert rdnbr[-1]['outline'] == {'path': 'fire.gpkg', 'index': 'RdNBR', 'burned_min': fire.RDNBR_BURNED,
	                                'min_ha': fire.PERIMETER_MIN_HA, 'sensor': 'Sentinel-2',
	                                'before': '/'.join(BEFORE), 'after': '/'.join(AFTER)}
	services.burn_severity(REGION, 'Sentinel-2', *BEFORE, *AFTER, index='RdNBR')
	assert rdnbr[-1]['outline'] is None


def test_burn_severity_with_modis_aqua(rdnbr):
	out = services.burn_severity(REGION, 'Modis', *BEFORE, *AFTER, index='RdNBR', collection=AQUA,
	                             where=[{'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 300}])
	assert rdnbr[-1]['collection'] == AQUA and rdnbr[-1]['where'][0]['variable'] == 'ELEVATION'
	assert {'miller2007', 'howe2022', 'veraverbeke2010', 'myd09ga061'} <= set(_ids(out))
	assert 'mod09ga061' not in _ids(out)


# The pixel filters of MODIS (MOD09GA, MYD09GA) ----------------------------------------------------------------------

class _QA:
	"""A fake band state_1km: the bit operations of sensors.PRODUCTS."""

	def __init__(self, values):
		import numpy as np
		self.v = np.asarray(values, dtype=np.int64)

	def select(self, name):
		assert name == 'state_1km'
		return self

	def rightShift(self, n):  # noqa: N802 (the names of Earth Engine)
		return _QA(self.v >> n)

	def bitwiseAnd(self, n):  # noqa: N802
		return _QA(self.v & n)

	def eq(self, n):
		return _QA((self.v == n).astype(int))

	def neq(self, n):
		return _QA((self.v != n).astype(int))

	def Or(self, other):  # noqa: N802
		return _QA(self.v | other.v)

	def And(self, other):  # noqa: N802
		return _QA(self.v & other.v)


def test_the_pixel_filters_of_modis():
	"""The four filters of MonitorEO with the band state_1km of MOD09GA and MYD09GA: clear or assumed clear (bits 0-1),
	without cloud shadow (bit 2) nor cloud of the internal algorithm (bit 10); land (bits 3-5 = 1); no snow (bit 15);
	aerosols not high (bits 6-7)."""
	assert sensors.PRODUCTS[TERRA] is sensors.PRODUCTS[AQUA]
	assert set(sensors.PRODUCTS[TERRA]) == {'clouds', 'water', 'snow', 'aerosols'}
	for col in (TERRA, AQUA):
		e = catalog.find('RdNBR', 'Modis', col)
		assert sensors.filters(e) == {'clouds': True, 'water': True, 'snow': True, 'aerosols': True}
		assert sensors.filters(e, {'snow': False, 'aerosols': False}) == {'clouds': True, 'water': True, 'snow': False,
		                                                                  'aerosols': False}
		assert all(e[f'{f}_bandQA'] == 'state_1km' for f in ('clouds', 'water', 'snow', 'aerosols'))
	land = 1 << 3
	qa = _QA([land, land | 1, land | 2, land | 3, land | 4, land | 1 << 10,  # clear, cloudy, mixed, assumed clear,
	          0, 3 << 3, land | 1 << 15, land | 1 << 6, land | 2 << 6, land | 3 << 6])  # shadow, internal cloud...
	p = sensors.PRODUCTS[TERRA]
	assert p['clouds'](qa).v.tolist() == [1, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1]
	assert p['water'](qa).v.tolist() == [1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1]  # shallow ocean, shallow inland water
	assert p['snow'](qa).v.tolist() == [1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1]
	assert p['aerosols'](qa).v.tolist() == [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0]  # low, average pass; high does not


# References ---------------------------------------------------------------------------------------------------------

def test_the_references_of_the_rdnbr():
	refs = catalog.load()['references']
	assert refs['miller2007']['doi'] == '10.1016/j.rse.2006.12.006'
	assert refs['howe2022']['doi'] == '10.3390/rs14205249'
	assert refs['veraverbeke2010']['doi'] == '10.1016/j.rse.2010.05.029'
	assert refs['miller2007']['citation'].startswith('Miller, J. D., & Thode, A. E. (2007). Quantifying burn severity')
	assert 'Remote Sensing of Environment, 109(1), 66–80' in refs['miller2007']['citation']
	assert 'Sentinel-2 and Landsat 8' in refs['howe2022']['citation']
	assert refs['veraverbeke2010']['citation'].startswith('Veraverbeke, S., Lhermitte, S., Verstraeten, W. W., & '
	                                                      'Goossens, R. (2010).')
	assert catalog.load()['methods']['rdnbr'] == ['miller2007', 'howe2022']
	assert {TERRA, AQUA} <= set(catalog.load()['datasets'])
	args = {'start': BEFORE[0], 'end': BEFORE[1], 'other_start': AFTER[0], 'other_end': AFTER[1], 'index': 'RdNBR',
	        'sensor': 'Modis'}
	terra = references.cite('burn_severity', args)
	assert {'miller2007', 'howe2022', 'veraverbeke2010', 'mod09ga061', 'gorelick2017'} <= set(_ids(terra))
	aqua = references.cite('burn_severity', dict(args, collection=AQUA))
	assert {'miller2007', 'howe2022', 'veraverbeke2010', 'myd09ga061'} <= set(_ids(aqua))
	assert 'mod09ga061' not in _ids(aqua) and 'myd09ga061' not in _ids(terra)
	cited = {r['id']: r for r in terra['references']}
	assert cited['miller2007']['url'] == 'https://doi.org/10.1016/j.rse.2006.12.006'
	# the dNBR and the RBR cite as before
	dnbr = _ids(references.cite('burn_severity', dict(args, index=None, sensor=None)))
	assert {'garcia1991', 'key2006'} <= set(dnbr) and 'miller2007' not in dnbr
	rbr = _ids(references.cite('burn_severity', dict(args, index='RBR', sensor='Landsat')))
	assert {'parks2014', 'silvacardoza2022'} <= set(rbr) and 'miller2007' not in rbr


# With Earth Engine --------------------------------------------------------------------------------------------------

@pytest.mark.ee
@pytest.mark.skipif(not os.environ.get('EE_PROJECT'), reason='EE_PROJECT not set')
@pytest.mark.parametrize('sensor, collection, resolution', [
	('Sentinel-2', None, 30),  # 30 m instead of 10 m: fewer pixels to download
	('Landsat', None, None),
	('Modis', None, None),
	('Modis', AQUA, None),
])
def test_the_rdnbr_of_a_fire(tmp_path, sensor, collection, resolution):
	"""The RdNBR of the fire of Sierra Bermeja (September 2021), one year after it: the hectares of its classes are
	those of its statistics, the burned hectares those of the classes low to high, and its GeoTIFF has the bands rdnbr,
	severity, dnbr, nbr_before and nbr_after, consistent with each other."""
	import numpy as np
	from osgeo import gdal
	gdal.UseExceptions()
	services.init()
	out = services.burn_severity(REGION, sensor, *BEFORE, *AFTER, index='RdNBR', collection=collection,
	                             resolution=resolution, csv=str(tmp_path / 'rdnbr.csv'),
	                             path=str(tmp_path / 'rdnbr.tif'))
	assert out['index'] == 'RdNBR' and out['bands'] == BANDS and os.path.exists(out['readme'])
	product = {None: ' MOD09GA', AQUA: ' MYD09GA'}[collection] if sensor == 'Modis' else ''  # Terra or Aqua
	assert out['title'].startswith(f'Burn severity (RdNBR, Miller & Thode 2007) {sensor}{product} (median)')
	assert {'miller2007', 'howe2022'} <= set(_ids(out))
	(stats,) = out['stats']
	region = stats['region']
	classes = [c for c in out['classes'] if c['region'] == region]
	assert [c['class'] for c in classes] == [0, 1, 2, 3]
	assert [c['label'] for c in classes] == [label for _, _, label in fire.RDNBR_SEVERITY]
	total = sum(c['ha'] for c in classes)
	assert total == pytest.approx(stats['ha'], rel=1e-2) and total > 0
	assert out['burned_ha'][region] == pytest.approx(sum(c['ha'] for c in classes if c['class'] >= 1))
	assert out['burned_ha'][region] > 1000  # thousands of hectares burned in the box
	assert stats['min'] <= stats['p10'] <= stats['median'] <= stats['p90'] <= stats['max']
	with open(out['csv'], encoding='utf-8') as f:
		header = next(csv.reader(f))
	assert header[:len(services.RDNBR_COLUMNS)] == services.RDNBR_COLUMNS
	ds = gdal.Open(out['file'])
	assert [ds.GetRasterBand(i + 1).GetDescription() for i in range(ds.RasterCount)] == BANDS
	rdnbr_, severity, dnbr, before, after = (ds.GetRasterBand(i + 1).ReadAsArray().astype(float) for i in range(5))
	nodata = ds.GetRasterBand(1).GetNoDataValue()
	ds = None
	ok = (rdnbr_ != nodata) & (severity != nodata) & (dnbr != nodata) & (before != nodata)
	assert ok.any() and set(np.unique(severity[ok])) <= {0, 1, 2, 3}
	assert np.allclose(dnbr[ok], before[ok] - after[ok], atol=1e-5)
	assert np.allclose(rdnbr_[ok], dnbr[ok] / np.sqrt(np.maximum(np.abs(before[ok]), 0.001)), rtol=1e-4, atol=1e-4)
	expected = np.digitize(rdnbr_[ok], [0.069, 0.316, 0.641])
	assert (expected != severity[ok]).mean() < 1e-3  # but at the limits (float32)
	assert fire.map_style(out['bands']) == {'band': 2, 'classes': fire.legend('RdNBR')}


def test_the_app_has_the_classes_and_sensors_of_the_package():
	"""gee/core.js, the port of the app, has the classes, colours, limits and sensors of the RdNBR of the package."""
	from test_rgb_gee import _js_value, _read
	core = _read('core.js')
	assert _js_value(core, 'RDNBR_COLOURS') == [fire.RDNBR_COLOURS[c] for c, _, _ in fire.RDNBR_SEVERITY]
	assert [[c, low, en] for c, low, _, en in _js_value(core, 'RDNBR_SEVERITY')] == [list(x) for x in fire.RDNBR_SEVERITY]
	assert tuple(_js_value(core, 'RDNBR_RANGE')) == fire.RDNBR_RANGE
	assert _js_value(core, 'RDNBR_BURNED') == fire.RDNBR_BURNED
	assert _js_value(core, 'RDNBR_MIN_NBR') == catalog.RDNBR_MIN_NBR
	assert _js_value(core, 'RDNBR_COLUMNS') == services.RDNBR_COLUMNS
	assert tuple(_js_value(core, 'BURN_INDICES')) == services.BURN_INDICES
	assert {k: tuple(v) for k, v in _js_value(core, 'BURN_SENSORS').items()} == services.BURN_SENSORS
