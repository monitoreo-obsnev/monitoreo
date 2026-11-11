"""The functions of MonitorEO for the tools that use it (QGIS plugin, MCP server, R package, command line).

They take plain values (text, numbers, lists, dictionaries) and return plain values or files, so every tool
computes exactly the same. A variable is given by its name in the catalog of MonitorEO (variable='NDVI',
sensor='Sentinel-2'; see list_variables) or by an Earth Engine source (collection= and band=, or image= and band=).
A region is a dictionary (see areas.region): {'wdpa_id': 555513}, {'ecoregion_id': 793}, {'bbox': [w, s, e, n]},
{'point': [lon, lat], 'buffer': 1000}, {'geojson': ...} or {'file': 'area.gpkg'}.

Besides time series, maps and statistics, the variables are downloaded as GeoTIFFs: one map (download_image, or
export_image to Google Drive), the true colour of the same images (rgb_map and download_rgb: the red, green and blue
reflectance of the images of a variable of Sentinel-2 or Landsat, with the same dates, pixel filters and metric; see
has_rgb) or a recipe of several variables on aligned grids over a study area and its ecoregions
(download_variables, see monitoreo.recipe). The seasonal trends (Mann-Kendall and Sen: trend_table, trend_map,
download_trend) and the comparison of a reference period with another (compare_series, compare_map,
download_comparison) are described in monitoreo.trends. The results of an analysis are published
for anyone in the static web viewer of results with publish_report (see monitoreo.publish).

Call init() first. With a project (init(project) or the variable EE_PROJECT) it computes with the Google account of
`earthengine authenticate` and the quota of that project; without one, with the shared account of MonitorEO, whose
research EECUs (the compute of Earth Engine of each month: the same for each user, who is the anonymous ID of each
installation) are only for research. eecu_usage tells how much of them (or, with the user's own account, of the monthly
EECU quota of their project) has been spent, and the tools warn when less than 10 % is left (see eecu_warning).

Every result says what to cite with it (see monitoreo.references): 'references', the articles of the formula or
algorithm of the variable and of the method, the Earth Engine datasets (cited as their pages of the Earth Engine catalog
suggest), Google Earth Engine and MonitorEO, each {'id', 'citation', 'doi', 'url', 'text'}; and 'credits', the lines
that the terms of use of the data ask for. The files of a result explain themselves (see monitoreo.readme): a README
next to them ('readme' in the answer) and, in the metadata of the GeoTIFFs, the call, the version of MonitorEO, when
it was computed, the references and the name and unit of each band.
"""

import datetime as dt
import functools
import inspect
import json
import math
import os
import re
import time
import warnings

import ee

from . import areas, catalog, charts, composite, drive, fire, maps, references, sensors, timeseries, trends
from . import recipe as recipes
from . import variable as variables
from .grid import Grid, download

# Broker of the shared account of MonitorEO (broker/ in the repository): tokens of one hour of a service account that
# only computes in Earth Engine with the quota of the project of MonitorEO. MONITOREO_BROKER replaces it.
BROKER = 'https://monitoreo-broker-872770286973.europe-west1.run.app'

_project = None
_shared = False


def _cited(fn):
	"""FN with the references of what it computed (monitoreo.references.cite) in its answer, 'references' and
	'credits', and its files documented (monitoreo.readme): the metadata of its GeoTIFF (the call, the version, when
	and the references) and a README next to them, whose path is in the answer ('readme')."""
	sig = inspect.signature(fn)

	@functools.wraps(fn)
	def wrapped(*args, **kwargs):
		out = fn(*args, **kwargs)
		if isinstance(out, dict):
			call = sig.bind(*args, **kwargs)
			given = dict(call.arguments)
			given.update(given.pop('source', None) or {})
			call.apply_defaults()
			a = dict(call.arguments)
			a.update(a.pop('source', None) or {})
			out.update(references.cite(fn.__name__, a))
			try:  # a file that cannot be documented is still the result
				from . import readme
				path = readme.document(fn.__name__, given, out)
				if path:
					out['readme'] = path
			except Exception as e:
				warnings.warn(f'MonitorEO could not document the files of {fn.__name__}: {e}')
		return out
	return wrapped


def tag_references(path, cited):
	"""Write the references and credits of CITED (see monitoreo.references.cite) to the metadata of the GeoTIFF PATH
	(item 'references', a line each)."""
	from osgeo import gdal
	gdal.UseExceptions()
	ds = gdal.Open(path, gdal.GA_Update)
	ds.SetMetadataItem('references', '\n'.join(references.texts(cited)))
	ds = None


def init(project=None, shared=False, warn=True):
	"""Connect to Earth Engine and return the project whose quota is used. With a PROJECT (default: the variable
	EE_PROJECT), with the credentials of `earthengine authenticate` (the Google account of the user) and that Google
	Cloud project registered in Earth Engine. Without one, or with SHARED (whatever EE_PROJECT says: a field of
	project left empty), with the shared account of MonitorEO: a token of one hour from its broker, renewed by itself,
	and the project of MonitorEO; it cannot export to Google Drive (see need_own_account), and each user has research
	EECUs for each month (see eecu_usage): who has spent theirs gets no token until the next month. When it connects,
	with WARN it gives a Python warning (EECUWarning) if less than 10 % of the EECUs of the month are left."""
	global _project, _shared
	project = None if shared else project or os.environ.get('EE_PROJECT') or os.environ.get('GOOGLE_CLOUD_PROJECT')
	if not project:
		was = _shared
		project = _init_shared()
		if warn and not was:
			eecu_warning(python_warning=True)
		return project
	if project == _project and not _shared:
		return project
	try:
		ee.Initialize(project=project)
	except Exception as e:
		raise RuntimeError(f'cannot connect to Earth Engine with the project {project}: {e}. Run '
		                   '`earthengine authenticate` once and check that the project is registered in Earth Engine '
		                   '(https://developers.google.com/earth-engine/guides/access)') from e
	if _shared:  # the computations of the user's own account are not tagged with their ID of the shared account
		ee.data.resetWorkloadTag(True)
	_project, _shared = project, False
	if warn:
		eecu_warning(python_warning=True)
	return project


class BrokerError(RuntimeError):
	"""An answer of the broker of the shared account that is not a success: its CODE ('spent': the user has spent their
	research EECUs of the month; 'project': the users of the shared account have spent all those of the project but its
	reserve; 'user': a version without the ID of its user) and its DETAILS."""

	def __init__(self, message, code=None, details=None):
		super().__init__(message)
		self.code, self.details = code, details or {}


def _broker(path, body=None, timeout=30, **params):
	"""The answer (JSON) of PATH of the broker of the shared account of MonitorEO, with PARAMS in its query (and BODY,
	posted as JSON)."""
	import requests  # a dependency of earthengine-api, with the certificates of certifi (also in QGIS)
	url = os.environ.get('MONITOREO_BROKER', BROKER).rstrip('/') + path
	if params:
		import urllib.parse
		url += '?' + urllib.parse.urlencode(params)
	headers = {'User-Agent': 'monitoreo'}
	if body is None:
		r = requests.get(url, timeout=timeout, headers=headers)
	else:
		r = requests.post(url, json=body, timeout=timeout, headers=headers)
	if r.status_code != 200:
		if 'json' not in r.headers.get('Content-Type', ''):
			raise BrokerError(str(r.status_code))
		d = r.json()
		raise BrokerError(d.get('error') or str(r.status_code), d.get('code'), d)
	return r.json()


USER_FILE = os.path.join('~', '.config', 'monitoreo', 'user_id')
_user = None


def user_id():
	"""The anonymous ID of this installation for the shared account of MonitorEO (mo- and 16 hexadecimal digits), made
	at random the first time and kept in USER_FILE: it tags the computations of the user in Earth Engine (its workload
	tag), so that the broker knows the research EECUs that each one spends. It says nothing about the user."""
	global _user
	if _user:
		return _user
	path = os.path.expanduser(USER_FILE)
	try:
		with open(path, encoding='utf-8') as f:
			found = f.read().strip()
		if re.fullmatch(r'mo-[0-9a-f]{16}', found):
			_user = found
			return _user
	except OSError:
		pass
	import secrets
	_user = 'mo-' + secrets.token_hex(8)
	try:
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, 'w', encoding='utf-8') as f:
			f.write(_user + '\n')
	except OSError:  # a folder without permission to write: an ID for this session only
		pass
	return _user


def _shared_token():
	"""(token, expiry as a naive UTC datetime, project) of the shared account of MonitorEO, from its broker."""
	d = _broker('/token', user=user_id())
	expiry = dt.datetime.fromtimestamp(d['expires_at'], dt.timezone.utc).replace(tzinfo=None)
	return d['access_token'], expiry, d['project']


OWN_ACCOUNT = ('use your own account: run `earthengine authenticate` once and give your Google Cloud project '
               '(init(project=...) or the variable EE_PROJECT)')


def _init_shared():
	global _project, _shared
	if _shared:
		return _project
	import google.oauth2.credentials
	try:
		token, expiry, project = _shared_token()
		credentials = google.oauth2.credentials.Credentials(
			token, expiry=expiry, refresh_handler=lambda request, scopes=None: _shared_token()[:2])
		ee.Initialize(credentials=credentials, project=project)
		ee.data.setDefaultWorkloadTag(user_id())  # what this user computes: their research EECUs
	except BrokerError as e:
		if e.code in ('spent', 'project'):  # the user, or all the users, have spent the research EECUs of the month
			raise RuntimeError(f'{e}. Meanwhile, {OWN_ACCOUNT}') from e
		raise RuntimeError(f'cannot connect to Earth Engine with the shared account of MonitorEO: {e}. Try again later '
		                   f'or {OWN_ACCOUNT}') from e
	except Exception as e:
		raise RuntimeError(f'cannot connect to Earth Engine with the shared account of MonitorEO: {e}. Try again later '
		                   f'or {OWN_ACCOUNT}') from e
	_project, _shared = project, True
	return project


def project():
	return _project


def shared():
	"""Whether Earth Engine is used with the shared account of MonitorEO (and not with the user's own)."""
	return _shared


