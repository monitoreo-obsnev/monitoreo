"""The oceans and seas of the world as regions of MonitorEO: the 101 sea areas of the International Hydrographic
Organization (its Limits of Oceans and Seas, S-23, with the Southern Ocean of Marine Regions), as Marine Regions gives
them in the intersect of the Exclusive Economic Zones and IHO sea areas, version 5 (Flanders Marine Institute 2024,
licence CC BY 4.0): its 572 parts dissolved by sea, in a public table of Earth Engine (ASSET), so that every tool
computes with the same ones, also the Earth Engine app; and an index of their names in the package (INDEX: the MRGID,
name, area and bounds of each one), to find them without Earth Engine. IHO Sea Areas version 3 itself has a licence
CC BY-NC-SA 4.0 (non commercial, share alike), so the sea areas are taken from the intersect, CC BY 4.0.

The table and the index are made by its maintainers, again when Marine Regions publishes a new version (VERSION):

    python -m monitoreo.seas harvest DIR       # the parts, from the WFS of Marine Regions (--source: a downloaded file)
    python -m monitoreo.seas index DIR         # a polygon per sea (seas.geojson) and the index of the package
    python -m monitoreo.seas upload DIR --project ee-ugr-default-project   # the table of Earth Engine

Each sea is given by its MRGID (the identifier of Marine Regions, e.g. 3324, the Alboran Sea) or by its name, in any
case and with or without accents ('Alboran Sea'): {"sea": 3324}, {"sea": "Alboran Sea"} or a list of them, a feature
per sea; {"sea_at": [lon, lat]} is the sea at a point. The oceans are what is left of them out of their seas: the
North Atlantic Ocean has neither the North Sea nor the Mediterranean. The seas are big regions: see
areas.LARGE_AREA_KM2.

Citation: Flanders Marine Institute (2024). The intersect of the Exclusive Economic Zones and IHO sea areas, version
5. Available online at https://www.marineregions.org/. https://doi.org/10.14284/699 (credit: CREDIT)."""

import gzip
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

WFS = 'https://geo.vliz.be/geoserver/MarineRegions/wfs'
LAYER = 'MarineRegions:eez_iho'  # the intersect of the EEZs and IHO sea areas: a part per sea and EEZ (or high seas)
VERSION = 5
DOI = '10.14284/699'
ASSET = 'projects/ee-ugr-default-project/assets/monitoreo/seas_iho'  # public: every account can read it
INDEX = os.path.join(os.path.dirname(__file__), 'seas.json.gz')
CREDIT = ('Oceans and seas: the IHO sea areas of the intersect of the Exclusive Economic Zones and IHO sea areas v5, '
          'Flanders Marine Institute, Marine Regions (CC BY 4.0), dissolved by sea by MonitorEO')
FIELDS = ('iho_mrgid', 'iho_sea', 'area_km2')  # of each part: its sea (MRGID and name) and its area (km²)
PAGE = 20  # parts of each request of the WFS (some have more than 1 MB of coordinates)
USER_AGENT = 'MonitorEO (monitoreo.seas)'
# The polygons are simplified (degrees, GDAL SimplifyPreserveTopology): about 100 m for the smaller seas and 1 km for
# the large ones (more than LARGE_KM2), whose pixels are of 1 to 10 km by default (areas.LARGE_AREA_KM2): else the
# coasts of the Arctic and of the archipelagos have more coordinates than a request to Earth Engine takes (10 MB)
TOLERANCE = 0.001
LARGE_TOLERANCE = 0.01
LARGE_KM2 = 100_000
DIGITS = 5  # decimals of the coordinates (about 1 m)


def _get(params, timeout=300, tries=4):
	"""The answer of the WFS to PARAMS, trying again (after 30 s, 60 s...) when the server fails (5xx, time-outs)."""
	import time
	url = WFS + '?' + urllib.parse.urlencode(params)
	req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
	for i in range(tries):
		try:
			with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310: the URL of Marine Regions  # noqa: S310
				return json.load(r)
		except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
			if i == tries - 1 or (isinstance(e, urllib.error.HTTPError) and e.code < 500):
				raise
			time.sleep(30 * (i + 1))


