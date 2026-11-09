"""Assistant of MonitorEO for managers: a chat in the browser, on this computer, with a language model connected to the
MCP server of MonitorEO (monitoreo.mcp_server). The model is, by default, the model of MonitorEO in the cloud, through
its broker (its route /chat, which chooses Gemini or Claude: nothing to install nor any key; the conversation goes to
Google or Anthropic, which do not use it to train their models) or, chosen in Settings, a model of open weights served
by Ollama on this computer (https://ollama.com; monitoreo.engine installs it if needed). The settings saved before the
model of MonitorEO existed keep their model of Ollama. The big models of the cloud get longer instructions (BIG_RULES)
and more of the manual than the small ones of Ollama (SMALL).

    monitoreo assistant [--no-update] [--port 8765] [--no-browser]

The model helps to choose the variable, the sensor, the region and the period of an analysis and calls the tools of
MonitorEO, but it never gets their results: they go to the screen and to the report (monitoreo.report), and the model
only gets a receipt. So it can advise but cannot interpret the results. The tools compute in Google Earth Engine with
the shared account of MonitorEO or, when the user gives their Google Cloud project, with their Google account (who
signs in from the browser, as with `earthengine authenticate`) and that project, which can also export to Google
Drive; the model gets only the text of the conversation. The page shows the EECUs of Earth Engine spent this month
(with the shared account, the research EECUs of this user, only for research; with the user's own, those of their
project, against the quota of its tier) and warns when less than 10 % are left. The settings (project, tier of the
project, the model of MonitorEO or Ollama, address of Ollama, model) are kept in ~/MonitorEO/assistant.json;
cloud_model, if there, asks the broker for one of its models (to compare them).

The page and its API answer only on 127.0.0.1, to the host names of this computer, and the API only with the token of
the address that the assistant opens (other pages of the browser cannot use it).
"""

import asyncio
import contextlib
import datetime as dt
import json
import os
import pathlib
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile

from . import __version__, areas, engine, manual, report, services
from .steps import PERIOD_MAP, UNITS, map_steps

OUTPUT = os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO')
SETTINGS = os.path.join(OUTPUT, 'assistant.json')
RUNNING = os.path.join(OUTPUT, '.assistant')  # port and token of the assistant that is running
LOG = os.path.join(OUTPUT, 'assistant.log')  # the calls of the model and their errors, to find out what went wrong
LAYERS = os.path.join(OUTPUT, 'capas')  # the vector files added by the user, and their list capas.json
LAYER_TYPES = ('.gpkg', '.geojson', '.json', '.kml', '.zip')  # .zip: a shapefile (or another of these) compressed
MAX_LAYER = 100 * 2 ** 20  # bytes
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
DEFAULTS = {'project': os.environ.get('EE_PROJECT', ''), 'provider': 'monitoreo', 'ollama': 'auto',
            'model': 'qwen3:8b', 'context': 16384, 'think': False,
            'eecu_tier': os.environ.get('MONITOREO_EECU_LIMIT') or 'Community'}
PROVIDERS = ('monitoreo', 'ollama')  # the model of MonitorEO (its broker), or a model of Ollama (on this computer)
CLOUD = 'MonitorEO'  # the name of its model in the page until the broker says which one it is
RECOMMENDED = [  # the models of Ollama of the list of the page, the first one by default, with their download in GB
	{'name': 'qwen3:8b', 'gb': 5.2, 'note': 'recommended'},
	{'name': 'qwen3:4b', 'gb': 2.5, 'note': 'faster and lighter; makes more mistakes'},
	{'name': 'gpt-oss:20b', 'gb': 14, 'note': 'for computers with 16 GB of memory or more'},
]
MODEL_GB = {m['name']: m['gb'] for m in RECOMMENDED}
MAX_STEPS = 8  # answers of the model to a message of the user
WAITING = ('Not done: the user has been asked to choose or answer something; wait for their answer and do it '
           'then.')  # the answer of a call that the assistant does not run while the user has to answer
ASK_AND_WAIT = (' Ask the user which one in one sentence and stop there, without calling any tool: the application '
                'waits for their choice.')  # added to the areas found when the user has to choose one
MAX_ADVICE = 8000  # characters of the answer of an advice tool that the model gets
MAX_ROWS_SHOWN = 1000  # of the tables of the page, which shows the first 6 (and the others with a button)
PASSED_ENV = ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'no_proxy', 'SSL_CERT_FILE',
              'REQUESTS_CA_BUNDLE', 'PYTHONPATH', 'GOOGLE_APPLICATION_CREDENTIALS', 'MONITOREO_BROKER')
SWITCH_ACCOUNT = ' In the assistant: press «Use my Google account» and write your Google Cloud project in Settings.'

ADVICE = ('list_variables', 'describe_variable', 'find_protected_areas')  # their answers go to the model
RESULTS = ('time_series', 'region_stats', 'map_layer', 'trend_table', 'trend_map', 'compare_series', 'compare_map',
           'burn_severity', 'download_image', 'download_trend', 'download_comparison',
           'download_variables')  # their answers go only to the user and the report
TASKS = ('export_image_to_drive', 'export_time_series_to_drive', 'task_status')  # answers without values: to both
HIDDEN = ('collection', 'scale', 'vmin', 'vmax', 'crs', 'lang', 'limit', 'quick')  # arguments the model does not see
ALPHA = 0.05  # the trends whose pixels are kept by «Significant pixels only» (Mann-Kendall p < ALPHA)
SIGNIFICANT = '|p<0.05'  # added to the key of a map with only those pixels
AREA_KEYS = ('SITE_ID', 'NAME', 'DESIG', 'DESIG_ENG', 'IUCN_CAT', 'ISO3', 'REP_AREA')  # of the protected areas
_DESIG = (r'(parque (nacional|natural|periurbano)|paraje natural|reserva (natural( concertada)?|de la biosfera)|'
          r'monumento natural|paisaje protegido|espacio natural( protegido)?|zona de especial conservaci[oó]n|zec|zepa|'
          r'lic|national park|natural park|nature park|(natural|nature|biosphere) reserve|natural monument|'
          r'protected landscape|special area of conservation|special protection area|site of community importance|sac|'
          r'spa|sci)')
DESIGNATIONS = (rf'^(el |la |the )?{_DESIG}\b( (de la|de los|de las|del|de|of the|of)\b)?\s*|'
                rf'\s+{_DESIG}$')  # removed from the searches: before the name (Spanish) or after it (English)

TASK_STATES = {'PENDING': 'queued', 'READY': 'queued', 'RUNNING': 'running', 'SUCCEEDED': 'finished',
               'COMPLETED': 'finished', 'FAILED': 'failed', 'CANCELLED': 'cancelled', 'CANCELLING': 'cancelling',
               'UNKNOWN': 'unknown'}
WIKI = 'https://github.com/monitoreo-obsnev/monitoreo/wiki/'
MANUAL_TOOL = {'type': 'function', 'function': {  # answered by the assistant (monitoreo.manual), not by the MCP server
	'name': 'manual',
	'description': 'Searches the manual of MonitorEO (its wiki) for the sections that answer a question about the '
	               'tool: what a variable measures, sensors, dates and resolution, concepts (metrics, filters, trends, '
	               'comparisons, fires), how it is installed or used, frequent problems and the other tools of '
	               'MonitorEO. Returns the sections with their link.',
	'parameters': {'type': 'object', 'properties': {'question': {
		'type': 'string', 'description': 'The question, in the words and the language of the user'}},
		'required': ['question']}}}
OTHER_TOOLS = [  # what the assistant does not do, by the words of the request (without accents), and who does it
	(r'automat|periodic|se repit|repetir|repeat|script|program(ar|acion)|cuaderno|notebook|en lote|\bbatch|schedul|'
	 r'\bcron\b|\b[2-9]\d (parques|espacios|zonas|sitios|regiones|parks|protected areas|areas|sites|regions|zones)',
	 'the Python package or the command line', 'automating computations that repeat or of many regions at once',
	 WIKI + 'Python-package'),
	(r'\ben r\b|\bdesde r\b|paquete de r\b|\bin r\b|\bfrom r\b|\bwith r\b|\br package|rstudio|\bterra\b|ggplot',
	 'the R package', 'doing the computations in R', WIKI + 'R-package'),
	(r'qgis|edit(ar|o) (la |una |mi |mis |las |esta )?capa|digitaliz|mapa para imprimir|maquet|composicion|'
	 r'leyenda del mapa|edit(ing)? (the |a |my |this |these |those )?layers?\b|digiti[sz]|maps? to print|'
	 r'printable map|print(ed)? map|(map|print) layout|map legend',
	 'the QGIS plugin', 'working next to your layers in QGIS, editing them and making maps to print',
	 WIKI + 'QGIS-plugin'),
	(r'sin instalar|en el navegador sin|desde (el|mi) movil|tablet|without install|in the browser without|'
	 r'(from|on) (my|the|a) (mobile|phone|cell)', 'the Earth Engine app',
	 'using MonitorEO in the browser without installing anything', WIKI + 'Earth-Engine-app'),
	(r'publicar|pagina web publica|que lo vea (cualquiera|todo el mundo)|publish|public (web ?page|website|site)|'
	 r'(for|so that) (anyone|everyone|everybody) (can )?(to )?see', 'the results viewer',
	 'publishing reports for anyone to see (its administrators do it)', WIKI + 'Results-viewer'),
]
LABELS = {'manual': 'Looking in the manual of MonitorEO',
          'list_variables': 'Looking at the variables of the catalog',
          'describe_variable': 'Looking at the description of {variable}',
          'find_protected_areas': 'Searching for protected areas named «{text}»'}

RECEIPT_NOTE = 'The result is shown to the user and goes to their report; you only get a receipt, without the values.'
NOTE = '\n\n(Note of the application, not of the user: '  # added to a message of the user (see Assistant.said)

