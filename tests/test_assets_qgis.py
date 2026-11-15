"""The help of the data of Earth Engine given by their ID in the QGIS plugin (helptexts.data_help, the button ⓘ of
Earth Engine ID), without QGIS and without Earth Engine: what services.describe_asset says of them, in the words of
the panel. Its metadata in Earth Engine and its STAC record are faked; qgis/test_plugin.py runs the plugin with QGIS
and Earth Engine."""

import os
import re
import sys

import pytest

from monitoreo import assets, references, services

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORLDCOVER = 'ESA/WorldCover/v200'
# a band with classes (land cover), as in the STAC record of the Earth Engine data catalog
RECORD = {'title': 'ESA WorldCover 10m v200', 'license': 'CC-BY-4.0',
          'summaries': {'eo:bands': [{'name': 'Map', 'description': 'Landcover class',
                                      'gee:classes': [{'value': 10, 'description': 'Tree cover'},
                                                      {'value': 20, 'description': 'Shrubland'},
                                                      {'value': 80, 'description': 'Permanent water bodies'}]}]}}
META = {'asset': WORLDCOVER, 'type': 'image_collection', 'first_date': '2021-01-01',
        'bands': [{'band': 'Map', 'data_type': 'int', 'resolution_m': 10.0}]}


@pytest.fixture
def helptexts(monkeypatch):
	"""The help of the QGIS plugin, which does not need QGIS."""
	monkeypatch.syspath_prepend(os.path.join(ROOT, 'qgis'))
	for name in [m for m in sys.modules if m.startswith('monitoreo_qgis')]:
		monkeypatch.delitem(sys.modules, name)
	import monitoreo_qgis.helptexts as module
	return module


@pytest.fixture
def worldcover(monkeypatch):
	"""What services.describe_asset says of ESA WorldCover (a band with classes), with its metadata and its record
	faked (and its citations left aside: they are tested with monitoreo.references)."""
	monkeypatch.setattr(assets, 'info', lambda asset: META)
	monkeypatch.setattr(assets, 'stac', lambda asset: RECORD)
	monkeypatch.setattr(references, 'of_data', lambda asset: {'references': [], 'credits': []})
	return services.describe_asset(WORLDCOVER)


def test_the_bands_with_classes_in_the_words_of_the_panel(helptexts, worldcover):
	"""describe_asset advises the metric mode for the bands with classes, which the panel does not offer (its metrics:
	dock.METRICS): its ⓘ gives the advice of the help of Band instead (Minimum or Maximum), one text for both."""
	assert worldcover['bands'][0]['classes'] and any('classes' in n.lower() for n in worldcover['notes'])
	entry = {'custom': True, 'asset': WORLDCOVER, 'band': 'Map', 'use': 'image', 'static': True}
	text = helptexts.data_help(entry, worldcover)
	assert helptexts.CLASSES in text and text.count('codes, not quantities') == 1, text
	assert not re.search(r'\bmode\b', text), text
	assert 'Tree cover' in text  # the classes of its band
	assert all(helptexts.esc(n) in text for n in worldcover['notes'] if 'classes' not in n.lower())  # the others
	assert f'<p>{helptexts.CLASSES}</p>' in helptexts.HELP['asset_band']
	assert '<b>Minimum</b>' in helptexts.CLASSES and '<b>Maximum</b>' in helptexts.CLASSES
	metrics = open(os.path.join(ROOT, 'qgis', 'monitoreo_qgis', 'dock.py'), encoding='utf-8').read()
	assert "('Minimum', 'min'), ('Maximum', 'max')" in metrics and "'mode')" not in metrics  # the metrics of the panel
	# without classes, no such note
	plain = dict(worldcover, bands=[{'band': 'Map'}], notes=[n for n in worldcover['notes'] if 'classes' not in n])
	assert helptexts.CLASSES not in helptexts.data_help(entry, plain)


def test_the_help_of_combined_bands(helptexts, monkeypatch):
	"""Several bands combined on each pixel (Combine bands: Sum or Mean of the bands): the help names the reducer and
	the bands, says that the scale and the offset apply to each band, and gives what the record says of each of them;
	the help of the options explains them."""
	meta = {'asset': 'IDAHO_EPSCOR/TERRACLIMATE', 'type': 'image_collection', 'first_date': '1958-01-01',
	        'bands': [{'band': b, 'data_type': 'int', 'resolution_m': 4638.3} for b in ('aet', 'def', 'pr')]}
	record = {'title': 'TerraClimate', 'summaries': {'eo:bands': [
		{'name': 'aet', 'description': 'Actual evapotranspiration', 'gee:units': 'mm', 'gee:scale': 0.1},
		{'name': 'def', 'description': 'Climate water deficit', 'gee:units': 'mm', 'gee:scale': 0.1},
		{'name': 'pr', 'description': 'Precipitation accumulation', 'gee:units': 'mm'}]}}
	monkeypatch.setattr(assets, 'info', lambda asset: meta)
	monkeypatch.setattr(assets, 'stac', lambda asset: record)
	monkeypatch.setattr(references, 'of_data', lambda asset: {'references': [], 'credits': []})
	info = services.describe_asset('IDAHO_EPSCOR/TERRACLIMATE')
	entry = {'custom': True, 'asset': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'aet', 'bands': ['aet', 'def'],
	         'band_reducer': 'sum', 'use': 'collection', 'band_scale': '0.1', 'unit': 'mm'}
	text = helptexts.data_help(entry, info)
	assert '<b>the sum of the bands aet and def</b> on each pixel' in text, text
	assert 'stored × 0.1 + 0 (each band, before they are combined)' in text
	assert 'Actual evapotranspiration' in text and 'Climate water deficit' in text
	assert 'Precipitation accumulation' not in text  # a band not combined
	assert 'fewer than two bands checked' in helptexts.data_help(dict(entry, bands=['aet']), info)
	one = helptexts.data_help(dict(entry, bands=['pr'], band='pr', band_reducer=None), info)
	assert ', band <b>pr</b>' in one and 'Precipitation accumulation' in one and 'Actual' not in one
	assert '<b>Sum of the bands</b>' in helptexts.HELP['band_reducer'] and 'mm, not mm month-1' in \
		helptexts.HELP['band_reducer']
	assert 'Combine bands' in helptexts.HELP['asset_bands'] and 'Combine bands' in helptexts.HELP['asset_band']
	dock = open(os.path.join(ROOT, 'qgis', 'monitoreo_qgis', 'dock.py'), encoding='utf-8').read()
	assert "('One band', ''), ('Sum of the bands', 'sum'), ('Mean of the bands', 'mean')" in dock
	assert "SOURCE = ('image', 'band', 'band_reducer'," in dock
