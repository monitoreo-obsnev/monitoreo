"""What to cite with each result of MonitorEO: the references of the variable (the articles of its formula or algorithm
and its Earth Engine datasets, cited as their pages of the Earth Engine catalog suggest), of the pixel filters, of the
method (trends, burn severity), of the region (protected areas, ecoregions and biomes, administrative units, islands,
and those of the region of its within), of Google Earth Engine and of MonitorEO.
They are in catalog.json (references, datasets, methods and the references of each variable); this module gathers
those of a call of a tool:

    cite('trend_table', {'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
                         'start': '2018-01-01', 'end': '2024-12-31'})
    -> {'references': [{'id', 'citation', 'doi', 'url', 'text'}, ...],   (in the order of a list of references)
        'credits': ['Contains modified Copernicus Sentinel data 2018-2024']}

A reference has its citation (APA) and its DOI (or, without one, its URL); 'text' is the citation with the link. The
credits are the lines that the terms of use of some data ask for (Copernicus Sentinel, USGS Landsat, Copernicus DEM,
MERIT Hydro).
Every result of monitoreo.services carries both, and the reports (monitoreo.report, monitoreo.publish) list them.

References:
    Gorelick, N., Hancher, M., Dixon, M., Ilyushchenko, S., Thau, D., & Moore, R. (2017). Google Earth Engine:
    Planetary-scale geospatial analysis for everyone. Remote Sensing of Environment, 202, 18–27.
    https://doi.org/10.1016/j.rse.2017.06.031
"""

import datetime as dt
import unicodedata

from . import about, areas, catalog, fire, landcover, perimeters, sensors

MONITOREO = 'monitoreo'  # the ID of the citation of MonitorEO (monitoreo.about)
LANDSAT = 'LANDSAT'  # the collection of the catalog with Landsat 5, 7, 8 and 9 (monitoreo.sensors.LANDSAT)
CLOUD_SCORE = sensors.CLOUD_SCORE
WORLDCOVER = 'ESA/WorldCover/v200'
WDPA = 'WCMC/WDPA/current/polygons'
ECOREGIONS = 'RESOLVE/ECOREGIONS/2017'
TRENDS = ('trend_table', 'trend_map', 'download_trend')
RGB = ('rgb_map', 'download_rgb')  # the true colour of the images of a variable: its data, not its formula (see cite)
# tools that compute in Earth Engine (the others only read the catalog or publish)
EARTH_ENGINE = TRENDS + ('time_series', 'time_series_to_drive', 'export_time_series_to_drive', 'map_layer',
                         'region_stats', 'thumbnail', 'composite_image', 'export_image', 'export_image_to_drive',
                         'download_image', 'download_variables', 'compare_series', 'compare_map', 'download_comparison',
                         'burn_severity', 'find_protected_areas', 'timelapse', 'area_by_class', 'transect',
                         'map_figure', 'image_count', 'recovery_metrics', 'control_ring', 'recovery_map', 'anomalies') + RGB


# The references of the data of Earth Engine outside the datasets of catalog.json met so far (see of_asset): {id:
# {'citation', 'doi' or 'url'}}, from their STAC record or their record in the GEE Community Catalog
DATA = {}


def bibliography():
	"""Every reference of the catalog, by its ID, with that of MonitorEO (and those of the data of Earth Engine outside
	the catalog met so far, DATA): {id: {'citation', 'doi' or 'url'}}."""
	refs = dict(catalog.load()['references'])
	refs.update(DATA)
	refs[MONITOREO] = {'citation': about.CITATION.replace(f'https://doi.org/{about.DOI}', '').strip(),
	                   'doi': about.DOI}
	return refs


def _fill(text, date, data_years):
	date = date or dt.date.today()
	return text.replace('{year}', str(date.year)).replace('{month_year}', date.strftime('%B %Y')).replace(
		'{data_years}', data_years or str(date.year))


def get(rid, date=None, data_years=None):
	"""The reference RID: {'id', 'citation', 'doi', 'url', 'text'}. DATE (default: today) is that of the computation,
	for the data whose version changes (the protected areas of the WDPA)."""
	r = bibliography()[rid]
	citation = _fill(r['citation'], date, data_years)
	url = f"https://doi.org/{r['doi']}" if r.get('doi') else r.get('url')
	return {'id': rid, 'citation': citation, 'doi': r.get('doi'), 'url': url,
	        'text': f'{citation} {url}' if url else citation}


