"""Variables of Sentinel-2 and Landsat of MonitorEO computed on this computer, without Earth Engine.

The images come from the open catalog of Microsoft Planetary Computer (STAC and Cloud Optimized GeoTIFFs, no account
needed) and only the pixels of the region are read, with GDAL, as the Semi-Automatic Classification Plugin of QGIS
does. The variables, pixel filters, steps, metrics and statistics are those of the package, computed as Earth Engine
computes them (tests/test_local.py compares both):

  - Sentinel-2 L2A as COPERNICUS/S2_SR_HARMONIZED: the offset of 1000 of the processing baselines 04.00 and later is
    removed (values below it become 0, as in Earth Engine); clouds with the SCL classes, since Cloud Score+ is only in
    Earth Engine;
  - Landsat 5, 7 (until 2003-05-31), 8 and 9 Collection 2 Level 2 Tier 1, as LANDSAT/*/C02/T1_L2;
  - percentiles as Earth Engine (the value of rank n p / 100 + 0.5, interpolated: numpy's 'hazen'), standard
    deviation of the population, x / 0 = 0 in the formulas, and the normalized difference masked where a band is
    negative;
  - the pixels of a region are those with their centre inside it, on a grid of SCALE metres in the UTM zone of its
    centre; data of smaller pixels are averaged into bigger ones, as the pyramids of Earth Engine do.

Everything is read and computed here, so a long series of Sentinel-2 over a big region reads gigabytes: plan() says
where it is computed, with which credentials (none) and how many images and megabytes it reads, before starting.
Regions are GeoJSON, vector files, boxes or points (protected areas and ecoregions are looked up in Earth Engine).
Needs GDAL (osgeo) and numpy.
"""

import ast
import concurrent.futures as cf
import datetime as dt
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request

import numpy as np

from . import areas, composite, sensors, timeseries
from . import variable as variables
from .grid import NODATA, Grid

STAC = 'https://planetarycomputer.microsoft.com/api/stac/v1'
TOKENS = 'https://planetarycomputer.microsoft.com/api/sas/v1/token/'
WHERE = {'where': 'local', 'computed_on': 'on this computer',
         'data': 'Microsoft Planetary Computer (open data: Sentinel-2 L2A, Landsat Collection 2 Level 2)',
         'credentials': 'none'}
SENSORS = ('Sentinel-2', 'Landsat')
S2 = 'sentinel-2-l2a'
LANDSAT = 'landsat-c2-l2'
# Bands of Sentinel-2 with the names of the formulas (those of Earth Engine): asset of Planetary Computer, pixel (m)
S2_BANDS = {'B1': ('B01', 60), 'B2': ('B02', 10), 'B3': ('B03', 10), 'B4': ('B04', 10), 'B5': ('B05', 20),
            'B6': ('B06', 20), 'B7': ('B07', 20), 'B8': ('B08', 10), 'B8A': ('B8A', 20), 'B9': ('B09', 60),
            'B11': ('B11', 20), 'B12': ('B12', 20), 'SCL': ('SCL', 20)}
S2_OFFSET = ('04.00', 1000)  # the processing baselines from 04.00 (2022-01-25) add 1000 to the reflectances
# Before, Planetary Computer has other processings of Sentinel-2 than Earth Engine (baselines 02.12 and 03.00, made
# after ESA's; Earth Engine has those of ESA, 02.06 to 03.01, and some of 05.00): about 0.01 of NDVI apart
S2_SAME_FROM = '2022-01-25'
# Bands of Landsat with the names of the formulas (sensors.LANDSAT_57 and LANDSAT_89): asset of Planetary Computer
# (the surface temperature is lwir11 in Landsat 8 and 9, lwir in Landsat 5 and 7)
LANDSAT_BANDS = {'blue': 'blue', 'green': 'green', 'red': 'red', 'nir': 'nir08', 'swir1': 'swir16', 'swir2': 'swir22',
                 'st': ('lwir11', 'lwir'), 'QA_PIXEL': 'qa_pixel', 'SR_QA_AEROSOL': 'qa_aerosol'}
LANDSAT_PLATFORMS = {'LANDSAT/LT05/C02/T1_L2': 'landsat-5', 'LANDSAT/LE07/C02/T1_L2': 'landsat-7',
                     'LANDSAT/LC08/C02/T1_L2': 'landsat-8', 'LANDSAT/LC09/C02/T1_L2': 'landsat-9'}
