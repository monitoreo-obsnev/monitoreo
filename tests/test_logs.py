"""The logs of MonitorEO on the computer of the user and the button "Send the logs" of the assistant and of the QGIS
plugin (monitoreo.logs), without Earth Engine, without QGIS and without the internet: what the logs keep, what they
lose before the user sees them (who the user is), what is sent to the anonymous form of the team (faked here), the
routes of the page of the assistant and the log of the plugin. The real form is only reached by hand."""

import asyncio
import json
import os
import re
import sys
import types
import urllib.error
import urllib.parse

import pytest

from monitoreo import __version__, about, assistant, logs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(os.path.dirname(assistant.__file__), 'ui', 'assistant.html')
QT = ('qgis', 'qgis.core', 'qgis.gui', 'qgis.PyQt', 'qgis.PyQt.QtCore', 'qgis.PyQt.QtGui', 'qgis.PyQt.QtWidgets')
# fake secrets, built here so that no scanner of secrets takes this file for a leak
TOKEN = 'ya29.' + 'a0Fake' * 6
REFRESH = '1//' + '0gFake' * 6
CLAUDE_KEY = 'sk-ant-' + 'api03-fake' * 4
GOOGLE_KEY = 'AIza' + 'Fake' * 9


# What the logs lose -------------------------------------------------------------------------------------------------

def test_the_logs_lose_who_the_user_is(monkeypatch):
	home = os.path.expanduser('~')
	monkeypatch.setattr(logs, '_user', lambda: 'jdoe7')
	monkeypatch.setattr(logs, '_computer', lambda: 'Janes-MacBook-Pro')
	text = '\n'.join([
		f'File "{home}/MonitorEO/assistant.py", line 3',
		f'{json.dumps(home + "/data/a.gpkg")}',  # a path in JSON
		'C:\\Users\\Someone\\MonitorEO\\qgis.log and /home/other/x and /Users/another/y',
		'Signed in as jane.doe+ee@example.org (jdoe7 on Janes-MacBook-Pro.local)',
		'monitoreo-public@ee-ugr-default-project.iam.gserviceaccount.com computes',
		f'Authorization: Bearer {TOKEN}', f'refresh {REFRESH}', f'keys {CLAUDE_KEY} {GOOGLE_KEY}',
		'{"access_token": "abc123", "project": "ee-jdoe7-research", "max_tokens": 8192}',
		'http://127.0.0.1:8765/?t=s3cr3t&lang=es and user mo-0123456789abcdef',
		'-----BEGIN PRIVATE KEY-----\nMIIEvQ\n-----END PRIVATE KEY-----'])
	out = logs.redact(text, hide=['ee-jdoe7-research'])
	for gone in (home, 'Someone', 'other', 'another', 'jane.doe', 'jdoe7', 'Janes-MacBook-Pro', TOKEN, REFRESH,
	             CLAUDE_KEY, GOOGLE_KEY, 'abc123', 'ee-jdoe7-research', 's3cr3t', '0123456789abcdef', 'MIIEvQ'):
		assert gone not in out, gone
	assert '~/MonitorEO/assistant.py' in out and '~/data/a.gpkg' in out
	assert 'C:\\Users\\<user>\\MonitorEO' in out and '/home/<user>/x' in out and '/Users/<user>/y' in out
	assert '<email> (<user> on <computer>.local)' in out
	# what helps to find the error stays: the service account, the project of the shared account, the numbers
	assert 'monitoreo-public@ee-ugr-default-project.iam.gserviceaccount.com' in out
	assert '"max_tokens": 8192' in out and '"project": "<project>"' in out and 'lang=es' in out
	assert 'Bearer <token>' in out and 'mo-<installation>' in out and '<private key>' in out


def test_a_common_word_as_user_name_stays(monkeypatch):
	"""An account called user, admin or monitoreo: replaced, it would hide the text of the logs."""
	monkeypatch.setattr(logs, '_computer', lambda: None)
	for name in ('user', 'Admin', 'monitoreo', 'abc'):
		monkeypatch.setattr(logs, '_user', lambda n=name: n)
		assert logs.redact(f'the {name} of monitoreo') == f'the {name} of monitoreo'


# What the logs keep ---------------------------------------------------------------------------------------------------

