"""Token broker of MonitorEO: it gives the tools of MonitorEO (Python package, R package, QGIS plugin, MCP server and
assistant) a short-lived access token of the shared Earth Engine account of MonitorEO, so that anyone without an Earth
Engine account of their own computes with the project of MonitorEO.

No key of that account exists anywhere. This service runs on Cloud Run as the service account monitoreo-broker, whose
only permission is to create tokens of the service account monitoreo-public. Those tokens last one hour, have only the
scope of Earth Engine and monitoreo-public may only compute in Earth Engine with the quota of the project (it cannot
read Google Drive, Cloud Storage or anything else of the project). See deploy.sh.

    GET /token?user=ID  ->  {"access_token": "...", "expires_at": <seconds since 1970, UTC>, "project": "..."}
    GET /usage?user=ID  ->  {"user": ID, "used_hours": <EECU-hours>, "limit_hours": <EECU-hours>,
                             "left_hours": <EECU-hours>, "resets": "YYYY-MM-DD", "project": "...",
                             "project_used_hours": ..., "project_limit_hours": ..., "project_reserve_hours": ...,
                             "updated": ...}
    GET /               ->  what this service is

Each user of the shared account has research EECUs (the compute of Earth Engine) for each month: USER_LIMIT
EECU-hours, so that no one spends the quota of the project of everyone. A user is the anonymous ID of an installation
of the tools (mo-<16 hex digits>), which tags their computations in Earth Engine (its workload tag); what each one
spends is the metric "Completed EECU-seconds" of Cloud Monitoring by workload tag since the first day of the month at
midnight Pacific Time (when the quotas of Earth Engine restart), read by monitoreo-broker (role Monitoring Viewer of the
project) every USAGE_TTL seconds. A user who has spent theirs gets no more tokens until the next month (the token they
have lasts at most one more hour), and the tools tell them to use their own account. The users of the shared account
also stop getting tokens when the whole project (they, the app of Earth Engine and the team) has spent its monthly
quota but PROJECT_RESERVE EECU-hours, which are kept for the app of Earth Engine and the team (they are not limited by
user): what a user has left (left_hours) is the least of what is left of their own and of the project before its
reserve. Without an ID (versions of the tools before 0.3.21) there is no token, unless REQUIRE_USER is 0. If Cloud
Monitoring does not answer, tokens are given.

Environment: PUBLIC_SA (e-mail of monitoreo-public), EE_PROJECT (project of the quota), LIMIT (tokens per address and
hour, default 60), USER_LIMIT (research EECU-hours a month of each user, default 25), EECU_LIMIT (EECU-hours a month of
the tier of EE_PROJECT, default 1000: the Contributor tier), PROJECT_RESERVE (EECU-hours of EECU_LIMIT not given to the
users of the shared account, default 10 % of EECU_LIMIT), REQUIRE_USER (default 1) and PORT (given by Cloud Run). It
only needs the standard library of Python.
"""

import calendar
import datetime as dt
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PUBLIC_SA = os.environ['PUBLIC_SA']
PROJECT = os.environ['EE_PROJECT']
LIMIT = int(os.environ.get('LIMIT', '60'))
EECU_LIMIT = float(os.environ.get('EECU_LIMIT', '1000'))
USER_LIMIT = float(os.environ.get('USER_LIMIT', '25'))
PROJECT_RESERVE = float(os.environ.get('PROJECT_RESERVE') or 0.1 * EECU_LIMIT)
REQUIRE_USER = os.environ.get('REQUIRE_USER', '1') != '0'
USER = re.compile(r'mo-[0-9a-f]{16}')
SCOPES = ['https://www.googleapis.com/auth/earthengine']
LIFETIME = 3600
MARGIN = 600  # a token is given again while it lives at least 10 more minutes
METADATA = 'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token'
IAM = 'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{}:generateAccessToken'
MONITORING = 'https://monitoring.googleapis.com/v3/projects/{}/timeSeries?{}'
EECU_METRIC = 'earthengine.googleapis.com/project/cpu/usage_time'  # "Completed EECU-seconds"
USAGE_TTL = 300  # seconds that the EECU spent are given again before asking Cloud Monitoring
ABOUT = {'service': 'Token broker of MonitorEO (Observatorio de Cambio Global de Sierra Nevada, Universidad de Granada)',
         'token': '/token', 'usage': '/usage', 'docs': 'https://github.com/monitoreo-obsnev/monitoreo/wiki'}

