"""Earth Engine in restricted mode: a project that has spent its noncommercial compute quota gets fewer requests at the
same time, many of them answered «too many requests» (HTTP 429) and tried again, so the computations are slow or fail,
and earthengine-api says it only with a Python warning on stderr (ee.data._handle_response_headers, on each answer with
the header x-earth-engine-quota-status parallelism_restricted=true). The services note it (services.watch_quota) and
every tool tells it (services.quota_warning): with the shared account of MonitorEO, to use the user's own Google Cloud
project. Without Earth Engine: the warning comes from a fake answer of Earth Engine."""

import json
import os
import sys
import types
import warnings

import pytest

from monitoreo import services

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# the warning of earthengine-api (ee/data.py, _handle_response_headers), a UserWarning
EE_WARNING = ('Your project has exceeded its noncommercial compute quota and is now in restricted mode. Visit '
              'https://developers.google.com/earth-engine/guides/noncommercial_tiers#restricted_mode to learn more.')


def _answer_of_earth_engine():
	"""What earthengine-api does with each answer of Earth Engine that has the header of restricted mode."""
	warnings.warn(EE_WARNING)


def _printed(clock):
	return [p for p in clock.printed if 'restricted mode' in p[0]]


@pytest.fixture
def clock(monkeypatch):
	"""The time of the services (seconds: t), which the test moves; connected with the shared account, without any
	warning of restricted mode yet; the warnings that reach stderr (printed), under the hook of the services."""
	now = types.SimpleNamespace(t=1_000_000.0, printed=[])
	monkeypatch.setattr(services, 'time', types.SimpleNamespace(time=lambda: now.t))
	monkeypatch.setattr(services, '_restricted', None)
	monkeypatch.setattr(services, '_quota_printed', 0.0)
	monkeypatch.setattr(services, '_quota_given', set())
	monkeypatch.setattr(services, '_project', 'ee-ugr-default-project')
	monkeypatch.setattr(services, '_shared', True)
	monkeypatch.setattr(warnings, 'showwarning', lambda message, category, filename, lineno, file=None, line=None:
	                    now.printed.append((str(message), category)))
	services.watch_quota()  # as at the import of the services and in init
	return now


def test_each_warning_is_noted_and_stderr_gets_it_once_in_a_while(clock):
	assert services.quota_warning() is None  # Earth Engine has not warned
	for _ in range(3):  # each answer of Earth Engine warns (Python would show only the first one of each place)
		_answer_of_earth_engine()
		clock.t += 10
	warnings.warn('another warning')
	assert services._restricted['time'] == clock.t - 10  # every one is noted
	assert _printed(clock) == [(EE_WARNING, UserWarning)]  # but stderr gets it once in QUOTA_EVERY seconds
	assert ('another warning', UserWarning) in clock.printed  # the other warnings go on as they were
	clock.t += services.QUOTA_EVERY
	_answer_of_earth_engine()
	assert len(_printed(clock)) == 2


def test_the_text_for_the_shared_account_and_for_the_users_project(clock, monkeypatch):
	_answer_of_earth_engine()
	text = services.quota_warning()
	assert text.startswith('The shared account of MonitorEO has spent the noncommercial compute quota of its Earth '
	                       'Engine project for now, and Earth Engine has put it in restricted mode: computations are '
	                       'slow')
	assert 'may fail with too many requests' in text and 'own Google Cloud project registered in Earth Engine' in text
	assert '`earthengine authenticate`' in text and 'EE_PROJECT' in text and 'December' not in text
	clock.t += services.QUOTA_TTL + 1
	assert services.quota_warning() is None  # Earth Engine has not warned for QUOTA_TTL seconds: no longer told

	monkeypatch.setattr(services, '_project', 'my-project')
	monkeypatch.setattr(services, '_shared', False)
	assert services.quota_warning() is None  # that of the shared account
	_answer_of_earth_engine()
	text = services.quota_warning()
	assert text.startswith('Your Earth Engine project my-project has exceeded its noncommercial compute quota, and '
	                       'Earth Engine has put it in restricted mode')
	assert services.TIERS_URL + '#restricted_mode' in text and 'shared account' not in text
	assert 'configuration?project=my-project' in text  # to raise its tier
	monkeypatch.setattr(services, '_project', 'other-project')
	assert services.quota_warning() is None  # that of another project
	monkeypatch.setattr(services, '_project', None)
	assert services.quota_warning() is None  # not connected


