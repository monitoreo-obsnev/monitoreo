"""What to cite with each result of MonitorEO: the references of the variable (the articles of its formula or algorithm
and its Earth Engine datasets, cited as their pages of the Earth Engine catalog suggest), of the pixel filters, of the
method (trends, burn severity), of the region (protected areas, ecoregions), of Google Earth Engine and of MonitorEO.
They are in catalog.json (references, datasets, methods and the references of each variable); this module gathers
those of a call of a tool:

    cite('trend_table', {'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
                         'start': '2018-01-01', 'end': '2024-12-31'})
    -> {'references': [{'id', 'citation', 'doi', 'url', 'text'}, ...],   (in the order of a list of references)
        'credits': ['Contains modified Copernicus Sentinel data 2018-2024']}

A reference has its citation (APA) and its DOI (or, without one, its URL); 'text' is the citation with the link. The
credits are the lines that the terms of use of some data ask for (Copernicus Sentinel, USGS Landsat, Copernicus DEM).
Every result of monitoreo.services carries both, and the reports (monitoreo.report, monitoreo.publish) list them.

References:
    Gorelick, N., Hancher, M., Dixon, M., Ilyushchenko, S., Thau, D., & Moore, R. (2017). Google Earth Engine:
    Planetary-scale geospatial analysis for everyone. Remote Sensing of Environment, 202, 18–27.
    https://doi.org/10.1016/j.rse.2017.06.031
"""

import datetime as dt
import unicodedata

from . import about, areas, catalog, sensors

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
                         'burn_severity', 'find_protected_areas') + RGB


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
	"""(first, last) day of the data of a call (both periods of a comparison), or None."""
	days = [str(args[k])[:10] for k in ('start', 'end', 'other_start', 'other_end') if args.get(k)]
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


def datasets(collection, period=None):
	"""The Earth Engine datasets of COLLECTION: itself, or, for LANDSAT, the Landsat collections of the PERIOD
	((first, last day); all of them without it)."""
	if collection != LANDSAT:
		return [collection]
	dates = catalog.load()['collections']
	out = []
	for col, _, last in sensors.LANDSAT:
		start, end = dates.get(col, {}).get('start'), last or dates.get(col, {}).get('end')
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


def of_asset(asset):
	"""(reference IDs, credit lines) of the data of Earth Engine ASSET (an image or a collection given by its ID): as
	the datasets of catalog.json say if it is one of them, else from its STAC record in the Earth Engine data catalog
	or its record in the GEE Community Catalog (see monitoreo.assets.cite)."""
	from . import assets
	asset = assets.normalize(asset)
	if asset in catalog.load()['datasets']:
		return of_datasets([asset])
	refs, credits, methods = assets.cite(asset)
	ids = []
	for rid, ref in refs:
		DATA[rid] = ref
		ids.append(rid)
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
	cols = datasets(entry['col'], period)
	on = sensors.filters(entry, quality)
	q = dict(sensors.QUALITY, **(quality or {}))
	if entry['sensor'] == 'Sentinel-2':
		if on['clouds'] and q.get('cloud_score') is not None:
			cols.append(CLOUD_SCORE)
		if (on['clouds'] and q.get('cloud_score') is None) or on['water'] or on['snow']:
			ids += _methods('sentinel2_scl')
	elif entry['sensor'] == 'Landsat' and (on['clouds'] or on['water'] or on['snow']):
		ids += _methods('landsat_qa')
	if sensors.is_cf(entry) and entry['sensor'] == 'Sentinel-2':  # the clouds of the cloud frequency: Cloud Score+
		cols.append(CLOUD_SCORE)
	if sensors.is_scf(entry):  # the SCF also reads the TOA scenes (snow in the shadow) and the SRTM (its hillShadow)
		cols += [sensors.SCF_TOA[c][0] for c in list(cols) if c in sensors.SCF_TOA] + [sensors.SCF['dem']]
	more, credits = of_datasets(cols)
	return ids + more, credits


def _entry(variable, sensor=None, collection=None):
	try:
		return catalog.find(variable, sensor, collection)
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
		if isinstance(c, dict) and c.get('variable'):
			more, cred = of_spec({'index': c['variable'], 'sensor': c.get('sensor'), 'collection': c.get('collection'),
			                      'quality': c.get('quality')}, period)
			ids += more
			credits += [x for x in cred if x not in credits]
	return ids, credits


def _region(region):
	cols = []
	if isinstance(region, dict):
		if 'wdpa_id' in region or 'wdpa_name' in region:
			cols.append(WDPA)
		if 'ecoregion_id' in region or 'ecoregion_at' in region:
			cols.append(ECOREGIONS)
		if 'country' in region:
			cols.append(areas.GAUL_COUNTRIES)
		for level in (1, 2):
			if f'admin{level}' in region:
				cols.append(areas.GAUL[level])
		if 'island_at' in region:
			cols.append(areas.ISLANDS)
	return cols


def _picks(args):
	"""Whether the variable of a true colour chooses the image of each pixel (its metric, or its metric between
	years, max or min: the colours of the image where the variable is highest or lowest), so that its formula is
	cited."""
	from .composite import MOSAICS

	def low(k):
		return str(args.get(k) or '').strip().lower()

	return low('metric') in MOSAICS or ((args.get('temporal') or 'period') != 'period' and low('interannual') in MOSAICS)


def cite(tool, args=None, date=None, datasets=()):
	"""What to cite with the result of the call of TOOL (a function of monitoreo.services or a tool of the MCP server)
	with ARGS: {'references': [{'id', 'citation', 'doi', 'url', 'text'}], 'credits': [lines]}, the references in the
	order of a list of references. DATE (default: today) is that of the computation; DATASETS, other Earth Engine
	datasets that it used."""
	args = dict(args or {})
	period = _period(args)
	ids, credits = [], []
	cols = _region(args.get('region')) + _region(args.get('area')) + list(datasets)
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
		rbr = str(args.get('index') or 'dNBR').upper() == 'RBR'
		more, credits = of_spec({'index': 'RBR' if rbr else 'NBR', 'sensor': args.get('sensor') or 'Sentinel-2',
		                         'quality': args.get('quality')}, period)
		ids += more + _methods('rbr' if rbr else 'burn_severity')
	elif args.get('variable') or args.get('index') or args.get('collection') or args.get('image'):
		ids, credits = of_spec(args, period, formula=tool not in RGB or _picks(args))
	if tool in TRENDS:
		ids += _methods('trends')
	if tool == 'find_protected_areas':
		cols.append(WDPA)
	more, cred = of_datasets(cols)
	ids += more
	credits += cred
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
