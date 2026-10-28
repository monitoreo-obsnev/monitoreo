"""Regions of interest: GeoJSON, vector files, protected areas (WDPA), ecoregions (RESOLVE Ecoregions 2017), boxes
and points, as Earth Engine feature collections with a 'name' property per feature.

GDAL (osgeo) is only needed to read vector files and to reproject local geometries; it is imported when used, so
the rest works without it.
"""

import json
import math

import ee

ECOREGIONS = 'RESOLVE/ECOREGIONS/2017'
ECO_FIELDS = ['ECO_ID', 'ECO_NAME', 'BIOME_NAME', 'REALM']
WDPA = 'WCMC/WDPA/current/polygons'
# Fields of WDPA since 2025: the WDPA ID is SITE_ID (WDPAID before) and NAME_ENG the English name (ORIG_NAME before)
WDPA_FIELDS = ['SITE_ID', 'NAME', 'NAME_ENG', 'DESIG', 'DESIG_ENG', 'IUCN_CAT', 'ISO3', 'REP_AREA', 'STATUS_YR']
REGION_KEYS = ('geojson', 'file', 'wdpa_id', 'wdpa_name', 'ecoregion_id', 'ecoregion_at', 'bbox', 'point')


def _osr():
	from osgeo import osr
	osr.UseExceptions()
	return osr


def _ogr():
	from osgeo import ogr
	ogr.UseExceptions()
	return ogr


def wgs84():
	osr = _osr()
	srs = osr.SpatialReference()
	srs.ImportFromEPSG(4326)
	srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
	return srs


def srs_of(crs):
	"""OSR spatial reference of a CRS given as 'EPSG:code' (or any other text that OSR understands, e.g. WKT)."""
	osr = _osr()
	srs = osr.SpatialReference()
	srs.SetFromUserInput(crs)
	srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
	return srs


def read_vector(path, layer=None):
	"""Union of the polygons of a vector file (OGR geometry, in the CRS of the file) and that CRS."""
	ogr, osr = _ogr(), _osr()
	ds = ogr.Open(path)
	lyr = ds.GetLayerByName(layer) if layer else ds.GetLayer(0)
	srs = lyr.GetSpatialRef()
	if srs is None:
		raise ValueError(f'{path} has no CRS')
	srs = srs.Clone()
	srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
	union = ogr.Geometry(ogr.wkbMultiPolygon)
	for feat in lyr:
		g = feat.GetGeometryRef()
		if g is not None:
			union = union.Union(g)
	if union.IsEmpty():
		raise ValueError(f'{path} has no polygons')
	return union, srs


def transform(geom, src, dst):
	g = geom.Clone()
	g.Transform(_osr().CoordinateTransformation(src, dst))
	return g


def utm_crs(geom, srs):
	"""'EPSG:326zz' or 'EPSG:327zz': WGS 84 / UTM zone of the centre of GEOM."""
	c = transform(geom, srs, wgs84()).Centroid()
	return utm_of(c.GetX(), c.GetY())


def utm_of(lon, lat):
	"""'EPSG:326zz' or 'EPSG:327zz': WGS 84 / UTM zone of a point."""
	zone = min(int(math.floor((lon + 180) / 6)) + 1, 60)
	return f'EPSG:{(32600 if lat >= 0 else 32700) + zone}'


def bounds(geom, srs, crs):
	"""(xmin, ymin, xmax, ymax) of GEOM in CRS."""
	xmin, xmax, ymin, ymax = transform(geom, srs, srs_of(crs)).GetEnvelope()
	return xmin, ymin, xmax, ymax


def to_ee(geom, srs, simplify=None):
	"""Earth Engine geometry (EPSG:4326) of an OGR geometry, simplified by SIMPLIFY (in the units of SRS)."""
	if simplify:
		geom = geom.SimplifyPreserveTopology(simplify)
	g = transform(geom, srs, wgs84())
	return ee.Geometry(json.loads(g.ExportToJson()), opt_geodesic=False)


# Regions -----------------------------------------------------------------------------------------------------------

def _features_from_geojson(gj, name_field=None):
	if isinstance(gj, str):
		gj = json.loads(gj)
	if gj.get('type') == 'FeatureCollection':
		feats = gj['features']
	elif gj.get('type') == 'Feature':
		feats = [gj]
	else:
		feats = [{'type': 'Feature', 'geometry': gj, 'properties': {}}]
	out = []
	for i, f in enumerate(feats, 1):
		props = f.get('properties') or {}
		name = props.get(name_field) if name_field else props.get('name', props.get('NAME'))
		geom = ee.Geometry(f['geometry'], opt_geodesic=False)
		out.append(ee.Feature(geom, {'name': str(name if name is not None else i)}))
	return out


def _features_from_file(path, layer=None, name_field=None, simplify=None):
	ogr = _ogr()
	ds = ogr.Open(path)
	if ds is None:
		raise ValueError(f'cannot open {path}')
	lyr = ds.GetLayerByName(layer) if layer else ds.GetLayer(0)
	src = lyr.GetSpatialRef()
	if src is None:
		raise ValueError(f'{path} has no CRS')
	src = src.Clone()
	src.SetAxisMappingStrategy(_osr().OAMS_TRADITIONAL_GIS_ORDER)
	out = []
	for i, feat in enumerate(lyr, 1):
		g = feat.GetGeometryRef()
		if g is None:
			continue
		if simplify:
			g = g.SimplifyPreserveTopology(simplify)
		g = transform(g, src, wgs84())
		name = feat.GetField(name_field) if name_field else i
		out.append(ee.Feature(ee.Geometry(json.loads(g.ExportToJson()), opt_geodesic=False), {'name': str(name)}))
	if not out:
		raise ValueError(f'{path} has no features')
	return out


