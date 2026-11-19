"""The functions of MonitorEO for the tools that use it (QGIS plugin, MCP server, R package, command line).

They take plain values (text, numbers, lists, dictionaries) and return plain values or files, so every tool
computes exactly the same. A variable is given by its name in the catalog of MonitorEO (variable='NDVI',
sensor='Sentinel-2'; see list_variables) or by an Earth Engine source (collection= and band=, or image= and band=;
several bands, band=['aet', 'def'], are combined on each pixel with band_reducer='sum' or 'mean': see make_spec).
A region is a dictionary (see areas.region): {'wdpa_id': 555513}, {'ecoregion_id': 793}, {'biome_id': 12} (a biome of
RESOLVE Ecoregions 2017), {'bbox': [w, s, e, n]}, {'point': [lon, lat], 'buffer': 1000}, {'geojson': ...} or {'file':
'area.gpkg'}; with within, only its part inside another region: {'biome_at': [lon, lat], 'within': {'country': 'ESP'}}.

Besides time series, maps and statistics, the variables are downloaded as GeoTIFFs: one map (download_image, or
export_image to Google Drive), the true colour of the same images (rgb_map and download_rgb: the red, green and blue
reflectance of the images of a variable of Sentinel-2 or Landsat, or of the cloud frequency of MODIS, with the same
dates, pixel filters and metric; see has_rgb) or a recipe of several variables on aligned grids over a study area and its ecoregions
(download_variables, see monitoreo.recipe). The seasonal trends (Mann-Kendall and Sen: trend_table, trend_map,
download_trend) and the comparison of a reference period with another (compare_series, compare_map,
download_comparison) are described in monitoreo.trends. The results of an analysis are published
for anyone in the static web viewer of results with publish_report (see monitoreo.publish).

The categorical layers (ECOREGION and BIOME, sensor RESOLVE: the ecoregions and biomes of RESOLVE Ecoregions 2017; see
monitoreo.categorical) are fixed layers whose values are class codes: their maps have a legend of the classes in the
region ('classes'), their statistic over a region is the majority class (region_stats: 'mode'), area_by_class gives the
area of each class, they give zones by class (region_stats with zones) and conditions of where with classes or exclude,
and list_classes lists their classes (code, name, colour), without Earth Engine.

Call init() first. With a project (init(project) or the variable EE_PROJECT) it computes with the Google account of
`earthengine authenticate` and the quota of that project; without one, with the shared account of MonitorEO, whose
research EECUs (the compute of Earth Engine of each month: the same for each user, who is the anonymous ID of each
installation) are only for research. eecu_usage tells how much of them (or, with the user's own account, of the monthly
EECU quota of their project) has been spent, and the tools warn when less than 10 % is left (see eecu_warning). When
Earth Engine puts the project in restricted mode (it has spent its noncommercial compute quota: computations are slow
and may fail with too many requests), the tools tell it too, with the shared account that the user can compute with
their own Google Cloud project (see quota_warning).

The periods are checked against the dates of the images of the data before computing (see monitoreo.coverage): a period
that ends before the first image, falls in a gap between the collections or begins after today is an error, and one
that begins before the first image (or ends, or even begins, after the last one of data that ended in the copy of the
Earth Engine data catalog) gives a warning, as a Python warning (coverage.DataDatesWarning) and in 'warnings' of the
answer ([texts]); those of a condition of where begin with 'where, the condition on ...'. The
answers say which data their values come from, 'data_source' (e.g. 'COPERNICUS/S2_SR_HARMONIZED (Harmonized
Sentinel-2 MSI, Level-2A (SR))'), and their charts in a line «Data: ...».

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
import threading
import time
import warnings

import ee

from . import animation, areas, catalog, categorical, charts, classes, composite, coverage, drive, figures, fire, landcover, maps, references, sensors, timeseries, trends
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
	and the references) and a README next to them, whose path is in the answer ('readme'), with the parameters of the
	call as JSON (monitoreo.parameters), whose path is in the answer too ('parameters'). Its answer also has, when
	there are any, the warnings of its periods ('warnings': the days without images of its data, see
	monitoreo.coverage) and the data its values come from ('data_source')."""
	sig = inspect.signature(fn)

	@functools.wraps(fn)
	def wrapped(*args, **kwargs):
		with coverage.collect() as notes:
			out = fn(*args, **kwargs)
		if isinstance(out, dict):
			if notes.warnings and not out.get('warnings'):
				out['warnings'] = list(notes.warnings)
			source = notes.source()
			if source and not out.get('data_source'):
				out['data_source'] = source
			call = sig.bind(*args, **kwargs)
			given = dict(call.arguments)
			given.update(given.pop('source', None) or {})
			call.apply_defaults()
			a = dict(call.arguments)
			a.update(a.pop('source', None) or {})
			sea = sea_warning(a)
			if sea and sea not in (out.get('warnings') or []):
				out['warnings'] = list(out.get('warnings') or []) + [sea]
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


def sea_warning(args):
	"""The warning of a variable of the catalog without data over the open sea (without sea in the catalog: the NDVI of
	MODIS, the land surface temperature...) computed over a sea (the region sea or sea_at, or within one), from the
	arguments ARGS of a call (region, variable, sensor, collection); else None (also for the data of Earth Engine given
	by their ID, which MonitorEO does not know)."""
	region, var = args.get('region'), args.get('variable')
	if not areas.is_sea(region) or not var or args.get('image'):
		return None
	entry = references._entry(var, args.get('sensor'), args.get('collection'))
	if entry is None or entry.get('sea'):
		return None
	marine = sorted({f"{e['index']} ({e['sensor']})" for e in catalog.variables() if e.get('sea')})
	return (f"{entry['index']} of {entry['sensor']} has no data over the open sea: its data are of the land "
	        f"(Sentinel-2 and Landsat see the coastal waters only). Over a sea, use {', '.join(marine)}.")


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
	with WARN it gives a Python warning (EECUWarning) if less than 10 % of the EECUs of the month are left. It notes
	the warnings of Earth Engine of its restricted mode (see watch_quota and quota_warning)."""
	global _project, _shared
	watch_quota()
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
	warning (None or why to worry), text, bar, quota_warning (see quota_warning: Earth Engine has put the project in
	restricted mode, asked with probe_quota when the account is that connected, and to Earth Engine by the broker for the
	shared account, also without connecting: then nothing is left)}, with the texts in LANG ('en' or 'es')."""
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
				       'left': d.get('left_hours'), 'project_left': d.get('project_left_hours'),
				       'restricted': bool(d.get('restricted'))}
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
	restricted = shared and hit.get('restricted')  # the broker asks Earth Engine (it gives 0 left)
	if restricted:
		warning = _QUOTA_TEXT['shared'].format(project=project)
	elif left_pct < EECU_LOW:
		out_key = 'out_project' if by_project and left <= 0 else ('out_' if left_pct <= 0 else 'low_') + kind
		warning = (t[out_key] + t[kind]).format(**values)
	text = t['text_' + kind].format(**values) + (t['project_shared'].format(**values) if by_project else '')
	out = {'account': kind, 'name': t['name_' + kind], 'project': project, 'used_hours': round(used, 2),
	       'limit_hours': limit, 'left_hours': round(left, 2), 'tier': tier, 'used_percent': used_pct,
	       'left_percent': left_pct, 'month': start.isoformat(), 'resets': resets.isoformat(), 'low': left_pct < EECU_LOW,
	       'warning': warning, 'text': text}
	if _project and bool(shared) == bool(_shared):  # the account connected: Earth Engine says whether its project is
		probe_quota()  # in restricted mode, which the broker (with the shared account) does not see
	out['quota_warning'] = quota_warning() or (warning if restricted else None)
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


# Restricted mode: Earth Engine slows down a project that has spent its noncommercial compute quota -----------------

QUOTA_MESSAGE = 'Your project has exceeded its noncommercial compute quota'  # the warning of earthengine-api begins so
QUOTA_TTL = 1800  # seconds after the last warning of restricted mode that the tools still tell it
QUOTA_EVERY = 300  # seconds between two warnings of restricted mode on stderr
QUOTA_PROBE = 600  # seconds between two questions of probe_quota to Earth Engine
_quota_probed = {}  # (project, shared): when probe_quota asked Earth Engine
_restricted = None  # the last warning of restricted mode: {time, since (the first of those in a row), project, shared}
_quota_printed = 0.0  # when stderr got a warning of restricted mode
_quota_given = set()  # (project, since) of the restricted modes whose text quota_warning has given
_quota_passing = threading.local()  # a warning of restricted mode on its way to stderr, in this thread

_QUOTA_TEXT = {
	'shared': 'The shared account of MonitorEO has spent the noncommercial compute quota of its Earth Engine project '
	          'for now, and Earth Engine has put it in restricted mode: computations are slow (fewer at the same time) '
	          'and may fail with too many requests (HTTP 429). To compute without waiting, use your own Google Cloud '
	          'project registered in Earth Engine (https://developers.google.com/earth-engine/guides/access); in Python, '
	          'after `earthengine authenticate`: init(project=...) or the variable EE_PROJECT.',
	'own': 'Your Earth Engine project {project} has exceeded its noncommercial compute quota, and Earth Engine has put it '
	       'in restricted mode: computations are slow (fewer at the same time) and may fail with too many requests '
	       '(HTTP 429); see ' + TIERS_URL + '#restricted_mode. For more quota, raise the tier of the project: '
	       'https://console.cloud.google.com/earth-engine/configuration?project={project}',
}


def watch_quota():
	"""Note the warnings of restricted mode of earthengine-api (see quota_warning): a hook of warnings.showwarning over
	the one there, which passes every warning on to it but those of restricted mode, at most one every QUOTA_EVERY
	seconds (Earth Engine warns with each answer), and a filter that lets each of them reach it (Python would show only
	the first one of each place). At the import of the services, and again in init if another hook has replaced it; it
	only sets values, so the threads of the QGIS plugin can warn at the same time."""
	if not getattr(warnings.showwarning, 'monitoreo_quota', False):
		warnings.showwarning = _quota_hook(warnings.showwarning)
	pattern = re.escape(QUOTA_MESSAGE)
	if not any(f[0] == 'always' and getattr(f[1], 'pattern', None) == pattern for f in warnings.filters):
		warnings.filterwarnings('always', message=pattern, category=UserWarning)


def _quota_hook(shown):
	"""warnings.showwarning that notes the warnings of restricted mode (see watch_quota) and passes them on to SHOWN,
	the previous hook, at most one every QUOTA_EVERY seconds, and every other warning always."""
	def show(message, category, filename, lineno, file=None, line=None):
		if getattr(_quota_passing, 'on', False) or not (isinstance(category, type) and
		                                                issubclass(category, UserWarning) and
		                                                str(message).startswith(QUOTA_MESSAGE)):
			return shown(message, category, filename, lineno, file, line)
		if not _note_restricted():
			return None
		_quota_passing.on = True  # through the hooks below this one, which may be this one again (see watch_quota)
		try:
			return shown(message, category, filename, lineno, file, line)
		finally:
			_quota_passing.on = False
	show.monitoreo_quota = True
	return show


def _note_restricted():
	"""Note a warning of restricted mode of Earth Engine for the project connected; whether it goes on to stderr (none
	did in the last QUOTA_EVERY seconds)."""
	global _restricted, _quota_printed
	now, seen = time.time(), _restricted
	same = bool(seen) and (seen['project'], seen['shared']) == (_project, _shared) and now - seen['time'] <= QUOTA_TTL
	_restricted = {'time': now, 'since': seen['since'] if same else now, 'project': _project, 'shared': _shared}
	if now - _quota_printed < QUOTA_EVERY:
		return False
	_quota_printed = now
	return True


def probe_quota():
	"""Ask Earth Engine for a number (ee.Number(1), nothing to compute), at most once every QUOTA_PROBE seconds for the
	project connected, so that its answer says whether the project is in restricted mode (see watch_quota): the tools
	can then warn of it before computing, as when the assistant opens (eecu_usage). It never fails."""
	if not _project:
		return
	key = (_project, _shared)
	if time.time() - _quota_probed.get(key, 0) < QUOTA_PROBE:
		return
	_quota_probed[key] = time.time()
	try:
		watch_quota()
		ee.Number(1).getInfo()
	except Exception:  # no network, a token refused: the computations will say it
		return


def quota_warning(once=False):
	"""Why Earth Engine computes slowly, or None: the text of its restricted mode when earthengine-api has warned of it
	(see watch_quota) for the project connected in the last QUOTA_TTL seconds. Earth Engine puts a project that has
	spent its noncommercial compute quota in restricted mode: fewer requests at the same time, many answered «too many
	requests» (HTTP 429, which earthengine-api tries again), so computations are slow or fail. With the shared account of
	MonitorEO, the text says to use the user's own Google Cloud project; with theirs, that it has spent its quota. With
	ONCE, only the first time of each restricted mode (one more begins when Earth Engine warns again after QUOTA_TTL
	seconds without warnings). It never fails, and asks nothing to Earth Engine: the tools call it after computing."""
	seen = _restricted
	if not seen or not _project or (seen['project'], seen['shared']) != (_project, _shared) or \
			time.time() - seen['time'] > QUOTA_TTL:
		return None
	key = (seen['project'], seen['since'])
	if once and key in _quota_given:
		return None
	_quota_given.add(key)
	return _QUOTA_TEXT['shared' if seen['shared'] else 'own'].format(project=seen['project'])


