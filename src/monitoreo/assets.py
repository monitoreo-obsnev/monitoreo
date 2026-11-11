"""Data of Earth Engine outside the catalog of MonitorEO, given by their ID (the path of their asset, as in
ee.Image('WORLDCLIM/V1/BIO') or ee.ImageCollection('IDAHO_EPSCOR/TERRACLIMATE')): any image or collection of images of
the Earth Engine data catalog, of the GEE Community Catalog (monitoreo.community) or of a project the account can read.

The tools compute them like the variables of the catalog, with these arguments instead of variable and sensor:

    collection   the ID of a collection of images with dates: aggregated in time (metric, temporal, period, season)
                 like the variables of the catalog, with time series, trends and comparisons
    image        the ID of an image, or of a collection of tiles (mosaicked, e.g. a DEM): a fixed layer without dates,
                 with maps and their statistics (no time series, trends or comparisons)
    band         the band (one)
    band_scale   factor of the stored values (e.g. 0.0001 for the NDVI of MODIS); band_offset, what is added after it
    unit         the unit of the values (after band_scale and band_offset) in UDUNITS, e.g. 'mm', 'degC', 'kg m-2'
                 (the words of the STAC records too: 'C' is degC, 'W/m^2' is W m-2, 'unitless' is 1; '' is none)
    terrain      'slope' or 'aspect' of the band of an image, in degrees (its unit is then degree)

describe(asset) tells what an ID is before computing it: an image or a collection (so which argument), its bands, its
dates and pixel size and, for the datasets of the Earth Engine data catalog, what their STAC record says of each band
(unit, scale, offset, classes), their licence and how to cite them (cite). The pixel filters of MonitorEO (clouds,
water, snow, aerosols) are for the variables of its catalog: these data keep only their own mask.

References:
    Gorelick, N., Hancher, M., Dixon, M., Ilyushchenko, S., Thau, D., & Moore, R. (2017). Google Earth Engine:
    Planetary-scale geospatial analysis for everyone. Remote Sensing of Environment, 202, 18–27.
    https://doi.org/10.1016/j.rse.2017.06.031
"""

import html
import http.client
import json
import re
import time
import urllib.error
import urllib.request

from . import community

STAC = 'https://storage.googleapis.com/earthengine-stac/catalog'
PAGE = 'https://developers.google.com/earth-engine/datasets/catalog/'
TYPES = {'IMAGE': 'image', 'IMAGE_COLLECTION': 'image_collection'}
# A DOI in a text: its suffix may have balanced parentheses and < > ; (the SICI DOIs of AMS and of old articles of
# Elsevier: 10.1175/1520-0477(1996)077<0437:TNYRP>2.0.CO;2, 10.1016/0034-4257(79)90013-0)
DOI = re.compile(r'''10\.\d{4,9}/(?:\([^\s()\[\]]*\)|[^\s()\[\]"',])+''')
LINK = re.compile(r'\[([^\]]*)\]\((?:[^\s()]|\([^\s()]*\))*\)')  # of Markdown, whose target may have (...)
DOI_OR_LINK = re.compile(LINK.pattern + r'|(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?' + DOI.pattern, re.I)
# what a citation asks the reader to fill in: (<date of access>), (date of access), [access date], [indicate subset
# used]
PLACEHOLDER = re.compile(r'\(\s*<[^<>]*>\s*\)|[(\[]\s*(?:date of access|access(?:ed)? date|indicate [^)\]]*)\s*[)\]]',
                         re.I)
