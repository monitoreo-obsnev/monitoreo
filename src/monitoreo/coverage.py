"""Where the values of a variable come from, and the dates of its images: the Earth Engine datasets of each variable,
named with their product level (e.g. COPERNICUS/S2_SR_HARMONIZED (Harmonized Sentinel-2 MSI, Level-2A (SR))), and the
first and last dates of their images, from the copy of the index of the Earth Engine data catalog that MonitorEO keeps
(monitoreo.eecatalog), without Earth Engine.

Every period is checked before Earth Engine computes it (variable.specs calls check for each spec, also for those of
the conditions of where, whose warnings say so, and of the recipes): a period that ends before the first image of its
data, falls in a gap between its collections or begins after today is an error (ValueError); one that begins before the
first image, or ends (or even begins) after the last image of data that ended in the copy of the index (e.g.
IDAHO_EPSCOR/TERRACLIMATE, which Earth Engine may extend after that copy), gives a warning, in the answer of the
services ('warnings') and as a Python warning (DataDatesWarning). The answers also say which data their values come
from ('data_source'), and their charts say it in a line «Data: ...».

The dates are those of the copy of the index (eecatalog.load()['downloaded']), which its maintainers refresh at each
release (python -m monitoreo.eecatalog): a collection that goes on has no last date. The Landsat of the catalog
(LANDSAT) is Landsat 5, 7 (only until 2003-05-31, see sensors.LANDSAT), 8 and 9, so its images have a gap between
the last of Landsat 5 and the first of Landsat 8, except with quality landsat7 (Landsat 7 until its last image, see
sensors.LANDSAT7), which fills it. The data of Earth Engine given by their ID (collection=) have the
dates of their record of the index, if they have one (else no date is checked: asking Earth Engine would cost a call
for each one), their last image the day before the end of its extent (that of a yearly collection is the end of its
last year: ESA/WorldCover/v200, of 2021, ends on 2022-01-01); the fixed layers (elevation, slope, an image) have no
dates.

dates(entry) gives the first and last day of the images of a variable of the catalog (e.g. to limit the period of a
form to them), refused whether a period has no images (e.g. to offer only the maps of the steps that have them), and
of_entry and of_asset what a chart says of its data.
"""

import contextlib
import contextvars
import datetime as dt
import re
import warnings

LANDSAT = 'LANDSAT'  # the collection of the catalog with Landsat 5, 7, 8 and 9 (sensors.LANDSAT)
# the product level in the subtitle of a title of the Earth Engine data catalog, e.g. 'Level-2A (SR)', 'Level-1C (TOA)'
LEVEL = re.compile(r'\bLevel[- ]?\d[A-Za-z0-9]*(?: \([A-Za-z]+\))?')
LONG_TITLE = 70  # characters: a longer title is shortened to the part before its subtitle (see title)
STEP_DAYS = {'daily': 1, 'monthly': 31, 'yearly': 366, 'annual': 366}  # the days that an image of each 'tr' covers
ASSET_STEP = 31  # days: the images of the data given by their ID may each cover up to a month (their step is unknown)


class DataDatesWarning(UserWarning):
	"""The period asked for begins before the first image of its data, or ends after the last image of data that
	ended: those days have no data (see check)."""


_by_id = None  # (the copy of the index, its records by ID)


def _records():
	"""The records of the copy of the index of the Earth Engine data catalog by their ID (monitoreo.eecatalog)."""
	global _by_id
	from . import eecatalog
	snap = eecatalog.load()
	if _by_id is None or _by_id[0] is not snap:  # also after a new copy (eecatalog.update)
		_by_id = (snap, {d['id']: d for d in snap['datasets']})
	return _by_id[1]


def checked():
	"""The day of the copy of the index of the Earth Engine data catalog whose dates the tools use (YYYY-MM-DD)."""
	from . import eecatalog
	return eecatalog.load().get('downloaded')


