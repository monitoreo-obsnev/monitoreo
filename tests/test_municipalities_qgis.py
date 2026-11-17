"""The municipalities of Spain (level 3 of the administrative units, monitoreo.municipalities) in the QGIS plugin,
without QGIS and without Earth Engine: the levels of the list of the region Administrative unit, the country greyed out
at ESP for level 3, the search of the municipalities at once from the index of the package (no task, no Earth Engine),
the entries of the list Unit and the region they give ({"admin3": "18134"}, checked offline), the credit of the IGN in
the layers and the help. The module dock is imported with QGIS and Qt replaced by empty classes; qgis/test_plugin.py
runs the plugin with QGIS and Earth Engine, qgis/test_analyses_offline.py its widgets in QGIS without it."""

import os
import sys
import types

import pytest

from monitoreo import areas, municipalities, references, services

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QT = ('qgis', 'qgis.core', 'qgis.gui', 'qgis.PyQt', 'qgis.PyQt.QtCore', 'qgis.PyQt.QtGui', 'qgis.PyQt.QtWidgets')
GAUL2 = {'GAUL0_NAME': 'Spain', 'GAUL1_NAME': 'Andalucía', 'GAUL2_CODE': 141938, 'GAUL2_NAME': 'Granada',
         'ISO3_CODE': 'ESP', 'DISP_EN': 'Granada, Andalucía, Spain', 'level': 2}  # as FAO GAUL 2025 has it


class _Qt(types.ModuleType):
	"""A module of QGIS or Qt whose names are empty classes: enough to import the plugin without QGIS."""

	def __getattr__(self, name):
		if name.startswith('__'):
			raise AttributeError(name)
		cls = type(name, (), {})
		setattr(self, name, cls)
		return cls


def _forget_plugin():
	return {m: sys.modules.pop(m) for m in [m for m in sys.modules if m.startswith('monitoreo_qgis')]}


@pytest.fixture
def plugin(monkeypatch):
	"""The modules dock and helptexts of the plugin, imported with QGIS and Qt replaced by empty classes (their
	functions, not their widgets)."""
	for name in QT:
		monkeypatch.setitem(sys.modules, name, _Qt(name))
	monkeypatch.syspath_prepend(os.path.join(ROOT, 'qgis'))
	before = _forget_plugin()
	import monitoreo_qgis.dock as dock
	import monitoreo_qgis.helptexts as helptexts
	monkeypatch.setattr(dock, 'QgsCoordinateReferenceSystem', lambda *args: None)  # region() makes one first
	yield types.SimpleNamespace(dock=dock, helptexts=helptexts)
	_forget_plugin()
	sys.modules.update(before)


class _Combo:
	"""A QComboBox of (text, data)."""

	def __init__(self, items=()):
		self.items, self.index = list(items), 0 if items else -1

	def addItem(self, text, data=None):
		self.items.append((text, data))
		if self.index < 0:
			self.index = 0

	def clear(self):
		self.items, self.index = [], -1

	def count(self):
		return len(self.items)

	def itemText(self, i):
		return self.items[i][0]

	def setCurrentIndex(self, i):
		self.index = i

	def currentData(self):
		return self.items[self.index][1] if self.index >= 0 else None


class _Line:
	"""A QLineEdit."""

	def __init__(self, text=''):
		self.value, self.enabled, self.tip, self.hint = text, True, '', ''

	def text(self):
		return self.value

	def setText(self, text):
		self.value = text

	def isEnabled(self):
		return self.enabled

	def setEnabled(self, on):
		self.enabled = on

	def setToolTip(self, text):
		self.tip = text

	def setPlaceholderText(self, text):
		self.hint = text


def _panel(dock, text='', level=1, country=''):
	"""The widgets of the region Administrative unit of the panel, with the messages it shows and the tasks it runs."""
	panel = types.SimpleNamespace(admin_text=_Line(text), admin_level=_Combo(dock.ADMIN_LEVELS),
	                              admin_country=_Line(country), admin_country_typed='', admin=_Combo(),
	                              region_kind=types.SimpleNamespace(currentData=lambda: 'admin'), messages=[], tasks=[])
	panel.admin_level.setCurrentIndex([v for _, v in dock.ADMIN_LEVELS].index(level))
	panel.message = lambda text, lvl='Info', duration=6: panel.messages.append((lvl, text))
	panel.run_task = lambda description, work, done: panel.tasks.append((description, work, done))
	return panel


@pytest.fixture
def no_earth_engine(monkeypatch):
	"""Earth Engine refused: the municipalities are found without it."""
	def refused(*args, **kw):
		raise AssertionError('Earth Engine used')
	monkeypatch.setattr(services, 'init', refused)
	monkeypatch.setattr(areas.ee, 'FeatureCollection', refused)
	monkeypatch.setattr(areas.ee.data, 'computeValue', refused)


