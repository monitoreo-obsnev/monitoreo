"""The links of the results to the sections of the wiki that explain their variables (monitoreo.wiki), as the developer
asked: «when a user asks for a variable, next to the results there should be a link to the section of the wiki that
explains that variable (or those variables)»."""

import json
import os
import shutil
import subprocess

import pytest

from monitoreo import catalog, readme, wiki

WIKI = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'monitoreo.wiki')


def test_every_variable_of_the_catalog_has_its_section():
	names = {e['index'] for e in catalog.variables()}
	missing = sorted(n for n in names if not wiki.variable_section(n))
	assert not missing, f'variables without a section of the wiki: {missing}'
	ndvi = wiki.variable_section('NDVI')
	assert ndvi == {'variable': 'NDVI', 'title': 'NDVI: Normalized Difference Vegetation Index',
	                'url': 'https://github.com/monitoreo-obsnev/monitoreo/wiki/Concepts#'
	                       'ndvi-normalized-difference-vegetation-index',
	                'url_es': 'https://github.com/monitoreo-obsnev/monitoreo/wiki/Conceptos#'
	                          'ndvi-índice-de-vegetación-de-diferencia-normalizada'}
	assert wiki.variable_section('PRECIP')['title'].startswith('Climate') and wiki.variable_section('UNKNOWN') is None


@pytest.mark.skipif(not os.path.isdir(WIKI), reason='the clone of the wiki is not next to the repository')
def test_the_headings_are_those_of_the_wiki():
	for page, i in (('Conceptos', 0), ('Concepts', 1)):
		with open(os.path.join(WIKI, page + '.md'), encoding='utf-8') as f:
			anchors = {wiki.anchor(line.lstrip('#')) for line in f if line.startswith('#')}
		missing = sorted(h[i] for h in wiki.HEADINGS.values() if wiki.anchor(h[i]) not in anchors)
		assert not missing, f'headings not in {page}: {missing}'


def test_the_variables_of_a_call():
	links = wiki.variable_links({'variable': 'NDVI', 'other_variable': 'NDSI', 'zones': {'variable': 'ELEVATION'},
	                             'where': [{'variable': 'SLOPE', 'max': 20}, {'landcover': 'CORINE', 'year': 2018}]})
	# each section once: ELEVATION and SLOPE share theirs; the land cover mask is not a variable
	assert [link['variable'] for link in links] == ['NDVI', 'NDSI', 'ELEVATION']
	assert [link['variable'] for link in wiki.variable_links({'collection': 'IDAHO_EPSCOR/TERRACLIMATE'})] == \
	       ['Earth Engine data by its ID']
	assert wiki.variable_links({'index': 'RdNBR'})[0]['title'].startswith('RdNBR')
	assert wiki.variable_links({'region': {'bbox': [0, 0, 1, 1]}}) == []
	recipe = {'variables': [{'index': 'NDVI'}, {'index': 'LST'}, {'collection': 'X', 'band': 'b'}]}
	assert [link['variable'] for link in wiki.variable_links({'recipe': recipe})] == \
	       ['NDVI', 'LST', 'Earth Engine data by its ID']


def test_the_readme_has_the_links():
	args = {'region': {'bbox': [-3.45, 37.02, -3.3, 37.12]}, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
	        'start': '2021-01-01', 'end': '2021-12-31', 'step': 'monthly'}
	text = ' '.join(readme.text('time_series', args, {'title': 'NDVI', 'unit': '[unitless]'}).split())
	assert f"What NDVI is: NDVI: Normalized Difference Vegetation Index, {wiki.variable_section('NDVI')['url']}" in text
	assert '(en español: https://github.com/monitoreo-obsnev/monitoreo/wiki/Conceptos#ndvi-' in text


def test_the_assistant_and_the_report_show_the_links(tmp_path):
	"""The card of a result in the assistant has the sections of the wiki of its variables, in the language of the
	user; the report has them under each result."""
	from monitoreo import assistant, report
	a = assistant.Assistant.__new__(assistant.Assistant)
	args = {'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2021-01-01',
	        'end': '2021-12-31', 'step': 'monthly'}
	item = {'id': 1, 'tool': 'time_series', 'args': args, 'title': 'NDVI', 'image': None,
	        'result': {'title': 'NDVI', 'unit': '[unitless]', 'rows': [], 'manual': wiki.variable_links(args)}}
	assert a.manual_links(item) == [{'variable': 'NDVI', 'title': 'NDVI: Normalized Difference Vegetation Index',
	                                 'url': wiki.variable_section('NDVI')['url']}]
	a.said = lambda: ['¿cómo ha cambiado el NDVI del parque en los últimos años?']
	assert a.manual_links(item)[0]['url'] == wiki.variable_section('NDVI')['url_es']
	item_without = dict(item, result={'title': 'NDVI'})  # a result of before the links: from its arguments
	assert a.manual_links(item_without)[0]['variable'] == 'NDVI'
	page = open(report.write([item], path=str(tmp_path / 'report.html')), encoding='utf-8').read()
	assert f'<a href="{wiki.variable_section("NDVI")["url"]}">NDVI: Normalized Difference Vegetation Index</a>' in page
	html = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src', 'monitoreo', 'ui',
	                         'assistant.html'), encoding='utf-8').read()
	assert 'function manualLinks(links)' in html and 'e.manual && e.manual.length' in html


APP = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var names = JSON.parse(fs.readFileSync(0, 'utf8'));
function nothing() { return new Proxy(function () {}, {get: function () { return nothing(); }, apply: nothing}); }
global.ee = nothing();
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[process.argv.length - 1], f), 'utf8'), {filename: f});
});
var mo = MonitorEO;
process.stdout.write(JSON.stringify(names.map(function (n) { return [mo.wikiSection(n, 'en'), mo.wikiSection(n, 'es')]; })));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_earth_engine_app_has_the_same_sections():
	"""The app (gee/core.js, with catalog.js) has the sections of the wiki of the package (wiki.HEADINGS, SAME_SECTION)
	and makes the same anchors and links, in Spanish and in English; its results show them (manualLinks, gee/ui.js)."""
	gee = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gee')
	names = sorted({e['index'] for e in catalog.variables()}) + [None, 'dNBR', 'RdNBR']
	run = subprocess.run(['node', '-e', APP, gee], input=json.dumps(names), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	for name, (en, es) in zip(names, json.loads(run.stdout)):
		py = wiki.variable_section(name)
		assert en == {'variable': py['variable'], 'title': py['title'], 'url': py['url']}, name
		assert es['url'] == py['url_es'], name
	ui = open(os.path.join(gee, 'ui.js'), encoding='utf-8').read()
	assert 'function manualLinks()' in ui and "manualOf: 'What it is (manual):'" in ui and \
	       "manualOf: 'Qué es (manual):'" in ui