PROMPT = """You are the assistant of MonitorEO-OBSNEV (Global Change Observatory of Sierra Nevada, University of \
Granada) for managers of natural areas. Today is {today}.

What you do:
- You help to choose the variable, the sensor, the region and the period of an analysis, and you run it with the \
compute tools of MonitorEO, which compute in Google Earth Engine with the shared account of MonitorEO or, if the user \
has put their project in Settings, with their Google account.
- You advise on sensors and variables with the guide below and with list_variables and describe_variable.
- You answer questions about MonitorEO (what a variable measures, sensors, dates, resolution, concepts, how each tool \
is installed or used) with the tool manual, which searches its manual.

Rules:
1. You never see the results of the computations: they go to the user's screen and to their report, with their \
chart, their table and their map. When a compute tool answers «Done», say in one sentence what has been computed and \
nothing about its values (not whether they rise or fall, are high or low, nor what they mean). The assistant does show \
charts, tables and maps: if the user asks for one that is computed already, say which result it is in (e.g. «The \
chart is in result 1, in Results, on the right.», said in the user's language); if not, do the computation that gives \
it. Never say that the assistant does not show charts.
2. Do not interpret results, even if asked: say that the assistant does not interpret results and that their \
interpretation is for technical staff, for example of the OBSNEV.
3. For a protected area, always search its ID with find_protected_areas, directly and without asking permission, and \
never make it up. If there are several candidates, ask which one: the user sees the list of the search and can choose \
one in it. When they choose one (their message ends with «WDPA N»), do the computation they asked for with that \
SITE_ID, without asking, even if you did it already with another one.
4. If something essential is missing (variable, place or dates), propose a reasonable option from the guide and ask \
in a single sentence before computing.
5. When you ask the user something (which area, which variable or index, which dates...), end your answer with the \
question and call no tool in it: the application waits for their answer and does not run the computations of an \
answer that asks.
6. Answer in the language of the user's last message (a question in Spanish gets the answer in Spanish, one in \
English in English), {style}
7. {manual_rule}
8. If the user asks for something the assistant cannot do, say so and recommend in one or two sentences the tool of \
MonitorEO that does it, from the list below, with its link: computations that repeat by themselves (each month) or of \
many regions at once, the Python package or the command line; editing layers or making maps to print, the QGIS \
plugin; working in R, the R package; trying it without installing anything, the Earth Engine app. Do not write code or \
installation commands: its page of the wiki explains them.
9. Do not name your internal tools to the user (time_series, find_protected_areas...): say what you do.

How to call the tools:
- Region: a JSON object with one of these forms: {{"wdpa_id": SITE_ID}} (a protected area, with the SITE_ID that \
find_protected_areas returns), {{"ecoregion_at": [lon, lat]}}, {{"bbox": [west, south, east, north]}} or \
{{"point": [lon, lat], "buffer": metres}}.
- Dates: "YYYY-MM-DD"; «since 2018», with no end, is up to today. Season of each year: season ["MM-DD", "MM-DD"], \
e.g. ["06-01", "08-31"] for the summer.
- Sensor: "Sentinel-2", "Landsat" or "Modis". The variable, as in the catalog (NDVI, EVI, NDWI, LST...).
- Filters: the pixels with water and snow are removed; with the NDWI, the NDCI or the Chl-a pass quality \
{{"water": "auto"}}, and with the NDSI quality {{"snow": "auto"}}, so that the filter does not remove what they measure.
- Snow cover frequency (how often there is snow: % of the clear observations with snow): variable "SCF", sensor \
"Landsat", always with metric "mean", also in maps (whose default is the median); its filters are fixed (clouds and water \
are always removed, whatever the quality), so pass no quality. For the snow season of each year, season ["10-01", "05-31"] (it counts in the year in which it starts).
- Elevation and slope (Copernicus DEM GLO-30, 30 m; the slope in degrees): variables "ELEVATION" and "SLOPE", sensor \
"Copernicus". They are fixed layers, without dates: map_layer, region_stats or download_image without start and end; they \
have no time series, trends or comparisons.
- Change over time: time_series (step "monthly" or "annual"; long series over big regions take minutes). Map of a \
period: map_layer; its statistics: region_stats. Interannual value (e.g. the mean of the annual medians): temporal \
"annual" (or "monthly"), metric that of each year ("median") and interannual that between the years ("mean"); \
temporal takes no other values. Trend over the years (Mann-Kendall and Sen's slope, 8 years or more): trend_table, \
with step "monthly" for that of each month; it gives the table and the chart of the area and the map of the trend on \
each pixel (of each month, in the page), so trend_map is not needed. Compare a period with a reference one: \
compare_series and compare_map. Fire: burn_severity.
- Download as GeoTIFF (for a GIS): a map with download_image, a trend with download_trend and a comparison with \
download_comparison; for small regions or, in big ones, with resolution (metres of pixel) coarser than that of the \
data. Several variables on aligned grids (for a model): download_variables, first with dry_run. Big regions at full \
resolution: export_image_to_drive (or export_time_series_to_drive for a long series), which export to Google Drive; \
then task_status with the operation they return tells whether they have finished. The exports to Google Drive need \
the user's account: with the shared account, tell them to sign in with their Google account and put their project in \
Settings.

Other tools of MonitorEO (the same functions and the same results):
- Earth Engine app: in the browser, without installing anything nor an Earth Engine account; maps, series, trends, \
comparisons and fires, also over a drawn polygon. {wiki}Earth-Engine-app
- QGIS plugin: the same without programming, next to the user's layers, with values to query on the map and maps to \
print in QGIS. {wiki}QGIS-plugin
- Python package and command line: automate computations (scripts, notebooks, many regions or dates). \
{wiki}Python-package and {wiki}Command-line
- R package: analysis in R with sf, terra or ggplot2. {wiki}R-package
- MCP server: the same computations with Claude or another AI assistant. {wiki}MCP-server
- Results viewer: publish reports on a website for anyone to see (only its administrators). {wiki}Results-viewer

Guide of sensors:
- Sentinel-2: pixel of 10-20 m, an image every 5 days or so, since 2017. For small areas or areas with detail \
(plots, edges, ponds) and recent periods. It has no data before 2017: for a period that starts before, propose \
Landsat, or Sentinel-2 only since 2017.
- Landsat: pixel of 30 m, an image every 8-16 days, since 1984. For long series and trends of decades. Between May \
2012 and March 2013 there are no Landsat images in the catalog.
- MODIS: pixel of 250-1000 m, daily images or composites of 8-16 days, since 2000. For big regions, seasonality and \
the variables that only MODIS gives (evapotranspiration, LAI, aerosols).
- MonitorEO discards the pixels with clouds, water, snow or aerosols, depending on the variable. In high mountains \
snow leaves few valid pixels in winter for the vegetation indices.
- Burn severity of a fire: burn_severity with Sentinel-2 or Landsat; period before, the 3 months before the fire; \
period after, the 2-3 months after it ends. It gives the dNBR and its classes; only if the user asks for the RBR \
(Relativized Burn Ratio), index "RBR": a continuous index, without classes.

Variables of the catalog (sensors, pixel and first year):
{variables}{guide}"""
SMALL = {  # rules 6 and 7 for the small models of Ollama: short answers, which they keep right
	'style': 'brief and clear.',
	'manual_rule': 'For questions about MonitorEO, consult manual and answer with what it says, in five sentences at most '
	               'and with the link of the page. You may add a brief general explanation (for example, what a '
	               'vegetation index measures), but do not make up facts about MonitorEO: if the manual does not say '
	               'it, say so. Use only the links that manual gives you or those of the list of tools below.',
	'guide': ''}
BIG_RULES = {  # for the big models of the cloud, which can explain more: how to use the assistant and the concepts
	'style': 'clear and to the point: a computation in one or two sentences; an explanation as long as it needs, in short '
	         'paragraphs or a list of steps. Plain text with lists and bold only: no tables, no LaTeX nor math notation '
	         '(write a formula as (NIR - red) / (NIR + red)).',
	'manual_rule': 'For questions about MonitorEO (its variables, sensors, concepts, the assistant or its other tools), '
	               'consult manual first and answer with what it says, with the link of the page. Explain in plain words '
	               'for managers who are not specialists in remote sensing: what it is, why it matters for their '
	               'question and its limits; a short example of a protected area helps. You may add general knowledge of '
	               'remote sensing and ecology (how an index works, what clouds or the size of the pixel change), saying '
	               'that it is general, but do not make up facts about MonitorEO (its options, dates, sensors or '
	               'buttons): if the manual does not say it, say so. Use only the links that manual gives you or those of '
	               'the list of tools below.',
	'guide': """

How to help the user:
- When a request is vague, propose the variable, sensor, period and step with a reason in one sentence (Sentinel-2 \
for a plot of a few hectares, Landsat for thirty years, MODIS for a whole mountain range) and ask before computing.
- When the user asks how to do something in the assistant, give the steps on its page (below) in order, with the \
names of its buttons in bold. Do not add details of the page that are neither below nor in the manual.
- Never tell the user to write options, code or JSON: you set the options of a computation yourself (for example the \
filters) and say in words what you did.
- The page is in English: write the names of its buttons, boxes and tabs as they are on it (**Upload study area**, \
**Query pixel**, **Create report**...), with a translation in brackets if the user writes in another language.
- When a computation is done, say where the result is and, if it helps, in one sentence how to look at it (Query \
pixel on the map, How it is computed in its card, Create report), never its values.
- Warn about the usual pitfalls when they apply: in high mountains snow and clouds leave few valid pixels in winter; \
an index of one sensor is not equal to that of another (do not mix sensors in a series or a trend); a MODIS pixel \
mixes land covers; a trend needs 8 years or more; the NDSI and the NDWI measure what the snow and water filters remove; \
the thresholds of the snow cover frequency (SCF) were set in Sierra Nevada.

The page of the assistant (to explain how to use it):
- On the left, the conversation; on the right, the results, with the map at the top (in a narrow window, the tabs \
Conversation and Results). The user types in the box at the bottom of the conversation (Enter sends) or clicks an \
example; below the box are the buttons Upload study area, Create report (N) and New request.
- Settings: the Earth Engine account (the shared account of MonitorEO; or «Use my Google account» and their Google \
Cloud project, needed to export to Google Drive) and the language model (the model of MonitorEO in the cloud, or a \
model on the computer with Ollama).
- The bar of research EECUs: what the user has spent this month of the compute of Earth Engine (with the shared \
account, 25 EECU-hours a month, only for research); Check asks again.
- Protected areas: the search shows the designations with that name; when several fit, the assistant asks which one \
and waits, and clicking one in the list computes with it (clicking another later repeats the computation with that \
one).
- Upload study area (or dragging a GeoPackage, GeoJSON, KML or zipped shapefile onto the page): then its polygons are \
used by the name of the layer, each one with its own series or row.
- Each result is a card: the chart or the map, the first rows of the table (See the N rows), See on the map, How it \
is computed (what was really computed), Download CSV or Download TIF, and In the report.
- The map: Map chooses the map of a result; Date, the map of each year, month or 16 days of it; Base map and Opacity; \
Query pixel gives the value of a pixel and its time series (Keep the series as a result); in trend maps, Significant \
pixels only (p < 0.05); Add this view to the report saves what is seen.
- Create report (N): a single HTML file, saved in the folder MonitorEO/informes, with the results marked In the \
report (their sheet, chart or map), to print or save as PDF. New request starts another conversation; the files stay \
in the folder MonitorEO."""}
BIG_MANUAL = {'k': 5, 'max_chars': 3000}  # sections of the manual for the big models (3 of 1800 for the small ones)
BIG_ADVICE = 16000  # characters of the answer of an advice tool for the big models (MAX_ADVICE for the small ones)


# The model -----------------------------------------------------------------------------------------------------------

class ModelError(RuntimeError):
	pass


def instructions(today=None, big=False):
	"""The instructions of the model, with the variables of the catalog: those of the big models of the cloud
	(BIG_RULES) or those of the small models of Ollama (SMALL)."""
	return PROMPT.format(today=(today or dt.date.today()).isoformat(), variables=variables_text(), wiki=WIKI,
	                     **(BIG_RULES if big else SMALL))


def variables_text():
	"""The variables of the catalog, a line each: name, group and, for each sensor, pixel size and first year."""
	variables = {}
	for v in services.list_variables(lang='en'):
		years = re.findall(r'(?<!\d)(?:19|20)\d\d(?!\d)', v['dates'])
		var = variables.setdefault(v['variable'], {'name': v['name'], 'group': v['group'], 'sensors': {},
		                                           'two_periods': v.get('two_periods', False)})
		s = var['sensors'].setdefault(v['sensor'], {'m': v['resolution_m'], 'first': None, 'last': None, 'now': False})
		s['m'] = min(s['m'], v['resolution_m'])
		if years:
			s['first'] = min(s['first'] or '9999', min(years))
			s['last'] = max(s['last'] or '0', max(years))
		s['now'] = s['now'] or bool(re.search(r'now|hoy', v['dates'], re.I))
	lines = []
	for code, var in variables.items():
		sensors = '; '.join(f"{'MODIS' if name == 'Modis' else name} {s['m']:g} m since {s['first'] or '?'}"
		                    + ('' if s['now'] or not s['last'] else f" until {s['last']}")
		                    for name, s in var['sensors'].items())
		only = ' Only burn_severity with index "RBR" (two periods).' if var.get('two_periods') else ''
		lines.append(f"- {code}: {var['name'].strip().rstrip('.')}; group {var['group']}. {sensors}.{only}")
	return '\n'.join(lines)


def model_tools(tools):
	"""The tools of the MCP server (as listed by it, in JSON) that the model may call, as Ollama wants them, without
	the arguments in HIDDEN."""
	out = []
	for t in tools:
		if t['name'] not in ADVICE + RESULTS + TASKS:
			continue
		schema = json.loads(json.dumps(t.get('inputSchema') or {'type': 'object', 'properties': {}}))
		props = schema.setdefault('properties', {})
		for k in HIDDEN:
			props.pop(k, None)
		schema['required'] = [k for k in schema.get('required', []) if k in props]
		description = (t.get('description') or '').strip()
		if t['name'] in RESULTS:
			description += ' ' + RECEIPT_NOTE
		out.append({'type': 'function', 'function': {'name': t['name'], 'description': description,
		                                             'parameters': schema}})
	return out


SINCE = re.compile(r'\b(?:desde\s+(?:el\s+)?(?:año\s+)?(?:(?:\d{1,2}\s+de\s+)?[a-záéíóú]+\s+(?:de|del)\s+)?|'
                   r'since\s+(?:the\s+)?(?:year\s+)?(?:(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?)?[a-z]+\s+'
                   r'(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?)?)((?:19|20)\d{2})\b'
                   r'|\bfrom\s+(?:[a-z]+\s+)?((?:19|20)\d{2})\s+on(?:wards?)?\b', re.I)  # «desde 2018», «since 2018»
YEAR = re.compile(r'\b(?:19|20)\d{2}\b')
UNTIL = re.compile(r'\b(?:hasta|until|till|through)\b', re.I)


def open_end(args, said, today=None):
	"""ARGS up to today when the last message of the user that gives a year (SAID, all of them) asks «desde 2018»
	(«since 2018») with no end, and the model ends before: small models end it at the end of a year, or at today's
	day of the year asked for."""
	today = (today or dt.date.today()).isoformat()
	if not isinstance(args.get('end'), str) or args['end'] >= today:
		return args
	text = next((t for t in reversed(said) if YEAR.search(t)), '')
	since = SINCE.search(text)
	if since and len(YEAR.findall(text)) == 1 and not UNTIL.search(text):
		return {**args, 'end': today}
	return args


def dated(args):
	"""Whether a map of ARGS has a period: not those of the fixed layers without dates (elevation, slope)."""
	return bool(args.get('start') and args.get('end'))


def main_label(m, args):
	"""The name in the page of the map M of a result of ARGS: its interannual value, its whole period or its last
	year (a fixed layer: that it has no dates)."""
	a = m['args']
	if not dated(a):
		return 'Fixed layer, without dates'
	period = report.period_text(a['start'], a['end'])
	if m['tool'] == 'trend_map':
		if a.get('part'):
			return next((s['label'] for s in map_steps('trend_map', a) if s['part'] == a['part']), f"Part {a['part']}")
		return f"Annual trend: Sen's slope of the values of each year ({period})"
	if a.get('temporal') in UNITS:
		stat = report.STATS.get(a.get('interannual') or 'mean', a.get('interannual'))
		return f"Interannual value: {stat} of the {UNITS[a['temporal']]} ({period})"
	return f'Last year of the period ({period})' if a['start'] > args['start'] else f'Whole period ({period})'


