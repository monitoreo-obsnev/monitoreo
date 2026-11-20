"""Maps of a variable: colour ramp, Earth Engine map tiles (XYZ, for QGIS, Leaflet, ...) and PNG thumbnails.

The tiles are computed by Earth Engine as they are viewed, so a map shows without downloading anything. Their URL
is valid for some hours (then ask for a new one).

The true colour of the images of a variable (bands red, green and blue, surface reflectance) is shown with the three
bands stretched together between the lowest of their percentiles 2 and the highest of their percentiles 98 over the
region (rgb_vis): one range for the three, so that the colours keep their balance (a stretch of each band would tint
them).

The colour ramp of every other map (vis_params) is stretched between the percentiles 1 and 99 of its values over the
region (STRETCH), each map with its own: the map of each step of a series and each frame of an animation too
(frame_ranges). The user can give other percentiles, or the minimum and the maximum (vmin, vmax). The maps of classes
(land cover, ecoregions, burn severity) keep the colour of each class.

The PNG previews (thumbnail) are computed by Earth Engine in a single request, which has to end in some minutes. Data
coarser than the pixels of the preview are computed on their own grid (coarse): the mean of 25 years of daily MODIS
(1 km) over an island of 40 km took more than 5 minutes at 768 pixels, and Earth Engine answered HTTP Error 400.
"""

import http.client
import json
import math
import re
import urllib.error
import urllib.request

import ee

from .sensors import RGB_BANDS

DEFAULT_PALETTE = ['000080', '0000FF', '0080FF', '00FFFF', '80FFFF', 'FFFFFF', 'FFFF00', 'FF8000', 'FF0000', '800000']
STRETCH = (1, 99)  # percentiles of the values of a map between which its colour ramp is stretched (default)
RGB_STRETCH = (2, 98)  # percentiles of the reflectance of the true colour between which it is stretched
RGB_RANGE = (0.0, 0.3)  # the reflectance of the true colour when it is not computed (quick) or cannot be
PREVIEW_PIXELS = 768  # width or height of the PNG previews
PREVIEW_TIMEOUT = 300  # seconds that Earth Engine has to make a PNG preview


def ramp(entry=None, colours=None):
	"""Colours (hex, without #) of the ramp of a catalog ENTRY (pm), or COLOURS, or DEFAULT_PALETTE."""
	return [str(c).lstrip('#') for c in (colours or (entry or {}).get('pm') or DEFAULT_PALETTE)]


def check_percentiles(percentiles, default=None):
	"""The two percentiles (lo, hi) of PERCENTILES (a list or tuple of two numbers, or a text such as '1,99' or '2 98')
	between which a colour ramp is stretched, 0 <= lo < hi <= 100; DEFAULT (STRETCH if None) without them. ValueError
	otherwise."""
	if percentiles is None or percentiles == '' or percentiles == []:
		return tuple(default or STRETCH)
	if isinstance(percentiles, str):
		percentiles = [x for x in re.split(r'[\s,;]+', percentiles.strip()) if x]
	try:
		lo, hi = (float(x) for x in percentiles)
	except (TypeError, ValueError):
		raise ValueError(f'percentiles must be two numbers between 0 and 100, e.g. [1, 99], not {percentiles!r}') from None
	if not (0 <= lo < hi <= 100):
		raise ValueError(f'percentiles must be two numbers 0 <= low < high <= 100, e.g. [1, 99], not [{lo:g}, {hi:g}]')
	return (int(lo) if lo == int(lo) else lo, int(hi) if hi == int(hi) else hi)


def _reducer(lo_p, hi_p):
	"""The percentiles LO_P and HI_P, named lo and hi (value_lo, value_hi: those of Earth Engine for a percentile with
	decimals are not obvious)."""
	return ee.Reducer.percentile([lo_p, hi_p], ['lo', 'hi'])


def stretch_of(computed, percentiles, vmin_given, vmax_given, catalog=False, symmetric=False):
	"""How a colour ramp was stretched, for the legend and the README: {'method' ('percentiles', 'given', 'catalog' or
	'mixed': one end given), 'percentiles' ([lo, hi], when they were used), 'given' ('min' or 'max', when mixed),
	'catalog' (mixed: the other end from the range of the catalog), 'symmetric' (around 0, up to the largest of the
	percentiles in absolute value: trends and differences), 'over' (COMPUTED: what the percentiles are of), 'text'}
	(see stretch_text)."""
	lo_p, hi_p = percentiles
	if vmin_given and vmax_given:
		out = {'method': 'given'}
	elif vmin_given or vmax_given:
		out = {'method': 'mixed', 'given': 'min' if vmin_given else 'max'}
		if catalog:
			out['catalog'] = True
		else:
			out['percentiles'] = [lo_p, hi_p]
	elif catalog:
		out = {'method': 'catalog'}
	else:
		out = {'method': 'percentiles', 'percentiles': [lo_p, hi_p]}
	if symmetric and out.get('percentiles'):
		out['symmetric'] = True
	if computed is not None:
		out['over'] = computed
	out['text'] = stretch_text(out)
	return out