def need_own_account(what='Exporting to Google Drive'):
	"""Stop with a clear message when WHAT cannot be done with the shared account of MonitorEO."""
	if _shared:
		raise RuntimeError(f'{what} needs your own Earth Engine account (the files go to the Google Drive of the '
		                   'account that computes): run `earthengine authenticate` once and give your Google Cloud '
		                   'project (init(project=...) or the variable EE_PROJECT). With the shared account of '
		                   'MonitorEO, download_image and download_variables save the GeoTIFFs on this computer.')


# EECU: the compute of Earth Engine spent this month ----------------------------------------------------------------

EECU_METRIC = 'earthengine.googleapis.com/project/cpu/usage_time'  # "Completed EECU-seconds" of Cloud Monitoring
EECU_TIERS = {'Community': 150, 'Contributor': 1000, 'Partner': 100000}  # EECU-hours a month of the noncommercial tiers
KNOWN_TIERS = {'ee-ugr-default-project': 'Contributor'}  # the tier of the projects that MonitorEO knows: its own
EECU_LOW = 10  # percent of the EECU of the month left under which the tools warn
EECU_TTL = 300  # seconds that an answer of eecu_usage is used again
TIERS_URL = 'https://developers.google.com/earth-engine/guides/noncommercial_tiers'
_eecu = {}  # (project or None, shared) -> (time, EECU-hours spent, limit of the broker or None, start of the month)
_eecu_warned = set()

_EECU_TEXT = {
	'es': {
		'name_shared': 'research EECUs', 'name_own': 'EECU de tu proyecto', 'tier': ', nivel {tier}',
		'text_shared': 'research EECUs: {used_pct} % gastado ({used} de tus {limit} EECU-h de este mes con la cuenta '
		               'compartida de MonitorEO). Te queda el {left_pct} %; se renuevan el {resets}.',
		'text_own': 'EECU de tu proyecto: {used_pct} % gastado ({used} de {limit} EECU-h este mes; proyecto {project}'
		            '{tier}). Queda el {left_pct} %; se renueva el {resets}.',
		'low_shared': 'Te quedan menos del {low} % de tus research EECUs de este mes ({used} de {limit} EECU-h '
		              'gastados).',
		'out_shared': 'Has gastado tus research EECUs de este mes ({used} de {limit} EECU-h): la cuenta compartida de '
		              'MonitorEO no calcula para ti hasta el {resets}.',
		'project_shared': ' La cuenta compartida solo tiene {project_left} EECU-h para todos sus usuarios hasta el '
		                  '{resets}, así que te quedan {left}.',
		'out_project': 'La cuenta compartida de MonitorEO ha gastado los EECU de este mes para sus usuarios: no calcula '
		               'hasta el {resets}.',
		'shared': ' Son solo para investigación y cada usuario tiene los suyos: cambia a tu propia cuenta de Earth '
		          'Engine (inicia sesión con tu cuenta de Google y usa tu proyecto de Google Cloud) para seguir '
		          'calculando.',
		'low_own': 'Queda menos del {low} % de la cuota mensual de EECU del proyecto {project} ({used} de {limit} EECU-h '
		           'gastados{tier}).',
		'out_own': 'Se ha agotado la cuota mensual de EECU del proyecto {project} ({used} de {limit} EECU-h{tier}).',
		'own': ' Sin ella, Earth Engine calcula más despacio (modo restringido) hasta el {resets}. Para tener más, sube '
		       'de nivel el proyecto: https://console.cloud.google.com/earth-engine/configuration?project={project}',
		'disabled': 'para ver los EECU gastados, activa la API de Cloud Monitoring (gratuita) en el proyecto {project}: '
		            'https://console.cloud.google.com/apis/library/monitoring.googleapis.com?project={project}',
		'scope': 'tus credenciales de Earth Engine no pueden leer Cloud Monitoring: vuelve a iniciar sesión '
		         '(`earthengine authenticate --force`)',
		'denied': 'tu cuenta de Google no puede leer los EECU gastados del proyecto {project}: necesita el rol '
		          'Monitoring Viewer (roles/monitoring.viewer) y Service Usage Consumer en el proyecto',
		'broker': 'no se pueden consultar tus research EECUs de la cuenta compartida de MonitorEO: {error}',
	},
	'en': {
		'name_shared': 'research EECUs', 'name_own': 'EECUs of your project', 'tier': ', {tier} tier',
		'text_shared': 'research EECUs: {used_pct}% used ({used} of your {limit} EECU-hours of this month with the '
		               'shared account of MonitorEO). {left_pct}% left; they restart on {resets}.',
		'text_own': 'EECUs of your project: {used_pct}% used ({used} of {limit} EECU-hours this month; project '
		            '{project}{tier}). {left_pct}% left; it restarts on {resets}.',
		'low_shared': 'Less than {low}% of your research EECUs of this month are left ({used} of {limit} EECU-hours '
		              'used).',
		'out_shared': 'You have spent your research EECUs of this month ({used} of {limit} EECU-hours): the shared '
		              'account of MonitorEO does not compute for you until {resets}.',
		'project_shared': ' The shared account has only {project_left} EECU-hours left for all its users until '
		                  '{resets}, so you have {left} left.',
		'out_project': 'The shared account of MonitorEO has spent the EECUs of this month for its users: it does not '
		               'compute until {resets}.',
		'shared': ' They are only for research and each user has their own: switch to your own Earth Engine account '
		          '(sign in with your Google account, `earthengine authenticate`, and use your Google Cloud project) to '
		          'keep computing.',
		'low_own': 'Less than {low}% of the monthly EECU quota of the project {project} is left ({used} of {limit} '
		           'EECU-hours used{tier}).',
		'out_own': 'The monthly EECU quota of the project {project} is spent ({used} of {limit} EECU-hours{tier}).',
		'own': ' Without it, Earth Engine computes more slowly (restricted mode) until {resets}. For more, raise the '
		       'tier of the project: https://console.cloud.google.com/earth-engine/configuration?project={project}',
		'disabled': 'to see the EECUs spent, enable the Cloud Monitoring API (free) in the project {project}: '
		            'https://console.cloud.google.com/apis/library/monitoring.googleapis.com?project={project}',
		'scope': 'your Earth Engine credentials cannot read Cloud Monitoring: sign in again '
		         '(`earthengine authenticate --force`)',
		'denied': 'your Google account cannot read the EECUs spent by the project {project}: it needs the roles '
		          'Monitoring Viewer (roles/monitoring.viewer) and Service Usage Consumer in the project',
		'broker': 'cannot get your research EECUs of the shared account of MonitorEO: {error}',
	},
}


class EECUWarning(UserWarning):
	"""Less than EECU_LOW % of the EECU of the month are left (see eecu_warning)."""


def eecu_limit(limit=None, project=None):
	"""EECU-hours a month of the quota of the user's own PROJECT: that of its tier if MonitorEO knows it (KNOWN_TIERS:
	the project of MonitorEO, Contributor), else LIMIT (hours, or the name of a noncommercial tier of Earth Engine:
	Community, Contributor or Partner), the variable MONITOREO_EECU_LIMIT or 150, that of the Community tier (every
	noncommercial project; see TIERS_URL). Earth Engine does not tell the tier of a project."""
	limit = KNOWN_TIERS.get(project) or limit or os.environ.get('MONITOREO_EECU_LIMIT') or 'Community'
	tiers = {k.lower(): v for k, v in EECU_TIERS.items()}
	if str(limit).strip().lower() in tiers:
		return float(tiers[str(limit).strip().lower()])
	try:
		value = float(limit)
	except (TypeError, ValueError):
		value = 0
	if not value > 0:
		raise ValueError(f'the monthly EECU quota is a number of EECU-hours or a tier ({", ".join(EECU_TIERS)}), '
		                 f'not {limit}')
	return value


def eecu_month(now=None):
	"""(start of the month of the quotas of Earth Engine as a UTC datetime, first day of the next month): they restart
	on the first day of each month at midnight Pacific Time."""
	try:
		from zoneinfo import ZoneInfo
		tz = ZoneInfo('America/Los_Angeles')
	except Exception:  # without the database of time zones (Windows without tzdata): the Pacific standard time
		tz = dt.timezone(dt.timedelta(hours=-8))
	local = (now or dt.datetime.now(dt.timezone.utc)).astimezone(tz)
	start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
	return start.astimezone(dt.timezone.utc), (start.date() + dt.timedelta(days=32)).replace(day=1)


def eecu_hours(session, project, start, end=None):
	"""EECU-hours of the computations completed by PROJECT between START and END (UTC datetimes; default: now), from
	the metric "Completed EECU-seconds" of Cloud Monitoring, with SESSION (requests, authorized to read it)."""
	end = end or dt.datetime.now(dt.timezone.utc)
	params = {'filter': f'metric.type = "{EECU_METRIC}"',
	          'interval.startTime': start.strftime('%Y-%m-%dT%H:%M:%SZ'),
	          'interval.endTime': end.strftime('%Y-%m-%dT%H:%M:%SZ'),
	          'aggregation.alignmentPeriod': '86400s', 'aggregation.perSeriesAligner': 'ALIGN_SUM',
	          'aggregation.crossSeriesReducer': 'REDUCE_SUM'}
	seconds = 0.0
	while True:
		r = session.get(f'https://monitoring.googleapis.com/v3/projects/{project}/timeSeries', params=params,
		                timeout=30)
		if r.status_code != 200:
			raise _MonitoringError(r)
		d = r.json()
		for series in d.get('timeSeries', []):
			for p in series.get('points', []):
				v = p.get('value', {})
				seconds += float(v.get('doubleValue', v.get('int64Value', 0)))
		if not d.get('nextPageToken'):
			return seconds / 3600
		params['pageToken'] = d['nextPageToken']


class _MonitoringError(RuntimeError):
	def __init__(self, response):
		try:
			error = response.json()['error']
		except Exception:
			error = {'message': str(response.status_code)}
		reasons = [x.get('reason') for x in error.get('details', []) if isinstance(x, dict)]
		self.reason = 'disabled' if 'SERVICE_DISABLED' in reasons else \
			'scope' if 'ACCESS_TOKEN_SCOPE_INSUFFICIENT' in reasons else \
			'denied' if response.status_code == 403 else None
		super().__init__(error.get('message') or response.status_code)


def _ee_credentials():
	"""The credentials with which Earth Engine was initialized (those of `earthengine authenticate`)."""
	state = getattr(ee.data, '_get_state', None)
	credentials = getattr(state(), 'credentials', None) if state else getattr(ee.data, '_credentials', None)
	return credentials or ee.data.get_persistent_credentials()


