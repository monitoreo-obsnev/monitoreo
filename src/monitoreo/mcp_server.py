"""MCP server of MonitorEO (stdio), for language models: the functions of monitoreo.services as tools.

    monitoreo mcp        (or python -m monitoreo.mcp_server, without the update below)

`monitoreo mcp` first installs the last version of the package in GitHub if the installed one is another (see
monitoreo.update), so the server always runs that version; --no-update skips it.

With a project (the variable EE_PROJECT or the tool connect) it computes with the Earth Engine credentials of
`earthengine authenticate` and that project; without one, with the shared account of MonitorEO (no exports to
Google Drive): each user has its research EECUs for each month, only for research. The tool eecu_usage tells the EECUs
of Earth Engine spent this month (with the shared account, the research EECUs of this user; with the user's own, the
monthly quota of their project), and the answers of the tools carry eecu_warning when less than 10 % are left. Files
(CSV tables, PNG charts and maps) are written to the folder MONITOREO_OUTPUT (default:
~/MonitorEO), and the call of each tool that writes files to its log calls.jsonl, where publish_report finds the call
that produced each file it publishes. Works with the MCP Python SDK 1.x (FastMCP) and 2.x (MCPServer).
"""

import datetime as dt
import functools
import inspect
import json
import os
import re
from typing import List, Optional

try:
	from mcp.server.mcpserver import Image, MCPServer as Server  # mcp >= 2
	from mcp.server.mcpserver.exceptions import ToolError
except ImportError:
	from mcp.server.fastmcp import FastMCP as Server, Image  # mcp 1.x
	from mcp.server.fastmcp.exceptions import ToolError

from . import about as about_
from . import assets, publish, services
from . import variable as variables

OUTPUT = os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO')
MAX_ROWS_SHOWN = 300

INSTRUCTIONS = about_.DESCRIPTION['en'] + ' ' + about_.ACKNOWLEDGEMENTS['en'] + ' Cite MonitorEO as: ' + \
	about_.CITATION + """ Mention this funding when the user asks about MonitorEO or its sources, and this citation
when results of MonitorEO go into a report, a paper or a map, or the user asks how to cite it (the tool about gives
both with the logos). MonitorEO computes in Google Earth Engine, so cite it too: """ + about_.EARTH_ENGINE + """.

Every result that writes files has also readme: the path of a README next to them (what each column or band is,
with its unit in UDUNITS, how it was computed, how to reproduce it and how to cite it); give it with the files. Every
result has references and credits: the references (with DOI) of the formula or algorithm of the variable, of
its Earth Engine datasets (as their pages of the Earth Engine catalog suggest), of the pixel filters, of the method
(Mann-Kendall and Sen, burn severity), of the region (WDPA, RESOLVE ecoregions, FAO GAUL, Global Islands), of
Google Earth Engine and of MonitorEO; and the credit lines that the terms of use of the data ask for (Copernicus
Sentinel, USGS Landsat, Copernicus DEM, FAO GAUL). When the results go into a report, a paper or a map, end it with
those references (all of them, as they are) and credits, and cite them in the text where each one is used.

MonitorEO (OBSNEV, Universidad de Granada): satellite variables of Google Earth Engine (NDVI, EVI, NDWI,
LSWI, NDSI, NDCI, NBR, albedo, land surface temperature, evapotranspiration, LAI, chlorophyll, aerosols, snow cover
frequency) of Sentinel-2, Landsat and MODIS, with the pixel filters of MonitorEO (clouds, water, snow, aerosols). The
snow cover frequency (SCF, Landsat) is the % of the clear observations of each pixel with snow: always with metric
"mean" (also in maps) and fixed pixel filters (clouds and water, whatever the quality). The elevation and the slope
(variables ELEVATION and SLOPE, sensor "Copernicus": the Copernicus DEM GLO-30, 30 m; slope in degrees) are fixed layers,
without dates: map_layer, region_stats, download_image and export_image_to_drive without start and end; no time
series, trends or comparisons.
The cloud frequency (CF, of MODIS Terra and Aqua, Sentinel-2 and Landsat) is the % of the observations of each pixel
with clouds: always with metric "mean" and no pixel filters (pass no quality). Climate: precipitation (PRECIP of
ERA5-Land and TerraClimate, monthly; of CHIRPS, daily), air temperature (TMEAN, TMIN, TMAX of ERA5-Land; TMIN, TMAX
of TerraClimate) and water balance of TerraClimate (PET, AET, CWD, SOILM, VPD): the totals of a period (e.g. the
annual precipitation) are the metric "sum" (step "annual" for each year); the 19 bioclimatic variables of WorldClim
(BIO01 to BIO19, climate of 1960-1990) are fixed layers, without dates, like the elevation.

Workflow: list_variables (or describe_variable) to choose variable and sensor; find_protected_areas to get the
WDPA ID of a protected area (designation "ramsar": only Ramsar sites), or find_admin_units the code of an
administrative unit; then time_series (table, CSV and chart), map_layer (map tiles and preview),
region_stats (statistics of a map) or the exports to Google Drive (export_image_to_drive,
export_time_series_to_drive, then task_status). The true colour (red, green and blue surface reflectance) of the same
images and pixels as a map, with the same arguments, shows what is on the ground to interpret the map of an index
(burned areas, bare soil, snow, water, clouds left): rgb_map (tiles and preview) and download_rgb (GeoTIFF), only for
the variables with rgb in list_variables (Sentinel-2, Landsat and the cloud frequency of MODIS) and the metrics
median, mean, min, max and pN. A map whose preview Earth Engine cannot make in some minutes comes without it
(thumbnail_error says why): its tiles are the map, so do not ask for it again. GeoTIFFs on this computer: download_image (one map of a small
region) and download_variables (several variables and metrics on aligned grids over a study area and, at a coarser
pixel size, over its ecoregions: the input variables of a model). Seasonal trends (Mann-Kendall test and Sen's slope
of each month, 16 days or year over the years): trend_table (over regions), trend_map and download_trend (on each
pixel). Comparison of a reference period with another: compare_series, compare_map and download_comparison. Burn
severity of a fire (dNBR with the classes of the USGS, hectares and GeoTIFF; or, with index "RBR", the Relativized
Burn Ratio, a continuous index; or, with index "RdNBR", the relative dNBR of Miller & Thode 2007 with the classes of
the article, also with MODIS): burn_severity. Only for the
administrators of the public viewer of results: publish_report, with the files written by those tools.

Other data of Earth Engine: besides the variables of the catalog, the tools compute any image or collection of images
of Earth Engine given by its ID (of the Earth Engine data catalog, of the GEE Community Catalog or of a project the
account can read), when the user gives an ID or asks for data that the catalog does not have. First describe_asset with
the ID: its type and use say whether to give it as collection (images with dates, aggregated in time like a variable,
with time series, trends and comparisons) or as image (a fixed image, or the mosaic of a collection of tiles: without
dates, so only maps, their statistics and GeoTIFFs, no time series, trends or comparisons); it gives its bands, their
scale, offset and unit, and arguments ready to pass. Then call the tools with collection or image, band (one),
band_scale, band_offset and unit (in UDUNITS) instead of variable and sensor. With terrain, "slope" or "aspect" of the
band of an image (e.g. of a DEM), the values are in degrees (its unit is then degree: give no unit, not that of the
band). To find the datasets of the GEE Community Catalog by its themes: community_themes, then community_datasets (by
theme or text), then describe_asset with the id of one. Never invent an ID: use only those that the user gives or that
describe_asset, community_datasets or the page of a dataset give. The pixel filters of MonitorEO (quality) are not
for these data, which keep their own mask; the conditions of where are still variables of the catalog. Cite the dataset
as describe_asset and the references and credits of the results say.

A region is a JSON object with one of: {"wdpa_id": 389011} (or a list of IDs), {"ecoregion_id": 793},
{"ecoregion_at": [lon, lat]}, {"country": "ESP"} (ISO3), {"admin1": GAUL1_CODE} or {"admin2": GAUL2_CODE}
(administrative units of FAO GAUL 2025, see find_admin_units; or lists of them), {"island_at": [lon, lat]} (the
island at a point), {"bbox": [west, south, east, north]}, {"point": [lon, lat], "buffer": metres},
{"geojson": <GeoJSON geometry, Feature or FeatureCollection>} or {"file": "<path of a vector file>"}. Several
features give one series per feature. Every tool with a region takes where: only the pixels of the region whose
variables pass some conditions, e.g. above 1,500 m and with less than 600 mm of rain a year: [{"variable":
"ELEVATION", "sensor": "Copernicus", "min": 1500}, {"variable": "PRECIP", "sensor": "TerraClimate", "metric": "sum",
"temporal": "annual", "max": 600}]. Each condition is its variable aggregated over the period of the result (or its own
"period": [start, end]; none for the fixed layers), the same mask for every step of a series or a trend and, in the
comparisons, over the reference period. A condition of where can also be a land cover mask, which leaves out the pixels
of some broad land covers (water, trees, grassland, wetland, cropland, shrubland, built, bare, snow) after a land cover
map of a year: {"landcover": "CORINE", "year": 2018, "exclude": ["water", "built"]} (landcover_maps lists the maps,
ESA WorldCover, Dynamic World, CORINE Land Cover and MODIS MCD12Q1, their years and coverage, and the classes of each
map in each land cover); choose the map and year closest to the period of the result, and CORINE only in Europe. Dates are YYYY-MM-DD; season is ["MM-DD", "MM-DD"] (e.g. summer of each year).
Long series over big regions take minutes: use step "monthly" or "annual", or export_time_series_to_drive.
Without a project of the user (EE_PROJECT or connect) the tools compute with the shared account of MonitorEO, which
cannot export to Google Drive: the exports need the user's own Earth Engine account and project. With the shared
account each user has research EECUs for each month (compute of Earth Engine, 25 EECU-hours), only for research; who
has spent them cannot compute with it until the next month, and nor can anyone when the users of the shared account
have spent the monthly quota of its project (1,000 EECU-hours) but the reserve of the app of Earth Engine. eecu_usage tells the percent of them spent (with the
user's own account, of the monthly EECU quota of their project). When an answer has eecu_warning (less than 10 % of
the EECUs of the month are left), tell the user; with the shared account, tell them to switch to their own Earth
Engine account and Google Cloud project (connect).

The texts of the tools are in English. Answer in the language of the user's question (in Spanish when they ask in
Spanish), and pass lang "es" to the tools that take it (about, eecu_usage, list_variables, community_themes) when
the user writes in Spanish. The manual is the wiki of MonitorEO, with every page in English and in Spanish: """ + \
	about_.MANUAL + \
	"""/English (English) and """ + about_.MANUAL + """ (Spanish). Its page Publications (""" + about_.MANUAL + \
	"""/Publications) has articles of the team of MonitorEO with the questions they answered and how to ask MonitorEO for
them: examples for a user who does not know what or how to ask."""

