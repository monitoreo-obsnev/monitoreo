"""Check a branch of MonitorEO before its pull request (the skill monitoreo-change).

Run it from the root of the repository, with a Python that has earthengine-api (the environment of environment.yml):

    python .claude/skills/monitoreo-change/scripts/check_change.py [--no-fetch] [--tests] [--wiki ../monitoreo.wiki]

It reads and computes nothing in Earth Engine, and changes no file. It checks:

  - git: that the work is on a branch (not main), what is not committed, whether main moved since the branch started
    and whether the branch still merges into origin/main without conflicts;
  - the method: whether main changed this skill or CLAUDE.md since the branch started (then the branch follows old
    rules until main is merged in);
  - a release: that its tag is new and after the last one, and that no other release is in progress;
  - the catalog: references (with their datasets) and UDUNITS units of every variable, and, for the variables new on
    this branch, that the help of the tools, the Earth Engine app and the wiki know them;
  - the generated files: the Earth Engine app (gee/catalog.js) against the catalog, the R help (man/) against its
    roxygen, the references of .zenodo.json, the versions, the about of the QGIS plugin;
  - the changelog of README.md: its format, its last release against the versions and, if the branch changes what
    users get, its entries;
  - with --tests, the offline tests.

Each line starts with OK, WARN (to look at, or to say in the PR) or FAIL (to fix before the PR). The exit status is 1
if anything failed.

The workflow .github/workflows/tests.yml runs it on every pull request, on the merge of the branch with main that
GitHub makes (a detached HEAD: the branch is then $GITHUB_HEAD_REF).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.getcwd()
SRC = os.path.join(ROOT, 'src')
MAIN = 'origin/main'
results = {'OK': 0, 'WARN': 0, 'FAIL': 0}


def say(level, text):
	results[level] += 1
	print(f'{level:4}  {text}')


def git(*args, check=False):
	p = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True)
	if check and p.returncode:
		raise RuntimeError(p.stderr.strip())
	return p


def changed_since_base(paths):
	"""The files of PATHS changed on this branch (committed or not) since it left origin/main."""
	base = git('merge-base', 'HEAD', MAIN).stdout.strip()
	if not base:
		return set()
	files = set(git('diff', '--name-only', base, '--', *paths).stdout.split())
	return files


# Git ------------------------------------------------------------------------------------------------------------

def check_git(fetch):
	print('\n== Git')
	if fetch:
		p = git('fetch', '--prune', 'origin')  # --prune: forget the branches deleted on GitHub (merged ones)
		if p.returncode:
			say('WARN', f'git fetch failed, comparing with the last known {MAIN}: {p.stderr.strip()[:200]}')
	branch = branch_name()
	if in_pull_request():  # its own name may be main: a pull request from the main of a fork
		say('OK', f'the pull request of the branch {branch}')
	elif branch in ('main', 'master', ''):
		say('FAIL', f'you are on {branch or "a detached HEAD"}: work on a branch (git switch -c <topic> {MAIN})')
	else:
		say('OK', f'branch {branch}')
		remote = f'origin/{branch}'
		if (git('rev-parse', '--verify', '--quiet', remote).returncode == 0
		        and git('merge-base', '--is-ancestor', remote, 'HEAD').returncode == 1):
			say('WARN', f'{remote} has commits this branch does not: pushed from another computer, or someone else '
			            'is using the same name (git log HEAD..' + remote + ')')
	dirty = [line for line in git('status', '--porcelain').stdout.splitlines() if not line.endswith('.serena/')]
	if dirty:
		say('WARN', f'{len(dirty)} files not committed: ' + ', '.join(line[3:] for line in dirty[:8])
		    + (' ...' if len(dirty) > 8 else ''))
	ahead, behind = (git('rev-list', '--left-right', '--count', f'HEAD...{MAIN}').stdout.split() + ['?', '?'])[:2]
	say('OK' if ahead != '0' else 'WARN', f'{ahead} commits on the branch that {MAIN} does not have')
	if behind not in ('0', '?'):
		say('WARN', f'{MAIN} has {behind} commits the branch does not: merge it in (git merge {MAIN}), run the tests '
		            'again and look for semantic conflicts')
	p = git('merge-tree', '--write-tree', '--name-only', MAIN, 'HEAD')
	if p.returncode == 1:
		files = [f for f in p.stdout.splitlines()[1:] if f and not f.startswith(('Auto-merging', 'CONFLICT'))]
		say('FAIL', f'the branch conflicts with {MAIN} in: {", ".join(sorted(set(files)))}')
	elif p.returncode == 0:
		say('OK', f'merges into {MAIN} without text conflicts')
	else:
		say('WARN', f'could not test the merge ({p.stderr.strip()[:200]}): git 2.38 or newer is needed')


def in_pull_request():
	"""Whether this runs in a pull request of GitHub Actions, which checks out the merge of the branch with main (a
	detached HEAD, whose second parent is the head of the branch)."""
	return bool(os.environ.get('GITHUB_HEAD_REF', '').strip())


def branch_name():
	"""The branch checked out or, in a pull request of GitHub Actions, the branch of the pull request."""
	return git('branch', '--show-current').stdout.strip() or os.environ.get('GITHUB_HEAD_REF', '').strip()


def branch_head():
	"""The last commit of the branch: HEAD, or in a pull request of GitHub Actions the second parent of the merge."""
	if in_pull_request() and git('rev-parse', '--verify', '--quiet', 'HEAD^2').returncode == 0:
		return 'HEAD^2'
	return 'HEAD'


def branch_base():
	"""The commit of main where the branch started (its merge base), or ''."""
	return git('merge-base', branch_head(), MAIN).stdout.strip()


# The method -----------------------------------------------------------------------------------------------------

# the rules of the team: Claude reads them from the checkout, so a branch behind main follows the old ones
METHOD = ['.claude/skills/monitoreo-change', 'CLAUDE.md']


def check_method():
	print('\n== The method of the team (this skill and CLAUDE.md)')
	base = branch_base()
	if not base:
		say('WARN', f'no commit in common with {MAIN}: the method of the team was not compared')
		return
	files = git('diff', '--name-only', base, MAIN, '--', *METHOD).stdout.split()
	if files:
		say('FAIL', f'{MAIN} changed the method of the team since this branch started ({", ".join(files[:4])}'
		            f'{" ..." if len(files) > 4 else ""}): merge it in (git merge {MAIN}) and read the skill again, '
		            'as this branch still has the old rules')
	else:
		say('OK', f'the branch has the method of the team of {MAIN}')


# A release ------------------------------------------------------------------------------------------------------

PLUGIN_VERSION = ('qgis/monitoreo_qgis/metadata.txt', r'^version\s*=\s*(\S+)')
PACKAGE_VERSION = ('pyproject.toml', r'^version\s*=\s*"([^"]+)"')


def numbers(version):
	"""(0, 3, 76) of '0.3.76', or None."""
	return tuple(int(n) for n in version.split('.')) if version and re.fullmatch(r'\d+(\.\d+)*', version) else None


def version_at(rev, where):
	"""The version of WHERE (file, pattern) at the commit REV, or in the working tree if REV is None."""
	text = read(where[0]) if rev is None else git('show', f'{rev}:{where[0]}').stdout
	m = re.search(where[1], text or '', re.M)
	return m.group(1) if m else None


def started(rev):
	"""When the branch REV started: the time of its first commit that main has not, or None."""
	first = git('log', '--reverse', '--format=%ct', f'{MAIN}..{rev}').stdout.split()
	return int(first[0]) if first else None


def check_release():
	"""A branch that changes the versions since it started (a release, references/release.md): both go up, above
	those of main, its tag is new and after the last one, and no other release started before it is in progress (two
	at once would take the same versions and tag)."""
	head, base = branch_head(), branch_base()
	if not base:
		return
	now = None if head == 'HEAD' else head  # in a pull request of GitHub Actions, the head of the branch
	versions = {name: (version_at(now, where), version_at(base, where), version_at(MAIN, where))
	            for name, where in (('QGIS plugin', PLUGIN_VERSION), ('package', PACKAGE_VERSION))}
	if all(v[0] == v[1] for v in versions.values()):
		if branch_name().startswith('release-'):  # e.g. main merged in, with the same versions released by someone else
			print('\n== Release')
			say('FAIL', f'the branch {branch_name()} does not raise the versions since it started (main has the plugin '
			            f'{versions["QGIS plugin"][2]} and the package {versions["package"][2]}): if someone else made '
			            'this release, raise them again from those of main')
		return  # not a release: the branch does not change the versions
	print('\n== Release')
	if None in (numbers(v) for vs in versions.values() for v in vs):
		say('WARN', f'versions that are not numbers, not compared: {versions}')
		return
	behind = [f'{k} {v} (main {m})' for k, (v, b, m) in versions.items() if v != b and numbers(v) <= numbers(m)]
	same = [f'{k} {v}' for k, (v, b, m) in versions.items() if v == b]
	if behind:
		say('FAIL', 'versions not above those of main: ' + ', '.join(behind) + f'. Merge {MAIN} and raise them from '
		            'its versions')
	if same:
		say('WARN', f'only one version goes up ({", ".join(same)} stays): a release raises both '
		            '(references/release.md)')
	plugin, plugin_base, _ = versions['QGIS plugin']
	if plugin == plugin_base:
		say('WARN', 'no new tag: the tag of a release is the version of the QGIS plugin, which stays')
	else:
		tags = {t: numbers(t[1:]) for t in git('tag', '--list', 'v*').stdout.split() if numbers(t[1:])}
		tag, last = f'v{plugin}', (max(tags, key=tags.get) if tags else None)
		if tag in tags:
			say('FAIL', f'the tag {tag} exists already: someone else made that release. Merge {MAIN} and raise the '
			            'versions again')
		elif last and numbers(plugin) <= tags[last]:
			say('FAIL', f'{tag} is not after the last tag, {last}: raise the plugin version from {last}')
		else:
			say('OK', f'the tag {tag} is new and after the last one ({last or "none"})')
	mine = f'origin/{branch_name()}'
	mine_started = started(head) or float('inf')
	before, after = [], []
	for ref in git('for-each-ref', '--format=%(refname:short)', 'refs/remotes/origin/release-*').stdout.split():
		if git('merge-base', '--is-ancestor', ref, MAIN).returncode == 0:
			continue  # a release merged already
		if ref == mine and git('merge-base', '--is-ancestor', ref, head).returncode == 0:
			continue  # this branch, pushed (not someone else's branch with the same name)
		(before if ((started(ref) or 0), ref) < (mine_started, mine) else after).append(ref)
	if before:
		say('FAIL', f'another release started before this one is in progress ({", ".join(before)}): two at once take '
		            f'the same versions. Wait for its merge, then merge {MAIN} into this branch and raise the versions '
		            'again; if it was abandoned, ask its author before deleting it')
	if after:
		say('WARN', f'another release started after this one ({", ".join(after)}): it waits for this one')
	if not before and not after:
		say('OK', 'no other release in progress')


# Catalog --------------------------------------------------------------------------------------------------------

def variables_of(src):
	"""[(ref, index, sensor, unit, vname_en)] of the catalog of the package in SRC, in a separate Python."""
	code = ('import json, sys; from monitoreo import catalog; '
	        'print(json.dumps([[e["ref"], e["index"], e["sensor"], e.get("unit"), e.get("vname_en")] '
	        'for e in catalog.variables()]))')
	p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
	                   env=dict(os.environ, PYTHONPATH=src, PYTHONNOUSERSITE='1'))
	if p.returncode:
		raise RuntimeError(p.stderr.strip().splitlines()[-1] if p.stderr.strip() else 'unknown error')
	return [tuple(v) for v in json.loads(p.stdout)]


def main_variables():
	"""The variables of the catalog of origin/main, or None."""
	tmp = tempfile.mkdtemp(prefix='monitoreo-main-')
	try:
		archive = subprocess.run(['git', 'archive', MAIN, 'src/monitoreo'], cwd=ROOT, capture_output=True)
		if archive.returncode:
			return None
		subprocess.run(['tar', '-x', '-C', tmp], input=archive.stdout, check=True)
		return variables_of(os.path.join(tmp, 'src'))
	except Exception:
		return None
	finally:
		shutil.rmtree(tmp, ignore_errors=True)


def mentioned(text, index, name):
	"""Whether TEXT names the variable by its index (as a word) or its English name."""
	if re.search(rf'(?<![A-Za-z0-9_]){re.escape(index)}(?![A-Za-z0-9_])', text):
		return True
	return bool(name) and name.lower() in text.lower()


def check_catalog(wiki):
	print('\n== Catalog')
	sys.path.insert(0, SRC)
	try:
		from monitoreo import catalog, references
	except Exception as e:  # noqa: BLE001
		say('FAIL', f'cannot import monitoreo from src/ ({type(e).__name__}: {e}): use the environment of '
		            'environment.yml')
		return
	cat = catalog.load()
	bib, datasets = references.bibliography(), cat['datasets']
	problems = []
	for e in catalog.variables():
		where = f"{e['index']} ({e['sensor']}, ref {e['ref']})"
		refs = e.get('references')
		if refs is None:
			problems.append(f'{where}: no field references')
		elif not refs and not (e.get('notes') or {}).get('references'):
			problems.append(f'{where}: no references, and no notes.references saying what is missing')
		elif set(refs) - set(bib):
			problems.append(f'{where}: references not in the bibliography: {sorted(set(refs) - set(bib))}')
		for col in references.datasets(e['col']):
			if col not in datasets:
				problems.append(f'{where}: the Earth Engine dataset {col} is not in datasets (its citation and credit)')
		unit = str(e.get('unit') or '')
		if 'º' in unit:
			problems.append(f'{where}: unit {unit} uses the ordinal º, not the degree sign °')
		elif not catalog.udunits(unit) and unit not in getattr(catalog, 'NO_UDUNITS', ()):  # e.g. class codes, no unit
			problems.append(f'{where}: unit {unit} has no UDUNITS name in catalog.UDUNITS')
		if hasattr(catalog, 'THEMES') and not e.get('theme'):
			problems.append(f'{where}: no theme: add {e["index"]} to the indices of its theme in catalog.THEMES')
	for p in problems:
		say('FAIL', p)
	if not problems:
		say('OK', f'{len(catalog.variables())} variables with references, datasets, UDUNITS units and themes')
	for t in getattr(catalog, 'THEMES', []):
		if not any(e['index'] in t['indices'] for e in catalog.variables()):
			say('WARN', f"the theme {t['key']} has no variable of the catalog")

	now = [(e['ref'], e['index'], e['sensor'], e.get('unit'), e.get('vname_en')) for e in catalog.variables()]
	before = main_variables()
	if before is None:
		say('WARN', f'could not read the catalog of {MAIN} to find the new variables')
		new = []
	else:
		old = {(v[1], v[2]) for v in before}
		new = [v for v in now if (v[1], v[2]) not in old]
		say('OK', f'new variables on this branch: ' + (', '.join(f'{i} ({s})' for _, i, s, _, _ in new) or 'none'))
	check_gee(now)
	if new:
		texts = {
			'MCP server (mcp_server.py INSTRUCTIONS)': 'src/monitoreo/mcp_server.py',
			'assistant (assistant.py PROMPT)': 'src/monitoreo/assistant.py',
			'QGIS plugin (metadata.txt about)': 'qgis/monitoreo_qgis/metadata.txt',
			'R package (DESCRIPTION)': 'r/monitoreo/DESCRIPTION',
		}
		for label, path in texts.items():
			text = open(os.path.join(ROOT, path), encoding='utf-8').read()
			missing = [f'{i} ({s})' for _, i, s, _, n in new if not mentioned(text, i, n)]
			if missing:
				say('WARN', f'the help of the {label} does not name: {", ".join(missing)}')
		test = open(os.path.join(ROOT, 'tests', 'test_offline.py'), encoding='utf-8').read()
		m = re.search(r'assert len\(entries\) == (\d+)', test)
		if m and int(m.group(1)) != len(now):
			say('FAIL', f'tests/test_offline.py::test_catalog expects {m.group(1)} variables, the catalog has {len(now)}')
	check_wiki(wiki, now, new)


def check_gee(now):
	path = os.path.join(ROOT, 'gee', 'catalog.js')
	try:
		text = open(path, encoding='utf-8').read()
		app = json.loads(text[text.index('{', text.index('var CATALOG')):text.rindex('};') + 1])['variables']
	except (OSError, ValueError) as e:
		say('WARN', f'cannot read gee/catalog.js: {e}')
		return
	in_app = {(v['index'], v['sensor']): v for v in app}
	missing = [f'{i} ({s})' for _, i, s, _, _ in now if (i, s) not in in_app]
	units = [f"{i} ({s}): {in_app[(i, s)].get('unit')} in the app, {u} in the catalog" for _, i, s, u, _ in now
	         if (i, s) in in_app and in_app[(i, s)].get('unit') != u]
	if missing:
		say('FAIL', 'the Earth Engine app does not have: ' + ', '.join(missing)
		    + ' (python gee/build.py --project <p>, which computes in Earth Engine)')
	if units:
		say('WARN', 'the Earth Engine app is out of date: ' + '; '.join(units) + ' (rebuild it with gee/build.py)')
	if not missing and not units:
		say('OK', f'the Earth Engine app has the {len(now)} variables, with the same units')
	inputs = changed_since_base(['src/monitoreo/catalog.json', 'src/monitoreo/catalog.py', 'src/monitoreo/about.py',
	                             'gee/core.js', 'gee/ui.js'])
	outputs = changed_since_base(['gee/catalog.js', 'gee/monitoreo_app.js'])
	if inputs and not outputs:
		say('WARN', f'{", ".join(sorted(inputs))} changed but gee/catalog.js and gee/monitoreo_app.js did not: '
		            'rebuild the app (gee/build.py) or say in the PR that it is pending')


def check_wiki(wiki, now, new):
	print('\n== Wiki')
	if not wiki or not os.path.isdir(wiki):
		say('WARN', f'no clone of the wiki at {wiki} (git clone git@github.com:monitoreo-obsnev/monitoreo.wiki.git): '
		            'its pages are not checked')
		return
	branch = git('branch', '--show-current').stdout.strip()
	wiki_branches = subprocess.run(['git', 'branch', '--list', branch], cwd=wiki, capture_output=True, text=True).stdout
	if branch and branch not in ('main', 'master') and wiki_branches.strip():
		say('OK', f'the wiki has a branch {branch}')
	elif new:
		say('WARN', f'the wiki has no branch {branch}: document the change there (Spanish and English pages)')
	for page in ('Conceptos.md', 'Concepts.md'):
		path = os.path.join(wiki, page)
		if not os.path.exists(path):
			continue
		text = open(path, encoding='utf-8').read()
		missing = sorted({i for _, i, _, _, _ in now if not mentioned(text, i, None)})  # by index: its table
		level = 'FAIL' if any(i in missing for _, i, _, _, _ in new) else 'WARN'
		if missing:
			say(level, f'{page} (wiki branch {current_branch(wiki)}) does not name: {", ".join(missing)}')
		else:
			say('OK', f'{page} names every variable')


def current_branch(repo):
	return subprocess.run(['git', 'branch', '--show-current'], cwd=repo, capture_output=True, text=True).stdout.strip()


# Generated files ------------------------------------------------------------------------------------------------

def check_generated():
	print('\n== Generated files and metadata')
	try:
		sys.path.insert(0, SRC)
		from monitoreo import references
		z = json.load(open(os.path.join(ROOT, '.zenodo.json'), encoding='utf-8'))
		if z.get('references') == references.bibliography_texts():
			say('OK', '.zenodo.json has the references of the catalog')
		else:
			say('FAIL', '.zenodo.json is out of date: regenerate its references (references/new-variable.md)')
		if any('orcid' not in c for c in z.get('contributors', [])):
			say('FAIL', '.zenodo.json: a contributor without ORCID')
	except Exception as e:  # noqa: BLE001
		say('WARN', f'.zenodo.json not checked: {e}')
	versions = {
		'pyproject.toml': re.search(r'^version\s*=\s*"([^"]+)"', read('pyproject.toml'), re.M),
		'src/monitoreo/__init__.py': re.search(r"__version__\s*=\s*['\"]([^'\"]+)", read('src/monitoreo/__init__.py')),
		'r/monitoreo/DESCRIPTION': re.search(r'^Version:\s*(\S+)', read('r/monitoreo/DESCRIPTION'), re.M),
	}
	found = {k: m.group(1) for k, m in versions.items() if m}
	if len(set(found.values())) == 1 and len(found) == 3:
		say('OK', f'package version {next(iter(found.values()))} in its three files')
	else:
		say('FAIL', f'the versions of the package differ: {found}')
	about = read('qgis/monitoreo_qgis/metadata.txt')
	if '%' in about:
		say('FAIL', 'qgis/monitoreo_qgis/metadata.txt has a % sign, which plugins.qgis.org cannot read')
	check_r()


def check_changelog():
	"""The changelog of README.md (.github/changelog.py): its format, the versions of its last release and, if the
	branch changes what users get, an entry for it."""
	print('\n== Changelog (README.md)')
	try:
		sys.path.insert(0, os.path.join(ROOT, '.github'))
		import changelog
	except ImportError as e:
		say('WARN', f'the changelog not checked: {e}')
		return
	text = read('README.md')
	found = changelog.problems(text)
	for p in found:
		say('FAIL', p)
	if found:
		return
	log = changelog.parse(text)
	say('OK', f'the changelog has the release {log["releases"][0]["tag"]} of the versions and date of the files')
	users = sorted(changed_since_base(['src/monitoreo', 'qgis/monitoreo_qgis', 'r/monitoreo', 'gee']))
	base = git('merge-base', 'HEAD', MAIN).stdout.strip()
	def entries(text):
		try:
			lg = changelog.parse(text)
		except ValueError:
			return None
		lists = [lg['unreleased'] or []] + [r['entries'] for r in lg['releases']]
		return [(e['tools'], e['fix'], e['text']) for entries in lists for e in entries]

	if users and entries(git('show', f'{base}:README.md').stdout) == entries(text):
		say('WARN', f'the branch changes what users get ({", ".join(users[:4])}{" ..." if len(users) > 4 else ""}) '
		            'but not the changelog: add its entries under "### Unreleased" in README.md, or say in the PR '
		            'why users do not notice it')
	elif users:
		say('OK', 'the changelog has the entries of the branch')


def read(path):
	try:
		return open(os.path.join(ROOT, path), encoding='utf-8').read()
	except OSError:
		return ''


def check_r():
	"""The R help (man/, NAMESPACE) against its roxygen: regenerated in a copy, if R and roxygen2 are there."""
	rscript = shutil.which('Rscript')
	if not rscript:
		if changed_since_base(['r/monitoreo/R']) and not changed_since_base(['r/monitoreo/man']):
			say('WARN', 'the R code changed but not man/: regenerate the help with roxygen2')
		return
	tmp = tempfile.mkdtemp(prefix='monitoreo-r-')
	try:
		copy = os.path.join(tmp, 'monitoreo')
		shutil.copytree(os.path.join(ROOT, 'r', 'monitoreo'), copy)
		p = subprocess.run([rscript, '-e', 'suppressMessages(roxygen2::roxygenise(".", roclets = c("rd", "namespace")))'],
		                   cwd=copy, capture_output=True, text=True)
		if p.returncode:
			say('WARN', 'could not run roxygen2 to check the R help: '
			            + (p.stderr.strip().splitlines() or ['?'])[-1][:200])
			return
		stale = []
		for sub in ('man', 'NAMESPACE'):
			d = subprocess.run(['diff', '-rq', os.path.join(ROOT, 'r', 'monitoreo', sub), os.path.join(copy, sub)],
			                   capture_output=True, text=True).stdout
			stale += [line.split()[1] if line.startswith('Files') else line for line in d.splitlines()]
		if stale:
			say('FAIL', 'the R help is out of date (Rscript -e \'roxygen2::roxygenise("r/monitoreo", roclets = '
			            'c("rd", "namespace"))\'): ' + ', '.join(os.path.relpath(s, ROOT) if s.startswith(ROOT) else s
			                                              for s in stale[:6]))
		else:
			say('OK', 'the R help (man/, NAMESPACE) matches its roxygen')
	finally:
		shutil.rmtree(tmp, ignore_errors=True)


# Tests ----------------------------------------------------------------------------------------------------------

def run_tests():
	print('\n== Offline tests')
	# -m 'not ee': never the tests that compute in Earth Engine, even with EE_PROJECT exported
	p = subprocess.run([sys.executable, '-m', 'pytest', 'tests', '-q', '-m', 'not ee', '-p', 'no:cacheprovider'],
	                   cwd=ROOT,
	                   capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=SRC, PYTHONNOUSERSITE='1'))
	last = (p.stdout.strip().splitlines() or ['no output'])[-1]
	say('OK' if p.returncode == 0 else 'FAIL', f'pytest tests: {last}')


def main():
	global MAIN
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument('--no-fetch', action='store_true', help=f'do not fetch origin before comparing with {MAIN}')
	parser.add_argument('--tests', action='store_true', help='also run the offline tests')
	parser.add_argument('--wiki', default=os.path.join('..', 'monitoreo.wiki'), help='the clone of the wiki')
	parser.add_argument('--base', default=MAIN, help='the branch to compare with (default: origin/main)')
	args = parser.parse_args()
	MAIN = args.base
	if not os.path.exists(os.path.join(ROOT, 'src', 'monitoreo', 'catalog.json')):
		sys.exit('run it from the root of the repository monitoreo')
	check_git(not args.no_fetch)
	check_method()
	check_release()
	check_catalog(os.path.abspath(args.wiki))
	check_generated()
	check_changelog()
	if args.tests:
		run_tests()
	print(f"\n{results['OK']} OK, {results['WARN']} WARN, {results['FAIL']} FAIL")
	sys.exit(1 if results['FAIL'] else 0)


if __name__ == '__main__':
	main()