def test_the_levels_of_the_administrative_units(plugin):
	"""Levels 1 and 2 of FAO GAUL 2025, as before, and level 3, the municipalities of Spain, in the list of the panel
	and in its tooltip."""
	dock = plugin.dock
	assert dock.ADMIN_LEVELS == [('Level 1', 1), ('Level 2', 2), ('Level 3 · Municipalities (Spain)', 3)]
	assert municipalities.LEVEL == 3 and municipalities.COUNTRY == 'ESP'
	assert 'level 3: the municipalities of Spain' in dock.ADMIN_LEVEL_TIP
	assert 'Instituto Geográfico Nacional' in dock.ADMIN_LEVEL_TIP and 'FAO GAUL 2025' in dock.ADMIN_LEVEL_TIP
	assert set(dock.ADMIN_HINTS) == {1, 2, 3} and 'INE code' in dock.ADMIN_HINTS[3]
	source = open(os.path.join(ROOT, 'qgis', 'monitoreo_qgis', 'dock.py'), encoding='utf-8').read()
	assert 'self.admin_level = combo(ADMIN_LEVELS)' in source
	assert 'self.admin_level.currentIndexChanged.connect(lambda i: self.admin_level_changed())' in source


def test_level_3_sets_the_country_to_spain_and_gives_back_the_one_written(plugin):
	dock = plugin.dock
	panel = _panel(dock, level=2, country='prt')
	dock.MonitorEODock.admin_level_changed(panel)  # level 2: as written
	assert panel.admin_country.enabled and panel.admin_country.value == 'prt'
	assert panel.admin_country.tip == dock.ADMIN_COUNTRY_TIP and panel.admin_text.hint == dock.ADMIN_HINTS[2]
	panel.admin_level.setCurrentIndex(2)  # level 3: Spain, greyed out
	dock.MonitorEODock.admin_level_changed(panel)
	assert not panel.admin_country.enabled and panel.admin_country.value == 'ESP'
	assert panel.admin_country.tip == dock.ADMIN_SPAIN_TIP and 'ESP' in panel.admin_country.tip
	assert panel.admin_text.hint == dock.ADMIN_HINTS[3]
	dock.MonitorEODock.admin_level_changed(panel)  # level 3 again (e.g. the signal twice): still Spain
	assert panel.admin_country.value == 'ESP' and panel.admin_country_typed == 'prt'
	panel.admin_level.setCurrentIndex(0)  # level 1: the country written before, editable
	dock.MonitorEODock.admin_level_changed(panel)
	assert panel.admin_country.enabled and panel.admin_country.value == 'prt'
	assert panel.admin_country.tip == dock.ADMIN_COUNTRY_TIP and panel.admin_text.hint == dock.ADMIN_HINTS[1]


@pytest.mark.parametrize('text, first', [('Monachil', '18134'), ('monachil', '18134'), ('18134', '18134'),
                                         ('GRANADA', '18087'), ('granada', '18087'), ("L'Hospitalet", '08101'),
                                         ('L\u2019Hospitalet', '08101'), ('l\u2018hospitalet', '08101'),
                                         ('Sant Joan d\u00b4Alacant', '03119')])
def test_the_municipalities_are_found_at_once_without_earth_engine(plugin, no_earth_engine, text, first):
	"""Level 3: services.find_admin_units in the index of the package, without a task (no Earth Engine), in any case
	and accents or by the code of the INE, the very name first; the country (Spain, greyed out) is not sent. The
	apostrophe typed as macOS writes it (’), or with the acute accent of the Spanish keyboards (´), is that of the
	names: they were not found."""
	dock = plugin.dock
	panel = _panel(dock, text, level=3, country='ESP')
	dock.MonitorEODock.search_admin(panel)
	assert panel.tasks == [] and panel.messages[-1][0] == 'Info', panel.messages
	assert 'municipalities of Spain' in panel.messages[-1][1] and f'"{text}"' in panel.messages[-1][1]
	assert panel.admin.count() >= 1 and panel.admin.currentData() == (3, first)
	unit = municipalities.find(first)[0]
	assert panel.admin.itemText(0) == f"{unit['DISP_EN']} · INE {first}"  # e.g. «Monachil (Granada) · INE 18134»
	region = dock.MonitorEODock.region(panel)
	assert region == {'admin3': first} and isinstance(region['admin3'], str)
	assert areas.check(region) == 'admin3'  # valid, offline


