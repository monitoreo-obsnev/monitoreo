"""The logs of MonitorEO on this computer and how to send them to the team when something fails.

The assistant writes assistant.log (the calls of the model, their answers and its errors) and, when it runs as an app,
assistant-output.log (its messages and tracebacks); the QGIS plugin writes qgis.log (its tasks and their errors, with
their tracebacks). They are in the folder MonitorEO of the user (MONITOREO_OUTPUT), and each one keeps its newest
MAX_BYTES.

The button "Send the logs" of the assistant and of the QGIS plugin shows the user what collect() gathered, which they
may edit or delete, and send() posts it to the anonymous form of the team (about.FORM) as an error of that tool, with
what the user wrote of it: no sign-in, no name and no e-mail. Before the user sees them, the logs lose their noise
(compact: warnings repeated, retries of requests wrapped in many lines) and what would say who they are (redact): their
home folder, user name and computer name, e-mail addresses, keys and tokens, the ID of the installation and the project
of Earth Engine of the user. What collect() gathers fits in a request to the form with a description of the user, so
that what they see is what is sent."""

import collections
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
READ = MAX_BYTES  # of each log, the newest bytes that collect() compacts (and counts its warnings in)
# bytes of the request to the form at most (urlencoded, see size): it took 32,673 bytes and answered HTTP 413 (Payload
# Too Large) to 32,829 and more (measured on 2026-11-19)
BODY_BYTES = 30000
LOGS_BYTES = 24000  # of the logs that collect() gathers: the rest of BODY_BYTES is for the description of the user
DESCRIPTION_BYTES = 4000  # of a long description, kept even if the logs that the user edited are shortened for it
HEAD = 2000  # bytes of the start of a text that shorten() keeps (the tool, its version and the system)
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

# what compact() never drops nor changes: the lines of the errors and of the tracebacks, also those of faulthandler when
# Python crashes (Fatal Python error, Windows fatal exception, Current thread …, File "…"), and the lines indented after
# them (their code, the frames of a crash, the lines of a message wrapped)
_KEEP = re.compile(r'(?i)error|exception|traceback|fatal|current thread|thread 0x|file "|most recent call')
_WARNING = re.compile(r'\S.*:\d+: \w*Warning: ')  # a warning of Python (warnings.warn): where, its category, its text
_RETRY = re.compile(r'\bSleeping \d+(?:\.\d+)? seconds\b')  # a retry of googleapiclient, logged as a WARNING
_RETRY_TEXT = re.compile(r'Sleeping [\d.]+ seconds before retry \d+ of \d+ for (?:request|media upload): '
                         r'(?P<method>[A-Z]+) (?P<uri>.+?), after (?P<after>\S.*)$')
_TIME = re.compile(r'\[([^\]]+)\]\s')  # the time of a line of rich: [11/18/26 02:03:55] WARNING …
_SAFE = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-~ ')  # 1 byte each in the form


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


def size(text):
	"""The bytes of TEXT in the request to the form (urlencoded): 1 for each letter, digit, space or _.-~, and 3 for
	each byte in UTF-8 of any other character (%XX)."""
	return len(urllib.parse.quote_plus(text))


def _bytes(c):
	"""The bytes of the character C in the request to the form (see size)."""
	return 1 if c in _SAFE else 3 * len(c.encode('utf-8'))


def _start(text, most):
	"""The start of TEXT that takes at most MOST bytes in the form."""
	used = 0
	for i, c in enumerate(text):
		used += _bytes(c)
		if used > most:
			return text[:i]
	return text


def _newest(text, most):
	"""The end of TEXT that takes at most MOST bytes in the form, from a whole line on: its newest lines (or the end of
	its last line, if that alone takes more)."""
	used = 0
	for i in range(len(text) - 1, -1, -1):
		used += _bytes(text[i])
		if used > most:
			part = text[i + 1:]
			cut = part.find('\n', 0, len(part) - 1)
			return part if text[i] == '\n' or cut < 0 else part[cut + 1:]
	return text


