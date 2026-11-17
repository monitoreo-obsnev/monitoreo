"""Regions of interest: GeoJSON, vector files, protected areas (WDPA, also its Ramsar sites), ecoregions and biomes
(RESOLVE Ecoregions 2017), administrative units (countries, their first and second levels: FAO GAUL 2025), islands
(Global Islands, Sayre et al. 2019), boxes and points, as Earth Engine feature collections with a 'name' property per
feature. Any region takes "within", another region: only the part of each feature inside it is kept, e.g. the
Mediterranean biome in Spain, {'biome_id': 12, 'within': {'country': 'ESP'}}.

The CRS of the statistics and grids is chosen for each region (auto_crs): the UTM zone of its centre or, for the regions
too wide for one (whole biomes, which span continents), an equal-area CRS of the whole world in metres (GLOBAL_CRS).

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
import os

import ee

from . import catalog

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
REGION_KEYS = ('geojson', 'file', 'wdpa_id', 'wdpa_name', 'ecoregion_id', 'ecoregion_at', 'biome_id', 'biome_at',
               'country', 'admin1', 'admin2', 'admin3', 'island_at', 'bbox', 'point')
WDPA_MAX_ERROR = 10  # metres: simplification of the protected areas fetched from WDPA (one pixel of Sentinel-2)
# A biome is the union of its ecoregions (those of the table of classes of BIOME, catalog.ecoregions_of_biome, so that
# Rock and Ice, 99, is one too), dissolved with a tolerance of BIOME_MAX_ERROR metres, as a country
BIOME_MAX_ERROR = 100
BIOME_CODES = '1 to 14 or 99 (Rock and Ice)'  # the codes of the biomes (catalog.biomes), in the messages
WITHIN_MAX_ERROR = 100  # metres: tolerance of the union of the region of within and of the part of a feature inside it
# The automatic CRS: the UTM zone of the centre of the region, unless its bounds span more than WIDE_DEGREES of
# longitude (or cross the antimeridian: then they span 360), where a UTM zone distorts it; then GLOBAL_CRS, WGS 84 /
# NSIDC EASE-Grid 2.0 Global (equal area, in metres). Spain with the Canary Islands spans some 22 degrees: UTM.
GLOBAL_CRS = 'EPSG:6933'
WIDE_DEGREES = 40
# A region across the antimeridian has bounds of 360 degrees in EPSG:4326, however small it is (an island of Fiji): its
# real span is that of its bounds in a Mercator centred on the Pacific (WGS 84 / PDC Mercator, its seam at 30° W), whose
# x is proportional to the longitude, PACIFIC_M_PER_DEGREE metres per degree
PACIFIC_CRS = 'EPSG:3832'
PACIFIC_M_PER_DEGREE = 6378137 * 3.141592653589793 / 180

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


def crs_for(info):
	"""The automatic CRS of a region from INFO, {'centroid': [lon, lat], 'bounds': the coordinates of its bounding box
	in EPSG:4326 ([[[lon, lat], ...]], those of ee.Geometry.bounds)} and, for a region across the antimeridian (whose
	bounds then span 360), 'pacific', those of its bounding box in PACIFIC_CRS: GLOBAL_CRS when the region spans more
	than WIDE_DEGREES of longitude (across the antimeridian without 'pacific': 360), else the UTM zone of the centre
	(also without bounds). Without Earth Engine."""
	ring = (info.get('bounds') or [[]])[0]
	lons = [p[0] for p in ring]
	span = max(lons) - min(lons) if lons else 0
	if span > 359 and info.get('pacific'):  # across the antimeridian: its real span, in the Mercator of the Pacific
		xs = [p[0] for p in info['pacific'][0]]
		span = (max(xs) - min(xs)) / PACIFIC_M_PER_DEGREE
	if span > WIDE_DEGREES:
		return GLOBAL_CRS
	lon, lat = info['centroid']
	return utm_of(lon, lat)


def auto_crs(geom, max_error=1000):
	"""The CRS of the statistics and grids of GEOM (an ee.Geometry) chosen automatically: WGS 84 / UTM zone of its
	centre or, when it is too wide for one (it spans more than WIDE_DEGREES of longitude: whole biomes, Russia...),
	GLOBAL_CRS (equal area, in metres); see crs_for. One request to Earth Engine, with a tolerance of MAX_ERROR metres,
	and another one for a region across the antimeridian (its span in PACIFIC_CRS: a small one, e.g. an island of
	Fiji, keeps its UTM zone; GLOBAL_CRS if that request fails, e.g. near the poles, where Mercator does not reach)."""
	info = ee.Dictionary({'centroid': geom.centroid(max_error).coordinates(),
	                      'bounds': geom.bounds(max_error).coordinates()}).getInfo()
	lons = [p[0] for p in (info.get('bounds') or [[]])[0]]
	if lons and max(lons) - min(lons) > 359:
		try:
			info['pacific'] = geom.bounds(max_error, PACIFIC_CRS).coordinates().getInfo()
		except ee.EEException:
			pass  # without it, crs_for gives GLOBAL_CRS
	return crs_for(info)


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
	  biome_id       code of a biome of RESOLVE Ecoregions 2017 (1 to 14, or 99 Rock and Ice: those of the classes of
	                 BIOME), or a list of them: a feature per biome, named by its name, the union of its ecoregions
	  biome_at       [lon, lat]: the biome of the ecoregion at that point (none in the sea)
	  country        ISO3 code of a country (e.g. 'ESP'), or a list of them (FAO GAUL 2025)
	  admin1         GAUL1_CODE of a first-level administrative unit (region, state, province...), or a list of them
	  admin2         GAUL2_CODE of a second-level administrative unit (province, district, municipality...), or a list
	                 (see find_admin_units for the codes)
	  admin3         code of the INE of a municipality of Spain (5 digits, e.g. '18134' Monachil), or a list of them:
	                 their polygons of the Instituto Geográfico Nacional (see monitoreo.municipalities)
	  island_at      [lon, lat]: the island (of more than 1 km²) at that point
	  bbox           [west, south, east, north] in degrees
	  point          [lon, lat], with buffer (metres, default 0)
	and, with any of them, within: another region (with an area); only the part of each feature inside its union is
	kept (with a tolerance of WITHIN_MAX_ERROR m), and the features outside it are left out, e.g. the Mediterranean
	biome in Spain: {'biome_id': 12, 'within': {'country': 'ESP'}}. A whole biome spans continents: within cuts it, and
	the cost of its union (only its ecoregions that touch the region of within are joined).
	Each feature has a 'name' property (used to label the rows of the time series). An ee.FeatureCollection is
	returned as it is. The dictionary is checked before Earth Engine is asked anything (see check)."""
	if not isinstance(spec, dict) and isinstance(spec, ee.FeatureCollection):
		return spec
	k = check(spec)
	inside = region(spec['within']).geometry(WITHIN_MAX_ERROR) if spec.get('within') is not None else None
	fc = _of(k, spec[k], spec, inside)
	return fc if inside is None else _within(fc, inside)


