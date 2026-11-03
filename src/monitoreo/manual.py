"""The manual of MonitorEO (the wiki of its repository) for the assistant: its pages, downloaded from GitHub to
~/MonitorEO/wiki (again when they are older than a day; without connection, the last ones), split in sections, and a
search of the sections that answer a question: BM25 over their words without accents nor endings (the words of the
titles count more, those of the code blocks do not count), with the names of the variables of the catalog for their
codes (NDVI: índice de vegetación...), and the pages for managers counting more than those for programmers.

    manual.update()                       # download the pages that are missing or old
    manual.search('¿qué es el NDVI?')    # [{page, title, url, text, score}]
"""

import math
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

RAW = 'https://raw.githubusercontent.com/wiki/monitoreo-obsnev/monitoreo/'
WEB = 'https://github.com/monitoreo-obsnev/monitoreo/wiki/'
FOLDER = os.path.join(os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO'), 'wiki')
PAGES = ('Home', 'Primeros-pasos', 'Instalación-paso-a-paso', 'Conceptos', 'Asistente', 'App-de-Earth-Engine', 'QGIS',
         'MCP', 'Python', 'Línea-de-comandos', 'R', 'Visor-de-resultados', 'Problemas-frecuentes', 'Desarrollo')
MAX_AGE = 24 * 3600  # seconds
TITLE_WEIGHT = 3
PAGE_WEIGHT = {'Conceptos': 1.3, 'Asistente': 1.2, 'Home': 1.2, 'Python': 0.8, 'Línea-de-comandos': 0.8, 'R': 0.8,
               'Desarrollo': 0.6}
SYNONYMS = {'resolucion': 'pixel', 'pixel': 'resolucion', 'frecuencia': 'fechas dias', 'cuanto': 'fechas dias',
            'nubes': 'filtros', 'citar': 'cita doi', 'instalar': 'instalacion'}  # words of the questions and the wiki
ENDINGS = ('aciones', 'ación', 'acion', 'iones', 'ión', 'ion', 'amiento', 'mente', 'ando', 'iendo', 'ados', 'adas',
           'idos', 'idas', 'ado', 'ada', 'ido', 'ida', 'ar', 'er', 'ir', 'as', 'es', 'os', 'a', 'e', 'o', 's')
STOP = set("""a al algo como con cual cuales cuando de del desde donde el ella en entre era es esa ese eso esta este
esto estos hay hace la las le lo los mas me mi muy no o os para pero por puede puedo que quien se segun ser si sin
sobre son su sus tambien te tiene tu un una uno unos y ya yo cada""".split())


def update(folder=None, timeout=10):
	"""Download the pages of the wiki (those of its sidebar) that are missing or older than MAX_AGE; returns the
	number of pages in FOLDER."""
	folder = folder or FOLDER
	os.makedirs(folder, exist_ok=True)
	for name in ('_Sidebar',) + _pages(folder):
		path = os.path.join(folder, name + '.md')
		if os.path.exists(path) and time.time() - os.path.getmtime(path) < MAX_AGE:
			continue
		try:
			with urllib.request.urlopen(RAW + urllib.parse.quote(name) + '.md', timeout=timeout) as r:
				text = r.read().decode('utf-8')
		except (urllib.error.URLError, OSError, UnicodeDecodeError):
			continue  # the one downloaded before, if any
		with open(path + '.part', 'w', encoding='utf-8') as f:
			f.write(text)
		os.replace(path + '.part', path)
	return len(_files(folder))


def sections(folder=None):
	"""The sections of the pages of FOLDER: [{page, title, url, text}], one per heading (#, ## or ###)."""
	out = []
	for name in _files(folder or FOLDER):
		with open(os.path.join(folder or FOLDER, name + '.md'), encoding='utf-8') as f:
			lines = f.read().splitlines()
		page = name.replace('-', ' ')
		title, body, fence = page, [], False
		for line in lines + ['# ']:
			fence = fence != line.lstrip().startswith('```')
			m = None if fence else re.match(r'(#{1,3}) (.*)', line)
			if not m:
				body.append(line)
				continue
			text = _plain('\n'.join(body))
			if text:
				out.append({'page': page, 'name': name, 'title': title, 'text': text,
				            'url': WEB + name + ('' if title == page else '#' + _anchor(title))})
			title, body = (m.group(2).strip() or page), []
			if m.group(1) == '#':
				page = title = m.group(2).strip() or page
	return out


def search(question, k=3, folder=None, max_chars=1800):
	"""The K sections of the manual that answer QUESTION best, each with at most MAX_CHARS of text."""
	secs = sections(folder)
	query = set(words(question))
	for w, more in SYNONYMS.items():
		if words(w)[0] in query:
			query |= set(words(more))
	for code, name in _variables().items():
		if code in query:
			query |= set(words(name))
	if not secs or not query:
		return []
	docs = [words(s['title'] + ' ' + s['page']) * TITLE_WEIGHT + words(re.sub(r'```.*?```', ' ', s['text'], flags=re.S))
	        for s in secs]
	avg = sum(map(len, docs)) / len(docs)
	df = {w: sum(1 for d in docs if w in d) for w in query}
	scored = []
	for s, d in zip(secs, docs):
		score = 0.0
		for w in query:
			tf = d.count(w)
			if tf:
				idf = math.log(1 + (len(docs) - df[w] + 0.5) / (df[w] + 0.5))
				score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * len(d) / avg))
		if score > 0:
			scored.append((score * PAGE_WEIGHT.get(s['name'], 1), s))
	scored.sort(key=lambda x: -x[0])
	return [{**s, 'text': s['text'][:max_chars], 'score': round(score, 2)} for score, s in scored[:k]]