def fix_args(name, args, tools):
	"""The arguments of a call of the model as the tool wants them: without those it does not know or in HIDDEN, and
	with the objects and lists that small models give as JSON text decoded."""
	if isinstance(args, str):
		args = json.loads(args or '{}')
	schema = next((t['function']['parameters'] for t in tools if t['function']['name'] == name), {})
	props = schema.get('properties', {})
	out = {}
	for k, v in (args or {}).items():
		if k not in props or v is None or v == '':
			continue
		if isinstance(v, str) and _wants(props[k], ('object', 'array')):
			try:
				v = json.loads(v)
			except ValueError:
				pass
		out[k] = v
	if out.get('temporal') in TEMPORAL_ALIASES:  # small models write what they want: «interannual»
		out['temporal'] = TEMPORAL_ALIASES[out['temporal']]
	return out


TEMPORAL_ALIASES = {'interannual': 'annual', 'interanual': 'annual', 'yearly': 'annual', 'year': 'annual',
                    'anual': 'annual', 'month': 'monthly', 'mensual': 'monthly', 'total': 'period', 'all': 'period'}


def _wants(schema, types):
	kinds = [schema.get('type')] + [s.get('type') for s in schema.get('anyOf', [])]
	return any(k in types for k in kinds)


def search_name(text):
	"""The name of a protected area without its designation ('Parque Nacional de Doñana', 'Doñana National Park' ->
	'Doñana'): WDPA has it in another field, and the name with it is often that of another area (here, the Ramsar
	site)."""
	text = str(text).strip()
	name = re.sub(DESIGNATIONS, '', text, flags=re.I).strip()
	if name != text:  # 'the Doñana National Park'
		name = re.sub(r'^the\s+', '', name, flags=re.I)
	return name or text


def designated(area, said):
	"""Whether the designation of the protected AREA (in WDPA: DESIG, and in English DESIG_ENG, without what goes
	in brackets) is in SAID, the messages of the user in lower case."""
	return any(d and d in said for d in (re.sub(r'\s*\(.*?\)', '', str(area.get(k) or '')).strip().lower()
	                                     for k in ('DESIG', 'DESIG_ENG')))


def areas_text(areas, question=''):
	"""The protected areas found, for the model: a line each, with the SITE_ID next to its designation (small models
	misread lists in JSON), first those whose designation is in the question of the user."""
	q = question.lower()
	matches = [designated(a, q) for a in areas]
	ranked = [a for a, m in zip(areas, matches) if m] + [a for a, m in zip(areas, matches) if not m]
	lines = [f"- SITE_ID {a['SITE_ID']}: {a.get('NAME', '')}, {a.get('DESIG') or 'no designation'}"
	         + (f", {report._num(a['REP_AREA'])} km²" if a.get('REP_AREA') is not None else '')
	         + (' (its designation matches the request)' if i < sum(matches) else '')
	         for i, a in enumerate(ranked)]
	return (f'{len(areas)} protected areas; the user sees this list and can choose one in it:\n' + '\n'.join(lines)
	        if areas else 'No protected area with that name: ask the user for another name or a layer.')


def task_text(tool, text):
	"""What the user reads of an answer of the exports to Google Drive or of task_status."""
	try:
		r = json.loads(text)
	except ValueError:
		return text
	if tool == 'task_status':
		state = TASK_STATES.get(r.get('state'), r.get('state'))
		progress = f" ({round(100 * r['progress'])}%)" if isinstance(r.get('progress'), (int, float)) else ''
		return f'Export to Google Drive: {state}{progress}.' + (f" {r['error']}" if r.get('error') else '')
	return (f"Export to Google Drive running: {r.get('file', '')} in the folder {r.get('folder', '')} of your Google "
	        'Drive. It takes from minutes to hours; ask «has the export finished?» to know.')


def fix_links(text, question=''):
	"""TEXT of the model with its links to the wiki that do not exist (small models make them up) replaced by their
	page, if it exists, or else by the section of the manual that answers QUESTION best (in its language)."""
	links = set(re.findall(re.escape(WIKI) + r'[^\s)\]>"\'«»]*[^\s)\]>"\'«».,;:]', text))
	if not links:
		return text
	secs = manual.sections()
	pages = {s['name'] for s in secs} | set(manual.PAGES) | set(manual.ENGLISH.values())  # also those to download
	urls = {s['url'] for s in secs}
	best = None
	for link in sorted(links, key=len, reverse=True):
		page = urllib.parse.unquote(link[len(WIKI):].split('#')[0])
		if page in pages and ('#' not in link or link in urls):
			continue
		if best is None:
			found = manual.search(question, k=1) if question else []
			best = found[0]['url'] if found else WIKI
		text = text.replace(link, WIKI + page if page in pages else best)
	return text


NOT_PLACES = {'ndvi', 'evi', 'ndwi', 'lswi', 'ndsi', 'ndci', 'nbr', 'lai', 'lst', 'et', 'le', 'albedo', 'arsl', 'chl',
              'sentinel', 'landsat', 'modis', 'google', 'earth', 'engine', 'drive', 'monitoreo', 'monitoreo-obsnev',
              'geotiff', 'csv', 'pdf', 'qgis', 'wdpa', 'obsnev', 'quiero', 'dame', 'haz', 'calcula', 'compara', 'serie',
              'mapa', 'evolucion', 'tendencia', 'como', 'que', 'cual', 'cuales', 'donde', 'cuando', 'descarga',
              'exporta', 'muestra', 'necesito', 'puedes', 'hola', 'gracias', 'si', 'no', 'vale', 'usa', 'busca',
              'i', 'want', 'give', 'show', 'compute', 'calculate', 'compare', 'series', 'map', 'trend', 'how', 'what',
              'which', 'where', 'when', 'download', 'export', 'need', 'can', 'could', 'please', 'hello', 'hi',
              'thanks', 'thank', 'yes', 'ok', 'okay', 'use', 'search', 'find', 'get', 'make', 'tell', 'list', 'is',
              'are', 'do', 'does', 'annual', 'monthly', 'yearly', 'daily', 'evolution', 'english', 'spanish',
              'espanol', 'ingles', 'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
              'september', 'october', 'november', 'december'}
PLACE = re.compile(r"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñü'-]*(?:(?:,?\s+(?:(?:de|del|y|of|and)(?:\s+(?:la|las|los|el|the))?|"
                   r"la|las|los|el|the)\s+|,\s+|\s+)[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñü'-]*)*")
NOT_PLACE = re.compile(r"\b(?:" + '|'.join(sorted(NOT_PLACES, key=len, reverse=True)) + r")\b[\w-]*|\S*\d\S*", re.I)
EDGES = re.compile(r"^(?:(?:de|del|la|las|los|el|y|of|the|and)\s+|[\s,])+|"
                   r"(?:\s+(?:de|del|la|las|los|el|y|of|the|and)|[\s,])+$", re.I)


def place_in(text):
	"""The name of a place in a message of the user ('NDVI mensual en el Parque Nacional de Sierra Nevada' ->
	'Parque Nacional de Sierra Nevada', 'Monthly NDVI in the Sierra Nevada National Park' -> 'Sierra Nevada National
	Park'): the longest run of words in capitals (with de, del, la, of, the, commas... inside), cut at the names of
	variables, sensors and programs and at the words that start requests; one that only starts a sentence, if there is
	no other."""
	text = str(text)
	plain = manual._ascii(text)  # the same length, without accents
	runs = []
	for m in PLACE.finditer(text):
		cuts = [(x.start(), x.end()) for x in NOT_PLACE.finditer(plain, m.start(), m.end())]
		for a, b in zip([m.start()] + [e for _, e in cuts], [s for s, _ in cuts] + [m.end()]):
			name = EDGES.sub('', text[a:b])
			if not name[:1].isupper() or not re.sub(DESIGNATIONS, '', name + ' x', flags=re.I).strip(' x'):
				continue  # nothing, or only a designation (Parque Nacional)
			at = text.index(name, a)
			first = at == 0 or re.search(r'[.!?¿¡:;]\s*$', text[:at])
			n = len(re.findall(r'(?:^|\s)[A-ZÁÉÍÓÚÑ]', name))
			runs.append((not (first and n == 1), n, name))
	return max(runs)[2] if runs else None


def other_tool(text):
	"""(name, what for, link) of the other tool of MonitorEO for a request that the assistant does not do, or None."""
	t = manual._ascii(str(text).lower())
	return next(((name, what, url) for pattern, name, what, url in OTHER_TOOLS if re.search(pattern, t)), None)


def asks(text):
	"""Whether the answer TEXT of the model ends by asking the user something (its last sentence is a question): then
	the assistant does not run the computations of that answer and waits for the user's answer."""
	return re.sub(r'[\s*_)\]»"\'`]+$', '', str(text or '')).endswith('?')


def must_choose(areas, said, last=''):
	"""Whether the user has to choose among the protected AREAS found (with 'match' when their designation is in
	SAID): several and none, or more than one, with the designation asked for, and none of their SITE_IDs in the
	LAST message of the user (they have chosen it already, e.g. «... WDPA 389011»)."""
	if len(areas) < 2 or any(re.search(rf'\b{a.get("SITE_ID")}\b', last) for a in areas):
		return False
	return sum(1 for a in areas if a.get('match', designated(a, said))) != 1


def receipt(n, title):
	"""What the model gets of a result: that it was computed and shown, without its values."""
	return (f'Done: «{title}» has been computed in Google Earth Engine and the assistant shows it to the user, with its '
	        f'chart, its table or its map, as result {n} (in Results, on the right). You do not see its values: do not '
	        'describe or interpret them.')


def ollama(base, path, payload=None, timeout=600):
	"""Answer (JSON) of the API of Ollama at BASE (e.g. http://localhost:11434)."""
	req = urllib.request.Request(base.rstrip('/') + path, method='POST' if payload is not None else 'GET',
	                             data=json.dumps(payload).encode() if payload is not None else None,
	                             headers={'Content-Type': 'application/json'})
	try:
		with urllib.request.urlopen(req, timeout=timeout) as r:
			return json.loads(r.read().decode())
	except urllib.error.HTTPError as e:
		body = e.read().decode(errors='replace')
		try:
			body = json.loads(body).get('error', body)
		except ValueError:
			pass
		raise ModelError(body) from e
	except (urllib.error.URLError, OSError) as e:
		raise ModelError(f'no connection with Ollama at {base}: open it or install it from https://ollama.com '
		                 f'({e})') from e


def chat_model(settings, system, messages, tools):
	"""The next message of the model of the settings: {'role', 'content', 'tool_calls'} (and 'model', the one of
	MonitorEO that answered)."""
	if settings.get('provider') != 'ollama':
		return chat_cloud(system, messages, tools, settings.get('cloud_model'))
	return chat_ollama(settings, system, messages, tools)


def chat_cloud(system, messages, tools, model=None):
	"""The next message of the model of MonitorEO (or MODEL, one of those of the broker), through its broker (its route
	/chat, with the anonymous ID of this installation), as chat_ollama gives it: the arguments of the calls as objects
	and, as they came, the other fields of the calls and of the message (the model wants them back: the thought
	signatures of Gemini, the thinking of Claude), with the model that answered."""
	body = {'messages': openai_messages(system, messages), 'tools': tools, 'temperature': 0.2}
	if model:
		body['model'] = model
	try:
		answer = services._broker('/chat', body=body, timeout=240, user=services.user_id())
	except services.BrokerError as e:
		text = str(e) if e.code else f'the language model of MonitorEO does not answer now ({e})'
		raise ModelError(text + ('' if e.code in ('day', 'user') else
		                         ' (in Settings you can use a model on this computer instead)')) from e
	except Exception as e:  # no connection
		raise ModelError(f'no connection with the language model of MonitorEO ({type(e).__name__}: {e}); in '
		                 'Settings you can use a model on this computer instead') from e
	choices = answer.get('choices') or [{}]
	message = dict(choices[0].get('message') or {})
	calls = []
	for call in message.get('tool_calls') or []:
		function = dict(call.get('function') or {})
		args = function.get('arguments')
		if isinstance(args, str):
			try:
				args = json.loads(args or '{}')
			except ValueError:
				args = {}
		calls.append({**call, 'function': {**function, 'arguments': args if isinstance(args, dict) else {}}})
	out = {k: v for k, v in message.items() if k not in ('tool_calls', 'content', 'role', 'refusal')}
	out.update(role='assistant', content=re.sub(r'<think>.*?</think>', '', message.get('content') or '',
	                                            flags=re.S).strip())
	if calls:
		out['tool_calls'] = calls
	if answer.get('model'):
		out['model'] = answer['model']
	return out


def model_title(model):
	"""The name of a model of MonitorEO for the page: gemini-3.8-flash, Gemini 3.8 Flash; claude-sonnet-5-5, Claude
	Sonnet 5.5."""
	words = []
	for part in str(model or '').split('-'):
		if words and re.fullmatch(r'\d+(\.\d+)?', part) and re.fullmatch(r'\d+(\.\d+)?', words[-1]):
			words[-1] += '.' + part
		elif part:
			words.append(part if re.fullmatch(r'\d+(\.\d+)?', part) else part.capitalize())
	return ' '.join(words) or CLOUD


