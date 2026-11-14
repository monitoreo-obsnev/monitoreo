"""The datasets of the Earth Engine data catalog (https://developers.google.com/earth-engine/datasets), searched by
words, dates and area, as the dataset search of geemap (Wu, 2020): the images and collections of images that Earth
Engine publishes, which MonitorEO computes like any data of Earth Engine given by its ID (see monitoreo.assets).

MonitorEO keeps a copy of its index (eecatalog.json.gz: the images and collections of images of its STAC catalog,
https://storage.googleapis.com/earthengine-stac/catalog/catalog.json, without the tables and the deprecated datasets),
so that every tool searches it without Earth Engine nor the internet. It is compressed (gzip -dc shows it), as
community.json.gz, for the scan of plugins.qgis.org. Its maintainers refresh it with:

    python -m monitoreo.eecatalog

Each record has id (the ID of its Earth Engine asset), title, type (image or image_collection), start and end (the
first and last day of its data; end empty if it goes on: a collection of images whose last image is at most OPEN days
older than the copy, as its record does not say it), bbox ([west, south, east, north], degrees), provider, keywords,
gsd (the smallest pixel of its bands, in metres, when its record says it), the start of its description and its page
in the catalog. The search ranks by the words found in its title and ID first, then in its keywords, provider and
description; describe_asset reads its bands, units and how to cite it.
"""

import concurrent.futures
import datetime as dt
import gzip
import json
import os
import re
import unicodedata
import urllib.request

SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'eecatalog.json.gz')
ROOT = 'https://storage.googleapis.com/earthengine-stac/catalog/catalog.json'
PAGE = 'https://developers.google.com/earth-engine/datasets/catalog/{}'
RASTERS = ('image', 'image_collection')
FIELDS = ('id', 'title', 'type', 'start', 'end', 'bbox', 'provider', 'keywords', 'gsd', 'description')
DESCRIPTION = 240  # characters of the description kept (its first sentences), to search it
OPEN = 120  # days: a collection whose last image is at most this older than the copy goes on (e.g. ERA5-Land, 2 months)
MAX_LIMIT = 100

_snapshot = None


def load():
	"""The copy of the index: {'source', 'downloaded', 'datasets': [records]}."""
	global _snapshot
	if _snapshot is None:
		with gzip.open(SNAPSHOT, 'rt', encoding='utf-8') as f:
			_snapshot = json.load(f)
	return _snapshot


def _low(text):
	text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode()
	return re.sub(r'[^a-z0-9.\-_/]+', ' ', text.lower()).strip()  # sentinel-2 is a word, not sentinel and 2


def _day(text, what):
	if text in (None, ''):
		return None
	try:
		return dt.date.fromisoformat(str(text)[:10])
	except ValueError:
		raise ValueError(f'{what} is a date YYYY-MM-DD, not {text!r}') from None


def _bbox(bbox):
	if bbox in (None, ''):
		return None
	try:
		w, s, e, n = [float(x) for x in bbox]
	except (TypeError, ValueError):
		raise ValueError('bbox is [west, south, east, north] in degrees') from None
	if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
		raise ValueError('bbox is [west, south, east, north] in degrees')
	return w, s, e, n


def _score(d, words):
	"""How well the record D matches WORDS: (words found, 3 for each in its title or ID and 1 in its keywords, provider
	or description), or None if it has fewer than half of them."""
	head = _low(f"{d['title']} {d['id']}")
	tail = _low(f"{' '.join(d.get('keywords') or [])} {d.get('provider') or ''} {d.get('description') or ''}")
	found, score = 0, 0
	for w in words:
		if w in head:
			found, score = found + 1, score + 3
		elif w in tail:
			found, score = found + 1, score + 1
	return (found, score) if found * 2 >= len(words) else None


