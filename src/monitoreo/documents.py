"""The text of the documents that the user gives to the assistant to explain their questions (monitoreo.assistant):
reports that the model reads to replicate their analyses, tables with more information about the study areas, notes...
They are read on this computer, once, when they are uploaded; the model gets their text, never the files.

    PDF                    pypdf (the text of each page, after a line [page N]; a scanned PDF has no text)
    Word (.docx), .odt     their paragraphs and tables (the standard library)
    Excel (.xlsx), .ods    each sheet as a table, after a line [sheet NAME: R rows, C columns] (GDAL, as the layers)
    CSV, TSV               the table, after a line with its rows and columns (any separator: , ; tab |)
    TXT, Markdown          the text

read(path) gives (text, info): the text for the model and what to say of the document ('kind', 'pages', 'sheets',
'rows'...); parts and search cut the text of a long document in parts of a given size, or find the passages with some
words, for the tool read_document of the assistant.
"""

import csv
import io
import os
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

TYPES = {'.pdf': 'PDF', '.docx': 'Word document', '.odt': 'OpenDocument text', '.xlsx': 'Excel workbook',
         '.ods': 'OpenDocument spreadsheet', '.csv': 'CSV table', '.tsv': 'TSV table', '.txt': 'text',
         '.md': 'Markdown text'}
OTHERS = {'.doc': 'save it as .docx or PDF', '.rtf': 'save it as .docx or PDF', '.xls': 'save it as .xlsx or CSV',
          '.ppt': 'save it as PDF', '.pptx': 'save it as PDF', '.odp': 'save it as PDF', '.pages': 'export it as PDF',
          '.numbers': 'export it as .xlsx or CSV', '.key': 'export it as PDF'}
MAX_INSIDE = 40 * 2 ** 20  # bytes of the text of a .docx or .odt once decompressed (more is not a document: a zip bomb)
MAX_SHEETS = 200 * 2 ** 20  # bytes of a .xlsx or .ods once decompressed
LIGATURES = str.maketrans({'\ufb00': 'ff', '\ufb01': 'fi', '\ufb02': 'fl', '\ufb03': 'ffi', '\ufb04': 'ffl',
                           '\ufb05': 'st', '\ufb06': 'st'})  # those of the PDFs made with LaTeX, as their letters
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ODF = {'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0', 'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0'}


def supported(filename):
	"""Whether FILENAME has the extension of a document that can be read."""
	return os.path.splitext(str(filename))[1].lower() in TYPES


def check_type(filename):
	"""Error with what to do if FILENAME is not a document that can be read."""
	ext = os.path.splitext(str(filename))[1].lower()
	if ext in TYPES:
		return
	if ext in OTHERS:
		raise ValueError(f'{ext} files cannot be read: {OTHERS[ext]}')
	raise ValueError('format not supported: use a PDF, a Word (.docx) or OpenDocument (.odt) text, an Excel (.xlsx) or '
	                 'OpenDocument (.ods) spreadsheet, a CSV or TSV table, or a text (.txt, .md)')


def decode(data):
	"""The text of the bytes DATA of a text file: UTF-8 (with or without its mark, also with a stray byte now and
	then) or UTF-16 (with its mark), else Windows-1252 (that of the CSVs of Excel in Spanish, and of Latin-1), else
	the encoding that charset_normalizer finds (the few bytes that Windows-1252 does not have)."""
	if data.startswith((b'\xff\xfe', b'\xfe\xff')):
		return data.decode('utf-16', errors='replace')
	try:
		return data.decode('utf-8-sig')
	except UnicodeDecodeError:
		pass
	text = data.decode('utf-8-sig', errors='replace')
	bad, good = text.count('\ufffd'), len(re.findall(r'[^\x00-\x7f\ufffd]', text))
	if good > bad:  # UTF-8 with a stray byte (e.g. a € of Windows pasted in): its letters are those of UTF-8
		return text
	try:
		return data.decode('cp1252')
	except UnicodeDecodeError:
		pass
	try:
		import charset_normalizer
		best = charset_normalizer.from_bytes(data).best()
		if best is not None:
			return str(best)
	except ImportError:
		pass
	return data.decode('cp1252', errors='replace')