RETRY = 60  # seconds before a STAC record that could not be read (no network, timeout, server error) is read again
# The units of the bands of the STAC records of the Earth Engine data catalog (gee:units) in UDUNITS; the others are
# left to the user (unit=)
UNITS = {
	'mm': 'mm', 'cm': 'cm', 'm': 'm', 'km': 'km', 'K': 'K', '&deg;C': 'degC', '°C': 'degC', 'C': 'degC',
	'&deg;F': 'degF', 'deg': 'degree', 'degrees': 'degree', 'rad': 'rad', '%': '%', 'Dimensionless': '1',
	'dimensionless': '1', 'unitless': '1', 'Fraction': '1', 'fraction': '1', 'Area fraction': '1',
	'Volume fraction': '1', 'Mass fraction': '1', 'Mol fraction': '1', 'Spectral reflectance': '1',
	'Reflectance factor': '1', 'index': '1', 'Coefficient of Variation': '1', 'count': '1', 'm/s': 'm s-1',
	'm/s^2': 'm s-2', 'm^2/s': 'm2 s-1', 'm^2/s^2': 'm2 s-2', 'm^2 s-2': 'm2 s-2', '1/s': 's-1', 's^-1': 's-1',
	'm^-1': 'm-1', '1/m': 'm-1', 'Pa': 'Pa', 'hPa': 'hPa', 'kPa': 'kPa', 'mbar': 'mbar', 'Pa/s': 'Pa s-1',
	'W/m^2': 'W m-2', 'J/m^2': 'J m-2', 'J/m^2/day': 'J m-2 day-1', 'MJ m^-2 day^-1': 'MJ m-2 day-1', 'J/kg': 'J kg-1',
	'kg/m^2': 'kg m-2', 'kg/m^2/s': 'kg m-2 s-1', 'kg/m^2/8day': 'kg m-2 (8 day)-1', 'kg/m^3': 'kg m-3',
	'g/m^2': 'g m-2', 'g/cm^3': 'g cm-3', 'g/kg': 'g kg-1', 'kg/kg': 'kg kg-1', 'mg/m^3': 'mg m-3',
	'mg/m^3/day': 'mg m-3 day-1', 'mol/m^2': 'mol m-2', 'mol/m^3': 'mol m-3', 'mmol/m^3': 'mmol m-3',
	'cm^3/cm^3': 'cm3 cm-3', 'm^2/m^3': 'm2 m-3', 'Mg/ha': 'Mg ha-1', 'tonnes/hectare': 'Mg ha-1', 'm^2': 'm2',
	'km^2': 'km2', 'ha': 'ha', 'm^3': 'm3', 'mm/d': 'mm day-1', 'mm/day': 'mm day-1', 'mm, daily total': 'mm day-1',
	'mm/hr': 'mm h-1', 'mm/h': 'mm h-1', 'm/h': 'm h-1', 'mm/month': 'mm month-1', 'mm/y': 'mm year-1',
	'mm/pentad': 'mm (5 day)-1', 'meter/year': 'm year-1', 'm of water equivalent': 'm', 'gpm': 'm', 'h': 'h',
	'min': 'min', 's': 's', 'seconds': 's', 'd': 'day', 'y': 'year', 'ppm': 'ppm', 'ppb': 'ppb', '&mu;m': 'um',
	'&micro;m': 'um', 'MW': 'MW', 'dB': 'dB',
}

_stac, _info = {}, {}
_unread = {}  # {asset: when its STAC record could not be read}: not cached, read again after RETRY seconds


def normalize(asset):
	"""The ID of an asset as the tools take it: without quotes, spaces or a call of the Code Editor around it
	(ee.ImageCollection("X") is X) and without the prefix of the public catalog."""
	text = str(asset or '').strip()
	m = re.fullmatch(r'''ee\.(?:Image|ImageCollection)\(\s*['"]([^'"]+)['"]\s*\)\s*;?''', text)
	if m:
		text = m.group(1)
	text = text.strip().strip('\'"').strip()
	return re.sub(r'^projects/earthengine-public/assets/', '', text)


def udunits(unit):
	"""The unit UNIT of a STAC record (gee:units, e.g. 'W/m^2' or '&deg;C') in UDUNITS ('W m-2', 'degC'), or None."""
	if unit is None:
		return None
	return UNITS.get(str(unit).strip())


