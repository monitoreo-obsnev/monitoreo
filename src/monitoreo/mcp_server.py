"""MCP server of MonitorEO (stdio), for language models: the functions of monitoreo.services as tools.

    monitoreo mcp        (or python -m monitoreo.mcp_server, without the update below)

`monitoreo mcp` first installs the last version of the package in GitHub if the installed one is another (see
monitoreo.update), so the server always runs that version; --no-update skips it.

It uses the Earth Engine credentials of `earthengine authenticate` and the project of the variable EE_PROJECT (or
the tool connect). Files (CSV tables, PNG charts and maps) are written to the folder MONITOREO_OUTPUT (default:
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
from . import publish, services

OUTPUT = os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO')
MAX_ROWS_SHOWN = 300

INSTRUCTIONS = about_.DESCRIPTION['en'] + ' ' + about_.ACKNOWLEDGEMENTS['en'] + """ Mention this funding when the user
asks about MonitorEO or its sources (the tool about gives it with the logos).

MonitorEO (OBSNEV, Universidad de Granada): satellite variables of Google Earth Engine (NDVI, EVI, NDWI,
LSWI, NDSI, NDCI, NBR, albedo, land surface temperature, evapotranspiration, LAI, chlorophyll, aerosols) of Sentinel-2,
Landsat and MODIS, with the pixel filters of MonitorEO (clouds, water, snow, aerosols).

Workflow: list_variables (or describe_variable) to choose variable and sensor; find_protected_areas to get the
WDPA ID of a protected area; then time_series (table, CSV and chart), map_layer (map tiles and preview),
region_stats (statistics of a map) or the exports to Google Drive (export_image_to_drive,
export_time_series_to_drive, then task_status). GeoTIFFs on this computer: download_image (one map of a small
region) and download_variables (several variables and metrics on aligned grids over a study area and, at a coarser
pixel size, over its ecoregions: the input variables of a model). Seasonal trends (Mann-Kendall test and Sen's slope
of each month, 16 days or year over the years): trend_table (over regions), trend_map and download_trend (on each
pixel). Comparison of a reference period with another: compare_series, compare_map and download_comparison. Burn
severity of a fire (dNBR with the classes of the USGS, hectares and GeoTIFF): burn_severity. Only for the
administrators of the public viewer of results: publish_report, with the files written by those tools.

