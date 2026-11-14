"""MonitorEO in Jupyter and Google Colab notebooks, on the interactive maps of geemap (Wu, 2020): the maps of the
variables of MonitorEO (with its pixel filters, where, land cover masks, metrics and colour ramps), the comparison of
two periods on a split map and the maps of each year or month with a time slider, each with its colour bar, the
outline of the region and the credits of the data. It needs geemap, the extra notebook of the package:

    pip install "monitoreo[notebook] @ https://github.com/monitoreo-obsnev/monitoreo/archive/refs/heads/main.zip"

    import monitoreo.services as mo
    from monitoreo import notebook
    mo.init()  # or mo.init('my-ee-project')
    m = notebook.Map()
    notebook.add_map(m, {'wdpa_id': 389011}, 'NDVI', 'Sentinel-2', '2023-06-01', '2023-08-31')
    m

It computes in Google Earth Engine as monitoreo.services (the same functions), and each function returns what to cite
with the map: its references (with DOI) and credits (monitoreo.references). The images of Earth Engine of the maps are
services.composite_image, which also goes to geemap, rgee or the Code Editor directly.

    Wu, Q. (2020). geemap: A Python package for interactive mapping with Google Earth Engine. Journal of Open Source
      Software, 5(51), 2305. https://doi.org/10.21105/joss.02305
"""

import ee

from . import animation, maps, references, services, timeseries
from . import variable as variables
from .publish import unit_text

GEEMAP = 'wu2020'  # the reference of geemap in the catalog
INSTALL = ('the maps of notebooks need geemap: pip install "monitoreo[notebook] @ '
           'https://github.com/monitoreo-obsnev/monitoreo/archive/refs/heads/main.zip" (or pip install geemap)')


def _geemap():
	try:
		import geemap
	except ImportError:
		raise ValueError(INSTALL) from None
	return geemap


def Map(**kwargs):
	"""An interactive map of geemap (geemap.Map, with its KWARGS) for the maps of MonitorEO."""
	return _geemap().Map(**kwargs)


def _cited(tool, args):
	"""{'references', 'credits'} of a map of TOOL with ARGS (see monitoreo.references.cite) and that of geemap (Wu, 2020),
	with which the maps are drawn."""
	cited = references.cite(tool, {k: v for k, v in args.items() if v is not None})
	if not any(r['id'] == GEEMAP for r in cited['references']):
		cited['references'] = sorted(cited['references'] + [references.get(GEEMAP)], key=references._sort_key)
	return cited


def _outline(m, regions, name='Region'):
	m.add_layer(ee.Image().byte().paint(regions, 1, 2), {'palette': ['000000']}, name)


def _credits(m, cited, position='bottomleft'):
	"""The credits of the data and MonitorEO, on the map M."""
	text = ' · '.join(list(cited.get('credits') or []) + ['MonitorEO', 'Google Earth Engine'])
	m.add_text(text, fontsize=9, padding='2px', position=position)


def add_map(m, region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
            interannual='mean', season=None, quality=None, vmin=None, vmax=None, palette=None, name=None,
            colorbar=True, outline=True, credits=True, center=True, **source):
	"""Add to the map of geemap M the map of a variable over REGION as services.map_layer computes it (the same
	arguments: METRIC, TEMPORAL, INTERANNUAL, SEASON, QUALITY, where, the data of Earth Engine by their ID...), coloured
	with its ramp (VMIN to VMAX; by default the percentiles 5 and 95 of the map), named NAME (default: that of the map),
	with its colour bar and unit (COLORBAR), the outline of the region (OUTLINE) and the credits of the data (CREDITS),
	centred on the region (CENTER).
	Returns {'name', 'min', 'max', 'palette', 'unit', 'references', 'credits'}."""
	spec, regions, whole, res = services._build(region, variable, sensor, start, end, metric, temporal, interannual,
	                                            season, quality, False, None, source)
	img = whole.clipToCollection(regions)
	vis = maps.vis_params(img, regions.geometry(), services.ramp_entry(spec), res, vmin, vmax, palette)
	name = name or services._named(spec, metric)
	unit = unit_text(services._unit(spec))
	m.add_layer(img, vis, name)
	if outline:
		_outline(m, regions)
	if colorbar:
		m.add_colorbar(vis_params=vis, label=f'{name} ({unit})' if unit else name, layer_name=name)
	cited = _cited('map_layer', dict(source, region=region, variable=variable, sensor=sensor, start=start, end=end,
	                                 metric=metric, temporal=temporal, interannual=interannual, season=season,
	                                 quality=quality))
	if credits:
		_credits(m, cited)
	if center:
		m.center_object(regions)
	return dict(vis, name=name, unit=services._unit(spec), **cited)


