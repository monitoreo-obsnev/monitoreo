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
                             "restricted": true/false/null, "quota_reached": true/false,
                             "project_quota_used_hours": ..., "project_quota_limit_hours": ...,
                             "project_quota_percent": ..., "project_quota_time": "...", "updated": ...}
    POST /chat?user=ID  ->  the next message of the language model of the assistant of MonitorEO (see below)
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

Earth Engine counts the monthly quota of the project its own way: the quota counters of Cloud Monitoring (resource
consumer_quota, quota/allocation/usage and quota/limit of QUOTA_METRIC), which also have the computations running or
failed and go down when Earth Engine settles them (it reached the limit on 2026-11-17 while the computations completed
were 45 % of it). This service reads them with the EECUs of the users: the limit of the project is quota/limit
(EECU_LIMIT only without it), project_quota_percent is how much of it Earth Engine has counted, so that the tools
warn before Earth Engine restricts the project, and quota_reached is whether it has counted it all (then restricted,
and nothing left). What is left for the users is still that of their completed computations (the counter is not by
user, and may go down the next day), which alone may refuse them tokens.

Earth Engine may also put the project in restricted mode (it has spent its noncommercial compute quota, which is not
the EECU_LIMIT that this service counts: computations are slow and many fail with too many requests), which Cloud
Monitoring does not say: every QUOTA_TTL seconds this service asks Earth Engine for a number with a token of
monitoreo-public, and its answer has the header x-earth-engine-quota-status (parallelism_restricted=true in restricted
mode). /usage then says restricted (null when it cannot be asked) and, while it is true, that nothing is left
(left_hours and project_left_hours are 0), so that the tools tell their users to use their own Google Cloud project
(it said 42.9 % left of the research EECUs of a user while the project was restricted, 2026-11-19). Tokens are still
given: the shared account still computes, slowly.

/chat is the language model of the assistant of MonitorEO (monitoreo assistant), so that its users need neither a key
nor a model on their computer: the first one of CHAT_MODELS (Claude Sonnet 5.5) and, only while it has no credit (the
API says so; asked again every CREDIT_RETRY seconds), the next one (Gemini 3.8 Flash). The users do not choose the
model: a request may ask for one of CHAT_MODELS only when CHAT_CHOOSE is 1 (to compare them). Gemini is that of the
Gemini API (Google AI Studio, with the paid tier of the project) and Claude that of the API of Anthropic, neither of
which uses the prompts and answers to train its models. Their keys, the only keys of this service, are the secrets
GEMINI_API_KEY and ANTHROPIC_API_KEY (Secret Manager; see deploy.sh) and never leave it. The body is a request of the
OpenAI chat completions API (model, messages, tools, tool_choice, temperature; the rest is dropped) and the answer is in
the same form, with the blocks that the model gave in extra_content, which the assistant sends back as they came (Gemini
its thought signatures, Claude its thinking); an instruction that it only serves MonitorEO goes before the system
message, the effort of reasoning is CHAT_REASONING and the answer has at most CHAT_MAX_TOKENS tokens. Gemini gets the
schemas of the tools in the subset of JSON Schema that it takes (gemini_tools); Claude gets the tools and the
instructions cached (they are the same in every request), the cached conversation, the fallbacks of Anthropic when a
model declines (those that have them) and drop_block for thinking whose conversation changed (claude_params). Each
address may ask CHAT_LIMIT times an hour and each user (the same ID) CHAT_USER_DAY times a day (a message of the
assistant asks from 1 to 8 times): what stops abuse; the spend caps of the projects (AI Studio, the Console of
Anthropic) are what limit the cost. The log has the tokens of each request, never its text.

/chat is also the backup key of GLM (Z.ai), the second model of the assistant (after that of MonitorEO, before a
model on the computer of the user), for its users without a key of GLM of their own or whose key fails: a request that
asks for one of GLM_MODELS (its free models) gets that one or, while it is busy, the next ones, with the key of the
secret ZAI_API_KEY, which never leaves this service either; the limits of each address and user are the same. GLM gets
the messages with only their standard fields and without thinking (glm_request). Z.ai, not Google nor Anthropic, then
gets the conversation.

