"""What the zip of the QGIS plugin carries of monitoreo (qgis/build_plugin.py), without QGIS: the scan of
plugins.qgis.org (Bandit and detect-secrets) refuses a version with any finding in it, so the zip leaves out the
modules that the plugin never imports, such as those of the assistant."""

import ast
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src', 'monitoreo')
PLUGIN = os.path.join(ROOT, 'qgis', 'monitoreo_qgis')


def _modules():
	return {f[:-3] for f in os.listdir(SRC) if f.endswith('.py') and f != '__init__.py'}


def _imports(path, inside):
	"""The modules of monitoreo that the file PATH imports, anywhere in it (also inside functions): with INSIDE, a module
	of monitoreo (from . import x, from .x import y), else the plugin (from monitoreo import x, import monitoreo.x)."""
	with open(path, encoding='utf-8') as f:
		tree = ast.parse(f.read())
	out = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.ImportFrom):
			if inside and node.level == 1:
				out |= {node.module.split('.')[0]} if node.module else {a.name for a in node.names}
			elif node.module and node.module.split('.')[0] == 'monitoreo':
				parts = node.module.split('.')
				out |= {parts[1]} if len(parts) > 1 else {a.name for a in node.names}
		elif isinstance(node, ast.Import):
			out |= {a.name.split('.')[1] for a in node.names if a.name.startswith('monitoreo.')}
	return out & _modules()


def plugin_modules():
	"""The modules of monitoreo that the plugin can import: those its files import, and theirs."""
	todo = set().union(*(_imports(os.path.join(PLUGIN, f), False) for f in os.listdir(PLUGIN) if f.endswith('.py')))
	seen = set()
	while todo:
		m = todo.pop()
		seen.add(m)
		todo |= _imports(os.path.join(SRC, m + '.py'), True) - seen
	return seen


def test_the_zip_leaves_out_what_the_plugin_never_imports():
	sys.path.insert(0, os.path.join(ROOT, 'qgis'))
	try:
		build = importlib.import_module('build_plugin')
	finally:
		sys.path.pop(0)
	left_out = {name[:-3] for name in build.MONITOREO_UNUSED if name.endswith('.py')}
	used = plugin_modules()
	assert {'services', 'readme', 'references'} <= used  # what the plugin computes and documents with
	never = _modules() - used
	assert never <= left_out, f'modules the plugin never imports, still in its zip: {sorted(never - left_out)}'
	assert 'documents' in left_out  # the documents of the assistant: XML parsers that Bandit flags (B405, B314)
	# and none that it imports: without report.py, the README of every result failed (readme.text imports it)
	assert not used & left_out, f'modules the plugin imports, left out of its zip: {sorted(used & left_out)}'
	assert 'report' in used


def test_the_readme_of_a_result_with_the_modules_of_the_zip(tmp_path):
	"""The README of a result, written with only the modules of monitoreo that the zip of the plugin carries (in a
	new Python, so that those of this one do not count)."""
	import shutil
	import subprocess
	sys.path.insert(0, os.path.join(ROOT, 'qgis'))
	try:
		build = importlib.import_module('build_plugin')
	finally:
		sys.path.pop(0)
	shutil.copytree(SRC, tmp_path / 'monitoreo',
	                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', *build.MONITOREO_UNUSED))
	code = ('from monitoreo import readme; print(readme.text("time_series", {"region": {"bbox": [0, 0, 1, 1]}, '
	        '"variable": "NDVI", "sensor": "Modis", "start": "2020-01-01", "end": "2020-12-31"}, {"unit": "[unitless]"}))')
	env = dict(os.environ, PYTHONPATH=str(tmp_path), PYTHONNOUSERSITE='1')
	out = subprocess.run([sys.executable, '-c', code], cwd=tmp_path, env=env, capture_output=True, text=True)
	assert out.returncode == 0, out.stderr
	assert 'Monthly time series of NDVI (MODIS)' in out.stdout and 'HOW TO CITE IT' in out.stdout


# what Bandit flags in the code of the plugin's zip that MonitorEO runs on purpose: each such line says so with
# «# nosec» and the IDs of its tests, as plugins.qgis.org refuses a version with any finding (qgis/build_plugin.py)
NOSEC = {'urlopen': {'B310'}, 'import subprocess': {'B404'}, 'subprocess': {'B603'}}


def _flagged(path):
	"""The lines of the module PATH that Bandit would flag for urllib.request.urlopen (B310), import subprocess (B404),
	a call of subprocess without a shell (B603) and, a program named without its path, B607: {line: IDs}."""
	with open(path, encoding='utf-8') as f:
		tree = ast.parse(f.read())
	out = {}
	for node in ast.walk(tree):
		if isinstance(node, ast.Import) and any(a.name == 'subprocess' for a in node.names):
			out.setdefault(node.lineno, set()).update(NOSEC['import subprocess'])
		elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
			owner = node.func.value
			if node.func.attr == 'urlopen':
				out.setdefault(node.lineno, set()).update(NOSEC['urlopen'])
			elif isinstance(owner, ast.Name) and owner.id == 'subprocess':
				out.setdefault(node.lineno, set()).update(NOSEC['subprocess'])
				first = node.args[0] if node.args else None
				first = first.elts[0] if isinstance(first, ast.List) and first.elts else first
				if isinstance(first, ast.Constant) and isinstance(first.value, str) and '/' not in first.value:
					out[node.lineno].add('B607')
	return out


def test_the_modules_of_the_zip_mark_what_bandit_flags():
	"""Every module of monitoreo that the zip carries marks with «# nosec» and its IDs the lines that Bandit flags:
	municipalities.py, which the plugin imports (level 3 of the administrative units), had urlopen (B310) with only a
	marker of ruff, and import subprocess (B404) and subprocess.check_output of gcloud (B603, B607) bare."""
	import re
	used = plugin_modules()
	assert 'municipalities' in used
	missing, seen = [], set()
	for module in sorted(used):
		path = os.path.join(SRC, module + '.py')
		with open(path, encoding='utf-8') as f:
			lines = f.read().splitlines()
		for line, ids in _flagged(path).items():
			seen.add(module)
			marked = re.search(r'#\s*nosec\b([^#]*)', lines[line - 1])
			if not marked or not ids <= set(re.findall(r'B\d{3}', marked.group(1))):
				missing.append(f'{module}.py:{line} {sorted(ids)}: {lines[line - 1].strip()}')
	assert not missing, 'lines that Bandit flags, without # nosec and their IDs:\n' + '\n'.join(missing)
	assert {'municipalities', 'assets', 'animation'} <= seen  # the check sees them