def _sort_key(ref):
	text = unicodedata.normalize('NFKD', ref['citation']).encode('ascii', 'ignore').decode().lower()
	return text.lstrip("'\"( ")


def _period(args):
	"""(first, last) day of the data of a call (both periods of a comparison), or None. A period with a start and no
	end ends today, as services.make_spec computes it."""
	days = [str(args[k])[:10] for k in ('start', 'end', 'other_start', 'other_end') if args.get(k)]
	if (args.get('start') and not args.get('end')) or (args.get('other_start') and not args.get('other_end')):
		days.append(dt.date.today().isoformat())
	period = (args.get('recipe') or {}).get('period') if isinstance(args.get('recipe'), dict) else None
	if isinstance(period, (list, tuple)) and len(period) == 2:
		days += [str(period[0])[:10], str(period[1])[:10]]
	if not days:
		return None
	return min(days), max(days)


def _years(period):
	if not period:
		return None
	a, b = period[0][:4], period[1][:4]
	return a if a == b else f'{a}-{b}'


def datasets(collection, period=None, quality=None):
	"""The Earth Engine datasets of COLLECTION: itself, or, for LANDSAT, the Landsat collections of the PERIOD
	((first, last day); all of them without it; Landsat 7 until its last image with quality landsat7, see
	sensors.landsat_parts), or, for a collection with a gap-filled version (sensors.GAP_FILLED),
	that version up to its last image and the collection after it, those of the PERIOD."""
	dates = catalog.load()['collections']
	if collection in sensors.GAP_FILLED:
		filled = sensors.GAP_FILLED[collection]
		last = dates.get(filled, {}).get('end')  # its last image (catalog.json: the same date as sensors.raw_collection)
		out = [filled] if not (period and last and period[0] > last) else []
		# the images of the collection after it: those of the next year (both have composites of 8 days from 1 January)
		if not period or not last or period[1] >= f'{int(last[:4]) + 1}-01-01':
			out.append(collection)
		return out
	if collection != LANDSAT:
		return [collection]
	out = []
	for col, _, last in sensors.landsat_parts(quality):
		end = last or dates.get(col, {}).get('end')
		if col == sensors.LANDSAT7['collection'] and not last:  # with landsat7: until its last image
			from . import coverage
			end = (coverage._records().get(col) or {}).get('end') or end
		start = dates.get(col, {}).get('start')
		if period and ((end and end < period[0]) or (start and start > period[1])):
			continue
		out.append(col)
	return out


def of_datasets(collections):
	"""(reference IDs, credit lines) of the Earth Engine datasets COLLECTIONS, as their catalog pages suggest."""
	known = catalog.load()['datasets']
	ids, credits = [], []
	for col in collections:
		d = known.get(col) or {}
		ids += d.get('references', [])
		if d.get('credit') and d['credit'] not in credits:
			credits.append(d['credit'])
	return ids, credits


# The families of data of Earth Engine whose terms of use ask for a credit line (and, the Copernicus DEM, for its
# references) whatever the dataset: (start of their IDs, the dataset of catalog.json with that credit, with its
# references too). The Landsat data: the credit of Level-2 for the surface reflectance (_L2), else that of Level-1.
FAMILIES = (('COPERNICUS/DEM/', 'COPERNICUS/DEM/GLO30_2024_1', True),
            ('COPERNICUS/S1', 'COPERNICUS/S2_SR_HARMONIZED', False),
            ('COPERNICUS/S2', 'COPERNICUS/S2_SR_HARMONIZED', False),
            ('COPERNICUS/S3/', 'COPERNICUS/S2_SR_HARMONIZED', False),
            ('COPERNICUS/S5P/', 'COPERNICUS/S2_SR_HARMONIZED', False),
            ('LANDSAT/', 'LANDSAT/LC08/C02/T1_TOA', False))
LANDSAT_L2 = 'LANDSAT/LC08/C02/T1_L2'


