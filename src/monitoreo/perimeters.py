"""Official perimeters as regions (see areas.region): the observed event of a rapid mapping activation of the Copernicus
Emergency Management Service (EMS), a burnt area of the European Forest Fire Information System (EFFIS), a layer of a
Web Feature Service (e.g. the burnt areas of ICNF, in Portugal) or a vector file on the web (e.g. the fire perimeters
of REDIAM, in Andalusia):

    {"ems": "EMSR375"}                          the burnt (flooded...) area of each area of interest (AOI) of the
                                                activation: that of its grading product or, without one, of its last
                                                delineation; aoi (its number), product ("delineation" or "grading")
                                                and monitoring (its number, 0 the first product) choose others
    {"effis_id": 17545}                         a burnt area of EFFIS (2000 to today; find_burnt_areas finds them)
    {"wfs": URL, "layer": "BDG:ardida_2022"}    the features of a layer of a WFS; cql_filter (sent to the server, as
                                                GeoServer understands it), filter (an OGR SQL condition on its fields,
                                                applied here), name_field and dissolve (one feature) optional
    {"url": URL}                                a vector file on the web (GeoJSON, GeoPackage, KML, a zipped
                                                shapefile...); layer, filter, name_field and dissolve optional

They are downloaded once to FOLDER (~/MonitorEO/perimeters, or that of MONITOREO_OUTPUT), with a note of where each
file comes from, and read with GDAL (osgeo). The answers of the services are kept CACHE_DAYS days, and the products of
EMS (each version of each has its own name) for ever. Their polygons go to Earth Engine simplified by MAX_ERROR metres.
The results cite their sources (credits): EMS as its citation guidelines ask, EFFIS by San-Miguel-Ayanz et al.
(2012), the others by their URL.

What the services answer is data: nothing of it is run, and only their polygons, names, dates and areas are read.
"""

import datetime as dt
import hashlib
import json
import os
import re

EMS_API = 'https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/'
EMS_PAGE = 'https://mapping.emergency.copernicus.eu/activations/{code}/'
EFFIS_API = 'https://api.effis.emergency.copernicus.eu/rest/2/burntareas/current/'
EFFIS_WFS = 'https://maps.effis.emergency.copernicus.eu/effis'
EFFIS_LAYER = 'ms:modis.ba.poly'
EFFIS_PAGE = 'https://forest-fire.emergency.copernicus.eu/'
EFFIS_CREDIT = ('Burnt areas of the European Forest Fire Information System (EFFIS), Copernicus Emergency Management '
                f'Service: {EFFIS_PAGE}')
KEYS = ('ems', 'effis_id', 'wfs', 'url')
OPTIONS = {'ems': ('aoi', 'product', 'monitoring'), 'effis_id': (),
           'wfs': ('layer', 'cql_filter', 'filter', 'name_field', 'dissolve'),
           'url': ('layer', 'filter', 'name_field', 'dissolve')}
PRODUCTS = {'del': 'DEL', 'delineation': 'DEL', 'gra': 'GRA', 'grading': 'GRA'}
PRODUCT_NAMES = {'DEL': 'Delineation Map', 'GRA': 'Grading Map'}  # as the citation guidelines of EMS name them
EMS_CODE = re.compile(r'^EMSR\d{2,4}$')
# The vector packages of the activations before the dashboard of EMS (2023), linked from their page
EMS_ZIP = re.compile(r'https://[^"\s]+/(EMSR\d+)_AOI(\d+)_(DEL|GRA)_(PRODUCT|MONIT(\d+))_r(\d+)_RTP\d+_v(\d+)'
                     r'_vector\.zip')