SCENE_CLOUDS = {'Sentinel-2': 'eo:cloud_cover', 'Landsat': 'landsat:cloud_cover_land'}
QA_BANDS = {'SCL', 'QA_PIXEL', 'SR_QA_AEROSOL'}
GDAL_OPTIONS = {'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR', 'GDAL_HTTP_MERGE_CONSECUTIVE_RANGES': 'YES',
                'GDAL_HTTP_MULTIPLEX': 'YES', 'GDAL_HTTP_MAX_RETRY': '4', 'GDAL_HTTP_RETRY_DELAY': '2',
                'VSI_CACHE': 'TRUE'}
STREAM = ('mean', 'sum', 'min', 'max', 'std', 'count')  # metrics computed adding the images one at a time
MAX_STACK = 4e9  # bytes of the images of a step kept in memory for a median or a percentile
WORKERS = 8      # images read at the same time

_tokens = {}    # {collection: (token, expiry)}
_token_lock = threading.Lock()
_searches = {}  # {search: items}


# Planetary Computer ------------------------------------------------------------------------------------------------

def _json(url, body=None, retries=6):
	"""JSON answer of URL (POST of BODY if given), repeated when the server is busy (after the seconds it asks
	for, or 2, 4, 8, ... s)."""
	data = json.dumps(body).encode() if body is not None else None
	headers = {'Content-Type': 'application/json', 'User-Agent': 'monitoreo'}
	for attempt in range(retries):
		wait = 2 ** attempt * 2
		try:
			with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=120) as r:
				return json.load(r)
		except urllib.error.HTTPError as e:
			if attempt == retries - 1 or e.code not in (408, 429, 500, 502, 503, 504):
				raise RuntimeError(f'Microsoft Planetary Computer answered {e.code} to {url}: {e.read()[:300]!r}') from e
			wait = max(wait, int(e.headers.get('Retry-After') or 0) + 1)
		except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
			if attempt == retries - 1:
				raise RuntimeError(f'cannot reach Microsoft Planetary Computer ({url}): {e}') from e
		time.sleep(wait)


def _signed(href, collection):
	"""HREF with a token of the collection (anonymous: Planetary Computer gives them to anyone, for an hour)."""
	with _token_lock:  # one request per collection, not one per thread
		token, expiry = _tokens.get(collection, (None, 0))
		if time.time() > expiry - 600:
			t = _json(TOKENS + collection)
			token = t['token']
			expiry = dt.datetime.fromisoformat(t['msft:expiry'].replace('Z', '+00:00')).timestamp()
			_tokens[collection] = (token, expiry)
	return f'{href}?{token}'


def _search(collection, geom, start, end, query=None):
	"""STAC items of COLLECTION over GEOM (OGR, EPSG:4326) from START to END (excluded) with the conditions QUERY."""
	body = {'collections': [collection], 'intersects': _search_geometry(geom),
	        'datetime': f'{start}T00:00:00Z/{end}T00:00:00Z', 'limit': 1000}
	if query:
		body['query'] = query
	key = json.dumps(body, sort_keys=True)
	if key not in _searches:
		url, data, found = STAC + '/search', body, []
		while url:
			page = _json(url, data)
			found += page.get('features', [])
			nxt = next((link for link in page.get('links', []) if link.get('rel') == 'next'), None)
			url = nxt and nxt['href']
			if nxt and nxt.get('method', 'GET').upper() == 'POST':
				data = dict(data or {}, **nxt.get('body', {})) if nxt.get('merge') else nxt.get('body')
			else:
				data = None
		_searches[key] = [it for it in found if start <= _day(it) < end]
	return _searches[key]


def _search_geometry(geom):
	"""GeoJSON of GEOM for a search (its convex hull if it is too long)."""
	text = geom.ExportToJson()
	return json.loads(text if len(text) < 50000 else geom.ConvexHull().ExportToJson())


def _day(item):
	return item['properties']['datetime'][:10]


def items(entry, geom, start, end, quality=None):
	"""STAC items (dictionaries) of the images of the catalog entry ENTRY over GEOM (OGR, EPSG:4326) from START to END
	(excluded), sorted by date, as the collections of Earth Engine: Landsat 5, 7 (until 2003-05-31), 8 and 9 of Tier 1,
	or Sentinel-2 L2A with each granule processed once, the first time (Planetary Computer has also ESA's
	reprocessing of 2024, baseline 05.10, of many granules of 2022 and 2023; Earth Engine has the first ones)."""
	sensor = entry['sensor']
	scene = (quality or {}).get('scene_clouds')
	query = {SCENE_CLOUDS[sensor]: {'lte': scene}} if scene is not None else {}
	if sensor == 'Sentinel-2':
		first = {}
		for it in _search(S2, geom, start, end, query):
			key = (it['properties'].get('s2:mgrs_tile'), it['properties']['datetime'])
			if key not in first or it['id'] < first[key]['id']:  # the id ends with the date of processing
				first[key] = it
		out = list(first.values())
	else:
		out = []
		for col, _, last in sensors.LANDSAT:
			end_l = min(end, last) if last else end
			if end_l > start:
				q = dict(query, platform={'eq': LANDSAT_PLATFORMS[col]},
				         **{'landsat:collection_category': {'eq': 'T1'}})
				out += _search(LANDSAT, geom, start, end_l, q)
	return sorted(out, key=lambda it: (it['properties']['datetime'], it['id']))


