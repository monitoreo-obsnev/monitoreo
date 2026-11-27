"""MonitorEO panel: region, variable, period and pixel filters, and the buttons of the time series, the map layer (the
map of the variable, the true colour of its images or both) and the exports to Google Drive; in the theme Fire, the
burn severity of a fire. Instead of a variable of the catalog, in the themes Earth Engine data (by its ID) and GEE
Community Catalog: any image or collection of images of Earth Engine given by its ID (read with
services.describe_asset), or a dataset of the GEE Community Catalog chosen by its themes (community_themes,
community_datasets). The work runs in QGIS tasks (QgsTask), so QGIS keeps responding; every computation is a
function of monitoreo.services, the same as in the MCP server and the R package. The button Projects… lists the Google
Cloud projects of the user's account registered in Earth Engine (services.own_projects), to choose one, and the
message bar warns when Earth Engine has put the project in restricted mode (quota_text: it has spent its
noncommercial compute quota, so computations are slow and may fail).
The parameters of each analysis (monitoreo.parameters: the JSON of the function of monitoreo.services and its
arguments, the same in every tool) are copied or saved by the button Parameters beside its button, from the arguments
that its button computes with; Apply parameters pastes or opens them and fills the fields of the panel, without
computing anything, and says what it could not apply."""

import inspect
import json
import os
import re
import tempfile

from qgis.core import (Qgis, QgsApplication, QgsColorRampShader, QgsContrastEnhancement, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsDataSourceUri, QgsDateTimeRange, QgsMultiBandColorRenderer,
                       QgsPalettedRasterRenderer, QgsPointXY, QgsProject, QgsRasterLayer, QgsRasterShader,
                       QgsRectangle, QgsSettings, QgsSingleBandPseudoColorRenderer, QgsTask, QgsFillSymbol,
                       QgsVectorLayer)
from qgis.gui import QgsCheckableComboBox, QgsCollapsibleGroupBox, QgsFieldComboBox, QgsMapLayerComboBox
from qgis.PyQt.QtCore import QDate, QDateTime, QEvent, QPoint, Qt, QTime, QTimer, QUrl
from qgis.PyQt.QtGui import QColor, QDesktopServices, QPixmap
from qgis.PyQt.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateEdit, QDockWidget, QDoubleSpinBox,
                                 QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                                 QPushButton, QScrollArea, QInputDialog, QMenu, QTabWidget, QToolButton, QVBoxLayout,
                                 QWhatsThis, QWidget)

from . import deps

deps.setup_path()
from monitoreo import (areas, assets, catalog, categorical, classes, fire, landcover, maps,  # noqa: E402
                       municipalities, parameters, seas, sensors, services, steps, timeseries, trends)
from monitoreo import variable as variables  # noqa: E402
from monitoreo.publish import period_text  # noqa: E402

from .helptexts import HELP, MANUAL, data_help, data_summary, data_use, esc, filters_help, variable_help  # noqa: E402
from .results import KINDS_TIP, MAP_KINDS, parameters_text  # noqa: E402
from . import sendlogs  # noqa: E402

SETTINGS = 'MonitorEO/'
STEPS = [('Monthly', 'monthly'), ('Annual', 'annual'), ('16 days', '16-day'), ('Daily (days with images)', 'daily')]
# the metrics of the images and the statistics of the region (any of them for any variable; composite.METRICS): the
# standard deviation and the coefficient of variation (100 × standard deviation / mean, in %) measure how much they vary
PERCENTILES = [('Percentile 5', 'p5'), ('Percentile 10', 'p10'), ('Percentile 25', 'p25'), ('Percentile 75', 'p75'),
               ('Percentile 90', 'p90'), ('Percentile 95', 'p95')]
SPREADS = [('Standard deviation', 'std'), ('Coefficient of variation (%)', 'cv')]
METRICS = [('Mean', 'mean'), ('Median', 'median'), ('Minimum', 'min'), ('Maximum', 'max')] + PERCENTILES + SPREADS
# the only metric of a variable that the others do not take (composite.ONLY: the snow cover days, SCD, and the snow
# melt-out day, SMOD): in the lists of the metrics only while that variable is chosen (variable_changed)
ONLY_METRICS = [('Days (snow cover)', 'days'), ('Melt-out day (snow)', 'melt')]
# the steps of the variables with one value per year (the snow melt-out day, composite.check_step): only Annual
YEARLY_METRICS = ('melt',)
STATS = [('Mean', 'mean'), ('Median', 'median'), ('Minimum', 'min'), ('Maximum', 'max')] + SPREADS + PERCENTILES
TEMPORAL = [('Whole period', 'period'), ('Each year, then between years', 'annual'),
            ('Each month, then between years', 'monthly')]
# the chart by day of the year: a line per year, or the seasonal profile, a metric between the years of the values of
# each step of the year (services.time_series with doy and interannual; timeseries.over_years)
DOY_INTERANNUAL = [('A line per year', None), ('Mean', 'mean'), ('Median', 'median'), ('Minimum', 'min'),
                   ('Maximum', 'max'), ('Percentile 25', 'p25'), ('Percentile 75', 'p75'),
                   ('Standard deviation', 'std'), ('Coefficient of variation (%)', 'cv')]
TREND_STEPS = [('Year', 'annual'), ('Months', 'monthly'), ('16 days', '16-day')]
TREND_TESTS = [('Mann-Kendall', 'mk'), ('Hamed-Rao (autocorrelation)', 'hamed-rao'),
               ('TFPW (pre-whitening)', 'tfpw')]  # monitoreo.trends.TESTS
ANIMATION_STEPS = [('Year', 'annual'), ('Month', 'monthly'), ('16 days', '16-day'), ('Day with images', 'daily')]
AREA_KINDS = [('Land cover map', 'landcover'), ('Classes of the variable (breaks)', 'breaks'),
              ('Trend of the variable', 'trend'), ('Classes of a categorical layer (the variable)', 'classes')]
# a condition of «Only the pixels where» on a categorical layer (ECOREGION, BIOME): its classes to keep or to leave out
CLASS_CONDITIONS = [('is one of the classes', 'classes'), ('is none of the classes', 'exclude')]
# the biome at the center of the map: its part in the map extent (a whole biome spans continents), the region
# {'biome_at': [lon, lat], 'within': {'bbox': the extent}}
REGIONS = [('Layer (selected features or all)', 'layer'), ('Map extent', 'extent'),
           ('Protected area (WDPA)', 'wdpa'), ('Administrative unit', 'admin'), ('Country', 'country'),
           ('Ecoregion at the center of the map', 'ecoregion'), ('Biome at the center of the map', 'biome'),
           ('Island at the center of the map', 'island'), ('Sea or ocean (IHO)', 'sea'),
           ('Sea at the center of the map', 'sea_point')]
# the regions of the point at the center of the map: their key in the region, {key: [lon, lat]}
CENTER_KEYS = {'ecoregion': 'ecoregion_at', 'island': 'island_at', 'sea_point': 'sea_at'}
# the levels of the administrative units: 1 and 2, those of FAO GAUL 2025 of any country, searched in Earth Engine; 3,
# the municipalities of Spain of the Instituto Geográfico Nacional (monitoreo.municipalities), found by their name or
# their code of the INE in the index of the package, without Earth Engine
ADMIN_LEVELS = [('Level 1', 1), ('Level 2', 2), ('Level 3 · Municipalities (Spain)', municipalities.LEVEL)]
ADMIN_LEVEL_TIP = ('Level 1: regions, states, provinces...; level 2: provinces, districts, municipalities... (both of '
                   'FAO GAUL 2025, any country); level 3: the municipalities of Spain, of the Instituto Geográfico '
                   'Nacional (by their name or their code of the INE, found without Earth Engine)')
ADMIN_COUNTRY_TIP = 'Country (ISO3 code, e.g. ESP): optional'
ADMIN_SPAIN_TIP = 'Level 3 is the municipalities of Spain: the country is Spain (ESP)'
ADMIN_HINTS = {1: 'name of the unit (e.g. Granada)', 2: 'name of the unit (e.g. Granada)',
               municipalities.LEVEL: 'name or INE code of the municipality (e.g. Monachil)'}
FIRE_SENSORS = [('Sentinel-2 (20 m)', 'Sentinel-2'), ('Landsat (30 m)', 'Landsat')]
# MODIS, only for the burn indices that have it (services.BURN_SENSORS: the RdNBR): the daily surface reflectance of
# Terra or of Aqua (500 m), given to services.burn_severity as the sensor 'Modis' and the collection of each
FIRE_MODIS = [('MODIS Terra (500 m)', 'MODIS/061/MOD09GA'), ('MODIS Aqua (500 m)', 'MODIS/061/MYD09GA')]
FIRE_TIPS = {
	'MODIS/061/MOD09GA': 'Daily surface reflectance of MODIS Terra (MOD09GA, since 2000-02-24), bands 2 and 7, 500 m',
	'MODIS/061/MYD09GA': 'Daily surface reflectance of MODIS Aqua (MYD09GA, since 2002-07-04), bands 2 and 7, 500 m',
	'dNBR': 'NBR before minus NBR after the fire, in the 7 classes of the USGS (Key & Benson 2006)',
	'RBR': 'Relativized Burn Ratio (Parks et al. 2014): a continuous map, without classes',
	'RdNBR': 'Relative dNBR (Miller & Thode 2007): dNBR / sqrt(|NBR before|), in the 4 classes of the article '
	         '(unchanged, low, moderate and high severity); also with MODIS Terra and Aqua',
}
FIRE_INDICES = [('dNBR (USGS classes)', 'dNBR'), ('RBR (continuous, no classes)', 'RBR'),
                ('RdNBR (Miller & Thode 2007 classes)', 'RdNBR')]
# which burned patches the perimeter keeps (services.burn_severity: seed or largest)
FIRE_KEEP = [('every burned patch', 'all'), ('the largest patch', 'largest'), ('the patch nearest to a point', 'seed')]
# the two periods of the burn severity, at first those of the example of the manual: the fire of August 2023 in Teide
# National Park (Tenerife)
FIRE_DATES = {'before_start': '2023-05-15', 'before_end': '2023-08-14', 'after_start': '2023-09-15',
              'after_end': '2023-11-30'}
POLL_MS = 30000
ALPHA = 0.05  # «Significant pixels only»: the pixels with p < ALPHA of the trend test
MAX_VERTICES = 20000
MAP_PIXELS = 4000000  # maps downloaded as GeoTIFF: at most these pixels (16 MB), always those of the data; a bigger
# region is not computed (services.check_pixels: a warning with what to change)
# how to compute with the user's own account instead of the shared one of MonitorEO, after its warnings
OWN_PROJECT = ' In this panel: write your project in "Project" and press "Authenticate…".'
# the data of Earth Engine outside the catalog (monitoreo.assets): images with dates, aggregated in time like the
# variables (collection=), or a fixed image without dates, like the elevation (image=)
USES = [('Images with dates (collection)', 'collection'), ('Fixed image (image)', 'image')]
# their arguments besides collection, which the maps of a result keep (add_result_map)
SOURCE = ('image', 'band', 'band_reducer', 'band_scale', 'band_offset', 'unit', 'terrain')
# how their bands are computed: one, or several combined on each pixel (band_reducer of monitoreo.variable)
REDUCERS = [('One band', ''), ('Sum of the bands', 'sum'), ('Mean of the bands', 'mean')]
NO_FILTERS = ('The data of Earth Engine outside the catalog keep only their own mask: the pixel filters are for the '
              'variables of the catalog')
NO_SNOW_NDSI = ('The snow by its NDSI is for the variables of Sentinel-2 and Landsat of the catalog, with the filter '
                'snow checked (not for MODIS, the data of Earth Engine by their ID, the variables with fixed filters '
                'nor those that measure water: open water has a high NDSI too)')
NO_TOPOGRAPHIC = ('The topographic correction is for the surface reflectance of Landsat (Sentinel-2 comes already '
                  'corrected; not for the land surface temperature, the snow or cloud frequency, MODIS, the climate or '
                  'the fixed layers)')
NO_HARMONIZE = ('The harmonization of Landsat 5 and 7 with Landsat 8 and 9 is for the variables of Landsat computed '
                'from its surface reflectance (not the land surface temperature, the snow or cloud frequency, nor the '
                'other sensors)')
NO_LANDSAT7 = 'Landsat 7 after 2003 is for the variables of Landsat of the catalog'
MIN_COVERAGE = 0.5  # the fraction of the check box of the minimum coverage of the steps of the series
READ_HINT = ('Write the ID of an image or a collection of images of Earth Engine (e.g. IDAHO_EPSCOR/TERRACLIMATE) and '
             'press Read: its bands, units, licence and how to cite it')
ZONE_STATS = ['p25', 'p50', 'p75', 'mean']  # the statistics of each band of Gradients (of a categorical layer, mode)
# the analyses of the panel: the method that gives its parameters (its function of monitoreo.services and its
# arguments, without its outputs: see monitoreo.parameters), what it is and its button
PANEL = {
	'series': ('series_call', 'the time series (with Compare with, the comparison of the periods)',
	           'Compute the time series'),
	'trend_table': ('trend_table_call', 'the trend table of the region', 'Trend table of the region'),
	'trend_map': ('trend_map_call', 'the trend map', 'Trend map'),
	'map': ('map_call', 'the map (with Compare with, the difference of the periods)', 'Add the layer to the map'),
	'areas': ('areas_call', 'the area by class', 'Compute the areas'),
	'zones': ('zones_call', 'the statistics of each band', 'Statistics of each band'),
	'transect': ('transect_call', 'the profile along the line', 'Profile along the line'),
	'animation': ('animation_call', 'the animation', 'Make the animation'),
	'export_map': ('export_map_call', 'the export of the map', 'Map (GeoTIFF)'),
	'export_series': ('export_series_call', 'the export of the series', 'Series (CSV)'),
	'burn': ('burn_call', 'the burn severity', 'Compute the severity'),
}
# the analysis of the panel of each analysis of monitoreo.parameters (the tiles of a map and its figure: its map)
GROUPS = {'time_series': 'series', 'compare_series': 'series', 'trend_table': 'trend_table', 'trend_map': 'trend_map',
          'download_trend': 'trend_map', 'map_layer': 'map', 'download_image': 'map', 'map_figure': 'map',
          'rgb_map': 'map', 'download_rgb': 'map', 'compare_map': 'map', 'download_comparison': 'map',
          'area_by_class': 'areas', 'region_stats': 'zones', 'transect': 'transect', 'timelapse': 'animation',
          'export_image': 'export_map', 'time_series_to_drive': 'export_series', 'burn_severity': 'burn'}
# the analyses with Compare with: on for the comparisons of two periods, off for the others
COMPARED = ('time_series', 'compare_series', 'map_layer', 'download_image', 'map_figure', 'rgb_map', 'download_rgb',
            'compare_map', 'download_comparison')
# what is computed: a variable of the catalog, or the data of Earth Engine by their ID
DATA = ('variable', 'sensor', 'collection', 'ref', 'image', 'band', 'band_reducer', 'band_scale', 'band_offset', 'unit',
        'terrain')
# the fields of the panel that the parameters set, in this order (the variable first: it greys out some of the others);
# those of COMBOS are the list of the panel of the same name
FIELDS = ('variable', 'region', 'line', 'where', 'period', 'compare', 'season', 'quality', 'step', 'ts_metric', 'stat',
          'min_coverage', 'doy', 'doy_interannual', 'doy_other', 'trend_step', 'trend_part', 'trend_metric', 'trend_test',
          'trend_alpha', 'trend_colours', 'map_metric', 'temporal', 'interannual', 'map_kind', 'map_colours', 'resolution', 'zones',
          'stats', 'area_kind', 'area_map', 'area_breaks', 'anim_step', 'anim_metric', 'anim_fps', 'anim_colours',
          'anim_same', 'fire_index', 'fire_sensor',
          'fire_before', 'fire_after', 'fire_perimeter')
COMBOS = ('step', 'ts_metric', 'stat', 'doy_interannual', 'trend_step', 'trend_part', 'trend_metric', 'trend_test',
          'map_metric',
          'temporal', 'interannual', 'area_kind', 'anim_step', 'anim_metric', 'fire_index', 'fire_sensor')
REGION_LAYER = 'Region of the parameters'  # the temporary layers of a region or a line of some parameters
LINE_LAYER = 'Line of the parameters'
_MISSING = object()


def level(name):
	"""Qgis message level NAME (Info, Warning, Critical, Success) in QGIS 3 and 4."""
	enum = getattr(Qgis, 'MessageLevel', None)
	return getattr(enum, name) if enum is not None and hasattr(enum, name) else getattr(Qgis, name)


def pseudocolor(layer, vmin, vmax, palette, band=1):
	"""Colour the band BAND of LAYER (default: the first) with the colours PALETTE (hex) spread from VMIN to VMAX."""
	if vmax <= vmin:
		vmax = vmin + 1e-6
	n = len(palette)
	items = [QgsColorRampShader.ColorRampItem(vmin + (vmax - vmin) * i / max(n - 1, 1), QColor('#' + c.lstrip('#')),
	                                          f'{vmin + (vmax - vmin) * i / max(n - 1, 1):.4g}')
	         for i, c in enumerate(palette)]
	ramp = QgsColorRampShader(vmin, vmax)
	ramp.setColorRampItemList(items)
	shader = QgsRasterShader()
	shader.setRasterShaderFunction(ramp)
	renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), band, shader)
	renderer.setClassificationMin(vmin)
	renderer.setClassificationMax(vmax)
	layer.setRenderer(renderer)


def rgb(layer, lo, hi, bands=(1, 2, 3)):
	"""Show the bands BANDS of LAYER (default: the first three, those of a true colour, red, green and blue) as its
	red, green and blue, the three stretched together from LO to HI (one range for the three, as in the other tools,
	so that the colours keep their balance)."""
	if hi <= lo:
		hi = lo + 1e-6
	provider = layer.dataProvider()
	renderer = QgsMultiBandColorRenderer(provider, *bands)
	for band, set_enhancement in zip(bands, (renderer.setRedContrastEnhancement, renderer.setGreenContrastEnhancement,
	                                         renderer.setBlueContrastEnhancement)):
		enhancement = QgsContrastEnhancement(provider.dataType(band))
		enhancement.setContrastEnhancementAlgorithm(
			QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum)
		enhancement.setMinimumValue(lo)
		enhancement.setMaximumValue(hi)
		set_enhancement(enhancement)
	layer.setRenderer(renderer)


def rgb_caption(lo, hi, stretch=None):
	"""The legend of a true colour shown from LO to HI (reflectance), as in the other tools, and how it was stretched
	(the text of STRETCH, see monitoreo.maps.stretch_of, if given)."""
	text = stretch.get('text') if isinstance(stretch, dict) else None
	return f'True colour (red, green, blue): reflectance from {lo:.4g} to {hi:.4g}' + (f' ({text})' if text else '')


def paletted(layer, band, classes):
	"""Colour the band BAND of LAYER with a colour for each of its values (a paletted renderer: unique values), from
	CLASSES ([{'value', 'color' ('#rrggbb'), 'label'}]); the legend of the layer shows their labels."""
	items = [QgsPalettedRasterRenderer.Class(c['value'], QColor(c['color']), c['label']) for c in classes]
	layer.setRenderer(QgsPalettedRasterRenderer(layer.dataProvider(), band, items))


def dated(layer, first, last):
	"""Give LAYER the days FIRST to LAST (YYYY-MM-DD) in the Temporal Controller of QGIS."""
	props = layer.temporalProperties()
	props.setMode(Qgis.RasterTemporalMode.FixedTemporalRange)
	begin = QDateTime(QDate.fromString(first, 'yyyy-MM-dd'), QTime(0, 0))
	end = QDateTime(QDate.fromString(last, 'yyyy-MM-dd').addDays(1), QTime(0, 0))
	props.setFixedTemporalRange(QgsDateTimeRange(begin, end, True, False))
	props.setIsActive(True)


CREDITS_HEADING = 'Credits of the data:'  # in the abstract of a layer, before its credits (see figure_layout)
MANUAL_HEADING = 'What it is (manual of MonitorEO):'  # the sections of the wiki of its variables (res['manual'])
REFERENCES_HEADING = 'References (cite them with this layer):'  # before its references (and its credits, earlier)


def references_text(res):
	"""The references and credits of a result (monitoreo.references), for the abstract of its layer: the credits under
	their own heading, CREDITS_HEADING, for the print layouts (figure_layout), after the data of its values («Data:
	...», data_source), as the figures of services.map_figure."""
	refs = [r['text'] for r in res.get('references') or []]
	credits = ([f"Data: {res['data_source']}"] if res.get('data_source') else []) + \
		[c for c in res.get('credits') or [] if c]
	links = [f"{m['title']}: {m['url']}" for m in res.get('manual') or [] if isinstance(m, dict) and m.get('url')]
	return (((f'\n\n{MANUAL_HEADING}\n' + '\n'.join(links)) if links else '') +  # what each variable is
	        ((f'\n\n{REFERENCES_HEADING}\n' + '\n'.join(refs)) if refs else '') +
	        ((f'\n\n{CREDITS_HEADING}\n' + '\n'.join(credits)) if credits else ''))


def layer_credits(text):
	"""The credits of the data in the abstract TEXT of a layer of the plugin (references_text): the lines under
	CREDITS_HEADING until a blank line. A layer of an earlier version of the plugin has them at the end of its
	references, without that heading: of the lines under REFERENCES_HEADING, those that are the credit of a dataset of
	catalog.json (Copernicus Sentinel, USGS Landsat, Copernicus DEM, FAO GAUL...), whatever its years."""
	lines = [line.strip() for line in str(text or '').splitlines()]
	heading = CREDITS_HEADING if CREDITS_HEADING in lines else REFERENCES_HEADING
	if heading not in lines:
		return []
	out = []
	for line in lines[lines.index(heading) + 1:]:
		if not line:
			break
		out.append(line)
	if heading == REFERENCES_HEADING:
		known = [re.compile(re.sub(r'\\\{(year|month_year|data_years)\\\}', '.+', re.escape(d['credit'])))
		         for d in catalog.load()['datasets'].values() if d.get('credit')]
		out = [line for line in out if any(k.fullmatch(line) for k in known)]
	return out


def add_layer(layer, group=None):
	"""Add LAYER to the project, on top of the layer tree or of GROUP."""
	if group is None:
		QgsProject.instance().addMapLayer(layer)
	else:
		QgsProject.instance().addMapLayer(layer, False)
		group.insertLayer(0, layer)


def result_maps(tool, args):
	"""The maps that the window of a result of TOOL ('time_series' or 'trend_table') with ARGS offers: that of its
	whole period (of a trend, the trend of the values of each year) and those of each of its steps (its years, months
	or periods of 16 days; of a trend, its parts of the year), as in the assistant (see monitoreo.steps)."""
	period = period_text(args['start'], args['end'])
	if tool == 'trend_table':
		main = {'key': '', 'label': f'Annual trend ({period})', 'step': 'annual'}
	else:
		main = {'key': '', 'label': f'Whole period ({period})', 'start': args['start'], 'end': args['end']}
	return [main] + steps.map_steps(tool, args)


def quota_text(once=False):
	"""The warning of services.quota_warning (Earth Engine has put the project in restricted mode: it has spent its
	noncommercial compute quota, so computations are slow and may fail), with the shared account of MonitorEO followed
	by how to use the user's own project in this panel; or None. ONCE: only the first time of each restricted mode."""
	text = services.quota_warning(once=once)
	return text + OWN_PROJECT if text and services.shared() else text


def too_many_text(description, e):
	"""The warning of the task DESCRIPTION whose map does not fit on the pixels of the data (services.TooManyPixels
	E): by how much it exceeds the limit and what to change."""
	fit = ', '.join(f"{s['sensor']} ({s['resolution']:g} m)" for s in e.sensors)
	return (f'{description}: not computed. At {e.resolution:g} m, the pixels of the data, the map would have '
	        f'{e.pixels:,} pixels, {e.excess:,}% more than the {e.max_pixels:,} of the maps added to QGIS. Choose '
	        + (f'another sensor ({fit}), ' if fit else '')
	        + f'a region with at most {e.share:g}% of its extent, or Export to Google Drive (no size limit)')


def true_colour(region, opts, path, resolution=None, stretch=None):
	"""The true colour of the images of the map with the arguments OPTS (services.download_rgb: the GeoTIFF PATH with
	the bands red, green and blue, on the grid of pixels of RESOLUTION m, that of the map, so that their pixels match)
	or, if it cannot be downloaded, its Earth Engine tiles (services.rgb_map, stretched from STRETCH[0] to STRETCH[1]
	if given). In a task."""
	try:
		return services.download_rgb(region, path=path, resolution=resolution, **opts)
	except Exception as e:
		out = services.rgb_map(region, **dict(opts, **({'vmin': stretch[0], 'vmax': stretch[1]} if stretch else {})))
		out['error'] = str(e)
		return out


def result_warnings(result):
	"""The warnings of the periods of the answers of the services in RESULT (an answer, a list or tuple of them, or a
	dictionary of them, as that of maps_work): their days without images of their data (see monitoreo.coverage),
	[texts], each once."""
	found = []
	for r in (result if isinstance(result, (list, tuple)) else [result]):
		if not isinstance(r, dict):
			continue
		for d in [r] + [v for v in r.values() if isinstance(v, dict)]:
			for w in d.get('warnings') or [] if isinstance(d.get('warnings'), list) else []:
				if w and w not in found:
					found.append(w)
	return found


def restretch(res, percentiles=None, given=None, over='the values of the file', symmetric=False):
	"""The GeoTIFF of the map RES (an answer of monitoreo.services with its file) with the colour ramp that the panel
	asks for, when its service could not make it: between the PERCENTILES (lo, hi) of the values of its first band, if
	its stretch has others (symmetric around 0 with SYMMETRIC, as the slope of a trend), and from the minimum and
	maximum of GIVEN ((vmin, vmax), None where not given). Updates its min, max and stretch (see maps.stretch_of).
	Without a file, values or with classes (a categorical layer), RES as it is. Returns RES."""
	if not isinstance(res, dict) or not res.get('file') or res.get('classes') is not None or res.get('min') is None:
		return res
	pct, (vmin, vmax) = tuple(percentiles or maps.STRETCH), given or (None, None)
	had = res.get('stretch') if isinstance(res.get('stretch'), dict) else {}
	if percentiles is None or (vmin is not None and vmax is not None) or tuple(had.get('percentiles') or ()) == pct:
		pass  # stretched so by its service, or from the minimum and maximum given
	elif not had and pct == tuple(maps.STRETCH):  # stretched so by its service (by default), without saying it
		res['stretch'] = maps.stretch_of(over, pct, False, False)
	else:
		lo, hi = services._percentiles(res['file'], *pct)
		if lo is not None:
			if symmetric:
				m = max(abs(lo), abs(hi)) or 1e-6
				lo, hi = -m, m
			res['min'], res['max'] = lo, hi
			res['stretch'] = maps.stretch_of(over, pct, False, False)
	if vmin is not None or vmax is not None:
		res['min'], res['max'] = given_colours(given, res['min'], res['max'])
		res['stretch'] = maps.stretch_of(over, pct, vmin is not None, vmax is not None)
	return res


def maps_work(kind, region, opts, folder, download, tiles, colors=None, stretch=None, percentiles=None):
	"""The layers of a map with the arguments OPTS, in a task: with KIND 'index' or 'both', the map of the variable
	(DOWNLOAD: the GeoTIFF map.tif, or trend.tif, of FOLDER or, if it cannot be downloaded, TILES), stretched between
	the PERCENTILES (lo, hi; by default maps.STRETCH) of its values, and from the minimum and maximum of COLORS
	((vmin, vmax), None where not given) if given (see restretch); with KIND 'rgb' or 'both', the true colour of the
	same images and pixels (rgb.tif, on the grid of the map; see true_colour: with 'both', with its own stretch, that
	of the true colour). Returns {'index', 'rgb'} (those asked for) and, if only the true colour of 'both' failed,
	'rgb_error' instead of 'rgb' (the map is added all the same). First, whether the map fits on the pixels of the
	data (services.check_pixels: if not, TooManyPixels, before computing anything)."""
	services.check_pixels(region, MAP_PIXELS, rgb=kind != 'index', **opts)  # with a true colour: sensors that have it
	out = {}
	if kind != 'rgb':
		trend = download is services.download_trend
		ends = {k: v for k, v in zip(('vmin', 'vmax'), colors or ()) if v is not None}
		taken = {k: v for k, v in ends.items() if takes(download, k)}  # the services compute them with the stretch
		try:
			out['index'] = download(region, path=os.path.join(folder, 'trend.tif' if trend else 'map.tif'),
			                        **dict(opts, **taken))
		except Exception as e:
			extra = {k: v for k, v in zip(('vmin', 'vmax'), colors or ()) if v is not None}
			if percentiles and tuple(percentiles) != tuple(maps.STRETCH) and takes(tiles, 'percentiles'):
				extra['percentiles'] = list(percentiles)
			out['index'] = tiles(region, **dict(opts, **extra))
			out['index']['error'] = str(e)
		else:  # the percentiles, here if its service does not take them (download_trend); the minimum and maximum too
			said = out['index'].get('stretch') if ends and taken == ends else None  # its service took the ends
			restretch(out['index'], None if takes(download, 'percentiles') else percentiles, colors,
			          'the slope of the file (symmetric around 0)' if trend else 'the values of the file', trend)
			if isinstance(said, dict):  # how its service said it stretched them (with the percentiles it used)
				out['index']['stretch'] = said
	if kind != 'index':
		# with Both, the true colour has its own stretch (maps.RGB_STRETCH): the colour range is that of the map
		rgb_opts = {k: v for k, v in opts.items() if kind == 'rgb' or k not in ('percentiles', 'vmin', 'vmax')}
		try:
			out['rgb'] = true_colour(region, rgb_opts, os.path.join(folder, 'rgb.tif'),
			                         (out.get('index') or {}).get('resolution'), stretch)
		except Exception as e:
			if kind == 'rgb':
				raise
			out['rgb_error'] = str(e)
	return out