def _own_eecu_hours(project, start):
	import google.auth.transport.requests
	session = google.auth.transport.requests.AuthorizedSession(_ee_credentials())
	session.headers['x-goog-user-project'] = project  # the quota of the user's project, not that of the client of EE
	return eecu_hours(session, project, start)


def _number(x, lang, decimals=1):
	text = f'{x:,.{decimals}f}'
	return text.replace(',', '\u202f').replace('.', ',') if lang == 'es' else text


_MONTHS = {'es': ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
                   'noviembre', 'diciembre'],
           'en': ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
                  'November', 'December']}


def _day(day, lang):
	month = _MONTHS[lang][day.month - 1]
	return f'{day.day} de {month}' if lang == 'es' else f'{month} {day.day}'


def eecu_usage(limit=None, refresh=False, lang='en', shared=None):
	"""The EECUs (compute units of Earth Engine) spent this month, against their limit. With the shared account of
	MonitorEO they are the research EECUs of this user (see user_id), only for research: each user has the same
	EECU-hours a month (those of the broker, 25), so that no one spends the quota of the project of everyone, and who
	has spent theirs gets no more tokens until the next month; what is left (left_hours) is also at most what is left
	of the quota of the project (1,000 EECU-hours, Contributor tier) for all the users of the shared account, the
	project keeping a reserve for the app of Earth Engine. With the user's own account, those of their project,
	from Cloud Monitoring (whose API must be enabled in the project; the user needs the role Monitoring Viewer),
	against the monthly quota of its tier, LIMIT (see eecu_limit); when it is spent, Earth Engine computes more slowly.
	SHARED chooses the account; by default that connected or, before connecting, the shared one if there is no project
	in EE_PROJECT (the research EECUs are asked to the broker without connecting, also when they are spent). Both restart
	on the first day of each month. Answers are kept EECU_TTL seconds (REFRESH asks again). Returns {account ('shared'
	or 'own'), name, project, used_hours, limit_hours, left_hours, tier, used_percent, left_percent, month, resets, low,
	warning (None or why to worry), text, bar}, with the texts in LANG ('en' or 'es')."""
	lang = 'es' if lang == 'es' else 'en'
	t = _EECU_TEXT[lang]
	if shared is None:
		shared = _shared if _project else not (os.environ.get('EE_PROJECT') or os.environ.get('GOOGLE_CLOUD_PROJECT'))
	if not shared and (not _project or _shared):
		init(warn=False)
		if _shared:
			raise RuntimeError('there is no project of your own: give it with init(project) or the variable EE_PROJECT')
	own_limit = None if shared else eecu_limit(limit, _project)
	start, resets = eecu_month()
	key = (None if shared else _project, shared)
	hit = _eecu.get(key)
	if refresh or not hit or time.time() - hit['time'] > EECU_TTL or hit['start'] != start:
		try:
			if shared:
				d = _broker('/usage', user=user_id())
				hit = {'used': float(d['used_hours']), 'limit': float(d['limit_hours']), 'project': d.get('project'),
				       'left': d.get('left_hours'), 'project_left': d.get('project_left_hours')}
			else:
				hit = {'used': _own_eecu_hours(_project, start), 'limit': None, 'project': _project}
		except _MonitoringError as e:
			raise RuntimeError(t[e.reason].format(project=_project) if e.reason else str(e)) from e
		except Exception as e:
			if shared:
				raise RuntimeError(t['broker'].format(error=e)) from e
			raise
		hit.update(time=time.time(), start=start)
		_eecu[key] = hit
	used, limit, project = hit['used'], hit['limit'] or own_limit, hit['project']
	tier = None if shared else next((k for k, v in EECU_TIERS.items() if v == limit), None)
	used_pct = round(100 * used / limit, 1)
	# with the shared account, the broker says what is left: at most what is left of the project for all its users
	left = max(0.0, limit - used) if hit.get('left') is None else max(0.0, float(hit['left']))
	by_project = shared and left < limit - used - 0.005
	left_pct = round(max(0.0, 100 * left / limit), 1)
	kind = 'shared' if shared else 'own'
	values = {'project': project, 'low': EECU_LOW, 'used': _number(used, lang, 2 if used < 10 else 1),
	          'limit': _number(limit, lang, 1 if limit % 1 else 0), 'used_pct': _number(used_pct, lang),
	          'left_pct': _number(left_pct, lang), 'tier': t['tier'].format(tier=tier) if tier else '',
	          'resets': _day(resets, lang), 'left': _number(left, lang, 2 if left < 10 else 1),
	          'project_left': _number(float(hit.get('project_left') or 0), lang, 0)}
	warning = None
	if left_pct < EECU_LOW:
		out_key = 'out_project' if by_project and left <= 0 else ('out_' if left_pct <= 0 else 'low_') + kind
		warning = (t[out_key] + t[kind]).format(**values)
	text = t['text_' + kind].format(**values) + (t['project_shared'].format(**values) if by_project else '')
	out = {'account': kind, 'name': t['name_' + kind], 'project': project, 'used_hours': round(used, 2),
	       'limit_hours': limit, 'left_hours': round(left, 2), 'tier': tier, 'used_percent': used_pct,
	       'left_percent': left_pct, 'month': start.isoformat(), 'resets': resets.isoformat(), 'low': left_pct < EECU_LOW,
	       'warning': warning, 'text': text}
	out['bar'] = eecu_bar(out)
	return out


def eecu_bar(usage, width=30):
	"""A bar of text of the percent spent of eecu_usage: [##########--------------------] 33.3%. The bar is what can
	no longer be used (100 % minus what is left: with the shared account, also what the project has no more)."""
	gone = 100 - usage.get('left_percent', 100 - usage['used_percent'])
	filled = min(width, max(0, round(width * gone / 100)))
	return f"[{'#' * filled}{'-' * (width - filled)}] {usage['used_percent']:g}%"


def eecu_warning(lang='en', limit=None, once=False, python_warning=False):
	"""The warning of eecu_usage when less than EECU_LOW % of the EECU of the month are left, or None (also when
	Earth Engine is not connected or the EECU cannot be read: it never fails, so the tools call it after computing).
	With ONCE, only the first time of each project and month; with PYTHON_WARNING, also as an EECUWarning."""
	if not _project:
		return None
	try:
		usage = eecu_usage(limit, lang=lang)
	except Exception:
		return None
	if not usage['warning']:
		return None
	key = (usage['project'], usage['account'], usage['month'])
	if once and key in _eecu_warned:
		return None
	_eecu_warned.add(key)
	if python_warning:
		warnings.warn(usage['warning'], EECUWarning, stacklevel=3)
	return usage['warning']


def about(lang='en'):
	"""What MonitorEO-OBSNEV is, who funds it and how to cite it: {'name', 'description', 'acknowledgements',
	'citation', 'doi', 'earth_engine' (the citation of Google Earth Engine, where MonitorEO computes), 'logos' (image
	files), 'manual', 'repository'} in LANG ('en' or 'es')."""
	from . import about as about_
	return about_.about(lang)


# Catalog -----------------------------------------------------------------------------------------------------------

def _name(e, lang, field):
	return e.get(f'{field}_{lang}') or e[field] if lang != 'es' else e[field]


def list_variables(sensor=None, text=None, lang='en', theme=None):
	"""Variables of the catalog of MonitorEO: [{ref, variable, sensor, collection, name, theme (its theme in the menus
	of the tools, see themes), group (its class of ecosystem functioning), resolution_m, dates, unit}] (and
	two_periods, RBR, or metric, the only metric of the SCF, and rgb when its images have a true colour, see has_rgb),
	optionally of one SENSOR, of one THEME (its key or its
	name) or with TEXT in their variable or their name (in English or in Spanish, whatever LANG is)."""
	out = []
	wanted = _theme(theme) if theme else None
	for e in catalog.variables():
		if sensor and e['sensor'].lower() != str(sensor).lower():
			continue
		if wanted and e.get('theme') != wanted['key']:
			continue
		t = catalog.theme_of(e['index']) or {}
		row = {'ref': e['ref'], 'variable': e['index'], 'sensor': e['sensor'], 'collection': e['col'],
		       'name': _name(e, lang, 'vname'), 'theme': t.get(lang) or t.get('en'), 'group': _name(e, lang, 'type'),
		       'resolution_m': e['m'], 'dates': e['dr'], 'unit': e['unit']}
		if e.get('two_periods'):
			row['two_periods'] = True  # RBR: only burn_severity computes it
		if e.get('metric'):
			row['metric'] = e['metric']  # its only metric (SCF: the mean)
		if sensors.fixed_filters(e) is not None:
			row['fixed_filters'] = sensors.fixed_filters(e)  # always on, whatever the quality (SCF: clouds, water)
		if e.get('static'):
			row['static'] = True  # elevation, slope: without dates, only maps and their statistics
		if sensors.rgb_of(e):
			row['rgb'] = True  # its images have a true colour (rgb_map, download_rgb)
		if text and str(text).lower() not in f"{row['variable']} {e['vname']} {e.get('vname_en', '')}".lower():
			continue
		out.append(row)
	return out


def themes(lang='en'):
	"""The themes of the menus of the tools (see catalog.THEMES): [{key, name, variables (their codes), analyses (those
	of the theme besides maps, series, trends, comparisons and exports)}], in LANG ('en' or 'es')."""
	return [{'key': t['key'], 'name': t.get(lang) or t['en'], 'variables': list(t['indices']),
	         'analyses': list(t.get('analyses') or [])} for t in catalog.THEMES]


def _theme(theme):
	low = str(theme).strip().lower()
	for t in catalog.THEMES:
		if low in (t['key'], t['en'].lower(), t['es'].lower()):
			return t
	raise ValueError(f"unknown theme {theme}: use {', '.join(t['key'] for t in catalog.THEMES)}")


