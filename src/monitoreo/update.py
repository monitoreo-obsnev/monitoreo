"""Keep the installed package at the last version of its GitHub repository (github.com/monitoreo-obsnev/monitoreo).

The tools that run from an installed copy call ensure_latest() when they start (the MCP server: `monitoreo mcp`), so
they always compute with the last version: if the installed commit is not the last one of GitHub, that version is
installed with pip in the same Python. Only a copy installed in site-packages is replaced: a clone, an editable
install (`pip install -e`, for development) or a copy inside another program (the QGIS plugin) is left as it is.
"""

import importlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

REPO = 'monitoreo-obsnev/monitoreo'
BRANCH = 'main'


def _stderr(msg):
	print(msg, file=sys.stderr, flush=True)


def installed():
	"""(version, commit of GitHub or None, folder of an editable copy or None) of the installed package, or None."""
	try:
		dist = importlib.metadata.distribution('monitoreo')
	except importlib.metadata.PackageNotFoundError:
		return None
	try:
		url = json.loads(dist.read_text('direct_url.json') or '{}')
	except ValueError:
		url = {}
	commit = url.get('vcs_info', {}).get('commit_id')
	m = re.search(r'/archive/([0-9a-f]{40})\.zip$', url.get('url', ''))
	if m:
		commit = m.group(1)
	folder = None
	if url.get('dir_info', {}).get('editable') and url.get('url', '').startswith('file:'):
		folder = urllib.request.url2pathname(urllib.parse.urlparse(url['url']).path)
	return dist.version, commit, folder


def local_copy():
	"""Folder of the running package if it is not an installed copy (a clone, an editable install or a copy inside
	another program), else None."""
	here = os.path.dirname(os.path.abspath(__file__))
	parts = os.path.normcase(here).split(os.sep)
	return None if 'site-packages' in parts or 'dist-packages' in parts else here


def latest(timeout=15):
	"""Commit of the last version in GitHub (branch BRANCH)."""
	req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/commits/{BRANCH}',
	                             headers={'Accept': 'application/vnd.github.sha', 'User-Agent': 'monitoreo'})
	with urllib.request.urlopen(req, timeout=timeout) as r:
		sha = r.read().decode().strip()
	if not re.fullmatch(r'[0-9a-f]{40}', sha):
		raise ValueError(f'unexpected answer of GitHub: {sha[:80]}')
	return sha


def requirement(commit, extras=''):
	"""pip requirement of the version COMMIT of GitHub (an archive: it does not need git)."""
	return f"monitoreo{'[' + extras + ']' if extras else ''} @ https://github.com/{REPO}/archive/{commit}.zip"


def _pip(*args):
	# pip writes to stderr only: the MCP server talks to its client through stdout
	subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--quiet', *args],
	               check=True, stdout=sys.stderr)


def ensure_latest(extras='', log=_stderr):
	"""Install the last version of GitHub if the installed one is another, with the dependencies of EXTRAS (e.g.
	'mcp,plot'). Returns 'updated' (the new version is used by the modules imported from now on: restart the
	program), 'current', 'local' (a local copy, see local_copy, left as it is) or 'offline' (GitHub cannot be reached,
	or the update failed: the installed version goes on)."""
	inst = installed()
	local = local_copy()
	try:
		sha = latest()
	except (OSError, ValueError) as e:
		log(f"monitoreo {inst[0] if inst else ''}: GitHub cannot be reached to check the last version ({e}); "
		    'using the installed one')
		return 'offline'
	if local:
		log(f'monitoreo: local copy in {local}, not updated from GitHub ({sha[:7]})')
		return 'local'
	if inst and inst[1] == sha:
		log(f'monitoreo {inst[0]} ({sha[:7]}): the last version of GitHub')
		return 'current'
	log(f'monitoreo: installing the last version of GitHub ({REPO}, {sha[:7]})...')
	try:
		_pip('--force-reinstall', '--no-deps', requirement(sha))  # the version number may be the same as the installed one
		_pip(requirement(sha, extras))  # the dependencies that are missing, if any
	except (OSError, subprocess.CalledProcessError) as e:
		log(f'monitoreo: cannot install the last version of GitHub ({e}); using the installed one')
		return 'offline'
	importlib.invalidate_caches()
	log(f"monitoreo {installed()[0]} ({sha[:7]}) installed")
	return 'updated'
