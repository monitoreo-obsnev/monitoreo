"""Regions of interest: GeoJSON, vector files, protected areas (WDPA, also its Ramsar sites), ecoregions (RESOLVE
Ecoregions 2017), administrative units (countries, their first and second levels: FAO GAUL 2025), islands (Global
Islands, Sayre et al. 2019), boxes and points, as Earth Engine feature collections with a 'name' property per
feature.

GDAL (osgeo) is only needed to read vector files and to reproject local geometries; it is imported when used, so
the rest works without it.

References (monitoreo.references gives them, with those of the data, with each result):
    UNEP-WCMC & IUCN (year). Protected Planet: The World Database on Protected Areas (WDPA) [On-line], month and
      year of the version used. Cambridge, UK: UNEP-WCMC and IUCN. https://www.protectedplanet.net
    Dinerstein, E., Olson, D., Joshi, A., Vynne, C., Burgess, N. D., Wikramanayake, E., Hahn, N., Palminteri, S.,
      Hedao, P., Noss, R., Hansen, M., Locke, H., Ellis, E. C., Jones, B., Barber, C. V., Hayes, R., Kormos, C.,
      Martin, V., Crist, E., et al. (2017). An ecoregion-based approach to protecting half the terrestrial realm.
      BioScience, 67(6), 534–545. https://doi.org/10.1093/biosci/bix014
    FAO (2025). Global Administrative Unit Layers (GAUL) [Data set]. Food and Agriculture Organization of the United
      Nations. Licence: CC BY 4.0. https://data.apps.fao.org
    Sayre, R., Noble, S., Hamann, S., Smith, R., Wright, D., Breyer, S., Butler, K., Van Graafeiland, K., Frye, C.,
      Karagulle, D., Hopkins, D., Stephens, D., Kelly, K., Basher, Z., Burton, D., Cress, J., Atkins, K., Van Sistine,
      D. P., Friesen, B., et al. (2019). A new 30 meter resolution global shoreline vector and associated global
      islands database for the development of standardized ecological coastal units. Journal of Operational
      Oceanography, 12(sup2), S47–S56. https://doi.org/10.1080/1755876X.2018.1529714
"""

import json
import math

import ee

ECOREGIONS = 'RESOLVE/ECOREGIONS/2017'
ECO_FIELDS = ['ECO_ID', 'ECO_NAME', 'BIOME_NAME', 'REALM']
WDPA = 'WCMC/WDPA/current/polygons'
# Fields of WDPA since 2025: the WDPA ID is SITE_ID (WDPAID before) and NAME_ENG the English name (ORIG_NAME before)
WDPA_FIELDS = ['SITE_ID', 'NAME', 'NAME_ENG', 'DESIG', 'DESIG_ENG', 'DESIG_TYPE', 'IUCN_CAT', 'ISO3', 'REP_AREA',
               'STATUS_YR']
RAMSAR = 'Ramsar Site'  # in DESIG_ENG of WDPA: «Wetland of International Importance (Ramsar Site)»
# FAO GAUL 2025: the first (states, regions, provinces...) and second (districts, provinces, municipalities...) levels
# of every country; it has no level 0, so a country is the union of its first level (simplified to 500 m: its border
# is not needed at 30 m to compute over a whole country)
GAUL = {1: 'FAO/GAUL/2025/level1', 2: 'FAO/GAUL/2025/level2'}
GAUL_COUNTRIES = 'FAO/GAUL_SIMPLIFIED_500m/2025/level1'
GAUL_FIELDS = {1: ['GAUL0_NAME', 'GAUL1_CODE', 'GAUL1_NAME', 'ISO3_CODE', 'DISP_EN'],
               2: ['GAUL0_NAME', 'GAUL1_NAME', 'GAUL2_CODE', 'GAUL2_NAME', 'ISO3_CODE', 'DISP_EN']}
ISLANDS = 'projects/sat-io/open-datasets/shoreline/big_islands'  # Global Islands of more than 1 km² (Sayre et al.)
REGION_KEYS = ('geojson', 'file', 'wdpa_id', 'wdpa_name', 'ecoregion_id', 'ecoregion_at', 'country', 'admin1',
               'admin2', 'island_at', 'bbox', 'point')
WDPA_MAX_ERROR = 10  # metres: simplification of the protected areas fetched from WDPA (one pixel of Sentinel-2)

_wdpa = {}  # protected areas already fetched: {region as JSON: [GeoJSON features]}


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


NAME_FIELDS = ('name', 'nombre', 'nom', 'denominacion', 'denominación', 'label', 'etiqueta', 'id')