def _clean(text):
	"""TEXT without the blanks at the end of its lines, without more than one empty line in a row, without the
	ligatures of the PDFs (the fi of LaTeX is fi) and without halves of characters (surrogates) that cannot be
	written."""
	text = str(text).encode('utf-16-le', 'surrogatepass').decode('utf-16-le', 'replace').translate(LIGATURES)
	lines = [line.rstrip(' \t\u00a0') for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n')]
	return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def _pdf(path):
	try:
		import pypdf
	except ImportError as e:
		raise ValueError('reading PDFs needs the package pypdf: close the assistant and open it again (it updates '
		                 'itself), or install it with `pip install pypdf`') from e
	try:
		reader = pypdf.PdfReader(path)
		if reader.is_encrypted and not reader.decrypt(''):
			raise ValueError('the PDF has a password: save it without one')
		pages = []
		for i, page in enumerate(reader.pages, 1):
			pages.append(f'[page {i}]\n{_clean(page.extract_text() or "")}')
	except ValueError:
		raise
	except Exception as e:
		raise ValueError(f'the PDF cannot be read ({type(e).__name__}: {e})') from e
	words = sum(len(re.findall(r'\w+', p)) - 2 for p in pages)
	if words < 5 * max(1, len(pages)) and words < 50:
		raise ValueError('the PDF has no text (a scanned document?): save it as PDF with text (OCR) or as a text')
	return '\n\n'.join(pages), {'pages': len(pages)}


def _zip_xml(path, member):
	try:
		with zipfile.ZipFile(path) as z:
			info = z.getinfo(member)
			if info.file_size > MAX_INSIDE:
				raise ValueError('the document is too big once decompressed')
			return ET.fromstring(z.read(member))
	except (KeyError, zipfile.BadZipFile, ET.ParseError) as e:
		raise ValueError(f'the document cannot be read ({type(e).__name__}): is it damaged?') from e


def _docx(path):
	body = _zip_xml(path, 'word/document.xml').find(f'{W}body')
	out = []

	def paragraph(p):
		text = ''
		for node in p.iter():
			if node.tag == f'{W}t':
				text += node.text or ''
			elif node.tag == f'{W}tab':
				text += '\t'
			elif node.tag in (f'{W}br', f'{W}cr'):
				text += '\n'
		return text

	def blocks(node):  # the paragraphs and tables, also inside content controls (w:sdt) and w:customXml
		for block in node:
			if block.tag == f'{W}p':
				out.append(paragraph(block))
			elif block.tag == f'{W}tbl':
				for row in block.iter(f'{W}tr'):
					cells = [' '.join(paragraph(p) for p in cell.iter(f'{W}p')).strip() for cell in row.iter(f'{W}tc')]
					out.append(' | '.join(cells))
				out.append('')
			elif block.tag not in (f'{W}sdtPr', f'{W}sdtEndPr', f'{W}sectPr', f'{W}del', f'{W}moveFrom'):
				blocks(block)

	blocks(body if body is not None else [])
	return _clean('\n'.join(out)), {}


def _odt(path):
	root = _zip_xml(path, 'content.xml')
	t, tb = f"{{{ODF['text']}}}", f"{{{ODF['table']}}}"
	office = '{urn:oasis:names:tc:opendocument:xmlns:office:1.0}'
	skip = (f'{t}tracked-changes', f'{office}annotation', f'{office}annotation-end')  # deleted text, comments
	out = []

	def text_of(node):
		parts = [node.text or '']
		for child in node:
			if child.tag in skip:
				pass
			elif child.tag == f'{t}tab':
				parts.append('\t')
			elif child.tag == f'{t}line-break':
				parts.append('\n')
			elif child.tag == f'{t}s':
				parts.append(' ' * int(child.get(f'{t}c') or 1))
			else:
				parts.append(text_of(child))
			parts.append(child.tail or '')
		return ''.join(parts)

	def walk(node):
		for child in node:
			if child.tag in skip:
				continue
			if child.tag in (f'{t}p', f'{t}h'):
				out.append(text_of(child))
			elif child.tag == f'{tb}table':
				for row in child.iter(f'{tb}table-row'):
					cells = [' '.join(text_of(p) for p in cell.iter(f'{t}p')).strip()
					         for cell in row if cell.tag == f'{tb}table-cell']
					out.append(' | '.join(cells))
				out.append('')
			else:
				walk(child)

	walk(root)
	return _clean('\n'.join(out)), {}


def _csv_text(rows):
	buf = io.StringIO()
	csv.writer(buf, lineterminator='\n').writerows(rows)
	return buf.getvalue().rstrip('\n')


def _sheets(path):
	try:
		from osgeo import gdal
	except ImportError as e:
		raise ValueError('reading spreadsheets needs GDAL, which comes with the installation of MonitorEO with conda: '
		                 'save it as CSV instead') from e
	gdal.UseExceptions()
	try:
		with zipfile.ZipFile(path) as z:
			if sum(i.file_size for i in z.infolist()) > MAX_SHEETS:
				raise ValueError('the spreadsheet is too big once decompressed: save the sheets that matter as CSV')
	except zipfile.BadZipFile as e:
		raise ValueError('the spreadsheet cannot be read: is it damaged?') from e
	try:
		ds = gdal.OpenEx(path, gdal.OF_VECTOR, open_options=['HEADERS=AUTO'])
	except RuntimeError as e:
		raise ValueError(f'the spreadsheet cannot be read ({e})') from e
	blocks, sheets = [], []
	for i in range(ds.GetLayerCount()):
		layer = ds.GetLayer(i)
		defn = layer.GetLayerDefn()
		names = [defn.GetFieldDefn(j).GetName() for j in range(defn.GetFieldCount())]
		rows = []
		for feature in layer:
			rows.append(['' if not feature.IsFieldSet(j) or feature.IsFieldNull(j) else
			             _cell(feature.GetField(j)) for j in range(len(names))])
		if not names and not rows:
			continue
		sheets.append({'name': layer.GetName(), 'rows': len(rows), 'columns': len(names)})
		blocks.append(f'[sheet {layer.GetName()}: {len(rows)} rows, {len(names)} columns]\n' +
		              _csv_text([names] + rows))
	ds = None
	if not sheets:
		raise ValueError('the spreadsheet has no data')
	return '\n\n'.join(blocks), {'sheets': sheets, 'rows': sum(s['rows'] for s in sheets)}


def _cell(value):
	if isinstance(value, float) and value.is_integer():
		return str(int(value))
	return str(value)


def _table(path, delimiter=None):
	with open(path, 'rb') as f:
		text = decode(f.read())
	sample = text[:20000]
	if delimiter is None:
		try:
			delimiter = csv.Sniffer().sniff(sample, delimiters=',;\t|').delimiter
		except csv.Error:
			delimiter = ','
	sep = {'\t': 'tab', ',': 'comma', ';': 'semicolon', '|': 'vertical bar'}.get(delimiter, repr(delimiter))
	limit = csv.field_size_limit()
	try:  # its rows and columns, for the line before it (its text goes as it is)
		csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))  # long fields: geometries in WKT, notes
		rows = list(csv.reader(io.StringIO(text, newline=''), delimiter=delimiter))
		while rows and not any(c.strip() for c in rows[-1]):
			rows.pop()
		if not rows:
			raise ValueError('the table is empty')
		n, columns, about = len(rows) - 1, max(len(r) for r in rows), ''
	except csv.Error:  # an open quote...: the lines, roughly
		lines = [line for line in text.splitlines() if line.strip()]
		n, columns, about = len(lines) - 1, lines[0].count(delimiter) + 1, 'about '
	finally:
		csv.field_size_limit(limit)
	head = f'[table: {about}{n} rows and a header, {about}{columns} columns; separator {sep}]'
	return head + '\n' + _clean(text), {'rows': n, 'columns': columns}