def family(asset):
	"""(the dataset of catalog.json whose credit line the terms of use of ASSET ask for, whether with its references
	too), or (None, False): COPERNICUS/DEM/* that of the Copernicus DEM; the Sentinels (COPERNICUS/S1*, S2*, S3/*,
	S5P/*) that of the Copernicus Sentinel data; LANDSAT/* that of the USGS."""
	for start, dataset, refs in FAMILIES:
		if asset.startswith(start):
			return (LANDSAT_L2 if dataset.startswith('LANDSAT/') and '_L2' in asset else dataset), refs
	return None, False


def of_asset(asset):
	"""(reference IDs, credit lines) of the data of Earth Engine ASSET (an image or a collection given by its ID): as
	the datasets of catalog.json say if it is one of them, else from its STAC record in the Earth Engine data catalog
	or its record in the GEE Community Catalog (see monitoreo.assets.cite), with the credit line that the terms of use
	of its family ask for, in the words of catalog.json (see family: the Copernicus Sentinel data, the Copernicus DEM,
	with its references, and Landsat)."""
	from . import assets
	asset = assets.normalize(asset)
	if asset in catalog.load()['datasets']:
		return of_datasets([asset])
	refs, credits, methods = assets.cite(asset)
	ids = []
	for rid, ref in refs:
		DATA[rid] = ref
		ids.append(rid)
	dataset, with_refs = family(asset)
	if dataset:
		more, cred = of_datasets([dataset])
		ids += more if with_refs else []
		credits = cred + [c for c in credits if c not in cred]
	return ids + [i for m in methods for i in ([m] if m in catalog.load()['references'] else _methods(m))], credits


def of_data(asset):
	"""What to cite with the data of Earth Engine ASSET, whatever the period: {'references', 'credits'} as cite
	(without Earth Engine and MonitorEO)."""
	ids, credits = of_asset(asset)
	years = '[years of the data]'
	return {'references': sorted((get(i, data_years=years) for i in dict.fromkeys(ids)), key=_sort_key),
	        'credits': list(dict.fromkeys(_fill(c, None, years) for c in credits))}


def _methods(name):
	return list(catalog.load()['methods'].get(name, []))


def of_variable(entry, quality=None, period=None, formula=True):
	"""(reference IDs, credit lines) of a variable of the catalog (its entry): those of its formula or algorithm, of its
	Earth Engine datasets in PERIOD and of its pixel filters with QUALITY (Landsat: the QA band of CFMask; Sentinel-2:
	Cloud Score+ for the clouds, else the SCL of Sen2Cor, which also gives water and snow). Without FORMULA (the true
	colour of its images), not those of its formula, except for the algorithms that decide which pixels it keeps (the
	snow cover frequency and the cloud frequency); see cite for the metrics max and min."""
	keep = formula or sensors.is_scf(entry) or sensors.is_cf(entry)
	ids = list(entry.get('references', [])) if keep else []
	cols = datasets(entry['col'], period, quality)
	on = sensors.filters(entry, quality)
	q = dict(sensors.QUALITY, **(quality or {}))
	if entry['sensor'] == 'Sentinel-2':
		if on['clouds'] and q.get('cloud_score') is not None:
			cols.append(CLOUD_SCORE)
		if (on['clouds'] and q.get('cloud_score') is None) or on['water'] or on['snow']:
			ids += _methods('sentinel2_scl')
	elif entry['sensor'] == 'Landsat' and (on['clouds'] or on['water'] or on['snow']):
		ids += _methods('landsat_qa')
	if sensors.snow_ndsi_of(entry, q) is not None:  # the snow by its NDSI
		ids += _methods('snow_ndsi')
	if sensors.permanent_water_of(entry, q):  # the permanent water of the JRC Global Surface Water
		cols.append(sensors.PERMANENT_WATER['image'])
	if sensors.harmonize(q) and not sensors.no_harmonize(entry):  # Landsat 5 and 7 as Landsat 8 and 9 (Roy et al. 2016)
		ids += _methods('harmonize')
	if sensors.topographic(q) and not sensors.no_topographic(entry):  # SCS+C, with the slope and aspect of the SRTM
		ids += _methods('topographic')
		cols.append(sensors.TOPOGRAPHIC['dem'])
	if sensors.is_cf(entry) and entry['sensor'] == 'Sentinel-2':  # the clouds of the cloud frequency: Cloud Score+
		cols.append(CLOUD_SCORE)
	if sensors.is_scf(entry) and entry['sensor'] in ('Landsat', 'Sentinel-2'):  # the SCF of Landsat and Sentinel-2 also
		# reads the TOA scenes (snow in the shadow) and the SRTM (its hillShadow), and that of Sentinel-2 always Cloud
		# Score+ (its fixed clouds); that of MODIS, only its daily snow product
		cols += [sensors.SCF_TOA[c][0] for c in list(cols) if c in sensors.SCF_TOA] + [sensors.SCF['dem']]
		if entry['sensor'] == 'Sentinel-2' and CLOUD_SCORE not in cols:
			cols.append(CLOUD_SCORE)
	more, credits = of_datasets(cols)
	return ids + more, credits


