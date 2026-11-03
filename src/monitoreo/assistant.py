"""Assistant of MonitorEO for managers: a chat in the browser, on this computer, with a language model of open weights
served by Ollama (https://ollama.com) and connected to the MCP server of MonitorEO (monitoreo.mcp_server).

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
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import zipfile

from . import __version__, areas, report, services

OUTPUT = os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO')
SETTINGS = os.path.join(OUTPUT, 'assistant.json')
RUNNING = os.path.join(OUTPUT, '.assistant')  # port and token of the assistant that is running
LAYERS = os.path.join(OUTPUT, 'capas')  # the vector files added by the user, and their list capas.json
LAYER_TYPES = ('.gpkg', '.geojson', '.json', '.kml', '.zip')  # .zip: a shapefile (or another of these) compressed
MAX_LAYER = 100 * 2 ** 20  # bytes
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
DEFAULTS = {'project': os.environ.get('EE_PROJECT', ''), 'ollama': 'http://localhost:11434', 'model': 'qwen3:8b',
            'context': 16384, 'think': False}
MAX_STEPS = 8  # answers of the model to a message of the user
MAX_ADVICE = 8000  # characters of the answer of an advice tool that the model gets
MAX_ROWS_SHOWN = 40
PASSED_ENV = ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'no_proxy', 'SSL_CERT_FILE',
              'REQUESTS_CA_BUNDLE', 'PYTHONPATH', 'GOOGLE_APPLICATION_CREDENTIALS')

ADVICE = ('list_variables', 'describe_variable', 'find_protected_areas')  # their answers go to the model
RESULTS = ('time_series', 'region_stats', 'map_layer', 'trend_table', 'trend_map', 'compare_series', 'compare_map',
           'burn_severity')  # their answers go only to the user and the report
HIDDEN = ('collection', 'scale', 'vmin', 'vmax', 'resolution', 'crs', 'lang', 'limit')  # arguments the model does not see
AREA_KEYS = ('SITE_ID', 'NAME', 'DESIG', 'IUCN_CAT', 'ISO3', 'REP_AREA')  # of the protected areas, for the model
DESIGNATIONS = (r'^(el |la )?(parque (nacional|natural|periurbano)|paraje natural|reserva (natural( concertada)?|'
                r'de la biosfera)|monumento natural|paisaje protegido|espacio natural( protegido)?|zona de especial '
                r'conservaci[oó]n|zec|zepa|lic)\b( (de la|de los|de las|del|de)\b)?\s*')  # removed from the searches

LABELS = {'list_variables': 'Consultando las variables del catálogo',
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
	return PROMPT.format(today=(today or dt.date.today()).isoformat(), variables=variables_text())


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
		if t['name'] not in ADVICE + RESULTS:
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
	"""A conversation with the model and the MCP server of MonitorEO, and its results."""

	def __init__(self, settings=None):
		self.settings = settings or load_settings()
		self.session, self.tools, self.system = None, [], instructions()
		self.busy = asyncio.Lock()
		self.layers = load_layers()
		self.reset()

	def reset(self):
		self.messages, self.results, self.names, self.question = [], [], {}, None

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
				self.tools = model_tools([_json(t) for t in listed.tools])
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
		self.messages.append({'role': 'user', 'content': text})
		self.question = self.question or text
		for _ in range(MAX_STEPS):
			yield {'type': 'status', 'text': f"El modelo ({self.settings['model']}) está pensando…"}
			try:
				message = await asyncio.to_thread(chat_model, self.settings, self.system_prompt(), self.messages,
				                                  self.tools)
			except ModelError as e:
				yield {'type': 'error', 'text': f'Modelo de lenguaje: {e}'}
				return
			calls = message.get('tool_calls') or []
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
		if name not in ADVICE + RESULTS:
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
		if name in RESULTS:
			problem = self.not_ready()
			if problem:
				yield {'type': 'error', 'text': problem[0].upper() + problem[1:] + '.'}
				self._tool_message(name, f'Error: no se ha calculado; {problem}.')
				return
			yield {'type': 'running', 'text': f'Calculando en Google Earth Engine: {title}…',
			       'facts': _facts(name, args, None, self.all_names())}
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
		try:
			result = json.loads(texts[0]) if texts else {}
		except ValueError:
			result = {'text': texts[0]}
		item = {'id': len(self.results) + 1, 'tool': name, 'args': args, 'result': result,
		        'image': images[0] if images else None, 'title': _title(name, args)}
		self.results.append(item)
		yield {'type': 'result', **self.card(item)}
		self._tool_message(name, receipt(item['id'], item['title']))

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
		return self.system + '\n\nCapas del usuario (archivos de su ordenador). Para usar una como región: ' \
		                     '{"capa": "nombre"}; cada polígono da su propia serie o fila.\n' + \
		       '\n'.join(f'- {k}: {layer_text(v)}' for k, v in self.layers.items())

	def all_names(self):
		"""The names of the regions for the user: protected areas (by WDPA ID) and layers (by file)."""
		return {**{v['file']: f'Capa «{k}» ({layer_text(v)})' for k, v in self.layers.items()}, **self.names}

	def check_areas(self, args):
		"""Refuse the WDPA IDs that come neither from find_protected_areas nor from the user: small models copy them
		from the examples or make them up."""
		region = args.get('region')
		ids = region.get('wdpa_id') if isinstance(region, dict) else None
		if ids is None:
			return
		said = {x for m in self.messages if m['role'] == 'user' for x in re.findall(r'\d+', m['content'])}
		unknown = [i for i in (ids if isinstance(ids, list) else [ids]) if str(i) not in self.names and str(i) not in said]
		if unknown:
			raise ValueError(f'el wdpa_id {", ".join(map(str, unknown))} no sale de find_protected_areas: busca '
			                 'primero el espacio protegido por su nombre con find_protected_areas y usa su SITE_ID')

	def with_layer(self, args):
		"""ARGS with a region {"capa": name} as the file of that layer."""
		region = args.get('region')
		if not isinstance(region, dict) or not (region.get('capa') or region.get('layer')):
			return args
		key = str(region.get('capa') or region.get('layer')).strip()
		layer = self.layers.get(key) or next((v for k, v in self.layers.items() if key.lower() in (
			k.lower(), v['original'].lower(), os.path.splitext(v['original'])[0].lower())), None)
		if not layer:
			raise ValueError(f'no hay ninguna capa «{key}»; las capas son: {", ".join(self.layers) or "ninguna"}')
		return {**args, 'region': {'file': layer['file'],
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
		s = assistant.settings
		return JSONResponse({'version': __version__, 'signed_in': signed_in(), 'project': s.get('project'),
		                     'model': s['model'], 'ollama': s['ollama'], 'models': await asyncio.to_thread(models, s),
		                     'results': len(assistant.results), 'server': assistant.session is not None,
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
		if assistant.busy.locked():
			raise ValueError('espera a que termine la consulta anterior')

		async def events():
			async with assistant.busy:
				async for e in assistant.chat(text):
					yield e
			yield {'type': 'done'}
		return ndjson(events())

	async def reset(request):
		if assistant.busy.locked():
			raise ValueError('espera a que termine la consulta anterior')
		assistant.reset()
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
		return ndjson(_pull(assistant.settings['ollama'], model))

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
		Route('/api/reset', guarded(reset), methods=['POST']),
		Route('/api/report', guarded(make_report), methods=['POST']),
		Route('/api/pull', guarded(pull), methods=['POST']),
		Route('/api/layer', guarded(add_layer), methods=['POST']),
		Route('/api/layer/remove', guarded(remove_layer), methods=['POST']),
		Route('/files/{path:path}', guarded(files)),
	], lifespan=lambda app: assistant.connected())


async def _pull(base, model):
	"""Download a model with Ollama: yields its progress {status, completed, total}."""
	lines, loop = asyncio.Queue(), asyncio.get_running_loop()

	def work():
		req = urllib.request.Request(base.rstrip('/') + '/api/pull',
		                             data=json.dumps({'model': model, 'name': model}).encode(),  # name: older Ollama
		                             headers={'Content-Type': 'application/json'})
		try:
			with urllib.request.urlopen(req, timeout=60) as r:
				for line in r:
					loop.call_soon_threadsafe(lines.put_nowait, json.loads(line))
		except (urllib.error.URLError, OSError, ValueError) as e:
			loop.call_soon_threadsafe(lines.put_nowait, {'error': f'no se ha podido descargar {model}: {e}'})
		loop.call_soon_threadsafe(lines.put_nowait, None)

	threading.Thread(target=work, daemon=True).start()
	while (line := await lines.get()) is not None:
		yield line


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
	token = secrets.token_urlsafe(16)
	assistant = Assistant()
	server = uvicorn.Server(uvicorn.Config(make_app(assistant, token, port), host='127.0.0.1', port=port,
	                                       log_level='warning'))
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


def _in_use(port):
	with socket.socket() as s:
		return s.connect_ex(('127.0.0.1', port)) == 0


def _open_when_started(server, url):
	for _ in range(600):
		if server.started:
			webbrowser.open(url)
			return
		time.sleep(0.1)
