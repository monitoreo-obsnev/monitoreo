"""Tests of the assistant and of its report that need neither Earth Engine nor a language model."""

import asyncio
import json
import os
import threading

import pytest

from monitoreo import assistant, report
from monitoreo.steps import MAX_MAP_STEPS, UNITS, map_steps

TOOLS = [
	{'name': 'time_series', 'description': 'Time series.', 'inputSchema': {'type': 'object', 'properties': {
		'region': {'type': 'object', 'additionalProperties': True}, 'variable': {'type': 'string'},
		'sensor': {'type': 'string'}, 'start': {'type': 'string'}, 'end': {'type': 'string'},
		'season': {'anyOf': [{'type': 'array', 'items': {'type': 'string'}}, {'type': 'null'}]},
		'collection': {'type': 'string'}, 'scale': {'type': 'number'}}, 'required': ['region', 'variable', 'scale']}},
	{'name': 'connect', 'description': 'Connect.', 'inputSchema': {'type': 'object', 'properties': {
		'project': {'type': 'string'}}}},
	{'name': 'find_protected_areas', 'description': 'Protected areas.', 'inputSchema': {'type': 'object', 'properties': {
		'text': {'type': 'string'}, 'limit': {'type': 'integer'}}, 'required': ['text']}},
]
ROWS = [{'region': 'region', 'date': f'2021-{m:02d}-01', 'value': 0.5 + m / 1000, 'n_pixels': 100, 'n_images': 4}
        for m in range(1, 13)]
SERIES = {'title': 'NDVI', 'unit': '[unitless]', 'scale': 10, 'n_steps': 12, 'regions': ['region'], 'rows': ROWS,
          'csv': '/tmp/ndvi.csv', 'chart': None}
ARGS = {'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2021-01-01',
        'end': '2021-12-31'}


def test_model_tools():
	tools = assistant.model_tools(TOOLS)
	assert [t['function']['name'] for t in tools] == ['time_series', 'find_protected_areas']  # not connect
	series = tools[0]['function']
	assert 'scale' not in series['parameters']['properties']  # hidden
	assert series['parameters']['required'] == ['region', 'variable']
	assert 'collection' in series['parameters']['properties']  # an ID of Earth Engine (see describe_asset)
	assert series['description'].endswith(assistant.RECEIPT_NOTE)
	assert 'limit' not in tools[1]['function']['parameters']['properties']


def test_fix_args():
	tools = assistant.model_tools(TOOLS)
	args = assistant.fix_args('time_series', {'region': '{"wdpa_id": 389011}', 'variable': 'NDVI', 'scale': 30,
	                                          'season': '["06-01", "08-31"]', 'unknown': 1, 'sensor': None}, tools)
	assert args == {'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'season': ['06-01', '08-31']}
	assert assistant.fix_args('time_series', '{"variable": "EVI"}', tools) == {'variable': 'EVI'}
	assert assistant.fix_args('time_series', {'collection': 'IDAHO_EPSCOR/TERRACLIMATE'}, tools) == {
		'collection': 'IDAHO_EPSCOR/TERRACLIMATE'}  # no longer hidden: the data of Earth Engine by their ID


def test_instructions():
	text = assistant.instructions()
	assert 'Do not interpret results' in text and 'never make it up' in text
	assert "Answer in the language of the user's last message (a question in Spanish gets the answer in Spanish" in text
	assert 'español' not in text and '«since 2018»' in text
	assert '- NDVI: ' in text and 'Sentinel-2 10 m since 2017' in text and 'Landsat 30 m since 1984' in text
	for page in ('Earth-Engine-app', 'QGIS-plugin', 'Python-package', 'Command-line', 'R-package', 'MCP-server',
	             'Results-viewer'):  # the English pages of the wiki
		assert assistant.WIKI + page + '\n' in text or assistant.WIKI + page + ' ' in text, page


AREAS = {'Sierra': [{'SITE_ID': 389011, 'NAME': 'Sierra Nevada', 'DESIG': 'Parque Nacional'}],
         'Doñana': [{'SITE_ID': 389012, 'NAME': 'Doñana', 'DESIG': 'Parque Nacional', 'DESIG_ENG': 'National Park'},
                    {'SITE_ID': 349268, 'NAME': 'Doñana', 'DESIG': 'Parque Natural', 'DESIG_ENG': 'Natural Park'}]}


@pytest.fixture(autouse=True)
def log(tmp_path, monkeypatch):
	"""The log of the assistant of the tests, not that of the user."""
	monkeypatch.setattr(assistant, 'LOG', str(tmp_path / 'assistant.log'))


MAP = {'url': 'https://ee/map/{z}/{x}/{y}', 'bounds': [-3.6, 36.9, -3.5, 37.0], 'min': 0, 'max': 1,
       'palette': ['ffffff', '00aa00'], 'unit': '[unitless]'}


class FakeAssistant(assistant.Assistant):
	"""An assistant whose MCP server answers a time series, a map (map_layer) and the protected areas of WDPA."""

	async def call(self, name, args):
		if name == 'find_protected_areas':
			return None, [json.dumps(next((v for k, v in AREAS.items() if k in args.get('text', '')), []))], []
		if name in ('map_layer', 'trend_map'):
			self.mapped = (name, args)
			return None, [json.dumps(MAP)], []
		self.called = (name, args)
		return None, [json.dumps(SERIES)], ['data:image/png;base64,iVBORw0KGgo=']


def test_the_model_does_not_get_the_results(monkeypatch):
	answers = iter([
		{'content': '', 'tool_calls': [{'function': {'name': 'find_protected_areas', 'arguments': {'text': 'Sierra'}}}]},
		{'content': '', 'tool_calls': [{'function': {'name': 'time_series', 'arguments': ARGS}}]},
		{'content': 'Done: the series is on the screen.'},
	])
	seen = []

	def model(settings, system, messages, tools):
		seen.append(json.dumps(messages, ensure_ascii=False))
		return next(answers)

	monkeypatch.setattr(assistant, 'chat_model', model)
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)

	async def run():
		a = FakeAssistant({**assistant.DEFAULTS, 'project': 'p', 'ollama': 'http://127.0.0.1:1'})
		a.tools = assistant.model_tools(TOOLS)
		return a, [e async for e in a.chat('NDVI de Sierra Nevada en 2021')]

	a, events = asyncio.run(run())
	assert [e['type'] for e in events if e['type'] != 'status'] == ['areas', 'running', 'result', 'map', 'assistant']
	assert next(e for e in events if e['type'] == 'areas')['areas'] == [
		{'SITE_ID': 389011, 'NAME': 'Sierra Nevada', 'DESIG': 'Parque Nacional', 'match': False}]
	result = next(e for e in events if e['type'] == 'result')
	assert result['table']['rows'][0][1] == report._num(0.501) and result['image'].startswith('data:image/png')
	assert 'Sierra Nevada (Parque Nacional) (WDPA 389011)' in result['facts'][0][1]  # the region
	assert 'Sierra Nevada' in seen[1]  # the answer of an advice tool goes to the model
	assert '0.501' not in seen[2] and '0,501' not in seen[2] and 'Done:' in seen[2]  # that of a result does not
	assert len(a.results) == 1 and a.question == 'NDVI de Sierra Nevada en 2021'
	# the map of the variable over the period of the series, without its preview (only the tiles), for the page
	shown = next(e for e in events if e['type'] == 'map')
	assert shown['id'] == 1 and shown['map'] == {'url': MAP['url'], 'bounds': MAP['bounds'], 'pixel': True, 'trend': False}
	assert shown['legend']['palette'] == MAP['palette'] and shown['title'] == result['title']  # the list of maps
	assert result['title'].endswith(' · Sierra Nevada (Parque Nacional)')  # the region, in the titles
	assert a.mapped == ('map_layer', {'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
	                                  'start': ARGS['start'], 'end': ARGS['end'], 'metric': 'median', 'quick': True})
	assert a.map_of(1)[1]['args'] == {k: v for k, v in a.mapped[1].items() if k != 'quick'}


def test_trend_map_of_an_area(monkeypatch):
	# the model asks for the trend of each pixel of an area (without its part of the year): the assistant computes
	# the trend over the area (table and chart of each month), which brings the map of each pixel, of each month
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)
	a = FakeAssistant({**assistant.DEFAULTS, 'project': 'p'})
	props = {k: {'type': 'string'} for k in ('variable', 'sensor', 'start', 'end', 'step', 'metric')}
	a.tools = assistant.model_tools(TOOLS + [{'name': 'trend_map', 'description': 'Trend map.', 'inputSchema': {
		'type': 'object', 'properties': {**props, 'region': {'type': 'object'}, 'part': {'type': 'integer'}}}}])
	a.names['389011'] = 'Sierra Nevada (Parque Nacional)'
	a.messages.append({'role': 'user', 'content': 'Monthly trend of each pixel of the WDPA 389011 since 2018'})

	async def run():
		return [e async for e in a.run_tool({'name': 'trend_map', 'arguments': {**ARGS, 'step': 'monthly'}})]
	events = asyncio.run(run())
	assert a.called[0] == 'trend_table' and a.called[1]['step'] == 'monthly' and 'part' not in a.called[1]
	assert [e['type'] for e in events if e['type'] != 'status'] == ['running', 'result', 'map']
	assert a.results[0]['tool'] == 'trend_table'
	assert a.results[0]['title'] == report.item_title('trend_table', a.called[1]) + ' · Sierra Nevada (Parque Nacional)'
	shown = events[-1]
	assert a.mapped[0] == 'trend_map' and a.mapped[1]['step'] == 'annual' and len(shown['steps']) == 12
	assert a.messages[-1]['tool_name'] == 'trend_map' and a.messages[-1]['content'].startswith('Done')


def test_waits_for_the_user(monkeypatch):
	"""The assistant computes nothing while the user has to answer: neither what the model asks for in the same answer
	as a search whose areas the user has to choose from, nor in an answer that asks the user something; once the user
	chooses (their message ends with «WDPA N»), it computes."""
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)
	answers, seen = [], []

	def model(settings, system, messages, tools):
		seen.append(len(messages))
		return answers.pop(0)

	monkeypatch.setattr(assistant, 'chat_model', model)
	doñana = {**ARGS, 'region': {'wdpa_id': 389012}}

	def call(name, args, i=0):
		return {'id': f'c{len(seen)}{i}', 'function': {'name': name, 'arguments': args}}

	async def run(a, text):
		return [e async for e in a.chat(text)]

	a = FakeAssistant({**assistant.DEFAULTS, 'project': 'p'})
	a.tools = assistant.model_tools(TOOLS)
	# a search with two areas and the computation in the same answer: the computation does not run, and the model
	# answers once more, only to ask (its calls do not run either)
	answers[:] = [{'content': '', 'tool_calls': [call('find_protected_areas', {'text': 'Doñana'}),
	                                             call('time_series', doñana, 1)]},
	              {'content': '¿Cuál de las dos áreas de Doñana quieres?',
	               'tool_calls': [call('time_series', doñana)]}]
	events = asyncio.run(run(a, 'Serie del NDVI de Doñana en 2021'))
	types = [e['type'] for e in events if e['type'] != 'status']
	assert types == ['areas', 'assistant'] and not a.results and len(seen) == 2 and not answers
	assert a.waiting and sum(m.get('content') == assistant.WAITING for m in a.messages) == 2
	assert assistant.ASK_AND_WAIT.strip() in next(m['content'] for m in a.messages if m.get('tool_name') ==
	                                             'find_protected_areas')
	# the user chooses one in the list: the model searches again and computes, and this time it runs
	answers[:] = [{'content': '', 'tool_calls': [call('find_protected_areas', {'text': 'Doñana'}),
	                                             call('time_series', doñana, 1)]},
	              {'content': 'Hecho: la serie del NDVI de Doñana está en el resultado 1.'}]
	events = asyncio.run(run(a, 'Calcula lo que he pedido con el espacio Doñana (Parque Nacional), WDPA 389012'))
	assert [e['type'] for e in events if e['type'] not in ('status', 'areas')][:2] == ['running', 'result']
	assert len(a.results) == 1 and a.called[1]['region'] == {'wdpa_id': 389012} and not a.waiting
	# an answer that asks something: its computation does not run, and the turn ends there
	a.reset()
	answers[:] = [{'content': 'Puedo calcular el NDVI o el EVI. ¿Cuál prefieres?',
	               'tool_calls': [call('time_series', ARGS)]}]
	seen.clear()
	events = asyncio.run(run(a, 'Quiero ver la vegetación de Sierra Nevada'))
	assert [e['type'] for e in events if e['type'] != 'status'] == ['assistant'] and not a.results and len(seen) == 1
	assert a.messages[-1]['content'] == assistant.WAITING
	# one area, or one with the designation asked for: it computes in the same answer, as before
	assert not assistant.must_choose([{'SITE_ID': 1}], 'x')
	areas = [{'SITE_ID': 389012, 'DESIG': 'Parque Nacional'}, {'SITE_ID': 349268, 'DESIG': 'Parque Natural'}]
	assert not assistant.must_choose(areas, 'el parque nacional de doñana')
	assert assistant.must_choose(areas, 'doñana') and not assistant.must_choose(areas, 'doñana', '... WDPA 349268')
	assert assistant.asks('¿Cuál prefieres?') and assistant.asks('Which one? **') and not assistant.asks('Done.')
	assert not assistant.asks('Is it Doñana? I compute it now.')


def test_administrative_units(monkeypatch):
	"""The administrative units found go to the page (a list to choose from) and to the model, with the region to use;
	with several, the assistant waits for the user; a code the model makes up is not computed."""
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)
	units = [{'GAUL2_CODE': 141938, 'GAUL2_NAME': 'Granada', 'GAUL1_NAME': 'Andalucía', 'GAUL0_NAME': 'Spain',
	          'ISO3_CODE': 'ESP', 'DISP_EN': 'Granada, Andalucía, Spain', 'level': 2},
	         {'GAUL2_CODE': 99, 'GAUL2_NAME': 'Granada', 'GAUL1_NAME': 'Meta', 'GAUL0_NAME': 'Colombia',
	          'ISO3_CODE': 'COL', 'DISP_EN': 'Granada, Meta, Colombia', 'level': 2}]

	class Units(FakeAssistant):
		async def call(self, name, args):
			if name == 'find_admin_units':
				return None, [json.dumps(units)], []
			return await super().call(name, args)

	a = Units({**assistant.DEFAULTS, 'project': 'p'})
	a.tools = assistant.model_tools(TOOLS)
	a.messages.append({'role': 'user', 'content': 'NDVI de la provincia de Granada'})

	async def run(call):
		return [e async for e in a.run_tool(call)]

	events = asyncio.run(run({'name': 'find_admin_units', 'arguments': {'text': 'Granada', 'level': 2}}))
	assert [e['type'] for e in events if e['type'] != 'status'] == ['units'] and a.waiting
	assert '{"admin2": 141938}: Granada, Andalucía, Spain' in a.messages[-1]['content']
	assert a.names['admin2:141938'] == 'Granada, Andalucía, Spain' and a.names['country:ESP'] == 'Spain'
	assert a.titled('time_series', {**ARGS, 'region': {'admin2': 141938}}).endswith(
		' · Granada, Andalucía, Spain (administrative unit, FAO GAUL 2025)')
	assert asyncio.run(run({'name': 'time_series', 'arguments': {**ARGS, 'region': {'admin2': 12345}}})) == []
	assert 'find_admin_units' in a.messages[-1]['content'] and 'admin2 12345' in a.messages[-1]['content']
	assert not assistant.units_must_choose(units[:1], 'Granada')
	assert assistant.units_must_choose(units, 'Granada') and not assistant.units_must_choose(units, 'x', 'admin2 99')
	# Ramsar: the designation of the user's words, in the list of the protected areas
	ramsar = {'SITE_ID': 68175, 'DESIG': 'Wetland of International Importance (Ramsar Site)',
	          'DESIG_ENG': 'Wetland of International Importance (Ramsar Site)'}
	assert assistant.designated(ramsar, 'el sitio ramsar de doñana') and not assistant.designated(ramsar, 'doñana')
	assert assistant.search_name('sitio Ramsar de Doñana') == 'Doñana'


def test_map_heading():
	"""The map of the page has a title with the full name of its variable, its own period and its region; the list of
	the maps keeps the title of the result."""
	a = FakeAssistant({**assistant.DEFAULTS, 'project': 'p'})
	a.names['389011'] = 'Sierra Nevada (Parque Nacional)'
	m = {'tool': 'map_layer', 'args': {**ARGS, 'start': '2024-01-01', 'end': '2024-12-31'}, 'result': MAP,
	     'title': 'NDVI series'}
	card = a.map_card(m)
	assert card['title'] == 'NDVI series'
	assert card['heading'] == ('Map of Normalized Difference Vegetation Index (NDVI, Sentinel-2), 2024 · Sierra Nevada '
	                           '(Parque Nacional)')
	fixed = a.map_card({'tool': 'map_layer', 'args': {'region': {'bbox': [0, 0, 1, 1]}, 'variable': 'SLOPE',
	                                                  'sensor': 'Copernicus'}, 'result': MAP, 'title': 'Slope'})
	assert fixed['heading'].startswith('Map of Slope (SLOPE, Copernicus) · ')
	other = a.map_card({'tool': 'map_layer', 'args': {'region': {'bbox': [0, 0, 1, 1]},
	                                                  'collection': 'ESA/WorldCover/v200', 'band': 'Map'},
	                    'result': MAP, 'title': 'WorldCover'})
	assert other['heading'] == a.titled('map_layer', {'region': {'bbox': [0, 0, 1, 1]},
	                                                   'collection': 'ESA/WorldCover/v200', 'band': 'Map'})