def stac_url(asset):
	"""The URL of the STAC record of ASSET in the Earth Engine data catalog (it may have none)."""
	asset = normalize(asset)
	parts = asset.split('/')
	folder = parts[1] if parts[0] == 'projects' and len(parts) > 1 else parts[0]
	return f"{STAC}/{'OpenET' if folder == 'openet' else folder}/{asset.replace('/', '_')}.json"


def page(asset):
	"""The page of ASSET in the Earth Engine data catalog."""
	return PAGE + normalize(asset).replace('/', '_')


def _fetch_json(url, timeout=10):
	"""The JSON at URL, or None if there is none (HTTP 4xx: Cloud Storage answers 403 or 404 for a record that does not
	exist). OSError if it cannot be read now (no network, a timeout, a server error, a truncated answer): it may be
	read later."""
	if not str(url).startswith('https://'):
		return None
	try:
		req = urllib.request.Request(url, headers={'User-Agent': 'monitoreo'})
		# only https (checked above): the warning of Bandit about file:/ and other schemes does not apply
		with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310
			return json.loads(r.read().decode('utf-8'))
	except urllib.error.HTTPError as e:  # before OSError: an HTTPError is an OSError too
		if 400 <= e.code < 500:
			return None
		raise OSError(f'{url}: HTTP {e.code}') from None
	except (ValueError, http.client.HTTPException) as e:  # an answer cut short, or not JSON
		raise OSError(f'{url}: {e}') from None


def stac(asset):
	"""The STAC record of ASSET in the Earth Engine data catalog (a dict), or None if it is not there (the community
	datasets and the assets of the users are not) or it cannot be read now. Only an answer is remembered (the record,
	or that there is none): a record that could not be read (no network, a timeout, a server error) is read again
	RETRY seconds later, so that one failure does not take the citation of the data for the rest of the session."""
	asset = normalize(asset)
	if asset not in _stac:
		if asset in _unread and time.monotonic() - _unread[asset] < RETRY:
			return None
		try:
			rec = _fetch_json(stac_url(asset))
		except OSError:  # URLError, timeouts, HTTP 5xx
			_unread[asset] = time.monotonic()
			return None
		_unread.pop(asset, None)
		_stac[asset] = rec if isinstance(rec, dict) and rec.get('id') == asset else None
	return _stac[asset]


def _not_readable(asset, error):
	from . import services
	mine = 'your own Earth Engine account (init with your Google Cloud project)' if services.shared() else \
		'an account with access to it'
	return (f"Earth Engine has no image or collection {asset}, or this account cannot read it ({error}). Check the ID: "
	        "it is the text between the quotes of ee.Image('...') or ee.ImageCollection('...') in the page of the "
	        'dataset (e.g. IDAHO_EPSCOR/TERRACLIMATE). The data of the Earth Engine catalog and of the GEE Community '
	        f'Catalog are public; private assets need {mine}, or to be shared with it.')


def asset_type(asset):
	"""'image' or 'image_collection' of the Earth Engine asset ASSET (ee.data.getAsset, cached); ValueError for
	tables, folders and IDs that cannot be read."""
	return _asset(asset)['type']


def _asset(asset):
	import ee
	asset = normalize(asset)
	if asset not in _info:
		try:
			a = ee.data.getAsset(asset)
		except ee.EEException as e:
			raise ValueError(_not_readable(asset, e)) from None
		t = a.get('type')
		if t in ('TABLE', 'FEATURE_VIEW'):
			raise ValueError(f'{asset} is a table (ee.FeatureCollection), not an image: MonitorEO computes images and '
			                 'collections of images (regions are given with region)')
		if t == 'FOLDER':
			raise ValueError(f'{asset} is a folder: give the ID of an image or a collection of images in it')
		if t not in TYPES:
			raise ValueError(f'{asset} is a {t}, not an image or a collection of images')
		_info[asset] = dict(a, type=TYPES[t])
	return _info[asset]