Environment: PUBLIC_SA (e-mail of monitoreo-public), EE_PROJECT (project of the quota), LIMIT (tokens per address and
hour, default 60), USER_LIMIT (research EECU-hours a month of each user, default 25), EECU_LIMIT (EECU-hours a month of
the tier of EE_PROJECT, default 1000: the Contributor tier), PROJECT_RESERVE (EECU-hours of EECU_LIMIT not given to the
users of the shared account, default 10 % of EECU_LIMIT), REQUIRE_USER (default 1), GEMINI_API_KEY and
ANTHROPIC_API_KEY (a model without its key is skipped), ZAI_API_KEY (GLM), GLM_MODELS (default
glm-4.7-flash,glm-4.5-flash), CHAT_MODELS (comma-separated, in order; default CHAT_MODEL or
claude-sonnet-5-5,gemini-3.8-flash), CHAT_CHOOSE (default 0), CHAT_REASONING (default low), CHAT_MAX_TOKENS (default
8192), CHAT_LIMIT (default 120), CHAT_USER_DAY (default 400) and PORT (given by Cloud Run). It needs the
standard library of Python and, for Claude, the package anthropic (see Dockerfile).
"""

import calendar
import datetime as dt
import json
import os
import re
import threading
import time
import urllib.error
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
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '').strip()
GEMINI = os.environ.get('GEMINI_URL', 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions')
CHAT_MODELS = [m.strip() for m in (os.environ.get('CHAT_MODELS') or os.environ.get('CHAT_MODEL') or
                                   'claude-sonnet-5-5,gemini-3.8-flash').split(',') if m.strip()]
ZAI_API_KEY = os.environ.get('ZAI_API_KEY', '').strip()  # the backup key of GLM of the assistant (see GLM_MODELS)
GLM = os.environ.get('GLM_URL', 'https://api.z.ai/api/paas/v4/chat/completions')
# the free models of GLM (Z.ai) that a request may always ask for (the second model of the assistant, when its user has
# no key of GLM or theirs fails): the one asked for and, if it is busy, the next ones
GLM_MODELS = [m.strip() for m in os.environ.get('GLM_MODELS', 'glm-4.7-flash,glm-4.5-flash').split(',') if m.strip()]
CLAUDE_FALLBACKS = ('claude-opus-5-5', 'claude-sonnet-5-5')  # with fallbacks "default" (Claude Haiku 5.5 has none)
CLAUDE_BETAS = ['thinking-binding-controls-2026-08-01']  # drop_block (see claude_params)
GEMINI_DROP = ('title', 'default', 'additionalProperties', '$schema')  # of the schemas of the tools, for Gemini
CHAT_REASONING = os.environ.get('CHAT_REASONING', 'low')
CHAT_MAX_TOKENS = int(os.environ.get('CHAT_MAX_TOKENS', '8192'))
CHAT_LIMIT = int(os.environ.get('CHAT_LIMIT', '120'))
CHAT_USER_DAY = int(os.environ.get('CHAT_USER_DAY', '400'))
CHAT_CHOOSE = os.environ.get('CHAT_CHOOSE', '0') == '1'  # whether a request may choose its model (to compare them)
CREDIT_RETRY = 3600  # seconds that a model without credit is not asked (the next ones of CHAT_MODELS answer)
CHAT_MAX_BYTES = 2 * 2 ** 20  # of a request: the instructions, the tools and the conversation
CHAT_KEYS = ('model', 'messages', 'tools', 'tool_choice', 'temperature')  # what is taken of a request
SCOPE = ('This service only serves the assistant of MonitorEO (satellite monitoring of ecosystems and protected '
         'areas). Decline any request unrelated to MonitorEO, remote sensing, ecology or the management of natural '
         'areas.\n\n')
USER = re.compile(r'mo-[0-9a-f]{16}')
SCOPES = ['https://www.googleapis.com/auth/earthengine']
LIFETIME = 3600
MARGIN = 600  # a token is given again while it lives at least 10 more minutes
METADATA = 'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token'
IAM = 'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{}:generateAccessToken'
MONITORING = 'https://monitoring.googleapis.com/v3/projects/{}/timeSeries?{}'
EECU_METRIC = 'earthengine.googleapis.com/project/cpu/usage_time'  # "Completed EECU-seconds"
USAGE_TTL = 300  # seconds that the EECU spent are given again before asking Cloud Monitoring
QUOTA_METRIC = 'earthengine.googleapis.com/monthly_eecu_usage_time'  # the monthly quota of EECUs of Earth Engine
QUOTA_USAGE = 'serviceruntime.googleapis.com/quota/allocation/usage'  # what Earth Engine has counted of it
QUOTA_LIMIT = 'serviceruntime.googleapis.com/quota/limit'  # and its limit
QUOTA_REACHED = 0.995  # of the limit: Earth Engine has counted it all (it goes a little over the limit)
QUOTA_HOURS = 50  # of the newest points of the quota counters (the limit is written about once a day)
EE_COMPUTE = 'https://earthengine.googleapis.com/v1/projects/{}/value:compute'
QUOTA_HEADER = 'x-earth-engine-quota-status'  # that of earthengine-api (ee/data.py), in each answer of Earth Engine
QUOTA_RESTRICTED = 'parallelism_restricted=true'  # in QUOTA_HEADER while the project is in restricted mode
QUOTA_TTL = 600  # seconds that the restricted mode of the project is given again before asking Earth Engine
ABOUT = {'service': 'Token broker of MonitorEO (Observatorio de Cambio Global de Sierra Nevada, Universidad de Granada)',
         'token': '/token', 'usage': '/usage', 'chat': '/chat',
         'docs': 'https://github.com/monitoreo-obsnev/monitoreo/wiki'}

_token = {'access_token': None, 'expires_at': 0}
_token_lock = threading.Lock()
_hits = {}  # address -> [hour, requests]
_hits_lock = threading.Lock()
_usage = {'month_start': None, 'time': 0, 'users': {}, 'project_hours': 0.0, 'updated': 0, 'quota': (None, None, None)}
_usage_lock = threading.Lock()
_no_credit = {}  # model -> time until which it is not asked (it said it had no credit)
_credit_lock = threading.Lock()
_quota = {'time': 0, 'restricted': None}  # the last answer of Earth Engine about its restricted mode (see restricted)
_quota_lock = threading.Lock()


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


def quota_seconds(token, project, now=None):
	"""(EECU-seconds counted by Earth Engine for the monthly quota of PROJECT, its limit, UTC time of the count) from
	the quota counters of Cloud Monitoring: the newest point of each in the last QUOTA_HOURS hours of this month; None
	for what they do not have (a project without them, or without a monthly limit: int64 max)."""
	now = now or dt.datetime.now(dt.timezone.utc)
	since = max(now - dt.timedelta(hours=QUOTA_HOURS), month(now)[0])
	newest = {}
	for metric in (QUOTA_LIMIT, QUOTA_USAGE):  # one metric per request of Cloud Monitoring
		params = {'filter': f'metric.type = "{metric}" AND resource.type = "consumer_quota" AND '
		                    f'metric.labels.quota_metric = "{QUOTA_METRIC}"',
		          'interval.startTime': since.strftime('%Y-%m-%dT%H:%M:%SZ'),
		          'interval.endTime': now.strftime('%Y-%m-%dT%H:%M:%SZ')}
		d = _json(MONITORING.format(project, urllib.parse.urlencode(params)), headers={'Authorization': 'Bearer ' + token})
		for series in d.get('timeSeries', []):
			name = series.get('metric', {}).get('labels', {}).get('limit_name', '')
			if name and not name.endswith('PerProject'):  # only the limit of the project
				continue
			for p in series.get('points', []):
				t, v = p['interval']['endTime'], p.get('value', {})
				if t < params['interval.startTime']:  # of the last month
					continue
				if metric not in newest or newest[metric][0] < t:
					newest[metric] = (t, float(v.get('int64Value', v.get('doubleValue', 0))))
		limit = newest.get(QUOTA_LIMIT, (None, None))[1]
		if limit is None or not 0 < limit < 2 ** 62:
			return None, None, None
	time_, used = newest.get(QUOTA_USAGE, (None, None))
	return used, limit, time_


def usage():
	"""The EECU-hours spent this month by each user (workload tag) and by the whole project (asked again every USAGE_TTL
	seconds)."""
	with _usage_lock:
		start, _ = month()
		if _usage['month_start'] != start or time.time() - _usage['time'] > USAGE_TTL:
			own = _json(METADATA, headers={'Metadata-Flavor': 'Google'})['access_token']
			hours = eecu_hours_by_tag(own, PROJECT, start, dt.datetime.now(dt.timezone.utc))
			try:
				quota = quota_seconds(own, PROJECT)
			except Exception as e:  # noqa: BLE001  (then the computations completed, against EECU_LIMIT)
				print(f'quota: {type(e).__name__} {getattr(e, "code", "")}', flush=True)
				quota = (None, None, None)
			_usage.update(month_start=start, time=time.time(), users=hours, project_hours=sum(hours.values()),
			              updated=int(time.time()), quota=quota)
		return _usage


def quota_status(access_token, project):
	"""The header QUOTA_HEADER of the answer of Earth Engine to a number (a constant: nothing to compute) asked for
	PROJECT with ACCESS_TOKEN ('' without it)."""
	body = json.dumps({'expression': {'result': '0', 'values': {'0': {'constantValue': 1}}}}).encode()
	req = urllib.request.Request(EE_COMPUTE.format(project), data=body, headers={
		'Authorization': 'Bearer ' + access_token, 'Content-Type': 'application/json'})
	try:
		with urllib.request.urlopen(req, timeout=20) as r:
			return r.headers.get(QUOTA_HEADER) or ''
	except urllib.error.HTTPError as e:  # too many requests (HTTP 429) also says it
		status = e.headers.get(QUOTA_HEADER) if e.headers else None
		if status is None:
			raise
		return status


def restricted():
	"""Whether Earth Engine has put PROJECT in restricted mode (asked again every QUOTA_TTL seconds with a token of
	monitoreo-public), or None when it cannot be asked."""
	with _quota_lock:
		if time.time() - _quota['time'] > QUOTA_TTL:
			try:
				status = quota_status(token()['access_token'], PROJECT)
				_quota.update(restricted=QUOTA_RESTRICTED in status)
			except Exception as e:  # noqa: BLE001  (never the token in the log)
				print(f'restricted: {type(e).__name__} {getattr(e, "code", "")}', flush=True)
				_quota.update(restricted=None)
			_quota['time'] = time.time()
		return _quota['restricted']


def user_usage(user, quota=True):
	"""What /usage answers for USER (None: only the project); with QUOTA, also whether the project is in restricted
	mode (see restricted), when nothing is left."""
	u, (_, resets) = usage(), month()
	counted, quota_limit, counted_at = u.get('quota') or (None, None, None)
	limit = quota_limit / 3600 if quota_limit else EECU_LIMIT  # the limit of the project, as Earth Engine has it
	reserve = PROJECT_RESERVE * limit / EECU_LIMIT if EECU_LIMIT > 0 else 0.1 * limit
	counted_hours = None if counted is None else counted / 3600
	# for all the users of the shared account: what is left of the computations completed (by those, and not by the
	# counter of Earth Engine, which may go down the next day, the users get no more tokens: see spent)
	project_left = max(0.0, limit - reserve - u['project_hours'])
	reached = counted_hours is not None and counted_hours >= QUOTA_REACHED * limit
	limited = restricted() if quota else None
	if reached and quota:
		limited = True  # Earth Engine has counted the whole quota: restricted mode, also without its header
	if limited:
		project_left = 0.0
	out = {'project': PROJECT, 'project_used_hours': round(u['project_hours'], 3), 'project_limit_hours': limit,
	       'project_reserve_hours': round(reserve, 3), 'project_left_hours': round(project_left, 3),
	       'restricted': limited, 'quota_reached': reached, 'resets': resets.isoformat(), 'updated': u['updated']}
	if counted_hours is not None:
		out.update(project_quota_used_hours=round(counted_hours, 3), project_quota_limit_hours=limit,
		           project_quota_percent=round(100 * counted_hours / limit, 1), project_quota_time=counted_at)
	if user:
		used = u['users'].get(user, 0.0)
		out.update(user=user, used_hours=round(used, 3), limit_hours=USER_LIMIT,
		           left_hours=round(max(0.0, min(USER_LIMIT - used, project_left)), 3))
	return out


def spent(user):
	"""Why USER may not get a token (they have spent their research EECUs of this month), or None. Tokens are given
	when Cloud Monitoring does not answer."""
	try:
		u = user_usage(user, quota=False)  # in restricted mode the shared account still computes, slowly
	except Exception as e:  # noqa: BLE001
		print(f'usage: {type(e).__name__} {getattr(e, "code", "")}', flush=True)
		return None
	if u['used_hours'] >= USER_LIMIT:
		return {'code': 'spent', 'used_hours': u['used_hours'], 'limit_hours': USER_LIMIT, 'resets': u['resets'],
		        'error': f"you have spent your research EECUs of this month ({u['used_hours']:.1f} of {USER_LIMIT:g} "
		                 f"EECU-hours): the shared account of MonitorEO computes for you again on {u['resets']}"}
	limit, reserve = u['project_limit_hours'], u['project_reserve_hours']
	if u['project_used_hours'] >= limit - reserve:  # the computations completed: not the counter of Earth Engine
		return {'code': 'project', 'used_hours': u['used_hours'], 'limit_hours': USER_LIMIT, 'resets': u['resets'],
		        'project_used_hours': u['project_used_hours'], 'project_limit_hours': limit,
		        'error': f"the shared account of MonitorEO has spent the EECUs of this month for its users "
		                 f"({u['project_used_hours']:.0f} of {limit:g} EECU-hours of the project, of which "
		                 f"{reserve:g} are kept for the app of Earth Engine): it computes again on {u['resets']}"}
	return None


def allowed(address, limit=LIMIT, period=3600):
	"""Whether ADDRESS (or another key) has asked at most LIMIT times in this PERIOD of seconds (an hour)."""
	now = int(time.time() // period)
	with _hits_lock:
		if len(_hits) > 100000:
			_hits.clear()
		h = _hits.get(address)
		if not h or h[0] != now:
			h = _hits[address] = [now, 0]
		h[1] += 1
		return h[1] <= limit


class ChatError(Exception):
	"""A request of /chat that is not answered: its STATUS and its answer."""

	def __init__(self, status, code, error):
		super().__init__(error)
		self.status, self.answer = status, {'code': code, 'error': error}


def chat_request(body):
	"""The request of BODY (JSON of the assistant, as the OpenAI chat completions API takes it) that goes on: only what
	it needs, with the length of answer of this service, its scope before the system message and the models that may
	answer it, in order: CHAT_MODELS (the first one, and the next ones only while it has no credit), or, only with
	CHAT_CHOOSE (to compare the models), the one of CHAT_MODELS that the request asks for, or, for a request that asks
	for one of GLM_MODELS (the backup key of GLM of the assistant), that one and then the other ones of GLM_MODELS."""
	try:
		req = json.loads(body)
	except ValueError:
		req = None
	if not isinstance(req, dict) or not isinstance(req.get('messages'), list) or not req['messages']:
		raise ChatError(400, 'request', 'the request has no messages')
	out = {k: req[k] for k in CHAT_KEYS if k in req}
	messages = [dict(m) for m in out['messages'] if isinstance(m, dict)]
	if messages and messages[0].get('role') == 'system' and isinstance(messages[0].get('content'), str):
		messages[0]['content'] = SCOPE + messages[0]['content']
	else:
		messages.insert(0, {'role': 'system', 'content': SCOPE.strip()})
	if out.get('model') in GLM_MODELS:
		models = [out['model']] + [m for m in GLM_MODELS if m != out['model']]
	else:
		models = [out['model']] if CHAT_CHOOSE and out.get('model') in CHAT_MODELS else list(CHAT_MODELS)
	out.update(messages=messages, model=models[0], models=models, max_tokens=CHAT_MAX_TOKENS)
	return out


def has_credit(model):
	"""Whether MODEL may have credit: not if it said it had none less than CREDIT_RETRY seconds ago."""
	with _credit_lock:
		return _no_credit.get(model, 0) <= time.time()


def no_credit(model):
	"""MODEL has no credit: the next models of CHAT_MODELS answer for CREDIT_RETRY seconds; then it is tried again."""
	with _credit_lock:
		_no_credit[model] = time.time() + CREDIT_RETRY
	print(f'chat {model} has no credit: the next model answers for {CREDIT_RETRY} s', flush=True)


def gemini_tools(tools):
	"""TOOLS (in the form of OpenAI) with schemas that Gemini takes (see _gemini_schema); a tool without arguments,
	without parameters."""
	out = []
	for t in tools:
		function = dict(t.get('function') or {})
		params = _gemini_schema(function.get('parameters') or {})
		if params.get('properties'):
			function['parameters'] = params
		else:
			function.pop('parameters', None)
		out.append({**t, 'function': function})
	return out


def _gemini_schema(schema):
	"""SCHEMA (JSON Schema of the arguments of a tool) without what Gemini may not take (GEMINI_DROP), «X or null» as X
	and an object without properties (a region) as its JSON text, which the assistant decodes."""
	if isinstance(schema, list):
		return [_gemini_schema(s) for s in schema]
	if not isinstance(schema, dict):
		return schema
	s = {k: v for k, v in schema.items() if k not in GEMINI_DROP}
	options = s.pop('anyOf', None)
	if options:
		kept = [o for o in options if not (isinstance(o, dict) and o.get('type') == 'null')] or options
		s = {**_gemini_schema(kept[0]), **s}  # the first one, with the description of the argument
	if 'properties' in s:
		s['properties'] = {k: _gemini_schema(v) for k, v in s['properties'].items()}
		if 'required' in s:
			s['required'] = [k for k in s['required'] if k in s['properties']]
	if 'items' in s:
		s['items'] = _gemini_schema(s['items'])
	if s.get('type') == 'object' and not s.get('properties'):
		s = {'type': 'string', 'description': ((s.get('description') or '') + ' A JSON object, written as text.').strip()}
	return s


def _google_only(obj):
	"""OBJ (a message or a call) with only what Gemini gave of its extra_content (another model's blocks dropped)."""
	extra = obj.get('extra_content')
	if isinstance(extra, dict) and 'google' in extra:
		obj['extra_content'] = {'google': extra['google']}
	else:
		obj.pop('extra_content', None)
	return obj


def gemini_request(request):
	"""REQUEST as the API of Gemini compatible with OpenAI takes it."""
	out = {**request, 'stream': False}
	if request.get('tools'):
		out['tools'] = gemini_tools(request['tools'])
	messages = []
	for m in request['messages']:
		m = _google_only(dict(m))
		if m.get('tool_calls'):
			m['tool_calls'] = [_google_only(dict(c)) for c in m['tool_calls']]
		messages.append(m)
	out['messages'] = messages
	if CHAT_REASONING:
		out['reasoning_effort'] = CHAT_REASONING
	return out


def claude_params(request):
	"""REQUEST (in the form of OpenAI) as the Messages API of Anthropic takes it: the system messages in system, each
	call of the model as a tool_use block and each answer of a tool as a tool_result block (those of a turn in one
	message), and the blocks that Claude gave in a turn (its thinking too) back as they came. The tools and the
	instructions are cached with a breakpoint at the end of system, the conversation with the automatic one; with the
	effort of reasoning, the fallbacks of Anthropic when a model declines (CLAUDE_FALLBACKS) and drop_block, so that a
	change of the instructions in a conversation (a layer added) drops its earlier thinking instead of failing.
	Without temperature (the API does not take it)."""
	system, messages = [], []
	for m in request['messages']:
		role, content = m.get('role'), m.get('content')
		text = content if isinstance(content, str) else ''
		if role == 'system':
			system.append(text)
		elif role == 'assistant':
			blocks = ((m.get('extra_content') or {}).get('anthropic') or {}).get('content')
			if not blocks:
				blocks = [{'type': 'text', 'text': text}] if text.strip() else []
				for i, call in enumerate(m.get('tool_calls') or []):
					function = call.get('function') or {}
					args = function.get('arguments')
					if isinstance(args, str):
						try:
							args = json.loads(args or '{}')
						except ValueError:
							args = {}
					blocks.append({'type': 'tool_use', 'id': call.get('id') or f'call_{i}', 'name': function.get('name') or '',
					               'input': args if isinstance(args, dict) else {}})
			if blocks:
				messages.append({'role': 'assistant', 'content': blocks})
		elif role == 'tool':
			result = {'type': 'tool_result', 'tool_use_id': m.get('tool_call_id') or '', 'content': text}
			last = messages[-1] if messages else None
			if last and last['role'] == 'user' and isinstance(last['content'], list) and \
					all(b.get('type') == 'tool_result' for b in last['content']):
				last['content'].append(result)
			else:
				messages.append({'role': 'user', 'content': [result]})
		else:
			messages.append({'role': 'user', 'content': text})
	tools = [{'name': f['name'], 'description': f.get('description') or '',
	          'input_schema': f.get('parameters') or {'type': 'object', 'properties': {}}}
	         for f in ((t.get('function') or {}) for t in request.get('tools') or []) if f.get('name')]
	params = {'model': request['model'], 'max_tokens': request['max_tokens'], 'messages': messages,
	          'system': [{'type': 'text', 'text': '\n\n'.join(system), 'cache_control': {'type': 'ephemeral'}}],
	          'cache_control': {'type': 'ephemeral'},
	          'thinking': {'type': 'adaptive', 'block_binding': {'prefix_mismatch_behavior': 'drop_block'}},
	          'betas': list(CLAUDE_BETAS)}
	if tools:
		params['tools'] = tools
	if CHAT_REASONING:
		params['output_config'] = {'effort': CHAT_REASONING}
	if request['model'] in CLAUDE_FALLBACKS:
		params['betas'].append('server-side-fallback-2026-07-01')
		params['fallbacks'] = 'default'
	return params


def claude_answer(response):
	"""RESPONSE of Claude (a dict, as the API gives it) as an answer of the API of OpenAI: its text, its calls of tools,
	its blocks as they came (in extra_content, to be sent back) and its tokens, also those of the cache."""
	blocks = response.get('content') or []
	if response.get('stop_reason') == 'refusal':  # Claude and its fallbacks declined: nothing to send back
		message = {'role': 'assistant', 'content': 'The language model of MonitorEO declined this request.'}
	else:
		message = {'role': 'assistant',
		           'content': '\n\n'.join(b.get('text') or '' for b in blocks if b.get('type') == 'text').strip()}
		calls = [{'id': b.get('id'), 'type': 'function',
		          'function': {'name': b.get('name'), 'arguments': json.dumps(b.get('input') or {}, ensure_ascii=False)}}
		         for b in blocks if b.get('type') == 'tool_use']
		if calls:
			message['tool_calls'] = calls
		if blocks:
			message['extra_content'] = {'anthropic': {'content': blocks}}
	use = response.get('usage') or {}
	read, write = use.get('cache_read_input_tokens') or 0, use.get('cache_creation_input_tokens') or 0
	return {'model': response.get('model'),
	        'choices': [{'index': 0, 'message': message, 'finish_reason': response.get('stop_reason')}],
	        'usage': {'prompt_tokens': (use.get('input_tokens') or 0) + read + write,
	                  'completion_tokens': use.get('output_tokens') or 0, 'cache_read_tokens': read,
	                  'cache_write_tokens': write},
	        'dropped_thinking': sum(1 for t in response.get('input_transformations') or []
	                                if t.get('type') == 'thinking_dropped')}


_anthropic = None


def _claude_call(params):
	"""The response (a dict) of the Messages API of Anthropic to PARAMS, or ChatError."""
	global _anthropic
	import anthropic
	if _anthropic is None:
		_anthropic = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=180, max_retries=2)
	try:
		return _anthropic.beta.messages.create(**params).to_dict()
	except anthropic.APIStatusError as e:
		if e.status_code == 402 or getattr(e, 'type', None) == 'billing_error' or \
				'credit balance' in str(e.message).lower():  # 402 billing_error (earlier, a 400 about the balance)
			raise ChatError(503, 'credit', 'the language model of MonitorEO has no credit left') from e
		if isinstance(e, anthropic.RateLimitError):
			raise ChatError(503, 'busy', 'the language model of MonitorEO is busy: try again in a minute') from e
		if isinstance(e, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
			raise ChatError(503, 'off', 'the language model of MonitorEO is not available') from e
		if isinstance(e, anthropic.BadRequestError):  # a request that Claude does not take (never the key in it)
			raise ChatError(502, 'model', f'the language model of MonitorEO did not take the request: {e.message}') from e
		raise ChatError(502, 'model', f'the language model of MonitorEO failed ({e.status_code})') from e
	except anthropic.APIConnectionError as e:
		raise ChatError(502, 'model', 'the language model of MonitorEO does not answer now') from e


def claude(request):
	"""The answer (in the form of OpenAI) of Claude to REQUEST, or ChatError."""
	return claude_answer(_claude_call(claude_params(request)))


def gemini(request):
	"""The answer (JSON) of Gemini to REQUEST, or ChatError."""
	req = urllib.request.Request(GEMINI, data=json.dumps(gemini_request(request)).encode(),
	                             headers={'Authorization': 'Bearer ' + GEMINI_API_KEY,
	                                      'Content-Type': 'application/json'})
	try:
		with urllib.request.urlopen(req, timeout=180) as r:
			return json.load(r)
	except urllib.error.HTTPError as e:
		try:
			detail = json.load(e)
			detail = detail[0] if isinstance(detail, list) and detail else detail
			detail = (detail.get('error') or {}).get('message') or ''
		except Exception:  # noqa: BLE001
			detail = ''
		if e.code == 429:
			raise ChatError(503, 'busy', 'the language model of MonitorEO is busy: try again in a minute') from e
		if e.code == 400:  # a request that Gemini does not take (never the key in it)
			raise ChatError(502, 'model', f'the language model of MonitorEO did not take the request: {detail}') from e
		raise ChatError(502, 'model', f'the language model of MonitorEO failed ({e.code})') from e
	except (urllib.error.URLError, OSError, ValueError) as e:
		raise ChatError(502, 'model', 'the language model of MonitorEO does not answer now') from e


def glm_request(request):
	"""REQUEST as the API of GLM (Z.ai, like that of OpenAI) takes it: each message with only its standard fields (not
	the blocks of other models in extra_content, which the assistant sends back), without thinking (the effort of the
	other models)."""
	messages = []
	for m in request['messages']:
		keep = {'role': m.get('role'), 'content': m.get('content') or ''}
		if m.get('tool_call_id'):
			keep['tool_call_id'] = m['tool_call_id']
		if m.get('tool_calls'):
			keep['tool_calls'] = []
			for c in m['tool_calls']:
				function = c.get('function') or {}
				args = function.get('arguments')
				keep['tool_calls'].append({'id': c.get('id'), 'type': 'function', 'function': {
					'name': function.get('name'),
					'arguments': args if isinstance(args, str) else json.dumps(args or {}, ensure_ascii=False)}})
		messages.append(keep)
	out = {k: request[k] for k in ('tools', 'tool_choice', 'temperature') if k in request}
	out.update(model=request['model'], messages=messages, max_tokens=request['max_tokens'],
	           thinking={'type': 'disabled'})
	return out


def glm(request):
	"""The answer (JSON) of GLM to REQUEST, or ChatError (busy: the free models of Z.ai are often overloaded)."""
	req = urllib.request.Request(GLM, data=json.dumps(glm_request(request)).encode(),
	                             headers={'Authorization': 'Bearer ' + ZAI_API_KEY, 'Content-Type': 'application/json',
	                                      'Accept-Language': 'en-US,en'})
	try:
		with urllib.request.urlopen(req, timeout=180) as r:
			return json.load(r)
	except urllib.error.HTTPError as e:
		try:
			detail = (json.load(e).get('error') or {}).get('message') or ''
		except Exception:  # noqa: BLE001
			detail = ''
		if e.code == 429:
			raise ChatError(503, 'busy', 'GLM (Z.ai) is busy: try again in a minute') from e
		if e.code in (401, 403):
			raise ChatError(503, 'off', 'GLM (Z.ai) is not available in MonitorEO') from e
		if e.code == 400:  # a request that GLM does not take (never the key in it)
			raise ChatError(502, 'model', f'GLM (Z.ai) did not take the request: {detail}') from e
		raise ChatError(502, 'model', f'GLM (Z.ai) failed ({e.code})') from e
	except (urllib.error.URLError, OSError, ValueError) as e:
		raise ChatError(502, 'model', 'GLM (Z.ai) does not answer now') from e


def model_key(model):
	"""The key of the API of MODEL ('' if this service has none)."""
	if model.startswith('glm-'):
		return ZAI_API_KEY
	return ANTHROPIC_API_KEY if model.startswith('claude-') else GEMINI_API_KEY


def ask(request):
	"""The answer (in the form of OpenAI) of the model of REQUEST, or ChatError."""
	model = request['model']
	if model.startswith('claude-'):
		return claude(request)
	return glm(request) if model.startswith('glm-') else gemini(request)


def chat(body, address, user):
	"""The answer of /chat to the request BODY of USER from ADDRESS, or ChatError: from the first of its models with a
	key and credit (a model that says it has no credit passes the request to the next one; a model of GLM that is busy
	too)."""
	if not any(model_key(m) for m in CHAT_MODELS + GLM_MODELS):
		raise ChatError(503, 'off', 'the language model of MonitorEO is not available')
	if not user:
		raise ChatError(400, 'user', 'this version of MonitorEO is too old for its language model: update it')
	if not allowed('chat ' + address, CHAT_LIMIT):
		raise ChatError(429, 'address', 'too many requests to the language model from this address: try again in an '
		                                'hour')
	if not allowed('chat ' + user, CHAT_USER_DAY, 86400):
		raise ChatError(429, 'day', 'you have asked the language model of MonitorEO too much today: go on tomorrow '
		                            'or use a model on your computer (Settings of the assistant)')
	request = chat_request(body)
	glm_asked = request['model'] in GLM_MODELS
	models = [m for m in request.pop('models') if model_key(m)]
	if not models and glm_asked:
		raise ChatError(503, 'off', 'GLM (Z.ai) is not available in MonitorEO')
	ready = [m for m in models if has_credit(m)] or models[-1:]  # without credit in any, the last one is tried
	if not ready:
		raise ChatError(503, 'off', 'the language model of MonitorEO is not available')
	for i, model in enumerate(ready):
		request['model'] = model
		try:
			answer = ask(request)
			break
		except ChatError as e:
			passes = ('credit', 'busy') if model.startswith('glm-') else ('credit',)
			if e.answer['code'] not in passes or i == len(ready) - 1:
				raise
			if e.answer['code'] == 'credit':
				no_credit(model)
	use = answer.get('usage') or {}
	print(f"chat {user} model={model} prompt={use.get('prompt_tokens')} answer={use.get('completion_tokens')}"
	      f" cache_read={use.get('cache_read_tokens', '-')} cache_write={use.get('cache_write_tokens', '-')}"
	      f" dropped_thinking={answer.pop('dropped_thinking', '-')}", flush=True)
	return answer


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

	def do_POST(self):
		if self.path.split('?')[0] != '/chat':
			return self.reply(404, {'error': 'not found'})
		try:
			size = int(self.headers.get('Content-Length') or 0)
		except ValueError:
			size = -1
		if not 0 < size <= CHAT_MAX_BYTES:
			self.close_connection = True
			return self.reply(413, {'code': 'request', 'error': 'the request is empty or too big'})
		body = self.rfile.read(size)
		try:
			return self.reply(200, chat(body, self.address(), self.user()))
		except ChatError as e:
			if e.status >= 500:
				self.log_error('chat: %s', e)
			return self.reply(e.status, e.answer)
		except Exception as e:  # noqa: BLE001  (never the key nor the text in the log)
			self.log_error('chat: %s', type(e).__name__)
			return self.reply(502, {'code': 'model', 'error': 'the language model of MonitorEO failed'})


if __name__ == '__main__':
	ThreadingHTTPServer(('', int(os.environ.get('PORT', '8080'))), Handler).serve_forever()
