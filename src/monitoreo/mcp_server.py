"""MCP server of MonitorEO (stdio), for language models: the functions of monitoreo.services as tools.

    monitoreo mcp        (or python -m monitoreo.mcp_server, without the update below)

`monitoreo mcp` first installs the last version of the package in GitHub if the installed one is another (see
monitoreo.update), so the server always runs that version; --no-update skips it.

With a project (the variable EE_PROJECT or the tool connect) it computes with the Earth Engine credentials of
`earthengine authenticate` and that project; without one, with the shared account of MonitorEO (no exports to
Google Drive): each user has its research EECUs for each month, only for research. The tool own_projects lists the
Google Cloud projects of the user's account registered in Earth Engine, to connect with one. The answers of the tools
carry quota_warning when Earth Engine has put the project in restricted mode (it has spent its noncommercial compute quota:
computations are slow and may fail with too many requests; see services.quota_warning), which their errors say too.
Files (CSV tables, PNG charts and maps) are written to the folder MONITOREO_OUTPUT (default:
~/MonitorEO), and the call of each tool that writes files to its log calls.jsonl, where publish_report finds the call
that produced each file it publishes. If it crashes (a fatal error: an access violation, a stack overflow, an abort),
the Python traceback of each of its threads goes to its stderr (faulthandler). Works with the MCP Python SDK 1.x
(FastMCP) and 2.x (MCPServer).
"""

import datetime as dt
import faulthandler
import functools
import inspect
import json
import os
import re
import sys
from typing import List, Optional, Union

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
(Mann-Kendall and Sen, burn severity), of the region (WDPA, RESOLVE ecoregions and biomes, FAO GAUL, Global Islands), of
Google Earth Engine and of MonitorEO; and the credit lines that the terms of use of the data ask for (Copernicus
Sentinel, USGS Landsat, Copernicus DEM, MERIT Hydro, FAO GAUL, RESOLVE). When the results go into a report, a paper or a
map, end it with those references (all of them, as they are) and credits, and cite them in the text where each one is used.
Every result about variables has manual: the sections of the manual of MonitorEO (its wiki) that explain each variable,
with their links in English (url) and Spanish (url_es); give the link of each variable next to its results, so that the
user can read what it is and how it is computed.

The results say which data their values come from, data_source (the Earth Engine collections and their product level,
e.g. COPERNICUS/S2_SR_HARMONIZED, Harmonized Sentinel-2 MSI, Level-2A (SR): surface reflectance), and their charts in
a line «Data: ...»: say it with the result. A period that ends before the first image of the data, falls between
Landsat 5 and Landsat 8 or begins after today is an error that says their dates; a period that begins before the first
image (e.g. Sentinel-2 SR from 2017-03-28), or ends (or even begins) after the last one of data that ended in the copy
of the Earth Engine data catalog (Earth Engine may have added images since), has warnings in the result (warnings):
always tell the user, as those days may have no data (describe_variable gives the dates of the data, data_dates). A
warning that begins with «where, the condition on ...» is about the variable of that condition, not the result.

MonitorEO (OBSNEV, Universidad de Granada): satellite variables of Google Earth Engine (NDVI, EVI, NDWI,
LSWI, NDSI, NDCI, CLre, CLreB7, WAVI, NBR, albedo, land surface temperature, evapotranspiration, LAI, chlorophyll, aerosols, snow cover
frequency, snow cover days, snow melt-out day) of Sentinel-2, Landsat and MODIS, with the pixel filters of MonitorEO (clouds, water, snow,
aerosols). The snow cover frequency (SCF, Sentinel-2, Landsat and MODIS) is the % of the clear observations of each
pixel with snow: always with metric "mean" (also in maps) and fixed pixel filters (clouds and water, whatever the
quality). The snow cover days (SCD, Sentinel-2, Landsat and MODIS) are the days with snow of each pixel, from the same
images (the SCF of each month times its days, summed): always with metric "days", the same fixed filters; their
time_series chart has a bar per step (with step "daily", a bar per day with images: the share of its clear pixels with
snow, 0 to 1 day); with temporal "period", the mean
days of each season (or of each 12 months without a season). An estimate: better with more images (n_images). The
snow melt-out day (SMOD, Sentinel-2, Landsat and MODIS) is the day of the year (1 = 1 January) of the first clear image
without snow after the last one with snow, in each season of each year (by default 1 January to 31 August; a season
must end before the snowfalls of autumn), from the same images: always with metric "melt", the same fixed filters and
shadows of the relief; one per year: time_series and trends with step "annual" (Sen's slope in days per year, negative
is earlier), maps with temporal "period" (the mean day of the years) or "annual"; no monthly, 16-day or daily steps. A
pixel without snow in the season takes the day of its first clear image; one whose snow does not go has no data. The elevation and the slope
(variables ELEVATION and SLOPE, sensor "Copernicus": the Copernicus DEM GLO-30, 30 m; slope in degrees) are fixed layers,
without dates: map_layer, region_stats, download_image and export_image_to_drive without start and end; no time
series, trends or comparisons. The topographic wetness index (variable TWI, sensor "MERIT Hydro": ln(a / tan β) of
MERIT Hydro, 90 m, unitless; high in the valley bottoms and flats where the water converges, low on the ridges and
steep slopes; most land between 5 and 15, rivers and lakes the highest) is a fixed layer too, like the elevation; it
also works in where (e.g. only the wet bottoms: {"variable": "TWI", "sensor": "MERIT Hydro", "min": 10}) and in the
zones of region_stats.
The cloud frequency (CF, of MODIS Terra and Aqua, Sentinel-2 and Landsat) is the % of the observations of each pixel
with clouds: always with metric "mean" and no pixel filters (pass no quality).
Topographic correction: quality {"topographic": true} corrects the surface reflectance of Landsat for the relief
before the formula (SCS+C, Soenen et al. 2005, with the slope and aspect of the SRTM and the sun of each scene): slopes
facing the sun look brighter, and those facing away darker, than the same cover on flat ground. Off by default; use it
in mountains (slopes of more than 5 degrees), above all to compare slopes of different aspect or dates with a low sun
(winter), not on flat land, for water (NDWI) or snow. Not for Sentinel-2 (its Level-2A, Sen2Cor, is already
corrected), LST, SCF, SCD, SMOD, CF, MODIS or the climate (an error says so). It costs more in Earth Engine.
Snow by its NDSI: quality {"snow_ndsi": 0.4}, with the snow filter on, also removes from each image of Sentinel-2 and
Landsat the pixels whose NDSI (green, SWIR1; Hall et al. 1995) is 0.4 or more: the patches and edges of snow that the QA
band (SCL, QA_PIXEL) misses, which raise the standard deviation or the minimum of a moisture index (NDMI, LSWI) in
mountains. Off by default; not for the NDSI, SCF, SCD and SMOD (snow), MODIS or the data by their ID (an error says so), and
not applied to the variables that measure water (NDWI, Chl-a, NDCI, WAVI: open water has a high NDSI too).
Metrics (of the images of each pixel,
metric; between the years, interannual) and statistics (over the region: stat of the series, trends and comparisons,
stats of region_stats), for any variable: mean, median, min, max, std (standard deviation), cv (coefficient of
variation: 100 * std / mean, in %; meaningful for variables with a true zero and positive values, not with a mean
near 0, e.g. a temperature in °C), and pN (percentile N, e.g. p90); the metrics also sum, count and mode. E.g. the
year-to-year variability of the annual precipitation: temporal "annual", metric "sum", interannual "cv". Climate: precipitation (PRECIP of
ERA5-Land and TerraClimate, monthly; of CHIRPS, daily), air temperature (TMEAN, TMIN, TMAX of ERA5-Land; TMIN, TMAX
of TerraClimate) and water balance of TerraClimate (PET, AET, CWD, SOILM, VPD): the totals of a period (e.g. the
annual precipitation) are the metric "sum" (step "annual" for each year); the 19 bioclimatic variables of WorldClim
(BIO01 to BIO19, climate of 1960-1990) are fixed layers, without dates, like the elevation.
Ecosystems: the ecoregions and biomes of RESOLVE Ecoregions 2017 (variables ECOREGION and BIOME, sensor "RESOLVE":
846 ecoregions and Rock and Ice in 14 biomes, Rock and Ice being the biome 99 of MonitorEO; nominal pixel of 1 km) are
categorical fixed layers, without dates: their values are class codes (the ECO_ID of each ecoregion, the BIOME_NUM of
each biome), not quantities. Their maps (map_layer, download_image) have the colour of each class and the legend of the
classes in the region (classes); their statistic over a region is the majority class (region_stats: stats "mode",
with mode_label); the hectares and % of each class: area_by_class with variable and sensor, without breaks nor trend
(the ecoregions with their biome, and by_group, the hectares of each biome); zones by class: region_stats with zones
{"variable": "BIOME", "sensor": "RESOLVE"} (no breaks); only some classes of a region: a condition of where with
classes (the codes to keep) or exclude (those to leave out), e.g. {"variable": "BIOME", "sensor": "RESOLVE", "classes":
[12]}. list_classes gives their codes and names (find an ecoregion by name with text). No transect, time series, trends
or comparisons.