def _named(fc, field):
	return fc.map(lambda f: f.set('name', ee.String(f.get(field))))


def region(spec):
	"""ee.FeatureCollection of a region given as a dictionary with one of:
	  geojson        a GeoJSON geometry, Feature or FeatureCollection (dict or text); name_field: property with names
	  file           a vector file (GDAL needed); layer, name_field and simplify (in the units of the file) optional
	  wdpa_id        WDPA ID (SITE_ID) of a protected area, or a list of them
	  wdpa_name      exact name of a protected area in WDPA (see find_protected_areas)
	  ecoregion_id   ECO_ID of RESOLVE Ecoregions 2017, or a list of them
	  ecoregion_at   [lon, lat]: the ecoregion at that point
	  bbox           [west, south, east, north] in degrees
	  point          [lon, lat], with buffer (metres, default 0)
	Each feature has a 'name' property (used to label the rows of the time series). An ee.FeatureCollection is
	returned as it is."""
	if isinstance(spec, ee.FeatureCollection):
		return spec
	if not isinstance(spec, dict):
		raise ValueError(f"give the region as a dictionary with one of: {', '.join(REGION_KEYS)}")
	keys = [k for k in REGION_KEYS if spec.get(k) is not None]
	if len(keys) != 1:
		raise ValueError(f"give one region: {', '.join(REGION_KEYS)}")
	k = keys[0]
	v = spec[k]
	if k == 'geojson':
		return ee.FeatureCollection(_features_from_geojson(v, spec.get('name_field')))
	if k == 'file':
		return ee.FeatureCollection(_features_from_file(v, spec.get('layer'), spec.get('name_field'), spec.get('simplify')))
	if k == 'wdpa_id':
		ids = [int(x) for x in (v if isinstance(v, (list, tuple)) else [v])]
		f = ee.Filter.Or(ee.Filter.inList('SITE_ID', ids), ee.Filter.inList('WDPAID', ids))
		return _named(ee.FeatureCollection(WDPA).filter(f), 'NAME')
	if k == 'wdpa_name':
		return _named(ee.FeatureCollection(WDPA).filter(ee.Filter.eq('NAME', v)), 'NAME')
	if k == 'ecoregion_id':
		ids = [int(x) for x in (v if isinstance(v, (list, tuple)) else [v])]
		return _named(ee.FeatureCollection(ECOREGIONS).filter(ee.Filter.inList('ECO_ID', ids)), 'ECO_NAME')
	if k == 'ecoregion_at':
		return _named(ee.FeatureCollection(ECOREGIONS).filterBounds(ee.Geometry.Point(list(v))), 'ECO_NAME')
	if k == 'bbox':
		return ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle(list(v), None, False), {'name': 'bbox'})])
	geom = ee.Geometry.Point(list(v))
	if spec.get('buffer'):
		geom = geom.buffer(float(spec['buffer']))
	return ee.FeatureCollection([ee.Feature(geom, {'name': 'point'})])


def find_protected_areas(text, limit=20):
	"""Protected areas of WDPA whose name (or English name) contains TEXT: [{SITE_ID (the WDPA ID), NAME, ...}]."""
	t = str(text).strip()
	variants = sorted({t, t.title(), t.upper(), t.lower(), t.capitalize()})
	f = ee.Filter.Or(*([ee.Filter.stringContains('NAME', s) for s in variants]
	                   + [ee.Filter.stringContains('NAME_ENG', s) for s in variants]))
	fc = ee.FeatureCollection(WDPA).filter(f).limit(int(limit))
	return [x['properties'] for x in fc.map(lambda x: ee.Feature(None, x.toDictionary(WDPA_FIELDS))).getInfo()['features']]


# Ecoregions --------------------------------------------------------------------------------------------------------

def ecoregions(geom):
	"""Ecoregions that intersect GEOM (ee.Geometry), as an ee.FeatureCollection."""
	return ee.FeatureCollection(ECOREGIONS).filterBounds(geom)


def ecoregion_info(eco):
	"""[{ECO_ID, ECO_NAME, BIOME_NAME, REALM}] of the ecoregions of the collection ECO."""
	return eco.select(ECO_FIELDS).map(lambda f: ee.Feature(None, f.toDictionary())).getInfo()['features']


def ecoregion_bounds(eco, crs, max_error):
	"""(xmin, ymin, xmax, ymax) of the union of the ecoregions ECO in CRS."""
	ring = eco.geometry(max_error).bounds(max_error, crs).getInfo()['coordinates'][0]
	xs, ys = [p[0] for p in ring], [p[1] for p in ring]
	return min(xs), min(ys), max(xs), max(ys)


def save_ecoregions(eco, path, max_error):
	"""Write the ecoregions ECO, simplified by MAX_ERROR metres, to a GeoPackage (EPSG:4326)."""
	ogr = _ogr()
	fc = eco.select(ECO_FIELDS).map(lambda f: f.simplify(max_error)).getInfo()
	drv = ogr.GetDriverByName('GPKG')
	ds = drv.CreateDataSource(path)
	lyr = ds.CreateLayer('ecoregions', wgs84(), ogr.wkbMultiPolygon)
	lyr.CreateField(ogr.FieldDefn('ECO_ID', ogr.OFTInteger))
	for name in ECO_FIELDS[1:]:
		lyr.CreateField(ogr.FieldDefn(name, ogr.OFTString))
	for f in fc['features']:
		feat = ogr.Feature(lyr.GetLayerDefn())
		for name in ECO_FIELDS:
			feat.SetField(name, f['properties'].get(name))
		g = ogr.CreateGeometryFromJson(json.dumps(f['geometry']))
		feat.SetGeometry(ogr.ForceToMultiPolygon(g))
		lyr.CreateFeature(feat)
	ds = None
