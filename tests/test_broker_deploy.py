"""broker/deploy.sh deploys the broker of the shared account only from main as GitHub has it, with nothing uncommitted
in broker/ (team decision, 2026-11-27): the broker is one for everyone, and deploying it from a branch behind main
would take away what the others added (in November 2026 a branch without the GLM of #157). Run with bash against a
fake gcloud and a local origin, without Google Cloud nor network."""

import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY = os.path.join(ROOT, 'broker', 'deploy.sh')

pytestmark = pytest.mark.skipif(shutil.which('bash') is None or shutil.which('git') is None,
                                reason='deploy.sh runs with bash and reads git')

GIT = {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 'MonitorEO tests',
       'GIT_AUTHOR_EMAIL': 'tests@example.org', 'GIT_COMMITTER_NAME': 'MonitorEO tests',
       'GIT_COMMITTER_EMAIL': 'tests@example.org'}

# every call is written to $FAKE_LOG; the service answers with its address
FAKE_GCLOUD = '''#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
case "$*" in
  "run services describe"*) echo https://monitoreo-broker.example.org ;;
esac
exit 0
'''


def git(cwd, *args):
	return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True,
	                      env=dict(os.environ, **GIT)).stdout.strip()


@pytest.fixture
def setup(tmp_path):
	"""A clone at main of a local origin, with broker/deploy.sh and broker/main.py, and a fake gcloud."""
	origin, work, bin_ = tmp_path / 'origin.git', tmp_path / 'work', tmp_path / 'bin'
	git(tmp_path, 'init', '--quiet', '--bare', '-b', 'main', str(origin))
	git(tmp_path, 'init', '--quiet', '-b', 'main', str(work))
	(work / 'broker').mkdir()
	shutil.copy(DEPLOY, work / 'broker' / 'deploy.sh')
	(work / 'broker' / 'main.py').write_text('# the broker\n')
	git(work, 'add', '-A')
	git(work, 'commit', '--quiet', '-m', 'The broker')
	git(work, 'remote', 'add', 'origin', str(origin))
	git(work, 'push', '--quiet', '-u', 'origin', 'main')
	bin_.mkdir()
	(bin_ / 'gcloud').write_text(FAKE_GCLOUD)
	(bin_ / 'gcloud').chmod(0o755)
	log = tmp_path / 'gcloud.log'
	env = dict(os.environ, **GIT, PATH=f'{bin_}{os.pathsep}{os.environ["PATH"]}', FAKE_LOG=str(log))
	env.pop('ALLOW_ANY', None)

	def deploy(cwd=work, project='test-project', **extra):
		run = subprocess.run(['bash', 'broker/deploy.sh', project], cwd=cwd, capture_output=True, text=True,
		                     env=dict(env, **extra))
		calls = log.read_text().splitlines() if log.exists() else []
		if log.exists():
			log.unlink()
		return run, calls

	return work, origin, deploy


def deployed(calls):
	return any(c.startswith('run deploy monitoreo-broker') for c in calls)


def test_from_main_as_github_has_it(setup):
	work, _, deploy = setup
	run, calls = deploy()
	assert run.returncode == 0, run.stderr
	assert deployed(calls) and 'https://monitoreo-broker.example.org' in run.stdout


def test_not_from_a_branch(setup):
	work, _, deploy = setup
	git(work, 'switch', '--quiet', '-c', 'gemini-default-assistant')
	(work / 'broker' / 'main.py').write_text('# an older broker\n')
	git(work, 'commit', '--quiet', '-am', 'Older')
	run, calls = deploy()
	assert run.returncode == 1 and calls == []
	assert 'not at main as GitHub has it' in run.stderr


def test_not_from_a_main_behind_github(setup, tmp_path):
	"""Another developer merged a PR: the local main is no longer that of GitHub."""
	work, origin, deploy = setup
	other = tmp_path / 'other'
	git(tmp_path, 'clone', '--quiet', str(origin), str(other))
	(other / 'broker' / 'main.py').write_text('# the broker, with GLM\n')
	git(other, 'commit', '--quiet', '-am', 'GLM')
	git(other, 'push', '--quiet', 'origin', 'main')
	run, calls = deploy()
	assert run.returncode == 1 and calls == [] and 'git switch main && git pull' in run.stderr
	git(work, 'pull', '--quiet', '--ff-only')
	run, calls = deploy()
	assert run.returncode == 0 and deployed(calls)


def test_not_with_uncommitted_changes_in_broker(setup):
	work, _, deploy = setup
	(work / 'broker' / 'main.py').write_text('# changed, not committed\n')
	run, calls = deploy()
	assert run.returncode == 1 and calls == [] and 'uncommitted changes' in run.stderr


def test_not_outside_a_clone(setup, tmp_path):
	_, _, deploy = setup
	plain = tmp_path / 'plain'
	(plain / 'broker').mkdir(parents=True)
	shutil.copy(DEPLOY, plain / 'broker' / 'deploy.sh')
	run, calls = deploy(cwd=plain, GIT_CEILING_DIRECTORIES=str(tmp_path))
	assert run.returncode == 1 and calls == [] and 'not in a clone of monitoreo' in run.stderr


def test_allow_any_for_a_test_project(setup):
	work, _, deploy = setup
	git(work, 'switch', '--quiet', '-c', 'try-the-broker')
	run, calls = deploy(ALLOW_ANY='1')
	assert run.returncode == 0 and deployed(calls)


def test_never_allow_any_for_the_shared_account(setup):
	"""ALLOW_ANY is for a test project: the project of the shared account is always deployed from main."""
	work, _, deploy = setup
	git(work, 'switch', '--quiet', '-c', 'try-the-broker')
	run, calls = deploy(project='ee-ugr-default-project', ALLOW_ANY='1')
	assert run.returncode == 1 and calls == [] and 'never for ee-ugr-default-project' in run.stderr
	git(work, 'switch', '--quiet', 'main')
	run, calls = deploy(project='ee-ugr-default-project')
	assert run.returncode == 0 and deployed(calls)