def short_title(title):
	"""TITLE of a dataset of the Earth Engine data catalog, short for a chart: without the subtitle after ': ' when it
	has the product level ('Harmonized Sentinel-2 MSI: MultiSpectral Instrument, Level-2A (SR)' is 'Harmonized
	Sentinel-2 MSI, Level-2A (SR)') or when the title is longer than LONG_TITLE characters ('TerraClimate: Monthly
	Climate and ...' is 'TerraClimate'); else as it is."""
	title = ' '.join(str(title or '').split())
	if ': ' not in title:
		return title or None
	head, tail = title.split(': ', 1)
	level = LEVEL.search(tail)
	if level:
		return f'{head}, {level.group(0)}'
	return head if len(title) > LONG_TITLE else title


def title(asset):
	"""The short title (see short_title) of the Earth Engine dataset ASSET: of its record in the Earth Engine data
	catalog or in the GEE Community Catalog, or None if neither has it."""
	rec = _records().get(asset)
	if rec is None:
		from . import community
		rec = community.record(asset)
	return short_title(rec.get('title')) if rec else None


def join(words):
	"""WORDS in a sentence: 'a', 'a and b', 'a, b and c'."""
	words = [str(w) for w in words]
	return ' and '.join(words) if len(words) < 3 else f"{', '.join(words[:-1])} and {words[-1]}"


def join_titles(titles):
	"""One title for the titles of several datasets of a family, with what they share said once: 'USGS Landsat 8 Level
	2, Collection 2, Tier 1' and 'USGS Landsat 9 Level 2, ...' are 'USGS Landsat 8 and 9 Level 2, Collection 2, Tier
	1'; titles that share nothing are joined with '; '."""
	titles = list(dict.fromkeys(t for t in titles if t))
	if len(titles) < 2:
		return titles[0] if titles else None
	words = [t.split(' ') for t in titles]
	n = min(len(w) for w in words)
	head = 0
	while head < n - 1 and all(w[head] == words[0][head] for w in words):
		head += 1
	tail = 0
	while tail < n - head - 1 and all(w[-1 - tail] == words[0][-1 - tail] for w in words):
		tail += 1
	if not head and not tail:
		return '; '.join(titles)
	middles = [' '.join(w[head:len(w) - tail]) for w in words]
	return ' '.join(words[0][:head] + [join(middles)] + (words[0][len(words[0]) - tail:] if tail else []))


def text(ids, name):
	"""The data of the datasets IDS named NAME (their title), as the charts and warnings say it: 'COPERNICUS/S2_SR_
	HARMONIZED (Harmonized Sentinel-2 MSI, Level-2A (SR))'."""
	return f'{join(ids)} ({name})' if name else join(ids)


def parts(entry, quality=None):
	"""The Earth Engine collections of the images of the variable of the catalog ENTRY, with the dates of their images
	as MonitorEO reads them with QUALITY: [(ID, first day, last day or None if it goes on)] (a day None if the index does
	not have it). The Landsat of the catalog is its four collections, Landsat 7 only until 2003-05-31 (sensors.LANDSAT;
	until its last image with quality landsat7, see sensors.landsat_parts); a
	collection with a gap-filled version (sensors.GAP_FILLED: ET and LE of MODIS) is that version up to the date of
	catalog.json and the collection after it."""
	if entry.get('col') == LANDSAT:
		from . import sensors
		out = []
		seven = sensors.landsat7(quality) or entry.get('landsat7_slc_off')  # see used
		for col, _, last in sensors.landsat_parts({'landsat7': bool(seven)}):
			rec = _records().get(col) or {}
			end = rec.get('end')
			if last:  # its images until the day before LAST
				stop = (dt.date.fromisoformat(last) - dt.timedelta(days=1)).isoformat()
				end = min(end, stop) if end else stop
			out.append((col, rec.get('start'), end))
		return out
	from . import sensors
	if entry.get('col') in sensors.GAP_FILLED:  # its gap-filled version up to the date of the catalog, then itself
		from . import catalog
		filled = sensors.GAP_FILLED[entry['col']]
		dates = catalog.load()['collections'][filled]  # the date of sensors.raw_collection and references.datasets
		after = (dt.date.fromisoformat(dates['end']) + dt.timedelta(days=1)).isoformat()
		rec = _records().get(entry['col']) or {}
		return [(filled, dates['start'], dates['end']), (entry['col'], max(after, rec.get('start') or after), rec.get('end'))]
	rec = _records().get(entry['col']) or {}
	return [(entry['col'], rec.get('start'), rec.get('end'))]


