"""Assistant of MonitorEO for managers: a chat in the browser, on this computer, with a language model of open weights
served by Ollama (https://ollama.com; monitoreo.engine installs it if needed) and connected to the MCP server of
MonitorEO (monitoreo.mcp_server).

    monitoreo assistant [--no-update] [--port 8765] [--no-browser]

The model helps to choose the variable, the sensor, the region and the period of an analysis and calls the tools of
MonitorEO, but it never gets their results: they go to the screen and to the report (monitoreo.report), and the model
only gets a receipt. So it can advise but cannot interpret the results. The tools compute in Google Earth Engine with
the Google account of the user (who signs in from the browser, as with `earthengine authenticate`) and their Google
Cloud project; the model gets only the text of the conversation. The settings (project, address of Ollama, model) are
kept in ~/MonitorEO/assistant.json.

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

OUTPUT = os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO')
SETTINGS = os.path.join(OUTPUT, 'assistant.json')
RUNNING = os.path.join(OUTPUT, '.assistant')  # port and token of the assistant that is running
LOG = os.path.join(OUTPUT, 'assistant.log')  # the calls of the model and their errors, to find out what went wrong
LAYERS = os.path.join(OUTPUT, 'capas')  # the vector files added by the user, and their list capas.json
LAYER_TYPES = ('.gpkg', '.geojson', '.json', '.kml', '.zip')  # .zip: a shapefile (or another of these) compressed
MAX_LAYER = 100 * 2 ** 20  # bytes
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
DEFAULTS = {'project': os.environ.get('EE_PROJECT', ''), 'ollama': 'auto', 'model': 'qwen3:8b',
            'context': 16384, 'think': False}
RECOMMENDED = [  # the models of Ollama of the list of the page, the first one by default, with their download in GB
	{'name': 'qwen3:8b', 'gb': 5.2, 'note': 'recomendado'},
	{'name': 'qwen3:4b', 'gb': 2.5, 'note': 'más rápido y ligero; se equivoca más'},
	{'name': 'gpt-oss:20b', 'gb': 14, 'note': 'para ordenadores con 16 GB o más de memoria'},
]
MODEL_GB = {m['name']: m['gb'] for m in RECOMMENDED}
MAX_STEPS = 8  # answers of the model to a message of the user
MAX_ADVICE = 8000  # characters of the answer of an advice tool that the model gets
MAX_ROWS_SHOWN = 40
PASSED_ENV = ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'no_proxy', 'SSL_CERT_FILE',
              'REQUESTS_CA_BUNDLE', 'PYTHONPATH', 'GOOGLE_APPLICATION_CREDENTIALS')

ADVICE = ('list_variables', 'describe_variable', 'find_protected_areas')  # their answers go to the model
RESULTS = ('time_series', 'region_stats', 'map_layer', 'trend_table', 'trend_map', 'compare_series', 'compare_map',
           'burn_severity', 'download_image', 'download_trend', 'download_comparison',
           'download_variables')  # their answers go only to the user and the report
TASKS = ('export_image_to_drive', 'export_time_series_to_drive', 'task_status')  # answers without values: to both
HIDDEN = ('collection', 'scale', 'vmin', 'vmax', 'crs', 'lang', 'limit')  # arguments the model does not see
AREA_KEYS = ('SITE_ID', 'NAME', 'DESIG', 'IUCN_CAT', 'ISO3', 'REP_AREA')  # of the protected areas, for the model
DESIGNATIONS = (r'^(el |la )?(parque (nacional|natural|periurbano)|paraje natural|reserva (natural( concertada)?|'
                r'de la biosfera)|monumento natural|paisaje protegido|espacio natural( protegido)?|zona de especial '
                r'conservaci[oó]n|zec|zepa|lic)\b( (de la|de los|de las|del|de)\b)?\s*')  # removed from the searches

TASK_STATES = {'PENDING': 'en cola', 'READY': 'en cola', 'RUNNING': 'en marcha', 'SUCCEEDED': 'terminada',
               'COMPLETED': 'terminada', 'FAILED': 'fallida', 'CANCELLED': 'cancelada', 'CANCELLING': 'cancelándose',
               'UNKNOWN': 'desconocido'}
WIKI = 'https://github.com/monitoreo-obsnev/monitoreo/wiki/'
MANUAL_TOOL = {'type': 'function', 'function': {  # answered by the assistant (monitoreo.manual), not by the MCP server
	'name': 'manual',
	'description': 'Busca en el manual de MonitorEO (su wiki) los apartados que responden a una pregunta sobre la '
	               'herramienta: qué mide una variable, sensores, fechas y resolución, conceptos (métricas, filtros, '
	               'tendencias, comparaciones, incendios), cómo se instala o se usa, problemas frecuentes y las otras '
	               'herramientas de MonitorEO. Devuelve los apartados con su enlace.',
	'parameters': {'type': 'object', 'properties': {'pregunta': {'type': 'string', 'description': 'La pregunta'}},
	               'required': ['pregunta']}}}
OTHER_TOOLS = [  # what the assistant does not do, by the words of the request (without accents), and who does it
	(r'automatic|periodic|se repit|repetir|script|program(ar|acion)|cuaderno|notebook|en lote|'
	 r'\b[2-9]\d (parques|espacios|zonas|sitios|regiones)',
	 'el paquete de Python o la línea de comandos', 'automatizar cálculos que se repiten o de muchas regiones a la vez',
	 WIKI + 'Python'),
	(r'\ben r\b|\bdesde r\b|paquete de r\b|rstudio|\bterra\b|ggplot', 'el paquete de R', 'hacer los cálculos en R',
	 WIKI + 'R'),
	(r'qgis|edit(ar|o) (la |una |mi |mis |las |esta )?capa|digitaliz|mapa para imprimir|maquet|composicion|leyenda del mapa',
	 'el plugin de QGIS', 'trabajar junto a tus capas en QGIS, editarlas y hacer mapas para imprimir', WIKI + 'QGIS'),
	(r'sin instalar|en el navegador sin|desde (el|mi) movil|tablet', 'la app de Earth Engine',
	 'usar MonitorEO en el navegador sin instalar nada', WIKI + 'App-de-Earth-Engine'),
	(r'publicar|pagina web publica|que lo vea (cualquiera|todo el mundo)', 'el visor de resultados',
	 'publicar informes para que los vea cualquiera (lo hacen sus administradores)', WIKI + 'Visor-de-resultados'),
]
LABELS = {'manual': 'Consultando el manual de MonitorEO',
          'list_variables': 'Consultando las variables del catálogo',
          'describe_variable': 'Consultando la ficha de {variable}',
          'find_protected_areas': 'Buscando espacios protegidos con «{text}»'}

RECEIPT_NOTE = ('El resultado se muestra al usuario y va a su informe; tú solo recibes un acuse de recibo, sin los '
                'valores.')

PROMPT = """Eres el asistente de MonitorEO-OBSNEV (Observatorio de Cambio Global de Sierra Nevada, Universidad de \
Granada) para gestores de espacios naturales. Hoy es {today}.

