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
