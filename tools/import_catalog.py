#### Imports the variable catalog of the MonitorEO app (OBSNEV, Google Earth Engine) into catalog.json
#### License: GPL-3.0-or-later

"""
MonitorEO is a Google Earth Engine app written in JavaScript. Its catalog of
variables (one entry per variable and sensor, with the collection, formula,
scale, offset, unit, ...) is a JavaScript array in its translations modules.
This script reads the source of the app, parses those arrays as data (the
JavaScript is never run) and writes src/monitoreo/catalog.json, so that the
Python code uses the same catalog as the app:

    python3 tools/import_catalog.py                 # latest version of the Earth Engine repository
    python3 tools/import_catalog.py --repo DIR      # a local clone of that repository
    python3 tools/import_catalog.py --published     # the published app (the JSON it loads)
    python3 tools/import_catalog.py --modules FILE  # a saved copy of that JSON

By default it clones the repository of the app (users/monitoreo-obsnev/monitoreo-obsnev), which needs git
credentials for earthengine.googlesource.com (https://earthengine.googlesource.com/new-password); without them it
reads the published app. The source and its commit are recorded in catalog.json. Run it again when the catalog of
MonitorEO changes.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

APP_URL = 'https://ee-ugr-default-project.projects.earthengine.app/view/monitoreo-obsnev'
MODULES_URL = 'https://ee-ugr-default-project.projects.earthengine.app/javascript/monitoreo-obsnev-modules.json'
REPO = 'users/monitoreo-obsnev/monitoreo-obsnev'
REPO_URL = 'https://earthengine.googlesource.com/' + REPO
LANGS = ('en', 'fr', 'de')  # other languages of the names (the catalog is read from translations/es.js)
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src', 'monitoreo', 'catalog.json')

# Fields of the entries that are numbers, sometimes written as strings in the app (e.g. "scale": "10000")
NUMERIC = ('ref', 'm', 'scale', 'offset', 'scalet', 'offsett', 'min', 'max', 'minp', 'maxp', 'fe', 'aux',
           'clouds', 'water', 'snow', 'aerosols', 'pclouds', 'pwater', 'psnow', 'paerosols')


def from_modules(modules):
	"""Reader of the modules of the JSON loaded by the app: read(name) -> source or None."""
	deps = {key.split(':', 1)[-1].lstrip('/'): src for key, src in modules['dependencies'].items()}
	return deps.get


def from_repo(folder):
	"""Reader of the modules of a clone of the repository of the app."""
	def read(name):
		path = os.path.join(folder, *name.split('/'))
		if not os.path.isfile(path):
			return None
		with open(path, encoding='utf-8') as f:
			return f.read()
	return read


def commit_of(folder):
	try:
		return subprocess.check_output(['git', '-C', folder, 'log', '-1', '--format=%H %cs'], text=True).strip()
	except (OSError, subprocess.CalledProcessError):
		return None


def module(read, name):
	"""Source of the module NAME (e.g. 'translations/es.js') of the app."""
	src = read(name)
	if src is None:
		sys.exit(f'ERROR: module {name} not found in the source of MonitorEO')
	return src


def split_comment(line):
	"""(code, comment) of a line of JavaScript: the comment starts at // outside a string."""
	in_str = False
	i = 0
	while i < len(line):
		c = line[i]
		if in_str:
			if c == '\\':
				i += 1
			elif c == '"':
				in_str = False
		elif c == '"':
			in_str = True
		elif line.startswith('//', i):
			return line[:i], line[i + 2:].strip()
		i += 1
	return line, ''


def parse_data(src):
	"""Entries of the array 'var data = [...]' of a translations module, and the comments of their fields
	({ref: {field: comment}})."""
	start = src.index('[', src.index('var data'))
	end = src.index('];', start) + 1
	code, notes, ref = [], {}, None
	for line in src[start:end].splitlines():
		line, comment = split_comment(line)
		m = re.search(r'"ref"\s*:\s*(\d+)', line)
		if m:
			ref = int(m.group(1))
		key = re.match(r'\s*"(\w+)"\s*:', line)
		if comment and key and ref is not None:
			notes.setdefault(ref, {})[key.group(1)] = comment
		code.append(line)
	text = re.sub(r',(\s*[\]}])', r'\1', '\n'.join(code))  # trailing commas are not valid JSON
	return json.loads(text), notes


def number(v):
	if isinstance(v, str):
		try:
			f = float(v)
		except ValueError:
			return v
		return int(f) if f.is_integer() else f
	return v


