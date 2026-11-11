"""The manual of MonitorEO (the wiki of its repository) for the assistant: its pages, downloaded from GitHub to
~/MonitorEO/wiki (again when they are older than a day; without connection, the last ones), split in sections, and a
search of the sections that answer a question: BM25 over their words without accents nor endings (the words of the
titles count more, those of the code blocks do not count), with the names of the variables of the catalog for their
codes (NDVI: índice de vegetación...), and the pages for managers counting more than those for programmers. Each page
is in Spanish and in English (ENGLISH): a question gets the pages of its language, and those in Spanish of the pages
that have no English one yet.

    manual.update()                       # download the pages that are missing or old
    manual.search('¿qué es el NDVI?')    # [{page, title, url, text, score, lang}], in Spanish
    manual.search('What is NDVI?')       # in English
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
         'MCP', 'Python', 'Línea-de-comandos', 'R', 'Visor-de-resultados', 'Problemas-frecuentes', 'Publicaciones',
         'Desarrollo')
ENGLISH = {'Home': 'English', 'Primeros-pasos': 'Getting-started', 'Instalación-paso-a-paso': 'Step-by-step-installation',
           'Conceptos': 'Concepts', 'App-de-Earth-Engine': 'Earth-Engine-app', 'QGIS': 'QGIS-plugin', 'MCP': 'MCP-server',
           'Asistente': 'Assistant', 'Python': 'Python-package', 'Línea-de-comandos': 'Command-line', 'R': 'R-package',
           'Visor-de-resultados': 'Results-viewer', 'Problemas-frecuentes': 'Troubleshooting',
           'Publicaciones': 'Publications', 'Desarrollo': 'Development'}  # the English page of each Spanish one
SPANISH = {en: es for es, en in ENGLISH.items()}
LISTS = {'Publicaciones', 'Publications'}  # pages that are lists (of articles): only their items are sections
EXAMPLES = {'es': 'articulo articulos ejemplo ejemplos publicacion publicaciones estudio estudios',
            'en': 'article articles example examples paper papers publication publications study studies'}
EXAMPLES_WEIGHT = 2.5  # the articles of the team, for a question that asks for articles or examples
MAX_AGE = 24 * 3600  # seconds
TITLE_WEIGHT = 3
PAGE_WEIGHT = {'Conceptos': 1.3, 'Asistente': 1.2, 'Home': 1.2, 'Python': 0.8, 'Línea-de-comandos': 0.8, 'R': 0.8,
               'Desarrollo': 0.6, 'Publicaciones': 0.9}  # the articles of the team: examples, after the concepts
PAGE_WEIGHT.update({ENGLISH[k]: w for k, w in PAGE_WEIGHT.items()})
SYNONYMS = {  # words of the questions and the wiki
	'es': {'resolucion': 'pixel', 'pixel': 'resolucion', 'frecuencia': 'fechas dias', 'cuanto': 'fechas dias',
	       'nubes': 'filtros', 'citar': 'cita doi', 'instalar': 'instalacion', 'documento': 'documentos subir tabla',
	       'adjuntar': 'subir documentos', 'excel': 'documentos tabla hoja', 'csv': 'documentos tabla',
	       # the data of Earth Engine outside the catalog (by their ID) and the GEE Community Catalog (not «comunidad»
	       # alone: the questions on the comunidades autónomas would get it)
	       'asset': 'datos earth engine id', 'community': 'catalogo comunidad gee'},
	'en': {'resolution': 'pixel', 'pixel': 'resolution', 'frequency': 'dates days', 'often': 'dates days',
	       'clouds': 'filters', 'cite': 'citation doi', 'install': 'installation', 'document': 'documents upload table',
	       'attach': 'upload documents', 'excel': 'documents table spreadsheet',
	       'spreadsheet': 'documents table', 'csv': 'documents table',
	       'asset': 'data earth engine id', 'dataset': 'data earth engine id', 'community': 'gee community catalog',
	       'awesome': 'gee community catalog'}}
ENDINGS = {
	'es': ('aciones', 'ación', 'acion', 'iones', 'ión', 'ion', 'amiento', 'mente', 'ando', 'iendo', 'ados', 'adas',
	       'idos', 'idas', 'ado', 'ada', 'ido', 'ida', 'ar', 'er', 'ir', 'as', 'es', 'os', 'a', 'e', 'o', 's'),
	'en': ('ational', 'ations', 'ation', 'ments', 'ment', 'ings', 'ing', 'ness', 'ies', 'ied', 'ers', 'ed', 'er', 'ly',
	       'es', 'y', 'e', 's')}
STOP = {
	'es': set("""a al algo como con cual cuales cuando de del desde donde el ella en entre era es esa ese eso esta este