def _overlaps(part, first, last):
	"""Whether PART (ID, first day, last day) has images between FIRST and LAST (ISO days)."""
	return (not part[1] or part[1] <= last) and (not part[2] or part[2] >= first)


def _in(found, periods):
	"""The parts of FOUND with images in any of PERIODS ([(first, last)]), or all of them if none has or without
	PERIODS."""
	inside = [p for p in found if any(_overlaps(p, a, b) for a, b in periods)] if periods else []
	return inside or list(found)


def _dates_of(found):
	"""(first day, last day or None if one of them goes on) of the images of the parts FOUND."""
	starts = [p[1] for p in found if p[1]]
	ends = [p[2] for p in found]
	return (min(starts) if starts else None), (None if not ends or None in ends else max(ends))


def dates(entry):
	"""{'start', 'end'}: the first and last day (YYYY-MM-DD) of the images of the variable of the catalog ENTRY, end
	None if they go on, both None for a fixed layer without dates (elevation, slope, WorldClim) or if the index does
	not have them. See checked for the day of the index."""
	if entry.get('static'):
		return {'start': None, 'end': None}
	start, end = _dates_of(parts(entry))
	return {'start': start, 'end': end}


def of_entry(entry, periods=()):
	"""What the values of the variable of the catalog ENTRY come from, in PERIODS ([(first, last day)]; all its
	collections without them): {'collections': [IDs], 'title' (their title, or None), 'start', 'end' (see dates),
	'text' (e.g. 'COPERNICUS/S2_SR_HARMONIZED (Harmonized Sentinel-2 MSI, Level-2A (SR))')}."""
	found = _in(parts(entry), [] if entry.get('static') else periods)
	ids = [p[0] for p in found]
	name = join_titles([title(i) for i in ids])
	return dict({'collections': ids, 'title': name, 'text': text(ids, name)}, **dates(entry))


def of_asset(asset, dated=True):
	"""What the values of the data of Earth Engine ASSET (given by its ID) come from: {'collections', 'title', 'start',
	'end', 'text'} as of_entry; its dates those of its record of the Earth Engine data catalog (None without one, or
	without DATED: an image, a fixed layer)."""
	rec = (_records().get(asset) or {}) if dated else {}
	name = title(asset)
	return {'collections': [asset], 'title': name, 'start': rec.get('start'), 'end': rec.get('end'),
	        'text': text([asset], name)}


# The notes of a call of the services: its warnings and the data of its values ------------------------------------

class Notes:
	"""What a call of the services noted: the warnings of its periods (texts, in their order, each once) and the data
	of its values ({key: [entry or None, asset or None, periods]}, see used)."""

	def __init__(self):
		self.warnings = []
		self.data = {}

	def warn(self, message):
		if message not in self.warnings:
			self.warnings.append(message)
			return True
		return False

	def merge(self, other):
		for w in other.warnings:
			self.warn(w)
		for key, (entry, asset, periods) in other.data.items():
			self.data.setdefault(key, [entry, asset, []])[2].extend(periods)

	def source(self):
		"""The data of the values of the call, as its charts say it (see source), or None."""
		texts = []
		for entry, asset, periods in self.data.values():
			t = of_entry(entry, periods)['text'] if entry else of_asset(asset, dated=False)['text']
			if t not in texts:
				texts.append(t)
		return '; '.join(texts) or None


_notes = contextvars.ContextVar('monitoreo_coverage_notes', default=None)
_label = contextvars.ContextVar('monitoreo_coverage_label', default='')  # the start of the warnings (see labelled)


@contextlib.contextmanager
def collect():
	"""Note, while it lasts, the warnings of the periods (check) and the data of the values (used) of a call of the
	services: yields its Notes. A call inside another notes them for both."""
	notes = Notes()
	token = _notes.set(notes)
	try:
		yield notes
	finally:
		_notes.reset(token)
		outer = _notes.get()
		if outer is not None:
			outer.merge(notes)


def noted(fn, *args, **kwargs):
	"""(FN(*ARGS, **KWARGS), the warnings of its periods [texts]) (see collect): for the tools that take no answer of
	the services with them, e.g. the spec of make_spec with those of the conditions of its where (R: mo_image)."""
	with collect() as notes:
		out = fn(*args, **kwargs)
	return out, list(notes.warnings)