def _warp(href, collection, grid, method, nodata, retries=4):
	"""Values of the raster HREF on GRID (NODATA where it has none), resampled with METHOD."""
	from osgeo import gdal
	gdal.UseExceptions()
	for k, v in GDAL_OPTIONS.items():
		gdal.SetThreadLocalConfigOption(k, v)
	for attempt in range(retries):
		try:
			ds = gdal.Warp('', '/vsicurl/' + _signed(href, collection), format='MEM', outputBounds=grid.extent,
			               width=grid.width, height=grid.height, dstSRS=grid.crs, resampleAlg=method,
			               srcNodata=nodata, dstNodata=nodata)
			return ds.GetRasterBand(1).ReadAsArray()
		except RuntimeError as e:
			if attempt == retries - 1:
				raise RuntimeError(f'cannot read {href} from Microsoft Planetary Computer: {e}') from e
			if '403' in str(e):  # an expired token
				with _token_lock:
					_tokens.pop(collection, None)
			time.sleep(2 ** attempt * 3)


# Formulas and reductions -------------------------------------------------------------------------------------------

def _divide(a, b):
	"""A / B with x / 0 = 0, as in the expressions of Earth Engine."""
	a, b = np.broadcast_arrays(np.asarray(a, np.float64), np.asarray(b, np.float64))
	return np.divide(a, b, out=np.zeros(a.shape), where=b != 0)


_OPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: _divide, ast.Pow: np.power}


def evaluate(formula, values):
	"""Value of a formula of the catalog (numbers, names of VALUES, + - * / ** and parentheses) with the arrays
	VALUES ({name: array}), as Earth Engine computes it (x / 0 = 0)."""
	def ev(node):
		if isinstance(node, ast.Expression):
			return ev(node.body)
		if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
			return _OPS[type(node.op)](ev(node.left), ev(node.right))
		if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
			v = ev(node.operand)
			return -v if isinstance(node.op, ast.USub) else v
		if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
			return float(node.value)
		if isinstance(node, ast.Name) and node.id in values:
			return values[node.id]
		raise ValueError(f'formula {formula}: only numbers, band names, + - * / ** and parentheses')

	return ev(ast.parse(formula.strip(), mode='eval'))


def normalized_difference(a, b):
	"""(A - B) / (A + B) as ee.Image.normalizedDifference: 0 where both are 0, NaN where one is negative."""
	out = _divide(np.subtract(a, b), np.add(a, b))
	return np.where((np.asarray(a) < 0) | (np.asarray(b) < 0), np.nan, out)


def percentile(a, p, axis=0):
	"""Percentile P (0-100) of A along AXIS without the NaN, as Earth Engine computes it: the value of rank
	n p / 100 + 0.5 (from 1 to n), interpolated (numpy's method 'hazen'); NaN where there is no value."""
	a = np.sort(np.asarray(a, np.float64), axis=axis)  # NaN at the end
	n = np.sum(~np.isnan(a), axis=axis)
	rank = np.clip(n * p / 100.0 + 0.5, 1, np.maximum(n, 1)) - 1
	lo = np.floor(rank).astype(np.int64)
	hi = np.minimum(lo + 1, np.maximum(n - 1, 0))
	vlo = np.take_along_axis(a, np.expand_dims(lo, axis), axis).squeeze(axis)
	vhi = np.take_along_axis(a, np.expand_dims(hi, axis), axis).squeeze(axis)
	return np.where(n > 0, vlo + (rank - lo) * (vhi - vlo), np.nan)


def _metric(metric):
	composite.check_metric(metric)
	m = str(metric).strip().lower()
	if m == 'mode':
		raise ValueError('the metric mode is only computed in Earth Engine')
	return m


