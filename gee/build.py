"""Build the app of MonitorEO for the Earth Engine Code Editor from the Python package of this repository:

  catalog.js         the catalog (catalog.json with the corrections and the NBR of catalog.py), with the band of every
                     name of the formulas resolved as sensors.parse_formula does, the themes of the menu (also those of
                     the data of Earth Engine outside the catalog, catalog.OTHER_THEMES), a slim copy of the index of
                     the GEE Community Catalog (community.json.gz) and the texts of about.py
  monitoreo_app.js   catalog.js, core.js and ui.js in a single script: paste it in a new script of the Code Editor and
                     publish it as an app (Apps > New App); the fallback of the git route below

The app is published from the git repository of its scripts in Earth Engine, users/monitoreo-obsnev/monitoreo (see
modules and gee/push_app.py): Earth Engine refuses any file of a repository over 512 KiB and monitoreo_app.js is
bigger, so there the app is the script app (core.js and ui.js) and the catalog is in the modules catalog_1,
catalog_2... that it requires. They are written from the catalog.js, core.js and ui.js there are, without Earth Engine:

  python gee/build.py --modules DIR

Run it after changing catalog.json, about.py, community.json.gz, core.js or ui.js (Earth Engine is needed for the
band names):

  python gee/build.py --project my-ee-project

After changing only core.js or ui.js, monitoreo_app.js can be written from the catalog.js there is, without Earth
Engine:

  python gee/build.py --app-only

At each release (a new version and date, see __released__), the about of catalog.js (version, date of the release and
the version in the links of suggestions) and monitoreo_app.js are written again, also without Earth Engine:

  python gee/build.py --about-only
"""

import argparse
import base64
import io
import json
import os
import re
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from monitoreo import __released__, __version__, about, catalog, community, eecatalog, sensors, services  # noqa: E402

FIELDS = ['ref', 'type', 'type_en', 'index', 'vname', 'vname_en', 'sensor', 'col', 'm', 'tr', 'dr', 'unit', 'ft',
          'scale', 'offset', 'minp', 'maxp', 'pm', 'large_areas', 'two_periods', 'metric', 'axis', 'static', 'band',
          'terrain', 'image_asset', 'theme']
LOGO_WIDTHS = [340, 340, 200]  # pixels of the logos of about.LOGOS in the app (the Code Editor shows them at their size)
COMMUNITY_DOCS = community.SITE + '/projects/'  # where the pages of the datasets of the GEE Community Catalog are
REPO = 'users/monitoreo-obsnev/monitoreo'  # the git repository of the scripts of the app in Earth Engine
MAX_FILE = 524288  # bytes: the biggest file Earth Engine takes in a push to a repository (measured; any push size)
LIMIT = 500000  # bytes of each file of the repository of the app, with a margin under MAX_FILE
MODULE = re.compile(r'app|catalog_[0-9]+')  # the names of the files that modules writes


def entries():
	out = []
	for e in catalog.variables():
		kind, bands = sensors.parse_formula(e)
		out.append(dict({k: e.get(k) for k in FIELDS}, fk=kind, fb=bands))
	return out


def logo(path, width):
	"""Data URL of the logo PATH resized to WIDTH pixels: the apps of Earth Engine only show images of data URLs."""
	from PIL import Image

	img = Image.open(path)
	img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
	buf = io.BytesIO()
	kind = 'jpeg' if img.mode == 'RGB' else 'png'
	img.save(buf, kind, **({'quality': 90} if kind == 'jpeg' else {'optimize': True}))
	return f'data:image/{kind};base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def eecatalog_index():
	"""The copy of the index of the Earth Engine data catalog (monitoreo.eecatalog) for the app, slim: each image or
	collection of images as [id, title, 1 if a collection of images (0: an image), first year, last year (None: it
	goes on, its last image at most eecatalog.OPEN days older than the copy or eecatalog.AHEAD days after it),
	keywords (with spaces)], in the order of the index (see searchCatalog in core.js). Without their descriptions,
	which the app does not search."""
	rows = []
	for d in eecatalog.load()['datasets']:
		rows.append([d['id'], d['title'], 1 if d['type'] == 'image_collection' else 0,
		             int(d['start'][:4]) if d.get('start') else None, int(d['end'][:4]) if d.get('end') else None,
		             ' '.join(d.get('keywords') or [])])
	return {'downloaded': eecatalog.load().get('downloaded'), 'datasets': rows}