def _entry(variable, sensor=None, collection=None, ref=None):
	try:
		return catalog.find(variable, sensor, collection, ref)
	except (KeyError, ValueError, TypeError):
		return None


def of_spec(var, period=None, formula=True):
	"""(reference IDs, credit lines) of a variable as given to the tools or in a recipe: {'index', 'sensor',
	'collection', 'quality', 'exclude_landcover', 'where'} of the catalog, or {'collection' or 'image', ...} of other
	data of Earth Engine (see of_asset); with the variables of the conditions of where (the pixels of the study area
	kept)."""
	ids, credits = [], []
	entry = _entry(var.get('index') or var.get('variable'), var.get('sensor'), var.get('collection')) \
		if (var.get('index') or var.get('variable')) else None
	if entry:
		ids, credits = of_variable(entry, var.get('quality'), period, formula)
	else:
		asset = var.get('collection') or var.get('image')
		if asset:
			ids, credits = of_asset(asset)
	if var.get('exclude_landcover'):
		more, _ = of_datasets([WORLDCOVER])
		ids += more
	conditions = var.get('where') or []
	for c in [conditions] if isinstance(conditions, dict) else conditions:
		if landcover.is_landcover(c):  # its land cover map and the table of correspondences of its classes
			maps, crosswalk = landcover.citations(c)
			more, cred = of_datasets(maps)
			ids += more + crosswalk
			credits += [x for x in cred if x not in credits]
		elif isinstance(c, dict) and c.get('variable'):
			more, cred = of_spec({'index': c['variable'], 'sensor': c.get('sensor'), 'collection': c.get('collection'),
			                      'quality': c.get('quality')}, period)
			ids += more
			credits += [x for x in cred if x not in credits]
	return ids, credits


def _region(region):
	"""The datasets of the REGION of a call (see areas.region): those of its kind and those of its within."""
	cols = []
	if isinstance(region, dict):
		if 'wdpa_id' in region or 'wdpa_name' in region:
			cols.append(WDPA)
		if any(k in region for k in ('ecoregion_id', 'ecoregion_at', 'biome_id', 'biome_at')):
			cols.append(ECOREGIONS)
		if 'country' in region:
			cols.append(areas.GAUL_COUNTRIES)
		for level in (1, 2):
			if f'admin{level}' in region:
				cols.append(areas.GAUL[level])
		if 'admin3' in region:  # the municipalities of Spain, of the IGN
			from . import municipalities
			cols.append(municipalities.ASSET)
		if 'island_at' in region:
			cols.append(areas.ISLANDS)
		if 'sea' in region or 'sea_at' in region:  # the sea areas of the IHO, of Marine Regions
			from . import seas
			cols.append(seas.ASSET)
		if isinstance(region.get('within'), dict):  # the region of within: e.g. FAO GAUL for a biome in a country
			cols += [c for c in _region(region['within']) if c not in cols]
	return cols


def _perimeter_refs(region):
	"""The references of the official perimeters of REGION and of its within: EFFIS, San-Miguel-Ayanz et al. (2012)."""
	out = ['sanmiguelayanz2012'] if region.get('effis_id') is not None else []
	if isinstance(region.get('within'), dict):
		out += _perimeter_refs(region['within'])
	return out


def _picks(args):
	"""Whether the variable of a true colour chooses the image of each pixel (its metric, or its metric between
	years, max or min: the colours of the image where the variable is highest or lowest), so that its formula is
	cited."""
	from .composite import MOSAICS

	def low(k):
		return str(args.get(k) or '').strip().lower()

	return low('metric') in MOSAICS or ((args.get('temporal') or 'period') != 'period' and low('interannual') in MOSAICS)


