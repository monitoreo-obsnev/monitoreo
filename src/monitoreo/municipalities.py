"""The municipalities of Spain, the administrative units of level 3 of MonitorEO (levels 1 and 2 are those of FAO GAUL
2025, see monitoreo.areas): their polygons, of the INSPIRE service of administrative units of the Instituto
Geográfico Nacional (IGN), in a public table of Earth Engine (ASSET), so that every tool computes with the same ones,
also the Earth Engine app, which cannot ask a WFS; and an index of their names in the package (INDEX: code, name,
province and autonomous community of each one), to find them without Earth Engine.

The table and the index are made from the WFS by its maintainers, again when the IGN updates its boundaries (every
three months; see the date of the index, DATE):

    python -m monitoreo.municipalities harvest DIR          # the polygons, from the WFS (GeoJSON files in DIR)
    python -m monitoreo.municipalities index DIR            # the index of the package, from them
    python -m monitoreo.municipalities upload DIR --project ee-ugr-default-project   # the table of Earth Engine

Each municipality is identified by its code of the INE (5 digits: province and municipality, e.g. '18134' Monachil):
{"admin3": "18134"} as a region, or a list of them. The 81 shared lands (mancomunidades, facerías, parzonerías) and
the territories without a municipality (Gibraltar, the islands of the north of Africa...) of the service are left out.

Licence: CC BY 4.0 ign.es (the conditions of use of the IGN, Orden FOM/2807/2015): the results of a region of them
credit it (CREDIT)."""

import gzip
import json
import os
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

WFS = 'https://www.ign.es/wfs-inspire/unidades-administrativas'
ASSET = 'projects/ee-ugr-default-project/assets/monitoreo/municipalities_es'  # public: every account can read it
INDEX = os.path.join(os.path.dirname(__file__), 'municipalities.json.gz')
LEVEL = 3  # the administrative level of MonitorEO of the municipalities (1 and 2: FAO GAUL)
COUNTRY = 'ESP'
CREDIT = ('Municipalities of Spain: derived from the INSPIRE administrative units of the Instituto Geográfico Nacional '
          '(CC BY 4.0 ign.es)')
NS = ('xmlns(au,http://inspire.ec.europa.eu/schemas/au/4.0),xmlns(gn,http://inspire.ec.europa.eu/schemas/gn/4.0),'
      'xmlns(xlink,http://www.w3.org/1999/xlink)')
ORDER = 'https://inspire.ec.europa.eu/codelist/AdministrativeHierarchyLevel/{}Order'
PAGE = 250  # features of each request of the WFS
USER_AGENT = 'MonitorEO (monitoreo.municipalities)'


def _level_filter(order):
	return ('<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0" '
	        'xmlns:au="http://inspire.ec.europa.eu/schemas/au/4.0" xmlns:xlink="http://www.w3.org/1999/xlink">'
	        '<fes:PropertyIsEqualTo><fes:ValueReference>au:nationalLevel/@xlink:href</fes:ValueReference>'
	        f'<fes:Literal>{ORDER.format(order)}</fes:Literal></fes:PropertyIsEqualTo></fes:Filter>')


def _get(params, timeout=300, tries=4):
	"""The answer of the WFS to PARAMS, trying again (after 30 s, 60 s...) when the server fails (5xx, time-outs)."""
	import time
	url = WFS + '?' + urllib.parse.urlencode(params)
	req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
	for i in range(tries):
		try:
			with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (the URL of the IGN above)
				return json.load(r)
		except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
			if i == tries - 1 or (isinstance(e, urllib.error.HTTPError) and e.code < 500):
				raise
			time.sleep(30 * (i + 1))


def _features(order, progress=print, start=0, page_size=PAGE):
	"""The administrative units of the WFS of national level ORDER ('1st' to '4th'), page by page, from the unit
	START."""
	while True:
		page = _get({'SERVICE': 'WFS', 'VERSION': '2.0.0', 'REQUEST': 'GetFeature', 'TYPENAMES': 'au:AdministrativeUnit',
		             'NAMESPACES': NS, 'OUTPUTFORMAT': 'application/geo+json', 'SRSNAME': 'EPSG:4326',
		             'FILTER': _level_filter(order), 'COUNT': page_size, 'STARTINDEX': start})
		feats = page.get('features') or []
		yield from feats
		start += len(feats)
		if progress:
			progress(f'{order} order: {start} units')
		if len(feats) < page_size:
			return


def _name(feature):
	return (((((feature['properties'].get('name') or {}).get('GeographicalName') or {}).get('spelling') or {})
	         .get('SpellingOfName') or {}).get('text'))