class Reducer:
	"""Reduction of images (arrays, NaN = masked) pixel by pixel with a metric of composite.METRICS, added one at
	a time: the mean, sum, minimum, maximum, standard deviation and count without keeping them."""

	def __init__(self, metric, shape):
		self.metric, self.shape = _metric(metric), shape
		self.images, self.acc = [], None

	def add(self, a):
		if self.metric not in STREAM:
			self.images.append(a)
			return
		ok = ~np.isnan(a)
		v = np.where(ok, a, 0).astype(np.float64)
		if self.acc is None:
			self.acc = {'n': np.zeros(self.shape), 's': np.zeros(self.shape), 'ss': np.zeros(self.shape),
			            'min': np.full(self.shape, np.inf), 'max': np.full(self.shape, -np.inf)}
		acc = self.acc
		acc['n'] += ok
		acc['s'] += v
		acc['ss'] += v * v
		acc['min'] = np.where(ok, np.minimum(acc['min'], v), acc['min'])
		acc['max'] = np.where(ok, np.maximum(acc['max'], v), acc['max'])

	def result(self):
		"""Image of the reduction (float32, NaN where no image has a value)."""
		m = self.metric
		if m not in STREAM:
			if not self.images:
				return np.full(self.shape, np.nan, np.float32)
			stack = np.stack(self.images)
			return percentile(stack, 50 if m == 'median' else float(m[1:])).astype(np.float32)
		if self.acc is None:
			return np.full(self.shape, 0 if m == 'count' else np.nan, np.float32)
		n, s = self.acc['n'], self.acc['s']
		with np.errstate(invalid='ignore', divide='ignore'):
			mean = s / n
			out = {'mean': mean, 'sum': s, 'min': self.acc['min'], 'max': self.acc['max'], 'count': n,
			       'std': np.sqrt(np.maximum(self.acc['ss'] / n - mean * mean, 0))}[m]
		return np.where((n > 0) | (m == 'count'), out, np.nan).astype(np.float32)


def statistic(values, stat):
	"""STAT (a metric of composite.METRICS) of the VALUES (1-D array without NaN) of a region, None without values."""
	s = _metric(stat)
	if not values.size:
		return 0 if s == 'count' else None
	v = values.astype(np.float64)
	if s in ('median',) or s.startswith('p'):
		return float(percentile(v, 50 if s == 'median' else float(s[1:])))
	return float({'mean': np.mean, 'sum': np.sum, 'min': np.min, 'max': np.max, 'std': np.std,
	              'count': np.size}[s](v))


# Regions -----------------------------------------------------------------------------------------------------------

def regions(spec):
	"""[(name, OGR geometry in EPSG:4326)] of a region given as for areas.region: geojson, file, bbox or point (with
	buffer in metres). Protected areas and ecoregions are looked up in Earth Engine: give them as files here."""
	ogr = areas._ogr()
	if not isinstance(spec, dict):
		raise ValueError(f"give the region as a dictionary with one of: {', '.join(areas.REGION_KEYS)}")
	keys = [k for k in areas.REGION_KEYS if spec.get(k) is not None]
	if len(keys) != 1:
		raise ValueError(f"give one region: {', '.join(areas.REGION_KEYS)}")
	k, v = keys[0], spec[keys[0]]
	if k in ('wdpa_id', 'wdpa_name', 'ecoregion_id', 'ecoregion_at'):
		raise ValueError('protected areas and ecoregions are looked up in Earth Engine: to compute on this computer, '
		                 'give the region as a vector file or GeoJSON (e.g. downloaded from protectedplanet.net)')
	if k == 'bbox':
		w, s, e, n = (float(x) for x in v)
		ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
		return [('bbox', ogr.CreateGeometryFromJson(json.dumps({'type': 'Polygon', 'coordinates': [ring]})))]
	if k == 'point':
		geom = ogr.CreateGeometryFromJson(json.dumps({'type': 'Point', 'coordinates': [float(x) for x in v[:2]]}))
		if spec.get('buffer'):
			utm = areas.srs_of(areas.utm_of(float(v[0]), float(v[1])))
			geom = areas.transform(areas.transform(geom, areas.wgs84(), utm).Buffer(float(spec['buffer']), 64),
			                       utm, areas.wgs84())
		return [('point', geom)]
	if k == 'geojson':
		gj = json.loads(v) if isinstance(v, str) else v
		if gj.get('type') == 'FeatureCollection':
			feats = gj['features']
		elif gj.get('type') == 'Feature':
			feats = [gj]
		else:
			feats = [{'type': 'Feature', 'geometry': gj, 'properties': {}}]
		out = []
		for i, f in enumerate(feats, 1):
			props = f.get('properties') or {}
			name = props.get(spec['name_field']) if spec.get('name_field') else props.get('name', props.get('NAME'))
			out.append((str(name if name is not None else i), ogr.CreateGeometryFromJson(json.dumps(f['geometry']))))
		return out
	ds = ogr.Open(v)
	if ds is None:
		raise ValueError(f'cannot open {v}')
	lyr = ds.GetLayerByName(spec['layer']) if spec.get('layer') else ds.GetLayer(0)
	src = lyr.GetSpatialRef()
	if src is None:
		raise ValueError(f'{v} has no CRS')
	src = src.Clone()
	src.SetAxisMappingStrategy(areas._osr().OAMS_TRADITIONAL_GIS_ORDER)
	out = []
	for i, feat in enumerate(lyr, 1):
		g = feat.GetGeometryRef()
		if g is None:
			continue
		if spec.get('simplify'):
			g = g.SimplifyPreserveTopology(spec['simplify'])
		name = feat.GetField(spec['name_field']) if spec.get('name_field') else i
		out.append((str(name), areas.transform(g, src, areas.wgs84())))
	if not out:
		raise ValueError(f'{v} has no features')
	return out


