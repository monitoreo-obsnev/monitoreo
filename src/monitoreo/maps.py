"""Maps of a variable: colour ramp, Earth Engine map tiles (XYZ, for QGIS, Leaflet, ...) and PNG thumbnails.

The tiles are computed by Earth Engine as they are viewed, so a map shows without downloading anything. Their URL
is valid for some hours (then ask for a new one).

The true colour of the images of a variable (bands red, green and blue, surface reflectance) is shown with the three
bands stretched together between the lowest of their percentiles 2 and the highest of their percentiles 98 over the
region (rgb_vis): one range for the three, so that the colours keep their balance (a stretch of each band would tint
them).

The PNG previews (thumbnail) are computed by Earth Engine in a single request, which has to end in some minutes. Data
coarser than the pixels of the preview are computed on their own grid (coarse): the mean of 25 years of daily MODIS
(1 km) over an island of 40 km took more than 5 minutes at 768 pixels, and Earth Engine answered HTTP Error 400.
"""

import http.client
import json
import math
import urllib.error
import urllib.request

import ee

from .sensors import RGB_BANDS

DEFAULT_PALETTE = ['000080', '0000FF', '0080FF', '00FFFF', '80FFFF', 'FFFFFF', 'FFFF00', 'FF8000', 'FF0000', '800000']
RGB_STRETCH = (2, 98)  # percentiles of the reflectance of the true colour between which it is stretched
RGB_RANGE = (0.0, 0.3)  # the reflectance of the true colour when it is not computed (quick) or cannot be
PREVIEW_PIXELS = 768  # width or height of the PNG previews
PREVIEW_TIMEOUT = 300  # seconds that Earth Engine has to make a PNG preview


def ramp(entry=None, colours=None):
	"""Colours (hex, without #) of the ramp of a catalog ENTRY (pm), or COLOURS, or DEFAULT_PALETTE."""
	return [str(c).lstrip('#') for c in (colours or (entry or {}).get('pm') or DEFAULT_PALETTE)]


def vis_params(image, region_geom, entry=None, scale=None, vmin=None, vmax=None, palette=None, compute=True):
	"""Colour ramp of a single band image ('value'): from the percentiles 5 and 95 of the image over
	REGION_GEOM (or VMIN and VMAX), with the palette of the catalog entry ENTRY (pm) or PALETTE. Without COMPUTE,
	or if Earth Engine cannot compute them (big regions and long periods run out of memory), the range of ENTRY."""
	if vmin is None or vmax is None:
		st = {}
		if compute:
			try:
				st = ee.Image(image).reduceRegion(ee.Reducer.percentile([5, 95]), region_geom, scale, bestEffort=True,
				                                  maxPixels=int(1e6)).getInfo()
			except ee.EEException:
				st = {}
		lo, hi = st.get('value_p5'), st.get('value_p95')
		if lo is None or hi is None:
			lo = (entry or {}).get('minp', 0) if isinstance((entry or {}).get('minp'), (int, float)) else 0
			hi = (entry or {}).get('maxp', 1) if isinstance((entry or {}).get('maxp'), (int, float)) else 1
		vmin = lo if vmin is None else vmin
		vmax = hi if vmax is None else vmax
	if vmax == vmin:
		vmax = vmin + 1e-6
	return {'min': float(vmin), 'max': float(vmax), 'palette': ramp(entry, palette)}


def rgb_vis(image, region_geom, scale=None, vmin=None, vmax=None, compute=True):
	"""Visualization of the true colour IMAGE (bands red, green and blue: reflectance): the three bands stretched
	together between VMIN and VMAX, by default the lowest percentile 2 and the highest percentile 98 of the bands over
	REGION_GEOM (see RGB_STRETCH). Without COMPUTE, or if Earth Engine cannot compute them, RGB_RANGE.
	Returns {'bands', 'min', 'max'} (the min and max of the three bands)."""
	if vmin is None or vmax is None:
		st = {}
		lo_p, hi_p = RGB_STRETCH
		if compute:
			try:
				# tileScale 4, as the Earth Engine app (gee/core.js rgbPercentiles): the percentiles of Earth Engine are
				# approximate, and the tiles change them a little; smaller tiles also need less memory (four bands)
				st = ee.Image(image).select(RGB_BANDS).reduceRegion(ee.Reducer.percentile([lo_p, hi_p]), region_geom,
				                                                    scale, bestEffort=True, maxPixels=int(1e6),
				                                                    tileScale=4).getInfo()
			except ee.EEException:
				st = {}
		lows = [st.get(f'{b}_p{lo_p}') for b in RGB_BANDS]
		highs = [st.get(f'{b}_p{hi_p}') for b in RGB_BANDS]
		if any(v is None for v in lows + highs):
			lo, hi = RGB_RANGE
		else:
			lo, hi = min(lows), max(highs)
		vmin = lo if vmin is None else vmin
		vmax = hi if vmax is None else vmax
	if vmax <= vmin:
		vmax = vmin + 1e-6
	return {'bands': list(RGB_BANDS), 'min': float(vmin), 'max': float(vmax)}


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


def thumbnail(image, region_geom, vis=None, dimensions=PREVIEW_PIXELS, path=None):
	"""PNG (bytes) of IMAGE over REGION_GEOM, coloured with VIS (None if IMAGE is already RGB). ee.EEException with
	the message of Earth Engine if it cannot make it, or does not in PREVIEW_TIMEOUT seconds."""
	img = ee.Image(image).visualize(**vis) if vis else ee.Image(image)
	url = img.getThumbURL({'region': region_geom, 'dimensions': int(dimensions), 'format': 'png'})
	if not url.startswith('https://'):
		raise ValueError(f'Earth Engine gave a thumbnail URL that is not https: {url}')
	try:
		# only https (checked above): the warning of Bandit about file:/ and other schemes does not apply
		with urllib.request.urlopen(url, timeout=PREVIEW_TIMEOUT) as r:  # nosec B310
			png = r.read()
	except urllib.error.HTTPError as e:  # before OSError (an HTTPError is one): its body says why
		raise ee.EEException(f'Earth Engine could not make the PNG preview: {earth_engine_error(e)}') from e
	except http.client.HTTPException as e:  # the connection cut while the PNG came (IncompleteRead, BadStatusLine)
		raise ee.EEException(f'Earth Engine could not send the PNG preview: {e!r}') from e
	except (TimeoutError, urllib.error.URLError) as e:
		if isinstance(e, TimeoutError) or isinstance(getattr(e, 'reason', None), TimeoutError):
			raise ee.EEException(f'Earth Engine did not make the PNG preview in {PREVIEW_TIMEOUT // 60} minutes') from e
		raise
	if path:
		with open(path, 'wb') as f:
			f.write(png)
	return png
