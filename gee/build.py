"""Build the app of MonitorEO for the Earth Engine Code Editor from the Python package of this repository:

  catalog.js         the catalog (catalog.json with the corrections and the NBR of catalog.py), with the band of every
                     name of the formulas resolved as sensors.parse_formula does, the themes of the menu (also those of
                     the data of Earth Engine outside the catalog, catalog.OTHER_THEMES), a slim copy of the index of
                     the GEE Community Catalog (community.json.gz) and the texts of about.py
  monitoreo_app.js   catalog.js, core.js and ui.js in a single script: paste it in a new script of the Code Editor and
                     publish it as an app (Apps > New App)

Run it after changing catalog.json, about.py, community.json.gz, core.js or ui.js (Earth Engine is needed for the
band names):

  python gee/build.py --project my-ee-project

After changing only core.js or ui.js, monitoreo_app.js can be written from the catalog.js there is, without Earth
Engine:

  python gee/build.py --app-only
"""

import argparse
import base64
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from monitoreo import __released__, __version__, about, catalog, community, sensors, services  # noqa: E402

FIELDS = ['ref', 'type', 'type_en', 'index', 'vname', 'vname_en', 'sensor', 'col', 'm', 'tr', 'dr', 'unit', 'ft',
          'scale', 'offset', 'minp', 'maxp', 'pm', 'large_areas', 'two_periods', 'metric', 'axis', 'static', 'band',
          'terrain', 'image_asset', 'theme']
LOGO_WIDTHS = [340, 340, 200]  # pixels of the logos of about.LOGOS in the app (the Code Editor shows them at their size)
COMMUNITY_DOCS = community.SITE + '/projects/'  # where the pages of the datasets of the GEE Community Catalog are


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


def about_texts():
	return {'name': 'MonitorEO-OBSNEV', 'description': about.DESCRIPTION, 'acknowledgements': about.ACKNOWLEDGEMENTS,
	        'citation': about.CITATION, 'doi': about.DOI, 'manual': about.MANUAL, 'repository': about.REPOSITORY,
	        'feedback': dict(about.FEEDBACK, links=about.feedback('gee', __version__)),
	        'version': __version__, 'released': __released__,  # shown under the subtitle
	        'logos': [logo(p, w) for p, w in zip(about.LOGOS, LOGO_WIDTHS)]}


def app():
	"""Write monitoreo_app.js: catalog.js, core.js and ui.js in a single script."""
	parts = []
	for name in ('catalog.js', 'core.js', 'ui.js'):
		with open(os.path.join(HERE, name), encoding='utf-8') as f:
			parts.append(f.read())
	# ASCII only, with \u escapes (valid in the strings, regular expressions and comments of these files): pasting the
	# script in the Code Editor cannot then garble the accents
	text = '\n'.join(parts)
	text = ''.join(c if ord(c) < 128 else f'\\u{ord(c):04x}' for c in text)
	with open(os.path.join(HERE, 'monitoreo_app.js'), 'w', encoding='ascii') as f:
		f.write('// MonitorEO for the Earth Engine Code Editor and Earth Engine Apps. Written by gee/build.py from\n'
		        '// catalog.js, core.js and ui.js of https://github.com/monitoreo-obsnev/monitoreo: do not edit.\n\n')
		f.write(text)


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument('--project', help='Earth Engine project (default: EE_PROJECT)')
	parser.add_argument('--app-only', action='store_true',
	                    help='only write monitoreo_app.js, from the catalog.js there is (without Earth Engine)')
	args = parser.parse_args()
	if args.app_only:
		app()
		print('wrote monitoreo_app.js (catalog.js as it was)')
		return
	services.init(args.project)
	data = {'variables': entries(), 'collections': catalog.load()['collections'], 'about': about_texts(),
	        'landcover': catalog.load()['landcover'],  # the land cover maps and their classes (monitoreo.landcover)
	        'themes': catalog.THEMES, 'other_themes': catalog.OTHER_THEMES, 'community': community_index()}
	text = catalog_text(data)
	with open(os.path.join(HERE, 'catalog.js'), 'w', encoding='utf-8') as f:
		f.write('// Written by build.py from src/monitoreo (catalog.json, catalog.py, about.py, community.json.gz): do not '
		        'edit.\n')
		f.write(f'var CATALOG = {text};\n')
	app()
	print(f"{len(data['variables'])} variables and {len(data['community']['datasets'])} datasets of the GEE Community "
	      'Catalog; wrote catalog.js and monitoreo_app.js')


if __name__ == '__main__':
	main()