def community_index():
	"""The copy of the index of the GEE Community Catalog (monitoreo.community) for the app, slim: its themes
	([English, Spanish], all of community.THEMES, in its order) and licences once, and each image or collection of
	images as [id, title, 1 if a collection of images (0: an image), theme (its index in themes), page (its URL after
	docs, or the whole URL if it is elsewhere), licence (its index in licences, or None)], in the order of the index
	(see communityDatasets in core.js)."""
	snap = community.load()
	themes = [[en, es] for en, es in community.THEMES]
	order = {en: i for i, (en, _) in enumerate(community.THEMES)}
	licences, rows = [], []
	for d in community.datasets():
		lic = d.get('license_text') if d.get('license') == 'custom' else d.get('license')  # as assets.cite
		if lic and lic not in licences:
			licences.append(lic)
		docs = d.get('docs') or ''
		rows.append([d['id'], d['title'], 1 if d['type'] == 'image_collection' else 0, order[d['theme']],
		             docs[len(COMMUNITY_DOCS):] if docs.startswith(COMMUNITY_DOCS) else docs,
		             licences.index(lic) if lic else None])
	return {'site': community.SITE, 'docs': COMMUNITY_DOCS, 'licence': community.LICENCE, 'source': snap.get('source'),
	        'date': snap.get('date'), 'themes': themes, 'licences': licences,
	        'datasets': rows}


def catalog_text(data):
	"""The text of catalog.js for DATA: a JSON object (one per line, sorted), with the datasets of the GEE Community
	Catalog one per line, so that the copy of its index does not take a line per value."""
	slim = dict(data, community='@COMMUNITY@')
	text = json.dumps(slim, ensure_ascii=False, indent=1, sort_keys=True)
	index = data['community']
	head = json.dumps({k: v for k, v in index.items() if k != 'datasets'}, ensure_ascii=False, sort_keys=True,
	                  separators=(',', ':'))
	rows = ',\n'.join(json.dumps(r, ensure_ascii=False, separators=(',', ':')) for r in index['datasets'])
	return text.replace('"@COMMUNITY@"', head[:-1] + ',"datasets":[\n' + rows + '\n]}', 1)


def about_texts(logos=True):
	"""The texts of about.py for the app, with the version of the package and the date of its release; with LOGOS,
	the logos as data URLs (they need PIL)."""
	texts = {'name': 'MonitorEO-OBSNEV', 'description': about.DESCRIPTION, 'acknowledgements': about.ACKNOWLEDGEMENTS,
	         'citation': about.CITATION, 'doi': about.DOI, 'manual': about.MANUAL, 'repository': about.REPOSITORY,
	         'feedback': dict(about.FEEDBACK, links=about.feedback('gee', __version__)),
	         'version': __version__, 'released': __released__}  # shown under the subtitle
	if logos:
		texts['logos'] = [logo(p, w) for p, w in zip(about.LOGOS, LOGO_WIDTHS)]
	return texts


def read_catalog():
	"""The data of the catalog.js there is."""
	with open(os.path.join(HERE, 'catalog.js'), encoding='utf-8') as f:
		text = f.read()
	return json.loads(text[text.index('{'):text.rstrip().rindex('}') + 1])


def write_catalog(data):
	with open(os.path.join(HERE, 'catalog.js'), 'w', encoding='utf-8') as f:
		f.write('// Written by build.py from src/monitoreo (catalog.json, catalog.py, about.py, community.json.gz): do not '
		        'edit.\n')
		f.write(f'var CATALOG = {catalog_text(data)};\n')


def ascii_js(text):
	"""TEXT in ASCII only, with \\u escapes (valid in the strings, regular expressions and comments of these files; a
	character beyond U+FFFF as its two surrogates): pasting the script in the Code Editor cannot then garble the
	accents, nor can Earth Engine read the files of its repository in another encoding."""
	out = []
	for c in text:
		n = ord(c)
		if n < 128:
			out.append(c)
		elif n < 0x10000:
			out.append(f'\\u{n:04x}')
		else:
			n -= 0x10000
			out.append(f'\\u{0xd800 + (n >> 10):04x}\\u{0xdc00 + (n & 0x3ff):04x}')
	return ''.join(out)


def _read(name):
	with open(os.path.join(HERE, name), encoding='utf-8') as f:
		return f.read()