DRIVERS = ['GeoJSON', 'GPKG', 'ESRI Shapefile', 'KML', 'LIBKML', 'GML', 'FlatGeobuf', 'OpenFileGDB', 'GPX', 'MapInfo File']
VECTOR_FILES = ('.geojson', '.json', '.gpkg', '.shp', '.kml', '.gml', '.fgb', '.gdb', '.gpx', '.tab')
MAX_ERROR = 5  # metres: simplification of the polygons sent to Earth Engine
CACHE_DAYS = 7
MAX_BYTES = 500 * 2 ** 20  # the biggest download
TIMEOUT = 120
FOLDER = os.path.join(os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO'), 'perimeters')

_memo = {}  # {spec as JSON: [{'name', 'geometry'}]}
_credits = {}  # {spec as JSON: [credit lines]}
_names = {}  # {spec as JSON: the text of the region}


# Checks, without the network ---------------------------------------------------------------------------------------

def _ids(v):
	ids = v if isinstance(v, (list, tuple)) else [v]
	try:
		out = [int(x) for x in ids]
	except (TypeError, ValueError):
		out = []
	if not out or any(str(x).strip() != str(i) for x, i in zip(ids, out)) or any(i <= 0 for i in out):
		raise ValueError('effis_id is the id of a burnt area of EFFIS (a whole number), or a list of them: '
		                 'find_burnt_areas finds them')
	return out


def ems_code(v):
	code = str(v or '').strip().upper()
	if not EMS_CODE.match(code):
		raise ValueError(f'ems is the code of a rapid mapping activation of Copernicus EMS, e.g. "EMSR375", not {v!r}')
	return code


def product(v):
	if v in (None, ''):
		return None
	p = PRODUCTS.get(str(v).strip().lower())
	if not p:
		raise ValueError(f'the product of ems is "delineation" or "grading", not {v!r}')
	return p


def _whole(v, what):
	if v in (None, ''):
		return None
	try:
		n = int(v)
	except (TypeError, ValueError):
		n = -1
	if n < 0 or str(v).strip() != str(n):
		raise ValueError(f'{what} is a whole number, not {v!r}')
	return n


def _web(v, key):
	if not isinstance(v, str) or not re.match(r'^https?://\S+$', v.strip()):
		raise ValueError(f'{key} is the address (http or https) of {"a WFS" if key == "wfs" else "a vector file"}, '
		                 f'not {v!r}')
	return v.strip()


def check(key, spec):
	"""Check the region SPEC of KEY (one of KEYS) without the network; else ValueError."""
	v = spec[key]
	if key == 'ems':
		ems_code(v)
		product(spec.get('product'))
		_whole(spec.get('aoi'), 'aoi')
		_whole(spec.get('monitoring'), 'monitoring')
	elif key == 'effis_id':
		_ids(v)
	else:
		_web(v, key)
		if key == 'wfs' and not str(spec.get('layer') or '').strip():
			raise ValueError('wfs takes layer, the name of the layer (typeName) of the WFS, as its GetCapabilities '
			                 'lists them')
	known = set(OPTIONS[key]) | {key, 'within'}
	other = sorted(k for k in spec if k not in known and spec[k] is not None)
	if other:
		raise ValueError(f"{key} takes {', '.join(OPTIONS[key]) or 'no other option'}, not {', '.join(other)}")
	return key


def _key(key, spec):
	return json.dumps({k: spec.get(k) for k in (key,) + OPTIONS[key] if spec.get(k) is not None}, sort_keys=True)


# Downloads ---------------------------------------------------------------------------------------------------------

def _agent():
	from . import __version__
	return {'User-Agent': f'MonitorEO/{__version__} (+https://github.com/monitoreo-obsnev/monitoreo)'}


def _path(url, params, ext):
	h = hashlib.sha1(json.dumps([url, params or {}], sort_keys=True).encode()).hexdigest()[:16]
	name = re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.basename(url.split('?')[0]) or 'data')[:60]
	if ext and not name.lower().endswith(ext):
		name += ext
	return os.path.join(FOLDER, f'{h}_{name}')


def _fresh(path, days):
	if not os.path.exists(path):
		return False
	if days is None:
		return True
	return (dt.datetime.now().timestamp() - os.path.getmtime(path)) < days * 86400


def download(url, params=None, ext='', days=CACHE_DAYS):
	"""The local copy of URL (with the query PARAMS) in FOLDER: downloaded unless a copy of less than DAYS days (any,
	with None) is there; if the download fails, an older copy, else ValueError. A note (the file + '.txt') says where
	it comes from and when."""
	import requests
	path = _path(url, params, ext)
	if _fresh(path, days):
		return path
	import tempfile
	os.makedirs(FOLDER, exist_ok=True)
	fd, tmp = tempfile.mkstemp(suffix='.part', dir=FOLDER)  # its own file: other processes may download it too
	try:
		with requests.get(url, params=params, headers=_agent(), timeout=TIMEOUT, stream=True) as r:
			r.raise_for_status()
			size = 0
			with os.fdopen(fd, 'wb') as f:
				for chunk in r.iter_content(1 << 20):
					size += len(chunk)
					if size > MAX_BYTES:
						raise ValueError(f'{url} is bigger than {MAX_BYTES // 2 ** 20} MB: download it yourself and '
						                 'use it as {"file": ...}')
					f.write(chunk)
			final = r.url
		os.replace(tmp, path)
		with open(path + '.txt', 'w', encoding='utf-8') as f:
			f.write(f'{final}\n{size} bytes, downloaded on {dt.datetime.now().isoformat(timespec="seconds")} by '
			        f'MonitorEO to use it as a region\n')
		return path
	except (requests.RequestException, OSError) as e:
		if os.path.exists(path):
			return path
		raise ValueError(f'cannot download {url}: {e}') from None
	finally:
		if os.path.exists(tmp):
			os.remove(tmp)


