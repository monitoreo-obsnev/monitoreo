"""The app of MonitorEO published from the git repository of its scripts in Earth Engine (gee/build.py modules and
gee/push_app.py), without Earth Engine and without network: every file of the repository is ASCII and under the
512 KiB that Earth Engine takes; the script app requires the modules of the catalog by their literal paths; in Node,
the modules and the script app give exactly the CATALOG of catalog.js and the same panel as catalog.js, core.js and
ui.js (with the ui and ee of tests/test_themes.py, which compute nothing); and push_app, with the repositories of Earth
Engine as local bare repositories: its commit, the push to the repository of the app and then to its backup (a mirror
that never loses a version: its master only moves forward, or replaces its test README), nothing pushed in a dry run,
nothing committed when nothing changed, the main of GitHub as GitHub has it, what it says when the backup was not
mirrored, its refusals and no cookie printed."""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess

import pytest

from monitoreo import catalog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEE = os.path.join(ROOT, 'gee')


def _load(name):
	"""gee/NAME.py as a module (its functions: nothing computes in Earth Engine)."""
	spec = importlib.util.spec_from_file_location(f'monitoreo_gee_{name}', os.path.join(GEE, f'{name}.py'))
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


push_app = _load('push_app')
build = push_app.build


def _read(name):
	with open(os.path.join(GEE, name), encoding='utf-8') as f:
		return f.read()


def _catalogs(files):
	"""The modules that the app requires, in the order it requires them: core, then the modules of the catalog."""
	return [n for n in files if n != 'app']


# The files of the repository ------------------------------------------------------------------------------------


def test_every_file_is_ascii_and_under_the_limit_of_earth_engine():
	files = build.modules()
	assert build.LIMIT < build.MAX_FILE == 524288  # measured: Earth Engine takes 524288 bytes, not 524289
	assert list(files) == ['app', 'core'] + [f'catalog_{n}' for n in range(1, len(files) - 1)]
	for name, text in files.items():
		assert build.MODULE.fullmatch(name)
		assert len(text.encode('ascii')) <= build.LIMIT, name  # encode fails if a character is not ASCII
	# the app is ui.js and the module core is core.js, as they are, with the \u escapes of monitoreo_app.js
	assert files['app'].endswith(build.ascii_js(_read('ui.js')))
	assert files['core'].endswith(build.ascii_js(_read('core.js')) + '\nexports.MonitorEO = MonitorEO;\n')
	with open(os.path.join(GEE, 'monitoreo_app.js'), encoding='ascii') as f:
		assert build.ascii_js(_read('core.js')) in f.read()
	assert build.ascii_js('aá \U0001f600') == 'a\\u00e1\\u2028\\ud83d\\ude00'


def test_the_requires_are_literal_paths_of_the_files_written(tmp_path):
	for repo in (build.REPO, 'users/someone/test-repo'):
		files = build.modules(repo)
		# the app requires the module core, and the module core the modules of the catalog
		paths = [re.findall(r"\brequire\(([^)]*)\)", files[n]) for n in ('app', 'core')]
		assert paths == [[f"'{repo}:core'"], [f"'{repo}:{name}'" for name in _catalogs(files)[1:]]]
		for n, found in zip(('app', 'core'), paths):
			assert files[n].count('require(') == len(found)  # core.js and ui.js require nothing
		assert all(build.MODULE.fullmatch(p.strip("'").split(':')[1]) for found in paths for p in found)
		assert f'Overwrite from repository script path {repo}:app' in files['app']
	for repo in ('', 'monitoreo', "users/x/y'); evil('", 'users/x/y:app'):
		with pytest.raises(ValueError, match='not the path of a repository'):
			build.modules(repo)
	# what build.py --modules writes: those files, and an old catalog_N removed (other files stay)
	(tmp_path / 'catalog_9').write_text('old', encoding='ascii')
	(tmp_path / 'README').write_text('mine', encoding='ascii')
	files = build.modules()
	assert build.write_modules(str(tmp_path), files) == ['catalog_9']
	assert sorted(os.listdir(tmp_path)) == sorted(list(files) + ['README'])
	for name, text in files.items():
		assert (tmp_path / name).read_bytes() == text.encode('ascii')