server = Server('MonitorEO', instructions=INSTRUCTIONS)


WHERE_DOC = """
	where: only the pixels of the region whose variables pass these conditions (all of them), each the variable
	aggregated over the period of the result (or its own "period": [start, end]) with metric (default mean), temporal
	and interannual, between min and max, e.g. [{"variable": "ELEVATION", "sensor": "Copernicus", "min": 1500},
	{"variable": "PRECIP", "sensor": "TerraClimate", "metric": "sum", "temporal": "annual", "max": 600}]."""

LANDCOVER_DOC = """ A condition can instead leave out some land covers of a land cover map of a year
	(landcover_maps lists the maps, their years and the land covers), e.g. {"landcover": "CORINE", "year": 2018,
	"exclude": ["water", "built"]}."""

WHERE_DOC += LANDCOVER_DOC

SOURCE_DOC = """
	variable and sensor: a variable of the catalog (list_variables); with them, collection is one of the collections of
	that variable. Instead of variable and sensor, any data of Earth Engine by its ID (describe_asset first: it says
	which to give and its arguments): collection (a collection of images with dates, aggregated in time like a
	variable) or image (a fixed image, or the mosaic of a collection of tiles: without dates, so only maps, their
	statistics and GeoTIFFs, no time series, trends or comparisons), with band (one, required), band_scale and
	band_offset (factor and offset of its stored values) and unit (of the values after them, in UDUNITS: "mm", "degC",
	"kg m-2", "mm day-1", "1" if dimensionless). These data keep their own mask: no pixel filters (quality)."""

TERRAIN_DOC = """
	terrain: "slope" or "aspect" of the band of an image (e.g. of a DEM), in degrees (its unit is then degree: give no
	unit, or "degree", not that of the band)."""


def tool(fn):
	"""Register FN as a tool whose errors reach the client with their message, and whose calls that write files are
	kept in the log of OUTPUT (see _log); the tools of the data of Earth Engine by its ID (band) get their explanation
	(SOURCE_DOC, TERRAIN_DOC) in their description, and those with where, its explanation (WHERE_DOC)."""
	sig = inspect.signature(fn)
	if 'band' in sig.parameters:
		fn.__doc__ = fn.__doc__.rstrip() + SOURCE_DOC + (TERRAIN_DOC if 'terrain' in sig.parameters else '')
	if 'where' in sig.parameters:
		fn.__doc__ = fn.__doc__.rstrip() + WHERE_DOC

	@functools.wraps(fn)
	def wrapped(*args, **kwargs):
		try:
			out = fn(*args, **kwargs)
		except ToolError:
			raise
		except Exception as e:
			raise ToolError(f'{type(e).__name__}: {e}') from e
		_log(fn.__name__, sig, args, kwargs, out)
		return out if fn.__name__ in NO_EECU_WARNING else _eecu_warning(out)
	return server.tool()(wrapped)


NO_EECU_WARNING = ('about', 'connect', 'list_variables', 'describe_variable', 'publish_report', 'eecu_usage',
                   'community_themes', 'community_datasets', 'landcover_maps')