@contextlib.contextmanager
def labelled(label):
	"""While it lasts, the warnings of check begin with LABEL, e.g. 'where, the condition on NDVI (Sentinel-2): ' (as
	the errors of the conditions of where: variable.where_specs), so that they do not read as those of the result."""
	token = _label.set(_label.get() + label)
	try:
		yield
	finally:
		_label.reset(token)


def used(spec, entry=None):
	"""Note that the values of the call come from the data of SPEC (a spec of monitoreo.variable; ENTRY, that of the
	catalog if it is one of its variables), in its period."""
	notes = _notes.get()
	if notes is None:
		return
	asset = None if entry else spec.get('collection') or spec.get('image')
	if not entry and not asset:
		return
	from . import sensors
	if entry and entry.get('col') == LANDSAT and sensors.landsat7(spec.get('quality')):  # Landsat 7 after 2003 too
		entry = dict(entry, landsat7_slc_off=True)  # (see parts)
	key = (('entry', entry['col'], bool(entry.get('landsat7_slc_off'))) if entry else ('asset', asset))
	period = spec.get('period')
	periods = [(str(period[0])[:10], str(period[1])[:10])] if period and not (entry or {}).get('static') else []
	notes.data.setdefault(key, [entry, asset, []])[2].extend(periods)


def source():
	"""The data of the values of the call of the services that is running (see used), as its charts say it, or None."""
	notes = _notes.get()
	return notes.source() if notes else None


def _warn(message):
	message = _label.get() + message
	notes = _notes.get()
	if notes is None or notes.warn(message):  # once in a call
		warnings.warn(message, DataDatesWarning, stacklevel=2)
	return message


# The check of a period ----------------------------------------------------------------------------------------------

def step_days(entry):
	"""The days that each image of the variable of the catalog ENTRY covers (its temporal resolution, 'tr': daily 1,
	'8-days' 8, monthly 31): a period may end that many days after the date of the last image without missing data."""
	tr = str(entry.get('tr') or '').strip().lower()
	m = re.match(r'(\d+)\s*-?\s*days?$', tr)
	return int(m.group(1)) if m else STEP_DAYS.get(tr, 1)


def _how_long(days):
	"""DAYS in words: '1 day', '20 days', '15 months', '4 years'."""
	n, unit = (days, 'day') if days < 31 else (round(days / 30.4375), 'month') if days < 730 else \
		(round(days / 365.25), 'year')
	return f'{n} {unit}' if n == 1 else f'{n} {unit}s'


def _missing(which, days):
	"""'its first 15 months have no data', or 'its last day has no data'."""
	length = _how_long(days)
	return f"its {which} {length.split(' ', 1)[1] if length.startswith('1 ') else length} " \
	       f"{'has' if length.startswith('1 ') else 'have'} no data"


def _last_image(rec):
	"""The day of the last image of the data given by their ID with the record REC of the index (None if they go on):
	the day before the end of its extent, which is that of the time its last image covers (ESA/WorldCover/v200, of
	2021, ends on 2022-01-01), not before its first day."""
	end = rec.get('end')
	if not end:
		return None
	day = (dt.date.fromisoformat(end[:10]) - dt.timedelta(days=1)).isoformat()
	return max(day, rec.get('start') or day)