def _metres(grid):
	"""The size (m) of the pixels of a grid of ee.data.getAsset (degrees at the equator in geographic coordinates)."""
	try:
		size = abs(float(grid['affineTransform']['scaleX']))
	except (KeyError, TypeError, ValueError):
		return None
	crs = str(grid.get('crsCode') or grid.get('crsWkt') or '')
	geographic = crs in ('EPSG:4326', 'EPSG:4269', 'EPSG:4258') or crs.startswith('GEOGCS')
	return round(size * 111320, 1) if geographic else round(size, 3)


def info(asset):
	"""What Earth Engine says of ASSET (metadata, without computing): {'asset', 'type' ('image' or
	'image_collection'), 'bands': [{'band', 'data_type', 'resolution_m'}], 'first_date' (of its first image, or of
	the image; None without dates)} (and 'first_image', of a collection). ValueError if it is not an image or a
	collection of images, or this account cannot read it."""
	asset = normalize(asset)
	a = _asset(asset)
	out = {'asset': asset, 'type': a['type']}
	if a['type'] == 'image':
		img = a
	else:
		img = _first_image(asset)
		out['first_image'] = normalize(img.get('id') or img.get('name') or '')
	out['bands'] = [{'band': b.get('id'), 'data_type': (b.get('dataType') or {}).get('precision', '').lower() or None,
	                 'resolution_m': _metres(b.get('grid'))} for b in img.get('bands') or []]
	out['first_date'] = (img.get('startTime') or '')[:10] or None
	return out


def _first_image(asset):
	"""What Earth Engine says of the first image of the collection ASSET (ee.data.listImages, metadata, without
	computing; cached with the asset). ValueError if it has none or this account cannot read it."""
	import ee
	asset = normalize(asset)
	a = _asset(asset)
	if '_first' not in a:
		try:
			first = ee.data.listImages({'parent': asset, 'pageSize': 1}).get('images') or []
		except ee.EEException as e:
			raise ValueError(_not_readable(asset, e)) from None
		if not first:
			raise ValueError(f'the collection {asset} has no images')
		a['_first'] = first[0]
	return a['_first']


def first_date(asset):
	"""The date (YYYY-MM-DD) of the image ASSET or of the first image of the collection ASSET, or None if it has none
	(a collection of tiles, e.g. a DEM: an image for the tools, their mosaic). ValueError as info."""
	a = _asset(asset)
	img = a if a['type'] == 'image' else _first_image(asset)
	return (img.get('startTime') or '')[:10] or None


def _provider(rec):
	names = [p.get('name') for p in rec.get('providers') or [] if set(p.get('roles') or []) & {'licensor', 'producer'}]
	return ', '.join(n.strip() for n in names if n) or None


def _sentence(text):
	text = ' '.join(str(text or '').split()).strip(' ,;')
	return text if not text or text.endswith(('.', '?', '!')) else text + '.'


def _doi(text):
	"""The DOI in TEXT, as the STAC records give it ('10.x/y', 'doi:10.x/y', 'https://doi.org/10.x/y'), without the
	punctuation after it nor the backslashes of Markdown ('TNYRP\\>2.0'); None if it has none."""
	m = DOI.search(html.unescape(str(text or '')).replace('\\', ''))
	return m.group(0).rstrip('.,;:>') if m else None


def _given_doi(value):
	"""A DOI given as such (sci:doi, the doi of sci:publications), without 'doi:' or 'https://doi.org/' before it."""
	text = re.sub(r'^\s*(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', str(value or ''), flags=re.I).strip()
	return _doi(text) or text or None