def _round(coords, digits=6):
	if isinstance(coords, (int, float)):
		return round(coords, digits)
	return [_round(c, digits) for c in coords]


def is_municipality(code):
	"""Whether the national code CODE of the WFS ('34' + autonomous community + province + INE code, 11 digits) is of a
	municipality of the INE: its province is that of its INE code (not a shared land, whose code begins with 53) and it
	is not a territory without a municipality (autonomous community 20)."""
	return len(code) == 11 and code[4:6] == code[6:8] and code[2:4] != '20'


def harvest(folder, progress=print, start=0, page_size=PAGE):
	"""Download from the WFS the municipalities (with their polygons, in EPSG:4326, rounded to 6 decimals: 0.1 m) and
	the names of the provinces and autonomous communities, to FOLDER: municipalities.geojson (a feature per line:
	code, name, province, region, national_code) and units.json. From the unit START (of the 4th order of the WFS),
	the municipalities are added to those of FOLDER: to go on with a download that stopped."""
	os.makedirs(folder, exist_ok=True)
	units = os.path.join(folder, 'units.json')
	if start and os.path.exists(units):  # going on: the names of the download that stopped
		with open(units, encoding='utf-8') as fh:
			names = json.load(fh)
	else:
		names = {}
		for order in ('2nd', '3rd'):  # the autonomous communities and the provinces: their names
			for f in _features(order, progress):
				names[f['properties']['nationalCode']] = _name(f)
		with open(units, 'w', encoding='utf-8') as fh:
			json.dump(names, fh, ensure_ascii=False)
	n = 0
	with open(os.path.join(folder, 'municipalities.geojson'), 'a' if start else 'w', encoding='utf-8') as fh:
		for f in _features('4th', progress, start, page_size):
			code = f['properties']['nationalCode']
			if not is_municipality(code):
				continue
			props = {'code': code[6:], 'name': _name(f), 'national_code': code,
			         'province': names.get(f'34{code[2:6]}00000'), 'region': names.get(f'34{code[2:4]}0000000')}
			geom = dict(f['geometry'], coordinates=_round(f['geometry']['coordinates']))
			fh.write(json.dumps({'type': 'Feature', 'properties': props, 'geometry': geom}, ensure_ascii=False,
			                    separators=(',', ':')) + '\n')
			n += 1
	return n


def _rows(folder):
	with open(os.path.join(folder, 'municipalities.geojson'), encoding='utf-8') as fh:
		for line in fh:
			yield json.loads(line)


def make_index(folder, date):
	"""Write INDEX from the harvest of FOLDER, of DATE (YYYY-MM-DD, that of the data of the IGN): {'date', 'source',
	'asset', 'rows': [[code, name, province, region]]}, sorted by code."""
	rows = sorted([f['properties'][k] for k in ('code', 'name', 'province', 'region')] for f in _rows(folder))
	data = {'date': date, 'source': WFS, 'asset': ASSET, 'credit': CREDIT, 'rows': rows}
	with gzip.open(INDEX, 'wt', encoding='utf-8') as fh:
		json.dump(data, fh, ensure_ascii=False, separators=(',', ':'))
	return len(rows)


_index = None


def load():
	"""The index of the package (see make_index)."""
	global _index
	if _index is None:
		with gzip.open(INDEX, 'rt', encoding='utf-8') as fh:
			_index = json.load(fh)
	return _index


def _plain(text):
	"""TEXT in lower case, without accents, and the separators of the bilingual names ('/', '-') as spaces."""
	text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode('ascii').lower()
	return ' '.join(text.replace('/', ' ').replace('-', ' ').split())


def find(text, province=None, limit=20):
	"""The municipalities whose name contains TEXT (any case and accents; also a code of the INE), in PROVINCE (its
	name or its 2 digits) if given, those whose name begins with it first: [{'ADMIN3_CODE', 'NAME', 'PROVINCE',
	'REGION', 'ISO3_CODE', 'DISP_EN', 'level'}] (the very name first, then those that begin with it), without Earth
	Engine."""
	t = _plain(text)
	prov = _plain(province) if province else None
	found = []
	for code, name, pname, region in load()['rows']:
		if prov and not (code[:2] == prov.zfill(2) if prov.isdigit() else prov in _plain(pname or '')):
			continue
		n = _plain(name)
		if t and t not in n and not code.startswith(t):
			continue
		found.append(((n != t, not n.startswith(t), n), code, name, pname, region))  # the very name first
	found.sort()
	return [{'ADMIN3_CODE': code, 'NAME': name, 'PROVINCE': pname, 'REGION': region, 'ISO3_CODE': COUNTRY,
	         'DISP_EN': f'{name} ({pname})', 'level': LEVEL} for _, code, name, pname, region in found[:int(limit)]]