Qué haces:
- Ayudas a elegir la variable, el sensor, la región y el periodo de un análisis, y lo lanzas con las herramientas de \
cálculo de MonitorEO, que calculan en Google Earth Engine con la cuenta del usuario.
- Aconsejas sobre sensores y variables con la guía de abajo y con list_variables y describe_variable.
- Respondes preguntas sobre MonitorEO (qué mide una variable, sensores, fechas, resolución, conceptos, cómo se \
instala o se usa cada herramienta) con la herramienta manual, que busca en su manual.

Reglas:
1. Nunca ves los resultados de los cálculos: van a la pantalla del usuario y a su informe. Cuando una herramienta de \
cálculo responda «Hecho», di en una frase qué se ha calculado y nada sobre sus valores (ni si suben, bajan, son altos \
o bajos, ni qué significan).
2. No interpretes resultados aunque te lo pidan: di que el asistente no interpreta resultados y que su interpretación \
corresponde a personal técnico, por ejemplo del OBSNEV.
3. Para un espacio protegido, busca siempre su identificador con find_protected_areas, directamente y sin pedir \
permiso, y nunca te lo inventes. Si hay varios candidatos, pregunta cuál: el usuario ve la lista de la búsqueda y \
puede elegir uno en ella.
4. Si falta algo imprescindible (variable, lugar o fechas), propón una opción razonable según la guía y pregunta en \
una sola frase antes de calcular.
5. Responde en español, breve y claro.
6. Para preguntas sobre MonitorEO, consulta manual y responde con lo que dice, en cinco frases como mucho y con el \
enlace de la página. Puedes añadir una explicación general breve (por ejemplo, qué mide un índice de vegetación), \
pero no te inventes datos de MonitorEO: si el manual no lo dice, dilo. Usa solo los enlaces que te dé manual o los de \
la lista de herramientas de abajo.
7. Si te piden algo que el asistente no puede hacer, dilo y aconseja en una o dos frases la herramienta de MonitorEO \
que lo hace, de la lista de abajo, con su enlace: cálculos que se repiten solos (cada mes) o de muchas regiones a la \
vez, el paquete de Python o la línea de comandos; editar capas o hacer mapas para imprimir, el plugin de QGIS; \
trabajar en R, el paquete de R; probar sin instalar nada, la app de Earth Engine. No escribas código ni órdenes de \
instalación: su página de la wiki lo explica.
8. No nombres al usuario tus herramientas internas (time_series, find_protected_areas...): di lo que haces.

Cómo llamar a las herramientas:
- Región: un objeto JSON con una de estas formas: {{"wdpa_id": SITE_ID}} (un espacio protegido, con el SITE_ID que \
devuelve find_protected_areas), {{"ecoregion_at": [lon, lat]}}, {{"bbox": [oeste, sur, este, norte]}} o \
{{"point": [lon, lat], "buffer": metros}}.
- Fechas: "AAAA-MM-DD". Temporada de cada año: season ["MM-DD", "MM-DD"], p. ej. ["06-01", "08-31"] para el verano.
- Sensor: "Sentinel-2", "Landsat" o "Modis". La variable, como en el catálogo (NDVI, EVI, NDWI, LST...).
- Evolución en el tiempo: time_series (step "monthly" o "annual"; las series largas en regiones grandes tardan \
minutos). Mapa de un periodo: map_layer; sus estadísticas: region_stats. Tendencia a lo largo de los años: \
trend_table (8 años o más) y trend_map para ver dónde. Comparar un periodo con otro de referencia: compare_series y \
compare_map. Incendio: burn_severity.
- Descargar en GeoTIFF (para un SIG): un mapa con download_image, una tendencia con download_trend y una \
comparación con download_comparison; para regiones pequeñas o, en las grandes, con resolution (metros de píxel) mayor \
que la de los datos. Varias variables en rejillas alineadas (para un modelo): download_variables, primero con \
dry_run. Regiones grandes a resolución completa: export_image_to_drive (o export_time_series_to_drive para una serie \
larga), que exportan a Google Drive; después, task_status con la operation que devuelven dice si han terminado.