def describe_file(path, layer=None):
	"""What a vector file has, to use it as a region: {'features' (with polygons), 'area_ha' (of their union),
	'bounds' ([w, s, e, n] in EPSG:4326), 'crs', 'fields', 'name_field' (a field with a different value in each
	feature that can name them, or None), 'layers' (of the file)}."""
	ogr = _ogr()
	ds = ogr.Open(path)
	if ds is None:
		raise ValueError(f'cannot open {path}')
	layers = [ds.GetLayer(i).GetName() for i in range(ds.GetLayerCount())]
	lyr = ds.GetLayerByName(layer) if layer else ds.GetLayer(0)
	defn = lyr.GetLayerDefn()
	fields = [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())]
	values, count = {f: [] for f in fields}, 0
	for feat in lyr:
		g = feat.GetGeometryRef()
		if g is None or ogr.GT_Flatten(g.GetGeometryType()) not in (ogr.wkbPolygon, ogr.wkbMultiPolygon):
			continue
		count += 1
		for f in fields:
			values[f].append(feat.GetField(f))
	if not count:
		raise ValueError(f'{path} has no polygons')
	union, srs = read_vector(path, layer)
	area = transform(union, srs, srs_of(utm_crs(union, srs))).GetArea() / 1e4
	w, s, e, n = bounds(union, srs, 'EPSG:4326')
	unique = [f for f in fields if all(v not in (None, '') for v in values[f]) and len(set(values[f])) == count]
	named = [f for f in unique if f.lower() in NAME_FIELDS]
	text = [f for f in unique if all(isinstance(v, str) for v in values[f])]
	code = srs.GetAuthorityCode(None)
	return {'features': count, 'area_ha': area, 'bounds': [w, s, e, n],
	        'crs': f'{srs.GetAuthorityName(None)}:{code}' if code else srs.GetName(), 'fields': fields,
	        'name_field': (named or text or [None])[0], 'layers': layers}


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


def _geojson_polygons(geom):
	"""The polygons of a GeoJSON geometry (WDPA has geometry collections with lines), or None."""
	t = geom.get('type')
	if t in ('Polygon', 'MultiPolygon'):
		return geom
	if t != 'GeometryCollection':
		return None
	coords = []
	for g in geom.get('geometries', []):
		if g.get('type') == 'Polygon':
			coords.append(g['coordinates'])
		elif g.get('type') == 'MultiPolygon':
			coords += g['coordinates']
	if not coords:
		return None
	return dict({k: v for k, v in geom.items() if k not in ('type', 'geometries')}, type='MultiPolygon', coordinates=coords)


def _fetched(key, fc):
	"""The protected areas FC of WDPA as a collection of their geometries, fetched once (simplified by
	WDPA_MAX_ERROR m, without lines) and kept in memory: every later request carries the geometries instead of
	searching them again among the 300 000 areas of WDPA (3 months of MODIS over Sierra Nevada: 126 s, 8 s so)."""
	if key not in _wdpa:
		info = fc.map(lambda f: ee.Feature(f.geometry(), {'name': f.get('name')}).simplify(WDPA_MAX_ERROR)).getInfo()
		feats = []
		for f in info['features']:
			geom = _geojson_polygons(f['geometry'])
			if geom:
				feats.append({'geometry': geom, 'name': f['properties']['name']})
		if not feats:
			raise ValueError(f'no protected area of WDPA for {key}: see find_protected_areas')
		_wdpa[key] = feats
	return ee.FeatureCollection([ee.Feature(ee.Geometry(f['geometry']), {'name': f['name']}) for f in _wdpa[key]])