def _dois(text):
	"""[(end, DOI)] of the DOIs of TEXT and where each one ends: that of a link of Markdown from its target (where the
	DOI is whole), or else from its text; the same DOI right after another (a DOI and then its link) is one."""
	out = []
	for m in DOI_OR_LINK.finditer(text):
		if m.group(1) is not None:  # a link: [text](target)
			d = _doi(m.group(0)[len(m.group(1)) + 3:-1]) or _doi(m.group(1))
		else:
			d = _doi(m.group(0))
		if d and out and out[-1][1] == d:
			out[-1] = (m.end(), d)
		elif d:
			out.append((m.end(), d))
	return out


def _clean(text):
	"""TEXT of a citation without its DOIs, links and URLs, and without what it asks the reader to fill in (the date of
	access)."""
	text = LINK.sub(r'\1', text)  # the text of the links of Markdown
	text = re.sub(r'(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?' + DOI.pattern, '', text.replace('\\', ''), flags=re.I)
	text = re.sub(r'https?://\S+', '', text)
	text = PLACEHOLDER.sub('', text)
	text = re.sub(r'\(\s*\)|\[\s*\]', '', text)
	text = re.sub(r'\s+([.,;:])', r'\1', ' '.join(text.split()))  # the gap that they leave
	return _sentence(re.sub(r'(?<!\.)\.\.(?!\.)', '.', text))


def _articles(par):
	"""[(text, DOI or None)] of a paragraph of sci:citation: one article, or one for each DOI if it has several (cut
	after each of them, so that each article keeps its own)."""
	dois = _dois(par)
	if len(dois) < 2:
		return [(par, dois[0][1] if dois else None)]
	out, start = [], 0
	for i, (end, d) in enumerate(dois):
		end = len(par) if i == len(dois) - 1 else end + len(re.match(r'[).]*', par[end:]).group(0))
		out.append((par[start:end], d))
		start = end
	return out


def _publications(rec):
	"""[(citation, DOI or None)] of the articles of a STAC record: sci:publications and the paragraphs of
	sci:citation (without their DOIs and links, which go to DOI, and without the HTML entities of the records:
	'Mu&ntilde;oz' is 'Muñoz')."""
	out = []
	for p in rec.get('sci:publications') or []:
		if p.get('citation'):
			text = html.unescape(str(p['citation']))
			out.append((_clean(text), _given_doi(p.get('doi')) or next((d for _, d in _dois(text)), None)))
	for par in re.split(r'\n\s*\n', html.unescape(str(rec.get('sci:citation') or ''))):
		for piece, doi in _articles(par):
			text = _clean(piece)
			if not re.search(r'\b(19|20)\d\d\b', text) or text.lower().startswith(('please', 'see ', 'for ')):
				continue  # not a citation (e.g. "Please visit LP DAAC 'Citing Our Data' page")
			if not any(c == text for c, _ in out):
				out.append((text, doi))
	return out


