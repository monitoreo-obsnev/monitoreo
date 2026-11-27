"""The checker of the skill monitoreo-change (.claude/skills/monitoreo-change/scripts/check_change.py) and the workflow
Tests that runs it on every pull request, with git repositories in a temporary folder: no network, no Earth Engine.

Three people change MonitorEO at the same time (2026-11-27), so the checker looks at what one of them cannot see from
their own branch: that main changed the method of the team since the branch started, and a release whose tag exists
already, is not after the last one, or starts while another one is in progress."""

import importlib.util
import os
import shutil
import subprocess

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, '.claude', 'skills', 'monitoreo-change', 'scripts', 'check_change.py')
WORKFLOW = os.path.join(ROOT, '.github', 'workflows', 'tests.yml')
SKILL = os.path.join('.claude', 'skills', 'monitoreo-change', 'SKILL.md')

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='the checker reads git')

GIT = {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 'MonitorEO tests',
       'GIT_AUTHOR_EMAIL': 'tests@example.org', 'GIT_COMMITTER_NAME': 'MonitorEO tests',
       'GIT_COMMITTER_EMAIL': 'tests@example.org'}


def git(cwd, *args, **env):
	return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True,
	                      env=dict(os.environ, **GIT, **env)).stdout.strip()


def write(root, path, text):
	full = os.path.join(root, path)
	os.makedirs(os.path.dirname(full), exist_ok=True)
	with open(full, 'w', encoding='utf-8') as f:
		f.write(text)


def versions(root, plugin, package):
	write(root, 'qgis/monitoreo_qgis/metadata.txt', f'[general]\nname=MonitorEO\nversion={plugin}\n')
	write(root, 'pyproject.toml', f'[project]\nname = "monitoreo"\nversion = "{package}"\n')


class Repos:
	"""A repository of GitHub (a bare origin) with main at the plugin 0.3.76 (tag v0.3.76) and the package 0.3.86, and
	two clones of it: mine (the checker looks at it) and that of another developer."""

	def __init__(self, tmp):
		self.origin = str(tmp / 'origin.git')
		git(tmp, 'init', '--quiet', '--bare', '-b', 'main', self.origin)
		self.mine = str(tmp / 'mine')
		git(tmp, 'init', '--quiet', '-b', 'main', self.mine)
		write(self.mine, SKILL, '# Changing MonitorEO\n')
		write(self.mine, 'CLAUDE.md', '# MonitorEO\n')
		versions(self.mine, '0.3.76', '0.3.86')
		git(self.mine, 'add', '-A')
		git(self.mine, 'commit', '--quiet', '-m', 'MonitorEO')
		git(self.mine, 'tag', 'v0.3.76')
		git(self.mine, 'remote', 'add', 'origin', self.origin)
		git(self.mine, 'push', '--quiet', 'origin', 'main', '--tags')
		git(self.mine, 'fetch', '--quiet', 'origin')
		self.other = str(tmp / 'other')
		git(tmp, 'clone', '--quiet', self.origin, self.other)

	def commit(self, root, message, date=None):
		git(root, 'add', '-A')
		env = {'GIT_AUTHOR_DATE': date, 'GIT_COMMITTER_DATE': date} if date else {}
		git(root, 'commit', '--quiet', '-m', message, **env)

	def fetch(self):
		git(self.mine, 'fetch', '--quiet', '--prune', '--tags', 'origin')

	def release(self, root, plugin, package, branch=None, date=None):
		"""A branch release-<plugin> from origin/main that raises the versions."""
		git(root, 'switch', '--quiet', '-c', branch or f'release-{plugin}', 'origin/main')
		versions(root, plugin, package)
		self.commit(root, f'monitoreo {package} and QGIS plugin {plugin}', date)

	def merge_release(self, plugin, package):
		"""Another developer makes the release PLUGIN and merges it into main, with its tag."""
		git(self.other, 'fetch', '--quiet', 'origin')
		self.release(self.other, plugin, package, branch=f'release-{plugin}-other')
		git(self.other, 'switch', '--quiet', 'main')
		git(self.other, 'merge', '--quiet', '--ff-only', 'origin/main')
		git(self.other, 'merge', '--quiet', '--no-ff', '-m', 'Merge pull request', f'release-{plugin}-other')
		git(self.other, 'tag', f'v{plugin}')
		git(self.other, 'push', '--quiet', 'origin', 'main', f'v{plugin}')
		self.fetch()

	def github_merge(self, branch):
		"""What GitHub Actions checks out in a pull request: the merge of BRANCH into main, detached."""
		git(self.mine, 'switch', '--quiet', '--detach', 'origin/main')
		git(self.mine, 'merge', '--quiet', '--no-ff', '-m', 'Merge into main', branch)