def test_once_each_time_it_begins(clock):
	_answer_of_earth_engine()
	assert services.quota_warning(once=True) and services.quota_warning(once=True) is None
	assert services.quota_warning()  # without once, while it lasts
	clock.t += 600
	_answer_of_earth_engine()
	assert services.quota_warning(once=True) is None  # the same restricted mode
	clock.t += services.QUOTA_TTL + 1
	_answer_of_earth_engine()  # again, after QUOTA_TTL seconds without warnings
	assert services.quota_warning(once=True) and services.quota_warning(once=True) is None


def test_watched_again_over_another_hook(clock, monkeypatch):
	hooked, n = warnings.showwarning, len(warnings.filters)
	services.watch_quota()
	assert warnings.showwarning is hooked and len(warnings.filters) == n  # once
	below = warnings.showwarning  # another hook over it (as that of the command line), and init watches again
	warnings.showwarning = lambda *a, **k: below(*a, **k)
	services.watch_quota()
	_answer_of_earth_engine()
	_answer_of_earth_engine()
	assert _printed(clock) == [(EE_WARNING, UserWarning)] and services.quota_warning()
	# init watches it, also when it is connected already
	monkeypatch.setattr(warnings, 'showwarning', lambda *a, **k: None)
	monkeypatch.setattr(services, '_shared', False)
	monkeypatch.setattr(services, '_project', 'my-project')
	services.init('my-project', warn=False)
	assert getattr(warnings.showwarning, 'monitoreo_quota', False)


def test_the_mcp_server_tells_it(clock, monkeypatch):
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	monkeypatch.setattr(services, 'eecu_warning', lambda *a, **k: None)
	monkeypatch.setattr(services, 'describe_asset', lambda asset: {'id': asset})
	assert json.loads(mcp_server.describe_asset('X')) == {'id': 'X'}
	_answer_of_earth_engine()
	assert json.loads(mcp_server.describe_asset('X')) == {'id': 'X', 'quota_warning': services.quota_warning()}
	monkeypatch.setattr(services, 'eecu_warning', lambda *a, **k: 'Few left')
	assert json.loads(mcp_server._eecu_warning('{"a": 1}')) == {'a': 1, 'eecu_warning': 'Few left',
	                                                             'quota_warning': services.quota_warning()}
	assert 'quota_warning' not in mcp_server.list_variables(text='NDVI')  # the tools without Earth Engine

	def fails(asset):
		raise RuntimeError('Too many concurrent aggregations')
	monkeypatch.setattr(services, 'describe_asset', fails)  # a computation that fails: its error says it too
	with pytest.raises(mcp_server.ToolError, match=r'^RuntimeError: Too many concurrent aggregations\. The shared '
	                                               r'account of MonitorEO has spent'):
		mcp_server.describe_asset('X')

	def wrong(asset):
		raise ValueError('X is not an asset')
	monkeypatch.setattr(services, 'describe_asset', wrong)  # not that of an argument
	with pytest.raises(mcp_server.ToolError, match=r'^ValueError: X is not an asset$'):
		mcp_server.describe_asset('X')
	assert 'quota_warning' in mcp_server.INSTRUCTIONS and 'quota_warning' in mcp_server.__doc__


def test_the_command_line_tells_it(clock, monkeypatch, capsys):
	from monitoreo import cli
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	monkeypatch.setattr(services, 'find_protected_areas', lambda text, limit: _answer_of_earth_engine() or [])
	cli.main(['parks', 'Sierra'])
	err = capsys.readouterr().err
	# after the commands that compute, with how to use your own project
	assert f'WARNING: {services.quota_warning()} In the command line: --project' in err
	assert 'restricted mode' in cli.__doc__


class _Qt(types.ModuleType):
	"""A module of QGIS or Qt whose names are empty classes: enough to import the plugin without QGIS."""

	def __getattr__(self, name):
		if name.startswith('__'):
			raise AttributeError(name)
		cls = type(name, (), {})
		setattr(self, name, cls)
		return cls