def _json(url, params=None, days=CACHE_DAYS):
	path = download(url, params, '.json', days)
	with open(path, encoding='utf-8') as f:
		try:
			return json.load(f)
		except ValueError:
			os.remove(path)
			raise ValueError(f'{url} did not answer with JSON') from None


# Reading polygons --------------------------------------------------------------------------------------------------

def _layer(ds, layer, path):
	names = [ds.GetLayer(i).GetName() for i in range(ds.GetLayerCount())]
	if not layer:
		return ds.GetLayer(0)
	if layer in names:
		return ds.GetLayerByName(layer)
	like = [n for n in names if str(layer).lower() in n.lower()]
	if len(like) == 1:
		return ds.GetLayerByName(like[0])
	raise ValueError(f"{os.path.basename(path)} has no layer {layer!r}: its layers are {', '.join(names)}")


def _polygons(g, ogr):
	"""The polygons of the OGR geometry G as a valid (Multi)Polygon in 2D (also those of the surfaces and curves of
	GML and of the collections), or None."""
	polys = (ogr.wkbPolygon, ogr.wkbMultiPolygon)
	g.FlattenTo2D()
	t = ogr.GT_Flatten(g.GetGeometryType())
	if t == ogr.wkbGeometryCollection:
		out = ogr.Geometry(ogr.wkbMultiPolygon)
		for k in range(g.GetGeometryCount()):
			p = _polygons(g.GetGeometryRef(k).Clone(), ogr)
			if p is not None:
				for q in ([p] if ogr.GT_Flatten(p.GetGeometryType()) == ogr.wkbPolygon else
				          [p.GetGeometryRef(j).Clone() for j in range(p.GetGeometryCount())]):
					out.AddGeometry(q)
		g = out if out.GetGeometryCount() else None
	elif t not in polys:  # the surfaces and curves of GML
		g = ogr.ForceToMultiPolygon(g)
		if g is None or ogr.GT_Flatten(g.GetGeometryType()) != ogr.wkbMultiPolygon or not g.GetGeometryCount():
			return None
	if g is not None and not g.IsValid():  # e.g. a ring that crosses itself: GEOS cannot join it
		g = g.MakeValid() if hasattr(g, 'MakeValid') else g.Buffer(0)
		if g is not None and ogr.GT_Flatten(g.GetGeometryType()) not in polys:
			return _polygons(g, ogr) if ogr.GT_Flatten(g.GetGeometryType()) == ogr.wkbGeometryCollection else None
	return g if g is not None and not g.IsEmpty() else None