def openai_messages(system, messages):
	"""SYSTEM and the MESSAGES of the conversation (as Ollama takes them) as the API of OpenAI takes them: each call of
	the model with its id and its arguments as JSON text, and each answer of a tool with the id of its call (that of the
	same name, else the next one); a call without answer gets one, and an answer without call goes as a note."""
	out, pending, n = [{'role': 'system', 'content': system}], [], 0

	def unanswered():
		out.extend({'role': 'tool', 'tool_call_id': i, 'content': 'No answer.'} for i, _ in pending)
		pending.clear()

	for m in messages:
		role = m.get('role')
		if role == 'tool':
			name, wanted = m.get('tool_name'), m.get('tool_call_id')
			match = (next((p for p in pending if p[0] == wanted), None) or
			         next((p for p in pending if p[1] == name), None) or (pending[0] if pending else None))
			if match:
				pending.remove(match)
				out.append({'role': 'tool', 'tool_call_id': match[0], 'content': m.get('content') or ''})
			else:
				out.append({'role': 'user',
				            'content': f"{NOTE.strip()}the tool {name} answered: {m.get('content') or ''})"})
			continue
		unanswered()
		if role == 'assistant' and m.get('tool_calls'):
			calls = []
			for call in m['tool_calls']:
				n += 1
				function = dict(call.get('function') or {})
				args = function.get('arguments')
				function['arguments'] = args if isinstance(args, str) else json.dumps(args or {}, ensure_ascii=False)
				c = {**call, 'id': call.get('id') or f'call_{n}', 'type': 'function', 'function': function}
				calls.append(c)
				pending.append((c['id'], function.get('name')))
			out.append({**{k: v for k, v in m.items() if k not in ('tool_calls', 'content')},
			            'content': m.get('content') or '', 'tool_calls': calls})
		else:
			out.append({k: v for k, v in m.items() if k in ('role', 'content', 'extra_content')})
	unanswered()
	return out


def chat_ollama(settings, system, messages, tools):
	"""The next message of the model of Ollama (/api/chat): {'role', 'content', 'tool_calls'}."""
	payload = {'model': settings['model'], 'messages': [{'role': 'system', 'content': system}] + messages,
	           'tools': tools, 'stream': False,
	           'options': {'num_ctx': int(settings.get('context') or 16384), 'temperature': 0.2}}
	if settings.get('think') is not None:
		payload['think'] = bool(settings['think'])
	try:
		answer = ollama(settings['ollama'], '/api/chat', payload)
	except ModelError as e:
		text = str(e).lower()
		if 'think' in payload and 'think' in text:  # a model without thinking
			del payload['think']
			answer = ollama(settings['ollama'], '/api/chat', payload)
		elif 'not found' in text:
			raise ModelError(f"the model {settings['model']} is not installed: download it") from e
		else:
			raise
	message = answer.get('message') or {}
	message['content'] = re.sub(r'<think>.*?</think>', '', message.get('content') or '', flags=re.S).strip()
	return message


def default_model(current, installed):
	"""The model to use: CURRENT if it is installed, else the first of RECOMMENDED that is (other models may not use
	tools), else CURRENT, to download it."""
	if not installed or current in installed:
		return current
	return next((m['name'] for m in RECOMMENDED if m['name'] in installed), current)


def check_update():
	"""{'available', 'current', 'latest'}: whether GitHub has another version than the installed one, and both
	commits; None for a local copy (a clone, an editable install) or without connection."""
	from . import update
	if update.local_copy():
		return None
	inst = update.installed()
	try:
		sha = update.latest()
	except (OSError, ValueError):
		return None
	commit = inst[1] if inst else None
	return {'available': commit != sha, 'current': (commit or '')[:7], 'latest': sha[:7]}


def models(settings):
	"""Names of the models installed in Ollama, or None if it does not answer."""
	try:
		return [m['name'] for m in ollama(settings['ollama'], '/api/tags', timeout=3).get('models', [])]
	except ModelError:
		return None


# The assistant -------------------------------------------------------------------------------------------------------

def load_settings():
	"""The settings of the assistant; those saved before the model of MonitorEO (without provider) keep their model of
	Ollama."""
	try:
		with open(SETTINGS, encoding='utf-8') as f:
			saved = json.load(f)
	except (OSError, ValueError):
		return dict(DEFAULTS)
	return {**DEFAULTS, 'provider': 'ollama', **saved}


def save_settings(settings):
	os.makedirs(OUTPUT, exist_ok=True)
	with open(SETTINGS, 'w', encoding='utf-8') as f:
		json.dump(settings, f, ensure_ascii=False, indent=1)


def load_layers():
	try:
		with open(os.path.join(LAYERS, 'capas.json'), encoding='utf-8') as f:
			layers = json.load(f)
		return {k: v for k, v in layers.items() if os.path.exists(v['path'])}
	except (OSError, ValueError, KeyError, AttributeError):
		return {}


def save_layers(layers):
	os.makedirs(LAYERS, exist_ok=True)
	with open(os.path.join(LAYERS, 'capas.json'), 'w', encoding='utf-8') as f:
		json.dump(layers, f, ensure_ascii=False, indent=1)


def layer_text(layer):
	"""'3 polygons, 125.3 ha' (and the field of their names)."""
	n = layer['features']
	return f"{n} polygon{'s' if n != 1 else ''}, {report._num(layer['area_ha'])} ha" + \
		(f", names in the field {layer['name_field']}" if layer.get('name_field') else '')


def _in_zip(path):
	"""The path of GDAL of the vector file inside a zip file (a shapefile, or a GeoPackage, GeoJSON or KML)."""
	with zipfile.ZipFile(path) as z:
		names = [n for n in z.namelist() if not n.startswith('__MACOSX/')]
	for ext in ('.shp', '.gpkg', '.geojson', '.json', '.kml'):
		inside = next((n for n in names if n.lower().endswith(ext)), None)
		if inside:
			return f'/vsizip/{path}/{inside}'
	raise ValueError('the .zip has no shapefile, GeoPackage, GeoJSON or KML')


def signed_in():
	"""Whether this computer has the credentials of Earth Engine of `earthengine authenticate`."""
	import ee
	return os.path.exists(ee.oauth.get_credentials_path())


REVOKE = 'https://oauth2.googleapis.com/revoke'  # where Google revokes a token of the user (OAuth 2.0)


def sign_out():
	"""Log out of the Google account of Earth Engine on this computer: revoke its refresh token at Google (if Google
	can be reached) and delete the credentials of `earthengine authenticate`, which the other tools of this computer
	(QGIS plugin, Python, R, command line, `earthengine`) use too. Returns whether there were credentials."""
	import ee
	path = ee.oauth.get_credentials_path()
	if not os.path.exists(path):
		return False
	try:
		with open(path, encoding='utf-8') as f:
			token = json.load(f).get('refresh_token')
		if token:
			import requests
			requests.post(REVOKE, data={'token': token}, timeout=15)
	except Exception:  # without the file, this computer is signed out anyway
		pass
	os.remove(path)
	return True