watch_quota()


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
	two_periods, RBR, or metric, the only metric of the SCF, and rgb when its images have a true colour, see has_rgb;
	categorical and n_classes for a layer of class codes, see list_classes), optionally of one SENSOR (compared as
	catalog.find does: 'merit hydro' and 'MERITHydro' are 'MERIT Hydro'), of one THEME (its key or its name) or with
	TEXT in their variable or their name (in English or in Spanish, whatever LANG is)."""
	out = []
	wanted = _theme(theme) if theme else None
	for e in catalog.variables():
		if sensor and catalog.name_key(e['sensor']) != catalog.name_key(sensor):
			continue
		if wanted and e.get('theme') != wanted['key']:
			continue
		t = catalog.theme_of(e['index']) or {}
		row = {'ref': e['ref'], 'variable': e['index'], 'sensor': e['sensor'], 'collection': e['col'],
		       'name': _name(e, lang, 'vname'), 'theme': t.get(lang) or t.get('en'), 'group': _name(e, lang, 'type'),
		       'resolution_m': e['m'], 'dates': e['dr'], 'unit': e['unit']}
		if e['col'] in sensors.GAP_FILLED:  # its images come from two datasets (ET, LE of MODIS: MOD16A2GF, MOD16A2)
			row['datasets'] = references.datasets(e['col'])
		if e.get('two_periods'):
			row['two_periods'] = True  # RBR: only burn_severity computes it
		if e.get('metric'):
			row['metric'] = e['metric']  # its only metric (SCF: the mean)
		if sensors.fixed_filters(e) is not None:
			row['fixed_filters'] = sensors.fixed_filters(e)  # always on, whatever the quality (SCF: clouds, water)
		if e.get('static'):
			row['static'] = True  # elevation, slope, TWI, WorldClim: without dates, only maps and their statistics
		if categorical.is_categorical(e):  # its values are class codes (the ecoregions, the biomes): see list_classes
			row['categorical'] = True
			row['n_classes'] = len(categorical.codes(e))
		if sensors.rgb_of(e):
			row['rgb'] = True  # its images have a true colour (rgb_map, download_rgb)
		if text and str(text).lower() not in f"{row['variable']} {e['vname']} {e.get('vname_en', '')}".lower():
			continue
		out.append(row)
	return out


def themes(lang='en'):
	"""The themes of the menus of the tools (see catalog.THEMES): [{key, name, variables (their codes), analyses (those
	of the theme besides maps, series, trends, comparisons and exports)}], in LANG ('en' or 'es'); then those of the
	data of Earth Engine outside the catalog (catalog.OTHER_THEMES), with 'data': 'earth_engine' (any image or
	collection by its ID, see describe_asset) or 'community' (the GEE Community Catalog, see community_datasets)."""
	return [{'key': t['key'], 'name': t.get(lang) or t['en'], 'variables': list(t['indices']),
	         'analyses': list(t.get('analyses') or [])} for t in catalog.THEMES] + \
		[{'key': t['key'], 'name': t.get(lang) or t['en'], 'variables': [], 'analyses': [], 'data': t['key']}
		 for t in catalog.OTHER_THEMES]


def landcover_maps(lang='en'):
	"""The land cover maps of the land cover masks (a condition of where that leaves out some land covers, e.g. water
	bodies and built-up areas: {"landcover": "CORINE", "year": 2018, "exclude": ["water", "built"]}), with their years,
	pixel size and coverage, and the broad land covers common to all of them, with the classes of each map that are
	each one (the table of correspondences; see monitoreo.landcover), in LANG ('en' or 'es'): {'classes': [{key, name,
	help}], 'maps': [{key, name, resolution_m, coverage, years, default_year, dataset, how, crosswalk, classes}],
	'rule', 'references', 'credits'}."""
	out = landcover.describe(lang)
	ids, credits = references.of_datasets([d for m in landcover.maps() for d in landcover.all_datasets(m)])
	ids += [r for m in landcover.maps() for r in m.get('crosswalk_references') or []]
	out['references'] = [references.get(i) for i in dict.fromkeys(ids)]
	out['credits'] = credits
	return out


def list_classes(variable, sensor=None, text=None, limit=None, lang='en'):
	"""The classes of a categorical layer of the catalog (VARIABLE and SENSOR: ECOREGION or BIOME, sensor RESOLVE; see
	monitoreo.categorical): [{code (for classes and exclude of a condition of where, or the classes of zones), name (in
	LANG 'es', the Spanish name of the biomes), colour (hex, without #) and, for the ecoregions, group and group_name
	(their biome)}], from the lowest code; with TEXT, those with its words at the start of a word of their code, name or
	biome (in any case, with or without accents), at most LIMIT. Without Earth Engine."""
	e = catalog.find(variable, sensor)
	if not categorical.is_categorical(e):
		raise ValueError(f"{e['index']} ({e['sensor']}) is not a categorical layer: list_classes is for the layers of "
		                 'class codes, ECOREGION and BIOME (sensor RESOLVE)')
	return categorical.find(e, text, limit, lang)


def _categorical(variable, sensor=None, source=None):
	"""The entry of the catalog of VARIABLE and SENSOR when it is a categorical layer (see monitoreo.categorical), else
	None (also for the data of Earth Engine outside the catalog, and for a variable not in it, which make_spec refuses):
	without Earth Engine."""
	ref = (source or {}).get('ref')
	if not variable and ref is None:  # a variable of the catalog is given by its name, or by its ref alone
		return None
	try:
		e = catalog.find(variable, sensor, (source or {}).get('collection'), ref)
	except (KeyError, ValueError, TypeError):
		return None
	return e if categorical.is_categorical(e) else None


def _class_map(spec, regions):
	"""(vis, legend) of the map of the categorical layer SPEC over REGIONS (see monitoreo.categorical): the colour of
	each class, and the legend of the classes in the region (all of them if it has none)."""
	entry = variables.entry_of(spec)
	present = categorical.present(entry, regions.geometry())
	return categorical.vis(entry, present), categorical.legend(entry, present)


def _theme(theme):
	low = str(theme).strip().lower()
	for t in catalog.THEMES:
		if low in (t['key'], t['en'].lower(), t['es'].lower()):
			return t
	for t in catalog.OTHER_THEMES:
		if low in (t['key'], t['en'].lower(), t['es'].lower()):
			raise ValueError(f"{t['en']} has no variables of the catalog: {t['help']}")
	raise ValueError(f"unknown theme {theme}: use {', '.join(t['key'] for t in catalog.THEMES)}")


def describe_variable(variable_name, sensor=None, collection=None, ref=None, lang='en'):
	"""Everything about a variable of the catalog: formula, collection, scale, unit, pixel filters, notes, ... and what
	to cite with its data: 'references' (the articles of its formula or algorithm, its Earth Engine datasets as their
	catalog pages suggest and the pixel filters) and 'credits' (see monitoreo.references). A categorical layer (class
	codes) has categorical, n_classes, classes_table and its classes, if they are at most categorical.DESCRIBE_MAX
	(else classes_note: list_classes gives them). data_dates: the first and last day of its images ({'start', 'end'},
	end None if they go on; None for a fixed layer), as the Earth Engine data catalog said on data_dates_checked (see
	monitoreo.coverage: the tools refuse a period that ends before them, falls in a gap between their collections or
	begins after today, and warn of the days without them); data_source:
	its Earth Engine datasets and their title, with their product level."""
	e = catalog.find(variable_name, sensor, collection, ref)
	out = {k: e.get(k) for k in ('ref', 'index', 'sensor', 'col', 'm', 'tr', 'dr', 'unit', 'ft', 'scale', 'offset')}
	out['name'] = _name(e, lang, 'vname')
	t = catalog.theme_of(e['index']) or {}
	out['theme'] = t.get(lang) or t.get('en')
	out['group'] = _name(e, lang, 'type')
	out['pixel_filters'] = sensors.filters(e)
	if e['col'] in sensors.GAP_FILLED:  # its images come from two datasets, each in its dates (references.datasets)
		out['datasets'] = references.datasets(e['col'])
	out['measures'] = [f for f, idx in sensors.MEASURES.items() if e['index'] in idx]
	out['notes'] = e.get('notes', {})
	if e.get('metric'):
		out['metric'] = e['metric']  # its only metric (SCF: the mean)
	if sensors.fixed_filters(e) is not None:
		out['fixed_filters'] = sensors.fixed_filters(e)  # always on, whatever the quality (SCF: clouds, water)
	if e.get('static'):
		out['static'] = True  # elevation, slope, TWI, WorldClim: without dates, only maps and their statistics
	if categorical.is_categorical(e):  # class codes: its classes (or how to list them, when they are many)
		out.update(categorical.describe(e, lang))
	out['rgb'] = sensors.rgb_of(e) is not None  # its images have a true colour (rgb_map, download_rgb)
	if e['ref'] in catalog.FIXES:
		out['fixed'] = catalog.FIXES[e['ref']]
	out['alternatives'] = [a['col'] for a in catalog.alternatives(e)]
	data = coverage.of_entry(e)
	out['data_source'] = data['text']
	out['data_dates'] = None if e.get('static') else {'start': data['start'], 'end': data['end']}
	out['data_dates_checked'] = coverage.checked()
	out.update(references.of_entry(e))  # references (formula, Earth Engine datasets, pixel filters) and credits
	return out


# Data of Earth Engine outside the catalog --------------------------------------------------------------------------

def describe_asset(asset):
	"""Everything about an image or a collection of images of Earth Engine given by its ID (ASSET, e.g.
	'IDAHO_EPSCOR/TERRACLIMATE' or 'projects/sat-io/open-datasets/FABDEM'), to compute it with the tools instead of a
	variable of the catalog: {'asset', 'type' (image or image_collection), 'use' (the argument that takes it: collection
	or image), 'how', 'title', 'source', 'page', 'provider', 'licence', 'dates', 'bands': [{'band', 'description',
	'units', 'unit' (in UDUNITS), 'band_scale', 'band_offset', 'resolution_m', 'classes'}], 'arguments' (to compute its
	first band, e.g. {'collection': ..., 'band': ..., 'band_scale': ..., 'unit': ...}; several bands are combined with
	band=[...] and band_reducer='sum' or 'mean'), 'notes', 'references', 'credits'}. It reads the metadata of the
	asset in Earth Engine (without computing) and, for the Earth Engine data catalog, its STAC record (see
	monitoreo.assets)."""
	from . import assets
	return assets.describe(asset)


def community_themes(lang='en'):
	"""The themes of the GEE Community Catalog with images or collections of images: [{'theme' (its name in the
	catalog), 'name' (in LANG, 'en' or 'es'), 'datasets' (how many)}] (see monitoreo.community)."""
	from . import community
	return community.themes(lang)


def find_datasets(text=None, start=None, end=None, bbox=None, kind=None, limit=20):
	"""The images and collections of images of the Earth Engine data catalog, from the copy of its index in MonitorEO
	(see monitoreo.eecatalog), as the dataset search of geemap: those with the words of TEXT (in English; at least half
	of them) in their title, ID, keywords, provider or description, the collections with data between START and END
	(the images, fixed layers without dates, whatever their dates), over BBOX ([w, s, e, n], degrees), of one KIND
	('image' or 'image_collection'), at most LIMIT (100): [{'id', 'title', 'type', 'start', 'end' (none: it goes on),
	'bbox', 'provider', 'keywords', 'gsd' (m), 'description', 'page'}], those with most words first. describe_asset
	gives the bands of one; then compute it with collection= or image= and band= (several with band_reducer=). Without
	Earth Engine."""
	from . import eecatalog
	return eecatalog.search(text, start, end, bbox, kind, limit)


def community_datasets(theme=None, text=None, kind=None, limit=None):
	"""The images and collections of images of the GEE Community Catalog (https://gee-community-catalog.org), from the
	copy of its index in MonitorEO: [{'id' (the ID of its Earth Engine asset, for collection or image), 'title',
	'type' (image or image_collection), 'theme', 'provider', 'license', 'tags', 'docs' (its page, with its bands and
	how to cite it)}], of one THEME (see community_themes; its name in English or Spanish), with TEXT in their title,
	ID, provider or tags, of one KIND ('image' or 'image_collection'), at most LIMIT. describe_asset gives the bands of
	one; then compute it with collection= or image= and band= (several with band_reducer=)."""
	from . import community
	return community.datasets(theme, text, kind, limit)


def find_protected_areas(text, limit=20, designation=None):
	"""Protected areas of WDPA whose name contains TEXT: [{SITE_ID (WDPA ID), NAME, DESIG, IUCN_CAT, ISO3, REP_AREA, ...}];
	with DESIGNATION 'ramsar', only the Ramsar sites (Wetlands of International Importance)."""
	return areas.find_protected_areas(text, limit, designation)


def find_seas(text, limit=20):
	"""The oceans and seas (the sea areas of the IHO, of Marine Regions) whose name contains TEXT, in any case and with
	or without accents (or whose MRGID begins with it), without Earth Engine: [{MRGID, NAME, AREA_KM2, BOUNDS}], the
	very name first; the whole Mediterranean Sea (1905) is its 10 sea areas as one region, with their MRGIDs (PARTS).
	Use the MRGID or the name as {"sea": 3324} or {"sea": "Alboran Sea"}; {"sea_at": [lon, lat]} is the sea at a point.
	They are large areas: see areas.LARGE_AREA_KM2."""
	return areas.find_seas(text, limit)


def find_admin_units(text, level=1, country=None, limit=20):
	"""Administrative units of FAO GAUL 2025 whose name contains TEXT: of LEVEL 1 (regions, states, provinces...) or 2
	(provinces, districts, municipalities...), in COUNTRY (ISO3 code) if given: [{GAUL1_CODE or GAUL2_CODE, the names,
	ISO3_CODE, DISP_EN, level}]; LEVEL 3, the municipalities of Spain, of the Instituto Geográfico Nacional (any case and
	accents, or a code of the INE): [{ADMIN3_CODE, NAME, PROVINCE, REGION, ISO3_CODE, DISP_EN, level}]. Use the code as
	{"admin1": ...}, {"admin2": ...} or {"admin3": "18134"}, and a country as {"country": "ESP"}."""
	return areas.find_admin_units(text, level, country, limit)


# Variables ---------------------------------------------------------------------------------------------------------

def make_spec(variable=None, sensor=None, start=None, end=None, metric='mean', temporal='period', interannual='mean',
              season=None, quality=None, collection=None, band=None, image=None, ref=None, band_scale=None,
              band_offset=None, terrain=None, exclude_landcover=None, where=None, two_periods=False, unit=None,
              band_reducer=None):
	"""Spec of a variable (see monitoreo.variable) from the arguments of the services (TWO_PERIODS: also the
	variables that compare two periods, RBR, for burn_severity). WHERE: the pixels of the study area to keep, a list of
	conditions on variables (see variable.where_specs), e.g. [{'variable': 'ELEVATION', 'sensor': 'Copernicus',
	'min': 1500}], or land covers to leave out after a land cover map of a year (see landcover_maps), e.g.
	{'landcover': 'CORINE', 'year': 2018, 'exclude': ['water', 'built']}; every tool that takes a region takes it.
	Instead of VARIABLE and SENSOR, any data of Earth Engine by its ID (see monitoreo.assets and describe_asset):
	COLLECTION (images with dates) or IMAGE (a fixed image, or the mosaic of a collection of tiles), with BAND (one,
	or several: a list, or a text with commas, with BAND_REDUCER 'sum' or 'mean', which combines them into one value
	on each pixel where all of them have data) and optionally BAND_SCALE and BAND_OFFSET (of its stored values, of each
	band before they are combined), UNIT (of the values, in UDUNITS: 'mm', 'degC'; '' is none; that of every band, so
	of their sum or mean) and, for an image of one band, TERRAIN ('slope' or 'aspect' of the band of an image, in
	degrees: its unit is then degree). An ID of Earth Engine given as VARIABLE is an error that says how to give it."""
	if variable and '/' in str(variable):  # no variable of the catalog has '/': an ID of Earth Engine, whatever SENSOR
		raise ValueError(f'{variable} is not a variable of the catalog: give an ID of Earth Engine as a collection or '
		                 'an image (describe_asset says which), with its band, instead of the variable')
	var = {'metric': metric, 'temporal': temporal, 'interannual': interannual, 'season': season,
	       'quality': quality or {}, 'exclude_landcover': exclude_landcover, 'where': where}
	if start or end:
		var['period'] = [str(start), str(end or dt.date.today().isoformat())]
	if variable or ref is not None:
		var.update({'index': variable, 'sensor': sensor, 'collection': collection, 'ref': ref})
		if ref is not None and not variable:
			var['index'] = catalog.find(None, ref=ref)['index']
	elif image:
		var.update({'image': image, 'band': band, 'terrain': terrain, 'band_reducer': band_reducer})
		var.pop('metric')
	elif collection:
		var.update({'collection': collection, 'band': band, 'band_reducer': band_reducer})
	if band_scale is not None:
		var['scale'] = band_scale
	if band_offset is not None:
		var['offset'] = band_offset
	if unit is not None and str(unit).strip() != '':
		var['unit'] = unit
	if variable or ref is not None:  # a variable of the catalog has its own band, scale, offset and unit
		extra = [k for k, v in (('image', image), ('band', band), ('band_reducer', band_reducer),
		                        ('band_scale', band_scale), ('band_offset', band_offset), ('terrain', terrain))
		         if v not in (None, '')]
		if extra:
			raise ValueError(f"{', '.join(extra)}: only for the data of Earth Engine given by their ID (collection or "
			                 f"image, instead of variable and sensor); {variable or ref} is a variable of the catalog")
	elif image and collection:
		raise ValueError('give collection (images with dates) or image (a fixed image), not both')
	elif terrain and not image:
		raise ValueError('terrain is for an image (image=, e.g. a DEM), not for a collection')
	var = {k: v for k, v in var.items() if v is not None}
	spec = variable_specs(var, two_periods)[0]
	coverage.used(spec, variables.entry_of(spec) if variables.kind(spec) == 'catalog' else None)  # for its charts
	return spec


def variable_specs(var, two_periods=False):
	return variables.specs(var, two_periods=two_periods)


def _series_name(spec):
	"""The name of the variable of SPEC in titles and tables: its index and sensor ('NDVI Sentinel-2'), or the ID, band
	and terrain of the data of Earth Engine (the slope of a DEM is not named as its elevation)."""
	if variables.kind(spec) == 'catalog':
		e = variables.entry_of(spec)
		return f"{e['index']} {e['sensor']}"
	return variables.data_name(spec)


def _title(spec, step=None, metric=None, stat=None, name=None):
	name = name or _series_name(spec)
	period = f"{spec['period'][0]} / {spec['period'][1]}" if spec.get('period') and not variables.is_static(spec) else ''
	parts = [name, period]
	if step:
		parts.append(f'{step} {metric}, spatial {stat}')
	return ' | '.join(p for p in parts if p)


def _named(spec, metric):
	"""Name of a map of SPEC: its title and METRIC (not for the fixed layers, elevation and slope)."""
	return _title(spec) + ('' if variables.is_static(spec) else f' ({metric})')


def _between(spec):
	"""The metric between the years of SPEC, if its images are aggregated by years (None for the whole period and the
	fixed layers, which have no images)."""
	if spec.get('temporal', 'period') == 'period' or variables.kind(spec) == 'image' or variables.is_static(spec):
		return None
	return spec.get('interannual')


def _unit(spec, stat=None, interannual=None):
	"""The unit of the values of SPEC (that of the catalog, or a total for the sums, or % for the coefficient of
	variation, of the images or between the years: see catalog.unit_of; for the data of Earth Engine outside the
	catalog, the unit given, in UDUNITS, see catalog.custom_unit; '' if none was given), and of their statistic STAT
	over a region (% for the coefficient of variation), and of the metric between the years INTERANNUAL of a profile
	by day of the year (see time_series)."""
	unit = variables.entry_of(spec)['unit'] if variables.kind(spec) == 'catalog' else \
		catalog.custom_unit(spec.get('unit'))
	return catalog.unit_of(unit, spec.get('metric'), interannual or _between(spec), stat)


def _source_name(variable, source):
	"""What a table says of the variable of a result: the variable of the catalog, or the ID (as the tools take it:
	ee.ImageCollection("X") is X), band and terrain of the data of Earth Engine (e.g. 'IDAHO_EPSCOR/TERRACLIMATE pr'),
	as the titles (see variable.data_name)."""
	if variable:
		return variable
	if not (source.get('collection') or source.get('image')):
		return ''
	return variables.data_name({k: source.get(k) for k in ('collection', 'image', 'band', 'band_reducer', 'terrain')})


def _ylabel(spec, stat=None, interannual=None):
	"""Title of the y axis of the charts of SPEC (and of the statistic STAT of the regions, and of the metric between the
	years INTERANNUAL of a profile by day of the year): the unit, after the axis title of the catalog if it has one (e.g.
	'Snow Cover Frequency (SCF) [%]'); of a coefficient of variation, after its name."""
	unit = _unit(spec, stat, interannual)
	if variables.kind(spec) != 'catalog':  # in UDUNITS, without brackets: shown as those of the catalog
		unit = f'[{unit}]' if unit and not unit.startswith('[') else unit
	if catalog.is_cv(spec.get('metric'), interannual or _between(spec), stat):
		return f'Coefficient of variation {unit}'
	if variables.kind(spec) != 'catalog':
		return unit
	axis = variables.entry_of(spec).get('axis')
	return f'{axis} {unit}'.strip() if axis else unit


def _slug(text):
	return re.sub(r'[^A-Za-z0-9_-]+', '_', str(text)).strip('_')[:80]


# Time series -------------------------------------------------------------------------------------------------------

# the options of the chart by day of the year (time_series with doy): the seasonal profile, its other variable and axes
DOY_OPTIONS = ('interannual', 'other_variable', 'other_sensor', 'ylim', 'other_ylim')


def check_ylim(ylim, name='ylim'):
	"""(min, max) of a y axis given as YLIM (two numbers, or a text 'min, max'), or None if it is not given; ValueError
	(about the argument NAME) if it is not two numbers, the first smaller."""
	if ylim is None or (isinstance(ylim, (str, list, tuple)) and not str(ylim).strip('[]() ')):
		return None
	parts = re.split(r'[,;\s]+', ylim.strip().strip('[]()').strip()) if isinstance(ylim, str) else ylim
	try:
		if isinstance(parts, (str, bytes, dict)) or any(isinstance(x, bool) for x in parts):
			raise TypeError
		lo, hi = (float(x) for x in parts)
	except (TypeError, ValueError):
		raise ValueError(f'{name}: give two numbers, the lowest and the highest value of the y axis (e.g. [-1, 1]), '
		                 f'not {ylim!r}') from None
	if not (math.isfinite(lo) and math.isfinite(hi)) or lo >= hi:
		raise ValueError(f'{name}: the first number of the y axis ({lo:g}) must be smaller than the second ({hi:g})')
	return lo, hi


def _other_spec(variable, sensor, start, end, metric, season, quality, source):
	"""The spec of the other variable of a profile by day of the year (the right axis): a variable of the catalog with
	dates, with the period, season, metric, pixel filters and pixels of the region (where, exclude_landcover) of the
	first one, and its own rules (the SCF and the CF only take the metric mean); ValueError otherwise."""
	if '/' in str(variable):
		raise ValueError(f'other_variable {variable}: the variable of the right axis is a variable of the catalog of '
		                 'MonitorEO (e.g. NDVI, see list_variables), not data of Earth Engine by its ID')
	if not sensor:
		raise ValueError(f'other_variable {variable}: give its sensor (other_sensor), e.g. Sentinel-2')
	try:
		catalog.find(variable, sensor)
		spec = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality,
		                 where=source.get('where'), exclude_landcover=source.get('exclude_landcover'))
		variables.check_dates(spec, 'time series')
	except KeyError as e:
		raise ValueError(f'other_variable (the right axis): {e.args[0]}') from None
	except ValueError as e:
		raise ValueError(f'other_variable (the right axis): {e}') from None
	return spec


def _sensor_of(spec, sensor=None):
	"""The sensor of the variable of SPEC as the catalog names it (else SENSOR as given, or '')."""
	return variables.entry_of(spec)['sensor'] if variables.kind(spec) == 'catalog' else sensor or ''


@_cited
def time_series(region, variable=None, sensor=None, start=None, end=None, step='monthly', metric='mean', stat='mean',
                season=None, quality=None, scale=None, csv=None, chart=None, progress=None, doy=False,
                interannual=None, other_variable=None, other_sensor=None, ylim=None, other_ylim=None, **source):
	"""Time series of a variable over REGION (one or several features): a value per STEP ('daily', '16-day',
	'monthly', 'annual') and region, reduced in time with METRIC and over the region with STAT (mean, median, min,
	max, std or pN). Writes the table to CSV and the chart to CHART (PNG) if given. With DOY, the rows have also the
	year and the day of the year (1-366) of each step, and the chart has a line per year over the days of the year
	(a panel for each of the first 4 regions), to compare the years (phenology, snow seasons; as the day-of-year
	charts of geemap): not for an annual step. The snow cover days (metric days) are drawn with a bar per step (the
	key bars of the answer): with the step daily, a bar per day with images, the share of its clear pixels with snow
	(0 to 1 day).
	With DOY and INTERANNUAL (mean, median, min, max, std, cv or pN: see timeseries.over_years) or OTHER_VARIABLE, the
	seasonal profile instead: for each step of the year (each month, 16-day period or calendar day: see
	timeseries.doy_profile), INTERANNUAL (default median) of its values in the years of the period, a line per
	variable over the days of the year. OTHER_VARIABLE (and OTHER_SENSOR, default SENSOR) is a second variable of the
	catalog with dates, computed as the first one (region, period, season, step, metric, statistic, pixel filters,
	scale), drawn on a right axis (e.g. NDSI and NDVI). YLIM and OTHER_YLIM: (min, max) of the left and right y axes,
	only when given; else each axis goes from the minimum to the maximum of the values of its own variable. The CSV of
	the profile has its rows (timeseries.PROFILE_COLUMNS and PROFILE_META), not those of each year.
	Returns {'rows': [{region, date, value, n_pixels, n_images}], 'csv', 'chart', 'scale', 'unit', 'ylabel', 'title',
	'n_steps', 'regions'}; with DOY also 'ylim' (YLIM, or None: from the data), and the rows have year and doy; with
	the profile also 'profile' ([{region, variable, part, doy, label, value, n_years}]), 'variables' (the names of
	the variables, as in the rows and the profile, e.g. ['NDSI Sentinel-2', 'NDVI Sentinel-2']), 'units' and 'scales'
	({name: unit or pixel size}), 'interannual', 'other_ylabel' (None without OTHER_VARIABLE) and 'other_ylim'
	(OTHER_YLIM, or None: from the data), and the rows of both variables, each with its 'variable' when there are
	two."""
	given = [k for k, v in zip(DOY_OPTIONS, (interannual, other_variable, other_sensor, ylim, other_ylim))
	         if v is not None and v != '' and v != [] and v != ()]
	if given and not doy:
		raise ValueError(f"{', '.join(given)}: only for the chart by day of the year (doy)")
	if doy and step == 'annual':
		raise ValueError('a line per year over the days of the year (doy) needs a step shorter than a year: daily, '
		                 '16-day or monthly')
	other_variable = other_variable or None
	if not other_variable and ('other_sensor' in given or 'other_ylim' in given):
		raise ValueError('other_sensor and other_ylim are those of the variable of the right axis: give other_variable')
	if interannual not in (None, ''):
		interannual = timeseries.check_interannual(interannual)
	else:
		interannual = 'median' if other_variable else None
	ylim, other_ylim = check_ylim(ylim, 'ylim'), check_ylim(other_ylim, 'other_ylim')
	spec = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	variables.check_dates(spec, 'time series')
	other = _other_spec(other_variable, other_sensor or sensor, start, end, metric, season, quality, source) \
		if other_variable else None
	names = [_series_name(spec)] + ([_series_name(other)] if other else [])
	if other and names[0] == names[1]:
		raise ValueError(f'other_variable (the right axis): {names[1]} is already the variable of the left axis')
	profiled = bool(doy and interannual)
	regions = areas.region(region)
	first_total = [0]

	def first_progress(done, total):  # the steps of both variables
		first_total[0] = total
		progress(done, 2 * total)

	rows, used_scale = timeseries.series(spec, regions, step, metric, stat, scale,
	                                     first_progress if progress and other else progress)
	other_rows, other_scale = timeseries.series(
		other, regions, step, metric, stat, scale,
		(lambda done, total: progress(first_total[0] + done, first_total[0] + total)) if progress else None) \
		if other else ([], None)
	if doy:
		timeseries.with_doy(rows)
		timeseries.with_doy(other_rows)
	if other:
		for name, part in zip(names, (rows, other_rows)):
			for r in part:
				r['variable'] = name
		rows = sorted(rows + other_rows, key=lambda r: (r['region'], names.index(r['variable']), r['date']))
	unit = _unit(spec, stat, interannual if profiled else None)
	title = _title(spec, step, metric, stat) + (' | by day of the year' if doy else '')
	out = {'rows': rows, 'csv': None, 'chart': None, 'scale': used_scale, 'unit': unit,
	       'ylabel': _ylabel(spec, stat, interannual if profiled else None), 'title': title,
	       'n_steps': len({r['date'] for r in rows}), 'regions': sorted({r['region'] for r in rows}),
	       # the snow cover days (metric days) are drawn with a bar per step, by date (not by day of the year)
	       'bars': not doy and not profiled and composite.is_days(spec.get('metric'))}
	if doy:
		out['ylim'] = ylim
	if profiled:
		units, scales = {names[0]: unit}, {names[0]: used_scale}
		out.update(profile=timeseries.doy_profile(rows, spec, step, interannual, names[0]), variables=names,
		           units=units, scales=scales, interannual=interannual, other_ylabel=None, other_ylim=None,
		           title=_title(spec, step, metric, stat, ' and '.join(names))
		           + f' | {interannual} of the years by day of the year')
		if other:
			units[names[1]], scales[names[1]] = _unit(other, stat, interannual), other_scale
			out['other_ylabel'] = _ylabel(other, stat, interannual)
			out['other_ylim'] = other_ylim
			for k, name in (('ylabel', names[0]), ('other_ylabel', names[1])):  # two axes: each says its variable
				if name.split()[0] not in str(out[k] or ''):
					out[k] = f'{name} {out[k] or ""}'.strip()
	if csv and profiled:  # the profile, what the chart shows
		sensors_of = {names[0]: _sensor_of(spec, sensor)}
		if other:
			sensors_of[names[1]] = _sensor_of(other)
		table = [dict(r, sensor=sensors_of[r['variable']], step=step, metric=metric, stat=stat, interannual=interannual,
		              unit=catalog.udunits(out['units'][r['variable']]), scale_m=out['scales'][r['variable']])
		         for r in out['profile']]
		out['csv'] = timeseries.write_csv(table, csv, {}, timeseries.PROFILE_COLUMNS + timeseries.PROFILE_META)
	elif csv:
		meta = {'variable': _source_name(variable, source), 'sensor': sensor or '',
		        'step': step, 'metric': metric, 'stat': stat, 'unit': catalog.udunits(unit), 'scale_m': used_scale}
		out['csv'] = timeseries.write_csv(rows, csv, meta, timeseries.COLUMNS + (['year', 'doy'] if doy else []))
	if chart and rows:
		try:
			if profiled:
				charts.doy_profile_png(out['profile'], chart, out['title'], out['ylabel'] or None,
				                       out['other_ylabel'] or None, out['ylim'], out['other_ylim'], source=coverage.source())
			elif doy:
				charts.doy_png(rows, chart, title=title, ylabel=out['ylabel'] or None, ylim=out['ylim'],
				               source=coverage.source())
			else:
				charts.time_series_png(rows, chart, title=title, ylabel=out['ylabel'] or None, source=coverage.source(),
				                       bars=out['bars'])
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
	name = _slug(name or f"{_what(variable, sensor, source)}_{step}_{metric}_{start}_{end}")
	task = ee.batch.Export.table.toDrive(collection=table, description=name[:100], folder=folder, fileNamePrefix=name,
	                                     fileFormat='CSV', selectors=timeseries.COLUMNS)
	task.start()
	return {'operation': task.operation_name or f'projects/{_project}/operations/{task.id}', 'file': name + '.csv',
	        'folder': folder}


# Maps --------------------------------------------------------------------------------------------------------------

def composite_image(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                    interannual='mean', season=None, quality=None, clip=True, resolution=None, rgb=False, **source):
	"""Earth Engine image (ee.Image, band 'value') of a variable over REGION aggregated in time (for rgee, geemap,
	...: monitoreo.notebook puts it on a map of geemap with its colours); with RGB, the true colour of its images
	instead (bands red, green and blue: see rgb_map). Returns (image, regions)."""
	_, regions, img, _ = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                            quality, clip, resolution, source, rgb)
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
	Writes a PNG preview to THUMBNAIL if given (if Earth Engine cannot make it, the map comes without it: thumbnail
	None and the reason in thumbnail_error). A categorical layer (ECOREGION, BIOME) has the colour of each class and,
	instead of a colour ramp (min, max and palette None), the legend of its classes in the region, classes: [{'value',
	'label', 'color'}].
	Returns {'url', 'min', 'max', 'palette', 'name', 'unit', 'bounds' (of the region, [w, s, e, n]), 'thumbnail'}."""
	spec, regions, whole, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                   quality, False, None, source)
	img = whole.clipToCollection(regions) if clip else whole
	if variables.is_categorical(spec):  # class codes: the colour of each class, and the legend of those in the region
		vis, legend = _class_map(spec, regions)
		out = {'url': maps.tile_url(img, vis), 'min': None, 'max': None, 'palette': None, 'classes': legend,
		       'name': _named(spec, metric), 'unit': _unit(spec), 'bounds': _bounds(regions), 'thumbnail': None}
		return _preview(out, whole, vis, regions, res, thumbnail, clip)
	entry = ramp_entry(spec)
	# the data of Earth Engine outside the catalog have no range in it, nor the standard deviation and the coefficient
	# of variation in that of the variable: always from the map
	vis = maps.vis_params(img, regions.geometry(), entry, res, vmin, vmax, palette,
	                      compute=not quick or entry is None or spread(spec))
	out = dict(vis, url=maps.tile_url(img, vis), name=_named(spec, metric), unit=_unit(spec),
	           bounds=_bounds(regions), thumbnail=None)
	return _preview(out, whole, vis, regions, res, thumbnail, clip)


@_cited
def map_figure(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
               interannual='mean', season=None, quality=None, vmin=None, vmax=None, palette=None, path=None,
               title=None, dpi=300, width=7.0, dimensions=1600, **source):
	"""Figure of the map of a variable over REGION (as map_layer) for a report or a paper, as the maps of cartoee of
	geemap: PATH (.png, by default, .pdf or .svg) with the map (DIMENSIONS pixels of Earth Engine, with the outline of
	the region) on its longitudes and latitudes, a scale bar, a north arrow, the colour ramp (VMIN to VMAX, by default
	those of the map) with its unit, the TITLE (default: that of the map) and the credits of the data and the citation
	of MonitorEO; WIDTH inches at DPI (see monitoreo.figures). It needs matplotlib. A categorical layer (ECOREGION,
	BIOME) has the legend of its classes in the region instead of the colour ramp (classes, as map_layer).
	Returns {'file', 'min', 'max', 'palette', 'name', 'unit', 'bounds', 'scale', 'dpi'}."""
	figures.check(path, dpi)
	try:
		import matplotlib  # noqa: F401
	except ImportError:
		raise ValueError('a figure needs matplotlib: pip install matplotlib (or monitoreo[plot])') from None
	spec, regions, whole, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                   quality, False, None, source)
	geom = regions.geometry()
	legend = None
	if variables.is_categorical(spec):  # the colour of each class, and their legend instead of the colour ramp
		vis, legend = _class_map(spec, regions)
	else:
		vis = maps.vis_params(whole.clipToCollection(regions), geom, ramp_entry(spec), res, vmin, vmax, palette)
	bounds = figures.padded(_bounds(regions))
	img = maps.coarse(whole, res, bounds, dimensions).clipToCollection(regions)  # see maps.coarse
	png = maps.thumbnail(maps.with_outline(img, vis, regions), ee.Geometry.Rectangle(bounds, 'EPSG:4326', False), None,
	                     dimensions, crs='EPSG:4326')
	from . import about
	from .publish import unit_text
	cited = references.cite('map_figure', dict(source, variable=variable, sensor=sensor, start=start, end=end,
	                                           quality=quality, region=region))
	data = [f'Data: {coverage.source()}'] if coverage.source() else []  # where its values come from
	credits = data + list(cited.get('credits') or []) + [
		f'Computed with MonitorEO in Google Earth Engine. {about.CITATION}']
	name = _named(spec, metric)
	path = path or _slug(f"figure_{_file_stem(variable, sensor, metric, start, end, source)}") + '.png'
	figures.map_figure(png, bounds, vis, unit_text(_unit(spec)), title or name, credits, path, dpi, width, legend)
	if legend is not None:
		return dict(file=path, min=None, max=None, palette=None, classes=legend, name=name, unit=_unit(spec),
		            bounds=bounds, scale=res, dpi=int(dpi))
	return dict(vis, file=path, name=name, unit=_unit(spec), bounds=bounds, scale=res, dpi=int(dpi))


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
	preview to THUMBNAIL if given (if Earth Engine cannot make it, the map comes without it: thumbnail None and the
	reason in thumbnail_error).
	Returns {'url', 'bands', 'min', 'max', 'name', 'unit', 'bounds' (of the region, [w, s, e, n]), 'thumbnail'}."""
	spec, regions, whole, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                   quality, False, None, source, rgb=True)
	img = whole.clipToCollection(regions) if clip else whole
	vis = maps.rgb_vis(img, regions.geometry(), res, vmin, vmax, compute=not quick)
	out = dict(vis, url=maps.tile_url(img, vis), name=_rgb_name(spec, metric), unit=catalog.RGB_UNIT,
	           bounds=_bounds(regions), thumbnail=None)
	return _preview(out, whole, vis, regions, res, thumbnail, clip)


def _preview(out, img, vis, regions, res, path, clip=True):
	"""The result OUT of a map ({'url', 'bounds'...}) with its PNG preview: IMG (not clipped yet) coloured with VIS,
	computed on the pixels of the data (RES metres) when they are bigger than those of the preview (see maps.coarse),
	then clipped to REGIONS (with CLIP) on the pixels of the preview, with their outline, written to PATH (if given).
	The preview is only a picture of the map: if Earth Engine cannot make it, the map is there anyway (its tiles),
	with the reason in thumbnail_error (and thumbnail None)."""
	if not path:
		return out
	try:
		img = maps.coarse(img, res, out.get('bounds'))
		img = img.clipToCollection(regions) if clip else img
		maps.thumbnail(maps.with_outline(img, vis, regions), regions.geometry().bounds(), None, path=path)
		out['thumbnail'] = path
	except (ee.EEException, OSError) as e:  # Earth Engine, or the network
		out['thumbnail'], out['thumbnail_error'] = None, str(e)
	return out


def _bounds(regions):
	"""[west, south, east, north] (degrees) of REGIONS."""
	ring = regions.geometry().bounds(1).getInfo()['coordinates'][0]
	return [min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring)]


def variable_entry(spec):
	return variables.entry_of(spec) if variables.kind(spec) == 'catalog' else None


def spread(spec):
	"""Whether the values of the map of SPEC are a spread (standard deviation, coefficient of variation: see
	composite.SPREAD), of the images or between the years, not in the range of the variable."""
	return any(str(m or '').strip().lower() in composite.SPREAD for m in (spec.get('metric'), _between(spec)))


def ramp_entry(spec):
	"""The catalog entry of SPEC for the colour ramp of its map (None outside the catalog): its palette, and the
	range of its values when Earth Engine cannot compute it, that of the variable or, for a spread (see spread), 0 to
	100 % for the coefficient of variation and 0 to half the range of the variable for the standard deviation."""
	entry = variable_entry(spec)
	if entry is None or not spread(spec):
		return entry
	if catalog.is_cv(spec.get('metric'), _between(spec)):
		return dict(entry, minp=0, maxp=100)
	lo, hi = entry.get('minp'), entry.get('maxp')
	half = (hi - lo) / 2 if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) else 1
	return dict(entry, minp=0, maxp=half)


def thumbnail(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
              interannual='mean', season=None, quality=None, vmin=None, vmax=None, palette=None, dimensions=768,
              path=None, **source):
	"""PNG (bytes) of the map of a variable over REGION, with the outline of the region."""
	spec, regions, whole, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                   quality, False, None, source)
	if variables.is_categorical(spec):  # the colour of each class
		vis = _class_map(spec, regions)[0]
	else:
		vis = maps.vis_params(whole.clipToCollection(regions), regions.geometry(), ramp_entry(spec), res, vmin, vmax,
		                      palette)
	img = maps.coarse(whole, res, _bounds(regions), dimensions).clipToCollection(regions)  # see maps.coarse
	return maps.thumbnail(maps.with_outline(img, vis, regions), regions.geometry().bounds(), None, dimensions, path)


@_cited
def timelapse(region, variable=None, sensor=None, start=None, end=None, step='annual', metric='median', season=None,
              quality=None, vmin=None, vmax=None, palette=None, dimensions=animation.DIMENSIONS, fps=animation.FPS,
              path=None, progress=None, **source):
	"""Animation of a variable over REGION (a timelapse, GIF or MP4 video): a frame per STEP ('annual', 'monthly',
	'16-day' or 'daily') of the period (and SEASON), each the METRIC of the images of the step on each pixel, coloured
	with one colour ramp for every frame (VMIN to VMAX; by default from the percentiles 5 and 95 of the map of the whole
	period, as map_layer, or, for the sum and the count, which grow with the images, of the median of the frames: see
	animation.range_image) and with its date, the title, the ramp with its unit and the credits of the data (also
	those of the region) written on it; the pixels of the region without data in a step are light grey. At most
	animation.MAX_FRAMES frames of DIMENSIONS pixels (width or height of the map), FPS frames per second. PATH ends in
	.gif (default) or .mp4 (with ffmpeg). Earth Engine computes the colours of each frame on the same grid of web
	Mercator, several at a time (PROGRESS(done, total) after each), and they are joined in a GIF with their texts (see
	monitoreo.animation). Not for the fixed layers (elevation, slope, an image), which have no dates.
	Returns {'file' (the GIF or the MP4), 'gif', 'note' (why there is no MP4: without ffmpeg, the GIF only), 'frames': [{'date', 'end', 'label', 'images'}], 'n_frames', 'step',
	'fps', 'dimensions', 'min', 'max', 'palette', 'name', 'unit', 'bounds', 'scale' (m: the pixels on which the frames
	are computed, those of the frames or, if bigger, those of the data; see animation.pixel_size)}."""
	animation.check(step, dimensions=dimensions, fps=fps, path=path)
	animation.can_draw()
	spec = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	variables.check_dates(spec, 'animations')
	composite.check_metric(metric)
	steps = None if step == 'daily' else timeseries.bins(spec, step)  # the days with images need Earth Engine
	if steps is not None:
		animation.check(step, len(steps))
	regions = areas.region(region)
	geom = regions.geometry()
	if steps is None:
		steps = timeseries.bins(spec, step, geom)
		animation.check(step, len(steps))
	res = variables.native_scale(spec)
	bounds = _bounds(regions)
	col = variables.collection(spec, geom, res)
	whole = animation.range_image(col, steps, metric, variables.image(spec, geom, res)).clipToCollection(regions)
	vis = maps.vis_params(whole, geom, ramp_entry(spec), res, vmin, vmax, palette)
	frames = animation.frames(col, regions, steps, metric, vis, res, bounds, dimensions)
	pictures = animation.fetch_frames(frames, animation.frame_grid(bounds, dimensions), progress=progress)
	unmasked = variables.collection(dict(spec, resample='nearest', where=None, exclude_landcover=None), geom, 1e9)
	counts = ee.List([unmasked.filterDate(a, b).size() for a, b in steps]).getInfo()
	labels = [animation.label(step, a, b) + ('' if n else ' · no images') for (a, b), n in zip(steps, counts)]
	path = path or _slug(f"animation_{_file_stem(variable, sensor, metric, start, end, source)}_{step}") + '.gif'
	unit = _unit(spec)
	name = _named(spec, metric)
	from .publish import unit_text
	cited = references.cite('timelapse', dict(source, region=region, variable=variable, sensor=sensor, start=start,
	                                          end=end, quality=quality))
	data = [f'Data: {coverage.source()}'] if coverage.source() else []  # where its values come from
	credits = '; '.join(data + ['MonitorEO', 'Google Earth Engine'] + list(cited.get('credits') or []))
	video = os.path.splitext(path)[1].lower() == '.mp4'
	gif = animation.write(pictures, os.path.splitext(path)[0] + '.gif' if video else path, labels,
	                      f"{name} · {STEP_NAMES.get(step, step)}", vis['min'], vis['max'], vis['palette'],
	                      unit_text(unit), credits, fps)
	note = None
	if video:  # without ffmpeg (or if it fails) the animation is its GIF, and the note says why there is no MP4
		try:
			animation.to_mp4(gif, path)
		except ValueError as e:
			path, note = gif, f'no MP4 video: {e}'
	return dict(vis, file=path, gif=gif, note=note, step=step, fps=float(fps), dimensions=int(dimensions), name=name, unit=unit,
	            bounds=bounds, scale=animation.pixel_size(bounds, dimensions, res), n_frames=len(steps),
	            frames=[{'date': a, 'end': b, 'label': animation.label(step, a, b), 'images': n}
	                    for (a, b), n in zip(steps, counts)])


STEP_NAMES = {'annual': 'a frame per year', 'monthly': 'a frame per month', '16-day': 'a frame per 16 days',
              'daily': 'a frame per day with images'}


REGION_STATS = catalog.REGION_STATS  # the statistics of region_stats by default
REGION_STATS_ZONES = catalog.REGION_STATS_ZONES  # and with zones


@_cited
def region_stats(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                 interannual='mean', season=None, quality=None, stats=None, scale=None, zones=None, csv=None,
                 chart=None, **source):
	"""Statistics over each feature of REGION of the map of a variable aggregated in time: STATS, any of mean,
	median, min, max, std (standard deviation), cv (coefficient of variation, in %: 100 × std / mean) and pN
	(percentile N, e.g. p5, p50, p95), for any variable, also the fixed layers (elevation, slope, topographic wetness
	index, WorldClim); by default REGION_STATS, and with ZONES REGION_STATS_ZONES (also p25 and p75).
	With ZONES, those of each zone of each feature instead: the classes of another variable cut at some values, e.g.
	the elevation bands {'variable': 'ELEVATION', 'sensor': 'Copernicus', 'breaks': [1500, 2000, 2500]} (also
	'metric', 'temporal', 'interannual' and 'period' of a variable with dates, by default aggregated over the period of
	the result, as the conditions of where), with the rows of every zone of every feature (zone, zone_label,
	zone_from, zone_to); a CSV of the rows and, with ZONES, a CHART (PNG) of the median (or else the mean, or the first
	statistic) of each zone and its percentiles 25 and 75 (or else 5 and 95, if STATS has them and not those; with
	neither, no band; its legend says which). The zones of a categorical layer (ECOREGION, BIOME) are its classes,
	without breaks, e.g. {'variable': 'BIOME', 'sensor': 'RESOLVE'} (optionally 'classes', the codes of those to
	keep): the rows of the classes with pixels in each feature (zone, its code; zone_label, its code and name).
	A categorical layer as the variable has class codes, so its statistic is the majority class: STATS 'mode' (by
	default) and 'count', with mode_label (its code and name) in the rows; for the area of each class, area_by_class.
	{'rows': [{region, mean, std, cv, min, p5, p50, p95, max, n_pixels}], 'stats', 'scale', 'unit' (of the map: that of
	cv is %), 'title', 'csv', 'chart'}."""
	klass = _categorical(variable, sensor, source)  # class codes: their statistic is the majority class
	stats = [stats] if isinstance(stats, str) else list(stats or (['mode'] if klass else REGION_STATS_ZONES if zones
	                                                                  else REGION_STATS))
	for s in stats:
		composite.check_metric(s)  # before Earth Engine
	if klass:
		categorical.check_stats(klass, stats)
	zone_cuts = zones_of(zones)
	spec, regions, img, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                 quality, False, None, source)
	scale = scale or timeseries.auto_scale(spec, regions)
	red, names = composite.region_reducer(stats)
	crs = timeseries.region_crs(regions)
	rows = []
	if isinstance(zone_cuts, dict):  # the classes of a categorical layer: the rows of those with pixels
		zspec = _zone_spec(zones, spec)
		zentry = variables.entry_of(zspec)
		zone = _class_zone(zspec, regions.geometry(), scale, zone_cuts['classes'])
		fc = img.addBands(zone).reduceRegions(collection=regions, reducer=red.group(1, 'zone'), scale=scale, crs=crs,
		                                      tileScale=4)
		for f in fc.getInfo()['features']:
			p = f['properties']
			for g in sorted(p.get('groups') or [], key=lambda g: int(round(g['zone']))):
				z = int(round(g['zone']))
				row = {'region': str(p.get('name')), 'zone': z, 'zone_label': categorical.label(zentry, z),
				       'zone_from': None, 'zone_to': None}
				row.update({s: composite.value_of(g, s, names) for s in stats})
				row['n_pixels'] = g.get('count', 0)
				rows.append(row)
	elif zone_cuts:
		zspec = _zone_spec(zones, spec)
		legend = classes.break_classes(zone_cuts, unit_text_of(_unit(zspec)))
		zone = classes.classify_breaks(variables.image(zspec, regions.geometry(), scale), zone_cuts)
		fc = img.addBands(zone).reduceRegions(collection=regions, reducer=red.group(1, 'zone'), scale=scale, crs=crs,
		                                      tileScale=4)
		for f in fc.getInfo()['features']:
			p = f['properties']
			by = {int(g['zone']): g for g in p.get('groups') or []}
			for z, label, lo, hi in legend:
				row = {'region': str(p.get('name')), 'zone': z, 'zone_label': label, 'zone_from': lo, 'zone_to': hi}
				row.update({s: composite.value_of(by.get(z, {}), s, names) for s in stats})
				row['n_pixels'] = by.get(z, {}).get('count', 0)
				rows.append(row)
	else:
		fc = img.reduceRegions(collection=regions, reducer=red, scale=scale, crs=crs, tileScale=4)
		for f in fc.getInfo()['features']:
			p = f['properties']
			row = {'region': str(p.get('name'))}
			row.update({s: composite.value_of(p, s, names) for s in stats})
			row['n_pixels'] = p.get('count')
			rows.append(row)
	if klass and 'mode' in stats:  # the majority class: its code (a whole number) and its name
		for row in rows:
			mode = row.get('mode')
			row['mode'] = int(round(mode)) if mode is not None else None
			row['mode_label'] = categorical.label(klass, row['mode']) if mode is not None else None
	title = _named(spec, metric) + (f" by {zone_name(zones)}" if zone_cuts else '')
	out = {'rows': rows, 'stats': stats, 'scale': scale, 'unit': _unit(spec), 'title': title, 'csv': None, 'chart': None}
	if zone_cuts and not klass:
		out['ylabel'] = _ylabel(spec)
	if csv:
		columns = ['region'] + (['zone', 'zone_label', 'zone_from', 'zone_to'] if zone_cuts else []) + stats + \
			(['mode_label'] if klass and 'mode' in stats else []) + ['n_pixels']
		out['csv'] = timeseries.write_csv(rows, csv, {'variable': _source_name(variable, source),
		                                              'sensor': sensor or '', 'unit': catalog.udunits(out['unit']),
		                                              'scale_m': scale}, columns)
	if chart and zone_cuts and rows and not klass:  # (no chart of class codes: the table says the class of each zone)
		try:
			charts.zones_png(rows, stats, chart, title, _ylabel(spec), zone_name(zones), source=coverage.source())
			out['chart'] = chart
		except ImportError:
			pass
	return out


@_cited
def transect(line, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
             interannual='mean', season=None, quality=None, spacing=None, points=100, scale=None, csv=None, chart=None,
             **source):
	"""Profile of the map of a variable (as map_layer, also the fixed layers) along LINE ([[lon, lat], ...], a GeoJSON
	LineString, or {'geojson': ...} of one), with the elevation of the Copernicus DEM: the line is cut in segments of
	SPACING metres (default: its length / POINTS, at least the pixel of the data), and each segment gets the mean of the
	pixels it crosses (those within half a pixel of it: a segment shorter than a pixel would get none), as the transects
	of geemap. Writes the table to CSV and a chart of the variable and the elevation
	along the line to CHART (PNG).
	Returns {'rows': [{distance_m, lon, lat, value, elevation}], 'length_m', 'spacing', 'scale', 'unit', 'title', 'csv',
	'chart'}."""
	coords = transect_line(line)
	spec = make_spec(variable, sensor, start, end, metric=metric, temporal=temporal, interannual=interannual,
	                 season=season, quality=quality, **source)
	if variables.is_categorical(spec):  # the mean of class codes along a line means nothing
		e = variables.entry_of(spec)
		raise ValueError(f"{e['index']} ({e['sensor']}) is a categorical layer, whose values are class codes: no "
		                 'profile along a line (the mean of each segment); area_by_class gives the area of each class')
	geom = ee.Geometry.LineString(coords)
	length = float(geom.length(1).getInfo())
	native = float(variables.native_scale(spec))
	step = float(spacing) if spacing else max(native, length / max(int(points), 2))
	cuts = transect_cuts(length, step)
	segments = ee.List(geom.cutLines(cuts, 1).geometries())
	n = len(cuts) + 1  # the segments wanted: the rows (Earth Engine may give one fewer, the last row then empty)
	half = float(scale or native) / 2

	def segment(i):
		g = ee.Geometry(segments.get(i))
		return ee.Feature(g.buffer(half, 1), {'i': i, 'centre': g.centroid(1).coordinates()})

	fc = ee.FeatureCollection(ee.List.sequence(0, segments.size().subtract(1)).map(segment))
	value = variables.image(spec, geom.buffer(step), scale or native).rename('value')
	dem = variables.image(make_spec('ELEVATION', 'Copernicus'), geom.buffer(step), 30).rename('elevation')
	stats = ee.Image.cat([value, dem]).reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=scale or native,
	                                                 crs=areas.utm_of(*coords[len(coords) // 2]), tileScale=4)
	got = {int(f['properties']['i']): f['properties'] for f in stats.getInfo()['features']}
	rows = []
	for i in range(n):
		p = got.get(i, {})
		a, b = (cuts[i - 1] if i else 0.0), (cuts[i] if i < len(cuts) else length)
		lon, lat = (p.get('centre') or [None, None])[:2]
		rows.append({'distance_m': (a + b) / 2, 'lon': lon, 'lat': lat, 'value': p.get('value'),
		             'elevation': p.get('elevation')})
	title = f"{_named(spec, metric)} along a line of {length / 1000:.3g} km"
	out = {'rows': rows, 'length_m': length, 'spacing': step, 'scale': scale or native, 'unit': _unit(spec),
	       'ylabel': _ylabel(spec), 'title': title, 'csv': None, 'chart': None}
	if csv:
		out['csv'] = timeseries.write_csv(rows, csv, {'variable': _source_name(variable, source), 'sensor': sensor or '',
		                                              'unit': catalog.udunits(out['unit']), 'scale_m': out['scale']},
		                                  TRANSECT_COLUMNS)
	if chart and rows:
		try:
			charts.transect_png(rows, chart, title, _ylabel(spec), source=coverage.source())
			out['chart'] = chart
		except ImportError:
			pass
	return out


TRANSECT_COLUMNS = ['distance_m', 'lon', 'lat', 'value', 'elevation']


def transect_cuts(length, step):
	"""The distances (m) where a line of LENGTH metres is cut every STEP metres: none within a millionth of a step of
	its end (with STEP = LENGTH / N, N × STEP may fall a hair short of LENGTH, and its cut would add a segment of 0 m)."""
	return [step * i for i in range(1, int(length // step) + 2) if step * i < length - step * 1e-6]


def transect_line(line):
	"""The [[lon, lat], ...] of LINE (a list of points, a GeoJSON LineString, a Feature of one, or {'geojson': ...}),
	or ValueError before Earth Engine."""
	if isinstance(line, str):
		try:
			line = json.loads(line)
		except ValueError:
			raise ValueError('the line is a list of points [[lon, lat], ...] or a GeoJSON LineString') from None
	if isinstance(line, dict):
		line = line.get('geojson', line)
		if isinstance(line, dict) and line.get('type') == 'Feature':
			line = line.get('geometry')
		if isinstance(line, dict) and line.get('type') == 'FeatureCollection' and line.get('features'):
			line = line['features'][0].get('geometry')
		if not (isinstance(line, dict) and line.get('type') == 'LineString'):
			raise ValueError('the line is a list of points [[lon, lat], ...] or a GeoJSON LineString')
		line = line.get('coordinates')
	try:
		coords = [[float(p[0]), float(p[1])] for p in line]
	except (TypeError, ValueError, IndexError):
		raise ValueError('the line is a list of points [[lon, lat], ...] or a GeoJSON LineString') from None
	if len(coords) < 2:
		raise ValueError('a line has two points or more')
	if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in coords):
		raise ValueError('the points of the line are [longitude, latitude] in degrees')
	return coords


def zones_of(zones):
	"""The breaks of ZONES (see region_stats), checked before Earth Engine, or None without zones; for the zones of a
	categorical layer (ECOREGION, BIOME: its classes, without breaks), {'classes': the codes of those kept, or None for
	all of them}."""
	if not zones:
		return None
	if not isinstance(zones, dict) or not (zones.get('variable') or zones.get('index')):
		raise ValueError('zones is a variable of the catalog and its breaks, e.g. {"variable": "ELEVATION", "sensor": '
		                 '"Copernicus", "breaks": [1500, 2000, 2500]}, or a categorical layer, whose classes are the '
		                 'zones: {"variable": "BIOME", "sensor": "RESOLVE"}')
	unknown = set(zones) - {'variable', 'index', 'sensor', 'collection', 'breaks', 'metric', 'temporal', 'interannual',
	                        'period', 'quality', 'classes'}
	if unknown:
		raise ValueError(f"zones has unknown keys {', '.join(sorted(unknown))}: give variable, sensor and breaks (and "
		                 'metric, temporal, interannual or period for a variable with dates; classes for a categorical '
		                 'layer)')
	period = zones.get('period')
	if period and (not isinstance(period, (list, tuple)) or len(period) != 2):
		raise ValueError(f"the period of zones on {zones.get('variable') or zones.get('index')} is [start, end]")
	klass = _categorical(zones.get('variable') or zones.get('index'), zones.get('sensor'), zones)
	if klass:  # its classes are the zones
		if zones.get('breaks') not in (None, '', []):
			raise ValueError(f"the zones of {klass['index']} ({klass['sensor']}) are its classes (a categorical layer, of "
			                 'class codes): give no breaks (classes, optionally, the codes of those to keep)')
		cs = zones.get('classes')
		return {'classes': None if cs in (None, '', []) else categorical.check(klass, cs)}
	if zones.get('classes') not in (None, '', []):
		raise ValueError(f"classes are for the zones of a categorical layer (ECOREGION, BIOME): "
		                 f"{zones.get('variable') or zones.get('index')} takes breaks")
	return classes.check_breaks(zones.get('breaks') or [])


def zone_name(zones):
	"""The zones in words, e.g. «ELEVATION (Copernicus) bands», «BIOME (RESOLVE) classes»."""
	v = zones.get('variable') or zones.get('index')
	kind = 'classes' if _categorical(v, zones.get('sensor'), zones) else 'bands'
	return f"{v} ({zones['sensor']}) {kind}" if zones.get('sensor') else f'{v} {kind}'


def _class_zone(zspec, region, scale, codes=None):
	"""The image of the zones of the categorical layer ZSPEC over REGION on pixels of SCALE metres (band 'zone': the code
	of the class of each pixel; on pixels more than twice as big as those of the layer, the majority class), only of
	the classes CODES if given (as zoneClass of the Earth Engine app)."""
	zone = variables.image(zspec, region, scale)
	if codes:
		zone = zone.remap(codes, codes)
	return zone.rename('zone')


def _zone_spec(zones, spec):
	"""The spec of the variable of ZONES: aggregated over its own period, or that of the result SPEC (none for the
	fixed layers), with its metric (by default the mean), as the conditions of where."""
	period = zones.get('period') or spec.get('period') or [None, None]
	zspec = make_spec(zones.get('variable') or zones.get('index'), zones.get('sensor'), *period,
	                  metric=zones.get('metric') or 'mean', temporal=zones.get('temporal') or 'period',
	                  interannual=zones.get('interannual') or 'mean', quality=zones.get('quality'),
	                  collection=zones.get('collection'))
	if not variables.is_static(zspec):
		if not zspec.get('period'):
			raise ValueError(f"the zones of {zones.get('variable')} need a period: give one to the result, or "
			                 '"period" to zones')
	return zspec


def unit_text_of(unit):
	"""The unit of the catalog as shown ('°C', '' if dimensionless): see monitoreo.publish.unit_text."""
	from .publish import unit_text
	return unit_text(unit)


@_cited
def area_by_class(region, variable=None, sensor=None, start=None, end=None, metric=None, temporal='period',
                  interannual='mean', season=None, quality=None, landcover=None, year=None, breaks=None, trend=False,
                  step='annual', part=None, alpha=0.05, scale=None, csv=None, chart=None, other_year=None, **source):
	"""Hectares and % of each class over each feature of REGION (see monitoreo.classes), of one of:
	LANDCOVER, a land cover map of YEAR (see landcover_maps; default: its last year), each class of the map with its
	broad land cover; BREAKS, the map of a variable (as map_layer: METRIC, by default the median, TEMPORAL, INTERANNUAL;
	also the fixed layers) cut at those values, e.g. [0.2, 0.4, 0.6] (below 0.2, 0.2 to 0.4, 0.4 to 0.6, 0.6 or more);
	or TREND, the trend of a variable on each pixel (as trend_map: STEP, PART and METRIC of each year, by default the
	mean), in significant
	decrease, no significant trend and significant increase (Mann-Kendall p-value below ALPHA); or, for a categorical
	layer (ECOREGION, BIOME, sensor RESOLVE) without breaks nor trend, its own classes (mode 'classes'): those with area
	in some feature, the ecoregions with their biome (group, group_label) and the hectares of each biome
	('by_group'), with the colours of the classes. The area of each pixel is
	its true area, on pixels of SCALE metres (default: those of the data, bigger over big regions); the % is of the
	area with a class (the pixels without data are not counted). Writes the table to CSV and a bar chart to CHART (PNG).
	With a land cover map and OTHER_YEAR, its changes from YEAR to OTHER_YEAR instead (see monitoreo.classes): the
	hectares of each pair of classes (mode 'transitions'), 'by_landcover' (those of each pair of broad land covers),
	'changed_ha' and 'unchanged_ha' of each region, and a Sankey diagram of the broad land covers in CHART (of the
	first feature of the region, named in its title, when it has several); features with the same name are numbered
	('Sierra Nevada (2)').
	Returns {'rows': [{region, class, label, ..., ha, percent}] (every class in each feature, also in the features with
	the same name), 'mode', 'classes': [{class, label, colour}], 'scale', 'unit', 'title', 'csv', 'chart'} and, for a
	land cover map, 'by_landcover' (the hectares of each broad land cover in each feature)."""
	klass = None if landcover else _categorical(variable, sensor, source)
	mode = classes.mode_of(landcover, breaks, trend, klass)
	if mode == 'landcover' and (variable or sensor or source.get('collection') or source.get('image')):
		raise ValueError('a land cover map has its own classes: give landcover and year, without a variable nor sensor')
	if other_year not in (None, ''):
		if mode != 'landcover':
			raise ValueError('other_year is for the changes of a land cover map between two years (with landcover)')
		return _transitions(region, landcover, year, other_year, scale, csv, chart, source)  # the map, by its key
	if mode == 'landcover':
		if source.get('where') or source.get('exclude_landcover'):
			raise ValueError('where is for the classes of a variable (breaks, trend), not for those of a land cover map')
		m, year = classes.landcover_map(landcover, year)
		_landcover_used(m, year)
		regions = areas.region(region)
		res = scale or classes.scale_for(float(m['m']), regions)
		img = classes.source(m, year, regions.geometry())  # the argument landcover hides the module of that name
		legend = [(code, f'{code} {name}', {'landcover': k}) for code, name, k in classes.landcover_classes(m)]
		colours = {label: classes.LANDCOVER_COLOURS.get(more['landcover'], '9e9e9e') for _, label, more in legend}
		extra, unit = {'map': m['name'], 'year': year}, ''
		title = f"Area of each class of {m['name']} {year}"
	elif mode == 'breaks':
		cuts = classes.check_breaks(breaks)
		metric = metric or 'median'
		spec, regions, value, res0 = _build(region, variable, sensor, start, end, metric, temporal, interannual,
		                                    season, quality, False, None, source)
		res = scale or classes.scale_for(float(res0), regions)
		unit = _unit(spec)
		from .publish import unit_text
		img = classes.classify_breaks(value, cuts)
		legend = [(c, label, {'value_from': lo, 'value_to': hi})
		          for c, label, lo, hi in classes.break_classes(cuts, unit_text(unit))]
		palette = maps.ramp(ramp_entry(spec))
		colours = {label: _ramp_colour(palette, (i + 0.5) / len(legend)) for i, (_, label, _) in enumerate(legend)}
		extra = {}
		title = f"Area of each class of {_named(spec, metric)}"
	elif mode == 'classes':  # its own classes, on its pixels of the data (the mode would favour the biggest classes)
		spec, regions, value, res0 = _build(region, variable, sensor, start, end, metric, temporal, interannual,
		                                    season, quality, False, None, source)
		res = scale or classes.scale_for(float(res0), regions)
		img = value.rename('class')
		legend, colours, extra, unit = None, {}, {}, ''  # the legend: the classes with area (after Earth Engine)
		title = f"Area of each class of {_named(spec, metric)}"
	else:
		metric = metric or 'mean'  # the metric of each year of the trends
		spec, regions, trend_img, part, native, name = _trend(region, variable, sensor, start, end, step, part, metric,
		                                                      season, quality, None, None, source, clip=False)
		res = scale or classes.scale_for(native, regions)
		img = classes.classify_trend(trend_img, alpha)
		legend = [(c, label, {}) for c, label, _ in classes.TREND]
		colours = {label: colour for _, label, colour in classes.TREND}
		extra, unit = {}, _unit(spec)
		title = f"Area of each class of the trend of {name} (p < {alpha:g})"
	crs = timeseries.region_crs(regions)
	ha = classes.hectares(img, regions, res, crs)
	group = None
	if mode == 'classes':  # the classes with area in some feature, each with its colour (and its group: the biome)
		group = categorical.group_entry(klass)
		present = sorted({c for _, by in ha for c, h in by.items() if h})
		legend = [(c, categorical.label(klass, c), {} if group is None else
		           {'group': categorical.group_of(klass, c),
		            'group_label': categorical.label(group, categorical.group_of(klass, c))}) for c in present]
		colours = {label: categorical.colour(klass, c) for c, label, _ in legend}
	rows = classes.rows(ha, legend, extra)
	out = {'rows': rows, 'mode': mode, 'scale': res, 'unit': unit, 'title': title, 'csv': None, 'chart': None,
	       'classes': [{'class': c, 'label': label, 'colour': colours.get(label)} for c, label, _ in legend]}
	if mode == 'landcover':
		out['by_landcover'] = classes.by_landcover(ha, legend)
	if group is not None:
		out['by_group'] = classes.by_group(ha, legend, group)
	if csv:
		meta = {'variable': _source_name(variable, source), 'sensor': sensor or '', 'scale_m': res}
		if mode != 'landcover' and spec.get('period') and not variables.is_static(spec):
			meta['period'] = '/'.join(spec['period'])
		columns = [c for c in classes.COLUMNS[mode] if group is not None or c not in ('group', 'group_label')]
		out['csv'] = timeseries.write_csv(rows, csv, meta if mode != 'landcover' else {'scale_m': res}, columns)
	if chart and rows:
		try:
			charts.areas_png(rows, colours, chart, title, source=coverage.source())
			out['chart'] = chart
		except ImportError:  # no matplotlib: the table and the CSV are still there
			pass
	return out


def _transitions(region, key, year, other_year, scale, csv, chart, source):
	"""The changes of the land cover map KEY from YEAR to OTHER_YEAR (see area_by_class)."""
	if source.get('where') or source.get('exclude_landcover') or source.get('collection') or source.get('image'):
		raise ValueError('the changes of a land cover map take no variable nor where')
	m, year = classes.landcover_map(key, year)
	_, other = classes.landcover_map(key, other_year)
	if other == year:
		raise ValueError(f'give two different years of {m["name"]}: year and other_year')
	_landcover_used(m, year)
	_landcover_used(m, other)
	regions = areas.region(region)
	res = scale or classes.scale_for(float(m['m']), regions)
	geom = regions.geometry()
	img = classes.pairs(classes.source(m, year, geom), classes.source(m, other, geom))
	ha = classes.hectares(img, regions, res, timeseries.region_crs(regions))
	rows = classes.transition_rows(ha, m, year, other)
	broad = classes.broad_transitions(rows)
	change = classes.changed(rows)
	title = f"Changes of the classes of {m['name']} from {year} to {other}"
	labels = {c['key']: landcover.label(c['key']) for c in landcover.classes()}  # the module: no argument hides it
	out = {'rows': rows, 'mode': 'transitions', 'by_landcover': broad, 'scale': res, 'unit': '', 'title': title,
	       'csv': None, 'chart': None, 'year': year, 'other_year': other,
	       'changed_ha': {k: v[0] for k, v in change.items()}, 'unchanged_ha': {k: v[1] for k, v in change.items()},
	       'classes': [{'class': k, 'label': labels[k], 'colour': classes.LANDCOVER_COLOURS.get(k)} for k in labels]}
	if csv:
		out['csv'] = timeseries.write_csv(rows, csv, {'scale_m': res}, classes.COLUMNS['transitions'])
	first = next(iter(change), None)  # the first feature of the region with data (the first rows of the CSV)
	if chart and first is not None:
		try:
			charts.sankey_png([(r['from_label'], r['to_label'], r['ha']) for r in broad if r['region'] == first],
			                  {labels[k]: c for k, c in classes.LANDCOVER_COLOURS.items() if k in labels}, chart,
			                  f'{title}: broad land covers' + (f' ({first})' if len(change) > 1 else ''),
			                  (str(year), str(other)), source=coverage.source())
			out['chart'] = chart
		except ImportError:
			pass
	return out


def _landcover_used(m, year):
	"""Note that the values of the call come from the land cover map M of YEAR (its dataset of that year, see
	landcover.dataset): its data_source and the line «Data: ...» of its chart (see monitoreo.coverage)."""
	coverage.used({'image': landcover.dataset(m, year)})


def _ramp_colour(palette, t):
	"""The colour (hex) at T (0 to 1) of the ramp PALETTE, as Earth Engine interpolates it."""
	return '%02x%02x%02x' % animation.ramp(palette, 101)[int(round(max(0.0, min(1.0, t)) * 100))]


# Exports -----------------------------------------------------------------------------------------------------------
# Exports -----------------------------------------------------------------------------------------------------------

@_cited
def export_image(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                 interannual='mean', season=None, quality=None, resolution=None, crs='auto', folder='MonitorEO',
                 name=None, clip=True, **source):
	"""Export the map of a variable over REGION to a GeoTIFF in FOLDER of Google Drive, on a grid of RESOLUTION
	metres (default: that of the data) in CRS ('auto' = WGS 84 / UTM of the centre of the region, or EPSG:6933 for a
	region wider than 40 degrees of longitude: see areas.auto_crs).
	Returns {'operation', 'file', 'folder', 'grid'}."""
	spec, regions, img, res = _build(region, variable, sensor, start, end, metric, temporal, interannual, season,
	                                 quality, clip, resolution, source)
	grid = _grid(regions, res, crs)
	name = _slug(name or _file_stem(variable, sensor, metric, start, end, source))
	op = drive.export(img, grid, name, folder, _project)
	return {'operation': op, 'file': name + '.tif', 'folder': folder, 'grid': grid.describe()}


def _grid(regions, res, crs):
	"""Grid of RES metres in CRS ('auto' = WGS 84 / UTM of the centre or, for regions too wide for one, an equal-area
	CRS in metres: areas.auto_crs) that covers REGIONS."""
	geom = regions.geometry()
	if str(crs).lower() == 'auto':
		crs = areas.auto_crs(geom, 1)
	ring = geom.bounds(res, crs).getInfo()['coordinates'][0]
	xs, ys = [p[0] for p in ring], [p[1] for p in ring]
	return Grid.around(crs, res, min(xs), min(ys), max(xs), max(ys))


def _what(variable, sensor, source):
	"""The variable of a file name: 'NDVI_Modis', or the end of the ID of the data of Earth Engine and its band
	('TERRACLIMATE_pr'), or the reducer of its bands ('TERRACLIMATE_sum_aet_def': see variable.band_stem)."""
	if not variable and (source.get('collection') or source.get('image')):
		from . import assets  # the ID as the tools take it (ee.ImageCollection("X") is X), as the MCP server names it
		asset = assets.normalize(source.get('collection') or source.get('image')).rstrip('/').split('/')[-1]
		return '_'.join(str(x) for x in (asset, variables.band_stem(source), source.get('terrain')) if x)
	return f"{variable}_{sensor or ''}"


def _file_stem(variable, sensor, metric, start, end, source):
	if not variable and (source.get('collection') or source.get('image')):  # data of Earth Engine: the end of the ID
		what = _what(variable, sensor, source)
		return what if source.get('image') else f'{what}_{metric}_{start}_{end}'  # a fixed image: no metric nor period
	try:
		static = bool(variable) and bool(catalog.find(variable, sensor, source.get('collection'), source.get('ref'))
		                                 .get('static'))
	except KeyError:
		static = False
	if static:  # a fixed layer (elevation, slope): no metric nor period
		return f'{variable}_{sensor}'
	return f"{variable}_{sensor or ''}_{metric}_{start}_{end}"


@_cited
def download_image(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
                   interannual='mean', season=None, quality=None, resolution=None, crs='auto', path=None, clip=True,
                   max_pixels=None, tile=512, workers=8, progress=None, **source):
	"""Download the map of a variable over REGION to the GeoTIFF PATH (float32, NoData -9999) on a grid of RESOLUTION
	metres (default: that of the data; in a large area, 1 to 10 km, see areas.default_scale) in CRS ('auto' = WGS 84 /
	UTM of the centre of the region, or EPSG:6933 for a region wider than 40 degrees of longitude), directly: Earth Engine computes it in tiles of TILE pixels, WORKERS at
	a time (PROGRESS(done, total) after each one). With MAX_PIXELS, a grid with more pixels gets a pixel 2, 3, ... times
	bigger. Fine for small regions; for big ones at full resolution, export_image (Google Drive).
	A categorical layer (ECOREGION, BIOME) has class codes: on pixels more than twice as big as those of the data, the
	majority class (see monitoreo.categorical), and classes (the legend of the classes in the file, [{'value', 'label',
	'color'}]) instead of min, max and palette (None).
	Returns {'file', 'grid', 'resolution', 'native_resolution' (that of the data), 'images', 'name', 'unit', 'min',
	'max' (percentiles 5 and 95 of the values, as the maps of MonitorEO), 'palette'}."""
	spec = make_spec(variable, sensor, start, end, metric=metric, temporal=temporal, interannual=interannual,
	                 season=season, quality=quality, **source)
	regions = areas.region(region)
	native = float(variables.native_scale(spec))
	grid, res = _fit_grid(regions, resolution, crs, max_pixels, native)
	img = variables.image(spec, regions.geometry(), res)
	if clip:
		img = img.clipToCollection(regions)
	path = path or _slug(_file_stem(variable, sensor, metric, start, end, source)) + '.tif'
	desc = variables.describe(spec)
	download(img, grid, path, tile=tile, workers=workers, progress=progress,
	         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(desc, default=str)})
	out = {'file': path, 'grid': grid.describe(), 'resolution': res, 'native_resolution': native,
	       'images': variables.n_images(spec, regions.geometry()), 'name': _named(spec, metric), 'unit': _unit(spec)}
	if variables.is_categorical(spec):  # class codes: the legend of the classes in the file
		return dict(out, min=None, max=None, palette=None,
		            classes=categorical.legend(variables.entry_of(spec), _values(path)))
	vmin, vmax = _percentiles(path)
	return dict(out, min=vmin, max=vmax, palette=maps.ramp(variable_entry(spec)))


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
	grid, res = _fit_grid(regions, resolution, crs, max_pixels, native)
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


def _default_grid(regions, resolution, crs, native):
	"""(grid, pixel size) of a map of REGIONS: pixels of RESOLUTION m if given; else those of the data, NATIVE, or for a
	large area (more than areas.LARGE_AREA_KM2), 1 to 10 km, as its statistics (areas.default_scale). The area of its
	biggest feature is asked of Earth Engine only when the bounds of the region (those of the grid) are of a large area:
	a region is never bigger than its bounds."""
	res = float(resolution or native)
	grid = _grid(regions, res, crs)
	if not resolution and areas.is_large(grid.pixels * res ** 2):
		area = areas.max_area(regions)
		if areas.is_large(area):
			res = areas.default_scale(res, area, timeseries.TARGET_PIXELS)
			grid = _grid(regions, res, grid.crs)
	return grid, res


def _fit_grid(regions, resolution, crs, max_pixels=None, native=None):
	"""(grid, pixel size) of REGIONS: pixels of RESOLUTION m (default: those of the data, NATIVE, or 1 to 10 km in a
	large area, see _default_grid), or 2, 3, ... times bigger if the grid has more than MAX_PIXELS."""
	grid, res = _default_grid(regions, resolution, crs, native)
	if max_pixels and grid.pixels > max_pixels:
		res *= math.ceil(math.sqrt(grid.pixels / max_pixels))
		grid = _grid(regions, res, grid.crs)
	return grid, res


class TooManyPixels(ValueError):
	"""The map of a region on the pixels of the data would have more pixels than a tool downloads (see check_pixels).
	Its attributes: pixels (of the grid), max_pixels, resolution (m), excess (% over max_pixels), share (the % of
	the extent of the region that would fit) and sensors ([{'sensor', 'resolution', 'pixels'}] of the same variable whose
	map fits, from the finest pixels)."""

	def __init__(self, pixels, max_pixels, resolution, sensors=()):
		self.pixels, self.max_pixels, self.resolution, self.sensors = pixels, max_pixels, resolution, list(sensors)
		self.excess = -(-100 * (pixels - max_pixels) // max_pixels)  # rounded up, in integers (no floating error)
		share = 100 * max_pixels / pixels  # rounded down to 2 significant digits: a region of that share fits
		step = 10 ** (math.floor(math.log10(share)) - 1)
		self.share = math.floor(share / step + 1e-9) * step
		fit = ', '.join(f"{s['sensor']} ({s['resolution']:g} m)" for s in self.sensors)
		super().__init__(
			f'the map at {resolution:g} m, the pixels of the data, would have {pixels:,} pixels: {self.excess:,}% more '
			f'than the {max_pixels:,} that can be downloaded. Choose '
			+ (f'another sensor ({fit}), ' if fit else '')
			+ f'a region with at most {self.share:g}% of its extent, or export the map to Google Drive (no limit)')


def check_pixels(region, max_pixels, variable=None, sensor=None, resolution=None, crs='auto', sensors=None, rgb=False,
                 **opts):
	"""Before computing the map of REGION to download (download_image, download_rgb, download_trend,
	download_comparison, burn_severity), whether its grid with pixels of RESOLUTION m (default: those of the data;
	in a large area, 1 to 10 km, see areas.default_scale) has at most MAX_PIXELS pixels. Only the bounds of the region
	(and, when they are of a large area, the area of its biggest feature) are asked of Earth Engine, nothing is
	computed.
	OPTS: the other arguments of the variable (those of make_spec; the rest are ignored). If it fits, returns
	{'pixels', 'max_pixels', 'resolution'}; if not, raises TooManyPixels, which says by how much the map exceeds the
	limit and what to change: the other sensors of the same variable (only those of SENSORS, if given, and with RGB
	only those with a true colour) whose map fits, a smaller region or the export to Google Drive. The period does not
	change the pixels of a map."""
	known = inspect.signature(make_spec).parameters
	spec = make_spec(variable, sensor, **{k: v for k, v in opts.items() if k in known})
	grid, res = _default_grid(areas.region(region), resolution, crs, variables.native_scale(spec))
	if grid.pixels <= max_pixels:
		return {'pixels': grid.pixels, 'max_pixels': max_pixels, 'resolution': res}
	fit = {}  # of each other sensor of the variable, its finest pixels whose map fits
	if variables.kind(spec) == 'catalog':
		from . import sensors as sensors_  # (SENSORS, the argument, hides the module)
		entry = variables.entry_of(spec)
		allowed = {catalog.name_key(s) for s in sensors} if sensors else None
		for e in catalog.variables():
			key = catalog.name_key(e['sensor'])
			if (e['index'] != entry['index'] or key == catalog.name_key(entry['sensor']) or not e.get('m')
			        or (allowed is not None and key not in allowed) or (rgb and sensors_.rgb_of(e) is None)):
				continue
			other = {'sensor': e['sensor'], 'resolution': float(e['m']),
			         'pixels': math.ceil(grid.pixels * (res / float(e['m'])) ** 2)}
			if other['pixels'] <= max_pixels and (key not in fit or other['resolution'] < fit[key]['resolution']):
				fit[key] = other
	raise TooManyPixels(grid.pixels, max_pixels, res, sorted(fit.values(), key=lambda o: o['resolution']))


def _values(path, band=1):
	"""The different valid values of a band of a GeoTIFF (the codes of the classes of a categorical layer), as whole
	numbers, from the lowest."""
	import numpy as np
	from osgeo import gdal
	gdal.UseExceptions()
	ds = gdal.Open(path)
	b = ds.GetRasterBand(band)
	a = b.ReadAsArray()
	a = a[(a != b.GetNoDataValue()) & np.isfinite(a)]
	ds = None
	return [int(v) for v in np.unique(np.round(a))]


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
	unit = _unit(spec, stat)
	title = _title(spec) + f' | trends of the {step} {metric}, spatial {stat}'
	out = {'rows': rows, 'yearly': yearly, 'csv': None, 'chart': None, 'scale': used, 'unit': unit,
	       'ylabel': _ylabel(spec, stat), 'title': title}
	if csv:
		meta = {'variable': _source_name(variable, source), 'sensor': sensor or '',
		        'step': step, 'metric': metric, 'stat': stat, 'unit': catalog.udunits(unit),
		        'slope_unit': catalog.udunits(unit, per_year=True),
		        'scale_m': used}
		out['csv'] = timeseries.write_csv(rows, csv, meta, TREND_COLUMNS)
	if chart and any(r['slope'] is not None for r in rows):
		try:
			charts.trends_png(yearly, rows, chart, title=title, ylabel=out['ylabel'] or None, source=coverage.source())
			out['chart'] = chart
		except ImportError:  # no matplotlib
			pass
	return out


def _trend(region, variable, sensor, start, end, step, part, metric, season, quality, alpha, res, source, clip=True):
	spec = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	variables.check_dates(spec, 'trends')
	regions = areas.region(region)
	part = _part(step, part)
	native = float(variables.native_scale(spec))
	img = trends.trend_image(spec, regions.geometry(), res or native, step, part, metric)
	if alpha:
		img = img.updateMask(img.select('p_value').lt(alpha))
	name = f"{_title(spec)} | trend {trends.part_key(step, part)} ({metric})"
	return spec, regions, img.clipToCollection(regions) if clip else img, part, native, name


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
	Returns {'url', 'min', 'max', 'palette', 'name', 'unit', 'bounds', 'thumbnail'} (thumbnail None, and the reason in
	thumbnail_error, if Earth Engine cannot make the PNG preview)."""
	if output not in trends.OUTPUTS:
		raise ValueError(f"unknown output {output}: use {', '.join(trends.OUTPUTS)}")
	spec, regions, img, part, native, name = _trend(region, variable, sensor, start, end, step, part, metric, season,
	                                                quality, alpha, None, source, clip=False)
	whole = img.select(output)  # the preview is clipped on its own pixels (see _preview)
	band = whole.clipToCollection(regions)
	vis = trends.vis(output)
	quick = quick and variable_entry(spec) is not None  # the data outside the catalog have no range in it
	if quick and (vis is None or (output in ('slope', 'z', 'n') and (vmin is None or vmax is None))):
		entry = ramp_entry(spec) or {}  # the range of the yearly values (0 to 100 % for the coefficient of variation)
		span = entry.get('maxp', 1) - entry.get('minp', 0) if all(
			isinstance(entry.get(k), (int, float)) for k in ('minp', 'maxp')) else 1
		years = int(str(end)[:4]) - int(str(start)[:4]) + 1
		lo, hi = {'slope': (-0.02 * span, 0.02 * span), 'n': (0, years)}.get(output, (None, None))
		vis = trends.vis(output, lo, hi) or maps.vis_params(band.rename('value'), None, entry, native, compute=False)
	elif vis is None or (output in ('slope', 'z', 'n') and (vmin is None or vmax is None)):
		auto = maps.vis_params(band.rename('value'), regions.geometry(), ramp_entry(spec), native)
		vis = trends.vis(output, auto['min'], auto['max']) or auto
	vis = dict(vis, **({'min': vmin} if vmin is not None else {}), **({'max': vmax} if vmax is not None else {}))
	if palette:
		vis['palette'] = maps.ramp(None, palette)
	unit = _unit(spec)
	out = dict(vis, url=maps.tile_url(band, vis), name=f'{name}: {output}', bounds=_bounds(regions), thumbnail=None,
	           unit=(f'{unit} / year' if unit else '') if output == 'slope' else unit if output == 'intercept' else '')
	return _preview(out, whole, vis, regions, native, thumbnail)