def app():
	"""Write monitoreo_app.js: catalog.js, core.js and ui.js in a single script."""
	text = ascii_js('\n'.join(_read(name) for name in ('catalog.js', 'core.js', 'ui.js')))
	with open(os.path.join(HERE, 'monitoreo_app.js'), 'w', encoding='ascii') as f:
		f.write('// MonitorEO for the Earth Engine Code Editor and Earth Engine Apps. Written by gee/build.py from\n'
		        '// catalog.js, core.js and ui.js of https://github.com/monitoreo-obsnev/monitoreo: do not edit.\n\n')
		f.write(text)


def _js(value, depth=0):
	"""VALUE in JSON (a valid expression of JavaScript) with a line for each key of an object and each element of an
	array of objects or arrays, down to DEPTH 3: a line is a variable, a dataset or a text of the about, not a whole
	key of the catalog."""
	if depth < 3 and isinstance(value, dict) and value:
		return '{\n' + ',\n'.join(json.dumps(k, ensure_ascii=False) + ':' + _js(v, depth + 1)
		                          for k, v in value.items()) + '\n}'
	if depth < 3 and isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value):
		return '[\n' + ',\n'.join(_js(v, depth + 1) for v in value) + '\n]'
	return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _catalog_module(n, keys, entries):
	head = (f'MonitorEO for Earth Engine Apps: part {n} of the catalog (catalog.js), with its keys {", ".join(keys)}, '
	        'required by the script app of this repository. Written by gee/build.py from catalog.js of '
	        'https://github.com/monitoreo-obsnev/monitoreo: do not edit.')
	return (''.join(f'// {line}\n' for line in textwrap.wrap(head, 117, break_on_hyphens=False)) +
	        'exports.part = {\n' + ',\n'.join(entries[k] for k in keys) + '\n};\n')


def catalog_modules(data, limit=LIMIT):
	"""The modules of the catalog DATA (that of catalog.js) for the git repository of the app, [text of catalog_1,
	text of catalog_2...]: its keys, in their order, packed greedily into modules that set exports.part (an object
	with some keys of the catalog), each of at most LIMIT bytes, in ASCII. ValueError if a key alone does not fit."""
	entries = {k: ascii_js(json.dumps(k) + ':' + _js(v, 1)) for k, v in data.items()}
	out, keys = [], []
	for k in data:
		if keys and len(_catalog_module(len(out) + 1, keys + [k], entries)) > limit:
			out.append(_catalog_module(len(out) + 1, keys, entries))
			keys = []
		keys.append(k)
		if len(keys) == 1 and len(_catalog_module(len(out) + 1, keys, entries)) > limit:
			raise ValueError(f'the key {k!r} of the catalog alone takes '
			                 f'{len(_catalog_module(len(out) + 1, keys, entries))} bytes in a module, over the limit of '
			                 f'{limit} bytes of a file of the repository of the app: split it in gee/build.py')
	if keys:
		out.append(_catalog_module(len(out) + 1, keys, entries))
	return out


def modules(repo=REPO, limit=LIMIT):
	"""The files of the git repository REPO of the app in Earth Engine, {name: text}, from the catalog.js, core.js and
	ui.js there are (without Earth Engine): app, the script published (the catalog filled from the modules, then
	core.js and ui.js as they are), and catalog_1, catalog_2..., the modules of the catalog (catalog_modules). Earth
	Engine refuses any file over 512 KiB (MAX_FILE), so each is in ASCII (with the \\u escapes of monitoreo_app.js)
	and of at most LIMIT bytes. The app requires each module by its literal path (REPO:catalog_1), as Earth Engine
	needs to bundle them when it publishes the app. ValueError if a file does not fit in LIMIT."""
	if not re.fullmatch(r'[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+', repo):
		raise ValueError(f'{repo!r} is not the path of a repository of Earth Engine (e.g. {REPO})')
	parts = catalog_modules(read_catalog(), limit)
	names = [f'catalog_{n}' for n in range(1, len(parts) + 1)]
	requires = ',\n'.join(f"\trequire('{repo}:{name}')" for name in names)
	head = (f'// MonitorEO for Earth Engine Apps: the script app of the repository {repo}, published\n'
	        f'// with Apps > the pencil of MonitorEO > Overwrite from repository script path {repo}:app.\n'
	        '// Written by gee/build.py from catalog.js, core.js and ui.js of\n'
	        '// https://github.com/monitoreo-obsnev/monitoreo: do not edit. The catalog is in the modules catalog_1,\n'
	        '// catalog_2... that it requires: Earth Engine refuses any file of a repository over 512 KiB.\n'
	        '\n'
	        'var CATALOG = {};\n'
	        f'[\n{requires}\n].forEach(function (m) {{\n'
	        '\tfor (var key in m.part) CATALOG[key] = m.part[key];\n'
	        '});\n\n')
	files = {'app': head + ascii_js('\n'.join(_read(name) for name in ('core.js', 'ui.js')))}
	files.update(zip(names, parts))
	for name, text in files.items():
		if len(text.encode('ascii')) > limit:
			raise ValueError(f'the file {name} of the repository of the app takes {len(text)} bytes, over the limit of '
			                 f'{limit}: split it in gee/build.py')
	return files