class Assistant:
	"""A conversation with the model and the MCP server of MonitorEO, and its results. Each message of the user is
	answered by a task of its own (start), whose events are kept (emit) and sent to every page that follows them
	(follow): the answer goes on without the page, and a page opened again shows the whole conversation."""

	def __init__(self, settings=None):
		self.settings = settings or load_settings()
		self.session, self.tools, self.system = None, [], instructions()
		self.task = None  # that of the message being answered
		self.events, self.offset, self.changed = [], 0, asyncio.Event()  # those of the conversation, from seq offset
		self.loop, self.closing = None, False  # that of the web server; closing: the pages stop following
		self.layers = load_layers()
		self.cloud_model = None  # the model of MonitorEO that answered last
		self.engine = engine.Engine()
		self.model_checked = False  # whether the model of the settings was checked against those installed
		self.eecu = None  # the last answer of eecu_usage (the EECUs of Earth Engine spent this month), or {'error'}
		self.eecu_warned = set()  # (project, account, month) whose warning of few EECUs left was shown
		self.quit = None  # stops the web server (see run)
		self.restart = False  # whether run starts it again (after an update)
		self.update_info = None  # see check_update
		self.in_window = False  # whether the page is in a window of its own (closing it closes the assistant)
		self.reset()

	def base(self):
		"""Address of the Ollama in use: that of the settings or, with 'auto', that of the engine (None if there is
		none yet)."""
		s = self.settings.get('ollama') or 'auto'
		return self.engine.url if s == 'auto' else s

	def cloud(self):
		"""Whether the model is that of MonitorEO, through its broker (else, one of Ollama)."""
		return self.settings.get('provider') != 'ollama'

	def model_name(self):
		"""The name of the model for the page: that of MonitorEO that answered last (or the one asked for), or that of
		Ollama."""
		if self.cloud():
			return model_title(self.cloud_model or self.settings.get('cloud_model')) if (
				self.cloud_model or self.settings.get('cloud_model')) else CLOUD
		return self.settings['model']

	def advice_limit(self):
		"""Characters of the answer of an advice tool (or of the manual) that the model gets."""
		return BIG_ADVICE if self.cloud() else MAX_ADVICE

	def model_settings(self):
		return {**self.settings, 'ollama': self.base()}

	def reset(self):
		self.messages, self.results, self.names, self.question, self.pixels = [], [], {}, None, []
		self.call_id = None  # the id of the call of the model being run (cloud), for the answer of its tool
		self.waiting = False  # whether the user has to choose or answer before anything is computed (see chat)

	def running(self):
		"""Whether a message is being answered."""
		return bool(self.task and not self.task.done())

	def emit(self, event):
		"""Keep an event of the conversation and wake the pages that follow it."""
		self.events.append({**event, 'seq': self.offset + len(self.events)})
		changed, self.changed = self.changed, asyncio.Event()
		changed.set()

	async def follow(self, since=0, ping=15):
		"""The events of the conversation from the number SINCE on, and then the new ones as they come (a ping every
		PING seconds without any, so that a page that is not there any more is noticed)."""
		while not self.closing:
			changed = self.changed  # before reading the events: one emitted meanwhile sets it
			for e in self.events[max(since - self.offset, 0):]:
				yield e
				since = e['seq'] + 1
			if self.closing:
				return
			try:
				await asyncio.wait_for(changed.wait(), ping)
			except asyncio.TimeoutError:
				yield {'type': 'ping'}

	def end_streams(self):
		"""Let the pages stop following the conversation (the web server closes); from any thread."""
		def end():
			self.closing = True
			self.changed.set()
		if self.loop and not self.loop.is_closed():
			self.loop.call_soon_threadsafe(end)

	def start(self, text):
		"""Answer a message of the user in a task of its own."""
		if self.running():
			raise ValueError('wait until the previous request ends')

		async def answer():
			self.emit({'type': 'user', 'text': text})
			try:
				async for e in self.chat(text):
					self.emit(e)
			except Exception as e:  # the conversation goes on
				self.emit({'type': 'error', 'text': f'The assistant has failed: {type(e).__name__}: {e}'})
			finally:
				self.emit({'type': 'done'})
		self.task = asyncio.create_task(answer())

	def new_conversation(self):
		"""Forget the conversation and its results (their files stay); the pages get a reset."""
		if self.running():
			raise ValueError('wait until the previous request ends')
		self.reset()
		self.offset += len(self.events)
		self.events = []
		self.emit({'type': 'reset'})

	@contextlib.asynccontextmanager
	async def connected(self):
		"""Start the MCP server of MonitorEO (this same version) and keep the session with it."""
		from mcp import ClientSession, StdioServerParameters
		from mcp.client.stdio import stdio_client
		env = {k: os.environ[k] for k in PASSED_ENV if os.environ.get(k)}
		env.update({'MONITOREO_OUTPUT': OUTPUT, 'PYTHONIOENCODING': 'utf-8'})
		if self.settings.get('project'):
			env['EE_PROJECT'] = self.settings['project']
		args = (['-s'] if sys.flags.no_user_site else []) + ['-m', 'monitoreo.mcp_server']
		async with stdio_client(StdioServerParameters(command=sys.executable, args=args, env=env)) as (read, write):
			async with ClientSession(read, write) as session:
				await session.initialize()
				listed = await session.list_tools()
				self.tools = model_tools([_json(t) for t in listed.tools]) + [MANUAL_TOOL]
				self.session = session
				try:
					yield
				finally:
					self.session = None

	async def call(self, name, args):
		"""Call a tool of the MCP server: (error or None, texts, images as data: URLs)."""
		if not self.session:
			raise RuntimeError('the MCP server of MonitorEO is not running: close the assistant and open it again')
		res = _json(await self.session.call_tool(name, args))
		content = res.get('content') or []
		texts = [_without_eecu_warning(c['text']) for c in content if c.get('type') == 'text']
		images = [f"data:{c.get('mimeType') or 'image/png'};base64,{c['data']}" for c in content
		          if c.get('type') == 'image']
		error = (texts[0] if texts else 'error') if res.get('isError') else None
		return error, texts, images

	async def connect(self, project):
		"""Use this Google Cloud project (empty: the shared account of MonitorEO); returns the answer of the MCP
		server."""
		self.settings['project'] = project.strip()
		save_settings(self.settings)
		self.eecu = None
		if self.settings['project'] and not signed_in():
			return 'Project saved: sign in with your Google account to use it'
		error, texts, _ = await self.call('connect', {'project': self.settings['project']})
		if error:
			raise RuntimeError(re.sub(r'^\w+Error: ', '', error))
		return texts[0] if texts else ''

	async def eecu_events(self, refresh=False):
		"""The events of the EECUs of Earth Engine spent this month: one for the bar of the page and, the first time
		that less than 10 % are left in a month, the warning (with the shared account: switch to your own)."""
		if self.not_ready() or not self.session:
			return []
		args = {'lang': 'en', 'refresh': refresh}
		if self.settings.get('project'):
			args['limit'] = str(self.settings.get('eecu_tier') or 'Community')
		try:
			error, texts, _ = await self.call('eecu_usage', args)
			usage = None if error else json.loads(texts[0])
		except Exception as e:  # the MCP server stopped
			error = f'{type(e).__name__}: {e}'
		if error:
			self.eecu = {'error': re.sub(r'^[A-Za-z]+Error: ', '', error)}
			return [{'type': 'eecu', 'usage': self.eecu}]
		self.eecu = usage
		events = [{'type': 'eecu', 'usage': usage}]
		key = (usage['project'], usage['account'], usage['month'])
		if usage.get('warning') and key not in self.eecu_warned:
			self.eecu_warned.add(key)
			events.append({'type': 'eecu_warning', 'text': usage['warning'] +
			               (SWITCH_ACCOUNT if usage['account'] == 'shared' else '')})
		return events

	def not_ready(self):
		"""Why the tools cannot compute yet, or None."""
		if self.settings.get('project') and not signed_in():
			return ('before computing with your project, sign in with your Google account (button «Use my Google '
			        'account») or leave the project empty to compute with the shared account of MonitorEO')
		return None

	async def chat(self, text):
		"""Answer a message of the user: yields the events for the page (see the module)."""
		said = text
		hint = other_tool(text)
		if hint:  # small models often miss it: the page says it, and the model gets a note
			name, what, url = hint
			yield {'type': 'other_tool', 'name': name, 'what': what, 'url': url}
			text += (f'{NOTE}the assistant does not do this; it is done with {name} of MonitorEO, for {what}: {url}. '
			         "Say it in one or two sentences with the link, in the language of the user's words above, without "
			         'code or names of tools.)')
		self.messages.append({'role': 'user', 'content': text})
		self.question = self.question or said
		self.waiting = False
		for _ in range(MAX_STEPS):
			yield {'type': 'status', 'text': f'The model ({self.model_name()}) is thinking…'}
			try:
				if not self.cloud() and not self.base():
					raise ModelError('the engine of the models is missing: install it in Settings')
				message = await asyncio.to_thread(chat_model, self.model_settings(), self.system_prompt(),
				                                  self.messages, self.tools)
				self.cloud_model = message.get('model') or self.cloud_model
			except ModelError as e:
				yield {'type': 'error', 'text': f'Language model: {e}'}
				return
			calls = message.get('tool_calls') or []
			message['content'] = await asyncio.to_thread(fix_links, message.get('content') or '', said)
			self.messages.append({'role': 'assistant', 'content': message['content'],
			                      **({'tool_calls': calls} if calls else {}),
			                      **({'extra_content': message['extra_content']} if message.get('extra_content') else {})})
			if message['content']:
				yield {'type': 'assistant', 'text': message['content']}
			if not calls:
				return
			# the user has to answer first: after a question of the model, its computations do not run; after a search
			# whose areas the user has to choose from (self.waiting), neither do the computations that follow, and the
			# model answers once more only to ask (none of the calls of that answer run)
			held, asking = self.waiting, asks(message['content'])
			for call in calls:
				self.call_id = call.get('id')
				function = call.get('function') or {}
				try:
					if held or ((asking or self.waiting) and function.get('name') in RESULTS + TASKS):
						self._tool_message(function.get('name'), WAITING)
						continue
					async for event in self.run_tool(function):
						yield event
				finally:
					self.call_id = None
			if held or asking:
				return
		yield {'type': 'error', 'text': 'I have stopped: too many steps for a single message. Ask for it in a more '
		                                'concrete way, in parts.'}

	async def run_tool(self, call):
		"""Run a call of the model: the answers of the advice tools go to the model, those of the others only to the
		user (a card on the page and a result for the report) and the model gets a receipt."""
		name = call.get('name')
		if name == 'manual':
			async for event in self.ask_manual(call.get('arguments')):
				yield event
			return
		if name not in ADVICE + RESULTS + TASKS:
			self._tool_message(name, f'Error: there is no tool {name}.')
			return
		try:
			args = fix_args(name, call.get('arguments'), self.tools)
			if name == 'find_protected_areas' and args.get('text'):
				args['text'] = search_name(args['text'])
			args = self.with_layer(args)
			if name in RESULTS + TASKS:
				args = open_end(args, self.said())
		except ValueError as e:
			self._tool_message(name, f'Error: {e}.')
			return
		if name == 'list_variables':
			args['lang'] = 'en'  # hidden from the model
		if name in RESULTS + TASKS and self.unknown_areas(args) and not self.not_ready():
			async for event in self.known_areas(name, args):
				if 'args' in event:
					args = event['args']
				else:
					yield event
			if args is None:
				return
		tool = name  # the tool computed: that of the call, but the trend over an area instead of its map
		if name == 'trend_map' and not ('point' in (args.get('region') or {}) and not args['region'].get('buffer')):
			tool = 'trend_table'  # its table and chart (Sen and Mann-Kendall of each part, for the whole area) and the
			args = {k: v for k, v in args.items() if k not in ('part', 'output', 'alpha')}  # map of each pixel, too
		title = self.titled(tool, args)
		if name in RESULTS + TASKS:
			problem = self.not_ready()
			if problem:
				yield {'type': 'error', 'text': problem[0].upper() + problem[1:] + '.'}
				self._tool_message(name, f'Error: not computed; {problem}.')
				return
		if name in RESULTS:
			yield {'type': 'running', 'text': f'Computing in Google Earth Engine: {title}…',
			       'facts': _facts(tool, args, None, self.all_names())}
		elif name in TASKS:
			yield {'type': 'status', 'text': ('Checking the export' if name == 'task_status' else
			                                  'Starting the export to Google Drive') + '…'}
		else:
			yield {'type': 'status', 'text': LABELS[name].format(**{k: args.get(k, '') for k in ('variable', 'text')})
			                                 + '…'}
		try:
			error, texts, images = await self.call(tool, args)
		except Exception as e:  # the MCP server stopped
			error, texts, images = f'{type(e).__name__}: {e}', [], []
		if error:
			what = f'The computation «{title}»' if name in RESULTS else f'The request {name}'
			yield {'type': 'error', 'text': f"{what} has failed: {re.sub(r'^[A-Za-z]+Error: ', '', error)}"}
			self._tool_message(name, f'Error: {error}')
			return
		if name in ADVICE:
			text = '\n'.join(texts)
			if name == 'find_protected_areas':
				found = self._remember_names(text)
				if found is not None:
					said = self.user_text().lower()
					shown = [{**a, 'match': designated(a, said)} for a in found]
					yield {'type': 'areas', 'query': args.get('text', ''),
					       'areas': sorted(shown, key=lambda a: not a['match'])}
					text = areas_text(found, said)
					if must_choose(shown, said, self.said()[-1] if self.said() else ''):
						self.waiting = True
						text += ASK_AND_WAIT
			self._tool_message(name, text[:self.advice_limit()])
			return
		if name in TASKS:
			text = '\n'.join(texts)
			yield {'type': 'notice', 'text': task_text(name, text)}
			self._tool_message(name, text[:self.advice_limit()])
			return
		try:
			result = json.loads(texts[0]) if texts else {}
		except ValueError:
			result = {'text': texts[0]}
		if not images and isinstance(result, dict) and str(result.get('file', '')).endswith('.tif'):
			preview = await asyncio.to_thread(report.tif_preview, result['file'], result.get('palette'),
			                                  result.get('min'), result.get('max'))
			images = [preview] if preview else []
		item = {'id': len(self.results) + 1, 'tool': tool, 'args': args, 'result': result,
		        'image': images[0] if images else None, 'title': title}
		self.results.append(item)
		yield {'type': 'result', **self.card(item)}
		self._tool_message(name, receipt(item['id'], item['title']))
		for event in await self.eecu_events():
			yield event
		if tool in PERIOD_MAP:
			yield {'type': 'status', 'text': 'Preparing the map of the period in Google Earth Engine…'}
			event = await self.period_map(item)
			if event:
				yield event

	async def period_map(self, item):
		"""The map of the variable over the period of a result over regions, for the map of the page: the area, and
		the value and series of each pixel; the maps of each of its steps are made when the page asks for them
		(step_map). That of region_stats is the map of its statistics; that of the others, the median of the last year
		of the period. With the colours of the catalog: Earth Engine takes minutes to draw the median of years of
		images over a big area, or to compute its colours. The event for the page, or None if Earth Engine cannot
		make it (the result is there anyway)."""
		a = item['args']
		args = {k: a[k] for k in ('region', 'variable', 'sensor', 'start', 'end', 'season', 'quality', 'collection')
		        if a.get(k) is not None}
		tool = 'map_layer'
		if item['tool'] == 'trend_table':  # the trend of the values of each year on each pixel
			tool = 'trend_map'
			args.update(step='annual', metric=a.get('metric') or 'mean')
		elif item['tool'] == 'region_stats':
			args.update({k: a[k] for k in ('metric', 'temporal', 'interannual') if a.get(k) is not None})
		else:
			end = dt.date.fromisoformat(args['end'][:10])
			year_before = end.replace(year=end.year - 1, day=min(end.day, 28) if end.month == 2 else end.day)
			args.update(start=max(args['start'], (year_before + dt.timedelta(days=1)).isoformat()), metric='median')
		try:
			error, texts, _ = await self.call(tool, {**args, 'quick': True})  # tiles only, in seconds
			result = json.loads(texts[0]) if not error and texts else {}
		except Exception as e:
			error, result = str(e), {}
		if not isinstance(result, dict) or not result.get('url'):
			_log({'tool': tool, 'call': args, 'answer': f'(map of the result {item["id"]}) {error}'})
			return None
		item['map'] = {'tool': tool, 'args': args, 'result': result, 'title': self.titled(tool, args)}
		return {'type': 'map', 'id': item['id'], **self.map_card(item['map']), **self.steps_card(item),
		        'title': item['title']}  # in the list of maps, that of the result

	def steps_card(self, item):
		"""What the page offers of the maps of each step of the result ITEM (see map_steps): {'main', 'steps'}."""
		_, m = self.map_of(item['id'])
		item.setdefault('steps', map_steps(item['tool'], item['args']))
		return {'main': main_label(m, item['args']), 'steps': [{k: s[k] for k in ('key', 'label')} for s in item['steps']],
		        'steps_label': 'Part of the year' if m['tool'] == 'trend_map' else 'Date'}

	async def step_map(self, rid, key, significant=False):
		"""The map of the step KEY of the result RID (see map_steps; '': the map of the result), made the first time
		with the colours of the map of the result, so that they can be compared; of a trend with SIGNIFICANT, only its
		pixels with Mann-Kendall p < ALPHA. What the page shows of it, with the key that names it."""
		item, main = self.map_of(rid)
		maps = item.setdefault('maps', {})
		significant = significant and main['tool'] == 'trend_map'
		name = key + (SIGNIFICANT if significant else '')
		if not name:
			return {'key': '', **self.map_card(main)}
		if name not in maps:
			step = next((s for s in item.get('steps') or [] if s['key'] == key), None)
			if key and not step:
				raise ValueError('that map does not exist')
			a = item['args']
			if not key:  # the map of the result
				tool, args = main['tool'], dict(main['args'])
			elif 'part' in step:  # the trend of a part of the year
				tool, args = 'trend_map', {**main['args'], 'step': a.get('step'), 'part': step['part']}
			else:
				tool = 'map_layer'
				args = {k: a[k] for k in ('region', 'variable', 'sensor', 'quality', 'collection') if a.get(k) is not None}
				args.update(start=step['start'], end=step['end'], metric=a.get('metric') or 'median')
			if significant:
				args['alpha'] = ALPHA
			r = main['result']
			error, texts, _ = await self.call(tool, {**args, 'vmin': r.get('min'), 'vmax': r.get('max'), 'quick': True})
			if error:
				raise RuntimeError(re.sub(r'^[A-Za-z]+Error: ', '', error))
			maps[name] = {'tool': tool, 'args': args, 'result': json.loads(texts[0]), 'title': self.titled(tool, args)}
		return {'key': name, **self.map_card(maps[name])}

	async def ask_manual(self, args):
		"""Answer a call of the tool manual with the sections of the wiki that answer its question; the user sees
		their links."""
		try:
			args = json.loads(args) if isinstance(args, str) else (args or {})
		except ValueError:
			args = {}
		question = str(args.get('question') or args.get('pregunta') or '').strip()
		said = (self.said() or [question])[-1]  # its language is that of the pages: small models translate questions
		lang = manual.language(said)
		query = question if manual.language(question) == lang else f'{question} {said}'
		yield {'type': 'status', 'text': LABELS['manual'] + '…'}
		found = await asyncio.to_thread(_search_manual, query, lang, **(BIG_MANUAL if self.cloud() else {}))
		if found:
			yield {'type': 'sources', 'sources': [{'title': f"{s['page']} › {s['title']}" if s['title'] != s['page']
			                                       else s['page'], 'url': s['url']} for s in found]}
			text = 'Sections of the manual of MonitorEO (answer with them and give the link):\n\n' + '\n\n'.join(
				f"## {s['page']} › {s['title']} ({s['url']})\n{s['text']}" for s in found)
		else:
			text = 'The manual has nothing about that (or it could not be downloaded): tell the user.'
		self._tool_message('manual', text[:self.advice_limit()])

	def card(self, item):
		"""What the page shows of a result."""
		tool, args, result = item['tool'], item['args'], item['result']
		table = report.item_table(tool, result, args)
		card = {'id': item['id'], 'title': item['title'], 'image': item['image'],
		        'facts': _facts(tool, args, result, self.all_names()) + report.view_facts(item), 'table': None,
		        'files': [], 'legend': None, 'references': [], 'credits': []}
		try:  # what to cite with it (its references never stop the page)
			cited = report.item_references(tool, args, result)
			card['references'] = [{'citation': r['citation'], 'url': r.get('url')} for r in cited['references']]
			card['credits'] = cited['credits']
		except Exception:
			pass
		if table:
			labels, rows = table
			card['table'] = {'labels': labels, 'rows': rows[:MAX_ROWS_SHOWN], 'more': max(0, len(rows) - MAX_ROWS_SHOWN)}
		if isinstance(result, dict):
			if result.get('palette'):
				card['legend'] = {k: result.get(k) for k in ('min', 'max', 'palette')}
				card['legend']['unit'] = report.unit_text(result.get('unit'))
			for k in ('csv', 'file', 'readme'):
				if isinstance(result.get(k), str):
					card['files'].append({'name': os.path.basename(result[k]), 'url': _file_url(result[k]),
					                      'path': result[k]})
			if result.get('url') and result.get('bounds') and not item.get('view'):  # tiles: the interactive map
				shown = self.map_card(item)
				card.update(map=shown['map'], heading=shown['heading'])
				card.update(self.steps_card(item))
		return card

	def heading(self, m):
		"""The title over the map M on the page: that of the map (its own period, season and region) with the full name
		of its variable, e.g. «Map of Normalized Difference Vegetation Index (NDVI, Sentinel-2), 2024 · Doñana (Parque
		Nacional)»; the select of the maps keeps the shorter title of the result."""
		title, a = self.titled(m['tool'], m['args']), m['args']
		entry = report._entry(a.get('variable'), a.get('sensor')) if a.get('variable') else None
		if not entry or not entry.get('name'):
			return title
		sensor = report.SENSORS.get(a.get('sensor'), a.get('sensor') or '')
		return title.replace(f"{a['variable']} ({sensor})", f"{entry['name']} ({a['variable']}, {sensor})", 1)

	def map_card(self, m):
		"""What the map of the page shows of the map M (a result with tiles, or the map of the period of one)."""
		result = m['result']
		out = {'title': m['title'], 'heading': self.heading(m), 'legend': None,
		       'map': {'url': result['url'], 'bounds': result['bounds'],
		               'pixel': m['tool'] in ('map_layer', 'trend_map'),  # with the value of the pixel
		               'trend': m['tool'] == 'trend_map'}}  # with «Significant pixels only»
		if not dated(m['args']):  # a fixed layer (elevation, slope): the value of a pixel, without its time series
			out['map']['series'] = False
		if result.get('palette'):
			out['legend'] = {**{k: result.get(k) for k in ('min', 'max', 'palette')},
			                 'unit': report.unit_text(result.get('unit'), per_year='/ year' in str(result.get('unit')))}
		return out

	def map_of(self, rid, key=None):
		"""(result RID, its map: {'tool', 'args', 'result', 'title'}): the result itself if it has tiles, or the map
		of its period (see period_map); with KEY, the map of that step (see step_map)."""
		item = next((r for r in self.results if r['id'] == rid), None)
		if item and key:
			if key not in item.get('maps', {}):
				raise ValueError('that map does not exist')
			return item, item['maps'][key]
		if item and item.get('map'):
			return item, item['map']
		if not item or not isinstance(item['result'], dict) or not item['result'].get('url'):
			raise ValueError('that result has no map')
		return item, item

	async def pixel(self, rid, lon, lat, key=None):
		"""Click on the map of the result RID: the value of the map at the point (maps of map_layer) and the time
		series of its pixel over the period of the map, computed in Earth Engine (the model takes no part). The series
		can be kept as a result (keep_pixel, with its key)."""
		item, m = self.map_of(rid, key)
		a, point = item['args'], {'point': [round(lon, 6), round(lat, 6)]}
		base = {k: a[k] for k in ('variable', 'sensor', 'season', 'quality') if a.get(k) is not None}
		unit = str(m['result'].get('unit'))
		out = {'lon': lon, 'lat': lat, 'value': None, 'unit': report.unit_text(unit, per_year='/ year' in unit),
		       'label': 'value'}
		if not dated(a):  # a fixed layer (elevation, slope): its value at the point, and no time series
			error, texts, _ = await self.call('region_stats', {**base, 'region': point})
			if error:
				raise RuntimeError(re.sub(r'^[A-Za-z]+Error: ', '', error))
			stats = json.loads(texts[0]) if texts else []
			rows = stats.get('rows') if isinstance(stats, dict) else stats
			return {**out, 'value': rows[0].get('mean') if rows else None}
		start, end = min(a['start'], a.get('other_start') or a['start']), max(a['end'], a.get('other_end') or a['end'])
		if m['tool'] == 'trend_map':  # the trend at the pixel: Mann-Kendall and Sen of its part of the year
			ma = m['args']
			error, texts, _ = await self.call('trend_table', {
				**base, 'region': point, 'start': ma['start'], 'end': ma['end'], 'step': ma.get('step') or 'annual',
				'metric': ma.get('metric') or 'mean'})
			trend = json.loads(texts[0]) if not error and texts else {}
			row = next((r for r in trend.get('trends') or [] if not ma.get('part') or r.get('part') == ma['part']), {})
			out.update(value=row.get('slope'), p_value=row.get('p_value'), label="Sen's slope")
		elif m['tool'] == 'map_layer':
			ma = m['args']
			error, texts, _ = await self.call('region_stats', {
				**base, 'region': point, 'start': ma['start'], 'end': ma['end'], 'metric': ma.get('metric') or 'median',
				'temporal': ma.get('temporal') or 'period'})
			stats = json.loads(texts[0]) if not error and texts else []
			rows = stats.get('rows') if isinstance(stats, dict) else stats
			out['value'] = rows[0].get('mean') if rows else None
		days = (dt.date.fromisoformat(end[:10]) - dt.date.fromisoformat(start[:10])).days
		step = a.get('step') if a.get('step') in UNITS else a.get('temporal') if a.get('temporal') in UNITS else \
		       '16-day' if days <= 400 else 'monthly' if days <= 6 * 366 else 'annual'  # that of the result, if any
		args = {**base, 'region': point, 'start': start, 'end': end, 'step': step}
		error, texts, images = await self.call('time_series', args)
		if error:
			raise RuntimeError(re.sub(r'^[A-Za-z]+Error: ', '', error))
		result = json.loads(texts[0])
		title = f"{step[0].upper() + step[1:]} time series of {a.get('variable', '')} at the pixel {lat:.5f}, {lon:.5f}"
		self.pixels.append({'tool': 'time_series', 'args': args, 'result': result,
		                    'image': images[0] if images else None, 'title': title})
		return {**out, 'key': len(self.pixels) - 1, 'title': title, 'image': images[0] if images else None,
		        'n': len(result.get('rows') or [])}

	def keep_pixel(self, key):
		"""Keep the series of a pixel (see pixel) as a result, for the report; returns its number."""
		item = {**self.pixels[int(key)], 'id': len(self.results) + 1}
		self.results.append(item)
		self.emit({'type': 'result', **self.card(item)})
		return item['id']

	async def snapshot(self, rid, view):
		"""Keep the view of the interactive map of the result RID (VIEW: bounds, zoom, base, opacity, marker) as a
		result, for the report; returns its number."""
		_, m = self.map_of(rid, view.get('key'))
		image = await asyncio.to_thread(report.map_view, [float(v) for v in view['bounds']], int(view['zoom']),
		                                m['result']['url'], view.get('base') or 'osm',
		                                float(view.get('opacity', 0.85)), view.get('marker'))
		new = {'id': len(self.results) + 1, 'tool': m['tool'], 'args': m['args'], 'image': image,
		       'result': {k: v for k, v in m['result'].items() if k != 'thumbnail'},
		       'title': f"{m['title']} (map view)",
		       'view': {'bounds': view['bounds'], 'base': view.get('base') or 'osm'}}
		self.results.append(new)
		self.emit({'type': 'result', **self.card(new)})
		return new['id']

	async def refresh_map(self, rid, key=None):
		"""Ask again for the tiles of the map of the result RID, or of its step KEY (those of Earth Engine expire after
		some hours)."""
		_, m = self.map_of(rid, key)
		args, result = m['args'], m['result']
		if m['tool'] in ('map_layer', 'trend_map'):  # only the tiles, with the same colours
			args = {**args, 'vmin': result.get('min'), 'vmax': result.get('max'), 'quick': True}
		error, texts, _ = await self.call(m['tool'], args)
		if error:
			raise RuntimeError(re.sub(r'^[A-Za-z]+Error: ', '', error))
		result['url'] = json.loads(texts[0])['url']
		return result['url']

	def write_report(self, title, ids=None, tables=()):
		"""Write the report of the results IDS (default: all), with the tables of values of those in TABLES, and
		return its path."""
		items = [{**r, 'table': r['id'] in tables} for r in self.results if ids is None or r['id'] in ids]
		if not items:
			raise ValueError('there are no results for the report')
		return report.write(items, title=title or self.question, question=self.question,
		                    project=self.settings.get('project'), shared=not self.settings.get('project'),
		                    names=self.all_names())

	def system_prompt(self):
		"""The instructions of the model (those of the big models of the cloud or those of the small ones of Ollama),
		with the layers of the user."""
		system = self.system
		if self.cloud():
			if not getattr(self, 'system_big', None):
				self.system_big = instructions(big=True)
			system = self.system_big
		if not self.layers:
			return system
		return system + '\n\nStudy areas of the user (layers of polygons on their computer), with the region that ' \
		                     'uses them; each polygon gives its own series or row:\n' + \
		       '\n'.join(f'- {k} ({layer_text(v)}): region {{"layer": "{k}"}}' for k, v in self.layers.items())

	def all_names(self):
		"""The names of the regions for the user: protected areas (by WDPA ID) and layers (by file)."""
		return {**{v['file']: f'Study area «{k}» ({layer_text(v)})' for k, v in self.layers.items()}, **self.names}

	def titled(self, tool, args):
		"""The title of a result, with the name of its region (results of the same thing in other areas differ) and
		the part of the year of a trend map."""
		region, title = self.region_name(args), _title(tool, args)
		if tool == 'trend_map' and args.get('part'):
			label = next((s['label'] for s in map_steps(tool, args) if s['part'] == args['part']), '')
			title += f" ({re.sub(r'^(Tendencia del?|Trend of( the)?)\s+', '', label, flags=re.I).strip()})" if label else ''
		if tool == 'trend_map' and args.get('alpha'):
			title += f", significant pixels only (p < {args['alpha']:g})"
		return title + (f' · {region}' if region else '')

	def region_name(self, args):
		"""A short name of the region of ARGS: the protected area, the study area, the pixel..."""
		region = args.get('region') if isinstance(args.get('region'), dict) else args.get('area')
		if not isinstance(region, dict):
			return ''
		if 'wdpa_id' in region:
			ids = region['wdpa_id'] if isinstance(region['wdpa_id'], list) else [region['wdpa_id']]
			return '; '.join(self.names.get(str(i), f'WDPA {i}') for i in ids)
		key = next((k for k, v in self.layers.items() if v['file'] == region.get('file')), None)
		return f'study area «{key}»' if key else report.region_text(region, self.all_names())

	def said(self):
		"""The messages of the user, without the notes of the application (see chat)."""
		return [m['content'].split(NOTE)[0] for m in self.messages if m['role'] == 'user']

	def user_text(self):
		return ' '.join(self.said())

	def unknown_areas(self, args):
		"""The WDPA IDs of ARGS that come neither from find_protected_areas nor from the user: small models copy them
		from the examples or make them up."""
		region = args.get('region') or args.get('area')
		ids = region.get('wdpa_id') if isinstance(region, dict) else None
		if ids is None:
			return []
		said = set(re.findall(r'\d+', self.user_text()))
		return [i for i in (ids if isinstance(ids, list) else [ids]) if str(i) not in self.names and str(i) not in said]

	async def find_areas(self, text):
		"""Search the protected areas of TEXT (without its designation): (event for the page or None, the areas found
		with 'match' when their designation is in the messages of the user, text for the model)."""
		query = search_name(text)
		error, texts, _ = await self.call('find_protected_areas', {'text': query})
		if error:
			return None, [], f'Error: {error}'
		found = self._remember_names('\n'.join(texts))
		if found is None:
			return None, [], '\n'.join(texts)
		said = self.user_text().lower()
		shown = sorted(({**a, 'match': designated(a, said)} for a in found),
		               key=lambda a: not a['match'])
		return {'type': 'areas', 'query': query, 'areas': shown}, shown, areas_text(found, said)

	async def known_areas(self, name, args):
		"""ARGS with WDPA IDs that are known (see unknown_areas): when the model gives others, the assistant searches
		the place that the user named and uses the area of the designation asked for, if there is just one; else the
		model gets the areas found (and the user sees them) and yields None. An async generator of the events, the
		last one {'args': ...}."""
		unknown = self.unknown_areas(args)
		if not unknown:
			yield {'args': args}
			return
		place = place_in(self.user_text())
		found, text = [], ''
		if place:
			yield {'type': 'status', 'text': LABELS['find_protected_areas'].format(text=search_name(place)) + '…'}
			event, found, text = await self.find_areas(place)
			if event:
				yield event
		key = 'region' if isinstance(args.get('region'), dict) else 'area'
		matches = [a for a in found if a['match']]
		if found and not self.unknown_areas(args):  # the ID of the model was among them
			yield {'args': args}
		elif len(unknown) == 1 and not isinstance(args[key]['wdpa_id'], list) and (len(matches) == 1 or len(found) == 1):
			yield {'args': {**args, key: {**args[key], 'wdpa_id': (matches or found)[0]['SITE_ID']}}}
		else:
			if found and must_choose(found, self.user_text().lower(), self.said()[-1] if self.said() else ''):
				self.waiting = True
			self._tool_message(name, (
				f'Error: the wdpa_id {", ".join(map(str, unknown))} does not exist. The application has searched '
				f'«{search_name(place)}»: {text}\nUse the SITE_ID of the area that the user asks for and call {name} '
				'again; if several are possible, ask the user which one (they see the list).') if found else (
				'Error: that wdpa_id does not exist. Search the area yourself by its name with find_protected_areas '
				f'and call {name} again with its SITE_ID; do not ask the user for it.'))
			yield {'args': None}

	def with_layer(self, args):
		"""ARGS with a region {"layer": name} (or {"capa": name}) as the file of that study area; also the ways small
		models give it: the name alone, {"study_area": name}, "layer parcelas", "capa parcelas"..."""
		arg = 'area' if 'area' in args and 'region' not in args else 'region'  # area: download_variables
		region = args.get(arg)
		if isinstance(region, dict) and (region.get('capa') or region.get('layer')):
			key = str(region.get('capa') or region.get('layer'))
		elif isinstance(region, dict) and not any(k in region for k in areas.REGION_KEYS):
			names = [v for v in region.values() if isinstance(v, str)]
			key = names[0] if len(names) == 1 else None
		else:
			key = region if isinstance(region, str) else None
		if key is None:
			return args
		key = re.sub(r'^(la |el |the )?(capa|[aá]rea de estudio|layer|study area)\s+', '', key.strip(),
		             flags=re.I).strip('«»"\' ')
		layer = self.layers.get(key) or next((v for k, v in self.layers.items() if key.lower() in (
			k.lower(), v['original'].lower(), os.path.splitext(v['original'])[0].lower())), None)
		if not layer:  # small models copy the examples ({"layer": "name"}): the one the user named, if only one
			said = self.user_text().lower()
			named = [v for k, v in self.layers.items() if re.search(r'\b' + re.escape(k.lower()) + r'\b', said)]
			layer = named[0] if len(named) == 1 else None
		if not layer:
			raise ValueError(f'there is no study area «{key}»; the study areas are: '
			                 f'{", ".join(self.layers) or "none"} (region: {{"layer": "name"}})')
		return {**args, arg: {'file': layer['file'],
		                      **({'name_field': layer['name_field']} if layer.get('name_field') else {})}}

	def add_layer(self, filename, data):
		"""Keep a vector file (its name and content) in LAYERS as a layer that the model can use as a region."""
		stem, ext = os.path.splitext(os.path.basename(filename))
		if ext.lower() not in LAYER_TYPES:
			raise ValueError('format not supported: use a GeoPackage (.gpkg), a GeoJSON, a KML or a shapefile '
			                 'compressed in a .zip')
		if len(data) > MAX_LAYER:
			raise ValueError(f'the layer takes more than {MAX_LAYER // 2 ** 20} MB')
		name = base = re.sub(r'[^a-z0-9_-]+', '_', stem.lower()).strip('_') or 'layer'
		k = 1
		while name in self.layers:
			k += 1
			name = f'{base}_{k}'
		os.makedirs(LAYERS, exist_ok=True)
		path = os.path.join(LAYERS, name + ext.lower())
		with open(path, 'wb') as f:
			f.write(data)
		try:
			src = _in_zip(path) if ext.lower() == '.zip' else path
			info = areas.describe_file(src)
		except ImportError as e:
			os.remove(path)
			raise ValueError('reading layers needs GDAL, which comes with the installation of MonitorEO with conda') \
				from e
		except Exception as e:
			os.remove(path)
			raise ValueError(f'{filename} cannot be read as a layer of polygons: {e}') from e
		self.layers[name] = {'file': src, 'path': path, 'original': os.path.basename(filename),
		                     **{k: info[k] for k in ('features', 'area_ha', 'crs', 'name_field', 'bounds')}}
		save_layers(self.layers)
		return {'name': name, **self.layers[name], 'text': layer_text(self.layers[name])}

	def remove_layer(self, name):
		layer = self.layers.pop(name, None)
		if layer:
			with contextlib.suppress(OSError):
				os.remove(layer['path'])
			save_layers(self.layers)

	def _tool_message(self, name, text):
		self.messages.append({'role': 'tool', 'tool_name': name, 'content': text,
		                      **({'tool_call_id': self.call_id} if self.call_id else {})})
		_log({'tool': name, 'call': next((c.get('function') for m in reversed(self.messages[:-1])
		                                   for c in m.get('tool_calls') or [] if (c.get('function') or {}).get('name') == name),
		                                  None), 'answer': text[:300]})

	def _remember_names(self, text):
		"""Keep the names of the protected areas of an answer of find_protected_areas, and return them with only
		what is needed to choose one (or None if the answer is not a list of areas)."""
		try:
			areas = json.loads(text)
			for p in areas:
				self.names[str(p['SITE_ID'])] = f"{p['NAME']}" + (f" ({p['DESIG']})" if p.get('DESIG') else '')
			return [{k: p.get(k) for k in AREA_KEYS if p.get(k) not in (None, '')} for p in areas]
		except (ValueError, KeyError, TypeError, AttributeError):
			return None