def _text(path):
	with open(path, 'rb') as f:
		return _clean(decode(f.read())), {}


def read(path):
	"""(text, info) of the document at PATH: its text for the model and {'kind', and 'pages' (PDF), 'sheets'
	[{name, rows, columns}] and 'rows' (spreadsheets), 'rows' and 'columns' (CSV, TSV)}. ValueError, with what to do,
	if it cannot be read."""
	ext = os.path.splitext(path)[1].lower()
	check_type(path)
	readers = {'.pdf': _pdf, '.docx': _docx, '.odt': _odt, '.xlsx': _sheets, '.ods': _sheets, '.csv': _table,
	           '.tsv': lambda p: _table(p, '\t'), '.txt': _text, '.md': _text}
	text, info = readers[ext](path)
	if not text.strip():
		raise ValueError('the document has no text')
	return text, {'kind': TYPES[ext], **info}


def summary(info, chars):
	"""What to say of a document: '12 pages, 45,210 characters', '2 sheets, 340 rows'..."""
	def n(x, word):
		return f"{x:,} {word}{'s' if x != 1 else ''}"
	parts = [info.get('kind') or 'document']
	if info.get('pages'):
		parts.append(n(info['pages'], 'page'))
	if info.get('sheets'):
		parts.append(n(len(info['sheets']), 'sheet'))
	if info.get('rows') is not None:
		parts.append(n(info['rows'], 'row'))
	parts.append(n(chars, 'character'))
	return ', '.join(parts)


