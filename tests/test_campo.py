"""MonitorEO Campo, the field app (campo/): it computes with the core of gee/ unchanged, so its copy must be that of
gee/, the functions of the core that it calls must exist, and its workflow must build it when the core changes.
Offline, without Earth Engine, Android or Xcode."""

import filecmp
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMPO = os.path.join(ROOT, 'campo')
WWW = os.path.join(CAMPO, 'app', 'src', 'main', 'assets', 'www')

pytestmark = pytest.mark.skipif(not os.path.isdir(CAMPO), reason='no campo/')


def read(*path):
	with open(os.path.join(*path), encoding='utf-8') as f:
		return f.read()


@pytest.mark.parametrize('name', ['core.js', 'catalog.js'])
def test_the_app_has_the_core_of_gee(name):
	"""The page of the app carries gee/core.js and gee/catalog.js as they are: after changing them, run
	python campo/sync.py core (gee/build.py does it too)."""
	assert filecmp.cmp(os.path.join(ROOT, 'gee', name), os.path.join(WWW, 'lib', name), shallow=False), (
		f'campo/ has not got gee/{name}: run python campo/sync.py core')


def exported(core):
	"""The names that the object MonitorEO of core.js exports (its last return {...})."""
	body = core[core.rindex('return {'):]
	return set(re.findall(r'\b([A-Za-z_]\w*)\s*:', body))


def test_the_functions_of_the_core_that_the_app_calls_exist():
	"""A function of core.js that the app uses (mo.<name> in app.js and ai.js) cannot be renamed or removed without
	changing the app."""
	names = exported(read(ROOT, 'gee', 'core.js'))
	used = set()
	for page in ('app.js', 'ai.js'):
		used |= set(re.findall(r'\bmo\.([A-Za-z_]\w*)', read(WWW, page)))
	assert used, 'the app calls no function of the core?'
	assert not used - names, f'core.js no longer has what the field app calls: {sorted(used - names)}'


def test_sync_check_says_whether_the_core_is_there():
	out = subprocess.run([sys.executable, os.path.join(CAMPO, 'sync.py'), 'check'], capture_output=True, text=True)
	assert out.returncode == 0, out.stdout + out.stderr


def test_the_workflow_builds_it_when_the_core_changes():
	text = read(ROOT, '.github', 'workflows', 'campo.yml')
	for path in ("'campo/**'", "'gee/core.js'", "'gee/catalog.js'"):
		assert path in text
	assert 'campo/sync.py core' in text
	assert 'assembleRelease' in text and 'xcodebuild' in text


def test_feedback_names_the_tool_as_about_does():
	"""The links to suggest a change or report an error of the app name it as monitoreo.about.TOOLS['campo']."""
	sys.path.insert(0, os.path.join(ROOT, 'src'))
	from monitoreo import about
	name, option = about.TOOLS['campo']
	app = read(WWW, 'app.js')
	assert f"['{name}', '{option}']" in app
	assert about.FORM in app and about.FORM_FIELDS['tool'] in app and about.FORM_FIELDS['version'] in app


def test_no_keys_in_the_app():
	"""The keys of the user stay in the private storage of the phone: none in the repository."""
	for folder, _, files in os.walk(CAMPO):
		if 'build' in folder.split(os.sep) or '.gradle' in folder:
			continue
		for name in files:
			assert not name.endswith(('.jks', '.keystore', '.p12', '.pem')), os.path.join(folder, name)
			if name.endswith(('.js', '.java', '.swift', '.gradle', '.py', '.json', '.md', '.yml')) and 'lib' not in folder:
				text = read(folder, name)
				assert '-----BEGIN PRIVATE KEY-----\n' not in text and not re.search(r'sk-ant-[A-Za-z0-9]{8}', text), \
					os.path.join(folder, name)