@_cited
def download_trend(region, variable=None, sensor=None, start=None, end=None, step='annual', part=None, metric='mean',
                   season=None, quality=None, alpha=None, resolution=None, crs='auto', path=None, max_pixels=None,
                   tile=512, workers=8, progress=None, **source):
	"""Download the trend of a part of the year of a variable over REGION (see trend_map) to the GeoTIFF PATH, with a
	band per output: slope, tau, z, p_value, intercept, n (NoData -9999 where there are fewer than 2 years or, with
	ALPHA, p_value >= ALPHA), on a grid of RESOLUTION metres (default: that of the data, or 1 to 10 km in a large area;
	2, 3, ... times bigger if the grid has more than MAX_PIXELS).
	Returns {'file', 'bands', 'grid', 'resolution', 'native_resolution', 'name', 'unit' (of the slope), 'min', 'max'
	(symmetric range of the slope), 'palette'}."""
	regions_ = areas.region(region)
	spec0 = make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	variables.check_dates(spec0, 'trends')
	native = float(variables.native_scale(spec0))
	grid, res = _fit_grid(regions_, resolution, crs, max_pixels, native)
	spec, regions, img, part, native, name = _trend(regions_, variable, sensor, start, end, step, part, metric, season,
	                                                quality, alpha, res, source)
	path = path or _slug(f"trend_{_file_stem(variable, sensor, metric, start, end, source)}_{trends.part_key(step, part)}") + '.tif'
	download(img, grid, path, tile=tile, workers=workers, progress=progress, bands=list(trends.OUTPUTS),
	         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(dict(
	             variables.describe(spec), trend=step, part=trends.part_key(step, part), alpha=alpha), default=str)})
	lo, hi = _percentiles(path)
	vis = trends.vis('slope', lo, hi)
	return dict(vis, file=path, bands=list(trends.OUTPUTS), grid=grid.describe(), resolution=res,
	            native_resolution=native, name=name, unit=f'{_unit(spec)} / year' if _unit(spec) else '')


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
	unit = _unit(ref, stat)
	title = (f"{_title(dict(ref, period=None))} | {ref['period'][0]} / {ref['period'][1]} vs "
	         f"{oth['period'][0]} / {oth['period'][1]} | {step} {metric}, spatial {stat}")
	names = tuple(a[:4] if a[:4] == b[:4] else f'{a[:4]}-{b[:4]}' for a, b in (ref['period'], oth['period']))
	out = {'profile': profile, 'rows': ref_rows + oth_rows, 'csv': None, 'chart': None, 'scale': scale, 'unit': unit,
	       'ylabel': _ylabel(ref, stat), 'title': title, 'periods': {'reference': ref['period'], 'other': oth['period']},
	       'names': names}
	if csv:
		meta = {'variable': _source_name(variable, source), 'sensor': sensor or '',
		        'reference_period': '/'.join(ref['period']), 'other_period': '/'.join(oth['period']), 'step': step,
		        'metric': metric, 'stat': stat, 'unit': catalog.udunits(unit), 'scale_m': scale}
		out['csv'] = timeseries.write_csv(profile, csv, meta, COMPARISON_COLUMNS)
	if chart and any(r['reference'] is not None or r['other'] is not None for r in profile):
		try:
			labels = {r['part']: r['key'] if step == '16-day' else r['label'][:3] if step == 'monthly' else r['label']
			          for r in profile}
			charts.comparison_png(profile, labels, chart, title=title, ylabel=out['ylabel'] or None, names=names,
			                      source=coverage.source())
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
                quality, res, source, two_periods=False, clip=True):
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
	img = ee.Image.cat([b.subtract(a), a, b]).rename(['difference', 'reference', 'other'])
	img = img.clipToCollection(regions) if clip else img
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
	Returns {'url', 'min', 'max', 'palette', 'name', 'unit', 'bounds', 'thumbnail'} (thumbnail None, and the reason in
	thumbnail_error, if Earth Engine cannot make the PNG preview)."""
	spec, regions, img, native, name = _comparison(region, variable, sensor, start, end, other_start, other_end, metric,
	                                               temporal, interannual, season, quality, None, source, clip=False)
	whole = img.select('difference')  # the preview is clipped on its own pixels (see _preview)
	diff = whole.clipToCollection(regions)
	if vmin is None or vmax is None:
		auto = maps.vis_params(diff.rename('value'), regions.geometry(), None, native)
		vis = trends.vis('difference', auto['min'], auto['max'])
	else:
		vis = {'min': vmin, 'max': vmax, 'palette': trends.DIVERGING}
	if palette:
		vis['palette'] = maps.ramp(None, palette)
	out = dict(vis, url=maps.tile_url(diff, vis), name=f'{name}: difference', unit=_unit(spec),
	           bounds=_bounds(regions), thumbnail=None)
	return _preview(out, whole, vis, regions, native, thumbnail)


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
	grid, res = _fit_grid(regions_, resolution, crs, max_pixels, variables.native_scale(spec0))
	spec, regions, img, native, name = _comparison(regions_, variable, sensor, start, end, other_start, other_end,
	                                               metric, temporal, interannual, season, quality, res, source)
	path = path or _slug(f"comparison_{_what(variable, sensor, source)}_{metric}_{start}_{end}_"
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
RBR_COLUMNS = ['region', 'mean', 'median', 'std', 'cv', 'p10', 'p90', 'min', 'max', 'ha']
RDNBR_COLUMNS = ['region', 'class', 'label', 'rdnbr_min', 'rdnbr_max', 'ha']
BURN_INDICES = ('dNBR', 'RBR', 'RdNBR')
# the sensors of each burn index (those of its entries of the catalog: NBR, RBR, RdNBR)
BURN_SENSORS = {'dNBR': ('Sentinel-2', 'Landsat'), 'RBR': ('Sentinel-2', 'Landsat'),
                'RdNBR': ('Sentinel-2', 'Landsat', 'Modis')}


@_cited
def burn_severity(region, sensor='Sentinel-2', start=None, end=None, other_start=None, other_end=None,
                  metric='median', season=None, quality=None, resolution=None, crs='auto', path=None, csv=None,
                  max_pixels=None, tile=512, workers=8, progress=None, index='dNBR', where=None, collection=None,
                  perimeter=None, burned_min=None, min_ha=None):
	"""Burn severity of a fire over each feature of REGION (see monitoreo.fire): the dNBR, NBR of a period before the
	fire (START to END) minus NBR of a period after it (OTHER_START to OTHER_END), each the METRIC of the images of
	SENSOR ('Sentinel-2' or 'Landsat') in its period, and its classes of the USGS (Key & Benson 2006). The hectares of
	each class are computed by Earth Engine on pixels of RESOLUTION metres (default: those of the data; 1 to 10 km in a
	large area). Writes the
	table to CSV and, with PATH, a GeoTIFF with the bands dnbr, severity (class -2 to 4), nbr_before and nbr_after.
	Returns {'index': 'dNBR', 'classes': [{region, class, label, dnbr_min, dnbr_max, ha}], 'burned_ha': {region:
	hectares with dNBR >= 0.1}, 'scale', 'title', 'csv', 'file', 'bands', 'grid', 'resolution', 'native_resolution'}.

	With INDEX 'RBR', the Relativized Burn Ratio instead: RBR = dNBR / (NBR before + 1.001), with the NBR of the
	catalog entry RBR (bands B8A and B12 in Sentinel-2, as Silva-Cardoza et al. 2022; NIR and SWIR2 in Landsat),
	without phenological correction and on the scale of the dNBR (the articles multiply it by 1000). A continuous
	map, without classes: {'index': 'RBR', 'stats': [{region, mean, median, std (standard deviation), cv (coefficient
	of variation, %), p10, p90, min, max, ha (of the pixels with values)}], ...} and the GeoTIFF bands rbr, dnbr,
	nbr_before and nbr_after.

	With INDEX 'RdNBR', the relative dNBR of Miller & Thode 2007: RdNBR = dNBR / sqrt(|NBR before|), with |NBR
	before| at least 0.001 (Howe et al. 2022), with the NBR of the catalog entry RdNBR (B8 and B12 in Sentinel-2, as
	Howe et al. 2022; NIR and SWIR2 in Landsat; bands 2 and 7 of the daily surface reflectance of MODIS, SENSOR
	'Modis': Terra, MOD09GA, or, with COLLECTION 'MODIS/061/MYD09GA', Aqua), without the offset of the dNBR of the
	unburned area around the fire and on the scale of the dNBR (the article multiplies it by 1000), and its classes
	of the article (its Table 4: 0 unchanged, RdNBR < 0.069; 1 low, 0.069 to 0.316; 2 moderate, 0.316 to 0.641; 3
	high, >= 0.641): {'index': 'RdNBR', 'classes': [{region, class, label, rdnbr_min, rdnbr_max, ha}], 'burned_ha':
	{region: hectares with RdNBR >= 0.069, those of the classes low to high}, 'stats': [{region, mean, median, p10,
	p90, min, max, ha}] of the RdNBR, ...}, the table of the classes in CSV and the GeoTIFF bands rdnbr, severity
	(class 0 to 3), dnbr, nbr_before and nbr_after.

	The median and the percentiles of the statistics of the RBR and the RdNBR come from a histogram of
	fire.PERCENTILE_BUCKETS buckets (see fire.stats_reducer): within about 0.001 of those of the pixels, even with a
	few extreme values.

	WHERE: only the pixels that pass these conditions on variables (as in the other tools), computed over the period
	before the fire.

	PERIMETER: the vector file (.gpkg, .geojson or .shp) where to write the perimeter of the burned area, to use
	it as the region of other analyses ({'file': PERIMETER, 'name_field': 'region'}): a feature for each feature of
	REGION, a MultiPolygon in EPSG:4326 of its burned pixels (index at least BURNED_MIN: by default the value from
	which a pixel is burned, dNBR 0.1, or changed, RdNBR 0.069; the RBR, without classes, needs it), joined when they
	touch, even by a corner, without the patches of less than MIN_HA hectares (default fire.PERIMETER_MIN_HA, 1 ha)
	and with the unburned islands of less than MIN_HA inside them filled (0: every burned pixel, every island). Its
	fields are those of fire.PERIMETER_FIELDS: region, ha (its area), patches (its burned patches of 8 connected
	pixels), index, burned_min, min_ha, sensor, before and after. The answer then has also 'perimeter' (its path),
	'perimeter_ha' ({region: hectares}), 'perimeter_patches' ({region: patches}), 'burned_min' and 'min_ha'."""
	index = {i.lower(): i for i in BURN_INDICES}.get(str(index or 'dNBR').lower())
	if index is None:
		raise ValueError(f"unknown burn index: use {', '.join(BURN_INDICES[:-1])} or {BURN_INDICES[-1]}")
	outline = _perimeter_args(index, perimeter, burned_min, min_ha, sensor, (start, end), (other_start, other_end))
	known = {s.lower().replace(' ', ''): s for s in BURN_SENSORS[index]}
	if sensor is not None and str(sensor).lower().replace(' ', '') not in known:
		raise ValueError(f"the burn index {index} is computed with the sensors {', '.join(BURN_SENSORS[index])}, not "
		                 f"{sensor}" + (': MODIS only with index RdNBR' if str(sensor).lower() == 'modis' else ''))
	if collection and (index != 'RdNBR' or str(sensor or '').lower().replace(' ', '') != 'modis'):
		raise ValueError('collection is only for the index RdNBR with sensor Modis (MODIS/061/MOD09GA, Terra, or '
		                 'MODIS/061/MYD09GA, Aqua)')
	if index == 'RBR':
		return _rbr(region, sensor, start, end, other_start, other_end, metric, season, quality, resolution, crs, path,
		            csv, max_pixels, tile, workers, progress, where, outline=outline)
	if index == 'RdNBR':
		return _rdnbr(region, sensor, start, end, other_start, other_end, metric, season, quality, resolution, crs,
		              path, csv, max_pixels, tile, workers, progress, where, collection, outline=outline)
	regions_ = areas.region(region)
	spec0 = make_spec('NBR', sensor, start, end, metric=metric, season=season, quality=quality)
	grid, res = _fit_grid(regions_, resolution, crs, max_pixels, variables.native_scale(spec0))
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
	if outline:
		out.update(_burn_perimeter(dnbr, regions, res, grid.crs, outline))
	return out


# the statistics of the RBR and the RdNBR: the standard deviation and the coefficient of variation (%) too
BURN_STATS = ('mean', 'median', 'std', 'cv', 'p10', 'p90', 'min', 'max')
_BURN_OUTPUTS = {'mean': 'mean', 'median': 'median', 'std': 'stdDev', 'p10': 'p10', 'p90': 'p90', 'min': 'min',
                 'max': 'max'}  # the outputs of fire.stats_reducer


def _burn_stats(index, band, regions, scale, crs):
	"""The statistics of the burn index INDEX (an ee.Image of the band BAND, rbr or rdnbr) over each feature of REGIONS,
	with the percentiles of fire.stats_reducer: [{region, mean, median, std, cv, p10, p90, min, max, ha (of the pixels
	with values)}]."""
	ha = ee.Image.pixelArea().divide(1e4).updateMask(index.mask()).rename('ha')
	stats = index.addBands(ha).reduceRegions(
		collection=regions, reducer=fire.stats_reducer().combine(ee.Reducer.sum(), '', True), scale=scale, crs=crs,
		tileScale=4).getInfo()['features']
	rows = []
	for f in stats:
		p = f['properties']
		rows.append(dict({'region': str(p.get('name'))},
		                 **{k: composite.value_of(p, k, _BURN_OUTPUTS, f'{band}_') for k in BURN_STATS},
		                 ha=p.get('ha_sum') or 0.0))
	return rows


def _rbr(region, sensor, start, end, other_start, other_end, metric, season, quality, resolution, crs, path, csv,
         max_pixels, tile, workers, progress, where=None, outline=None):
	"""burn_severity with the index RBR."""
	regions_ = areas.region(region)
	spec0 = make_spec('RBR', sensor, start, end, metric=metric, season=season, quality=quality, two_periods=True)
	grid, res = _fit_grid(regions_, resolution, crs, max_pixels, variables.native_scale(spec0))
	spec, regions, img, native, name = _comparison(regions_, 'RBR', sensor, start, end, other_start, other_end,
	                                               metric, 'period', 'mean', season, quality, res,
	                                               {'where': where} if where else {}, two_periods=True)
	before, after = img.select('reference'), img.select('other')
	dnbr = before.subtract(after).rename('dnbr')
	rbr = fire.rbr(dnbr, before)
	rows = _burn_stats(rbr, 'rbr', regions, res, grid.crs)
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
	if outline:
		out.update(_burn_perimeter(rbr, regions, res, grid.crs, outline))
	return out


def _rdnbr(region, sensor, start, end, other_start, other_end, metric, season, quality, resolution, crs, path, csv,
           max_pixels, tile, workers, progress, where=None, collection=None, outline=None):
	"""burn_severity with the index RdNBR (Miller & Thode 2007), with the classes of the article."""
	regions_ = areas.region(region)
	source = dict({'where': where} if where else {}, **({'collection': collection} if collection else {}))
	spec0 = make_spec('RdNBR', sensor, start, end, metric=metric, season=season, quality=quality, two_periods=True,
	                  collection=collection)
	grid, res = _fit_grid(regions_, resolution, crs, max_pixels, variables.native_scale(spec0))
	spec, regions, img, native, name = _comparison(regions_, 'RdNBR', sensor, start, end, other_start, other_end,
	                                               metric, 'period', 'mean', season, quality, res, source,
	                                               two_periods=True)
	before, after = img.select('reference'), img.select('other')
	dnbr = before.subtract(after).rename('dnbr')
	rdnbr = fire.rdnbr(dnbr, before)
	severity = fire.classify(rdnbr, 'RdNBR')
	ha = ee.Image.pixelArea().divide(1e4).updateMask(rdnbr.mask())
	groups = ha.addBands(severity).reduceRegions(collection=regions, reducer=ee.Reducer.sum().group(1, 'class'),
	                                              scale=res, crs=grid.crs, tileScale=4).getInfo()['features']
	classes = []
	for f in groups:
		classes += fire.table(f['properties'].get('groups'), str(f['properties'].get('name')), 'RdNBR')
	burned = {}
	for r in classes:
		burned[r['region']] = burned.get(r['region'], 0.0) + (r['ha'] if r['class'] >= 1 else 0.0)
	rows = _burn_stats(rdnbr, 'rdnbr', regions, res, grid.crs)
	col = variables.entry_of(spec)['col']  # MODIS: its product, so that Terra (MOD09GA) and Aqua (MYD09GA) differ
	product = f" {col.split('/')[-1]}" if str(sensor).lower() == 'modis' else ''
	title = (f"Burn severity (RdNBR, Miller & Thode 2007) {sensor}{product} ({metric}) | before {spec['period'][0]} / "
	         f"{spec['period'][1]}, after {other_start} / {other_end}")
	out = {'index': 'RdNBR', 'classes': classes, 'burned_ha': burned, 'stats': rows, 'scale': res, 'title': title,
	       'csv': None, 'file': None, 'bands': None, 'grid': grid.describe(), 'resolution': res,
	       'native_resolution': native}
	if csv:
		meta = {'index': 'RdNBR', 'sensor': sensor, 'before': f'{start}/{end}', 'after': f'{other_start}/{other_end}',
		        'metric': metric, 'scale_m': res}
		out['csv'] = timeseries.write_csv(classes, csv, meta, RDNBR_COLUMNS)
	if path:
		bands = ['rdnbr', 'severity', 'dnbr', 'nbr_before', 'nbr_after']
		image = ee.Image.cat([rdnbr, severity.toFloat(), dnbr, before, after]).rename(bands)
		download(image, grid, path, tile=tile, workers=workers, progress=progress, bands=bands,
		         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(dict(
		             variables.describe(spec), before=[start, end], after=[other_start, other_end],
		             index='RdNBR = dNBR / sqrt(max(|NBR before|, 0.001))',
		             severity='Miller & Thode 2007 (Table 4)'), default=str)})
		out.update(file=path, bands=bands)
	if outline:
		out.update(_burn_perimeter(rdnbr, regions, res, grid.crs, outline))
	return out


def _perimeter_args(index, path, burned_min, min_ha, sensor, before, after):
	"""What burn_severity needs for the perimeter of the burned area, checked before computing anything: {path,
	index, burned_min, min_ha, sensor, before, after}, or None without PATH (and then neither BURNED_MIN nor MIN_HA)."""
	if not path:
		if burned_min is not None or min_ha is not None:
			raise ValueError('burned_min and min_ha are for the perimeter of the burned area: give also perimeter, the '
			                 f"vector file to write ({', '.join(areas.VECTOR_DRIVERS)})")
		return None
	areas.vector_driver(path)
	min_ha = fire.PERIMETER_MIN_HA if min_ha is None else float(min_ha)
	if min_ha < 0:
		raise ValueError('min_ha, the smallest burned patch and unburned island of the perimeter, cannot be negative')
	return {'path': path, 'index': index, 'burned_min': fire.burned_min(index, burned_min), 'min_ha': min_ha,
	        'sensor': sensor, 'before': '/'.join(map(str, before)), 'after': '/'.join(map(str, after))}


def _burn_perimeter(value, regions, scale, crs, outline):
	"""Write the perimeter of the burned area (fire.perimeter) of the burn index VALUE over each feature of REGIONS,
	with pixels of SCALE metres in CRS, to the vector file of OUTLINE (see _perimeter_args). Returns {'perimeter',
	'perimeter_ha', 'perimeter_patches', 'burned_min', 'min_ha'} for the answer of burn_severity."""
	fc = fire.perimeter(value, outline['burned_min'], regions, scale, crs, outline['min_ha'])
	rows = fire.perimeter_rows(fc.getInfo()['features'])
	same = {k: outline[k] for k in ('index', 'burned_min', 'min_ha', 'sensor', 'before', 'after')}
	areas.save_polygons([dict(r, **same) for r in rows], outline['path'], 'perimeter', fire.PERIMETER_TYPES)
	return {'perimeter': outline['path'], 'perimeter_ha': {r['region']: r['ha'] for r in rows},
	        'perimeter_patches': {r['region']: r['patches'] for r in rows}, 'burned_min': outline['burned_min'],
	        'min_ha': outline['min_ha']}


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


# The data of Earth Engine by their ID in the help of every function that takes them (**source), as the MCP server,
# the command line and R say it in theirs: help(time_series) tells them without reading make_spec
SOURCE_DOC = """

	Instead of VARIABLE and SENSOR, any data of Earth Engine by its ID (see describe_asset and community_datasets):
	COLLECTION (images with dates) or IMAGE (a fixed image, or the mosaic of a collection of tiles: maps and their
	statistics, without dates), with BAND (one, or several with BAND_REDUCER 'sum' or 'mean': each band times
	BAND_SCALE plus BAND_OFFSET, then combined on each pixel; e.g. 12 monthly bands in mm summed into the annual total,
	in mm) and, optionally, BAND_SCALE and BAND_OFFSET (of its stored values), UNIT (of the values after them, in
	UDUNITS: 'mm', 'degC', '1' if dimensionless; that of every band, so of their sum or mean) and, for an image of one
	band, TERRAIN ('slope' or 'aspect' of the band of an image, in degrees: its unit is then degree). Also WHERE and
	EXCLUDE_LANDCOVER (the pixels of the region to keep): see make_spec."""


def _with_source_doc(names):
	"""Add SOURCE_DOC to the help of the functions NAMES of this module that take **source (inspect.signature reads
	that of the function itself, behind _cited)."""
	for name, fn in names.items():
		if inspect.isfunction(fn) and not name.startswith('_') and fn.__module__ == __name__ and fn.__doc__ and \
				any(p.kind is inspect.Parameter.VAR_KEYWORD and p.name == 'source'
				    for p in inspect.signature(fn).parameters.values()):
			fn.__doc__ = fn.__doc__.rstrip() + SOURCE_DOC


_with_source_doc(dict(globals()))