_token = {'access_token': None, 'expires_at': 0}
_token_lock = threading.Lock()
_hits = {}  # address -> [hour, requests]
_hits_lock = threading.Lock()
_usage = {'month_start': None, 'time': 0, 'users': {}, 'project_hours': 0.0, 'updated': 0}
_usage_lock = threading.Lock()


def _json(url, data=None, headers=None):
	req = urllib.request.Request(url, data=data, headers=headers or {})
	with urllib.request.urlopen(req, timeout=20) as r:
		return json.load(r)


def _seconds(rfc3339):
	"""Seconds since 1970 of a UTC time such as 2026-11-04T12:00:00Z or 2026-11-04T12:00:00.123456789Z."""
	return calendar.timegm(time.strptime(rfc3339[:19], '%Y-%m-%dT%H:%M:%S'))


def token():
	"""A token of monitoreo-public that lives at least MARGIN more seconds (the same one for everyone until then)."""
	with _token_lock:
		if _token['expires_at'] - time.time() < MARGIN:
			own = _json(METADATA, headers={'Metadata-Flavor': 'Google'})['access_token']
			body = json.dumps({'scope': SCOPES, 'lifetime': f'{LIFETIME}s'}).encode()
			out = _json(IAM.format(PUBLIC_SA), body, {'Authorization': 'Bearer ' + own,
			                                          'Content-Type': 'application/json'})
			_token.update(access_token=out['accessToken'], expires_at=_seconds(out['expireTime']))
		return dict(_token, project=PROJECT)


def month(now=None):
	"""(the first day of this month at midnight Pacific Time, when the quotas of Earth Engine restart, in UTC; the
	first day of the next month)."""
	try:
		from zoneinfo import ZoneInfo
		tz = ZoneInfo('America/Los_Angeles')
	except Exception:  # without the database of time zones: the Pacific standard time
		tz = dt.timezone(dt.timedelta(hours=-8))
	local = (now or dt.datetime.now(dt.timezone.utc)).astimezone(tz)
	start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
	return start.astimezone(dt.timezone.utc), (start.date() + dt.timedelta(days=32)).replace(day=1)


def eecu_hours_by_tag(token, project, start, end):
	"""{workload tag ('' without one): EECU-hours of the computations completed by PROJECT between START and END (UTC
	datetimes)}, from Cloud Monitoring."""
	params = {'filter': f'metric.type = "{EECU_METRIC}"',
	          'interval.startTime': start.strftime('%Y-%m-%dT%H:%M:%SZ'),
	          'interval.endTime': end.strftime('%Y-%m-%dT%H:%M:%SZ'),
	          'aggregation.alignmentPeriod': '86400s', 'aggregation.perSeriesAligner': 'ALIGN_SUM',
	          'aggregation.crossSeriesReducer': 'REDUCE_SUM', 'aggregation.groupByFields': 'metric.label.workload_tag'}
	hours = {}
	while True:
		d = _json(MONITORING.format(project, urllib.parse.urlencode(params)), headers={'Authorization': 'Bearer ' + token})
		for series in d.get('timeSeries', []):
			tag = series.get('metric', {}).get('labels', {}).get('workload_tag', '')
			for p in series.get('points', []):
				v = p.get('value', {})
				hours[tag] = hours.get(tag, 0.0) + float(v.get('doubleValue', v.get('int64Value', 0))) / 3600
		if not d.get('nextPageToken'):
			return hours
		params['pageToken'] = d['nextPageToken']


def usage():
	"""The EECU-hours spent this month by each user (workload tag) and by the whole project (asked again every USAGE_TTL
	seconds)."""
	with _usage_lock:
		start, _ = month()
		if _usage['month_start'] != start or time.time() - _usage['time'] > USAGE_TTL:
			own = _json(METADATA, headers={'Metadata-Flavor': 'Google'})['access_token']
			hours = eecu_hours_by_tag(own, PROJECT, start, dt.datetime.now(dt.timezone.utc))
			_usage.update(month_start=start, time=time.time(), users=hours, project_hours=sum(hours.values()),
			              updated=int(time.time()))
		return _usage