@pytest.fixture
def repos(tmp_path, monkeypatch):
	for k, v in GIT.items():
		monkeypatch.setenv(k, v)
	monkeypatch.delenv('GITHUB_HEAD_REF', raising=False)
	return Repos(tmp_path)


@pytest.fixture
def checker(repos):
	spec = importlib.util.spec_from_file_location('check_change_under_test', SCRIPT)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	module.ROOT = repos.mine
	module.MAIN = 'origin/main'
	return module


def lines(capsys, level):
	return [line for line in capsys.readouterr().out.splitlines() if line.startswith(level)]


# The method of the team ------------------------------------------------------------------------------------------

def test_a_branch_with_the_method_of_main(repos, checker, capsys):
	git(repos.mine, 'switch', '--quiet', '-c', 'ndmi', 'origin/main')
	checker.check_method()
	assert checker.results['FAIL'] == 0 and lines(capsys, 'OK')


def test_main_changed_the_skill_since_the_branch_started(repos, checker, capsys):
	"""Claude reads the skill from the checkout: a branch that started before main changed it has the old rules
	until main is merged in."""
	git(repos.mine, 'switch', '--quiet', '-c', 'ndmi', 'origin/main')
	write(repos.other, SKILL, '# Changing MonitorEO\n\nA new rule of the team.\n')
	repos.commit(repos.other, 'A new rule')
	git(repos.other, 'push', '--quiet', 'origin', 'main')
	repos.fetch()
	checker.check_method()
	fails = lines(capsys, 'FAIL')
	assert len(fails) == 1 and 'SKILL.md' in fails[0] and 'git merge origin/main' in fails[0]
	git(repos.mine, 'merge', '--quiet', 'origin/main')
	checker.check_method()
	assert checker.results['FAIL'] == 1 and lines(capsys, 'OK')  # the one before the merge


def test_other_changes_of_main_are_not_the_method(repos, checker, capsys):
	git(repos.mine, 'switch', '--quiet', '-c', 'ndmi', 'origin/main')
	write(repos.other, 'src/monitoreo/x.py', 'x = 1\n')
	repos.commit(repos.other, 'Code')
	git(repos.other, 'push', '--quiet', 'origin', 'main')
	repos.fetch()
	checker.check_method()
	assert checker.results['FAIL'] == 0


# A release -------------------------------------------------------------------------------------------------------

def test_a_branch_that_is_not_a_release_says_nothing(repos, checker, capsys):
	git(repos.mine, 'switch', '--quiet', '-c', 'ndmi', 'origin/main')
	checker.check_release()
	assert capsys.readouterr().out == '' and sum(checker.results.values()) == 0


def test_a_release_with_a_new_tag(repos, checker, capsys):
	repos.release(repos.mine, '0.3.77', '0.3.87')
	checker.check_release()
	assert checker.results['FAIL'] == 0 and checker.results['WARN'] == 0
	assert any('v0.3.77 is new' in line for line in lines(capsys, 'OK'))