def _union(regs):
	union = regs[0][1].Clone()
	for _, g in regs[1:]:
		union = union.Union(g)
	return union


def _projected(geom, crs):
	"""GEOM (EPSG:4326, with straight edges in degrees, as the geometries of Earth Engine that are not geodesic) in
	CRS."""
	g = geom.Clone()
	g.Segmentize(0.001)
	return areas.transform(g, areas.wgs84(), areas.srs_of(crs))


def _utm(geom):
	c = geom.Centroid()
	return areas.utm_of(c.GetX(), c.GetY())


def auto_scale(entry, regs):
	"""Pixel size (m) of the statistics, as timeseries.auto_scale."""
	area = max(_projected(g, _utm(g)).GetArea() for _, g in regs)
	return timeseries.nice_scale(float(entry['m']), area)


def grid_of(regs, res, crs='auto'):
	"""Grid of RES metres in CRS ('auto' = WGS 84 / UTM of the centre) that covers the regions REGS."""
	union = _union(regs)
	crs = _utm(union) if str(crs).lower() == 'auto' else crs
	xmin, xmax, ymin, ymax = _projected(union, crs).GetEnvelope()
	margin = res / 2 if xmax - xmin < res or ymax - ymin < res else 0  # a point, or a line: at least one pixel
	return Grid.around(crs, res, xmin, ymin, xmax, ymax, margin)


def masks(regs, grid):
	"""[(name, boolean array)]: the pixels of GRID with their centre inside each region (that of a point)."""
	from osgeo import gdal
	ogr = areas._ogr()
	srs = areas.srs_of(grid.crs)
	out = []
	for name, geom in regs:
		ds = gdal.GetDriverByName('MEM').Create('', grid.width, grid.height, 1, gdal.GDT_Byte)
		ds.SetGeoTransform(grid.geotransform)
		ds.SetProjection(srs.ExportToWkt())
		vec = (ogr.GetDriverByName('MEM') or ogr.GetDriverByName('Memory')).CreateDataSource('')
		lyr = vec.CreateLayer('region', srs)
		feat = ogr.Feature(lyr.GetLayerDefn())
		feat.SetGeometry(_projected(geom, grid.crs))
		lyr.CreateFeature(feat)
		gdal.RasterizeLayer(ds, [1], lyr, burn_values=[1])
		out.append((name, ds.GetRasterBand(1).ReadAsArray().astype(bool)))
	return out


# Images ------------------------------------------------------------------------------------------------------------

def check(spec):
	"""Catalog entry of SPEC, if it can be computed on this computer (else ValueError)."""
	if variables.kind(spec) != 'catalog':
		raise ValueError('on this computer only the variables of the catalog of MonitorEO are computed (collection '
		                 'and image are sources of Earth Engine)')
	entry = variables.entry_of(spec)
	if entry['sensor'] not in SENSORS:
		raise ValueError(f"{entry['index']} of {entry['sensor']}: on this computer only Sentinel-2 and Landsat are "
		                 "computed (MODIS in Earth Engine: where='gee')")
	if spec.get('exclude_landcover'):
		raise ValueError('exclude_landcover uses ESA WorldCover in Earth Engine: not available on this computer')
	return entry


def notes(entry, spec):
	"""How the computation of SPEC (variable ENTRY) on this computer differs from that of Earth Engine."""
	q = dict(sensors.QUALITY, **(spec.get('quality') or {}))
	out = []
	if entry['sensor'] == 'Sentinel-2':
		if sensors.filters(entry, q)['clouds'] and q.get('cloud_score') is not None:
			out.append('Sentinel-2 clouds: SCL classes (Cloud Score+ is only in Earth Engine)')
		if spec.get('period') and str(spec['period'][0]) < S2_SAME_FROM:
			out.append(f'Sentinel-2 before {S2_SAME_FROM}: Planetary Computer has other processings than Earth Engine '
			           '(Sen2Cor), the values differ by about 0.01 of NDVI')
	return out


def harmonized(raw, baseline=None):
	"""Raw values of a band (float64), without the offset of the Sentinel-2 processing BASELINE ('05.10'; None for
	Landsat) as in COPERNICUS/S2_SR_HARMONIZED: from 04.00, the values minus 1000, and 0 below it."""
	v = np.asarray(raw, np.float64)
	if baseline is not None and baseline >= S2_OFFSET[0]:
		v = np.maximum(v - S2_OFFSET[1], 0)
	return v


