"""Token broker of MonitorEO: it gives the tools of MonitorEO (Python package, R package, QGIS plugin, MCP server and
assistant) a short-lived access token of the shared Earth Engine account of MonitorEO, so that anyone without an Earth
Engine account of their own computes with the project of MonitorEO.

No key of that account exists anywhere. This service runs on Cloud Run as the service account monitoreo-broker, whose
only permission is to create tokens of the service account monitoreo-public. Those tokens last one hour, have only the
scope of Earth Engine and monitoreo-public may only compute in Earth Engine with the quota of the project (it cannot
read Google Drive, Cloud Storage or anything else of the project). See deploy.sh.

    GET /token  ->  {"access_token": "...", "expires_at": <seconds since 1970, UTC>, "project": "..."}
    GET /       ->  what this service is

Environment: PUBLIC_SA (e-mail of monitoreo-public), EE_PROJECT (project of the quota), LIMIT (tokens per address and
hour, default 60) and PORT (given by Cloud Run). It only needs the standard library of Python.
"""

import calendar
import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PUBLIC_SA = os.environ['PUBLIC_SA']
PROJECT = os.environ['EE_PROJECT']
LIMIT = int(os.environ.get('LIMIT', '60'))
SCOPES = ['https://www.googleapis.com/auth/earthengine']
LIFETIME = 3600
MARGIN = 600  # a token is given again while it lives at least 10 more minutes
METADATA = 'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token'
IAM = 'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{}:generateAccessToken'
ABOUT = {'service': 'Token broker of MonitorEO (Observatorio de Cambio Global de Sierra Nevada, Universidad de Granada)',
         'token': '/token', 'docs': 'https://github.com/monitoreo-obsnev/monitoreo/wiki'}

_token = {'access_token': None, 'expires_at': 0}
_token_lock = threading.Lock()
_hits = {}  # address -> [hour, requests]
_hits_lock = threading.Lock()


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


def allowed(address):
	"""Whether ADDRESS has asked for at most LIMIT tokens this hour."""
	hour = int(time.time() // 3600)
	with _hits_lock:
		if len(_hits) > 100000:
			_hits.clear()
		h = _hits.get(address)
		if not h or h[0] != hour:
			h = _hits[address] = [hour, 0]
		h[1] += 1
		return h[1] <= LIMIT


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

	def do_GET(self):
		path = self.path.split('?')[0]
		if path == '/token':
			if not allowed(self.address()):
				return self.reply(429, {'error': 'too many requests from this address: try again in an hour'})
			try:
				return self.reply(200, token())
			except Exception as e:  # noqa: BLE001  (never the token in the log)
				self.log_error('token: %s', type(e).__name__)
				return self.reply(503, {'error': 'the shared account of MonitorEO is not available now'})
		if path == '/':
			return self.reply(200, ABOUT)
		self.reply(404, {'error': 'not found'})


if __name__ == '__main__':
	ThreadingHTTPServer(('', int(os.environ.get('PORT', '8080'))), Handler).serve_forever()