def test_the_tag_exists_already(repos, checker, capsys):
	"""Someone else made the release 0.3.77 (its tag is on GitHub) while this branch was being prepared."""
	repos.release(repos.mine, '0.3.77', '0.3.87')
	git(repos.other, 'tag', 'v0.3.77')
	git(repos.other, 'push', '--quiet', 'origin', 'v0.3.77')
	repos.fetch()
	checker.check_release()
	assert any('v0.3.77 exists already' in line for line in lines(capsys, 'FAIL'))


def test_the_tag_is_not_after_the_last_one(repos, checker, capsys):
	repos.release(repos.mine, '0.3.77', '0.3.87')
	git(repos.other, 'tag', 'v0.3.80')
	git(repos.other, 'push', '--quiet', 'origin', 'v0.3.80')
	repos.fetch()
	checker.check_release()
	assert any('not after the last tag, v0.3.80' in line for line in lines(capsys, 'FAIL'))


def test_another_release_is_in_progress(repos, checker, capsys):
	"""Two releases at once would take the same versions and tag: the branch release-* that another developer started
	first stops the second one, which waits for it."""
	repos.release(repos.other, '0.3.77', '0.3.87', date='2026-11-27T10:00:00')
	git(repos.other, 'push', '--quiet', 'origin', 'release-0.3.77')
	repos.release(repos.mine, '0.3.77', '0.3.87', branch='release-0.3.77-mine', date='2026-11-27T10:05:00')
	repos.fetch()
	checker.check_release()
	fails = lines(capsys, 'FAIL')
	assert len(fails) == 1 and 'origin/release-0.3.77' in fails[0] and 'started before this one' in fails[0]


def test_the_first_of_two_releases_goes_on(repos, checker, capsys):
	"""Both releases pushed within minutes: only the second one stops, so that they cannot block each other."""
	repos.release(repos.other, '0.3.77', '0.3.87', branch='release-0.3.77-other', date='2026-11-27T10:05:00')
	git(repos.other, 'push', '--quiet', 'origin', 'release-0.3.77-other')
	repos.release(repos.mine, '0.3.77', '0.3.87', date='2026-11-27T10:00:00')
	git(repos.mine, 'push', '--quiet', 'origin', 'release-0.3.77')
	repos.fetch()
	checker.check_release()
	assert checker.results['FAIL'] == 0
	assert any('started after this one' in line for line in lines(capsys, 'WARN'))


def test_someone_else_pushed_a_release_branch_with_my_name(repos, checker, capsys):
	"""Both took the name release-0.3.77; theirs is on GitHub and mine is not pushed yet: theirs is another release,
	not mine."""
	repos.release(repos.other, '0.3.77', '0.3.87', date='2026-11-27T10:00:00')
	git(repos.other, 'push', '--quiet', 'origin', 'release-0.3.77')
	repos.release(repos.mine, '0.3.77', '0.3.87', date='2026-11-27T10:05:00')
	repos.fetch()
	checker.check_release()
	assert any('origin/release-0.3.77' in line and 'started before' in line for line in lines(capsys, 'FAIL'))


def test_a_release_branch_that_raises_nothing(repos, checker, capsys):
	"""Someone else merged the same release first, and merging main into this branch left its versions as main's."""
	repos.release(repos.mine, '0.3.77', '0.3.87', date='2026-11-27T09:00:00')
	repos.merge_release('0.3.77', '0.3.87')
	git(repos.mine, 'merge', '--quiet', '-m', 'Merge main', 'origin/main')
	checker.check_release()
	assert any('does not raise the versions' in line for line in lines(capsys, 'FAIL'))


def test_a_merged_release_branch_left_on_github_is_not_in_progress(repos, checker, capsys):
	repos.merge_release('0.3.77', '0.3.87')
	git(repos.other, 'push', '--quiet', 'origin', 'release-0.3.77-other')  # not deleted after its merge
	repos.fetch()
	repos.release(repos.mine, '0.3.78', '0.3.88')
	checker.check_release()
	assert checker.results['FAIL'] == 0, capsys.readouterr().out


