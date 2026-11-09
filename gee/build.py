"""Build the app of MonitorEO for the Earth Engine Code Editor from the Python package of this repository:

  catalog.js         the catalog (catalog.json with the corrections and the NBR of catalog.py), with the band of every
                     name of the formulas resolved as sensors.parse_formula does, and the texts of about.py
  monitoreo_app.js   catalog.js, core.js and ui.js in a single script: paste it in a new script of the Code Editor and
                     publish it as an app (Apps > New App)

Run it after changing catalog.json, about.py, core.js or ui.js (Earth Engine is needed for the band names):

  python gee/build.py --project my-ee-project
"""

import argparse
import base64
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from monitoreo import about, catalog, sensors, services  # noqa: E402

FIELDS = ['ref', 'type', 'type_en', 'index', 'vname', 'vname_en', 'sensor', 'col', 'm', 'tr', 'dr', 'unit', 'ft',
          'scale', 'offset', 'minp', 'maxp', 'pm', 'large_areas', 'two_periods', 'metric', 'axis', 'static', 'band',
          'terrain']
LOGO_WIDTHS = [340, 340, 200]  # pixels of the logos of about.LOGOS in the app (the Code Editor shows them at their size)


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


def about_texts():
	return {'name': 'MonitorEO-OBSNEV', 'description': about.DESCRIPTION, 'acknowledgements': about.ACKNOWLEDGEMENTS,
	        'citation': about.CITATION, 'doi': about.DOI, 'manual': about.MANUAL, 'repository': about.REPOSITORY,
	        'logos': [logo(p, w) for p, w in zip(about.LOGOS, LOGO_WIDTHS)]}


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument('--project', help='Earth Engine project (default: EE_PROJECT)')
	args = parser.parse_args()
	services.init(args.project)
	data = {'variables': entries(), 'collections': catalog.load()['collections'], 'about': about_texts()}
	text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)
	with open(os.path.join(HERE, 'catalog.js'), 'w', encoding='utf-8') as f:
		f.write('// Written by build.py from src/monitoreo (catalog.json, catalog.py, about.py): do not edit.\n')
		f.write(f'var CATALOG = {text};\n')
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
	print(f"{len(data['variables'])} variables; wrote catalog.js and monitoreo_app.js")


if __name__ == '__main__':
	main()
