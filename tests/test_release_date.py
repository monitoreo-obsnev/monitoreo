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


def _build():
	import importlib.util
	spec = importlib.util.spec_from_file_location('build', os.path.join(ROOT, 'gee', 'build.py'))
	build = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(build)
	return build


def test_the_earth_engine_app_shows_it():
	about = _catalog_js()['about']
	assert (about['version'], about['released']) == (__version__, __released__)  # gee/build.py --about-only
	# its whole about is that of the package: the links of suggestions with the same version as the label
	assert {k: v for k, v in about.items() if k != 'logos'} == _build().about_texts(logos=False)
	ui = read('gee', 'ui.js')
	assert "version: 'MonitorEO %s · released %s'" in ui and "version: 'MonitorEO %s · publicada el %s'" in ui
	assert "fmt(t('version'), mo.CATALOG.about.version, mo.CATALOG.about.released)" in ui
	app = read('gee', 'monitoreo_app.js')  # the script pasted in the Code Editor: catalog.js, core.js and ui.js
	assert f'"released": "{__released__}"' in app and "fmt(t('version'), mo.CATALOG.about.version" in app


def test_the_qgis_plugin_shows_it():
	"""The label itself is checked in QGIS by qgis/test_rgb_offline.py; here, that the plugin builds it, with the date
	of the package it carries (ext/), released with it."""
	dock = read('qgis', 'monitoreo_qgis', 'dock.py')
	assert 'row.addWidget(self.version_label())' in dock
	assert "f'MonitorEO {plugin_version()}' + (f' · released {released}' if released else '')" in dock
	assert "'ext', 'monitoreo', '__init__.py'" in dock and 'released = plugin_released()' in dock


def test_the_release_refreshes_the_app_without_earth_engine(tmp_path, monkeypatch):
	"""gee/build.py --about-only (a step of each release) writes the about of catalog.js and monitoreo_app.js without
	Earth Engine: here, on a copy, with an older version."""
	import shutil
	import sys
	build = _build()
	for name in ('catalog.js', 'core.js', 'ui.js'):
		shutil.copy(os.path.join(ROOT, 'gee', name), tmp_path / name)
	monkeypatch.setattr(build, 'HERE', str(tmp_path))
	monkeypatch.setattr(build, '__version__', '0.3.42')
	monkeypatch.setattr(build, '__released__', '2026-11-20')
	monkeypatch.setattr(build.services, 'init', lambda *a, **k: pytest.fail('Earth Engine'))
	monkeypatch.setattr(sys, 'argv', ['build.py', '--about-only'])
	build.main()
	text = (tmp_path / 'catalog.js').read_text(encoding='utf-8')
	about = json.loads(text[text.index('{'):text.rstrip().rindex('}') + 1])['about']
	assert (about['version'], about['released']) == ('0.3.42', '2026-11-20')
	assert 'version=0.3.42' in about['feedback']['links']['issue']
	assert about['logos'] == _catalog_js()['about']['logos']  # as they were
	assert '"released": "2026-11-20"' in (tmp_path / 'monitoreo_app.js').read_text(encoding='ascii')


def test_the_date_is_a_date():
	assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', monitoreo.__released__)