def write_modules(directory, files):
	"""Write FILES ({name: text}, those of modules) into DIRECTORY, and remove the files of an older build that are
	not among them (a catalog_N no longer needed); the other files stay. The names removed."""
	os.makedirs(directory, exist_ok=True)
	removed = sorted(n for n in os.listdir(directory)
	                 if MODULE.fullmatch(n) and n not in files and os.path.isfile(os.path.join(directory, n)))
	for name in removed:
		os.remove(os.path.join(directory, name))
	for name, text in files.items():
		with open(os.path.join(directory, name), 'w', encoding='ascii', newline='\n') as f:
			f.write(text)
	return removed


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument('--project', help='Earth Engine project (default: EE_PROJECT)')
	parser.add_argument('--app-only', action='store_true',
	                    help='only write monitoreo_app.js, from the catalog.js there is (without Earth Engine)')
	parser.add_argument('--indexes-only', action='store_true',
	                    help='write the indexes of catalog.js again (the GEE Community Catalog and the Earth Engine data '
	                         'catalog) and monitoreo_app.js, without Earth Engine: after refreshing them')
	parser.add_argument('--about-only', action='store_true',
	                    help='write the about of catalog.js again (version, date of the release, links of suggestions; '
	                         'its logos as they were) and monitoreo_app.js, without Earth Engine: at each release')
	parser.add_argument('--modules', metavar='DIR',
	                    help='only write the files of the git repository of the app in Earth Engine (app, catalog_1, '
	                         'catalog_2...) into DIR, from the catalog.js, core.js and ui.js there are, without Earth '
	                         'Engine (gee/push_app.py publishes them)')
	parser.add_argument('--repo', default=REPO,
	                    help=f'with --modules, the repository of Earth Engine the app requires its modules from '
	                         f'(default: {REPO})')
	args = parser.parse_args()
	if args.modules:
		files = modules(args.repo)
		removed = write_modules(args.modules, files)
		for name, text in files.items():
			print(f'wrote {name} ({len(text)} bytes)')
		if removed:
			print(f"removed {', '.join(removed)}")
		print(f'the app is {args.repo}:app')
		return
	if args.app_only:
		app()
		print('wrote monitoreo_app.js (catalog.js as it was)')
		return
	if args.indexes_only:
		data = read_catalog()
		data['community'] = community_index()
		data['eecatalog'] = eecatalog_index()
		write_catalog(data)
		app()
		print(f"wrote the indexes of catalog.js ({len(data['eecatalog']['datasets'])} datasets of the Earth Engine data "
		      'catalog) and monitoreo_app.js')
		return
	if args.about_only:
		data = read_catalog()
		data['about'] = dict(about_texts(logos=False), logos=data['about'].get('logos', []))
		write_catalog(data)
		app()
		print(f'wrote the about of catalog.js (MonitorEO {__version__}, released {__released__}) and monitoreo_app.js')
		return
	services.init(args.project)
	data = {'variables': entries(), 'collections': catalog.load()['collections'], 'about': about_texts(),
	        'landcover': catalog.load()['landcover'],  # the land cover maps and their classes (monitoreo.landcover)
	        'themes': catalog.THEMES, 'other_themes': catalog.OTHER_THEMES, 'community': community_index(),
	        'eecatalog': eecatalog_index()}
	write_catalog(data)
	app()
	print(f"{len(data['variables'])} variables and {len(data['community']['datasets'])} datasets of the GEE Community "
	      'Catalog; wrote catalog.js and monitoreo_app.js')


if __name__ == '__main__':
	main()