def read(path, layer=None, where=None, name_field=None, dissolve=False, name=None):
	"""The polygons of the vector file PATH (also a zip, through /vsizip/), in EPSG:4326 and simplified by
	MAX_ERROR m: [{'name', 'geometry' (GeoJSON)}]; LAYER (its name, or a part of it), WHERE (an OGR SQL condition on
	its fields), NAME_FIELD (the field that names them; else NAME and their number), DISSOLVE (all of them as one
	feature, named NAME). ValueError without polygons."""
	from . import areas
	ogr, osr = areas._ogr(), areas._osr()
	from osgeo import gdal
	with open(path, 'rb') as f:
		zipped = f.read(4) == b'PK\x03\x04' and not path.lower().endswith(('.gpkg', '.kmz', '.xlsx'))
	def open_(p):
		try:
			return gdal.OpenEx(p, gdal.OF_VECTOR | gdal.OF_READONLY, allowed_drivers=DRIVERS)
		except RuntimeError:
			return None
	inside = '/vsizip/{' + os.path.abspath(path) + '}'  # with braces: also a zip without the extension .zip
	ds = open_(inside if zipped else path)
	if ds is None and zipped:  # a zip of one GeoJSON, GeoPackage...: the first file inside it that can be read
		for name in sorted(gdal.ReadDirRecursive(inside) or []):
			if name.lower().endswith(VECTOR_FILES):
				ds = open_(f'{inside}/{name}')
				if ds is not None:
					break
	if ds is None:
		raise ValueError(f'cannot read {os.path.basename(path)} as a vector file ({", ".join(DRIVERS)})')
	lyr = _layer(ds, layer, path)
	if where:
		try:
			lyr.SetAttributeFilter(where)
		except RuntimeError as e:
			fields = [lyr.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(lyr.GetLayerDefn().GetFieldCount())]
			raise ValueError(f'filter {where!r}: {e}; the fields are {", ".join(fields)}') from None
	srs = lyr.GetSpatialRef()
	srs = srs.Clone() if srs is not None else areas.wgs84()
	srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
	out = []
	for i, feat in enumerate(lyr, 1):
		g = feat.GetGeometryRef()
		if g is None:
			continue
		g = _polygons(g.Clone(), ogr)
		if g is None:
			continue
		if name_field and feat.GetFieldIndex(name_field) < 0:
			raise ValueError(f'{os.path.basename(path)} has no field {name_field!r}')
		label = feat.GetField(name_field) if name_field else None
		out.append((g, str(label) if label not in (None, '') else f'{name or "Feature"} {i}'))
	if not out:
		raise ValueError(f'{os.path.basename(path)} has no polygons' + (f' with {where}' if where else ''))
	if dissolve:
		parts = ogr.Geometry(ogr.wkbMultiPolygon)
		for g, _ in out:
			for k in range(g.GetGeometryCount()) if ogr.GT_Flatten(g.GetGeometryType()) == ogr.wkbMultiPolygon \
					else [None]:
				parts.AddGeometry(g if k is None else g.GetGeometryRef(k))
		try:
			union = parts.UnionCascaded()
		except RuntimeError as e:
			raise ValueError(f'cannot join the polygons of {os.path.basename(path)}: {e}') from None
		out = [(union, name or out[0][1])]
	feats = []
	for g, label in out:
		utm = areas.srs_of(areas.utm_crs(g, srs))
		g = areas.transform(areas.transform(g, srs, utm).SimplifyPreserveTopology(MAX_ERROR), utm, areas.wgs84())
		if not g.IsEmpty():
			feats.append({'name': label, 'geometry': json.loads(g.ExportToJson())})
	return feats


# Copernicus EMS ----------------------------------------------------------------------------------------------------

def _ems_api(code):
	"""The products with an observed event of an activation of the dashboard of EMS (2023 on), or None:
	[{'aoi', 'aoi_name', 'type', 'monitoring', 'url' (GeoJSON), 'delivery'}], and the year of the activation."""
	try:
		d = _json(EMS_API, {'code': code})
	except ValueError:
		return None, None
	results = d.get('results') if isinstance(d, dict) else None
	act = next((r for r in results if isinstance(r, dict) and r.get('code') == code), None) \
		if isinstance(results, list) else None
	if not act:
		return None, None
	out = []
	for a in act.get('aois') if isinstance(act.get('aois'), list) else []:
		if not isinstance(a, dict):
			continue
		for p in a.get('products') if isinstance(a.get('products'), list) else []:
			if not isinstance(p, dict):
				continue
			layer = next((l.get('json') for l in p.get('layers') or [] if isinstance(l, dict)
			              and 'observedEventA' in str(l.get('name')) and str(l.get('json') or '').startswith('https://')),
			             None)
			if layer and p.get('type') in PRODUCT_NAMES:
				out.append({'aoi': int(a.get('number') or 0), 'aoi_name': a.get('name') or '', 'type': p['type'],
				            'monitoring': int(p.get('monitoringNumber') or 0), 'url': layer,
				            'delivery': str((p.get('version') if isinstance(p.get('version'), dict) else {})
				                            .get('deliveryTime') or '')})
	year = str(act.get('activationTime') or act.get('eventTime') or '')[:4]
	return out, year if year.isdigit() else None