CATALOG_TEXT = ('the range of the variable in the catalog of MonitorEO (the percentiles of the map were not computed: '
                'quick map, or Earth Engine could not compute them)')


def stretch_text(stretch):
	"""The range of a colour ramp in words, from STRETCH (see stretch_of), e.g. «stretched between the percentiles 1
	and 99 of the values of the map over the region»; '' without it."""
	if not isinstance(stretch, dict):
		return ''
	m, (lo, hi) = stretch.get('method'), (stretch.get('percentiles') or [None, None])
	over = stretch.get('over') or 'the values of the map over the region'
	symmetric = (f'symmetric around 0, up to the largest in absolute value of the percentiles {lo:g} and {hi:g} of '
	             f'{over}' if stretch.get('symmetric') and lo is not None else '')
	if m == 'given':
		return 'range given by the user (vmin and vmax)'
	if m == 'catalog':
		return CATALOG_TEXT[len('the '):]
	if m == 'mixed':
		end = 'minimum' if stretch.get('given') == 'min' else 'maximum'
		if stretch.get('catalog'):
			return f'{end} given by the user, the other end from {CATALOG_TEXT}'
		if symmetric:
			return f'{end} given by the user, the other end {symmetric}'
		other = f'percentile {hi:g}' if stretch.get('given') == 'min' else f'percentile {lo:g}'
		return f'{end} given by the user, the other end the {other} of {over}'
	if m == 'percentiles' and lo is not None:
		return symmetric or f'stretched between the percentiles {lo:g} and {hi:g} of {over}'
	return ''


def ordered(vmin, vmax, given=(False, False), what='the map'):
	"""(VMIN, VMAX) of a colour ramp, the maximum above the minimum: with only one end given by the user (GIVEN: whether
	each one was) that crosses the other, from the percentiles, a ValueError that says so (the ramp would be painted
	the other way round); the same values otherwise, VMAX a little above VMIN when they are equal."""
	if vmin is not None and vmax is not None and vmax <= vmin and given[0] != given[1]:
		end, value, other = ('minimum', vmin, vmax) if given[0] else ('maximum', vmax, vmin)
		raise ValueError(f'the {end} of the colours given, {value:g}, is beyond the other end of the colours of '
		                 f'{what} ({other:g}): give both the minimum and the maximum (vmin and vmax), or other '
		                 'percentiles')
	if vmin is not None and vmax is not None and vmax == vmin:
		vmax = vmin + 1e-6
	return vmin, vmax


def vis_params(image, region_geom, entry=None, scale=None, vmin=None, vmax=None, palette=None, compute=True,
               percentiles=None, describe=False):
	"""Colour ramp of a single band image ('value'): from the PERCENTILES (by default STRETCH, 1 and 99) of the image
	over REGION_GEOM, or VMIN and VMAX (either of them, the other end from its percentile), with the palette of the
	catalog entry ENTRY (pm) or PALETTE. Without COMPUTE, or if Earth Engine cannot compute them (big regions and long
	periods run out of memory), the range of ENTRY. With DESCRIBE, (the ramp, how it was stretched: see stretch_of)."""
	lo_p, hi_p = check_percentiles(percentiles)
	catalog = False
	if vmin is None or vmax is None:
		st = {}
		if compute:
			try:
				# tileScale 4, as the Earth Engine app (gee/core.js): without it, the median of some years of
				# Sentinel-2 over a few km runs out of memory, and the ramp was that of the catalog
				st = ee.Image(image).reduceRegion(_reducer(lo_p, hi_p), region_geom, scale,
				                                  bestEffort=True, maxPixels=int(1e6), tileScale=4).getInfo() or {}
			except ee.EEException:
				st = {}
		lo, hi = st.get('value_lo'), st.get('value_hi')
		if lo is None or hi is None:
			catalog = True
			lo = (entry or {}).get('minp', 0) if isinstance((entry or {}).get('minp'), (int, float)) else 0
			hi = (entry or {}).get('maxp', 1) if isinstance((entry or {}).get('maxp'), (int, float)) else 1
		given = (vmin is not None, vmax is not None)
		vmin = lo if vmin is None else vmin
		vmax = hi if vmax is None else vmax
	else:
		given = (True, True)
	vmin, vmax = ordered(vmin, vmax, given)
	vis = {'min': float(vmin), 'max': float(vmax), 'palette': ramp(entry, palette)}
	if describe:
		return vis, stretch_of(None, (lo_p, hi_p), *given, catalog=catalog)
	return vis