def _verdict(spec, entry=None, today=None):
	"""(the error of the period of SPEC or None, [the texts of its warnings]): see check."""
	from . import composite
	if entry is not None:
		if entry.get('static'):
			return None, []
		found, step = parts(entry, spec.get('quality')), step_days(entry)
	else:
		asset = spec.get('collection')
		rec = _records().get(asset) if asset else None
		if not rec or rec.get('type') != 'image_collection':
			return None, []
		found, step = [(asset, rec.get('start'), _last_image(rec))], ASSET_STEP
	if not any(p[1] for p in found):
		return None, []
	wins = composite.windows(spec['period'], spec.get('season'))
	first, last = wins[0][1], wins[-1][2] - dt.timedelta(days=1)
	a, b = first.isoformat(), last.isoformat()
	season = ' (in its season)' if spec.get('season') else ''
	today = today or dt.date.today()
	if first > today:  # whatever the data: also those that ended (the warning below would say they may have images)
		return (f'The period asked for{season}, {a} to {b}, begins after today ({today.isoformat()}): there are no '
		        f'images of {_text_of(found)} for it yet.'), []
	start, end = _dates_of(found)
	inside = [p for p in found if _overlaps(p, a, b)]
	if not inside:
		data = _text_of(found)
		if start and b < start:
			return (f'The images of {data} start on {start}: the period asked for{season}, {a} to {b}, ends before them '
			        f'and has no data. Choose a period from {start} on.'), []
		if end and a > end:  # a warning, not an error: the copy of the index may be older than their last images
			return None, [f'The images of {data} end on {end} (in the copy of the Earth Engine data catalog of '
			              f'{checked()}): the period asked for{season}, {a} to {b}, begins after them, so it may have no '
			              'data, unless Earth Engine has added images since.']
		before = max((p[2] for p in found if p[2] and p[2] < a), default=None)
		after = min((p[1] for p in found if p[1] and p[1] > b), default=None)
		if before and after:
			gap = ((dt.date.fromisoformat(before) + dt.timedelta(days=1)).isoformat(),
			       (dt.date.fromisoformat(after) - dt.timedelta(days=1)).isoformat())
			seven = ('' if entry is None or entry.get('col') != LANDSAT else ' Or add Landsat 7 after 2003, with the '
			         'gaps of its scan line corrector, which has images then (quality landsat7: true).')
			return (f'The images of {data} have none from {gap[0]} to {gap[1]}: the period asked for{season}, {a} to '
			        f'{b}, has no data. Choose a period before or after those days.{seven}'), []
		return None, []
	out = []
	data = _text_of(inside)
	if start and a < start:
		days = (dt.date.fromisoformat(start) - first).days
		out.append(f'The images of {data} start on {start}: the period asked for{season} begins on {a}, so '
		           f"{_missing('first', days)}.")
	if end:
		covered = dt.date.fromisoformat(end) + dt.timedelta(days=step - 1)
		if last > covered:
			out.append(f'The images of {data} end on {end}: the period asked for{season} ends on {b}, so '
			           f"{_missing('last', (last - covered).days)}.")
	return None, out


def check(spec, entry=None, today=None):
	"""Check the period of SPEC (a spec of monitoreo.variable with period and season; ENTRY, its entry of the catalog
	if it is one of its variables, else the data given by its ID, spec['collection']) against the dates of its images
	(see parts and of_asset), without Earth Engine: ValueError if it has no image of them (it ends before the first,
	falls in a gap between collections, or begins after TODAY, by default today); otherwise the warnings of the days
	without data, [texts] (empty if none), each also noted for the answer of the call (see collect) and given as a
	Python warning (DataDatesWarning): the period begins before the first image, or ends after the last image of data
	that ended (and the days it covers, step_days), or begins after it (Earth Engine may have added images since the
	copy of the index). Nothing for the fixed layers and the data without known dates."""
	error, found = _verdict(spec, entry, today)
	if error:
		raise ValueError(error)
	return [_warn(w) for w in found]


def refused(spec, entry=None, today=None):
	"""The error of check for the period of SPEC (see check), or None if it has images; without warnings."""
	return _verdict(spec, entry, today)[0]


def _text_of(found):
	ids = [p[0] for p in found]
	return text(ids, join_titles([title(i) for i in ids]))


def app_index():
	"""The collections of the variables of the catalog with the dates and short titles of their images, for the Earth
	Engine app (gee/build.py, catalog.js): {'checked' (the day of the index), 'collections': {col of the catalog:
	[[ID, first day, last day, short title]]}, 'landsat7': those of LANDSAT with quality landsat7} (see parts and title), so that it checks the periods and names the data
	as the package does."""
	from . import catalog
	cols = {}
	landsat7 = None
	for e in catalog.variables():
		if e['col'] not in cols:
			cols[e['col']] = [[p[0], p[1], p[2], title(p[0])] for p in parts(e)]
		if e['col'] == LANDSAT and landsat7 is None:  # with quality landsat7: Landsat 7 until its last image
			landsat7 = [[p[0], p[1], p[2], title(p[0])] for p in parts(e, {'landsat7': True})]
	return {'checked': checked(), 'collections': cols, 'landsat7': landsat7}