def _ems_page(code):
	"""The same from the page of an activation before the dashboard: its vector packages (zip), the names of its AOIs
	and the year of its activation."""
	path = download(EMS_PAGE.format(code=code), None, '.html')
	with open(path, encoding='utf-8', errors='replace') as f:
		html = f.read()
	names = {int(n): t.strip() for n, t in re.findall(r'id="aoi-(\d+)-tab"[^>]*>\s*AOI\d+\s+([^<]+)<', html)}
	best = {}
	for m in EMS_ZIP.finditer(html):
		url, c, aoi, typ, _, mon, rel, ver = m.group(0), *m.groups()
		if c != code:
			continue
		k = (int(aoi), typ, int(mon or 0))
		order = (int(rel), int(ver))
		if k not in best or order > best[k][0]:
			best[k] = (order, url)
	out = [{'aoi': k[0], 'aoi_name': names.get(k[0], ''), 'type': k[1], 'monitoring': k[2], 'url': u, 'delivery': ''}
	       for k, (_, u) in best.items()]
	year = re.search(r'Activation time.*?\d{2}/\d{2}/(\d{4})', re.sub(r'<[^>]+>', ' ', html), re.S)
	return out, year.group(1) if year else None


def ems(code, aoi=None, product_=None, monitoring=None):
	"""The observed event of the activation CODE of EMS: a feature for each AOI (or that of AOI), from its grading
	product or, without one, its last delineation (PRODUCT_ and MONITORING choose another); and their credit
	lines."""
	code = ems_code(code)
	products, year = _ems_api(code)
	if not products:
		products, year = _ems_page(code)
	if not products:
		raise ValueError(f'{code} has no vector product with an observed event in Copernicus EMS (see '
		                 f'{EMS_PAGE.format(code=code)})')
	aois = sorted({p['aoi'] for p in products})
	if aoi is not None:
		if aoi not in aois:
			raise ValueError(f"{code} has no AOI {aoi} with an observed event: its AOIs are {', '.join(map(str, aois))}")
		aois = [aoi]
	feats, credits = [], []
	for n in aois:
		mine = [p for p in products if p['aoi'] == n]
		typ = product_ or ('GRA' if any(p['type'] == 'GRA' for p in mine) else 'DEL')
		mine = [p for p in mine if p['type'] == typ]
		if monitoring is not None:
			mine = [p for p in mine if p['monitoring'] == monitoring]
		if not mine:
			if aoi is None:  # the other AOIs may have it
				continue
			raise ValueError(f'{code} AOI{n:02d} has no {PRODUCT_NAMES[typ].lower()}'
			                 + (f' of monitoring {monitoring}' if monitoring is not None else ''))
		p = max(mine, key=lambda x: (x['monitoring'], x['delivery']))
		path = download(p['url'], None, '', None)
		layer = None if path.lower().endswith('.json') else 'observedEventA'
		label = f"{code} AOI{n:02d}{' ' + p['aoi_name'] if p['aoi_name'] else ''}: {PRODUCT_NAMES[typ]}" + \
			(f" (monitoring {p['monitoring']})" if p['monitoring'] else '')
		feats += read(path, layer, dissolve=True, name=label)
		credits.append(f"Copernicus Emergency Management Service (© {year + ' ' if year else ''}European Union), "
		               f"[{code}] {p['aoi_name'] + ' ' if p['aoi_name'] else ''}(AOI{n:02d}): {PRODUCT_NAMES[typ]}")
	if not feats:
		what = (PRODUCT_NAMES[product_].lower() if product_ else 'vector product') + \
			(f' of monitoring {monitoring}' if monitoring is not None else '')
		raise ValueError(f'{code} has no {what} with an observed event in Copernicus EMS')
	return feats, credits


# EFFIS -------------------------------------------------------------------------------------------------------------

def _effis_label(r):
	place = ', '.join(x for x in (r.get('commune'), r.get('province')) if x and x != 'N.A.')
	date = str(r.get('firedate') or '')[:10]
	area = r.get('area_ha')
	return f"EFFIS {r.get('id')}" + (f': {place}' if place else '') + (f', {date}' if date else '') + \
		(f', {area} ha' if area not in (None, '') else '')


def effis(ids):
	"""The burnt areas IDS of EFFIS, a feature each, and their credit line."""
	feats = []
	for i in _ids(ids):
		r = _json(f'{EFFIS_API}{i}/', {'format': 'json'})
		shape = r.get('shape') if isinstance(r, dict) else None
		if not shape:
			raise ValueError(f'EFFIS has no burnt area {i} (find_burnt_areas finds them)')
		path = _path(f'{EFFIS_API}{i}/', {'format': 'json'}, '.json')[:-len('.json')] + '_shape.geojson'
		os.makedirs(FOLDER, exist_ok=True)
		with open(path, 'w', encoding='utf-8') as f:
			json.dump({'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'geometry': shape,
			                                                      'properties': {}}]}, f)
		feats += read(path, dissolve=True, name=_effis_label(r))
	return feats, [EFFIS_CREDIT]


