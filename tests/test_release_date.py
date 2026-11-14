"""The version of each tool with the date of its release next to it (__released__ of the package, that of its heading
in the changelog: tests/test_changelog.py): the assistant, the Earth Engine app, the QGIS plugin and the command line,
without Earth Engine."""

import asyncio
import json
import os
import re

import pytest

import monitoreo
from monitoreo import __released__, __version__, assistant, cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*path):
	with open(os.path.join(ROOT, *path), encoding='utf-8') as f:
		return f.read()


def test_the_assistant_shows_it(monkeypatch):
	monkeypatch.setattr(assistant, 'signed_in', lambda: False)
	monkeypatch.setattr(assistant, 'models', lambda settings: [])
	a = assistant.Assistant({**assistant.DEFAULTS, 'project': ''})
	app = assistant.make_app(a, 'token', 8765)
	route = next(r for r in app.routes if getattr(r, 'path', None) == '/api/state')

	class Request:  # what the guard of the route reads: the host and the token of the page
		headers = {'x-token': 'token', 'host': '127.0.0.1:8765'}
		query_params = {}

	response = asyncio.run(route.endpoint(Request()))
	state = json.loads(response.body)
	assert state['version'] == __version__ and state['released'] == __released__


def test_the_page_of_the_assistant_shows_it():
	page = read('src', 'monitoreo', 'ui', 'assistant.html')
	assert "'MonitorEO ' + state.version + (state.released ? ' · released ' + state.released : '')" in page
	assert "'released': __released__" in read('src', 'monitoreo', 'assistant.py')


def test_the_command_line_shows_it(capsys):
	with pytest.raises(SystemExit):
		cli.main(['--version'])
	assert capsys.readouterr().out.strip() == f'{__version__} (released {__released__})'


def _catalog_js():
	text = read('gee', 'catalog.js')
	return json.loads(text[text.index('{'):text.rstrip().rindex('}') + 1])


def test_the_earth_engine_app_shows_it():
	about = _catalog_js()['about']
	assert (about['version'], about['released']) == (__version__, __released__)  # gee/build.py, at each release
	ui = read('gee', 'ui.js')
	assert "version: 'MonitorEO %s · released %s'" in ui and "version: 'MonitorEO %s · publicada el %s'" in ui
	assert "fmt(t('version'), mo.CATALOG.about.version, mo.CATALOG.about.released)" in ui
	app = read('gee', 'monitoreo_app.js')  # the script pasted in the Code Editor: catalog.js, core.js and ui.js
	assert f'"released": "{__released__}"' in app and "fmt(t('version'), mo.CATALOG.about.version" in app


def test_the_qgis_plugin_shows_it():
	"""The label itself is checked in QGIS by qgis/test_rgb_offline.py; here, that the plugin builds it."""
	dock = read('qgis', 'monitoreo_qgis', 'dock.py')
	assert 'row.addWidget(self.version_label())' in dock
	assert "f'MonitorEO {plugin_version()}' + (f' · released {released}' if released else '')" in dock


def test_the_date_is_a_date():
	assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', monitoreo.__released__)