def date_ranges(src):
	"""First and last date of each collection, from predefinedRanges of modules/sensorList."""
	ranges = {}
	for m in re.finditer(r'"([\w/\-]+)"\s*:\s*\{\s*start:\s*"([\d-]+)"(?:\s*,\s*end:\s*"([\d-]+)")?', src):
		ranges[m.group(1)] = {'start': m.group(2), 'end': m.group(3)}
	return ranges


def main():
	parser = argparse.ArgumentParser(description='Import the variable catalog of MonitorEO into catalog.json.')
	parser.add_argument('--repo', metavar='DIR', help='local clone of the repository of the app')
	parser.add_argument('--published', action='store_true', help=f'read the published app ({MODULES_URL})')
	parser.add_argument('--modules', metavar='FILE', help='saved copy of the JSON loaded by the app')
	parser.add_argument('--out', default=OUT, help='output file (default: %(default)s)')
	args = parser.parse_args()

	tmp = None
	if args.modules:
		with open(args.modules, encoding='utf-8') as f:
			read, source = from_modules(json.load(f)), {'modules': os.path.basename(args.modules)}
	elif args.repo:
		read, source = from_repo(args.repo), {'repository': REPO_URL, 'commit': commit_of(args.repo)}
	else:
		read = None
		if not args.published:
			tmp = tempfile.TemporaryDirectory()
			r = subprocess.run(['git', 'clone', '-q', '--depth', '1', REPO_URL, tmp.name], capture_output=True, text=True)
			if r.returncode == 0:
				read, source = from_repo(tmp.name), {'repository': REPO_URL, 'commit': commit_of(tmp.name)}
			else:
				print(f'Cannot clone {REPO_URL} ({r.stderr.strip()}): reading the published app instead')
		if read is None:
			with urllib.request.urlopen(MODULES_URL, timeout=60) as r:
				read, source = from_modules(json.loads(r.read().decode('utf-8'))), {'modules': MODULES_URL}

	es, notes = parse_data(module(read, 'translations/es.js'))
	names = {}
	for lang in LANGS:
		src = read(f'translations/{lang}.js')
		if src:
			names[lang] = {e['ref']: e for e in parse_data(src)[0]}
	large = {e['ref'] for e in parse_data(module(read, 'translations/es_largeareas.js'))[0]}

	entries = []
	for e in es:
		e = {k: number(v) if k in NUMERIC else v for k, v in e.items()}
		ref = e['ref']
		for lang, by_ref in names.items():
			e[f'vname_{lang}'] = by_ref.get(ref, {}).get('vname', e['vname'])
			e[f'type_{lang}'] = by_ref.get(ref, {}).get('type', e['type'])
		e['large_areas'] = ref in large
		if ref in notes:
			e['notes'] = notes[ref]
		entries.append(e)

	catalog = {
		'source': dict({'app': APP_URL, 'script': REPO}, **source, imported=datetime.date.today().isoformat()),
		'fields': {
			'ref': 'ID of the entry', 'type': 'group of variables', 'index': 'variable', 'vname': 'name',
			'sensor': 'Sentinel-2, Landsat or Modis', 'col': 'Earth Engine collection (LANDSAT = Landsat 5, 7, 8 and 9)',
			'm': 'native pixel size (m)', 'tr': 'revisit time', 'dr': 'dates', 'unit': 'unit',
			'ft': "formula: a band, an expression of the bands, or N(b1,b2) for the normalized difference",
			'scale': 'scale factor of the bands', 'offset': 'offset of the bands',
			'clouds_bandQA': 'QA band for clouds', 'water_bandQA': 'QA band for water', 'snow_bandQA': 'QA band for snow',
			'aerosols_bandQA': 'QA band for aerosols', 'minp': 'minimum of the colour ramp', 'maxp': 'maximum of the colour ramp',
			'pm': 'colour ramp', 'large_areas': 'offered for large areas', 'notes': 'comments of the fields in the app',
		},
		'collections': date_ranges(module(read, 'modules/sensorList')),
		'variables': entries,
	}
	with open(args.out, 'w', encoding='utf-8') as f:
		json.dump(catalog, f, ensure_ascii=False, indent=1)
		f.write('\n')
	if tmp:
		tmp.cleanup()
	print(f"{len(entries)} variables written to {args.out} (from {source.get('repository') or source['modules']}"
	      f"{', commit ' + source['commit'] if source.get('commit') else ''})")


if __name__ == '__main__':
	main()