def compact(text):
	"""TEXT (the lines of a log) without its noise, its newest lines last as they were: each warning of Python
	(warnings.warn, with its line of code) only the last time, with how many times it was there; each retry of a
	request of googleapiclient («Sleeping … seconds before retry …», which rich wraps in many lines) in one line, and
	those in a row in one line, with how many they were, after what and until when; and the lines repeated in a row,
	once with how many times. The lines of the errors and of the tracebacks (_KEEP) never change, but those of the
	assistant (JSON) repeated in a row. Its lines end in \\n, also those of Windows (\\r\\n)."""
	lines, units = text.replace('\r\n', '\n').split('\n'), []  # [kind, its lines, its retry]: 'line', 'keep'…
	last, kept, i = None, False, 0  # the last time that rich wrote, which it writes only when it changes
	while i < len(lines):
		line = lines[i]
		retry = _RETRY.search(line)
		retry = retry if retry and 'WARNING' in line[:retry.start()] else None  # a new message, not of the last one
		kept = bool(_KEEP.search(line)) or (kept and not retry and line[:1] in (' ', '\t', '│', '╭', '╰'))
		own = _TIME.match(line)
		last = own.group(1) if own else last
		if retry and not kept:
			col, j = retry.start(), i + 1
			while j < len(lines) and lines[j].startswith(' ' * col) and lines[j].strip():  # the lines wrapped
				j += 1
			first = re.sub(r'\s+\S+\.py:\d+\s*$', '', line[col:])  # without where it was logged (rich: http.py:177)
			message = ' '.join([first.strip()] + [x.strip() for x in lines[i + 1:j]])
			m = _RETRY_TEXT.match(message)
			if m and not _KEEP.search(message):  # one after an error (ConnectionResetError…) stays as it was
				uri = re.sub(r'\s+', '', m['uri'])
				units.append(['retry', lines[i:j], {
					'time': last if own or line[:1].isspace() else None, 'request': f"{m['method']} {uri}",
					'after': m['after'],
					'text': message[:m.start('uri')] + uri + message[m.end('uri'):]}])
				i = j
				continue
		if not kept and _WARNING.match(line):
			block = lines[i:i + 1]
			if i + 1 < len(lines) and lines[i + 1].startswith('  ') and lines[i + 1].strip() and \
					not _KEEP.search(lines[i + 1]):  # its line of code
				block.append(lines[i + 1])
			units.append(['warning', block, None])
			i += len(block)
			continue
		repeatable = line.strip() and (not kept or (line.startswith('{"') and line.endswith('}')))
		units.append(['line' if repeatable else 'keep', [line], None])
		i += 1
	times, seen = collections.Counter(tuple(u[1]) for u in units if u[0] == 'warning'), set()
	for u in reversed(units):  # each warning, the last time
		if u[0] == 'warning':
			key = tuple(u[1])
			if key in seen:
				u[0] = None
			elif times[key] > 1:
				u[1] = [f'{u[1][0]} ({times[key]} times; only the last one is shown)'] + u[1][1:]
			seen.add(key)
	units, out, i = [u for u in units if u[0]], [], 0
	while i < len(units):
		kind, block = units[i][:2]
		j = i + 1
		while j < len(units) and units[j][0] == kind and kind in ('retry', 'line') and \
				(kind == 'retry' or units[j][1] == block):
			j += 1
		if kind == 'retry':
			out.append(_retries([u[2] for u in units[i:j]]))
		elif kind == 'line':
			out.append(block[0] + (f' (repeated {j - i} times)' if j > i + 1 else ''))
		else:
			out += block
		i = j
	return '\n'.join(out)


def _retries(retries):
	"""The line of RETRIES of googleapiclient in a row (see compact): the text of one, or how many they were, after what
	(the HTTP status or the error) and until when, and their requests."""
	first, last = retries[0], retries[-1]
	start = f"[{first['time']}] WARNING  " if first['time'] else 'WARNING  '
	if len(retries) == 1:
		return start + first['text']
	after = collections.Counter(r['after'] for r in retries)
	requests = list(dict.fromkeys(r['request'] for r in retries))
	return (f'{start}googleapiclient retried requests {len(retries)} times' +
	        (f" until [{last['time']}]" if last['time'] else '') + ': ' +
	        ', '.join(f'{n} after {a}' for a, n in after.items()) + '; ' + '; '.join(requests[:3]) +
	        ('; …' if len(requests) > 3 else ''))


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