def find_burnt_areas(bounds=None, geometry=None, country=None, start=None, end=None, min_area_ha=None, limit=50):
	"""The burnt areas of EFFIS (2000 to today) in BOUNDS ([w, s, e, n]; those that touch GEOMETRY, a GeoJSON
	geometry in EPSG:4326, if given) or in COUNTRY (its two-letter code, e.g. ES or PT), that began between START and
	END (YYYY-MM-DD) and burnt at least MIN_AREA_HA hectares, the largest first, at most LIMIT: [{effis_id,
	firedate, finaldate, area_ha, country, province, commune, lastupdate, region}]."""
	rows = []
	if bounds:
		w, s, e, n = [float(x) for x in bounds]
		d = _json(EFFIS_WFS, {'service': 'WFS', 'request': 'GetFeature', 'version': '1.1.0', 'typename': EFFIS_LAYER,
		                      'srsName': 'EPSG:4326', 'bbox': f'{s},{w},{n},{e},EPSG:4326', 'outputformat': 'geojson'},
		          days=1)
		touch = None
		if geometry:
			from . import areas
			ogr = areas._ogr()
			touch = ogr.CreateGeometryFromJson(json.dumps(geometry))
		for f in d.get('features') or []:
			p = {k.lower(): v for k, v in (f.get('properties') or {}).items()}
			if touch is not None and f.get('geometry'):
				g = ogr.CreateGeometryFromJson(json.dumps(f['geometry']))
				if g is None or not g.Intersects(touch):
					continue
			rows.append(p)
	elif country:
		params = {'format': 'json', 'country': str(country).strip().upper(), 'ordering': '-area_ha',
		          'limit': int(limit)}
		if start:
			params['firedate__gte'] = str(start)[:10]
		if end:  # the whole day of END (firedate has an hour)
			params['firedate__lt'] = (dt.date.fromisoformat(str(end)[:10]) + dt.timedelta(days=1)).isoformat()
		if min_area_ha:
			params['area_ha__gte'] = int(float(min_area_ha))
		rows = list(_json(EFFIS_API, params, days=1).get('results') or [])
	else:
		raise ValueError('find_burnt_areas takes a region (its bounding box) or a country (e.g. "ES")')
	out = []
	for r in rows:
		date = str(r.get('firedate') or '')[:10]
		try:
			area = float(r.get('area_ha') or 0)
		except ValueError:
			area = 0
		if (start and date < str(start)[:10]) or (end and date > str(end)[:10]) or \
				(min_area_ha and area < float(min_area_ha)):
			continue
		i = int(r.get('id'))
		out.append({'effis_id': i, 'firedate': date, 'finaldate': str(r.get('finaldate') or '')[:10] or None,
		            'area_ha': area, 'country': r.get('country'), 'province': r.get('province'),
		            'commune': r.get('commune'), 'lastupdate': str(r.get('lastupdate') or '')[:10] or None,
		            'region': {'effis_id': i}})
	out.sort(key=lambda x: -x['area_ha'])
	return out[:int(limit)]


# WFS and files on the web ------------------------------------------------------------------------------------------

def wfs(url, layer, cql_filter=None, where=None, name_field=None, dissolve=False):
	"""The features of LAYER of the WFS at URL (GeoJSON in EPSG:4326 if the server gives it, else its GML), with the
	CQL_FILTER of the server and the OGR SQL condition WHERE; and their credit line."""
	url = _web(url, 'wfs')
	base = {'service': 'WFS', 'version': '2.0.0', 'request': 'GetFeature', 'typeNames': layer,
	        'srsName': 'EPSG:4326'}
	if cql_filter:
		base['CQL_FILTER'] = cql_filter
	path = None
	for fmt in ('application/json', None):
		params = dict(base, outputFormat=fmt) if fmt else base
		try:
			path = download(url, params, '.geojson' if fmt else '.gml')
		except ValueError:
			if fmt is None:
				raise
			continue
		with open(path, 'rb') as f:
			head = f.read(2048).lstrip()
		if fmt and head[:1] in (b'{', b'['):
			break
		if not fmt and b'ExceptionReport' not in head and b'ServiceException' not in head:
			break
		os.remove(path)
		path = None
	if path is None:
		raise ValueError(f'the WFS {url} gave no features of {layer}' + (f' with {cql_filter}' if cql_filter else ''))
	feats = read(path, None, where, name_field, dissolve, name=layer)
	return feats, [_static('wfs', {'wfs': url, 'layer': layer})]