A region is a JSON object with one of: {"wdpa_id": 389011} (or a list of IDs), {"ecoregion_id": 793},
{"ecoregion_at": [lon, lat]}, {"bbox": [west, south, east, north]}, {"point": [lon, lat], "buffer": metres},
{"geojson": <GeoJSON geometry, Feature or FeatureCollection>} or {"file": "<path of a vector file>"}. Several
features give one series per feature. Dates are YYYY-MM-DD; season is ["MM-DD", "MM-DD"] (e.g. summer of each year).
Long series over big regions take minutes: use step "monthly" or "annual", or export_time_series_to_drive."""

server = Server('MonitorEO', instructions=INSTRUCTIONS)


def tool(fn):
	"""Register FN as a tool whose errors reach the client with their message, and whose calls that write files are
	kept in the log of OUTPUT (see _log)."""
	sig = inspect.signature(fn)

	@functools.wraps(fn)
	def wrapped(*args, **kwargs):
		try:
			out = fn(*args, **kwargs)
		except ToolError:
			raise
		except Exception as e:
			raise ToolError(f'{type(e).__name__}: {e}') from e
		_log(fn.__name__, sig, args, kwargs, out)
		return out
	return server.tool()(wrapped)


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
		services.init()


def _out(stem, ext):
	os.makedirs(OUTPUT, exist_ok=True)
	stem = re.sub(r'[^A-Za-z0-9_-]+', '_', stem).strip('_')[:80]
	return os.path.join(OUTPUT, f"{stem}_{dt.datetime.now():%Y%m%d-%H%M%S}.{ext}")


def _text(obj):
	return json.dumps(obj, ensure_ascii=False, indent=1, default=str)


@tool
def about(lang: str = 'en'):
	"""What MonitorEO-OBSNEV is and who funds it (description and acknowledgements, in 'en' or 'es'), with the logos
	of the institutions and projects."""
	a = services.about(lang)
	return [_text({k: a[k] for k in ('name', 'description', 'acknowledgements', 'manual', 'repository')})] + \
	       [Image(path=p) for p in a['logos']]


@tool
def connect(project: str) -> str:
	"""Connect to Earth Engine with this Google Cloud project (registered in Earth Engine), instead of EE_PROJECT."""
	return f'Connected to Earth Engine with the project {services.init(project)}'


@tool
def list_variables(sensor: Optional[str] = None, text: Optional[str] = None, lang: str = 'es') -> str:
	"""Variables of the catalog of MonitorEO: variable, sensor (Sentinel-2, Landsat, Modis), collection, resolution,
	dates and unit. Filter by sensor or by text in the name. lang: es or en."""
	return _text(services.list_variables(sensor, text, lang))


@tool
def describe_variable(variable: str, sensor: Optional[str] = None, collection: Optional[str] = None) -> str:
	"""Formula, collection, scale, unit, resolution, dates, pixel filters and notes of a variable of the catalog."""
	return _text(services.describe_variable(variable, sensor, collection))


@tool
def find_protected_areas(text: str, limit: int = 10) -> str:
	"""Protected areas of the World Database on Protected Areas (WDPA) whose name contains TEXT, with their WDPA ID
	(SITE_ID), designation, IUCN category, country and area (km2). Use the SITE_ID as {"wdpa_id": ...}."""
	_ready()
	return _text(services.find_protected_areas(text, limit))


@tool
def time_series(region: dict, variable: str, sensor: str, start: str, end: str, step: str = 'monthly',
                metric: str = 'mean', stat: str = 'mean', season: Optional[List[str]] = None,
                quality: Optional[dict] = None, scale: Optional[float] = None, collection: Optional[str] = None):
	"""Time series of a variable over a region: one value per step ('daily', '16-day', 'monthly', 'annual') and
	feature of the region, reduced in time with METRIC (mean, median, min, max, pN) and over the region with STAT
	(mean, median, min, max, std, pN), with the number of images and of valid pixels of each value. Writes a CSV
	table and a PNG chart (paths in the answer) and returns the chart. quality: pixel filters, e.g.
	{"snow": false} or {"cloud_score": null} (SCL clouds); scale: pixel size of the statistics in metres."""
	_ready()
	stem = f'{variable}_{sensor}_{step}_{metric}_{start}_{end}'
	res = services.time_series(region, variable, sensor, start, end, step, metric, stat, season=season,
	                           quality=quality, scale=scale, csv=_out(stem, 'csv'), chart=_out(stem, 'png'),
	                           collection=collection)
	rows = res['rows']
	summary = {k: res[k] for k in ('title', 'unit', 'scale', 'n_steps', 'regions', 'csv', 'chart')}
	summary['rows'] = rows[:MAX_ROWS_SHOWN]
	if len(rows) > MAX_ROWS_SHOWN:
		summary['note'] = f'{len(rows)} rows: the first {MAX_ROWS_SHOWN} are shown, all of them are in the CSV file'
	out = [_text(summary)]
	if res['chart']:
		with open(res['chart'], 'rb') as f:
			out.append(Image(data=f.read(), format='png'))
	return out


@tool
def map_layer(region: dict, variable: str, sensor: str, start: str, end: str, metric: str = 'median',
              temporal: str = 'period', interannual: str = 'mean', season: Optional[List[str]] = None,
              quality: Optional[dict] = None, vmin: Optional[float] = None, vmax: Optional[float] = None,
              collection: Optional[str] = None):
	"""Map of a variable over a region aggregated in time (e.g. the median NDVI of a period): returns the URL of
	its Earth Engine map tiles (XYZ, {z}/{x}/{y}, valid for some hours; add it to QGIS as an XYZ layer), the colour
	ramp and a PNG preview with the outline of the region. temporal: 'period' (METRIC over all the images),
	'annual', 'monthly' or '16-day' (METRIC of each, then INTERANNUAL between the years)."""
	_ready()
	png = _out(f'map_{variable}_{sensor}_{metric}_{start}_{end}', 'png')
	res = services.map_layer(region, variable, sensor, start, end, metric, temporal, interannual, season, quality,
	                         vmin, vmax, thumbnail=png, collection=collection)
	out = [_text(res)]
	with open(png, 'rb') as f:
		out.append(Image(data=f.read(), format='png'))
	return out


@tool
def region_stats(region: dict, variable: str, sensor: str, start: str, end: str, metric: str = 'median',
                 temporal: str = 'period', season: Optional[List[str]] = None, quality: Optional[dict] = None,
                 scale: Optional[float] = None, collection: Optional[str] = None) -> str:
	"""Statistics (mean, std, min, p5, p50, p95, max, number of pixels) over each feature of a region of the map of
	a variable aggregated in time."""
	_ready()
	return _text(services.region_stats(region, variable, sensor, start, end, metric, temporal, season=season,
	                                   quality=quality, scale=scale, collection=collection))


@tool
def export_image_to_drive(region: dict, variable: str, sensor: str, start: str, end: str, metric: str = 'median',
                          temporal: str = 'period', season: Optional[List[str]] = None,
                          quality: Optional[dict] = None, resolution: Optional[float] = None, crs: str = 'auto',
                          folder: str = 'MonitorEO', name: Optional[str] = None,
                          collection: Optional[str] = None) -> str:
	"""Export the map of a variable over a region to a GeoTIFF in a folder of the Google Drive of the Earth Engine
	account (a batch task, without limits of size). resolution: pixel size in metres (default: that of the data);
	crs: 'auto' (UTM zone of the region) or e.g. 'EPSG:25830'. Check it with task_status."""
	_ready()
	return _text(services.export_image(region, variable, sensor, start, end, metric, temporal, season=season,
	                                   quality=quality, resolution=resolution, crs=crs, folder=folder, name=name,
	                                   collection=collection))


@tool
def export_time_series_to_drive(region: dict, variable: str, sensor: str, start: str, end: str,
                                step: str = 'monthly', metric: str = 'mean', stat: str = 'mean',
                                season: Optional[List[str]] = None, quality: Optional[dict] = None,
                                scale: Optional[float] = None, folder: str = 'MonitorEO',
                                name: Optional[str] = None, collection: Optional[str] = None) -> str:
	"""Export a time series (as time_series) to a CSV file in a folder of Google Drive: for long series or many
	regions. Check it with task_status."""
	_ready()
	return _text(services.time_series_to_drive(region, variable, sensor, start, end, step, metric, stat, season,
	                                           quality, scale, folder, name, collection=collection))


@tool
def download_image(region: dict, variable: str, sensor: str, start: str, end: str, metric: str = 'median',
                   temporal: str = 'period', season: Optional[List[str]] = None, quality: Optional[dict] = None,
                   resolution: Optional[float] = None, crs: str = 'auto', clip: bool = True,
                   collection: Optional[str] = None) -> str:
	"""Download the map of a variable over a region to a GeoTIFF on this computer (float32, NoData -9999), computed
	by Earth Engine in tiles: for small regions (up to some million pixels); bigger ones, export_image_to_drive.
	resolution: pixel size in metres (default: that of the data); crs: 'auto' (UTM zone of the region) or e.g.
	'EPSG:25830'. Returns the path of the file and its grid."""
	_ready()
	return _text(services.download_image(region, variable, sensor, start, end, metric, temporal, season=season,
	                                     quality=quality, resolution=resolution, crs=crs, clip=clip,
	                                     path=_out(f'{variable}_{sensor}_{metric}_{start}_{end}', 'tif'),
	                                     collection=collection))


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
	temporal (period, annual, monthly) and interannual, collection and band (other collections), drive_folder.
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
def trend_table(region: dict, variable: str, sensor: str, start: str, end: str, step: str = 'annual',
                metric: str = 'mean', stat: str = 'mean', season: Optional[List[str]] = None,
                quality: Optional[dict] = None, scale: Optional[float] = None, alpha: float = 0.05,
                collection: Optional[str] = None):
	"""Seasonal trends of a variable over each feature of a region:
	for each part of the year (step 'monthly': each month; '16-day': 23 parts of 16 days from 1 January; 'annual':
	the year), the spatial STAT of the METRIC of its images in each year, and the trend of those yearly values:
	Mann-Kendall tau, Z and p-value (significant if p < alpha) and Sen's slope (change per year). Use 8 or more
	years. Writes a CSV and a chart of the yearly values with their Sen lines, and returns the chart."""
	_ready()
	stem = f'trend_{variable}_{sensor}_{step}_{start}_{end}'
	res = services.trend_table(region, variable, sensor, start, end, step, metric, stat, season=season,
	                           quality=quality, scale=scale, alpha=alpha, csv=_out(stem, 'csv'),
	                           chart=_out(stem, 'png'), collection=collection)
	summary = {k: res[k] for k in ('title', 'unit', 'scale', 'csv', 'chart')}
	summary['slope_unit'] = f"{res['unit']} / year"
	summary['trends'] = res['rows']
	out = [_text(summary)]
	if res['chart']:
		out.append(Image(path=res['chart']))
	return out


@tool
def trend_map(region: dict, variable: str, sensor: str, start: str, end: str, step: str = 'annual',
              part: Optional[int] = None, output: str = 'slope', metric: str = 'mean',
              season: Optional[List[str]] = None, quality: Optional[dict] = None, alpha: Optional[float] = None,
              collection: Optional[str] = None):
	"""Map of the trend of a part of the year computed on each pixel (see trend_table): part is the month (1-12)
	with step 'monthly', 1-23 with '16-day', nothing with 'annual'; output 'slope' (Sen, per year), 'tau', 'z',
	'p_value', 'intercept' or 'n' (years with data); alpha (e.g. 0.05) keeps only the significant pixels. Returns
	the URL of its Earth Engine tiles (XYZ, valid for some hours) and a preview."""
	_ready()
	thumb = _out(f'trend_{variable}_{sensor}_{step}_{part}_{output}', 'png')
	res = services.trend_map(region, variable, sensor, start, end, step, part, output, metric, season=season,
	                         quality=quality, alpha=alpha, thumbnail=thumb, collection=collection)
	return [_text(res), Image(path=res['thumbnail'])]


@tool
def download_trend(region: dict, variable: str, sensor: str, start: str, end: str, step: str = 'annual',
                   part: Optional[int] = None, metric: str = 'mean', season: Optional[List[str]] = None,
                   quality: Optional[dict] = None, alpha: Optional[float] = None,
                   resolution: Optional[float] = None, crs: str = 'auto', collection: Optional[str] = None) -> str:
	"""Download the trend of a part of the year on each pixel (see trend_map) to a GeoTIFF on this computer with
	the bands slope, tau, z, p_value, intercept and n. For small regions (Earth Engine computes it in tiles)."""
	_ready()
	return _text(services.download_trend(region, variable, sensor, start, end, step, part, metric, season=season,
	                                     quality=quality, alpha=alpha, resolution=resolution, crs=crs,
	                                     path=_out(f'trend_{variable}_{sensor}_{step}_{part}_{start}_{end}', 'tif'),
	                                     collection=collection))


@tool
def compare_series(region: dict, variable: str, sensor: str, start: str, end: str, other_start: str,
                   other_end: str, step: str = 'monthly', metric: str = 'mean', stat: str = 'mean',
                   season: Optional[List[str]] = None, quality: Optional[dict] = None,
                   scale: Optional[float] = None, collection: Optional[str] = None):
	"""Compare a reference period (start to end) with another (other_start to other_end) over each feature of a
	region: the mean of each part of the year (step 'monthly', '16-day' or 'annual') over the years of each period
	and the difference (other - reference). Writes a CSV and a chart of both
	periods by part of the year, and returns the chart."""
	_ready()
	stem = f'comparison_{variable}_{sensor}_{start}_{end}_{other_start}_{other_end}'
	res = services.compare_series(region, variable, sensor, start, end, other_start, other_end, step, metric, stat,
	                              season=season, quality=quality, scale=scale, csv=_out(stem, 'csv'),
	                              chart=_out(stem, 'png'), collection=collection)
	summary = {k: res[k] for k in ('title', 'unit', 'scale', 'csv', 'chart')}
	summary['comparison'] = res['profile']
	out = [_text(summary)]
	if res['chart']:
		out.append(Image(path=res['chart']))
	return out


@tool
def compare_map(region: dict, variable: str, sensor: str, start: str, end: str, other_start: str, other_end: str,
                metric: str = 'median', temporal: str = 'period', season: Optional[List[str]] = None,
                quality: Optional[dict] = None, collection: Optional[str] = None):
	"""Map of the difference between the variable aggregated over another period (other_start to other_end) and
	over the reference period (start to end), e.g. the median NDVI of 2023 minus that of 2018-2021. Returns the URL
	of its Earth Engine tiles (XYZ, valid for some hours) and a preview."""
	_ready()
	thumb = _out(f'comparison_{variable}_{sensor}_{metric}', 'png')
	res = services.compare_map(region, variable, sensor, start, end, other_start, other_end, metric, temporal,
	                           season=season, quality=quality, thumbnail=thumb, collection=collection)
	return [_text(res), Image(path=res['thumbnail'])]


@tool
def download_comparison(region: dict, variable: str, sensor: str, start: str, end: str, other_start: str,
                        other_end: str, metric: str = 'median', temporal: str = 'period',
                        season: Optional[List[str]] = None, quality: Optional[dict] = None,
                        resolution: Optional[float] = None, crs: str = 'auto',
                        collection: Optional[str] = None) -> str:
	"""Download the comparison of two periods (see compare_map) to a GeoTIFF on this computer with the bands
	difference (other - reference), reference and other. For small regions."""
	_ready()
	return _text(services.download_comparison(
		region, variable, sensor, start, end, other_start, other_end, metric, temporal, season=season,
		quality=quality, resolution=resolution, crs=crs,
		path=_out(f'comparison_{variable}_{sensor}_{metric}_{start}_{end}_{other_start}_{other_end}', 'tif'),
		collection=collection))


@tool
def burn_severity(region: dict, start: str, end: str, other_start: str, other_end: str, sensor: str = 'Sentinel-2',
                  metric: str = 'median', season: Optional[List[str]] = None, quality: Optional[dict] = None,
                  resolution: Optional[float] = None, crs: str = 'auto') -> str:
	"""Burn severity of a fire with the dNBR and the official classes of the USGS (Key & Benson 2006): dNBR = NBR of
	a period before the fire (start to end) minus NBR of a period after it (other_start to other_end), with
	Sentinel-2 (10 m, since 2017) or Landsat (30 m, since 1984). Returns the hectares of each class over each feature
	of the region (unburned, low, moderate-low, moderate-high and high severity, and enhanced regrowth) and the burned
	area (dNBR >= 0.1), writes them to a CSV and downloads a GeoTIFF with the bands dnbr, severity (class -2 to 4),
	nbr_before and nbr_after. Use periods without the fire: e.g. the 3 months before it and the 2-3 months after it
	ends. For small regions (bigger ones: lower resolution)."""
	_ready()
	stem = f'burn_severity_{sensor}_{start}_{end}_{other_start}_{other_end}'
	return _text(services.burn_severity(region, sensor, start, end, other_start, other_end, metric, season=season,
	                                    quality=quality, resolution=resolution, crs=crs, path=_out(stem, 'tif'),
	                                    csv=_out(stem, 'csv')))


@tool
def publish_report(title: str, summary: str, files: List[str], question: Optional[str] = None,
                   answer: Optional[str] = None, method: Optional[str] = None, region: Optional[dict] = None,
                   authors: Optional[List[str]] = None, downloads: Optional[List[str]] = None,
                   report_id: Optional[str] = None, site: Optional[str] = None) -> str:
	"""For the administrators of the viewer of results of MonitorEO: publish an analysis as a report of the static
	web site in the folder site (default: MONITOREO_SITE or ~/MonitorEO/visor). files: the GeoTIFF and CSV files
	written by the other tools (download_trend, download_comparison, download_image, burn_severity, time_series,
	trend_table, compare_series) in the order of the page; their calls are read from the log of this server. Texts in
	Spanish, the language of the viewer: title (e.g. the question of the analysis), summary (the answer in one or two
	sentences), question, answer (the result; paragraphs separated by a blank line), method; region: {"name": ...,
	"wdpa_id": ...}; downloads: other files (PDF, figures). The GeoTIFFs become Cloud Optimized GeoTIFFs and the site
	gets the report, the viewer and its catalogue. It is public only when an administrator deploys the folder (git
	push to the repository of the site, or rsync to its server); `monitoreo serve` shows it on this computer."""
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