def test_the_qgis_plugin_tells_it(clock, monkeypatch):
	# the text of its message bar (dock.quota_text), with how to use the user's own project in its panel
	for name in ('qgis', 'qgis.core', 'qgis.gui', 'qgis.PyQt', 'qgis.PyQt.QtCore', 'qgis.PyQt.QtGui',
	             'qgis.PyQt.QtWidgets'):
		monkeypatch.setitem(sys.modules, name, _Qt(name))
	monkeypatch.syspath_prepend(os.path.join(ROOT, 'qgis'))
	before = {m: sys.modules.pop(m) for m in [m for m in sys.modules if m.startswith('monitoreo_qgis')]}
	try:
		import monitoreo_qgis.dock as dock
		assert dock.quota_text() is None
		_answer_of_earth_engine()
		assert dock.quota_text(once=True) == services.quota_warning() + dock.OWN_PROJECT
		assert 'write your project in "Project"' in dock.OWN_PROJECT
		assert dock.quota_text(once=True) is None and dock.quota_text()  # once each time it begins (after a task)
		monkeypatch.setattr(services, '_shared', False)
		monkeypatch.setattr(services, '_project', 'my-project')
		_answer_of_earth_engine()
		assert dock.quota_text() == services.quota_warning()  # the user's own project (the error of a task)
		assert dock.quota_text(once=True) is None  # given already
		import monitoreo_qgis.helptexts as helptexts
		assert 'restricted mode' in helptexts.HELP['eecu']
	finally:
		for m in [m for m in sys.modules if m.startswith('monitoreo_qgis')]:
			sys.modules.pop(m)
		sys.modules.update(before)


def test_earth_engine_is_asked_with_the_eecus(clock, monkeypatch):
	"""eecu_usage (when the assistant opens, after each task of QGIS, before each function of R) asks Earth Engine for a
	number (probe_quota), at most once every QUOTA_PROBE seconds, when the account asked is that connected: its answer
	says whether the project is in restricted mode, which the broker of the shared account does not see (it said 42.9 %
	left of the research EECUs of a user while the project was restricted, 2026-11-19)."""
	asked = []

	class Number:
		def __init__(self, n):
			self.n = n

		def getInfo(self):
			asked.append(self.n)
			_answer_of_earth_engine()
			return self.n

	monkeypatch.setattr(services.ee, 'Number', Number)
	monkeypatch.setattr(services, '_quota_probed', {})
	monkeypatch.setattr(services, '_eecu', {})
	monkeypatch.setattr(services, 'user_id', lambda: 'u')
	monkeypatch.setattr(services, '_broker', lambda path, **kw: {'used_hours': 14.28, 'limit_hours': 25.0,
	                                                            'left_hours': 10.72, 'project': 'ee-ugr-default-project'})
	usage = services.eecu_usage(shared=True)
	assert asked == [1] and usage['warning'] is None and usage['left_percent'] == 42.9
	assert usage['quota_warning'].startswith('The shared account of MonitorEO has spent')
	services.eecu_usage(shared=True, refresh=True)
	assert asked == [1]  # not again before QUOTA_PROBE seconds
	clock.t += services.QUOTA_PROBE
	services.eecu_usage(shared=True, refresh=True)
	assert asked == [1, 1]
	monkeypatch.setattr(services, '_project', None)  # not connected: nothing asked to Earth Engine
	clock.t += services.QUOTA_PROBE
	assert services.eecu_usage(shared=True, refresh=True)['quota_warning'] is None and asked == [1, 1]


def test_the_mcp_server_connects_to_tell_it_with_the_eecus(clock, monkeypatch):
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	connected = []
	monkeypatch.setattr(mcp_server, '_ready', lambda: connected.append(True))
	monkeypatch.setattr(services, 'eecu_usage', lambda *a: {'used_percent': 1, 'quota_warning': 'restricted'})
	assert json.loads(mcp_server.eecu_usage())['quota_warning'] == 'restricted' and connected == [True]
	monkeypatch.setattr(services, 'eecu_usage', lambda *a: {'used_percent': 1, 'quota_warning': None})
	assert 'quota_warning' not in json.loads(mcp_server.eecu_usage())

	def spent():
		raise RuntimeError('no token: the research EECUs of this month are spent')
	monkeypatch.setattr(mcp_server, '_ready', spent)  # the usage is told without connecting
	assert json.loads(mcp_server.eecu_usage())['used_percent'] == 1


