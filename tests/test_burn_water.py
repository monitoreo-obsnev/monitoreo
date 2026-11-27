"""The water of the burn severity (services.burn_severity): the permanent water of the JRC Global Surface Water instead of
the water flagged in each image, which takes burned pixels for water (after the fire of Lanjarón, Sierra Nevada,
QA_PIXEL of Landsat 5 flagged as water 442 ha of its 3,384 ha on 2005-11-09). The option {'water': 'permanent'} of the
pixel filters, its default in the burn severity, its citation and its description, without Earth Engine (the test
marked ee computes the mask in Earth Engine)."""

import os
import re

import pytest

from monitoreo import catalog, fire, references, report, sensors

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ids(c):
	return [r['id'] for r in c['references']]


def test_burn_quality_uses_the_permanent_water():
	assert fire.burn_quality(None) == {'water': 'permanent'}  # the default of the water filter is on
	assert fire.burn_quality({'water': True})['water'] == 'permanent'
	assert fire.burn_quality({'water': 'auto'})['water'] == 'permanent'
	assert fire.burn_quality({'water': 'permanent'})['water'] == 'permanent'
	assert fire.burn_quality({'water': False})['water'] is False  # off stays off
	q = {'clouds': False, 'scene_clouds': 30}
	assert fire.burn_quality(q) == {'clouds': False, 'scene_clouds': 30, 'water': 'permanent'}
	assert q == {'clouds': False, 'scene_clouds': 30}  # the quality given is not changed


@pytest.mark.parametrize('sensor', ['Landsat', 'Sentinel-2'])
def test_permanent_is_the_water_filter_on(sensor):
	e = catalog.find('NBR', sensor)
	q = {'water': 'permanent'}
	assert sensors.water_permanent(q) and not sensors.water_permanent({'water': True})
	assert not sensors.water_permanent(None)
	assert sensors.filters(e, q)['water'] is True
	assert sensors.filters(e, {'water': False})['water'] is False


def test_the_permanent_water_is_cited():
	args = {'region': {'bbox': [-3.53, 36.93, -3.43, 37.02]}, 'sensor': 'Landsat', 'start': '2005-06-01',
	        'end': '2005-09-15', 'other_start': '2005-10-01', 'other_end': '2005-12-31'}
	c = references.cite('burn_severity', args)
	assert {'pekel2016', 'foga2017'} <= set(_ids(c))
	assert 'Source: EC JRC/Google' in c['credits']
	off = references.cite('burn_severity', dict(args, quality={'water': False}))
	assert 'pekel2016' not in _ids(off)
	# the other tools only with {'water': 'permanent'}
	ts = {'region': args['region'], 'variable': 'NDVI', 'sensor': 'Landsat', 'start': '2004-01-01', 'end': '2008-12-31'}
	assert 'pekel2016' not in _ids(references.cite('time_series', ts))
	assert 'pekel2016' in _ids(references.cite('time_series', dict(ts, quality={'water': 'permanent'})))
	ref = catalog.load()['references']['pekel2016']
	assert ref['doi'] == '10.1038/nature20584' and 'Nature, 540' in ref['citation']


def test_the_readme_says_which_water():
	e = report._entry('NBR', 'Landsat')
	text = report._discarded(e, fire.burn_quality(None))
	assert 'permanent water (JRC Global Surface Water' in text and 'clouds' in text
	assert 'permanent' not in report._discarded(e, None)


def test_the_app_has_it_too():
	"""The Earth Engine app (gee/core.js) and its burn severity (gee/ui.js) use the permanent water as the package."""
	core = open(os.path.join(ROOT, 'gee', 'core.js'), encoding='utf-8').read()
	ui = open(os.path.join(ROOT, 'gee', 'ui.js'), encoding='utf-8').read()
	w = sensors.PERMANENT_WATER
	assert f"var PERMANENT_WATER = {{image: '{w['image']}', band: '{w['band']}', min: {w['min']}}};" in core
	assert 'burnQuality: burnQuality' in core and 'if (permanent) masks.push(permanentLand());' in core
	assert len(re.findall(r"quality: mo\.burnQuality\(qualityFor\(", ui)) == 6
	assert not re.search(r"fire(Before|After)\.slice\(\), metric: 'median', quality: qualityFor", ui)


@pytest.mark.ee
@pytest.mark.skipif(not os.environ.get('EE_PROJECT'), reason='EE_PROJECT not set')
def test_the_burned_pixels_are_kept():
	"""In Earth Engine: over the burned area of Lanjarón (2005-11-09, Landsat 5), the permanent water keeps the pixels
	that QA_PIXEL flags as water."""
	import ee
	from monitoreo import services
	services.init()
	img = ee.Image('LANDSAT/LT05/C02/T1_L2/LT05_200034_20051109')
	region = ee.Geometry.Rectangle([-3.50, 36.95, -3.45, 37.00])
	e = catalog.find('NBR', 'Landsat')
	area = ee.Image.pixelArea().divide(1e4)

	def kept(quality):
		m = sensors.quality_mask(img, e, quality)
		return area.updateMask(m).reduceRegion(ee.Reducer.sum(), region, 30).getInfo()['area']

	flags, permanent = kept({'water': True, 'aerosols': False}), kept({'water': 'permanent', 'aerosols': False})
	assert permanent > flags + 10  # hectares of burned land that the flags removed


@pytest.mark.parametrize('sensor', ['Landsat', 'Sentinel-2', 'Modis'])
def test_the_fixed_filters_keep_their_water(sensor):
	"""The snow cover frequency keeps its own fixed water filter whatever the quality: neither computed, cited nor
	described with the permanent water."""
	e = catalog.find('SCF', sensor)
	q = {'water': 'permanent'}
	assert not sensors.permanent_water_of(e, q)
	assert 'permanent' not in report._discarded(e, q)
	c = references.cite('time_series', {'region': {'bbox': [-3.5, 37, -3.4, 37.1]}, 'variable': 'SCF', 'sensor': sensor,
	                                    'start': '2020-01-01', 'end': '2021-12-31', 'quality': q})
	assert 'pekel2016' not in _ids(c)
	assert sensors.permanent_water_of(catalog.find('NDVI', sensor), q)
