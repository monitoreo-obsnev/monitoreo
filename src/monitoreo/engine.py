"""The engine of the language models of the assistant (monitoreo.assistant): Ollama (https://ollama.com).

An Ollama that answers already on this computer (the app of Ollama, at http://localhost:11434) is used as it is. Else
the assistant starts one at http://127.0.0.1:11435 and stops it when it closes: the Ollama installed on this computer
or, if there is none, the one that install() downloads to ~/MonitorEO/ollama from the release OLLAMA of GitHub, without
administrator rights (the file of each system is checked with its SHA-256). The models are those of Ollama
(~/.ollama/models), shared with an Ollama installed later.

To use another version of Ollama, change OLLAMA and the files of ASSETS, with their size and SHA-256 (the digest of
each asset in https://api.github.com/repos/ollama/ollama/releases/tags/<version>).
"""

import hashlib
import os
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
import zipfile

OLLAMA = 'v0.40.14'
ASSETS = {  # (system, machine): (file of the release, bytes, SHA-256)
	('darwin', 'arm64'): ('ollama-darwin.tgz', 186686970,
	                      'f3bf9a528e908da0da5a2b3a4ad3252a369d62186501dc4880261e8d9023bff5'),
	('darwin', 'x86_64'): ('ollama-darwin.tgz', 186686970,
	                       'f3bf9a528e908da0da5a2b3a4ad3252a369d62186501dc4880261e8d9023bff5'),
	('windows', 'amd64'): ('ollama-windows-amd64.zip', 1601954968,
	                       '65d68cade6cf6375f398b518224f8c8a15e062387f38cf477abfc848de7e7e29'),
	('linux', 'x86_64'): ('ollama-linux-amd64.tar.zst', 1525335029,
	                      '993e83d08c3d13d17c55009a3e2664c8a25445e644aec3a68bef5abb6abce67d'),
	('linux', 'aarch64'): ('ollama-linux-arm64.tar.zst', 1581673422,
	                       '39bb333b7b4c0bafcdd7fad35eab1ae9aaf4518ea0f2c731de4376e3a29c94d0'),
}
FOLDER = os.path.join(os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO'), 'ollama')
SYSTEM_URL = 'http://localhost:11434'  # that of an Ollama installed apart
PORT = 11435  # that of the Ollama started by the assistant
CHUNK = 4 * 2 ** 20


def asset():
	"""(file, bytes, SHA-256) of the release of Ollama for this computer, or None."""
	return ASSETS.get((platform.system().lower(), platform.machine().lower()))


def answers(url, timeout=2):
	"""Whether an Ollama answers at URL."""
	try:
		with urllib.request.urlopen(url.rstrip('/') + '/api/version', timeout=timeout) as r:
			return r.status == 200
	except (urllib.error.URLError, OSError, ValueError):
		return False


def system_binary():
	"""The ollama of an Ollama installed on this computer apart, or None."""
	found = shutil.which('ollama')
	candidates = [found, '/Applications/Ollama.app/Contents/Resources/ollama',
	              os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Ollama', 'ollama.exe')]
	return next((c for c in candidates if c and os.path.isfile(c)), None)


class Engine:
	"""The Ollama used by the assistant: url is its address (None if there is none: install()), how 'running' (it was
	running already) or 'started' (by the assistant, which stops it)."""

	def __init__(self, folder=None):
		self.folder = folder or FOLDER
		self.process, self.url, self.how, self.installing = None, None, None, False

	def installed(self):
		"""The ollama installed by install(), of the version OLLAMA or else of another one (installed by an older
		MonitorEO, still used until Ollama is installed again), or None."""
		others = sorted((v for v in (os.listdir(self.folder) if os.path.isdir(self.folder) else [])
		                 if v.startswith('v') and v != OLLAMA and not v.endswith('.tmp')), reverse=True)
		for version in [OLLAMA] + others:
			for root, _, files in os.walk(os.path.join(self.folder, version)):
				name = next((n for n in ('ollama.exe', 'ollama') if n in files), None)
				if name:
					return os.path.join(root, name)
		return None

	def find(self):
		"""Use an Ollama that answers or start one (see the module): returns its address, or None if there is none."""
		if self.process and self.process.poll() is None and answers(self.url):
			return self.url
		own = f'http://127.0.0.1:{PORT}'
		for url in (SYSTEM_URL, own):  # own: one started by an assistant that did not stop it
			if answers(url):
				self.url, self.how = url, 'running'
				return url
		binary = self.installed() or system_binary()
		if not binary:
			self.url = self.how = None
			return None
		self.start(binary)
		return self.url

	def start(self, binary):
		url = f'http://127.0.0.1:{PORT}'
		os.makedirs(self.folder, exist_ok=True)
		env = {**os.environ, 'OLLAMA_HOST': f'127.0.0.1:{PORT}', 'OLLAMA_FLASH_ATTENTION': '1',
		       'OLLAMA_KV_CACHE_TYPE': 'q8_0'}
		with open(os.path.join(self.folder, 'ollama.log'), 'ab') as log:
			self.process = subprocess.Popen([binary, 'serve'], env=env, stdin=subprocess.DEVNULL, stdout=log,
			                                stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
		for _ in range(300):
			if answers(url, timeout=1):
				self.url, self.how = url, 'started'
				return
			if self.process.poll() is not None:
				break
			time.sleep(0.2)
		self.stop()
		raise RuntimeError(f"Ollama does not start: see {os.path.join(self.folder, 'ollama.log')}")

	def stop(self):
		"""Stop the Ollama started by the assistant."""
		p, self.process = self.process, None
		if p and p.poll() is None:
			p.terminate()
			try:
				p.wait(10)
			except subprocess.TimeoutExpired:
				p.kill()
		if self.how == 'started':
			self.url = self.how = None

	def install(self):
		"""Download Ollama to the folder of the engine and start it: yields the progress {status, completed, total}."""
		a = asset()
		if not a:
			raise RuntimeError('there is no Ollama to install on this system: install it from https://ollama.com/download')
		name, size, sha = a
		self.installing = True
		try:
			os.makedirs(self.folder, exist_ok=True)
			part = os.path.join(self.folder, name + '.part')
			url = f'https://github.com/ollama/ollama/releases/download/{OLLAMA}/{name}'
			digest, done = hashlib.sha256(), 0
			with urllib.request.urlopen(url, timeout=60) as r, open(part, 'wb') as f:
				while True:
					chunk = r.read(CHUNK)
					if not chunk:
						break
					f.write(chunk)
					digest.update(chunk)
					done += len(chunk)
					yield {'status': 'Downloading Ollama', 'completed': done, 'total': size}
			if digest.hexdigest() != sha:
				os.remove(part)
				raise RuntimeError('the download of Ollama does not match its SHA-256: it has not been installed')
			yield {'status': 'Installing Ollama'}
			dest = os.path.join(self.folder, OLLAMA)
			tmp = dest + '.tmp'
			shutil.rmtree(tmp, ignore_errors=True)
			os.makedirs(tmp)
			_extract(part, tmp)
			shutil.rmtree(dest, ignore_errors=True)
			os.replace(tmp, dest)
			os.remove(part)
			for old in os.listdir(self.folder):  # other versions
				if old.startswith('v') and old != OLLAMA and os.path.isdir(os.path.join(self.folder, old)):
					shutil.rmtree(os.path.join(self.folder, old), ignore_errors=True)
			binary = self.installed()
			if not binary:
				raise RuntimeError(f'{name} does not have the program ollama')
			if os.name != 'nt':
				os.chmod(binary, 0o755)
			yield {'status': 'Starting Ollama'}
			self.stop()
			self.start(binary)
			yield {'status': 'success'}
		finally:
			self.installing = False


def _extract(path, dest):
	if path.endswith('.zip.part'):
		with zipfile.ZipFile(path) as z:
			z.extractall(dest)
	elif path.endswith('.tgz.part'):
		with tarfile.open(path, 'r:gz') as t:
			try:
				t.extractall(dest, filter='data')  # Python 3.12, and the security updates of 3.9-3.11
			except TypeError:
				t.extractall(dest)
	else:  # .tar.zst: Python reads zstd from 3.14; the tar of the system, before
		try:
			subprocess.run(['tar', '--zstd', '-xf', path, '-C', dest], check=True, capture_output=True)
		except (OSError, subprocess.CalledProcessError) as e:
			raise RuntimeError('installing Ollama needs tar with zstd; or install it from '
			                   'https://ollama.com/download') from e