class Reader:
	"""Reads the images of a variable of the catalog (ENTRY) on GRID: the bands of its formula, with the scale and
	offset of the catalog, masked with the pixel filters of QUALITY."""

	def __init__(self, entry, quality, grid, resample='auto'):
		self.entry, self.grid = entry, grid
		self.s2 = entry['sensor'] == 'Sentinel-2'
		self.on = sensors.filters(entry, dict(sensors.QUALITY, **(quality or {})))
		self.scale = sensors.number(entry.get('scale'), 1.0)
		self.offset = sensors.number(entry.get('offset'), 0.0)
		names = list(S2_BANDS) if self.s2 else sensors.band_names(entry)
		self.kind, self.bands = sensors.parse_formula(entry, names)
		self.used = list(self.bands) if self.kind == 'nd' else sorted(set(self.bands.values()))
		if self.s2:
			self.qa = ['SCL'] if any(self.on[f] for f in sensors.S2_SCL) else []
		else:
			self.qa = ((['QA_PIXEL'] if any(self.on[f] for f in ('clouds', 'snow', 'water')) else [])
			           + (['SR_QA_AEROSOL'] if self.on['aerosols'] else []))
		self.methods = {b: self._method(b, resample, float(entry['m'])) for b in self.used + self.qa}

	def _method(self, band, resample, native):
		"""Resampling of BAND: nearest for the QA bands; for the data, that of the spec (bilinear when the pixels are
		smaller than those of the data, with 'auto'), or the mean of the pixels when they are at least twice bigger
		(the pyramids of Earth Engine)."""
		if band in QA_BANDS:
			return 'near'
		method = variables._resample({'resample': resample}, self.grid.res, native)
		if method:
			return method
		size = S2_BANDS[band][1] if self.s2 else 30
		return 'average' if self.grid.res >= 2 * size else 'near'

	def _asset(self, item, band):
		if self.s2:
			return item['assets'].get(S2_BANDS[band][0])
		names = LANDSAT_BANDS[band]
		names = names if isinstance(names, tuple) else (names,)
		return next((item['assets'][n] for n in names if n in item['assets']), None)

	def bands_read(self, item):
		"""[(band, pixel size in m)] that ITEM reads."""
		return [(b, S2_BANDS[b][1] if self.s2 else 30) for b in self.used + self.qa if self._asset(item, b)]

	def image(self, item):
		"""Values of the variable in the image ITEM (float32, NaN where masked or without data)."""
		shape = (self.grid.height, self.grid.width)
		raw, valid = {}, np.ones(shape, bool)
		for b in self.used + self.qa:
			asset = self._asset(item, b)
			if asset is None:  # Landsat 5 and 7 have no aerosol QA: nothing is removed, as in Earth Engine
				continue
			nodata = ((asset.get('raster:bands') or [{}])[0]).get('nodata', 0)
			raw[b] = _warp(asset['href'], item['collection'], self.grid, self.methods[b], nodata)
			valid &= raw[b] != nodata
		baseline = item['properties'].get('s2:processing_baseline') if self.s2 else None
		data = {b: harmonized(raw[b], baseline) * self.scale + self.offset for b in self.used}
		if self.kind == 'nd':
			out = normalized_difference(data[self.bands[0]], data[self.bands[1]])
		else:
			out = evaluate(self.entry['ft'], {name: data[b] for name, b in self.bands.items()})
		ok = valid & self._quality(raw) & np.isfinite(out)
		return np.where(ok, out, np.nan).astype(np.float32)

	def _quality(self, raw):
		"""Pixels that pass the pixel filters (see sensors.quality_mask) in the raw bands RAW ({band: array})."""
		ok = np.ones(next(iter(raw.values())).shape if raw else (self.grid.height, self.grid.width), bool)
		if self.s2:
			for f, classes in sensors.S2_SCL.items():
				if self.on[f]:
					ok &= ~np.isin(raw['SCL'], classes)
			return ok
		qa = raw.get('QA_PIXEL')
		if qa is not None:
			qa = qa.astype(np.int64)
			if self.on['clouds']:
				ok &= ((qa >> 1) & 15) == 0  # dilated cloud, cirrus, cloud, cloud shadow
			if self.on['snow']:
				ok &= ((qa >> 5) & 1) == 0
			if self.on['water']:
				ok &= ((qa >> 7) & 1) == 0
		aerosol = raw.get('SR_QA_AEROSOL')
		if self.on['aerosols'] and aerosol is not None:
			ok &= ((aerosol.astype(np.int64) >> 6) & 3) != 3  # aerosol level 3 = high
		return ok