Otras herramientas de MonitorEO (las mismas funciones y los mismos resultados):
- App de Earth Engine: en el navegador, sin instalar nada ni cuenta de Earth Engine; mapas, series, tendencias, \
comparaciones e incendios, también sobre un polígono dibujado. {wiki}App-de-Earth-Engine
- Plugin de QGIS: lo mismo sin programar, junto a las capas del usuario, con valores consultables en el mapa y mapas \
para imprimir en QGIS. {wiki}QGIS
- Paquete de Python y línea de comandos: automatizar cálculos (scripts, cuadernos, muchas regiones o fechas). \
{wiki}Python y {wiki}Línea-de-comandos
- Paquete de R: análisis en R con sf, terra o ggplot2. {wiki}R
- Servidor MCP: los mismos cálculos con Claude u otro asistente de IA. {wiki}MCP
- Visor de resultados: publicar informes en una web para que los vea cualquiera (solo sus administradores). \
{wiki}Visor-de-resultados

Guía de sensores:
- Sentinel-2: píxel de 10-20 m, una imagen cada 5 días aproximadamente, desde 2017. Para zonas pequeñas o con \
detalle (parcelas, bordes, lagunas) y periodos recientes. No tiene datos antes de 2017: para un periodo que empieza \
antes, propón Landsat, o Sentinel-2 solo desde 2017.
- Landsat: píxel de 30 m, una imagen cada 8-16 días, desde 1984. Para series largas y tendencias de décadas. Entre \
mayo de 2012 y marzo de 2013 no hay imágenes de Landsat en el catálogo.
- MODIS: píxel de 250-1000 m, imágenes diarias o compuestas de 8-16 días, desde 2000. Para regiones grandes, la \
estacionalidad y las variables que solo da MODIS (evapotranspiración, LAI, aerosoles).
- MonitorEO descarta los píxeles con nubes, agua, nieve o aerosoles según la variable. En alta montaña la nieve deja \
pocos píxeles válidos en invierno para los índices de vegetación.
- Severidad de un incendio: burn_severity con Sentinel-2 o Landsat; periodo anterior, los 3 meses antes del incendio; \
periodo posterior, los 2-3 meses después de que termine.