def cite(asset):
	"""What to cite with data of ASSET outside the datasets of catalog.json: (references, credits, methods), with
	references [(id, {'citation', 'doi' or 'url'})] and methods the IDs of catalog.json to cite with them. From its
	STAC record in the Earth Engine data catalog (the articles of sci:citation and sci:publications, and the dataset
	with its DOI, or its page), or its record in the GEE Community Catalog (the dataset with its page, which says how
	to cite it, and the catalog), or else the asset itself."""
	asset = normalize(asset)
	rec, com = stac(asset), community.record(asset)
	refs, credits, methods = [], [], []
	if rec:
		title = ' '.join(str(rec.get('title') or asset).split())
		provider = _provider(rec)
		for i, (citation, doi) in enumerate(_publications(rec), 1):
			refs.append((f'{asset}#{i}', {'citation': citation, 'doi': doi} if doi else {'citation': citation}))
		dataset = _sentence(f"{provider + '. ' if provider else ''}{title} [Dataset]. Earth Engine data catalog, "
		                    f'{asset}')
		doi = _given_doi(rec.get('sci:doi'))
		if doi and not any(r.get('doi') == doi for _, r in refs):
			refs.append((asset, {'citation': dataset, 'doi': doi}))
		elif not refs:
			refs.append((asset, {'citation': dataset, 'url': page(asset)}))
		lic = rec.get('license')
		credits.append(f'{title} ({asset}): licence {lic}' if lic and lic != 'proprietary' else
		               f'{title} ({asset}): terms of use in {page(asset)}#terms-of-use')
	elif com:
		provider = com.get('provider')
		refs.append((asset, {'citation': _sentence(f"{provider + '. ' if provider else ''}{com['title']} [Dataset]. GEE "
		                                           f'Community Catalog, {asset}'), 'url': com.get('docs')}))
		methods = list(community.REFERENCES)
		lic = com.get('license_text') if com.get('license') == 'custom' else com.get('license')
		credits.append(f"{com['title']}{' (' + provider + ')' if provider else ''}: {lic or 'see its page'}")
	elif in_data_catalog(asset):  # its record could not be read (or it has none): its page says how to cite it
		refs.append((asset, {'citation': f'{asset} [Dataset]. Earth Engine data catalog.', 'url': page(asset)}))
		credits.append(f'{asset}: terms of use in {page(asset)}#terms-of-use')
	else:
		refs.append((asset, {'citation': f'Earth Engine asset {asset}.',
		                     'url': f'https://code.earthengine.google.com/?asset={asset}'}))
	return refs, credits, methods


def in_data_catalog(asset):
	"""Whether ASSET is of the Earth Engine data catalog: every ID but those of the users and the projects (users/,
	projects/), as the app says (gee/core.js)."""
	return not re.match(r'(users|projects)/', normalize(asset))


def _gsd(band):
	"""The pixel size (m) of a band of a STAC record (gsd, a number or a list of them), or None."""
	gsd = (band or {}).get('gsd')
	gsd = gsd[0] if isinstance(gsd, list) and gsd else gsd
	return float(gsd) if isinstance(gsd, (int, float)) else None


def _band_stac(rec):
	return {b.get('name'): b for b in ((rec or {}).get('summaries') or {}).get('eo:bands') or []}