def parts(text, size):
	"""TEXT cut in parts of at most SIZE characters, at the end of a line when it can."""
	out, start = [], 0
	while start < len(text):
		end = min(len(text), start + size)
		if end < len(text):
			cut = text.rfind('\n', start + size // 2, end)
			end = cut + 1 if cut > 0 else end
		out.append(text[start:end])
		start = end
	return out or ['']


class _Fold(dict):
	"""For str.translate: each character as a lowercase letter without its accent (á is a, Ñ is n), always one for
	one, so that a position in the folded text is that of the text."""

	def __missing__(self, code):
		c = chr(code)
		folded = (unicodedata.normalize('NFKD', c)[:1] or c).lower()
		self[code] = folded if len(folded) == 1 else c
		return self[code]


_FOLD = _Fold()


def _plain(text):
	return text.translate(_FOLD)


def search(text, query, size, context=600):
	"""The passages of TEXT with the words of QUERY (without accents nor case, at least 3 letters), together at most
	SIZE characters, in the order of the text: [(part, passage)], with the number of the part (from 1) of
	parts(TEXT, size) where each starts. The passages around the rarest words, and with more of the words near, come
	first; each takes at most 2 * CONTEXT characters."""
	words = list(dict.fromkeys(w for w in re.findall(r'\w+', _plain(query)) if len(w) >= 3))
	if not words:
		return []
	plain = _plain(text)
	hits = {w: [m.start() for m in re.finditer(re.escape(w), plain)] for w in words}
	hits = {w: h for w, h in hits.items() if h}
	if not hits:
		return []
	candidates = []
	for w in sorted(hits, key=lambda x: len(hits[x])):  # the rarest words first
		candidates += hits[w][:500]
		if len(candidates) >= 1000:
			break

	def score(h):
		seg = plain[max(0, h - context):h + context]
		return sum(1 for w in hits if w in seg)

	taken, used = [], 0
	for h in sorted(dict.fromkeys(candidates), key=lambda h: (-score(h), h)):
		allowed = min(2 * context, size - used)
		if allowed <= 0:
			break
		a = max(0, h - allowed // 2)
		b = min(len(text), a + allowed)
		if any(a < tb and b > ta for ta, tb in taken):
			continue
		taken.append((a, b))
		used += b - a
	bounds, start = [], 0
	for p in parts(text, size):
		bounds.append(start)
		start += len(p)
	return [(max(i for i, s in enumerate(bounds) if s <= a) + 1, text[a:b]) for a, b in sorted(taken)]