esto estos hay hace la las le lo los mas me mi muy no o os para pero por puede puedo que quien se segun ser si sin
sobre son su sus tambien te tiene tu un una uno unos y ya yo cada""".split()),
	'en': set("""a about also an and any are as at be been but by can could do does each for from get has have how i if
in into is it its me my no not of on or our so some than that the their them then there these they this to us was we
what when where which who why will with would you your""".split())}
COMMON = {  # the words of each language that tell it, without accents (see language; the same in ui/assistant.html)
	'es': set('''al algo como con cual cuales cuando de del desde donde el ella en entre era es esa ese eso esta este esto
estos hay hace la las le lo los mas mi muy para pero por puede puedo que quien se segun ser si sin sobre son su sus
tambien tiene tu un una uno unos y ya yo cada mes ano anos hola gracias vale quiero dame calcula serie mapa tendencia
mensual anual'''.split()),
	'en': set('''about also an and any are as at be been but by can could do does each for from get has have how i if in
into is it its my not of on or our so some than that the their them then there these they this to us was we what when
where which who why will with would you your since until year years month yes hello thanks please want show give series
map trend monthly annual'''.split())}


def update(folder=None, timeout=10):
	"""Download the pages of the wiki (those of its sidebar, and their English pages) that are missing or older than
	MAX_AGE; returns the number of pages in FOLDER. A page that is not there (an English one not written yet) is
	skipped: the search gives the Spanish one."""
	folder = folder or FOLDER
	os.makedirs(folder, exist_ok=True)
	_download('_Sidebar', folder, timeout)  # first: it says which pages there are
	for name in _pages(folder):
		_download(name, folder, timeout)
	return len(_files(folder))


def _download(name, folder, timeout):
	"""Download the page NAME of the wiki to FOLDER if it is missing or older than MAX_AGE (without connection, or if
	it is not in the wiki, the one downloaded before stays, if any)."""
	path = os.path.join(folder, name + '.md')
	if os.path.exists(path) and time.time() - os.path.getmtime(path) < MAX_AGE:
		return
	try:
		with urllib.request.urlopen(RAW + urllib.parse.quote(name) + '.md', timeout=timeout) as r:
			text = r.read().decode('utf-8')
	except (urllib.error.URLError, OSError, UnicodeDecodeError):
		return
	with open(path + '.part', 'w', encoding='utf-8') as f:
		f.write(text)
	os.replace(path + '.part', path)


def sections(folder=None):
	"""The sections of the pages of FOLDER: [{page, name, title, url, text, lang}], one per heading (#, ## or ###);
	lang is that of the page, 'es' or 'en'."""
	out = []
	for name in _files(folder or FOLDER):
		with open(os.path.join(folder or FOLDER, name + '.md'), encoding='utf-8') as f:
			content = f.read()
		lines = content.splitlines()
		lang = 'en' if name in SPANISH else 'es' if name in ENGLISH else language(content)
		page = name.replace('-', ' ')
		title, body, fence = page, [], False
		for line in lines + ['# ']:
			fence = fence != line.lstrip().startswith('```')
			m = None if fence else re.match(r'(#{1,3}) (.*)', line)
			if not m:
				body.append(line)
				continue
			text = _plain('\n'.join(body))
			if text and not (name in LISTS and title == page):  # not the introduction of a list
				out.append({'page': page, 'name': name, 'title': title, 'text': text, 'lang': lang,
				            'url': WEB + name + ('' if title == page else '#' + _anchor(title))})
			title, body = (m.group(2).strip() or page), []
			if m.group(1) == '#':
				page = title = m.group(2).strip() or page
	return out


def search(question, k=3, folder=None, max_chars=1800, lang=None):
	"""The K sections of the manual that answer QUESTION best, each with at most MAX_CHARS of text: those of the
	pages in LANG ('es' or 'en'; default, that of QUESTION) and, of the pages without a page in LANG, those of the
	other language."""
	lang = lang if lang in STOP else language(question)
	secs = in_language(sections(folder), lang)
	query = set(words(question, lang))
	for w, more in SYNONYMS[lang].items():
		if words(w, lang)[0] in query:
			query |= set(words(more, lang))
	for code, name in _variables(lang).items():
		if code in query:
			query |= set(words(name, lang))
	if not secs or not query:
		return []
	examples = bool(query & set(words(EXAMPLES[lang], lang)))
	docs = [words(s['title'] + ' ' + s['page'], s['lang']) * TITLE_WEIGHT +
	        words(re.sub(r'```.*?```', ' ', s['text'], flags=re.S), s['lang']) for s in secs]
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
			weight = PAGE_WEIGHT.get(s['name'], 1) * (EXAMPLES_WEIGHT if examples and s['name'] in LISTS else 1)
			scored.append((score * weight, s))
	scored.sort(key=lambda x: -x[0])
	return [{**s, 'text': s['text'][:max_chars], 'score': round(score, 2)} for score, s in scored[:k]]


def in_language(secs, lang):
	"""The sections SECS of the pages in LANG, and of the pages whose page in LANG is not there (or that have no other
	page)."""
	names = {s['name'] for s in secs}
	return [s for s in secs if s['lang'] == lang or (ENGLISH.get(s['name']) or SPANISH.get(s['name'])) not in names]


def language(text):
	"""'es' or 'en': the language of TEXT, by its words in COMMON, its inverted marks (¿, ¡) and its words with accents
	that are not names (Doñana is in English questions too); English when nothing tells."""
	text = str(text)
	es, en = 2 * bool(re.search('[¿¡]', text)), 0
	for w in re.findall(r'[^\W\d_]+', text):
		lower = w.lower()
		plain = _ascii(lower)
		if plain in COMMON['es']:
			es += 1
		elif plain in COMMON['en']:
			en += 1
		elif w[0] == lower[0] and plain != lower:  # with accents, and not a name
			es += 1
	return 'es' if es > en else 'en'


def words(text, lang='es'):
	"""The words of TEXT that count in a search: in lower case, without accents, stop words nor endings (those of
	LANG, 'es' or 'en')."""
	out = []
	stop, endings = STOP[lang], ENDINGS_ASCII[lang]
	for w in re.findall(r'[a-z0-9]+', _ascii(str(text).lower())):
		if w in stop or len(w) < 2:
			continue
		if not w.isdigit():
			w = next((w[:-len(e)] for e in endings if w.endswith(e) and len(w) - len(e) >= 3), w)
		out.append(w)
	return out


def _ascii(text):
	return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))


ENDINGS_ASCII = {lang: tuple(dict.fromkeys(_ascii(e) for e in endings)) for lang, endings in ENDINGS.items()}
_variable_names = {}


def _variables(lang='es'):
	"""{code in lower case: its name in LANG} of the variables of the catalog (ndvi: Índice de Vegetación...)."""
	if lang not in _variable_names:
		try:
			from . import catalog
			field = 'vname' if lang == 'es' else f'vname_{lang}'
			_variable_names[lang] = {w: e.get(field) or e.get('vname') or '' for e in catalog.variables()
			                         for w in words(e.get('index') or '', lang)}
		except Exception:  # without the catalog, the search goes on
			_variable_names[lang] = {}
	return _variable_names[lang]


def _pages(folder):
	"""The pages of the sidebar of the wiki (downloaded before), or PAGES, and the English page of each one."""
	try:
		with open(os.path.join(folder, '_Sidebar.md'), encoding='utf-8') as f:
			found = tuple(re.findall(r'\]\(([^)#\s:]+)\)', f.read())) or PAGES
	except OSError:
		found = PAGES
	return tuple(dict.fromkeys(found + tuple(ENGLISH[p] for p in found if p in ENGLISH)))


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
	"""The anchor of a heading in GitHub: 'Paquete de Python (también…)' -> 'paquete-de-python-también…', 'How to
	cite' -> 'how-to-cite'."""
	return re.sub(r'[^\w\- ]', '', title.strip().lower()).replace(' ', '-')