def name_of(code):
	"""The name of the municipality of the INE code CODE, or None."""
	return next((r[1] for r in load()['rows'] if r[0] == str(code)), None)


def upload(folder, project, asset=ASSET, chunk=3_500_000, progress=print):
	"""Upload the harvest of FOLDER to the Earth Engine table ASSET of PROJECT, public: in parts of at most CHUNK bytes
	of GeoJSON (a request to Earth Engine takes at most 10 MB), each exported to a table of its own, then all of them
	into ASSET, and the parts deleted. Uses the credentials given to ee.Initialize before (those of the owner of the
	project). Each municipality has the properties code, name, province, region, national_code and search (its name in
	lower case and without accents, see _plain: the Earth Engine app finds them with it). Returns the state of the last
	export."""
	import time

	import ee
	parent = asset.rsplit('/', 1)[0]
	try:
		ee.data.getAsset(parent)
	except ee.EEException:
		ee.data.createAsset({'type': 'FOLDER'}, parent)
	parts, part, size = [], [], 0
	for f in _rows(folder):
		text = json.dumps(f)
		if part and size + len(text) > chunk:
			parts.append(part)
			part, size = [], 0
		part.append(f)
		size += len(text)
	if part:
		parts.append(part)

	def wait(task):
		while task.status()['state'] in ('READY', 'RUNNING'):
			time.sleep(10)
		state = task.status()
		if state['state'] != 'COMPLETED':
			raise RuntimeError(f"{state.get('description')}: {state.get('state')} {state.get('error_message', '')}")

	ids, tasks = [], []
	for i, feats in enumerate(parts):  # every part at once, then their wait
		fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f['geometry'], None, False),
		                                      dict(f['properties'], search=_plain(f['properties']['name'])))
		                           for f in feats])  # search: the name to find it in Earth Engine (the app)
		pid = f'{asset}_part{i:02d}'
		task = ee.batch.Export.table.toAsset(fc, f'municipalities_part{i:02d}', pid)
		task.start()
		ids.append(pid)
		tasks.append(task)
		if progress:
			progress(f'part {i + 1}/{len(parts)} started: {len(feats)} municipalities')
	for i, task in enumerate(tasks):
		wait(task)
		if progress:
			progress(f'part {i + 1}/{len(parts)} done')
	merged = ee.FeatureCollection([ee.FeatureCollection(p) for p in ids]).flatten()
	task = ee.batch.Export.table.toAsset(merged, 'municipalities_es', asset)
	task.start()
	wait(task)
	ee.data.setAssetAcl(asset, {'all_users_can_read': True})
	for p in ids:
		ee.data.deleteAsset(p)
	return task.status()


def credentials(account):
	"""Credentials of Earth Engine of the Google ACCOUNT signed in with gcloud (gcloud auth login ACCOUNT), for the
	owner of the project to upload the table."""
	import subprocess

	import google.oauth2.credentials
	token = subprocess.check_output(['gcloud', 'auth', 'print-access-token', '--account', account]).decode().strip()
	return google.oauth2.credentials.Credentials(token)


def main(argv=None):
	import argparse
	import datetime as dt
	p = argparse.ArgumentParser(prog='python -m monitoreo.municipalities', description=__doc__.split('\n\n')[0])
	sub = p.add_subparsers(dest='cmd', required=True)
	s = sub.add_parser('harvest', help='the municipalities from the WFS of the IGN, to a folder')
	s.add_argument('folder')
	s.add_argument('--start', type=int, default=0, help='go on from this unit of the WFS (a download that stopped)')
	s.add_argument('--page', type=int, default=PAGE, help='units of each request (fewer if the server times out)')
	s = sub.add_parser('index', help='the index of the package, from a harvest')
	s.add_argument('folder')
	s.add_argument('--date', default=dt.date.today().isoformat(), help='the date of the data of the IGN')
	s = sub.add_parser('upload', help='the public table of Earth Engine, from a harvest')
	s.add_argument('folder')
	s.add_argument('--project', required=True)
	s.add_argument('--asset', default=ASSET)
	s.add_argument('--account', help='the Google account of gcloud that uploads it (default: that of earthengine)')
	a = p.parse_args(argv)
	if a.cmd == 'harvest':
		print(harvest(a.folder, start=a.start, page_size=a.page), 'municipalities', flush=True)
	elif a.cmd == 'index':
		print(make_index(a.folder, a.date), 'municipalities in', INDEX)
	else:
		import ee
		ee.Initialize(credentials(a.account) if a.account else None, project=a.project)
		print(upload(a.folder, a.project, a.asset))


if __name__ == '__main__':
	main()