def describe_variable(variable_name, sensor=None, collection=None, ref=None, lang='en'):
	"""Everything about a variable of the catalog: formula, collection, scale, unit, pixel filters, notes, ... and what
	to cite with its data: 'references' (the articles of its formula or algorithm, its Earth Engine datasets as their
	catalog pages suggest and the pixel filters) and 'credits' (see monitoreo.references)."""
	e = catalog.find(variable_name, sensor, collection, ref)
	out = {k: e.get(k) for k in ('ref', 'index', 'sensor', 'col', 'm', 'tr', 'dr', 'unit', 'ft', 'scale', 'offset')}
	out['name'] = _name(e, lang, 'vname')
	t = catalog.theme_of(e['index']) or {}
	out['theme'] = t.get(lang) or t.get('en')
	out['group'] = _name(e, lang, 'type')
	out['pixel_filters'] = sensors.filters(e)
	out['measures'] = [f for f, idx in sensors.MEASURES.items() if e['index'] in idx]
	out['notes'] = e.get('notes', {})
	if e.get('metric'):
		out['metric'] = e['metric']  # its only metric (SCF: the mean)
	if sensors.fixed_filters(e) is not None:
		out['fixed_filters'] = sensors.fixed_filters(e)  # always on, whatever the quality (SCF: clouds, water)
	if e.get('static'):
		out['static'] = True  # elevation, slope: without dates, only maps and their statistics
	out['rgb'] = sensors.rgb_of(e) is not None  # its images have a true colour (rgb_map, download_rgb)
	if e['ref'] in catalog.FIXES:
		out['fixed'] = catalog.FIXES[e['ref']]
	out['alternatives'] = [a['col'] for a in catalog.alternatives(e)]
	out.update(references.of_entry(e))  # references (formula, Earth Engine datasets, pixel filters) and credits
	return out


def find_protected_areas(text, limit=20, designation=None):
	"""Protected areas of WDPA whose name contains TEXT: [{SITE_ID (WDPA ID), NAME, DESIG, IUCN_CAT, ISO3, REP_AREA, ...}];
	with DESIGNATION 'ramsar', only the Ramsar sites (Wetlands of International Importance)."""
	return areas.find_protected_areas(text, limit, designation)


def find_admin_units(text, level=1, country=None, limit=20):
	"""Administrative units of FAO GAUL 2025 whose name contains TEXT: of LEVEL 1 (regions, states, provinces...) or 2
	(provinces, districts, municipalities...), in COUNTRY (ISO3 code) if given: [{GAUL1_CODE or GAUL2_CODE, the names,
	ISO3_CODE, DISP_EN, level}]. Use the code as {"admin1": ...} or {"admin2": ...}, and a country as
	{"country": "ESP"}."""
	return areas.find_admin_units(text, level, country, limit)


# Variables ---------------------------------------------------------------------------------------------------------

def make_spec(variable=None, sensor=None, start=None, end=None, metric='mean', temporal='period', interannual='mean',
              season=None, quality=None, collection=None, band=None, image=None, ref=None, band_scale=None,
              band_offset=None, terrain=None, exclude_landcover=None, where=None, two_periods=False):
	"""Spec of a variable (see monitoreo.variable) from the arguments of the services (TWO_PERIODS: also the
	variables that compare two periods, RBR, for burn_severity). WHERE: the pixels of the study area to keep, a list of
	conditions on variables (see variable.where_specs), e.g. [{'variable': 'ELEVATION', 'sensor': 'Copernicus',
	'min': 1500}]; every tool that takes a region takes it."""
	var = {'metric': metric, 'temporal': temporal, 'interannual': interannual, 'season': season,
	       'quality': quality or {}, 'exclude_landcover': exclude_landcover, 'where': where}
	if start or end:
		var['period'] = [str(start), str(end or dt.date.today().isoformat())]
	if variable or ref is not None:
		var.update({'index': variable, 'sensor': sensor, 'collection': collection, 'ref': ref})
		if ref is not None and not variable:
			var['index'] = catalog.find(None, ref=ref)['index']
	elif image:
		var.update({'image': image, 'band': band, 'terrain': terrain})
		var.pop('metric')
	elif collection:
		var.update({'collection': collection, 'band': band})
	if band_scale is not None:
		var['scale'] = band_scale
	if band_offset is not None:
		var['offset'] = band_offset
	var = {k: v for k, v in var.items() if v is not None}
	return variable_specs(var, two_periods)[0]


def variable_specs(var, two_periods=False):
	return variables.specs(var, two_periods=two_periods)


def _title(spec, step=None, metric=None, stat=None):
	k = variables.kind(spec)
	if k == 'catalog':
		e = variables.entry_of(spec)
		name = f"{e['index']} {e['sensor']}"
	else:
		name = f"{spec.get(k)} {spec.get('band') or ''}".strip()
	period = f"{spec['period'][0]} / {spec['period'][1]}" if spec.get('period') and not variables.is_static(spec) else ''
	parts = [name, period]
	if step:
		parts.append(f'{step} {metric}, spatial {stat}')
	return ' | '.join(p for p in parts if p)


def _named(spec, metric):
	"""Name of a map of SPEC: its title and METRIC (not for the fixed layers, elevation and slope)."""
	return _title(spec) + ('' if variables.is_static(spec) else f' ({metric})')


def _unit(spec):
	"""The unit of the values of SPEC (that of the catalog, or a total for the sums: see catalog.unit_of)."""
	return catalog.unit_of(variables.entry_of(spec)['unit'], spec.get('metric')) if variables.kind(spec) == 'catalog' \
		else ''


def _ylabel(spec):
	"""Title of the y axis of the charts of SPEC: the unit, after the axis title of the catalog if it has one (e.g.
	'Snow Cover Frequency (SCF) [%]')."""
	unit = _unit(spec)
	axis = variables.entry_of(spec).get('axis') if variables.kind(spec) == 'catalog' else None
	return f'{axis} {unit}'.strip() if axis else unit


def _slug(text):
	return re.sub(r'[^A-Za-z0-9_-]+', '_', str(text)).strip('_')[:80]


# Time series -------------------------------------------------------------------------------------------------------

@_cited
def time_series(region, variable=None, sensor=None, start=None, end=None, step='monthly', metric='mean', stat='mean',
                season=None, quality=None, scale=None, csv=None, chart=None, progress=None, **source):
	"""Time series of a variable over REGION (one or several features): a value per STEP ('daily', '16-day',
	'monthly', 'annual') and region, reduced in time with METRIC and over the region with STAT (mean, median, min,
	max, std or pN). Writes the table to CSV and the chart to CHART (PNG) if given.
	Returns {'rows': [{region, date, value, n_pixels, n_images}], 'csv', 'chart', 'scale', 'unit', 'title'}."""
	spec = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	variables.check_dates(spec, 'time series')
	regions = areas.region(region)
	rows, used_scale = timeseries.series(spec, regions, step, metric, stat, scale, progress)
	unit = _unit(spec)
	title = _title(spec, step, metric, stat)
	out = {'rows': rows, 'csv': None, 'chart': None, 'scale': used_scale, 'unit': unit, 'ylabel': _ylabel(spec),
	       'title': title, 'n_steps': len({r['date'] for r in rows}), 'regions': sorted({r['region'] for r in rows})}
	if csv:
		meta = {'variable': variable or source.get('collection') or source.get('image'), 'sensor': sensor or '',
		        'step': step, 'metric': metric, 'stat': stat, 'unit': catalog.udunits(unit), 'scale_m': used_scale}
		out['csv'] = timeseries.write_csv(rows, csv, meta)
	if chart and rows:
		try:
			charts.time_series_png(rows, chart, title=title, ylabel=out['ylabel'] or None)
			out['chart'] = chart
		except ImportError:  # no matplotlib: the table and the CSV are still there
			pass
	return out


@_cited
def time_series_to_drive(region, variable=None, sensor=None, start=None, end=None, step='monthly', metric='mean',
                         stat='mean', season=None, quality=None, scale=None, folder='MonitorEO', name=None, **source):
	"""Export the time series to a CSV file in FOLDER of Google Drive (for long series or many regions).
	Returns {'operation', 'file', 'folder'}."""
	need_own_account()
	spec = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	variables.check_dates(spec, 'time series')
	regions = areas.region(region)
	table = timeseries.table(spec, regions, step, metric, stat, scale)
	name = _slug(name or f"{variable or source.get('collection')}_{sensor or ''}_{step}_{metric}_{start}_{end}")
	task = ee.batch.Export.table.toDrive(collection=table, description=name[:100], folder=folder, fileNamePrefix=name,
	                                     fileFormat='CSV', selectors=timeseries.COLUMNS)
	task.start()
	return {'operation': task.operation_name or f'projects/{_project}/operations/{task.id}', 'file': name + '.csv',
	        'folder': folder}


# Maps --------------------------------------------------------------------------------------------------------------

def composite_image(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                    interannual='mean', season=None, quality=None, clip=True, resolution=None, **source):
	"""Earth Engine image (ee.Image, band 'value') of a variable over REGION aggregated in time (for rgee, geemap,
	...). Returns (image, regions)."""
	_, regions, img, _ = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                            quality, clip, resolution, source)
	return img, regions


def _build(region, var_name, sensor, start, end, metric, temporal, interannual, season, quality, clip, res, source,
           rgb=False):
	spec = make_spec(var_name, sensor, start, end, metric=metric, temporal=temporal, interannual=interannual,
	                 season=season, quality=quality, **source)
	if rgb:
		variables.check_rgb(spec)  # before Earth Engine
	regions = areas.region(region)
	res = res or variables.native_scale(spec)
	img = variables.image(spec, regions.geometry(), res, rgb)
	if clip:
		img = img.clipToCollection(regions)
	return spec, regions, img, res


@_cited
def map_layer(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
              interannual='mean', season=None, quality=None, vmin=None, vmax=None, palette=None, clip=True,
              thumbnail=None, quick=False, **source):
	"""Map of a variable over REGION aggregated in time (e.g. the median NDVI of 2018-2021): URL of its Earth
	Engine tiles (XYZ, valid for some hours; their values cannot be queried: download_image for that) and colour
	ramp (from the map, or from the catalog if QUICK: computing it over big regions and long periods takes long).
	Writes a PNG preview to THUMBNAIL if given.
	Returns {'url', 'min', 'max', 'palette', 'name', 'unit', 'bounds' (of the region, [w, s, e, n]), 'thumbnail'}."""
	spec, regions, img, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                 quality, clip, None, source)
	entry = variable_entry(spec)
	vis = maps.vis_params(img, regions.geometry(), entry, res, vmin, vmax, palette, compute=not quick)
	out = dict(vis, url=maps.tile_url(img, vis), name=_named(spec, metric), unit=_unit(spec),
	           bounds=_bounds(regions), thumbnail=None)
	if thumbnail:
		maps.thumbnail(maps.with_outline(img, vis, regions), regions.geometry().bounds(), None, path=thumbnail)
		out['thumbnail'] = thumbnail
	return out