def _wfs_parts(progress=print, start=0, page_size=PAGE):
	"""The parts of LAYER of the WFS (GeoJSON features in EPSG:4326, longitude first), page by page, from the part
	START."""
	while True:
		page = _get({'SERVICE': 'WFS', 'VERSION': '2.0.0', 'REQUEST': 'GetFeature', 'TYPENAMES': LAYER,
		             'OUTPUTFORMAT': 'application/json', 'SRSNAME': 'EPSG:4326', 'SORTBY': 'mrgid',
		             'COUNT': page_size, 'STARTINDEX': start})
		feats = page.get('features') or []
		yield from feats
		start += len(feats)
		if progress:
			progress(f'{start} parts')
		if len(feats) < page_size:
			return


def _file_parts(path):
	"""The parts of a downloaded file of the intersect (GeoPackage or shapefile of Marine Regions), as GeoJSON
	features in EPSG:4326."""
	from osgeo import ogr, osr
	ogr.UseExceptions()
	ds = ogr.Open(path)
	lyr = ds.GetLayer(0)
	wgs = osr.SpatialReference()
	wgs.ImportFromEPSG(4326)
	wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
	src = lyr.GetSpatialRef()
	tr = None
	if src is not None and not src.IsSame(wgs):
		src = src.Clone()
		src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
		tr = osr.CoordinateTransformation(src, wgs)
	for feat in lyr:
		g = feat.GetGeometryRef()
		if g is None:
			continue
		g = g.Clone()
		if tr:
			g.Transform(tr)
		yield {'type': 'Feature', 'properties': {k: feat.GetField(k) for k in FIELDS},
		       'geometry': json.loads(g.ExportToJson())}


def harvest(folder, source=None, progress=print, start=0, page_size=PAGE):
	"""Download the parts of the intersect (their sea, iho_mrgid and iho_sea, their area, area_km2, and their
	polygons) to FOLDER/parts.geojson, a feature per line: from the WFS of Marine Regions or, with SOURCE, from a
	downloaded file (GeoPackage or shapefile). From the part START of the WFS, they are added to those of FOLDER: to go
	on with a download that stopped. Returns the number of parts written."""
	os.makedirs(folder, exist_ok=True)
	feats = _file_parts(source) if source else _wfs_parts(progress, start, page_size)
	n = 0
	with open(os.path.join(folder, 'parts.geojson'), 'a' if start and not source else 'w', encoding='utf-8') as fh:
		for f in feats:
			props = {k: f['properties'].get(k) for k in FIELDS}
			fh.write(json.dumps({'type': 'Feature', 'properties': props, 'geometry': f['geometry']},
			                    separators=(',', ':')) + '\n')
			n += 1
	return n


def _round(coords, digits=DIGITS):
	if isinstance(coords, (int, float)):
		return round(coords, digits)
	return [_round(c, digits) for c in coords]


def _polygons(g, ogr):
	"""The polygons of G (a union or a simplification can give a collection with lines or points) as a
	MultiPolygon."""
	out = ogr.Geometry(ogr.wkbMultiPolygon)

	def add(x):
		kind = ogr.GT_Flatten(x.GetGeometryType())
		if kind == ogr.wkbPolygon:
			out.AddGeometry(x)
		elif kind in (ogr.wkbMultiPolygon, ogr.wkbGeometryCollection):
			for i in range(x.GetGeometryCount()):
				add(x.GetGeometryRef(i))

	add(g)
	return out


