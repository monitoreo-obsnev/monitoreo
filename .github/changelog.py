"""The changelog of MonitorEO: the section "## Changelog" of README.md, what each release brings, newest first.

    python .github/changelog.py check            # its format, and that it has the versions and date of the files
    python .github/changelog.py notes v0.3.19    # the entries of a release in Markdown (its GitHub release notes)
    python .github/changelog.py qgis             # the changelog of metadata.txt of the QGIS plugin (last releases)

Each release is a heading, with the version of the QGIS plugin (its tag), its date and the version of the Python and
R package, followed by its entries, one per line, each with the tools it reaches and "(fix)" for the fixes:

    ### [v0.3.19](https://github.com/monitoreo-obsnev/monitoreo/releases/tag/v0.3.19) · 2026-11-10 · package 0.3.29

    - **Assistant**: A button to suggest a change or report an error.
    - **QGIS plugin, Earth Engine app** (fix): The map of a period without images no longer stops with an error.

Above the releases, "### Unreleased" holds the entries of the pull requests merged since the last release (the
assistant and the MCP server have them already: they update themselves from main); the release renames it. The
workflow qgis-plugin.yml takes the notes of each GitHub release from here, and qgis/build_plugin.py the changelog that
the plugin manager of QGIS shows. Only the standard library: it runs in the workflows and in the build of the plugin.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = 'https://github.com/monitoreo-obsnev/monitoreo'
SECTION = '## Changelog'
UNRELEASED = '### Unreleased'
TOOLS = ('All tools', 'Earth Engine app', 'QGIS plugin', 'MCP server', 'Assistant', 'Python package', 'Command line',
         'R package', 'Results viewer')
RELEASE = re.compile(r'^### \[(?P<tag>v?\d+(?:\.\d+)+)\]\(' + re.escape(REPO) + r'/releases/tag/(?P<link>[^)]+)\)'
                     r' · (?P<date>\d{4}-\d{2}-\d{2}) · package (?P<package>\d+(?:\.\d+)+)$')
ENTRY = re.compile(r'^- \*\*(?P<tools>[^*]+)\*\*(?P<fix> \(fix\))?: (?P<text>\S.*)$')
FORMAT = (f'a release is "### [v<plugin version>]({REPO}/releases/tag/v<plugin version>) · <YYYY-MM-DD> · '
          'package <package version>", and an entry is "- **<tools>**: <text>." or "- **<tools>** (fix): <text>."')


def version(v):
	"""A version as a tuple to compare: v0.3.19 = (0, 3, 19), 0.1 = (0, 1, 0)."""
	parts = [int(p) for p in str(v).strip().lstrip('vV').split('.')]
	return tuple(parts + [0] * (3 - len(parts)))


def section(text):
	"""The lines of the section "## Changelog" (without its heading), with their line numbers in README.md."""
	lines = text.splitlines()
	starts = [i for i, line in enumerate(lines) if line.strip() == SECTION]
	if len(starts) != 1:
		raise ValueError(f'README.md has {len(starts)} sections "{SECTION}" (one expected)')
	out = []
	for i in range(starts[0] + 1, len(lines)):
		if lines[i].startswith('## ') or lines[i].strip() == '---':
			break
		out.append((i + 1, lines[i]))
	return out


def parse(text):
	"""The changelog of README.md: {'unreleased': entries or None, 'releases': [{tag, date, package, entries}]},
	newest first. An entry is {tools, fix, text, line}. Raises ValueError, with the line, if something is malformed."""
	unreleased, releases, current = None, [], None
	for n, line in section(text):
		if line.startswith('### '):
			if line.strip() == UNRELEASED:
				if releases or unreleased is not None:
					raise ValueError(f'README.md:{n}: "{UNRELEASED}" goes once, above the releases')
				unreleased = current = []
				continue
			m = RELEASE.match(line.rstrip())
			if not m:
				raise ValueError(f'README.md:{n}: a heading of the changelog that is not a release: {FORMAT}')
			if m['link'] != m['tag']:
				raise ValueError(f'README.md:{n}: the link of {m["tag"]} goes to the release {m["link"]}')
			current = []
			releases.append({'tag': m['tag'], 'date': m['date'], 'package': m['package'], 'entries': current,
			                 'line': n})
		elif line.startswith('- ') or (current is not None and line.strip()):
			if current is None:
				raise ValueError(f'README.md:{n}: an entry above the first release')
			m = ENTRY.match(line.rstrip())
			if not m:
				raise ValueError(f'README.md:{n}: not an entry of the changelog (one per line): {FORMAT}')
			tools = [t.strip() for t in m['tools'].split(',')]
			wrong = [t for t in tools if t not in TOOLS]
			if wrong:
				raise ValueError(f'README.md:{n}: unknown tool {", ".join(wrong)} (the tools: {", ".join(TOOLS)})')
			current.append({'tools': tools, 'fix': bool(m['fix']), 'text': m['text'].strip(), 'line': n})
	return {'unreleased': unreleased, 'releases': releases}


def problems(text, plugin=None, package=None, released=None):
	"""What is wrong with the changelog of README.md, against the version of the QGIS plugin and of the package and
	the date of their release (by default, those of metadata.txt, pyproject.toml and __released__ of
	src/monitoreo/__init__.py, which the tools show next to their version): a list of texts, empty if nothing."""
	plugin = plugin or read_version('qgis/monitoreo_qgis/metadata.txt', r'^version=(\S+)')
	package = package or read_version('pyproject.toml', r'^version\s*=\s*"([^"]+)"')
	released = released or read_version('src/monitoreo/__init__.py', r"^__released__\s*=\s*['\"]([^'\"]+)")
	try:
		log = parse(text)
	except ValueError as e:
		return [str(e)]
	out = []
	if log['unreleased'] is not None and not log['unreleased']:
		out.append(f'"{UNRELEASED}" without entries: remove it until there is one')
	releases = log['releases']
	if not releases:
		return out + ['the changelog has no release']
	for release in releases:
		if not release['entries']:
			out.append(f'README.md:{release["line"]}: the release {release["tag"]} has no entries')
		for entry in release['entries']:
			if not entry['text'].endswith(('.', '.)')):
				out.append(f'README.md:{entry["line"]}: an entry ends with a period')
	for new, old in zip(releases, releases[1:]):
		if version(new['tag']) <= version(old['tag']):
			out.append(f'README.md:{new["line"]}: {new["tag"]} is above {old["tag"]}: newest first')
		if new['date'] < old['date'] or version(new['package']) < version(old['package']):
			out.append(f'README.md:{new["line"]}: {new["tag"]} has an older date or package than {old["tag"]}')
	last = releases[0]
	if plugin and version(last['tag']) != version(plugin):
		out.append(f'the last release of the changelog is {last["tag"]}, but the QGIS plugin is {plugin} '
		           f'(metadata.txt): a release renames "{UNRELEASED}" to its heading')
	if package and version(last['package']) != version(package):
		out.append(f'the release {last["tag"]} of the changelog has the package {last["package"]}, but '
		           f'pyproject.toml has {package}')
	if released and released != last['date']:
		out.append(f'the release {last["tag"]} of the changelog is of {last["date"]}, but src/monitoreo/__init__.py has '
		           f'__released__ = {released!r}: a release sets it to its date')
	return out


def entry_text(entry, markdown=True):
	"""An entry as a line: '- **Assistant** (fix): ...' in Markdown, or '- Assistant (fix): ...' in plain text."""
	tools = ', '.join(entry['tools'])
	head = f'**{tools}**' if markdown else tools
	return f'- {head}{" (fix)" if entry["fix"] else ""}: {entry["text"] if markdown else plain(entry["text"])}'


def plain(text):
	"""Markdown as plain text, without % (metadata.txt is read with the interpolation of ConfigParser)."""
	text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
	text = text.replace('**', '').replace('`', '')
	return re.sub(r'\s*%', ' percent', text)


def notes(text, tag):
	"""The notes of the GitHub release of TAG, in Markdown: its versions and its entries."""
	for release in parse(text)['releases']:
		if version(release['tag']) == version(tag):
			lines = [f'MonitorEO {release["tag"]} ({release["date"]}): QGIS plugin {".".join(map(str, version(tag)))}, '
			         f'Python and R package {release["package"]}.', '']
			lines += [entry_text(e) for e in release['entries']]
			lines += ['', f'All the versions: [changelog]({REPO}#changelog).']
			return '\n'.join(lines)
	raise ValueError(f'the changelog of README.md has no release {tag}')


def qgis(text, n=5):
	"""The changelog of metadata.txt (what the plugin manager of QGIS shows): the last N releases, in plain text, one
	line each, to go after "changelog=" with an indent."""
	lines = []
	for release in parse(text)['releases'][:n]:
		lines.append(f'{".".join(map(str, version(release["tag"])))} ({release["date"]})')
		lines += [entry_text(e, markdown=False) for e in release['entries']]
	return '\n'.join(lines)


def read_version(path, pattern):
	try:
		with open(os.path.join(ROOT, path), encoding='utf-8') as f:
			m = re.search(pattern, f.read(), re.M)
	except OSError:
		return None
	return m.group(1).strip() if m else None


def readme():
	with open(os.path.join(ROOT, 'README.md'), encoding='utf-8') as f:
		return f.read()


def main(argv):
	if not argv or argv[0] not in ('check', 'notes', 'qgis') or (argv[0] == 'notes' and len(argv) != 2):
		sys.exit(__doc__.split('\n\n')[1])
	text = readme()
	try:
		if argv[0] == 'check':
			found = problems(text)
			for p in found:
				print(p)
			sys.exit(1 if found else 0)
		print(notes(text, argv[1]) if argv[0] == 'notes' else qgis(text))
	except ValueError as e:
		sys.exit(str(e))


if __name__ == '__main__':
	main(sys.argv[1:])