def test_the_entries_of_the_list_unit(plugin):
	"""The text and the data of each entry: the GAUL code, an integer, at levels 1 and 2; the code of the INE, a
	string of 5 digits, at level 3 (that of a province below 10 keeps its 0)."""
	dock = plugin.dock
	assert dock.admin_item(GAUL2, 2) == ('Granada, Andalucía, Spain (GAUL 141938)', (2, 141938))
	assert dock.admin_item(dict(GAUL2, GAUL2_CODE=141938.0), '2')[1] == (2, 141938)
	monachil = services.find_admin_units('Monachil', 3)[0]
	assert dock.admin_item(monachil, 3) == ('Monachil (Granada) · INE 18134', (3, '18134'))
	row = {'ADMIN3_CODE': 4013, 'NAME': 'Almería', 'PROVINCE': 'Almería', 'level': 3}  # no DISP_EN, a number
	assert dock.admin_item(row, 3) == ('Almería · INE 04013', (3, '04013'))
	for data, region in (((2, 141938), {'admin2': 141938}), ((3, '18134'), {'admin3': '18134'})):
		panel = _panel(dock)
		panel.admin.addItem('unit', data)
		assert dock.MonitorEODock.region(panel) == region
	with pytest.raises(ValueError, match='search for an administrative unit'):
		dock.MonitorEODock.region(_panel(dock))


def test_levels_1_and_2_are_searched_in_earth_engine_as_before(plugin, monkeypatch):
	"""Levels 1 and 2: in a task (Earth Engine), with the country written; their entries as before."""
	dock = plugin.dock
	calls = []
	monkeypatch.setattr(services, 'find_admin_units', lambda *args: calls.append(args) or [GAUL2])
	panel = _panel(dock, 'Granada', level=2, country='esp')
	dock.MonitorEODock.search_admin(panel)
	assert calls == [] and [t[0] for t in panel.tasks] == ['Search administrative units']
	_, work, done = panel.tasks[0]
	done(work())
	assert calls == [('Granada', 2, 'ESP', 30)]
	assert panel.admin.items == [('Granada, Andalucía, Spain (GAUL 141938)', (2, 141938))]
	assert panel.messages[-1] == ('Info', '1 administrative units with "Granada"')
	assert dock.MonitorEODock.region(panel) == {'admin2': 141938}


def test_the_errors_and_an_empty_search_of_the_municipalities(plugin, monkeypatch):
	dock = plugin.dock
	panel = _panel(dock, '', level=3)
	dock.MonitorEODock.search_admin(panel)  # nothing written: nothing searched
	assert panel.messages == [] and panel.tasks == [] and panel.admin.count() == 0
	panel = _panel(dock, 'zzzz no such municipality', level=3)
	dock.MonitorEODock.search_admin(panel)
	assert panel.admin.count() == 0 and panel.messages == [('Info', '0 municipalities of Spain with '
	                                                                '"zzzz no such municipality"')]

	def broken(*args):
		raise ValueError('the index is broken')
	monkeypatch.setattr(services, 'find_admin_units', broken)
	panel = _panel(dock, 'Monachil', level=3)
	dock.MonitorEODock.search_admin(panel)
	assert panel.tasks == [] and panel.messages == [('Critical', 'Search municipalities: the index is broken')]


def test_the_layers_of_a_municipality_credit_the_ign(plugin):
	"""The abstract of a layer over a municipality has the reference and the credit of the IGN (monitoreo.references),
	which the print layout of the plugin takes (layer_credits)."""
	dock = plugin.dock
	args = {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'collection': 'COPERNICUS/S2_SR_HARMONIZED',
	        'start': '2021-01-01', 'end': '2021-12-31'}
	res = references.cite('map_layer', dict(args, region={'admin3': '18134'}))
	text = dock.references_text(res)
	assert 'Instituto Geográfico Nacional' in text and municipalities.CREDIT in dock.layer_credits(text)
	assert 'FAO GAUL' not in text  # not a unit of FAO GAUL


def test_the_help_explains_the_levels(plugin):
	help_ = plugin.helptexts.HELP
	text = help_['admin']
	for words in ('<b>Level 1</b>', '<b>Level 2</b>', '<b>Level 3 · Municipalities (Spain)</b>', 'FAO GAUL 2025',
	              'Instituto Geográfico Nacional', 'CC BY 4.0 ign.es', 'without Earth Engine', 'code of the INE',
	              'The country is Spain', 'More in the manual'):
		assert words in text, words
	assert f'{plugin.helptexts.about.MANUAL}/QGIS-plugin#2-choose-the-region' in text
	assert dict(plugin.dock.ADMIN_LEVELS)['Level 3 · Municipalities (Spain)'] == 3  # the same name as in the list
	assert 'a municipality of Spain (level 3, of the Instituto Geográfico Nacional)' in help_['region']