def _search_manual(question, lang=None, k=3, max_chars=1800):
	"""The K sections of the wiki for QUESTION (at most MAX_CHARS of each), in its language or LANG ('es' or 'en'); the
	wiki is downloaded first if it is not on this computer yet."""
	if not manual.sections():
		manual.update()
	return manual.search(question, k=k, lang=lang, max_chars=max_chars)


def _log(entry):
	"""Add ENTRY to LOG (a JSON line with the time); the log never breaks the assistant."""
	with contextlib.suppress(OSError, TypeError, ValueError):
		os.makedirs(OUTPUT, exist_ok=True)
		with open(LOG, 'a', encoding='utf-8') as f:
			f.write(json.dumps({'time': dt.datetime.now().isoformat(timespec='seconds'), **entry}, ensure_ascii=False,
			                   default=str) + '\n')


def _title(name, args):
	try:
		return report.item_title(name, args)
	except (KeyError, TypeError, ValueError):
		return name


def _facts(name, args, result, names):
	try:
		return report.item_facts(name, args, result, names)
	except (KeyError, TypeError, ValueError):
		return [(k, json.dumps(v, ensure_ascii=False)) for k, v in args.items()]


def _json(obj):
	"""A result of the MCP SDK (1.x or 2.x) as the JSON of the protocol."""
	return obj.model_dump(mode='json', by_alias=True, exclude_none=True)