def test_unknown_protected_area(monkeypatch):
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)
	a = FakeAssistant({**assistant.DEFAULTS, 'project': 'p'})
	a.tools = assistant.model_tools(TOOLS)

	async def run(user, args=ARGS):
		a.reset()
		a.messages.append({'role': 'user', 'content': user})
		return [e async for e in a.run_tool({'name': 'time_series', 'arguments': args})]

	# 389011, made up or copied: the assistant searches the place named and takes the one of the designation asked for
	events = asyncio.run(run('Serie del NDVI en el Parque Nacional de Doñana'))
	assert [e['type'] for e in events if e['type'] != 'status'] == ['areas', 'running', 'result', 'map']
	assert a.called[1]['region'] == {'wdpa_id': 389012}
	# without the designation, two areas: the model gets them, the user sees them, nothing is computed
	events = asyncio.run(run('Serie del NDVI de Doñana'))
	assert [e['type'] for e in events if e['type'] != 'status'] == ['areas']
	assert 'SITE_ID 389012' in a.messages[-1]['content'] and 'ask the user which one' in a.messages[-1]['content']
	# the same in English: the designation after the name, as in WDPA (DESIG_ENG)
	events = asyncio.run(run('NDVI series in the Doñana National Park'))
	assert [e['type'] for e in events if e['type'] != 'status'] == ['areas', 'running', 'result', 'map']
	assert a.called[1]['region'] == {'wdpa_id': 389012}
	assert [e['type'] for e in asyncio.run(run('NDVI series of Doñana')) if e['type'] != 'status'] == ['areas']
	# no place in the message: the model has to search it, without asking the user
	assert asyncio.run(run('ndvi de un parque')) == [] and 'Search the area yourself' in a.messages[-1]['content']
	assert asyncio.run(run('ndvi of a park')) == [] and 'Search the area yourself' in a.messages[-1]['content']
	# the model gives the right one (it is among those found)
	events = asyncio.run(run('NDVI de Sierra Nevada'))
	assert 'result' in [e['type'] for e in events] and a.called[1]['region'] == {'wdpa_id': 389011}
	assert 'result' in [e['type'] for e in asyncio.run(run('El de WDPA 389011'))]  # an ID the user gave


def test_place_in():
	assert assistant.place_in('Evolución mensual del NDVI en el Parque Nacional de Sierra Nevada en 2023') == \
	       'Parque Nacional de Sierra Nevada'
	assert assistant.place_in('Doñana en 2024, NDVI') == 'Doñana'
	assert assistant.place_in('Compara los veranos del Parque Natural de la Sierra de Cazorla, Segura y Las Villas') == \
	       'Parque Natural de la Sierra de Cazorla, Segura y Las Villas'
	assert assistant.place_in('Quiero el NDVI de Sentinel-2') is None
	assert assistant.place_in('ndvi en sierra nevada') is None
	assert assistant.place_in('Usa el del Parque Nacional') is None  # only a designation
	# in English
	assert assistant.place_in('Monthly evolution of the NDVI in the Sierra Nevada National Park in 2023') == \
	       'Sierra Nevada National Park'
	assert assistant.place_in('Doñana in 2024, NDVI') == 'Doñana'
	assert assistant.place_in('The NDVI of the National Park of Sierra Nevada') == 'National Park of Sierra Nevada'
	assert assistant.place_in('Compare the summers of the Sierra de Cazorla, Segura y Las Villas Natural Park') == \
	       'Sierra de Cazorla, Segura y Las Villas Natural Park'
	assert assistant.place_in('Can I get the NDVI of Doñana since January 2018?') == 'Doñana'  # not the month
	assert assistant.place_in('I want the NDVI of Sentinel-2') is None
	assert assistant.place_in('Annual series of NDVI in the study area parcelas') is None
	assert assistant.place_in('Use the one of the National Park') is None


def test_not_ready(monkeypatch):
	monkeypatch.setattr(assistant, 'signed_in', lambda: False)
	a = FakeAssistant({**assistant.DEFAULTS, 'project': 'p'})
	a.tools = assistant.model_tools(TOOLS)

	async def run():
		args = {**ARGS, 'region': {'bbox': [-3.62, 36.86, -3.50, 36.93]}}
		return [e async for e in a.run_tool({'name': 'time_series', 'arguments': args})]

	events = asyncio.run(run())
	assert events[0]['type'] == 'error' and 'sign in' in events[0]['text'] and not a.results
	a.settings['project'] = ''  # without a project: the shared account of MonitorEO, with no sign-in
	assert a.not_ready() is None


def test_report(tmp_path):
	items = [{'tool': 'time_series', 'args': ARGS, 'result': SERIES},
	         {'tool': 'time_series', 'args': ARGS, 'result': {**SERIES, 'rows': ROWS * 5}},
	         {'tool': 'region_stats', 'args': ARGS, 'result': [{'region': 'r', 'mean': 0.4, 'n_pixels': 1234}]}]
	path = report.write(items, str(tmp_path / 'report.html'), title='NDVI <2021>', question='NDVI?', project='p',
	                    names={'389011': 'Sierra Nevada'})
	text = open(path, encoding='utf-8').read()
	assert '<title>NDVI &lt;2021&gt;</title>' in text and 'computed in Google Earth Engine with the project p' in text
	assert 'Sierra Nevada (WDPA 389011)' in text and 'Monthly time series of NDVI (Sentinel-2), 2021' in text
	assert '<td>0.501</td>' in text and '1,234' in text  # numbers as written in English
	assert 'Annex: full tables' in text and 'Table 2.' in text  # the table of 60 rows goes to the annex
	assert 'mo.time_series(region={&quot;wdpa_id&quot;: 389011}' in text and 'zenodo' in text.lower()
	assert text.count('data:image/') >= 3  # the logos, embedded
	text = open(report.write(items[:1], str(tmp_path / 'c.html'), title='t', shared=True), encoding='utf-8').read()
	assert 'computed in Google Earth Engine with the shared account of MonitorEO' in text
	assert report.item_table('trend_table', {'unit': '[ºC]', 'trends': [
		{'label': 'January', 'n': 20, 'slope': 0.05, 'p_value': 0.01, 'significant': True}]})[0] == \
	       ['Part of the year', 'Years', "Sen's slope (°C/year)", 'p-value', 'Significant']


def _polygons(path, driver):
	"""Two squares of 1 km (100 ha) in ETRS89 / UTM 30N with the field nombre, written with GDAL."""
	from osgeo import ogr, osr
	ogr.UseExceptions()
	srs = osr.SpatialReference()
	srs.ImportFromEPSG(25830)
	ds = ogr.GetDriverByName(driver).CreateDataSource(str(path))
	lyr = ds.CreateLayer('parcelas', srs, ogr.wkbPolygon)
	lyr.CreateField(ogr.FieldDefn('nombre', ogr.OFTString))
	for i, name in enumerate(('norte', 'sur')):
		x, y = 450000, 4110000 - 2000 * i
		f = ogr.Feature(lyr.GetLayerDefn())
		f.SetField('nombre', name)
		f.SetGeometry(ogr.CreateGeometryFromWkt(f'POLYGON(({x} {y},{x + 1000} {y},{x + 1000} {y + 1000},{x} {y + 1000},'
		                                        f'{x} {y}))'))
		lyr.CreateFeature(f)
	ds = None


def test_layers(tmp_path, monkeypatch):
	pytest.importorskip('osgeo')
	import zipfile
	monkeypatch.setattr(assistant, 'LAYERS', str(tmp_path / 'capas'))
	_polygons(tmp_path / 'Mis parcelas.gpkg', 'GPKG')
	(tmp_path / 'shp').mkdir()
	_polygons(tmp_path / 'shp' / 'parcelas.shp', 'ESRI Shapefile')
	with zipfile.ZipFile(tmp_path / 'parcelas.zip', 'w') as z:
		for p in (tmp_path / 'shp').iterdir():
			z.write(p, f'carpeta/{p.name}')
	a = assistant.Assistant({**assistant.DEFAULTS})
	gpkg = a.add_layer('Mis parcelas.gpkg', (tmp_path / 'Mis parcelas.gpkg').read_bytes())
	assert gpkg['name'] == 'mis_parcelas' and gpkg['features'] == 2 and abs(gpkg['area_ha'] - 200) < 0.5
	assert gpkg['crs'] == 'EPSG:25830' and gpkg['name_field'] == 'nombre'
	shp = a.add_layer('parcelas.zip', (tmp_path / 'parcelas.zip').read_bytes())
	assert shp['file'].startswith('/vsizip/') and shp['file'].endswith('carpeta/parcelas.shp') and shp['features'] == 2
	assert '- parcelas (2 polygons, 200 ha, names in the field nombre): region {"layer": "parcelas"}' in a.system_prompt()
	args = a.with_layer({'region': {'layer': 'Mis parcelas'}, 'variable': 'NDVI'})
	assert args == {'region': {'file': gpkg['file'], 'name_field': 'nombre'}, 'variable': 'NDVI'}
	for region in ('mis_parcelas', 'Mis parcelas', {'area_de_estudio': 'mis_parcelas'}, 'capa mis_parcelas',
	               {'capa': 'el área de estudio «mis_parcelas»'}, {'capa': 'Mis parcelas'},  # the ways small models
	               {'study_area': 'mis_parcelas'}, 'layer mis_parcelas',  # give it, in Spanish and in English
	               {'layer': 'the study area «mis_parcelas»'}):
		assert a.with_layer({'region': region})['region'] == args['region']
	with pytest.raises(ValueError, match='there is no study area'):
		a.with_layer({'region': {'layer': 'otra'}})
	a.messages.append({'role': 'user', 'content': 'Serie del NDVI en el área de estudio mis_parcelas'})
	assert a.with_layer({'region': {'layer': 'name'}})['region'] == args['region']  # the example, copied
	assert a.with_layer({'region': {'capa': 'nombre'}})['region'] == args['region']
	assert a.with_layer({'region': {'bbox': [0, 0, 1, 1]}}) == {'region': {'bbox': [0, 0, 1, 1]}}
	assert report.region_text(args['region'], a.all_names()).startswith('Study area «mis_parcelas» (2 polygons')
	assert set(assistant.Assistant({**assistant.DEFAULTS}).layers) == {'mis_parcelas', 'parcelas'}  # kept
	a.remove_layer('parcelas')
	assert set(assistant.load_layers()) == {'mis_parcelas'} and not (tmp_path / 'capas' / 'parcelas.zip').exists()
	with pytest.raises(ValueError, match='format not supported'):
		a.add_layer('parcelas.shp', b'')


def test_areas_text():
	areas = [{'SITE_ID': 68175, 'NAME': 'Parque Nacional de Doñana', 'DESIG': 'Ramsar Site', 'REP_AREA': 1116.0},
	         {'SITE_ID': 389012, 'NAME': 'Doñana', 'DESIG': 'Parque Nacional', 'REP_AREA': 534.2}]
	lines = assistant.areas_text(areas, 'NDVI en el Parque Nacional de Doñana').splitlines()
	assert lines[0].startswith('2 protected areas; the user sees this list')
	assert lines[1] == f'- SITE_ID 389012: Doñana, Parque Nacional, {report._num(534.2)} km² (its designation matches ' \
	                   'the request)'
	assert lines[2] == f'- SITE_ID 68175: Parque Nacional de Doñana, Ramsar Site, {report._num(1116.0)} km²'
	assert 'No protected area' in assistant.areas_text([], 'x')
	areas[1]['DESIG_ENG'] = 'National Park'  # in English: that of WDPA in English
	assert 'SITE_ID 389012' in assistant.areas_text(areas, 'NDVI in the Doñana National Park').splitlines()[1]
	assert assistant.designated({'DESIG_ENG': 'Special Protection Area (Birds Directive)'}, 'the special protection area')


def test_search_name():
	assert assistant.search_name('Parque Nacional de Doñana') == 'Doñana'
	assert assistant.search_name('parque natural de la Sierra de Cazorla') == 'Sierra de Cazorla'
	assert assistant.search_name('Reserva Natural Concertada del Peñón') == 'Peñón'
	assert assistant.search_name('ZEPA Doñana') == 'Doñana'
	assert assistant.search_name('Sierra Nevada') == 'Sierra Nevada'
	assert assistant.search_name('Parque Nacional') == 'Parque Nacional'  # nothing else: as it was
	assert assistant.search_name('Doñana National Park') == 'Doñana'  # in English, after the name
	assert assistant.search_name('the Doñana National Park') == 'Doñana'
	assert assistant.search_name('National Park of Sierra Nevada') == 'Sierra Nevada'
	assert assistant.search_name('Sierra Nevada Biosphere Reserve') == 'Sierra Nevada'
	assert assistant.search_name('Doñana SPA') == 'Doñana' and assistant.search_name('SAC Sierra Nevada') == 'Sierra Nevada'
	assert assistant.search_name('National Park') == 'National Park'


FAKE_OLLAMA = '''#!{python}
"""A fake ollama: `ollama serve` answers /api/version and /api/tags at OLLAMA_HOST."""
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
	def log_message(self, *a): pass
	def do_GET(self):
		body = json.dumps({{'version': 'fake'}} if self.path == '/api/version' else {{'models': []}}).encode()
		self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers()
		self.wfile.write(body)
host, port = os.environ['OLLAMA_HOST'].split(':')
assert sys.argv[1:] == ['serve']
HTTPServer((host, int(port)), H).serve_forever()
'''


def _free_port():
	import socket
	with socket.socket() as s:
		s.bind(('127.0.0.1', 0))
		return s.getsockname()[1]


def test_engine_install_and_start(tmp_path, monkeypatch):
	import hashlib
	import io
	import sys
	import tarfile
	from monitoreo import engine
	if sys.platform == 'win32':
		pytest.skip('the fake ollama is a script')
	script = FAKE_OLLAMA.format(python=sys.executable).encode()
	buf = io.BytesIO()
	with tarfile.open(fileobj=buf, mode='w:gz') as t:
		info = tarfile.TarInfo('ollama')
		info.size, info.mode = len(script), 0o755
		t.addfile(info, io.BytesIO(script))
	data = buf.getvalue()
	monkeypatch.setattr(engine, 'ASSETS', {('x', 'y'): ('ollama-x.tgz', len(data), hashlib.sha256(data).hexdigest())})
	monkeypatch.setattr(engine.platform, 'system', lambda: 'X')
	monkeypatch.setattr(engine.platform, 'machine', lambda: 'Y')
	monkeypatch.setattr(engine, 'PORT', _free_port())
	monkeypatch.setattr(engine, 'SYSTEM_URL', f'http://127.0.0.1:{_free_port()}')  # nothing there
	monkeypatch.setattr(engine, 'system_binary', lambda: None)
	monkeypatch.setattr(engine.urllib.request, 'urlopen', _fake_download(data))
	e = engine.Engine(str(tmp_path / 'ollama'))
	assert e.find() is None and e.installed() is None  # nothing to use: install it
	try:
		steps = [s['status'] for s in e.install()]
		assert steps[0] == 'Downloading Ollama' and steps[-1] == 'success'
		assert e.how == 'started' and e.url == f'http://127.0.0.1:{engine.PORT}' and engine.answers(e.url)
		assert e.installed() == str(tmp_path / 'ollama' / engine.OLLAMA / 'ollama')
	finally:
		e.stop()
	assert e.url is None and not engine.answers(f'http://127.0.0.1:{engine.PORT}')
	try:
		assert e.find() == f'http://127.0.0.1:{engine.PORT}' and e.how == 'started'  # installed: started again
	finally:
		e.stop()
	monkeypatch.setattr(engine, 'ASSETS', {('x', 'y'): ('ollama-x.tgz', len(data), '0' * 64)})
	with pytest.raises(RuntimeError, match='SHA-256'):
		list(e.install())


def _fake_download(data):
	import io
	real = __import__('urllib.request').request.urlopen

	def urlopen(url, *a, **k):
		if isinstance(url, str) and url.startswith('https://github.com/ollama/'):
			return io.BytesIO(data)
		return real(url, *a, **k)
	return urlopen


def test_engine_older_version(tmp_path):
	from monitoreo import engine
	old = tmp_path / 'v0.1.0'
	old.mkdir()
	(old / 'ollama').write_text('')
	(tmp_path / f'{engine.OLLAMA}.tmp').mkdir()  # an installation that did not end
	assert engine.Engine(str(tmp_path)).installed() == str(old / 'ollama')  # used until Ollama is installed again
	assert engine.Engine(str(tmp_path / 'nothing')).installed() is None