def _reduce_groups(reader, groups, metric, finish, workers=WORKERS):
	"""Reduce the images of each group of items (GROUPS: [[item]]) with METRIC, reading WORKERS images at a time over
	all the groups, and call FINISH(i, image) when group i is complete (an image without values if it is empty)."""
	shape = (reader.grid.height, reader.grid.width)
	reducers = [Reducer(metric, shape) for _ in groups]
	left = [len(g) for g in groups]
	for i, n in enumerate(left):
		if not n:
			finish(i, reducers[i].result())
	with cf.ThreadPoolExecutor(max_workers=workers) as pool:
		futures = {pool.submit(reader.image, it): i for i, g in enumerate(groups) for it in g}
		try:
			for fut in cf.as_completed(list(futures)):
				i = futures.pop(fut)
				reducers[i].add(fut.result())
				left[i] -= 1
				if not left[i]:
					finish(i, reducers[i].result())
					reducers[i] = None
		except BaseException:
			for fut in futures:
				fut.cancel()
			raise


def _check_memory(metric, groups, grid):
	if _metric(metric) in STREAM:
		return
	need = max((len(g) for g in groups), default=0) * grid.pixels * 4
	if need > MAX_STACK:
		raise ValueError(f'the {metric} of {max(len(g) for g in groups)} images of {grid.pixels} pixels needs '
		                 f'{need / 1e9:.1f} GB of memory on this computer: use bigger pixels, shorter steps, a metric '
		                 "such as mean, min or max, or compute it in Earth Engine (where='gee')")


def _in_windows(its, wins):
	return [it for it in its if any(ws.isoformat() <= _day(it) < we.isoformat() for _, ws, we in wins)]


def _items(entry, spec, regs):
	wins = composite.windows(spec['period'], spec['season'])
	found = items(entry, _union(regs), wins[0][1].isoformat(), wins[-1][2].isoformat(), spec['quality'])
	return _in_windows(found, wins), wins