def remote(url, layer=None, where=None, name_field=None, dissolve=False):
	"""The polygons of the vector file at URL; and their credit line."""
	url = _web(url, 'url')
	name = os.path.basename(url.split('?')[0]) or 'file'
	path = download(url, None, '', 30)
	feats = read(path, layer, where, name_field, dissolve, name=os.path.splitext(name)[0])
	return feats, [_static('url', {'url': url, 'layer': layer})]


# Regions -----------------------------------------------------------------------------------------------------------

def features(key, spec):
	"""The features of the region SPEC of KEY (see the docstring of the module): [{'name', 'geometry'}], fetched
	once per session."""
	check(key, spec)
	k = _key(key, spec)
	if k not in _memo:
		v = spec[key]
		if key == 'ems':
			feats, credits = ems(v, _whole(spec.get('aoi'), 'aoi'), product(spec.get('product')),
			                     _whole(spec.get('monitoring'), 'monitoring'))
		elif key == 'effis_id':
			feats, credits = effis(v)
		elif key == 'wfs':
			feats, credits = wfs(v, spec['layer'], spec.get('cql_filter'), spec.get('filter'), spec.get('name_field'),
			                     spec.get('dissolve'))
		else:
			feats, credits = remote(v, spec.get('layer'), spec.get('filter'), spec.get('name_field'),
			                        spec.get('dissolve'))
		_memo[k], _credits[k] = feats, credits
		_names[k] = '; '.join(f['name'] for f in feats[:5]) + (f' and {len(feats) - 5} more' if len(feats) > 5 else '')
	return _memo[k]


def _static(key, region):
	"""The credit line of a region of KEY that does not need its features (all but EMS, or EMS without them)."""
	if key == 'ems':
		return f'Copernicus Emergency Management Service (© European Union), [{ems_code(region[key])}]'
	if key == 'effis_id':
		return EFFIS_CREDIT
	if key == 'wfs':
		return f"Perimeters: layer {region.get('layer')} of the WFS {str(region[key]).split('?')[0]}"
	return f'Perimeters: {region[key]}' + (f", layer {region['layer']}" if region.get('layer') else '')


def credits(region):
	"""The credit lines of the perimeters of REGION (and of its within), [] for other regions. Only EMS needs the
	features (the year and the names of the AOIs, from the copies in FOLDER); without them (no network), a general
	line. Never fails."""
	if not isinstance(region, dict):
		return []
	out = []
	key = next((k for k in KEYS if region.get(k) is not None), None)
	if key == 'ems':
		try:
			features(key, region)
			out += _credits[_key(key, region)]
		except Exception:  # anything the answers of EMS or GDAL do: the general line
			try:
				out.append(_static(key, region))
			except ValueError:
				pass
	elif key:
		out.append(_static(key, region))
	if isinstance(region.get('within'), dict):
		out += [c for c in credits(region['within']) if c not in out]
	return out


def text(region):
	"""How REGION (one of KEYS) is named in the READMEs and reports: the names of its features if they were fetched in
	this session, else its definition."""
	key = next(k for k in KEYS if region.get(k) is not None)
	known = _names.get(_key(key, region))
	if key == 'ems':
		what = f"Copernicus EMS {str(region['ems']).upper()}" + (f", AOI{int(region['aoi']):02d}"
		                                                         if region.get('aoi') not in (None, '') else '')
		return f'{known} ({what}, observed event)' if known else f'Observed event of {what}'
	if key == 'effis_id':
		return f'{known} (burnt area of EFFIS)' if known else \
			'Burnt area of EFFIS ' + ', '.join(map(str, _ids(region['effis_id'])))
	if key == 'wfs':
		return f"Layer {region.get('layer')} of the WFS {region['wfs']}" + \
			(f" ({region['filter']})" if region.get('filter') else '') + \
			(f" (CQL: {region['cql_filter']})" if region.get('cql_filter') else '')
	return f"File {region['url']}" + (f", layer {region['layer']}" if region.get('layer') else '') + \
		(f" ({region['filter']})" if region.get('filter') else '')