def test_downloads_and_exports(monkeypatch):
	tools = assistant.model_tools(TOOLS + [
		{'name': n, 'description': n, 'inputSchema': {'type': 'object', 'properties': {
			'region': {'type': 'object'}, 'resolution': {'type': 'number'}, 'crs': {'type': 'string'},
			'operation': {'type': 'string'}}}}
		for n in ('download_image', 'export_image_to_drive', 'task_status', 'publish_report')])
	names = [t['function']['name'] for t in tools]
	assert 'download_image' in names and 'export_image_to_drive' in names and 'publish_report' not in names
	props = next(t for t in tools if t['function']['name'] == 'download_image')['function']['parameters']['properties']
	assert 'resolution' in props and 'crs' not in props
	tif = {'file': '/tmp/NDVI.tif', 'grid': {'crs': 'EPSG:32630', 'resolution': 20, 'width': 1200, 'height': 800},
	       'resolution': 20, 'native_resolution': 10, 'images': 12, 'name': 'NDVI', 'unit': '[unitless]',
	       'min': 0.12, 'max': 0.63, 'palette': ['ffffff', '00aa00']}
	facts = dict(report.item_facts('download_image', ARGS, tif))
	assert facts['GeoTIFF'] == '1,200 × 800 pixels of 20 m (the data, of 10 m), in EPSG:32630'
	assert facts['Values (percentiles 5 and 95)'] == '0.12 to 0.63' and facts['Images'] == '12'
	assert report.item_title('download_image', ARGS) == 'Map of NDVI (Sentinel-2), 2021 (GeoTIFF)'
	assert assistant.task_text('task_status', json.dumps({'state': 'RUNNING', 'progress': 0.42})) == \
	       'Export to Google Drive: running (42%).'
	assert 'folder MonitorEO' in assistant.task_text('export_image_to_drive', json.dumps(
		{'operation': 'projects/p/operations/X', 'file': 'NDVI.tif', 'folder': 'MonitorEO'}))
	recipe = {'period': ['2018-01-01', '2021-12-31'], 'variables': [{'index': 'NDVI', 'sensor': 'Sentinel-2',
	                                                                 'metric': ['p95', 'p5']}]}
	plan = {'grids': {'study': {'width': 500, 'height': 400, 'resolution': 10, 'mb_per_variable': 0.76}},
	        'files': [{'file': '01_NDVI_p95.tif', 'pixel_filters': ['clouds', 'snow'], 'images': 310}]}
	facts = dict(report.item_facts('download_variables', {'recipe': recipe, 'area': {'bbox': [0, 0, 1, 1]},
	                                                       'name': 'modelo', 'dry_run': True}, plan))
	assert facts['Variables'] == 'NDVI (Sentinel-2): percentile 95, percentile 5' and 'only the plan' in facts['Download']
	assert report.item_table('download_variables', plan)[1] == [['01_NDVI_p95.tif', '310', 'clouds, snow']]