def has_rgb(variable=None, sensor=None, collection=None, ref=None):
	"""Whether the images of a variable of the catalog have a true colour (rgb_map, download_rgb): those of Sentinel-2
	and Landsat and the cloud frequency of MODIS (MOD09GA, MYD09GA); not the fixed layers, the climate nor the other
	MODIS products (MOD13Q1 has no green band)."""
	try:
		e = catalog.find(variable, sensor, collection, ref)
	except (KeyError, ValueError):
		return False
	return sensors.rgb_of(e) is not None


def _rgb_name(spec, metric):
	return f'{_named(spec, metric)}, true colour'


@_cited
def rgb_map(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
            interannual='mean', season=None, quality=None, vmin=None, vmax=None, clip=True, thumbnail=None, quick=False,
            **source):
	"""True colour map of the images of a variable over REGION: the red, green and blue surface reflectance of the
	same images and pixels as its map (map_layer with the same arguments: sensor, period, season, pixel filters,
	where), aggregated in time with the same METRIC: median, mean and pN band by band; max and min, the colour of the
	image where the variable is highest or lowest on each pixel (sum, std, count and mode give no colours). URL of its
	Earth Engine tiles (XYZ, valid for some hours), with the three bands stretched together between VMIN and VMAX
	(reflectance; by default the lowest percentile 2 and the highest percentile 98 of the bands over the region, or 0
	to 0.3 if QUICK). Only the variables whose images have red, green and blue bands (see has_rgb). Writes a PNG
	preview to THUMBNAIL if given.
	Returns {'url', 'bands', 'min', 'max', 'name', 'unit', 'bounds' (of the region, [w, s, e, n]), 'thumbnail'}."""
	spec, regions, img, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                 quality, clip, None, source, rgb=True)
	vis = maps.rgb_vis(img, regions.geometry(), res, vmin, vmax, compute=not quick)
	out = dict(vis, url=maps.tile_url(img, vis), name=_rgb_name(spec, metric), unit=catalog.RGB_UNIT,
	           bounds=_bounds(regions), thumbnail=None)
	if thumbnail:
		maps.thumbnail(maps.with_outline(img, vis, regions), regions.geometry().bounds(), None, path=thumbnail)
		out['thumbnail'] = thumbnail
	return out


def _bounds(regions):
	"""[west, south, east, north] (degrees) of REGIONS."""
	ring = regions.geometry().bounds(1).getInfo()['coordinates'][0]
	return [min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring)]


def variable_entry(spec):
	return variables.entry_of(spec) if variables.kind(spec) == 'catalog' else None


def thumbnail(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
              interannual='mean', season=None, quality=None, vmin=None, vmax=None, palette=None, dimensions=768,
              path=None, **source):
	"""PNG (bytes) of the map of a variable over REGION, with the outline of the region."""
	spec, regions, img, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                 quality, True, None, source)
	vis = maps.vis_params(img, regions.geometry(), variable_entry(spec), res, vmin, vmax, palette)
	return maps.thumbnail(maps.with_outline(img, vis, regions), regions.geometry().bounds(), None, dimensions, path)


@_cited
def region_stats(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                 interannual='mean', season=None, quality=None, stats=('mean', 'std', 'min', 'p5', 'p50', 'p95', 'max'),
                 scale=None, **source):
	"""Statistics over each feature of REGION of the map of a variable aggregated in time:
	{'rows': [{region, mean, std, min, p5, p50, p95, max, n_pixels}], 'scale', 'unit', 'title'}."""
	spec, regions, img, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                 quality, False, None, source)
	scale = scale or timeseries.auto_scale(spec, regions)
	red = ee.Reducer.count()
	names = {}
	for s in stats:
		r = composite.reducer(s)
		names[s] = r.getOutputs().getInfo()[0]
		red = red.combine(r, '', True)
	fc = img.reduceRegions(collection=regions, reducer=red, scale=scale, crs=timeseries.region_crs(regions), tileScale=4)
	rows = []
	for f in fc.getInfo()['features']:
		p = f['properties']
		row = {'region': str(p.get('name'))}
		row.update({s: p.get(n) for s, n in names.items()})
		row['n_pixels'] = p.get('count')
		rows.append(row)
	return {'rows': rows, 'scale': scale, 'unit': _unit(spec), 'title': _named(spec, metric)}


# Exports -----------------------------------------------------------------------------------------------------------

@_cited
def export_image(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                 interannual='mean', season=None, quality=None, resolution=None, crs='auto', folder='MonitorEO',
                 name=None, clip=True, **source):
	"""Export the map of a variable over REGION to a GeoTIFF in FOLDER of Google Drive, on a grid of RESOLUTION
	metres (default: that of the data) in CRS ('auto' = WGS 84 / UTM of the centre of the region).
	Returns {'operation', 'file', 'folder', 'grid'}."""
	spec, regions, img, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                 quality, clip, resolution, source)
	grid = _grid(regions, res, crs)
	name = _slug(name or _file_stem(variable, sensor, metric, start, end, source))
	op = drive.export(img, grid, name, folder, _project)
	return {'operation': op, 'file': name + '.tif', 'folder': folder, 'grid': grid.describe()}


def _grid(regions, res, crs):
	"""Grid of RES metres in CRS ('auto' = WGS 84 / UTM of the centre) that covers REGIONS."""
	geom = regions.geometry()
	if str(crs).lower() == 'auto':
		lon, lat = geom.centroid(1).coordinates().getInfo()
		crs = areas.utm_of(lon, lat)
	ring = geom.bounds(res, crs).getInfo()['coordinates'][0]
	xs, ys = [p[0] for p in ring], [p[1] for p in ring]
	return Grid.around(crs, res, min(xs), min(ys), max(xs), max(ys))


def _file_stem(variable, sensor, metric, start, end, source):
	try:
		static = bool(variable) and bool(catalog.find(variable, sensor, source.get('collection'), source.get('ref'))
		                                 .get('static'))
	except KeyError:
		static = False
	if static:  # a fixed layer (elevation, slope): no metric nor period
		return f'{variable}_{sensor}'
	return f"{variable or source.get('collection') or source.get('image')}_{sensor or ''}_{metric}_{start}_{end}"


@_cited
def download_image(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                   interannual='mean', season=None, quality=None, resolution=None, crs='auto', path=None, clip=True,
                   max_pixels=None, tile=512, workers=8, progress=None, **source):
	"""Download the map of a variable over REGION to the GeoTIFF PATH (float32, NoData -9999) on a grid of RESOLUTION
	metres (default: that of the data) in CRS ('auto' = WGS 84 / UTM of the centre of the region), directly: Earth
	Engine computes it in tiles of TILE pixels, WORKERS at a time (PROGRESS(done, total) after each one). With
	MAX_PIXELS, a grid with more pixels gets a pixel 2, 3, ... times bigger. Fine for small regions; for big ones at
	full resolution, export_image (Google Drive).
	Returns {'file', 'grid', 'resolution', 'native_resolution' (that of the data), 'images', 'name', 'unit', 'min',
	'max' (percentiles 5 and 95 of the values, as the maps of MonitorEO), 'palette'}."""
	spec = make_spec(variable, sensor, start, end, metric=metric, temporal=temporal, interannual=interannual,
	                 season=season, quality=quality, **source)
	regions = areas.region(region)
	native = float(variables.native_scale(spec))
	grid, res = _fit_grid(regions, float(resolution or native), crs, max_pixels)
	img = variables.image(spec, regions.geometry(), res)
	if clip:
		img = img.clipToCollection(regions)
	path = path or _slug(_file_stem(variable, sensor, metric, start, end, source)) + '.tif'
	desc = variables.describe(spec)
	download(img, grid, path, tile=tile, workers=workers, progress=progress,
	         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(desc, default=str)})
	vmin, vmax = _percentiles(path)
	return {'file': path, 'grid': grid.describe(), 'resolution': res, 'native_resolution': native,
	        'images': variables.n_images(spec, regions.geometry()), 'name': _named(spec, metric),
	        'unit': _unit(spec), 'min': vmin, 'max': vmax, 'palette': maps.ramp(variable_entry(spec))}


@_cited
def download_rgb(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                 interannual='mean', season=None, quality=None, resolution=None, crs='auto', path=None, clip=True,
                 max_pixels=None, tile=512, workers=8, progress=None, **source):
	"""Download the true colour of the images of a variable over REGION (see rgb_map: the red, green and blue surface
	reflectance of the same images and pixels as its map, with the same metric) to the GeoTIFF PATH: three bands, red,
	green and blue (float32 reflectance, NoData -9999), on the same grid as download_image with the same arguments
	(RESOLUTION, CRS, MAX_PIXELS: see download_image).
	Returns {'file', 'grid', 'resolution', 'native_resolution', 'images', 'name', 'unit', 'bands', 'min', 'max' (the
	lowest percentile 2 and the highest percentile 98 of the three bands: the range to show them together)}."""
	spec = make_spec(variable, sensor, start, end, metric=metric, temporal=temporal, interannual=interannual,
	                 season=season, quality=quality, **source)
	variables.check_rgb(spec)  # before Earth Engine
	regions = areas.region(region)
	native = float(variables.native_scale(spec))
	grid, res = _fit_grid(regions, float(resolution or native), crs, max_pixels)
	img = variables.image(spec, regions.geometry(), res, rgb=True)
	if clip:
		img = img.clipToCollection(regions)
	path = path or _slug(_file_stem(variable, sensor, metric, start, end, source) + '_RGB') + '.tif'
	desc = variables.describe(spec, rgb=True)
	download(img, grid, path, tile=tile, workers=workers, progress=progress, bands=sensors.RGB_BANDS,
	         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(desc, default=str)})
	lo_p, hi_p = maps.RGB_STRETCH
	stretch = [_percentiles(path, lo_p, hi_p, b) for b in (1, 2, 3)]
	lows, highs = [lo for lo, _ in stretch if lo is not None], [hi for _, hi in stretch if hi is not None]
	return {'file': path, 'grid': grid.describe(), 'resolution': res, 'native_resolution': native,
	        'images': variables.n_images(spec, regions.geometry()), 'name': _rgb_name(spec, metric),
	        'unit': catalog.RGB_UNIT, 'bands': list(sensors.RGB_BANDS), 'min': min(lows) if lows else None,
	        'max': max(highs) if highs else None}