def dissolve(folder, tolerance=TOLERANCE, large_tolerance=LARGE_TOLERANCE, progress=print):
	"""A polygon per sea from the parts of FOLDER (see harvest): the union of its parts (GDAL), simplified with
	TOLERANCE degrees (LARGE_TOLERANCE for the seas of more than LARGE_KM2), its coordinates rounded to DIGITS decimals,
	to FOLDER/seas.geojson (a feature per line: mrgid, name, area_km2, the sum of the areas of its parts, and bounds,
	[west, south, east, north]). Returns the number of seas."""
	from osgeo import ogr
	ogr.UseExceptions()
	seas = {}
	with open(os.path.join(folder, 'parts.geojson'), encoding='utf-8') as fh:
		for line in fh:
			f = json.loads(line)
			p = f['properties']
			s = seas.setdefault(int(p['iho_mrgid']), {'name': p['iho_sea'], 'area_km2': 0.0, 'parts': []})
			s['area_km2'] += float(p.get('area_km2') or 0)
			s['parts'].append(f['geometry'])
	with open(os.path.join(folder, 'seas.geojson'), 'w', encoding='utf-8') as fh:
		for i, (mrgid, s) in enumerate(sorted(seas.items(), key=lambda x: x[1]['name']), 1):
			union = ogr.Geometry(ogr.wkbMultiPolygon)
			for part in s['parts']:
				g = ogr.CreateGeometryFromJson(json.dumps(part))
				if not g.IsValid():
					g = g.MakeValid()
				polys = _polygons(g, ogr)
				for j in range(polys.GetGeometryCount()):
					union.AddGeometry(polys.GetGeometryRef(j))
			union = union.UnionCascaded()
			tol = large_tolerance if s['area_km2'] > LARGE_KM2 else tolerance
			geom = _polygons(union.SimplifyPreserveTopology(tol) if tol else union, ogr)
			if not geom.IsValid():
				geom = _polygons(geom.MakeValid(), ogr)
			w, e, south, n = geom.GetEnvelope()
			gj = json.loads(geom.ExportToJson())
			props = {'mrgid': mrgid, 'name': s['name'], 'area_km2': round(s['area_km2']),
			         'bounds': [round(w, 3), round(south, 3), round(e, 3), round(n, 3)]}
			fh.write(json.dumps({'type': 'Feature', 'properties': props,
			                     'geometry': {'type': gj['type'], 'coordinates': _round(gj['coordinates'])}},
			                    ensure_ascii=False, separators=(',', ':')) + '\n')
			if progress:
				progress(f"{i}/{len(seas)} {s['name']}")
	return len(seas)


def _rows(folder):
	with open(os.path.join(folder, 'seas.geojson'), encoding='utf-8') as fh:
		for line in fh:
			yield json.loads(line)


def make_index(folder, date):
	"""Write INDEX from FOLDER/seas.geojson (see dissolve), of DATE (YYYY-MM-DD, that of the version of Marine Regions):
	{'date', 'source', 'doi', 'version', 'asset', 'credit', 'rows': [[mrgid, name, area_km2, bounds]]}, sorted by
	name."""
	rows = sorted(([f['properties'][k] for k in ('mrgid', 'name', 'area_km2', 'bounds')] for f in _rows(folder)),
	              key=lambda r: r[1])
	data = {'date': date, 'source': f'{WFS} ({LAYER})', 'doi': DOI, 'version': VERSION, 'asset': ASSET,
	        'credit': CREDIT, 'rows': rows}
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


# the apostrophes typed in other ways (’ ‘ ʼ ´) as "'"
APOSTROPHES = str.maketrans(dict.fromkeys('’‘ʼ´', "'"))


def plain(text):
	"""TEXT in lower case, without accents, its apostrophes as "'" and every other sign that is not a letter, a digit
	or "'" as a space, its words separated by one space: 'Balearic (Iberian Sea)' is 'balearic iberian sea' and
	'Mediterranean Sea - Eastern Basin', 'mediterranean sea eastern basin'. The property search of the table of Earth
	Engine is this of the name (the app finds the seas with it)."""
	text = unicodedata.normalize('NFKD', str(text).translate(APOSTROPHES)).encode('ascii', 'ignore').decode('ascii')
	return ' '.join(re.sub(r"[^a-z0-9']+", ' ', text.lower()).split())


def find(text, limit=20):
	"""The seas whose name contains TEXT (any case and accents, see plain; also the beginning of an MRGID): the very
	name first, then those that begin with it, then the others, each group by name: [{'MRGID', 'NAME', 'AREA_KM2',
	'BOUNDS' ([west, south, east, north])}], without Earth Engine."""
	t = plain(text)
	found = []
	for mrgid, name, area, bounds in load()['rows']:
		n = plain(name)
		if t and t not in n and not str(mrgid).startswith(t):
			continue
		found.append(((n != t, not n.startswith(t), n), mrgid, name, area, bounds))
	found.sort(key=lambda x: x[0])
	return [{'MRGID': mrgid, 'NAME': name, 'AREA_KM2': area, 'BOUNDS': bounds}
	        for _, mrgid, name, area, bounds in found[:int(limit)]]