def _steps(spec, step, its):
	"""[(first day, day after the last)] of the steps: as timeseries.bins, the days with images for 'daily'."""
	if step != 'daily':
		return timeseries.bins(spec, step)
	days = sorted({_day(it) for it in its})
	return [(d, (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()) for d in days]


def _groups(its, steps):
	return [[it for it in its if a <= _day(it) < b] for a, b in steps]


def series(spec, region, step='monthly', metric='mean', stat='mean', scale=None, progress=None, workers=WORKERS):
	"""Rows [{region, date, value, n_pixels, n_images}] of the time series of SPEC over REGION (see
	timeseries.series), sorted by region and date, and the scale used, computed on this computer."""
	entry = check(spec)
	_metric(stat)
	regs = regions(region)
	scale = float(scale or auto_scale(entry, regs))
	grid = grid_of(regs, scale)
	its, _ = _items(entry, spec, regs)
	steps = _steps(spec, step, its)
	groups = _groups(its, steps)
	_check_memory(metric, groups, grid)
	reader = Reader(entry, spec['quality'], grid, spec.get('resample') or 'auto')
	region_masks = masks(regs, grid)
	rows, done = [], [0]

	def finish(i, img):
		for name, m in region_masks:
			v = img[m]
			v = v[~np.isnan(v)]
			rows.append({'region': name, 'date': steps[i][0], 'value': statistic(v, stat), 'n_pixels': int(v.size),
			             'n_images': len(groups[i])})
		done[0] += 1
		if progress:
			progress(done[0], len(steps))

	_reduce_groups(reader, groups, metric, finish, workers)
	rows.sort(key=lambda r: (r['region'], r['date']))
	return rows, scale


def composite_image(spec, regs, grid, progress=None, workers=WORKERS):
	"""Image of SPEC aggregated in time as composite.composite (metric, temporal, interannual) on GRID (float32 array,
	NaN without value) and the number of images, computed on this computer."""
	entry = check(spec)
	its, wins = _items(entry, spec, regs)
	temporal = spec['temporal']
	if temporal not in composite.TEMPORAL:
		raise ValueError(f"unknown temporal aggregation {temporal}: use {', '.join(composite.TEMPORAL)}")
	if temporal == 'period':
		parts = [None]
		groups = [its]
	elif temporal == 'annual':
		parts = [None for _ in wins]
		groups = _groups(its, [(ws.isoformat(), we.isoformat()) for _, ws, we in wins])
	else:
		bins = [b for w in wins for b in composite.bins(w, temporal)]
		parts = [month for month, _, _ in bins]
		groups = _groups(its, [(bs.isoformat(), be.isoformat()) for _, bs, be in bins])
	_check_memory(spec['metric'], groups, grid)
	reader = Reader(entry, spec['quality'], grid, spec.get('resample') or 'auto')
	images, done = [None] * len(groups), [0]

	def finish(i, img):
		images[i] = img
		done[0] += 1
		if progress:
			progress(done[0], len(groups))

	_reduce_groups(reader, groups, spec['metric'], finish, workers)
	shape = (grid.height, grid.width)
	if temporal == 'period':
		return images[0], len(its)

	def reduce(imgs, metric):
		r = Reducer(metric, shape)
		for img in imgs:
			r.add(img)
		return r.result()

	if temporal == 'annual':
		return reduce(images, spec['interannual']), len(its)
	by_month = {}
	for month, img in zip(parts, images):
		by_month.setdefault(month, []).append(img)
	months = [reduce(imgs, spec['interannual']) for _, imgs in sorted(by_month.items())]
	return reduce(months, 'mean'), len(its)


def download_image(spec, region, resolution=None, crs='auto', path=None, clip=True, max_pixels=None, progress=None,
                   workers=WORKERS):
	"""Write the map of SPEC over REGION (see services.download_image) to the GeoTIFF PATH (float32, NoData -9999),
	computed on this computer. Returns {'file', 'grid', 'resolution', 'native_resolution', 'images'}."""
	entry = check(spec)
	regs = regions(region)
	native = float(entry['m'])
	res = float(resolution or native)
	grid = grid_of(regs, res, crs)
	if max_pixels and grid.pixels > max_pixels:
		res *= math.ceil(math.sqrt(grid.pixels / max_pixels))
		grid = grid_of(regs, res, grid.crs)
	img, n = composite_image(spec, regs, grid, progress, workers)
	if clip:
		inside = np.zeros(img.shape, bool)
		for _, m in masks(regs, grid):
			inside |= m
		img = np.where(inside, img, np.nan)
	desc = dict(variables.describe(spec), computed_on=WHERE['computed_on'], data=WHERE['data'],
	            notes=notes(entry, spec))
	write_geotiff(img, grid, path, {'source': f"{WHERE['data']}, computed on {WHERE['computed_on']}",
	                                'monitoreo': json.dumps(desc, default=str)})
	return {'file': path, 'grid': grid.describe(), 'resolution': res, 'native_resolution': native, 'images': n}


def write_geotiff(img, grid, path, metadata=None):
	"""Write IMG (NaN = NoData) on GRID to the float32 GeoTIFF PATH, NoData -9999."""
	from osgeo import gdal
	gdal.UseExceptions()
	part = path + '.part.tif'
	ds = gdal.GetDriverByName('GTiff').Create(part, grid.width, grid.height, 1, gdal.GDT_Float32,
	                                          ['COMPRESS=DEFLATE', 'PREDICTOR=3', 'TILED=YES', 'BIGTIFF=IF_SAFER'])
	ds.SetGeoTransform(grid.geotransform)
	ds.SetProjection(areas.srs_of(grid.crs).ExportToWkt())
	band = ds.GetRasterBand(1)
	band.SetNoDataValue(NODATA)
	band.WriteArray(np.where(np.isnan(img), NODATA, img).astype(np.float32))
	if metadata:
		ds.SetMetadata({k: str(v) for k, v in metadata.items()})
	try:
		band.ComputeStatistics(False)
	except RuntimeError:  # no valid pixels
		pass
	ds.FlushCache()
	ds = None
	os.replace(part, path)
	return path


# Before computing --------------------------------------------------------------------------------------------------

def plan(spec, region, step=None, scale=None, resolution=None, crs='auto'):
	"""What computing SPEC over REGION on this computer reads, to tell the user before starting (it searches the
	images, without reading them): WHERE and {'images', 'grid', 'read_mb' (megabytes of the pixels read, roughly),
	'notes'}, with 'steps' and 'scale' for the time series of STEP, or 'resolution' for the map (without STEP)."""
	entry = check(spec)
	regs = regions(region)
	its, _ = _items(entry, spec, regs)
	out = dict(WHERE, images=len(its), notes=notes(entry, spec))
	if step is None:
		res = float(resolution or entry['m'])
		grid = grid_of(regs, res, crs)
		out['resolution'] = res
	else:
		res = float(scale or auto_scale(entry, regs))
		grid = grid_of(regs, res)
		out.update(scale=res, steps=len(_steps(spec, step, its)))
	reader = Reader(entry, spec['quality'], grid, spec.get('resample') or 'auto')
	area = grid.pixels * grid.res ** 2
	nbytes = sum(area / max(size, res) ** 2 * (1 if b == 'SCL' else 2) for it in its for b, size in reader.bands_read(it))
	out.update(grid=grid.describe(), read_mb=round(nbytes / 1e6, 1))
	return out

