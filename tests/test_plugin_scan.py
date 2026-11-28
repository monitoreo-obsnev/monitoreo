"""The security scan of the zip of the QGIS plugin (qgis/build_plugin.py): only the lines that are an ID of Earth
Engine go to the .secrets.baseline of our files, and the code of monitoreo has no finding of Bandit it can avoid."""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('build_plugin', os.path.join(HERE, '..', 'qgis', 'build_plugin.py'))
build_plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_plugin)


def test_only_the_ids_of_earth_engine_are_false_findings(tmp_path):
	lines = ['{', '  "users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1": {', '  "projects/sat-io/x/y_1": [',
	         '  "key": "AIzaSyD4b1f00cafe1234567890abcdefghijklm",', '  "users/a/b": "c3VwZXJzZWNyZXQ="',
	         '  "projects/AIzaSyD4b1f00cafe1234567890abcdefghijklm": {', '  "users/x":']
	(tmp_path / 'c.json').write_text('\n'.join(lines), encoding='utf-8')
	ok = [build_plugin.asset_id_line(str(tmp_path), 'c.json', n) for n in range(1, len(lines) + 1)]
	assert ok == [False, True, True, False, False, False, False]
	assert not build_plugin.asset_id_line(str(tmp_path), 'missing.json', 1)


def test_the_weak_hashes_of_monitoreo_are_not_for_security():
	# Bandit B324 stops the plugin: every md5 or sha1 of monitoreo says usedforsecurity=False
	import ast
	src = os.path.join(HERE, '..', 'src', 'monitoreo')
	for name in sorted(os.listdir(src)):
		if not name.endswith('.py'):
			continue
		with open(os.path.join(src, name), encoding='utf-8') as f:
			tree = ast.parse(f.read())
		for node in ast.walk(tree):
			if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('md5', 'sha1'):
				ok = any(k.arg == 'usedforsecurity' and isinstance(k.value, ast.Constant) and k.value.value is False
				         for k in node.keywords)
				assert ok, f'{name}:{node.lineno} {node.func.attr} without usedforsecurity=False'


def test_the_canopy_height_id_keeps_its_allowlist_comment():
	with open(os.path.join(HERE, '..', 'src', 'monitoreo', 'catalog.py'), encoding='utf-8') as f:
		lines = [l for l in f if "'col': 'users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1'" in l]
	assert lines and all('pragma: allowlist secret' in l for l in lines)