def test_geotiff_preview(tmp_path, monkeypatch):
	pytest.importorskip('osgeo')
	pytest.importorskip('matplotlib')
	import numpy as np
	from osgeo import gdal, osr
	gdal.UseExceptions()
	path = str(tmp_path / 'ndvi.tif')
	ds = gdal.GetDriverByName('GTiff').Create(path, 40, 30, 1, gdal.GDT_Float32)
	srs = osr.SpatialReference()
	srs.ImportFromEPSG(32630)
	ds.SetProjection(srs.ExportToWkt())
	ds.SetGeoTransform([450000, 10, 0, 4090000, 0, -10])
	band = ds.GetRasterBand(1)
	band.SetNoDataValue(-9999)
	a = np.linspace(0, 1, 1200, dtype='float32').reshape(30, 40)
	a[:5] = -9999
	band.WriteArray(a)
	ds = None
	assert report.tif_preview(path, ['ffffff', '00aa00'], 0.1, 0.9).startswith('data:image/png;base64,')
	assert report.tif_preview(str(tmp_path / 'nothing.tif')) is None
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)

	class Downloads(FakeAssistant):
		async def call(self, name, args):
			return None, [json.dumps({'file': path, 'palette': ['ffffff', '00aa00'], 'min': 0.1, 'max': 0.9,
			                          'grid': {'crs': 'EPSG:32630', 'width': 40, 'height': 30}, 'resolution': 10})], []

	a = Downloads({**assistant.DEFAULTS, 'project': 'p'})
	a.tools = assistant.model_tools(TOOLS + [{'name': 'download_image', 'description': '', 'inputSchema': {
		'type': 'object', 'properties': {'region': {'type': 'object'}, 'variable': {'type': 'string'}}}}])

	async def run():
		return [e async for e in a.run_tool({'name': 'download_image', 'arguments': {
			'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'variable': 'NDVI'}})]

	result = next(e for e in asyncio.run(run()) if e['type'] == 'result')
	assert result['image'].startswith('data:image/png') and result['files'][0]['name'] == 'ndvi.tif'
	assert 'Done:' in a.messages[-1]['content'] and '0.9' not in a.messages[-1]['content']


def _burn_tif(path):
	"""A GeoTIFF of burn_severity: bands dnbr, severity (a column of each class, -2 to 4), nbr_before and nbr_after."""
	import numpy as np
	from osgeo import gdal, osr
	gdal.UseExceptions()
	ds = gdal.GetDriverByName('GTiff').Create(path, 70, 10, 4, gdal.GDT_Float32)
	srs = osr.SpatialReference()
	srs.ImportFromEPSG(32630)
	ds.SetProjection(srs.ExportToWkt())
	ds.SetGeoTransform([450000, 10, 0, 4090000, 0, -10])
	classes = np.repeat(np.arange(-2, 5, dtype='float32'), 10)[None, :].repeat(10, axis=0)
	dnbr = np.linspace(-0.4, 0.9, 700, dtype='float32').reshape(10, 70)  # a viridis of the dNBR, what it showed
	for i, a in enumerate((dnbr, classes, dnbr + 0.3, dnbr * 0 + 0.2), 1):
		b = ds.GetRasterBand(i)
		b.SetNoDataValue(-9999)
		b.WriteArray(a)
	ds = None


def _png_colours(url):
	"""The colours '#rrggbb' of the middle row of a PNG data: URL, one per column."""
	import base64
	import io
	from matplotlib import image
	a = image.imread(io.BytesIO(base64.b64decode(url.split(',', 1)[1])), format='png')
	row = a[a.shape[0] // 2]
	return ['#' + ''.join(f'{round(float(v) * 255):02x}' for v in px[:3]) for px in row]


def test_burn_severity_with_the_colours_of_the_usgs(tmp_path, monkeypatch):
	# the result of burn_severity showed its first band, the dNBR, with the default ramp (viridis), and no legend: its
	# card shows the band severity with the colour of each class of the USGS, and a legend with the classes
	pytest.importorskip('osgeo')
	pytest.importorskip('matplotlib')
	from monitoreo import fire
	path = str(tmp_path / 'burn.tif')
	_burn_tif(path)
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)
	rows = fire.table([{'class': 1, 'sum': 12.5}, {'class': 4, 'sum': 3.0}], 'region')

	class Fire(FakeAssistant):
		async def call(self, name, args):
			return None, [json.dumps({'index': 'dNBR', 'classes': rows, 'burned_ha': {'region': 15.5}, 'scale': 10,
			                          'file': path, 'bands': ['dnbr', 'severity', 'nbr_before', 'nbr_after'],
			                          'grid': {'crs': 'EPSG:32630', 'width': 70, 'height': 10}, 'resolution': 10})], []

	a = Fire({**assistant.DEFAULTS, 'project': 'p'})
	a.tools = assistant.model_tools(TOOLS + [{'name': 'burn_severity', 'description': '', 'inputSchema': {
		'type': 'object', 'properties': {k: {'type': 'string'} for k in ('start', 'end', 'other_start', 'other_end')}}}])

	async def run():
		return [e async for e in a.run_tool({'name': 'burn_severity', 'arguments': {
			'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'start': '2022-06-01', 'end': '2022-07-31',
			'other_start': '2022-09-01', 'other_end': '2022-10-31'}})]

	result = next(e for e in asyncio.run(run()) if e['type'] == 'result')
	colours = _png_colours(result['image'])
	usgs = ['#' + fire.COLOURS[c] for c, _, _ in fire.SEVERITY]
	assert [colours[i * len(colours) // 7 + len(colours) // 14] for i in range(7)] == usgs  # each class, its colour
	legend = result['legend']['classes']
	assert [c['color'] for c in legend] == usgs
	assert legend[0]['label'] == 'Enhanced regrowth, high (dNBR < -0.25)'
	assert legend[3]['label'] == 'Low severity (dNBR 0.1 to 0.27)'
	assert legend[-1]['label'] == 'High severity (dNBR ≥ 0.66)'
	html = open(a.write_report('Fire'), encoding='utf-8').read()  # and the report, with the legend of the classes
	assert all(f'background: {c}' in html for c in usgs) and 'Moderate-high severity (dNBR 0.44 to 0.66)' in html


def test_rbr_with_the_colours_of_the_earth_engine_app():
	# the RBR (band rbr, the first one) with the reversed diverging ramp from -0.5 to 0.5, as the Earth Engine app
	from monitoreo import fire, trends
	result = {'index': 'RBR', 'file': 'x.tif', 'bands': ['rbr', 'dnbr', 'nbr_before', 'nbr_after'], 'stats': []}
	style = report.map_style('burn_severity', {'index': 'RBR'}, result)
	assert style == {'band': 1, 'min': fire.RBR_RANGE[0], 'max': fire.RBR_RANGE[1],
	                 'palette': list(reversed(trends.DIVERGING))}
	dnbr = report.map_style('burn_severity', {}, {**result, 'bands': ['dnbr', 'severity', 'nbr_before', 'nbr_after']})
	assert dnbr['band'] == 2 and [c['value'] for c in dnbr['classes']] == [-2, -1, 0, 1, 2, 3, 4]
	assert report.map_style('burn_severity', {}, {'index': 'dNBR', 'classes': []}) is None  # without its GeoTIFF
	assert report.map_style('download_image', {}, {'palette': ['000000', 'ffffff'], 'min': 0, 'max': 1}) == {
		'band': 1, 'min': 0, 'max': 1, 'palette': ['000000', 'ffffff']}  # the others, as before


RDNBR_BANDS = ['rdnbr', 'severity', 'dnbr', 'nbr_before', 'nbr_after']


def _rdnbr_tif(path):
	"""A GeoTIFF of burn_severity with the index RdNBR: bands rdnbr, severity (a column of each class of Miller & Thode
	2007, 0 to 3), dnbr, nbr_before and nbr_after."""
	import numpy as np
	from osgeo import gdal, osr
	gdal.UseExceptions()
	ds = gdal.GetDriverByName('GTiff').Create(path, 40, 10, 5, gdal.GDT_Float32)
	srs = osr.SpatialReference()
	srs.ImportFromEPSG(32630)
	ds.SetProjection(srs.ExportToWkt())
	ds.SetGeoTransform([450000, 30, 0, 4090000, 0, -30])
	classes = np.repeat(np.arange(0, 4, dtype='float32'), 10)[None, :].repeat(10, axis=0)
	rdnbr = np.linspace(-0.2, 1.2, 400, dtype='float32').reshape(10, 40)
	for i, a in enumerate((rdnbr, classes, rdnbr * 0.5, rdnbr * 0 + 0.5, rdnbr * 0 + 0.2), 1):
		b = ds.GetRasterBand(i)
		b.SetNoDataValue(-9999)
		b.SetDescription(RDNBR_BANDS[i - 1])
		b.WriteArray(a)
	ds = None


def test_rdnbr_with_the_classes_of_miller_and_thode(tmp_path, monkeypatch):
	# the result of burn_severity with the index RdNBR: its card shows the band severity with the colour of each class
	# of Miller & Thode 2007, a legend with those classes and their RdNBR, the table of their hectares, and the method
	pytest.importorskip('osgeo')
	pytest.importorskip('matplotlib')
	from monitoreo import fire
	path = str(tmp_path / 'rdnbr.tif')
	_rdnbr_tif(path)
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)
	rows = fire.table([{'class': 1, 'sum': 12.5}, {'class': 3, 'sum': 3.0}], 'region', 'RdNBR')
	stats = [{'region': 'region', 'mean': 0.3, 'median': 0.25, 'p10': 0.01, 'p90': 0.7, 'min': -0.2, 'max': 1.1,
	          'ha': 20.0}]

	class Fire(FakeAssistant):
		async def call(self, name, args):
			return None, [json.dumps({'index': 'RdNBR', 'classes': rows, 'burned_ha': {'region': 15.5}, 'stats': stats,
			                          'scale': 30, 'file': path, 'bands': RDNBR_BANDS,
			                          'grid': {'crs': 'EPSG:32630', 'width': 40, 'height': 10}, 'resolution': 30})], []

	a = Fire({**assistant.DEFAULTS, 'project': 'p'})
	a.tools = assistant.model_tools(TOOLS + [{'name': 'burn_severity', 'description': '', 'inputSchema': {
		'type': 'object', 'properties': {k: {'type': 'string'} for k in ('start', 'end', 'other_start', 'other_end',
		                                                                  'sensor', 'index')}}}])

	async def run():
		return [e async for e in a.run_tool({'name': 'burn_severity', 'arguments': {
			'region': {'bbox': [-3.62, 36.86, -3.5, 36.93]}, 'sensor': 'Landsat', 'index': 'RdNBR',
			'start': '2022-06-01', 'end': '2022-07-31', 'other_start': '2023-06-01', 'other_end': '2023-07-31'}})]

	result = next(e for e in asyncio.run(run()) if e['type'] == 'result')
	colours = _png_colours(result['image'])
	miller = ['#' + fire.RDNBR_COLOURS[c] for c, _, _ in fire.RDNBR_SEVERITY]
	assert [colours[i * len(colours) // 4 + len(colours) // 8] for i in range(4)] == miller  # each class, its colour
	legend = result['legend']['classes']
	assert [c['color'] for c in legend] == miller
	assert [c['label'] for c in legend] == ['Unchanged (RdNBR < 0.069)', 'Low severity (RdNBR 0.069 to 0.316)',
	                                        'Moderate severity (RdNBR 0.316 to 0.641)', 'High severity (RdNBR ≥ 0.641)']
	assert result['title'] == 'Burn severity (RdNBR of Landsat): before, 1 Jun 2022 - 31 Jul 2022; after, ' \
	                          '1 Jun 2023 - 31 Jul 2023'
	assert result['table']['labels'] == ['Severity class', 'RdNBR from', 'RdNBR to', 'Hectares']
	assert [r[0] for r in result['table']['rows']] == ['Unchanged', 'Low severity', 'Moderate severity', 'High severity']
	facts = dict(result['facts'])
	assert facts['Variable'] == 'Relative differenced Normalized Burn Ratio (RdNBR)'
	assert facts['Changed area (RdNBR ≥ 0.069)'] == '15.5 ha' and 'Burned area' not in facts
	assert facts['RdNBR, median (percentiles 10 to 90)'] == '0.25 (0.01 to 0.7)'
	assert facts['Method'].startswith('RdNBR (relative dNBR, Miller and Thode, 2007): dNBR / sqrt(|NBR before|)')
	for words in ('at least 0.001 (Howe et al., 2022)', 'without the factor 1000', 'without its offset',
	              'High severity (RdNBR ≥ 0.641)', 'one year after the fire', 'Unchanged is not unburned'):
		assert words in facts['Method'], words
	assert 'USGS' not in facts['Method']
	# and the report, with the legend of its classes and the table of their hectares
	html = open(a.write_report('Fire', tables=(result['id'],)), encoding='utf-8').read()
	assert all(f'background: {c}' in html for c in miller) and 'Moderate severity (RdNBR 0.316 to 0.641)' in html
	assert '<th>RdNBR from</th>' in html and '<th>dNBR from</th>' not in html


def test_rdnbr_map_style_and_title():
	# the GeoTIFF of the RdNBR is drawn as in the QGIS plugin (fire.map_style): its band severity with the classes of
	# Miller & Thode 2007; the dNBR and the RBR, as before
	from monitoreo import fire, publish
	style = report.map_style('burn_severity', {'index': 'RdNBR'}, {'index': 'RdNBR', 'bands': RDNBR_BANDS})
	assert style == {'band': 2, 'classes': fire.legend('RdNBR')}
	assert [c['color'] for c in style['classes']] == ['#' + fire.RDNBR_COLOURS[c] for c in range(4)]
	assert [report.class_label(c) for c in style['classes']][1] == 'Low severity (RdNBR 0.069 to 0.316)'
	dnbr = report.map_style('burn_severity', {}, {'bands': ['dnbr', 'severity', 'nbr_before', 'nbr_after']})
	assert dnbr == {'band': 2, 'classes': fire.legend()}
	assert report.map_style('burn_severity', {'index': 'RdNBR'}, {'index': 'RdNBR', 'classes': []}) is None
	args = {'sensor': 'Modis', 'index': 'RdNBR', 'start': '2022-06-01', 'end': '2022-07-31',
	        'other_start': '2023-06-01', 'other_end': '2023-07-31'}
	assert report.item_title('burn_severity', args).startswith('Burn severity (RdNBR of MODIS Terra): before')
	aqua = dict(args, collection='MODIS/061/MYD09GA')
	assert report.item_title('burn_severity', aqua).startswith('Burn severity (RdNBR of MODIS Aqua): before')
	facts = dict(report.item_facts('burn_severity', aqua, {'index': 'RdNBR'}))
	assert facts['Sensor'] == 'MODIS, pixel of 500 m, collection MODIS/061/MYD09GA'  # its own collection
	assert publish.fire_variable(args) == 'RdNBR' and publish.fire_variable(dict(args, index='rdnbr')) == 'RdNBR'
	assert publish.fire_variable(dict(args, index='RBR')) == 'RBR' and publish.fire_variable({}) == 'NBR'
	rbr = dict(report.item_facts('burn_severity', dict(args, sensor='Landsat', index='RBR'), {}))
	assert rbr['Method'] == report.METHODS['burn_severity_rbr']  # the RBR and the dNBR, as before
	assert dict(report.item_facts('burn_severity', dict(args, sensor='Landsat', index='dNBR'), {}))['Method'] == \
		report.METHODS['burn_severity']


def test_two_periods_and_the_rdnbr_in_the_instructions():
	# the RdNBR said 'Only burn_severity with index "RBR"': each two-period entry says its own index
	lines = {line.split(':')[0]: line for line in assistant.variables_text().splitlines()}
	assert lines['- RBR'].endswith('Only burn_severity with index "RBR" (two periods).')
	assert lines['- RdNBR'].endswith('Only burn_severity with index "RdNBR" (two periods).')
	assert 'MODIS 500 m since 2000' in lines['- RdNBR'] and 'two periods' not in lines['- NBR']
	text = ' '.join(assistant.instructions().split())
	assert 'index "RdNBR"' in text and 'Miller & Thode 2007' in text and '"MODIS/061/MYD09GA"' in text
	assert 'unchanged, low, moderate and high severity' in text and 'one year after the fire' in text


def test_fix_args_of_the_rdnbr_of_modis():
	# the collection of MODIS Aqua of the RdNBR reaches burn_severity with its sensor; not a collection of the others
	tools = assistant.model_tools(TOOLS + [{'name': 'burn_severity', 'description': '', 'inputSchema': {
		'type': 'object', 'properties': {k: {'type': 'string'} for k in ('sensor', 'index', 'collection', 'start')}}}])
	aqua = {'sensor': 'Modis', 'index': 'RdNBR', 'collection': 'MODIS/061/MYD09GA', 'start': '2022-06-01'}
	assert assistant.fix_args('burn_severity', aqua, tools) == aqua
	filled = {'sensor': 'Landsat', 'index': 'dNBR', 'collection': 'LANDSAT/LC09/C02/T1_L2', 'start': '2022-06-01'}
	assert assistant.fix_args('burn_severity', filled, tools) == {'sensor': 'Landsat', 'index': 'dNBR',
	                                                              'start': '2022-06-01'}
	# the collection of MODIS says the sensor, whatever the model wrote (none, «MODIS Aqua», another sensor)
	for sensor in (None, 'MODIS Aqua', 'Sentinel-2'):
		given = dict(aqua, sensor=sensor) if sensor else {k: v for k, v in aqua.items() if k != 'sensor'}
		assert assistant.fix_args('burn_severity', given, tools) == aqua


def test_default_model():
	assert [m['name'] for m in assistant.RECOMMENDED][0] == assistant.DEFAULTS['model'] == 'qwen3:8b'
	assert assistant.default_model('qwen3:8b', ['qwen3:8b', 'gpt-oss:20b']) == 'qwen3:8b'  # the chosen one, installed
	assert assistant.default_model('qwen3:8b', ['gpt-oss:20b', 'qwen3:4b']) == 'qwen3:4b'  # installed, in their order
	assert assistant.default_model('qwen3:8b', ['nomic-embed-text']) == 'qwen3:8b'  # not one without tools
	assert assistant.default_model('qwen3:8b', []) == 'qwen3:8b'


WIKI_PAGES = {
	'Conceptos': '# Conceptos\n\nIntro.\n\n## Variables\n\n| `NDVI` | Índice de vegetación de diferencia normalizada | '
	             'Sentinel-2 (10 m) |\n\n## Filtros por píxel\n\nSe quitan las nubes y la nieve.\n',
	'Python': '# Python\n\n## Serie temporal\n\n```python\nmo.time_series(variable="NDVI")  # NDVI NDVI NDVI\n```\n',
	'Home': '# Inicio\n\n## Cómo citar\n\nCítalo con su DOI: [Zenodo](https://doi.org/x).\n<img src="images/a.png">\n',
	'Concepts': '# Concepts\n\nIntro.\n\n## Variables\n\n| `NDVI` | Normalized difference vegetation index | '
	            'Sentinel-2 (10 m) |\n\n## Pixel filters\n\nThe clouds and the snow are removed.\n',
	'English': '# MonitorEO\n\n## How to cite\n\nCite it with its DOI: [Zenodo](https://doi.org/x).\n',
}


def test_manual(tmp_path):
	from monitoreo import manual
	for name, text in WIKI_PAGES.items():
		(tmp_path / f'{name}.md').write_text(text, encoding='utf-8')
	(tmp_path / '_Sidebar.md').write_text('[Inicio](Home)', encoding='utf-8')
	secs = manual.sections(str(tmp_path))
	assert {(s['page'], s['title']) for s in secs} >= {('Conceptos', 'Variables'), ('Inicio', 'Cómo citar')}
	cite = next(s for s in secs if s['title'] == 'Cómo citar')
	assert cite['url'].endswith('/wiki/Home#cómo-citar') and cite['text'] == 'Cítalo con su DOI: Zenodo.'
	assert manual.search('¿Qué es el NDVI?', folder=str(tmp_path))[0]['title'] == 'Variables'  # not the code
	assert manual.search('¿cómo cito MonitorEO?', folder=str(tmp_path))[0]['title'] == 'Cómo citar'
	assert manual.search('filtro de nubes', folder=str(tmp_path))[0]['title'] == 'Filtros por píxel'
	assert manual.search('xyz', folder=str(tmp_path)) == []
	assert manual.words('Imágenes, citar y cito') == ['imagen', 'cit', 'cit']
	# in English: the English pages, with their anchors
	cite = next(s for s in secs if s['title'] == 'How to cite')
	assert cite['lang'] == 'en' and cite['url'].endswith('/wiki/English#how-to-cite')
	found = manual.search('What is the NDVI?', folder=str(tmp_path))[0]
	assert found['title'] == 'Variables' and found['url'].endswith('/wiki/Concepts#variables')
	assert manual.search('How do I cite MonitorEO?', folder=str(tmp_path))[0]['url'].endswith('/wiki/English#how-to-cite')
	assert manual.search('cloud filters', folder=str(tmp_path))[0]['url'].endswith('/wiki/Concepts#pixel-filters')
	assert manual.search('¿Qué es el NDVI?', folder=str(tmp_path))[0]['url'].endswith('/wiki/Conceptos#variables')
	assert manual.search('NDVI', folder=str(tmp_path))[0]['url'].endswith('/wiki/Concepts#variables')
	assert manual.search('NDVI', folder=str(tmp_path), lang='es')[0]['url'].endswith('/wiki/Conceptos#variables')
	assert manual.words('Images, citing and cited', 'en') == ['imag', 'cit', 'cit']
	# a page without its English page yet: the Spanish one, for the questions in English too
	found = manual.search('How do I use the time series in Python?', folder=str(tmp_path))
	assert found[0]['url'].endswith('/wiki/Python#serie-temporal')
	assert manual.language('¿Qué es el NDVI?') == manual.language('NDVI de Doñana') == 'es'
	assert manual.language('What is the NDVI of Doñana?') == manual.language('NDVI') == 'en'
	assert manual.language('Compare the summers of 2023 to 2025 with those of 2018 to 2022 in Doñana') == 'en'


def test_manual_of_the_data_of_earth_engine(tmp_path):
	# the questions on the data of Earth Engine outside the catalog and on the GEE Community Catalog find their sections
	# (manual.SYNONYMS: asset, dataset, community...), not those of the Earth Engine app; with the headings of the wiki
	from monitoreo import manual
	pages = {**WIKI_PAGES,
	         'Conceptos': WIKI_PAGES['Conceptos'] + '\n## Datos de Earth Engine por su ID\n\nCualquier imagen o colección '
	                      'de imágenes por su ID.\n\n## Catálogo de la comunidad de GEE\n\nSus conjuntos de datos por '
	                      'temas.\n',
	         'Concepts': WIKI_PAGES['Concepts'] + '\n## Earth Engine data by its ID\n\nAny image or collection of images '
	                     'by its ID.\n\n## GEE Community Catalog\n\nIts datasets by theme.\n',
	         'App-de-Earth-Engine': '# App de Earth Engine\n\n## Datos\n\nLa app de Earth Engine usa los datos y el catálogo '
	                                'de Earth Engine en el navegador.\n',
	         'Earth-Engine-app': '# Earth Engine app\n\n## Data\n\nThe Earth Engine app uses the data and the catalog of '
	                             'Earth Engine in the browser.\n'}
	for name, text in pages.items():
		(tmp_path / f'{name}.md').write_text(text, encoding='utf-8')
	data_es, data_en = '/wiki/Conceptos#datos-de-earth-engine-por-su-id', '/wiki/Concepts#earth-engine-data-by-its-id'
	for question, url in (('otros datos de Earth Engine', data_es), ('¿Cómo uso un asset?', data_es),
	                      ('¿Qué es el catálogo de la comunidad?', '/wiki/Conceptos#catálogo-de-la-comunidad-de-gee'),
	                      ('other Earth Engine data', data_en), ('How do I use an asset?', data_en),
	                      ('Can I use any dataset?', data_en),
	                      ('community catalog', '/wiki/Concepts#gee-community-catalog')):
		found = manual.search(question, folder=str(tmp_path))
		assert found and found[0]['url'].endswith(url), (question, [s['url'] for s in found])
	# an autonomous community (comunidad autónoma) is not the community of the catalog: «comunidad» alone adds nothing
	assert 'comunidad' not in manual.SYNONYMS['es']


def test_manual_update(tmp_path, monkeypatch):
	# the pages of the sidebar and their English pages are downloaded; an English page not written yet is skipped
	from monitoreo import manual
	pages = {'_Sidebar': '[Inicio](Home) [Conceptos](Conceptos) [R](R)', 'Home': '# Inicio\n\nHola.\n',
	         'Conceptos': '# Conceptos\n\n## Filtros\n\nNubes.\n', 'R': '# R\n\n## Instalación\n\nCon `remotes::install_github`.\n',
	         'English': '# MonitorEO\n\nHello.\n', 'Concepts': '# Concepts\n\n## Filters\n\nClouds.\n'}
	asked = []

	def urlopen(url, timeout=None):
		import io
		import urllib.parse
		name = urllib.parse.unquote(url[len(manual.RAW):-3])
		asked.append(name)
		if name not in pages:
			raise manual.urllib.error.HTTPError(url, 404, 'Not Found', {}, None)
		return io.BytesIO(pages[name].encode())

	monkeypatch.setattr(manual.urllib.request, 'urlopen', urlopen)
	assert manual.update(str(tmp_path)) == 5
	assert asked == ['_Sidebar', 'Home', 'Conceptos', 'R', 'English', 'Concepts', 'R-package']
	assert manual.search('How do I install it in R?', folder=str(tmp_path))[0]['url'].endswith('/wiki/R#instalación')
	assert manual.search('cloud filters', folder=str(tmp_path))[0]['url'].endswith('/wiki/Concepts#filters')
	assert manual.search('filtro de nubes', folder=str(tmp_path))[0]['url'].endswith('/wiki/Conceptos#filtros')


def test_manual_tool(monkeypatch):
	found = [{'page': 'Conceptos', 'title': 'Variables', 'url': 'https://w/Conceptos#variables', 'text': 'NDVI: ...'}]
	asked = []

	sizes = []

	def search(q, lang=None, **size):
		asked.append((q, lang))
		sizes.append(size)
		return found if 'NDVI' in q else []
	monkeypatch.setattr(assistant, '_search_manual', search)
	a = FakeAssistant({**assistant.DEFAULTS, 'provider': 'ollama'})
	a.tools = assistant.model_tools(TOOLS) + [assistant.MANUAL_TOOL]

	async def run(question, key='question'):
		return [e async for e in a.run_tool({'name': 'manual', 'arguments': {key: question}})]

	events = asyncio.run(run('¿Qué es el NDVI?', 'pregunta'))  # the name of the argument before
	assert events[-1] == {'type': 'sources', 'sources': [{'title': 'Conceptos › Variables',
	                                                     'url': 'https://w/Conceptos#variables'}]}
	assert 'NDVI: ...' in a.messages[-1]['content'] and 'https://w/Conceptos#variables' in a.messages[-1]['content']
	assert asked[-1] == ('¿Qué es el NDVI?', 'es')
	asyncio.run(run('something else'))
	assert 'The manual has nothing' in a.messages[-1]['content'] and asked[-1] == ('something else', 'en')
	# the model asks in English what the user asked in Spanish: the pages in Spanish, with the words of the user
	a.messages.append({'role': 'user', 'content': '¿Cómo se calcula la severidad de un incendio?'})
	asyncio.run(run('How is the burn severity computed?'))
	assert asked[-1] == ('How is the burn severity computed? ¿Cómo se calcula la severidad de un incendio?', 'es')
	assert 'Earth-Engine-app' in assistant.instructions() and 'manual' in assistant.instructions()
	assert set(map(len, sizes)) == {0}  # the small models: 3 sections of 1800 characters (those of _search_manual)
	a.settings['provider'] = 'monitoreo'  # the big models: more and longer sections
	asyncio.run(run('¿Qué es el NDVI?'))
	assert sizes[-1] == assistant.BIG_MANUAL == {'k': 5, 'max_chars': 3000}


def test_instructions_of_the_big_models():
	# the big models of the cloud get their own rules and the guide of the page of the assistant; the small models,
	# the short ones
	small, big = assistant.instructions(), assistant.instructions(big=True)
	assert 'in five sentences at most' in small and 'How to help the user' not in small and '{' not in small[-40:]
	assert 'in five sentences at most' not in big and 'managers who are not specialists in remote sensing' in big
	for words in ('Do not interpret results, even if asked', 'You never see the results', 'Query pixel',
	              'Upload study area', 'Create report (N)', 'do not mix sensors in a series'):
		assert words in big, words
	assert big.index('Variables of the catalog') < big.index('How to help the user')
	assert 'no LaTeX' in big and 'Never tell the user to write options' in big and 'no LaTeX' not in small
	for text in (small, big):  # both: the filter of what the variable measures, off
		assert 'with the NDWI, the NDCI or the Chl-a pass quality {"water": "auto"}' in text
		assert 'with the NDSI quality {"snow": "auto"}' in text
	a = FakeAssistant({**assistant.DEFAULTS, 'provider': 'monitoreo'})
	assert 'How to help the user' in a.system_prompt() and a.advice_limit() == assistant.BIG_ADVICE
	a.settings['provider'] = 'ollama'
	assert a.system_prompt() == a.system == small and a.advice_limit() == assistant.MAX_ADVICE


def test_fix_links(monkeypatch):
	# the links to pages that are not in the wiki are replaced; those to the English pages stay, also before they are
	# downloaded
	from monitoreo import manual
	secs = [{'name': 'Conceptos', 'url': assistant.WIKI + 'Conceptos#variables'}]
	monkeypatch.setattr(manual, 'sections', lambda folder=None: secs)
	monkeypatch.setattr(manual, 'search', lambda q, k=3, lang=None: [{'url': assistant.WIKI + 'Conceptos#variables'}])
	text = (f'See {assistant.WIKI}QGIS-plugin, {assistant.WIKI}Python and {assistant.WIKI}Made-up-page. And '
	        f'{assistant.WIKI}Conceptos#nothing.')
	assert assistant.fix_links(text, '¿Qué es el NDVI?') == (
		f'See {assistant.WIKI}QGIS-plugin, {assistant.WIKI}Python and {assistant.WIKI}Conceptos#variables. And '
		f'{assistant.WIKI}Conceptos.')


def test_other_tool():
	python = ('the Python package or the command line', 'automating computations that repeat or of many regions at '
	          'once', assistant.WIKI + 'Python-package')
	assert assistant.other_tool('Quiero el NDVI de 30 parques cada mes de forma automática') == python
	assert assistant.other_tool('¿Lo puedo hacer en R?')[0] == 'the R package'
	assert assistant.other_tool('quiero editar mi capa')[0] == 'the QGIS plugin'
	assert assistant.other_tool('¿Se puede usar desde el móvil sin instalar nada?')[2] == assistant.WIKI + 'Earth-Engine-app'
	assert assistant.other_tool('Quiero publicarlo en una página web pública')[2] == assistant.WIKI + 'Results-viewer'
	assert assistant.other_tool('Serie del NDVI de cada mes de 2024 en Doñana') is None
	assert assistant.other_tool('¿Qué es el NDVI?') is None
	# in English
	assert assistant.other_tool('I want the NDVI of 30 parks every month automatically') == python
	assert assistant.other_tool('Can I do it in R?')[2] == assistant.WIKI + 'R-package'
	assert assistant.other_tool('Is there an R package?')[0] == 'the R package'
	assert assistant.other_tool('I want to edit my layer')[2] == assistant.WIKI + 'QGIS-plugin'
	assert assistant.other_tool('Can I make a map to print?')[0] == 'the QGIS plugin'
	assert assistant.other_tool('Can I use it on my phone without installing anything?')[0] == 'the Earth Engine app'
	assert assistant.other_tool('How do I publish a report for anyone to see?')[0] == 'the results viewer'
	assert assistant.other_tool('Monthly NDVI series of 2024 in Doñana') is None
	assert assistant.other_tool('What is the NDVI?') is None


def test_note_of_the_application(monkeypatch):
	# a request for another tool: the page says it, and the model gets a note that the user does not see, which
	# does not count as the words of the user
	seen = []
	monkeypatch.setattr(assistant, 'chat_model', lambda settings, system, messages, tools: seen.append(
		messages[-1]['content']) or {'content': 'Eso se hace con el paquete de R.'})

	async def run():
		a = FakeAssistant({**assistant.DEFAULTS, 'ollama': 'http://127.0.0.1:1'})
		a.tools = assistant.model_tools(TOOLS)
		return a, [e async for e in a.chat('¿Lo puedo hacer en R?')]

	a, events = asyncio.run(run())
	assert events[0] == {'type': 'other_tool', 'name': 'the R package', 'what': 'doing the computations in R',
	                     'url': assistant.WIKI + 'R-package'}
	assert seen[0].startswith('¿Lo puedo hacer en R?' + assistant.NOTE) and "language of the user's words" in seen[0]
	assert a.said() == ['¿Lo puedo hacer en R?'] and a.question == '¿Lo puedo hacer en R?'


def test_map_steps():
	# the maps that the page offers of a result: those of its steps, or of the years of a map
	steps = map_steps('map_layer', {'start': '2018-01-01', 'end': '2024-12-31', 'temporal': 'annual',
	                                          'season': ['06-01', '08-31']})
	assert [s['label'] for s in steps] == [str(y) for y in range(2018, 2025)]
	assert steps[0]['start'] == '2018-06-01' and steps[0]['end'] == '2018-08-31'  # the summer of each year
	steps = map_steps('time_series', {'start': '2024-01-01', 'end': '2024-02-29', 'step': '16-day'})
	assert [s['label'] for s in steps][:2] == ['1 Jan 2024 - 16 Jan 2024', '17 Jan 2024 - 1 Feb 2024']
	assert map_steps('map_layer', {'start': '2024-06-01', 'end': '2024-08-31'}) == []  # one year: one map
	assert map_steps('compare_map', {'start': '2018-01-01', 'end': '2024-12-31'}) == []
	assert len(map_steps('time_series', {'start': '1984-01-01', 'end': '2024-12-31', 'step': 'daily'})) == \
	       MAX_MAP_STEPS  # the last ones
	m = {'tool': 'map_layer', 'args': {'start': '2018-01-01', 'end': '2024-12-31', 'temporal': 'annual',
	                                   'interannual': 'median'}}
	assert assistant.main_label(m, m['args']) == \
	       f"Interannual value: {report.STATS['median']} of the {UNITS['annual']} (2018-2024)"
	m = {'tool': 'map_layer', 'args': {'start': '2018-01-01', 'end': '2024-12-31'}}
	assert assistant.main_label(m, m['args']) == 'Whole period (2018-2024)'
	assert assistant.main_label(m, {'start': '2010-01-01'}) == 'Last year of the period (2018-2024)'
	# a trend: the annual one, and that of each month
	steps = map_steps('trend_table', {'start': '2018-01-01', 'end': '2024-12-31', 'step': 'monthly'})
	assert len(steps) == 12 and steps[6] == {'key': 'part:7', 'label': 'Trend of July', 'part': 7}
	assert map_steps('trend_table', {'start': '2018-01-01', 'end': '2024-12-31', 'step': 'annual'}) == []
	m = {'tool': 'trend_map', 'args': {'start': '2018-01-01', 'end': '2024-12-31', 'step': 'annual'}}
	assert assistant.main_label(m, m['args']) == "Annual trend: Sen's slope of the values of each year (2018-2024)"
	m = {'tool': 'trend_map', 'args': {'start': '2018-01-01', 'end': '2024-12-31', 'step': 'monthly', 'part': 7}}
	assert assistant.main_label(m, m['args']) == steps[6]['label']


def test_interannual():
	# small models write temporal «interannual»: the annual values, then the interannual one; the facts say so
	tools = assistant.model_tools([{'name': 'map_layer', 'description': '', 'inputSchema': {'type': 'object',
	                                'properties': {'temporal': {'type': 'string'}, 'metric': {'type': 'string'}}}}])
	assert assistant.fix_args('map_layer', {'temporal': 'interannual', 'metric': 'median'}, tools) == \
	       {'temporal': 'annual', 'metric': 'median'}
	facts = dict(report.item_facts('map_layer', {**ARGS, 'metric': 'median', 'temporal': 'annual'}))
	assert facts['Temporal aggregation'] == 'median of each year and, between the years, mean (interannual value)'
	assert 'Temporal aggregation' not in dict(report.item_facts('map_layer', ARGS))


def test_open_end():
	today = assistant.dt.date(2026, 11, 3)
	args = {'variable': 'NDVI', 'start': '2025-01-01', 'end': '2025-11-03'}
	for said in (['Evolución mensual del NDVI en el Parque Nacional de Sierra Nevada desde 2025'],
	             ['NDVI desde el año 2025 en Doñana', 'Calcula lo que he pedido con el espacio Doñana, WDPA 349467'],
	             ['NDVI desde enero de 2025']):
		assert assistant.open_end(args, said, today)['end'] == '2026-11-03', said
	for said in (['NDVI desde 2025 hasta junio'], ['NDVI de 2025'], ['NDVI desde 2018 a 2025'],
	             ['NDVI desde 2018', 'y ahora solo 2025']):  # an end, or a later message with its years
		assert assistant.open_end(args, said, today) == args, said
	assert assistant.open_end({**args, 'end': '2026-11-03'}, ['desde 2025'], today)['end'] == '2026-11-03'
	# in English
	for said in (['Monthly evolution of the NDVI in the Sierra Nevada National Park since 2025'],
	             ['NDVI since the year 2025 in Doñana', 'Compute what I asked for with the protected area Doñana, WDPA 1'],
	             ['NDVI since January 2025'], ['NDVI since 1 January 2025'], ['NDVI since January 1, 2025'],
	             ['NDVI from 2025 onwards']):
		assert assistant.open_end(args, said, today)['end'] == '2026-11-03', said
	for said in (['NDVI since 2025 until June'], ['NDVI of 2025'], ['NDVI from 2018 to 2025'], ['NDVI from 2025'],
	             ['NDVI since 2018', 'and now only 2025']):
		assert assistant.open_end(args, said, today) == args, said


def test_check_update(monkeypatch):
	from monitoreo import update
	monkeypatch.setattr(update, 'local_copy', lambda: None)
	monkeypatch.setattr(update, 'installed', lambda: ('0.3.11', 'a' * 40, None))
	monkeypatch.setattr(update, 'latest', lambda: 'b' * 40)
	assert assistant.check_update() == {'available': True, 'current': 'aaaaaaa', 'latest': 'bbbbbbb'}
	monkeypatch.setattr(update, 'latest', lambda: 'a' * 40)
	assert assistant.check_update()['available'] is False
	monkeypatch.setattr(update, 'latest', lambda: (_ for _ in ()).throw(OSError('offline')))
	assert assistant.check_update() is None
	monkeypatch.setattr(update, 'local_copy', lambda: '/src/monitoreo')
	assert assistant.check_update() is None  # a clone is not updated


def test_update_in_window(monkeypatch):
	# opened without a terminal: a small window says that it is installing a new version, only while it does
	import sys
	import threading
	import types
	from monitoreo import cli, update
	windows, shown = [], threading.Event()

	def create_window(*args, **kwargs):
		windows.append(kwargs)
		shown.set()
		return types.SimpleNamespace(destroy=lambda: windows.append('closed'))
	fake = types.SimpleNamespace(create_window=create_window, start=lambda func: func())
	monkeypatch.setitem(sys.modules, 'webview', fake)
	monkeypatch.setattr(update, 'ensure_latest', lambda extras, installing=None: 'current')
	assert cli._update_in_window() == 'current' and windows == []

	def new_version(extras, installing=None):
		installing()
		shown.wait(5)  # pip takes a while
		return 'updated'
	monkeypatch.setattr(update, 'ensure_latest', new_version)
	assert cli._update_in_window() == 'shown'  # the assistant starts in another process
	assert 'Updating MonitorEO' in windows[0]['html'] and windows[1] == 'closed'


def test_window_asks_while_computing(monkeypatch):
	# the cross of the window (or Cmd+Q) asks before closing only while something is computed, as Close
	import sys
	import types

	class Handlers(list):
		def __iadd__(self, func):
			self.append(func)
			return self
	win = types.SimpleNamespace(confirm_close=False, events=types.SimpleNamespace(closing=Handlers()))
	texts, busy = {}, [True]
	fake = types.SimpleNamespace(settings={}, create_window=lambda *a, **k: win,
	                             start=lambda localization=None: texts.update(localization))
	monkeypatch.setitem(sys.modules, 'webview', fake)
	assert assistant._show_window('http://127.0.0.1:1/', busy=lambda: busy[0])
	win.events.closing[0]()
	assert win.confirm_close is True and 'computation is running' in texts['global.quitConfirmation']
	busy[0] = False
	win.events.closing[0]()
	assert win.confirm_close is False and texts['global.quit'] == 'Close'


def test_events_of_the_conversation(monkeypatch):
	answers = iter([{'content': 'First answer.'}, {'content': 'Second.'}])
	monkeypatch.setattr(assistant, 'chat_model', lambda *a: next(answers))

	async def run():
		a = FakeAssistant({**assistant.DEFAULTS, 'ollama': 'http://127.0.0.1:1'})
		a.tools = assistant.model_tools(TOOLS)

		async def until_done(since=0):
			got = []
			async for e in a.follow(since, ping=0.05):
				got.append(e)
				if e['type'] == 'done':
					return got

		a.start('Hello')
		with pytest.raises(ValueError, match='wait'):
			a.start('Another one')  # one message at a time
		first = await until_done()
		later = await until_done()  # a page opened afterwards gets the whole conversation again
		a.start('Otra pregunta')
		second = await until_done(first[-1]['seq'] + 1)  # and one that follows, only what is new
		a.new_conversation()
		after_reset = [e async for e in _take(a.follow(second[-1]['seq'] + 1), 1)]
		return first, later, second, after_reset, a

	first, later, second, after_reset, a = asyncio.run(run())
	assert [e['type'] for e in first if e['type'] != 'status'] == ['user', 'assistant', 'done']
	assert later == first and [e['seq'] for e in first] == list(range(len(first)))
	assert second[0] == {'type': 'user', 'text': 'Otra pregunta', 'seq': len(first)}
	assert after_reset[0]['type'] == 'reset' and not a.messages and not a.running()


async def _take(events, n):
	async for e in events:
		yield e
		n -= 1
		if not n:
			return


def test_report_without_tables(tmp_path):
	items = [{'tool': 'time_series', 'args': ARGS, 'result': SERIES, 'table': False},
	         {'tool': 'region_stats', 'args': ARGS, 'result': {'rows': [{'region': 'r', 'mean': 0.4, 'n_pixels': 1234}]}}]
	text = open(report.write(items, str(tmp_path / 'i.html'), title='t'), encoding='utf-8').read()
	assert '<td>0.501</td>' not in text and '1,234' in text  # the table of the series out, that of the stats in


def test_map_and_pixel():
	calls = []

	class Maps(FakeAssistant):
		async def call(self, name, args):
			calls.append((name, args))
			if name == 'region_stats':
				return None, [json.dumps({'rows': [{'region': 'point', 'mean': 0.42, 'n_pixels': 1}], 'unit': '[unitless]'})], []
			if name in ('map_layer', 'trend_map'):
				return None, [json.dumps({'url': 'https://ee/new/{z}/{x}/{y}', 'bounds': [-3.6, 36.9, -3.5, 37.0],
				                          'unit': '[unitless] / year' if name == 'trend_map' else '[unitless]'})], []
			if name == 'trend_table':
				return None, [json.dumps({'trends': [{'part': p, 'slope': p / 1000, 'p_value': 0.2} for p in (1, 7)]})], []
			return None, [json.dumps(SERIES)], ['data:image/png;base64,iVBORw0KGgo=']

	async def run():
		a = Maps({**assistant.DEFAULTS, 'project': 'p'})
		args = {**ARGS, 'start': '2024-06-01', 'end': '2024-08-31', 'season': ['06-01', '08-31']}
		a.results.append({'id': 1, 'tool': 'map_layer', 'args': args, 'image': None, 'title': 'Map',
		                  'result': {'url': 'https://ee/old/{z}/{x}/{y}', 'bounds': [-3.6, 36.9, -3.5, 37.0],
		                             'min': 0.1, 'max': 0.6, 'palette': ['ffffff', '00aa00'], 'unit': '[unitless]'}})
		card = a.card(a.results[0])
		px = await a.pixel(1, -3.55, 36.95)
		rid = a.keep_pixel(px['key'])
		url = await a.refresh_map(1)
		return a, card, px, rid, url

	a, card, px, rid, url = asyncio.run(run())
	assert card['map'] == {'url': 'https://ee/old/{z}/{x}/{y}', 'bounds': [-3.6, 36.9, -3.5, 37.0], 'pixel': True,
	                       'trend': False}
	assert px['value'] == 0.42 and px['image'].startswith('data:image/png') and px['n'] == 12
	assert calls[0] == ('region_stats', {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'season': ['06-01', '08-31'],
	                                     'region': {'point': [-3.55, 36.95]}, 'start': '2024-06-01',
	                                     'end': '2024-08-31', 'metric': 'median', 'temporal': 'period'})
	assert calls[1][0] == 'time_series' and calls[1][1]['step'] == '16-day'  # a period of months: by 16 days
	assert rid == 2 and a.results[1]['tool'] == 'time_series' and a.events[-1]['type'] == 'result'
	assert px['title'] == '16-day time series of NDVI at the pixel 36.95000, -3.55000' and px['label'] == 'value'
	assert report.region_text(a.results[1]['args']['region']) == 'Pixel at 36.95000, -3.55000 (lat., lon.)'
	assert url == 'https://ee/new/{z}/{x}/{y}' and a.results[0]['result']['url'] == url
	assert calls[-1] == ('map_layer', {**a.results[0]['args'], 'vmin': 0.1, 'vmax': 0.6, 'quick': True})  # same colours
	with pytest.raises(ValueError, match='has no map'):
		asyncio.run(a.pixel(2, 0, 0))

	# a series: the map of its period, and on a pixel the series with the step of that of the result
	async def series():
		a = Maps({**assistant.DEFAULTS, 'project': 'p'})
		args = {**ARGS, 'start': '2018-01-01', 'end': '2024-12-31', 'step': 'monthly', 'metric': 'mean'}
		a.results.append({'id': 1, 'tool': 'time_series', 'args': args, 'result': SERIES, 'image': None,
		                  'title': 'Series'})
		shown = await a.period_map(a.results[0])
		calls.clear()
		return a, shown, await a.pixel(1, -3.55, 36.95)

	a, shown, px = asyncio.run(series())
	assert shown['type'] == 'map' and shown['map']['url'] == 'https://ee/new/{z}/{x}/{y}'
	assert shown['main'] == 'Last year of the period (2024)' and len(shown['steps']) == 84  # the months of 7 years
	assert shown['steps_label'] == 'Date'
	assert shown['steps'][0] == {'key': '2018-01-01/2018-01-31', 'label': 'Jan 2018'}
	assert a.results[0]['map']['args']['start'] == '2024-01-01'  # the last year of the period, which is longer
	assert px['value'] == 0.42 and calls[0][1]['metric'] == 'median' and calls[0][1]['start'] == '2024-01-01'
	assert calls[1][1]['start'] == '2018-01-01'  # the series of the pixel, over the whole period
	assert calls[1][0] == 'time_series' and calls[1][1]['step'] == 'monthly'  # 7 years, but monthly as the result

	# the map of a month, with the colours of that of the result; its pixel, and its tiles again
	async def step():
		calls.clear()
		shown = await a.step_map(1, '2019-03-01/2019-03-31')
		await a.step_map(1, '2019-03-01/2019-03-31')  # made once
		return shown, await a.pixel(1, -3.55, 36.95, '2019-03-01/2019-03-31')

	shown, px = asyncio.run(step())
	assert shown['key'] == '2019-03-01/2019-03-31'
	assert shown['title'] == report.item_title('map_layer', {**ARGS, 'start': '2019-03-01', 'end': '2019-03-31'}) + \
	       ' · WDPA 389011'
	assert calls[0] == ('map_layer', {'region': ARGS['region'], 'variable': 'NDVI', 'sensor': 'Sentinel-2',
	                                  'start': '2019-03-01', 'end': '2019-03-31', 'metric': 'mean', 'vmin': None,
	                                  'vmax': None, 'quick': True})
	assert calls[1][0] == 'region_stats' and calls[1][1]['start'] == '2019-03-01' and calls[2][0] == 'time_series'
	with pytest.raises(ValueError, match='does not exist'):
		asyncio.run(a.step_map(1, '1990-01-01/1990-01-31'))

	# a trend: the map of the annual one, and of a month; their tiles again, with the same colours
	async def trend():
		a = Maps({**assistant.DEFAULTS, 'project': 'p'})
		args = {**ARGS, 'start': '2018-01-01', 'end': '2024-12-31', 'step': 'monthly', 'metric': 'median'}
		a.results.append({'id': 1, 'tool': 'trend_table', 'args': args, 'result': {}, 'image': None, 'title': 'T'})
		calls.clear()
		shown = await a.period_map(a.results[0])
		month = await a.step_map(1, 'part:7')
		await a.refresh_map(1, 'part:7')
		return shown, month, await a.pixel(1, -3.55, 36.95, 'part:7')

	shown, month, px = asyncio.run(trend())
	trend_args = {**ARGS, 'start': '2018-01-01', 'end': '2024-12-31', 'step': 'monthly', 'metric': 'median', 'part': 7}
	assert month['title'].startswith(report.item_title('trend_map', trend_args) + ' (July)')
	per_year = report.unit_text('[unitless] / year', per_year=True)
	assert month['legend'] is None or month['legend']['unit'] == per_year
	assert px['value'] == 0.007 and px['p_value'] == 0.2  # the slope of July at the pixel
	assert px['label'] == "Sen's slope" and px['unit'] == per_year
	assert calls[3][0] == 'trend_table' and calls[3][1]['step'] == 'monthly' and calls[3][1]['region'] == {
		'point': [-3.55, 36.95]}
	assert calls[0] == ('trend_map', {'region': ARGS['region'], 'variable': 'NDVI', 'sensor': 'Sentinel-2',
	                                  'start': '2018-01-01', 'end': '2024-12-31', 'step': 'annual',
	                                  'metric': 'median', 'quick': True})
	assert shown['steps_label'] == 'Part of the year' and shown['steps'][6]['label'] == map_steps('trend_table', {
		'start': '2018-01-01', 'end': '2024-12-31', 'step': 'monthly'})[6]['label']
	assert calls[1][0] == 'trend_map' and calls[1][1]['step'] == 'monthly' and calls[1][1]['part'] == 7
	assert calls[2][0] == 'trend_map' and calls[2][1]['quick'] and calls[2][1]['part'] == 7

	# «Significant pixels only»: the same maps with only the pixels of p < 0.05, and their pixels
	async def significant():
		a = Maps({**assistant.DEFAULTS, 'project': 'p'})
		args = {**ARGS, 'start': '2018-01-01', 'end': '2024-12-31', 'step': 'monthly', 'metric': 'median'}
		a.results.append({'id': 1, 'tool': 'trend_table', 'args': args, 'result': {}, 'image': None, 'title': 'T'})
		await a.period_map(a.results[0])
		calls.clear()
		main, month = await a.step_map(1, '', True), await a.step_map(1, 'part:7', True)
		return main, month, await a.pixel(1, -3.55, 36.95, 'part:7|p<0.05'), await a.step_map(1, '', False)

	main, month, px, plain = asyncio.run(significant())
	assert main['key'] == '|p<0.05' and month['key'] == 'part:7|p<0.05' and plain['key'] == ''
	assert calls[0][0] == 'trend_map' and calls[0][1]['alpha'] == 0.05 and calls[0][1]['step'] == 'annual'
	assert calls[1][1]['alpha'] == 0.05 and calls[1][1]['part'] == 7 and calls[1][1]['quick']
	assert main['title'].endswith(', significant pixels only (p < 0.05) · WDPA 389011') and main['map']['trend']
	assert px['value'] == 0.007
	facts = dict(report.item_facts('trend_map', {**ARGS, 'step': 'annual', 'alpha': 0.05}))
	assert facts['Pixels'] == 'only those with a significant trend (Mann-Kendall, p < 0.05)'

	# a map of interannual values (of each year): the series of a pixel, by years
	a.results.append({'id': 2, 'tool': 'map_layer', 'image': None, 'title': 'Map',
	                  'args': {**ARGS, 'start': '2021-06-01', 'end': '2024-08-31', 'temporal': 'annual'},
	                  'result': {'url': 'https://ee/old/{z}/{x}/{y}', 'bounds': [-3.6, 36.9, -3.5, 37.0]}})
	calls.clear()
	asyncio.run(a.pixel(2, -3.55, 36.95))
	assert calls[0][1]['temporal'] == 'annual' and calls[1][1]['step'] == 'annual'


def test_fixed_layers():
	"""The maps of a fixed layer without dates (elevation, slope): their card and its name in the page, the map of
	their statistics, and on a pixel its value without a time series (the arguments have no start nor end)."""
	calls = []

	class Maps(FakeAssistant):
		async def call(self, name, args):
			calls.append((name, args))
			if name == 'region_stats':
				return None, [json.dumps({'rows': [{'region': 'point', 'mean': 2950.0, 'n_pixels': 1}], 'unit': '[m]'})], []
			return None, [json.dumps({**MAP, 'unit': '[m]'})], []

	async def run():
		a = Maps({**assistant.DEFAULTS, 'project': 'p'})
		args = {'region': {'wdpa_id': 389011}, 'variable': 'ELEVATION', 'sensor': 'Copernicus'}
		a.results.append({'id': 1, 'tool': 'map_layer', 'args': args, 'image': None, 'title': a.titled('map_layer', args),
		                  'result': {**MAP, 'unit': '[m]'}})
		stats = {**args, 'variable': 'SLOPE'}
		a.results.append({'id': 2, 'tool': 'region_stats', 'args': stats, 'image': None, 'title': 'Statistics',
		                  'result': {'rows': [{'region': 'Sierra Nevada', 'mean': 20.1}], 'unit': '[°]'}})
		card = a.card(a.results[0])
		px = await a.pixel(1, -3.3, 37.05)
		shown = await a.period_map(a.results[1])
		return a, card, px, shown

	a, card, px, shown = asyncio.run(run())
	assert a.results[0]['title'] == 'Map of ELEVATION (Copernicus) · WDPA 389011'
	assert card['main'] == 'Fixed layer, without dates' and card['steps'] == [] and card['map']['series'] is False
	assert px == {'lon': -3.3, 'lat': 37.05, 'value': 2950.0, 'unit': 'm', 'label': 'value'}  # no key: no series
	assert calls[0] == ('region_stats', {'variable': 'ELEVATION', 'sensor': 'Copernicus',
	                                     'region': {'point': [-3.3, 37.05]}})
	assert shown['main'] == 'Fixed layer, without dates' and shown['map']['series'] is False
	assert calls[1] == ('map_layer', {'region': {'wdpa_id': 389011}, 'variable': 'SLOPE', 'sensor': 'Copernicus',
	                                  'quick': True})


# The data of Earth Engine outside the catalog: the tools that find and describe them, and the compute tools with
# their arguments instead of variable and sensor (as the MCP server lists them)
OPTIONAL = {'anyOf': [{'type': 'string'}, {'type': 'null'}]}
SOURCE_PROPS = {'variable': OPTIONAL, 'sensor': OPTIONAL, 'collection': OPTIONAL, 'image': OPTIONAL, 'band': OPTIONAL,
                'band_scale': {'anyOf': [{'type': 'number'}, {'type': 'null'}]},
                'band_offset': {'anyOf': [{'type': 'number'}, {'type': 'null'}]}, 'unit': OPTIONAL}
DATA_TOOLS = [
	{'name': 'describe_asset', 'description': 'An image or collection of Earth Engine by its ID.', 'inputSchema': {
		'type': 'object', 'properties': {'asset': {'type': 'string'}}, 'required': ['asset']}},
	{'name': 'community_themes', 'description': 'Themes of the GEE Community Catalog.', 'inputSchema': {
		'type': 'object', 'properties': {'lang': {'type': 'string'}}}},
	{'name': 'community_datasets', 'description': 'Datasets of the GEE Community Catalog.', 'inputSchema': {
		'type': 'object', 'properties': {'theme': OPTIONAL, 'text': OPTIONAL, 'kind': OPTIONAL,
		                                 'limit': {'type': 'integer'}}}},
	{'name': 'map_layer', 'description': 'Map.', 'inputSchema': {'type': 'object', 'properties': {
		**SOURCE_PROPS, 'region': {'type': 'object'}, 'start': OPTIONAL, 'end': OPTIONAL, 'metric': {'type': 'string'},
		'temporal': {'type': 'string'}, 'interannual': {'type': 'string'}, 'terrain': OPTIONAL,
		'vmin': {'type': 'number'}, 'vmax': {'type': 'number'}, 'quick': {'type': 'boolean'}}, 'required': ['region']}},
]
TERRACLIMATE = {'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr', 'band_scale': 1, 'unit': 'mm'}
ASSET = {'asset': 'IDAHO_EPSCOR/TERRACLIMATE', 'type': 'image_collection', 'use': 'collection',
         'how': "a collection of images with dates: give it as collection='IDAHO_EPSCOR/TERRACLIMATE'",
         'title': 'TerraClimate: Monthly Climate and Climatic Water Balance', 'source': 'Earth Engine data catalog',
         'dates': ['1958-01-01', '2024-12-01'],
         'bands': [{'band': b, 'description': 'x' * 400, 'units': 'mm', 'unit': 'mm'} for b in ('aet', 'def', 'pr')],
         'arguments': TERRACLIMATE, 'notes': ['monthly'],
         'references': [{'id': 'abatzoglou2018', 'citation': 'Abatzoglou et al. (2018)'}], 'credits': []}
COMMUNITY = [{'id': 'projects/sat-io/open-datasets/CHIRPS/v3', 'title': 'CHIRPS v3 precipitation',
              'type': 'image_collection', 'theme': 'Weather & Climate', 'provider': 'CHC', 'license': 'CC BY 4.0',
              'tags': 'rain, ' * 100, 'docs': 'https://gee-community-catalog.org/projects/chirps_v3/'},
             {'id': 'projects/sat-io/open-datasets/RAIN/mean', 'title': 'Mean rain', 'type': 'image',
              'theme': 'Weather & Climate', 'docs': 'https://gee-community-catalog.org/projects/rain/'}]


class Data(FakeAssistant):
	"""An assistant whose MCP server also answers describe_asset, the GEE Community Catalog and the statistics."""

	async def call(self, name, args):
		self.calls = getattr(self, 'calls', []) + [(name, args)]
		if name == 'describe_asset':
			return None, [json.dumps(ASSET)], []
		if name == 'community_datasets':
			return None, [json.dumps(COMMUNITY)], []
		if name == 'community_themes':
			return None, [json.dumps([{'theme': 'Weather & Climate', 'name': 'Weather & Climate', 'datasets': 20}])], []
		if name == 'region_stats':
			return None, [json.dumps({'rows': [{'region': 'point', 'mean': 512.5, 'n_pixels': 1}], 'unit': 'mm'})], []
		if name in ('map_layer', 'trend_map'):
			return None, [json.dumps({**MAP, 'unit': 'mm', 'url': f'https://ee/{len(self.calls)}/{{z}}/{{x}}/{{y}}'})], []
		return None, [json.dumps({**SERIES, 'unit': 'mm'})], ['data:image/png;base64,iVBORw0KGgo=']


def test_data_of_earth_engine_by_its_id(monkeypatch):
	"""The model finds a dataset in the GEE Community Catalog, reads what an ID is with describe_asset (both answers go
	to it, the bands last and the datasets a line each) and maps a collection by its ID and band: the result has its
	title, facts and references, and a pixel of its map keeps the collection, its band, scale and unit."""
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)
	tools = assistant.model_tools(TOOLS + DATA_TOOLS)
	names = [t['function']['name'] for t in tools]
	assert {'describe_asset', 'community_themes', 'community_datasets'} <= set(names)
	params = {t['function']['name']: t['function']['parameters']['properties'] for t in tools}
	assert 'limit' not in params['community_datasets'] and 'lang' not in params['community_themes']  # hidden
	assert set(SOURCE_PROPS) <= set(params['map_layer']) and 'quick' not in params['map_layer']
	region = {'bbox': [-3.5, 37, -3, 37.2]}
	mapped = {'region': region, **TERRACLIMATE, 'start': '2015-01-01', 'end': '2020-12-31', 'metric': 'sum',
	          'temporal': 'annual', 'interannual': 'mean'}
	answers = iter([
		{'content': '', 'tool_calls': [{'function': {'name': 'community_datasets', 'arguments': {'text': 'rain'}}}]},
		{'content': '', 'tool_calls': [{'function': {'name': 'describe_asset',
		                                             'arguments': {'asset': 'IDAHO_EPSCOR/TERRACLIMATE'}}}]},
		{'content': '', 'tool_calls': [{'function': {'name': 'map_layer', 'arguments': mapped}}]},
		{'content': 'Done: the map is in result 1.'},
	])
	monkeypatch.setattr(assistant, 'chat_model', lambda settings, system, messages, tools: next(answers))

	async def run():
		a = Data({**assistant.DEFAULTS, 'project': 'p'})
		a.tools = tools
		events = [e async for e in a.chat('Mean annual precipitation of TerraClimate in this rectangle, 2015 to 2020')]
		return a, events, await a.pixel(1, -3.25, 37.1)

	a, events, px = asyncio.run(run())
	statuses = [e['text'] for e in events if e['type'] == 'status']
	assert 'Looking at the datasets of the GEE Community Catalog…' in statuses
	assert 'Reading the description of IDAHO_EPSCOR/TERRACLIMATE in Earth Engine…' in statuses
	answers_of = {m['tool_name']: m['content'] for m in a.messages if m['role'] == 'tool'}
	found = answers_of['community_datasets']  # a line each, without the tags
	assert '- projects/sat-io/open-datasets/CHIRPS/v3 (image collection): CHIRPS v3 precipitation; theme Weather & ' \
	       'Climate; https://gee-community-catalog.org/projects/chirps_v3/' in found
	assert '- projects/sat-io/open-datasets/RAIN/mean (image): Mean rain' in found and 'rain, rain' not in found
	described = json.loads(answers_of['describe_asset'])  # all of it, the bands last
	assert list(described)[-1] == 'bands' and described['arguments'] == TERRACLIMATE and described == ASSET
	# the map: its title and facts name the ID and the band, and it cites the dataset
	assert [e['type'] for e in events if e['type'] not in ('status', 'eecu')] == ['running', 'result', 'assistant']
	assert a.calls[2] == ('map_layer', mapped)
	result = next(e for e in events if e['type'] == 'result')
	assert result['title'] == ('Map of IDAHO_EPSCOR/TERRACLIMATE pr, 2015-2020 · Rectangle of longitude -3.5 to -3 and '
	                           'latitude 37 to 37.2')
	facts = dict(result['facts'])
	assert facts['Data'] == 'Earth Engine image collection IDAHO_EPSCOR/TERRACLIMATE, band pr; values × 1 + 0; unit mm'
	assert facts['Discarded pixels'].startswith('none') and 'Variable' not in facts
	assert any(r['citation'].startswith('Abatzoglou') for r in result['references'])  # TerraClimate
	assert result['legend']['unit'] == 'mm' and result['map']['pixel'] and not result['rgb']
	assert result['main'].startswith('Interannual value')
	# its pixel: the value of the map and the series of the pixel, with the same data
	same = {k: v for k, v in mapped.items() if k in assistant.SOURCE}
	assert a.calls[3] == ('region_stats', {**same, 'region': {'point': [-3.25, 37.1]}, 'start': '2015-01-01',
	                                       'end': '2020-12-31', 'metric': 'sum', 'temporal': 'annual'})
	assert a.calls[4] == ('time_series', {**same, 'region': {'point': [-3.25, 37.1]}, 'start': '2015-01-01',
	                                      'end': '2020-12-31', 'step': 'annual'})
	assert px['value'] == 512.5 and px['unit'] == 'mm'
	assert px['title'] == 'Annual time series of IDAHO_EPSCOR/TERRACLIMATE pr at the pixel 37.10000, -3.25000'


def test_series_and_fixed_image_of_earth_engine(tmp_path):
	"""A series of a collection of Earth Engine by its ID: the map of its period and those of its steps keep the data
	(collection, band, scale, unit); a fixed image (image=): a map without dates, also when the model gives it dates,
	on a pixel its value without a series, and the report."""
	region = {'bbox': [-3.5, 37, -3, 37.2]}

	async def series():
		a = Data({**assistant.DEFAULTS, 'project': 'p'})
		args = {'region': region, **TERRACLIMATE, 'start': '2018-01-01', 'end': '2020-12-31', 'step': 'monthly',
		        'metric': 'sum'}
		a.results.append({'id': 1, 'tool': 'time_series', 'args': args, 'result': {**SERIES, 'unit': 'mm'},
		                  'image': None, 'title': a.titled('time_series', args)})
		shown = await a.period_map(a.results[0])
		step = await a.step_map(1, '2019-03-01/2019-03-31')
		return a, shown, step

	a, shown, step = asyncio.run(series())
	same = {'region': region, **TERRACLIMATE}
	assert a.calls[0] == ('map_layer', {**same, 'start': '2020-01-01', 'end': '2020-12-31', 'metric': 'median',
	                                    'quick': True})
	assert shown['title'].startswith('Monthly time series of IDAHO_EPSCOR/TERRACLIMATE pr')
	assert shown['heading'].startswith('Map of IDAHO_EPSCOR/TERRACLIMATE pr, 2020')
	assert len(shown['steps']) == 36 and shown['main'] == 'Last year of the period (2020)'
	assert a.calls[1] == ('map_layer', {**same, 'start': '2019-03-01', 'end': '2019-03-31', 'metric': 'sum',
	                                    'vmin': 0, 'vmax': 1, 'quick': True})
	assert step['title'].startswith('Map of IDAHO_EPSCOR/TERRACLIMATE pr, ')

	async def fixed():
		a = Data({**assistant.DEFAULTS, 'project': 'p'})
		args = {'region': region, 'image': 'WORLDCLIM/V1/BIO', 'band': 'bio01', 'band_scale': 0.1, 'unit': 'degC'}
		a.results.append({'id': 1, 'tool': 'map_layer', 'args': args, 'image': None, 'title': a.titled('map_layer', args),
		                  'result': {**MAP, 'unit': 'degC'}})
		return a, a.card(a.results[0]), await a.pixel(1, -3.25, 37.1)

	a, card, px = asyncio.run(fixed())
	assert card['title'] == 'Map of WORLDCLIM/V1/BIO bio01 · ' + a.region_name({'region': region})
	assert card['main'] == 'Fixed layer, without dates' and card['steps'] == [] and card['map']['series'] is False
	assert not card['rgb'] and card['legend']['unit'] == 'degC'
	facts = dict(card['facts'])
	assert facts['Data'] == 'Earth Engine image WORLDCLIM/V1/BIO, band bio01; values × 0.1 + 0; unit degC'
	assert 'Period' not in facts and 'Discarded pixels' not in facts
	assert any(r['citation'].startswith('Hijmans') for r in card['references'])  # WorldClim
	assert a.calls == [('region_stats', {'image': 'WORLDCLIM/V1/BIO', 'band': 'bio01', 'band_scale': 0.1,
	                                     'unit': 'degC', 'region': {'point': [-3.25, 37.1]}})]  # no series
	assert px == {'lon': -3.25, 'lat': 37.1, 'value': 512.5, 'unit': 'degC', 'label': 'value'}
	# the report of both
	html = open(report.write(a.results, str(tmp_path / 'report.html'), title='WorldClim'), encoding='utf-8').read()
	assert 'Earth Engine image WORLDCLIM/V1/BIO, band bio01' in html and 'Hijmans' in html
	assert 'image=&quot;WORLDCLIM/V1/BIO&quot;, band=&quot;bio01&quot;' in html  # how to reproduce it

	async def dates():  # a fixed image that the model gave dates: they change nothing (the services do not use them)
		a = Data({**assistant.DEFAULTS, 'project': 'p'})
		args = {'region': region, 'image': 'WORLDCLIM/V1/BIO', 'band': 'bio01', 'band_scale': 0.1, 'unit': 'degC',
		        'start': '2015-01-01', 'end': '2020-12-31'}
		a.results.append({'id': 1, 'tool': 'map_layer', 'args': args, 'image': None, 'title': a.titled('map_layer', args),
		                  'result': {**MAP, 'unit': 'degC'}})
		a.results.append({'id': 2, 'tool': 'region_stats', 'args': args, 'image': None, 'title': 'Statistics',
		                  'result': {'rows': [{'region': 'r', 'mean': 14.2}], 'unit': 'degC'}})
		return a, a.card(a.results[0]), await a.pixel(1, -3.25, 37.1), await a.period_map(a.results[1])

	a, card, px, shown = asyncio.run(dates())
	assert card['title'] == 'Map of WORLDCLIM/V1/BIO bio01 · ' + a.region_name({'region': region})
	assert card['main'] == 'Fixed layer, without dates' and card['steps'] == [] and card['map']['series'] is False
	assert 'key' not in px and a.calls[0] == ('region_stats', {'image': 'WORLDCLIM/V1/BIO', 'band': 'bio01',
	                                                           'band_scale': 0.1, 'unit': 'degC',
	                                                           'region': {'point': [-3.25, 37.1]}})  # no series
	assert shown['main'] == 'Fixed layer, without dates' and shown['steps'] == [] and shown['map']['series'] is False
	assert assistant.dated({'start': '2015-01-01', 'end': '2020-12-31', **TERRACLIMATE})  # a collection has dates
	assert not assistant.dated({'variable': 'ELEVATION', 'sensor': 'Copernicus', 'start': '2015-01-01',
	                            'end': '2020-12-31'})


def test_data_of_the_catalog_or_by_its_id():
	"""A call of the model with a variable of the catalog keeps none of the arguments of the data of Earth Engine by
	their ID (small models fill them all, and the MCP server refuses them mixed; the collection of a variable was
	hidden before), and one with data by their ID, no sensor."""
	tools = assistant.model_tools(DATA_TOOLS)
	mixed = {'region': {'wdpa_id': 1}, 'variable': 'PRECIP', 'sensor': 'TerraClimate', 'start': '2020-01-01',
	         'end': '2020-12-31', **TERRACLIMATE, 'image': 'X', 'terrain': 'slope'}
	assert assistant.fix_args('map_layer', mixed, tools) == {'region': {'wdpa_id': 1}, 'variable': 'PRECIP',
	                                                         'sensor': 'TerraClimate', 'start': '2020-01-01',
	                                                         'end': '2020-12-31'}
	assert assistant.fix_args('map_layer', {'region': {'wdpa_id': 1}, **TERRACLIMATE, 'sensor': 'TerraClimate'},
	                          tools) == {'region': {'wdpa_id': 1}, **TERRACLIMATE}
	assert assistant.fix_args('map_layer', {'image': 'WORLDCLIM/V1/BIO', 'band': 'bio01', 'sensor': 'WorldClim'},
	                          tools) == {'image': 'WORLDCLIM/V1/BIO', 'band': 'bio01'}
	# an ID of Earth Engine as the variable, with the collection too (small models fill every argument): the data by
	# their ID, not the catalog; without collection or image, as it is (the MCP server explains it)
	by_id = {'region': {'wdpa_id': 1}, 'variable': TERRACLIMATE['collection'], 'sensor': 'TerraClimate',
	         'start': '2020-01-01', 'end': '2020-12-31', **TERRACLIMATE}
	assert assistant.fix_args('map_layer', by_id, tools) == {'region': {'wdpa_id': 1}, 'start': '2020-01-01',
	                                                         'end': '2020-12-31', **TERRACLIMATE}
	alone = {'variable': TERRACLIMATE['collection'], 'sensor': 'TerraClimate'}
	assert assistant.fix_args('map_layer', alone, tools) == alone


def test_tools_of_the_mcp_server():
	"""The tools of the MCP server as the model gets them: those of the data of Earth Engine by their ID, with their
	arguments, but compact (see assistant._compact and _description), as the small models of Ollama have 16,384 tokens
	of context for the instructions, the tools and the conversation: their size before those data (39,337 characters)
	is the limit, with some room."""
	from monitoreo import mcp_server as mcp
	tools = assistant.model_tools([assistant._json(t) for t in asyncio.run(mcp.server.list_tools())])
	names = [t['function']['name'] for t in tools]
	assert sorted(names) == sorted(assistant.ADVICE + assistant.RESULTS + assistant.TASKS)
	text = json.dumps(tools)
	assert len(text) < 42000, len(text)
	assert '"title"' not in text and '{"type": "null"}' not in text and '"default": null' not in text
	source = ' '.join(mcp.SOURCE_DOC.split())
	assert source[:60] not in text  # said once in the instructions
	f = {t['function']['name']: t['function'] for t in tools}
	assert set(assistant.SOURCE) <= set(f['map_layer']['parameters']['properties'])
	assert f['map_layer']['parameters']['properties']['band_scale'] == {'type': 'number'}
	assert f['map_layer']['parameters']['properties']['season'] == {'type': 'array', 'items': {'type': 'string'}}
	assert 'terrain: "slope" or "aspect"' in f['map_layer']['description']  # not said in the instructions
	assert 'Required: region' in f['time_series']['description']  # what it needs, now that variable has a default
	assert f['describe_asset']['parameters']['required'] == ['asset']
	assert f['rgb_map']['parameters']['required'] == ['region', 'variable', 'sensor', 'start', 'end']
	# the dates where they are needed, whatever the data (not variable and sensor: data by ID instead)
	for name in ('time_series', 'export_time_series_to_drive', 'trend_table', 'trend_map', 'download_trend'):
		assert f[name]['parameters']['required'] == ['region', 'start', 'end'], name
	for name in ('compare_series', 'compare_map', 'download_comparison'):
		assert f[name]['parameters']['required'] == ['region', 'start', 'end', 'other_start', 'other_end'], name
	assert f['map_layer']['parameters']['required'] == ['region']  # the fixed layers have no dates
	assert 'its unit is then degree' in f['map_layer']['description']  # the slope and the aspect, in degrees
	assert 'limit' not in f['community_datasets']['parameters']['properties']
	# an argument called title is an argument
	assert assistant._compact({'title': 'X', 'properties': {'title': {'title': 'Title', 'type': 'string'}}}) == {
		'properties': {'title': {'type': 'string'}}}


def test_data_text():
	"""What the model gets of the answers of describe_asset and community_datasets (see data_text), and the labels of
	the page while they run."""
	assert assistant.data_text('describe_asset', 'not JSON') == 'not JSON'
	assert assistant.data_text('community_datasets', '[]').startswith('No dataset of the GEE Community Catalog')
	described = json.loads(assistant.data_text('describe_asset', json.dumps({'bands': [1], 'asset': 'A', 'use': 'image'})))
	assert list(described) == ['asset', 'use', 'bands']
	assert set(assistant.ADVICE) >= {'describe_asset', 'community_themes', 'community_datasets'}
	for name in assistant.ADVICE:  # every label is filled with the arguments it names
		assert '{' not in assistant.LABELS[name].format(**{k: 'x' for k in assistant.LABEL_KEYS}), name
	assert 'collection' not in assistant.HIDDEN
	text = assistant.instructions()
	assert 'describe_asset' in text and 'community_datasets' in text and 'Never make up an ID' in text
	assert 'pass no quality' in text and 'With a variable of the catalog, pass no collection' in text
	assert 'the values are in degrees (its unit is then degree: pass no unit, not that of the band)' in text
	# the datasets of a theme (all of them: some have more than 100): when they do not fit, it says so first
	many = [{'id': f'projects/sat-io/open-datasets/X{i}', 'type': 'image', 'title': f'Dataset {i}', 'theme': 'T',
	         'docs': f'https://gee-community-catalog.org/projects/x{i}/'} for i in range(145)]
	cut = assistant.data_text('community_datasets', json.dumps(many), assistant.MAX_ADVICE)
	assert len(cut) > assistant.MAX_ADVICE  # the caller cuts it
	assert cut[:assistant.MAX_ADVICE].splitlines()[0] == (
		'145 datasets of the GEE Community Catalog (ID, type, title, theme, page); only the first ones fit here: '
		'narrow the list with text or kind; describe_asset tells whether one goes as collection or image, and its bands:')
	for limit in (None, assistant.BIG_ADVICE * 10):  # what fits: no such note
		assert 'only the first ones' not in assistant.data_text('community_datasets', json.dumps(many), limit)
	assert 'only the first ones' not in assistant.data_text('community_datasets', json.dumps(many[:3]),
	                                                         assistant.MAX_ADVICE)


def test_map_view(monkeypatch):
	pytest.importorskip('PIL')
	import base64
	import io
	from PIL import Image
	seen = []

	def urlopen(req, timeout=None):
		url = req.full_url
		seen.append(url)
		colour = (200, 200, 200, 255) if 'openstreetmap' in url else (255, 0, 0, 255)
		buf = io.BytesIO()
		Image.new('RGBA', (256, 256), colour).save(buf, 'PNG')
		return io.BytesIO(buf.getvalue())

	monkeypatch.setattr(report.urllib.request, 'urlopen', urlopen)
	url = report.map_view([-3.6, 36.86, -3.5, 36.93], 13, 'https://ee/{z}/{x}/{y}', 'osm', 0.5, [-3.55, 36.9])
	img = Image.open(io.BytesIO(base64.b64decode(url.split(',')[1])))
	assert img.size == (int(round(report._pixel(-3.5, 0, 13)[0] - report._pixel(-3.6, 0, 13)[0])), img.size[1])
	r, g, b = img.getpixel((5, 5))
	assert 220 <= r <= 235 and 95 <= g <= 105  # the red of the overlay at half opacity over the grey base
	assert any('openstreetmap' in u for u in seen) and any(u.startswith('https://ee/13/') for u in seen)
	with pytest.raises(ValueError, match='too big'):
		report.map_view([-10, 35, 5, 44], 14, 'https://ee/{z}/{x}/{y}')


def test_eecu_bar_and_warning(monkeypatch):
	# after each result, the page gets the EECUs spent this month for its bar and, once, the warning of few left (with
	# the shared account: switch to your own); the answers of the tools reach the page without eecu_warning
	monkeypatch.setattr(assistant, 'signed_in', lambda: False)
	usage = {'account': 'shared', 'name': 'research EECUs', 'project': 'shared-project', 'month': '2026-11-01',
	         'used_percent': 95.0, 'left_percent': 5.0, 'low': True, 'warning': 'Less than 10% are left.'}

	class Eecu(FakeAssistant):
		async def call(self, name, args):
			if name == 'eecu_usage':
				self.eecu_args = args
				return None, [json.dumps(usage)], []
			return await super().call(name, args)

	async def run():
		a = Eecu({**assistant.DEFAULTS, 'project': '', 'ollama': 'http://127.0.0.1:1'})
		a.session, a.tools = object(), assistant.model_tools(TOOLS)
		args = {**ARGS, 'region': {'bbox': [-3.5, 37, -3, 37.2]}}
		first = [e async for e in a.run_tool({'name': 'time_series', 'arguments': args})]
		second = await a.eecu_events()
		return a, first, second

	a, first, second = asyncio.run(run())
	types = [e['type'] for e in first]
	assert types.index('result') + 1 == types.index('eecu') == types.index('eecu_warning') - 1
	assert first[types.index('eecu')]['usage'] == usage and a.eecu == usage
	assert a.eecu_args == {'lang': 'en', 'refresh': False}
	warning = first[types.index('eecu_warning')]['text']
	assert warning.startswith('Less than 10% are left.') and 'Use my Google account' in warning
	assert [e['type'] for e in second] == ['eecu']  # the warning, once
	assert assistant._without_eecu_warning(json.dumps({'a': 1, 'eecu_warning': 'x'})) == '{\n "a": 1\n}'


def test_sign_out(monkeypatch, tmp_path):
	# «Log out»: the refresh token is revoked at Google and the credentials of `earthengine authenticate` deleted
	import ee
	import requests
	path = tmp_path / 'credentials'
	path.write_text(json.dumps({'refresh_token': 'refresh-123', 'scopes': []}))
	monkeypatch.setattr(ee.oauth, 'get_credentials_path', lambda: str(path))
	posted = []
	monkeypatch.setattr(requests, 'post', lambda url, data=None, timeout=None: posted.append((url, data)))
	assert assistant.signed_in() and assistant.sign_out()
	assert not path.exists() and not assistant.signed_in()
	assert posted == [(assistant.REVOKE, {'token': 'refresh-123'})]
	assert assistant.sign_out() is False and len(posted) == 1  # nothing to sign out

	path.write_text('{"refresh_token": "r"}')  # without a connection to Google, the credentials are deleted anyway

	def offline(*a, **k):
		raise requests.ConnectionError('offline')
	monkeypatch.setattr(requests, 'post', offline)
	assert assistant.sign_out() and not path.exists()


CLOUD_USER = 'mo-' + 'c' * 16


def test_settings_of_the_model(monkeypatch, tmp_path):
	# the model of MonitorEO by default; the settings saved before it existed keep their model of Ollama
	monkeypatch.setattr(assistant, 'SETTINGS', str(tmp_path / 'assistant.json'))
	assert assistant.load_settings()['provider'] == 'monitoreo'
	(tmp_path / 'assistant.json').write_text(json.dumps({'model': 'qwen3:4b'}))
	assert assistant.load_settings()['provider'] == 'ollama'
	(tmp_path / 'assistant.json').write_text(json.dumps({'model': 'qwen3:4b', 'provider': 'monitoreo'}))
	s = assistant.load_settings()
	assert s['provider'] == 'monitoreo' and s['model'] == 'qwen3:4b'


def test_model_title():
	assert assistant.model_title('gemini-3.8-flash') == 'Gemini 3.8 Flash'
	assert assistant.model_title('claude-sonnet-5-5') == 'Claude Sonnet 5.5'
	assert assistant.model_title('claude-haiku-5-5') == 'Claude Haiku 5.5'
	assert assistant.model_title(None) == assistant.CLOUD == 'MonitorEO'
	a = FakeAssistant({**assistant.DEFAULTS, 'provider': 'monitoreo'})
	assert a.model_name() == 'MonitorEO'
	a.cloud_model = 'claude-opus-5-5'
	assert a.model_name() == 'Claude Opus 5.5'
	a.settings['provider'] = 'ollama'
	assert a.model_name() == 'qwen3:8b'


def test_openai_messages():
	# the conversation as the API of OpenAI takes it (the broker passes it to Gemini or Claude), also with calls of a model
	# of Ollama (without ids) and a call without answer; the fields that the model gave go back as they came
	call = {'id': 'g1', 'type': 'function', 'function': {'name': 'time_series', 'arguments': {'variable': 'NDVI'}},
	        'extra_content': {'google': {'thought_signature': 'sig'}}}
	messages = [
		{'role': 'user', 'content': 'NDVI de Sierra Nevada'},
		{'role': 'assistant', 'content': '', 'tool_calls': [
			{'function': {'name': 'find_protected_areas', 'arguments': {'text': 'Sierra Nevada'}}}]},
		{'role': 'tool', 'tool_name': 'find_protected_areas', 'content': 'SITE_ID 389011'},
		{'role': 'assistant', 'content': '', 'tool_calls': [call]},
		{'role': 'tool', 'tool_name': 'time_series', 'content': 'Done', 'tool_call_id': 'g1'},
		{'role': 'assistant', 'content': 'Hecho.', 'extra_content': {'google': {'x': 1}}},
		{'role': 'user', 'content': 'Y el EVI'},
		{'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 'list_variables', 'arguments': {}}}]},
		{'role': 'user', 'content': 'Para'},
		{'role': 'tool', 'tool_name': 'manual', 'content': 'late'},
	]
	out = assistant.openai_messages('System', messages)
	assert out[0] == {'role': 'system', 'content': 'System'} and out[1] == messages[0]
	assert out[2]['tool_calls'] == [{'id': 'call_1', 'type': 'function', 'function': {
		'name': 'find_protected_areas', 'arguments': '{"text": "Sierra Nevada"}'}}]
	assert out[3] == {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'SITE_ID 389011'}
	assert out[4]['tool_calls'] == [{**call, 'function': {'name': 'time_series', 'arguments': '{"variable": "NDVI"}'}}]
	assert out[5] == {'role': 'tool', 'tool_call_id': 'g1', 'content': 'Done'}
	assert out[6] == messages[5] and out[7] == messages[6]
	assert out[8]['tool_calls'][0]['id'] == 'call_3'
	assert out[9] == {'role': 'tool', 'tool_call_id': 'call_3', 'content': 'No answer.'}  # before the next message
	assert out[10] == messages[8]
	assert out[11]['role'] == 'user' and out[11]['content'].endswith('the tool manual answered: late)')
	assert len(out) == 12 and messages[1]['tool_calls'][0]['function']['arguments'] == {'text': 'Sierra Nevada'}


def test_chat_cloud(monkeypatch):
	# the model of MonitorEO through the broker: the request with the anonymous ID of this installation and the tools as
	# they are (the broker adapts them to each model), and its answer as chat_ollama gives it, with the calls and their
	# fields as they came and the model that answered
	from monitoreo import services
	monkeypatch.setattr(services, '_user', CLOUD_USER)
	asked = []

	def broker(path, body=None, timeout=30, **params):
		asked.append((path, body, params))
		return {'model': 'claude-sonnet-5-5',
		        'choices': [{'message': {'role': 'assistant', 'content': None, 'extra_content': {'anthropic': {'a': 1}},
		                                 'tool_calls': [{'id': 'g1', 'type': 'function', 'extra_content': {'s': 2},
		                                                 'function': {'name': 'time_series',
		                                                              'arguments': '{"variable": "NDVI"}'}}]}}]}
	monkeypatch.setattr(services, '_broker', broker)
	tools = assistant.model_tools(TOOLS)
	message = assistant.chat_model({'provider': 'monitoreo', 'model': 'qwen3:8b'}, 'System',
	                               [{'role': 'user', 'content': 'NDVI'}], tools)
	assert message == {'role': 'assistant', 'content': '', 'extra_content': {'anthropic': {'a': 1}},
	                   'model': 'claude-sonnet-5-5',
	                   'tool_calls': [{'id': 'g1', 'type': 'function', 'extra_content': {'s': 2},
	                                   'function': {'name': 'time_series', 'arguments': {'variable': 'NDVI'}}}]}
	path, body, params = asked[0]
	assert path == '/chat' and params == {'user': CLOUD_USER}
	assert body['messages'] == [{'role': 'system', 'content': 'System'}, {'role': 'user', 'content': 'NDVI'}]
	assert body['tools'] == tools and 'model' not in body  # the broker chooses it
	assistant.chat_model({'provider': 'monitoreo', 'cloud_model': 'claude-haiku-5-5'}, 'System', [], tools)
	assert asked[1][1]['model'] == 'claude-haiku-5-5'  # unless the settings ask for one (to compare them)

	def busy(path, body=None, timeout=30, **params):
		raise services.BrokerError('the language model of MonitorEO is busy: try again in a minute', 'busy')
	monkeypatch.setattr(services, '_broker', busy)
	with pytest.raises(assistant.ModelError, match='busy: try again in a minute .in Settings you can use a model on'):
		assistant.chat_cloud('System', [], tools)


def test_the_assistant_with_the_model_of_monitoreo(monkeypatch):
	# a conversation with the model of MonitorEO: the answer of each tool goes with the id of its call, the model still
	# gets only a receipt of the results, and Ollama is not needed
	from monitoreo import services
	monkeypatch.setattr(services, '_user', CLOUD_USER)
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)
	answers = iter([
		{'tool_calls': [{'id': 'g1', 'type': 'function', 'extra_content': {'google': {'thought_signature': 's1'}},
		                 'function': {'name': 'find_protected_areas', 'arguments': '{"text": "Sierra"}'}}]},
		{'tool_calls': [{'id': 'g2', 'type': 'function',
		                 'function': {'name': 'time_series', 'arguments': json.dumps(ARGS)}}]},
		{'content': 'La serie está en el resultado 1.'},
	])
	bodies = []

	def broker(path, body=None, timeout=30, **params):
		bodies.append(body)
		return {'choices': [{'message': {'role': 'assistant', 'content': None, **next(answers)}}]}
	monkeypatch.setattr(services, '_broker', broker)

	async def run():
		a = FakeAssistant({**assistant.DEFAULTS, 'project': 'p', 'provider': 'monitoreo', 'ollama': 'http://127.0.0.1:1'})
		a.engine.url = None  # no Ollama
		a.tools = assistant.model_tools(TOOLS)
		return a, [e async for e in a.chat('NDVI de Sierra Nevada en 2021')]

	a, events = asyncio.run(run())
	assert [e['type'] for e in events if e['type'] != 'status'] == ['areas', 'running', 'result', 'map', 'assistant']
	assert events[0]['text'] == 'The model (MonitorEO) is thinking…'
	second, third = bodies[1]['messages'], bodies[2]['messages']
	assert second[2]['tool_calls'][0]['extra_content'] == {'google': {'thought_signature': 's1'}}
	assert second[3]['role'] == 'tool' and second[3]['tool_call_id'] == 'g1' and 'Sierra Nevada' in second[3]['content']
	assert third[5]['tool_call_id'] == 'g2' and third[5]['content'].startswith('Done:')
	assert '0.501' not in json.dumps(third) and '0,501' not in json.dumps(third)
	assert [m.get('tool_call_id') for m in a.messages if m['role'] == 'tool'] == ['g1', 'g2'] and a.call_id is None


def test_manual_with_the_articles_of_the_team(tmp_path):
	"""The real pages Publicaciones and Publications of the wiki (with a page of concepts): an example question finds
	an article of the team; a question about a concept still finds the concept."""
	from monitoreo import manual
	wiki = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'monitoreo.wiki')
	if not os.path.exists(os.path.join(wiki, 'Publicaciones.md')):
		pytest.skip('no clone of the wiki with the page Publicaciones next to this repository')
	for name in ('Publicaciones', 'Publications'):
		with open(os.path.join(wiki, name + '.md'), encoding='utf-8') as f:
			(tmp_path / f'{name}.md').write_text(f.read(), encoding='utf-8')
	for name, text in WIKI_PAGES.items():
		(tmp_path / f'{name}.md').write_text(text, encoding='utf-8')
	(tmp_path / '_Sidebar.md').write_text('[Inicio](Home) [Publicaciones](Publicaciones)', encoding='utf-8')
	assert 'Publicaciones' in manual.PAGES and manual.ENGLISH['Publicaciones'] == 'Publications'
	found = manual.search('¿Algún artículo de ejemplo sobre tipos funcionales de ecosistemas con el EVI?',
	                      folder=str(tmp_path))[0]
	assert found['name'] == 'Publicaciones' and 'doi.org' in found['text'], found
	found = manual.search('An example article on ecosystem functional types with EVI?', folder=str(tmp_path))[0]
	assert found['name'] == 'Publications' and found['lang'] == 'en'
	assert manual.search('¿Qué es el NDVI?', folder=str(tmp_path))[0]['title'] == 'Variables'


def test_the_page_has_the_feedback_button():
	"""The page of the assistant has the button "Suggest a change or report an error", like the QGIS plugin and the
	Earth Engine app, with the links of about.feedback filled with the assistant and its version: it had none."""
	import urllib.parse
	from monitoreo import __version__, about
	fb = assistant.feedback()
	assert {k: fb[k] for k in ('button', 'issue', 'form')} == about.FEEDBACK['en']
	issue = urllib.parse.parse_qs(urllib.parse.urlparse(fb['links']['issue']).query)
	assert fb['links']['issue'].startswith(about.ISSUES) and issue == {'tool': ['Assistant'], 'version': [__version__]}
	form = urllib.parse.parse_qs(urllib.parse.urlparse(fb['links']['form']).query)
	assert fb['links']['form'].startswith(about.FORM)
	assert form[about.FORM_FIELDS['tool']] == [about.TOOLS['assistant'][1]]
	assert form[about.FORM_FIELDS['version']] == [__version__]
	with open(os.path.join(os.path.dirname(assistant.__file__), 'ui', 'assistant.html'), encoding='utf-8') as f:
		page = f.read()
	assert all(f'id="{i}"' in page for i in ('feedbackButton', 'feedback', 'feedbackIssue', 'feedbackForm'))
	assert 'fb.links[key]' in page  # the links come from /api/state


# The button Stop, and the maps without their preview (the map of the cloud frequency of MODIS of 2001-2025 over La
# Palma failed with «HTTPError: HTTP Error 400: Bad Request», and nothing could be asked until it ended) -------------

MAP_TOOL = {'name': 'map_layer', 'description': 'Map.', 'inputSchema': {'type': 'object', 'properties': {
	**{k: {'type': 'string'} for k in ('variable', 'sensor', 'start', 'end', 'metric')}, 'region': {'type': 'object'}}}}
CF = {'region': {'island_at': [-17.86, 28.68]}, 'variable': 'CF', 'sensor': 'MODIS', 'start': '2001-01-01',
      'end': '2025-12-31', 'metric': 'mean'}


class Blocked:
	"""A session of the MCP server whose tools do not end (as a map that takes Earth Engine many minutes)."""

	def __init__(self):
		self.started = asyncio.Event()

	async def call_tool(self, name, args):
		self.started.set()
		await asyncio.Event().wait()


async def _until_done(a, since=0):
	got = []
	async for e in a.follow(since, ping=0.05):
		got.append(e)
		if e['type'] == 'done':
			return got


def test_stop_a_computation(monkeypatch):
	"""Stop while a tool computes: the answer ends at once, the MCP server starts again (what Earth Engine computed
	for it stops), the model gets that the call was not done, and the user asks for something else at once."""
	answers = iter([{'content': '', 'tool_calls': [{'id': 'c1', 'function': {'name': 'map_layer', 'arguments': CF}}]},
	                {'content': 'The NDVI, then.'}])
	seen = []

	def model(settings, system, messages, tools):
		seen.append(json.loads(json.dumps(messages)))
		return next(answers)

	monkeypatch.setattr(assistant, 'chat_model', model)

	async def run():
		a = assistant.Assistant({**assistant.DEFAULTS, 'project': ''})
		a.tools = assistant.model_tools(TOOLS + [MAP_TOOL])
		a.session = Blocked()
		restarts = []

		async def restart():
			restarts.append(a.calling)
			a.session = Blocked()

		a.restart_server = restart
		assert await a.stop() is False  # nothing to stop
		a.start('Cloud frequency of MODIS of 2001-2025 in La Palma')
		await asyncio.wait_for(a.session.started.wait(), 5)
		assert a.running() and a.calling == 1
		assert await a.stop() is True
		assert not a.running() and restarts == [0]
		first = await _until_done(a)
		a.start('Stop it: the NDVI instead')  # at once
		second = await _until_done(a, first[-1]['seq'] + 1)
		return a, first, second

	a, first, second = asyncio.run(run())
	assert [e['type'] for e in first if e['type'] != 'status'] == ['user', 'running', 'stopped', 'done']
	assert next(e for e in first if e['type'] == 'stopped')['text'].startswith('Stopped.')
	assert [e['type'] for e in second if e['type'] != 'status'] == ['user', 'assistant', 'done']
	stopped = next(m for m in seen[1] if m['role'] == 'tool')
	assert stopped == {'role': 'tool', 'tool_name': 'map_layer', 'content': assistant.STOPPED, 'tool_call_id': 'c1'}
	assert seen[1][-1]['content'] == 'Stop it: the NDVI instead' + assistant.NOTE + assistant.INTERRUPTED
	assert a.said() == ['Cloud frequency of MODIS of 2001-2025 in La Palma', 'Stop it: the NDVI instead']
	assert not a.interrupted and not a.results
	# the model of the cloud gets an answer for each call (openai_messages)
	sent = assistant.openai_messages('s', seen[1])
	assert any(m['role'] == 'tool' and m['tool_call_id'] and m['content'] == assistant.STOPPED for m in sent)


def test_stop_while_the_model_thinks(monkeypatch):
	"""Stop before the model answers: nothing computes, so the MCP server goes on as it is; the late answer of the
	model is not kept."""
	entered, release = threading.Event(), threading.Event()
	seen = []

	def model(settings, system, messages, tools):
		seen.append(json.loads(json.dumps(messages)))
		if len(seen) == 1:
			entered.set()
			release.wait(10)
			return {'content': 'Too late.'}
		return {'content': 'Answered.'}

	monkeypatch.setattr(assistant, 'chat_model', model)

	async def run():
		a = FakeAssistant({**assistant.DEFAULTS, 'project': ''})
		a.tools = assistant.model_tools(TOOLS)
		restarts = []

		async def restart():
			restarts.append(True)

		a.restart_server = restart
		a.start('Map of the cloud frequency')
		await asyncio.to_thread(entered.wait, 5)
		assert await a.stop() is True
		release.set()
		first = await _until_done(a)
		a.start('Another thing')
		second = await _until_done(a, first[-1]['seq'] + 1)
		return a, first, second, restarts

	try:
		a, first, second, restarts = asyncio.run(run())
	finally:
		release.set()
	assert restarts == []
	assert [e['type'] for e in first if e['type'] != 'status'] == ['user', 'stopped', 'done']
	assert [m['role'] for m in seen[1]] == ['user', 'user']  # 'Too late.' is not in the conversation
	assert seen[1][1]['content'].endswith(assistant.INTERRUPTED)
	assert [e['text'] for e in second if e['type'] == 'assistant'] == ['Answered.']


def test_a_map_without_its_preview(monkeypatch):
	"""A map whose preview Earth Engine could not make is a result with its map in the panel, and a notice."""

	class NoPreview(FakeAssistant):
		async def call(self, name, args):
			return None, [json.dumps({**MAP, 'thumbnail': None, 'thumbnail_error':
			                          'EEException: Earth Engine could not make the PNG preview: Computation timed out.'})], []

	a = NoPreview({**assistant.DEFAULTS, 'project': ''})
	a.tools = assistant.model_tools(TOOLS + [MAP_TOOL])
	a.messages.append({'role': 'user', 'content': 'Cloud frequency of MODIS of 2001-2025 in La Palma'})

	async def run():
		return [e async for e in a.run_tool({'name': 'map_layer', 'arguments': CF})]

	events = asyncio.run(run())
	assert [e['type'] for e in events if e['type'] != 'status'] == ['running', 'result', 'notice']
	result = next(e for e in events if e['type'] == 'result')
	assert result['image'] is None and result['map']['url'] == MAP['url']  # the map, by its tiles
	notice = next(e for e in events if e['type'] == 'notice')['text']
	assert notice.startswith('The result 1 has no preview image (Earth Engine could not make the PNG preview: '
	                         'Computation timed out.)') and 'EEException' not in notice
	assert a.messages[-1]['content'].startswith('Done')  # the model gets its receipt: nothing to ask for again


def test_the_mcp_server_starts_again():
	"""The MCP server of MonitorEO starts again (after a stop) with its tools, without computing in Earth Engine."""
	pytest.importorskip('mcp')

	async def run():
		a = assistant.Assistant({**assistant.DEFAULTS, 'project': ''})
		async with a.connected():
			first = a.session
			assert first is not None and a.server_ready.is_set()
			assert 'map_layer' in [t['function']['name'] for t in a.tools]
			restart = asyncio.create_task(a.restart_server())
			await asyncio.sleep(0)  # the old server is stopping: a call now waits for the new one
			assert a.restarting is not None
			error, texts, _ = await a.call('list_variables', {'text': 'cloud frequency', 'lang': 'en'})
			await restart
			assert a.session is not None and a.session is not first and a.server_ready.is_set() and not a.restarting
			assert error is None and 'CF' in texts[0]
		assert a.session is None and not a.server_ready.is_set() and a.server_task is None

	asyncio.run(asyncio.wait_for(run(), 120))


def test_the_page_stops():
	"""The page has the button Stop (Send while an answer runs) and the route of the API behind it."""
	page = open(os.path.join(os.path.dirname(assistant.__file__), 'ui', 'assistant.html'), encoding='utf-8').read()
	assert "b.textContent = on ? 'Stop' : 'Send'" in page and "api('/api/stop', {})" in page
	assert "e.type === 'stopped'" in page
	app = assistant.make_app(assistant.Assistant({**assistant.DEFAULTS, 'project': ''}), 'token', 8765)
	assert '/api/stop' in [r.path for r in app.routes]