Variables del catálogo (sensores, píxel y primer año):
{variables}"""


# The model -----------------------------------------------------------------------------------------------------------

class ModelError(RuntimeError):
	pass


def instructions(today=None):
	"""The instructions of the model, with the variables of the catalog."""
	return PROMPT.format(today=(today or dt.date.today()).isoformat(), variables=variables_text(), wiki=WIKI)


def variables_text():
	"""The variables of the catalog, a line each: name, group and, for each sensor, pixel size and first year."""
	variables = {}
	for v in services.list_variables():
		years = re.findall(r'(?<!\d)(?:19|20)\d\d(?!\d)', v['dates'])
		var = variables.setdefault(v['variable'], {'name': v['name'], 'group': v['group'], 'sensors': {}})
		s = var['sensors'].setdefault(v['sensor'], {'m': v['resolution_m'], 'first': None, 'last': None, 'now': False})
		s['m'] = min(s['m'], v['resolution_m'])
		if years:
			s['first'] = min(s['first'] or '9999', min(years))
			s['last'] = max(s['last'] or '0', max(years))
		s['now'] = s['now'] or bool(re.search(r'now|hoy', v['dates'], re.I))
	lines = []
	for code, var in variables.items():
		sensors = '; '.join(f"{'MODIS' if name == 'Modis' else name} {s['m']:g} m desde {s['first'] or '?'}"
		                    + ('' if s['now'] or not s['last'] else f" hasta {s['last']}")
		                    for name, s in var['sensors'].items())
		lines.append(f"- {code}: {var['name'].strip().rstrip('.')}; grupo {var['group']}. {sensors}.")
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
	return out


def _wants(schema, types):
	kinds = [schema.get('type')] + [s.get('type') for s in schema.get('anyOf', [])]
	return any(k in types for k in kinds)


def search_name(text):
	"""The name of a protected area without its designation ('Parque Nacional de Doñana' -> 'Doñana'): WDPA has it
	in another field, and the name with it is often that of another area (here, the Ramsar site)."""
	name = re.sub(DESIGNATIONS, '', str(text).strip(), flags=re.I).strip()
	return name or str(text).strip()


def areas_text(areas, question=''):
	"""The protected areas found, for the model: a line each, with the SITE_ID next to its designation (small models
	misread lists in JSON), first those whose designation is in the question of the user."""
	q = question.lower()
	matches = [bool(a.get('DESIG') and a['DESIG'].lower() in q) for a in areas]
	ranked = [a for a, m in zip(areas, matches) if m] + [a for a, m in zip(areas, matches) if not m]
	lines = [f"- SITE_ID {a['SITE_ID']}: {a.get('NAME', '')}, {a.get('DESIG') or 'sin designación'}"
	         + (f", {report._num(a['REP_AREA'])} km²" if a.get('REP_AREA') is not None else '')
	         + (' (su designación coincide con la consulta)' if i < sum(matches) else '')
	         for i, a in enumerate(ranked)]
	return (f'{len(areas)} espacios protegidos; el usuario ve esta lista y puede elegir uno en ella:\n' + '\n'.join(lines)
	        if areas else 'Ningún espacio protegido con ese nombre: pide al usuario otro nombre o una capa.')


def task_text(tool, text):
	"""What the user reads of an answer of the exports to Google Drive or of task_status."""
	try:
		r = json.loads(text)
	except ValueError:
		return text
	if tool == 'task_status':
		state = TASK_STATES.get(r.get('state'), r.get('state'))
		progress = f" ({round(100 * r['progress'])} %)" if isinstance(r.get('progress'), (int, float)) else ''
		return f'Exportación a Google Drive: {state}{progress}.' + (f" {r['error']}" if r.get('error') else '')
	return (f"Exportación a Google Drive en marcha: {r.get('file', '')} en la carpeta {r.get('folder', '')} de tu "
	        'Google Drive. Tarda de minutos a horas; pregunta «¿ha terminado la exportación?» para saberlo.')


def fix_links(text, question=''):
	"""TEXT of the model with its links to the wiki that do not exist (small models make them up) replaced by their
	page, if it exists, or else by the section of the manual that answers QUESTION best."""
	links = set(re.findall(re.escape(WIKI) + r'[^\s)\]>"\'«»]*[^\s)\]>"\'«».,;:]', text))
	if not links:
		return text
	secs = manual.sections()
	pages, urls = {s['name'] for s in secs} or set(manual.PAGES), {s['url'] for s in secs}
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


def other_tool(text):
	"""(name, what for, link) of the other tool of MonitorEO for a request that the assistant does not do, or None."""
	t = manual._ascii(str(text).lower())
	return next(((name, what, url) for pattern, name, what, url in OTHER_TOOLS if re.search(pattern, t)), None)


def receipt(n, title):
	"""What the model gets of a result: that it was computed and shown, without its values."""
	return (f'Hecho: «{title}» se ha calculado en Google Earth Engine y se muestra al usuario como resultado {n}. '
	        'No ves sus valores: no los describas ni los interpretes.')


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
		raise ModelError(f'no hay conexión con Ollama en {base}: ábrelo o instálalo desde https://ollama.com '
		                 f'({e})') from e


def chat_model(settings, system, messages, tools):
	"""The next message of the model (Ollama /api/chat): {'role', 'content', 'tool_calls'}."""
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
			raise ModelError(f"el modelo {settings['model']} no está instalado: descárgalo") from e
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
	try:
		with open(SETTINGS, encoding='utf-8') as f:
			return {**DEFAULTS, **json.load(f)}
	except (OSError, ValueError):
		return dict(DEFAULTS)


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
	"""'3 polígonos, 125,3 ha' (and the field of their names)."""
	n = layer['features']
	return f"{n} polígono{'s' if n != 1 else ''}, {report._num(layer['area_ha'])} ha" + \
		(f", nombres del campo {layer['name_field']}" if layer.get('name_field') else '')


def _in_zip(path):
	"""The path of GDAL of the vector file inside a zip file (a shapefile, or a GeoPackage, GeoJSON or KML)."""
	with zipfile.ZipFile(path) as z:
		names = [n for n in z.namelist() if not n.startswith('__MACOSX/')]
	for ext in ('.shp', '.gpkg', '.geojson', '.json', '.kml'):
		inside = next((n for n in names if n.lower().endswith(ext)), None)
		if inside:
			return f'/vsizip/{path}/{inside}'
	raise ValueError('el .zip no tiene ningún shapefile, GeoPackage, GeoJSON ni KML')


def signed_in():
	"""Whether this computer has the credentials of Earth Engine of `earthengine authenticate`."""
	import ee
	return os.path.exists(ee.oauth.get_credentials_path())


class Assistant:
	"""A conversation with the model and the MCP server of MonitorEO, and its results. Each message of the user is
	answered by a task of its own (start), whose events are kept (emit) and sent to every page that follows them
	(follow): the answer goes on without the page, and a page opened again shows the whole conversation."""

	def __init__(self, settings=None):
		self.settings = settings or load_settings()
		self.session, self.tools, self.system = None, [], instructions()
		self.task = None  # that of the message being answered
		self.events, self.offset, self.changed = [], 0, asyncio.Event()  # those of the conversation, from seq offset
		self.layers = load_layers()
		self.engine = engine.Engine()
		self.model_checked = False  # whether the model of the settings was checked against those installed
		self.quit = None  # stops the web server (see run)
		self.restart = False  # whether run starts it again (after an update)
		self.update_info = None  # see check_update
		self.reset()

	def base(self):
		"""Address of the Ollama in use: that of the settings or, with 'auto', that of the engine (None if there is
		none yet)."""
		s = self.settings.get('ollama') or 'auto'
		return self.engine.url if s == 'auto' else s

	def model_settings(self):
		return {**self.settings, 'ollama': self.base()}

	def reset(self):
		self.messages, self.results, self.names, self.question = [], [], {}, None

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
		while True:
			changed = self.changed  # before reading the events: one emitted meanwhile sets it
			for e in self.events[max(since - self.offset, 0):]:
				yield e
				since = e['seq'] + 1
			try:
				await asyncio.wait_for(changed.wait(), ping)
			except asyncio.TimeoutError:
				yield {'type': 'ping'}

	def start(self, text):
		"""Answer a message of the user in a task of its own."""
		if self.running():
			raise ValueError('espera a que termine la consulta anterior')

		async def answer():
			self.emit({'type': 'user', 'text': text})
			try:
				async for e in self.chat(text):
					self.emit(e)
			except Exception as e:  # the conversation goes on
				self.emit({'type': 'error', 'text': f'El asistente ha fallado: {type(e).__name__}: {e}'})
			finally:
				self.emit({'type': 'done'})
		self.task = asyncio.create_task(answer())

	def new_conversation(self):
		"""Forget the conversation and its results (their files stay); the pages get a reset."""
		if self.running():
			raise ValueError('espera a que termine la consulta anterior')
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
			raise RuntimeError('el servidor MCP de MonitorEO no está en marcha: cierra el asistente y ábrelo otra vez')
		res = _json(await self.session.call_tool(name, args))
		content = res.get('content') or []
		texts = [c['text'] for c in content if c.get('type') == 'text']
		images = [f"data:{c.get('mimeType') or 'image/png'};base64,{c['data']}" for c in content
		          if c.get('type') == 'image']
		error = (texts[0] if texts else 'error') if res.get('isError') else None
		return error, texts, images

	async def connect(self, project):
		"""Use this Google Cloud project; returns the answer of the MCP server."""
		self.settings['project'] = project.strip()
		save_settings(self.settings)
		if not signed_in():
			return 'Proyecto guardado: inicia sesión con Google para usarlo'
		error, texts, _ = await self.call('connect', {'project': self.settings['project']})
		if error:
			raise RuntimeError(re.sub(r'^\w+Error: ', '', error))
		return texts[0] if texts else ''

	def not_ready(self):
		"""Why the tools cannot compute yet, or None."""
		if not signed_in():
			return 'antes de calcular, inicia sesión con tu cuenta de Google (botón «Iniciar sesión con Google»)'
		if not self.settings.get('project'):
			return 'antes de calcular, escribe tu proyecto de Google Cloud registrado en Earth Engine'
		return None

	async def chat(self, text):
		"""Answer a message of the user: yields the events for the page (see the module)."""
		hint = other_tool(text)
		if hint:  # small models often miss it: the page says it, and the model gets a note
			name, what, url = hint
			yield {'type': 'other_tool', 'name': name, 'what': what, 'url': url}
			text += (f'\n\n(Nota de la aplicación: el asistente no hace esto; se hace con {name} de MonitorEO, para '
			         f'{what}: {url}. Dilo en una o dos frases con el enlace, sin código ni nombres de herramientas.)')
		self.messages.append({'role': 'user', 'content': text})
		self.question = self.question or text
		for _ in range(MAX_STEPS):
			yield {'type': 'status', 'text': f"El modelo ({self.settings['model']}) está pensando…"}
			try:
				if not self.base():
					raise ModelError('falta el motor de los modelos: instálalo en Configuración')
				message = await asyncio.to_thread(chat_model, self.model_settings(), self.system_prompt(),
				                                  self.messages, self.tools)
			except ModelError as e:
				yield {'type': 'error', 'text': f'Modelo de lenguaje: {e}'}
				return
			calls = message.get('tool_calls') or []
			message['content'] = await asyncio.to_thread(fix_links, message['content'], text)
			self.messages.append({'role': 'assistant', 'content': message['content'],
			                      **({'tool_calls': calls} if calls else {})})
			if message['content']:
				yield {'type': 'assistant', 'text': message['content']}
			if not calls:
				return
			for call in calls:
				async for event in self.run_tool(call.get('function') or {}):
					yield event
		yield {'type': 'error', 'text': 'He parado: demasiados pasos para un solo mensaje. Pídelo de forma más '
		                                'concreta, por partes.'}

	async def run_tool(self, call):
		"""Run a call of the model: the answers of the advice tools go to the model, those of the others only to the
		user (a card on the page and a result for the report) and the model gets a receipt."""
		name = call.get('name')
		if name == 'manual':
			async for event in self.ask_manual(call.get('arguments')):
				yield event
			return
		if name not in ADVICE + RESULTS + TASKS:
			self._tool_message(name, f'Error: no hay ninguna herramienta {name}.')
			return
		try:
			args = fix_args(name, call.get('arguments'), self.tools)
			if name == 'find_protected_areas' and args.get('text'):
				args['text'] = search_name(args['text'])
			self.check_areas(args)
			args = self.with_layer(args)
		except ValueError as e:
			self._tool_message(name, f'Error: {e}.')
			return
		title = _title(name, args)
		if name in RESULTS + TASKS:
			problem = self.not_ready()
			if problem:
				yield {'type': 'error', 'text': problem[0].upper() + problem[1:] + '.'}
				self._tool_message(name, f'Error: no se ha calculado; {problem}.')
				return
		if name in RESULTS:
			yield {'type': 'running', 'text': f'Calculando en Google Earth Engine: {title}…',
			       'facts': _facts(name, args, None, self.all_names())}
		elif name in TASKS:
			yield {'type': 'status', 'text': ('Consultando la exportación' if name == 'task_status' else
			                                  'Lanzando la exportación a Google Drive') + '…'}
		else:
			yield {'type': 'status', 'text': LABELS[name].format(**{k: args.get(k, '') for k in ('variable', 'text')})
			                                 + '…'}
		try:
			error, texts, images = await self.call(name, args)
		except Exception as e:  # the MCP server stopped
			error, texts, images = f'{type(e).__name__}: {e}', [], []
		if error:
			what = f'El cálculo «{title}»' if name in RESULTS else f'La consulta {name}'
			yield {'type': 'error', 'text': f"{what} ha fallado: {re.sub(r'^[A-Za-z]+Error: ', '', error)}"}
			self._tool_message(name, f'Error: {error}')
			return
		if name in ADVICE:
			text = '\n'.join(texts)
			if name == 'find_protected_areas':
				found = self._remember_names(text)
				if found is not None:
					question = ' '.join(m['content'] for m in self.messages if m['role'] == 'user')
					shown = [{**a, 'match': bool(a.get('DESIG') and a['DESIG'].lower() in question.lower())}
					         for a in found]
					yield {'type': 'areas', 'query': args.get('text', ''),
					       'areas': sorted(shown, key=lambda a: not a['match'])}
					text = areas_text(found, question)
			self._tool_message(name, text[:MAX_ADVICE])
			return
		if name in TASKS:
			text = '\n'.join(texts)
			yield {'type': 'notice', 'text': task_text(name, text)}
			self._tool_message(name, text[:MAX_ADVICE])
			return
		try:
			result = json.loads(texts[0]) if texts else {}
		except ValueError:
			result = {'text': texts[0]}
		if not images and isinstance(result, dict) and str(result.get('file', '')).endswith('.tif'):
			preview = await asyncio.to_thread(report.tif_preview, result['file'], result.get('palette'),
			                                  result.get('min'), result.get('max'))
			images = [preview] if preview else []
		item = {'id': len(self.results) + 1, 'tool': name, 'args': args, 'result': result,
		        'image': images[0] if images else None, 'title': _title(name, args)}
		self.results.append(item)
		yield {'type': 'result', **self.card(item)}
		self._tool_message(name, receipt(item['id'], item['title']))

	async def ask_manual(self, args):
		"""Answer a call of the tool manual with the sections of the wiki that answer its question; the user sees
		their links."""
		try:
			args = json.loads(args) if isinstance(args, str) else (args or {})
		except ValueError:
			args = {}
		question = str(args.get('pregunta') or args.get('question') or '').strip()
		yield {'type': 'status', 'text': LABELS['manual'] + '…'}
		found = await asyncio.to_thread(_search_manual, question)
		if found:
			yield {'type': 'sources', 'sources': [{'title': f"{s['page']} › {s['title']}" if s['title'] != s['page']
			                                       else s['page'], 'url': s['url']} for s in found]}
			text = 'Apartados del manual de MonitorEO (responde con ellos y da el enlace):\n\n' + '\n\n'.join(
				f"## {s['page']} › {s['title']} ({s['url']})\n{s['text']}" for s in found)
		else:
			text = 'El manual no tiene nada sobre eso (o no se ha podido descargar): dilo al usuario.'
		self._tool_message('manual', text[:MAX_ADVICE])

	def card(self, item):
		"""What the page shows of a result."""
		tool, args, result = item['tool'], item['args'], item['result']
		table = report.item_table(tool, result, args)
		card = {'id': item['id'], 'title': item['title'], 'image': item['image'],
		        'facts': _facts(tool, args, result, self.all_names()), 'table': None, 'files': [], 'legend': None}
		if table:
			labels, rows = table
			card['table'] = {'labels': labels, 'rows': rows[:MAX_ROWS_SHOWN], 'more': max(0, len(rows) - MAX_ROWS_SHOWN)}
		if isinstance(result, dict):
			if result.get('palette'):
				card['legend'] = {k: result.get(k) for k in ('min', 'max', 'palette')}
				card['legend']['unit'] = report.unit_text(result.get('unit'))
			for k in ('csv', 'file'):
				if result.get(k):
					card['files'].append({'name': os.path.basename(result[k]), 'url': _file_url(result[k]),
					                      'path': result[k]})
		return card

	def write_report(self, title, ids=None):
		"""Write the report of the results IDS (default: all) and return its path."""
		items = [r for r in self.results if ids is None or r['id'] in ids]
		if not items:
			raise ValueError('no hay resultados para el informe')
		return report.write(items, title=title or self.question, question=self.question,
		                    project=self.settings.get('project'), names=self.all_names())

	def system_prompt(self):
		"""The instructions of the model, with the layers of the user."""
		if not self.layers:
			return self.system
		return self.system + '\n\nÁreas de estudio del usuario (capas de polígonos de su ordenador), con la región que ' \
		                     'las usa; cada polígono da su propia serie o fila:\n' + \
		       '\n'.join(f'- {k} ({layer_text(v)}): región {{"capa": "{k}"}}' for k, v in self.layers.items())

	def all_names(self):
		"""The names of the regions for the user: protected areas (by WDPA ID) and layers (by file)."""
		return {**{v['file']: f'Área de estudio «{k}» ({layer_text(v)})' for k, v in self.layers.items()}, **self.names}

	def check_areas(self, args):
		"""Refuse the WDPA IDs that come neither from find_protected_areas nor from the user: small models copy them
		from the examples or make them up."""
		region = args.get('region') or args.get('area')
		ids = region.get('wdpa_id') if isinstance(region, dict) else None
		if ids is None:
			return
		said = {x for m in self.messages if m['role'] == 'user' for x in re.findall(r'\d+', m['content'])}
		unknown = [i for i in (ids if isinstance(ids, list) else [ids]) if str(i) not in self.names and str(i) not in said]
		if unknown:
			raise ValueError(f'el wdpa_id {", ".join(map(str, unknown))} no sale de find_protected_areas: busca '
			                 'primero el espacio protegido por su nombre con find_protected_areas y usa su SITE_ID')

	def with_layer(self, args):
		"""ARGS with a region {"capa": name} as the file of that area of study; also the ways small models give it:
		the name alone, {"area_de_estudio": name}, "capa parcelas"..."""
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
		key = re.sub(r'^(la |el )?(capa|area de estudio|área de estudio)\s+', '', key.strip(), flags=re.I).strip('«»"\' ')
		layer = self.layers.get(key) or next((v for k, v in self.layers.items() if key.lower() in (
			k.lower(), v['original'].lower(), os.path.splitext(v['original'])[0].lower())), None)
		if not layer:  # small models copy the examples ({"capa": "nombre"}): the one the user named, if only one
			said = ' '.join(m['content'] for m in self.messages if m['role'] == 'user').lower()
			named = [v for k, v in self.layers.items() if re.search(r'\b' + re.escape(k.lower()) + r'\b', said)]
			layer = named[0] if len(named) == 1 else None
		if not layer:
			raise ValueError(f'no hay ningún área de estudio «{key}»; las áreas de estudio son: '
			                 f'{", ".join(self.layers) or "ninguna"} (región: {{"capa": "nombre"}})')
		return {**args, arg: {'file': layer['file'],
		                      **({'name_field': layer['name_field']} if layer.get('name_field') else {})}}

	def add_layer(self, filename, data):
		"""Keep a vector file (its name and content) in LAYERS as a layer that the model can use as a region."""
		stem, ext = os.path.splitext(os.path.basename(filename))
		if ext.lower() not in LAYER_TYPES:
			raise ValueError('formato no admitido: usa un GeoPackage (.gpkg), un GeoJSON, un KML o un shapefile '
			                 'comprimido en .zip')
		if len(data) > MAX_LAYER:
			raise ValueError(f'la capa ocupa más de {MAX_LAYER // 2 ** 20} MB')
		name = base = re.sub(r'[^a-z0-9_-]+', '_', stem.lower()).strip('_') or 'capa'
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
			raise ValueError('para leer capas hace falta GDAL, que trae la instalación de MonitorEO con conda') from e
		except Exception as e:
			os.remove(path)
			raise ValueError(f'no se puede leer {filename} como capa de polígonos: {e}') from e
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
		self.messages.append({'role': 'tool', 'tool_name': name, 'content': text})
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


def _search_manual(question):
	"""The sections of the wiki for QUESTION; the wiki is downloaded first if it is not on this computer yet."""
	if not manual.sections():
		manual.update()
	return manual.search(question)


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

	async def logo(request):
		return FileResponse(os.path.join(HERE, 'logos', 'monitoreo_obsnev.png'))

	async def state(request):
		s, e = assistant.settings, assistant.engine
		if s.get('ollama', 'auto') == 'auto' and not e.url and not e.installing:  # Ollama opened or installed now
			with contextlib.suppress(RuntimeError):
				await asyncio.to_thread(e.find)
		base, a = assistant.base(), engine.asset()
		installed = await asyncio.to_thread(models, {'ollama': base}) if base else None
		if installed is not None and not assistant.model_checked:  # once: a model installed already, by default
			assistant.model_checked = True
			chosen = default_model(s['model'], installed)
			if chosen != s['model']:
				s['model'] = chosen
				save_settings(s)
		return JSONResponse({'version': __version__, 'signed_in': signed_in(), 'project': s.get('project'),
		                     'model': s['model'], 'ollama': base or s.get('ollama'), 'models': installed,
		                     'recommended': RECOMMENDED,
		                     'engine': {'auto': s.get('ollama', 'auto') == 'auto', 'how': e.how,
		                                'installing': e.installing, 'mb': round(a[1] / 2 ** 20) if a else None},
		                     'model_gb': MODEL_GB.get(s['model']),
		                     'results': len(assistant.results), 'server': assistant.session is not None,
		                     'update': assistant.update_info, 'busy': assistant.running(),
		                     'layers': [{'name': k, 'text': layer_text(v)} for k, v in assistant.layers.items()]})

	async def signin(request):
		import ee
		await asyncio.to_thread(lambda: ee.Authenticate(auth_mode='localhost', force=True))
		return JSONResponse({'signed_in': signed_in()})

	async def settings(request):
		body = await request.json()
		answer = {}
		for k in ('model', 'ollama'):
			if body.get(k):
				assistant.settings[k] = str(body[k]).strip()
		save_settings(assistant.settings)
		if 'project' in body:
			answer['message'] = await assistant.connect(str(body['project']))
		return JSONResponse(answer)

	async def chat(request):
		text = str((await request.json()).get('text') or '').strip()
		if not text:
			raise ValueError('mensaje vacío')
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
			raise ValueError('espera a que termine la consulta anterior')
		log = []
		result = await asyncio.to_thread(update.ensure_latest, 'assistant', log.append)
		if result != 'updated':
			raise RuntimeError(f"no se ha actualizado ({log[-1] if log else result})")
		assistant.restart = True
		asyncio.get_running_loop().call_later(0.5, assistant.quit)
		return JSONResponse({'updated': True})

	async def reset(request):
		assistant.new_conversation()
		return JSONResponse({})

	async def make_report(request):
		body = await request.json()
		path = await asyncio.to_thread(assistant.write_report, body.get('title'), body.get('ids'))
		webbrowser.open(pathlib.Path(path).resolve().as_uri())
		return JSONResponse({'path': path, 'url': _file_url(path)})

	async def add_layer(request):
		if int(request.headers.get('content-length') or 0) > MAX_LAYER:
			raise ValueError(f'la capa ocupa más de {MAX_LAYER // 2 ** 20} MB')
		data = await request.body()
		return JSONResponse(await asyncio.to_thread(assistant.add_layer, request.query_params.get('name') or '', data))

	async def remove_layer(request):
		assistant.remove_layer(str((await request.json()).get('name') or ''))
		return JSONResponse({})

	async def pull(request):
		model = str((await request.json()).get('model') or assistant.settings['model']).strip()
		if not assistant.base():
			raise ValueError('falta el motor de los modelos: instálalo primero')
		return ndjson(_threaded(lambda: pull_model(assistant.base(), model)))

	async def install_engine(request):
		if assistant.engine.installing:
			raise ValueError('ya se está instalando')
		return ndjson(_threaded(assistant.engine.install))

	@contextlib.asynccontextmanager
	async def lifespan(app):
		if assistant.settings.get('ollama', 'auto') == 'auto':
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
		Route('/api/state', guarded(state)),
		Route('/api/signin', guarded(signin), methods=['POST']),
		Route('/api/settings', guarded(settings), methods=['POST']),
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
		raise RuntimeError(f'no se ha podido descargar {model}: {e}') from e


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


def run(port=PORT, browser=True):
	"""Start the assistant on PORT and open it in the browser; if it is running already, only open it."""
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
		if browser:
			webbrowser.open(url)
		return
	token = os.environ.pop('MONITOREO_ASSISTANT_TOKEN', None) or secrets.token_urlsafe(16)  # the same after an update
	assistant = Assistant()
	server = uvicorn.Server(uvicorn.Config(make_app(assistant, token, port), host='127.0.0.1', port=port,
	                                       log_level='warning', timeout_graceful_shutdown=3))
	assistant.quit = lambda: setattr(server, 'should_exit', True)  # the button Cerrar of the page
	if hasattr(signal, 'SIGHUP'):  # the window of the terminal closed: stop as with Cerrar (and the engine with it)
		signal.signal(signal.SIGHUP, lambda *_: assistant.quit())
	os.makedirs(OUTPUT, exist_ok=True)
	with open(RUNNING, 'w', encoding='utf-8') as f:
		json.dump({'port': port, 'token': token, 'pid': os.getpid()}, f)
	url = f'http://127.0.0.1:{port}/?t={token}'
	print(f'Assistant of MonitorEO {__version__}: {url} (Ctrl+C to stop it)', file=sys.stderr)
	if browser:
		threading.Thread(target=_open_when_started, args=(server, url), daemon=True).start()
	try:
		server.run()
	finally:
		with contextlib.suppress(OSError):
			os.remove(RUNNING)
	if assistant.restart:  # after an update: the new version, with the same port and token (the page goes on)
		cmd = [sys.executable] + (['-s'] if sys.flags.no_user_site else []) + \
		      ['-m', 'monitoreo.cli', 'assistant', '--no-update', '--no-browser', '--port', str(port)]
		env = {**os.environ, 'MONITOREO_ASSISTANT_TOKEN': token}
		print('Starting the new version of the assistant...', file=sys.stderr)
		if os.name == 'nt':  # no exec on Windows
			sys.exit(subprocess.call(cmd, env=env))
		os.execve(sys.executable, cmd, env)
	print('The assistant of MonitorEO is closed.', file=sys.stderr)


def _watch_updates(assistant, every=6 * 3600):
	"""Check for a new version on GitHub now and every EVERY seconds (the page shows then the button Actualizar)."""
	while True:
		with contextlib.suppress(Exception):
			assistant.update_info = check_update()
		time.sleep(every)


def _in_use(port):
	with socket.socket() as s:
		return s.connect_ex(('127.0.0.1', port)) == 0


def _open_when_started(server, url):
	for _ in range(600):
		if server.started:
			webbrowser.open(url)
			return
		time.sleep(0.1)
