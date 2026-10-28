"""Maps of a variable: colour ramp, Earth Engine map tiles (XYZ, for QGIS, Leaflet, ...) and PNG thumbnails.

The tiles are computed by Earth Engine as they are viewed, so a map shows without downloading anything. Their URL
is valid for some hours (then ask for a new one).
"""

import urllib.request

import ee

DEFAULT_PALETTE = ['000080', '0000FF', '0080FF', '00FFFF', '80FFFF', 'FFFFFF', 'FFFF00', 'FF8000', 'FF0000', '800000']


def vis_params(image, region_geom, entry=None, scale=None, vmin=None, vmax=None, palette=None):
	"""Colour ramp of a single band image ('value'): as MonitorEO, from the percentiles 5 and 95 of the image over
	REGION_GEOM (or VMIN and VMAX), with the palette of the catalog entry ENTRY (pm) or PALETTE."""
	if vmin is None or vmax is None:
		st = ee.Image(image).reduceRegion(ee.Reducer.percentile([5, 95]), region_geom, scale, bestEffort=True,
		                                  maxPixels=int(1e6)).getInfo()
		lo, hi = st.get('value_p5'), st.get('value_p95')
		if lo is None or hi is None:
			lo = (entry or {}).get('minp', 0) if isinstance((entry or {}).get('minp'), (int, float)) else 0
			hi = (entry or {}).get('maxp', 1) if isinstance((entry or {}).get('maxp'), (int, float)) else 1
		vmin = lo if vmin is None else vmin
		vmax = hi if vmax is None else vmax
	if vmax == vmin:
		vmax = vmin + 1e-6
	palette = palette or (entry or {}).get('pm') or DEFAULT_PALETTE
	return {'min': float(vmin), 'max': float(vmax), 'palette': [str(c).lstrip('#') for c in palette]}


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
	with urllib.request.urlopen(url, timeout=300) as r:
		png = r.read()
	if path:
		with open(path, 'wb') as f:
			f.write(png)
	return png