def collect(tool, version=None, extra=None, hide=(), where=None, max_bytes=LOGS_BYTES):
	"""What "Send the logs" of TOOL ('assistant' or 'qgis', keys of FILES and of about.TOOLS) shows the user and
	sends: the tool and its VERSION, the system, EXTRA ({name: value}, e.g. the version of QGIS) and the newest lines
	of each of its logs in the folder WHERE (default: folder()) without their noise (compact), in at most MAX_BYTES
	bytes of the request to the form (see size), without what would say who the user is (redact, with HIDE)."""
	from . import __version__
	ee = _package('earthengine-api')
	head = [f'Logs of the {about.TOOLS[tool][0]}' + (f' {version}' if version else '') + f' (monitoreo {__version__})',
	        f'Collected: {dt.datetime.now().isoformat(timespec="seconds")}',
	        f'System: {platform.platform()}; Python {platform.python_version()}' +
	        (f'; earthengine-api {ee}' if ee else '')]
	head += [f'{k}: {v}' for k, v in (extra or {}).items()]
	text = redact('\n'.join(head) + '\n', hide)
	files = [(n, path(n, where)) for n in FILES[tool]]
	files = [(n, p) for n, p in files if os.path.isfile(p) and os.path.getsize(p)]
	if not files:
		return text + f'\n(There is no log of the {about.TOOLS[tool][0]} on this computer yet.)\n'
	parts = []
	for name, p in files:
		part = compact(_last_bytes(p, READ))
		if len(part) > 4 * max_bytes:  # only its end that may fit is redacted, from a whole line on
			part = part[-4 * max_bytes:].split('\n', 1)[-1]
		parts.append((name, redact(part, hide)))  # before it is cut: what fits is what the user sees
	left = max_bytes - size(text)
	for i, (name, part) in enumerate(sorted(parts, key=lambda f: size(f[1]))):  # the smallest first: the rest to others
		title = f'\n== {name} (its newest lines) ==\n'
		section = title + _newest(part, left // (len(parts) - i) - size(title))
		text += section
		left -= size(section)
	return text


def shorten(text, max_bytes=LOGS_BYTES):
	"""TEXT in at most MAX_BYTES bytes of the request to the form (see size): its first lines (the tool, its version and
	the system, up to the first empty line, in at most HEAD bytes) and its newest lines."""
	if size(text) <= max_bytes:
		return text
	head = _start(text, min(HEAD, max_bytes // 4))
	head = head[:head.index('\n\n') + 1] if '\n\n' in head else head[:head.rfind('\n') + 1]
	gap = '[…]\n'
	return head + gap + _newest(text[len(head):], max_bytes - size(head) - size(gap))


def send(text, tool, version=None, description='', timeout=30):
	"""Send the logs TEXT (as the user saw and maybe edited them) to the anonymous form of the team, as an error of
	TOOL (a key of about.TOOLS) of VERSION with DESCRIPTION (what the user wrote of it), in a request of at most
	BODY_BYTES: a long DESCRIPTION keeps its start, and logs longer than what it leaves (shorten) their start and their
	newest lines, with DESCRIPTION_BYTES of the description at least. RuntimeError, with what to do instead, if the form
	does not take them."""
	text = (text or '').strip()
	if not text:
		raise ValueError('there are no logs to send')
	fields = about.FORM_FIELDS
	description = (description or '').strip() or NO_DESCRIPTION
	data = {fields['what']: about.FORM_ERROR, fields['tool']: about.TOOLS[tool][1], fields['description']: '',
	        fields['logs']: ''}
	if version:
		data[fields['version']] = str(version)
	room = BODY_BYTES - len(urllib.parse.urlencode(data))  # for the description and the logs
	text = shorten(text, room - min(size(description), DESCRIPTION_BYTES))
	if size(description) > room - size(text):
		gap = ' […]'
		description = _start(description, room - size(text) - size(gap)) + gap
	data[fields['description']], data[fields['logs']] = description, text
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