def _eecu_warning(out):
	"""The answer OUT of a tool with the warning of services.eecu_warning (eecu_warning in its JSON object) when less
	than 10 % of the EECUs of the month are left."""
	warning = services.eecu_warning()
	text = out[0] if isinstance(out, list) and out else out
	if not warning or not isinstance(text, str):
		return out
	try:
		res = json.loads(text)
	except ValueError:
		return out
	if not isinstance(res, dict):
		return out
	text = _text({**res, 'eecu_warning': warning})
	return [text] + out[1:] if isinstance(out, list) else text


def _log(name, sig, args, kwargs, out):
	"""Keep the call of a tool whose answer names a GeoTIFF or a CSV (file, csv) in the log of OUTPUT."""
	text = out[0] if isinstance(out, list) and out else out
	try:
		res = json.loads(text) if isinstance(text, str) else None
		if isinstance(res, dict) and any(isinstance(res.get(k), str) for k in ('file', 'csv')):
			call = {k: v for k, v in sig.bind_partial(*args, **kwargs).arguments.items() if v is not None}
			publish.log_call(name, call, {k: v for k, v in res.items() if k != 'rows'}, OUTPUT)
	except Exception:  # the log never breaks a tool
		pass


def _ready():
	if not services.project():
		services.init(warn=False)


def _out(stem, ext):
	os.makedirs(OUTPUT, exist_ok=True)
	stem = re.sub(r'[^A-Za-z0-9_-]+', '_', stem).strip('_')[:80]
	return os.path.join(OUTPUT, f"{stem}_{dt.datetime.now():%Y%m%d-%H%M%S}.{ext}")


def _stem(*parts):
	"""The name of the files of a tool, of PARTS without those left empty (e.g. the dates of a fixed layer)."""
	return '_'.join(str(p) for p in parts if p is not None and p != '')


def _source(variable, sensor, collection=None, image=None, band=None, band_scale=None, band_offset=None, unit=None,
            terrain=None):
	"""The keywords of services for the data of a tool: VARIABLE and SENSOR, a variable of the catalog (COLLECTION, one
	of the collections of that variable), or instead the data of Earth Engine given by its ID (COLLECTION or IMAGE, with
	BAND, BAND_SCALE, BAND_OFFSET, UNIT and TERRAIN; see describe_asset). ValueError, before Earth Engine, if neither
	is given or they are mixed."""
	custom = {k: v for k, v in (('image', image), ('band', band), ('band_scale', band_scale),
	                            ('band_offset', band_offset), ('unit', unit), ('terrain', terrain))
	          if v is not None and v != ''}
	if variable:
		# an ID of Earth Engine given as a variable of the catalog (none has '/'), also with a sensor: small models fill
		# every argument
		if '/' in str(variable):
			raise ValueError(f'{variable} is not a variable of the catalog (list_variables): give an ID of Earth Engine '
			                 'as collection or image (describe_asset says which), with band, instead of variable')
		if not sensor:
			raise ValueError(f'give the sensor of {variable} (list_variables gives those of each variable)')
		if custom:
			raise ValueError(f"{', '.join(custom)}: only for the data of Earth Engine given by its ID (collection or "
			                 f'image instead of variable and sensor); {variable} is a variable of the catalog, with its '
			                 'own band, scale and unit')
		return {'collection': collection}
	if sensor:
		raise ValueError('sensor is for the variables of the catalog (with variable): the data of Earth Engine given by '
		                 'its ID take collection or image, and band')
	if not (collection or image):
		raise ValueError('give variable and sensor (a variable of the catalog: list_variables), or collection or image '
		                 'and band (any data of Earth Engine by its ID: describe_asset says which)')
	if collection and image:
		raise ValueError('give collection (a collection of images with dates) or image (a fixed image), not both')
	if not band:
		raise ValueError(f'give band: the band of {collection or image} (one; describe_asset lists them)')
	if terrain and not image:
		raise ValueError('terrain is for an image (image, e.g. a DEM), not for a collection')
	return dict(custom, **({'collection': collection} if collection else {}))


def _data(variable, sensor, source):
	"""What a tool computes, in the names of its files: the variable and sensor of the catalog ('NDVI_Sentinel-2'), or
	the end of the ID of the data of Earth Engine of SOURCE (see _source) with its band ('TERRACLIMATE_pr',
	'GLO30_DEM_slope')."""
	asset = source.get('collection') or source.get('image')
	if variable or not asset:
		return f'{variable}_{sensor}'
	# as the services read the ID: ee.ImageCollection("X") is X
	return _stem(assets.normalize(asset).rstrip('/').split('/')[-1], source.get('band'), source.get('terrain'))


def _dates(variable, sensor, source, what, **given):
	"""ValueError, before Earth Engine, for a tool of WHAT ('time series', 'trends', 'comparisons of periods'), which
	needs dates: if its data (VARIABLE and SENSOR, or SOURCE: see _source) are a fixed layer or image, without them
	(the message of the services, also when the dates are empty), or naming the dates of GIVEN that the call left
	empty. These tools take their dates after '*', without a default, so that their schema requires them although
	variable and sensor, before them, have one; an empty text still passes the schema."""
	if source.get('image'):
		spec = {'image': assets.normalize(source['image']), 'band': source.get('band')}
	else:
		spec = {'index': variable, 'sensor': sensor, 'collection': source.get('collection')} if variable else None
	try:
		static = spec is not None and variables.is_static(spec)
	except KeyError:  # not in the catalog: the services say so
		static = False
	if static:
		variables.check_dates(spec, what)
	missing = [k for k, v in given.items() if v is None or v == '']
	if missing:
		raise ValueError(f"give {' and '.join(missing)}")


def _text(obj):
	return json.dumps(obj, ensure_ascii=False, indent=1, default=str)


def _preview(res):
	"""The PNG preview of the map RES as an image, if Earth Engine made it (else its reason is in thumbnail_error of
	RES, and the map has its tiles anyway)."""
	if not res.get('thumbnail'):
		return []
	with open(res['thumbnail'], 'rb') as f:
		return [Image(data=f.read(), format='png')]


@tool
def about(lang: str = 'en'):
	"""What MonitorEO-OBSNEV is, who funds it and how to cite it (description, acknowledgements, citation and DOI, and
	the citation of Google Earth Engine, where it computes, in 'en' or 'es'), with the logos of the institutions and
	projects."""
	a = services.about(lang)
	keys = ('name', 'description', 'acknowledgements', 'citation', 'doi', 'earth_engine', 'cite_also', 'manual',
	        'repository')
	return [_text({k: a[k] for k in keys})] + \
	       [Image(path=p) for p in a['logos']]


