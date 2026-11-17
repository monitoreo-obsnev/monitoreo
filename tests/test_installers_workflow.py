"""The step "Attach the zips to the release" of .github/workflows/installers.yml, run with bash against a fake gh and
a fake sleep, without GitHub: with a pushed tag it waits until the workflow of the QGIS plugin has published the
release (gh release create makes it a draft while it uploads the plugin zip, and at v0.3.42 the upload of the zips
failed with "release not found" while that draft was being published), and it retries the upload."""

import json
import os
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, '.github', 'workflows', 'installers.yml')

pytestmark = pytest.mark.skipif(shutil.which('bash') is None, reason='the steps of the workflow run with bash')

# gh release view/create/upload as GitHub answers them; FAKE_DIR/state.json has the state of the release at each call
# of gh release view (the last one stays) and the result of each upload (the last one stays)
FAKE_GH = '''#!{python}
import json, os, sys
d = os.environ['FAKE_DIR']
with open(os.path.join(d, 'state.json')) as f:
	s = json.load(f)
args = sys.argv[1:]
s['calls'].append(args)
code = 0
if args[:2] == ['release', 'view']:
	release = s['created'] or s['views'][min(s['n_views'], len(s['views']) - 1)]
	s['n_views'] += 1
	s['seen'] = release
	if release == 'none':
		print('release not found', file=sys.stderr)
		code = 1
	elif '--json' in args:
		print('true' if release == 'draft' else 'false')
elif args[:2] == ['release', 'create']:
	if s['seen'] != 'none':
		print('a release with the same tag name already exists', file=sys.stderr)
		code = 1
	else:
		s['created'] = 'published'
elif args[:2] == ['release', 'upload']:
	ok = s['uploads'][min(s['n_uploads'], len(s['uploads']) - 1)]
	s['n_uploads'] += 1
	if not ok:
		print('release not found', file=sys.stderr)
		code = 1
else:
	code = 2
with open(os.path.join(d, 'state.json'), 'w') as f:
	json.dump(s, f)
sys.exit(code)
'''

FAKE_SLEEP = '''#!/bin/sh
echo "$1" >> "$FAKE_DIR/sleeps"
'''


def attach_step():
	with open(WORKFLOW) as f:
		jobs = yaml.safe_load(f)['jobs']
	return next(step for step in jobs['zips']['steps'] if step.get('name') == 'Attach the zips to the release')


def attach(tmp_path, event='push', views=('published',), uploads=(True,)):
	"""Runs the step as GitHub does (bash -e) with the tag v0.3.42; returns its result, the calls of gh and the
	seconds it slept."""
	bin_dir = tmp_path / 'bin'
	bin_dir.mkdir()
	for name, text in (('gh', FAKE_GH.format(python=sys.executable)), ('sleep', FAKE_SLEEP)):
		(bin_dir / name).write_text(text)
		(bin_dir / name).chmod(0o755)
	state = {'views': list(views), 'uploads': list(uploads), 'n_views': 0, 'n_uploads': 0, 'seen': 'none',
		'created': None, 'calls': []}
	(tmp_path / 'state.json').write_text(json.dumps(state))
	(tmp_path / 'step.sh').write_text(attach_step()['run'])
	env = dict(os.environ, PATH=f'{bin_dir}{os.pathsep}{os.environ["PATH"]}', FAKE_DIR=str(tmp_path),
		TAG='v0.3.42', GITHUB_EVENT_NAME=event, GH_TOKEN='fake')
	result = subprocess.run(['bash', '--noprofile', '--norc', '-e', str(tmp_path / 'step.sh')], env=env,
		cwd=tmp_path, capture_output=True, text=True, timeout=120)
	calls = json.loads((tmp_path / 'state.json').read_text())['calls']
	sleeps = tmp_path / 'sleeps'
	slept = sum(int(s) for s in sleeps.read_text().split()) if sleeps.exists() else 0
	return result, calls, slept


def commands(calls):
	return [' '.join(c[:2]) for c in calls]


def test_the_step_runs_only_with_a_tag_and_the_token():
	step = attach_step()
	assert step['if'] == "env.TAG != ''"
	assert step['env']['GH_TOKEN'] == '${{ github.token }}'


def test_it_waits_until_the_draft_of_the_qgis_plugin_is_published(tmp_path):
	# v0.3.42: no release, then the draft that gh release create of the QGIS plugin makes while it uploads its zip
	result, calls, slept = attach(tmp_path, views=['none', 'none', 'draft', 'draft', 'published'])
	assert result.returncode == 0, result.stderr
	assert 'release create' not in commands(calls)
	uploads = [i for i, c in enumerate(commands(calls)) if c == 'release upload']
	assert len(uploads) == 1
	assert commands(calls)[:uploads[0]].count('release view') >= 5  # not before the fifth: the release published
	assert calls[uploads[0]][2:] == ['v0.3.42', 'dist/asistente-monitoreo-macos.zip',
		'dist/asistente-monitoreo-windows.zip', '--clobber']
	assert slept == 40


def test_it_retries_the_upload(tmp_path):
	result, calls, _ = attach(tmp_path, uploads=[False, False, True])
	assert result.returncode == 0, result.stderr
	assert commands(calls).count('release upload') == 3


def test_it_fails_with_how_to_attach_them_if_every_upload_fails(tmp_path):
	result, calls, _ = attach(tmp_path, uploads=[False])
	assert result.returncode == 1
	assert commands(calls).count('release upload') == 5
	assert '::error::' in result.stdout and 'Run workflow with the tag v0.3.42' in result.stdout


def test_it_creates_the_release_with_empty_notes_if_there_is_none_after_10_minutes(tmp_path):
	result, calls, slept = attach(tmp_path, views=['none'])
	assert result.returncode == 0, result.stderr
	created = [c for c in calls if c[:2] == ['release', 'create']]
	assert created == [['release', 'create', 'v0.3.42', '--verify-tag', '--title', 'MonitorEO v0.3.42', '--notes', '']]
	assert commands(calls)[-1] == 'release upload'
	assert slept == 600


def test_it_does_not_create_a_release_over_a_draft(tmp_path):
	# a draft for 10 minutes: the zips go to the draft, which the QGIS plugin publishes
	result, calls, _ = attach(tmp_path, views=['draft'])
	assert result.returncode == 0, result.stderr
	assert 'release create' not in commands(calls)
	assert commands(calls)[-1] == 'release upload'


@pytest.mark.parametrize('event', ['release', 'workflow_dispatch'])
def test_a_published_release_or_a_run_by_hand_neither_waits_nor_creates(tmp_path, event):
	# the release exists already (or the tag given by hand is wrong, and the upload says so)
	wrong, ok = tmp_path / 'wrong', tmp_path / 'ok'
	wrong.mkdir()
	ok.mkdir()
	result, calls, _ = attach(wrong, event=event, views=['none'], uploads=[False])
	assert result.returncode == 1
	assert set(commands(calls)) == {'release upload'}
	result, calls, slept = attach(ok, event=event)
	assert result.returncode == 0, result.stderr
	assert commands(calls) == ['release upload'] and slept == 0
