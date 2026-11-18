"""The logs of MonitorEO on this computer and how to send them to the team when something fails.

The assistant writes assistant.log (the calls of the model, their answers and its errors) and, when it runs as an app,
assistant-output.log (its messages and tracebacks); the QGIS plugin writes qgis.log (its tasks and their errors, with
their tracebacks). They are in the folder MonitorEO of the user (MONITOREO_OUTPUT), and each one keeps its newest
MAX_BYTES.

The button "Send the logs" of the assistant and of the QGIS plugin shows the user what collect() gathered, which they
may edit or delete, and send() posts it to the anonymous form of the team (about.FORM) as an error of that tool, with
what the user wrote of it: no sign-in, no name and no e-mail. Before the user sees them, the logs lose what would say
who they are (redact): their home folder, user name and computer name, e-mail addresses, keys and tokens, the ID of the
installation and the project of Earth Engine of the user."""

import contextlib
import datetime as dt
import getpass
import http.client
import json
import os
import platform
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

from . import about

FILES = {'assistant': ['assistant.log', 'assistant-output.log'], 'qgis': ['qgis.log']}  # those of each tool
MAX_BYTES = 2 * 2 ** 20  # a log larger than that keeps its newest half
MAX_CHARS = 40000  # sent at most: an answer of the form fits in a cell of its sheet (50,000 characters)
HEAD = 2000  # of a text longer than MAX_CHARS, its beginning that is kept (the tool, its version, the system)
NO_DESCRIPTION = '(Only the logs: the user wrote nothing.)'
# words that are no user name (as some accounts are called): replaced, they would hide the text of the logs
COMMON = {'user', 'users', 'admin', 'root', 'test', 'guest', 'usuario', 'monitoreo', 'qgis', 'python'}

