"""Build the QGIS plugin zip: dist/monitoreo_qgis-<version>.zip, installable from QGIS (Plugins > Manage and
Install Plugins > Install from ZIP).

    python qgis/build_plugin.py

It copies the package monitoreo (src/monitoreo) into monitoreo_qgis/ext and adds earthengine-api and its
dependencies as pure Python wheels for Python 3.9 or newer (QGIS 4 has 3.12; on Windows, macOS and Linux), without
google-cloud-storage, which Earth Engine does not import. It needs pip and internet.

The security scan of plugins.qgis.org (Bandit and detect-secrets) blocks a version with critical findings, and the
bundled libraries have false positives (constants such as 'nextPageToken', markers of PEM keys). So the zip leaves
out what the plugin never runs (tests and command lines of the libraries, the discovery documents of
googleapiclient) and has a .bandit that excludes the bundled libraries and, with detect-secrets installed, a
.secrets.baseline with their findings. With Bandit and detect-secrets installed it scans the zip as plugins.qgis.org
does and fails if the plugin or monitoreo have a critical finding.
"""

import argparse
import configparser
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGIN = os.path.join(HERE, 'monitoreo_qgis')
EXT = os.path.join(PLUGIN, 'ext')
DIST = os.path.join(ROOT, 'dist')
PURE = ['--only-binary=:all:', '--platform', 'any', '--python-version', '3.9', '--implementation', 'py', '--abi', 'none']
DEPS = ['google-api-python-client', 'google-auth', 'google-auth-httplib2', 'httplib2', 'requests']
# never run by the plugin: Earth Engine reads its discovery document from the internet (static_discovery=False)
UNUSED = ['googleapiclient/discovery_cache/documents', 'ee/tests', 'ee/apitestcase.py', 'ee/cli', 'ee/mapclient.py',
          'certifi/tests', 'rsa/cli.py']
# Bandit tests whose findings are critical (they block a version) in plugins.qgis.org/docs/security-scanning/rules
CRITICAL = ('B102,B103,B105,B106,B107,B111,B201,B202,B301,B302,B304,B305,B306,B307,B312,B321,B323,B401,B402,B412,'
            'B413,B501,B502,B503,B505,B506,B507,B601,B602,B604,B605,B609,B610,B611,B612,B613,B615,B701')
SECRET_WARNINGS = {'Base64 High Entropy String', 'Hex High Entropy String', 'Secret Keyword', 'Public IP (ipv4)'}
OURS = re.compile(r'monitoreo_qgis/(ext/monitoreo/|[^/]+$)')  # the plugin and monitoreo, not the bundled libraries


def pip_download(args, dest):
	subprocess.run([sys.executable, '-m', 'pip', 'download', '-q', '-d', dest] + args, check=True)


def bandit_ini():
	"""The .bandit of the zip: Bandit skips the libraries bundled in ext (all but monitoreo). None without them (an
	empty exclude would skip everything)."""
	libs = [f'/ext/{n}/' if os.path.isdir(os.path.join(EXT, n)) else f'/ext/{n}'
	        for n in sorted(os.listdir(EXT)) if n != 'monitoreo' and not n.endswith('.dist-info')]
	return libs and ('[bandit]\n# libraries bundled by build_plugin.py (earthengine-api and its dependencies), not '
	                 'code of the plugin\nexclude = ' + ','.join(libs) + '\n') or None


def scan(out):
	"""Scan the zip OUT as plugins.qgis.org does (extracted, Bandit with its .bandit and detect-secrets from its folder)
	and add the .secrets.baseline with the findings of the bundled libraries. Fails if the plugin or monitoreo have a
	critical finding. Without Bandit or detect-secrets (pip install bandit detect-secrets) it only warns."""
	with tempfile.TemporaryDirectory() as tmp:
		with zipfile.ZipFile(out) as z:
			z.extractall(tmp)
		critical = []
		if shutil.which('bandit'):
			r = subprocess.run(['bandit', '-r', tmp, '-f', 'json', '--quiet', '-t', CRITICAL], capture_output=True,
			                   text=True)
			critical += [f"{x['filename'].replace(tmp, '')}:{x['line_number']} {x['test_id']} {x['issue_text']}"
			             for x in json.loads(r.stdout)['results']]
		else:
			print('   without Bandit: the zip is not scanned (pip install bandit)')
		if shutil.which('detect-secrets'):
			r = subprocess.run(['detect-secrets', 'scan', '--all-files', '--exclude-files', r'metadata\.txt',
			                    '--exclude-files', r'\.secrets\.baseline', '.'], cwd=tmp, capture_output=True,
			                   text=True, check=True)
			baseline = json.loads(r.stdout)
			critical += [f"{f}:{s['line_number']} {s['type']}" for f, found in baseline['results'].items()
			             if OURS.match(f) for s in found if s['type'] not in SECRET_WARNINGS]
			baseline['results'] = {f: found for f, found in baseline['results'].items() if not OURS.match(f)}
			with zipfile.ZipFile(out, 'a', zipfile.ZIP_DEFLATED) as z:
				z.writestr('monitoreo_qgis/.secrets.baseline', json.dumps(baseline, indent=2) + '\n')
			print(f"   .secrets.baseline: {sum(map(len, baseline['results'].values()))} findings of the bundled "
			      'libraries')
		else:
			print('   without detect-secrets: no .secrets.baseline (pip install detect-secrets)')
	if critical:
		sys.exit('Critical findings of the security scan of plugins.qgis.org:\n' + '\n'.join(critical))


def main():
	parser = argparse.ArgumentParser(description='Build the zip of the QGIS plugin MonitorEO.')
	parser.add_argument('--no-ee', action='store_true', help='without earthengine-api (when QGIS already has it)')
	args = parser.parse_args()

	shutil.rmtree(EXT, ignore_errors=True)
	os.makedirs(EXT)
	shutil.copytree(os.path.join(ROOT, 'src', 'monitoreo'), os.path.join(EXT, 'monitoreo'),
	                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
	if not args.no_ee:
		with tempfile.TemporaryDirectory() as wheels:
			pip_download(['--no-deps', 'earthengine-api'] + PURE, wheels)
			pip_download(DEPS + PURE, wheels)
			for whl in sorted(glob.glob(os.path.join(wheels, '*.whl'))):
				with zipfile.ZipFile(whl) as z:
					z.extractall(EXT)
				print('  ', os.path.basename(whl))
		for name in UNUSED:
			path = os.path.join(EXT, name)
			if os.path.isdir(path):
				shutil.rmtree(path)
			elif os.path.exists(path):
				os.remove(path)

	meta = configparser.ConfigParser()
	meta.read(os.path.join(PLUGIN, 'metadata.txt'), encoding='utf-8')
	version = meta['general']['version']
	os.makedirs(DIST, exist_ok=True)
	out = os.path.join(DIST, f'monitoreo_qgis-{version}.zip')
	with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
		for folder, dirs, files in os.walk(PLUGIN):
			dirs[:] = [d for d in dirs if d != '__pycache__']
			for f in files:
				if f.endswith('.pyc') or f == '.DS_Store':
					continue
				path = os.path.join(folder, f)
				z.write(path, os.path.relpath(path, HERE))
		z.write(os.path.join(ROOT, 'LICENSE'), os.path.join(os.path.basename(PLUGIN), 'LICENSE'))
		ini = bandit_ini()
		if ini:
			z.writestr(os.path.join(os.path.basename(PLUGIN), '.bandit'), ini)
	scan(out)
	print(f'{out} ({os.path.getsize(out) / 2 ** 20:.1f} MB)')


if __name__ == '__main__':
	main()