def describe(asset):
	"""Everything about the Earth Engine asset ASSET to compute it with the tools (it reads its metadata in Earth
	Engine, without computing): {'asset', 'type', 'use' (the argument that takes it: 'collection' or 'image'), 'how',
	'title', 'source' (Earth Engine data catalog, GEE Community Catalog or other), 'page', 'provider', 'licence',
	'dates', 'cadence', 'theme', 'bands': [{'band', 'description', 'units' (as its record says), 'unit' (in UDUNITS,
	None if unknown), 'band_scale', 'band_offset', 'resolution_m', 'data_type', 'classes'}], 'arguments' (those to
	compute its first band), 'notes', 'references', 'credits'}."""
	from . import references
	asset = normalize(asset)
	meta = info(asset)
	rec, com = stac(asset), community.record(asset)
	by_band = _band_stac(rec)
	bands = []
	# the bands of its first image, then those of its STAC record that it has not (some collections change their bands
	# from image to image, e.g. Sentinel-1: VV and VH, or HH and HV; the tools use the images with the band)
	first = {b['band'] for b in meta['bands']}
	for b in meta['bands'] + [{'band': name, 'resolution_m': _gsd(s), 'data_type': None}
	                          for name, s in by_band.items() if name not in first]:
		s = by_band.get(b['band'], {})
		row = {'band': b['band'], 'description': s.get('description'), 'units': s.get('gee:units'),
		       'unit': udunits(s.get('gee:units')), 'band_scale': s.get('gee:scale'), 'band_offset': s.get('gee:offset'),
		       'resolution_m': b['resolution_m'], 'data_type': b['data_type']}
		if s.get('gee:classes'):
			row['classes'] = {str(c.get('value')): c.get('description') for c in s['gee:classes']}
		if s.get('gee:bitmask'):
			row['bitmask'] = True
		bands.append({k: v for k, v in row.items() if v is not None})
	dated = meta['type'] == 'image_collection' and bool(meta['first_date'])
	use = 'collection' if dated else 'image'
	out = {'asset': asset, 'type': meta['type'], 'use': use}
	if meta['type'] == 'image':
		out['how'] = f"an image: give it as image='{asset}' (a fixed layer, without dates: maps and their statistics)"
	elif dated:
		out['how'] = (f"a collection of images with dates: give it as collection='{asset}' (aggregated in time, with "
		              f"time series, trends and comparisons), or as image='{asset}' for a mosaic of its images without "
		              'dates (a collection of tiles, e.g. a DEM)')
	else:
		out['how'] = (f"a collection of images without dates (tiles): give it as image='{asset}' (their mosaic, a "
		              'fixed layer)')
	notes = ['The pixel filters of MonitorEO (clouds, water, snow, aerosols) are for the variables of its catalog: '
	         'these data keep only their own mask.']
	if rec:
		temporal = (((rec.get('extent') or {}).get('temporal') or {}).get('interval') or [[None, None]])[0]
		iv = rec.get('gee:interval') or {}
		out.update({'title': ' '.join(str(rec.get('title') or '').split()), 'source': 'Earth Engine data catalog',
		            'page': page(asset), 'provider': _provider(rec), 'licence': rec.get('license'),
		            'dates': [str(d)[:10] if d else None for d in temporal],
		            'cadence': f"{iv['interval']} {iv['unit']}" if iv.get('interval') and iv.get('unit') else None})
		if rec.get('deprecated') or rec.get('gee:status') == 'deprecated':
			newer = [l['href'] for l in rec.get('links') or [] if l.get('rel') in ('successor-version', 'latest-version')]
			notes.append('Earth Engine has deprecated this dataset' + (f': see {newer[0]}' if newer else '') + '.')
	elif com:
		out.update({'title': com['title'], 'source': 'GEE Community Catalog', 'page': com.get('docs'),
		            'provider': com.get('provider'), 'theme': com.get('theme'),
		            'licence': com.get('license_text') if com.get('license') == 'custom' else com.get('license'),
		            'dates': [meta['first_date'], None] if dated else None})
		notes.append('The GEE Community Catalog does not give the units, scale and offset of the bands: read them in '
		             'its page, and give them with unit, band_scale and band_offset.')
	elif in_data_catalog(asset):  # of the Earth Engine data catalog, but its record could not be read now
		out.update({'title': asset, 'source': 'Earth Engine data catalog', 'page': page(asset),
		            'dates': [meta['first_date'], None] if dated else None})
		notes.append('Its record in the Earth Engine data catalog (STAC) could not be read: read the units, scale and '
		             'offset of its bands and how to cite it in its page, and give them with unit, band_scale and '
		             'band_offset.')
	else:
		out.update({'title': asset, 'source': 'Earth Engine asset', 'page': None,
		            'dates': [meta['first_date'], None] if dated else None})
		notes.append('Give the unit of its values (unit, in UDUNITS) and, if they are stored scaled, band_scale and '
		             'band_offset.')
	if any(b.get('classes') or b.get('bitmask') for b in bands):
		notes.append('Bands with classes or bit flags (e.g. land cover or quality) are codes, not quantities: use the '
		             'metric mode (or min/max), not the mean or the median.')
	out['bands'] = bands
	first = bands[0] if bands else {}
	out['arguments'] = {k: v for k, v in {use: asset, 'band': first.get('band'), 'band_scale': first.get('band_scale'),
	                                      'band_offset': first.get('band_offset'), 'unit': first.get('unit')}.items()
	                    if v is not None}
	out['notes'] = notes
	out.update(references.of_data(asset))
	return {k: v for k, v in out.items() if v is not None}