def words(text):
	"""The words of TEXT that count in a search: in lower case, without accents, stop words nor plurals."""
	out = []
	for w in re.findall(r'[a-z0-9]+', _ascii(str(text).lower())):
		if w in STOP or len(w) < 2:
			continue
		if not w.isdigit():
			w = next((w[:-len(e)] for e in ENDINGS_ASCII if w.endswith(e) and len(w) - len(e) >= 3), w)
		out.append(w)
	return out


def _ascii(text):
	return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))


ENDINGS_ASCII = tuple(dict.fromkeys(_ascii(e) for e in ENDINGS))
_variable_names = None


def _variables():
	"""{code in lower case: its name} of the variables of the catalog (ndvi: Índice de Vegetación...)."""
	global _variable_names
	if _variable_names is None:
		try:
			from . import catalog
			_variable_names = {w: e.get('vname') or '' for e in catalog.variables()
			                   for w in words(e.get('index') or '')}
		except Exception:  # without the catalog, the search goes on
			_variable_names = {}
	return _variable_names


def _pages(folder):
	"""The pages of the sidebar of the wiki (downloaded before), or PAGES."""
	try:
		with open(os.path.join(folder, '_Sidebar.md'), encoding='utf-8') as f:
			found = re.findall(r'\]\(([^)#\s:]+)\)', f.read())
		return tuple(dict.fromkeys(found)) or PAGES
	except OSError:
		return PAGES


def _files(folder):
	if not os.path.isdir(folder):
		return []
	return sorted(n[:-3] for n in os.listdir(folder) if n.endswith('.md') and not n.startswith('_'))


def _plain(text):
	"""TEXT of markdown without images, HTML nor the addresses of its links."""
	text = re.sub(r'<img[^>]*>', '', text)
	text = re.sub(r'<[^>]+>', ' ', text)
	text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
	text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
	return re.sub(r'\n{3,}', '\n\n', text).strip()


def _anchor(title):
	"""The anchor of a heading in GitHub: 'Paquete de Python (también…)' -> 'paquete-de-python-también…'."""
	return re.sub(r'[^\w\- ]', '', title.strip().lower()).replace(' ', '-')