def test_a_log_keeps_its_newest_lines(tmp_path, monkeypatch):
	monkeypatch.setattr(logs, 'MAX_BYTES', 2000)
	file = tmp_path / 'sub' / 'qgis.log'
	for i in range(200):
		logs.write(str(file), {'task': f'Time series {i}', 'name': 'Doñana'})
	lines = file.read_text(encoding='utf-8').splitlines()
	assert os.path.getsize(file) <= 2000 + 200
	assert json.loads(lines[0])['task'] and json.loads(lines[-1])['task'] == 'Time series 199'  # whole lines
	assert all(re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d', json.loads(x)['time']) for x in lines)


def test_writing_a_log_never_fails(tmp_path):
	(tmp_path / 'a file').write_text('')
	logs.write(str(tmp_path / 'a file' / 'qgis.log'), {'error': 'x'})  # its folder is a file
	logs.write(str(tmp_path / 'qgis.log'), {'error': object()})  # not JSON: written as text
	assert 'object' in (tmp_path / 'qgis.log').read_text()


def test_the_tail_of_a_log_starts_with_a_whole_line(tmp_path):
	file = tmp_path / 'a.log'
	file.write_text(''.join(f'line {i} ñ\n' for i in range(1000)), encoding='utf-8')
	out = logs.tail(str(file), 100)
	assert len(out) <= 100 and out.startswith('line ') and out.endswith('line 999 ñ\n')
	assert logs.tail(str(file), 10 ** 6).startswith('line 0 ')


def test_the_logs_of_each_tool(tmp_path, monkeypatch):
	monkeypatch.setattr(logs, '_user', lambda: None)
	monkeypatch.setattr(logs, '_computer', lambda: None)
	(tmp_path / 'assistant.log').write_text('{"error": "Language model: HTTP 500"}\n' * 3000, encoding='utf-8')
	(tmp_path / 'assistant-output.log').write_text('Traceback (most recent call last):\nKeyError: start\n')
	(tmp_path / 'qgis.log').write_text('{"task": "Map of NDVI", "failed": "EEException: quota"}\n')
	text = logs.collect('assistant', '1.2.3', extra={'Language model': 'that of MonitorEO'}, where=str(tmp_path),
	                    hide=['my-project'])
	assert text.startswith(f'Logs of the Assistant 1.2.3 (monitoreo {__version__})\n')
	assert 'System: ' in text and 'Language model: that of MonitorEO' in text
	assert '== assistant-output.log (its newest lines) ==\nTraceback' in text and 'KeyError: start' in text
	assert '== assistant.log (its newest lines) ==\n{"error"' in text and 'qgis.log' not in text
	assert len(text) <= logs.MAX_CHARS
	qgis = logs.collect('qgis', '0.3.9', where=str(tmp_path))
	assert qgis.startswith('Logs of the QGIS plugin 0.3.9') and 'EEException: quota' in qgis and 'assistant' not in qgis
	assert 'There is no log of the QGIS plugin on this computer yet' in logs.collect('qgis', where=str(tmp_path / 'x'))


# What is sent ---------------------------------------------------------------------------------------------------------

def test_the_form_has_the_question_of_the_logs():
	assert about.FORM_RESPONSE == about.FORM.replace('/viewform', '/formResponse')
	assert all(re.fullmatch(r'entry\.\d+', v) for v in about.FORM_FIELDS.values()), about.FORM_FIELDS
	assert len(set(about.FORM_FIELDS.values())) == len(about.FORM_FIELDS)
	assert about.FORM_ERROR.startswith('Report an error')  # an option of «What would you like to do?»
	assert set(about.LOGS['en']) == set(about.LOGS['es']) == {'menu', 'button', 'help', 'description', 'sent'}


class _Answer:
	def __init__(self, url):
		self.url = url

	def geturl(self):
		return self.url

	def __enter__(self):
		return self

	def __exit__(self, *args):
		return False


@pytest.fixture
def form(monkeypatch):
	"""The anonymous form faked: the requests it gets, and URL (where it answers from) or ERROR (what it raises)."""
	got = types.SimpleNamespace(requests=[], url=about.FORM_RESPONSE, error=None)

	def urlopen(request, timeout=None):
		got.requests.append(request)
		if got.error:
			raise got.error
		return _Answer(got.url)
	monkeypatch.setattr(logs.urllib.request, 'urlopen', urlopen)
	return got


def _fields(request):
	return {k: v[0] for k, v in urllib.parse.parse_qs(request.data.decode('utf-8')).items()}


def test_the_logs_go_to_the_form_as_an_error_of_the_tool(form):
	logs.send('Logs of the QGIS plugin\nerror ñ', 'qgis', '0.3.9 (monitoreo 0.3.1)', 'The map failed ')
	(request,) = form.requests
	assert request.full_url == about.FORM_RESPONSE and request.get_method() == 'POST'
	f, ids = _fields(request), about.FORM_FIELDS
	assert f == {ids['what']: about.FORM_ERROR, ids['tool']: about.TOOLS['qgis'][1],
	             ids['version']: '0.3.9 (monitoreo 0.3.1)', ids['description']: 'The map failed',
	             ids['logs']: 'Logs of the QGIS plugin\nerror ñ'}
	logs.send('x', 'assistant')  # the description is required in the form
	assert _fields(form.requests[-1])[ids['description']] == logs.NO_DESCRIPTION
	assert ids['version'] not in _fields(form.requests[-1])


def test_long_logs_keep_their_start_and_their_newest_lines(form):
	text = 'Logs of the Assistant 1.0\n' + ''.join(f'line {i}\n' for i in range(20000))
	logs.send(text, 'assistant')
	sent = _fields(form.requests[0])[about.FORM_FIELDS['logs']]
	assert len(sent) <= logs.MAX_CHARS and sent.startswith('Logs of the Assistant 1.0\n')
	assert '[…]' in sent and sent.endswith('line 19999')


def test_what_to_do_when_the_form_does_not_take_them(form):
	with pytest.raises(ValueError):
		logs.send('  ', 'qgis')
	assert not form.requests
	form.error = urllib.error.HTTPError(about.FORM_RESPONSE, 400, 'Bad Request', {}, None)
	with pytest.raises(RuntimeError, match=r'HTTP 400.*anonymous form'):
		logs.send('x', 'qgis')
	form.error = urllib.error.URLError('no network')
	with pytest.raises(RuntimeError, match='check the connection'):
		logs.send('x', 'qgis')
	form.error, form.url = None, 'https://docs.google.com/forms/d/e/x/closedform'
	with pytest.raises(RuntimeError, match='does not take answers'):
		logs.send('x', 'qgis')


# The assistant --------------------------------------------------------------------------------------------------------

def _call(app, path, body=None):
	"""The answer of the route PATH of the page (GET, or POST with BODY), as the page asks for it."""
	from starlette.requests import Request
	route = next(r for r in app.routes if r.path == path)
	scope = {'type': 'http', 'method': 'GET' if body is None else 'POST', 'path': path, 'query_string': b'',
	         'headers': [(b'host', b'127.0.0.1:8765'), (b'x-token', b'token'), (b'content-type', b'application/json')]}

	async def receive():
		return {'type': 'http.request', 'body': json.dumps(body or {}).encode(), 'more_body': False}
	answer = asyncio.run(route.endpoint(Request(scope, receive)))
	return answer.status_code, json.loads(answer.body)


def test_the_assistant_shows_and_sends_its_logs(tmp_path, monkeypatch, form):
	monkeypatch.setattr(assistant, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(assistant, 'LOG', str(tmp_path / 'assistant.log'))
	a = assistant.Assistant({**assistant.DEFAULTS, 'project': 'my-own-project', 'provider': 'monitoreo'})
	a.emit({'type': 'error', 'text': 'Map of NDVI has failed: quota of my-own-project'})  # every error to the log
	app = assistant.make_app(a, 'token', 8765)
	status, shown = _call(app, '/api/logs')
	assert status == 200 and shown['text'].startswith(f'Logs of the Assistant {__version__}')
	assert 'Earth Engine: a project of the user' in shown['text'] and 'my-own-project' not in shown['text']
	assert 'Map of NDVI has failed: quota of <project>' in shown['text']
	status, sent = _call(app, '/api/logs/send', {'text': 'edited by the user', 'description': 'It failed'})
	assert status == 200 and sent == {'sent': True, 'text': about.LOGS['en']['sent']}
	f = _fields(form.requests[0])
	assert f[about.FORM_FIELDS['logs']] == 'edited by the user' and f[about.FORM_FIELDS['version']] == __version__
	assert f[about.FORM_FIELDS['tool']] == about.TOOLS['assistant'][1]
	form.error = urllib.error.URLError('no network')  # the page says why, in the window
	status, failed = _call(app, '/api/logs/send', {'text': 'x'})
	assert status == 400 and 'could not be sent' in failed['error']
	assert '/api/logs/send: The logs could not be sent' in (tmp_path / 'assistant.log').read_text()


def test_an_unforeseen_error_of_the_page_goes_to_the_log_with_its_traceback(tmp_path, monkeypatch):
	monkeypatch.setattr(assistant, 'LOG', str(tmp_path / 'assistant.log'))
	a = assistant.Assistant({**assistant.DEFAULTS, 'project': ''})
	monkeypatch.setattr(assistant, 'logs_text', lambda settings: {}['start'])
	status, answer = _call(assistant.make_app(a, 'token', 8765), '/api/logs')
	assert status == 500 and answer == {'error': "KeyError: 'start'"}
	entry = json.loads((tmp_path / 'assistant.log').read_text().splitlines()[-1])
	assert entry['error'] == "/api/logs: KeyError: 'start'" and 'Traceback' in entry['traceback']


def test_the_page_has_the_button_send_the_logs():
	fb = assistant.feedback()
	assert fb['logs'] == about.LOGS['en'] and {k: fb[k] for k in ('button', 'issue', 'form')} == about.FEEDBACK['en']
	with open(PAGE, encoding='utf-8') as f:
		page = f.read()
	assert all(f'id="{i}"' in page for i in ('feedbackLogs', 'logsDialog', 'logsText', 'logsDescription', 'logsSend'))
	assert "api('/api/logs')" in page and "api('/api/logs/send', {text: $('logsText').value" in page
	assert 'notice(e.text, true, true)' in page  # next to each error of the conversation
	app = assistant.make_app(assistant.Assistant({**assistant.DEFAULTS, 'project': ''}), 'token', 8765)
	assert {'/api/logs', '/api/logs/send'} <= {r.path for r in app.routes}


# The QGIS plugin -------------------------------------------------------------------------------------------------------

class _Qt(types.ModuleType):
	"""A module of QGIS or Qt whose names are empty classes: enough to import the plugin without QGIS."""

	def __getattr__(self, name):
		if name.startswith('__'):
			raise AttributeError(name)
		cls = type(name, (), {})
		setattr(self, name, cls)
		return cls


def _forget_plugin():
	return {m: sys.modules.pop(m) for m in [m for m in sys.modules if m.startswith('monitoreo_qgis')]}


@pytest.fixture
def plugin(monkeypatch):
	for name in QT:
		monkeypatch.setitem(sys.modules, name, _Qt(name))
	monkeypatch.syspath_prepend(os.path.join(ROOT, 'qgis'))
	before = _forget_plugin()
	import monitoreo_qgis.dock as dock
	import monitoreo_qgis.sendlogs as sendlogs
	yield types.SimpleNamespace(dock=dock, sendlogs=sendlogs)
	_forget_plugin()
	sys.modules.update(before)


class _Signal:
	def __init__(self):
		self.slots = []

	def connect(self, slot):
		self.slots.append(slot)


class _Button:
	def __init__(self, text=''):
		self.text, self.clicked, self.enabled = text, _Signal(), True

	def setToolTip(self, text):
		self.tip = text

	def setEnabled(self, on):
		self.enabled = on


class _Bar:
	"""The message bar of QGIS: the messages pushed (text, level) and the widgets of the errors."""

	def __init__(self):
		self.messages, self.items = [], []

	def pushMessage(self, title, text, level=None, duration=None):
		self.messages.append(text)

	def createMessage(self, title, text):
		widgets = []
		item = types.SimpleNamespace(text=text, widgets=widgets,
		                             layout=lambda: types.SimpleNamespace(addWidget=widgets.append))
		return item

	def pushWidget(self, item, level=None, duration=None):
		self.items.append(item)


class _Tasks:
	"""QgsTask and the task manager of QGIS: the functions of the tasks added, to run them by hand."""

	def __init__(self):
		self.added = []

	def fromFunction(self, description, run, on_finished=None):
		return types.SimpleNamespace(description=description, run=run, finished=on_finished)

	def taskManager(self):
		return types.SimpleNamespace(addTask=self.added.append)


def _log(tmp_path):
	file = tmp_path / 'qgis.log'
	return [json.loads(x) for x in file.read_text(encoding='utf-8').splitlines()] if file.exists() else []


def test_the_plugin_logs_its_tasks_and_their_errors(plugin, tmp_path, monkeypatch):
	dock, tasks, bar = plugin.dock, _Tasks(), _Bar()
	monkeypatch.setattr(dock, 'QgsTask', tasks)
	monkeypatch.setattr(dock, 'QgsApplication', tasks)
	monkeypatch.setattr(dock, 'QPushButton', _Button)
	monkeypatch.setattr(dock, 'level', lambda name: name)
	monkeypatch.setattr(dock.services, 'init', lambda *args, **kw: None)
	sent = []
	me = types.SimpleNamespace(iface=types.SimpleNamespace(messageBar=lambda: bar), tasks=[], save_settings=lambda: None,
	                           project=types.SimpleNamespace(text=lambda: ''), check_eecu=lambda: None,
	                           send_logs=sent.append)
	me.message = lambda *args, **kw: dock.MonitorEODock.message(me, *args, **kw)

	def work():
		raise KeyError('start')
	dock.MonitorEODock.run_task(me, 'Time series of NDVI', work, lambda r: None)
	task = tasks.added[-1]
	try:
		task.run(task)
	except KeyError as e:
		task.finished(e)
	entries = _log(tmp_path)
	assert entries[0]['task'] == 'Time series of NDVI' and entries[0]['account'] == 'shared'
	assert entries[1]['task'] == 'Time series of NDVI' and entries[1]['failed'] == "KeyError: 'start'"
	assert 'Traceback' in entries[1]['traceback'] and 'in work' in entries[1]['traceback']
	assert entries[2]['error'] == "Time series of NDVI: 'start'"  # what the message bar said
	(item,) = bar.items  # the error, with the button "Send the logs"
	(button,) = item.widgets
	assert button.text == about.LOGS['en']['button'] and button.tip == about.LOGS['en']['menu']
	button.clicked.slots[0]()
	assert sent == ["Time series of NDVI: 'start'"]  # the window starts with the error

	dock.MonitorEODock.run_task(me, 'Map of NDVI', lambda: 1, lambda r: None)  # a task that ends well
	task = tasks.added[-1]
	task.finished(None, task.run(task))
	assert _log(tmp_path)[-1] == {'time': _log(tmp_path)[-1]['time'], 'task': 'Map of NDVI', 'end': 'done'}
	dock.MonitorEODock.message(me, 'Connected', 'Info')  # not an error: neither logged nor with the button
	assert bar.messages == ['Time series of NDVI…', 'Map of NDVI…', 'Connected']
	assert len(bar.items) == 1 and 'Connected' not in json.dumps(_log(tmp_path))


def test_the_window_of_the_plugin_sends_what_the_user_left(plugin, tmp_path, monkeypatch, form):
	sendlogs, tasks = plugin.sendlogs, _Tasks()
	monkeypatch.setattr(sendlogs, 'QgsTask', tasks)
	monkeypatch.setattr(sendlogs, 'QgsApplication', tasks)
	monkeypatch.setattr(logs, '_user', lambda: None)
	sendlogs.write({'task': 'Map of NDVI', 'failed': 'EEException: quota of ee-mine'})
	text = sendlogs.logs_text('0.3.9', ' ee-mine ')
	assert text.startswith(f'Logs of the QGIS plugin 0.3.9 (monitoreo {__version__})') and 'QGIS: ' in text
	assert 'quota of <project>' in text and 'Earth Engine: a project of the user' in text
	done = []
	me = types.SimpleNamespace(plugin='0.3.9', tasks=[], on_sent=done.append, accept=lambda: done.append('closed'),
	                           logs=types.SimpleNamespace(toPlainText=lambda: 'what the user left'),
	                           description=types.SimpleNamespace(toPlainText=lambda: 'The map failed'),
	                           send_button=_Button('Send'), status=types.SimpleNamespace(setText=lambda t: done.append(t)))
	sendlogs.LogsDialog.send(me)
	assert not me.send_button.enabled and done == ['Sending…']
	task = tasks.added[-1]
	task.finished(None, task.run(task))
	assert done[1:] == ['closed', about.LOGS['en']['sent']] and not me.tasks
	f = _fields(form.requests[0])
	assert f[about.FORM_FIELDS['logs']] == 'what the user left' and f[about.FORM_FIELDS['description']] == 'The map failed'
	assert f[about.FORM_FIELDS['version']] == f'0.3.9 (monitoreo {__version__})'
	form.error = urllib.error.URLError('no network')  # the window says why, and Send works again
	sendlogs.LogsDialog.send(me)
	task = tasks.added[-1]
	try:
		task.run(task)
	except RuntimeError as e:
		task.finished(e)
	assert 'could not be sent' in done[-1] and me.send_button.enabled


def test_the_menu_of_the_plugin_has_send_the_logs(plugin):
	with open(os.path.join(ROOT, 'qgis', 'monitoreo_qgis', 'dock.py'), encoding='utf-8') as f:
		source = f.read()
	assert "menu.addAction(about.LOGS['en']['menu'])" in source and 'self.send_logs()' in source