def _fit_grid(regions, res, crs, max_pixels=None):
	"""(grid, pixel size) of REGIONS: pixels of RES m, or 2, 3, ... times bigger if the grid has more than MAX_PIXELS."""
	grid = _grid(regions, res, crs)
	if max_pixels and grid.pixels > max_pixels:
		res *= math.ceil(math.sqrt(grid.pixels / max_pixels))
		grid = _grid(regions, res, grid.crs)
	return grid, res


def _percentiles(path, lo=5, hi=95, band=1):
	"""Percentiles LO and HI of the valid values of a band of a GeoTIFF (None, None if it has none)."""
	import numpy as np
	from osgeo import gdal
	gdal.UseExceptions()
	ds = gdal.Open(path)
	band = ds.GetRasterBand(band)
	a = band.ReadAsArray()
	a = a[(a != band.GetNoDataValue()) & np.isfinite(a)]
	ds = None
	if not a.size:
		return None, None
	return float(np.percentile(a, lo)), float(np.percentile(a, hi))


@_cited
def download_variables(recipe, area, folder, layer=None, buffer=None, only=None, dry_run=False, overwrite=False,
                       drive_all=False, drive_dir=None, wait=True, record=recipes.RECORD, tile=512, workers=8, log=None,
                       progress=None):
	"""Download the variables of RECIPE (a dictionary or a YAML file, see monitoreo.recipe: variables with one or
	several metrics, period, pixel filters and pixel sizes) as GeoTIFFs on aligned grids over the study AREA (a vector
	file, or a region such as {'wdpa_id': 555513}) in FOLDER and, if the recipe has ecoregion: resolution, over the
	ecoregions of RESOLVE 2017 that it touches in FOLDER/ecoregion. Running it again downloads only what changed
	(OVERWRITE: everything) and imports the finished exports to Google Drive (WAIT: wait for them). DRY_RUN: only the
	plan and the number of images. LOG(message) and PROGRESS(file, done, total) follow it.
	Returns {'area', 'grids', 'ecoregions', 'files', ...} and, unless DRY_RUN, {'done', 'folders', 'pending',
	'in_drive', 'failed'}."""
	log = log or recipes._quiet
	p = recipes.plan(recipe, area, layer, buffer, only, warn=log)
	out = p.summary()
	if dry_run:
		images = recipes.n_images(p)
		for f in out['files']:
			f['images'] = images[f['file']]
		return out
	res = recipes.run(p, folder, record, overwrite, drive_all, drive_dir, wait=wait, tile=tile, workers=workers,
	                  project=_project or p.recipe.get('project'), log=log, progress=progress)
	out.update({k: v for k, v in res.items() if k != 'files'})
	return out


# Seasonal trends and comparison of periods ---------------------------------------------------------------------------

def _seasonal_rows(spec, regions, step, metric, stat, scale, progress):
	"""Regional values of each part of the year of STEP in each year: ([{region, part, year, date, value, n_pixels,
	n_images}], scale)."""
	bins = trends.seasonal_bins(spec, step)
	part_year = {a: (p, y) for p, y, a, _ in bins}
	rows, used = timeseries.series(spec, regions, step, metric, stat, scale, progress,
	                               steps=[(a, b) for _, _, a, b in bins])
	for r in rows:
		r['part'], r['year'] = part_year[r['date']]
	return rows, used


def _part(step, part):
	"""The part of the year to map: PART, or the year for 'annual'."""
	if step == 'annual':
		return 0
	if part is None or int(part) not in trends.parts(step):
		raise ValueError(f"give the part of the year: 1-12 (monthly) or 1-23 (16-day), not {part}")
	return int(part)


TREND_COLUMNS = ['region', 'key', 'label', 'n', 'tau', 'z', 'p_value', 'significant', 'slope', 'intercept',
                 'first_year', 'last_year']
COMPARISON_COLUMNS = ['region', 'key', 'label', 'reference', 'other', 'difference', 'n_reference', 'n_other']


@_cited
def trend_table(region, variable=None, sensor=None, start=None, end=None, step='annual', metric='mean', stat='mean',
                season=None, quality=None, scale=None, alpha=0.05, csv=None, chart=None, progress=None, **source):
	"""Seasonal trends of a variable over each feature of REGION (see monitoreo.trends): the spatial STAT of the
	METRIC of each part of the year of STEP ('monthly': 12 months, '16-day': 23 parts of 16 days, 'annual': the
	year) in each year, and the trend of each part over the years (Mann-Kendall tau, Z and p-value, Sen's slope per
	year). Writes the trends to CSV and the chart of the yearly values with their Sen lines to CHART if given.
	Returns {'rows': [{region, part, key, label, n, tau, z, p_value, significant (p < ALPHA), slope, intercept,
	first_year, last_year}], 'yearly': [{region, part, year, value, n_pixels, n_images}], 'csv', 'chart', 'scale',
	'unit', 'title'}."""
	spec = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	variables.check_dates(spec, 'trends')
	regions = areas.region(region)
	yearly, used = _seasonal_rows(spec, regions, step, metric, stat, scale, progress)
	first = composite.windows(spec['period'], spec['season'])[0][0]
	rows = trends.trend_rows(yearly, step, first, alpha=alpha)
	unit = _unit(spec)
	title = _title(spec) + f' | trends of the {step} {metric}, spatial {stat}'
	out = {'rows': rows, 'yearly': yearly, 'csv': None, 'chart': None, 'scale': used, 'unit': unit,
	       'ylabel': _ylabel(spec), 'title': title}
	if csv:
		meta = {'variable': variable or source.get('collection') or source.get('image'), 'sensor': sensor or '',
		        'step': step, 'metric': metric, 'stat': stat, 'unit': catalog.udunits(unit),
		        'slope_unit': catalog.udunits(unit, per_year=True),
		        'scale_m': used}
		out['csv'] = timeseries.write_csv(rows, csv, meta, TREND_COLUMNS)
	if chart and any(r['slope'] is not None for r in rows):
		try:
			charts.trends_png(yearly, rows, chart, title=title, ylabel=out['ylabel'] or None)
			out['chart'] = chart
		except ImportError:  # no matplotlib
			pass
	return out


def _trend(region, variable, sensor, start, end, step, part, metric, season, quality, alpha, res, source):
	spec = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	variables.check_dates(spec, 'trends')
	regions = areas.region(region)
	part = _part(step, part)
	native = float(variables.native_scale(spec))
	img = trends.trend_image(spec, regions.geometry(), res or native, step, part, metric)
	if alpha:
		img = img.updateMask(img.select('p_value').lt(alpha))
	name = f"{_title(spec)} | trend {trends.part_key(step, part)} ({metric})"
	return spec, regions, img.clipToCollection(regions), part, native, name


@_cited
def trend_map(region, variable=None, sensor=None, start=None, end=None, step='annual', part=None, output='slope',
              metric='mean', season=None, quality=None, alpha=None, vmin=None, vmax=None, palette=None,
              thumbnail=None, quick=False, **source):
	"""Map of the trend of a part of the year (PART: month 1-12 with STEP 'monthly', 1-23 with '16-day', none with
	'annual') of a variable over REGION, computed on each pixel: OUTPUT is 'slope' (Sen, per year), 'tau', 'z',
	'p_value', 'intercept' or 'n' (years with data); ALPHA (e.g. 0.05) leaves only the pixels with p_value < ALPHA.
	Earth Engine tiles (the values cannot be queried: download_trend for that). QUICK: with a fixed colour ramp
	(slope: ±2 % of the range of the variable in the catalog per year) instead of that of the map, which takes
	minutes over big regions and long periods.
	Returns {'url', 'min', 'max', 'palette', 'name', 'unit', 'bounds', 'thumbnail'}."""
	if output not in trends.OUTPUTS:
		raise ValueError(f"unknown output {output}: use {', '.join(trends.OUTPUTS)}")
	spec, regions, img, part, native, name = _trend(region, variable, sensor, start, end, step, part, metric, season,
	                                                quality, alpha, None, source)
	band = img.select(output)
	vis = trends.vis(output)
	if quick and (vis is None or (output in ('slope', 'z', 'n') and (vmin is None or vmax is None))):
		entry = variable_entry(spec) or {}
		span = entry.get('maxp', 1) - entry.get('minp', 0) if all(
			isinstance(entry.get(k), (int, float)) for k in ('minp', 'maxp')) else 1
		years = int(str(end)[:4]) - int(str(start)[:4]) + 1
		lo, hi = {'slope': (-0.02 * span, 0.02 * span), 'n': (0, years)}.get(output, (None, None))
		vis = trends.vis(output, lo, hi) or maps.vis_params(band.rename('value'), None, entry, native, compute=False)
	elif vis is None or (output in ('slope', 'z', 'n') and (vmin is None or vmax is None)):
		auto = maps.vis_params(band.rename('value'), regions.geometry(), variable_entry(spec), native)
		vis = trends.vis(output, auto['min'], auto['max']) or auto
	vis = dict(vis, **({'min': vmin} if vmin is not None else {}), **({'max': vmax} if vmax is not None else {}))
	if palette:
		vis['palette'] = maps.ramp(None, palette)
	unit = _unit(spec)
	out = dict(vis, url=maps.tile_url(band, vis), name=f'{name}: {output}', bounds=_bounds(regions), thumbnail=None,
	           unit=f'{unit} / year' if output == 'slope' else unit if output == 'intercept' else '')
	if thumbnail:
		maps.thumbnail(maps.with_outline(band, vis, regions), regions.geometry().bounds(), None, path=thumbnail)
		out['thumbnail'] = thumbnail
	return out