def search(text=None, start=None, end=None, bbox=None, kind=None, limit=20):
	"""The images and collections of images of the catalog with the words of TEXT (at least half of them) in their
	title, ID, keywords, provider or description (those with most words first, and in their title or ID), the
	collections of images with data between START and END (any part of the period; the images, fixed layers without
	dates, whatever their dates), over BBOX ([w, s, e, n], degrees; any part of it), of one KIND ('image' or
	'image_collection'), at most LIMIT (100): [{id, title, type, start, end, bbox, provider, keywords, gsd, page}]."""
	if kind and kind not in RASTERS:
		raise ValueError('unknown kind {}: use image or image_collection'.format(kind))
	a, b, box = _day(start, 'start'), _day(end, 'end'), _bbox(bbox)
	if a and b and b < a:
		raise ValueError('end is before start')
	words = _low(text).split()
	found = []
	for i, d in enumerate(load()['datasets']):
		if kind and d['type'] != kind:
			continue
		dated = d['type'] == 'image_collection'  # an image is a fixed layer: computed without dates
		if a and dated and d.get('end') and _day(d['end'], 'end') < a:
			continue
		if b and dated and d.get('start') and _day(d['start'], 'start') > b:
			continue
		if box and d.get('bbox'):
			w, s, e, n = d['bbox']
			if e < box[0] or w > box[2] or n < box[1] or s > box[3]:
				continue
		score = _score(d, words) if words else (0, 0)
		if score is None:
			continue
		found.append(((-score[0], -score[1]), i, d))
	found.sort(key=lambda x: (x[0], x[1]))  # the most words first, then the best placed, then in the order of the IDs
	limit = max(1, min(int(limit or 20), MAX_LIMIT))
	return [dict(d, page=PAGE.format(d['id'].replace('/', '_'))) for _, _, d in found[:limit]]


# The copy of the index ------------------------------------------------------------------------------------------------

def _get(url, timeout=30):
	if not url.startswith('https://'):
		raise ValueError(f'not https: {url}')
	with urllib.request.urlopen(url, timeout=timeout) as r:  # nosec B310: https only (checked above)
		return json.load(r)


def _record(c, day=None):
	"""The record of the copy of a STAC collection C, or None (a table, or deprecated). Its record says the day of its
	last image, also for a collection that goes on: without end if it is a collection of images whose last image is at
	most OPEN days older than DAY (the day of the copy)."""
	kind = c.get('gee:type')
	if kind not in RASTERS or c.get('deprecated') or c.get('gee:status') == 'deprecated':
		return None
	ext = c.get('extent') or {}
	interval = ((ext.get('temporal') or {}).get('interval') or [[None, None]])[0]
	box = ((ext.get('spatial') or {}).get('bbox') or [None])[0]
	gsd = [x for x in (c.get('summaries') or {}).get('gsd') or [] if isinstance(x, (int, float))]
	providers = [p.get('name') for p in c.get('providers') or [] if p.get('name')]
	text = ' '.join(re.sub(r'<[^>]+>|\[([^]]*)\]\([^)]*\)', r'\1', str(c.get('description') or '')).split())
	out = {'id': c['id'], 'title': ' '.join(str(c.get('title') or '').split()), 'type': kind,
	       'start': (interval[0] or '')[:10] or None, 'end': (interval[1] or '')[:10] or None,
	       'bbox': [round(float(x), 3) for x in box] if box and len(box) == 4 else None,
	       'provider': providers[0] if providers else None, 'keywords': list(c.get('keywords') or [])[:12],
	       'gsd': min(gsd) if gsd else None,
	       'description': text[:DESCRIPTION].rsplit(' ', 1)[0] + '…' if len(text) > DESCRIPTION else text}
	if day and kind == 'image_collection' and out['end'] and 0 <= (day - dt.date.fromisoformat(out['end'])).days <= OPEN:
		out['end'] = None  # it goes on (an end after the copy, as the projections to 2100, is kept)
	return {k: out[k] for k in FIELDS if out.get(k) not in (None, '', [])}


def update(path=SNAPSHOT, workers=16):
	"""Read the STAC catalog of Earth Engine and write the copy of MonitorEO to PATH: its images and collections of
	images, without the tables and the deprecated ones (the collections that go on without end). Returns how many it
	kept."""
	children = [lk['href'] for lk in _get(ROOT)['links'] if lk.get('rel') == 'child']
	with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
		catalogs = list(pool.map(_get, children))
		links = [lk['href'] for cat in catalogs for lk in cat.get('links') or [] if lk.get('rel') == 'child']
		collections = list(pool.map(_get, links))
	seen, kept, today = set(), [], dt.date.today()
	for c in collections:
		rec = _record(c, today)
		if rec and rec['id'] not in seen:
			seen.add(rec['id'])
			kept.append(rec)
	kept.sort(key=lambda d: d['id'])
	data = {'source': ROOT, 'downloaded': today.isoformat(),
	        'note': 'The images and collections of images of the STAC catalog of Earth Engine, without its tables and '
	                'deprecated datasets, as MonitorEO searches them (monitoreo.eecatalog).', 'datasets': kept}
	with gzip.GzipFile(path, 'wb', mtime=0) as gz:  # mtime 0: the same index, the same file
		gz.write((json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8'))
	global _snapshot
	_snapshot = None
	return len(kept)


if __name__ == '__main__':
	print(f'{update()} images and collections of images of the Earth Engine data catalog in {SNAPSHOT}')