def _whole(x):
	try:
		f = float(str(x).strip())
	except (TypeError, ValueError):
		return None
	return int(f) if f == int(f) else None


def codes(v):
	"""The MRGIDs of the seas V (one, or a list: their MRGIDs, 3324 or '3324', or their names, in any case and with or
	without accents, e.g. 'alboran sea'), each once, in their order, checked against the index of the package without
	Earth Engine; else ValueError, with the way to find them."""
	values = list(v) if isinstance(v, (list, tuple)) else [v]
	rows = load()['rows']
	by_code = {r[0]: r[0] for r in rows}
	by_name = {plain(r[1]): r[0] for r in rows}
	out, unknown = [], []
	for x in values:
		c = _whole(x) if not isinstance(x, bool) else None
		code = by_code.get(c) if c is not None else by_name.get(plain(x))
		if code is None:
			unknown.append(str(x))
		elif code not in out:
			out.append(code)
	if not values or unknown:
		raise ValueError(f"sea is the MRGID of a sea area of the IHO (e.g. 3324) or its name (e.g. 'Alboran Sea'): "
		                 f"{', '.join(repr(u) for u in unknown) or 'none given'} is not one (find them with find_seas)")
	return out


def name_of(mrgid):
	"""The name of the sea of MRGID, or None."""
	c = _whole(mrgid)
	return next((r[1] for r in load()['rows'] if r[0] == c), None)


def area_of(mrgid):
	"""The area (km²) of the sea of MRGID in the index, or None."""
	c = _whole(mrgid)
	return next((r[2] for r in load()['rows'] if r[0] == c), None)


def simplified(geometry, tolerance):
	"""The GeoJSON GEOMETRY simplified with TOLERANCE degrees (GDAL, keeping its topology), for the tests of the
	tolerance."""
	from osgeo import ogr
	g = ogr.CreateGeometryFromJson(json.dumps(geometry))
	return json.loads(g.SimplifyPreserveTopology(tolerance).ExportToJson())


def parts_of(folder, chunk=3_500_000):
	"""The seas of FOLDER/seas.geojson (see dissolve) in parts of at most CHUNK bytes of GeoJSON (a request to Earth
	Engine takes at most 10 MB), in their order: the same parts each time, so that an upload can go on (see upload)."""
	parts, part, size = [], [], 0
	for f in _rows(folder):
		text = json.dumps(f)
		if len(text) > 9_000_000:
			raise ValueError(f"{f['properties']['name']} has {len(text):,} bytes of GeoJSON: more than a request to Earth "
			                 'Engine takes; simplify it more (dissolve with a bigger tolerance)')
		if part and size + len(text) > chunk:
			parts.append(part)
			part, size = [], 0
		part.append(f)
		size += len(text)
	if part:
		parts.append(part)
	return parts


