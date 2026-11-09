"""The themes of the menus (catalog.THEMES) and the links to suggest a change or report an error (about.feedback),
without Earth Engine."""

import json
import os
import urllib.parse

import pytest

from monitoreo import about, catalog, services

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_variable_has_one_theme():
	for e in catalog.variables():
		themes = [t['key'] for t in catalog.THEMES if e['index'] in t['indices']]
		assert len(themes) == 1, (e['index'], themes)
		assert e['theme'] == themes[0]
	assert all(t['en'] and t['es'] for t in catalog.THEMES)
	assert len({t['key'] for t in catalog.THEMES}) == len(catalog.THEMES)
	indices = {e['index'] for e in catalog.variables()}
	for t in catalog.THEMES:  # no theme lists a variable the catalog does not have
		assert set(t['indices']) <= indices, (t['key'], set(t['indices']) - indices)


def test_the_analyses_of_a_theme_are_tools():
	from monitoreo import mcp_server
	for t in catalog.THEMES:
		for name in t.get('analyses') or []:
			assert hasattr(services, name) and hasattr(mcp_server, name), name
	assert catalog.theme_of('NBR')['analyses'] == ['burn_severity']


def test_list_variables_by_theme():
	fire = services.list_variables(theme='fire')
	assert {v['variable'] for v in fire} == {'NBR', 'RBR'} and fire[0]['theme'] == 'Fire'
	assert services.list_variables(theme='Nieve', lang='es')[0]['theme'] == 'Nieve'
	assert {v['variable'] for v in services.list_variables(theme='terrain')} == {'ELEVATION', 'SLOPE'}
	with pytest.raises(ValueError, match='unknown theme'):
		services.list_variables(theme='mountains')
	assert services.describe_variable('LST', 'Modis')['theme'] == 'Energy and temperature'
	assert [t['key'] for t in services.themes()][:2] == ['vegetation', 'water']


def test_the_app_has_the_themes():
	with open(os.path.join(ROOT, 'gee', 'catalog.js'), encoding='utf-8') as f:
		text = f.read()
	data = json.loads(text[text.index('{'):text.rstrip().rindex('}') + 1])
	assert [t['key'] for t in data['themes']] == [t['key'] for t in catalog.THEMES]
	assert all(v['theme'] for v in data['variables'])
	links = data['about']['feedback']['links']
	assert 'tool=Earth+Engine+app' in links['issue'] and about.FORM in links['form']


def test_feedback_links():
	links = about.feedback('qgis', '0.3.15')
	issue = urllib.parse.urlparse(links['issue'])
	assert links['issue'].startswith(about.REPOSITORY + '/issues/new/choose?')
	assert urllib.parse.parse_qs(issue.query) == {'tool': ['QGIS plugin'], 'version': ['0.3.15']}
	form = urllib.parse.parse_qs(urllib.parse.urlparse(links['form']).query)
	assert form[about.FORM_FIELDS['tool']] == ['Complemento de QGIS / QGIS plugin']
	assert form[about.FORM_FIELDS['version']] == ['0.3.15'] and form['usp'] == ['pp_url']
	assert set(about.FEEDBACK['en']) == set(about.FEEDBACK['es']) == {'button', 'issue', 'form'}
	for name in ('error.yml', 'suggestion.yml', 'config.yml'):  # the templates the links open
		assert os.path.exists(os.path.join(ROOT, '.github', 'ISSUE_TEMPLATE', name))
	with open(os.path.join(ROOT, '.github', 'ISSUE_TEMPLATE', 'error.yml'), encoding='utf-8') as f:
		template = f.read()
	assert 'id: tool' in template and 'id: version' in template and about.FORM in template
