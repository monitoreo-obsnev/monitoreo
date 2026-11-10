"""The changelog of README.md (.github/changelog.py): its format, the versions of the last release, the notes of the
GitHub releases and the changelog of the QGIS plugin, without Earth Engine."""

import configparser
import importlib.util
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
	spec = importlib.util.spec_from_file_location('changelog', os.path.join(ROOT, '.github', 'changelog.py'))
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


changelog = load()
README = changelog.readme()
URL = changelog.REPO + '/releases/tag/'


def test_the_changelog_of_the_readme_is_right():
	# a release raises the versions of metadata.txt and pyproject.toml, and renames "### Unreleased" to its heading
	assert changelog.problems(README) == []
	log = changelog.parse(README)
	assert log['releases'][-1]['tag'] == '0.1'  # every release since the first
	assert all(e['text'][0].isupper() or e['text'][0] in '`"' for r in log['releases'] for e in r['entries'])


def test_the_readme_links_to_the_changelog():
	spanish, english = README.split('\n## English\n')
	assert '](#changelog)' in spanish and '](#changelog)' in english
	assert README.index(changelog.SECTION) > README.index('\n## English\n')  # in English, after both languages


def sample(unreleased='', releases=None):
	releases = releases or [('v0.3.20', '2026-11-11', '0.3.30', ['- **Assistant** (fix): A fix.'])]
	text = '# MonitorEO\n\n## Changelog\n\nWhat each release brings.\n\n' + unreleased
	for tag, date, package, entries in releases:
		text += f'### [{tag}]({URL}{tag}) · {date} · package {package}\n\n' + '\n'.join(entries) + '\n\n'
	return text + '---\n\nCopyright\n'


def test_parse():
	text = sample('### Unreleased\n\n- **QGIS plugin, Earth Engine app**: A `new` option.\n\n')
	log = changelog.parse(text)
	assert log['unreleased'][0]['tools'] == ['QGIS plugin', 'Earth Engine app']
	assert not log['unreleased'][0]['fix']
	release = log['releases'][0]
	assert (release['tag'], release['date'], release['package']) == ('v0.3.20', '2026-11-11', '0.3.30')
	assert release['entries'][0]['fix'] and release['entries'][0]['text'] == 'A fix.'
	assert changelog.problems(text, '0.3.20', '0.3.30') == []


@pytest.mark.parametrize('text, problem', [
	(sample(releases=[('v0.3.20', '2026-11-11', '0.3.30', ['- **Asistente**: Unknown tool.'])]), 'unknown tool'),
	(sample(releases=[('v0.3.20', '2026-11-11', '0.3.30', ['- Assistant: Without bold.'])]), 'not an entry'),
	(sample(releases=[('v0.3.20', '2026-11-11', '0.3.30', ['- **Assistant**: Two', '  lines.'])]), 'not an entry'),
	(sample(releases=[('v0.3.20', '2026-11-11', '0.3.30', ['- **Assistant**: No period'])]), 'period'),
	(sample(releases=[('v0.3.20', '2026-11-11', '0.3.30', [])]), 'no entries'),
	(sample('### Unreleased\n\n'), 'without entries'),
	(sample().replace('### [v0.3.20]', '### v0.3.20 '), 'not a release'),
	(sample().replace('tag/v0.3.20', 'tag/v0.3.19'), 'link'),
	(sample(releases=[('v0.3.19', '2026-11-10', '0.3.29', ['- **Assistant**: Old.']),
	                  ('v0.3.20', '2026-11-11', '0.3.30', ['- **Assistant**: New.'])]), 'newest first'),
	(sample(releases=[('v0.3.19', '2026-11-10', '0.3.29', ['- **Assistant**: Only the old one.'])]), 'QGIS plugin is'),
	(sample(releases=[('v0.3.20', '2026-11-11', '0.3.29', ['- **Assistant**: Old package.'])]), 'pyproject.toml has'),
])
def test_problems(text, problem):
	found = changelog.problems(text, '0.3.20', '0.3.30')
	assert any(problem in p for p in found), found


def test_notes_of_a_github_release():
	text = sample()
	notes = changelog.notes(text, 'v0.3.20')
	assert notes.startswith('MonitorEO v0.3.20 (2026-11-11): QGIS plugin 0.3.20, Python and R package 0.3.30.')
	assert '- **Assistant** (fix): A fix.' in notes and changelog.REPO + '#changelog' in notes
	with pytest.raises(ValueError):
		changelog.notes(text, 'v0.3.21')
	assert changelog.notes(README, changelog.parse(README)['releases'][0]['tag'])


def test_changelog_of_the_qgis_plugin():
	# plugins.qgis.org reads metadata.txt with the interpolation of ConfigParser: no %, one value of several lines
	text = sample(releases=[('v0.3.20', '2026-11-11', '0.3.30', ['- **All tools**: The **SCF** is the 20% of '
	                                                             '[the pixels](https://example.org) with `snow`.'])])
	log = changelog.qgis(text)
	assert log == '0.3.20 (2026-11-11)\n- All tools: The SCF is the 20 percent of the pixels with snow.'
	block = 'changelog=' + '\n    '.join(changelog.qgis(README).splitlines())
	meta = configparser.ConfigParser()
	meta.read_string('[general]\nname=MonitorEO\n' + block + '\n')
	value = meta['general']['changelog']
	last = changelog.parse(README)['releases'][0]
	assert value.splitlines()[0] == '.'.join(map(str, changelog.version(last['tag']))) + f' ({last["date"]})'
	assert '%' not in value and '**' not in value and len(re.findall(r'^\d+\.\d+\.\d+ \(', value, re.M)) <= 5


def test_the_zip_of_the_plugin_has_the_changelog():
	import importlib
	import sys
	sys.path.insert(0, os.path.join(ROOT, 'qgis'))
	try:
		build = importlib.import_module('build_plugin')
	finally:
		sys.path.remove(os.path.join(ROOT, 'qgis'))
	text = build.metadata_with_changelog()
	meta = configparser.ConfigParser()
	meta.read_string(text)
	assert meta['general']['changelog'] and meta['general']['version'] in meta['general']['changelog']
	assert text.count('changelog=') == 1