@tool
def connect(project: str = '') -> str:
	"""Connect to Earth Engine with this Google Cloud project (registered in Earth Engine) and the Google account of
	`earthengine authenticate`, instead of EE_PROJECT; with no project, with the shared account of MonitorEO (which
	cannot export to Google Drive)."""
	project = project.strip()
	p = services.init(project or None, shared=not project, warn=False)
	text = f'Connected to Earth Engine with the shared account of MonitorEO (project {p}): the research EECUs of each ' \
	       'user are only for research' if services.shared() else f'Connected to Earth Engine with the project {p}'
	warning = services.eecu_warning()
	return f'{text}. {warning}' if warning else text


@tool
def eecu_usage(limit: Optional[str] = None, refresh: bool = False, lang: str = 'en') -> str:
	"""EECUs (compute units of Earth Engine) spent this month, against their limit, which restarts on the first day of
	each month: used and left percent, EECU-hours, a bar of text and a warning when less than 10 % are left. With the
	shared account of MonitorEO they are the research EECUs of this user (25 EECU-hours a month, only for research,
	and at most what the project has left for all the users of the shared account; when they are spent, the shared
	account does not compute for them until the next month and they must switch to their own account: connect). With
	the user's own project, the monthly quota of that project (the Cloud Monitoring API must be enabled in it), against
	limit: its EECU-hours a month or tier (Community 150, Contributor 1000, Partner 100000; default
	MONITOREO_EECU_LIMIT or Community). refresh: ask again (answers are kept 5 minutes). lang: en or
	es."""
	return _text(services.eecu_usage(limit, refresh, lang))


@tool
def list_variables(sensor: Optional[str] = None, text: Optional[str] = None, lang: str = 'en',
                   theme: Optional[str] = None) -> str:
	"""Variables of the catalog of MonitorEO: variable, sensor (Sentinel-2, Landsat, Modis, Copernicus, ERA5-Land,
	TerraClimate, CHIRPS, WorldClim), collection, theme, resolution, dates and unit; rgb (true) when its images have a
	true colour (rgb_map, download_rgb). Filter by sensor, by theme (vegetation, water, snow, fire, energy, atmosphere,
	climate, terrain) or by text in the name (English or Spanish). lang: en or es."""
	return _text(services.list_variables(sensor, text, lang, theme=theme))


@tool
def describe_variable(variable: str, sensor: Optional[str] = None, collection: Optional[str] = None) -> str:
	"""Formula, collection, scale, unit, resolution, dates, pixel filters and notes of a variable of the catalog,
	whether its images have a true colour (rgb: see rgb_map), and what to cite with its data: references (the
	articles of its formula or algorithm and its Earth Engine datasets, as their catalog pages suggest, with DOI) and
	credits (lines asked by the terms of use of the data)."""
	if '/' in str(variable):  # an ID of Earth Engine (no variable of the catalog has '/'): not the list of them all
		raise ValueError(f'{variable} is not a variable of the catalog (list_variables): describe_asset describes an ID '
		                 'of Earth Engine')
	return _text(services.describe_variable(variable, sensor, collection))


@tool
def describe_asset(asset: str) -> str:
	"""Everything about an image or a collection of images of Earth Engine given by its ID (the text between the
	quotes of ee.Image('...') or ee.ImageCollection('...') in the page of the dataset, e.g. "IDAHO_EPSCOR/TERRACLIMATE"
	or "projects/sat-io/open-datasets/..."), to compute it with the tools instead of a variable of the catalog: type
	(image or image_collection) and use (the argument that takes it: collection or image) and how, title, source,
	page, provider, licence, dates, cadence, its bands (description, units, unit in UDUNITS, band_scale, band_offset,
	pixel size, classes), arguments (ready to pass to the tools, for its first band), notes, and what to cite with its
	data (references and credits). It reads its metadata in Earth Engine (without computing) and, for the Earth Engine
	data catalog, its STAC record. Use it before computing data given by its ID."""
	_ready()
	return _text(services.describe_asset(asset))


@tool
def community_themes(lang: str = 'en') -> str:
	"""The themes of the GEE Community Catalog (https://gee-community-catalog.org: images and collections of images
	shared by the community of Earth Engine as public assets) and how many datasets each has: theme (its name in the
	catalog, for community_datasets) and name (in lang: en or es). Without Earth Engine."""
	return _text(services.community_themes(lang))


@tool
def landcover_maps(lang: str = 'en') -> str:
	"""The land cover maps of the land cover masks (a condition of where of every tool with a region, which leaves out
	the pixels of some land covers, e.g. water bodies and built-up areas: {"landcover": "CORINE", "year": 2018,
	"exclude": ["water", "built"]}): for each map its key (for landcover), name, resolution_m, coverage, years,
	default_year (without year) and, in classes, its own classes in each broad land cover; and the broad land covers
	(classes: key, for exclude, name in lang, en or es, and what each includes), the rule of the mask and the references
	of the maps and of the table of correspondences. Without Earth Engine."""
	return _text(services.landcover_maps(lang))


@tool
def community_datasets(theme: Optional[str] = None, text: Optional[str] = None, kind: Optional[str] = None,
                       limit: Optional[int] = None) -> str:
	"""The images and collections of images of the GEE Community Catalog: id (the ID of its Earth Engine asset, for
	collection or image), title, type (image or image_collection), theme, provider, license, tags and docs (its page,
	with its bands and how to cite it); of one theme (see community_themes; its name in English or Spanish), with the
	words of text in their title, ID, provider or tags, of one kind (image or image_collection), at most limit (by
	default all of them, as in the other tools: some themes have more than 100). Then describe_asset with the id of
	one. Without Earth Engine."""
	return _text(services.community_datasets(theme, text, kind, limit))


@tool
def find_protected_areas(text: str, limit: int = 10, designation: Optional[str] = None) -> str:
	"""Protected areas of the World Database on Protected Areas (WDPA) whose name contains TEXT, with their WDPA ID
	(SITE_ID), designation, IUCN category, country and area (km2). Use the SITE_ID as {"wdpa_id": ...}. designation
	"ramsar": only the Ramsar sites (Wetlands of International Importance; those that WDPA has only as points are
	not there)."""
	_ready()
	return _text(services.find_protected_areas(text, limit, **({'designation': designation} if designation else {})))


@tool
def find_admin_units(text: str, level: int = 1, country: Optional[str] = None, limit: int = 10) -> str:
	"""Administrative units of FAO GAUL 2025 whose name contains TEXT: level 1 (regions, states, provinces...) or 2
	(provinces, districts, municipalities...), in country (ISO3 code, e.g. "ESP") if given, with their code and full
	name (DISP_EN). Use the code as {"admin1": GAUL1_CODE} or {"admin2": GAUL2_CODE}; a whole country is
	{"country": "ESP"}."""
	_ready()
	return _text(services.find_admin_units(text, level, country, limit))