def _uses_cv(tool, args, recipe=None):
	"""Whether the result of the call of TOOL with ARGS has coefficients of variation (composite.CV): its metric, its
	metric between the years (if the images are aggregated by years), its statistic over the region or one of its
	statistics (region_stats: by default, see catalog.REGION_STATS and REGION_STATS_ZONES; the RBR and the RdNBR of
	burn_severity), a condition of where on them, or the same of a variable of its RECIPE (with the defaults of the
	recipe). A fixed layer (elevation, slope, an image) has no images: its metrics, which the services ignore, do not
	count."""
	def cv(x):
		return str(x or '').strip().lower() == 'cv'

	def static(a):
		if not (a.get('index') or a.get('variable')):
			return bool(a.get('image'))
		e = _entry(a.get('index') or a.get('variable'), a.get('sensor'), a.get('collection'))
		return bool(e and e.get('static'))

	def of(a):
		if static(a):
			return cv(a.get('stat'))
		metrics = a.get('metrics') or a.get('metric')
		metrics = metrics if isinstance(metrics, (list, tuple)) else [metrics]
		between = a.get('interannual') if (a.get('temporal') or 'period') != 'period' else None
		return any(cv(m) for m in list(metrics) + [between, a.get('stat')])

	def where(a):  # the conditions on variables (not the land covers) of the pixels kept
		conditions = a.get('where') or []
		conditions = [conditions] if isinstance(conditions, dict) else conditions
		return any(of(c) for c in conditions if isinstance(c, dict) and (c.get('variable') or c.get('index')))

	if tool == 'burn_severity':
		return str(args.get('index') or '').lower() in ('rbr', 'rdnbr') or where(args)
	if tool == 'time_series' and args.get('doy') and cv(args.get('interannual')):  # between the years of the profile
		return True
	if tool == 'region_stats':
		stats = args.get('stats')
		name = args.get('index') or args.get('variable')
		e = _entry(name, args.get('sensor'), args.get('collection')) if name else None
		if e is None and args.get('ref') is not None:
			e = _entry(None, None, None, args['ref'])
		if e and e.get('classes'):  # a categorical layer: its statistic is the majority class (as region_stats)
			default = ('mode',)
		else:
			default = catalog.REGION_STATS_ZONES if args.get('zones') else catalog.REGION_STATS  # as region_stats
		stats = [stats] if isinstance(stats, str) else list(stats or default)
		if any(cv(s) for s in stats):
			return True
	if recipe is not None:
		defaults = {k: v for k, v in recipe.items() if k in ('temporal', 'interannual', 'where')}
		return any(of(dict(defaults, **v)) or where(dict(defaults, **v))
		           for v in recipe.get('variables') or [] if isinstance(v, dict))
	return of(args) or where(args)


def _test_methods(test):
	"""The references of the trends with the trend test TEST ('mk', 'hamed-rao' or 'tfpw'; see monitoreo.trends)."""
	test = str(test or 'mk').lower()
	return _methods('trends') + (_methods(f'trends_{test}') if test != 'mk' else [])