# what would tell who the user is, and what it is replaced with
_SECRETS = [
	(re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----', re.S), '<private key>'),
	(re.compile(r'\bya29\.[\w.-]+'), '<token>'),  # OAuth access tokens of Google
	(re.compile(r'\b1//[\w.-]{20,}'), '<token>'),  # refresh tokens of Google
	(re.compile(r'\bsk-ant-[\w-]+'), '<key>'),  # keys of Anthropic
	(re.compile(r'\bAIza[\w-]{30,}'), '<key>'),  # keys of Google
	(re.compile(r'(?i)\b(bearer\s+)[\w.~+/-]+=*'), r'\1<token>'),
	(re.compile(r'(?i)(?<![\w-])((?:access_token|refresh_token|id_token|client_secret|api[_-]?key|password|token|'
	            r'secret|x-token)["\']?\s*[:=]\s*["\']?)[^"\'\s,&}]+'), r'\1<hidden>'),
	(re.compile(r'(?i)([?&](?:t|token|key|access_token|code)=)[^&\s"\'<>]+'), r'\1<hidden>'),
	(re.compile(r'[\w.+-]+@(?![\w-]+\.iam\.gserviceaccount\.com\b)[\w-]+(?:\.[\w-]+)+'), '<email>'),
	(re.compile(r'\bmo-[0-9a-f]{16}\b'), 'mo-<installation>'),  # the anonymous ID of this installation
	# the folders of other users (the home folder of this one is ~ already)
	(re.compile(r'(?i)((?:/Users/|/home/|[A-Z]:\\{1,2}Users\\{1,2}))[^/\\\s"\']+'), r'\1<user>'),
]


def folder():
	"""The folder of the logs: that of the results of MonitorEO (MONITOREO_OUTPUT, else ~/MonitorEO)."""
	return os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO')


def path(name, where=None):
	"""The path of the log NAME (e.g. 'qgis.log') in the folder WHERE (default: folder())."""
	return os.path.join(where or folder(), name)


def write(file, entry):
	"""Add ENTRY (a dict) to the log FILE as a JSON line with the time; a log larger than MAX_BYTES keeps its newest
	half first. Writing a log never fails (a full disk, a folder without permission)."""
	with contextlib.suppress(OSError, TypeError, ValueError):
		os.makedirs(os.path.dirname(file) or '.', exist_ok=True)
		if os.path.exists(file) and os.path.getsize(file) > MAX_BYTES:
			kept = _last_bytes(file, MAX_BYTES // 2)
			with open(file, 'w', encoding='utf-8') as f:
				f.write(kept)
		with open(file, 'a', encoding='utf-8') as f:
			f.write(json.dumps({'time': dt.datetime.now().isoformat(timespec='seconds'), **entry}, ensure_ascii=False,
			                   default=str) + '\n')


def _last_bytes(file, size):
	"""The text of the last SIZE bytes of FILE, from its first whole line on."""
	with open(file, 'rb') as f:
		f.seek(0, os.SEEK_END)
		length = f.tell()
		f.seek(max(length - size, 0))
		text = f.read().decode('utf-8', errors='replace')
	if length > size:
		text = text.split('\n', 1)[1] if '\n' in text else ''
	return text


def tail(file, chars):
	"""The last CHARS characters of FILE (or fewer), from a whole line on: its newest lines."""
	text = _last_bytes(file, 4 * chars)  # at most 4 bytes a character in UTF-8
	if len(text) > chars:
		text = text[-chars:]
		text = text.split('\n', 1)[1] if '\n' in text else text
	return text


def redact(text, hide=()):
	"""TEXT without what would tell who the user is: the home folder (~), the user name (<user>) and the name of the
	computer (<computer>), e-mail addresses (<email>; not those of the service accounts of Google Cloud), keys and
	tokens, the ID of the installation and each text of HIDE (e.g. the project of Earth Engine of the user:
	<project>)."""
	home = os.path.expanduser('~')
	if len(home) > 3:
		for h in sorted({home, home.replace('\\', '/'), home.replace('\\', '\\\\')}, key=len, reverse=True):
			text = text.replace(h, '~')
	for pattern, replacement in _SECRETS:  # before the names: an address or a token may have them
		text = pattern.sub(replacement, text)
	for value in hide:  # before the user name, which a project may have
		if value and len(str(value)) >= 3:
			text = text.replace(str(value), '<project>')
	for name, what in ((_user(), '<user>'), (_computer(), '<computer>')):
		if name and len(name) >= 4 and name.lower() not in COMMON:
			text = re.sub(rf'(?i)(?<![\w-]){re.escape(name)}(?![\w-])', what, text)
	return text


def _user():
	try:
		return getpass.getuser()
	except Exception:  # no user name (getpass raises different errors in each system)
		return None


def _computer():
	with contextlib.suppress(OSError):
		return socket.gethostname().split('.')[0]
	return None


def _package(name):
	try:
		from importlib import metadata
		return metadata.version(name)
	except Exception:  # not installed (or bundled without its metadata, as in the QGIS plugin)
		return None


def collect(tool, version=None, extra=None, hide=(), where=None, max_chars=MAX_CHARS):
	"""What "Send the logs" of TOOL ('assistant' or 'qgis', keys of FILES and of about.TOOLS) shows the user and
	sends: the tool and its VERSION, the system, EXTRA ({name: value}, e.g. the version of QGIS) and the newest lines
	of each of its logs in the folder WHERE (default: folder()), in at most MAX_CHARS characters, without what would say
	who the user is (redact, with HIDE)."""
	from . import __version__
	ee = _package('earthengine-api')
	head = [f'Logs of the {about.TOOLS[tool][0]}' + (f' {version}' if version else '') + f' (monitoreo {__version__})',
	        f'Collected: {dt.datetime.now().isoformat(timespec="seconds")}',
	        f'System: {platform.platform()}; Python {platform.python_version()}' +
	        (f'; earthengine-api {ee}' if ee else '')]
	head += [f'{k}: {v}' for k, v in (extra or {}).items()]
	text = '\n'.join(head) + '\n'
	files = [(n, path(n, where)) for n in FILES[tool]]
	files = [(n, p) for n, p in files if os.path.isfile(p) and os.path.getsize(p)]
	if not files:
		return redact(text + f'\n(There is no log of the {about.TOOLS[tool][0]} on this computer yet.)\n', hide)
	left = max_chars - len(text)
	for i, (name, p) in enumerate(sorted(files, key=lambda f: os.path.getsize(f[1]))):  # the smallest first
		share = left // (len(files) - i) - 60
		part = tail(p, max(share, 0))
		section = f'\n== {name} (its newest lines) ==\n{part}'
		text += section
		left -= len(section)
	return redact(text, hide)


def shorten(text, max_chars=MAX_CHARS):
	"""TEXT in at most MAX_CHARS characters: its beginning (HEAD, the tool and the system) and its end (the newest
	lines of the logs)."""
	if len(text) <= max_chars:
		return text
	gap = '\n[…]\n'
	return text[:HEAD] + gap + text[-(max_chars - HEAD - len(gap)):]


def send(text, tool, version=None, description='', timeout=30):
	"""Send the logs TEXT (as the user saw and maybe edited them; at most MAX_CHARS characters, see shorten) to the
	anonymous form of the team, as an error of TOOL (a key of about.TOOLS) of VERSION with DESCRIPTION (what the user
	wrote of it). RuntimeError, with what to do instead, if the form does not take them."""
	text = (text or '').strip()
	if not text:
		raise ValueError('there are no logs to send')
	fields = about.FORM_FIELDS
	data = {fields['what']: about.FORM_ERROR, fields['tool']: about.TOOLS[tool][1],
	        fields['description']: (description or '').strip() or NO_DESCRIPTION, fields['logs']: shorten(text)}
	if version:
		data[fields['version']] = str(version)
	request = urllib.request.Request(about.FORM_RESPONSE, data=urllib.parse.urlencode(data).encode('utf-8'),
	                                 headers={'User-Agent': 'monitoreo',
	                                          'Content-Type': 'application/x-www-form-urlencoded'})
	instead = f'save them and use the anonymous form ({about.FORM}) or a GitHub issue ({about.ISSUES}) instead'
	try:
		# the address of the form, https: the warning of Bandit about file:/ and other schemes does not apply
		with urllib.request.urlopen(request, timeout=timeout) as r:  # nosec B310
			final = r.geturl()
	except urllib.error.HTTPError as e:  # before OSError: an HTTPError is an OSError too
		raise RuntimeError(f'The form did not take the logs (HTTP {e.code}): {instead}') from None
	except (OSError, http.client.HTTPException) as e:  # no network, a timeout
		raise RuntimeError(f'The logs could not be sent ({e}): check the connection, or {instead}') from None
	if 'closedform' in (final or ''):
		raise RuntimeError(f'The form does not take answers now: {instead}')