@tool
def time_series(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str, end: str,
                step: str = 'monthly', metric: str = 'mean', stat: str = 'mean', season: Optional[List[str]] = None,
                quality: Optional[dict] = None, scale: Optional[float] = None, collection: Optional[str] = None,
                image: Optional[str] = None, band: Optional[str] = None, band_scale: Optional[float] = None,
                band_offset: Optional[float] = None, unit: Optional[str] = None, where: Optional[list] = None):
	"""Time series of a variable over a region: one value per step ('daily', '16-day', 'monthly', 'annual') and
	feature of the region, reduced in time with METRIC (mean, median, min, max, pN) and over the region with STAT
	(mean, median, min, max, std, pN), with the number of images and of valid pixels of each value. Writes a CSV
	table and a PNG chart (paths in the answer) and returns the chart. Required: region, start and end, and variable
	and sensor or collection and band. quality: pixel filters, e.g. {"snow": false} or {"cloud_score": null} (SCL
	clouds); scale: pixel size of the statistics in metres."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit)
	_dates(variable, sensor, source, 'time series', start=start, end=end)
	_ready()
	stem = _stem(_data(variable, sensor, source), step, metric, start, end)
	res = services.time_series(region, variable, sensor, start, end, step, metric, stat, season=season,
	                           quality=quality, scale=scale, csv=_out(stem, 'csv'), chart=_out(stem, 'png'),
	                           where=where, **source)
	rows = res['rows']
	summary = {k: res.get(k) for k in ('title', 'unit', 'ylabel', 'scale', 'n_steps', 'regions', 'csv', 'chart', 'readme',
	                                    'references', 'credits')}
	summary['rows'] = rows[:MAX_ROWS_SHOWN]
	if len(rows) > MAX_ROWS_SHOWN:
		summary['note'] = f'{len(rows)} rows: the first {MAX_ROWS_SHOWN} are shown, all of them are in the CSV file'
	out = [_text(summary)]
	if res['chart']:
		with open(res['chart'], 'rb') as f:
			out.append(Image(data=f.read(), format='png'))
	return out


@tool
def map_layer(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, start: Optional[str] = None,
              end: Optional[str] = None, metric: str = 'median',
              temporal: str = 'period', interannual: str = 'mean', season: Optional[List[str]] = None,
              quality: Optional[dict] = None, vmin: Optional[float] = None, vmax: Optional[float] = None,
              collection: Optional[str] = None, image: Optional[str] = None, band: Optional[str] = None,
              band_scale: Optional[float] = None, band_offset: Optional[float] = None, unit: Optional[str] = None,
              terrain: Optional[str] = None, where: Optional[list] = None, quick: bool = False):
	"""Map of a variable over a region aggregated in time (e.g. the median NDVI of a period): returns the URL of
	its Earth Engine map tiles (XYZ, {z}/{x}/{y}, valid for some hours; add it to QGIS as an XYZ layer), the colour
	ramp and a PNG preview with the outline of the region. temporal: 'period' (METRIC over all the images),
	'annual', 'monthly' or '16-day' (METRIC of each, then INTERANNUAL between the years). quick: only the tiles, at
	once (without the preview, and with the colour ramp of the catalog instead of that of the map). Required: region,
	and variable and sensor or collection or image and band; start and end, except for the fixed layers."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit, terrain)
	_ready()
	png = None if quick else _out(_stem('map', _data(variable, sensor, source),
	                                    *(() if image else (metric, start, end))), 'png')
	res = services.map_layer(region, variable, sensor, start, end, metric, temporal, interannual, season, quality,
	                         vmin, vmax, thumbnail=png, quick=quick, where=where, **source)
	return [_text(res)] + _preview(res)


@tool
def rgb_map(region: dict, variable: str, sensor: str, start: str, end: str, metric: str = 'median',
            temporal: str = 'period', interannual: str = 'mean', season: Optional[List[str]] = None,
            quality: Optional[dict] = None, vmin: Optional[float] = None, vmax: Optional[float] = None,
            collection: Optional[str] = None,
            where: Optional[list] = None, quick: bool = False, preview: bool = True):
	"""True colour of the images of a variable over a region: the red, green and blue surface reflectance of the
	same images and pixels as its map (map_layer with the same arguments: period, season, pixel filters, where),
	aggregated in time with the same metric (median, mean and pN band by band; max and min, the colours of the image
	where the variable is highest or lowest on each pixel; not sum, std, count nor mode). Use it with the map of an
	index to see what is on the ground: burned areas, bare soil, snow, water or clouds left by the filters. Only the
	variables with rgb in list_variables (those of Sentinel-2 and Landsat, and the cloud frequency of MODIS); not the
	fixed layers, the climate nor the other MODIS products. Returns the URL of its Earth Engine map tiles (XYZ,
	{z}/{x}/{y}, valid for some hours), the bands red, green and blue stretched together from min to max
	(reflectance: the lowest percentile 2 and the highest percentile 98 of the bands over the region, or vmin and
	vmax) and a PNG preview with the outline of the region. quick: only the tiles, at once (without the preview, and
	from 0 to 0.3 instead of the range of the map); preview false: the tiles and their range, without the preview."""
	_ready()
	png = None if quick or not preview else _out(f'rgb_{variable}_{sensor}_{metric}_{start}_{end}', 'png')
	res = services.rgb_map(region, variable, sensor, start, end, metric, temporal, interannual, season, quality,
	                       vmin, vmax, thumbnail=png, quick=quick, collection=collection, where=where)
	return [_text(res)] + _preview(res)