def figure_layout(canvas, name='MonitorEO figure'):
	"""A print layout (A4 landscape) of the map of CANVAS, added to the project with a free NAME: the map with a grid
	of coordinates, the legend, a scale bar, a north arrow, the title (the name of the top visible layer) and the credits
	of the layers of MonitorEO (from their metadata) with the citation of MonitorEO."""
	from qgis.core import (QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemMap, QgsLayoutItemMapGrid,
	                       QgsLayoutItemPicture, QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize, QgsPrintLayout)
	from qgis.PyQt.QtCore import QRectF
	from qgis.PyQt.QtGui import QFont
	from monitoreo.figures import decimals
	project = QgsProject.instance()
	manager = project.layoutManager()
	title = name
	k = 1
	while manager.layoutByName(title):
		k += 1
		title = f'{name} {k}'
	layout = QgsPrintLayout(project)
	layout.initializeDefaults()  # A4 landscape, 297 x 210 mm
	layout.setName(title)
	visible = [n.layer() for n in project.layerTreeRoot().findLayers() if n.isVisible() and n.layer() is not None]
	top = visible[0].name() if visible else 'MonitorEO'
	label = QgsLayoutItemLabel(layout)
	label.setText(top)
	font = QFont()
	font.setPointSize(14)
	font.setBold(True)
	label.setFont(font)
	layout.addLayoutItem(label)
	label.attemptMove(QgsLayoutPoint(12, 6))
	label.attemptResize(QgsLayoutSize(273, 10))
	item = QgsLayoutItemMap(layout)
	item.attemptSetSceneRect(QRectF(12, 18, 205, 160))
	item.setCrs(canvas.mapSettings().destinationCrs())
	item.zoomToExtent(canvas.extent())  # the map keeps its 205 x 160 mm, with all the extent of the canvas in it
	layout.addLayoutItem(item)
	grid = item.grid()
	grid.setEnabled(True)
	extent = item.extent()
	step = _nice(max(extent.width(), extent.height()) / 5)
	grid.setIntervalX(step)
	grid.setIntervalY(step)
	grid.setStyle(QgsLayoutItemMapGrid.GridStyle.Cross)
	grid.setAnnotationEnabled(True)
	# the decimals that tell apart the lines of the grid (at least 2 in degrees, as the figures of monitoreo)
	grid.setAnnotationPrecision(decimals(step, 2 if canvas.mapSettings().destinationCrs().isGeographic() else 0))
	legend = QgsLayoutItemLegend(layout)
	legend.setLinkedMap(item)
	legend.setTitle('Legend')
	layout.addLayoutItem(legend)
	legend.attemptMove(QgsLayoutPoint(222, 18))
	scale = QgsLayoutItemScaleBar(layout)
	scale.setStyle('Single Box')
	scale.setLinkedMap(item)
	scale.applyDefaultSize()
	layout.addLayoutItem(scale)
	scale.attemptMove(QgsLayoutPoint(14, 166))
	north = QgsLayoutItemPicture(layout)
	north.setPicturePath(':/images/north_arrows/layout_default_north_arrow.svg')
	north.setLinkedMap(item)
	layout.addLayoutItem(north)
	north.attemptMove(QgsLayoutPoint(200, 20))
	north.attemptResize(QgsLayoutSize(12, 12))
	credits = []
	for layer in visible:  # the credits of the data that the plugin writes in the metadata of its layers
		credits += layer_credits(layer.serverProperties().abstract() if hasattr(layer, 'serverProperties') else '')
	from monitoreo import about
	note = QgsLayoutItemLabel(layout)
	note.setText('\n'.join(list(dict.fromkeys(credits)) + [f'Computed with MonitorEO in Google Earth Engine. '
	                                                        f'{about.CITATION}']))
	small = QFont()
	small.setPointSize(7)
	note.setFont(small)
	layout.addLayoutItem(note)
	note.attemptMove(QgsLayoutPoint(12, 182))
	note.attemptResize(QgsLayoutSize(273, 22))
	manager.addLayout(layout)
	return layout


def _nice(x):
	"""The number 1, 2 or 5 × 10^k closest below X (the step of a grid)."""
	from monitoreo.figures import nice
	return nice(x)


def data_name(var, sensor=True):
	"""What the arguments VAR compute, for the titles of the tasks: the variable of the catalog with its sensor (with
	SENSOR: NDVI (Sentinel-2)), or the ID and band (or the reducer of its bands: monitoreo.variable.band_text) of the
	data of Earth Engine outside it (IDAHO_EPSCOR/TERRACLIMATE pr, IDAHO_EPSCOR/TERRACLIMATE sum of aet, def), which
	have no variable nor sensor."""
	if var.get('variable'):
		return f"{var['variable']} ({var['sensor']})" if sensor else var['variable']
	return f"{var.get('collection') or var.get('image') or '?'} {variables.band_text(var)}".strip()


def bands_note(records):
	"""What the panel says of the bands checked to combine (RECORDS: theirs in services.describe_asset) when they
	differ: in pixel size (they are combined on those of the first band), or in the unit, scale or offset of their
	records (the Band scale, Band offset and Unit of the panel are those of every band); '' if they do not."""
	notes = []
	sizes = [r.get('resolution_m') for r in records]
	if len(set(sizes)) > 1 and sizes[0]:
		notes.append(f'The bands checked have pixels of different sizes: they are combined on those of the first '
		             f'({sizes[0]:g} m).')
	differ = [what for key, what in (('units', 'units'), ('band_scale', 'scales'), ('band_offset', 'offsets'))
	          if len({str(r.get(key)) for r in records}) > 1]
	if differ:
		notes.append(f"Their records give different {' and '.join(differ)}: the Band scale, Band offset and Unit "
		             'apply to every band, so combine bands of the same quantity.')
	return ' '.join(notes)


def burn_stem(index):
	"""The name of the files of a burn severity of the index INDEX, without extension."""
	return 'burn_severity' + {'RBR': '_rbr', 'RdNBR': '_rdnbr'}.get(index, '')


def burn_label(title, collection=None):
	"""The name of a burn severity of title TITLE in the list of results and of its layer: TITLE, with the product of
	MODIS of COLLECTION after the sensor (Modis MYD09GA), so that Terra and Aqua can be told apart, if it does not say
	it already."""
	short = str(collection or '').split('/')[-1]
	if not short or short in title:
		return title
	return title.replace(' Modis ', f' Modis {short} ', 1)


def number(value):
	"""VALUE (a number, or None) as the text of a field: '' if None."""
	return '' if value is None else format(float(value), '.10g')


def unit_text(res):
	"""The unit of the values of the map RES for its abstract ('[NDVI]', 'mm', 'mm / year' of a trend): '(unit not
	given)' for the data of Earth Engine outside the catalog computed without one (whose trends have ' / year')."""
	unit = str(res.get('unit') or '').strip()
	return '(unit not given)' if not unit or unit.startswith('/') else unit


def sea_item(sea):
	"""The entry of the list Sea for the sea SEA (a row of services.find_seas): its text, with its name, area and
	MRGID (and, for a sea of several sea areas, the Mediterranean Sea, how many: one region), and its data, the
	MRGID."""
	parts = f" · its {len(sea['PARTS'])} sea areas as one" if sea.get('PARTS') else ''
	return f"{sea['NAME']} · {sea['AREA_KM2']:,.0f} km²{parts} (MRGID {sea['MRGID']})", int(sea['MRGID'])


def admin_item(unit, level):
	"""The entry of the list Unit for the administrative unit UNIT (a row of services.find_admin_units) of LEVEL: its
	text, with the full name (DISP_EN) and the code, and its data, (level, code): the GAUL code, an integer, at levels 1
	and 2 (FAO GAUL 2025); the code of the INE, a string of 5 digits, of a municipality of Spain (level 3)."""
	level = int(level)
	if level == municipalities.LEVEL:
		code = str(unit['ADMIN3_CODE']).strip().zfill(5)
		return f"{unit.get('DISP_EN') or unit['NAME']} · INE {code}", (level, code)
	code = int(unit[f'GAUL{level}_CODE'])
	return f"{unit.get('DISP_EN') or unit[f'GAUL{level}_NAME']} (GAUL {code})", (level, code)


def combo(items, current=None):
	c = QComboBox()
	for label, value in items:
		c.addItem(label, value)
	if current is not None:
		c.setCurrentIndex([v for _, v in items].index(current))
	return c


def item_index(box, value=None, test=None):
	"""The index of the item of the list BOX whose value is VALUE (or for which TEST(value) is true), or -1."""
	for i in range(box.count()):
		v = box.itemData(i)
		if (test(v) if test else v == value):
			return i
	return -1


# Parameters of an analysis (monitoreo.parameters) ------------------------------------------------------------------

def missing(name, value, reason):
	"""A parameter NAME that was not applied, with its VALUE and the REASON (as parameters.check)."""
	return {'name': name, 'value': value, 'reason': reason}


def breaks_text(breaks):
	"""The breaks of some parameters (a list of numbers, or their text) as the panel writes them: '1500, 2000'."""
	if isinstance(breaks, (list, tuple)):
		return ', '.join(number(b) for b in breaks)
	return str(breaks)


def service_defaults(analysis):
	"""The default of each argument of the function ANALYSIS of monitoreo.services."""
	params = inspect.signature(getattr(services, analysis)).parameters
	return {n: p.default for n, p in params.items() if p.default is not p.empty}


def same_variable(v, data):
	"""Whether V (an item of a list of variables of the panel, from services.list_variables) is the variable of DATA
	({'variable', 'sensor', 'collection'}, the last two optional), their names in any case and without spaces
	(catalog.name_key), as catalog.find, parameters.check, the services and the Earth Engine app take them."""
	key = catalog.name_key
	return bool(v) and key(v['variable']) == key(data.get('variable')) and \
		(data.get('sensor') is None or key(v['sensor']) == key(data['sensor'])) and \
		data.get('collection') in (None, v.get('collection'))


def canonical(value, names):
	"""The name of NAMES that VALUE is, in any case and without spaces (catalog.name_key, as services.burn_severity
	takes its sensor); VALUE if it is none of them."""
	return next((n for n in names if value is not None and catalog.name_key(n) == catalog.name_key(value)), value)


def cover_key(value):
	"""The key of the land cover map VALUE (its key or its name in any case, as landcover.find), or VALUE if it is
	none."""
	try:
		return landcover.find(value)['key']
	except ValueError:
		return value


def variable_row(data):
	"""The entry of the list Variable of the panel (services.list_variables) of the variable of DATA ({'variable',
	'sensor', 'collection', 'ref'}, the last three optional; names as same_variable): that of its ref if given, else
	the first one; None if there is none (RBR and RdNBR, which compare two periods, are only in the burn severity)."""
	rows = [v for v in services.list_variables(lang='en') if not v.get('two_periods') and same_variable(v, data)]
	return next((v for v in rows if v.get('ref') == data.get('ref')), rows[0] if rows else None)


def feature_collection(geojson):
	"""The GeoJSON GEOJSON (a dictionary or its text: a geometry, a Feature or a FeatureCollection) as a
	FeatureCollection, or None if it is none of them."""
	try:
		g = json.loads(geojson) if isinstance(geojson, str) else geojson
	except ValueError:
		return None
	if not isinstance(g, dict):
		return None
	if g.get('type') == 'FeatureCollection' and isinstance(g.get('features'), list):
		return g
	if g.get('type') == 'Feature':
		return {'type': 'FeatureCollection', 'features': [g]}
	if 'coordinates' in g or g.get('type') == 'GeometryCollection':
		return {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': {}, 'geometry': g}]}
	return None


def line_of(line):
	"""The line LINE of some parameters of transect ([[lon, lat], ...], a GeoJSON LineString, a Feature of one or
	{'geojson': ...}) as [[lon, lat], ...], or None if it is not a line of two points or more."""
	if isinstance(line, dict):
		line = line.get('geojson', line)
		if isinstance(line, str):
			try:
				line = json.loads(line)
			except ValueError:
				return None
		if isinstance(line, dict) and line.get('type') == 'Feature':
			line = line.get('geometry') or {}
		line = line.get('coordinates') if isinstance(line, dict) and line.get('type') == 'LineString' else None
	try:
		points = [[float(x), float(y)] for x, y in line]
	except (TypeError, ValueError):
		return None
	return points if len(points) >= 2 else None


def _point(v):
	"""V as [lon, lat], or None."""
	try:
		lon, lat = (float(x) for x in v)
	except (TypeError, ValueError):
		return None
	return [lon, lat]


def _one(v):
	"""V, or the only item of the list V; None for a list of several."""
	if isinstance(v, (list, tuple)):
		return v[0] if len(v) == 1 else None
	return v


def region_kind(region):
	"""The kind of region of the panel (see REGIONS) and its value for the region REGION of some parameters: ('layer',
	(its FeatureCollection, the field of its names)), ('extent', bbox), ('wdpa', ID), ('admin', (level, code)),
	('country', ISO3), ('sea', MRGID), ('ecoregion', 'island' or 'sea_point', [lon, lat]) or ('biome', {'at': [lon,
	lat], 'within': bbox or None});
	(None, the reason) if the panel has no region like it (see areas.region)."""
	kinds = ('the panel takes a layer (geojson), the map extent (bbox), a protected area (wdpa_id), an administrative '
	         'unit (admin1, admin2, admin3), a country, a sea (sea) or the ecoregion, biome, island or sea at the '
	         'center of the map (ecoregion_at, biome_at, island_at, sea_at)')
	keys = [k for k in areas.REGION_KEYS if region.get(k) is not None] if isinstance(region, dict) else []
	if len(keys) != 1:
		return None, f'not a region: {kinds}'
	k, v = keys[0], region[keys[0]]
	within = region.get('within')
	if within is not None and not (k == 'biome_at' and isinstance(within, dict) and set(within) == {'bbox'}):
		return None, 'the panel takes within only for the biome at the center of the map (within the map extent)'
	if k == 'geojson':
		fc = feature_collection(v)
		return ('layer', (fc, region.get('name_field'))) if fc else (None, 'its geojson is not GeoJSON')
	if k == 'bbox':
		box = [float(x) for x in v] if isinstance(v, (list, tuple)) and len(v) == 4 else None
		return ('extent', box) if box else (None, 'bbox is [west, south, east, north]')
	if k == 'wdpa_id':
		one = _one(v)
		return ('wdpa', int(one)) if one is not None else (None, 'the panel takes one protected area')
	if k in ('admin1', 'admin2'):
		one = _one(v)
		return ('admin', (int(k[-1]), int(one))) if one is not None else \
			(None, 'the panel takes one administrative unit')
	if k == 'admin3':  # a municipality of Spain: its code of the INE, checked in the index of the package
		one = _one(v)
		if one is None:
			return None, 'the panel takes one administrative unit'
		try:
			return 'admin', (municipalities.LEVEL, areas.municipality_codes(one)[0])
		except ValueError as e:
			return None, str(e)
	if k == 'country':
		one = _one(v)
		return ('country', str(one).strip().upper()) if one is not None else (None, 'the panel takes one country')
	if k == 'sea':  # an ocean or sea: its MRGID or its name, checked in the index of the package
		one = _one(v)
		if one is None:
			return None, 'the panel takes one sea'
		try:
			return 'sea', seas.codes(one)[0]
		except ValueError as e:
			return None, str(e)
	if k in ('ecoregion_at', 'island_at', 'biome_at', 'sea_at'):
		at = _point(v)
		if at is None:
			return None, f'{k} is a point, [lon, lat]'
		if k == 'biome_at':
			return 'biome', {'at': at, 'within': within['bbox'] if within else None}
		return {'sea_at': 'sea_point'}.get(k, k[:-3]), at
	return None, f'the panel has no region {k}: {kinds}'


def quality_fields(quality, burn=False):
	"""The pixel filters QUALITY of some parameters as the panel takes them ({filter: True, False or 'auto',
	'cloud_score': whether Cloud Score+ is checked}; those not given, as sensors.QUALITY) and the reports of those it
	cannot take (its Cloud Score+ is 0.6, and it has no filter of whole scenes)."""
	q, reports = dict(sensors.QUALITY), []
	if quality is not None and not isinstance(quality, dict):
		reports.append(missing('quality', quality, 'the pixel filters are a dictionary, e.g. {"snow": false}'))
		quality = {}
	for k, v in (quality or {}).items():
		if k in sensors.FILTERS and v in (True, False, 'auto'):
			q[k] = v
		elif k == 'water' and str(v).lower() == 'permanent':  # the panel has it only in the burn severity, always
			q[k] = True
			if not burn:
				reports.append(missing('quality.water', v, 'the panel removes the water flagged in each image (the '
				                       'permanent water of the JRC Global Surface Water only in the burn severity)'))
		elif k == 'cloud_score' and v in (None, sensors.QUALITY['cloud_score']):
			q[k] = v
		elif k == 'cloud_score':
			q[k] = v
			reports.append(missing('quality.cloud_score', v, f"the panel uses Cloud Score+ "
			                       f"{sensors.QUALITY['cloud_score']:g} (checked) or the SCL of Sentinel-2 (unchecked)"))
		elif k == 'scene_clouds' and v is None:
			continue
		elif k in ('topographic', 'harmonize', 'landsat7') and v in (True, False, None):
			q[k] = bool(v)
		elif k == 'snow_ndsi':
			try:
				x = sensors.snow_ndsi({k: v})
			except ValueError as e:
				reports.append(missing('quality.snow_ndsi', v, str(e)))
				continue
			if x is not None:
				q[k] = x
			if x not in (None, sensors.SNOW_NDSI_DEFAULT):
				reports.append(missing('quality.snow_ndsi', v, f"the panel removes the snow with an NDSI of "
				                       f"{sensors.SNOW_NDSI_DEFAULT:g} or more (checked) or none (unchecked)"))
		else:
			reports.append(missing(f'quality.{k}', v, 'the panel has no such pixel filter (clouds, water, snow and '
			                       'aerosols: true, false or "auto"; cloud_score; topographic, harmonize, landsat7: true '
			                       f'or false; snow_ndsi: {sensors.SNOW_NDSI_DEFAULT:g} or null)'))
	return dict({f: q[f] for f in sensors.FILTERS}, cloud_score=q['cloud_score'] is not None,
	            topographic=bool(q.get('topographic')), snow_ndsi=bool(q.get('snow_ndsi')),
	            harmonize=bool(q.get('harmonize')), landsat7=bool(q.get('landsat7'))), reports


def where_fields(where, period=None):
	"""The conditions WHERE of some parameters as the panel takes them: ([(i, condition)] of its two rows of «Only the
	pixels where», the land cover condition of the group Land cover mask or None, the reports of those it cannot take,
	and the period of the first condition that has one). PERIOD ([first day, last day]): that of the analysis, which
	the panel gives to the conditions on variables with dates."""
	if where is None:
		return [], None, [], None
	items = [where] if isinstance(where, dict) else list(where) if isinstance(where, (list, tuple)) else None
	if items is None:
		return [], None, [missing('where', where, 'a list of conditions')], None
	rows, cover, reports, first = [], None, [], None
	for i, c in enumerate(items):
		name = f'where[{i}]'
		if landcover.is_landcover(c):
			if cover is None:
				cover = dict(c)
			else:
				reports.append(missing(name, c, 'the panel has one land cover mask'))
			continue
		if not isinstance(c, dict) or not c.get('variable'):
			reports.append(missing(name, c, 'the panel takes conditions on the variables of the catalog'))
			continue
		if len(rows) == 2:
			reports.append(missing(name, c, 'the panel has two conditions in «Only the pixels where»'))
			continue
		cond = {k: c[k] for k in ('variable', 'sensor', 'collection', 'min', 'max', 'classes', 'exclude')
		        if c.get(k) is not None}
		for k in sorted(set(c) - set(cond) - {'period'}):
			if c[k] is not None:
				reports.append(missing(f'{name}.{k}', c[k], 'the conditions of the panel have no such option'))
		if c.get('period') is not None:
			got = [str(x)[:10] for x in c['period']]
			want = list(period or first or got)
			if got != want:
				reports.append(missing(f'{name}.period', c['period'], f'the panel takes the period of the analysis, '
				                       f'{want[0]} to {want[1]}'))
			first = first or got
		rows.append((i, cond))
	return rows, cover, reports, first


def panel_fields(analysis, params):
	"""How the panel takes the parameters PARAMS of ANALYSIS (those that parameters.check applies): (its analysis in
	the panel, see PANEL; {field (see FIELDS): {'value', 'given', 'name' (of the parameter)}}; the reports of those
	it has no field for, or whose values its fixed lists do not have). Those not given take the default of their
	function of monitoreo.services, as when it computes them (given False: not reported if their field is greyed
	out). Without widgets: MonitorEODock.apply_parameters sets the fields."""
	key = GROUPS[analysis]
	p, defaults = dict(params), service_defaults(analysis)
	fields, reports, used = {}, [], set()
	burn = analysis == 'burn_severity'

	def field(name, value, given=True, param=None):
		fields[name] = {'value': value, 'given': given, 'name': param or name}

	def colours(name):
		"""The Colour range NAME from the parameters percentiles, vmin and vmax (those of the service: the defaults
		without them)."""
		keys = [k for k in ('percentiles', 'vmin', 'vmax') if k in defaults]
		used.update(keys)
		field(name, {k: p.get(k) for k in keys}, any(k in p for k in keys), keys[0] if keys else name)

	def take(name, param=None, choices=None, default=_MISSING):
		"""The field NAME from the parameter PARAM (default: NAME) or its default, if CHOICES ([(label, value)]) has
		it."""
		param = param or name
		used.add(param)
		given = param in p
		value = p[param] if given else defaults.get(param) if default is _MISSING else default
		if choices is not None and value not in [v for _, v in choices]:
			if given:
				reports.append(missing(param, value, f"not in its list in the panel: "
				                       f"{', '.join(str(v) for _, v in choices)}"))
			return
		field(name, value, given, param)

	# what is computed, and where
	row = None
	if not burn:
		used.update(DATA)
		data = {k: p[k] for k in DATA if k in p}
		if data.get('variable'):
			row = variable_row(data)
			extra = [k for k in ('image', 'band', 'band_reducer', 'band_scale', 'band_offset', 'unit', 'terrain')
			         if k in data]
			if row is None:
				reports.append(missing('variable', data['variable'], 'not in the list Variable of the panel (RBR and '
				                       'RdNBR: only in the burn severity)'))
			else:
				field('variable', row)
				first = variable_row({k: v for k, v in data.items() if k != 'ref'})
				if data.get('ref') is not None and first and data['ref'] != first.get('ref'):
					reports.append(missing('ref', data['ref'], f"the panel computes the first {data['variable']} of "
					                       f"{first['sensor']} of the catalog (ref {first.get('ref')})"))
			reports += [missing(k, data[k], 'only for the data of Earth Engine by their ID') for k in extra]
		elif data.get('collection') or data.get('image'):
			use = 'collection' if data.get('collection') else 'image'
			band = data.get('band')
			bands = [str(b) for b in band] if isinstance(band, (list, tuple)) else [str(band)] if band else []
			reducer = data.get('band_reducer') or ''
			if reducer not in [v for _, v in REDUCERS]:
				reports.append(missing('band_reducer', reducer, 'the panel combines bands with sum or mean'))
				reducer = ''
			field('variable', {'custom': True, 'use': use, 'asset': data[use], 'bands': bands, 'band_reducer': reducer,
			                   'band_scale': data.get('band_scale'), 'band_offset': data.get('band_offset'),
			                   'unit': data.get('unit')}, True, use)
			reports += [missing(k, data[k], 'not for the data of Earth Engine by their ID in the panel')
			            for k in ('sensor', 'ref', 'terrain', 'image' if use == 'collection' else '') if k in data]
	if analysis == 'transect':
		used.add('line')
		if 'line' in p:
			line = line_of(p['line'])
			if line:
				field('line', line)
			else:
				reports.append(missing('line', p['line'], 'not a line of two points or more'))
	elif 'region' in p:
		used.add('region')
		kind, value = region_kind(p['region'])
		if kind:
			field('region', (kind, value))
		else:
			reports.append(missing('region', p['region'], value))

	# the periods, the season, the pixel filters and the conditions
	used.update(('start', 'end', 'other_start', 'other_end', 'quality', 'where'))
	if burn:
		for name, a, b in (('fire_before', 'start', 'end'), ('fire_after', 'other_start', 'other_end')):
			if a in p or b in p:
				field(name, (p.get(a), p.get(b)), True, a)
	else:
		if 'start' in p or 'end' in p:
			field('period', (p.get('start'), p.get('end')), True, 'start')
		if analysis in COMPARED:
			other = (p['other_start'], p['other_end']) if p.get('other_start') and p.get('other_end') else None
			field('compare', other, other is not None, 'other_start')
		used.add('season')
		field('season', p.get('season'), 'season' in p)
	if 'quality' in p or burn or (row and not row.get('static')):
		q, bad = quality_fields(p.get('quality'), burn)
		reports += bad
		field('quality', {'filters': q, 'own': burn}, 'quality' in p)
	period = [str(p['start'])[:10], str(p['end'])[:10]] if p.get('start') and p.get('end') else None
	rows, cover, bad, first = where_fields(p.get('where'), period)
	reports += bad
	if first and not period and not burn:  # a fixed layer with conditions on variables with dates: their period
		field('period', tuple(first), True, 'where')
	field('where', {'conditions': rows, 'landcover': cover}, 'where' in p)

	# the options of the analysis
	if analysis in ('time_series', 'compare_series', 'time_series_to_drive', 'trend_table'):
		used.add('min_coverage')
		try:
			m = timeseries.check_min_coverage(p.get('min_coverage'))
		except ValueError as e:
			m, bad = None, str(e)
		else:
			bad = None if m in (None, MIN_COVERAGE) else (f'the panel leaves without value the steps with valid pixels in '
			                                              f'less than {MIN_COVERAGE:g} of the region (checked) or none '
			                                              '(unchecked)')
		if bad:  # unchecked: not another threshold than that of the panel
			reports.append(missing('min_coverage', p.get('min_coverage'), bad))
		field('min_coverage', m == MIN_COVERAGE, 'min_coverage' in p)
	if analysis in ('time_series', 'compare_series', 'time_series_to_drive'):
		take('step', choices=STEPS)
		take('ts_metric', 'metric', METRICS)
		take('stat', choices=STATS)
		if analysis == 'time_series':
			used.update(('doy', 'other_variable', 'other_sensor'))
			field('doy', bool(p.get('doy')), 'doy' in p)
			take('doy_interannual', 'interannual', DOY_INTERANNUAL)
			other = {'variable': p['other_variable'], 'sensor': p.get('other_sensor')} if p.get('other_variable') \
				else None
			field('doy_other', other, other is not None, 'other_variable')
	elif analysis == 'trend_table':
		take('trend_step', 'step', TREND_STEPS)
		take('trend_metric', 'metric', METRICS)
		take('trend_test', 'test', TREND_TESTS)
		take('stat', choices=STATS)
	elif analysis in ('trend_map', 'download_trend'):
		take('trend_step', 'step', TREND_STEPS)
		take('trend_part', 'part')
		take('trend_metric', 'metric', METRICS)
		take('trend_test', 'test', TREND_TESTS)
		used.add('alpha')
		if p.get('alpha') not in (None, ALPHA):
			reports.append(missing('alpha', p['alpha'], f'the panel shows only the pixels with p < {ALPHA:g} '
			                       '(Significant pixels only) or every pixel'))
		else:
			field('trend_alpha', p.get('alpha') == ALPHA, 'alpha' in p, 'alpha')
		colours('trend_colours')
	elif key in ('map', 'export_map', 'zones', 'transect'):
		take('map_metric', 'metric', METRICS)
		take('temporal', choices=TEMPORAL)
		take('interannual', choices=METRICS)
		if key == 'map':
			field('map_kind', 'rgb' if analysis in ('rgb_map', 'download_rgb') else 'index', False, 'analysis')
			colours('map_colours')
		if analysis == 'map_figure':
			reports.append(missing('analysis', analysis, 'the panel adds the map as a layer (Add the layer to the map), '
			                       'and Figure (print layout)… makes its figure in QGIS'))
		if analysis == 'export_image':
			used.add('resolution')
			field('resolution', p.get('resolution'), 'resolution' in p)
		if analysis == 'region_stats':
			used.update(('zones', 'stats'))
			zones = p.get('zones')
			if isinstance(zones, dict) and zones.get('variable'):
				field('zones', zones)
			else:
				reports.append(missing('zones', zones, 'the panel computes the statistics of each band of a fixed layer '
				                       'or class of a categorical layer (Gradients → Bands of)'))
			if 'stats' in p:
				field('stats', list(p['stats']) if isinstance(p['stats'], (list, tuple)) else [p['stats']])
	elif analysis == 'area_by_class':
		used.update(('landcover', 'year', 'other_year', 'breaks', 'trend'))
		if p.get('landcover'):
			field('area_kind', 'landcover')
			field('area_map', {k: p.get(k) for k in ('landcover', 'year', 'other_year')}, True, 'landcover')
		elif p.get('breaks') is not None:
			field('area_kind', 'breaks')
			field('area_breaks', breaks_text(p['breaks']), True, 'breaks')
			take('map_metric', 'metric', METRICS, 'median' if p.get('metric') is None else _MISSING)
			take('temporal', choices=TEMPORAL)
			take('interannual', choices=METRICS)
		elif p.get('trend'):
			field('area_kind', 'trend')
			take('trend_step', 'step', TREND_STEPS)
			take('trend_part', 'part')
			take('trend_metric', 'metric', METRICS, 'mean' if p.get('metric') is None else _MISSING)
			take('trend_test', 'test', TREND_TESTS)
		else:
			field('area_kind', 'classes')
	elif analysis == 'timelapse':
		take('anim_step', 'step', ANIMATION_STEPS)
		take('anim_metric', 'metric', METRICS)
		used.add('fps')
		field('anim_fps', p.get('fps', defaults.get('fps')), 'fps' in p, 'fps')
		colours('anim_colours')
		used.add('same_colours')
		field('anim_same', p.get('same_colours') is not False, 'same_colours' in p, 'same_colours')
	elif burn:  # the index and the sensor in any case, as services.burn_severity takes them
		if p.get('index') is not None:
			p['index'] = {i.lower(): i for i in services.BURN_INDICES}.get(str(p['index']).lower(), p['index'])
		take('fire_index', 'index', FIRE_INDICES)
		used.update(('sensor', 'collection', 'perimeter', 'burned_min', 'min_ha', 'seed', 'largest', 'offset_region'))
		sensor = p.get('sensor', defaults.get('sensor'))
		modis = sensor is not None and catalog.name_key(sensor) == 'modis'
		# MODIS: Terra without a collection, as services.burn_severity (its collection only switches to Aqua)
		value = (p.get('collection') or FIRE_MODIS[0][1]) if modis else canonical(sensor, [v for _, v in FIRE_SENSORS])
		index = fields['fire_index']['value'] if 'fire_index' in fields else None
		if modis and 'Modis' not in services.BURN_SENSORS.get(index, ('Modis',)):
			reports.append(missing('sensor', p['sensor'], f'MODIS only with the index RdNBR, not {index}'))
		elif value in [v for _, v in FIRE_SENSORS + FIRE_MODIS]:
			field('fire_sensor', value, True, 'sensor')
			if not modis and p.get('collection'):
				reports.append(missing('collection', p['collection'], f'{value} takes no collection in the panel'))
		else:
			reports.append(missing('sensor', p.get('collection') if modis else p.get('sensor'),
			                       'the panel has Sentinel-2, Landsat and MODIS Terra or Aqua (MOD09GA, MYD09GA)'))
		keep = 'largest' if p.get('largest') else 'seed' if p.get('seed') else 'all'
		if p.get('largest') and p.get('seed'):  # as the services: one or the other
			reports.append(missing('seed', p['seed'], 'seed or largest, not both: the panel keeps the largest patch'))
		field('fire_perimeter', {'on': bool(p.get('perimeter')), 'burned_min': p.get('burned_min'),
		                         'min_ha': p.get('min_ha'), 'keep': keep,
		                         **({'seed': p['seed']} if p.get('seed') else {})}, 'perimeter' in p, 'perimeter')
		if p.get('offset_region'):  # a region of the parameters: the panel takes a layer of polygons of the project
			reports.append(missing('offset_region', p['offset_region'], 'choose its polygons, a layer of the project, in '
			                       'Offset region'))

	# what the panel has no option for: fine at its default
	for name, value in p.items():
		default = defaults.get(name, _MISSING)
		if name in used or value == default:
			continue
		reports.append(missing(name, value, f'the panel always uses the pixels of the data, up to {MAP_PIXELS:,} '
		                       'pixels (a bigger region is not computed: Export to Google Drive)' if name == 'max_pixels'
		                       else 'the panel has no option for it' +
		                       ('' if default in (_MISSING, None) else f' (it uses {json.dumps(default)})')))
	return key, fields, reports


class InfoButton(QToolButton):
	"""Small button ⓘ beside an option: a click shows its help (TEXT, or TEXT() if it is a function) in a balloon
	that stays until the next click; its links open in the browser."""

	def __init__(self, text):
		super().__init__()
		self.help_text = text
		icon = QgsApplication.getThemeIcon('/mActionPropertiesWidget.svg')  # a blue ⓘ in QGIS 3 and 4
		if icon.isNull():
			self.setText('ⓘ')
		else:
			self.setIcon(icon)
		self.setAutoRaise(True)
		self.setToolTip('Help')
		self.clicked.connect(self.show_help)

	def help(self):
		return self.help_text() if callable(self.help_text) else self.help_text

	def show_help(self):
		QWhatsThis.showText(self.mapToGlobal(QPoint(0, self.height())), self.help(), self)

	def event(self, e):
		if e.type() == QEvent.Type.WhatsThisClicked:  # a link of the balloon
			QDesktopServices.openUrl(QUrl(e.href()))
			QWhatsThis.hideText()
			return True
		return super().event(e)


def plugin_released():
	"""The date of the release of the plugin: __released__ of the package monitoreo it carries (ext/, released with
	it, whatever package Python finds first), or of the package in use when it carries none (from the code); None for a
	package older than the date."""
	path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ext', 'monitoreo', '__init__.py')
	try:
		with open(path, encoding='utf-8') as f:
			found = re.search(r"^__released__\s*=\s*['\"]([^'\"]+)", f.read(), re.M)
		if found:
			return found.group(1)
	except OSError:
		pass
	import monitoreo
	return getattr(monitoreo, '__released__', None)


def plugin_version():
	"""The version of the plugin, from its metadata.txt."""
	import configparser
	meta = configparser.ConfigParser()
	meta.read(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'metadata.txt'), encoding='utf-8')
	return meta.get('general', 'version', fallback='?')