def check(spec, what='region'):
	"""The key of the region SPEC (see region), after checking it without Earth Engine: a dictionary with one region,
	its codes of biomes and points, and its within (another region with an area, checked the same); else ValueError.
	WHAT names it in the messages."""
	keys = [k for k in REGION_KEYS if spec.get(k) is not None] if isinstance(spec, dict) else []
	if len(keys) != 1:
		if what == 'within':
			raise ValueError(f"within is another region, a dictionary with one of: {', '.join(REGION_KEYS)}; e.g. "
			                 '{"country": "ESP"}')
		if not isinstance(spec, dict):
			raise ValueError(f"give the region as a dictionary with one of: {', '.join(REGION_KEYS)}")
		raise ValueError(f"give one region: {', '.join(REGION_KEYS)}")
	k = keys[0]
	if what == 'within' and k == 'point' and not spec.get('buffer'):
		raise ValueError('within takes a region with an area: give the point a buffer (metres)')
	if k == 'biome_id':
		biome_codes(spec[k])
	if k == 'biome_at':
		_point(spec[k], k)
	if k == 'admin3':
		municipality_codes(spec[k])
	if spec.get('within') is not None:
		check(spec['within'], 'within')
	return k


def municipality_codes(v):
	"""The codes of the INE of the municipalities of Spain V (one, or a list; '18134' or 18134), checked against the
	index of the package without Earth Engine (else ValueError, with the way to find them)."""
	from . import municipalities
	codes = [str(x).strip().zfill(5) for x in (v if isinstance(v, (list, tuple)) else [v])]
	known = {r[0] for r in municipalities.load()['rows']}
	unknown = [c for c in codes if c not in known]
	if not codes or unknown:
		raise ValueError(f"admin3 is the code of the INE of a municipality of Spain (5 digits, e.g. '18134'): "
		                 f"{', '.join(unknown) or 'none given'} is not one (find them with find_admin_units, level 3)")
	return codes