@_cited
def download_trend(region, variable=None, sensor=None, start=None, end=None, step='annual', part=None, metric='mean',
                   season=None, quality=None, alpha=None, resolution=None, crs='auto', path=None, max_pixels=None,
                   tile=512, workers=8, progress=None, **source):
	"""Download the trend of a part of the year of a variable over REGION (see trend_map) to the GeoTIFF PATH, with a
	band per output: slope, tau, z, p_value, intercept, n (NoData -9999 where there are fewer than 2 years or, with
	ALPHA, p_value >= ALPHA), on a grid of RESOLUTION metres (default: that of the data; 2, 3, ... times bigger if
	the grid has more than MAX_PIXELS).
	Returns {'file', 'bands', 'grid', 'resolution', 'native_resolution', 'name', 'unit' (of the slope), 'min', 'max'
	(symmetric range of the slope), 'palette'}."""
	regions_ = areas.region(region)
	spec0 = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	variables.check_dates(spec0, 'trends')
	native = float(variables.native_scale(spec0))
	grid, res = _fit_grid(regions_, float(resolution or native), crs, max_pixels)
	spec, regions, img, part, native, name = _trend(regions_, variable, sensor, start, end, step, part, metric, season,
	                                                quality, alpha, res, source)
	path = path or _slug(f"trend_{_file_stem(variable, sensor, metric, start, end, source)}_{trends.part_key(step, part)}") + '.tif'
	download(img, grid, path, tile=tile, workers=workers, progress=progress, bands=list(trends.OUTPUTS),
	         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(dict(
	             variables.describe(spec), trend=step, part=trends.part_key(step, part), alpha=alpha), default=str)})
	lo, hi = _percentiles(path)
	vis = trends.vis('slope', lo, hi)
	return dict(vis, file=path, bands=list(trends.OUTPUTS), grid=grid.describe(), resolution=res,
	            native_resolution=native, name=name, unit=f'{_unit(spec)} / year')


@_cited
def compare_series(region, variable=None, sensor=None, start=None, end=None, other_start=None, other_end=None,
                   step='monthly', metric='mean', stat='mean', season=None, quality=None, scale=None, csv=None,
                   chart=None, progress=None, **source):
	"""Comparison of a reference period (START to END) with another (OTHER_START to OTHER_END) over each feature of
	REGION: the spatial STAT of the METRIC of each part of the year of STEP ('monthly', '16-day' or 'annual') in each
	year of both periods, and the mean of each part in each period and their difference (other - reference). Writes
	the comparison to CSV and the chart of both periods by part of the year to CHART if given.
	Returns {'profile': [{region, part, key, label, reference, other, difference, n_reference, n_other}], 'rows':
	[{period ('reference' or 'other'), region, part, year, date, value, n_pixels, n_images}], 'csv', 'chart',
	'scale', 'unit', 'title', 'periods': {'reference': [first, last day], 'other': [...]}, 'names' (short names
	of both periods, e.g. 2018-2021)}."""
	if not other_start or not other_end:
		raise ValueError('give the other period: other_start and other_end')
	ref = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	oth = make_spec(variable, sensor, other_start, other_end, metric=metric, season=season, quality=quality,
	                **same_area(source, start, end))
	variables.check_dates(ref, 'comparisons of periods')
	regions = areas.region(region)
	scale = scale or timeseries.auto_scale(ref, regions)
	ref_rows, _ = _seasonal_rows(ref, regions, step, metric, stat, scale, progress)
	oth_rows, _ = _seasonal_rows(oth, regions, step, metric, stat, scale, progress)
	for rows, name in ((ref_rows, 'reference'), (oth_rows, 'other')):
		for r in rows:
			r['period'] = name
	profile = trends.profile(ref_rows, oth_rows)
	for r in profile:
		r['key'], r['label'] = trends.part_key(step, r['part']), trends.part_label(step, r['part'])
	unit = _unit(ref)
	title = (f"{_title(dict(ref, period=None))} | {ref['period'][0]} / {ref['period'][1]} vs "
	         f"{oth['period'][0]} / {oth['period'][1]} | {step} {metric}, spatial {stat}")
	names = tuple(a[:4] if a[:4] == b[:4] else f'{a[:4]}-{b[:4]}' for a, b in (ref['period'], oth['period']))
	out = {'profile': profile, 'rows': ref_rows + oth_rows, 'csv': None, 'chart': None, 'scale': scale, 'unit': unit,
	       'ylabel': _ylabel(ref), 'title': title, 'periods': {'reference': ref['period'], 'other': oth['period']},
	       'names': names}
	if csv:
		meta = {'variable': variable or source.get('collection') or source.get('image'), 'sensor': sensor or '',
		        'reference_period': '/'.join(ref['period']), 'other_period': '/'.join(oth['period']), 'step': step,
		        'metric': metric, 'stat': stat, 'unit': catalog.udunits(unit), 'scale_m': scale}
		out['csv'] = timeseries.write_csv(profile, csv, meta, COMPARISON_COLUMNS)
	if chart and any(r['reference'] is not None or r['other'] is not None for r in profile):
		try:
			labels = {r['part']: r['key'] if step == '16-day' else r['label'][:3] if step == 'monthly' else r['label']
			          for r in profile}
			charts.comparison_png(profile, labels, chart, title=title, ylabel=out['ylabel'] or None, names=names)
			out['chart'] = chart
		except ImportError:  # no matplotlib
			pass
	return out


def same_area(source, start, end):
	"""SOURCE (the arguments of the variable) for the other period of a comparison: its conditions on variables with
	dates (where) computed over the reference period, START to END, so both periods keep the same pixels."""
	where = source.get('where')
	return dict(source, where=variables.pin_where(where, start, end)) if where else source


def _comparison(region, variable, sensor, start, end, other_start, other_end, metric, temporal, interannual, season,
                quality, res, source, two_periods=False):
	if not other_start or not other_end:
		raise ValueError('give the other period: other_start and other_end')
	ref = make_spec(variable, sensor, start, end, metric=metric, temporal=temporal, interannual=interannual,
	                season=season, quality=quality, two_periods=two_periods, **source)
	oth = make_spec(variable, sensor, other_start, other_end, metric=metric, temporal=temporal,
	                interannual=interannual, season=season, quality=quality, two_periods=two_periods,
	                **same_area(source, start, end))
	variables.check_dates(ref, 'comparisons of periods')
	regions = areas.region(region)
	native = float(variables.native_scale(ref))
	geom = regions.geometry()
	a = variables.image(ref, geom, res or native)
	b = variables.image(oth, geom, res or native)
	img = ee.Image.cat([b.subtract(a), a, b]).rename(['difference', 'reference', 'other']).clipToCollection(regions)
	name = (f"{_title(dict(ref, period=None))} ({metric}) | {oth['period'][0]} / {oth['period'][1]} - "
	        f"{ref['period'][0]} / {ref['period'][1]}")
	return ref, regions, img, native, name


@_cited
def compare_map(region, variable=None, sensor=None, start=None, end=None, other_start=None, other_end=None,
                metric='median', temporal='period', interannual='mean', season=None, quality=None, vmin=None,
                vmax=None, palette=None, thumbnail=None, **source):
	"""Map of the difference between the variable aggregated in time over another period (OTHER_START to OTHER_END)
	and over the reference period (START to END), over REGION (e.g. the median NDVI of 2023 minus that of
	2018-2021). Earth Engine tiles (the values cannot be queried: download_comparison for that).
	Returns {'url', 'min', 'max', 'palette', 'name', 'unit', 'bounds', 'thumbnail'}."""
	spec, regions, img, native, name = _comparison(region, variable, sensor, start, end, other_start, other_end, metric,
	                                               temporal, interannual, season, quality, None, source)
	diff = img.select('difference')
	if vmin is None or vmax is None:
		auto = maps.vis_params(diff.rename('value'), regions.geometry(), None, native)
		vis = trends.vis('difference', auto['min'], auto['max'])
	else:
		vis = {'min': vmin, 'max': vmax, 'palette': trends.DIVERGING}
	if palette:
		vis['palette'] = maps.ramp(None, palette)
	out = dict(vis, url=maps.tile_url(diff, vis), name=f'{name}: difference', unit=_unit(spec),
	           bounds=_bounds(regions), thumbnail=None)
	if thumbnail:
		maps.thumbnail(maps.with_outline(diff, vis, regions), regions.geometry().bounds(), None, path=thumbnail)
		out['thumbnail'] = thumbnail
	return out


@_cited
def download_comparison(region, variable=None, sensor=None, start=None, end=None, other_start=None, other_end=None,
                        metric='median', temporal='period', interannual='mean', season=None, quality=None,
                        resolution=None, crs='auto', path=None, max_pixels=None, tile=512, workers=8, progress=None,
                        **source):
	"""Download the comparison of two periods (see compare_map) to the GeoTIFF PATH, with the bands 'difference'
	(other - reference), 'reference' and 'other' (NoData -9999), on a grid of RESOLUTION metres (default: that of the
	data; 2, 3, ... times bigger if the grid has more than MAX_PIXELS).
	Returns {'file', 'bands', 'grid', 'resolution', 'native_resolution', 'name', 'unit', 'min', 'max' (symmetric
	range of the difference), 'palette'}."""
	regions_ = areas.region(region)
	spec0 = make_spec(variable, sensor, start, end, metric=metric, temporal=temporal, interannual=interannual,
	                  season=season, quality=quality, **source)
	variables.check_dates(spec0, 'comparisons of periods')
	grid, res = _fit_grid(regions_, float(resolution or variables.native_scale(spec0)), crs, max_pixels)
	spec, regions, img, native, name = _comparison(regions_, variable, sensor, start, end, other_start, other_end,
	                                               metric, temporal, interannual, season, quality, res, source)
	path = path or _slug(f"comparison_{variable or source.get('collection')}_{sensor or ''}_{metric}_{start}_{end}_"
	                     f"{other_start}_{other_end}") + '.tif'
	bands = ['difference', 'reference', 'other']
	download(img, grid, path, tile=tile, workers=workers, progress=progress, bands=bands,
	         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(dict(
	             variables.describe(spec), reference=[start, end], other=[other_start, other_end]), default=str)})
	lo, hi = _percentiles(path)
	vis = trends.vis('difference', lo, hi)
	return dict(vis, file=path, bands=bands, grid=grid.describe(), resolution=res, native_resolution=native, name=name,
	            unit=_unit(spec))


BURN_COLUMNS = ['region', 'class', 'label', 'dnbr_min', 'dnbr_max', 'ha']
RBR_COLUMNS = ['region', 'mean', 'median', 'p10', 'p90', 'min', 'max', 'ha']
BURN_INDICES = ('dNBR', 'RBR')