def cite(tool, args=None, date=None, datasets=()):
	"""What to cite with the result of the call of TOOL (a function of monitoreo.services or a tool of the MCP server)
	with ARGS: {'references': [{'id', 'citation', 'doi', 'url', 'text'}], 'credits': [lines]}, the references in the
	order of a list of references. DATE (default: today) is that of the computation; DATASETS, other Earth Engine
	datasets that it used."""
	args = dict(args or {})
	period = _period(args)
	ids, credits = [], []
	cols = _region(args.get('region')) + _region(args.get('area')) + _region(args.get('offset_region')) + list(datasets)
	recipe = None
	if tool == 'download_variables':
		recipe = args.get('recipe') or {}
		if not isinstance(recipe, dict):
			from . import recipe as recipes
			try:
				recipe = recipes.read(recipe)
			except (ValueError, OSError):
				recipe = {}
		defaults = {k: recipe.get(k) for k in ('quality', 'exclude_landcover', 'where', 'period') if recipe.get(k)}
		for v in recipe.get('variables') or []:
			v = dict(defaults, **v)
			more, cred = of_spec(v, _period({'start': v['period'][0], 'end': v['period'][1]})
			                     if isinstance(v.get('period'), (list, tuple)) and len(v['period']) == 2 else period)
			ids += more
			credits += cred
		if recipe.get('ecoregion'):
			cols.append(ECOREGIONS)
	elif tool == 'burn_severity':
		index = {'rbr': 'RBR', 'rdnbr': 'RdNBR'}.get(str(args.get('index') or 'dNBR').lower(), 'NBR')
		spec = {'index': index, 'sensor': args.get('sensor') or 'Sentinel-2', 'where': args.get('where'),
		        'quality': fire.burn_quality(args.get('quality') if isinstance(args.get('quality'), dict) else None)}
		if args.get('collection'):  # MODIS Aqua (MYD09GA) for the RdNBR
			spec['collection'] = args['collection']
		more, credits = of_spec(spec, period)
		ids += more + _methods({'RBR': 'rbr', 'RdNBR': 'rdnbr'}.get(index, 'burn_severity'))
		if args.get('offset_region'):  # the offset of the dNBR, as Miller & Thode 2007 and Parks et al. 2014
			ids += ['miller2007', 'parks2014']
	elif tool == 'area_by_class' and args.get('landcover'):  # a land cover map of a year, with its crosswalk
		try:
			m, year, _ = landcover.check({'landcover': args['landcover'], 'year': args.get('year'),
			                              'exclude': [landcover.classes()[0]['key']]})
			years = [year] + ([int(args['other_year'])] if args.get('other_year') not in (None, '') else [])
			ids, credits = of_datasets(list(dict.fromkeys(landcover.dataset(m, y) for y in years)))
			ids += list(m.get('crosswalk_references') or [])
		except (ValueError, KeyError, TypeError):
			pass
	elif args.get('variable') or args.get('index') or args.get('collection') or args.get('image'):
		ids, credits = of_spec(args, period, formula=tool not in RGB or _picks(args))
	if tool in TRENDS:
		ids += _test_methods(args.get('test'))
	if tool == 'timelapse':
		ids += _methods('timelapse')
	if tool == 'recovery_metrics':  # Marcos et al. 2023, STL, Mann-Kendall and Sen
		ids += _methods('recovery')
	if tool == 'recovery_map':  # Marcos et al. 2023 on the annual series of each pixel (no STL)
		ids += ['marcos2023']
	ring = args.get('ring') if tool in ('time_series', 'recovery_metrics') else \
		{k: args.get(k) for k in ('match', 'exclude', 'within')} if tool == 'control_ring' else None
	if ring:  # the matching of the pixels of the control ring: the fixed layers of the Copernicus DEM, and its regions
		from . import control
		try:
			opts = control.check(ring if isinstance(ring, dict) else True)
		except ValueError:
			opts = dict(control.DEFAULTS)
		for name in opts['match']:
			more, cred = of_spec({'index': name, 'sensor': control.MATCH.get(name, 'Copernicus')}, period)
			ids += more
			credits += [c for c in cred if c not in credits]
		for k in ('exclude', 'within'):
			if isinstance(ring, dict) and ring.get(k):
				cols += _region(ring[k])
	if tool == 'area_by_class':
		ids += _methods('area_by_class') + (_test_methods(args.get('test')) if args.get('trend') else [])
	if tool == 'map_figure':
		ids += _methods('map_figure')
	if tool == 'time_series' and args.get('doy'):  # a line per year, or the profile, over the days of the year
		ids += _methods('doy')
	if tool == 'time_series' and args.get('other_variable'):  # the variable of the right axis of the profile
		more, cred = of_spec({'index': args['other_variable'], 'sensor': args.get('other_sensor') or args.get('sensor'),
		                      'quality': args.get('quality')}, period)
		ids += more
		credits += [c for c in cred if c not in credits]
	if tool == 'transect':  # the elevation of the profile: the Copernicus DEM
		more, cred = of_spec({'index': 'ELEVATION', 'sensor': 'Copernicus'}, period)
		ids += more + _methods('transect')
		credits += [c for c in cred if c not in credits]
	if tool == 'region_stats' and isinstance(args.get('zones'), dict):  # the variable of the zones
		z = args['zones']
		more, cred = of_spec({'index': z.get('variable') or z.get('index'), 'sensor': z.get('sensor'),
		                      'collection': z.get('collection'), 'quality': z.get('quality')}, period)
		ids += more + _methods('zones')
		credits += [c for c in cred if c not in credits]
	if _uses_cv(tool, args, recipe if tool == 'download_variables' else None):
		ids += _methods('cv')
	if tool == 'find_protected_areas':
		cols.append(WDPA)
	more, cred = of_datasets(cols)
	ids += more
	credits += cred
	ring_args = args.get('ring') if isinstance(args.get('ring'), dict) else {}
	for r in (args.get('region'), args.get('area'), args.get('offset_region'), ring_args.get('exclude'),
	          ring_args.get('within'), *((args.get('exclude'), args.get('within')) if tool == 'control_ring' else ())):
		if isinstance(r, dict):  # official perimeters, also of a control ring, as their sources ask (perimeters)
			ids += _perimeter_refs(r)
			credits += [c for c in perimeters.credits(r) if c not in credits]
	if tool == 'find_burnt_areas':
		ids.append('sanmiguelayanz2012')
		credits += [c for c in [perimeters.EFFIS_CREDIT] if c not in credits]
	if tool in EARTH_ENGINE:
		ids += _methods('earth_engine')
	if tool != 'about':
		ids.append(MONITOREO)
	years = _years(period)
	refs = sorted((get(i, date, years) for i in dict.fromkeys(ids)), key=_sort_key)
	return {'references': refs, 'credits': list(dict.fromkeys(_fill(c, date, years) for c in credits))}