def _point(v, key):
	"""V as [lon, lat] (two numbers, in degrees); ValueError, naming KEY, if it is not."""
	try:
		lon, lat = [float(x) for x in v]
	except (TypeError, ValueError):
		raise ValueError(f'{key} is a point, [lon, lat] in degrees, e.g. [-3.3, 37.1]; not {v!r}') from None
	if not (math.isfinite(lon) and math.isfinite(lat)):
		raise ValueError(f'{key} is a point, [lon, lat] in degrees, e.g. [-3.3, 37.1]; not {v!r}')
	return [lon, lat]


def _whole(x):
	"""X as a whole number (an int), or None if it is not one (as categorical._code)."""
	try:
		f = float(str(x).strip())
	except (TypeError, ValueError):
		return None
	return int(f) if math.isfinite(f) and f == int(f) else None


def biome_codes(v):
	"""V (the code of a biome of RESOLVE Ecoregions 2017, a list of them or a text with commas) as the codes of the
	biomes, each once, in their order; ValueError, without Earth Engine, if one is not a code of the table of the biomes
	(catalog.biomes: BIOME_CODES), or if there are none."""
	if isinstance(v, str):
		values = [x for x in v.replace(';', ',').split(',') if x.strip()]
	else:
		values = list(v) if isinstance(v, (list, tuple)) else [v]
	if not values:
		raise ValueError(f'biome_id takes the codes of the biomes of RESOLVE Ecoregions 2017, {BIOME_CODES}, e.g. 12: '
		                 'list_classes of BIOME gives them')
	known = [b['code'] for b in catalog.biomes()]
	out = []
	for x in values:
		c = _whole(x)
		if c is None or c not in known:
			shown = c if c is not None else repr(x) if isinstance(x, str) else x
			raise ValueError(f'biome_id takes the codes of the biomes of RESOLVE Ecoregions 2017, {BIOME_CODES}, not '
			                 f'{shown}: list_classes of BIOME gives them')
		if c not in out:
			out.append(c)
	return out


def biome_name(code, lang='en'):
	"""The name of the biome CODE (in Spanish with LANG 'es'), from the table of classes of BIOME, or None."""
	c = _whole(code)
	return next((b['name'] for b in catalog.biomes(lang) if b['code'] == c), None)


def ecoregion_name(code):
	"""The name of the ecoregion CODE (its ECO_ID), from the table of classes of ECOREGION, or None."""
	c = _whole(code)
	row = catalog.classes_table('ecoregions')['classes'].get(str(c)) if c is not None else None
	return row[0] if row else None


def _of(k, v, spec, inside):
	"""ee.FeatureCollection of the region of key K and value V of SPEC (see region); INSIDE: the geometry of its
	within (to join only the ecoregions of a biome there), or None."""
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
	if k == 'biome_id':
		return ee.FeatureCollection([_biome(c, inside) for c in biome_codes(v)])
	if k == 'biome_at':
		return _biome_at(_point(v, k), inside)
	if k == 'country':
		codes = [str(x).strip().upper() for x in (v if isinstance(v, (list, tuple)) else [v])]
		return ee.FeatureCollection([_country(c) for c in codes])
	if k in ('admin1', 'admin2'):
		level = int(k[-1])
		ids = [int(x) for x in (v if isinstance(v, (list, tuple)) else [v])]
		fc = ee.FeatureCollection(GAUL[level]).filter(ee.Filter.inList(f'GAUL{level}_CODE', ids))
		return _named(fc, 'DISP_EN')  # e.g. «Granada, Andalucía, Spain»: the names of the units repeat in other countries
	if k == 'admin3':  # the municipalities of Spain (monitoreo.municipalities), named with their province
		from . import municipalities
		codes = municipality_codes(v)
		fc = ee.FeatureCollection(municipalities.ASSET).filter(ee.Filter.inList('code', codes))
		return fc.map(lambda f: f.set('name', ee.String(f.get('name')).cat(' (').cat(f.get('province')).cat(')')))
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


def _biome(code, inside=None):
	"""The biome CODE as a single feature named by its name (and with its code, biome): the union of its ecoregions,
	those of its ECO_IDs in the table of classes (not of the BIOME_NUM of the data, which for Rock and Ice is that of
	the Tundra), dissolved with a tolerance of BIOME_MAX_ERROR m; with INSIDE (an ee.Geometry), only the ecoregions
	that touch it, which cuts the cost of the union. Never fetched as _fetched does: its geometry is too big."""
	eco = ee.FeatureCollection(ECOREGIONS).filter(ee.Filter.inList('ECO_ID', catalog.ecoregions_of_biome(code)))
	if inside is not None:
		eco = eco.filterBounds(inside)
	union = eco.geometry(BIOME_MAX_ERROR).dissolve(BIOME_MAX_ERROR)
	return ee.Feature(union, {'name': biome_name(code), 'biome': code})


