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