def takes(service, name):
	"""Whether the function SERVICE of monitoreo.services has the argument NAME."""
	return name in inspect.signature(service).parameters


def given_colours(given, lo, hi):
	"""The ends of a colour ramp: those of GIVEN ((vmin, vmax), or None) that are not None, otherwise LO and HI (those
	of the map)."""
	vmin, vmax = given or (None, None)
	return (lo if vmin is None else vmin), (hi if vmax is None else vmax)


def stretch_note(res):
	"""How the colour ramp of the map RES was stretched, in words (its stretch: see monitoreo.maps.stretch_of), with
	the range: e.g. «colours from 0.12 to 0.85: stretched between the percentiles 1 and 99 of ...»; '' without a
	range."""
	lo, hi = res.get('min'), res.get('max')
	if lo is None or hi is None:
		return ''
	text = (res.get('stretch') or {}).get('text') if isinstance(res.get('stretch'), dict) else None
	return f'colours from {lo:.4g} to {hi:.4g}' + (f' ({text})' if text else '')


class ColourRange(QWidget):
	"""Colour range of the maps of a group of the panel: the percentiles (low and high, by default maps.STRETCH, 1 and
	99) of the values of each map between which its colour ramp is stretched, and an optional minimum and maximum
	(either of them: the other end from its percentile)."""

	def __init__(self):
		super().__init__()
		row = QHBoxLayout(self)
		row.setContentsMargins(0, 0, 0, 0)
		self.low, self.high = QDoubleSpinBox(), QDoubleSpinBox()
		for box, value, tip in ((self.low, maps.STRETCH[0], 'Low percentile of the values of the map (the first '
		                         'colour of the ramp)'),
		                        (self.high, maps.STRETCH[1], 'High percentile of the values of the map (the last '
		                         'colour of the ramp)')):
			box.setRange(0, 100)
			box.setDecimals(2)  # e.g. 2.5 and 97.5
			box.setPrefix('p')
			box.setValue(value)
			box.setToolTip(tip)
		self.vmin, self.vmax = QLineEdit(), QLineEdit()
		self.vmin.setPlaceholderText('min')
		self.vmax.setPlaceholderText('max')
		self.vmin.setToolTip('Minimum of the colour ramp (optional: empty, from the low percentile)')
		self.vmax.setToolTip('Maximum of the colour ramp (optional: empty, from the high percentile)')
		for w in (self.low, self.high, self.vmin, self.vmax):
			row.addWidget(w, 1)
		# whether the user chose the percentiles (also 1 and 99): else the true colour takes its own (RGB_STRETCH)
		self.chosen = False
		for box in (self.low, self.high):
			box.valueChanged.connect(lambda _value: setattr(self, 'chosen', True))

	def percentiles(self):
		"""The two percentiles chosen (lo, hi), checked (maps.check_percentiles: ValueError if not lo < hi)."""
		try:
			return maps.check_percentiles([self.low.value(), self.high.value()])
		except ValueError as e:
			raise ValueError(f'Colour range: {e}') from None

	def given(self):
		"""The minimum and the maximum written (None where empty); ValueError if not numbers, or if min >= max."""
		out = []
		for edit, name in ((self.vmin, 'minimum'), (self.vmax, 'maximum')):
			text = edit.text().strip().replace(',', '.')
			try:
				out.append(float(text) if text else None)
			except ValueError:
				raise ValueError(f'Colour range: the {name} must be a number, not {edit.text()!r}') from None
		if None not in out and out[0] >= out[1]:
			raise ValueError(f'Colour range: the minimum ({out[0]:g}) must be lower than the maximum ({out[1]:g})')
		return tuple(out)

	def args(self, service=None):
		"""The arguments of the colour range for the function SERVICE of monitoreo.services (only those it has, all
		without it): percentiles (if not the default ones of SERVICE: maps.STRETCH, or maps.RGB_STRETCH for the true
		colour, which takes 1 and 99 too when the user chose them), vmin and vmax (if given)."""
		pct, (vmin, vmax) = self.percentiles(), self.given()
		rgb = service is not None and service in (services.rgb_map, services.download_rgb)
		chosen = getattr(self, 'chosen', False)
		out = {}
		if (chosen if rgb else tuple(pct) != tuple(maps.STRETCH)):  # the true colour: its own unless chosen
			out['percentiles'] = list(pct)
		if vmin is not None:
			out['vmin'] = vmin
		if vmax is not None:
			out['vmax'] = vmax
		return {k: v for k, v in out.items() if service is None or takes(service, k)}

	def put(self, value):
		"""Set the fields from VALUE ({'percentiles', 'vmin', 'vmax'}, as the parameters of a map; the defaults
		without them)."""
		lo, hi = maps.check_percentiles(value.get('percentiles'))
		self.low.setValue(lo)
		self.high.setValue(hi)
		self.chosen = value.get('percentiles') is not None
		self.vmin.setText(number(value.get('vmin')))
		self.vmax.setText(number(value.get('vmax')))

	def summary(self):
		"""What is chosen, for the title of its folded group: the minimum and maximum written and the percentiles if
		not the default ones; empty with the defaults."""
		parts = [f'{name} {edit.text().strip()}' for edit, name in ((self.vmin, 'min'), (self.vmax, 'max'))
		         if edit.text().strip()]
		if (self.low.value(), self.high.value()) != tuple(maps.STRETCH):
			parts.insert(0, f'p{self.low.value():g}–p{self.high.value():g}')
		return ', '.join(parts)


def sync_folds(widget):
	"""Show the folded groups (QgsCollapsibleGroupBox) visible in WIDGET as they are: one folded or unfolded while
	hidden (in a folded group or another tab, e.g. by applying parameters, or the land cover mask checked) only
	records it, and would look as before when shown."""
	for box in widget.findChildren(QgsCollapsibleGroupBox):
		folded = box.maximumHeight() < 16777215  # how QgsCollapsibleGroupBox folds: its height
		if box.isVisible() and folded != box.isCollapsed():
			scroll = box.scrollOnExpand()
			box.setScrollOnExpand(False)
			collapsed = box.isCollapsed()
			box.setCollapsed(not collapsed)
			box.setCollapsed(collapsed)
			box.setScrollOnExpand(scroll)


class Section(QgsCollapsibleGroupBox):
	"""A group of the panel folded under its title, as the sections of the Earth Engine app (section of
	gee/monitoreo_app.js): only the groups the user opens show their options, and a folded group shows on its title
	what is chosen in it (SUMMARY, a function that gives that text; refresh). Its widgets go in CONTENT (with a layout
	of their own), built even when folded: folding only hides CONTENT, so that what the panel shows or hides in it
	keeps its own state (see MonitorEODock.shown). OPEN: unfolded at first. Its state is not kept between sessions,
	as in the app."""

	def __init__(self, title, open=False, summary=None):
		super().__init__(title)
		self.base, self.summary = title, summary
		self.setSaveCollapsedState(False)
		self.setSaveCheckedState(False)
		lay = QVBoxLayout(self)
		lay.setContentsMargins(4, 4, 4, 4)
		self.content = QWidget()
		self.content.setProperty('fold', True)  # hidden by folding, not by the panel (MonitorEODock.shown)
		lay.addWidget(self.content)
		self.setScrollOnExpand(False)
		self.setCollapsed(not open)
		self.collapsedStateChanged.connect(self.refresh)
		self.collapsedStateChanged.connect(lambda collapsed: collapsed or sync_folds(self.content))
		self.refresh()

	def refresh(self, collapsed=None):
		"""The title, with the summary while folded (COLLAPSED: as collapsedStateChanged says, else isCollapsed)."""
		text = ''
		if self.summary is not None and (self.isCollapsed() if collapsed is None else collapsed):
			try:
				text = self.summary() or ''
			except Exception:  # a field not built yet, or not valid: the title alone
				text = ''
		self.setTitle(self.base + (f' · {text}' if text else ''))


def info(field, text):
	"""FIELD (a widget, or a row of them) with an InfoButton with TEXT at its right, for a row of a QFormLayout."""
	if isinstance(field, QHBoxLayout):
		row = field
	else:
		row = QHBoxLayout()
		row.addWidget(field, 1)
	row.addWidget(InfoButton(text))
	return row