def upload(folder, project, asset=ASSET, chunk=3_500_000, progress=print, pause=10):
	"""Upload FOLDER/seas.geojson (see dissolve) to the Earth Engine table ASSET of PROJECT, public: in parts (parts_of),
	each exported to a table of its own, then all of them into ASSET, and the parts deleted. The polygons are planar in
	EPSG:4326 (not geodesic: the limits of the oceans along a parallel stay on it). Each sea has the properties mrgid,
	name, area_km2 and search (its name as plain gives it: the Earth Engine app finds the seas with it). Uses the
	credentials given to ee.Initialize before (those of the owner of the project).
	An upload that stopped goes on: a part already in Earth Engine is kept, one whose export is waiting or running
	(READY, RUNNING: a project in the restricted mode of Earth Engine queues them for hours) is waited for, and only the
	others are exported again; if ASSET is there, only its access and the parts left are seen to. Returns the state of
	the export of ASSET, or None if it was there."""
	import time

	import ee

	def exists(path):
		try:
			ee.data.getAsset(path)
			return True
		except ee.EEException:
			return False

	def wait(task_id):
		while True:
			state = ee.data.getTaskStatus(task_id)[0]
			if state['state'] not in ('READY', 'RUNNING'):
				break
			time.sleep(pause)
		if state['state'] != 'COMPLETED':
			raise RuntimeError(f"{state.get('description')}: {state.get('state')} {state.get('error_message', '')}")
		return state

	parent = asset.rsplit('/', 1)[0]
	if not exists(parent):
		ee.data.createAsset({'type': 'FOLDER'}, parent)
	parts = parts_of(folder, chunk)
	ids = [f'{asset}_part{i:02d}' for i in range(len(parts))]
	there = exists(asset)
	active = {} if there else {t['description']: t['id'] for t in ee.data.getTaskList()
	                           if t.get('state') in ('READY', 'RUNNING')}
	waits = []
	for i, feats in enumerate([] if there else parts):
		pid, name = ids[i], f'seas_part{i:02d}'
		if exists(pid):
			what = 'already in Earth Engine'
		elif name in active:
			waits.append((i, active[name]))
			what = 'waiting for its export'
		else:
			fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f['geometry'], None, False),
			                                      {'mrgid': f['properties']['mrgid'], 'name': f['properties']['name'],
			                                       'area_km2': f['properties']['area_km2'],
			                                       'search': plain(f['properties']['name'])})
			                           for f in feats])
			task = ee.batch.Export.table.toAsset(fc, name, pid)
			task.start()
			waits.append((i, task.id))
			what = 'started'
		if progress:
			progress(f'part {i + 1}/{len(parts)} {what}: {len(feats)} seas')
	for i, task_id in waits:
		wait(task_id)
		if progress:
			progress(f'part {i + 1}/{len(parts)} done')
	state = None
	if not there:
		merged = ee.FeatureCollection([ee.FeatureCollection(p) for p in ids]).flatten()
		task = ee.batch.Export.table.toAsset(merged, 'seas_iho', asset)
		task.start()
		state = wait(task.id)
	ee.data.setAssetAcl(asset, {'all_users_can_read': True})
	for p in ids:
		if exists(p):
			ee.data.deleteAsset(p)
	return state


def main(argv=None):
	import argparse
	import datetime as dt
	p = argparse.ArgumentParser(prog='python -m monitoreo.seas', description=__doc__.split('\n\n')[0])
	sub = p.add_subparsers(dest='cmd', required=True)
	s = sub.add_parser('harvest', help='the parts of the intersect of the EEZs and IHO sea areas, to a folder')
	s.add_argument('folder')
	s.add_argument('--source', help='a downloaded GeoPackage or shapefile of the intersect, instead of the WFS')
	s.add_argument('--start', type=int, default=0, help='go on from this part of the WFS (a download that stopped)')
	s.add_argument('--page', type=int, default=PAGE, help='parts of each request (fewer if the server times out)')
	s = sub.add_parser('index', help='a polygon per sea and the index of the package, from a harvest')
	s.add_argument('folder')
	s.add_argument('--date', default=dt.date.today().isoformat(), help='the date of the data of Marine Regions')
	s.add_argument('--tolerance', type=float, default=TOLERANCE, help='simplification of the smaller seas (degrees)')
	s.add_argument('--large-tolerance', type=float, default=LARGE_TOLERANCE,
	               help=f'simplification of the seas of more than {LARGE_KM2:,} km² (degrees)')
	s = sub.add_parser('upload', help='the public table of Earth Engine, from the polygons of index')
	s.add_argument('folder')
	s.add_argument('--project', required=True)
	s.add_argument('--asset', default=ASSET)
	s.add_argument('--account', help='the Google account of gcloud that uploads it (default: that of earthengine)')
	a = p.parse_args(argv)
	if a.cmd == 'harvest':
		print(harvest(a.folder, a.source, start=a.start, page_size=a.page), 'parts', flush=True)
	elif a.cmd == 'index':
		print(dissolve(a.folder, a.tolerance, a.large_tolerance), 'seas;', make_index(a.folder, a.date), 'in', INDEX)
	else:
		import ee

		from . import municipalities
		ee.Initialize(municipalities.credentials(a.account) if a.account else None, project=a.project)
		print(upload(a.folder, a.project, a.asset))


if __name__ == '__main__':
	main()