def test_a_branch_behind_a_release_of_someone_else_is_not_a_release(repos, checker, capsys):
	"""Someone else released 0.3.77 after this branch started: the branch does not change the versions, so the
	checker says nothing about releases (it must not ask to raise them)."""
	git(repos.mine, 'switch', '--quiet', '-c', 'ndmi', 'origin/main')
	write(repos.mine, 'src/monitoreo/ndmi.py', 'x = 1\n')
	repos.commit(repos.mine, 'NDMI')
	repos.merge_release('0.3.77', '0.3.87')
	checker.check_release()
	assert capsys.readouterr().out == '' and sum(checker.results.values()) == 0


def test_a_release_behind_another_release(repos, checker, capsys):
	"""This release took 0.3.77, but someone else merged 0.3.77 first."""
	repos.release(repos.mine, '0.3.77', '0.3.87', date='2026-11-27T09:00:00')  # not the same commit as theirs
	repos.merge_release('0.3.77', '0.3.87')
	checker.check_release()
	fails = lines(capsys, 'FAIL')
	assert any('not above those of main' in line for line in fails)
	assert any('v0.3.77 exists already' in line for line in fails)


def test_my_own_release_branch_on_github_is_not_another_release(repos, checker, capsys):
	repos.release(repos.mine, '0.3.77', '0.3.87')
	git(repos.mine, 'push', '--quiet', 'origin', 'release-0.3.77')
	repos.fetch()
	checker.check_release()
	assert checker.results['FAIL'] == 0


def test_only_one_version_goes_up(repos, checker, capsys):
	repos.release(repos.mine, '0.3.77', '0.3.86')
	checker.check_release()
	assert checker.results['FAIL'] == 0
	assert any('only one version goes up' in line for line in lines(capsys, 'WARN'))


def test_only_the_package_goes_up(repos, checker, capsys):
	"""Without a new version of the plugin there is no new tag: a warning, not that someone made the release."""
	repos.release(repos.mine, '0.3.76', '0.3.87', branch='package-0.3.87')
	checker.check_release()
	warns = lines(capsys, 'WARN')
	assert checker.results['FAIL'] == 0
	assert any('only one version goes up' in w for w in warns) and any('no new tag' in w for w in warns)


def test_a_version_lower_than_main(repos, checker, capsys):
	repos.release(repos.mine, '0.3.77', '0.3.85')
	checker.check_release()
	assert any('not above those of main: package 0.3.85' in line for line in lines(capsys, 'FAIL'))


# On GitHub Actions -----------------------------------------------------------------------------------------------

def test_in_a_pull_request_of_github_actions(repos, checker, capsys, monkeypatch):
	"""GitHub checks out the merge of the branch with main, without a branch (a detached HEAD): the branch of the pull
	request is $GITHUB_HEAD_REF, and its own branch on GitHub is not another release."""
	repos.release(repos.mine, '0.3.77', '0.3.87')
	git(repos.mine, 'push', '--quiet', 'origin', 'release-0.3.77')
	repos.fetch()
	repos.github_merge('release-0.3.77')
	monkeypatch.setenv('GITHUB_HEAD_REF', 'release-0.3.77')
	checker.check_git(False)
	checker.check_method()
	checker.check_release()
	out = capsys.readouterr().out
	assert 'OK    the pull request of the branch release-0.3.77' in out and '== Release' in out
	assert checker.results['FAIL'] == 0, out


def test_in_github_actions_main_changed_the_skill(repos, checker, capsys, monkeypatch):
	"""On the merge that GitHub checks out, main is always in: the branch is its second parent."""
	git(repos.mine, 'switch', '--quiet', '-c', 'ndmi', 'origin/main')
	write(repos.mine, 'src/monitoreo/ndmi.py', 'x = 1\n')
	repos.commit(repos.mine, 'NDMI')
	write(repos.other, SKILL, '# Changing MonitorEO\n\nA new rule of the team.\n')
	repos.commit(repos.other, 'A new rule')
	git(repos.other, 'push', '--quiet', 'origin', 'main')
	repos.fetch()
	repos.github_merge('ndmi')
	monkeypatch.setenv('GITHUB_HEAD_REF', 'ndmi')
	checker.check_method()
	checker.check_release()  # a branch behind main is not a release
	assert checker.results['FAIL'] == 1 and any('SKILL.md' in line for line in lines(capsys, 'FAIL'))