class MonitorEODock(QDockWidget):

	def __init__(self, iface):
		super().__init__('MonitorEO')
		self.iface = iface
		self.setObjectName('MonitorEODock')
		self.tasks = []          # running QgsTasks (kept so that Python does not delete them)
		self.series = []         # results of the time series of this session
		self.series_dialogs = {}  # their windows, by index in self.series
		self.exports = []        # export tasks of Earth Engine being followed
		self.timer = QTimer(self)
		self.timer.timeout.connect(self.poll_exports)
		self.group_boxes = {}  # the group of each analysis of the panel (see PANEL)
		self.applied = []  # what applying some parameters did besides setting fields (a layer added)
		self.build()

	# Interface --------------------------------------------------------------------------------------------------

	def build(self):
		s = QgsSettings()
		body = QWidget()
		main = QVBoxLayout(body)
		row = QHBoxLayout()
		row.addWidget(self.version_label())
		row.addStretch()
		row.addWidget(self.feedback_button())
		main.addLayout(row)
		row = QHBoxLayout()  # the parameters of an analysis, pasted or opened (each analysis copies its own)
		row.addStretch()
		row.addWidget(self.apply_button())
		row.addWidget(InfoButton(HELP['parameters']))
		main.addLayout(row)
		# what the analyses use (the region, the variable, the period and the pixel filters), above the tabs other
		# than Data, whose groups set it (refresh_titles)
		self.context = QLabel()
		self.context.setWordWrap(True)
		self.context.setStyleSheet('font-size: 11px; color: #444;')
		main.addWidget(self.context)
		# the groups of the panel in tabs, each group folded under its title as the sections of the Earth Engine app
		# (Section): the data (region, variable, pixel filters), then the analyses
		self.tabs = QTabWidget()
		self.tabs.setUsesScrollButtons(True)
		self.pages, self.tab_widgets = {}, {}  # the layout of each tab, and its widget
		main.addWidget(self.tabs, 1)
		data = self.tab('Data')

		box = Section('Google Earth Engine', open=True, summary=lambda: self.project.text().strip() or 'shared account')
		self.project_box = box
		f = QFormLayout(box.content)
		self.project = QLineEdit(s.value(SETTINGS + 'project', os.environ.get('EE_PROJECT', '')))
		self.project.setPlaceholderText('empty: shared account of MonitorEO · or your Google Cloud project')
		row = QHBoxLayout()
		row.addWidget(self.project)
		b = QPushButton('Connect')
		b.clicked.connect(self.connect)
		row.addWidget(b)
		b = QPushButton('Authenticate…')
		b.setToolTip('Sign in with your Google account in the browser (as earthengine authenticate), to compute with '
		             'your project and export to Google Drive')
		b.clicked.connect(self.authenticate)
		row.addWidget(b)
		self.projects_button = b = QPushButton('Projects…')
		b.setToolTip('Your Google Cloud projects registered in Earth Engine, to choose one (after Authenticate…)')
		b.clicked.connect(lambda: self.list_projects())
		row.addWidget(b)
		f.addRow('Project', info(row, HELP['project']))
		data.addWidget(box)

		box = Section('Region', open=True, summary=self.region_summary)
		self.region_box = box
		f = QFormLayout(box.content)
		self.region_kind = combo(REGIONS)
		self.region_kind.currentIndexChanged.connect(self.region_changed)
		f.addRow('Region', info(self.region_kind, HELP['region']))
		self.layer = QgsMapLayerComboBox()
		self.layer.setFilters(Qgis.LayerFilter.PolygonLayer)
		self.name_field = QgsFieldComboBox()
		self.name_field.setAllowEmptyFieldName(True)
		self.layer.layerChanged.connect(lambda layer: self.sync_fields())
		# the layer box can pick a new layer by itself without layerChanged (QGIS 4): follow the project too, and stop
		# following it in stop(), or the project would call this panel once deleted (when the plugin is reloaded)
		self.project_signals = [QgsProject.instance().layersAdded, QgsProject.instance().layersRemoved]
		for signal in self.project_signals:
			signal.connect(self.project_layers_changed)
		self.sync_fields()
		self.layer_row = QWidget()
		lf = QFormLayout(self.layer_row)
		lf.setContentsMargins(0, 0, 0, 0)
		lf.addRow('Layer', info(self.layer, HELP['layer']))
		lf.addRow('Name', info(self.name_field, HELP['name_field']))
		f.addRow(self.layer_row)
		self.wdpa_row = QWidget()
		wl = QHBoxLayout(self.wdpa_row)
		wl.setContentsMargins(0, 0, 0, 0)
		self.wdpa_text = QLineEdit()
		self.wdpa_text.setPlaceholderText('name of the area (e.g. Sierra Nevada)')
		self.wdpa_text.returnPressed.connect(self.search_wdpa)
		wl.addWidget(self.wdpa_text)
		self.ramsar = QCheckBox('Ramsar only')
		self.ramsar.setToolTip('Only the Ramsar sites (Wetlands of International Importance)')
		wl.addWidget(self.ramsar)
		b = QPushButton('Search')
		b.clicked.connect(self.search_wdpa)
		wl.addWidget(b)
		wl.addWidget(InfoButton(HELP['wdpa']))
		f.addRow(self.wdpa_row)
		self.wdpa = QComboBox()
		self.wdpa_field = QWidget()  # the list and its ⓘ, shown only with the region WDPA
		row = info(self.wdpa, HELP['wdpa_area'])
		row.setContentsMargins(0, 0, 0, 0)
		self.wdpa_field.setLayout(row)
		f.addRow('Area', self.wdpa_field)
		self.wdpa_label = f.labelForField(self.wdpa_field)
		# administrative units: of FAO GAUL 2025 (levels 1 and 2), searched by name, level and country; or the
		# municipalities of Spain (level 3), by name or code of the INE
		self.admin_row = QWidget()
		al = QHBoxLayout(self.admin_row)
		al.setContentsMargins(0, 0, 0, 0)
		self.admin_text = QLineEdit()
		self.admin_text.setPlaceholderText(ADMIN_HINTS[1])
		self.admin_text.returnPressed.connect(self.search_admin)
		al.addWidget(self.admin_text)
		self.admin_level = combo(ADMIN_LEVELS)
		self.admin_level.setToolTip(ADMIN_LEVEL_TIP)
		self.admin_level.currentIndexChanged.connect(lambda i: self.admin_level_changed())
		al.addWidget(self.admin_level)
		self.admin_country = QLineEdit()
		self.admin_country.setPlaceholderText('ISO3')
		self.admin_country.setToolTip(ADMIN_COUNTRY_TIP)
		self.admin_country.setMaximumWidth(60)
		self.admin_country_typed = ''  # the country written for levels 1 and 2, back when leaving level 3
		al.addWidget(self.admin_country)
		b = QPushButton('Search')
		b.clicked.connect(self.search_admin)
		al.addWidget(b)
		al.addWidget(InfoButton(HELP['admin']))
		f.addRow(self.admin_row)
		self.admin = QComboBox()
		f.addRow('Unit', self.admin)
		self.admin_label = f.labelForField(self.admin)
		# the oceans and seas (the sea areas of the IHO, Marine Regions), searched by name in the index of the package,
		# without Earth Engine
		self.sea_row = QWidget()
		sl = QHBoxLayout(self.sea_row)
		sl.setContentsMargins(0, 0, 0, 0)
		self.sea_text = QLineEdit()
		self.sea_text.setPlaceholderText('name of the sea in English (e.g. Alboran)')
		self.sea_text.returnPressed.connect(self.search_seas)
		sl.addWidget(self.sea_text)
		b = QPushButton('Search')
		b.clicked.connect(self.search_seas)
		sl.addWidget(b)
		sl.addWidget(InfoButton(HELP['sea']))
		f.addRow(self.sea_row)
		self.sea = QComboBox()
		f.addRow('Sea', self.sea)
		self.sea_label = f.labelForField(self.sea)
		self.country = QLineEdit()
		self.country.setPlaceholderText('ISO3 code of the country (e.g. ESP)')
		self.country_field = QWidget()
		row = info(self.country, HELP['country'])
		row.setContentsMargins(0, 0, 0, 0)
		self.country_field.setLayout(row)
		f.addRow('Country', self.country_field)
		self.country_label = f.labelForField(self.country_field)
		data.addWidget(box)

		box = Section('Variable and period', open=True, summary=self.variable_summary)
		self.variable_box = box
		data.addWidget(box)
		f = QFormLayout(box.content)
		# first the theme (catalog.THEMES), then the variables of that theme; after them, as in the Earth Engine app,
		# the themes of the data of Earth Engine outside the catalog (catalog.OTHER_THEMES, with 'data'), which have no
		# variables: any image or collection by its ID, and the GEE Community Catalog
		self.theme = QComboBox()
		themes = services.themes('en')
		for t in themes:
			self.theme.addItem(t['name'], t['key'])
		self.theme.addItem('All the variables', None)
		self.data_themes = {t['key']: t['data'] for t in themes if t.get('data')}
		f.addRow('Theme', info(self.theme, HELP['theme']))
		f.addRow(self.data_block(s))
		# the English names of the catalog (vname_en, type_en); RBR and RdNBR, which compare two periods: only the burn
		# severity (Burn severity of a fire, below)
		self.all_variables = [v for v in services.list_variables(lang='en') if not v.get('two_periods')]
		self.catalog_choice = None  # the variable chosen before a theme of other data, chosen again when back
		self.variable = QComboBox()
		self.variable_field = QWidget()  # the list and its ⓘ, hidden in the themes of other data
		row = info(self.variable, lambda: variable_help(self.variable.currentData(), self.described()))
		row.setContentsMargins(0, 0, 0, 0)
		self.variable_field.setLayout(row)
		f.addRow('Variable', self.variable_field)
		self.variable_label = f.labelForField(self.variable_field)
		self.fill_variables('NDVI · Sentinel-2')
		self.theme.currentIndexChanged.connect(lambda i: self.fill_variables())
		self.start = QDateEdit(QDate.fromString(s.value(SETTINGS + 'start', '2020-01-01'), 'yyyy-MM-dd'))
		self.end = QDateEdit(QDate.fromString(s.value(SETTINGS + 'end', '2021-12-31'), 'yyyy-MM-dd'))
		for d in (self.start, self.end):
			d.setCalendarPopup(True)
			d.setDisplayFormat('yyyy-MM-dd')
		row = QHBoxLayout()
		row.addWidget(self.start)
		row.addWidget(QLabel('to'))
		row.addWidget(self.end)
		f.addRow('Period', info(row, HELP['period']))
		self.compare_on = QCheckBox('other period:')
		self.compare_on.setToolTip('Compares the reference period (the one above) with this one: the time series gives '
		                           'the mean of each part of the year in the two periods and their difference, and the '
		                           'map, the difference (this period minus the reference period)')
		self.other_start = QDateEdit(QDate.fromString(s.value(SETTINGS + 'other_start', '2023-01-01'), 'yyyy-MM-dd'))
		self.other_end = QDateEdit(QDate.fromString(s.value(SETTINGS + 'other_end', '2023-12-31'), 'yyyy-MM-dd'))
		row = QHBoxLayout()
		row.addWidget(self.compare_on)
		for i, d in enumerate((self.other_start, self.other_end)):
			d.setCalendarPopup(True)
			d.setDisplayFormat('yyyy-MM-dd')
			d.setEnabled(False)
			self.compare_on.toggled.connect(d.setEnabled)
			if i:
				row.addWidget(QLabel('to'))
			row.addWidget(d)
		f.addRow('Compare with', info(row, HELP['compare']))
		self.season_on = QCheckBox('only')
		self.season_start = QLineEdit('06-01')
		self.season_end = QLineEdit('09-30')
		for w in (self.season_start, self.season_end):
			w.setMaximumWidth(60)
			w.setPlaceholderText('MM-DD')
		row = QHBoxLayout()
		row.addWidget(self.season_on)
		row.addWidget(self.season_start)
		row.addWidget(QLabel('to'))
		row.addWidget(self.season_end)
		row.addWidget(QLabel('of each year'))
		row.addStretch()
		f.addRow('Season', info(row, HELP['season']))
		box = Section('Pixel filters', summary=self.pixel_summary)
		self.pixels_box = box
		data.addWidget(box)
		pixels = QVBoxLayout(box.content)
		pixels.setContentsMargins(0, 0, 0, 0)
		f = QFormLayout()
		pixels.addLayout(f)
		self.filters = {}
		self.chosen_filters = None  # the filters checked by the user while the variable chosen sets some (set_filters)
		self.set_filters = set()  # the filters set and greyed out by the variable: all if fixed, else what it measures
		row = QHBoxLayout()
		for key, label in (('clouds', 'clouds'), ('water', 'water'), ('snow', 'snow'), ('aerosols', 'aerosols')):
			self.filters[key] = QCheckBox(label)
			self.filters[key].setChecked(True)
			row.addWidget(self.filters[key])
		f.addRow('Remove pixels with', info(row, lambda: filters_help(self.variable.currentData())))
		self.cloud_score = QCheckBox('Sentinel-2 clouds with Cloud Score+')  # unchecked, with SCL: in its help ⓘ
		self.cloud_score.setChecked(True)
		f.addRow('', info(self.cloud_score, HELP['cloud_score']))
		self.snow_ndsi = QCheckBox(f'Snow also by its NDSI ≥ {sensors.SNOW_NDSI_DEFAULT:g} (Sentinel-2, Landsat)')
		self.snow_ndsi.setChecked(False)  # off: the snow that the QA band misses, in its help ⓘ
		f.addRow('', info(self.snow_ndsi, HELP['snow_ndsi']))
		self.filters['snow'].toggled.connect(lambda _on: self.snow_ndsi_enabled())  # greyed out without the snow filter
		self.topographic = QCheckBox('Topographic correction (Landsat)')  # off: SCS+C, in its help ⓘ
		self.topographic.setChecked(False)
		f.addRow('', info(self.topographic, HELP['topographic']))
		self.harmonize = QCheckBox('Harmonize Landsat 5 and 7 with Landsat 8 and 9 (Roy et al. 2016)')
		self.harmonize.setChecked(False)  # off: for long series and trends of Landsat, in its help ⓘ
		f.addRow('', info(self.harmonize, HELP['harmonize']))
		self.landsat7 = QCheckBox('Also Landsat 7 after 2003 (with stripes without data)')
		self.landsat7.setChecked(False)  # off: the images of the failure of its scan line corrector, in its help ⓘ
		f.addRow('', info(self.landsat7, HELP['landsat7']))
		self.landcover_group(s, pixels)
		f = QFormLayout()
		pixels.addLayout(f)
		# where: up to two conditions on variables, the only pixels of the region that pass them all; on a categorical
		# layer (ECOREGION, BIOME), its classes to keep or to leave out instead of a min and a max
		self.where = []
		for i, default in enumerate(('ELEVATION · Copernicus', 'SLOPE · Copernicus')):
			on, var, lo, hi, unit = QCheckBox(), QComboBox(), QLineEdit(), QLineEdit(), QLabel('')
			keep, codes, pick = combo(CLASS_CONDITIONS, 'classes'), QLineEdit(), QPushButton('Classes…')
			codes.setPlaceholderText('codes, e.g. 12, 4')
			pick.setToolTip('Choose a class of the layer from its list (code and name): its code is added to the codes')
			for v in services.list_variables(lang='en'):
				if not v.get('two_periods'):
					var.addItem(f"{v['variable']} · {v['sensor']}", v)
					var.setItemData(var.count() - 1, f"{v['name']} ({v['unit']}), {v['dates']}",
					                Qt.ItemDataRole.ToolTipRole)
			var.setCurrentIndex(max(0, var.findText(default, Qt.MatchFlag.MatchStartsWith)))
			for w, text in ((lo, 'min'), (hi, 'max')):
				w.setPlaceholderText(text)
				w.setMaximumWidth(70)
			row = QHBoxLayout()
			row.addWidget(on)
			row.addWidget(var, 1)
			f.addRow('Only the pixels where' if i == 0 else 'and where', info(row, HELP['where']) if i == 0 else row)
			row = QHBoxLayout()
			between, also = QLabel('between'), QLabel('and')
			for w in (between, lo, also, hi, unit, keep, codes, pick):
				row.addWidget(w)
			row.addStretch()
			f.addRow('', row)
			condition = {'on': on, 'variable': var, 'min': lo, 'max': hi, 'unit': unit, 'keep': keep, 'codes': codes,
			             'pick': pick, 'labels': (between, also)}
			self.where.append(condition)
			on.toggled.connect(self.where_changed)
			var.currentIndexChanged.connect(self.where_changed)
			pick.clicked.connect(lambda checked=False, c=condition: self.pick_class(c))

		page = self.tab('Series')
		box = Section('Time series', open=True)
		self.series_box = box  # greyed out for the fixed layers without dates (elevation, slope)
		f = QFormLayout(box.content)
		self.step = combo(STEPS, 'monthly')
		self.ts_metric = combo(METRICS, 'mean')
		self.stat = combo(STATS, 'mean')
		f.addRow('Step', info(self.step, HELP['step']))
		f.addRow('Metric of each step', info(self.ts_metric, HELP['ts_metric']))
		f.addRow('Statistic of the region', info(self.stat, HELP['stat']))
		self.min_coverage = QCheckBox(f'no value in the steps with valid pixels in less than {MIN_COVERAGE:.0%} of the '
		                              'region (also the trend table and the export of the series)')
		self.min_coverage.setChecked(False)  # off: also for the trend table and the export (the same statistic)
		f.addRow('Minimum coverage', info(self.min_coverage, HELP['min_coverage']))
		chart = Section('Chart', summary=self.chart_summary)
		self.chart_box = chart
		f.addRow(chart)
		series_form, f = f, QFormLayout(chart.content)
		self.doy = QCheckBox('a line per year, over the days of the year')
		self.doy.setToolTip('The chart with a line per year (from January to December), to compare the years: the '
		                    'snow seasons, the greening of each spring... Not with the annual step')
		f.addRow('Line per year', info(self.doy, HELP['doy']))
		# the seasonal profile instead of a line per year: a metric between the years of each step of the year, and a
		# second variable of the catalog with dates on a right axis (services.time_series: interannual, other_variable)
		self.doy_interannual = combo(DOY_INTERANNUAL, None)
		self.doy_interannual.setToolTip('A line per year, or a line per variable: this metric of the values of each '
		                                'step of the year (each month, 16-day period or day) in the years of the period')
		self.doy_other = QComboBox()
		self.doy_other.addItem('None', None)
		self.doy_other.setToolTip('A second variable on a right axis, computed as the first one (e.g. the NDSI and the '
		                          'NDVI)')
		shown = set()
		for v in self.all_variables:  # the variables with dates, once each (of MODIS Terra and Aqua, the first one)
			if v.get('static') or (v['variable'], v['sensor']) in shown:
				continue
			shown.add((v['variable'], v['sensor']))
			self.doy_other.addItem(f"{v['variable']} ({v['sensor']})", {'variable': v['variable'], 'sensor': v['sensor']})
			self.doy_other.setItemData(self.doy_other.count() - 1, f"{v['name']} ({v['unit']}), {v['dates']}, "
			                           f"{v['collection']}", Qt.ItemDataRole.ToolTipRole)
		f.addRow('Between years', info(self.doy_interannual, HELP['doy_interannual']))
		f.addRow('Right axis', info(self.doy_other, HELP['doy_other']))
		self.doy.toggled.connect(self.doy_changed)
		self.doy_interannual.currentIndexChanged.connect(self.doy_interannual_changed)
		self.doy_other.currentIndexChanged.connect(self.doy_other_changed)
		self.doy_changed()
		f = series_form
		b = QPushButton('Compute the time series')
		b.clicked.connect(self.run_series)
		f.addRow(self.with_parameters(b, 'series'))
		self.series_list = QComboBox()  # the series computed in this session, to open them again
		self.series_list.setToolTip('Series computed in this QGIS session')
		self.show_series_button = QPushButton('Show')
		self.show_series_button.setToolTip('Open again the chart and the table of the chosen series')
		self.show_series_button.clicked.connect(self.show_series)
		row = QHBoxLayout()
		row.addWidget(self.series_list, 1)
		row.addWidget(self.show_series_button)
		f.addRow('Series', info(row, HELP['series_list']))
		self.update_series_list()
		page.addWidget(box)

		box = Section('Trends (Mann-Kendall and Sen)')
		self.trends_box = box
		box.setToolTip("Trend of each part of the year over the years of the period: Kendall's τ, Mann-Kendall Z and "
		               "p-value (or corrected for autocorrelation: Hamed-Rao, TFPW), and Sen's slope (change per "
		               "year). Better with 8 years or more")
		f = QFormLayout(box.content)
		self.trend_step = combo(TREND_STEPS, 'annual')
		self.trend_part = QComboBox()
		self.trend_step.currentIndexChanged.connect(self.update_trend_parts)
		self.update_trend_parts()
		self.trend_metric = combo(METRICS, 'mean')
		self.trend_test = combo(TREND_TESTS, 'mk')
		self.trend_alpha = QCheckBox('only pixels with a significant trend (p < 0.05)')
		f.addRow('Parts of the year', info(self.trend_step, HELP['trend_step']))
		f.addRow('Metric of each year', info(self.trend_metric, HELP['trend_metric']))
		f.addRow('Test', info(self.trend_test, HELP['trend_test']))
		b = QPushButton('Trend table of the region')
		b.setToolTip('Trend of each part of the year of the statistic of the region (that of the time series)')
		b.clicked.connect(self.run_trend_table)
		f.addRow(self.with_parameters(b, 'trend_table'))
		f.addRow('Part of the year of the map', info(self.trend_part, HELP['trend_part']))
		options = Section('Options of the map', summary=lambda: ', '.join(
			x for x in ('significant only' if self.trend_alpha.isChecked() else '', self.trend_colours.summary()) if x))
		self.trend_options_box = options
		f.addRow(options)
		trend_form, f = f, QFormLayout(options.content)
		f.addRow('', info(self.trend_alpha, HELP['trend_alpha']))
		self.trend_colours = ColourRange()
		f.addRow('Colour range', info(self.trend_colours, HELP['trend_colours']))
		f = trend_form
		b = QPushButton('Trend map')
		b.setToolTip("Temporary GeoTIFF with Sen's slope, τ, Z, p-value, intercept and number of years of each pixel "
		             '(queryable with the Identify Features tool)')
		b.clicked.connect(self.run_trend_map)
		f.addRow(self.with_parameters(b, 'trend_map'))
		page.addWidget(box)

		page = self.tab('Maps')
		box = Section('Map', open=True)
		self.group_boxes['map'] = box
		f = QFormLayout(box.content)
		self.map_metric = combo(METRICS, 'median')
		self.temporal = combo(TEMPORAL, 'period')
		self.interannual = combo(METRICS, 'mean')
		f.addRow('Metric', info(self.map_metric, HELP['map_metric']))
		f.addRow('Temporal aggregation', info(self.temporal, HELP['temporal']))
		f.addRow('Metric between years', info(self.interannual, HELP['interannual']))
		self.map_kind = combo(MAP_KINDS, 'index')  # the map of the variable, its true colour or both
		f.addRow('Layer', info(self.map_kind, HELP['map_kind']))
		colours = Section('Colours', summary=lambda: self.map_colours.summary())
		self.map_colours_box = colours
		f.addRow(colours)
		map_form, f = f, QFormLayout(colours.content)
		self.map_colours = ColourRange()
		f.addRow('Colour range', info(self.map_colours, HELP['map_colours']))
		self.map_same = QCheckBox('Same colours in every map of a series or trends (those of its first map)')
		self.map_same.setChecked(True)  # so that its dates can be compared, as the frames of an animation
		f.addRow('', info(self.map_same, HELP['map_same']))
		f = map_form
		b = QPushButton('Add the layer to the map')
		b.setToolTip('Downloads the map as a temporary GeoTIFF, with the values of the variable (queryable with the '
		             'Identify Features tool) or, with Layer, its true colour, always at the resolution of the data, up '
		             f'to {MAP_PIXELS / 1e6:g} million pixels (bigger regions: a warning, before computing anything)')
		b.clicked.connect(self.run_map)
		row = self.with_parameters(b, 'map')
		b = QPushButton('Figure (print layout)…')
		b.setToolTip('A print layout of QGIS with the map as the canvas shows it, its grid, legend, scale bar, north '
		             'arrow, title and the credits and citation of MonitorEO, to export as PDF, PNG or SVG')
		b.clicked.connect(self.make_layout)
		row.addWidget(b)
		f.addRow(row)
		page.addWidget(box)
		self.compare_on.toggled.connect(lambda on: self.update_map_kind())

		box = Section('Area by class')
		self.group_boxes['areas'] = box
		f = QFormLayout(box.content)
		self.area_kind = combo(AREA_KINDS, s.value(SETTINGS + 'area_kind', 'landcover'))
		f.addRow('Classes of', info(self.area_kind, HELP['area_kind']))
		self.area_map = QComboBox()
		for m in landcover.maps():
			self.area_map.addItem(f"{m['name']} · {m['m']} m · {m['coverage']}", m['key'])
		self.area_map.setCurrentIndex(max(0, self.area_map.findData(s.value(SETTINGS + 'area_map', 'WorldCover'))))
		self.area_year = QComboBox()
		self.area_change = QCheckBox('changes to')  # the changes of the map from its year to another
		self.area_change.setToolTip('The changes of the land cover map from the first year to the second: the hectares '
		                            'of each pair of classes, and a Sankey diagram of the broad land covers')
		self.area_other_year = QComboBox()
		self.area_other_year.setEnabled(False)
		self.area_change.toggled.connect(self.area_other_year.setEnabled)
		self.area_change.toggled.connect(lambda on: self.area_years_apart())
		row = QHBoxLayout()
		row.addWidget(self.area_map, 1)
		row.addWidget(self.area_year)
		row.addWidget(self.area_change)
		row.addWidget(self.area_other_year)
		self.area_map_row = QWidget()
		self.area_map_row.setLayout(row)
		row.setContentsMargins(0, 0, 0, 0)
		f.addRow('Map and year', self.area_map_row)
		self.area_map_label = f.labelForField(self.area_map_row)
		self.area_breaks = QLineEdit(s.value(SETTINGS + 'area_breaks', ''))
		self.area_breaks.setPlaceholderText('values separated by commas, e.g. 1500, 2000, 2500')
		f.addRow('Breaks', self.area_breaks)
		self.area_breaks_label = f.labelForField(self.area_breaks)
		self.fill_area_years()
		self.area_map.currentIndexChanged.connect(lambda i: self.fill_area_years())
		self.area_kind.currentIndexChanged.connect(lambda i: self.area_kind_changed())
		b = QPushButton('Compute the areas')
		b.setToolTip('Hectares and % of each class over each feature of the region, in a window with its chart and '
		             'table')
		b.clicked.connect(self.run_areas)
		f.addRow(self.with_parameters(b, 'areas'))
		self.area_kind_changed()
		page.addWidget(box)

		box = Section('Gradients (elevation bands and profiles)')
		self.group_boxes['zones'] = self.group_boxes['transect'] = box
		f = QFormLayout(box.content)
		self.zone_variable = QComboBox()  # the fixed layers: the elevation, the slope, the climate of WorldClim, and the
		for v in self.all_variables:  # categorical layers (ECOREGION, BIOME), whose classes are the zones (no breaks)
			if v.get('static'):
				self.zone_variable.addItem(f"{v['variable']} · {v['sensor']}", v)
		self.zone_variable.setCurrentIndex(max(0, self.zone_variable.findText('ELEVATION', Qt.MatchFlag.MatchStartsWith)))
		self.zone_breaks = QLineEdit(s.value(SETTINGS + 'zone_breaks', '1500, 2000, 2500, 3000'))
		self.zone_breaks.setPlaceholderText('e.g. 1500, 2000, 2500')
		row = QHBoxLayout()
		row.addWidget(self.zone_variable, 1)
		row.addWidget(self.zone_breaks, 1)
		f.addRow('Bands of', info(row, HELP['zones']))
		self.zone_variable.currentIndexChanged.connect(lambda i: self.zone_variable_changed())
		self.zone_variable_changed()
		b = QPushButton('Statistics of each band')
		b.setToolTip('The percentiles 25, 50 and 75 and the mean of the map of the variable (with the options of the group '
		             'Map) in each band of the elevation (or of another fixed layer), over each feature of the region')
		b.clicked.connect(self.run_zones)
		f.addRow(self.with_parameters(b, 'zones'))
		self.line_layer = QgsMapLayerComboBox()
		self.line_layer.setFilters(Qgis.LayerFilter.LineLayer)
		self.line_layer.setAllowEmptyLayer(True)
		f.addRow('Line', info(self.line_layer, HELP['transect']))
		b = QPushButton('Profile along the line')
		b.setToolTip('The map of the variable (with the options of the group Map) and the elevation along the selected '
		             'line of the layer (or its first one), every 1 % of its length (at least a pixel of the data)')
		b.clicked.connect(self.run_transect)
		f.addRow(self.with_parameters(b, 'transect'))
		page.addWidget(box)

		box = Section('Animation (timelapse)')
		self.animation_box = box  # greyed out for the fixed layers without dates (elevation, slope)
		f = QFormLayout(box.content)
		self.anim_step = combo(ANIMATION_STEPS, s.value(SETTINGS + 'anim_step', 'annual'))
		self.anim_metric = combo(METRICS, 'median')
		self.anim_fps = QDoubleSpinBox()
		self.anim_fps.setRange(0.5, 30)
		self.anim_fps.setDecimals(1)
		self.anim_fps.setValue(1)
		self.anim_fps.setSuffix(' frames per second')
		f.addRow('A frame per', info(self.anim_step, HELP['anim_step']))
		f.addRow('Metric of each frame', info(self.anim_metric, HELP['anim_metric']))
		f.addRow('Speed', info(self.anim_fps, HELP['anim_fps']))
		colours = Section('Colours', summary=lambda: self.anim_colours.summary())
		self.anim_colours_box = colours
		f.addRow(colours)
		anim_form, f = f, QFormLayout(colours.content)
		self.anim_colours = ColourRange()
		f.addRow('Colour range', info(self.anim_colours, HELP['anim_colours']))
		self.anim_same = QCheckBox('Same colours in every frame')
		self.anim_same.setChecked(True)  # so that the frames can be compared (services.timelapse)
		f.addRow('', info(self.anim_same, HELP['anim_same']))
		f = anim_form
		b = QPushButton('Make the animation')
		b.setToolTip('A GIF with a frame per step of the period, each with its date, in a window (it takes some '
		             'minutes: Earth Engine makes each frame)')
		b.clicked.connect(self.run_timelapse)
		f.addRow(self.with_parameters(b, 'animation'))
		page.addWidget(box)

		# the analyses of a theme (catalog.THEMES): only in the themes that have them, and with «All the variables»
		page = self.tab('Fire')
		box = Section('Burn severity of a fire (dNBR, RBR or RdNBR)', open=True)
		self.fire_box = box
		f = QFormLayout(box.content)
		self.fire_form(s, f)
		page.addWidget(box)

		page = self.tab('Export')
		box = Section('Export to Google Drive', open=True)
		self.group_boxes['export_map'] = self.group_boxes['export_series'] = box
		f = QFormLayout(box.content)
		self.resolution = QDoubleSpinBox()
		self.resolution.setRange(0, 100000)
		self.resolution.setSpecialValueText('that of the data')
		self.resolution.setSuffix(' m')
		f.addRow('Resolution', info(self.resolution, HELP['resolution']))
		self.folder = QLineEdit(s.value(SETTINGS + 'folder', 'MonitorEO'))
		f.addRow('Drive folder', info(self.folder, HELP['folder']))
		row = QHBoxLayout()
		b = QPushButton('Map (GeoTIFF)')
		b.clicked.connect(self.run_export_image)
		row.addWidget(b)
		b = QPushButton('Series (CSV)')
		b.clicked.connect(self.run_export_series)
		self.export_series_button = b
		row.addWidget(b)
		row.addWidget(self.parameters_button('export_map', 'export_series'))  # one button for both: less crowded
		f.addRow(row)
		self.export_status = QLabel('')
		self.export_status.setWordWrap(True)
		f.addRow(self.export_status)
		page.addWidget(box)

		self.theme.currentIndexChanged.connect(lambda i: self.show_analyses())
		self.show_analyses()
		# the options that do not apply to the variable: the other metrics of the SCF, the filters and the dates of the
		# fixed layers (elevation, slope)
		self.variable.currentIndexChanged.connect(self.variable_changed)
		self.where_changed()  # also variable_changed
		self.tab('About').addWidget(self.about_box())
		for lay in self.pages.values():
			lay.addStretch()

		self.group_boxes.update(series=self.series_box, trend_table=self.trends_box, trend_map=self.trends_box,
		                        animation=self.animation_box, burn=self.fire_box)
		self.setWidget(body)
		self.region_changed()
		self.follow_titles()
		self.tabs.currentChanged.connect(lambda i: self.refresh_titles())
		self.tabs.currentChanged.connect(lambda i: sync_folds(self.tabs.widget(i)))
		self.refresh_titles()

	def tab(self, title):
		"""A new tab TITLE of the panel, which scrolls: the layout of its groups."""
		body = QWidget()
		lay = QVBoxLayout(body)
		scroll = QScrollArea()
		scroll.setWidgetResizable(True)
		scroll.setWidget(body)
		scroll.setProperty('fold', True)  # hidden by the tabs, not by the panel (shown)
		self.tabs.addTab(scroll, title)
		self.pages[title] = lay
		self.tab_widgets[title] = scroll
		return lay

	def shown(self, widget):
		"""Whether the panel shows WIDGET, as isVisibleTo(self) without the folded groups and the tabs not chosen:
		what the panel hides for the region, the variable or the theme chosen is hidden; what is only folded or in
		another tab is not."""
		w = widget
		while w is not None and w is not self:
			if w.isHidden() and not w.property('fold'):
				return False
			w = w.parentWidget()
		return w is self

	def follow_titles(self):
		"""Refresh the titles of the folded groups and the line above the tabs (refresh_titles) when what they
		summarize changes."""
		refresh = lambda *args: self.refresh_titles()  # noqa: E731
		for box in (self.region_kind, self.wdpa, self.admin, self.sea, self.variable, self.step, self.doy_interannual,
		            self.doy_other):
			box.currentIndexChanged.connect(refresh)
		self.layer.layerChanged.connect(refresh)
		self.name_field.fieldChanged.connect(refresh)
		for edit in (self.project, self.country, self.season_start, self.season_end, self.asset_id):
			edit.textChanged.connect(refresh)
		for d in (self.start, self.end, self.other_start, self.other_end):
			d.dateChanged.connect(refresh)
		checks = [self.compare_on, self.season_on, self.cloud_score, self.snow_ndsi, self.topographic, self.harmonize,
		          self.landsat7, self.min_coverage, self.doy,
		          self.trend_alpha, self.landcover_box] + list(self.filters.values()) + [c['on'] for c in self.where]
		for c in checks:
			c.toggled.connect(refresh)
		for c in self.where:
			c['variable'].currentIndexChanged.connect(refresh)
		for r in (self.trend_colours, self.map_colours, self.anim_colours):
			for w in (r.low, r.high):
				w.valueChanged.connect(refresh)
			for w in (r.vmin, r.vmax):
				w.textChanged.connect(refresh)

	def refresh_titles(self):
		"""The titles of the folded groups, with what is chosen in them, and above the tabs other than Data what the
		analyses use."""
		if not hasattr(self, 'tabs'):
			return
		for box in self.findChildren(Section):
			box.refresh()
		data = self.tabs.currentWidget() is self.tabs.widget(0)
		parts = [] if data else [self.region_summary(), self.variable_summary(), self.pixel_summary()]
		text = ' · '.join(p for p in parts if p)
		self.context.setText(text)
		self.context.setVisible(bool(text))

	def region_summary(self):
		"""The region chosen, in a few words (the title of the folded group Region and the line above the tabs)."""
		kind = self.region_kind.currentData()
		name = {'layer': lambda: self.layer.currentText(), 'wdpa': lambda: self.wdpa.currentText(),
		        'admin': lambda: self.admin.currentText(), 'sea': lambda: self.sea.currentText(),
		        'country': lambda: self.country.text().strip()}.get(kind, lambda: '')()
		return name or self.region_kind.currentText()

	def variable_summary(self):
		"""The variable and its period (or the ID of the data of Earth Engine), in a few words."""
		v = self.variable.currentData() or {}
		name = self.variable.currentText() if self.variable_field.isVisibleTo(self.variable_box.content) or \
			not self.asset_id.text().strip() else self.asset_id.text().strip()
		if v.get('static'):
			return name
		period = f"{self.start.date().toString('yyyy-MM-dd')} to {self.end.date().toString('yyyy-MM-dd')}"
		return ', '.join(x for x in (name, period) if x)

	def pixel_summary(self):
		"""What the pixel filters leave out besides the default filters: the filters unchecked, the land cover mask
		and the conditions where."""
		parts = []
		off = [k for k, c in self.filters.items() if c.isEnabled() and not c.isChecked()]
		if off:
			parts.append('without the filter of ' + ', '.join(off))
		if self.landcover_box.isChecked():
			parts.append('land cover mask')
		for c in self.where:
			if c['on'].isChecked():
				parts.append('where ' + c['variable'].currentText().split(' · ')[0])
		if self.topographic.isEnabled() and self.topographic.isChecked():
			parts.append('topographic correction')
		if self.harmonize.isEnabled() and self.harmonize.isChecked():
			parts.append('Landsat 5 and 7 harmonized')
		if self.landsat7.isEnabled() and self.landsat7.isChecked():
			parts.append('Landsat 7 after 2003')
		return ', '.join(parts)

	def chart_summary(self):
		"""The options of the chart of the series that are not the default ones."""
		parts = []
		if self.doy.isChecked():
			parts.append('a line per year')
		if self.doy_interannual.isEnabled() and self.doy_interannual.currentData():
			parts.append(self.doy_interannual.currentText())
		if self.doy_other.isEnabled() and self.doy_other.currentData():
			parts.append('right axis ' + self.doy_other.currentText())
		return ', '.join(parts)

	def fire_form(self, s, f):
		"""The fields of the group «Burn severity of a fire» in its form F (with the settings S)."""
		# first the index, as its sensors depend on it (MODIS only for the RdNBR)
		self.fire_index = combo(FIRE_INDICES, 'dNBR')
		for i, (_, value) in enumerate(FIRE_INDICES):
			self.fire_index.setItemData(i, FIRE_TIPS[value], Qt.ItemDataRole.ToolTipRole)
		f.addRow('Index', info(self.fire_index, HELP['fire_index']))
		self.fire_sensor = QComboBox()
		self.fill_fire_sensors(s.value(SETTINGS + 'fire_sensor', 'Sentinel-2'))
		self.fire_index.currentIndexChanged.connect(lambda i: self.fill_fire_sensors())
		f.addRow('Sensor', info(self.fire_sensor, HELP['fire_sensor']))
		self.fire_dates = {}
		for when, label in (('before', 'Before the fire'), ('after', 'After the fire')):
			row = QHBoxLayout()
			for i, key in enumerate((f'{when}_start', f'{when}_end')):
				d = QDateEdit(QDate.fromString(s.value(SETTINGS + 'fire_' + key, FIRE_DATES[key]), 'yyyy-MM-dd'))
				d.setCalendarPopup(True)
				d.setDisplayFormat('yyyy-MM-dd')
				self.fire_dates[key] = d
				if i:
					row.addWidget(QLabel('to'))
				row.addWidget(d)
			f.addRow(label, info(row, HELP['fire_' + when]))
		# the perimeter of the burned area: its polygons, a layer to choose as the region of other analyses
		self.fire_perimeter = QCheckBox('polygons of the burned area')
		self.fire_perimeter.setChecked(s.value(SETTINGS + 'fire_perimeter', 'true') == 'true')
		f.addRow('Perimeter', info(self.fire_perimeter, HELP['fire_perimeter']))
		row = QHBoxLayout()
		self.fire_burned_min = QLineEdit()  # empty: the value of the classes of the index (none for the RBR)
		self.fire_burned_min.setToolTip('The index from which a pixel is burned; empty: that of its classes')
		row.addWidget(self.fire_burned_min, 1)
		row.addWidget(QLabel('smallest'))
		self.fire_min_ha = QDoubleSpinBox()
		self.fire_min_ha.setRange(0, 100000)
		self.fire_min_ha.setDecimals(2)
		self.fire_min_ha.setValue(fire.PERIMETER_MIN_HA)
		self.fire_min_ha.setSuffix(' ha')
		self.fire_min_ha.setToolTip('Burned patches of less than this are left out, and unburned islands of less than '
		                            'this inside them filled; 0: every pixel')
		row.addWidget(self.fire_min_ha)
		f.addRow('Burned from', info(row, HELP['fire_perimeter']))
		row = QHBoxLayout()  # only the fire in a large region: the largest patch, or that nearest to a point
		self.fire_keep = combo(FIRE_KEEP, 'all')
		row.addWidget(self.fire_keep, 1)
		self.fire_seed = QLineEdit()
		self.fire_seed.setPlaceholderText('lon, lat')
		self.fire_seed.setToolTip('A point in the fire, in degrees (WGS 84): longitude, latitude')
		row.addWidget(self.fire_seed, 1)
		f.addRow('Keep', info(row, HELP['fire_keep']))
		self.fire_keep.currentIndexChanged.connect(lambda i: self.perimeter_changed())
		# the offset of the dNBR: the median dNBR of unburned land near the fire (a layer of polygons), subtracted
		self.fire_offset = QgsMapLayerComboBox()
		self.fire_offset.setFilters(Qgis.LayerFilter.PolygonLayer)
		self.fire_offset.setAllowEmptyLayer(True, 'none')
		self.fire_offset.setLayer(None)
		f.addRow('Offset region', info(self.fire_offset, HELP['fire_offset']))
		self.fire_perimeter.toggled.connect(lambda on: self.perimeter_changed())
		self.fire_index.currentIndexChanged.connect(lambda i: self.perimeter_changed())
		self.perimeter_changed()
		b = QPushButton('Compute the severity')
		b.setToolTip('Hectares of each class of the USGS (dNBR) or of Miller & Thode 2007 (RdNBR, also its statistics), '
		             'or statistics of the RBR, over each feature of the region, in a window, and a temporary GeoTIFF '
		             'with its colours (queryable with the Identify Features tool)')
		b.clicked.connect(self.run_burn)
		f.addRow(self.with_parameters(b, 'burn'))


	def data_block(self, s):
		"""The options of the data of Earth Engine outside the catalog, shown in their themes instead of the list
		Variable (with the settings S): the theme and the dataset of the GEE Community Catalog (only in its theme), the
		ID of an image or a collection of images with the button Read (services.describe_asset), its band, how it is
		used (images with dates or a fixed image), the scale, offset and unit of its values, and what its record says.
		Their values reach the list Variable as an entry of it (custom_entry), so that the panel greys out what does
		not apply to them as it does for the variables of the catalog."""
		self.asset_info = None  # what services.describe_asset said of the last ID read
		self.community_records = {}  # the records of the datasets listed, by ID
		self.data_row = QWidget()
		form = QFormLayout(self.data_row)
		form.setContentsMargins(0, 0, 0, 0)
		self.community_row = QWidget()  # the GEE Community Catalog: from the copy of its index (no Earth Engine)
		cf = QFormLayout(self.community_row)
		cf.setContentsMargins(0, 0, 0, 0)
		self.community_theme = QComboBox()
		for t in services.community_themes('en'):
			self.community_theme.addItem(f"{t['name']} ({t['datasets']})", t['theme'])
		self.community_theme.setCurrentIndex(max(0, self.community_theme.findData(
			s.value(SETTINGS + 'community_theme', ''))))
		cf.addRow('Theme of the catalog', info(self.community_theme, HELP['community_theme']))
		self.community_dataset = QComboBox()
		self.community_dataset.setPlaceholderText('choose the dataset')  # as the Earth Engine app
		self.community_dataset.activated.connect(self.dataset_chosen)  # only a choice of the user reads it
		cf.addRow('Dataset', info(self.community_dataset, HELP['community_dataset']))
		self.fill_datasets()
		self.community_theme.currentIndexChanged.connect(lambda i: self.fill_datasets())
		form.addRow(self.community_row)
		self.search_row = QWidget()  # the Earth Engine data catalog: from the copy of its index (no Earth Engine)
		sf = QFormLayout(self.search_row)
		sf.setContentsMargins(0, 0, 0, 0)
		self.catalog_text = QLineEdit()
		self.catalog_text.setPlaceholderText('words in English, e.g. snow cover, soil moisture')
		self.catalog_text.returnPressed.connect(self.search_catalog)
		row = QHBoxLayout()
		row.addWidget(self.catalog_text, 1)
		b = QPushButton('Search')
		b.setToolTip('Searches the Earth Engine data catalog (the copy of its index in MonitorEO: without Earth '
		             'Engine): the collections with data in the period, the images (fixed) of any date, over the map '
		             'view when it is the region')
		b.clicked.connect(lambda checked=False: self.search_catalog())
		row.addWidget(b)
		sf.addRow('Search the catalog', info(row, HELP['catalog_search']))
		self.catalog_found = QComboBox()
		self.catalog_found.setPlaceholderText('search first')
		self.catalog_found.activated.connect(self.catalog_chosen)
		sf.addRow('Dataset', self.catalog_found)
		form.addRow(self.search_row)
		self.asset_id = QLineEdit(s.value(SETTINGS + 'asset', ''))
		self.asset_id.setPlaceholderText('e.g. IDAHO_EPSCOR/TERRACLIMATE or projects/sat-io/open-datasets/FABDEM')
		self.asset_id.returnPressed.connect(self.read_asset)
		row = QHBoxLayout()
		row.addWidget(self.asset_id, 1)
		b = QPushButton('Read')
		b.setToolTip('Reads in Earth Engine what this ID is (an image or a collection of images) and its bands; for the '
		             'Earth Engine data catalog, also their units, scale and offset, its licence and how to cite it')
		b.clicked.connect(lambda checked=False: self.read_asset())
		row.addWidget(b)
		form.addRow('Earth Engine ID', info(row, lambda: data_help(self.variable.currentData(), self.described())))
		self.asset_band = QComboBox()  # the bands read, or one written
		self.asset_band.setEditable(True)
		self.asset_band.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
		self.asset_band.setEditText(s.value(SETTINGS + 'asset_band', ''))
		self.asset_band.lineEdit().setPlaceholderText('press Read, or write it')
		self.band_field = QWidget()  # one band (or several written with commas, before Read), hidden with the list
		row = info(self.asset_band, HELP['asset_band'])
		row.setContentsMargins(0, 0, 0, 0)
		self.band_field.setLayout(row)
		form.addRow('Band', self.band_field)
		self.band_label = form.labelForField(self.band_field)
		# one band, or several combined on each pixel (their sum or mean: band_reducer of monitoreo.variable)
		reducer = s.value(SETTINGS + 'band_reducer', '')
		self.band_reducer = combo(REDUCERS, reducer if reducer in dict(REDUCERS).values() else '')
		form.addRow('Combine bands', info(self.band_reducer, HELP['band_reducer']))
		self.asset_bands = QgsCheckableComboBox()  # the bands read, checked to be combined
		self.asset_bands.setDefaultText('check two or more bands')
		self.saved_bands = [b for b in str(s.value(SETTINGS + 'asset_bands', '') or '').split(',') if b]  # until Read
		self.filling_bands = False  # while the bands read are listed
		self.bands_field = QWidget()
		row = info(self.asset_bands, HELP['asset_bands'])
		row.setContentsMargins(0, 0, 0, 0)
		self.bands_field.setLayout(row)
		form.addRow('Bands', self.bands_field)
		self.bands_label = form.labelForField(self.bands_field)
		self.bands_note = QLabel()  # the bands checked that differ in pixel size, unit, scale or offset
		self.bands_note.setWordWrap(True)
		self.bands_note.setStyleSheet('font-size: 11px; color: #b06000;')
		form.addRow(self.bands_note)
		use = s.value(SETTINGS + 'asset_use', 'collection')
		self.asset_use = combo(USES, use if use in dict(USES).values() else 'collection')
		form.addRow('Use as', info(self.asset_use, HELP['asset_use']))
		self.band_scale = QLineEdit(s.value(SETTINGS + 'band_scale', ''))
		self.band_scale.setPlaceholderText('1: the values as stored')
		form.addRow('Band scale', info(self.band_scale, HELP['band_scale']))
		self.band_offset = QLineEdit(s.value(SETTINGS + 'band_offset', ''))
		self.band_offset.setPlaceholderText('0')
		form.addRow('Band offset', info(self.band_offset, HELP['band_offset']))
		self.asset_unit = QLineEdit(s.value(SETTINGS + 'asset_unit', ''))
		self.asset_unit.setPlaceholderText('e.g. mm, degC, kg m-2, mm day-1 or 1 (dimensionless)')
		form.addRow('Unit (UDUNITS)', info(self.asset_unit, HELP['asset_unit']))
		self.asset_label = QLabel(READ_HINT)  # title, source, licence and page of the data read
		self.asset_label.setWordWrap(True)
		self.asset_label.setOpenExternalLinks(True)
		self.asset_label.setStyleSheet('font-size: 11px; color: #444;')
		form.addRow(self.asset_label)
		# connected once filled: every change reaches the entry of the list Variable
		self.asset_id.textEdited.connect(lambda text: self.asset_edited())
		self.asset_id.textChanged.connect(lambda text: self.custom_changed())
		self.asset_band.currentIndexChanged.connect(lambda i: self.band_changed())
		self.asset_band.currentTextChanged.connect(lambda text: self.custom_changed())
		self.band_reducer.currentIndexChanged.connect(lambda i: self.reducer_changed())
		# each band checked or unchecked, at once (checkedItemsChanged only comes when its list closes)
		model = self.asset_bands.model()
		checked = getattr(model, 'itemCheckStateChanged', None) or self.asset_bands.checkedItemsChanged
		checked.connect(lambda *args: self.bands_checked())
		self.show_bands()
		self.asset_use.currentIndexChanged.connect(lambda i: self.custom_changed())
		for w in (self.band_scale, self.band_offset, self.asset_unit):
			w.textChanged.connect(lambda text: self.custom_changed())
		return self.data_row

	def sync_fields(self):
		layer = self.layer.currentLayer()
		if self.name_field.layer() is not layer:
			self.name_field.setLayer(layer)

	def region_changed(self):
		kind = self.region_kind.currentData()
		self.layer_row.setVisible(kind == 'layer')
		for widgets, shown in (((self.wdpa_row, self.wdpa_field, self.wdpa_label), kind == 'wdpa'),
		                       ((self.admin_row, self.admin, self.admin_label), kind == 'admin'),
		                       ((self.sea_row, self.sea, self.sea_label), kind == 'sea'),
		                       ((self.country_field, self.country_label), kind == 'country')):
			for w in widgets:
				if w is not None:
					w.setVisible(shown)

	def message(self, text, lvl='Info', duration=6):
		"""TEXT in the message bar; an error (LVL Critical) goes to the log of the plugin too, with the button "Send
		the logs" (sendlogs)."""
		bar = self.iface.messageBar()
		if lvl != 'Critical':
			bar.pushMessage('MonitorEO', text, level=level(lvl), duration=duration)
			return
		sendlogs.write({'error': text})
		from monitoreo import about
		item = bar.createMessage('MonitorEO', text)
		button = QPushButton(about.LOGS['en']['button'])
		button.setToolTip(about.LOGS['en']['menu'])
		button.clicked.connect(lambda checked=False, t=text: self.send_logs(t))
		item.layout().addWidget(button)
		bar.pushWidget(item, level(lvl), duration)

	def send_logs(self, error=''):
		"""The window "Send the logs" (sendlogs.LogsDialog), with the error ERROR to start the description with."""
		self.logs_dialog = sendlogs.LogsDialog(self, plugin_version(), self.project.text(), error,
		                                       on_sent=lambda text: self.message(text, 'Success', 10))
		self.logs_dialog.show()

	def version_label(self):
		"""The version of the plugin and the date of its release (that of the package monitoreo it carries, released
		with it), e.g. «MonitorEO 0.3.31 · released 2026-11-13»."""
		import monitoreo
		released = plugin_released()  # without a date (a package older than it): the version alone
		label = QLabel(f'MonitorEO {plugin_version()}' + (f' · released {released}' if released else ''))
		label.setToolTip(f'QGIS plugin {plugin_version()}, with the package monitoreo {monitoreo.__version__}' +
		                 (f', released on {released}' if released else ''))
		label.setStyleSheet('font-size: 11px; color: #666;')
		self.version_text = label.text()
		return label

	def feedback_button(self):
		"""The button to suggest a change or report an error: an issue of GitHub or the anonymous form, filled with
		the plugin and its version (see monitoreo.about.feedback), or "Send the logs" of the plugin (send_logs)."""
		from monitoreo import __version__, about
		texts = about.FEEDBACK['en']
		links = about.feedback('qgis', f'{plugin_version()} (monitoreo {__version__})')
		button = QToolButton()
		button.setText(texts['button'])
		button.setToolTip('Opens a new issue of GitHub, or the anonymous form, in the browser')
		button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
		menu = QMenu(button)
		for key in ('issue', 'form'):
			action = menu.addAction(texts[key])
			action.triggered.connect(lambda checked=False, url=links[key]: QDesktopServices.openUrl(QUrl(url)))
		menu.addSeparator()  # the log of the plugin, with the anonymous form (sendlogs)
		action = menu.addAction(about.LOGS['en']['menu'])
		action.triggered.connect(lambda checked=False: self.send_logs())
		button.setMenu(menu)
		self.feedback_links = links
		return button

	def about_box(self):
		"""What MonitorEO-OBSNEV is, who funds it and how to cite it, with the logos of the institutions and projects."""
		from monitoreo import about
		box = QGroupBox('About MonitorEO')
		lay = QVBoxLayout(box)
		for path in about.about('en')['logos']:
			logo = QLabel()
			logo.setPixmap(QPixmap(path).scaled(330, 48, Qt.AspectRatioMode.KeepAspectRatio,
			                                    Qt.TransformationMode.SmoothTransformation))
			logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
			lay.addWidget(logo)
		doi = f'https://doi.org/{about.DOI}'
		gee = 'https://doi.org/10.1016/j.rse.2017.06.031'
		for text in (about.DESCRIPTION['en'], about.ACKNOWLEDGEMENTS['en'],
		             f"<b>{about.HOW_TO_CITE['en']}:</b> " + about.CITATION.replace(doi, f'<a href="{doi}">{doi}</a>'),
		             f"{about.CITE_ALSO['en']}: " + about.EARTH_ENGINE.replace(gee, f'<a href="{gee}">{gee}</a>'),
		             f'<a href="{MANUAL}">Manual</a> · <a href="{about.REPOSITORY}">Code</a>'):
			label = QLabel(text)
			label.setWordWrap(True)
			label.setOpenExternalLinks(True)
			label.setStyleSheet('font-size: 11px; color: #444;')
			lay.addWidget(label)
		return box

	def project_layers_changed(self, *args):
		self.sync_fields()

	def stop(self):
		self.timer.stop()
		for signal in self.project_signals:
			try:
				signal.disconnect(self.project_layers_changed)
			except (TypeError, RuntimeError):  # already disconnected
				pass

	# Parameters of the analyses (monitoreo.parameters) ------------------------------------------------------------

	def apply_button(self):
		"""The button that fills the panel with the parameters of an analysis: pasted, or opened from a JSON file."""
		button = QToolButton()
		button.setText('Apply parameters')
		button.setToolTip('Fill the panel with the parameters of an analysis (JSON), copied or saved here or in Python, '
		                  'R, the command line, the MCP server or the Earth Engine app, without computing it')
		button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
		menu = QMenu(button)
		menu.addAction('Paste parameters').triggered.connect(lambda checked=False: self.paste_parameters())
		menu.addAction('Open parameters…').triggered.connect(lambda checked=False: self.open_parameters())
		button.setMenu(menu)
		self.apply_menu = menu
		return button

	def parameters_button(self, *keys):
		"""The small button Parameters of the analyses KEYS of the panel (see PANEL): Copy parameters and Save
		parameters… of each, from the arguments that its button computes with."""
		button = QToolButton()
		button.setText('Parameters')
		what = ' and '.join(PANEL[k][1].split(' (')[0] for k in keys)
		button.setToolTip(f'Copy or save the parameters of {what} (JSON), as its button computes it, to repeat it here '
		                  '(Apply parameters) or in Python, R, the command line, the MCP server or the Earth Engine app')
		button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
		menu = QMenu(button)
		for key in keys:
			name = '' if len(keys) == 1 else f" of {PANEL[key][1].split(' (')[0]}"
			menu.addAction(f'Copy parameters{name}').triggered.connect(
				lambda checked=False, k=key: self.copy_parameters(k))
			menu.addAction(f'Save parameters{name}…').triggered.connect(
				lambda checked=False, k=key: self.save_parameters(k))
		button.setMenu(menu)
		button.setObjectName('parameters_' + '_'.join(keys))
		return button

	def with_parameters(self, button, key):
		"""A row with BUTTON, the button of the analysis KEY, and its button Parameters."""
		row = QHBoxLayout()
		row.addWidget(button, 1)
		row.addWidget(self.parameters_button(key))
		return row

	def call_of(self, key, **kw):
		"""The parameters of the analysis KEY of the panel (see PANEL): (its function of monitoreo.services, its
		arguments without its outputs), or None, with a message, if the fields are not valid."""
		try:
			return getattr(self, PANEL[key][0])(**kw)
		except Exception as e:
			self.message(str(e), 'Warning')
			return None

	def copy_parameters(self, key):
		"""Copy the parameters of the analysis KEY of the panel (JSON, see monitoreo.parameters) to the clipboard."""
		call = self.call_of(key)
		if call:
			QApplication.clipboard().setText(parameters_text(parameters.make(*call)))
			self.message(f'Parameters of {PANEL[key][1].split(" (")[0]} ({call[0]}) copied: Apply parameters → Paste '
			             'parameters fills the panel with them, and the other tools of MonitorEO take them', 'Success')

	def save_parameters(self, key):
		"""Save the parameters of the analysis KEY of the panel to a JSON file chosen by the user."""
		call = self.call_of(key)
		if not call:
			return
		path, _ = QFileDialog.getSaveFileName(self, 'Save parameters', call[0] + parameters.SUFFIX,
		                                      'Parameters (*.json)')
		if path:
			parameters.save(*call, path)
			self.message(f'Parameters of {call[0]} saved: {path}', 'Success', 10)

	def paste_parameters(self):
		"""Fill the panel with the parameters in the clipboard (see apply_parameters)."""
		text = QApplication.clipboard().text().strip()
		if not text:
			self.message('The clipboard has no parameters: copy those of an analysis first (Parameters → Copy '
			             'parameters, its window, or another tool of MonitorEO)', 'Warning')
			return
		self.apply_parameters(text)

	def open_parameters(self):
		"""Fill the panel with the parameters of a JSON file chosen by the user (see apply_parameters)."""
		path, _ = QFileDialog.getOpenFileName(self, 'Open parameters', '', 'Parameters (*.json);;All files (*)')
		if path:
			self.apply_parameters(path)

	def apply_parameters(self, source):
		"""Fill the fields of the panel with the parameters SOURCE (a dictionary, a JSON text or the path of a JSON file:
		see monitoreo.parameters), without computing anything, and bring the group of their analysis into view. A
		message that stays tells what was not applied, with the reason: those that parameters.check leaves out (not
		parameters of the analysis in this version, a variable that is not in the catalog) and those that the panel
		has no field or value for (a region or an option it does not have, a value that its list does not have, an
		option greyed out for the variable). Returns those, or None if SOURCE is not parameters of an analysis."""
		try:
			checked = parameters.check(source)
			key, fields, reports = panel_fields(checked['analysis'], checked['parameters'])
		except Exception as e:  # not JSON, no analysis...
			self.message(f'Parameters not applied: {e}', 'Critical', 15)
			return None
		reports = list(checked['not_applied']) + reports
		self.applied = []
		if key == 'burn':  # the parameters give no layer: no Offset region (none is the default of the services)
			self.fire_offset.setLayer(None)
		if key == 'burn' and not self.theme_has('burn_severity'):  # its group, only in its theme
			self.theme.setCurrentIndex(item_index(self.theme, test=lambda k: k is not None and self.theme_has_key(
				k, 'burn_severity')))
		for name in FIELDS:
			f = fields.get(name)
			if f is None:
				continue
			try:
				if name in COMBOS:
					reports += self.choose(getattr(self, name), f['value'], f['name'], f['given'])
				else:
					reports += getattr(self, 'put_' + name)(f['value'], f['given'], f['name']) or []
			except Exception as e:  # a value the field cannot take
				reports.append(missing(f['name'], f['value'], str(e)))
		self.show_group(key)
		what, button = PANEL[key][1].split(' (')[0], PANEL[key][2]
		text = f"Parameters of {checked['analysis']} applied to {what}: press {button} to compute it" + \
			''.join(f'; {x}' for x in self.applied) + (f". {checked['note']}" if checked.get('note') else '')
		if reports:
			self.message(f'{text}. Not applied: {parameters.text(reports)}', 'Warning', 0)
		else:
			self.message(text, 'Success', 10)
		return reports

	def theme_has_key(self, key, name):
		"""Whether the theme KEY has the analysis NAME of its own (see theme_has)."""
		return any(t['key'] == key and name in t['analyses'] for t in services.themes('en'))

	def show_group(self, key):
		"""Bring the group of the analysis KEY into view, with its title in colour for some seconds."""
		box = self.group_boxes.get(key)
		if box is None:
			return
		for i in range(self.tabs.count()):  # first its tab: a group folded or unfolded while hidden only records it
			scroll = self.tabs.widget(i)
			if scroll.isAncestorOf(box):
				self.tabs.setCurrentIndex(i)
				box.setCollapsed(False)  # unfolded, as the section of its button in the Earth Engine app
				sync_folds(scroll)
				QTimer.singleShot(0, lambda: scroll.ensureWidgetVisible(box, 0, 0))  # once laid out
		# the colour of its title only (not of the groups in it), added to the style that QGIS gives the folded groups
		# (the room of their arrow), which comes back after
		if not box.objectName():
			box.setObjectName(f'monitoreo_{key}')
		style = box.styleSheet()
		box.setStyleSheet(style + f' QGroupBox#{box.objectName()}::title {{ color: #c0392b; }}')
		timer = QTimer(box)  # deleted with the group
		timer.setSingleShot(True)
		timer.timeout.connect(lambda: box.setStyleSheet(style))
		timer.start(4000)

	def choose(self, box, value, name, given=True):
		"""Choose in the list BOX the item of VALUE (that of the parameter NAME): the reports if it cannot (not in the
		list, or greyed out for the variable, as its tooltip says); not those of a value not GIVEN (a default)."""
		i = item_index(box, value)
		if i < 0:
			listed = ', '.join(str(box.itemData(j)) for j in range(box.count()))
			return [missing(name, value, f'not in its list in the panel: {listed}')] if given else []
		if i != box.currentIndex():
			if not box.isEnabled():
				return [missing(name, value, box.toolTip() or 'greyed out in the panel')] if given else []
			box.setCurrentIndex(i)
		return []

	def put_variable(self, value, given, name):
		"""The variable of the catalog VALUE (its entry of services.list_variables) or the data of Earth Engine by
		their ID ({'custom': True, ...}, see panel_fields): its theme and its entry of the list Variable."""
		if value.get('custom'):
			return self.put_data(value)

		def same(v):
			return bool(v) and all(v.get(k) == value.get(k) for k in ('variable', 'sensor', 'collection', 'ref'))

		if item_index(self.variable, test=same) < 0:  # another theme: that of the variable
			theme = (catalog.theme_of(value['variable']) or {}).get('key')
			self.theme.setCurrentIndex(item_index(self.theme, theme))
		i = item_index(self.variable, test=same)
		if i < 0:
			return [missing(name, value['variable'], 'not in the list Variable of the panel')]
		self.variable.setCurrentIndex(i)
		return []

	def put_data(self, value):
		"""The data of Earth Engine by their ID VALUE (see panel_fields): their theme, ID, use, band (or bands
		combined), scale, offset and unit, without reading them (Read lists their bands)."""
		if self.theme.currentData() not in self.data_themes:
			self.theme.setCurrentIndex(item_index(self.theme, next(k for k, d in self.data_themes.items()
			                                                       if d == 'earth_engine')))
		bands, reducer = value['bands'], value['band_reducer']
		self.asset_id.setText(value['asset'])
		self.asset_edited()
		self.asset_info = None
		self.filling_bands = True
		self.asset_bands.clear()  # those of another ID: Read lists its own
		self.filling_bands = False
		self.saved_bands = list(bands) if reducer else []
		self.asset_band.clear()
		self.asset_band.setEditText(', '.join(bands))
		self.first_band = None
		self.band_reducer.setCurrentIndex(item_index(self.band_reducer, reducer))
		self.asset_use.setCurrentIndex(item_index(self.asset_use, value['use']))
		self.band_scale.setText(number(value.get('band_scale')))
		self.band_offset.setText(number(value.get('band_offset')))
		self.asset_unit.setText(value.get('unit') or '')
		self.show_bands()
		self.custom_changed()
		return []

	def put_region(self, value, given, name):
		"""The region of the panel of kind and value VALUE (see region_kind): a layer of the project (the layer chosen,
		if it gives the same polygons, or a temporary one), the map extent or its center (zoomed to them), the
		protected area or administrative unit by its ID (added to its list, without searching: Search gives its name)
		or the country."""
		kind, v = value
		canvas = self.iface.mapCanvas()
		wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
		tr = QgsCoordinateTransform(wgs84, canvas.mapSettings().destinationCrs(), QgsProject.instance())
		out = []
		if kind == 'layer':
			out = self.region_layer(*v)
		elif kind == 'wdpa':
			self.add_choice(self.wdpa, v, f'WDPA {v} (from the parameters: Search gives its name)')
		elif kind == 'admin':
			self.admin_level.setCurrentIndex(item_index(self.admin_level, v[0]))
			text = (f'{municipalities.label(v[1])} · INE {v[1]}' if v[0] == municipalities.LEVEL else  # its name: the index
			        f'GAUL {v[1]}, level {v[0]} (from the parameters: Search gives its name)')
			self.add_choice(self.admin, v, text, test=lambda d: d is not None and tuple(d) == tuple(v))
		elif kind == 'country':
			self.country.setText(v)
		elif kind == 'sea':  # its name: the index of the package
			self.add_choice(self.sea, v, f'{seas.name_of(v)} (MRGID {v})')
		elif kind == 'extent':
			canvas.setExtent(tr.transformBoundingBox(QgsRectangle(*v)))
		else:
			if kind == 'biome' and v['within']:
				canvas.setExtent(tr.transformBoundingBox(QgsRectangle(*v['within'])))
			at = v['at'] if kind == 'biome' else v
			canvas.setCenter(tr.transform(QgsPointXY(*at)))
		canvas.refresh()
		self.region_kind.setCurrentIndex(item_index(self.region_kind, kind))
		if kind in ('extent', 'ecoregion', 'island', 'biome', 'sea_point'):  # what the map gives: its shape may change
			got = self.region()
			if kind == 'extent':
				pairs = [('region.bbox', v, got['bbox'], 'the panel computes over the map extent, now {}: the map '
				          'keeps the shape of its window')]
			elif kind == 'biome':
				pairs = [('region.biome_at', v['at'], got['biome_at'], 'the panel takes the biome at the center of '
				          'the map, now {}'),
				         ('region.within', v['within'], got['within']['bbox'], 'the panel takes the part of the biome '
				          'in the map extent, now {}')]
			else:
				key = CENTER_KEYS[kind]
				pairs = [(f'region.{key}', v, got[key], 'the panel takes the point at the center of the map, now {}')]
			for key, want, have, reason in pairs:
				if not want or any(abs(a - b) > 1e-6 for a, b in zip(want, have)):
					out.append(missing(key, want, reason.format([round(x, 6) for x in have])))
		return out

	def add_choice(self, box, value, label, test=None):
		"""Choose VALUE in the list BOX, added to it with LABEL if it has not got it."""
		i = item_index(box, value, test)
		if i < 0:
			box.addItem(label, value)
			i = box.count() - 1
		box.setCurrentIndex(i)

	def region_layer(self, fc, name_field=None):
		"""Choose in Region → Layer the polygons of the FeatureCollection FC of some parameters: the layer chosen, if it
		gives them, or a temporary layer added to the project (REGION_LAYER), with its field of names NAME_FIELD (by
		default name, as the panel writes them)."""
		chosen = self.layer.currentLayer()
		for layer in [chosen] + QgsProject.instance().mapLayersByName(REGION_LAYER):  # one that gives them already
			if not isinstance(layer, QgsVectorLayer):
				continue
			field = self.field_of(layer, fc, name_field or (self.name_field.currentField() if layer is chosen else
			                                                'name'))
			if field is not None:
				self.layer.setLayer(layer)
				self.sync_fields()
				self.name_field.setField(field)
				return []
		layer = self.geojson_layer(fc, REGION_LAYER)
		self.layer.setLayer(layer)
		if self.layer.currentLayer() is not layer:
			QgsProject.instance().removeMapLayer(layer.id())
			return [missing('region', 'geojson', 'its GeoJSON has no polygons')]
		self.sync_fields()
		names = [f.name() for f in layer.fields()]
		field = name_field if name_field in names else 'name' if 'name' in names else ''
		self.name_field.setField(field)
		self.applied.append(f'the region: the temporary layer {REGION_LAYER}')
		return [] if field or not name_field else [missing('region.name_field', name_field, 'not a field of its GeoJSON')]

	def field_of(self, layer, fc, prefer=None):
		"""The field of names of LAYER (PREFER first; '' for the numbers of its features) with which its polygons give
		the FeatureCollection FC of some parameters (layer_region), or None if they give other polygons."""
		try:
			got = self.layer_region(layer, '')['geojson']['features']
		except Exception:  # no features
			return None
		want = fc.get('features') or []
		if [f['geometry'] for f in got] != [f.get('geometry') for f in want]:
			return None
		names = [(f.get('properties') or {}).get('name') for f in want]
		fields = [f.name() for f in layer.fields()]
		if all(n is None for n in names):  # without names: any field
			return prefer if prefer in fields else ''
		feats = [f for f in (list(layer.getSelectedFeatures()) or list(layer.getFeatures())) if f.hasGeometry()]
		for field in dict.fromkeys([prefer] + fields):
			if field in fields and [str(f[field]) for f in feats] == [str(n) for n in names]:
				return field
		return '' if [str(f.id()) for f in feats] == [str(n) for n in names] else None

	def geojson_layer(self, fc, name):
		"""A layer NAME of the GeoJSON FC (a temporary file), added to the project."""
		path = os.path.join(tempfile.mkdtemp(prefix='monitoreo_'), 'parameters.geojson')
		with open(path, 'w', encoding='utf-8') as f:
			json.dump(fc, f)
		layer = QgsVectorLayer(path, name, 'ogr')
		if not layer.isValid():
			raise ValueError('QGIS could not read its GeoJSON')
		QgsProject.instance().addMapLayer(layer)
		return layer

	def put_line(self, value, given, name):
		"""The line VALUE ([[lon, lat], ...]) of a profile: the layer of lines chosen (or one added before, LINE_LAYER)
		if its line is that one, or else a temporary layer of it added to the project."""
		for layer in [self.line_layer.currentLayer()] + QgsProject.instance().mapLayersByName(LINE_LAYER):
			if not isinstance(layer, QgsVectorLayer):
				continue
			try:
				same = self.layer_line(layer) == value
			except Exception:  # no lines
				same = False
			if same:
				self.line_layer.setLayer(layer)
				return []
		layer = self.geojson_layer({'type': 'FeatureCollection', 'features': [
			{'type': 'Feature', 'properties': {}, 'geometry': {'type': 'LineString', 'coordinates': value}}]}, LINE_LAYER)
		self.line_layer.setLayer(layer)
		if self.line_layer.currentLayer() is not layer:
			QgsProject.instance().removeMapLayer(layer.id())
			return [missing(name, value, 'QGIS could not make a layer of lines of it')]
		self.applied.append(f'the line: the temporary layer {LINE_LAYER}')
		return []

	def put_where(self, value, given, name):
		"""The conditions of «Only the pixels where» and the land cover mask VALUE (see where_fields); the rows and
		the mask without one, unchecked."""
		out = []
		rows = value['conditions']
		for k, c in enumerate(self.where):
			if k >= len(rows):
				c['on'].setChecked(False)
				continue
			i, cond = rows[k]
			j = item_index(c['variable'], test=lambda v: same_variable(v, cond))
			if j < 0:
				out.append(missing(f'where[{i}]', cond, 'its variable is not in the list of the panel'))
				c['on'].setChecked(False)
				continue
			c['variable'].setCurrentIndex(j)
			keep = 'classes' if cond.get('classes') is not None else 'exclude' if cond.get('exclude') is not None \
				else None
			if keep:
				codes = cond[keep]
				c['keep'].setCurrentIndex(item_index(c['keep'], keep))
				c['codes'].setText(', '.join(str(x) for x in (codes if isinstance(codes, (list, tuple)) else [codes])))
			else:
				c['min'].setText(number(cond.get('min')))
				c['max'].setText(number(cond.get('max')))
			c['on'].setChecked(True)
		cover = value['landcover']
		self.landcover_box.setChecked(cover is not None)
		if cover is not None:
			out += self.choose(self.landcover_map, cover_key(cover.get('landcover')), 'where.landcover')
			self.fill_landcover_years(cover.get('year'))
			if cover.get('year') not in (None, '') and self.landcover_year.currentData() != int(cover['year']):
				out.append(missing('where.year', cover['year'], 'not a year of the land cover map in the panel'))
			exclude = cover.get('exclude') or []
			exclude = [exclude] if isinstance(exclude, str) else list(exclude)
			low = [str(x).strip().lower() for x in exclude]  # in any case, as landcover.check
			keys = [self.landcover_classes.itemData(i) for i in range(self.landcover_classes.count())]
			for i, k in enumerate(keys):
				self.landcover_classes.setItemCheckState(i, Qt.CheckState.Checked if k in low else
				                                         Qt.CheckState.Unchecked)
			out += [missing('where.exclude', x, f"not a land cover of the mask: {', '.join(keys)}")
			        for x, k in zip(exclude, low) if k not in keys]
		self.where_changed()
		return out

	def put_period(self, value, given, name):
		"""The period VALUE (first day, last day; None keeps that of the panel)."""
		return self.put_dates((self.start, self.end), value, ('start', 'end') if name == 'start' else (name, name))

	def put_dates(self, edits, days, names):
		"""The days DAYS (YYYY-MM-DD, or None) in the date fields EDITS, of the parameters NAMES."""
		out = []
		for edit, day, name in zip(edits, days, names):
			if day is None:
				continue
			d = QDate.fromString(str(day)[:10], 'yyyy-MM-dd')
			if d.isValid():
				edit.setDate(d)
			else:
				out.append(missing(name, day, 'not a day YYYY-MM-DD'))
		return out

	def put_compare(self, value, given, name):
		"""Compare with: on with the other period VALUE (first day, last day), off with None."""
		if value is None:
			self.compare_on.setChecked(False)
			return []
		if not self.compare_on.isEnabled():
			return [missing(name, value[0], self.compare_on.toolTip() or 'Compare with is greyed out for the variable')]
		out = self.put_dates((self.other_start, self.other_end), value, ('other_start', 'other_end'))
		self.compare_on.setChecked(True)
		return out

	def put_season(self, value, given, name):
		"""The season VALUE ([MM-DD, MM-DD], or None: every day of the year)."""
		if value is None:
			self.season_on.setChecked(False)
			return []
		days = [str(x) for x in value] if isinstance(value, (list, tuple)) else []
		if len(days) != 2 or not all(re.fullmatch(r'\d\d-\d\d', x) for x in days):
			return [missing(name, value, 'the panel takes a season of two days MM-DD, e.g. ["06-01", "09-30"]')]
		self.season_start.setText(days[0])
		self.season_end.setText(days[1])
		self.season_on.setChecked(True)
		return []

	def put_quality(self, value, given, name):
		"""The pixel filters VALUE (see quality_fields): the check boxes and, of those that the variable greys out, the
		choice of the user (that of the burn severity, OWN), reported if the variable cannot take it (the filter of
		what it measures)."""
		q, own = value['filters'], value['own']
		fixed = (self.variable.currentData() or {}).get('fixed_filters') is not None  # whatever the parameters say
		out = []
		for k, w in self.filters.items():
			on = bool(q[k])
			if k in self.set_filters:
				if self.chosen_filters is not None:
					self.chosen_filters[k] = on
				if given and not own and not fixed and q[k] != 'auto' and w.isChecked() != on:
					out.append(missing(f'quality.{k}', q[k], w.toolTip()))
			else:
				w.setChecked(on)
		# also greyed out: the burn severity and the right axis of a profile compute other variables with it
		self.cloud_score.setChecked(q['cloud_score'])
		self.topographic.setChecked(bool(q.get('topographic')))
		self.snow_ndsi.setChecked(bool(q.get('snow_ndsi')))
		if given and q.get('snow_ndsi') and not own and not self.snow_ndsi.isEnabled():
			out.append(missing('quality.snow_ndsi', sensors.SNOW_NDSI_DEFAULT, NO_SNOW_NDSI))
		if given and q.get('topographic') and not own and not self.topographic.isEnabled():
			out.append(missing('quality.topographic', True, NO_TOPOGRAPHIC))
		for k, box, why in (('harmonize', self.harmonize, NO_HARMONIZE), ('landsat7', self.landsat7, NO_LANDSAT7)):
			box.setChecked(bool(q.get(k)))
			if given and q.get(k) and not own and not box.isEnabled():
				out.append(missing(f'quality.{k}', True, why))
		return out

	def put_min_coverage(self, value, given, name):
		self.min_coverage.setChecked(bool(value))
		return []

	def put_doy(self, value, given, name):
		self.doy.setChecked(bool(value))
		return []

	def put_doy_other(self, value, given, name):
		"""The variable on the right axis VALUE ({'variable', 'sensor'}, or None)."""
		i = 0 if value is None else item_index(self.doy_other, test=lambda v: same_variable(v, value))
		if i < 0:
			return [missing(name, value['variable'], 'not a variable with dates of the panel (Right axis)')]
		if i != self.doy_other.currentIndex() and not self.doy_other.isEnabled():
			return [missing(name, value['variable'], 'only with Chart checked')] if given else []
		self.doy_other.setCurrentIndex(i)
		return []

	def put_trend_alpha(self, value, given, name):
		self.trend_alpha.setChecked(bool(value))
		return []

	def put_map_kind(self, value, given, name):
		"""The layer of the map: the true colour (value 'rgb') or the index (the true colour under it, Both, stays)."""
		if value == 'index' and self.map_kind.currentData() == 'both':
			return []
		return self.choose(self.map_kind, value, name, value == 'rgb')

	def put_resolution(self, value, given, name):
		self.resolution.setValue(float(value or 0))
		return []

	def put_zones(self, value, given, name):
		"""The bands of a fixed layer or the classes of a categorical layer VALUE ({'variable', 'sensor', 'breaks'})."""
		which = {k: value.get(k) for k in ('variable', 'sensor')}  # the other keys: reported below
		i = item_index(self.zone_variable, test=lambda v: same_variable(v, which))
		if i < 0:
			return [missing(name, value, 'the panel takes the bands of a fixed layer or the classes of a categorical '
			                'layer (Bands of)')]
		self.zone_variable.setCurrentIndex(i)
		out = [missing(f'{name}.{k}', value[k], 'the panel has no such option') for k in value
		       if k not in ('variable', 'sensor', 'breaks')]
		if value.get('breaks') is not None:
			if self.zone_breaks.isEnabled():
				self.zone_breaks.setText(breaks_text(value['breaks']))
			else:
				out.append(missing(f'{name}.breaks', value['breaks'], self.zone_breaks.toolTip()))
		return out

	def put_stats(self, value, given, name):
		"""The statistics of each band: those of the panel (ZONE_STATS; the mode, of a categorical layer)."""
		want = ['mode'] if (self.variable.currentData() or {}).get('categorical') else ZONE_STATS
		return [] if list(value) == want else [missing(name, value, f"the panel computes {', '.join(want)} in each "
		                                                            'band')]

	def put_area_map(self, value, given, name):
		"""The land cover map of Area by class VALUE ({'landcover', 'year', 'other_year'}): its year (by default its
		last one) and the year of its changes, if any."""
		out = self.choose(self.area_map, cover_key(value['landcover']), 'landcover')
		if out:
			return out
		self.area_change.setChecked(value.get('other_year') is not None)
		year = value.get('year') or landcover.default_year(landcover.find(value['landcover']))
		out += self.choose(self.area_year, int(year), 'year')
		if value.get('other_year') is not None:
			out += self.choose(self.area_other_year, int(value['other_year']), 'other_year')
		return out

	def put_area_breaks(self, value, given, name):
		self.area_breaks.setText(value)
		return []

	def put_trend_colours(self, value, given, name):
		self.trend_colours.put(value)
		return []

	def put_map_colours(self, value, given, name):
		self.map_colours.put(value)
		return []

	def put_anim_colours(self, value, given, name):
		self.anim_colours.put(value)
		return []

	def put_anim_same(self, value, given, name):
		self.anim_same.setChecked(bool(value))
		return []

	def put_anim_fps(self, value, given, name):
		v = float(value)
		if not self.anim_fps.minimum() <= v <= self.anim_fps.maximum():
			return [missing(name, value, f'the panel takes from {self.anim_fps.minimum():g} to '
			                f'{self.anim_fps.maximum():g} frames per second')]
		self.anim_fps.setValue(v)
		return []

	def put_fire_before(self, value, given, name):
		return self.put_dates((self.fire_dates['before_start'], self.fire_dates['before_end']), value, ('start', 'end'))

	def put_fire_after(self, value, given, name):
		return self.put_dates((self.fire_dates['after_start'], self.fire_dates['after_end']), value,
		                      ('other_start', 'other_end'))

	def put_fire_perimeter(self, value, given, name):
		"""The perimeter of the burned area: on or off and, on, the value from which a pixel is burned and the smallest
		patch (by default, those of monitoreo.fire)."""
		self.fire_perimeter.setChecked(value['on'])
		if value['on']:
			self.fire_burned_min.setText(number(value.get('burned_min')))
			self.fire_min_ha.setValue(fire.PERIMETER_MIN_HA if value.get('min_ha') is None else float(value['min_ha']))
			keep = value.get('keep') or 'all'
			self.fire_keep.setCurrentIndex(max(0, [v for _, v in FIRE_KEEP].index(keep)))
			seed = value.get('seed')
			self.fire_seed.setText(', '.join(repr(float(v)) for v in seed) if seed else '')
		return []

	# Arguments --------------------------------------------------------------------------------------------------

	def save_settings(self):
		s = QgsSettings()
		s.setValue(SETTINGS + 'project', self.project.text().strip())
		s.setValue(SETTINGS + 'start', self.start.date().toString('yyyy-MM-dd'))
		s.setValue(SETTINGS + 'end', self.end.date().toString('yyyy-MM-dd'))
		s.setValue(SETTINGS + 'other_start', self.other_start.date().toString('yyyy-MM-dd'))
		s.setValue(SETTINGS + 'other_end', self.other_end.date().toString('yyyy-MM-dd'))
		s.setValue(SETTINGS + 'folder', self.folder.text().strip())
		s.setValue(SETTINGS + 'anim_step', self.anim_step.currentData())
		s.setValue(SETTINGS + 'area_kind', self.area_kind.currentData())
		s.setValue(SETTINGS + 'area_map', self.area_map.currentData())
		s.setValue(SETTINGS + 'area_breaks', self.area_breaks.text().strip())
		s.setValue(SETTINGS + 'zone_breaks', self.zone_breaks.text().strip())
		s.setValue(SETTINGS + 'fire_sensor', self.fire_sensor.currentData())
		s.setValue(SETTINGS + 'fire_perimeter', 'true' if self.fire_perimeter.isChecked() else 'false')
		for key, d in self.fire_dates.items():
			s.setValue(SETTINGS + 'fire_' + key, d.date().toString('yyyy-MM-dd'))
		# the data of Earth Engine outside the catalog: the last ID, band, use, scale, offset and unit, as written
		s.setValue(SETTINGS + 'asset', self.asset_id.text().strip())
		s.setValue(SETTINGS + 'asset_band', self.asset_band.currentText().strip())
		s.setValue(SETTINGS + 'band_reducer', self.band_reducer.currentData())  # and the bands checked to combine
		s.setValue(SETTINGS + 'asset_bands', ','.join(self.checked_bands() if self.asset_bands.count() else
		                                              self.saved_bands))
		s.setValue(SETTINGS + 'asset_use', self.asset_use.currentData())
		for key, w in (('band_scale', self.band_scale), ('band_offset', self.band_offset), ('asset_unit', self.asset_unit)):
			s.setValue(SETTINGS + key, w.text().strip())
		s.setValue(SETTINGS + 'community_theme', self.community_theme.currentData() or '')
		# the land cover mask: on or off, its map, year and land covers left out
		s.setValue(SETTINGS + 'landcover_on', 'true' if self.landcover_box.isChecked() else 'false')
		s.setValue(SETTINGS + 'landcover_map', self.landcover_map.currentData())
		s.setValue(SETTINGS + 'landcover_year', str(self.landcover_year.currentData() or ''))
		s.setValue(SETTINGS + 'landcover_exclude', ','.join(self.landcover_classes.checkedItemsData()))

	def region(self):
		"""Region of the services from the widgets (read in the main thread)."""
		kind = self.region_kind.currentData()
		wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
		if kind in ('extent', 'ecoregion', 'biome', 'island', 'sea_point'):
			canvas = self.iface.mapCanvas()
			tr = QgsCoordinateTransform(canvas.mapSettings().destinationCrs(), wgs84, QgsProject.instance())
			r = tr.transformBoundingBox(canvas.extent())
			extent = {'bbox': [r.xMinimum(), r.yMinimum(), r.xMaximum(), r.yMaximum()]}
			if kind == 'extent':
				return extent
			c = tr.transform(canvas.extent().center())
			if kind == 'biome':  # its part in the map extent: a whole biome spans continents
				return {'biome_at': [c.x(), c.y()], 'within': extent}
			return {CENTER_KEYS[kind]: [c.x(), c.y()]}
		if kind == 'wdpa':
			if self.wdpa.currentData() is None:
				raise ValueError('search for a protected area and choose it in the list')
			return {'wdpa_id': self.wdpa.currentData()}
		if kind == 'admin':
			if self.admin.currentData() is None:
				raise ValueError('search for an administrative unit and choose it in the list')
			level, code = self.admin.currentData()
			return {f'admin{level}': code}
		if kind == 'sea':
			if self.sea.currentData() is None:
				raise ValueError('search for a sea and choose it in the list')
			return {'sea': self.sea.currentData()}
		if kind == 'country':
			code = self.country.text().strip().upper()
			if len(code) != 3:
				raise ValueError('write the ISO3 code of the country (e.g. ESP)')
			return {'country': code}
		layer = self.layer.currentLayer()
		if layer is None:
			raise ValueError('choose a layer of polygons')
		self.sync_fields()
		return self.layer_region(layer, self.name_field.currentField())

	def layer_region(self, layer, field):
		"""The region of the polygons of LAYER (its selected features, or all), named by its field FIELD (or their
		number), in WGS 84: {'geojson': FeatureCollection}."""
		wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
		feats = list(layer.getSelectedFeatures()) or list(layer.getFeatures())
		if not feats:
			raise ValueError(f'the layer {layer.name()} has no features')
		tr = QgsCoordinateTransform(layer.crs(), wgs84, QgsProject.instance())
		vertices = sum(f.geometry().constGet().nCoordinates() for f in feats if f.hasGeometry())
		tol = 0.0001 * max(1.0, vertices / MAX_VERTICES)  # degrees: simplify only big geometries
		out = []
		for f in feats:
			if not f.hasGeometry():
				continue
			g = f.geometry()
			g.transform(tr)
			if vertices > MAX_VERTICES:
				g = g.simplify(tol)
			name = f[field] if field else f.id()
			out.append({'type': 'Feature', 'properties': {'name': str(name)}, 'geometry': json.loads(g.asJson())})
		return {'geojson': {'type': 'FeatureCollection', 'features': out}}

	def variable_args(self):
		v = self.variable.currentData()
		where = self.where_args()
		if v.get('custom'):  # data of Earth Engine by its ID: no variable, sensor nor pixel filters (their own mask)
			args = self.data_args()
			if 'collection' in args:  # images with dates; a fixed image has none (greyed out, as the elevation)
				args.update(start=self.start.date().toString('yyyy-MM-dd'), end=self.end.date().toString('yyyy-MM-dd'))
				if self.season_on.isChecked():
					args['season'] = [self.season_start.text().strip(), self.season_end.text().strip()]
			if where:  # conditions on variables of the catalog
				args['where'] = where
			return args
		if v.get('static'):  # elevation, slope: without dates, pixel filters or season (greyed out), nor in the README
			return dict({'variable': v['variable'], 'sensor': v['sensor'], 'collection': v['collection']},
			            **({'where': where} if where else {}))
		args = {'variable': v['variable'], 'sensor': v['sensor'], 'collection': v['collection'],
		        'start': self.start.date().toString('yyyy-MM-dd'), 'end': self.end.date().toString('yyyy-MM-dd'),
		        'quality': self.quality_args()}
		if self.season_on.isChecked():
			args['season'] = [self.season_start.text().strip(), self.season_end.text().strip()]
		if where:
			args['where'] = where
		return args

	def data_args(self):
		"""The data of Earth Engine of the panel as the services take them instead of variable and sensor:
		{'collection' or 'image': its ID, 'band'} (or the list of the bands checked, with 'band_reducer') and the
		'band_scale', 'band_offset' and 'unit' written (see monitoreo.assets)."""
		asset = self.asset_text()
		if not asset:
			raise ValueError('Earth Engine data: write the ID of an image or a collection of images (or choose a '
			                 'dataset) and press Read')
		reducer = self.band_reducer.currentData()
		bands = self.chosen_bands()
		if not bands:
			raise ValueError(f'Earth Engine data: choose or write the band of {asset} (Read lists them)')
		if reducer and len(bands) < 2:
			raise ValueError(f'Earth Engine data: check two or more bands of {asset} to combine them (or choose One '
			                 'band in Combine bands)')
		if not reducer and len(bands) > 1:
			raise ValueError(f"Earth Engine data: to combine the bands {', '.join(bands)} of {asset}, choose Sum or "
			                 'Mean of the bands in Combine bands; or write one band')
		read = self.described()
		names = [b.get('band') for b in (read or {}).get('bands') or []]
		for band in bands:
			if read and band not in names:
				raise ValueError(f"Earth Engine data: {asset} has no band {band}: choose one of {', '.join(names)}")
		args = {self.asset_use.currentData(): asset, 'band': bands if reducer else bands[0]}
		if reducer:
			args['band_reducer'] = reducer
		for key, w in (('band_scale', self.band_scale), ('band_offset', self.band_offset)):
			text = w.text().strip().replace(',', '.')
			if text:
				try:
					args[key] = float(text)
				except ValueError:
					raise ValueError(f"Earth Engine data: the {key.replace('_', ' ')} of {asset} is not a number: "
					                 f'{text}') from None
		unit = self.asset_unit.text().strip()
		if unit:
			args['unit'] = unit
		return args

	def asset_text(self):
		"""The ID written, as the services take it (monitoreo.assets.normalize: also ee.ImageCollection('...'))."""
		return assets.normalize(self.asset_id.text())

	def described(self):
		"""What services.describe_asset said of the ID written, or None if it has not been read."""
		read = self.asset_info
		return read if read and read.get('asset') == self.asset_text() else None

	def custom_entry(self):
		"""The data of Earth Engine of the panel as an entry of the list Variable, so that the panel treats them as a
		variable: an image is a fixed layer without dates (static: no series, trends, comparisons nor exports of
		series), they have no pixel filters (fixed_filters: none) nor true colour (rgb), and they have no variable nor
		sensor of the catalog (custom); several bands combined, with their list (bands) and band_reducer."""
		asset, band, use = self.asset_text(), self.asset_band.currentText().strip(), self.asset_use.currentData()
		reducer = self.band_reducer.currentData() or None
		bands = self.chosen_bands() if reducer else ([band] if band else [])
		what = variables.band_text({'band': bands, 'band_reducer': reducer})  # 'pr', or 'sum of aet, def'
		return {'custom': True, 'asset': asset, 'band': band, 'bands': bands, 'band_reducer': reducer, 'use': use,
		        'static': use == 'image', 'fixed_filters': [], 'rgb': False,
		        'name': f'{asset} {what}'.strip() or 'Earth Engine data',
		        'band_scale': self.band_scale.text().strip(), 'band_offset': self.band_offset.text().strip(),
		        'unit': self.asset_unit.text().strip()}

	def custom_changed(self):
		"""The data of Earth Engine changed: their entry of the list Variable, and what applies to them."""
		if not hasattr(self, 'where'):  # not built yet
			return
		if (self.variable.currentData() or {}).get('custom'):
			self.variable.setItemData(0, self.custom_entry())
			self.variable_changed()

	def show_data(self):
		"""The options of the data of Earth Engine in their themes (those of the GEE Community Catalog only in its
		own), instead of the list Variable."""
		data = self.data_themes.get(self.theme.currentData())
		self.data_row.setVisible(data is not None)
		self.community_row.setVisible(data == 'community')
		self.search_row.setVisible(data == 'earth_engine')
		for w in (self.variable_field, self.variable_label):
			if w is not None:
				w.setVisible(data is None)

	def read_asset(self, asset=None):
		"""Read in Earth Engine what the ID ASSET (default: the one written) is, with services.describe_asset in a
		task with the project of the panel (metadata, without computing), and fill its bands, its use, the scale,
		offset and unit of its band and what its record says."""
		asset = assets.normalize(asset or self.asset_id.text())
		if not asset:
			self.message(READ_HINT, 'Warning')
			return

		def work():
			try:
				return services.describe_asset(asset)
			except Exception as e:  # an unknown ID, one without access, a table...: also said under the options
				return {'asset': asset, 'error': str(e)}

		self.run_task(f'Read {asset} in Earth Engine', work, self.asset_read)

	def asset_read(self, d):
		"""Show what services.describe_asset said (D): its bands (the one of its arguments chosen, or the one written
		if it has it), how it is used (only as a fixed image if it is an image), the scale, offset and unit of the band
		and its title, source, licence and page; or why it could not be read. Nothing if another ID was written
		meanwhile (its own Read applies)."""
		if d['asset'] != self.asset_text():
			return
		if d.get('error'):
			self.asset_label.setText(f"<b>{esc(d['asset'])}</b>: it could not be read: {esc(d['error'])}")
			self.message(f"Read {d['asset']} in Earth Engine: {d['error']}", 'Critical', 15)
			return
		self.asset_info = d
		typed = self.asset_band.currentText().strip()
		# the bands checked to combine (those of the settings, or written with commas, before the first Read)
		checked = self.checked_bands() if self.asset_bands.count() else \
			(self.saved_bands or variables.bands_of({'band': typed}))
		if self.asset_id.text() != d['asset']:
			self.asset_id.setText(d['asset'])
		bands = d.get('bands') or []
		names = [b['band'] for b in bands]
		self.filling_bands = True
		self.asset_bands.clear()
		for b in bands:
			self.asset_bands.addItemWithCheckState(
				f"{b['band']}" + (f" · {b['resolution_m']:g} m" if b.get('resolution_m') else ''),
				Qt.CheckState.Checked if b['band'] in checked else Qt.CheckState.Unchecked, b['band'])
		self.filling_bands = False
		self.saved_bands = []
		self.asset_band.blockSignals(True)
		self.asset_band.clear()
		for b in bands:
			self.asset_band.addItem(b['band'], b)
			tip = ' · '.join(str(x) for x in (b.get('description'), b.get('units'), b.get('resolution_m') and
			                                  f"{b['resolution_m']:g} m", b.get('data_type')) if x)
			self.asset_band.setItemData(self.asset_band.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
		chosen = typed if typed in names else (d.get('arguments') or {}).get('band')
		self.asset_band.setCurrentIndex(names.index(chosen) if chosen in names else (0 if names else -1))
		self.asset_band.blockSignals(False)
		image = d.get('type') == 'image'
		self.asset_use.setCurrentIndex(max(0, self.asset_use.findData(d.get('use') or 'collection')))
		self.asset_use.setEnabled(not image)  # an image has no dates: never a collection
		self.asset_use.setToolTip('An image has no dates: only a fixed image (maps and their statistics)' if image
		                          else 'As its record suggests; a collection of tiles (e.g. a DEM) is a fixed image')
		self.first_band = None  # the scale, offset and unit of the band chosen, as its record says
		self.band_changed()
		self.show_bands()
		self.asset_label.setText(data_summary(d))
		self.custom_changed()
		self.message(f"{d['asset']}: {data_use(d)} ({len(names)} band{'' if len(names) == 1 else 's'})", 'Success', 10)

	def asset_edited(self):
		"""A new ID written by hand or chosen in the GEE Community Catalog: what was read of the former one no longer
		applies until it is read."""
		self.asset_use.setEnabled(True)
		self.asset_use.setToolTip('')
		self.asset_label.setText(READ_HINT)

	def checked_bands(self):
		"""The bands checked in the list Bands, in the order of the data (jan to dec)."""
		return [self.asset_bands.itemData(i) for i in range(self.asset_bands.count())
		        if self.asset_bands.itemCheckState(i) == Qt.CheckState.Checked]

	def chosen_bands(self):
		"""The bands of the panel: those checked in Bands to combine them (Sum or Mean of the bands) once read, or else
		those written in Band (one, or several separated by commas)."""
		if self.band_reducer.currentData() and self.asset_bands.count():
			return self.checked_bands()
		if self.band_reducer.currentData() and self.saved_bands:  # those saved, until Read lists the bands again
			return list(self.saved_bands)
		return variables.bands_of({'band': self.asset_band.currentText()})

	def show_bands(self):
		"""The checkable list Bands when the bands read are combined (Sum or Mean of the bands); Band otherwise (one
		band, or several written with commas before Read)."""
		listed = bool(self.band_reducer.currentData()) and self.asset_bands.count() > 0
		for w in (self.bands_field, self.bands_label):
			w.setVisible(listed)
		for w in (self.band_field, self.band_label):
			w.setVisible(not listed)
		self.bands_note.setVisible(listed and bool(self.bands_note.text()))

	def bands_checked(self):
		"""A band checked or unchecked in Bands (not while they are listed): its scale, offset and unit, the note and
		the entry of the list Variable."""
		if not self.filling_bands:
			self.band_changed()
			self.custom_changed()

	def reducer_changed(self):
		"""One band, or several combined: the band chosen is the first one checked if none was."""
		if self.band_reducer.currentData() and self.asset_bands.count() and not self.checked_bands():
			i = self.asset_bands.findData(self.asset_band.currentText().strip())
			if i >= 0:
				self.asset_bands.setItemCheckState(i, Qt.CheckState.Checked)  # also band_changed
		self.band_changed()
		self.show_bands()
		self.custom_changed()

	def band_changed(self):
		"""The scale, offset and unit of the band chosen (of the first one checked, to combine several), as the record
		of its data says (services.describe_asset), when it changes; if it gives its unit but not in UDUNITS, the field
		says it. With several, a note if they differ in pixel size, unit, scale or offset."""
		b = self.asset_band.currentData()
		if self.band_reducer.currentData() and self.asset_bands.count():
			records = {r['band']: r for r in (self.described() or {}).get('bands') or []}
			chosen = [records[x] for x in self.checked_bands() if x in records]
			self.bands_note.setText(bands_note(chosen))
			self.show_bands()
			b = chosen[0] if chosen else None
		if not isinstance(b, dict) or b.get('band') == getattr(self, 'first_band', None):  # written, or the same
			return
		self.first_band = b.get('band')
		self.band_scale.setText(number(b.get('band_scale')))
		self.band_offset.setText(number(b.get('band_offset')))
		self.asset_unit.setText(b.get('unit') or '')
		self.asset_unit.setPlaceholderText(f"its record says {b['units']}: write it in UDUNITS" if b.get('units') and
		                                   not b.get('unit') else 'e.g. mm, degC, kg m-2, mm day-1 or 1 (dimensionless)')

	def fill_datasets(self):
		"""The datasets of the theme of the GEE Community Catalog chosen (services.community_datasets, from the copy of
		its index in MonitorEO: no Earth Engine), none of them chosen."""
		self.community_records = {}
		self.community_dataset.clear()
		for d in services.community_datasets(theme=self.community_theme.currentData()):
			self.community_records[d['id']] = d
			kind = 'collection' if d['type'] == 'image_collection' else 'image'
			self.community_dataset.addItem(f"{d['title']} ({kind})", d['id'])
			licence = d.get('license_text') if d.get('license') == 'custom' else d.get('license')
			self.community_dataset.setItemData(self.community_dataset.count() - 1,
			                                   '\n'.join(x for x in (d['id'], d.get('provider'), licence and
			                                                         f'Licence: {licence}') if x),
			                                   Qt.ItemDataRole.ToolTipRole)
		self.community_dataset.setCurrentIndex(-1)

	def search_catalog(self):
		"""The datasets of the Earth Engine data catalog with the words written (services.find_datasets): the
		collections of images with data in the period and the images (fixed) whatever their dates, over the region of
		the map view when it is the region (within the world: a view zoomed out goes beyond it), in the list Dataset."""
		bbox = None
		if self.region_kind.currentData() == 'extent':
			canvas = self.iface.mapCanvas()
			tr = QgsCoordinateTransform(canvas.mapSettings().destinationCrs(), QgsCoordinateReferenceSystem('EPSG:4326'),
			                            QgsProject.instance())
			r = tr.transformBoundingBox(canvas.extent())
			w, s, e, n = max(r.xMinimum(), -180), max(r.yMinimum(), -90), min(r.xMaximum(), 180), min(r.yMaximum(), 90)
			bbox = [w, s, e, n] if w < e and s < n else None  # a view outside the world: all of it
		try:
			found = services.find_datasets(self.catalog_text.text(), self.start.date().toString('yyyy-MM-dd'),
			                               self.end.date().toString('yyyy-MM-dd'), bbox, limit=50)
		except ValueError as e:
			self.message(str(e), 'Warning')
			return
		self.catalog_records = {d['id']: d for d in found}
		self.catalog_found.clear()
		for d in found:
			kind = 'collection' if d['type'] == 'image_collection' else 'image'
			years = f"{(d.get('start') or '?')[:4]}-{(d.get('end') or 'now')[:4]}"
			self.catalog_found.addItem(f"{d['title']} ({kind}, {years})", d['id'])
			self.catalog_found.setItemData(self.catalog_found.count() - 1, d['id'], Qt.ItemDataRole.ToolTipRole)
		self.catalog_found.setPlaceholderText(f'{len(found)} datasets: choose one' if found else
		                                      'none: try other words in English')
		self.catalog_found.setCurrentIndex(-1)

	def catalog_chosen(self, i):
		"""A dataset of the Earth Engine data catalog chosen: its ID, then read in Earth Engine (its bands)."""
		asset = self.catalog_found.itemData(i)
		if not asset:
			return
		self.asset_id.setText(asset)
		self.asset_edited()
		self.read_asset(asset)

	def dataset_chosen(self, i):
		"""A dataset of the GEE Community Catalog chosen: its ID and what its record says, then read in Earth Engine
		(its bands)."""
		asset = self.community_dataset.itemData(i)
		if not asset:
			return
		rec = self.community_records.get(asset) or {}
		self.asset_id.setText(asset)
		self.asset_edited()
		self.asset_label.setText(data_summary({
			'asset': asset, 'title': rec.get('title'), 'source': 'GEE Community Catalog', 'provider': rec.get('provider'),
			'licence': rec.get('license_text') if rec.get('license') == 'custom' else rec.get('license'),
			'page': rec.get('docs'), 'type': rec.get('type')}, read=False))
		self.read_asset(asset)

	def quality_args(self, own=False, auto=False):
		"""The pixel filters checked in the panel (clouds, with Cloud Score+ or the SCL of Sentinel-2). OWN: those the
		user chose, also while the variable selected greys some out (all of them the fixed filters of the elevation, the
		slope and the cloud or snow cover frequency; that of what it measures the NDSI, the NDWI...), for the analyses
		that compute other variables (the burn severity, the NBR). AUTO: 'auto' instead of True, so that each variable
		computed with them leaves out the filter of what it measures (sensors.filters), as those of a profile on two
		axes."""
		quality = self.own_filters() if own else {k: w.isChecked() for k, w in self.filters.items()}
		if auto:
			quality = {k: 'auto' if on else False for k, on in quality.items()}
		quality['cloud_score'] = 0.6 if self.cloud_score.isChecked() else None
		if self.topographic.isChecked() and (own or self.topographic.isEnabled()):  # SCS+C, only when asked
			quality['topographic'] = True
		if self.snow_ndsi.isChecked() and (own or self.snow_ndsi.isEnabled()):  # the snow by its NDSI, when asked
			quality['snow_ndsi'] = sensors.SNOW_NDSI_DEFAULT
		for k in ('harmonize', 'landsat7'):  # Landsat 5 and 7 as 8 and 9, Landsat 7 after 2003: when asked
			box = getattr(self, k)
			if box.isChecked() and (own or box.isEnabled()):
				quality[k] = True
		return quality

	def coverage_args(self):
		"""{'min_coverage': MIN_COVERAGE} when its check box is checked (the series, their comparison, the trend table
		and the export of the series), else {}."""
		return {'min_coverage': MIN_COVERAGE} if self.min_coverage.isChecked() else {}

	def snow_ndsi_enabled(self, v=None):
		"""The check box of the snow by its NDSI, enabled for the variables of the catalog of Sentinel-2 and Landsat with
		the snow filter checked, not for those with fixed filters nor those that measure water (sensors.snow_ndsi_of)."""
		v = v if v is not None else (self.variable.currentData() or {})
		on = (v.get('fixed_filters') is None and not v.get('custom') and v.get('sensor') in sensors.SNOW_NDSI
		      and v.get('variable') not in sensors.MEASURES['water'] and self.filters['snow'].isChecked())
		self.snow_ndsi.setEnabled(on)
		self.snow_ndsi.setToolTip('' if on else NO_SNOW_NDSI)

	def own_filters(self):
		"""The pixel filters chosen by the user: those checked in the panel and, of those that the variable chosen sets
		and greys out (set_filters), those checked before choosing it."""
		return {k: self.chosen_filters[k] if k in self.set_filters else w.isChecked() for k, w in self.filters.items()}

	def fill_variables(self, choose=None):
		"""The variables of the theme chosen (all of them with «All the variables»), keeping the one chosen if it is
		there; else CHOOSE (the start of its text) or the first one. In the themes of the data of Earth Engine outside
		the catalog, only the entry of those data (custom_entry), with their options instead of the list."""
		key = self.theme.currentData()
		was = self.variable.currentData() or {}
		current = (self.catalog_choice if was.get('custom') else self.variable.currentText()) or choose
		self.variable.blockSignals(True)
		self.variable.clear()
		if key in self.data_themes:
			self.catalog_choice = current  # chosen again back in a theme of the catalog
			self.variable.addItem('Earth Engine data (by its ID)', self.custom_entry())
			self.variable.blockSignals(False)
			self.show_data()
			if hasattr(self, 'where'):  # built: the options of the data
				self.variable_changed()
			return
		for v in self.all_variables:
			if key is not None and (catalog.theme_of(v['variable']) or {}).get('key') != key:
				continue
			self.variable.addItem(f"{v['variable']} · {v['sensor']} · {v['resolution_m']} m · "
			                      f"{v['collection'].split('/')[-1]}", v)
			self.variable.setItemData(self.variable.count() - 1, f"{v['name']} ({v['unit']}), {v['dates']}",
			                          Qt.ItemDataRole.ToolTipRole)
		self.variable.setCurrentIndex(max(0, self.variable.findText(current or '', Qt.MatchFlag.MatchStartsWith)))
		self.variable.blockSignals(False)
		self.show_data()
		if hasattr(self, 'where'):  # built: the options of the variable chosen
			self.variable_changed()

	def landcover_group(self, s, main):
		"""The land cover mask (monitoreo.landcover), before the variable: a group that unfolds when checked, with the
		land cover map, its year and the broad land covers to leave out of every result (a condition of where)."""
		box = QgsCollapsibleGroupBox('Land cover mask')
		box.setCheckable(True)
		box.setChecked(str(s.value(SETTINGS + 'landcover_on', 'false')).lower() == 'true')
		box.setCollapsed(not box.isChecked())
		box.toggled.connect(lambda on: box.setCollapsed(not on))
		self.landcover_box = box
		f = QFormLayout(box)
		self.landcover_map = QComboBox()
		for m in landcover.maps():
			self.landcover_map.addItem(f"{m['name']} · {m['m']} m · {m['coverage']}", m['key'])
		self.landcover_map.setCurrentIndex(max(0, self.landcover_map.findData(s.value(SETTINGS + 'landcover_map',
		                                                                              'WorldCover'))))
		f.addRow('Map', info(self.landcover_map, HELP['landcover_map']))
		self.landcover_year = QComboBox()
		f.addRow('Year', self.landcover_year)
		self.landcover_classes = QgsCheckableComboBox()
		self.landcover_classes.setDefaultText('choose the land covers')
		chosen = str(s.value(SETTINGS + 'landcover_exclude', 'water,built')).split(',')
		for c in landcover.classes():
			self.landcover_classes.addItemWithCheckState(
				c['en'], Qt.CheckState.Checked if c['key'] in chosen else Qt.CheckState.Unchecked, c['key'])
			self.landcover_classes.setItemData(self.landcover_classes.count() - 1, c['help'],
			                                   Qt.ItemDataRole.ToolTipRole)
		f.addRow('Leave out', info(self.landcover_classes, self.landcover_help))
		self.fill_landcover_years(s.value(SETTINGS + 'landcover_year', ''))
		self.landcover_map.currentIndexChanged.connect(lambda i: self.fill_landcover_years())
		main.addWidget(box)

	def fill_landcover_years(self, year=None):
		"""The years of the land cover map chosen, keeping YEAR (or the year chosen) if the map has it; otherwise its
		last one (for Dynamic World, the last whole year)."""
		m = landcover.find(self.landcover_map.currentData())
		year = str(year or self.landcover_year.currentData() or '')
		self.landcover_year.blockSignals(True)
		self.landcover_year.clear()
		for y in reversed(landcover.years(m)):
			self.landcover_year.addItem(str(y), y)
		i = self.landcover_year.findData(int(year)) if year.isdigit() else -1
		self.landcover_year.setCurrentIndex(i if i >= 0 else self.landcover_year.findData(landcover.default_year(m)))
		self.landcover_year.blockSignals(False)

	def landcover_help(self):
		"""The help of «Leave out»: the classes of the map chosen that are each broad land cover."""
		m = landcover.find(self.landcover_map.currentData())
		rows = []
		for c in landcover.classes():
			codes = sorted((code for code, k in m['classes'].items() if k == c['key']), key=int)
			names = ', '.join(f"{code} {m['names'][code]}" for code in codes) or 'none'
			rows.append(f"<li><b>{esc(c['en'])}</b>: {esc(names)}</li>")
		return HELP['landcover'] + f"<p>The classes of {esc(m['name'])} in each:</p><ul>{''.join(rows)}</ul>"

	def landcover_args(self):
		"""The land cover condition of where of the group «Land cover mask» (see monitoreo.landcover), or None if it is
		off."""
		if not self.landcover_box.isChecked():
			return None
		exclude = [k for k in self.landcover_classes.checkedItemsData()]
		if not exclude:
			raise ValueError('Land cover mask: check the land covers to leave out (or uncheck the mask)')
		return {'landcover': self.landcover_map.currentData(), 'year': self.landcover_year.currentData(),
		        'exclude': exclude}

	def where_args(self, period=None):
		"""The checked conditions of «Only the pixels where» (see monitoreo.variable.where_specs), or None. Those of
		variables with dates are the mean over the period of the panel (or PERIOD: the first and the last day), fixed
		in each condition, so that the maps of each step of a series, and the other period of a comparison, keep the
		same pixels."""
		out = []
		for c in self.where:
			if not c['on'].isChecked():
				continue
			v = c['variable'].currentData()
			if v.get('categorical'):  # its classes to keep or to leave out (checked here, without Earth Engine)
				entry = catalog.find(v['variable'], v['sensor'])
				if not c['codes'].text().strip():
					raise ValueError(f"Only the pixels where: give the codes of the classes of {v['variable']} (Classes…)")
				codes = categorical.check(entry, c['codes'].text(), c['keep'].currentData())
				out.append({'variable': v['variable'], 'sensor': v['sensor'], c['keep'].currentData(): codes})
				continue
			limits = {}
			for key in ('min', 'max'):
				text = c[key].text().strip().replace(',', '.')
				if text:
					try:
						limits[key] = float(text)
					except ValueError:
						raise ValueError(f"Only the pixels where: the {key} of {v['variable']} is not a number: {text}")
			if not limits:
				raise ValueError(f"Only the pixels where: give a min, a max or both for {v['variable']}")
			cond = {'variable': v['variable'], 'sensor': v['sensor'], 'collection': v['collection'], **limits}
			if not v.get('static'):
				cond['period'] = list(period or (self.start.date().toString('yyyy-MM-dd'),
				                                 self.end.date().toString('yyyy-MM-dd')))
			out.append(cond)
		lc = self.landcover_args()  # the land covers left out: a map of a year, not the period
		if lc:
			out.append(lc)
		return out or None

	def where_changed(self):
		"""The unit of each condition of «Only the pixels where», and the period on when a condition needs it (a
		variable with dates filtering a fixed layer)."""
		for c in self.where:
			v = c['variable'].currentData() or {}
			klass = bool(v.get('categorical'))  # class codes: the classes to keep or to leave out, not min and max
			c['unit'].setText('' if klass else v.get('unit') or '')
			for key in ('variable', 'min', 'max', 'keep', 'codes', 'pick'):
				c[key].setEnabled(c['on'].isChecked())
			for w in (c['min'], c['max']) + c['labels']:
				w.setVisible(not klass)
			for key in ('keep', 'codes', 'pick'):
				c[key].setVisible(klass)
		self.variable_changed()

	def pick_class(self, c):
		"""The list of the classes of the categorical layer of the condition C of «Only the pixels where» (code and name),
		to add the code of the class chosen to its codes."""
		v = c['variable'].currentData() or {}
		if not v.get('categorical'):
			return
		items = [f"{x['code']} {x['name']}" for x in services.list_classes(v['variable'], v['sensor'])]
		item, ok = QInputDialog.getItem(self, f"Classes of {v['variable']}", 'Class (code and name):', items, 0, False)
		if ok and item:
			given = [x.strip() for x in c['codes'].text().replace(';', ',').split(',') if x.strip()]
			code = item.split(' ', 1)[0]
			if code not in given:
				c['codes'].setText(', '.join(given + [code]))

	# Tasks ------------------------------------------------------------------------------------------------------

	def run_task(self, description, work, done):
		"""Run WORK() in a QGIS task and DONE(result) in the main thread; errors go to the message bar. The log of the
		plugin (sendlogs) has the task, its end and, if it failed, its traceback."""
		self.save_settings()
		project = self.project.text().strip() or None

		def run(task):
			services.init(project, shared=not project, warn=False)  # an empty field: the shared account of MonitorEO
			return work()

		def finished(exception, result=None):
			self.tasks = [t for t in self.tasks if t is not task]
			if isinstance(exception, services.TooManyPixels):  # nothing computed: until the user closes it
				sendlogs.write({'task': description, 'end': 'too many pixels'})
				self.message(too_many_text(description, exception), 'Warning', 0)
				return
			if exception is not None:
				sendlogs.write_failure(description, exception)
				# why it failed, perhaps (not for the errors of its arguments): Earth Engine in restricted mode
				quota = None if isinstance(exception, (ValueError, KeyError, TypeError)) else quota_text()
				self.message(f'{description}: {exception}' + (f' {quota}' if quota else ''), 'Critical', 15)
				return
			try:
				done(result)
			except Exception as e:
				sendlogs.write_failure(f'{description} (showing its result)', e)
				self.message(f'{description}: {e}', 'Critical', 15)
			else:
				sendlogs.write({'task': description, 'end': 'done'})
			warned = result_warnings(result)
			if warned:  # days of its period without images of its data: the window of the result shows them too
				self.message(f"{description}: {' '.join(warned)}", 'Warning', 30)
			quota = quota_text(once=True)
			if quota:  # Earth Engine has put the project in restricted mode: once each time
				self.message(quota, 'Warning', 60)

		task = QgsTask.fromFunction(description, run, on_finished=finished)
		self.tasks.append(task)
		QgsApplication.taskManager().addTask(task)
		sendlogs.write({'task': description, 'account': 'own project' if project else 'shared'})
		self.message(f'{description}…', 'Info', 3)
		return task

	def connect(self):
		self.run_task('Connect to Earth Engine', lambda: (services.project(), services.shared()),
		              lambda r: self.message(f'Connected to Earth Engine with the shared account of MonitorEO '
		                                     f'(project {r[0]})' if r[1] else
		                                     f'Connected to Earth Engine with your account (project {r[0]})', 'Success'))

	def list_projects(self, signed_in=False):
		"""The Google Cloud projects of the account of Authenticate… registered in Earth Engine
		(services.own_projects), in a menu under the button Projects…: the one chosen goes to the field Project.
		SIGNED_IN: right after signing in (then nothing is said when none is found)."""
		known = [self.project.text().strip()] if self.project.text().strip() else []

		def finished(exception, result=None):
			self.tasks = [t for t in self.tasks if t is not task]
			if exception is not None:
				self.message(f'Your projects: {exception}', 'Warning', 15)
				return
			found = result['projects']
			if not found:
				if not signed_in:
					self.message('No project of your Google account registered in Earth Engine was found (Google does '
					             'not let MonitorEO list them all): write yours in Project, or register one at '
					             + result['register'], 'Warning', 30)
				return
			menu = QMenu(self.projects_button)
			for p in found:
				label = p['project'] + (f" ({p['name']})" if p['name'] and p['name'] != p['project'] else '')
				action = menu.addAction(label + (' · commercial' if p['registration'] == 'commercial' else ''))
				action.triggered.connect(lambda checked=False, project=p['project']: self.project.setText(project))
			menu.addSeparator()
			action = menu.addAction('Shared account of MonitorEO (empty project)')
			action.triggered.connect(lambda checked=False: self.project.setText(''))
			menu.exec(self.projects_button.mapToGlobal(self.projects_button.rect().bottomLeft()))

		task = QgsTask.fromFunction('Your projects of Earth Engine', lambda t: services.own_projects(known),
		                            on_finished=finished)
		self.tasks.append(task)
		QgsApplication.taskManager().addTask(task)

	def authenticate(self):
		def work():
			import ee
			ee.Authenticate(auth_mode='localhost', force=True)
			return True

		def finished(exception, result=None):
			self.tasks = [t for t in self.tasks if t is not task]
			if exception is not None:
				self.message(f'Authentication: {exception}', 'Critical', 10)
				return
			self.message('Authenticated with Earth Engine: choose your project', 'Success', 10)
			self.list_projects(signed_in=True)

		task = QgsTask.fromFunction('Authenticate with Earth Engine', lambda t: work(), on_finished=finished)
		self.tasks.append(task)
		QgsApplication.taskManager().addTask(task)
		self.message('Sign in with your Google account in the browser', 'Info', 10)

	def search_wdpa(self):
		text = self.wdpa_text.text().strip()
		if not text:
			return

		def done(parks):
			self.wdpa.clear()
			for p in parks:
				self.wdpa.addItem(f"{p['NAME']} · {p.get('DESIG', '')} · {p.get('ISO3', '')} · {p.get('REP_AREA', 0):,.0f} km² "
				                  f"(WDPA {p['SITE_ID']})", int(p['SITE_ID']))
			self.message(f'{len(parks)} protected areas with "{text}"', 'Info', 4)

		more = {'designation': 'ramsar'} if self.ramsar.isChecked() else {}
		self.run_task('Search protected areas', lambda: services.find_protected_areas(text, 30, **more), done)

	def admin_level_changed(self):
		"""Level 3, the municipalities of Spain: the country is Spain (ESP), greyed out, and the text a name or a code
		of the INE; back at levels 1 and 2 (FAO GAUL 2025, any country), the country written before."""
		spain = self.admin_level.currentData() == municipalities.LEVEL
		if spain == self.admin_country.isEnabled():  # from FAO GAUL to the municipalities of Spain, or back
			if spain:
				self.admin_country_typed = self.admin_country.text()
			self.admin_country.setText(municipalities.COUNTRY if spain else self.admin_country_typed)
		self.admin_country.setEnabled(not spain)
		self.admin_country.setToolTip(ADMIN_SPAIN_TIP if spain else ADMIN_COUNTRY_TIP)
		self.admin_text.setPlaceholderText(ADMIN_HINTS[self.admin_level.currentData()])

	def search_admin(self):
		"""The administrative units of the level chosen with the text in their name, in the list Unit: those of FAO
		GAUL 2025 (levels 1 and 2, in the country if given) in a task, since they are searched in Earth Engine; the
		municipalities of Spain (level 3; also by their code of the INE) at once, from the index of the package,
		without Earth Engine."""
		text, level = self.admin_text.text().strip(), self.admin_level.currentData()
		country = self.admin_country.text().strip().upper() or None
		if not text:
			return
		spain = level == municipalities.LEVEL

		def done(units):
			self.admin.clear()
			for u in units:
				self.admin.addItem(*admin_item(u, level))
			what = 'municipalities of Spain' if spain else 'administrative units'
			self.message(f'{len(units)} {what} with "{text}"', 'Info', 4)

		if spain:  # no Earth Engine: no task, and the country is Spain
			try:
				done(services.find_admin_units(text, level, None, 30))
			except Exception as e:  # to the message bar, as the errors of run_task
				self.message(f'Search municipalities: {e}', 'Critical', 15)
			return
		self.run_task('Search administrative units', lambda: services.find_admin_units(text, level, country, 30), done)

	def search_seas(self):
		"""The oceans and seas with the text in their name (in English, any case and accents; or an MRGID), in the list
		Sea, at once: from the index of the package, without Earth Engine."""
		text = self.sea_text.text().strip()
		if not text:
			return
		self.sea.clear()
		found = services.find_seas(text, 30)
		for s in found:
			self.sea.addItem(*sea_item(s))
		self.message(f'{len(found)} seas with "{text}"' if found else
		             f'No sea with "{text}": write its English name (e.g. Alboran, Biscay, Mediterranean)', 'Info', 4)

	def other_period(self):
		"""(first day, last day) of the period to compare with the reference one, or None."""
		if not self.compare_on.isChecked() or (self.variable.currentData() or {}).get('static'):
			return None
		return self.other_start.date().toString('yyyy-MM-dd'), self.other_end.date().toString('yyyy-MM-dd')

	def add_result(self, res):
		"""Keep a result (series, trends, comparison or burn severity) in the list of the session and open its
		window."""
		self.series.append(res)
		self.update_series_list()
		self.series_list.setCurrentIndex(self.series_list.count() - 1)
		self.show_series()

	def series_call(self):
		"""The time series of the panel ('time_series', its arguments) or, with Compare with, the comparison of its
		periods ('compare_series'); ValueError if the fields are not valid."""
		region, var = self.region(), self.variable_args()
		step, metric, stat = self.step.currentData(), self.ts_metric.currentData(), self.stat.currentData()
		other = self.other_period()
		if other:
			if step not in trends.STEPS:
				raise ValueError('To compare periods, choose the step Monthly, 16 days or Annual')
			return 'compare_series', dict(region=region, **var, other_start=other[0], other_end=other[1], step=step,
			                              metric=metric, stat=stat, **self.coverage_args())
		doy = self.doy.isChecked() and step != 'annual'  # a line per year: not with a value per year
		profile = self.doy_args(var) if doy else {}
		if profile.get('other_variable'):
			# each axis with the filters the user chose, not the greyed out ones of the variable of the left axis (all of
			# them with the SCF, the CF and the data by ID, which ignore them; that of what it measures with the NDSI...),
			# as 'auto': each variable leaves out the filter of what it measures, e.g. the snow of the NDSI, not the NDVI
			quality = self.quality_args(own=True, auto=True)
			if not (self.variable.currentData() or {}).get('topographic'):  # greyed out: not for the left axis
				quality.pop('topographic', None)  # (the right axis gets it only if it can, services._other_spec)
			if not self.snow_ndsi.isEnabled():  # the snow by its NDSI, likewise
				quality.pop('snow_ndsi', None)
			for k in ('harmonize', 'landsat7'):  # the Landsat options, likewise (services._other_spec)
				if not getattr(self, k).isEnabled():
					quality.pop(k, None)
			var = dict(var, quality=quality)
		return 'time_series', dict(region=region, **var, step=step, metric=metric, stat=stat, doy=doy, **profile,
		                           **self.coverage_args())

	def run_series(self):
		call = self.call_of('series')
		if not call:
			return
		analysis, args = call
		tmp = tempfile.mkdtemp(prefix='monitoreo_')
		if analysis == 'compare_series':
			return self.run_comparison(args, tmp)
		# what its maps keep (add_result_map): the arguments of the variable, the region, the step and the metric
		var = {k: v for k, v in args.items() if k not in ('stat', 'doy', 'interannual', 'other_variable', 'other_sensor')}
		name = data_name(var) + (f" and {args['other_variable']} ({args['other_sensor']})"
		                         if args.get('other_variable') else '')

		def work():
			return services.time_series(csv=os.path.join(tmp, 'series.csv'), **args)

		def done(res):
			from .results import SeriesDialog, chart_png
			if not res['rows']:
				self.message('The series has no values', 'Warning')
				return
			# the chart is drawn here, in the main thread: matplotlib in the thread of a task can crash QGIS (the
			# OpenBLAS of numpy overflows the small stack of those threads on macOS)
			res['chart'] = chart_png(res, os.path.join(tmp, 'series.png'))
			res['label'] = f"{res['title']} · {', '.join(res['regions'])}"
			res['kind'] = 'series'
			res['call'] = parameters.make(analysis, args)
			res['args'] = dict(var)
			res['maps'] = result_maps('time_series', res['args'])
			# whether its maps can also be the true colour of their images (the list Layer of its window): never for
			# the data of Earth Engine outside the catalog
			res['rgb'] = False
			if var.get('variable'):
				res['rgb'] = services.has_rgb(var['variable'], var['sensor'], var['collection'])
			self.add_result(res)

		self.run_task(f"Time series of {name}", work, done)

	def doy_args(self, var):
		"""The options of the chart by day of the year of the time series of VAR: {} for a line per year, or those of the
		seasonal profile (interannual, and other_variable and other_sensor for a variable on the right axis);
		ValueError if the right axis has the variable of the left one."""
		between, other = self.doy_interannual.currentData(), self.doy_other.currentData()
		args = {'interannual': between} if between else {}
		if other:
			if (var.get('variable'), var.get('sensor')) == (other['variable'], other['sensor']):
				raise ValueError(f"Right axis: {other['variable']} ({other['sensor']}) is already the variable of the "
				                 'left axis: choose another one, or None')
			args.update(other_variable=other['variable'], other_sensor=other['sensor'])
		return args

	def doy_changed(self):
		"""Between years and Right axis: only with the chart by day of the year."""
		for w in (self.doy_interannual, self.doy_other):
			w.setEnabled(self.doy.isChecked())

	def doy_interannual_changed(self):
		"""A line per year: no variable on the right axis (a line per variable needs a metric between the years)."""
		if self.doy_interannual.currentData() is None and self.doy_other.currentData():
			self.doy_other.setCurrentIndex(0)

	def doy_other_changed(self):
		"""A variable on the right axis: a line per variable, with the median between the years if it was a line per year
		(as services.time_series)."""
		if self.doy_other.currentData() and self.doy_interannual.currentData() is None:
			self.doy_interannual.setCurrentIndex(self.doy_interannual.findData('median'))

	def run_comparison(self, args, tmp):
		"""The comparison of the periods of the time series with the arguments ARGS (see series_call)."""

		def work():
			return services.compare_series(csv=os.path.join(tmp, 'comparison.csv'), **args)

		def done(res):
			from .results import comparison_png
			if not any(r['reference'] is not None or r['other'] is not None for r in res['profile']):
				self.message('The comparison has no values', 'Warning')
				return
			res['chart'] = comparison_png(res, args['step'], os.path.join(tmp, 'comparison.png'))  # in the main thread
			res['label'] = f"Comparison: {res['title']}"
			res['kind'] = 'comparison'
			res['call'] = parameters.make('compare_series', args)
			self.add_result(res)

		self.run_task(f"Comparison of periods of {data_name(args)}", work, done)

	def variable_changed(self):
		"""The metrics of the images, fixed at the only metric of the variable if it has one, and its pixel filters,
		greyed out and checked those always on if they are fixed (the snow cover frequency: the mean, the % of the clear
		observations with snow, without clouds and water), and unchecked and greyed out that of what the variable
		measures (sensors.MEASURES: snow with the NDSI, water with the NDWI, the Chl-a, the NDCI and the WAVI, aerosols
		with the ARSL). The filters chosen before come back with another variable.
		The fixed layers without dates (elevation, slope): only maps, so the period, the metrics, the filters, the time
		series and the trends greyed out. The data of Earth Engine outside the catalog (custom_entry): no pixel filters
		and, a fixed image, as those layers. The list Layer of the map, with the true colour only if it has one
		(update_map_kind)."""
		v = self.variable.currentData() or {}
		only = v.get('metric')
		static = bool(v.get('static'))
		for w in (self.ts_metric, self.trend_metric, self.map_metric, self.anim_metric):
			for label, m in ONLY_METRICS:  # offered only to the variable whose only metric it is
				i = w.findData(m)
				if only == m and i < 0:
					w.addItem(label, m)
				elif only != m and i >= 0:
					w.removeItem(i)
			if only:
				w.setCurrentIndex(max(0, w.findData(only)))
			w.setEnabled(not only and not static)
			w.setToolTip(f"{v['variable']} only takes the {only}" if only else '')
		yearly = only in YEARLY_METRICS  # one value per year: the steps and the temporal aggregation, Annual (or period)
		for w, value in ((self.step, 'annual'), (self.trend_step, 'annual'), (self.anim_step, 'annual')):
			if yearly:
				w.setCurrentIndex(max(0, w.findData(value)))
			w.setEnabled(not yearly)
			w.setToolTip(f"{v['variable']} has one value per year: the step is Annual" if yearly else '')
		if yearly and self.temporal.currentData() not in ('period', 'annual'):
			self.temporal.setCurrentIndex(max(0, self.temporal.findData('period')))
		for w in (self.compare_on, self.season_on, self.season_start, self.season_end,
		          self.temporal, self.interannual, self.series_box, self.trends_box, self.animation_box,
		          self.export_series_button):
			w.setEnabled(not static)
		dated = any(c['on'].isChecked() and not (c['variable'].currentData() or {}).get('static')
		            for c in getattr(self, 'where', []))  # the period of a condition with dates
		for w in (self.start, self.end):
			w.setEnabled(not static or dated)
		for w in (self.other_start, self.other_end):
			w.setEnabled(not static and self.compare_on.isChecked())
		fixed = v.get('fixed_filters')
		self.cloud_score.setEnabled(fixed is None)
		self.cloud_score.setToolTip(NO_FILTERS if v.get('custom') else '')
		self.snow_ndsi_enabled(v)
		self.topographic.setEnabled(bool(v.get('topographic')))  # the surface reflectance of Landsat
		self.topographic.setToolTip('' if v.get('topographic') else NO_TOPOGRAPHIC)
		self.harmonize.setEnabled(bool(v.get('harmonize')))  # Landsat 5 and 7 as 8 and 9: its surface reflectance
		self.harmonize.setToolTip('' if v.get('harmonize') else NO_HARMONIZE)
		seven = v.get('sensor') == 'Landsat' and not v.get('custom')
		self.landsat7.setEnabled(seven)
		self.landsat7.setToolTip('' if seven else NO_LANDSAT7)
		measured = set() if fixed is not None else \
			{f for f in sensors.FILTERS if v.get('variable') in sensors.MEASURES.get(f, ())}
		own = self.own_filters()
		self.set_filters = set(self.filters) if fixed is not None else measured
		self.chosen_filters = own if self.set_filters else None
		for k, w in self.filters.items():
			w.setChecked(k in fixed if fixed is not None else k not in measured and own[k])
			w.setEnabled(k not in self.set_filters)
			w.setToolTip('' if k not in self.set_filters else NO_FILTERS if v.get('custom') else
			             f"Fixed filters of {v['variable']}: they cannot be changed" if fixed is not None else
			             f"Off with {v['variable']}: removing the pixels with {k} would remove what it measures")
		self.update_map_kind()

	def update_map_kind(self):
		"""The list Layer of the group Map (the map of the variable, its true colour or both): only for the variables
		whose images have a true colour (services.has_rgb), not for the fixed layers, the data of Earth Engine outside
		the catalog nor the difference of «Compare with»; else it is the map of the variable, and its tooltip says
		why."""
		if not hasattr(self, 'map_kind'):  # not built yet
			return
		v = self.variable.currentData() or {}
		if v.get('custom'):
			why = (f"{v.get('name')}: the data of Earth Engine outside the catalog have no true colour (only the "
			       'variables of Sentinel-2 and Landsat and the cloud frequency of MODIS)')
		elif v.get('static'):
			why = f"{v['variable']} is a fixed layer, without dates: it has no images, nor true colour"
		elif not v.get('rgb'):
			why = (f"{v.get('variable')} of {v.get('sensor')} has no true colour: only the variables of Sentinel-2 and "
			       'Landsat and the cloud frequency of MODIS (MOD09GA, MYD09GA) have images with red, green and blue '
			       'bands')
		elif self.compare_on.isChecked():
			why = 'No true colour with Compare with: the map is the difference between two periods'
		else:
			why = None
		if why:
			self.map_kind.setCurrentIndex(self.map_kind.findData('index'))
		self.map_kind.setEnabled(why is None)
		self.map_kind.setToolTip(why or KINDS_TIP + ', with the same pixels')

	def update_trend_parts(self):
		step = self.trend_step.currentData()
		self.trend_part.clear()
		for p in trends.parts(step):
			self.trend_part.addItem('the year' if step == 'annual' else trends.part_label(step, p), p)
		self.trend_part.setEnabled(step != 'annual')

	def trend_table_call(self):
		"""The trend table of the region ('trend_table', its arguments: the statistic of the region is that of the time
		series); ValueError if the fields are not valid."""
		region, var = self.region(), self.variable_args()
		return 'trend_table', dict(region=region, **var, step=self.trend_step.currentData(),
		                           metric=self.trend_metric.currentData(), test=self.trend_test.currentData(),
		                           stat=self.stat.currentData(), **self.coverage_args())

	def run_trend_table(self):
		call = self.call_of('trend_table')
		if not call:
			return
		analysis, args = call
		tmp = tempfile.mkdtemp(prefix='monitoreo_')
		var = {k: v for k, v in args.items() if k != 'stat'}  # what its maps keep (add_result_map)

		def work():
			return services.trend_table(csv=os.path.join(tmp, 'trends.csv'), **args)

		def done(res):
			from .results import trends_png
			if not any(r['slope'] is not None for r in res['rows']):
				self.message('There are not enough years to compute trends (2 or more are needed)', 'Warning')
				return
			res['chart'] = trends_png(res, os.path.join(tmp, 'trends.png'))  # in the main thread
			res['label'] = f"Trends: {res['title']}"
			res['kind'] = 'trends'
			res['call'] = parameters.make(analysis, args)
			res['args'] = dict(var)
			res['maps'] = result_maps('trend_table', res['args'])
			self.add_result(res)

		self.run_task(f"Trends of {data_name(var)}", work, done)

	def trend_map_call(self):
		"""The trend map ('download_trend', its arguments; its tiles, trend_map, if it cannot be downloaded), with those
		of the Colour range that it takes (the others: see run_trend_map); ValueError if the fields are not valid."""
		region, var, step = self.region(), self.variable_args(), self.trend_step.currentData()
		return 'download_trend', dict(region=region, **var, step=step,
		                              part=self.trend_part.currentData() if step != 'annual' else None,  # as areas_call
		                              metric=self.trend_metric.currentData(),
		                              alpha=ALPHA if self.trend_alpha.isChecked() else None,
		                              test=self.trend_test.currentData(),
		                              **self.trend_colours.args(services.download_trend))

	def run_trend_map(self):
		call = self.call_of('trend_map')
		if not call:
			return
		args = call[1]
		region = args['region']
		opts = {k: v for k, v in args.items() if k != 'region'}
		folder = tempfile.mkdtemp(prefix='monitoreo_')
		# the Colour range: the slope stretched symmetric around 0 up to the largest of its percentiles (by default 1
		# and 99), or from the minimum and maximum given (those that the service does not take, here: see maps_work)
		pct, given = self.trend_colours.percentiles(), self.trend_colours.given()

		def work():
			# on the pixels of the data, or a warning; if the GeoTIFF cannot be downloaded, the tiles of trend_map
			return maps_work('index', region, opts, folder, services.download_trend, services.trend_map, given, None,
			                 pct)

		self.run_task(f"Trend map of {data_name(args)}", work, self.add_maps)

	def fill_area_years(self):
		"""The years of the land cover map of Area by class, its last one chosen (for Dynamic World, the last whole
		year)."""
		m = landcover.find(self.area_map.currentData())
		for box in (self.area_year, self.area_other_year):
			box.clear()
			for y in reversed(landcover.years(m)):
				box.addItem(str(y), y)
			box.setCurrentIndex(max(0, box.findData(landcover.default_year(m))))
		self.area_years_apart()

	def area_years_apart(self):
		"""With «changes to», two different years: the first one, the year before the other (its last one)."""
		if self.area_change.isChecked() and self.area_year.currentData() == self.area_other_year.currentData() and \
				self.area_year.count() > 1:
			self.area_year.setCurrentIndex(min(self.area_year.currentIndex() + 1, self.area_year.count() - 1))

	def zone_variable_changed(self):
		"""The breaks of the bands of a fixed layer, greyed out for a categorical layer (ECOREGION, BIOME): its classes
		are the zones."""
		klass = bool((self.zone_variable.currentData() or {}).get('categorical'))
		self.zone_breaks.setEnabled(not klass)
		self.zone_breaks.setToolTip('The classes of the layer are the zones: no breaks' if klass else '')

	def area_kind_changed(self):
		"""The map and year for the classes of a land cover map, the breaks for the classes of the variable; neither
		for its trend (that of the group Trends: its parts of the year and its metric) nor for the classes of a
		categorical layer (its own)."""
		kind = self.area_kind.currentData()
		for w in (self.area_map_row, self.area_map_label):
			w.setVisible(kind == 'landcover')
		for w in (self.area_breaks, self.area_breaks_label):
			w.setVisible(kind == 'breaks')

	def areas_call(self):
		"""The area by class ('area_by_class', its arguments): of a land cover map of a year (refused with the land
		cover mask or «Only the pixels where», as services), of the variable cut at the breaks, of its trend (with the
		options of the group Trends) or of the classes of a categorical layer; ValueError if the fields are not
		valid."""
		kind = self.area_kind.currentData()
		if kind == 'landcover':
			if self.landcover_box.isChecked() or any(c['on'].isChecked() for c in self.where):  # as services
				raise ValueError('The land cover mask and «Only the pixels where» are for the classes of a variable '
				                 '(breaks, trend), not for those of a land cover map: uncheck them')
			opts = {'region': self.region(), 'landcover': self.area_map.currentData(),
			        'year': self.area_year.currentData()}
			if self.area_change.isChecked():  # its changes to another year: the pairs of classes and a Sankey diagram
				opts['other_year'] = self.area_other_year.currentData()
			return 'area_by_class', opts
		region, var = self.region(), self.variable_args()
		if kind == 'classes':  # a categorical layer (ECOREGION, BIOME): its own classes
			if not (self.variable.currentData() or {}).get('categorical'):
				raise ValueError('The classes of a categorical layer: choose ECOREGION or BIOME (theme Ecosystems) as the '
				                 'variable')
			opts = dict(var)
		elif kind == 'breaks':  # the map of the variable, as the group Map (a fixed layer has no metric); its numbers
			opts = dict(var, breaks=classes.check_breaks(self.area_breaks.text()))
			if not (self.variable.currentData() or {}).get('static'):
				opts.update(metric=self.map_metric.currentData(), temporal=self.temporal.currentData(),
				            interannual=self.interannual.currentData())
		else:
			opts = dict(var, trend=True, step=self.trend_step.currentData(), metric=self.trend_metric.currentData(),
			            test=self.trend_test.currentData(), part=self.trend_part.currentData() if self.trend_step.currentData() != 'annual' else None)
		return 'area_by_class', dict(region=region, **opts)

	def run_areas(self):
		"""Hectares and % of each class over each feature of the region (services.area_by_class, see areas_call), in a
		window with its chart and table."""
		call = self.call_of('areas')
		if not call:
			return
		analysis, args = call
		if args.get('landcover'):
			what = f"{self.area_map.currentText().split(' · ')[0]} {args['year']}" + (
				f" to {args['other_year']}" if args.get('other_year') else '')
		else:
			what = data_name(args)
		tmp = tempfile.mkdtemp(prefix='monitoreo_')

		def work():
			return services.area_by_class(csv=os.path.join(tmp, 'areas.csv'), **args)

		def done(res):
			from monitoreo import charts
			path = os.path.join(tmp, 'areas.png')
			colours = {c['label']: c['colour'] for c in res['classes']}
			try:  # in the main thread; without matplotlib, the table only
				if res['mode'] == 'transitions':  # the Sankey diagram of the first feature, named if there are several
					first = res['rows'][0]['region'] if res['rows'] else None
					charts.sankey_png([(r['from_label'], r['to_label'], r['ha']) for r in res['by_landcover']
					                   if r['region'] == first], colours, path,
					                  res['title'] + (f' ({first})' if len(res['changed_ha']) > 1 else ''),
					                  (str(res['year']), str(res['other_year'])), source=res.get('data_source'))
				else:
					charts.areas_png(res['rows'], colours, path, res['title'], source=res.get('data_source'))
				res['chart'] = path
			except ImportError:
				res['chart'] = None
			res.update(kind='areas', label=f"Area by class: {what}", call=parameters.make(analysis, args))
			self.add_result(res)

		self.run_task(f"Area by class of {what}", work, done)

	def make_layout(self):
		"""A print layout of the map of the canvas for a report or a paper (as the figures of services.map_figure), opened
		in the layout designer: the map with a grid of coordinates, the legend of its layers, a scale bar, a north arrow,
		the title (the top layer) and the credits of the data of its layers and the citation of MonitorEO."""
		layout = figure_layout(self.iface.mapCanvas())
		self.iface.openLayoutDesigner(layout)
		self.message(f'Print layout «{layout.name()}»: export it as PDF, PNG or SVG from its window', 'Info', 8)

	def map_options(self, var):
		"""VAR with the metric, temporal aggregation and metric between years of the group Map (none for a fixed
		layer)."""
		if (self.variable.currentData() or {}).get('static'):
			return dict(var)
		return dict(var, metric=self.map_metric.currentData(), temporal=self.temporal.currentData(),
		            interannual=self.interannual.currentData())

	def zones_call(self):
		"""The statistics of the map of the variable in each band of a fixed layer or class of a categorical layer
		('region_stats' with zones, its arguments); ValueError if the fields are not valid."""
		region, var = self.region(), self.variable_args()
		z = self.zone_variable.currentData() or {}
		zones = {'variable': z.get('variable'), 'sensor': z.get('sensor')}
		if not z.get('categorical'):  # the bands of a fixed layer; those of a categorical layer are its classes
			zones['breaks'] = classes.check_breaks(self.zone_breaks.text())  # numbers, as every tool writes them
		klass = bool((self.variable.currentData() or {}).get('categorical'))
		stats = ['mode'] if klass else list(ZONE_STATS)  # class codes: the majority class of each zone
		return 'region_stats', dict(region=region, **self.map_options(var), stats=stats, zones=zones)

	def run_zones(self):
		"""The statistics of each band (services.region_stats with zones, see zones_call), in a window with its table
		(and chart, with matplotlib)."""
		call = self.call_of('zones')
		if not call:
			return
		analysis, args = call
		stats, zones = args['stats'], args['zones']
		klass = stats == ['mode']
		tmp = tempfile.mkdtemp(prefix='monitoreo_')

		def work():
			return services.region_stats(csv=os.path.join(tmp, 'zones.csv'), **args)

		def done(res):
			from monitoreo import charts
			path = os.path.join(tmp, 'zones.png')
			try:  # in the main thread; without matplotlib, the table only (no chart of class codes)
				if klass or not res['rows']:
					raise ImportError
				charts.zones_png(res['rows'], stats, path, res['title'], res.get('ylabel'), services.zone_name(zones),
				                 source=res.get('data_source'))
				res['chart'] = path
			except ImportError:
				res['chart'] = None
			res.update(kind='zones', label=f"Bands of {zones['variable']}: {data_name(args)}",
			           call=parameters.make(analysis, args))
			self.add_result(res)

		self.run_task(f"Statistics by band of {data_name(args)}", work, done)

	def line_points(self):
		"""[[lon, lat], ...] of the selected line of the layer of Line (or its first one), in WGS 84, or ValueError."""
		layer = self.line_layer.currentLayer()
		if layer is None:
			raise ValueError('choose a layer of lines in Line (add one, or draw a line in a new temporary layer)')
		return self.layer_line(layer)

	def layer_line(self, layer):
		"""[[lon, lat], ...] of the selected line of LAYER (or its first one), in WGS 84, or ValueError."""
		feats = list(layer.getSelectedFeatures()) or list(layer.getFeatures())
		if not feats:
			raise ValueError(f'the layer {layer.name()} has no lines')
		tr = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem('EPSG:4326'), QgsProject.instance())
		geom = feats[0].geometry()
		geom.transform(tr)
		parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
		points = [[p.x(), p.y()] for p in (parts[0] if parts else [])]
		if len(points) < 2:
			raise ValueError(f'the first line of {layer.name()} has fewer than two points')
		return points

	def transect_call(self):
		"""The profile of the map of the variable along the line of the layer of Line ('transect', its arguments);
		ValueError if the fields are not valid."""
		line = self.line_points()
		var = self.variable_args()
		return 'transect', dict(line=line, **self.map_options(var))

	def run_transect(self):
		"""The profile of the map of the variable along a line (services.transect, see transect_call), with the
		elevation, in a window with its table (and chart, with matplotlib)."""
		call = self.call_of('transect')
		if not call:
			return
		analysis, args = call
		tmp = tempfile.mkdtemp(prefix='monitoreo_')

		def work():
			return services.transect(csv=os.path.join(tmp, 'profile.csv'), **args)

		def done(res):
			from monitoreo import charts
			path = os.path.join(tmp, 'profile.png')
			try:  # in the main thread; without matplotlib, the table only
				charts.transect_png(res['rows'], path, res['title'], res.get('ylabel'), source=res.get('data_source'))
				res['chart'] = path
			except ImportError:
				res['chart'] = None
			res.update(kind='transect', label=f"Profile of {data_name(args)}", call=parameters.make(analysis, args))
			self.add_result(res)

		self.run_task(f"Profile of {data_name(args)}", work, done)

	def animation_call(self):
		"""The animation of the variable over the region ('timelapse', its arguments: with the Colour range, each frame
		stretched between its own percentiles, by default 1 and 99, or from the minimum and maximum given, and with Same
		colours in every frame, one colour range for all of them); ValueError if the fields are not valid."""
		region, var = self.region(), self.variable_args()
		return 'timelapse', dict(region=region, **var, step=self.anim_step.currentData(),
		                         metric=self.anim_metric.currentData(), fps=self.anim_fps.value(),
		                         **self.anim_colours.args(services.timelapse),
		                         **({} if self.anim_same.isChecked() else {'same_colours': False}))

	def run_timelapse(self):
		"""Animation of the variable over the region (services.timelapse, see animation_call): a GIF with a frame per
		step, in its window and in the list of the results of the session."""
		call = self.call_of('animation')
		if not call:
			return
		analysis, args = call
		path = os.path.join(tempfile.mkdtemp(prefix='monitoreo_'), 'animation.gif')

		def work():
			return services.timelapse(path=path, **args)

		def done(res):
			res.update(kind='animation', label=f"Animation of {data_name(args)} ({args['step']})",
			           call=parameters.make(analysis, args))
			self.add_result(res)

		self.run_task(f"Animation of {data_name(args)}", work, done)

	def update_series_list(self):
		self.series_list.clear()
		for i, res in enumerate(self.series):
			self.series_list.addItem(f"{i + 1}. {res['label']}", i)
		self.series_list.setEnabled(bool(self.series))
		self.show_series_button.setEnabled(bool(self.series))

	def show_series(self):
		"""Open the window of the chosen series, trends, comparison or burn severity (or bring it to the front if it
		is open)."""
		from .results import AnimationDialog, ResultDialog, SeriesDialog
		i = self.series_list.currentData()
		if i is None:
			return
		dlg = self.series_dialogs.get(i)
		if dlg is None:
			res = self.series[i]
			kind = res.get('kind', 'series')
			cls = SeriesDialog if kind == 'series' else AnimationDialog if kind == 'animation' else ResultDialog
			dlg = self.series_dialogs[i] = cls(res, self.iface.mainWindow(), self.add_result_map)
		dlg.show()
		dlg.raise_()
		dlg.activateWindow()

	def map_kind_chosen(self):
		"""The layers of the map of the group Map: the map of the variable ('index'), its true colour ('rgb') or both
		(never of a fixed layer or a difference: see update_map_kind)."""
		static = (self.variable.currentData() or {}).get('static')
		return 'index' if static or self.other_period() or not self.map_kind.isEnabled() else \
			self.map_kind.currentData()

	def map_call(self):
		"""The map of the group Map ('download_image', its arguments; its tiles, map_layer, if it cannot be
		downloaded): with Compare with, the difference between the periods ('download_comparison'); its true colour
		alone, 'download_rgb' (with Both, the true colour has the arguments of the map). ValueError if the fields are
		not valid."""
		region, var = self.region(), self.variable_args()
		other = self.other_period()
		opts = self.map_options(var)  # no temporal metric for the fixed layers
		if other:
			opts.update(other_start=other[0], other_end=other[1])
		analysis = 'download_comparison' if other else 'download_rgb' if self.map_kind_chosen() == 'rgb' else \
			'download_image'
		if not (self.variable.currentData() or {}).get('categorical'):  # a categorical layer: the colours of its classes
			opts.update(self.map_colours.args(getattr(services, analysis)))  # those that its service takes
		return analysis, dict(region=region, **opts)

	def run_map(self):
		call = self.call_of('map')
		if not call:
			return
		analysis, args = call
		region = args['region']
		opts = {k: v for k, v in args.items() if k != 'region'}  # maps_work checks the pixels first (check_pixels)
		folder = tempfile.mkdtemp(prefix='monitoreo_')
		other = analysis == 'download_comparison'
		download, tiles = ((services.download_comparison, services.compare_map) if other else
		                   (services.download_image, services.map_layer))
		kind = self.map_kind_chosen()
		title = {'index': 'Map', 'rgb': 'True colour', 'both': 'Map and true colour'}[kind]
		# the colour range of the group Map (those of its parts that the service does not take, here); with True colour
		# alone, its minimum and maximum are those of the reflectance
		pct, given = self.map_colours.percentiles(), self.map_colours.given()
		stretch = given if kind == 'rgb' and None not in given else None

		def work():
			"""The map as a GeoTIFF with the values (with OTHER, the difference between the periods, and both) and/or
			its true colour; if they cannot be downloaded, Earth Engine tiles (colours only)."""
			return maps_work(kind, region, opts, folder, download, tiles, given, stretch, pct)

		self.run_task(f"{title} of {data_name(opts)}", work,
		              lambda r: self.add_maps(r, kept={'rgb_stretch': stretch} if stretch else None))

	def add_maps(self, r, name=None, rgb_name=None, group=None, zoom=True, period=None, kept=None):
		"""Add the layers of R (see maps_work): first its true colour, then the map of the variable on top of it, both
		with PERIOD in the Temporal Controller, and zoom to the first one (with ZOOM). NAME and RGB_NAME: their names
		(by default, those of the results). KEPT (the result of a series with Same colours in every map of a series):
		the colours of its first map ('colors') and the stretch of its first true colour ('rgb_stretch'), kept there
		for its next maps, so that they can be compared; without it, each map with its own colour range (that of the
		group Map: by default its percentiles 1 and 99)."""
		kept = {} if kept is None else kept
		if r.get('rgb_error'):  # only the true colour failed: the map is added all the same
			self.message(f"True colour of {name or r['index']['name']}: {r['rgb_error']} (only the map was added)",
			             'Warning', 15)
		c = r.get('rgb')
		if c is not None:
			if 'rgb_stretch' not in kept and c.get('min') is not None:
				kept['rgb_stretch'] = (c['min'], c['max'])
			if 'url' in c:
				self.add_tile_layer(c, rgb_name, group, zoom=zoom, period=period)
			else:
				self.add_rgb_layer(c, rgb_name, group, kept.get('rgb_stretch'), zoom=zoom, period=period)
			zoom = False
		i = r.get('index')
		if i is not None:
			if 'colors' not in kept and i.get('min') is not None:
				kept['colors'] = (i['min'], i['max'])
			elif i.get('min') is not None and i.get('classes') is None:  # those of the first map, to compare them
				i['min'], i['max'] = kept['colors']
				i['stretch'] = {'method': 'first', 'text': 'the colour range of the first map of the series, so that '
				                'its maps can be compared'}
			if 'url' in i:
				self.add_tile_layer(i, name, group, zoom=zoom, period=period)
			else:
				self.add_map_layer(i, name, group, kept.get('colors'), zoom=zoom, period=period)

	def add_map_layer(self, res, name=None, group=None, colors=None, zoom=True, period=None):
		"""Add the GeoTIFF of a map with the colour ramp of MonitorEO (from its min to its max: by default its
		percentiles 1 and 99, maps.STRETCH; or COLORS: (min, max)) and zoom to it; with GROUP, in that group of the
		layer tree, and with PERIOD (first and last day), with those days in the Temporal Controller. Its abstract and
		the message say the colour range and how it was stretched (stretch_note)."""
		name = name or res['name']
		layer = QgsRasterLayer(res['file'], name)
		if not layer.isValid():
			raise RuntimeError(f"QGIS could not open {res['file']}")
		if res.get('classes') is not None:  # a categorical layer: a colour per class, with its code and name
			if res['classes']:
				paletted(layer, 1, res['classes'])
			else:
				self.message(f"{name}: no class in the region", 'Warning', 10)
		elif res['min'] is None:
			self.message(f"{name}: no values in the region (no images, or all filtered out)", 'Warning', 10)
		else:
			pseudocolor(layer, *given_colours(colors, res['min'], res['max']), res['palette'])
		bands = ', '.join(res.get('bands') or [])
		note = stretch_note(res) if res.get('classes') is None else ''
		# (the data of Earth Engine outside the catalog may have no unit: none was given)
		layer.setAbstract(f"MonitorEO: {res['name']} {unit_text(res)}, pixels of {res['resolution']:g} m"
		                  + (f", {res['images']:,} images" if res.get('images') is not None else '')
		                  + (f", bands {bands}" if bands else '') + (f". Colour ramp: {note}" if note else '')
		                  + f". Temporary GeoTIFF: {res['file']}" + references_text(res))
		if period:
			dated(layer, *period)
		add_layer(layer, group)
		if zoom:
			self.zoom_to(layer.extent(), layer.crs())
		self.message(f"Layer added: {name}, pixels of {res['resolution']:g} m" + (f", {note}" if note else '')
		             + '. Query the values with the Identify Features tool', 'Success', 10)

	def add_rgb_layer(self, res, name=None, group=None, stretch=None, zoom=True, period=None):
		"""Add the GeoTIFF of a true colour (services.download_rgb: the bands red, green and blue, reflectance) with the
		three bands stretched together between its percentiles 2 and 98 (maps.RGB_STRETCH, or those of the colour range
		of the group Map) or STRETCH ((min, max), None where not given: that of the first true colour of a series, so
		that its dates can be compared, or the minimum and maximum of the colour range) and zoom to it; with GROUP and
		PERIOD, as add_map_layer."""
		name = name or res['name']
		layer = QgsRasterLayer(res['file'], name)
		if not layer.isValid():
			raise RuntimeError(f"QGIS could not open {res['file']}")
		lo, hi = given_colours(stretch, res['min'], res['max'])
		if res['min'] is None:
			self.message(f"{name}: no values in the region (no images, or all filtered out)", 'Warning', 10)
		if lo is not None and hi is not None:
			rgb(layer, lo, hi)
		caption = rgb_caption(lo, hi, None if stretch else res.get('stretch')) if lo is not None and hi is not None \
			else 'True colour (red, green, blue)'
		layer.setAbstract(f"MonitorEO: {res['name']} {res['unit']}, pixels of {res['resolution']:g} m"
		                  + (f", {res['images']:,} images" if res.get('images') is not None else '')
		                  + f", bands {', '.join(res.get('bands') or ['red', 'green', 'blue'])}. {caption}. "
		                  f"Temporary GeoTIFF: {res['file']}" + references_text(res))
		if period:
			dated(layer, *period)
		add_layer(layer, group)
		if zoom:
			self.zoom_to(layer.extent(), layer.crs())
		self.message(f"Layer added: {name}, pixels of {res['resolution']:g} m. {caption}. Query the reflectance with "
		             'the Identify Features tool', 'Success', 10)

	def zoom_to(self, rect, crs):
		canvas = self.iface.mapCanvas()
		tr = QgsCoordinateTransform(crs, canvas.mapSettings().destinationCrs(), QgsProject.instance())
		r = tr.transformBoundingBox(rect)
		r.scale(1.05)
		canvas.setExtent(r)
		canvas.refresh()

	def add_tile_layer(self, res, name=None, group=None, zoom=True, period=None):
		"""Add the Earth Engine tiles RES of a map (with its colour ramp) or of a true colour (services.rgb_map: without
		palette, the bands red, green and blue), when its GeoTIFF could not be downloaded; with GROUP and PERIOD, as
		add_map_layer."""
		name = name or res['name']
		uri = QgsDataSourceUri()
		uri.setParam('type', 'xyz')
		uri.setParam('url', res['url'])
		uri.setParam('zmin', '0')
		uri.setParam('zmax', '20')
		layer = QgsRasterLayer(bytes(uri.encodedUri()).decode(), name, 'wms')
		if not layer.isValid():
			raise RuntimeError('QGIS could not open the tiles of Earth Engine')
		# the unit of a map of values (see unit_text); that of a true colour, as it comes
		unit = unit_text(res) if res.get('palette') else str(res.get('unit') or '')
		if res.get('classes') is not None:  # a categorical layer: its classes in the region, with their colours
			unit = ''
			colours = f"{len(res['classes'])} classes: " + '; '.join(f"{c['label']} {c['color']}" for c in res['classes'])
			shown = f"{len(res['classes'])} classes"
		elif res.get('palette'):
			text = res['stretch'].get('text') if isinstance(res.get('stretch'), dict) else None
			colours = (f"Color ramp from {res['min']:.4g} to {res['max']:.4g}" + (f" ({text})" if text else '')
			           + f": {', '.join('#' + c for c in res['palette'])}")
			shown = f"from {res['min']:.4g} to {res['max']:.4g} {unit}"
		else:  # a true colour
			colours = shown = rgb_caption(res['min'], res['max'], res.get('stretch'))
		layer.setAbstract(f"MonitorEO: {res['name']} {unit}".rstrip() + f". {colours}. Earth Engine tiles, valid for a "
		                  'few hours.' + references_text(res))
		if period:
			dated(layer, *period)
		add_layer(layer, group)
		if zoom:
			self.zoom_to(QgsRectangle(*res['bounds']), QgsCoordinateReferenceSystem('EPSG:4326'))
		self.message(f"Tile layer added: {name} ({shown}; no queryable values: the GeoTIFF could not be downloaded: "
		             f"{res.get('error')})", 'Warning', 15)

	def result_group(self, res):
		"""The group of the layer tree with the maps of the result RES (made the first time, on top)."""
		root = QgsProject.instance().layerTreeRoot()
		return root.findGroup(res['label']) or root.insertGroup(0, res['label'])

	def add_result_map(self, res, entry, significant=False, kind='index'):
		"""Add the map ENTRY (one of res['maps']: its whole period or one of its steps) of the series or trends RES,
		as a GeoTIFF in the group of the result, with its own colours (the Colour range of the group Map, or of the
		group Trends for trends: its percentiles 1 and 99 by default) or, with Same colours in every map of a series or
		trends (checked by default), those of the first map of the result, so that its maps can be compared; the dates of a series, with
		their days in the Temporal Controller of QGIS. Trends with SIGNIFICANT: only the pixels with p < ALPHA. A series
		with KIND 'rgb' or 'both': the true colour of the same images and pixels (services.download_rgb, with the same
		arguments and on the same grid), stretched as the first true colour of the result with Same colours, alone or
		under the map, with the same days. If a GeoTIFF cannot be downloaded, Earth Engine tiles."""
		a = res['args']
		region = a['region']
		# the same pixels as the series: its filters, season and conditions (those with dates, over its whole period);
		# of the data of Earth Engine outside the catalog, their ID, band, scale, offset and unit (SOURCE)
		var = {k: a[k] for k in ('variable', 'sensor', 'collection', 'quality', 'season', 'where') + SOURCE if k in a}
		folder = tempfile.mkdtemp(prefix='monitoreo_')
		if res['kind'] == 'trends':
			kind = 'index'
			opts = dict(var, start=a['start'], end=a['end'], step=entry.get('step') or a['step'], part=entry.get('part'),
			            metric=a['metric'], alpha=ALPHA if significant else None, test=a.get('test') or 'mk')
			download, tiles = services.download_trend, services.trend_map
		else:
			opts = dict(var, start=entry['start'], end=entry['end'], metric=a['metric'])
			download, tiles = services.download_image, services.map_layer
		try:
			colours = self.trend_colours if res['kind'] == 'trends' else self.map_colours
			pct, given = colours.percentiles(), colours.given()
		except ValueError as e:
			self.message(str(e), 'Warning')
			return
		same = self.map_same.isChecked()
		if tuple(pct) != tuple(maps.STRETCH):  # the services of series and trends take them
			opts['percentiles'] = list(pct)
		if kind == 'rgb' and not same and given != (None, None):  # the true colour alone: its reflectance
			opts.update({k: v for k, v in zip(('vmin', 'vmax'), given) if v is not None})
		# with Same colours, (min, max) of the first map and of the first true colour of the result
		colors = (res.get('colors') if same else None) or (given if given != (None, None) else None)
		stretch = res.get('rgb_stretch') if same else None
		label = f"{res['title'].split(' | ')[0]} · {entry['label']}"
		name = label + (' (p < 0.05)' if significant else '')
		period = (entry['start'], entry['end']) if res['kind'] == 'series' and entry['key'] else None
		title = {'index': f'Map of {name}', 'rgb': f'True colour of {label}', 'both': f'Map and true colour of {label}'}

		def work():
			return maps_work(kind, region, opts, folder, download, tiles, colors, stretch, pct)

		def done(r):
			first = not res.get('zoomed')  # zoom to the first map of the result
			res['zoomed'] = True
			self.add_maps(r, name, f'{label} · true colour', self.result_group(res), first, period, res if same else None)

		self.run_task(title[kind], work, done)

	def export_map_call(self):
		"""The export of the map to Google Drive ('export_image', its arguments: the options of the group Map, none for
		the fixed layers, and the resolution; the Drive folder is its output); ValueError if the fields are not
		valid."""
		region, var = self.region(), self.variable_args()
		return 'export_image', dict(region=region, **self.map_options(var), resolution=self.resolution.value() or None)

	def run_export_image(self):
		call = self.call_of('export_map')
		if not call:
			return
		args = call[1]
		folder = self.folder.text().strip() or 'MonitorEO'
		self.run_task(f"Export the map of {data_name(args, sensor=False)}",
		              lambda: services.export_image(folder=folder, **args), self.follow_export)

	def export_series_call(self):
		"""The export of the time series to Google Drive ('time_series_to_drive', its arguments: the options of the
		group Time series; the Drive folder is its output); ValueError if the fields are not valid."""
		region, var = self.region(), self.variable_args()
		return 'time_series_to_drive', dict(region=region, **var, step=self.step.currentData(),
		                                    metric=self.ts_metric.currentData(), stat=self.stat.currentData(),
		                                    **self.coverage_args())

	def run_export_series(self):
		call = self.call_of('export_series')
		if not call:
			return
		args = call[1]
		folder = self.folder.text().strip() or 'MonitorEO'
		self.run_task(f"Export the series of {data_name(args, sensor=False)}",
		              lambda: services.time_series_to_drive(folder=folder, **args), self.follow_export)

	# Burn severity ----------------------------------------------------------------------------------------------

	def theme_has(self, name):
		"""Whether the theme chosen has the analysis NAME of its own (e.g. burn_severity, of the fires), as themeHas of
		the Earth Engine app: with «All the variables», every analysis."""
		key = self.theme.currentData()
		return key is None or any(t['key'] == key and name in t['analyses'] for t in services.themes('en'))

	def show_analyses(self):
		"""The groups of the analyses of a theme, shown only in that theme (and with «All the variables»)."""
		on = self.theme_has('burn_severity')
		self.fire_box.setVisible(on)
		i = self.tabs.indexOf(self.tab_widgets['Fire'])
		if hasattr(self.tabs, 'setTabVisible'):  # Qt 5.15 and later
			self.tabs.setTabVisible(i, on)
		else:
			self.tabs.setTabEnabled(i, on)

	def fill_fire_sensors(self, choose=None):
		"""The sensors of the burn index chosen (services.BURN_SENSORS): Sentinel-2 and Landsat, and MODIS Terra and
		Aqua only for the RdNBR. Keeps the sensor chosen (at first, CHOOSE) if the index has it; going back to the dNBR
		or the RBR with MODIS chosen chooses Landsat (as the Earth Engine app: a big region), never MODIS; else,
		Sentinel-2."""
		index = self.fire_index.currentData()
		current = self.fire_sensor.currentData() if self.fire_sensor.count() else choose
		items = FIRE_SENSORS + (FIRE_MODIS if 'Modis' in services.BURN_SENSORS.get(index, ()) else [])
		values = [v for _, v in items]
		if current not in values:
			current = 'Landsat' if current in [v for _, v in FIRE_MODIS] else 'Sentinel-2'
		self.fire_sensor.blockSignals(True)
		self.fire_sensor.clear()
		for i, (label, value) in enumerate(items):
			self.fire_sensor.addItem(label, value)
			if value in FIRE_TIPS:
				self.fire_sensor.setItemData(i, FIRE_TIPS[value], Qt.ItemDataRole.ToolTipRole)
		self.fire_sensor.setCurrentIndex(values.index(current))
		self.fire_sensor.blockSignals(False)

	def perimeter_changed(self):
		"""The options of the perimeter of the burned area, only with it: the index from which a pixel is burned,
		whose hint is the value of the classes of the index chosen (the RBR has none: it has to be written), and the
		smallest patch and island."""
		on = self.fire_perimeter.isChecked()
		self.fire_burned_min.setEnabled(on)
		self.fire_min_ha.setEnabled(on)
		self.fire_keep.setEnabled(on)
		self.fire_seed.setEnabled(on and self.fire_keep.currentData() == 'seed')
		index = self.fire_index.currentData()
		self.fire_burned_min.setPlaceholderText(f"{index} {fire.CLASSES[index]['burned']:g}" if index in fire.CLASSES
		                                        else 'write the RBR, e.g. 0.1')

	def perimeter_args(self, index, stem):
		"""The arguments of the perimeter of the burned area of services.burn_severity (perimeter, burned_min,
		min_ha), {} without it; ValueError if the value from which a pixel is burned is not a number, or is missing
		with the RBR."""
		if not self.fire_perimeter.isChecked():
			return {}
		text = self.fire_burned_min.text().strip().replace(',', '.')
		try:
			low = float(text) if text else None
		except ValueError:
			raise ValueError(f'Burned from: write a number (the {index} from which a pixel is burned), or nothing for '
			                 'that of its classes') from None
		if low is None and index not in fire.CLASSES:
			raise ValueError(f'The {index} has no classes: write in Burned from the {index} from which a pixel is '
			                 'burned (e.g. 0.1), or uncheck Perimeter')
		keep = self.fire_keep.currentData()
		chosen = {'largest': True} if keep == 'largest' else {}
		if keep == 'seed':  # lon and lat, separated by a comma, a semicolon or spaces
			point = [v for v in re.split(r'[,;\s]+', self.fire_seed.text().strip()) if v]
			try:
				seed = fire.check_keep(point)
				if seed is None:
					raise ValueError('no point')
			except ValueError as e:
				raise ValueError(f'Keep the patch nearest to a point: write it as lon, lat in degrees, e.g. -3.49, '
				                 f'36.98 ({e})') from None
			chosen = {'seed': seed}
		return {'perimeter': stem + '_perimeter.gpkg', 'burned_min': low, 'min_ha': self.fire_min_ha.value(), **chosen}

	def offset_args(self):
		"""The offset region of services.burn_severity (offset_region: the polygons of the layer of Offset region),
		{} without one."""
		layer = self.fire_offset.currentLayer()
		return {'offset_region': self.layer_region(layer, None)} if layer is not None else {}

	def fire_source(self):
		"""The sensor and the collection of the burn severity (services.burn_severity): MODIS is the sensor 'Modis'
		with the collection of Terra (MOD09GA) or Aqua (MYD09GA); Sentinel-2 and Landsat go without a collection."""
		value = self.fire_sensor.currentData()
		if value in [v for _, v in FIRE_MODIS]:
			return 'Modis', value
		return value, None

	def fire_periods(self):
		"""The periods before and after the fire ([first day, last day] each), checked."""
		day = lambda key: self.fire_dates[key].date().toString('yyyy-MM-dd')  # noqa: E731
		before, after = [day('before_start'), day('before_end')], [day('after_start'), day('after_end')]
		if before[0] > before[1] or after[0] > after[1]:
			raise ValueError('Burn severity: each period has to end after it starts')
		if before[1] >= after[0]:
			raise ValueError('Burn severity: the period before the fire has to end before the period after it starts')
		return before, after

	def burn_call(self, folder=''):
		"""The burn severity of a fire over the region ('burn_severity', its arguments), with the pixel filters and the
		conditions of «Only the pixels where» of the panel (over the period before the fire) and, with Perimeter, the
		polygons of the burned area (a GeoPackage in FOLDER: its name, in the parameters); ValueError if the fields
		are not valid."""
		region = self.region()
		before, after = self.fire_periods()
		where = self.where_args(before)
		quality = self.quality_args(own=True)  # the NBR, whatever the variable selected
		(sensor, collection), index = self.fire_source(), self.fire_index.currentData()
		if sensor != 'Landsat':  # the topographic correction: only for Landsat (Sentinel-2 comes already corrected)
			quality.pop('topographic', None)
		if sensor not in sensors.SNOW_NDSI:  # the snow by its NDSI: not for MODIS
			quality.pop('snow_ndsi', None)
		if sensor != 'Landsat':  # Landsat 5 and 7 as 8 and 9, Landsat 7 after 2003: only Landsat
			quality.pop('harmonize', None)
			quality.pop('landsat7', None)
		stem = os.path.join(folder, burn_stem(index))
		more = {'collection': collection} if collection else {}  # MODIS (RdNBR): Terra or Aqua
		outline = self.perimeter_args(index, stem)  # the polygons of the burned area
		return 'burn_severity', dict(region=region, sensor=sensor, start=before[0], end=before[1], other_start=after[0],
		                             other_end=after[1], quality=quality, index=index,
		                             where=where, **more, **outline, **self.offset_args())

	def run_burn(self):
		"""Burn severity of a fire over the region (services.burn_severity, see burn_call): the window of its table
		(hectares of each class of the USGS and burned area, statistics of the RBR, or hectares of each class of Miller
		& Thode 2007, changed area and statistics of the RdNBR) and its GeoTIFF, in colours."""
		folder = tempfile.mkdtemp(prefix='monitoreo_')
		call = self.call_of('burn', folder=folder)
		if not call:
			return
		analysis, args = call
		index, collection = args['index'], args.get('collection')
		stem = os.path.join(folder, burn_stem(index))
		source = self.fire_sensor.currentText().split(' (')[0]  # Sentinel-2, Landsat, MODIS Terra or MODIS Aqua

		def work():
			# on the pixels of the data, or a warning (the other sensors it proposes: those of this burn index)
			services.check_pixels(args['region'], MAP_PIXELS, {'dNBR': 'NBR'}.get(index, index), args['sensor'],
			                      start=args['start'], end=args['end'], two_periods=True,
			                      sensors=services.BURN_SENSORS[index], **({'collection': collection} if collection else {}))
			return services.burn_severity(path=stem + '.tif', csv=stem + '.csv', **args)

		def done(res):
			if not any((r.get('ha') or 0) > 0 for r in res.get('classes') or res.get('stats') or []):
				self.message(f"{res['title'].split(' | ')[0]}: no values in the region (no images in a period, or all "
				             'filtered out)', 'Warning', 15)
				return
			res['label'] = burn_label(res['title'], collection)
			res['kind'] = 'burn'
			res['call'] = parameters.make(analysis, args)
			res['args'] = {k: args[k] for k in ('region', 'sensor', 'start', 'end', 'other_start', 'other_end', 'index',
			                                    'collection') if k in args}
			self.add_burn_layer(res)
			if res.get('perimeter'):
				self.add_perimeter_layer(res)
			self.add_result(res)

		self.run_task(f'Burn severity ({index}, {source})', work, done)

	def add_burn_layer(self, res):
		"""Add the GeoTIFF of the burn severity RES coloured as in the other tools (fire.map_style, as the assistant):
		the classes of its band severity, with their names and values in the legend (those of the USGS for the dNBR,
		those of Miller & Thode 2007 for the RdNBR), or the RBR from red (burned) to green (regrowth)."""
		name = res.get('label') or res['title']
		layer = QgsRasterLayer(res['file'], name)
		if not layer.isValid():
			raise RuntimeError(f"QGIS could not open {res['file']}")
		style = fire.map_style(res.get('bands'))
		if style and style.get('classes'):
			paletted(layer, style['band'], [dict(c, label=fire.class_label(c)) for c in style['classes']])
		elif style:
			pseudocolor(layer, style['min'], style['max'], style['palette'], band=style['band'])
		layer.setAbstract(f"MonitorEO: {name}, pixels of {res['resolution']:g} m, bands {', '.join(res['bands'])}. "
		                  f"Temporary GeoTIFF: {res['file']}" + references_text(res))
		add_layer(layer)
		self.zoom_to(layer.extent(), layer.crs())
		self.message(f"Layer added: {name}, pixels of {res['resolution']:g} m. Query the values with the Identify "
		             'Features tool', 'Success', 10)

	def add_perimeter_layer(self, res):
		"""Add the perimeter of the burned area of the burn severity RES (its GeoPackage) over its GeoTIFF: its
		polygons, outlined in black without fill, to choose in Region → Layer for the analyses inside it."""
		ha = res.get('perimeter_ha') or {}
		if not any(ha.values()):
			self.message(f"No burned area for the perimeter ({res['index']} ≥ {res['burned_min']:g}, patches of at "
			             f"least {res['min_ha']:g} ha)", 'Warning', 10)
			return
		name = f"{res.get('label') or res['title']} · perimeter"
		layer = QgsVectorLayer(f"{res['perimeter']}|layername=perimeter", name, 'ogr')
		if not layer.isValid():
			raise RuntimeError(f"QGIS could not open {res['perimeter']}")
		layer.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '0,0,0,0', 'outline_color': '0,0,0,255',
		                                                       'outline_width': '0.6'}))
		layer.setAbstract(f"MonitorEO: perimeter of the burned area of {name}: {res['index']} ≥ {res['burned_min']:g}, "
		                  f"without the patches nor the unburned islands of less than {res['min_ha']:g} ha. "
		                  f"Temporary GeoPackage: {res['perimeter']}" + references_text(res))
		add_layer(layer)
		total = sum(ha.values())
		self.message(f'Layer added: {name}, {total:,.1f} ha. Choose it in Region → Layer to analyse inside it',
		             'Success', 10)

	# Exports ----------------------------------------------------------------------------------------------------

	def follow_export(self, res):
		res['state'] = 'PENDING'
		self.exports.append(res)
		self.show_exports()
		self.message(f"Exporting {res['file']} to Google Drive/{res['folder']}", 'Info')
		if not self.timer.isActive():
			self.timer.start(POLL_MS)

	def show_exports(self):
		self.export_status.setText('\n'.join(f"{e['file']}: {e['state'].lower()}" for e in self.exports[-6:]))

	def poll_exports(self):
		running = [e for e in self.exports if e['state'] not in ('SUCCEEDED', 'FAILED', 'CANCELLED', 'UNKNOWN')]
		if not running:
			self.timer.stop()
			return

		def work():
			return [(e, services.task_status(e['operation'])) for e in running]

		def done(states):
			for e, st in states:
				if st['state'] != e['state']:
					e['state'] = st['state']
					if st['state'] == 'SUCCEEDED':
						self.exported(e)
					elif st['state'] in ('FAILED', 'CANCELLED', 'UNKNOWN'):
						self.message(f"{e['file']}: {st['state'].lower()} {st['error'] or ''}", 'Critical', 15)
			self.show_exports()

		task = QgsTask.fromFunction('MonitorEO: state of the exports', lambda t: work(),
		                            on_finished=lambda exc, r=None: done(r) if exc is None else None)
		self.tasks.append(task)
		QgsApplication.taskManager().addTask(task)

	def exported(self, e):
		"""Open an exported GeoTIFF from Google Drive for desktop, if it is on this computer."""
		roots = services.local_drive_folders()
		files = []
		for root in roots:
			files += services.find_exported(os.path.join(root, e['folder']), e['file'])
		tifs = [f for f in files if f.lower().endswith('.tif')]
		if not tifs:
			self.message(f"{e['file']} is in Google Drive/{e['folder']}", 'Success', 10)
			return
		path = tifs[0]
		if len(tifs) > 1:
			from osgeo import gdal
			path = os.path.join(tempfile.mkdtemp(prefix='monitoreo_'), os.path.splitext(e['file'])[0] + '.vrt')
			gdal.BuildVRT(path, tifs)
		layer = QgsRasterLayer(path, os.path.splitext(e['file'])[0])
		if layer.isValid():
			QgsProject.instance().addMapLayer(layer)
			self.message(f"{e['file']} added from Google Drive ({path})", 'Success', 10)