@tool
def region_stats(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None,
                 start: Optional[str] = None, end: Optional[str] = None, metric: str = 'median',
                 temporal: str = 'period', season: Optional[List[str]] = None, quality: Optional[dict] = None,
                 scale: Optional[float] = None, collection: Optional[str] = None, image: Optional[str] = None,
                 band: Optional[str] = None, band_scale: Optional[float] = None, band_offset: Optional[float] = None,
                 unit: Optional[str] = None, terrain: Optional[str] = None, where: Optional[list] = None) -> str:
	"""Statistics (mean, std, min, p5, p50, p95, max, number of pixels) over each feature of a region of the map of
	a variable aggregated in time. Required: region, and variable and sensor or collection or image and band; start
	and end, except for the fixed layers."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit, terrain)
	_ready()
	return _text(services.region_stats(region, variable, sensor, start, end, metric, temporal, season=season,
	                                   quality=quality, scale=scale, where=where, **source))


@tool
def export_image_to_drive(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None,
                          start: Optional[str] = None, end: Optional[str] = None, metric: str = 'median',
                          temporal: str = 'period', season: Optional[List[str]] = None,
                          quality: Optional[dict] = None, resolution: Optional[float] = None, crs: str = 'auto',
                          folder: str = 'MonitorEO', name: Optional[str] = None,
                          collection: Optional[str] = None, image: Optional[str] = None, band: Optional[str] = None,
                          band_scale: Optional[float] = None, band_offset: Optional[float] = None,
                          unit: Optional[str] = None, terrain: Optional[str] = None,
                          where: Optional[list] = None) -> str:
	"""Export the map of a variable over a region to a GeoTIFF in a folder of the Google Drive of the Earth Engine
	account (a batch task, without limits of size; it needs the user's own account, not the shared one). resolution:
	pixel size in metres (default: that of the data); crs: 'auto' (UTM zone of the region) or e.g. 'EPSG:25830'.
	Check it with task_status. Required: region, and variable and sensor or collection or image and band; start and
	end, except for the fixed layers."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit, terrain)
	_ready()
	return _text(services.export_image(region, variable, sensor, start, end, metric, temporal, season=season,
	                                   quality=quality, resolution=resolution, crs=crs, folder=folder, name=name,
	                                   where=where, **source))


@tool
def export_time_series_to_drive(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *,
                                start: str, end: str, step: str = 'monthly', metric: str = 'mean', stat: str = 'mean',
                                season: Optional[List[str]] = None, quality: Optional[dict] = None,
                                scale: Optional[float] = None, folder: str = 'MonitorEO',
                                name: Optional[str] = None, collection: Optional[str] = None,
                                image: Optional[str] = None, band: Optional[str] = None,
                                band_scale: Optional[float] = None, band_offset: Optional[float] = None,
                                unit: Optional[str] = None, where: Optional[list] = None) -> str:
	"""Export a time series (as time_series) to a CSV file in a folder of Google Drive: for long series or many
	regions (it needs the user's own Earth Engine account, not the shared one). Check it with task_status. Required:
	region, start and end, and variable and sensor or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit)
	_dates(variable, sensor, source, 'time series', start=start, end=end)
	_ready()
	return _text(services.time_series_to_drive(region, variable, sensor, start, end, step, metric, stat, season,
	                                           quality, scale, folder, name, where=where, **source))


@tool
def download_image(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None,
                   start: Optional[str] = None, end: Optional[str] = None, metric: str = 'median',
                   temporal: str = 'period', interannual: str = 'mean', season: Optional[List[str]] = None,
                   quality: Optional[dict] = None, resolution: Optional[float] = None, crs: str = 'auto',
                   clip: bool = True, collection: Optional[str] = None, image: Optional[str] = None,
                   band: Optional[str] = None, band_scale: Optional[float] = None, band_offset: Optional[float] = None,
                   unit: Optional[str] = None, terrain: Optional[str] = None, where: Optional[list] = None) -> str:
	"""Download the map of a variable over a region to a GeoTIFF on this computer (float32, NoData -9999), computed
	by Earth Engine in tiles: for small regions (up to some million pixels); bigger ones, export_image_to_drive.
	resolution: pixel size in metres (default: that of the data); crs: 'auto' (UTM zone of the region) or e.g.
	'EPSG:25830'. Returns the path of the file and its grid. Required: region, and variable and sensor or collection
	or image and band; start and end, except for the fixed layers."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit, terrain)
	_ready()
	stem = _stem(_data(variable, sensor, source), *(() if image else (metric, start, end)))
	return _text(services.download_image(region, variable, sensor, start, end, metric, temporal, interannual,
	                                     season=season,
	                                     quality=quality, resolution=resolution, crs=crs, clip=clip,
	                                     path=_out(stem, 'tif'), where=where, **source))


@tool
def download_rgb(region: dict, variable: str, sensor: str, start: str, end: str, metric: str = 'median',
                 temporal: str = 'period', interannual: str = 'mean', season: Optional[List[str]] = None,
                 quality: Optional[dict] = None, resolution: Optional[float] = None, crs: str = 'auto',
                 clip: bool = True, collection: Optional[str] = None,
                 where: Optional[list] = None) -> str:
	"""Download the true colour of the images of a variable over a region (see rgb_map: the red, green and blue
	surface reflectance of the same images and pixels as its map, with the same metric) to a GeoTIFF on this
	computer with the bands red, green and blue (float32 reflectance, NoData -9999), on the same grid as
	download_image with the same arguments (resolution, crs): to compare the values of an index with what is on the
	ground. For small regions. Returns the path of the file, its grid and min and max, the range of reflectance to
	show the three bands together (the lowest percentile 2 and the highest percentile 98 of the bands)."""
	_ready()
	return _text(services.download_rgb(region, variable, sensor, start, end, metric, temporal, interannual,
	                                   season=season, quality=quality, resolution=resolution, crs=crs, clip=clip,
	                                   path=_out(f'{variable}_{sensor}_{metric}_{start}_{end}_RGB', 'tif'),
	                                   collection=collection, where=where))


@tool
def download_variables(recipe: dict, area: dict, name: str, dry_run: bool = False, overwrite: bool = False) -> str:
	"""Download several variables as GeoTIFFs on aligned grids over a study area and, if the recipe has ecoregion,
	over the ecoregions of RESOLVE 2017 that it touches (their union), each grid with its own pixel size: the input
	variables of a model (e.g. eHabitat+). The files go to the folder NAME of the output folder (the ecoregions to its
	subfolder ecoregion), numbered in the order of the recipe. area: a region (as in the other tools). recipe:
	{"study": {"resolution": 10, "buffer": 0}, "ecoregion": {"resolution": 100, "drive": true},
	"period": ["2018-01-01", "2021-12-31"], "variables": [{"index": "NDVI", "sensor": "Sentinel-2",
	"metric": ["p95", "p5"]}, {"index": "LSWI", "sensor": "Sentinel-2", "metric": "median"}, {"name": "slope",
	"image": "COPERNICUS/DEM/GLO30_2024_1", "band": "DEM", "terrain": "slope"}]}; optional: crs, season, quality,
	where (the pixels kept, as in the other tools), temporal (period, annual, monthly) and interannual, collection
	and band (other collections), drive_folder.
	Grids with "drive": true are exported to Google Drive (no size limits): the tasks keep running and calling this
	tool again with the same arguments imports the finished ones (also from Google Drive for desktop). Use dry_run
	first: it gives the grids, their size and the number of images, without downloading."""
	_ready()
	folder = os.path.join(OUTPUT, re.sub(r'[^A-Za-z0-9_-]+', '_', name).strip('_') or 'variables')
	log = []
	res = services.download_variables(recipe, area, folder, dry_run=dry_run, overwrite=overwrite, wait=False,
	                                  log=log.append)
	if log:
		res['log'] = '\n'.join(log).strip()
	return _text(res)


@tool
def trend_table(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str, end: str,
                step: str = 'annual', metric: str = 'mean', stat: str = 'mean', season: Optional[List[str]] = None,
                quality: Optional[dict] = None, scale: Optional[float] = None, alpha: float = 0.05,
                collection: Optional[str] = None, image: Optional[str] = None, band: Optional[str] = None,
                band_scale: Optional[float] = None, band_offset: Optional[float] = None, unit: Optional[str] = None,
                where: Optional[list] = None):
	"""Seasonal trends of a variable over each feature of a region:
	for each part of the year (step 'monthly': each month; '16-day': 23 parts of 16 days from 1 January; 'annual':
	the year), the spatial STAT of the METRIC of its images in each year, and the trend of those yearly values:
	Mann-Kendall tau, Z and p-value (significant if p < alpha) and Sen's slope (change per year). Use 8 or more
	years. Writes a CSV and a chart of the yearly values with their Sen lines, and returns the chart. Required:
	region, start and end, and variable and sensor or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit)
	_dates(variable, sensor, source, 'trends', start=start, end=end)
	_ready()
	stem = _stem('trend', _data(variable, sensor, source), step, start, end)
	res = services.trend_table(region, variable, sensor, start, end, step, metric, stat, season=season,
	                           quality=quality, scale=scale, alpha=alpha, csv=_out(stem, 'csv'),
	                           chart=_out(stem, 'png'), where=where, **source)
	summary = {k: res.get(k) for k in ('title', 'unit', 'ylabel', 'scale', 'csv', 'chart')}
	summary['slope_unit'] = f"{res['unit']} / year" if res.get('unit') else 'per year'  # data without a unit
	summary['trends'] = res['rows']
	summary.update({k: res.get(k) for k in ('readme', 'references', 'credits')})
	out = [_text(summary)]
	if res.get('chart'):
		out.append(Image(path=res['chart']))
	return out


@tool
def trend_map(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str, end: str,
              step: str = 'annual', part: Optional[int] = None, output: str = 'slope', metric: str = 'mean',
              season: Optional[List[str]] = None, quality: Optional[dict] = None, alpha: Optional[float] = None,
              collection: Optional[str] = None, image: Optional[str] = None, band: Optional[str] = None,
              band_scale: Optional[float] = None, band_offset: Optional[float] = None, unit: Optional[str] = None,
              where: Optional[list] = None, vmin: Optional[float] = None, vmax: Optional[float] = None,
              quick: bool = False):
	"""Map of the trend of a part of the year computed on each pixel (see trend_table): part is the month (1-12)
	with step 'monthly', 1-23 with '16-day', nothing with 'annual'; output 'slope' (Sen, per year), 'tau', 'z',
	'p_value', 'intercept' or 'n' (years with data); alpha (e.g. 0.05) keeps only the significant pixels. Returns
	the URL of its Earth Engine tiles (XYZ, valid for some hours) and a preview. quick: only the tiles, at once
	(without the preview, and with a fixed colour ramp instead of that of the map). Required: region, start and end,
	and variable and sensor or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit)
	_dates(variable, sensor, source, 'trends', start=start, end=end)
	_ready()
	thumb = None if quick else _out(_stem('trend', _data(variable, sensor, source), step, part, output), 'png')
	res = services.trend_map(region, variable, sensor, start, end, step, part, output, metric, season=season,
	                         quality=quality, alpha=alpha, vmin=vmin, vmax=vmax, thumbnail=thumb, quick=quick,
	                         where=where, **source)
	return [_text(res)] + _preview(res)