Workflow: list_variables (or describe_variable) to choose variable and sensor; find_protected_areas to get the
WDPA ID of a protected area (designation "ramsar": only Ramsar sites), find_admin_units the code of an
administrative unit, or find_seas the MRGID of an ocean or sea; then time_series (table, CSV and chart), map_layer (map tiles and preview),
region_stats (statistics of a map) or the exports to Google Drive (export_image_to_drive,
export_time_series_to_drive, then task_status). The true colour (red, green and blue surface reflectance) of the same
images and pixels as a map, with the same arguments, shows what is on the ground to interpret the map of an index
(burned areas, bare soil, snow, water, clouds left): rgb_map (tiles and preview) and download_rgb (GeoTIFF), only for
the variables with rgb in list_variables (Sentinel-2, Landsat and the cloud frequency of MODIS) and the metrics
median, mean, min, max and pN. A map whose preview Earth Engine cannot make in some minutes comes without it
(thumbnail_error says why): its tiles are the map, so do not ask for it again. The colour ramp of every map (map_layer, trend_map,
compare_map, timelapse, download_image) is stretched between the percentiles 1 and 99 of its own values over the region
(the frames of an animation, those of the map of the whole period: the same for every frame), and its answer says the
range and how it was computed (stretch): when the user asks for other limits, give percentiles (e.g. [2, 98]) or vmin
and vmax; timelapse with same_colours false gives each frame its own range. Maps of classes (land cover, ecoregions, burn severity) keep the colour of each class. GeoTIFFs on this computer: download_image (one map of a small
region) and download_variables (several variables and metrics on aligned grids over a study area and, at a coarser
pixel size, over its ecoregions: the input variables of a model). Seasonal trends (Mann-Kendall test and Sen's slope
of each month, 16 days or year over the years): trend_table (over regions), trend_map and download_trend (on each
pixel); with test 'hamed-rao' (Hamed & Rao 1998) or 'tfpw' (trend-free pre-whitening, Yue et al. 2002), corrected for
the autocorrelation of the yearly values, which makes the plain test find significant trends too often. By day of the year: time_series with doy, a line per year (phenology, snow seasons), or the seasonal profile of
one or two variables on two y axes with interannual (the metric between the years of each month, 16 days or day,
default median) and other_variable (and other_sensor), e.g. the median NDSI and NDVI of each month of 2018-2024; each
y axis goes from the minimum to the maximum of its own variable, or as ylim and other_ylim say. Comparison of a
reference period with another: compare_series, compare_map and download_comparison. Hectares and %
of each class of a land cover map of a year, of the map of a variable cut at some values, or of the trend on each
pixel (significant decrease, no trend, increase): area_by_class. Gradients: the statistics of a map by elevation band
(region_stats with zones) and its profile along a line, with the elevation (transect). Animations
(timelapses) of a variable, a frame per year, month, 16 days or day with its date: timelapse (a GIF, or an MP4). Burn
severity of a fire (dNBR with the classes of the USGS, hectares and GeoTIFF; or, with index "RBR", the Relativized
Burn Ratio, a continuous index; or, with index "RdNBR", the relative dNBR of Miller & Thode 2007 with the classes of
the article, also with MODIS): burn_severity; with perimeter true, also the polygons of the burned area in a
GeoPackage, to use as the region of other analyses: {"file": <its path>, "name_field": "region"}. Only for the
administrators of the public viewer of results: publish_report, with the files written by those tools.

Other data of Earth Engine: besides the variables of the catalog, the tools compute any image or collection of images
of Earth Engine given by its ID (of the Earth Engine data catalog, of the GEE Community Catalog or of a project the
account can read), when the user gives an ID or asks for data that the catalog does not have. First describe_asset with
the ID: its type and use say whether to give it as collection (images with dates, aggregated in time like a variable,
with time series, trends and comparisons) or as image (a fixed image, or the mosaic of a collection of tiles: without
dates, so only maps, their statistics and GeoTIFFs, no time series, trends or comparisons); it gives its bands, their
scale, offset and unit, and arguments ready to pass. Then call the tools with collection or image, band (one, or a
list of several with band_reducer "sum", e.g. the 12 monthly bands of an image into the annual total, or "mean", e.g.
the depth bands of a soil image: each band times band_scale plus band_offset, then combined on each pixel where all of
them have data), band_scale, band_offset and unit (in UDUNITS; that of every band, so of their sum or mean: 12 monthly
bands in mm sum to mm) instead of variable and sensor. With terrain, "slope" or "aspect" of the band of an image (e.g.
of a DEM; one band, not several), the values are in degrees (its unit is then degree: give no unit, not that of the
band). To find the datasets of the Earth Engine data catalog by words (in English), dates and area: find_datasets;
those of the GEE Community Catalog by its themes: community_themes, then community_datasets (by theme or text); then
describe_asset with the id of one. Never invent an ID: use only those that the user gives or that
describe_asset, find_datasets, community_datasets or the page of a dataset give. The pixel filters of MonitorEO
(quality) are not for these data, which keep their own mask; the conditions of where are still variables of the
catalog. Cite the dataset as describe_asset and the references and credits of the results say.