def test_a_pull_request_from_the_main_of_a_fork(repos, checker, capsys, monkeypatch):
	git(repos.mine, 'switch', '--quiet', '-c', 'fork-main', 'origin/main')
	write(repos.mine, 'src/monitoreo/x.py', 'x = 1\n')
	repos.commit(repos.mine, 'A contribution')
	repos.github_merge('fork-main')
	monkeypatch.setenv('GITHUB_HEAD_REF', 'main')
	checker.check_git(False)
	assert checker.results['FAIL'] == 0


def test_a_detached_head_outside_github_actions_fails(repos, checker, capsys):
	git(repos.mine, 'switch', '--quiet', '--detach', 'origin/main')
	checker.check_git(False)
	assert any('detached HEAD' in line for line in lines(capsys, 'FAIL'))


def test_my_branch_on_github_has_commits_i_do_not(repos, checker, capsys):
	"""The same name used by someone else, or pushed from another computer."""
	git(repos.other, 'switch', '--quiet', '-c', 'ndmi')
	write(repos.other, 'a.txt', 'a\n')
	repos.commit(repos.other, 'Theirs')
	git(repos.other, 'push', '--quiet', 'origin', 'ndmi')
	repos.fetch()
	git(repos.mine, 'switch', '--quiet', '-c', 'ndmi', 'origin/main')
	checker.check_git(False)
	assert any('origin/ndmi has commits this branch does not' in line for line in lines(capsys, 'WARN'))


# The workflow Tests ----------------------------------------------------------------------------------------------

def test_the_workflow_checks_every_pull_request_to_main():
	"""The same checks as the skill (offline tests, checker), on every pull request to main and push to main, with the
	history and the tags that the checker reads."""
	with open(WORKFLOW, encoding='utf-8') as f:
		wf = yaml.safe_load(f)
	on = wf.get('on', wf.get(True))  # YAML 1.1 reads the key on as true
	assert on['pull_request']['branches'] == ['main'] and on['push']['branches'] == ['main']
	steps = wf['jobs']['offline']['steps']
	checkout = next(s for s in steps if s.get('uses', '').startswith('actions/checkout'))
	assert checkout['with']['fetch-depth'] == 0
	runs = {s.get('name'): s for s in steps if 'run' in s}
	tests = next(s for s in runs.values() if 'pytest' in s['run'])
	assert '-m "not ee"' in tests['run'] and tests['env']['PYTHONPATH'] == 'src'
	check = next(s for s in runs.values() if 'check_change.py' in s['run'])
	assert check['if'] == "github.event_name == 'pull_request'"
	assert os.path.exists(os.path.join(ROOT, check['run'].split()[1]))
	assert 'secrets.' not in open(WORKFLOW, encoding='utf-8').read()  # nothing is published, no keys


def test_the_workflow_has_the_packages_of_the_environment():
	"""The workflow installs the conda packages of environment.yml (by name), so that the tests run with what users
	install; it leaves out pip (the window of the assistant and monitoreo from GitHub: the tests use src/)."""
	with open(os.path.join(ROOT, 'environment.yml'), encoding='utf-8') as f:
		env = yaml.safe_load(f)
	names = {d.split('=')[0].split('>')[0].split('<')[0].strip() for d in env['dependencies'] if isinstance(d, str)}
	with open(WORKFLOW, encoding='utf-8') as f:
		wf = yaml.safe_load(f)
	micromamba = next(s for s in wf['jobs']['offline']['steps'] if s.get('uses', '').startswith('mamba-org/'))
	installed = {a.split('=')[0] for a in micromamba['with']['create-args'].split()}
	assert names - {'pip'} <= installed, f'add to the workflow Tests: {sorted(names - {"pip"} - installed)}'