def _file_url(path):
	rel = os.path.relpath(os.path.realpath(path), os.path.realpath(OUTPUT))
	return None if rel.startswith('..') else '/files/' + rel.replace(os.sep, '/')


# The web server ------------------------------------------------------------------------------------------------------

def make_app(assistant, token, port):
	"""The Starlette application of the page and its API."""
	from starlette.applications import Starlette
	from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
	from starlette.routing import Route

	hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}

	def guarded(handler, need_token=True):
		async def wrapped(request):
			if request.headers.get('host') not in hosts:
				return Response('host not allowed', status_code=403)
			if need_token and not secrets.compare_digest(
					request.headers.get('x-token') or request.query_params.get('t') or '', token):
				return Response('token not valid', status_code=403)
			try:
				return await handler(request)
			except (ValueError, RuntimeError, ModelError) as e:
				return JSONResponse({'error': str(e)}, status_code=400)
		return wrapped

	def ndjson(events):
		async def lines():
			async for e in events:
				yield json.dumps(e, ensure_ascii=False) + '\n'
		return StreamingResponse(lines(), media_type='application/x-ndjson')

	async def index(request):
		with open(os.path.join(HERE, 'ui', 'assistant.html'), encoding='utf-8') as f:
			return HTMLResponse(f.read(), headers={'Cache-Control': 'no-store'})

	async def vendor(request):  # the libraries of the page (Leaflet), kept in the package
		root = os.path.realpath(os.path.join(HERE, 'ui', 'vendor'))
		path = os.path.realpath(os.path.join(root, request.path_params['path']))
		if not path.startswith(root + os.sep) or not os.path.isfile(path):
			return Response('not found', status_code=404)
		return FileResponse(path)

	async def pixel(request):
		body = await request.json()
		return JSONResponse(await assistant.pixel(int(body['id']), float(body['lon']), float(body['lat']),
		                                          body.get('key') or None))

	async def keep_pixel(request):
		return JSONResponse({'id': assistant.keep_pixel((await request.json())['key'])})

	async def refresh_map(request):
		body = await request.json()
		return JSONResponse({'url': await assistant.refresh_map(int(body['id']), body.get('key') or None)})

	async def step_map(request):
		body = await request.json()
		return JSONResponse(await assistant.step_map(int(body['id']), str(body.get('key') or ''),
		                                             bool(body.get('significant'))))

	async def snapshot(request):
		body = await request.json()
		return JSONResponse({'id': await assistant.snapshot(int(body['id']), body)})

	async def logo(request):
		return FileResponse(os.path.join(HERE, 'logos', 'monitoreo_obsnev.png'))

	async def state(request):
		s, e = assistant.settings, assistant.engine
		cloud = assistant.cloud()  # then Ollama is neither looked for nor started
		if not cloud and s.get('ollama', 'auto') == 'auto' and not e.url and not e.installing:  # opened or installed now
			with contextlib.suppress(RuntimeError):
				await asyncio.to_thread(e.find)
		base, a = assistant.base(), engine.asset()
		installed = await asyncio.to_thread(models, {'ollama': base}) if base and not cloud else None
		if installed is not None and not assistant.model_checked:  # once: a model installed already, by default
			assistant.model_checked = True
			chosen = default_model(s['model'], installed)
			if chosen != s['model']:
				s['model'] = chosen
				save_settings(s)
		return JSONResponse({'version': __version__, 'signed_in': signed_in(), 'project': s.get('project'),
		                     'provider': 'monitoreo' if cloud else 'ollama', 'model_name': assistant.model_name(),
		                     'model': s['model'], 'ollama': base or s.get('ollama'), 'models': installed,
		                     'recommended': RECOMMENDED,
		                     'engine': {'auto': s.get('ollama', 'auto') == 'auto', 'how': e.how,
		                                'installing': e.installing, 'mb': round(a[1] / 2 ** 20) if a else None},
		                     'model_gb': MODEL_GB.get(s['model']),
		                     'results': len(assistant.results), 'server': assistant.session is not None,
		                     'update': assistant.update_info, 'busy': assistant.running(),
		                     'window': assistant.in_window, 'eecu': assistant.eecu,
		                     'eecu_tier': s.get('eecu_tier') or 'Community',
		                     'layers': [{'name': k, 'text': layer_text(v)} for k, v in assistant.layers.items()]})

	async def signin(request):
		import ee
		await asyncio.to_thread(lambda: ee.Authenticate(auth_mode='localhost', force=True))
		return JSONResponse({'signed_in': signed_in()})

	async def signout(request):
		"""Log out of the Google account (sign_out) and compute again with the shared account of MonitorEO."""
		was = await asyncio.to_thread(sign_out)
		message = await assistant.connect('')
		for event in await assistant.eecu_events():
			assistant.emit(event)
		return JSONResponse({'signed_in': signed_in(), 'was_signed_in': was, 'message': message})

	async def settings(request):
		body = await request.json()
		answer = {}
		for k in ('model', 'ollama', 'eecu_tier'):
			if body.get(k):
				assistant.settings[k] = str(body[k]).strip()
		if body.get('provider') in PROVIDERS:
			assistant.settings['provider'] = body['provider']
		save_settings(assistant.settings)
		if 'project' in body:
			answer['message'] = await assistant.connect(str(body['project']))
		if 'project' in body or 'eecu_tier' in body:
			for event in await assistant.eecu_events():
				assistant.emit(event)
		return JSONResponse(answer)

	async def eecu(request):
		body = await request.json()
		events = await assistant.eecu_events(refresh=bool(body.get('refresh')))
		for event in events:
			assistant.emit(event)
		return JSONResponse({'usage': assistant.eecu})

	async def chat(request):
		text = str((await request.json()).get('text') or '').strip()
		if not text:
			raise ValueError('empty message')
		assistant.start(text)
		return JSONResponse({})

	async def events(request):
		return ndjson(assistant.follow(int(request.query_params.get('since') or 0)))

	async def quit_app(request):
		"""Close the assistant: the web server stops (and with it the MCP server and the engine of the models)."""
		if assistant.quit:
			asyncio.get_running_loop().call_later(0.5, assistant.quit)
		return JSONResponse({'closed': bool(assistant.quit)})

	async def update_app(request):
		"""Install the last version of GitHub and start the assistant again with it (the same port and token)."""
		from . import update
		if assistant.running():
			raise ValueError('wait until the previous request ends')
		log = []
		result = await asyncio.to_thread(update.ensure_latest, 'assistant', log.append)
		if result != 'updated':
			raise RuntimeError(f"it has not been updated ({log[-1] if log else result})")
		assistant.restart = True
		asyncio.get_running_loop().call_later(0.5, assistant.quit)
		return JSONResponse({'updated': True})

	async def reset(request):
		assistant.new_conversation()
		return JSONResponse({})

	async def make_report(request):
		body = await request.json()
		path = await asyncio.to_thread(assistant.write_report, body.get('title'), body.get('ids'),
		                               set(body.get('tables') or []))
		webbrowser.open(pathlib.Path(path).resolve().as_uri())
		return JSONResponse({'path': path, 'url': _file_url(path)})

	async def add_layer(request):
		if int(request.headers.get('content-length') or 0) > MAX_LAYER:
			raise ValueError(f'the layer takes more than {MAX_LAYER // 2 ** 20} MB')
		data = await request.body()
		return JSONResponse(await asyncio.to_thread(assistant.add_layer, request.query_params.get('name') or '', data))

	async def remove_layer(request):
		assistant.remove_layer(str((await request.json()).get('name') or ''))
		return JSONResponse({})

	async def pull(request):
		model = str((await request.json()).get('model') or assistant.settings['model']).strip()
		if not assistant.base():
			raise ValueError('the engine of the models is missing: install it first')
		return ndjson(_threaded(lambda: pull_model(assistant.base(), model)))

	async def install_engine(request):
		if assistant.engine.installing:
			raise ValueError('it is being installed already')
		return ndjson(_threaded(assistant.engine.install))

	@contextlib.asynccontextmanager
	async def lifespan(app):
		assistant.loop = asyncio.get_running_loop()
		if not assistant.cloud() and assistant.settings.get('ollama', 'auto') == 'auto':
			try:
				await asyncio.to_thread(assistant.engine.find)
			except RuntimeError as e:
				print(f'WARNING: {e}', file=sys.stderr)
		try:
			threading.Thread(target=manual.update, daemon=True).start()  # the wiki, for the tool manual
			threading.Thread(target=_watch_updates, args=(assistant,), daemon=True).start()
			async with assistant.connected():
				yield
		finally:
			assistant.engine.stop()

	async def files(request):
		root = os.path.realpath(OUTPUT)
		path = os.path.realpath(os.path.join(root, request.path_params['path']))
		if not path.startswith(root + os.sep) or not os.path.isfile(path):
			return Response('not found', status_code=404)
		return FileResponse(path)

	return Starlette(routes=[
		Route('/', guarded(index, need_token=False)),
		Route('/logo.png', guarded(logo, need_token=False)),
		Route('/vendor/{path:path}', guarded(vendor, need_token=False)),
		Route('/api/pixel', guarded(pixel), methods=['POST']),
		Route('/api/pixel/keep', guarded(keep_pixel), methods=['POST']),
		Route('/api/map/refresh', guarded(refresh_map), methods=['POST']),
		Route('/api/map/step', guarded(step_map), methods=['POST']),
		Route('/api/map/snapshot', guarded(snapshot), methods=['POST']),
		Route('/api/state', guarded(state)),
		Route('/api/signin', guarded(signin), methods=['POST']),
		Route('/api/signout', guarded(signout), methods=['POST']),
		Route('/api/settings', guarded(settings), methods=['POST']),
		Route('/api/eecu', guarded(eecu), methods=['POST']),
		Route('/api/chat', guarded(chat), methods=['POST']),
		Route('/api/events', guarded(events)),
		Route('/api/reset', guarded(reset), methods=['POST']),
		Route('/api/quit', guarded(quit_app), methods=['POST']),
		Route('/api/update', guarded(update_app), methods=['POST']),
		Route('/api/report', guarded(make_report), methods=['POST']),
		Route('/api/pull', guarded(pull), methods=['POST']),
		Route('/api/engine/install', guarded(install_engine), methods=['POST']),
		Route('/api/layer', guarded(add_layer), methods=['POST']),
		Route('/api/layer/remove', guarded(remove_layer), methods=['POST']),
		Route('/files/{path:path}', guarded(files)),
	], lifespan=lifespan)