def user_usage(user):
	"""What /usage answers for USER (None: only the project)."""
	u, (_, resets) = usage(), month()
	project_left = max(0.0, EECU_LIMIT - PROJECT_RESERVE - u['project_hours'])  # for all the users of the shared account
	out = {'project': PROJECT, 'project_used_hours': round(u['project_hours'], 3), 'project_limit_hours': EECU_LIMIT,
	       'project_reserve_hours': PROJECT_RESERVE, 'project_left_hours': round(project_left, 3),
	       'resets': resets.isoformat(), 'updated': u['updated']}
	if user:
		used = u['users'].get(user, 0.0)
		out.update(user=user, used_hours=round(used, 3), limit_hours=USER_LIMIT,
		           left_hours=round(max(0.0, min(USER_LIMIT - used, project_left)), 3))
	return out


def spent(user):
	"""Why USER may not get a token (they have spent their research EECUs of this month), or None. Tokens are given
	when Cloud Monitoring does not answer."""
	try:
		u = user_usage(user)
	except Exception as e:  # noqa: BLE001
		print(f'usage: {type(e).__name__} {getattr(e, "code", "")}', flush=True)
		return None
	if u['used_hours'] >= USER_LIMIT:
		return {'code': 'spent', 'used_hours': u['used_hours'], 'limit_hours': USER_LIMIT, 'resets': u['resets'],
		        'error': f"you have spent your research EECUs of this month ({u['used_hours']:.1f} of {USER_LIMIT:g} "
		                 f"EECU-hours): the shared account of MonitorEO computes for you again on {u['resets']}"}
	if u['project_left_hours'] <= 0:
		return {'code': 'project', 'used_hours': u['used_hours'], 'limit_hours': USER_LIMIT, 'resets': u['resets'],
		        'project_used_hours': u['project_used_hours'], 'project_limit_hours': EECU_LIMIT,
		        'error': f"the shared account of MonitorEO has spent the EECUs of this month for its users "
		                 f"({u['project_used_hours']:.0f} of {EECU_LIMIT:g} EECU-hours of the project, of which "
		                 f"{PROJECT_RESERVE:g} are kept for the app of Earth Engine): it computes again on {u['resets']}"}
	return None


def allowed(address, limit=LIMIT):
	"""Whether ADDRESS has asked at most LIMIT times this hour."""
	hour = int(time.time() // 3600)
	with _hits_lock:
		if len(_hits) > 100000:
			_hits.clear()
		h = _hits.get(address)
		if not h or h[0] != hour:
			h = _hits[address] = [hour, 0]
		h[1] += 1
		return h[1] <= limit


class Handler(BaseHTTPRequestHandler):
	server_version = 'monitoreo-broker'
	sys_version = ''

	def address(self):
		# Google adds the address of the client at the end of X-Forwarded-For (what comes before it is the client's).
		return self.headers.get('X-Forwarded-For', self.client_address[0]).split(',')[-1].strip()

	def reply(self, status, obj):
		body = json.dumps(obj).encode()
		self.send_response(status)
		self.send_header('Content-Type', 'application/json')
		self.send_header('Content-Length', str(len(body)))
		self.send_header('Cache-Control', 'no-store')
		self.end_headers()
		self.wfile.write(body)

	def user(self):
		"""The ID of the user of the request (?user=), if it is one."""
		query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
		user = (query.get('user') or [''])[0]
		return user if USER.fullmatch(user) else None

	def do_GET(self):
		path = self.path.split('?')[0]
		if path == '/token':
			if not allowed(self.address()):
				return self.reply(429, {'error': 'too many requests from this address: try again in an hour'})
			user = self.user()
			if not user and REQUIRE_USER:
				return self.reply(400, {'code': 'user', 'error': 'this version of MonitorEO is too old for the shared '
				                                                 'account: update it'})
			why = spent(user) if user else None
			if why:
				return self.reply(403, why)
			try:
				return self.reply(200, token())
			except Exception as e:  # noqa: BLE001  (never the token in the log)
				self.log_error('token: %s', type(e).__name__)
				return self.reply(503, {'error': 'the shared account of MonitorEO is not available now'})
		if path == '/usage':
			if not allowed('usage ' + self.address(), 10 * LIMIT):
				return self.reply(429, {'error': 'too many requests from this address: try again in an hour'})
			try:
				return self.reply(200, user_usage(self.user()))
			except Exception as e:  # noqa: BLE001
				self.log_error('usage: %s %s', type(e).__name__, getattr(e, 'code', ''))
				return self.reply(503, {'error': 'the EECUs spent by the shared account of MonitorEO are not available '
				                                 'now'})
		if path == '/':
			return self.reply(200, ABOUT)
		self.reply(404, {'error': 'not found'})


if __name__ == '__main__':
	ThreadingHTTPServer(('', int(os.environ.get('PORT', '8080'))), Handler).serve_forever()