def compare(region, variable=None, sensor=None, start=None, end=None, other_start=None, other_end=None,
            metric='median', temporal='period', interannual='mean', season=None, quality=None, vmin=None, vmax=None,
            palette=None, credits=True, **source):
	"""A split map of geemap (as compare_map, but the two periods side by side): the map of the reference period (START
	to END) on the left and that of the other one (OTHER_START to OTHER_END) on the right, with the same colours (by
	default from the percentiles 5 and 95 of both or, if Earth Engine cannot compute them or there are no pixels, the
	range of the catalog), their colour bar and unit, the outline of the region and the credits of the data.
	Returns (the map of geemap, {'min', 'max', 'palette', 'unit', 'references', 'credits'})."""
	geemap = _geemap()
	spec = services.make_spec(variable, sensor, start, end, metric=metric, temporal=temporal, interannual=interannual,
	                          season=season, quality=quality, **source)
	variables.check_dates(spec, 'comparisons of periods')
	regions, img, native, _ = services._comparison(region, variable, sensor, start, end, other_start, other_end, metric,
	                                               temporal, interannual, season, quality, None, source)[1:5]
	geom = regions.geometry()
	both = img.select('reference').addBands(img.select('other'))
	if vmin is None or vmax is None:
		try:  # as maps.vis_params: big regions and long periods run out of memory
			st = both.reduceRegion(ee.Reducer.percentile([5, 95]), geom, native, bestEffort=True, maxPixels=int(1e6),
			                       tileScale=4).getInfo() or {}
		except ee.EEException:
			st = {}
		lows = [v for k, v in st.items() if k.endswith('_p5') and v is not None]
		highs = [v for k, v in st.items() if k.endswith('_p95') and v is not None]
		if vmin is None and lows:
			vmin = min(lows)
		if vmax is None and highs:
			vmax = max(highs)
	# what is still None (no pixels in both periods), the range of the catalog
	vis = maps.vis_params(None, None, services.ramp_entry(spec), native, vmin, vmax, palette, compute=False)
	left, right = ' / '.join(spec['period']), f'{other_start} / {other_end}'  # as computed (no END: today)
	m = geemap.Map()
	m.split_map(left_layer=geemap.ee_tile_layer(img.select('reference').clipToCollection(regions), vis, left),
	            right_layer=geemap.ee_tile_layer(img.select('other').clipToCollection(regions), vis, right),
	            left_label=left, right_label=right)
	_outline(m, regions)
	name = services._named(dict(spec, period=None), metric)
	unit = unit_text(services._unit(spec))
	m.add_colorbar(vis_params=vis, label=f'{name} ({unit})' if unit else name)
	m.center_object(regions)
	cited = _cited('compare_map', dict(source, region=region, variable=variable, sensor=sensor, start=start, end=end,
	                                   other_start=other_start, other_end=other_end, metric=metric, temporal=temporal,
	                                   interannual=interannual, season=season, quality=quality))
	if credits:
		_credits(m, cited, 'bottomright')
	return m, dict(vis, unit=services._unit(spec), **cited)


def time_slider(m, region, variable=None, sensor=None, start=None, end=None, step='annual', metric='median',
                season=None, quality=None, vmin=None, vmax=None, palette=None, name=None, colorbar=True, credits=True,
                **source):
	"""Add to the map of geemap M the maps of each STEP ('annual', 'monthly' or '16-day') of the period of a variable
	over REGION with a time slider (as the frames of timelapse: the METRIC of the images of each step, with the colours
	of the map of the whole period), its colour bar and the credits of the data.
	Returns {'name', 'labels' (the date of each map), 'min', 'max', 'palette', 'unit', 'references', 'credits'}."""
	if step not in animation.STEPS[:3]:
		raise ValueError(f"unknown step {step}: use {', '.join(animation.STEPS[:3])}")
	spec = services.make_spec(variable, sensor, start, end, metric=metric, season=season, quality=quality, **source)
	variables.check_dates(spec, 'time sliders')
	steps = timeseries.bins(spec, step)
	animation.check(step, len(steps))
	regions = services.areas.region(region)
	geom = regions.geometry()
	res = variables.native_scale(spec)
	whole = variables.image(spec, geom, res).clipToCollection(regions)
	vis = maps.vis_params(whole, geom, services.ramp_entry(spec), res, vmin, vmax, palette)
	col = variables.collection(spec, geom, res)
	imgs = [services.composite._reduce(col.filterDate(a, b), metric).clipToCollection(regions)
	        .set('system:time_start', ee.Date(a).millis()) for a, b in steps]
	labels = [animation.label(step, a, b) for a, b in steps]
	name = name or services._named(spec, metric)
	unit = unit_text(services._unit(spec))
	m.add_time_slider(ee.ImageCollection.fromImages(imgs), vis, layer_name=name, labels=labels, time_interval=1)
	_outline(m, regions)
	if colorbar:
		m.add_colorbar(vis_params=vis, label=f'{name} ({unit})' if unit else name)
	cited = _cited('timelapse', dict(source, region=region, variable=variable, sensor=sensor, start=start, end=end,
	                                 step=step, metric=metric, season=season, quality=quality))
	if credits:
		_credits(m, cited)
	m.center_object(regions)
	return dict(vis, name=name, labels=labels, unit=services._unit(spec), **cited)