def pull_model(base, model):
	"""Download a model with the Ollama at BASE: yields its progress {status, completed, total}."""
	req = urllib.request.Request(base.rstrip('/') + '/api/pull',
	                             data=json.dumps({'model': model, 'name': model}).encode(),  # name: older Ollama
	                             headers={'Content-Type': 'application/json'})
	try:
		with urllib.request.urlopen(req, timeout=60) as r:
			for line in r:
				yield json.loads(line)
	except (urllib.error.URLError, OSError, ValueError) as e:
		raise RuntimeError(f'{model} could not be downloaded: {e}') from e


def _without_eecu_warning(text):
	"""The answer of a tool of the MCP server without its eecu_warning (the page shows it, see eecu_events)."""
	if '"eecu_warning"' not in text:
		return text
	try:
		res = json.loads(text)
	except ValueError:
		return text
	if isinstance(res, dict):
		res.pop('eecu_warning', None)
		return json.dumps(res, ensure_ascii=False, indent=1, default=str)
	return text


async def _threaded(produce):
	"""Run the generator PRODUCE() in a thread and yield what it yields ({'error'} if it fails)."""
	items, loop = asyncio.Queue(), asyncio.get_running_loop()

	def work():
		try:
			for item in produce():
				loop.call_soon_threadsafe(items.put_nowait, item)
		except Exception as e:
			loop.call_soon_threadsafe(items.put_nowait, {'error': str(e)})
		loop.call_soon_threadsafe(items.put_nowait, None)

	threading.Thread(target=work, daemon=True).start()
	while (item := await items.get()) is not None:
		yield item


def run(port=PORT, browser=True, window=True):
	"""Start the assistant on PORT and open it: in a window of its own (pywebview), closing which closes the
	assistant, if WINDOW and this computer can; else in the browser if BROWSER. If it is running already, only open
	it."""
	import uvicorn
	if _in_use(port):
		try:
			with open(RUNNING, encoding='utf-8') as f:
				running = json.load(f)
		except (OSError, ValueError):
			running = {}
		if running.get('port') != port:
			sys.exit(f'ERROR: the port {port} is in use: start the assistant with --port N')
		url = f"http://127.0.0.1:{port}/?t={running['token']}"
		print(f'The assistant of MonitorEO is running already: {url}', file=sys.stderr)
		if not (window and _show_window(url)) and browser:
			webbrowser.open(url)
		return
	token = os.environ.pop('MONITOREO_ASSISTANT_TOKEN', None) or secrets.token_urlsafe(16)  # the same after an update
	assistant = Assistant()
	server = uvicorn.Server(uvicorn.Config(make_app(assistant, token, port), host='127.0.0.1', port=port,
	                                       log_level='warning', timeout_graceful_shutdown=3))
	assistant.quit = lambda: (assistant.end_streams(), setattr(server, 'should_exit', True))  # the button Close
	if hasattr(signal, 'SIGHUP'):  # the window of the terminal closed: stop as with Close (and the engine with it)
		signal.signal(signal.SIGHUP, lambda *_: assistant.quit())
	os.makedirs(OUTPUT, exist_ok=True)
	with open(RUNNING, 'w', encoding='utf-8') as f:
		json.dump({'port': port, 'token': token, 'pid': os.getpid()}, f)
	url = f'http://127.0.0.1:{port}/?t={token}'
	print(f'Assistant of MonitorEO {__version__}: {url} (Ctrl+C to stop it)', file=sys.stderr)
	in_window = assistant.in_window = window and _webview() is not None
	try:
		if in_window:  # the server in a thread, the window in this one (macOS wants it so)
			thread = threading.Thread(target=server.run, daemon=True)
			thread.start()
			for _ in range(600):
				if server.started or not thread.is_alive():
					break
				time.sleep(0.1)

			asked = threading.Event()  # closed by Close (which asked already), an update or the terminal

			def ready(win):  # Close, an update or the window of the terminal closed: the window too
				assistant.quit = lambda: (asked.set(), assistant.end_streams(), setattr(server, 'should_exit', True),
				                          win.destroy())
			in_window = _show_window(url, ready, lambda: assistant.running() and not asked.is_set())
			if in_window:  # the window was closed
				assistant.end_streams()
				server.should_exit = True
			else:
				assistant.in_window = False
				if browser:
					webbrowser.open(url)
			thread.join()
		else:
			if browser:
				threading.Thread(target=_open_when_started, args=(server, url), daemon=True).start()
			server.run()
	finally:
		with contextlib.suppress(OSError):
			os.remove(RUNNING)
	if assistant.restart:  # after an update: the new version, with the same port and token (the page goes on)
		cmd = [sys.executable] + (['-s'] if sys.flags.no_user_site else []) + \
		      ['-m', 'monitoreo.cli', 'assistant', '--no-update', '--port', str(port)] + \
		      ([] if in_window else ['--no-browser'])  # a window again; a page in the browser reloads by itself
		env = {**os.environ, 'MONITOREO_ASSISTANT_TOKEN': token}
		print('Starting the new version of the assistant...', file=sys.stderr)
		if os.name == 'nt':  # no exec on Windows
			sys.exit(subprocess.call(cmd, env=env))
		os.execve(sys.executable, cmd, env)
	print('The assistant of MonitorEO is closed.', file=sys.stderr)


def _watch_updates(assistant, every=6 * 3600):
	"""Check for a new version on GitHub now and every EVERY seconds (the page shows then the button Update)."""
	while True:
		with contextlib.suppress(Exception):
			assistant.update_info = check_update()
		time.sleep(every)


def _webview():
	"""The module webview (pywebview), or None if it is not installed."""
	try:
		import webview
		return webview
	except Exception:  # not installed, or without what it needs (Linux without GTK nor Qt)
		return None


WINDOW_TEXTS = {  # of pywebview: the question when the window closes while computing, and the menu of macOS
	'global.quitConfirmation': 'A computation is running and will be lost. Close the assistant? The engine of the '
	                           'models closes too; the results, the study areas and the reports stay in the folder '
	                           'MonitorEO.',
	'global.ok': 'OK', 'global.quit': 'Close', 'global.cancel': 'Cancel', 'global.saveFile': 'Save file',
	'cocoa.menu.about': 'About', 'cocoa.menu.services': 'Services', 'cocoa.menu.view': 'View',
	'cocoa.menu.edit': 'Edit', 'cocoa.menu.hide': 'Hide', 'cocoa.menu.hideOthers': 'Hide Others',
	'cocoa.menu.showAll': 'Show All', 'cocoa.menu.quit': 'Quit', 'cocoa.menu.fullscreen': 'Enter Full Screen',
	'cocoa.menu.cut': 'Cut', 'cocoa.menu.copy': 'Copy', 'cocoa.menu.paste': 'Paste',
	'cocoa.menu.selectAll': 'Select All', 'windows.fileFilter.allFiles': 'All files',
	'windows.fileFilter.otherFiles': 'Other file types', 'linux.openFile': 'Open file',
	'linux.openFiles': 'Open files', 'linux.openFolder': 'Open folder'}


def _show_window(url, ready=None, busy=None):
	"""Show URL in a window of its own and wait until it is closed (READY(window) when it is created); closing it
	(or quitting, Cmd+Q in macOS) asks first while BUSY() is true. False if this computer cannot open it."""
	webview = _webview()
	if webview is None:
		return False
	try:
		webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True  # the wiki and other pages, in the browser
		webview.settings['ALLOW_DOWNLOADS'] = True  # CSV and GeoTIFF
		win = webview.create_window('MonitorEO Assistant', url, width=1400, height=900, min_size=(720, 520),
		                            text_select=True)
		if busy:  # pywebview asks (confirm_close) after this event, in the thread of the window
			win.events.closing += lambda: setattr(win, 'confirm_close', bool(busy()))
		if ready:
			ready(win)
		webview.start(localization=WINDOW_TEXTS)
		return True
	except Exception as e:
		print(f'WARNING: cannot open a window of its own ({type(e).__name__}: {e}): the browser instead',
		      file=sys.stderr)
		return False


def _in_use(port):
	with socket.socket() as s:
		return s.connect_ex(('127.0.0.1', port)) == 0


def _open_when_started(server, url):
	for _ in range(600):
		if server.started:
			webbrowser.open(url)
			return
		time.sleep(0.1)