def of_entry(entry, quality=None):
	"""What to cite with the data of a variable of the catalog (its entry), whatever the period: {'references',
	'credits'} as cite (without Earth Engine and MonitorEO)."""
	ids, credits = of_variable(entry, quality)
	years = '[years of the data]'
	return {'references': sorted((get(i, data_years=years) for i in dict.fromkeys(ids)), key=_sort_key),
	        'credits': list(dict.fromkeys(_fill(c, None, years) for c in credits))}


def of_result(tool, args=None, result=None, date=None):
	"""What to cite with a result of TOOL: {'references', 'credits'} of its answer RESULT (the results of
	monitoreo.services and of the MCP server have them), or else of its call (cite)."""
	if isinstance(result, dict) and result.get('references'):
		return {'references': result['references'], 'credits': result.get('credits') or []}
	return cite(tool, args or {}, date)


def _key(ref):
	return ref.get('id') or ref.get('text') or ref.get('citation')


def of_items(items, date=None):
	"""The references of several results ITEMS ([{'tool', 'args', 'result'}], as in a report): (references, credits,
	numbers), the references of all of them in the order of a list of references, their credits, and the numbers in
	that list (from 1) of those of each item."""
	each = [of_result(it.get('tool'), it.get('args'), it.get('result'), date) for it in items]
	by_key = {}
	for c in each:
		for r in c['references']:
			by_key.setdefault(_key(r), r)
	refs = sorted(by_key.values(), key=_sort_key)
	number = {_key(r): i + 1 for i, r in enumerate(refs)}
	credits = list(dict.fromkeys(x for c in each for x in c['credits']))
	return refs, credits, [sorted({number[_key(r)] for r in c['references']}) for c in each]


def bibliography_texts():
	"""Every reference of the catalog as text, in the order of a list of references, without that of MonitorEO and
	with the date of the WDPA left generic (for the metadata of Zenodo, .zenodo.json)."""
	refs = [get(i) for i in catalog.load()['references']]
	for r in refs:
		if '{' in bibliography()[r['id']]['citation']:
			r['citation'] = bibliography()[r['id']]['citation'].replace(' ({year})', '').replace(', {month_year}', '')
			r['text'] = f"{r['citation']} {r['url']}" if r['url'] else r['citation']
	return [r['text'] for r in sorted(refs, key=_sort_key)]


def texts(cited):
	"""The references of CITE (or a list of references) as lines of text, then its credits."""
	refs = cited.get('references', []) if isinstance(cited, dict) else cited
	return [r['text'] for r in refs] + (list(cited.get('credits', [])) if isinstance(cited, dict) else [])
