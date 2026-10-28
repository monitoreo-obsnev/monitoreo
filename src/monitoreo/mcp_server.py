"""MCP server of MonitorEO (stdio), for language models: the functions of monitoreo.services as tools.

    monitoreo mcp        (or python -m monitoreo.mcp_server)

It uses the Earth Engine credentials of `earthengine authenticate` and the project of the variable EE_PROJECT (or
the tool connect). Files (CSV tables, PNG charts and maps) are written to the folder MONITOREO_OUTPUT (default:
~/MonitorEO). Works with the MCP Python SDK 1.x (FastMCP) and 2.x (MCPServer).
"""

import datetime as dt
import functools
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

from . import services

OUTPUT = os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO')
MAX_ROWS_SHOWN = 300

INSTRUCTIONS = """MonitorEO (OBSNEV, Universidad de Granada): satellite variables of Google Earth Engine (NDVI, EVI, NDWI,
LSWI, NDSI, NDCI, albedo, land surface temperature, evapotranspiration, LAI, chlorophyll, aerosols) of Sentinel-2,
Landsat and MODIS, with the pixel filters of MonitorEO (clouds, water, snow, aerosols).

Workflow: list_variables (or describe_variable) to choose variable and sensor; find_protected_areas to get the
WDPA ID of a protected area; then time_series (table, CSV and chart), map_layer (map tiles and preview),
region_stats (statistics of a map) or the exports to Google Drive (export_image_to_drive,
export_time_series_to_drive, then task_status). GeoTIFFs on this computer: download_image (one map of a small
region) and download_variables (several variables and metrics on aligned grids over a study area and, at a coarser
pixel size, over its ecoregions: the input variables of a model).

A region is a JSON object with one of: {"wdpa_id": 389011} (or a list of IDs), {"ecoregion_id": 793},
{"ecoregion_at": [lon, lat]}, {"bbox": [west, south, east, north]}, {"point": [lon, lat], "buffer": metres},
{"geojson": <GeoJSON geometry, Feature or FeatureCollection>} or {"file": "<path of a vector file>"}. Several
features give one series per feature. Dates are YYYY-MM-DD; season is ["MM-DD", "MM-DD"] (e.g. summer of each year).
Long series over big regions take minutes: use step "monthly" or "annual", or export_time_series_to_drive."""

server = Server('MonitorEO', instructions=INSTRUCTIONS)


def tool(fn):
	"""Register FN as a tool whose errors reach the client with their message."""
	@functools.wraps(fn)
	def wrapped(*args, **kwargs):
		try:
			return fn(*args, **kwargs)
		except ToolError:
			raise
		except Exception as e:
			raise ToolError(f'{type(e).__name__}: {e}') from e
	return server.tool()(wrapped)


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
def task_status(operation: str) -> str:
	"""State of an export task (PENDING, RUNNING, SUCCEEDED, FAILED, CANCELLED) and its progress, given the operation
	returned by the export tools."""
	_ready()
	return _text(services.task_status(operation))


def main():
	server.run()


if __name__ == '__main__':
	main()