def frame_ranges(images, region_geom, scale=None, percentiles=None):
	"""The percentiles (lo, hi) of each single band image of IMAGES ('value') over REGION_GEOM, in a single request
	(the colour ramp of each frame of an animation, of each step of a series): [(lo, hi) or (None, None) for an image
	without values]; [(None, None), ...] if Earth Engine cannot compute them."""
	lo_p, hi_p = check_percentiles(percentiles)
	reducer = _reducer(lo_p, hi_p)
	stats = ee.List([ee.Image(img).reduceRegion(reducer, region_geom, scale, bestEffort=True, maxPixels=int(1e6),
	                                            tileScale=4) for img in images])
	try:
		got = stats.getInfo()
	except ee.EEException:
		return [(None, None)] * len(images)
	return [((d or {}).get('value_lo'), (d or {}).get('value_hi')) for d in got]


def frame_stretch(ranges, percentiles, vmin_given, vmax_given, what='frame'):
	"""How the colours of the frames (or maps of each step) with their RANGES (see frame_ranges) were stretched: each
	between the PERCENTILES of its own values (stretch_of, per_frame), those without them (a frame without values, or
	all if Earth Engine could not compute them) with the range of the catalog: 'catalog' for all, or the frames that
	took it (catalog_frames, numbered from 1) and said in its text."""
	missing = [i + 1 for i, (lo, hi) in enumerate(ranges) if lo is None or hi is None]
	every = bool(ranges) and len(missing) == len(ranges)
	out = stretch_of(f'the values of each {what} over the region', percentiles, vmin_given, vmax_given,
	                 catalog=every)
	out['per_frame'] = True
	if not out['method'] == 'given':
		if every:
			out['text'] += f' (for every {what})'
		else:
			out['text'] += f': each {what} has its own range, written next to it'
			if missing:
				out['catalog_frames'] = missing
				out['text'] += (f"; {what}s {', '.join(map(str, missing))} (without values) have the range of the "
				                'variable in the catalog')
	return out


def rgb_vis(image, region_geom, scale=None, vmin=None, vmax=None, compute=True, percentiles=None, describe=False):
	"""Visualization of the true colour IMAGE (bands red, green and blue: reflectance): the three bands stretched
	together between VMIN and VMAX, by default the lowest of their PERCENTILES low and the highest of their PERCENTILES
	high over REGION_GEOM (by default RGB_STRETCH, 2 and 98). Without COMPUTE, or if Earth Engine cannot compute them,
	RGB_RANGE. Returns {'bands', 'min', 'max'} (the min and max of the three bands); with DESCRIBE, (that, how it was
	stretched: see stretch_of)."""
	lo_p, hi_p = check_percentiles(percentiles, RGB_STRETCH)
	catalog = False
	given = (vmin is not None, vmax is not None)
	if vmin is None or vmax is None:
		st = {}
		if compute:
			try:
				# tileScale 4, as the Earth Engine app (gee/core.js rgbPercentiles): the percentiles of Earth Engine are
				# approximate, and the tiles change them a little; smaller tiles also need less memory (four bands)
				st = ee.Image(image).select(RGB_BANDS).reduceRegion(_reducer(lo_p, hi_p), region_geom,
				                                                    scale, bestEffort=True, maxPixels=int(1e6),
				                                                    tileScale=4).getInfo() or {}
			except ee.EEException:
				st = {}
		lows = [st.get(f'{b}_lo') for b in RGB_BANDS]
		highs = [st.get(f'{b}_hi') for b in RGB_BANDS]
		if any(v is None for v in lows + highs):
			lo, hi = RGB_RANGE
			catalog = True
		else:
			lo, hi = min(lows), max(highs)
		vmin = lo if vmin is None else vmin
		vmax = hi if vmax is None else vmax
	vmin, vmax = ordered(vmin, vmax, given, 'the true colour')
	if vmax <= vmin:
		vmax = vmin + 1e-6
	vis = {'bands': list(RGB_BANDS), 'min': float(vmin), 'max': float(vmax)}
	if describe:
		stretch = stretch_of('the red, green and blue reflectance of the map over the region (one range for the '
		                     'three bands)', (lo_p, hi_p), *given)
		if catalog and not all(given):
			fixed = (f'reflectance from {RGB_RANGE[0]:g} to {RGB_RANGE[1]:g} (the percentiles were not computed: quick '
			         'map, or Earth Engine could not compute them)')
			stretch = {'method': 'catalog', 'text': fixed} if not any(given) else {
				'method': 'mixed', 'given': 'min' if given[0] else 'max', 'catalog': True,
				'text': f"{'minimum' if given[0] else 'maximum'} given by the user, the other end that of the "
				        f'{fixed}'}
		return vis, stretch
	return vis


