"""Maps of a variable: colour ramp, Earth Engine map tiles (XYZ, for QGIS, Leaflet, ...) and PNG thumbnails.

The tiles are computed by Earth Engine as they are viewed, so a map shows without downloading anything. Their URL
is valid for some hours (then ask for a new one).

The true colour of the images of a variable (bands red, green and blue, surface reflectance) is shown with the three
bands stretched together between the lowest of their percentiles 2 and the highest of their percentiles 98 over the
region (rgb_vis): one range for the three, so that the colours keep their balance (a stretch of each band would tint
them).
"""

import urllib.request

import ee

from .sensors import RGB_BANDS

DEFAULT_PALETTE = ['000080', '0000FF', '0080FF', '00FFFF', '80FFFF', 'FFFFFF', 'FFFF00', 'FF8000', 'FF0000', '800000']
RGB_STRETCH = (2, 98)  # percentiles of the reflectance of the true colour between which it is stretched
RGB_RANGE = (0.0, 0.3)  # the reflectance of the true colour when it is not computed (quick) or cannot be


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
				st = ee.Image(image).select(RGB_BANDS).reduceRegion(ee.Reducer.percentile([lo_p, hi_p]), region_geom,
				                                                    scale, bestEffort=True, maxPixels=int(1e6)).getInfo()
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


def thumbnail(image, region_geom, vis=None, dimensions=768, path=None):
	"""PNG (bytes) of IMAGE over REGION_GEOM, coloured with VIS (None if IMAGE is already RGB)."""
	img = ee.Image(image).visualize(**vis) if vis else ee.Image(image)
	url = img.getThumbURL({'region': region_geom, 'dimensions': int(dimensions), 'format': 'png'})
	if not url.startswith('https://'):
		raise ValueError(f'Earth Engine gave a thumbnail URL that is not https: {url}')
	# only https (checked above): the warning of Bandit about file:/ and other schemes does not apply
	with urllib.request.urlopen(url, timeout=300) as r:  # nosec B310
		png = r.read()
	if path:
		with open(path, 'wb') as f:
			f.write(png)
	return png
