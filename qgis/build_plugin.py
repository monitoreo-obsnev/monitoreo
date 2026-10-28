"""Build the QGIS plugin zip: dist/monitoreo_qgis-<version>.zip, installable from QGIS (Plugins > Manage and
Install Plugins > Install from ZIP).

    python qgis/build_plugin.py

It copies the package monitoreo (src/monitoreo) into monitoreo_qgis/ext and adds earthengine-api and its
dependencies as pure Python wheels for Python 3.9 or newer (QGIS 3 and 4, on Windows, macOS and Linux), without
google-cloud-storage, which Earth Engine does not import. It needs pip and internet.
"""

import argparse
import configparser
import glob
import os
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


def pip_download(args, dest):
	subprocess.run([sys.executable, '-m', 'pip', 'download', '-q', '-d', dest] + args, check=True)


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
	print(f'{out} ({os.path.getsize(out) / 2 ** 20:.1f} MB)')


if __name__ == '__main__':
	main()