def test_the_broker_asks_earth_engine(monkeypatch):
	"""The broker of the shared account reads the header of restricted mode in the answer of Earth Engine to a number,
	also in an answer «too many requests» (HTTP 429); without the header, an error is an error (here, a fake Earth
	Engine on this computer)."""
	import importlib.util
	import threading
	from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
	monkeypatch.setenv('PUBLIC_SA', 'public@p.iam.gserviceaccount.com')
	monkeypatch.setenv('EE_PROJECT', 'shared-project')
	spec = importlib.util.spec_from_file_location('broker_main', os.path.join(ROOT, 'broker', 'main.py'))
	broker = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(broker)
	answers, asked = [], []

	class EarthEngine(BaseHTTPRequestHandler):
		def do_POST(self):
			body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
			asked.append((self.path, self.headers['Authorization'], body))
			status, header = answers.pop(0)
			self.send_response(status)
			if header is not None:
				self.send_header(broker.QUOTA_HEADER, header)
			self.send_header('Content-Length', '2')
			self.end_headers()
			self.wfile.write(b'{}')

		def log_message(self, *args):
			pass
	server = ThreadingHTTPServer(('127.0.0.1', 0), EarthEngine)
	threading.Thread(target=server.serve_forever, daemon=True).start()
	monkeypatch.setattr(broker, 'EE_COMPUTE', f'http://127.0.0.1:{server.server_port}/v1/projects/{{}}/value:compute')
	try:
		answers.append((200, 'parallelism_restricted=false'))
		assert broker.quota_status('t', 'shared-project') == 'parallelism_restricted=false'
		assert asked[0][:2] == ('/v1/projects/shared-project/value:compute', 'Bearer t')
		assert asked[0][2]['expression']['values']['0'] == {'constantValue': 1}
		answers.append((429, 'parallelism_restricted=true'))
		assert broker.quota_status('t', 'shared-project') == 'parallelism_restricted=true'
		answers.append((200, None))
		assert broker.quota_status('t', 'shared-project') == ''
		answers.append((403, None))
		with pytest.raises(broker.urllib.error.HTTPError):
			broker.quota_status('t', 'shared-project')
		monkeypatch.setattr(broker, 'token', lambda: {'access_token': 't'})
		answers.append((429, 'parallelism_restricted=true'))
		assert broker.restricted() is True
		assert broker.restricted() is True and len(asked) == 5  # kept QUOTA_TTL seconds
	finally:
		server.shutdown()


def test_the_broker_tells_it_without_connecting(clock, monkeypatch):
	"""The broker says that the project of the shared account is in restricted mode (restricted, with nothing left):
	eecu_usage warns of it without connecting to Earth Engine (when the assistant and QGIS open), with the text of
	the shared account and a full bar."""
	monkeypatch.setattr(services, '_project', None)
	monkeypatch.setattr(services, '_eecu', {})
	monkeypatch.setattr(services, 'user_id', lambda: 'u')
	monkeypatch.setattr(services, '_broker', lambda path, **kw: {
		'used_hours': 14.28, 'limit_hours': 25.0, 'left_hours': 0, 'project_left_hours': 0, 'restricted': True,
		'project': 'ee-ugr-default-project'})
	usage = services.eecu_usage(shared=True)
	assert usage['left_percent'] == 0 and usage['low'] and usage['bar'].startswith('[' + '#' * 30 + ']')
	assert usage['warning'].startswith('The shared account of MonitorEO has spent the noncommercial compute quota')
	assert usage['quota_warning'] == usage['warning']  # the assistant shows it once (test_assistant)
	monkeypatch.setattr(services, '_broker', lambda path, **kw: {
		'used_hours': 14.28, 'limit_hours': 25.0, 'left_hours': 10.72, 'project_left_hours': 500, 'restricted': False,
		'project': 'ee-ugr-default-project'})
	usage = services.eecu_usage(shared=True, refresh=True)
	assert usage['warning'] is None and usage['quota_warning'] is None and usage['left_percent'] == 42.9