@tool
def download_trend(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str,
                   end: str, step: str = 'annual', part: Optional[int] = None, metric: str = 'mean',
                   season: Optional[List[str]] = None, quality: Optional[dict] = None, alpha: Optional[float] = None,
                   resolution: Optional[float] = None, crs: str = 'auto', collection: Optional[str] = None,
                   image: Optional[str] = None, band: Optional[str] = None, band_scale: Optional[float] = None,
                   band_offset: Optional[float] = None, unit: Optional[str] = None,
                   where: Optional[list] = None) -> str:
	"""Download the trend of a part of the year on each pixel (see trend_map) to a GeoTIFF on this computer with
	the bands slope, tau, z, p_value, intercept and n. For small regions (Earth Engine computes it in tiles).
	Required: region, start and end, and variable and sensor or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit)
	_dates(variable, sensor, source, 'trends', start=start, end=end)
	_ready()
	stem = _stem('trend', _data(variable, sensor, source), step, part, start, end)
	return _text(services.download_trend(region, variable, sensor, start, end, step, part, metric, season=season,
	                                     quality=quality, alpha=alpha, resolution=resolution, crs=crs,
	                                     path=_out(stem, 'tif'), where=where, **source))


@tool
def compare_series(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str,
                   end: str, other_start: str, other_end: str, step: str = 'monthly', metric: str = 'mean',
                   stat: str = 'mean', season: Optional[List[str]] = None, quality: Optional[dict] = None,
                   scale: Optional[float] = None, collection: Optional[str] = None, image: Optional[str] = None,
                   band: Optional[str] = None, band_scale: Optional[float] = None, band_offset: Optional[float] = None,
                   unit: Optional[str] = None, where: Optional[list] = None):
	"""Compare a reference period (start to end) with another (other_start to other_end) over each feature of a
	region: the mean of each part of the year (step 'monthly', '16-day' or 'annual') over the years of each period
	and the difference (other - reference). Writes a CSV and a chart of both
	periods by part of the year, and returns the chart. Required: region, start, end, other_start and other_end, and
	variable and sensor or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit)
	_dates(variable, sensor, source, 'comparisons of periods', start=start, end=end, other_start=other_start,
	       other_end=other_end)
	_ready()
	stem = _stem('comparison', _data(variable, sensor, source), start, end, other_start, other_end)
	res = services.compare_series(region, variable, sensor, start, end, other_start, other_end, step, metric, stat,
	                              season=season, quality=quality, scale=scale, csv=_out(stem, 'csv'),
	                              chart=_out(stem, 'png'), where=where, **source)
	summary = {k: res.get(k) for k in ('title', 'unit', 'ylabel', 'scale', 'csv', 'chart')}
	summary['comparison'] = res['profile']
	summary.update({k: res.get(k) for k in ('readme', 'references', 'credits')})
	out = [_text(summary)]
	if res.get('chart'):
		out.append(Image(path=res['chart']))
	return out


@tool
def compare_map(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str, end: str,
                other_start: str, other_end: str, metric: str = 'median', temporal: str = 'period',
                season: Optional[List[str]] = None, quality: Optional[dict] = None, collection: Optional[str] = None,
                image: Optional[str] = None, band: Optional[str] = None, band_scale: Optional[float] = None,
                band_offset: Optional[float] = None, unit: Optional[str] = None, where: Optional[list] = None):
	"""Map of the difference between the variable aggregated over another period (other_start to other_end) and
	over the reference period (start to end), e.g. the median NDVI of 2023 minus that of 2018-2021. Returns the URL
	of its Earth Engine tiles (XYZ, valid for some hours) and a preview. Required: region, start, end, other_start
	and other_end, and variable and sensor or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit)
	_dates(variable, sensor, source, 'comparisons of periods', start=start, end=end, other_start=other_start,
	       other_end=other_end)
	_ready()
	thumb = _out(_stem('comparison', _data(variable, sensor, source), metric), 'png')
	res = services.compare_map(region, variable, sensor, start, end, other_start, other_end, metric, temporal,
	                           season=season, quality=quality, thumbnail=thumb, where=where, **source)
	return [_text(res)] + _preview(res)


@tool
def download_comparison(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str,
                        end: str, other_start: str, other_end: str, metric: str = 'median', temporal: str = 'period',
                        season: Optional[List[str]] = None, quality: Optional[dict] = None,
                        resolution: Optional[float] = None, crs: str = 'auto',
                        collection: Optional[str] = None, image: Optional[str] = None, band: Optional[str] = None,
                        band_scale: Optional[float] = None, band_offset: Optional[float] = None,
                        unit: Optional[str] = None, where: Optional[list] = None) -> str:
	"""Download the comparison of two periods (see compare_map) to a GeoTIFF on this computer with the bands
	difference (other - reference), reference and other. For small regions. Required: region, start, end,
	other_start and other_end, and variable and sensor or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit)
	_dates(variable, sensor, source, 'comparisons of periods', start=start, end=end, other_start=other_start,
	       other_end=other_end)
	_ready()
	stem = _stem('comparison', _data(variable, sensor, source), metric, start, end, other_start, other_end)
	return _text(services.download_comparison(
		region, variable, sensor, start, end, other_start, other_end, metric, temporal, season=season,
		quality=quality, resolution=resolution, crs=crs, path=_out(stem, 'tif'), where=where, **source))