def test_a_key_or_a_file_bigger_than_the_limit():
	data = build.read_catalog()
	big = max(data, key=lambda k: len(json.dumps(data[k])))
	parts = build.catalog_modules(data, 200000)  # every key fits, not all of them in one module
	assert len(parts) > 2 and all(len(p) <= 200000 for p in parts)
	with pytest.raises(ValueError, match="the key '[a-z_]+' of the catalog alone takes"):
		build.catalog_modules(data, len(json.dumps(data[big])) // 2)
	with pytest.raises(ValueError, match='the file (app|core) of the repository of the app takes'):
		build.modules(limit=200000)  # core.js and ui.js are bigger


# In Node: the modules and the script app ------------------------------------------------------------------------

# the modules of input.modules evaluated as Earth Engine evaluates a module (its exports, in a scope of its own), when
# a script requires them by their path, then the script app: the CATALOG of catalog.js (as JSON, before core.js and
# ui.js run), the paths required, whether the CATALOG of the module core has the very objects of the modules of the
# catalog, and whether core.js left anything global
LOAD = r"""
var original = vm.runInNewContext(input.catalog + '\nJSON.stringify(CATALOG);', {});
var sources = {}, exportsOf = {}, merged = {}, required = [];
Object.keys(input.modules).filter(function (n) { return n !== 'app'; }).forEach(function (name) {
	sources[input.repo + ':' + name] = input.modules[name];
});
global.require = function (p) {
	required.push(p);
	if (!sources[p]) throw new Error('no module ' + p);
	if (!exportsOf[p]) {
		var exports = {};
		exportsOf[p] = exports;
		vm.runInThisContext('(function (exports) {\n' + sources[p] + '\n})', {filename: p})(exports);
		if (exports.part) Object.keys(exports.part).forEach(function (k) { merged[k] = exports.part[k]; });
	}
	return exportsOf[p];
};
vm.runInThisContext(input.modules.app, {filename: 'app'});
var catalogEqual = JSON.stringify(merged) === original;
var CORE_CATALOG = MonitorEO.CATALOG;
var loaded = {catalogEqual: catalogEqual, required: required, keys: Object.keys(CORE_CATALOG),
	same: Object.keys(merged).every(function (k) { return CORE_CATALOG[k] === merged[k]; }),
	global: typeof CATALOG !== 'undefined'};
"""


def _node(script, data):
	run = subprocess.run(['node', '-e', script, GEE], input=json.dumps(data), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	return json.loads(run.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_modules_give_the_catalog_of_catalog_js(tmp_path, monkeypatch):
	"""Several modules (a smaller limit), with a core.js and a ui.js that only read CATALOG: the same catalog, filled
	before core.js runs."""
	shutil.copy(os.path.join(GEE, 'catalog.js'), tmp_path)
	(tmp_path / 'core.js').write_text('var MonitorEO = {keys: Object.keys(CATALOG), CATALOG: CATALOG};\n',
	                                  encoding='utf-8')
	(tmp_path / 'ui.js').write_text('MonitorEO.ui = MonitorEO.CATALOG.themes.length;\n', encoding='utf-8')
	monkeypatch.setattr(build, 'HERE', str(tmp_path))
	files = build.modules(limit=200000)
	assert len(files) > 3
	script = ("var fs = require('fs'), vm = require('vm'); var input = JSON.parse(fs.readFileSync(0, 'utf8'));\n" +
	          LOAD + 'loaded.core = MonitorEO;\nprocess.stdout.write(JSON.stringify(loaded));')
	out = _node(script, {'modules': files, 'repo': build.REPO, 'catalog': _read('catalog.js')})
	keys = list(build.read_catalog())
	assert out['catalogEqual'] and out['same'] and out['keys'] == keys and not out['global']
	assert out['required'] == [f'{build.REPO}:{n}' for n in _catalogs(files)]
	assert out['core']['keys'] == keys and out['core']['ui'] == len(catalog.THEMES)


# the panel that ui.js draws (with the ui of PANEL): the kind of each widget, its texts and the values of its items
TREE = r"""
function tree(w) {
	var o = w.opts || {}, d = {kind: w.kind};
	['label', 'placeholder'].forEach(function (k) { if (typeof o[k] === 'string') d[k] = o[k]; });
	if (['string', 'number', 'boolean'].indexOf(typeof o.value) >= 0) d.value = o.value;
	if (Array.isArray(o.items)) d.items = o.items.map(function (i) { return i && typeof i === 'object' ? i.value : i; });
	d.children = (w.children || []).map(tree);
	return d;
}
var result = typeof loaded === 'undefined' ? {} : loaded;
result.tree = tree(root);
result.functions = Object.keys(global.MonitorEO).sort();
process.stdout.write(JSON.stringify(result));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_app_of_the_repository_is_the_app_of_its_parts():
	"""The script app with its modules gives the CATALOG of catalog.js, and core.js and ui.js load without errors and
	draw the same panel as catalog.js, core.js and ui.js run as the other tests of the app run them."""
	from test_themes import PANEL
	head = PANEL[:PANEL.index('var GEE = process.argv')]
	files = build.modules()
	parts = ("var GEE = process.argv[process.argv.length - 1];\n"
	         "['catalog.js', 'core.js', 'ui.js'].forEach(function (f) {\n"
	         "\tvm.runInThisContext(fs.readFileSync(path.join(GEE, f), 'utf8'), {filename: f});\n"
	         "});\n")
	data = {'assets': {}, 'modules': files, 'repo': build.REPO, 'catalog': _read('catalog.js')}
	expected = _node(head + parts + TREE, data)
	out = _node(head + LOAD + TREE, data)
	assert out['catalogEqual'] and out['same'] and out['keys'] == list(build.read_catalog()) and not out['global']
	assert out['required'] == [f'{build.REPO}:{n}' for n in _catalogs(files)]
	assert out['tree'] == expected['tree'] and out['functions'] == expected['functions']
	assert {'spec', 'collection', 'image', 'series'} <= set(out['functions'])

	def items(w):
		return [i for c in w['children'] for i in items(c)] + (w.get('items') or [])
	assert {t['key'] for t in catalog.THEMES} <= set(items(out['tree']))  # the menu of the themes


# push_app, with a git that touches no network ----------------------------------------------------------------------

HEAD = 'a1b2c3d' + '4' * 33
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_AUTHOR_NAME='MonitorEO tests',
           GIT_AUTHOR_EMAIL='tests@example.org', GIT_COMMITTER_NAME='MonitorEO tests',
           GIT_COMMITTER_EMAIL='tests@example.org', GIT_TERMINAL_PROMPT='0')
SECRET = 'earthengine.googlesource.com\tFALSE\t/\tTRUE\t2147483647\to\tgit-everest.SECRET-COOKIE-VALUE'


class FakeGit:
	"""The git of push_app without network: the repositories of Earth Engine (push_app.HOST + path) are local bare
	repositories under REMOTES; the checkout ROOT of monitoreo answers HEAD, the main of GitHub (git ls-remote origin)
	and the changes of gee/ as given (by default a folder with only the metadata.txt of a plugin 0.3.99); every call is
	logged as (command, arguments, cookie file)."""

	def __init__(self, tmp_path, root=None, head=HEAD, main=HEAD, dirty=''):
		self.remotes = str(tmp_path / 'remotes')
		self.root = root or str(tmp_path / 'checkout')
		if not root:
			os.makedirs(os.path.join(self.root, 'qgis', 'monitoreo_qgis'), exist_ok=True)
			with open(os.path.join(self.root, 'qgis', 'monitoreo_qgis', 'metadata.txt'), 'w') as f:
				f.write('[general]\nname=MonitorEO\nqgisMinimumVersion=4.0.3\nversion=0.3.99\nauthor=OBSNEV\n')
		self.answers = {('rev-parse', 'HEAD'): head + '\n', ('status', '--porcelain', '--', 'gee'): dirty}
		self.main(main)
		self.calls = []

	def main(self, commit):
		"""The main of GitHub is COMMIT now."""
		self.answers[('ls-remote', 'origin', 'refs/heads/main')] = f'{commit}\trefs/heads/main\n'

	def local(self, repo):
		return os.path.join(self.remotes, repo)

	def __call__(self, args, cwd=None, cookies=None):
		self.calls.append((args[0], list(args), cookies))
		if cwd == self.root:
			if isinstance(self.answers.get(tuple(args)), Exception):
				raise self.answers[tuple(args)]
			return self.answers[tuple(args)]
		args = [self.local(a[len(push_app.HOST):]) if a.startswith(push_app.HOST) else a for a in args]
		run = subprocess.run(['git'] + args, cwd=cwd, capture_output=True, text=True, env=ENV)
		if run.returncode:
			raise push_app.PublishError(run.stderr)
		return run.stdout

	def bare(self, repo, readme=None):
		"""A repository of Earth Engine: empty, or with a commit of a README on master."""
		path = self.local(repo)
		_git('init', '--quiet', '--bare', path)
		if readme:
			work = path + '-work'
			_git('init', '--quiet', work)
			with open(os.path.join(work, 'README'), 'w') as f:
				f.write(readme)
			_git('-C', work, 'add', 'README')
			_git('-C', work, 'commit', '--quiet', '-m', 'README')
			_git('-C', work, 'push', '--quiet', path, 'HEAD:refs/heads/master')
		return path

	def pushes(self):
		return [c for c in self.calls if c[0] == 'push']


def _git(*args):
	return subprocess.run(['git'] + list(args), capture_output=True, text=True, env=ENV, check=True).stdout


def _master(path):
	"""The commits of master of the bare repository PATH (subjects, newest first), its files and its commit."""
	if not _git('--git-dir', path, 'for-each-ref', 'refs/heads/master').strip():
		return None
	return {'log': _git('--git-dir', path, 'log', '--format=%s', 'master').splitlines(),
	        'files': sorted(_git('--git-dir', path, 'ls-tree', '--name-only', 'master').split()),
	        'commit': _git('--git-dir', path, 'rev-parse', 'master').strip(),
	        'text': lambda name: _git('--git-dir', path, 'show', f'master:{name}')}


@pytest.fixture
def cookies(tmp_path):
	"""Cookie files of the two accounts (their content must never be printed)."""
	paths = []
	for name in ('everest', 'backup'):
		path = tmp_path / f'gitcookies-{name}'
		path.write_text(SECRET + name + '\n', encoding='ascii')
		paths.append(str(path))
	return paths


FILES = {'app': "var CATALOG = {};\n[\n\trequire('users/monitoreo-obsnev/monitoreo:catalog_1'),\n"
                "\trequire('users/monitoreo-obsnev/monitoreo:catalog_2')\n].forEach(function (m) {});\n",
         'catalog_1': 'exports.part = {"about": {}};\n', 'catalog_2': 'exports.part = {"variables": []};\n'}


@pytest.mark.skipif(not shutil.which('git'), reason='no git')
def test_push_app_publishes_the_app_then_mirrors_it(tmp_path, cookies):
	fake = FakeGit(tmp_path)
	app = fake.bare(push_app.REPO)  # empty, as Earth Engine creates it
	backup = fake.bare(push_app.BACKUP, readme='a test\n')
	readme = _master(backup)['commit']
	cache = str(tmp_path / 'cache' / 'gee-app')
	run = dict(cookies=cookies[0], backup_cookies=cookies[1], cache=cache, git=fake, root=fake.root)
	done = push_app.publish(files=FILES, **run)
	message = 'MonitorEO app v0.3.99 (gee of monitoreo-obsnev/monitoreo a1b2c3d)'
	assert done['changed'] and done['pushed'] and done['message'] == message and done['removed'] == []
	assert done['path'] == 'users/monitoreo-obsnev/monitoreo:app'
	assert done['files'] == {n: (len(t), hashlib.sha256(t.encode('ascii')).hexdigest()) for n, t in FILES.items()}
	pushed = _master(app)
	assert pushed['log'] == [message] and pushed['files'] == ['app', 'catalog_1', 'catalog_2']
	assert pushed['commit'] == done['commit'] and pushed['text']('catalog_2') == FILES['catalog_2']
	assert _master(backup)['commit'] == done['commit']  # its test README replaced: a mirror
	assert _master(backup)['files'] == ['app', 'catalog_1', 'catalog_2'] and done['mirror'] == 'replaced its test commit'
	# the clone with the cookie of everest; the backup read with its own cookie before anything is pushed; then the
	# repository of the app and the backup, forced only over the README it had (with a lease on it)
	assert [(c[0], c[2]) for c in fake.calls if c[2]] == [('clone', cookies[0]), ('ls-remote', cookies[1]),
	                                                       ('fetch', cookies[1]), ('push', cookies[0]),
	                                                       ('push', cookies[1])]
	first, second = fake.pushes()
	assert first[1][-2:] == ['origin', 'HEAD:refs/heads/master']
	assert second[1][2:] == [f'--force-with-lease=refs/heads/master:{readme}', push_app.HOST + push_app.BACKUP,
	                         f"{done['commit']}:refs/heads/master"]
	assert fake.calls.index(first) < fake.calls.index(second)
	assert f'mirrored to {push_app.HOST}{push_app.BACKUP} (master, replaced its test commit)' in push_app.report(done)

	# again, with nothing changed: no commit (the backup up to date, never forced again)
	fake.calls = []
	again = push_app.publish(files=FILES, **run)
	assert not again['changed'] and again['commit'] == done['commit'] and again['message'] == message
	assert _master(app)['log'] == [message] and not [c for c in fake.calls if c[0] == 'commit']
	assert [c[0] for c in fake.calls if c[2]] == ['fetch', 'ls-remote', 'fetch', 'push', 'push']
	assert again['mirror'] == 'up to date' and not [a for c in fake.pushes() for a in c[1] if a.startswith('--force')]
	assert push_app.report(again)[0].startswith(f"nothing changed: the last commit, {done['commit'][:7]} '{message}'")

	# a catalog in one module: the old catalog_2 removed, and the backup still a mirror
	fewer = {'app': FILES['app'].replace(",\n\trequire('users/monitoreo-obsnev/monitoreo:catalog_2')", ''),
	         'catalog_1': 'exports.part = {"about": {}, "variables": []};\n'}
	third = push_app.publish(files=fewer, **run)
	assert third['changed'] and third['removed'] == ['catalog_2']
	assert _master(app)['files'] == ['app', 'catalog_1'] and len(_master(app)['log']) == 2
	assert _master(backup)['commit'] == third['commit'] == _master(app)['commit']
	assert _master(backup)['log'] == _master(app)['log'] and third['mirror'] == 'fast-forward'
	assert not [a for c in fake.pushes() for a in c[1] if a.startswith('--force')]
	lines = push_app.report(third)
	assert 'users/monitoreo-obsnev/monitoreo:app > UPDATE' in '\n'.join(lines)
	assert any(hashlib.sha256(fewer['catalog_1'].encode()).hexdigest() in line for line in lines)


@pytest.mark.skipif(not shutil.which('git'), reason='no git')
def test_push_app_dry_run_pushes_nothing(tmp_path, cookies):
	fake = FakeGit(tmp_path)
	app = fake.bare(push_app.REPO)
	backup = fake.bare(push_app.BACKUP, readme='a test\n')
	cache = str(tmp_path / 'cache')
	done = push_app.publish(cookies=cookies[0], backup_cookies=str(tmp_path / 'none'), cache=cache, git=fake,
	                        root=fake.root, files=FILES, dry_run=True)  # the cookie of the backup is not needed
	assert done['changed'] and not done['pushed'] and not fake.pushes()
	assert _master(app) is None and _master(backup)['log'] == ['README']
	assert _git('-C', cache, 'log', '--format=%H %s').split(' ', 1) == [done['commit'], done['message'] + '\n']
	assert 'dry run: nothing pushed' in '\n'.join(push_app.report(done))
	# the next run starts from the repository again: the commit of the dry run is not pushed as it was
	real = push_app.publish(cookies=cookies[0], backup_cookies=cookies[1], cache=cache, git=fake, root=fake.root,
	                        files=FILES)
	assert real['changed'] and _master(app)['log'] == [real['message']] and _master(backup)['commit'] == real['commit']


def test_push_app_refuses_what_is_not_main(tmp_path, cookies):
	run = dict(cookies=cookies[0], backup_cookies=cookies[1], cache=str(tmp_path / 'cache'), files=FILES)
	behind, dirty = FakeGit(tmp_path, main='f' * 40), FakeGit(tmp_path, dirty=' M gee/ui.js\n')
	with pytest.raises(push_app.PublishError, match=r'at a1b2c3d, not at main as GitHub has it \(fffffff\)'):
		push_app.publish(git=behind, root=behind.root, **run)
	with pytest.raises(push_app.PublishError, match='gee/ has uncommitted changes'):
		push_app.publish(git=dirty, root=dirty.root, **run)
	for fake in (behind, dirty):  # nothing cloned nor pushed
		assert fake.calls and all(c[0] in ('rev-parse', 'status', 'ls-remote') for c in fake.calls)
	fake = FakeGit(tmp_path)
	with pytest.raises(push_app.PublishError, match='no cookie file .*new-password'):
		push_app.publish(git=fake, root=fake.root, **dict(run, cookies=str(tmp_path / 'none')))
	with pytest.raises(push_app.PublishError, match=f'no cookie file .* the repository {push_app.BACKUP}'):
		push_app.publish(git=fake, root=fake.root, **dict(run, backup_cookies=str(tmp_path / 'none')))
	assert all(c[0] in ('rev-parse', 'status', 'ls-remote') for c in fake.calls)


@pytest.mark.skipif(not shutil.which('git'), reason='no git')
def test_push_app_allow_any(tmp_path, cookies):
	fake = FakeGit(tmp_path, main='f' * 40, dirty=' M gee/ui.js\n')
	fake.bare(push_app.REPO)
	done = push_app.publish(cookies=cookies[0], cache=str(tmp_path / 'cache'), git=fake, root=fake.root, files=FILES,
	                        dry_run=True, allow_any=True)
	assert done['message'].endswith('(gee of monitoreo-obsnev/monitoreo a1b2c3d with uncommitted changes)')


@pytest.mark.skipif(not shutil.which('git'), reason='no git')
def test_push_app_never_prints_a_cookie(tmp_path, cookies, monkeypatch, capsys):
	"""The command line, with the files that build.py writes: what it says, and never a cookie (git gets only the paths
	of their files), also when it refuses."""
	fake = FakeGit(tmp_path, root=push_app.ROOT)
	app = fake.bare(push_app.REPO)
	backup = fake.bare(push_app.BACKUP, readme='a test\n')
	monkeypatch.setattr(push_app, 'run_git', fake)
	push_app.main(['--cookies', cookies[0], '--backup-cookies', cookies[1], '--cache', str(tmp_path / 'cache')])
	out, err = capsys.readouterr()
	files = build.modules()
	assert _master(app)['files'] == sorted(files) and _master(backup)['commit'] == _master(app)['commit']
	assert 'Overwrite from repository script path users/monitoreo-obsnev/monitoreo:app > UPDATE' in out
	for name, text in files.items():
		assert re.search(rf'^  {name} +{len(text)} {hashlib.sha256(text.encode()).hexdigest()}$', out, re.M), name
	assert {c[2] for c in fake.calls} <= {None, cookies[0], cookies[1]}
	fake.main('f' * 40)
	with pytest.raises(SystemExit, match='push_app: the checkout is at a1b2c3d'):
		push_app.main(['--cookies', cookies[0], '--backup-cookies', cookies[1], '--cache', str(tmp_path / 'cache')])
	out2, err2 = capsys.readouterr()
	assert 'SECRET-COOKIE' not in out + err + out2 + err2


def test_run_git_passes_only_the_path_of_the_cookie_file(monkeypatch):
	seen = []

	class Run:
		def __init__(self, code):
			self.returncode, self.stdout, self.stderr = code, 'out\n', 'fatal: no\n'

	def run(cmd, **kwargs):
		seen.append((cmd, kwargs))
		return Run(1 if 'fail' in cmd else 0)

	monkeypatch.setattr(push_app.subprocess, 'run', run)
	assert push_app.run_git(['push', 'origin', 'HEAD'], cwd='/clone', cookies='/home/me/.gitcookies-everest') == 'out\n'
	cmd, kwargs = seen[0]
	assert cmd == ['git', '-c', 'http.cookiefile=/home/me/.gitcookies-everest', 'push', 'origin', 'HEAD']
	assert kwargs['cwd'] == '/clone' and kwargs['env']['GIT_TERMINAL_PROMPT'] == '0'
	assert push_app.run_git(['status']) == 'out\n' and seen[1][0] == ['git', 'status']
	with pytest.raises(push_app.PublishError, match='git fail failed: fatal: no'):
		push_app.run_git(['fail'])


FILES_2 = dict(FILES, catalog_1='exports.part = {"about": {"version": "2"}};\n')  # a second version of the app


@pytest.mark.skipif(not shutil.which('git'), reason='no git')
def test_push_app_never_loses_the_history_of_the_backup(tmp_path, cookies):
	"""The repository of the app lost and recreated empty, the case the backup is for: its next commit has no parent,
	and mirroring it would drop every version of the backup, so nothing is pushed until the repository is restored from
	the backup (as the message says); --replace-backup replaces the history of the backup anyway, with a lease."""
	fake = FakeGit(tmp_path)
	app = fake.bare(push_app.REPO)
	backup = fake.bare(push_app.BACKUP, readme='a test\n')
	cache = str(tmp_path / 'cache')
	run = dict(cookies=cookies[0], backup_cookies=cookies[1], cache=cache, git=fake, root=fake.root)
	push_app.publish(files=FILES, **run)
	second = push_app.publish(files=FILES_2, **run)
	kept = _master(backup)
	assert len(kept['log']) == 2 and kept['commit'] == second['commit'] == _master(app)['commit']

	shutil.rmtree(app)
	fake.bare(push_app.REPO)  # recreated empty
	fake.calls = []
	with pytest.raises(push_app.PublishError, match=rf"the master of the backup .*{push_app.BACKUP} "
	                                                rf"\({kept['commit'][:7]}\) is not in the history .*nothing was "
	                                                r"pushed.*restore it from its backup first"):
		push_app.publish(files=FILES_2, **run)
	assert not fake.pushes() and _master(app) is None  # nothing pushed: neither the app nor the backup
	assert _master(backup)['log'] == kept['log'] and _master(backup)['commit'] == kept['commit']

	# restored as the message says, the next run only mirrors what there is
	fake(['push', '--quiet', push_app.HOST + push_app.REPO, f'{push_app.BACKUP_REF}:refs/heads/master'], cwd=cache,
	     cookies=cookies[0])
	again = push_app.publish(files=FILES_2, **run)
	assert not again['changed'] and again['mirror'] == 'up to date'
	assert _master(app)['commit'] == _master(backup)['commit'] == kept['commit']

	# a backup with versions that the repository does not have (another history): refused, unless --replace-backup
	other = _git('--git-dir', backup, 'commit-tree', '-m', 'another app', '-p', kept['commit'],
	             _git('--git-dir', backup, 'rev-parse', 'master^{tree}').strip()).strip()
	_git('--git-dir', backup, 'update-ref', 'refs/heads/master', other)
	with pytest.raises(push_app.PublishError, match='would lose versions of the backup'):
		push_app.publish(files=FILES, **run)
	assert _master(app)['commit'] == kept['commit'] and _master(backup)['commit'] == other
	replaced = push_app.publish(files=FILES, replace_backup=True, **run)
	assert replaced['mirror'] == 'replaced' and _master(backup)['commit'] == replaced['commit'] == _master(app)['commit']
	assert f'--force-with-lease=refs/heads/master:{other}' in fake.pushes()[-1][1]


@pytest.mark.skipif(not shutil.which('git'), reason='no git')
def test_push_app_needs_its_own_backup_for_another_repo(tmp_path, cookies, capsys):
	"""A test repository is never mirrored over the backup of the app: --backup is required with another --repo, and
	given the backup of the app, its versions are kept."""
	fake = FakeGit(tmp_path)
	fake.bare(push_app.REPO)
	backup = fake.bare(push_app.BACKUP, readme='a test\n')
	test_repo = fake.bare('users/someone/test-repo')
	run = dict(cookies=cookies[0], backup_cookies=cookies[1], git=fake, root=fake.root)
	push_app.publish(files=FILES, cache=str(tmp_path / 'cache'), **run)
	kept = _master(backup)
	fake.calls = []
	with pytest.raises(push_app.PublishError, match='no backup for users/someone/test-repo: give it with --backup'):
		push_app.publish(repo='users/someone/test-repo', files=FILES, cache=str(tmp_path / 'test'), **run)
	assert not fake.calls  # refused before anything
	with pytest.raises(push_app.PublishError, match='cannot be the repository itself'):
		push_app.publish(repo='users/someone/test-repo', backup='users/someone/test-repo', files=FILES,
		                 cache=str(tmp_path / 'test'), **run)
	with pytest.raises(push_app.PublishError, match='would lose versions of the backup'):
		push_app.publish(repo='users/someone/test-repo', backup=push_app.BACKUP, files=FILES_2,
		                 cache=str(tmp_path / 'test'), **run)
	assert _master(backup) and _master(backup)['commit'] == kept['commit'] and _master(test_repo) is None
	# a dry run of a test repository needs no backup
	dry = push_app.publish(repo='users/someone/test-repo', files=FILES, cache=str(tmp_path / 'test'), dry_run=True,
	                       **run)
	assert not dry['pushed'] and dry['backup'] is None
	with pytest.raises(SystemExit, match='push_app: no backup for users/someone/test-repo'):
		push_app.main(['--repo', 'users/someone/test-repo', '--cookies', cookies[0], '--backup-cookies', cookies[1],
		               '--cache', str(tmp_path / 'test')])
	assert _master(backup)['commit'] == kept['commit']
	capsys.readouterr()
	with pytest.raises(SystemExit):
		push_app.main(['--help'])
	usage = ' '.join(capsys.readouterr().out.split())
	assert f'(default: {push_app.BACKUP} with the default --repo; required with another --repo' in usage
	assert '--replace-backup' in usage


@pytest.mark.skipif(not shutil.which('git'), reason='no git')
def test_push_app_says_when_the_backup_was_not_mirrored(tmp_path, cookies):
	"""The backup refuses the push (a cookie of an account without write access): the repository of the app already
	has the commit, and the message says so and that running it again mirrors it, which it does."""
	fake = FakeGit(tmp_path)
	app = fake.bare(push_app.REPO)
	backup = fake.bare(push_app.BACKUP, readme='a test\n')
	hook = os.path.join(backup, 'hooks', 'pre-receive')
	with open(hook, 'w') as f:
		f.write('#!/bin/sh\necho "no write access" >&2\nexit 1\n')
	os.chmod(hook, 0o755)
	run = dict(cookies=cookies[0], backup_cookies=cookies[1], cache=str(tmp_path / 'cache'), git=fake, root=fake.root,
	           files=FILES)
	with pytest.raises(push_app.PublishError) as refused:
		push_app.publish(**run)
	commit = _master(app)['commit']
	text = str(refused.value)
	assert f'{push_app.HOST}{push_app.REPO} is already at {commit[:7]} (master)' in text
	assert f'its backup {push_app.HOST}{push_app.BACKUP} was not mirrored' in text and 'no write access' in text
	assert f'({cookies[1]}) at {push_app.HOST}new-password' in text and 'run push_app.py again' in text
	assert 'SECRET-COOKIE' not in text
	assert _master(backup)['log'] == ['README']
	os.remove(hook)
	again = push_app.publish(**run)
	assert not again['changed'] and again['commit'] == commit == _master(backup)['commit']



@pytest.mark.skipif(not shutil.which('git'), reason='no git')
def test_push_app_does_not_mirror_a_push_that_the_app_repository_refused(tmp_path, cookies):
	"""The repository of the app refuses the push (e.g. a file bigger than 512 KiB): the backup is not touched, so it
	never gets ahead of the repository of the app."""
	fake = FakeGit(tmp_path)
	app = fake.bare(push_app.REPO)
	backup = fake.bare(push_app.BACKUP, readme='a test\n')
	hook = os.path.join(app, 'hooks', 'pre-receive')
	with open(hook, 'w') as f:
		f.write('#!/bin/sh\necho "HTTP 400" >&2\nexit 1\n')
	os.chmod(hook, 0o755)
	with pytest.raises(push_app.PublishError):
		push_app.publish(cookies=cookies[0], backup_cookies=cookies[1], cache=str(tmp_path / 'cache'), git=fake,
		                 root=fake.root, files=FILES)
	assert _master(app) is None and _master(backup)['log'] == ['README']
	assert [c[1][1:] for c in fake.pushes()][:1] and all(push_app.BACKUP not in ' '.join(c[1]) for c in fake.pushes())

@pytest.mark.skipif(not shutil.which('git'), reason='no git')
def test_push_app_pushes_nothing_when_the_backup_cannot_be_read(tmp_path, cookies):
	"""The backup read with its own cookie before the first push: a cookie that does not work (here, no such
	repository) stops it before the repository of the app moves."""
	fake = FakeGit(tmp_path)
	app = fake.bare(push_app.REPO)  # and no backup
	with pytest.raises(push_app.PublishError, match=rf'cannot read the backup .*{push_app.BACKUP} with the cookie file '
	                                                rf'{re.escape(cookies[1])}, so nothing was pushed'):
		push_app.publish(cookies=cookies[0], backup_cookies=cookies[1], cache=str(tmp_path / 'cache'), git=fake,
		                 root=fake.root, files=FILES)
	assert not fake.pushes() and _master(app) is None


def test_push_app_asks_github_for_its_main(tmp_path, cookies):
	"""A local origin/main from before the merge is not main: the checkout is compared with the main GitHub has now."""
	run = dict(cookies=cookies[0], backup_cookies=cookies[1], cache=str(tmp_path / 'cache'), files=FILES)
	stale = FakeGit(tmp_path, main='f' * 40)
	stale.answers[('rev-parse', 'origin/main')] = HEAD + '\n'  # as the checkout last fetched it
	with pytest.raises(push_app.PublishError, match=r'not at main as GitHub has it \(fffffff\).*git pull'):
		push_app.publish(git=stale, root=stale.root, **run)
	assert ['ls-remote', 'origin', 'refs/heads/main'] in [c[1] for c in stale.calls]
	assert ['rev-parse', 'origin/main'] not in [c[1] for c in stale.calls]
	offline = FakeGit(tmp_path)
	offline.answers[('ls-remote', 'origin', 'refs/heads/main')] = push_app.PublishError('git ls-remote failed: no net')
	with pytest.raises(push_app.PublishError, match='cannot ask GitHub for its main .*no net.*--allow-any'):
		push_app.publish(git=offline, root=offline.root, **run)
	assert all(c[0] in ('rev-parse', 'status', 'ls-remote') for c in stale.calls + offline.calls)


@pytest.mark.skipif(not shutil.which('git'), reason='no git')
def test_push_app_relative_cache(tmp_path, cookies, monkeypatch, capsys):
	"""--cache relative to the current folder (here a bare name, without a folder), and a cache that cannot be made
	said without a traceback."""
	fake = FakeGit(tmp_path)
	fake.bare(push_app.REPO)
	work = tmp_path / 'work'
	work.mkdir()
	monkeypatch.chdir(work)
	done = push_app.publish(cookies=cookies[0], cache='gee-app', git=fake, root=fake.root, files=FILES, dry_run=True)
	assert os.path.realpath(done['clone']) == os.path.realpath(work / 'gee-app') and os.path.isabs(done['clone'])
	assert sorted(os.listdir(work / 'gee-app')) == ['.git', 'app', 'catalog_1', 'catalog_2']
	monkeypatch.setattr(push_app, 'run_git', FakeGit(tmp_path, root=push_app.ROOT))
	(work / 'a-file').write_text('', encoding='ascii')
	with pytest.raises(SystemExit, match='push_app: .*a-file'):
		push_app.main(['--cookies', cookies[0], '--cache', 'a-file/sub/gee-app', '--dry-run'])