A region is a JSON object with one of: {"wdpa_id": 389011} (or a list of IDs), {"ecoregion_id": 793},
{"ecoregion_at": [lon, lat]}, {"biome_id": 12} (a biome of RESOLVE Ecoregions 2017, 1 to 14 or 99 Rock and Ice, or a
list: the union of its ecoregions; list_classes of BIOME gives them), {"biome_at": [lon, lat]} (the biome at a point),
{"country": "ESP"} (ISO3), {"admin1": GAUL1_CODE} or {"admin2": GAUL2_CODE}
(administrative units of FAO GAUL 2025, see find_admin_units; or lists of them), {"admin3": "18134"} (a municipality
of Spain, with the code of the INE that find_admin_units gives with level 3), {"island_at": [lon, lat]} (the
island at a point), {"sea": 3324} or {"sea": "Alboran Sea"} (an ocean or sea: a sea area of the IHO of Marine Regions,
by the MRGID or the name that find_seas gives, or a list of them), {"sea_at": [lon, lat]} (the sea at a point),
{"bbox": [west, south, east, north]}, {"point": [lon, lat], "buffer": metres},
{"geojson": <GeoJSON geometry, Feature or FeatureCollection>} or {"file": "<path of a vector file>"}. Several
features give one series per feature. Any region takes "within", another region (with an area): only the part of each
feature inside it, e.g. the Mediterranean biome in Spain, {"biome_id": 12, "within": {"country": "ESP"}}, or a
protected area in a province. A whole biome spans continents (its statistics and grids are in EPSG:6933, equal area,
as those of every region wider than 40 degrees of longitude): give it within a country or another region, or use
MODIS, the climate or coarse pixels at an annual or monthly step. The large areas (more than 100,000 km²: a country,
a biome, most seas) are computed by default on pixels of 1 to 10 km (never finer than the data); give scale or
resolution for others. Over the open sea only the variables with data there have values (today the chlorophyll-a of
MODIS, Chl-a); the others are of the land, and their results over a sea say so in warnings. Within cuts the outline of the region; for the pixels
of a biome in a country (at the pixel of the layer BIOME) use instead the country with where on the classes of BIOME,
{"variable": "BIOME", "sensor": "RESOLVE", "classes": [12]}, or zones by its classes.
Every tool with a region takes where: only the pixels of the region whose variables pass some conditions, e.g. above
1,500 m and with less than 600 mm of rain a year: [{"variable": "ELEVATION", "sensor": "Copernicus", "min": 1500},
{"variable": "PRECIP", "sensor": "TerraClimate", "metric": "sum", "temporal": "annual", "max": 600}]. Each condition is
its variable aggregated over the period of the result (or its own "period": [start, end]; none for the fixed layers),
the same mask for every step of a series or a trend and, in the comparisons, over the reference period. A condition of
where can also be a land cover mask, which leaves out the pixels of some broad land covers (water, trees, grassland,
wetland, cropland, shrubland, built, bare, snow) after a land cover map of a year: {"landcover": "CORINE", "year": 2018,
"exclude": ["water", "built"]} (landcover_maps lists the maps, ESA WorldCover, Dynamic World, CORINE Land Cover and
MODIS MCD12Q1, their years and coverage, and the classes of each map in each land cover); choose the map and year
closest to the period of the result, and CORINE only in Europe. Dates are YYYY-MM-DD; season is ["MM-DD", "MM-DD"] (e.g. summer of each year).
Long series over big regions take minutes: use step "monthly" or "annual", or export_time_series_to_drive.
Without a project of the user (EE_PROJECT or connect) the tools compute with the shared account of MonitorEO, which
cannot export to Google Drive: the exports need the user's own Earth Engine account and project. With the shared
account each user has research EECUs for each month (compute of Earth Engine, 25 EECU-hours), only for research; who
has spent them cannot compute with it until the next month, and nor can anyone when the users of the shared account
have spent the monthly quota of its project (1,000 EECU-hours) but the reserve of the app of Earth Engine. MonitorEO
does not tell the EECUs spent (its count was not that of Earth Engine): do not estimate them. To use their own Google
Cloud project, own_projects lists those of the user's account registered in Earth Engine (after `earthengine
authenticate`), and connect connects with the one they choose. When an answer has quota_warning, or an error ends with its text
(Earth Engine has put the project in restricted mode: it has spent its noncommercial compute quota, so computations
are slow and may fail with too many requests), tell the user why it is slow or failed; with the shared account, that
to compute without waiting they can use their own Google Cloud project registered in Earth Engine (connect).

The texts of the tools are in English. Answer in the language of the user's question (in Spanish when they ask in
Spanish), and pass lang "es" to the tools that take it (about, list_variables, community_themes, list_classes) when
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
	{"variable": "PRECIP", "sensor": "TerraClimate", "metric": "sum", "temporal": "annual", "max": 600}]; on a
	categorical layer (ECOREGION, BIOME of sensor RESOLVE), with classes (the codes to keep) or exclude (those to leave
	out) instead of min and max, e.g. {"variable": "BIOME", "sensor": "RESOLVE", "classes": [12]} (list_classes)."""

LANDCOVER_DOC = """ A condition can instead leave out some land covers of a land cover map of a year
	(landcover_maps lists the maps, their years and the land covers), e.g. {"landcover": "CORINE", "year": 2018,
	"exclude": ["water", "built"]}."""

WHERE_DOC += LANDCOVER_DOC

SOURCE_DOC = """
	variable and sensor: a variable of the catalog (list_variables); with them, collection is one of the collections of
	that variable. Instead of variable and sensor, any data of Earth Engine by its ID (describe_asset first: it says
	which to give and its arguments): collection (a collection of images with dates, aggregated in time like a
	variable) or image (a fixed image, or the mosaic of a collection of tiles: without dates, so only maps, their
	statistics and GeoTIFFs, no time series, trends or comparisons), with band (required: one, or a list of several
	with band_reducer "sum" or "mean", which combines them into one value on each pixel where all of them have data,
	e.g. ["jan", ..., "dec"] with "sum" for the annual total), band_scale and band_offset (factor and offset of its
	stored values, of each band before they are combined) and unit (of the values after them, in UDUNITS: "mm", "degC",
	"kg m-2", "mm day-1", "1" if dimensionless; that of every band, so of their sum or mean, not turned from a rate into
	a total). These data keep their own mask: no pixel filters (quality)."""

TERRAIN_DOC = """
	terrain: "slope" or "aspect" of the band of an image (e.g. of a DEM; one band, not several), in degrees (its unit is
	then degree: give no unit, or "degree", not that of the band)."""


def tool(fn):
	"""Register FN as a tool whose errors reach the client with their message (those of the tools that compute, but
	the errors of their arguments, with the text of services.quota_warning when Earth Engine is in restricted mode), and
	whose calls that write files are kept in the log of OUTPUT (see _log); the tools of the data of Earth Engine by its
	ID (band) get their explanation (SOURCE_DOC, TERRAIN_DOC) in their description, and those with where, its
	explanation (WHERE_DOC)."""
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
			error = f'{type(e).__name__}: {e}'
			quota = None if fn.__name__ in NO_QUOTA_WARNING or isinstance(e, (ValueError, KeyError, TypeError)) else \
				services.quota_warning()  # why it failed, perhaps: Earth Engine in restricted mode
			raise ToolError(f"{error}{'' if error.endswith('.') else '.'} {quota}" if quota else error) from e
		_log(fn.__name__, sig, args, kwargs, out)
		return out if fn.__name__ in NO_QUOTA_WARNING else _quota_warning(out)
	return server.tool()(wrapped)


NO_QUOTA_WARNING = ('about', 'connect', 'own_projects', 'list_variables', 'describe_variable', 'publish_report',
                   'save_parameters', 'apply_parameters',
                   'community_themes', 'community_datasets', 'landcover_maps', 'find_datasets', 'list_classes')


def _quota_warning(out):
	"""The answer OUT of a tool with the warning of services.quota_warning (quota_warning in its JSON object) when
	Earth Engine has put the project in restricted mode."""
	quota = services.quota_warning()
	warned = {'quota_warning': quota} if quota else {}
	text = out[0] if isinstance(out, list) and out else out
	if not warned or not isinstance(text, str):
		return out
	try:
		res = json.loads(text)
	except ValueError:
		return out
	if not isinstance(res, dict):
		return out
	text = _text({**res, **warned})
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
            terrain=None, band_reducer=None):
	"""The keywords of services for the data of a tool: VARIABLE and SENSOR, a variable of the catalog (COLLECTION, one
	of the collections of that variable), or instead the data of Earth Engine given by its ID (COLLECTION or IMAGE, with
	BAND, one or several with BAND_REDUCER, BAND_SCALE, BAND_OFFSET, UNIT and TERRAIN; see describe_asset). ValueError,
	before Earth Engine, if neither is given, they are mixed or the bands cannot be combined (variable.check_bands)."""
	custom = {k: v for k, v in (('image', image), ('band', band), ('band_reducer', band_reducer),
	                            ('band_scale', band_scale), ('band_offset', band_offset), ('unit', unit),
	                            ('terrain', terrain))
	          if v is not None and v != '' and v != []}
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
	if not variables.bands_of({'band': band}):
		raise ValueError(f'give band: the band of {collection or image} (one, or several with band_reducer; '
		                 'describe_asset lists them)')
	variables.check_bands(dict(custom), collection or image)  # several without band_reducer, one with it, terrain...
	if terrain and not image:
		raise ValueError('terrain is for an image (image, e.g. a DEM), not for a collection')
	return dict(custom, **({'collection': collection} if collection else {}))


def _data(variable, sensor, source):
	"""What a tool computes, in the names of its files: the variable and sensor of the catalog ('NDVI_Sentinel-2'), or
	the end of the ID of the data of Earth Engine of SOURCE (see _source) with its band, or the reducer of its bands
	('TERRACLIMATE_pr', 'TERRACLIMATE_sum_aet_def', 'GLO30_DEM_slope': see variable.band_stem)."""
	asset = source.get('collection') or source.get('image')
	if variable or not asset:
		return f'{variable}_{sensor}'
	# as the services read the ID: ee.ImageCollection("X") is X
	return _stem(assets.normalize(asset).rstrip('/').split('/')[-1], variables.band_stem(source), source.get('terrain'))


def _dates(variable, sensor, source, what, **given):
	"""ValueError, before Earth Engine, for a tool of WHAT ('time series', 'trends', 'comparisons of periods'), which
	needs dates: if its data (VARIABLE and SENSOR, or SOURCE: see _source) are a fixed layer or image, without them
	(the message of the services, also when the dates are empty), or naming the dates of GIVEN that the call left
	empty. These tools take their dates after '*', without a default, so that their schema requires them although
	variable and sensor, before them, have one; an empty text still passes the schema."""
	if source.get('image'):
		spec = {'image': assets.normalize(source['image']), 'band': source.get('band'),
		        'band_reducer': source.get('band_reducer')}
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


def _notes(summary, res):
	"""Put in SUMMARY, the answer of a tool that summarizes its result RES, the data its values come from (data_source)
	and the warnings of its period (warnings: e.g. it begins before the first image of the data), when RES has
	them: what the services answer."""
	for k in ('data_source', 'warnings'):
		if res.get(k):
			summary[k] = res[k]


def _preview(res):
	"""The PNG preview of the map RES as an image, if Earth Engine made it (else its reason is in thumbnail_error of
	RES, and the map has its tiles anyway)."""
	if not res.get('thumbnail'):
		return []
	with open(res['thumbnail'], 'rb') as f:
		return [Image(data=f.read(), format='png')]


# what the answer of time_series has of a seasonal profile by day of the year, besides the profile itself
PROFILE_KEYS = ('variables', 'units', 'scales', 'interannual', 'other_ylabel', 'other_ylim')


def _profile_answer(summary, res):
	"""Put in SUMMARY, the answer of time_series, what its result RES has of a seasonal profile by day of the year
	(services.time_series with doy and interannual or other_variable): its variables with their units, pixel sizes and
	axes (PROFILE_KEYS), the profile (what the chart and the CSV show: its first MAX_ROWS_SHOWN rows) and the values of
	each year (rows) only when they fit too, as compare_series answers its profile."""
	summary.update({k: res.get(k) for k in PROFILE_KEYS})
	profile, rows = res['profile'], res['rows']
	summary['profile'] = profile[:MAX_ROWS_SHOWN]
	notes = []
	if len(profile) > MAX_ROWS_SHOWN:
		notes.append(f'{len(profile)} rows of the profile: the first {MAX_ROWS_SHOWN} are shown, all of them are in the '
		             'CSV file')
	if len(profile) + len(rows) <= MAX_ROWS_SHOWN:
		summary['rows'] = rows
	elif rows:
		notes.append(f'the {len(rows)} values of each year are not shown (time_series with doy, without interannual nor '
		             'other_variable, gives them for each variable)')
	if notes:
		summary['note'] = '; '.join(notes)


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
	warning = services.quota_warning()
	return f'{text}. {warning}' if warning else text


@tool
def own_projects(project: str = '') -> str:
	"""The Google Cloud projects of the Google account of `earthengine authenticate` that are registered in Earth
	Engine, to connect with one of them (connect): account, projects [{project, name, registration (noncommercial or
	commercial)}] and register (where to register another one). Google does not let MonitorEO list all the projects of
	the account, so it gives those it finds (the one of EE_PROJECT or of `earthengine set_project`, those of the Google
	Cloud CLI, the ee-<user> that the registration of Earth Engine creates, those of BigQuery), each one checked in Earth
	Engine without computing; the user can give another one. project: one more to check (e.g. the one used before)."""
	return _text(services.own_projects([project] if project.strip() else []))


@tool
def list_variables(sensor: Optional[str] = None, text: Optional[str] = None, lang: str = 'en',
                   theme: Optional[str] = None) -> str:
	"""Variables of the catalog of MonitorEO: variable, sensor (Sentinel-2, Landsat, Modis, Copernicus, MERIT Hydro,
	ERA5-Land, TerraClimate, CHIRPS, WorldClim, RESOLVE), collection, theme, resolution, dates and unit; rgb (true) when
	its images have a true colour (rgb_map, download_rgb). Filter by sensor, by theme (vegetation, water, snow, fire,
	energy, atmosphere, climate, terrain, ecosystems) or by text in the name (English or Spanish). lang: en or es."""
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
def list_classes(variable: str, sensor: str = 'RESOLVE', text: Optional[str] = None, limit: Optional[int] = None,
                 lang: str = 'en') -> str:
	"""The classes of ECOREGION or BIOME (sensor RESOLVE): code (for classes or exclude of where), name and biome;
	text finds them by name."""
	return _text(services.list_classes(variable, sensor, text, limit, lang))


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
def find_datasets(text: str, start: Optional[str] = None, end: Optional[str] = None,
                  bbox: Optional[List[float]] = None, kind: Optional[str] = None, limit: int = 20) -> str:
	"""Search the Earth Engine data catalog (the copy of its index in MonitorEO) by words in English (at least half of
	them in its title, ID, keywords or description), dates (collections with data between start and end; images, fixed,
	of any date) and area (bbox [w, s, e, n]): id, title, type, dates (no end: it goes on), provider, pixel (gsd, m) and
	page of each, the best first. Then describe_asset with an id. For data that the catalog of MonitorEO does not have;
	without Earth Engine."""
	return _text(services.find_datasets(text, start, end, bbox, kind, limit))


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
	"""Administrative units whose name contains TEXT: of FAO GAUL 2025, level 1 (regions, states...) or 2 (provinces,
	districts...), or level 3, the municipalities of Spain (IGN), in country (ISO3, e.g. "ESP"), with code and full name
	(DISP_EN). Use {"admin1": GAUL1_CODE}, {"admin2": GAUL2_CODE} or {"admin3": ADMIN3_CODE}; a country, {"country":
	"ESP"}."""
	if int(level) != 3:  # the municipalities of Spain are found without Earth Engine
		_ready()
	return _text(services.find_admin_units(text, level, country, limit))


@tool
def find_seas(text: str, limit: int = 10) -> str:
	"""Oceans and seas (IHO sea areas, Marine Regions) whose English name contains TEXT (e.g. "Alboran"): MRGID, NAME,
	AREA_KM2 and BOUNDS. Use {"sea": MRGID}; the whole Mediterranean Sea is 1905, its 10 sea areas as one region (PARTS:
	their MRGIDs)."""
	return _text(services.find_seas(text, limit))


@tool
def time_series(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str, end: str,
                step: str = 'monthly', metric: str = 'mean', stat: str = 'mean', season: Optional[List[str]] = None,
                quality: Optional[dict] = None, scale: Optional[float] = None, collection: Optional[str] = None,
                image: Optional[str] = None, band: Optional[Union[str, List[str]]] = None,
                band_reducer: Optional[str] = None, band_scale: Optional[float] = None,
                band_offset: Optional[float] = None, unit: Optional[str] = None, where: Optional[list] = None,
                doy: bool = False, interannual: Optional[str] = None, other_variable: Optional[str] = None,
                other_sensor: Optional[str] = None, ylim: Optional[List[float]] = None,
                other_ylim: Optional[List[float]] = None):
	"""Time series of a variable over a region: one value per step ('daily', '16-day', 'monthly', 'annual') and
	feature of the region, reduced in time with METRIC (mean, median, min, max, std, cv, pN) and over the region with
	STAT (mean, median, min, max, std, cv, pN; cv: coefficient of variation, 100 * std / mean, in %), with the number
	of images and of valid pixels of each value. Writes a CSV
	table and a PNG chart (paths in the answer) and returns the chart. Required: region, start and end, and variable
	and sensor or collection and band. quality: pixel filters, e.g. {"snow": false} or {"cloud_score": null} (SCL
	clouds); scale: pixel size of the statistics in metres. doy: a line per year over the days of the year (not with
	step annual); with interannual (the metric between the years of each step, default median) or other_variable (and
	other_sensor; right axis), a line per variable. ylim, other_ylim: [min, max] of the y axes (default: the data's)."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit,
	                 band_reducer=band_reducer)
	_dates(variable, sensor, source, 'time series', start=start, end=end)
	_ready()
	profiled = bool(doy and (interannual or other_variable))  # the seasonal profile (report.is_profile)
	other = f'{other_variable}_{other_sensor or sensor}' if profiled and other_variable else None
	stem = _stem('profile' if profiled else None, _data(variable, sensor, source), other, step, metric, start, end)
	res = services.time_series(region, variable, sensor, start, end, step, metric, stat, season=season,
	                           quality=quality, scale=scale, csv=_out(stem, 'csv'), chart=_out(stem, 'png'),
	                           where=where, doy=doy, interannual=interannual, other_variable=other_variable,
	                           other_sensor=other_sensor, ylim=ylim, other_ylim=other_ylim, **source)
	rows = res['rows']
	summary = {k: res.get(k) for k in ('title', 'unit', 'ylabel', 'scale', 'n_steps', 'regions', 'csv', 'chart', 'readme', 'parameters',
	                                    'references', 'credits', 'manual')}
	_notes(summary, res)
	if doy:
		summary['ylim'] = res.get('ylim')
	if profiled and isinstance(res.get('profile'), list):
		_profile_answer(summary, res)
	else:
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
              end: Optional[str] = None, metric: str = 'median', temporal: str = 'period', interannual: str = 'mean',
              season: Optional[List[str]] = None, quality: Optional[dict] = None, vmin: Optional[float] = None,
              vmax: Optional[float] = None, collection: Optional[str] = None, image: Optional[str] = None,
              band: Optional[Union[str, List[str]]] = None, band_reducer: Optional[str] = None,
              band_scale: Optional[float] = None, band_offset: Optional[float] = None, unit: Optional[str] = None,
              terrain: Optional[str] = None, where: Optional[list] = None, quick: bool = False, figure: bool = False,
              percentiles: Optional[List[float]] = None, preview: bool = True):
	"""Map of a variable over a region aggregated in time (e.g. the median NDVI of a period): returns the URL of
	its Earth Engine map tiles (XYZ, {z}/{x}/{y}, valid for some hours; add it to QGIS as an XYZ layer), the colour
	ramp and a PNG preview with the outline of the region. temporal: 'period' (METRIC over all the images),
	'annual', 'monthly' or '16-day' (METRIC of each, then INTERANNUAL between the years). quick: only the tiles, at
	once (without the preview, and with the colour ramp of the catalog instead of that of the map). figure: instead
	of the tiles, a figure for a report or a paper (PNG of 300 dpi with grid, scale bar, north arrow, colour ramp and
	credits), in file. percentiles: its colours between these percentiles of the map (default [1, 99]); stretch says
	how. Required: region, and variable and sensor or collection or image and band; start and end, except for the
	fixed layers."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit, terrain,
	                 band_reducer=band_reducer)
	_ready()
	if figure:
		path = _out(_stem('figure', _data(variable, sensor, source), *(() if image else (metric, start, end))), 'png')
		fig = services.map_figure(region, variable, sensor, start, end, metric, temporal, interannual, season, quality,
		                          vmin, vmax, path=path, where=where, percentiles=percentiles, **source)
		with open(fig['file'], 'rb') as f:
			return [_text(fig)] + [Image(data=f.read(), format='png')]
	png = None if quick or not preview else _out(_stem('map', _data(variable, sensor, source),
	                                                   *(() if image else (metric, start, end))), 'png')
	res = services.map_layer(region, variable, sensor, start, end, metric, temporal, interannual, season, quality,
	                         vmin, vmax, thumbnail=png, quick=quick, where=where, percentiles=percentiles, **source)
	return [_text(res)] + _preview(res)


@tool
def timelapse(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str, end: str,
              step: str = 'annual', metric: str = 'median', season: Optional[List[str]] = None,
              quality: Optional[dict] = None, vmin: Optional[float] = None, vmax: Optional[float] = None,
              fps: float = 1, dimensions: int = 600, video: bool = False, collection: Optional[str] = None,
              band: Optional[Union[str, List[str]]] = None, band_reducer: Optional[str] = None,
              band_scale: Optional[float] = None, band_offset: Optional[float] = None, unit: Optional[str] = None,
              where: Optional[list] = None, percentiles: Optional[List[float]] = None, same_colours: bool = True):
	"""Animation of a variable over a region (a timelapse): a frame per step ('annual', 'monthly', '16-day' or 'daily')
	of the period (and season), each the METRIC of the images of the step on each pixel, all with the colours of the
	map of the period (percentiles, default [1, 99]); same_colours false: each frame its own (frames: min, max). Written on each frame, its date, the
	title, the colour ramp with its unit and the credits of the data and of the region; the pixels without data in a
	step are light grey. At most 120 frames: annual or monthly steps for long periods. Writes a GIF (and, with
	video, an MP4 too; it needs ffmpeg: without it, note says so and the GIF is the file) and returns its last frame
	as a picture, the date and the number of images of each frame, and the colour ramp. It takes some minutes (Earth
	Engine makes each frame). fps: frames per second; dimensions: width or height of the map in pixels (64 to 1200).
	Not for the fixed layers, which have no dates. Required: region, start and end, and variable and sensor or
	collection and band."""
	source = _source(variable, sensor, collection, None, band, band_scale, band_offset, unit, band_reducer=band_reducer)
	_dates(variable, sensor, source, 'animations', start=start, end=end)
	_ready()
	path = _out(_stem('animation', _data(variable, sensor, source), step, metric, start, end), 'mp4' if video else 'gif')
	res = services.timelapse(region, variable, sensor, start, end, step, metric, season, quality, vmin, vmax,
	                         fps=fps, dimensions=dimensions, path=path, where=where, percentiles=percentiles,
	                         same_colours=same_colours, **source)
	summary = {k: res.get(k) for k in ('name', 'unit', 'step', 'n_frames', 'fps', 'min', 'max', 'palette', 'stretch',
	                                    'file', 'gif', 'note', 'readme', 'parameters', 'references', 'credits',
	                                    'manual')}
	_notes(summary, res)
	summary['frames'] = res.get('frames') or []
	return [_text(summary)] + _last_frame(res.get('gif'))


def _last_frame(gif):
	"""The last frame of the GIF of an animation as a PNG picture (the GIF itself would be too big for the model),
	or nothing without it."""
	if not gif or not os.path.exists(gif):
		return []
	try:
		import io
		from PIL import Image as Picture
		pic = Picture.open(gif)
		pic.seek(pic.n_frames - 1)
		buf = io.BytesIO()
		pic.convert('RGB').save(buf, 'PNG')
		return [Image(data=buf.getvalue(), format='png')]
	except Exception:  # the animation is in its file anyway
		return []


@tool
def rgb_map(region: dict, variable: str, sensor: str, start: str, end: str, metric: str = 'median',
            temporal: str = 'period', interannual: str = 'mean', season: Optional[List[str]] = None,
            quality: Optional[dict] = None, vmin: Optional[float] = None, vmax: Optional[float] = None,
            collection: Optional[str] = None,
            where: Optional[list] = None, quick: bool = False, preview: bool = True,
            percentiles: Optional[List[float]] = None):
	"""True colour of the images of a variable over a region: the red, green and blue surface reflectance of the
	same images and pixels as its map (map_layer with the same arguments: period, season, pixel filters, where),
	aggregated in time with the same metric (median, mean and pN band by band; max and min, the colours of the image
	where the variable is highest or lowest on each pixel; not sum, std, count nor mode). Use it with the map of an
	index to see what is on the ground: burned areas, bare soil, snow, water or clouds left by the filters. Only the
	variables with rgb in list_variables (those of Sentinel-2 and Landsat, and the cloud frequency of MODIS); not the
	fixed layers, the climate nor the other MODIS products. Returns the URL of its Earth Engine map tiles (XYZ,
	{z}/{x}/{y}, valid for some hours), the bands red, green and blue stretched together from min to max
	(reflectance: the lowest percentile 2 and the highest percentile 98 of the bands over the region, or of
	percentiles, or vmin and vmax) and a PNG preview with the outline of the region. quick: only the tiles, at once (without the preview, and
	from 0 to 0.3 instead of the range of the map); preview false: the tiles and their range, without the preview."""
	_ready()
	png = None if quick or not preview else _out(f'rgb_{variable}_{sensor}_{metric}_{start}_{end}', 'png')
	res = services.rgb_map(region, variable, sensor, start, end, metric, temporal, interannual, season, quality,
	                       vmin, vmax, thumbnail=png, quick=quick, collection=collection, where=where,
	                       percentiles=percentiles)
	return [_text(res)] + _preview(res)


def _test_stem(test):
	"""The trend test in the names of the files ('' for the Mann-Kendall test)."""
	return '' if str(test or 'mk').lower() == 'mk' else str(test).lower()


@tool
def area_by_class(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None,
                  start: Optional[str] = None, end: Optional[str] = None, landcover: Optional[str] = None,
                  year: Optional[int] = None, other_year: Optional[int] = None, breaks: Optional[List[float]] = None,
                  trend: bool = False, metric: Optional[str] = None, temporal: str = 'period',
                  interannual: str = 'mean', step: str = 'annual', part: Optional[int] = None, alpha: float = 0.05,
                  test: str = 'mk', season: Optional[List[str]] = None, quality: Optional[dict] = None, collection: Optional[str] = None,
                  image: Optional[str] = None, band: Optional[Union[str, List[str]]] = None,
                  band_reducer: Optional[str] = None, band_scale: Optional[float] = None,
                  band_offset: Optional[float] = None, unit: Optional[str] = None, terrain: Optional[str] = None,
                  where: Optional[list] = None):
	"""Hectares and % of each class over each feature of a region, of one of: landcover, a land cover map of a year
	(landcover_maps; e.g. "CORINE", 2018): each class of the map with its broad land cover, without variable (with
	other_year, its changes between the two years: each pair of classes and a Sankey diagram); breaks,
	the map of a variable (as map_layer, also the fixed layers) cut at those values, e.g. [1500, 2000, 2500] for the
	ELEVATION; or trend true, the trend of a variable on each pixel (as trend_map: step, part, metric of each year, the
	mean by default; start and end) in significant decrease, no significant trend and significant increase
	(p < alpha). The % is of the area with a class. Writes a CSV and returns a bar chart."""
	_ready()
	if landcover:
		source, what = {}, f"landcover_{landcover}_{year or ''}" + (f'_{other_year}' if other_year else '')
	else:
		source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit, terrain,
		                 band_reducer=band_reducer)
		if trend:
			_dates(variable, sensor, source, 'trends', start=start, end=end)
		what = _data(variable, sensor, source)
	stem = _stem('areas', what, 'trend' if trend else 'breaks' if breaks else '', start, end)
	res = services.area_by_class(region, variable, sensor, start, end, metric, temporal, interannual, season, quality,
	                             landcover, year, breaks, trend, step, part, alpha, test=test, csv=_out(stem, 'csv'),
	                             chart=_out(stem, 'png'), where=where, other_year=other_year, **source)
	summary = {k: res.get(k) for k in ('title', 'mode', 'unit', 'scale', 'by_landcover', 'by_group', 'changed_ha',
	                                    'unchanged_ha', 'rows', 'csv', 'chart', 'readme', 'parameters', 'references', 'credits', 'manual')
	           if res.get(k) is not None}
	_notes(summary, res)
	if len(summary.get('rows') or []) > MAX_ROWS_SHOWN:
		summary['note'] = f"{len(summary['rows'])} rows: the first {MAX_ROWS_SHOWN} are shown, all of them in the CSV"
		summary['rows'] = summary['rows'][:MAX_ROWS_SHOWN]
	out = [_text(summary)]
	if res.get('chart'):
		with open(res['chart'], 'rb') as f:
			out.append(Image(data=f.read(), format='png'))
	return out


@tool
def region_stats(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None,
                 start: Optional[str] = None, end: Optional[str] = None, metric: str = 'median',
                 temporal: str = 'period', season: Optional[List[str]] = None, quality: Optional[dict] = None,
                 scale: Optional[float] = None, collection: Optional[str] = None, image: Optional[str] = None,
                 band: Optional[Union[str, List[str]]] = None, band_reducer: Optional[str] = None,
                 band_scale: Optional[float] = None, band_offset: Optional[float] = None, unit: Optional[str] = None,
                 terrain: Optional[str] = None, where: Optional[list] = None, interannual: str = 'mean',
                 stats: Optional[List[str]] = None, zones: Optional[dict] = None):
	"""Statistics over each feature of a region of the map of a variable aggregated in time (METRIC; with temporal
	'annual', 'monthly' or '16-day', then INTERANNUAL between the years), with the number of pixels. stats: any of
	mean, median, min, max, std (standard deviation), cv (coefficient of variation: 100 * std / mean, in %) and pN
	(percentile N), for any variable; by default mean, std, cv, min, p5, p50, p95 and max (with zones, also p25 and
	p75). zones: those of each band of another variable instead, e.g. {"variable": "ELEVATION", "sensor":
	"Copernicus", "breaks": [1500, 2000, 2500]} (elevation bands), with a CSV and a chart. Required: region, and
	variable and sensor or collection or image and band; start and end, except for the fixed layers."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit, terrain,
	                 band_reducer=band_reducer)
	_ready()
	files = {}
	if zones:
		stem = _stem('zones', _data(variable, sensor, source), *(() if image else (metric, start, end)))
		files = {'csv': _out(stem, 'csv'), 'chart': _out(stem, 'png')}
	res = services.region_stats(region, variable, sensor, start, end, metric, temporal, interannual, season=season,
	                            quality=quality, stats=stats, scale=scale, where=where, zones=zones, **files, **source)
	if not zones:
		return _text(res)
	out = [_text(res)]
	if res.get('chart'):
		with open(res['chart'], 'rb') as f:
			out.append(Image(data=f.read(), format='png'))
	return out


@tool
def transect(line: list, variable: Optional[str] = None, sensor: Optional[str] = None, start: Optional[str] = None,
             end: Optional[str] = None, metric: str = 'median', temporal: str = 'period', interannual: str = 'mean',
             season: Optional[List[str]] = None, quality: Optional[dict] = None, spacing: Optional[float] = None,
             points: int = 100, collection: Optional[str] = None, image: Optional[str] = None,
             band: Optional[Union[str, List[str]]] = None, band_reducer: Optional[str] = None,
             band_scale: Optional[float] = None, band_offset: Optional[float] = None, unit: Optional[str] = None,
             terrain: Optional[str] = None, where: Optional[list] = None):
	"""Profile of the map of a variable (as map_layer, also the fixed layers) along a line ([[lon, lat], ...], two
	points or more), with the elevation: the mean of each segment of spacing metres (default: the length / points, at
	least a pixel), e.g. the NDVI from the valley to the summit. Writes a CSV and returns the chart. Required: line,
	and variable and sensor or collection or image and band; start and end, except for the fixed layers."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit, terrain,
	                 band_reducer=band_reducer)
	_ready()
	stem = _stem('transect', _data(variable, sensor, source), *(() if image else (metric, start, end)))
	res = services.transect(line, variable, sensor, start, end, metric, temporal, interannual, season, quality,
	                        spacing, points, csv=_out(stem, 'csv'), chart=_out(stem, 'png'), where=where, **source)
	out = [_text(res)]
	if res.get('chart'):
		with open(res['chart'], 'rb') as f:
			out.append(Image(data=f.read(), format='png'))
	return out


@tool
def export_image_to_drive(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None,
                          start: Optional[str] = None, end: Optional[str] = None, metric: str = 'median',
                          temporal: str = 'period', season: Optional[List[str]] = None, quality: Optional[dict] = None,
                          resolution: Optional[float] = None, crs: str = 'auto', folder: str = 'MonitorEO',
                          name: Optional[str] = None, collection: Optional[str] = None, image: Optional[str] = None,
                          band: Optional[Union[str, List[str]]] = None, band_reducer: Optional[str] = None,
                          band_scale: Optional[float] = None, band_offset: Optional[float] = None,
                          unit: Optional[str] = None, terrain: Optional[str] = None,
                          where: Optional[list] = None) -> str:
	"""Export the map of a variable over a region to a GeoTIFF in a folder of the Google Drive of the Earth Engine
	account (a batch task, without limits of size; it needs the user's own account, not the shared one). resolution:
	pixel size in metres (default: that of the data); crs: 'auto' (UTM zone of the region; EPSG:6933 over 40° of
	longitude) or e.g. 'EPSG:25830'. Check it with task_status. Required: region, and variable and sensor or
	collection or image and band; start and end, except for the fixed layers."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit, terrain,
	                 band_reducer=band_reducer)
	_ready()
	return _text(services.export_image(region, variable, sensor, start, end, metric, temporal, season=season,
	                                   quality=quality, resolution=resolution, crs=crs, folder=folder, name=name,
	                                   where=where, **source))


@tool
def export_time_series_to_drive(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *,
                                start: str, end: str, step: str = 'monthly', metric: str = 'mean', stat: str = 'mean',
                                season: Optional[List[str]] = None, quality: Optional[dict] = None,
                                scale: Optional[float] = None, folder: str = 'MonitorEO', name: Optional[str] = None,
                                collection: Optional[str] = None, image: Optional[str] = None,
                                band: Optional[Union[str, List[str]]] = None, band_reducer: Optional[str] = None,
                                band_scale: Optional[float] = None, band_offset: Optional[float] = None,
                                unit: Optional[str] = None, where: Optional[list] = None) -> str:
	"""Export a time series (as time_series) to a CSV file in a folder of Google Drive: for long series or many
	regions (it needs the user's own Earth Engine account, not the shared one). Check it with task_status. Required:
	region, start and end, and variable and sensor or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit,
	                 band_reducer=band_reducer)
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
                   band: Optional[Union[str, List[str]]] = None, band_reducer: Optional[str] = None,
                   band_scale: Optional[float] = None, band_offset: Optional[float] = None, unit: Optional[str] = None,
                   terrain: Optional[str] = None, where: Optional[list] = None, vmin: Optional[float] = None,
                   vmax: Optional[float] = None, percentiles: Optional[List[float]] = None) -> str:
	"""Download the map of a variable over a region to a GeoTIFF on this computer (float32, NoData -9999), computed
	by Earth Engine in tiles: for small regions (up to some million pixels); bigger ones, export_image_to_drive.
	resolution: pixel size in metres (default: that of the data); crs: 'auto' (UTM zone of the region; EPSG:6933
	over 40° of longitude) or e.g. 'EPSG:25830'. Returns the path of the file, its grid and its colours (min, max: its
	percentiles, default [1, 99], or vmin and vmax). Required: region, and
	variable and sensor or collection or image and band; start and end, except for the fixed layers."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit, terrain,
	                 band_reducer=band_reducer)
	_ready()
	stem = _stem(_data(variable, sensor, source), *(() if image else (metric, start, end)))
	return _text(services.download_image(region, variable, sensor, start, end, metric, temporal, interannual,
	                                     season=season,
	                                     quality=quality, resolution=resolution, crs=crs, clip=clip,
	                                     path=_out(stem, 'tif'), where=where, vmin=vmin, vmax=vmax,
	                                     percentiles=percentiles, **source))


@tool
def download_rgb(region: dict, variable: str, sensor: str, start: str, end: str, metric: str = 'median',
                 temporal: str = 'period', interannual: str = 'mean', season: Optional[List[str]] = None,
                 quality: Optional[dict] = None, resolution: Optional[float] = None, crs: str = 'auto',
                 clip: bool = True, collection: Optional[str] = None,
                 where: Optional[list] = None, percentiles: Optional[List[float]] = None,
                 vmin: Optional[float] = None, vmax: Optional[float] = None) -> str:
	"""Download the true colour of the images of a variable over a region (see rgb_map: the red, green and blue
	surface reflectance of the same images and pixels as its map, with the same metric) to a GeoTIFF on this
	computer with the bands red, green and blue (float32 reflectance, NoData -9999), on the same grid as
	download_image with the same arguments (resolution, crs): to compare the values of an index with what is on the
	ground. For small regions. Returns the path of the file, its grid and min and max, the range of reflectance to
	show the three bands together (the lowest percentile 2 and the highest percentile 98 of the bands, or of
	percentiles)."""
	_ready()
	return _text(services.download_rgb(region, variable, sensor, start, end, metric, temporal, interannual,
	                                   season=season, quality=quality, resolution=resolution, crs=crs, clip=clip,
	                                   path=_out(f'{variable}_{sensor}_{metric}_{start}_{end}_RGB', 'tif'),
	                                   collection=collection, where=where, percentiles=percentiles, vmin=vmin,
	                                   vmax=vmax))


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
	and band (other collections; several bands, a list, with "band_reducer": "sum" or "mean" in that variable),
	drive_folder.
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
                test: str = 'mk', collection: Optional[str] = None, image: Optional[str] = None,
                band: Optional[Union[str, List[str]]] = None, band_reducer: Optional[str] = None,
                band_scale: Optional[float] = None, band_offset: Optional[float] = None, unit: Optional[str] = None,
                where: Optional[list] = None):
	"""Seasonal trends of a variable over each feature of a region:
	for each part of the year (step 'monthly': each month; '16-day': 23 parts of 16 days from 1 January; 'annual':
	the year), the spatial STAT of the METRIC of its images in each year, and the trend of those yearly values:
	Mann-Kendall tau, Z and p-value (significant if p < alpha) and Sen's slope (change per year). Use 8 or more
	years. test: 'mk', 'hamed-rao' or 'tfpw' (autocorrelation). Writes a CSV and a chart of the yearly values with their Sen lines, and returns the chart. Required:
	region, start and end, and variable and sensor or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit,
	                 band_reducer=band_reducer)
	_dates(variable, sensor, source, 'trends', start=start, end=end)
	_ready()
	stem = _stem('trend', _data(variable, sensor, source), step, start, end, _test_stem(test))
	res = services.trend_table(region, variable, sensor, start, end, step, metric, stat, season=season,
	                           quality=quality, scale=scale, alpha=alpha, test=test, csv=_out(stem, 'csv'),
	                           chart=_out(stem, 'png'), where=where, **source)
	summary = {k: res.get(k) for k in ('title', 'unit', 'ylabel', 'scale', 'csv', 'chart')}
	summary['slope_unit'] = f"{res['unit']} / year" if res.get('unit') else 'per year'  # data without a unit
	summary['trends'] = res['rows']
	summary.update({k: res.get(k) for k in ('readme', 'parameters', 'references', 'credits', 'manual')})
	_notes(summary, res)
	out = [_text(summary)]
	if res.get('chart'):
		out.append(Image(path=res['chart']))
	return out


@tool
def trend_map(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str, end: str,
              step: str = 'annual', part: Optional[int] = None, output: str = 'slope', metric: str = 'mean',
              season: Optional[List[str]] = None, quality: Optional[dict] = None, alpha: Optional[float] = None,
              test: str = 'mk', collection: Optional[str] = None, image: Optional[str] = None,
              band: Optional[Union[str, List[str]]] = None, band_reducer: Optional[str] = None,
              band_scale: Optional[float] = None, band_offset: Optional[float] = None, unit: Optional[str] = None,
              where: Optional[list] = None, vmin: Optional[float] = None, vmax: Optional[float] = None,
              quick: bool = False, percentiles: Optional[List[float]] = None, preview: bool = True):
	"""Map of the trend of a part of the year computed on each pixel (see trend_table): part is the month (1-12)
	with step 'monthly', 1-23 with '16-day', nothing with 'annual'; output 'slope' (Sen, per year), 'tau', 'z',
	'p_value', 'intercept' or 'n' (years with data); alpha (e.g. 0.05) keeps only the significant pixels. Returns
	the URL of its Earth Engine tiles (XYZ, valid for some hours) and a preview. quick: only the tiles, at once
	(without the preview, and with a fixed colour ramp instead of that of the map). percentiles (default [1, 99]) or
	vmin and vmax: the colour ramp (tau and p_value: fixed). Required: region, start and end, and variable and sensor
	or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit,
	                 band_reducer=band_reducer)
	_dates(variable, sensor, source, 'trends', start=start, end=end)
	_ready()
	thumb = None if quick or not preview else _out(_stem('trend', _data(variable, sensor, source), step, part, output,
	                                                     _test_stem(test)), 'png')
	res = services.trend_map(region, variable, sensor, start, end, step, part, output, metric, season=season,
	                         quality=quality, alpha=alpha, test=test, vmin=vmin, vmax=vmax, thumbnail=thumb, quick=quick,
	                         where=where, percentiles=percentiles, **source)
	return [_text(res)] + _preview(res)


@tool
def download_trend(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str, end: str,
                   step: str = 'annual', part: Optional[int] = None, metric: str = 'mean',
                   season: Optional[List[str]] = None, quality: Optional[dict] = None, alpha: Optional[float] = None,
                   test: str = 'mk', resolution: Optional[float] = None, crs: str = 'auto', collection: Optional[str] = None,
                   image: Optional[str] = None, band: Optional[Union[str, List[str]]] = None,
                   band_reducer: Optional[str] = None, band_scale: Optional[float] = None,
                   band_offset: Optional[float] = None, unit: Optional[str] = None,
                   where: Optional[list] = None, vmin: Optional[float] = None, vmax: Optional[float] = None,
                   percentiles: Optional[List[float]] = None) -> str:
	"""Download the trend of a part of the year on each pixel (see trend_map) to a GeoTIFF on this computer with
	the bands slope, tau, z, p_value, intercept and n. For small regions (Earth Engine computes it in tiles).
	percentiles or vmin, vmax: its colours.
	Required: region, start and end, and variable and sensor or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit,
	                 band_reducer=band_reducer)
	_dates(variable, sensor, source, 'trends', start=start, end=end)
	_ready()
	stem = _stem('trend', _data(variable, sensor, source), step, part, start, end, _test_stem(test))
	return _text(services.download_trend(region, variable, sensor, start, end, step, part, metric, season=season,
	                                     quality=quality, alpha=alpha, test=test, resolution=resolution, crs=crs,
	                                     path=_out(stem, 'tif'), where=where, vmin=vmin, vmax=vmax,
	                                     percentiles=percentiles, **source))


@tool
def compare_series(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str, end: str,
                   other_start: str, other_end: str, step: str = 'monthly', metric: str = 'mean', stat: str = 'mean',
                   season: Optional[List[str]] = None, quality: Optional[dict] = None, scale: Optional[float] = None,
                   collection: Optional[str] = None, image: Optional[str] = None,
                   band: Optional[Union[str, List[str]]] = None, band_reducer: Optional[str] = None,
                   band_scale: Optional[float] = None, band_offset: Optional[float] = None, unit: Optional[str] = None,
                   where: Optional[list] = None):
	"""Compare a reference period (start to end) with another (other_start to other_end) over each feature of a
	region: the mean of each part of the year (step 'monthly', '16-day' or 'annual') over the years of each period
	and the difference (other - reference). Writes a CSV and a chart of both
	periods by part of the year, and returns the chart. Required: region, start, end, other_start and other_end, and
	variable and sensor or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit,
	                 band_reducer=band_reducer)
	_dates(variable, sensor, source, 'comparisons of periods', start=start, end=end, other_start=other_start,
	       other_end=other_end)
	_ready()
	stem = _stem('comparison', _data(variable, sensor, source), start, end, other_start, other_end)
	res = services.compare_series(region, variable, sensor, start, end, other_start, other_end, step, metric, stat,
	                              season=season, quality=quality, scale=scale, csv=_out(stem, 'csv'),
	                              chart=_out(stem, 'png'), where=where, **source)
	summary = {k: res.get(k) for k in ('title', 'unit', 'ylabel', 'scale', 'csv', 'chart')}
	summary['comparison'] = res['profile']
	summary.update({k: res.get(k) for k in ('readme', 'parameters', 'references', 'credits', 'manual')})
	_notes(summary, res)
	out = [_text(summary)]
	if res.get('chart'):
		out.append(Image(path=res['chart']))
	return out


@tool
def compare_map(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str, end: str,
                other_start: str, other_end: str, metric: str = 'median', temporal: str = 'period',
                season: Optional[List[str]] = None, quality: Optional[dict] = None, collection: Optional[str] = None,
                image: Optional[str] = None, band: Optional[Union[str, List[str]]] = None,
                band_reducer: Optional[str] = None, band_scale: Optional[float] = None,
                band_offset: Optional[float] = None, unit: Optional[str] = None, where: Optional[list] = None,
                vmin: Optional[float] = None, vmax: Optional[float] = None,
                percentiles: Optional[List[float]] = None):
	"""Map of the difference between the variable aggregated over another period (other_start to other_end) and
	over the reference period (start to end), e.g. the median NDVI of 2023 minus that of 2018-2021. Returns the URL
	of its Earth Engine tiles (XYZ, valid for some hours) and a preview; percentiles (default [1, 99]) or vmin and
	vmax: its colour ramp. Required: region, start, end, other_start and other_end, and variable and sensor or
	collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit,
	                 band_reducer=band_reducer)
	_dates(variable, sensor, source, 'comparisons of periods', start=start, end=end, other_start=other_start,
	       other_end=other_end)
	_ready()
	thumb = _out(_stem('comparison', _data(variable, sensor, source), metric), 'png')
	res = services.compare_map(region, variable, sensor, start, end, other_start, other_end, metric, temporal,
	                           season=season, quality=quality, thumbnail=thumb, where=where, vmin=vmin, vmax=vmax,
	                           percentiles=percentiles, **source)
	return [_text(res)] + _preview(res)


@tool
def download_comparison(region: dict, variable: Optional[str] = None, sensor: Optional[str] = None, *, start: str,
                        end: str, other_start: str, other_end: str, metric: str = 'median', temporal: str = 'period',
                        season: Optional[List[str]] = None, quality: Optional[dict] = None,
                        resolution: Optional[float] = None, crs: str = 'auto', collection: Optional[str] = None,
                        image: Optional[str] = None, band: Optional[Union[str, List[str]]] = None,
                        band_reducer: Optional[str] = None, band_scale: Optional[float] = None,
                        band_offset: Optional[float] = None, unit: Optional[str] = None,
                        where: Optional[list] = None, percentiles: Optional[List[float]] = None,
                        vmin: Optional[float] = None, vmax: Optional[float] = None) -> str:
	"""Download the comparison of two periods (see compare_map) to a GeoTIFF on this computer with the bands
	difference (other - reference), reference and other; percentiles or vmin, vmax: its colours. For small regions.
	Required: region, start, end,
	other_start and other_end, and variable and sensor or collection and band."""
	source = _source(variable, sensor, collection, image, band, band_scale, band_offset, unit,
	                 band_reducer=band_reducer)
	_dates(variable, sensor, source, 'comparisons of periods', start=start, end=end, other_start=other_start,
	       other_end=other_end)
	_ready()
	stem = _stem('comparison', _data(variable, sensor, source), metric, start, end, other_start, other_end)
	return _text(services.download_comparison(
		region, variable, sensor, start, end, other_start, other_end, metric, temporal, season=season,
		quality=quality, resolution=resolution, crs=crs, path=_out(stem, 'tif'), where=where, percentiles=percentiles,
		vmin=vmin, vmax=vmax, **source))


@tool
def burn_severity(region: dict, start: str, end: str, other_start: str, other_end: str, sensor: str = 'Sentinel-2',
                  metric: str = 'median', season: Optional[List[str]] = None, quality: Optional[dict] = None,
                  resolution: Optional[float] = None, crs: str = 'auto', index: str = 'dNBR',
                  where: Optional[list] = None, collection: Optional[str] = None, perimeter: bool = False,
                  burned_min: Optional[float] = None, min_ha: Optional[float] = None) -> str:
	"""Burn severity of a fire with the dNBR and the official classes of the USGS (Key & Benson 2006): dNBR = NBR of
	a period before the fire (start to end) minus NBR of a period after it (other_start to other_end), with
	Sentinel-2 (20 m, since 2017) or Landsat (30 m, since 1984). Returns the hectares of each class over each feature
	of the region (unburned, low, moderate-low, moderate-high and high severity, and enhanced regrowth) and the burned
	area (dNBR >= 0.1), writes them to a CSV and downloads a GeoTIFF with the bands dnbr, severity (class -2 to 4),
	nbr_before and nbr_after. Use periods without the fire: e.g. the 3 months before it and the 2-3 months after it
	ends. For small regions (bigger ones: lower resolution). index "RBR" (only when the user asks for it): the
	Relativized Burn Ratio, dNBR / (NBR before + 1.001), with the NBR of B8A and B12 of Sentinel-2 (20 m; Landsat:
	NIR and SWIR2), without phenological correction and on the scale of the dNBR (articles multiply it by 1000): a
	continuous index without classes; returns its mean, median, std, cv (coefficient of variation, %), p10, p90, min
	and max and the hectares with values
	over each feature, and a GeoTIFF with the bands rbr, dnbr, nbr_before and nbr_after.
	index "RdNBR" (when the user asks for it or for the classes of Miller & Thode, for a fire over heterogeneous
	vegetation, e.g. shrubs and forest, or to compare fires): the relative dNBR of Miller & Thode 2007, dNBR /
	sqrt(|NBR before|) with |NBR before| at least 0.001 (Howe et al. 2022), the change relative to the vegetation
	before the fire, with the classes of the article (unchanged < 0.069, low 0.069 to 0.316, moderate 0.316 to 0.641,
	high >= 0.641), on the scale of the dNBR, without the factor 1000 of the article (0.641 here is 641 there) and
	without its offset (the dNBR of an unburned area outside the fire). Sensors: Sentinel-2 (B8 and B12, 20 m),
	Landsat (30 m) or "Modis" (500 m, only with this index: the daily surface reflectance of Terra, since 2000, or of
	Aqua, since 2002-07-04, with collection "MODIS/061/MYD09GA"; its classes are approximate, as a pixel of 500 m
	mixes burned and unburned land, and small fires are missed). Its classes were calibrated with Landsat TM (30 m)
	and field plots of 14 fires of the Sierra Nevada of California, mostly in conifer and live oak forests (also
	pinyon pine and sagebrush), with field data one year after the fire: give a period after about
	one year after the fire, in the season of the period before. Returns the hectares of each class (classes),
	the changed area (burned_ha, RdNBR >= 0.069; unchanged is not unburned) and the mean, median, std, cv (%), p10,
	p90, min and max of the RdNBR (stats) over each feature, a CSV of the classes and a GeoTIFF with the bands rdnbr, severity (class 0
	to 3), dnbr, nbr_before and nbr_after. collection: only for index "RdNBR" with sensor "Modis".
	perimeter true (when the user wants the perimeter, outline or polygons of the burned area, e.g. to study it
	afterwards): also a GeoPackage (perimeter) with a MultiPolygon of the burned pixels of each feature of the region
	(perimeter_ha, perimeter_patches), to give as the region of the next analyses: {"file": <perimeter>, "name_field":
	"region"} (e.g. the NDVI after the fire inside it). Burned: index >= burned_min, by default dNBR 0.1 or RdNBR 0.069
	(the RBR has no classes: ask the user for burned_min, e.g. 0.1); burned patches of less than min_ha hectares
	(default 1) are left out, and unburned islands of less than min_ha inside them filled (0: every pixel)."""
	_ready()
	name = {i.lower(): i for i in services.BURN_INDICES}.get(str(index or 'dNBR').lower())
	prefix = f'{name}_' if name and name != 'dNBR' else ''  # burn_severity_RBR_..., burn_severity_RdNBR_...
	stem = f"burn_severity_{prefix}{sensor}_{start}_{end}_{other_start}_{other_end}"
	tif = _out(stem, 'tif')  # the perimeter next to it, with the same time: <stem>_<time>_perimeter.gpkg
	return _text(services.burn_severity(region, sensor, start, end, other_start, other_end, metric, season=season,
	                                    quality=quality, resolution=resolution, crs=crs, path=tif,
	                                    csv=_out(stem, 'csv'), index=index, where=where, collection=collection,
	                                    perimeter=tif[:-4] + '_perimeter.gpkg' if perimeter else None,
	                                    burned_min=burned_min, min_ha=min_ha))


@tool
def publish_report(title: str, summary: str, files: List[str], question: Optional[str] = None,
                   answer: Optional[str] = None, method: Optional[str] = None, region: Optional[dict] = None,
                   authors: Optional[List[str]] = None, downloads: Optional[List[str]] = None,
                   report_id: Optional[str] = None, site: Optional[str] = None) -> str:
	"""For the administrators of the viewer of results of MonitorEO: publish an analysis as a report of the static
	web site in the folder site (default: MONITOREO_SITE or ~/MonitorEO/visor). files: the GeoTIFF, CSV and figure
	files written by the other tools (download_trend, download_comparison, download_image, burn_severity, time_series,
	trend_table, compare_series, map_layer with figure; not yet the true colour of download_rgb) in the order of the
	page; their calls are read from the log of this server. Texts in Spanish, the language of the viewer: title (e.g.
	the question of the analysis), summary (the answer in one or two sentences), question, answer (the result;
	paragraphs separated by a blank line), method; region: {"name": ..., "wdpa_id": ...}; downloads: other files (a
	PDF). The GeoTIFFs become Cloud Optimized GeoTIFFs and the site gets the report, the viewer and its catalogue. It
	is public only when an administrator deploys the folder (git push to the repository of the site, or rsync to its
	server); `monitoreo serve` shows it on this computer."""
	spec = {'title': title, 'summary': summary, 'question': question, 'answer': answer, 'method': method,
	        'region': region, 'authors': authors, 'downloads': downloads, 'results': list(files)}
	if report_id:
		spec['id'] = report_id
	res = services.publish_report({k: v for k, v in spec.items() if v is not None}, site, OUTPUT,
	                              publish.calls_log(OUTPUT))
	res['next'] = (f"see it with `monitoreo serve {res['site']}`, then deploy the folder (git push or rsync) to make "
	               'it public')
	return _text(res)


# the analyses of monitoreo.services (monitoreo.parameters) that are tools of this server with another name or with
# another argument: their tool and the arguments that make it that analysis
TOOL_OF = {'export_image': ('export_image_to_drive', {}), 'time_series_to_drive': ('export_time_series_to_drive', {}),
           'map_figure': ('map_layer', {'figure': True})}
ANALYSIS_OF = {'export_image_to_drive': 'export_image', 'export_time_series_to_drive': 'time_series_to_drive'}


@tool
def save_parameters(analysis: str, arguments: dict, name: Optional[str] = None) -> str:
	"""Save the parameters of an analysis as JSON, to repeat it later or in another tool of MonitorEO (the Python and R
	packages, the command line, the QGIS plugin, the Earth Engine app): analysis is the tool that computed it (e.g.
	time_series, map_layer, trend_table, burn_severity) and arguments the arguments it was called with. The tools that
	write files already write it next to them (parameters in their answer); this one is for the others (e.g. map_layer
	without figure) or to save it with a name. Returns the path of the file and its contents."""
	from . import parameters
	args = dict(arguments or {})
	analysis = ANALYSIS_OF.get(analysis, analysis)
	path = _out(_stem('parameters', name or analysis), 'json')
	try:
		parameters.save(analysis, args, path)
	except ValueError as e:
		raise ToolError(str(e)) from e
	return _text({'parameters': path, 'contents': parameters.read(path)})


@tool
def apply_parameters(parameters: str) -> str:
	"""The parameters of an analysis saved as JSON (its text or a .parameters.json path): which tool computes it, with
	which arguments (not computed). Tell the user what is in not_applied, then call that tool."""
	from . import parameters as params
	try:
		checked = params.check(parameters)
	except ValueError as e:
		raise ToolError(str(e)) from e
	analysis = checked['analysis']
	name, extra = TOOL_OF.get(analysis, (analysis, {}))
	fn = globals().get(name)
	if fn is None:
		raise ToolError(f'{analysis} is not a tool of the MCP server of MonitorEO: compute it with the Python package or '
		                'the command line (monitoreo run FILE)')
	takes = inspect.signature(fn).parameters
	args, skipped = dict(extra), list(checked['not_applied'])
	params = dict(checked['parameters'])
	if name == 'burn_severity' and 'perimeter' in params:  # this tool writes its own file: it asks for it with true
		params['perimeter'] = bool(params['perimeter'])
	for k, v in params.items():
		if k in takes:
			args[k] = v
		else:
			skipped.append({'name': k, 'value': v, 'reason': f'not an argument of the tool {name} of this server'})
	out = {'tool': name, 'arguments': args, 'not_applied': skipped}
	if checked.get('note'):
		out['note'] = checked['note']
	out['next'] = (f'call the tool {name} with these arguments'
	               + (' after telling the user what is not applied and why' if skipped else ''))
	return _text(out)


@tool
def task_status(operation: str) -> str:
	"""State of an export task (PENDING, RUNNING, SUCCEEDED, FAILED, CANCELLED) and its progress, given the operation
	returned by the export tools."""
	_ready()
	return _text(services.task_status(operation))


def main():
	"""Run the server; if it crashes (a fatal error: an access violation, a stack overflow, an abort), the Python
	traceback of each of its threads goes to its stderr, never to its stdout (the channel of the MCP protocol), so that
	the log of its client says where (that of the assistant: assistant-output.log as an app)."""
	try:
		faulthandler.enable(file=sys.stderr, all_threads=True)
	except Exception:  # no stderr with a file descriptor (pythonw.exe: None): no traceback, but the server starts
		pass
	server.run()


if __name__ == '__main__':
	main()