def _biome_at(point, inside=None):
	"""The biome of the ecoregion at POINT ([lon, lat]) as _biome (two at a boundary; none in the sea): of each biome
	of the table, its feature if one of its ecoregions is at the point; Earth Engine joins only that one (If)."""
	at = ee.FeatureCollection(ECOREGIONS).filterBounds(ee.Geometry.Point(point))
	feats = [ee.Algorithms.If(at.filter(ee.Filter.inList('ECO_ID', catalog.ecoregions_of_biome(b['code']))).size(),
	                          _biome(b['code'], inside), None) for b in catalog.biomes()]
	return ee.FeatureCollection(ee.List(feats).removeAll([None]))


def _within(fc, inside):
	"""The part of each feature of FC inside INSIDE (the geometry of the region of within), with its properties; the
	features outside it are left out."""
	return fc.filterBounds(inside).map(lambda f: f.intersection(ee.Feature(inside), WITHIN_MAX_ERROR))


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
	the names of the country and of the first level, ISO3_CODE, DISP_EN (the full name), level}]. LEVEL 3: the
	municipalities of Spain, of the Instituto Geográfico Nacional, without Earth Engine (monitoreo.municipalities.find:
	[{ADMIN3_CODE, NAME, PROVINCE, REGION, ISO3_CODE, DISP_EN, level}], any case and accents; the code of the INE too)."""
	level = int(level)
	if level == 3:
		from . import municipalities
		if country and str(country).strip().upper() != municipalities.COUNTRY:
			raise ValueError('level 3 is the municipalities of Spain (country ESP); other countries have levels 1 and 2')
		return municipalities.find(text, limit=limit)
	if level not in GAUL:
		raise ValueError('level is 1 (regions, states, provinces...), 2 (provinces, districts, municipalities...) or '
		                 '3 (the municipalities of Spain)')
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


# the vector files that MonitorEO writes (the perimeter of the burned area of burn_severity): their driver of OGR by
# their extension
VECTOR_DRIVERS = {'.gpkg': 'GPKG', '.geojson': 'GeoJSON', '.shp': 'ESRI Shapefile'}


def vector_driver(path):
	"""The driver of OGR of the vector file PATH, by its extension (see VECTOR_DRIVERS)."""
	ext = os.path.splitext(str(path))[1].lower()
	if ext not in VECTOR_DRIVERS:
		raise ValueError(f"write the polygons to a file {', '.join(VECTOR_DRIVERS)}, not {os.path.basename(str(path))}")
	return VECTOR_DRIVERS[ext]


def save_polygons(rows, path, layer, types):
	"""Write ROWS ([{field: value, ..., 'geometry': a GeoJSON geometry in EPSG:4326}]) to the vector file PATH (its
	format by its extension, see vector_driver) as the layer LAYER of MultiPolygons in EPSG:4326, valid (OGR MakeValid:
	the polygons joined by a corner become two), with the fields TYPES ({name: str, int or float}). A row without
	polygons is written without geometry. Returns PATH."""
	ogr = _ogr()
	drv = ogr.GetDriverByName(vector_driver(path))
	if os.path.exists(path):
		drv.DeleteDataSource(path)
	ds = drv.CreateDataSource(path)
	lyr = ds.CreateLayer(layer, wgs84(), ogr.wkbMultiPolygon)
	kinds = {str: ogr.OFTString, int: ogr.OFTInteger, float: ogr.OFTReal}
	for name, kind in types.items():
		lyr.CreateField(ogr.FieldDefn(name, kinds[kind]))
	for r in rows:
		feat = ogr.Feature(lyr.GetLayerDefn())
		for name, kind in types.items():
			if r.get(name) is not None:
				feat.SetField(name, kind(r[name]))
		g = r.get('geometry')
		if g and g.get('coordinates'):
			geom = ogr.CreateGeometryFromJson(json.dumps(g))
			if not geom.IsValid():
				geom = geom.MakeValid()
			feat.SetGeometry(_polygons(geom, ogr))
		lyr.CreateFeature(feat)
	ds = None
	return path


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