@_cited
def burn_severity(region, sensor='Sentinel-2', start=None, end=None, other_start=None, other_end=None,
                  metric='median', season=None, quality=None, resolution=None, crs='auto', path=None, csv=None,
                  max_pixels=None, tile=512, workers=8, progress=None, index='dNBR', where=None):
	"""Burn severity of a fire over each feature of REGION (see monitoreo.fire): the dNBR, NBR of a period before the
	fire (START to END) minus NBR of a period after it (OTHER_START to OTHER_END), each the METRIC of the images of
	SENSOR ('Sentinel-2' or 'Landsat') in its period, and its classes of the USGS (Key & Benson 2006). The hectares of
	each class are computed by Earth Engine on pixels of RESOLUTION metres (default: those of the data). Writes the
	table to CSV and, with PATH, a GeoTIFF with the bands dnbr, severity (class -2 to 4), nbr_before and nbr_after.
	Returns {'index': 'dNBR', 'classes': [{region, class, label, dnbr_min, dnbr_max, ha}], 'burned_ha': {region:
	hectares with dNBR >= 0.1}, 'scale', 'title', 'csv', 'file', 'bands', 'grid', 'resolution', 'native_resolution'}.

	With INDEX 'RBR', the Relativized Burn Ratio instead: RBR = dNBR / (NBR before + 1.001), with the NBR of the
	catalog entry RBR (bands B8A and B12 in Sentinel-2, as Silva-Cardoza et al. 2022; NIR and SWIR2 in Landsat),
	without phenological correction and on the scale of the dNBR (the articles multiply it by 1000). A continuous
	map, without classes: {'index': 'RBR', 'stats': [{region, mean, median, p10, p90, min, max, ha (of the pixels with
	values)}], ...} and the GeoTIFF bands rbr, dnbr, nbr_before and nbr_after.

	WHERE: only the pixels that pass these conditions on variables (as in the other tools), computed over the period
	before the fire."""
	index = {i.lower(): i for i in BURN_INDICES}.get(str(index or 'dNBR').lower())
	if index is None:
		raise ValueError(f"unknown burn index: use {' or '.join(BURN_INDICES)}")
	if index == 'RBR':
		return _rbr(region, sensor, start, end, other_start, other_end, metric, season, quality, resolution, crs, path,
		            csv, max_pixels, tile, workers, progress, where)
	regions_ = areas.region(region)
	spec0 = make_spec('NBR', sensor, start, end, metric=metric, season=season, quality=quality)
	grid, res = _fit_grid(regions_, float(resolution or variables.native_scale(spec0)), crs, max_pixels)
	spec, regions, img, native, name = _comparison(regions_, 'NBR', sensor, start, end, other_start, other_end,
	                                               metric, 'period', 'mean', season, quality, res,
	                                               {'where': where} if where else {})
	dnbr = img.select('reference').subtract(img.select('other')).rename('dnbr')
	severity = fire.classify(dnbr)
	hectares = ee.Image.pixelArea().divide(1e4).addBands(severity).updateMask(dnbr.mask())
	stats = hectares.reduceRegions(collection=regions, reducer=ee.Reducer.sum().group(1, 'class'), scale=res,
	                               crs=grid.crs, tileScale=4).getInfo()['features']
	classes = []
	for f in stats:
		classes += fire.table(f['properties'].get('groups'), str(f['properties'].get('name')))
	burned = {}
	for r in classes:
		burned[r['region']] = burned.get(r['region'], 0.0) + (r['ha'] if r['class'] >= 1 else 0.0)
	title = (f"Burn severity (dNBR, USGS) {sensor} ({metric}) | before {spec['period'][0]} / {spec['period'][1]}, "
	         f"after {other_start} / {other_end}")
	out = {'index': 'dNBR', 'classes': classes, 'burned_ha': burned, 'scale': res, 'title': title, 'csv': None,
	       'file': None, 'bands': None, 'grid': grid.describe(), 'resolution': res, 'native_resolution': native}
	if csv:
		meta = {'sensor': sensor, 'before': f'{start}/{end}', 'after': f'{other_start}/{other_end}', 'metric': metric,
		        'scale_m': res}
		out['csv'] = timeseries.write_csv(classes, csv, meta, BURN_COLUMNS)
	if path:
		bands = ['dnbr', 'severity', 'nbr_before', 'nbr_after']
		image = ee.Image.cat([dnbr, severity.toFloat(), img.select('reference'), img.select('other')]).rename(bands)
		download(image, grid, path, tile=tile, workers=workers, progress=progress, bands=bands,
		         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(dict(
		             variables.describe(spec), before=[start, end], after=[other_start, other_end],
		             severity='USGS, Key & Benson 2006'), default=str)})
		out.update(file=path, bands=bands)
	return out


def _rbr(region, sensor, start, end, other_start, other_end, metric, season, quality, resolution, crs, path, csv,
         max_pixels, tile, workers, progress, where=None):
	"""burn_severity with the index RBR."""
	regions_ = areas.region(region)
	spec0 = make_spec('RBR', sensor, start, end, metric=metric, season=season, quality=quality, two_periods=True)
	grid, res = _fit_grid(regions_, float(resolution or variables.native_scale(spec0)), crs, max_pixels)
	spec, regions, img, native, name = _comparison(regions_, 'RBR', sensor, start, end, other_start, other_end,
	                                               metric, 'period', 'mean', season, quality, res,
	                                               {'where': where} if where else {}, two_periods=True)
	before, after = img.select('reference'), img.select('other')
	dnbr = before.subtract(after).rename('dnbr')
	rbr = fire.rbr(dnbr, before)
	reducer = ee.Reducer.mean().combine(ee.Reducer.median(), '', True) \
		.combine(ee.Reducer.percentile([10, 90]), '', True).combine(ee.Reducer.minMax(), '', True)
	stats = rbr.addBands(ee.Image.pixelArea().divide(1e4).updateMask(rbr.mask()).rename('ha')).reduceRegions(
		collection=regions, reducer=reducer.combine(ee.Reducer.sum(), '', True), scale=res, crs=grid.crs,
		tileScale=4).getInfo()['features']
	rows = []
	for f in stats:
		p = f['properties']
		rows.append({'region': str(p.get('name')), 'mean': p.get('rbr_mean'), 'median': p.get('rbr_median'),
		             'p10': p.get('rbr_p10'), 'p90': p.get('rbr_p90'), 'min': p.get('rbr_min'), 'max': p.get('rbr_max'),
		             'ha': p.get('ha_sum') or 0.0})
	title = (f"Relativized Burn Ratio (RBR) {sensor} ({metric}) | before {spec['period'][0]} / {spec['period'][1]}, "
	         f"after {other_start} / {other_end}")
	out = {'index': 'RBR', 'stats': rows, 'scale': res, 'title': title, 'csv': None, 'file': None, 'bands': None,
	       'grid': grid.describe(), 'resolution': res, 'native_resolution': native}
	if csv:
		meta = {'index': 'RBR', 'sensor': sensor, 'before': f'{start}/{end}', 'after': f'{other_start}/{other_end}',
		        'metric': metric, 'scale_m': res}
		out['csv'] = timeseries.write_csv(rows, csv, meta, RBR_COLUMNS)
	if path:
		bands = ['rbr', 'dnbr', 'nbr_before', 'nbr_after']
		image = ee.Image.cat([rbr, dnbr, before, after]).rename(bands)
		download(image, grid, path, tile=tile, workers=workers, progress=progress, bands=bands,
		         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(dict(
		             variables.describe(spec), before=[start, end], after=[other_start, other_end],
		             index='RBR = dNBR / (NBR before + 1.001)'), default=str)})
		out.update(file=path, bands=bands)
	return out


# Publication -------------------------------------------------------------------------------------------------------

def publish_report(report, site=None, base=None, log=None):
	"""Publish the results of an analysis as a report of the static viewer of results of MonitorEO, in the folder SITE
	(default: MONITOREO_SITE or ~/MonitorEO/visor), for the administrators of the viewer (see monitoreo.publish).
	REPORT is a dictionary (title, summary, question, answer, method, region, authors, results: the calls and results
	of the other functions or the files they wrote, downloads, ...) with its paths relative to BASE, or a YAML file
	with one or several reports. The GeoTIFFs are converted to COG and the CSVs copied; the report gets its
	report.json and SITE the viewer and the catalogue catalog.json. LOG: the log of the calls of the MCP server, where
	the call of each file is looked up (default: that of MONITOREO_OUTPUT).
	Returns {'site', 'catalog', 'reports': [{'id', 'title', 'folder', 'page' (relative to SITE)}]}."""
	from . import publish
	if isinstance(report, (str, os.PathLike)):
		specs = publish.read_specs(report)
	else:
		specs = [(report, base)]
	site = publish.site_folder(site)
	out = []
	for spec, folder in specs:
		r = publish.publish(spec, site, folder, log)
		out.append({'id': r['id'], 'title': r['title'], 'folder': os.path.join(site, 'reports', r['id']),
		            'page': f"report.html?id={r['id']}"})
	return {'site': site, 'catalog': os.path.join(site, 'catalog.json'), 'reports': out}


def remove_report(report_id, site=None):
	"""Remove a report from the viewer of results in the folder SITE and from its catalogue."""
	from . import publish
	publish.remove(report_id, site)
	return {'site': publish.site_folder(site), 'removed': report_id}


def check_site(site=None):
	"""Problems of the catalogue and the reports of the viewer of results in the folder SITE ([] if it is right)."""
	from . import publish
	return publish.check_site(site)


def task_status(operation):
	"""State of an export task: {'state': PENDING|RUNNING|SUCCEEDED|FAILED|CANCELLED|UNKNOWN, 'progress', 'error'}."""
	state, progress, error = drive.status(operation)
	return {'operation': operation, 'state': state, 'progress': progress, 'error': error}


def local_drive_folders():
	"""Folders 'My Drive' of Google Drive for desktop on this computer (to open the exported files)."""
	return drive.local_drives()


def find_exported(folder, name):
	"""Files exported as NAME (NAME.tif or its pieces, or NAME.csv) in the local FOLDER of Google Drive and its
	namesakes 'FOLDER (1)', ..."""
	stem = os.path.splitext(name)[0]
	files = drive.find(folder, stem)
	for d in drive.folders(folder):
		p = os.path.join(d, stem + '.csv')
		if os.path.exists(p):
			files.append(p)
	return files