@tool
def burn_severity(region: dict, start: str, end: str, other_start: str, other_end: str, sensor: str = 'Sentinel-2',
                  metric: str = 'median', season: Optional[List[str]] = None, quality: Optional[dict] = None,
                  resolution: Optional[float] = None, crs: str = 'auto', index: str = 'dNBR',
                  where: Optional[list] = None, collection: Optional[str] = None) -> str:
	"""Burn severity of a fire with the dNBR and the official classes of the USGS (Key & Benson 2006): dNBR = NBR of
	a period before the fire (start to end) minus NBR of a period after it (other_start to other_end), with
	Sentinel-2 (10 m, since 2017) or Landsat (30 m, since 1984). Returns the hectares of each class over each feature
	of the region (unburned, low, moderate-low, moderate-high and high severity, and enhanced regrowth) and the burned
	area (dNBR >= 0.1), writes them to a CSV and downloads a GeoTIFF with the bands dnbr, severity (class -2 to 4),
	nbr_before and nbr_after. Use periods without the fire: e.g. the 3 months before it and the 2-3 months after it
	ends. For small regions (bigger ones: lower resolution). index "RBR" (only when the user asks for it): the
	Relativized Burn Ratio, dNBR / (NBR before + 1.001), with the NBR of B8A and B12 of Sentinel-2 (20 m; Landsat:
	NIR and SWIR2), without phenological correction and on the scale of the dNBR (articles multiply it by 1000): a
	continuous index without classes; returns its mean, median, p10, p90, min and max and the hectares with values
	over each feature, and a GeoTIFF with the bands rbr, dnbr, nbr_before and nbr_after.
	index "RdNBR" (when the user asks for it or for the classes of Miller & Thode, for a fire over heterogeneous
	vegetation, e.g. shrubs and forest, or to compare fires): the relative dNBR of Miller & Thode 2007, dNBR /
	sqrt(|NBR before|) with |NBR before| at least 0.001 (Howe et al. 2022), the change relative to the vegetation
	before the fire, with the classes of the article (unchanged < 0.069, low 0.069 to 0.316, moderate 0.316 to 0.641,
	high >= 0.641), on the scale of the dNBR, without the factor 1000 of the article (0.641 here is 641 there) and
	without its offset (the dNBR of an unburned area outside the fire). Sensors: Sentinel-2 (B8 and B12, 10 m),
	Landsat (30 m) or "Modis" (500 m, only with this index: the daily surface reflectance of Terra, since 2000, or of
	Aqua, since 2002-07-04, with collection "MODIS/061/MYD09GA"; its classes are approximate, as a pixel of 500 m
	mixes burned and unburned land, and small fires are missed). Its classes were calibrated with Landsat TM (30 m)
	and field plots of 14 fires of the Sierra Nevada of California, mostly in conifer and live oak forests (also
	pinyon pine and sagebrush), with field data one year after the fire: give a period after about
	one year after the fire, in the season of the period before. Returns the hectares of each class (classes),
	the changed area (burned_ha, RdNBR >= 0.069; unchanged is not unburned) and the mean, median, p10, p90, min and max
	of the RdNBR (stats) over each feature, a CSV of the classes and a GeoTIFF with the bands rdnbr, severity (class 0
	to 3), dnbr, nbr_before and nbr_after. collection: only for index "RdNBR" with sensor "Modis"."""
	_ready()
	name = {i.lower(): i for i in services.BURN_INDICES}.get(str(index or 'dNBR').lower())
	prefix = f'{name}_' if name and name != 'dNBR' else ''  # burn_severity_RBR_..., burn_severity_RdNBR_...
	stem = f"burn_severity_{prefix}{sensor}_{start}_{end}_{other_start}_{other_end}"
	return _text(services.burn_severity(region, sensor, start, end, other_start, other_end, metric, season=season,
	                                    quality=quality, resolution=resolution, crs=crs, path=_out(stem, 'tif'),
	                                    csv=_out(stem, 'csv'), index=index, where=where, collection=collection))


@tool
def publish_report(title: str, summary: str, files: List[str], question: Optional[str] = None,
                   answer: Optional[str] = None, method: Optional[str] = None, region: Optional[dict] = None,
                   authors: Optional[List[str]] = None, downloads: Optional[List[str]] = None,
                   report_id: Optional[str] = None, site: Optional[str] = None) -> str:
	"""For the administrators of the viewer of results of MonitorEO: publish an analysis as a report of the static
	web site in the folder site (default: MONITOREO_SITE or ~/MonitorEO/visor). files: the GeoTIFF and CSV files
	written by the other tools (download_trend, download_comparison, download_image, burn_severity, time_series,
	trend_table, compare_series; not yet the true colour of download_rgb) in the order of the page; their calls are
	read from the log of this server. Texts in Spanish, the language of the viewer: title (e.g. the question of the
	analysis), summary (the answer in one or two sentences), question, answer (the result; paragraphs separated by a
	blank line), method; region: {"name": ..., "wdpa_id": ...}; downloads: other files (PDF, figures). The GeoTIFFs
	become Cloud Optimized GeoTIFFs and the site gets the report, the viewer and its catalogue. It is public only when
	an administrator deploys the folder (git push to the repository of the site, or rsync to its server); `monitoreo
	serve` shows it on this computer."""
	spec = {'title': title, 'summary': summary, 'question': question, 'answer': answer, 'method': method,
	        'region': region, 'authors': authors, 'downloads': downloads, 'results': list(files)}
	if report_id:
		spec['id'] = report_id
	res = services.publish_report({k: v for k, v in spec.items() if v is not None}, site, OUTPUT,
	                              publish.calls_log(OUTPUT))
	res['next'] = (f"see it with `monitoreo serve {res['site']}`, then deploy the folder (git push or rsync) to make "
	               'it public')
	return _text(res)


@tool
def task_status(operation: str) -> str:
	"""State of an export task (PENDING, RUNNING, SUCCEEDED, FAILED, CANCELLED) and its progress, given the operation
	returned by the export tools."""
	_ready()
	return _text(services.task_status(operation))


def main():
	server.run()


if __name__ == '__main__':
	main()