def tile_url(image, vis):
	"""URL template of the Earth Engine map tiles of IMAGE with VIS ({z}/{x}/{y}, web Mercator)."""
	return ee.Image(image).getMapId(vis)['tile_fetcher'].url_format


def with_outline(image, vis, regions, color='000000', width=2):
	"""IMAGE coloured with VIS and the outline of REGIONS drawn on top (an RGB image)."""
	outline = ee.Image().byte().paint(regions, 1, width).visualize(palette=[color])
	return ee.Image(image).visualize(**vis).blend(outline)


def coarse(image, scale, bounds, dimensions=PREVIEW_PIXELS):
	"""IMAGE computed on a grid of SCALE metres (the pixels of its data) when they are bigger than the pixels of a
	preview of DIMENSIONS over BOUNDS ([w, s, e, n], degrees): Earth Engine then computes each pixel of the data once,
	instead of each pixel of the preview (hundreds of times fewer for MODIS or ERA5-Land over a small region), and the
	preview shows the pixels of the data. IMAGE as it is otherwise, or without SCALE or BOUNDS. IMAGE should not be
	clipped to the region yet: its clip would be computed on that grid too (a region smaller than a pixel would get a
	faint pixel); clip what this returns instead, on the pixels of the preview."""
	if not scale or not bounds:
		return image
	w, s, e, n = bounds
	size = max((e - w) * 111320 * math.cos(math.radians((s + n) / 2)), (n - s) * 110574)  # metres
	if float(scale) * int(dimensions) <= size:
		return image
	return ee.Image(image).reproject(ee.Projection('EPSG:4326').atScale(float(scale)))


def earth_engine_error(error):
	"""The message of Earth Engine in the HTTPError ERROR of a request of its PNG (its body: {"error": {"message"}}),
	or the error itself."""
	try:
		body = error.read().decode('utf-8', 'replace')
	except (OSError, ValueError, AttributeError, http.client.HTTPException):  # a body cut short, too
		body = ''
	try:
		message = json.loads(body)['error']['message']
	except (ValueError, KeyError, TypeError):
		message = body.strip()[:300]
	return message or str(error)


def thumbnail(image, region_geom, vis=None, dimensions=PREVIEW_PIXELS, path=None, crs=None):
	"""PNG (bytes) of IMAGE over REGION_GEOM, coloured with VIS (None if IMAGE is already RGB), in CRS (by default that
	of Earth Engine for thumbnails). ee.EEException with the message of Earth Engine if it cannot make it, or does not
	in PREVIEW_TIMEOUT seconds."""
	img = ee.Image(image).visualize(**vis) if vis else ee.Image(image)
	params = {'region': region_geom, 'dimensions': int(dimensions), 'format': 'png'}
	if crs:
		params['crs'] = crs
	url = img.getThumbURL(params)
	png = fetch(url, 'the PNG preview')
	if path:
		with open(path, 'wb') as f:
			f.write(png)
	return png


def fetch(url, what='the PNG preview', timeout=PREVIEW_TIMEOUT):
	"""The bytes of a picture that Earth Engine makes at URL (a thumbnail, or the GIF of an animation: WHAT, for the
	messages). ee.EEException with the message of Earth Engine if it cannot make it, or does not in TIMEOUT seconds."""
	if not url.startswith('https://'):
		raise ValueError(f'Earth Engine gave a thumbnail URL that is not https: {url}')
	try:
		# only https (checked above): the warning of Bandit about file:/ and other schemes does not apply
		with urllib.request.urlopen(url, timeout=timeout) as r:  # nosec B310
			return r.read()
	except urllib.error.HTTPError as e:  # before OSError (an HTTPError is one): its body says why
		raise ee.EEException(f'Earth Engine could not make {what}: {earth_engine_error(e)}') from e
	except http.client.HTTPException as e:  # the connection cut while the picture came (IncompleteRead, BadStatusLine)
		raise ee.EEException(f'Earth Engine could not send {what}: {e!r}') from e
	except (TimeoutError, urllib.error.URLError) as e:
		if isinstance(e, TimeoutError) or isinstance(getattr(e, 'reason', None), TimeoutError):
			raise ee.EEException(f'Earth Engine did not make {what} in {timeout // 60} minutes') from e
		raise