def region(spec):
	"""ee.FeatureCollection of a region given as a dictionary with one of:
	  geojson        a GeoJSON geometry, Feature or FeatureCollection (dict or text); name_field: property with names
	  file           a vector file (GDAL needed); layer, name_field and simplify (in the units of the file) optional
	  wdpa_id        WDPA ID (SITE_ID) of a protected area, or a list of them
	  wdpa_name      exact name of a protected area in WDPA (see find_protected_areas)
	  ecoregion_id   ECO_ID of RESOLVE Ecoregions 2017, or a list of them
	  ecoregion_at   [lon, lat]: the ecoregion at that point
	  country        ISO3 code of a country (e.g. 'ESP'), or a list of them (FAO GAUL 2025)
	  admin1         GAUL1_CODE of a first-level administrative unit (region, state, province...), or a list of them
	  admin2         GAUL2_CODE of a second-level administrative unit (province, district, municipality...), or a list
	                 (see find_admin_units for the codes)
	  island_at      [lon, lat]: the island (of more than 1 km²) at that point
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
		return _fetched(json.dumps({k: ids}), _named(ee.FeatureCollection(WDPA).filter(f), 'NAME'))
	if k == 'wdpa_name':
		return _fetched(json.dumps({k: v}), _named(ee.FeatureCollection(WDPA).filter(ee.Filter.eq('NAME', v)), 'NAME'))
	if k == 'ecoregion_id':
		ids = [int(x) for x in (v if isinstance(v, (list, tuple)) else [v])]
		return _named(ee.FeatureCollection(ECOREGIONS).filter(ee.Filter.inList('ECO_ID', ids)), 'ECO_NAME')
	if k == 'ecoregion_at':
		return _named(ee.FeatureCollection(ECOREGIONS).filterBounds(ee.Geometry.Point(list(v))), 'ECO_NAME')
	if k == 'country':
		codes = [str(x).strip().upper() for x in (v if isinstance(v, (list, tuple)) else [v])]
		return ee.FeatureCollection([_country(c) for c in codes])
	if k in ('admin1', 'admin2'):
		level = int(k[-1])
		ids = [int(x) for x in (v if isinstance(v, (list, tuple)) else [v])]
		fc = ee.FeatureCollection(GAUL[level]).filter(ee.Filter.inList(f'GAUL{level}_CODE', ids))
		return _named(fc, 'DISP_EN')  # e.g. «Granada, Andalucía, Spain»: the names of the units repeat in other countries
	if k == 'island_at':
		lon, lat = list(v)
		label = f'Island at {lat:.5f}, {lon:.5f}'
		fc = ee.FeatureCollection(ISLANDS).filterBounds(ee.Geometry.Point([lon, lat]))
		return fc.map(lambda f: f.set('name', ee.Algorithms.If(ee.String(f.get('Name')).length().gt(0),
		                                                       f.get('Name'), label)))
	if k == 'bbox':
		return ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle(list(v), None, False), {'name': 'bbox'})])
	geom = ee.Geometry.Point(list(v))
	if spec.get('buffer'):
		geom = geom.buffer(float(spec['buffer']))
	return ee.FeatureCollection([ee.Feature(geom, {'name': 'point'})])


def _country(code):
	"""The country of ISO3 CODE as a single feature: the union of its first-level units of GAUL 2025."""
	units = ee.FeatureCollection(GAUL_COUNTRIES).filter(ee.Filter.eq('ISO3_CODE', code))
	return ee.Feature(units.geometry(100).dissolve(100), {'name': ee.Feature(units.first()).get('GAUL0_NAME')})


def _variants(text):
	t = str(text).strip()
	return sorted({t, t.title(), t.upper(), t.lower(), t.capitalize()})


def find_protected_areas(text, limit=20, designation=None):
	"""Protected areas of WDPA whose name (or English name) contains TEXT: [{SITE_ID (the WDPA ID), NAME, ...}];
	with DESIGNATION 'ramsar', only the Ramsar sites (Wetlands of International Importance)."""
	variants = _variants(text)
	f = ee.Filter.Or(*([ee.Filter.stringContains('NAME', s) for s in variants]
	                   + [ee.Filter.stringContains('NAME_ENG', s) for s in variants]))
	if designation:
		if str(designation).strip().lower() != 'ramsar':
			raise ValueError(f'unknown designation {designation}: use "ramsar" (or none)')
		f = ee.Filter.And(f, ee.Filter.stringContains('DESIG_ENG', RAMSAR))
	fc = ee.FeatureCollection(WDPA).filter(f).limit(int(limit))
	return [x['properties'] for x in fc.map(lambda x: ee.Feature(None, x.toDictionary(WDPA_FIELDS))).getInfo()['features']]


def find_admin_units(text, level=1, country=None, limit=20):
	"""Administrative units of FAO GAUL 2025 of LEVEL (1: regions, states, provinces...; 2: provinces, districts,
	municipalities...) whose name contains TEXT, in COUNTRY (ISO3 code) if given: [{GAUL1_CODE or GAUL2_CODE, its name,
	the names of the country and of the first level, ISO3_CODE, DISP_EN (the full name), level}]."""
	level = int(level)
	if level not in GAUL:
		raise ValueError('level is 1 (regions, states, provinces...) or 2 (provinces, districts, municipalities...)')
	f = ee.Filter.Or(*[ee.Filter.stringContains(f'GAUL{level}_NAME', s) for s in _variants(text)])
	if country:
		f = ee.Filter.And(f, ee.Filter.eq('ISO3_CODE', str(country).strip().upper()))
	fc = ee.FeatureCollection(GAUL[level]).filter(f).limit(int(limit))
	rows = fc.map(lambda x: ee.Feature(None, x.toDictionary(GAUL_FIELDS[level]))).getInfo()['features']
	return [dict(x['properties'], level=level) for x in rows]


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
		feat.SetGeometry(_polygons(g, ogr))
		lyr.CreateFeature(feat)
	ds = None


def _polygons(g, ogr):
	"""MultiPolygon of the polygons of G (a simplified geometry can be a collection with lines or points too)."""
	if ogr.GT_Flatten(g.GetGeometryType()) != ogr.wkbGeometryCollection:
		return ogr.ForceToMultiPolygon(g)
	out = ogr.Geometry(ogr.wkbMultiPolygon)
	for i in range(g.GetGeometryCount()):
		part = g.GetGeometryRef(i)
		if ogr.GT_Flatten(part.GetGeometryType()) in (ogr.wkbPolygon, ogr.wkbMultiPolygon):
			part = ogr.ForceToMultiPolygon(part)
			for j in range(part.GetGeometryCount()):
				out.AddGeometry(part.GetGeometryRef(j))
	return out
